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


def session_records(entries, opening_index, mode, mandates, generation, product_generation=None):
    records = {}
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


def exact_product_identity(receipt, generation):
    receipt_data = data(receipt)
    opening_data = generation["opening"]
    mandate = receipt.get("mandate")
    if opening_data.get("schema") == 2:
        account = generation["accounts"].get(mandate)
        if any(receipt_data.get(key) != value for key, value in account.items()):
            fail("a PRODUCT REVIEW receipt changes its pass generation")
        identity = {**account, "report_sha256": receipt_data.get("report_sha256")}
        if not isinstance(identity["report_sha256"], str) or not identity["report_sha256"]:
            fail("a PRODUCT REVIEW receipt has malformed verifier identity")
        return identity
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
    if state == "unusable" and len(events) == 4:
        return "exhausted"
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
        identity = exact_product_identity(receipt, generation)
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
        elif verifier == "exhausted":
            continuations.append(f"{mandate}: finding verifier failed twice; report stable blocker")
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
