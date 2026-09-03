# Hand off to a successor Orchestrator

Execute this Workflow only at a completed root Lot boundary.

## Select the successor provider

Inspect the currently enabled TwiCC providers.

Ask the Human which provider the successor must use. Present the current or last Orchestrator provider as the recommended choice.

Use the `Controller` preset.

Update `PROGRESS.md` with the selected provider, next Lot, and pending succession.

## Stop the current Watchdog

Load TwiCC's current process-stop and session-update instructions when needed.

Stop the current Watchdog process. Then set its `bwr.status` to `done`, archive it, and hide it.

## Create the successor

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/session/orchestrator-handoff.md`.

Load TwiCC's current session-creation instructions when needed.

Create the successor in the same TwiCC project and repository checkout.

Resolve both inclusion paths before creation. Build the prompt in this order:

```text
@@<absolute path to prompts/entries/orchestrator.md>
@@<absolute BWR Workspace path>/ADDITIONAL-INSTRUCTIONS.md

BWR_SKILL: <absolute path>
BWR_WORKSPACE: <absolute path>
REPOSITORY: <absolute checkout path>
LOT: <new Lot identifier>
CURRENT_SPEC: <absolute path>
GIT_COMMIT: <current commit>
PROGRESS: <absolute path>
GUIDE: <absolute path>
```

Use these session settings:

- a title that identifies the Feature and new Lot, without a `- ` prefix;
- the Human-selected provider;
- preset `Controller`;
- `mute_on_user_turn: false`;
- `question_widget: true`;
- `hidden: false`.

Set these annotations:

```text
bwr.role: orchestrator
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: planning
bwr.lot: <LOT>
```

Keep the returned successor `session_id`. Wait for its Orchestrator acceptance message.

## Settle the handoff

For `BLOCKED`, resolve the exact missing or contradictory context. Send a follow-up to the same successor.

For `ACCEPTED`, ownership transfers to the successor.

Set your own `bwr.status` to `done`.

Remain visible, unmuted, unarchived, and not hidden. Stop BWR work after acceptance.

## Exit

- Successor `ACCEPTED` → end this Orchestrator assignment.
- Successor `BLOCKED` → remain in this Workflow with the same successor.
- Session creation failure → remain in this Workflow and preserve the prepared handoff context.
