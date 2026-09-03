# Full Spec review round

Execute this Workflow to review one unchanged candidate Spec through every full-round mandate.

## Prepare the round

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/concurrency.md`;
- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Use these mandates for the first full round:

- `enumerator`;
- `verifier`;
- `feasibility`;
- `judge`.

Add `ripple` to every later full round.

Assign one Full Round identifier. Keep the candidate Current Spec unchanged until every assignment has a settled result.

Update `PROGRESS.md` with the Full Round identifier, exact Spec path, and expected mandates.

## Assign each reviewer

Use the `Document reviewers` provider group and the preset assigned to the mandate.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/spec/full-round-<number>/<mandate>.md
```

Set these annotations:

```text
bwr.role: spec-reviewer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: spec
bwr.round: <ROUND>
bwr.mandate: <mandate>
```

Provide the exact Current Spec path, Full Round identifier, mandate, and Report path.

For `enumerator`, `verifier`, `judge`, and `ripple`, also provide this private-history path:

```text
<BWR_WORKSPACE>/reports/spec/risk-filtered/<mandate>.md
```

Provide the preceding Spec Fixer Report path to `ripple`.

## Apply Review Concurrency

Each launched reviewer occupies one review place while its assignment remains active.

After accepting a `READY` Handoff, retire that reviewer. This frees its review place.

Launch mandates in the listed order while a place is available. Launch the next waiting mandate when a place becomes free.

## Collect the round

Require each `READY` Handoff summary to state the Report verdict: `CLEAN` or `FINDINGS`.

A `BLOCKED` or `FAILED` Handoff summary states its exact obstacle or failure.

Do not read the Reviewer Reports during collection. Keep every exact Report path for later routing.

Resolve a `BLOCKED` or `FAILED` assignment before settling the Full Round. Use the same child for a follow-up to that assignment.

Settle the Full Round only after every expected mandate returns an accepted `READY` Handoff.

Update `PROGRESS.md` with the settled verdicts and Report paths.

## Exit

- Every mandate reports `CLEAN` → read and execute `<BWR_SKILL>/prompts/workflows/spec/human-approval.md`.
- One or more mandates report `FINDINGS` → pass every Full Round Report path to `<BWR_SKILL>/prompts/workflows/spec/correction-loop.md`, then read and execute it.
- The Spec changes before settlement → supersede the affected reviewers and restart this Workflow with a fresh Full Round identifier.
