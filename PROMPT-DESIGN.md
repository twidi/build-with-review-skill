# BWR Prompt Design

## 1. Purpose

This document defines how BWR instructions are divided, loaded, and written.

It applies to `SKILL.md`, common prompts, Roles, Workflows, Contracts, and References. `BWR-DESIGN.md` defines the exact runtime inventory.

> A file contains only the context needed at the same time.

## 2. Loading model

BWR uses two loading modes.

### Immediate loading

Use TwiCC `@@` includes for fixed content required before the first action.

This content includes only applicable permanent context:

- role identity and authority;
- parent or child behavior;
- input and completion responsibilities;
- the short workflow map;
- an immediate Startup Workflow when the entry has one fixed startup route.

One entry composer composes the fixed files. The parent sends one absolute `@@` marker for that composer.

The entry composer contains only fixed `@@` includes. Its nested paths are relative to the composer. See `BWR-DESIGN.md` for the exact inventory, syntax, and limits.

### On-demand loading

Use an explicit path for details needed only during a later phase.

```md
Before starting Code Review:

Read once; reread as needed: <BWR_SKILL>/prompts/workflows/construction/code-review-loop.md

Execute that Workflow.
```

Do not use `@@` for later reads.

Reading adds context. It does not remove earlier content. This model reduces initial context and delays later context cost.

For a reusable fixed file, use `Read once; reread as needed:` followed by its path.

This means: read it before first use. Later, reread it only when its exact content is no longer clear.

For a mutable file, use the normal `Read` instruction at the exact point that requires its current content.

## 3. File model and ownership

Each file has one type, one audience, and one function.

| Type | Function | Normal content |
|---|---|---|
| Router | Select the next file | Conditions and paths |
| Role | Define permanent responsibility | Scope, authority, inputs, workflow map |
| Workflow | Run one active phase | Loads, actions, exits |
| Contract | Define a valid shared result | Required information and acceptance shape |
| Reference | Define consultable information | Terms, categories, rubrics |

A common prompt is a shared fixed fragment. It contains only permanent rules needed immediately by every reader.

A runtime Reference contains general rules shared by all its readers.

It does not catalogue case-specific values that most readers do not need.

The applicable Role or Workflow owns exact launch annotations, Report paths, and other case-specific values.

### General concept and local application

A file that defines a reusable concept contains only its invariant meaning and operation.

It does not contain the different procedures for every Role or Workflow that uses the concept.

Each applicable Role or Workflow:

1. routes to the general file;
2. states how the concept applies in that exact case;
3. provides only the values and procedure required for that case.

For example, the Review Concurrency Reference defines a limit and the general counting rule.

The Spec Review Workflow defines what occupies a place during a Spec full round.

The Product Review Workflow separately defines what occupies and releases a Product lens-chain place.

```md
Read once; reread as needed: <BWR_SKILL>/prompts/references/review/concurrency.md

For this Workflow, one Product lens chain occupies one review place until verification settles.
```

When two phases apply one concept differently, keep only their common invariant in the general file.

Put each difference in the phase that uses it.

Do not enumerate excluded cases when a positive applicability statement already gives the complete scope.

Do not introduce an unknown action only to prohibit it.

Use a negative instruction only when the action is a credible consequence of the agent's role, inputs, or normal tools.

Each rule has one owner file:

- shared permanent behavior → applicable common prompt;
- permanent role behavior → Role;
- phase behavior → Workflow;
- shared interface shape → Contract;
- definitions and rubrics → Reference;
- role-specific criteria → that role file.

Other files route to the owner. They do not summarize its rules.

Navigation can repeat a path. It does not repeat behavior.

## 4. File boundaries

Create a separate file when its content:

- belongs to a future phase;
- belongs to one conditional branch;
- has a distinct audience;
- is shared by some roles but not all roles;
- defines an independent Workflow, Contract, or Reference.

Keep content together when:

- one decision needs all of it;
- its rules must be interpreted together;
- separation causes repeated back-and-forth reading;
- the new file contains only another route.

Do not use line counts to choose a boundary.

## 5. Entrypoints and roles

### `SKILL.md`

`SKILL.md` is the minimal BWR entry point.

It contains only:

- discovery frontmatter;
- the BWR purpose;
- the high-level stage map;
- universal authority principles;
- role routing.

It does not contain phase procedures, report formats, rubrics, Gate details, or complete transitions.

```md
If you are the Orchestrator, read:

<BWR_SKILL>/prompts/common/workflow.md
<BWR_SKILL>/prompts/common/parent.md
<BWR_SKILL>/prompts/roles/orchestrator.md

Then read and execute the assigned Startup Workflow.

If your assignment gives another BWR Role, read `workflow.md` and `child.md`.

If that Role creates child sessions, also read `parent.md`.

Then read the assigned pure Role prompt.

Read and execute the starting Workflow named by the Role or assignment.
```

### Role files

A Role contains only facts that remain true for the full session:

- identity and owned decisions;
- authority limits;
- parent and child relationships;
- assigned inputs;
- general completion responsibility;
- short workflow map;
- first Workflow when its caller does not supply that Workflow.

A Role file contains no `@@` marker. An entry composer can include it. `SKILL.md` can also tell an agent to read it directly.

A Role states the general completion outcome. A Contract owns its exact shape.

```md
## Completion

Deliver the implementation result through the Handoff workflow.

Before handoff:

Read once; reread as needed: <BWR_SKILL>/prompts/workflows/construction/validate-and-deliver.md

Execute that Workflow.
```

## 6. Workflows and routing

A Workflow defines one executable phase.

```md
# Code Review

Execute this workflow now.

## Load

Read the Contracts and References required for this phase.

## Procedure

1. Run the assigned Code Checkers.
2. Resolve every confirmed Finding.

## Exit

- If clean, enter the next Workflow.
- If changes are required, return to implementation.
- If blocked, report the blocker.
```

`Load` names only context required now. `Procedure` contains observable actions. `Exit` defines every valid outcome and next route.

Only one Workflow is active at a time.

### Read and execute

These verbs have different meanings:

- `Read`: load a file into context;
- `Execute`: follow a Workflow until an exit.

Reading a Workflow is preparation, not completion. `common/workflow.md` owns this invariant. Every entry composer includes it. A manual Role load reads it first.

Use explicit routing:

```md
Enter the Handoff phase.

Read once; reread as needed: <BWR_SKILL>/prompts/workflows/construction/validate-and-deliver.md

Execute that Workflow until it reaches an exit condition.
```

The Role provides a short global map. Each Workflow provides only its local exits.

This navigation can name the same path twice. It prevents dead ends without duplicating procedure rules.

## 7. Contracts, references, and audience

### Contracts

A Contract describes one valid shared interface. The producer and consumer read the same file.

The Contract uses neutral language. Their Workflows define the actions.

```md
# Session Handoff Contract

A valid Handoff message contains:

1. the result;
2. the exact assigned Report path;
3. a short summary;
4. the expected parent action.

The Report is a separate file produced before the Handoff.
```

A Contract requires useful information. It does not require machine-oriented structure without a real machine consumer.

Do not add JSON, checksums, proof tokens, empty fields, or parser-oriented syntax.

One Handoff Contract owns the common return-message interface. A specialized Report Contract owns content required by its producer and consumer. It does not repeat the Handoff format.

All ordinary review roles use one common Review Report Contract. Role-specific mandates do not create copies of the same output shape.

One Implementer Report covers the complete Attempt. A failed Attempt adds its failure information to that Report. It does not create a second failure Report.

### References and audience

A shared file contains only information shared by every reader.

Do not mix transmitted results with private producer reasoning. Probability remains Reviewer-only.

```text
references/review/risk-filtering.md
    Applicable Reviewer only

contracts/review/finding.md
    Reviewer, consumer, and applicable fixer or verifier
```

Sharing a file means sharing all its content.

## 8. Fixed and dynamic content

Fixed content precedes all dynamic values.

A created session prompt uses this order:

1. fixed entry composer through `@@`;
2. optional Human instructions through `@@`;
3. dynamic assignment.

The dynamic suffix contains only:

- real BWR paths;
- current Lot or phase;
- assigned artifacts and Report path;
- specific mission;
- exceptional corrections or limits.

It does not repeat Role, Workflow, or Contract rules. This ordering supports provider prompt caching.

The parent resolves every top-level `@@` path before it creates the session. TwiCC does not replace variables or placeholders inside an `@@` marker.

```text
@@/opt/bwr/prompts/entries/construction/implementer.md
@@/srv/project/bwr_workspace/feature-a/ADDITIONAL-INSTRUCTIONS.md

BWR_SKILL: /opt/bwr
BWR_WORKSPACE: /srv/project/bwr_workspace/feature-a
```

The paths are illustrative. A runtime prompt contains real absolute paths. Relative `@@` markers exist only inside entry composers.

Common prompts and Roles can be included or read manually. They contain no active nested `@@` includes.

Workflows, Contracts, and References load their dependencies through on-demand reads, not `@@`.

A file can still show resolved top-level `@@` syntax when it defines session prompt composition.

A created Orchestrator entry can include its immediate Startup Workflow.

## 9. Writing language

### Direct instructions

Use short, operational sentences.

- Put one instruction in each sentence.
- Start with the expected action.
- Explain why only when it changes a decision.
- Omit normal agent capabilities and system history.
- Use `must` only for a real invariant.
- Prefer short lists to explanatory paragraphs.

Each instruction produces an action, artifact, decision, or state.

Prefer `read`, `execute`, `compare`, `write`, `run`, `fix`, `record`, `send`, `ask`, `update`, and `retire`.

Avoid `consider`, `ensure`, `be careful`, `keep in mind`, and `handle appropriately`.

```md
For each confirmed Finding:

- fix it; or
- record the blocker.

Do not continue while a confirmed Finding remains unresolved.
```

Understanding the instructions is not a phase exit.

### Explicit conditions

Use one observable condition and one action per branch.

```md
If the issue changes product behavior, ask the Human.

If the issue invalidates the Plan, start the Diagnostic workflow.

Otherwise, continue implementation.
```

Do not use `if needed` or `when appropriate` instead of a criterion.

If one rule needs many exceptions, review its owner or boundary.

### Stable vocabulary

Use Router, Role, Workflow, Contract, and Reference consistently.

Use these actions consistently:

- `Produce`: create the required result;
- `Send`: transmit a message;
- `Accept`: recognize a valid Handoff;
- `Return`: resume an earlier Workflow;
- `Retire`: archive and hide a non-Orchestrator child.

Use established BWR names without synonyms.

These include BWR workspace, Lot, Round, Pass, Attempt, Finding, Report, Handoff, Gate, and Current Spec.

### Human decisions

Internal instructions stay concise. Human decision requests stay complete.

Give the useful context, problem, impact, options, trade-offs, recommendation, and exact decision required.

Compression removes noise. It does not remove decision context.

### Examples, templates, and tools

Use one example only when the rule remains ambiguous without it.

Use a template only when its structure helps a real consumer. Its Contract owns the canonical template.

Describe the required result instead of one provider interface. Prefer `Create the child session as muted` to one CLI flag.

Use exact syntax only when syntax is part of the BWR contract.

Examples include `@@`, annotation names, `lot-1.10`, assigned paths, and Gate commands.

Load the applicable TwiCC skill when interface details are required.

## 10. Compatibility

Later loading does not create an implicit override.

- the Role bounds authority;
- the active Workflow operates within that authority;
- an applicable Contract defines a valid interface;
- a Reference defines terms and gives no authority;
- Human instructions control normal BWR choices within higher-level constraints.

These relationships are not a `last file wins` hierarchy.

Report conflicting BWR files. Do not select one silently.

Correct the owner files. Do not add another override layer.

## 11. Maintenance and compression

An agent failure does not automatically create a new rule.

Classify the cause first:

- missing instruction;
- ambiguous instruction;
- wrong owner file;
- present instruction not executed.

Then add, replace, move, or strengthen the minimum owning instruction.

Do not copy the correction elsewhere. Do not record failure history in runtime prompts.

Before accepting a file, ask of every sentence:

> Does this sentence change an agent decision or action?

Delete it when the answer is no.

Remove duplicated rules, future-phase details, unnecessary examples, normal capabilities, and rationale without decision value.

Do not enforce a line, word, or file count. Size follows simultaneous context need.

## 12. Validation

Validation stays lightweight and behavior-focused.

For each file, review:

- one function and clear audience;
- one owner for every rule;
- observable actions and explicit exits;
- no future-phase detail;
- no dead route;
- no sentence without decision value.

For each Role, inspect one representative path from entry to Handoff.

For the full graph, inspect missing includes, cycles, unreachable Workflows, unused Contracts, and duplicate owners.

Do not create Markdown snapshots or wording tests. Keep mechanical graph validation outside the deployed `skill/` directory.

## 13. Scope of this document

This document guides BWR authors. Runtime sessions do not load it.

Only behavior-changing rules belong in runtime files. Authoring advice stays here.

`BWR-DESIGN.md` defines the exact file inventory, include graph, audiences, owner responsibilities, and on-demand routes.
