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

Stop the current Watchdog process. Then set its `bwr.status` to `done`, archive it, and hide it.

Inspect the current TwiCC topology.

For every remaining non-Orchestrator child, stop any live process and apply its accurate terminal status.

Archive and hide each of those children.

Keep every Orchestrator visible, unmuted, unarchived, and not hidden.

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
