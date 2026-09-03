# Finding Severity

This Reference is for reviewers that classify public Findings.

Severity measures consequence only.

Use one value:

## CRITICAL

Use `CRITICAL` when the problem can cause:

- data loss;
- a destructive action;
- a serious security failure;
- silent wrong delivery;
- loss of an authoritative decision.

## IMPORTANT

Use `IMPORTANT` when the problem can cause:

- incorrect behavior;
- blocked work;
- broken recovery;
- a false result that remains detectable or recoverable.

A concrete incorrect behavior is at least `IMPORTANT`, unless it is `CRITICAL`.

## MINOR

Use `MINOR` for limited friction, clarity, diagnostics, or maintainability impact.

A `MINOR` Finding has no credible wrong product result.

## Separate concepts

Probability never changes Severity.

`DECISION` is not a Severity. It identifies an unresolved product choice.

Every confirmed public Finding requires resolution, including a `MINOR` Finding.
