#!/usr/bin/env python3
"""Canonical post-AMENDMENT Correction Round return accounts."""

import copy
import pathlib
import re

from final_checker_obligations import escalation_item_for_member, validate_transition


HASH_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
PROOF_RE = re.compile(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}")
FINDING_RE = re.compile(r"F[1-9][0-9]*")
LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
RETURN_KEYS = {
    "schema", "built", "round", "previous_authority",
    "previous_execution_authority_sha256", "amendment", "tree_transition",
    "input_artifact", "current", "findings", "task_projection",
    "accepted_contributions", "blocker", "required_sublot_outcome",
    "retry_transition", "route",
}
AMENDMENT_KEYS = {
    "opening", "committed", "artifact_sha256", "spec_path", "spec_sha256",
}
TREE_TRANSITION_KEYS = {"pre_amendment_rewind", "rewind", "reland"}
INPUT_ARTIFACT_KEYS = {"sha256", "object"}
CURRENT_KEYS = {"artifact_sha256", "artifact_object", "commit", "tree", "gate"}
FINDING_KEYS = {"id", "outcome", "amendment_item"}
TASK_PROJECTION_KEYS = {"preserved", "removed", "remaining"}
REMOVED_TASK_KEYS = {"task", "reason"}
REMAINING_TASK_KEYS = {"task", "prior_tasks", "findings"}
CONTRIBUTION_KEYS = {"task", "success", "commit", "gate", "outcome", "rewind"}


def require_exact_keys(value, keys, subject):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{subject} does not have its exact fields")


def require_hash(value, subject):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{subject} is not one exact SHA-256")


def require_commit(value, subject):
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise ValueError(f"{subject} is not one exact commit")


def require_proof(value, subject):
    if not isinstance(value, str) or not PROOF_RE.fullmatch(value):
        raise ValueError(f"{subject} is not one exact journal proof")


def require_positive(value, subject):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{subject} is not one positive integer")


def require_sorted_positive(values, subject, *, prefix=False):
    if not isinstance(values, list):
        raise ValueError(f"{subject} is not one list")
    for value in values:
        require_positive(value, f"{subject} member")
    if values != sorted(set(values)):
        raise ValueError(f"{subject} is not sorted and unique")
    if prefix and values != list(range(1, len(values) + 1)):
        raise ValueError(f"{subject} is not one exact prefix")


def content_object_path(built, digest, suffix):
    return f"corrections/{built}/objects/sha256-{digest}{suffix}"


def validate_amendment(value, current_artifact):
    require_exact_keys(value, AMENDMENT_KEYS, "the correction AMENDMENT return authority")
    require_proof(value["opening"], "the correction AMENDMENT opening")
    require_proof(value["committed"], "the correction AMENDMENT commit")
    require_hash(value["artifact_sha256"], "the accepted AMENDMENT artifact")
    require_hash(value["spec_sha256"], "the amended specification")
    spec_path = value["spec_path"]
    if not isinstance(spec_path, str) or not spec_path \
            or pathlib.PurePosixPath(spec_path).is_absolute() \
            or pathlib.PurePosixPath(spec_path).as_posix() != spec_path \
            or ".." in pathlib.PurePosixPath(spec_path).parts:
        raise ValueError("the correction AMENDMENT return has no exact specification path")
    if value["opening"] != current_artifact.get("amendment_opening") \
            or value["committed"] != current_artifact.get("amendment_commit"):
        raise ValueError("the correction artifact changes its AMENDMENT generation")


def validate_tree_transition(value):
    require_exact_keys(value, TREE_TRANSITION_KEYS, "the correction return tree transition")
    for key in TREE_TRANSITION_KEYS:
        if value[key] is not None:
            require_proof(value[key], f"the correction return {key}")
    if value["reland"] is not None:
        raise ValueError("the current correction return schema has no separate re-land producer")


def validate_artifact_accounts(value, previous_artifact, current_artifact, built, round_number):
    require_exact_keys(
        value["input_artifact"], INPUT_ARTIFACT_KEYS,
        "the correction return input artifact",
    )
    input_digest = value["input_artifact"]["sha256"]
    require_hash(input_digest, "the correction return input artifact")
    if input_digest != previous_artifact.get("artifact_sha256") \
            or value["input_artifact"]["object"] \
            != content_object_path(built, input_digest, ".md"):
        raise ValueError("the correction return changes its input artifact")

    require_exact_keys(value["current"], CURRENT_KEYS, "the current correction return state")
    current_digest = value["current"]["artifact_sha256"]
    require_hash(current_digest, "the current correction artifact")
    require_commit(value["current"]["commit"], "the correction return commit")
    require_commit(value["current"]["tree"], "the correction return tree")
    require_hash(value["current"]["gate"], "the correction return gate")
    if current_digest != current_artifact.get("artifact_sha256") \
            or value["current"]["artifact_object"] \
            != content_object_path(built, current_digest, ".md"):
        raise ValueError("the correction return changes its current artifact")

    stable_fields = (
        "built", "round", "identity", "source_findings_path",
        "source_findings_sha256", "source_findings", "source_finding_coverage", "route",
    )
    if previous_artifact.get("built") != built or previous_artifact.get("round") != round_number \
            or current_artifact.get("built") != built \
            or current_artifact.get("round") != round_number \
            or any(previous_artifact.get(key) != current_artifact.get(key)
                   for key in stable_fields):
        raise ValueError("the correction return changes stable controller authority")
    if current_artifact.get("schema") != 2:
        raise ValueError("the post-AMENDMENT correction artifact is not schema 2")


def validate_findings(value, previous_artifact, current_artifact):
    if not isinstance(value, list):
        raise ValueError("the correction return finding account is not one list")
    expected_ids = previous_artifact.get("source_findings")
    if not isinstance(expected_ids, list) or len(value) != len(expected_ids):
        raise ValueError("the correction return finding partition is incomplete")
    normalized = []
    absorbed = {}
    remaining = []
    for expected_id, item in zip(expected_ids, value, strict=True):
        require_exact_keys(item, FINDING_KEYS, "a correction return finding")
        if item["id"] != expected_id or not FINDING_RE.fullmatch(str(item["id"])):
            raise ValueError("the correction return finding order changed")
        if item["outcome"] == "remaining":
            if item["amendment_item"] is not None:
                raise ValueError("a remaining correction finding names an AMENDMENT item")
            remaining.append(item["id"])
        elif item["outcome"] == "absorbed":
            require_proof(item["amendment_item"], "an absorbed correction finding")
            absorbed[item["id"]] = item["amendment_item"]
        else:
            raise ValueError("a correction return finding has an unknown outcome")
        normalized.append(copy.deepcopy(item))
    if absorbed != current_artifact.get("absorbed_findings") \
            or remaining != list(current_artifact.get("finding_coverage", {})):
        raise ValueError("the correction return and artifact finding partitions disagree")
    return normalized, set(absorbed), remaining


def active_previous_tasks(previous_artifact):
    tasks = {
        task.get("task") for task in previous_artifact.get("tasks", [])
        if isinstance(task, dict)
    }
    tasks.update(
        item.get("task") for item in previous_artifact.get("accepted_contributions", [])
        if isinstance(item, dict)
    )
    if any(not isinstance(task, int) or isinstance(task, bool) or task < 1 for task in tasks):
        raise ValueError("the pre-AMENDMENT correction task account is malformed")
    return tasks


def validate_task_projection(value, previous_artifact, current_artifact,
                             absorbed_findings, route):
    require_exact_keys(value, TASK_PROJECTION_KEYS, "the correction return task projection")
    preserved = value["preserved"]
    require_sorted_positive(preserved, "the preserved correction tasks", prefix=True)

    removed = value["removed"]
    if not isinstance(removed, list):
        raise ValueError("the removed correction task account is not one list")
    removed_tasks = []
    previous_by_task = {
        item["task"]: item for item in previous_artifact.get("tasks", [])
        if isinstance(item, dict) and isinstance(item.get("task"), int)
    }
    for item in removed:
        require_exact_keys(item, REMOVED_TASK_KEYS, "a removed correction task")
        require_positive(item["task"], "a removed correction task")
        if item["reason"] not in {"absorbed", "structural-escalation"}:
            raise ValueError("a removed correction task has an unknown reason")
        if item["reason"] == "structural-escalation" and route != "sublot":
            raise ValueError("a bounded correction return claims structural task removal")
        prior = previous_by_task.get(item["task"])
        if item["reason"] == "absorbed" and (
            prior is None or not set(prior.get("covers", [])).issubset(absorbed_findings)
        ):
            raise ValueError("an absorbed task still owns a remaining finding")
        removed_tasks.append(item["task"])
    if removed_tasks != sorted(set(removed_tasks)):
        raise ValueError("the removed correction tasks are not sorted and unique")

    remaining = value["remaining"]
    if not isinstance(remaining, list):
        raise ValueError("the remaining correction task projection is not one list")
    projected_tasks = []
    projected_prior = set()
    for expected_task, item in enumerate(remaining, len(preserved) + 1):
        require_exact_keys(item, REMAINING_TASK_KEYS, "a remaining correction task")
        if item["task"] != expected_task:
            raise ValueError("the remaining correction tasks are not one exact suffix")
        require_sorted_positive(item["prior_tasks"], "the prior correction task account")
        if not item["prior_tasks"]:
            raise ValueError("a remaining correction task owns no prior task")
        findings = item["findings"]
        if not isinstance(findings, list) or not findings \
                or any(not isinstance(finding, str) or not FINDING_RE.fullmatch(finding)
                       for finding in findings) \
                or findings != sorted(set(findings), key=lambda identity: int(identity[1:])):
            raise ValueError("a remaining correction task has an invalid finding account")
        projected_tasks.append(item["task"])
        projected_prior.update(item["prior_tasks"])

    preserved_set = set(preserved)
    removed_set = set(removed_tasks)
    if preserved_set & removed_set or preserved_set & projected_prior \
            or removed_set & projected_prior \
            or preserved_set | removed_set | projected_prior \
            != active_previous_tasks(previous_artifact):
        raise ValueError("the correction return task projection is not exhaustive")

    artifact_projection = current_artifact.get("task_projection")
    expected_artifact_projection = {
        "preserved": preserved,
        "removed": removed_tasks,
        "remaining": remaining,
    }
    if artifact_projection != expected_artifact_projection:
        raise ValueError("the correction return and artifact task projections disagree")
    current_tasks = current_artifact.get("tasks")
    if not isinstance(current_tasks, list) \
            or [task.get("task") for task in current_tasks] != projected_tasks \
            or any(task["covers"] != projected["findings"]
                   for task, projected in zip(current_tasks, remaining, strict=True)):
        raise ValueError("the runnable task graph changes its return projection")
    return copy.deepcopy(value)


def validate_contributions(value, current_artifact, projection):
    if not isinstance(value, list):
        raise ValueError("the accepted correction contribution account is not one list")
    tasks = []
    for item in value:
        require_exact_keys(item, CONTRIBUTION_KEYS, "an accepted correction contribution")
        require_positive(item["task"], "an accepted correction contribution task")
        require_proof(item["success"], "an accepted correction contribution success")
        require_commit(item["commit"], "an accepted correction contribution commit")
        require_hash(item["gate"], "an accepted correction contribution gate")
        if item["outcome"] == "preserved":
            if item["rewind"] is not None:
                raise ValueError("a preserved correction contribution names a rewind")
        elif item["outcome"] == "rewound":
            require_proof(item["rewind"], "a rewound correction contribution")
        else:
            raise ValueError("an accepted correction contribution has an unknown outcome")
        tasks.append(item["task"])
    if tasks != sorted(set(tasks)):
        raise ValueError("the accepted correction contributions are not sorted and unique")
    if value != current_artifact.get("accepted_contributions"):
        raise ValueError("the return and artifact contribution accounts disagree")
    preserved = [item["task"] for item in value if item["outcome"] == "preserved"]
    if preserved != projection["preserved"]:
        raise ValueError("the preserved task and contribution accounts disagree")
    return copy.deepcopy(value)


def validate_rebased_task_obligations(output, current_artifact):
    tasks = current_artifact.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("the rebased correction artifact has no exact task account")
    expected = {}
    for task in tasks:
        task_number = task.get("task") if isinstance(task, dict) else None
        if not isinstance(task_number, int) or isinstance(task_number, bool) \
                or task_number < 1 or task_number in expected:
            raise ValueError("the rebased correction artifact has a malformed task account")
        expected[task_number] = []
    for member in output["entries"]:
        assignment = member["assignment"]
        task_number = assignment.get("task")
        if assignment.get("owner") != "task" or task_number not in expected:
            raise ValueError("the rebased obligation has no exact task consumer")
        if assignment.get("phase") != member["source"].get("required_consumer_phase"):
            raise ValueError("the rebased obligation changes its required consumer phase")
        expected[task_number].append(member["source"]["obligation_id"])
    if any(task.get("obligation_ids") != expected[task["task"]] for task in tasks):
        raise ValueError("the rebased task obligation projection is not exhaustive")
    return copy.deepcopy(expected)


def validate_retry_transition(
        value, input_set, route, current_artifact, absorbed_items,
        *, amendment_commit=None, required_sublot_outcome=None, remaining_findings=None,
):
    if not isinstance(value, dict) or value.get("additions") != []:
        raise ValueError("the correction return transition adds a final-checker source")
    output = validate_transition(input_set, value, transfer_kind="amendment-return")
    dispositions = value.get("dispositions")
    if route == "rebase":
        tasks = {task["task"]: task for task in current_artifact["tasks"]}
        for disposition in dispositions:
            assignment = disposition.get("assignment")
            obligation_id = disposition.get("obligation_id")
            if disposition.get("outcome") != "deferred" \
                    or disposition.get("evidence") is not None \
                    or not isinstance(assignment, dict) \
                    or assignment.get("owner") != "task" \
                    or assignment.get("unit") != {
                        "kind": "correction",
                        "built": current_artifact["built"],
                        "round": current_artifact["round"],
                    }:
                raise ValueError("the rebased return has a non-task disposition")
            task = tasks.get(assignment.get("task"))
            if task is None or assignment.get("task_contract_sha256") \
                    != task["task_contract_sha256"] \
                    or obligation_id not in task["obligation_ids"]:
                raise ValueError("the rebased obligation has no exact task consumer")
        validate_rebased_task_obligations(output, current_artifact)
    elif route == "resolved":
        if any(
            disposition.get("outcome") != "absorbed"
            or disposition.get("assignment") is not None
            or not isinstance(disposition.get("evidence"), dict)
            or set(disposition["evidence"]) != {"amendment_item"}
            or disposition["evidence"].get("amendment_item") not in absorbed_items
            for disposition in dispositions
        ):
            raise ValueError("the resolved return retains a final-checker obligation")
        if output != {"schema": 1, "entries": []}:
            raise ValueError("the resolved return does not produce the empty set")
    else:
        input_by_id = {
            entry["source"]["obligation_id"]: entry for entry in input_set["entries"]
        }
        coverage = current_artifact.get("source_finding_coverage")
        if not isinstance(remaining_findings, list) or not isinstance(coverage, dict):
            raise ValueError("the structural return has no exact escalation item account")
        item_accounts = []
        for ordinal, finding in enumerate(remaining_findings, 1):
            tasks = coverage.get(finding)
            if not isinstance(tasks, list):
                raise ValueError("the structural return has a foreign remaining finding")
            item_accounts.append({"id": f"F{ordinal}", "tasks": tasks})
        for disposition in dispositions:
            assignment = disposition.get("assignment")
            obligation_id = disposition.get("obligation_id")
            member = input_by_id.get(obligation_id)
            source = member.get("source", {}) if isinstance(member, dict) else {}
            requirement = assignment.get("consumer_requirement") \
                if isinstance(assignment, dict) else None
            escalation_item = escalation_item_for_member(member, item_accounts)
            if disposition.get("outcome") != "carried" \
                    or disposition.get("evidence") is not None \
                    or not isinstance(assignment, dict) \
                    or assignment.get("owner") != "escalation-tail" \
                    or assignment.get("unit") != {
                        "kind": "correction-escalation",
                        "built": current_artifact["built"],
                        "round": current_artifact["round"],
                        "producer": "post-amendment-return",
                        "amendment": amendment_commit,
                    } \
                    or not isinstance(requirement, dict) \
                    or requirement.get("obligation_id") != obligation_id \
                    or requirement.get("checker") != source.get("checker") \
                    or requirement.get("manifest_phase") \
                    != source.get("required_consumer_phase") \
                    or requirement.get("remaining_outcome") != required_sublot_outcome \
                    or requirement.get("escalation_item") != escalation_item:
                raise ValueError("the structural return has no exact escalation consumer")
    return output


def validate_return_account(value, *, previous_artifact, current_artifact, input_set):
    require_exact_keys(value, RETURN_KEYS, "the post-AMENDMENT correction return")
    if value["schema"] != 1 or not LOT_RE.fullmatch(str(value["built"])):
        raise ValueError("the post-AMENDMENT correction return has an invalid identity")
    require_positive(value["round"], "the post-AMENDMENT correction round")
    require_proof(value["previous_authority"], "the previous correction authority")
    require_hash(
        value["previous_execution_authority_sha256"],
        "the previous correction execution authority",
    )
    route = value["route"]
    if route not in {"rebase", "resolved", "sublot"}:
        raise ValueError("the post-AMENDMENT correction return has an unknown route")

    validate_artifact_accounts(
        value, previous_artifact, current_artifact, value["built"], value["round"],
    )
    validate_amendment(value["amendment"], current_artifact)
    validate_tree_transition(value["tree_transition"])
    findings, absorbed_findings, remaining_findings = validate_findings(
        value["findings"], previous_artifact, current_artifact,
    )
    projection = validate_task_projection(
        value["task_projection"], previous_artifact, current_artifact,
        absorbed_findings, route,
    )
    contributions = validate_contributions(
        value["accepted_contributions"], current_artifact, projection,
    )
    rewound = [item for item in contributions if item["outcome"] == "rewound"]
    rewind = value["tree_transition"]["rewind"]
    if bool(rewound) != (rewind is not None) \
            or any(item["rewind"] != rewind for item in rewound):
        raise ValueError("the correction return contributions change their exact rewind")

    expected_state = {"rebase": "active", "resolved": "resolved", "sublot": "escalating"}
    if current_artifact["state"] != expected_state[route]:
        raise ValueError("the correction artifact has another return route")
    if route == "rebase":
        if not remaining_findings or not current_artifact["tasks"] \
                or value["blocker"] is not None \
                or value["required_sublot_outcome"] is not None:
            raise ValueError("the rebased correction return has an invalid route account")
    elif route == "resolved":
        if remaining_findings or current_artifact["tasks"] \
                or value["blocker"] is not None \
                or value["required_sublot_outcome"] is not None:
            raise ValueError("the resolved correction return has an invalid route account")
    else:
        require_proof(value["blocker"], "the structural correction return blocker")
        if not isinstance(value["required_sublot_outcome"], str) \
                or not value["required_sublot_outcome"].strip() \
                or value["required_sublot_outcome"] != value["required_sublot_outcome"].strip():
            raise ValueError("the structural correction return has no exact sub-lot outcome")

    validate_retry_transition(
        value["retry_transition"], input_set, route, current_artifact,
        set(item for item in current_artifact["absorbed_findings"].values()),
        amendment_commit=value["amendment"]["committed"],
        required_sublot_outcome=value["required_sublot_outcome"],
        remaining_findings=remaining_findings,
    )
    return copy.deepcopy(value)
