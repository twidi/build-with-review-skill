#!/usr/bin/env python3
"""Rewind accepted Correction Round task refs under one composite authority."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
COMMON = HERE.parent / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
)
from work_unit import resolve_correction  # noqa: E402

MARKER_NAME = "correction-rewind-in-progress"
BLOCKING_MARKERS = {
    "amendment-commit-in-progress",
    "attempt-in-flight",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-product-authority-in-progress",
    "correction-round-built-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "document-copy-in-progress",
    "gate-check-in-progress",
    "plan-commit-in-progress",
    "rewind-in-progress",
    "spec-breach-recovery-in-progress",
    "spec-commit-in-progress",
}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def run(*args, check=True, env=None, input_text=None):
    result = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, env=env, input=input_text,
    )
    if check and result.returncode != 0:
        fail(result.stderr.strip() or result.stdout.strip() or "a required command refused")
    return result


def git_output(*args, env=None):
    return run("git", "-C", str(REPO), *args, env=env).stdout.strip()


def note_args(event, task):
    return SimpleNamespace(
        kind="rewind.done", mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def operation_identity(args):
    payload = {
        "kind": "correction-rewind",
        "built": args.built,
        "round": args.round,
        "earliest_task": args.earliest_task,
        "attempt": args.attempt,
        "failure_proof": args.failure_proof,
    }
    return "correction-rewind:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def ensure_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        path = WORKSPACE / name
        if path.exists() or path.is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def publish_marker(account):
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction rewind owner",
    ) as anchored:
        anchored.publish(canonical_bytes(account) + b"\n")


def read_marker():
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the correction rewind owner",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the correction rewind owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the correction rewind owner is not canonical")
    return payload, account


def remove_marker(payload):
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the completed correction rewind owner",
    ) as anchored:
        anchored.remove_exact(hashlib.sha256(payload).hexdigest())


def temp_index_from(commit):
    descriptor, path = tempfile.mkstemp(prefix=".correction-rewind-index-", dir=WORKSPACE)
    os.close(descriptor)
    os.unlink(path)
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = path
    run("git", "-C", str(REPO), "read-tree", commit, env=environment)
    return path, environment


def build_relands(crossed, base_commit, artifact_path, built, round_number, rewind):
    relands = []
    onto = base_commit
    try:
        for transition in crossed:
            index_path, environment = temp_index_from(onto)
            try:
                listing = run(
                    "git", "-C", str(REPO), "ls-tree", transition["source_commit"],
                    "--", artifact_path,
                ).stdout.strip()
                match = re.fullmatch(r"([0-7]{6}) blob ([0-9a-f]{40,64})\t(.+)", listing)
                if match is None or match.group(3) != artifact_path:
                    fail("a retained correction revision has no exact artifact blob")
                run(
                    "git", "-C", str(REPO), "update-index", "--add", "--cacheinfo",
                    match.group(1), match.group(2), artifact_path, env=environment,
                )
                tree = git_output("write-tree", env=environment)
            finally:
                try:
                    os.unlink(index_path)
                except FileNotFoundError:
                    pass
            subject = (
                f"{WORKSPACE.name} {built} correction {round_number} rewind {rewind} "
                f"— retain {transition['kind']}"
            )
            result = run(
                "git", "-C", str(REPO), "commit-tree", tree, "-p", onto,
                input_text=f"{subject}\n",
            ).stdout.strip()
            relands.append({
                "authority": transition["proof"],
                "onto_commit": onto,
                "result_commit": result,
                "result_tree": tree,
                "transition_sha256": transition["transition_sha256"],
            })
            onto = result
    except BaseException:
        raise
    return relands, onto, git_output("rev-parse", f"{onto}^{{tree}}")


def derive_account(args, operation):
    entries = progress.journal_entries()
    resolved = resolve_correction(args.built, args.round)
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round, "the correction rewind",
    )
    failure_index, failure = progress.journal_entry_from_proof(
        entries, args.failure_proof, "the correction rewind failure",
    )
    failure_data = progress.note_data(failure)
    if failure.get("kind") != "attempt.failed" or failure.get("lot") != args.built \
            or failure.get("correction") != args.round \
            or failure_data.get("schema") != 2 \
            or failure_data.get("classification") != "C3.9c" \
            or failure_data.get("attempt", 0) + 1 != args.attempt \
            :
        fail("the correction rewind does not consume the exact current C3.9c failure")
    progress.validate_attempt_failed_entry(entries, failure_index, failure)
    if failure_data.get("unit_authority_sha256") != state["authority_sha256"] \
            or failure_data.get("execution_authority_sha256") \
            != state["execution_authority_sha256"]:
        fail("the correction rewind failure is not under the current execution authority")
    later_boundaries = [
        entry for entry in entries[failure_index + 1:]
        if (
            entry.get("lot") == args.built and entry.get("correction") == args.round
            and entry.get("kind") in {
                "attempt.failed", "attempt.succeeded", "paused", "aborted", "rewind.done",
            }
        ) or (
            entry.get("kind") in {
                "correction.round.revised", "correction.round.built",
                "correction.round.resolved", "correction.round.escalated",
            }
            and progress.note_data(entry).get("built") == args.built
            and progress.note_data(entry).get("round") == args.round
        )
    ]
    if later_boundaries:
        fail("the correction rewind failure is no longer the current transition owner")
    if args.earliest_task > failure.get("task", 0):
        fail("the correction rewind target follows its failed task")

    base_ref = f"{resolved['ref_root']}/task-{args.earliest_task - 1}"
    base_commit = git_output("rev-parse", "--verify", f"{base_ref}^{{commit}}")
    base_tree = git_output("rev-parse", f"{base_commit}^{{tree}}")
    rewind = state.get("rewind_ordinal", 0) + 1
    moved = []
    for task in range(args.earliest_task, resolved["task_count"] + 1):
        source = f"{resolved['ref_root']}/task-{task}"
        found = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{source}^{{commit}}",
            check=False,
        )
        if found.returncode != 0:
            continue
        moved.append({
            "task": task,
            "commit": found.stdout.strip(),
            "from": source,
            "to": f"{resolved['ref_root']}/rewound/r-{rewind}/task-{task}",
        })
    crossed = progress.retained_authority_chain(
        entries, len(entries), state, base_commit, "the correction rewind",
    )
    relands, result_commit, result_tree = build_relands(
        crossed, base_commit, state["path"], args.built, args.round, rewind,
    )
    event_base = {
        "schema": 2,
        "unit": {"kind": "correction", "built": args.built, "round": args.round},
        "unit_authority_sha256": state["authority_sha256"],
        "cause": {"kind": "attempt-failure", "proof": args.failure_proof},
        "previous_rewind": state.get("rewind_proof"),
        "ref_root": resolved["ref_root"],
        "rewind": rewind,
        "target": {
            "earliest_task": args.earliest_task,
            "base_ref": base_ref,
            "base_commit": base_commit,
            "base_tree": base_tree,
        },
        "attempt": args.attempt,
        "moved": moved,
        "crossed_authorities": crossed,
        "relands": relands,
        "result_commit": result_commit,
        "result_tree": result_tree,
        "gate": None,
        "outstanding_retry_set_sha256": progress.final_checker_set_sha256(
            progress.outstanding_final_checker_set(
                entries, len(entries), args.built, args.round, "the correction rewind",
            )
        ),
    }
    phase = "baseline-required" if crossed else "terminal-ready"
    account = {
        "schema": 1,
        "operation": operation,
        "disposition": "rewind",
        "phase": phase,
        "event_base": event_base,
        "baseline_owner": (
            f"correction/{args.built}/c{args.round}/rewind-{rewind}/{result_commit}"
            if crossed else None
        ),
    }
    if not crossed:
        event = dict(event_base)
        event["pending_owner_sha256"] = progress.correction_rewind_pending_owner_sha256(event)
        account["event"] = event
    return account


def validate_marker(account, expected):
    if account != expected:
        fail("the pending correction rewind changes its complete frozen account")


def validate_pending_marker(args, operation, account):
    required = {
        "schema", "operation", "disposition", "phase", "event_base", "baseline_owner",
    }
    if account.get("phase") == "terminal-ready":
        required.add("event")
    if not isinstance(account, dict) or set(account) != required \
            or account.get("schema") != 1 or account.get("operation") != operation \
            or account.get("disposition") != "rewind" \
            or account.get("phase") not in {"baseline-required", "terminal-ready"}:
        fail("the pending correction rewind owner is malformed")
    event = account.get("event") or account.get("event_base")
    if not isinstance(event, dict) or event.get("unit") != {
        "kind": "correction", "built": args.built, "round": args.round,
    } or event.get("cause") != {
        "kind": "attempt-failure", "proof": args.failure_proof,
    } or event.get("target", {}).get("earliest_task") != args.earliest_task \
            or event.get("attempt") != args.attempt:
        fail("the pending correction rewind owner belongs to another call")
    entries = progress.journal_entries()
    def matches_terminal(entry):
        if entry.get("kind") != "rewind.done":
            return False
        data = progress.note_data(entry)
        if account.get("event") is not None:
            return data == account["event"]
        return {
            key: value for key, value in data.items()
            if key != "pending_owner_sha256"
        } | {"gate": None} == account["event_base"] \
            and data.get("pending_owner_sha256") \
            == progress.correction_rewind_pending_owner_sha256(data)

    terminals = [
        (index, entry) for index, entry in enumerate(entries)
        if matches_terminal(entry)
    ]
    if terminals:
        if len(terminals) != 1:
            fail("the pending correction rewind has duplicate terminals")
        progress.validate_correction_rewind_entry(entries, terminals[0][0], terminals[0][1])
        return terminals
    state = progress.current_correction_contract_state(
        entries, len(entries), args.built, args.round, "the pending correction rewind",
    )
    crossed = event.get("crossed_authorities")
    phase = "baseline-required" if crossed else "terminal-ready"
    baseline_owner = (
        f"correction/{args.built}/c{args.round}/rewind-{event.get('rewind')}/"
        f"{event.get('result_commit')}"
        if crossed else None
    )
    if account.get("phase") != phase or account.get("baseline_owner") != baseline_owner:
        fail("the pending correction rewind changes its completion route")
    if phase == "baseline-required":
        if account.get("event") is not None or event.get("gate") is not None \
                or "pending_owner_sha256" in event:
            fail("the pending correction rewind invents a baseline terminal")
        pending_event = dict(event)
        pending_event["pending_owner_sha256"] = \
            progress.correction_rewind_pending_owner_sha256(pending_event)
    else:
        if account.get("event") is None or {
            key: value for key, value in event.items() if key != "pending_owner_sha256"
        } != account.get("event_base"):
            fail("the pending correction rewind changes its terminal event")
        pending_event = event
    candidate = {
        "kind": "rewind.done", "lot": args.built, "correction": args.round,
        "task": args.earliest_task, "data": pending_event,
    }
    progress.validate_correction_rewind_transition(
        entries + [candidate], len(entries), candidate, state,
        "the pending correction rewind", candidate=True, pending=True,
    )
    return []


def move_refs_and_tree(account):
    event = account.get("event") or account["event_base"]
    for member in event["moved"]:
        source = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{member['from']}^{{commit}}",
            check=False,
        )
        destination = run(
            "git", "-C", str(REPO), "rev-parse", "--verify", f"{member['to']}^{{commit}}",
            check=False,
        )
        if destination.returncode == 0 and destination.stdout.strip() != member["commit"]:
            fail("a rewound correction destination belongs to another commit")
        if destination.returncode != 0:
            if source.returncode != 0 or source.stdout.strip() != member["commit"]:
                fail("a correction stable ref changed before its rewind")
            update = run(
                "git", "-C", str(REPO), "update-ref", member["to"], member["commit"],
                "0" * len(member["commit"]), check=False,
            )
            if update.returncode != 0:
                fail("a correction rewound ref could not publish")
        if source.returncode == 0:
            deleted = run(
                "git", "-C", str(REPO), "update-ref", "-d", member["from"], member["commit"],
                check=False,
            )
            if deleted.returncode != 0:
                fail("a correction stable ref could not retire")
    head = git_output("rev-parse", "HEAD")
    status = git_output("status", "--porcelain")
    if head != event["result_commit"] or status:
        if status:
            fail("the correction rewind found an unexpected dirty tree")
        run("git", "-C", str(REPO), "reset", "-q", "--hard", event["result_commit"])
    if git_output("rev-parse", "HEAD") != event["result_commit"] \
            or git_output("rev-parse", "HEAD^{tree}") != event["result_tree"]:
        fail("the correction rewind did not reach its exact result tree")


def accepted_baseline(entries, account):
    event = account["event_base"]
    selected = run(
        "bash", str(HERE / "gate-check.sh"), "require-current",
        event["unit"]["built"], str(event["unit"]["round"]), check=False,
    )
    if selected.returncode != 0:
        return None
    operation = selected.stdout.strip()
    accepted = [
        progress.note_data(entry) for entry in entries
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
        and progress.note_data(entry).get("op") == operation
        and "unusable" not in progress.note_data(entry)
    ]
    if len(accepted) != 1 or accepted[0].get("scope") != "correction-baseline" \
            or accepted[0].get("owner") != account["baseline_owner"] \
            or accepted[0].get("head") != event["result_commit"] \
            or accepted[0].get("base") != event["result_commit"] \
            or accepted[0].get("green") is not True \
            or accepted[0].get("surface") != "unchanged":
        fail("the current gate is not the exact retained-authority rewind baseline")
    verified = run(
        "bash", str(HERE / "gate-check.sh"), "require-correction-baseline",
        operation, event["result_commit"], event["unit"]["built"],
        str(event["unit"]["round"]), check=False,
    )
    if verified.returncode != 0:
        fail(verified.stderr.strip() or verified.stdout.strip())
    return operation


def close(args):
    operation = operation_identity(args)
    marker_path = WORKSPACE / MARKER_NAME
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        current_entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            current_entries, len(current_entries), args.built, args.round,
            "the correction rewind",
        )
        if marker_path.exists() or marker_path.is_symlink():
            marker_payload, account = read_marker()
            terminals = validate_pending_marker(args, operation, account)
            if terminals:
                move_refs_and_tree(account)
                remove_marker(marker_payload)
                print(
                    f"CORRECTION REWOUND {args.built} c{args.round} "
                    f"from task {args.earliest_task} (already recorded)"
                )
                return
        else:
            ensure_no_foreign_owner()
            if git_output("status", "--porcelain"):
                fail("a fresh correction rewind requires one clean tree")
            account = derive_account(args, operation)
            publish_marker(account)
            marker_payload = canonical_bytes(account) + b"\n"

        move_refs_and_tree(account)
        if account["phase"] == "baseline-required":
            gate = accepted_baseline(progress.journal_entries(), account)
            if gate is None:
                print(
                    "BASELINE REQUIRED\n"
                    f"Run correction-round-baseline.sh {args.built} {args.round}, "
                    "finish its exact baseline gate, then rerun this command."
                )
                return
            event = {**account["event_base"], "gate": gate}
            event["pending_owner_sha256"] = progress.correction_rewind_pending_owner_sha256(event)
            account = {**account, "event": event}

        event = account["event"]
        entries = progress.journal_entries()
        matches = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "rewind.done" and progress.note_data(entry) == event
        ]
        if len(matches) > 1:
            fail("the correction rewind has duplicate terminals")
        if not matches:
            progress.normalize_correction_rewind(
                entries, event,
                {"lot": args.built, "correction": args.round, "task": args.earliest_task},
                "the correction rewind",
            )
            progress.cmd_note_with_lease(
                note_args(event, args.earliest_task), lease, operation,
                owner_marker=MARKER_NAME,
            )
        entries = progress.journal_entries()
        matches = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "rewind.done" and progress.note_data(entry) == event
        ]
        if len(matches) != 1:
            fail("the correction rewind terminal is unavailable")
        progress.validate_correction_rewind_entry(entries, matches[0][0], matches[0][1])
        remove_marker(marker_payload)
    print(f"CORRECTION REWOUND {args.built} c{args.round} from task {args.earliest_task}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("earliest_task", type=int)
    parser.add_argument("attempt", type=int)
    parser.add_argument("failure_proof")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.earliest_task < 1 or args.attempt < 2 \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", args.failure_proof):
        print("**correction rewind ERROR** · malformed correction rewind identity", file=sys.stderr)
        raise SystemExit(1)
    try:
        close(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"**correction rewind ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
