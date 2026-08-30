#!/usr/bin/env python3
"""Read the exact current SPEC or PRODUCT REVIEW reviewer pool."""

import hashlib
import json
import os
import subprocess
import sys

from correction_authority import product_pass_generation_account


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
PRODUCT_RETIREMENT_RECOVERY_KIND = "product.reviewer.retirement.recovered"
PRODUCT_RECEIPT_COUNT_KEYS = {"critical", "important", "minor", "decision"}
PRODUCT_RECEIPT_KEYS = PRODUCT_RECEIPT_COUNT_KEYS | {
    "pass_commit", "pass_gate", "report_sha256",
}


def fail(message):
    print(f"review-pool ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def data(entry):
    value = entry.get("data")
    return value if isinstance(value, dict) else {}


def context(entry):
    return {key: entry[key] for key in CONTEXT_FIELDS if key in entry}


def journal_proof(entry, subject):
    proof = entry.get("_journal_proof")
    if not isinstance(proof, str) or not proof:
        fail(f"{subject} has no exact journal proof")
    return proof


def read_entries():
    if not os.path.isfile(JOURNAL) or os.path.islink(JOURNAL):
        fail("progress.jsonl is absent or aliased")
    entries = []
    proofs = []
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
            proofs.append(f"{number - 1}:{hashlib.sha256(raw[:-1]).hexdigest()}")
    return entries, proofs


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


def current_generation(entries, proofs, mode):
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
        return index, tuple(mandates), {"round": round_number}, f"round-{round_number}", None

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
    opening_data = data(opening)
    product_generation = {
        "proof": proofs[index], "opening": opening_data, "accounts": {},
    }
    if opening_data.get("schema") == 2:
        progress = os.path.join(SCRIPT_DIR, "progress.py")
        if not os.path.isfile(progress) or os.path.islink(progress):
            fail("the current PRODUCT REVIEW pass has no real generation projector")
        for mandate in PRODUCT_MANDATES:
            projected = subprocess.run(
                [sys.executable, progress, "product-pass-generation", mandate],
                cwd=WORKSPACE, capture_output=True, text=True,
            )
            if projected.returncode != 0:
                fail(
                    f"the current PRODUCT REVIEW pass failed its {mandate} generation projection: "
                    f"{projected.stderr.strip() or projected.stdout.strip()}"
                )
            try:
                account = json.loads(projected.stdout)
                expected = product_pass_generation_account(proofs[index], opening_data, mandate)
            except (ValueError, json.JSONDecodeError) as exc:
                fail(f"the current PRODUCT REVIEW pass has malformed generation authority: {exc}")
            if account != expected:
                fail(f"the current PRODUCT REVIEW pass changes its {mandate} generation account")
            product_generation["accounts"][mandate] = account
        account = product_generation["accounts"]["unlooked"]
        name = f"{built}-c{account['position']}-p{account['pass']}"
    else:
        name = built
    return index, PRODUCT_MANDATES, {"lot": built}, name, product_generation


def same_generation(entry, mode, generation):
    if entry.get("mode") != mode or entry.get("job") != "reviewer":
        return False
    return all(entry.get(key) == value for key, value in generation.items())


def session_records(
        entries, opening_index, mode, mandates, generation, product_generation=None,
        *, allow_pending_recovery=False,
):
    records = {}
    generation_owner = entries[opening_index].get("by")
    for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1):
        if entry.get("event") != "session-started" \
                or not same_generation(entry, mode, generation):
            continue
        session = entry.get("session")
        mandate = entry.get("mandate")
        if not isinstance(session, str) or not session or mandate not in mandates:
            fail("a current reviewer session has malformed identity")
        if mode == "product-review":
            opening_data = product_generation["opening"]
            if opening_data.get("schema") == 2:
                account = product_generation["accounts"].get(mandate)
                if data(entry) != account:
                    fail(f"the {mandate} reviewer start changes its Product pass generation")
            elif data(entry):
                fail(f"the ordinary {mandate} reviewer start adds pass-generation authority")
            if entry.get("by") != generation_owner or context(entry) != {
                "mode": "product-review", "lot": generation["lot"],
                "mandate": mandate, "job": "reviewer",
            }:
                fail("a current Product reviewer start has no exact pass owner and context")
        if session in records:
            fail(f"reviewer session {session} has duplicate starts")
        records[session] = {
            "session": session,
            "mandate": mandate,
            "start": index,
            "retirement": None,
            "recovery": None,
            "statuses": [],
        }

    for index, entry in enumerate(entries[opening_index + 1:], opening_index + 1):
        if entry.get("event") == "note" \
                and entry.get("kind") == PRODUCT_RETIREMENT_RECOVERY_KIND:
            session = data(entry).get("session")
            record = records.get(session)
            if mode != "product-review" or record is None:
                fail("a Product reviewer retirement recovery has no exact session owner")
            validate_product_reviewer_retirement_recovery(
                entries, index, entry, opening_index, generation, record,
            )
            record["retirement"] = None
            record["recovery"] = index
            continue
        if entry.get("event") not in {"session-status", "session-retired"}:
            continue
        record = records.get(entry.get("session"))
        if record is None:
            continue
        if not same_generation(entry, mode, generation) \
                or entry.get("mandate") != record["mandate"]:
            fail(f"reviewer session {record['session']} changes its pool identity")
        if mode == "product-review" and (
            entry.get("by") != generation_owner
            or context(entry) != {
                "mode": "product-review", "lot": generation["lot"],
                "mandate": record["mandate"], "job": "reviewer",
            }
        ):
            fail(f"reviewer session {record['session']} changes its Product pass owner")
        if entry.get("event") == "session-status":
            if record["retirement"] is not None:
                has_later_recovery = mode == "product-review" and any(
                    candidate.get("event") == "note"
                    and candidate.get("kind") == PRODUCT_RETIREMENT_RECOVERY_KIND
                    and data(candidate).get("session") == record["session"]
                    for candidate in entries[index + 1:]
                )
                if mode != "product-review" \
                        or not allow_pending_recovery and not has_later_recovery:
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


def exact_product_identity(receipt, authority=None, built=None, mandate=None):
    receipt_data = data(receipt)
    product_generation = authority if isinstance(authority, dict) \
        and set(authority).issuperset({"opening", "accounts"}) else None
    opening = None if product_generation is not None else authority
    if product_generation is not None:
        opening_data = product_generation["opening"]
        mandate = receipt.get("mandate")
        account = product_generation["accounts"].get(mandate)
    else:
        opening_data = data(opening) if opening is not None else None
        account = product_pass_generation_account(
            journal_proof(opening, "the Product receipt opening"), opening_data, mandate,
        ) if opening_data is not None and opening_data.get("schema") == 2 else None
    if account is not None:
        if any(receipt_data.get(key) != value for key, value in account.items()):
            fail("a PRODUCT REVIEW receipt changes its pass generation")
        identity = {**account, "report_sha256": receipt_data.get("report_sha256")}
        if not isinstance(identity["report_sha256"], str) or not identity["report_sha256"]:
            fail("a PRODUCT REVIEW receipt has malformed verifier identity")
        return identity
    if opening is not None:
        expected_context = {
            "mode": "product-review", "lot": built,
            "mandate": mandate, "job": "controller",
        }
        if receipt.get("event") != "note" or receipt.get("kind") != "report.received" \
                or receipt.get("by") != opening.get("by") \
                or context(receipt) != expected_context \
                or set(receipt_data) != PRODUCT_RECEIPT_KEYS \
                or any(not isinstance(receipt_data.get(key), int)
                       or isinstance(receipt_data.get(key), bool) or receipt_data[key] < 0
                       for key in PRODUCT_RECEIPT_COUNT_KEYS) \
                or receipt_data.get("pass_commit") != opening_data.get("commit") \
                or receipt_data.get("pass_gate") != opening_data.get("gate") \
                or not isinstance(receipt_data.get("report_sha256"), str) \
                or len(receipt_data["report_sha256"]) != 64 \
                or any(character not in "0123456789abcdef"
                       for character in receipt_data["report_sha256"]):
            fail("a PRODUCT REVIEW receipt changes its exact pass authority")
    identity = {key: receipt_data.get(key)
                for key in ("pass_commit", "pass_gate", "report_sha256")}
    if any(not isinstance(value, str) or not value for value in identity.values()):
        fail("a PRODUCT REVIEW receipt has malformed verifier identity")
    return identity


def validate_product_verifier_terminal(event_data, identity, receipt_data, mandate):
    if set(event_data) == set(identity) | {"unusable"}:
        if event_data.get("unusable") not in UNUSABLE_RESULTS:
            fail(f"the {mandate} finding-verifier has an unknown unusable terminal")
        return "unusable"
    result_keys = {"confirmed", "disproved", "malformed", "claims"}
    if set(event_data) != set(identity) | result_keys:
        fail(f"the {mandate} finding-verifier has a malformed terminal")
    if any(not isinstance(event_data.get(key), int)
           or isinstance(event_data.get(key), bool) or event_data[key] < 0
           for key in ("confirmed", "disproved", "malformed")):
        fail(f"the {mandate} finding-verifier has malformed result counts")
    expected_count = sum(receipt_data.get(key, -1) for key in (
        "critical", "important", "minor", "decision",
    ))
    claims = event_data.get("claims")
    if expected_count < 0 or not isinstance(claims, list) \
            or len(claims) != expected_count:
        fail(f"the {mandate} finding-verifier lacks one result per accepted claim")
    totals = {"confirmed": 0, "disproved": 0, "malformed": 0}
    kinds = {"correction": 0, "decision": 0}
    actual_ids = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "kind", "verdict"} \
                or claim.get("kind") not in kinds or claim.get("verdict") not in totals:
            fail(f"the {mandate} finding-verifier has a malformed claim")
        actual_ids.append(claim["id"])
        kinds[claim["kind"]] += 1
        totals[claim["verdict"]] += 1
    if actual_ids != [f"F{ordinal}" for ordinal in range(1, expected_count + 1)] \
            or totals != {key: event_data[key] for key in totals} \
            or kinds["decision"] != receipt_data.get("decision") \
            or kinds["correction"] != expected_count - receipt_data.get("decision", -1):
        fail(f"the {mandate} finding-verifier result contradicts its accepted report")
    return "complete-malformed" if event_data["malformed"] else "complete"


def product_verifier_generation(
        entries, receipt_index, mandate, identity, receipt_data, *,
        before=None, owner=None, built=None,
):
    before = len(entries) if before is None else before
    events = [(index, entry) for index, entry in enumerate(
        entries[receipt_index + 1:before], receipt_index + 1,
    ) if entry.get("kind") == "finding-verifier"
        and entry.get("mandate") == mandate
        and entry.get("event") in {"subagent-started", "subagent-ended"}]
    expecting = "start"
    state = "none"
    opening = None
    terminal = None
    for index, entry in events:
        event = entry["event"]
        event_data = data(entry)
        if owner is not None and (
            entry.get("by") != owner
            or context(entry) != {
                "mode": "product-review", "lot": built,
                "mandate": mandate, "job": "controller",
            }
        ):
            fail(f"the {mandate} finding-verifier changes its pass controller")
        if expecting == "start":
            if event != "subagent-started" or event_data != identity:
                fail(f"the {mandate} finding-verifier has a contradictory physical sequence")
            expecting = "end"
            state = "open"
            opening = (index, entry)
            terminal = None
            continue
        if event != "subagent-ended" \
                or any(event_data.get(key) != value for key, value in identity.items()):
            fail(f"the {mandate} finding-verifier changes its physical identity")
        terminal_state = validate_product_verifier_terminal(
            event_data, identity, receipt_data, mandate,
        )
        if terminal_state == "unusable":
            expecting = "start"
            state = "unusable"
            terminal = (index, entry)
            continue
        expecting = "complete"
        state = terminal_state
        terminal = (index, entry)
    return {"state": state, "opening": opening, "terminal": terminal}


def product_verifier_state(entries, receipt_index, mandate, identity):
    return product_verifier_generation(
        entries, receipt_index, mandate, identity, data(entries[receipt_index]),
    )["state"]


def product_reviewer_receipts(entries, opening_index, mandate, *, before=None):
    before = len(entries) if before is None else before
    return [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1,
    ) if entry.get("kind") == "report.received" and entry.get("mandate") == mandate]


def journal_proof_index(proof, subject):
    try:
        index = int(proof.split(":", 1)[0])
    except (AttributeError, TypeError, ValueError):
        fail(f"{subject} has a malformed journal proof")
    if index < 0:
        fail(f"{subject} has a malformed journal proof")
    return index


def exact_malformed_return(entry, opening, built, mandate, session, claim_id):
    return entry.get("event") == "note" \
        and entry.get("kind") == "bound.spent" \
        and entry.get("by") == opening.get("by") \
        and context(entry) == {
            "mode": "product-review", "lot": built,
            "mandate": mandate, "job": "controller",
        } \
        and set(entry) - {"ts", "_journal_proof"} == {
            "by", "event", "kind", "text", "mode", "lot", "mandate", "job",
        } \
        and entry.get("text") == (
            f"malformed finding returned: {claim_id} - lens {session}"
        )


def product_reviewer_receipt_sequence(
        entries, opening_index, opening, built, mandate, records, *, before=None,
):
    before = len(entries) if before is None else before
    receipts = product_reviewer_receipts(
        entries, opening_index, mandate, before=before,
    )
    sequence = []
    final_closure = None
    for position, (receipt_index, receipt) in enumerate(receipts):
        owner = receipt_owner(records, mandate, receipt_index, forbid_later=False)
        identity = exact_product_identity(receipt, opening, built, mandate)
        next_receipt_index = (
            receipts[position + 1][0] if position + 1 < len(receipts) else before
        )
        verifier = product_verifier_generation(
            entries, receipt_index, mandate, identity, data(receipt),
            before=next_receipt_index, owner=opening.get("by"), built=built,
        )
        item = {
            "index": receipt_index, "entry": receipt, "owner": owner,
            "identity": identity, "verifier": verifier,
        }
        sequence.append(item)
        if position == 0:
            continue
        if final_closure is not None:
            fail(f"the {mandate} report continues after its final malformed closure")
        previous = sequence[position - 1]
        if item["owner"]["session"] != previous["owner"]["session"]:
            continue
        previous_verifier = previous["verifier"]
        if previous_verifier["state"] != "complete-malformed" \
                or previous_verifier["terminal"] is None:
            fail(f"the {mandate} report replacement has no exact malformed verifier")
        malformed_claims = [
            claim for claim in data(previous_verifier["terminal"][1])["claims"]
            if claim["verdict"] == "malformed"
        ]
        transition_returns = [
            (index, entry) for index, entry in enumerate(
                entries[previous_verifier["terminal"][0] + 1:receipt_index],
                previous_verifier["terminal"][0] + 1,
            )
            if entry.get("kind") == "bound.spent"
            and entry.get("mandate") == mandate
            and isinstance(entry.get("text"), str)
            and entry["text"].startswith("malformed finding returned:")
        ]
        session_returns = [
            entry for entry in entries[opening_index + 1:receipt_index]
            if entry.get("kind") == "bound.spent"
            and entry.get("mandate") == mandate
            and isinstance(entry.get("text"), str)
            and entry["text"].startswith("malformed finding returned:")
            and entry["text"].endswith(f" - lens {item['owner']['session']}")
        ]
        complete_returns = len(transition_returns) == len(malformed_claims) \
            and all(
                exact_malformed_return(
                    returned[1], opening, built, mandate,
                    previous["owner"]["session"], claim["id"],
                )
                for returned, claim in zip(transition_returns, malformed_claims)
            )
        if transition_returns and complete_returns \
                and len(session_returns) == len(transition_returns):
            continue
        recovery_settlement = set()
        recovery_index = item["owner"].get("recovery")
        if recovery_index is not None:
            recovery_settlement.update(
                journal_proof_index(
                    proof, f"the {mandate} final receipt's settlement recovery",
                ) for proof in data(entries[recovery_index]).get("settlement", [])
            )
        recovered_final_returns = position >= 2 and complete_returns \
            and all(index in recovery_settlement for index, entry in transition_returns)
        if transition_returns and not recovered_final_returns:
            fail(f"the {mandate} report replacement has no complete malformed return set")
        if position < 2:
            fail(f"the {mandate} report replacement has no exact malformed return")
        returned = sequence[position - 2]
        returned_verifier = returned["verifier"]
        restated = previous
        restated_verifier = restated["verifier"]
        if returned_verifier["state"] != "complete-malformed" \
                or returned_verifier["terminal"] is None \
                or restated_verifier["state"] != "complete-malformed" \
                or restated_verifier["terminal"] is None:
            fail(f"the {mandate} final receipt has no two exact malformed generations")
        malformed_returned = [
            claim for claim in data(returned_verifier["terminal"][1])["claims"]
            if claim["verdict"] == "malformed"
        ]
        returned_spends = [
            (index, entry) for index, entry in enumerate(
                entries[returned_verifier["terminal"][0] + 1:restated["index"]],
                returned_verifier["terminal"][0] + 1,
            )
            if entry.get("kind") == "bound.spent"
            and entry.get("mandate") == mandate
            and isinstance(entry.get("text"), str)
            and entry["text"].startswith("malformed finding returned:")
        ]
        if len(returned_spends) != len(malformed_returned) or not all(
                exact_malformed_return(
                    spend[1], opening, built, mandate,
                    returned["owner"]["session"], claim["id"],
                ) and returned_verifier["terminal"][0] < spend[0] < restated["index"]
                for spend, claim in zip(returned_spends, malformed_returned)
        ) or len([
                    candidate for candidate in receipts
                    if returned_verifier["terminal"][0] < candidate[0] <= restated["index"]
                ]) != 1:
            fail(f"the {mandate} final receipt has no exact prior malformed return")
        if len({
            returned["owner"]["session"], restated["owner"]["session"],
            item["owner"]["session"],
        }) != 1:
            fail(f"the {mandate} final receipt changes its reviewer generation")
        old_total = sum(data(restated["entry"])[key] for key in PRODUCT_RECEIPT_COUNT_KEYS)
        new_total = sum(data(receipt)[key] for key in PRODUCT_RECEIPT_COUNT_KEYS)
        malformed_count = data(restated_verifier["terminal"][1])["malformed"]
        if new_total != old_total - malformed_count:
            fail(f"the {mandate} final receipt changes more than its malformed claims")

        allowed_recovery = set()
        recovery_index = item["owner"].get("recovery")
        if recovery_index is not None:
            recovery_data = data(entries[recovery_index])
            allowed_recovery.add(recovery_index)
            allowed_recovery.add(journal_proof_index(
                recovery_data.get("retirement"),
                f"the {mandate} final receipt's retirement recovery",
            ))
            allowed_recovery.update(
                journal_proof_index(
                    proof, f"the {mandate} final receipt's settlement recovery",
                ) for proof in recovery_data.get("settlement", [])
            )
        suffix_start = restated_verifier["terminal"][0] + 1
        for index, entry in enumerate(entries[suffix_start:receipt_index], suffix_start):
            if index in allowed_recovery:
                continue
            event = entry.get("event")
            kind = entry.get("kind")
            same_mandate = entry.get("mandate") == mandate
            same_session = entry.get("session") == item["owner"]["session"]
            replacement = event == "session-started" \
                and same_generation(entry, "product-review", {"lot": built}) \
                and same_mandate
            pass_terminal = kind == "pass.closed"
            amendment = kind == "amendment.opened" \
                and data(entry).get("origin") == "product-review"
            whole_run_cleanup = kind == "cleanup.started" \
                and data(entry).get("scope") == "whole-run"
            stop = kind in {"paused", "aborted"} \
                and entry.get("by") == opening.get("by") \
                and context(entry) == {
                    "mode": "product-review", "lot": built, "job": "controller",
                }
            if same_mandate or same_session or replacement or pass_terminal \
                    or amendment or whole_run_cleanup or stop:
                fail(f"the {mandate} final receipt crosses a competing pass event")
        final_closure = receipt_index
    return {"receipts": sequence, "final_closure": final_closure}


def validate_product_malformed_return(
        entries, opening_index, opening, built, mandate, records, candidate,
):
    sequence = product_reviewer_receipt_sequence(
        entries, opening_index, opening, built, mandate, records,
    )
    if not sequence["receipts"] or sequence["final_closure"] is not None:
        fail(f"the {mandate} malformed return has no current report generation")
    latest = sequence["receipts"][-1]
    verifier = latest["verifier"]
    if verifier["state"] != "complete-malformed" or verifier["terminal"] is None:
        fail(f"the {mandate} malformed return has no exact malformed verifier")
    malformed = [
        claim for claim in data(verifier["terminal"][1])["claims"]
        if claim["verdict"] == "malformed"
    ]
    session = latest["owner"]["session"]
    prior = [
        (index, entry) for index, entry in enumerate(
            entries[opening_index + 1:], opening_index + 1,
        )
        if entry.get("kind") == "bound.spent" and entry.get("mandate") == mandate
        and isinstance(entry.get("text"), str)
        and entry["text"].startswith("malformed finding returned:")
        and entry["text"].endswith(f" - lens {session}")
    ]
    terminal_index = verifier["terminal"][0]
    if any(index <= terminal_index for index, entry in prior):
        fail(f"the {mandate} reviewer generation already spent its malformed return")
    if len(prior) >= len(malformed) or any(
        not exact_malformed_return(
            entry, opening, built, mandate, session, malformed[position]["id"],
        ) for position, (_, entry) in enumerate(prior)
    ) or not exact_malformed_return(
        candidate, opening, built, mandate, session, malformed[len(prior)]["id"],
    ):
        fail(f"the {mandate} malformed return changes its exact claim or lens")


def product_reviewer_generation(entries, session):
    opening_index, mandates, generation, built = current_generation(entries, "product-review")
    opening = entries[opening_index]
    records = session_records(entries, opening_index, "product-review", mandates, generation)
    record = records.get(session)
    if record is None:
        fail("the Product reviewer generation has no exact session start")
    mandate = record["mandate"]
    receipt_index = receipt = identity = verifier = None
    sequence = product_reviewer_receipt_sequence(
        entries, opening_index, opening, built, mandate, records,
    )
    if sequence["receipts"]:
        latest = sequence["receipts"][-1]
        receipt_index, receipt = latest["index"], latest["entry"]
        if latest["owner"]["session"] != session:
            fail("the Product reviewer generation receipt belongs to another session")
        identity, verifier = latest["identity"], latest["verifier"]
    return {
        "opening_index": opening_index,
        "opening": opening,
        "built": built,
        "owner": opening.get("by"),
        "controller_context": context(opening),
        "record": record,
        "receipt_index": receipt_index,
        "receipt": receipt,
        "identity": identity,
        "verifier": verifier,
    }


def product_reviewer_settlement_suffix(
        entries, start, before, opening, generation, record, verifier, subject,
):
    mandate = record["mandate"]
    session = record["session"]
    owner = opening.get("by")
    reviewer_context = {
        "mode": "product-review", "lot": generation["lot"],
        "mandate": mandate, "job": "reviewer",
    }
    controller_context = {
        "mode": "product-review", "lot": generation["lot"],
        "mandate": mandate, "job": "controller",
    }
    malformed_ids = [
        claim["id"] for claim in data(verifier["terminal"][1])["claims"]
        if claim["verdict"] == "malformed"
    ]
    proofs = []
    spend_count = 0
    working_seen = False
    for index, entry in enumerate(entries[start:before], start):
        event = entry.get("event")
        kind = entry.get("kind")
        same_mandate = entry.get("mandate") == mandate
        same_session = entry.get("session") == session
        if kind == "bound.spent" and same_mandate:
            expected_text = (
                f"malformed finding returned: {malformed_ids[spend_count]} - lens {session}"
                if spend_count < len(malformed_ids) else None
            )
            if working_seen or entry.get("event") != "note" \
                    or entry.get("by") != owner or context(entry) != controller_context \
                    or set(entry) - {"ts", "_journal_proof"} != {
                        "by", "event", "kind", "text", "mode", "lot", "mandate", "job",
                    } or entry.get("text") != expected_text:
                fail(f"{subject} has a foreign malformed-finding settlement")
            proofs.append(journal_proof(entry, subject))
            spend_count += 1
            continue
        if event == "session-status" and same_session:
            if working_seen or entry.get("status") != "working" \
                    or entry.get("by") != owner or context(entry) != reviewer_context \
                    or set(entry) - {"ts", "_journal_proof"} != {
                        "by", "event", "session", "status", "mode", "lot", "mandate", "job",
                    } or spend_count not in {0, len(malformed_ids)}:
                fail(f"{subject} has a foreign post-retirement reviewer status")
            proofs.append(journal_proof(entry, subject))
            working_seen = True
            continue
        replacement = event == "session-started" and same_generation(
            entry, "product-review", generation,
        ) and same_mandate
        closes_pass = kind == "pass.closed"
        opens_amendment = kind == "amendment.opened" \
            and data(entry).get("origin") == "product-review"
        whole_run_cleanup = kind == "cleanup.started" \
            and data(entry).get("scope") == "whole-run"
        stops_run = kind in {"paused", "aborted"} \
            and entry.get("by") == owner \
            and context(entry) == {
                "mode": "product-review", "lot": generation["lot"], "job": "controller",
            }
        if same_session or same_mandate or replacement or closes_pass \
                or opens_amendment or whole_run_cleanup or stops_run:
            fail(f"{subject} crosses a later event for the same reviewer generation")
    if spend_count not in {0, len(malformed_ids)}:
        fail(f"{subject} has an incomplete malformed-finding settlement")
    return {"proofs": proofs, "reopened": spend_count > 0}


def product_reviewer_recovery_account(
        entries, before, opening_index, generation, record, subject,
):
    opening = entries[opening_index]
    retirement = record.get("retirement")
    if retirement is None or record.get("recovery") is not None:
        fail(f"{subject} has no one mistaken retirement")
    retirement_index, status = retirement
    retirement_entry = entries[retirement_index]
    mandate = record["mandate"]
    reviewer_context = {
        "mode": "product-review", "lot": generation["lot"],
        "mandate": mandate, "job": "reviewer",
    }
    if status != "done" or retirement_entry.get("archived") is not True \
            or retirement_entry.get("hidden") is not True \
            or retirement_entry.get("by") != opening.get("by") \
            or context(retirement_entry) != reviewer_context:
        fail(f"{subject} does not select one exact done/archive/hide retirement")

    receipts = product_reviewer_receipts(entries, opening_index, mandate, before=before)
    if not receipts:
        fail(f"{subject} has no accepted report receipt")
    receipt_index, receipt = receipts[-1]
    if not (record["start"] < receipt_index < retirement_index < before):
        fail(f"{subject} has an unordered reviewer generation")
    identity = exact_product_identity(
        receipt, opening, generation["lot"], mandate,
    )
    verifier = product_verifier_generation(
        entries, receipt_index, mandate, identity, data(receipt), before=retirement_index,
        owner=opening.get("by"), built=generation["lot"],
    )
    if verifier["state"] != "complete-malformed" \
            or verifier["opening"] is None or verifier["terminal"] is None \
            or verifier["terminal"][0] >= retirement_index:
        fail(f"{subject} has no exact complete-malformed verifier call")

    settlement = product_reviewer_settlement_suffix(
        entries, retirement_index + 1, before, opening, generation, record,
        verifier, subject,
    )

    report_sha256 = identity["report_sha256"]

    verifier_opening_index, verifier_opening = verifier["opening"]
    verifier_terminal_index, verifier_terminal = verifier["terminal"]
    return {
        "schema": 1,
        "pass_opening": journal_proof(opening, subject),
        "owner": opening.get("by"),
        "controller_context": context(opening),
        "session_start": journal_proof(entries[record["start"]], subject),
        "session": record["session"],
        "mandate": mandate,
        "receipt": journal_proof(receipt, subject),
        "report_sha256": report_sha256,
        "verifier_opening": journal_proof(verifier_opening, subject),
        "verifier_terminal": journal_proof(verifier_terminal, subject),
        "retirement": journal_proof(retirement_entry, subject),
        "settlement": settlement["proofs"],
    }


def validate_product_reviewer_retirement_recovery(
        entries, index, entry, opening_index, generation, record,
):
    subject = "the Product reviewer retirement recovery"
    expected = product_reviewer_recovery_account(
        entries, index, opening_index, generation, record, subject,
    )
    expected_context = {
        "mode": "product-review", "lot": generation["lot"], "job": "controller",
    }
    if entry.get("event") != "note" \
            or entry.get("kind") != PRODUCT_RETIREMENT_RECOVERY_KIND \
            or entry.get("by") != expected["owner"] \
            or context(entry) != expected_context \
            or data(entry) != expected:
        fail(f"{subject} changes its exact authority")


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


def product_state(entries, opening_index, mandates, records, generation):
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
        reviewer_generation = product_reviewer_generation(entries, owner["session"])
        if reviewer_generation["receipt_index"] != receipt_index \
                or reviewer_generation["receipt"] is not receipt:
            fail(f"the {mandate} reviewer projector selected another report generation")
        verifier = reviewer_generation["verifier"]["state"]
        retirement = reviewer_generation["record"]["retirement"]
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
    entries, proofs = read_entries()
    cap = exact_cap(entries)
    opening_index, mandates, generation, name, product_generation = current_generation(
        entries, proofs, mode,
    )
    records = session_records(
        entries, opening_index, mode, mandates, generation, product_generation,
    )
    if mode == "spec":
        states, continuations, unsettled = spec_state(
            entries, opening_index, mandates, records, generation,
        )
    else:
        states, continuations, unsettled = product_state(
            entries, opening_index, mandates, records, product_generation,
        )
    render(mode, name, cap, mandates, states, continuations, unsettled)


if __name__ == "__main__":
    main()
