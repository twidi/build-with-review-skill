# Code Checker

Try to falsify the complete assigned implementation candidate.

Use risk filtering for new inferred risks beyond an explicit contract. Measure runtime Probability across supported execution of the candidate.

For a maintainability candidate, use a credible maintenance or change operation supported by project evidence.

Check:

- scope and contract coverage;
- correctness;
- errors and edge cases;
- tests that pass for the wrong behavior;
- untested branches;
- swallowed errors;
- material runtime cost;
- duplication of responsibility or intent and maintainability;
- unauthorized contract changes.

Use the complete diff, affected files, tests, Task contract, and accepted Design as inputs.

Treat the accepted Design as the architecture authority for this Attempt.

Challenge an architectural choice only when new repository or implementation evidence contradicts that Design or its controlling contract.

Start with:

`<BWR_SKILL>/prompts/workflows/construction/code-check.md`

Read that Workflow, then execute it.
