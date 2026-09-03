# Fixer Report Contract

A Fixer Report records the complete current result of one correction assignment.

It contains:

- the current stage and corrected target path;
- every processed reviewer Report path;
- one disposition for every input Finding;
- every self-detected correction;
- the touched locations and checked relevant dependents;
- the complete target self-review result;
- any unresolved blocker or required product decision.

## Finding dispositions

Identify each Finding with `<reviewer-report-path>#F<number>`.

Use one disposition:

- `APPLIED`: state the correction and its location;
- `DECLINED`: state the contradictory evidence.

Every input Finding appears exactly once.

## Self-detected corrections

For each self-detected correction, state:

- the original problem;
- the correction;
- the affected location.

Number these entries locally as `S1`, `S2`, and later values.

## Completion

A ready Report confirms that the fixer self-reviewed the complete corrected target.

A blocked Report states the exact missing information, external action, or unresolved product decision.
