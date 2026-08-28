#!/usr/bin/env python3
"""Fast contract tests for child runtime-input handoffs."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback


HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE / "SKILL.md"
PROMPTS = HERE / "prompts"
ADDITIONAL_PROMPT_HELPER = PROMPTS / "common" / "additional-prompt.py"
TESTS = []


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def read(relative):
    return (HERE / relative).read_text(encoding="utf-8")


def additional_prompt_call(workspace, command, role_prompt, additional_prompt, source=None):
    arguments = [
        sys.executable,
        str(workspace / "prompts" / "common" / "additional-prompt.py"),
        command,
        str(workspace),
        str(role_prompt),
        str(additional_prompt),
    ]
    if source is not None:
        arguments.append(str(source))
    return subprocess.run(arguments, capture_output=True, check=False)


def global_prompt_call(workspace, command, global_prompt, source=None):
    arguments = [
        sys.executable,
        str(workspace / "prompts" / "common" / "additional-prompt.py"),
        command,
        str(workspace),
        str(global_prompt),
    ]
    if source is not None:
        arguments.append(str(source))
    return subprocess.run(arguments, capture_output=True, check=False)


def additional_prompt_workspace(root):
    workspace = root / "workspace"
    helper = workspace / "prompts" / "common" / "additional-prompt.py"
    role_prompt = workspace / "prompts" / "construction" / "implementer.md"
    additional_prompt = workspace / "additional-prompts" / "construction" / "implementer.md"
    helper.parent.mkdir(parents=True)
    role_prompt.parent.mkdir(parents=True)
    (workspace / "additional-prompts").mkdir()
    shutil.copy2(ADDITIONAL_PROMPT_HELPER, helper)
    role_prompt.write_text("official role\n", encoding="utf-8")
    return workspace, role_prompt, additional_prompt


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
def session_creation_visibility_keeps_one_exact_child_identity():
    skill = " ".join(SKILL.read_text(encoding="utf-8").split())
    product = " ".join(read("prompts/product-review/MODE.md").split())
    journal = " ".join(read("prompts/common/progress-rules.md").split())

    for subject, text in (
        ("shared root", skill),
        ("journal caller contract", journal),
        ("PRODUCT lens launch", product),
    ):
        check("session-started" in text and "visibility" in text,
              f"{subject} does not assign the post-creation visibility boundary")
        check("returned id" in text and "replacement" in text,
              f"{subject} does not preserve the exact created child identity")


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

    direct_runtime_contracts = [
        ("SKILL.md", skill),
        ("worker.md", worker),
        ("implementer.md", read("prompts/construction/implementer.md")),
        ("gate-runner.md", read("prompts/construction/gate-runner.md")),
        ("watchdog-prompt.md", read("prompts/common/watchdog-prompt.md")),
        ("handover", read("prompts/common/handover-to-construction-rules.md")),
        ("construction launch", read("prompts/construction/MODE.md")),
    ]
    ambiguous_absence_rules = (
        "if one value is absent",
        "if one field is absent",
        "if one is absent",
        "when one value is absent",
        "one runtime input is absent",
    )
    for subject, text in direct_runtime_contracts:
        normalized = " ".join(text.lower().split())
        for stale in ambiguous_absence_rules:
            check(stale not in normalized,
                  f"{subject} confuses a missing input value with an absent optional file: {stale}")


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
        check("operation: <op>" in text,
              f"{subject} does not carry the sole operation-specific input")
        check("gate-check.sh runner-input <op>" in text,
              f"{subject} does not derive the exact gate-runner input")
        check("gate-check.sh publish-report <op>" in text,
              f"{subject} does not use mechanical report publication")
    for subject, text in (("C0 launch", c0), ("final gate launch", final)):
        check("only this operation-specific input" in text,
              f"{subject} does not limit the launch message to the operation")
        check("report: <workspace>/reports/gate/<op>.json" not in text,
              f"{subject} still asks the controller to transcribe the report path")
        check("verify: bash <workspace>" not in text,
              f"{subject} still asks the controller to transcribe the verify command")


@test
def gate_runner_corrects_one_local_helper_invocation_without_replacement():
    prompt = read("prompts/construction/gate-runner.md")
    c0 = section("prompts/construction/MODE.md", "### C0.3", "### C0.4")
    final = section("prompts/construction/implementer.md", "## Final gate surface", "## Commit")

    for subject, text in (("gate-runner.md", prompt), ("C0 launch", c0), ("final gate launch", final)):
        normalized = " ".join(text.lower().split())
        check("correct only that invocation once" in normalized,
              f"{subject} does not require one bounded local invocation correction")
        check("same live gate runner" in normalized and "same physical bracket" in normalized,
              f"{subject} replaces the live gate runner for its own invocation error")
        check("does not consume a replacement" in normalized,
              f"{subject} charges a local invocation correction as a replacement")
        check("exact corrected invocation" in normalized and "blocker" in normalized,
              f"{subject} does not stop after the corrected authoritative invocation refuses")


@test
def product_verifier_corrects_local_path_transcription_without_physical_relaunch():
    prompt = read("prompts/product-review/verifier.md")
    launch = section("prompts/product-review/MODE.md", "### R2.1", "### R2.2")
    normalized_prompt = " ".join(prompt.lower().split())
    normalized_launch = " ".join(launch.lower().split())

    check("opaque authoritative path" in normalized_prompt,
          "the verifier does not treat verify-open stdout as authoritative path data")
    check("reuse it exactly" in normalized_prompt and "never reconstruct" in normalized_prompt,
          "the verifier can reconstruct the verification-copy path")
    check("before you use its result" in normalized_prompt,
          "the verifier does not compare each proof command before using a successful result")
    check("different locally derived copy path and fails" not in normalized_prompt,
          "the verifier limits copy-path correction to failed commands")
    check("correct only that local invocation once" in normalized_prompt,
          "the verifier does not correct one local copy-path transcription error")
    check("same live verifier" in normalized_prompt and "same physical bracket" in normalized_prompt,
          "the verifier replaces itself for a local copy-path transcription error")
    check("do not close the copy" in normalized_prompt and "before this correction" in normalized_prompt,
          "the verifier can destroy its copy before correcting its local command")
    check("before you invoke `verify-open.sh` or `verify-close.sh`" in normalized_prompt,
          "the verifier does not compare its open and close helper invocations before execution")
    check("reviewed commit and report file name" in normalized_prompt,
          "the verifier does not bind open and close helpers to their authoritative values")
    check("correct only that helper invocation once" in normalized_prompt,
          "the verifier cannot correct its own open or close helper invocation")

    check("compare the invocation you issued" in normalized_launch,
          "the verifier launch does not require comparison with authoritative runtime inputs")
    check("before you use its stdout" in normalized_launch,
          "the verifier launch does not compare the helper invocation before successful stdout use")
    check("before you treat an additional-prompt helper refusal" not in normalized_launch,
          "the verifier launch limits helper comparison to refused invocations")
    check("correct only that invocation once" in normalized_launch,
          "the verifier launch does not correct one additional-prompt invocation error")
    check("same live verifier" in normalized_launch and "same physical bracket" in normalized_launch,
          "the verifier launch replaces the physical call for its own helper invocation error")
    check("does not consume the one physical verifier regeneration" in normalized_launch,
          "the verifier launch charges a local helper correction as physical regeneration")
    check("exact corrected invocation" in normalized_launch and "blocker" in normalized_launch,
          "the verifier launch does not stop after an authoritative corrected helper refusal")
    check("verify-open.sh" in normalized_launch and "verify-close.sh" in normalized_launch,
          "the verifier launch correction does not propagate to its open and close helpers")


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


@test
def correction_c3_launches_carry_the_exact_work_unit_form():
    launch = section(
        "prompts/construction/MODE.md", "### Launching an attempt", "### What comes back"
    )
    ordinary_annotations = launch.split(
        "#### Ordinary implementer launch annotations", 1,
    )[1].split("#### Correction implementer launch annotations", 1)[0]
    correction_annotations = launch.split(
        "#### Correction implementer launch annotations", 1,
    )[1].split("The message starts with this fixed block", 1)[0]
    ordinary_inputs = launch.split(
        "#### Ordinary implementer role inputs", 1,
    )[1].split("#### Correction implementer role inputs", 1)[0]
    correction_inputs = launch.split(
        "#### Correction implementer role inputs", 1,
    )[1].split("#### Retry inputs for both forms", 1)[0]

    check("`bwr.correction` is absent" in ordinary_annotations,
          "the ordinary implementer annotations admit a Correction identity")
    check("`bwr.correction=<round>`" in correction_annotations,
          "the Correction implementer annotations omit the round")
    check("work-unit form `ordinary`" in ordinary_inputs,
          "the ordinary implementer message omits its work-unit form")
    check("complete canonical resolver JSON account" in correction_inputs
          and "work-unit form `Correction`" in correction_inputs,
          "the Correction implementer message omits its complete resolver authority")
    for field in ("workspace_document", "report_root", "ref_root"):
        check(f"`{field}`" in correction_inputs,
              f"the Correction implementer message omits resolved {field}")
    for forbidden in ("<workspace>/plans/<lot>-plan.md", "task-diff.sh", "paths from the lot"):
        check(forbidden not in correction_inputs,
              f"the Correction implementer message infers an ordinary path: {forbidden}")
    check("<workspace>/plans/<lot>-plan.md" in ordinary_inputs and "task-diff.sh" in ordinary_inputs,
          "the ordinary implementer message lost its ordinary path contract")

    for checker, end in (("Design checker", "## Implement"),
                         ("Code checker", "## Final gate surface")):
        body = section("prompts/construction/implementer.md", f"## {checker}", end)
        check("work-unit form `ordinary` or `Correction`" in body,
              f"the actual {checker} launch omits the explicit work-unit form")
        check("manifest path" in body and "private history" in body and "occurrence label" in body,
              f"the actual {checker} launch lost a frozen checker input")


@test
def every_child_launch_carries_its_one_exact_additional_prompt():
    launch_sections = [
        ("SPEC reviewer", "prompts/spec/MODE.md", "### S3.2", "### S3.3",
         "<workspace>/additional-prompts/spec/reviewer-<slug>.md"),
        ("SPEC fixer", "prompts/spec/MODE.md", "### S3.4", "### S3.5",
         "<workspace>/additional-prompts/spec/fixer.md"),
        ("C0 gate runner", "prompts/construction/MODE.md", "### C0.3", "### C0.4",
         "<workspace>/additional-prompts/construction/gate-runner.md"),
        ("completeness checker", "prompts/construction/MODE.md", "## C2", "## C3",
         "<workspace>/additional-prompts/construction/completeness.md"),
        ("implementer", "prompts/construction/MODE.md", "### Launching an attempt", "### What comes back",
         "<workspace>/additional-prompts/construction/implementer.md"),
        ("diagnostic", "prompts/construction/MODE.md", "When you do not trust the classification", "### C3.9",
         "<workspace>/additional-prompts/construction/diagnostic.md"),
        ("design checker", "prompts/construction/implementer.md", "## Design checker", "## Implement",
         "<workspace>/additional-prompts/construction/design-checker.md"),
        ("code checker", "prompts/construction/implementer.md", "## Code checker", "## Final gate surface",
         "<workspace>/additional-prompts/construction/code-checker.md"),
        ("final gate runner", "prompts/construction/implementer.md", "## Final gate surface", "## Commit",
         "<workspace>/additional-prompts/construction/gate-runner.md"),
        ("PRODUCT lens", "prompts/product-review/MODE.md", "### R1.1", "### R1.2",
         "<workspace>/additional-prompts/product-review/lens-<slug>.md"),
        ("finding verifier", "prompts/product-review/MODE.md", "### R2.1", "### R2.2",
         "<workspace>/additional-prompts/product-review/verifier.md"),
        ("amendment fixer", "prompts/amendment/MODE.md", "### Create the fixer", "## A3",
         "<workspace>/additional-prompts/spec/fixer.md"),
        ("reach reviewer", "prompts/amendment/MODE.md", "### Launching it", "### The loop",
         "<workspace>/additional-prompts/amendment/reviewer-reach.md"),
        ("consolidation checker", "prompts/amendment/MODE.md", "## A4", "## Going back",
         "<workspace>/additional-prompts/amendment/consolidation.md"),
        ("controller handover", "prompts/common/handover-to-construction-rules.md", "## The message", "## Once it exists",
         "<workspace>/additional-prompts/construction/MODE.md"),
    ]
    for name, relative, start, end, expected in launch_sections:
        body = section(relative, start, end)
        check(expected in body, f"{name} launch omits its exact additional prompt")
        check("additional-prompt.py read" in body,
              f"{name} launch does not use the physical additional-prompt reader")

    watchdog = read("prompts/common/watchdog-prompt.md")
    check("<WORKSPACE>/additional-prompts/common/watchdog-prompt.md" in watchdog,
          "watchdog launch omits its exact additional prompt")
    check("additional-prompt.py read" in watchdog,
          "watchdog launch does not use the physical additional-prompt reader")


@test
def additional_prompt_contract_is_optional_exact_and_workspace_owned():
    skill = SKILL.read_text(encoding="utf-8")
    worker = read("prompts/common/worker.md")
    workspace_init = read("prompts/common/workspace-init.sh")

    for subject, text in (("SKILL.md", skill), ("worker.md", worker)):
        check("additional prompt:" in text, f"{subject} omits the additional-prompt input")
        check("additional-prompts" in text and "after" in text,
              f"{subject} does not order the additional prompt after official prompts")
        check("absent" in text and "no other" in text,
              f"{subject} does not define the one-path absent behavior")
        check("additional-prompt.py read" in text,
              f"{subject} does not require the shared physical reader")

    check("additional-prompt.py publish" in skill and "additional-prompt.py remove" in skill,
          "SKILL.md does not route controller mutations through the shared helper")

    check("additional-prompts" in workspace_init,
          "workspace-init.sh does not create the additional-prompts root")


@test
def every_launch_reads_the_global_prompt_before_its_role_prompt():
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

    def check_human_instruction_wording(name, body):
        normalized = " ".join(body.replace("\n> ", " ").lower().split())
        check("read the global additional prompt through" in normalized,
              f"{name} launch describes the global prompt as an executable action")
        check("treat its stdout as human instructions" in normalized,
              f"{name} launch does not classify global stdout as human instructions")
        check("read the role-specific additional prompt through" in normalized,
              f"{name} launch describes the role prompt as an executable action")
        check("follow both instruction sets" in normalized,
              f"{name} launch does not keep both instruction sets active")
        check("role-specific instruction wins on contradiction" in normalized,
              f"{name} launch does not preserve role-specific precedence")
        check("required absolute path values" in normalized,
              f"{name} launch does not require both additional-prompt path inputs")
        check("absent input means that the input field has no value" in normalized,
              f"{name} launch leaves absent input ambiguous with an absent optional file")
        check("it never means that an optional prompt file or its parent directory is absent" in normalized,
              f"{name} launch lets an absent optional file trigger the generic input refusal")
        check("copy this complete rule without shortening or paraphrasing it" in normalized,
              f"{name} launch permits a partial or paraphrased prompt-lookup rule")
        check("their files may be absent" in normalized,
              f"{name} launch wrongly permits requiring optional prompt files to exist")
        check("always call both helpers" in normalized,
              f"{name} launch permits skipping an additional-prompt lookup")
        check("empty stdout is valid absence and never a blocker" in normalized,
              f"{name} launch does not make proven absence non-blocking")
        check("only a helper refusal blocks" in normalized,
              f"{name} launch does not give the helper sole classification authority")
        check("never test either file directly" in normalized,
              f"{name} launch permits a direct existence test")
        check("validate every runtime path" not in normalized,
              f"{name} launch contains the ambiguous generic runtime-path instruction")

    for name, relative, start, end in launch_sections:
        body = section(relative, start, end)
        check("additional-prompts/global.md" in body,
              f"{name} launch omits the global additional prompt")
        check("additional-prompt.py read-global" in body,
              f"{name} launch does not use the global physical reader")
        check("additional-prompt.py read " in body,
              f"{name} launch lost its role-specific physical reader")
        check(body.index("additional-prompt.py read-global") < body.index("additional-prompt.py read "),
              f"{name} launch does not read global before role-specific instructions")
        check_human_instruction_wording(name, body)

    watchdog = read("prompts/common/watchdog-prompt.md")
    check("additional-prompts/global.md" in watchdog,
          "watchdog launch omits the global additional prompt")
    check("additional-prompt.py read-global" in watchdog,
          "watchdog launch does not use the global physical reader")
    check(watchdog.index("additional-prompt.py read-global")
          < watchdog.index("additional-prompt.py read "),
          "watchdog does not read global before role-specific instructions")
    check_human_instruction_wording("watchdog", watchdog)

    skill = SKILL.read_text(encoding="utf-8")
    worker = read("prompts/common/worker.md")
    for subject, text in (("SKILL.md", skill), ("worker.md", worker)):
        check("additional-prompts/global.md" in text,
              f"{subject} omits the global additional prompt")
        check("additional-prompt.py read-global" in text,
              f"{subject} does not use the global physical reader")
        check("official" in text and "role" in text,
              f"{subject} does not define official/global/role reading order")
        check_human_instruction_wording(subject, text)

    check("additional-prompt.py publish-global" in skill
          and "additional-prompt.py remove-global" in skill,
          "SKILL.md does not route global prompt mutations through the shared helper")


@test
def global_additional_prompt_uses_the_shared_physical_owner():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        workspace, _, _ = additional_prompt_workspace(root / "global")
        global_prompt = workspace / "additional-prompts" / "global.md"

        result = global_prompt_call(workspace, "read-global", global_prompt)
        check(result.returncode == 0 and result.stdout == b"",
              f"ordinary global-prompt absence refused: {result.stderr!r}")

        source = root / "global-source.md"
        source_bytes = b"instruction for every future actor\nEOF\n$(touch must-not-run)\n"
        source.write_bytes(source_bytes)
        result = global_prompt_call(workspace, "publish-global", global_prompt, source)
        check(result.returncode == 0, f"ordinary global-prompt publish refused: {result.stderr!r}")
        result = global_prompt_call(workspace, "read-global", global_prompt)
        check(result.returncode == 0 and result.stdout == source_bytes,
              "the global additional prompt did not travel byte-for-byte")
        result = global_prompt_call(workspace, "remove-global", global_prompt)
        check(result.returncode == 0 and not global_prompt.exists(),
              f"ordinary global-prompt removal refused: {result.stderr!r}")

        external = root / "global-external-sentinel.md"
        sentinel = b"global external sentinel\n"
        external.write_bytes(sentinel)
        global_prompt.symlink_to(external)
        for command in ("read-global", "publish-global", "remove-global"):
            result = global_prompt_call(
                workspace,
                command,
                global_prompt,
                source if command == "publish-global" else None,
            )
            check(result.returncode != 0, f"{command} accepted a global-prompt alias")
            check(external.read_bytes() == sentinel,
                  f"{command} changed the global prompt's external target")


@test
def additional_prompt_helper_owns_every_physical_read_and_mutation():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)

        workspace, role_prompt, additional_prompt = additional_prompt_workspace(root / "absent")
        result = additional_prompt_call(workspace, "read", role_prompt, additional_prompt)
        check(result.returncode == 0 and result.stdout == b"",
              f"ordinary additional-prompt absence refused: {result.stderr!r}")

        source = root / "source.md"
        source_bytes = b"runtime instruction\nEOF\n$(touch must-not-run)\n"
        source.write_bytes(source_bytes)
        result = additional_prompt_call(
            workspace, "publish", role_prompt, additional_prompt, source
        )
        check(result.returncode == 0, f"ordinary additional-prompt publish refused: {result.stderr!r}")
        result = additional_prompt_call(workspace, "read", role_prompt, additional_prompt)
        check(result.returncode == 0 and result.stdout == source_bytes,
              "a real additional prompt did not travel byte-for-byte")
        result = additional_prompt_call(workspace, "remove", role_prompt, additional_prompt)
        check(result.returncode == 0 and not additional_prompt.exists(),
              f"ordinary additional-prompt removal refused: {result.stderr!r}")

        for case, leaf_target in (("leaf-alias", True), ("dangling-alias", False)):
            workspace, role_prompt, additional_prompt = additional_prompt_workspace(root / case)
            additional_prompt.parent.mkdir()
            external = root / f"{case}-external.md"
            if leaf_target:
                external.write_text("external\n", encoding="utf-8")
            additional_prompt.symlink_to(external)
            result = additional_prompt_call(workspace, "read", role_prompt, additional_prompt)
            check(result.returncode != 0,
                  f"the {case} was accepted as an additional prompt")

        workspace, role_prompt, additional_prompt = additional_prompt_workspace(root / "parent-alias")
        external_parent = root / "external-parent"
        external_parent.mkdir()
        (external_parent / "implementer.md").write_text("external\n", encoding="utf-8")
        additional_prompt.parent.symlink_to(external_parent, target_is_directory=True)
        result = additional_prompt_call(workspace, "read", role_prompt, additional_prompt)
        check(result.returncode != 0,
              "an intermediate directory alias was accepted as workspace-owned")

        workspace, role_prompt, additional_prompt = additional_prompt_workspace(root / "publish-alias")
        additional_prompt.parent.mkdir()
        external = root / "external-sentinel.md"
        sentinel = b"external sentinel\n"
        external.write_bytes(sentinel)
        additional_prompt.symlink_to(external)
        result = additional_prompt_call(
            workspace, "publish", role_prompt, additional_prompt, source
        )
        check(result.returncode != 0, "publish followed an exact-leaf alias")
        check(external.read_bytes() == sentinel,
              "a refused additional-prompt update changed its external target")
        result = additional_prompt_call(workspace, "remove", role_prompt, additional_prompt)
        check(result.returncode != 0, "remove accepted an exact-leaf alias")
        check(external.read_bytes() == sentinel and additional_prompt.is_symlink(),
              "a refused additional-prompt removal changed its external target")


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
