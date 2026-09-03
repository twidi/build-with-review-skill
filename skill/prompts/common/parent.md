# Parent session

## Your responsibility

Manage the complete lifecycle of your direct child sessions.

One child owns one logical assignment. Reuse that child for follow-ups to the same assignment.

Create a new child for a new Round, Pass, Task, Attempt, or mandate.

## Prepare TwiCC

Before creating your first session, load and follow TwiCC's current `twicc-create-session` instructions.

Use the TwiCC MCP operation when available. Discover a deferred MCP operation before using the CLI fallback.

Use TwiCC `whoami` to get your current `project_id`. Pass that project explicitly to every created session.

## Create a child

Read once; reread as needed:

- `<BWR_SKILL>/prompts/references/sessions/annotations.md`;
- `<BWR_SKILL>/prompts/references/sessions/presets.md`;
- `<BWR_SKILL>/prompts/references/bwr-workspace/reports.md`.

These References define general rules. The current Role or Workflow defines the exact annotations and Report path pattern.

Use them together to build the unique Report path and complete applicable annotation set.

Select the entry composer for the assigned Role under `<BWR_SKILL>/prompts/entries/`.

Resolve the entry-composer path and `<BWR_WORKSPACE>/ADDITIONAL-INSTRUCTIONS.md` before session creation.

Build the prompt in this order:

```text
@@<absolute entry-composer path>
@@<absolute BWR Workspace path>/ADDITIONAL-INSTRUCTIONS.md

BWR_SKILL: <absolute path>
BWR_WORKSPACE: <absolute path>
<applicable identifiers and exact input paths>
REPORT: <assigned absolute path>

MISSION
<specific work, limits, and expected result>
```

The `@@` paths must be absolute and resolved. Never put a variable inside an `@@` path.

Keep both `@@` markers before all dynamic values. TwiCC removes the optional marker when its file does not exist.

Pass every value required by the Role. Include only applicable Feature, Lot, Task, Attempt, Round, Pass, and correction identifiers.

Always set:

- the title, current project, assigned provider, and Role preset;
- the applicable annotations, including `bwr.status: working`;
- `mute_on_user_turn: true`;
- `question_widget: false`;
- `hidden: false`;
- the complete prompt.

Prefix the title with `- `.

Create the child. Keep the returned `session_id`.

A successful creation means that work started. It does not mean that work finished.

## Receive a child result

Each child returns two separate outputs:

- a complete Report at its assigned path;
- a concise Handoff message that names that path.

The child sends only the Handoff. The Report remains available at its path.

When you receive a Handoff, complete these steps in order:

1. Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/session/handoff.md`.
2. Check that the message matches the Contract and names the exact assigned Report path.
3. Check that the Report exists at that path.

The current Workflow must tell you whether to read the Report.

If it says `Read`, read the current Report. Use its contents only as that Workflow directs.

If it says `Do not read`, do not add the Report to your context. Route only its exact path.

If a required visible check fails, request a correction from the same child.

Otherwise, use the current Workflow to route the result.

When another child needs the Report, pass its exact path as an input. Do not copy or attach the Report contents.

## Send a follow-up

Keep the same child and Report path for follow-up work on the same assignment.

Before your first follow-up, load TwiCC's current `twicc-update-session` and `twicc-send-message` instructions.

Later, reload either set of instructions only when its procedure is no longer clear.

For each follow-up:

1. Set that child's `bwr.status` to `working`. Change no other annotation.
2. Send the follow-up to the saved `session_id`.

The child updates the same Report and returns a new Handoff.

Correct a stale `bwr.status` only from observed session state.

## Replace a failed child

A `FAILED` Handoff ends that child session. Never send it a follow-up.

The current Workflow decides whether the work stops, starts as a new logical assignment, or receives a replacement session.

When the work does not receive a replacement, stop any live process and retire the failed child before continuing.

For a replacement of the same logical assignment:

1. Load TwiCC's current process-stop instructions when needed.
2. Stop any live process for the failed child.
3. Retire that child with `bwr.status: failed`.
4. Create the replacement with the same assignment and Report path.

Recovery assigns a fresh Report path instead.

## Retire a child

Retire a child only when the current Workflow gives its result final acceptance.

If you have not loaded TwiCC's current `twicc-update-session` instructions, load them now.

Otherwise, reload them only when their procedure is no longer clear.

Then complete these steps in order:

1. Set the applicable terminal `bwr.status`.
2. Archive the child.
3. Hide the child.
