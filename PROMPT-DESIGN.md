# BWR Prompt Design

## 1. Purpose

This document defines how BWR instructions are divided, loaded, and written.

It applies to `SKILL.md`, prompts, workflows, contracts, and references. It does not define the final file inventory.

> A file contains only the context needed at the same time.

## 2. Loading model

BWR uses two loading modes.

### Immediate loading

Use TwiCC `@@` includes for fixed content required before the first action.

This content includes only applicable permanent context:

- role identity and authority;
- parent or child behavior;
- assigned inputs and completion responsibility;
- the short workflow map.

One entry prompt composes the fixed files. The parent sends one absolute `@@` marker for that entry prompt.

Nested fixed includes use paths relative to their containing file. See `BWR-DESIGN.md` for the TwiCC syntax and limits.

### On-demand loading

Use an explicit path for details needed only during a later phase.

```md
Before starting Code Review, read and execute:

<BWR_SKILL>/prompts/construction/code-review.md
```

Do not use `@@` for later reads.

Reading adds context. It does not remove earlier content. This model reduces initial context and delays later context cost.

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
If you are the Orchestrator, read and execute:

<BWR_SKILL>/prompts/orchestrator.md

If your assignment gives another BWR role, execute its assigned entry prompt.
```

### Role files

A Role contains only facts that remain true for the full session:

- identity and owned decisions;
- authority limits;
- parent and child relationships;
- assigned inputs;
- general completion responsibility;
- short workflow map;
- first Workflow.

A Role states the general completion outcome. A Contract owns its exact shape.

```md
## Completion

Deliver the implementation result through the Handoff workflow.

Before handoff, read and execute:

<BWR_SKILL>/prompts/construction/handoff.md
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

Reading a Workflow is preparation, not completion. One shared runtime prompt owns this invariant. Every applicable Role includes it.

Use explicit routing:

```md
Enter the Handoff phase.

Read and execute:

<BWR_SKILL>/prompts/construction/handoff.md

Continue until that workflow reaches an exit condition.
```

The Role provides a short global map. Each Workflow provides only its local exits.

This navigation can name the same path twice. It prevents dead ends without duplicating procedure rules.

## 7. Contracts, references, and audience

### Contracts

A Contract describes one valid shared interface. The producer and consumer read the same file.

The Contract uses neutral language. Their Workflows define the actions.

```md
# Implementer handoff contract

A valid handoff contains:

1. an implementation Report;
2. a return message.

The Report contains completed work, changed files, decisions, the final Gate result, and blockers.

The return message contains the result, Report path, final Gate status, and any blocker.
```

A Contract requires useful information. It does not require machine-oriented structure without a real machine consumer.

Do not add JSON, checksums, proof tokens, empty fields, or parser-oriented syntax.

One Contract covers a Report and its return message by default. Split them only for different consumers or lifecycles.

### References and audience

A shared file contains only information shared by every reader.

Do not mix transmitted results with private producer reasoning. For example, reviewer likelihood remains Reviewer-only.

```text
references/review/reviewer-likelihood.md
    Reviewer only

contracts/reviewer-verifier-handoff.md
    Reviewer and Verifier
```

Sharing a file means sharing all its content.

## 8. Fixed and dynamic content

Fixed content precedes all dynamic values.

The child prompt uses this order:

1. fixed entry prompt through `@@`;
2. optional Human instructions through `@@`;
3. dynamic assignment.

The dynamic suffix contains only:

- real BWR paths;
- current Lot or phase;
- assigned artifacts and Report path;
- specific mission;
- exceptional corrections or limits.

It does not repeat Role, Workflow, or Contract rules. This ordering supports provider prompt caching.

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

Examples include `@@`, annotation names, `LOT.1.10`, assigned paths, and Gate commands.

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

Do not create Markdown snapshots, wording tests, or a BWR validation script.

## 13. Scope of this document

This document guides BWR authors. Runtime sessions do not load it.

Only behavior-changing rules belong in runtime files. Authoring advice stays here.

The next design step defines the exact file inventory, include graph, audiences, owner responsibilities, and on-demand routes.
