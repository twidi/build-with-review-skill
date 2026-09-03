# Implementer checker loop

This Reference is for an Implementer that runs a Design or Code checker loop.

The active Workflow defines the exact checker role, subject, paths, annotations, and outcome routes.

## Start a round

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`;
- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Start a Round only after the complete subject passes Implementer self-review.

Keep that complete subject unchanged while its checker works.

Create a fresh checker session for each new Round. Use the `Implementer checkers` provider group and `Reviewer` preset.

Provide the current Implementer Report in every Round. From the second Round, also provide the previous checker Report.

## Receive a result

Use the Handoff summary to identify `CLEAN`, `FINDINGS`, or `BLOCKED`.

For `CLEAN`, do not read the checker Report. Retire the checker and record its path and verdict in the Implementer Report.

For `FINDINGS`, read the checker Report. Retire the checker and record its path and verdict in the Implementer Report.

For `BLOCKED`, read the Report. Resolve a checker-only cause and follow up with the same checker.

Return an unresolved subject or external blocker to the active Workflow.

For `FAILED`, read the Report and retire the failed checker. Return the failure to the active Workflow.

## Continue the loop

A `CLEAN` result accepts the current subject.

A `FINDINGS` result returns the Report to the Implementer correction Workflow.

After correction and complete self-review, create a fresh checker Round for the complete corrected subject.
