#!/usr/bin/env python3
"""Publish one pending final-checker consumer mapping."""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
COMMON = WORKSPACE / "prompts" / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
import correction_attempt_failure as failure  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
    publish_content_object,
)
from correction_round import parse_artifact  # noqa: E402
from final_checker_obligations import materialize_transition  # noqa: E402

MARKER_NAME = "final-checker-contract-map-in-progress"
GATE_MARKER_NAME = "gate-check-in-progress"
BLOCKING_MARKERS = (
    failure.BLOCKING_MARKERS | {"correction-attempt-failure-in-progress"}
) - {MARKER_NAME}


def fail(message):
    raise ValueError(message)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def read_marker():
    with WorkspaceFileAnchor(
        WORKSPACE, MARKER_NAME, "the final-checker contract-map owner",
    ) as anchored:
        payload = anchored.read_regular()
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the final-checker contract-map owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the final-checker contract-map owner is not canonical")
    return payload, account


def note_args(kind, task, data):
    return SimpleNamespace(
        kind=kind, mandate=None, task=task, round=None,
        text=None, text_file=None,
        data=json.dumps(data, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def source_failure(entries, marker):
    matches = []
    for index, entry in enumerate(entries):
        data = progress.note_data(entry)
        additions = data.get("final_checker_transition", {}).get("additions") \
            if isinstance(data, dict) else None
        if entry.get("kind") == "attempt.failed" \
                and entry.get("lot") == marker["work_unit"]["built"] \
                and entry.get("correction") == marker["work_unit"]["round"] \
                and isinstance(additions, list) \
                and any(
                    isinstance(item, dict)
                    and isinstance(item.get("assignment"), dict)
                    and item["assignment"].get("owner") == "task-contract-map"
                    for item in additions
                ):
            expected = failure.historical_map_marker_account(entries, index, entry)
            if expected.get("operation") == marker.get("operation"):
                matches.append((index, entry, expected))
    if len(matches) != 1:
        fail("the final-checker map has no one exact source failure")
    index, entry, expected = matches[0]
    if marker != expected:
        fail("the final-checker contract-map owner changes its exact failure account")
    return index, entry


def preservation_transition(current):
    dispositions = []
    for member in current["entries"]:
        assignment = {
            key: value for key, value in member["assignment"].items()
            if key != "mapping_proof"
        }
        dispositions.append({
            "obligation_id": member["source"]["obligation_id"],
            "outcome": "deferred" if assignment["owner"] == "task" else "carried",
            "assignment": assignment,
            "evidence": None,
        })
    transition, output = materialize_transition(
        current, additions=[], dispositions=dispositions,
        transfer_kind="contract-map-document",
    )
    current_accounts = [
        {"source": item["source"], "assignment": item["assignment"]}
        for item in current["entries"]
    ]
    output_accounts = [
        {"source": item["source"], "assignment": item["assignment"]}
        for item in output["entries"]
    ]
    if output_accounts != current_accounts:
        fail("the controller document publication remaps an obligation")
    return transition


def git_text(*arguments):
    result = subprocess.run(
        ["git", "-C", progress.project_root(), *arguments],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def matching_document_commit(state, accepted, artifact_sha256):
    accepted_commit = accepted[-1][2]["sha"]
    head = git_text("rev-parse", "HEAD")
    if head == accepted_commit:
        return None
    parent = subprocess.run(
        ["git", "-C", progress.project_root(), "rev-parse", "--verify", f"{head}^"],
        capture_output=True, text=True,
    )
    names = subprocess.run(
        ["git", "-C", progress.project_root(), "diff-tree", "--no-commit-id",
         "--name-only", "-r", head], capture_output=True, text=True,
    )
    blob = subprocess.run(
        ["git", "-C", progress.project_root(), "show", f"{head}:{state['path']}"],
        capture_output=True,
    )
    if parent.returncode != 0 or parent.stdout.strip() != accepted_commit \
            or names.returncode != 0 or names.stdout.splitlines() != [state["path"]] \
            or blob.returncode != 0 \
            or hashlib.sha256(blob.stdout).hexdigest() != artifact_sha256:
        fail("HEAD is not the exact final-checker map document commit")
    return head


def publish_document_commit(state, accepted, artifact_sha256):
    document_copy = WORKSPACE / "prompts" / "common" / "document-copy.sh"
    commit = matching_document_commit(state, accepted, artifact_sha256)
    copied = subprocess.run(
        [document_copy, "copy", state["path"], state["path"], "replace"],
        cwd=progress.project_root(), capture_output=True, text=True,
    )
    if copied.returncode != 0:
        fail(copied.stderr.strip() or copied.stdout.strip())
    if commit is None:
        staged = subprocess.run(
            ["git", "-C", progress.project_root(), "add", "--", state["path"]],
            capture_output=True, text=True,
        )
        if staged.returncode != 0:
            fail(staged.stderr.strip() or "the map document could not be staged")
        if git_text("diff", "--cached", "--name-only").splitlines() != [state["path"]]:
            fail("the map document commit would consume another staged path")
        committed = subprocess.run(
            ["git", "-C", progress.project_root(), "-c", "core.hooksPath=/dev/null",
             "commit", "-q", "-m", "docs(correction): map final-checker obligation",
             "--", state["path"]], capture_output=True, text=True,
        )
        if committed.returncode != 0:
            fail(committed.stderr.strip() or committed.stdout.strip())
        commit = matching_document_commit(state, accepted, artifact_sha256)
    finished = subprocess.run(
        [document_copy, "finish", state["path"], state["path"], "replace"],
        cwd=progress.project_root(), capture_output=True, text=True,
    )
    if finished.returncode != 0:
        fail(finished.stderr.strip() or finished.stdout.strip())
    if git_text("status", "--porcelain"):
        fail("the map document commit did not leave one clean tree")
    return commit, git_text("rev-parse", f"{commit}^{{tree}}")


def accepted_mapping_baseline(entries, event):
    if event["baseline"]["required"] is False:
        return event["baseline"]["reused_gate"]
    owner = progress.correction_revision_baseline_owner(
        event["built"], event["round"], event["revision"], event["commit"],
    )
    matches = [progress.note_data(entry) for entry in entries
               if entry.get("event") == "subagent-ended"
               and entry.get("kind") == "gate-runner"
               and progress.note_data(entry).get("scope") == "correction-baseline"
               and progress.note_data(entry).get("owner") == owner
               and progress.note_data(entry).get("head") == event["commit"]
               and progress.note_data(entry).get("base") == event["commit"]
               and "unusable" not in progress.note_data(entry)]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].get("green") is not True \
            or matches[0].get("surface") != "unchanged":
        fail("the final-checker map has another controller-document baseline")
    verified = subprocess.run(
        [
            "bash", progress.GATE_CHECK, "require-correction-baseline",
            matches[0]["op"], event["commit"], event["built"], str(event["round"]),
        ],
        capture_output=True, text=True,
    )
    if verified.returncode != 0:
        fail(verified.stderr.strip() or verified.stdout.strip())
    return matches[0]["op"]


def derive_revision(entries, marker, failure_proof):
    built = marker["work_unit"]["built"]
    correction = marker["work_unit"]["round"]
    task = marker["target_task"]
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction,
        "the final-checker contract-map document",
    )
    accepted = progress.accepted_correction_task_entries_at_prefix(
        entries, len(entries), built, correction, state["opening_index"],
    )
    path = WORKSPACE / state["path"]
    artifact = parse_artifact(path, expected_built=built, expected_round=correction)
    payload = path.read_bytes()
    published = publish_content_object(WORKSPACE, built, payload, ".md")
    targets = [candidate for candidate in artifact["tasks"] if candidate["task"] == task]
    if len(targets) != 1:
        fail("the final-checker contract-map has no one exact target task")
    target = targets[0]
    current = progress.outstanding_final_checker_set(
        entries, len(entries), built, correction,
        "the final-checker contract-map document",
    )
    if accepted:
        commit, tree = publish_document_commit(
            state, accepted, artifact["artifact_sha256"],
        )
        baseline = {"required": True, "reused_gate": None}
    else:
        commit, tree = state["commit"], state["tree"]
        baseline = {"required": False, "reused_gate": state["gate"]}
    event = {
        "schema": 2,
        "producer": "final-checker-contract-map",
        "built": built,
        "round": correction,
        "revision": state["revision"] + 1,
        "previous": state["proof"],
        "previous_execution_authority_sha256": state["execution_authority_sha256"],
        "mapping": {
            "operation": marker["operation"],
            "source_failure": failure_proof,
            "task": task,
            "prior_ids": marker["prior_ids"],
            "added_ids": marker["added_ids"],
            "next_ids": marker["next_ids"],
            "previous_consumer_account_sha256": marker["document"][
                "consumer_account_sha256"
            ],
            "next_consumer_account_sha256": marker["next_consumer_account_sha256"],
            "previous_task_contract_sha256": marker["document"]["task_contract_sha256"],
            "next_task_contract_sha256": marker["next_task_contract_sha256"],
        },
        "artifact_sha256": artifact["artifact_sha256"],
        "artifact_object": str(published.relative_to(WORKSPACE)),
        "controller_sha256": artifact["controller_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "design_contract_sha256": target["design_contract_sha256"],
        "consumer_account_sha256": target["consumer_account_sha256"],
        "task_contract_sha256": target["task_contract_sha256"],
        "design_sha256": target["design_sha256"],
        "disagreement_sha256": target["disagreement_sha256"],
        "commit": commit,
        "tree": tree,
        "baseline": baseline,
        "retry_transition": preservation_transition(current),
    }
    progress.normalize_correction_round_revision(
        entries, event, "the final-checker contract-map document",
    )
    return event


def matching_event(entries, kind, operation):
    matches = [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") == kind
        and progress.note_data(entry).get("operation") == operation
    ]
    if kind == "correction.round.revised":
        matches = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == kind
            and progress.note_data(entry).get("mapping", {}).get("operation") == operation
        ]
    if len(matches) > 1:
        fail(f"the final-checker map has duplicate {kind} terminals")
    return matches[0] if matches else None


def append_owned(kind, task, event, operation, lease):
    current_entries = progress.journal_entries()
    progress.require_no_current_correction_stop(
        current_entries, len(current_entries), event["built"], event["round"],
        f"the final-checker map's {kind}",
    )
    existing = matching_event(progress.journal_entries(), kind, operation)
    if existing is not None:
        if progress.note_data(existing[1]) != event:
            fail(f"the recorded {kind} changes the final-checker map")
        return existing
    note = note_args(kind, task, event)
    progress.cmd_note_with_lease(
        note, lease, operation, owner_marker=MARKER_NAME,
    )
    existing = matching_event(progress.journal_entries(), kind, operation)
    if existing is None:
        fail(f"the final-checker map did not publish {kind}")
    return existing


def require_no_live_gate():
    path = WORKSPACE / GATE_MARKER_NAME
    if path.exists() or path.is_symlink():
        fail("the final-checker contract map cannot cross a live Correction gate")


def require_no_foreign_owner():
    for name in BLOCKING_MARKERS:
        if (WORKSPACE / name).exists() or (WORKSPACE / name).is_symlink():
            fail(f"another workflow owner is unfinished: {name}")


def public_document_update(marker):
    document = marker.get("document")
    workspace_path = document.get("workspace_path") if isinstance(document, dict) else None
    try:
        artifact = pathlib.Path(workspace_path)
        relative = artifact.relative_to(WORKSPACE)
    except (TypeError, ValueError):
        fail("the final-checker contract-map owner has no exact workspace document")
    ids = marker.get("next_ids")
    if not isinstance(ids, list) or not ids or any(
        not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity)
        for identity in ids
    ):
        fail("the final-checker contract-map owner has no exact obligation list")
    return {
        "schema": 1,
        "work_unit": marker["work_unit"],
        "target_task": marker["target_task"],
        "artifact": relative.as_posix(),
        "field": "Consumes final-checker obligations",
        "obligation_ids": ids,
        "replacement": "Consumes final-checker obligations: " + ", ".join(ids),
        "continue": [
            str(HERE / "final-checker-contract-map.sh"),
            marker["work_unit"]["built"],
            str(marker["work_unit"]["round"]),
        ],
    }


def require_document_update(marker):
    account = public_document_update(marker)
    artifact = parse_artifact(
        WORKSPACE / account["artifact"],
        expected_built=marker["work_unit"]["built"],
        expected_round=marker["work_unit"]["round"],
    )
    targets = [
        task for task in artifact["tasks"] if task["task"] == marker["target_task"]
    ]
    if len(targets) != 1:
        fail("the final-checker contract-map has no one exact target task")
    current = targets[0]["obligation_ids"]
    if current == marker["next_ids"]:
        return True
    if current != marker["prior_ids"]:
        fail("the final-checker contract-map document changes its obligation authority")
    print("FINAL CHECKER CONTRACT MAP DOCUMENT UPDATE REQUIRED")
    print(json.dumps(account, sort_keys=True, separators=(",", ":")))
    return False


def revision_phase(args):
    with CorrectionAuthorityLease.acquire(WORKSPACE, args.operation) as lease:
        entries = progress.journal_entries()
        progress.require_no_active_correction_amendment(
            entries, len(entries), args.built, args.round,
            "the final-checker contract map",
        )
        require_no_foreign_owner()
        require_no_live_gate()
        _marker_payload, marker = read_marker()
        if marker.get("operation") != args.operation \
                or marker.get("work_unit") != {
                    "kind": "correction", "built": args.built, "round": args.round,
                } or marker.get("phase") != "prepared":
            fail("the final-checker contract-map arguments change its pending owner")
        task = marker.get("target_task")
        if isinstance(task, bool) or not isinstance(task, int) or task < 1:
            fail("the final-checker contract-map owner has no exact target task")

        entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            entries, len(entries), args.built, args.round,
            "the final-checker contract map",
        )
        failure_index, _failure = source_failure(entries, marker)
        failure_proof = progress.journal_line_proof(failure_index)
        revision = matching_event(entries, "correction.round.revised", args.operation)
        if revision is None:
            if not require_document_update(marker):
                return False
            revision_event = derive_revision(entries, marker, failure_proof)
            revision = append_owned(
                "correction.round.revised", task, revision_event, args.operation, lease,
            )
        progress.validate_correction_round_revision_entry(
            progress.journal_entries(), revision[0], revision[1],
        )
        return True


def mapping_phase(args):
    with CorrectionAuthorityLease.acquire(WORKSPACE, args.operation) as lease:
        entries = progress.journal_entries()
        progress.require_no_active_correction_amendment(
            entries, len(entries), args.built, args.round,
            "the final-checker contract map",
        )
        require_no_foreign_owner()
        require_no_live_gate()
        marker_payload, marker = read_marker()
        if marker.get("operation") != args.operation \
                or marker.get("work_unit") != {
                    "kind": "correction", "built": args.built, "round": args.round,
                } or marker.get("phase") != "prepared":
            fail("the final-checker contract-map arguments change its pending owner")
        task = marker.get("target_task")
        if isinstance(task, bool) or not isinstance(task, int) or task < 1:
            fail("the final-checker contract-map owner has no exact target task")

        entries = progress.journal_entries()
        progress.require_no_current_correction_stop(
            entries, len(entries), args.built, args.round,
            "the final-checker contract map",
        )
        failure_index, _failure = source_failure(entries, marker)
        failure_proof = progress.journal_line_proof(failure_index)
        revision = matching_event(entries, "correction.round.revised", args.operation)
        if revision is None:
            fail("the final-checker contract-map document authority is unavailable")
        progress.validate_correction_round_revision_entry(
            entries, revision[0], revision[1],
        )
        revision_event = progress.note_data(revision[1])
        if accepted_mapping_baseline(entries, revision_event) is None:
            print(
                "BASELINE REQUIRED\n"
                f"Run correction-round-baseline.sh {args.built} {args.round}, "
                "finish its exact baseline gate, then rerun this command."
            )
            return
        mapping = matching_event(entries, "final-checker.contract-mapped", args.operation)
        if mapping is None:
            mapping_event = progress.final_checker_contract_mapping_account(
                entries, len(entries), args.built, args.round, args.operation,
                failure_proof, task, "the final-checker contract map",
            )
            append_owned(
                "final-checker.contract-mapped", task, mapping_event, args.operation, lease,
            )

        entries = progress.journal_entries()
        mapping = matching_event(entries, "final-checker.contract-mapped", args.operation)
        if mapping is None:
            fail("the final-checker contract-map terminal is unavailable")
        progress.validate_final_checker_contract_mapped_entry(
            entries, mapping[0], mapping[1],
        )
        with WorkspaceFileAnchor(
            WORKSPACE, MARKER_NAME, "the completed final-checker contract-map owner",
        ) as anchored:
            anchored.remove_exact(hashlib.sha256(marker_payload).hexdigest())
        print(f"FINAL CHECKER CONTRACT MAPPED {args.built} c{args.round} task {task}")


def run(args):
    if args.operation is None:
        _payload, marker = read_marker()
        if marker.get("work_unit") != {
            "kind": "correction", "built": args.built, "round": args.round,
        } or not re.fullmatch(r"[0-9a-f]{64}", str(marker.get("operation"))):
            fail("the public final-checker contract-map selector found another owner")
        args.operation = marker["operation"]
    if not revision_phase(args):
        return
    mapping_phase(args)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("operation", nargs="?")
    args = parser.parse_args()
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or args.round < 1 or args.operation is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", args.operation):
        fail("the final-checker contract-map arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"**final-checker contract-map ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
