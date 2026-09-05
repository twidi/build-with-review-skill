# Review Report Contract

A Review Report is the durable result of one review assignment.

It has this shape:

```text
# <Role> Report

Subject: <exact assigned subject>
Verdict: CLEAN | FINDINGS | BLOCKED | FAILED

## Coverage

<what the complete mandate examined>

## Findings

<every admitted public Finding, or none>
```

`Subject` identifies the exact subject assigned by the current Workflow.

`Verdict` has one value:

- `CLEAN`: the reviewer completed the mandate and admitted no Finding;
- `FINDINGS`: the reviewer completed the mandate and reports every admitted Finding;
- `BLOCKED`: a resumable operational obstacle prevented completion of the mandate;
- `FAILED`: the assignment cannot complete or resume a valid review.

`Coverage` states what the reviewer examined against the complete mandate.

For `BLOCKED` or `FAILED`, it also states the exact obstacle or failure and the completed coverage.

`Findings` uses the Finding Contract for each admitted Finding. Use `none` when there is no admitted Finding.

The Report never contains private probability assessments or rejected observations.

The current Role or Workflow defines the review mandate and any additional required content.
