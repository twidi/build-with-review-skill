import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


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

    def test_topology_selects_only_direct_children(self):
        topology = {
            "processes": {"available": True, "reason": None},
            "nodes": [
                {"id": "orchestrator", "session": {"id": "orchestrator", "title": "Main"}},
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
            ],
        }

        orchestrator, sessions, processes = self.watchdog.read_topology(
            topology, "orchestrator"
        )

        self.assertEqual(orchestrator["title"], "Main")
        self.assertEqual([session["id"] for session in sessions], ["direct"])
        self.assertEqual(processes[0]["session_id"], "direct")

    def session(self, session_id, status, quiet_minutes, archived=False, hidden=False):
        updated = datetime.fromtimestamp(
            self.now.timestamp() - quiet_minutes * 60,
            tz=timezone.utc,
        ).isoformat()
        return {
            "id": session_id,
            "title": f"- {session_id}",
            "archived": archived,
            "hidden": hidden,
            "last_updated_at": updated,
            "annotations": {"bwr": {"status": status}},
        }


if __name__ == "__main__":
    unittest.main()
