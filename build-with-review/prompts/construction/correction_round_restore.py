#!/usr/bin/env python3
"""Restore one terminal Correction artifact before its Product successor."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
COMMON = WORKSPACE / "prompts" / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
from correction_authority import CorrectionAuthorityLease, WorkspaceFileAnchor  # noqa: E402

MARKER_NAME = "correction-terminal-restore-in-progress"
BLOCKING_MARKERS = {
    "attempt-in-flight",
    "gate-check-in-progress",
    "amendment-commit-in-progress",
    "document-copy-in-progress",
    "plan-commit-in-progress",
    "spec-commit-in-progress",
    "spec-breach-recovery-in-progress",
    "rewind-in-progress",
    *progress.CORRECTION_PENDING_OWNER_COMMANDS,
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def operation_identity(built, correction):
    payload = f"correction-terminal-restore:{built}:{correction}"
    return "correction-terminal-restore:" + hashlib.sha256(payload.encode()).hexdigest()


def derive_account(built, correction, operation):
    entries = progress.journal_entries()
    authority = progress.correction_terminal_artifact_account(
        entries, len(entries), built, correction,
        "the Correction terminal artifact restoration",
    )
    return {"schema": 1, "operation": operation, "authority": authority}


def ensure_no_foreign_owner():
    for name in sorted(BLOCKING_MARKERS - {MARKER_NAME}):
        if os.path.lexists(WORKSPACE / name):
            fail(f"another workflow owner is unfinished: {name}")


def marker_generation(path):
    with WorkspaceFileAnchor(
        WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
        "the Correction terminal artifact restoration owner",
    ) as marker:
        payload = marker.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the Correction terminal artifact restoration owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the Correction terminal artifact restoration owner is not canonical")
    return payload, account


def publish_marker(path, account):
    payload = canonical_bytes(account) + b"\n"
    with WorkspaceFileAnchor(
        WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
        "the Correction terminal artifact restoration owner",
    ) as marker:
        marker.publish(payload, mode=0o600)
    return payload


def recovery_relative_path(artifact):
    target = pathlib.PurePosixPath(artifact["path"])
    return target.with_name(
        f".{target.name}.correction-terminal-restore-{artifact['sha256']}"
    )


def validate_target(account, *, retained):
    authority = account["authority"]
    artifact = authority["artifact"]
    payload = progress.correction_terminal_artifact_bytes(
        authority, "the Correction terminal artifact restoration preflight",
    )
    target_relative = pathlib.PurePosixPath(artifact["path"])
    recovery_relative = recovery_relative_path(artifact)
    expected_recovery = WORKSPACE.joinpath(*recovery_relative.parts)
    parent = WORKSPACE.joinpath(*target_relative.parent.parts)
    candidates = list(parent.glob(
        f".{target_relative.name}.correction-terminal-restore-*",
    ))
    if any(candidate != expected_recovery for candidate in candidates) \
            or candidates and not retained:
        fail("the Correction terminal artifact has a foreign restoration generation")
    with WorkspaceFileAnchor(
        WORKSPACE, target_relative.as_posix(),
        "the canonical terminal Correction artifact",
    ) as target:
        current = target.status()
        if current is not None and (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or current.st_nlink < 1
        ):
            fail("the canonical terminal Correction artifact is not one real regular file")
        if current is not None:
            target.read_regular()
    if retained and expected_recovery in candidates:
        with WorkspaceFileAnchor(
            WORKSPACE, recovery_relative.as_posix(),
            "the retained terminal Correction artifact restoration generation",
        ) as recovery:
            if recovery.read_regular() != payload:
                fail("the retained terminal artifact restoration bytes changed")


def restore_artifact(account):
    authority = account["authority"]
    artifact = authority["artifact"]
    payload = progress.correction_terminal_artifact_bytes(
        authority, "the Correction terminal artifact restoration",
    )
    target_relative = pathlib.PurePosixPath(artifact["path"])
    recovery_relative = recovery_relative_path(artifact)
    parent = WORKSPACE.joinpath(*target_relative.parent.parts)
    expected_recovery = WORKSPACE.joinpath(*recovery_relative.parts)
    for candidate in parent.glob(f".{target_relative.name}.correction-terminal-restore-*"):
        if candidate != expected_recovery:
            fail("the Correction terminal artifact has a foreign restoration generation")

    with WorkspaceFileAnchor(
        WORKSPACE, target_relative.as_posix(),
        "the canonical terminal Correction artifact",
    ) as target, WorkspaceFileAnchor(
        WORKSPACE, recovery_relative.as_posix(),
        "the terminal Correction artifact restoration generation",
    ) as recovery:
        current_status = target.status()
        if current_status is not None and (
            stat.S_ISLNK(current_status.st_mode)
            or not stat.S_ISREG(current_status.st_mode)
            or current_status.st_nlink < 1
        ):
            fail("the canonical terminal Correction artifact is not one real regular file")
        current = target.read_regular() if current_status is not None else None
        if current == payload:
            recovery_status = recovery.status()
            if recovery_status is not None:
                if recovery.read_regular() != payload:
                    fail("the retained terminal artifact restoration bytes changed")
                recovery.remove_exact(artifact["sha256"])
            return False
        recovery_status = recovery.status()
        if recovery_status is None:
            recovery.publish(payload, mode=0o600)
        elif recovery.read_regular() != payload:
            fail("the retained terminal artifact restoration bytes changed")
        recovery.read_regular()
        recovery.replace_over(target)
        if target.read_regular() != payload:
            fail("the restored terminal Correction artifact changed")
        return True


def remove_marker(path, payload):
    with WorkspaceFileAnchor(
        WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
        "the Correction terminal artifact restoration owner",
    ) as marker:
        current = marker.read_regular()
        if current != payload:
            fail("the Correction terminal artifact restoration owner changed before cleanup")
        marker.remove_exact(hashlib.sha256(payload).hexdigest())


def run(args):
    operation = operation_identity(args.built, args.round)
    marker_path = WORKSPACE / MARKER_NAME
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation):
        expected = derive_account(args.built, args.round, operation)
        if os.path.lexists(marker_path):
            marker_payload, account = marker_generation(marker_path)
            ensure_no_foreign_owner()
            if account != expected:
                fail("the retained artifact restoration changes its terminal authority")
            validate_target(account, retained=True)
        else:
            ensure_no_foreign_owner()
            account = expected
            validate_target(account, retained=False)
            marker_payload = publish_marker(marker_path, account)
        changed = restore_artifact(account)
        progress.require_canonical_correction_terminal_artifact(
            account["authority"], "the completed Correction terminal artifact restoration",
        )
        remove_marker(marker_path, marker_payload)
    state = "RESTORED" if changed else "EXACT"
    print(f"CORRECTION ARTIFACT {state} {args.built} {args.round}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1:
        print("**correction restore ERROR** · malformed Correction Round identity", file=sys.stderr)
        raise SystemExit(1)
    try:
        run(args)
    except (OSError, ValueError) as exc:
        print(f"**correction restore ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
