#!/usr/bin/env python3
"""Focused behavior tests for the read-only review pool helper."""

import hashlib
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


class ReviewPoolTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.common = self.workspace / "prompts" / "common"
        self.common.mkdir(parents=True)
        self.script = self.common / "review-pool.py"
        if SOURCE.exists():
            shutil.copyfile(SOURCE, self.script)
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
            "mandate": mandate,
            "data": {
                "pass_commit": "c" * 40,
                "pass_gate": "g" * 64,
                "report_sha256": report_sha,
            },
        }

    @staticmethod
    def verifier_ended(mandate, report_sha):
        return {
            "event": "subagent-ended",
            "kind": "finding-verifier",
            "mandate": mandate,
            "data": {
                "pass_commit": "c" * 40,
                "pass_gate": "g" * 64,
                "report_sha256": report_sha,
                "confirmed": 0,
                "disproved": 0,
                "malformed": 0,
                "claims": [],
            },
        }

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
