# Restart after a failed Attempt

Execute this Workflow after the Orchestrator accepts an Implementer `FAILED` Handoff.

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/implementer-report.md`.

When a Diagnostic Report is assigned:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/diagnostic-report.md`.

## Select the restart boundary

Read the failed Implementer Report, Current Spec, active Plan, assigned Task, and current Git state.

Read earlier failed Implementer Reports for this Task only when they can affect the route.

Select the smallest boundary that must change:

- `IMPLEMENTATION`: the Task and its obligations remain valid;
- `DESIGN`: the Task remains valid, but its Design approach must change;
- `EARLIER_TASK`: a completed Task must be corrected first;
- `PLAN`: the active Plan must change;
- `AMENDMENT`: the Current Spec needs a product decision or correction;
- `BLOCKED`: indispensable external information or action is missing.

When repeated comparable failures leave this choice uncertain, read and execute:

- `<BWR_SKILL>/prompts/workflows/construction/diagnose-failures.md`.

Then return here with its Report.

Record the selected boundary, evidence paths, and reason in `PROGRESS.md`.

## Revert the failed state

When the failed Implementer Report names a preservation commit, inspect that commit and the current Git state.

Apply `git revert --no-commit <preservation-commit>`.

Preserve unrelated working-tree changes. Do not reset or rewrite Git history.

When the Report names no preservation commit, do not create a revert or an empty commit.

## Prepare the selected route

Before creating a commit, read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

For `IMPLEMENTATION` or `DESIGN`, commit the pending revert when one exists.

Start a fresh Attempt for the same Task. Provide the failed Implementer Report and any Diagnostic Report as sources.

For `DESIGN`, state that the failed Design is evidence only. The new Implementer must produce a new complete Design.

For `EARLIER_TASK` or `PLAN`, revise the active Plan through the Planning Workflows.

Treat the pending revert as explicitly transferred into the Orchestrator commit scope. Commit it with the clean revised Plan.

Resume construction from the earliest incomplete or revised Task.

For `AMENDMENT`, commit the pending revert when one exists. Then execute the applicable Amendment Workflow.

For `BLOCKED`, commit the pending revert when one exists. Present the complete context and required action to the Human.

Create every commit through that procedure.

Update `PROGRESS.md` with the restored base commit and next route.

## Exit

- `IMPLEMENTATION` or `DESIGN` prepared → execute `<BWR_SKILL>/prompts/workflows/construction/attempt.md` with a fresh Attempt identifier.
- `EARLIER_TASK` or `PLAN` prepared → execute `<BWR_SKILL>/prompts/workflows/construction/attempt.md` for the selected Task.
- `AMENDMENT` → execute `<BWR_SKILL>/prompts/workflows/amendments/write.md`.
- `BLOCKED` → wait for the required Human or external action.
