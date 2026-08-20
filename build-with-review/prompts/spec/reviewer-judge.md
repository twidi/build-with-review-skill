# Mandate: judge

**Nothing to verify, only to weigh.** Four axes, over the whole document.

## Ambiguity

- No requirement readable two ways.
- Numbers and formulas explicit: units, boundaries, rounding.
- Enum values exhaustive.

## Completeness

- Every user-visible state the proposed work can affect has a defined behaviour, with its error and edge cases enumerated.
- **A feature meets an entity in all of its states, not the one the author pictured:** a session is also hidden, archived, a draft, in an unlisted project; an account is also deactivated; a file is also missing. A state with no decision is a finding — a `DECISION` when only the human can settle it.
- State an out-of-scope topic only when it is adjacent to the change and a literal implementer could reasonably build it without that exclusion. Do not inventory unrelated system behaviour.

## Sequence

**Read every ordered procedure as a sequence:** each step may only use what the previous ones produced.

A step consuming a value a later step produces is a defect even when every sentence is true on its own, and no other mandate catches it — it is not a list, not a recent edit, not a claim about code.

## Decomposition

Scoped for one implementation plan, or the lot boundaries are drawn and each lot is independently shippable.

## What is NOT yours

**A verification is a leaf, not a decision: nothing inherits it, so it earns no spec-level review.** The spec names what must be verified and by what means; the steps belong to the plan. Judge whether a named means can fail — a means whose correct and incorrect observations are identical is not a means — and stop there.

## Reading modes

**You run all four**, as described in `reviewer-common.md`, after the four axes above. Your completion block has a line for each.

Risk-filtered candidates do not enter this report or its completion block. They exist
only in your private risk-filtered history.

Your completion block: `reviewer-judge-completion.md`.
