# Plan Contract

A BWR Plan defines one ordered construction scope from the Current Spec.

It contains:

- the Feature identifier;
- the exact plan identifier;
- the Current Spec path;
- the plan responsibility;
- the ordered Tasks;
- the additional sources required by its specialized Contract.

Reference a Spec obligation with its heading path and a short exact quote.

## Task

Each Task is one coherent construction unit.

Each Task contains:

```text
## Task <number> — <outcome>

Sources:
Depends on:
Achieves:
Probable locations:
To verify:

### Design
```

`Sources` identifies the controlling obligations.

`Depends on` identifies earlier Tasks required first.

`Achieves` states the completed outcome.

`Probable locations` guides discovery without freezing implementation details.

`To verify` states observable validation targets.

The `Design` section remains empty until the assigned Implementer writes and validates it.

## Detail boundary

Keep the Plan thin. Refer to Current Spec constraints instead of copying them.

Leave functions, signatures, commands, detailed tests, and implementation steps to the Task Design.
