# Review Concurrency

This Reference is for an Orchestrator that launches concurrent reviews.

Use the current Human-selected Review Concurrency value from `PROGRESS.md`.

The value limits the number of review places that can operate concurrently.

The active Workflow defines:

- whether Review Concurrency applies;
- what occupies one place;
- when that place becomes free.

Before each launch, count the occupied places defined by that Workflow.

Launch a new review unit when the count is below the current value.

## Changes

The Human can change Review Concurrency during the run.

Record the new value in `PROGRESS.md`. Use it for later launches.
