# Check an implementation candidate

Execute this Workflow for one assigned Code Check Round.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/construction/task-design.md`;
- `<BWR_SKILL>/prompts/contracts/construction/implementer-report.md`.

This Workflow uses risk filtering. Use the assigned `PRIVATE_HISTORY` through the loaded risk-filtering rules.

## Read the subject

Read the complete Current Spec, Plan, Task, applicable parent Plans, accepted Task Design, and Implementer Report.

Read the previous checker Report when assigned.

Inspect the complete candidate diff from the assigned base commit.

Read every affected file and test in its relevant repository context.

Treat this complete input set as the review subject.

## Check the candidate

Execute the complete Code Checker Role mandate against the complete subject.

Review the complete candidate. Use the previous checker Report only to verify its Finding dispositions.

For each previous `APPLIED` disposition, verify the correction and its effects.

For each previous `DISAGREED` disposition, verify the contradictory evidence against the current candidate.

Report a still-valid disagreed Finding again with current evidence.

Run focused checks when they provide useful evidence for a candidate problem.

Support every Finding with exact affected locations, controlling obligations, and concrete evidence.

Confirm that the complete diff, affected behavior, and Role mandate received coverage.

Complete the Reviewer completion procedure.

## Exit

- Handoff sent → wait for parent action.
- Follow-up received for this assignment → execute this Workflow again with the updated inputs.
