import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "skill" / "scripts" / "watchdog.py"


def load_watchdog():
    spec = importlib.util.spec_from_file_location("bwr_watchdog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.watchdog = load_watchdog()
        self.now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)

    def test_keeps_only_open_direct_children(self):
        sessions = [
            self.session("working", "working", 50, hidden=True),
            self.session("idle", "idle", 180),
            self.session("blocked", "blocked", 45),
            self.session("done", "done", 60),
            self.session("archived", "working", 60, archived=True),
            self.session("watchdog", "working", 60),
        ]
        processes = [
            {
                "session_id": "working",
                "state": "assistant_turn",
                "last_state_change_at": "2026-09-03T11:55:00+00:00",
            }
        ]

        rows = self.watchdog.collect_rows(
            sessions,
            processes,
            own_session_id="watchdog",
            now=self.now,
        )

        self.assertEqual({row["id"] for row in rows}, {"working", "idle", "blocked"})
        working = next(row for row in rows if row["id"] == "working")
        self.assertEqual(working["state"], "assistant_turn")
        self.assertEqual(working["turn"], 5)
        self.assertEqual(working["quiet"], 50)

    def test_marks_quiet_work_and_blockers_but_not_idle_sessions(self):
        rows = self.watchdog.collect_rows(
            [
                self.session("working", "working", 50),
                self.session("blocked", "blocked", 45),
                self.session("idle", "idle", 180),
            ],
            [],
            own_session_id="watchdog",
            now=self.now,
        )

        report = self.watchdog.render_snapshot(
            "Main Orchestrator",
            rows,
            stale_after=40,
            now=self.now,
        )

        self.assertIn("**3** open children", report)
        self.assertIn("⚠ **2**", report)
        self.assertIn("⚠ **working**", report)
        self.assertIn("⚠ **blocked**", report)
        self.assertIn("• **idle**", report)
        self.assertLess(report.index("**blocked**"), report.index("**idle**"))
        self.assertIn("If you have unfinished work and no valid blocker, resume it now.", report)

    def test_empty_snapshot_remains_a_resume_reminder(self):
        report = self.watchdog.render_snapshot(
            "Main Orchestrator",
            [],
            stale_after=40,
            now=self.now,
        )

        self.assertIn('NO open children of "Main Orchestrator"', report)
        self.assertIn("**RESUME CHECK**", report)

    def test_topology_selects_complete_current_orchestrator_subtree(self):
        topology = {
            "processes": {"available": True, "reason": None},
            "nodes": [
                {
                    "id": "predecessor",
                    "session": {"id": "predecessor", "title": "Previous"},
                },
                {
                    "id": "orchestrator",
                    "session": {
                        "id": "orchestrator",
                        "title": "Main",
                        "spawned_by": "predecessor",
                    },
                },
                {
                    "id": "direct",
                    "session": {"id": "direct", "spawned_by": "orchestrator"},
                    "process": {"state": "assistant_turn"},
                },
                {
                    "id": "grandchild",
                    "session": {"id": "grandchild", "spawned_by": "direct"},
                    "process": {"state": "assistant_turn"},
                },
                {
                    "id": "other-branch",
                    "session": {"id": "other-branch", "spawned_by": "predecessor"},
                    "process": {"state": "assistant_turn"},
                },
            ],
        }

        orchestrator, sessions, processes = self.watchdog.read_topology(
            topology, "orchestrator"
        )

        self.assertEqual(orchestrator["title"], "Main")
        self.assertEqual(
            [session["id"] for session in sessions], ["direct", "grandchild"]
        )
        self.assertEqual(
            [process["session_id"] for process in processes],
            ["direct", "grandchild"],
        )

    def test_builds_one_local_snapshot_for_each_parent_with_open_children(self):
        orchestrator = self.session("orchestrator", "working", 2)
        orchestrator["title"] = "Main"
        sessions = [
            self.session("implementer", "working", 50, spawned_by="orchestrator"),
            self.session("leaf-reviewer", "working", 8, spawned_by="orchestrator"),
            self.session("checker", "working", 5, spawned_by="implementer"),
            self.session("done-child", "done", 3, spawned_by="leaf-reviewer"),
            self.session("watchdog", "working", 1, spawned_by="orchestrator"),
        ]

        deliveries = self.watchdog.build_deliveries(
            orchestrator,
            sessions,
            [],
            own_session_id="watchdog",
            stale_after=40,
            now=self.now,
        )

        self.assertEqual(
            [recipient for recipient, _ in deliveries],
            ["orchestrator", "implementer"],
        )
        reports = dict(deliveries)
        self.assertIn("**implementer**", reports["orchestrator"])
        self.assertIn("**leaf-reviewer**", reports["orchestrator"])
        self.assertNotIn("**checker**", reports["orchestrator"])
        self.assertIn('**checker**', reports["implementer"])

    def test_orchestrator_receives_snapshot_without_open_children(self):
        orchestrator = self.session("orchestrator", "working", 2)
        orchestrator["title"] = "Main"

        deliveries = self.watchdog.build_deliveries(
            orchestrator,
            [],
            [],
            own_session_id="watchdog",
            stale_after=40,
            now=self.now,
        )

        self.assertEqual([recipient for recipient, _ in deliveries], ["orchestrator"])
        self.assertIn("NO open children", deliveries[0][1])

    def test_deliver_sends_every_parent_report(self):
        self.watchdog.TWICC = ["twicc-test"]
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(self.watchdog.subprocess, "run", return_value=completed) as run:
            with redirect_stdout(io.StringIO()):
                self.watchdog.deliver(
                    [("orchestrator", "root snapshot"), ("implementer", "child snapshot")]
                )

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["twicc-test", "send-message", "orchestrator", "root snapshot"],
                ["twicc-test", "send-message", "implementer", "child snapshot"],
            ],
        )

    def test_delivery_continues_after_one_parent_send_fails(self):
        self.watchdog.TWICC = ["twicc-test"]
        failed = SimpleNamespace(returncode=1, stdout="", stderr="first failed")
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(
            self.watchdog.subprocess, "run", side_effect=[failed, completed]
        ) as run:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.watchdog.deliver(
                        [("orchestrator", "root snapshot"), ("implementer", "child snapshot")]
                    )

        self.assertEqual(len(run.call_args_list), 2)

    def test_print_only_does_not_send_reports(self):
        output = io.StringIO()

        with patch.object(self.watchdog.subprocess, "run") as run:
            with redirect_stdout(output):
                self.watchdog.deliver(
                    [("orchestrator", "root snapshot"), ("implementer", "child snapshot")],
                    print_only=True,
                )

        run.assert_not_called()
        self.assertEqual(output.getvalue(), "root snapshot\nchild snapshot\n")

    def session(
        self,
        session_id,
        status,
        quiet_minutes,
        archived=False,
        hidden=False,
        spawned_by=None,
    ):
        updated = datetime.fromtimestamp(
            self.now.timestamp() - quiet_minutes * 60,
            tz=timezone.utc,
        ).isoformat()
        return {
            "id": session_id,
            "title": f"- {session_id}",
            "archived": archived,
            "hidden": hidden,
            "spawned_by": spawned_by,
            "last_updated_at": updated,
            "annotations": {"bwr": {"status": status}},
        }


if __name__ == "__main__":
    unittest.main()
