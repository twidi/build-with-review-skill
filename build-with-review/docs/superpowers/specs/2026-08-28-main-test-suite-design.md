# Main Test Suite Repair and Performance Design

## Status

Approved in chat on 2026-08-28.

## Goal

Make the current `main` generation pass every test suite.

Reduce test wall time without reducing workflow authority coverage.

## Scope

This work starts from `main` commit `5b4c95ed237fc1530f2e47b7ee5dbe552cac558f`.

It changes the test harness and stale fixtures first.

It changes runtime only when a focused failing test proves a runtime defect.

It does not include Correction Rounds integration.

## Constraints

- No individual test can run for ten minutes.
- No suite can hide one long workflow by splitting it into many near-ten-minute tests.
- The complete `test_gate.py` and `test_progress.py` suites must each finish within ten minutes.
- Existing independent suites can run in parallel during final verification.
- Bounded seeds must use real production projectors.
- A seed must not copy a production grammar or bypass lifecycle admission.
- Each external filesystem, lock, atomic-replace, and real-process boundary keeps one minimal smoke test.
- No benchmark-only run is allowed.
- Functional runs collect timing data as a side effect.
- No push is allowed without explicit user authorization.

## Current Failures

`test_gate.py` is not green on current `main`.

The first confirmed failure uses a fixture with no `progress.jsonl` file.

`gate-check.sh` now reads the journal under its admission lock.

The fixture therefore fails before the gate behavior under test.

Another test expects a retained duplicate checker opening to refuse.

The current public recovery contract accepts the exact retained rerun.

That assertion is stale after commit `5b4c95e`.

## Design

### Fixture correctness

Each test fixture creates the minimum valid durable prefix required by its public command.

Tests must not depend on permissive behavior removed from production.

Fixture setup uses shared helpers for repeated journal and session authority.

### Bounded execution

Each test runner records elapsed time for every functional test.

The runner fails a test that exceeds its explicit wall-time budget.

The suite report prints the slowest tests after the functional result.

This timing is not a separate benchmark run.

### Fast authority setup

Slow tests replace complete workflow setup with bounded durable seeds.

The seed builds normalized authority facts through production projectors.

The behavior under test still uses the real public helper when it owns filesystem or process behavior.

Repeated same-process validation uses an exact-prefix cache.

The cache key includes the exact journal prefix and the exact entries object where required.

Any prefix change forces validation of the new suffix.

### Test layers

Pure projector tests cover grammar, historical replay, and mutation refusals.

Focused helper tests cover append, lock, marker, ref, and recovery transitions.

Minimal real-process smoke tests cover executable wrappers and OS boundaries.

No test rebuilds an unrelated Design, Product, AMENDMENT, gate, or review workflow.

## Verification

The branch must pass:

- `test_child_launch.py`;
- `test_code_review.py`;
- `test_gate.py`;
- `test_gate_parallel.py`;
- `test_progress.py`;
- `test_review_pool.py`;
- `test_subagent_watchdog.py`;
- targeted `py_compile`;
- `bash -n` for changed shell files;
- `git diff --check`.

Every suite command has a hard timeout below ten minutes.

The final report includes suite durations and the slowest individual tests.

## Integration Boundary

This branch remains separate from `main` and `feat/correction-rounds`.

The earlier integration worktree remains suspended.

No merge, deployment, or push occurs during this work.
