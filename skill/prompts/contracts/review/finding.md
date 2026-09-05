# Finding Contract

A public Finding states one checkable problem within the assigned review scope.

## Ordinary Finding

Use this shape:

```text
## <CRITICAL | IMPORTANT | MINOR> F<number> — <checkable claim>

Where: <file and lines, user path, or document passage>

Scope edge: <direct connection with the reviewed subject>

Observed: <observable fact>

Expected: <required behavior or property>

Consequence: <what can go wrong>

Evidence: <reproduction, citation, or absence search>
```

The heading states a claim that another session can verify.

`Where` identifies the affected location. `Scope edge` explains why the Finding belongs to this review.

`Observed`, `Expected`, and `Consequence` separate fact, requirement, and impact.

`Evidence` uses a reproduction, a citation, or an explicit absence search.

## DECISION Finding

Use this shape when the Current Spec does not resolve a required product choice:

```text
## DECISION F<number> — <unresolved product question>

Where: <where the question appears>

Scope edge: <connection with the reviewed subject>

Spec silence: <what the Current Spec does not decide>

Evidence: <observed behavior or contradiction>

Options:
- <option and user consequence>
- <option and user consequence>
```

The reviewer presents the choice. The reviewer does not select an option or propose an implicit fix.

## Identity and privacy

Finding identifiers start at `F1` and are local to one Review Report.

The stable identity is `<report-path>#F<number>`.

When the same assignment overwrites its Report, every surviving Finding keeps its identifier. Never reuse a removed identifier. Give each new Finding the next identifier never used in that Report.

A public Finding never contains its private Probability assessment or rejected review observations.
