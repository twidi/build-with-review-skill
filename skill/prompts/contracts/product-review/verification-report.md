# Finding Verification Report Contract

One Finding Verification Report covers every Finding in one Product reviewer Report.

It identifies:

- the Product reviewer Report path;
- the exact reviewed subject;
- one verification result for every source Finding.

Use this shape for each result:

```text
## F<number> — <source Finding title>

Verdict: CONFIRMED | DISPROVED | UNVERIFIABLE

Checked: <concrete verification action>

Observed: <verification result>
```

Use `CONFIRMED` when the verification supports the complete Finding claim.

Use `DISPROVED` when the verification contradicts that claim.

Use `UNVERIFIABLE` when the source Finding lacks enough precision or evidence for either verdict. Also use it when a credible issue is framed as a `DECISION` but asks for an implementation mechanism instead of a product choice.

For an ordinary Finding, the verification addresses its observed fact, requirement, scope connection, every scenario condition, causal path, consequence, and evidence.

For a `DECISION`, verify the claimed Current Spec silence and that the unresolved choice changes product behavior.

Use `DISPROVED` when an authority resolves the question or evidence disproves its premise.

Every source Finding appears exactly once.

When the verification work is blocked by its environment, record the completed checks and exact blocker in the Report.
