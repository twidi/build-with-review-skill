#!/usr/bin/env python3
"""Fast contract tests for child runtime-input handoffs."""
import pathlib
import traceback


HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE / "SKILL.md"
PROMPTS = HERE / "prompts"
TESTS = []


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def read(relative):
    return (HERE / relative).read_text(encoding="utf-8")


def check_runtime_identity(subject, text):
    check("RUNTIME INPUTS" in text, f"{subject} has no fixed runtime-input block")
    for field in ("repository:", "workspace:", "role prompt:"):
        check(field in text, f"{subject} omits {field[:-1]}")
    check("current working directory" in text and "stop before" in text,
          f"{subject} does not refuse cwd fallback before I/O")


def section(relative, start, end):
    text = read(relative)
    check(start in text, f"{relative} has no section marker: {start}")
    body = text.split(start, 1)[1]
    if end is not None:
        check(end in body, f"{relative} has no closing marker after {start}: {end}")
        body = body.split(end, 1)[0]
    return body


@test
def every_child_launch_has_an_explicit_workspace_input():
    launch_sections = [
        ("SPEC reviewer", "prompts/spec/MODE.md", "### S3.2", "### S3.3"),
        ("SPEC fixer", "prompts/spec/MODE.md", "### S3.4", "### S3.5"),
        ("C0 gate runner", "prompts/construction/MODE.md", "### C0.3", "### C0.4"),
        ("completeness checker", "prompts/construction/MODE.md", "## C2", "## C3"),
        ("implementer", "prompts/construction/MODE.md", "### Launching an attempt", "### What comes back"),
        ("diagnostic", "prompts/construction/MODE.md", "When you do not trust the classification", "### C3.9"),
        ("design checker", "prompts/construction/implementer.md", "## Design checker", "## Implement"),
        ("code checker", "prompts/construction/implementer.md", "## Code checker", "## Final gate surface"),
        ("final gate runner", "prompts/construction/implementer.md", "## Final gate surface", "## Commit"),
        ("PRODUCT lens", "prompts/product-review/MODE.md", "### R1.1", "### R1.2"),
        ("finding verifier", "prompts/product-review/MODE.md", "### R2.1", "### R2.2"),
        ("amendment fixer", "prompts/amendment/MODE.md", "### Create the fixer", "## A3"),
        ("reach reviewer", "prompts/amendment/MODE.md", "### Launching it", "### The loop"),
        ("consolidation checker", "prompts/amendment/MODE.md", "## A4", "## Going back"),
        ("controller handover", "prompts/common/handover-to-construction-rules.md", "## The message", "## Once it exists"),
    ]
    for name, relative, start, end in launch_sections:
        body = section(relative, start, end)
        check("workspace path" in body or "<workspace>" in body,
              f"{name} launch does not pass an explicit workspace path")

    watchdog = read("prompts/common/watchdog-prompt.md")
    check("<WORKSPACE>" in watchdog, "watchdog launch does not pass its workspace")


@test
def shared_runtime_contract_forbids_a_working_directory_fallback():
    skill = SKILL.read_text(encoding="utf-8")
    worker = read("prompts/common/worker.md")
    for subject, text in (("SKILL.md", skill), ("worker.md", worker)):
        check("RUNTIME INPUTS" in text, f"{subject} has no fixed RUNTIME INPUTS contract")
        check("repository" in text and "workspace" in text and "role prompt" in text,
              f"{subject} omits a universal runtime input")
        check("current working directory" in text and "stop before reading or writing" in text,
              f"{subject} does not refuse a missing workspace before side effects")


@test
def gate_runner_requires_the_exact_workspace_and_output_path():
    prompt = read("prompts/construction/gate-runner.md")
    c0 = section("prompts/construction/MODE.md", "### C0.3", "### C0.4")
    final = section("prompts/construction/implementer.md", "## Final gate surface", "## Commit")

    for subject, text in (("gate-runner.md", prompt), ("C0 launch", c0), ("final gate launch", final)):
        check("RUNTIME INPUTS" in text, f"{subject} has no fixed runtime-input block")
        check("workspace" in text and "role prompt" in text,
              f"{subject} does not bind the workspace and role prompt")

    check("report: none" in c0, "first gate discovery does not explicitly forbid an artifact")
    for subject, text in (("gate-runner.md", prompt), ("C0 launch", c0), ("final gate launch", final)):
        check("reports/gate/<op>.json" in text,
              f"{subject} does not carry the exact op-scoped report path")
        check("gate-check.sh verify <op>" in text,
              f"{subject} does not carry the exact verification command")


@test
def closed_form_session_messages_carry_the_complete_runtime_identity():
    implementer_launch = section(
        "prompts/construction/MODE.md", "### Launching an attempt", "### What comes back"
    )
    handover = section(
        "prompts/common/handover-to-construction-rules.md", "## The message", "## Once it exists"
    )
    handover_rules = read("prompts/common/handover-to-construction-rules.md")
    watchdog = read("prompts/common/watchdog-prompt.md")
    skill_watchdog = section("SKILL.md", "## The watchdog", "## The journal")

    for subject, text in (
        ("implementer launch", implementer_launch),
        ("controller handover message", handover),
        ("watchdog whole prompt", watchdog),
    ):
        check_runtime_identity(subject, text)

    check("project" in implementer_launch and "explicit" in implementer_launch,
          "implementer create_session does not carry the exact project explicitly")
    check("project" in handover_rules and "passed explicitly" in handover_rules,
          "controller handover does not carry the exact project explicitly")
    check("project" in skill_watchdog and "explicit" in skill_watchdog,
          "watchdog create_session does not carry the exact project explicitly")


def main():
    failures = []
    for function in TESTS:
        try:
            function()
        except Exception:
            failures.append((function.__name__, traceback.format_exc()))
    if failures:
        for name, details in failures:
            print(f"FAIL {name}\n{details}")
        raise SystemExit(1)
    print(f"all {len(TESTS)} child-launch tests passed")


if __name__ == "__main__":
    main()
