# Validate an Amendment through Reach Review

Execute this Workflow for the current Amendment candidate until one fresh Reach reviewer returns `CLEAN`.

Keep one Amendment fixer session across the complete Reach and Consolidation stages.

## Start a Reach Round

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign the next Reach Round identifier. Keep the Amendment unchanged while that reviewer works.

Use the `Document reviewers` provider group and the `Reviewer` preset.

Use these paths:

```text
REPORT: <BWR_WORKSPACE>/reports/amendments/amendment-<number>/round-<round>-reach.md
PRIVATE_HISTORY: <BWR_WORKSPACE>/reports/amendments/amendment-<number>/risk-filtered-reach.md
```

Set these annotations:

```text
bwr.role: reach-reviewer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: amendment
bwr.round: <ROUND>
```

Provide the old Current Spec, complete Amendment candidate, Round identifier, private-history path, and assigned Report path.

Update `PROGRESS.md` with the Reach Round, frozen candidate, and assigned paths.

## Receive the Reach reviewer

Before reading a Reach Report:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`.

Use the Handoff summary to identify `CLEAN`, `FINDINGS`, or `BLOCKED`.

For `CLEAN`, do not read the Reach Report. Retire the reviewer with `bwr.status: done`.

Record the Amendment as Reach-clean and frozen. Continue to the Updated Spec stage.

For `FINDINGS`, do not read the Reach Report. Retire the reviewer with `bwr.status: done`.

Send its exact path to the Amendment fixer.

For `BLOCKED`, read the available Report. Resolve the blocker and follow up with the same reviewer.

For `FAILED`, read the available Report and resolve the assignment failure before continuing.

## Start or resume the Amendment fixer

Use the `Fixers` provider group and the `Fixer` preset.

Use this Report path across both Amendment stages:

```text
<BWR_WORKSPACE>/reports/amendments/amendment-<number>/fixer.md
```

When creating the fixer, set:

```text
bwr.role: amendment-fixer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: amendment
```

Provide:

- `STAGE: reach`;
- the old Current Spec path;
- the Amendment path as the editable target;
- the current Reach Report path;
- the assigned Fixer Report path.

Create the fixer for the first correction. Use the same fixer and Report path for every later Amendment correction.

Keep the fixer in `idle` while each fresh Reach reviewer works.

## Receive the fixer

Use the Fixer Handoff summary to route its result:

- `CORRECTED` with `READY` → start a fresh Reach Round;
- `DECISION` with `BLOCKED` → resolve the product decision;
- another `BLOCKED` or `FAILED` result → resolve its stated cause before continuing.

For `DECISION`:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`.

Read the Fixer Report and referenced Reach Report.

Present the complete decision through the Orchestrator Human-decision procedure. Record the answer in `PROGRESS.md`.

Send the exact Human decision to the same fixer as a `reach` stage follow-up.

Update `PROGRESS.md` with the Fixer Report path and every processed Reach Report path.

## Exit

- Reach `CLEAN` → execute `<BWR_SKILL>/prompts/workflows/amendments/update-spec.md`.
- Fixer `CORRECTED` → repeat this Workflow with a fresh Reach Round.
- Unresolved decision or external blocker → remain in this Workflow.
