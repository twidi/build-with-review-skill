# Run an Implementer Attempt

Execute this Workflow for the next incomplete Task in the accepted Plan.

## Prepare the Attempt

Confirm the exact Current Spec, Plan, Task, current Git commit, and applicable parent obligations.

Set `<TASK>` to `task-<number>` from the Plan heading.

Set `<ATTEMPT>` to `attempt-<next sequential number>` for that Task.

Use the `Implementer` provider group and the `Implementer` preset.

Use this Report path for a Lot or Sub-lot Task:

```text
<BWR_WORKSPACE>/reports/construction/<LOT>/<TASK>/<ATTEMPT>/implementer.md
```

For a Correction Round Task, insert its Correction Round identifier after `<LOT>`.

```text
<BWR_WORKSPACE>/reports/construction/<LOT>/<CORRECTION>/<TASK>/<ATTEMPT>/implementer.md
```

Set these annotations:

```text
bwr.role: implementer
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: construction
bwr.lot: <LOT>
bwr.task: <TASK>
bwr.attempt: <ATTEMPT>
```

Add `bwr.correction: <CORRECTION>` for a Correction Round Task.

Provide:

- the exact Current Spec and accepted Plan paths;
- the exact assigned Task and its controlling obligations;
- every applicable parent Plan path;
- the expected base Git commit;
- the current `Implementer checkers` provider choice;
- `<BWR_WORKSPACE>/GUIDE.md`;
- the assigned Implementer Report path.

Update `PROGRESS.md` with the Task, Attempt, expected base commit, and Report path.

## Receive the Implementer

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/implementer-report.md`.

Read the complete Implementer Report for every Handoff.

For `READY`, confirm that the Report satisfies the Implementer Report Contract.

Inspect the reported commit and current Git state. Do not rerun the Gate.

Request a correction from the same Implementer when the visible result is incomplete or contradictory.

Add every new Implementer-created validation command to the Gate in `GUIDE.md`. Use its recommended execution group.

After accepting the result, retire the Implementer. Update `PROGRESS.md` with the completed Task, commit, and Gate changes.

## Route a non-ready Attempt

For a product decision, record the blocker and start the applicable Amendment Workflow.

For an external blocker, present its complete context to the Human. Resume the same Implementer after resolution.

For `FAILED`, retire the Implementer and preserve its Report path. Then use the restart-after-failure Workflow.

## Exit

- Accepted `READY` with another Task → execute this Workflow for that next Task and a fresh Attempt.
- Accepted `READY` with every Plan Task complete → read and execute `<BWR_SKILL>/prompts/workflows/product-review/pass.md`.
- `FAILED` → read and execute `<BWR_SKILL>/prompts/workflows/construction/restart-after-failure.md`.
- Product decision → read and execute `<BWR_SKILL>/prompts/workflows/amendments/write.md`.
- Unresolved external blocker → remain in this Workflow.
