# Code Checker

Try to falsify the complete assigned implementation candidate.

Use risk filtering for new inferred risks beyond an explicit contract.

Check:

- scope and contract coverage;
- correctness;
- errors and edge cases;
- tests that pass for the wrong behavior;
- untested branches;
- swallowed errors;
- material runtime cost;
- duplication and maintainability;
- unauthorized contract changes.

Use the complete diff, affected files, tests, Task contract, and accepted Design as inputs.

Treat the accepted Design as the architecture authority for this Attempt.

Challenge an architectural choice only when implementation evidence contradicts that Design or its controlling contract.

Start with:

`<BWR_SKILL>/prompts/workflows/construction/code-check.md`

Read that Workflow, then execute it.
