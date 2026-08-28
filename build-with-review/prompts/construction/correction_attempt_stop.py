#!/usr/bin/env python3
"""Preserve and stop one active Correction Round task attempt."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
COMMON = HERE.parent / "common"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(HERE))

import correction_attempt_failure as failure  # noqa: E402
import progress  # noqa: E402
from correction_authority import CorrectionAuthorityLease, WorkspaceFileAnchor  # noqa: E402
from work_unit import resolve_correction  # noqa: E402

MARKER_NAME = "correction-attempt-stop-in-progress"
BLOCKING_MARKERS = failure.BLOCKING_MARKERS | {
    "correction-attempt-failure-in-progress",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def git_output(*args):
    return failure.git_output(*args)


def normalize_spares(values):
    roots = []
    for value in values:
        path = pathlib.Path(value)
        if path.is_absolute():
            try:
                relative = path.relative_to(REPO)
            except ValueError:
                fail(f"the spared path is outside the repository: {value}")
        else:
            relative = path
        normalized = pathlib.PurePosixPath(os.path.normpath(relative.as_posix()))
        if not normalized.parts or normalized.is_absolute() \
                or any(part in {"", ".", ".."} for part in normalized.parts) \
                or normalized.parts[0] == ".git" \
                or normalized.parts[:2] == (".superpowers", "bwr"):
            fail(f"the spared path is not one safe repository-relative path: {value}")
        text = normalized.as_posix()
        if text in roots:
            fail(f"the spared path is duplicated: {text}")
        roots.append(text)
    roots.sort()
    for index, path in enumerate(roots):
        if any(path == parent or path.startswith(f"{parent}/") for parent in roots[:index]):
            fail(f"the spared paths overlap: {path}")
    return roots


def spare_manifest(roots):
    manifest = []

    def visit(relative):
        path = REPO / relative
        try:
            status = path.lstat()
        except FileNotFoundError:
            fail(f"the spared path does not exist: {relative}")
        mode = stat.S_IMODE(status.st_mode)
        if stat.S_ISDIR(status.st_mode):
            manifest.append({"path": relative, "kind": "directory", "mode": mode})
            with os.scandir(path) as members:
                names = sorted(member.name for member in members)
            for name in names:
                visit(f"{relative}/{name}")
        elif stat.S_ISREG(status.st_mode):
            payload = path.read_bytes()
            manifest.append({
                "path": relative, "kind": "file", "mode": mode,
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        elif stat.S_ISLNK(status.st_mode):
            target = os.readlink(path).encode()
            manifest.append({
                "path": relative, "kind": "symlink", "mode": mode,
                "sha256": hashlib.sha256(target).hexdigest(),
            })
        else:
            fail(f"the spared path has an unsupported file type: {relative}")

    for root in roots:
        visit(root)
    return manifest


def candidate_with_spares(feature, args, base_commit, roots):
    head = git_output("rev-parse", "HEAD")
    snapshot_tree = failure.temporary_index_tree()
    head_tree = git_output("rev-parse", f"{head}^{{tree}}")
    if snapshot_tree == head_tree:
        snapshot_commit = head
    else:
        snapshot_commit = failure.run(
            "git", "-C", str(REPO), "commit-tree", snapshot_tree, "-p", head,
            input_text=(
                f"{feature} {args.built} correction task {args.task} attempt "
                f"{args.attempt} — SPARED INPUTS\n"
            ),
        ).stdout.strip()
    candidate_tree = failure.temporary_index_tree(roots)
    if roots:
        candidate = failure.run(
            "git", "-C", str(REPO), "commit-tree", candidate_tree, "-p", snapshot_commit,
            input_text=(
                f"{feature} {args.built} correction task {args.task} attempt "
                f"{args.attempt} — {args.kind.upper()}\n"
            ),
        ).stdout.strip()
    else:
        candidate = failure.candidate_account(
            feature, args.built, args.task, args.attempt, base_commit,
        )["candidate_commit"]
    return {
        "input_head": head,
        "candidate_commit": candidate,
        "candidate_tree": candidate_tree,
        "spare_snapshot_commit": snapshot_commit if roots else None,
        "spare_snapshot_tree": snapshot_tree if roots else None,
        "spare_manifest": spare_manifest(roots),
    }


def note_args(event, task, kind):
    return SimpleNamespace(
        kind=kind, mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def operation_identity(args, event):
    event_identity = {
        **event, "preserved_ref": None, "spare_snapshot": None,
    }
    payload = {
        "kind": args.kind, "built": args.built, "round": args.round,
        "task": args.task, "attempt": args.attempt,
        "spares": normalize_spares(args.spares),
        "event": event_identity,
    }
    return "correction-attempt-stop:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def publish_marker(account):
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction attempt stop owner",
    ) as anchored:
        anchored.publish(canonical_bytes(account) + b"\n")


def read_marker():
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction attempt stop owner",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the correction attempt stop owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the correction attempt stop owner is not canonical")
    return payload, account


def remove_exact(relative, payload, subject):
    with WorkspaceFileAnchor(WORKSPACE, relative, subject) as anchored:
        anchored.remove_exact(hashlib.sha256(payload).hexdigest())


def matching_terminals(entries, args, event=None):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == args.kind and entry.get("lot") == args.built
        and entry.get("correction") == args.round and entry.get("task") == args.task
        and progress.note_data(entry).get("attempt") == args.attempt
        and (event is None or progress.note_data(entry) == event)
    ]


def attempt_terminals(entries, args):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") in {"attempt.failed", "attempt.succeeded", "paused", "aborted"}
        and entry.get("lot") == args.built and entry.get("correction") == args.round
        and entry.get("task") == args.task
        and progress.note_data(entry).get("attempt") == args.attempt
    ]


def require_matching_stop_terminal(terminals, args):
    if len(terminals) > 1:
        fail("the correction attempt has duplicate terminals")
    if terminals and terminals[0][1].get("kind") != args.kind:
        fail("the correction attempt already has another terminal outcome")


def derive(args, attempt_payload, attempt_marker, resolved, roots):
    identity = progress.active_attempt_identity({
        "lot": args.built, "correction": args.round,
        "task": args.task, "attempt": args.attempt,
    }, f"the correction attempt {args.kind}", allow_closer=True, include_completion=True)
    base_ref = f"{resolved['ref_root']}/attempt-base"
    base_commit = git_output("rev-parse", "--verify", f"{base_ref}^{{commit}}")
    base_tree = git_output("rev-parse", f"{base_commit}^{{tree}}")
    try_ref = f"{resolved['ref_root']}/task-{args.task}-try-{args.attempt}"
    event = {
        "schema": 2,
        "unit": identity["unit"],
        "unit_authority_sha256": identity["unit_authority_sha256"],
        "execution_authority_sha256": identity["execution_authority_sha256"],
        "prior_attempt": identity["prior_attempt"],
        "attempt": identity["attempt"],
        "sha": base_commit,
        "preserved_ref": None,
        "design_proof_authority": identity["design_proof_authority"],
        "final_checker_set_sha256": identity["outstanding_final_checker_set_sha256"],
        "final_checker_assignments": identity["assigned_final_checker_obligations"],
        "spares": roots,
        "spare_snapshot": None,
    }
    operation = operation_identity(args, event)
    return operation, {
        "schema": 1,
        "operation": operation,
        "kind": args.kind,
        "event": event,
        "attempt_marker_sha256": hashlib.sha256(attempt_payload).hexdigest(),
        "base_ref": base_ref,
        "base_commit": base_commit,
        "base_tree": base_tree,
        "try_ref": try_ref,
    }


def derive_with_resolved(args, attempt_payload, attempt_marker, resolved, roots):
    token = progress.CORRECTION_RESOLVED_WORK_UNITS.set((resolved,))
    try:
        return derive(args, attempt_payload, attempt_marker, resolved, roots)
    finally:
        progress.CORRECTION_RESOLVED_WORK_UNITS.reset(token)


def derive_live(args, roots):
    resolved = resolve_correction(args.built, args.round, args.task)
    attempt_payload, attempt_marker = failure.read_attempt_marker()
    if attempt_marker.get("task") != args.task or attempt_marker.get("attempt") != args.attempt:
        fail("the correction attempt marker belongs to another attempt")
    operation, expected = derive_with_resolved(
        args, attempt_payload, attempt_marker, resolved, roots,
    )
    return {
        "resolved": resolved,
        "attempt_payload": attempt_payload,
        "attempt_marker": attempt_marker,
        "operation": operation,
        "expected": expected,
    }


def provisional_event(args, attempt_marker, roots):
    predecessor = attempt_marker.get("attempt_predecessor")
    predecessor_commit = predecessor.get("commit") if isinstance(predecessor, dict) else None
    execution_authority = {
        "schema": 1,
        "contract_authority": attempt_marker.get("unit_authority_sha256"),
        "tree_authority": attempt_marker.get("tree_authority"),
    }
    return {
        "schema": 2,
        "unit": attempt_marker.get("unit"),
        "unit_authority_sha256": attempt_marker.get("unit_authority_sha256"),
        "execution_authority_sha256": hashlib.sha256(
            canonical_bytes(execution_authority),
        ).hexdigest(),
        "prior_attempt": attempt_marker.get("prior_attempt"),
        "attempt": attempt_marker.get("attempt"),
        "sha": predecessor_commit,
        "preserved_ref": None,
        "design_proof_authority": attempt_marker.get("design_proof_authority"),
        "final_checker_set_sha256": attempt_marker.get(
            "outstanding_final_checker_set_sha256"
        ),
        "final_checker_assignments": attempt_marker.get(
            "assigned_final_checker_obligations"
        ),
        "spares": roots,
        "spare_snapshot": None,
    }


def provisional_operation(args, roots):
    marker_path = WORKSPACE / MARKER_NAME
    if marker_path.exists() or marker_path.is_symlink():
        _payload, account = read_marker()
        operation = account.get("operation")
        if not isinstance(operation, str):
            fail("the pending correction attempt stop has no operation identity")
        return operation
    entries = progress.journal_entries()
    terminals = attempt_terminals(entries, args)
    require_matching_stop_terminal(terminals, args)
    if terminals:
        progress.expected_attempt_stop_data(
            entries, terminals[0][0], terminals[0][1],
            "the recorded correction attempt stop",
        )
        return operation_identity(args, progress.note_data(terminals[0][1]))
    _attempt_payload, attempt_marker = failure.read_attempt_marker()
    if attempt_marker.get("task") != args.task or attempt_marker.get("attempt") != args.attempt:
        fail("the correction attempt marker belongs to another attempt")
    return operation_identity(args, provisional_event(args, attempt_marker, roots))


def close(args):
    if args.kind == "paused" and args.spares:
        fail("a Correction Round pause preserves everything and takes no spared path")
    roots = normalize_spares(args.spares)
    operation = provisional_operation(args, roots)
    marker_path = WORKSPACE / MARKER_NAME

    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        resolved = resolve_correction(args.built, args.round, args.task)
        attempt_payload, attempt_marker = failure.read_attempt_marker()
        if attempt_marker.get("task") != args.task \
                or attempt_marker.get("attempt") != args.attempt:
            fail("the correction attempt marker belongs to another attempt")
        entries = progress.journal_entries()
        terminals = attempt_terminals(entries, args)
        require_matching_stop_terminal(terminals, args)
        if terminals:
            event = progress.expected_attempt_stop_data(
                entries, terminals[0][0], terminals[0][1],
                "the recorded correction attempt stop",
            )
            failure.validate_completed_attempt_marker(
                args, entries, terminals[0][0], event, attempt_marker, resolved,
                set_key="final_checker_set_sha256",
                assignments_key="final_checker_assignments",
            )
            current_operation = operation_identity(args, event)
            if current_operation != operation:
                fail("the correction attempt stop operation changed while waiting for authority")
            _operation, expected = derive_with_resolved(
                args, attempt_payload, attempt_marker, resolved, roots,
            )
            if marker_path.exists() or marker_path.is_symlink():
                marker_payload, account = read_marker()
                event_projection = {
                    **account.get("event", {}),
                    "preserved_ref": None,
                    "spare_snapshot": None,
                }
                if any(account.get(key) != expected.get(key) for key in (
                    "schema", "operation", "kind", "attempt_marker_sha256",
                    "base_ref", "base_commit", "base_tree", "try_ref",
                )) or event_projection != expected["event"]:
                    fail("the pending correction attempt stop changes its frozen account")
                failure.validate_candidate(account)
                failure.preserve_and_reset(account)
                remove_exact(
                    MARKER_NAME, marker_payload,
                    "the completed correction attempt stop owner",
                )
            remove_exact(
                "attempt-in-flight", attempt_payload,
                "the completed correction attempt identity",
            )
            print(f"CORRECTION ATTEMPT {args.kind.upper()} (already recorded)")
            return
        operation_under_lease, expected = derive_with_resolved(
            args, attempt_payload, attempt_marker, resolved, roots,
        )
        current = {
            "resolved": resolved,
            "attempt_payload": attempt_payload,
            "attempt_marker": attempt_marker,
            "operation": operation_under_lease,
            "expected": expected,
        }
        if current["operation"] != operation:
            fail("the correction attempt stop operation changed while waiting for authority")
        attempt_payload = current["attempt_payload"]
        attempt_marker = current["attempt_marker"]
        expected = current["expected"]
        if marker_path.exists() or marker_path.is_symlink():
            marker_payload, account = read_marker()
            event_projection = {
                **account.get("event", {}), "preserved_ref": None, "spare_snapshot": None,
            }
            if any(account.get(key) != expected.get(key) for key in (
                "schema", "operation", "kind", "attempt_marker_sha256",
                "base_ref", "base_commit", "base_tree", "try_ref",
            )) or event_projection != expected["event"]:
                fail("the pending correction attempt stop changes its frozen account")
        else:
            failure.ensure_no_foreign_owner()
            for name in BLOCKING_MARKERS:
                path = WORKSPACE / name
                if path.exists() or path.is_symlink():
                    fail(f"another workflow owner is unfinished: {name}")
            feature = WORKSPACE.name[11:] if re.match(
                r"^\d{4}-\d{2}-\d{2}-", WORKSPACE.name,
            ) else WORKSPACE.name
            candidate = candidate_with_spares(
                feature, args, expected["base_commit"], roots,
            )
            event = {**expected["event"], "spare_snapshot": candidate["spare_snapshot_commit"]}
            preserved_ref = expected["try_ref"] if candidate["candidate_commit"] is not None else None
            event["preserved_ref"] = preserved_ref
            expected = {**expected, "event": event, **candidate}
            account = expected
            publish_marker(account)
            marker_payload = canonical_bytes(account) + b"\n"

        failure.validate_candidate(account)
        failure.preserve_and_reset(account)
        if account["event"]["spares"]:
            restore = [
                "git", "-C", str(REPO), "restore", "--source",
                account["spare_snapshot_commit"], "--worktree", "--",
                *[f":(literal){path}" for path in account["event"]["spares"]],
            ]
            restored = subprocess.run(
                restore, cwd=REPO, capture_output=True, text=True,
            )
            if restored.returncode != 0:
                fail(restored.stderr.strip() or "the spared correction paths could not restore")
            if spare_manifest(account["event"]["spares"]) != account["spare_manifest"]:
                fail("the spared correction paths changed during restoration")
        if args.kind == "aborted":
            clean = ["git", "-C", str(REPO), "clean", "-fd"]
            for path in account["event"]["spares"]:
                clean.extend(["-e", f"/{path}"])
            removed = subprocess.run(
                clean,
                cwd=REPO, capture_output=True, text=True,
            )
            if removed.returncode != 0:
                fail(removed.stderr.strip() or "the correction abort cleanup refused")
        entries = progress.journal_entries()
        terminals = matching_terminals(entries, args, account["event"])
        if not terminals:
            note = note_args(account["event"], args.task, args.kind)
            progress.cmd_note_with_lease(
                note, lease, operation, owner_marker=MARKER_NAME,
            )
            entries = progress.journal_entries()
            terminals = matching_terminals(entries, args, account["event"])
        if len(terminals) != 1:
            fail("the correction attempt stop terminal is unavailable")
        progress.expected_attempt_stop_data(
            entries, terminals[0][0], terminals[0][1],
            "the durable correction attempt stop",
        )
        remove_exact(MARKER_NAME, marker_payload, "the completed correction attempt stop owner")
        remove_exact(
            "attempt-in-flight", attempt_payload, "the completed correction attempt identity",
        )
    print(f"CORRECTION ATTEMPT {args.kind.upper()} {args.built} c{args.round} task {args.task}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("paused", "aborted"))
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("task", type=int)
    parser.add_argument("attempt", type=int)
    parser.add_argument("spares", nargs="*")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.task < 1 or args.attempt < 1:
        print("**correction stop ERROR** · malformed correction stop identity", file=sys.stderr)
        raise SystemExit(1)
    try:
        close(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"**correction stop ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
