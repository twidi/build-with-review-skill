# Finalize an Amendment

Execute this Workflow after a fresh Consolidation checker returns `CLEAN` for the complete Updated Spec.

## Commit the accepted product contract

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

Inspect the complete tracked Amendment and Updated Spec changes.

Commit the accepted Amendment and Updated Spec together through the Git commit procedure.

Confirm the created commit and working-tree state.

The Updated Spec at the existing Spec path is now the Current Spec. The committed Amendment remains historical.

Update `PROGRESS.md` with:

- the accepted Amendment path and number;
- the replaced Current Spec commit;
- the new Current Spec path and commit;
- the completed Reach and Consolidation result;
- every source Finding identity resolved by this Amendment;
- the recorded return Workflow and pending work.

Retire the Amendment fixer with `bwr.status: done`.

## Re-evaluate interrupted work

Read the exact return Workflow and pending work recorded when the Amendment started.

Evaluate that work against the new Current Spec.

Before resuming it, replace your complete applicable annotation set. Always use `bwr.role: orchestrator`, `bwr.status: working`, and the current `bwr.feature`.

Restore the remaining values from the recorded return context:

| Return context | Restored assignment annotations |
|---|---|
| Active Attempt or failed Attempt routing | `bwr.phase: construction`, its Lot, and its Correction Round when applicable |
| Planning | `bwr.phase: planning`, its Lot, and its Correction Round when applicable |
| Product Review routing | `bwr.phase: product-review` and its root Lot |
| Another origin | its exact phase and applicable Lot or Correction Round |

Omit every assignment key that does not apply to the restored context.

For an active Implementer whose Task objective remains valid, set the Amendment commit as that Attempt's new expected base commit.

Update `PROGRESS.md` with the replacement base. Send the Updated Spec path, Amendment path, and new expected base commit to that same Implementer.

Require it to execute the Task Design Workflow and obtain a fresh clean Design check before implementation continues.

Then resume the suspended Attempt Workflow and wait for that same Implementer.

When the Amendment makes the active Task objective false, ask that Implementer to execute the failed Attempt Workflow with `FAILED`.

Resume the suspended Attempt Workflow and receive its failed Handoff.

For Planning work, rebuild its complete assignment with:

- the recorded Plan type, identifier, path, and candidate state;
- the new Current Spec path;
- every controlling obligation for that Plan from the new Current Spec;
- the accepted Amendment path as origin evidence;
- every other recorded controlling source and transferred commit scope.

Revise and validate the Plan against that assignment. The new Current Spec remains authoritative.

For Product Review work, return every pending confirmed Finding, accepted Amendment path, and resolved source Finding identity to the Product Review outcome Workflow.

For a failed Attempt route, return to its recorded restart Workflow with the new Current Spec.

Record any old-Current-Spec Product Review Pass as historical. A later corrected product receives a fresh complete Pass.

## Exit

- Valid active Attempt continues → resume its suspended Attempt Workflow after sending the Design follow-up.
- Active Task objective became false → resume its suspended Attempt Workflow after requesting the failed Handoff.
- Planning resumes → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` with the rebuilt Planning assignment.
- Product Review routing resumes → execute `<BWR_SKILL>/prompts/workflows/product-review/route-outcome.md`.
- Failed Attempt routing resumes → execute `<BWR_SKILL>/prompts/workflows/construction/restart-after-failure.md`.
- Another recorded origin → execute its exact recorded return Workflow.
