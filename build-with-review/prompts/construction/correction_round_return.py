#!/usr/bin/env python3
"""Return one committed AMENDMENT to its exact Correction Round authority."""

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
    WorkspaceFileAnchor,
    content_object_path,
    publish_content_object,
    replacement_recovery_relative_path,
    validate_content_object,
)
from correction_round import parse_artifact  # noqa: E402
from correction_escalation import parse_artifact as parse_escalation_artifact  # noqa: E402

MARKER_NAME = "correction-amendment-return-in-progress"
BLOCKING_MARKERS = {
    "amendment-commit-in-progress",
    "attempt-in-flight",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "correction-rewind-in-progress",
    "correction-round-escalation-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "document-copy-in-progress",
    "final-checker-contract-map-in-progress",
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


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def git_text(*arguments):
    result = subprocess.run(
        ["git", "-C", progress.project_root(), *arguments],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def operation_identity(route, built, correction, amendment, earliest_task):
    account = {
        "kind": "correction-amendment-return", "route": route,
        "built": built, "round": correction, "amendment": amendment,
        "earliest_task": earliest_task,
    }
    return "correction-amendment-return:" + sha256(canonical_bytes(account))


def ensure_no_foreign_owner():
    for name in sorted(BLOCKING_MARKERS):
        if os.path.lexists(WORKSPACE / name):
            fail(f"another workflow owner is unfinished: {name}")


def atomic_marker(path, account):
    try:
        payload = canonical_bytes(account) + b"\n"
        with WorkspaceFileAnchor(
            WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
            "the Correction AMENDMENT return owner",
        ) as marker:
            marker.publish(payload, mode=0o600)
        return payload
    except FileExistsError:
        fail("another Correction AMENDMENT return owner is pending")


def replace_marker(path, account, predecessor_payload=None):
    payload = canonical_bytes(account) + b"\n"
    with WorkspaceFileAnchor(
        WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
        "the Correction AMENDMENT return owner",
    ) as marker:
        current = marker.read_regular()
        if predecessor_payload is not None and current != predecessor_payload:
            fail("the Correction AMENDMENT return marker changed before its phase update")
        marker.replace_exact(sha256(current), payload, mode=0o600)
    return payload


def marker_recovery_generations(path):
    pattern = f".{path.name}.correction-recovery-*"
    generations = []
    for recovery_path in sorted(path.parent.glob(pattern)):
        with WorkspaceFileAnchor(
            WORKSPACE, recovery_path.relative_to(WORKSPACE).as_posix(),
            "a Correction AMENDMENT return marker recovery",
        ) as recovery:
            payload = recovery.read_regular()
        try:
            account = json.loads(payload)
        except (UnicodeError, ValueError) as exc:
            fail(f"a Correction AMENDMENT return marker recovery is malformed: {exc}")
        if canonical_bytes(account) + b"\n" != payload:
            fail("a Correction AMENDMENT return marker recovery is not canonical")
        expected = replacement_recovery_relative_path(
            path.relative_to(WORKSPACE).as_posix(), payload,
        )
        if recovery_path.relative_to(WORKSPACE).as_posix() != expected.as_posix():
            fail("a Correction AMENDMENT return marker recovery has another identity")
        generations.append((recovery_path, payload, account))
    return generations


def latest_marker_recovery(path, generations):
    ranks = {
        "prepared": 0,
        "baseline-required": 1,
        "return-required": 2,
        "escalation-required": 3,
        "terminal-ready": 4,
    }
    if not generations:
        fail("the Correction AMENDMENT return marker and recovery are absent")
    operations = {account.get("operation") for _, _, account in generations}
    if len(operations) != 1 or not next(iter(operations)):
        fail("the Correction AMENDMENT return marker recoveries have another owner")
    ranked = []
    for generation in generations:
        phase = generation[2].get("phase")
        if phase not in ranks:
            fail("a Correction AMENDMENT return marker recovery has another phase")
        ranked.append((ranks[phase], generation))
    highest = max(rank for rank, _ in ranked)
    matches = [generation for rank, generation in ranked if rank == highest]
    payloads = {payload for _, payload, _ in matches}
    if len(payloads) != 1:
        fail("the latest Correction AMENDMENT return marker recovery is ambiguous")
    return matches[0]


def read_marker_generation(path):
    try:
        generations = marker_recovery_generations(path)
        if not os.path.lexists(path):
            _, recovered_payload, _ = latest_marker_recovery(path, generations)
            with WorkspaceFileAnchor(
                WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
                "the recovered Correction AMENDMENT return owner",
            ) as marker:
                marker.publish(recovered_payload, mode=0o600)
        with WorkspaceFileAnchor(
            WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
            "the Correction AMENDMENT return owner",
        ) as marker:
            payload = marker.read_regular()
        account = json.loads(payload)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the Correction AMENDMENT return marker is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the Correction AMENDMENT return marker is not one canonical real file")
    if any(recovery_account.get("operation") != account.get("operation")
           for _, _, recovery_account in generations):
        fail("the Correction AMENDMENT return marker recovery has another owner")
    return payload, account


def read_marker(path):
    return read_marker_generation(path)[1]


def remove_marker(path, expected):
    payload = expected if isinstance(expected, bytes) else canonical_bytes(expected) + b"\n"
    generations = marker_recovery_generations(path)
    expected_account = json.loads(payload)
    if generations and not any(recovery_payload == payload
                               for _, recovery_payload, _ in generations):
        fail("the completed Correction AMENDMENT return has no exact recovery generation")
    if any(account.get("operation") != expected_account.get("operation")
           for _, _, account in generations):
        fail("the completed Correction AMENDMENT return recovery has another owner")
    with WorkspaceFileAnchor(
        WORKSPACE, path.relative_to(WORKSPACE).as_posix(),
        "the completed Correction AMENDMENT return owner",
    ) as marker:
        current = marker.read_regular()
        if current != payload:
            fail("the completed Correction AMENDMENT return marker changed before cleanup")
        marker.remove_exact(sha256(payload))
    for recovery_path, recovery_payload, _ in generations:
        with WorkspaceFileAnchor(
            WORKSPACE, recovery_path.relative_to(WORKSPACE).as_posix(),
            "a completed Correction AMENDMENT return marker recovery",
        ) as recovery:
            current = recovery.read_regular()
            if current != recovery_payload:
                fail("a completed Correction AMENDMENT return recovery changed before cleanup")
            recovery.remove_exact(sha256(recovery_payload))


def current_artifact(state, amendment_number, route, earliest_task):
    path = WORKSPACE / state["path"]
    payload = path.read_bytes()
    artifact = parse_artifact(
        path, expected_built=state["built"], expected_round=state["round"],
    )
    expected_state = {
        "rebase": "active", "resolved": "resolved", "sublot": "escalating",
    }[route]
    tasks = artifact.get("tasks")
    if artifact.get("state") != expected_state or artifact.get("schema") != 2 \
            or artifact.get("amendment") != amendment_number:
        fail("the Correction AMENDMENT return has no exact schema-2 artifact state")
    if route == "rebase" and (
        not isinstance(tasks, list) or not tasks or tasks[0].get("task") != earliest_task
    ):
        fail("the Correction AMENDMENT rebase changes its earliest task")
    if route == "resolved" and tasks != []:
        fail("the resolved Correction AMENDMENT return retains a runnable task")
    if route == "sublot" and tasks != []:
        fail("the escalated Correction AMENDMENT return retains a runnable task")
    return payload, artifact


def derive_static(entries, route, built, correction, amendment, earliest_task, operation):
    progress.require_no_current_correction_stop(
        entries, len(entries), built, correction, "the Correction AMENDMENT return",
    )
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction, "the Correction AMENDMENT return",
    )
    owner = progress.current_correction_amendment_owner(
        entries, len(entries), built, correction, "the Correction AMENDMENT return",
    )
    if owner is None:
        fail("the Correction AMENDMENT return has no active owner")
    opening_index, opening, commit_index, commit, commit_proof = (
        progress.correction_amendment_generation(
            entries, len(entries), state, "the Correction AMENDMENT return",
        )
    )
    opening_data = progress.note_data(opening)
    amendment_number = opening_data["amendment"]
    if amendment_number != amendment \
            or owner["opening"] != progress.journal_line_proof(opening_index) \
            or owner["commit"] != progress.journal_line_proof(commit_index):
        fail("the Correction AMENDMENT return names another amendment")
    current_set = progress.outstanding_final_checker_set(
        entries, len(entries), built, correction, "the Correction AMENDMENT return",
    )
    if progress.final_checker_set_sha256(current_set) \
            != opening_data["retry_transition"]["output_sha256"] \
            or any(member["assignment"].get("owner") != "amendment-return"
                   for member in current_set["entries"]):
        fail("the Correction AMENDMENT return changes its suspended checker set")
    tree_account = progress.correction_amendment_return_tree_account(
        entries, len(entries), state, opening_index, opening, commit_index,
        "the Correction AMENDMENT return",
    )
    pre_state = tree_account["pre_state"]
    payload, artifact = current_artifact(state, amendment_number, route, earliest_task)
    digest = sha256(payload)
    object_path = content_object_path(WORKSPACE, built, digest, ".md")
    commit_data = progress.note_data(commit)
    if artifact.get("amendment_opening") \
            != progress.journal_line_proof(opening_index) \
            or artifact.get("amendment_commit") \
            != progress.journal_line_proof(commit_index):
        fail("the Correction artifact changes its exact AMENDMENT generation")
    return {
        "schema": 1,
        "operation": operation,
        "route": route,
        "built": built,
        "round": correction,
        "amendment": amendment_number,
        "earliest_task": earliest_task,
        "opening": progress.journal_line_proof(opening_index),
        "committed": progress.journal_line_proof(commit_index),
        "amendment_commit": commit_data["sha"],
        "amendment_sha256": commit_data["amendment_sha256"],
        "spec_path": commit_proof["spec_path"],
        "spec_sha256": commit_data["spec_sha256"],
        "previous_authority": pre_state["proof"],
        "previous_execution_authority_sha256": pre_state["execution_authority_sha256"],
        "tree_transition": tree_account["tree_transition"],
        "return_parent": tree_account["return_parent"],
        "input_artifact_sha256": pre_state["artifact_sha256"],
        "input_artifact_object": pre_state["artifact_object"],
        "input_set_sha256": progress.final_checker_set_sha256(current_set),
        "document": state["path"],
        "artifact_sha256": artifact["artifact_sha256"],
        "artifact_object": str(object_path.relative_to(WORKSPACE)),
        "controller_sha256": artifact["controller_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
    }


def validate_marker(account, static):
    if not isinstance(account, dict) or any(account.get(key) != value
                                            for key, value in static.items()):
        fail("the pending Correction AMENDMENT return changes its frozen account")
    allowed = set(static) | {
        "phase", "commit", "tree", "baseline_owner", "gate", "return", "event",
    }
    if set(account) - allowed or account.get("phase") not in {
        "prepared", "baseline-required", "return-required", "escalation-required",
        "terminal-ready",
    }:
        fail("the pending Correction AMENDMENT return has a malformed phase")
    later = {key for key in ("commit", "tree", "baseline_owner", "gate", "return", "event")
             if key in account}
    expected = {
        "prepared": set(),
        "baseline-required": {"commit", "tree", "baseline_owner"},
        "return-required": {"commit", "tree", "baseline_owner", "gate"},
        "escalation-required": {"commit", "tree", "baseline_owner", "gate", "return"},
        "terminal-ready": {"commit", "tree", "baseline_owner", "gate", "return", "event"},
    }[account["phase"]]
    if later != expected:
        fail("the pending Correction AMENDMENT return crosses its durable phase")
    if account["phase"] != "prepared":
        if account.get("baseline_owner") != progress.correction_amendment_return_baseline_owner(
            account["built"], account["round"], account["amendment"], account.get("commit"),
        ) or not re.fullmatch(r"[0-9a-f]{40,64}", str(account.get("commit"))) \
                or not re.fullmatch(r"[0-9a-f]{40,64}", str(account.get("tree"))):
            fail("the pending Correction AMENDMENT return changes its document commit")
    if account["phase"] in {"return-required", "escalation-required", "terminal-ready"} \
            and not re.fullmatch(r"[0-9a-f]{64}", str(account.get("gate"))):
        fail("the pending Correction AMENDMENT return has no exact baseline")
    if account["phase"] == "terminal-ready" \
            and (not isinstance(account.get("return"), dict)
                 or not isinstance(account.get("event"), dict)):
        fail("the pending Correction AMENDMENT return has no exact terminal")


def document_commit_matches(account):
    head = git_text("rev-parse", "HEAD")
    if head == account["return_parent"]:
        return None
    parent = git_text("rev-parse", f"{head}^")
    names = git_text("diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines()
    result = subprocess.run(
        ["git", "-C", progress.project_root(), "show", f"{head}:{account['document']}"],
        capture_output=True,
    )
    if parent != account["return_parent"] or names != [account["document"]] \
            or result.returncode != 0 or sha256(result.stdout) != account["artifact_sha256"]:
        fail("HEAD is not the exact post-AMENDMENT Correction artifact commit")
    return head


def publish_document_commit(account):
    published = publish_content_object(
        WORKSPACE, account["built"], (WORKSPACE / account["document"]).read_bytes(), ".md",
    )
    if str(published.relative_to(WORKSPACE)) != account["artifact_object"]:
        fail("the Correction AMENDMENT return published another artifact object")
    document_copy = WORKSPACE / "prompts" / "common" / "document-copy.sh"
    existing = document_commit_matches(account)
    copied = subprocess.run(
        [document_copy, "copy", account["document"], account["document"], "replace"],
        cwd=progress.project_root(), capture_output=True, text=True,
    )
    if copied.returncode != 0:
        fail(copied.stderr.strip() or copied.stdout.strip())
    if existing is None:
        staged = subprocess.run(
            ["git", "-C", progress.project_root(), "add", "--", account["document"]],
            capture_output=True, text=True,
        )
        if staged.returncode != 0 \
                or git_text("diff", "--cached", "--name-only").splitlines() != [account["document"]]:
            fail("the Correction AMENDMENT return would commit another path")
        committed = subprocess.run(
            ["git", "-C", progress.project_root(), "-c", "core.hooksPath=/dev/null",
             "commit", "-q", "-m",
             f"docs(correction): {account['route']} amendment {account['amendment']} "
             f"for {account['built']}",
             "--", account["document"]],
            capture_output=True, text=True,
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
    if git_text("status", "--porcelain"):
        fail("the Correction AMENDMENT return document commit is not clean")
    return existing, git_text("rev-parse", f"{existing}^{{tree}}")


def accepted_baseline(entries, account):
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
        fail("the Correction AMENDMENT return has another baseline result")
    verified = subprocess.run(
        ["bash", progress.GATE_CHECK, "require-correction-baseline", matches[0]["op"],
         account["commit"], account["built"], str(account["round"])],
        capture_output=True, text=True,
    )
    if verified.returncode != 0:
        fail(verified.stderr.strip() or verified.stdout.strip())
    return matches[0]["op"]


def return_path(account):
    return WORKSPACE / "corrections" / account["built"] / (
        f"round-{account['round']}-amendment-{account['amendment']}-return.json"
    )


def validate_return_value(entries, account, value):
    state = progress.current_correction_contract_state(
        entries, len(entries), account["built"], account["round"],
        "the Correction AMENDMENT return",
    )
    input_set = progress.outstanding_final_checker_set(
        entries, len(entries), account["built"], account["round"],
        "the Correction AMENDMENT return",
    )
    artifact_path = validate_content_object(
        WORKSPACE, account["built"], account["artifact_sha256"], ".md",
    )
    if str(artifact_path.relative_to(WORKSPACE)) != account["artifact_object"]:
        fail("the Correction AMENDMENT return changes its correction artifact object")
    artifact = parse_artifact(
        artifact_path, expected_built=account["built"], expected_round=account["round"],
    )
    validator = progress.load_correction_amendment_return_validator()
    try:
        return validator.validate_return_account(
            value,
            previous_artifact=state["artifact"],
            current_artifact=artifact,
            input_set=input_set,
        )
    except ValueError as exc:
        fail(f"the Correction AMENDMENT return account is invalid: {exc}")


def consume_return(account):
    path = return_path(account)
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the Correction AMENDMENT return account is unavailable: {exc}")
    if canonical_bytes(value) + b"\n" != payload:
        fail("the Correction AMENDMENT return account is not canonical JSON")
    validate_return_value(progress.journal_entries(), account, value)
    published = publish_content_object(WORKSPACE, account["built"], payload, ".json")
    return {
        "artifact": str(path.relative_to(WORKSPACE)),
        "sha256": sha256(payload),
        "object": str(published.relative_to(WORKSPACE)),
    }


def derive_event(entries, account, reference):
    return_account = progress.immutable_correction_return_object(
        account["built"], reference, "the Correction AMENDMENT return",
    )
    if return_account.get("route") != account["route"]:
        fail("the immutable return account changes its frozen route")
    if account["route"] == "sublot":
        escalation_path = (
            WORKSPACE / "corrections" / account["built"]
            / f"round-{account['round']}-escalation.md"
        )
        artifact = parse_escalation_artifact(
            escalation_path, expected_built=account["built"], expected_round=account["round"],
        )
        state = progress.current_correction_contract_state(
            entries, len(entries), account["built"], account["round"],
            "the Correction AMENDMENT return",
        )
        correction_artifact_path = validate_content_object(
            WORKSPACE, account["built"], account["artifact_sha256"], ".md",
        )
        if str(correction_artifact_path.relative_to(WORKSPACE)) \
                != account["artifact_object"]:
            fail("the Correction AMENDMENT return changes its correction artifact object")
        correction_artifact = parse_artifact(
            correction_artifact_path,
            expected_built=account["built"], expected_round=account["round"],
        )
        confirmed = progress.correction_escalation_confirmed_account(
            entries, len(entries), state, "the Correction AMENDMENT return",
        )
        projection = progress.correction_post_amendment_escalation_projection(
            return_account, correction_artifact, artifact, confirmed, account["round"],
            "the Correction AMENDMENT return",
        )
        published = publish_content_object(
            WORKSPACE, account["built"], escalation_path.read_bytes(), ".md",
        )
        event = {
            "schema": 2, "producer": "post-amendment-return",
            "built": account["built"], "round": account["round"], "route": "sublot",
            "opening": artifact["opening"],
            "previous_authority": account["previous_authority"],
            "previous_execution_authority_sha256": account[
                "previous_execution_authority_sha256"
            ],
            "amendment": {"opening": account["opening"], "committed": account["committed"]},
            "return": reference,
            "completed_tasks": [
                item["task"] for item in return_account["accepted_contributions"]
                if item["outcome"] == "preserved"
            ],
            "items": projection["items"],
            "commit": account["commit"], "tree": account["tree"], "gate": account["gate"],
            "blocker": return_account["blocker"],
            "correction_artifact_sha256": account["artifact_sha256"],
            "correction_artifact_object": account["artifact_object"],
            "artifact": str(escalation_path.relative_to(WORKSPACE)),
            "artifact_sha256": artifact["artifact_sha256"],
            "artifact_object": str(published.relative_to(WORKSPACE)),
            "retry_transition": return_account["retry_transition"],
        }
        return progress.normalize_correction_round_escalated(
            entries, event, "the Correction AMENDMENT return",
        )
    if account["route"] == "resolved":
        event = {
            "schema": 1,
            "built": account["built"],
            "round": account["round"],
            "reason": "amendment-absorbed",
            "opening": None,
            "previous_authority": account["previous_authority"],
            "previous_execution_authority_sha256": account[
                "previous_execution_authority_sha256"
            ],
            "amendment": account["committed"],
            "return": reference,
            "accepted_contributions": [
                item["task"] for item in return_account["accepted_contributions"]
                if item["outcome"] == "preserved"
            ],
            "absorbed_findings": [
                item["id"] for item in return_account["findings"]
                if item["outcome"] == "absorbed"
            ],
            "commit": account["commit"],
            "tree": account["tree"],
            "gate": account["gate"],
            "artifact_sha256": account["artifact_sha256"],
            "artifact_object": account["artifact_object"],
            "retry_transition": return_account["retry_transition"],
        }
        state = progress.current_correction_contract_state(
            entries, len(entries), account["built"], account["round"],
            "the Correction AMENDMENT return",
        )
        event["opening"] = progress.journal_line_proof(state["opening_index"])
        event["generation_sha256"] = sha256(canonical_bytes(event))
        return progress.normalize_correction_round_resolved(
            entries, event, "the Correction AMENDMENT return",
        )
    candidate = {
        "schema": 1,
        "built": account["built"],
        "round": account["round"],
        "previous_authority": account["previous_authority"],
        "previous_execution_authority_sha256": account[
            "previous_execution_authority_sha256"
        ],
        "amendment": account["committed"],
        "return": reference,
        "commit": account["commit"],
        "tree": account["tree"],
        "gate": account["gate"],
        "artifact_sha256": account["artifact_sha256"],
        "artifact_object": account["artifact_object"],
        "controller_sha256": account["controller_sha256"],
        "rewind": return_account["tree_transition"]["rewind"],
    }
    candidate.update({
        "retry_transition": return_account["retry_transition"],
        "preserved_tasks": return_account["task_projection"]["preserved"],
        "earliest_task": return_account["task_projection"]["remaining"][0]["task"],
        "remaining_tasks": [item["task"] for item in return_account["task_projection"]["remaining"]],
    })
    return progress.normalize_correction_round_rebased(
        entries, candidate, "the Correction AMENDMENT return",
    )


def note_args(event):
    if event.get("producer") == "post-amendment-return":
        kind = "correction.round.escalated"
    elif "earliest_task" in event:
        kind = "correction.round.rebased"
    else:
        kind = "correction.round.resolved"
    return SimpleNamespace(
        kind=kind,
        mandate=None, task=None, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def terminal_kind(route):
    return {
        "rebase": "correction.round.rebased",
        "resolved": "correction.round.resolved",
        "sublot": "correction.round.escalated",
    }[route]


def validate_terminal_entry(entries, index, entry, kind):
    if kind == "correction.round.rebased":
        progress.validate_correction_round_rebased_entry(entries, index, entry)
    elif kind == "correction.round.resolved":
        progress.validate_correction_round_resolved_entry(entries, index, entry)
    else:
        progress.validate_correction_round_escalated_entry(entries, index, entry)


def recover_terminal_marker(entries, marker_path, marker_payload, account, args, operation):
    if account.get("phase") != "terminal-ready" or not isinstance(account.get("event"), dict):
        return False
    kind = terminal_kind(args.route)
    matches = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == kind and progress.note_data(entry) == account["event"]
    ]
    if len(matches) > 1:
        fail("the Correction AMENDMENT return terminal is duplicated")
    if not matches:
        return False
    index, entry = matches[0]
    static = derive_static(
        entries[:index], args.route, args.built, args.round, args.amendment,
        args.earliest_task, operation,
    )
    validate_marker(account, static)
    validate_terminal_entry(entries, index, entry, kind)
    remove_marker(marker_path, marker_payload)
    label = {"rebase": "REBASED", "resolved": "RESOLVED", "sublot": "ESCALATED"}[
        args.route
    ]
    print(f"CORRECTION ROUND {label} {args.built} {args.round} "
          f"after amendment {account['amendment']}")
    return True


def baseline_account(args):
    marker = read_marker(WORKSPACE / MARKER_NAME)
    operation = marker.get("operation")
    static = derive_static(
        progress.journal_entries(), marker.get("route"), args.built, args.round,
        marker.get("amendment"), marker.get("earliest_task"), operation,
    )
    validate_marker(marker, static)
    if marker["phase"] not in {
        "baseline-required", "return-required", "escalation-required", "terminal-ready",
    }:
        fail("the Correction AMENDMENT return has no document commit for a baseline")
    if git_text("rev-parse", "HEAD") != marker["commit"] \
            or git_text("rev-parse", "HEAD^{tree}") != marker["tree"] \
            or git_text("status", "--porcelain"):
        fail("the Correction AMENDMENT return baseline is not its clean document commit")
    return marker


def run(args):
    marker_path = WORKSPACE / MARKER_NAME
    operation = operation_identity(
        args.route, args.built, args.round, args.amendment, args.earliest_task,
    )
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        entries = progress.journal_entries()
        recoveries = marker_recovery_generations(marker_path)
        marker_payload, account = (
            read_marker_generation(marker_path)
            if os.path.lexists(marker_path) or recoveries else (None, None)
        )
        if account is not None and recover_terminal_marker(
            entries, marker_path, marker_payload, account, args, operation,
        ):
            return
        static = derive_static(
            entries, args.route, args.built, args.round, args.amendment,
            args.earliest_task, operation,
        )
        if account is not None:
            validate_marker(account, static)
        else:
            ensure_no_foreign_owner()
            if git_text("status", "--porcelain"):
                fail("the Correction AMENDMENT return requires one clean project tree")
            if git_text("rev-parse", "HEAD") != static["return_parent"]:
                fail("the Correction AMENDMENT return is not on its exact retained tree")
            account = {**static, "phase": "prepared"}
            marker_payload = atomic_marker(marker_path, account)

        if account["phase"] == "prepared":
            commit, tree = publish_document_commit(account)
            account = {
                **account,
                "phase": "baseline-required",
                "commit": commit,
                "tree": tree,
                "baseline_owner": progress.correction_amendment_return_baseline_owner(
                    account["built"], account["round"], account["amendment"], commit,
                ),
            }
            marker_payload = replace_marker(marker_path, account, marker_payload)
        if account["phase"] == "baseline-required":
            gate = accepted_baseline(progress.journal_entries(), account)
            if gate is None:
                print(
                    "BASELINE REQUIRED\n"
                    f"Run correction-round-baseline.sh {args.built} {args.round}, "
                    "finish its exact baseline gate, then rerun this command."
                )
                return
            account = {**account, "phase": "return-required", "gate": gate}
            marker_payload = replace_marker(marker_path, account, marker_payload)
        if account["phase"] == "return-required":
            path = return_path(account)
            if not path.exists() and not path.is_symlink():
                print(
                    "RETURN ACCOUNT REQUIRED\n"
                    f"Write the canonical return account to {path}, then rerun this command."
                )
                return
            reference = consume_return(account)
            return_account = progress.immutable_correction_return_object(
                account["built"], reference, "the Correction AMENDMENT return",
            )
            if return_account.get("route") != account["route"]:
                fail("the immutable return account changes its frozen route")
            if account["route"] == "sublot":
                account = {
                    **account, "phase": "escalation-required", "return": reference,
                }
            else:
                event = derive_event(progress.journal_entries(), account, reference)
                account = {
                    **account, "phase": "terminal-ready", "return": reference, "event": event,
                }
            marker_payload = replace_marker(marker_path, account, marker_payload)
        if account["phase"] == "escalation-required":
            escalation_path = (
                WORKSPACE / "corrections" / account["built"]
                / f"round-{account['round']}-escalation.md"
            )
            if not escalation_path.exists() and not escalation_path.is_symlink():
                print(
                    "ESCALATION ARTIFACT REQUIRED\n"
                    f"Write the exact escalation artifact to {escalation_path}, "
                    "then rerun this command."
                )
                return
            event = derive_event(progress.journal_entries(), account, account["return"])
            account = {**account, "phase": "terminal-ready", "event": event}
            marker_payload = replace_marker(marker_path, account, marker_payload)
        event = account["event"]
        entries = progress.journal_entries()
        event_kind = terminal_kind(args.route)
        matches = [(index, entry) for index, entry in enumerate(entries)
                   if entry.get("kind") == event_kind
                   and progress.note_data(entry) == event]
        if len(matches) > 1:
            fail("the Correction AMENDMENT return terminal is duplicated")
        if matches:
            validate_terminal_entry(entries, *matches[0], event_kind)
        else:
            if event_kind == "correction.round.rebased":
                progress.normalize_correction_round_rebased(
                    entries, event, "the Correction AMENDMENT return",
                )
            elif event_kind == "correction.round.resolved":
                progress.normalize_correction_round_resolved(
                    entries, event, "the Correction AMENDMENT return",
                )
            else:
                progress.normalize_correction_round_escalated(
                    entries, event, "the Correction AMENDMENT return",
                )
            progress.cmd_note_with_lease(
                note_args(event), lease, operation, owner_marker=MARKER_NAME,
            )
        remove_marker(marker_path, marker_payload)
        terminal_label = {
            "rebase": "REBASED", "resolved": "RESOLVED", "sublot": "ESCALATED",
        }[args.route]
        print(f"CORRECTION ROUND {terminal_label} {args.built} {args.round} "
              f"after amendment {account['amendment']}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("route", choices=("rebase", "resolved", "sublot"))
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("amendment", type=int)
    parser.add_argument("earliest_task", type=int, nargs="?")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1 \
            or isinstance(args.amendment, bool) or args.amendment < 1 \
            or (args.route == "rebase" and (
                isinstance(args.earliest_task, bool) or not isinstance(args.earliest_task, int)
                or args.earliest_task < 1
            )) or (args.route in {"resolved", "sublot"} and args.earliest_task is not None):
        fail("the Correction AMENDMENT return arguments are malformed")
    return args


def main():
    cache_token = progress.CORRECTION_CONTRACT_STATE_CACHE.set({})
    try:
        try:
            run(parse_args())
        except (OSError, ValueError) as exc:
            print(f"**correction return ERROR** · {exc}", file=sys.stderr)
            raise SystemExit(1)
    finally:
        progress.CORRECTION_CONTRACT_STATE_CACHE.reset(cache_token)


if __name__ == "__main__":
    main()
