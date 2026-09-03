# Run a Construction Diagnostic

Execute this Workflow when repeated comparable failed Attempts do not provide a clear restart boundary.

The Orchestrator owns this Workflow. The Construction Diagnostic performs the analysis.

## Prepare the assignment

Assign the next sequential Diagnostic number for this Task.

Use the `Implementer checkers` provider group and the `Reviewer` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/diagnostic-<number>.md
```

For a Correction Round Task, insert its Correction Round identifier after `<LOT>`.

```text
<BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/diagnostic-<number>.md
```

Set these annotations:

```text
bwr.role: construction-diagnostic
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: construction
bwr.lot: <LOT>
bwr.task: <TASK>
```

Add `bwr.correction: <CORRECTION>` for a Correction Round Task.

Provide:

- every comparable failed Implementer Report path;
- the Current Spec and active Plan paths;
- the exact Task section and any relevant earlier Task sections;
- the failed Attempt and preservation commit identifiers;
- the current Git commit;
- any exact question that the diagnostic must resolve;
- `<BWR_WORKSPACE>/GUIDE.md` when Git, Gate, or environment evidence is relevant;
- the assigned Diagnostic Report path.

Update `PROGRESS.md` with the Diagnostic number, inputs, question, and Report path.

## Receive the Diagnostic

Read the Diagnostic Report for every Handoff.

For `READY`, confirm that the Report contains one classification, its evidence, and one concrete restart point.

Request a correction from the same Diagnostic when the Report is incomplete or internally contradictory.

After accepting a `READY` Report, retire the Diagnostic. Record its classification, restart point, and Report path in `PROGRESS.md`.

For `BLOCKED`, resolve the named missing input or action. Then send it to the same Diagnostic.

For `FAILED`, retire the Diagnostic and present the failure context to the Human.

## Exit

- Accepted `READY` → return to `<BWR_SKILL>/prompts/workflows/construction/restart-after-failure.md` with the Diagnostic Report path.
- Resolvable `BLOCKED` → remain in this Workflow.
- Unresolved `BLOCKED` or `FAILED` → wait for the Human.
