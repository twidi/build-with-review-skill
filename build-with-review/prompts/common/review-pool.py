#!/usr/bin/env python3
"""Read the exact current SPEC or PRODUCT REVIEW reviewer pool."""

import hashlib
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
JOURNAL = os.path.join(WORKSPACE, "progress.jsonl")

SPEC_MANDATES = {"enumerator", "ripple", "verifier", "feasibility", "judge", "scoped"}
PRODUCT_MANDATES = ("unlooked", "user", "meaning", "quality", "coverage")
TERMINAL_STATUSES = {"done", "failed", "cancelled", "superseded"}
UNUSABLE_RESULTS = {"error", "empty", "lost", "unusable"}
REOPEN_PREFIXES = (
    "malformed block returned",
    "malformed finding returned:",
    "report returned whole for recalibration",
)
CONTEXT_FIELDS = ("mode", "lot", "task", "attempt", "round", "mandate", "job")


def fail(message):
    print(f"review-pool ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def data(entry):
    value = entry.get("data")
    return value if isinstance(value, dict) else {}


def read_entries():
    if not os.path.isfile(JOURNAL) or os.path.islink(JOURNAL):
        fail("progress.jsonl is absent or aliased")
    entries = []
    with open(JOURNAL, "rb") as source:
        for number, raw in enumerate(source, 1):
            if not raw.endswith(b"\n"):
                fail(f"progress.jsonl line {number} is incomplete")
            try:
                entry = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                fail(f"progress.jsonl line {number} is unreadable: {exc}")
            if not isinstance(entry, dict):
                fail(f"progress.jsonl line {number} is not an object")
            entry["_journal_proof"] = (
                f"{number - 1}:{hashlib.sha256(raw[:-1]).hexdigest()}"
            )
            entries.append(entry)
    return entries


def exact_cap(entries):
    starts = [entry for entry in entries if entry.get("kind") == "run.started"]
    if len(starts) != 1:
        fail("the run has no one exact run.started event")
    cap = data(starts[0]).get("cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        fail("run.started has no positive reviewer cap")
    return cap


def pass_opening_stop_suffix(entries, start, before, built):
    opening = entries[start - 1]
    owner = opening.get("by")
    expected_context = {"mode": "product-review", "lot": built, "job": "controller"}
    state = {
        "phase": "active", "mode": None, "op": None, "pending": {},
        "terminal": None, "retirements": [], "report": None, "resumed": None,
    }

    def context(entry):
        return {key: entry[key] for key in CONTEXT_FIELDS if key in entry}

    def controller_event(entry):
        return entry.get("by") == owner and context(entry) == expected_context

    def active_sessions(at):
        starts = {}
        retired = set()
        for entry in entries[:at]:
            event, session = entry.get("event"), entry.get("session")
            if event == "session-started":
                if not isinstance(session, str) or not session or session in starts:
                    fail("the current PRODUCT REVIEW pass has malformed physical-session history")
                starts[session] = entry
            elif event == "session-retired" and session in starts:
                if session in retired:
                    fail("the current PRODUCT REVIEW pass has duplicate session retirement")
                retired.add(session)
        return {session: entry for session, entry in starts.items()
                if session not in retired}

    def exact_helper_stop(entry):
        entry_data = data(entry)
        return entry.get("event") == "note" \
            and entry.get("kind") in {"paused", "aborted"} \
            and controller_event(entry) \
            and set(entry_data) == {"sha", "op"} \
            and isinstance(entry_data["sha"], str) \
            and 40 <= len(entry_data["sha"]) <= 64 \
            and all(character in "0123456789abcdef" for character in entry_data["sha"]) \
            and isinstance(entry_data["op"], str) and len(entry_data["op"]) == 64 \
            and all(character in "0123456789abcdef" for character in entry_data["op"]) \
            and isinstance(entry.get("text"), str) and bool(entry["text"])

    def exact_retirement(entry, started):
        started_context = context(started)
        watchdog = started_context.get("job") == "watchdog"
        allowed_statuses = {"done"} if watchdog else {"done", "cancelled"}
        return entry.get("event") == "session-retired" \
            and entry.get("by") == owner and context(entry) == started_context \
            and entry.get("status") in allowed_statuses \
            and entry.get("archived") is True and entry.get("hidden") is True \
            and "kind" not in entry and "text" not in entry and "data" not in entry

    def exact_controller_report(entry):
        return entry.get("event") == "note" and entry.get("kind") == state["mode"] \
            and controller_event(entry) and "data" not in entry \
            and isinstance(entry.get("text"), str) and bool(entry["text"])

    def exact_resume(entry):
        return entry.get("event") == "note" and entry.get("kind") == "resumed" \
            and controller_event(entry) and "data" not in entry and "text" not in entry

    for index, entry in enumerate(entries[start:before], start):
        phase = state["phase"]
        if phase == "active" and exact_helper_stop(entry):
            pending = active_sessions(index)
            watchdogs = [session for session, started in pending.items()
                         if context(started).get("job") == "watchdog"]
            if len(watchdogs) != 1:
                fail("the current PRODUCT REVIEW pass has no one exact active watchdog")
            state = {
                "phase": "retirements" if pending else "controller-report",
                "mode": entry["kind"], "op": data(entry)["op"], "pending": pending,
                "terminal": entry["_journal_proof"], "retirements": [],
                "report": None, "resumed": None,
            }
        elif phase == "retirements":
            session = entry.get("session")
            started = state["pending"].get(session)
            if started is None or not exact_retirement(entry, started):
                fail("the current PRODUCT REVIEW pass has a foreign stop retirement")
            if context(started).get("job") == "watchdog" \
                    and any(context(candidate).get("job") != "watchdog"
                            for candidate in state["pending"].values()):
                fail("the current PRODUCT REVIEW pass retires its watchdog too early")
            state["pending"] = dict(state["pending"])
            state["pending"].pop(session)
            state["retirements"] = [*state["retirements"], entry["_journal_proof"]]
            if not state["pending"]:
                state["phase"] = "controller-report"
        elif phase == "controller-report" and exact_controller_report(entry):
            state["phase"] = "pause-reported" \
                if state["mode"] == "paused" else "aborted"
            state["report"] = entry["_journal_proof"]
        elif phase == "pause-reported" and exact_resume(entry):
            state["phase"] = "resumed"
            state["resumed"] = entry["_journal_proof"]
        else:
            fail("the current PRODUCT REVIEW pass has an event outside its stop-owned suffix")
    return state


def pass_opening_stop_account(state):
    if state["phase"] == "active":
        return None
    if state["phase"] != "resumed" or state["mode"] != "paused" \
            or state["pending"] or state["report"] is None or state["resumed"] is None:
        fail("the current PRODUCT REVIEW pass has no complete pause/resume recovery account")
    return {
        "mode": "paused", "op": state["op"], "terminal": state["terminal"],
        "retirements": state["retirements"], "report": state["report"],
        "resumed": state["resumed"],
    }


def current_generation(entries, mode):
    if mode == "spec":
        openings = [(index, entry) for index, entry in enumerate(entries)
                    if entry.get("kind") == "round.opened"]
        if not openings:
            fail("there is no current SPEC round")
        index, opening = openings[-1]
        opening_data = data(opening)
        round_number = opening_data.get("round")
        mandates = opening_data.get("mandates")
        if not isinstance(round_number, int) or isinstance(round_number, bool) \
                or round_number < 1 or not isinstance(mandates, list) or not mandates \
                or len(mandates) != len(set(mandates)) \
                or any(mandate not in SPEC_MANDATES for mandate in mandates):
            fail("the current SPEC round has a malformed assignment set")
        return index, tuple(mandates), {"round": round_number}, f"round-{round_number}"

    openings = [(index, entry) for index, entry in enumerate(entries)
                if entry.get("kind") == "pass.opened"]
    if not openings:
        fail("there is no current PRODUCT REVIEW pass")
    index, opening = openings[-1]
    if any(entry.get("kind") == "pass.closed" for entry in entries[index + 1:]):
        fail("the latest PRODUCT REVIEW pass is already closed")
    built = data(opening).get("built")
    if not isinstance(built, str) or not built:
        fail("the current PRODUCT REVIEW pass has no built lot")
    expected = {"mode": "product-review", "lot": built, "job": "controller"}
    context = {key: opening[key] for key in CONTEXT_FIELDS if key in opening}
    recoveries = [
        (candidate_index, candidate)
        for candidate_index, candidate in enumerate(entries[index + 1:], index + 1)
        if candidate.get("kind") == "pass.opening.context.recovered"
    ]
    if context == expected and recoveries:
        fail("the current PRODUCT REVIEW pass has an unexpected context recovery")
    if context != expected:
        legacy = {"mode": "construction", "lot": built, "job": "controller"}
        if context != legacy or not isinstance(opening.get("by"), str) or not opening["by"]:
            fail("the current PRODUCT REVIEW pass has no exact controller context")
        if len(recoveries) != 1:
            fail("the current PRODUCT REVIEW pass has no one exact context recovery")
        recovery_index, recovery = recoveries[0]
        stop_state = pass_opening_stop_suffix(entries, index + 1, recovery_index, built)
        if stop_state["phase"] not in {"active", "resumed"}:
            fail("the current PRODUCT REVIEW pass context recovery crosses a current run stop")
        expected_data = {
            "schema": 1,
            "opening": opening["_journal_proof"],
            "owner": opening["by"],
            "built": built,
            "commit": data(opening).get("commit"),
            "gate": data(opening).get("gate"),
            "from": legacy,
            "to": expected,
            "stop": pass_opening_stop_account(stop_state),
        }
        recovery_context = {key: recovery[key] for key in CONTEXT_FIELDS if key in recovery}
        if recovery.get("event") != "note" \
                or recovery.get("by") != opening["by"] \
                or data(recovery) != expected_data \
                or recovery_context != expected:
            fail("the current PRODUCT REVIEW pass has a malformed context recovery")
    return index, PRODUCT_MANDATES, {"lot": built}, built


def same_generation(entry, mode, generation):
    if entry.get("mode") != mode or entry.get("job") != "reviewer":
        return False
    return all(entry.get(key) == value for key, value in generation.items())


def session_records(entries, opening_index, mode, mandates, generation):
    records = {}
    for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1):
        if entry.get("event") != "session-started" \
                or not same_generation(entry, mode, generation):
            continue
        session = entry.get("session")
        mandate = entry.get("mandate")
        if not isinstance(session, str) or not session or mandate not in mandates:
            fail("a current reviewer session has malformed identity")
        if session in records:
            fail(f"reviewer session {session} has duplicate starts")
        records[session] = {
            "session": session,
            "mandate": mandate,
            "start": index,
            "retirement": None,
            "statuses": [],
        }

    for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1):
        if entry.get("event") not in {"session-status", "session-retired"}:
            continue
        record = records.get(entry.get("session"))
        if record is None:
            continue
        if not same_generation(entry, mode, generation) \
                or entry.get("mandate") != record["mandate"]:
            fail(f"reviewer session {record['session']} changes its pool identity")
        if entry.get("event") == "session-status":
            if record["retirement"] is not None:
                fail(f"reviewer session {record['session']} changes after retirement")
            record["statuses"].append((index, entry.get("status")))
            continue
        if record["retirement"] is not None:
            fail(f"reviewer session {record['session']} has duplicate retirements")
        status = entry.get("status")
        if status not in TERMINAL_STATUSES:
            fail(f"reviewer session {record['session']} has a non-terminal retirement")
        record["retirement"] = (index, status)
    return records


def active_for(records, mandate):
    return [record for record in records.values()
            if record["mandate"] == mandate and record["retirement"] is None]


def validate_replacement_order(records, mandates):
    for mandate in mandates:
        owners = sorted(
            (record for record in records.values() if record["mandate"] == mandate),
            key=lambda record: record["start"],
        )
        for prior, replacement in zip(owners, owners[1:]):
            retirement = prior["retirement"]
            if retirement is None or retirement[0] > replacement["start"]:
                fail(f"the {mandate} replacement starts before its prior owner retired")
            if retirement[1] == "done":
                fail(f"the {mandate} replacement follows a successfully retired owner")


def receipt_owner(records, mandate, receipt_index, *, forbid_later=True):
    candidates = []
    for record in records.values():
        if record["mandate"] != mandate or record["start"] >= receipt_index:
            continue
        retirement = record["retirement"]
        if retirement is None or retirement[0] > receipt_index:
            candidates.append(record)
    if len(candidates) != 1:
        fail(f"the {mandate} receipt has no one exact reviewer owner")
    if forbid_later:
        later = [record for record in records.values()
                 if record["mandate"] == mandate and record["start"] > receipt_index]
        if later:
            fail(f"the {mandate} receipt is followed by another reviewer owner")
    return candidates[0]


def exact_product_identity(receipt):
    receipt_data = data(receipt)
    identity = {key: receipt_data.get(key)
                for key in ("pass_commit", "pass_gate", "report_sha256")}
    if any(not isinstance(value, str) or not value for value in identity.values()):
        fail("a PRODUCT REVIEW receipt has malformed verifier identity")
    return identity


def product_verifier_state(entries, receipt_index, mandate, identity):
    events = [entry for entry in entries[receipt_index + 1:]
              if entry.get("kind") == "finding-verifier"
              and entry.get("mandate") == mandate
              and entry.get("event") in {"subagent-started", "subagent-ended"}]
    expecting = "start"
    state = "none"
    for entry in events:
        event = entry["event"]
        event_data = data(entry)
        if expecting == "start":
            if event != "subagent-started" or event_data != identity:
                fail(f"the {mandate} finding-verifier has a contradictory physical sequence")
            expecting = "end"
            state = "open"
            continue
        if event != "subagent-ended" \
                or any(event_data.get(key) != value for key, value in identity.items()):
            fail(f"the {mandate} finding-verifier changes its physical identity")
        if set(event_data) == set(identity) | {"unusable"} \
                and event_data.get("unusable") in UNUSABLE_RESULTS:
            expecting = "start"
            state = "unusable"
            continue
        result_keys = {"confirmed", "disproved", "malformed", "claims"}
        if set(event_data) != set(identity) | result_keys:
            fail(f"the {mandate} finding-verifier has a malformed terminal")
        malformed = event_data.get("malformed")
        if not isinstance(malformed, int) or isinstance(malformed, bool) or malformed < 0:
            fail(f"the {mandate} finding-verifier has a malformed result count")
        expecting = "complete"
        state = "complete-malformed" if malformed else "complete"
    return state


def spec_state(entries, opening_index, mandates, records, generation):
    for mandate in mandates:
        if len(active_for(records, mandate)) > 1:
            fail(f"duplicate active reviewer for {mandate}")
    validate_replacement_order(records, mandates)
    states = {}
    continuations = []
    for mandate in mandates:
        receipts = [(index, entry) for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1)
                    if entry.get("kind") == "report.received"
                    and entry.get("round") == generation["round"]
                    and entry.get("mandate") == mandate]
        if len(receipts) > 1:
            fail(f"the current {mandate} SPEC assignment has duplicate receipts")
        active = active_for(records, mandate)
        if len(active) > 1:
            fail(f"duplicate active reviewer for {mandate}")
        if not receipts:
            states[mandate] = "active" if active else "pending"
            continue
        receipt_index, _ = receipts[0]
        owner = receipt_owner(records, mandate, receipt_index)
        retirement = owner["retirement"]
        if retirement is None:
            states[mandate] = "active"
            continuations.append(f"{mandate}: receipt accepted; retire reviewer done")
        elif retirement[1] == "done":
            states[mandate] = "complete"
        else:
            fail(f"the accepted {mandate} SPEC report has a non-successful owner")
    return states, continuations, []


def product_state(entries, opening_index, mandates, records):
    for mandate in mandates:
        if len(active_for(records, mandate)) > 1:
            fail(f"duplicate active reviewer for {mandate}")
    validate_replacement_order(records, mandates)
    states = {}
    continuations = []
    unsettled = []
    for mandate in mandates:
        receipts = [(index, entry) for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1)
                    if entry.get("kind") == "report.received" and entry.get("mandate") == mandate]
        active = active_for(records, mandate)
        if len(active) > 1:
            fail(f"duplicate active reviewer for {mandate}")
        if not receipts:
            states[mandate] = "active" if active else "pending"
            continue

        receipt_index, receipt = receipts[-1]
        reopened = any(
            entry.get("kind") == "bound.spent" and entry.get("mandate") == mandate
            and isinstance(entry.get("text"), str)
            and entry["text"].startswith(REOPEN_PREFIXES)
            for entry in entries[receipt_index + 1:]
        )
        if reopened:
            states[mandate] = "active" if active else "pending"
            if active:
                continuations.append(f"{mandate}: wait for the replacement report")
            continue

        owner = receipt_owner(records, mandate, receipt_index, forbid_later=False)
        identity = exact_product_identity(receipt)
        verifier = product_verifier_state(entries, receipt_index, mandate, identity)
        retirement = owner["retirement"]
        if retirement is not None and retirement[1] != "done" and verifier != "complete":
            states[mandate] = "active" if active else "pending"
            if active:
                continuations.append(f"{mandate}: wait for the replacement report")
            continue
        if verifier == "complete":
            if retirement is None:
                states[mandate] = "active"
                continuations.append(f"{mandate}: settle verifier result and retire the lens")
            elif retirement[1] == "done":
                states[mandate] = "complete"
            else:
                fail(f"the settled {mandate} report has a non-successful owner")
            continue
        if verifier == "complete-malformed":
            if retirement is not None:
                fail(f"the {mandate} lens retired before its malformed claims settled")
            states[mandate] = "active"
            continuations.append(
                f"{mandate}: settle malformed verifier claims with the live lens; "
                "do not retire it yet"
            )
            continue
        if retirement is not None:
            fail(f"the {mandate} lens retired before its verifier settled")
        states[mandate] = "active"
        if verifier == "none":
            continuations.append(f"{mandate}: launch finding verifier")
        elif verifier == "unusable":
            continuations.append(f"{mandate}: regenerate finding verifier after unusable terminal")
        else:
            unsettled.append(f"{mandate}: finding verifier unsettled; physical subagent reconciliation required")
    return states, continuations, unsettled


def render(mode, generation_name, cap, mandates, states, continuations, unsettled):
    active = [mandate for mandate in mandates if states[mandate] == "active"]
    pending = [mandate for mandate in mandates if states[mandate] == "pending"]
    if len(active) > cap:
        fail(f"the current reviewer pool has {len(active)} active reviewers above cap {cap}")
    free = cap - len(active)
    launch = pending[:free]
    waiting = pending[free:]
    print("REVIEW POOL")
    print(f"mode: {mode}")
    print(f"generation: {generation_name}")
    print(f"cap: {cap}")
    print(f"active reviewers: {len(active)}")
    print(f"free slots: {free}")
    print(f"launch now: {', '.join(launch) if launch else 'none'}")
    print(f"waiting: {', '.join(waiting) if waiting else 'none'}")
    print()
    print("DURABLE CONTINUATIONS")
    if continuations:
        for line in continuations:
            print(line)
    else:
        print("none")
    print()
    print("UNSETTLED PROVIDER SUBAGENTS")
    if unsettled:
        for line in unsettled:
            print(line)
    else:
        print("none")
    print()
    print("AFTER REFILL")
    print('Launch every assignment from "launch now".')
    print("Then return to the exact report or verifier result that triggered this checkpoint.")
    print("Do not abandon that work because new sessions were launched.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"spec", "product-review"}:
        fail("usage: review-pool.py spec | product-review")
    mode = sys.argv[1]
    entries = read_entries()
    cap = exact_cap(entries)
    opening_index, mandates, generation, name = current_generation(entries, mode)
    records = session_records(entries, opening_index, mode, mandates, generation)
    if mode == "spec":
        states, continuations, unsettled = spec_state(
            entries, opening_index, mandates, records, generation,
        )
    else:
        states, continuations, unsettled = product_state(
            entries, opening_index, mandates, records,
        )
    render(mode, name, cap, mandates, states, continuations, unsettled)


if __name__ == "__main__":
    main()
