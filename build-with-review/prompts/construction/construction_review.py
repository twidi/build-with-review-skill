#!/usr/bin/env python3
"""Freeze and audit one exact construction checker generation."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
TASK_RE = re.compile(r"[1-9][0-9]*")
TASK_HEADING_RE = re.compile(r"^## Task ([1-9][0-9]*) - .+$")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
MAX_READ_BYTES = 65_536
IMPACTS = ("CRITICAL", "IMPORTANT", "MINOR")
IMPACT_RANK = {impact: rank for rank, impact in enumerate(reversed(IMPACTS), 1)}


def refuse(message):
    print(f"**construction review ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def git_bytes(*args, check=True):
    result = subprocess.run(
        ["git", "-C", str(REPO), *map(str, args)], capture_output=True,
    )
    if check and result.returncode:
        refuse(result.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} failed")
    return result


def validate_identity(lot, task):
    if not LOT_RE.fullmatch(lot) or not TASK_RE.fullmatch(str(task)):
        refuse("the lot or task identity is malformed")
    return int(task)


def real_workspace_file(relative, subject):
    try:
        pure = pathlib.PurePosixPath(relative)
    except TypeError:
        refuse(f"{subject} has an invalid path")
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        refuse(f"{subject} is not one workspace-relative path")
    current = WORKSPACE
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            refuse(f"{subject} traverses a symlink: {current}")
    if not current.is_file():
        refuse(f"{subject} is not one real regular file: {current}")
    return current


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


def task_slice(lines, task):
    structural = structural_markdown_lines(lines)
    starts = []
    for index, line in enumerate(lines):
        if index not in structural:
            continue
        match = TASK_HEADING_RE.fullmatch(line.rstrip("\r\n"))
        if match:
            starts.append((index, int(match.group(1))))
        elif line.startswith("## Task "):
            refuse(f"the plan has a malformed Task heading: {line.rstrip()}")
    matches = [position for position, (_, number) in enumerate(starts) if number == task]
    if len(matches) != 1:
        refuse(f"the plan does not contain exactly one Task {task}")
    position = matches[0]
    start = starts[position][0]
    end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
    return start, end


def named_section(lines, start, end, heading):
    structural = structural_markdown_lines(lines)
    positions = [
        index for index in range(start + 1, end)
        if index in structural and lines[index].rstrip("\r\n") == heading
    ]
    if len(positions) > 1:
        refuse(f"Task has more than one {heading} section")
    if not positions:
        return None, b""
    section_start = positions[0]
    section_end = next(
        (
            index for index in range(section_start + 1, end)
            if index in structural and lines[index].startswith("### ")
        ),
        end,
    )
    content_end = section_end
    while content_end > section_start + 1 and not lines[content_end - 1].strip():
        content_end -= 1
    content = "".join(lines[section_start:content_end]).rstrip("\r\n") + "\n"
    return (section_start, section_end), content.encode("utf-8")


def plan_state_bytes(raw, lot, task, relative):
    task = validate_identity(lot, task)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        refuse(f"the construction plan is not UTF-8: {exc}")
    lines = text.splitlines(keepends=True)
    start, end = task_slice(lines, task)
    design_range, design = named_section(lines, start, end, "### Design")
    if design_range is None:
        refuse(f"Task {task} must contain exactly one ### Design section")
    disagreement_range, disagreement = named_section(lines, start, end, "### Disagreement")
    mutable_starts = [item[0] for item in (design_range, disagreement_range) if item]
    contract_end = min(mutable_starts, default=end)
    while contract_end > start and not lines[contract_end - 1].strip():
        contract_end -= 1
    contract = ("".join(lines[start:contract_end]).rstrip("\r\n") + "\n").encode("utf-8")
    if not contract.strip():
        refuse("the task has no controller-owned contract")

    projected = list(lines)
    if disagreement_range:
        first, last = disagreement_range
        while first > start and not projected[first - 1].strip():
            first -= 1
        projected[first:last] = []
    projection = "".join(projected).encode("utf-8")

    owned = list(lines)
    for section_range in sorted(
        (item for item in (design_range, disagreement_range) if item), reverse=True,
    ):
        first, last = section_range
        while first > start and not owned[first - 1].strip():
            first -= 1
        owned[first:last] = []
    ownership = "".join(owned).encode("utf-8")
    return {
        "plan": str(relative),
        "plan_sha256": sha256(raw),
        "plan_projection_sha256": sha256(projection),
        "plan_ownership_sha256": sha256(ownership),
        "contract_sha256": sha256(contract),
        "design_sha256": sha256(design) if design else None,
        "disagreement_sha256": sha256(disagreement) if disagreement else None,
    }


def plan_state(lot, task):
    relative = pathlib.PurePosixPath("plans", f"{lot}-plan.md")
    path = real_workspace_file(str(relative), "the construction plan")
    return plan_state_bytes(path.read_bytes(), lot, task, relative)


def committed_plan_state(lot, task, revision):
    validate_identity(lot, task)
    if not re.fullmatch(r"[0-9a-f]{40,64}|HEAD", revision):
        refuse("the committed plan revision is malformed")
    relative = pathlib.PurePosixPath(
        "docs", "plans", f"{WORKSPACE.name}-{lot}-plan.md",
    )
    result = git_bytes("show", f"{revision}:{relative}")
    return plan_state_bytes(result.stdout, lot, task, relative)


def appended_disagreement_headings(content, base_sha256, heading, subject):
    section_lines = content.decode("utf-8").splitlines(keepends=True)
    all_headings = [(index, int(match.group(1))) for index, line in enumerate(section_lines)
                    if (match := heading.fullmatch(line.rstrip("\r\n")))]
    boundaries = [index for index, _ in all_headings] + [len(section_lines)]
    matching_boundaries = []
    for boundary in boundaries:
        prefix_lines = list(section_lines[:boundary])
        while prefix_lines and not prefix_lines[-1].strip():
            prefix_lines.pop()
        prefix = ("".join(prefix_lines).rstrip("\r\n") + "\n").encode("utf-8") \
            if prefix_lines else b""
        identity = None if prefix in {b"", b"### Disagreement\n"} else sha256(prefix)
        if identity == base_sha256:
            matching_boundaries.append(boundary)
    if len(matching_boundaries) != 1:
        refuse(f"{subject} changed the prior Disagreement bytes")
    boundary = matching_boundaries[0]
    current = [(index, finding) for index, finding in all_headings if index >= boundary]
    current_indexes = {index for index, _ in current}
    if any(
        line.startswith("#### Finding ") and index not in current_indexes
        for index, line in enumerate(section_lines[boundary:], boundary)
    ):
        refuse(f"{subject} has a malformed appended finding heading")
    return section_lines, current


def disagreement_state(lot, task, base_sha256, expected):
    task = validate_identity(lot, task)
    if base_sha256 != "-" and not re.fullmatch(r"[0-9a-f]{64}", base_sha256):
        refuse("the accepted Design Disagreement identity is malformed")
    base_sha256 = None if base_sha256 == "-" else base_sha256
    expected_ids = [] if expected == "-" else [int(value) for value in expected.split(",")]
    if expected_ids != sorted(set(expected_ids)) or any(value < 1 for value in expected_ids):
        refuse("the expected Disagreement finding identities are malformed")
    path = real_workspace_file(f"plans/{lot}-plan.md", "the construction plan")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = task_slice(lines, task)
    section_range, content = named_section(lines, start, end, "### Disagreement")
    if section_range is None:
        if base_sha256 or expected_ids:
            refuse("the final plan lost its accepted Disagreement section")
        return {"disagreement_sha256": None, "findings": []}
    section_lines, headings = appended_disagreement_headings(
        content, base_sha256,
        re.compile(r"^#### Finding ([1-9][0-9]*) — code alternative$"),
        "the code-review resolution",
    )
    found = [finding for _, finding in headings]
    if found != expected_ids:
        refuse("the Disagreement section does not name every alternative exactly once and in order")
    for position, (start_index, finding) in enumerate(headings):
        end_index = headings[position + 1][0] if position + 1 < len(headings) else len(section_lines)
        if not any(line.strip() for line in section_lines[start_index + 1:end_index]):
            refuse(f"the Disagreement code alternative for finding {finding} has no explanation")
    return {"disagreement_sha256": sha256(content), "findings": found}


def design_disagreement_state(lot, task, base_sha256, expected):
    task = validate_identity(lot, task)
    if base_sha256 != "-" and not re.fullmatch(r"[0-9a-f]{64}", base_sha256):
        refuse("the prior Design Disagreement identity is malformed")
    base_sha256 = None if base_sha256 == "-" else base_sha256
    expected_ids = [] if expected == "-" else [int(value) for value in expected.split(",")]
    if expected_ids != sorted(set(expected_ids)) or any(value < 1 for value in expected_ids):
        refuse("the expected design-alternative identities are malformed")
    path = real_workspace_file(f"plans/{lot}-plan.md", "the construction plan")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = task_slice(lines, task)
    section_range, content = named_section(lines, start, end, "### Disagreement")
    if section_range is None:
        if base_sha256 or expected_ids:
            refuse("the final Design has no required Disagreement section")
        return {"disagreement_sha256": None, "findings": []}
    section_lines, headings = appended_disagreement_headings(
        content, base_sha256,
        re.compile(r"^#### Finding ([1-9][0-9]*) — design alternative$"),
        "the design-review settlement",
    )
    found = [finding for _, finding in headings]
    if found != expected_ids:
        refuse("the Disagreement section does not name every design alternative exactly once")
    for position, (start_index, finding) in enumerate(headings):
        end_index = headings[position + 1][0] if position + 1 < len(headings) else len(section_lines)
        if not any(line.strip() for line in section_lines[start_index + 1:end_index]):
            refuse(f"the Design alternative for finding {finding} has no explanation")
    return {"disagreement_sha256": sha256(content), "findings": found}


def parse_name_status(base, tree):
    result = git_bytes("diff", "--name-status", "--find-renames", "-z", base, tree)
    tokens = result.stdout.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    parsed = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii", "strict")
        index += 1
        if not re.fullmatch(r"[AMD]|[RC][0-9]+", status):
            refuse(f"the candidate has an unsupported Git status: {status}")
        if index >= len(tokens):
            refuse("the candidate name-status output is truncated")
        old_path = None
        if status.startswith(("R", "C")):
            old_path = tokens[index].decode("utf-8", "surrogateescape")
            index += 1
            if index >= len(tokens):
                refuse("the candidate rename output is truncated")
        path = tokens[index].decode("utf-8", "surrogateescape")
        index += 1
        parsed.append((status, old_path, path))
    return parsed


def tree_file(tree, path):
    result = git_bytes("show", f"{tree}:{path}", check=False)
    return None if result.returncode else result.stdout


def path_diff(base, tree, old_path, path):
    paths = [candidate for candidate in (old_path, path) if candidate]
    return git_bytes("diff", "--no-ext-diff", "--no-color", "--binary", base, tree, "--", *paths).stdout


def atomic_publish(relative, payload, subject):
    target = WORKSPACE / pathlib.PurePosixPath(relative)
    current = WORKSPACE
    for part in target.relative_to(WORKSPACE).parts[:-1]:
        current = current / part
        if current.exists() or current.is_symlink():
            if not current.is_dir() or current.is_symlink():
                refuse(f"{subject} ground is not one real directory: {current}")
        else:
            current.mkdir()
    if target.exists() or target.is_symlink():
        existing = real_workspace_file(relative, subject).read_bytes()
        if existing != payload:
            refuse(f"{subject} already exists with different bytes")
        return target
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = real_workspace_file(relative, subject).read_bytes()
            if existing != payload:
                refuse(f"{subject} raced with different bytes")
    finally:
        temporary.unlink(missing_ok=True)
    return target


def manifest(lot, task, attempt, round_number, gate, base, tree):
    task = validate_identity(lot, task)
    if not TASK_RE.fullmatch(str(attempt)) or not TASK_RE.fullmatch(str(round_number)):
        refuse("the attempt or round identity is malformed")
    for value, subject in ((base, "base"), (tree, "tree")):
        if not re.fullmatch(r"[0-9a-f]{40,64}", value):
            refuse(f"the candidate {subject} identity is malformed")
    if not re.fullmatch(r"[0-9a-f]{64}", gate):
        refuse("the gate operation identity is malformed")
    git_bytes("rev-parse", "--verify", f"{base}^{{commit}}")
    git_bytes("cat-file", "-e", f"{tree}^{{tree}}")
    state = plan_state(lot, task)
    files = []
    for number, (status, old_path, path) in enumerate(parse_name_status(base, tree), 1):
        diff = path_diff(base, tree, old_path, path)
        after = None if status == "D" else tree_file(tree, path)
        if status != "D" and after is None:
            refuse(f"the candidate tree has no after image for {path}")
        files.append({
            "id": number,
            "status": status,
            "old_path": old_path,
            "path": path,
            "diff_lines": len(diff.splitlines()),
            "diff_bytes": len(diff),
            "diff_sha256": sha256(diff),
            "file_lines": len(after.splitlines()) if after is not None else 0,
            "file_bytes": len(after) if after is not None else 0,
            "after_sha256": sha256(after) if after is not None else None,
        })
    if not files:
        refuse("the code-review candidate changes no path")
    document = {
        "schema": 4,
        "lot": lot,
        "task": task,
        "attempt": int(attempt),
        "round": int(round_number),
        "gate": gate,
        "base": base,
        "tree": tree,
        **state,
        "previous": read_previous_account(int(round_number)),
        "files": files,
    }
    payload = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    relative = pathlib.PurePosixPath(
        "reports", "construction", lot,
        f"task-{task}-attempt-{attempt}-code-round-{round_number}-{gate}-manifest.json",
    )
    atomic_publish(str(relative), payload, "the code-review manifest")
    return {"path": str(relative), "sha256": sha256(payload), "tree": tree, "files": len(files)}


def design_manifest(lot, task, attempt, round_number):
    task = validate_identity(lot, task)
    if not TASK_RE.fullmatch(str(attempt)) or not TASK_RE.fullmatch(str(round_number)) \
            or int(round_number) > 10:
        refuse("the design-review attempt or round identity is malformed")
    state = plan_state(lot, task)
    document = {
        "schema": 1,
        "lot": lot,
        "task": task,
        "attempt": int(attempt),
        "round": int(round_number),
        **state,
        "previous": read_design_previous_account(int(round_number)),
    }
    payload = (json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode()
    relative = pathlib.PurePosixPath(
        "reports", "construction", lot,
        f"task-{task}-attempt-{attempt}-design-round-{round_number}-manifest.json",
    )
    atomic_publish(str(relative), payload, "the design-review manifest")
    return {"path": str(relative), "sha256": sha256(payload)}


def load_design_manifest(relative):
    path = real_workspace_file(relative, "the design-review manifest")
    payload = path.read_bytes()
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the design-review manifest is invalid JSON: {exc}")
    required = {
        "schema", "lot", "task", "attempt", "round", "plan", "plan_sha256",
        "plan_projection_sha256", "plan_ownership_sha256", "contract_sha256",
        "design_sha256", "disagreement_sha256", "previous",
    }
    if not isinstance(document, dict) or set(document) != required \
            or document.get("schema") != 1:
        refuse("the design-review manifest has an invalid shape")
    task = validate_identity(document.get("lot"), document.get("task"))
    if not TASK_RE.fullmatch(str(document.get("attempt"))) \
            or not TASK_RE.fullmatch(str(document.get("round"))) \
            or document["round"] > 10:
        refuse("the design-review manifest has a malformed generation identity")
    validate_design_previous_account(document["previous"], document["round"])
    expected_relative = str(pathlib.PurePosixPath(
        "reports", "construction", document["lot"],
        f"task-{task}-attempt-{document['attempt']}-design-round-{document['round']}-manifest.json",
    ))
    if relative != expected_relative:
        refuse("the design-review manifest path contradicts its generation identity")
    return path, payload, document


def load_manifest(relative):
    path = real_workspace_file(relative, "the code-review manifest")
    payload = path.read_bytes()
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the code-review manifest is invalid JSON: {exc}")
    required = {
        "schema", "lot", "task", "attempt", "round", "gate", "base", "tree",
        "plan", "plan_sha256", "plan_projection_sha256", "plan_ownership_sha256",
        "contract_sha256", "design_sha256", "disagreement_sha256", "previous", "files",
    }
    if not isinstance(document, dict) or set(document) != required \
            or document.get("schema") != 4 or not isinstance(document.get("files"), list):
        refuse("the code-review manifest has an invalid shape")
    task = validate_identity(document.get("lot"), document.get("task"))
    if not TASK_RE.fullmatch(str(document.get("attempt"))) \
            or not TASK_RE.fullmatch(str(document.get("round"))):
        refuse("the code-review manifest has a malformed generation identity")
    validate_previous_account(document["previous"], int(document["round"]))
    expected_relative = str(pathlib.PurePosixPath(
        "reports", "construction", document["lot"],
        f"task-{task}-attempt-{document['attempt']}-code-round-{document['round']}-{document['gate']}-manifest.json",
    ))
    if relative != expected_relative:
        refuse("the code-review manifest path contradicts its generation identity")
    expected_files = []
    for number, (status, old_path, item_path) in enumerate(
        parse_name_status(document["base"], document["tree"]), 1,
    ):
        diff = path_diff(document["base"], document["tree"], old_path, item_path)
        after = None if status == "D" else tree_file(document["tree"], item_path)
        expected_files.append({
            "id": number, "status": status, "old_path": old_path, "path": item_path,
            "diff_lines": len(diff.splitlines()), "diff_bytes": len(diff),
            "diff_sha256": sha256(diff),
            "file_lines": len(after.splitlines()) if after is not None else 0,
            "file_bytes": len(after) if after is not None else 0,
            "after_sha256": sha256(after) if after is not None else None,
        })
    if document["files"] != expected_files:
        refuse("the code-review manifest does not match its exact candidate files")
    return path, payload, document


def validate_previous_account(account, round_number):
    if round_number == 1:
        if account is None:
            return None
        required = {
            "source", "failure", "result", "result_sha256", "findings",
            "resolution", "resolution_proof",
        }
        if not isinstance(account, dict) or set(account) != required \
                or account.get("source") != "retry" \
                or not re.fullmatch(r"[0-9]+:[0-9a-f]{64}", account.get("failure", "")):
            refuse("the first code-review round has a malformed retry obligation")
    else:
        required = {
            "source", "round", "result", "result_sha256", "findings",
            "resolution", "resolution_proof",
        }
        if not isinstance(account, dict) or set(account) != required \
                or account.get("source") != "round" or account.get("round") != round_number - 1:
            refuse("the prior code-review batch account has an invalid generation")
    if not isinstance(account.get("result"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", account.get("result_sha256", "")) \
            or not re.fullmatch(r"[0-9]+:[0-9a-f]{64}", account.get("resolution_proof", "")):
        refuse("the prior code-review batch account has an invalid shape")
    result_path = real_workspace_file(account["result"], "the prior physical checker result")
    if sha256(result_path.read_bytes()) != account["result_sha256"]:
        refuse("the prior physical checker result changed")
    findings = account.get("findings")
    resolution = account.get("resolution")
    expected_ids = [item.get("id") for item in findings] if isinstance(findings, list) else []
    if not findings or any(
        not isinstance(item, dict) or set(item) != {"id", "where", "what", "why", "impact"}
        or item.get("impact") not in IMPACTS
        for item in findings
    ) or any(not TASK_RE.fullmatch(str(value)) for value in expected_ids) \
            or expected_ids != sorted(set(expected_ids)):
        refuse("the prior batch has no exact contiguous findings")
    if not isinstance(resolution, list) or len(resolution) != len(findings) or any(
        not isinstance(item, dict) or set(item) != {"id", "status", "evidence"}
        or item.get("status") not in (
            {"accepted"} if account.get("source") == "retry" else {"corrected", "unchanged"}
        )
        or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
        for item in resolution
    ) or [item.get("id") for item in resolution] != expected_ids:
        refuse("the prior batch has no complete correction account")
    return account


def validate_design_previous_account(account, round_number):
    if round_number == 1 and account is None:
        return None
    required = {
        "source", "result", "result_sha256", "findings", "resolution",
        "resolution_proof",
    }
    if not isinstance(account, dict):
        refuse("the prior design-review account is malformed")
    if account.get("source") == "round":
        required.add("round")
        if round_number == 1 or account.get("round") != round_number - 1:
            refuse("the prior design-review account has the wrong logical round")
        statuses = {"corrected", "unchanged"}
        contiguous_identities = True
    elif account.get("source") == "retry":
        required.add("failure")
        if round_number != 1 or not re.fullmatch(
            r"[0-9]+:[0-9a-f]{64}", account.get("failure", ""),
        ):
            refuse("the design retry account has a malformed failure proof")
        statuses = {"accepted", "contract-blocked", "carried"}
        contiguous_identities = False
    else:
        refuse("the prior design-review account has an unknown source")
    if set(account) != required \
            or not isinstance(account.get("result"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", account.get("result_sha256", "")) \
            or not re.fullmatch(r"[0-9]+:[0-9a-f]{64}", account.get("resolution_proof", "")):
        refuse("the prior design-review account has an invalid shape")
    result_path = real_workspace_file(account["result"], "the prior design-checker result")
    if sha256(result_path.read_bytes()) != account["result_sha256"]:
        refuse("the prior design-checker result changed")
    findings = account.get("findings")
    identities = [item.get("id") for item in findings] if isinstance(findings, list) else []
    if contiguous_identities:
        identities_invalid = identities != list(range(1, len(findings) + 1))
    else:
        identities_invalid = identities != sorted(set(identities)) or any(
            not TASK_RE.fullmatch(str(identity)) for identity in identities
        )
    if not findings or identities_invalid or any(
        not isinstance(item, dict) or set(item) != {"id", "where", "what", "why", "impact"}
        or item.get("impact") not in IMPACTS
        or any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in ("where", "what", "why"))
        for item in findings
    ):
        refuse("the prior design-review batch has malformed findings")
    resolution = account.get("resolution")
    if not isinstance(resolution, list) or len(resolution) != len(findings) \
            or [item.get("id") for item in resolution] != identities or any(
                not isinstance(item, dict) or set(item) != {"id", "status", "evidence"}
                or item.get("status") not in statuses
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
                for item in resolution
            ):
        refuse("the prior design-review batch has no complete resolution account")
    return account


def read_design_previous_account(round_number):
    payload = sys.stdin.buffer.read()
    if not payload.strip():
        if round_number == 1:
            return None
        refuse("a later design-review round has no prior resolution account")
    try:
        account = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the prior design-review account is invalid JSON: {exc}")
    return validate_design_previous_account(account, round_number)


def read_previous_account(round_number):
    payload = sys.stdin.buffer.read()
    if round_number == 1:
        if not payload.strip():
            return None
    if not payload.strip():
        refuse("a later code-review round has no exact prior batch account")
    try:
        account = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the prior code-review batch account is invalid JSON: {exc}")
    return validate_previous_account(account, round_number)


def read_candidate(relative, item_number, kind, start, count):
    _, _, document = load_manifest(relative)
    if not TASK_RE.fullmatch(str(item_number)) or not re.fullmatch(r"0|[1-9][0-9]*", str(start)) \
            or not TASK_RE.fullmatch(str(count)) or int(count) > MAX_READ_BYTES \
            or kind not in {"diff", "file"}:
        refuse("the manifest read request is malformed")
    matches = [item for item in document["files"] if item.get("id") == int(item_number)]
    if len(matches) != 1:
        refuse("the manifest has no unique requested item")
    item = matches[0]
    if kind == "diff":
        payload = path_diff(document["base"], document["tree"], item.get("old_path"), item["path"])
        expected = item["diff_sha256"]
    else:
        payload = tree_file(document["tree"], item["path"])
        if payload is None or item.get("after_sha256") is None:
            refuse("the requested item has no after image")
        expected = item["after_sha256"]
    if sha256(payload) != expected:
        refuse("the requested candidate bytes changed")
    first = int(start)
    last = first + int(count)
    if first >= len(payload) or last > len(payload):
        refuse("the byte-bounded read exceeds the declared member size")
    selected = payload[first:last]
    sys.stdout.buffer.write(selected)


def manifest_count(relative):
    _, _, document = load_manifest(relative)
    print(len(document["files"]))


def manifest_item(relative, item_number):
    _, _, document = load_manifest(relative)
    if not TASK_RE.fullmatch(str(item_number)):
        refuse("the manifest item identity is malformed")
    matches = [item for item in document["files"] if item["id"] == int(item_number)]
    if len(matches) != 1:
        refuse("the manifest has no unique requested item")
    print(json.dumps(matches[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def manifest_previous(relative):
    _, _, document = load_manifest(relative)
    print(json.dumps(document["previous"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def previous_count(relative):
    _, _, document = load_manifest(relative)
    previous = document["previous"]
    print(len(previous["findings"]) if previous else 0)


def previous_item(relative, item_number):
    _, _, document = load_manifest(relative)
    if not TASK_RE.fullmatch(str(item_number)):
        refuse("the prior finding identity is malformed")
    previous = document["previous"]
    if previous is None or int(item_number) > len(previous["findings"]):
        refuse("the manifest has no requested prior finding")
    index = int(item_number) - 1
    print(json.dumps({
        "finding": previous["findings"][index],
        "resolution": previous["resolution"][index],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def read_plan_generation(relative, kind):
    _, _, document = load_manifest(relative)
    if kind not in {"contract", "design"}:
        refuse("the plan-generation read kind must be contract or design")
    state = plan_state(document["lot"], document["task"])
    for key in ("contract_sha256", "design_sha256", "plan_projection_sha256",
                "plan_ownership_sha256", "disagreement_sha256"):
        if state[key] != document[key]:
            refuse("the living plan no longer matches the frozen checker generation")
    path = real_workspace_file(state["plan"], "the construction plan")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = task_slice(lines, document["task"])
    if kind == "contract":
        ranges = [named_section(lines, start, end, heading)[0]
                  for heading in ("### Design", "### Disagreement")]
        stop = min((item[0] for item in ranges if item), default=end)
        while stop > start and not lines[stop - 1].strip():
            stop -= 1
        payload = ("".join(lines[start:stop]).rstrip("\r\n") + "\n").encode("utf-8")
        expected = document["contract_sha256"]
    else:
        _, payload = named_section(lines, start, end, "### Design")
        expected = document["design_sha256"]
    if sha256(payload) != expected:
        refuse(f"the exact {kind} bytes contradict the frozen identity")
    sys.stdout.buffer.write(payload)


def read_design_generation(relative, kind):
    _, _, document = load_design_manifest(relative)
    if kind not in {"contract", "design"}:
        refuse("the design-generation read kind must be contract or design")
    state = plan_state(document["lot"], document["task"])
    for key in (
        "contract_sha256", "design_sha256", "plan_projection_sha256",
        "plan_ownership_sha256", "disagreement_sha256",
    ):
        if state[key] != document[key]:
            refuse("the living plan no longer matches the frozen design-review generation")
    path = real_workspace_file(state["plan"], "the construction plan")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = task_slice(lines, document["task"])
    if kind == "contract":
        ranges = [named_section(lines, start, end, heading)[0]
                  for heading in ("### Design", "### Disagreement")]
        stop = min((item[0] for item in ranges if item), default=end)
        while stop > start and not lines[stop - 1].strip():
            stop -= 1
        payload = ("".join(lines[start:stop]).rstrip("\r\n") + "\n").encode("utf-8")
        expected = document["contract_sha256"]
    else:
        _, payload = named_section(lines, start, end, "### Design")
        expected = document["design_sha256"]
    if sha256(payload) != expected:
        refuse(f"the exact {kind} bytes contradict the design-review manifest")
    sys.stdout.buffer.write(payload)


def design_previous_count(relative):
    _, _, document = load_design_manifest(relative)
    previous = document["previous"]
    print(len(previous["findings"]) if previous else 0)


def design_previous_item(relative, item_number):
    _, _, document = load_design_manifest(relative)
    if not TASK_RE.fullmatch(str(item_number)):
        refuse("the prior design finding identity is malformed")
    previous = document["previous"]
    if previous is None or int(item_number) > len(previous["findings"]):
        refuse("the design-review manifest has no requested prior finding")
    index = int(item_number) - 1
    print(json.dumps({
        "finding": previous["findings"][index],
        "resolution": previous["resolution"][index],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def strict_result(manifest_relative, source):
    _, _, frozen = load_manifest(manifest_relative)
    source = pathlib.Path(source)
    if not source.is_file() or source.is_symlink():
        refuse("the physical checker result source is not one real regular file")
    raw = source.read_bytes()
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the physical checker result is not complete JSON: {exc}")
    if not isinstance(report, dict) or set(report) != {
        "verdict", "manifest", "inspected", "checks", "previous", "findings",
    } or report.get("verdict") not in {"clean", "findings"} \
            or report.get("manifest") != manifest_relative:
        refuse("the physical checker result has an invalid top-level shape")
    expected_inspected = [
        {
            "id": item["id"], "path": item["path"],
            "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"],
        }
        for item in frozen["files"]
    ]
    if report["inspected"] != expected_inspected:
        refuse("the physical checker result does not account for every manifest member exactly once")
    checks = report["checks"]
    if not isinstance(checks, list) or len(checks) not in {2, 3} or any(
        not isinstance(item, dict) or set(item) != {"subject", "evidence"}
        or not isinstance(item["subject"], str) or not item["subject"].strip()
        or not isinstance(item["evidence"], str) or not item["evidence"].strip()
        for item in checks
    ):
        refuse("the physical checker result has no exact two-or-three-item checked evidence account")
    if not any(item["subject"].strip().lower() == "assertion" for item in checks):
        refuse("the physical checker result does not identify the assertion that the checker tried to break")
    previous = report["previous"]
    prior = frozen["previous"]
    prior_ids = [item["id"] for item in prior["findings"]] if prior else []
    if not isinstance(previous, list) or len(previous) != len(prior_ids) or any(
        not isinstance(item, dict) or set(item) != {"id", "status", "evidence"}
        or item.get("status") not in {"addressed", "still-open"}
        or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
        for item in previous
    ) or [item.get("id") for item in previous] != prior_ids:
        refuse("the physical checker result does not verify every prior finding exactly once")
    findings = report["findings"]
    if not isinstance(findings, list) or any(
        not isinstance(item, dict) or set(item) != {
            "id", "where", "what", "why", "impact", "previous",
        }
        or not TASK_RE.fullmatch(str(item.get("id")))
        or item.get("impact") not in IMPACTS
        or any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in ("where", "what", "why"))
        or not isinstance(item.get("previous"), list)
        or item["previous"] != sorted(set(item["previous"]))
        or any(value not in prior_ids for value in item["previous"])
        for item in findings
    ) or [item["id"] for item in findings] != list(range(1, len(findings) + 1)):
        refuse("the physical checker result has malformed or non-contiguous findings")
    still_open = [item["id"] for item in previous if item["status"] == "still-open"]
    carried = [value for finding in findings for value in finding["previous"]]
    if carried != still_open:
        refuse("the physical checker result drops, duplicates or invents a still-open prior finding")
    prior_impacts = {item["id"]: item["impact"] for item in prior["findings"]} if prior else {}
    for finding in findings:
        if finding["previous"]:
            expected_impact = max(
                (prior_impacts[identity] for identity in finding["previous"]),
                key=IMPACT_RANK.__getitem__,
            )
            if finding["impact"] != expected_impact:
                refuse("a carried code finding changes its previously admitted impact")
    outcome = "clean" if not findings else "findings"
    if report["verdict"] != outcome:
        refuse("the physical checker verdict contradicts its exact findings")
    canonical = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    result_relative = manifest_relative.removesuffix("-manifest.json") + "-result.json"
    atomic_publish(result_relative, canonical, "the physical code-checker result")
    return {
        "outcome": outcome,
        "findings": len(findings),
        "critical": sum(item["impact"] == "CRITICAL" for item in findings),
        "important": sum(item["impact"] == "IMPORTANT" for item in findings),
        "minor": sum(item["impact"] == "MINOR" for item in findings),
        "report": result_relative,
        "report_sha256": sha256(canonical),
        "manifest": manifest_relative,
        "manifest_sha256": sha256((WORKSPACE / manifest_relative).read_bytes()),
    }


def strict_design_result(manifest_relative, source):
    _, manifest_payload, frozen = load_design_manifest(manifest_relative)
    source = pathlib.Path(source)
    if not source.is_file() or source.is_symlink():
        refuse("the physical design-checker result source is not one real regular file")
    raw = source.read_bytes()
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the physical design-checker result is not complete JSON: {exc}")
    if not isinstance(report, dict) or set(report) != {
        "verdict", "manifest", "checks", "previous", "findings",
    } or report.get("verdict") not in {"clean", "findings"} \
            or report.get("manifest") != manifest_relative:
        refuse("the physical design-checker result has an invalid top-level shape")
    checks = report["checks"]
    if not isinstance(checks, list) or len(checks) not in {2, 3} or any(
        not isinstance(item, dict) or set(item) != {"subject", "evidence"}
        or not isinstance(item.get("subject"), str) or not item["subject"].strip()
        or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
        for item in checks
    ):
        refuse("the physical design-checker result has no exact checked evidence account")
    prior = frozen["previous"]
    prior_ids = [item["id"] for item in prior["findings"]] if prior else []
    previous = report["previous"]
    if not isinstance(previous, list) or len(previous) != len(prior_ids) or any(
        not isinstance(item, dict) or set(item) != {"id", "status", "evidence"}
        or item.get("status") not in {"addressed", "still-open"}
        or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
        for item in previous
    ) or [item.get("id") for item in previous] != prior_ids:
        refuse("the physical design-checker result does not verify every prior finding exactly once")
    findings = report["findings"]
    if not isinstance(findings, list) or any(
        not isinstance(item, dict) or set(item) != {
            "id", "where", "what", "why", "impact", "previous",
        }
        or not TASK_RE.fullmatch(str(item.get("id")))
        or item.get("impact") not in IMPACTS
        or any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in ("where", "what", "why"))
        or not isinstance(item.get("previous"), list)
        or item["previous"] != sorted(set(item["previous"]))
        or any(identity not in prior_ids for identity in item["previous"])
        for item in findings
    ) or [item["id"] for item in findings] != list(range(1, len(findings) + 1)):
        refuse("the physical design-checker result has malformed or non-contiguous findings")
    still_open = [item["id"] for item in previous if item["status"] == "still-open"]
    carried = [identity for finding in findings for identity in finding["previous"]]
    if carried != still_open:
        refuse("the physical design-checker result drops, duplicates or invents a still-open prior finding")
    prior_impacts = {item["id"]: item["impact"] for item in prior["findings"]} if prior else {}
    for finding in findings:
        if finding["previous"]:
            strongest = max(
                (prior_impacts[identity] for identity in finding["previous"]),
                key=IMPACT_RANK.__getitem__,
            )
            if IMPACT_RANK[finding["impact"]] < IMPACT_RANK[strongest]:
                refuse("a carried design finding lowers its previously admitted impact")
    outcome = "clean" if not findings else "findings"
    if report["verdict"] != outcome:
        refuse("the physical design-checker verdict contradicts its exact findings")
    canonical = (json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode()
    result_relative = manifest_relative.removesuffix("-manifest.json") + "-result.json"
    atomic_publish(result_relative, canonical, "the physical design-checker result")
    return {
        "outcome": outcome,
        "findings": len(findings),
        "critical": sum(item["impact"] == "CRITICAL" for item in findings),
        "important": sum(item["impact"] == "IMPORTANT" for item in findings),
        "minor": sum(item["impact"] == "MINOR" for item in findings),
        "report": result_relative,
        "report_sha256": sha256(canonical),
        "manifest": manifest_relative,
        "manifest_sha256": sha256(manifest_payload),
    }


def final_tree(manifest_relative, current_tree, resolved_disagreement="-"):
    _, _, frozen = load_manifest(manifest_relative)
    if not re.fullmatch(r"[0-9a-f]{40,64}", current_tree):
        refuse("the final candidate tree identity is malformed")
    git_bytes("cat-file", "-e", f"{current_tree}^{{tree}}")
    state = plan_state(frozen["lot"], frozen["task"])
    for key in ("contract_sha256", "design_sha256", "plan_projection_sha256",
                "plan_ownership_sha256"):
        if state[key] != frozen[key]:
            refuse(f"the final plan changed its frozen {key.removesuffix('_sha256')}")
    expected_disagreement = frozen["disagreement_sha256"] \
        if resolved_disagreement == "-" else resolved_disagreement
    if expected_disagreement is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", expected_disagreement):
        refuse("the accepted final Disagreement identity is malformed")
    if state["disagreement_sha256"] != expected_disagreement:
        refuse("the final plan carries an unreviewed Disagreement generation")
    plan_copy = f"docs/plans/{WORKSPACE.name}-{frozen['lot']}-plan.md"
    changed = git_bytes("diff", "--name-only", "-z", frozen["tree"], current_tree).stdout
    paths = [item.decode("utf-8", "surrogateescape") for item in changed.split(b"\0") if item]
    if any(path != plan_copy for path in paths):
        refuse("the final gate candidate changes bytes outside the reviewed candidate and plan projection")
    committed_plan = tree_file(current_tree, plan_copy)
    workspace_plan = real_workspace_file(state["plan"], "the construction plan").read_bytes()
    if committed_plan != workspace_plan:
        refuse("the final tree does not carry the exact reviewed plan publication")
    print(json.dumps({"tree": current_tree, "plan": plan_copy}, separators=(",", ":")))


def main():
    if len(sys.argv) < 2:
        refuse("a command is required")
    command, args = sys.argv[1], sys.argv[2:]
    if command == "plan-state" and len(args) == 2:
        print(json.dumps(plan_state(*args), separators=(",", ":"), sort_keys=True))
    elif command == "committed-plan-state" and len(args) == 3:
        print(json.dumps(committed_plan_state(*args), separators=(",", ":"), sort_keys=True))
    elif command == "disagreement" and len(args) == 4:
        print(json.dumps(disagreement_state(*args), separators=(",", ":"), sort_keys=True))
    elif command == "design-disagreement" and len(args) == 4:
        print(json.dumps(design_disagreement_state(*args), separators=(",", ":"), sort_keys=True))
    elif command == "manifest" and len(args) == 7:
        print(json.dumps(manifest(*args), separators=(",", ":"), sort_keys=True))
    elif command == "design-manifest" and len(args) == 4:
        print(json.dumps(design_manifest(*args), separators=(",", ":"), sort_keys=True))
    elif command == "read" and len(args) == 5:
        read_candidate(*args)
    elif command == "count" and len(args) == 1:
        manifest_count(*args)
    elif command == "item" and len(args) == 2:
        manifest_item(*args)
    elif command == "previous" and len(args) == 1:
        manifest_previous(*args)
    elif command == "previous-count" and len(args) == 1:
        previous_count(*args)
    elif command == "previous-item" and len(args) == 2:
        previous_item(*args)
    elif command == "read-plan" and len(args) == 2:
        read_plan_generation(*args)
    elif command == "read-design" and len(args) == 2:
        read_design_generation(*args)
    elif command == "design-previous-count" and len(args) == 1:
        design_previous_count(*args)
    elif command == "design-previous-item" and len(args) == 2:
        design_previous_item(*args)
    elif command == "publish-result" and len(args) == 2:
        print(json.dumps(strict_result(*args), separators=(",", ":"), sort_keys=True))
    elif command == "publish-design-result" and len(args) == 2:
        print(json.dumps(strict_design_result(*args), separators=(",", ":"), sort_keys=True))
    elif command == "final-tree" and len(args) in {2, 3}:
        final_tree(*args)
    else:
        refuse("unknown command or wrong argument count")


if __name__ == "__main__":
    main()
