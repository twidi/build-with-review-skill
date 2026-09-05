# Human approval of the Spec

Execute this Workflow after a clean full Spec review round.

## Present the candidate

Read the complete candidate Spec from its current path.

Present the Human with:

- the exact Spec path;
- its goal and principal product behavior;
- its scope boundaries;
- its Lot breakdown and dependencies;
- confirmation that every mandate in the latest full round reported `CLEAN`.

Do not read the Reviewer Reports. Their accepted Handoffs already establish the round outcome.

Ask the Human to approve the candidate as the Current Spec or state the required changes.

## Required changes

When the Human requests changes:

1. Update `PROGRESS.md` with the exact Human request and the new candidate state.
2. Pass that request as a Human correction input to the Spec correction loop.
3. Keep the existing Spec Fixer when one exists. The correction loop creates one otherwise.

## Approval

When the Human explicitly approves the candidate:

1. Retire the idle Spec Fixer when one exists.
2. Read once; reread as needed: `<BWR_SKILL>/prompts/references/git/commit.md`.
3. Commit only the approved Current Spec through that procedure.
4. Confirm the created commit and working-tree state.
5. Select the first root Lot in the Current Spec's execution order.
6. Update `PROGRESS.md` with the approval, Current Spec path, created commit, and selected Lot.
7. Set your `bwr.phase` annotation to `planning` and add the selected `bwr.lot` value.
8. Prepare this exact Planning assignment:

```text
PLAN TYPE: Lot
LOT: <selected root Lot identifier>
CURRENT SPEC: <Current Spec path>
CONTROLLING OBLIGATIONS: <every Current Spec heading path assigned to this Lot>
```

## Exit

- Approved and committed Current Spec → read and execute `<BWR_SKILL>/prompts/workflows/planning/write.md` with the prepared Planning assignment.
- Human-requested changes → read and execute `<BWR_SKILL>/prompts/workflows/spec/correction-loop.md` with the exact request.
- Commit blocker → remain in this Workflow and resolve it before planning.
