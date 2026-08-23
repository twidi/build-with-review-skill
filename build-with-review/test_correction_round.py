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
import tempfile
import traceback

HERE = pathlib.Path(__file__).resolve().parent
CONSTRUCTION = HERE / "prompts" / "construction"
TESTS = []


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
    remaining = "F1: task 1"
    removed = "2"
    task_projection = "Task 1: prior task 3 · findings F1\n"
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
    if state != "active":
        raw = raw.replace("State: active", f"State: {state}", 1)
        start = raw.index("---\n\n## Task 1")
        raw = raw[:start]
    return raw.encode()


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
    check(active["finding_coverage"] == {"F1": [1]}, active)
    check(active["accepted_contributions"][0]["outcome"] == "preserved", active)
    check(active["task_projection"]["remaining"][0]["prior_tasks"] == [3], active)

    resolved = module.parse_artifact_bytes(schema_two_artifact(state="resolved"))
    check(resolved["state"] == "resolved" and not resolved["tasks"], resolved)
    check(set(resolved["absorbed_findings"]) == {"F1", "F2"}, resolved)
    escalating = module.parse_artifact_bytes(schema_two_artifact(state="escalating"))
    check(escalating["state"] == "escalating" and not escalating["tasks"], escalating)
    check(escalating["finding_coverage"] == {"F1": [1]}, escalating)

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
