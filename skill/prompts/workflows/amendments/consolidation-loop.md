# Validate the Updated Spec through Consolidation

Execute this Workflow after initial generation or correction of the complete Updated Spec.

Keep the accepted Amendment frozen throughout each Consolidation Round.

## Start a Consolidation Round

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/review/frozen-subject.md`.

Assign the next Consolidation Round identifier.

Freeze the exact old Current Spec reference, accepted Amendment, and complete Updated Spec for this Round.

Use the `Document reviewers` provider group and the `ReviewerMedium` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/amendments/amendment-<number>/consolidation-round-<round>.md
```

Set these annotations:

```text
bwr.role: consolidation-checker
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: amendment
bwr.round: <ROUND>
```

Provide the old Current Spec commit and path, accepted Amendment, Updated Spec, Round identifier, and assigned Report path.

Update `PROGRESS.md` with the Round, frozen inputs, and Report path.

Keep the Amendment fixer in `idle` while the checker works.

## Receive the checker

Before reading a Consolidation Report:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`.

Use the Handoff summary to identify `CLEAN`, `FINDINGS`, or `BLOCKED`.

For `CLEAN`, do not read the Consolidation Report. Retire the checker with `bwr.status: done`.

Record the Updated Spec as Consolidation-clean.

For `FINDINGS`, do not read the Consolidation Report. Retire the checker with `bwr.status: done`.

Send its exact path to the same Amendment fixer.

For `BLOCKED`, read the available Report. Resolve the blocker and follow up with the same checker.

For `FAILED`, read the available Report. When the same frozen assignment remains executable, use the failed-child replacement procedure for its Report path.

Otherwise, stop and retire the failed checker. Present the assignment failure to the Human.

## Resume the Amendment fixer

Provide:

- `STAGE: consolidation`;
- the old Current Spec commit and path;
- the frozen accepted Amendment path;
- the Updated Spec path as the editable target;
- the current Consolidation Report path;
- the existing Fixer Report path.

The fixer reads the Consolidation Report, corrects the complete Updated Spec, and updates its existing Fixer Report.

## Receive the fixer

Use the Fixer Handoff summary to route its result:

- `CORRECTED` with `READY` → start a fresh Consolidation Round;
- `DECISION` with `BLOCKED` → resolve the product decision;
- another `BLOCKED` result → resolve its stated cause and follow up with the same Fixer;
- `FAILED` → use the failed-child replacement procedure.

For a failed Fixer, read its available Report. When correction remains executable, use the failed-child replacement procedure for the same assignment and Report path.

Provide both Amendment stages' complete current inputs and accumulated correction sources. Otherwise, stop and retire the failed Fixer. Present the assignment failure to the Human.

For `DECISION`:

Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/correction/fixer-report.md`.

Read the Fixer Report and referenced Consolidation Report.

Present the complete decision through the Orchestrator Human-decision procedure. Record the answer in `PROGRESS.md`.

Return the same fixer to `STAGE: reach` with the exact Human decision. The Fixer applies it to the Amendment and records its result.

Then run a fresh Reach Round on the changed Amendment.

Update `PROGRESS.md` with every processed Consolidation Report path.

## Exit

- Consolidation `CLEAN` → execute `<BWR_SKILL>/prompts/workflows/amendments/finalize.md`.
- Fixer `CORRECTED` → repeat this Workflow with a fresh Consolidation Round.
- Amendment changed by a new decision → execute `<BWR_SKILL>/prompts/workflows/amendments/reach-loop.md`.
- Unresolved external blocker → remain in this Workflow.
