#!/usr/bin/env python3
"""Publish one bounded controller-owned Correction Round artifact revision."""

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
from correction_round import parse_artifact  # noqa: E402

MARKER_NAME = "correction-round-revision-in-progress"
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
    "correction-round-built-in-progress",
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


def current_artifact(built, correction):
    relative = pathlib.PurePosixPath("corrections", built, f"round-{correction}.md")
    path = WORKSPACE / relative
    artifact = parse_artifact(path, expected_built=built, expected_round=correction)
    if artifact["state"] != "active":
        fail("only an active Correction Round artifact can be revised")
    return relative.as_posix(), path.read_bytes(), artifact


def revision_projection(entries, built, correction, from_task):
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction, "the Correction Round revision",
    )
    relative, payload, artifact = current_artifact(built, correction)
    projection = {
        "from_task": from_task,
        "artifact_sha256": artifact["artifact_sha256"],
    }
    _artifact, accepted = progress.validate_correction_revision_projection(
        entries, len(entries), state, projection, "the Correction Round revision",
        artifact=artifact,
    )
    published = publish_content_object(WORKSPACE, built, payload, ".md")
    projection["artifact_object"] = str(published.relative_to(WORKSPACE))
    if relative != state["path"]:
        fail("the Correction Round revision changes its canonical artifact path")
    return state, relative, artifact, projection, accepted


def derive_pre_task_event(entries, built, correction, from_task):
    state, relative, artifact, projection, accepted = revision_projection(
        entries, built, correction, from_task,
    )
    if accepted:
        fail("the pre-task revision follows accepted correction work")
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    tree = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or tree.returncode != 0 \
            or head.stdout.strip() != state["commit"] \
            or tree.stdout.strip() != state["tree"]:
        fail("the pre-task revision is not on its exact accepted correction base")
    event = {
        "schema": 1,
        "built": built,
        "round": correction,
        "revision": state["revision"] + 1,
        "previous": state["proof"],
        "previous_execution_authority_sha256": state["execution_authority_sha256"],
        "reason": "task-contract-correction",
        "from_task": from_task,
        "artifact_sha256": projection["artifact_sha256"],
        "artifact_object": projection["artifact_object"],
        "controller_sha256": artifact["controller_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "commit": state["commit"],
        "tree": state["tree"],
        "gate": state["gate"],
        "retry_transition": progress.correction_revision_retry_transition(
            entries, len(entries), state, artifact, "the Correction Round revision",
        ),
    }
    progress.normalize_correction_round_revision(
        entries, event, "the Correction Round revision",
    )
    return event


def post_task_static_account(entries, built, correction, from_task, operation, reason_sha256):
    state, relative, artifact, projection, accepted = revision_projection(
        entries, built, correction, from_task,
    )
    if not accepted:
        fail("the post-task revision has no accepted correction task")
    revision = state["revision"] + 1
    parent = progress.correction_revision_parent(
        state, accepted, "the Correction Round revision",
    )
    return {
        "schema": 1,
        "operation": operation,
        "reason_sha256": reason_sha256,
        "built": built,
        "round": correction,
        "from_task": from_task,
        "revision": revision,
        "previous": state["proof"],
        "previous_execution_authority_sha256": state["execution_authority_sha256"],
        "artifact_sha256": projection["artifact_sha256"],
        "artifact_object": projection["artifact_object"],
        "controller_sha256": artifact["controller_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "document": relative,
        "parent_commit": parent,
        "retry_transition": progress.correction_revision_retry_transition(
            entries, len(entries), state, artifact, "the Correction Round revision",
        ),
    }, state, artifact


def operation_identity(built, correction, from_task, reason):
    payload = {
        "kind": "correction-round-revision",
        "built": built,
        "round": correction,
        "from_task": from_task,
        "reason_sha256": hashlib.sha256(reason.encode()).hexdigest(),
    }
    return f"correction-revision:{hashlib.sha256(canonical_bytes(payload)).hexdigest()}"


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def atomic_marker(path, account):
    if path.exists() or path.is_symlink():
        fail("another Correction Round revision owner is pending")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the Correction Round revision marker had a short write")
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
        fail(f"the Correction Round revision marker is malformed: {exc}")
    if path.is_symlink() or not path.is_file() or status.st_nlink < 1 \
            or canonical_bytes(account) + b"\n" != payload:
        fail("the Correction Round revision marker is not one canonical real file")
    return account


def replace_marker(path, account):
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        payload = canonical_bytes(account) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            fail("the Correction Round revision marker had a short replacement write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def git_text(*arguments):
    result = subprocess.run(
        ["git", "-C", progress.project_root(), *arguments],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def validate_post_task_marker(account, expected):
    static_keys = set(expected)
    if not isinstance(account, dict) or any(account.get(key) != value
                                            for key, value in expected.items()):
        fail("the pending Correction Round revision changes its frozen account")
    allowed = static_keys | {"phase", "commit", "tree", "gate", "event", "baseline_owner"}
    if set(account) - allowed or account.get("phase") not in {
        "prepared", "baseline-required", "terminal-ready",
    }:
        fail("the pending Correction Round revision has a malformed phase account")
    phase = account["phase"]
    if phase == "prepared":
        if any(key in account for key in ("commit", "tree", "gate", "event", "baseline_owner")):
            fail("the prepared Correction Round revision carries a later-phase value")
    else:
        if not re.fullmatch(r"[0-9a-f]{40,64}", str(account.get("commit"))) \
                or not re.fullmatch(r"[0-9a-f]{40,64}", str(account.get("tree"))) \
                or account.get("baseline_owner") != progress.correction_revision_baseline_owner(
                    account["built"], account["round"], account["revision"], account["commit"],
                ):
            fail("the pending Correction Round revision has no exact document commit")
        if phase == "baseline-required" and any(key in account for key in ("gate", "event")):
            fail("the baseline-required Correction Round revision carries a terminal")
        if phase == "terminal-ready" and (
            not re.fullmatch(r"[0-9a-f]{64}", str(account.get("gate")))
            or not isinstance(account.get("event"), dict)
        ):
            fail("the terminal-ready Correction Round revision has no exact event")


def document_commit_matches(account):
    head = git_text("rev-parse", "HEAD")
    if head == account["parent_commit"]:
        return None
    parent = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "--verify", f"{head}^"],
        capture_output=True, text=True,
    )
    names = subprocess.run(
        ["git", "-C", progress.project_root(), "diff-tree", "--no-commit-id",
         "--name-only", "-r", head], capture_output=True, text=True,
    )
    blob = subprocess.run(
        ["git", "-C", progress.project_root(), "show", f"{head}:{account['document']}"],
        capture_output=True,
    )
    if parent.returncode != 0 or parent.stdout.strip() != account["parent_commit"] \
            or names.returncode != 0 or names.stdout.splitlines() != [account["document"]] \
            or blob.returncode != 0 \
            or hashlib.sha256(blob.stdout).hexdigest() != account["artifact_sha256"]:
        fail("HEAD is not the exact pending Correction Round document commit")
    return head


def publish_document_commit(account):
    document_copy = WORKSPACE / "prompts" / "common" / "document-copy.sh"
    copied = subprocess.run(
        [document_copy, "copy", account["document"], account["document"], "replace"],
        cwd=progress.project_root(), capture_output=True, text=True,
    )
    if copied.returncode != 0:
        fail(copied.stderr.strip() or copied.stdout.strip())
    existing = document_commit_matches(account)
    if existing is None:
        staged = subprocess.run(
            ["git", "-C", progress.project_root(), "add", "--", account["document"]],
            capture_output=True, text=True,
        )
        if staged.returncode != 0:
            fail(staged.stderr.strip() or "the Correction Round document could not be staged")
        names = git_text("diff", "--cached", "--name-only").splitlines()
        if names != [account["document"]]:
            fail("the Correction Round document commit would consume another staged path")
        committed = subprocess.run(
            ["git", "-C", progress.project_root(), "-c", "core.hooksPath=/dev/null",
             "commit", "-q", "-m",
             f"docs(correction): revise {account['built']} correction round {account['round']}",
             "--", account["document"]], capture_output=True, text=True,
        )
        if committed.returncode != 0:
            fail(committed.stderr.strip() or committed.stdout.strip())
        existing = document_commit_matches(account)
    finished = subprocess.run(
        [document_copy, "finish", account["document"], account["document"], "replace"],
        cwd=progress.project_root(), capture_output=True, text=True,
    )
    if finished.returncode != 0:
        fail(finished.stderr.strip() or finished.stdout.strip())
    status = git_text("status", "--porcelain")
    if status:
        fail("the Correction Round document commit did not leave one clean tree")
    return existing, git_text("rev-parse", f"{existing}^{{tree}}")


def accepted_revision_baseline(entries, account):
    matches = [progress.note_data(entry) for entry in entries
               if entry.get("event") == "subagent-ended"
               and entry.get("kind") == "gate-runner"
               and progress.note_data(entry).get("scope") == "correction-baseline"
               and progress.note_data(entry).get("owner") == account["baseline_owner"]
               and progress.note_data(entry).get("head") == account["commit"]
               and progress.note_data(entry).get("base") == account["commit"]
               and "unusable" not in progress.note_data(entry)]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].get("green") is not True \
            or matches[0].get("surface") != "unchanged":
        fail("the pending Correction Round revision has another baseline result")
    verified = subprocess.run(
        [
            "bash", progress.GATE_CHECK, "require-correction-baseline",
            matches[0]["op"], account["commit"], account["built"], str(account["round"]),
        ],
        capture_output=True, text=True,
    )
    if verified.returncode != 0:
        fail(verified.stderr.strip() or verified.stdout.strip())
    return matches[0]["op"]


def revision_event(account, gate):
    return {
        "schema": 1,
        "built": account["built"],
        "round": account["round"],
        "revision": account["revision"],
        "previous": account["previous"],
        "previous_execution_authority_sha256": account[
            "previous_execution_authority_sha256"
        ],
        "reason": "task-contract-correction",
        "from_task": account["from_task"],
        "artifact_sha256": account["artifact_sha256"],
        "artifact_object": account["artifact_object"],
        "controller_sha256": account["controller_sha256"],
        "manifest_sha256": account["manifest_sha256"],
        "commit": account["commit"],
        "tree": account["tree"],
        "gate": gate,
        "retry_transition": account["retry_transition"],
    }


def note_args(event):
    return SimpleNamespace(
        kind="correction.round.revised", mandate=None, task=None, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def run(args):
    entries = progress.journal_entries()
    marker = WORKSPACE / MARKER_NAME
    operation = operation_identity(args.built, args.round, args.from_task, args.reason)
    reason_sha256 = hashlib.sha256(args.reason.encode()).hexdigest()
    if not marker.exists() and not marker.is_symlink():
        _, payload, _ = current_artifact(args.built, args.round)
        latest = [(index, entry) for index, entry in enumerate(entries)
                  if entry.get("kind") == "correction.round.revised"
                  and progress.note_data(entry).get("built") == args.built
                  and progress.note_data(entry).get("round") == args.round]
        if latest and progress.note_data(latest[-1][1]).get("artifact_sha256") \
                == hashlib.sha256(payload).hexdigest() \
                and progress.note_data(latest[-1][1]).get("from_task") == args.from_task:
            progress.validate_correction_round_revision_entry(
                entries, latest[-1][0], latest[-1][1],
            )
            print("CORRECTION ROUND REVISION (already recorded)")
            return
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        current_entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            current_entries, len(current_entries), args.built, args.round,
            "the Correction Round revision",
        )
        if marker.exists() or marker.is_symlink():
            account = read_marker(marker)
            if account.get("operation") != operation \
                    or account.get("reason_sha256") != reason_sha256:
                fail("the pending Correction Round revision belongs to another operation")
        else:
            ensure_no_foreign_owner()
            dirty = subprocess.run(
                ["git", "-C", progress.project_root(), "status", "--porcelain"],
                capture_output=True, text=True,
            )
            if dirty.returncode != 0 or dirty.stdout:
                fail("a Correction Round revision requires one clean project tree")
            current_entries = progress.journal_entries()
            _state, _relative, _artifact, _projection, accepted = revision_projection(
                current_entries, args.built, args.round, args.from_task,
            )
            if accepted:
                static, _state, _artifact = post_task_static_account(
                    current_entries, args.built, args.round, args.from_task,
                    operation, reason_sha256,
                )
                head = git_text("rev-parse", "HEAD")
                if head != static["parent_commit"]:
                    fail("the post-task revision is not on its exact accepted predecessor")
                account = {**static, "phase": "prepared"}
            else:
                event = derive_pre_task_event(
                    current_entries, args.built, args.round, args.from_task,
                )
                account = {
                    "schema": 1, "operation": operation, "event": event,
                    "reason_sha256": reason_sha256,
                }
            atomic_marker(marker, account)

        if "phase" in account:
            static, _state, _artifact = post_task_static_account(
                progress.journal_entries(), args.built, args.round, args.from_task,
                operation, reason_sha256,
            )
            validate_post_task_marker(account, static)
            if account["phase"] == "prepared":
                commit, tree = publish_document_commit(account)
                account = {
                    **account,
                    "phase": "baseline-required",
                    "commit": commit,
                    "tree": tree,
                    "baseline_owner": progress.correction_revision_baseline_owner(
                        account["built"], account["round"], account["revision"], commit,
                    ),
                }
                replace_marker(marker, account)
            if account["phase"] == "baseline-required":
                gate = accepted_revision_baseline(progress.journal_entries(), account)
                if gate is None:
                    print(
                        "BASELINE REQUIRED\n"
                        f"Run correction-round-baseline.sh {args.built} {args.round}, "
                        "finish its exact baseline gate, then rerun this command."
                    )
                    return
                event = revision_event(account, gate)
                progress.normalize_correction_round_revision(
                    progress.journal_entries(), event, "the Correction Round revision",
                )
                account = {
                    **account, "phase": "terminal-ready", "gate": gate, "event": event,
                }
                replace_marker(marker, account)
            event = account["event"]
        else:
            event = account.get("event")
        entries = progress.journal_entries()
        matches = [(index, entry) for index, entry in enumerate(entries)
                   if entry.get("kind") == "correction.round.revised"
                   and progress.note_data(entry) == event]
        if len(matches) > 1:
            fail("the Correction Round revision terminal is duplicated")
        if matches:
            progress.validate_correction_round_revision_entry(
                entries, matches[0][0], matches[0][1],
            )
        else:
            progress.normalize_correction_round_revision(
                entries, event, "the Correction Round revision",
            )
            progress.cmd_note_with_lease(
                note_args(event), lease, operation, owner_marker=MARKER_NAME,
            )
        marker.unlink()
        print(f"CORRECTION ROUND REVISED {args.built} {args.round} revision {event['revision']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("from_task", type=int)
    parser.add_argument("reason")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.from_task < 1 or not args.reason.strip():
        print("**correction revision ERROR** · malformed revision input", file=sys.stderr)
        raise SystemExit(1)
    try:
        run(args)
    except (OSError, ValueError) as exc:
        print(f"**correction revision ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
