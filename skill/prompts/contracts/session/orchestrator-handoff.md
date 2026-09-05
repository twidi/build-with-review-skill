# Orchestrator Handoff Contract

An Orchestrator succession transfers one completed Lot boundary to a fresh Orchestrator.

The succession context contains:

```text
BWR_SKILL: <absolute path>
BWR_WORKSPACE: <absolute path>
REPOSITORY: <absolute checkout path>
LOT: <new Lot identifier>
CURRENT_SPEC: <absolute path>
PLAN_TYPE: Lot
CONTROLLING_OBLIGATIONS: <every Current Spec heading path assigned to the new Lot>
GIT_COMMIT: <current commit>
PROGRESS: <absolute path>
GUIDE: <absolute path>
```

`PROGRESS` provides the current run state, provider defaults, and Review Concurrency.

`GUIDE` provides the Git guidance and approved Gate.

The successor returns one acceptance message:

```text
SUCCESSOR: ACCEPTED | BLOCKED
SUMMARY: <readiness or exact blocker>
```

`ACCEPTED` means that the successor has enough authoritative context, confirmed its Watchdog, and recorded its ownership in `PROGRESS.md`.

`BLOCKED` identifies missing or contradictory context that prevents ownership.
