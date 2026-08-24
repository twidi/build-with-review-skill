#!/usr/bin/env python3
"""Preserve and close one failed Correction Round task attempt."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
COMMON = HERE.parent / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
)
from work_unit import resolve_correction  # noqa: E402

MARKER_NAME = "correction-attempt-failure-in-progress"
FINAL_MAP_MARKER = "final-checker-contract-map-in-progress"
BLOCKING_MARKERS = {
    "amendment-commit-in-progress",
    "document-copy-in-progress",
    "gate-check-in-progress",
    "plan-commit-in-progress",
    "rewind-in-progress",
    "spec-breach-recovery-in-progress",
    "spec-commit-in-progress",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-product-authority-in-progress",
    "correction-round-built-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "correction-rewind-in-progress",
    "correction-attempt-stop-in-progress",
    "final-checker-contract-map-in-progress",
}
CLASSIFICATIONS = {"C3.9a", "C3.9b", "C3.9c", "C3.9d"}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def run(*args, check=True, env=None, input_text=None):
    result = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, env=env, input=input_text,
    )
    if check and result.returncode != 0:
        fail(result.stderr.strip() or result.stdout.strip() or "a required command refused")
    return result


def git_output(*args, env=None):
    return run("git", "-C", str(REPO), *args, env=env).stdout.strip()


def note_args(event, task):
    return SimpleNamespace(
        kind="attempt.failed", mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def operation_identity(event, task):
    return progress.correction_note_operation(note_args(event, task))


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def read_attempt_marker():
    relative = pathlib.PurePosixPath("attempt-in-flight")
    with WorkspaceFileAnchor(
        WORKSPACE, relative, "the correction attempt identity",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the correction attempt identity is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the correction attempt identity is not canonical")
    return payload, account


def publish_marker(account):
    payload = canonical_bytes(account) + b"\n"
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction attempt failure owner",
    ) as anchored:
        anchored.publish(payload)


def publish_final_map_marker(account):
    payload = canonical_bytes(account) + b"\n"
    path = WORKSPACE / FINAL_MAP_MARKER
    if path.exists() or path.is_symlink():
        with WorkspaceFileAnchor(
            WORKSPACE, FINAL_MAP_MARKER, "the final-checker contract-map owner",
        ) as anchored:
            if anchored.read_regular() != payload:
                fail("the pending final-checker contract-map owner changed")
        return payload
    with WorkspaceFileAnchor(
        WORKSPACE, FINAL_MAP_MARKER, "the final-checker contract-map owner",
    ) as anchored:
        anchored.publish(payload)
    return payload


def read_marker():
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction attempt failure owner",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the correction attempt failure owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the correction attempt failure owner is not canonical")
    return payload, account


def remove_exact(relative, payload, subject):
    digest = hashlib.sha256(payload).hexdigest()
    with WorkspaceFileAnchor(WORKSPACE, relative, subject) as anchored:
        anchored.remove_exact(digest)


def temporary_index_tree(excludes=()):
    descriptor, index_path = tempfile.mkstemp(
        prefix=".correction-failure-index-", dir=WORKSPACE,
    )
    os.close(descriptor)
    os.unlink(index_path)
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = index_path
    try:
        run("git", "-C", str(REPO), "read-tree", "HEAD", env=environment)
        pathspecs = ["."] + [f":(exclude,literal){path}" for path in excludes]
        run("git", "-C", str(REPO), "add", "-A", "--", *pathspecs, env=environment)
        return git_output("write-tree", env=environment)
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass


def candidate_account(feature, built, task, attempt, base, *, excludes=()):
    head = git_output("rev-parse", "HEAD")
    tree = temporary_index_tree(excludes)
    head_tree = git_output("rev-parse", f"{head}^{{tree}}")
    if head == base and tree == head_tree and not excludes:
        return {"input_head": head, "candidate_commit": None, "candidate_tree": tree}
    if tree == head_tree:
        candidate = head
    else:
        subject = f"{feature} {built} correction task {task} attempt {attempt} — FAILED"
        candidate = run(
            "git", "-C", str(REPO), "commit-tree", tree, "-p", head,
            input_text=f"{subject}\n",
        ).stdout.strip()
    return {"input_head": head, "candidate_commit": candidate, "candidate_tree": tree}


def derive_static(args, event, operation, attempt_payload, resolved):
    base_ref = f"{resolved['ref_root']}/attempt-base"
    base_commit = git_output("rev-parse", "--verify", f"{base_ref}^{{commit}}")
    base_tree = git_output("rev-parse", f"{base_commit}^{{tree}}")
    try_ref = f"{resolved['ref_root']}/task-{args.task}-try-{args.attempt}"
    return {
        "schema": 1,
        "operation": operation,
        "event": event,
        "attempt_marker_sha256": hashlib.sha256(attempt_payload).hexdigest(),
        "base_ref": base_ref,
        "base_commit": base_commit,
        "base_tree": base_tree,
        "try_ref": try_ref,
    }


def map_marker_account(args, event, attempt_payload, attempt_marker, resolved):
    additions = event.get("final_checker_transition", {}).get("additions")
    if not additions:
        return None
    if len(additions) != 1:
        fail("one correction failure cannot add several final-checker sources")
    addition = additions[0]
    source = addition.get("source") if isinstance(addition, dict) else None
    assignment = addition.get("assignment") if isinstance(addition, dict) else None
    unit = assignment.get("unit") if isinstance(assignment, dict) else None
    operation = unit.get("operation") if isinstance(unit, dict) else None
    if not isinstance(source, dict) or assignment is None \
            or assignment.get("owner") != "task-contract-map" \
            or unit != {
                "kind": "task-contract-map",
                "operation": operation,
                "work_unit": event["unit"],
                "target_task": args.task,
                "document_kind": "correction-artifact",
            } or not re.fullmatch(r"[0-9a-f]{64}", str(operation)):
        fail("the final-checker source has no exact contract-map assignment")
    task = resolved["task"]
    prior_ids = task["obligation_ids"]
    added_ids = [source["obligation_id"]]
    next_ids = sorted(set(prior_ids + added_ids))
    if len(next_ids) != len(prior_ids) + 1:
        fail("the final-checker source already exists in the task consumer account")
    consumer_account = {"schema": 1, "obligation_ids": next_ids}
    next_consumer = hashlib.sha256(canonical_bytes(consumer_account)).hexdigest()
    next_contract = hashlib.sha256(canonical_bytes({
        "schema": 1,
        "design_contract_sha256": task["design_contract_sha256"],
        "consumer_account_sha256": next_consumer,
    })).hexdigest()
    document = attempt_marker["document"]
    account = {
        "schema": 1,
        "operation": operation,
        "source": source,
        "attempt_marker_sha256": hashlib.sha256(attempt_payload).hexdigest(),
        "settlement": source["settlement"],
        "failure_route_sha256": hashlib.sha256(canonical_bytes(event)).hexdigest(),
        "input_sha256": event["final_checker_input_set_sha256"],
        "work_unit": event["unit"],
        "target_task": args.task,
        "consumer_phase": source["required_consumer_phase"],
        "document": {
            "kind": "correction-artifact",
            "workspace_path": str(WORKSPACE / document["path"]),
            "repository_path": resolved.get("repository_document"),
            "authority": resolved["authority"],
            "sha256": resolved["artifact_sha256"],
            "controller_sha256": document["controller_sha256"],
            "manifest_sha256": document["manifest_sha256"],
            "design_contract_sha256": document["design_contract_sha256"],
            "consumer_account_sha256": document["consumer_account_sha256"],
            "task_contract_sha256": document["task_contract_sha256"],
            "design_sha256": document["design_sha256"],
            "disagreement_sha256": document["disagreement_sha256"],
        },
        "current_design_proof_authority": event["design_proof_authority"],
        "prior_ids": prior_ids,
        "added_ids": added_ids,
        "next_ids": next_ids,
        "next_consumer_account_sha256": next_consumer,
        "next_task_contract_sha256": next_contract,
        "phase": "prepared",
    }
    return account


def validate_candidate(account):
    candidate = account.get("candidate_commit")
    tree = account.get("candidate_tree")
    head = account.get("input_head")
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(head)) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(tree)) \
            or candidate is not None and not re.fullmatch(r"[0-9a-f]{40,64}", str(candidate)):
        fail("the correction attempt failure candidate account is malformed")
    if git_output("rev-parse", f"{head}^{{commit}}") != head:
        fail("the correction attempt failure input commit is unavailable")
    if candidate is not None:
        if git_output("rev-parse", f"{candidate}^{{commit}}") != candidate \
                or git_output("rev-parse", f"{candidate}^{{tree}}") != tree:
            fail("the correction attempt failure candidate changed")
    snapshot = account.get("spare_snapshot_commit")
    if snapshot is not None:
        if git_output("rev-parse", f"{snapshot}^{{commit}}") != snapshot \
                or git_output("rev-parse", f"{snapshot}^{{tree}}") \
                != account.get("spare_snapshot_tree") \
                or candidate is None \
                or git_output("rev-parse", f"{candidate}^1") != snapshot:
            fail("the correction attempt spared-input snapshot changed")


def matching_terminals(entries, args, event):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == "attempt.failed" and entry.get("lot") == args.built
        and entry.get("correction") == args.round and entry.get("task") == args.task
        and progress.note_data(entry) == event
    ]


def attempt_terminals(entries, args):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") in {"attempt.failed", "attempt.succeeded", "paused", "aborted"}
        and entry.get("lot") == args.built
        and entry.get("correction") == args.round and entry.get("task") == args.task
        and progress.note_data(entry).get("attempt") == args.attempt
    ]


def require_matching_failure_terminal(terminals, args):
    if len(terminals) > 1:
        fail("the correction attempt has duplicate terminals")
    if terminals and (
        terminals[0][1].get("kind") != "attempt.failed"
        or progress.note_data(terminals[0][1]).get("classification") != args.classification
    ):
        fail("the correction attempt already has another terminal outcome")


def preserve_and_reset(account):
    candidate = account["candidate_commit"]
    try_ref = account["try_ref"]
    existing = run(
        "git", "-C", str(REPO), "rev-parse", "--verify", f"{try_ref}^{{commit}}",
        check=False,
    )
    if candidate is None:
        if existing.returncode == 0:
            fail("an untouched correction failure unexpectedly owns a try ref")
    elif existing.returncode == 0:
        if existing.stdout.strip() != candidate:
            fail("the correction attempt try ref names another candidate")
    else:
        update = run(
            "git", "-C", str(REPO), "update-ref", try_ref, candidate,
            "0" * len(candidate), check=False,
        )
        if update.returncode != 0:
            fail("the correction attempt try ref could not publish")

    head = git_output("rev-parse", "HEAD")
    spares = account.get("event", {}).get("spares", [])
    current_tree = temporary_index_tree(spares)
    if head == account["base_commit"] and current_tree == account["base_tree"]:
        return
    if current_tree != account["candidate_tree"] \
            or head not in {account["input_head"], candidate}:
        fail("the candidate tree changed after the failure owner was published")
    if candidate is not None:
        run("git", "-C", str(REPO), "reset", "-q", "--hard", candidate)
    run("git", "-C", str(REPO), "reset", "-q", "--hard", account["base_commit"])
    if git_output("rev-parse", "HEAD") != account["base_commit"] \
            or temporary_index_tree(spares) != account["base_tree"]:
        fail("the correction attempt did not return to its exact attempt base")


def failure_event(args):
    result = run(
        str(COMMON / "progress.py"), "construction-failure-check",
        args.built, str(args.task), str(args.attempt), args.classification,
    )
    try:
        event = json.loads(result.stdout)
    except ValueError as exc:
        fail(f"the correction failure account is malformed: {exc}")
    if event.get("schema") != 2 \
            or event.get("unit") != {
                "kind": "correction", "built": args.built, "round": args.round,
            }:
        fail("the failure checker did not return this Correction Round identity")
    return event


def derive_live(args):
    resolved = resolve_correction(args.built, args.round, args.task)
    attempt_payload, attempt_marker = read_attempt_marker()
    if attempt_marker.get("task") != args.task or attempt_marker.get("attempt") != args.attempt:
        fail("the correction attempt marker belongs to another attempt")
    event = failure_event(args)
    note = note_args(event, args.task)
    operation = operation_identity(event, args.task)
    static = derive_static(args, event, operation, attempt_payload, resolved)
    return {
        "resolved": resolved,
        "attempt_payload": attempt_payload,
        "attempt_marker": attempt_marker,
        "event": event,
        "note": note,
        "operation": operation,
        "static": static,
    }


def provisional_operation(args):
    marker_path = WORKSPACE / MARKER_NAME
    if marker_path.exists() or marker_path.is_symlink():
        _payload, account = read_marker()
        operation = account.get("operation")
        if not isinstance(operation, str):
            fail("the pending correction attempt failure has no operation identity")
        return operation
    entries = progress.journal_entries()
    terminals = attempt_terminals(entries, args)
    require_matching_failure_terminal(terminals, args)
    if terminals:
        event = progress.note_data(terminals[0][1])
        progress.validate_attempt_failed_entry(entries, terminals[0][0], terminals[0][1])
        return operation_identity(event, args.task)
    return derive_live(args)["operation"]


def completed_account(args, entries, terminal, attempt_payload, resolved):
    index, entry = terminal
    progress.validate_attempt_failed_entry(entries, index, entry)
    event = progress.note_data(entry)
    validate_completed_attempt_marker(
        args, entries, index, event, json.loads(attempt_payload), resolved,
        set_key="final_checker_input_set_sha256",
        assignments_key="final_checker_assignments",
    )
    operation = operation_identity(event, args.task)
    static = derive_static(args, event, operation, attempt_payload, resolved)
    return event, operation, static


def validate_completed_attempt_marker(
        args, entries, terminal_index, event, marker, resolved, *, set_key, assignments_key,
):
    unit = {"kind": "correction", "built": args.built, "round": args.round}
    required = {
        "schema", "unit", "unit_authority_sha256", "tree_authority", "task", "attempt",
        "attempt_predecessor", "document", "retry", "design_proof_authority",
        "outstanding_final_checker_set_sha256", "assigned_final_checker_obligations",
    }
    document = marker.get("document") if isinstance(marker, dict) else None
    task = resolved.get("task") or {}
    expected_document = {
        "path": resolved.get("workspace_document"),
        "manifest_sha256": resolved.get("task_manifest_sha256"),
        "controller_sha256": resolved.get("controller_sha256"),
        "design_contract_sha256": task.get("design_contract_sha256"),
        "consumer_account_sha256": task.get("consumer_account_sha256"),
        "task_contract_sha256": task.get("task_contract_sha256"),
        "design_sha256": document.get("design_sha256") if isinstance(document, dict) else None,
        "disagreement_sha256": document.get("disagreement_sha256")
        if isinstance(document, dict) else None,
    }
    tree_authority = marker.get("tree_authority") if isinstance(marker, dict) else None
    execution_authority_sha256 = hashlib.sha256(canonical_bytes({
        "schema": 1,
        "contract_authority": marker.get("unit_authority_sha256"),
        "tree_authority": tree_authority,
    })).hexdigest() if isinstance(marker, dict) else None
    predecessor = progress.correction_attempt_predecessor_account(
        entries, terminal_index, args.built, args.round, args.task,
        "the completed correction attempt predecessor",
    )
    if not isinstance(marker, dict) or set(marker) != required \
            or marker.get("schema") != 2 or marker.get("unit") != unit \
            or marker.get("task") != args.task or marker.get("attempt") != args.attempt \
            or marker.get("retry") != "-" or document != expected_document \
            or marker.get("unit_authority_sha256") != event.get("unit_authority_sha256") \
            or tree_authority != resolved.get("tree_authority") \
            or execution_authority_sha256 != event.get("execution_authority_sha256") \
            or marker.get("outstanding_final_checker_set_sha256") != event.get(set_key) \
            or marker.get("assigned_final_checker_obligations") \
            != event.get(assignments_key) \
            or marker.get("design_proof_authority") != event.get("design_proof_authority") \
            or marker.get("attempt_predecessor") != predecessor:
        fail("the completed correction attempt marker changes its frozen authority")
    base_ref = f"{resolved['ref_root']}/attempt-base"
    if git_output("rev-parse", "--verify", f"{base_ref}^{{commit}}") \
            != predecessor["commit"]:
        fail("the completed correction attempt has no exact frozen attempt-base ref")


def close(args):
    operation = provisional_operation(args)
    marker_path = WORKSPACE / MARKER_NAME

    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        resolved = resolve_correction(args.built, args.round, args.task)
        attempt_payload, attempt_marker = read_attempt_marker()
        if attempt_marker.get("task") != args.task \
                or attempt_marker.get("attempt") != args.attempt:
            fail("the correction attempt marker belongs to another attempt")
        entries = progress.journal_entries()
        existing_terminals = attempt_terminals(entries, args)
        require_matching_failure_terminal(existing_terminals, args)
        if existing_terminals:
            event, current_operation, static = completed_account(
                args, entries, existing_terminals[0], attempt_payload, resolved,
            )
            if current_operation != operation:
                fail("the correction attempt failure operation changed while waiting for authority")
            if marker_path.exists() or marker_path.is_symlink():
                marker_payload, account = read_marker()
                if any(account.get(key) != value for key, value in static.items()):
                    fail("the pending correction attempt failure changes its frozen account")
                validate_candidate(account)
                preserve_and_reset(account)
                remove_exact(
                    MARKER_NAME, marker_payload,
                    "the completed correction attempt failure owner",
                )
            if git_output("rev-parse", "HEAD") != static["base_commit"] \
                    or temporary_index_tree() != static["base_tree"]:
                fail("the recorded correction failure no longer has its exact reset tree")
            remove_exact(
                "attempt-in-flight", attempt_payload,
                "the completed correction attempt identity",
            )
            print(
                f"CORRECTION ATTEMPT FAILED {args.built} c{args.round} "
                f"task {args.task} (already recorded)"
            )
            return
        current = derive_live(args)
        if current["operation"] != operation:
            fail("the correction attempt failure operation changed while waiting for authority")
        resolved = current["resolved"]
        attempt_payload = current["attempt_payload"]
        attempt_marker = current["attempt_marker"]
        event = current["event"]
        note = current["note"]
        static = current["static"]
        if marker_path.exists() or marker_path.is_symlink():
            marker_payload, account = read_marker()
            if any(account.get(key) != value for key, value in static.items()):
                fail("the pending correction attempt failure changes its frozen account")
        else:
            ensure_no_foreign_owner()
            run_name = WORKSPACE.name
            feature = run_name[11:] if re.match(r"^\d{4}-\d{2}-\d{2}-", run_name) else run_name
            account = {
                **static,
                **candidate_account(
                    feature, args.built, args.task, args.attempt, static["base_commit"],
                ),
            }
            publish_marker(account)
            marker_payload = canonical_bytes(account) + b"\n"

        map_account = map_marker_account(
            args, event, attempt_payload, attempt_marker, resolved,
        )
        if map_account is not None:
            publish_final_map_marker(map_account)

        validate_candidate(account)
        terminals = matching_terminals(progress.journal_entries(), args, event)
        if len(terminals) > 1:
            fail("the correction attempt has duplicate failure terminals")
        if not terminals:
            preserve_and_reset(account)
            progress.cmd_note_with_lease(
                note, lease, operation, owner_marker=MARKER_NAME,
            )
            terminals = matching_terminals(progress.journal_entries(), args, event)
        if len(terminals) != 1:
            fail("the correction attempt failure terminal is unavailable")
        progress.validate_attempt_failed_entry(
            progress.journal_entries(), terminals[0][0], terminals[0][1],
        )
        preserve_and_reset(account)
        remove_exact(
            MARKER_NAME, marker_payload, "the completed correction attempt failure owner",
        )
        remove_exact(
            "attempt-in-flight", attempt_payload, "the completed correction attempt identity",
        )
    print(f"CORRECTION ATTEMPT FAILED {args.built} c{args.round} task {args.task}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("task", type=int)
    parser.add_argument("attempt", type=int)
    parser.add_argument("classification")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.task < 1 or args.attempt < 1 \
            or args.classification not in CLASSIFICATIONS:
        print("**correction failure ERROR** · malformed correction attempt identity", file=sys.stderr)
        raise SystemExit(1)
    try:
        close(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"**correction failure ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
