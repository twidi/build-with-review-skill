#!/usr/bin/env python3
"""Publish the active Correction Round artifact into the repository candidate."""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()

from correction_round import parse_artifact, parse_artifact_bytes
from work_unit import progress, resolve_correction


def refuse(message):
    print(f"**correction artifact ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args, check=True):
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)
    if check and result.returncode != 0:
        refuse(result.stderr.decode("utf-8", "replace").strip() or "Git refused")
    return result


def marker():
    path = WORKSPACE / "attempt-in-flight"
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("the attempt marker is not one real file")
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        refuse(f"the correction attempt marker is invalid: {exc}")
    return value


def publish(args):
    try:
        resolved = resolve_correction(args.built, args.round)
        current = parse_artifact(
            WORKSPACE / resolved["workspace_document"],
            expected_built=args.built, expected_round=args.round,
        )
    except (OSError, ValueError) as exc:
        refuse(str(exc))
    active = marker()
    unit = {"kind": "correction", "built": args.built, "round": args.round}
    task = active.get("task")
    if active.get("schema") != 2 or active.get("unit") != unit \
            or not isinstance(task, int) or isinstance(task, bool) or task < 1 \
            or active.get("unit_authority_sha256") != resolved["authority"]["sha256"]:
        refuse("the active attempt belongs to another work unit")
    document = active.get("document") or {}
    matches = [candidate for candidate in current["tasks"] if candidate["task"] == task]
    selected = matches[0] if len(matches) == 1 else {}
    if current["controller_sha256"] != document.get("controller_sha256") \
            or current["manifest_sha256"] != document.get("manifest_sha256") \
            or selected.get("task_contract_sha256") != document.get("task_contract_sha256"):
        refuse("the workspace artifact changes frozen controller authority")

    relative = resolved["repository_document"]
    committed = git("show", f"HEAD:{relative}", check=False)
    if committed.returncode != 0:
        if task != 1:
            refuse("a later correction task has no predecessor repository artifact")
    else:
        if task == 1 and current.get("task_projection") is None:
            refuse("Task 1 cannot replace a predecessor repository artifact")
        try:
            predecessor = parse_artifact_bytes(
                committed.stdout, expected_built=args.built, expected_round=args.round,
            )
        except ValueError as exc:
            refuse(f"the predecessor repository artifact is invalid: {exc}")
        if predecessor["controller_sha256"] != current["controller_sha256"] \
                or predecessor["manifest_sha256"] != current["manifest_sha256"]:
            refuse("the repository and workspace artifacts have different controller authority")
        predecessor_tasks = {item["task"]: item for item in predecessor["tasks"]}
        for new in (item for item in current["tasks"] if item["task"] < task):
            old = predecessor_tasks.get(new["task"])
            if old is None:
                refuse("the current task invents an earlier active task")
            if any(old[key] != new[key] for key in (
                "task_contract_sha256", "design_sha256", "disagreement_sha256",
            )):
                refuse("the current task changes an earlier accepted task projection")

    if os.path.lexists(WORKSPACE / "gate-check-in-progress"):
        refuse("artifact publication must precede the next gate opening")
    helper = WORKSPACE / "prompts" / "common" / "document-copy.sh"
    copy = subprocess.run(
        [str(helper), "copy", resolved["workspace_document"], relative, "replace"],
        cwd=REPO, capture_output=True, text=True,
    )
    if copy.returncode != 0:
        refuse(copy.stderr.strip() or copy.stdout.strip() or "document copy refused")
    finish = subprocess.run(
        [str(helper), "finish", resolved["workspace_document"], relative, "replace"],
        cwd=REPO, capture_output=True, text=True,
    )
    if finish.returncode != 0:
        refuse(finish.stderr.strip() or finish.stdout.strip() or "document copy finish refused")
    target = REPO / pathlib.PurePosixPath(relative)
    if target.read_bytes() != (WORKSPACE / resolved["workspace_document"]).read_bytes():
        refuse("the repository artifact differs from the workspace authority")
    print(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) or args.round < 1:
        refuse("the Correction Round identity is malformed")
    cache_token = progress.CORRECTION_CONTRACT_STATE_CACHE.set({})
    try:
        publish(args)
    finally:
        progress.CORRECTION_CONTRACT_STATE_CACHE.reset(cache_token)


if __name__ == "__main__":
    main()
