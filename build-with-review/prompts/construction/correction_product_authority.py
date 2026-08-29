#!/usr/bin/env python3
"""Own one in-pass product-authority tail over an unopened Correction Round."""

import argparse
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
import correction_round_supersede as supersede  # noqa: E402
from correction_authority import CorrectionAuthorityLease  # noqa: E402

MARKER_NAME = "correction-product-authority-in-progress"
STATE_KINDS = {
    "ruling.ready",
    "decision.batch.ready",
    "decision.batch.supplemented",
    "decision.conflict.ready",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def operation_identity(args):
    return (
        f"correction-product-authority:{args.built}:{args.round}:"
        f"{args.allocation}:{args.owner}:{args.state_kind}:{args.state_ref}:{args.ready_op}"
    )


def refuse_competing_owner_markers():
    for name in supersede.BLOCKING_MARKERS:
        if name == MARKER_NAME:
            continue
        marker = WORKSPACE / name
        if marker.exists() or marker.is_symlink():
            fail("another correction authority owner is unfinished")


def atomic_write(path, account, *, replace):
    if not replace and (path.exists() or path.is_symlink()):
        fail("another product-authority owner is already pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the product-authority marker had a short write")
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
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        fail(f"the product-authority marker is unreadable: {exc}")
    if path.is_symlink() or not path.is_file() or metadata.st_nlink < 1:
        fail("the product-authority marker is not one real regular file")
    try:
        account = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        fail(f"the product-authority marker is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != raw:
        fail("the product-authority marker is not canonical")
    return account


def remove_marker(path):
    path.unlink()
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def state_matches(entry, kind, ref):
    data = progress.note_data(entry)
    if entry.get("kind") != kind:
        return False
    if kind == "ruling.ready":
        return data.get("ruling") == ref
    if kind == "decision.batch.ready":
        match = re.fullmatch(r"B([1-9][0-9]*)", ref)
        return match is not None and data.get("batch") == int(match.group(1))
    if kind == "decision.batch.supplemented":
        return data.get("after_op") == ref
    if kind == "decision.recheck.completed":
        return data.get("commit_op") == ref or data.get("basis_ref") == ref
    if kind == "decision.conflict.ready":
        match = re.fullmatch(r"(R[1-9][0-9]*|B[1-9][0-9]*)/C([1-9][0-9]*)", ref)
        return match is not None and data.get("owner") == match.group(1) \
            and data.get("conflict") == int(match.group(2))
    return False


def exact_state(entries, args):
    matches = [(index, entry) for index, entry in enumerate(entries)
               if state_matches(entry, args.state_kind, args.state_ref)]
    if len(matches) != 1:
        fail("the product-authority owner has no one exact current state generation")
    index, entry = matches[0]
    artifact_sha256 = progress.authority_artifact_sha(
        entry, "the product-authority state",
    )
    return index, artifact_sha256


def exact_owed_route(entries, args, state_index, artifact_sha256):
    if args.owner.startswith("R"):
        _, route, authority = progress.direct_ruling_state(args.owner)
        expected = {
            "authority_kind": args.state_kind,
            "authority_ref": args.state_ref,
            "authority_sha256": artifact_sha256,
        }
        if authority != expected:
            fail("the product-authority owner does not name the current ruling generation")
    else:
        batch_text, decision = args.owner.split("/", 1)
        state = progress.batch_state(entries, int(batch_text[1:]))
        answer = state["answers"].get(decision)
        if answer is None or answer.get("status") != "active" \
                or state.get("generation_kind") != args.state_kind \
                or state.get("generation_ref") != args.state_ref \
                or state_index != answer.get("state_index"):
            fail("the product-authority owner does not name the current batch generation")
        route = answer.get("route")
    if route != "spec-in-place":
        fail("the current product authority owes no multi-step spec transition")


def initial_account(args, operation, *, before=None):
    entries, opening_index, _, _, allocation = supersede.exact_current_allocation(
        args, before=before, allowed_marker=MARKER_NAME,
    )
    current = progress.current_product_generation(
        entries, opening_index, len(entries), args.built, "the product-authority owner",
    )
    if current != allocation["parent"]:
        fail("the product-authority owner starts after the allocation base changed")
    state_index, artifact_sha256 = exact_state(entries, args)
    owner = progress.whoami().get("session_id")
    if not isinstance(owner, str) or not owner:
        fail("the product-authority owner has no controller session")
    account = {
        "schema": 1,
        "phase": "authority",
        "operation": operation,
        "owner_session": owner,
        "built": args.built,
        "round": args.round,
        "allocation": args.allocation,
        "authority_owner": args.owner,
        "pass_opening": progress.journal_line_proof(opening_index),
        "parent_generation_sha256": allocation["parent"]["generation_sha256"],
        "parent_commit": allocation["parent"]["commit"],
        "parent_gate": allocation["parent"]["gate"],
        "state_kind": args.state_kind,
        "state_ref": args.state_ref,
        "state_proof": progress.journal_line_proof(state_index),
        "state_artifact_sha256": artifact_sha256,
        "ready_op": args.ready_op,
        "reason": None,
        "supersession": None,
    }
    return account, entries, state_index, artifact_sha256


def begin_account(args, operation):
    account, entries, state_index, artifact_sha256 = initial_account(args, operation)
    exact_owed_route(entries, args, state_index, artifact_sha256)
    return account


def validate_marker(account, args, operation):
    required = {
        "schema", "phase", "operation", "owner_session", "built", "round",
        "allocation", "authority_owner", "pass_opening", "parent_generation_sha256", "parent_commit",
        "parent_gate", "state_kind", "state_ref", "state_proof",
        "state_artifact_sha256", "ready_op", "reason", "supersession",
    }
    if not isinstance(account, dict) or set(account) != required \
            or account.get("schema") != 1 or account.get("operation") != operation \
            or account.get("built") != args.built or account.get("round") != args.round \
            or account.get("allocation") != args.allocation \
            or account.get("authority_owner") != args.owner \
            or account.get("state_kind") != args.state_kind \
            or account.get("state_ref") != args.state_ref \
            or account.get("ready_op") != args.ready_op:
        fail("the pending product authority belongs to another operation")
    if account.get("owner_session") != progress.whoami().get("session_id"):
        fail("the pending product authority belongs to another controller session")
    if account.get("phase") not in {"authority", "supersede"}:
        fail("the pending product authority has an unknown phase")
    if account["phase"] == "authority" and (
        account.get("reason") is not None or account.get("supersession") is not None
    ):
        fail("the pending product authority changes its unfinished authority phase")
    state_index = int(account["state_proof"].split(":", 1)[0])
    expected, _, _, _ = initial_account(args, operation, before=state_index + 1)
    frozen_keys = required - {"phase", "reason", "supersession"}
    if any(account.get(key) != expected.get(key) for key in frozen_keys):
        fail("the pending product authority changes its frozen initial account")
    return account


def exact_ready(entries, account):
    matches = [(index, entry) for index, entry in enumerate(entries)
               if entry.get("kind") == "spec.edit.ready"
               and progress.note_data(entry).get("op") == account["ready_op"]
               and progress.note_data(entry).get("owner") == account["authority_owner"]
               and progress.note_data(entry).get("state_kind") == account["state_kind"]
               and progress.note_data(entry).get("state_ref") == account["state_ref"]
               and entry.get("by") == account["owner_session"]]
    if len(matches) != 1:
        fail("the product-authority owner has no one exact ready boundary")
    return matches[0][0]


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


def run_begin(args, marker, operation):
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation):
        refuse_competing_owner_markers()
        if marker.exists() or marker.is_symlink():
            validate_marker(read_marker(marker), args, operation)
            print("PRODUCT AUTHORITY ALREADY OWNED")
            return
        account = begin_account(args, operation)
        atomic_write(marker, account, replace=False)
        print(f"PRODUCT AUTHORITY OWNED {args.state_kind} {args.state_ref}")


def run_finish(args, marker, operation):
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        account = validate_marker(read_marker(marker), args, operation)
        if account["phase"] == "authority":
            entries = progress.journal_entries()
            owned_chain = progress.product_authority_chain(
                entries, account, len(entries), "the completed product-authority owner",
            )
            ready_index = exact_ready(entries, account)
            successor_result = progress.in_pass_controller_successor(
                entries,
                int(account["pass_opening"].split(":", 1)[0]),
                len(entries),
                args.built,
                "the completed product-authority owner",
            )
            if successor_result is None:
                fail("the product-authority owner has no completed successor generation")
            successor, _ = successor_result
            if successor["authorities"] != owned_chain:
                fail("the product-authority successor omits or changes its complete owned chain")
            if progress.journal_line_proof(ready_index) not in successor["authorities"]:
                fail("the product-authority successor belongs to another ready boundary")
            supersede_args = SimpleNamespace(
                built=args.built,
                round=args.round,
                allocation=args.allocation,
                outcome="reclassify",
                reason=args.reason,
            )
            supersession = supersede.derive_account(
                supersede_args, operation, allowed_marker=MARKER_NAME,
            )
            account = {
                **account,
                "phase": "supersede",
                "reason": args.reason,
                "supersession": supersession,
            }
            atomic_write(marker, account, replace=True)
        elif account.get("reason") != args.reason:
            fail("the pending product authority has another supersession reason")

        supersession = account["supersession"]
        event = supersession["event"]
        entries = progress.journal_entries()
        terminal_indices = [
            index for index, entry in enumerate(entries)
            if entry.get("kind") == "correction.round.allocation.superseded"
            and progress.note_data(entry) == event
        ]
        if len(terminal_indices) > 1:
            fail("the product-authority supersession terminal is duplicated")
        expected_supersession = supersede.derive_account(
            SimpleNamespace(
                built=args.built, round=args.round, allocation=args.allocation,
                outcome="reclassify", reason=args.reason,
            ),
            operation, allowed_marker=MARKER_NAME,
            before=terminal_indices[0] if terminal_indices else None,
        )
        if supersession != expected_supersession:
            fail("the product-authority marker changes its frozen supersession account")
        if supersede.exact_terminal(entries, event):
            supersede.finish_move(supersession)
            remove_marker(marker)
            print("PRODUCT AUTHORITY RECLASSIFICATION ALREADY RECORDED")
            return

        supersede_args = SimpleNamespace(
            built=args.built,
            round=args.round,
            allocation=args.allocation,
            outcome="reclassify",
            reason=args.reason,
        )
        supersede.exact_current_allocation(
            supersede_args, allowed_marker=MARKER_NAME,
        )
        supersede.finish_move(supersession)
        progress.normalize_correction_allocation_supersession(
            progress.journal_entries(), event, "the product-authority supersession",
        )
        progress.cmd_note_with_lease(
            note_args(event), lease, operation, owner_marker=MARKER_NAME,
        )
        remove_marker(marker)
        print(f"PRODUCT AUTHORITY RECLASSIFIED {args.allocation}")


def release_terminal(entries, account, proof):
    index, entry = progress.journal_entry_from_proof(
        entries, proof, "the product-authority release terminal",
    )
    if index <= int(account["state_proof"].split(":", 1)[0]):
        fail("the product-authority release terminal predates its owner")
    data = progress.note_data(entry)
    owner = account["authority_owner"]
    if entry.get("kind") == "ruling.applied":
        if owner.startswith("R"):
            matches = data.get("ruling") == owner
        else:
            batch, decision = owner.split("/", 1)
            matches = data.get("batch") == int(batch[1:]) and data.get("decision") == decision
        if not matches or data.get("route") != "closed":
            fail("the product-authority release terminal does not close its exact owner")
    elif entry.get("kind") == "decision.conflict.ready":
        if owner.startswith("R"):
            current = progress.direct_ruling_state(owner)[1]
        else:
            batch, decision = owner.split("/", 1)
            answer = progress.batch_state(entries, int(batch[1:]))["answers"].get(decision)
            current = answer.get("route") if answer and answer.get("status") == "active" else None
        if current in {None, "spec-in-place"}:
            fail("the product-authority conflict terminal does not abandon its spec transition")
    else:
        fail("the product-authority release has no exact failure or abandonment terminal")
    return index


def run_release(args, marker, operation):
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation):
        account = validate_marker(read_marker(marker), args, operation)
        if account["phase"] != "authority":
            fail("a supersession-phase product authority cannot be released")
        entries, opening_index, _, _, allocation = supersede.exact_current_allocation(
            args, allowed_marker=MARKER_NAME,
        )
        terminal_index = release_terminal(entries, account, args.terminal)
        owned_chain = progress.product_authority_chain(
            entries, account, len(entries), "the released product-authority owner",
        )
        if not owned_chain or owned_chain[-1] != progress.journal_line_proof(terminal_index):
            fail("the release terminal does not close the complete owned authority chain")
        if any(entry.get("kind") == "spec.committed"
               and progress.note_data(entry).get("ready_op") == account["ready_op"]
               for entry in entries):
            fail("a committed product authority must finish reclassification")
        current = progress.current_product_generation(
            entries, opening_index, len(entries), args.built,
            "the released product-authority owner",
        )
        if current != allocation["parent"]:
            fail("the released product authority changed the correction base")
        remove_marker(marker)
        print(f"PRODUCT AUTHORITY RELEASED {args.terminal}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("begin", "finish", "release"))
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("allocation")
    parser.add_argument("owner")
    parser.add_argument("state_kind")
    parser.add_argument("state_ref")
    parser.add_argument("ready_op")
    parser.add_argument("detail", nargs="?")
    args = parser.parse_args()
    args.reason = args.detail if args.action == "finish" else None
    args.terminal = args.detail if args.action == "release" else None
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1 \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", args.allocation) \
            or not re.fullmatch(r"(?:R[1-9][0-9]*|B[1-9][0-9]*/D[1-9][0-9]*)", args.owner) \
            or args.state_kind not in STATE_KINDS \
            or not re.fullmatch(r"[A-Za-z0-9._:/-]+", args.state_ref) \
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", args.ready_op) \
            or args.action == "begin" and args.detail is not None \
            or args.action == "finish" and (
                not args.reason or args.reason != args.reason.strip()
            ) or args.action == "release" and not re.fullmatch(
                r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(args.terminal),
            ):
        fail("the product-authority owner arguments are malformed")
    return args


def main():
    try:
        args = parse_args()
        marker = WORKSPACE / MARKER_NAME
        operation = operation_identity(args)
        if args.action == "begin":
            run_begin(args, marker, operation)
        elif args.action == "finish":
            run_finish(args, marker, operation)
        else:
            run_release(args, marker, operation)
    except (OSError, ValueError) as exc:
        print(f"**correction-product-authority ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
