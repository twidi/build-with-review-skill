# Implement the Task

Execute this Workflow after a clean Design check and after each Code checker Report with Findings.

## Prepare the implementation

Read the assigned Current Spec, Plan, Task Design, applicable parent Plans, and `GUIDE.md`.

Inspect the complete working-tree state and relevant project instructions.

Identify the exact candidate diff boundary from the expected base commit and assigned Task.

When a Code checker Report is assigned:

1. Read once; reread as needed:
   - `<BWR_SKILL>/prompts/contracts/review/report.md`;
   - `<BWR_SKILL>/prompts/contracts/review/finding.md`.
2. Read that Report before changing the candidate.

Resolve each ordinary checker Finding during this Workflow.

After a completed correction, record `APPLIED`. Otherwise, record `DISAGREED` with concrete contradictory evidence.

Treat a `DECISION` Finding or invalid controlling contract as a blocker for this Workflow.

## Write tests and code

Implement the accepted Design completely.

Create suitable evidence for every behavior declared by the Design.

Prefer writing or updating tests before implementation when that order is practical.

Use the validation form that best proves each behavior when an automated test is unsuitable.

Run useful targeted, partial, or complete checks during implementation.

Record meaningful targeted validation and its result in the Implementer Report.

Record every new validation command and its recommended Gate group.

## Handle a Design change

When implementation evidence requires a material Design change, stop the affected implementation work.

Update the complete Task Design through `<BWR_SKILL>/prompts/workflows/construction/design.md`.

Resume implementation only after a fresh Design checker accepts that complete Design.

Return any required product decision or invalid controlling contract to your parent through the failed Attempt Workflow.

## Self-review the complete change

Inspect the complete Task diff, affected files, tests, configuration, documentation, and generated artifacts.

Review the complete candidate against:

- the Current Spec, Plan, Task, and accepted Design;
- correctness and complete behavior coverage;
- state transitions, errors, edge cases, and recovery;
- test relevance and failure sensitivity;
- unintended scope changes;
- runtime cost, duplication, clarity, and maintainability;
- applicable project instructions.

Correct every issue found. Run the checks needed to validate each correction.

After each correction, repeat the complete self-review.

If a correction changes the Design materially, use the Design change procedure before continuing.

Continue until the complete candidate is internally clean.

Update the Implementer Report with the current delivered scope, self-review result, validation, and changed files.

## Exit

- Internally clean complete candidate → read and execute `<BWR_SKILL>/prompts/workflows/construction/code-review-loop.md`.
- Material Design change → execute the Design Workflow, then its fresh review loop.
- Required product decision, invalid controlling contract, or external blocker → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
