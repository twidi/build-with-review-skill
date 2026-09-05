# Spec correction loop

Execute this Workflow when a full or Scoped Spec review reports Findings, or when the Human requests a Spec correction.

Keep one Spec Fixer session for the complete Spec correction cycle. Keep it available during later Scoped and full rounds.

## Start or resume the Spec Fixer

Use the `Fixers` provider group and the `Fixer` preset.

Use this Report path for the complete cycle:

```text
<BWR_WORKSPACE>/reports/spec/fixer.md
```

Set these annotations when creating the Fixer:

```text
bwr.role: spec-fixer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: spec
```

Provide the exact Current Spec path and every source Reviewer Report path from the current correction input.

When the Human requested the correction, also provide that exact request as a Human correction input.

Create the Fixer for the first correction. Send a follow-up to the same Fixer for each later correction input.

Do not read the source Reviewer Reports. The Fixer consumes them.

Update `PROGRESS.md` with the Fixer Report path and current correction sources.

## Receive the Fixer

Do not read the Fixer Report for `READY` or a non-decision `BLOCKED` result.

Use the Fixer Handoff summary to route its result:

- `CORRECTED` with `READY` → continue to Scoped review;
- `DECISION` with `BLOCKED` → examine the reported `DECISION` classification;
- another `BLOCKED` result → resolve its stated cause and follow up with the same Fixer;
- `FAILED` → use the failed-child replacement procedure.

For `FAILED`, read the available Fixer Report. When the correction remains executable, use the failed-child replacement procedure for the same assignment and Report path.

Provide the complete current Spec and every accumulated correction source to that replacement. Otherwise, retire the failed Fixer. Present the assignment failure to the Human.

For `DECISION`:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`;
- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`;
- `<BWR_SKILL>/prompts/references/decisions/adjudication.md`.

Read the current Fixer Report and the referenced source Reviewer Report.

Apply the decision-adjudication procedure.

When authority or evidence resolves the question, send that resolution to the same Fixer.

When the question belongs to a technical owner, tell the Fixer that the Spec selects no mechanism. The Fixer records the `DECISION` Finding as declined.

Only for a Human product decision, present the complete context, options, and consequences. Record the answer in `PROGRESS.md`.

For a Human technical choice, present the complete question. Record its answer, scope, and future applying Plan or Task Design in `PROGRESS.md`. Tell the Fixer that product behavior remains unchanged and that the `DECISION` Finding is declined.

Send the exact resolution or Human product decision to the same Fixer as a follow-up. Keep the same Fixer Report path.

## Start a Scoped review

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign `scoped-round-<next sequential number>` as the fresh Scoped Round identifier. Keep the corrected Current Spec unchanged during this review.

Use the `Document reviewers` provider group and the `Reviewer` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/spec/<SCOPED_ROUND>.md
```

Set these annotations:

```text
bwr.role: spec-reviewer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: spec
bwr.round: <SCOPED_ROUND>
bwr.mandate: scoped
```

Provide:

- the exact Current Spec path;
- the current Spec Fixer Report path;
- every source Reviewer Report path processed by that Fixer Report;
- every exact Human correction input processed by that Fixer Report;
- `<BWR_WORKSPACE>/reports/spec/risk-filtered/scoped.md` as `PRIVATE_HISTORY`;
- the Scoped Report path.

Update `PROGRESS.md` with the Scoped Round identifier and assigned paths.

## Receive the Scoped reviewer

For `CLEAN` or `FINDINGS`, do not read the Scoped Report. Use its Handoff summary.

- `CLEAN` → retire the Scoped reviewer and continue to a fresh full round;
- `FINDINGS` → retire the Scoped reviewer and send its Report path to the same Spec Fixer;
- `BLOCKED` → read the available Report, resolve the obstacle, and follow up with the same reviewer;
- `FAILED` → read the available Report. When the same frozen assignment remains executable, use the failed-child replacement procedure for its Report path. Otherwise, retire the failed reviewer and present the assignment failure to the Human.

Keep the Spec Fixer `idle` while a reviewer works.

## Exit

- Scoped `CLEAN` → pass the current Spec Fixer Report path to `<BWR_SKILL>/prompts/workflows/spec/review-round.md`, then execute it.
- Scoped `FINDINGS` → repeat this Workflow with the same Spec Fixer and its Report path.
- Unresolved Human decision or external blocker → remain in this Workflow.
