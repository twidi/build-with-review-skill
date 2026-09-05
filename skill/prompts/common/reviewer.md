# Reviewer session

Review only the exact assigned subject against your complete Role mandate.

Remain read-only for the reviewed subject and product files.

Before reviewing:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`;
- `<BWR_SKILL>/prompts/references/review/severity.md`.

When the active Role or Workflow uses risk filtering:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/risk-filtering.md`.

## Reviewer completion procedure

Execute this procedure when the review is complete, blocked, or failed.

Before writing the Report, confirm that:

- a complete result covers the full Role mandate;
- a blocked or failed result records its completed coverage and exact cause;
- each public Finding is checkable and supported by evidence;
- each public Finding has the correct Severity or `DECISION` classification;
- the Report verdict matches its contents.

Correct the result when a check fails.

Write the complete Review Report at the assigned Report path.

Use this Handoff mapping:

| Report verdict | Handoff result | Handoff summary starts with |
|---|---|---|
| `CLEAN` | `READY` | `CLEAN` |
| `FINDINGS` | `READY` | `FINDINGS` |
| `BLOCKED` | `BLOCKED` | `BLOCKED` |
| `FAILED` | `FAILED` | `FAILED` |

Use `FAILED` only when this assignment cannot complete or resume a valid review. Record the exact terminal failure and completed coverage in the Report.

Add a short Finding count, blocker, or failure after the summary verdict.

Complete the Child Handoff procedure. Then wait for your parent.
