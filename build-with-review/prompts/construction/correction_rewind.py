#!/usr/bin/env python3
"""Rewind accepted Correction Round task refs under one composite authority."""

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
    content_object_path,
    publish_content_object,
    validate_content_object,
)
from correction_escalation import parse_rewind_blocker  # noqa: E402
from final_checker_obligations import escalation_item_for_member  # noqa: E402
from correction_round import merge_controller_projection  # noqa: E402
from work_unit import resolve_correction  # noqa: E402

MARKER_NAME = "correction-rewind-in-progress"
BLOCKING_MARKERS = {
    "amendment-commit-in-progress",
    "attempt-in-flight",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
    "correction-round-escalation-in-progress",
    "correction-product-authority-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "document-copy-in-progress",
    "gate-check-in-progress",
    "plan-commit-in-progress",
    "rewind-in-progress",
    "spec-breach-recovery-in-progress",
    "spec-commit-in-progress",
}


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


def note_args(event, task, *, kind="rewind.done"):
    return SimpleNamespace(
        kind=kind, mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def operation_identity(args):
    payload = {
        "kind": "correction-rewind",
        "built": args.built,
        "round": args.round,
        "earliest_task": args.earliest_task,
        "attempt": args.attempt,
        "cause_proof": args.cause_proof,
    }
    return "correction-rewind:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def publish_marker(account):
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction rewind owner",
    ) as anchored:
        anchored.publish(canonical_bytes(account) + b"\n")


def read_marker():
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction rewind owner",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the correction rewind owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the correction rewind owner is not canonical")
    return payload, account


def remove_marker(payload):
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the completed correction rewind owner",
    ) as anchored:
        anchored.remove_exact(hashlib.sha256(payload).hexdigest())


def temp_index_from(treeish):
    descriptor, path = tempfile.mkstemp(prefix=".correction-rewind-index-", dir=WORKSPACE)
    os.close(descriptor)
    os.unlink(path)
    environment = {**os.environ, "GIT_INDEX_FILE": path, "GIT_LITERAL_PATHSPECS": "1"}
    run("git", "-C", str(REPO), "read-tree", treeish, env=environment)
    return path, environment


def git_blob(commit, path):
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{commit}:{path}"],
        cwd=REPO, capture_output=True,
    )
    return None if result.returncode != 0 else result.stdout


def build_retained_transition_tree(transition, onto, artifact_path):
    paths = progress.retained_transition_paths(
        transition, "the correction rewind preflight",
    )
    index_path, environment = temp_index_from(onto)
    try:
        for path in paths:
            parent_payload = git_blob(transition["source_parent"], path)
            source_payload = git_blob(transition["source_commit"], path)
            target_payload = git_blob(onto, path)
            if path == artifact_path and source_payload is not None:
                result_payload = source_payload \
                    if target_payload is None or transition["kind"] == "revision" \
                    else merge_controller_projection(source_payload, target_payload)
                if result_payload is None:
                    return None
            elif target_payload != parent_payload and target_payload != source_payload:
                return None
            else:
                result_payload = source_payload
            if result_payload is None:
                run(
                    "git", "-C", str(REPO), "update-index", "--remove", "--", path,
                    env=environment,
                )
                continue
            hashed = subprocess.run(
                ["git", "-C", str(REPO), "hash-object", "-w", "--stdin"],
                cwd=REPO, capture_output=True, input=result_payload, env=environment,
            )
            if hashed.returncode != 0:
                fail("a retained transition blob could not publish")
            blob = hashed.stdout.decode().strip()
            mode = run(
                "git", "-C", str(REPO), "ls-tree", transition["source_commit"],
                "--", path,
            ).stdout.split(maxsplit=1)[0]
            if not re.fullmatch(r"[0-7]{6}", mode):
                fail("a retained transition has no exact source mode")
            run(
                "git", "-C", str(REPO), "update-index", "--add", "--cacheinfo",
                mode, blob, path, env=environment,
            )
        return git_output("write-tree", env=environment)
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass


def build_relands(crossed, base_commit, artifact_path, built, round_number, rewind):
    blocked = progress.retained_authority_failure(
        crossed, base_commit, artifact_path, "the correction rewind preflight",
    )
    if blocked is not None:
        return {"status": "blocked", "failed_transition": blocked}
    projected_trees = []
    onto_treeish = base_commit
    for transition in crossed:
        tree = build_retained_transition_tree(transition, onto_treeish, artifact_path)
        if tree is None:
            fail("the retained-authority writer contradicts its read-only preflight")
        projected_trees.append(tree)
        onto_treeish = tree
    relands = []
    onto = base_commit
    for transition, tree in zip(crossed, projected_trees, strict=True):
        subject = (
            f"{WORKSPACE.name} {built} correction {round_number} rewind {rewind} "
            f"— retain {transition['kind']}"
        )
        result = run(
            "git", "-C", str(REPO), "commit-tree", tree, "-p", onto,
            input_text=f"{subject}\n",
        ).stdout.strip()
        reland = {
            "authority": transition["proof"],
            "onto_commit": onto,
            "result_commit": result,
            "result_tree": tree,
            "transition_sha256": transition["transition_sha256"],
        }
        progress.validate_correction_reland(
            transition, reland, onto, "", "the correction rewind preflight",
        )
        relands.append(reland)
        onto = result
    return {
        "status": "ready", "relands": relands, "result_commit": onto,
        "result_tree": git_output("rev-parse", f"{onto}^{{tree}}"),
    }


def derive_account(args, operation):
    entries = progress.journal_entries()
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round, "the correction rewind",
    )
    cause_index, cause_entry = progress.journal_entry_from_proof(
        entries, args.cause_proof, "the correction rewind cause",
    )
    cause_data = progress.note_data(cause_entry)
    cause_kind = None
    if cause_entry.get("kind") == "attempt.failed":
        if cause_entry.get("lot") != args.built \
                or cause_entry.get("correction") != args.round \
                or cause_data.get("schema") != 2 \
                or cause_data.get("classification") != "C3.9c":
            fail("the correction rewind does not consume the exact current C3.9c failure")
        progress.validate_attempt_failed_entry(entries, cause_index, cause_entry)
        if cause_data.get("unit_authority_sha256") != state["authority_sha256"] \
                or cause_data.get("execution_authority_sha256") \
                != state["execution_authority_sha256"]:
            fail("the correction rewind failure is not under the current execution authority")
        cause_kind = "attempt-failure"
        latest_target_task = cause_entry.get("task", 0)
        accepted_at_cause = progress.accepted_correction_task_entries_at_prefix(
            entries, cause_index + 1, args.built, args.round, state["opening_index"],
        )
        accepted_by_task = {task: data for task, _index, data in accepted_at_cause}
    elif cause_entry.get("kind") == "amendment.committed":
        progress.validate_amendment_commit_entry(entries, cause_index, cause_entry)
        amendment = progress.correction_amendment_generation(
            entries, len(entries), state, "the correction rewind AMENDMENT",
        )
        opening_index, opening, commit_index, commit, _commit_proof = amendment
        opening_data = progress.note_data(opening)
        if commit_index != cause_index or commit != cause_entry \
                or opening_data.get("correction_authority") != state["proof"] \
                or opening_data.get("correction_execution_authority_sha256") \
                != state["execution_authority_sha256"]:
            fail("the correction rewind does not consume the current Correction AMENDMENT")
        accepted_at_cause = progress.accepted_correction_task_entries_at_prefix(
            entries, opening_index, args.built, args.round, state["opening_index"],
        )
        accepted_by_task = {task: data for task, _index, data in accepted_at_cause}
        latest_target_task = accepted_at_cause[-1][0] if accepted_at_cause else 0
        cause_kind = "amendment-rebase"
    else:
        fail("the correction rewind has an unsupported cause")
    resolved = resolve_correction(
        args.built, args.round,
        allow_active_amendment=cause_kind == "amendment-rebase",
    )
    later_boundaries = [
        entry for entry in entries[cause_index + 1:]
        if (
            entry.get("lot") == args.built and entry.get("correction") == args.round
            and entry.get("kind") in {
                "attempt.failed", "attempt.succeeded", "paused", "aborted", "rewind.done",
            }
        ) or (
            entry.get("kind") in {
                "correction.round.revised", "correction.round.built",
                "correction.round.resolved", "correction.round.escalated",
            }
            and progress.note_data(entry).get("built") == args.built
            and progress.note_data(entry).get("round") == args.round
        )
    ]
    if later_boundaries:
        fail("the correction rewind cause is no longer the current transition owner")
    if args.earliest_task > latest_target_task:
        fail("the correction rewind target follows its current accepted suffix")
    target_success = accepted_by_task.get(args.earliest_task)
    if target_success is None or target_success.get("attempt", 0) + 1 != args.attempt:
        fail("the correction rewind does not select the earliest accepted task retry")

    base_ref = f"{resolved['ref_root']}/task-{args.earliest_task - 1}"
    base_commit = git_output("rev-parse", "--verify", f"{base_ref}^{{commit}}")
    base_tree = git_output("rev-parse", f"{base_commit}^{{tree}}")
    rewind = state.get("rewind_ordinal", 0) + 1
    moved = []
    accepted_commits = {
        task: data["sha"] for task, _index, data in accepted_at_cause
    }
    for task in range(args.earliest_task, resolved["task_count"] + 1):
        source = f"{resolved['ref_root']}/task-{task}"
        found = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{source}^{{commit}}",
            check=False,
        )
        expected_commit = accepted_commits.get(task)
        if expected_commit is None:
            if found.returncode == 0:
                fail("the correction rewind found a stable ref outside its accepted prefix")
            continue
        if found.returncode != 0 or found.stdout.strip() != expected_commit:
            fail("the correction rewind accepted stable ref changed")
        moved.append({
            "task": task,
            "commit": expected_commit,
            "from": source,
            "to": f"{resolved['ref_root']}/rewound/r-{rewind}/task-{task}",
        })
    crossed = progress.retained_authority_chain(
        entries, len(entries), state, base_commit, "the correction rewind",
    )
    if cause_kind == "amendment-rebase":
        crossed.append(progress.correction_amendment_retained_transition(
            entries, len(entries), args.cause_proof, base_commit,
            "the correction rewind",
        ))
    preservation = build_relands(
        crossed, base_commit, state["path"], args.built, args.round, rewind,
    )
    if preservation["status"] == "blocked":
        accepted = progress.accepted_correction_task_entries_at_prefix(
            entries, len(entries), args.built, args.round, state["opening_index"],
        )
        completed = [{
            "task": task,
            "success": progress.journal_line_proof(success_index),
            "commit": success["sha"],
            "gate": success["gate"],
        } for task, success_index, success in accepted]
        current_commit = progress.correction_revision_parent(
            state, [(item["task"], item["commit"]) for item in completed],
            "the retained-authority rewind escalation",
        ) if completed else state["execution_commit"]
        current_tree = git_output("rev-parse", f"{current_commit}^{{tree}}")
        current_gate = state["execution_gate"] \
            if current_commit == state["execution_commit"] else completed[-1]["gate"]
        if not re.fullmatch(r"[0-9a-f]{64}", str(current_gate)):
            fail("the retained-authority escalation has no exact current gate")
        current_set = progress.outstanding_final_checker_set(
            entries, len(entries), args.built, args.round,
            "the retained-authority rewind escalation",
        )
        owner_base = {
            "schema": 1,
            "producer": "retained-authority-rewind",
            "built": args.built,
            "round": args.round,
            "opening": progress.journal_line_proof(state["opening_index"]),
            "latest_authority": state["proof"],
            "previous_rewind": state.get("rewind_proof"),
            "cause": args.cause_proof,
            "target": {
                "earliest_task": args.earliest_task,
                "base_ref": base_ref,
                "base_commit": base_commit,
                "base_tree": base_tree,
            },
            "crossed_authorities": crossed,
            "failed_transition": preservation["failed_transition"],
            "current_set_sha256": progress.final_checker_set_sha256(current_set),
            "completed": completed,
            "current_commit": current_commit,
            "current_tree": current_tree,
            "current_gate": current_gate,
            "artifact_sha256": state["artifact_sha256"],
            "artifact_object": state["artifact_object"],
            "current_authority_sha256": state["authority_sha256"],
            "current_execution_authority_sha256": state["execution_authority_sha256"],
        }
        owner_sha256 = hashlib.sha256(canonical_bytes(owner_base)).hexdigest()
        return {
            "schema": 1,
            "operation": operation,
            "disposition": "escalate",
            "phase": "blocker-required",
            "owner": owner_base,
            "owner_sha256": owner_sha256,
            "blocker_path": (
                f"corrections/{args.built}/"
                f"round-{args.round}-rewind-preservation.md"
            ),
        }
    relands = preservation["relands"]
    result_commit = preservation["result_commit"]
    result_tree = preservation["result_tree"]
    event_base = {
        "schema": 2,
        "unit": {"kind": "correction", "built": args.built, "round": args.round},
        "unit_authority_sha256": state["authority_sha256"],
        "cause": {"kind": cause_kind, "proof": args.cause_proof},
        "previous_rewind": state.get("rewind_proof"),
        "ref_root": resolved["ref_root"],
        "rewind": rewind,
        "target": {
            "earliest_task": args.earliest_task,
            "base_ref": base_ref,
            "base_commit": base_commit,
            "base_tree": base_tree,
        },
        "attempt": args.attempt,
        "moved": moved,
        "crossed_authorities": crossed,
        "relands": relands,
        "result_commit": result_commit,
        "result_tree": result_tree,
        "gate": None,
        "outstanding_retry_set_sha256": progress.final_checker_set_sha256(
            progress.outstanding_final_checker_set(
                entries, len(entries), args.built, args.round, "the correction rewind",
            )
        ),
    }
    phase = "baseline-required" if crossed else "terminal-ready"
    account = {
        "schema": 1,
        "operation": operation,
        "disposition": "rewind",
        "phase": phase,
        "event_base": event_base,
        "baseline_owner": (
            f"correction/{args.built}/c{args.round}/rewind-{rewind}/{result_commit}"
            if crossed else None
        ),
    }
    if not crossed:
        event = dict(event_base)
        event["pending_owner_sha256"] = progress.correction_rewind_pending_owner_sha256(event)
        account["event"] = event
    return account


def public_crossed_authorities(crossed):
    return [{
        "kind": item["kind"], "proof": item["proof"],
        "source_commit": item["source_commit"], "source_tree": item["source_tree"],
        "transition_sha256": item["transition_sha256"],
    } for item in crossed]


def derive_escalation_event(account):
    owner = account["owner"]
    built = owner["built"]
    correction = owner["round"]
    blocker_path = WORKSPACE / account["blocker_path"]
    payload = blocker_path.read_bytes()
    blocker = parse_rewind_blocker(
        blocker_path, expected_built=built, expected_round=correction,
    )
    expected_items = []
    entries = progress.journal_entries()
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction,
        "the retained-authority rewind escalation",
    )
    completed_tasks = [item["task"] for item in owner["completed"]]
    for finding, tasks in state["artifact"]["source_finding_coverage"].items():
        expected_items.append({
            "id": finding,
            "origin": f"correction/c{correction}/{finding}",
            "accepted_contributions": [task for task in tasks if task in completed_tasks],
        })
    failed = owner["failed_transition"]
    if blocker["owner_sha256"] != account["owner_sha256"] \
            or blocker["opening"] != owner["opening"] \
            or blocker["latest_authority"] != owner["latest_authority"] \
            or blocker["previous_rewind"] != owner["previous_rewind"] \
            or blocker["cause"] != owner["cause"] \
            or blocker["target_commit"] != owner["target"]["base_commit"] \
            or blocker["failed_transition"] != failed["proof"] \
            or blocker["failed_transition_sha256"] != failed["transition_sha256"] \
            or blocker["failure_reason"] != failed["reason"] \
            or blocker["current_commit"] != owner["current_commit"] \
            or blocker["current_tree"] != owner["current_tree"] \
            or blocker["current_gate"] != owner["current_gate"] \
            or blocker["items"] != expected_items:
        fail("the rewind preservation blocker changes its frozen owner account")
    digest = hashlib.sha256(payload).hexdigest()
    object_path = content_object_path(WORKSPACE, built, digest, ".md")
    blocker_account = {
        "artifact": account["blocker_path"], "sha256": digest,
        "object": str(object_path.relative_to(WORKSPACE)),
    }
    current = progress.outstanding_final_checker_set(
        entries, len(entries), built, correction,
        "the retained-authority rewind escalation",
    )
    if progress.final_checker_set_sha256(current) != owner["current_set_sha256"]:
        fail("the rewind preservation owner changes its final-checker set")
    coverage = state["artifact"]["source_finding_coverage"]
    item_accounts = [
        {"id": finding, "tasks": tasks}
        for finding, tasks in coverage.items()
    ]
    dispositions = []
    for member in current["entries"]:
        source = member["source"]
        try:
            escalation_item = escalation_item_for_member(member, item_accounts)
        except ValueError as exc:
            fail(f"the retained-authority escalation has no exact consumer item: {exc}")
        requirement = {
            "obligation_id": source["obligation_id"],
            "checker": source["checker"],
            "manifest_phase": source["required_consumer_phase"],
            "remaining_outcome": blocker["required_outcome"],
            "escalation_item": escalation_item,
        }
        dispositions.append({
            "obligation_id": source["obligation_id"], "outcome": "carried",
            "assignment": {
                "unit": {
                    "kind": "correction-escalation", "built": built,
                    "round": correction, "producer": "retained-authority-rewind",
                    "rewind_owner_sha256": account["owner_sha256"],
                },
                "task": None, "phase": "sublot-plan-consumer-map",
                "owner": "escalation-tail", "consumer_requirement": requirement,
            },
            "evidence": None,
        })
    retry_transition, _output = progress.materialize_final_checker_transition(
        current, additions=[], dispositions=dispositions,
        transfer_kind="retained-authority-escalation",
    )
    event = {
        "schema": 3, "producer": "retained-authority-rewind",
        "built": built, "round": correction, "route": "sublot",
        "opening": owner["opening"], "latest_authority": owner["latest_authority"],
        "previous_rewind": owner["previous_rewind"], "cause": owner["cause"],
        "target": owner["target"],
        "crossed_authorities": public_crossed_authorities(owner["crossed_authorities"]),
        "blocker": blocker_account,
        "completed_tasks": completed_tasks,
        "items": [{
            "id": item["id"], "origins": [item["origin"]],
            "accepted_contributions": item["accepted_contributions"],
            "blocker": blocker_account,
        } for item in expected_items],
        "commit": owner["current_commit"], "tree": owner["current_tree"],
        "gate": owner["current_gate"],
        "artifact_sha256": owner["artifact_sha256"],
        "artifact_object": owner["artifact_object"],
        "retry_transition": retry_transition,
    }
    return payload, event


def validate_marker(account, expected):
    if account != expected:
        fail("the pending correction rewind changes its complete frozen account")


def escalation_owner_matches_event(account, event):
    owner = account["owner"]
    expected = {
        "schema": 3,
        "producer": "retained-authority-rewind",
        "built": owner["built"],
        "round": owner["round"],
        "route": "sublot",
        "opening": owner["opening"],
        "latest_authority": owner["latest_authority"],
        "previous_rewind": owner["previous_rewind"],
        "cause": owner["cause"],
        "target": owner["target"],
        "crossed_authorities": public_crossed_authorities(owner["crossed_authorities"]),
        "completed_tasks": [item["task"] for item in owner["completed"]],
        "commit": owner["current_commit"],
        "tree": owner["current_tree"],
        "gate": owner["current_gate"],
        "artifact_sha256": owner["artifact_sha256"],
        "artifact_object": owner["artifact_object"],
    }
    return isinstance(event, dict) \
        and all(event.get(key) == value for key, value in expected.items()) \
        and isinstance(event.get("blocker"), dict) \
        and event["blocker"].get("artifact") == account["blocker_path"]


def validate_escalation_terminal_owner(account, event):
    owner = account["owner"]
    blocker_data = event.get("blocker") if isinstance(event, dict) else None
    if not isinstance(blocker_data, dict) or set(blocker_data) != {
        "artifact", "sha256", "object",
    }:
        fail("the retained-authority terminal has no exact immutable blocker")
    object_path = validate_content_object(
        WORKSPACE, owner["built"], blocker_data["sha256"], ".md",
    )
    blocker = parse_rewind_blocker(
        object_path, expected_built=owner["built"], expected_round=owner["round"],
    )
    if blocker_data["object"] != str(object_path.relative_to(WORKSPACE)) \
            or blocker.get("owner_sha256") != account["owner_sha256"]:
        fail("the retained-authority terminal belongs to another complete marker owner")


def escalation_terminal(account):
    entries = progress.journal_entries()
    matches = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == "correction.round.escalated"
        and escalation_owner_matches_event(account, progress.note_data(entry))
    ]
    if len(matches) > 1:
        fail("the retained-authority escalation has duplicate terminals")
    if matches:
        progress.validate_correction_round_escalated_entry(entries, *matches[0])
        validate_escalation_terminal_owner(account, progress.note_data(matches[0][1]))
        return matches[0]
    return None


def validate_escalation_marker(args, operation, account):
    if not isinstance(account, dict) or set(account) != {
        "schema", "operation", "disposition", "phase", "owner", "owner_sha256",
        "blocker_path",
    } or account.get("schema") != 1 or account.get("operation") != operation \
            or account.get("disposition") != "escalate" \
            or account.get("phase") != "blocker-required" \
            or account.get("blocker_path") != (
                f"corrections/{args.built}/round-{args.round}-rewind-preservation.md"
            ) \
            or account.get("owner_sha256") != hashlib.sha256(
                canonical_bytes(account.get("owner")),
            ).hexdigest():
        fail("the retained-authority escalation owner is malformed")
    if escalation_terminal(account) is not None:
        return
    expected = derive_account(args, operation)
    validate_marker(account, expected)


def finish_escalation(args, operation, lease, marker_payload, account):
    if escalation_terminal(account) is not None:
        remove_marker(marker_payload)
        print(f"CORRECTION ROUND ESCALATED {args.built} {args.round} (already recorded)")
        return
    blocker_path = WORKSPACE / account["blocker_path"]
    if not blocker_path.exists():
        print(
            "PRESERVATION BLOCKER REQUIRED\n"
            f"Write the exact retained-authority blocker to {blocker_path}, "
            "then rerun this command."
        )
        return
    blocker_payload, event = derive_escalation_event(account)
    published = publish_content_object(
        WORKSPACE, args.built, blocker_payload, ".md",
    )
    if str(published.relative_to(WORKSPACE)) != event["blocker"]["object"]:
        fail("the retained-authority escalation published another blocker object")
    entries = progress.journal_entries()
    matches = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == "correction.round.escalated"
        and progress.note_data(entry) == event
    ]
    if len(matches) > 1:
        fail("the retained-authority escalation has duplicate terminals")
    if not matches:
        progress.normalize_correction_round_escalated(
            entries, event, "the retained-authority rewind escalation",
        )
        progress.cmd_note_with_lease(
            note_args(event, None, kind="correction.round.escalated"),
            lease, operation, owner_marker=MARKER_NAME,
        )
    else:
        progress.validate_correction_round_escalated_entry(entries, *matches[0])
    remove_marker(marker_payload)
    print(f"CORRECTION ROUND ESCALATED {args.built} {args.round}")


def validate_pending_marker(args, operation, account):
    if isinstance(account, dict) and account.get("disposition") == "escalate":
        validate_escalation_marker(args, operation, account)
        return []
    required = {
        "schema", "operation", "disposition", "phase", "event_base", "baseline_owner",
    }
    if account.get("phase") == "terminal-ready":
        required.add("event")
    if not isinstance(account, dict) or set(account) != required \
            or account.get("schema") != 1 or account.get("operation") != operation \
            or account.get("disposition") != "rewind" \
            or account.get("phase") not in {"baseline-required", "terminal-ready"}:
        fail("the pending correction rewind owner is malformed")
    event = account.get("event") or account.get("event_base")
    if not isinstance(event, dict) or event.get("unit") != {
        "kind": "correction", "built": args.built, "round": args.round,
    } or not isinstance(event.get("cause"), dict) \
            or set(event["cause"]) != {"kind", "proof"} \
            or event["cause"].get("kind") not in {"attempt-failure", "amendment-rebase"} \
            or event["cause"].get("proof") != args.cause_proof \
            or event.get("target", {}).get("earliest_task") != args.earliest_task \
            or event.get("attempt") != args.attempt:
        fail("the pending correction rewind owner belongs to another call")
    entries = progress.journal_entries()
    def matches_terminal(entry):
        if entry.get("kind") != "rewind.done":
            return False
        data = progress.note_data(entry)
        if account.get("event") is not None:
            return data == account["event"]
        return {
            key: value for key, value in data.items()
            if key != "pending_owner_sha256"
        } | {"gate": None} == account["event_base"] \
            and data.get("pending_owner_sha256") \
            == progress.correction_rewind_pending_owner_sha256(data)

    terminals = [
        (index, entry) for index, entry in enumerate(entries)
        if matches_terminal(entry)
    ]
    if terminals:
        if len(terminals) != 1:
            fail("the pending correction rewind has duplicate terminals")
        progress.validate_correction_rewind_entry(entries, terminals[0][0], terminals[0][1])
        return terminals
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round, "the pending correction rewind",
    )
    crossed = event.get("crossed_authorities")
    phase = "baseline-required" if crossed else "terminal-ready"
    baseline_owner = (
        f"correction/{args.built}/c{args.round}/rewind-{event.get('rewind')}/"
        f"{event.get('result_commit')}"
        if crossed else None
    )
    if account.get("phase") != phase or account.get("baseline_owner") != baseline_owner:
        fail("the pending correction rewind changes its completion route")
    if phase == "baseline-required":
        if account.get("event") is not None or event.get("gate") is not None \
                or "pending_owner_sha256" in event:
            fail("the pending correction rewind invents a baseline terminal")
        pending_event = dict(event)
        pending_event["pending_owner_sha256"] = \
            progress.correction_rewind_pending_owner_sha256(pending_event)
    else:
        if account.get("event") is None or {
            key: value for key, value in event.items() if key != "pending_owner_sha256"
        } != account.get("event_base"):
            fail("the pending correction rewind changes its terminal event")
        pending_event = event
    candidate = {
        "kind": "rewind.done", "lot": args.built, "correction": args.round,
        "task": args.earliest_task, "data": pending_event,
    }
    progress.validate_correction_rewind_transition(
        entries + [candidate], len(entries), candidate, state,
        "the pending correction rewind", candidate=True, pending=True,
    )
    return []


def move_refs_and_tree(account):
    event = account.get("event") or account["event_base"]
    for member in event["moved"]:
        source = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{member['from']}^{{commit}}",
            check=False,
        )
        destination = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{member['to']}^{{commit}}",
            check=False,
        )
        if destination.returncode == 0 and destination.stdout.strip() != member["commit"]:
            fail("a rewound correction destination belongs to another commit")
        if destination.returncode != 0:
            if source.returncode != 0 or source.stdout.strip() != member["commit"]:
                fail("a correction stable ref changed before its rewind")
            update = run(
                "git", "-C", str(REPO), "update-ref", member["to"], member["commit"],
                "0" * len(member["commit"]), check=False,
            )
            if update.returncode != 0:
                fail("a correction rewound ref could not publish")
        if source.returncode == 0:
            deleted = run(
                "git", "-C", str(REPO), "update-ref", "-d", member["from"], member["commit"],
                check=False,
            )
            if deleted.returncode != 0:
                fail("a correction stable ref could not retire")
    head = git_output("rev-parse", "HEAD")
    status = git_output("status", "--porcelain")
    if head != event["result_commit"] or status:
        if status:
            fail("the correction rewind found an unexpected dirty tree")
        run("git", "-C", str(REPO), "reset", "-q", "--hard", event["result_commit"])
    if git_output("rev-parse", "HEAD") != event["result_commit"] \
            or git_output("rev-parse", "HEAD^{tree}") != event["result_tree"]:
        fail("the correction rewind did not reach its exact result tree")


def accepted_baseline(entries, account):
    event = account["event_base"]
    selected = run(
        "bash", str(HERE / "gate-check.sh"), "require-current",
        event["unit"]["built"], str(event["unit"]["round"]), check=False,
    )
    if selected.returncode != 0:
        return None
    operation = selected.stdout.strip()
    accepted = [
        progress.note_data(entry) for entry in entries
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
        and progress.note_data(entry).get("op") == operation
        and "unusable" not in progress.note_data(entry)
    ]
    if len(accepted) != 1 or accepted[0].get("scope") != "correction-baseline" \
            or accepted[0].get("owner") != account["baseline_owner"] \
            or accepted[0].get("head") != event["result_commit"] \
            or accepted[0].get("base") != event["result_commit"] \
            or accepted[0].get("green") is not True \
            or accepted[0].get("surface") != "unchanged":
        fail("the current gate is not the exact retained-authority rewind baseline")
    verified = run(
        "bash", str(HERE / "gate-check.sh"), "require-correction-baseline",
        operation, event["result_commit"], event["unit"]["built"],
        str(event["unit"]["round"]), check=False,
    )
    if verified.returncode != 0:
        fail(verified.stderr.strip() or verified.stdout.strip())
    return operation


def close(args):
    operation = operation_identity(args)
    marker_path = WORKSPACE / MARKER_NAME
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        current_entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            current_entries, len(current_entries), args.built, args.round,
            "the correction rewind",
        )
        _cause_index, cause_entry = progress.journal_entry_from_proof(
            current_entries, args.cause_proof, "the correction rewind cause",
        )
        if cause_entry.get("kind") != "amendment.committed":
            progress.require_no_active_correction_amendment(
                current_entries, len(current_entries), args.built, args.round,
                "the correction rewind",
            )
        if marker_path.exists() or marker_path.is_symlink():
            marker_payload, account = read_marker()
            terminals = validate_pending_marker(args, operation, account)
            if account["disposition"] == "escalate":
                finish_escalation(args, operation, lease, marker_payload, account)
                return
            if terminals:
                move_refs_and_tree(account)
                remove_marker(marker_payload)
                print(
                    f"CORRECTION REWOUND {args.built} c{args.round} "
                    f"from task {args.earliest_task} (already recorded)"
                )
                return
        else:
            ensure_no_foreign_owner()
            if git_output("status", "--porcelain"):
                fail("a fresh correction rewind requires one clean tree")
            account = derive_account(args, operation)
            if account["disposition"] == "escalate" \
                    and os.path.lexists(WORKSPACE / account["blocker_path"]):
                fail("the rewind preservation blocker path is already occupied")
            publish_marker(account)
            marker_payload = canonical_bytes(account) + b"\n"

        if account["disposition"] == "escalate":
            finish_escalation(args, operation, lease, marker_payload, account)
            return

        move_refs_and_tree(account)
        if account["phase"] == "baseline-required":
            gate = accepted_baseline(progress.journal_entries(), account)
            if gate is None:
                print(
                    "BASELINE REQUIRED\n"
                    f"Run correction-round-baseline.sh {args.built} {args.round}, "
                    "finish its exact baseline gate, then rerun this command."
                )
                return
            event = {**account["event_base"], "gate": gate}
            event["pending_owner_sha256"] = progress.correction_rewind_pending_owner_sha256(event)
            account = {**account, "event": event}

        event = account["event"]
        entries = progress.journal_entries()
        matches = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "rewind.done" and progress.note_data(entry) == event
        ]
        if len(matches) > 1:
            fail("the correction rewind has duplicate terminals")
        if not matches:
            progress.normalize_correction_rewind(
                entries, event,
                {"lot": args.built, "correction": args.round, "task": args.earliest_task},
                "the correction rewind",
            )
            progress.cmd_note_with_lease(
                note_args(event, args.earliest_task), lease, operation,
                owner_marker=MARKER_NAME,
            )
        entries = progress.journal_entries()
        matches = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "rewind.done" and progress.note_data(entry) == event
        ]
        if len(matches) != 1:
            fail("the correction rewind terminal is unavailable")
        progress.validate_correction_rewind_entry(entries, matches[0][0], matches[0][1])
        remove_marker(marker_payload)
    print(f"CORRECTION REWOUND {args.built} c{args.round} from task {args.earliest_task}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("earliest_task", type=int)
    parser.add_argument("attempt", type=int)
    parser.add_argument("cause_proof")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.earliest_task < 1 or args.attempt < 2 \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", args.cause_proof):
        print("**correction rewind ERROR** · malformed correction rewind identity", file=sys.stderr)
        raise SystemExit(1)
    cache_token = progress.CORRECTION_CONTRACT_STATE_CACHE.set({})
    try:
        try:
            close(args)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            print(f"**correction rewind ERROR** · {exc}", file=sys.stderr)
            raise SystemExit(1)
    finally:
        progress.CORRECTION_CONTRACT_STATE_CACHE.reset(cache_token)


if __name__ == "__main__":
    main()
