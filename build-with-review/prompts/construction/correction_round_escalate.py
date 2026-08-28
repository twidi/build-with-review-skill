#!/usr/bin/env python3
"""Publish one ordinary pre-AMENDMENT Correction Round escalation."""

import argparse
import hashlib
import json
import os
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
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
    content_object_path,
    publish_content_object,
    replacement_recovery_relative_path,
    validate_content_object,
)
from correction_escalation import parse_artifact  # noqa: E402
import correction_attempt_failure as failure  # noqa: E402

MARKER_NAME = "correction-round-escalation-in-progress"
BLOCKING_MARKERS = {
    "amendment-commit-in-progress",
    "attempt-in-flight",
    "correction-allocation-supersede-in-progress",
    "correction-amendment-return-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "correction-rewind-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
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


def operation_identity(built, correction, blocker):
    account = {
        "kind": "ordinary-correction-escalation", "built": built,
        "round": correction, "blocker": blocker,
    }
    return "correction-round-escalation:" + hashlib.sha256(
        canonical_bytes(account),
    ).hexdigest()


def note_args(event):
    return SimpleNamespace(
        kind="correction.round.escalated", mandate=None, task=None, round=None,
        text=None, text_file=None,
        data=json.dumps(event, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def ensure_no_foreign_owner():
    for name in sorted(BLOCKING_MARKERS):
        if os.path.lexists(WORKSPACE / name):
            fail(f"another workflow owner is unfinished: {name}")


def marker_anchor(subject="the ordinary Correction escalation owner"):
    return WorkspaceFileAnchor(WORKSPACE, MARKER_NAME, subject)


def parse_marker_payload(payload):
    try:
        account = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"the ordinary Correction escalation owner is malformed: {exc}")
    if canonical_bytes(account) + b"\n" != payload:
        fail("the ordinary Correction escalation owner is not canonical")
    return account


def read_marker():
    with marker_anchor() as anchor:
        payload = anchor.read_regular()
    return payload, parse_marker_payload(payload)


def publish_marker(account):
    with marker_anchor() as anchor:
        anchor.publish(canonical_bytes(account) + b"\n", mode=0o600)


def replace_marker(anchor, predecessor_payload, account):
    anchor.replace_exact(
        hashlib.sha256(predecessor_payload).hexdigest(),
        canonical_bytes(account) + b"\n", mode=0o600,
    )


def marker_recovery_generations():
    generations = []
    for path in sorted(WORKSPACE.glob(f".{MARKER_NAME}.correction-recovery-*")):
        relative = path.relative_to(WORKSPACE).as_posix()
        with WorkspaceFileAnchor(
            WORKSPACE, relative, "an ordinary Correction escalation marker recovery",
        ) as recovery:
            payload = recovery.read_regular()
        account = parse_marker_payload(payload)
        expected = replacement_recovery_relative_path(MARKER_NAME, payload)
        if relative != expected.as_posix():
            fail("the ordinary Correction escalation marker recovery has another identity")
        generations.append((relative, payload, account))
    return generations


def validate_marker_recoveries(entries, built, correction, operation):
    generations = marker_recovery_generations()
    for _relative, _payload, account in generations:
        reproject_marker(
            entries, account, built, correction, operation, current=False,
        )
    return generations


def remove_marker(anchor, payload, entries, built, correction, operation):
    generations = validate_marker_recoveries(
        entries, built, correction, operation,
    )
    for relative, recovery_payload, _account in generations:
        with WorkspaceFileAnchor(
            WORKSPACE, relative, "a completed ordinary Correction escalation recovery",
        ) as recovery:
            current = recovery.read_regular()
            if current != recovery_payload:
                fail("an ordinary Correction escalation recovery changed before cleanup")
            recovery.remove_exact(hashlib.sha256(current).hexdigest())
    anchor.remove_exact(hashlib.sha256(payload).hexdigest())


def final_map_owner(entries, blocker, *, require_present=True):
    path = WORKSPACE / "final-checker-contract-map-in-progress"
    blocker_index, blocker_entry = progress.journal_entry_from_proof(
        entries, blocker, "the ordinary Correction escalation blocker",
    )
    additions = progress.note_data(blocker_entry).get(
        "final_checker_transition", {},
    ).get("additions", [])
    if not additions:
        if os.path.lexists(path):
            fail("the ordinary Correction escalation found a foreign map owner")
        return None
    expected = failure.historical_map_marker_account(
        entries, blocker_index, blocker_entry,
    )
    payload = canonical_bytes(expected) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    if os.path.lexists(path):
        with WorkspaceFileAnchor(
            WORKSPACE, "final-checker-contract-map-in-progress",
            "the ordinary Correction escalation final-checker map owner",
        ) as anchor:
            current = anchor.read_regular()
        if current != payload:
            fail("the ordinary Correction escalation has another final-checker map owner")
    elif require_present:
        fail("the ordinary Correction escalation lost its final-checker map owner")
    return digest


def derive_event(entries, built, correction, blocker):
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction, "the ordinary Correction escalation",
    )
    artifact_path = WORKSPACE / "corrections" / built / f"round-{correction}-escalation.md"
    payload = artifact_path.read_bytes()
    artifact = parse_artifact(
        artifact_path, expected_built=built, expected_round=correction,
    )
    if artifact["schema"] != 1 or artifact["producer"] != "ordinary" \
            or artifact["authority"] != state["proof"] or artifact["blocker"] != blocker:
        fail("the ordinary Correction escalation artifact changes its current authority")
    accepted = progress.accepted_correction_task_entries_at_prefix(
        entries, len(entries), built, correction, state["opening_index"],
    )
    completed = [task for task, _index, _data in accepted]
    commit = progress.correction_current_escalation_base(
        state, accepted, "the ordinary Correction escalation",
    )
    if artifact["commit"] != commit:
        fail("the ordinary Correction escalation artifact changes its current commit")
    current = progress.outstanding_final_checker_set(
        entries, len(entries), built, correction, "the ordinary Correction escalation",
    )
    requirements = progress.correction_ordinary_escalation_consumer_requirements(
        current, artifact, state["artifact"]["source_finding_coverage"], correction,
        "the ordinary Correction escalation",
    )
    dispositions = []
    for member, requirement in zip(current["entries"], requirements):
        source = member["source"]
        dispositions.append({
            "obligation_id": source["obligation_id"], "outcome": "carried",
            "assignment": {
                "unit": {
                    "kind": "correction-escalation", "built": built,
                    "round": correction, "producer": "ordinary",
                    "authority": state["proof"],
                },
                "task": None, "phase": "sublot-plan-consumer-map",
                "owner": "escalation-tail", "consumer_requirement": requirement,
            },
            "evidence": None,
        })
    transition, _output = progress.materialize_final_checker_transition(
        current, additions=[], dispositions=dispositions,
        transfer_kind="ordinary-escalation",
    )
    digest = hashlib.sha256(payload).hexdigest()
    object_path = content_object_path(WORKSPACE, built, digest, ".md")
    event = {
        "schema": 1, "producer": "ordinary", "built": built,
        "round": correction, "route": "sublot",
        "opening": progress.journal_line_proof(state["opening_index"]),
        "latest_authority": state["proof"],
        "execution_authority_sha256": state["execution_authority_sha256"],
        "completed_tasks": completed,
        "items": [{
            "id": item["id"], "origins": item["origins"],
            "sources": item["sources"],
            "accepted_contributions": item["accepted_contributions"],
            "blocker": item["blocker"],
        } for item in artifact["items"]],
        "commit": commit, "blocker": blocker,
        "artifact": str(artifact_path.relative_to(WORKSPACE)),
        "artifact_sha256": digest,
        "artifact_object": str(object_path.relative_to(WORKSPACE)),
        "retry_transition": transition,
    }
    return payload, event


def correction_terminals(entries, built, correction):
    return [
        (index, entry) for index, entry in enumerate(entries)
        if entry.get("kind") in {
            "correction.round.built", "correction.round.resolved",
            "correction.round.escalated",
        }
        and progress.note_data(entry).get("built") == built
        and progress.note_data(entry).get("round") == correction
    ]


def retained_marker_identity(account, built, correction):
    event = account.get("event") if isinstance(account, dict) else None
    blocker = event.get("blocker") if isinstance(event, dict) else None
    if not isinstance(event, dict) or event.get("built") != built \
            or event.get("round") != correction or event.get("producer") != "ordinary" \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(blocker)):
        fail("the retained ordinary Correction escalation has malformed owner identity")
    operation = operation_identity(built, correction, blocker)
    if account.get("operation") != operation:
        fail("the retained ordinary Correction escalation has another operation")
    return blocker, operation


def reproject_marker(entries, account, built, correction, operation, *, current=True):
    blocker, current_operation = retained_marker_identity(account, built, correction)
    if current_operation != operation:
        fail("the retained ordinary Correction escalation changes its operation")
    terminals = correction_terminals(entries, built, correction)
    if len(terminals) > 1:
        fail("the ordinary Correction escalation has ambiguous terminals")
    terminal = terminals[0] if terminals else None
    if terminal is not None:
        terminal_index, terminal_entry = terminal
        terminal_data = progress.note_data(terminal_entry)
        if terminal_entry.get("kind") != "correction.round.escalated" \
                or terminal_data.get("producer") != "ordinary":
            fail("the ordinary Correction escalation found another terminal route")
        progress.validate_correction_round_escalated_entry(
            entries, terminal_index, terminal_entry,
        )
        source_entries = entries[:terminal_index]
    else:
        source_entries = entries
    artifact_payload, event = derive_event(
        source_entries, built, correction, blocker,
    )
    if terminal is not None and progress.note_data(terminal[1]) != event:
        fail("the ordinary Correction escalation terminal changes its source account")
    phase = account.get("phase")
    expected = {
        "schema": 1,
        "operation": operation,
        "phase": phase,
        "event": event,
        "final_map_marker_sha256": final_map_owner(
            source_entries, blocker, require_present=terminal is None,
        ),
    }
    if phase not in {"owner-only", "object-published", "terminal-ready"} \
            or account != expected:
        fail("the ordinary Correction escalation owner changes its exact source account")
    if current and terminal is not None and phase != "terminal-ready":
        fail("the ordinary Correction escalation terminal crosses its owner phase")
    if phase in {"object-published", "terminal-ready"}:
        published = validate_content_object(
            WORKSPACE, built, event["artifact_sha256"], ".md",
        )
        if str(published.relative_to(WORKSPACE)) != event["artifact_object"]:
            fail("the ordinary Correction escalation has another immutable object")
    return artifact_payload, event, terminal


def run(args):
    entries = progress.journal_entries()
    marker_path = WORKSPACE / MARKER_NAME
    marker_exists = os.path.lexists(marker_path)
    retained_anchor = None
    retained_payload = None
    retained_identity = None
    if marker_exists:
        retained_anchor = marker_anchor()
        try:
            retained_anchor.__enter__()
            retained_payload = retained_anchor.read_regular()
            retained_status = retained_anchor.status()
            retained_identity = (retained_status.st_dev, retained_status.st_ino)
            candidate = parse_marker_payload(retained_payload)
            marker_blocker, marker_operation = retained_marker_identity(
                candidate, args.built, args.round,
            )
            if args.retained:
                blocker, operation = marker_blocker, marker_operation
            else:
                blocker = args.blocker
                operation = operation_identity(args.built, args.round, blocker)
                if marker_blocker != blocker or marker_operation != operation:
                    fail("the ordinary Correction escalation owner belongs to another operation")
        except BaseException:
            retained_anchor.close()
            raise
    elif args.retained:
        fail("the retained ordinary Correction escalation owner is absent")
    else:
        blocker = args.blocker
        operation = operation_identity(args.built, args.round, blocker)
        terminals = correction_terminals(entries, args.built, args.round)
        if not marker_exists and terminals:
            if len(terminals) != 1:
                fail("the ordinary Correction escalation has ambiguous terminals")
            terminal_index, terminal_entry = terminals[0]
            source_entries = entries[:terminal_index]
            _artifact_payload, event = derive_event(
                source_entries, args.built, args.round, blocker,
            )
            synthetic = {
                "schema": 1, "operation": operation, "phase": "terminal-ready",
                "event": event,
                "final_map_marker_sha256": final_map_owner(
                    source_entries, blocker, require_present=False,
                ),
            }
            _payload, _event, terminal = reproject_marker(
                entries, synthetic, args.built, args.round, operation,
            )
            if terminal is None:
                fail("the ordinary Correction escalation terminal disappeared")
            print(f"CORRECTION ROUND ESCALATED {args.built} {args.round} (already recorded)")
            return
    try:
        with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
            current_entries = progress.journal_entries()
            progress.require_no_current_correction_stop(
                current_entries, len(current_entries), args.built, args.round,
                "the ordinary Correction escalation",
            )
            progress.require_no_active_correction_amendment(
                current_entries, len(current_entries), args.built, args.round,
                "the ordinary Correction escalation",
            )
            if os.path.lexists(marker_path):
                if retained_anchor is not None:
                    current_payload = retained_anchor.read_regular()
                    current_status = retained_anchor.status()
                    if (current_status.st_dev, current_status.st_ino) != retained_identity \
                            or current_payload != retained_payload:
                        fail("the retained ordinary Correction escalation marker was substituted")
                    account = parse_marker_payload(current_payload)
                    retained_anchor.close()
                    retained_anchor = None
                else:
                    _payload, account = read_marker()
                retained_blocker, retained_operation = retained_marker_identity(
                    account, args.built, args.round,
                )
                if retained_operation != operation or retained_blocker != blocker:
                    fail("the ordinary Correction escalation owner belongs to another operation")
            else:
                if args.retained:
                    fail("the retained ordinary Correction escalation owner disappeared")
                ensure_no_foreign_owner()
                dirty = subprocess.run(
                    ["git", "-C", progress.project_root(), "status", "--porcelain"],
                    capture_output=True, text=True,
                )
                if dirty.returncode != 0 or dirty.stdout:
                    fail("the ordinary Correction escalation requires one clean project tree")
                artifact_payload, event = derive_event(
                    current_entries, args.built, args.round, blocker,
                )
                head = subprocess.run(
                    ["git", "-C", progress.project_root(), "rev-parse", "HEAD"],
                    capture_output=True, text=True,
                )
                if head.returncode != 0 or head.stdout.strip() != event["commit"]:
                    fail("the ordinary Correction escalation is not at its current accepted commit")
                account = {
                    "schema": 1,
                    "operation": operation,
                    "phase": "owner-only",
                    "event": event,
                    "final_map_marker_sha256": final_map_owner(
                        current_entries, blocker,
                    ),
                }
                publish_marker(account)

            while True:
                with marker_anchor() as anchor:
                    marker_payload = anchor.read_regular()
                    account = parse_marker_payload(marker_payload)
                    entries = progress.journal_entries()
                    artifact_payload, event, terminal = reproject_marker(
                        entries, account, args.built, args.round, operation,
                    )
                    validate_marker_recoveries(
                        entries, args.built, args.round, operation,
                    )
                    if account["phase"] == "owner-only":
                        published = publish_content_object(
                            WORKSPACE, args.built, artifact_payload, ".md",
                        )
                        if str(published.relative_to(WORKSPACE)) != event["artifact_object"]:
                            fail("the ordinary Correction escalation published another object")
                        replace_marker(
                            anchor, marker_payload,
                            {**account, "phase": "object-published"},
                        )
                        continue
                    if account["phase"] == "object-published":
                        progress.normalize_correction_round_escalated(
                            entries, event, "the ordinary Correction escalation",
                        )
                        replace_marker(
                            anchor, marker_payload,
                            {**account, "phase": "terminal-ready"},
                        )
                        continue
                    if terminal is None:
                        progress.normalize_correction_round_escalated(
                            entries, event, "the ordinary Correction escalation",
                        )
                        progress.cmd_note_with_lease(
                            note_args(event), lease, operation, owner_marker=MARKER_NAME,
                        )
                    entries = progress.journal_entries()
                    _payload, _event, terminal = reproject_marker(
                        entries, account, args.built, args.round, operation,
                    )
                    if terminal is None:
                        fail("the ordinary Correction escalation terminal is unavailable")
                    map_digest = account["final_map_marker_sha256"]
                    map_path = WORKSPACE / "final-checker-contract-map-in-progress"
                    if map_digest is not None and os.path.lexists(map_path):
                        with WorkspaceFileAnchor(
                            WORKSPACE, "final-checker-contract-map-in-progress",
                            "the superseded final-checker contract-map owner",
                        ) as map_anchor:
                            map_anchor.remove_exact(map_digest)
                    entries = progress.journal_entries()
                    reproject_marker(
                        entries, account, args.built, args.round, operation,
                    )
                    remove_marker(
                        anchor, marker_payload, entries,
                        args.built, args.round, operation,
                    )
                    print(f"CORRECTION ROUND ESCALATED {args.built} {args.round}")
                    return
    finally:
        if retained_anchor is not None:
            retained_anchor.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("built")
    parser.add_argument("round", type=int)
    parser.add_argument("blocker", nargs="?")
    args = parser.parse_args()
    args.retained = args.blocker is None
    if not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", args.built) \
            or isinstance(args.round, bool) or args.round < 1 \
            or args.blocker is not None and not re.fullmatch(
                r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", args.blocker,
            ):
        fail("the ordinary Correction escalation arguments are malformed")
    return args


def main():
    try:
        run(parse_args())
    except (OSError, ValueError) as exc:
        print(f"**correction escalation ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
