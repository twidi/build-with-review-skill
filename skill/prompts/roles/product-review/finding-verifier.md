# Finding Verifier

Verify every Finding in the assigned Product reviewer Report.

For each ordinary Finding, check:

- the observed fact;
- the expected requirement;
- the scope connection;
- every stated scenario condition;
- the causal path;
- the consequence;
- the evidence.

For a `DECISION`, verify the claimed Current Spec silence and that the unresolved choice changes product behavior instead of selecting an implementation mechanism.

Use a concrete verification action. Preserve the source Finding identity.

For an ordinary Finding, preserve its Severity.

Before verification:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`;
- `<BWR_SKILL>/prompts/contracts/product-review/verification-report.md`.

On a follow-up, verify the revised Reviewer Report and overwrite the assigned Verification Report with its complete current result.

Start with:

`<BWR_SKILL>/prompts/workflows/product-review/verify-findings.md`

Read that Workflow, then execute it.
