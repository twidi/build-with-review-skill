# Main Test Suite Repair and Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a green current-main test baseline and make every complete suite finish within ten minutes.

**Architecture:** Repair stale fixtures before changing runtime. Add functional timing to the two slow runners, then replace repeated end-to-end setup with bounded seeds and exact-prefix in-process projection where evidence shows repeated history replay. Keep real public helpers for filesystem, lock, marker, process, Git, and recovery boundaries.

**Tech Stack:** Python 3 standard library, Bash, Git, append-only JSONL projectors.

**Spec:** `build-with-review/docs/superpowers/specs/2026-08-28-main-test-suite-design.md`

## Global Constraints

- Do not modify `main`, `feat/correction-rounds`, or the suspended integration branch.
- Do not push, merge, or deploy.
- No individual test or complete suite can run for ten minutes.
- Do not split one slow end-to-end workflow into several near-ten-minute tests.
- Use real production projectors for every normalized authority seed.
- Keep one minimal real-process smoke test for each external boundary.
- Do not run benchmark-only commands.
- Collect duration data during functional verification.
- Change runtime only after one focused RED proves a runtime defect.

---

### Task 1: Repair the gate fixture baseline

**Files:**
- Modify: `build-with-review/test_gate.py`
- Test: `build-with-review/test_gate.py`

**Interfaces:**
- Consumes: `Fixture.workspace`, the fail-closed journal admission in `gate-check.sh`, and exact retained checker-opening recovery.
- Produces: a valid empty journal for every gate fixture and current recovery expectations.

- [ ] **Step 1: Keep the existing missing-journal failure as RED.**

  Run:

  ```bash
  BWR_TEST_FILTER=logical_gate_freezes_and_consumes_the_semantic_parallel_schedule \
    python3 build-with-review/test_gate.py
  ```

  Expected: FAIL because `progress.jsonl` does not exist.

- [ ] **Step 2: Create the minimum valid journal in `Fixture.__init__`.**

  Add this after `self.workspace.mkdir(parents=True)`:

  ```python
  (self.workspace / "progress.jsonl").write_bytes(b"")
  ```

- [ ] **Step 3: Verify the focused gate test.**

  Run the Step 1 command.

  Expected: PASS.

- [ ] **Step 4: Align the lost-live-repair test with exact retained recovery.**

  Replace the stale `ok=False` rerun assertion with an exact idempotent success assertion.

  Require zero journal delta and the same `call`, `manifest`, `tree`, and gate values.

- [ ] **Step 5: Run the two focused tests.**

  ```bash
  BWR_TEST_FILTER=logical_gate_freezes_and_consumes_the_semantic_parallel_schedule \
    python3 build-with-review/test_gate.py
  BWR_TEST_FILTER=unusable_code_result_regenerates_the_same_logical_round_without_another_spend \
    python3 build-with-review/test_gate.py
  ```

- [ ] **Step 6: Commit the fixture repair.**

  ```bash
  git add build-with-review/test_gate.py
  git commit -m "test(gate): align fixtures with current authority"
  ```

### Task 2: Add functional duration reports

**Files:**
- Modify: `build-with-review/test_gate.py`
- Modify: `build-with-review/test_progress.py`

**Interfaces:**
- Consumes: each file's ordered `TESTS` registry.
- Produces: deterministic per-test elapsed output and one sorted slow-test report.

- [ ] **Step 1: Add a runner self-test for duration output.**

  Add a small pure helper in each file:

  ```python
  def format_slowest_tests(durations, limit=10):
      return [f"{seconds:.3f}s {name}" for seconds, name in sorted(durations, reverse=True)[:limit]]
  ```

  Add one registered pure test that gives `[(0.2, "fast"), (1.5, "slow")]` and requires `"1.500s slow"` first.

- [ ] **Step 2: Run each new pure test as RED.**

  Use `BWR_TEST_FILTER=format_slowest_tests_orders_descending` for each suite.

  Expected: FAIL before the helper exists.

- [ ] **Step 3: Measure every existing functional test.**

  Wrap each `function()` call with `time.monotonic()`.

  Print `ok <duration>s <name>` or `FAIL <duration>s <name>`.

  Print the ten slowest tests after the result count.

- [ ] **Step 4: Verify both pure tests and syntax.**

  ```bash
  python3 -m py_compile build-with-review/test_gate.py build-with-review/test_progress.py
  BWR_TEST_FILTER=format_slowest_tests_orders_descending python3 build-with-review/test_gate.py
  BWR_TEST_FILTER=format_slowest_tests_orders_descending python3 build-with-review/test_progress.py
  ```

- [ ] **Step 5: Commit the timing harness.**

  ```bash
  git add build-with-review/test_gate.py build-with-review/test_progress.py
  git commit -m "test: report slow workflow cases"
  ```

### Task 3: Bound retained task-success gate tests

**Files:**
- Modify: `build-with-review/test_gate.py`
- Test: `build-with-review/test_gate.py`

**Interfaces:**
- Consumes: real `attempt_success.py`, `attempt-succeeded.sh`, gate marker, stable ref, journal lock, and recovery account.
- Produces: one shared bounded success prefix and independent phase mutations.

- [ ] **Step 1: Run the complete gate suite once with a 590-second hard limit.**

  ```bash
  timeout -k 5s 590s env PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    python3 build-with-review/test_gate.py
  ```

  Use the functional duration report to confirm the retained task-success family dominates wall time.

- [ ] **Step 2: Extract `seed_task_success_authority()`.**

  The helper must create only:

  ```python
  {
      "attempt_start": exact_start_account,
      "gate": exact_final_gate_account,
      "commit": full_commit_sha,
      "stable_ref": canonical_task_ref,
  }
  ```

  Derive `exact_start_account` and `exact_final_gate_account` through the copied production `progress.py` module.

- [ ] **Step 3: Replace repeated full setup in `task_success_*` tests.**

  Keep public real-process calls for:

  ```text
  attempt-succeeded.sh
  attempt_success.py phase continuation
  concurrent exact reruns
  stable-ref publication
  marker replacement and cleanup
  ```

  Do not rerun plan publication, Design review, code review, or physical gate execution unless that test asserts that boundary.

- [ ] **Step 4: Verify the full `task_success_` family.**

  ```bash
  timeout -k 5s 590s env PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    BWR_TEST_FILTER=task_success_ python3 build-with-review/test_gate.py
  ```

  Expected: all selected tests pass. The family completes below 120 seconds.

- [ ] **Step 5: Commit the bounded gate fixtures.**

  ```bash
  git add build-with-review/test_gate.py
  git commit -m "test(gate): bound task success recovery fixtures"
  ```

### Task 4: Add an exact in-process progress runner

**Files:**
- Modify: `build-with-review/test_progress.py`
- Test: `build-with-review/test_progress.py`

**Interfaces:**
- Consumes: copied `progress.py`, `build_parser()`, `COMMAND_VALIDATION_CACHE`, `ENV`, and the shared journal.
- Produces: `in_process_progress_runner(retain_validation_cache=False)` returning `subprocess.CompletedProcess` values.

- [ ] **Step 1: Write the runner parity RED.**

  Add `in_process_runner_matches_real_note_and_refusal_results`.

  It must compare a real-process and in-process `note ruling` success on reset-equivalent prefixes.

  It must also compare a malformed `--data` refusal.

- [ ] **Step 2: Run the parity RED.**

  ```bash
  BWR_TEST_FILTER=in_process_runner_matches_real_note_and_refusal_results \
    python3 build-with-review/test_progress.py
  ```

  Expected: FAIL because `in_process_progress_runner` does not exist.

- [ ] **Step 3: Implement the runner.**

  Load the copied module once.

  Parse each call with `build_parser()`.

  Redirect stdout and stderr to `io.StringIO`.

  Set `COMMAND_VALIDATION_CACHE` to a fresh dict per command by default.

  When `retain_validation_cache=True`, keep one dict but reuse a validation only when its exact-prefix key and entries-object identity remain valid.

  Restore `os.environ`, `sys.argv`, and `COMMAND_VALIDATION_CACHE` in `finally` blocks.

- [ ] **Step 4: Verify parity and cold replay.**

  ```bash
  BWR_TEST_FILTER=in_process_runner_matches_real_note_and_refusal_results \
    python3 build-with-review/test_progress.py
  BWR_TEST_FILTER=construction_history_ python3 build-with-review/test_progress.py
  ```

- [ ] **Step 5: Commit the runner.**

  ```bash
  git add build-with-review/test_progress.py
  git commit -m "test(progress): add exact in-process command runner"
  ```

### Task 5: Replace repeated long progress setup

**Files:**
- Modify: `build-with-review/test_progress.py`
- Test: `build-with-review/test_progress.py`

**Interfaces:**
- Consumes: `in_process_progress_runner()`, existing `seed_*` helpers, and production historical validators.
- Produces: bounded Design, code, Product, AMENDMENT, gate, and attempt fixture families.

- [ ] **Step 1: Run the complete progress suite once with a 590-second hard limit.**

  ```bash
  timeout -k 5s 590s env PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    python3 build-with-review/test_progress.py
  ```

  Keep the functional failures and duration output. Do not rerun solely for timing.

- [ ] **Step 2: Convert setup-only command loops to the in-process runner.**

  Pass a runner into these existing setup families:

  ```text
  seed_active_attempt
  drive_design_to_round_ten
  resolve_design_round
  seed_review_gate
  seed_review_pass
  seed_committed_construction_attempt_with_spec
  ```

  Default each helper to the real `run_progress` function.

  Slow consumers pass one retained exact-prefix runner explicitly.

- [ ] **Step 3: Replace full predecessor workflows with normalized seeds.**

  For each slow test, seed the exact durable predecessor through the production validator that the tested command consumes.

  Keep public real-process execution for the command named by the test.

- [ ] **Step 4: Verify each changed family before the complete suite.**

  Use one `BWR_TEST_FILTER` value matching the actual behavior family.

  Each selected family must finish below 120 seconds unless it contains an external concurrency smoke test.

- [ ] **Step 5: Commit each independent fixture family.**

  Use one `test(progress): bound <authority> fixtures` commit per authority family.

### Task 6: Complete bounded verification

**Files:**
- Verify: all `build-with-review/test_*.py` suites.
- Verify: changed Python and Bash files.

**Interfaces:**
- Consumes: the complete bugfix branch.
- Produces: one green, measured local generation.

- [ ] **Step 1: Run every suite with a 590-second hard limit.**

  Run each existing suite once.

  Independent suites can run concurrently.

- [ ] **Step 2: Run syntax checks.**

  ```bash
  python3 -m py_compile build-with-review/test_*.py build-with-review/prompts/common/*.py \
    build-with-review/prompts/construction/*.py
  find build-with-review/prompts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
  git diff --check
  ```

- [ ] **Step 3: Confirm repository boundaries.**

  Confirm `main`, `feat/correction-rounds`, and `feature/integrate-correction-rounds` did not move.

  Confirm the standard checkout still holds its user-owned `SKILL.md` hunk.

- [ ] **Step 4: Request independent review.**

  Provide commits, focused evidence, suite durations, and the slowest test list.

- [ ] **Step 5: Commit any reviewed correction and report locally.**

  Do not push, merge, or deploy.
