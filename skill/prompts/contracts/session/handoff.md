# Session Handoff Contract

A Handoff is the common interface between one session and its direct parent.

A valid Handoff message has this shape:

```text
RESULT: READY | BLOCKED | FAILED
REPORT: <assigned absolute path>
SUMMARY: <one short result>
PARENT ACTION: <next expected action, or none>
```

`RESULT` has one value:

- `READY`: the current deliverable is complete and ready for routing;
- `BLOCKED`: work can resume after specified information, choice, or action;
- `FAILED`: the current assignment ended without a valid deliverable.

`REPORT` contains the exact assigned absolute path.

`SUMMARY` states the concrete result or obstacle. `PARENT ACTION` states the expected next action or `none`.
