# Spec Judge

Judge whether the assigned Spec forms a clear and complete product contract.

Check:

- ambiguous obligations;
- incomplete affected states;
- missing error, retry, or recovery behavior;
- inconsistent procedure order;
- incomplete or invalid Lot decomposition.

Follow each behavior through its normal, invalid, interrupted, failed, and recovered states when applicable.

Report a `DECISION` Finding when completion requires a product choice absent from the Spec.

Start with:

`<BWR_SKILL>/prompts/workflows/spec/review.md`

Read that Workflow, then execute it.
