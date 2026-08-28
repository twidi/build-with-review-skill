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
from correction_round_return import baseline_account as correction_return_baseline_account  # noqa: E402


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


def selected_correction_baseline(entries, selected, owner, head, base, subject):
    if selected.returncode != 0:
        return None
    operation = selected.stdout.strip()
    accepted = [progress.note_data(entry) for entry in entries
                if entry.get("event") == "subagent-ended"
                and entry.get("kind") == "gate-runner"
                and progress.note_data(entry).get("op") == operation
                and "unusable" not in progress.note_data(entry)]
    if len(accepted) != 1:
        fail(f"{subject} has no one exact current gate result")
    if accepted[0].get("scope") != "correction-baseline":
        return None
    if accepted[0].get("owner") != owner \
            or accepted[0].get("head") != head \
            or accepted[0].get("base") != base \
            or accepted[0].get("green") is not True \
            or accepted[0].get("surface") != "unchanged":
        fail(f"{subject} is not the exact current correction baseline")
    return operation


def pending_revision(args, entries, opening):
    path = WORKSPACE / "correction-round-revision-in-progress"
    if not path.exists() and not path.is_symlink():
        return None
    try:
        status = path.lstat()
        raw = path.read_bytes()
        account = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the correction baseline revision marker is malformed: {exc}")
    if path.is_symlink() or not path.is_file() or status.st_nlink < 1 \
            or json.dumps(account, sort_keys=True, separators=(",", ":")).encode() + b"\n" != raw:
        fail("the correction baseline revision marker is not one canonical real file")
    if account.get("schema") != 1 or account.get("built") != args.built \
            or account.get("round") != args.round \
            or account.get("phase") not in {"baseline-required", "terminal-ready"} \
            or not isinstance(account.get("revision"), int) or account["revision"] < 2 \
            or account.get("baseline_owner") != progress.correction_revision_baseline_owner(
                args.built, args.round, account["revision"], account.get("commit"),
            ):
        fail("the correction baseline revision marker changes its owner")
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round, "the correction revision baseline",
    )
    if account.get("previous") != state["proof"] \
            or account.get("previous_execution_authority_sha256") \
            != state["execution_authority_sha256"] \
            or account.get("parent_commit") is None:
        fail("the correction baseline revision marker changes its predecessor authority")
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    tree = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True,
    )
    status_result = subprocess.run(
        ["git", "-C", progress.project_root(), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or head.stdout.strip() != account.get("commit") \
            or tree.returncode != 0 or tree.stdout.strip() != account.get("tree") \
            or status_result.returncode != 0 or status_result.stdout:
        fail("the correction revision baseline candidate is not its clean document commit")
    return account


def pending_final_checker_map(args, entries):
    path = WORKSPACE / "final-checker-contract-map-in-progress"
    if not path.exists() and not path.is_symlink():
        return None
    try:
        status = path.lstat()
        raw = path.read_bytes()
        marker = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the correction baseline final-checker marker is malformed: {exc}")
    if path.is_symlink() or not path.is_file() or status.st_nlink < 1 \
            or json.dumps(marker, sort_keys=True, separators=(",", ":")).encode() + b"\n" != raw \
            or marker.get("schema") != 1 or marker.get("phase") != "prepared" \
            or marker.get("work_unit") != {
                "kind": "correction", "built": args.built, "round": args.round,
            } or not re.fullmatch(r"[0-9a-f]{64}", str(marker.get("operation"))):
        fail("the correction baseline final-checker marker changes its owner")
    revisions = [(index, entry) for index, entry in enumerate(entries)
                 if entry.get("kind") == "correction.round.revised"
                 and progress.note_data(entry).get("schema") == 2
                 and progress.note_data(entry).get("producer") \
                 == "final-checker-contract-map"
                 and progress.note_data(entry).get("built") == args.built
                 and progress.note_data(entry).get("round") == args.round
                 and progress.note_data(entry).get("mapping", {}).get("operation") \
                 == marker["operation"]]
    if not revisions:
        return None
    if len(revisions) != 1:
        fail("the correction baseline has duplicate final-checker document revisions")
    index, entry = revisions[0]
    progress.validate_correction_round_revision_entry(entries, index, entry)
    event = progress.note_data(entry)
    if event.get("baseline") != {"required": True, "reused_gate": None}:
        fail("the correction baseline final-checker revision does not require a gate")
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round,
        "the final-checker mapping baseline",
    )
    if state.get("proof") != progress.journal_line_proof(index) \
            or state.get("commit") != event.get("commit") \
            or state.get("tree") != event.get("tree"):
        fail("the correction baseline final-checker revision is not current")
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    tree = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True,
    )
    clean = subprocess.run(
        ["git", "-C", progress.project_root(), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or head.stdout.strip() != event["commit"] \
            or tree.returncode != 0 or tree.stdout.strip() != event["tree"] \
            or clean.returncode != 0 or clean.stdout:
        fail("the final-checker mapping baseline is not its clean document commit")
    return {
        "commit": event["commit"],
        "tree": event["tree"],
        "revision": event["revision"],
        "baseline_owner": progress.correction_revision_baseline_owner(
            args.built, args.round, event["revision"], event["commit"],
        ),
    }


def pending_rewind(args, entries):
    path = WORKSPACE / "correction-rewind-in-progress"
    if not path.exists() and not path.is_symlink():
        return None
    try:
        status = path.lstat()
        raw = path.read_bytes()
        account = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"the correction baseline rewind marker is malformed: {exc}")
    event = account.get("event_base") if isinstance(account, dict) else None
    unit = event.get("unit") if isinstance(event, dict) else None
    if path.is_symlink() or not path.is_file() or status.st_nlink < 1 \
            or json.dumps(account, sort_keys=True, separators=(",", ":")).encode() + b"\n" != raw \
            or account.get("schema") != 1 or account.get("disposition") != "rewind" \
            or account.get("phase") != "baseline-required" \
            or unit != {"kind": "correction", "built": args.built, "round": args.round} \
            or not isinstance(account.get("baseline_owner"), str) \
            or not event.get("crossed_authorities") or event.get("gate") is not None:
        fail("the correction baseline rewind marker changes its owner")
    head = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    tree = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True,
    )
    dirty = subprocess.run(
        ["git", "-C", progress.project_root(), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or head.stdout.strip() != event.get("result_commit") \
            or tree.returncode != 0 or tree.stdout.strip() != event.get("result_tree") \
            or dirty.returncode != 0 or dirty.stdout:
        fail("the correction rewind baseline candidate is not its exact clean result tree")
    return account


def run(args):
    entries, opening, close = exact_opening(args)
    return_marker = WORKSPACE / "correction-amendment-return-in-progress"
    if return_marker.exists() or return_marker.is_symlink():
        account = correction_return_baseline_account(args)
        task_zero = exact_task_zero(args, opening["base_commit"])
        selected = current_gate()
        gate = selected_correction_baseline(
            entries, selected, account["baseline_owner"], account["commit"],
            account["commit"], "the Correction AMENDMENT return baseline",
        )
        print(json.dumps({
            "schema": 1,
            "built": args.built,
            "round": args.round,
            "base_commit": account["commit"],
            "task_zero": task_zero,
            "mode": "fresh" if gate is not None else "required",
            "gate": gate,
            "owner": account["baseline_owner"],
        }, sort_keys=True, separators=(",", ":")))
        return
    rewind = pending_rewind(args, entries)
    if rewind is not None:
        task_zero = exact_task_zero(args, opening["base_commit"])
        event = rewind["event_base"]
        selected = current_gate()
        gate = None
        mode = "required"
        gate = selected_correction_baseline(
            entries, selected, rewind["baseline_owner"], event["result_commit"],
            event["result_commit"], "the correction rewind baseline",
        )
        if gate is not None:
            mode = "fresh"
        print(json.dumps({
            "schema": 1,
            "built": args.built,
            "round": args.round,
            "base_commit": event["result_commit"],
            "task_zero": task_zero,
            "mode": mode,
            "gate": gate,
            "owner": rewind["baseline_owner"],
        }, sort_keys=True, separators=(",", ":")))
        return
    final_map = pending_final_checker_map(args, entries)
    if final_map is not None:
        task_zero = exact_task_zero(args, opening["base_commit"])
        selected = current_gate()
        gate = None
        mode = "required"
        gate = selected_correction_baseline(
            entries, selected, final_map["baseline_owner"], final_map["commit"],
            final_map["commit"], "the final-checker mapping baseline",
        )
        if gate is not None:
            mode = "fresh"
        print(json.dumps({
            "schema": 1,
            "built": args.built,
            "round": args.round,
            "base_commit": final_map["commit"],
            "task_zero": task_zero,
            "mode": mode,
            "gate": gate,
            "owner": final_map["baseline_owner"],
        }, sort_keys=True, separators=(",", ":")))
        return
    revision = pending_revision(args, entries, opening)
    if revision is not None:
        task_zero = exact_task_zero(args, opening["base_commit"])
        selected = current_gate()
        gate = None
        mode = "required"
        gate = selected_correction_baseline(
            entries, selected, revision["baseline_owner"], revision["commit"],
            revision["commit"], "the correction revision baseline",
        )
        if gate is not None:
            mode = "fresh"
        print(json.dumps({
            "schema": 1,
            "built": args.built,
            "round": args.round,
            "base_commit": revision["commit"],
            "task_zero": task_zero,
            "mode": mode,
            "gate": gate,
            "owner": revision["baseline_owner"],
        }, sort_keys=True, separators=(",", ":")))
        return
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
    gate = selected_correction_baseline(
        entries, selected, owner, base_commit, base_commit,
        "the correction base baseline",
    )
    if gate is not None:
        mode = "fresh"
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
