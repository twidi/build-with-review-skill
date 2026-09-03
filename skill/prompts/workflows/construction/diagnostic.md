# Diagnose repeated failed Attempts

Execute this Workflow for the Construction Diagnostic assignment from your parent.

## Read the evidence

Read every assigned failed Implementer Report.

Read the assigned Current Spec, Plan, Task sections, Designs, and commits needed to test their claims.

Read `<BWR_WORKSPACE>/GUIDE.md` when your assignment provides it.

Establish which failures are comparable. Identify their common stage, behavior, probable cause, and restart recommendation.

Identify material differences between their inputs, Designs, implementations, checks, environments, and observed failures.

Separate confirmed repository or execution facts from inference.

## Select one classification

Choose the smallest restart boundary supported by the combined evidence.

Use exactly one classification from the Construction Diagnostic Report Contract.

For each plausible smaller boundary, state the evidence that accepts or rejects it.

Identify the exact Plan, Task, or Attempt boundary where work must resume.

## Write the Diagnostic Report

Write the complete Diagnostic Report at the assigned path.

Include every required Contract field, the comparison, the classification, and the concrete restart point.

When indispensable evidence is missing, record the exact missing input and why it prevents a valid classification.

## Hand off

When the Report contains a valid classification, complete the Child Handoff with:

- `RESULT`: `READY`;
- `SUMMARY`: `<CLASSIFICATION> — <concrete restart point>`;
- `PARENT ACTION`: `route the failed Attempt from the Diagnostic Report`.

A Report classified `BLOCKED` is still a completed Diagnostic deliverable. Return `RESULT: READY` for that Report.

When missing evidence prevents a valid classification, complete the Child Handoff with:

- `RESULT`: `BLOCKED`;
- `SUMMARY`: `BLOCKED — <exact missing evidence>`;
- `PARENT ACTION`: `provide the named evidence`.

Use `RESULT: FAILED` only when this Diagnostic assignment cannot produce or resume a valid Report.

Then wait for your parent.

## Exit

- Valid classification reported → wait for final acceptance.
- Missing evidence reported → wait for a parent follow-up.
- Assignment failure reported → wait for final retirement.
