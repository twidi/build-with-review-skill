#!/usr/bin/env python3
"""Focused behavior tests for the read-only review pool helper."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "prompts" / "common" / "review-pool.py"
CORRECTION_AUTHORITY_SOURCE = HERE / "prompts" / "common" / "correction_authority.py"
FINAL_CHECKER_SOURCE = HERE / "prompts" / "common" / "final_checker_obligations.py"


class ReviewPoolTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.common = self.workspace / "prompts" / "common"
        self.common.mkdir(parents=True)
        self.script = self.common / "review-pool.py"
        if SOURCE.exists():
            shutil.copyfile(SOURCE, self.script)
        if CORRECTION_AUTHORITY_SOURCE.exists():
            shutil.copyfile(CORRECTION_AUTHORITY_SOURCE, self.common / "correction_authority.py")
        if FINAL_CHECKER_SOURCE.exists():
            shutil.copyfile(FINAL_CHECKER_SOURCE, self.common / "final_checker_obligations.py")
        self.entries = [
            {"event": "note", "kind": "run.started", "data": {"cap": 3}},
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def append(self, *entries):
        self.entries.extend(entries)

    def write(self):
        with open(self.workspace / "progress.jsonl", "w", encoding="utf-8") as target:
            for entry in self.entries:
                target.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def run_helper(self, mode):
        self.write()
        return subprocess.run(
            [sys.executable, self.script, mode],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @staticmethod
    def started(session, mode, mandate, *, round_number=None, job="reviewer", lot=None):
        entry = {
            "event": "session-started",
            "session": session,
            "job": job,
            "mode": mode,
            "mandate": mandate,
        }
        if round_number is not None:
            entry["round"] = round_number
        if lot is not None:
            entry["lot"] = lot
        if mode == "product-review":
            entry["by"] = "product-controller"
        return entry

    @staticmethod
    def status(session, mode, mandate, status, *, round_number=None, job="reviewer", lot=None):
        entry = ReviewPoolTest.started(
            session, mode, mandate, round_number=round_number, job=job, lot=lot,
        )
        entry["event"] = "session-status"
        entry["status"] = status
        return entry

    @staticmethod
    def retired(session, mode, mandate, status="done", *, round_number=None, job="reviewer", lot=None):
        entry = ReviewPoolTest.status(
            session, mode, mandate, status, round_number=round_number, job=job, lot=lot,
        )
        entry["event"] = "session-retired"
        return entry

    @staticmethod
    def product_receipt(mandate, report_sha):
        return {
            "event": "note",
            "kind": "report.received",
            "by": "product-controller",
            "mode": "product-review",
            "lot": "lot-1",
            "job": "controller",
            "mandate": mandate,
            "data": {
                "critical": 0,
                "important": 0,
                "minor": 0,
                "decision": 0,
                "pass_commit": "c" * 40,
                "pass_gate": "g" * 64,
                "report_sha256": report_sha,
            },
        }

    @staticmethod
    def verifier_started(mandate, report_sha):
        return {
            "event": "subagent-started",
            "kind": "finding-verifier",
            "by": "product-controller",
            "mode": "product-review",
            "lot": "lot-1",
            "job": "controller",
            "mandate": mandate,
            "data": {
                "pass_commit": "c" * 40,
                "pass_gate": "g" * 64,
                "report_sha256": report_sha,
            },
        }

    @staticmethod
    def verifier_ended(mandate, report_sha):
        entry = ReviewPoolTest.verifier_started(mandate, report_sha)
        entry["event"] = "subagent-ended"
        entry["data"].update({
            "confirmed": 0, "disproved": 0, "malformed": 0, "claims": [],
        })
        return entry

    @staticmethod
    def verifier_unusable(mandate, report_sha, reason):
        entry = ReviewPoolTest.verifier_started(mandate, report_sha)
        entry["event"] = "subagent-ended"
        entry["data"]["unusable"] = reason
        return entry

    @staticmethod
    def verifier_malformed(mandate, report_sha):
        entry = ReviewPoolTest.verifier_started(mandate, report_sha)
        entry["event"] = "subagent-ended"
        entry["data"].update({
            "confirmed": 0,
            "disproved": 0,
            "malformed": 1,
            "claims": [{"id": "F1", "kind": "correction", "verdict": "malformed"}],
        })
        return entry

    def open_spec_round(self):
        self.append({
            "event": "note",
            "kind": "round.opened",
            "data": {
                "round": 1,
                "kind": "full",
                "mandates": ["enumerator", "verifier", "feasibility", "judge"],
            },
        })

    def open_product_pass(self):
        self.append({
            "event": "note",
            "kind": "pass.opened",
            "by": "product-controller",
            "mode": "product-review",
            "lot": "lot-1",
            "job": "controller",
            "data": {"built": "lot-1", "commit": "c" * 40, "gate": "g" * 64},
        })

    def test_product_pass_requires_exact_context_or_one_stop_safe_recovery(self):
        child = {
            "event": "session-started", "session": "lens",
            "mode": "product-review", "lot": "lot-1",
            "mandate": "unlooked", "job": "reviewer",
        }
        watchdog = {
            "event": "session-started", "session": "watchdog", "job": "watchdog",
        }
        self.append(child, watchdog)
        opening = {
            "event": "note",
            "kind": "pass.opened",
            "by": "product-controller",
            "mode": "construction",
            "lot": "lot-1",
            "job": "controller",
            "data": {"built": "lot-1", "commit": "c" * 40, "gate": "g" * 64},
        }
        self.append(opening)
        refused = self.run_helper("product-review")
        self.assertNotEqual(refused.returncode, 0)

        def proof(index, entry):
            raw = json.dumps(entry, separators=(",", ":")).encode()
            return f"{index}:{hashlib.sha256(raw).hexdigest()}"

        opening_proof = proof(3, opening)
        helper_stop = {
            "event": "note", "kind": "paused", "by": "product-controller",
            "mode": "product-review", "lot": "lot-1", "job": "controller",
            "text": "nothing in flight", "data": {"sha": "c" * 40, "op": "d" * 64},
        }
        child_retirement = {
            "event": "session-retired", "session": "lens", "by": "product-controller",
            "mode": "product-review", "lot": "lot-1",
            "mandate": "unlooked", "job": "reviewer",
            "status": "cancelled", "archived": True, "hidden": True,
        }
        watchdog_retirement = {
            "event": "session-retired", "session": "watchdog", "by": "product-controller",
            "job": "watchdog", "status": "done", "archived": True, "hidden": True,
        }
        controller_stop = {
            "event": "note", "kind": "paused", "by": "product-controller",
            "mode": "product-review", "lot": "lot-1", "job": "controller",
            "text": "The Product Review run is paused.",
        }
        resumed = {
            "event": "note", "kind": "resumed", "by": "product-controller",
            "mode": "product-review", "lot": "lot-1", "job": "controller",
        }
        self.append(
            helper_stop, child_retirement, watchdog_retirement, controller_stop, resumed,
        )
        self.append({
            "event": "note",
            "kind": "pass.opening.context.recovered",
            "by": "product-controller",
            "mode": "product-review",
            "lot": "lot-1",
            "job": "controller",
            "data": {
                "schema": 1,
                "opening": opening_proof,
                "owner": "product-controller",
                "built": "lot-1",
                "commit": "c" * 40,
                "gate": "g" * 64,
                "from": {"mode": "construction", "lot": "lot-1", "job": "controller"},
                "to": {"mode": "product-review", "lot": "lot-1", "job": "controller"},
                "stop": {
                    "mode": "paused", "op": "d" * 64,
                    "terminal": proof(4, helper_stop),
                    "retirements": [
                        proof(5, child_retirement), proof(6, watchdog_retirement),
                    ],
                    "report": proof(7, controller_stop),
                    "resumed": proof(8, resumed),
                },
            },
        })
        recovered = self.run_helper("product-review")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)

        self.entries[-1]["data"]["opening"] = "0:" + "f" * 64
        changed = self.run_helper("product-review")
        self.assertNotEqual(changed.returncode, 0)

        self.entries[-1]["data"]["opening"] = opening_proof
        self.entries[8]["kind"] = "aborted"
        aborted = self.run_helper("product-review")
        self.assertNotEqual(aborted.returncode, 0)

    def test_spec_refill_excludes_fixer_and_unrelated_sessions(self):
        self.open_spec_round()
        self.append(
            self.started("enum", "spec", "enumerator", round_number=1),
            self.started("verify", "spec", "verifier", round_number=1),
            self.started("feasible", "spec", "feasibility", round_number=1),
            self.started("fixer", "spec", "fixer", round_number=1, job="fixer"),
            self.started("old", "spec", "judge", round_number=2),
            {
                "event": "note",
                "kind": "report.received",
                "round": 1,
                "mandate": "verifier",
                "data": {"critical": 0, "important": 0, "minor": 0, "decision": 0},
            },
            self.retired("verify", "spec", "verifier", round_number=1),
        )

        result = self.run_helper("spec")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active reviewers: 2", result.stdout)
        self.assertIn("free slots: 1", result.stdout)
        self.assertIn("launch now: judge", result.stdout)
        self.assertNotIn("fixer", result.stdout)

    def test_spec_replacement_requires_prior_non_successful_retirement(self):
        self.open_spec_round()
        self.append(
            self.started("enum-old", "spec", "enumerator", round_number=1),
            self.retired("enum-old", "spec", "enumerator", "failed", round_number=1),
            self.started("enum-new", "spec", "enumerator", round_number=1),
        )

        valid = self.run_helper("spec")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertIn("active reviewers: 1", valid.stdout)

    def test_spec_replacement_before_retirement_fails_closed(self):
        self.open_spec_round()
        self.append(
            self.started("enum-old", "spec", "enumerator", round_number=1),
            self.started("enum-new", "spec", "enumerator", round_number=1),
            self.retired("enum-old", "spec", "enumerator", "failed", round_number=1),
        )

        result = self.run_helper("spec")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("replacement starts before its prior owner retired", result.stdout + result.stderr)

    def test_product_refill_survives_an_incoming_second_report(self):
        self.open_product_pass()
        user_sha = "1" * 64
        unlooked_sha = "2" * 64
        self.append(
            self.started("unlooked", "product-review", "unlooked", lot="lot-1"),
            self.started("user", "product-review", "user", lot="lot-1"),
            self.started("meaning", "product-review", "meaning", lot="lot-1"),
            self.status("user", "product-review", "user", "idle", lot="lot-1"),
            self.product_receipt("user", user_sha),
            self.verifier_started("user", user_sha),
            self.verifier_ended("user", user_sha),
            self.retired("user", "product-review", "user", lot="lot-1"),
            self.product_receipt("unlooked", unlooked_sha),
        )

        result = self.run_helper("product-review")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active reviewers: 2", result.stdout)
        self.assertIn("free slots: 1", result.stdout)
        self.assertIn("launch now: quality", result.stdout)
        self.assertIn("unlooked: launch finding verifier", result.stdout)
        self.assertIn("return to the exact report or verifier result", result.stdout)

    def test_idle_product_lens_keeps_its_slot_and_open_verifier_requires_reconciliation(self):
        self.open_product_pass()
        report_sha = "3" * 64
        self.append(
            self.started("unlooked", "product-review", "unlooked", lot="lot-1"),
            self.started("user", "product-review", "user", lot="lot-1"),
            self.started("meaning", "product-review", "meaning", lot="lot-1"),
            self.status("meaning", "product-review", "meaning", "idle", lot="lot-1"),
            self.product_receipt("meaning", report_sha),
            self.verifier_started("meaning", report_sha),
        )

        result = self.run_helper("product-review")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active reviewers: 3", result.stdout)
        self.assertIn("free slots: 0", result.stdout)
        self.assertIn("launch now: none", result.stdout)
        self.assertIn("meaning: finding verifier unsettled", result.stdout)
        self.assertIn("physical subagent reconciliation required", result.stdout)

    def test_duplicate_active_owner_fails_closed(self):
        self.open_product_pass()
        self.append(
            self.started("user-1", "product-review", "user", lot="lot-1"),
            self.started("user-2", "product-review", "user", lot="lot-1"),
        )

        result = self.run_helper("product-review")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate active reviewer", result.stdout + result.stderr)

    def test_every_unusable_verifier_reports_exact_regeneration(self):
        self.open_product_pass()
        report_sha = "4" * 64
        self.append(
            self.started("user", "product-review", "user", lot="lot-1"),
            self.product_receipt("user", report_sha),
            self.verifier_started("user", report_sha),
            self.verifier_unusable("user", report_sha, "error"),
        )
        once = self.run_helper("product-review")
        self.assertEqual(once.returncode, 0, once.stdout + once.stderr)
        self.assertIn("user: regenerate finding verifier after unusable terminal", once.stdout)

        self.append(
            self.verifier_started("user", report_sha),
            self.verifier_unusable("user", report_sha, "lost"),
        )
        twice = self.run_helper("product-review")
        self.assertEqual(twice.returncode, 0, twice.stdout + twice.stderr)
        self.assertIn("user: regenerate finding verifier after unusable terminal", twice.stdout)

        self.append(
            self.verifier_started("user", report_sha),
            self.verifier_unusable("user", report_sha, "empty"),
        )
        three = self.run_helper("product-review")
        self.assertEqual(three.returncode, 0, three.stdout + three.stderr)
        self.assertIn("user: regenerate finding verifier after unusable terminal", three.stdout)

    def test_positive_malformed_result_keeps_lens_for_settlement(self):
        self.open_product_pass()
        report_sha = "5" * 64
        receipt = self.product_receipt("meaning", report_sha)
        receipt["data"]["minor"] = 1
        self.append(
            self.started("meaning", "product-review", "meaning", lot="lot-1"),
            self.status("meaning", "product-review", "meaning", "idle", lot="lot-1"),
            receipt,
            self.verifier_started("meaning", report_sha),
            self.verifier_malformed("meaning", report_sha),
        )

        result = self.run_helper("product-review")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("meaning: settle malformed verifier claims with the live lens", result.stdout)
        self.assertNotIn("meaning: settle verifier result and retire the lens", result.stdout)
        self.assertIn("active reviewers: 1", result.stdout)

    def test_malformed_retirement_recovery_reopens_the_same_lens_generation(self):
        self.open_product_pass()
        report = self.workspace / "reports" / "product-review" / "lot-1" / "lot-1-meaning.md"
        report.parent.mkdir(parents=True)
        report.write_text("accepted report\n", encoding="utf-8")
        report_sha = hashlib.sha256(report.read_bytes()).hexdigest()
        receipt = self.product_receipt("meaning", report_sha)
        receipt["data"]["minor"] = 1
        start = self.started("meaning", "product-review", "meaning", lot="lot-1")
        start["by"] = "product-controller"
        verifier_start = self.verifier_started("meaning", report_sha)
        verifier_start["by"] = "product-controller"
        verifier_start.update({
            "mode": "product-review", "lot": "lot-1", "job": "controller",
            "mandate": "meaning",
        })
        verifier_end = self.verifier_malformed("meaning", report_sha)
        verifier_end["by"] = "product-controller"
        verifier_end.update({
            "mode": "product-review", "lot": "lot-1", "job": "controller",
            "mandate": "meaning",
        })
        retirement = self.retired("meaning", "product-review", "meaning", lot="lot-1")
        retirement.update({"by": "product-controller", "archived": True, "hidden": True})
        self.append(start, receipt, verifier_start, verifier_end, retirement)

        def proof(index):
            raw = json.dumps(self.entries[index], separators=(",", ":")).encode()
            return f"{index}:{hashlib.sha256(raw).hexdigest()}"

        other_mandate = {
            "event": "note", "kind": "bound.spent", "mandate": "user",
            "text": "malformed finding returned: F1 - lens other",
        }
        same_mandate = {
            "event": "note", "kind": "bound.spent", "mandate": "meaning",
            "text": "malformed finding returned: F1 - lens meaning",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller",
        }
        working = self.status(
            "meaning", "product-review", "meaning", "working", lot="lot-1",
        )
        self.append(other_mandate, same_mandate, working)
        recovery = {
            "event": "note",
            "kind": "product.reviewer.retirement.recovered",
            "by": "product-controller",
            "mode": "product-review",
            "lot": "lot-1",
            "job": "controller",
            "data": {
                "schema": 1,
                "pass_opening": proof(1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "session_start": proof(2),
                "session": "meaning",
                "mandate": "meaning",
                "receipt": proof(3),
                "report_sha256": report_sha,
                "verifier_opening": proof(4),
                "verifier_terminal": proof(5),
                "retirement": proof(6),
                "settlement": [proof(8), proof(9)],
            },
        }
        self.append(recovery)

        recovered = self.run_helper("product-review")

        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertIn("meaning: wait for the replacement report", recovered.stdout)
        self.assertIn("active reviewers: 1", recovered.stdout)

        exact_opening = recovery["data"]["verifier_opening"]
        recovery["data"]["verifier_opening"] = "0:" + "f" * 64
        changed = self.run_helper("product-review")
        self.assertNotEqual(changed.returncode, 0)
        recovery["data"]["verifier_opening"] = exact_opening

        resumed = self.run_helper("product-review")
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        self.assertIn("meaning: wait for the replacement report", resumed.stdout)

    def test_still_malformed_restatement_closes_with_one_final_receipt(self):
        self.open_product_pass()
        start = self.started("meaning", "product-review", "meaning", lot="lot-1")
        first_receipt = self.product_receipt("meaning", "1" * 64)
        first_receipt["data"]["minor"] = 1
        first_start = self.verifier_started("meaning", "1" * 64)
        first_end = self.verifier_malformed("meaning", "1" * 64)
        malformed_return = {
            "event": "note", "kind": "bound.spent",
            "text": "malformed finding returned: F1 - lens meaning",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "mandate": "meaning", "job": "controller",
        }
        second_receipt = self.product_receipt("meaning", "2" * 64)
        second_receipt["data"]["minor"] = 1
        second_start = self.verifier_started("meaning", "2" * 64)
        second_end = self.verifier_malformed("meaning", "2" * 64)
        retirement = self.retired("meaning", "product-review", "meaning", lot="lot-1")
        retirement.update({"archived": True, "hidden": True})
        recovered_return = dict(malformed_return)
        recovered_working = self.status(
            "meaning", "product-review", "meaning", "working", lot="lot-1",
        )
        final_receipt = self.product_receipt("meaning", "3" * 64)
        final_start = self.verifier_started("meaning", "3" * 64)
        final_end = self.verifier_ended("meaning", "3" * 64)
        retired_base = [
            *self.entries, start, first_receipt, first_start, first_end,
            malformed_return, second_receipt, second_start, second_end, retirement,
            recovered_return, recovered_working,
        ]

        def proof(entries, index):
            raw = json.dumps(entries[index], separators=(",", ":")).encode()
            return f"{index}:{hashlib.sha256(raw).hexdigest()}"

        recovery = {
            "event": "note", "kind": "product.reviewer.retirement.recovered",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller", "data": {
                "schema": 1,
                "pass_opening": proof(retired_base, 1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "session_start": proof(retired_base, 2),
                "session": "meaning", "mandate": "meaning",
                "receipt": proof(retired_base, 7),
                "report_sha256": "2" * 64,
                "verifier_opening": proof(retired_base, 8),
                "verifier_terminal": proof(retired_base, 9),
                "retirement": proof(retired_base, 10),
                "settlement": [proof(retired_base, 11), proof(retired_base, 12)],
            },
        }
        base = [*retired_base, recovery]
        final = [final_receipt, final_start, final_end]

        def copy_entries(entries):
            return json.loads(json.dumps(entries))

        def refused(entries, message):
            self.entries = copy_entries(entries)
            result = self.run_helper("product-review")
            self.assertNotEqual(result.returncode, 0, message)

        nudge = {
            "event": "note", "kind": "bound.spent",
            "text": "nudged the lens meaning",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "mandate": "meaning", "job": "controller",
        }
        first_generation = [
            *copy_entries(self.entries), start, first_receipt, first_start, first_end,
        ]
        refused(
            [*first_generation, nudge, second_receipt],
            "an ordinary nudge authorized the R1 to R2 replacement receipt",
        )
        self.entries = copy_entries([
            *first_generation, nudge, malformed_return,
            second_receipt, second_start, second_end,
        ])
        exact_return_with_nudge = self.run_helper("product-review")
        self.assertEqual(
            exact_return_with_nudge.returncode, 0,
            exact_return_with_nudge.stdout + exact_return_with_nudge.stderr,
        )
        refused(
            [*retired_base[:10], recovered_return, final_receipt],
            "a second-generation return without its exact recovery authorized R3",
        )

        spend_index = next(
            index for index, entry in enumerate(base)
            if entry.get("kind") == "bound.spent" and entry.get("mandate") == "meaning"
        )
        receipt_indexes = [
            index for index, entry in enumerate(base)
            if entry.get("kind") == "report.received" and entry.get("mandate") == "meaning"
        ]
        second_terminal_index = max(
            index for index, entry in enumerate(base)
            if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "finding-verifier"
        )
        missing_spend = [entry for entry in base if entry is not malformed_return]
        refused([*missing_spend, *final], "a missing malformed return authorized final receipt")
        foreign_spend = copy_entries(base)
        foreign_spend[spend_index]["text"] = "malformed finding returned: F1 - lens foreign"
        refused([*foreign_spend, *final], "a foreign malformed return authorized final receipt")
        changed_spend = copy_entries(base)
        changed_spend[spend_index]["text"] = "malformed finding returned: F2 - lens meaning"
        refused([*changed_spend, *final], "a changed malformed claim authorized final receipt")
        duplicate_spend = copy_entries(base)
        duplicate_spend.insert(receipt_indexes[1], copy_entries([malformed_return])[0])
        refused([*duplicate_spend, *final], "a second malformed return authorized final receipt")

        changed_first_receipt = copy_entries(base)
        changed_first_receipt[receipt_indexes[0]]["data"]["report_sha256"] = "4" * 64
        refused([*changed_first_receipt, *final], "a changed R1 receipt authorized final receipt")
        changed_second_verifier = copy_entries(base)
        changed_second_verifier[second_terminal_index]["data"]["report_sha256"] = "5" * 64
        refused([*changed_second_verifier, *final], "a changed R2 verifier authorized final receipt")
        changed_total = copy_entries(final)
        changed_total[0]["data"]["minor"] = 1
        refused([*base, *changed_total], "a changed final count delta authorized final receipt")

        intervening = (
            self.product_receipt("meaning", "4" * 64),
            self.verifier_started("meaning", "2" * 64),
            self.started("meaning-next", "product-review", "meaning", lot="lot-1"),
            self.retired("meaning", "product-review", "meaning", lot="lot-1"),
            {"event": "note", "kind": "pass.closed", "data": {"confirmed": 0}},
            {"event": "note", "kind": "amendment.opened",
             "data": {"origin": "product-review"}},
            {"event": "note", "kind": "paused", "by": "product-controller",
             "mode": "product-review", "lot": "lot-1", "job": "controller"},
            {"event": "note", "kind": "cleanup.started",
             "data": {"scope": "whole-run"}},
        )
        for event in intervening:
            refused(
                [*base, event, *final],
                f"an intervening {event.get('kind') or event.get('event')} authorized final receipt",
            )

        self.entries = [*copy_entries(base), *copy_entries(final)]
        closed = self.run_helper("product-review")
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertIn("meaning: settle verifier result and retire the lens", closed.stdout)

        self.entries.append(self.product_receipt("meaning", "6" * 64))
        fourth = self.run_helper("product-review")
        self.assertNotEqual(fourth.returncode, 0)
        self.assertIn("continues after its final malformed closure", fourth.stdout + fourth.stderr)

    def test_multiple_malformed_claims_require_the_complete_ordered_return_set(self):
        self.open_product_pass()
        start = self.started("meaning", "product-review", "meaning", lot="lot-1")
        first_receipt = self.product_receipt("meaning", "1" * 64)
        first_receipt["data"]["minor"] = 2
        first_terminal = self.verifier_malformed("meaning", "1" * 64)
        first_terminal["data"].update({
            "malformed": 2,
            "claims": [
                {"id": "F1", "kind": "correction", "verdict": "malformed"},
                {"id": "F2", "kind": "correction", "verdict": "malformed"},
            ],
        })
        base = [
            *self.entries, start, first_receipt,
            self.verifier_started("meaning", "1" * 64), first_terminal,
        ]
        second_receipt = self.product_receipt("meaning", "2" * 64)
        second_receipt["data"]["minor"] = 2

        def returned(claim, session="meaning"):
            return {
                "event": "note", "kind": "bound.spent",
                "text": f"malformed finding returned: {claim} - lens {session}",
                "by": "product-controller", "mode": "product-review", "lot": "lot-1",
                "mandate": "meaning", "job": "controller",
            }

        nudge = {
            "event": "note", "kind": "bound.spent", "text": "nudged the lens meaning",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "mandate": "meaning", "job": "controller",
        }

        def validate_return(entries, candidate):
            self.entries = json.loads(json.dumps(entries))
            self.write()
            spec = importlib.util.spec_from_file_location(
                "review_pool_multi_malformed", self.script,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            projected = module.read_entries()
            opening_index, mandates, generation, built = module.current_generation(
                projected, "product-review",
            )
            records = module.session_records(
                projected, opening_index, "product-review", mandates, generation,
            )
            module.validate_product_malformed_return(
                projected, opening_index, projected[opening_index], built,
                "meaning", records, candidate,
            )

        validate_return(base, returned("F1"))
        validate_return([*base, returned("F1"), nudge], returned("F2"))
        with self.assertRaises(SystemExit):
            validate_return(base, returned("F2"))
        with self.assertRaises(SystemExit):
            validate_return([*base, returned("F1")], returned("F1"))

        def result(*suffix):
            self.entries = json.loads(json.dumps([*base, *suffix, second_receipt]))
            return self.run_helper("product-review")

        for suffix, message in (
            ((returned("F1"),), "a missing F2 return authorized R2"),
            ((returned("F2"), returned("F1")), "reordered returns authorized R2"),
            ((returned("F1"), returned("F1")), "a duplicate F1 return authorized R2"),
            ((returned("F1"), returned("F2", "foreign")),
             "a foreign reviewer return authorized R2"),
            ((returned("F1"), returned("F3")), "a foreign claim return authorized R2"),
        ):
            refused = result(*suffix)
            self.assertNotEqual(refused.returncode, 0, message)

        accepted = result(returned("F1"), nudge, returned("F2"))
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertIn("meaning: launch finding verifier", accepted.stdout)

        second_terminal = self.verifier_malformed("meaning", "2" * 64)
        second_terminal["data"].update({
            "malformed": 2,
            "claims": [
                {"id": "F1", "kind": "correction", "verdict": "malformed"},
                {"id": "F2", "kind": "correction", "verdict": "malformed"},
            ],
        })
        self.entries = json.loads(json.dumps([
            *base, returned("F1"), nudge, returned("F2"), second_receipt,
            self.verifier_started("meaning", "2" * 64),
            second_terminal,
        ]))
        with self.assertRaises(SystemExit):
            validate_return(self.entries, returned("F1"))

    def test_recovered_legacy_malformed_chain_closes_with_one_final_receipt(self):
        self.open_product_pass()
        start = self.started("meaning", "product-review", "meaning", lot="lot-1")

        def receipt(number, count=1):
            entry = self.product_receipt("meaning", str(number) * 64)
            entry["data"]["minor"] = count
            return entry

        def returned():
            return {
                "event": "note", "kind": "bound.spent",
                "text": "malformed finding returned: legacy descriptive finding - lens meaning\n",
                "by": "product-controller", "mode": "product-review", "lot": "lot-1",
                "mandate": "meaning", "job": "controller",
            }

        chain = [*self.entries, start]
        receipt_indexes = []
        terminal_indexes = []
        return_indexes = []
        for number in range(1, 5):
            receipt_indexes.append(len(chain))
            chain.extend([
                receipt(number),
                self.verifier_started("meaning", str(number) * 64),
                self.verifier_malformed("meaning", str(number) * 64),
            ])
            terminal_indexes.append(len(chain) - 1)
            if number < 4:
                return_indexes.append(len(chain))
                chain.append(returned())

        retirement = self.retired("meaning", "product-review", "meaning", lot="lot-1")
        retirement.update({"archived": True, "hidden": True})
        chain.append(retirement)

        def proof(entries, index):
            raw = json.dumps(entries[index], separators=(",", ":")).encode()
            return f"{index}:{hashlib.sha256(raw).hexdigest()}"

        recovery = {
            "event": "note", "kind": "product.reviewer.retirement.recovered",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller", "data": {
                "schema": 1,
                "pass_opening": proof(chain, 1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "session_start": proof(chain, 2),
                "session": "meaning", "mandate": "meaning",
                "receipt": proof(chain, receipt_indexes[-1]),
                "report_sha256": "4" * 64,
                "verifier_opening": proof(chain, terminal_indexes[-1] - 1),
                "verifier_terminal": proof(chain, terminal_indexes[-1]),
                "retirement": proof(chain, len(chain) - 1),
                "settlement": [],
            },
        }
        with_recovery = [*chain, recovery]
        legacy_recovery = {
            "event": "note", "kind": "product.reviewer.legacy-chain.recovered",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller", "data": {
                "schema": 1,
                "pass_opening": proof(chain, 1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "reviewer_start": proof(chain, 2),
                "session": "meaning", "mandate": "meaning",
                "retirement_recovery": proof(with_recovery, len(with_recovery) - 1),
                "anchor_receipt": proof(chain, receipt_indexes[-1]),
                "transitions": [
                    {
                        "from_receipt": proof(chain, receipt_indexes[position]),
                        "verifier_opening": proof(
                            chain, terminal_indexes[position] - 1,
                        ),
                        "verifier_terminal": proof(chain, terminal_indexes[position]),
                        "returns": [proof(chain, return_indexes[position])],
                        "to_receipt": proof(chain, receipt_indexes[position + 1]),
                    }
                    for position in range(3)
                ],
            },
        }
        final_receipt = receipt(5, count=1)

        def copied(entries):
            return json.loads(json.dumps(entries))

        def refused(entries, message):
            self.entries = copied(entries)
            result = self.run_helper("product-review")
            self.assertNotEqual(result.returncode, 0, message)

        refused(
            [*chain[:-1], final_receipt],
            "a repeated malformed chain without recovery authorized its final receipt",
        )
        refused(
            [*with_recovery, final_receipt],
            "a retained retirement recovery alone authorized the legacy final receipt",
        )

        return_indexes = [
            index for index, entry in enumerate(chain)
            if entry.get("kind") == "bound.spent"
        ]
        for return_index in return_indexes:
            missing = copied(chain)
            missing[return_index]["text"] = "nudged the lens meaning"
            refused(
                [*missing, recovery, legacy_recovery, final_receipt],
                "a legacy transition with a missing return authorized its final receipt",
            )

        invalid_legacy_returns = (
            "malformed finding returned:   - lens meaning\n",
            "malformed finding returned: F1 - lens meaning\n",
            "malformed finding returned: legacy\nmultiline - lens meaning\n",
            "malformed finding returned: legacy description - lens foreign\n",
            "malformed finding returned: legacy description - lens meaning",
            "wrong prefix: legacy description - lens meaning\n",
        )
        for text in invalid_legacy_returns:
            changed_chain = copied(chain)
            changed_chain[return_indexes[0]]["text"] = text
            changed_legacy_recovery = copied(legacy_recovery)
            changed_legacy_recovery["data"]["transitions"][0]["returns"] = [
                proof(changed_chain, return_indexes[0]),
            ]
            refused(
                [*changed_chain, recovery, changed_legacy_recovery, final_receipt],
                "a malformed descriptive legacy return authorized the final receipt",
            )

        for anchor_index in receipt_indexes[:-1]:
            changed_anchor = copied(legacy_recovery)
            changed_anchor["data"]["anchor_receipt"] = proof(chain, anchor_index)
            refused(
                [*with_recovery, changed_anchor, final_receipt],
                "a recovery anchored to an earlier receipt authorized the final receipt",
            )

        for field in ("verifier_opening", "verifier_terminal", "retirement"):
            changed_proof = copied(recovery)
            changed_proof["data"][field] = "0:" + "f" * 64
            refused(
                [*chain, changed_proof, legacy_recovery, final_receipt],
                f"a changed recovery {field} authorized the final receipt",
            )

        refused(
            [*with_recovery, legacy_recovery, returned(), final_receipt],
            "a new malformed return after recovery authorized the final receipt",
        )
        competing_suffixes = (
            self.status("meaning", "product-review", "meaning", "working", lot="lot-1"),
            self.verifier_started("meaning", "4" * 64),
            self.started("replacement", "product-review", "meaning", lot="lot-1"),
            self.retired("meaning", "product-review", "meaning", lot="lot-1"),
            {
                "event": "note", "kind": "pass.closed", "by": "product-controller",
                "mode": "product-review", "lot": "lot-1", "job": "controller",
            },
            {
                "event": "note", "kind": "amendment.opened", "by": "product-controller",
                "mode": "product-review", "lot": "lot-1", "job": "controller",
                "data": {"origin": "product-review"},
            },
            {
                "event": "note", "kind": "cleanup.started", "by": "product-controller",
                "mode": "product-review", "lot": "lot-1", "job": "controller",
                "data": {"scope": "whole-run"},
            },
            {
                "event": "note", "kind": "paused", "by": "product-controller",
                "mode": "product-review", "lot": "lot-1", "job": "controller",
            },
        )
        for competitor in competing_suffixes:
            refused(
                [*with_recovery, legacy_recovery, competitor, final_receipt],
                "a competing post-recovery event authorized the final receipt",
            )
        wrong_total = copied(final_receipt)
        wrong_total["data"]["minor"] = 0
        refused(
            [*with_recovery, legacy_recovery, wrong_total],
            "a legacy restatement used malformed as removal authority",
        )
        unchanged_sha = copied(final_receipt)
        unchanged_sha["data"]["report_sha256"] = "4" * 64
        refused(
            [*with_recovery, legacy_recovery, unchanged_sha],
            "a legacy restatement reused the anchor report SHA",
        )

        self.entries = copied([*with_recovery, legacy_recovery, final_receipt])
        recovered = self.run_helper("product-review")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertIn("meaning: launch finding verifier", recovered.stdout)

        refused(
            [*with_recovery, legacy_recovery, final_receipt, receipt(6, count=0)],
            "a receipt followed the recovered final closure",
        )

    def test_recovered_legacy_multi_malformed_chain_freezes_return_order(self):
        self.open_product_pass()
        start = self.started("meaning", "product-review", "meaning", lot="lot-1")

        def receipt(number, count=2):
            entry = self.product_receipt("meaning", str(number) * 64)
            entry["data"]["minor"] = count
            return entry

        def terminal(number):
            entry = self.verifier_started("meaning", str(number) * 64)
            entry["event"] = "subagent-ended"
            entry["data"].update({
                "confirmed": 0, "disproved": 0, "malformed": 2,
                "claims": [
                    {"id": "F1", "kind": "correction", "verdict": "malformed"},
                    {"id": "F2", "kind": "correction", "verdict": "malformed"},
                ],
            })
            return entry

        def returned(description):
            return {
                "event": "note", "kind": "bound.spent",
                "text": f"malformed finding returned: {description} - lens meaning\n",
                "by": "product-controller", "mode": "product-review", "lot": "lot-1",
                "mandate": "meaning", "job": "controller",
            }

        chain = [*self.entries, start]
        receipt_indexes = []
        terminal_indexes = []
        return_indexes = []
        for number in range(1, 4):
            receipt_indexes.append(len(chain))
            chain.extend([
                receipt(number),
                self.verifier_started("meaning", str(number) * 64),
                terminal(number),
            ])
            terminal_indexes.append(len(chain) - 1)
            if number < 3:
                current_returns = []
                for claim in (1, 2):
                    current_returns.append(len(chain))
                    chain.append(returned(f"legacy generation {number} claim {claim}"))
                return_indexes.append(current_returns)

        retirement = self.retired("meaning", "product-review", "meaning", lot="lot-1")
        retirement.update({"archived": True, "hidden": True})
        chain.append(retirement)

        def proof(entries, index):
            raw = json.dumps(entries[index], separators=(",", ":")).encode()
            return f"{index}:{hashlib.sha256(raw).hexdigest()}"

        recovery = {
            "event": "note", "kind": "product.reviewer.retirement.recovered",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller", "data": {
                "schema": 1,
                "pass_opening": proof(chain, 1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "session_start": proof(chain, 2),
                "session": "meaning", "mandate": "meaning",
                "receipt": proof(chain, receipt_indexes[-1]),
                "report_sha256": "3" * 64,
                "verifier_opening": proof(chain, terminal_indexes[-1] - 1),
                "verifier_terminal": proof(chain, terminal_indexes[-1]),
                "retirement": proof(chain, len(chain) - 1),
                "settlement": [],
            },
        }
        with_recovery = [*chain, recovery]
        legacy_recovery = {
            "event": "note", "kind": "product.reviewer.legacy-chain.recovered",
            "by": "product-controller", "mode": "product-review", "lot": "lot-1",
            "job": "controller", "data": {
                "schema": 1,
                "pass_opening": proof(chain, 1),
                "owner": "product-controller",
                "controller_context": {
                    "mode": "product-review", "lot": "lot-1", "job": "controller",
                },
                "reviewer_start": proof(chain, 2),
                "session": "meaning", "mandate": "meaning",
                "retirement_recovery": proof(with_recovery, len(with_recovery) - 1),
                "anchor_receipt": proof(chain, receipt_indexes[-1]),
                "transitions": [
                    {
                        "from_receipt": proof(chain, receipt_indexes[position]),
                        "verifier_opening": proof(
                            chain, terminal_indexes[position] - 1,
                        ),
                        "verifier_terminal": proof(chain, terminal_indexes[position]),
                        "returns": [
                            proof(chain, index) for index in return_indexes[position]
                        ],
                        "to_receipt": proof(chain, receipt_indexes[position + 1]),
                    }
                    for position in range(2)
                ],
            },
        }
        final_receipt = receipt(4, count=2)

        self.entries = json.loads(json.dumps([
            *with_recovery, legacy_recovery, final_receipt,
        ]))
        accepted = self.run_helper("product-review")
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

        reordered = json.loads(json.dumps(legacy_recovery))
        reordered["data"]["transitions"][0]["returns"].reverse()
        self.entries = json.loads(json.dumps([
            *with_recovery, reordered, final_receipt,
        ]))
        refused = self.run_helper("product-review")
        self.assertNotEqual(
            refused.returncode, 0,
            "a reordered multi-claim legacy return account authorized final closure",
        )

    def test_failed_owner_becomes_replaceable_until_fresh_receipt_settles(self):
        self.open_product_pass()
        stale_sha = "6" * 64
        fresh_sha = "7" * 64
        self.append(
            self.started("user-old", "product-review", "user", lot="lot-1"),
            self.product_receipt("user", stale_sha),
            self.retired("user-old", "product-review", "user", "failed", lot="lot-1"),
        )

        before = self.run_helper("product-review")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
        self.assertIn("launch now: unlooked, user, meaning", before.stdout)

        self.append(self.started("user-new", "product-review", "user", lot="lot-1"))
        active = self.run_helper("product-review")
        self.assertEqual(active.returncode, 0, active.stdout + active.stderr)
        self.assertIn("user: wait for the replacement report", active.stdout)

        self.append(
            self.product_receipt("user", fresh_sha),
            self.verifier_started("user", fresh_sha),
            self.verifier_ended("user", fresh_sha),
        )
        fresh = self.run_helper("product-review")
        self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)
        self.assertIn("user: settle verifier result and retire the lens", fresh.stdout)

    def test_replacement_start_before_failed_retirement_fails_closed(self):
        self.open_product_pass()
        report_sha = "9" * 64
        self.append(
            self.started("user-old", "product-review", "user", lot="lot-1"),
            self.product_receipt("user", report_sha),
            self.started("user-new", "product-review", "user", lot="lot-1"),
            self.retired("user-old", "product-review", "user", "failed", lot="lot-1"),
        )

        result = self.run_helper("product-review")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("replacement starts before its prior owner retired", result.stdout + result.stderr)

    def test_done_owner_before_verifier_settlement_still_fails_closed(self):
        self.open_product_pass()
        report_sha = "8" * 64
        self.append(
            self.started("user", "product-review", "user", lot="lot-1"),
            self.product_receipt("user", report_sha),
            self.retired("user", "product-review", "user", "done", lot="lot-1"),
        )

        result = self.run_helper("product-review")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retired before its verifier settled", result.stdout + result.stderr)

    def test_direct_controller_and_handoff_contracts_require_refill(self):
        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        worker = (HERE / "prompts" / "common" / "worker.md").read_text(encoding="utf-8")
        spec_mode = (HERE / "prompts" / "spec" / "MODE.md").read_text(encoding="utf-8")
        spec_handoff = (HERE / "prompts" / "spec" / "reviewer-common.md").read_text(
            encoding="utf-8",
        )
        product_mode = (HERE / "prompts" / "product-review" / "MODE.md").read_text(
            encoding="utf-8",
        )
        product_handoff = (HERE / "prompts" / "product-review" / "lens-common.md").read_text(
            encoding="utf-8",
        )
        verifier_handoff = (HERE / "prompts" / "product-review" / "verifier.md").read_text(
            encoding="utf-8",
        )

        self.assertGreaterEqual(spec_mode.count("review-pool.py\" spec"), 2)
        self.assertIn("review-pool.py spec", spec_handoff)
        self.assertGreaterEqual(spec_mode.count("S3.3 SPEC reviewer replacement checkpoint"), 2)
        self.assertNotIn("Fresh reviewers for the", spec_mode)
        self.assertGreaterEqual(product_mode.count("review-pool.py\" product-review"), 2)
        self.assertIn("review-pool.py product-review", product_handoff)
        self.assertIn("CONTROLLER HANDOFF — SUBAGENT TERMINAL FIRST", verifier_handoff)
        self.assertIn("return to the exact report or verifier result", skill)
        self.assertIn("active-subagent roster", worker)
        self.assertIn("active-subagent roster", product_mode)
        self.assertIn('unusable":"lost', product_mode)
        self.assertIn("Never use a TwiCC process-wait", product_mode)
        self.assertGreaterEqual(product_mode.count("R1.2 PRODUCT replacement checkpoint"), 5)
        self.assertNotIn("relaunch fresh", product_mode)
        self.assertNotIn("Relaunch it as a fresh session", product_mode)
        self.assertNotIn("relaunch the reading fresh", product_mode)


if __name__ == "__main__":
    unittest.main()
