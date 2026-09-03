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

Execute this procedure after completing the full Role mandate.

Before writing the Report, confirm that:

- the complete Role mandate received coverage;
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

Add a short Finding count or blocker after the summary verdict.

Complete the Child Handoff procedure. Then wait for your parent.
