# BWR Progress Contract

`PROGRESS.md` contains the durable operating state required to continue one BWR run.

Write it for direct Human and Orchestrator reading.

Use these sections:

```text
# BWR Progress

## Run

## Provider Choices

## Review Concurrency

## Lots

## Human Decisions

## Amendments

## Durable Log
```

## Current state

Keep current information in its applicable section.

Include:

- the Feature and goal;
- the repository and BWR workspace paths;
- the Current Spec path;
- the current Git commit;
- the current provider choices;
- the current Review Concurrency;
- completed Lots and the current Lot;
- accepted Human decisions;
- Amendment paths and outcomes;
- the final result when the run closes.

Update current values in place.

## Durable log

Append an entry only for an event needed to understand or resume the run.

Record durable route changes, blockers, and accepted outcomes.

Use exact artifact or Report paths when an event depends on their details.

Keep the text concise. Refer to existing artifacts instead of copying their contents.
