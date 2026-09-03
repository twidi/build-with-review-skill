# Spec correction loop

Execute this Workflow when a full or Scoped Spec review reports Findings.

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

Create the Fixer for the first correction. Send a follow-up to the same Fixer for each later correction input.

Do not read the source Reviewer Reports. The Fixer consumes them.

Update `PROGRESS.md` with the Fixer Report path and current source Report paths.

## Receive the Fixer

Use the Fixer Handoff summary to route its result:

- `CORRECTED` with `READY` → continue to Scoped review;
- `DECISION` with `BLOCKED` → resolve the product decision;
- another `BLOCKED` or `FAILED` result → resolve its stated cause before continuing.

For `DECISION`:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`;
- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`.

Read the current Fixer Report and the referenced source Reviewer Report.

Present the complete decision context, options, and consequences to the Human. Record the answer in `PROGRESS.md`.

Send the exact Human decision to the same Fixer as a follow-up. Keep the same Fixer Report path.

## Start a Scoped review

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign a fresh Scoped Round identifier. Keep the corrected Current Spec unchanged during this review.

Use the `Document reviewers` provider group and the `Reviewer` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/spec/scoped-round-<number>.md
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
- `<BWR_WORKSPACE>/reports/spec/risk-filtered/scoped.md` as `PRIVATE_HISTORY`;
- the Scoped Report path.

Update `PROGRESS.md` with the Scoped Round identifier and assigned paths.

## Receive the Scoped reviewer

Do not read the Scoped Report. Use its Handoff summary.

- `CLEAN` → retire the Scoped reviewer and continue to a fresh full round;
- `FINDINGS` → retire the Scoped reviewer and send its Report path to the same Spec Fixer;
- `BLOCKED` or `FAILED` → resolve the assignment before continuing.

Keep the Spec Fixer `idle` while a reviewer works.

## Exit

- Scoped `CLEAN` → pass the current Spec Fixer Report path to `<BWR_SKILL>/prompts/workflows/spec/review-round.md`, then execute it.
- Scoped `FINDINGS` → repeat this Workflow with the same Spec Fixer and its Report path.
- Unresolved Human decision or external blocker → remain in this Workflow.
