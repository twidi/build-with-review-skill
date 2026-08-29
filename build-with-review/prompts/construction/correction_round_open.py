#!/usr/bin/env python3
"""Open one frozen Correction Round under one correction-authority lease."""

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import subprocess
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
)

MARKER_NAME = "correction-round-open-in-progress"
BLOCKING_MARKERS = {
    "attempt-in-flight",
    "gate-check-in-progress",
    "amendment-commit-in-progress",
    "document-copy-in-progress",
    "plan-commit-in-progress",
    "spec-commit-in-progress",
    "spec-breach-recovery-in-progress",
    "rewind-in-progress",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-round-void-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
    "correction-round-revision-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-rewind-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
    "correction-round-escalation-in-progress",
}
TERMINALS = {
    "correction.round.built",
    "correction.round.resolved",
    "correction.round.escalated",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def operation_identity(args, pass_close):
    payload = f"correction-open:{args.built}:{args.round}:{pass_close}"
    return f"correction-open:{hashlib.sha256(payload.encode()).hexdigest()}"


def read_marker(path):
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the Correction Round opening marker is malformed: {exc}")
    if path.is_symlink() or not path.is_file() or metadata.st_nlink < 1 \
            or canonical_bytes(value) + b"\n" != raw:
        fail("the Correction Round opening marker is not one canonical real file")
    return value


def atomic_marker(path, account):
    if path.exists() or path.is_symlink():
        fail("another Correction Round opening owner is already pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the Correction Round opening marker had a short write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def raw_close(args):
    entries = progress.journal_entries()
    opening_index, _, built, _ = progress.current_pass_opening(
        entries, len(entries), "the Correction Round opening",
    )
    closes = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1,
    ) if entry.get("kind") == "pass.closed"]
    if len(closes) != 1:
        fail("the Correction Round opening has no one exact pass close")
    close_index, close = closes[0]
    data = progress.note_data(close)
    confirmed = data.get("confirmed")
    if built != args.built or not isinstance(confirmed, int) or confirmed < 1 \
            or data.get("schema") != 2 \
            or data.get("route") != "correction":
        fail("the Correction Round opening has no exact positive correction close")
    allocation_index, allocation_entry = progress.journal_entry_from_proof(
        entries, data["allocation"], "the Correction Round opening allocation",
    )
    if allocation_index >= close_index \
            or allocation_entry.get("kind") != "correction.round.allocated":
        fail("the Correction Round opening has no exact preceding allocation")
    allocation = normalize_allocation(progress.note_data(allocation_entry))
    if allocation["round"] != args.round:
        fail("the Correction Round opening names another round")
    progress.validate_correction_opening_batch_tails(
        entries, close_index, data, allocation, "the Correction Round opening",
    )
    event = {
        "schema": 1,
        "built": built,
        "round": args.round,
        "parent_generation_sha256": data["base_generation_sha256"],
        "allocation": data["allocation"],
        "pass_close": progress.journal_line_proof(close_index),
        "artifact": data["artifact"],
        "artifact_sha256": data["artifact_sha256"],
        "artifact_object": data["artifact_object"],
        "controller_sha256": data["controller_sha256"],
        "manifest_sha256": data["manifest_sha256"],
        "tasks": data["tasks"],
        "base_commit": data["base_commit"],
    }
    restores = [
        {
            "target": data["confirmed_artifact"],
            "object": data["confirmed_object"],
            "sha256": data["confirmed_sha256"],
        },
        {
            "target": data["artifact"],
            "object": data["artifact_object"],
            "sha256": data["artifact_sha256"],
        },
    ]
    return entries, event, restores


def current_close(args):
    entries, event, _ = raw_close(args)
    _, _, _, close, _, _ = progress.current_pass_close(
        entries, "the Correction Round opening",
    )
    if progress.note_data(close)["base_commit"] != event["base_commit"]:
        fail("the Correction Round opening changes its validated close")
    return entries, event


def ref_name(args):
    return f"refs/bwr/{WORKSPACE.name}/{args.built}/correction-{args.round}/task-0"


def inspect_refs(args, base_commit):
    prefix = f"refs/bwr/{WORKSPACE.name}/{args.built}/correction-{args.round}/"
    result = subprocess.run(
        ["git", "-C", progress.project_root(), "for-each-ref", "--format=%(refname) %(objectname)",
         prefix],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail("the Correction Round ref namespace is unreadable")
    expected = ref_name(args)
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if any(len(row) != 2 or row[0] != expected or row[1] != base_commit for row in rows) \
            or len(rows) > 1:
        fail("the Correction Round ref namespace contains a foreign tail")
    return bool(rows)


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def validate_restore_pair(restore, *, create_target_parents=False):
    with contextlib.ExitStack() as stack:
        source = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, restore["object"], "the immutable Correction Round authority object",
        ))
        target = stack.enter_context(WorkspaceFileAnchor(
            WORKSPACE, restore["target"], "the canonical Correction Round artifact",
            create_parents=create_target_parents,
        ))
        source_status = source.status()
        if source_status is None or source_status.st_nlink != 1 \
                or source_status.st_mode & 0o222:
            fail("the Correction Round opening has no exact immutable authority object")
        payload = source.read_regular()
        if hashlib.sha256(payload).hexdigest() != restore["sha256"]:
            fail("the immutable Correction Round authority object changed")
        target_status = target.status()
        if target_status is not None \
                and hashlib.sha256(target.read_regular()).hexdigest() != restore["sha256"]:
            fail("the canonical Correction Round artifact contains foreign bytes")
        return payload


def derive_account(args, operation):
    entries, event, restores = raw_close(args)
    matches = [entry for entry in entries if entry.get("kind") == "correction.round.opened"
               and progress.note_data(entry).get("built") == args.built
               and progress.note_data(entry).get("round") == args.round]
    if len(matches) > 1 or matches and progress.note_data(matches[0]) != event:
        fail("the Correction Round opening has a foreign or duplicate terminal")
    if any(entry.get("kind") in TERMINALS
           and progress.note_data(entry).get("built") == args.built
           and progress.note_data(entry).get("round") == args.round
           for entry in entries):
        fail("the Correction Round already has a terminal")
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or head.stdout.strip() != event["base_commit"]:
        fail("HEAD is not the exact frozen correction base")
    inspect_refs(args, event["base_commit"])
    for restore in restores:
        validate_restore_pair(restore)
    return {
        "schema": 1,
        "operation": operation,
        "event": event,
        "ref": ref_name(args),
        "base_commit": event["base_commit"],
        "restores": restores,
    }


def validate_marker(account, args, operation):
    required = {"schema", "operation", "event", "ref", "base_commit", "restores"}
    if not isinstance(account, dict) or set(account) != required \
            or account.get("schema") != 1 or account.get("operation") != operation \
            or account.get("ref") != ref_name(args):
        fail("the pending Correction Round opening belongs to another operation")
    expected = derive_account(args, operation)
    if account != expected:
        fail("the pending Correction Round opening changes its frozen close")
    return expected


def restore_artifacts(account):
    with contextlib.ExitStack() as stack:
        prepared = []
        for restore in account["restores"]:
            source = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, restore["object"],
                "the immutable Correction Round authority object",
            ))
            target = stack.enter_context(WorkspaceFileAnchor(
                WORKSPACE, restore["target"], "the canonical Correction Round artifact",
                create_parents=True,
            ))
            source_status = source.status()
            if source_status is None or source_status.st_nlink != 1 \
                    or source_status.st_mode & 0o222:
                fail("the immutable Correction Round authority object is unavailable")
            payload = source.read_regular()
            if hashlib.sha256(payload).hexdigest() != restore["sha256"]:
                fail("the immutable Correction Round authority object changed")
            target_status = target.status()
            if target_status is not None \
                    and hashlib.sha256(target.read_regular()).hexdigest() != restore["sha256"]:
                fail("the canonical Correction Round artifact contains foreign bytes")
            prepared.append((target, payload, target_status is not None))
        for target, payload, exists in prepared:
            if not exists:
                target.publish(payload)


def publish_ref(account):
    args = SimpleNamespace(
        built=account["event"]["built"], round=account["event"]["round"],
    )
    if inspect_refs(args, account["base_commit"]):
        return
    result = subprocess.run([
        "git", "-C", progress.project_root(), "update-ref",
        account["ref"], account["base_commit"], "0" * 40,
    ], capture_output=True, text=True)
    if result.returncode != 0:
        fail("the Correction Round task-0 ref could not be published")


def note_args(event):
    return SimpleNamespace(
        kind="correction.round.opened",
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
    entries, event, _ = raw_close(args)
    operation = operation_identity(args, event["pass_close"])
    existing = [entry for entry in entries if entry.get("kind") == "correction.round.opened"
                and progress.note_data(entry) == event]
    marker = WORKSPACE / MARKER_NAME
    if len(existing) == 1 and not marker.exists() and not marker.is_symlink():
        if not inspect_refs(args, event["base_commit"]):
            fail("the recorded Correction Round opening has no task-0 ref")
        progress.normalize_correction_round_opening(
            entries[:entries.index(existing[0])], event,
            "the recorded Correction Round opening", historical=True,
        )
        print("CORRECTION ROUND ALREADY OPEN")
        return
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        if marker.exists() or marker.is_symlink():
            account = validate_marker(read_marker(marker), args, operation)
        else:
            ensure_no_foreign_owner()
            account = derive_account(args, operation)
            atomic_marker(marker, account)
        restore_artifacts(account)
        _, validated_event = current_close(args)
        if validated_event != account["event"]:
            fail("the restored Correction Round authority changes its opening")
        publish_ref(account)
        entries = progress.journal_entries()
        terminals = [entry for entry in entries
                     if entry.get("kind") == "correction.round.opened"
                     and progress.note_data(entry) == account["event"]]
        if len(terminals) > 1:
            fail("the Correction Round opening terminal is duplicated")
        if not terminals:
            progress.normalize_correction_round_opening(
                entries, account["event"], "the Correction Round opening",
            )
            progress.cmd_note_with_lease(
                note_args(account["event"]), lease, operation, owner_marker=MARKER_NAME,
            )
        marker.unlink()
        print(f"CORRECTION ROUND OPEN {args.built} {args.round}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1:
        fail("the Correction Round opening arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError) as exc:
        print(f"**correction-round-open ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
