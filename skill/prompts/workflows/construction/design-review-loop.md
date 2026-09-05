# Design review loop

Execute this Workflow after the complete Task Design passes Implementer self-review.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/construction/checker-loop.md`.

Execute that procedure with the following local configuration.

## Subject and Round

The subject contains:

- the exact Current Spec, Plan, Task, and applicable parent Plans;
- the complete Task Design;
- the expected base commit and relevant repository state.

Use `design-check-round-<next sequential number>` as the Design Check Round identifier.

## Report and private history

For a Lot or Sub-lot Task, use:

```text
REPORT: <BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/<ATTEMPT>/<DESIGN_CHECK_ROUND>.md
PRIVATE_HISTORY: <BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/<ATTEMPT>/risk-filtered-design.md
```

For a Correction Round Task, use:

```text
REPORT: <BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/<ATTEMPT>/<DESIGN_CHECK_ROUND>.md
PRIVATE_HISTORY: <BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/<ATTEMPT>/risk-filtered-design.md
```

## Annotations

Set:

```text
bwr.role: design-checker
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: construction
bwr.lot: <LOT>
bwr.task: <TASK>
bwr.attempt: <ATTEMPT>
bwr.round: <DESIGN_CHECK_ROUND>
```

Add `bwr.correction: <CORRECTION>` for a Correction Round Task.

## Exit

- `CLEAN` → read and execute `<BWR_SKILL>/prompts/workflows/construction/implement.md`.
- `FINDINGS` → pass the checker Report to `<BWR_SKILL>/prompts/workflows/construction/design.md`, then execute it.
- Unresolved subject or external blocker → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
- Failed checker replaced → remain in this Workflow with the same Design Check Round.
- Unresolved checker assignment failure → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
