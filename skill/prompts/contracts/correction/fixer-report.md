# Fixer Report Contract

A Fixer Report records the complete current result of one correction assignment.

It contains:

- the current stage and corrected target path;
- every processed reviewer Report path;
- every processed Human correction or decision, when applicable;
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

Contradictory evidence can address the Finding's scenario, necessary conditions, scope, obligation, observed behavior, causal path, consequence, or evidence.

A valid `DECLINED` disposition shows that at least one of those elements is false. Correction difficulty or architecture preference does not contradict a Finding.

Every input Finding appears exactly once.

For each processed Human correction or decision, state its applied result and location.

## Self-detected corrections

For each self-detected correction, state:

- the original problem;
- the correction;
- the affected location.

Number these entries locally as `S1`, `S2`, and later values.

## Completion

A ready Report confirms that the fixer self-reviewed the complete corrected target.

A blocked Report states the exact missing information, external action, or unresolved product decision.
