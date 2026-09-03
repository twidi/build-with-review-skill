# Code review loop

Execute this Workflow after the complete implementation candidate passes Implementer self-review.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/construction/checker-loop.md`.

Execute that procedure with the following local configuration.

## Subject and Round

The subject contains:

- the exact Current Spec, Plan, Task, and applicable parent Plans;
- the accepted complete Task Design;
- the expected base commit;
- the complete candidate diff, affected files, and tests.

Use the next Code Check Round identifier.

## Report and private history

For a Lot or Sub-lot Task, use:

```text
REPORT: <BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/<ATTEMPT>/code-check-round-<number>.md
PRIVATE_HISTORY: <BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/<ATTEMPT>/risk-filtered-code.md
```

For a Correction Round Task, use:

```text
REPORT: <BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/<ATTEMPT>/code-check-round-<number>.md
PRIVATE_HISTORY: <BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/<ATTEMPT>/risk-filtered-code.md
```

## Annotations

Set:

```text
bwr.role: code-checker
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: construction
bwr.lot: <LOT>
bwr.task: <TASK>
bwr.attempt: <ATTEMPT>
bwr.round: <CODE_CHECK_ROUND>
```

Add `bwr.correction: <CORRECTION>` for a Correction Round Task.

## Exit

- `CLEAN` → read and execute `<BWR_SKILL>/prompts/workflows/construction/validate-and-deliver.md`.
- `FINDINGS` → pass the checker Report to `<BWR_SKILL>/prompts/workflows/construction/implement.md`, then execute it.
- Unresolved subject or external blocker → read and execute `<BWR_SKILL>/prompts/workflows/construction/report-failure.md`.
- Failed checker assignment → execute this Workflow again with a fresh Code Check Round.
