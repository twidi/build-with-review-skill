# Close a root Lot

Execute this Workflow after a complete Product Review Pass returns `CLEAN` for the root Lot.

## Confirm the Lot boundary

Confirm that:

- every planned Task, Sub-lot, and Correction Round under the root Lot is complete;
- the current commit is covered by a passing complete Gate;
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

Read the Current Spec and identify the next incomplete root Lot in its execution order.

When another root Lot remains, prepare this exact Planning assignment:

```text
PLAN TYPE: Lot
LOT: <next exact root Lot identifier>
CURRENT SPEC: <Current Spec path>
CONTROLLING OBLIGATIONS: <every Current Spec heading path assigned to this Lot>
```

## Continue or transfer ownership

When another root Lot remains, the current Orchestrator can continue directly.

Use succession only at this Lot boundary. Start it when the Human requests it or a fresh Orchestrator is appropriate.

For direct continuation, update your `bwr.lot` to the next Lot and set `bwr.phase: planning`.

Record the selected continuation route and prepared Planning assignment in `PROGRESS.md`.

## Exit

- Same Orchestrator continues → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` with the prepared Planning assignment.
- Successor selected → execute `<BWR_SKILL>/prompts/workflows/delivery/handoff-successor.md` with the prepared Planning assignment.
- No root Lot remains → execute `<BWR_SKILL>/prompts/workflows/delivery/close-run.md`.
- Closing condition missing → return to the Workflow that owns that open condition.
