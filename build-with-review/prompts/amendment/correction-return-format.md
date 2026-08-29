# Correction Round post-AMENDMENT return format

This file defines the only accepted post-AMENDMENT Correction return object.
The controller writes canonical UTF-8 JSON with one final LF. It writes no comments.
Canonical serialization uses lexicographically sorted object keys, no indentation, and
`,` / `:` separators with no spaces. The expanded examples below describe the logical
shape. Convert the final object to this one-line canonical serialization before use.
The canonical path is:

```text
corrections/<built>/round-<round>-amendment-<amendment>-return.json
```

The controller does not publish the content-addressed object. The selected return helper
validates this file, publishes the immutable object, and owns the terminal.

## Complete top-level grammar

The object has exactly these keys. No key is optional.

```json
{
  "schema": 1,
  "built": "lot-N[.M]",
  "round": 1,
  "previous_authority": "<journal proof>",
  "previous_execution_authority_sha256": "<sha256>",
  "amendment": {
    "opening": "<amendment.opened proof>",
    "committed": "<amendment.committed proof>",
    "artifact_sha256": "<accepted AMENDMENT markdown sha256>",
    "spec_path": "<safe relative path>",
    "spec_sha256": "<amended spec sha256>"
  },
  "tree_transition": {
    "pre_amendment_rewind": null,
    "rewind": null,
    "reland": null
  },
  "input_artifact": {
    "sha256": "<pre-AMENDMENT Correction artifact sha256>",
    "object": "corrections/<built>/objects/sha256-<sha256>.md"
  },
  "current": {
    "artifact_sha256": "<schema-2 Correction artifact sha256>",
    "artifact_object": "corrections/<built>/objects/sha256-<sha256>.md",
    "commit": "<post-AMENDMENT document commit>",
    "tree": "<exact current tree>",
    "gate": "<fresh baseline gate>"
  },
  "findings": [],
  "task_projection": {"preserved": [], "removed": [], "remaining": []},
  "accepted_contributions": [],
  "blocker": null,
  "required_sublot_outcome": null,
  "retry_transition": {},
  "route": "rebase"
}
```

`schema` is exactly `1`. `round` is positive. Proofs use `<zero-based journal
index>:<line sha256>`. SHA-256 values use 64 lower-case hex characters. Git commits
and trees use 40 through 64 lower-case hex characters.

`previous_authority` and `previous_execution_authority_sha256` are the exact suspended
Correction owner. The controller copies them from the authenticated opening account.
It does not infer or recalculate them from mutable state.

`amendment` names the exact opening and committed generation. `artifact_sha256`,
`spec_path`, and `spec_sha256` equal the validated `amendment.committed` account.

`tree_transition.pre_amendment_rewind` is the prior rewind proof in the opening's
composite execution authority, or `null`. `tree_transition.rewind` is the exact new
schema-2 `rewind.done` proof with `cause.kind=amendment-rebase`, or `null` when no
accepted contribution moves. `tree_transition.reland` is always `null`. The selected
`rewind.done` event owns every ordered embedded re-land.

`current` names the exact schema-2 Correction artifact, the post-AMENDMENT document
commit and tree, and the required fresh baseline. The two artifact object paths are
derived paths. They are not controller-selected paths.

## Finding partition

`findings` has one entry for every source finding. It keeps the original numeric order.
Each entry has exactly these keys:

```json
{"id":"F1","outcome":"remaining","amendment_item":null}
{"id":"F2","outcome":"absorbed","amendment_item":"<exact amendment.committed proof>"}
```

The partition is exhaustive. It has no duplicate or foreign finding. Every absorbed
finding names the same authenticated `amendment.committed` proof. Every remaining
finding names `null`. The schema-2 Correction artifact carries the identical absorbed
map and remaining coverage.

## Task projection

`task_projection` has exactly `preserved`, `removed`, and `remaining`.

- `preserved` is the sorted exact accepted prefix.
- `removed` is sorted and unique. Each entry is
  `{"task":N,"reason":"absorbed"}` or
  `{"task":N,"reason":"structural-escalation"}`.
- `remaining` is the exact sequential suffix. Each entry is
  `{"task":N,"prior_tasks":[...],"findings":["F1",...]}`.

The three accounts are disjoint and exhaustive over the pre-AMENDMENT task graph.
`structural-escalation` is valid only for route `sublot`. Each current schema-2 task
has the same task number, finding list, contract, Design, nullable Disagreement, and
ordered obligation IDs as this projection and its canonical final-checker output.

## Accepted contributions

`accepted_contributions` is sorted and unique by task. Each entry has exactly:

```json
{"task":1,"success":"<attempt.succeeded proof>","commit":"<commit>","gate":"<sha256>","outcome":"preserved","rewind":null}
```

or:

```json
{"task":1,"success":"<attempt.succeeded proof>","commit":"<commit>","gate":"<sha256>","outcome":"rewound","rewind":"<tree_transition.rewind proof>"}
```

Every proof, commit, gate, stable ref, archive ref, moved contribution, and embedded
re-land must replay through the shared rewind and success projectors.

## Retry transition

`retry_transition` is the canonical materialized final-checker transition. It has the
shared exact fields `schema`, `input_sha256`, `additions`, `dispositions`,
`transition_id`, and `output_sha256`. `additions` is exactly `[]`.

Each disposition has exactly `obligation_id`, `outcome`, `assignment`, `evidence`, and
`transition_authority`. Its order is the canonical input obligation order. The shared
transition projector derives both hashes. Do not hand-calculate or reorder them.

The route selects one closed disposition grammar:

- `rebase`: every member is `deferred`. `evidence` is `null`. `assignment` is the exact
  current task owner. Its unit is
  `{"kind":"correction","built":"<built>","round":N}`. Its `phase` equals the
  immutable source `required_consumer_phase`. It also carries the exact task contract
  SHA and mapping proof.
- `resolved`: every member is `absorbed`. `assignment` is `null`. `evidence` is exactly
  `{"amendment_item":"<amendment.committed proof>"}`. The output is the canonical
  empty set.
- `sublot`: every member is `carried`. `evidence` is `null`. `assignment.owner` is
  `escalation-tail`. Its unit is
  `{"kind":"correction-escalation","built":"<built>","round":N,
  "producer":"post-amendment-return","amendment":"<amendment.committed proof>"}`.
  It has `task:null`, phase `sublot-plan-consumer-map`, the exact mapping proof, and one
  complete `consumer_requirement`. That requirement binds obligation ID, checker,
  manifest phase, remaining outcome, and exact escalation item.

## Route grammar

Exactly one route applies.

- `rebase`: at least one finding and task remain. `blocker` and
  `required_sublot_outcome` are `null`. The schema-2 artifact state is `active`.
- `resolved`: no finding or task remains. `blocker` and
  `required_sublot_outcome` are `null`. The schema-2 artifact state is `resolved`.
- `sublot`: at least one finding remains. The schema-2 artifact state is `escalating`.
  `blocker` is the exact structural blocker proof. `required_sublot_outcome` is the
  single non-empty outcome copied into every escalation item and consumer requirement.

## Bounded self-review

Before the selected helper runs, inspect this file once against the exact current
Correction artifact, AMENDMENT commit, retry set, task successes, rewind, baseline, and
route. Correct local serialization or field-copy errors in this file once. Do not edit
journal history, content-addressed objects, the committed plan, or any producer proof.

Then run only the selected helper. A helper refusal is an authority failure. Stop and
preserve the file and every durable owner. Do not change the account to fit the refusal.
