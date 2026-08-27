#!/usr/bin/env python3
"""Integration tests for the build-with-review gate boundary.

Run from the skill root with: python3 test_gate.py
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


HERE = pathlib.Path(__file__).resolve().parent
TESTS = []


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Fixture:
    def __init__(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="bwr-gate-test-"))
        self.repo = self.temp / "repo"
        self.workspace = self.repo / ".superpowers" / "bwr" / "2026-08-19-demo"
        self.workspace.mkdir(parents=True)
        shutil.copytree(HERE / "prompts", self.workspace / "prompts")
        self.fake = self.temp / "fake_twicc.py"
        self.current_attempt = 1
        self.write_context()

        self.env = dict(os.environ)
        self.env["TWICC_BIN"] = f"{sys.executable} {self.fake}"
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Gate Test")
        (self.repo / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
        (self.repo / "app.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "spec.md").write_text("# Spec\n\nbase\n", encoding="utf-8")
        (self.repo / "docs" / "plans").mkdir(parents=True)
        self.plan_copy = self.repo / "docs" / "plans" / "2026-08-19-demo-lot-1-plan.md"
        self.plan_copy.write_text(
            "# Plan\n\n## Task 1 - One\n"
            "Achieves: Change the application value.\n"
            "To verify: The changed value is covered.\n\n"
            "### Design\n"
            "[written at C3.1 - see below]\n",
            encoding="utf-8",
        )
        self.plan = self.workspace / "plans" / "lot-1-plan.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(self.plan_copy.read_text(encoding="utf-8"), encoding="utf-8")
        (self.repo / ".superpowers" / "bwr" / "gate.md").write_text(
            "git diff --check\n", encoding="utf-8"
        )
        self.git("add", ".gitignore", "app.txt", "spec.md", str(self.plan_copy.relative_to(self.repo)))
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def write_context(self):
        session_id = f"gate-test-session-{self.current_attempt}"
        self.fake.write_text(
            f"""#!/usr/bin/env python3
import json, os, sys
payload = {{"session_id":{session_id!r},"session":{{"id":{session_id!r},"annotations":{{"bwr":{{"schema":1,"job":"implementer","mode":"construction","feature":"demo","lot":"lot-1","task":1,"attempt":{self.current_attempt},"status":"working"}}}}}}}}
if sys.argv[1] == "whoami":
    print(json.dumps(payload))
elif sys.argv[1] == "session":
    print(json.dumps(payload["session"]))
elif sys.argv[1] == "update-session":
    if os.environ.get("BWR_TEST_UPDATE_LOG"):
        with open(os.environ["BWR_TEST_UPDATE_LOG"], "a", encoding="utf-8") as target:
            target.write(json.dumps(sys.argv[1:]) + "\\n")
    print(json.dumps({{"status":"updated"}}))
else:
    raise SystemExit(64)
""",
            encoding="utf-8",
        )

    def set_attempt_context(self, attempt):
        self.current_attempt = attempt
        self.write_context()

    def close(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def run(self, *args, ok=None, input_text=None):
        result = subprocess.run(
            list(map(str, args)), cwd=self.repo, env=self.env,
            input=input_text, capture_output=True, text=True, timeout=60,
        )
        if ok is True and result.returncode != 0:
            raise AssertionError(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
        if ok is False and result.returncode == 0:
            raise AssertionError(f"command unexpectedly succeeded: {args}\n{result.stdout}")
        return result

    def git(self, *args, ok=True, input=None):
        return self.run("git", *args, ok=ok, input_text=input)

    @property
    def gate_check(self):
        return self.workspace / "prompts" / "construction" / "gate-check.sh"

    @property
    def progress(self):
        return self.workspace / "prompts" / "common" / "progress.py"

    def publish_gate_schedule(self, maximum, groups):
        helper = self.workspace / "prompts" / "construction" / "gate_execution.py"
        policy = self.temp / "gate-policy-draft.json"
        policy.write_text(json.dumps({
            "schema": 1, "max_parallel": maximum, "rulings": [],
        }), encoding="utf-8")
        self.run(sys.executable, helper, "policy-publish", policy, ok=True)
        compatibility = []
        offset = 0
        for group in groups:
            positions = list(range(offset + 1, offset + len(group) + 1))
            compatibility.extend({
                "commands": [positions[left], positions[right]],
                "decision": "compatible",
                "basis": {
                    "kind": "analysis", "probability": "RARE",
                    "reason": "The focused fixture gives each command an isolated effect.",
                },
                "triggers": [],
            } for left in range(len(positions)) for right in range(left + 1, len(positions)))
            offset += len(group)
        gate = self.repo / ".superpowers" / "bwr" / "gate.md"
        draft = self.temp / "gate-execution-draft.json"
        draft.write_text(json.dumps({
            "schema": 2,
            "gate": self.git("hash-object", str(gate)).stdout.strip(),
            "compatible_groups": groups,
            "compatibility": compatibility,
        }), encoding="utf-8")
        self.run(sys.executable, helper, "publish", draft, ok=True)

    def progress_call(self, *args, ok=True):
        return self.run(sys.executable, self.progress, *args, ok=ok)

    def journal(self):
        path = self.workspace / "progress.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def seed_clean_spec_close(self):
        spec = self.repo / "spec.md"
        draft = "# Spec\n\n**Status:** draft\n\n## Lot 1 — Core\n\nImplement it.\n"
        spec.write_text(draft, encoding="utf-8")
        self.progress_call(
            "note", "spec.written", "--text", "spec.md", "--data", '{"lots":1}', ok=True,
        )
        mandates = ("enumerator", "verifier", "feasibility", "judge")
        self.progress_call(
            "note", "round.opened", "--data",
            json.dumps({"round": 1, "mandates": list(mandates)}), ok=True,
        )
        reports = self.workspace / "reports" / "spec-review"
        reports.mkdir(parents=True, exist_ok=True)
        for mandate in mandates:
            template = self.workspace / "prompts" / "spec" / f"reviewer-{mandate}-completion.md"
            labels = [
                line.strip()[6:].split(" —", 1)[0]
                for line in template.read_text(encoding="utf-8").splitlines()
                if line.startswith("    - [ ] ")
            ]
            values = []
            for label in labels:
                if mandate == "verifier" and label == "Consistency":
                    value = "0 contradictions, 0 unresolved § references, 0 terminology conflicts"
                elif mandate == "judge" and label == "Ambiguity":
                    value = "10 requirements tested, 0 ambiguous"
                elif mandate == "judge" and label == "Completeness":
                    value = "4 affected states tested, 0 missing a behaviour"
                else:
                    value = "0"
                values.append(f"- [x] {label} — {value}")
            report = "\n".join([f"COMPLETION ({len(labels)} items)", *values, "", "READY", ""])
            (reports / f"round-1-{mandate}.md").write_text(report, encoding="utf-8")
            self.progress_call(
                "note", "report.received", "--round", "1", "--mandate", mandate,
                "--data", '{"critical":0,"important":0,"minor":0,"decision":0}', ok=True,
            )
        spec.write_text(draft.replace("**Status:** draft", "**Status:** reviewed"), encoding="utf-8")

    def append_code_clean(self):
        self.append_design_clean()
        self.run_code_round(1, 0)

    def append_design_clean(self):
        if any((entry.get("data") or {}).get("check") == "design"
               and entry.get("kind") == "verdict.consumed"
               and entry.get("attempt") == self.current_attempt for entry in self.journal()):
            return
        plan = self.plan.read_text(encoding="utf-8")
        if "[written at C3.1 - see below]" in plan:
            self.plan.write_text(
                plan.replace(
                    "[written at C3.1 - see below]",
                    "Change app.txt and verify its observable result.",
                    1,
                ),
                encoding="utf-8",
            )
        elif "### Design" not in plan:
            self.plan.write_text(
                plan.rstrip()
                + "\n\n### Design\nChange app.txt and verify its observable result.\n",
                encoding="utf-8",
            )
        opened = self.progress_call("subagent-started", "design-checker", "--round", "1")
        manifest = json.loads(opened.stdout)["manifest"]
        self.progress_call(
            "note", "bound.spent", "--round", "1",
            "--text", "design checker round 1 of 10",
        )
        report = self.temp / f"design-result-{self.current_attempt}.json"
        report.write_text(json.dumps({
            "verdict": "clean", "manifest": manifest,
            "checks": [
                {"subject": "task contract", "evidence": "Every task obligation was checked."},
                {"subject": "repository fit", "evidence": "Repository placement was checked."},
            ],
            "previous": [], "findings": [],
        }), encoding="utf-8")
        self.progress_call(
            "subagent-ended", "design-checker", "--round", "1",
            "--data", json.dumps({"result": str(report)}),
        )
        self.progress_call(
            "note", "verdict.consumed", "--round", "1",
            "--data", '{"check":"design","outcome":"clean"}',
        )

    def append_design_contract_blocker(self, blocker_round=10):
        plan = self.plan.read_text(encoding="utf-8")
        self.plan.write_text(
            plan.replace(
                "[written at C3.1 - see below]",
                "Implement the exact frozen task contract.",
                1,
            ),
            encoding="utf-8",
        )
        previous = []
        for round_number in range(1, blocker_round + 1):
            opened = self.progress_call(
                "subagent-started", "design-checker", "--round", str(round_number),
            )
            manifest = json.loads(opened.stdout)["manifest"]
            self.progress_call(
                "note", "bound.spent", "--round", str(round_number),
                "--text", f"design checker round {round_number} of 10",
            )
            findings = [{
                "id": 1,
                "where": (
                    "frozen task contract" if round_number == blocker_round
                    else f"Design round {round_number}"
                ),
                "what": "The task contract omits one required parent outcome.",
                "why": "The current task cannot guarantee its parent product obligation.",
                "impact": "IMPORTANT",
                "previous": [1] if previous else [],
            }]
            if round_number == blocker_round:
                findings.append({
                    "id": 2, "where": f"Design round {round_number}",
                    "what": "The blocked Design retains another unresolved defect.",
                    "why": "The next Design must account for the complete final batch.",
                    "impact": "IMPORTANT", "previous": [],
                })
            report = self.temp / f"design-contract-result-{round_number}.json"
            report.write_text(json.dumps({
                "verdict": "findings", "manifest": manifest,
                "checks": [
                    {"subject": "task contract",
                     "evidence": "Every Achieves and To verify obligation was checked."},
                    {"subject": "repository fit",
                     "evidence": "The relevant repository constraints were checked."},
                ],
                "previous": previous,
                "findings": findings,
            }), encoding="utf-8")
            self.progress_call(
                "subagent-ended", "design-checker", "--round", str(round_number),
                "--data", json.dumps({"result": str(report)}),
            )
            self.progress_call(
                "note", "verdict.consumed", "--round", str(round_number),
                "--data", '{"check":"design","outcome":"findings"}',
            )
            if round_number == blocker_round:
                break
            self.plan.write_text(
                re.sub(
                    r"(?ms)^### Design\n.*?(?=^### |^## Task |\Z)",
                    f"### Design\nCorrected Design generation {round_number}.\n",
                    self.plan.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            account = self.temp / f"design-contract-resolution-{round_number}.md"
            account.write_text(
                "## Finding 1 — corrected\n"
                "The corrected Design addresses the exact finding.\n",
                encoding="utf-8",
            )
            self.progress_call(
                "note", "design.review.resolved", "--round", str(round_number),
                "--text-file", account,
                "--data", '{"check":"design","items":[{"id":1,"status":"corrected"}]}',
            )
            previous = [{
                "id": 1, "status": "still-open",
                "evidence": "The exact admitted defect remains open.",
            }]
        self.progress_call(
            "note", "design.review.blocked", "--round", str(blocker_round),
            "--data", '{"check":"design"}',
        )

    def append_design_round_ten_contract_blocker(self):
        self.append_design_contract_blocker(10)

    def run_code_round(self, round_number, findings):
        self.append_design_clean()
        if round_number > 1:
            self.resolve_code_correction(round_number - 1)
        (self.repo / "app.txt").write_text(
            f"reviewed candidate round {round_number}\n", encoding="utf-8",
        )
        self.git("add", "app.txt")
        opened = self.run(
            "bash", self.gate_check, "open", "review",
            f"lot-1/task-1/attempt-{self.current_attempt}/code-round-{round_number}",
            "lot-1", "1", str(self.current_attempt),
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        self.write_gate_report(op)
        self.close_gate(op)
        self.progress_call(
            "subagent-started", "code-checker", "--round", str(round_number),
            "--data", json.dumps({"gate": op}),
        )
        started = self.journal()[-1]["data"]
        manifest = json.loads(
            (self.workspace / started["manifest"]).read_text(encoding="utf-8")
        )
        self.progress_call(
            "note", "bound.spent", "--round", str(round_number),
            "--text", f"code checker round {round_number} of 10",
        )
        report = {
            "verdict": "clean" if findings == 0 else "findings",
            "manifest": started["manifest"],
            "inspected": [
                {"id": item["id"], "path": item["path"],
                 "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"]}
                for item in manifest["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate satisfies Achieves."},
                {"subject": "assertion", "evidence": "The prior value breaks the result."},
            ],
            "previous": [
                {"id": item["id"], "status": "addressed",
                 "evidence": "The corrected candidate removes this exact defect."}
                for item in (manifest.get("previous") or {}).get("findings", [])
            ],
            "findings": [
                {"id": number, "where": f"app.txt:{number}",
                 "what": f"Finding {number}", "why": "The accepted contract is not met.",
                 "impact": "IMPORTANT",
                 "previous": []}
                for number in range(1, findings + 1)
            ],
        }
        source = self.temp / f"code-result-{round_number}.json"
        source.write_text(json.dumps(report), encoding="utf-8")
        self.progress_call(
            "subagent-ended", "code-checker", "--round", str(round_number),
            "--data", json.dumps({"result": str(source)}),
        )
        self.progress_call(
            "note", "verdict.consumed", "--round", str(round_number),
            "--data", json.dumps({
                "check": "code", "outcome": "clean" if findings == 0 else "findings",
            }),
        )

    def resolve_code_correction(self, round_number):
        verdict = next(
            entry for entry in reversed(self.journal())
            if entry.get("kind") == "verdict.consumed"
            and (entry.get("data") or {}).get("check") == "code"
            and entry.get("round") == round_number
        )
        findings = verdict["data"]["findings"]
        path = self.temp / f"code-review-correction-{round_number}.md"
        path.write_text(
            "\n\n".join(
                f"## Finding {finding} — corrected\n"
                f"The candidate correction addresses finding {finding}."
                for finding in range(1, findings + 1)
            ) + "\n",
            encoding="utf-8",
        )
        return self.progress_call(
            "note", "code.review.resolved", "--round", str(round_number),
            "--text-file", path,
            "--data", json.dumps({
                "check": "code",
                "items": [
                    {"id": finding, "status": "corrected"}
                    for finding in range(1, findings + 1)
                ],
            }),
        )
    def append_code_round_ten_findings(self, findings=2):
        for round_number in range(1, 11):
            count = findings if round_number == 10 else 1
            self.run_code_round(round_number, count)

    def resolve_code_round_ten(self, statuses):
        path = self.temp / "code-review-resolution.md"
        sections = []
        for finding, status in enumerate(statuses, 1):
            sections.append(
                f"## Finding {finding} — {status}\n"
                f"Durable evidence for finding {finding} and disposition {status}."
            )
        path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        items = [
            {"id": finding, "status": status}
            for finding, status in enumerate(statuses, 1)
        ]
        alternatives = [finding for finding, status in enumerate(statuses, 1)
                        if status == "alternative"]
        if alternatives:
            disagreement = ["", "### Disagreement"]
            disagreement.extend(
                f"#### Finding {finding} — code alternative\n"
                "Both implementations satisfy the accepted contract."
                for finding in alternatives
            )
            self.plan.write_text(
                self.plan.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(disagreement) + "\n",
                encoding="utf-8",
            )
            publish = self.workspace / "prompts" / "construction" / "plan-publish.sh"
            self.run("bash", publish, "lot-1", ok=True)
            self.git("add", str(self.plan_copy.relative_to(self.repo)))
        return self.progress_call(
            "note", "code.review.resolved", "--round", "10",
            "--text-file", path,
            "--data", json.dumps({"check": "code", "items": items}),
        )

    def start_attempt_state(self):
        run = "refs/bwr/2026-08-19-demo/lot-1"
        self.git("update-ref", f"{run}/task-0", self.base)
        self.git("update-ref", f"{run}/attempt-base", self.base)
        task_headings = [
            line for line in self.plan.read_text(encoding="utf-8").splitlines()
            if line.startswith("## Task ")
        ]
        headings = "\n".join(task_headings) + "\n"
        manifest = self.git("hash-object", "--stdin", input=headings).stdout.strip()
        helper = self.workspace / "prompts" / "construction" / "construction_review.py"
        state = json.loads(self.run(
            sys.executable, helper, "plan-state", "lot-1", "1", ok=True,
        ).stdout)
        (self.workspace / "attempt-in-flight").write_text(
            f"lot-1 1 1\nplan {manifest} {len(task_headings)} ownership {state['plan_ownership_sha256']} "
            f"contract {state['contract_sha256']} retry -\n",
            encoding="utf-8",
        )
        self.progress_call(
            "session-started", f"gate-test-session-{self.current_attempt}", ok=True,
        )

    def prepare_task_candidate(self):
        self.start_attempt_state()
        plan = self.plan.read_text(encoding="utf-8")
        self.plan.write_text(
            plan.replace(
                "[written at C3.1 - see below]",
                "Change app.txt and verify its observable result.",
                1,
            ),
            encoding="utf-8",
        )
        (self.repo / "app.txt").write_text("task candidate\n", encoding="utf-8")
        self.git("add", "app.txt")
        self.append_code_clean()
        publish = self.workspace / "prompts" / "construction" / "plan-publish.sh"
        self.run("bash", publish, "lot-1", ok=True)
        self.git("add", str(self.plan_copy.relative_to(self.repo)))

    def open_task_gate(self):
        result = self.run(
            "bash", self.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        match = re.search(r"^OP ([0-9a-f]{64})$", result.stdout, re.MULTILINE)
        check(match, result.stdout)
        return match.group(1)

    def gate_marker(self):
        marker = {}
        for line in (self.workspace / "gate-check-in-progress").read_text(encoding="utf-8").splitlines():
            key, value = line.split(" ", 1)
            marker[key] = value
        return marker

    def write_gate_report(self, op, *, omit_last=False, command_status="green",
                          cleanliness=True, surface="unchanged"):
        marker = self.gate_marker()
        execution_helper = self.workspace / "prompts" / "construction" / "gate_execution.py"
        self.run(sys.executable, execution_helper, "run", op, ok=True)
        inspection = json.loads(
            self.run(sys.executable, execution_helper, "inspect", op, ok=True).stdout
        )
        account = json.loads(
            (self.workspace / "reports" / "gate" / f"{op}.commands" / "account.json").read_text(
                encoding="utf-8"
            )
        )
        command_results = [
            {
                "command": result["command"],
                "status": "green" if result["returncode"] == 0 else "red",
                "count": 1,
                "example": result["example"],
            }
            for result in account["commands"]
        ]
        if omit_last:
            command_results = command_results[:-1]
        candidates = [] if surface == "unchanged" else [
            {"kind": "addition", "evidence": "README documents python -m extra_check"}
        ]
        report = {
            "op": op,
            "gate": marker["gate"],
            "tree": marker["tree"],
            "execution": inspection["execution"],
            "command_account_sha256": inspection["command_account_sha256"],
            "commands": command_results,
            "cleanliness": {
                "completed": True,
                "unchanged": cleanliness,
                "paths": [] if cleanliness else ["generated.txt"],
            },
            "surface": {"completed": True, "status": surface, "candidates": candidates},
        }
        directory = self.workspace / "reports" / "gate"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{op}.json"
        temporary = directory / f".{op}.tmp"
        temporary.write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
        return path

    def gate_observations(self, op, *, extra=None, cleanliness=True, surface="unchanged"):
        account = json.loads(
            (self.workspace / "reports" / "gate" / f"{op}.commands" / "account.json").read_text(
                encoding="utf-8"
            )
        )
        candidates = [] if surface == "unchanged" else [
            {"kind": "addition", "evidence": "README documents python -m extra_check"}
        ]
        observations = {
            "schema": 1,
            "commands": [
                {"count": 1, "example": result["example"]}
                for result in account["commands"]
            ],
            "cleanliness": {
                "completed": True,
                "unchanged": cleanliness,
                "paths": [] if cleanliness else ["generated.txt"],
            },
            "surface": {"completed": True, "status": surface, "candidates": candidates},
        }
        observations.update(extra or {})
        return observations

    def publish_gate_report(self, op, *, extra=None, cleanliness=True, surface="unchanged",
                            run_execution=True, ok=True):
        execution_helper = self.workspace / "prompts" / "construction" / "gate_execution.py"
        if run_execution:
            self.run(sys.executable, execution_helper, "run", op, ok=True)
        observations = self.gate_observations(
            op, extra=extra, cleanliness=cleanliness, surface=surface,
        )
        return self.run(
            "bash", self.gate_check, "publish-report", op,
            input_text=json.dumps(observations), ok=ok,
        )

    def close_gate(self, op, *, report=True, ok=True):
        if report and not (self.workspace / "reports" / "gate" / f"{op}.json").exists():
            self.write_gate_report(op)
        return self.run("bash", self.gate_check, "close", op, ok=ok)

    def commit_task(self, message="task"):
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()


@test
def logical_gate_freezes_candidate_and_reuses_one_operation():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.write_text("git diff --check\npython -m project_check\n", encoding="utf-8")
        fixture.run("bash", fixture.gate_check, "verify", op, ok=False)
        gate.write_text("git diff --check\n", encoding="utf-8")
        (fixture.repo / "app.txt").write_text("runner side effect\n", encoding="utf-8")
        fixture.run("bash", fixture.gate_check, "verify", op, ok=False)
        fixture.run("git", "checkout", "--", "app.txt", ok=True)
        # checkout restores the staged candidate into the worktree. The same
        # logical opening regenerates a physical call under the same op after
        # the unavailable physical call receives its exact lost terminal.
        fixture.run("bash", fixture.gate_check, "lost", op, ok=True)
        check(fixture.open_task_gate() == op, "a lost physical call allocated a new logical op")
        fixture.close_gate(op)
        retry = fixture.close_gate(op)
        check("already recorded" in retry.stdout, retry.stdout)
    finally:
        fixture.close()


@test
def logical_gate_freezes_and_consumes_the_semantic_parallel_schedule():
    fixture = Fixture()
    try:
        first_ready = fixture.temp / "first-ready"
        second_ready = fixture.temp / "second-ready"
        first_script = fixture.temp / "parallel-first.py"
        second_script = fixture.temp / "parallel-second.py"
        first_script.write_text(
            "import pathlib, time\n"
            f"mine=pathlib.Path({str(first_ready)!r}); other=pathlib.Path({str(second_ready)!r})\n"
            "mine.write_text('ready')\n"
            "\nfor _ in range(100):\n"
            "    if other.exists(): break\n"
            "    time.sleep(0.01)\n"
            "raise SystemExit(0 if other.exists() else 8)\n",
            encoding="utf-8",
        )
        second_script.write_text(
            "import pathlib, time\n"
            f"mine=pathlib.Path({str(second_ready)!r}); other=pathlib.Path({str(first_ready)!r})\n"
            "mine.write_text('ready')\n"
            "\nfor _ in range(100):\n"
            "    if other.exists(): break\n"
            "    time.sleep(0.01)\n"
            "raise SystemExit(0 if other.exists() else 9)\n",
            encoding="utf-8",
        )
        commands = [f"{sys.executable} {first_script}", f"{sys.executable} {second_script}"]
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.write_text("\n".join(commands) + "\n", encoding="utf-8")
        fixture.publish_gate_schedule(2, [commands])

        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        execution_hash = re.search(
            r"^EXECUTION ([0-9a-f]{64})$", opened.stdout, re.MULTILINE
        ).group(1)
        fixture.publish_gate_report(op)
        fixture.close_gate(op, report=False)
        terminal = fixture.journal()[-1]
        check(terminal["data"]["execution"] == execution_hash, terminal)
        check(all(path.exists() for path in (first_ready, second_ready)),
              "the approved compatible group did not execute concurrently")
    finally:
        fixture.close()


@test
def changed_gate_cannot_open_until_execution_schedule_is_settled():
    fixture = Fixture()
    try:
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        original = ["git diff --check", "git status --short"]
        gate.write_text("\n".join(original) + "\n", encoding="utf-8")
        helper = fixture.workspace / "prompts" / "construction" / "gate_execution.py"
        fixture.publish_gate_schedule(2, [original])

        gate.write_text("git diff --check\n", encoding="utf-8")
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opening = (
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD",
        )
        fixture.run(*opening, ok=False)
        check(not (fixture.workspace / "gate-check-in-progress").exists(),
              "a stale execution schedule opened a logical gate")

        fixture.run(sys.executable, helper, "remove", ok=True)
        accepted = fixture.run(*opening, ok=True)
        check(re.search(r"^OP [0-9a-f]{64}$", accepted.stdout, re.MULTILINE),
              accepted.stdout)
    finally:
        fixture.close()


@test
def logical_gate_cannot_be_abandoned_while_its_executor_owner_is_live():
    fixture = Fixture()
    executor = None
    try:
        ready = fixture.temp / "abandon-ready"
        release = fixture.temp / "abandon-release"
        script = fixture.temp / "abandon-owner.py"
        script.write_text(
            "import pathlib, time\n"
            f"ready=pathlib.Path({str(ready)!r}); release=pathlib.Path({str(release)!r})\n"
            "ready.write_text('ready')\n"
            "while not release.exists(): time.sleep(0.01)\n",
            encoding="utf-8",
        )
        command = f"{sys.executable} {script}"
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.write_text(f"{command}\n", encoding="utf-8")
        helper = fixture.workspace / "prompts" / "construction" / "gate_execution.py"
        fixture.publish_gate_schedule(1, [[command]])
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        executor = subprocess.Popen(
            [sys.executable, helper, "run", op], cwd=fixture.repo,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(200):
            if ready.exists():
                break
            time.sleep(0.01)
        check(ready.exists(), "the executor never acquired the logical operation")
        fixture.run("bash", fixture.gate_check, "abandon", op, ok=False)
        check((fixture.workspace / "gate-check-in-progress").exists(),
              "abandon removed a live executor's marker")
        release.write_text("release", encoding="utf-8")
        output = executor.communicate(timeout=10)
        check(executor.returncode == 0, output)
        fixture.run("bash", fixture.gate_check, "abandon", op, ok=True)
        check(not (fixture.workspace / "gate-check-in-progress").exists(),
              "an idle unterminalled operation could not be abandoned")
    finally:
        release = fixture.temp / "abandon-release"
        release.write_text("release", encoding="utf-8")
        if executor is not None and executor.poll() is None:
            executor.kill()
            executor.wait()
        fixture.close()


@test
def lost_gate_runner_closes_before_same_operation_regeneration():
    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        run = "refs/bwr/2026-08-19-demo/lot-1"
        fixture.git("update-ref", f"{run}/task-0", head)
        opening = (
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD",
        )
        first = fixture.run(*opening, ok=True)
        op = re.search(r"^OP ([0-9a-f]{64})$", first.stdout, re.MULTILINE).group(1)
        fixture.run("bash", fixture.gate_check, "lost", op, ok=True)
        open_calls = fixture.run(sys.executable, fixture.progress, "subagents-open", ok=True)
        check(json.loads(open_calls.stdout) == [], "the lost gate-runner bracket remained open")

        second = fixture.run(*opening, ok=True)
        replacement_op = re.search(r"^OP ([0-9a-f]{64})$", second.stdout, re.MULTILINE).group(1)
        check(replacement_op == op, "gate-runner regeneration changed the logical operation")
        fixture.publish_gate_report(op)
        fixture.close_gate(op, report=False)
        terminals = [entry["data"] for entry in fixture.journal()
                     if entry.get("event") == "subagent-ended"
                     and entry.get("kind") == "gate-runner"
                     and entry.get("data", {}).get("op") == op]
        check(len(terminals) == 2 and terminals[0].get("unusable") == "lost"
              and terminals[1].get("green") is True,
              f"the physical gate calls did not retain exact separate terminals: {terminals}")
        current = fixture.run("bash", fixture.gate_check, "require-current", ok=True)
        check(current.stdout.strip() == op,
              "the accepted retry result did not become the current logical gate proof")
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "1", ok=True)
        check((fixture.workspace / "attempt-in-flight").is_file(),
              "the accepted retry result did not authorize the next attempt")
    finally:
        fixture.close()


@test
def close_refuses_when_no_physical_report_exists():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        before = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        fixture.run("bash", fixture.gate_check, "close", op, "true", "unchanged", ok=False)
        check((fixture.workspace / "progress.jsonl").read_text(encoding="utf-8") == before,
              "controller-supplied gate booleans appended a terminal")
        fixture.close_gate(op, report=False, ok=False)
        after = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        check(after == before, "close without a physical report appended a terminal")
        check((fixture.workspace / "gate-check-in-progress").exists(),
              "close without a physical report removed the logical owner")
    finally:
        fixture.close()


@test
def gate_runner_input_derives_every_frozen_value_from_the_live_marker():
    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        marker = fixture.gate_marker()
        context = json.loads(
            fixture.run("bash", fixture.gate_check, "runner-input", op, ok=True).stdout
        )
        expected = {
            "schema": 1,
            "operation": op,
            "gate_path": str(fixture.repo / ".superpowers" / "bwr" / "gate.md"),
            "gate_blob": marker["gate"],
            "candidate_tree": marker["tree"],
            "head": marker["head"],
            "predecessor": marker["base"],
            "execution": re.search(
                r"^EXECUTION ([0-9a-f]{64})$", opened.stdout, re.MULTILINE
            ).group(1),
            "report_path": str(fixture.workspace / "reports" / "gate" / f"{op}.json"),
            "commands": {
                "verify": ["bash", str(fixture.gate_check), "verify", op],
                "run": [
                    "python3",
                    str(fixture.workspace / "prompts" / "construction" / "gate_execution.py"),
                    "run", op,
                ],
                "inspect": [
                    "python3",
                    str(fixture.workspace / "prompts" / "construction" / "gate_execution.py"),
                    "inspect", op,
                ],
                "publish_report": ["bash", str(fixture.gate_check), "publish-report", op],
            },
        }
        check(context == expected, f"runner-input did not derive the exact marker identity: {context}")
        fixture.run("bash", fixture.gate_check, "runner-input", "0" * 64, ok=False)
    finally:
        fixture.close()


@test
def gate_report_publication_injects_frozen_identity_and_closes():
    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        marker = fixture.gate_marker()
        fixture.publish_gate_report(op)
        report_path = fixture.workspace / "reports" / "gate" / f"{op}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        check(report["op"] == op, "the publisher did not inject the frozen operation")
        check(report["gate"] == marker["gate"], "the publisher did not inject the frozen gate")
        check(report["tree"] == marker["tree"], "the publisher did not inject the frozen tree")
        check(report["commands"][0]["command"] == "git diff --check",
              "the publisher did not inject the frozen command")
        check(report["commands"][0]["status"] == "green",
              "the publisher did not derive the physical command status")
        fixture.close_gate(op, report=False)
        check(fixture.journal()[-1]["data"]["green"] is True,
              "the mechanically published report did not close green")
    finally:
        fixture.close()


@test
def gate_report_publication_refuses_identity_fields_and_candidate_drift():
    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        result = fixture.publish_gate_report(op, extra={"tree": head}, ok=False)
        check(result.returncode != 0, "a runner-supplied tree was accepted")
        report_path = fixture.workspace / "reports" / "gate" / f"{op}.json"
        check(not report_path.exists(), "a refused runner-supplied identity published a report")

        (fixture.repo / "app.txt").write_text("drift after opening\n", encoding="utf-8")
        fixture.run("bash", fixture.gate_check, "runner-input", op, ok=False)
        result = fixture.publish_gate_report(op, run_execution=False, ok=False)
        check(result.returncode != 0, "a changed candidate published a gate report")
        check(not report_path.exists(), "candidate drift left a canonical report")
    finally:
        fixture.close()


@test
def gate_report_publication_rechecks_drift_after_reading_observations():
    fixture = Fixture()
    publisher = None
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        marker = fixture.gate_marker()
        execution = re.search(
            r"^EXECUTION ([0-9a-f]{64})$", opened.stdout, re.MULTILINE
        ).group(1)
        execution_helper = fixture.workspace / "prompts" / "construction" / "gate_execution.py"
        fixture.run(sys.executable, execution_helper, "run", op, ok=True)
        observations = fixture.gate_observations(op)
        report_helper = fixture.workspace / "prompts" / "construction" / "gate_report.py"
        publisher = subprocess.Popen(
            [
                sys.executable, str(report_helper), "publish", op,
                marker["gate"], marker["tree"], execution,
            ],
            cwd=fixture.repo, env=fixture.env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        waiting = False
        for _ in range(500):
            if publisher.poll() is not None:
                break
            try:
                waiting = "pipe_read" in pathlib.Path(
                    f"/proc/{publisher.pid}/wchan"
                ).read_text(encoding="utf-8")
            except OSError:
                waiting = False
            if waiting:
                break
            time.sleep(0.01)
        check(waiting, "the publisher did not reach its observation-read boundary")

        (fixture.repo / "app.txt").write_text("drift during publication\n", encoding="utf-8")
        stdout, stderr = publisher.communicate(json.dumps(observations), timeout=10)
        check(publisher.returncode != 0, f"publication crossed candidate drift: {stdout} {stderr}")
        check(not (fixture.workspace / "reports" / "gate" / f"{op}.json").exists(),
              "publication after candidate drift left a canonical report")
    finally:
        if publisher is not None and publisher.poll() is None:
            publisher.kill()
            publisher.wait()
        fixture.close()


@test
def gate_report_publication_is_idempotent_and_refuses_foreign_bytes():
    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.publish_gate_report(op)
        report_path = fixture.workspace / "reports" / "gate" / f"{op}.json"
        original = report_path.read_bytes()
        fixture.publish_gate_report(op)
        check(report_path.read_bytes() == original,
              "idempotent publication changed the canonical report")

        report_path.unlink()
        report_path.write_text("foreign\n", encoding="utf-8")
        result = fixture.publish_gate_report(op, run_execution=False, ok=False)
        check(result.returncode != 0, "foreign report bytes were replaced")
        check(report_path.read_text(encoding="utf-8") == "foreign\n",
              "publication changed a foreign report occupant")
    finally:
        fixture.close()


@test
def gate_report_publication_derives_red_status_and_refuses_bad_summaries():
    fixture = Fixture()
    try:
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.write_text("bash -c 'echo failed; exit 7'\n", encoding="utf-8")
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.publish_gate_report(op)
        report_path = fixture.workspace / "reports" / "gate" / f"{op}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        check(report["commands"][0]["status"] == "red",
              "the publisher did not derive RED from the command account")
        fixture.close_gate(op, report=False)
        check(fixture.journal()[-1]["data"]["green"] is False,
              "the RED command became a green logical gate result")
    finally:
        fixture.close()

    fixture = Fixture()
    try:
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"c0/{head}",
            "-", "0", "0", "HEAD", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        execution_helper = fixture.workspace / "prompts" / "construction" / "gate_execution.py"
        fixture.run(sys.executable, execution_helper, "run", op, ok=True)
        bad = {
            "schema": 1,
            "commands": [{"count": True, "example": "not a valid count"}],
            "cleanliness": {"completed": True, "unchanged": True, "paths": []},
            "surface": {"completed": True, "status": "unchanged", "candidates": []},
        }
        fixture.run(
            "bash", fixture.gate_check, "publish-report", op,
            input_text=json.dumps(bad), ok=False,
        )
        check(not (fixture.workspace / "reports" / "gate" / f"{op}.json").exists(),
              "invalid summaries left a canonical report")
    finally:
        fixture.close()


@test
def close_refuses_a_report_that_omits_one_frozen_gate_line():
    fixture = Fixture()
    try:
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.write_text("git diff --check\ngit status --short\n", encoding="utf-8")
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.write_gate_report(op, omit_last=True)
        before = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        fixture.close_gate(op, report=False, ok=False)
        after = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        check(after == before, "an incomplete command account appended a terminal")
        check((fixture.workspace / "gate-check-in-progress").exists(),
              "an incomplete command account removed the logical owner")
    finally:
        fixture.close()


@test
def full_line_gate_comments_are_not_commands():
    fixture = Fixture()
    try:
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        command = "printf '%s\\n' '# remains command data' >/dev/null"
        gate.write_text(
            "# Explain why one documented command is not present.\n"
            "   # An indented full-line comment is also non-executable.\n"
            f"{command}\n",
            encoding="utf-8",
        )
        op = "a" * 64
        tree = fixture.git("write-tree").stdout.strip()
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        gate_sha = fixture.git("hash-object", str(gate)).stdout.strip()
        (fixture.workspace / "gate-check-in-progress").write_text(
            "\n".join((
                f"op {op}",
                "scope review",
                "owner comment-test",
                "lot lot-1",
                "task 1",
                "attempt 1",
                f"head {head}",
                f"base {head}",
                f"tree {tree}",
                f"gate {gate_sha}",
                "code -",
            )) + "\n",
            encoding="utf-8",
        )

        ordinary = fixture.workspace / "prompts" / "construction" / "ordinary_gate.py"
        fixture.run(sys.executable, ordinary, op, ok=True)
        report = json.loads(
            (fixture.workspace / "reports" / "gate" / f"{op}.json").read_text(encoding="utf-8")
        )
        check(
            [result["command"] for result in report["commands"]] == [command],
            "full-line comments entered the physical command account",
        )

        auditor = fixture.workspace / "prompts" / "construction" / "gate_report.py"
        fixture.run(sys.executable, auditor, op, gate_sha, tree, ok=True)
    finally:
        fixture.close()


@test
def gate_writer_counts_commands_and_refuses_comment_only_files():
    fixture = Fixture()
    try:
        gate = fixture.repo / ".superpowers" / "bwr" / "gate.md"
        gate.unlink()
        writer = fixture.workspace / "prompts" / "construction" / "gate-write.sh"
        created = fixture.run(
            "bash", writer, "create", "--",
            "# This rationale is human-validated with the list.",
            "git diff --check",
            ok=True,
        )
        check("COMMANDS 1" in created.stdout, created.stdout)
        check(
            gate.read_text(encoding="utf-8")
            == "# This rationale is human-validated with the list.\ngit diff --check\n",
            "gate-write did not preserve the validated comment bytes",
        )

        current = fixture.git("hash-object", str(gate)).stdout.strip()
        fixture.run(
            "bash", writer, "replace", current, "--", "# No executable command remains.",
            ok=False,
        )
        check("git diff --check" in gate.read_text(encoding="utf-8"),
              "a refused comment-only replacement changed gate.md")
    finally:
        fixture.close()


@test
def plan_publication_after_the_runner_invalidates_the_result():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.plan.write_text(fixture.plan.read_text(encoding="utf-8") + "late\n", encoding="utf-8")
        before = fixture.plan_copy.read_text(encoding="utf-8")
        publish = fixture.workspace / "prompts" / "construction" / "plan-publish.sh"
        fixture.run("bash", publish, "lot-1", ok=False)
        check(fixture.plan_copy.read_text(encoding="utf-8") == before,
              "plan-publish changed the frozen post-runner candidate")
        fixture.close_gate(op)
    finally:
        fixture.close()


@test
def plan_publication_preserves_the_frozen_controller_contract():
    fixture = Fixture()
    try:
        initial = (
            "# Plan\n\n## Task 1 - One\n"
            "Achieves: Keep the accepted behavior.\n"
            "To verify: The behavior remains visible.\n\n"
            "### Design\nInitial implementation design.\n"
        )
        fixture.plan.write_text(initial, encoding="utf-8")
        headings = "## Task 1 - One\n"
        manifest = fixture.git("hash-object", "--stdin", input=headings).stdout.strip()
        helper = fixture.workspace / "prompts" / "construction" / "construction_review.py"
        state = json.loads(fixture.run(sys.executable, helper, "plan-state", "lot-1", "1").stdout)
        (fixture.workspace / "attempt-in-flight").write_text(
            f"lot-1 1 1\nplan {manifest} 1 ownership {state['plan_ownership_sha256']} "
            f"contract {state['contract_sha256']} retry -\n",
            encoding="utf-8",
        )
        publish = fixture.workspace / "prompts" / "construction" / "plan-publish.sh"

        fixture.plan.write_text(initial.replace("Keep the accepted behavior", "Weaken it"),
                                encoding="utf-8")
        fixture.run("bash", publish, "lot-1", ok=False)

        fixture.plan.write_text(initial.replace("Initial implementation design", "Revised design"),
                                encoding="utf-8")
        fixture.run("bash", publish, "lot-1", ok=True)
        check("Revised design" in fixture.plan_copy.read_text(encoding="utf-8"),
              "the permitted Design change was not published")
        check("Keep the accepted behavior" in fixture.plan_copy.read_text(encoding="utf-8"),
              "the published plan changed the frozen controller contract")
    finally:
        fixture.close()


@test
def ordinary_review_gate_proves_one_exact_staged_candidate():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        (fixture.repo / "app.txt").write_text("review candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review", "lot-1/task-1/attempt-1/code-round-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        ordinary = fixture.workspace / "prompts" / "construction" / "ordinary_gate.py"
        fixture.run(sys.executable, ordinary, op, ok=True)
        fixture.close_gate(op)
        fixture.run(
            "bash", fixture.gate_check, "require-review", op, "lot-1", "1", "1", ok=True,
        )

        (fixture.repo / "app.txt").write_text("different candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        fixture.run(
            "bash", fixture.gate_check, "require-review", op, "lot-1", "1", "1", ok=False,
        )
    finally:
        fixture.close()


@test
def code_checker_consumes_the_exact_gate_manifest_and_strict_result():
    fixture = Fixture()
    try:
        plan = (
            "# Plan\n\n## Task 1 - One\n"
            "Achieves: Change the application value.\n"
            "To verify: The changed value is covered.\n\n"
            "### Design\nChange app.txt and verify its observable result.\n"
        )
        fixture.plan.write_text(plan, encoding="utf-8")
        fixture.plan_copy.write_text(plan, encoding="utf-8")
        fixture.git("add", str(fixture.plan_copy.relative_to(fixture.repo)))
        fixture.git("commit", "-q", "-m", "accepted plan")
        fixture.base = fixture.git("rev-parse", "HEAD").stdout.strip()
        fixture.start_attempt_state()

        fixture.append_design_clean()

        (fixture.repo / "app.txt").write_text("reviewed candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review", "lot-1/task-1/attempt-1/code-round-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)

        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}),
        )
        started = fixture.journal()[-1]["data"]
        manifest_path = fixture.workspace / started["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fixture.progress_call(
            "note", "bound.spent", "--round", "1",
            "--text", "code checker round 1 of 10",
        )
        result = {
            "verdict": "clean", "manifest": started["manifest"],
            "inspected": [
                {
                    "id": item["id"], "path": item["path"],
                    "diff_sha256": item["diff_sha256"],
                    "after_sha256": item["after_sha256"],
                }
                for item in manifest["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate satisfies Achieves."},
                {"subject": "assertion", "evidence": "The old value breaks the required result."},
            ],
            "previous": [], "findings": [],
        }
        source = fixture.temp / "checker-result.json"
        source.write_text(json.dumps(result), encoding="utf-8")
        fixture.progress_call(
            "subagent-ended", "code-checker", "--round", "1",
            "--data", json.dumps({"result": str(source)}),
        )
        fixture.progress_call(
            "note", "verdict.consumed", "--round", "1",
            "--data", '{"check":"code","outcome":"clean"}',
        )
        consumed = fixture.journal()[-1]["data"]
        check(consumed["tree"] == started["tree"], "the verdict changed candidate identity")
        check(consumed["findings"] == 0 and consumed["report_sha256"], consumed)
    finally:
        fixture.close()


@test
def invalid_code_result_can_be_replaced_on_the_same_physical_call():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_design_clean()
        (fixture.repo / "app.txt").write_text("reviewed candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review",
            "lot-1/task-1/attempt-1/code-round-1", "lot-1", "1", "1",
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}),
        )
        started = fixture.journal()[-1]["data"]
        manifest = json.loads(
            (fixture.workspace / started["manifest"]).read_text(encoding="utf-8")
        )
        fixture.progress_call(
            "note", "bound.spent", "--round", "1",
            "--text", "code checker round 1 of 10",
        )

        invalid = fixture.temp / "invalid-code-result.json"
        invalid.write_text(json.dumps({
            "verdict": "findings", "manifest": started["manifest"],
            "inspected": [
                {
                    "id": item["id"], "path": item["path"],
                    "diff_sha256": item["diff_sha256"],
                    "after_sha256": item["after_sha256"],
                }
                for item in manifest["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate violates Achieves."},
                {"subject": "assertion", "evidence": "The old value still passes the test."},
            ],
            "previous": [],
            "findings": [
                {"id": 1, "where": "app.txt:1", "what": "The old value remains",
                 "why": "The accepted contract is not met.", "previous": []}
            ],
        }), encoding="utf-8")
        before = (fixture.workspace / "progress.jsonl").read_bytes()
        fixture.progress_call(
            "subagent-ended", "code-checker", "--round", "1",
            "--data", json.dumps({"result": str(invalid)}), ok=False,
        )
        check((fixture.workspace / "progress.jsonl").read_bytes() == before,
              "an invalid checker result changed the open physical call")

        replacement = {
            "verdict": "clean", "manifest": started["manifest"],
            "inspected": [
                {
                    "id": item["id"], "path": item["path"],
                    "diff_sha256": item["diff_sha256"],
                    "after_sha256": item["after_sha256"],
                }
                for item in manifest["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate satisfies Achieves."},
                {"subject": "assertion", "evidence": "The old value breaks the result."},
            ],
            "previous": [], "findings": [],
        }
        corrected = fixture.temp / "corrected-code-result.json"
        corrected.write_text(json.dumps(replacement), encoding="utf-8")
        fixture.progress_call(
            "subagent-ended", "code-checker", "--round", "1",
            "--data", json.dumps({"result": str(corrected)}),
        )
        ended = [
            entry for entry in fixture.journal()
            if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "code-checker"
        ]
        check(len(ended) == 1 and ended[0]["data"]["call"] == 1,
              "the corrected replacement did not close the original physical call")
    finally:
        fixture.close()


@test
def unusable_code_result_regenerates_the_same_logical_round_without_another_spend():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_design_clean()
        (fixture.repo / "app.txt").write_text("reviewed candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review",
            "lot-1/task-1/attempt-1/code-round-1", "lot-1", "1", "1",
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}),
        )
        first = fixture.journal()[-1]["data"]
        fixture.progress_call(
            "note", "bound.spent", "--round", "1",
            "--text", "code checker round 1 of 10",
        )
        invalid = fixture.temp / "lost-live-repair-result.json"
        invalid.write_text('{"verdict":"clean"', encoding="utf-8")
        for _ in range(2):
            before = (fixture.workspace / "progress.jsonl").read_bytes()
            fixture.progress_call(
                "subagent-ended", "code-checker", "--round", "1",
                "--data", json.dumps({"result": str(invalid)}), ok=False,
            )
            check((fixture.workspace / "progress.jsonl").read_bytes() == before,
                  "a refused live repair changed durable state")
        before = (fixture.workspace / "progress.jsonl").read_bytes()
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}), ok=False,
        )
        check((fixture.workspace / "progress.jsonl").read_bytes() == before,
              "resume opened a new physical call over the lost live repair call")
        fixture.progress_call(
            "subagent-ended", "code-checker", "--round", "1",
            "--data", '{"unusable":"lost"}',
        )
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}),
        )
        second = fixture.journal()[-1]["data"]
        check(first["call"] == 1 and second["call"] == 2,
              "the regenerated checker did not allocate the next physical call")
        check(first["manifest"] == second["manifest"] and first["tree"] == second["tree"],
              "the regenerated checker changed its frozen candidate")
        spends = [
            entry for entry in fixture.journal()
            if entry.get("kind") == "bound.spent"
            and entry.get("text") == "code checker round 1 of 10"
        ]
        check(len(spends) == 1,
              "the regenerated physical call consumed another logical round spend")
    finally:
        fixture.close()


@test
def final_gate_refuses_code_bytes_changed_after_the_clean_review():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        (fixture.repo / "app.txt").write_text("changed after clean review\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        before = fixture.workspace.joinpath("progress.jsonl").read_text(encoding="utf-8")
        fixture.run(
            "bash", fixture.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=False,
        )
        check(fixture.workspace.joinpath("progress.jsonl").read_text(encoding="utf-8") == before,
              "a changed post-review candidate mutated the journal")
        check(not fixture.workspace.joinpath("gate-check-in-progress").exists(),
              "a changed post-review candidate opened the final gate")
    finally:
        fixture.close()


@test
def code_checker_refuses_a_design_changed_after_its_clean_verdict():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_design_clean()
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").replace(
                "Change app.txt and verify its observable result.",
                "Use an unreviewed replacement architecture.",
            ),
            encoding="utf-8",
        )
        (fixture.repo / "app.txt").write_text("candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review",
            "lot-1/task-1/attempt-1/code-round-1", "lot-1", "1", "1",
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)
        before = fixture.workspace.joinpath("progress.jsonl").read_text(encoding="utf-8")
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "1",
            "--data", json.dumps({"gate": op}), ok=False,
        )
        check(fixture.workspace.joinpath("progress.jsonl").read_text(encoding="utf-8") == before,
              "an unreviewed Design opened a code checker")
    finally:
        fixture.close()


@test
def later_code_round_refuses_the_unchanged_prior_candidate():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.run_code_round(1, 1)
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review",
            "lot-1/task-1/attempt-1/code-round-2", "lot-1", "1", "1",
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "2",
            "--data", json.dumps({"gate": op}), ok=False,
        )
    finally:
        fixture.close()


@test
def later_code_round_requires_an_exact_prior_finding_account():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.run_code_round(1, 1)
        (fixture.repo / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
        fixture.git("add", "unrelated.txt")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "review",
            "lot-1/task-1/attempt-1/code-round-2", "lot-1", "1", "1",
            "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)
        fixture.progress_call(
            "subagent-started", "code-checker", "--round", "2",
            "--data", json.dumps({"gate": op}), ok=False,
        )
    finally:
        fixture.close()


@test
def attempt_start_refuses_a_workspace_contract_changed_from_the_committed_plan():
    fixture = Fixture()
    try:
        run = "refs/bwr/2026-08-19-demo/lot-1"
        fixture.git("update-ref", f"{run}/task-0", fixture.base)
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{fixture.base}",
            "-", "0", "0", fixture.base, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").replace(
                "Change the application value.", "Use a weaker task contract.",
            ),
            encoding="utf-8",
        )
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "1", ok=False)
        check(not (fixture.workspace / "attempt-in-flight").exists(),
              "a mutable workspace contract became fresh task authority")
    finally:
        fixture.close()


@test
def plan_publication_refuses_a_change_to_another_task_section():
    fixture = Fixture()
    try:
        plan = (
            "# Plan\n\n## Task 1 - One\n"
            "Achieves: Change the application value.\n"
            "To verify: The changed value is covered.\n\n"
            "### Design\n"
            "[written at C3.1 - see below]\n\n"
            "## Task 2 - Two\n"
            "Achieves: Preserve the second contract.\n"
            "To verify: The second contract remains visible.\n\n"
            "### Design\n"
            "[written at C3.1 - see below]\n"
        )
        fixture.plan.write_text(plan, encoding="utf-8")
        fixture.plan_copy.write_text(plan, encoding="utf-8")
        fixture.git("add", str(fixture.plan_copy.relative_to(fixture.repo)))
        fixture.git("commit", "-q", "-m", "two-task plan")
        fixture.base = fixture.git("rev-parse", "HEAD").stdout.strip()
        run = "refs/bwr/2026-08-19-demo/lot-1"
        fixture.git("update-ref", f"{run}/task-0", fixture.base)
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{fixture.base}",
            "-", "0", "0", fixture.base, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "1", ok=True)

        fixture.plan.write_text(
            plan.replace("Preserve the second contract.", "Silently replace task two."),
            encoding="utf-8",
        )
        publish = fixture.workspace / "prompts" / "construction" / "plan-publish.sh"
        fixture.run("bash", publish, "lot-1", ok=False)
        check(fixture.plan_copy.read_text(encoding="utf-8") == plan,
              "another task's controller-owned section was published")
    finally:
        fixture.close()


@test
def task_acceptance_consumes_exact_gate_tree_and_rejects_done_repair():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        stable = fixture.git("rev-parse", "refs/bwr/2026-08-19-demo/lot-1/task-1").stdout.strip()
        check(stable == sha, "the exact valid gate did not publish the task ref")

        # A later content-changing amend cannot consume the old green result.
        (fixture.repo / "app.txt").write_text("changed after Done\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        fixture.git("commit", "--amend", "-q", "--no-edit")
        amended = fixture.git("rev-parse", "HEAD").stdout.strip()
        fixture.run("bash", fixture.gate_check, "require-task", op, "lot-1", "1", "1", amended, ok=False)
    finally:
        fixture.close()


@test
def task_success_recovers_one_legacy_ref_without_attempt_identity():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        journal = fixture.workspace / "progress.jsonl"
        entries = fixture.journal()
        start = next(entry for entry in entries if entry.get("event") == "session-started")
        start["data"].pop("session")
        start["data"].pop("authority_sha256")
        start["data"]["schema"] = 1
        journal.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in entries),
            encoding="utf-8",
        )
        stable_ref = "refs/bwr/2026-08-19-demo/lot-1/task-1"
        fixture.git("update-ref", stable_ref, sha)
        (fixture.workspace / "attempt-in-flight").unlink()
        before_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        before_tree = fixture.git("rev-parse", "HEAD^{tree}").stdout.strip()

        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        refused = fixture.run("bash", succeeded, "lot-1", "1", sha, "0" * 64, ok=False)
        check(refused.returncode != 0
              and not (fixture.workspace / "attempt-success-in-progress.json").exists()
              and fixture.git("rev-parse", stable_ref).stdout.strip() == sha,
              f"a foreign gate changed the legacy recovery prefix: {refused.stdout} {refused.stderr}")
        fixture.set_attempt_context(2)
        wrong_provider = fixture.run(
            "bash", succeeded, "lot-1", "1", sha, op, ok=False,
        )
        check("live legacy implementer session" in (wrong_provider.stdout + wrong_provider.stderr)
              and not (fixture.workspace / "attempt-success-in-progress.json").exists(),
              wrong_provider.stdout + wrong_provider.stderr)
        fixture.set_attempt_context(1)
        recovered = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        terminals = [
            entry for entry in fixture.journal()
            if entry.get("kind") == "attempt.succeeded"
            and entry.get("lot") == "lot-1" and entry.get("task") == 1
        ]
        check(len(terminals) == 1, terminals)
        recovery = terminals[0]["data"].get("success_recovery")
        check(isinstance(recovery, dict)
              and recovery.get("session") == "gate-test-session-1"
              and recovery.get("session_authority", {}).get("session")
              == "gate-test-session-1"
              and recovery.get("commit") == sha
              and recovery.get("gate") == op,
              terminals[0])
        check(not (fixture.workspace / "attempt-success-in-progress.json").exists(),
              "the recovered success retained its owner marker")
        check(fixture.git("rev-parse", stable_ref).stdout.strip() == sha
              and fixture.git("rev-parse", "HEAD").stdout.strip() == before_head
              and fixture.git("rev-parse", "HEAD^{tree}").stdout.strip() == before_tree
              and not fixture.git("status", "--porcelain").stdout,
              "the legacy recovery changed repository authority")

        again = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        check("already recorded" in again.stdout
              and len([
                  entry for entry in fixture.journal()
                  if entry.get("kind") == "attempt.succeeded"
                  and entry.get("lot") == "lot-1" and entry.get("task") == 1
              ]) == 1,
              recovered.stdout + recovered.stderr + again.stdout + again.stderr)
    finally:
        fixture.close()


@test
def task_success_resumes_every_helper_owned_public_phase():
    for phase in ("owned", "ref-written", "ref-published", "terminal-written",
                  "terminal-recorded"):
        fixture = Fixture()
        try:
            fixture.prepare_task_candidate()
            op = fixture.open_task_gate()
            fixture.close_gate(op)
            sha = fixture.commit_task()
            succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
            fixture.env["BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER"] = phase
            interrupted = fixture.run(
                "bash", succeeded, "lot-1", "1", sha, op, ok=False,
            )
            check(interrupted.returncode == 75, f"{phase}: {interrupted.stderr}")
            check((fixture.workspace / "attempt-success-in-progress.json").is_file(),
                  f"{phase} did not retain the durable success owner")
            if phase == "owned":
                update_log = fixture.temp / "session-updates.jsonl"
                fixture.env["BWR_TEST_UPDATE_LOG"] = str(update_log)
                journal = fixture.workspace / "progress.jsonl"
                complete_journal = journal.read_bytes()
                incomplete_journal = complete_journal + b'{"interrupted"'
                journal.write_bytes(incomplete_journal)
                fixture.progress_call(
                    "session-retired", "gate-test-session-1", "done",
                    "--archive", "--hide", ok=False,
                )
                check(not update_log.exists()
                      and journal.read_bytes() == incomplete_journal,
                      "a competing retirement mutated external state or the journal")
                journal.write_bytes(complete_journal)
                fixture.env.pop("BWR_TEST_UPDATE_LOG")
            fixture.env.pop("BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER")
            resumed = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
            terminals = [
                entry for entry in fixture.journal()
                if entry.get("kind") == "attempt.succeeded"
                and entry.get("lot") == "lot-1" and entry.get("task") == 1
            ]
            check(len(terminals) == 1
                  and not (fixture.workspace / "attempt-success-in-progress.json").exists()
                  and not (fixture.workspace / "attempt-in-flight").exists()
                  and fixture.git(
                      "rev-parse", "refs/bwr/2026-08-19-demo/lot-1/task-1"
                  ).stdout.strip() == sha,
                  f"{phase}: {resumed.stdout} {resumed.stderr} {terminals}")
        finally:
            fixture.close()


@test
def task_success_serializes_two_exact_public_reruns():
    fixture = Fixture()
    first = second = None
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        barrier = fixture.temp / "attempt-success-barrier"
        barrier.mkdir()
        first_env = dict(fixture.env)
        first_env["BWR_TEST_ATTEMPT_SUCCESS_OWNER_BARRIER"] = str(barrier)
        command = ["bash", str(succeeded), "lot-1", "1", sha, op]
        first = subprocess.Popen(
            command, cwd=fixture.repo, env=first_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        ready = barrier / "owner.ready"
        for _ in range(1000):
            if ready.exists() or first.poll() is not None:
                break
            time.sleep(0.01)
        check(ready.exists(), "the first success call did not retain its owner lock")
        second = subprocess.Popen(
            command, cwd=fixture.repo, env=fixture.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.1)
        check(second.poll() is None, "the second success call bypassed the retained owner")
        (barrier / "owner.release").write_text("release\n", encoding="utf-8")
        first_stdout, first_stderr = first.communicate(timeout=30)
        second_stdout, second_stderr = second.communicate(timeout=30)
        terminals = [
            entry for entry in fixture.journal()
            if entry.get("kind") == "attempt.succeeded"
            and entry.get("lot") == "lot-1" and entry.get("task") == 1
        ]
        check(first.returncode == 0 and second.returncode == 0 and len(terminals) == 1
              and "already recorded" in second_stdout,
              f"first={first_stdout} {first_stderr}; second={second_stdout} {second_stderr}")
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()


@test
def task_success_reprojects_every_retained_owner_field_before_ref_publication():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.env["BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER"] = "owned"
        stopped = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
        check(stopped.returncode == 75, stopped.stdout + stopped.stderr)
        fixture.env.pop("BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER")
        marker_path = fixture.workspace / "attempt-success-in-progress.json"
        original = marker_path.read_bytes()
        stable_ref = "refs/bwr/2026-08-19-demo/lot-1/task-1"

        def changed_marker(label):
            marker = json.loads(original)
            owner = marker["owner"]
            if label == "stable_ref":
                owner["stable_ref"] = "refs/bwr/foreign/task-1"
            elif label == "started":
                owner["started"] = "0:" + "0" * 64
            elif label == "session":
                owner["session"] = "foreign-session"
            elif label == "start_account":
                owner["start_account"]["attempt_base_tree"] = "0" * 40
            elif label == "gate_account":
                owner["gate_account"]["opening"] = "0:" + "0" * 64
            elif label == "retry":
                owner["retry"] = "0:" + "0" * 64
            elif label == "phase":
                marker["phase"] = "ref-published"
            marker["owner_sha256"] = hashlib.sha256(json.dumps(
                owner, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode()).hexdigest()
            return (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()

        for label in (
            "stable_ref", "started", "session", "start_account",
            "gate_account", "retry", "phase",
        ):
            marker_path.write_bytes(changed_marker(label))
            refused = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
            check(refused.returncode != 0
                  and fixture.git("rev-parse", "--verify", "--quiet", stable_ref,
                                  ok=False).returncode == 1,
                  f"{label}: {refused.stdout} {refused.stderr}")
            marker_path.write_bytes(original)

        completed = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        check("task-1" in completed.stdout, completed.stdout + completed.stderr)
    finally:
        fixture.close()


@test
def task_success_refuses_same_byte_marker_substitution_before_each_phase_gesture():
    for boundary in ("ref-written", "terminal-written", "before-cleanup"):
        fixture = Fixture()
        try:
            fixture.prepare_task_candidate()
            op = fixture.open_task_gate()
            fixture.close_gate(op)
            sha = fixture.commit_task()
            succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
            fixture.env["BWR_TEST_ATTEMPT_SUCCESS_SUBSTITUTE_AFTER"] = boundary
            refused = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
            terminals = [
                entry for entry in fixture.journal()
                if entry.get("kind") == "attempt.succeeded"
            ]
            check("marker generation" in refused.stderr
                  and (fixture.workspace / "attempt-success-in-progress.json").is_file(),
                  f"{boundary}: {refused.stdout} {refused.stderr}")
            if boundary == "ref-written":
                check(not terminals, f"{boundary} appended a terminal")
            if boundary == "before-cleanup":
                check((fixture.workspace / "attempt-in-flight").is_file(),
                      "cleanup consumed attempt-in-flight after marker substitution")
        finally:
            fixture.close()


@test
def task_success_and_gate_open_share_one_physical_admission():
    fixture = Fixture()
    success = gate = None
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        barrier = fixture.temp / "success-gate-race"
        barrier.mkdir()
        success_env = dict(fixture.env)
        success_env["BWR_TEST_ATTEMPT_SUCCESS_PHYSICAL_BARRIER"] = str(barrier)
        success_env["BWR_TEST_ATTEMPT_SUCCESS_PHYSICAL_BOUNDARY"] = (
            "success-before-marker,success-marker-published"
        )
        success = subprocess.Popen(
            ["bash", str(succeeded), "lot-1", "1", sha, op], cwd=fixture.repo,
            env=success_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        ready = barrier / "success-before-marker.ready"
        for _ in range(1000):
            if ready.exists() or success.poll() is not None:
                break
            time.sleep(0.01)
        check(ready.exists(), "success did not retain physical admission")
        gate = subprocess.Popen(
            ["bash", str(fixture.gate_check), "open", "baseline", "race/success-first",
             "-", "0", "0", "HEAD"], cwd=fixture.repo, env=fixture.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.2)
        (barrier / "success-before-marker.release").write_text("release\n", encoding="utf-8")
        published = barrier / "success-marker-published.ready"
        for _ in range(1000):
            if published.exists() or success.poll() is not None:
                break
            time.sleep(0.01)
        check(published.exists(), "success did not publish its owner while gate waited")
        (barrier / "success-marker-published.release").write_text("release\n", encoding="utf-8")
        success_out, success_err = success.communicate(timeout=30)
        gate_out, gate_err = gate.communicate(timeout=30)
        check(success.returncode == 0 and gate.returncode != 0
              and not (fixture.workspace / "gate-check-in-progress").exists(),
              f"success={success_out} {success_err}; gate={gate_out} {gate_err}")

        journal = fixture.workspace / "progress.jsonl"
        complete = journal.read_bytes()
        incomplete = complete + b'{"incomplete"'
        journal.write_bytes(incomplete)
        refused = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", "race/incomplete-tail",
            "-", "0", "0", "HEAD", ok=False,
        )
        check(refused.returncode != 0 and journal.read_bytes() == incomplete
              and not (fixture.workspace / "gate-check-in-progress").exists(),
              refused.stdout + refused.stderr)
    finally:
        for process in (success, gate):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()

    fixture = Fixture()
    success = gate = None
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        barrier = fixture.temp / "gate-success-race"
        barrier.mkdir()
        gate_env = dict(fixture.env)
        gate_env["BWR_TEST_CONTROLLER_PHYSICAL_BARRIER"] = "gate-before-marker"
        gate_env["BWR_TEST_CONTROLLER_PHYSICAL_BARRIER_DIR"] = str(barrier)
        gate = subprocess.Popen(
            ["bash", str(fixture.gate_check), "open", "baseline", "race/gate-first",
             "-", "0", "0", "HEAD"], cwd=fixture.repo, env=gate_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        ready = barrier / "gate-before-marker.ready"
        for _ in range(1000):
            if ready.exists() or gate.poll() is not None:
                break
            time.sleep(0.01)
        check(ready.exists(), "gate did not retain physical admission")
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        success = subprocess.Popen(
            ["bash", str(succeeded), "lot-1", "1", sha, op], cwd=fixture.repo,
            env=fixture.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.2)
        check(success.poll() is None, "success bypassed gate physical admission")
        (barrier / "gate-before-marker.release").write_text("release\n", encoding="utf-8")
        gate_out, gate_err = gate.communicate(timeout=30)
        success_out, success_err = success.communicate(timeout=30)
        stable_ref = "refs/bwr/2026-08-19-demo/lot-1/task-1"
        check(gate.returncode == 0 and success.returncode != 0
              and (fixture.workspace / "gate-check-in-progress").is_file()
              and not (fixture.workspace / "attempt-success-in-progress.json").exists()
              and fixture.git("rev-parse", "--verify", "--quiet", stable_ref,
                              ok=False).returncode == 1,
              f"gate={gate_out} {gate_err}; success={success_out} {success_err}")
    finally:
        for process in (success, gate):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()


@test
def task_success_rejects_an_invented_document_copy_physical_descriptor():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.env["BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER"] = "owned"
        stopped = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
        check(stopped.returncode == 75, stopped.stdout + stopped.stderr)
        fixture.env.pop("BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER")

        marker = fixture.workspace / "attempt-success-in-progress.json"
        journal = fixture.workspace / "progress.jsonl"
        stable_ref = "refs/bwr/2026-08-19-demo/lot-1/task-1"
        destination_before = fixture.plan_copy.read_bytes()
        marker_before = marker.read_bytes()
        marker_identity = (marker.stat().st_dev, marker.stat().st_ino)
        journal_before = journal.read_bytes()
        head_before = fixture.git("rev-parse", "HEAD").stdout.strip()
        tree_before = fixture.git("rev-parse", "HEAD^{tree}").stdout.strip()
        index_before = fixture.git("write-tree").stdout.strip()
        status_before = fixture.git("status", "--porcelain=v1").stdout

        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8")
            .replace("Change the application value.", "Invented descriptor crossed the owner."),
            encoding="utf-8",
        )
        document_copy = fixture.workspace / "prompts" / "common" / "document-copy.sh"
        foreign_lock = fixture.temp / "foreign-physical-admission.lock"
        canonical_lock = fixture.workspace / "controller-physical-admission.lock"
        attempts = (
            (
                "closed",
                'export CONTROLLER_PHYSICAL_ADMISSION_FD=999; '
                'exec "$1" copy "$2" "$3" replace',
                [str(document_copy)],
            ),
            (
                "foreign",
                'exec 9>>"$1"; export CONTROLLER_PHYSICAL_ADMISSION_FD=9; '
                'exec "$2" copy "$3" "$4" replace',
                [str(foreign_lock), str(document_copy)],
            ),
            (
                "canonical-unlocked",
                'exec 9>>"$1"; export CONTROLLER_PHYSICAL_ADMISSION_FD=9; '
                'exec "$2" copy "$3" "$4" replace',
                [str(canonical_lock), str(document_copy)],
            ),
        )
        for label, script, arguments in attempts:
            command = [
                "bash", "-c", script, f"document-copy-{label}", *arguments,
                "plans/lot-1-plan.md",
                str(fixture.plan_copy.relative_to(fixture.repo)),
            ]
            refused = subprocess.run(
                command, cwd=fixture.repo, env=fixture.env,
                capture_output=True, text=True, timeout=60,
            )

            check(refused.returncode != 0
                  and marker.read_bytes() == marker_before
                  and (marker.stat().st_dev, marker.stat().st_ino) == marker_identity
                  and journal.read_bytes() == journal_before
                  and fixture.git("rev-parse", "--verify", "--quiet", stable_ref,
                                  ok=False).returncode == 1
                  and fixture.git("rev-parse", "HEAD").stdout.strip() == head_before
                  and fixture.git("rev-parse", "HEAD^{tree}").stdout.strip() == tree_before
                  and fixture.git("write-tree").stdout.strip() == index_before
                  and fixture.git("status", "--porcelain=v1").stdout == status_before
                  and fixture.plan_copy.read_bytes() == destination_before
                  and not (fixture.workspace / "document-copy-in-progress").exists(),
                  f"{label}: {refused.stdout}{refused.stderr}")
    finally:
        fixture.close()


@test
def task_success_historical_replay_binds_schema_two_start_session():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        journal = fixture.workspace / "progress.jsonl"
        rows = fixture.journal()
        start_index = next(index for index, entry in enumerate(rows)
                           if entry.get("event") == "session-started")
        terminal = next(entry for entry in rows if entry.get("kind") == "attempt.succeeded")
        rows[start_index]["session"] = "rewritten-session"
        recovery = terminal["data"]["success_recovery"]
        recovery["session"] = "rewritten-session"
        recovery["started"] = (
            f"{start_index}:" + hashlib.sha256(json.dumps(
                rows[start_index], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode()).hexdigest()
        )
        owner = dict(recovery)
        owner.pop("owner_sha256")
        recovery["owner_sha256"] = hashlib.sha256(json.dumps(
            owner, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()).hexdigest()
        journal.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in rows),
            encoding="utf-8",
        )
        replay = fixture.progress_call("construction-verdict-check", "history", ok=False)
        check("frozen attempt authority" in (replay.stdout + replay.stderr),
              replay.stdout + replay.stderr)
    finally:
        fixture.close()


@test
def task_success_does_not_replay_the_complete_construction_history_per_phase():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()

        helper = fixture.workspace / "prompts" / "construction" / "attempt_success.py"
        source = helper.read_text(encoding="utf-8")
        import_line = "import progress  # noqa: E402\n"
        check(source.count(import_line) == 1, "the task-success progress import changed")
        helper.write_text(
            source.replace(
                import_line,
                import_line
                + "\n"
                + "def forbid_complete_history_replay(_entries):\n"
                + "    raise RuntimeError('task success invoked the complete history replay')\n"
                + "progress.validate_construction_verdict_history = "
                + "forbid_complete_history_replay\n"
                + "\n",
            ),
            encoding="utf-8",
        )

        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        result = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        check("task-1" in result.stdout, result.stdout + result.stderr)
    finally:
        fixture.close()


@test
def task_success_legacy_ref_does_not_bypass_invalid_construction_history():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        stable_ref = "refs/bwr/2026-08-19-demo/lot-1/task-1"
        fixture.git("update-ref", stable_ref, sha)
        (fixture.workspace / "attempt-in-flight").unlink()

        journal = fixture.workspace / "progress.jsonl"
        malformed = {
            "session": "foreign-controller",
            "event": "note",
            "kind": "verdict.consumed",
            "lot": "lot-99",
            "task": 1,
            "data": {"check": "code"},
        }
        with journal.open("a", encoding="utf-8") as target:
            target.write(json.dumps(malformed, separators=(",", ":")) + "\n")
        journal_before = journal.read_bytes()

        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        result = fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
        terminals = [
            entry for entry in fixture.journal()
            if entry.get("kind") == "attempt.succeeded"
            and entry.get("lot") == "lot-1" and entry.get("task") == 1
        ]
        check(result.returncode != 0
              and not terminals
              and not (fixture.workspace / "attempt-success-in-progress.json").exists()
              and journal.read_bytes() == journal_before
              and fixture.git("rev-parse", stable_ref).stdout.strip() == sha,
              result.stdout + result.stderr)
    finally:
        fixture.close()


def prepare_accepted_first_task_in_two_task_plan(fixture):
    plan = (
        "# Plan\n\n## Task 1 - One\n"
        "Achieves: Change the application value.\n"
        "To verify: The changed value is covered.\n\n"
        "### Design\n"
        "[written at C3.1 - see below]\n\n"
        "## Task 2 - Two\n"
        "Achieves: Preserve the second contract.\n"
        "To verify: The second contract remains visible.\n\n"
        "### Design\n"
        "Task 2 Design placeholder.\n"
    )
    fixture.plan.write_text(plan, encoding="utf-8")
    fixture.plan_copy.write_text(plan, encoding="utf-8")
    fixture.git("add", str(fixture.plan_copy.relative_to(fixture.repo)))
    fixture.git("commit", "-q", "-m", "two-task plan")
    fixture.base = fixture.git("rev-parse", "HEAD").stdout.strip()
    fixture.prepare_task_candidate()
    op = fixture.open_task_gate()
    fixture.close_gate(op)
    sha = fixture.commit_task()
    succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
    fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
    return op, sha


@test
def historical_task_gate_ignores_later_task_design_and_disagreement():
    fixture = Fixture()
    try:
        op, sha = prepare_accepted_first_task_in_two_task_plan(fixture)
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").replace(
                "Task 2 Design placeholder.",
                "Design the second task without changing the accepted first task.",
            ).rstrip()
            + "\n\n### Disagreement\n#### Finding 1 — alternative\n"
            "The second task records its own later disagreement.\n",
            encoding="utf-8",
        )

        current = fixture.run("bash", fixture.gate_check, "require-current", ok=True)
        check(current.stdout.strip() == op, current.stdout + current.stderr)
        found = fixture.run(
            "bash", fixture.gate_check, "find-task", "lot-1", "1", "1", sha, ok=True,
        )
        check(found.stdout.strip() == op, found.stdout + found.stderr)
        passed = fixture.run("bash", fixture.gate_check, "require-pass", op, sha, ok=True)
        check(passed.stdout.split()[0] == "task", passed.stdout + passed.stderr)
    finally:
        fixture.close()


@test
def historical_task_gate_refuses_changed_proof_artifacts():
    fixture = Fixture()
    try:
        op, _ = prepare_accepted_first_task_in_two_task_plan(fixture)
        entries = fixture.journal()
        verdict = next(
            entry for entry in entries if entry.get("kind") == "verdict.consumed"
            and (entry.get("data") or {}).get("check") == "code"
        )
        manifest = fixture.workspace / verdict["data"]["manifest"]
        manifest_bytes = manifest.read_bytes()
        manifest.write_bytes(manifest_bytes + b"\n")
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        manifest.write_bytes(manifest_bytes)

        result = fixture.workspace / verdict["data"]["report"]
        result_bytes = result.read_bytes()
        result.write_bytes(result_bytes + b"\n")
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        result.write_bytes(result_bytes)

        journal = fixture.workspace / "progress.jsonl"
        journal_bytes = journal.read_bytes()
        rows = fixture.journal()
        changed = next(
            entry for entry in rows if entry.get("kind") == "verdict.consumed"
            and (entry.get("data") or {}).get("check") == "code"
        )
        changed["data"]["report_sha256"] = "0" * 64
        journal.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in rows),
            encoding="utf-8",
        )
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        journal.write_bytes(journal_bytes)

        journal_bytes = journal.read_bytes()
        rows = fixture.journal()
        gate_opening = next(
            entry for entry in rows if entry.get("event") == "subagent-started"
            and entry.get("kind") == "gate-runner"
            and (entry.get("data") or {}).get("op") == op
        )
        gate_opening["data"]["code"] = "0:" + "0" * 64
        journal.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in rows),
            encoding="utf-8",
        )
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        journal.write_bytes(journal_bytes)

        report = fixture.workspace / "reports" / "gate" / f"{op}.json"
        report_bytes = report.read_bytes()
        gate_report = json.loads(report_bytes)
        gate_report["tree"] = fixture.base
        report.write_text(json.dumps(gate_report, separators=(",", ":")), encoding="utf-8")
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        report.write_bytes(report_bytes)

        journal_bytes = journal.read_bytes()
        rows = fixture.journal()
        gate_terminal = next(
            entry for entry in rows if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "gate-runner"
            and (entry.get("data") or {}).get("op") == op
            and (entry.get("data") or {}).get("green") is True
        )
        gate_terminal["data"]["tree"] = fixture.base
        journal.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in rows),
            encoding="utf-8",
        )
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
        journal.write_bytes(journal_bytes)
    finally:
        fixture.close()


@test
def live_task_gate_still_rejects_a_changed_current_task_projection():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").replace(
                "Change app.txt and verify its observable result.",
                "Replace the current task Design after its final checker.",
            ),
            encoding="utf-8",
        )
        fixture.run(
            "bash", fixture.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=False,
        )
        check(not (fixture.workspace / "gate-check-in-progress").exists(),
              "a changed current task projection opened a final gate")
    finally:
        fixture.close()


@test
def task_gate_refuses_an_unproved_historical_code_verdict():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        entry = {
            "ts": "2026-08-19T00:00:00Z", "by": "implementer",
            "event": "note", "kind": "verdict.consumed",
            "lot": "lot-1", "task": 1, "attempt": 1, "round": 1,
            "data": {"check": "code", "outcome": "clean"},
        }
        (fixture.workspace / "progress.jsonl").write_text(
            json.dumps(entry, separators=(",", ":")) + "\n", encoding="utf-8",
        )
        (fixture.repo / "app.txt").write_text("candidate without a checker\n", encoding="utf-8")
        design = "# Plan\n\n## Task 1 - One\n\n### Design\n\nDo it.\n"
        fixture.plan.write_text(design, encoding="utf-8")
        fixture.plan_copy.write_text(design, encoding="utf-8")
        fixture.git("add", "app.txt", str(fixture.plan_copy.relative_to(fixture.repo)))
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=False,
        )
        check("latest code review" in opened.stderr, opened.stdout + opened.stderr)
        check(not (fixture.workspace / "gate-check-in-progress").exists(),
              "an unproved code verdict opened a gate operation")
    finally:
        fixture.close()


@test
def round_ten_resolution_without_an_accepted_defect_can_finish_the_task():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_code_round_ten_findings()

        fixture.run(
            "bash", fixture.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=False,
        )
        fixture.resolve_code_round_ten(["refuted", "alternative"])
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        sha = fixture.commit_task()
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=True)
        stable = fixture.git(
            "rev-parse", "refs/bwr/2026-08-19-demo/lot-1/task-1"
        ).stdout.strip()
        check(stable == sha, "the resolved round-ten candidate did not publish its stable ref")
        current = fixture.run("bash", fixture.gate_check, "require-current", ok=True)
        check(current.stdout.strip() == op,
              "the resolved round-ten task gate could not replay its historical code proof")
    finally:
        fixture.close()


@test
def an_accepted_round_ten_defect_refuses_the_final_gate_before_mutation():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_code_round_ten_findings(findings=1)
        fixture.resolve_code_round_ten(["accepted"])
        (fixture.repo / "app.txt").write_text("defective candidate\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        before = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        fixture.run(
            "bash", fixture.gate_check, "open", "task", "lot-1/task-1/attempt-1",
            "lot-1", "1", "1", "refs/bwr/2026-08-19-demo/lot-1/attempt-base", ok=False,
        )
        check((fixture.workspace / "progress.jsonl").read_text(encoding="utf-8") == before,
              "an accepted final defect changed the journal while refusing the gate")
        check(not (fixture.workspace / "gate-check-in-progress").exists(),
              "an accepted final defect published a gate owner")
    finally:
        fixture.close()


@test
def failure_closer_refuses_unsettled_round_ten_findings_before_mutation():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_code_round_ten_findings(findings=1)
        before_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        before_identity = (fixture.workspace / "attempt-in-flight").read_bytes()
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9a", ok=False)
        check(fixture.git("rev-parse", "HEAD").stdout.strip() == before_head,
              "the failure closer moved HEAD before the round-ten batch was settled")
        check((fixture.workspace / "attempt-in-flight").read_bytes() == before_identity,
              "the failure closer bound or removed the attempt before settlement")
        fixture.git(
            "rev-parse", "--verify",
            "refs/bwr/2026-08-19-demo/lot-1/task-1-try-1", ok=False,
        )
        check(not any(entry.get("kind") == "attempt.failed" for entry in fixture.journal()),
              "the unresolved final batch gained a failure terminal")
    finally:
        fixture.close()


@test
def final_design_contract_blocker_uses_the_real_plan_fault_closer():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_design_round_ten_contract_blocker()
        plan = fixture.plan.read_text(encoding="utf-8")
        fixture.plan.write_text(
            plan.replace(
                "Achieves: Change the application value.",
                "Achieves: Change the application value and preserve the parent outcome.",
                1,
            ),
            encoding="utf-8",
        )
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9b", ok=True)
        terminal = next(
            entry for entry in reversed(fixture.journal())
            if entry.get("kind") == "attempt.failed"
        )
        review = terminal["data"]["design_review"]
        check("report" not in terminal["data"], terminal)
        check(review["contract_blocked"] == [1], review)
        check(review["required"] == [1, 2], review)
        retry = fixture.progress_call(
            "construction-retry-check", "lot-1", "1", "-", ok=True,
        )
        proof = retry.stdout.strip()
        check(proof != "-", "the plan-fault closer lost its Design obligation")

        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"
        fixture.run(
            "bash", plan_commit, "lot-1", "fix: correct the task contract", ok=True,
        )
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        predecessor = fixture.git("rev-parse", "HEAD^").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{head}",
            "-", "0", "0", predecessor, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)

        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "2", "-", ok=True)
        identity = (fixture.workspace / "attempt-in-flight").read_text(encoding="utf-8")
        check(f"retry {proof}" in identity, identity)
        fixture.set_attempt_context(2)
        fixture.plan.write_text(
            re.sub(
                r"(?ms)^### Design\n.*?(?=^### |^## Task |\Z)",
                "### Design\nDesign against the corrected controller-owned contract.\n",
                fixture.plan.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        design = fixture.progress_call(
            "subagent-started", "design-checker", "--round", "1", ok=True,
        )
        manifest = json.loads(
            (fixture.workspace / json.loads(design.stdout)["manifest"]).read_text(
                encoding="utf-8"
            )
        )
        check(manifest["previous"]["failure"] == proof, manifest["previous"])
        check(
            [item["status"] for item in manifest["previous"]["resolution"]]
            == ["contract-blocked", "carried"],
            manifest["previous"],
        )

    finally:
        fixture.close()


@test
def early_design_contract_blocker_uses_the_real_plan_fault_closer():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_design_contract_blocker(1)
        fixture.progress_call(
            "subagent-started", "design-checker", "--round", "2", ok=False,
        )
        plan = fixture.plan.read_text(encoding="utf-8")
        fixture.plan.write_text(
            plan.replace(
                "Achieves: Change the application value.",
                "Achieves: Change the application value and preserve the parent outcome.",
                1,
            ),
            encoding="utf-8",
        )
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9b", ok=True)
        terminal = next(
            entry for entry in reversed(fixture.journal())
            if entry.get("kind") == "attempt.failed"
        )
        review = terminal["data"]["design_review"]
        check(review["contract_blocked"] == [1], review)
        check(review["required"] == [1, 2], review)
        proof = fixture.progress_call(
            "construction-retry-check", "lot-1", "1", "-", ok=True,
        ).stdout.strip()
        check(proof != "-", "the early plan-fault closer lost its Design obligation")

        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"
        fixture.run(
            "bash", plan_commit, "lot-1", "fix: correct the early task contract", ok=True,
        )
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        predecessor = fixture.git("rev-parse", "HEAD^").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{head}",
            "-", "0", "0", predecessor, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)

        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "2", "-", ok=True)
        fixture.set_attempt_context(2)
        fixture.plan.write_text(
            re.sub(
                r"(?ms)^### Design\n.*?(?=^### |^## Task |\Z)",
                "### Design\nDesign against the corrected early contract.\n",
                fixture.plan.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        design = fixture.progress_call(
            "subagent-started", "design-checker", "--round", "1", ok=True,
        )
        manifest = json.loads(
            (fixture.workspace / json.loads(design.stdout)["manifest"]).read_text(
                encoding="utf-8"
            )
        )
        check(manifest["previous"]["failure"] == proof, manifest["previous"])
        check(
            [item["status"] for item in manifest["previous"]["resolution"]]
            == ["contract-blocked", "carried"],
            manifest["previous"],
        )
    finally:
        fixture.close()


@test
def intermediate_code_contract_blocker_reaches_the_corrected_plan_retry():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.run_code_round(1, 1)
        fixture.run_code_round(2, 2)

        account = fixture.temp / "code-contract-blocker.md"
        account.write_text(
            "## Finding 1 — contract-blocked\n"
            "The required production test is outside the frozen Files account.\n\n"
            "## Finding 2 — carried\n"
            "The replacement attempt must still prove this implementation finding.\n",
            encoding="utf-8",
        )
        fixture.progress_call(
            "note", "code.review.blocked", "--round", "2",
            "--data", json.dumps({
                "check": "code",
                "items": [
                    {"id": 1, "status": "contract-blocked"},
                    {"id": 2, "status": "carried"},
                ],
            }),
            "--text-file", account,
            ok=True,
        )
        fixture.progress_call(
            "note", "code.review.resolved", "--round", "2",
            "--data", json.dumps({
                "check": "code",
                "items": [
                    {"id": 1, "status": "unchanged"},
                    {"id": 2, "status": "corrected"},
                ],
            }),
            "--text-file", account,
            ok=False,
        )
        fixture.progress_call(
            "construction-failure-check", "lot-1", "1", "1", "C3.9a", ok=False,
        )

        plan = fixture.plan.read_text(encoding="utf-8")
        fixture.plan.write_text(
            plan.replace(
                "To verify: The changed value is covered.",
                "Files: app.txt, migration-test.txt\n"
                "To verify: The changed value and migration path are covered.",
                1,
            ),
            encoding="utf-8",
        )
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9b", ok=True)
        failure_index, failure = next(
            (index, entry) for index, entry in reversed(list(enumerate(fixture.journal())))
            if entry.get("kind") == "attempt.failed"
        )
        code_review = failure["data"]["code_review"]
        check("report" not in failure["data"], failure)
        check(code_review["contract_blocked"] == [1], code_review)
        check(code_review["required"] == [1, 2], code_review)
        raw_lines = (fixture.workspace / "progress.jsonl").read_bytes().splitlines()
        failure_proof = f"{failure_index}:{hashlib.sha256(raw_lines[failure_index]).hexdigest()}"

        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"
        fixture.run(
            "bash", plan_commit, "lot-1", "fix: extend the task write set", ok=True,
        )
        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        predecessor = fixture.git("rev-parse", "HEAD^").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{head}",
            "-", "0", "0", predecessor, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)

        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "2", "-", ok=True)
        identity = (fixture.workspace / "attempt-in-flight").read_text(encoding="utf-8")
        check(f"retry {failure_proof}" in identity, identity)
        fixture.set_attempt_context(2)
        fixture.run_code_round(1, 0)
        opening = next(
            entry for entry in reversed(fixture.journal())
            if entry.get("event") == "subagent-started"
            and entry.get("kind") == "code-checker" and entry.get("attempt") == 2
        )
        manifest = json.loads(
            (fixture.workspace / opening["data"]["manifest"]).read_text(encoding="utf-8")
        )
        check(manifest["previous"]["failure"] == failure_proof, manifest["previous"])
        check(
            [item["status"] for item in manifest["previous"]["resolution"]]
            == ["contract-blocked", "carried"],
            manifest["previous"],
        )

        journal = fixture.journal()
        blocker = next(entry for entry in journal if entry.get("kind") == "code.review.blocked")
        blocker["data"]["contract_blocked"] = []
        with (fixture.workspace / "progress.jsonl").open("w", encoding="utf-8") as target:
            for entry in journal:
                target.write(json.dumps(entry, separators=(",", ":")) + "\n")
        fixture.progress_call("construction-verdict-check", "history", ok=False)
    finally:
        fixture.close()


@test
def accepted_round_ten_defect_requires_its_exact_failure_handoff():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_code_round_ten_findings(findings=1)
        fixture.resolve_code_round_ten(["accepted"])
        before_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        before_identity = (fixture.workspace / "attempt-in-flight").read_bytes()
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9a", ok=False)
        check(fixture.git("rev-parse", "HEAD").stdout.strip() == before_head,
              "the failure closer moved HEAD without the accepted-defect artifact")
        check((fixture.workspace / "attempt-in-flight").read_bytes() == before_identity,
              "the failure closer bound the attempt without the accepted-defect artifact")
        check(not any(entry.get("kind") == "attempt.failed" for entry in fixture.journal()),
              "an accepted defect gained an unbound failure terminal")
    finally:
        fixture.close()


@test
def accepted_round_ten_handoff_is_bound_to_the_next_checker_generation():
    fixture = Fixture()
    try:
        fixture.start_attempt_state()
        fixture.append_code_round_ten_findings(findings=2)
        fixture.resolve_code_round_ten(["accepted", "refuted"])
        handoff = fixture.progress_call(
            "construction-failure-handoff", "lot-1", "1", "1",
        ).stdout
        report_relative = "reports/construction/lot-1-task-1-try-1.md"
        report = fixture.workspace / report_relative
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# Failed attempt\n\n"
            "## What failed\nThe final checker found one accepted defect.\n\n"
            "## Classification\nC3.9a — the accepted Design needs a fresh implementation.\n\n"
            "## Evidence read\nThe exact round-10 checker result and resolution.\n\n"
            + handoff,
            encoding="utf-8",
        )
        failed = fixture.workspace / "prompts" / "construction" / "attempt-failed.sh"
        fixture.run("bash", failed, "lot-1", "1", "1", "C3.9a", ok=True)
        terminal_index, terminal = next(
            (index, entry) for index, entry in reversed(list(enumerate(fixture.journal())))
            if entry.get("kind") == "attempt.failed"
        )
        terminal_data = terminal["data"]
        check(terminal_data["code_review"]["accepted"] == [1], terminal_data)
        check(terminal_data["report"] == report_relative and terminal_data["report_sha256"],
              terminal_data)
        raw_lines = (fixture.workspace / "progress.jsonl").read_bytes().splitlines()
        failure_proof = f"{terminal_index}:{hashlib.sha256(raw_lines[terminal_index]).hexdigest()}"

        head = fixture.git("rev-parse", "HEAD").stdout.strip()
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{head}",
            "-", "0", "0", head, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.write_gate_report(op)
        fixture.close_gate(op)

        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "2", ok=False)
        fixture.run("bash", started, "lot-1", "1", "2", report_relative, ok=True)
        identity = (fixture.workspace / "attempt-in-flight").read_text(encoding="utf-8")
        check(f"retry {failure_proof}" in identity,
              "the next attempt identity does not freeze the accepted-defect handoff")

        fixture.set_attempt_context(2)
        fixture.run_code_round(1, 0)
        opening = next(
            entry for entry in reversed(fixture.journal())
            if entry.get("event") == "subagent-started"
            and entry.get("kind") == "code-checker" and entry.get("attempt") == 2
        )
        manifest = json.loads(
            (fixture.workspace / opening["data"]["manifest"]).read_text(encoding="utf-8")
        )
        check(manifest["previous"]["source"] == "retry", manifest["previous"])
        check(manifest["previous"]["failure"] == failure_proof, manifest["previous"])
        check([item["id"] for item in manifest["previous"]["findings"]] == [1],
              "the next checker did not receive the exact accepted finding")
        check(manifest["previous"]["findings"][0]["impact"] == "IMPORTANT",
              "the accepted finding lost its public impact during retry handoff")

        fixture.run("bash", failed, "lot-1", "1", "2", "C3.9a", ok=True)
        propagated = next(
            entry for entry in reversed(fixture.journal())
            if entry.get("kind") == "attempt.failed" and entry.get("task") == 1
        )
        check(propagated["data"]["retry"] == failure_proof,
              "another failed retry dropped the accepted-defect obligation")
        fixture.run("bash", started, "lot-1", "1", "3", ok=False)
        fixture.run("bash", started, "lot-1", "1", "3", report_relative, ok=True)

        report.write_text(report.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        fixture.progress_call("construction-verdict-check", "history", ok=False)
    finally:
        fixture.close()


@test
def attempt_start_refuses_damaged_historical_construction_verdicts():
    fixture = Fixture()
    try:
        run = "refs/bwr/2026-08-19-demo/lot-1"
        fixture.git("update-ref", f"{run}/task-0", fixture.base)
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{fixture.base}",
            "-", "0", "0", fixture.base, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)
        entry = {
            "ts": "2026-08-19T00:00:00Z", "by": "implementer",
            "event": "note", "kind": "verdict.consumed",
            "lot": "lot-1", "task": 1, "attempt": 1, "round": 1,
            "data": {"check": "design", "outcome": "clean"},
        }
        with (fixture.workspace / "progress.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "1", ok=False)
        check(not (fixture.workspace / "attempt-in-flight").exists(),
              "a new attempt replaced damaged verdict history")
        fixture.git("rev-parse", "--verify", f"{run}/attempt-base", ok=False)
    finally:
        fixture.close()


@test
def successful_commit_hook_cannot_publish_a_task_ref():
    fixture = Fixture()
    try:
        fixture.prepare_task_candidate()
        op = fixture.open_task_gate()
        fixture.close_gate(op)
        hook = fixture.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nprintf 'hook byte\\n' >> app.txt\ngit add app.txt\n", encoding="utf-8")
        hook.chmod(0o755)
        sha = fixture.commit_task("hook-mutated task")
        succeeded = fixture.workspace / "prompts" / "construction" / "attempt-succeeded.sh"
        fixture.run("bash", succeeded, "lot-1", "1", sha, op, ok=False)
        fixture.git("rev-parse", "--verify", "refs/bwr/2026-08-19-demo/lot-1/task-1", ok=False)
    finally:
        fixture.close()


@test
def current_baseline_starts_work_but_cannot_stand_in_for_a_built_task_pass():
    fixture = Fixture()
    try:
        run = "refs/bwr/2026-08-19-demo/lot-1"
        fixture.git("update-ref", f"{run}/task-0", fixture.base)
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        fixture.run("bash", started, "lot-1", "1", "1", ok=False)
        check(not (fixture.workspace / "attempt-in-flight").exists(), "a start without gate proof wrote identity")
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{fixture.base}",
            "-", "0", "0", fixture.base, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)
        fixture.run("bash", started, "lot-1", "1", "1", ok=True)

        before = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        fixture.progress_call(
            "note", "pass.opened", "--data",
            json.dumps({"built": "lot-1", "commit": fixture.base, "gate": "0" * 64}), ok=False,
        )
        check((fixture.workspace / "progress.jsonl").read_text(encoding="utf-8") == before,
              "a pass with a false gate proof was appended")
        before = (fixture.workspace / "progress.jsonl").read_text(encoding="utf-8")
        fixture.progress_call(
            "note", "pass.opened", "--data",
            json.dumps({"built": "lot-1", "commit": fixture.base, "gate": op}), ok=False,
        )
        check((fixture.workspace / "progress.jsonl").read_text(encoding="utf-8") == before,
              "a controller baseline opened the first product pass without a built task")
        (fixture.repo / "spec.md").write_text("# Spec\n\nchanged during review\n", encoding="utf-8")
        fixture.git("add", "spec.md")
        fixture.run("git", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "review spec edit", ok=True)
        fixture.run("bash", fixture.gate_check, "require-current", ok=False)
    finally:
        fixture.close()


@test
def plan_commit_refuses_when_any_task_lacks_a_design_boundary():
    fixture = Fixture()
    try:
        fixture.plan.write_text(
            "# Plan\n\n"
            "## Task 1 - One\n"
            "Achieves: Change the application value.\n"
            "To verify: The changed value is covered.\n\n"
            "### Design\n"
            "[written at C3.1 - see below]\n\n"
            "## Task 2 - Two\n"
            "Achieves: Preserve the application value.\n"
            "To verify: The preserved value is covered.\n\n"
            "```markdown\n"
            "### Design\n"
            "This is illustrative data, not the ownership boundary.\n"
            "```\n",
            encoding="utf-8",
        )
        original_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        original_copy = fixture.plan_copy.read_bytes()
        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"

        result = fixture.run("bash", plan_commit, "lot-1", "invalid plan", ok=False)

        check("Task 2" in result.stderr and "### Design" in result.stderr, result.stderr)
        check(fixture.git("rev-parse", "HEAD").stdout.strip() == original_head,
              "a plan without every Design boundary created a commit")
        check(fixture.plan_copy.read_bytes() == original_copy,
              "a refused plan changed the repository copy")
        check(not (fixture.workspace / "plan-commit-in-progress").exists(),
              "a refused plan created a commit marker")
        check(not (fixture.workspace / "progress.jsonl").exists(),
              "a refused plan wrote the journal")
    finally:
        fixture.close()


@test
def construction_entry_refuses_a_sublot_without_its_opening_terminal():
    fixture = Fixture()
    try:
        original_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        original_copy = fixture.plan_copy.read_bytes()
        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"

        refused_plan = fixture.run(
            "bash", plan_commit, "lot-1.1", "invalid sub-lot entry", ok=False,
        )
        check("sub-lot" in refused_plan.stderr and "sublot.opened" in refused_plan.stderr,
              refused_plan.stderr)
        check(fixture.git("rev-parse", "HEAD").stdout.strip() == original_head,
              "a sub-lot without an opening created a plan commit")
        check(fixture.plan_copy.read_bytes() == original_copy,
              "a refused sub-lot entry changed the repository plan copy")
        check(not (fixture.workspace / "plan-commit-in-progress").exists(),
              "a refused sub-lot entry created a plan marker")

        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"
        refused_attempt = fixture.run("bash", started, "lot-1.1", "1", "1", ok=False)
        check("sub-lot" in refused_attempt.stderr and "sublot.opened" in refused_attempt.stderr,
              refused_attempt.stderr)
        check(not (fixture.workspace / "attempt-in-flight").exists(),
              "a sub-lot without an opening created an attempt identity")
    finally:
        fixture.close()


@test
def attempt_start_refuses_a_committed_task_without_a_design_boundary():
    fixture = Fixture()
    try:
        missing = (
            "# Plan\n\n## Task 1 - One\n"
            "Achieves: Change the application value.\n"
            "To verify: The changed value is covered.\n"
        )
        fixture.plan.write_text(missing, encoding="utf-8")
        fixture.plan_copy.write_text(missing, encoding="utf-8")
        fixture.git("add", str(fixture.plan_copy.relative_to(fixture.repo)))
        fixture.git("commit", "-q", "-m", "legacy plan without Design boundary")
        fixture.base = fixture.git("rev-parse", "HEAD").stdout.strip()
        fixture.git("update-ref", "refs/bwr/2026-08-19-demo/lot-1/task-0", fixture.base)
        opened = fixture.run(
            "bash", fixture.gate_check, "open", "baseline", f"plan/lot-1/{fixture.base}",
            "-", "0", "0", fixture.base, ok=True,
        )
        op = re.search(r"^OP ([0-9a-f]{64})$", opened.stdout, re.MULTILINE).group(1)
        fixture.close_gate(op)
        started = fixture.workspace / "prompts" / "construction" / "attempt-started.sh"

        result = fixture.run("bash", started, "lot-1", "1", "1", ok=False)

        check("### Design" in result.stderr, result.stderr)
        check(not (fixture.workspace / "attempt-in-flight").exists(),
              "a task without a Design boundary created an attempt identity")
    finally:
        fixture.close()


@test
def controller_document_commits_bypass_mutating_project_hooks():
    fixture = Fixture()
    try:
        hook = fixture.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nprintf hook-ran >> hook.log\nexit 77\n", encoding="utf-8")
        hook.chmod(0o755)

        fixture.plan.write_text(
            "# Plan\n\n## Task 1 - One\n\ncontroller\n\n"
            "### Design\n[written at C3.1 - see below]\n",
            encoding="utf-8",
        )
        plan_commit = fixture.workspace / "prompts" / "construction" / "plan-commit.sh"
        fixture.run("bash", plan_commit, "lot-1", "plan update", ok=True)

        fixture.seed_clean_spec_close()
        spec_commit = fixture.workspace / "prompts" / "common" / "spec-commit.sh"
        fixture.run("bash", spec_commit, "spec.md", "spec update", "-", ok=True)

        amendment = fixture.workspace / "amendments" / "1.md"
        amendment.parent.mkdir(parents=True)
        amendment.write_text("# Amendment 1\n", encoding="utf-8")
        (fixture.repo / "spec.md").write_text("# Spec\n\namended\n", encoding="utf-8")
        amendment_commit = fixture.workspace / "prompts" / "amendment" / "amendment-commit.sh"
        # This test isolates hook handling. test_progress.py exercises the real
        # amendment admission and retry end to end. Replace only that admission
        # boundary here, then restore the real journal tool before rewind.
        real_progress = fixture.progress.with_name("progress-real.py")
        fixture.progress.rename(real_progress)
        fixture.progress.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if sys.argv[1] == 'amendment-close-check':\n"
            "    print('a' * 64)\n"
            "    print('b' * 64)\n"
            "    print('c' * 64)\n"
            "    print('1')\n"
            "    print('d' * 64)\n"
            "    print('1')\n"
            "    print('e' * 64)\n"
            "    print('f' * 64)\n"
            "elif sys.argv[1:3] == ['note', 'amendment.committed']:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(64)\n",
            encoding="utf-8",
        )
        fixture.progress.chmod(0o755)
        try:
            fixture.run("bash", amendment_commit, "1", "spec.md", "amendment", "-", ok=True)
        finally:
            fixture.progress.unlink()
            real_progress.rename(fixture.progress)

        (fixture.repo / "app.txt").write_text("validated task\n", encoding="utf-8")
        fixture.git("add", "app.txt")
        fixture.run("git", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "task", ok=True)
        task_sha = fixture.git("rev-parse", "HEAD").stdout.strip()
        fixture.git("update-ref", "refs/bwr/2026-08-19-demo/lot-1/task-1", task_sha)
        (fixture.repo / "controller.txt").write_text("keep through rewind\n", encoding="utf-8")
        fixture.git("add", "controller.txt")
        fixture.run("git", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "controller", ok=True)
        rewind = fixture.workspace / "prompts" / "construction" / "rewind.sh"
        fixture.run("bash", rewind, "lot-1", "1", "1", "re-land controller state", ok=True)
        check((fixture.repo / "controller.txt").read_text(encoding="utf-8") == "keep through rewind\n",
              "rewind did not restore the controller payload")
        check(not (fixture.repo / "hook.log").exists(), "a controller document commit ran the project hook")
    finally:
        fixture.close()


@test
def gate_runner_contract_covers_real_gate_and_semantic_surface_drift():
    prompt = (HERE / "prompts" / "construction" / "gate-runner.md").read_text(encoding="utf-8")
    for required in (
        "Never accept a copied command list",
        "definition-change candidate",
        "uncovered-target candidate",
        "gate_execution.py run <op>",
        "semantically admitted compatible group",
        "continues after a RED",
        "canonical report",
        "operation: <op>",
        "gate-check.sh runner-input <op>",
        "gate-check.sh publish-report <op>",
        "contains no operation, gate, tree, execution, account, command or status",
        "full-line comment",
        "not a machine exemption",
    ):
        check(required in prompt, f"gate-runner contract lost: {required}")


@test
def code_checker_contract_repairs_invalid_results_before_regeneration():
    implementer = (HERE / "prompts" / "construction" / "implementer.md").read_text(
        encoding="utf-8"
    )
    mode = (HERE / "prompts" / "construction" / "MODE.md").read_text(encoding="utf-8")
    skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
    implementer_contract = " ".join(implementer.replace("**", "").split()).lower()
    mode_contract = " ".join(mode.replace("**", "").split()).lower()
    skill_contract = " ".join(skill.replace("**", "").split()).lower()
    for required in (
        "same open physical call",
        "complete replacement json",
        "at most two repair requests",
        "same exact refusal",
        "no second `bound.spent`",
    ):
        check(required in implementer_contract,
              f"implementer lost code-result repair rule: {required}")
        check(required in mode_contract,
              f"construction mode lost code-result repair rule: {required}")
    for required in (
        "live repair context",
        "after compaction",
        '`{"unusable":"lost"}`',
        "close the exact open call before regeneration",
    ):
        check(required in implementer_contract,
              f"implementer lost live-only repair resume rule: {required}")
        check(required in mode_contract,
              f"construction mode lost live-only repair resume rule: {required}")
        check(required in skill_contract,
              f"root skill lost live-only repair resume rule: {required}")


def main():
    selected = TESTS
    test_filter = os.environ.get("BWR_TEST_FILTER")
    if test_filter:
        selected = [function for function in TESTS if test_filter in function.__name__]
        if not selected:
            raise SystemExit(f"no test matches BWR_TEST_FILTER={test_filter!r}")
    failures = 0
    for function in selected:
        try:
            function()
        except Exception:
            failures += 1
            print(f"FAIL  {function.__name__}")
            traceback.print_exc()
            print()
        else:
            print(f"ok    {function.__name__}")
    print()
    if failures:
        print(f"{failures} of {len(selected)} tests FAILED")
        raise SystemExit(1)
    print(f"all {len(selected)} tests passed")


if __name__ == "__main__":
    main()
