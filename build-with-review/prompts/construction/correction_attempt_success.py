#!/usr/bin/env python3
"""Close one successful Correction Round task attempt."""

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

import correction_attempt_failure as failure  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
)
from work_unit import progress, resolve_correction  # noqa: E402

BLOCKING_MARKERS = failure.BLOCKING_MARKERS | {
    "correction-attempt-failure-in-progress",
}


def refuse(message):
    print(f"**correction success ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args, check=True, input_text=None):
    result = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, input=input_text,
    )
    if check and result.returncode != 0:
        refuse(result.stderr.strip() or result.stdout.strip() or "a required command refused")
    return result


def git_output(*args):
    return run("git", "-C", str(REPO), *args).stdout.strip()


def read_marker():
    path = WORKSPACE / "attempt-in-flight"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        refuse(f"the attempt-in-flight identity is unavailable: {exc}")
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            refuse("attempt-in-flight is not a real regular file")
        with os.fdopen(descriptor, encoding="utf-8") as source:
            descriptor = None
            payload = source.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        marker = json.loads(payload)
    except ValueError as exc:
        refuse(f"the correction attempt marker is malformed: {exc}")
    return path, payload, marker


def matching_successes(entries, built, round_number, task, account):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("event") == "note" and entry.get("kind") == "attempt.succeeded"
        and entry.get("lot") == built and entry.get("correction") == round_number
        and entry.get("task") == task and progress.note_data(entry) == account
    ]


def operation_identity(args):
    account = {
        "kind": "correction-attempt-success",
        "built": args.built,
        "round": args.round,
        "task": args.task,
        "commit": args.commit,
        "gate": args.gate,
    }
    return "correction-attempt-success:" + hashlib.sha256(json.dumps(
        account, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def validate_recorded_success(entries, built, round_number, task, commit, gate):
    candidates = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("event") == "note" and entry.get("kind") == "attempt.succeeded"
        and entry.get("lot") == built and entry.get("correction") == round_number
        and entry.get("task") == task and progress.note_data(entry).get("sha") == commit
        and progress.note_data(entry).get("gate") == gate
    ]
    if len(candidates) != 1:
        refuse("the stable correction task ref has no one exact success terminal")
    index, entry = candidates[0]
    progress.validate_attempt_succeeded_entry(entries, index, entry)


def authenticate_candidate(resolved, identity, reported, gate):
    dirty = git_output("status", "--porcelain")
    if dirty:
        refuse(f"the tree is not clean:\n{dirty}")
    commit = git_output("rev-parse", "--verify", f"{reported}^{{commit}}")
    head = git_output("rev-parse", "HEAD")
    if commit != head:
        refuse("the reported correction commit is not current HEAD")
    parent = git_output("rev-parse", "--verify", f"{commit}^")
    if parent != identity["attempt_predecessor"]["commit"]:
        refuse("the correction task commit is not a direct child of its frozen predecessor")
    document = resolved["repository_document"]
    changed = run(
        "git", "-C", str(REPO), "diff-tree", "--no-commit-id", "--name-only", "-r",
        "HEAD", "--", document,
    ).stdout.splitlines()
    if changed != [document]:
        refuse("the correction task commit does not publish its exact correction artifact")
    committed = run("git", "-C", str(REPO), "show", f"HEAD:{document}").stdout.encode()
    try:
        workspace = (WORKSPACE / resolved["workspace_document"]).read_bytes()
    except OSError as exc:
        refuse(f"the workspace correction artifact is unreadable: {exc}")
    if committed != workspace:
        refuse("the committed correction artifact differs from its workspace authority")
    gate_result = run(
        "bash", str(HERE / "gate-check.sh"), "require-task", gate, resolved["unit"]["built"],
        str(identity["task"]), str(identity["attempt"]), commit,
        str(resolved["unit"]["round"]), check=False,
    )
    if gate_result.returncode != 0:
        refuse("the supplied final gate does not prove the exact correction task candidate")
    return commit


def append_success(account, task, lease, operation):
    note = SimpleNamespace(
        kind="attempt.succeeded", mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(account, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )
    try:
        progress.cmd_note_with_lease(
            note, lease, operation, owner_marker="attempt-in-flight",
        )
    except SystemExit:
        refuse(
            "the stable correction task ref exists, but attempt.succeeded did not append; "
            "retry this exact success closer"
        )


def remove_exact_marker(path, expected_payload):
    digest = hashlib.sha256(expected_payload.encode()).hexdigest()
    try:
        with WorkspaceFileAnchor(
            WORKSPACE, path.name, "the completed correction attempt owner",
        ) as anchored:
            anchored.remove_exact(digest)
    except (OSError, ValueError) as exc:
        refuse(f"the attempt marker changed before cleanup: {exc}")


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        if os.path.lexists(WORKSPACE / name):
            refuse(f"another workflow owner is unfinished: {name}")


def close_owned(args, lease, operation):
    ensure_no_foreign_owner()
    try:
        resolved = resolve_correction(args.built, args.round, args.task)
    except (OSError, ValueError) as exc:
        refuse(str(exc))
    stable_ref = f"{resolved['ref_root']}/task-{args.task}"
    stable_result = run(
        "git", "-C", str(REPO), "rev-parse", "--verify", f"{stable_ref}^{{commit}}",
        check=False,
    )
    stable = stable_result.stdout.strip() if stable_result.returncode == 0 else None
    marker_path = WORKSPACE / "attempt-in-flight"

    if not marker_path.exists():
        if stable is None:
            refuse("no correction attempt is in flight and no stable task ref exists")
        reported = git_output("rev-parse", "--verify", f"{args.commit}^{{commit}}")
        if reported != stable:
            refuse("the stable correction task ref never retargets")
        validate_recorded_success(
            progress.journal_entries(), args.built, args.round, args.task, stable, args.gate,
        )
        print(f"correction-task-{args.task} {stable} (already recorded)")
        return

    marker_path, marker_payload, marker = read_marker()
    attempt = marker.get("attempt") if isinstance(marker, dict) else None
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        refuse("the correction attempt marker has no positive attempt identity")
    identity = progress.active_attempt_identity({
        "lot": args.built, "correction": args.round, "task": args.task, "attempt": attempt,
    }, "the correction attempt success", include_completion=True)
    entries = progress.journal_entries()
    account = progress.correction_attempt_succeeded_account(
        entries, len(entries), identity, args.commit, args.gate,
        "the correction attempt success",
    )

    if stable is None:
        commit = authenticate_candidate(resolved, identity, args.commit, args.gate)
        account["sha"] = commit
        update = run(
            "git", "-C", str(REPO), "update-ref", stable_ref, commit,
            "0" * len(commit), check=False,
        )
        if update.returncode != 0:
            refuse("the stable correction task ref could not publish from its absent state")
        stable = commit
    else:
        reported = git_output("rev-parse", "--verify", f"{args.commit}^{{commit}}")
        if reported != stable:
            refuse("the stable correction task ref never retargets")
        account["sha"] = stable
        gate_result = run(
            "bash", str(HERE / "gate-check.sh"), "require-task", args.gate, args.built,
            str(args.task), str(attempt), stable, str(args.round), check=False,
        )
        if gate_result.returncode != 0:
            refuse("the stable correction task ref has no matching final gate")

    entries = progress.journal_entries()
    matches = matching_successes(entries, args.built, args.round, args.task, account)
    if len(matches) > 1:
        refuse("the correction task has duplicate success terminals")
    if matches:
        progress.validate_attempt_succeeded_entry(entries, matches[0][0], matches[0][1])
    else:
        append_success(account, args.task, lease, operation)
    remove_exact_marker(marker_path, marker_payload)
    print(f"correction-task-{args.task} {stable}")


def close(args):
    operation = operation_identity(args)
    try:
        with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
            close_owned(args, lease, operation)
    except (OSError, ValueError) as exc:
        refuse(str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("task", type=int)
    parser.add_argument("commit")
    parser.add_argument("gate")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.task < 1 \
            or not re.fullmatch(r"[0-9a-f]{40,64}", args.commit) \
            or not re.fullmatch(r"[0-9a-f]{64}", args.gate):
        refuse("the correction success identity is malformed")
    close(args)


if __name__ == "__main__":
    main()
