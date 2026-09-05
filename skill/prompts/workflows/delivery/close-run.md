# Close the BWR run

Execute this Workflow after the final root Lot closes.

## Confirm delivery

Confirm that:

- every root Lot, Sub-lot, and Correction Round is complete;
- the last complete Gate passed;
- the last complete Product Review Pass is clean;
- no confirmed Finding, product decision, or blocker remains open;
- the Current Spec contains every accepted Amendment;
- no assigned tracked BWR work remains uncommitted.

Inspect the current Git commit and working-tree state.

## Record the final result

Update `PROGRESS.md` with:

- the final delivery result;
- the Current Spec path and commit;
- every delivered Lot and construction commit;
- the final Gate command-result summary;
- the final clean Product Review Pass;
- accepted scope limits and excluded Gate commands.

## Retire BWR sessions

Load TwiCC's current session-update and topology instructions when needed.

Set the current Watchdog's `bwr.status` to `done`. Then archive and hide it.

Inspect your direct children in the current TwiCC topology.

For every remaining direct non-Orchestrator child, apply its accurate terminal status.

Archive and hide each of those children.

Keep every Orchestrator and every session owned by another parent unchanged.

## Report delivery

Present the Human with:

- the delivered result;
- the Current Spec and final commit;
- the delivered Lots and commits;
- the final Gate summary;
- the final clean Product Review Pass;
- accepted limits;
- the current Git and working-tree state.

Ask whether to keep or delete the exact `<BWR_WORKSPACE>` directory. Recommend keeping it.

Delete that directory only after the Human explicitly selects deletion for that exact path.

Set your own `bwr.status` to `done` after the BWR workspace choice is complete.

## Exit

- BWR workspace kept → end the BWR run and preserve every repository object.
- BWR workspace deletion explicitly selected → delete only `<BWR_WORKSPACE>`, then end the BWR run.
- Delivery condition missing → return to the Workflow that owns that open condition.
