#!/usr/bin/env python3
"""Start one Correction Round task attempt from its exact opened authority."""

import argparse
import contextvars
import hashlib
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

from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
)
from correction_lifecycle import TaskFacts, admit_task  # noqa: E402
from work_unit import resolve_correction  # noqa: E402


CORRECTION_OWNER_MARKERS = {
    "amendment-commit-in-progress",
    "document-copy-in-progress",
    "gate-check-in-progress",
    "plan-commit-in-progress",
    "rewind-in-progress",
    "spec-breach-recovery-in-progress",
    "spec-commit-in-progress",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "correction-rewind-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
    "correction-round-escalation-in-progress",
}


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


def unfinished_correction_owner():
    return next(
        (name for name in sorted(CORRECTION_OWNER_MARKERS)
         if os.path.lexists(WORKSPACE / name)),
        None,
    )


def operation_identity(args):
    account = {
        "kind": "correction-attempt-start",
        "built": args.built,
        "round": args.round,
        "task": args.task,
        "attempt": args.attempt,
    }
    return "correction-attempt-start:" + hashlib.sha256(json.dumps(
        account, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def start_owned(args):
    if args.retry != "-":
        refuse("Correction Round retry obligations are not available at this implementation checkpoint")
    try:
        resolved = resolve_correction(
            args.built, args.round, args.task, include_rewind_recoveries=True,
        )
    except (OSError, ValueError) as exc:
        refuse(str(exc))

    pending_owner = unfinished_correction_owner()
    if pending_owner is not None:
        refuse(f"another workflow owner is unfinished: {pending_owner}")
    if marker_exists():
        refuse("attempt-in-flight already owns another attempt")
    dirty = git_output("status", "--porcelain")
    if dirty:
        refuse(f"the tree is not clean:\n{dirty}")

    ref_root = resolved["ref_root"]
    from work_unit import progress  # imported here to keep the CLI error boundary local
    entries = progress.journal_entries()
    recoveries = resolved.pop("_rewind_success_recoveries")
    projection = contextvars.copy_context()
    projection.run(
        progress.CORRECTION_REWIND_SUCCESS_RECOVERIES.set, tuple(recoveries),
    )
    projection.run(progress.CORRECTION_VERDICT_HISTORY_REWIND_PROJECTION.set, True)
    try:
        projection.run(progress.validate_construction_verdict_history, entries)
        stopped = projection.run(
            progress.current_correction_stop_state,
            entries, len(entries), "the correction attempt start",
            unit={"kind": "correction", "built": args.built, "round": args.round},
        )
    except ValueError as exc:
        refuse(str(exc))
    if stopped is not None:
        refuse("the Correction Round is stopped; resume its exact pause before another attempt")
    try:
        prior_attempt = projection.run(
            progress.correction_attempt_sequence_account,
            entries, len(entries), args.built, args.round, args.task, args.attempt,
            "the correction attempt start",
        )
        attempt_predecessor = projection.run(
            progress.correction_attempt_predecessor_account,
            entries, len(entries), args.built, args.round, args.task,
            "the correction attempt start", require_first_missing=True,
        )
        admit_task(TaskFacts(
            opening_present=True,
            active_owner=None,
            accepted_tasks=args.task - 1,
            task_count=resolved["task_count"],
            task=args.task,
            attempt=args.attempt,
            expected_attempt=args.attempt,
            retry_available=prior_attempt is not None,
            retry_used=False,
            terminal=None,
        ), "retry" if prior_attempt is not None else "start")
    except ValueError as exc:
        refuse(str(exc))
    if run(
        "git", "-C", str(REPO), "show-ref", "--verify", "--quiet",
        f"{ref_root}/task-{args.task}", check=False,
    ).returncode == 0:
        refuse(f"task {args.task} is already stable")
    head = git_output("rev-parse", "HEAD")
    if head != attempt_predecessor["commit"]:
        refuse("current HEAD is not the exact Correction Round attempt predecessor")
    gate = run(
        "bash", str(HERE / "gate-check.sh"), "require-current",
        args.built, str(args.round), check=False,
    )
    if gate.returncode != 0:
        detail = gate.stderr.strip() or gate.stdout.strip()
        refuse(f"the current Correction Round base has no accepted Correction gate: {detail}")
    try_ref = f"{ref_root}/task-{args.task}-try-{args.attempt}"
    if run("git", "-C", str(REPO), "show-ref", "--verify", "--quiet", try_ref,
           check=False).returncode == 0:
        refuse("the Correction Round attempt already has a try ref")

    task = resolved["task"]
    try:
        outstanding = projection.run(
            progress.outstanding_final_checker_set,
            entries, len(entries), args.built, args.round,
            "the correction attempt start",
        )
        assigned = projection.run(
            progress.assigned_final_checker_obligations,
            outstanding, resolved["unit"], args.task, task,
            "the correction attempt start",
        )
    except ValueError as exc:
        refuse(str(exc))
    try:
        _design_authority_index, design_proof_authority = projection.run(
            progress.design_proof_authority_for_assigned_code,
                entries, len(entries), outstanding, resolved["unit"], args.task,
                task, "the correction attempt start",
            )
    except ValueError as exc:
        refuse(str(exc))
    marker = {
        "schema": 2,
        "unit": resolved["unit"],
        "unit_authority_sha256": resolved["authority"]["sha256"],
        "tree_authority": resolved["tree_authority"],
        "task": args.task,
        "attempt": args.attempt,
        "attempt_predecessor": attempt_predecessor,
        "prior_attempt": prior_attempt,
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
        "design_proof_authority": design_proof_authority,
        "outstanding_final_checker_set_sha256": progress.final_checker_set_sha256(
            outstanding,
        ),
        "assigned_final_checker_obligations": assigned,
    }
    run(
        "git", "-C", str(REPO), "update-ref", f"{ref_root}/attempt-base",
        attempt_predecessor["commit"],
    )
    payload = json.dumps(marker, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with WorkspaceFileAnchor(
        WORKSPACE, "attempt-in-flight", "the correction attempt owner",
    ) as anchored:
        anchored.publish(payload, mode=0o600)
    print(
        f"ATTEMPT correction {args.built} round {args.round} "
        f"task {args.task} try {args.attempt}\nFROM {attempt_predecessor['commit']}",
    )


def start(args):
    operation = operation_identity(args)
    from work_unit import progress  # imported here to share one command-local replay cache
    cache_token = progress.CORRECTION_CONTRACT_STATE_CACHE.set({})
    try:
        with CorrectionAuthorityLease.acquire(WORKSPACE, operation):
            start_owned(args)
    except (OSError, ValueError) as exc:
        refuse(str(exc))
    finally:
        progress.CORRECTION_CONTRACT_STATE_CACHE.reset(cache_token)


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
