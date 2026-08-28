#!/usr/bin/env python3
"""Closed producer-specific Correction escalation artifacts."""

import hashlib
import pathlib
import re


PROOF_RE = re.compile(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}")
HASH_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
FINDING_RE = re.compile(r"F[1-9][0-9]*")
SOURCE_RE = re.compile(r"[a-z][a-z0-9-]*/F[1-9][0-9]*")
PRODUCT_REVIEW_MANDATES = ("unlooked", "user", "meaning", "quality", "coverage")


def fail(message):
    raise ValueError(message)


def one_field(line, name):
    prefix = f"{name}: "
    if not line.startswith(prefix) or not line[len(prefix):].strip() \
            or line[len(prefix):] != line[len(prefix):].strip():
        fail(f"the escalation artifact has no exact {name}")
    return line[len(prefix):]


def split_list(value, pattern, subject, *, canonical_key, empty=False):
    if value == "-" and empty:
        return []
    members = value.split(", ")
    if any(not re.fullmatch(pattern, member) for member in members) \
            or len(members) != len(set(members)) \
            or members != sorted(members, key=canonical_key):
        fail(f"{subject} is not one sorted exact set")
    return members


def finding_identity_key(identity):
    return int(identity[1:])


def correction_origin_key(identity):
    round_text, finding = identity.removeprefix("correction/c").split("/", 1)
    return int(round_text), finding_identity_key(finding)


def accepted_task_identity_key(identity):
    return int(identity.removeprefix("task "))


def source_identity_key(identity):
    mandate, ordinal = identity.split("/F", 1)
    return PRODUCT_REVIEW_MANDATES.index(mandate), int(ordinal)


def canonical_source_identities(members, subject):
    if not isinstance(members, list) or not members \
            or any(not isinstance(member, str) or not SOURCE_RE.fullmatch(member)
                   for member in members) \
            or any(member.split("/", 1)[0] not in PRODUCT_REVIEW_MANDATES
                   for member in members) \
            or len(members) != len(set(members)):
        fail(f"{subject} is not one exact product source set")
    return sorted(members, key=source_identity_key)


def split_source_list(value, subject):
    members = value.split(", ")
    if members != canonical_source_identities(members, subject):
        fail(f"{subject} is not in product mandate order")
    return members


def parse_schema_one(lines, cursor, *, subject, built, correction):
    fields = {"Schema": "1"}
    for name in (
        "Built unit", "Correction round", "Correction authority", "Current commit",
        "Structural blocker",
    ):
        if cursor >= len(lines):
            fail(f"the escalation artifact has no {name}")
        fields[name] = one_field(lines[cursor], name)
        cursor += 1
    if fields["Built unit"] != built or fields["Correction round"] != str(correction):
        fail("the escalation artifact changes its schema-1 identity")
    if not PROOF_RE.fullmatch(fields["Correction authority"]) \
            or not PROOF_RE.fullmatch(fields["Structural blocker"]):
        fail("the escalation artifact has a malformed schema-1 proof")
    if not COMMIT_RE.fullmatch(fields["Current commit"]):
        fail("the escalation artifact has a malformed Current commit")
    return fields, cursor


def parse_schema_two(lines, cursor, *, built, correction):
    fields = {"Schema": "2"}
    for name in (
        "Producer", "Built unit", "Correction round", "Correction opening",
        "Previous authority", "AMENDMENT opening", "AMENDMENT commit", "Return SHA-256",
        "Current commit", "Current tree", "Current gate", "Correction artifact SHA-256",
        "Structural blocker",
    ):
        if cursor >= len(lines):
            fail(f"the escalation artifact has no {name}")
        fields[name] = one_field(lines[cursor], name)
        cursor += 1
    if fields["Producer"] != "post-amendment-return" \
            or fields["Built unit"] != built \
            or fields["Correction round"] != str(correction):
        fail("the escalation artifact changes its schema-2 identity")
    for name in (
        "Correction opening", "Previous authority", "AMENDMENT opening",
        "AMENDMENT commit", "Structural blocker",
    ):
        if not PROOF_RE.fullmatch(fields[name]):
            fail(f"the escalation artifact has a malformed {name}")
    for name in ("Return SHA-256", "Current gate", "Correction artifact SHA-256"):
        if not HASH_RE.fullmatch(fields[name]):
            fail(f"the escalation artifact has a malformed {name}")
    for name in ("Current commit", "Current tree"):
        if not COMMIT_RE.fullmatch(fields[name]):
            fail(f"the escalation artifact has a malformed {name}")
    return fields, cursor


def parse_artifact_bytes(raw, *, expected_built=None, expected_round=None):
    if not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000:
        fail("the escalation artifact has invalid bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"the escalation artifact is not UTF-8: {exc}")
    if "\r" in text or not text.endswith("\n"):
        fail("the escalation artifact has non-canonical line endings")
    lines = text.splitlines()
    cursor = 0

    title = re.fullmatch(
        r"# (\S(?:.*\S)?) — (lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?) "
        r"correction round ([1-9][0-9]*) escalation",
        lines[cursor] if lines else "",
    )
    if title is None:
        fail("the escalation artifact has no exact title")
    subject, built, correction_text = title.groups()
    correction = int(correction_text)
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != "":
        fail("the escalation artifact title has no exact separator")
    cursor += 1
    if cursor >= len(lines):
        fail("the escalation artifact has no Schema")
    schema = one_field(lines[cursor], "Schema")
    cursor += 1
    if schema == "1":
        fields, cursor = parse_schema_one(
            lines, cursor, subject=subject, built=built, correction=correction,
        )
    elif schema == "2":
        fields, cursor = parse_schema_two(
            lines, cursor, built=built, correction=correction,
        )
    else:
        fail("the escalation artifact has an unsupported schema")
    if expected_built is not None and built != expected_built \
            or expected_round is not None and correction != expected_round:
        fail("the escalation artifact belongs to another Correction Round")
    if cursor >= len(lines) or lines[cursor] != "":
        fail("the escalation identity has no exact separator")
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != "## Accepted contributions":
        fail("the escalation artifact has no Accepted contributions section")
    cursor += 1
    contributions = []
    while cursor < len(lines) and lines[cursor] != "":
        if schema == "1":
            match = re.fullmatch(
                r"Task ([1-9][0-9]*): ([0-9a-f]{40,64}) · ([0-9a-f]{64})"
                r" · satisfies (F[1-9][0-9]*(?:, F[1-9][0-9]*)*)",
                lines[cursor],
            )
        else:
            match = re.fullmatch(
                r"Task ([1-9][0-9]*): ((?:0|[1-9][0-9]*):[0-9a-f]{64}) · "
                r"([0-9a-f]{40,64}) · ([0-9a-f]{64})",
                lines[cursor],
            )
        if match is None:
            fail("the escalation artifact has a malformed accepted contribution")
        if schema == "1":
            findings = split_list(
                match.group(4), r"F[1-9][0-9]*",
                "the escalation contribution finding account",
                canonical_key=finding_identity_key,
            )
            contributions.append({
                "task": int(match.group(1)), "commit": match.group(2),
                "gate": match.group(3), "satisfies": findings,
            })
        else:
            contributions.append({
                "task": int(match.group(1)), "success": match.group(2),
                "commit": match.group(3), "gate": match.group(4),
            })
        cursor += 1
    if [item["task"] for item in contributions] != list(range(1, len(contributions) + 1)):
        fail("the escalation accepted contributions are not one exact prefix")
    if cursor >= len(lines) or lines[cursor] != "":
        fail("the escalation contribution account has no exact separator")
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != "## Unresolved account":
        fail("the escalation artifact has no Unresolved account")
    cursor += 1
    items = []
    while cursor < len(lines) and lines[cursor] == "":
        cursor += 1
    while cursor < len(lines) and lines[cursor].startswith("### F"):
        match = re.fullmatch(r"### (F[1-9][0-9]*) - (\S(?:.*\S)?)", lines[cursor])
        if match is None or match.group(1) != f"F{len(items) + 1}":
            fail("the escalation unresolved items are not contiguous")
        item = {"id": match.group(1), "outcome": match.group(2)}
        cursor += 1
        values = {}
        for name in ("Origins", "Sources", "Accepted contributions", "Blocker", "Required outcome"):
            if cursor >= len(lines):
                fail(f"the escalation item has no {name}")
            values[name] = one_field(lines[cursor], name)
            cursor += 1
        item["origins"] = split_list(
            values["Origins"], r"correction/c[1-9][0-9]*/F[1-9][0-9]*",
            "the escalation item origins",
            canonical_key=correction_origin_key,
        )
        item["sources"] = split_source_list(
            values["Sources"], "the escalation item sources",
        )
        tasks = split_list(
            values["Accepted contributions"], r"task [1-9][0-9]*",
            "the escalation item accepted contributions",
            canonical_key=accepted_task_identity_key, empty=True,
        )
        item["accepted_contributions"] = [int(task.split()[1]) for task in tasks]
        if not PROOF_RE.fullmatch(values["Blocker"]):
            fail("the escalation item has no exact blocker")
        item["blocker"] = values["Blocker"]
        item["required_outcome"] = values["Required outcome"]
        items.append(item)
        if cursor < len(lines) and lines[cursor] == "":
            cursor += 1
    if not items or cursor >= len(lines) or lines[cursor] != "## Required sub-lot outcome":
        fail("the escalation artifact has no exact structural outcome")
    cursor += 1
    if cursor >= len(lines) or not lines[cursor].strip() or lines[cursor] != lines[cursor].strip():
        fail("the escalation artifact has no exact required sub-lot outcome")
    required_outcome = lines[cursor]
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != "":
        fail("the escalation structural outcome has no exact separator")
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != "## Final-checker consumer requirements":
        fail("the escalation artifact has no consumer requirement section")
    cursor += 1
    requirements = []
    while cursor < len(lines) and lines[cursor]:
        match = re.fullmatch(
            r"Obligation ([0-9a-f]{64}): (design|code) · "
            r"(first-(?:design|code)-manifest) · (\S(?:.*\S)?) · (F[1-9][0-9]*)",
            lines[cursor],
        )
        if match is None or match.group(3) != f"first-{match.group(2)}-manifest":
            fail("the escalation artifact has a malformed consumer requirement")
        requirements.append({
            "obligation_id": match.group(1), "checker": match.group(2),
            "manifest_phase": match.group(3), "remaining_outcome": match.group(4),
            "escalation_item": match.group(5),
        })
        cursor += 1
    if cursor != len(lines):
        fail("the escalation artifact has unowned trailing bytes")
    if [item["obligation_id"] for item in requirements] \
            != sorted({item["obligation_id"] for item in requirements}):
        fail("the escalation consumer requirements are not sorted and unique")
    item_ids = {item["id"] for item in items}
    if any(item["remaining_outcome"] != required_outcome
           or item["escalation_item"] not in item_ids for item in requirements):
        fail("the escalation consumer requirement changes its structural outcome")
    common = {
        "schema": int(schema),
        "producer": "ordinary" if schema == "1" else "post-amendment-return",
        "subject": subject,
        "built": built, "round": correction,
        "commit": fields["Current commit"],
        "blocker": fields["Structural blocker"],
        "accepted_contributions": contributions, "items": items,
        "required_outcome": required_outcome, "requirements": requirements,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if schema == "1":
        common["authority"] = fields["Correction authority"]
    else:
        common.update({
            "opening": fields["Correction opening"],
            "previous_authority": fields["Previous authority"],
            "amendment_opening": fields["AMENDMENT opening"],
            "amendment_commit": fields["AMENDMENT commit"],
            "return_sha256": fields["Return SHA-256"],
            "tree": fields["Current tree"], "gate": fields["Current gate"],
            "correction_artifact_sha256": fields["Correction artifact SHA-256"],
        })
    return common


def parse_artifact(path, **kwargs):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        fail("the escalation artifact is not one real regular file")
    return parse_artifact_bytes(path.read_bytes(), **kwargs)


def parse_rewind_blocker_bytes(raw, *, expected_built=None, expected_round=None):
    """Parse one closed retained-authority rewind preservation blocker."""
    if not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000:
        fail("the rewind preservation blocker has invalid bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"the rewind preservation blocker is not UTF-8: {exc}")
    if "\r" in text or not text.endswith("\n"):
        fail("the rewind preservation blocker has non-canonical line endings")
    lines = text.splitlines()
    title = re.fullmatch(
        r"# Retained authority preservation blocker — "
        r"(lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?) correction round ([1-9][0-9]*)",
        lines[0] if lines else "",
    )
    if title is None or len(lines) < 20 or lines[1] != "":
        fail("the rewind preservation blocker has no exact title")
    built, round_text = title.groups()
    correction = int(round_text)
    if expected_built is not None and built != expected_built \
            or expected_round is not None and correction != expected_round:
        fail("the rewind preservation blocker belongs to another Correction Round")
    cursor = 2
    names = (
        "Schema", "Producer", "Built unit", "Correction round", "Rewind owner SHA-256",
        "Correction opening", "Latest authority", "Previous rewind", "Cause",
        "Target commit", "Failed transition", "Failed transition SHA-256",
        "Failure reason", "Current commit", "Current tree", "Current gate",
    )
    fields = {}
    for name in names:
        if cursor >= len(lines):
            fail(f"the rewind preservation blocker has no {name}")
        fields[name] = one_field(lines[cursor], name)
        cursor += 1
    if fields["Schema"] != "1" or fields["Producer"] != "retained-authority-rewind" \
            or fields["Built unit"] != built or fields["Correction round"] != round_text:
        fail("the rewind preservation blocker changes its producer identity")
    if not HASH_RE.fullmatch(fields["Rewind owner SHA-256"]) \
            or not HASH_RE.fullmatch(fields["Failed transition SHA-256"]) \
            or not HASH_RE.fullmatch(fields["Current gate"]):
        fail("the rewind preservation blocker has a malformed SHA-256")
    for name in ("Correction opening", "Latest authority", "Cause", "Failed transition"):
        if not PROOF_RE.fullmatch(fields[name]):
            fail(f"the rewind preservation blocker has a malformed {name}")
    if fields["Previous rewind"] != "-" \
            and not PROOF_RE.fullmatch(fields["Previous rewind"]):
        fail("the rewind preservation blocker has a malformed Previous rewind")
    for name in ("Target commit", "Current commit", "Current tree"):
        if not COMMIT_RE.fullmatch(fields[name]):
            fail(f"the rewind preservation blocker has a malformed {name}")
    if fields["Failure reason"] \
            != "the retained transition has no exact conflict-free Git projection":
        fail("the rewind preservation blocker changes its mechanical failure reason")
    if cursor >= len(lines) or lines[cursor] != "" \
            or cursor + 1 >= len(lines) or lines[cursor + 1] != "## Unresolved account":
        fail("the rewind preservation blocker has no exact unresolved boundary")
    cursor += 2
    items = []
    while cursor < len(lines) and lines[cursor]:
        match = re.fullmatch(
            r"(F[1-9][0-9]*): (correction/c[1-9][0-9]*/F[1-9][0-9]*)"
            r" · accepted (task [1-9][0-9]*(?:, task [1-9][0-9]*)*|-)",
            lines[cursor],
        )
        if match is None or match.group(1) != f"F{len(items) + 1}":
            fail("the rewind preservation blocker has a malformed unresolved item")
        tasks = split_list(
            match.group(3), r"task [1-9][0-9]*",
            "the rewind blocker accepted contribution account",
            canonical_key=accepted_task_identity_key, empty=True,
        )
        items.append({
            "id": match.group(1), "origin": match.group(2),
            "accepted_contributions": [int(task.split()[1]) for task in tasks],
        })
        cursor += 1
    if not items or cursor >= len(lines) or lines[cursor] != "" \
            or cursor + 2 >= len(lines) \
            or lines[cursor + 1] != "## Required sub-lot outcome" \
            or not lines[cursor + 2].strip() \
            or lines[cursor + 2] != lines[cursor + 2].strip() \
            or cursor + 3 != len(lines):
        fail("the rewind preservation blocker has no exact structural outcome")
    return {
        "schema": 1, "producer": "retained-authority-rewind",
        "built": built, "round": correction,
        "owner_sha256": fields["Rewind owner SHA-256"],
        "opening": fields["Correction opening"],
        "latest_authority": fields["Latest authority"],
        "previous_rewind": None if fields["Previous rewind"] == "-"
        else fields["Previous rewind"],
        "cause": fields["Cause"], "target_commit": fields["Target commit"],
        "failed_transition": fields["Failed transition"],
        "failed_transition_sha256": fields["Failed transition SHA-256"],
        "failure_reason": fields["Failure reason"],
        "current_commit": fields["Current commit"],
        "current_tree": fields["Current tree"], "current_gate": fields["Current gate"],
        "items": items, "required_outcome": lines[cursor + 2],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def parse_rewind_blocker(path, **kwargs):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        fail("the rewind preservation blocker is not one real regular file")
    return parse_rewind_blocker_bytes(path.read_bytes(), **kwargs)
