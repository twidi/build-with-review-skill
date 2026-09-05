# Run a Product Review Pass

Execute this Workflow after construction completes or when an accepted Amendment requires a fresh Pass without implementation.

## Confirm Gate coverage

Identify the most recent passing complete Gate and the commit it covered.

Compare that commit with the current commit.

When no later change can affect an included Gate command, continue to the Pass subject.

When a later change can affect an included Gate command, tell the Human that you will run the complete Gate before Product Review. Then run the complete Gate from `<BWR_WORKSPACE>/GUIDE.md`.

When it passes, record `PASSED`, the covered commit, and a concise command-result summary in `PROGRESS.md`. Then continue this Workflow.

When it fails, give the Human the failed commands and a concise useful result summary. Return control to the Human.

The Human owns the next action. Re-evaluate Gate coverage after the Human asks you to continue.

## Freeze the Pass subject

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/concurrency.md`;
- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign the next sequential `pass-<number>` identifier for the root Lot.

Freeze:

- the exact current commit;
- the Current Spec;
- the root Lot Plan;
- every completed Sub-lot and Correction Round Plan under that Lot;
- every applicable source Finding path.

Use these five lenses:

1. `unlooked`;
2. `user`;
3. `meaning`;
4. `quality`;
5. `coverage`.

Update `PROGRESS.md` with the Pass identifier, frozen inputs, expected lenses, and current Review Concurrency.

Replace your complete applicable annotation set with:

```text
bwr.role: orchestrator
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: product-review
bwr.lot: <root LOT>
```

This removes assignment keys from completed Correction Round or Sub-lot work.

## Assign a lens reviewer

Use the `Product reviewers` provider group and the preset assigned to the lens Role.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/product-review/<LOT>/<PASS>/reviewer-<lens>.md
```

Set these annotations:

```text
bwr.role: product-reviewer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: product-review
bwr.lot: <LOT>
bwr.pass: <PASS>
bwr.mandate: <lens>
```

Provide every frozen input, the lens name, and the assigned Reviewer Report path.

For `unlooked`, `user`, `meaning`, and `quality`, also provide this private-history path:

```text
<BWR_WORKSPACE>/reports/product-review/<LOT>/risk-filtered/<lens>.md
```

## Apply Review Concurrency

One unsettled lens chain occupies one review place.

Its reviewer or Finding verifier can work while the other waits in `idle`. Together they still occupy one place.

Launch lens reviewers in the listed order while a review place is available.

When a reviewer returns, immediately execute the lens-settlement Workflow for that lens.

A settled lens frees its place. Launch the next waiting lens reviewer immediately.

## Preserve the frozen subject

Keep the frozen inputs unchanged until every lens settles.

If the subject changes, mark every still-open lens-chain session `superseded`, then archive and hide it.

Record the superseded Pass in `PROGRESS.md`. Start a fresh Pass for the new commit.

## Complete the Pass

The Pass completes only after every expected lens has a settled result.

Update `PROGRESS.md` after each lens settles. Keep its Reviewer Report path, final verdict, and Verification Report path when one exists.

## Exit

- Reviewer Handoff received → execute `<BWR_SKILL>/prompts/workflows/product-review/settle-lens.md` for that lens.
- Every lens settled → execute `<BWR_SKILL>/prompts/workflows/product-review/route-outcome.md`.
- Frozen subject changed → restart this Workflow with a fresh Pass identifier.
