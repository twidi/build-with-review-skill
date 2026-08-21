#!/usr/bin/env python3
"""Audit one complete op-scoped physical gate-runner report."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

from gate_file import GateFileError, read_gate_commands
from gate_execution import canonical_bytes, read_account, validate_frozen_execution


def refuse(message):
    print(f"**gate report ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()


def real_file(path, root, subject):
    try:
        relative = path.relative_to(root)
    except ValueError:
        refuse(f"{subject} is outside {root}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            refuse(f"{subject} traverses a symlink: {current}")
    if not current.is_file():
        refuse(f"{subject} is not one real regular file: {current}")
    return current


def audit(op, expected_gate, expected_tree, expected_execution="-"):
    if not re.fullmatch(r"[0-9a-f]{64}", op):
        refuse("the operation identity is invalid")
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_gate):
        refuse("the frozen gate identity is invalid")
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_tree):
        refuse("the frozen tree identity is invalid")
    if expected_execution != "-" and not re.fullmatch(r"[0-9a-f]{64}", expected_execution):
        refuse("the frozen gate execution identity is invalid")

    gate = real_file(REPO / ".superpowers" / "bwr" / "gate.md", REPO, "gate.md")
    actual_gate = subprocess.check_output(
        ["git", "-C", str(REPO), "hash-object", str(gate)], text=True
    ).strip()
    if actual_gate != expected_gate:
        refuse(f"gate.md changed: expected {expected_gate}, got {actual_gate}")
    try:
        commands = read_gate_commands(gate)
    except (OSError, UnicodeError, GateFileError) as exc:
        refuse(str(exc))

    relative = pathlib.PurePosixPath("reports", "gate", f"{op}.json")
    report_path = real_file(WORKSPACE / relative, WORKSPACE, "the physical gate report")
    raw = report_path.read_bytes()
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the physical gate report is not complete JSON: {exc}")
    legacy_keys = {"op", "gate", "tree", "commands", "cleanliness", "surface"}
    expected_keys = legacy_keys if expected_execution == "-" else legacy_keys | {
        "execution", "command_account_sha256"
    }
    if not isinstance(report, dict) or set(report) != expected_keys:
        refuse("the physical gate report has an incomplete top-level shape")
    if report["op"] != op or report["gate"] != expected_gate or report["tree"] != expected_tree:
        refuse("the physical gate report belongs to another frozen logical check")

    account_results = None
    if expected_execution != "-":
        try:
            execution = validate_frozen_execution(
                report["execution"], expected_gate, commands, expected_tree,
            )
        except ValueError as exc:
            refuse(str(exc))
        if hashlib.sha256(canonical_bytes(execution)).hexdigest() != expected_execution:
            refuse("the physical gate report carries another frozen execution")
        account, account_sha256 = read_account(
            op, expected_execution, commands, authenticate_outputs=True,
        )
        if report["command_account_sha256"] != account_sha256:
            refuse("the physical gate report names another command account")
        account_results = account["commands"]

    results = report["commands"]
    if not isinstance(results, list) or len(results) != len(commands):
        refuse("the physical gate report has no one result per frozen gate command")
    actual_commands = []
    command_green = True
    for index, result in enumerate(results, 1):
        if not isinstance(result, dict) or set(result) != {"command", "status", "count", "example"}:
            refuse(f"command result {index} has an invalid shape")
        command = result["command"]
        status = result["status"]
        count = result["count"]
        example = result["example"]
        if not isinstance(command, str) or status not in {"green", "red"} \
                or not isinstance(count, int) or isinstance(count, bool) or count < 0 \
                or not isinstance(example, str) or not example:
            refuse(f"command result {index} has invalid values")
        actual_commands.append(command)
        command_green = command_green and status == "green"
        if account_results is not None:
            account_result = account_results[index - 1]
            expected_status = "green" if account_result["returncode"] == 0 else "red"
            if command != account_result["command"] or status != expected_status:
                refuse(f"command result {index} contradicts its physical command account")
    if actual_commands != commands:
        refuse("the physical gate report omitted, reordered, added or changed a frozen gate command")

    cleanliness = report["cleanliness"]
    if not isinstance(cleanliness, dict) or set(cleanliness) != {"completed", "unchanged", "paths"} \
            or cleanliness.get("completed") is not True \
            or not isinstance(cleanliness.get("unchanged"), bool) \
            or not isinstance(cleanliness.get("paths"), list) \
            or any(not isinstance(path, str) or not path for path in cleanliness["paths"]):
        refuse("the physical gate report has no complete repository-cleanliness result")
    if cleanliness["unchanged"] and cleanliness["paths"]:
        refuse("an unchanged cleanliness result names changed paths")
    if not cleanliness["unchanged"] and not cleanliness["paths"]:
        refuse("a changed cleanliness result names no changed path")

    surface = report["surface"]
    if not isinstance(surface, dict) or set(surface) != {"completed", "status", "candidates"} \
            or surface.get("completed") is not True \
            or surface.get("status") not in {"unchanged", "different"} \
            or not isinstance(surface.get("candidates"), list):
        refuse("the physical gate report has no complete gate-surface result")
    allowed_kinds = {"addition", "removal", "rename", "definition-change", "uncovered-target"}
    for candidate in surface["candidates"]:
        if not isinstance(candidate, dict) or set(candidate) != {"kind", "evidence"} \
                or candidate.get("kind") not in allowed_kinds \
                or not isinstance(candidate.get("evidence"), str) or not candidate["evidence"]:
            refuse("the physical gate report has a malformed gate-surface candidate")
    if surface["status"] == "unchanged" and surface["candidates"]:
        refuse("an unchanged gate surface carries candidates")
    if surface["status"] == "different" and not surface["candidates"]:
        refuse("a different gate surface carries no candidate evidence")

    outcome = {
        "green": command_green and cleanliness["unchanged"],
        "surface": surface["status"],
        "report": str(relative),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "commands": len(commands),
    }
    print(json.dumps(outcome, separators=(",", ":"), sort_keys=True))


def main():
    if len(sys.argv) not in {4, 5}:
        refuse("usage: gate_report.py <op> <frozen gate blob> <frozen tree> [execution sha256|-]")
    audit(*sys.argv[1:])


if __name__ == "__main__":
    main()
