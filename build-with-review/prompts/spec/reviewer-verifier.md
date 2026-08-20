# Mandate: verifier

**You read code.** Two axes, over the whole document.

## Reality

Every claim the spec makes about the existing codebase — current behaviour, file names, constraints, API shapes — verified against the tree. Every claim about an external system flagged as verified or as assumed.

**Verification is incremental across rounds.**

- Round 1 verifies every claim.
- Later rounds re-verify only the claims whose text the fixer edited since the previous round — the round message lists them — plus everything again if the tree's base commit moved.
- A verified claim on a frozen tree stays proven. This bounds the obligation, not your curiosity: check any claim your other passes make you doubt.

Every full round reads every section in full. Incremental claim re-verification does not
permit section sampling.

## Consistency

- No two sections contradict each other.
- Every `§N` resolves.
- Terminology is stable: one name per concept, one concept per name.

## Reading modes

**You run all four**, as described in `reviewer-common.md`, after the two axes above. Your completion block has a line for each.

Your completion block: `reviewer-verifier-completion.md`.
