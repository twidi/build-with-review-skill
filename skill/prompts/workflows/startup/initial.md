# Initial startup

Execute this Workflow when the Human starts a new BWR run in the current session.

## Inspect

Complete these steps before the first BWR workspace write:

1. Determine the installed BWR skill absolute path as `<BWR_SKILL>`.
2. Inspect the active checkout and repository structure.
3. Read applicable project instructions.
4. Determine the repository commit style from project rules and recent commits.
5. Discover credible validation commands in documentation, CI, package scripts, configuration, and existing tooling.
6. Propose a stable Feature identifier using `YYYY-MM-DD-short-name`.
7. Determine the Current Spec path from repository conventions. When no clear convention exists, prepare a suitable path proposal for the Human.

## Agree on the Gate

Present every credible Gate command with its source and purpose.

Agree with the Human on:

- included commands;
- excluded commands and their reasons;
- execution order;
- commands that can run in parallel.

## Complete Human setup

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/provider-groups.md`.

Inspect the currently enabled TwiCC providers.

Ask one question for each provider group and one question for Review Concurrency. Require an integer of `1` or more.

Put as many questions as the provider supports in each widget. If they do not all fit, immediately continue with another widget.

Present the proposed Feature identifier during the same setup phase. Accept an immediate correction from the Human.

Present the proposed Current Spec path during that setup phase. When no clear repository convention determines it, ask the Human to confirm or replace the proposal.

Set `<BWR_WORKSPACE>` to:

```text
<active checkout>/bwr_workspace/<FEATURE>
```

If that exact directory exists, do not reuse it. Ask the Human for another Feature identifier.

## Validate the starting state

Tell the Human that you will run the complete approved Gate to verify the stable starting state required by BWR.

Run every included command. Follow the approved execution groups and parallelism.

When every command passes, continue the Startup Workflow.

When a command fails, give the Human the failed commands and a concise useful result summary. Return control to the Human.

The Human owns all diagnosis, correction, and disposition of that failure.

After the Human asks you to continue, run the complete approved Gate again. Continue only after every command passes.

## Initialize the BWR workspace

Create the exact `<BWR_WORKSPACE>` directory.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/bwr-workspace/guide.md`;
- `<BWR_SKILL>/prompts/contracts/bwr-workspace/progress.md`.

Write `GUIDE.md` with the discovered Git guidance and Human-approved Gate.

Write `PROGRESS.md` with the run, provider choices, Review Concurrency, planned Current Spec path, and current Git commit.

Load TwiCC's current session-update instructions. Set your annotations through the `self` target:

- `bwr.role: orchestrator`;
- `bwr.status: working`;
- `bwr.feature: <FEATURE>`;
- `bwr.phase: spec`.

## Start the Watchdog

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/watchdog.md`.

Start the Watchdog for this Orchestrator with that configuration. Keep its returned `session_id`.

Wait for its first message.

For `WATCHDOG: READY`, keep the session and continue.

For `WATCHDOG: FAILED`, or when the session ends before confirmation, retire it with `bwr.status: failed`. Resolve the cause and create a replacement.

Do not leave this Startup Workflow without one confirmed Watchdog.

## Exit

- Initialization complete → read and execute `<BWR_SKILL>/prompts/workflows/spec/write.md`.
