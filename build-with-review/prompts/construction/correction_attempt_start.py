#!/usr/bin/env python3
"""Start one Correction Round task attempt from its exact opened authority."""

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
COMMON = HERE.parent / "common"
sys.path.insert(0, str(COMMON))

from correction_authority import EMPTY_FINAL_CHECKER_SET_SHA256  # noqa: E402
from work_unit import resolve_correction  # noqa: E402


def refuse(message):
    print(f"**correction attempt ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args, check=True):
    result = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if check and result.returncode != 0:
        refuse(result.stderr.strip() or result.stdout.strip() or "a required command refused")
    return result


def git_output(*args):
    return run("git", "-C", str(REPO), *args).stdout.strip()


def marker_exists():
    return os.path.lexists(WORKSPACE / "attempt-in-flight")


def used_attempt(entries, built, round_number, task, attempt):
    return any(
        entry.get("kind") in {"attempt.succeeded", "attempt.failed", "paused", "aborted"}
        and entry.get("lot") == built and entry.get("correction") == round_number
        and entry.get("task") == task
        and (entry.get("data") or {}).get("attempt") == attempt
        for entry in entries
    )


def start(args):
    if args.retry != "-":
        refuse("Correction Round retry obligations are not available at this implementation checkpoint")
    try:
        resolved = resolve_correction(args.built, args.round, args.task)
    except (OSError, ValueError) as exc:
        refuse(str(exc))

    if marker_exists():
        refuse("attempt-in-flight already owns another attempt")
    dirty = git_output("status", "--porcelain")
    if dirty:
        refuse(f"the tree is not clean:\n{dirty}")

    ref_root = resolved["ref_root"]
    task_zero = git_output("rev-parse", f"{ref_root}/task-0")
    if args.task == 1:
        predecessor = task_zero
    else:
        predecessor = git_output("rev-parse", f"{ref_root}/task-{args.task - 1}")
    for task in range(1, args.task):
        git_output("rev-parse", f"{ref_root}/task-{task}")
    if run(
        "git", "-C", str(REPO), "show-ref", "--verify", "--quiet",
        f"{ref_root}/task-{args.task}", check=False,
    ).returncode == 0:
        refuse(f"task {args.task} is already stable")
    head = git_output("rev-parse", "HEAD")
    if run("git", "-C", str(REPO), "merge-base", "--is-ancestor", predecessor, head,
           check=False).returncode != 0:
        refuse("the current branch omits the required correction predecessor")
    gate = run(
        "bash", str(HERE / "gate-check.sh"), "require-current", check=False,
    )
    if gate.returncode != 0:
        refuse("the current Correction Round base has no accepted current gate")

    common_progress = HERE.parent / "common" / "progress.py"
    verdicts = run(
        str(common_progress), "construction-verdict-check", "history", check=False,
    )
    if verdicts.returncode != 0:
        refuse("construction has an unsettled checker or diagnostic verdict")

    from work_unit import progress  # imported here to keep the CLI error boundary local
    entries = progress.journal_entries()
    if used_attempt(entries, args.built, args.round, args.task, args.attempt):
        refuse("the Correction Round attempt number was already used")
    try_ref = f"{ref_root}/task-{args.task}-try-{args.attempt}"
    if run("git", "-C", str(REPO), "show-ref", "--verify", "--quiet", try_ref,
           check=False).returncode == 0:
        refuse("the Correction Round attempt already has a try ref")

    task = resolved["task"]
    marker = {
        "schema": 2,
        "unit": resolved["unit"],
        "unit_authority_sha256": resolved["authority"]["sha256"],
        "tree_authority": resolved["tree_authority"],
        "task": args.task,
        "attempt": args.attempt,
        "document": {
            "path": resolved["workspace_document"],
            "manifest_sha256": resolved["task_manifest_sha256"],
            "controller_sha256": resolved["controller_sha256"],
            "design_contract_sha256": task["design_contract_sha256"],
            "consumer_account_sha256": task["consumer_account_sha256"],
            "task_contract_sha256": task["task_contract_sha256"],
            "design_sha256": task["design_sha256"],
            "disagreement_sha256": task["disagreement_sha256"],
        },
        "retry": "-",
        "design_proof_authority": None,
        "outstanding_final_checker_set_sha256": EMPTY_FINAL_CHECKER_SET_SHA256,
        "assigned_final_checker_obligations": [],
    }
    run("git", "-C", str(REPO), "update-ref", f"{ref_root}/attempt-base", head)
    marker_path = WORKSPACE / "attempt-in-flight"
    temporary = marker_path.with_name(f"{marker_path.name}.tmp-{os.getpid()}")
    try:
        with open(temporary, "x", encoding="utf-8") as target:
            json.dump(marker, target, sort_keys=True, separators=(",", ":"))
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, marker_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(
        f"ATTEMPT correction {args.built} round {args.round} "
        f"task {args.task} try {args.attempt}\nFROM {head}",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("task", type=int)
    parser.add_argument("attempt", type=int)
    parser.add_argument("retry", nargs="?", default="-")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.task < 1 or args.attempt < 1:
        refuse("the Correction Round attempt identity is malformed")
    start(args)


if __name__ == "__main__":
    main()
