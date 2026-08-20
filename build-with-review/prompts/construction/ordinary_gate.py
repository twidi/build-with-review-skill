#!/usr/bin/env python3
"""Run the exact frozen ordinary gate and publish its complete physical report."""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from gate_file import GateFileError, read_gate_commands


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
MARKER = WORKSPACE / "gate-check-in-progress"
GATE = REPO / ".superpowers" / "bwr" / "gate.md"


def refuse(message):
    print(f"**ordinary gate ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def real_file(path, subject):
    current = path.anchor and pathlib.Path(path.anchor) or pathlib.Path()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current /= part
        if current.is_symlink():
            refuse(f"{subject} traverses a symlink: {current}")
    if not path.is_file():
        refuse(f"{subject} is not one real regular file: {path}")
    return path


def marker_data(op):
    raw = real_file(MARKER, "the gate-check marker").read_text(encoding="utf-8").splitlines()
    data = {}
    for line in raw:
        key, separator, value = line.partition(" ")
        if not separator or not value or key in data:
            refuse("the gate-check marker is malformed")
        data[key] = value
    if len(data) != 11 or data.get("op") != op or data.get("scope") != "review":
        refuse("the marker does not own this exact ordinary gate operation")
    return data


def repository_state():
    result = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain=v1", "-z"], capture_output=True,
    )
    if result.returncode:
        refuse(result.stderr.decode("utf-8", "replace") or "git status failed")
    return result.stdout


def candidate_tree():
    result = subprocess.run(["git", "-C", str(REPO), "write-tree"], capture_output=True, text=True)
    if result.returncode:
        refuse(result.stderr or "git write-tree failed")
    return result.stdout.strip()


def atomic_report(op, report):
    ground = WORKSPACE
    for part in ("reports", "gate"):
        ground /= part
        if ground.exists() or ground.is_symlink():
            if ground.is_symlink() or not ground.is_dir():
                refuse(f"the gate report ground is not one real directory: {ground}")
        else:
            ground.mkdir()
    target = ground / f"{op}.json"
    payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
            refuse("the gate report already exists with different or foreign bytes")
        return
    descriptor, name = tempfile.mkstemp(prefix=f".{op}.", dir=ground)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    except FileExistsError:
        if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
            refuse("the gate report raced with different bytes")
    finally:
        temporary.unlink(missing_ok=True)


def run(op):
    if not re.fullmatch(r"[0-9a-f]{64}", op):
        refuse("the operation identity is malformed")
    marker = marker_data(op)
    try:
        commands = read_gate_commands(real_file(GATE, "gate.md"))
    except (OSError, UnicodeError, GateFileError) as exc:
        refuse(str(exc))
    before = repository_state()
    if candidate_tree() != marker["tree"]:
        refuse("the staged candidate changed before the ordinary gate")
    results = []
    for command in commands:
        completed = subprocess.run(
            ["bash", "-c", command], cwd=REPO, capture_output=True, text=True,
        )
        output = (completed.stdout + completed.stderr).strip()
        if output:
            print(output)
        after_command = repository_state()
        if after_command != before or candidate_tree() != marker["tree"]:
            refuse(f"gate command changed the candidate or repository state: {command}")
        results.append({
            "command": command,
            "status": "green" if completed.returncode == 0 else "red",
            "count": 1,
            "example": output.splitlines()[0][:300] if output else f"exit {completed.returncode}",
        })
    report = {
        "op": op, "gate": marker["gate"], "tree": marker["tree"], "commands": results,
        "cleanliness": {"completed": True, "unchanged": True, "paths": []},
        "surface": {"completed": True, "status": "unchanged", "candidates": []},
    }
    atomic_report(op, report)
    print(f"ORDINARY GATE REPORT {op}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        refuse("usage: ordinary_gate.py <op>")
    run(sys.argv[1])
