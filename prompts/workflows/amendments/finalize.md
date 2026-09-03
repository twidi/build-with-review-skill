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
- the recorded return Workflow and pending work.

Retire the Amendment fixer with `bwr.status: done`.

## Re-evaluate interrupted work

Read the exact return Workflow and pending work recorded when the Amendment started.

Evaluate that work against the new Current Spec.

For an active Implementer whose Task objective remains valid, send the Updated Spec and Amendment paths to that same Implementer.

Require it to execute the Task Design Workflow and obtain a fresh clean Design check before implementation continues.

Then resume the suspended Attempt Workflow and wait for that same Implementer.

When the Amendment makes the active Task objective false, ask that Implementer to execute the failed Attempt Workflow with `FAILED`.

Resume the suspended Attempt Workflow and receive its failed Handoff.

For planning work, revise and validate the Plan against the new Current Spec.

For Product Review work, return every pending confirmed Finding and accepted Amendment path to the Product Review outcome Workflow.

For a failed Attempt route, return to its recorded restart Workflow with the new Current Spec.

Record any old-Current-Spec Product Review Pass as historical. A later corrected product receives a fresh complete Pass.

## Exit

- Valid active Attempt continues → resume its suspended Attempt Workflow after sending the Design follow-up.
- Active Task objective became false → resume its suspended Attempt Workflow after requesting the failed Handoff.
- Planning resumes → execute `<BWR_SKILL>/prompts/workflows/planning/write.md`.
- Product Review routing resumes → execute `<BWR_SKILL>/prompts/workflows/product-review/route-outcome.md`.
- Failed Attempt routing resumes → execute `<BWR_SKILL>/prompts/workflows/construction/restart-after-failure.md`.
- Another recorded origin → execute its exact recorded return Workflow.
