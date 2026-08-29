# Post-AMENDMENT Correction escalation artifact format

This file defines the only schema-2 structural escalation Markdown artifact.
Use it only when the Correction AMENDMENT return route is `sublot`.

The canonical path is:

```text
corrections/<built>/round-<round>-escalation.md
```

The file is UTF-8, uses LF line endings, ends with one LF, and contains no trailing
section. All headings and field names below are exact and column-zero.

## Closed grammar

```text
# <subject> — <built> correction round <round> escalation

Schema: 2
Producer: post-amendment-return
Built unit: <built>
Correction round: <round>
Correction opening: <proof>
Previous authority: <proof>
AMENDMENT opening: <proof>
AMENDMENT commit: <proof>
Return SHA-256: <sha256>
Current commit: <commit>
Current tree: <tree>
Current gate: <sha256>
Correction artifact SHA-256: <sha256>
Structural blocker: <proof>

## Accepted contributions
Task 1: <attempt.succeeded proof> · <commit> · <gate sha256>

## Unresolved account

### F1 - <required outcome>
Origins: correction/c1/F1, correction/c2/F1
Sources: unlooked/F1, user/F1, meaning/F1, quality/F1, coverage/F1
Accepted contributions: task 1, task 2
Blocker: <proof>
Required outcome: <required outcome>

## Required sub-lot outcome
<required outcome>

## Final-checker consumer requirements
Obligation <sha256>: design · first-design-manifest · <required outcome> · F1
Obligation <sha256>: code · first-code-manifest · <required outcome> · F1
```

The accepted-contribution section can be empty. Keep the blank line after its heading.
Otherwise, tasks form the exact contiguous accepted prefix. Each proof, commit, and gate
equals the authenticated return contribution.

The unresolved items form exactly `F1` through `FK`. Each item corresponds to one and
only one remaining source finding from the return. An item can combine several exact
Correction origins and Product sources. It cannot name an absorbed or foreign source.

`Origins` uses numeric Correction-round and finding order. `Sources` uses the canonical
Product mandate order: `unlooked`, `user`, `meaning`, `quality`, `coverage`, then numeric
finding order. Both fields are non-empty, unique comma-space lists.

`Accepted contributions` is `-` or a unique numeric `task N` list. It equals the exact
preserved contribution subset needed by that item. The item `Blocker` equals the return's
authenticated structural blocker. The item outcome, `Required outcome`, the global
required sub-lot outcome, and every consumer requirement outcome are byte-identical.

Consumer requirements are sorted and unique by obligation SHA. They cover every and only
the carried final-checker obligations. Checker and manifest phase must match. Each one
names the exact escalation item derived from its immutable source and current consumer
task. Do not select the first item or use a fallback item.

## Bounded self-review

Before `correction-round-escalate.sh` runs, inspect this file once against the immutable
return object, current schema-2 Correction artifact, accepted successes, blocker, and
canonical retry transition. Correct one local formatting or copied-field error before
publication. Do not change the return, journal, source artifact, plan, or producer proof.

The helper parses this file before publication. A parser or authority refusal preserves
the file and durable owner. Stop on that refusal. Do not publish an alternative artifact.
