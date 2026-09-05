# Write an Amendment

Execute this Workflow for one coherent Human product decision after approval of the initial Current Spec.

Replace your complete applicable annotation set with:

```text
bwr.role: orchestrator
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: amendment
bwr.lot: <origin LOT, when applicable>
bwr.correction: <origin CORRECTION, when applicable>
```

Omit each inapplicable assignment key.

## Prepare the Amendment

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/amendments/amendment.md`.

Read the complete old Current Spec, exact Human decision, and every applicable source Report.

Read prior accepted Amendments when they affect the same behavior or preserved obligations.

Assign the next sequential run-wide Amendment number.

Choose the tracked Amendment path from applicable repository conventions. Keep it beside the Current Spec.

When no clear convention determines that path, present a suitable proposal to the Human. Continue after the Human confirms or replaces it.

## Write the candidate

Write the exact Human decision and why it is required.

Define every resulting observable behavior, state, transition, error, recovery rule, and constraint that applies.

Identify the existing product behavior that this decision must preserve.

Record the origin phase, Lot, source Report paths, and source Finding identities.

Keep the Amendment at product level. Leave implementation decomposition and technical design to later Plans and Task Designs.

## Self-review

Review the complete candidate against:

- the Amendment Contract;
- the exact Human decision;
- the old Current Spec and accepted Amendments;
- every source Report and Finding;
- direct and known transitive product effects;
- all behavior that must remain preserved;
- sufficient detail for an Updated Spec without another product choice.

Correct every issue found.

Repeat the complete self-review after each correction until it finds no remaining issue.

When another product decision remains necessary, use the Orchestrator decision-adjudication procedure.

Update the same Amendment candidate for a Human product decision. Leave an ordinary technical choice to its owner. Record a Human technical choice for its applying Plan or Task Design and keep the Amendment product content unchanged.

Update `PROGRESS.md` with:

- the Amendment number, candidate path, old Current Spec path, sources, and `reach` stage;
- the exact return Workflow and pending work interrupted by this Amendment.

When the interrupted work is Planning, include its complete Planning assignment, Plan path, and current candidate state in that return context.

## Exit

- Internally clean Amendment → execute `<BWR_SKILL>/prompts/workflows/amendments/reach-loop.md`.
- Human product decision → remain in this Workflow and apply the answer to the Amendment.
- Human technical choice → record its applying artifact and continue this Workflow.
- External blocker → record it in `PROGRESS.md` and present it to the Human.
