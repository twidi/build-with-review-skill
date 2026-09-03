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

## Human setup

Present every credible Gate command with its source and purpose.

Agree with the Human on:

- included commands;
- excluded commands and their reasons;
- execution order;
- commands that can run in parallel.

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/provider-groups.md`.

Inspect the currently enabled TwiCC providers.

Ask one question for each provider group and one question for Review Concurrency.

Put as many questions as the provider supports in each widget. If they do not all fit, immediately continue with another widget.

Present the proposed Feature identifier during the same setup phase. Accept an immediate correction from the Human.

Set `<BWR_WORKSPACE>` to:

```text
<active checkout>/bwr_workspace/<FEATURE>
```

If that exact directory exists, ask the Human to choose Recovery or another Feature identifier.

## Initialize the BWR workspace

Determine the Current Spec path from repository conventions.

Create `<BWR_WORKSPACE>/reports/`.

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

## Exit

- Recovery selected → read and execute `<BWR_SKILL>/prompts/workflows/startup/recovery.md`.
- Initialization complete → read and execute `<BWR_SKILL>/prompts/workflows/spec/write.md`.
