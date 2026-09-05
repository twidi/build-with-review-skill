# Decision adjudication

Use this Reference when a question can require the Human.

An ordinary decision is a choice inside one role's authority.

`DECISION` is a Finding classification for an unresolved Human product decision. A reported `DECISION` is a claim until its classification is examined.

Classify the question in this order:

1. An applicable authority for that choice resolves it. This can be a Spec, Amendment, project rule, established behavior, recorded Human answer, or a Plan or Design inside its technical authority. Return the answer with its source.
2. Evidence disproves the premise. Return that evidence.
3. A technical role owns the choice inside the approved contract and scope. Route the choice to that owner.
4. The choice changes unresolved product behavior. It is a `DECISION` for the Human.
5. No reasonable technical solution avoids a grave, durable consequence beyond the approved Feature. It is a Human technical choice.

Difficulty, code volume, and implementation cost do not select a Human route.

A dependency, migration, interface, or architecture change is evidence to examine. Evaluate its actual scope, reasonable alternatives, reversibility, project conventions, and continuing consequences.

Record a Human product decision in `PROGRESS.md` and the applicable Spec or Amendment.

Record a Human technical choice, its scope, and its applying artifact in `PROGRESS.md`. Apply it through the applicable Plan or Task Design and resume that artifact's normal review loop.

Reuse an earlier Human answer only inside its recorded scope.
