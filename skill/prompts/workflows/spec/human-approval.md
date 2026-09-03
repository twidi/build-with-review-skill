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

1. Retire the idle Spec Fixer when one exists.
2. Update `PROGRESS.md` with the Human request and the new candidate state.
3. Apply the requested changes to the candidate Spec.
4. Read and execute `<BWR_SKILL>/prompts/workflows/spec/write.md` for complete self-review and a fresh full round.

## Approval

When the Human explicitly approves the candidate:

1. Retire the idle Spec Fixer when one exists.
2. Read once; reread as needed: `<BWR_SKILL>/prompts/references/git/commit.md`.
3. Commit only the approved Current Spec through that procedure.
4. Confirm the created commit and working-tree state.
5. Update `PROGRESS.md` with the approval, Current Spec path, created commit, and first Lot.
6. Set your `bwr.phase` annotation to `planning` and add the first `bwr.lot` value.

## Exit

- Approved and committed Current Spec → read and execute `<BWR_SKILL>/prompts/workflows/planning/write.md`.
- Human-requested changes → continue through the Spec write Workflow.
- Commit blocker → remain in this Workflow and resolve it before planning.
