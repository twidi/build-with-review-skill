#!/usr/bin/env python3
"""Void one live Correction Round allocation under one recoverable owner."""

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

MARKER_NAME = "correction-round-void-in-progress"
BLOCKING_MARKERS = {
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-round-open-in-progress",
    "correction-product-authority-in-progress",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def operation_identity(args):
    return f"correction-amendment-void:{args.built}"


def read_real_file(path, subject):
    try:
        relative = pathlib.Path(path).relative_to(WORKSPACE)
    except ValueError:
        fail(f"{subject} is outside the workspace")
    with WorkspaceFileAnchor(WORKSPACE, relative, subject) as anchored:
        return anchored.read_regular()


def optional_frozen_member(source, destination, subject, *, allow_moved):
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
        if not allow_moved and destination_status is not None:
            fail(f"{subject} destination precedes its owner marker")
        if source_status is not None:
            return source_file.read_regular()
        if allow_moved and destination_status is not None:
            return destination_file.read_regular()
        return None


def atomic_marker(path, account):
    if path.exists() or path.is_symlink():
        fail("another Correction Round void owner is already pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = canonical_bytes(account) + b"\n"
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                fail("the Correction Round void marker had a short write")
            offset += written
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
    raw = read_real_file(path, "the Correction Round void marker")
    try:
        account = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        fail(f"the Correction Round void marker is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != raw:
        fail("the Correction Round void marker is not canonical")
    return account


def exact_current_state(args, *, allowed_marker=None, before=None):
    entries = progress.journal_entries()
    if before is not None:
        entries = entries[:before]
    opening_index, opening, built, _ = progress.current_pass_opening(
        entries, len(entries), "the Correction Round void",
    )
    if built != args.built or progress.pass_closes(entries, opening_index, len(entries)):
        fail("the Correction Round void does not own the current open pass")
    current, prior = progress.correction_allocation_lineage(
        entries, opening_index, len(entries), "the Correction Round void",
    )
    if current is None or prior is not None:
        fail("the Correction Round void has no one exact live allocation")
    amendments = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1,
    ) if entry.get("kind") == "amendment.opened"
        and progress.note_data(entry).get("origin") == "product-review"
        and progress.note_data(entry).get("built") == built]
    if len(amendments) != 1:
        fail("the Correction Round void has no one exact PRODUCT REVIEW AMENDMENT opening")
    amendment_data = progress.note_data(amendments[0][1])
    if amendment_data.get("schema") != 2 \
            or amendment_data.get("pass_opening") != progress.journal_line_proof(opening_index) \
            or amendment_data.get("correction_allocation") != progress.journal_line_proof(current[0]) \
            or amendment_data.get("correction_supersession") is not None:
        fail("the Correction Round void does not own the AMENDMENT's frozen predecessor")
    if any(entry.get("kind") == "sublot.allocated" for entry in entries[opening_index + 1:]):
        fail("the Correction Round void follows an allocated sub-lot")
    if any((WORKSPACE / name).exists() or (WORKSPACE / name).is_symlink()
           for name in BLOCKING_MARKERS if name != allowed_marker):
        fail("another correction authority owner is unfinished")
    return entries, opening_index, opening, current, amendments[0]


def derive_account(args, operation, *, allowed_marker=None, before=None):
    entries, opening_index, opening, current, amendment = exact_current_state(
        args, allowed_marker=allowed_marker, before=before,
    )
    allocation_index, allocation_entry = current
    allocation = normalize_allocation(progress.note_data(allocation_entry))
    opening_data = progress.note_data(opening)
    controller = allocation_entry.get("by")
    if not isinstance(controller, str) or not re.fullmatch(r"[A-Za-z0-9-]+", controller):
        fail("the Correction Round allocation has no path-safe controller identity")

    confirmed = progress.product_confirmed_path(
        args.built, opening_data["position"], opening_data["pass"],
    )
    confirmed_destination = pathlib.PurePosixPath(
        confirmed.parent, f"{confirmed.stem}-superseded-{controller}.md",
    )
    artifact = pathlib.PurePosixPath(
        "corrections", args.built, f"round-{allocation['round']}.md",
    )
    artifact_destination = pathlib.PurePosixPath(
        "corrections", args.built,
        f"round-{allocation['round']}-voided-p{opening_data['pass']}.md",
    )
    allow_moved = allowed_marker is not None
    confirmed_bytes = optional_frozen_member(
        confirmed, confirmed_destination, "the voided confirmed artifact",
        allow_moved=allow_moved,
    )
    artifact_bytes = optional_frozen_member(
        artifact, artifact_destination, "the voided Correction Round artifact",
        allow_moved=allow_moved,
    )
    if artifact_bytes is not None and confirmed_bytes is None:
        fail("the Correction Round artifact has no confirmed source authority")
    if confirmed_bytes is not None:
        expected_confirmed = {
            item["id"]: {"sources": item["sources"], "carries": item["carries"]}
            for item in allocation["items"]
        }
        if progress.confirmed_account_bytes(
            confirmed_bytes, "the voided confirmed artifact",
        ) != expected_confirmed:
            fail("the voided confirmed artifact changes its allocation")
    if artifact_bytes is not None:
        parser = progress.load_correction_round_parser()
        parsed = parser.parse_artifact_bytes(
            artifact_bytes, expected_built=args.built, expected_round=allocation["round"],
        )
        if parsed["source_findings_path"] != str(confirmed) \
                or parsed["source_findings_sha256"] != sha256(confirmed_bytes) \
                or list(parsed["source_finding_coverage"]) != [
                    item["id"] for item in allocation["items"]
                ]:
            fail("the voided Correction Round artifact changes its allocation authority")

    physical = {
        "schema": 1,
        "producer": "correction-round-void",
        "pass_opening": progress.journal_line_proof(opening_index),
        "allocation": progress.journal_line_proof(allocation_index),
        "confirmed": str(confirmed),
        "confirmed_sha256": sha256(confirmed_bytes) if confirmed_bytes is not None else None,
        "confirmed_moved_to": (
            str(confirmed_destination) if confirmed_bytes is not None else None
        ),
        "artifact": str(artifact),
        "artifact_sha256": sha256(artifact_bytes) if artifact_bytes is not None else None,
        "artifact_moved_to": str(artifact_destination) if artifact_bytes is not None else None,
    }
    event = {
        "schema": 2,
        "voided": True,
        "route": "amendment",
        "amendment": progress.journal_line_proof(amendment[0]),
        "correction_allocation": progress.journal_line_proof(allocation_index),
        "correction_supersession": None,
        "correction_void": physical,
    }
    return {"schema": 1, "operation": operation, "event": event}


def validate_marker(account, args, operation):
    if not isinstance(account, dict) or set(account) != {"schema", "operation", "event"} \
            or account.get("schema") != 1 or account.get("operation") != operation:
        fail("the pending Correction Round void belongs to another operation")
    entries = progress.journal_entries()
    terminals = [index for index, entry in enumerate(entries)
                 if entry.get("kind") == "pass.closed"
                 and progress.note_data(entry) == account.get("event")]
    if len(terminals) > 1:
        fail("the pending Correction Round void has duplicate terminals")
    expected = derive_account(
        args, operation, allowed_marker=MARKER_NAME,
        before=terminals[0] if terminals else None,
    )
    if account != expected:
        fail("the pending Correction Round void changed its complete frozen account")
    return expected


def exact_terminal(entries, event):
    matches = [entry for entry in entries if entry.get("kind") == "pass.closed"
               and progress.note_data(entry) == event]
    if len(matches) > 1:
        fail("the Correction Round void terminal is duplicated")
    return bool(matches)


def finish_moves(account):
    physical = account["event"]["correction_void"]
    members = (("confirmed", "confirmed_sha256", "confirmed_moved_to"),
               ("artifact", "artifact_sha256", "artifact_moved_to"))
    with contextlib.ExitStack() as stack:
        anchors = []
        for source_key, digest_key, destination_key in members:
            source = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, physical[source_key], f"the voided {source_key} source",
            ))
            destination_value = physical[destination_key]
            destination = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE,
                destination_value or _absent_destination(physical[source_key], source_key),
                f"the voided {source_key} destination",
            ))
            recovery = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, recovery_relative_path(physical[source_key]),
                f"the voided {source_key} recovery",
            ))
            anchors.append((source, destination, recovery, physical[digest_key], destination_value))
        for source, destination, recovery, digest, destination_value in anchors:
            source.verify()
            destination.verify()
            recovery.verify()
            source_status = source.status()
            destination_status = destination.status()
            recovery_status = recovery.status()
            if digest is None:
                if source_status is not None or destination_status is not None \
                        or recovery_status is not None or destination_value is not None:
                    fail("an absent void member changed after marker publication")
                continue
            source_payload = source.read_regular() if source_status is not None else None
            destination_payload = destination.read_regular() \
                if destination_status is not None else None
            recovery_payload = recovery.read_regular() if recovery_status is not None else None
            if source_payload is not None and sha256(source_payload) != digest:
                fail("a void source changed after marker publication")
            if destination_payload is not None and sha256(destination_payload) != digest:
                fail("a void destination changed after marker publication")
            if recovery_payload is not None and sha256(recovery_payload) != digest:
                fail("a void recovery changed after marker publication")
            if source_status is not None and destination_status is not None:
                fail("both source and destination exist for a void member")
            if source_status is not None:
                source.replace_to(destination)
            elif destination_status is None:
                if recovery_status is None:
                    fail("a void member has no recoverable frozen artifact")
                recovery.link_to(destination)
            if digest is not None and sha256(destination.read_regular()) != digest:
                fail("a void destination changed after its move")


def cleanup_recoveries(account):
    physical = account["event"]["correction_void"]
    for source_key, digest_key in (("confirmed", "confirmed_sha256"),
                                   ("artifact", "artifact_sha256")):
        digest = physical[digest_key]
        if digest is None:
            continue
        with WorkspaceFileAnchor(
            WORKSPACE, recovery_relative_path(physical[source_key]),
            f"the completed voided {source_key} recovery",
        ) as recovery:
            if recovery.status() is not None:
                recovery.remove_exact(digest)


def _absent_destination(source, name):
    path = pathlib.PurePosixPath(source)
    return pathlib.PurePosixPath(path.parent, f".{path.name}.absent-{name}")


def note_args(event):
    return SimpleNamespace(
        kind="pass.closed", mandate=None, task=None, round=None, text=None, text_file=None,
        data=json.dumps(event, separators=(",", ":")), mode=None, lot=None, job=None,
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
            finish_moves(account)
            cleanup_recoveries(account)
            marker.unlink()
            print("CORRECTION ROUND VOID ALREADY RECORDED")
            return

        exact_current_state(args)
        finish_moves(account)
        progress.validate_pass_close(
            progress.journal_entries(), account["event"], "the Correction Round void",
        )
        progress.cmd_note_with_lease(
            note_args(account["event"]), lease, operation, owner_marker=MARKER_NAME,
        )
        cleanup_recoveries(account)
        marker.unlink()
        print(f"VOIDED {args.built}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built):
        fail("the Correction Round void arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError) as exc:
        print(f"**correction-round-void ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
