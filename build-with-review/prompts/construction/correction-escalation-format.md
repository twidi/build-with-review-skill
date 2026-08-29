# Ordinary Correction escalation artifact format

This file defines the only schema-1 structural escalation Markdown artifact.
Use it only after an exact Correction `attempt.failed` with classification `C3.9d`.

The canonical path is:

```text
corrections/<built>/round-<round>-escalation.md
```

The file is UTF-8. It uses LF line endings and ends with one LF. All headings and
field names below are exact and start in column zero. The file has no later section.

## Closed grammar

```text
# <subject> — <built> correction round <round> escalation

Schema: 1
Built unit: <built>
Correction round: <round>
Correction authority: <proof>
Current commit: <commit>
Structural blocker: <attempt.failed proof>

## Accepted contributions
Task 1: <commit> · <gate sha256> · satisfies F1, F2

## Unresolved account

### F1 - <required outcome>
Origins: correction/c1/F1, correction/c2/F1
Sources: unlooked/F1, user/F1, meaning/F1, quality/F1, coverage/F1
Accepted contributions: task 1, task 2
Blocker: <attempt.failed proof>
Required outcome: <required outcome>

## Required sub-lot outcome
<required outcome>

## Final-checker consumer requirements
Obligation <sha256>: design · first-design-manifest · <required outcome> · F1
Obligation <sha256>: code · first-code-manifest · <required outcome> · F1
```

The accepted-contribution section can be empty. Keep the blank line after its heading.
Otherwise, tasks form the exact contiguous accepted prefix. Each commit and gate equals
the authenticated accepted success. `satisfies` names every escalation item that uses it.

The unresolved items form exactly `F1` through `FK`. Each item owns one structural
outcome. It can combine several exact Correction origins and Product sources. It cannot
name an absorbed, resolved or foreign source.

`Origins` uses numeric Correction-round and finding order. `Sources` uses the canonical
Product mandate order: `unlooked`, `user`, `meaning`, `quality`, `coverage`, then numeric
finding order. Both fields are non-empty, unique comma-space lists.

`Accepted contributions` is `-` or a unique numeric `task N` list. It equals the exact
accepted contribution subset needed by that item. Every `Blocker` equals the exact
`attempt.failed` proof printed by the failure closer.

The item outcome, `Required outcome`, the global required sub-lot outcome, and every
consumer requirement outcome are byte-identical. Consumer requirements are sorted and
unique by obligation SHA. They cover every and only the carried final-checker obligations.

## Bounded self-review

Before the fresh `correction-round-escalate.sh` call, inspect this file once against the
current Correction artifact, accepted task successes, exact failure proof, unresolved
source findings, and current final-checker set. Correct one local format or copied-field
error before publication. Do not change the journal, source artifact, plan or failure.

The helper parses and authenticates this file before object publication. A refusal keeps
the file and every durable owner unchanged. Stop on that refusal. Do not publish another
artifact. After a retained owner exists, rerun only the public two-argument helper. Never
read, copy, infer, replace or remove its marker.
