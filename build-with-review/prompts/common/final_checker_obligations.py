#!/usr/bin/env python3
"""Canonical final-checker obligation sets and finite authority transitions."""

import copy
import hashlib
import json
import re


HASH_RE = re.compile(r"[0-9a-f]{64}")
PROOF_RE = re.compile(r"[1-9][0-9]*:[0-9a-f]{64}")
LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
SOURCE_KEYS = {
    "obligation_id", "source_proof", "source_unit",
    "source_contract_authority_sha256", "source_execution_authority_sha256",
    "owner_task", "checker", "accepted_ids", "result_sha256", "settlement",
    "required_consumer_phase",
}
SEMANTIC_TRANSITION_KEYS = {"schema", "input_sha256", "additions", "dispositions"}
TRANSITION_KEYS = SEMANTIC_TRANSITION_KEYS | {"transition_id", "output_sha256"}
SEMANTIC_DISPOSITION_KEYS = {"obligation_id", "outcome", "assignment", "evidence"}
MATERIALIZED_DISPOSITION_KEYS = SEMANTIC_DISPOSITION_KEYS | {"transition_authority"}
ENTRY_KEYS = {"source", "assignment", "transfers"}
TRANSFER_KEYS = {"kind", "transition_id", "from", "to"}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def empty_set():
    return {"schema": 1, "entries": []}


EMPTY_SET_SHA256 = canonical_sha256(empty_set())


def set_sha256(value):
    return canonical_sha256(validate_set(value))


def require_exact_keys(value, keys, subject):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{subject} does not have its exact fields")


def require_hash(value, subject):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{subject} is not one exact SHA-256")


def require_proof(value, subject):
    if not isinstance(value, str) or not PROOF_RE.fullmatch(value):
        raise ValueError(f"{subject} is not one exact journal proof")


def require_positive(value, subject):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{subject} is not one positive integer")


def validate_work_unit(value, subject="the final-checker work unit"):
    if not isinstance(value, dict):
        raise ValueError(f"{subject} is not one object")
    if value.get("kind") == "correction":
        require_exact_keys(value, {"kind", "built", "round"}, subject)
        if not isinstance(value["built"], str) or not LOT_RE.fullmatch(value["built"]):
            raise ValueError(f"{subject} has an invalid built unit")
        require_positive(value["round"], f"{subject} round")
    elif value.get("kind") == "task":
        require_exact_keys(value, {"kind", "lot"}, subject)
        if not isinstance(value["lot"], str) or not LOT_RE.fullmatch(value["lot"]):
            raise ValueError(f"{subject} has an invalid lot")
    else:
        raise ValueError(f"{subject} has an unsupported kind")
    return copy.deepcopy(value)


def validate_source_unit(value):
    if not isinstance(value, dict):
        raise ValueError("the final-checker source unit is not one object")
    if value.get("kind") == "correction":
        return validate_work_unit(value, "the final-checker source unit")
    if value.get("kind") == "task":
        keys = {
            "kind", "lot", "task", "attempt", "plan_contract_sha256",
            "execution_authority_sha256",
        }
        require_exact_keys(value, keys, "the final-checker task source unit")
        if not isinstance(value["lot"], str) or not LOT_RE.fullmatch(value["lot"]):
            raise ValueError("the final-checker task source unit has an invalid lot")
        require_positive(value["task"], "the final-checker source task")
        require_positive(value["attempt"], "the final-checker source attempt")
        require_hash(value["plan_contract_sha256"], "the final-checker source plan contract")
        require_hash(
            value["execution_authority_sha256"],
            "the final-checker source execution authority",
        )
        return copy.deepcopy(value)
    raise ValueError("the final-checker source unit has an unsupported kind")


def source_account(value):
    if not isinstance(value, dict):
        raise ValueError("the final-checker source account is not one object")
    if "obligation_id" in value:
        require_exact_keys(value, SOURCE_KEYS, "the final-checker source account")
        supplied_id = value["obligation_id"]
        semantic = {key: copy.deepcopy(item) for key, item in value.items()
                    if key != "obligation_id"}
    else:
        require_exact_keys(
            value, SOURCE_KEYS - {"obligation_id"}, "the final-checker source account",
        )
        supplied_id = None
        semantic = copy.deepcopy(value)

    require_proof(semantic["source_proof"], "the final-checker source proof")
    semantic["source_unit"] = validate_source_unit(semantic["source_unit"])
    require_hash(
        semantic["source_contract_authority_sha256"],
        "the final-checker source contract authority",
    )
    require_hash(
        semantic["source_execution_authority_sha256"],
        "the final-checker source execution authority",
    )
    require_positive(semantic["owner_task"], "the final-checker source owner task")
    checker = semantic["checker"]
    if checker not in {"design", "code"}:
        raise ValueError("the final-checker source has an invalid checker")
    accepted_ids = semantic["accepted_ids"]
    if not isinstance(accepted_ids, list) or not accepted_ids:
        raise ValueError("the final-checker source has no accepted identities")
    for accepted_id in accepted_ids:
        require_positive(accepted_id, "a final-checker accepted identity")
    if accepted_ids != sorted(set(accepted_ids)):
        raise ValueError("the final-checker accepted identities are not sorted and unique")
    require_hash(semantic["result_sha256"], "the final-checker result")
    require_proof(semantic["settlement"], "the final-checker settlement")
    if semantic["required_consumer_phase"] != f"first-{checker}-manifest":
        raise ValueError("the final-checker source has the wrong consumer phase")

    obligation_id = canonical_sha256(semantic)
    if supplied_id is not None and supplied_id != obligation_id:
        raise ValueError("the final-checker source has the wrong obligation identity")
    return {"obligation_id": obligation_id, **semantic}


def validate_assignment(value, *, materialized):
    if not isinstance(value, dict):
        raise ValueError("the final-checker assignment is not one object")
    owner = value.get("owner")
    common = {"unit", "task", "phase", "owner"}
    keys = set(common)
    if owner == "task":
        keys.add("task_contract_sha256")
    if "consumer_requirement" in value:
        keys.add("consumer_requirement")
    if materialized:
        keys.add("mapping_proof")
    require_exact_keys(value, keys, "the final-checker assignment")

    if owner == "task":
        validate_work_unit(value["unit"])
        require_positive(value["task"], "the assigned final-checker task")
        if value["phase"] not in {"first-design-manifest", "first-code-manifest"}:
            raise ValueError("the task assignment has an invalid consumer phase")
        require_hash(value["task_contract_sha256"], "the assigned task contract")
        if "consumer_requirement" in value:
            raise ValueError("a task assignment has a foreign consumer requirement")
    elif owner == "task-contract-map":
        require_exact_keys(
            value["unit"],
            {"kind", "operation", "work_unit", "target_task", "document_kind"},
            "the task-contract-map unit",
        )
        if value["unit"]["kind"] != "task-contract-map":
            raise ValueError("the task-contract-map assignment has the wrong unit kind")
        require_hash(value["unit"]["operation"], "the task-contract-map operation")
        validate_work_unit(value["unit"]["work_unit"])
        require_positive(value["unit"]["target_task"], "the task-contract-map target")
        if value["unit"]["document_kind"] not in {"correction-artifact", "plan"}:
            raise ValueError("the task-contract-map assignment has an invalid document kind")
        if value["task"] is not None or value["phase"] != "publish-task-contract" \
                or "consumer_requirement" in value:
            raise ValueError("the task-contract-map assignment has an invalid owner account")
    elif owner == "amendment-return":
        require_exact_keys(value["unit"], {"kind", "number"}, "the amendment return unit")
        if value["unit"]["kind"] != "amendment":
            raise ValueError("the amendment return has the wrong unit kind")
        require_positive(value["unit"]["number"], "the amendment return number")
        if value["task"] is not None \
                or value["phase"] != "publish-post-amendment-return" \
                or "consumer_requirement" in value:
            raise ValueError("the amendment return assignment has an invalid owner account")
    elif owner == "escalation-tail":
        unit = value["unit"]
        if not isinstance(unit, dict) or unit.get("kind") != "correction-escalation" \
                or unit.get("producer") not in {
                    "ordinary", "post-amendment-return", "retained-authority-rewind",
                }:
            raise ValueError("the escalation-tail unit has an invalid producer")
        producer = unit["producer"]
        authority_key = {
            "ordinary": "authority",
            "post-amendment-return": "amendment",
            "retained-authority-rewind": "rewind_owner_sha256",
        }[producer]
        require_exact_keys(
            unit, {"kind", "built", "round", "producer", authority_key},
            "the escalation-tail unit",
        )
        if not isinstance(unit["built"], str) or not LOT_RE.fullmatch(unit["built"]):
            raise ValueError("the escalation-tail unit has an invalid built unit")
        require_positive(unit["round"], "the escalation-tail correction round")
        if authority_key in {"authority", "amendment"}:
            require_proof(unit[authority_key], "the escalation-tail journal authority")
        else:
            require_hash(unit[authority_key], "the escalation-tail producer authority")
        validate_consumer_requirement(value.get("consumer_requirement"))
        if value["task"] is not None or value["phase"] != "sublot-plan-consumer-map":
            raise ValueError("the escalation-tail assignment has an invalid owner account")
    elif owner == "sublot-plan":
        unit = value["unit"]
        require_exact_keys(unit, {"kind", "lot", "source"}, "the sublot-plan unit")
        if unit["kind"] != "sublot-plan" \
                or not isinstance(unit["lot"], str) or not LOT_RE.fullmatch(unit["lot"]):
            raise ValueError("the sublot-plan unit has an invalid identity")
        require_proof(unit["source"], "the sublot-plan escalation source")
        validate_consumer_requirement(value.get("consumer_requirement"))
        if value["task"] is not None or value["phase"] != "publish-consumer-map":
            raise ValueError("the sublot-plan assignment has an invalid owner account")
    else:
        raise ValueError("the final-checker assignment has an unsupported owner")

    if "consumer_requirement" in value and (
        not isinstance(value["consumer_requirement"], dict)
        or not value["consumer_requirement"]
    ):
        raise ValueError("the final-checker consumer requirement is invalid")
    if materialized:
        require_hash(value["mapping_proof"], "the assignment mapping proof")
    return copy.deepcopy(value)


def validate_consumer_requirement(value):
    keys = {
        "obligation_id", "checker", "manifest_phase", "remaining_outcome",
        "escalation_item",
    }
    require_exact_keys(value, keys, "the final-checker consumer requirement")
    require_hash(value["obligation_id"], "the consumer requirement obligation")
    if value["checker"] not in {"design", "code"} \
            or value["manifest_phase"] != f"first-{value['checker']}-manifest":
        raise ValueError("the consumer requirement has an invalid checker phase")
    if not isinstance(value["remaining_outcome"], str) \
            or not value["remaining_outcome"].strip() \
            or value["remaining_outcome"] != value["remaining_outcome"].strip():
        raise ValueError("the consumer requirement has no exact remaining outcome")
    if not isinstance(value["escalation_item"], str) \
            or not re.fullmatch(r"F[1-9][0-9]*", value["escalation_item"]):
        raise ValueError("the consumer requirement has no exact escalation item")
    return copy.deepcopy(value)


def _assignment_consumer_task(assignment):
    if not isinstance(assignment, dict):
        return None
    if assignment.get("owner") == "task":
        return assignment.get("task")
    unit = assignment.get("unit")
    if assignment.get("owner") == "task-contract-map" and isinstance(unit, dict):
        return unit.get("target_task")
    return None


def consumer_task_for_member(member):
    if not isinstance(member, dict):
        raise ValueError("the final-checker member is not one object")
    source_account(member.get("source"))
    assignments = [member.get("assignment")]
    transfers = member.get("transfers")
    if not isinstance(transfers, list):
        raise ValueError("the final-checker member has no transfer history")
    for transfer in reversed(transfers):
        if not isinstance(transfer, dict):
            raise ValueError("the final-checker member has a malformed transfer")
        assignments.extend((transfer.get("to"), transfer.get("from")))
    for assignment in assignments:
        task = _assignment_consumer_task(assignment)
        if isinstance(task, int) and not isinstance(task, bool) and task > 0:
            return task
    raise ValueError("the final-checker member has no exact consumer task authority")


def escalation_item_for_member(member, items):
    if not isinstance(items, list) or not items:
        raise ValueError("the escalation has no item task authority")
    expected_ids = [f"F{index}" for index in range(1, len(items) + 1)]
    actual_ids = []
    normalized = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "tasks"}:
            raise ValueError("an escalation item has malformed task authority")
        tasks = item["tasks"]
        if not isinstance(tasks, list) or tasks != sorted(set(tasks)) \
                or any(not isinstance(task, int) or isinstance(task, bool) or task < 1
                       for task in tasks):
            raise ValueError("an escalation item has malformed consumer tasks")
        actual_ids.append(item["id"])
        normalized.append({"id": item["id"], "tasks": tasks})
    if actual_ids != expected_ids:
        raise ValueError("the escalation item task authority is not contiguous")
    task = consumer_task_for_member(member)
    matches = [item["id"] for item in normalized if task in item["tasks"]]
    if len(matches) != 1:
        raise ValueError("the final-checker member has no one exact escalation item")
    return matches[0]


def consumer_requirement_for_member(member):
    source = source_account(member.get("source") if isinstance(member, dict) else None)
    assignments = [member.get("assignment")]
    transfers = member.get("transfers")
    if not isinstance(transfers, list):
        raise ValueError("the final-checker member has no transfer history")
    for transfer in transfers:
        if not isinstance(transfer, dict):
            raise ValueError("the final-checker member has a malformed transfer")
        assignments.extend((transfer.get("from"), transfer.get("to")))
    requirements = []
    for assignment in assignments:
        requirement = assignment.get("consumer_requirement") \
            if isinstance(assignment, dict) else None
        if requirement is not None:
            requirements.append(validate_consumer_requirement(requirement))
    if not requirements or any(requirement != requirements[0]
                               for requirement in requirements[1:]):
        raise ValueError("the final-checker member has no one immutable consumer requirement")
    requirement = requirements[0]
    if requirement["obligation_id"] != source["obligation_id"] \
            or requirement["checker"] != source["checker"] \
            or requirement["manifest_phase"] != source["required_consumer_phase"]:
        raise ValueError("the final-checker consumer requirement changes its source authority")
    return requirement


def semantic_assignment(value):
    validated = validate_assignment(value, materialized=True)
    return {key: item for key, item in validated.items() if key != "mapping_proof"}


def validate_transfer(value):
    require_exact_keys(value, TRANSFER_KEYS, "the final-checker transfer")
    if not isinstance(value["kind"], str) or not value["kind"]:
        raise ValueError("the final-checker transfer has no kind")
    require_hash(value["transition_id"], "the final-checker transfer transition")
    if value["from"] is not None:
        validate_assignment(value["from"], materialized=True)
    validate_assignment(value["to"], materialized=True)
    return copy.deepcopy(value)


def validate_set(value):
    require_exact_keys(value, {"schema", "entries"}, "the final-checker set")
    if value["schema"] != 1 or not isinstance(value["entries"], list):
        raise ValueError("the final-checker set has an invalid schema")
    result = empty_set()
    identities = []
    for raw_entry in value["entries"]:
        require_exact_keys(raw_entry, ENTRY_KEYS, "a final-checker set entry")
        source = source_account(raw_entry["source"])
        assignment = validate_assignment(raw_entry["assignment"], materialized=True)
        if not isinstance(raw_entry["transfers"], list) or not raw_entry["transfers"]:
            raise ValueError("a final-checker set entry has no transfer history")
        transfers = [validate_transfer(item) for item in raw_entry["transfers"]]
        if transfers[0]["kind"] != "addition" or transfers[0]["from"] is not None:
            raise ValueError("a final-checker transfer history has no exact addition")
        prior = None
        for index, transfer in enumerate(transfers):
            if index and transfer["from"] != prior:
                raise ValueError("a final-checker transfer history is not contiguous")
            prior = transfer["to"]
        if prior != assignment:
            raise ValueError("a final-checker transfer history does not reach its assignment")
        identities.append(source["obligation_id"])
        result["entries"].append({
            "source": source,
            "assignment": assignment,
            "transfers": transfers,
        })
    if identities != sorted(set(identities)):
        raise ValueError("the final-checker set entries are not sorted and unique")
    return result


def validate_semantic_transition(value, input_set):
    require_exact_keys(value, SEMANTIC_TRANSITION_KEYS, "the semantic retry transition")
    if value["schema"] != 1 or value["input_sha256"] != set_sha256(input_set):
        raise ValueError("the semantic retry transition has the wrong input")
    if not isinstance(value["additions"], list) or not isinstance(value["dispositions"], list):
        raise ValueError("the semantic retry transition has invalid member arrays")

    input_ids = [entry["source"]["obligation_id"] for entry in input_set["entries"]]
    additions = []
    addition_ids = []
    for raw_addition in value["additions"]:
        require_exact_keys(raw_addition, {"source", "assignment"}, "a retry addition")
        source = source_account(raw_addition["source"])
        assignment = validate_assignment(raw_addition["assignment"], materialized=False)
        if assignment["owner"] == "task":
            raise ValueError("a new final-checker obligation is assigned directly to a task")
        addition_ids.append(source["obligation_id"])
        additions.append({"source": source, "assignment": assignment})
    if addition_ids != sorted(set(addition_ids)) or set(addition_ids) & set(input_ids):
        raise ValueError("the retry additions do not have new sorted identities")

    dispositions = []
    disposition_ids = []
    for raw_disposition in value["dispositions"]:
        require_exact_keys(
            raw_disposition, SEMANTIC_DISPOSITION_KEYS, "a semantic retry disposition",
        )
        obligation_id = raw_disposition["obligation_id"]
        require_hash(obligation_id, "the retry disposition obligation")
        outcome = raw_disposition["outcome"]
        assignment = raw_disposition["assignment"]
        evidence = raw_disposition["evidence"]
        if outcome in {"deferred", "carried"}:
            assignment = validate_assignment(assignment, materialized=False)
            if outcome == "deferred" and assignment["owner"] != "task":
                raise ValueError("a deferred obligation does not name one task")
            if outcome == "carried" and assignment["owner"] == "task":
                raise ValueError("a carried obligation names a task owner")
            if evidence is not None:
                raise ValueError("a pending obligation has terminal evidence")
        elif outcome in {"absorbed", "consumed"}:
            if assignment is not None or not isinstance(evidence, dict) or not evidence:
                raise ValueError("a terminal obligation has no exact external evidence")
        else:
            raise ValueError("a retry disposition has an invalid outcome")
        disposition_ids.append(obligation_id)
        dispositions.append({
            "obligation_id": obligation_id,
            "outcome": outcome,
            "assignment": assignment,
            "evidence": copy.deepcopy(evidence),
        })
    if disposition_ids != input_ids:
        raise ValueError("the retry dispositions do not exhaust the input set in order")
    return {
        "schema": 1,
        "input_sha256": value["input_sha256"],
        "additions": additions,
        "dispositions": dispositions,
    }


def _materialize_semantic(input_set, semantic, transfer_kind):
    if not isinstance(transfer_kind, str) or not transfer_kind or transfer_kind == "addition":
        raise ValueError("the retry transition has an invalid producer transfer kind")
    semantic = validate_semantic_transition(semantic, input_set)
    transition_id = canonical_sha256(semantic)
    output_by_id = {}
    materialized_additions = []

    for addition in semantic["additions"]:
        assignment = {**copy.deepcopy(addition["assignment"]), "mapping_proof": transition_id}
        materialized = {"source": addition["source"], "assignment": assignment}
        materialized_additions.append(materialized)
        output_by_id[addition["source"]["obligation_id"]] = {
            "source": addition["source"],
            "assignment": assignment,
            "transfers": [{
                "kind": "addition",
                "transition_id": transition_id,
                "from": None,
                "to": assignment,
            }],
        }

    input_by_id = {
        entry["source"]["obligation_id"]: entry for entry in input_set["entries"]
    }
    materialized_dispositions = []
    for disposition in semantic["dispositions"]:
        prior = input_by_id[disposition["obligation_id"]]
        next_assignment = disposition["assignment"]
        if next_assignment is not None:
            if next_assignment == semantic_assignment(prior["assignment"]):
                next_assignment = copy.deepcopy(prior["assignment"])
            else:
                next_assignment = {**copy.deepcopy(next_assignment), "mapping_proof": transition_id}
            output_by_id[disposition["obligation_id"]] = {
                "source": prior["source"],
                "assignment": next_assignment,
                "transfers": copy.deepcopy(prior["transfers"]) + [{
                    "kind": transfer_kind,
                    "transition_id": transition_id,
                    "from": prior["assignment"],
                    "to": next_assignment,
                }],
            }
        materialized_dispositions.append({
            **copy.deepcopy(disposition),
            "assignment": next_assignment,
            "transition_authority": transition_id,
        })

    output = {
        "schema": 1,
        "entries": [output_by_id[key] for key in sorted(output_by_id)],
    }
    output = validate_set(output)
    envelope = {
        "schema": 1,
        "input_sha256": semantic["input_sha256"],
        "transition_id": transition_id,
        "additions": materialized_additions,
        "dispositions": materialized_dispositions,
        "output_sha256": set_sha256(output),
    }
    return envelope, output


def materialize_transition(input_set, *, additions, dispositions, transfer_kind):
    input_set = validate_set(input_set)
    semantic = {
        "schema": 1,
        "input_sha256": set_sha256(input_set),
        "additions": copy.deepcopy(additions),
        "dispositions": copy.deepcopy(dispositions),
    }
    return _materialize_semantic(input_set, semantic, transfer_kind)


def validate_transition(input_set, transition, *, transfer_kind):
    input_set = validate_set(input_set)
    require_exact_keys(transition, TRANSITION_KEYS, "the materialized retry transition")
    if transition["schema"] != 1:
        raise ValueError("the materialized retry transition has an invalid schema")
    require_hash(transition["transition_id"], "the retry transition identity")
    require_hash(transition["output_sha256"], "the retry transition output")
    if not isinstance(transition["additions"], list) \
            or not isinstance(transition["dispositions"], list):
        raise ValueError("the materialized retry transition has invalid member arrays")

    semantic_additions = []
    for addition in transition["additions"]:
        require_exact_keys(addition, {"source", "assignment"}, "a materialized retry addition")
        assignment = semantic_assignment(addition["assignment"])
        semantic_additions.append({"source": source_account(addition["source"]),
                                   "assignment": assignment})
    semantic_dispositions = []
    for disposition in transition["dispositions"]:
        require_exact_keys(
            disposition, MATERIALIZED_DISPOSITION_KEYS,
            "a materialized retry disposition",
        )
        require_hash(
            disposition["transition_authority"], "the retry disposition authority",
        )
        assignment = disposition["assignment"]
        if assignment is not None:
            assignment = semantic_assignment(assignment)
        semantic_dispositions.append({
            "obligation_id": disposition["obligation_id"],
            "outcome": disposition["outcome"],
            "assignment": assignment,
            "evidence": copy.deepcopy(disposition["evidence"]),
        })
    semantic = {
        "schema": 1,
        "input_sha256": transition["input_sha256"],
        "additions": semantic_additions,
        "dispositions": semantic_dispositions,
    }
    expected, output = _materialize_semantic(input_set, semantic, transfer_kind)
    if transition != expected:
        raise ValueError("the materialized retry transition does not match its exact preimage")
    return output
