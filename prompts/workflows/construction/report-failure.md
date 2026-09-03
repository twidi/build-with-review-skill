# Report a blocked or failed Attempt

Execute this Workflow when the Implementer cannot continue through the current construction stage.

## Select the Attempt outcome

Use `BLOCKED` when exact external information or action can let this same Attempt continue.

Use `FAILED` when this Attempt cannot produce a valid complete result.

An unresolved product decision or environment dependency is `BLOCKED` while its resolution can preserve the Attempt objective.

An invalid Task contract or abandoned objective is `FAILED`.

## Record the problem

Update the current Implementer Report with:

- the exact failure or blocker stage;
- the observed behavior;
- the meaningful checks already performed;
- the probable cause and supporting evidence;
- the current Design, Code Review, and Gate state;
- the required parent action;
- the recommended continuation or restart point.

Keep command evidence concise. Do not copy raw command output.

## Preserve a failed Attempt

For `FAILED`, inspect the complete assigned Attempt diff.

When the diff contains assigned tracked changes, read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

Create one preservation commit for that exact assigned state. Include its identifier in the Implementer Report.

Create no empty commit when the Attempt has no assigned tracked change.

## Hand off

Write the complete current Implementer Report through the Child Handoff procedure.

For a resumable blocker, use:

- `RESULT`: `BLOCKED`;
- `SUMMARY`: `DECISION — <required choice>` or `BLOCKED — <required external action>`;
- `PARENT ACTION`: the exact action required to resume this Attempt.

For a failed Attempt, use:

- `RESULT`: `FAILED`;
- `SUMMARY`: `FAILED — <stage and concise cause>`;
- `PARENT ACTION`: `select and prepare the restart route`.

Then wait for your parent.

## Follow-up after `BLOCKED`

Read every changed authoritative input supplied by your parent.

When the product contract, Task, or Design changes, restart at the Task Design Workflow.

When only the external blocker changes, resume the Workflow that reported it.

When the parent ends this Attempt, execute this Workflow again with outcome `FAILED`.

## Exit

- `BLOCKED` Handoff sent → wait for a parent follow-up.
- `FAILED` Handoff sent → wait for final retirement.
- Product, Task, or Design input changed → read and execute `<BWR_SKILL>/prompts/workflows/construction/design.md`.
- External blocker resolved → resume the interrupted Workflow.
