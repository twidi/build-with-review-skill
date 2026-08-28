#!/usr/bin/env python3
"""Publish one bounded controller-owned Correction Round artifact revision."""

import argparse
import hashlib
import json
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
    publish_content_object,
    replacement_recovery_relative_path,
    validate_content_object,
)
from correction_round import parse_artifact  # noqa: E402

MARKER_NAME = "correction-round-revision-in-progress"
REVISION_REASON = "task-contract-correction"
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
    "correction-terminal-restore-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-rewind-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
    "correction-round-escalation-in-progress",
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


def revision_projection(entries, built, correction, from_task, *, publish_object=True):
    blocker = progress.correction_revision_blocker_account(
        entries, len(entries), built, correction, "the Correction Round revision",
    )
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
    if publish_object:
        published = publish_content_object(WORKSPACE, built, payload, ".md")
    else:
        if hashlib.sha256(payload).hexdigest() != artifact["artifact_sha256"]:
            fail("the retained Correction Round revision changes its artifact bytes")
        published = validate_content_object(
            WORKSPACE, built, artifact["artifact_sha256"], ".md",
        )
    projection["artifact_object"] = str(published.relative_to(WORKSPACE))
    if relative != state["path"]:
        fail("the Correction Round revision changes its canonical artifact path")
    return state, relative, artifact, projection, accepted, blocker


def derive_pre_task_event(entries, built, correction, from_task, *, publish_object=True):
    state, relative, artifact, projection, accepted, blocker = revision_projection(
        entries, built, correction, from_task, publish_object=publish_object,
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
        "reason": REVISION_REASON,
        "from_task": from_task,
        "artifact_sha256": projection["artifact_sha256"],
        "artifact_object": projection["artifact_object"],
        "controller_sha256": artifact["controller_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "blocker": blocker,
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


def post_task_static_account(
        entries, built, correction, from_task, operation, *, publish_object=True,
):
    state, relative, artifact, projection, accepted, blocker = revision_projection(
        entries, built, correction, from_task, publish_object=publish_object,
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
        "reason": REVISION_REASON,
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
        "blocker": blocker,
        "document": relative,
        "parent_commit": parent,
        "retry_transition": progress.correction_revision_retry_transition(
            entries, len(entries), state, artifact, "the Correction Round revision",
        ),
    }, state, artifact


def operation_identity(built, correction, from_task):
    payload = {
        "kind": "correction-round-revision",
        "built": built,
        "round": correction,
        "from_task": from_task,
        "reason": REVISION_REASON,
    }
    return f"correction-revision:{hashlib.sha256(canonical_bytes(payload)).hexdigest()}"


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def marker_anchor(subject="the Correction Round revision owner"):
    return WorkspaceFileAnchor(WORKSPACE, MARKER_NAME, subject)


def parse_marker_payload(payload):
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the Correction Round revision marker is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the Correction Round revision marker is not canonical")
    return account


def read_marker():
    with marker_anchor() as anchored:
        return parse_marker_payload(anchored.read_regular())


def publish_marker(account):
    payload = canonical_bytes(account) + b"\n"
    try:
        with marker_anchor() as anchored:
            anchored.publish(payload, mode=0o600)
    except FileExistsError:
        fail("another Correction Round revision owner is pending")


def marker_recovery_generations(operation):
    pattern = f".{MARKER_NAME}.correction-recovery-*"
    generations = []
    for path in sorted(WORKSPACE.glob(pattern)):
        relative = path.relative_to(WORKSPACE).as_posix()
        with WorkspaceFileAnchor(
            WORKSPACE, relative, "a Correction Round revision marker recovery",
        ) as recovery:
            payload = recovery.read_regular()
        account = parse_marker_payload(payload)
        expected = replacement_recovery_relative_path(MARKER_NAME, payload)
        if relative != expected.as_posix() or account.get("operation") != operation:
            fail("the Correction Round revision marker recovery has another owner")
        generations.append((relative, payload, account))
    return generations


def replace_marker(anchored, predecessor_payload, account):
    payload = canonical_bytes(account) + b"\n"
    anchored.replace_exact(
        hashlib.sha256(predecessor_payload).hexdigest(), payload, mode=0o600,
    )


def validate_marker_recoveries(entries, built, correction, operation):
    recoveries = marker_recovery_generations(operation)
    for _relative, _payload, account in recoveries:
        reproject_marker(entries, account, built, correction, operation)
    return recoveries


def remove_marker(anchored, payload, operation, entries, built, correction):
    recoveries = validate_marker_recoveries(
        entries, built, correction, operation,
    )
    for relative, recovery_payload, _account in recoveries:
        with WorkspaceFileAnchor(
            WORKSPACE, relative, "a completed Correction Round revision recovery",
        ) as recovery:
            current = recovery.read_regular()
            if current != recovery_payload:
                fail("a Correction Round revision recovery changed before cleanup")
            recovery.remove_exact(hashlib.sha256(current).hexdigest())
    anchored.remove_exact(hashlib.sha256(payload).hexdigest())


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


def retained_marker_identity(account, built, correction):
    if not isinstance(account, dict) or account.get("reason") != REVISION_REASON:
        fail("the retained Correction Round revision has malformed owner identity")
    if "phase" in account:
        marker_built = account.get("built")
        marker_round = account.get("round")
        from_task = account.get("from_task")
    else:
        event = account.get("event")
        if not isinstance(event, dict):
            fail("the retained Correction Round revision has no event identity")
        marker_built = event.get("built")
        marker_round = event.get("round")
        from_task = event.get("from_task")
    if marker_built != built or marker_round != correction \
            or isinstance(from_task, bool) or not isinstance(from_task, int) \
            or from_task < 1:
        fail("the retained Correction Round revision belongs to another work unit")
    operation = operation_identity(built, correction, from_task)
    if account.get("operation") != operation:
        fail("the retained Correction Round revision has malformed operation identity")
    return from_task, operation


def reproject_marker(entries, account, built, correction, operation):
    from_task, current_operation = retained_marker_identity(account, built, correction)
    if current_operation != operation:
        fail("the retained Correction Round revision changes its operation")
    event = account.get("event")
    if event is not None:
        terminals = [(index, entry) for index, entry in enumerate(entries)
                     if entry.get("kind") == "correction.round.revised"
                     and progress.note_data(entry) == event]
        if len(terminals) > 1:
            fail("the retained Correction Round revision terminal is duplicated")
        if terminals:
            terminal_index, terminal = terminals[0]
            progress.validate_correction_round_revision_entry(
                entries, terminal_index, terminal,
            )
            entries = entries[:terminal_index]
    if "phase" in account:
        static, _state, _artifact = post_task_static_account(
            entries, built, correction, from_task, operation, publish_object=False,
        )
        validate_post_task_marker(account, static)
    else:
        event = derive_pre_task_event(
            entries, built, correction, from_task, publish_object=False,
        )
        expected = {
            "schema": 1,
            "operation": operation,
            "reason": REVISION_REASON,
            "event": event,
        }
        if account != expected:
            fail("the pending Correction Round revision changes its frozen account")
    return from_task


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
        "reason": REVISION_REASON,
        "from_task": account["from_task"],
        "artifact_sha256": account["artifact_sha256"],
        "artifact_object": account["artifact_object"],
        "controller_sha256": account["controller_sha256"],
        "manifest_sha256": account["manifest_sha256"],
        "blocker": account["blocker"],
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
    marker_exists = marker.exists() or marker.is_symlink()
    retained_anchor = None
    retained_payload = None
    retained_identity = None
    if args.retained:
        if not marker_exists:
            fail("the retained Correction Round revision owner is absent")
        retained_anchor = marker_anchor()
        try:
            retained_anchor.__enter__()
            retained_payload = retained_anchor.read_regular()
            retained_status = retained_anchor.status()
            retained_identity = (retained_status.st_dev, retained_status.st_ino)
            candidate = parse_marker_payload(retained_payload)
            from_task, operation = retained_marker_identity(
                candidate, args.built, args.round,
            )
        except BaseException:
            retained_anchor.close()
            raise
    else:
        from_task = args.from_task
        operation = operation_identity(args.built, args.round, from_task)
    if not marker.exists() and not marker.is_symlink():
        _, payload, _ = current_artifact(args.built, args.round)
        latest = [(index, entry) for index, entry in enumerate(entries)
                  if entry.get("kind") == "correction.round.revised"
                  and progress.note_data(entry).get("built") == args.built
                  and progress.note_data(entry).get("round") == args.round]
        if latest and progress.note_data(latest[-1][1]).get("artifact_sha256") \
                == hashlib.sha256(payload).hexdigest() \
                and progress.note_data(latest[-1][1]).get("from_task") == from_task:
            progress.validate_correction_round_revision_entry(
                entries, latest[-1][0], latest[-1][1],
            )
            print("CORRECTION ROUND REVISION (already recorded)")
            return
    try:
        with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
            current_entries = progress.journal_entries()
            progress.require_no_current_correction_stop(
                current_entries, len(current_entries), args.built, args.round,
                "the Correction Round revision",
            )
            progress.require_no_active_correction_amendment(
                current_entries, len(current_entries), args.built, args.round,
                "the Correction Round revision",
            )
            if marker.exists() or marker.is_symlink():
                if retained_anchor is not None:
                    current_payload = retained_anchor.read_regular()
                    current_status = retained_anchor.status()
                    if (current_status.st_dev, current_status.st_ino) != retained_identity \
                            or current_payload != retained_payload:
                        fail("the retained Correction Round revision marker was substituted")
                    account = parse_marker_payload(current_payload)
                    retained_anchor.close()
                    retained_anchor = None
                else:
                    account = read_marker()
                retained_from_task, retained_operation = retained_marker_identity(
                    account, args.built, args.round,
                )
                if retained_operation != operation or retained_from_task != from_task:
                    fail("the pending Correction Round revision belongs to another operation")
            else:
                if args.retained:
                    fail("the retained Correction Round revision owner disappeared")
                ensure_no_foreign_owner()
                dirty = subprocess.run(
                    ["git", "-C", progress.project_root(), "status", "--porcelain"],
                    capture_output=True, text=True,
                )
                if dirty.returncode != 0 or dirty.stdout:
                    fail("a Correction Round revision requires one clean project tree")
                current_entries = progress.journal_entries()
                (_state, _relative, _artifact, _projection, accepted,
                 _blocker) = revision_projection(
                    current_entries, args.built, args.round, from_task,
                )
                if accepted:
                    static, _state, _artifact = post_task_static_account(
                        current_entries, args.built, args.round, from_task, operation,
                    )
                    head = git_text("rev-parse", "HEAD")
                    if head != static["parent_commit"]:
                        fail("the post-task revision is not on its exact accepted predecessor")
                    account = {**static, "phase": "prepared"}
                else:
                    event = derive_pre_task_event(
                        current_entries, args.built, args.round, from_task,
                    )
                    account = {
                        "schema": 1, "operation": operation, "event": event,
                        "reason": REVISION_REASON,
                    }
                publish_marker(account)

            while True:
                with marker_anchor() as anchored:
                    marker_payload = anchored.read_regular()
                    account = parse_marker_payload(marker_payload)
                    from_task = reproject_marker(
                        progress.journal_entries(), account, args.built, args.round, operation,
                    )
                    validate_marker_recoveries(
                        progress.journal_entries(), args.built, args.round, operation,
                    )
                    if account.get("phase") == "prepared":
                        commit, tree = publish_document_commit(account)
                        successor = {
                            **account,
                            "phase": "baseline-required",
                            "commit": commit,
                            "tree": tree,
                            "baseline_owner": progress.correction_revision_baseline_owner(
                                account["built"], account["round"], account["revision"], commit,
                            ),
                        }
                        replace_marker(anchored, marker_payload, successor)
                        continue
                    if account.get("phase") == "baseline-required":
                        gate = accepted_revision_baseline(progress.journal_entries(), account)
                        if gate is None:
                            print(
                                "BASELINE REQUIRED\n"
                                f"Run correction-round-baseline.sh {args.built} {args.round}, "
                                "finish its exact baseline gate, then rerun "
                                f"correction-round-revise.sh {args.built} {args.round}."
                            )
                            return
                        event = revision_event(account, gate)
                        progress.normalize_correction_round_revision(
                            progress.journal_entries(), event, "the Correction Round revision",
                        )
                        successor = {
                            **account, "phase": "terminal-ready", "gate": gate, "event": event,
                        }
                        replace_marker(anchored, marker_payload, successor)
                        continue
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
                    remove_marker(
                        anchored, marker_payload, operation, entries,
                        args.built, args.round,
                    )
                    print(
                        f"CORRECTION ROUND REVISED {args.built} {args.round} "
                        f"revision {event['revision']}"
                    )
                    return
    finally:
        if retained_anchor is not None:
            retained_anchor.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("from_task", type=int, nargs="?")
    parser.add_argument("reason", nargs="?")
    args = parser.parse_args()
    args.retained = args.from_task is None
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 \
            or (args.from_task is None and args.reason is not None) \
            or (args.from_task is not None and (
                args.from_task < 1
                or (args.reason is not None and not args.reason.strip())
            )):
        print("**correction revision ERROR** · malformed revision input", file=sys.stderr)
        raise SystemExit(1)
    try:
        run(args)
    except (OSError, ValueError) as exc:
        print(f"**correction revision ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
