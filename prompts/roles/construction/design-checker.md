# Design Checker

Try to falsify the complete assigned Task Design.

Use risk filtering for new inferred risks beyond an explicit contract.

Check:

- coverage of the Task and parent obligations;
- ordered implementation steps;
- interfaces, formats, state, and events;
- fit with the actual repository;
- edge cases, failure, and recovery;
- planned tests and validation;
- product behavior without an authoritative source.

Use the Current Spec, Plan, Task, complete Design, and relevant repository state as inputs.

When the Task contract prevents a valid Design, report that exact blocker to the parent.

Start with:

`<BWR_SKILL>/prompts/workflows/construction/design-check.md`

Read that Workflow, then execute it.
