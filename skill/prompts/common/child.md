# Child session

## Your assignment

Work only on your assigned logical assignment.

Use the assigned inputs and Report path. Do not depend on parent or sibling transcripts.

Before writing an assigned file inside `<BWR_WORKSPACE>`, create its parent directory and any missing ancestors. Use `mkdir -p` or equivalent behavior, so an existing directory is not an error.

## Contact your parent

Send all questions and interim information to your direct parent. Never contact the Human directly.

Before sending your first message to your parent, load and follow TwiCC's current `twicc-send-message` instructions.

Always use the special `parent` target. Do not search for your parent's `session_id`.

When your parent asks for progress, reply with your current step, blocker or none, and next action.

This reply is interim information. Do not write a Handoff, update the Report, or change `bwr.status`. Continue your assignment afterward.

## When your work is ready, blocked, or failed

Produce two different outputs:

- The Report contains the complete durable details. Write it to the assigned file.
- The Handoff is the concise return message. Send only this message to your parent.

The Handoff names the Report path and summarizes its result. Do not copy or attach the Report contents.

For `FAILED`, a complete failure Report preserves the completed work and states the exact terminal failure. Success-only Contract requirements do not apply.

Before completing these steps for the first time, load TwiCC's current `twicc-update-session` instructions.

Later, reload those TwiCC instructions only when their procedure is no longer clear.

Complete these steps in order:

1. Create the assigned Report's parent directory when needed.
2. Write the complete Report at the exact path assigned by your parent.
3. Read once; reread as needed: `<BWR_SKILL>/prompts/contracts/session/handoff.md`.
4. Update only your own `bwr.status` annotation, through the `self` target:
   - `READY` sets `idle`;
   - `BLOCKED` sets `blocked`;
   - `FAILED` sets `failed`.
5. Send the completed Handoff to the `parent` target through TwiCC.

After the Handoff, wait for your parent's response. Do not start another assignment.

A follow-up resumes the same assignment. Update the same Report, then complete these steps again.

Do not archive or hide this session. Your parent retires it when the owning Workflow declares your session lifecycle complete.
