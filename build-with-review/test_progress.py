#!/usr/bin/env python3
"""Tests for progress.py — standard library only, no pytest.

THIS FILE IS NOT PART OF THE WORKFLOW. It is a development tool, which is why
it sits at the root of the skill and not under prompts/: nothing here runs
during a feature, and it is never copied into a workspace. No agent reads it.

Run: python3 test_progress.py — exits non-zero and says what failed.

Everything runs against a throwaway workspace under a temp directory: the
script under test is COPIED there (its workspace is derived from its own
location), and the `twicc` CLI is a fake pointed at by TWICC_BIN. The fake
returns canned JSON for `whoami` and `session <id>`, records every call it
receives so order can be asserted, and fails on demand. No real TwiCC
instance and no file of this repository is ever touched.
"""
import hashlib
import importlib.util
import json
import multiprocessing
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "prompts", "common", "progress.py")
AUTHORITY_SOURCE = os.path.join(HERE, "prompts", "common", "authority_precedence.py")
SPEC_EDIT_SOURCE = os.path.join(HERE, "prompts", "common", "spec_edit_auth.py")
SPEC_PROMPTS = os.path.join(HERE, "prompts", "spec")
PRODUCT_PROMPTS = os.path.join(HERE, "prompts", "product-review")
AMENDMENT_PROMPTS = os.path.join(HERE, "prompts", "amendment")
COMMON_PROMPTS = os.path.join(HERE, "prompts", "common")

CALLER = "caller-session-00000000-0000-0000-0000-000000000001"
TARGET = "target-session-00000000-0000-0000-0000-000000000002"

# The caller and the target carry DIFFERENT annotation sets on purpose: every
# context assertion below also proves which side the context was derived from.
CALLER_BWR = {"schema": 1, "job": "controller", "mode": "construction",
              "feature": "demo-feature", "lot": "lot-1", "task": 3,
              "attempt": 2, "status": "working"}
TARGET_BWR = {"schema": 1, "job": "reviewer", "mode": "spec",
              "feature": "demo-feature", "mandate": "verifier", "round": 2,
              "status": "working"}

# A raw string: the "\n" below must land literally in the generated fake.
FAKE_TWICC = r'''#!/usr/bin/env python3
import json, os, sys
base = os.environ["FAKE_TWICC_DIR"]
args = sys.argv[1:]
with open(os.path.join(base, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\n")
with open(os.path.join(base, "config.json")) as f:
    cfg = json.load(f)
for pattern in cfg.get("fail", []):
    if args[: len(pattern)] == pattern:
        print("simulated CLI failure", file=sys.stderr)
        sys.exit(4)
for pattern in cfg.get("garbage", []):
    if args[: len(pattern)] == pattern:
        print("this is not json")
        sys.exit(0)
if args[0] == "whoami":
    print(json.dumps(cfg["whoami"]))
    sys.exit(0)
if args[0] == "session":
    payload = cfg["sessions"].get(args[1])
    if payload is None:
        print("session not found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(payload))
    sys.exit(0)
if args[0] == "update-session":
    print(json.dumps({"status": "updated", "session_id": args[1]}))
    sys.exit(0)
print("unexpected command: " + " ".join(args), file=sys.stderr)
sys.exit(64)
'''

# Globals filled by main() once the temp layout exists.
BASE = REPO = WORKSPACE = SCRIPT = FAKE_DIR = ENV = None

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------- harness

def default_config():
    return {
        "whoami": {"session_id": CALLER,
                   "session": {"id": CALLER, "annotations": {"bwr": dict(CALLER_BWR)}}},
        "sessions": {
            CALLER: {"id": CALLER, "annotations": {"bwr": dict(CALLER_BWR)}},
            TARGET: {"id": TARGET, "annotations": {"bwr": dict(TARGET_BWR)}},
        },
        "fail": [],
    }


def set_config(cfg):
    with open(os.path.join(FAKE_DIR, "config.json"), "w") as f:
        json.dump(cfg, f)


def reset():
    for path in (os.path.join(FAKE_DIR, "calls.jsonl"),
                 os.path.join(WORKSPACE, "progress.jsonl"),
                 os.path.join(WORKSPACE, "progress.jsonl.lock"),
                 os.path.join(REPO, "fixture-code-review.txt")):
        if os.path.exists(path):
            os.remove(path)
    shutil.rmtree(os.path.join(WORKSPACE, "dashboard"), ignore_errors=True)
    shutil.rmtree(os.path.join(WORKSPACE, "reports"), ignore_errors=True)
    shutil.rmtree(os.path.join(WORKSPACE, "plans"), ignore_errors=True)
    shutil.rmtree(os.path.join(WORKSPACE, "amendments"), ignore_errors=True)
    for marker in (
        "amendment-commit-in-progress", "document-copy-in-progress", "attempt-in-flight",
    ):
        path = os.path.join(WORKSPACE, marker)
        if os.path.lexists(path):
            os.remove(path)
    shutil.rmtree(os.path.join(REPO, "docs"), ignore_errors=True)
    shutil.rmtree(os.path.join(REPO, ".git"), ignore_errors=True)
    subprocess.run(["git", "init", "-q", REPO], check=True)
    subprocess.run(["git", "-C", REPO, "config", "user.name", "Progress Test"], check=True)
    subprocess.run(["git", "-C", REPO, "config", "user.email", "progress@example.test"], check=True)
    set_config(default_config())


def run_progress(*args, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, env=env or ENV, timeout=120)


def load_common_module(name):
    common = os.path.join(WORKSPACE, "prompts", "common")
    path = os.path.join(common, f"{name}.py")
    sys.path.insert(0, common)
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_{os.getpid()}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(common)


def journal_lines():
    path = os.path.join(WORKSPACE, "progress.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                out.append(json.loads(raw))  # a torn line raises: that IS a failure
    return out


def cli_calls():
    path = os.path.join(FAKE_DIR, "calls.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(raw) for raw in f if raw.strip()]


def mutations():
    return [c for c in cli_calls() if c and c[0] == "update-session"]


def the_line(proc):
    check(proc.returncode == 0, f"expected success, got {proc.returncode}:\n{proc.stdout}{proc.stderr}")
    lines = journal_lines()
    check(len(lines) == 1, f"expected exactly 1 journal line, got {len(lines)}")
    return lines[0]


def refused(proc):
    check(proc.returncode != 0, "the call should have been refused")
    check(journal_lines() == [], "a refused call must journal nothing")


def refused_after(proc, before, subject):
    check(proc.returncode != 0, f"{subject} should have been refused")
    check(len(journal_lines()) == before, f"{subject} appended a journal event")


def append_note(kind, data=None, text=None, mandate=None, **context):
    entry = {"ts": "t", "by": "fixture", "event": "note", "kind": kind}
    if data is not None:
        entry["data"] = data
    if text is not None:
        entry["text"] = text
    if mandate is not None:
        entry["mandate"] = mandate
    entry.update(context)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps(entry, separators=(",", ":")) + "\n")


def append_subagent(event, kind, *, mandate=None, data=None, **context):
    entry = {"ts": "t", "by": "fixture", "event": event, "kind": kind}
    if mandate is not None:
        entry["mandate"] = mandate
    if data is not None:
        entry["data"] = data
    entry.update(context)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps(entry, separators=(",", ":")) + "\n")


def append_code_correction(round_number):
    verdict = next(
        entry for entry in reversed(journal_lines())
        if entry.get("kind") == "verdict.consumed"
        and (entry.get("data") or {}).get("check") == "code"
        and entry.get("round") == round_number
    )
    findings = verdict["data"]["findings"]
    path = os.path.join(BASE, f"code-correction-{round_number}.md")
    with open(path, "w", encoding="utf-8") as target:
        target.write("\n\n".join(
            f"## Finding {finding} — corrected\n"
            f"The next candidate corrects finding {finding}."
            for finding in range(1, findings + 1)
        ) + "\n")
    result = run_progress(
        "note", "code.review.resolved", "--round", str(round_number),
        "--text-file", path,
        "--data", json.dumps({
            "check": "code",
            "items": [{"id": finding, "status": "corrected"}
                      for finding in range(1, findings + 1)],
        }),
    )
    check(result.returncode == 0, result.stdout + result.stderr)


def append_checker_verdict(check="code", *, lot="lot-1", task=1, attempt=1,
                           round_number=1, findings=0, text=None, impacts=None):
    round_limit = {"design": 10, "code": 10}[check]
    helper = os.path.join(WORKSPACE, "prompts", "construction", "construction_review.py")
    plan_path = os.path.join(WORKSPACE, "plans", f"{lot}-plan.md")
    if not os.path.isfile(plan_path):
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        headings = []
        for number in range(1, task + 1):
            headings.append(
                f"## Task {number} - Task {number}\n"
                f"Achieves: Complete task {number}.\n"
                f"To verify: Task {number} is complete.\n"
                + ("\n### Design\nImplement the accepted task contract.\n" if number == task else "")
            )
        with open(plan_path, "w", encoding="utf-8") as target:
            target.write("# Plan\n\n" + "\n".join(headings))
    state = json.loads(subprocess.check_output(
        [sys.executable, helper, "plan-state", lot, str(task)], text=True, cwd=REPO,
    ))
    active = os.path.isfile(os.path.join(WORKSPACE, "attempt-in-flight"))
    plan_manifest = "a" * 40
    plan_tasks = task
    retry = None
    if active:
        lines = open(os.path.join(WORKSPACE, "attempt-in-flight"), encoding="utf-8").read().splitlines()
        match = re.fullmatch(
            r"plan ([0-9a-f]{40,64}) ([1-9][0-9]*) ownership ([0-9a-f]{64}) "
            r"contract ([0-9a-f]{64}) retry (-|[0-9]+:[0-9a-f]{64})", lines[1],
        )
        plan_manifest, plan_tasks = match.group(1), int(match.group(2))
        retry = None if match.group(5) == "-" else match.group(5)
    logical = {
        "check": check, "lot": lot, "task": task,
        "attempt": attempt, "round": round_number,
        "plan_manifest": plan_manifest, "plan_tasks": plan_tasks,
        "plan_ownership_sha256": state["plan_ownership_sha256"],
        "contract_sha256": state["contract_sha256"],
        "design_sha256": state["design_sha256"],
        "plan_projection_sha256": state["plan_projection_sha256"],
        "disagreement_sha256": state["disagreement_sha256"],
        "retry": retry,
    }
    context = {"mode": "construction", "lot": lot, "task": task,
               "attempt": attempt, "round": round_number}
    if check == "code":
        if not any(entry.get("kind") == "verdict.consumed"
                   and (entry.get("data") or {}).get("check") == "design"
                   and entry.get("lot") == lot and entry.get("task") == task
                   and entry.get("attempt") == attempt
                   and (entry.get("data") or {}).get("outcome") == "clean"
                   for entry in journal_lines()):
            append_checker_verdict(
                "design", lot=lot, task=task, attempt=attempt,
                round_number=1, findings=0,
            )
        if round_number > 1:
            prior_round = round_number - 1
            if not any(entry.get("kind") == "code.review.resolved"
                       and entry.get("round") == prior_round for entry in journal_lines()):
                append_code_correction(prior_round)
        if active:
            candidate = os.path.join(REPO, "fixture-code-review.txt")
            with open(candidate, "w", encoding="utf-8") as target:
                target.write(f"round {round_number}\n")
            subprocess.run(["git", "-C", REPO, "add", "fixture-code-review.txt"], check=True)
            base = subprocess.check_output([
                "git", "-C", REPO, "rev-parse",
                f"refs/bwr/test-run/{lot}/attempt-base^{{commit}}",
            ], text=True).strip()
            tree = subprocess.check_output(["git", "-C", REPO, "write-tree"], text=True).strip()
        else:
            base = subprocess.check_output(
                ["git", "-C", REPO, "rev-parse", "HEAD^"], text=True,
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", REPO, "rev-parse", "HEAD^{tree}"], text=True,
            ).strip()
        gate = hashlib.sha256(f"review:{lot}:{task}:{attempt}:{round_number}".encode()).hexdigest()
        previous = None
        if round_number > 1:
            entries = journal_lines()
            prior_index, prior_verdict = next(
                (index, entry) for index, entry in reversed(list(enumerate(entries)))
                if entry.get("kind") == "verdict.consumed" and entry.get("round") == round_number - 1
                and (entry.get("data") or {}).get("check") == "code"
            )
            resolution_index, resolution = next(
                (index, entry) for index, entry in reversed(list(enumerate(entries)))
                if entry.get("kind") == "code.review.resolved" and entry.get("round") == round_number - 1
            )
            prior_data = prior_verdict["data"]
            raw_lines = open(os.path.join(WORKSPACE, "progress.jsonl"), "rb").read().splitlines()
            prior_report = json.load(open(os.path.join(WORKSPACE, prior_data["report"]), encoding="utf-8"))
            previous = {
                "source": "round", "round": round_number - 1,
                "result": prior_data["report"],
                "result_sha256": prior_data["report_sha256"],
                "findings": [{key: item[key] for key in ("id", "where", "what", "why", "impact")}
                             for item in prior_report["findings"]],
                "resolution": resolution["data"]["items"],
                "resolution_proof": f"{resolution_index}:{hashlib.sha256(raw_lines[resolution_index]).hexdigest()}",
            }
        manifest_result = subprocess.run([
            sys.executable, helper, "manifest", lot, str(task), str(attempt),
            str(round_number), gate, base, tree,
        ], input=json.dumps(previous) if previous else "", capture_output=True,
           text=True, cwd=REPO, check=True)
        frozen = json.loads(manifest_result.stdout)
        logical.update({
            "gate": gate, "tree": tree, "manifest": frozen["path"],
            "manifest_sha256": frozen["sha256"],
        })
        gate_path = write_project(".superpowers/bwr/gate.md", "true\n")
        gate_blob = subprocess.check_output(
            ["git", "-C", REPO, "hash-object", gate_path], text=True,
        ).strip()
        head = subprocess.check_output(
            ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
        ).strip()
        gate_data = {
            "op": gate, "scope": "review",
            "owner": f"{lot}/task-{task}/attempt-{attempt}/code-round-{round_number}",
            "lot": lot, "task": task, "attempt": attempt, "head": head, "base": base,
            "tree": tree, "gate": gate_blob, "code": "-",
        }
        append_subagent("subagent-started", "gate-runner", data=gate_data)
        report_relative, report_sha = write_gate_report(gate, gate_blob, tree)
        append_subagent("subagent-ended", "gate-runner", data={
            **gate_data, "green": True, "surface": "unchanged", "report": report_relative,
            "report_sha256": report_sha, "commands": 1,
        })
    else:
        frozen = json.loads(subprocess.check_output([
            sys.executable, helper, "design-manifest", lot, str(task), str(attempt),
            str(round_number),
        ], text=True, cwd=REPO))
        logical.update({
            "manifest": frozen["path"], "manifest_sha256": frozen["sha256"],
        })
    append_subagent("subagent-started", f"{check}-checker",
                    data={**logical, "call": 1}, **context)
    append_note(
        "bound.spent", logical,
        f"{check} checker round {round_number} of {round_limit}", **context,
    )
    if check == "code":
        manifest = json.loads(open(
            os.path.join(WORKSPACE, *logical["manifest"].split("/")), encoding="utf-8",
        ).read())
        report = {
            "verdict": "clean" if findings == 0 else "findings",
            "manifest": logical["manifest"],
            "inspected": [
                {"id": item["id"], "path": item["path"],
                 "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"]}
                for item in manifest["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate was checked against Achieves."},
                {"subject": "assertion", "evidence": "The checker tried one concrete counterexample."},
            ],
            "previous": [
                {"id": item["id"], "status": "addressed",
                 "evidence": "The next candidate corrects this exact finding."}
                for item in (manifest.get("previous") or {}).get("findings", [])
            ],
            "findings": [
                {"id": number, "where": f"fixture-code-review.txt:{number}",
                 "what": f"Finding {number}", "why": "The accepted task contract is not met.",
                 "impact": impacts[number - 1] if impacts else "IMPORTANT",
                 "previous": []}
                for number in range(1, findings + 1)
            ],
        }
        source = os.path.join(BASE, f"code-result-{lot}-{task}-{attempt}-{round_number}.json")
        with open(source, "w", encoding="utf-8") as target:
            json.dump(report, target)
        audited = json.loads(subprocess.check_output([
            sys.executable, helper, "publish-result", logical["manifest"], source,
        ], text=True, cwd=REPO))
        ended_data = {**logical, "call": 1, **audited}
    else:
        report = design_result_payload({"manifest": logical["manifest"]}, findings=[
            {"id": number, "where": f"Design step {number}",
             "what": f"Design finding {number}",
             "why": "The accepted task contract is not met.",
             "impact": impacts[number - 1] if impacts else "IMPORTANT", "previous": []}
            for number in range(1, findings + 1)
        ])
        source = write_design_result(
            f"design-result-{lot}-{task}-{attempt}-{round_number}.json", report,
        )
        audited = json.loads(subprocess.check_output([
            sys.executable, helper, "publish-design-result", logical["manifest"], source,
        ], text=True, cwd=REPO))
        ended_data = {**logical, "call": 1, **audited}
    append_subagent("subagent-ended", f"{check}-checker", data=ended_data, **context)
    outcome = "clean" if findings == 0 else "findings"
    verdict = dict(ended_data)
    append_note("verdict.consumed", verdict, None, **context)


def design_result_payload(opening, *, findings=(), previous=(), verdict=None):
    findings = list(findings)
    return {
        "verdict": verdict or ("clean" if not findings else "findings"),
        "manifest": opening["manifest"],
        "checks": [
            {"subject": "task contract",
             "evidence": "Every Achieves and To verify obligation was checked."},
            {"subject": "repository fit",
             "evidence": "The named repository patterns and constraints were checked."},
        ],
        "previous": list(previous),
        "findings": findings,
    }


def write_design_result(name, payload):
    path = os.path.join(BASE, name)
    with open(path, "w", encoding="utf-8") as target:
        json.dump(payload, target)
    return path


def open_design_round(round_number):
    opened = run_progress(
        "subagent-started", "design-checker", "--round", str(round_number),
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    opening = json.loads(opened.stdout)
    spent = run_progress(
        "note", "bound.spent", "--round", str(round_number),
        "--text", f"design checker round {round_number} of 10",
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    return opening


def finish_design_round(round_number, opening, *, findings=(), previous=()):
    source = write_design_result(
        f"design-round-{round_number}.json",
        design_result_payload(opening, findings=findings, previous=previous),
    )
    ended = run_progress(
        "subagent-ended", "design-checker", "--round", str(round_number),
        "--data", json.dumps({"result": source}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    outcome = "clean" if not findings else "findings"
    consumed = run_progress(
        "note", "verdict.consumed", "--round", str(round_number),
        "--data", json.dumps({"check": "design", "outcome": outcome}),
    )
    check(consumed.returncode == 0, consumed.stdout + consumed.stderr)


def resolve_design_round(round_number, items):
    text_path = os.path.join(BASE, f"design-resolution-{round_number}.md")
    with open(text_path, "w", encoding="utf-8") as target:
        target.write("\n\n".join(
            f"## Finding {item['id']} — {item['status']}\n"
            f"Exact evidence for finding {item['id']}."
            for item in items
        ) + "\n")
    result = run_progress(
        "note", "design.review.resolved", "--round", str(round_number),
        "--text-file", text_path,
        "--data", json.dumps({"check": "design", "items": items}),
    )
    check(result.returncode == 0, result.stdout + result.stderr)


def replace_current_design(replacement):
    path = os.path.join(WORKSPACE, "plans", "lot-1-plan.md")
    text = open(path, encoding="utf-8").read()
    text = re.sub(
        r"(?ms)^### Design\n.*?(?=^### |^## Task |\Z)",
        f"### Design\n{replacement.rstrip()}\n",
        text,
    )
    with open(path, "w", encoding="utf-8") as target:
        target.write(text)


def append_current_disagreement(body):
    path = os.path.join(WORKSPACE, "plans", "lot-1-plan.md")
    text = open(path, encoding="utf-8").read()
    with open(path, "a", encoding="utf-8") as target:
        heading = "" if "\n### Disagreement\n" in text else "\n### Disagreement\n"
        target.write(f"{heading}{body.rstrip()}\n")


def drive_design_to_round_ten():
    previous = []
    for round_number in range(1, 11):
        opening = open_design_round(round_number)
        finding = {
            "id": 1, "where": f"Design round {round_number}",
            "what": f"The round {round_number} design keeps one exact defect.",
            "why": "The accepted task contract remains unmet.",
            "impact": "IMPORTANT", "previous": [1] if previous else [],
        }
        findings = [finding]
        if round_number == 10:
            findings.append({
                "id": 2, "where": "Design round 10 alternative",
                "what": "The checker proposes another plan-compliant Design.",
                "why": "The final settlement must preserve the exact alternative.",
                "impact": "MINOR", "previous": [],
            })
        finish_design_round(round_number, opening, findings=findings, previous=previous)
        if round_number < 10:
            replace_current_design(
                f"Implement the accepted task contract. Corrected generation {round_number}."
            )
            resolve_design_round(round_number, [{"id": 1, "status": "corrected"}])
            previous = [{
                "id": 1, "status": "still-open",
                "evidence": "The exact admitted defect remains open.",
            }]


def stop_active_attempt(mode, attempt=2):
    result = subprocess.run(
        [os.path.join(WORKSPACE, "prompts", "common", "stop.sh"),
         mode, "lot-1", "3", str(attempt)],
        capture_output=True, text=True, cwd=REPO, env=ENV, timeout=120,
    )
    check(result.returncode == 0, result.stdout + result.stderr)
    check(not os.path.exists(os.path.join(WORKSPACE, "attempt-in-flight")),
          f"the {mode} stop did not remove the completed attempt identity")
    return result


def seed_active_attempt(lot="lot-1", task=3, attempt=2):
    plan = ["# Plan", ""]
    for number in range(1, task + 1):
        plan.extend([
            f"## Task {number} - Task {number}",
            f"Achieves: Complete task {number}.",
            f"To verify: Task {number} is complete.",
        ])
        if number == task:
            plan.extend(["", "### Design", "Implement the accepted task contract."])
        plan.append("")
    plan_text = "\n".join(plan)
    write_report(f"plans/{lot}-plan.md", plan_text)
    helper = os.path.join(WORKSPACE, "prompts", "construction", "construction_review.py")
    state = json.loads(subprocess.check_output(
        [sys.executable, helper, "plan-state", lot, str(task)], text=True, cwd=REPO,
    ))
    if subprocess.run(["git", "-C", REPO, "rev-parse", "--verify", "HEAD"],
                      capture_output=True).returncode != 0:
        write_project(".gitignore", ".superpowers/\n")
        subprocess.run(["git", "-C", REPO, "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", REPO, "commit", "-qm", "attempt base"], check=True)
    base = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    subprocess.run([
        "git", "-C", REPO, "update-ref", f"refs/bwr/test-run/{lot}/attempt-base", base,
    ], check=True)
    headings = "".join(f"## Task {number} - Task {number}\n" for number in range(1, task + 1))
    manifest = subprocess.check_output(
        ["git", "-C", REPO, "hash-object", "--stdin"], input=headings, text=True,
    ).strip()
    with open(os.path.join(WORKSPACE, "attempt-in-flight"), "w", encoding="utf-8") as target:
        target.write(
            f"{lot} {task} {attempt}\n"
            f"plan {manifest} {task} ownership {state['plan_ownership_sha256']} "
            f"contract {state['contract_sha256']} retry -\n"
        )


def seed_review_gate(lot="lot-1", task=3, attempt=2, round_number=1):
    write_project(".superpowers/bwr/gate.md", "true\n")
    candidate = write_project("fixture-code-review.txt", f"round {round_number}\n")
    subprocess.run(["git", "-C", REPO, "add", candidate], check=True)
    tree = subprocess.check_output(["git", "-C", REPO, "write-tree"], text=True).strip()
    head = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    base = subprocess.check_output([
        "git", "-C", REPO, "rev-parse", f"refs/bwr/test-run/{lot}/attempt-base",
    ], text=True).strip()
    gate_blob = subprocess.check_output([
        "git", "-C", REPO, "hash-object", os.path.join(REPO, ".superpowers", "bwr", "gate.md"),
    ], text=True).strip()
    op = hashlib.sha256(f"ordinary:{lot}:{task}:{attempt}:{round_number}".encode()).hexdigest()
    data = {
        "op": op, "scope": "review",
        "owner": f"{lot}/task-{task}/attempt-{attempt}/code-round-{round_number}",
        "lot": lot, "task": task, "attempt": attempt, "head": head, "base": base,
        "tree": tree, "gate": gate_blob, "code": "-",
    }
    append_subagent("subagent-started", "gate-runner", data=data)
    report_relative, report_sha = write_gate_report(op, gate_blob, tree)
    append_subagent("subagent-ended", "gate-runner", data={
        **data, "green": True, "surface": "unchanged", "report": report_relative,
        "report_sha256": report_sha, "commands": 1,
    })
    return op


def code_result_source(started, findings=0):
    manifest_path = os.path.join(WORKSPACE, *started["manifest"].split("/"))
    with open(manifest_path, encoding="utf-8") as source:
        manifest = json.load(source)
    report = {
        "verdict": "clean" if findings == 0 else "findings",
        "manifest": started["manifest"],
        "inspected": [
            {"id": item["id"], "path": item["path"],
             "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"]}
            for item in manifest["files"]
        ],
        "checks": [
            {"subject": "contract", "evidence": "The candidate was checked against Achieves."},
            {"subject": "assertion", "evidence": "The old behavior breaks the accepted result."},
        ],
        "previous": [
            {"id": item["id"], "status": "addressed",
             "evidence": "The next candidate corrects this exact finding."}
            for item in (manifest.get("previous") or {}).get("findings", [])
        ],
        "findings": [
            {"id": number, "where": f"fixture-code-review.txt:{number}",
             "what": f"Finding {number}", "why": "The accepted contract is not met.",
             "impact": "IMPORTANT",
             "previous": []}
            for number in range(1, findings + 1)
        ],
    }
    path = os.path.join(BASE, f"physical-code-result-{started['round']}.json")
    with open(path, "w", encoding="utf-8") as target:
        json.dump(report, target)
    return path


def stage_workspace_plan(lot="lot-1"):
    source = os.path.join(WORKSPACE, "plans", f"{lot}-plan.md")
    relative = f"docs/plans/test-run-{lot}-plan.md"
    destination = write_project(relative, open(source, encoding="utf-8").read())
    subprocess.run(["git", "-C", REPO, "add", destination], check=True)


def write_report(relative, content):
    path = os.path.join(WORKSPACE, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as target:
        target.write(content)
    return hashlib.sha256(content.encode()).hexdigest()


def write_project(relative, content):
    path = os.path.join(REPO, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as target:
        target.write(content)
    return path


def file_sha256(relative):
    with open(os.path.join(WORKSPACE, *relative.split("/")), "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def seed_batch(*, items, answers, batch=1):
    decisions = [item["id"] for item in items if item["id"].startswith("D")]
    append_note("decision.batch.opened", {"batch": batch, "built": "lot-1"})
    append_note(
        "decision.batch.sourced",
        {"batch": batch, "decisions": decisions, "items": items},
        f"reports/product-review/lot-1/lot-1-decision-batch-{batch}-source.md",
    )
    append_note("decision.batch.settled", {"batch": batch, "answers": answers}, "answers")
    actions_path = f"reports/product-review/lot-1/lot-1-decision-batch-{batch}-actions.md"
    write_report(actions_path, json.dumps({"batch": batch, "answers": answers}, sort_keys=True))
    append_note("decision.batch.ready", {"batch": batch}, actions_path)


def seed_direct_ruling(*, ruling="R1", route="spec-in-place"):
    state_path = f"reports/answers/{ruling}-state.md"
    write_report(state_path, f"{ruling} {route}\n")
    append_note("decision.escalated", {"ruling": ruling}, "question")
    append_note("ruling", {"ruling": ruling, "route": route}, "answer")
    append_note("ruling.ready", {"ruling": ruling}, state_path)
    return state_path


def seed_bound_commit(owner, commit_op, sha, *, state_kind, state_ref,
                      state_path, batch=None, decision=None):
    artifact_sha = file_sha256(state_path)
    ready_op = f"ready-{commit_op}"
    append_note("spec.edit.ready", {
        "op": ready_op, "owner": owner, "status": "active", "route": "spec-in-place",
        "state_kind": state_kind, "state_ref": state_ref, "source_sha": "f" * 40,
        "spec_path_sha256": "e" * 64, "artifact_sha256": artifact_sha,
    }, state_path)
    commit = {
        "op": commit_op, "sha": sha, "parent": "f" * 40, "ready_op": ready_op,
        "state_kind": state_kind, "state_ref": state_ref,
        "artifact_sha256": artifact_sha,
    }
    if batch is None:
        commit["ruling"] = owner
    else:
        commit.update(batch=batch, decision=decision)
    append_note("spec.committed", commit)
    return artifact_sha


SPEC_FIRST = ["enumerator", "verifier", "feasibility", "judge"]
SPEC_LATER = ["enumerator", "ripple", "verifier", "feasibility", "judge"]


def spec_document(*, status="draft", extra=""):
    return (
        "# Demo design\n\n"
        f"**Status:** {status}\n\n"
        "## Lot 1 — Core\n\n"
        "The first contract.\n\n"
        "## Lot 2 — Surface\n\n"
        f"The second contract.\n{extra}"
    )


def seed_spec():
    relative = "docs/plans/demo-design.md"
    write_project(relative, spec_document())
    proc = run_progress("note", "spec.written", "--text", relative, "--data", '{"lots":2}')
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    return relative


def completion_labels(mandate):
    filename = "fixer-completion.md" if mandate == "fixer" else f"reviewer-{mandate}-completion.md"
    with open(os.path.join(SPEC_PROMPTS, filename), encoding="utf-8") as source:
        return [line.strip()[6:].split(" —", 1)[0] for line in source if line.startswith("    - [ ] ")]


def product_completion_labels(mandate):
    with open(os.path.join(PRODUCT_PROMPTS, f"lens-{mandate}.md"), encoding="utf-8") as source:
        return [line.strip()[6:].split(" —", 1)[0]
                for line in source if line.startswith("    - [ ] ")]


def product_report_text(mandate, findings=()):
    labels = product_completion_labels(mandate)
    body = [
        f"COMPLETION ({len(labels)} items)",
        *(f"- [x] {label} — exact evidence" for label in labels),
        "",
    ]
    for number, severity in enumerate(findings, 1):
        body.extend([
            f"### Finding {number}",
            f"Severity: {severity}",
            "Where: src/example.py:1",
            "What: one observable fact",
            "Why it matters: the product can return a wrong result",
            "Proof: exact cited location",
            "",
        ])
    return "\n".join(body)


def spec_report_text(mandate, findings=()):
    labels = completion_labels(mandate)
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
    verdict = "READY" if not findings else "NOT READY"
    body = [f"COMPLETION ({len(labels)} items)", *values, "", verdict]
    for number, finding_class in enumerate(findings, 1):
        body.extend([
            "", f"## {finding_class} F{number} — Finding {number}",
            "Evidence.",
        ])
    return "\n".join(body) + "\n"


def open_spec_round(round_number, mandates):
    proc = run_progress(
        "note", "round.opened", "--data", json.dumps({"round": round_number, "mandates": mandates})
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    return journal_lines()[-1]


def receive_spec_report(round_number, mandate, findings=()):
    report = spec_report_text(mandate, findings)
    write_report(f"reports/spec-review/round-{round_number}-{mandate}.md", report)
    counts = {"critical": 0, "important": 0, "minor": 0, "decision": 0}
    for finding_class in findings:
        counts[finding_class.lower()] += 1
    proc = run_progress(
        "note", "report.received", "--round", str(round_number), "--mandate", mandate,
        "--data", json.dumps(counts),
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    return journal_lines()[-1]


def receive_full_spec_round(round_number, mandates, findings_by_mandate=None):
    findings_by_mandate = findings_by_mandate or {}
    for mandate in mandates:
        receive_spec_report(round_number, mandate, findings_by_mandate.get(mandate, ()))


def recheck_data(owner, commit_op, sha, actions, *, artifact_sha, batch=None,
                 decision=None, items=None, accepted=True, missing=None):
    data = {
        "sha": sha, "commit_op": commit_op, "accepted": accepted,
        "missing": [] if missing is None else missing,
        "artifact_sha256": artifact_sha, "actions": actions,
    }
    if batch is None:
        data["owner"] = owner
    else:
        data.update(batch=batch, decision=decision, items=items)
    return data


def append_conflict_generation(owner, conflict, ids, updates, actions, *,
                               state_kind, state_ref, content="resolution"):
    source_path = f"reports/answers/{owner}-conflict-{conflict}-source.md"
    ready_path = f"reports/answers/{owner}-conflict-{conflict}-resolution.md"
    write_report(source_path, f"source {owner} C{conflict}\n")
    artifact_sha = write_report(ready_path, content)
    append_note("decision.conflict.opened", {
        "owner": owner, "conflict": conflict, "state_kind": state_kind,
        "state_ref": state_ref, "ids": ids,
    })
    append_note("decision.conflict.sourced", {"owner": owner, "conflict": conflict}, source_path)
    append_note("decision.conflict.settled", {
        "owner": owner, "conflict": conflict, "updates": updates,
    }, "the human settlement")
    append_note("decision.conflict.ready", {
        "owner": owner, "conflict": conflict, "actions": actions,
        "artifact_sha256": artifact_sha,
    }, ready_path)
    return ready_path, artifact_sha


def grouped_open_data(*, amendment=1, batch=1, members=None,
                      state_kind="decision.batch.ready", state_ref=None):
    if members is None:
        members = [f"B{batch}/D1"]
    return {
        "amendment": amendment, "origin": "product-review", "built": "lot-1",
        "batch": batch, "members": members, "state_kind": state_kind,
        "state_ref": state_ref or f"B{batch}",
    }


def amendment_document(number, order, members=()):
    decisions = "\n".join(f"{member}: preserve the settled answer." for member in members) \
        or "Apply the operational change ordered above."
    return (
        f"# Amendment {number}\n\n"
        f"## Order and return\n{order}\n\n"
        f"## Decisions\n{decisions}\n\n"
        "## Why\nThe durable order requires this change.\n\n"
        "## What it changes\nReplace the old subject rule.\n\n"
        "## What it preserves\nPreserve every other active answer.\n\n"
        "## Where it was raised\nReturn to the recorded origin.\n"
    )


def reach_report(hops=(0,), dispositions=(), sources=("A1/order",),
                 open_blocker="missing durable input: deployment event catalogue is absent"):
    labels = (
        "hops walked", "places found", "phrasings swept for every changed thing",
        "places reached by purpose and not by name", "tests asserting any changed behaviour",
        "frontier",
    )
    disposition_counts = {value: dispositions.count(value)
                          for value in ("kept", "moved", "removed", "DECISION")}
    closed = bool(hops and hops[-1] == 0)
    evidence = (
        f"{len(hops)} hops, last one returning {hops[-1]} new places",
        f"{sum(hops)} total: {disposition_counts['kept']} kept, "
        f"{disposition_counts['moved']} moved, {disposition_counts['removed']} removed, "
        f"{disposition_counts['DECISION']} DECISION",
        f"active {', '.join(sources)}; 1 unique terms or hits",
        "0",
        "0 found, 0 still asserting it after the amendment",
        f"closed at hop {len(hops)}" if closed
        else (f"NOT CLOSED: {', '.join(str(value) for value in hops)} new places by hop; "
              f"next hop cannot be enumerated — {open_blocker}"),
    )
    lines = [f"COMPLETION ({len(labels)} items)"]
    lines.extend(f"- [x] {label} — {value}" for label, value in zip(labels, evidence))
    lines.extend(["", "## Reach account", ""])
    for ordinal, count in enumerate(hops, 1):
        suffix = " — closed" if ordinal == len(hops) and count == 0 else ""
        lines.append(f"Hop {ordinal}: {count} new{suffix}")
    for ordinal, disposition in enumerate(dispositions, 1):
        handling = {
            "kept": ("### Reason", "The place survives unchanged."),
            "moved": ("### Exact edit", "Move the exact place in the amendment."),
            "removed": ("### Exact edit", "Remove the exact place in the amendment."),
            "DECISION": ("### Options", "Keep it or remove it; each changes user behaviour."),
        }[disposition]
        lines.extend([
            "", f"## P{ordinal} · Place {ordinal}",
            f"Sources: {', '.join(sources)}", f"Location: specification place {ordinal}",
            f"Disposition: {disposition}", "### Evidence", "Exact place evidence.",
            handling[0], handling[1],
        ])
    return "\n".join(lines) + "\n"


def seed_amendment_context():
    if not any(entry.get("kind") == "spec.written" for entry in journal_lines()):
        seed_committed_spec()
    if not any(entry.get("kind") == "pass.opened" for entry in journal_lines()):
        commit, gate, owner = seed_task_gate("lot-1", "amendment-context")
        opening = run_progress(
            "note", "pass.opened",
            "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
        )
        check(opening.returncode == 0, opening.stdout + opening.stderr)


def seed_committed_spec():
    relative = seed_spec()
    subprocess.run(["git", "-C", REPO, "add", relative], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "seed specification"], check=True)
    return relative


def append_reach_session(sweep, session=None):
    session = session or f"reach-session-{sweep}"
    common = {"session": session, "mode": "amendment", "mandate": "reach", "round": sweep}
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps({"ts": "t", "by": "fixture", "event": "session-started",
                                 **common}, separators=(",", ":")) + "\n")
        target.write(json.dumps({"ts": "t", "by": "fixture", "event": "session-retired",
                                 "status": "done", **common}, separators=(",", ":")) + "\n")
    return session


def append_live_reach_session(sweep, session):
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps({
            "ts": "t", "by": "fixture", "event": "session-started",
            "session": session, "mode": "amendment", "mandate": "reach", "round": sweep,
        }, separators=(",", ":")) + "\n")


def seed_written_amendment_for_reach(order="apply the reach order; return to product review"):
    seed_amendment_context()
    opened = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    check(run_progress("note", "pass.closed", "--data", '{"voided":true}').returncode == 0,
          "the product pass did not void")
    write_report("amendments/1.md", amendment_document(1, order))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    path = os.path.join(WORKSPACE, "amendments", "1.md")
    written = run_progress(
        "note", "amendment.written", "--data", '{"amendment":1}', "--text", path,
    )
    check(written.returncode == 0, written.stdout + written.stderr)
    return path


def seed_clean_amendment_landing(opening_data, order="apply amendment; return to caller"):
    seed_amendment_context()
    if not any(entry.get("kind") == "amendment.opened" for entry in journal_lines()):
        opened = run_progress(
            "note", "amendment.opened", "--data", json.dumps(opening_data), "--text", order,
        )
        check(opened.returncode == 0, opened.stdout + opened.stderr)
    opening = next(entry for entry in reversed(journal_lines())
                   if entry.get("kind") == "amendment.opened")
    number = opening["data"]["amendment"]
    if opening["data"]["origin"] == "product-review" and not any(
        entry.get("kind") == "pass.closed" for entry in journal_lines()
    ):
        voided = run_progress("note", "pass.closed", "--data", '{"voided":true}')
        check(voided.returncode == 0, voided.stdout + voided.stderr)
    members = opening["data"].get("members") or ([opening["data"]["ruling"]]
                                                   if opening["data"].get("ruling") else [])
    write_report(f"amendments/{number}.md", amendment_document(number, opening["text"], members))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", str(number)), exist_ok=True)
    written = run_progress(
        "note", "amendment.written", "--data", json.dumps({"amendment": number}),
        "--text", os.path.join(WORKSPACE, "amendments", f"{number}.md"),
    )
    check(written.returncode == 0, written.stdout + written.stderr)
    sources = tuple(members) if members else (f"A{number}/order",)
    report = reach_report(sources=sources)
    write_report(f"reports/amendment/{number}/sweep-1.md", report)
    session = append_reach_session(1)
    sweep = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(sweep.returncode == 0, sweep.stdout + sweep.stderr)
    check(journal_lines()[-1]["data"]["session"] == session,
          "the sweep did not freeze its retired session")
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    relative = next(entry["text"] for entry in journal_lines() if entry.get("kind") == "spec.written")
    write_project(relative, spec_document(status="amended"))
    started = run_progress("subagent-started", "consolidation", "--round", "1")
    check(started.returncode == 0, started.stdout + started.stderr)
    spent = run_progress(
        "note", "bound.spent", "--round", "1", "--text", "consolidation round 1 of 3",
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    ended = run_progress(
        "subagent-ended", "consolidation", "--round", "1", "--data", '{"exact":true}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    consumed = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"consolidation","outcome":"exact"}',
    )
    check(consumed.returncode == 0, consumed.stdout + consumed.stderr)
    script = os.path.join(WORKSPACE, "prompts", "amendment", "amendment-commit.sh")
    committed = subprocess.run(
        [script, str(number), relative, "docs: land amendment", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(committed.returncode == 0, committed.stdout + committed.stderr)
    terminal = journal_lines()[-1]
    check(terminal["kind"] == "amendment.committed", terminal)
    state = run_progress("amendment-state-check")
    check(state.returncode == 0, state.stdout + state.stderr)
    return terminal["data"]["sha"]


def dedupe_items(*, count=1, carries=None, sources=None):
    carries = carries or []
    sources = sources or [f"unlooked/F{ordinal}" for ordinal in range(1, count + 1)]
    items = []
    for ordinal in range(1, count + 1):
        items.append({
            "id": f"F{ordinal}",
            "sources": [source for index, source in enumerate(sources) if index == ordinal - 1],
            "carries": carries if ordinal == 1 else [],
        })
    return items


def allocation_data(built="lot-1", *, count=1, carries=None, sources=None,
                    items=None, refuted=None):
    return {
        "built": built,
        "items": items if items is not None else dedupe_items(
            count=count, carries=carries, sources=sources,
        ),
        "refuted": refuted or [],
    }


def write_confirmed(built, carries, *, lot="lot-1.1", count=1, sources=None,
                    items=None, plan_text=None):
    root = built.split(".", 1)[0]
    items = items if items is not None else dedupe_items(
        count=count, carries=carries, sources=sources,
    )
    directory = os.path.join(WORKSPACE, "reports", "product-review", root)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, f"{built}-confirmed.md"), "w", encoding="utf-8") as target:
        for item in items:
            target.write(f"## {item['id']} · correction\n")
            if item["sources"]:
                target.write("Sources: " + ", ".join(item["sources"]) + "\n")
            if item["carries"]:
                target.write("Carries: " + ", ".join(item["carries"]) + "\n")
    plan = os.path.join(WORKSPACE, "plans", f"{lot}-plan.md")
    os.makedirs(os.path.dirname(plan), exist_ok=True)
    with open(plan, "w", encoding="utf-8") as target:
        target.write(plan_text if plan_text is not None else f"Covers: {built}-confirmed.md\n")


def seed_review_receipts(built="lot-1", *, confirmed=0, omit=None):
    root = built.split(".", 1)[0]
    opening = next(entry for entry in reversed(journal_lines()) if entry.get("kind") == "pass.opened")
    pass_commit = opening["data"]["commit"]
    pass_gate = opening["data"]["gate"]
    for mandate in ("unlooked", "user", "meaning", "quality", "coverage"):
        if mandate == omit:
            continue
        report = os.path.join(
            WORKSPACE, "reports", "product-review", root, f"{built}-{mandate}.md",
        )
        os.makedirs(os.path.dirname(report), exist_ok=True)
        content = product_report_text(
            mandate, ("IMPORTANT",) * confirmed if mandate == "unlooked" else (),
        )
        with open(report, "w", encoding="utf-8") as target:
            target.write(content)
        report_sha = hashlib.sha256(content.encode()).hexdigest()
        counts = {
            "critical": 0, "important": confirmed if mandate == "unlooked" else 0,
            "minor": 0, "decision": 0,
        }
        append_note(
            "report.received",
            {**counts, "pass_commit": pass_commit, "pass_gate": pass_gate,
             "report_sha256": report_sha},
            mandate=mandate,
        )
        identity = {
            "pass_commit": pass_commit, "pass_gate": pass_gate,
            "report_sha256": report_sha,
        }
        append_subagent(
            "subagent-started", "finding-verifier", mandate=mandate, data=identity,
        )
        append_subagent(
            "subagent-ended", "finding-verifier", mandate=mandate,
            data={**identity, "confirmed": confirmed if mandate == "unlooked" else 0,
                  "disproved": 0, "malformed": 0,
                  "claims": [
                      {"id": f"F{ordinal}", "kind": "correction", "verdict": "confirmed"}
                      for ordinal in range(1, confirmed + 1)
                  ] if mandate == "unlooked" else []},
        )


def prepare_review_commit(built="lot-1", token=None, tasks=1):
    # Build one real clean candidate. The pass terminal rechecks this exact HEAD,
    # tree, gate blob and canonical physical gate report.
    write_project(".gitignore", ".superpowers/\n")
    manifest = "# Plan\n\n" + "\n\n".join(
        f"## Task {task} - Task {task}\n"
        f"Achieves: Complete task {task}.\n"
        f"To verify: Task {task} is complete."
        for task in range(1, tasks + 1)
    ) + "\n"
    plan_relative = f"docs/plans/test-run-{built}-plan.md"
    write_project(plan_relative, manifest)
    subprocess.run(
        ["git", "-C", REPO, "add", ".gitignore", plan_relative],
        check=True,
    )
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "plan review lot"], check=True)
    plan = "# Plan\n\n" + "\n\n".join(
        f"## Task {task} - Task {task}\n"
        f"Achieves: Complete task {task}.\n"
        f"To verify: Task {task} is complete.\n\n"
        "### Design\n\nImplemented."
        for task in range(1, tasks + 1)
    ) + "\n"
    write_report(f"plans/{built}-plan.md", plan)
    write_project(plan_relative, plan)
    write_project("subject.txt", f"{built}:{token or 'current'}\n")
    subprocess.run(
        ["git", "-C", REPO, "add", "subject.txt", plan_relative], check=True,
    )
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "review candidate"], check=True)
    commit = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD^{tree}"], text=True,
    ).strip()
    gate_path = write_project(".superpowers/bwr/gate.md", "true\n")
    gate_blob = subprocess.check_output(
        ["git", "-C", REPO, "hash-object", gate_path], text=True,
    ).strip()
    return commit, tree, gate_blob


def write_gate_report(op, gate_blob, tree):
    report_relative = f"reports/gate/{op}.json"
    report = {
        "op": op, "gate": gate_blob, "tree": tree,
        "commands": [{"command": "true", "status": "green", "count": 1,
                      "example": "true exited zero"}],
        "cleanliness": {"completed": True, "unchanged": True, "paths": []},
        "surface": {"completed": True, "status": "unchanged", "candidates": []},
    }
    report_sha = write_report(
        report_relative, json.dumps(report, separators=(",", ":"), sort_keys=True),
    )
    return report_relative, report_sha


def seed_task_gate(built="lot-1", token=None, *, tasks=1, add_lot_built=True,
                   precommit_head=True):
    commit, tree, gate_blob = prepare_review_commit(built, token, tasks)
    head = commit
    if precommit_head:
        head = subprocess.check_output(
            ["git", "-C", REPO, "rev-parse", f"{commit}^"], text=True,
        ).strip()
    gate = hashlib.sha256(f"gate:{built}:{commit}".encode()).hexdigest()
    owner = f"{built}/task-1/attempt-1"
    append_checker_verdict("code", lot=built, task=1, attempt=1)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "rb") as journal:
        raw_lines = journal.read().splitlines()
    code_proof = f"{len(raw_lines) - 1}:{hashlib.sha256(raw_lines[-1]).hexdigest()}"
    report_relative, report_sha = write_gate_report(gate, gate_blob, tree)
    append_subagent(
        "subagent-ended", "gate-runner", mandate="gate",
        data={"op": gate, "scope": "task", "owner": owner, "lot": built,
              "task": 1, "attempt": 1, "head": head, "base": head,
              "tree": tree, "gate": gate_blob, "code": code_proof,
              "green": True, "surface": "unchanged", "report": report_relative,
              "report_sha256": report_sha, "commands": 1},
    )
    append_note(
        "attempt.succeeded", {"attempt": 1, "lot": built, "sha": commit, "gate": gate},
        lot=built, task=1,
    )
    ref_root = f"refs/bwr/test-run/{built}"
    subprocess.run(
        ["git", "-C", REPO, "update-ref", f"{ref_root}/task-0", f"{commit}^"], check=True,
    )
    subprocess.run(
        ["git", "-C", REPO, "update-ref", f"{ref_root}/task-1", commit], check=True,
    )
    if add_lot_built:
        append_note("lot.built", {"tasks": tasks, "attempts": tasks}, lot=built)
    return commit, gate, owner


def seed_baseline_gate(owner, commit, base):
    tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", f"{commit}^{{tree}}"], text=True,
    ).strip()
    gate_path = os.path.join(REPO, ".superpowers", "bwr", "gate.md")
    gate_blob = subprocess.check_output(
        ["git", "-C", REPO, "hash-object", gate_path], text=True,
    ).strip()
    gate = hashlib.sha256(f"baseline:{owner}:{commit}".encode()).hexdigest()
    report_relative, report_sha = write_gate_report(gate, gate_blob, tree)
    append_subagent(
        "subagent-ended", "gate-runner", mandate="gate",
        data={"op": gate, "scope": "baseline", "owner": owner, "lot": "-",
              "task": 0, "attempt": 0, "head": commit, "base": base,
              "tree": tree, "gate": gate_blob, "code": "-", "green": True,
              "surface": "unchanged", "report": report_relative,
              "report_sha256": report_sha, "commands": 1},
    )
    return gate


def seed_review_pass(*, built="lot-1", commit=None, confirmed=0, omit=None):
    commit, gate, owner = seed_task_gate(built, commit)
    append_note("pass.opened", {
        "built": built, "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": owner, "source_lot": built,
        "source_task": 1, "source_attempt": 1,
    })
    seed_review_receipts(built, confirmed=confirmed, omit=omit)
    return commit


def seed_breach():
    opening = {
        "breach": 1, "owner": "R1", "answer": "R1", "bad_op": "bad-1",
        "bad_sha": "a" * 40, "authorized_sha": "b" * 40, "erased": ["B1/D1"],
    }
    corrected = dict(opening)
    corrected.update({"sha": "c" * 40, "op": "repair-1", "mark_moved": False})
    append_note("spec.breach.opened", opening, "bad-state proof")
    append_note("spec.breach.corrected", corrected)


def restored_data(**overrides):
    data = {
        "breach": 1, "owner": "R1", "bad_op": "bad-1",
        "basis_kind": "spec.breach.corrected", "basis_ref": "repair-1",
        "sha": "c" * 40,
    }
    data.update(overrides)
    return data


# ------------------------------------------------------- session commands

@test
def session_started_records_target_context():
    line = the_line(run_progress("session-started", TARGET))
    check(line["event"] == "session-started", line)
    check(line["by"] == CALLER, "`by` must be the caller")
    check(line["session"] == TARGET, "`session` must be the target")
    check(line["mode"] == "spec" and line["mandate"] == "verifier"
          and line["round"] == 2 and line["job"] == "reviewer",
          f"context must come from the TARGET's annotations: {line}")
    check("task" not in line and "attempt" not in line and "lot" not in line,
          "caller-only context fields must not leak into a target event")
    check("feature" not in line and "status" not in line and "schema" not in line,
          "only the seven context fields belong on the line")
    check(line["ts"].startswith("20") and line["ts"].endswith("Z"), "unreadable timestamp")
    check(mutations() == [], "session-started must not mutate anything")


@test
def session_started_unknown_target_fails_loudly():
    refused(run_progress("session-started", "no-such-session"))


@test
def session_status_changes_and_records():
    line = the_line(run_progress("session-status", TARGET, "blocked"))
    check(line["event"] == "session-status" and line["status"] == "blocked", line)
    check(line["session"] == TARGET and line["by"] == CALLER, line)
    check(line["mode"] == "spec" and line["mandate"] == "verifier",
          "session-status must carry the TARGET's context")
    check(["update-session", TARGET, "annotations", "set:bwr.status=blocked"] in cli_calls(),
          "the status change must go through the CLI")


@test
def session_status_own_id_done_is_allowed():
    # The handover case: an outgoing orchestrator sets ITSELF done, without a
    # retirement — `done` must stay reachable through session-status.
    line = the_line(run_progress("session-status", CALLER, "done"))
    check(line["session"] == CALLER and line["status"] == "done", line)
    check(line["mode"] == "construction" and line["task"] == 3, "own context expected")
    check(["update-session", CALLER, "annotations", "set:bwr.status=done"] in cli_calls(),
          "the change must reach the CLI")


@test
def session_status_unknown_status_is_refused():
    refused(run_progress("session-status", TARGET, "resting"))
    check(cli_calls() == [], "a refused vocabulary must trigger no CLI call at all")


@test
def session_status_cli_failure_logs_nothing():
    cfg = default_config()
    cfg["fail"] = [["update-session", TARGET, "annotations"]]
    set_config(cfg)
    proc = run_progress("session-status", TARGET, "idle")
    refused(proc)
    check("NOTHING WAS JOURNALED" in proc.stdout,
          "the failure must say the act did not happen")


@test
def session_retired_full_chain_in_order():
    line = the_line(run_progress("session-retired", TARGET, "done", "--archive", "--hide"))
    check(line["event"] == "session-retired" and line["status"] == "done", line)
    check(line["archived"] is True and line["hidden"] is True, line)
    check(line["mode"] == "spec" and line["job"] == "reviewer",
          "session-retired must carry the TARGET's context")
    check(mutations() == [
        ["update-session", TARGET, "annotations", "set:bwr.status=done"],
        ["update-session", TARGET, "archive"],
        ["update-session", TARGET, "hide"],
    ], f"status, then archive, then hide — got {mutations()}")


@test
def session_retired_without_flags_omits_the_booleans():
    line = the_line(run_progress("session-retired", TARGET, "failed"))
    check(line["status"] == "failed", line)
    check("archived" not in line and "hidden" not in line,
          "archive/hide not requested: the fields must be absent, not false")
    check(mutations() == [["update-session", TARGET, "annotations", "set:bwr.status=failed"]],
          "only the status change should have been issued")


@test
def session_retired_rejects_non_terminal_status():
    proc = run_progress("session-retired", TARGET, "working", "--archive", "--hide")
    refused(proc)
    check(cli_calls() == [], "refused before any CLI call")
    check("session-status" in proc.stdout, "the error must point at session-status")


@test
def session_retired_archive_failure_stops_the_chain():
    cfg = default_config()
    cfg["fail"] = [["update-session", TARGET, "archive"]]
    set_config(cfg)
    proc = run_progress("session-retired", TARGET, "done", "--archive", "--hide")
    check(proc.returncode != 0, "a half-done retirement must exit non-zero")
    lines = journal_lines()
    check(len(lines) == 1, "the line records what actually succeeded")
    line = lines[0]
    check(line["status"] == "done" and line["archived"] is False and line["hidden"] is False,
          f"archived must be false and hide must not be claimed: {line}")
    check(["update-session", TARGET, "hide"] not in cli_calls(),
          "hide must not be attempted once archive failed")
    check("WAS journaled" in proc.stdout, "the failure must say the line was written")


@test
def session_retired_hide_failure_is_recorded():
    cfg = default_config()
    cfg["fail"] = [["update-session", TARGET, "hide"]]
    set_config(cfg)
    proc = run_progress("session-retired", TARGET, "done", "--archive", "--hide")
    check(proc.returncode != 0, "a half-done retirement must exit non-zero")
    lines = journal_lines()
    check(len(lines) == 1, "the line records what actually succeeded")
    check(lines[0]["archived"] is True and lines[0]["hidden"] is False,
          f"archive succeeded, hide did not — the line must say exactly that: {lines[0]}")
    check("WAS journaled" in proc.stdout, "the failure must say the line was written")


@test
def session_retired_hide_only():
    line = the_line(run_progress("session-retired", TARGET, "superseded", "--hide"))
    check(line["status"] == "superseded" and line["hidden"] is True, line)
    check("archived" not in line, "archive not requested: the field must be absent")
    check(mutations() == [
        ["update-session", TARGET, "annotations", "set:bwr.status=superseded"],
        ["update-session", TARGET, "hide"],
    ], f"status then hide, nothing else — got {mutations()}")


@test
def session_retired_status_failure_logs_nothing():
    cfg = default_config()
    cfg["fail"] = [["update-session", TARGET, "annotations"]]
    set_config(cfg)
    proc = run_progress("session-retired", TARGET, "done", "--archive", "--hide")
    refused(proc)
    check(["update-session", TARGET, "archive"] not in cli_calls()
          and ["update-session", TARGET, "hide"] not in cli_calls(),
          "nothing after the failed status change may be attempted")


# ------------------------------------------------------ subagents and notes

@test
def subagent_started_uses_caller_context():
    line = the_line(run_progress("subagent-started", "completeness"))
    check(line["event"] == "subagent-started" and line["kind"] == "completeness", line)
    check(line["by"] == CALLER, line)
    check(line["mode"] == "construction" and line["lot"] == "lot-1"
          and line["task"] == 3 and line["attempt"] == 2 and line["job"] == "controller",
          f"context must come from the CALLER's annotations: {line}")
    check(mutations() == [], "subagent events log only")


@test
def subagent_unknown_kind_is_refused():
    refused(run_progress("subagent-started", "gate-checker"))
    refused(run_progress("subagent-ended", "verifier"))


@test
def subagent_ended_carries_data():
    line = the_line(run_progress("subagent-ended", "completeness",
                                 "--data", '{"decisions":"12/12","tasks":"7/8"}'))
    check(line["kind"] == "completeness", line)
    check(line["data"] == {"decisions": "12/12", "tasks": "7/8"}, line)


@test
def discovery_gate_is_bracketed_but_is_not_an_accepted_gate_proof():
    proc = run_progress(
        "subagent-started", "gate-runner", "--data", '{"scope":"discovery"}'
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    started = journal_lines()[-1]
    check(started["data"] == {"scope": "discovery"}, started)
    duplicate = run_progress(
        "subagent-started", "gate-runner", "--data", '{"scope":"discovery"}'
    )
    check(duplicate.returncode != 0 and len(journal_lines()) == 1,
          "a second discovery opening was accepted")
    proc = run_progress(
        "subagent-ended", "gate-runner", "--data",
        '{"scope":"discovery","green":true,"surface":"different"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    ended = journal_lines()[-1]
    check(ended["data"]["surface"] == "different", ended)


@test
def context_flags_override_the_derived_context():
    line = the_line(run_progress("subagent-started", "completeness",
                                 "--mandate", "coverage", "--task", "9", "--round", "4"))
    check(line["mandate"] == "coverage" and line["task"] == 9 and line["round"] == 4,
          f"the flags must win over the derived values: {line}")
    check(line["lot"] == "lot-1" and line["mode"] == "construction",
          "unflagged fields keep their derived value")


@test
def construction_verdicts_require_a_spend_and_physical_result():
    seed_active_attempt()
    refused(run_progress(
        "note", "verdict.consumed", "--round", "1", "--data",
        '{"check":"design","outcome":"clean"}',
    ))
    refused(run_progress(
        "note", "verdict.consumed", "--round", "1", "--data",
        '{"check":"code","outcome":"clean"}',
    ))

    append_note(
        "attempt.failed", {"attempt": 2, "classification": "C3.9b"},
        lot="lot-1", task=3,
    )
    before = len(journal_lines())
    proc = run_progress(
        "note", "verdict.consumed", "--task", "3", "--text", "invented analysis",
        "--data", '{"check":"diagnostic","outcome":"C3.9b"}',
    )
    refused_after(proc, before, "a diagnostic verdict without a physical result")


@test
def design_checker_result_is_one_immutable_structured_batch():
    seed_active_attempt()
    opened = run_progress("subagent-started", "design-checker", "--round", "1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    opening = json.loads(opened.stdout)
    check(set(opening) == {"manifest", "manifest_sha256", "call"}, opening)

    spent = run_progress(
        "note", "bound.spent", "--round", "1",
        "--text", "design checker round 1 of 10",
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    result = design_result_payload(opening, findings=[{
        "id": 1,
        "where": "Design step 2",
        "what": "The design drops the required state transition.",
        "why": "The task cannot satisfy its accepted contract.",
        "impact": "IMPORTANT",
        "previous": [],
    }])
    source = write_design_result("design-round-1.json", result)
    ended = run_progress(
        "subagent-ended", "design-checker", "--round", "1",
        "--data", json.dumps({"result": source}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)

    consumed = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"design","outcome":"findings"}',
    )
    check(consumed.returncode == 0, consumed.stdout + consumed.stderr)
    data = journal_lines()[-1]["data"]
    check(data["findings"] == 1 and data["important"] == 1, data)
    check(data["critical"] == 0 and data["minor"] == 0, data)
    check(data["report"].endswith("-design-round-1-result.json"), data)
    result_path = os.path.join(WORKSPACE, data["report"])
    with open(result_path, "a", encoding="utf-8") as target:
        target.write(" ")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0,
          "a changed immutable design-checker result passed historical validation")


@test
def design_parity_requires_one_correction_account_before_the_next_round():
    seed_active_attempt()
    opening = open_design_round(1)
    finding = {
        "id": 1, "where": "Design step 1",
        "what": "The state transition is absent.",
        "why": "The accepted task outcome cannot occur.",
        "impact": "IMPORTANT", "previous": [],
    }
    finish_design_round(1, opening, findings=[finding])
    before = len(journal_lines())
    refused_after(
        run_progress("subagent-started", "design-checker", "--round", "2"),
        before, "a later design round without a complete prior resolution",
    )

    replace_current_design("Implement the accepted task contract and its state transition.")
    resolve_design_round(1, [{"id": 1, "status": "corrected"}])
    opening = open_design_round(2)
    previous = [{
        "id": 1, "status": "addressed",
        "evidence": "The corrected Design now names the state transition.",
    }]
    finish_design_round(2, opening, previous=previous)
    proof = run_progress("construction-verdict-check", "design", "lot-1", "3", "2")
    check(proof.returncode == 0, proof.stdout + proof.stderr)


@test
def design_parity_round_ten_uses_one_terminal_settlement_and_no_round_eleven():
    seed_active_attempt()
    append_current_disagreement(
        "#### Finding 7 — design alternative\n"
        "A prior attempt preserved this accepted alternative."
    )
    drive_design_to_round_ten()

    before = len(journal_lines())
    refused_after(
        run_progress("subagent-started", "design-checker", "--round", "11"),
        before, "an eleventh design-checker round",
    )
    append_current_disagreement(
        "#### Finding 1 — design alternative\n"
        "The checker alternative and the selected Design both satisfy the accepted plan.\n"
        "#### Finding 2 — design alternative\n"
        "The second checker alternative also satisfies the accepted plan."
    )
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "alternative"},
    ])
    proof = run_progress("construction-verdict-check", "design", "lot-1", "3", "2")
    check(proof.returncode == 0, proof.stdout + proof.stderr)
    plan = open(os.path.join(WORKSPACE, "plans", "lot-1-plan.md"), encoding="utf-8").read()
    check("Finding 7 — design alternative" in plan,
          "the final settlement did not preserve an earlier Design alternative")


@test
def design_parity_accepted_final_defect_requires_exact_failure_handoff():
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    refused_after(
        run_progress("construction-verdict-check", "design", "lot-1", "3", "2"),
        len(journal_lines()), "an accepted final Design defect as implementation authority",
    )
    handoff = run_progress("construction-failure-handoff", "lot-1", "3", "2")
    check(handoff.returncode == 0, handoff.stdout + handoff.stderr)
    check(handoff.stdout.startswith("## Final design-review handoff\n```json\n"), handoff.stdout)
    report_relative = "reports/construction/lot-1-task-3-try-2.md"
    report_path = os.path.join(WORKSPACE, report_relative)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as target:
        target.write(
            "## What failed\nThe final design review accepted one defect.\n\n"
            "## Classification\nC3.9b — the current task Design is wrong.\n\n"
            "## Evidence read\nThe immutable design-checker result and settlement.\n\n"
            + handoff.stdout
        )
    before = len(journal_lines())
    refused_after(
        run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9a"),
        before, "C3.9a for an accepted pre-implementation Design defect",
    )
    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "2", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    failure_data = json.loads(admitted.stdout)
    check(failure_data["report"] == report_relative, failure_data)
    check(failure_data["design_review"]["accepted"] == [2], failure_data)
    failed = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", json.dumps(failure_data),
    )
    check(failed.returncode == 0, failed.stdout + failed.stderr)
    retry = run_progress(
        "construction-retry-check", "lot-1", "3", report_relative,
    )
    check(retry.returncode == 0, retry.stdout + retry.stderr)
    proof = retry.stdout.strip()
    marker = os.path.join(WORKSPACE, "attempt-in-flight")
    lines = open(marker, encoding="utf-8").read().splitlines()
    lines[0] = "lot-1 3 3"
    lines[1] = re.sub(r" retry .+$", f" retry {proof}", lines[1])
    with open(marker, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")
    replace_current_design("Implement the accepted task contract without the accepted defect.")
    cfg = default_config()
    cfg["whoami"]["session"]["annotations"]["bwr"]["attempt"] = 3
    cfg["sessions"][CALLER]["annotations"]["bwr"]["attempt"] = 3
    set_config(cfg)
    retry_opening = open_design_round(1)
    manifest_relative = retry_opening["manifest"]
    manifest = json.load(open(os.path.join(WORKSPACE, manifest_relative), encoding="utf-8"))
    check(manifest["previous"]["source"] == "retry", manifest["previous"])
    check([item["id"] for item in manifest["previous"]["findings"]] == [2], manifest)
    finish_design_round(1, retry_opening, previous=[{
        "id": 2, "status": "addressed",
        "evidence": "The replacement Design removes the exact accepted defect.",
    }])
    retry_proof = run_progress("construction-verdict-check", "design", "lot-1", "3", "3")
    check(retry_proof.returncode == 0, retry_proof.stdout + retry_proof.stderr)


def assert_stopped_design_obligation_reaches_retry(mode):
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    stop_active_attempt(mode)

    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0, retry.stdout + retry.stderr)
    proof = retry.stdout.strip()
    check(proof != "-", f"the {mode} stop discarded the accepted Design obligation")

    seed_active_attempt(attempt=3)
    marker = os.path.join(WORKSPACE, "attempt-in-flight")
    lines = open(marker, encoding="utf-8").read().splitlines()
    lines[1] = re.sub(r" retry .+$", f" retry {proof}", lines[1])
    with open(marker, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")
    cfg = default_config()
    cfg["whoami"]["session"]["annotations"]["bwr"]["attempt"] = 3
    cfg["sessions"][CALLER]["annotations"]["bwr"]["attempt"] = 3
    set_config(cfg)
    opening = open_design_round(1)
    manifest = json.load(open(
        os.path.join(WORKSPACE, opening["manifest"]), encoding="utf-8",
    ))
    check([item["id"] for item in manifest["previous"]["findings"]] == [2], manifest)
    finish_design_round(1, opening, previous=[{
        "id": 2, "status": "addressed",
        "evidence": "The retry Design addresses the stopped accepted defect.",
    }])
    stop_active_attempt(mode, attempt=3)
    propagated = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(propagated.returncode == 0, propagated.stdout + propagated.stderr)
    check(propagated.stdout.strip() == proof,
          f"the later {mode} stop did not propagate the accepted Design obligation")


@test
def design_parity_triplet_pause_preserves_accepted_final_obligation():
    assert_stopped_design_obligation_reaches_retry("pause")


@test
def design_parity_triplet_abort_preserves_accepted_final_obligation():
    assert_stopped_design_obligation_reaches_retry("abort")


@test
def design_parity_stop_without_an_accepted_settlement_keeps_normal_retry_behavior():
    seed_active_attempt()
    drive_design_to_round_ten()
    append_current_disagreement(
        "#### Finding 1 — design alternative\n"
        "The first alternative satisfies the accepted task contract.\n"
        "#### Finding 2 — design alternative\n"
        "The second alternative satisfies the accepted task contract."
    )
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "alternative"},
    ])
    stop_active_attempt("pause")
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() == "-", retry.stdout + retry.stderr)

    reset()
    seed_active_attempt()
    drive_design_to_round_ten()
    stop_active_attempt("abort")
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() == "-", retry.stdout + retry.stderr)


@test
def design_parity_historical_stop_rejects_a_changed_accepted_obligation():
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    stop_active_attempt("pause")
    journal = journal_lines()
    stopped = journal[-1]
    check(stopped["kind"] == "paused" and stopped["data"]["design_review"]["accepted"] == [2],
          stopped)
    stopped["data"]["design_review"]["accepted"] = []
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0,
          "a changed accepted Design obligation passed historical validation")


@test
def design_parity_contract_has_probability_strict_result_repair_and_terminal_rules():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as source:
        risk = " ".join(source.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "design-checker.md"),
              encoding="utf-8") as source:
        checker = " ".join(source.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"),
              encoding="utf-8") as source:
        implementer = " ".join(source.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"),
              encoding="utf-8") as source:
        mode = " ".join(source.read().split())
    with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as source:
        skill = " ".join(source.read().split())
    progress_source = open(SOURCE, encoding="utf-8").read()

    check("CONSTRUCTION design and code checkers" in risk,
          "the shared risk contract must include both construction discovery checkers")
    check("-design-risk-filtered.md" in risk,
          "the design checker needs one attempt-scoped private history")
    check("Design and consolidation have three logical checker rounds" not in skill,
          "the root skill retains the obsolete three-round Design limit")
    check("CONSTRUCTION design and code checkers use" in skill,
          "the root risk-admission summary omits one construction checker")
    check("-design-risk-filtered.md" in skill and "-code-risk-filtered.md" in skill,
          "the root private-history summary omits one construction checker")
    check("Final design-review handoff" in implementer
          and "Final code-review handoff" in implementer,
          "the retry summary omits one accepted checker handoff")
    check("first Design manifest" in implementer and "first code-checker manifest" in implementer,
          "the retry summary omits one accepted checker manifest")
    check("no accepted final checker obligation authorizes this retry report" in progress_source,
          "the shared retry diagnostic still names only code review")
    check("no accepted final code-review obligation authorizes this retry report"
          not in progress_source,
          "the stale code-only retry diagnostic remains present")
    for name, contract in (("design checker", checker), ("implementer", implementer),
                           ("construction mode", mode), ("skill", skill)):
        lowered = contract.lower()
        check("ten logical" in lowered or "ten rounds" in lowered,
              f"the {name} does not state the ten-round design bound")
        check("round 11" in lowered,
              f"the {name} does not forbid design round 11")
    for name, contract in (("implementer", implementer), ("construction mode", mode),
                           ("skill", skill)):
        check("design.review.resolved" in contract,
              f"the {name} does not carry the exact design settlement")
    check("Return one JSON object" in checker and "Return no prose outside it" in checker,
          "the design checker must have one strict result channel")
    check("result-validation refusal" in checker
          and "complete replacement JSON object" in checker
          and "current physical call" in checker,
          "the design checker must support one bounded same-call result repair")
    check("at most two repair requests" in implementer.lower()
          and "same open physical call" in implementer.lower()
          and "unusable:\"lost\"" in implementer,
          "the design result needs the bounded live repair route")
    check("C3.9a" in implementer and "not valid" in implementer.lower(),
          "an accepted pre-implementation Design defect must forbid C3.9a")
    check("Preserve `Disagreement` unchanged" in implementer,
          "an accepted final Design defect must not publish alternatives")
    for name, contract in (("implementer", implementer), ("construction mode", mode),
                           ("skill", skill)):
        check("stop" in contract.lower() and "accepted" in contract.lower()
              and "Design" in contract and "first Design manifest" in contract,
              f"the {name} does not preserve a stopped accepted Design obligation")


@test
def design_parity_invalid_result_repair_keeps_the_same_open_physical_call():
    seed_active_attempt()
    opening = open_design_round(1)
    invalid = write_design_result("invalid-design-result.json", {"verdict": "clean"})
    before = len(journal_lines())
    refused_after(
        run_progress(
            "subagent-ended", "design-checker", "--round", "1",
            "--data", json.dumps({"result": invalid}),
        ),
        before, "an invalid design result",
    )
    refused_after(
        run_progress("subagent-started", "design-checker", "--round", "1"),
        before, "another physical opening over the live repair call",
    )
    valid = write_design_result(
        "replacement-design-result.json", design_result_payload(opening),
    )
    accepted = run_progress(
        "subagent-ended", "design-checker", "--round", "1",
        "--data", json.dumps({"result": valid}),
    )
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)
    finish = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"design","outcome":"clean"}',
    )
    check(finish.returncode == 0, finish.stdout + finish.stderr)


@test
def design_parity_historical_consumers_reject_a_damaged_resolution():
    seed_active_attempt()
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1, "where": "Design step 1", "what": "The transition is absent.",
        "why": "The accepted outcome cannot occur.", "impact": "IMPORTANT", "previous": [],
    }])
    replace_current_design("Implement the accepted task contract and its transition.")
    resolve_design_round(1, [{"id": 1, "status": "corrected"}])
    journal = journal_lines()
    resolution = next(entry for entry in journal if entry.get("kind") == "design.review.resolved")
    resolution["data"]["items"][0]["evidence"] = ""
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0, "damaged durable design resolution passed history validation")


@test
def design_checker_consumes_the_exact_latest_result_once():
    seed_active_attempt()
    refused(run_progress("subagent-started", "design-checker", "--task", "4", "--round", "1"))
    refused(run_progress("subagent-started", "design-checker", "--round", "2"))

    opening = open_design_round(1)
    before = len(journal_lines())
    proc = run_progress(
        "note", "verdict.consumed", "--round", "1", "--data",
        '{"check":"design","outcome":"clean"}',
    )
    refused_after(proc, before, "a design verdict before the physical return")
    proc = run_progress(
        "subagent-ended", "code-checker", "--round", "1", "--data", '{"findings":2}',
    )
    refused_after(proc, before, "a physical return from the wrong checker")

    source = write_design_result(
        "two-design-findings.json",
        design_result_payload(opening, findings=[
            {"id": 1, "where": "Design step 1", "what": "The interface changes.",
             "why": "A caller breaks.", "impact": "IMPORTANT", "previous": []},
            {"id": 2, "where": "Design step 2", "what": "Required state is absent.",
             "why": "The task result is wrong.", "impact": "CRITICAL", "previous": []},
        ]),
    )
    proc = run_progress(
        "subagent-ended", "design-checker", "--round", "1", "--data",
        json.dumps({"result": source}),
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    before = len(journal_lines())
    proc = run_progress(
        "note", "verdict.consumed", "--round", "1", "--data",
        '{"check":"design","outcome":"clean"}',
    )
    refused_after(proc, before, "a clean verdict over positive findings")
    proc = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"design","outcome":"findings"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    consumed = journal_lines()[-1]
    check(consumed["data"]["findings"] == 2 and consumed["data"]["call"] == 1, consumed)
    before = len(journal_lines())
    duplicate = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"design","outcome":"findings"}',
    )
    refused_after(duplicate, before, "a duplicate design verdict")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)


@test
def code_checker_regenerates_under_one_logical_spend():
    seed_active_attempt()
    append_checker_verdict("design", lot="lot-1", task=3, attempt=2)
    gate = seed_review_gate()
    for args in (
        ("subagent-started", "code-checker", "--round", "1",
         "--data", json.dumps({"gate": gate})),
        ("note", "bound.spent", "--round", "1", "--text", "code checker round 1 of 10"),
    ):
        proc = run_progress(*args)
        check(proc.returncode == 0, proc.stdout + proc.stderr)
    before = len(journal_lines())
    open_again = run_progress(
        "subagent-started", "code-checker", "--round", "1",
        "--data", json.dumps({"gate": gate}),
    )
    refused_after(open_again, before, "regeneration beside a live physical call")

    proc = run_progress(
        "subagent-ended", "code-checker", "--round", "1", "--data", '{"unusable":"error"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    proc = run_progress(
        "subagent-started", "code-checker", "--round", "1",
        "--data", json.dumps({"gate": gate}),
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    started = [entry for entry in journal_lines()
               if entry.get("event") == "subagent-started"
               and entry.get("kind") == "code-checker"][-1]["data"]
    result = code_result_source(started)
    proc = run_progress(
        "subagent-ended", "code-checker", "--round", "1",
        "--data", json.dumps({"result": result}),
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    proc = run_progress(
        "note", "verdict.consumed", "--round", "1", "--data",
        '{"check":"code","outcome":"clean"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    entries = journal_lines()
    spends = [entry for entry in entries if entry.get("kind") == "bound.spent"
              and (entry.get("data") or {}).get("check") == "code"]
    starts = [entry for entry in entries if entry.get("event") == "subagent-started"
              and entry.get("kind") == "code-checker"]
    ends = [entry for entry in entries if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "code-checker"]
    check(len(spends) == 1 and len(starts) == len(ends) == 2, entries)
    check(entries[-1]["data"]["call"] == 2 and entries[-1]["data"]["findings"] == 0, entries[-1])
    stage_workspace_plan()
    proof = run_progress("construction-verdict-check", "code", "lot-1", "3", "2")
    check(proof.returncode == 0 and re.fullmatch(r"[0-9]+:[0-9a-f]{64}\n", proof.stdout),
          proof.stdout + proof.stderr)


@test
def code_checker_round_limit_still_stops_at_ten():
    seed_active_attempt()
    append_checker_verdict("design", lot="lot-1", task=3, attempt=2)

    for round_number in range(1, 10):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1, text="F1 remains actionable.",
        )

    append_code_correction(9)
    gate = seed_review_gate(round_number=10)
    for args in (
        ("subagent-started", "code-checker", "--round", "10",
         "--data", json.dumps({"gate": gate})),
        ("note", "bound.spent", "--round", "10", "--text", "code checker round 10 of 10"),
        ("subagent-ended", "code-checker", "--round", "10", "--data", '{"unusable":"lost"}'),
        ("subagent-started", "code-checker", "--round", "10",
         "--data", json.dumps({"gate": gate})),
    ):
        proc = run_progress(*args)
        check(proc.returncode == 0, proc.stdout + proc.stderr)
    started = [entry for entry in journal_lines()
               if entry.get("event") == "subagent-started"
               and entry.get("kind") == "code-checker"][-1]["data"]
    result = code_result_source(started, findings=1)
    for args in (
        ("subagent-ended", "code-checker", "--round", "10",
         "--data", json.dumps({"result": result})),
        ("note", "verdict.consumed", "--round", "10",
         "--data", '{"check":"code","outcome":"findings"}'),
    ):
        proc = run_progress(*args)
        check(proc.returncode == 0, proc.stdout + proc.stderr)

    before = len(journal_lines())
    refused_after(
        run_progress("subagent-started", "code-checker", "--round", "11"),
        before, "an eleventh logical code-checker round",
    )

@test
def code_checker_verdict_derives_exact_public_impact_counts():
    seed_active_attempt()
    append_checker_verdict(
        "code", lot="lot-1", task=3, attempt=2, round_number=1, findings=3,
        impacts=["CRITICAL", "IMPORTANT", "MINOR"],
    )
    ended = next(
        entry for entry in reversed(journal_lines())
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "code-checker"
    )["data"]
    verdict = next(
        entry for entry in reversed(journal_lines())
        if entry.get("kind") == "verdict.consumed"
        and (entry.get("data") or {}).get("check") == "code"
    )["data"]
    for data in (ended, verdict):
        check(data["findings"] == 3, data)
        check(data["critical"] == 1 and data["important"] == 1 and data["minor"] == 1,
              data)


@test
def code_round_ten_resolution_accounts_for_the_exact_findings_batch():
    seed_active_attempt()
    for round_number in range(1, 10):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1, text="Finding 1 remains actionable.",
        )
    append_checker_verdict(
        "code", lot="lot-1", task=3, attempt=2,
        round_number=10, findings=2,
        text="Finding 1 is disputed.\nFinding 2 is another valid implementation.\n",
    )

    incomplete_path = os.path.join(BASE, "incomplete-code-resolution.md")
    with open(incomplete_path, "w", encoding="utf-8") as target:
        target.write("## Finding 1 — refuted\nThe cited branch is not reachable.\n")
    before = len(journal_lines())
    incomplete = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", incomplete_path,
        "--data", '{"check":"code","items":[{"id":1,"status":"refuted"}]}',
    )
    refused_after(incomplete, before, "an incomplete final code-review resolution")

    mismatch_path = os.path.join(BASE, "mismatched-code-resolution.md")
    with open(mismatch_path, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — refuted\nThe cited branch is not reachable.\n\n"
            "## Finding 2 — accepted\nThe implementation drops the required retry.\n"
        )
    mismatch = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", mismatch_path,
        "--data", json.dumps({
            "check": "code",
            "items": [
                {"id": 1, "status": "refuted"},
                {"id": 2, "status": "alternative"},
            ],
        }),
    )
    refused_after(mismatch, before, "a final resolution whose text contradicts its item state")

    resolved_path = os.path.join(BASE, "resolved-code-review.md")
    with open(resolved_path, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — refuted\nThe cited branch is not reachable; the guard proves it.\n\n"
            "## Finding 2 — alternative\nBoth implementations satisfy the accepted retry contract.\n"
        )
    plan_path = os.path.join(WORKSPACE, "plans", "lot-1-plan.md")
    with open(plan_path, "a", encoding="utf-8") as target:
        target.write(
            "\n### Disagreement\n"
            "#### Finding 2 — code alternative\n"
            "Both implementations satisfy the accepted retry contract.\n"
        )
    resolved = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", resolved_path,
        "--data", json.dumps({
            "check": "code",
            "items": [
                {"id": 1, "status": "refuted"},
                {"id": 2, "status": "alternative"},
            ],
        }),
    )
    check(resolved.returncode == 0, resolved.stdout + resolved.stderr)
    terminal = journal_lines()[-1]
    check(terminal["kind"] == "code.review.resolved", terminal)
    check(terminal["data"]["findings"] == 2, terminal)
    check(terminal["data"]["accepted"] == 0, terminal)
    check(terminal["data"]["refuted"] == 1, terminal)
    check(terminal["data"]["alternative"] == 1, terminal)
    check(re.fullmatch(r"[0-9]+:[0-9a-f]{64}", terminal["data"]["verdict"]), terminal)

    stage_workspace_plan()
    proof = run_progress("construction-verdict-check", "code", "lot-1", "3", "2")
    check(proof.returncode == 0 and re.fullmatch(r"[0-9]+:[0-9a-f]{64}\n", proof.stdout),
          proof.stdout + proof.stderr)
    proof_index = int(proof.stdout.split(":", 1)[0])
    check(journal_lines()[proof_index]["kind"] == "code.review.resolved",
          "the final proof does not identify the implementer's resolution")

    before = len(journal_lines())
    duplicate = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", resolved_path,
        "--data", json.dumps({
            "check": "code",
            "items": [
                {"id": 1, "status": "refuted"},
                {"id": 2, "status": "alternative"},
            ],
        }),
    )
    refused_after(duplicate, before, "a duplicate final code-review resolution")


@test
def an_accepted_round_ten_defect_cannot_become_a_gate_proof():
    seed_active_attempt()
    for round_number in range(1, 11):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1, text="Finding 1 is a real defect.",
        )
    resolution_path = os.path.join(BASE, "accepted-code-defect.md")
    with open(resolution_path, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — accepted\nThe implementation drops the required retry.\n"
        )
    resolved = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", resolution_path,
        "--data", '{"check":"code","items":[{"id":1,"status":"accepted"}]}',
    )
    check(resolved.returncode == 0, resolved.stdout + resolved.stderr)
    proof = run_progress("construction-verdict-check", "code", "lot-1", "3", "2")
    check(proof.returncode != 0, "an accepted final defect became a final-gate proof")
    check("accepted" in proof.stdout.lower(), proof.stdout + proof.stderr)


@test
def a_damaged_historical_round_ten_resolution_fails_closed():
    seed_active_attempt()
    for round_number in range(1, 11):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1, text="Finding 1 is disputed.",
        )
    append_note(
        "code.review.resolved",
        {
            "check": "code", "lot": "lot-1", "task": 3, "attempt": 2, "round": 10,
            "verdict": f"0:{'0' * 64}", "findings": 1,
            "items": [{"id": 1, "status": "refuted"}],
            "accepted": 0, "refuted": 1, "alternative": 0,
        },
        "## Finding 1 — refuted\nThe exact evidence disproves the claim.\n",
        mode="construction", lot="lot-1", task=3, attempt=2, round=10,
    )
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0, "a damaged durable final resolution passed history audit")
    proof = run_progress("construction-verdict-check", "code", "lot-1", "3", "2")
    check(proof.returncode != 0, "a damaged durable final resolution became a gate proof")


@test
def code_checker_prompt_requires_an_exhaustive_batch_and_free_work_loops():
    checker = open(
        os.path.join(HERE, "prompts", "construction", "code-checker.md"),
        encoding="utf-8",
    ).read()
    implementer = open(
        os.path.join(HERE, "prompts", "construction", "implementer.md"),
        encoding="utf-8",
    ).read()
    mode = open(
        os.path.join(HERE, "prompts", "construction", "MODE.md"),
        encoding="utf-8",
    ).read()
    plan_format = open(
        os.path.join(HERE, "prompts", "construction", "plan-format.md"),
        encoding="utf-8",
    ).read()
    skill = open(os.path.join(HERE, "SKILL.md"), encoding="utf-8").read()
    checker_contract = " ".join(checker.split())
    implementer_contract = " ".join(implementer.split())
    mode_contract = " ".join(mode.split())
    plan_format_contract = " ".join(plan_format.split())
    skill_contract = " ".join(skill.split())

    for required in (
        "mandatory minimum, not an exhaustive list",
        "finite immutable code-review manifest",
        "Continue at the next byte offset until you read each declared byte",
        "Read the whole diff and every created file before you answer",
        "Do not stop at the first finding",
        "Return every independent finding in one batch",
        "Group findings only when they have the same root cause",
        "contiguous `Finding 1..N`",
        "previous-count <manifest>",
        "Mark it `still-open` otherwise",
        "Every still-open ID appears once",
        '"impact":"CRITICAL|IMPORTANT|MINOR"',
        "Your final message is only the complete JSON object",
    ):
        check(required in checker_contract, f"the code-checker contract lost: {required}")
    for required in (
        "code checker round <K> of 10",
        "Rounds 1 through 9",
        "one exact account",
        "corrected",
        "unchanged",
        "every prior finding and this exact account",
        "At round 10, settle the complete batch",
        "accepted",
        "refuted",
        "alternative",
        "code.review.resolved",
        "If any item is `accepted`",
        "If no item is `accepted`",
        "### Disagreement",
        "There is no eleventh logical round",
        "A red ordinary gate returns you to free work",
        "ordinary_gate.py <op>",
        "--data '{\"gate\":\"<ordinary gate op>\"}'",
        "--data '{\"result\":\"<result JSON file>\"}'",
        "Do not run `plan-publish.sh` again here",
    ):
        check(required in implementer_contract, f"the implementer contract lost: {required}")
    for required in (
        "Ten logical rounds at most",
        "Rounds 1 through 9",
        "complete correction account",
        "every prior finding for exact verification",
        "round 10",
        "accepted`, `refuted` or `alternative",
        "accepted defect fails through C3.9",
        "### Disagreement",
        "A red ordinary gate returns to free work",
    ):
        check(required in mode_contract, f"the construction mode contract lost: {required}")
    check("design-checker or code-checker round 10" in plan_format_contract,
          "the plan format does not carry both final-round disagreement routes")
    check("#### Finding N — design alternative" in plan_format_contract,
          "the plan format has no exact design-alternative ownership heading")
    check(
        "#### Finding N — code alternative" in plan_format_contract,
        "the plan format has no exact code-alternative ownership heading",
    )
    check(
        "Round 10 never allocates round 11" in skill_contract
        and "code.review.resolved" in skill_contract,
        "the global bounded-round contract lost the final code-review settlement",
    )


@test
def diagnostic_consumes_its_exact_classification_and_analysis():
    append_note(
        "attempt.failed", {"attempt": 2, "classification": "C3.9b"},
        lot="lot-1", task=3,
    )
    refused_after(
        run_progress("subagent-started", "diagnostic", "--task", "4"),
        1, "a diagnostic for the wrong failed task",
    )
    for args in (
        ("subagent-started", "diagnostic", "--task", "3"),
        ("note", "bound.spent", "--task", "3", "--text", "diagnostic ran - once per task"),
    ):
        proc = run_progress(*args)
        check(proc.returncode == 0, proc.stdout + proc.stderr)
    before = len(journal_lines())
    premature = run_progress(
        "note", "verdict.consumed", "--task", "3", "--text", "analysis",
        "--data", '{"check":"diagnostic","outcome":"C3.9b"}',
    )
    refused_after(premature, before, "a diagnostic verdict before its return")
    proc = run_progress(
        "subagent-ended", "diagnostic", "--task", "3", "--data", '{"classification":"C3.9b"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    before = len(journal_lines())
    mismatch = run_progress(
        "note", "verdict.consumed", "--task", "3", "--text", "analysis",
        "--data", '{"check":"diagnostic","outcome":"C3.9a"}',
    )
    refused_after(mismatch, before, "a mismatched diagnostic classification")
    missing = run_progress(
        "note", "verdict.consumed", "--task", "3",
        "--data", '{"check":"diagnostic","outcome":"C3.9b"}',
    )
    refused_after(missing, before, "a diagnostic verdict without exact analysis")
    analysis_path = os.path.join(BASE, "diagnostic-analysis.txt")
    with open(analysis_path, "w", encoding="utf-8") as target:
        target.write("The task boundary is wrong. Rebuild from task 2.\n")
    proc = run_progress(
        "note", "verdict.consumed", "--task", "3", "--text-file", analysis_path,
        "--data", '{"check":"diagnostic","outcome":"C3.9b"}',
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    consumed = journal_lines()[-1]
    check(consumed["attempt"] == 2 and "round" not in consumed, consumed)
    before = len(journal_lines())
    duplicate = run_progress(
        "note", "verdict.consumed", "--task", "3", "--text-file", analysis_path,
        "--data", '{"check":"diagnostic","outcome":"C3.9b"}',
    )
    refused_after(duplicate, before, "a duplicate diagnostic verdict")
    append_note(
        "attempt.failed", {"attempt": 3, "classification": "C3.9b"},
        lot="lot-1", task=3,
    )
    before = len(journal_lines())
    repeated = run_progress("subagent-started", "diagnostic", "--task", "3")
    refused_after(repeated, before, "a second logical diagnostic for the same task")


@test
def damaged_historical_construction_verdicts_fail_closed():
    append_note(
        "verdict.consumed", {"check": "design", "outcome": "clean"},
        lot="lot-1", task=3, attempt=2, round=1,
    )
    proc = run_progress("construction-verdict-check", "history")
    check(proc.returncode != 0, "a historical unproved design verdict passed")

    reset()
    append_note(
        "verdict.consumed", {"check": "code", "outcome": "clean"},
        lot="lot-1", task=3, attempt=2, round=1,
    )
    proc = run_progress("construction-verdict-check", "code", "lot-1", "3", "2")
    check(proc.returncode != 0, "a historical unproved code verdict became a gate proof")

    reset()
    append_note(
        "verdict.consumed", {"check": "diagnostic", "outcome": "C3.9b"}, "analysis",
        lot="lot-1", task=3, attempt=2,
    )
    proc = run_progress("construction-verdict-check", "history")
    check(proc.returncode != 0, "a historical unproved diagnostic verdict passed")

    reset()
    append_note("verdict.consumed", {"check": "invented", "outcome": "clean"})
    proc = run_progress("construction-verdict-check", "history")
    check(proc.returncode != 0, "a historical unknown checker verdict was ignored")


@test
def diagnostic_contract_separates_invented_and_unmet_dependencies():
    diagnostic_path = os.path.join(HERE, "prompts", "construction", "diagnostic.md")
    mode_path = os.path.join(HERE, "prompts", "construction", "MODE.md")
    implementer_path = os.path.join(HERE, "prompts", "construction", "implementer.md")
    skill_path = os.path.join(HERE, "SKILL.md")
    with open(diagnostic_path, encoding="utf-8") as source:
        diagnostic = source.read()
    with open(mode_path, encoding="utf-8") as source:
        mode = source.read()
    with open(implementer_path, encoding="utf-8") as source:
        implementer = source.read()
    with open(skill_path, encoding="utf-8") as source:
        skill = source.read()
    contract = "\n".join((diagnostic, mode, implementer, skill))
    contract_flat = " ".join(contract.split())

    required = (
        "C3.9c` — an earlier task's accepted obligation was wrong or unmet",
        "Quote the exact obligation from K's controller-owned plan section or accepted",
        "A missing or different shape without that prior obligation is not `C3.9c`",
        "This includes a dependency that this design invented and no earlier accepted obligation promised",
        "accepted contract require a dependency that no task's accepted obligation owns?** If yes → `C3.9d`",
        "Two attempts can make the same coding mistake against a sound design",
        "Repetition does not count against this classification",
        "Repetition does not prove which classification is correct",
    )
    for value in required:
        check(value in contract_flat, f"the diagnostic contract lost: {value}")

    ordered_questions = (
        "Does one named earlier task have an exact accepted obligation",
        "Does this task's controller-owned accepted contract require a dependency",
        "Could this task be built at all, in this position, by any design?",
        "Did only the current design invent the missing dependency",
        "Does the current design otherwise assume something the tree contradicts?",
        "Otherwise → `C3.9a`",
    )
    positions = [diagnostic.index(question) for question in ordered_questions]
    check(positions == sorted(positions), "the diagnostic decision questions changed order")

    for forbidden in (
        "least likely answer",
        "so it was wrong, or the second attempt would not have repeated",
        "failing the same way means the classification was wrong",
    ):
        check(forbidden not in contract,
              f"repeated failure still claims to prove the prior classification: {forbidden}")


@test
def note_records_text_and_caller_context():
    line = the_line(run_progress("note", "ruling", "--text", "The human chose the second option"))
    check(line["event"] == "note" and line["kind"] == "ruling", line)
    check(line["text"] == "The human chose the second option", line)
    check(line["mode"] == "construction" and line["task"] == 3 and line["job"] == "controller",
          f"context must come from the CALLER's annotations: {line}")
    check("data" not in line, "no --data: no data field")
    check("feature" not in line and "status" not in line,
          "only the seven context fields belong on the line")


@test
def note_text_file_preserves_eof_and_shell_looking_lines_exactly():
    sentinel = os.path.join(BASE, "journal-text-executed")
    payload = f"first line\nEOF\ntouch {sentinel}\n`printf danger`\nlast line\n"
    text_file = os.path.join(BASE, "journal-text.txt")
    with open(text_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    line = the_line(run_progress("note", "ruling", "--text-file", text_file))
    check(line["text"] == payload, f"the file transport changed the exact payload: {line['text']!r}")
    check(not os.path.exists(sentinel), "a shell-looking journal line executed")


@test
def note_text_sources_are_exclusive_and_ordinary_multiline_still_works():
    text_file = os.path.join(BASE, "ordinary-journal-text.txt")
    payload = "one\ntwo\n"
    with open(text_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    refused(run_progress("note", "ruling", "--text", "one", "--text-file", text_file))
    line = the_line(run_progress("note", "ruling", "--text-file", text_file))
    check(line["text"] == payload, line)


@test
def worker_cli_file_transport_preserves_eof_without_execution():
    sentinel = os.path.join(BASE, "worker-message-executed")
    payload = f"result\nEOF\ntouch {sentinel}\n$(printf danger)\nfinished\n"
    message_file = os.path.join(BASE, "worker-message.txt")
    capture = os.path.join(BASE, "worker-message-captured.txt")
    receiver = os.path.join(BASE, "fake-send-message.py")
    with open(message_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    with open(receiver, "w", encoding="utf-8") as handle:
        handle.write(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_bytes(pathlib.Path(sys.argv[4]).read_bytes())\n"
        )
    os.chmod(receiver, 0o700)
    env = dict(ENV)
    env.update({"MESSAGE_FILE": message_file, "CAPTURE": capture, "RECEIVER": receiver})
    proc = subprocess.run(
        ["bash", "-c",
         '"$RECEIVER" "$CAPTURE" send-message parent "$MESSAGE_FILE"; '
         'rc=$?; rm -f -- "$MESSAGE_FILE"; exit "$rc"'],
        capture_output=True, text=True, env=env, timeout=120,
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    with open(capture, encoding="utf-8", newline="") as handle:
        check(handle.read() == payload, "the worker fallback changed the exact message")
    check(not os.path.exists(sentinel), "a shell-looking worker message line executed")
    check(not os.path.exists(message_file), "the consumed worker message file remains")


@test
def current_markdown_has_no_fixed_eof_payload_heredoc():
    offenders = []
    for root, _, files in os.walk(HERE):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            if "<<'EOF'" in content or '<<"EOF"' in content or "<<EOF" in content:
                offenders.append(os.path.relpath(path, HERE))
    check(not offenders, f"fixed EOF payload heredocs remain in workflow Markdown: {offenders}")


@test
def note_without_text_is_complete():
    line = the_line(run_progress("note", "resumed"))
    check(line["kind"] == "resumed", line)
    check("text" not in line and "data" not in line,
          "absent values must be omitted, never null or empty")


@test
def note_accepts_context_flags():
    # spec/MODE.md and product-review/MODE.md call `note report.received --mandate <slug>`.
    line = the_line(run_progress("note", "report.received", "--mandate", "verifier",
                                 "--data", '{"critical":0,"important":3}'))
    check(line["mandate"] == "verifier", line)
    check(line["data"] == {"critical": 0, "important": 3}, line)


@test
def note_unknown_kind_is_refused():
    refused(run_progress("note", "run.finished", "--text", "nope"))


@test
def malformed_data_is_refused():
    proc = run_progress("note", "ruling", "--data", "{broken")
    refused(proc)
    check("JSON" in proc.stdout, "the error must name the malformed JSON")
    refused(run_progress("subagent-ended", "diagnostic", "--data", "not json"))


@test
def non_object_data_is_refused():
    # Valid JSON is not enough: `data` carries named values, and a list or a
    # bare string is the signature of free text sent through the wrong flag.
    for raw in ("[1,2]", '"free text"', "3", "true", "null"):
        proc = run_progress("note", "ruling", "--data", raw)
        refused(proc)
        check("object" in proc.stdout, f"the error must say an object was expected (got: {raw})")
    refused(run_progress("subagent-ended", "diagnostic", "--data", "[]"))


# -------------------------------------------- structured authority admission

@test
def direct_recheck_requires_its_exact_bound_commit_and_complete_proof():
    state_path = seed_direct_ruling()
    sha = "a" * 40
    report_path = "reports/answers/R1-recheck.md"
    report_sha = write_report(report_path, "direct accepted recheck\n")
    action = [{"answer": "R1", "status": "active", "route": "spec-in-place"}]
    base = recheck_data("R1", "edit-r1", sha, action, artifact_sha=report_sha)

    invented_closed = dict(base)
    invented_closed["actions"] = [
        {"answer": "R1", "status": "active", "route": "closed"},
    ]
    before = len(journal_lines())
    missing_commit = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(invented_closed),
        "--text", report_path,
    )
    check(missing_commit.returncode != 0 and len(journal_lines()) == before,
          "an unbound direct recheck was accepted")

    seed_bound_commit(
        "R1", "edit-r1", sha, state_kind="ruling.ready", state_ref="R1",
        state_path=state_path,
    )
    for changed, reason in (
        ({"sha": "b" * 40}, "wrong commit SHA"),
        ({"actions": []}, "incomplete action state"),
        ({"accepted": True, "missing": ["R1"]}, "inconsistent accepted result"),
    ):
        candidate = dict(base)
        candidate.update(changed)
        before = len(journal_lines())
        proc = run_progress(
            "note", "decision.recheck.completed", "--data", json.dumps(candidate),
            "--text", report_path,
        )
        check(proc.returncode != 0 and len(journal_lines()) == before,
              f"a direct recheck with {reason} was accepted")

    write_report(report_path, "changed after hashing\n")
    changed = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(base),
        "--text", report_path,
    )
    check(changed.returncode != 0, "a direct recheck with changed proof bytes was accepted")
    write_report(report_path, "direct accepted recheck\n")
    valid = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(base),
        "--text", report_path,
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)

    authority_sha = file_sha256(state_path)
    terminal = {
        "answer": "R1", "ruling": "R1", "route": "spec-in-place",
        "sha": sha, "recheck_op": "edit-r1", "authority_kind": "ruling.ready",
        "authority_ref": "R1", "authority_sha256": authority_sha,
    }
    closed = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(closed.returncode == 0, closed.stdout + closed.stderr)


@test
def direct_recheck_rejects_a_commit_bound_to_the_wrong_generation():
    state_path = seed_direct_ruling()
    sha = "a" * 40
    seed_bound_commit(
        "R1", "edit-r1", sha, state_kind="ruling.ready", state_ref="R999",
        state_path=state_path,
    )
    report_path = "reports/answers/R1-recheck.md"
    report_sha = write_report(report_path, "wrong-generation recheck\n")
    candidate = recheck_data(
        "R1", "edit-r1", sha,
        [{"answer": "R1", "status": "active", "route": "spec-in-place"}],
        artifact_sha=report_sha,
    )
    before = len(journal_lines())
    proc = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(candidate),
        "--text", report_path,
    )
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "a direct recheck consumed a commit bound to the wrong authority generation")


@test
def adverse_bound_recheck_is_durable_but_cannot_route_before_its_breach():
    state_path = seed_direct_ruling()
    sha = "a" * 40
    seed_bound_commit(
        "R1", "edit-r1", sha, state_kind="ruling.ready", state_ref="R1",
        state_path=state_path,
    )
    report_path = "reports/answers/R1-adverse.md"
    report_sha = write_report(report_path, "direct adverse recheck\n")
    adverse = recheck_data(
        "R1", "edit-r1", sha,
        [{"answer": "R1", "status": "active", "route": "spec-in-place"}],
        artifact_sha=report_sha, accepted=False, missing=["R1"],
    )
    recorded = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(adverse),
        "--text", report_path,
    )
    check(recorded.returncode == 0, recorded.stdout + recorded.stderr)
    state_sha = file_sha256(state_path)
    terminal = {
        "answer": "R1", "ruling": "R1", "route": "spec-in-place",
        "sha": sha, "recheck_op": "edit-r1", "authority_kind": "ruling.ready",
        "authority_ref": "R1", "authority_sha256": state_sha,
    }
    before = len(journal_lines())
    blocked = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(blocked.returncode != 0 and len(journal_lines()) == before,
          "an adverse bound recheck allowed its old route to terminalize")


@test
def batch_recheck_requires_the_exact_commit_and_every_owner_action():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"},
               {"id": "D2", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "spec-in-place"},
                 {"id": "D2", "choice": "O2", "route": "closed"}],
    )
    sha = "b" * 40
    state_path = "reports/product-review/lot-1/lot-1-decision-batch-1-actions.md"
    report_path = "reports/product-review/lot-1/batch-recheck.md"
    report_sha = write_report(report_path, "batch accepted recheck\n")
    actions = [
        {"answer": "B1/D1", "status": "active", "route": "spec-in-place"},
        {"answer": "B1/D2", "status": "active", "route": "closed"},
    ]
    items = [{"id": "D1", "verdict": "confirmed"},
             {"id": "D2", "verdict": "confirmed"}]
    base = recheck_data(
        "B1/D1", "edit-b1", sha, actions, artifact_sha=report_sha,
        batch=1, decision="D1", items=items,
    )
    invented_closed = dict(base)
    invented_closed["actions"] = [
        {"answer": "B1/D1", "status": "active", "route": "closed"},
        actions[1],
    ]
    before = len(journal_lines())
    no_commit = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(invented_closed),
        "--text", report_path,
    )
    check(no_commit.returncode != 0 and len(journal_lines()) == before,
          "an unbound batch recheck was accepted")

    seed_bound_commit(
        "B1/D1", "edit-b1", sha, state_kind="decision.batch.ready",
        state_ref="B1", state_path=state_path, batch=1, decision="D1",
    )
    for changed, reason in (
        ({"sha": "c" * 40}, "wrong commit SHA"),
        ({"actions": actions[:1]}, "omitted owner action"),
        ({"actions": actions + [{"answer": "B1/D3", "status": "active",
                                  "route": "closed"}]}, "added owner action"),
    ):
        candidate = dict(base)
        candidate.update(changed)
        before = len(journal_lines())
        proc = run_progress(
            "note", "decision.recheck.completed", "--data", json.dumps(candidate),
            "--text", report_path,
        )
        check(proc.returncode != 0 and len(journal_lines()) == before,
              f"a batch recheck with {reason} was accepted")
    valid = run_progress(
        "note", "decision.recheck.completed", "--data", json.dumps(base),
        "--text", report_path,
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)


@test
def conflict_ready_is_the_exact_settled_complete_owner_state():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"},
               {"id": "D2", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"},
                 {"id": "D2", "choice": "O2", "route": "closed"}],
    )
    source_path = "reports/answers/B1-conflict-1-source.md"
    ready_path = "reports/answers/B1-conflict-1-resolution.md"
    write_report(source_path, "conflict source\n")
    ready_sha = write_report(ready_path, "conflict resolution\n")
    opening = {
        "owner": "B1", "conflict": 1, "state_kind": "decision.batch.ready",
        "state_ref": "B1", "ids": ["B1/D1", "B1/D2"],
    }
    proc = run_progress("note", "decision.conflict.opened", "--data", json.dumps(opening))
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    sourced = run_progress(
        "note", "decision.conflict.sourced",
        "--data", '{"owner":"B1","conflict":1}', "--text", source_path,
    )
    check(sourced.returncode == 0, sourced.stdout + sourced.stderr)

    omitted = {
        "owner": "B1", "conflict": 1,
        "updates": [{"id": "B1/D1", "action": "qualify", "status": "active",
                     "route": "amendment"}],
    }
    before = len(journal_lines())
    bad_settlement = run_progress(
        "note", "decision.conflict.settled", "--data", json.dumps(omitted),
        "--text", "partial human answer",
    )
    check(bad_settlement.returncode != 0 and len(journal_lines()) == before,
          "a settlement omitted one opened conflict identity")
    settlement = {
        "owner": "B1", "conflict": 1,
        "updates": [
            {"id": "B1/D1", "action": "qualify", "status": "active",
             "route": "amendment"},
            {"id": "B1/D2", "action": "keep", "status": "active", "route": "closed"},
        ],
    }
    settled = run_progress(
        "note", "decision.conflict.settled", "--data", json.dumps(settlement),
        "--text", "the complete human resolution",
    )
    check(settled.returncode == 0, settled.stdout + settled.stderr)

    valid_actions = [
        {"answer": "B1/D1", "status": "active", "route": "amendment"},
        {"answer": "B1/D2", "status": "active", "route": "closed"},
    ]
    candidates = (
        (valid_actions[:1], "omitted unchanged owner answer"),
        (valid_actions + [{"answer": "B1/D3", "status": "active", "route": "closed"}],
         "added owner answer"),
        ([{"answer": "B1/D1", "status": "active", "route": "closed"}, valid_actions[1]],
         "action contradicting the settlement"),
    )
    for actions, reason in candidates:
        data = {"owner": "B1", "conflict": 1, "actions": actions,
                "artifact_sha256": ready_sha}
        before = len(journal_lines())
        proc = run_progress(
            "note", "decision.conflict.ready", "--data", json.dumps(data),
            "--text", ready_path,
        )
        check(proc.returncode != 0 and len(journal_lines()) == before,
              f"a conflict ready state with {reason} was accepted")

    ready_data = {"owner": "B1", "conflict": 1, "actions": valid_actions,
                  "artifact_sha256": ready_sha}
    ready = run_progress(
        "note", "decision.conflict.ready", "--data", json.dumps(ready_data),
        "--text", ready_path,
    )
    check(ready.returncode == 0, ready.stdout + ready.stderr)
    seed_amendment_context()
    write_report(ready_path, "changed conflict resolution\n")
    opening_data = grouped_open_data(
        members=["B1/D1"], state_kind="decision.conflict.ready", state_ref="B1/C1",
    )
    before = len(journal_lines())
    changed = run_progress(
        "note", "amendment.opened", "--data", json.dumps(opening_data),
        "--text", "apply B1/D1 and return to product review",
    )
    check(changed.returncode != 0 and len(journal_lines()) == before,
          "a changed conflict artifact authorised a grouped amendment")
    write_report(ready_path, "conflict resolution\n")
    valid_opening = run_progress(
        "note", "amendment.opened", "--data", json.dumps(opening_data),
        "--text", "apply B1/D1 and return to product review",
    )
    check(valid_opening.returncode == 0, valid_opening.stdout + valid_opening.stderr)


@test
def direct_conflict_ready_can_route_only_its_settled_owner_state():
    seed_direct_ruling(ruling="R1", route="closed")
    seed_direct_ruling(ruling="R2", route="closed")
    ready_path, ready_sha = append_conflict_generation(
        "R1", 1, ["R1", "R2"],
        [{"id": "R1", "action": "qualify", "status": "active", "route": "amendment"},
         {"id": "R2", "action": "keep", "status": "active", "route": "closed"}],
        [{"answer": "R1", "status": "active", "route": "amendment"}],
        state_kind="ruling.ready", state_ref="R1",
    )
    opening = {
        "amendment": 1, "origin": "product-review", "built": "lot-1", "ruling": "R1",
        "authority_kind": "decision.conflict.ready", "authority_ref": "R1/C1",
        "authority_sha256": ready_sha,
    }
    seed_amendment_context()
    proc = run_progress(
        "note", "amendment.opened", "--data", json.dumps(opening),
        "--text", "apply R1 and return to product review",
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check(os.path.isfile(os.path.join(WORKSPACE, *ready_path.split("/"))),
          "the valid direct conflict authority artifact disappeared")


@test
def spec_edit_auth_fails_closed_on_an_unbound_historical_recheck():
    spec_edit = load_common_module("spec_edit_auth")
    seed_direct_ruling()
    append_note("decision.recheck.completed", {
        "owner": "R1", "sha": "a" * 40, "commit_op": "missing-edit",
        "accepted": True, "missing": [], "artifact_sha256": "b" * 64,
        "actions": [{"answer": "R1", "status": "active", "route": "closed"}],
    }, "reports/answers/unbound-recheck.md")
    append_note("spec.edit.ready", {
        "op": "next-edit", "owner": "R1", "status": "active", "route": "spec-in-place",
        "state_kind": "ruling.ready", "state_ref": "R1", "source_sha": "c" * 40,
        "spec_path_sha256": "d" * 64, "artifact_sha256": "e" * 64,
    }, "reports/answers/R1-state.md")
    notes = list(enumerate(journal_lines(), 1))
    try:
        spec_edit.validate_no_unfinished_authority(
            notes, len(notes) - 1, "ruling", "R1"
        )
    except SystemExit:
        pass
    else:
        raise AssertionError("spec_edit_auth consumed an unbound historical recheck")


# ------------------------------------------------------- batch terminals

@test
def batch_supplement_cannot_change_another_batch_local_decision():
    spec_edit = load_common_module("spec_edit_auth")

    def entry(kind, data):
        return 0, {"event": "note", "kind": kind, "data": data}

    notes = [
        entry("decision.batch.opened", {"batch": 1}),
        entry("decision.batch.sourced", {"batch": 1, "decisions": ["D1"]}),
        entry("decision.batch.settled", {"batch": 1, "answers": []}),
        entry("decision.batch.ready", {"batch": 1}),
        entry("decision.batch.opened", {"batch": 2}),
        entry("decision.batch.sourced", {"batch": 2, "decisions": ["D1"]}),
        entry("decision.batch.settled", {
            "batch": 2, "answers": [{"id": "D1", "route": "closed"}],
        }),
        entry("decision.batch.ready", {"batch": 2}),
        entry("decision.batch.supplemented", {
            "batch": 1, "after_op": "op-b1",
            "answers": [{"id": "D1", "route": "spec-in-place"}],
        }),
    ]
    route, status = spec_edit.current_route(notes, len(notes), "B2/D1")
    check((route, status) == ("closed", "active"),
          f"B1's local D1 supplement changed B2/D1: {(route, status)}")


@test
def batch_source_requires_the_complete_structured_item_index():
    opened = run_progress(
        "note", "decision.batch.opened", "--data", '{"batch":1,"built":"lot-1"}',
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    before = len(journal_lines())
    sourced = run_progress(
        "note", "decision.batch.sourced",
        "--data", '{"batch":1,"decisions":["D1"]}',
        "--text", "reports/product-review/lot-1/source.md",
    )
    check(sourced.returncode != 0 and len(journal_lines()) == before,
          "a batch source without the complete F/D verdict index was accepted")


@test
def batch_terminal_rejects_unknown_identity_and_route():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"}],
    )
    before = len(journal_lines())
    proc = run_progress(
        "note", "ruling.applied",
        "--data", '{"answer":"B1/D999","batch":1,"decision":"D999",'
                  '"route":"teleport","sha":"not-a-sha"}',
    )
    check(proc.returncode != 0, "an invented batch terminal was accepted")
    check(len(journal_lines()) == before, "the invented batch terminal reached the journal")


@test
def closed_batch_terminal_is_current_and_unique():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"}],
    )
    data = '{"answer":"B1/D1","batch":1,"decision":"D1","route":"closed"}'
    proc = run_progress("note", "ruling.applied", "--data", data)
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    before = len(journal_lines())
    duplicate = run_progress("note", "ruling.applied", "--data", data)
    check(duplicate.returncode != 0, "a duplicate batch terminal was accepted")
    check(len(journal_lines()) == before, "the duplicate batch terminal reached the journal")


@test
def batch_spec_terminal_requires_its_exact_commit_and_current_recheck():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "spec-in-place"}],
    )
    sha = "a" * 40
    data = (f'{{"answer":"B1/D1","batch":1,"decision":"D1","route":"spec-in-place",'
            f'"sha":"{sha}","recheck_op":"edit-1"}}')
    before = len(journal_lines())
    proc = run_progress("note", "ruling.applied", "--data", data)
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "a batch spec terminal without proof was accepted")

    state_path = "reports/product-review/lot-1/lot-1-decision-batch-1-actions.md"
    seed_bound_commit(
        "B1/D1", "edit-1", sha, state_kind="decision.batch.ready",
        state_ref="B1", state_path=state_path, batch=1, decision="D1",
    )
    recheck_path = "reports/product-review/lot-1/recheck.md"
    recheck_sha = write_report(recheck_path, "complete batch recheck\n")
    before = len(journal_lines())
    incomplete = run_progress(
        "note", "decision.recheck.completed",
        "--data", (f'{{"batch":1,"decision":"D1","commit_op":"edit-1","sha":"{sha}",'
                   f'"accepted":true,"missing":[],"artifact_sha256":"{recheck_sha}",'
                   '"actions":[{"answer":"B1/D1","status":"active",'
                   '"route":"spec-in-place"}]}'),
        "--text", recheck_path,
    )
    check(incomplete.returncode != 0 and len(journal_lines()) == before,
          "a batch recheck without its complete item replacement index was accepted")
    complete = recheck_data(
        "B1/D1", "edit-1", sha,
        [{"answer": "B1/D1", "status": "active", "route": "spec-in-place"}],
        artifact_sha=recheck_sha, batch=1, decision="D1",
        items=[{"id": "D1", "verdict": "confirmed"}],
    )
    append_note("decision.recheck.completed", complete, recheck_path)
    proc = run_progress("note", "ruling.applied", "--data", data)
    check(proc.returncode == 0, proc.stdout + proc.stderr)


@test
def batch_amendment_terminal_requires_the_grouped_landing():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "amendment"}],
    )
    sha = "b" * 40
    data = (f'{{"answer":"B1/D1","batch":1,"decision":"D1","route":"amendment",'
            f'"amendment":1,"sha":"{sha}"}}')
    proc = run_progress("note", "ruling.applied", "--data", data)
    check(proc.returncode != 0, "an amendment terminal without a grouped landing was accepted")
    sha = seed_clean_amendment_landing(grouped_open_data(), "apply B1/D1; return to review")
    data = (f'{{"answer":"B1/D1","batch":1,"decision":"D1","route":"amendment",'
            f'"amendment":1,"sha":"{sha}"}}')
    proc = run_progress("note", "ruling.applied", "--data", data)
    check(proc.returncode == 0, proc.stdout + proc.stderr)


@test
def grouped_amendment_opening_requires_the_exact_current_member_set():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"},
               {"id": "D2", "verdict": "confirmed"},
               {"id": "D3", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "amendment"},
                 {"id": "D2", "choice": "O2", "route": "amendment"},
                 {"id": "D3", "choice": "O3", "route": "closed"}],
    )
    seed_amendment_context()
    before = len(journal_lines())
    for members, reason in (
        ([], "zero-member grouped amendment"),
        (["B1/D1"], "grouped amendment that omits D2"),
        (["B1/D1", "B1/D2", "B1/D3"], "grouped amendment that adds closed D3"),
    ):
        proc = run_progress(
            "note", "amendment.opened", "--data",
            json.dumps(grouped_open_data(members=members), separators=(",", ":")),
            "--text", "apply the grouped answers; return to review",
        )
        check(proc.returncode != 0 and len(journal_lines()) == before,
              f"the {reason} was accepted")

    invented = grouped_open_data(members=["B1/D1", "B1/D2"], state_ref="B999")
    proc = run_progress(
        "note", "amendment.opened", "--data", json.dumps(invented, separators=(",", ":")),
        "--text", "apply the grouped answers; return to review",
    )
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "an invented batch authority generation opened an amendment")

    exact = grouped_open_data(members=["B1/D1", "B1/D2"])
    proc = run_progress(
        "note", "amendment.opened", "--data", json.dumps(exact, separators=(",", ":")),
        "--text", "apply the grouped answers; return to review",
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    duplicate = grouped_open_data(amendment=2, members=["B1/D1", "B1/D2"])
    proc = run_progress(
        "note", "amendment.opened", "--data", json.dumps(duplicate, separators=(",", ":")),
        "--text", "apply the grouped answers again; return to review",
    )
    check(proc.returncode != 0, "one batch authority generation opened two amendments")


@test
def grouped_amendment_terminal_rejects_a_stale_opening_generation():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "amendment"}],
    )
    opening = grouped_open_data()
    sha = seed_clean_amendment_landing(opening, "apply B1/D1; return to review")
    append_conflict_generation(
        "B1", 1, ["B1/D1"],
        [{"id": "B1/D1", "action": "qualify", "status": "active",
          "route": "amendment"}],
        [{"answer": "B1/D1", "status": "active", "route": "amendment"}],
        state_kind="decision.batch.ready", state_ref="B1",
    )
    terminal = {
        "answer": "B1/D1", "batch": 1, "decision": "D1", "route": "amendment",
        "amendment": 1, "sha": sha, "conflict": 1,
    }
    before = len(journal_lines())
    proc = run_progress(
        "note", "ruling.applied", "--data", json.dumps(terminal, separators=(",", ":")),
    )
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "a later authority generation did not stale the grouped opening")


@test
def grouped_amendment_terminals_consume_the_opening_membership():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"},
               {"id": "D2", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "amendment"},
                 {"id": "D2", "choice": "O2", "route": "amendment"}],
    )
    # Reproduce RV-015 through a damaged journal: the opening itself omits D2.
    append_note("amendment.opened", grouped_open_data(members=["B1/D1"]))
    append_note("amendment.committed", {"amendment": 1, "sha": "b" * 40})
    d2 = {
        "answer": "B1/D2", "batch": 1, "decision": "D2", "route": "amendment",
        "amendment": 1, "sha": "b" * 40,
    }
    before = len(journal_lines())
    proc = run_progress(
        "note", "ruling.applied", "--data", json.dumps(d2, separators=(",", ":")),
    )
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "D2 received a terminal from an opening that omitted it")


@test
def grouped_amendment_exact_commit_closes_every_named_member_once():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"},
               {"id": "D2", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "amendment"},
                 {"id": "D2", "choice": "O2", "route": "amendment"}],
    )
    opening = grouped_open_data(members=["B1/D1", "B1/D2"])
    sha = seed_clean_amendment_landing(opening, "apply B1/D1 and B1/D2; return to review")
    terminals = []
    for decision in ("D1", "D2"):
        terminal = {
            "answer": f"B1/{decision}", "batch": 1, "decision": decision,
            "route": "amendment", "amendment": 1, "sha": sha,
        }
        terminals.append(terminal)
        proc = run_progress(
            "note", "ruling.applied", "--data", json.dumps(terminal, separators=(",", ":")),
        )
        check(proc.returncode == 0, proc.stdout + proc.stderr)
    duplicate = run_progress(
        "note", "ruling.applied", "--data", json.dumps(terminals[0], separators=(",", ":")),
    )
    check(duplicate.returncode != 0, "D1 received a duplicate grouped-amendment terminal")


@test
def superseded_batch_answer_cannot_receive_a_terminal():
    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"}],
    )
    append_conflict_generation(
        "B1", 1, ["B1/D1"],
        [{"id": "B1/D1", "action": "supersede", "status": "superseded",
          "by": "R1"}],
        [{"answer": "B1/D1", "status": "superseded"}],
        state_kind="decision.batch.ready", state_ref="B1",
    )
    proc = run_progress(
        "note", "ruling.applied",
        "--data", '{"answer":"B1/D1","batch":1,"decision":"D1",'
                  '"route":"closed","conflict":1}',
    )
    check(proc.returncode != 0, "a superseded batch answer received a terminal")


@test
def batch_close_authenticates_pass_work_and_confirmed_carries():
    seed_batch(
        items=[{"id": "F1", "verdict": "confirmed"},
               {"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "sublot"}],
    )
    seed_review_pass(confirmed=1)
    append_note(
        "sublot.allocated",
        allocation_data(carries=["B1/F1", "B1/D1"]),
        text="lot-1.1",
    )
    write_confirmed("lot-1", ["batch 1/F1"])
    pass_close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(pass_close.returncode != 0,
          "a pass close omitted its current D work from the confirmed artifact")
    write_confirmed("lot-1", ["batch 1/F1", "B1/D1"])
    pass_close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(pass_close.returncode == 0, pass_close.stdout + pass_close.stderr)
    terminal = run_progress(
        "note", "ruling.applied",
        "--data", '{"answer":"B1/D1","batch":1,"decision":"D1",'
                  '"route":"sublot","lot":"lot-1.1"}',
    )
    check(terminal.returncode == 0, terminal.stdout + terminal.stderr)
    close_data = '{"batch":1,"outcome":"sublot","lot":"lot-1.1"}'
    proc = run_progress("note", "decision.batch.closed", "--data", close_data)
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    duplicate = run_progress("note", "decision.batch.closed", "--data", close_data)
    check(duplicate.returncode != 0, "a duplicate batch close was accepted")


@test
def no_correction_batch_close_requires_the_zero_pass_close():
    seed_batch(
        items=[{"id": "F1", "verdict": "refuted"},
               {"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"}],
    )
    terminal = run_progress(
        "note", "ruling.applied",
        "--data", '{"answer":"B1/D1","batch":1,"decision":"D1","route":"closed"}',
    )
    check(terminal.returncode == 0, terminal.stdout + terminal.stderr)
    before = len(journal_lines())
    premature = run_progress(
        "note", "decision.batch.closed",
        "--data", '{"batch":1,"outcome":"no-correction"}',
    )
    check(premature.returncode != 0 and len(journal_lines()) == before,
          "a no-correction batch close preceded its pass close")
    reviewed = seed_review_pass(commit="e" * 40)
    pass_close = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(pass_close.returncode == 0, pass_close.stdout + pass_close.stderr)
    close = run_progress(
        "note", "decision.batch.closed",
        "--data", '{"batch":1,"outcome":"no-correction"}',
    )
    check(close.returncode == 0, close.stdout + close.stderr)
    delivery = run_progress(
        "note", "lot.delivered", "--data", json.dumps({"sha": reviewed, "passes": 1}),
    )
    check(delivery.returncode == 0, delivery.stdout + delivery.stderr)


@test
def batch_close_rejects_malformed_identity_and_unproved_prior_terminal():
    malformed = run_progress(
        "note", "decision.batch.closed",
        "--data", '{"batch":"not-an-integer","outcome":"invented","lot":"lot-999"}',
    )
    check(malformed.returncode != 0 and journal_lines() == [],
          "the malformed batch close reproduction was accepted")

    seed_batch(
        items=[{"id": "D1", "verdict": "confirmed"}],
        answers=[{"id": "D1", "choice": "O1", "route": "closed"}],
    )
    good = run_progress(
        "note", "ruling.applied",
        "--data", '{"answer":"B1/D1","batch":1,"decision":"D1","route":"closed"}',
    )
    check(good.returncode == 0, good.stdout + good.stderr)
    append_note("ruling.applied", {
        "answer": "B1/D999", "batch": 1, "decision": "D999", "route": "teleport",
    })
    append_note("pass.opened", {"built": "lot-1", "commit": "d" * 40})
    append_note("pass.closed", {"confirmed": 0})
    before = len(journal_lines())
    close = run_progress(
        "note", "decision.batch.closed",
        "--data", '{"batch":1,"outcome":"no-correction"}',
    )
    check(close.returncode != 0, "an invalid prior terminal made the batch close valid")
    check(len(journal_lines()) == before, "the invalid batch close reached the journal")


# ------------------------------------------------ product-review terminals

@test
def task_pass_accepts_a_precommit_final_gate():
    commit, gate, _ = seed_task_gate(
        "lot-1", "precommit-final-gate", precommit_head=True,
    )
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode == 0, opening.stdout + opening.stderr)


@test
def historical_task_pass_rejects_a_gate_tree_from_another_commit():
    commit, gate, _ = seed_task_gate(
        "lot-1", "historical-tree", precommit_head=False,
    )
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode == 0, opening.stdout + opening.stderr)

    wrong_tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", f"{commit}^^{{tree}}"], text=True,
    ).strip()
    entries = journal_lines()
    result = next(
        entry for entry in entries
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
        and (entry.get("data") or {}).get("op") == gate
    )
    result["data"]["tree"] = wrong_tree
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as journal:
        for entry in entries:
            journal.write(json.dumps(entry, separators=(",", ":")) + "\n")

    write_report(
        "reports/product-review/lot-1/lot-1-user.md",
        product_report_text("user"),
    )
    before = len(journal_lines())
    receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(receipt.returncode != 0 and len(journal_lines()) == before,
          "a historical task pass retained a gate result for another candidate tree")


@test
def pass_opening_binds_the_exact_task_lot_and_one_open_generation():
    commit, gate, _ = seed_task_gate("lot-1", "task-source")
    before = len(journal_lines())
    wrong_lot = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-2", "commit": commit, "gate": gate}),
    )
    check(wrong_lot.returncode != 0 and len(journal_lines()) == before,
          "a task gate for lot-1 opened a pass for lot-2")

    valid = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    opening = journal_lines()[-1]["data"]
    check(opening["source_scope"] == "task" and opening["source_lot"] == "lot-1"
          and opening["source_owner"] == "lot-1/task-1/attempt-1",
          f"the pass did not freeze its exact task source: {opening}")
    before = len(journal_lines())
    duplicate = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(duplicate.returncode != 0 and len(journal_lines()) == before,
          "a second opening hid the unfinished current pass")


@test
def task_pass_requires_the_final_manifest_task_and_lot_built_boundary():
    commit, gate, _ = seed_task_gate("lot-1", "missing-built", add_lot_built=False)
    data = json.dumps({"built": "lot-1", "commit": commit, "gate": gate})
    before = len(journal_lines())
    missing_built = run_progress("note", "pass.opened", "--data", data)
    check(missing_built.returncode != 0 and len(journal_lines()) == before,
          "a first pass opened without its lot.built boundary")
    append_note("lot.built", {"tasks": 1, "attempts": 1}, lot="lot-1")
    valid = run_progress("note", "pass.opened", "--data", data)
    check(valid.returncode == 0, valid.stdout + valid.stderr)


@test
def task_pass_rejects_a_nonfinal_task_and_missing_stable_result():
    commit, gate, _ = seed_task_gate("lot-1", "unfinished-plan", tasks=2)
    data = json.dumps({"built": "lot-1", "commit": commit, "gate": gate})
    before = len(journal_lines())
    unfinished = run_progress("note", "pass.opened", "--data", data)
    check(unfinished.returncode != 0 and len(journal_lines()) == before,
          "task 1 opened review for a two-task plan")


@test
def task_pass_accepts_one_exact_complete_multitask_generation():
    first, _, _ = seed_task_gate(
        "lot-1", "first-of-two", tasks=2, add_lot_built=False,
    )
    write_project("subject.txt", "second task\n")
    subprocess.run(["git", "-C", REPO, "add", "subject.txt"], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "second task"], check=True)
    commit = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD^{tree}"], text=True,
    ).strip()
    gate_path = os.path.join(REPO, ".superpowers", "bwr", "gate.md")
    gate_blob = subprocess.check_output(
        ["git", "-C", REPO, "hash-object", gate_path], text=True,
    ).strip()
    gate = hashlib.sha256(f"gate:lot-1:{commit}".encode()).hexdigest()
    append_checker_verdict("code", lot="lot-1", task=2, attempt=1)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "rb") as journal:
        raw_lines = journal.read().splitlines()
    code_proof = f"{len(raw_lines) - 1}:{hashlib.sha256(raw_lines[-1]).hexdigest()}"
    report_relative, report_sha = write_gate_report(gate, gate_blob, tree)
    owner = "lot-1/task-2/attempt-1"
    append_subagent(
        "subagent-ended", "gate-runner", mandate="gate",
        data={"op": gate, "scope": "task", "owner": owner, "lot": "lot-1",
              "task": 2, "attempt": 1, "head": commit, "base": first,
              "tree": tree, "gate": gate_blob, "code": code_proof,
              "green": True, "surface": "unchanged", "report": report_relative,
              "report_sha256": report_sha, "commands": 1},
    )
    append_note(
        "attempt.succeeded",
        {"attempt": 1, "lot": "lot-1", "sha": commit, "gate": gate},
        lot="lot-1", task=2,
    )
    subprocess.run(
        ["git", "-C", REPO, "update-ref", "refs/bwr/test-run/lot-1/task-2", commit],
        check=True,
    )
    append_note("lot.built", {"tasks": 2, "attempts": 2}, lot="lot-1")
    proof = run_progress("construction-verdict-check", "code", "lot-1", "2", "1")
    check(proof.returncode == 0, proof.stdout + proof.stderr)
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode == 0, opening.stdout + opening.stderr)
    check(journal_lines()[-1]["data"]["source_task"] == 2,
          "the complete two-task pass did not consume its final task")


@test
def task_pass_requires_the_stable_ref_for_every_completed_task():
    commit, gate, _ = seed_task_gate("lot-1", "missing-ref")
    subprocess.run(
        ["git", "-C", REPO, "update-ref", "-d", "refs/bwr/test-run/lot-1/task-1"],
        check=True,
    )
    before = len(journal_lines())
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode != 0 and len(journal_lines()) == before,
          "a first pass opened without its stable final-task ref")


@test
def baseline_pass_requires_the_exact_amendment_successor_owner():
    seed_committed_spec()
    first_commit, first_gate, _ = seed_task_gate("lot-1", "first-pass")
    opened = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": first_commit, "gate": first_gate}),
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    amendment = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", "return to the same built lot",
    )
    check(amendment.returncode == 0, amendment.stdout + amendment.stderr)
    amendment_commit = seed_clean_amendment_landing(
        {"amendment": 1, "origin": "product-review", "built": "lot-1"},
        "return to the same built lot",
    )

    wrong_gate = seed_baseline_gate("amendment/2/" + amendment_commit,
                                    amendment_commit, first_commit)
    before = len(journal_lines())
    wrong_owner = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": amendment_commit,
                              "gate": wrong_gate}),
    )
    check(wrong_owner.returncode != 0 and len(journal_lines()) == before,
          "a baseline owned by another amendment opened the successor pass")

    gate = seed_baseline_gate("amendment/1/" + amendment_commit,
                              amendment_commit, first_commit)
    valid = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": amendment_commit, "gate": gate}),
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    check(journal_lines()[-1]["data"]["source_owner"] == f"amendment/1/{amendment_commit}",
          "the successor pass did not freeze its exact amendment owner")


@test
def a_controller_baseline_cannot_open_the_first_pass():
    commit, _, _ = prepare_review_commit("lot-1", "baseline-first")
    gate = seed_baseline_gate("amendment/1/" + commit, commit, commit)
    before = len(journal_lines())
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode != 0 and len(journal_lines()) == before,
          "a controller baseline opened the first pass of a built lot")


@test
def baseline_pass_accepts_only_the_exact_c2_plan_successor():
    seed_committed_spec()
    first_commit, first_gate, _ = seed_task_gate("lot-1", "pre-amendment")
    opened = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": first_commit, "gate": first_gate}),
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    amendment = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", "return through C2",
    )
    check(amendment.returncode == 0, amendment.stdout + amendment.stderr)
    amendment_commit = seed_clean_amendment_landing(
        {"amendment": 1, "origin": "product-review", "built": "lot-1"},
        "return through C2",
    )

    plan_relative = "docs/plans/test-run-lot-1-plan.md"
    write_project(plan_relative, "# Revalidated plan\n")
    subprocess.run(["git", "-C", REPO, "add", plan_relative], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "revalidate plan"], check=True)
    plan_commit = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    append_note("plan.written", {"tasks": 1, "op": "c2-plan"})
    gate = seed_baseline_gate(f"plan/lot-1/{plan_commit}", plan_commit, amendment_commit)
    successor = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": plan_commit, "gate": gate}),
    )
    check(successor.returncode == 0, successor.stdout + successor.stderr)
    check(journal_lines()[-1]["data"]["source_owner"] == f"plan/lot-1/{plan_commit}",
          "the pass did not freeze its exact C2 plan successor")


@test
def product_receipt_audits_the_fixed_lens_block_and_freezes_its_bytes():
    commit, gate, _ = seed_task_gate("lot-1", "receipt")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    labels = product_completion_labels("user")
    malformed = "\n".join([
        f"COMPLETION ({len(labels)} items)",
        *(f"- [x] {label} — exact evidence" for label in labels[:-1]),
        "",
    ])
    write_report("reports/product-review/lot-1/lot-1-user.md", malformed)
    before = len(journal_lines())
    refused_receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(refused_receipt.returncode != 0 and len(journal_lines()) == before,
          "a report omitted one fixed user-lens duty")

    content = product_report_text("user")
    report_sha = write_report("reports/product-review/lot-1/lot-1-user.md", content)
    accepted = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)
    receipt = journal_lines()[-1]["data"]
    check(receipt["pass_commit"] == commit and receipt["pass_gate"] == gate
          and receipt["report_sha256"] == report_sha,
          f"the receipt did not freeze its pass and report generation: {receipt}")
    write_report("reports/product-review/lot-1/lot-1-user.md", content + "changed\n")
    before = len(journal_lines())
    stale = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({"pass_commit": commit, "pass_gate": gate,
                              "report_sha256": report_sha}),
    )
    check(stale.returncode != 0 and len(journal_lines()) == before,
          "a changed report retained its old verifier capability")


@test
def product_receipt_counts_every_structured_finding_in_its_hashed_report():
    commit, gate, _ = seed_task_gate("lot-1", "finding-account")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    content = product_report_text("user", ("IMPORTANT", "DECISION"))
    report_sha = write_report("reports/product-review/lot-1/lot-1-user.md", content)
    before = len(journal_lines())
    omitted = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(omitted.returncode != 0 and len(journal_lines()) == before,
          "a receipt omitted findings present in its hashed report")

    accepted = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":1,"minor":0,"decision":1}',
    )
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)
    identity = {"pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha}
    started = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(started.returncode == 0, started.stdout + started.stderr)
    before = len(journal_lines())
    empty = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({
            **identity, "confirmed": 0, "disproved": 0, "malformed": 0, "claims": [],
        }),
    )
    check(empty.returncode != 0 and len(journal_lines()) == before,
          "an empty verifier result consumed a report with two real findings")
    complete = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({
            **identity, "confirmed": 2, "disproved": 0, "malformed": 0,
            "claims": [
                {"id": "F1", "kind": "correction", "verdict": "confirmed"},
                {"id": "F2", "kind": "decision", "verdict": "confirmed"},
            ],
        }),
    )
    check(complete.returncode == 0, complete.stdout + complete.stderr)


@test
def product_receipt_rejects_a_noncontiguous_finding_structure():
    commit, gate, _ = seed_task_gate("lot-1", "malformed-finding")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    malformed = product_report_text("user", ("IMPORTANT",)).replace(
        "Proof: exact cited location\n", "",
    )
    write_report("reports/product-review/lot-1/lot-1-user.md", malformed)
    before = len(journal_lines())
    receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":1,"minor":0,"decision":0}',
    )
    check(receipt.returncode != 0 and len(journal_lines()) == before,
          "a finding without its complete fixed field account received a receipt")


@test
def product_verifier_and_physical_copy_consume_one_exact_pass_generation():
    commit, gate, _ = seed_task_gate("lot-1", "verifier")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    content = product_report_text("meaning")
    report_sha = write_report("reports/product-review/lot-1/lot-1-meaning.md", content)
    receipt = run_progress(
        "note", "report.received", "--mandate", "meaning",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    identity = {"pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha}
    before = len(journal_lines())
    wrong = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "meaning",
        "--data", json.dumps({**identity, "pass_commit": "a" * 40}),
    )
    check(wrong.returncode != 0 and len(journal_lines()) == before,
          "a finding verifier opened against another pass commit")
    started = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "meaning",
        "--data", json.dumps(identity),
    )
    check(started.returncode == 0, started.stdout + started.stderr)

    verify_open = os.path.join(WORKSPACE, "prompts", "product-review", "verify-open.sh")
    before_tmp = os.path.join(REPO, ".superpowers", "bwr", "tmp")
    stale_copy = subprocess.run(
        ["bash", verify_open, "a" * 40, "lot-1-meaning.md"],
        capture_output=True, text=True, env=ENV,
    )
    check(stale_copy.returncode != 0 and not os.path.exists(before_tmp),
          "verify-open touched the disposable ground before rejecting a stale pass")
    exact_copy = subprocess.run(
        ["bash", verify_open, commit, "lot-1-meaning.md"],
        capture_output=True, text=True, env=ENV,
    )
    check(exact_copy.returncode == 0, exact_copy.stdout + exact_copy.stderr)
    copy_path = exact_copy.stdout.strip()
    copy_head = subprocess.check_output(
        ["git", "-C", copy_path, "rev-parse", "HEAD"], text=True,
    ).strip()
    check(copy_head == commit, "the physical verifier copy opened another commit")
    verify_close = os.path.join(WORKSPACE, "prompts", "product-review", "verify-close.sh")
    closed = subprocess.run(
        ["bash", verify_close, "lot-1-meaning.md"],
        capture_output=True, text=True, env=ENV,
    )
    check(closed.returncode == 0, closed.stdout + closed.stderr)

    ended = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "meaning",
        "--data", json.dumps({**identity, "confirmed": 0, "disproved": 0,
                              "malformed": 0, "claims": []}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)


@test
def product_verifier_unusable_terminal_allows_exact_regeneration():
    commit, gate, owner = seed_task_gate("lot-1", "verifier-regeneration")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": owner,
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    identities = {}
    for mandate in ("unlooked", "user", "meaning", "quality", "coverage"):
        content = product_report_text(mandate)
        report_sha = write_report(
            f"reports/product-review/lot-1/lot-1-{mandate}.md", content,
        )
        receipt = run_progress(
            "note", "report.received", "--mandate", mandate,
            "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
        )
        check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
        identities[mandate] = {
            "pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha,
        }

    identity = identities["user"]
    first = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(first.returncode == 0, first.stdout + first.stderr)
    before = len(journal_lines())
    overlapping = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(overlapping.returncode != 0 and len(journal_lines()) == before,
          "a second physical verifier opened over an unsettled call")
    unusable = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({**identity, "unusable": "lost"}),
    )
    check(unusable.returncode == 0, unusable.stdout + unusable.stderr)
    before = len(journal_lines())
    terminal_without_start = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({
            **identity, "confirmed": 0, "disproved": 0, "malformed": 0, "claims": [],
        }),
    )
    check(terminal_without_start.returncode != 0 and len(journal_lines()) == before,
          "a result landed without a regenerated physical opening")
    second = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(second.returncode == 0, second.stdout + second.stderr)

    for mandate, current_identity in identities.items():
        if mandate != "user":
            started = run_progress(
                "subagent-started", "finding-verifier", "--mandate", mandate,
                "--data", json.dumps(current_identity),
            )
            check(started.returncode == 0, started.stdout + started.stderr)
        ended = run_progress(
            "subagent-ended", "finding-verifier", "--mandate", mandate,
            "--data", json.dumps({
                **current_identity,
                "confirmed": 0, "disproved": 0, "malformed": 0, "claims": [],
            }),
        )
        check(ended.returncode == 0, ended.stdout + ended.stderr)

    before = len(journal_lines())
    after_result = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(after_result.returncode != 0 and len(journal_lines()) == before,
          "a complete verifier result allowed another physical call")
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(closed.returncode == 0, closed.stdout + closed.stderr)


@test
def product_verifier_refuses_a_second_physical_relaunch():
    commit, gate, _ = seed_task_gate("lot-1", "verifier-relaunch-limit")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    })
    content = product_report_text("user")
    report_sha = write_report("reports/product-review/lot-1/lot-1-user.md", content)
    receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    identity = {"pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha}
    for reason in ("error", "lost"):
        started = run_progress(
            "subagent-started", "finding-verifier", "--mandate", "user",
            "--data", json.dumps(identity),
        )
        check(started.returncode == 0, started.stdout + started.stderr)
        ended = run_progress(
            "subagent-ended", "finding-verifier", "--mandate", "user",
            "--data", json.dumps({**identity, "unusable": reason}),
        )
        check(ended.returncode == 0, ended.stdout + ended.stderr)
    before = len(journal_lines())
    third = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(third.returncode != 0 and len(journal_lines()) == before,
          "a finding verifier received a second physical relaunch")


@test
def pass_close_requires_all_five_settled_receipts_and_verifiers():
    seed_review_pass(omit="coverage")
    before = len(journal_lines())
    missing = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(missing.returncode != 0 and len(journal_lines()) == before,
          "a clean pass close accepted four lens receipts")


@test
def pass_close_rejects_reopened_reports_and_unfinished_authority():
    seed_review_pass()
    append_note(
        "bound.spent", text="malformed finding returned: stale claim - lens session-1",
        mandate="coverage",
    )
    before = len(journal_lines())
    reopened = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(reopened.returncode != 0 and len(journal_lines()) == before,
          "a reopened report without a fresh receipt closed the pass")


@test
def clean_pass_close_requires_current_work_to_be_consumed():
    seed_batch(
        items=[{"id": "F1", "verdict": "confirmed"}],
        answers=[],
    )
    seed_review_pass()
    before = len(journal_lines())
    proc = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "a clean pass close discarded carried confirmed batch work")


@test
def pass_close_rejects_an_unapplied_current_direct_ruling():
    seed_direct_ruling(route="closed")
    seed_review_pass()
    before = len(journal_lines())
    proc = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(proc.returncode != 0 and len(journal_lines()) == before,
          "a pass close bypassed an unapplied current direct ruling")


@test
def positive_pass_close_requires_exact_allocation_and_artifacts():
    seed_review_pass(confirmed=1)
    append_note("sublot.allocated", allocation_data(), text="lot-1.1")
    before = len(journal_lines())
    missing = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(missing.returncode != 0 and len(journal_lines()) == before,
          "a positive pass close accepted missing confirmed and plan artifacts")
    write_confirmed("lot-1", [])
    valid = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    duplicate = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(duplicate.returncode != 0, "a duplicate pass close was accepted")


@test
def positive_pass_dedupe_accounts_for_every_confirmed_source_once():
    seed_review_pass(confirmed=2)
    omitted = allocation_data(items=[{
        "id": "F1", "sources": ["unlooked/F1"], "carries": [],
    }])
    before = len(journal_lines())
    refused_allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(omitted, separators=(",", ":")),
    )
    check(refused_allocation.returncode != 0 and len(journal_lines()) == before,
          "a dedupe account omitted one unique confirmed source")

    repeated = allocation_data(items=[
        {"id": "F1", "sources": ["unlooked/F1"], "carries": []},
        {"id": "F2", "sources": ["unlooked/F1"], "carries": []},
    ])
    repeated_allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(repeated, separators=(",", ":")),
    )
    check(repeated_allocation.returncode != 0 and len(journal_lines()) == before,
          "a dedupe account consumed one confirmed source twice")

    merged_items = [{
        "id": "F1", "sources": ["unlooked/F1", "unlooked/F2"], "carries": [],
    }]
    valid_allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(
            allocation_data(items=merged_items), separators=(",", ":"),
        ),
    )
    check(valid_allocation.returncode == 0,
          valid_allocation.stdout + valid_allocation.stderr)

    write_confirmed(
        "lot-1", [], count=1,
        items=[{"id": "F1", "sources": ["unlooked/F1"], "carries": []}],
    )
    before = len(journal_lines())
    incomplete_artifact = run_progress(
        "note", "pass.closed", "--data", '{"confirmed":1}',
    )
    check(incomplete_artifact.returncode != 0 and len(journal_lines()) == before,
          "a confirmed artifact dropped one source from its allocated dedupe account")

    write_confirmed("lot-1", [], count=1, items=merged_items)
    valid_close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(valid_close.returncode == 0, valid_close.stdout + valid_close.stderr)


@test
def positive_pass_requires_the_confirmed_pointer_inside_covers():
    seed_review_pass(confirmed=1)
    allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(allocation_data(), separators=(",", ":")),
    )
    check(allocation.returncode == 0, allocation.stdout + allocation.stderr)
    write_confirmed(
        "lot-1", [],
        plan_text="Covers: another-source.md\n\nNote: lot-1-confirmed.md\n",
    )
    before = len(journal_lines())
    outside_mention = run_progress(
        "note", "pass.closed", "--data", '{"confirmed":1}',
    )
    check(outside_mention.returncode != 0 and len(journal_lines()) == before,
          "a confirmed filename outside Covers satisfied the plan-source proof")

    write_confirmed("lot-1", [])
    valid_close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(valid_close.returncode == 0, valid_close.stdout + valid_close.stderr)


@test
def positive_pass_account_preserves_a_later_source_refutation():
    seed_review_pass(confirmed=2)
    refuted = run_progress(
        "note", "decision.refuted", "--data", '{"source":"unlooked/F2"}',
        "--text", "the changed spec now disproves this source",
    )
    check(refuted.returncode == 0, refuted.stdout + refuted.stderr)
    items = [{"id": "F1", "sources": ["unlooked/F1"], "carries": []}]
    allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(
            allocation_data(items=items, refuted=["unlooked/F2"]),
            separators=(",", ":"),
        ),
    )
    check(allocation.returncode == 0, allocation.stdout + allocation.stderr)
    write_confirmed("lot-1", [], items=items)
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)


@test
def pass_close_rejects_malformed_shapes_and_preserves_amendment_void():
    seed_review_pass(commit="a" * 40)
    before = len(journal_lines())
    malformed = run_progress(
        "note", "pass.closed", "--data", '{"confirmed":0,"voided":true}',
    )
    check(malformed.returncode != 0 and len(journal_lines()) == before,
          "a mixed ordinary and voided close shape was accepted")
    opening = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", "return to this pass",
    )
    check(opening.returncode == 0, opening.stdout + opening.stderr)
    voided = run_progress("note", "pass.closed", "--data", '{"voided":true}')
    check(voided.returncode == 0, voided.stdout + voided.stderr)
    duplicate = run_progress("note", "pass.closed", "--data", '{"voided":true}')
    check(duplicate.returncode != 0, "a duplicate amendment-owned void close was accepted")


# ---------------------------------------------------- amendment admission

@test
def amendment_opening_requires_one_exact_current_generation_and_return():
    seed_amendment_context()
    before = len(journal_lines())
    for payload, text in (
        ({"amendment": 2, "origin": "product-review", "built": "lot-1"}, "return"),
        ({"amendment": 1, "origin": "invented", "built": "lot-1"}, "return"),
        ({"amendment": 1, "origin": "product-review", "built": "lot-2"}, "return"),
        ({"amendment": 1, "origin": "product-review", "built": "lot-1"}, None),
    ):
        args = ["note", "amendment.opened", "--data", json.dumps(payload)]
        if text is not None:
            args += ["--text", text]
        proc = run_progress(*args)
        check(proc.returncode != 0 and len(journal_lines()) == before,
              f"an invalid amendment opening was accepted: {payload}, {text!r}")
    valid = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", "apply the order; return to this pass",
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    data = journal_lines()[-1]["data"]
    check(data["opening_sha256"] and len(data["opening_sha256"]) == 64,
          "the opening did not freeze its order and identity")
    replacement = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":2,"origin":"product-review","built":"lot-1"}',
        "--text", "replace the unfinished generation",
    )
    check(replacement.returncode != 0, "a second opening replaced an unfinished amendment")


@test
def amendment_written_requires_the_complete_exact_document_and_report_directory():
    seed_amendment_context()
    order = "apply the complete order; return to product review"
    opened = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    voided = run_progress("note", "pass.closed", "--data", '{"voided":true}')
    check(voided.returncode == 0, voided.stdout + voided.stderr)
    path = os.path.join(WORKSPACE, "amendments", "1.md")
    write_report("amendments/1.md", "# Amendment 1\n\n## Order and return\n" + order + "\n")
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    before = len(journal_lines())
    partial = run_progress(
        "note", "amendment.written", "--data", '{"amendment":1}', "--text", path,
    )
    check(partial.returncode != 0 and len(journal_lines()) == before,
          "a coherent partial amendment document became ready")
    write_report("amendments/1.md", amendment_document(1, order))
    ready = run_progress(
        "note", "amendment.written", "--data", '{"amendment":1}', "--text", path,
    )
    check(ready.returncode == 0, ready.stdout + ready.stderr)
    proof = journal_lines()[-1]["data"]
    check(set(proof) == {"amendment", "opening_sha256", "document_sha256", "snapshot"}, proof)
    write_report("amendments/1.md", amendment_document(1, order) + "\nchanged after ready\n")
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_reach_session(1)
    before = len(journal_lines())
    stale = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(stale.returncode != 0 and len(journal_lines()) == before,
          "a sweep consumed amendment bytes changed after readiness")


@test
def sweep_receipt_consumes_its_exact_retired_session_report_and_counts():
    seed_amendment_context()
    order = "apply the reach order; return to product review"
    opened = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    check(run_progress("note", "pass.closed", "--data", '{"voided":true}').returncode == 0,
          "the product pass did not void")
    write_report("amendments/1.md", amendment_document(1, order))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    path = os.path.join(WORKSPACE, "amendments", "1.md")
    check(run_progress("note", "amendment.written", "--data", '{"amendment":1}',
                       "--text", path).returncode == 0, "the valid amendment did not become ready")
    before = len(journal_lines())
    absent = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(absent.returncode != 0 and len(journal_lines()) == before,
          "an absent reach report received a receipt")
    write_report("reports/amendment/1/sweep-1.md", reach_report((2, 0), ("kept", "removed")))
    no_session = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":2,"closed":true}',
    )
    check(no_session.returncode != 0, "a sweep without a retired session received a receipt")
    append_reach_session(1)
    wrong = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":1,"closed":true}',
    )
    check(wrong.returncode != 0, "caller-supplied reach counts overrode the report")
    valid = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":2,"closed":true}',
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    data = journal_lines()[-1]["data"]
    check(data["sweep"] == 1 and data["report_sha256"] and data["session"], data)


@test
def sweep_receipt_binds_each_disposition_to_one_exact_place_block():
    seed_written_amendment_for_reach()
    valid = reach_report((2, 0), ("kept", "removed"))
    before_last, after_last = valid.rsplit("Disposition: removed\n", 1)
    malformed = before_last.replace(
        "Disposition: kept\n", "Disposition: kept\nDisposition: removed\n", 1,
    ) + after_last
    write_report("reports/amendment/1/sweep-1.md", malformed)
    append_reach_session(1)
    before = len(journal_lines())
    result = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":2,"closed":true}',
    )
    check(result.returncode != 0 and len(journal_lines()) == before,
          "global disposition counts hid one duplicate P1 disposition and an empty P2")


@test
def sweep_receipt_rejects_template_completion_and_out_of_block_structure():
    seed_written_amendment_for_reach()
    template = reach_report()
    replacements = (
        ("0 total: 0 kept, 0 moved, 0 removed, 0 DECISION",
         "N total: N kept, N moved, N removed, N DECISION"),
        ("1 hops, last one returning 0 new places",
         "N, last one returning M new places"),
        ("active A1/order; 1 unique terms or hits",
         "active B<N>/D<M> or R<N> terms and hits, N unique total"),
        ("- [x] places reached by purpose and not by name — 0",
         "- [x] places reached by purpose and not by name — N"),
        ("0 found, 0 still asserting it after the amendment",
         "N found, N still asserting it after the amendment"),
        ("closed at hop 1", "closed at hop N, or NOT CLOSED with the count per hop"),
    )
    for old, new in replacements:
        template = template.replace(old, new)
    write_report("reports/amendment/1/sweep-1.md", template)
    append_reach_session(1)
    before = len(journal_lines())
    placeholder = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(placeholder.returncode != 0 and len(journal_lines()) == before,
          "the untouched completion template became accepted evidence")
    orphan = reach_report() + "\n## P99 · orphan\nDisposition: removed\n"
    write_report("reports/amendment/1/sweep-1.md", orphan)
    orphan_result = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(orphan_result.returncode != 0 and len(journal_lines()) == before,
          "out-of-block structural lines satisfied the Reach account")
    fenced = reach_report() + (
        "\n```text\n## P99 · example\nDisposition: removed\n```\n"
    )
    write_report("reports/amendment/1/sweep-1.md", fenced)
    fenced_result = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(fenced_result.returncode == 0, fenced_result.stdout + fenced_result.stderr)


@test
def sweep_receipt_refuses_one_successful_session_beside_a_live_session():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_reach_session(1, "settled-reach")
    append_live_reach_session(1, "still-live-reach")
    before = len(journal_lines())
    result = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(result.returncode != 0 and len(journal_lines()) == before,
          "one completed session hid a second live writer for the same sweep")


@test
def reach_accepts_a_finite_five_hop_frontier_and_closes_only_on_zero():
    seed_written_amendment_for_reach()
    report = reach_report(
        (1, 1, 1, 1, 0), ("kept", "moved", "removed", "DECISION"),
    )
    write_report("reports/amendment/1/sweep-1.md", report)
    append_reach_session(1)
    result = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":5,"places":4,"closed":true}',
    )
    check(result.returncode == 0, result.stdout + result.stderr)
    data = journal_lines()[-1]["data"]
    check(data["hop"] == 5 and data["places"] == 4 and data["closed"] is True, data)


@test
def open_reach_requires_an_explicit_unenumerable_input_not_only_counts():
    seed_written_amendment_for_reach()
    blocker = "missing durable input: event consumer registry is absent"
    valid = reach_report(
        (2, 1), ("kept", "removed", "DECISION"), open_blocker=blocker,
    )
    invalid = valid.replace(
        f"; next hop cannot be enumerated — {blocker}", "",
    )
    write_report("reports/amendment/1/sweep-1.md", invalid)
    append_reach_session(1)
    before = len(journal_lines())
    counts_only = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":3,"closed":false}',
    )
    check(counts_only.returncode != 0 and len(journal_lines()) == before,
          "positive hop counts alone became a NOT CLOSED frontier")
    write_report("reports/amendment/1/sweep-1.md", valid)
    accepted = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":3,"closed":false}',
    )
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)


@test
def reach_contract_has_no_fixed_depth_cutoff_and_keeps_the_exit_door():
    paths = (
        os.path.join(HERE, "prompts", "amendment", "reviewer-reach.md"),
        os.path.join(HERE, "prompts", "amendment", "reviewer-reach-completion.md"),
        os.path.join(HERE, "prompts", "amendment", "MODE.md"),
        os.path.join(HERE, "SKILL.md"),
    )
    contract = "\n".join(open(path, encoding="utf-8").read() for path in paths)
    contract_flat = " ".join(contract.split())
    for forbidden in (
        "Still growing at the third or fourth hop",
        "still growing at the third or\nfourth hop",
    ):
        check(forbidden not in contract, f"the reach contract kept a fixed cutoff: {forbidden}")
    for required in (
        "No hop number and no positive place count proves that the frontier is unbounded",
        "Continue the union-frontier walk while the next finite frontier can be enumerated",
        "next hop cannot be enumerated — missing durable input:",
        "next hop cannot be enumerated — unbounded input:",
        "progress.py note reach.not-closed --text-file",
        "They may answer *\"carry on as an amendment\"*",
    ):
        check(required in contract_flat, f"the reach contract lost its required rule: {required}")


@test
def amendment_commit_refuses_without_the_exact_clean_review_and_accepts_the_full_path():
    seed_amendment_context()
    order = "apply the reviewed amendment; return to product review"
    opened = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1"}',
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    check(run_progress("note", "pass.closed", "--data", '{"voided":true}').returncode == 0,
          "the product pass did not void")
    write_report("amendments/1.md", amendment_document(1, order))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    path = os.path.join(WORKSPACE, "amendments", "1.md")
    check(run_progress("note", "amendment.written", "--data", '{"amendment":1}',
                       "--text", path).returncode == 0, "the amendment did not become ready")
    spec_relative = next(entry["text"] for entry in journal_lines()
                         if entry.get("kind") == "spec.written")
    script = os.path.join(WORKSPACE, "prompts", "amendment", "amendment-commit.sh")
    head = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    premature = subprocess.run(
        [script, "1", spec_relative, "docs: premature amendment", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(premature.returncode != 0
          and subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"],
                                      text=True).strip() == head
          and not os.path.exists(os.path.join(WORKSPACE, "amendment-commit-in-progress")),
          "amendment-commit.sh mutated before clean reach and consolidation")
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_reach_session(1)
    check(run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    ).returncode == 0, "the clean sweep did not settle")
    check(run_progress(
        "note", "fixer.returned", "--data", '{"applied":1,"declined":0}',
    ).returncode == 0, "the final fixer return did not settle")
    write_project(spec_relative, spec_document(status="amended"))
    check(run_progress("subagent-started", "consolidation", "--round", "1").returncode == 0,
          "the consolidation did not open")
    check(run_progress(
        "note", "bound.spent", "--round", "1", "--text", "consolidation round 1 of 3",
    ).returncode == 0, "the consolidation spend did not land")
    check(run_progress(
        "subagent-ended", "consolidation", "--round", "1", "--data", '{"exact":true}',
    ).returncode == 0, "the consolidation result did not land")
    check(run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"consolidation","outcome":"exact"}',
    ).returncode == 0, "the exact consolidation verdict did not settle")
    cfg = default_config()
    cfg["fail"] = [["whoami"]]
    set_config(cfg)
    interrupted = subprocess.run(
        [script, "1", spec_relative, "docs: land reviewed amendment", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(interrupted.returncode != 0
          and os.path.isfile(os.path.join(WORKSPACE, "amendment-commit-in-progress"))
          and not any(entry.get("kind") == "amendment.committed" for entry in journal_lines()),
          "the interrupted commit did not preserve its exact pending journal tail")
    sha = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True).strip()
    set_config(default_config())
    committed = subprocess.run(
        [script, "1", spec_relative, "docs: land reviewed amendment", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(committed.returncode == 0, committed.stdout + committed.stderr)
    check(subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"],
                                  text=True).strip() == sha,
          "the amendment retry repeated the already-created commit")
    check(not os.path.exists(os.path.join(WORKSPACE, "amendment-commit-in-progress")),
          "the completed retry left its pending marker")
    terminal = journal_lines()[-1]
    check(terminal["kind"] == "amendment.committed" and terminal["data"]["sha"] == sha
          and terminal["data"]["review_sha256"]
          and terminal["data"]["consolidation_round"] == 1,
          "the amendment terminal lacks its exact clean-review proof")
    write_report("reports/amendment/1/sweep-1.md", reach_report((1, 0), ("kept",)))
    damaged = run_progress("amendment-state-check")
    check(damaged.returncode != 0,
          "the historical amendment consumer accepted a changed reach artifact")


@test
def lot_delivery_requires_current_clean_close_and_exact_metadata():
    commit = seed_review_pass(commit="b" * 40)
    before = len(journal_lines())
    premature = run_progress(
        "note", "lot.delivered", "--data", json.dumps({"sha": commit, "passes": 1}),
    )
    check(premature.returncode != 0 and len(journal_lines()) == before,
          "a delivery without a clean pass close was accepted")
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(close.returncode == 0, close.stdout + close.stderr)
    for payload in (
        {"sha": "NOT-A-SHA", "passes": 1},
        {"sha": commit, "passes": 0},
        {"sha": commit, "passes": 2},
        {"sha": "c" * 40, "passes": 1},
    ):
        before = len(journal_lines())
        refused_delivery = run_progress(
            "note", "lot.delivered", "--data", json.dumps(payload, separators=(",", ":")),
        )
        check(refused_delivery.returncode != 0 and len(journal_lines()) == before,
              f"an invalid delivery payload was accepted: {payload}")
    valid = run_progress(
        "note", "lot.delivered", "--data", json.dumps({"sha": commit, "passes": 1}),
    )
    check(valid.returncode == 0, valid.stdout + valid.stderr)
    duplicate = run_progress(
        "note", "lot.delivered", "--data", json.dumps({"sha": commit, "passes": 1}),
    )
    check(duplicate.returncode != 0, "a duplicate lot delivery was accepted")


@test
def lot_delivery_does_not_consume_an_older_pass_generation():
    first = seed_review_pass(commit="d" * 40)
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(close.returncode == 0, close.stdout + close.stderr)
    append_note("pass.opened", {"built": "lot-1", "commit": "e" * 40})
    before = len(journal_lines())
    stale = run_progress(
        "note", "lot.delivered", "--data", json.dumps({"sha": first, "passes": 1}),
    )
    check(stale.returncode != 0 and len(journal_lines()) == before,
          "a delivery consumed the clean close of an older pass generation")


# ------------------------------------------------------- breach restoration

@test
def breach_restoration_requires_a_keyed_successful_recheck():
    seed_breach()
    before = len(journal_lines())
    no_recheck = run_progress(
        "note", "spec.breach.restored", "--data", json.dumps(restored_data()),
    )
    check(no_recheck.returncode != 0 and len(journal_lines()) == before,
          "a breach restoration without a recheck was accepted")

    append_note("decision.recheck.completed", {
        "owner": "R1", "breach": 1, "basis_kind": "spec.breach.corrected",
        "basis_ref": "repair-1", "sha": "c" * 40,
        "restored": False, "missing": ["B1/D1"],
    }, "reports/answers/breach-1-adverse.md")
    before = len(journal_lines())
    adverse = run_progress(
        "note", "spec.breach.restored", "--data", json.dumps(restored_data()),
    )
    check(adverse.returncode != 0 and len(journal_lines()) == before,
          "an adverse breach recheck released global precedence")


@test
def breach_restoration_rejects_fabricated_and_stale_basis():
    seed_breach()
    append_note("decision.recheck.completed", {
        "owner": "R1", "breach": 1, "basis_kind": "spec.breach.corrected",
        "basis_ref": "repair-1", "sha": "c" * 40,
        "restored": True, "missing": [],
    }, "reports/answers/breach-1-restored.md")
    before = len(journal_lines())
    fabricated = run_progress(
        "note", "spec.breach.restored",
        "--data", json.dumps(restored_data(basis_ref="invented", sha="d" * 40)),
    )
    check(fabricated.returncode != 0 and len(journal_lines()) == before,
          "a fabricated breach basis and SHA were accepted")

    append_note("spec.committed", {
        "breach": 1, "conflict": 1, "op": "repair-2", "sha": "e" * 40,
    })
    before = len(journal_lines())
    stale = run_progress(
        "note", "spec.breach.restored", "--data", json.dumps(restored_data()),
    )
    check(stale.returncode != 0 and len(journal_lines()) == before,
          "a successful recheck older than a later repair basis was accepted")


@test
def successful_breach_recheck_allows_one_exact_restoration():
    seed_breach()
    append_note("decision.recheck.completed", {
        "owner": "R1", "breach": 1, "basis_kind": "spec.breach.corrected",
        "basis_ref": "repair-1", "sha": "c" * 40,
        "restored": True, "missing": [],
    }, "reports/answers/breach-1-restored.md")
    data = json.dumps(restored_data())
    restored = run_progress("note", "spec.breach.restored", "--data", data)
    check(restored.returncode == 0, restored.stdout + restored.stderr)
    before = len(journal_lines())
    duplicate = run_progress("note", "spec.breach.restored", "--data", data)
    check(duplicate.returncode != 0 and len(journal_lines()) == before,
          "a duplicate breach restoration was accepted")


@test
def invalid_raw_restoration_does_not_release_shared_global_precedence():
    seed_breach()
    append_note("spec.breach.restored", restored_data())
    before = len(journal_lines())
    consumer = run_progress(
        "note", "amendment.opened",
        "--data", '{"amendment":1,"origin":"product-review","built":"lot-1","batch":1}',
    )
    check(consumer.returncode != 0 and len(journal_lines()) == before,
          "authority_precedence accepted a raw restoration without its successful recheck")


# ---------------------------------------------------------- SPEC admission

@test
def spec_written_freezes_one_real_exact_lot_manifest():
    relative = "docs/plans/demo-design.md"
    write_project(relative, "# Partial\n\n## Lot 1 — Only\n")
    refused(run_progress("note", "spec.written", "--text", relative, "--data", '{"lots":2}'))
    write_project(relative, spec_document())
    proc = run_progress("note", "spec.written", "--text", relative, "--data", '{"lots":2}')
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    data = journal_lines()[-1]["data"]
    check(data["lot_manifest"] == ["## Lot 1 — Core", "## Lot 2 — Surface"],
          "spec.written did not freeze the exact lot headings")
    check(data["spec_sha256"] == hashlib.sha256(spec_document().encode()).hexdigest(),
          "spec.written did not freeze the exact authoring bytes")
    before = len(journal_lines())
    duplicate = run_progress("note", "spec.written", "--text", relative, "--data", '{"lots":2}')
    check(duplicate.returncode != 0 and len(journal_lines()) == before,
          "a duplicate readiness boundary reached the journal")


@test
def spec_round_opening_requires_exact_phase_number_and_source_bytes():
    relative = seed_spec()
    before = len(journal_lines())
    partial = run_progress(
        "note", "round.opened",
        "--data", '{"round":1,"mandates":["enumerator","verifier","judge"]}',
    )
    check(partial.returncode != 0 and len(journal_lines()) == before,
          "a partial first round reached the journal")
    write_project(relative, spec_document(extra="\nUnreviewed mutation.\n"))
    stale = run_progress(
        "note", "round.opened", "--data", json.dumps({"round": 1, "mandates": SPEC_FIRST})
    )
    check(stale.returncode != 0 and len(journal_lines()) == before,
          "a round opened over bytes different from spec.written")
    write_project(relative, spec_document())
    opening = open_spec_round(1, SPEC_FIRST)
    check(os.path.isfile(os.path.join(WORKSPACE, opening["data"]["snapshot"])),
          "round.opened did not publish its immutable snapshot")
    before = len(journal_lines())
    reused = run_progress(
        "note", "round.opened", "--data", json.dumps({"round": 1, "mandates": SPEC_FIRST})
    )
    check(reused.returncode != 0 and len(journal_lines()) == before,
          "a reused round identity reached the journal")


@test
def spec_receipt_authenticates_current_report_block_counts_and_generation():
    seed_spec()
    open_spec_round(1, SPEC_FIRST)
    counts = '{"critical":0,"important":0,"minor":0,"decision":0}'
    before = len(journal_lines())
    missing = run_progress(
        "note", "report.received", "--round", "1", "--mandate", "enumerator", "--data", counts
    )
    check(missing.returncode != 0 and len(journal_lines()) == before,
          "an absent SPEC report received a receipt")
    write_report("reports/spec-review/round-1-enumerator.md", "COMPLETION (7 items)\nREADY\n")
    partial = run_progress(
        "note", "report.received", "--round", "1", "--mandate", "enumerator", "--data", counts
    )
    check(partial.returncode != 0 and len(journal_lines()) == before,
          "a partial completion block received a receipt")
    write_report("reports/spec-review/round-1-enumerator.md",
                 spec_report_text("enumerator", ("IMPORTANT",)))
    wrong = run_progress(
        "note", "report.received", "--round", "1", "--mandate", "enumerator", "--data", counts
    )
    check(wrong.returncode != 0 and len(journal_lines()) == before,
          "report counts that contradict the findings reached the journal")
    receipt = receive_spec_report(1, "enumerator", ("IMPORTANT",))
    check(receipt["data"]["important"] == 1 and receipt["data"]["report_sha256"],
          "the valid report receipt lacks its exact durable proof")
    before = len(journal_lines())
    duplicate = run_progress(
        "note", "report.received", "--round", "1", "--mandate", "enumerator",
        "--data", '{"critical":0,"important":1,"minor":0,"decision":0}',
    )
    check(duplicate.returncode != 0 and len(journal_lines()) == before,
          "a duplicate current-round receipt reached the journal")


@test
def spec_close_revalidates_historical_receipt_artifacts_fail_closed():
    relative = seed_spec()
    opening = open_spec_round(1, SPEC_FIRST)
    receive_full_spec_round(1, SPEC_FIRST)
    write_report("reports/spec-review/round-1-verifier.md", spec_report_text("verifier") + "changed\n")
    changed_report = run_progress("spec-close-check", relative)
    check(changed_report.returncode != 0,
          "the SPEC close consumed a changed historical accepted report")
    write_report("reports/spec-review/round-1-verifier.md", spec_report_text("verifier"))
    snapshot = os.path.join(WORKSPACE, opening["data"]["snapshot"])
    with open(snapshot, "a", encoding="utf-8") as target:
        target.write("changed\n")
    changed_snapshot = run_progress("spec-close-check", relative)
    check(changed_snapshot.returncode != 0,
          "the SPEC close consumed a changed historical round snapshot")


@test
def spec_fixer_return_consumes_exact_account_and_opens_only_scoped_round():
    relative = seed_spec()
    open_spec_round(1, SPEC_FIRST)
    receive_full_spec_round(1, SPEC_FIRST, {"enumerator": ("IMPORTANT",)})
    account = "- R1/enumerator/F1 | APPLIED | § Core | Clarified the first contract"
    labels = completion_labels("fixer")
    values = {
        "findings": "1 received, 1 applied, 0 declined",
        "failure directions derived": "1 edits, 2 cases checked, 0 wrongly permissive, 0 wrongly restrictive",
        "grep inventory": "1 identifiers grepped, 1 pre-edit hits, 1 edited hits; pre/post counts and reasons in the log",
        "subdivision this round": "n/a: no subdivision",
        "self-detected items": "0",
        "blocked on a human decision": "0",
    }
    bad = [f"COMPLETION ({len(labels)} items)",
           *[f"- [x] {label} — {values[label]}" for label in labels], "", "## Correction account", ""]
    write_report("reports/spec-review/round-1-fixer.md", "\n".join(bad))
    write_report("reports/spec-review/decisions-log.md", "# Decisions\n")
    write_project(relative, spec_document(extra="\nClarified.\n"))
    before = len(journal_lines())
    incomplete = run_progress(
        "note", "fixer.returned", "--round", "1", "--data", '{"applied":1,"declined":0}'
    )
    check(incomplete.returncode != 0 and len(journal_lines()) == before,
          "an incomplete fixer account reached the journal")
    good = [f"COMPLETION ({len(labels)} items)",
            *[f"- [x] {label} — {values[label]}" for label in labels], "",
            "## Correction account", account, ""]
    write_report("reports/spec-review/round-1-fixer.md", "\n".join(good))
    write_report("reports/spec-review/decisions-log.md", f"# Decisions\n\n## Round 1\n{account}\n")
    returned = run_progress(
        "note", "fixer.returned", "--round", "1", "--data", '{"applied":1,"declined":0}'
    )
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    data = journal_lines()[-1]["data"]
    check(data["round"] == 1 and data["spec_sha256"] and data["report_sha256"],
          "fixer.returned lacks its exact round and resulting state")
    opening = open_spec_round(2, ["scoped"])
    check(opening["data"]["source_kind"] == "fixer.returned",
          "the scoped round did not consume the accepted fixer result")


@test
def amendment_fixer_return_remains_outside_the_spec_round_contract():
    proc = run_progress(
        "note", "fixer.returned", "--data", '{"applied":1,"declined":0}'
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    entry = journal_lines()[-1]
    check(entry["kind"] == "fixer.returned"
          and entry["data"] == {"applied": 1, "declined": 0}
          and "round" not in entry,
          "the shared amendment fixer return was changed into a SPEC boundary")


@test
def spec_close_requires_one_clean_full_snapshot_and_status_only_delta():
    relative = seed_spec()
    open_spec_round(1, SPEC_FIRST)
    for mandate in SPEC_FIRST[:-1]:
        receive_spec_report(1, mandate)
    missing = run_progress("spec-close-check", relative)
    check(missing.returncode != 0, "SPEC close accepted a missing final mandate")
    receive_spec_report(1, SPEC_FIRST[-1])
    write_project(relative, spec_document(status="reviewed"))
    valid = run_progress("spec-close-check", relative)
    check(valid.returncode == 0 and len(valid.stdout.splitlines()) == 3,
          "the exact clean full round did not authorize status-only close:\n" + valid.stdout + valid.stderr)
    write_project(relative, spec_document(status="reviewed", extra="\nNormative change.\n"))
    changed = run_progress("spec-close-check", relative)
    check(changed.returncode != 0, "SPEC close accepted a post-review normative edit")


@test
def spec_commit_script_consumes_and_records_the_frozen_clean_round():
    relative = seed_spec()
    open_spec_round(1, SPEC_FIRST)
    for mandate in SPEC_FIRST[:-1]:
        receive_spec_report(1, mandate)
    write_project(relative, spec_document(status="reviewed"))
    script = os.path.join(WORKSPACE, "prompts", "common", "spec-commit.sh")
    premature = subprocess.run(
        [script, relative, "docs: validate demo spec", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(premature.returncode != 0
          and not os.path.exists(os.path.join(WORKSPACE, "spec-commit-in-progress"))
          and subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                             capture_output=True).returncode != 0,
          "spec-commit.sh mutated before the final full round was complete")
    receive_spec_report(1, SPEC_FIRST[-1])
    proc = subprocess.run(
        [script, relative, "docs: validate demo spec", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    close = journal_lines()[-1]
    check(close["kind"] == "spec.committed"
          and close["data"]["spec_round"] == 1
          and close["data"]["review_sha256"]
          and close["data"]["spec_sha256"],
          "spec-commit.sh did not record its exact clean-round proof")
    check(not os.path.exists(os.path.join(WORKSPACE, "spec-commit-in-progress")),
          "the completed SPEC close left its pending marker")


@test
def spec_commit_retry_finishes_only_the_frozen_journal_tail():
    relative = seed_spec()
    open_spec_round(1, SPEC_FIRST)
    receive_full_spec_round(1, SPEC_FIRST)
    write_project(relative, spec_document(status="reviewed"))
    cfg = default_config()
    cfg["fail"] = [["whoami"]]
    set_config(cfg)
    script = os.path.join(WORKSPACE, "prompts", "common", "spec-commit.sh")
    first = subprocess.run(
        [script, relative, "docs: validate demo spec", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    marker = os.path.join(WORKSPACE, "spec-commit-in-progress")
    check(first.returncode != 0 and os.path.isfile(marker),
          "the interrupted close did not preserve its frozen marker")
    first_sha = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    set_config(default_config())
    retry = subprocess.run(
        [script, relative, "docs: validate demo spec", "-"], cwd=REPO,
        capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(retry.returncode == 0, retry.stdout + retry.stderr)
    final_sha = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    count = subprocess.run(
        ["git", "-C", REPO, "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    check(final_sha == first_sha and count == "1" and not os.path.exists(marker),
          "the close retry repeated its commit or failed to settle its marker")


@test
def spec_loop_recheck_requires_exact_fresh_verifier_brackets_and_artifact():
    state_path = seed_direct_ruling(ruling="R1", route="spec-fixer")
    authority = {
        "authority_kind": "ruling.ready", "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    }
    append_note("fixer.dispatched", {"ruling": "R1", "route": "spec-fixer", **authority})
    commit_op, sha = "close-op-1", "a" * 40
    append_note("spec.committed", {
        "op": commit_op, "sha": sha, "spec_round": 4,
        "review_sha256": "b" * 64, "spec_sha256": "c" * 64,
    })
    common = {"owner": "spec-loop", "commit_op": commit_op, "sha": sha,
              "ruling": "R1", **authority}
    recheck = {
        "owner": "spec-loop", "sha": sha, "commit_op": commit_op,
        "accepted": True, "missing": [],
        "rulings": [{"ruling": "R1", **authority}],
        "actions": [{"answer": "R1", "status": "active", "route": "spec-fixer"}],
        "verifiers": [{"ruling": "R1", "present": True}],
    }
    artifact_path = "reports/answers/spec-loop-close-op-1.json"
    write_report(artifact_path, json.dumps(recheck, sort_keys=True))
    recheck["artifact_sha256"] = file_sha256(artifact_path)
    before = len(journal_lines())
    skipped = run_progress(
        "note", "decision.recheck.completed", "--text", artifact_path, "--data", json.dumps(recheck)
    )
    check(skipped.returncode != 0 and len(journal_lines()) == before,
          "a SPEC-loop recheck without a physical verifier reached the journal")
    started = run_progress("subagent-started", "finding-verifier", "--data", json.dumps(common))
    check(started.returncode == 0, started.stdout + started.stderr)
    ended = run_progress(
        "subagent-ended", "finding-verifier", "--data", json.dumps({**common, "present": True})
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    accepted = run_progress(
        "note", "decision.recheck.completed", "--text", artifact_path, "--data", json.dumps(recheck)
    )
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)
    terminal = {"answer": "R1", "ruling": "R1", "route": "spec-fixer",
                "sha": sha, "recheck_op": commit_op, **authority}
    closed = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(closed.returncode == 0, closed.stdout + closed.stderr)


@test
def damaged_historical_spec_loop_recheck_cannot_terminalize_a_ruling():
    state_path = seed_direct_ruling(ruling="R1", route="spec-fixer")
    authority = {
        "authority_kind": "ruling.ready", "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    }
    append_note("fixer.dispatched", {"ruling": "R1", "route": "spec-fixer", **authority})
    commit_op, sha = "close-op-damaged", "d" * 40
    append_note("spec.committed", {
        "op": commit_op, "sha": sha, "spec_round": 2,
        "review_sha256": "e" * 64, "spec_sha256": "f" * 64,
    })
    data = {
        "owner": "spec-loop", "sha": sha, "commit_op": commit_op,
        "accepted": True, "missing": [],
        "rulings": [{"ruling": "R1", **authority}],
        "actions": [{"answer": "R1", "status": "active", "route": "spec-fixer"}],
        "verifiers": [{"ruling": "R1", "present": True}],
    }
    artifact_path = "reports/answers/damaged-spec-loop.json"
    write_report(artifact_path, json.dumps(data, sort_keys=True))
    data["artifact_sha256"] = file_sha256(artifact_path)
    append_note("decision.recheck.completed", data, artifact_path)
    before = len(journal_lines())
    terminal = {"answer": "R1", "ruling": "R1", "route": "spec-fixer",
                "sha": sha, "recheck_op": commit_op, **authority}
    refused_terminal = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(refused_terminal.returncode != 0 and len(journal_lines()) == before,
          "a damaged historical SPEC-loop recheck terminalized its ruling")


@test
def no_arguments_is_refused():
    proc = run_progress()
    check(proc.returncode != 0, "no subcommand must not succeed")
    check(journal_lines() == [], "and must journal nothing")


# --------------------------------------------------------- caller resolution

@test
def whoami_failure_stops_everything():
    cfg = default_config()
    cfg["fail"] = [["whoami"]]
    set_config(cfg)
    refused(run_progress("note", "ruling", "--text", "who am I"))
    refused(run_progress("session-started", TARGET))


@test
def whoami_without_session_id_fails_loudly():
    cfg = default_config()
    cfg["whoami"] = {}  # valid JSON, no identity — and no detail worth printing
    set_config(cfg)
    proc = run_progress("note", "ruling", "--text", "anonymous")
    refused(proc)
    check("session_id" in proc.stdout, "the error must name the missing session_id")


@test
def missing_cli_binary_fails_loudly():
    env = dict(ENV)
    env["TWICC_BIN"] = "/nonexistent/twicc-binary"
    proc = run_progress("note", "ruling", "--text", "no CLI here", env=env)
    check(proc.returncode != 0, "a missing CLI must not succeed")
    check(journal_lines() == [], "and must journal nothing")


@test
def unreadable_cli_output_fails_loudly():
    cfg = default_config()
    cfg["garbage"] = [["whoami"]]  # exit 0, but the output is not JSON
    set_config(cfg)
    proc = run_progress("note", "ruling", "--text", "garbled")
    refused(proc)
    check("unreadable" in proc.stdout, "the error must name the unreadable output")


@test
def empty_caller_annotations_yield_a_bare_line():
    cfg = default_config()
    cfg["whoami"]["session"]["annotations"] = {}
    set_config(cfg)
    line = the_line(run_progress("note", "ruling", "--text", "no context"))
    context_fields = ("mode", "lot", "task", "attempt", "round", "mandate", "job")
    check(all(key not in line for key in context_fields),
          f"no annotations must mean no context fields, not empty ones: {line}")
    proc = run_progress("notes")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    ruling_line = next(l for l in proc.stdout.splitlines() if "· ruling ·" in l)
    check(ruling_line.rstrip().endswith(CALLER),
          "the header must stop after the author when there is no context")


@test
def whoami_without_payload_falls_back_to_session():
    cfg = default_config()
    cfg["whoami"] = {"session_id": CALLER}  # no embedded session payload
    set_config(cfg)
    line = the_line(run_progress("note", "ruling", "--text", "still attributed"))
    check(line["by"] == CALLER and line["mode"] == "construction",
          "context must be fetched through `session <caller>` when whoami omits it")
    check(["session", CALLER] in cli_calls(), "the fallback call must have happened")


# ------------------------------------------------------------- concurrency

def _concurrent_worker(script_path, worker_idx, count):
    # Each worker imports its own copy of the module and hammers the
    # low-level append — the exact code path every subcommand writes through.
    # spec_from_file_location does not add the module's directory to sys.path,
    # so reproduce normal script import semantics for adjacent dependencies.
    script_dir = os.path.dirname(script_path)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(f"progress_w{worker_idx}", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(script_dir)
    for seq in range(count):
        mod.write_line({"ts": "t", "by": f"w{worker_idx}", "event": "note",
                        "kind": "ruling", "text": "x" * 1000,
                        "data": {"w": worker_idx, "seq": seq}})


def _positive_short_write_worker(script_path):
    """Make the real append syscall write a positive prefix, then report it."""
    script_dir = os.path.dirname(script_path)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            f"progress_short_{os.getpid()}", script_path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(script_dir)

    write = mod.os.write

    def short_write(fd, payload):
        prefix = max(1, len(payload) // 2)
        return write(fd, payload[:prefix])

    mod.os.write = short_write
    try:
        mod.write_line({"ts": "t", "by": "short", "event": "note",
                        "kind": "ruling", "text": "x" * 1000})
    except OSError as exc:
        if "short journal write" not in str(exc):
            raise
    else:
        raise AssertionError("a positive short write returned successfully")


def _dashboard_refresh_worker(script_path, copied, release, locking, done, pause_after_copy):
    """Run the real refresh with deterministic hooks around copy or flock."""
    script_dir = os.path.dirname(script_path)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            f"progress_dashboard_{os.getpid()}", script_path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(script_dir)

    if pause_after_copy:
        copyfile = mod.shutil.copyfile

        def controlled_copy(source, target):
            result = copyfile(source, target)
            copied.set()
            if not release.wait(30):
                raise TimeoutError("dashboard test did not release the older publisher")
            return result

        mod.shutil.copyfile = controlled_copy
    else:
        flock = mod.fcntl.flock

        def observed_flock(fd, operation):
            if operation == mod.fcntl.LOCK_EX:
                locking.set()
            return flock(fd, operation)

        mod.fcntl.flock = observed_flock

    mod.refresh_dashboard()
    done.set()


@test
def concurrent_appends_do_not_interleave():
    workers, per_worker = 4, 50
    procs = [multiprocessing.Process(target=_concurrent_worker, args=(SCRIPT, i, per_worker))
             for i in range(workers)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        check(p.exitcode == 0, "a concurrency worker failed")
    lines = journal_lines()  # a torn line fails json.loads, which fails the test
    check(len(lines) == workers * per_worker,
          f"expected {workers * per_worker} intact lines, got {len(lines)}")
    seen = {(line["data"]["w"], line["data"]["seq"]) for line in lines}
    check(len(seen) == workers * per_worker, "lines were lost or duplicated")
    check(all(line["text"] == "x" * 1000 for line in lines), "a line lost part of its text")
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "rb") as source:
        raw = source.read()
    check(raw.endswith(b"\n") and raw.count(b"\n") == workers * per_worker,
          "every concurrent append must end in one physical newline")


@test
def positive_short_write_fails_and_rolls_back_its_fragment():
    proc = multiprocessing.Process(target=_positive_short_write_worker, args=(SCRIPT,))
    proc.start()
    proc.join(30)
    check(proc.exitcode == 0, "the controlled short-write worker did not get the expected failure")
    journal = os.path.join(WORKSPACE, "progress.jsonl")
    check(os.path.exists(journal) and os.path.getsize(journal) == 0,
          "a failed positive short write left its fragment in the journal")


@test
def positive_short_write_cannot_poison_the_next_event():
    proc = multiprocessing.Process(target=_positive_short_write_worker, args=(SCRIPT,))
    proc.start()
    proc.join(30)
    check(proc.exitcode == 0, "the controlled short-write worker did not get the expected failure")
    line = the_line(run_progress("note", "resumed", "--text", "the next event"))
    check(line["kind"] == "resumed" and line["text"] == "the next event",
          "the event after a short write did not remain independently readable")


@test
def interrupted_final_fragment_is_removed_before_the_next_event():
    journal = os.path.join(WORKSPACE, "progress.jsonl")
    first = {"ts": "t", "by": "first", "event": "note", "kind": "resumed"}
    with open(journal, "wb") as target:
        target.write((json.dumps(first) + "\n").encode("utf-8"))
        target.write(b'{"ts":"t","by":"interrupted"')

    proc = run_progress("note", "resumed", "--text", "after recovery")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check("discarded an incomplete final event" in proc.stdout,
          "tail recovery must report the interrupted event it discarded")
    lines = journal_lines()
    check(len(lines) == 2 and lines[0] == first and lines[1]["text"] == "after recovery",
          f"tail recovery did not preserve the complete events: {lines}")


@test
def concurrent_full_calls_stay_parseable():
    procs = [subprocess.Popen([sys.executable, SCRIPT, "note", "ruling",
                               "--text", f"concurrent {i} " + "y" * 500],
                              env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for i in range(6)]
    for p in procs:
        check(p.wait(120) == 0, "a concurrent call failed")
    lines = journal_lines()
    check(len(lines) == 6, f"expected 6 lines, got {len(lines)}")
    check({line["text"].split()[1] for line in lines} == {str(i) for i in range(6)},
          "each concurrent call must land exactly once")


# ------------------------------------------------------------------- notes

@test
def notes_prints_notes_and_nothing_else():
    run_progress("session-started", TARGET)
    run_progress("subagent-started", "completeness")
    the_notes = [
        run_progress("note", "ruling", "--text", "The human chose blue"),
        run_progress("note", "handover", "--data", '{"to":"abc"}'),
    ]
    for proc in the_notes:
        check(proc.returncode == 0, proc.stdout + proc.stderr)
    proc = run_progress("notes")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    out = proc.stdout
    check("ruling" in out and "The human chose blue" in out, f"the note text is missing:\n{out}")
    check("handover" in out and '"to"' in out and '"abc"' in out, f"the note data is missing:\n{out}")
    check(CALLER in out, "each note must say who wrote it")
    check("session-started" not in out and "gate-runner" not in out,
          "session and subagent traffic must never appear in notes")
    ruling_line = next(l for l in out.splitlines() if "· ruling ·" in l)
    check(ruling_line.startswith("20"), "each note must start with its timestamp")


@test
def notes_with_no_journal_is_not_an_error():
    proc = run_progress("notes")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check("No journal" in proc.stdout, "an empty run must read as empty, not as broken")
    check(journal_lines() == [], "notes must write nothing")


@test
def notes_tolerates_corrupt_and_blank_lines():
    # Only the test may corrupt the journal by hand: it simulates the damage
    # the script itself can never produce, and proves reading survives it.
    run_progress("note", "ruling", "--text", "still readable")
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as f:
        f.write("\n{broken json\n")
    proc = run_progress("notes")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check("1 unreadable" in proc.stdout, "corruption must be announced, not hidden")
    check("still readable" in proc.stdout, "the valid notes must still be printed")


@test
def authority_consumers_fail_closed_on_an_interior_malformed_line():
    journal = os.path.join(WORKSPACE, "progress.jsonl")
    with open(journal, "wb") as target:
        target.write(b'{"ts":"t","by":"first","event":"note","kind":"resumed"}\n')
        target.write(b'{broken json\n')
        target.write(b'{"ts":"t","by":"last","event":"note","kind":"resumed"}\n')
    proc = run_progress(
        "note", "decision.conflict.opened",
        "--data", '{"owner":"R1","conflict":1}',
    )
    check(proc.returncode != 0, "an authority consumer accepted an unreadable journal")
    check("journal has an unreadable line" in proc.stdout,
          "the refusal must identify the journal integrity failure")
    with open(journal, "rb") as source:
        check(source.read().count(b"\n") == 3,
              "the refused authority event must not append or rewrite interior damage")


@test
def notes_with_no_note_events_says_so():
    run_progress("session-started", TARGET)
    proc = run_progress("notes")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check("No notes" in proc.stdout, "a journal without notes must read as empty of notes")


# --------------------------------------------------------------- dashboard

@test
def dashboard_copy_is_refreshed_when_present():
    os.makedirs(os.path.join(WORKSPACE, "dashboard"))
    proc = run_progress("note", "ruling", "--text", "first")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    copy = os.path.join(WORKSPACE, "dashboard", "data", "progress.jsonl")
    journal = os.path.join(WORKSPACE, "progress.jsonl")
    check(os.path.exists(copy), "the dashboard copy must exist after a call")
    with open(copy, "rb") as a, open(journal, "rb") as b:
        check(a.read() == b.read(), "the copy must match the journal")
    proc = run_progress("note", "resumed")
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    with open(copy, "rb") as a, open(journal, "rb") as b:
        check(a.read() == b.read(), "every call must refresh the copy")


@test
def slower_dashboard_refresh_cannot_overwrite_a_newer_mirror():
    os.makedirs(os.path.join(WORKSPACE, "dashboard", "data"))
    journal = os.path.join(WORKSPACE, "progress.jsonl")
    copy = os.path.join(WORKSPACE, "dashboard", "data", "progress.jsonl")
    with open(journal, "w", encoding="utf-8") as f:
        f.write("A\n")

    older_copied = multiprocessing.Event()
    release_older = multiprocessing.Event()
    newer_locking = multiprocessing.Event()
    older_done = multiprocessing.Event()
    newer_done = multiprocessing.Event()
    older = multiprocessing.Process(
        target=_dashboard_refresh_worker,
        args=(SCRIPT, older_copied, release_older, multiprocessing.Event(),
              older_done, True),
    )
    older.start()
    check(older_copied.wait(30), "the older refresh did not pause after copying A")

    with open(journal, "a", encoding="utf-8") as f:
        f.write("B\n")
    newer = multiprocessing.Process(
        target=_dashboard_refresh_worker,
        args=(SCRIPT, multiprocessing.Event(), multiprocessing.Event(), newer_locking,
              newer_done, False),
    )
    newer.start()
    check(newer_locking.wait(30), "the newer refresh did not reach the publication lock")
    check(not older_done.is_set() and not newer_done.is_set(),
          "the newer refresh passed the older copy-and-publish critical section")

    release_older.set()
    older.join(30)
    newer.join(30)
    check(older.exitcode == 0 and newer.exitcode == 0,
          f"refresh workers failed: older={older.exitcode}, newer={newer.exitcode}")
    with open(journal, "rb") as authoritative, open(copy, "rb") as mirror:
        check(mirror.read() == authoritative.read() == b"A\nB\n",
              "an older dashboard snapshot overwrote the newer mirror")


@test
def missing_dashboard_is_not_an_error():
    proc = run_progress("note", "ruling", "--text", "no dashboard yet")
    check(proc.returncode == 0, "a missing dashboard/ must not fail the call:\n"
          + proc.stdout + proc.stderr)
    check(len(journal_lines()) == 1, "the journal line must land regardless")
    check(not os.path.exists(os.path.join(WORKSPACE, "dashboard")),
          "the script must not create the dashboard on its own")


@test
def dashboard_refresh_without_journal_copies_nothing():
    os.makedirs(os.path.join(WORKSPACE, "dashboard"))
    proc = run_progress("notes")  # a call that writes nothing, on a virgin run
    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check(not os.path.exists(os.path.join(WORKSPACE, "dashboard", "data")),
          "no journal yet: there is nothing to copy, and nothing to create")


@test
def dashboard_refresh_failure_warns_but_does_not_fail():
    os.makedirs(os.path.join(WORKSPACE, "dashboard"))
    with open(os.path.join(WORKSPACE, "dashboard", "data"), "w") as f:
        f.write("a file where the data directory should be")
    proc = run_progress("note", "ruling", "--text", "journal first")
    check(proc.returncode == 0,
          "a dashboard refresh failure must not fail a call whose line landed:\n"
          + proc.stdout + proc.stderr)
    check("WARNING" in proc.stdout, "but it must be said out loud")
    check(len(journal_lines()) == 1, "the journal line must have landed regardless")


@test
def partial_retirement_still_reaches_the_dashboard():
    os.makedirs(os.path.join(WORKSPACE, "dashboard"))
    cfg = default_config()
    cfg["fail"] = [["update-session", TARGET, "archive"]]
    set_config(cfg)
    proc = run_progress("session-retired", TARGET, "done", "--archive", "--hide")
    check(proc.returncode != 0, "the partial retirement must still exit non-zero")
    copy = os.path.join(WORKSPACE, "dashboard", "data", "progress.jsonl")
    check(os.path.exists(copy), "the journaled partial outcome must reach the dashboard")
    with open(copy, encoding="utf-8") as f:
        line = json.loads(f.read().strip())
    check(line["archived"] is False, "the copy must carry what actually happened")


@test
def risk_admission_has_one_shared_impact_vocabulary():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = f.read()
    with open(os.path.join(PRODUCT_PROMPTS, "lens-common.md"), encoding="utf-8") as f:
        product = f.read()

    for level, meaning in (
        ("CRITICAL", "silent wrong delivery"),
        ("IMPORTANT", "false result that remains detectable and recoverable"),
        ("MINOR", "without a credible wrong result"),
    ):
        check(level in risk and meaning in risk,
              f"review-risk.md must define the shared {level} impact")
    check("Severity, one of three:" not in product,
          "PRODUCT REVIEW must not keep a second impact vocabulary")
    check("`prompts/common/review-risk.md` defines the impact vocabulary" in product,
          "PRODUCT REVIEW must consume the shared impact vocabulary")

    reviewer_prompts = [
        os.path.join(SPEC_PROMPTS, f"reviewer-{mandate}.md")
        for mandate in ("enumerator", "ripple", "verifier", "feasibility", "judge", "scoped")
    ]
    reviewer_prompts.extend(
        os.path.join(PRODUCT_PROMPTS, f"lens-{mandate}.md")
        for mandate in ("unlooked", "user", "meaning", "quality", "coverage")
    )
    for path in reviewer_prompts:
        with open(path, encoding="utf-8") as f:
            prompt = f.read()
        for level in ("CRITICAL", "IMPORTANT", "MINOR"):
            check(level not in prompt,
                  f"leaf reviewer prompts must not assign a local {level} impact: {path}")


@test
def risk_filtered_decisions_never_use_the_shared_blocker_route():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = f.read()
    with open(os.path.join(COMMON_PROMPTS, "worker.md"), encoding="utf-8") as f:
        worker = f.read()
    with open(os.path.join(SPEC_PROMPTS, "reviewer-common.md"), encoding="utf-8") as f:
        spec = f.read()

    check("do not report it, ping `parent`, or stop" in risk.lower(),
          "the risk contract must close every filtered DECISION route")
    check("only after `review-risk.md` admits" in worker,
          "the common worker DECISION rule must defer to risk admission")
    check("only after `review-risk.md` admits" in spec,
          "the SPEC DECISION rule must defer to risk admission")

    for mandate in ("unlooked", "user", "meaning", "quality", "coverage"):
        path = os.path.join(PRODUCT_PROMPTS, f"lens-{mandate}.md")
        with open(path, encoding="utf-8") as f:
            lens = f.read()
        check("`<workspace>/prompts/common/review-risk.md`" in lens,
              f"the {mandate} lens must load the shared admission contract")
        check("Report it as one." not in lens,
              f"the {mandate} lens must not bypass DECISION admission")

    for mandate in ("unlooked", "user"):
        path = os.path.join(PRODUCT_PROMPTS, f"lens-{mandate}.md")
        with open(path, encoding="utf-8") as f:
            lens = f.read()
        check("Only if `review-risk.md` admits this question" in lens,
              f"the {mandate} lens must qualify its local DECISION route")


@test
def spec_operational_blockers_bypass_risk_admission():
    with open(os.path.join(SPEC_PROMPTS, "reviewer-common.md"), encoding="utf-8") as f:
        spec = f.read()

    check("A genuine operational blocker" in spec,
          "SPEC must name the operational-blocker route separately")
    check("does not pass through `review-risk.md`" in spec,
          "an operational blocker must bypass probability admission")
    check("A product question only a human can answer" in spec,
          "SPEC must keep the product-question admission route separate")


@test
def risk_filtered_candidates_never_enter_completion_counts():
    rules_path = os.path.join(SPEC_PROMPTS, "completion-rules.md")
    with open(rules_path, encoding="utf-8") as f:
        rules = f.read()
    check("An adverse-result datum counts or names only admitted findings" in rules,
          "SPEC completion rules must exclude filtered observations from adverse results")
    check("never encode a pass/fail fraction" in rules,
          "coverage evidence must not disclose a filtered result through a fraction")

    completion_files = [
        os.path.join(SPEC_PROMPTS, f"reviewer-{mandate}-completion.md")
        for mandate in ("enumerator", "ripple", "verifier", "feasibility", "judge", "scoped")
    ]
    for path in completion_files:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        check("completion-rules.md" in content,
              f"the SPEC completion template must consume the private-result rule: {path}")

    with open(os.path.join(PRODUCT_PROMPTS, "lens-coverage.md"), encoding="utf-8") as f:
        coverage = f.read()
    check("N of N" not in coverage,
          "PRODUCT coverage must not expose a filtered gap through a pass fraction")
    for label in (
        "root-lot decisions checked", "sub-lot findings checked", "Global Constraints checked",
    ):
        matching = [line for line in coverage.splitlines()
                    if line.startswith(f"    - [ ] {label} — ")]
        check(len(matching) == 1 and "admitted gap IDs or none" in matching[0],
              f"PRODUCT coverage must separate checked work from admitted gaps: {label}")
    check("every admitted absence has a complete search proof" in coverage,
          "PRODUCT coverage must account only for admitted absence findings")

    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = f.read()
    normalized_risk = " ".join(risk.split())
    check("may mention why the probability changed" not in risk,
          "an admitted finding must not expose an earlier private occurrence")
    check("never mention the earlier private occurrence or its filtering basis" in normalized_risk,
          "the private-history barrier must remain strict after later admission")


@test
def probability_admission_applies_only_to_new_candidates():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = " ".join(f.read().split())
    with open(os.path.join(SPEC_PROMPTS, "reviewer-common.md"), encoding="utf-8") as f:
        common = " ".join(f.read().split())
    with open(os.path.join(SPEC_PROMPTS, "reviewer-scoped.md"), encoding="utf-8") as f:
        scoped = " ".join(f.read().split())
    with open(os.path.join(SPEC_PROMPTS, "reviewer-scoped-completion.md"), encoding="utf-8") as f:
        scoped_completion = " ".join(f.read().split())
    with open(os.path.join(PRODUCT_PROMPTS, "lens-coverage.md"), encoding="utf-8") as f:
        coverage = " ".join(f.read().split())

    check("applies only to a newly discovered candidate" in risk,
          "probability admission must be limited to newly discovered candidates")
    check("A finding already admitted is not admitted again" in risk,
          "the shared contract must preserve an existing finding through verification")
    check("New candidates discovered during verification still use this admission table" in risk,
          "verification discoveries must retain ordinary probability admission")

    for name, prompt in (("SPEC re-review", common), ("scoped verification", scoped)):
        check("already admitted" in prompt and "do not pass" in prompt
              and "through `review-risk.md` again" in prompt,
              f"{name} must not re-admit an existing finding")
        check("new candidate" in prompt and "`review-risk.md`" in prompt,
              f"{name} must still admit new discoveries normally")
    check("`NOT ADDRESSED` is verified and still open" in scoped_completion,
          "the scoped completion account must preserve every surviving finding")

    check("Evaluate each still-true finding through `review-risk.md`" not in coverage,
          "PRODUCT coverage must not re-admit an existing sub-lot finding")
    check("already admitted" in coverage and "without applying `review-risk.md` again" in coverage,
          "PRODUCT coverage must preserve a still-true source finding")
    check("new candidate" in coverage and "uses `review-risk.md` normally" in coverage,
          "PRODUCT coverage must still admit new discoveries normally")


@test
def code_checker_probability_admission_is_private_and_attempt_scoped():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "code-checker.md"),
              encoding="utf-8") as f:
        checker = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"),
              encoding="utf-8") as f:
        implementer = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"),
              encoding="utf-8") as f:
        mode = " ".join(f.read().split())
    with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as f:
        skill = " ".join(f.read().split())

    check("CONSTRUCTION code checker" in risk,
          "the shared risk contract must include the severity-bearing code checker")
    check("design checker" in risk and "diagnostics" in risk,
          "non-severity construction roles must remain outside risk admission")
    for contract in (checker, implementer, mode, skill):
        check("task-<N>-attempt-<K>-code-risk-filtered.md" in contract,
              "every code-checker consumer must use one attempt-scoped private history")
    check("Code checker round <R>" in checker and "same private history" in checker,
          "all rounds and physical regenerations must share one attempt history")
    check("A new attempt uses a new path" in implementer,
          "a new attempt must not inherit another candidate's filtered history")
    check("Only newly discovered candidates" in checker,
          "the checker must not re-admit an existing public finding")
    check("does not appear in this JSON object" in checker,
          "a filtered observation must stay outside the physical result")
    check('"impact":"CRITICAL|IMPORTANT|MINOR"' in checker,
          "every admitted code finding must publish one impact")
    check("Do not publish probability" in checker,
          "the private probability classification must not enter the checker result")


@test
def code_checker_admission_keeps_one_strict_output_route():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "code-checker.md"),
              encoding="utf-8") as f:
        checker = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"),
              encoding="utf-8") as f:
        implementer = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"),
              encoding="utf-8") as f:
        mode = " ".join(f.read().split())
    with open(os.path.join(SPEC_PROMPTS, "reviewer-common.md"), encoding="utf-8") as f:
        spec = " ".join(f.read().split())
    with open(os.path.join(PRODUCT_PROMPTS, "lens-common.md"), encoding="utf-8") as f:
        product = " ".join(f.read().split())

    check("The CONSTRUCTION code checker does not own a `DECISION` output route" in risk,
          "the shared DECISION route must exclude the strict code-checker result")
    check("Return every admitted observation only through the strict JSON result" in checker,
          "the code checker must have one result channel")
    check("Do not emit `DECISION`, message the implementer separately, or stop outside that JSON" in checker,
          "the code checker must not bypass its physical terminal")
    for name, contract in (("implementer", implementer), ("construction mode", mode)):
        lowered = contract.lower()
        check("the implementer alone" in lowered and "blocked" in lowered
              and "decision" in lowered,
              f"the {name} must retain ownership of code-finding authority routing")
    check("Write it in your report, ping `parent`, and stop" in spec,
          "SPEC must retain its admitted DECISION route")
    check("This proof form applies only after `review-risk.md` admits the question" in product
          and "A human answers it" in product,
          "PRODUCT REVIEW must retain its admitted DECISION route")


# ------------------------------------------------------------------ runner

def main():
    global BASE, REPO, WORKSPACE, SCRIPT, FAKE_DIR, ENV
    BASE = tempfile.mkdtemp(prefix="progress-test-")
    try:
        REPO = os.path.join(BASE, "repo")
        WORKSPACE = os.path.join(REPO, ".superpowers", "bwr", "test-run")
        os.makedirs(os.path.join(WORKSPACE, "prompts", "common"))
        os.makedirs(os.path.join(WORKSPACE, "prompts", "spec"))
        os.makedirs(os.path.join(WORKSPACE, "prompts", "product-review"))
        os.makedirs(os.path.join(WORKSPACE, "prompts", "amendment"))
        SCRIPT = os.path.join(WORKSPACE, "prompts", "common", "progress.py")
        shutil.copyfile(SOURCE, SCRIPT)
        os.chmod(SCRIPT, 0o755)
        shutil.copyfile(AUTHORITY_SOURCE,
                        os.path.join(WORKSPACE, "prompts", "common", "authority_precedence.py"))
        shutil.copyfile(SPEC_EDIT_SOURCE,
                        os.path.join(WORKSPACE, "prompts", "common", "spec_edit_auth.py"))
        for name in ("spec-commit.sh", "attempt-closer.sh", "bare-stop.sh", "stop.sh",
                     "disposable-worktree.sh", "document-copy.sh"):
            destination = os.path.join(WORKSPACE, "prompts", "common", name)
            shutil.copyfile(os.path.join(COMMON_PROMPTS, name), destination)
            os.chmod(destination, 0o755)
        for name in (
            "reviewer-enumerator-completion.md", "reviewer-ripple-completion.md",
            "reviewer-verifier-completion.md", "reviewer-feasibility-completion.md",
            "reviewer-judge-completion.md", "reviewer-scoped-completion.md",
            "fixer-completion.md",
        ):
            shutil.copyfile(os.path.join(SPEC_PROMPTS, name),
                            os.path.join(WORKSPACE, "prompts", "spec", name))
        for mandate in ("unlooked", "user", "meaning", "quality", "coverage"):
            name = f"lens-{mandate}.md"
            shutil.copyfile(os.path.join(PRODUCT_PROMPTS, name),
                            os.path.join(WORKSPACE, "prompts", "product-review", name))
        for name in ("verify-open.sh", "verify-close.sh"):
            destination = os.path.join(WORKSPACE, "prompts", "product-review", name)
            shutil.copyfile(os.path.join(PRODUCT_PROMPTS, name), destination)
            os.chmod(destination, 0o755)
        destination = os.path.join(WORKSPACE, "prompts", "amendment", "amendment-commit.sh")
        shutil.copyfile(os.path.join(AMENDMENT_PROMPTS, "amendment-commit.sh"), destination)
        os.chmod(destination, 0o755)
        os.makedirs(os.path.join(WORKSPACE, "prompts", "construction"))
        for name in (
            "gate-check.sh", "gate_file.py", "gate_execution.py", "gate_report.py",
            "construction_review.py",
        ):
            destination = os.path.join(WORKSPACE, "prompts", "construction", name)
            shutil.copyfile(os.path.join(HERE, "prompts", "construction", name), destination)
            os.chmod(destination, 0o755)

        FAKE_DIR = os.path.join(BASE, "fake")
        os.makedirs(FAKE_DIR)
        fake = os.path.join(FAKE_DIR, "fake_twicc.py")
        with open(fake, "w") as f:
            f.write(FAKE_TWICC)

        ENV = dict(os.environ)
        ENV["TWICC_BIN"] = f"{shlex.quote(sys.executable)} {shlex.quote(fake)}"
        ENV["FAKE_TWICC_DIR"] = FAKE_DIR

        selected = TESTS
        test_filter = os.environ.get("BWR_TEST_FILTER")
        if test_filter:
            selected = [fn for fn in TESTS if test_filter in fn.__name__]
            if not selected:
                raise RuntimeError(f"no test name contains {test_filter!r}")
        failures = 0
        for fn in selected:
            reset()
            try:
                fn()
            except Exception:
                failures += 1
                print(f"FAIL  {fn.__name__}")
                traceback.print_exc()
                print()
            else:
                print(f"ok    {fn.__name__}")
        print()
        if failures:
            print(f"{failures} of {len(selected)} tests FAILED")
            sys.exit(1)
        print(f"all {len(selected)} tests passed")
    finally:
        shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    main()
