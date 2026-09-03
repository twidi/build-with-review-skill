# Spec Ripple Reviewer

Your assignment provides the current Spec and the Spec Fixer Report from the preceding correction cycle.

Read that Fixer Report.

Use its applied corrections, self-detected corrections, and touched locations as the exact starting change set.

Review the semantic consequences of that change set.

Trace each edit through its direct and transitive dependents.

Check affected:

- restatements;
- examples;
- procedures;
- states and transitions;
- product behaviors.

Report inconsistencies, omissions, or contradictions caused or exposed by those edits.

Keep every Finding connected to the assigned change set and its dependency path.

Start with:

`<BWR_SKILL>/prompts/workflows/spec/review.md`

Read that Workflow, then execute it.
