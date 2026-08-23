#!/usr/bin/env python3
"""Select the exact reusable or required first Correction Round baseline."""

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
COMMON = WORKSPACE / "prompts" / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402


def fail(message):
    raise ValueError(message)


def exact_opening(args):
    entries = progress.journal_entries()
    matches = [(index, entry) for index, entry in enumerate(entries)
               if entry.get("kind") == "correction.round.opened"
               and progress.note_data(entry).get("built") == args.built
               and progress.note_data(entry).get("round") == args.round]
    if len(matches) != 1:
        fail("the correction baseline has no one exact Correction Round opening")
    index, entry = matches[0]
    data = progress.normalize_correction_round_opening(
        entries[:index], progress.note_data(entry), "the correction baseline opening",
        historical=True,
    )
    later_terminals = [candidate for candidate in entries[index + 1:]
                       if candidate.get("kind") in {
                           "correction.round.built",
                           "correction.round.resolved",
                           "correction.round.escalated",
                       }
                       and progress.note_data(candidate).get("built") == args.built
                       and progress.note_data(candidate).get("round") == args.round]
    if later_terminals:
        fail("the correction baseline follows a terminal Correction Round")
    _, close = progress.journal_entry_from_proof(
        entries, data["pass_close"], "the correction baseline pass close",
    )
    close_data = progress.note_data(close)
    return entries, data, close_data


def exact_task_zero(args, base_commit):
    reference = f"refs/bwr/{WORKSPACE.name}/{args.built}/correction-{args.round}/task-0"
    result = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "--verify", reference],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != base_commit:
        fail("the correction baseline has no exact task-0 ref")
    return reference


def current_gate():
    return subprocess.run(
        ["bash", progress.GATE_CHECK, "require-current"],
        capture_output=True, text=True,
    )


def run(args):
    entries, opening, close = exact_opening(args)
    base_commit = opening["base_commit"]
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    status = subprocess.run(
        ["git", "-C", progress.project_root(), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or head.stdout.strip() != base_commit \
            or status.returncode != 0 or status.stdout:
        fail("the correction baseline candidate is not the clean frozen base")
    task_zero = exact_task_zero(args, base_commit)
    owner = f"correction/{args.built}/c{args.round}/{base_commit}"
    selected = current_gate()
    mode = "required"
    gate = None
    if selected.returncode == 0:
        operation = selected.stdout.strip()
        if operation == close["base_gate"]:
            mode, gate = "reuse", operation
        else:
            accepted = [progress.note_data(entry) for entry in entries
                        if entry.get("event") == "subagent-ended"
                        and entry.get("kind") == "gate-runner"
                        and progress.note_data(entry).get("op") == operation
                        and "unusable" not in progress.note_data(entry)]
            if len(accepted) != 1 or accepted[0].get("scope") != "baseline" \
                    or accepted[0].get("owner") != owner \
                    or accepted[0].get("head") != base_commit \
                    or accepted[0].get("green") is not True \
                    or accepted[0].get("surface") != "unchanged":
                fail("the current gate is not the correction base or its exact fresh baseline")
            mode, gate = "fresh", operation
    print(json.dumps({
        "schema": 1,
        "built": args.built,
        "round": args.round,
        "base_commit": base_commit,
        "task_zero": task_zero,
        "mode": mode,
        "gate": gate,
        "owner": owner,
    }, sort_keys=True, separators=(",", ":")))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1:
        fail("the correction baseline arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError) as exc:
        print(f"**correction-round-baseline ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
