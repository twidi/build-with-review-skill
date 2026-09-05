# Finding Contract

A public Finding states one checkable problem within the assigned review scope.

## Ordinary Finding

Use this shape:

```text
## <CRITICAL | IMPORTANT | MINOR> F<number> — <checkable claim>

Where: <file and lines, user path, or document passage>

Scope edge: <direct connection with the reviewed subject>

Scenario: <complete minimal scenario, or direct inspection>

Observed: <observable fact>

Expected: <required behavior or property and its authoritative source>

Consequence: <what can go wrong>

Evidence: <reproduction, citation, or absence search>
```

The heading states a claim that another session can verify.

`Where` identifies the affected location. `Scope edge` explains why the Finding belongs to this review.

For a conditional Finding, `Scenario` states the initial state, necessary actions or events, their order, and independent conditions.

For a direct fact, use `Scenario: direct inspection`.

`Observed`, `Expected`, and `Consequence` separate fact, requirement, and direct impact.

`Evidence` establishes every necessary scenario condition and the causal path. It uses a reproduction, citation, or explicit absence search.

State the required outcome. Do not prescribe an implementation mechanism.

One Finding normally represents one correction obligation. Group occurrences with the same cause, expected outcome, consequence, and correction logic.

Split occurrences when their behavior, cause, Severity, owner, consequence, correction logic, or validation differs. Keep each Finding independently verifiable and traceable.

## DECISION Finding

Use this shape only when the Current Spec and established product behavior do not resolve a required Human product choice:

```text
## DECISION F<number> — <unresolved product question>

Where: <where the question appears>

Scope edge: <connection with the reviewed subject>

Scenario: <supported use that requires the decision>

Spec silence: <what the Current Spec does not decide>

Evidence: <observed behavior or contradiction>

Options:
- <option and user consequence>
- <option and user consequence>
```

The reviewer presents the product choice. The classification is a claim for later examination.

An implementation mechanism is not a `DECISION`. Report the required product outcome and leave the mechanism to its technical owner.

The reviewer does not select an option or propose an implicit fix.

## Identity and privacy

Finding identifiers start at `F1` and are local to one Review Report.

The stable identity is `<report-path>#F<number>`.

When the same assignment overwrites its Report, every surviving Finding keeps its identifier. Never reuse a removed identifier. Give each new Finding the next identifier never used in that Report.
