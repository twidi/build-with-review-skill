#!/usr/bin/env python3
"""Supersede one unopened Correction Round allocation under one authority lease."""

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import sys
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
COMMON = WORKSPACE / "prompts" / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
    normalize_allocation,
    recovery_relative_path,
)

MARKER_NAME = "correction-allocation-supersede-in-progress"
BLOCKING_MARKERS = {
    "correction-artifact-in-progress",
    "correction-round-open-in-progress",
    "correction-round-void-in-progress",
    "correction-product-authority-in-progress",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def operation_identity(args):
    reason_sha256 = sha256(args.reason.encode())
    return (
        f"allocation-supersede:{args.built}:{args.round}:"
        f"{args.allocation}:{args.outcome}:{reason_sha256}"
    )


def read_real_file(path, subject):
    try:
        relative = pathlib.Path(path).relative_to(WORKSPACE)
    except ValueError:
        fail(f"{subject} is outside the workspace")
    with WorkspaceFileAnchor(WORKSPACE, relative, subject) as anchored:
        return anchored.read_regular()


def frozen_member(source, destination, subject, *, allow_moved):
    with WorkspaceFileAnchor(WORKSPACE, source, f"{subject} source") as source_file, \
            WorkspaceFileAnchor(WORKSPACE, destination, f"{subject} destination") as destination_file, \
            WorkspaceFileAnchor(
                WORKSPACE, recovery_relative_path(source), f"{subject} recovery",
            ) as recovery_file:
        source_status = source_file.status()
        destination_status = destination_file.status()
        recovery_status = recovery_file.status()
        if recovery_status is not None:
            if not allow_moved:
                fail(f"{subject} recovery precedes its owner marker")
            return recovery_file.read_regular()
        if source_status is not None and destination_status is not None:
            fail(f"both source and destination exist for {subject}")
        if not allow_moved and source_status is None:
            fail(f"{subject} moved before its owner marker")
        if not allow_moved and destination_status is not None:
            fail(f"{subject} destination precedes its owner marker")
        if source_status is not None:
            return source_file.read_regular()
        if allow_moved and destination_status is not None:
            return destination_file.read_regular()
        fail(f"{subject} is unavailable")


def atomic_marker(path, account):
    if path.exists() or path.is_symlink():
        fail("another allocation supersession owner is already pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the allocation supersession marker had a short write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_marker(path):
    raw = read_real_file(path, "the allocation supersession marker")
    try:
        account = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        fail(f"the allocation supersession marker is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != raw:
        fail("the allocation supersession marker is not canonical")
    return account


def exact_current_allocation(args, *, allowed_marker=None, before=None):
    entries = progress.journal_entries()
    if before is not None:
        entries = entries[:before]
    opening_index, opening, built, _ = progress.current_pass_opening(
        entries, len(entries), "the allocation supersession",
    )
    if built != args.built or progress.pass_closes(entries, opening_index, len(entries)):
        fail("the allocation supersession does not own the current open pass")
    current, prior = progress.correction_allocation_lineage(
        entries, opening_index, len(entries), "the allocation supersession",
    )
    if current is None or prior is not None:
        fail("the allocation supersession has no one exact live allocation")
    allocation_index, allocation_entry = current
    if progress.journal_line_proof(allocation_index) != args.allocation:
        fail("the allocation supersession names another allocation")
    allocation = normalize_allocation(progress.note_data(allocation_entry))
    if allocation["round"] != args.round:
        fail("the allocation supersession names another correction round")
    if any((WORKSPACE / name).exists() or (WORKSPACE / name).is_symlink()
           for name in BLOCKING_MARKERS if name != allowed_marker):
        fail("another correction authority owner is unfinished")
    return entries, opening_index, opening, allocation_index, allocation


def derive_account(args, operation, *, allowed_marker=None, before=None):
    entries, opening_index, opening, allocation_index, allocation = exact_current_allocation(
        args, allowed_marker=allowed_marker, before=before,
    )
    opening_data = progress.note_data(opening)
    current = progress.current_product_generation(
        entries, opening_index, len(entries), args.built, "the allocation supersession",
    )
    if args.outcome == "sublot":
        if current != allocation["parent"]:
            fail("the structural supersession changes its reviewed generation")
    elif current == allocation["parent"]:
        fail("reclassify requires one authenticated controller-successor generation")

    confirmed_relative = progress.product_confirmed_path(
        args.built, opening_data["position"], opening_data["pass"],
    )
    allocation_hash = args.allocation.split(":", 1)[1]
    destination_relative = pathlib.PurePosixPath(
        "corrections", args.built,
        f"round-{args.round}-superseded-p{opening_data['pass']}-{allocation_hash}.md",
    )
    confirmed_destination = None
    if args.outcome == "reclassify":
        confirmed_name = pathlib.PurePosixPath(confirmed_relative).name
        stem = confirmed_name.removesuffix(".md")
        confirmed_destination = pathlib.PurePosixPath(
            pathlib.PurePosixPath(confirmed_relative).parent,
            f"{stem}-superseded-{allocation_hash}.md",
        )
    allow_moved = allowed_marker is not None
    if confirmed_destination is None:
        with WorkspaceFileAnchor(
            WORKSPACE, confirmed_relative, "the allocation supersession confirmed artifact",
        ) as confirmed_file:
            confirmed_bytes = confirmed_file.read_regular()
    else:
        confirmed_bytes = frozen_member(
            confirmed_relative, confirmed_destination,
            "the allocation supersession confirmed artifact", allow_moved=allow_moved,
        )
    expected_confirmed = {
        item["id"]: {"sources": item["sources"], "carries": item["carries"]}
        for item in allocation["items"]
    }
    if progress.confirmed_account_bytes(
        confirmed_bytes, "the allocation supersession confirmed artifact",
    ) != expected_confirmed:
        fail("the confirmed artifact changes its allocation")

    source_relative = pathlib.PurePosixPath(
        "corrections", args.built, f"round-{args.round}.md",
    )
    artifact_bytes = frozen_member(
        source_relative, destination_relative, "the allocation supersession artifact",
        allow_moved=allow_moved,
    )
    parser = progress.load_correction_round_parser()
    artifact = parser.parse_artifact_bytes(
        artifact_bytes, expected_built=args.built, expected_round=args.round,
    )
    expected_identity = {
        "parent_generation_sha256": allocation["parent"]["generation_sha256"],
        "source_reviewed_commit": allocation["pass"]["commit"],
        "source_accepted_gate": allocation["pass"]["gate"],
        "correction_base_commit": allocation["parent"]["commit"],
        "correction_base_gate": allocation["parent"]["gate"],
        "source_pass": allocation["pass"]["ordinal"],
        "source_opening": allocation["pass"]["opening"],
    }
    expected_route = {
        "Spec": "current and settled",
        "Human decisions": allocation["admission"]["human_decisions"],
        "Controller contract": allocation["admission"]["controller_contract"],
        "Ownership": allocation["admission"]["ownership"],
        "Decomposition": allocation["admission"]["decomposition"],
        "Coordination": allocation["admission"]["coordination"],
        "Repetition": allocation["admission"]["repetition"],
        "Reason": allocation["admission"]["reason"],
    }
    if artifact["schema"] != 1 or artifact["state"] != "active" \
            or artifact["parent_position"] != f"c{opening_data['position']}" \
            or artifact["identity"] != expected_identity \
            or artifact["source_findings_path"] != str(confirmed_relative) \
            or artifact["source_findings_sha256"] != sha256(confirmed_bytes) \
            or artifact["route"] != expected_route \
            or list(artifact["source_finding_coverage"]) != list(expected_confirmed):
        fail("the Correction Round artifact changes its allocation authority")

    event = {
        "schema": 1,
        "built": args.built,
        "round": args.round,
        "allocation": args.allocation,
        "pass_opening": progress.journal_line_proof(opening_index),
        "parent_generation_sha256": allocation["parent"]["generation_sha256"],
        "current_generation_sha256": current["generation_sha256"],
        "outcome": args.outcome,
        "evidence": (
            "artifact-self-review" if args.outcome == "sublot" else "controller-successor"
        ),
        "reason": args.reason,
        "confirmed_moved_to": (
            str(confirmed_destination) if confirmed_destination is not None else None
        ),
        "artifact_moved_to": str(destination_relative),
    }
    return {
        "schema": 1,
        "operation": operation,
        "event": event,
        "source": str(source_relative),
        "source_sha256": sha256(artifact_bytes),
        "destination": str(destination_relative),
        "confirmed": str(confirmed_relative),
        "confirmed_sha256": sha256(confirmed_bytes),
        "confirmed_destination": (
            str(confirmed_destination) if confirmed_destination is not None else None
        ),
    }


def validate_marker(account, args, operation):
    required = {
        "schema", "operation", "event", "source", "source_sha256", "destination",
        "confirmed", "confirmed_sha256", "confirmed_destination",
    }
    if not isinstance(account, dict) or set(account) != required or account.get("schema") != 1 \
            or account.get("operation") != operation:
        fail("the pending allocation supersession belongs to another operation")
    event = account.get("event")
    if not isinstance(event, dict) or event.get("built") != args.built \
            or event.get("round") != args.round or event.get("allocation") != args.allocation \
            or event.get("outcome") != args.outcome or event.get("reason") != args.reason:
        fail("the pending allocation supersession changes its requested authority")
    for key in ("source_sha256", "confirmed_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(account.get(key))):
            fail("the pending allocation supersession has a malformed content identity")
    entries = progress.journal_entries()
    terminals = [
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "correction.round.allocation.superseded"
        and progress.note_data(entry) == account.get("event")
    ]
    if len(terminals) > 1:
        fail("the pending allocation supersession has duplicate terminals")
    expected = derive_account(
        args, operation, allowed_marker=MARKER_NAME,
        before=terminals[0] if terminals else None,
    )
    if account != expected:
        fail("the pending allocation supersession changed its complete frozen account")
    return expected


def exact_terminal(entries, event):
    matches = [entry for entry in entries
               if entry.get("kind") == "correction.round.allocation.superseded"
               and progress.note_data(entry) == event]
    if len(matches) > 1:
        fail("the allocation supersession terminal is duplicated")
    return bool(matches)


def finish_move(account):
    # Open and validate every parent before the first move. A later member
    # cannot leave an earlier member moved after a component-alias refusal.
    with contextlib.ExitStack() as stack:
        source = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, account["source"], "the allocation supersession source",
        ))
        destination = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, account["destination"], "the allocation supersession destination",
        ))
        source_recovery = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, recovery_relative_path(account["source"]),
            "the allocation supersession source recovery",
        ))
        confirmed = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, account["confirmed"], "the retained confirmed artifact",
        ))
        confirmed_destination_value = account["confirmed_destination"]
        confirmed_destination = None
        confirmed_recovery = None
        if confirmed_destination_value is not None:
            confirmed_destination = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, confirmed_destination_value,
                "the allocation supersession confirmed destination",
            ))
            confirmed_recovery = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, recovery_relative_path(account["confirmed"]),
                "the allocation supersession confirmed recovery",
            ))

        def finish_member(member_source, member_destination, recovery, digest, subject):
            for anchor in (member_source, member_destination, recovery):
                anchor.verify()
            source_status = member_source.status()
            destination_status = member_destination.status()
            recovery_status = recovery.status()
            source_payload = member_source.read_regular() if source_status is not None else None
            destination_payload = member_destination.read_regular() \
                if destination_status is not None else None
            recovery_payload = recovery.read_regular() if recovery_status is not None else None
            if source_payload is not None and sha256(source_payload) != digest:
                fail(f"{subject} source changed after marker publication")
            if destination_payload is not None and sha256(destination_payload) != digest:
                fail(f"{subject} destination changed after marker publication")
            if recovery_payload is not None and sha256(recovery_payload) != digest:
                fail(f"{subject} recovery changed after marker publication")
            if source_status is not None and destination_status is not None:
                fail(f"both source and destination exist for {subject}")
            if source_status is not None:
                member_source.replace_to(member_destination)
            elif destination_status is None:
                if recovery_status is None:
                    fail(f"{subject} has no recoverable frozen artifact")
                recovery.link_to(member_destination)
            if sha256(member_destination.read_regular()) != digest:
                fail(f"{subject} destination changed after its move")

        finish_member(
            source, destination, source_recovery, account["source_sha256"],
            "the allocation supersession",
        )

        confirmed_status = confirmed.status()
        if confirmed_destination_value is None:
            if confirmed_status is None \
                    or sha256(confirmed.read_regular()) != account["confirmed_sha256"]:
                fail("the retained confirmed artifact changed after marker publication")
        else:
            finish_member(
                confirmed, confirmed_destination, confirmed_recovery,
                account["confirmed_sha256"], "the confirmed allocation supersession",
            )


def cleanup_recoveries(account):
    members = [(account["source"], account["source_sha256"])]
    if account["confirmed_destination"] is not None:
        members.append((account["confirmed"], account["confirmed_sha256"]))
    for source, digest in members:
        with WorkspaceFileAnchor(
            WORKSPACE, recovery_relative_path(source),
            "the completed allocation supersession recovery",
        ) as recovery:
            if recovery.status() is not None:
                recovery.remove_exact(digest)


def note_args(event):
    return SimpleNamespace(
        kind="correction.round.allocation.superseded",
        mandate=None,
        task=None,
        round=None,
        text=None,
        text_file=None,
        data=json.dumps(event, separators=(",", ":")),
        mode=None,
        lot=None,
        job=None,
        attempt=None,
    )


def run(args):
    marker = WORKSPACE / MARKER_NAME
    operation = operation_identity(args)
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        if marker.exists() or marker.is_symlink():
            account = validate_marker(read_marker(marker), args, operation)
        else:
            account = derive_account(args, operation)
            atomic_marker(marker, account)

        entries = progress.journal_entries()
        if exact_terminal(entries, account["event"]):
            finish_move(account)
            cleanup_recoveries(account)
            marker.unlink()
            print("SUPERSESSION ALREADY RECORDED")
            return

        exact_current_allocation(args)
        finish_move(account)
        progress.normalize_correction_allocation_supersession(
            progress.journal_entries(), account["event"], "the allocation supersession",
        )
        progress.cmd_note_with_lease(
            note_args(account["event"]), lease, operation, owner_marker=MARKER_NAME,
        )
        cleanup_recoveries(account)
        marker.unlink()
        print(f"SUPERSEDED {args.allocation} -> {args.outcome}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("allocation")
    parser.add_argument("outcome", choices=("sublot", "reclassify"))
    parser.add_argument("reason")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1 \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", args.allocation) \
            or not args.reason or args.reason != args.reason.strip():
        fail("the allocation supersession arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError) as exc:
        print(f"**correction-round-supersede ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
