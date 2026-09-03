# Fix a Spec

Execute this Workflow for each correction input sent to the persistent Spec Fixer.

## Read the correction input

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/spec/current-spec.md`.

Read the complete current Spec and every newly assigned Reviewer Report.

Read every exact Human correction input assigned by your parent.

Keep the Spec Fixer Report complete across follow-ups. Preserve its earlier source paths, dispositions, corrections, and decisions.

## Process the Findings

Verify every new Finding against the complete current Spec and its authoritative inputs.

For an ordinary Finding, apply the correction or record contradictory evidence for declining it.

For a `DECISION` Finding:

- apply an exact Human decision supplied by your parent;
- otherwise record the unresolved question, context, options, consequences, and source Finding identity.

Do not select a product option yourself.

Apply each assigned Human correction exactly. Record its result and touched location.

When an assigned Human correction needs another unresolved product choice, return that new decision to your parent.

Keep related corrections coherent across the complete Spec. Record every additional correction found during this work.

## Self-review the Spec

Review the complete corrected Spec against:

- the accepted Human request and decisions;
- the Current Spec Contract;
- factual repository evidence;
- internal consistency;
- every Lot boundary and dependency.

Correct every issue that does not require a new product decision.

Record any newly exposed product decision with its location, context, options, and consequences.

Repeat the complete self-review after each correction until it finds no remaining correctable issue.

## Write the complete Report

Replace the assigned Fixer Report with its complete current state.

Set its stage to `Spec correction`. Include every processed Reviewer Report and every Finding disposition accumulated during the cycle.

Include every processed Human correction input, its result, and its touched locations.

Use this Handoff mapping:

| Current result | Handoff result | Handoff summary starts with |
|---|---|---|
| Complete corrected Spec | `READY` | `CORRECTED` |
| Required product decision | `BLOCKED` | `DECISION` |
| External operational blocker | `BLOCKED` | `BLOCKED` |

For `CORRECTED`, summarize the applied, declined, and self-detected correction counts.

For `DECISION`, identify the required question and its source Finding when one exists.

Complete the Child Handoff procedure. Then wait for your parent.

## Exit

- Handoff sent → wait for parent action.
- Follow-up received → execute this Workflow again with the new correction input.
