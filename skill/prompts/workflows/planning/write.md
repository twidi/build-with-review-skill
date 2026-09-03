# Write a Plan

Execute this Workflow to create or correct one BWR Plan.

## Load the Plan contract

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/planning/plan.md`.

Read once; reread as needed: the one specialized Contract for the assigned Plan.

| Plan | Contract |
|---|---|
| Lot | `<BWR_SKILL>/prompts/contracts/planning/lot-plan.md` |
| Sub-lot | `<BWR_SKILL>/prompts/contracts/planning/sub-lot-plan.md` |
| Correction Round | `<BWR_SKILL>/prompts/contracts/planning/correction-plan.md` |

## Read the sources

Read the complete Current Spec and relevant repository structure.

For a Lot Plan, read every Current Spec obligation assigned to that Lot.

For a Sub-lot Plan, also read the parent Plan, source Findings, and inherited obligations. Inspect the reviewed commit.

For a Correction Round Plan, also read the parent Plan, confirmed Findings, and their Verification Reports. Inspect the reviewed commit.

When correcting a completeness check, also read its assigned checker Report.

When source Findings or Reviewer Reports control this Plan:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`.

When Verification Reports control this Plan:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/product-review/verification-report.md`.

When a failed Attempt requires this Plan revision, read every assigned failed Implementer Report and Diagnostic Report.

Use them as evidence for the assigned `EARLIER_TASK` or `PLAN` boundary. The Current Spec and current repository state remain authoritative.

Preserve the exact pending revert as transferred commit scope. Do not alter unrelated working-tree changes.

## Write the Plan

Choose the tracked Plan path from applicable repository conventions.

Write one thin Plan that completely covers its assigned obligations.

Define coherent Tasks with explicit outcomes, order, dependencies, probable locations, and observable verification targets.

Keep technical design choices for the Implementer. Leave every Task `Design` section empty.

When planning exposes a required product choice absent from the Current Spec, use the Orchestrator decision procedure.

## Self-review

Review the complete Plan against:

- the common and specialized Plan Contracts;
- every assigned source obligation;
- complete coverage across the Tasks;
- Task boundaries, order, and backward dependencies;
- compatibility with the repository;
- preservation of existing obligations;
- the Plan detail boundary.

Correct every issue found.

Repeat the complete self-review after each correction until it finds no remaining issue.

Update `PROGRESS.md` with the Plan type, identifier, path, sources, current planning state, and any transferred commit scope.

## Exit

- Internally clean Plan → read and execute `<BWR_SKILL>/prompts/workflows/planning/validate-and-commit.md`.
- Required product decision → resolve it through the applicable Amendment Workflow before completing this Plan.
- External blocker → record it in `PROGRESS.md` and present it to the Human.
