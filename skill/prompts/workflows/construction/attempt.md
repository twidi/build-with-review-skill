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

For an Attempt created by the restart-after-failure Workflow, also provide:

- the selected restart boundary;
- every exact failed Implementer Report path selected as evidence;
- the exact Diagnostic Report path when one informed that boundary.

Update `PROGRESS.md` with the Task, Attempt, expected base commit, and Report path.

## Receive the Implementer

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/construction/implementer-report.md`.

Read the complete Implementer Report for every Handoff.

For `READY`, confirm that the Report satisfies the Implementer Report Contract.

Inspect the reported commit and current Git state. Do not rerun the Gate.

Request a correction from the same Implementer when the visible result is incomplete or contradictory.

Confirm that every simple Gate command replacement preserves validation coverage.

Present any validation coverage change to the Human before updating the Gate.

Apply every automatic replacement to `GUIDE.md`. Keep its existing execution group.

Add every remaining new Implementer-created validation command to the Gate. Use its recommended execution group.

When that group is missing or its parallel safety is uncertain, use a new sequential group.

After accepting the result, retire the Implementer. Update `PROGRESS.md` with the completed Task, commit, and Gate changes.

## Route a non-ready Attempt

### Validation coverage choice

For a validation coverage choice, present its complete context to the Human.

Update `GUIDE.md` with the exact Human-approved Gate configuration.

Resume the same Implementer with the exact choice and current `GUIDE.md` path.

### Product or technical question

When the Implementer Report contains a product or technical question:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/decisions/adjudication.md`.

Apply the decision-adjudication procedure before selecting a Human route.

When authority or evidence resolves the question, send the exact resolution to the same Implementer. Resume its normal Design or implementation loop.

For a Human product decision, present the complete question, record the answer, and start the applicable Amendment Workflow.

For a technical choice inside the Implementer's authority, send the relevant authority and evidence to the same Implementer. Resume its normal Design or implementation loop.

For a Human technical choice, present the complete question. Record its answer, scope, and applying artifact in `PROGRESS.md`. Resume the same Implementer with that answer. The Implementer updates its Task Design before coding when the choice changes the Design.

### External blocker

For an external blocker, resolve it when current authority and evidence allow. Otherwise, present the complete required Human action. Resume the same Implementer after resolution.

### Failed Attempt

For `FAILED`, retire the Implementer and preserve its Report path. Then use the restart-after-failure Workflow.

## Exit

- Accepted `READY` with another Task → execute this Workflow for that next Task and a fresh Attempt.
- Accepted `READY` with every Plan Task complete → read and execute `<BWR_SKILL>/prompts/workflows/product-review/pass.md`.
- `FAILED` → read and execute `<BWR_SKILL>/prompts/workflows/construction/restart-after-failure.md`.
- Question resolved by authority or evidence → resume the same Implementer.
- Human product decision → read and execute `<BWR_SKILL>/prompts/workflows/amendments/write.md`.
- Technical choice routed to the Implementer → resume the same Implementer.
- Human technical choice resolved → resume the same Implementer.
- Unresolved external blocker → remain in this Workflow.
