# Successor startup

Execute this Workflow now. Another Orchestrator assigned you a new Lot.

## Read the handoff

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/session/orchestrator-handoff.md`;
- `<BWR_SKILL>/prompts/contracts/bwr-workspace/progress.md`;
- `<BWR_SKILL>/prompts/contracts/bwr-workspace/guide.md`.

Read the assigned `PROGRESS.md`, `GUIDE.md`, Current Spec, and current Git state.

Confirm that:

- every assigned path exists;
- the repository matches the assigned Git commit;
- the new Lot exists in the Current Spec;
- `PROGRESS.md` and `GUIDE.md` contain the required current state.

Adopt the provider map and Review Concurrency from `PROGRESS.md` as current defaults.

## Blocked handoff

When required context is missing or contradictory:

1. Load TwiCC's current session-update and send-message instructions.
2. Set your `bwr.status` annotation to `blocked` through the `self` target.
3. Send the `BLOCKED` acceptance message to the `parent` target.
4. Wait for a follow-up from the previous Orchestrator.
5. Recheck the complete handoff after that follow-up.

## Prepare ownership

Load TwiCC's current session-update instructions when not already loaded.

Set your annotations through the `self` target:

- `bwr.role: orchestrator`;
- `bwr.status: working`;
- `bwr.feature: <FEATURE>`;
- `bwr.phase: planning`;
- `bwr.lot: <LOT>`.

## Start the Watchdog

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/watchdog.md`.

Start the Watchdog for this Orchestrator with that configuration. Keep its returned `session_id`.

## Accept ownership

Load TwiCC's current send-message instructions when not already loaded.

Send the `ACCEPTED` message from the Orchestrator Handoff Contract to the `parent` target.

Update `PROGRESS.md` with the new current Lot and accepted succession.

## Exit

- Valid handoff and started Watchdog → read and execute `<BWR_SKILL>/prompts/workflows/planning/write.md`.
- Unresolved handoff blocker → remain in this Workflow and wait.
