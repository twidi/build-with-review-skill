# Recovery startup

Execute this Workflow when a new Orchestrator resumes an abandoned BWR run.

## Confirm authority

Obtain Human confirmation that the previous Orchestrator no longer works.

When that confirmation already appears in the current conversation, use it directly.

## Locate the BWR workspace

Use an exact BWR workspace path supplied by the Human when it contains `PROGRESS.md` and `GUIDE.md`.

Otherwise, inspect the direct children of `<active checkout>/bwr_workspace/` that contain both files.

When exactly one candidate exists, present its path and obtain Human confirmation.

When no candidate or several candidates exist, ask the Human for the exact path.

Set `<BWR_WORKSPACE>` only after confirming the selected path.

Read `<BWR_WORKSPACE>/ADDITIONAL-INSTRUCTIONS.md` when it exists.

## Reconstruct durable state

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/bwr-workspace/progress.md`;
- `<BWR_SKILL>/prompts/contracts/bwr-workspace/guide.md`.

Read the current:

- `PROGRESS.md`;
- `GUIDE.md`;
- Current Spec;
- active Plans;
- Git state;
- Reports named by the current durable work.

Determine the last completed durable outcome and the first incomplete action.

Preserve valid commits. Reuse a Report only when its current contents clearly complete its assignment.

Treat an incomplete or ambiguous Report as unfinished work.

The owning Workflow creates a fresh session and Report path for each unfinished specialist assignment.

## Restore configuration

Check the current provider map, Review Concurrency, Gate, and Git guidance against the available providers and repository.

Reuse each valid value.

Collect every missing or invalid value before contacting the Human.

Ask the required questions together. Put as many questions as the provider supports in each widget.

Update `PROGRESS.md` and `GUIDE.md` with the accepted replacements.

## Prepare ownership

Load TwiCC's current session-update instructions.

Set your applicable annotations through the `self` target:

- `bwr.role: orchestrator`;
- `bwr.status: working`;
- `bwr.feature: <FEATURE>`;
- the recovered `bwr.phase`;
- the recovered Lot or Correction Round identifiers when applicable.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/watchdog.md`.

Start the Watchdog for this Orchestrator with that configuration. Keep its returned `session_id`.

Record the Recovery and selected continuation point in `PROGRESS.md`.

## Exit

Read and execute the Workflow that owns the first incomplete action:

- Spec creation → `<BWR_SKILL>/prompts/workflows/spec/write.md`;
- Spec review or correction → the applicable Workflow under `<BWR_SKILL>/prompts/workflows/spec/`;
- Plan creation or validation → the applicable Workflow under `<BWR_SKILL>/prompts/workflows/planning/`;
- Task construction or failed Attempt routing → the applicable Workflow under `<BWR_SKILL>/prompts/workflows/construction/`;
- Product Review → `<BWR_SKILL>/prompts/workflows/product-review/pass.md`;
- Amendment work → the applicable Workflow under `<BWR_SKILL>/prompts/workflows/amendments/`;
- completed Lot or run → the applicable Workflow under `<BWR_SKILL>/prompts/workflows/delivery/`.
