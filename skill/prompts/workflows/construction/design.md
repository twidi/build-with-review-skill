# Create the Task Design

Execute this Workflow at the start of one Implementer Attempt and after Design checker Findings.

## Load the Design contract

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/construction/task-design.md`.

Read the assigned Current Spec, Plan, Task, applicable parent Plans, and `GUIDE.md`.

Read applicable project instructions.

When a Design checker Report is assigned:

1. Read once; reread as needed:
   - `<BWR_SKILL>/prompts/contracts/review/report.md`;
   - `<BWR_SKILL>/prompts/contracts/review/finding.md`.
2. Read that Report before changing the Design.

Resolve each ordinary checker Finding during this Workflow.

After a completed correction, record `APPLIED`. Otherwise, record `DISAGREED` with concrete contradictory evidence.

Treat a `DECISION` Finding or invalid controlling contract as a blocker for this Workflow.

## Inspect the repository

Inspect the current Git state and confirm the expected base commit.

Inspect the code, tests, configuration, documentation, dependencies, and tooling relevant to the Task.

Identify existing patterns, interfaces, state transitions, failure behavior, and validation boundaries.

Preserve unrelated working-tree changes.

## Write the complete Design

Write the complete Task Design inside the assigned tracked `Design` section.

During this Workflow, change only that Design section.

Trace every proposed behavior to the Task, parent Plan, or Current Spec.

Define the implementation structure, ordered steps, interfaces, state, errors, recovery, and behaviors to prove.

Record material alternatives and the reason for the selected approach.

When an authoritative source does not resolve a required product choice, return that decision to your parent.

## Self-review

Review the complete Design against:

- every Task and parent obligation;
- the Task Design Contract;
- the actual repository structure and constraints;
- interfaces, formats, state, and events;
- edge cases, errors, and recovery;
- planned tests and other validation;
- the boundary between product intent and implementation design.

Correct every issue found.

Repeat the complete self-review after each correction until it finds no remaining issue.

Update the Implementer Report with the Design state and any targeted validation already performed.

## Exit

- Internally clean complete Design → read and execute `<BWR_SKILL>/prompts/workflows/construction/design-review-loop.md`.
- Required product decision, invalid Task contract, or external blocker → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
