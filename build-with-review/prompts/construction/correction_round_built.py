#!/usr/bin/env python3
"""Close one fully accepted Correction Round generation."""

import argparse
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
    publish_content_object,
)
from work_unit import resolve_correction  # noqa: E402

MARKER_NAME = "correction-round-built-in-progress"
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
    "correction-round-open-in-progress",
    "correction-round-void-in-progress",
    "correction-round-revision-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-rewind-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "final-checker-contract-map-in-progress",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def operation_identity(built, correction):
    payload = f"correction-built:{built}:{correction}"
    return f"correction-built:{hashlib.sha256(payload.encode()).hexdigest()}"


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def atomic_marker(path, account):
    if path.exists() or path.is_symlink():
        fail("another Correction Round completion owner is already pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the Correction Round completion marker had a short write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def read_marker(path):
    try:
        status = path.lstat()
        payload = path.read_bytes()
        account = json.loads(payload)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the Correction Round completion marker is malformed: {exc}")
    if path.is_symlink() or not path.is_file() or status.st_nlink < 1 \
            or canonical_bytes(account) + b"\n" != payload:
        fail("the Correction Round completion marker is not one canonical real file")
    return account


def publish_final_artifact(built, correction):
    resolved = resolve_correction(built, correction)
    artifact_path = WORKSPACE / resolved["workspace_document"]
    try:
        payload = artifact_path.read_bytes()
    except OSError as exc:
        fail(f"the final correction artifact is unreadable: {exc}")
    published = publish_content_object(WORKSPACE, built, payload, ".md")
    return str(published.relative_to(WORKSPACE))


def derive_account(built, correction, operation):
    entries = progress.journal_entries()
    event = progress.correction_round_built_account(
        entries, len(entries), built, correction, "the Correction Round completion",
    )
    return {"schema": 1, "operation": operation, "event": event}


def note_args(event):
    return SimpleNamespace(
        kind="correction.round.built",
        mandate=None,
        task=None,
        round=None,
        text=None,
        text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None,
        lot=None,
        job=None,
        attempt=None,
    )


def run(args):
    operation = operation_identity(args.built, args.round)
    marker = WORKSPACE / MARKER_NAME
    entries = progress.journal_entries()
    existing = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == "correction.round.built"
        and progress.note_data(entry).get("built") == args.built
        and progress.note_data(entry).get("round") == args.round
    ]
    if len(existing) > 1:
        fail("the Correction Round has duplicate built terminals")
    if existing and not marker.exists() and not marker.is_symlink():
        progress.validate_correction_round_built_entry(
            entries, existing[0][0], existing[0][1],
        )
        print("CORRECTION ROUND BUILT (already recorded)")
        return

    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        current_entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            current_entries, len(current_entries), args.built, args.round,
            "the Correction Round completion",
        )
        if marker.exists() or marker.is_symlink():
            account = read_marker(marker)
            current_entries = progress.journal_entries()
            recorded = [
                (index, entry) for index, entry in enumerate(current_entries)
                if entry.get("kind") == "correction.round.built"
                and progress.note_data(entry).get("built") == args.built
                and progress.note_data(entry).get("round") == args.round
            ]
            if recorded:
                if len(recorded) != 1 or progress.note_data(recorded[0][1]) != account.get("event"):
                    fail("the pending Correction Round completion disagrees with its terminal")
                progress.validate_correction_round_built_entry(
                    current_entries, recorded[0][0], recorded[0][1],
                )
                marker.unlink()
                print("CORRECTION ROUND BUILT (already recorded)")
                return
            expected = derive_account(args.built, args.round, operation)
            if account != expected:
                fail("the pending Correction Round completion changes its generation")
        else:
            ensure_no_foreign_owner()
            repository = progress.project_root()
            if subprocess.run(
                ["git", "-C", repository, "status", "--porcelain"],
                capture_output=True, text=True,
            ).stdout:
                fail("the Correction Round completion requires one clean tree")
            publish_final_artifact(args.built, args.round)
            account = derive_account(args.built, args.round, operation)
            head = subprocess.run(
                ["git", "-C", repository, "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            if head != account["event"]["commit"]:
                fail("HEAD is not the final stable correction task commit")
            atomic_marker(marker, account)

        entries = progress.journal_entries()
        terminals = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "correction.round.built"
            and progress.note_data(entry).get("built") == args.built
            and progress.note_data(entry).get("round") == args.round
        ]
        if len(terminals) > 1:
            fail("the Correction Round has duplicate built terminals")
        if terminals:
            if progress.note_data(terminals[0][1]) != account["event"]:
                fail("the recorded Correction Round terminal changes its generation")
            progress.validate_correction_round_built_entry(
                entries, terminals[0][0], terminals[0][1],
            )
        else:
            progress.normalize_correction_round_built(
                entries, account["event"], "the Correction Round completion",
            )
            progress.cmd_note_with_lease(
                note_args(account["event"]), lease, operation, owner_marker=MARKER_NAME,
            )
        marker.unlink()
        print(f"CORRECTION ROUND BUILT {args.built} {args.round}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1:
        print("**correction built ERROR** · malformed Correction Round identity", file=sys.stderr)
        raise SystemExit(1)
    try:
        run(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"**correction built ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
