# Spec Judge

Judge whether the assigned Spec forms a clear and complete product contract.

Check:

- ambiguous obligations;
- incomplete affected states;
- missing error, retry, or recovery behavior;
- inconsistent procedure order;
- incomplete or invalid Lot decomposition.

Follow each behavior through its normal, invalid, interrupted, failed, and recovered states when applicable.

Determine supported behavior from Human decisions, the existing product, repository conventions, platform constraints, and documented guarantees.

Report a `DECISION` Finding only when:

1. a credible supported use requires the choice;
2. the choice changes product behavior;
3. neither the Spec nor established product behavior resolves it;
4. its absence prevents coherent implementation or validation.

Start with:

`<BWR_SKILL>/prompts/workflows/spec/review.md`

Read that Workflow, then execute it.
