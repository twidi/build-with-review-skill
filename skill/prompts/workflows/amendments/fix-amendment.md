# Fix an Amendment or Updated Spec

Execute the stage named by your parent's `STAGE` assignment.

Keep one complete Fixer Report across both stages. Preserve completed earlier-stage records when updating it.

When your parent resolves an earlier `DECISION`, read the exact resolution. Apply a Human product decision in the Reach stage. Otherwise, record the disposition with its authority or evidence and resume the assigned stage.

## Reach stage

For `STAGE: reach`, read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/amendments/amendment.md`.

Read the current Amendment, old Current Spec, and every newly assigned Reach Report.

When the assignment includes a new Human decision, read it and apply it exactly to the Amendment.

Record that decision, its applied result, and its exact location in the Fixer Report.

Verify each Finding against the complete Amendment and its product context.

Apply each supported correction to the Amendment. Record `APPLIED` with its exact result and location.

Record `DECLINED` only with concrete contradictory evidence.

Record every self-detected Amendment correction.

Self-review the complete corrected Amendment against its Contract, Human decision, dependencies, and preserved behavior.

Repeat correction and complete self-review until your current work finds no remaining issue.

## Consolidation stage

For your first `STAGE: consolidation` assignment, read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/spec/current-spec.md`.

Read the complete old Current Spec and frozen accepted Amendment.

When your assignment provides no Consolidation Report, produce the complete Updated Spec at the assigned target path.

Integrate every Amendment change exactly. Preserve every old Current Spec obligation not changed by the Amendment.

When your assignment provides Consolidation Reports, read each new Report and verify every Finding.

Apply supported corrections only to the Updated Spec. Record every disposition and self-detected correction.

Self-review the complete Updated Spec against its Contract, old Current Spec, and frozen Amendment.

Repeat correction and complete self-review until your current work finds no remaining issue.

## Return a required decision or blocker

When valid correction requires an unresolved product choice, record its full context, options, and source identity in the Fixer Report.

Complete the Child Handoff with:

- `RESULT`: `BLOCKED`;
- `SUMMARY`: `DECISION — <required product choice>`;
- `PARENT ACTION`: `obtain and return the Human decision`.

For another resumable external blocker, use `RESULT: BLOCKED` and state its exact required action.

## Return completed work

Update the complete Fixer Report before every completed Handoff.

Complete the Child Handoff with the applicable values below.

For completed Reach corrections, use:

- `RESULT`: `READY`;
- `SUMMARY`: `CORRECTED — Amendment reach`;
- `PARENT ACTION`: `start a fresh Reach Round`.

For the initial complete Updated Spec, use:

- `RESULT`: `READY`;
- `SUMMARY`: `UPDATED — complete Updated Spec`;
- `PARENT ACTION`: `start a fresh Consolidation Round`.

For completed Consolidation corrections, use:

- `RESULT`: `READY`;
- `SUMMARY`: `CORRECTED — Updated Spec consolidation`;
- `PARENT ACTION`: `start a fresh Consolidation Round`.

Then wait for your parent.

## Exit

- Completed stage work reported → wait for the next stage, review result, or final acceptance.
- Product decision or external blocker reported → wait for a parent follow-up.
- Assignment failure reported → wait for final retirement.
