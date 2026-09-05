# Validate an Amendment through Reach Review

Execute this Workflow for the current Amendment candidate until one fresh Reach reviewer returns `CLEAN`.

Keep one Amendment fixer session across the complete Reach and Consolidation stages.

## Start a Reach Round

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign `round-<next sequential number>-reach` as the Reach Round identifier. Keep the Amendment unchanged while that reviewer works.

Use the `Document reviewers` provider group and the `Reviewer` preset.

Use these paths:

```text
REPORT: <BWR_WORKSPACE>/reports/amendments/amendment-<number>/<ROUND>.md
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

Use the Handoff summary to identify `CLEAN`, `FINDINGS`, `BLOCKED`, or `FAILED`.

For `CLEAN`, do not read the Reach Report. Retire the reviewer with `bwr.status: done`.

Record the Amendment as Reach-clean and frozen. Continue to the Updated Spec stage.

For `FINDINGS`, do not read the Reach Report. Retire the reviewer with `bwr.status: done`.

Send its exact path to the Amendment fixer.

For `BLOCKED`, read the available Report. Resolve the blocker and follow up with the same reviewer.

For `FAILED`, read the available Report. When the same frozen assignment remains executable, use the failed-child replacement procedure for its Report path.

Otherwise, retire the failed reviewer. Present the assignment failure to the Human.

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

Do not read the Fixer Report for `READY` or a non-decision `BLOCKED` result.

Use the Fixer Handoff summary to route its result:

- `CORRECTED` with `READY` → start a fresh Reach Round;
- `DECISION` with `BLOCKED` → examine the reported `DECISION` classification;
- another `BLOCKED` result → resolve its stated cause and follow up with the same Fixer;
- `FAILED` → use the failed-child replacement procedure.

For a failed Fixer, read its available Report. When Amendment correction remains executable, use the failed-child replacement procedure for the same assignment and Report path.

Provide the current Amendment, old Current Spec, current stage, and every accumulated correction source. Otherwise, retire the failed Fixer. Present the assignment failure to the Human.

For `DECISION`:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`.

Read the Fixer Report and referenced Reach Report.

Apply the Orchestrator decision-adjudication procedure. Present the complete question when a Human product decision or Human technical choice remains. Record an answer in `PROGRESS.md` only when the Human answered.

Send the exact resolution to the same fixer as a `STAGE: reach` follow-up. For a Human product decision, the Fixer applies it to the Amendment. Otherwise, it records the disposition and resumes the correction. When the resolution is a Human technical choice, record its applying Plan or Task Design.

Update `PROGRESS.md` with the Fixer Report path and every processed Reach Report path.

## Exit

- Reach `CLEAN` → execute `<BWR_SKILL>/prompts/workflows/amendments/update-spec.md`.
- Fixer `CORRECTED` → repeat this Workflow with a fresh Reach Round.
- Unresolved decision or external blocker → remain in this Workflow.
