# Validate and commit a Plan

Execute this Workflow after the Orchestrator self-review finds the complete Plan internally clean.

## Start a completeness check

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign `check-round-<next sequential number>` as the fresh Check Round identifier.

Keep the candidate Plan unchanged while the checker works.

Use the `Document reviewers` provider group and the `ReviewerMedium` preset.

Use this Report path for a Lot or Sub-lot Plan:

```text
<BWR_WORKSPACE>/reports/planning/<LOT>/<CHECK_ROUND>.md
```

For a Correction Round Plan, insert its Correction Round identifier after `<LOT>`.

```text
<BWR_WORKSPACE>/reports/planning/<LOT>/<CORRECTION>/<CHECK_ROUND>.md
```

Set these annotations:

```text
bwr.role: plan-completeness-checker
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: planning
bwr.lot: <LOT>
bwr.round: <CHECK_ROUND>
```

Add `bwr.correction: <CORRECTION>` for a Correction Round Plan.

Provide the Plan type, exact Plan, Current Spec, and every controlling source path. Include the current Git commit.

Update `PROGRESS.md` with the Check Round identifier, frozen Plan path, and assigned Report path.

## Receive the checker

Before reading a checker Report:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`.

Use the checker Handoff summary to identify `CLEAN`, `FINDINGS`, `BLOCKED`, or `FAILED`.

For `CLEAN`, do not read the checker Report. Retire the checker.

For `FINDINGS`, read the checker Report and retire the checker. Pass its path back to the Plan write Workflow.

For `BLOCKED`, read the available Report. Resolve the cause and follow up with the same checker.

For `FAILED`, read the available Report. When the unchanged check remains executable, use the failed-child replacement procedure for the same assignment and Report path.

Otherwise, retire the failed checker. Present the assignment failure to the Human.

## Commit a clean Plan

Continue here only after a `CLEAN` checker Handoff.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/git/commit.md`.

Commit the clean Plan through that procedure.

When the invoking Workflow transferred an exact pending revert into this commit scope, include that revert in the same commit.

Commit no other working-tree change.

Confirm the created commit and working-tree state.

Update `PROGRESS.md` with the accepted Plan, its commit, and its earliest incomplete or revised Task.

Set your `bwr.phase` annotation to `construction`. Keep the applicable Lot and Correction Round annotations.

## Exit

- `FINDINGS` → read and execute `<BWR_SKILL>/prompts/workflows/planning/write.md` with the checker Report as a correction source.
- `CLEAN` and committed Plan → read and execute `<BWR_SKILL>/prompts/workflows/construction/attempt.md` for the earliest incomplete or revised Task.
- Unresolved blocker or commit failure → remain in this Workflow.
