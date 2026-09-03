# Close a root Lot

Execute this Workflow after a complete Product Review Pass returns `CLEAN` for the root Lot.

## Confirm the Lot boundary

Confirm that:

- every planned Task, Sub-lot, and Correction Round under the root Lot is complete;
- the final Task Report records a passing complete Gate;
- the final Product Review Pass is complete and clean;
- no confirmed Finding, product decision, or blocker remains open for this Lot;
- the Current Spec contains every accepted Amendment;
- no assigned tracked BWR change remains uncommitted.

Use the current Git state, final Gate declaration, and clean Pass as the closing evidence.

## Record completion

Update `PROGRESS.md` with:

- the completed root Lot;
- its final commit;
- its final Gate result;
- its clean Product Review Pass;
- every completed Sub-lot and Correction Round.

Read the Current Spec and identify the next incomplete root Lot.

## Continue or transfer ownership

When another root Lot remains, the current Orchestrator can continue directly.

Use succession only at this Lot boundary. Start it when the Human requests it or a fresh Orchestrator is appropriate.

For direct continuation, update your `bwr.lot` to the next Lot and set `bwr.phase: planning`.

Record the selected continuation route in `PROGRESS.md`.

## Exit

- Same Orchestrator continues → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for the next root Lot.
- Successor selected → execute `<BWR_SKILL>/prompts/workflows/delivery/handoff-successor.md`.
- No root Lot remains → execute `<BWR_SKILL>/prompts/workflows/delivery/close-run.md`.
- Closing condition missing → return to the Workflow that owns that open condition.
