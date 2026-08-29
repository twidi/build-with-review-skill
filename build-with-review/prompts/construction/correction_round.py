#!/usr/bin/env python3
"""Parse and authenticate one Correction Round artifact."""

import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import re
import sys

LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
HASH_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
PROOF_RE = re.compile(r"0|[1-9][0-9]*:[0-9a-f]{64}")
FINDING_RE = re.compile(r"F([1-9][0-9]*)")
TASK_HEADING_RE = re.compile(r"## Task ([1-9][0-9]*) - (\S(?:.*\S)?)")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
MAX_ARTIFACT_BYTES = 1_048_576
IDENTITY_FIELDS = (
    "Built unit",
    "Correction round",
    "Parent position",
    "Parent generation SHA-256",
    "Source reviewed commit",
    "Source accepted gate",
    "Correction base commit",
    "Correction base gate",
    "Source pass",
    "Source opening",
    "Source findings",
    "Source findings SHA-256",
)
ROUTE_FIELDS = (
    "Spec",
    "Human decisions",
    "Controller contract",
    "Ownership",
    "Decomposition",
    "Coordination",
    "Repetition",
    "Reason",
)
ROUTE_FIXED = {
    "Spec": "current and settled",
    "Human decisions": "settled",
    "Controller contract": "preserved",
    "Ownership": "preserved",
    "Decomposition": "preserved",
    "Coordination": "bounded",
}
REPETITION_VALUES = {"independent", "reassessed-bounded"}


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value):
    return sha256(canonical_bytes(value))


def structural_markdown_lines(lines):
    structural = set()
    fence_character = None
    fence_length = 0
    for index, raw in enumerate(lines):
        line = raw.rstrip("\r\n")
        if fence_character is not None:
            if re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                line,
            ):
                fence_character = None
                fence_length = 0
            continue
        match = FENCE_OPEN_RE.fullmatch(line)
        if match:
            marker, info = match.groups()
            if marker[0] != "`" or "`" not in info:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
        structural.add(index)
    return structural


def is_commonmark_atx_heading(raw):
    return ATX_HEADING_RE.match(raw.rstrip("\r\n")) is not None


def nonblank(lines, start=0, end=None):
    end = len(lines) if end is None else end
    return [index for index in range(start, end) if lines[index].strip()]


def parse_field(line, expected):
    prefix = f"{expected}: "
    if not line.startswith(prefix):
        raise ValueError(f"expected {expected}")
    value = line[len(prefix):]
    if not value or value != value.strip():
        raise ValueError(f"{expected} has an invalid value")
    return value


def parse_number_list(value, *, prefix=None, subject):
    if value == "-":
        return []
    values = value.split(", ")
    if ", ".join(values) != value:
        raise ValueError(f"{subject} is not canonical")
    parsed = []
    for item in values:
        if prefix:
            match = re.fullmatch(rf"{re.escape(prefix)}([1-9][0-9]*)", item)
            if not match:
                raise ValueError(f"{subject} has an invalid identity")
            parsed.append(int(match.group(1)))
        elif not re.fullmatch(r"[1-9][0-9]*", item):
            raise ValueError(f"{subject} has an invalid number")
        else:
            parsed.append(int(item))
    if parsed != sorted(set(parsed)):
        raise ValueError(f"{subject} is not sorted and unique")
    return parsed


def parse_hash_list(value, subject):
    if value == "-":
        return []
    values = value.split(", ")
    if ", ".join(values) != value or values != sorted(set(values)):
        raise ValueError(f"{subject} is not sorted and unique")
    if any(not HASH_RE.fullmatch(item) for item in values):
        raise ValueError(f"{subject} has an invalid identity")
    return values


def parse_finding_account(lines, structural, cursor, heading):
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines) or cursor not in structural \
            or lines[cursor].rstrip("\n") != heading:
        raise ValueError(f"the Correction Round artifact has no exact {heading[3:]}")
    cursor += 1
    account = {}
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        line = lines[cursor].rstrip("\n")
        if cursor in structural and (line == "---" or line.startswith("## ")):
            break
        match = re.fullmatch(r"(F[1-9][0-9]*): (task|tasks) (.+)", line)
        if not match:
            raise ValueError(f"the {heading[3:]} has an invalid line")
        finding, grammar, values = match.groups()
        tasks = parse_number_list(values, subject="the finding task account")
        if not tasks or (grammar == "task" and len(tasks) != 1) \
                or (grammar == "tasks" and len(tasks) < 2):
            raise ValueError(f"the {heading[3:]} has invalid task grammar")
        if finding in account:
            raise ValueError(f"the {heading[3:]} repeats a finding")
        account[finding] = tasks
        cursor += 1
    numbers = [int(FINDING_RE.fullmatch(item).group(1)) for item in account]
    if numbers != sorted(numbers):
        raise ValueError(f"the {heading[3:]} is not sorted")
    return account, cursor


def parse_schema_two_projection(lines, structural, cursor, source_coverage):
    def expect_heading(expected):
        nonlocal cursor
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines) or cursor not in structural \
                or lines[cursor].rstrip("\n") != expected:
            raise ValueError(f"the schema-2 artifact has no exact {expected[3:]}")
        cursor += 1

    expect_heading("## Absorbed findings")
    absorbed = {}
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        line = lines[cursor].rstrip("\n")
        if cursor in structural and line.startswith("## "):
            break
        match = re.fullmatch(r"(F[1-9][0-9]*): (\S(?:.*\S)?)", line)
        if not match or match.group(1) in absorbed:
            raise ValueError("the Absorbed findings account is malformed")
        absorbed[match.group(1)] = match.group(2)
        cursor += 1

    remaining, cursor = parse_finding_account(
        lines, structural, cursor, "## Remaining finding coverage",
    )
    expect_heading("## Accepted contributions")
    contributions = []
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        line = lines[cursor].rstrip("\n")
        if cursor in structural and line.startswith("## "):
            break
        match = re.fullmatch(
            r"Task ([1-9][0-9]*): ([0-9]+:[0-9a-f]{64}) · ([0-9a-f]{40,64})"
            r" · ([0-9a-f]{64}) · (preserved|rewound ([0-9]+:[0-9a-f]{64}))",
            line,
        )
        if not match:
            raise ValueError("the Accepted contributions account is malformed")
        contributions.append({
            "task": int(match.group(1)),
            "success": match.group(2),
            "commit": match.group(3),
            "gate": match.group(4),
            "outcome": "rewound" if match.group(6) else "preserved",
            "rewind": match.group(6),
        })
        cursor += 1
    contribution_tasks = [item["task"] for item in contributions]
    if contribution_tasks != sorted(set(contribution_tasks)):
        raise ValueError("the Accepted contributions account is not sorted and unique")

    expect_heading("## Task projection")
    projection_lines = []
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        line = lines[cursor].rstrip("\n")
        if cursor in structural and line == "---":
            break
        if cursor in structural and line.startswith("## "):
            break
        projection_lines.append(line)
        cursor += 1
    if len(projection_lines) < 2:
        raise ValueError("the Task projection is incomplete")
    preserved = parse_number_list(
        parse_field(projection_lines[0], "Preserved"), subject="the preserved task account",
    )
    if preserved != list(range(1, len(preserved) + 1)):
        raise ValueError("the preserved task account is not one exact prefix")
    removed = parse_number_list(
        parse_field(projection_lines[1], "Removed"), subject="the removed task account",
    )
    projected = []
    first_remaining_task = len(preserved) + 1
    for expected_task, line in enumerate(projection_lines[2:], first_remaining_task):
        match = re.fullmatch(
            r"Task ([1-9][0-9]*): prior (task|tasks) ([1-9][0-9]*(?:, [1-9][0-9]*)*)"
            r" · findings (F[1-9][0-9]*(?:, F[1-9][0-9]*)*)",
            line,
        )
        if not match or int(match.group(1)) != expected_task:
            raise ValueError("the remaining Task projection is not exact and sequential")
        prior = parse_number_list(match.group(3), subject="the prior task account")
        findings = parse_number_list(
            match.group(4), prefix="F", subject="the projected finding account",
        )
        projected.append({
            "task": expected_task,
            "prior_tasks": prior,
            "findings": [f"F{number}" for number in findings],
        })

    source_findings = set(source_coverage)
    absorbed_findings = set(absorbed)
    remaining_findings = set(remaining)
    if absorbed_findings & remaining_findings \
            or absorbed_findings | remaining_findings != source_findings:
        raise ValueError("the absorbed and remaining finding accounts are not exhaustive")
    source_tasks = {
        task for owners in source_coverage.values() for task in owners
    }
    projected_prior = {
        task for item in projected for task in item["prior_tasks"]
    }
    if set(preserved) & set(removed) \
            or set(preserved) & projected_prior \
            or set(removed) & projected_prior \
            or set(preserved) | set(removed) | projected_prior != source_tasks:
        raise ValueError("the prior task projection is not exhaustive")
    preserved_contributions = {
        item["task"] for item in contributions if item["outcome"] == "preserved"
    }
    if preserved_contributions != set(preserved):
        raise ValueError("the preserved task and contribution accounts disagree")
    return {
        "absorbed": absorbed,
        "remaining": remaining,
        "contributions": contributions,
        "projection": {
            "preserved": preserved,
            "removed": removed,
            "remaining": projected,
        },
    }, cursor


def exact_section(lines, structural, start, end, heading, *, required):
    positions = [
        index for index in range(start, end)
        if index in structural and lines[index].rstrip("\r\n") == heading
    ]
    if len(positions) > 1:
        raise ValueError(f"the task has more than one {heading} section")
    if not positions:
        if required:
            raise ValueError(f"the task has no {heading} section")
        return None, None
    section_start = positions[0]
    section_end = next(
        (
            index for index in range(section_start + 1, end)
            if index in structural and is_commonmark_atx_heading(lines[index])
        ),
        end,
    )
    content_end = section_end
    while content_end > section_start + 1 and not lines[content_end - 1].strip():
        content_end -= 1
    content = ("".join(lines[section_start:content_end]).rstrip("\r\n") + "\n").encode()
    return (section_start, section_end), content


def parse_task(lines, structural, start, end, expected_task):
    heading = lines[start].rstrip("\r\n")
    match = TASK_HEADING_RE.fullmatch(heading)
    if not match or int(match.group(1)) != expected_task:
        raise ValueError("the task headings are not exact and sequential")
    title = match.group(2)
    owned_headings = [
        (index, lines[index].rstrip("\r\n"))
        for index in range(start + 1, end)
        if index in structural and is_commonmark_atx_heading(lines[index])
    ]
    expected_headings = ["### Design"]
    if any(value == "### Disagreement" for _, value in owned_headings):
        expected_headings.append("### Disagreement")
    if [value for _, value in owned_headings] != expected_headings:
        raise ValueError(
            f"Task {expected_task} does not have the exact Design then optional Disagreement structure",
        )
    design_range, design = exact_section(
        lines, structural, start + 1, end, "### Design", required=True,
    )
    disagreement_range, disagreement = exact_section(
        lines, structural, start + 1, end, "### Disagreement", required=False,
    )
    section_starts = [item[0] for item in (design_range, disagreement_range) if item]
    contract_end = min(section_starts)
    indexes = nonblank(lines, start + 1, contract_end)
    if len(indexes) < 6:
        raise ValueError(f"Task {expected_task} has an incomplete controller contract")
    cursor = 0
    covers = parse_number_list(
        parse_field(lines[indexes[cursor]].rstrip("\r\n"), "Covers"),
        prefix="F", subject="the task finding account",
    )
    cursor += 1
    if not covers:
        raise ValueError(f"Task {expected_task} covers no finding")
    dependencies = parse_number_list(
        parse_field(lines[indexes[cursor]].rstrip("\r\n"), "Depends on"),
        subject="the task dependency account",
    )
    cursor += 1
    if any(dependency >= expected_task for dependency in dependencies):
        raise ValueError(f"Task {expected_task} has a non-backward dependency")
    obligations = parse_hash_list(
        parse_field(
            lines[indexes[cursor]].rstrip("\r\n"),
            "Consumes final-checker obligations",
        ),
        "the final-checker consumer account",
    )
    cursor += 1
    if lines[indexes[cursor]].rstrip("\r\n") != "Achieves:":
        raise ValueError(f"Task {expected_task} has no exact Achieves block")
    cursor += 1
    achieves = []
    while cursor < len(indexes) and lines[indexes[cursor]].startswith("  - "):
        outcome = lines[indexes[cursor]].rstrip("\r\n")[4:]
        if not outcome or outcome != outcome.strip():
            raise ValueError(f"Task {expected_task} has an invalid Achieves item")
        achieves.append(outcome)
        cursor += 1
    if not achieves or cursor >= len(indexes):
        raise ValueError(f"Task {expected_task} has an empty Achieves block")
    files = parse_field(lines[indexes[cursor]].rstrip("\r\n"), "Files")
    cursor += 1
    if cursor >= len(indexes):
        raise ValueError(f"Task {expected_task} has no To verify field")
    to_verify = parse_field(lines[indexes[cursor]].rstrip("\r\n"), "To verify")
    cursor += 1
    if cursor != len(indexes):
        raise ValueError(f"Task {expected_task} has unexpected controller prose")

    design_contract = {
        "schema": 1,
        "achieves": achieves,
        "files": files,
        "to_verify": to_verify,
    }
    consumer_account = {"schema": 1, "obligation_ids": obligations}
    design_contract_sha256 = canonical_sha256(design_contract)
    consumer_account_sha256 = canonical_sha256(consumer_account)
    task_contract = {
        "schema": 1,
        "design_contract_sha256": design_contract_sha256,
        "consumer_account_sha256": consumer_account_sha256,
    }
    return {
        "task": expected_task,
        "title": title,
        "covers": [f"F{number}" for number in covers],
        "depends_on": dependencies,
        "obligation_ids": obligations,
        "achieves": achieves,
        "files": files,
        "to_verify": to_verify,
        "design_contract_sha256": design_contract_sha256,
        "consumer_account_sha256": consumer_account_sha256,
        "task_contract_sha256": canonical_sha256(task_contract),
        "design_sha256": sha256(design),
        "disagreement_sha256": sha256(disagreement) if disagreement else None,
    }


def parse_artifact_bytes(raw, *, expected_built=None, expected_round=None):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("the Correction Round artifact has invalid bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"the Correction Round artifact is not UTF-8: {exc}") from exc
    if "\r" in text or not text.endswith("\n"):
        raise ValueError("the Correction Round artifact has non-canonical line endings")
    lines = text.splitlines(keepends=True)
    structural = structural_markdown_lines(lines)
    indexes = nonblank(lines)
    if not indexes or indexes[0] != 0:
        raise ValueError("the Correction Round artifact has no exact title")
    title_match = re.fullmatch(
        r"# (\S(?:.*\S)?) — (lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?) correction round ([1-9][0-9]*)",
        lines[0].rstrip("\n"),
    )
    if not title_match:
        raise ValueError("the Correction Round artifact has an invalid title")
    subject, title_built, title_round = title_match.group(1), title_match.group(2), int(title_match.group(3))

    cursor = 1
    metadata = {}
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    schema_value = parse_field(lines[cursor].rstrip("\n"), "Schema")
    if schema_value not in ("1", "2"):
        raise ValueError("the Correction Round artifact uses an unknown schema")
    schema = int(schema_value)
    metadata["Schema"] = schema_value
    cursor += 1
    state = "active"
    amendment = None
    amendment_opening = None
    amendment_commit = None
    if schema == 2:
        extra_fields = ("State", "Amendment", "Amendment opening", "Amendment commit")
        extra = {}
        for field in extra_fields:
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            extra[field] = parse_field(lines[cursor].rstrip("\n"), field)
            cursor += 1
        state = extra["State"]
        if state not in ("active", "resolved", "escalating"):
            raise ValueError("the schema-2 Correction Round state is invalid")
        if not re.fullmatch(r"[1-9][0-9]*", extra["Amendment"]):
            raise ValueError("the schema-2 Amendment identity is invalid")
        amendment = int(extra["Amendment"])
        amendment_opening = extra["Amendment opening"]
        amendment_commit = extra["Amendment commit"]
        if not PROOF_RE.fullmatch(amendment_opening) \
                or not PROOF_RE.fullmatch(amendment_commit):
            raise ValueError("the schema-2 Amendment proof is malformed")
        metadata.update(extra)
    for field in IDENTITY_FIELDS:
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines) or cursor not in structural:
            raise ValueError(f"the Correction Round artifact has no {field}")
        metadata[field] = parse_field(lines[cursor].rstrip("\n"), field)
        cursor += 1
    built = metadata["Built unit"]
    if not LOT_RE.fullmatch(built) or built != title_built:
        raise ValueError("the built unit does not match the artifact title")
    if not re.fullmatch(r"[1-9][0-9]*", metadata["Correction round"]):
        raise ValueError("the Correction Round identity is malformed")
    round_number = int(metadata["Correction round"])
    if round_number != title_round:
        raise ValueError("the Correction Round identity does not match the title")
    if expected_built is not None and built != expected_built:
        raise ValueError("the artifact belongs to another built unit")
    if expected_round is not None and round_number != expected_round:
        raise ValueError("the artifact belongs to another correction round")
    parent_match = re.fullmatch(r"c([0-9]+)", metadata["Parent position"])
    if not parent_match or int(parent_match.group(1)) != round_number - 1:
        raise ValueError("the parent correction position is invalid")
    for field in (
        "Parent generation SHA-256", "Source accepted gate", "Correction base gate",
        "Source findings SHA-256",
    ):
        if not HASH_RE.fullmatch(metadata[field]):
            raise ValueError(f"{field} is malformed")
    if not PROOF_RE.fullmatch(metadata["Source opening"]):
        raise ValueError("Source opening is malformed")
    for field in ("Source reviewed commit", "Correction base commit"):
        if not COMMIT_RE.fullmatch(metadata[field]):
            raise ValueError(f"{field} is malformed")
    if not re.fullmatch(r"p[1-9][0-9]*", metadata["Source pass"]):
        raise ValueError("the source pass is malformed")
    root = built.split(".", 1)[0]
    expected_source = (
        f"reports/product-review/{root}/{built}-{metadata['Parent position']}-"
        f"{metadata['Source pass']}-confirmed.md"
    )
    if metadata["Source findings"] != expected_source:
        raise ValueError("the source finding path is not canonical")

    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines) or lines[cursor].rstrip("\n") != "## Route account":
        raise ValueError("the Correction Round artifact has no exact Route account")
    cursor += 1
    route = {}
    for field in ROUTE_FIELDS:
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        route[field] = parse_field(lines[cursor].rstrip("\n"), field)
        cursor += 1
    for field, value in ROUTE_FIXED.items():
        if route[field] != value:
            raise ValueError(f"the Route account has an invalid {field} value")
    if route["Repetition"] not in REPETITION_VALUES:
        raise ValueError("the Route account has an invalid Repetition value")

    source_coverage, cursor = parse_finding_account(
        lines, structural, cursor, "## Finding coverage",
    )
    finding_numbers = [int(FINDING_RE.fullmatch(item).group(1)) for item in source_coverage]
    if finding_numbers != list(range(1, len(finding_numbers) + 1)):
        raise ValueError("the Finding coverage is not exact and sequential")

    schema_two = None
    coverage = source_coverage
    if schema == 2:
        schema_two, cursor = parse_schema_two_projection(
            lines, structural, cursor, source_coverage,
        )
        coverage = schema_two["remaining"]

    task_starts = [
        index for index in range(cursor, len(lines))
        if index in structural and TASK_HEADING_RE.fullmatch(lines[index].rstrip("\n"))
    ]
    if state == "active" and not task_starts:
        raise ValueError("the Correction Round artifact has no task")
    if state == "active" and not coverage:
        raise ValueError("the active Correction Round artifact has no remaining finding")
    if state != "active" and task_starts:
        raise ValueError(f"the {state} Correction Round artifact has runnable tasks")
    if state == "resolved" and coverage:
        raise ValueError("the resolved Correction Round artifact has remaining findings")
    if state == "escalating" and not coverage:
        raise ValueError("the escalating Correction Round artifact has no remaining finding")
    tasks = []
    if task_starts:
        first_task = schema_two["projection"]["remaining"][0]["task"] \
            if schema_two else 1
        separators = []
        for start in task_starts:
            previous = start - 1
            while previous >= cursor and not lines[previous].strip():
                previous -= 1
            if previous < cursor or previous not in structural \
                    or lines[previous].rstrip("\r\n") != "---":
                raise ValueError("a Correction Round task has no exact separator")
            separators.append(previous)
        if nonblank(lines, cursor, task_starts[0]) != [separators[0]]:
            raise ValueError("the Correction Round root has unowned bytes before its tasks")
        for position, start in enumerate(task_starts):
            if nonblank(lines, separators[position] + 1, start):
                raise ValueError("a Correction Round task separator has trailing prose")
            end = separators[position + 1] \
                if position + 1 < len(separators) else len(lines)
            tasks.append(parse_task(
                lines, structural, start, end, first_task + position,
            ))
    elif nonblank(lines, cursor):
        raise ValueError("the Correction Round root has unowned trailing bytes")
    if state == "active":
        task_ids = {task["task"] for task in tasks}
        for finding, owners in coverage.items():
            if any(owner not in task_ids for owner in owners):
                raise ValueError(f"{finding} names an unknown task")
        task_coverage = {task["task"]: set(task["covers"]) for task in tasks}
        for finding, owners in coverage.items():
            for owner in owners:
                if finding not in task_coverage[owner]:
                    raise ValueError("the finding and task coverage accounts disagree")
        for task in tasks:
            expected_findings = {
                finding for finding, owners in coverage.items() if task["task"] in owners
            }
            if set(task["covers"]) != expected_findings:
                raise ValueError("the task and finding coverage accounts disagree")

    if schema == 2:
        projected = schema_two["projection"]["remaining"]
        if [item["task"] for item in projected] != [task["task"] for task in tasks]:
            raise ValueError("the Task projection and runnable tasks disagree")
        for item, task in zip(projected, tasks):
            if item["findings"] != task["covers"]:
                raise ValueError("the Task projection and runnable finding accounts disagree")

    manifest = {
        "schema": schema,
        "tasks": [
            {
                "task": task["task"],
                "title": task["title"],
                "findings": task["covers"],
                "depends_on": task["depends_on"],
            }
            for task in tasks
        ],
    }
    controller = {
        "schema": schema,
        "built": built,
        "round": round_number,
        "metadata": metadata,
        "route": route,
        "source_finding_coverage": source_coverage,
        "finding_coverage": coverage,
        "tasks": [
            {
                key: task[key]
                for key in (
                    "task", "title", "covers", "depends_on", "obligation_ids",
                    "achieves", "files", "to_verify",
                )
            }
            for task in tasks
        ],
    }
    return {
        "schema": schema,
        "state": state,
        "subject": subject,
        "built": built,
        "round": round_number,
        "parent_position": metadata["Parent position"],
        "identity": {
            "parent_generation_sha256": metadata["Parent generation SHA-256"],
            "source_reviewed_commit": metadata["Source reviewed commit"],
            "source_accepted_gate": metadata["Source accepted gate"],
            "correction_base_commit": metadata["Correction base commit"],
            "correction_base_gate": metadata["Correction base gate"],
            "source_pass": int(metadata["Source pass"][1:]),
            "source_opening": metadata["Source opening"],
        },
        "source_findings_path": metadata["Source findings"],
        "source_findings_sha256": metadata["Source findings SHA-256"],
        "source_findings": list(source_coverage),
        "source_finding_coverage": source_coverage,
        "finding_coverage": coverage,
        "route": route,
        "tasks": tasks,
        "manifest_sha256": canonical_sha256(manifest),
        "controller_sha256": canonical_sha256(controller),
        "artifact_sha256": sha256(raw),
        "amendment": amendment,
        "amendment_opening": amendment_opening,
        "amendment_commit": amendment_commit,
        "absorbed_findings": schema_two["absorbed"] if schema_two else {},
        "accepted_contributions": schema_two["contributions"] if schema_two else [],
        "task_projection": schema_two["projection"] if schema_two else None,
    }


def parse_artifact(path, *, expected_built=None, expected_round=None):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("the Correction Round artifact is not one real regular file")
    return parse_artifact_bytes(
        path.read_bytes(), expected_built=expected_built, expected_round=expected_round,
    )


def merge_controller_projection(source_raw, target_raw):
    """Apply one controller projection when it owns every target task byte.

    Return None when the target owns task bytes that the source controller graph cannot
    represent exactly. The caller then selects the structural escalation route.
    """
    source = parse_artifact_bytes(source_raw)
    target = parse_artifact_bytes(target_raw)
    if source["built"] != target["built"] or source["round"] != target["round"]:
        return None

    source_tasks = {item["task"]: item for item in source["tasks"]}
    target_tasks = {item["task"]: item for item in target["tasks"]}

    def unwritten(task):
        return task["design_sha256"] in {
            sha256(b"### Design\n"),
            sha256(b"### Design\n[written at correction task Design - see below]\n"),
        } and task["disagreement_sha256"] is None

    for task, target_task in target_tasks.items():
        source_task = source_tasks.get(task)
        if source_task is None:
            if not unwritten(target_task):
                return None
            continue
        if source_task["task_contract_sha256"] != target_task["task_contract_sha256"]:
            if not unwritten(target_task):
                return None
    return source_raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser(
        "check", help="validate one canonical workspace Correction Round artifact",
    )
    check_parser.add_argument("built")
    check_parser.add_argument("round")
    args = parser.parse_args(argv)

    if not LOT_RE.fullmatch(args.built):
        parser.error("BUILT must be one canonical lot identity")
    if not re.fullmatch(r"[1-9][0-9]*", args.round):
        parser.error("ROUND must be one positive canonical integer")
    round_number = int(args.round)
    workspace = pathlib.Path(__file__).absolute().parents[2]
    common = workspace / "prompts" / "common"
    sys.path.insert(0, str(common))
    try:
        import progress

        refusal = io.StringIO()
        try:
            with contextlib.redirect_stdout(refusal):
                account = progress.correction_round_check_account(
                    progress.journal_entries(), args.built, round_number,
                    "the read-only Correction Round artifact check",
                )
        except SystemExit as exc:
            message = refusal.getvalue().rstrip()
            if message:
                print(message, file=sys.stderr)
            return exc.code if isinstance(exc.code, int) and exc.code else 1
    finally:
        sys.path.remove(str(common))
    print(json.dumps(account, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
