# Check a Task Design

Execute this Workflow for one assigned Design Check Round.

## Load the Design contract

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/construction/task-design.md`.

This Workflow uses risk filtering. Use the assigned `PRIVATE_HISTORY` through the loaded risk-filtering rules.

## Read the subject

Read the complete Current Spec, Plan, Task, applicable parent Plans, Task Design, and Implementer Report.

Read the previous checker Report when assigned.

Inspect the relevant repository state and expected base commit.

Treat the complete Design and controlling input set as the review subject.

## Check the Design

Execute the complete Design Checker Role mandate against the complete subject.

Review the complete current Design. Use a previous checker Report only to verify its recorded dispositions.

Verify every `APPLIED` disposition against the corrected Design.

Verify the evidence for every `DISAGREED` disposition. Report the problem again when the evidence does not resolve it.

Report any controlling-contract conflict that prevents a valid Design as a checkable Finding.

Support each Finding with the exact Design location, controlling obligation, and repository evidence.

Confirm that the complete controlling input set received coverage.

Complete the Reviewer completion procedure.

## Exit

- Handoff sent → wait for parent action.
- Follow-up received for this assignment → execute this Workflow again with the updated inputs.
