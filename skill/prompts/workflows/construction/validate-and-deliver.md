# Validate and deliver an Attempt

Execute this Workflow only after a clean Code checker accepts the complete Task candidate.

## Build the final Gate

Read the current `<BWR_WORKSPACE>/GUIDE.md` and applicable project instructions.

Start with every command included in the approved Gate.

Treat a recorded replacement as automatic when it preserves validation coverage.

When a replacement changes validation coverage, execute the failed Attempt Workflow with `BLOCKED`. State the exact coverage change and require your parent to obtain the Human Gate decision.

Replace each old command with its automatic replacement. Keep the existing Gate group.

Add every remaining validation command created during this Attempt. Use the Gate group recorded in the Implementer Report.

## Run the complete final Gate

Run every included Gate command.

Run commands from the same execution group in parallel when the group contains several commands.

Wait for the complete group before starting the next group.

Use command output to diagnose failures. Do not copy raw output into the Implementer Report.

Set the final Gate state to `PASSED` only when every included command passes.

Otherwise, set it to `FAILED`.

## Handle a Gate failure

Analyze every failed command inside this Attempt.

When a content correction can resolve the failure, make that correction through the implementation Workflow.

The complete corrected candidate must pass self-review, a fresh Code checker, and a new complete final Gate.

A corrected Gate failure does not remain in the final Implementer Report.

Use the failed Attempt Workflow when the failure needs external action or cannot be resolved in this Attempt.

## Commit a passing Attempt

Continue here only after the complete final Gate passes.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

Commit the complete assigned Task scope through that procedure.

Include the accepted Design, tests, implementation, and other assigned product changes.

Confirm the created commit and inspect the remaining working-tree state.

## Complete the Attempt Report

Update the Implementer Report with:

- the delivered result;
- the final Gate state and a concise command-result summary;
- every new validation command and recommended Gate group;
- every simple Gate command replacement;
- the created commit;
- the complete Design and Code Review history.

Complete the Child Handoff procedure with these local values:

- `RESULT`: `READY`;
- `SUMMARY`: `DELIVERED — <commit>; final Gate passed`;
- `PARENT ACTION`: `validate the Report and continue the Plan`.

Then wait for your parent.

## Exit

- Passing Gate and confirmed commit → Handoff and wait.
- Correctable Gate failure → read and execute `<BWR_SKILL>/prompts/workflows/construction/implement.md`.
- Unresolved Gate or commit blocker → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
