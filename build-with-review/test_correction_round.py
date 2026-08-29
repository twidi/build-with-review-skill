#!/usr/bin/env python3
"""Focused tests for Correction Round identities and artifact projections."""

import hashlib
import importlib.util
import json
import os
import pathlib
import pickle
import re
import stat
import sys
import tempfile
import traceback
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
CONSTRUCTION = HERE / "prompts" / "construction"
TESTS = []


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def valid_artifact(*, design="[written at correction task Design - see below]",
                   consumes="-", task_2=False):
    coverage = "F1: tasks 1, 2\nF2: task 1" if task_2 else "F1: task 1\nF2: task 1"
    text = f"""# Demo — lot-1.1 correction round 1

Schema: 1
Built unit: lot-1.1
Correction round: 1
Parent position: c0
Parent generation SHA-256: {'a' * 64}
Source reviewed commit: {'b' * 40}
Source accepted gate: {'c' * 64}
Correction base commit: {'d' * 40}
Correction base gate: {'e' * 64}
Source pass: p1
Source opening: 6:{'f' * 64}
Source findings: reports/product-review/lot-1/lot-1.1-c0-p1-confirmed.md
Source findings SHA-256: {'1' * 64}

## Route account
Spec: current and settled
Human decisions: settled
Controller contract: preserved
Ownership: preserved
Decomposition: preserved
Coordination: bounded
Repetition: independent
Reason: The two fixes share one bounded implementation area.

## Finding coverage
{coverage}

---

## Task 1 - Correct both accepted findings

Covers: F1, F2
Depends on: -
Consumes final-checker obligations: {consumes}
Achieves:
  - Both accepted behaviors use the current implementation contract.
Files: src/demo.py and its focused tests
To verify: Both accepted behaviors pass through the production entry point.

### Design
{design}

### Disagreement
[optional - same accepted alternative contract as an ordinary task]
"""
    if task_2:
        text += """

---

## Task 2 - Preserve the second entry point

Covers: F1
Depends on: 1
Consumes final-checker obligations: -
Achieves:
  - The second entry point preserves the corrected behavior.
Files: src/second.py and its focused tests
To verify: The second entry point uses the accepted correction.

### Design
[written at correction task Design - see below]
"""
    return text.encode()


def schema_two_artifact(*, state="active"):
    raw = valid_artifact().decode()
    raw = raw.replace(
        "Schema: 1\n",
        "Schema: 2\n"
        "State: active\n"
        "Amendment: 1\n"
        f"Amendment opening: 7:{'4' * 64}\n"
        f"Amendment commit: 8:{'5' * 64}\n",
        1,
    )
    raw = raw.replace("F1: task 1\nF2: task 1", "F1: tasks 1, 3\nF2: task 2", 1)
    absorbed = f"F2: 9:{'6' * 64}"
    remaining = "F1: task 2"
    removed = "2"
    task_projection = "Task 2: prior task 3 · findings F1\n"
    if state == "resolved":
        absorbed = f"F1: 9:{'6' * 64}\nF2: 11:{'a' * 64}"
        remaining = ""
        removed = "2, 3"
        task_projection = ""
    elif state == "escalating":
        removed = "2, 3"
        task_projection = ""
    projection = f"""## Absorbed findings
{absorbed}

## Remaining finding coverage
{remaining}

## Accepted contributions
Task 1: 10:{'7' * 64} · {'8' * 40} · {'9' * 64} · preserved

## Task projection
Preserved: 1
Removed: {removed}
{task_projection}

"""
    raw = raw.replace("---\n\n## Task 1", projection + "---\n\n## Task 1", 1)
    raw = raw.replace("Covers: F1, F2", "Covers: F1", 1)
    raw = raw.replace("## Task 1 - Correct both accepted findings",
                      "## Task 2 - Correct both accepted findings", 1)
    if state != "active":
        raw = raw.replace("State: active", f"State: {state}", 1)
        start = raw.index("---\n\n## Task 2")
        raw = raw[:start]
    return raw.encode()


def post_amendment_return_artifact(*, state="active"):
    raw = valid_artifact(task_2=True).decode()
    raw = raw.replace(
        "Schema: 1\n",
        "Schema: 2\n"
        "State: active\n"
        "Amendment: 1\n"
        f"Amendment opening: 7:{'4' * 64}\n"
        f"Amendment commit: 8:{'5' * 64}\n",
        1,
    )
    absorbed = f"F2: 9:{'6' * 64}"
    remaining = "F1: task 1"
    removed = "-"
    projected = "Task 1: prior tasks 1, 2 · findings F1\n"
    if state == "resolved":
        absorbed = f"F1: 11:{'a' * 64}\nF2: 9:{'6' * 64}"
        remaining = ""
        removed = "1, 2"
        projected = ""
    elif state == "escalating":
        removed = "1, 2"
        projected = ""
    projection = f"""## Absorbed findings
{absorbed}

## Remaining finding coverage
{remaining}

## Accepted contributions

## Task projection
Preserved: -
Removed: {removed}
{projected}

"""
    raw = raw.replace("---\n\n## Task 1", projection + "---\n\n## Task 1", 1)
    raw = raw.replace("Covers: F1, F2", "Covers: F1", 1)
    second = raw.find("\n\n---\n\n## Task 2")
    raw = raw[:second] + "\n" if second >= 0 else raw
    if state in {"resolved", "escalating"}:
        raw = raw.replace("State: active", f"State: {state}", 1)
        start = raw.index("---\n\n## Task 1")
        raw = raw[:start]
    return raw.encode()


def escalation_artifact(*, schema):
    if schema == 1:
        identity = (
            "Schema: 1\n"
            "Built unit: lot-1.1\n"
            "Correction round: 1\n"
            f"Correction authority: 1:{'a' * 64}\n"
            f"Current commit: {'b' * 40}\n"
            f"Structural blocker: 2:{'c' * 64}\n"
        )
        contributions = (
            f"Task 1: {'d' * 40} · {'e' * 64} · satisfies F2, F10\n"
        )
    else:
        identity = (
            "Schema: 2\n"
            "Producer: post-amendment-return\n"
            "Built unit: lot-1.1\n"
            "Correction round: 1\n"
            f"Correction opening: 1:{'a' * 64}\n"
            f"Previous authority: 2:{'b' * 64}\n"
            f"AMENDMENT opening: 3:{'c' * 64}\n"
            f"AMENDMENT commit: 4:{'d' * 64}\n"
            f"Return SHA-256: {'e' * 64}\n"
            f"Current commit: {'f' * 40}\n"
            f"Current tree: {'1' * 40}\n"
            f"Current gate: {'2' * 64}\n"
            f"Correction artifact SHA-256: {'3' * 64}\n"
            f"Structural blocker: 5:{'4' * 64}\n"
        )
        contributions = ""
    return (
        "# Demo — lot-1.1 correction round 1 escalation\n\n"
        f"{identity}\n"
        "## Accepted contributions\n"
        f"{contributions}\n"
        "## Unresolved account\n\n"
        "### F1 - Publish the structural correction.\n"
        "Origins: correction/c1/F2, correction/c1/F10\n"
        "Sources: unlooked/F2, unlooked/F10, coverage/F1\n"
        "Accepted contributions: task 2, task 10\n"
        f"Blocker: 2:{'c' * 64}\n"
        "Required outcome: Publish the structural correction.\n\n"
        "## Required sub-lot outcome\n"
        "Publish the structural correction.\n\n"
        "## Final-checker consumer requirements\n"
    ).encode()


def post_amendment_return_account(return_module, obligations_module, *, route="rebase"):
    parser = load_module(
        f"correction_round_return_{route}", CONSTRUCTION / "correction_round.py",
    )
    previous = parser.parse_artifact_bytes(valid_artifact(task_2=True))
    state = {"rebase": "active", "resolved": "resolved", "sublot": "escalating"}[route]
    current = parser.parse_artifact_bytes(post_amendment_return_artifact(state=state))
    transition, _ = obligations_module.materialize_transition(
        obligations_module.empty_set(), additions=[], dispositions=[],
        transfer_kind="amendment-return",
    )
    absorbed = {"F2": f"9:{'6' * 64}"}
    findings = [
        {"id": "F1", "outcome": "remaining", "amendment_item": None},
        {"id": "F2", "outcome": "absorbed", "amendment_item": absorbed["F2"]},
    ]
    projection = {
        "preserved": [],
        "removed": [],
        "remaining": [{"task": 1, "prior_tasks": [1, 2], "findings": ["F1"]}],
    }
    if route == "resolved":
        absorbed = {
            "F1": f"11:{'a' * 64}",
            "F2": f"9:{'6' * 64}",
        }
        findings = [
            {"id": finding, "outcome": "absorbed", "amendment_item": absorbed[finding]}
            for finding in ("F1", "F2")
        ]
        projection = {
            "preserved": [],
            "removed": [
                {"task": 1, "reason": "absorbed"},
                {"task": 2, "reason": "absorbed"},
            ],
            "remaining": [],
        }
    elif route == "sublot":
        projection = {
            "preserved": [],
            "removed": [
                {"task": 1, "reason": "structural-escalation"},
                {"task": 2, "reason": "structural-escalation"},
            ],
            "remaining": [],
        }
    account = {
        "schema": 1,
        "built": "lot-1.1",
        "round": 1,
        "previous_authority": f"6:{'3' * 64}",
        "previous_execution_authority_sha256": "b" * 64,
        "amendment": {
            "opening": f"7:{'4' * 64}",
            "committed": f"8:{'5' * 64}",
            "artifact_sha256": "c" * 64,
            "spec_path": "docs/plans/demo-design.md",
            "spec_sha256": "d" * 64,
        },
        "tree_transition": {
            "pre_amendment_rewind": None,
            "rewind": None,
            "reland": None,
        },
        "input_artifact": {
            "sha256": previous["artifact_sha256"],
            "object": (
                "corrections/lot-1.1/objects/"
                f"sha256-{previous['artifact_sha256']}.md"
            ),
        },
        "current": {
            "artifact_sha256": current["artifact_sha256"],
            "artifact_object": (
                "corrections/lot-1.1/objects/"
                f"sha256-{current['artifact_sha256']}.md"
            ),
            "commit": "e" * 40,
            "tree": "f" * 40,
            "gate": "1" * 64,
        },
        "findings": findings,
        "task_projection": projection,
        "accepted_contributions": [],
        "blocker": f"12:{'b' * 64}" if route == "sublot" else None,
        "required_sublot_outcome": (
            "Publish the remaining correction through one sub-lot."
            if route == "sublot" else None
        ),
        "retry_transition": transition,
        "route": route,
    }
    return account, previous, current


@test
def work_units_are_explicit_and_canonical():
    module = load_module("work_unit", CONSTRUCTION / "work_unit.py")
    lot = module.normalize_work_unit({"kind": "lot", "lot": "lot-1.2"})
    correction = module.normalize_work_unit(
        {"kind": "correction", "built": "lot-1.2", "round": 3},
    )
    check(lot == {"kind": "lot", "lot": "lot-1.2"}, lot)
    check(correction == {"kind": "correction", "built": "lot-1.2", "round": 3}, correction)
    check(module.readable_work_unit(correction) == "lot-1.2 correction round 3", correction)
    for invalid in (
        {"kind": "correction", "built": "lot-1.2"},
        {"kind": "correction", "built": "lot-1.2", "round": True},
        {"kind": "correction", "built": "lot-1.2", "round": 0},
        {"kind": "lot", "lot": "lot-1", "round": 1},
        {"kind": "correction", "built": "lot-0", "round": 1},
    ):
        try:
            module.normalize_work_unit(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid work unit: {invalid}")


@test
def correction_authority_lease_is_one_live_non_serializable_owner():
    module = load_module(
        "correction_authority_lease", HERE / "prompts" / "common" / "correction_authority.py",
    )
    with tempfile.TemporaryDirectory() as directory:
        with module.CorrectionAuthorityLease.acquire(directory, "allocate:lot-1:1") as lease:
            lease.verify("allocate:lot-1:1")
            lease.bind_generation("a" * 64)
            lease.verify("allocate:lot-1:1", "a" * 64)
            for operation, generation in (
                ("allocate:lot-1:2", "a" * 64),
                ("allocate:lot-1:1", "b" * 64),
            ):
                try:
                    lease.verify(operation, generation)
                except ValueError:
                    pass
                else:
                    raise AssertionError("a correction lease accepted foreign authority")
            try:
                pickle.dumps(lease)
            except TypeError:
                pass
            else:
                raise AssertionError("a live correction lease became serializable authority")
        try:
            lease.verify("allocate:lot-1:1", "a" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError("a closed correction lease retained authority")


@test
def controller_successor_generation_has_one_finite_ordered_authority_account():
    module = load_module(
        "correction_authority_successor",
        HERE / "prompts" / "common" / "correction_authority.py",
    )
    account = {
        "schema": 1,
        "kind": "controller-successor",
        "transition": "in-pass-product-authority",
        "built": "lot-1.1",
        "position": 2,
        "predecessor_generation_sha256": "a" * 64,
        "source_pass": "17:" + "b" * 64,
        "authorities": [
            "18:" + "c" * 64,
            "19:" + "d" * 64,
            "20:" + "e" * 64,
            "21:" + "f" * 64,
        ],
        "commit": "1" * 40,
        "gate": "2" * 64,
    }
    normalized = module.normalize_controller_successor(account)
    check(normalized == account, normalized)
    check(module.generation_sha256(normalized) == hashlib.sha256(
        json.dumps(account, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest(), "the controller-successor digest uses another preimage")

    for mutate in (
        lambda value: value["authorities"].reverse(),
        lambda value: value["authorities"].append(value["authorities"][0]),
        lambda value: value.update(transition="unknown"),
        lambda value: value.update(position=True),
    ):
        invalid = json.loads(json.dumps(account))
        mutate(invalid)
        try:
            module.normalize_controller_successor(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid controller successor: {invalid}")


@test
def schema_one_artifact_exposes_exact_many_to_many_accounts():
    module = load_module("correction_round", CONSTRUCTION / "correction_round.py")
    raw = valid_artifact(task_2=True)
    state = module.parse_artifact_bytes(raw, expected_built="lot-1.1", expected_round=1)
    check(state["schema"] == 1, state)
    check(state["state"] == "active", state)
    check(state["built"] == "lot-1.1" and state["round"] == 1, state)
    check(state["source_findings"] == ["F1", "F2"], state)
    check(state["finding_coverage"] == {"F1": [1, 2], "F2": [1]}, state)
    check([task["task"] for task in state["tasks"]] == [1, 2], state)
    check(state["tasks"][1]["depends_on"] == [1], state)
    check(state["artifact_sha256"] == hashlib.sha256(raw).hexdigest(), state)


@test
def design_and_consumer_projections_have_separate_authority():
    module = load_module("correction_round_projection", CONSTRUCTION / "correction_round.py")
    original = module.parse_artifact_bytes(valid_artifact())
    design_edit = module.parse_artifact_bytes(valid_artifact(design="Use the established service path."))
    consumer_edit = module.parse_artifact_bytes(valid_artifact(consumes=f"{'2' * 64}, {'3' * 64}"))

    first = original["tasks"][0]
    changed_design = design_edit["tasks"][0]
    changed_consumer = consumer_edit["tasks"][0]
    check(changed_design["design_sha256"] != first["design_sha256"], changed_design)
    check(changed_design["design_contract_sha256"] == first["design_contract_sha256"], changed_design)
    check(changed_design["consumer_account_sha256"] == first["consumer_account_sha256"], changed_design)
    check(changed_consumer["design_contract_sha256"] == first["design_contract_sha256"], changed_consumer)
    check(changed_consumer["consumer_account_sha256"] != first["consumer_account_sha256"], changed_consumer)
    check(changed_consumer["task_contract_sha256"] != first["task_contract_sha256"], changed_consumer)
    check(consumer_edit["manifest_sha256"] == original["manifest_sha256"], consumer_edit)

    preimage = {
        "schema": 1,
        "design_contract_sha256": changed_consumer["design_contract_sha256"],
        "consumer_account_sha256": changed_consumer["consumer_account_sha256"],
    }
    expected = hashlib.sha256(
        json.dumps(preimage, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    check(changed_consumer["task_contract_sha256"] == expected, changed_consumer)


@test
def structural_headings_inside_fences_remain_design_data():
    module = load_module("correction_round_fences", CONSTRUCTION / "correction_round.py")
    design = """Use the renderer example.

```markdown
## Task 9 - Example only
### Design
### Disagreement
```

Keep the example inside this Design."""
    state = module.parse_artifact_bytes(valid_artifact(design=design))
    check(len(state["tasks"]) == 1, state)
    check(state["tasks"][0]["design_sha256"], state)


@test
def correction_artifact_rejects_every_unowned_structural_interval():
    module = load_module("correction_round_closed_structure", CONSTRUCTION / "correction_round.py")
    original = valid_artifact()
    reversed_sections = original.replace(
        b"### Design\n[written at correction task Design - see below]\n\n"
        b"### Disagreement\n[optional - same accepted alternative contract as an ordinary task]\n",
        b"### Disagreement\n[optional - same accepted alternative contract as an ordinary task]\n\n"
        b"### Design\n[written at correction task Design - see below]\n",
    )
    cases = (
        original.replace(
            b"F2: task 1\n\n---",
            b"F2: task 1\n\n## Foreign account\nUnowned root bytes.\n\n---",
        ),
        original.replace(
            b"### Disagreement",
            b"### Foreign authority\nUnowned task bytes.\n\n### Disagreement",
        ),
        reversed_sections,
    )
    for raw in cases:
        try:
            module.parse_artifact_bytes(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an unowned Correction Round structural interval")


@test
def correction_artifact_rejects_indented_commonmark_headings():
    module = load_module(
        "correction_round_indented_headings", CONSTRUCTION / "correction_round.py",
    )
    original = valid_artifact()
    for spaces in (b" ", b"  ", b"   "):
        cases = (
            original.replace(
                b"F2: task 1\n\n---",
                b"F2: task 1\n\n" + spaces + b"## Foreign account\nUnowned root bytes.\n\n---",
            ),
            original.replace(
                b"### Disagreement",
                spaces + b"### Foreign authority\nUnowned task bytes.\n\n### Disagreement",
            ),
            original.replace(b"### Design", spaces + b"### Design"),
            original.replace(b"### Disagreement", spaces + b"### Disagreement"),
        )
        for raw in cases:
            try:
                module.parse_artifact_bytes(raw)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"accepted a CommonMark heading indented by {len(spaces)} spaces",
                )

    with tempfile.TemporaryDirectory() as temporary:
        artifact = pathlib.Path(temporary) / "historical-round.md"
        artifact.write_bytes(original.replace(
            b"### Disagreement", b"  ### Disagreement",
        ))
        try:
            module.parse_artifact(artifact)
        except ValueError:
            pass
        else:
            raise AssertionError("the file-backed parser accepted an indented historical section")


@test
def indented_headings_inside_both_commonmark_fences_remain_design_data():
    module = load_module(
        "correction_round_indented_fences", CONSTRUCTION / "correction_round.py",
    )
    design = """Use both CommonMark fence kinds.

 ```markdown
 ### Foreign backtick heading
  ## Task 9 - Example only
 ```

  ~~~markdown
 ### Foreign tilde heading
   ### Disagreement
  ~~~

Keep every fenced heading inside this Design."""
    state = module.parse_artifact_bytes(valid_artifact(design=design))
    check(len(state["tasks"]) == 1, state)
    check(state["tasks"][0]["design_sha256"], state)


@test
def malformed_coverage_dependencies_and_consumer_ids_refuse():
    module = load_module("correction_round_refusal", CONSTRUCTION / "correction_round.py")
    cases = (
        valid_artifact().replace(b"F2: task 1\n", b""),
        valid_artifact().replace(b"Covers: F1, F2", b"Covers: F1"),
        valid_artifact(task_2=True).replace(b"Depends on: 1", b"Depends on: 2"),
        valid_artifact(consumes=f"{'3' * 64}, {'2' * 64}"),
        valid_artifact(consumes=f"{'2' * 64}, {'2' * 64}"),
    )
    for raw in cases:
        try:
            module.parse_artifact_bytes(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a malformed Correction Round artifact")


@test
def schema_two_projection_is_exhaustive_and_state_specific():
    module = load_module("correction_round_schema_two", CONSTRUCTION / "correction_round.py")
    active = module.parse_artifact_bytes(schema_two_artifact())
    check(active["schema"] == 2 and active["state"] == "active", active)
    check(active["absorbed_findings"] == {"F2": f"9:{'6' * 64}"}, active)
    check(active["finding_coverage"] == {"F1": [2]}, active)
    check(active["accepted_contributions"][0]["outcome"] == "preserved", active)
    check([task["task"] for task in active["tasks"]] == [2], active)
    check(active["task_projection"]["remaining"][0]["prior_tasks"] == [3], active)

    resolved = module.parse_artifact_bytes(schema_two_artifact(state="resolved"))
    check(resolved["state"] == "resolved" and not resolved["tasks"], resolved)
    check(set(resolved["absorbed_findings"]) == {"F1", "F2"}, resolved)
    escalating = module.parse_artifact_bytes(schema_two_artifact(state="escalating"))
    check(escalating["state"] == "escalating" and not escalating["tasks"], escalating)
    check(escalating["finding_coverage"] == {"F1": [2]}, escalating)

    invalid_resolved = schema_two_artifact(state="resolved").replace(
        b"## Remaining finding coverage\n\n",
        b"## Remaining finding coverage\nF1: task 1\n\n",
    )
    try:
        module.parse_artifact_bytes(invalid_resolved)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a resolved state with remaining work")

    overlap = schema_two_artifact().replace(
        b"## Absorbed findings\nF2:", b"## Absorbed findings\nF1:", 1,
    )
    try:
        module.parse_artifact_bytes(overlap)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted one finding as both absorbed and remaining")


@test
def escalation_numeric_identities_use_field_specific_canonical_order():
    module = load_module(
        "correction_escalation_numeric_order",
        CONSTRUCTION / "correction_escalation.py",
    )
    for schema in (1, 2):
        raw = escalation_artifact(schema=schema)
        account = module.parse_artifact_bytes(
            raw, expected_built="lot-1.1", expected_round=1,
        )
        check(
            account["items"][0]["origins"]
            == ["correction/c1/F2", "correction/c1/F10"],
            account,
        )
        check(
            account["items"][0]["accepted_contributions"] == [2, 10],
            account,
        )
        for old, new in (
            (
                b"Origins: correction/c1/F2, correction/c1/F10",
                b"Origins: correction/c1/F10, correction/c1/F2",
            ),
            (
                b"Accepted contributions: task 2, task 10",
                b"Accepted contributions: task 10, task 2",
            ),
        ):
            try:
                module.parse_artifact_bytes(raw.replace(old, new))
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"schema {schema} accepted reverse numeric identity order",
                )

    schema_one = escalation_artifact(schema=1)
    parsed = module.parse_artifact_bytes(schema_one)
    check(parsed["accepted_contributions"][0]["satisfies"] == ["F2", "F10"], parsed)
    try:
        module.parse_artifact_bytes(
            schema_one.replace(b"satisfies F2, F10", b"satisfies F10, F2"),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("schema 1 accepted reverse finding identity order")

    check(
        module.canonical_source_identities(
            ["coverage/F1", "unlooked/F10", "unlooked/F2"],
            "the product source order fixture",
        ) == ["unlooked/F2", "unlooked/F10", "coverage/F1"],
        "product sources stopped using mandate-plus-numeric order",
    )


@test
def post_amendment_return_account_owns_one_exhaustive_projection():
    return_module = load_module(
        "correction_amendment_return",
        CONSTRUCTION / "correction_amendment_return.py",
    )
    obligations_module = load_module(
        "final_checker_obligations_return",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    for route in ("rebase", "resolved", "sublot"):
        account, previous, current = post_amendment_return_account(
            return_module, obligations_module, route=route,
        )
        validated = return_module.validate_return_account(
            account,
            previous_artifact=previous,
            current_artifact=current,
            input_set=obligations_module.empty_set(),
        )
        check(validated == account, validated)

        if route == "sublot":
            structural_mutations = []
            omitted = json.loads(json.dumps(account))
            omitted["findings"].pop()
            structural_mutations.append(("omitted", omitted))
            reordered = json.loads(json.dumps(account))
            reordered["findings"].reverse()
            structural_mutations.append(("reordered", reordered))
            foreign = json.loads(json.dumps(account))
            foreign["findings"][0]["id"] = "F3"
            structural_mutations.append(("foreign", foreign))
            for label, mutation in structural_mutations:
                try:
                    return_module.validate_return_account(
                        mutation,
                        previous_artifact=previous,
                        current_artifact=current,
                        input_set=obligations_module.empty_set(),
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError(
                        f"the structural return accepted an {label} remaining finding",
                    )

        mutations = []
        missing_finding = json.loads(json.dumps(account))
        missing_finding["findings"].pop()
        mutations.append(missing_finding)
        overlapping_finding = json.loads(json.dumps(account))
        overlapping_finding["findings"][0]["outcome"] = "absorbed"
        overlapping_finding["findings"][0]["amendment_item"] = f"12:{'2' * 64}"
        mutations.append(overlapping_finding)
        changed_projection = json.loads(json.dumps(account))
        changed_projection["task_projection"]["preserved"] = [1]
        mutations.append(changed_projection)
        changed_artifact = json.loads(json.dumps(account))
        changed_artifact["current"]["artifact_sha256"] = "3" * 64
        mutations.append(changed_artifact)
        changed_transition = json.loads(json.dumps(account))
        changed_transition["retry_transition"]["output_sha256"] = "4" * 64
        mutations.append(changed_transition)
        changed_route = json.loads(json.dumps(account))
        changed_route["route"] = "resolved" if route == "sublot" else "sublot"
        mutations.append(changed_route)
        invented_rewind = json.loads(json.dumps(account))
        invented_rewind["tree_transition"]["rewind"] = f"13:{'7' * 64}"
        mutations.append(invented_rewind)
        invented_reland = json.loads(json.dumps(account))
        invented_reland["tree_transition"]["rewind"] = f"13:{'7' * 64}"
        invented_reland["tree_transition"]["reland"] = f"13:{'7' * 64}"
        mutations.append(invented_reland)
        for mutation in mutations:
            try:
                return_module.validate_return_account(
                    mutation,
                    previous_artifact=previous,
                    current_artifact=current,
                    input_set=obligations_module.empty_set(),
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted changed {route} return account: {mutation}")


@test
def post_amendment_rebase_owns_every_task_obligation_exactly_once():
    return_module = load_module(
        "correction_amendment_return_task_obligations",
        CONSTRUCTION / "correction_amendment_return.py",
    )
    obligations_module = load_module(
        "final_checker_obligations_return_task_obligations",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    sources = [
        correction_obligation_source(
            obligations_module,
            checker="code" if identity == 2 else "design",
            accepted_ids=[identity],
        )
        for identity in (1, 2, 3)
    ]
    sources.sort(key=lambda source: source["obligation_id"])
    amendment_assignment = {
        "unit": {"kind": "amendment", "number": 1},
        "task": None,
        "phase": "publish-post-amendment-return",
        "owner": "amendment-return",
    }
    _opening, input_set = obligations_module.materialize_transition(
        obligations_module.empty_set(),
        additions=[
            {"source": source, "assignment": amendment_assignment}
            for source in sources
        ],
        dispositions=[],
        transfer_kind="amendment-opening",
    )
    task_contracts = {1: "1" * 64, 2: "2" * 64}
    dispositions = []
    expected = {1: [], 2: []}
    for index, source in enumerate(sources):
        task = 1 if index < 2 else 2
        expected[task].append(source["obligation_id"])
        dispositions.append({
            "obligation_id": source["obligation_id"],
            "outcome": "deferred",
            "assignment": {
                "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
                "task": task,
                "phase": source["required_consumer_phase"],
                "owner": "task",
                "task_contract_sha256": task_contracts[task],
            },
            "evidence": None,
        })
    transition, output = obligations_module.materialize_transition(
        input_set,
        additions=[],
        dispositions=dispositions,
        transfer_kind="amendment-return",
    )
    artifact = {
        "built": "lot-1.1",
        "round": 1,
        "tasks": [
            {
                "task": task,
                "task_contract_sha256": task_contracts[task],
                "obligation_ids": expected[task],
            }
            for task in (1, 2)
        ],
    }
    check(
        return_module.validate_retry_transition(
            transition, input_set, "rebase", artifact, set(),
        ) == output,
        "the exact multi-task rebase did not validate",
    )

    mutations = []
    foreign = json.loads(json.dumps(artifact))
    foreign["tasks"][0]["obligation_ids"] = sorted(
        foreign["tasks"][0]["obligation_ids"] + ["f" * 64],
    )
    mutations.append(("foreign", foreign))
    duplicate = json.loads(json.dumps(artifact))
    duplicate["tasks"][1]["obligation_ids"] = sorted(
        duplicate["tasks"][1]["obligation_ids"] + [expected[1][0]],
    )
    mutations.append(("cross-task duplicate", duplicate))
    omitted = json.loads(json.dumps(artifact))
    omitted["tasks"][0]["obligation_ids"] = expected[1][1:]
    mutations.append(("omitted", omitted))
    reordered = json.loads(json.dumps(artifact))
    reordered["tasks"][0]["obligation_ids"] = list(reversed(expected[1]))
    mutations.append(("reordered", reordered))
    for label, mutation in mutations:
        try:
            return_module.validate_retry_transition(
                transition, input_set, "rebase", mutation, set(),
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted a {label} rebased obligation projection")

    for checker, wrong_phase in (
        ("code", "first-design-manifest"),
        ("design", "first-code-manifest"),
    ):
        source = next(item for item in sources if item["checker"] == checker)
        wrong_dispositions = json.loads(json.dumps(dispositions))
        disposition = next(
            item for item in wrong_dispositions
            if item["obligation_id"] == source["obligation_id"]
        )
        disposition["assignment"]["phase"] = wrong_phase
        wrong, _wrong_output = obligations_module.materialize_transition(
            input_set,
            additions=[],
            dispositions=wrong_dispositions,
            transfer_kind="amendment-return",
        )
        try:
            return_module.validate_retry_transition(
                wrong, input_set, "rebase", artifact, set(),
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted {checker} obligation through {wrong_phase}")


@test
def post_amendment_return_validates_before_immutable_publication():
    runner = load_module(
        "correction_round_return_prepublication",
        CONSTRUCTION / "correction_round_return.py",
    )
    return_module = load_module(
        "correction_amendment_return_prepublication",
        CONSTRUCTION / "correction_amendment_return.py",
    )
    obligations_module = load_module(
        "final_checker_obligations_return_prepublication",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    value, previous, current = post_amendment_return_account(
        return_module, obligations_module, route="rebase",
    )
    source = correction_obligation_source(
        obligations_module, checker="code", accepted_ids=[1],
    )
    amendment_assignment = {
        "unit": {"kind": "amendment", "number": 1},
        "task": None,
        "phase": "publish-post-amendment-return",
        "owner": "amendment-return",
    }
    _opening, input_set = obligations_module.materialize_transition(
        obligations_module.empty_set(),
        additions=[{"source": source, "assignment": amendment_assignment}],
        dispositions=[],
        transfer_kind="amendment-opening",
    )
    wrong_assignment = {
        "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
        "task": 1,
        "phase": "first-design-manifest",
        "owner": "task",
        "task_contract_sha256": current["tasks"][0]["task_contract_sha256"],
    }
    wrong_transition, _output = obligations_module.materialize_transition(
        input_set,
        additions=[],
        dispositions=[{
            "obligation_id": source["obligation_id"],
            "outcome": "deferred",
            "assignment": wrong_assignment,
            "evidence": None,
        }],
        transfer_kind="amendment-return",
    )
    value["retry_transition"] = wrong_transition
    current["tasks"][0]["obligation_ids"] = [source["obligation_id"]]
    current["artifact_sha256"] = "3" * 64
    value["current"]["artifact_sha256"] = current["artifact_sha256"]
    value["current"]["artifact_object"] = (
        "corrections/lot-1.1/objects/"
        f"sha256-{current['artifact_sha256']}.md"
    )
    published = []

    with tempfile.TemporaryDirectory() as temporary:
        workspace = pathlib.Path(temporary)
        runner.WORKSPACE = workspace
        account = {
            "built": "lot-1.1",
            "round": 1,
            "amendment": 1,
            "artifact_sha256": current["artifact_sha256"],
            "artifact_object": value["current"]["artifact_object"],
        }
        path = runner.return_path(account)
        path.parent.mkdir(parents=True)
        path.write_bytes(runner.canonical_bytes(value) + b"\n")
        runner.progress.journal_entries = lambda: []
        runner.progress.current_correction_contract_state = (
            lambda *_args, **_kwargs: {"artifact": previous}
        )
        runner.progress.outstanding_final_checker_set = (
            lambda *_args, **_kwargs: input_set
        )
        runner.progress.load_correction_amendment_return_validator = lambda: return_module
        runner.validate_content_object = (
            lambda *_args, **_kwargs: workspace / account["artifact_object"]
        )
        runner.parse_artifact = lambda *_args, **_kwargs: current

        def publish(*_args, **_kwargs):
            published.append(True)
            return workspace / "corrections/lot-1.1/objects/foreign.json"

        runner.publish_content_object = publish
        try:
            runner.consume_return(account)
        except ValueError:
            pass
        else:
            raise AssertionError("published an invalid immutable return account")
    check(not published, "validated the return only after immutable publication")


@test
def content_addressed_object_requires_exact_immutable_regular_bytes():
    module = load_module(
        "correction_authority", HERE / "prompts" / "common" / "correction_authority.py",
    )
    raw = valid_artifact()
    digest = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        workspace = pathlib.Path(temporary)
        objects = workspace / "corrections" / "lot-1.1" / "objects"
        objects.mkdir(parents=True)
        target = objects / f"sha256-{digest}.md"
        target.write_bytes(raw)
        target.chmod(0o444)
        checked = module.validate_content_object(workspace, "lot-1.1", digest, ".md")
        check(checked == target, checked)

        target.chmod(0o644)
        try:
            module.validate_content_object(workspace, "lot-1.1", digest, ".md")
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a writable authority object")
        target.chmod(0o444)

        alias = objects / "alias.md"
        os.link(target, alias)
        try:
            module.validate_content_object(workspace, "lot-1.1", digest, ".md")
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a multiply linked authority object")
        alias.unlink()

        target.unlink()
        foreign = objects / "foreign.md"
        foreign.write_bytes(raw)
        foreign.chmod(stat.S_IRUSR)
        target.symlink_to(foreign.name)
        try:
            module.validate_content_object(workspace, "lot-1.1", digest, ".md")
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a symlink authority object")


@test
def content_addressed_publication_is_atomic_idempotent_and_non_replacing():
    module = load_module(
        "correction_publication", HERE / "prompts" / "common" / "correction_authority.py",
    )
    raw = valid_artifact()
    digest = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        workspace = pathlib.Path(temporary)
        first = module.publish_content_object(workspace, "lot-1.1", raw, ".md")
        check(first.name == f"sha256-{digest}.md", first)
        check(first.read_bytes() == raw and first.stat().st_mode & 0o222 == 0, first)
        second = module.publish_content_object(workspace, "lot-1.1", raw, ".md")
        check(second == first, second)

        foreign_raw = b"foreign bytes\n"
        foreign_digest = hashlib.sha256(foreign_raw).hexdigest()
        foreign = module.content_object_path(workspace, "lot-1.1", foreign_digest, ".md")
        foreign.write_bytes(b"different bytes\n")
        foreign.chmod(0o444)
        try:
            module.publish_content_object(workspace, "lot-1.1", foreign_raw, ".md")
        except ValueError:
            pass
        else:
            raise AssertionError("replaced a foreign content-addressed occupant")
        check(foreign.read_bytes() == b"different bytes\n", foreign)


@test
def allocation_and_pass_local_paths_bind_one_exact_generation():
    module = load_module(
        "correction_allocation", HERE / "prompts" / "common" / "correction_authority.py",
    )
    allocation = {
        "schema": 2,
        "built": "lot-1.1",
        "round": 1,
        "predecessor_supersession": None,
        "parent": {
            "position": 0,
            "generation_sha256": "a" * 64,
            "commit": "b" * 40,
            "gate": "c" * 64,
        },
        "pass": {
            "ordinal": 1,
            "opening": f"12:{'d' * 64}",
            "commit": "b" * 40,
            "gate": "c" * 64,
        },
        "items": [{
            "id": "F1",
            "sources": ["meaning/F2", "quality/F1"],
            "carries": ["B2/F1"],
        }],
        "refuted": ["unlooked/F3"],
        "admission": {
            "items": [{
                "id": "F1",
                "classification": "implementation-correction",
                "reason": "The fixes share one bounded implementation outcome.",
            }],
            "spec": "current-and-settled",
            "human_decisions": "settled",
            "controller_contract": "preserved",
            "ownership": "preserved",
            "decomposition": "preserved",
            "coordination": "bounded",
            "repetition": "independent",
            "reason": "The complete set remains local and bounded.",
        },
    }
    normalized = module.normalize_allocation(allocation)
    check(normalized == allocation, normalized)
    check(
        module.product_report_path("lot-1.1", 0, 1, "quality")
        == pathlib.PurePosixPath(
            "reports/product-review/lot-1/lot-1.1-c0-p1-quality.md",
        ),
        "the pass-local report path is wrong",
    )
    check(
        module.private_risk_history_path("lot-1.1", "quality")
        == pathlib.PurePosixPath(
            "reports/product-review/lot-1/lot-1.1-quality-risk-filtered.md",
        ),
        "the private history path is not stable",
    )
    check(module.occurrence_label(0, 1) == "c0-p1", "the occurrence label is wrong")

    invalid = json.loads(json.dumps(allocation))
    invalid["admission"]["items"][0]["id"] = "F2"
    for candidate in (
        invalid,
        {**allocation, "round": 2},
        {**allocation, "predecessor_supersession": "not-a-proof"},
    ):
        try:
            module.normalize_allocation(candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a malformed correction allocation")


@test
def review_generation_digest_has_one_finite_exact_preimage():
    module = load_module(
        "correction_generation", HERE / "prompts" / "common" / "correction_authority.py",
    )
    account = {
        "schema": 1,
        "kind": "built",
        "built": "lot-1.1",
        "position": 0,
        "origin": {
            "kind": "sublot",
            "opening": f"4:{'a' * 64}",
            "source": f"3:{'b' * 64}",
        },
        "plan": {"path": "docs/plans/run-lot-1.1-plan.md", "sha256": "c" * 64},
        "tasks": [{
            "task": 1,
            "attempt": 1,
            "commit": "d" * 40,
            "gate": "e" * 64,
            "success": f"6:{'f' * 64}",
        }],
        "terminal": f"7:{'1' * 64}",
        "commit": "d" * 40,
        "gate": "e" * 64,
        "final_checker_set_sha256": module.EMPTY_FINAL_CHECKER_SET_SHA256,
    }
    first = module.generation_sha256(account)
    second = module.generation_sha256(json.loads(json.dumps(account)))
    check(first == second and re.fullmatch(r"[0-9a-f]{64}", first), first)
    changed = json.loads(json.dumps(account))
    changed["commit"] = "2" * 40
    changed["tasks"][-1]["commit"] = "2" * 40
    check(module.generation_sha256(changed) != first, "the generation ignores its commit")
    for invalid in (
        {**account, "generation_sha256": first},
        {**account, "position": 1},
        {**account, "unknown": "value"},
    ):
        try:
            module.generation_sha256(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an invalid built-generation preimage")


def correction_obligation_source(module, *, checker="design", accepted_ids=None):
    return module.source_account({
        "source_proof": f"12:{'a' * 64}",
        "source_unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
        "source_contract_authority_sha256": "b" * 64,
        "source_execution_authority_sha256": "c" * 64,
        "owner_task": 2,
        "checker": checker,
        "accepted_ids": accepted_ids or [1, 3],
        "result_sha256": "d" * 64,
        "settlement": f"13:{'e' * 64}",
        "required_consumer_phase": f"first-{checker}-manifest",
    })


def correction_contract_map_assignment(module):
    return {
        "unit": {
            "kind": "task-contract-map",
            "operation": "f" * 64,
            "work_unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
            "target_task": 2,
            "document_kind": "correction-artifact",
        },
        "task": None,
        "phase": "publish-task-contract",
        "owner": "task-contract-map",
    }


@test
def final_checker_transition_has_one_finite_exact_preimage():
    module = load_module(
        "final_checker_obligations",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    empty = module.empty_set()
    source = correction_obligation_source(module)
    assignment = correction_contract_map_assignment(module)
    transition, output = module.materialize_transition(
        empty,
        additions=[{"source": source, "assignment": assignment}],
        dispositions=[],
        transfer_kind="final-checker-source",
    )

    replay = module.validate_transition(
        json.loads(json.dumps(empty)),
        json.loads(json.dumps(transition)),
        transfer_kind="final-checker-source",
    )
    check(replay == output, "independent transition replay changed the output set")
    check(transition["input_sha256"] == module.set_sha256(empty), transition)
    check(transition["output_sha256"] == module.set_sha256(output), transition)
    check(
        output["entries"][0]["assignment"]["mapping_proof"]
        == transition["transition_id"],
        output,
    )
    check(output["entries"][0]["transfers"] == [{
        "kind": "addition",
        "transition_id": transition["transition_id"],
        "from": None,
        "to": output["entries"][0]["assignment"],
    }], output)

    mutations = []
    for path, value in (
        (("transition_id",), "0" * 64),
        (("output_sha256",), "1" * 64),
        (("additions", 0, "assignment", "mapping_proof"), "2" * 64),
        (("dispositions",), [{"foreign": True}]),
    ):
        changed = json.loads(json.dumps(transition))
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        mutations.append(changed)
    mutations.append({**transition, "payload_sha256": "3" * 64})
    for changed in mutations:
        try:
            module.validate_transition(empty, changed, transfer_kind="final-checker-source")
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a changed final-checker transition")


@test
def final_checker_transition_composes_assignment_and_consumption():
    module = load_module(
        "final_checker_obligations_composition",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    source = correction_obligation_source(module, checker="code", accepted_ids=[2])
    first, mapped = module.materialize_transition(
        module.empty_set(),
        additions=[{
            "source": source,
            "assignment": correction_contract_map_assignment(module),
        }],
        dispositions=[],
        transfer_kind="final-checker-source",
    )
    obligation_id = source["obligation_id"]
    task_assignment = {
        "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
        "task": 2,
        "phase": "first-code-manifest",
        "owner": "task",
        "task_contract_sha256": "4" * 64,
    }
    second, assigned = module.materialize_transition(
        mapped,
        additions=[],
        dispositions=[{
            "obligation_id": obligation_id,
            "outcome": "deferred",
            "assignment": task_assignment,
            "evidence": None,
        }],
        transfer_kind="contract-mapped",
    )
    entry = assigned["entries"][0]
    check(entry["source"] == source, "the immutable obligation source changed")
    check(len(entry["transfers"]) == 2, entry)
    check(entry["transfers"][1]["from"] == mapped["entries"][0]["assignment"], entry)
    check(entry["transfers"][1]["to"] == entry["assignment"], entry)
    check(entry["assignment"]["mapping_proof"] == second["transition_id"], entry)

    evidence = {
        "manifest": f"20:{'5' * 64}",
        "success": f"21:{'6' * 64}",
    }
    third, consumed = module.materialize_transition(
        assigned,
        additions=[],
        dispositions=[{
            "obligation_id": obligation_id,
            "outcome": "consumed",
            "assignment": None,
            "evidence": evidence,
        }],
        transfer_kind="retry-consumed",
    )
    check(consumed == module.empty_set(), consumed)
    check(
        module.validate_transition(assigned, third, transfer_kind="retry-consumed")
        == consumed,
        third,
    )

    stale = json.loads(json.dumps(second))
    stale["dispositions"][0]["assignment"]["mapping_proof"] = first["transition_id"]
    try:
        module.validate_transition(mapped, stale, transfer_kind="contract-mapped")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a stale changed-assignment mapping proof")


@test
def escalation_item_authority_uses_the_current_consumer_task_exactly_once():
    module = load_module(
        "final_checker_obligations_escalation_item",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    source = correction_obligation_source(module)
    _addition, mapped = module.materialize_transition(
        module.empty_set(),
        additions=[{
            "source": source,
            "assignment": correction_contract_map_assignment(module),
        }],
        dispositions=[],
        transfer_kind="final-checker-source",
    )
    obligation_id = source["obligation_id"]
    _assignment, assigned = module.materialize_transition(
        mapped,
        additions=[],
        dispositions=[{
            "obligation_id": obligation_id,
            "outcome": "deferred",
            "assignment": {
                "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
                "task": 2,
                "phase": source["required_consumer_phase"],
                "owner": "task",
                "task_contract_sha256": "4" * 64,
            },
            "evidence": None,
        }],
        transfer_kind="contract-mapped",
    )
    member = assigned["entries"][0]
    check(
        module.escalation_item_for_member(
            member,
            [{"id": "F1", "tasks": [1]}, {"id": "F2", "tasks": [2]}],
        ) == "F2",
        "the escalation item followed the immutable source task instead of its consumer",
    )
    for items in (
        [{"id": "F1", "tasks": [1]}],
        [{"id": "F1", "tasks": [2]}, {"id": "F2", "tasks": [2]}],
    ):
        try:
            module.escalation_item_for_member(member, items)
        except ValueError:
            pass
        else:
            raise AssertionError("a retained escalation accepted zero or multiple items")


@test
def retained_authority_live_escalation_uses_the_current_consumer_task():
    obligations = load_module(
        "final_checker_obligations_retained_live",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    runner = load_module(
        "correction_rewind_retained_live",
        CONSTRUCTION / "correction_rewind.py",
    )
    source = correction_obligation_source(obligations)
    _source_transition, mapped = obligations.materialize_transition(
        obligations.empty_set(),
        additions=[{
            "source": source,
            "assignment": correction_contract_map_assignment(obligations),
        }],
        dispositions=[],
        transfer_kind="final-checker-source",
    )
    _task_transition, current = obligations.materialize_transition(
        mapped,
        additions=[],
        dispositions=[{
            "obligation_id": source["obligation_id"],
            "outcome": "deferred",
            "assignment": {
                "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
                "task": 1,
                "phase": source["required_consumer_phase"],
                "owner": "task",
                "task_contract_sha256": "4" * 64,
            },
            "evidence": None,
        }],
        transfer_kind="contract-mapped",
    )
    coverage = {"F1": [2], "F2": [1]}
    owner = {
        "built": "lot-1.1", "round": 1,
        "opening": f"1:{'1' * 64}",
        "latest_authority": f"2:{'2' * 64}",
        "previous_rewind": None,
        "cause": f"3:{'3' * 64}",
        "target": {"base_commit": "5" * 40},
        "crossed_authorities": [],
        "failed_transition": {
            "proof": f"4:{'4' * 64}",
            "transition_sha256": "6" * 64,
            "reason": "the retained transition has no exact conflict-free Git projection",
        },
        "current_set_sha256": obligations.set_sha256(current),
        "completed": [{"task": 1}],
        "current_commit": "7" * 40,
        "current_tree": "8" * 40,
        "current_gate": "9" * 64,
        "artifact_sha256": "a" * 64,
        "artifact_object": "corrections/lot-1.1/objects/sha256-a.json",
    }
    account = {
        "owner": owner,
        "owner_sha256": "b" * 64,
        "blocker_path": "corrections/lot-1.1/round-1-rewind-preservation.md",
    }
    blocker = {
        "owner_sha256": account["owner_sha256"],
        "opening": owner["opening"],
        "latest_authority": owner["latest_authority"],
        "previous_rewind": owner["previous_rewind"],
        "cause": owner["cause"],
        "target_commit": owner["target"]["base_commit"],
        "failed_transition": owner["failed_transition"]["proof"],
        "failed_transition_sha256": owner["failed_transition"]["transition_sha256"],
        "failure_reason": owner["failed_transition"]["reason"],
        "current_commit": owner["current_commit"],
        "current_tree": owner["current_tree"],
        "current_gate": owner["current_gate"],
        "items": [
            {
                "id": finding,
                "origin": f"correction/c1/{finding}",
                "accepted_contributions": [task for task in tasks if task == 1],
            }
            for finding, tasks in coverage.items()
        ],
        "required_outcome": "Publish the retained structural correction.",
    }

    with tempfile.TemporaryDirectory() as temporary:
        runner.WORKSPACE = pathlib.Path(temporary)
        blocker_path = runner.WORKSPACE / account["blocker_path"]
        blocker_path.parent.mkdir(parents=True)
        blocker_path.write_bytes(b"retained blocker\n")
        runner.parse_rewind_blocker = lambda *_args, **_kwargs: blocker
        runner.progress.journal_entries = lambda: []
        runner.progress.current_correction_contract_state = (
            lambda *_args, **_kwargs: {
                "artifact": {"source_finding_coverage": coverage},
            }
        )
        runner.progress.outstanding_final_checker_set = (
            lambda *_args, **_kwargs: current
        )
        runner.progress.final_checker_set_sha256 = obligations.set_sha256
        runner.progress.materialize_final_checker_transition = obligations.materialize_transition
        runner.escalation_terminal = lambda *_args: None
        published = []
        appended = []

        def publish(_workspace, _built, payload, _suffix):
            published.append(payload)
            return runner.content_object_path(
                runner.WORKSPACE, "lot-1.1", hashlib.sha256(payload).hexdigest(), ".md",
            )

        def normalize(_entries, event, _subject):
            output = obligations.validate_transition(
                current,
                event["retry_transition"],
                transfer_kind="retained-authority-escalation",
            )
            requirement = output["entries"][0]["assignment"]["consumer_requirement"]
            check(requirement["escalation_item"] == "F2", requirement)
            appended.append(event)

        runner.publish_content_object = publish
        runner.progress.normalize_correction_round_escalated = normalize
        runner.progress.cmd_note_with_lease = lambda *_args, **_kwargs: None
        runner.remove_marker = lambda *_args: None
        runner.finish_escalation(
            SimpleNamespace(built="lot-1.1", round=1),
            "retained-authority-test", object(), b"marker\n", account,
        )
        check(len(published) == 1 and len(appended) == 1, (published, appended))

        for label, changed_coverage in (
            ("absent", {"F1": [2], "F2": [2]}),
            ("ambiguous", {"F1": [1], "F2": [1]}),
        ):
            coverage.clear()
            coverage.update(changed_coverage)
            blocker["items"] = [
                {
                    "id": finding,
                    "origin": f"correction/c1/{finding}",
                    "accepted_contributions": [task for task in tasks if task == 1],
                }
                for finding, tasks in coverage.items()
            ]
            published.clear()
            appended.clear()
            try:
                runner.finish_escalation(
                    SimpleNamespace(built="lot-1.1", round=1),
                    "retained-authority-test", object(), b"marker\n", account,
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"published an {label} retained consumer item")
            check(
                not published and not appended,
                f"the {label} retained consumer item mutated durable authority",
            )


@test
def retained_authority_terminal_cleanup_authenticates_the_complete_marker_owner():
    runner = load_module(
        "correction_rewind_retained_terminal_cleanup",
        CONSTRUCTION / "correction_rewind.py",
    )
    owner = {
        "built": "lot-1.1", "round": 1,
        "opening": f"1:{'1' * 64}",
        "latest_authority": f"2:{'2' * 64}",
        "previous_rewind": None,
        "cause": f"3:{'3' * 64}",
        "target": {"base_commit": "4" * 40},
        "crossed_authorities": [],
        "failed_transition": {
            "proof": f"4:{'4' * 64}",
            "transition_sha256": "5" * 64,
            "reason": "the retained transition has no exact conflict-free Git projection",
        },
        "current_set_sha256": runner.progress.EMPTY_FINAL_CHECKER_SET_SHA256,
        "completed": [{
            "task": 1, "success": f"5:{'7' * 64}",
            "commit": "8" * 40, "gate": "9" * 64,
        }],
        "current_commit": "a" * 40,
        "current_tree": "b" * 40,
        "current_gate": "c" * 64,
        "artifact_sha256": "d" * 64,
        "artifact_object": "corrections/lot-1.1/objects/sha256-d.md",
        "current_authority_sha256": "e" * 64,
        "current_execution_authority_sha256": "f" * 64,
    }
    owner_sha256 = hashlib.sha256(
        json.dumps(owner, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    account = {
        "schema": 1,
        "operation": "retained-authority-terminal-cleanup",
        "disposition": "escalate",
        "phase": "blocker-required",
        "owner": owner,
        "owner_sha256": owner_sha256,
        "blocker_path": "corrections/lot-1.1/round-1-rewind-preservation.md",
    }
    blocker_data = {
        "artifact": account["blocker_path"],
        "sha256": "0" * 64,
        "object": "corrections/lot-1.1/objects/sha256-0.md",
    }
    event = {
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
        "crossed_authorities": [],
        "blocker": blocker_data,
        "completed_tasks": [1],
        "commit": owner["current_commit"],
        "tree": owner["current_tree"],
        "gate": owner["current_gate"],
        "artifact_sha256": owner["artifact_sha256"],
        "artifact_object": owner["artifact_object"],
        "items": [],
        "retry_transition": {},
    }
    terminal = {"kind": "correction.round.escalated", "data": event}

    with tempfile.TemporaryDirectory() as temporary:
        runner.WORKSPACE = pathlib.Path(temporary)
        object_path = runner.WORKSPACE / blocker_data["object"]
        object_path.parent.mkdir(parents=True)
        object_path.write_bytes(b"immutable blocker\n")
        runner.progress.journal_entries = lambda: [terminal]
        runner.progress.validate_correction_round_escalated_entry = lambda *_args: None
        runner.validate_content_object = lambda *_args, **_kwargs: object_path
        runner.parse_rewind_blocker = lambda *_args, **_kwargs: {
            "owner_sha256": owner_sha256,
        }
        runner.validate_escalation_marker(
            SimpleNamespace(built="lot-1.1", round=1),
            account["operation"], account,
        )
        removed = []
        runner.remove_marker = lambda payload: removed.append(payload)
        runner.finish_escalation(
            SimpleNamespace(built="lot-1.1", round=1),
            account["operation"], object(), b"exact marker\n", account,
        )
        check(removed == [b"exact marker\n"], removed)

        mutations = []
        changed_set = json.loads(json.dumps(account))
        changed_set["owner"]["current_set_sha256"] = "1" * 64
        mutations.append(("current set", changed_set))
        changed_failure = json.loads(json.dumps(account))
        changed_failure["owner"]["failed_transition"]["transition_sha256"] = "2" * 64
        mutations.append(("failed transition", changed_failure))
        changed_success = json.loads(json.dumps(account))
        changed_success["owner"]["completed"][0]["success"] = f"6:{'3' * 64}"
        mutations.append(("completed success", changed_success))
        for field, digest in (
            ("current_authority_sha256", "4" * 64),
            ("current_execution_authority_sha256", "5" * 64),
        ):
            changed = json.loads(json.dumps(account))
            changed["owner"][field] = digest
            mutations.append((field, changed))

        for label, changed in mutations:
            changed["owner_sha256"] = hashlib.sha256(
                json.dumps(
                    changed["owner"], sort_keys=True, separators=(",", ":"),
                ).encode(),
            ).hexdigest()
            try:
                runner.validate_escalation_marker(
                    SimpleNamespace(built="lot-1.1", round=1),
                    changed["operation"], changed,
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"removed a marker with changed {label}")



@test
def post_amendment_return_rejects_an_existing_item_owned_by_another_task():
    return_module = load_module(
        "correction_amendment_return_item_authority",
        CONSTRUCTION / "correction_amendment_return.py",
    )
    obligations_module = load_module(
        "final_checker_obligations_return_item_authority",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    source = correction_obligation_source(obligations_module)
    _addition, input_set = obligations_module.materialize_transition(
        obligations_module.empty_set(),
        additions=[{
            "source": source,
            "assignment": correction_contract_map_assignment(obligations_module),
        }],
        dispositions=[],
        transfer_kind="final-checker-source",
    )
    obligation_id = source["obligation_id"]
    amendment_commit = f"8:{'5' * 64}"
    current_artifact = {
        "built": "lot-1.1",
        "round": 1,
        "source_finding_coverage": {"F1": [1], "F2": [2]},
    }

    def transition_for(item):
        transition, _output = obligations_module.materialize_transition(
            input_set,
            additions=[],
            dispositions=[{
                "obligation_id": obligation_id,
                "outcome": "carried",
                "assignment": {
                    "unit": {
                        "kind": "correction-escalation",
                        "built": "lot-1.1",
                        "round": 1,
                        "producer": "post-amendment-return",
                        "amendment": amendment_commit,
                    },
                    "task": None,
                    "phase": "sublot-plan-consumer-map",
                    "owner": "escalation-tail",
                    "consumer_requirement": {
                        "obligation_id": obligation_id,
                        "checker": source["checker"],
                        "manifest_phase": source["required_consumer_phase"],
                        "remaining_outcome": "new sub-lot",
                        "escalation_item": item,
                    },
                },
                "evidence": None,
            }],
            transfer_kind="amendment-return",
        )
        return transition

    exact = transition_for("F2")
    return_module.validate_retry_transition(
        exact,
        input_set,
        "sublot",
        current_artifact,
        set(),
        amendment_commit=amendment_commit,
        required_sublot_outcome="new sub-lot",
        remaining_findings=["F1", "F2"],
    )

    try:
        return_module.validate_retry_transition(
            transition_for("F1"),
            input_set,
            "sublot",
            current_artifact,
            set(),
            amendment_commit=amendment_commit,
            required_sublot_outcome="new sub-lot",
            remaining_findings=["F1", "F2"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("a post-AMENDMENT return accepted another task's item")


@test
def structural_final_checker_assignment_owners_use_closed_producer_grammars():
    module = load_module(
        "final_checker_obligations_future_owners",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    source = correction_obligation_source(module)
    empty = module.empty_set()
    future_assignments = [
        {
            "unit": {"foreign": "unit"},
            "task": None,
            "phase": "anything",
            "owner": "escalation-tail",
        },
        {
            "unit": {"kind": "escalation-tail"},
            "task": None,
            "phase": "publish-escalation-tail",
            "owner": "escalation-tail",
        },
        {
            "unit": {"kind": "escalation-tail", "lot": "lot-1", "foreign": True},
            "task": None,
            "phase": "wrong-phase",
            "owner": "escalation-tail",
            "consumer_requirement": {"foreign": True},
        },
        {
            "unit": {"x": 1},
            "task": None,
            "phase": "wrong-phase",
            "owner": "sublot-plan",
            "consumer_requirement": {"foreign": True},
        },
        {
            "unit": {"kind": "sublot-plan"},
            "task": None,
            "phase": "publish-sublot-plan",
            "owner": "sublot-plan",
        },
        {
            "unit": {"kind": "sublot-plan", "lot": "lot-1", "extra": 1},
            "task": None,
            "phase": "publish-sublot-plan",
            "owner": "sublot-plan",
            "consumer_requirement": {"kind": "unknown"},
        },
    ]

    for assignment in future_assignments:
        for materialized in (False, True):
            candidate = json.loads(json.dumps(assignment))
            if materialized:
                candidate["mapping_proof"] = "9" * 64
            try:
                module.validate_assignment(candidate, materialized=materialized)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"accepted future {assignment['owner']} assignment: {candidate}"
                )

    for assignment in future_assignments[:1] + future_assignments[3:4]:
        transition_id = "8" * 64
        materialized = {**json.loads(json.dumps(assignment)), "mapping_proof": transition_id}
        output = {
            "schema": 1,
            "entries": [{
                "source": source,
                "assignment": materialized,
                "transfers": [{
                    "kind": "addition",
                    "transition_id": transition_id,
                    "from": None,
                    "to": materialized,
                }],
            }],
        }
        try:
            module.validate_set(output)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted materialized future {assignment['owner']} set")

        try:
            module.materialize_transition(
                empty,
                additions=[{"source": source, "assignment": assignment}],
                dispositions=[],
                transfer_kind="future-owner",
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"materialized future {assignment['owner']} transition")

        semantic = {
            "schema": 1,
            "input_sha256": module.set_sha256(empty),
            "additions": [{"source": source, "assignment": assignment}],
            "dispositions": [],
        }
        legacy_transition_id = module.canonical_sha256(semantic)
        legacy_assignment = {
            **json.loads(json.dumps(assignment)),
            "mapping_proof": legacy_transition_id,
        }
        legacy_output = {
            "schema": 1,
            "entries": [{
                "source": source,
                "assignment": legacy_assignment,
                "transfers": [{
                    "kind": "addition",
                    "transition_id": legacy_transition_id,
                    "from": None,
                    "to": legacy_assignment,
                }],
            }],
        }
        legacy_transition = {
            **semantic,
            "transition_id": legacy_transition_id,
            "additions": [{"source": source, "assignment": legacy_assignment}],
            "output_sha256": module.canonical_sha256(legacy_output),
        }
        try:
            module.validate_transition(
                empty, legacy_transition, transfer_kind="future-owner",
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"replayed future {assignment['owner']} transition")

    requirement = {
        "obligation_id": source["obligation_id"],
        "checker": "design",
        "manifest_phase": "first-design-manifest",
        "remaining_outcome": "Publish the structural correction.",
        "escalation_item": "F1",
    }
    escalation = {
        "unit": {
            "kind": "correction-escalation", "built": "lot-1.1", "round": 1,
            "producer": "post-amendment-return", "amendment": f"12:{'a' * 64}",
        },
        "task": None,
        "phase": "sublot-plan-consumer-map",
        "owner": "escalation-tail",
        "consumer_requirement": requirement,
    }
    opened, escalation_set = module.materialize_transition(
        empty,
        additions=[{"source": source, "assignment": escalation}],
        dispositions=[],
        transfer_kind="amendment-return",
    )
    check(module.validate_transition(
        empty, opened, transfer_kind="amendment-return",
    ) == escalation_set, opened)
    sublot = {
        "unit": {
            "kind": "sublot-plan", "lot": "lot-1.2", "source": f"13:{'b' * 64}",
        },
        "task": None,
        "phase": "publish-consumer-map",
        "owner": "sublot-plan",
        "consumer_requirement": requirement,
    }
    allocated, sublot_set = module.materialize_transition(
        escalation_set,
        additions=[],
        dispositions=[{
            "obligation_id": source["obligation_id"],
            "outcome": "carried", "assignment": sublot, "evidence": None,
        }],
        transfer_kind="sublot-allocation",
    )
    check(module.validate_transition(
        escalation_set, allocated, transfer_kind="sublot-allocation",
    ) == sublot_set, allocated)

    compatible = [
        {
            "unit": {"kind": "correction", "built": "lot-1.1", "round": 1},
            "task": 2,
            "phase": "first-design-manifest",
            "owner": "task",
            "task_contract_sha256": "4" * 64,
        },
        correction_contract_map_assignment(module),
        {
            "unit": {"kind": "amendment", "number": 2},
            "task": None,
            "phase": "publish-post-amendment-return",
            "owner": "amendment-return",
        },
    ]
    for assignment in compatible:
        check(
            module.validate_assignment(assignment, materialized=False) == assignment,
            assignment,
        )
        materialized = {**assignment, "mapping_proof": "7" * 64}
        check(module.semantic_assignment(materialized) == assignment, materialized)


@test
def amendment_return_consumer_requirement_refuses_until_its_producer_defines_it():
    module = load_module(
        "final_checker_obligations_amendment_return_requirement",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    source = correction_obligation_source(module)
    empty = module.empty_set()
    assignment = {
        "unit": {"kind": "amendment", "number": 2},
        "task": None,
        "phase": "publish-post-amendment-return",
        "owner": "amendment-return",
        "consumer_requirement": {"foreign": {"shape": True}},
    }

    try:
        module.validate_assignment(assignment, materialized=False)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted semantic amendment-return consumer requirement")

    transition_id = "8" * 64
    materialized = {**assignment, "mapping_proof": transition_id}
    output = {
        "schema": 1,
        "entries": [{
            "source": source,
            "assignment": materialized,
            "transfers": [{
                "kind": "addition",
                "transition_id": transition_id,
                "from": None,
                "to": materialized,
            }],
        }],
    }
    try:
        module.validate_set(output)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted materialized amendment-return consumer requirement")

    try:
        module.materialize_transition(
            empty,
            additions=[{"source": source, "assignment": assignment}],
            dispositions=[],
            transfer_kind="amendment-return",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("materialized amendment-return consumer requirement")

    semantic = {
        "schema": 1,
        "input_sha256": module.set_sha256(empty),
        "additions": [{"source": source, "assignment": assignment}],
        "dispositions": [],
    }
    legacy_transition_id = module.canonical_sha256(semantic)
    legacy_assignment = {
        **json.loads(json.dumps(assignment)),
        "mapping_proof": legacy_transition_id,
    }
    legacy_output = {
        "schema": 1,
        "entries": [{
            "source": source,
            "assignment": legacy_assignment,
            "transfers": [{
                "kind": "addition",
                "transition_id": legacy_transition_id,
                "from": None,
                "to": legacy_assignment,
            }],
        }],
    }
    legacy_transition = {
        **semantic,
        "transition_id": legacy_transition_id,
        "additions": [{"source": source, "assignment": legacy_assignment}],
        "output_sha256": module.canonical_sha256(legacy_output),
    }
    try:
        module.validate_transition(
            empty, legacy_transition, transfer_kind="amendment-return",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("replayed amendment-return consumer requirement")

    compatible = {key: value for key, value in assignment.items()
                  if key != "consumer_requirement"}
    check(
        module.validate_assignment(compatible, materialized=False) == compatible,
        compatible,
    )


@test
def repeated_amendments_compose_every_pending_and_new_obligation():
    module = load_module(
        "final_checker_obligations_repeated_amendments",
        HERE / "prompts" / "common" / "final_checker_obligations.py",
    )
    first_source = correction_obligation_source(module, accepted_ids=[1])
    second_source = correction_obligation_source(
        module, checker="code", accepted_ids=[2],
    )
    third_source = correction_obligation_source(module, accepted_ids=[3])
    unit = {"kind": "correction", "built": "lot-1.1", "round": 1}

    task_assignments = [
        {
            "unit": unit,
            "task": 1,
            "phase": first_source["required_consumer_phase"],
            "owner": "task",
            "task_contract_sha256": "1" * 64,
        },
        {
            "unit": unit,
            "task": 2,
            "phase": second_source["required_consumer_phase"],
            "owner": "task",
            "task_contract_sha256": "2" * 64,
        },
    ]
    initial_additions = [
        {"source": first_source, "assignment": correction_contract_map_assignment(module)},
        {"source": second_source, "assignment": correction_contract_map_assignment(module)},
    ]
    initial_additions.sort(key=lambda item: item["source"]["obligation_id"])
    assignments_by_id = {
        first_source["obligation_id"]: task_assignments[0],
        second_source["obligation_id"]: task_assignments[1],
    }
    _initial_transition, initial = module.materialize_transition(
        module.empty_set(),
        additions=initial_additions,
        dispositions=[],
        transfer_kind="final-checker-failure",
    )
    _mapped_transition, mapped = module.materialize_transition(
        initial,
        additions=[],
        dispositions=[{
            "obligation_id": member["source"]["obligation_id"],
            "outcome": "deferred",
            "assignment": assignments_by_id[member["source"]["obligation_id"]],
            "evidence": None,
        } for member in initial["entries"]],
        transfer_kind="contract-mapped",
    )

    first_return_owner = {
        "unit": {"kind": "amendment", "number": 1},
        "task": None,
        "phase": "publish-post-amendment-return",
        "owner": "amendment-return",
    }
    first_opening, first_suspended = module.materialize_transition(
        mapped,
        additions=[],
        dispositions=[{
            "obligation_id": member["source"]["obligation_id"],
            "outcome": "carried",
            "assignment": first_return_owner,
            "evidence": None,
        } for member in mapped["entries"]],
        transfer_kind="amendment-opening",
    )
    check(module.validate_transition(
        mapped, first_opening, transfer_kind="amendment-opening",
    ) == first_suspended, first_opening)
    first_return, first_rebased = module.materialize_transition(
        first_suspended,
        additions=[],
        dispositions=[{
            "obligation_id": member["source"]["obligation_id"],
            "outcome": "deferred",
            "assignment": assignments_by_id[member["source"]["obligation_id"]],
            "evidence": None,
        } for member in first_suspended["entries"]],
        transfer_kind="amendment-return",
    )
    check(module.validate_transition(
        first_suspended, first_return, transfer_kind="amendment-return",
    ) == first_rebased, first_return)

    second_return_owner = {
        "unit": {"kind": "amendment", "number": 2},
        "task": None,
        "phase": "publish-post-amendment-return",
        "owner": "amendment-return",
    }
    second_opening, second_suspended = module.materialize_transition(
        first_rebased,
        additions=[{"source": third_source, "assignment": second_return_owner}],
        dispositions=[{
            "obligation_id": member["source"]["obligation_id"],
            "outcome": "carried",
            "assignment": second_return_owner,
            "evidence": None,
        } for member in first_rebased["entries"]],
        transfer_kind="amendment-opening",
    )
    check(module.validate_transition(
        first_rebased, second_opening, transfer_kind="amendment-opening",
    ) == second_suspended, second_opening)
    members = {entry["source"]["obligation_id"]: entry for entry in second_suspended["entries"]}
    dispositions = []
    for source, task_number, digest in (
        (first_source, 1, "5" * 64),
        (third_source, 2, "6" * 64),
    ):
        dispositions.append({
            "obligation_id": source["obligation_id"],
            "outcome": "deferred",
            "assignment": {
                "unit": unit,
                "task": task_number,
                "phase": source["required_consumer_phase"],
                "owner": "task",
                "task_contract_sha256": digest,
            },
            "evidence": None,
        })
    dispositions.append({
        "obligation_id": second_source["obligation_id"],
        "outcome": "absorbed",
        "assignment": None,
        "evidence": {"amendment_item": f"42:{'7' * 64}"},
    })
    dispositions.sort(key=lambda item: item["obligation_id"])
    second_return, output = module.materialize_transition(
        second_suspended,
        additions=[],
        dispositions=dispositions,
        transfer_kind="amendment-return",
    )
    check(module.validate_transition(
        second_suspended, second_return, transfer_kind="amendment-return",
    ) == output, second_return)
    check(len(output["entries"]) == 2, output)
    check(first_source["obligation_id"] in members
          and len(next(entry for entry in output["entries"]
                       if entry["source"] == first_source)["transfers"]) == 6,
          output)

    incomplete = json.loads(json.dumps(second_opening))
    incomplete["dispositions"] = incomplete["dispositions"][:-1]
    try:
        module.validate_transition(
            first_rebased, incomplete, transfer_kind="amendment-opening",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("a repeated AMENDMENT dropped one pending obligation")


def main():
    failures = 0
    for function in TESTS:
        try:
            function()
            print(f"ok    {function.__name__}")
        except Exception:  # noqa: BLE001 - the test runner reports every case failure
            failures += 1
            print(f"FAIL  {function.__name__}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures} of {len(TESTS)} tests failed")
        raise SystemExit(1)
    print(f"\nall {len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
