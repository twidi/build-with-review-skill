# Finding Severity

Use this Reference when a reviewer classifies public Findings.

Severity measures how seriously a Finding prevents the reviewed subject from fulfilling its assigned authoritative contract.

Assess the subject as accepted unchanged. Use the direct credible causal consequence after existing protections and normal recovery.

## CRITICAL

Use `CRITICAL` when:

- a required principal outcome becomes impossible;
- a required flow has no valid continuation;
- the subject cannot fulfill its central responsibility;
- authoritative data or a decision is silently lost or corrupted;
- an important destructive action occurs;
- a serious security failure occurs;
- the result appears valid while the central purpose fails.

## IMPORTANT

Use `IMPORTANT` when significant behavior, an obligation, or a result is wrong, but the central responsibility remains possible.

Examples include:

- a secondary path is blocked;
- an obligation is partially fulfilled;
- a reasonable workaround remains;
- the error is detectable or recoverable;
- a maintainability defect creates a concrete future-error risk.

## MINOR

Use `MINOR` when the result remains correct. The impact is limited to friction, clarity, diagnostics, local divergence, or maintenance cost.

## Decision order

1. Can the subject fulfill its central responsibility? If not, use `CRITICAL`.
2. Is significant behavior, an obligation, or a result wrong? If yes, use `IMPORTANT`.
3. Does the result remain correct with limited impact? If yes, use `MINOR`.

Use the direct consequence. Do not add another independent failure or the worst imaginable downstream result.

Probability never changes Severity. `DECISION` identifies an unresolved product choice instead of a Severity.

Every confirmed public Finding requires resolution.
