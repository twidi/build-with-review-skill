#!/usr/bin/env python3
"""Focused tests for provider-subagent reporting in watchdog.py."""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = HERE / "prompts" / "common"
CONTROLLER = "controller-session-00000000-0000-0000-0000-000000000001"
OWNER = "owner-session-00000000-0000-0000-0000-000000000002"

FAKE_TWICC = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args[:1] == ["whoami"]:
    print(json.dumps({"session_id": "watchdog-session"}))
elif args[:1] == ["session"]:
    print(json.dumps({"id": args[1], "title": "Controller"}))
elif args[:1] == ["processes"]:
    print("[]")
elif args[:1] == ["sessions"]:
    print("[]")
else:
    print("unexpected command", file=sys.stderr)
    sys.exit(64)
'''


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run_watchdog(workspace, fake=None):
    env = dict(os.environ)
    env["TWICC_BIN"] = (f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
                        if fake is not None else "/bin/false")
    script = workspace / "prompts" / "common" / "watchdog.py"
    return subprocess.run(
        [sys.executable, script, CONTROLLER, "40", "--print-only"],
        capture_output=True, text=True, env=env, timeout=30,
    )


def main():
    root = Path(tempfile.mkdtemp(prefix="subagent-watchdog-test-"))
    try:
        workspace = root / "repo" / ".superpowers" / "bwr" / "run"
        common = workspace / "prompts" / "common"
        common.mkdir(parents=True)
        for name in (
            "watchdog.py", "progress.py", "authority_precedence.py",
            "correction_authority.py", "correction_lifecycle.py",
            "final_checker_obligations.py", "journal_context.py",
        ):
            shutil.copyfile(COMMON / name, common / name)
        fake = root / "fake_twicc.py"
        fake.write_text(FAKE_TWICC, encoding="utf-8")

        empty = run_watchdog(workspace, fake)
        check(empty.returncode == 0, empty.stdout + empty.stderr)
        check("OPEN PROVIDER SUBAGENTS" not in empty.stdout, empty.stdout)
        check("RESUME CHECK" in empty.stdout and "resume it now" in empty.stdout,
              empty.stdout)
        check("already acknowledged" in empty.stdout, empty.stdout)

        failed = run_watchdog(workspace)
        check(failed.returncode != 0, "a broken watchdog dependency succeeded")
        check("state is unknown" in failed.stdout, failed.stdout)
        check(failed.stdout.rstrip().splitlines()[-1].startswith("**RESUME CHECK**"),
              failed.stdout)

        opening = {
            "ts": "2026-08-21T10:00:00Z",
            "by": OWNER,
            "event": "subagent-started",
            "kind": "finding-verifier",
            "mode": "product-review",
            "lot": "lot-1",
            "round": 2,
            "mandate": "user",
            "job": "controller",
            "data": {
                "pass_commit": "a" * 40,
                "pass_gate": "b" * 64,
                "report_sha256": "c" * 64,
            },
        }
        (workspace / "progress.jsonl").write_text(
            json.dumps(opening, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        active = run_watchdog(workspace, fake)
        check(active.returncode == 0, active.stdout + active.stderr)
        check("OPEN PROVIDER SUBAGENTS — 1" in active.stdout, active.stdout)
        check("finding-verifier" in active.stdout and OWNER in active.stdout, active.stdout)
        check("mandate=user" in active.stdout, active.stdout)
        check("provider-native" in active.stdout and "Never invent" in active.stdout,
              active.stdout)
        check("After you reconcile every open provider subagent above" in active.stdout,
              active.stdout)
        check("resume it now" not in active.stdout, active.stdout)

        correction_openings = []
        for correction in (1, 2):
            correction_openings.append({
                "ts": f"2026-08-21T10:0{correction}:00Z",
                "by": OWNER,
                "event": "subagent-started",
                "kind": "diagnostic",
                "mode": "construction",
                "lot": "lot-1",
                "correction": correction,
                "task": 1,
                "attempt": 1,
                "job": "implementer",
                "data": {"scope": "diagnostic"},
            })
        (workspace / "progress.jsonl").write_text(
            "".join(json.dumps(opening, separators=(",", ":")) + "\n"
                    for opening in correction_openings),
            encoding="utf-8",
        )
        correction = run_watchdog(workspace, fake)
        check(correction.returncode == 0, correction.stdout + correction.stderr)
        check("OPEN PROVIDER SUBAGENTS — 2" in correction.stdout, correction.stdout)
        check("lot=lot-1 · correction=1 · task=1 · attempt=1" in correction.stdout,
              "the watchdog dropped or reordered Correction round 1")
        check("lot=lot-1 · correction=2 · task=1 · attempt=1" in correction.stdout,
              "the watchdog collapsed Correction round 2")

        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        worker = (COMMON / "worker.md").read_text(encoding="utf-8")
        rules = (COMMON / "progress-rules.md").read_text(encoding="utf-8")
        watchdog_prompt = (COMMON / "watchdog-prompt.md").read_text(encoding="utf-8")
        spec_mode = (HERE / "prompts" / "spec" / "MODE.md").read_text(encoding="utf-8")
        construction_mode = (HERE / "prompts" / "construction" / "MODE.md").read_text(
            encoding="utf-8"
        )
        amendment_mode = (HERE / "prompts" / "amendment" / "MODE.md").read_text(
            encoding="utf-8"
        )
        for subject, text in (("SKILL", skill), ("worker", worker)):
            check("SUBAGENT OPEN" in text and "provider-native" in text,
                  f"{subject} omits the immediate opening reminder")
            check("TwiCC process wait" in text,
                  f"{subject} omits the process-wait prohibition")
        check("`bwr.correction`" in skill and "positive Correction Round ordinal" in skill,
              "the common annotation grammar omits the Correction Round identity")
        check("Correction work-unit sessions" in skill,
              "the common annotation grammar does not restrict bwr.correction")
        check("subagents-open" in rules and "read-only" in rules,
              "progress rules omit the exact open-bracket query")
        check("open provider-subagent" in watchdog_prompt and "RESUME CHECK" in watchdog_prompt,
              "watchdog prompt omits its new report duties")
        check("state unknown" in watchdog_prompt
              and "retry the exact watchdog state inspection" in watchdog_prompt,
              "watchdog prompt omits the safe error resume route")
        check("the only subagent in this mode" in spec_mode,
              "SPEC still contradicts its close-time finding-verifier")
        check('{"scope":"discovery","unusable":"lost"}' in construction_mode,
              "CONSTRUCTION discovery omits its exact lost terminal")
        check("gate-check.sh lost <op>" in construction_mode,
              "CONSTRUCTION gate recovery bypasses its exact lost terminal")
        check('subagent-ended completeness --data \'{"unusable":"lost"}\'' in construction_mode,
              "CONSTRUCTION completeness omits its exact lost terminal")
        check('"owner":"spec-loop"' in spec_mode and '"unusable":"lost"' in spec_mode,
              "SPEC-loop verification omits its exact lost terminal")
        check('subagent-ended consolidation --round <n> --data \'{"unusable":"lost"}\''
              in amendment_mode,
              "AMENDMENT consolidation omits its exact lost terminal")
        check("close that physical bracket as unusable before" in amendment_mode,
              "AMENDMENT resume can regenerate over an open consolidation call")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("all 2 subagent-watchdog cases passed")


if __name__ == "__main__":
    main()
