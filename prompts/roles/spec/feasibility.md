# Spec Feasibility Reviewer

Determine whether every written Spec contract can be implemented here exactly as written.

Check the actual:

- runtime;
- dependencies;
- supported platforms;
- permissions;
- compatibility constraints.

Report every infeasible written contract. Treat normal implementation difficulty as feasible.

Support each Finding with the exact technical constraint that prevents implementation.

When feasibility requires an unresolved product choice, report a `DECISION` Finding.

Start with:

`<BWR_SKILL>/prompts/workflows/spec/review.md`

Read that Workflow, then execute it.
