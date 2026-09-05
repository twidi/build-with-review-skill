# Implementer Report Contract

One Implementer Report records the complete current history and result of one Attempt.

It contains:

- the Feature, Lot, Task, and Attempt identifiers;
- the delivered result;
- every Design Review round;
- every Code Review round;
- every checker Finding disposition;
- targeted validation performed;
- every new validation command and its recommended Gate group;
- every simple Gate command replacement as `<old command> -> <new command>`;
- the complete final Gate record;
- the created commit, when applicable;
- failure or blocker information, when applicable.

## Review rounds

For each Design or Code Review round, record:

- the checker Report path;
- its verdict;
- each Finding disposition.

Identify a Finding with `<checker-report-path>#F<number>`.

Use `APPLIED` for a completed correction. Use `DISAGREED` with concrete contradictory evidence.

## Validation

Separate targeted validation from the final Gate.

Declare the final Gate as `PASSED`, `FAILED`, or `NOT RUN`.

For `PASSED`, give a concise summary of the commands and their successful results.

For unresolved `FAILED`, summarize the blocking failures and useful evidence.

Do not copy raw command output. A corrected Gate failure does not remain in the final Report.

Record every newly created validation command and its recommended execution group.

Record every simple Gate command replacement as `<old command> -> <new command>` and confirm equivalent validation coverage.

## Attempt outcome

A ready Report contains a `PASSED` final Gate and the successful Attempt commit identifier.

A failed Report states the exact unresolved failure and any preservation commit.

A blocked Report states the exact external information or action required.

The same Report covers every outcome.
