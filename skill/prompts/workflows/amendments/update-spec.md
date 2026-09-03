# Produce the Updated Spec

Execute this Workflow after a fresh Reach reviewer accepts the complete Amendment.

## Freeze the accepted inputs

Keep the Reach-clean Amendment unchanged through the complete Consolidation stage.

Record the exact old Current Spec commit and path. This pair remains the old-spec reference after the working file changes.

Use the existing Current Spec path as the Updated Spec target.

Update `PROGRESS.md` with the frozen Amendment, old-spec reference, Updated Spec target, and `consolidation` stage.

## Start or resume the Amendment fixer

Use the existing Amendment fixer when the Reach stage created one.

When no fixer exists, create one with the `Fixers` provider group and `Fixer` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/amendments/amendment-<number>/fixer.md
```

For a new fixer, set:

```text
bwr.role: amendment-fixer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: amendment
```

Provide:

- `STAGE: consolidation`;
- the exact old Current Spec commit and path;
- the frozen accepted Amendment path;
- the Current Spec path as the editable Updated Spec target;
- no Consolidation Report for this initial generation;
- the assigned Fixer Report path.

Send these values as a follow-up when the fixer already exists.

## Receive the Updated Spec

Before reading the Fixer Report:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`.

For `UPDATED` with `READY`, do not read the Fixer Report. Confirm the Updated Spec target exists.

Record the completed generation and Fixer Report path in `PROGRESS.md`.

For `DECISION` with `BLOCKED`, read the Fixer Report and present the complete decision to the Human.

A new decision changes the Amendment. Return the same fixer to `STAGE: reach`, update the Amendment, and run a fresh Reach Round.

For another `BLOCKED`, resolve its exact external cause and follow up with the same fixer.

For `FAILED`, read the Fixer Report and resolve the assignment failure before continuing.

## Exit

- Updated Spec generated → execute `<BWR_SKILL>/prompts/workflows/amendments/consolidation-loop.md`.
- Amendment changed by a new decision → execute `<BWR_SKILL>/prompts/workflows/amendments/reach-loop.md`.
- Unresolved external blocker → remain in this Workflow.
