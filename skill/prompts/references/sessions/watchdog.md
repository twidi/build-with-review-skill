# Watchdog session

This Reference defines the Watchdog session attached to one Orchestrator.

Use the current TwiCC project and these settings:

- title `- BWR watchdog — <FEATURE>`;
- provider `claude_code`;
- preset `Minimal`;
- `mute_on_user_turn: true`;
- `question_widget: false`;
- `hidden: false`;
- annotations `bwr.role: watchdog`, `bwr.status: working`, and `bwr.feature: <FEATURE>`.

Use this prompt after replacing every placeholder with its current value:

```text
@@<BWR_SKILL>/prompts/entries/watchdog.md

BWR_SKILL: <absolute path>
BWR_WORKSPACE: <absolute path>
ORCHESTRATOR_SESSION_ID: <current session_id>
```

The script sends the Orchestrator a snapshot of its direct children on every tick.

It also sends each descendant parent a snapshot when that parent has an open direct child.

A descendant without an open direct child receives no Watchdog message.

Every recipient handles its snapshot through the Parent-session instructions.
