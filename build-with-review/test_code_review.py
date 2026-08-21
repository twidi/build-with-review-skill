#!/usr/bin/env python3
"""Focused tests for the exact construction code-review generation."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback


HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "prompts" / "construction" / "construction_review.py"
TESTS = []


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Fixture:
    def __init__(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="bwr-code-review-test-"))
        self.repo = self.temp / "repo"
        self.workspace = self.repo / ".superpowers" / "bwr" / "2026-08-20-demo"
        (self.workspace / "prompts" / "construction").mkdir(parents=True)
        shutil.copyfile(SOURCE, self.workspace / "prompts" / "construction" / SOURCE.name)
        self.run("git", "init", "-q", cwd=self.repo.parent)
        self.repo.mkdir(exist_ok=True)
        self.run("git", "init", "-q")
        self.run("git", "config", "user.email", "test@example.invalid")
        self.run("git", "config", "user.name", "Code Review Test")
        (self.repo / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "docs" / "plans").mkdir(parents=True)
        self.plan_copy = self.repo / "docs" / "plans" / "2026-08-20-demo-lot-1-plan.md"
        self.plan = self.workspace / "plans" / "lot-1-plan.md"
        self.plan.parent.mkdir(parents=True)
        self.set_plan()
        self.plan_copy.write_bytes(self.plan.read_bytes())
        self.run("git", "add", ".gitignore", "app.py", str(self.plan_copy.relative_to(self.repo)))
        self.run("git", "commit", "-q", "-m", "base")
        self.base = self.run("git", "rev-parse", "HEAD").stdout.strip()

    def close(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def run(self, *args, ok=True, cwd=None, input_text=None):
        result = subprocess.run(
            list(map(str, args)), cwd=cwd or self.repo,
            input=input_text, capture_output=True, text=True, timeout=60,
        )
        if ok is True and result.returncode != 0:
            raise AssertionError(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
        if ok is False and result.returncode == 0:
            raise AssertionError(f"command unexpectedly succeeded: {args}\n{result.stdout}")
        return result

    def helper(self, *args, ok=True, input_text=None):
        return self.run(sys.executable, self.workspace / "prompts" / "construction" / SOURCE.name,
                        *args, ok=ok, input_text=input_text)

    def set_plan(self, *, achieves="Keep the value correct.", design="Set VALUE to 2.",
                 disagreement=None):
        text = (
            "# Plan\n\n## Task 1 - Change value\n"
            f"Achieves: {achieves}\n"
            "To verify: The value is two.\n\n"
            "### Design\n"
            f"{design}\n"
        )
        if disagreement is not None:
            text += f"\n### Disagreement\n{disagreement}\n"
        self.plan.write_text(text, encoding="utf-8")

    def plan_state(self):
        result = self.helper("plan-state", "lot-1", "1")
        return json.loads(result.stdout)

    def stage_candidate(self):
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repo / "created.py").write_text("CREATED = True\n", encoding="utf-8")
        self.run("git", "add", "app.py", "created.py")
        return self.run("git", "write-tree").stdout.strip()

    def manifest(self, tree, *, round_number=1, previous=None):
        result = self.helper(
            "manifest", "lot-1", "1", "1", str(round_number), "a" * 64, self.base, tree,
            input_text=json.dumps(previous) if previous else None,
        )
        return json.loads(result.stdout)


@test
def plan_state_freezes_controller_contract_and_accepted_design_separately():
    fixture = Fixture()
    try:
        original = fixture.plan_state()
        fixture.set_plan(design="Use the neighbouring constant pattern.")
        design_edit = fixture.plan_state()
        check(design_edit["contract_sha256"] == original["contract_sha256"],
              "a Design edit changed the controller-owned task contract")
        check(design_edit["plan_ownership_sha256"] == original["plan_ownership_sha256"],
              "a Design edit changed the whole-plan ownership projection")
        check(design_edit["design_sha256"] != original["design_sha256"],
              "a Design edit did not change the Design generation")

        fixture.set_plan(achieves="Silently weaken the accepted task.")
        contract_edit = fixture.plan_state()
        check(contract_edit["contract_sha256"] != original["contract_sha256"],
              "an Achieves edit did not change the controller-owned contract")

        fixture.set_plan(disagreement="Keep the current valid alternative.")
        projected = fixture.plan_state()
        check(projected["plan_projection_sha256"] == original["plan_projection_sha256"],
              "the documented Disagreement projection changed the frozen plan projection")
        check(projected["plan_ownership_sha256"] == original["plan_ownership_sha256"],
              "the documented Disagreement changed the whole-plan ownership projection")
    finally:
        fixture.close()


@test
def plan_state_refuses_a_task_without_a_design_boundary():
    fixture = Fixture()
    try:
        fixture.plan.write_text(
            "# Plan\n\n## Task 1 - Change value\n"
            "Achieves: Keep the value correct.\n"
            "To verify: The value is two.\n",
            encoding="utf-8",
        )
        result = fixture.helper("plan-state", "lot-1", "1", ok=False)
        check("exactly one ### Design section" in result.stderr, result.stderr)
    finally:
        fixture.close()


@test
def plan_state_ignores_design_headings_inside_markdown_fences():
    fixture = Fixture()
    try:
        for opening, closing in (("```markdown", "```"), ("   ~~~~markdown", "   ~~~~")):
            fixture.plan.write_text(
                "# Plan\n\n## Task 1 - Change value\n"
                "Achieves: Keep the value correct.\n"
                "To verify: The value is two.\n\n"
                f"{opening}\n"
                "### Design\n"
                "This is illustrative data.\n"
                f"{closing}\n",
                encoding="utf-8",
            )
            result = fixture.helper("plan-state", "lot-1", "1", ok=False)
            check("exactly one ### Design section" in result.stderr, result.stderr)

            fixture.plan.write_text(
                fixture.plan.read_text(encoding="utf-8")
                + "\n### Design\n[written at C3.1 - see below]\n",
                encoding="utf-8",
            )
            state = fixture.plan_state()
            check(state["design_sha256"] == hashlib.sha256(
                b"### Design\n[written at C3.1 - see below]\n"
            ).hexdigest(), "a fenced Design heading replaced the structural boundary")
    finally:
        fixture.close()


@test
def plan_state_still_refuses_two_structural_design_boundaries():
    fixture = Fixture()
    try:
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8")
            + "\n### Design\nA second real Design.\n",
            encoding="utf-8",
        )
        result = fixture.helper("plan-state", "lot-1", "1", ok=False)
        check("more than one ### Design section" in result.stderr, result.stderr)
    finally:
        fixture.close()


@test
def plan_state_ignores_fenced_disagreement_and_keeps_the_real_optional_section():
    fixture = Fixture()
    try:
        fixture.set_plan(design=(
            "Use the accepted implementation.\n\n"
            "```markdown\n"
            "### Disagreement\n"
            "This heading is illustrative data.\n"
            "```\n"
            "Keep this sentence inside the Design."
        ))
        without_real = fixture.plan_state()
        check(without_real["disagreement_sha256"] is None,
              "a fenced Disagreement became a structural section")

        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8")
            + "\n### Disagreement\nKeep the accepted alternative.\n",
            encoding="utf-8",
        )
        with_real = fixture.plan_state()
        expected_design = (
            "### Design\n"
            "Use the accepted implementation.\n\n"
            "```markdown\n"
            "### Disagreement\n"
            "This heading is illustrative data.\n"
            "```\n"
            "Keep this sentence inside the Design.\n"
        ).encode("utf-8")
        check(with_real["design_sha256"] == hashlib.sha256(expected_design).hexdigest(),
              "a fenced sibling heading truncated the Design generation")
        check(with_real["disagreement_sha256"] == hashlib.sha256(
            b"### Disagreement\nKeep the accepted alternative.\n"
        ).hexdigest(), "the real optional Disagreement was not preserved")
    finally:
        fixture.close()


@test
def manifest_is_finite_and_supports_byte_bounded_direct_reads():
    fixture = Fixture()
    try:
        large = b"x" * 2_000_000
        (fixture.repo / "large.txt").write_bytes(large)
        fixture.run("git", "add", "large.txt")
        tree = fixture.stage_candidate()
        published = fixture.manifest(tree)
        manifest_path = fixture.workspace / published["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check([item["path"] for item in manifest["files"]] == ["app.py", "created.py", "large.txt"], manifest)
        check([item["id"] for item in manifest["files"]] == [1, 2, 3], manifest)
        count = fixture.helper("count", published["path"])
        check(count.stdout.strip() == "3", count.stdout)
        for item in manifest["files"]:
            described = json.loads(fixture.helper("item", published["path"], str(item["id"])).stdout)
            check(described == item, (described, item))
            diff = b""
            for offset in range(0, item["diff_bytes"], 65_536):
                chunk = fixture.helper(
                    "read", published["path"], str(item["id"]), "diff",
                    str(offset), str(min(65_536, item["diff_bytes"] - offset)),
                )
                diff += chunk.stdout.encode()
            check(len(diff) == item["diff_bytes"], item)
            check(hashlib.sha256(diff).hexdigest() == item["diff_sha256"], item)
            if item["after_sha256"] is not None:
                content = b""
                for offset in range(0, item["file_bytes"], 65_536):
                    chunk = fixture.helper(
                        "read", published["path"], str(item["id"]), "file",
                        str(offset), str(min(65_536, item["file_bytes"] - offset)),
                    )
                    content += chunk.stdout.encode()
                check(len(content) == item["file_bytes"], item)
                check(hashlib.sha256(content).hexdigest() == item["after_sha256"], item)
        fixture.helper("read", published["path"], "3", "file", "0", "65537", ok=False)
    finally:
        fixture.close()


@test
def strict_result_derives_clean_or_exact_contiguous_findings():
    fixture = Fixture()
    try:
        manifest = fixture.manifest(fixture.stage_candidate())
        frozen = json.loads((fixture.workspace / manifest["path"]).read_text(encoding="utf-8"))
        inspected = [
            {
                "id": item["id"], "path": item["path"],
                "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"],
            }
            for item in frozen["files"]
        ]
        report = {
            "verdict": "clean", "manifest": manifest["path"], "inspected": inspected,
            "checks": [
                {"subject": "contract", "evidence": "The changed assignment implements Achieves."},
                {"subject": "assertion", "evidence": "Changing VALUE back to 1 breaks the new test."},
            ],
            "previous": [], "findings": [],
        }
        source = fixture.temp / "clean.json"
        source.write_text(json.dumps(report), encoding="utf-8")
        result = json.loads(fixture.helper("publish-result", manifest["path"], source).stdout)
        check(result["outcome"] == "clean" and result["findings"] == 0, result)
        check((fixture.workspace / result["report"]).is_file(), result)

        omitted = dict(report)
        omitted["inspected"] = inspected[:-1]
        bad = fixture.temp / "omitted.json"
        bad.write_text(json.dumps(omitted), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], bad, ok=False)

        malformed = dict(report)
        malformed["verdict"] = "findings"
        malformed["findings"] = [
            {"id": 2, "where": "app.py:1", "what": "Wrong value",
             "why": "The task fails.", "impact": "IMPORTANT", "previous": []}
        ]
        bad.write_text(json.dumps(malformed), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], bad, ok=False)

        incomplete_clean = dict(report)
        incomplete_clean["checks"] = incomplete_clean["checks"][:1]
        bad.write_text(json.dumps(incomplete_clean), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], bad, ok=False)

        no_assertion = dict(report)
        no_assertion["checks"] = [
            {"subject": "contract", "evidence": "The required value is present."},
            {"subject": "robustness", "evidence": "The boundary rejects invalid input."},
        ]
        bad.write_text(json.dumps(no_assertion), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], bad, ok=False)
    finally:
        fixture.close()


@test
def strict_result_requires_impact_and_derives_exact_impact_counts():
    fixture = Fixture()
    try:
        manifest = fixture.manifest(fixture.stage_candidate())
        frozen = json.loads((fixture.workspace / manifest["path"]).read_text(encoding="utf-8"))
        report = {
            "verdict": "findings", "manifest": manifest["path"],
            "inspected": [
                {"id": item["id"], "path": item["path"],
                 "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"]}
                for item in frozen["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate was compared with Achieves."},
                {"subject": "assertion", "evidence": "Changing VALUE back to 1 breaks the task."},
            ],
            "previous": [],
            "findings": [
                {"id": 1, "where": "app.py:1", "what": "The value is unclear",
                 "why": "The name causes repeated local friction.", "impact": "MINOR", "previous": []},
                {"id": 2, "where": "created.py:1", "what": "The guard is absent",
                 "why": "The task can return an incorrect result.", "impact": "IMPORTANT", "previous": []},
            ],
        }
        source = fixture.temp / "findings.json"
        missing = json.loads(json.dumps(report))
        del missing["findings"][0]["impact"]
        source.write_text(json.dumps(missing), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], source, ok=False)

        invalid = json.loads(json.dumps(report))
        invalid["findings"][0]["impact"] = "LOW"
        source.write_text(json.dumps(invalid), encoding="utf-8")
        fixture.helper("publish-result", manifest["path"], source, ok=False)

        source.write_text(json.dumps(report), encoding="utf-8")
        result = json.loads(fixture.helper("publish-result", manifest["path"], source).stdout)
        check(result["findings"] == 2, result)
        check(result["critical"] == 0 and result["important"] == 1 and result["minor"] == 1,
              result)
    finally:
        fixture.close()


@test
def later_result_must_verify_and_carry_every_still_open_prior_identity():
    fixture = Fixture()
    try:
        prior_relative = "reports/construction/lot-1/prior-result.json"
        prior_path = fixture.workspace / prior_relative
        prior_path.parent.mkdir(parents=True)
        prior_path.write_text("{}\n", encoding="utf-8")
        previous = {
            "source": "round",
            "round": 1,
            "result": prior_relative,
            "result_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
            "findings": [
                {"id": 1, "where": "app.py:1", "what": "VALUE remains wrong",
                 "why": "The task contract fails.", "impact": "CRITICAL"}
            ],
            "resolution": [
                {"id": 1, "status": "corrected", "evidence": "VALUE was changed."}
            ],
            "resolution_proof": f"1:{'b' * 64}",
        }
        published = fixture.manifest(
            fixture.stage_candidate(), round_number=2, previous=previous,
        )
        frozen = json.loads((fixture.workspace / published["path"]).read_text(encoding="utf-8"))
        report = {
            "verdict": "findings", "manifest": published["path"],
            "inspected": [
                {"id": item["id"], "path": item["path"],
                 "diff_sha256": item["diff_sha256"], "after_sha256": item["after_sha256"]}
                for item in frozen["files"]
            ],
            "checks": [
                {"subject": "contract", "evidence": "The candidate was compared with Achieves."},
                {"subject": "assertion", "evidence": "VALUE = 1 still breaks the result."},
            ],
            "previous": [
                {"id": 1, "status": "still-open", "evidence": "The wrong value remains."}
            ],
            "findings": [
                {"id": 1, "where": "app.py:1", "what": "VALUE remains wrong",
                 "why": "The task contract fails.", "impact": "CRITICAL", "previous": [1]}
            ],
        }
        source = fixture.temp / "carried.json"
        report["findings"][0]["impact"] = "IMPORTANT"
        source.write_text(json.dumps(report), encoding="utf-8")
        fixture.helper("publish-result", published["path"], source, ok=False)
        report["findings"][0]["impact"] = "CRITICAL"

        source.write_text(json.dumps(report), encoding="utf-8")
        fixture.helper("publish-result", published["path"], source)

        report["previous"] = []
        report["findings"][0]["previous"] = []
        source.write_text(json.dumps(report), encoding="utf-8")
        fixture.helper("publish-result", published["path"], source, ok=False)
    finally:
        fixture.close()


@test
def final_tree_rejects_a_disagreement_added_after_a_clean_review():
    fixture = Fixture()
    try:
        reviewed_tree = fixture.stage_candidate()
        manifest = fixture.manifest(reviewed_tree)
        fixture.helper("final-tree", manifest["path"], reviewed_tree)

        fixture.set_plan(disagreement="The checker preferred VALUE = 3; both satisfy the contract.")
        fixture.plan_copy.write_bytes(fixture.plan.read_bytes())
        fixture.run("git", "add", str(fixture.plan_copy.relative_to(fixture.repo)))
        final_tree = fixture.run("git", "write-tree").stdout.strip()
        fixture.helper("final-tree", manifest["path"], final_tree, ok=False)

        (fixture.repo / "app.py").write_text("VALUE = 4\n", encoding="utf-8")
        fixture.run("git", "add", "app.py")
        changed_tree = fixture.run("git", "write-tree").stdout.strip()
        fixture.helper("final-tree", manifest["path"], changed_tree, ok=False)
    finally:
        fixture.close()


@test
def round_ten_alternative_preserves_the_exact_design_disagreement_prefix():
    fixture = Fixture()
    try:
        fixture.set_plan(disagreement=(
            "The design checker preferred another placement.\n"
            "The accepted plan permits both placements."
        ))
        base_state = fixture.plan_state()
        manifest = fixture.manifest(fixture.stage_candidate())
        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").rstrip()
            + "\n\n#### Finding 1 — code alternative\n"
              "The code checker preferred another expression. Both satisfy the contract.\n",
            encoding="utf-8",
        )
        resolved = json.loads(fixture.helper(
            "disagreement", "lot-1", "1", base_state["disagreement_sha256"], "1",
        ).stdout)
        fixture.plan_copy.write_bytes(fixture.plan.read_bytes())
        fixture.run("git", "add", str(fixture.plan_copy.relative_to(fixture.repo)))
        final_tree = fixture.run("git", "write-tree").stdout.strip()
        fixture.helper(
            "final-tree", manifest["path"], final_tree, resolved["disagreement_sha256"],
        )

        fixture.plan.write_text(
            fixture.plan.read_text(encoding="utf-8").replace(
                "The design checker preferred another placement.",
                "The design checker history was rewritten.",
            ),
            encoding="utf-8",
        )
        fixture.helper(
            "disagreement", "lot-1", "1", base_state["disagreement_sha256"], "1", ok=False,
        )
    finally:
        fixture.close()


def main():
    failures = 0
    for function in TESTS:
        try:
            function()
            print(f"ok    {function.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {function.__name__}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures} of {len(TESTS)} tests failed")
        raise SystemExit(1)
    print(f"\nall {len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
