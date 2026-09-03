# Verify one Product reviewer Report

Execute this Workflow for the Finding Verification assignment from your parent.

## Read the source

Read the complete current Reviewer Report and every frozen Pass input needed for verification.

Confirm that the Reviewer Report identifies the assigned frozen subject.

Use repository inspection, focused commands, and observable behavior as appropriate. Keep the reviewed product unchanged.

## Verify every Finding

For each ordinary Finding, independently check its fact, requirement, scope connection, consequence, and evidence.

For each `DECISION`, inspect the complete relevant Current Spec context and verify the claimed unresolved choice.

Assign one Contract verdict to every source Finding.

Preserve each source `F<number>` identity in the Verification Report.

## Write the Verification Report

Write the complete Verification Report at the assigned path.

Record the concrete check and observed result for every source Finding.

On a follow-up, read the complete revised Reviewer Report again. Reverify every current Finding and overwrite the complete Verification Report.

If an environment blocker prevents completion, preserve the completed verification evidence and record the exact blocker.

## Hand off

When every Finding has a verification verdict, complete the Child Handoff with:

- `RESULT`: `READY`;
- `SUMMARY`: `<confirmed count> CONFIRMED, <disproved count> DISPROVED, <unverifiable count> UNVERIFIABLE`;
- `PARENT ACTION`: `settle the lens or return UNVERIFIABLE results to the reviewer`.

When an environment blocker prevents completion, complete the Child Handoff with:

- `RESULT`: `BLOCKED`;
- `SUMMARY`: `BLOCKED — <exact blocker>`;
- `PARENT ACTION`: `resolve the blocker and resume verification`.

Use `RESULT: FAILED` only when this verification assignment cannot produce or resume a valid Report.

Then wait for your parent.

## Exit

- Complete verdict set reported → wait for acceptance or a revised Reviewer Report.
- Environment blocker reported → wait for a parent follow-up.
- Assignment failure reported → wait for final retirement.
