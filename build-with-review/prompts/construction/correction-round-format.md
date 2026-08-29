# Correction Round artifact format

This file is the complete controller-writing contract for a Correction Round artifact.
Read it before creating or changing an unclosed artifact.

The canonical path is:

```text
<workspace>/corrections/<built>/round-<N>.md
```

The file is UTF-8. It uses LF line endings and ends with one LF. Its maximum size is
1,048,576 bytes. Every structural heading and field below is exact and ordered.

Backtick and tilde fences use CommonMark structure. An opening or closing fence permits
zero through three ASCII spaces. A structural heading inside a real fence is data. A
fence cannot replace a required structural heading.

## Schema 1

Use schema 1 for the initial artifact and every ordinary bounded revision.

```markdown
# <subject> — <built> correction round <N>

Schema: 1
Built unit: <built>
Correction round: <N>
Parent position: c<N-1>
Parent generation SHA-256: <64 lowercase hex>
Source reviewed commit: <full commit SHA>
Source accepted gate: <64 lowercase hex>
Correction base commit: <full commit SHA>
Correction base gate: <64 lowercase hex>
Source pass: p<M>
Source opening: <journal-line proof>
Source findings: reports/product-review/<root>/<built>-c<N-1>-p<M>-confirmed.md
Source findings SHA-256: <64 lowercase hex>

## Route account
Spec: current and settled
Human decisions: settled
Controller contract: preserved
Ownership: preserved
Decomposition: preserved
Coordination: bounded
Repetition: independent
Reason: <complete-set bounded reason>

## Finding coverage
F1: task 1
F2: tasks 1, 2

---

## Task 1 - <title>

Covers: F1, F2
Depends on: -
Consumes final-checker obligations: -
Achieves:
  - <required product outcome>
Files: <expected implementation area>
To verify: <observable production behavior>

### Design
[written at correction task Design - see below]

### Disagreement
[optional - same accepted alternative contract as an ordinary task]
```

The route `Repetition` value is `independent` or `reassessed-bounded`. A
`reassessed-bounded` reason identifies the related earlier round. It explains why the
same root cause did not survive.

`Finding coverage` contains exactly `F1..F<K>`. Each finding names one sorted unique task
set. Use `task` for one task and `tasks` for two or more tasks.

Each task starts after one exact structural `---`. Tasks are exact and sequential.
Dependencies are sorted, unique, and lower than the current task.

`Covers` is the exact sorted finding set assigned to that task. Every finding-to-task
relation appears in both coverage directions. No finding or task can be empty.

`Consumes final-checker obligations` is `-` or one sorted unique list of 64-character
lowercase obligation hashes. It is `-` until an authenticated producer maps obligations
to the task.

`Achieves` contains one or more exact two-space list items. `Files` and `To verify` are
non-empty single-line values. `### Design` is required. `### Disagreement` is optional
and follows Design when present. No other structural task heading or controller prose is
valid.

## Schema 2

Use schema 2 only for the immutable post-AMENDMENT projection. Keep every schema-1
identity and route field unchanged. Insert these fields immediately after `Schema: 2`:

```markdown
State: <active|resolved|escalating>
Amendment: <positive integer>
Amendment opening: <journal-line proof>
Amendment commit: <journal-line proof>
```

Keep the complete original `## Finding coverage`. It is the immutable source coverage.
Then insert these blocks before any task separator:

```markdown
## Absorbed findings
F2: <exact accepted amendment.committed proof>

## Remaining finding coverage
F1: task 2

## Accepted contributions
Task 1: <attempt.succeeded proof> · <commit> · <gate> · preserved
Task 2: <attempt.succeeded proof> · <commit> · <gate> · rewound <rewind.done proof>

## Task projection
Preserved: 1
Removed: 2
Task 2: prior task 3 · findings F1
```

Absorbed and remaining findings form one exhaustive, disjoint partition of the original
finding coverage. Both lists use numeric finding order.

Accepted contributions use numeric task order. Each line binds one exact accepted task
success, commit, gate, and outcome. A `rewound` outcome names its exact `rewind.done`
proof. Preserved contributions equal the `Preserved` task prefix.

`Preserved` is `-` or the exact contiguous accepted prefix. `Removed` is `-` or one
sorted unique task list. Every remaining Task projection line is sequential. It names
one or more prior tasks and the exact remaining findings for the new task. Preserved,
removed, and projected prior tasks form an exhaustive disjoint partition of the original
task set.

An `active` artifact has one or more remaining findings and its exact runnable task
graph. Those tasks use the schema-1 task grammar. Their numbers start after the preserved
prefix.

A `resolved` artifact absorbs every source finding. It has no remaining finding, task
projection line, separator, or runnable task.

An `escalating` artifact retains one or more remaining findings. It has no runnable task
graph. Its separate escalation artifact owns the structural successor.

## Closed root structure

Only the fields and structural blocks in this document are valid. Free root prose,
unknown root headings, duplicate headings, indented structural substitutes, missing
separators, reordered fields, non-sequential findings or tasks, and trailing structural
accounts refuse.

Fenced headings can remain inside a real Design or Disagreement body as data. They never
satisfy a required root, task, Design, or Disagreement heading.

## Bounded self-review

Before the positive PRODUCT REVIEW close, the controller checks all of these conditions:

- Every task has one coherent implementation and verification outcome.
- Related small edits with shared behavior, area, approach, or tests are grouped.
- No task exists only for one trivial edit that belongs in another task.
- Every separate task has an independent outcome or a necessary ordered dependency.
- The complete graph remains smaller and narrower than a normal C1 decomposition.
- No task changes the product contract, ownership, global decomposition, or unrelated work.
- Every source finding remains mandatory input. It does not limit later Design or code review.

A bounded wording or grouping defect can change the unclosed artifact. Rerun the check
after the edit. A structural, ownership, contract, or coordination defect invalidates
Correction Round admission. Use the authenticated allocation-supersession route. Never
rewrite a positively closed artifact.

## Read-only command

Run the exact workspace command after every controller edit:

```sh
python3 <workspace>/prompts/construction/correction_round.py check <built> <round>
```

Success prints the canonical compact JSON account derived by the same read-only projector
as the positive PRODUCT REVIEW close. That account binds the current allocation lineage,
pass, parent generation, confirmed source, route, controller, manifest and task authority.
For schema 2, it binds the current immutable post-AMENDMENT return authority. Refusal
prints no JSON account and changes no artifact, journal, object, ref, marker, index,
commit, or tree byte.
