# Correction Rounds Integration Plan

## Goal

Integrate `feat/correction-rounds` into `main` at
`d5cae0f798e5cdf6ec0acc498c8d469bb3aefa8b`.

Keep every accepted standard-workflow fix and every accepted Correction Rounds boundary.

## Constraints

- Work only on `feature/integrate-correction-rounds-main`.
- Do not modify the standard or Correction Rounds worktrees.
- Do not push, deploy, or merge into `main` without explicit user authorization.
- Preserve the user-owned `build-with-review/SKILL.md` change in the standard checkout.
- Keep every complete test command below ten minutes.
- Do not split one slow workflow into several near-ten-minute tests.
- Preserve historical compatibility, concurrency, and interruption recovery.

## Task 1: Establish the baseline

- Confirm the integration branch starts exactly at current `main`.
- Reuse the fresh green evidence for the same exact commit:
  399 standard BWR tests, `py_compile`, and `git diff --check`.
- Confirm the integration worktree is clean.

## Task 2: Merge without committing

- Run `git merge --no-commit --no-ff feat/correction-rounds`.
- Record the exact conflict list.
- Keep the merge uncommitted until the combined generation is verified.

## Task 3: Resolve runtime conflicts

- Preserve the current standard authority implementation from `main`.
- Add the accepted Correction Rounds schema and routes around it.
- Keep both live and historical consumers closed.
- Preserve main's history checkpoint and bounded validation performance.
- Run focused syntax checks after each runtime conflict family.

## Task 4: Resolve prompt and test conflicts

- Preserve current standard public commands and recovery routes.
- Preserve accepted Correction-specific routes and resume rows.
- Keep main's bounded fixtures and timing reports.
- Keep Correction Rounds fixtures, transition explorer, and sensitivity checks.
- Remove all conflict markers and stale public command forms.

## Task 5: Verify the combined generation

- Run `git diff --check`, targeted `py_compile`, and `bash -n`.
- Run all seven standard BWR suites with a 590-second hard timeout.
- Run the complete Correction Rounds suite with the same hard timeout.
- Run the transition explorer.
- Run focused families for every resolved authority conflict.
- Stop and diagnose any command that approaches ten minutes.

## Task 6: Review and commit locally

- Review every resolved producer and direct consumer.
- Verify historical replay, concurrency, and interruption recovery.
- Commit the merge only after all required evidence passes.
- Keep follow-up corrections in separate commits.
- Report the local integration branch and commit.
- Do not push, deploy, or merge into `main` without the next user instruction.
