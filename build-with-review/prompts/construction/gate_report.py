#!/usr/bin/env python3
"""Publish or audit one complete op-scoped physical gate-runner report."""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

from gate_file import GateFileError, read_gate_commands
from gate_execution import (
    GateExecutionError,
    atomic_publish,
    canonical_bytes,
    ensure_report_ground,
    frozen_execution,
    read_account,
    validate_frozen_execution,
    verify_frozen,
)


def refuse(message):
    print(f"**gate report ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
REPORT_GROUND = WORKSPACE / "reports" / "gate"
MAX_OBSERVATION_BYTES = 1024 * 1024


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


def validate_identity(op, expected_gate, expected_tree, expected_execution):
    if not re.fullmatch(r"[0-9a-f]{64}", op):
        refuse("the operation identity is invalid")
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_gate):
        refuse("the frozen gate identity is invalid")
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_tree):
        refuse("the frozen tree identity is invalid")
    if expected_execution != "-" and not re.fullmatch(r"[0-9a-f]{64}", expected_execution):
        refuse("the frozen gate execution identity is invalid")


def gate_commands(expected_gate):
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
    return commands


def validate_report(report, op, expected_gate, expected_tree, expected_execution, commands,
                    account_results, account_sha256):
    legacy_keys = {"op", "gate", "tree", "commands", "cleanliness", "surface"}
    expected_keys = legacy_keys if expected_execution == "-" else legacy_keys | {
        "execution", "command_account_sha256"
    }
    if not isinstance(report, dict) or set(report) != expected_keys:
        refuse("the physical gate report has an incomplete top-level shape")
    if report["op"] != op or report["gate"] != expected_gate or report["tree"] != expected_tree:
        refuse("the physical gate report belongs to another frozen logical check")

    if expected_execution != "-":
        try:
            execution = validate_frozen_execution(
                report["execution"], expected_gate, commands, expected_tree,
            )
        except ValueError as exc:
            refuse(str(exc))
        if hashlib.sha256(canonical_bytes(execution)).hexdigest() != expected_execution:
            refuse("the physical gate report carries another frozen execution")
        if report["command_account_sha256"] != account_sha256:
            refuse("the physical gate report names another command account")

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

    return command_green


def audit(op, expected_gate, expected_tree, expected_execution="-"):
    validate_identity(op, expected_gate, expected_tree, expected_execution)
    commands = gate_commands(expected_gate)
    account_results = None
    account_sha256 = None
    if expected_execution != "-":
        account, account_sha256 = read_account(
            op, expected_execution, commands, authenticate_outputs=True,
        )
        account_results = account["commands"]

    relative = pathlib.PurePosixPath("reports", "gate", f"{op}.json")
    report_path = real_file(WORKSPACE / relative, WORKSPACE, "the physical gate report")
    raw = report_path.read_bytes()
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the physical gate report is not complete JSON: {exc}")
    command_green = validate_report(
        report, op, expected_gate, expected_tree, expected_execution, commands,
        account_results, account_sha256,
    )

    outcome = {
        "green": command_green and report["cleanliness"]["unchanged"],
        "surface": report["surface"]["status"],
        "report": str(relative),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "commands": len(commands),
    }
    print(json.dumps(outcome, separators=(",", ":"), sort_keys=True))


def read_observations():
    raw = sys.stdin.buffer.read(MAX_OBSERVATION_BYTES + 1)
    if len(raw) > MAX_OBSERVATION_BYTES:
        refuse("gate observations exceed the one-megabyte limit")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"gate observations are not complete JSON: {exc}")
    if not isinstance(value, dict) or set(value) != {
        "schema", "commands", "cleanliness", "surface"
    } or value.get("schema") != 1:
        refuse("gate observations have an incomplete top-level shape")
    return value


def publish(op, expected_gate, expected_tree, expected_execution):
    validate_identity(op, expected_gate, expected_tree, expected_execution)
    marker, execution, execution_hash = frozen_execution(op)
    if marker["gate"] != expected_gate or marker["tree"] != expected_tree \
            or execution_hash != expected_execution:
        refuse("the report publisher received another logical gate identity")
    verify_frozen(marker)
    commands = gate_commands(expected_gate)
    account, account_sha256 = read_account(
        op, expected_execution, commands, authenticate_outputs=True,
    )
    observations = read_observations()
    summaries = observations["commands"]
    if not isinstance(summaries, list) or len(summaries) != len(commands):
        refuse("gate observations have no one summary per frozen gate command")
    results = []
    for number, (summary, account_result) in enumerate(zip(summaries, account["commands"]), 1):
        if not isinstance(summary, dict) or set(summary) != {"count", "example"}:
            refuse(f"gate observation {number} has an invalid shape")
        results.append({
            "command": account_result["command"],
            "status": "green" if account_result["returncode"] == 0 else "red",
            "count": summary["count"],
            "example": summary["example"],
        })
    report = {
        "op": op,
        "gate": expected_gate,
        "tree": expected_tree,
        "commands": results,
        "cleanliness": observations["cleanliness"],
        "surface": observations["surface"],
    }
    if expected_execution != "-":
        report["execution"] = execution
        report["command_account_sha256"] = account_sha256
    validate_report(
        report, op, expected_gate, expected_tree, expected_execution, commands,
        account["commands"], account_sha256,
    )
    ensure_report_ground()
    verify_frozen(marker)
    target = REPORT_GROUND / f"{op}.json"
    atomic_publish(target, canonical_bytes(report))
    print(f"GATE REPORT {op}")


def main():
    try:
        if len(sys.argv) == 6 and sys.argv[1] == "publish":
            publish(*sys.argv[2:])
        elif len(sys.argv) in {4, 5}:
            audit(*sys.argv[1:])
        else:
            refuse(
                "usage: gate_report.py <op> <frozen gate blob> <frozen tree> "
                "[execution sha256|-] | gate_report.py publish <op> <gate> <tree> <execution>"
            )
    except GateExecutionError as exc:
        refuse(str(exc))


if __name__ == "__main__":
    main()
