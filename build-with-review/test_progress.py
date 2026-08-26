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
import fcntl
import multiprocessing
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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
    delayed_reads = cfg.get("session_visibility_delays", {}).get(args[1], 0)
    if delayed_reads:
        with open(os.path.join(base, "calls.jsonl")) as f:
            reads = sum(json.loads(line) == ["session", args[1]] for line in f)
        if reads <= delayed_reads:
            print(f"Error: session '{args[1]}' not found.", file=sys.stderr)
            sys.exit(1)
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


def set_caller_bwr(**values):
    with open(os.path.join(FAKE_DIR, "config.json")) as source:
        config = json.load(source)
    for payload in (
        config["whoami"]["session"]["annotations"]["bwr"],
        config["sessions"][CALLER]["annotations"]["bwr"],
    ):
        for key, value in values.items():
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
    set_config(config)


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
        "amendment-sweep-preflight.json", "bare-stop-in-progress",
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


def block_design_contract(round_number):
    result = run_progress(
        "note", "design.review.blocked", "--round", str(round_number),
        "--data", '{"check":"design"}',
    )
    check(result.returncode == 0, result.stdout + result.stderr)


def block_final_design_contract():
    block_design_contract(10)


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


def drive_design_to_round_ten_contract_blocker():
    previous = []
    for round_number in range(1, 11):
        opening = open_design_round(round_number)
        finding = {
            "id": 1,
            "where": "frozen task contract" if round_number == 10 else f"Design round {round_number}",
            "what": "The frozen task contract omits one required parent outcome.",
            "why": "The current task cannot guarantee its exact parent product obligation.",
            "impact": "IMPORTANT", "previous": [1] if previous else [],
        }
        findings = [finding]
        if round_number == 10:
            findings.append({
                "id": 2, "where": "Design round 10",
                "what": "The final Design retains another unresolved defect.",
                "why": "The next Design generation must account for the complete immutable batch.",
                "impact": "IMPORTANT", "previous": [],
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


def seed_committed_construction_attempt_with_spec(lot="lot-1", task=3, attempt=2):
    spec_relative = "docs/plans/construction-attempt-design.md"
    committed_plan = f"docs/plans/{os.path.basename(WORKSPACE)}-{lot}-plan.md"
    plan = ["# Plan", "", f"Spec: {spec_relative}", ""]
    for number in range(1, task + 1):
        plan.extend([
            f"## Task {number} - Task {number}",
            f"Achieves: Complete task {number}.",
            f"To verify: Task {number} is complete.",
            "",
            "### Design",
            "Implement the accepted task contract.",
        ])
        plan.append("")
    plan_text = "\n".join(plan)
    write_report(f"plans/{lot}-plan.md", plan_text)
    write_project(spec_relative, spec_document())
    write_project(committed_plan, plan_text)
    write_project(".gitignore", ".superpowers/\n")
    subprocess.run(
        ["git", "-C", REPO, "add", ".gitignore", spec_relative, committed_plan], check=True,
    )
    subprocess.run(
        ["git", "-C", REPO, "commit", "-qm", "seed active construction attempt"],
        check=True,
    )
    append_note(
        "run.started", {"cap": 3}, "construction attempt",
        mode="construction", lot=lot, job="controller",
    )
    append_note(
        "plan.written", {"tasks": task, "op": "construction-attempt-plan"},
        mode="construction", lot=lot, job="controller",
    )
    helper = os.path.join(WORKSPACE, "prompts", "construction", "construction_review.py")
    state = json.loads(subprocess.check_output(
        [sys.executable, helper, "plan-state", lot, str(task)], text=True, cwd=REPO,
    ))
    base = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
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
    return spec_relative


def open_clean_construction_amendment_for_attempt(
        lot="lot-1", task=3, attempt=2, *, ruling="R1",
):
    state_path = seed_direct_ruling(ruling=ruling, route="amendment")
    order = f"apply {ruling} and return to {lot} task {task} attempt {attempt}"
    opened = run_progress(
        "note", "amendment.opened",
        "--data", json.dumps({
            "amendment": 1,
            "origin": "construction",
            "ruling": ruling,
            "authority_kind": "ruling.ready",
            "authority_ref": ruling,
            "authority_sha256": file_sha256(state_path),
        }),
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    write_report("amendments/1.md", amendment_document(1, order, (ruling,)))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    written = run_progress(
        "note", "amendment.written", "--data", '{"amendment":1}',
        "--text", os.path.join(WORKSPACE, "amendments", "1.md"),
    )
    check(written.returncode == 0, written.stdout + written.stderr)
    accept_reach_sweep(
        1, reach_report(sources=(ruling,)), f"amendment-supersession-{ruling}-reach",
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


def append_real_code_verdict(*, attempt, findings):
    if not any(
        entry.get("kind") == "verdict.consumed"
        and (entry.get("data") or {}).get("check") == "design"
        and entry.get("attempt") == attempt
        for entry in journal_lines()
    ):
        append_checker_verdict(
            "design", lot="lot-1", task=3, attempt=attempt,
            round_number=1, findings=0,
        )
    gate = seed_review_gate(attempt=attempt)
    opened = run_progress(
        "subagent-started", "code-checker", "--round", "1",
        "--data", json.dumps({"gate": gate}),
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    spent = run_progress(
        "note", "bound.spent", "--round", "1", "--text", "code checker round 1 of 10",
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    started = [
        entry for entry in journal_lines()
        if entry.get("event") == "subagent-started"
        and entry.get("kind") == "code-checker" and entry.get("attempt") == attempt
    ][-1]["data"]
    result = code_result_source(started, findings=findings)
    ended = run_progress(
        "subagent-ended", "code-checker", "--round", "1",
        "--data", json.dumps({"result": result}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    verdict = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", json.dumps({
            "check": "code", "outcome": "clean" if findings == 0 else "findings",
        }),
    )
    check(verdict.returncode == 0, verdict.stdout + verdict.stderr)
    return started


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


def reach_report(hops=(0,), dispositions=(), sources=("A1/order",), findings=(),
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
    for ordinal, severity in enumerate(findings, 1):
        lines.extend([
            "", f"## {severity} F{ordinal} — Reach finding {ordinal}",
            "The reached behavior contradicts the amendment.",
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


CONSTRUCTION_ONLY_SPEC = "docs/plans/construction-only-design.md"


def seed_construction_only_amendment_context(*, plan_spec_lines=None):
    spec_relative = CONSTRUCTION_ONLY_SPEC
    write_project(spec_relative, spec_document())
    commit, gate, owner = seed_task_gate(
        "lot-1", "construction-only-amendment-context", spec_relative=spec_relative,
        plan_spec_lines=plan_spec_lines,
    )
    opening = run_progress(
        "note", "pass.opened",
        "--data", json.dumps({"built": "lot-1", "commit": commit, "gate": gate}),
    )
    check(opening.returncode == 0, opening.stdout + opening.stderr)
    check(not any(entry.get("kind") == "spec.written" for entry in journal_lines()),
          "the construction-only fixture unexpectedly created a SPEC readiness event")
    return spec_relative


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


def append_reach_retirement(sweep, session, status):
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps({
            "ts": "t", "by": "fixture", "event": "session-retired",
            "session": session, "mode": "amendment", "mandate": "reach",
            "round": sweep, "status": status,
        }, separators=(",", ":")) + "\n")


def configure_reach_session(session, sweep):
    cfg = default_config()
    controller = {
        "schema": 1, "job": "controller", "mode": "amendment",
        "feature": "demo-feature", "lot": "lot-1", "status": "working",
    }
    cfg["whoami"] = {"session_id": CALLER,
                     "session": {"id": CALLER, "annotations": {"bwr": controller}}}
    cfg["sessions"][CALLER] = {"id": CALLER, "annotations": {"bwr": controller}}
    cfg["sessions"][session] = {
        "id": session,
        "annotations": {"bwr": {
            "schema": 1, "job": "reviewer", "mode": "amendment",
            "feature": "demo-feature", "lot": "lot-1", "mandate": "reach",
            "round": sweep, "status": "working",
        }},
    }
    set_config(cfg)


def accept_reach_sweep(sweep, report, session):
    write_report(f"reports/amendment/1/sweep-{sweep}.md", report)
    configure_reach_session(session, sweep)
    append_live_reach_session(sweep, session)
    preflight = run_progress("amendment-sweep-check", str(sweep))
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retirement = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retirement.returncode == 0, retirement.stdout + retirement.stderr)
    proof = json.loads(preflight.stdout)
    receipt = run_progress(
        "note", "sweep.reported", "--round", str(sweep),
        "--data", json.dumps({key: proof[key] for key in ("hop", "places", "closed")}),
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    return proof


def append_raw_reach_receipt(sweep, session, *, hop, places, closed):
    opening = next(entry for entry in reversed(journal_lines())
                   if entry.get("kind") == "amendment.opened")
    number = opening["data"]["amendment"]
    append_note("sweep.reported", {
        "amendment": number, "sweep": sweep,
        "opening_sha256": opening["data"]["opening_sha256"],
        "report_sha256": file_sha256(f"reports/amendment/{number}/sweep-{sweep}.md"),
        "session": session,
        "amendment_sha256": file_sha256(f"amendments/{number}.md"),
        "hop": hop, "places": places, "closed": closed, "done": True,
    }, mode="amendment", lot="lot-1", round=sweep)


def seed_written_amendment_for_reach(order="apply the reach order; return to product review",
                                     *, construction_only=False, plan_spec_lines=None):
    if construction_only:
        seed_construction_only_amendment_context(plan_spec_lines=plan_spec_lines)
    if not construction_only:
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
    session = f"clean-amendment-{number}-reach"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retired = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
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


def prepare_review_commit(built="lot-1", token=None, tasks=1, spec_relative=None,
                          plan_spec_lines=None):
    # Build one real clean candidate. The pass terminal rechecks this exact HEAD,
    # tree, gate blob and canonical physical gate report.
    write_project(".gitignore", ".superpowers/\n")
    plan_header = "# Plan\n\n"
    if plan_spec_lines is None:
        plan_spec_lines = (f"Spec: {spec_relative}",) if spec_relative else ()
    if plan_spec_lines:
        plan_header += "\n".join(plan_spec_lines) + "\n\n"
    manifest = plan_header + "\n\n".join(
        f"## Task {task} - Task {task}\n"
        f"Achieves: Complete task {task}.\n"
        f"To verify: Task {task} is complete."
        for task in range(1, tasks + 1)
    ) + "\n"
    plan_relative = f"docs/plans/test-run-{built}-plan.md"
    write_project(plan_relative, manifest)
    staged = [".gitignore", plan_relative]
    if spec_relative:
        staged.append(spec_relative)
    subprocess.run(["git", "-C", REPO, "add", *staged], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "plan review lot"], check=True)
    plan = plan_header + "\n\n".join(
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
                   precommit_head=True, spec_relative=None, plan_spec_lines=None):
    commit, tree, gate_blob = prepare_review_commit(
        built, token, tasks, spec_relative, plan_spec_lines,
    )
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
    gate_data = {
        "op": gate, "scope": "task", "owner": owner, "lot": built,
        "task": 1, "attempt": 1, "head": head, "base": head,
        "tree": tree, "gate": gate_blob, "code": code_proof,
    }
    append_subagent("subagent-started", "gate-runner", mandate="gate", data=gate_data)
    append_subagent(
        "subagent-ended", "gate-runner", mandate="gate",
        data={**gate_data, "green": True, "surface": "unchanged", "report": report_relative,
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
    set_caller_bwr(
        mode="product-review", lot=built, job="controller", task=None, attempt=None,
    )
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
    gate_data = {
        "op": gate, "scope": "baseline", "owner": owner, "lot": "-",
        "task": 0, "attempt": 0, "head": commit, "base": base,
        "tree": tree, "gate": gate_blob, "code": "-",
    }
    append_subagent("subagent-started", "gate-runner", mandate="gate", data=gate_data)
    append_subagent(
        "subagent-ended", "gate-runner", mandate="gate",
        data={**gate_data, "green": True,
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
    }, by=CALLER, mode="product-review", lot=built, job="controller")
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
def session_started_waits_for_a_created_session_to_become_visible():
    cfg = default_config()
    cfg["session_visibility_delays"] = {TARGET: 2}
    set_config(cfg)

    proc = run_progress("session-started", TARGET)

    check(proc.returncode == 0, proc.stdout + proc.stderr)
    check(len(journal_lines()) == 1, "the visibility retry must append exactly one opening")
    reads = [call for call in cli_calls() if call == ["session", TARGET]]
    check(len(reads) == 3, f"expected two visibility misses and one success: {reads}")


@test
def session_started_does_not_retry_an_unrelated_cli_failure():
    cfg = default_config()
    cfg["fail"] = [["session", TARGET]]
    set_config(cfg)

    proc = run_progress("session-started", TARGET)

    refused(proc)
    reads = [call for call in cli_calls() if call == ["session", TARGET]]
    check(len(reads) == 1, f"an unrelated CLI failure was retried: {reads}")


@test
def session_started_exhaustion_keeps_the_created_identity_and_journals_nothing():
    cfg = default_config()
    cfg["session_visibility_delays"] = {TARGET: 100}
    set_config(cfg)

    proc = run_progress("session-started", TARGET)

    refused(proc)
    reads = [call for call in cli_calls() if call == ["session", TARGET]]
    check(len(reads) == 21, f"the bounded visibility retry used the wrong limit: {len(reads)}")
    check(TARGET in proc.stdout and "Create no replacement" in proc.stdout,
          "the exhausted boundary did not preserve the authoritative created id")


@test
def session_started_unknown_target_fails_loudly():
    refused(run_progress("session-started", "no-such-session"))


@test
def construction_session_started_requires_the_exact_attempt_identity():
    cfg = default_config()
    cfg["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1, "job": "implementer", "mode": "construction",
        "feature": "demo-feature", "lot": "lot-1", "task": 3,
        "attempt": 1, "status": "working",
    }
    set_config(cfg)

    refused(run_progress("session-started", TARGET))

    seed_active_attempt(attempt=1)
    started = run_progress("session-started", TARGET)
    check(started.returncode == 0, started.stdout + started.stderr)
    line = journal_lines()[-1]
    check(line["event"] == "session-started" and line["session"] == TARGET, line)
    check(line["data"]["schema"] == 1, line)
    check(line["data"]["attempt_identity"]["attempt"] == 1, line)
    base = subprocess.check_output([
        "git", "-C", REPO, "rev-parse", "refs/bwr/test-run/lot-1/attempt-base",
    ], text=True).strip()
    check(line["data"]["attempt_base"] == base, line)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)
    changed = journal_lines()
    changed[0]["data"]["attempt_base_tree"] = "0" * 40
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in changed:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    refused_after(
        run_progress("construction-verdict-check", "history"),
        len(changed), "a changed historical implementer start",
    )


@test
def construction_orphan_launch_requires_retirement_and_one_exact_abandonment():
    seed_active_attempt()
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))
    cfg = default_config()
    cfg["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1, "job": "implementer", "mode": "construction",
        "feature": "demo-feature", "lot": "lot-1", "task": 3,
        "attempt": 2, "status": "working",
    }
    set_config(cfg)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        target.write(json.dumps({
            "ts": "t", "by": CALLER, "event": "session-started", "session": TARGET,
            "mode": "construction", "lot": "lot-1", "task": 3, "attempt": 2,
            "job": "implementer",
        }, separators=(",", ":")) + "\n")

    before = len(journal_lines())
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "3"),
        before, "a replacement before the orphan owner is retired",
    )
    retired = run_progress("session-retired", TARGET, "failed", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    before = len(journal_lines())
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "3"),
        before, "a replacement before the orphan launch is durably abandoned",
    )

    cfg["sessions"][TARGET]["annotations"]["bwr"]["status"] = "failed"
    set_config(cfg)
    refused_after(
        run_progress(
            "note", "attempt.launch.abandoned",
            "--data", '{"reason":"missing-attempt-identity"}',
        ),
        len(journal_lines()), "a generic orphan-launch terminal",
    )
    abandoned = run_progress("construction-launch-abandoned", TARGET)
    check(abandoned.returncode == 0, abandoned.stdout + abandoned.stderr)
    terminal = journal_lines()[-1]
    check(terminal.get("kind") == "attempt.launch.abandoned", terminal)
    check(terminal["data"]["session"] == TARGET
          and terminal["data"]["attempt"] == 2
          and terminal["data"]["started"] is not None
          and terminal["data"]["retired"] is not None, terminal)
    admitted = run_progress("construction-launch-check", "lot-1", "3", "3")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "2"),
        len(journal_lines()), "reuse of the abandoned attempt number",
    )
    refused_after(
        run_progress("construction-launch-abandoned", TARGET),
        len(journal_lines()), "a duplicate orphan-launch terminal",
    )

    durable = journal_lines()
    retired_index = next(
        index for index, entry in enumerate(durable)
        if entry.get("event") == "session-retired" and entry.get("session") == TARGET
    )
    durable[retired_index]["status"] = "cancelled"
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in durable:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "3"),
        len(durable), "a changed historical orphan retirement",
    )


@test
def construction_unrecorded_orphan_launch_can_only_end_as_abandoned():
    seed_active_attempt()
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))
    cfg = default_config()
    cfg["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1, "job": "implementer", "mode": "construction",
        "feature": "demo-feature", "lot": "lot-1", "task": 3,
        "attempt": 2, "status": "working",
    }
    set_config(cfg)
    retired = run_progress("session-retired", TARGET, "failed", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    cfg["sessions"][TARGET]["annotations"]["bwr"]["status"] = "failed"
    set_config(cfg)

    abandoned = run_progress("construction-launch-abandoned", TARGET)
    check(abandoned.returncode == 0, abandoned.stdout + abandoned.stderr)
    terminal = journal_lines()[-1]
    check(terminal["data"]["started"] is None, terminal)
    admitted = run_progress("construction-launch-check", "lot-1", "3", "3")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)


@test
def construction_orphan_launch_refuses_any_owned_attempt_work():
    seed_active_attempt()
    cfg = default_config()
    cfg["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1, "job": "implementer", "mode": "construction",
        "feature": "demo-feature", "lot": "lot-1", "task": 3,
        "attempt": 2, "status": "working",
    }
    set_config(cfg)
    retired = run_progress("session-retired", TARGET, "failed", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    cfg["sessions"][TARGET]["annotations"]["bwr"]["status"] = "failed"
    set_config(cfg)
    before = len(journal_lines())

    refused_after(
        run_progress("construction-launch-abandoned", TARGET),
        before, "an orphan abandonment while the attempt marker exists",
    )
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))

    candidate = write_project("orphan-candidate.txt", "unowned candidate\n")
    refused_after(
        run_progress("construction-launch-abandoned", TARGET),
        before, "an orphan abandonment with a dirty candidate",
    )
    os.remove(candidate)

    report_relative = "reports/construction/lot-1-task-3-try-2.md"
    write_report(report_relative, "attempt work\n")
    report = os.path.join(WORKSPACE, *report_relative.split("/"))
    refused_after(
        run_progress("construction-launch-abandoned", TARGET),
        before, "an orphan abandonment with an attempt report",
    )
    os.remove(report)

    append_subagent(
        "subagent-started", "design-checker",
        mode="construction", lot="lot-1", task=3, attempt=2, round=1,
    )
    refused_after(
        run_progress("construction-launch-abandoned", TARGET),
        before + 1, "an orphan abandonment after a checker opening",
    )


def seed_two_physical_orphan_owners():
    other = "other-session-00000000-0000-0000-0000-000000000003"
    seed_active_attempt()
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))
    owner = {
        "schema": 1, "job": "implementer", "mode": "construction",
        "feature": "demo-feature", "lot": "lot-1", "task": 3,
        "attempt": 2, "status": "working",
    }
    cfg = default_config()
    cfg["sessions"][TARGET]["annotations"]["bwr"] = dict(owner)
    cfg["sessions"][other] = {"id": other, "annotations": {"bwr": dict(owner)}}
    set_config(cfg)
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        target.write(json.dumps({
            "ts": "t", "by": CALLER, "event": "session-started", "session": TARGET,
            "mode": "construction", "lot": "lot-1", "task": 3, "attempt": 2,
            "job": "implementer",
        }, separators=(",", ":")) + "\n")
    for session in (TARGET, other):
        retired = run_progress("session-retired", session, "failed", "--archive", "--hide")
        check(retired.returncode == 0, retired.stdout + retired.stderr)
        cfg["sessions"][session]["annotations"]["bwr"]["status"] = "failed"
    set_config(cfg)
    return other


@test
def construction_orphan_launch_closes_each_physical_owner_a_then_b():
    other = seed_two_physical_orphan_owners()
    first = run_progress("construction-launch-abandoned", TARGET)
    check(first.returncode == 0, first.stdout + first.stderr)
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "3"),
        len(journal_lines()), "reuse of A's terminal for physical owner B",
    )
    second = run_progress("construction-launch-abandoned", other)
    check(second.returncode == 0, second.stdout + second.stderr)
    admitted = run_progress("construction-launch-check", "lot-1", "3", "3")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)

    changed = journal_lines()
    first_terminal = next(
        entry for entry in changed
        if entry.get("kind") == "attempt.launch.abandoned"
        and entry.get("data", {}).get("session") == TARGET
    )
    first_terminal["data"]["session"] = other
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in changed:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    refused_after(
        run_progress("construction-verdict-check", "history"),
        len(changed), "a changed physical-owner identity",
    )


@test
def construction_orphan_launch_closes_each_physical_owner_b_then_a():
    other = seed_two_physical_orphan_owners()
    first = run_progress("construction-launch-abandoned", other)
    check(first.returncode == 0, first.stdout + first.stderr)
    refused_after(
        run_progress("construction-launch-check", "lot-1", "3", "3"),
        len(journal_lines()), "reuse of B's terminal for physical owner A",
    )
    second = run_progress("construction-launch-abandoned", TARGET)
    check(second.returncode == 0, second.stdout + second.stderr)
    admitted = run_progress("construction-launch-check", "lot-1", "3", "3")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)


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
def subagent_watchdog_started_prints_a_reminder_without_changing_stdout():
    started = run_progress("subagent-started", "completeness")
    check(started.returncode == 0, started.stdout + started.stderr)
    check(started.stdout == "", "a generic subagent opening gained stdout")
    check("SUBAGENT OPEN" in started.stderr, started.stderr)
    check("provider-native" in started.stderr, started.stderr)
    check("Never use TwiCC process wait" in started.stderr, started.stderr)


@test
def subagent_watchdog_lists_only_exact_open_brackets():
    started = run_progress("subagent-started", "completeness", "--round", "4")
    check(started.returncode == 0, started.stdout + started.stderr)

    listed = run_progress("subagents-open")
    check(listed.returncode == 0, listed.stdout + listed.stderr)
    rows = json.loads(listed.stdout)
    check(len(rows) == 1, rows)
    row = rows[0]
    check(row["kind"] == "completeness" and row["owner"] == CALLER, row)
    check(row["context"]["round"] == 4 and row["context"]["lot"] == "lot-1", row)
    check(row["started"] == journal_lines()[0]["ts"], row)
    check(isinstance(row["opening"], str) and re.fullmatch(r"0:[0-9a-f]{64}", row["opening"]), row)

    ended = run_progress(
        "subagent-ended", "completeness", "--round", "4",
        "--data", '{"decisions":"1/1"}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    listed = run_progress("subagents-open")
    check(listed.returncode == 0 and json.loads(listed.stdout) == [],
          listed.stdout + listed.stderr)


@test
def subagent_watchdog_accepts_a_late_exact_terminal():
    started = run_progress("subagent-started", "completeness", "--round", "2")
    check(started.returncode == 0, started.stdout + started.stderr)
    path = os.path.join(WORKSPACE, "progress.jsonl")
    lines = journal_lines()
    lines[0]["ts"] = "2020-01-01T00:00:00Z"
    with open(path, "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, separators=(",", ":")) + "\n")

    ended = run_progress(
        "subagent-ended", "completeness", "--round", "2",
        "--data", '{"decisions":"1/1"}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    listed = run_progress("subagents-open")
    check(listed.returncode == 0 and json.loads(listed.stdout) == [],
          listed.stdout + listed.stderr)


@test
def subagent_recovery_discovery_closes_lost_before_regeneration():
    started = run_progress(
        "subagent-started", "gate-runner", "--data", '{"scope":"discovery"}'
    )
    check(started.returncode == 0, started.stdout + started.stderr)
    lost = run_progress(
        "subagent-ended", "gate-runner",
        "--data", '{"scope":"discovery","unusable":"lost"}',
    )
    check(lost.returncode == 0, lost.stdout + lost.stderr)
    check(json.loads(run_progress("subagents-open").stdout) == [],
          "the lost discovery bracket remained open")
    replacement = run_progress(
        "subagent-started", "gate-runner", "--data", '{"scope":"discovery"}'
    )
    check(replacement.returncode == 0, replacement.stdout + replacement.stderr)
    ended = run_progress(
        "subagent-ended", "gate-runner",
        "--data", '{"scope":"discovery","green":true,"surface":"different"}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    check(json.loads(run_progress("subagents-open").stdout) == [],
          "the replacement discovery bracket remained open")


@test
def subagent_recovery_completeness_requires_one_closed_physical_call():
    started = run_progress("subagent-started", "completeness")
    check(started.returncode == 0, started.stdout + started.stderr)
    duplicate = run_progress("subagent-started", "completeness")
    check(duplicate.returncode != 0, "a duplicate completeness bracket opened")
    lost = run_progress(
        "subagent-ended", "completeness", "--data", '{"unusable":"lost"}'
    )
    check(lost.returncode == 0, lost.stdout + lost.stderr)
    replacement = run_progress("subagent-started", "completeness")
    check(replacement.returncode == 0, replacement.stdout + replacement.stderr)
    ended = run_progress(
        "subagent-ended", "completeness",
        "--data", '{"decisions":"1/1","tasks":"1/1","deps":"1/1","constraints":"ok","parent":"n/a"}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    check(json.loads(run_progress("subagents-open").stdout) == [],
          "the completed completeness bracket remained open")


@test
def subagent_unknown_kind_is_refused():
    refused(run_progress("subagent-started", "gate-checker"))
    refused(run_progress("subagent-ended", "verifier"))


@test
def subagent_ended_carries_data():
    started = run_progress("subagent-started", "completeness")
    check(started.returncode == 0, started.stdout + started.stderr)
    ended = run_progress("subagent-ended", "completeness",
                         "--data", '{"decisions":"12/12","tasks":"7/8"}')
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    lines = journal_lines()
    check(len(lines) == 2, f"one physical bracket must contain one opening and one terminal: {lines}")
    line = lines[-1]
    check(line["event"] == "subagent-ended", line)
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
def amendment_superseded_design_finding_closes_without_a_false_checker_terminal():
    seed_committed_construction_attempt_with_spec()
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1,
        "where": "Design Step 1",
        "what": "The product behavior needed by this Design is not specified.",
        "why": "Only a product decision can define the required task outcome.",
        "impact": "IMPORTANT",
        "previous": [],
    }])

    open_clean_construction_amendment_for_attempt()

    plan_path = os.path.join(WORKSPACE, "plans", "lot-1-plan.md")
    plan_text = open(plan_path, encoding="utf-8").read()
    refused_after(
        run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b"),
        len(journal_lines()), "an AMENDMENT that did not replace the task contract",
    )
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(plan_text.replace(
            "Implement the accepted task contract.",
            "The controller must not rewrite this implementer-owned Design.",
        ))
    refused_after(
        run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b"),
        len(journal_lines()), "an AMENDMENT route that changed the Design",
    )
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(plan_text.replace(
            "Achieves: Complete task 3.",
            "Achieves: Complete task 3 under the accepted R1 product behavior.",
        ))

    admitted = run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    account = json.loads(admitted.stdout)
    supersession = account.get("amendment_supersession")
    check(
        isinstance(supersession, dict)
        and supersession.get("amendment") == 1
        and supersession.get("checker") == "design"
        and supersession.get("finding_ids") == [1],
        f"the failure admission omitted its exact amendment supersession: {account}",
    )

    closer = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", json.dumps(account),
    )
    check(closer.returncode == 0, closer.stdout + closer.stderr)
    failure = next(entry for entry in journal_lines() if entry.get("kind") == "attempt.failed")
    check(failure["data"] == account, "the closer changed its admitted supersession account")
    check(not any(entry.get("kind") in {"design.review.blocked", "design.review.resolved"}
                  for entry in journal_lines()),
          "the amendment route fabricated a Design checker terminal")
    unpublished_start = run_progress(
        "construction-plan-successor-check", "lot-1", "3",
    )
    check(unpublished_start.returncode != 0,
          "replacement attempt admission accepted no durable plan publication")

    accepted_plan_text = open(plan_path, encoding="utf-8").read()
    head_before_publication = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(plan_text.replace(
            "Achieves: Complete task 3.",
            "Achieves: A foreign post-failure plan replaces the accepted correction.",
        ))
    plan_commit = os.path.join(WORKSPACE, "prompts", "construction", "plan-commit.sh")
    changed_publication = subprocess.run(
        [plan_commit, "lot-1", "Publish the wrong amendment replacement"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(changed_publication.returncode != 0, changed_publication.stdout + changed_publication.stderr)
    check(subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip() == head_before_publication,
          "a changed post-failure plan committed before replacement authentication")

    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(accepted_plan_text)
    published = subprocess.run(
        [plan_commit, "lot-1", "Publish the exact amendment replacement"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(published.returncode == 0, published.stdout + published.stderr)
    publication = journal_lines()[-1]
    check(publication.get("kind") == "plan.written"
          and publication.get("data", {}).get("schema") == 2
          and publication["data"]["amendment_supersession"]["failure"]
          == load_common_module("progress").journal_line_proof(
              journal_lines().index(failure)
          ), publication)
    load_common_module("progress").validate_plan_written_entry(
        journal_lines(), len(journal_lines()) - 1, publication,
    )

    marker = os.path.join(WORKSPACE, "plan-commit-in-progress")
    marker_tree = subprocess.check_output(
        ["git", "-C", REPO, "write-tree"], text=True,
    ).strip()
    with open(marker, "w", encoding="utf-8") as target:
        target.write(f"lot-1\n{marker_tree}\n{publication['data']['op']}\n")
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(accepted_plan_text.replace(
            "Complete task 3 under the accepted R1 product behavior.",
            "Replace the accepted correction after its orphan marker.",
        ))
    orphan_bypass = subprocess.run(
        [plan_commit, "lot-1", "Do not bypass C2 after orphan cleanup"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(orphan_bypass.returncode != 0,
          "an orphan marker bypassed the required C2 successor proof")
    check(not os.path.exists(marker), "the exact completed operation marker was not retired")
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(accepted_plan_text)

    c2_started = run_progress("subagent-started", "completeness")
    check(c2_started.returncode == 0, c2_started.stdout + c2_started.stderr)
    c2_ended = run_progress(
        "subagent-ended", "completeness",
        "--data", json.dumps({
            "decisions": "1/1", "tasks": "2/3", "deps": "2/2",
            "constraints": "ok", "parent": "n/a",
        }),
    )
    check(c2_ended.returncode == 0, c2_ended.stdout + c2_ended.stderr)
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(accepted_plan_text.replace(
            "Complete task 3 under the accepted R1 product behavior.",
            "Complete task 3 under R1 with the exact C2 ownership correction.",
        ))
    c2_publication = subprocess.run(
        [plan_commit, "lot-1", "Publish the authenticated C2 plan successor"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(c2_publication.returncode == 0, c2_publication.stdout + c2_publication.stderr)
    publication = journal_lines()[-1]
    check(publication["data"]["amendment_supersession"]["previous_publication"] is not None
          and publication["data"]["amendment_supersession"]["c2"] is not None,
          publication)
    load_common_module("progress").validate_plan_written_entry(
        journal_lines(), len(journal_lines()) - 1, publication,
    )

    published_commit = publication["data"]["commit"]
    write_project(".superpowers/bwr/gate.md", "true\n")
    seed_baseline_gate(f"plan/lot-1/{published_commit}", published_commit,
                       head_before_publication)
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))
    for number in range(3):
        subprocess.run([
            "git", "-C", REPO, "update-ref",
            f"refs/bwr/test-run/lot-1/task-{number}", published_commit,
        ], check=True)
    replacement_start = subprocess.run(
        [os.path.join(WORKSPACE, "prompts", "construction", "attempt-started.sh"),
         "lot-1", "3", "3"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(replacement_start.returncode == 0,
          replacement_start.stdout + replacement_start.stderr)
    os.remove(os.path.join(WORKSPACE, "attempt-in-flight"))

    durable = journal_lines()
    publication_index = max(
        index for index, entry in enumerate(durable)
        if entry.get("kind") == "plan.written"
        and entry.get("data", {}).get("schema") == 2
    )
    changed_publication = json.loads(json.dumps(durable))
    changed_publication[publication_index]["data"]["amendment_supersession"][
        "task_state_sha256"
    ] = "0" * 64
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in changed_publication:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed_history = run_progress("construction-verdict-check", "history")
    check(changed_history.returncode != 0,
          "historical validation accepted a changed plan publication proof")

    changed_c2 = json.loads(json.dumps(durable))
    c2_index = max(
        index for index, entry in enumerate(changed_c2)
        if entry.get("event") == "subagent-ended"
        and entry.get("kind") == "completeness"
    )
    changed_c2[c2_index]["data"]["tasks"] = "3/3"
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in changed_c2:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed_history = run_progress("construction-verdict-check", "history")
    check(changed_history.returncode != 0,
          "historical validation accepted a clean C2 result as successor authority")

    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in durable:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")

    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(plan_text.replace(
            "Achieves: Complete task 3.",
            "Achieves: A later plan generation changes this contract again.",
        ))
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)

    lines = journal_lines()
    durable_failure = next(entry for entry in lines if entry.get("kind") == "attempt.failed")
    durable_failure["data"]["amendment_supersession"]["replacement_task"][
        "contract_sha256"
    ] = "0" * 64
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in lines:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed = run_progress("construction-verdict-check", "history")
    check(changed.returncode != 0,
          "historical validation accepted a changed replacement task contract")


@test
def amendment_superseded_code_finding_uses_the_same_exact_account():
    seed_committed_construction_attempt_with_spec()
    append_checker_verdict(
        "code", lot="lot-1", task=3, attempt=2, round_number=1, findings=1,
        text="The implementation needs a product decision before it can be corrected.",
    )
    open_clean_construction_amendment_for_attempt(ruling="R2")
    plan_path = os.path.join(WORKSPACE, "plans", "lot-1-plan.md")
    plan_text = open(plan_path, encoding="utf-8").read()
    with open(plan_path, "w", encoding="utf-8") as target:
        target.write(plan_text.replace(
            "Achieves: Complete task 3.",
            "Achieves: Complete task 3 under the accepted R2 product behavior.",
        ))

    admitted = run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b")
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    account = json.loads(admitted.stdout)
    supersession = account.get("amendment_supersession")
    check(
        supersession.get("checker") == "code"
        and supersession.get("finding_ids") == [1]
        and "code_review" not in account,
        f"the code finding did not use the exact AMENDMENT supersession account: {account}",
    )
    appended = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", json.dumps(account),
    )
    check(appended.returncode == 0, appended.stdout + appended.stderr)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)


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


@test
def design_parity_final_contract_blocker_reaches_plan_fault_retry_without_settlement():
    seed_active_attempt()
    drive_design_to_round_ten_contract_blocker()

    before = len(journal_lines())
    refused_after(
        run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b"),
        before, "an unrecorded final contract blocker",
    )
    block_final_design_contract()
    refused_after(
        run_progress(
            "note", "design.review.blocked", "--round", "10",
            "--data", '{"check":"design"}',
        ),
        len(journal_lines()), "a duplicate final contract-blocker terminal",
    )
    settlement_path = os.path.join(BASE, "blocked-design-settlement.md")
    with open(settlement_path, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — accepted\nA settlement must not replace the blocker.\n\n"
            "## Finding 2 — accepted\nThe complete batch remains blocked.\n"
        )
    refused_after(
        run_progress(
            "note", "design.review.resolved", "--round", "10",
            "--text-file", settlement_path,
            "--data",
            '{"check":"design","items":[{"id":1,"status":"accepted"},'
            '{"id":2,"status":"accepted"}]}',
        ),
        len(journal_lines()), "a Design settlement after its blocker terminal",
    )

    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "2", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    failure_data = json.loads(admitted.stdout)
    check("report" not in failure_data, failure_data)
    check(failure_data["design_review"]["contract_blocked"] == [1], failure_data)
    check(failure_data["design_review"]["required"] == [1, 2], failure_data)
    decomposition = run_progress(
        "construction-failure-check", "lot-1", "3", "2", "C3.9d",
    )
    check(decomposition.returncode == 0, decomposition.stdout + decomposition.stderr)

    for classification in ("C3.9a", "C3.9c"):
        refused_after(
            run_progress(
                "construction-failure-check", "lot-1", "3", "2", classification,
            ),
            len(journal_lines()),
            f"{classification} for a pre-implementation contract blocker",
        )
    failed = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", json.dumps(failure_data),
    )
    check(failed.returncode == 0, failed.stdout + failed.stderr)
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() != "-", retry.stdout + retry.stderr)
    proof = retry.stdout.strip()

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
    previous = manifest["previous"]
    check([item["id"] for item in previous["findings"]] == [1, 2], previous)
    check(
        [item["status"] for item in previous["resolution"]]
        == ["contract-blocked", "carried"],
        previous,
    )

    journal = journal_lines()
    blocked = next(entry for entry in journal if entry.get("kind") == "design.review.blocked")
    blocked["data"]["required"] = [1]
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0,
          "a changed final contract-blocker obligation passed historical validation")


@test
def design_parity_early_contract_blocker_stops_without_spending_later_rounds():
    seed_active_attempt()
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[
        {
            "id": 1, "where": "frozen task contract",
            "what": "The task contract requires the wrong product result.",
            "why": "The implementer cannot correct controller-owned bytes.",
            "impact": "IMPORTANT", "previous": [],
        },
        {
            "id": 2, "where": "Design step 2",
            "what": "The Design also carries one dependent defect.",
            "why": "The corrected contract must be checked against the complete batch.",
            "impact": "IMPORTANT", "previous": [],
        },
    ])
    block_design_contract(1)

    before = len(journal_lines())
    refused_after(
        run_progress("subagent-started", "design-checker", "--round", "2"),
        before, "a later Design round after an early controller-contract blocker",
    )
    refused_after(
        run_progress("construction-verdict-check", "design", "lot-1", "3", "2"),
        before, "an early controller-contract blocker as implementation authority",
    )
    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "2", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    data = json.loads(admitted.stdout)
    check(data["design_review"]["contract_blocked"] == [1], data)
    check(data["design_review"]["required"] == [1, 2], data)

    stop_active_attempt("pause")
    stopped = journal_lines()[-1]
    check(stopped["data"]["design_review"] == data["design_review"], stopped)
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() != "-", retry.stdout + retry.stderr)

    journal = journal_lines()
    blocked = next(entry for entry in journal if entry.get("kind") == "design.review.blocked")
    blocked["data"]["required"] = [1]
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0,
          "historical replay accepted a changed early contract-blocker obligation")


@test
def early_design_blocker_refuses_an_implementer_owned_finding():
    seed_active_attempt()
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1, "where": "Design step 1",
        "what": "The Design omits one implementation step.",
        "why": "The implementer can correct its own Design.",
        "impact": "IMPORTANT", "previous": [],
    }])
    before = len(journal_lines())
    refused_after(
        run_progress(
            "note", "design.review.blocked", "--round", "1",
            "--data", '{"check":"design"}',
        ),
        before, "an implementer-owned finding as a controller-contract blocker",
    )
    refused_after(
        run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9b"),
        before, "an unresolved implementer-owned Design finding as a plan-fault close",
    )
    replace_current_design("Add the missing implementation step.")
    resolve_design_round(1, [{"id": 1, "status": "corrected"}])
    next_opening = open_design_round(2)
    check(next_opening["manifest"], "the ordinary corrected Design could not continue")


@test
def early_design_contract_blocker_composes_with_an_inherited_design_obligation():
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    stop_active_attempt("pause")
    inherited = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(inherited != "-", "the accepted Design obligation has no retry proof")

    set_active_attempt_retry(inherited, 3)
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1, "where": "frozen task contract",
        "what": "The corrected Design exposes a controller-contract defect.",
        "why": "The controller must correct the task contract before another attempt.",
        "impact": "IMPORTANT", "previous": [],
    }], previous=[{
        "id": 2, "status": "addressed",
        "evidence": "This Design addresses the inherited accepted finding.",
    }])
    block_design_contract(1)
    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "3", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    failure_data = json.loads(admitted.stdout)
    check(failure_data.get("retry") == inherited, failure_data)
    failed = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", admitted.stdout.strip(),
    )
    check(failed.returncode == 0, failed.stdout + failed.stderr)
    composed = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(composed not in {"-", inherited}, "the early blocker replaced the inherited proof")

    set_active_attempt_retry(composed, 4)
    next_opening = open_design_round(1)
    manifest = json.load(open(
        os.path.join(WORKSPACE, next_opening["manifest"]), encoding="utf-8",
    ))
    previous = manifest["previous"]
    check(previous["source"] == "retry-set" and previous["failure"] == composed, previous)
    check(len(previous["members"]) == 2, previous)
    check([item["id"] for item in previous["findings"]] == [1, 2], previous)
    check(
        [item["status"] for item in previous["resolution"]]
        == ["accepted", "contract-blocked"],
        previous,
    )
    finish_design_round(1, next_opening, previous=[
        {
            "id": 1, "status": "addressed",
            "evidence": "The replacement Design preserves the inherited correction.",
        },
        {
            "id": 2, "status": "addressed",
            "evidence": "The replacement Design follows the corrected task contract.",
        },
    ])
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)


@test
def early_design_contract_blocker_survives_abort():
    seed_active_attempt()
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1, "where": "frozen task contract",
        "what": "The task contract requires the wrong product result.",
        "why": "The controller must correct the contract before another attempt.",
        "impact": "IMPORTANT", "previous": [],
    }])
    block_design_contract(1)
    stop_active_attempt("abort")
    stopped = journal_lines()[-1]
    check(stopped["kind"] == "aborted", stopped)
    check(stopped["data"]["design_review"]["contract_blocked"] == [1], stopped)
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() != "-", retry.stdout + retry.stderr)


@test
def design_parity_stop_preserves_a_final_contract_blocker():
    seed_active_attempt()
    drive_design_to_round_ten_contract_blocker()
    block_final_design_contract()
    stop_active_attempt("pause")
    stopped = journal_lines()[-1]
    check(stopped["kind"] == "paused", stopped)
    review = stopped["data"]["design_review"]
    check(review["contract_blocked"] == [1] and review["required"] == [1, 2], review)
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() != "-", retry.stdout + retry.stderr)


def record_code_contract_blocker(round_number=1, findings=2):
    account = os.path.join(BASE, "code-contract-blocker.md")
    with open(account, "w", encoding="utf-8") as target:
        parts = [
            "## Finding 1 — contract-blocked\n"
            "The required file is outside the frozen task contract."
        ]
        parts.extend(
            f"## Finding {identity} — carried\n"
            "The replacement attempt must preserve this finding."
            for identity in range(2, findings + 1)
        )
        target.write("\n\n".join(parts) + "\n")
    blocked = run_progress(
        "note", "code.review.blocked", "--round", str(round_number),
        "--text-file", account,
        "--data", json.dumps({
            "check": "code",
            "items": [
                {"id": 1, "status": "contract-blocked"},
                *[
                    {"id": identity, "status": "carried"}
                    for identity in range(2, findings + 1)
                ],
            ],
        }),
    )
    check(blocked.returncode == 0, blocked.stdout + blocked.stderr)


def set_active_attempt_retry(proof, attempt):
    seed_active_attempt(attempt=attempt)
    marker = os.path.join(WORKSPACE, "attempt-in-flight")
    lines = open(marker, encoding="utf-8").read().splitlines()
    lines[1] = re.sub(r" retry .+$", f" retry {proof}", lines[1])
    with open(marker, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")
    cfg = default_config()
    cfg["whoami"]["session"]["annotations"]["bwr"]["attempt"] = attempt
    cfg["sessions"][CALLER]["annotations"]["bwr"]["attempt"] = attempt
    set_config(cfg)


def assert_code_contract_blocker_stop_preserves_retry(mode):
    seed_active_attempt()
    append_checker_verdict(
        "code", lot="lot-1", task=3, attempt=2, round_number=1, findings=2,
    )
    record_code_contract_blocker()
    stop_active_attempt(mode)
    stopped = journal_lines()[-1]
    review = stopped["data"]["code_review"]
    check(review["contract_blocked"] == [1] and review["required"] == [1, 2], review)
    retry = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(retry.returncode == 0 and retry.stdout.strip() != "-", retry.stdout + retry.stderr)


@test
def code_contract_blocker_pause_preserves_the_exact_retry_batch():
    assert_code_contract_blocker_stop_preserves_retry("pause")


@test
def code_contract_blocker_abort_preserves_the_exact_retry_batch():
    assert_code_contract_blocker_stop_preserves_retry("abort")


@test
def code_contract_blocker_composes_with_an_inherited_design_obligation():
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    stop_active_attempt("pause")
    inherited = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(inherited != "-", "the accepted Design obligation has no retry proof")

    set_active_attempt_retry(inherited, 3)
    opening = open_design_round(1)
    finish_design_round(1, opening, previous=[{
        "id": 2, "status": "addressed",
        "evidence": "The retry Design addresses the inherited accepted defect.",
    }])
    code_opening = append_real_code_verdict(attempt=3, findings=1)
    code_manifest = json.load(open(
        os.path.join(WORKSPACE, code_opening["manifest"]), encoding="utf-8",
    ))
    check(code_manifest["previous"] is None,
          "a Design-only obligation was misrouted into the code checker")
    record_code_contract_blocker(findings=1)

    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "3", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    data = json.loads(admitted.stdout)
    check(data.get("retry") == inherited, data)
    check(data["code_review"]["contract_blocked"] == [1], data)


@test
def early_design_contract_blocker_composes_with_an_inherited_code_obligation():
    seed_active_attempt()
    for round_number in range(1, 11):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1,
        )
    resolution = os.path.join(BASE, "accepted-code-before-design-blocker.md")
    with open(resolution, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — accepted\n"
            "The retry must preserve this accepted code obligation.\n"
        )
    resolved = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", resolution,
        "--data", '{"check":"code","items":[{"id":1,"status":"accepted"}]}',
    )
    check(resolved.returncode == 0, resolved.stdout + resolved.stderr)
    handoff = run_progress("construction-failure-handoff", "lot-1", "3", "2")
    check(handoff.returncode == 0, handoff.stdout + handoff.stderr)
    report_relative = "reports/construction/lot-1-task-3-try-2.md"
    report = os.path.join(WORKSPACE, report_relative)
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as target:
        target.write(
            "## What failed\nThe final code checker accepted one defect.\n\n"
            "## Classification\nC3.9a — retry the implementation.\n\n"
            "## Evidence read\nThe immutable code-checker result.\n\n"
            + handoff.stdout
        )
    failure = run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9a")
    check(failure.returncode == 0, failure.stdout + failure.stderr)
    appended = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", failure.stdout.strip(),
    )
    check(appended.returncode == 0, appended.stdout + appended.stderr)
    inherited = run_progress(
        "construction-retry-check", "lot-1", "3", report_relative,
    ).stdout.strip()
    check(inherited != "-", "the accepted code obligation has no retry proof")

    set_active_attempt_retry(inherited, 3)
    opening = open_design_round(1)
    finish_design_round(1, opening, findings=[{
        "id": 1, "where": "frozen task contract",
        "what": "The retry Design exposes a controller-contract defect.",
        "why": "The controller must correct the contract before another attempt.",
        "impact": "IMPORTANT", "previous": [],
    }])
    block_design_contract(1)
    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "3", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    failure_data = json.loads(admitted.stdout)
    check(failure_data.get("retry") == inherited, failure_data)
    failed = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", admitted.stdout.strip(),
    )
    check(failed.returncode == 0, failed.stdout + failed.stderr)
    composed = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(composed not in {"-", inherited}, "the early blocker replaced the code proof")

    set_active_attempt_retry(composed, 4)
    design_opening = open_design_round(1)
    design_manifest = json.load(open(
        os.path.join(WORKSPACE, design_opening["manifest"]), encoding="utf-8",
    ))
    check([item["id"] for item in design_manifest["previous"]["findings"]] == [1],
          design_manifest["previous"])
    finish_design_round(1, design_opening, previous=[{
        "id": 1, "status": "addressed",
        "evidence": "The replacement Design follows the corrected task contract.",
    }])
    code_opening = append_real_code_verdict(attempt=4, findings=0)
    code_manifest = json.load(open(
        os.path.join(WORKSPACE, code_opening["manifest"]), encoding="utf-8",
    ))
    check([item["id"] for item in code_manifest["previous"]["findings"]] == [1],
          code_manifest["previous"])
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)


@test
def code_contract_blocker_composes_two_code_obligations_for_one_manifest():
    seed_active_attempt()
    for round_number in range(1, 11):
        append_checker_verdict(
            "code", lot="lot-1", task=3, attempt=2,
            round_number=round_number, findings=1,
        )
    resolution = os.path.join(BASE, "accepted-code-retry.md")
    with open(resolution, "w", encoding="utf-8") as target:
        target.write(
            "## Finding 1 — accepted\n"
            "The implementation must preserve this accepted code obligation.\n"
        )
    resolved = run_progress(
        "note", "code.review.resolved", "--round", "10",
        "--text-file", resolution,
        "--data", '{"check":"code","items":[{"id":1,"status":"accepted"}]}',
    )
    check(resolved.returncode == 0, resolved.stdout + resolved.stderr)
    handoff = run_progress("construction-failure-handoff", "lot-1", "3", "2")
    check(handoff.returncode == 0, handoff.stdout + handoff.stderr)
    report = os.path.join(WORKSPACE, "reports", "construction", "lot-1-task-3-try-2.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as target:
        target.write(
            "# Failed attempt\n\n"
            "## What failed\nThe final code checker found one accepted defect.\n\n"
            "## Classification\nC3.9a — retry the accepted implementation obligation.\n\n"
            "## Evidence read\nThe immutable final code-checker batch.\n\n"
            + handoff.stdout
        )
    failure = run_progress("construction-failure-check", "lot-1", "3", "2", "C3.9a")
    check(failure.returncode == 0, failure.stdout + failure.stderr)
    appended = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", failure.stdout.strip(),
    )
    check(appended.returncode == 0, appended.stdout + appended.stderr)
    retry = run_progress(
        "construction-retry-check", "lot-1", "3",
        "reports/construction/lot-1-task-3-try-2.md",
    )
    check(retry.returncode == 0, retry.stdout + retry.stderr)
    inherited = retry.stdout.strip()
    check(re.fullmatch(r"[0-9]+:[0-9a-f]{64}", inherited),
          "the accepted code obligation has no retry proof")

    set_active_attempt_retry(inherited, 3)
    append_real_code_verdict(attempt=3, findings=1)
    record_code_contract_blocker(findings=1)
    admitted = run_progress(
        "construction-failure-check", "lot-1", "3", "3", "C3.9b",
    )
    check(admitted.returncode == 0, admitted.stdout + admitted.stderr)
    data = json.loads(admitted.stdout)
    check(data.get("retry") == inherited, data)
    appended = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", admitted.stdout.strip(),
    )
    check(appended.returncode == 0, appended.stdout + appended.stderr)
    composed = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(composed not in {"-", inherited}, "the two obligations have no composed proof")

    set_active_attempt_retry(composed, 4)
    append_real_code_verdict(attempt=4, findings=0)
    opening = next(
        entry for entry in reversed(journal_lines())
        if entry.get("event") == "subagent-started"
        and entry.get("kind") == "code-checker" and entry.get("attempt") == 4
    )
    manifest = json.load(open(
        os.path.join(WORKSPACE, opening["data"]["manifest"]), encoding="utf-8",
    ))
    previous = manifest["previous"]
    check(previous["source"] == "retry-set" and previous["failure"] == composed, previous)
    check(len(previous["members"]) == 2, previous)
    check([item["id"] for item in previous["findings"]] == [1, 2], previous)
    failed_again = run_progress(
        "construction-failure-check", "lot-1", "3", "4", "C3.9a",
    )
    check(failed_again.returncode == 0, failed_again.stdout + failed_again.stderr)
    check(json.loads(failed_again.stdout) == {
        "attempt": 4, "classification": "C3.9a", "retry": composed,
    }, failed_again.stdout)
    appended = run_progress(
        "note", "attempt.failed", "--task", "3", "--data", failed_again.stdout.strip(),
    )
    check(appended.returncode == 0, appended.stdout + appended.stderr)
    propagated = run_progress("construction-retry-check", "lot-1", "3", "-")
    check(propagated.returncode == 0 and propagated.stdout.strip() == composed,
          propagated.stdout + propagated.stderr)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)

    journal_path = os.path.join(WORKSPACE, "progress.jsonl")
    original_lines = open(journal_path, encoding="utf-8").read().splitlines()
    terminal_index = int(composed.split(":", 1)[0])
    terminal = json.loads(original_lines[terminal_index])
    terminal["data"].pop("retry")
    changed_lines = list(original_lines)
    changed_lines[terminal_index] = json.dumps(terminal, separators=(",", ":"))
    with open(journal_path, "w", encoding="utf-8") as target:
        target.write("\n".join(changed_lines) + "\n")
    damaged = run_progress("construction-verdict-check", "history")
    check(damaged.returncode != 0, "historical replay accepted an omitted inherited proof")
    with open(journal_path, "w", encoding="utf-8") as target:
        target.write("\n".join(original_lines) + "\n")

    manifest_path = os.path.join(WORKSPACE, opening["data"]["manifest"])
    original_manifest = open(manifest_path, encoding="utf-8").read()
    damaged_manifest = json.loads(original_manifest)
    damaged_manifest["previous"]["members"].pop(0)
    damaged_manifest["previous"]["findings"] = damaged_manifest["previous"]["findings"][1:]
    damaged_manifest["previous"]["resolution"] = damaged_manifest["previous"]["resolution"][1:]
    with open(manifest_path, "w", encoding="utf-8") as target:
        json.dump(damaged_manifest, target, separators=(",", ":"))
        target.write("\n")
    damaged = run_progress("construction-verdict-check", "history")
    check(damaged.returncode != 0, "historical replay accepted an omitted retry-set member")
    with open(manifest_path, "w", encoding="utf-8") as target:
        target.write(original_manifest)


def assert_composed_code_contract_blocker_stop_reaches_both_checkers(mode):
    seed_active_attempt()
    drive_design_to_round_ten()
    resolve_design_round(10, [
        {"id": 1, "status": "alternative"},
        {"id": 2, "status": "accepted"},
    ])
    stop_active_attempt("pause")
    inherited = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(inherited != "-", "the accepted Design obligation has no retry proof")

    set_active_attempt_retry(inherited, 3)
    design_opening = open_design_round(1)
    finish_design_round(1, design_opening, previous=[{
        "id": 2, "status": "addressed",
        "evidence": "The retry Design addresses the inherited accepted defect.",
    }])
    append_real_code_verdict(attempt=3, findings=1)
    record_code_contract_blocker(findings=1)
    stop_active_attempt(mode, attempt=3)
    stopped = journal_lines()[-1]
    check(stopped["kind"] == {"pause": "paused", "abort": "aborted"}[mode]
          and stopped["data"]["retry"] == inherited, stopped)
    check(stopped["data"]["code_review"]["contract_blocked"] == [1], stopped)
    composed = run_progress("construction-retry-check", "lot-1", "3", "-").stdout.strip()
    check(composed not in {"-", inherited}, "the stopped attempt lost one obligation")

    set_active_attempt_retry(composed, 4)
    design_opening = open_design_round(1)
    design_manifest = json.load(open(
        os.path.join(WORKSPACE, design_opening["manifest"]), encoding="utf-8",
    ))
    check(design_manifest["previous"]["failure"] == composed, design_manifest["previous"])
    check([item["id"] for item in design_manifest["previous"]["findings"]] == [2],
          design_manifest["previous"])
    finish_design_round(1, design_opening, previous=[{
        "id": 2, "status": "addressed",
        "evidence": "The next retry Design still addresses the inherited defect.",
    }])
    code_opening = append_real_code_verdict(attempt=4, findings=0)
    code_manifest = json.load(open(
        os.path.join(WORKSPACE, code_opening["manifest"]), encoding="utf-8",
    ))
    check(code_manifest["previous"]["failure"] == composed, code_manifest["previous"])
    check([item["id"] for item in code_manifest["previous"]["findings"]] == [1],
          code_manifest["previous"])
    succeeded = run_progress(
        "note", "attempt.succeeded", "--task", "3",
        "--data", json.dumps({
            "attempt": 4, "lot": "lot-1", "sha": "a" * 40,
            "gate": "b" * 64, "retry": composed,
        }),
    )
    check(succeeded.returncode == 0, succeeded.stdout + succeeded.stderr)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)


@test
def inherited_design_and_code_obligations_survive_a_pause_until_success():
    assert_composed_code_contract_blocker_stop_reaches_both_checkers("pause")


@test
def inherited_design_and_code_obligations_survive_an_abort_until_success():
    assert_composed_code_contract_blocker_stop_reaches_both_checkers("abort")


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
    check("no final checker correction obligation authorizes this retry report" in progress_source,
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
        check("design.review.blocked" in contract,
              f"the {name} does not carry the exact controller-contract blocker")
        lowered_contract = contract.lower()
        check("at the round where it is found" in lowered_contract
              or "at its current round" in lowered_contract,
              f"the {name} defers a controller-owned Design blocker")
    check("Do not allocate another Design round" in implementer,
          "the implementer can continue after a controller-owned Design blocker")
    check("design.review.blocked --round <K>" in implementer,
          "the implementer lacks the exact current-round blocker command")
    check("design.review.blocked --round 10" not in implementer,
          "the implementer still limits a controller-owned blocker to round 10")
    check('"where":"frozen task contract"' in checker,
          "the Design checker lacks one exact controller-contract finding identity")
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
def construction_logical_spend_append_is_atomic():
    seed_active_attempt()
    opened = run_progress("subagent-started", "design-checker", "--round", "1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)

    command = [
        sys.executable, SCRIPT, "note", "bound.spent", "--round", "1",
        "--text", "design checker round 1 of 10",
    ]
    lock_path = os.path.join(WORKSPACE, "progress.jsonl.lock")
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        processes = [subprocess.Popen(command, env=ENV, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            waiting = []
            for process in processes:
                try:
                    with open(f"/proc/{process.pid}/wchan", encoding="utf-8") as source:
                        waiting.append("lock" in source.read())
                except OSError:
                    waiting.append(False)
            if waiting == [True, True]:
                break
            time.sleep(0.01)
        check(waiting == [True, True], "both logical spends did not reach the journal lock")
        fcntl.flock(lock, fcntl.LOCK_UN)

    results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
    check(sorted(result[2] for result in results) == [0, 1], results)
    check(any("already exists" in result[0] for result in results if result[2] != 0), results)
    spends = [entry for entry in journal_lines() if entry.get("kind") == "bound.spent"]
    check(len(spends) == 1, "concurrent logical-spend admission appended a duplicate")


@test
def construction_duplicate_logical_spend_recovers_the_open_physical_result():
    seed_active_attempt()
    opening = open_design_round(1)
    before = len(journal_lines())
    refused_after(
        run_progress(
            "construction-spend-recover", "lot-1", "3", "2", "design", "1",
        ),
        before, "logical-spend recovery without a duplicate",
    )
    entries = journal_lines()
    spend = next(entry for entry in entries if entry.get("kind") == "bound.spent")
    duplicate = json.loads(json.dumps(spend))
    duplicate["ts"] = "duplicate"
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps(duplicate, separators=(",", ":")) + "\n")

    before = len(journal_lines())
    blocked = run_progress(
        "subagent-ended", "design-checker", "--round", "1",
        "--data", json.dumps({"result": write_design_result(
            "duplicate-spend-result.json", design_result_payload(opening),
        )}),
    )
    refused_after(blocked, before, "a physical result before duplicate-spend recovery")

    recovered = run_progress(
        "construction-spend-recover", "lot-1", "3", "2", "design", "1",
    )
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    recovery = journal_lines()[-1]
    check(recovery.get("kind") == "construction.spend.recovered", recovery)
    check(len(recovery["data"]["spends"]) == 2, recovery)

    ended = run_progress(
        "subagent-ended", "design-checker", "--round", "1",
        "--data", json.dumps({"result": os.path.join(
            BASE, "duplicate-spend-result.json",
        )}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    verdict = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"design","outcome":"clean"}',
    )
    check(verdict.returncode == 0, verdict.stdout + verdict.stderr)
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode == 0, history.stdout + history.stderr)

    before = len(journal_lines())
    duplicate_recovery = run_progress(
        "construction-spend-recover", "lot-1", "3", "2", "design", "1",
    )
    refused_after(duplicate_recovery, before, "a duplicate spend recovery")

    journal = journal_lines()
    recovery = next(entry for entry in journal
                    if entry.get("kind") == "construction.spend.recovered")
    recovery["data"]["spends"][0] = recovery["data"]["spends"][1]
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    damaged = run_progress("construction-verdict-check", "history")
    check(damaged.returncode != 0, "changed duplicate-spend authority passed historical replay")


@test
def construction_duplicate_logical_spend_recovery_rejects_a_foreign_owner():
    seed_active_attempt()
    open_design_round(1)
    spend = next(entry for entry in journal_lines() if entry.get("kind") == "bound.spent")
    duplicate = json.loads(json.dumps(spend))
    duplicate["ts"] = "duplicate"
    duplicate["by"] = "foreign-physical-owner"
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
        target.write(json.dumps(duplicate, separators=(",", ":")) + "\n")
    before = len(journal_lines())
    refused_after(
        run_progress(
            "construction-spend-recover", "lot-1", "3", "2", "design", "1",
        ),
        before, "duplicate-spend recovery across physical owners",
    )
    journal = journal_lines()
    journal[-1]["by"] = spend["by"]
    journal[-1]["data"]["contract_sha256"] = "f" * 64
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    refused_after(
        run_progress(
            "construction-spend-recover", "lot-1", "3", "2", "design", "1",
        ),
        before, "duplicate-spend recovery across logical identities",
    )


@test
def construction_duplicate_logical_spend_recovery_rejects_a_late_duplicate():
    seed_active_attempt()
    open_design_round(1)
    spend = next(entry for entry in journal_lines() if entry.get("kind") == "bound.spent")
    duplicate = json.loads(json.dumps(spend))
    duplicate["ts"] = "duplicate-before-recovery"
    journal_path = os.path.join(WORKSPACE, "progress.jsonl")
    with open(journal_path, "a", encoding="utf-8") as target:
        target.write(json.dumps(duplicate, separators=(",", ":")) + "\n")
    recovered = run_progress(
        "construction-spend-recover", "lot-1", "3", "2", "design", "1",
    )
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    duplicate["ts"] = "duplicate-after-recovery"
    with open(journal_path, "a", encoding="utf-8") as target:
        target.write(json.dumps(duplicate, separators=(",", ":")) + "\n")
    history = run_progress("construction-verdict-check", "history")
    check(history.returncode != 0, "a post-recovery duplicate spend passed historical replay")


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

def seed_pending_legacy_pass_opening(*, stop_sessions=False):
    commit, gate, owner = seed_task_gate("lot-1", "pending-opening-context")
    stop_contexts = {}
    if stop_sessions:
        stop_contexts = {
            TARGET: {
                "mode": "product-review", "lot": "lot-1",
                "mandate": "unlooked", "job": "reviewer",
            },
            "watchdog-session": {"job": "watchdog"},
        }
        with open(os.path.join(WORKSPACE, "progress.jsonl"), "a", encoding="utf-8") as target:
            for session, context in stop_contexts.items():
                target.write(json.dumps({
                    "ts": "t", "by": CALLER, "event": "session-started",
                    "session": session, **context,
                }, separators=(",", ":")) + "\n")
    append_note(
        "pass.opened",
        {
            "built": "lot-1",
            "commit": commit,
            "gate": gate,
            "source_scope": "task",
            "source_owner": owner,
            "source_lot": "lot-1",
            "source_task": 1,
            "source_attempt": 1,
        },
        by=CALLER,
        mode="construction",
        lot="lot-1",
        job="controller",
    )
    config = default_config()
    for payload in (
        config["whoami"]["session"]["annotations"]["bwr"],
        config["sessions"][CALLER]["annotations"]["bwr"],
    ):
        payload.update(mode="product-review", lot="lot-1", job="controller")
        payload.pop("task", None)
        payload.pop("attempt", None)
    for session, context in stop_contexts.items():
        config["sessions"][session] = {
            "id": session,
            "annotations": {"bwr": {
                "schema": 1, "feature": "demo-feature", "status": "working",
                **context,
            }},
        }
    if not stop_sessions:
        config["sessions"][TARGET]["annotations"]["bwr"] = {
            "schema": 1,
            "job": "reviewer",
            "mode": "product-review",
            "feature": "demo-feature",
            "lot": "lot-1",
            "mandate": "unlooked",
            "status": "working",
        }
    set_config(config)
    return commit, gate


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
def pass_opening_context_requires_product_review_and_recovers_one_exact_legacy_opening():
    commit, gate, owner = seed_task_gate("lot-1", "opening-context")
    data = {"built": "lot-1", "commit": commit, "gate": gate}

    construction = default_config()
    set_config(construction)
    before = len(journal_lines())
    wrong_mode = run_progress("note", "pass.opened", "--data", json.dumps(data))
    check(wrong_mode.returncode != 0 and len(journal_lines()) == before,
          "a fresh PRODUCT REVIEW pass opened from Construction context")

    append_note(
        "pass.opened",
        {
            **data,
            "source_scope": "task",
            "source_owner": owner,
            "source_lot": "lot-1",
            "source_task": 1,
            "source_attempt": 1,
        },
        by=CALLER,
        mode="construction",
        lot="lot-1",
        job="controller",
    )
    legacy_index = len(journal_lines()) - 1
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "rb") as journal:
        legacy_raw = journal.read().splitlines()[legacy_index]
    legacy_proof = f"{legacy_index}:{hashlib.sha256(legacy_raw).hexdigest()}"

    premature = run_progress("pass-opening-context-recover")
    check(premature.returncode != 0 and len(journal_lines()) == legacy_index + 1,
          "Construction context recovered its own malformed pass opening")

    product_review = default_config()
    for payload in (
        product_review["whoami"]["session"]["annotations"]["bwr"],
        product_review["sessions"][CALLER]["annotations"]["bwr"],
    ):
        payload.update(mode="product-review", lot="lot-1", job="controller")
        payload.pop("task", None)
        payload.pop("attempt", None)
    product_review["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1,
        "job": "reviewer",
        "mode": "product-review",
        "feature": "demo-feature",
        "lot": "lot-1",
        "mandate": "unlooked",
        "status": "working",
    }
    set_config(product_review)

    blocked_reviewer = run_progress("session-started", TARGET)
    check(blocked_reviewer.returncode != 0 and len(journal_lines()) == legacy_index + 1,
          "a PRODUCT REVIEW reviewer started before the malformed opening was recovered")

    recovered = run_progress("pass-opening-context-recover")
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    recovery = journal_lines()[-1]
    check(
        recovery.get("kind") == "pass.opening.context.recovered"
        and recovery.get("mode") == "product-review"
        and recovery.get("lot") == "lot-1"
        and recovery.get("job") == "controller"
        and recovery.get("by") == CALLER
        and recovery.get("data") == {
            "schema": 1,
            "opening": legacy_proof,
            "owner": CALLER,
            "built": "lot-1",
            "commit": commit,
            "gate": gate,
            "from": {"mode": "construction", "lot": "lot-1", "job": "controller"},
            "to": {"mode": "product-review", "lot": "lot-1", "job": "controller"},
            "stop": None,
        },
        f"the pass-opening recovery has the wrong account: {recovery}",
    )

    progress = load_common_module("progress")
    entries = journal_lines()
    progress.validate_pass_opening_history(
        entries, legacy_index, "the recovered product-review pass",
    )

    reviewer = run_progress("session-started", TARGET)
    check(reviewer.returncode == 0, reviewer.stdout + reviewer.stderr)
    entries = journal_lines()

    duplicate = run_progress("pass-opening-context-recover")
    check(duplicate.returncode != 0 and len(journal_lines()) == len(entries),
          "the same malformed pass opening received two recoveries")

    entries[legacy_index + 1]["data"]["opening"] = "0:" + "f" * 64
    try:
        progress.current_pass_opening(
            entries, len(entries), "the changed recovered product-review pass",
        )
    except SystemExit:
        pass
    else:
        raise AssertionError("historical replay accepted a changed pass-opening recovery proof")


@test
def pass_opening_context_pending_owner_blocks_every_unrelated_mutation():
    commands = (
        ("generic note", ("note", "not-converging", "--text", "blocked"), False),
        ("subagent opening", ("subagent-started", "completeness"), False),
        ("session status", ("session-status", TARGET, "blocked"), True),
        ("session retirement", ("session-retired", TARGET, "failed", "--hide"), True),
    )
    for subject, command, external in commands:
        reset()
        seed_pending_legacy_pass_opening()
        before = len(journal_lines())
        before_mutations = list(mutations())
        refused_after(run_progress(*command), before, subject)
        if external:
            check(mutations() == before_mutations,
                  f"{subject} changed TwiCC before the pending-owner refusal")

    reset()
    seed_pending_legacy_pass_opening()
    lock_path = os.path.join(WORKSPACE, "progress.jsonl.lock")
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        generic = subprocess.Popen(
            [sys.executable, SCRIPT, "note", "not-converging", "--text", "blocked"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV,
        )
        recovery = subprocess.Popen(
            [sys.executable, SCRIPT, "pass-opening-context-recover"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV,
        )
        fcntl.flock(lock, fcntl.LOCK_UN)
    generic_stdout, generic_stderr = generic.communicate(timeout=120)
    recovery_stdout, recovery_stderr = recovery.communicate(timeout=120)
    check(recovery.returncode == 0, recovery_stdout + recovery_stderr)
    entries = journal_lines()
    recoveries = [
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "pass.opening.context.recovered"
    ]
    generic_notes = [
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "not-converging"
    ]
    check(len(recoveries) == 1, entries)
    check(not generic_notes or generic_notes == [recoveries[0] + 1], entries)
    if generic.returncode != 0:
        check(not generic_notes, generic_stdout + generic_stderr)

    reset()
    seed_pending_legacy_pass_opening()
    append_note("pass.closed", {"legacy": "already consumed"})
    old_closed = run_progress("note", "not-converging", "--text", "later history")
    check(old_closed.returncode == 0, old_closed.stdout + old_closed.stderr)


def run_pending_opening_bare_stop(mode):
    result = subprocess.run(
        [os.path.join(WORKSPACE, "prompts", "common", "stop.sh"), mode],
        capture_output=True, text=True, cwd=REPO, env=ENV, timeout=120,
    )
    check(result.returncode == 0, result.stdout + result.stderr)
    terminal = journal_lines()[-1]
    check(
        terminal.get("kind") == {"pause": "paused", "abort": "aborted"}[mode]
        and set(terminal.get("data", {})) == {"sha", "op"},
        terminal,
    )
    return terminal


def retire_pending_opening_stop_sessions():
    child = run_progress(
        "session-retired", TARGET, "cancelled", "--archive", "--hide",
    )
    check(child.returncode == 0, child.stdout + child.stderr)
    watchdog = run_progress(
        "session-retired", "watchdog-session", "done", "--archive", "--hide",
    )
    check(watchdog.returncode == 0, watchdog.stdout + watchdog.stderr)


@test
def pass_opening_context_preserves_the_complete_pause_and_abort_stop_tails():
    reset()
    seed_pending_legacy_pass_opening(stop_sessions=True)
    run_pending_opening_bare_stop("pause")
    retire_pending_opening_stop_sessions()
    reported = run_progress("note", "paused", "--text", "The Product Review run is paused.")
    check(reported.returncode == 0, reported.stdout + reported.stderr)
    resumed = run_progress("note", "resumed")
    check(resumed.returncode == 0, resumed.stdout + resumed.stderr)
    recovered = run_progress("pass-opening-context-recover")
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    progress = load_common_module("progress")
    pause_entries = journal_lines()
    opening_index = next(
        index for index, entry in enumerate(pause_entries)
        if entry.get("kind") == "pass.opened"
    )
    progress.validate_pass_opening_context(
        pause_entries, opening_index, len(pause_entries),
        "the complete Product Review pause tail",
    )

    reset()
    seed_pending_legacy_pass_opening(stop_sessions=True)
    run_pending_opening_bare_stop("abort")
    retire_pending_opening_stop_sessions()
    reported = run_progress("note", "aborted", "--text", "The Product Review run is aborted.")
    check(reported.returncode == 0, reported.stdout + reported.stderr)
    before = len(journal_lines())
    refused_after(
        run_progress("note", "not-converging", "--text", "must stay stopped"),
        before, "normal work after the complete abort tail",
    )
    refused_after(
        run_progress("pass-opening-context-recover"),
        before, "context recovery after the complete abort tail",
    )


@test
def pass_opening_context_abort_owns_one_exact_whole_run_cleanup():
    seed_pending_legacy_pass_opening(stop_sessions=True)
    run_pending_opening_bare_stop("abort")
    retire_pending_opening_stop_sessions()
    reported = run_progress(
        "note", "aborted", "--text", "The Product Review run is aborted.",
    )
    check(reported.returncode == 0, reported.stdout + reported.stderr)

    cleanup_data = {"reason": "aborted", "scope": "whole-run", "choice": "clean"}
    cleanup = run_progress(
        "note", "cleanup.started", "--data", json.dumps(cleanup_data),
    )
    check(cleanup.returncode == 0, cleanup.stdout + cleanup.stderr)
    cleanup_index = len(journal_lines()) - 1
    cleanup_event = journal_lines()[cleanup_index]
    check(
        cleanup_event.get("data", {}).get("abort", {}).get("op")
        == next(
            entry["data"]["op"] for entry in journal_lines()
            if entry.get("kind") == "aborted" and set(entry.get("data", {})) == {"sha", "op"}
        ),
        "cleanup.started does not freeze its exact completed abort authority",
    )

    checked = run_progress("pass-opening-cleanup-check", "audit", "whole-run")
    check(checked.returncode == 0, checked.stdout + checked.stderr)
    checked_again = run_progress("pass-opening-cleanup-check", "audit", "whole-run")
    check(checked_again.returncode == 0, checked_again.stdout + checked_again.stderr)

    for subject, command in (
        ("duplicate cleanup", (
            "note", "cleanup.started", "--data", json.dumps(cleanup_data),
        )),
        ("resume after abort cleanup", ("note", "resumed")),
        ("context recovery after abort cleanup", ("pass-opening-context-recover",)),
        ("normal work after abort cleanup", (
            "note", "not-converging", "--text", "must stay stopped",
        )),
    ):
        refused_after(run_progress(*command), cleanup_index + 1, subject)

    entries = journal_lines()
    opening_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "pass.opened"
    )
    helper_abort_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "aborted" and set(entry.get("data", {})) == {"sha", "op"}
    )
    progress = load_common_module("progress")
    for label, mutate in (
        ("abort authority", lambda changed: changed[helper_abort_index]["data"].update(op="f" * 64)),
        ("cleanup authority", lambda changed: changed[cleanup_index]["data"].update(choice="keep")),
    ):
        changed = json.loads(json.dumps(entries))
        mutate(changed)
        try:
            progress.pass_opening_cleanup_account(
                changed, opening_index, len(changed), f"the changed {label}",
            )
        except SystemExit:
            pass
        else:
            raise AssertionError(f"historical replay accepted changed {label}")

    refs_clear = os.path.join(
        WORKSPACE, "prompts", "product-review", "refs-clear.sh",
    )
    head = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    cleanup_refs = (
        "refs/bwr/test-run/lot-1/cleanup-proof",
        "refs/bwr/test-run/lot-2/cleanup-proof",
    )
    for ref in cleanup_refs:
        subprocess.run(
            ["git", "-C", REPO, "update-ref", ref, head], check=True,
        )
    scoped_clear = subprocess.run(
        [refs_clear, "lot-1"], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(scoped_clear.returncode != 0,
          "lot-scoped refs-clear consumed a whole-run cleanup")
    for ref in cleanup_refs:
        retained = subprocess.run(
            ["git", "-C", REPO, "show-ref", "--verify", "--quiet", ref],
        )
        check(retained.returncode == 0,
              "lot-scoped refs-clear deleted part of a whole-run cleanup")

    changed = json.loads(json.dumps(entries))
    changed[cleanup_index]["data"]["choice"] = "keep"
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as journal:
        for entry in changed:
            journal.write(json.dumps(entry, separators=(",", ":")) + "\n")
    refused_clear = subprocess.run(
        [refs_clear], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(refused_clear.returncode != 0, "refs-clear accepted changed cleanup authority")
    for ref in cleanup_refs:
        retained = subprocess.run(
            ["git", "-C", REPO, "show-ref", "--verify", "--quiet", ref],
        )
        check(retained.returncode == 0,
              "refs-clear deleted a ref before cleanup validation")

    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as journal:
        for entry in entries:
            journal.write(json.dumps(entry, separators=(",", ":")) + "\n")
    cleared = subprocess.run(
        [refs_clear], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(cleared.returncode == 0, cleared.stdout + cleared.stderr)
    for ref in cleanup_refs:
        removed = subprocess.run(
            ["git", "-C", REPO, "show-ref", "--verify", "--quiet", ref],
        )
        check(removed.returncode != 0, "whole-run refs-clear retained a run ref")

    deleting = os.path.join(
        REPO, ".superpowers", "bwr", "2026-01-01-cleanup-test",
    )
    shutil.copytree(WORKSPACE, deleting)
    delete_script = os.path.join(COMMON_PROMPTS, "workspace-delete.sh")
    deleting_refs = (
        "refs/bwr/2026-01-01-cleanup-test/lot-1/cleanup-proof",
        "refs/bwr/2026-01-01-cleanup-test/lot-2/cleanup-proof",
    )
    for ref in deleting_refs:
        subprocess.run(
            ["git", "-C", REPO, "update-ref", ref, head], check=True,
        )
    refused_delete = subprocess.run(
        [delete_script, deleting], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(refused_delete.returncode != 0 and os.path.isdir(deleting),
          "workspace-delete crossed a non-empty run ref namespace")
    deleting_refs_clear = os.path.join(
        deleting, "prompts", "product-review", "refs-clear.sh",
    )
    cleared_deleting = subprocess.run(
        [deleting_refs_clear], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(cleared_deleting.returncode == 0, cleared_deleting.stdout + cleared_deleting.stderr)
    resumed_delete = subprocess.run(
        [delete_script, deleting], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(resumed_delete.returncode == 0 and not os.path.exists(deleting),
          resumed_delete.stdout + resumed_delete.stderr)

    interrupted = os.path.join(
        REPO, ".superpowers", "bwr", "2026-01-02-cleanup-retry",
    )
    shutil.copytree(WORKSPACE, interrupted)
    tombstone = interrupted + ".deleting"
    os.rename(interrupted, tombstone)
    retried_delete = subprocess.run(
        [delete_script, tombstone], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(retried_delete.returncode == 0 and not os.path.exists(tombstone),
          retried_delete.stdout + retried_delete.stderr)

    for ordinal, use_tombstone in ((3, True), (4, False)):
        partial = os.path.join(
            REPO, ".superpowers", "bwr", f"2026-01-0{ordinal}-cleanup-partial",
        )
        shutil.copytree(WORKSPACE, partial)
        partial_tombstone = partial + ".deleting"
        os.rename(partial, partial_tombstone)
        os.remove(os.path.join(
            partial_tombstone, "prompts", "common", "authority_precedence.py",
        ))
        retry_input = partial_tombstone if use_tombstone else partial
        partial_retry = subprocess.run(
            [delete_script, retry_input],
            capture_output=True, text=True, cwd=REPO, env=ENV,
        )
        check(
            partial_retry.returncode == 0 and not os.path.exists(partial_tombstone),
            partial_retry.stdout + partial_retry.stderr,
        )


@test
def pass_opening_context_keeps_ordinary_lot_scoped_ref_cleanup():
    commit, _, _ = seed_task_gate("lot-1", "ordinary-lot-ref-cleanup")
    refs = {
        "lot-1": "refs/bwr/test-run/lot-1/cleanup-proof",
        "lot-2": "refs/bwr/test-run/lot-2/cleanup-proof",
    }
    for ref in refs.values():
        subprocess.run(
            ["git", "-C", REPO, "update-ref", ref, commit], check=True,
        )
    refs_clear = os.path.join(
        WORKSPACE, "prompts", "product-review", "refs-clear.sh",
    )
    cleared = subprocess.run(
        [refs_clear, "lot-1"], capture_output=True, text=True, cwd=REPO, env=ENV,
    )
    check(cleared.returncode == 0, cleared.stdout + cleared.stderr)
    lot_one = subprocess.run(
        ["git", "-C", REPO, "show-ref", "--verify", "--quiet", refs["lot-1"]],
    )
    lot_two = subprocess.run(
        ["git", "-C", REPO, "show-ref", "--verify", "--quiet", refs["lot-2"]],
    )
    check(lot_one.returncode != 0 and lot_two.returncode == 0,
          "ordinary lot-scoped cleanup did not preserve the other lot")


@test
def pass_opening_context_stop_tail_authenticates_owner_context_operation_and_order():
    reset()
    seed_pending_legacy_pass_opening(stop_sessions=True)
    before = len(journal_lines())
    refused_after(
        run_progress(
            "note", "paused", "--text", "foreign stop",
            "--data", json.dumps({"sha": "a" * 40, "op": "not-an-operation"}),
        ),
        before, "a malformed stop operation",
    )
    refused_after(
        run_progress(
            "note", "paused", "--text", "foreign stop",
            "--data", json.dumps({"sha": "a" * 40, "op": "f" * 64}),
        ),
        before, "a well-formed stop operation without its physical owner",
    )

    run_pending_opening_bare_stop("pause")
    before = len(journal_lines())
    refused_after(
        run_progress("note", "paused", "--text", "reported before retirement"),
        before, "a controller stopping point before required retirements",
    )
    before_mutations = list(mutations())
    refused_after(
        run_progress(
            "session-retired", "watchdog-session", "done", "--archive", "--hide",
        ),
        before, "a watchdog retirement before the stopped child",
    )
    check(mutations() == before_mutations,
          "the out-of-order watchdog retirement changed TwiCC")

    config = default_config()
    for payload in (
        config["whoami"]["session"]["annotations"]["bwr"],
        config["sessions"][CALLER]["annotations"]["bwr"],
    ):
        payload.clear()
        payload.update({
            "schema": 1, "feature": "demo-feature", "status": "working",
            "mode": "product-review", "lot": "lot-1", "job": "controller",
        })
    config["sessions"][TARGET]["annotations"]["bwr"] = {
        "schema": 1, "feature": "demo-feature", "status": "working",
        "mode": "product-review", "lot": "lot-1", "mandate": "quality",
        "job": "reviewer",
    }
    config["sessions"]["watchdog-session"] = {
        "id": "watchdog-session",
        "annotations": {"bwr": {
            "schema": 1, "feature": "demo-feature", "status": "working",
            "job": "watchdog",
        }},
    }
    set_config(config)
    refused_after(
        run_progress("session-retired", TARGET, "cancelled", "--archive", "--hide"),
        before, "a changed stopped-child context",
    )
    check(mutations() == before_mutations,
          "the changed stopped-child context changed TwiCC")

    reset()
    seed_pending_legacy_pass_opening(stop_sessions=True)
    first = run_pending_opening_bare_stop("pause")
    retire_pending_opening_stop_sessions()
    reported = run_progress("note", "paused", "--text", "The Product Review run is paused.")
    check(reported.returncode == 0, reported.stdout + reported.stderr)
    resumed = run_progress("note", "resumed")
    check(resumed.returncode == 0, resumed.stdout + resumed.stderr)
    recovered = run_progress("pass-opening-context-recover")
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    entries = journal_lines()
    opening_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("kind") == "pass.opened"
    )
    first_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("data", {}).get("op") == first["data"]["op"]
    )
    child_retirement_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("event") == "session-retired" and entry.get("session") == TARGET
    )
    watchdog_retirement_index = next(
        index for index, entry in enumerate(entries)
        if entry.get("event") == "session-retired"
        and entry.get("session") == "watchdog-session"
    )
    progress = load_common_module("progress")
    for label, mutate in (
        ("owner", lambda changed: changed[first_index].update(by="another-controller")),
        ("context", lambda changed: changed[first_index].update(lot="lot-2")),
        ("operation", lambda changed: changed[first_index]["data"].update(op="f" * 64)),
        ("retirement", lambda changed: changed[child_retirement_index].update(archived=False)),
        ("note order", lambda changed: changed.__setitem__(
            slice(child_retirement_index, watchdog_retirement_index + 1),
            [changed[watchdog_retirement_index], changed[child_retirement_index]],
        )),
    ):
        changed = json.loads(json.dumps(entries))
        mutate(changed)
        try:
            progress.validate_pass_opening_context(
                changed, opening_index, len(changed),
                f"the changed {label} stop tail",
            )
        except SystemExit:
            pass
        else:
            raise AssertionError(f"historical replay accepted a changed stop {label}")


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
def task_pass_refuses_a_built_sublot_without_its_authenticated_origin():
    commit, gate, _ = seed_task_gate("lot-1.1", "missing-sublot-origin")
    data = json.dumps({"built": "lot-1.1", "commit": commit, "gate": gate})
    before = len(journal_lines())
    opening = run_progress("note", "pass.opened", "--data", data)
    check(opening.returncode != 0 and len(journal_lines()) == before,
          "a built sub-lot entered PRODUCT REVIEW without its source pass terminal")


@test
def task_pass_accepts_a_built_sublot_after_the_exact_origin_terminal():
    seed_review_pass(confirmed=1)
    append_note("sublot.allocated", allocation_data(), text="lot-1.1")
    write_confirmed("lot-1", [])
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)
    opened = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)

    commit, gate, _ = seed_task_gate(
        "lot-1.1", "authenticated-sublot-origin",
        plan_spec_lines=("Covers: lot-1-confirmed.md",),
    )
    data = json.dumps({"built": "lot-1.1", "commit": commit, "gate": gate})
    review = run_progress("note", "pass.opened", "--data", data)
    check(review.returncode == 0, review.stdout + review.stderr)


@test
def construction_origin_keeps_root_lots_origin_free():
    origin = run_progress("construction-origin-check", "lot-3")
    check(origin.returncode == 0 and origin.stdout.strip() == "root",
          origin.stdout + origin.stderr)


@test
def generic_construction_terminals_cannot_bypass_a_missing_sublot_origin():
    config = default_config()
    for payload in (
        config["whoami"]["session"]["annotations"]["bwr"],
        config["sessions"][CALLER]["annotations"]["bwr"],
    ):
        payload["lot"] = "lot-1.1"
    set_config(config)

    for kind, data in (
        ("plan.written", {"tasks": 1, "op": "bypass"}),
        ("lot.built", {"tasks": 1, "attempts": 1}),
    ):
        before = len(journal_lines())
        result = run_progress(
            "note", kind, "--data", json.dumps(data, separators=(",", ":")),
        )
        check(result.returncode != 0 and len(journal_lines()) == before,
              f"generic {kind} bypassed the missing sub-lot origin")


@test
def task_pass_consumer_accepts_and_reauthenticates_a_retry_success_shape():
    progress = load_common_module("progress")
    retry = "17:" + "a" * 64
    success = {
        "event": "note",
        "kind": "attempt.succeeded",
        "lot": "lot-1",
        "task": 1,
        "data": {
            "attempt": 2,
            "lot": "lot-1",
            "sha": "b" * 40,
            "gate": "c" * 64,
            "retry": retry,
        },
    }
    validated = []
    progress.validate_attempt_succeeded_entry = (
        lambda entries, index, entry: validated.append((entries, index, entry))
    )
    data = progress.validate_built_task_success(
        [success], 0, success, "lot-1", 1, "b" * 40, "the test pass",
    )
    check(data["retry"] == retry and validated == [([success], 0, success)],
          "the pass consumer did not reauthenticate the successful retry proof")

    success["data"]["foreign"] = "not authority"
    progress.fail = lambda message, detail=None: (_ for _ in ()).throw(
        ValueError((message, detail))
    )
    try:
        progress.validate_built_task_success(
            [success], 0, success, "lot-1", 1, "b" * 40, "the test pass",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("the pass consumer accepted a foreign success field")


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
    }, mode="product-review", lot="lot-1", job="controller")
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
    }, mode="product-review", lot="lot-1", job="controller")
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
def product_verifier_allows_technical_regeneration_until_one_complete_result():
    commit, gate, _ = seed_task_gate("lot-1", "verifier-relaunch-limit")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    }, mode="product-review", lot="lot-1", job="controller")
    content = product_report_text("user")
    report_sha = write_report("reports/product-review/lot-1/lot-1-user.md", content)
    receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    identity = {"pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha}
    for reason in ("error", "lost", "empty", "unusable"):
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
    final_start = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(final_start.returncode == 0, final_start.stdout + final_start.stderr)
    final = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({
            **identity, "confirmed": 0, "disproved": 0, "malformed": 0,
            "claims": [],
        }),
    )
    check(final.returncode == 0, final.stdout + final.stderr)
    before = len(journal_lines())
    after_complete = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(after_complete.returncode != 0 and len(journal_lines()) == before,
          "a complete finding-verifier result allowed another physical call")


@test
def product_verifier_append_serializes_duplicate_openings_and_terminals():
    commit, gate, _ = seed_task_gate("lot-1", "verifier-append-race")
    append_note("pass.opened", {
        "built": "lot-1", "commit": commit, "gate": gate,
        "source_scope": "task", "source_owner": "lot-1/task-1/attempt-1",
        "source_lot": "lot-1", "source_task": 1, "source_attempt": 1,
    }, mode="product-review", lot="lot-1", job="controller")
    content = product_report_text("user")
    report_sha = write_report("reports/product-review/lot-1/lot-1-user.md", content)
    receipt = run_progress(
        "note", "report.received", "--mandate", "user",
        "--data", '{"critical":0,"important":0,"minor":0,"decision":0}',
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    identity = {"pass_commit": commit, "pass_gate": gate, "report_sha256": report_sha}

    def run_concurrently(command):
        lock_path = os.path.join(WORKSPACE, "progress.jsonl.lock")
        with open(lock_path, "a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            processes = [
                subprocess.Popen(
                    command, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                for _ in range(2)
            ]
            deadline = time.monotonic() + 30
            waiting = [False, False]
            while time.monotonic() < deadline:
                waiting = []
                for process in processes:
                    try:
                        with open(f"/proc/{process.pid}/wchan", encoding="utf-8") as source:
                            waiting.append("lock" in source.read())
                    except OSError:
                        waiting.append(False)
                if waiting == [True, True]:
                    break
                time.sleep(0.01)
            check(waiting == [True, True], "both verifier commands did not reach the journal lock")
            fcntl.flock(lock, fcntl.LOCK_UN)
        return [process.communicate(timeout=30) + (process.returncode,) for process in processes]

    start_command = [
        sys.executable, SCRIPT, "subagent-started", "finding-verifier",
        "--mandate", "user", "--data", json.dumps(identity),
    ]
    start_results = run_concurrently(start_command)
    check(sorted(result[2] for result in start_results) == [0, 1], start_results)
    starts = [
        entry for entry in journal_lines()
        if entry.get("event") == "subagent-started"
        and entry.get("kind") == "finding-verifier"
        and entry.get("mandate") == "user"
    ]
    check(len(starts) == 1, "concurrent verifier admission appended duplicate openings")

    unusable = run_progress(
        "subagent-ended", "finding-verifier", "--mandate", "user",
        "--data", json.dumps({**identity, "unusable": "error"}),
    )
    check(unusable.returncode == 0, unusable.stdout + unusable.stderr)
    next_start = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(next_start.returncode == 0, next_start.stdout + next_start.stderr)

    terminal = {
        **identity, "confirmed": 0, "disproved": 0, "malformed": 0, "claims": [],
    }
    terminal_command = [
        sys.executable, SCRIPT, "subagent-ended", "finding-verifier",
        "--mandate", "user", "--data", json.dumps(terminal),
    ]
    terminal_results = run_concurrently(terminal_command)
    check(sorted(result[2] for result in terminal_results) == [0, 1], terminal_results)
    terminals = [
        entry for entry in journal_lines()
        if entry.get("event") == "subagent-ended"
        and entry.get("kind") == "finding-verifier"
        and entry.get("mandate") == "user"
        and "unusable" not in (entry.get("data") or {})
    ]
    check(len(terminals) == 1, "concurrent verifier admission appended duplicate terminals")

    before = len(journal_lines())
    after_complete = run_progress(
        "subagent-started", "finding-verifier", "--mandate", "user",
        "--data", json.dumps(identity),
    )
    check(after_complete.returncode != 0 and len(journal_lines()) == before,
          "the raced complete result did not close the winning physical bracket")


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


def seed_applied_direct_recheck():
    state_path = seed_direct_ruling()
    sha = "a" * 40
    seed_bound_commit(
        "R1", "edit-r1", sha, state_kind="ruling.ready", state_ref="R1",
        state_path=state_path,
    )
    report_path = "reports/answers/R1-recheck.md"
    report_sha = write_report(report_path, "direct accepted recheck\n")
    action = [{"answer": "R1", "status": "active", "route": "spec-in-place"}]
    recheck = run_progress(
        "note", "decision.recheck.completed",
        "--data", json.dumps(recheck_data(
            "R1", "edit-r1", sha, action, artifact_sha=report_sha,
        )),
        "--text", report_path,
    )
    check(recheck.returncode == 0, recheck.stdout + recheck.stderr)

    terminal = {
        "answer": "R1", "ruling": "R1", "route": "spec-in-place",
        "sha": sha, "recheck_op": "edit-r1", "authority_kind": "ruling.ready",
        "authority_ref": "R1", "authority_sha256": file_sha256(state_path),
    }
    applied = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(applied.returncode == 0, applied.stdout + applied.stderr)
    return report_path


def seed_applied_spec_loop_recheck():
    state_path = seed_direct_ruling(route="spec-fixer")
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
    common = {
        "owner": "spec-loop", "commit_op": commit_op, "sha": sha,
        "ruling": "R1", **authority,
    }
    started = run_progress("subagent-started", "finding-verifier", "--data", json.dumps(common))
    check(started.returncode == 0, started.stdout + started.stderr)
    ended = run_progress(
        "subagent-ended", "finding-verifier", "--data", json.dumps({**common, "present": True})
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    recheck_data_value = {
        "owner": "spec-loop", "sha": sha, "commit_op": commit_op,
        "accepted": True, "missing": [],
        "rulings": [{"ruling": "R1", **authority}],
        "actions": [{"answer": "R1", "status": "active", "route": "spec-fixer"}],
        "verifiers": [{"ruling": "R1", "present": True}],
    }
    artifact_path = "reports/answers/spec-loop-close-op-1.json"
    write_report(artifact_path, json.dumps(recheck_data_value, sort_keys=True))
    recheck_data_value["artifact_sha256"] = file_sha256(artifact_path)
    recheck = run_progress(
        "note", "decision.recheck.completed", "--text", artifact_path,
        "--data", json.dumps(recheck_data_value),
    )
    check(recheck.returncode == 0, recheck.stdout + recheck.stderr)
    terminal = {
        "answer": "R1", "ruling": "R1", "route": "spec-fixer",
        "sha": sha, "recheck_op": commit_op, **authority,
    }
    applied = run_progress("note", "ruling.applied", "--data", json.dumps(terminal))
    check(applied.returncode == 0, applied.stdout + applied.stderr)
    return artifact_path


@test
def pass_close_accepts_an_applied_direct_recheck_generation():
    seed_applied_direct_recheck()

    seed_review_pass()
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(closed.returncode == 0, closed.stdout + closed.stderr)


@test
def pass_close_accepts_an_applied_spec_loop_recheck_generation():
    seed_applied_spec_loop_recheck()

    seed_review_pass()
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(closed.returncode == 0, closed.stdout + closed.stderr)


@test
def pass_close_rejects_changed_applied_direct_recheck_artifact():
    artifact_path = seed_applied_direct_recheck()
    write_report(artifact_path, "changed direct recheck\n")
    seed_review_pass()
    before = len(journal_lines())
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(closed.returncode != 0 and len(journal_lines()) == before,
          "a pass close accepted a changed direct recheck artifact")


@test
def pass_close_rejects_changed_applied_spec_loop_recheck_artifact():
    artifact_path = seed_applied_spec_loop_recheck()
    write_report(artifact_path, "{}")
    seed_review_pass()
    before = len(journal_lines())
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":0}')
    check(closed.returncode != 0 and len(journal_lines()) == before,
          "a pass close accepted a changed SPEC-loop recheck artifact")


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
def sublot_opening_requires_and_replays_the_exact_positive_pass_close():
    seed_review_pass(confirmed=1)
    allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-1.1",
        "--data", json.dumps(allocation_data(), separators=(",", ":")),
    )
    check(allocation.returncode == 0, allocation.stdout + allocation.stderr)
    write_confirmed("lot-1", [])

    before = len(journal_lines())
    premature = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(premature.returncode != 0 and len(journal_lines()) == before,
          "a sub-lot opened before its source pass closed")

    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)
    opened = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    origin = run_progress("construction-origin-check", "lot-1.1")
    check(origin.returncode == 0 and origin.stdout.strip(), origin.stdout + origin.stderr)

    duplicate = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(duplicate.returncode != 0, "one sub-lot received two opening terminals")

    rows = journal_lines()
    close_entry = next(entry for entry in rows if entry.get("kind") == "pass.closed")
    close_entry["data"] = {"confirmed": 0}
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as journal:
        for entry in rows:
            journal.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed = run_progress("construction-origin-check", "lot-1.1")
    check(changed.returncode != 0,
          "construction retained a sub-lot opening after its source close changed")


@test
def sublot_opening_can_finish_after_downstream_work_without_rewriting_history():
    seed_review_pass(confirmed=1)
    append_note("sublot.allocated", allocation_data(), text="lot-1.1")
    write_confirmed("lot-1", [])
    append_note("plan.written", {"tasks": 1, "op": "historical-missing-boundary"}, lot="lot-1.1")
    append_note("lot.built", {"tasks": 1, "attempts": 1}, lot="lot-1.1")

    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)
    opened = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    origin = run_progress("construction-origin-check", "lot-1.1")
    check(origin.returncode == 0, origin.stdout + origin.stderr)


@test
def sublot_origin_replays_the_frozen_source_gate_not_the_later_current_head():
    seed_review_pass(confirmed=1)
    append_note("sublot.allocated", allocation_data(), text="lot-1.1")
    write_confirmed("lot-1", [])
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)
    opened = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)

    plan = (
        "# Plan\n\n"
        "Covers: reports/product-review/lot-1/lot-1-confirmed.md\n\n"
        "## Task 1 - Correct the confirmed behavior\n"
        "Achieves: The confirmed behavior is corrected.\n"
        "To verify: The confirmed behavior stays corrected.\n\n"
        "### Design\n"
        "[written at C3.1 - see below]\n"
    )
    write_report("plans/lot-1.1-plan.md", plan)
    config = default_config()
    for payload in (
        config["whoami"]["session"]["annotations"]["bwr"],
        config["sessions"][CALLER]["annotations"]["bwr"],
    ):
        payload["lot"] = "lot-1.1"
    set_config(config)

    source_head = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    plan_commit = os.path.join(WORKSPACE, "prompts", "construction", "plan-commit.sh")
    committed = subprocess.run(
        ["bash", plan_commit, "lot-1.1", "test: publish sub-lot plan"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(committed.returncode == 0, committed.stdout + committed.stderr)
    later_head = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD"], text=True,
    ).strip()
    check(later_head != source_head, "the real plan commit did not create its later HEAD")
    terminal = journal_lines()[-1]
    check(terminal.get("kind") == "plan.written" and terminal.get("lot") == "lot-1.1",
          "the real plan commit did not append its authenticated plan.written terminal")
    current_gate = subprocess.run(
        ["bash", os.path.join(WORKSPACE, "prompts", "construction", "gate-check.sh"),
         "require-current"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(current_gate.returncode != 0,
          "the fixture unexpectedly gave the later plan commit a baseline gate")
    origin = run_progress("construction-origin-check", "lot-1.1")
    check(origin.returncode == 0, origin.stdout + origin.stderr)


@test
def sublot_origin_rejects_a_changed_frozen_source_gate():
    seed_review_pass(confirmed=1)
    append_note("sublot.allocated", allocation_data(), text="lot-1.1")
    write_confirmed("lot-1", [])
    close = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(close.returncode == 0, close.stdout + close.stderr)
    opened = run_progress("note", "sublot.opened", "--text", "lot-1.1")
    check(opened.returncode == 0, opened.stdout + opened.stderr)

    entries = journal_lines()
    pass_commit = next(
        entry for entry in entries if entry.get("kind") == "pass.opened"
    )["data"]["commit"]
    foreign_tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", f"{pass_commit}^^{{tree}}"], text=True,
    ).strip()
    terminal = next(
        entry for entry in entries
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
        and (entry.get("data") or {}).get("scope") == "task"
    )
    terminal["data"]["tree"] = foreign_tree
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as journal:
        for entry in entries:
            journal.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed = run_progress("construction-origin-check", "lot-1.1")
    check(changed.returncode != 0,
          "construction accepted a source-pass gate terminal for another frozen tree")


@test
def sublot_origin_replays_only_the_immediate_source_not_every_ancestor():
    progress = load_common_module("progress")
    ancestors = [
        {"event": "note", "kind": "sublot.opened", "text": f"lot-1.{number}"}
        for number in range(1, 20)
    ]
    opening_index = len(ancestors)
    close_index = opening_index + 2
    entries = [
        *ancestors,
        {"event": "note", "kind": "pass.opened", "data": {"built": "lot-1.19"}},
        {"event": "note", "kind": "sublot.allocated", "text": "lot-1.20",
         "data": {"built": "lot-1.19"}},
        {"event": "note", "kind": "pass.closed", "data": {"confirmed": 1}},
    ]
    calls = []

    def source_close(_entries, _subject, *, validate_origin=True, validate_current_gate=True):
        calls.append(("close", validate_origin, validate_current_gate))
        return opening_index, entries[opening_index], close_index, entries[close_index], 1, "lot-1.19"

    def source_opening(_entries, _before, _subject, *, validate_origin=True):
        calls.append(("allocation", validate_origin))
        return opening_index, entries[opening_index], "lot-1.19", "a" * 40

    progress.current_pass_close = source_close
    progress.current_pass_opening = source_opening
    progress.validate_global_authority_precedence = lambda _entries: None
    progress.validate_current_direct_terminals = lambda _entries, _before, _subject: None
    progress.validate_allocation_identity = lambda *_args: "lot-1"
    progress.validate_allocation_account = lambda *_args: None

    progress.validate_sublot_opening(entries, None, "lot-1.20", "the deep origin")
    check(calls == [("close", False, False), ("allocation", False)],
          f"the historical projector re-enabled ancestor or current-gate validation: {calls}")


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
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    session = "changed-amendment-reach"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    write_report("amendments/1.md", amendment_document(1, order) + "\nchanged after ready\n")
    before = len(journal_lines())
    stale = run_progress("session-retired", session, "done", "--archive", "--hide")
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
    session = "reach-receipt"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retirement = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retirement.returncode == 0, retirement.stdout + retirement.stderr)
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
def amendment_sweep_preflight_audits_the_complete_live_report_journal_free():
    seed_written_amendment_for_reach()
    session = "live-reach-preflight"
    append_live_reach_session(1, session)
    valid = reach_report((2, 0), ("kept", "removed"))
    malformed_reports = (
        valid.replace("\n## Reach account\n", "\nREADY\n\n## Reach account\n", 1),
        valid.replace("Hop 2: 0 new — closed\n", (
            "Hop 2: 0 new — closed\n\n"
            "The semantic sweep covered one extra free-form account.\n"
        ), 1),
    )
    before = list(journal_lines())
    for malformed in malformed_reports:
        write_report("reports/amendment/1/sweep-1.md", malformed)
        result = run_progress("amendment-sweep-check", "1")
        check(result.returncode != 0, "the preflight accepted a malformed complete report")
        check(journal_lines() == before, "a refused preflight changed the journal")
        check(mutations() == [], "a refused preflight changed the reviewer session")

    write_report("reports/amendment/1/sweep-1.md", valid)
    result = run_progress("amendment-sweep-check", "1")
    check(result.returncode == 0, result.stdout + result.stderr)
    proof = json.loads(result.stdout)
    check(proof["amendment"] == 1 and proof["sweep"] == 1, proof)
    check(proof["session"] == session and proof["hop"] == 2 and proof["places"] == 2, proof)
    check(proof["closed"] is True and proof["report_sha256"], proof)
    check(journal_lines() == before, "a successful preflight changed the journal")
    check(mutations() == [], "a successful preflight retired the reviewer")
    marker = os.path.join(WORKSPACE, "amendment-sweep-preflight.json")
    with open(marker, encoding="utf-8") as source:
        frozen = json.load(source)
    check(frozen == proof, "the journal-free preflight did not freeze its consumable proof")


@test
def amendment_sweep_preflight_reports_independent_completion_and_source_errors_together():
    seed_written_amendment_for_reach()
    session = "reach-aggregate-errors"
    append_live_reach_session(1, session)
    malformed = reach_report((1, 0), ("kept",)).replace(
        "active A1/order; 1 unique terms or hits",
        "active A1/order; 1 unique terms, 9 hits",
        1,
    ).replace("Sources: A1/order", "Sources: R2", 1)
    write_report("reports/amendment/1/sweep-1.md", malformed)
    before = list(journal_lines())
    result = run_progress("amendment-sweep-check", "1")
    check(result.returncode != 0, "the preflight accepted two mechanical errors")
    check("completion block contains placeholder or malformed evidence" in result.stdout,
          result.stdout + result.stderr)
    check("P1 names a source outside the current amendment" in result.stdout,
          result.stdout + result.stderr)
    check(journal_lines() == before, "the aggregated refusal changed the journal")


@test
def amendment_sweep_preflight_reports_indented_completion_and_evidence_errors_together():
    seed_written_amendment_for_reach()
    session = "reach-indented-errors"
    append_live_reach_session(1, session)
    malformed = reach_report((1, 0), ("kept",)).replace(
        "active A1/order; 1 unique terms or hits",
        "active A1/order; 12 term families, 1312 matching lines",
        1,
    ).replace("Sources: A1/order", "Sources: R2", 1)
    lines = malformed.splitlines()
    malformed = "\n".join(
        f"    {line}" if index < 7 else line for index, line in enumerate(lines)
    ) + "\n"
    write_report("reports/amendment/1/sweep-1.md", malformed)
    result = run_progress("amendment-sweep-check", "1")
    check(result.returncode != 0, "the preflight accepted an indented completion block")
    check("completion block is indented" in result.stdout, result.stdout + result.stderr)
    check("completion block contains placeholder or malformed evidence" in result.stdout,
          result.stdout + result.stderr)
    check("P1 names a source outside the current amendment" in result.stdout,
          result.stdout + result.stderr)


@test
def reach_completion_template_has_one_literal_column_zero_shape():
    path = os.path.join(
        AMENDMENT_PROMPTS, "reviewer-reach-completion.md",
    )
    with open(path, encoding="utf-8") as source:
        text = source.read()
    lines = text.splitlines()
    start = lines.index("COMPLETION (6 items)")
    block = lines[start:start + 7]
    check(len(block) == 7 and all(line and not line.startswith((" ", "\t")) for line in block),
          block)
    check(text.count("COMPLETION (6 items)") == 1, "the template has several block shapes")
    check("Every line below starts at column zero" in text, "the literal byte rule is absent")


@test
def corrected_reach_contract_resume_authorizes_one_new_physical_reviewer():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "reach-original")
    append_reach_retirement(1, "reach-original", "failed")
    append_live_reach_session(1, "reach-replacement")
    append_reach_retirement(1, "reach-replacement", "failed")
    append_note(
        "not-converging", text="both Reach producers failed the malformed completion contract",
        mode="amendment", lot="lot-1", job="controller",
    )
    configure_reach_session("reach-after-contract-fix", 1)
    before_wrong_reason = len(journal_lines())
    wrong_reason = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "A different recovery reason.",
    )
    refused_after(wrong_reason, before_wrong_reason, "a changed Reach recovery reason")
    before_wrong_scope = len(journal_lines())
    wrong_scope = run_progress(
        "note", "reach.recovery.authorized", "--round", "1", "--mandate", "reach",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    refused_after(wrong_scope, before_wrong_scope, "a mandate-scoped Reach recovery authority")
    authorization = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    check(authorization.returncode == 0, authorization.stdout + authorization.stderr)
    authority = journal_lines()[-1]
    check(authority["kind"] == "reach.recovery.authorized", authority)
    check(authority["data"]["owners"] == ["reach-original", "reach-replacement"], authority)
    before_duplicate = len(journal_lines())
    duplicate = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    refused_after(duplicate, before_duplicate, "a duplicate Reach recovery authority")

    configure_reach_session("reach-original", 1)
    before_reused_third = len(journal_lines())
    reused_third = run_progress("session-started", "reach-original")
    refused_after(
        reused_third, before_reused_third,
        "a recovery owner that reuses the original physical Reach owner",
    )

    configure_reach_session("reach-after-contract-fix", 1)
    started = run_progress("session-started", "reach-after-contract-fix")
    check(started.returncode == 0, started.stdout + started.stderr)
    accepted = run_progress("amendment-sweep-check", "1")
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)

    os.remove(os.path.join(WORKSPACE, "amendment-sweep-preflight.json"))
    append_reach_retirement(1, "reach-after-contract-fix", "failed")
    configure_reach_session("reach-unbounded-fourth", 1)
    refused = run_progress("session-started", "reach-unbounded-fourth")
    check(refused.returncode != 0, "one contract authority authorized several replacements")
    check(not any(entry.get("session") == "reach-unbounded-fourth"
                  for entry in journal_lines()),
          "the refused fourth Reach owner entered durable history")


@test
def reach_stable_blocker_refuses_a_new_reviewer_without_its_resume():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "reach-original")
    append_reach_retirement(1, "reach-original", "failed")
    append_live_reach_session(1, "reach-replacement")
    append_reach_retirement(1, "reach-replacement", "failed")
    append_note(
        "not-converging", text="both Reach producers failed the malformed completion contract",
        mode="amendment", lot="lot-1", job="controller",
    )
    append_live_reach_session(1, "reach-unauthorized-third")
    result = run_progress("amendment-sweep-check", "1")
    check(result.returncode != 0, "the stable blocker allowed an unauthorised third reviewer")


@test
def reach_recovery_requires_two_distinct_physical_owners():
    seed_written_amendment_for_reach()
    append_live_reach_session(1, "reach-reused-owner")
    append_reach_retirement(1, "reach-reused-owner", "failed")
    append_live_reach_session(1, "reach-reused-owner")
    append_reach_retirement(1, "reach-reused-owner", "failed")
    append_note(
        "not-converging", text="one physical owner was incorrectly reused",
        mode="amendment", lot="lot-1", job="controller",
    )
    configure_reach_session("reach-after-contract-fix", 1)
    before = len(journal_lines())
    result = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    refused_after(result, before, "a reused physical Reach owner")


@test
def reach_recovery_history_reauthenticates_its_stable_blocker():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "reach-original")
    append_reach_retirement(1, "reach-original", "failed")
    append_live_reach_session(1, "reach-replacement")
    append_reach_retirement(1, "reach-replacement", "failed")
    append_note(
        "not-converging", text="both Reach producers failed the malformed completion contract",
        mode="amendment", lot="lot-1", job="controller",
    )
    configure_reach_session("reach-after-contract-fix", 1)
    authorization = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    check(authorization.returncode == 0, authorization.stdout + authorization.stderr)
    append_live_reach_session(1, "reach-after-contract-fix")

    lines = journal_lines()
    authority = next(entry for entry in lines if entry.get("kind") == "reach.recovery.authorized")
    authority["data"]["blocker"] = "0:" + "0" * 64
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in lines:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")

    result = run_progress("amendment-sweep-check", "1")
    check(result.returncode != 0, "historical Reach recovery accepted a changed blocker proof")


@test
def reach_recovery_authorization_obeys_pause_resume_and_abort():
    def seed_stable_blocker():
        seed_written_amendment_for_reach()
        append_live_reach_session(1, "reach-original")
        append_reach_retirement(1, "reach-original", "failed")
        append_live_reach_session(1, "reach-replacement")
        append_reach_retirement(1, "reach-replacement", "failed")
        append_note(
            "not-converging", text="both Reach producers failed the completion contract",
            mode="amendment", lot="lot-1", job="controller",
        )
        configure_reach_session("reach-after-contract-fix", 1)

    def authorize():
        return run_progress(
            "note", "reach.recovery.authorized", "--round", "1",
            "--data", '{"reason":"reviewed-contract-correction"}',
            "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
        )

    seed_stable_blocker()
    paused = run_progress("note", "paused", "--text", "pause before recovery")
    check(paused.returncode == 0, paused.stdout + paused.stderr)
    refused_after(authorize(), len(journal_lines()), "Reach recovery during a current pause")

    reset()
    seed_stable_blocker()
    paused = run_progress("note", "paused", "--text", "pause before recovery")
    check(paused.returncode == 0, paused.stdout + paused.stderr)
    resumed = run_progress("note", "resumed", "--text", "resume before recovery")
    check(resumed.returncode == 0, resumed.stdout + resumed.stderr)
    accepted = authorize()
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)

    reset()
    seed_stable_blocker()
    aborted = run_progress("note", "aborted", "--text", "abort before recovery")
    check(aborted.returncode == 0, aborted.stdout + aborted.stderr)
    refused_after(authorize(), len(journal_lines()), "Reach recovery after abort")


@test
def reach_recovery_third_owner_rechecks_a_later_run_stop():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "reach-original")
    append_reach_retirement(1, "reach-original", "failed")
    append_live_reach_session(1, "reach-replacement")
    append_reach_retirement(1, "reach-replacement", "failed")
    append_note(
        "not-converging", text="both Reach producers failed the completion contract",
        mode="amendment", lot="lot-1", job="controller",
    )
    configure_reach_session("reach-after-contract-fix", 1)
    authorization = run_progress(
        "note", "reach.recovery.authorized", "--round", "1",
        "--data", '{"reason":"reviewed-contract-correction"}',
        "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
    )
    check(authorization.returncode == 0, authorization.stdout + authorization.stderr)

    paused = run_progress("note", "paused", "--text", "pause after authorization")
    check(paused.returncode == 0, paused.stdout + paused.stderr)
    refused = run_progress("session-started", "reach-after-contract-fix")
    check(refused.returncode != 0, "a current pause allowed the third Reach owner")

    append_live_reach_session(1, "reach-after-contract-fix")
    historical = run_progress("amendment-sweep-check", "1")
    check(historical.returncode != 0,
          "historical Reach validation ignored a stop before the third owner")


@test
def reach_recovery_third_owner_obeys_stops_after_authorization():
    def seed_authorization():
        seed_written_amendment_for_reach()
        append_live_reach_session(1, "reach-original")
        append_reach_retirement(1, "reach-original", "failed")
        append_live_reach_session(1, "reach-replacement")
        append_reach_retirement(1, "reach-replacement", "failed")
        append_note(
            "not-converging", text="both Reach producers failed the completion contract",
            mode="amendment", lot="lot-1", job="controller",
        )
        configure_reach_session("reach-after-contract-fix", 1)
        authorization = run_progress(
            "note", "reach.recovery.authorized", "--round", "1",
            "--data", '{"reason":"reviewed-contract-correction"}',
            "--text", "The reviewed Reach contract correction authorizes one new physical reviewer.",
        )
        check(authorization.returncode == 0, authorization.stdout + authorization.stderr)

    seed_authorization()
    paused = run_progress("note", "paused", "--text", "pause after authorization")
    check(paused.returncode == 0, paused.stdout + paused.stderr)
    resumed = run_progress("note", "resumed", "--text", "resume after authorization")
    check(resumed.returncode == 0, resumed.stdout + resumed.stderr)
    started = run_progress("session-started", "reach-after-contract-fix")
    check(started.returncode == 0, started.stdout + started.stderr)

    reset()
    seed_authorization()
    aborted = run_progress("note", "aborted", "--text", "abort after authorization")
    check(aborted.returncode == 0, aborted.stdout + aborted.stderr)
    refused = run_progress("session-started", "reach-after-contract-fix")
    check(refused.returncode != 0, "an abort after authorization allowed the third Reach owner")


@test
def amendment_sweep_preflight_requires_one_live_reviewer_generation():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())

    absent = run_progress("amendment-sweep-check", "1")
    check(absent.returncode != 0, "the preflight accepted no live reach reviewer")

    append_reach_session(1, "already-retired-reach")
    retired = run_progress("amendment-sweep-check", "1")
    check(retired.returncode != 0, "the preflight accepted an already retired reviewer")


@test
def amendment_sweep_preflight_is_required_and_blocks_generation_drift_before_retirement():
    seed_written_amendment_for_reach()
    session = "reach-preflight-drift"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    report_a = reach_report((2, 0), ("kept", "removed"))
    report_b = report_a.replace("Exact place evidence.", "Different valid evidence.", 1)
    report_path = "reports/amendment/1/sweep-1.md"
    write_report(report_path, report_a)

    skipped = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(skipped.returncode != 0, "a Reach reviewer retired done without preflight")
    check(not any(entry.get("event") == "session-retired" for entry in journal_lines()),
          "a skipped preflight wrote a successful retirement")

    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    write_report(report_path, report_b)
    drifted = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(drifted.returncode != 0, "same-count report drift crossed terminal retirement")
    check(not any(entry.get("event") == "session-retired" for entry in journal_lines()),
          "drifted bytes produced a durable successful retirement")

    write_report(report_path, report_a.replace(
        "\n## Reach account\n", "\nREADY\n\n## Reach account\n", 1,
    ))
    malformed = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(malformed.returncode != 0, "malformed report drift crossed terminal retirement")

    write_report(report_path, report_a)
    retired = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    received = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":2,"places":2,"closed":true}',
    )
    check(received.returncode == 0, received.stdout + received.stderr)
    check(journal_lines()[-1]["data"]["report_sha256"] == json.loads(
        preflight.stdout,
    )["report_sha256"], "the receipt did not consume the preflight generation")


@test
def amendment_sweep_preflight_recovers_after_each_durable_boundary():
    seed_written_amendment_for_reach()
    session = "reach-preflight-recovery"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    marker = os.path.join(WORKSPACE, "amendment-sweep-preflight.json")

    first = run_progress("amendment-sweep-check", "1")
    second = run_progress("amendment-sweep-check", "1")
    check(first.returncode == 0 and second.returncode == 0 and first.stdout == second.stdout,
          "an interruption after preflight could not reuse the exact proof")

    retired = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    received = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(received.returncode == 0, received.stdout + received.stderr)
    receipt = journal_lines()[-1]["data"]
    check(not os.path.lexists(marker), "a completed receipt left its preflight marker")

    with open(marker, "w", encoding="utf-8") as target:
        json.dump(receipt, target, sort_keys=True, separators=(",", ":"))
        target.write("\n")
    recovered = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(recovered.returncode == 0, recovered.stdout + recovered.stderr)
    check(not os.path.lexists(marker), "receipt interruption recovery did not clear its marker")
    check(sum(entry.get("kind") == "sweep.reported" for entry in journal_lines()) == 1,
          "receipt interruption recovery appended a duplicate receipt")


@test
def amendment_sweep_receipt_refuses_a_skipped_preflight():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_reach_session(1)
    before = len(journal_lines())
    receipt = run_progress(
        "note", "sweep.reported", "--round", "1",
        "--data", '{"hop":1,"places":0,"closed":true}',
    )
    check(receipt.returncode != 0 and len(journal_lines()) == before,
          "a done Reach session received without a consumable preflight")


@test
def amendment_sweep_preflight_requires_the_exact_owed_next_sweep():
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1, reach_report((1,), ("kept",), findings=("IMPORTANT",)), "owed-sweep-1",
    )
    write_report("reports/amendment/1/sweep-2.md", reach_report())
    append_live_reach_session(2, "premature-sweep-2")
    missing_fixer = run_progress("amendment-sweep-check", "2")
    check(missing_fixer.returncode != 0,
          "a new sweep started before the actionable prior sweep's fixer return")
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    owed = run_progress("amendment-sweep-check", "2")
    check(owed.returncode == 0, owed.stdout + owed.stderr)

    reset()
    seed_written_amendment_for_reach()
    accept_reach_sweep(1, reach_report(), "clean-close-sweep-1")
    write_report("reports/amendment/1/sweep-2.md", reach_report())
    append_live_reach_session(2, "after-clean-sweep-2")
    after_clean = run_progress("amendment-sweep-check", "2")
    check(after_clean.returncode != 0, "a later sweep followed a clean Reach close")

    reset()
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1, reach_report((2, 0), ("kept", "removed")), "positive-place-clean-sweep-1",
    )
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    write_report("reports/amendment/1/sweep-2.md", reach_report())
    append_live_reach_session(2, "after-positive-place-clean-sweep-2")
    after_positive_place_clean = run_progress("amendment-sweep-check", "2")
    check(after_positive_place_clean.returncode != 0,
          "an A4 fixer return made a clean positive-place sweep look actionable")

    reset()
    seed_written_amendment_for_reach()
    append_note("amendment.committed", {"amendment": 1})
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "after-commit-sweep-1")
    after_commit = run_progress("amendment-sweep-check", "1")
    check(after_commit.returncode != 0, "a closed amendment generation admitted a sweep")


@test
def amendment_sweep_reach_sources_include_a_later_owner_linked_amendment_ruling():
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1,
        reach_report(hops=(1,), dispositions=("kept",)),
        "reach-before-later-ruling",
    )

    state_path = seed_direct_ruling(ruling="R1", route="amendment-fixer")
    authority = {
        "authority_kind": "ruling.ready",
        "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    }
    dispatched = run_progress(
        "note", "fixer.dispatched",
        "--data", json.dumps({
            "ruling": "R1", "route": "amendment-fixer", **authority,
        }),
        "--text", state_path,
    )
    check(dispatched.returncode == 0, dispatched.stdout + dispatched.stderr)
    before_duplicate = len(journal_lines())
    duplicate = run_progress(
        "note", "fixer.dispatched",
        "--data", json.dumps({
            "ruling": "R1", "route": "amendment-fixer", **authority,
        }),
        "--text", state_path,
    )
    check(duplicate.returncode != 0 and len(journal_lines()) == before_duplicate,
          "a duplicate current-authority amendment-fixer dispatch reached the journal")
    write_report(
        "amendments/1.md",
        amendment_document(1, "apply the reach order; return to product review", ("R1",)),
    )

    write_report(
        "reports/amendment/1/sweep-2.md",
        reach_report(sources=("A1/order", "R1")),
    )
    session = "reach-after-later-ruling"
    configure_reach_session(session, 2)
    append_live_reach_session(2, session)
    preflight = run_progress("amendment-sweep-check", "2")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retired = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retired.returncode == 0, retired.stdout + retired.stderr)
    proof = json.loads(preflight.stdout)
    receipt = run_progress(
        "note", "sweep.reported", "--round", "2",
        "--data", json.dumps({key: proof[key] for key in ("hop", "places", "closed")}),
    )
    check(receipt.returncode == 0, receipt.stdout + receipt.stderr)
    history = run_progress("amendment-state-check")
    check(history.returncode == 0, history.stdout + history.stderr)

    journal = journal_lines()
    dispatch = next(entry for entry in journal if entry.get("kind") == "fixer.dispatched")
    dispatch["data"]["authority_sha256"] = "0" * 64
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "w", encoding="utf-8") as target:
        for entry in journal:
            target.write(json.dumps(entry, separators=(",", ":")) + "\n")
    changed_history = run_progress("amendment-state-check")
    check(changed_history.returncode != 0,
          "historical Reach replay accepted a changed owner-linked source authority")


@test
def amendment_sweep_refuses_an_active_amendment_ruling_without_its_owner_dispatch():
    seed_written_amendment_for_reach()
    seed_direct_ruling(ruling="R1", route="amendment-fixer")
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    session = "reach-with-unowned-ruling"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    before = len(journal_lines())
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode != 0 and len(journal_lines()) == before,
          "Reach preflight omitted an active amendment-fixer ruling without a dispatch")


@test
def amendment_sweep_requires_one_dispatch_for_the_current_ruling_authority():
    seed_written_amendment_for_reach()
    state_path = seed_direct_ruling(ruling="R1", route="amendment-fixer")
    initial_authority = {
        "authority_kind": "ruling.ready",
        "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    }
    append_note("fixer.dispatched", {
        "ruling": "R1", "route": "amendment-fixer", **initial_authority,
    })
    ready_path, ready_sha = append_conflict_generation(
        "R1", 1, ["R1"],
        [{"id": "R1", "action": "qualify", "status": "active",
          "route": "amendment-fixer"}],
        [{"answer": "R1", "status": "active", "route": "amendment-fixer"}],
        state_kind="ruling.ready", state_ref="R1",
    )
    current_authority = {
        "authority_kind": "decision.conflict.ready",
        "authority_ref": "R1/C1",
        "authority_sha256": ready_sha,
    }
    write_report(
        "reports/amendment/1/sweep-1.md",
        reach_report(sources=("A1/order", "R1")),
    )
    session = "reach-after-ruling-authority-change"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    missing_current_owner = run_progress("amendment-sweep-check", "1")
    check(missing_current_owner.returncode != 0,
          "an older amendment-fixer dispatch owned the current ruling authority")

    current_dispatch = run_progress(
        "note", "fixer.dispatched",
        "--data", json.dumps({
            "ruling": "R1", "route": "amendment-fixer", **current_authority,
        }),
        "--text", ready_path,
    )
    check(current_dispatch.returncode == 0, current_dispatch.stdout + current_dispatch.stderr)
    accepted = run_progress("amendment-sweep-check", "1")
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)


@test
def amendment_sweep_ignores_a_dispatch_for_a_superseded_ruling_authority():
    seed_written_amendment_for_reach()
    state_path = seed_direct_ruling(ruling="R1", route="amendment-fixer")
    append_note("fixer.dispatched", {
        "ruling": "R1", "route": "amendment-fixer",
        "authority_kind": "ruling.ready",
        "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    })
    append_conflict_generation(
        "R1", 1, ["R1"],
        [{"id": "R1", "action": "supersede", "status": "superseded",
          "route": None}],
        [{"answer": "R1", "status": "superseded"}],
        state_kind="ruling.ready", state_ref="R1",
    )
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    session = "reach-after-ruling-supersession"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    accepted = run_progress("amendment-sweep-check", "1")
    check(accepted.returncode == 0, accepted.stdout + accepted.stderr)


@test
def amendment_clean_positive_place_sweep_authorizes_consolidation():
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1, reach_report((1,), ("kept",), findings=("IMPORTANT",)), "actionable-sweep-1",
    )
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    clean_report = reach_report((2, 0), ("kept", "removed")) + (
        "\n```text\n## IMPORTANT F1 — Example finding heading\n```\n"
    )
    accept_reach_sweep(2, clean_report, "clean-sweep-2")
    consolidated = run_progress(
        "note", "fixer.returned", "--data", '{"applied":1,"declined":0}',
    )
    check(consolidated.returncode == 0, consolidated.stdout + consolidated.stderr)
    relative = next(entry["text"] for entry in journal_lines()
                    if entry.get("kind") == "spec.written")
    write_project(relative, spec_document(status="amended"))

    started = run_progress("subagent-started", "consolidation", "--round", "1")
    check(started.returncode == 0, started.stdout + started.stderr)


@test
def amendment_construction_only_product_pass_authenticates_its_spec_for_consolidation():
    seed_written_amendment_for_reach(construction_only=True)
    accept_reach_sweep(
        1, reach_report((2, 0), ("kept", "removed")), "construction-only-clean-sweep",
    )
    consolidated = run_progress(
        "note", "fixer.returned", "--data", '{"applied":1,"declined":0}',
    )
    check(consolidated.returncode == 0, consolidated.stdout + consolidated.stderr)
    write_project(CONSTRUCTION_ONLY_SPEC, spec_document(status="amended"))

    started = run_progress("subagent-started", "consolidation", "--round", "1")
    check(started.returncode == 0, started.stdout + started.stderr)


@test
def construction_only_run_opens_a_construction_amendment_from_its_committed_plan_spec():
    append_note(
        "run.started", {"cap": 3}, "construction-only-feature",
        mode="construction", lot="lot-1", job="controller",
    )
    spec_relative = "docs/plans/construction-only-direct-design.md"
    plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-lot-1-plan.md"
    write_project(spec_relative, spec_document())
    write_project(
        plan_relative,
        "# Construction plan\n\n"
        f"Spec: {spec_relative}\n\n"
        "## Task 1 - Implement the product\n"
        "Achieves: The product follows the committed specification.\n"
        "To verify: The product result matches the specification.\n",
    )
    subprocess.run(
        ["git", "-C", REPO, "add", spec_relative, plan_relative], check=True,
    )
    subprocess.run(
        ["git", "-C", REPO, "commit", "-qm", "seed construction authority"], check=True,
    )
    append_note(
        "plan.written", {"tasks": 1, "op": "construction-plan"},
        mode="construction", lot="lot-1", job="controller",
    )
    state_path = seed_direct_ruling(ruling="R1", route="amendment")
    order = "apply R1 and return to lot-1 task 1"
    opened = run_progress(
        "note", "amendment.opened",
        "--data", json.dumps({
            "amendment": 1,
            "origin": "construction",
            "ruling": "R1",
            "authority_kind": "ruling.ready",
            "authority_ref": "R1",
            "authority_sha256": file_sha256(state_path),
        }),
        "--text", order,
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    source = journal_lines()[-1]["data"].get("construction_source")
    check(
        isinstance(source, dict)
        and source.get("lot") == "lot-1"
        and source.get("plan") == plan_relative
        and source.get("spec") == spec_relative,
        "the opening did not freeze its committed Construction spec source",
    )
    write_project("docs/later.txt", "later committed work\n")
    subprocess.run(["git", "-C", REPO, "add", "docs/later.txt"], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-qm", "advance head"], check=True)
    write_report("amendments/1.md", amendment_document(1, order, ("R1",)))
    os.makedirs(os.path.join(WORKSPACE, "reports", "amendment", "1"), exist_ok=True)
    amendment_path = os.path.join(WORKSPACE, "amendments", "1.md")
    written = run_progress(
        "note", "amendment.written", "--data", '{"amendment":1}',
        "--text", amendment_path,
    )
    check(written.returncode == 0, written.stdout + written.stderr)
    accept_reach_sweep(1, reach_report(sources=("R1",)), "construction-direct-reach")
    returned = run_progress(
        "note", "fixer.returned", "--data", '{"applied":1,"declined":0}',
    )
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    write_project(spec_relative, spec_document(status="amended"))
    consolidation = run_progress("subagent-started", "consolidation", "--round", "1")
    check(consolidation.returncode == 0, consolidation.stdout + consolidation.stderr)
    spent = run_progress(
        "note", "bound.spent", "--round", "1",
        "--text", "consolidation round 1 of 3",
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    ended = run_progress(
        "subagent-ended", "consolidation", "--round", "1",
        "--data", '{"exact":true}',
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    consumed = run_progress(
        "note", "verdict.consumed", "--round", "1",
        "--data", '{"check":"consolidation","outcome":"exact"}',
    )
    check(consumed.returncode == 0, consumed.stdout + consumed.stderr)
    commit_script = os.path.join(
        WORKSPACE, "prompts", "amendment", "amendment-commit.sh",
    )
    committed = subprocess.run(
        [commit_script, "1", spec_relative, "docs: land Construction amendment", "-"],
        cwd=REPO, capture_output=True, text=True, env=ENV, timeout=120,
    )
    check(committed.returncode == 0, committed.stdout + committed.stderr)
    state = run_progress("amendment-state-check")
    check(state.returncode == 0, state.stdout + state.stderr)


@test
def construction_feature_run_opens_an_amendment_from_a_later_root_sublot():
    append_note(
        "run.started", {"cap": 3}, "construction-only-feature",
        mode="construction", lot="lot-1", job="controller",
    )
    seed_review_pass(built="lot-2", confirmed=1)
    allocation = run_progress(
        "note", "sublot.allocated", "--text", "lot-2.1",
        "--data", json.dumps(allocation_data("lot-2"), separators=(",", ":")),
    )
    check(allocation.returncode == 0, allocation.stdout + allocation.stderr)
    write_confirmed("lot-2", [], lot="lot-2.1")
    closed = run_progress("note", "pass.closed", "--data", '{"confirmed":1}')
    check(closed.returncode == 0, closed.stdout + closed.stderr)
    sublot = run_progress("note", "sublot.opened", "--text", "lot-2.1")
    check(sublot.returncode == 0, sublot.stdout + sublot.stderr)

    set_caller_bwr(
        mode="construction", lot="lot-2.1", job="controller", task=None, attempt=None,
    )
    spec_relative = "docs/plans/construction-only-direct-design.md"
    plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-lot-2.1-plan.md"
    write_project(spec_relative, spec_document())
    write_project(
        plan_relative,
        "# Construction plan\n\n"
        f"Spec: {spec_relative}\n\n"
        "## Task 1 - Implement the allocated correction\n"
        "Achieves: The allocated correction follows the specification.\n"
        "To verify: The allocated correction matches the specification.\n",
    )
    subprocess.run(
        ["git", "-C", REPO, "add", spec_relative, plan_relative], check=True,
    )
    subprocess.run(
        ["git", "-C", REPO, "commit", "-qm", "seed later sub-lot authority"], check=True,
    )
    append_note(
        "plan.written", {"tasks": 1, "op": "construction-plan"},
        mode="construction", lot="lot-2.1", job="controller",
    )
    state_path = seed_direct_ruling(ruling="R1", route="amendment")
    opened = run_progress(
        "note", "amendment.opened",
        "--data", json.dumps({
            "amendment": 1,
            "origin": "construction",
            "ruling": "R1",
            "authority_kind": "ruling.ready",
            "authority_ref": "R1",
            "authority_sha256": file_sha256(state_path),
        }),
        "--text", "apply R1 and return to lot-2.1 task 1",
    )
    check(opened.returncode == 0, opened.stdout + opened.stderr)
    source = journal_lines()[-1]["data"].get("construction_source")
    with open(os.path.join(WORKSPACE, "progress.jsonl"), "rb") as journal:
        raw_lines = journal.read().splitlines()
    run_proof = next(
        f"{index}:{hashlib.sha256(raw).hexdigest()}"
        for index, raw in enumerate(raw_lines)
        if json.loads(raw).get("kind") == "run.started"
    )
    check(
        isinstance(source, dict)
        and source.get("lot") == "lot-2.1"
        and source.get("run") == run_proof
        and source.get("origin"),
        "the later sub-lot opening did not bind the feature run and exact lot origin",
    )


@test
def construction_only_amendment_source_fails_closed_before_opening():
    for label in ("dirty-spec", "duplicate-spec", "untracked-spec"):
        reset()
        append_note(
            "run.started", {"cap": 3}, "construction-only-feature",
            mode="construction", lot="lot-1", job="controller",
        )
        spec_relative = "docs/plans/construction-only-direct-design.md"
        plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-lot-1-plan.md"
        write_project(spec_relative, spec_document())
        spec_lines = f"Spec: {spec_relative}\n"
        if label == "duplicate-spec":
            spec_lines += f"Spec: {spec_relative}\n"
        write_project(
            plan_relative,
            "# Construction plan\n\n"
            f"{spec_lines}\n"
            "## Task 1 - Implement the product\n"
            "Achieves: The product follows the committed specification.\n"
            "To verify: The product result matches the specification.\n",
        )
        staged = [plan_relative]
        if label != "untracked-spec":
            staged.append(spec_relative)
        subprocess.run(["git", "-C", REPO, "add", *staged], check=True)
        subprocess.run(
            ["git", "-C", REPO, "commit", "-qm", f"seed {label} authority"],
            check=True,
        )
        append_note(
            "plan.written", {"tasks": 1, "op": label},
            mode="construction", lot="lot-1", job="controller",
        )
        if label == "dirty-spec":
            write_project(spec_relative, spec_document(extra="\nUncommitted change.\n"))
        state_path = seed_direct_ruling(ruling="R1", route="amendment")
        before = len(journal_lines())
        opened = run_progress(
            "note", "amendment.opened",
            "--data", json.dumps({
                "amendment": 1,
                "origin": "construction",
                "ruling": "R1",
                "authority_kind": "ruling.ready",
                "authority_ref": "R1",
                "authority_sha256": file_sha256(state_path),
            }),
            "--text", "apply R1 and return to lot-1 task 1",
        )
        refused_after(opened, before, f"the {label} Construction spec source")


@test
def amendment_construction_only_spec_source_fails_closed():
    cases = (
        ("missing", ()),
        ("fenced-only", ("```text", f"Spec: {CONSTRUCTION_ONLY_SPEC}", "```")),
        ("duplicate", (f"Spec: {CONSTRUCTION_ONLY_SPEC}",
                       f"Spec: {CONSTRUCTION_ONLY_SPEC}")),
        ("not-reviewed", ("Spec: docs/plans/not-reviewed-design.md",)),
    )
    for label, plan_spec_lines in cases:
        reset()
        seed_written_amendment_for_reach(
            construction_only=True, plan_spec_lines=plan_spec_lines,
        )
        if label == "not-reviewed":
            write_project("docs/plans/not-reviewed-design.md", spec_document())
        accept_reach_sweep(
            1, reach_report((1, 0), ("kept",)), f"{label}-clean-sweep",
        )
        consolidated = run_progress(
            "note", "fixer.returned", "--data", '{"applied":1,"declined":0}',
        )
        check(consolidated.returncode == 0, consolidated.stdout + consolidated.stderr)
        write_project(CONSTRUCTION_ONLY_SPEC, spec_document(status="amended"))

        started = run_progress("subagent-started", "consolidation", "--round", "1")
        check(started.returncode != 0,
              f"the {label} committed Spec source authorized consolidation")
        check(not any(entry.get("kind") == "subagent-started"
                      and entry.get("subagent") == "consolidation"
                      for entry in journal_lines()),
              f"the {label} committed Spec source mutated the journal")


@test
def amendment_reach_decision_heading_matches_its_place_disposition():
    seed_written_amendment_for_reach()
    session = "reach-decision-account"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    write_report(
        "reports/amendment/1/sweep-1.md",
        reach_report((1, 0), ("DECISION",)),
    )
    missing_heading = run_progress("amendment-sweep-check", "1")
    check(missing_heading.returncode != 0,
          "a Reach DECISION disposition had no matching public finding")

    write_report(
        "reports/amendment/1/sweep-1.md",
        reach_report((1, 0), ("DECISION",), findings=("DECISION",)),
    )
    matched = run_progress("amendment-sweep-check", "1")
    check(matched.returncode == 0, matched.stdout + matched.stderr)


@test
def amendment_sweep_preflight_reauthenticates_every_prior_receipt():
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1, reach_report((1,), ("kept",), findings=("IMPORTANT",)),
        "prior-proof-sweep-1",
    )
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    write_report("reports/amendment/1/sweep-1.md", reach_report((1,), ("removed",)))
    write_report("reports/amendment/1/sweep-2.md", reach_report())
    append_live_reach_session(2, "changed-prior-sweep-2")
    preflight = run_progress("amendment-sweep-check", "2")
    check(preflight.returncode != 0, "a changed prior receipt authorized the next sweep")


@test
def amendment_reach_replacement_must_follow_the_prior_owner_retirement():
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "overlap-old")
    append_live_reach_session(1, "overlap-new")
    append_reach_retirement(1, "overlap-old", "failed")
    overlap = run_progress("amendment-sweep-check", "1")
    check(overlap.returncode != 0,
          "a Reach replacement that overlapped its prior owner became authoritative")

    reset()
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "ordered-old")
    append_reach_retirement(1, "ordered-old", "failed")
    append_live_reach_session(1, "ordered-new")
    ordered = run_progress("amendment-sweep-check", "1")
    check(ordered.returncode == 0, ordered.stdout + ordered.stderr)

    reset()
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_reach_session(1, "done-old")
    append_live_reach_session(1, "after-done-new")
    after_done = run_progress("amendment-sweep-check", "1")
    check(after_done.returncode != 0, "a Reach replacement followed a successful owner")


@test
def amendment_sweep_history_rejects_unowed_and_overlapping_receipts():
    seed_written_amendment_for_reach()
    accept_reach_sweep(
        1, reach_report((1,), ("kept",), findings=("IMPORTANT",)), "history-sweep-1",
    )
    write_report("reports/amendment/1/sweep-2.md", reach_report())
    append_reach_session(2, "history-sweep-2")
    append_raw_reach_receipt(2, "history-sweep-2", hop=1, places=0, closed=True)
    unowed = run_progress("amendment-state-check")
    check(unowed.returncode != 0,
          "historical consumption accepted a sweep before its owed fixer return")

    reset()
    seed_written_amendment_for_reach()
    write_report("reports/amendment/1/sweep-1.md", reach_report())
    append_live_reach_session(1, "history-overlap-old")
    append_live_reach_session(1, "history-overlap-new")
    append_reach_retirement(1, "history-overlap-old", "failed")
    append_reach_retirement(1, "history-overlap-new", "done")
    append_raw_reach_receipt(1, "history-overlap-new", hop=1, places=0, closed=True)
    overlap = run_progress("amendment-state-check")
    check(overlap.returncode != 0,
          "historical consumption accepted overlapping Reach owners")


@test
def amendment_reach_contract_preflights_before_retirement_and_owns_its_handoff():
    mode = open(os.path.join(AMENDMENT_PROMPTS, "MODE.md"), encoding="utf-8").read()
    reviewer = open(
        os.path.join(AMENDMENT_PROMPTS, "reviewer-reach.md"), encoding="utf-8",
    ).read()
    common = open(
        os.path.join(SPEC_PROMPTS, "reviewer-common.md"), encoding="utf-8",
    ).read()
    worker = open(os.path.join(COMMON_PROMPTS, "worker.md"), encoding="utf-8").read()
    skill = open(os.path.join(HERE, "SKILL.md"), encoding="utf-8").read()
    normalized_mode = " ".join(mode.split())

    check("progress.py amendment-sweep-check <K>" in mode,
          "AMENDMENT has no official complete-report preflight")
    check(mode.index("progress.py amendment-sweep-check <K>")
          < mode.index("progress.py session-retired <id> done --archive --hide"),
          "AMENDMENT retires the reviewer before the complete report preflight")
    check("Do not include the SPEC review-pool handoff" in reviewer,
          "the Reach reviewer still emits a SPEC pool handoff")
    check("only when your assignment mode is spec" in common.lower(),
          "the shared SPEC handoff is still universal")
    check("a sweep's complete official preflight" in skill
          and "the marker-consuming `sweep.reported`" in skill,
          "the root stop contract still places Reach retirement after its receipt")
    check("amendment-sweep-preflight.json" in mode
          and "marker plus live reviewer" in mode
          and "marker plus successful retirement" in mode
          and "marker plus its matching receipt" in mode,
          "AMENDMENT does not preserve every preflight interruption boundary")
    check("A Reach replacement never overlaps its prior owner" in normalized_mode
          and "An actionable prior sweep has at least one public finding heading"
          in normalized_mode
          and "A clean close permits A4, never another sweep" in normalized_mode,
          "AMENDMENT does not state the exact current-sweep admission boundary")
    check("Place count records coverage. It never decides whether the sweep is actionable or clean"
          in " ".join(reviewer.split())
          and "Its place count records handled coverage and can be positive" in normalized_mode,
          "AMENDMENT still treats handled place count as actionable work or cleanliness")
    normalized_reviewer = " ".join(reviewer.split())
    check("Could changing at least one current amendment source change this place's truth"
          in normalized_reviewer
          and "Same file, same section, same entity, a neighbouring branch, or the same user journey"
          in normalized_reviewer,
          "Reach still admits adjacency without one counterfactual dependency")
    check("`kept` means that the place depends on the amendment" in normalized_reviewer
          and "Older active rulings are preservation constraints" in normalized_reviewer
          and "never add them to `Sources`" in normalized_reviewer,
          "Reach still confuses a preserved authority with a current amendment source")
    check("A neighbouring error branch that consumes none of the changed state is not a place"
          in normalized_reviewer
          and "name the predecessor place and the exact dependency" in normalized_reviewer,
          "Reach has no direct negative or transitive-dependency instruction")
    check("reach.recovery.authorized --round <K>" in mode
          and "It authorizes no fourth physical reviewer" in normalized_mode
          and "is not a run-level `resumed` boundary" in normalized_mode,
          "AMENDMENT has no bounded post-contract-correction Reach recovery")
    check("The spec path is authority, not controller memory" in normalized_mode
          and "one structural root `Spec: <relative path>`" in normalized_mode
          and "exact committed plan reviewed by the amendment's voided pass" in normalized_mode,
          "AMENDMENT does not define the construction-only A4 spec source")

    for subject, contract in (("shared worker", worker), ("root skill", skill),
                              ("AMENDMENT", mode)):
        normalized = " ".join(contract.split())
        check("correct only the local invocation once" in normalized,
              f"{subject} has no bounded helper-invocation correction")
        check("same live actor" in normalized and "does not consume" in normalized,
              f"{subject} turns a local invocation correction into replacement work")
        check("do not import" in normalized.lower() and "exact corrected invocation" in normalized,
              f"{subject} does not distinguish an unsupported import from a helper refusal")


@test
def post_amendment_completeness_keeps_built_design_historical():
    amendment_mode = open(
        os.path.join(AMENDMENT_PROMPTS, "MODE.md"), encoding="utf-8",
    ).read()
    construction_mode = open(
        os.path.join(HERE, "prompts", "construction", "MODE.md"), encoding="utf-8",
    ).read()
    completeness = open(
        os.path.join(HERE, "prompts", "construction", "completeness.md"),
        encoding="utf-8",
    ).read()
    skill = open(os.path.join(HERE, "SKILL.md"), encoding="utf-8").read()

    amendment = " ".join(amendment_mode.split())
    construction = " ".join(construction_mode.split())
    checker = " ".join(completeness.split())
    root = " ".join(skill.split())

    for subject, contract in (("AMENDMENT", amendment),
                              ("CONSTRUCTION", construction),
                              ("completeness checker", checker),
                              ("root skill", root)):
        check("post-amendment C2" in contract,
              f"{subject} does not distinguish the post-amendment C2 rerun")
        check("historical implementation record" in contract,
              f"{subject} lets post-amendment C2 reinterpret a built Design")
        check("controller-owned task contract" in contract,
              f"{subject} gives post-amendment C2 no exact current plan boundary")

    check("must not be added retroactively to the built plan's `Covers:` or "
          "`Descends from:`" in checker,
          "the checker folds amendment-created work into the built sub-lot")
    check("mandatory input to the fresh complete PRODUCT REVIEW" in checker,
          "the checker can discard the amendment-created implementation obligation")
    check("never rewrite `### design` or `### disagreement`" in construction.lower(),
          "CONSTRUCTION can repair post-amendment C2 by rewriting historical Design")
    check("C2.5 plan-only successor" in construction,
          "CONSTRUCTION has no bounded route for a real controller-contract mismatch")

    counter_1 = checker[checker.index("### 1 ·"):checker.index("### 2 ·")]
    counter_2 = checker[checker.index("### 2 ·"):checker.index("### 3 ·")]
    counter_4 = checker[checker.index("### 4 ·"):checker.index("## For a sub-lot")]
    for number, counter in ((1, counter_1), (2, counter_2), (4, counter_4)):
        check("In ordinary C2" in counter and "In post-amendment C2" in counter,
              f"counter {number} leaves its ordinary rule active after an amendment")
    check("**The reference set is the plan's `Covers:` line, never the whole spec.**"
          not in counter_1,
          "counter 1 still states one unconditional current-source rule")
    check("The plan's `Global Constraints` section is a copy of the spec's" not in counter_4,
          "counter 4 still requires unconditional current-spec copy equality")
    check("post-amendment rules below replace, rather than supplement" in checker,
          "the checker can combine ordinary and post-amendment counter rules")
    check("Post-amendment C2 reports" in checker
          and "Historical Covers retained" in checker
          and "Current product contract" in checker,
          "the post-amendment report still asks for ordinary source-copy counts")

    check("In post-amendment C2, keep the exact built `Covers:` set" in construction
          and "In post-amendment C2, every task traces to that frozen set" in construction
          and "In post-amendment C2, do not compare the historical Global Constraints copy"
          in construction,
          "CONSTRUCTION leaves ordinary C2.1, C2.2 or C2.4 active post-amendment")


@test
def sweep_receipt_binds_each_disposition_to_one_exact_place_block():
    seed_written_amendment_for_reach()
    valid = reach_report((2, 0), ("kept", "removed"))
    before_last, after_last = valid.rsplit("Disposition: removed\n", 1)
    malformed = before_last.replace(
        "Disposition: kept\n", "Disposition: kept\nDisposition: removed\n", 1,
    ) + after_last
    write_report("reports/amendment/1/sweep-1.md", malformed)
    append_live_reach_session(1, "malformed-place-account")
    before = len(journal_lines())
    result = run_progress("amendment-sweep-check", "1")
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
    session = "reach-structure"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    before = len(journal_lines())
    placeholder = run_progress("amendment-sweep-check", "1")
    check(placeholder.returncode != 0 and len(journal_lines()) == before,
          "the untouched completion template became accepted evidence")
    orphan = reach_report() + "\n## P99 · orphan\nDisposition: removed\n"
    write_report("reports/amendment/1/sweep-1.md", orphan)
    orphan_result = run_progress("amendment-sweep-check", "1")
    check(orphan_result.returncode != 0 and len(journal_lines()) == before,
          "out-of-block structural lines satisfied the Reach account")
    fenced = reach_report() + (
        "\n```text\n## P99 · example\nDisposition: removed\n```\n"
    )
    write_report("reports/amendment/1/sweep-1.md", fenced)
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retirement = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retirement.returncode == 0, retirement.stdout + retirement.stderr)
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
        findings=("DECISION",),
    )
    accept_reach_sweep(1, report, "five-hop-reach")
    data = journal_lines()[-1]["data"]
    check(data["hop"] == 5 and data["places"] == 4 and data["closed"] is True, data)


@test
def open_reach_requires_an_explicit_unenumerable_input_not_only_counts():
    seed_written_amendment_for_reach()
    blocker = "missing durable input: event consumer registry is absent"
    valid = reach_report(
        (2, 1), ("kept", "removed", "DECISION"), findings=("DECISION",),
        open_blocker=blocker,
    )
    invalid = valid.replace(
        f"; next hop cannot be enumerated — {blocker}", "",
    )
    session = "open-frontier-reach"
    configure_reach_session(session, 1)
    append_live_reach_session(1, session)
    write_report("reports/amendment/1/sweep-1.md", invalid)
    before = len(journal_lines())
    counts_only = run_progress("amendment-sweep-check", "1")
    check(counts_only.returncode != 0 and len(journal_lines()) == before,
          "positive hop counts alone became a NOT CLOSED frontier")
    write_report("reports/amendment/1/sweep-1.md", valid)
    preflight = run_progress("amendment-sweep-check", "1")
    check(preflight.returncode == 0, preflight.stdout + preflight.stderr)
    retirement = run_progress("session-retired", session, "done", "--archive", "--hide")
    check(retirement.returncode == 0, retirement.stdout + retirement.stderr)
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
    accept_reach_sweep(1, reach_report(), "amendment-commit-reach")
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
def subagent_recovery_spec_loop_closes_lost_before_regeneration():
    state_path = seed_direct_ruling(ruling="R1", route="spec-fixer")
    authority = {
        "authority_kind": "ruling.ready", "authority_ref": "R1",
        "authority_sha256": file_sha256(state_path),
    }
    append_note("fixer.dispatched", {"ruling": "R1", "route": "spec-fixer", **authority})
    common = {
        "owner": "spec-loop", "commit_op": "close-op-1", "sha": "a" * 40,
        "ruling": "R1", **authority,
    }
    append_note("spec.committed", {
        "op": common["commit_op"], "sha": common["sha"], "spec_round": 4,
        "review_sha256": "b" * 64, "spec_sha256": "c" * 64,
    })
    started = run_progress(
        "subagent-started", "finding-verifier", "--data", json.dumps(common)
    )
    check(started.returncode == 0, started.stdout + started.stderr)
    lost = run_progress(
        "subagent-ended", "finding-verifier",
        "--data", json.dumps({**common, "unusable": "lost"}),
    )
    check(lost.returncode == 0, lost.stdout + lost.stderr)
    replacement = run_progress(
        "subagent-started", "finding-verifier", "--data", json.dumps(common)
    )
    check(replacement.returncode == 0, replacement.stdout + replacement.stderr)
    ended = run_progress(
        "subagent-ended", "finding-verifier",
        "--data", json.dumps({**common, "present": True}),
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    check(json.loads(run_progress("subagents-open").stdout) == [],
          "the replacement SPEC-loop verifier remained open")


@test
def subagent_recovery_consolidation_closes_lost_before_same_round_regeneration():
    seed_written_amendment_for_reach()
    accept_reach_sweep(1, reach_report(), "consolidation-recovery-reach")
    returned = run_progress("note", "fixer.returned", "--data", '{"applied":1,"declined":0}')
    check(returned.returncode == 0, returned.stdout + returned.stderr)
    relative = next(entry["text"] for entry in journal_lines()
                    if entry.get("kind") == "spec.written")
    write_project(relative, spec_document(status="amended"))
    started = run_progress("subagent-started", "consolidation", "--round", "1")
    check(started.returncode == 0, started.stdout + started.stderr)
    spent = run_progress(
        "note", "bound.spent", "--round", "1", "--text", "consolidation round 1 of 3"
    )
    check(spent.returncode == 0, spent.stdout + spent.stderr)
    lost = run_progress(
        "subagent-ended", "consolidation", "--round", "1",
        "--data", '{"unusable":"lost"}',
    )
    check(lost.returncode == 0, lost.stdout + lost.stderr)
    replacement = run_progress("subagent-started", "consolidation", "--round", "1")
    check(replacement.returncode == 0, replacement.stdout + replacement.stderr)
    ended = run_progress(
        "subagent-ended", "consolidation", "--round", "1", "--data", '{"exact":true}'
    )
    check(ended.returncode == 0, ended.stdout + ended.stderr)
    check(json.loads(run_progress("subagents-open").stdout) == [],
          "the replacement consolidation checker remained open")


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
def risk_admission_rejects_artificially_narrow_probability_bases():
    with open(os.path.join(COMMON_PROMPTS, "review-risk.md"), encoding="utf-8") as f:
        risk = f.read()
    with open(os.path.join(HERE, "prompts", "construction", "design-checker.md"), encoding="utf-8") as f:
        design = f.read()
    risk_flat = " ".join(risk.split())
    design_flat = " ".join(design.split())

    check("every condition necessary for the consequence" in risk_flat,
          "probability must use only necessary conditions")
    check("other supported paths to the same consequence" in risk_flat,
          "probability must account for supported alternative paths")
    check("Hold the candidate's violated property and causal mechanism fixed" in risk_flat,
          "alternate paths must remain realizations of the same candidate")
    check("Do not aggregate an independent candidate that only shares the end consequence" in risk_flat,
          "independent causes must not inflate this candidate's probability")
    check("A probability basis contradicted by available evidence is invalid" in risk_flat,
          "contradicted probability bases must not filter findings")
    check("affects relevance, not probability" in risk_flat,
          "pre-existing conditions must not lower probability")
    check("Classify impact from the consequence alone" in risk_flat,
          "probability must not lower consequence impact")

    check("A necessary condition is not automatically sufficient" in design_flat,
          "the Design checker must inspect the complete behavioural predicate")
    check("Try to falsify every `Achieves`-to-step and `To verify`-to-behaviour match" in design_flat,
          "the Design checker must challenge its positive mappings")
    check("a supported counter-path leaves the contract false" in design_flat,
          "a named step must not stand as proof over a counter-path")
    check("named files are starting evidence, not a closed read set" in design_flat,
          "the Design must not close its own evidence boundary")
    check("directly relevant repository evidence needed to close each asserted predicate" in design_flat,
          "the checker must follow evidence outside the Design's named files")
    check("already exists before this task remains in scope" in design_flat,
          "pre-existing conditions relied on by the Design must stay in scope")


@test
def design_checker_proves_parent_product_closure_without_becoming_lot_review():
    with open(os.path.join(HERE, "prompts", "construction", "design-checker.md"), encoding="utf-8") as f:
        design = f.read()
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"), encoding="utf-8") as f:
        implementer = f.read()
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"), encoding="utf-8") as f:
        mode = f.read()
    design_flat = " ".join(design.split())
    implementer_flat = " ".join(implementer.split())
    mode_flat = " ".join(mode.split())

    check("exact `Covers:` obligation" in design_flat and "exact `Descends from:` obligation" in design_flat,
          "the checker must bind the task to its frozen parent obligation")
    check("The frozen task contract is evidence, not authority that the parent obligation is complete" in design_flat,
          "the task contract must not prove its own sufficiency")
    check("externally observable product result" in design_flat,
          "the checker must trace each affected behaviour to its product result")
    check("success, failure, ambiguous outcome, repetition, retry and recovery" in design_flat,
          "the checker must inspect every supported outcome class")
    check("supported orderings and interactions" in design_flat,
          "the checker must inspect temporal interactions that affect the same guarantee")
    check("`unchanged`, `preserved` or `outside scope`" in design_flat,
          "the checker must challenge exclusions that share the same product guarantee")
    check("directly coupled task" in design_flat and "independent task" in design_flat,
          "the checker must distinguish necessary composition from a lot-wide review")
    check("observe the external contract through the real integration boundary" in design_flat,
          "the checker must reject tests that prove only its local abstraction")
    check("the frozen task contract cannot close its exact parent obligation" in design_flat,
          "an insufficient controller-owned contract must become a checker finding")
    check("Do not perform a lot-wide PRODUCT REVIEW" in design_flat,
          "the expanded mandate must remain bounded to the current task")
    check("finding against the frozen task contract" in implementer_flat and "Blocked" in implementer_flat,
          "the implementer must route a controller-owned contract defect without widening its Design")
    check("parent product obligation" in mode_flat and "directly coupled" in mode_flat,
          "the controller summary must describe the expanded checker boundary")
    blocked_route = mode.split("### C3.10 · Blocked", 1)[1]
    check(
        "plan-commit.sh" in blocked_route
        and "Repeat C2" in blocked_route
        and "baseline gate" in blocked_route
        and "attempt-started.sh" in blocked_route,
        "the controller-contract correction must publish and establish a baseline before retry",
    )


@test
def sublot_construction_requires_one_replayed_product_review_origin():
    with open(os.path.join(HERE, "prompts", "product-review", "MODE.md"), encoding="utf-8") as f:
        product = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"), encoding="utf-8") as f:
        construction = " ".join(f.read().split())
    with open(os.path.join(COMMON_PROMPTS, "progress-rules.md"), encoding="utf-8") as f:
        rules = " ".join(f.read().split())

    for contract in (product, construction, rules):
        check("sublot.opened" in contract and "CONSTRUCTION origin" in contract,
              "a direct contract omits the sub-lot origin terminal")
        check("positive" in contract and "allocation" in contract,
              "a direct contract does not bind the source pass and allocation")
    check("before any copy, staging, commit or marker" in construction,
          "C1 does not refuse before plan publication mutates state")
    check("Plan publication, attempt start, `lot.built`" in rules
          and "first PRODUCT REVIEW pass" in rules,
          "the shared rule omits a direct construction-origin consumer")


@test
def code_contract_blocker_stops_its_current_round_and_uses_the_plan_fault_route():
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"), encoding="utf-8") as f:
        implementer = " ".join(f.read().split())
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"), encoding="utf-8") as f:
        mode = " ".join(f.read().split())
    with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as f:
        skill = " ".join(f.read().split())

    for contract in (implementer, mode, skill):
        check("code.review.blocked" in contract, "a direct consumer omits the code blocker terminal")
        check("contract-blocked" in contract and "carried" in contract,
              "a direct consumer omits the complete blocker batch")
        check("composes" in contract and "matching first checker" in contract,
              "a direct consumer lets the blocker replace an inherited obligation")
    check("every code round" in implementer and "Do not spend later rounds" in implementer,
          "the implementer can still wait for round 10")
    check("not `code.review.resolved`" in implementer,
          "the blocker can still impersonate an implementer-owned settlement")
    check("does not wait for round 10" in mode and "Before you edit the plan" in mode,
          "the controller can change authority before the blocker is frozen")
    check("reportless" in mode and "matching first checker" in mode,
          "the controller does not preserve the exact retry obligation")


@test
def design_self_review_precedes_the_first_checker_without_creating_a_round():
    with open(os.path.join(HERE, "prompts", "construction", "implementer.md"), encoding="utf-8") as f:
        implementer = f.read()
    with open(os.path.join(HERE, "prompts", "construction", "MODE.md"), encoding="utf-8") as f:
        mode = f.read()
    with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as f:
        skill = f.read()

    design_self_review = implementer.split("## Design self review", 1)[1].split("## Design checker", 1)[0]
    self_review_flat = " ".join(design_self_review.split())
    mode_flat = " ".join(mode.split())
    skill_flat = " ".join(skill.split())
    check(implementer.index("## Design") < implementer.index("## Design self review")
          < implementer.index("## Design checker"),
          "the Design self review must follow Design writing and precede the first checker")
    check("Once, and only once, for each newly written Design" in self_review_flat,
          "the Design self review must have the same one-pass boundary as code self review")
    check("task contract and its parent product obligation" in self_review_flat,
          "the Design self review must check complete parent-product coverage")
    check("steps, interfaces and directly required dependencies" in self_review_flat,
          "the Design self review must check internal composition")
    check("chosen and discarded alternatives" in self_review_flat and "repository evidence" in self_review_flat,
          "the Design self review must check its decisions against real evidence")
    check("success, failure, ambiguous outcome, repetition, retry and recovery" in self_review_flat,
          "the Design self review must check supported outcome classes")
    check("Fix the Design during this same pass" in self_review_flat,
          "a self-review correction must remain inside the one pass")
    check("no journal event" in self_review_flat and "no Design-checker round" in self_review_flat,
          "the Design self review must not become durable workflow state")
    implementer_flat = " ".join(implementer.split())
    check("exact `Covers:` obligation" in implementer_flat
          and "exact `Descends from:` obligation" in implementer_flat,
          "the implementer must bind the self review to the frozen parent source")
    check("For a normal lot, read the named spec decision" in implementer_flat,
          "a normal-lot self review must read its exact spec source")
    check("For a sub-lot, read the exact confirmed-finding artifact named by `Covers:`" in implementer_flat
          and "finding identity named by `Descends from:`" in implementer_flat,
          "a sub-lot self review must read its exact confirmed finding")
    check("The spec decision your task descends from" not in implementer,
          "a universal spec-decision source must not override the sub-lot confirmed finding")
    check("Stay within the current task" in implementer_flat,
          "the implementer parent-source read must remain task-bounded")
    check("C3.1a — Design self review" in mode_flat and "before the first Design checker" in mode_flat,
          "the controller summary must expose the Design self-review boundary")
    check("Before a newly written Design enters its first Design-checker round" in skill_flat
          and "Design self review" in skill_flat,
          "the root skill must preserve the Design self-review boundary across resume")
    resume_tail = skill.split("The pair is the resume test:", 1)[1].lstrip()
    check(resume_tail.startswith("- latest domain `bound.spent`, no matching `verdict.consumed`"),
          "the resume-pair introduction must remain directly attached to its bullets")


@test
def human_judgment_context_precedes_every_choice_widget_without_a_new_schema():
    with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as f:
        skill = f.read()
    mode_paths = {
        "SPEC": os.path.join(HERE, "prompts", "spec", "MODE.md"),
        "CONSTRUCTION": os.path.join(HERE, "prompts", "construction", "MODE.md"),
        "PRODUCT REVIEW": os.path.join(HERE, "prompts", "product-review", "MODE.md"),
        "AMENDMENT": os.path.join(HERE, "prompts", "amendment", "MODE.md"),
    }
    modes = {}
    for name, path in mode_paths.items():
        with open(path, encoding="utf-8") as f:
            modes[name] = " ".join(f.read().split())

    skill_flat = " ".join(skill.split())
    check("The widget is the last step, never the explanation" in skill_flat,
          "a human judgment must receive context before its widget")
    check("Every DECISION starts with an explicit product orientation" in skill_flat,
          "a product DECISION must start with a product orientation")
    check("feature or product area" in skill_flat and "exact screen or surface" in skill_flat,
          "the orientation must identify the product area and surface")
    check("what the user does immediately before the issue" in skill_flat
          and "what the user sees now" in skill_flat,
          "the orientation must establish the user action and visible result")
    check("Define every project-specific object or label" in skill_flat,
          "the orientation must define project-specific language")
    check("one concrete start-to-finish example" in skill_flat
          and "without implementation details" in skill_flat,
          "the orientation must include one concrete product example")
    check("before detection, evidence, timing, or options" in skill_flat,
          "product orientation must precede technical and workflow analysis")
    check("understandable when read without the preceding prose" in skill_flat,
          "the widget question must remain understandable on its own")
    check("A workflow-only judgement starts with an equivalent workflow orientation" in skill_flat
          and "Do not invent a product screen or user action" in skill_flat,
          "a workflow judgment must orient the human without inventing product context")
    check("why the answer is necessary now" in skill_flat and "what cannot continue without it" in skill_flat,
          "the orchestrator must explain the decision need and blocker")
    check("who detected it" in skill_flat and "evidence confirmed it" in skill_flat,
          "the orchestrator must identify the decision origin and proof")
    check("why an earlier phase did not settle it" in skill_flat,
          "the orchestrator must explain why the question appears at this point")
    check("Do not invent causality, fault or a missed opportunity" in skill_flat,
          "the earlier-detection account must remain evidence-based")
    check("advantages" in skill_flat and "downsides and risks" in skill_flat,
          "every option must expose its trade-offs")
    check("what the workflow does next" in skill_flat,
          "every option must expose its downstream route")
    check("one numbered context block per question" in skill_flat
          and "same IDs and short labels in the widget" in skill_flat,
          "batched decisions must map their prose to one widget call")
    check("No fixed prose template" in skill_flat and "no new artifact or schema" in skill_flat,
          "the presentation rule must remain prompt-only and flexible")
    check("setup choice" in skill_flat and "provider" in skill_flat,
          "ordinary configuration questions must stay concise")

    for name, mode in modes.items():
        check("human-judgment presentation rule" in mode,
              f"{name} does not propagate the shared human-judgment presentation rule")
    for name in ("SPEC", "PRODUCT REVIEW", "AMENDMENT"):
        check("product orientation" in modes[name],
              f"{name} does not preserve product orientation at its direct DECISION boundary")
    check("workflow orientation" in modes["CONSTRUCTION"] and "product orientation" in modes["CONSTRUCTION"],
          "CONSTRUCTION must distinguish workflow judgments from product DECISIONs")
    check(modes["PRODUCT REVIEW"].count("human-judgment presentation rule") >= 3,
          "PRODUCT REVIEW must propagate the rule to initial, supplemental and conflict questions")
    check(modes["PRODUCT REVIEW"].count("product orientation") >= 3,
          "PRODUCT REVIEW must preserve product orientation for initial, supplemental and conflict questions")
    check("discussion is free-form" in modes["AMENDMENT"] and "final bounded choice" in modes["AMENDMENT"],
          "AMENDMENT must preserve discussion while contextualising its final choice")

    amendment_repeated_reach = modes["AMENDMENT"].split("And once only", 1)[1].split(
        "A DECISION raised by the sweep", 1)[0]
    check("human-judgment presentation rule" in amendment_repeated_reach
          and "workflow orientation" in amendment_repeated_reach,
          "a repeated unliftable Reach blocker must orient its human judgment")
    amendment_exit = modes["AMENDMENT"].split("The exit door", 1)[1].split(
        "The hand-back clause", 1)[0]
    check("human-judgment presentation rule" in amendment_exit
          and "workflow orientation" in amendment_exit,
          "the Reach exit door must orient its human judgment")

    construction_dirty = modes["CONSTRUCTION"].split(
        "C0.1 · The working tree", 1)[1].split("C0.2 · Read the gate file", 1)[0]
    check("human-judgment presentation rule" in construction_dirty
          and "workflow orientation" in construction_dirty,
          "a foreign dirty tree must orient its human judgment")
    construction_gate_leaf = modes["CONSTRUCTION"].split(
        "C0.2 · Read the gate file", 1)[1].split("C0.2a · Validate gate execution", 1)[0]
    check("human-judgment presentation rule" in construction_gate_leaf
          and "workflow orientation" in construction_gate_leaf,
          "a foreign gate leaf must orient its human judgment")
    construction_repeated_failure = modes["CONSTRUCTION"].split(
        "And it runs once logically per task", 1)[1].split("C3.9 · Where the next attempt starts", 1)[0]
    check("human-judgment presentation rule" in construction_repeated_failure
          and "workflow orientation" in construction_repeated_failure,
          "a repeated post-diagnostic failure must orient its human judgment")
    construction_abort_refs = modes["CONSTRUCTION"].split(
        "The code:", 1)[1].split("A task creates files", 1)[0]
    check("human-judgment presentation rule" in construction_abort_refs
          and "workflow orientation" in construction_abort_refs,
          "abort ref retention must orient its human judgment")

    product_structural_exits = modes["PRODUCT REVIEW"].split(
        "Two numbers to report", 1)[1].split("The rule that governs every later pass", 1)[0]
    check("human-judgment presentation rule" in product_structural_exits
          and "workflow orientation" in product_structural_exits,
          "oversized and repeated-area sub-lot exits must orient their human judgments")

    audit_blockers = skill_flat.split("Audit what comes back", 1)[1].split(
        "Spot-check a report", 1)[0]
    check("human-judgment presentation rule" in audit_blockers
          and "workflow orientation" in audit_blockers,
          "shared malformed and NOT DONE blockers must orient their human judgments")
    workspace_ignore = skill_flat.split(
        "It also refuses to create anything if `.superpowers/` is not ignored", 1)[1].split(
        "The subject is yours", 1)[0]
    check("human-judgment presentation rule" in workspace_ignore
          and "workflow orientation" in workspace_ignore,
          "the workspace ignore choice must orient its human judgment")
    abort_trace = skill_flat.split(
        "The workspace and the git refs go together", 1)[1].split("The reports need no decision", 1)[0]
    check("human-judgment presentation rule" in abort_trace
          and "workflow orientation" in abort_trace,
          "the abort keep-or-clean choice must orient its human judgment")
    final_trace = skill_flat.split("The feature is finished", 1)[1].split(
        "The cap is asked once", 1)[0]
    check("human-judgment presentation rule" in final_trace
          and "workflow orientation" in final_trace,
          "the final-delivery keep-or-clean choice must orient its human judgment")

    spec_not_done = modes["SPEC"].split("And no block of that closing round", 1)[1].split(
        "Never a reviewer simply writing READY", 1)[0]
    check("human-judgment presentation rule" in spec_not_done
          and "workflow orientation" in spec_not_done,
          "the second full-round NOT DONE must orient its human judgment")
    product_replacement = modes["PRODUCT REVIEW"].split(
        "And relaunch once", 1)[1].split("Then go to R2.1", 1)[0]
    check("human-judgment presentation rule" in product_replacement
          and "workflow orientation" in product_replacement,
          "the replacement lens stable blocker must orient its human judgment")
    construction_missing_start = modes["CONSTRUCTION"].split(
        "Ten refusals, and each has its route", 1)[1].split("The dirty-tree row grants one return", 1)[0]
    check("missing start marker" in construction_missing_start
          and "human-judgment presentation rule" in construction_missing_start
          and "workflow orientation" in construction_missing_start,
          "a missing attempt-start marker must orient its human judgment")
    amendment_reach_decision = modes["AMENDMENT"].split(
        "A DECISION raised by the sweep", 1)[1].split("Before sending the answer to the fixer", 1)[0]
    check("human-judgment presentation rule" in amendment_reach_decision
          and "product orientation" in amendment_reach_decision,
          "an amendment Reach DECISION must orient its product judgment")
    product_final_trace = modes["PRODUCT REVIEW"].split(
        "Only when the human says the whole feature is done", 1)[1].split(
        "This line must land before the first cleanup gesture", 1)[0]
    check("human-judgment presentation rule" in product_final_trace
          and "workflow orientation" in product_final_trace,
          "PRODUCT REVIEW must preserve final trace orientation")
    duplicate_session = skill_flat.split("several matches", 1)[1].split(
        "One creature mutates", 1)[0]
    check("human-judgment presentation rule" in duplicate_session
          and "workflow orientation" in duplicate_session,
          "duplicate physical owners must orient their human judgment")
    amendment_consolidation = modes["AMENDMENT"].split("Three rounds at most", 1)[1].split(
        "You commit both files", 1)[0]
    check("human-judgment presentation rule" in amendment_consolidation
          and "workflow orientation" in amendment_consolidation,
          "a non-converging amendment consolidation must orient its human judgment")
    spec_scoped_nonconvergence = modes["SPEC"].split(
        "A scoped chain that does not converge", 1)[1].split("Closing the spec", 1)[0]
    check("human-judgment presentation rule" in spec_scoped_nonconvergence
          and "product orientation" in spec_scoped_nonconvergence
          and "workflow orientation" in spec_scoped_nonconvergence
          and "after the Recurring findings classification" in spec_scoped_nonconvergence,
          "a non-converging scoped SPEC chain must select orientation from its classification")


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
    for contract in (checker, implementer, mode):
        check("task-<N>-attempt-<K>-code-risk-filtered.md" in contract,
              "every code-checker consumer must use one attempt-scoped private history")
    check("task-<N>-attempt-<K>-design-risk-filtered.md" in skill
          and "matching `-code-risk-filtered.md` path" in skill,
          "the root contract must name both attempt-scoped checker histories")
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

    check("The CONSTRUCTION design and code checkers do not own a `DECISION` output route" in risk,
          "the shared DECISION route must exclude both strict checker results")
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
        destination = os.path.join(
            WORKSPACE, "prompts", "product-review", "refs-clear.sh",
        )
        shutil.copyfile(os.path.join(PRODUCT_PROMPTS, "refs-clear.sh"), destination)
        os.chmod(destination, 0o755)
        destination = os.path.join(WORKSPACE, "prompts", "amendment", "amendment-commit.sh")
        shutil.copyfile(os.path.join(AMENDMENT_PROMPTS, "amendment-commit.sh"), destination)
        os.chmod(destination, 0o755)
        shutil.copyfile(
            os.path.join(AMENDMENT_PROMPTS, "reviewer-reach-completion.md"),
            os.path.join(WORKSPACE, "prompts", "amendment", "reviewer-reach-completion.md"),
        )
        os.makedirs(os.path.join(WORKSPACE, "prompts", "construction"))
        for name in (
            "gate-check.sh", "gate_file.py", "gate_execution.py", "gate_report.py",
            "construction_review.py", "plan-commit.sh", "attempt-started.sh",
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
