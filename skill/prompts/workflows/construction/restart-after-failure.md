# Restart after a failed Attempt

Execute this Workflow after the Orchestrator accepts an Implementer `FAILED` Handoff.

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/implementer-report.md`.

When a Diagnostic Report is assigned:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/diagnostic-report.md`.

When this Workflow resumes after its `BLOCKED` exit, read its recorded restart base and blocker from `PROGRESS.md`.

Inspect the resolution evidence and current Git state. Record that evidence in `PROGRESS.md`.

Use the restart base as a Git reference. Preserve legitimate later changes. Do not reset to it.

Return directly to restart-boundary selection.

## Select the restart boundary

Read the failed Implementer Report, Current Spec, active Plan, assigned Task, and current Git state.

Read earlier failed Implementer Reports for this Task only when they can affect the route.

Select the smallest boundary that must change:

- `IMPLEMENTATION`: the Task and its obligations remain valid;
- `DESIGN`: the Task remains valid, but its Design approach must change;
- `EARLIER_TASK`: a completed Task must be corrected first;
- `PLAN`: the active Plan must change;
- `AMENDMENT`: the Current Spec needs a product decision or correction;
- `BLOCKED`: indispensable information, technical choice, or external action is missing.

When repeated comparable failures leave this choice uncertain, read and execute:

- `<BWR_SKILL>/prompts/workflows/construction/diagnose-failures.md`.

Then return here with its Report.

Record the selected boundary, evidence paths, and reason in `PROGRESS.md`.

When the selected boundary contains a product or technical question:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/decisions/adjudication.md`.

## Revert the failed state

When the failed Implementer Report names a preservation commit, inspect that commit and the current Git state.

Determine whether this Workflow already applied that exact preservation commit's revert. The revert can be pending or included in a later commit.

When it is already applied, preserve that state and do not apply it again.

Otherwise, apply `git revert --no-commit <preservation-commit>`. Immediately record the applied revert in `PROGRESS.md`.

Preserve unrelated working-tree changes. Do not reset or rewrite Git history.

When the Report names no preservation commit, do not create a revert or an empty commit.

## Prepare the selected route

Before creating a commit, read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

For `IMPLEMENTATION` or `DESIGN`, commit the pending revert when one exists.

Start a fresh Attempt for the same Task. Provide the failed Implementer Report and any Diagnostic Report as sources.

For `DESIGN`, state that the failed Design is evidence only. The new Implementer must produce a new complete Design.

For `EARLIER_TASK` or `PLAN`, prepare a revision of the active Plan.

Provide the selected boundary, relevant failed Implementer Report paths, any Diagnostic Report path, and the earliest Task that must change.

Treat the pending revert as explicitly transferred into the Planning commit scope. Provide its preservation commit identifier when one exists.

Then read and execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for the active Plan.

The Planning Workflows commit the clean revised Plan with that transferred revert. They resume construction from the earliest incomplete or revised Task.

For `AMENDMENT`:

Apply the decision-adjudication procedure to the exact Current Spec problem, evidence, options, consequences, and recommendation.

Present the complete question only when a Human product decision or Human technical choice remains.

Record the exact resolution or Human decision in `PROGRESS.md`.

When the result is a technical choice or does not require a Current Spec change, preserve the current revert state. Record any Human technical choice with its scope and applying artifact. Re-evaluate the smallest restart boundary from the resolution.

When it requires an Amendment, record this Workflow and the interrupted Task as the return context. Commit the pending revert when one exists.

Then provide the exact Human decision, Current Spec, relevant failed Implementer Reports, any Diagnostic Report, origin context, and return context to `<BWR_SKILL>/prompts/workflows/amendments/write.md`.

For `BLOCKED`, commit the pending revert when one exists.

Record the current Git commit as the restart base. Also record the failed Attempt, its preservation commit when one exists, and whether its revert is complete or unnecessary.

Apply the decision-adjudication procedure when the blocker is a product or technical choice.

Resolve an ordinary technical choice through its owner. Present the complete context only when a Human product decision, Human technical choice, or external Human action remains.

Create every commit through the Commit Reference procedure.

Update `PROGRESS.md` with the next route and its committed Git state when applicable.

## Exit

- `IMPLEMENTATION` or `DESIGN` prepared → execute `<BWR_SKILL>/prompts/workflows/construction/attempt.md` with a fresh Attempt identifier.
- `EARLIER_TASK` or `PLAN` selected → continue through `<BWR_SKILL>/prompts/workflows/planning/write.md`; its Workflows return to construction.
- Human decision requires an Amendment → execute `<BWR_SKILL>/prompts/workflows/amendments/write.md` with the prepared inputs.
- Human decision changes the restart route → repeat boundary selection with that decision.
- Required Human decision remains open → remain in this Workflow.
- `BLOCKED` resolved without the Human → repeat boundary selection from the restart base.
- `BLOCKED` requires the Human or external action → wait for it.
- Recorded blocker resolved → repeat boundary selection from the restart base.
