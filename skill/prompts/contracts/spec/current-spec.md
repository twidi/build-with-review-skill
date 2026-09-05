# Current Spec Contract

The Current Spec is the complete authoritative product contract for one Feature.

An Updated Spec follows the same Contract. It replaces the earlier Current Spec when the Amendment Workflow commits it after clean Reach and Consolidation review.

Use flexible headings that clearly cover:

- the goal;
- users and their expected result;
- scope and out-of-scope behavior;
- product behaviors;
- states and transitions;
- errors, retries, and recovery;
- important interactions;
- global constraints;
- verification behaviors and proof boundaries;
- the ordered root Lot breakdown;
- dependencies between Lots.

Each Lot states:

- its exact stable identifier;
- its responsibility;
- its product obligations;
- its dependencies;
- its required end state.

List root Lots in execution order. A root Lot can depend only on earlier root Lots.

Initial Lot identifiers use `lot-<number>`, such as `lot-1` and `lot-2`.

Keep every Lot identifier as a string. Never convert a later identifier such as `lot-1.10` to a number.

An approved Current Spec resolves every necessary product choice.

The Spec defines product intent and observable obligations.

Plans and Task Designs define later implementation decomposition, commands, technical interfaces, and report details.

Reference one Spec obligation by its heading path and a short exact quote.
