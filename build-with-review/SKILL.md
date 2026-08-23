---
name: build-with-review
description: Use when a feature has to go from an idea to committed code — writing a spec, planning it, building it task by task, reviewing the result, or amending a spec after a review. Use when the user invokes "build with review", or when correctness matters enough that the work should be validated by running it rather than by reading it.
---

# Build With Review

## Overview

One arc, from an idea to a delivered lot: **a spec**, then **construction task by
task**, then **a review of what was built**. A review finding opens a new lot, and the
arc turns again until a complete review pass finds nothing.

**Three modes.** They alternate; they do not merely follow one another.

| | |
|---|---|
| **SPEC** | decide what the product must do, and cut the work into lots |
| **CONSTRUCTION** | write the plan and the code, task by task, until everything the project verifies passes |
| **PRODUCT REVIEW** | judge the built product. **Produce findings, never a line of code.** |

**A fourth file sits outside that arc.** `prompts/amendment/MODE.md` — a DECISION can open
it from any of the three, and it hands you back where you were.

**The barrier between CONSTRUCTION and PRODUCT REVIEW is the point of this workflow.**
Nothing is judged by reading that could be judged by running. A reviewer only ever opens
a product that already builds, lints and passes its tests.

**This skill replaces `superpowers:writing-plans`, `superpowers:executing-plans` and
`superpowers:subagent-driven-development`.** It keeps `superpowers:brainstorming`,
invoked in SPEC mode. Where another skill's instructions contradict this one, this one
wins.

**You are the controller** — the session that orchestrates the whole feature. This file
is yours, and only yours: every other actor gets a prompt written for its role.

### What you read, and when

1. **This file**, in full, now.
2. **`prompts/common/vocabulary.md`** — the words used everywhere, which every worker
   reads too. Read it right after this one; it sharpens what you have just read.
3. **`prompts/common/progress-rules.md`** — how to write the run's journal. Before your
   first call to it, which comes early.
4. **`prompts/<mode>/MODE.md`**, when you enter a mode. Never before you need it.

**Each mode's file is authoritative for its mode.** Phase numbers exist there and
nowhere else — this file names a transition by its condition, never by a number.

---

## The shape this borrows

It reproduces something software teams have done for decades. Placing yourself in it
tells you what you may decide and what you must ask.

| Here | In a team |
|---|---|
| The human | the **product owner** — and the only one who answers a product question |
| You, the controller | the developer who plans the work |
| The implementer | the same developer writing it, task by task, committing as they go |
| The gate | the checks that must pass before opening a pull request |
| The CONSTRUCTION → PRODUCT REVIEW barrier | **opening the pull request** |
| The product reviewers | the colleagues who review it |
| A DECISION | the question a reviewer raises that only the product owner can settle |
| A sub-lot | the follow-up commits that answer the review |

A developer does not stop the review to redesign the feature; they take the comments,
decide which are theirs to fix, and send the rest to the product owner. Neither do you.

**Three words, three people, never swapped.** **The human** drives this and answers its
questions. **The user** lives with the feature — a DECISION asks what *they* would see.
**The controller** is you.

---

## The invariants

Everything below follows from these. A reader who keeps only them is rarely wrong.

- **The only gate is the full suite.** Nothing is closed or accepted on a narrowed
  command — narrowing exists to work (an implementer mid-task) and to prove one claim
  (a verifier), never to close — therefore no closing command to review.
- **The gate proves that nothing tested broke. It does not prove the code is right.**
  A wrong test over wrong code is green.
- **A finding is proved, never asserted — and its author never has the last word on
  it.** Somebody else confronts it with reality before it becomes action: the fixer, the
  implementer, or a dedicated verifier — each mode says which.
- **Severity-bearing discovery review is risk-admitted before it leaves its reviewer.**
  SPEC mandates, PRODUCT REVIEW lenses, and the CONSTRUCTION design and code checkers use
  `prompts/common/review-risk.md`. Each reviewer keeps one private, append-only,
  best-effort history of candidates it filtered by impact and probability. No other
  actor reads it, and its loss is accepted.
- **Work is scoped to the lot. Review is always global.**
- **Nothing validated is rewritten outside its machinery.** A delivered lot's plan is
  frozen; the spec **as it stood when a lot was built** is frozen in git. The living
  spec changes only by a ruling and under a check: the DECISION channel's in-place
  commit, an amendment landing verified, a re-entered review's close.
- **Before the whole exists, you go back. After, you go forward.**
- **An interface is a hypothesis** until a consumer has exercised it.
- **The code is the authority on the current state.** Each spec describes a transition,
  not a state.
- **Deleting a test is the visible trace of a contract change**, and must be justified by
  a line of spec.
- **The human sees DECISIONs and checkpoints, never a finding.** A finding is settled
  by proof; a DECISION and a checkpoint are theirs.
- **The plan is alive.** Thin at first, thickened task by task by reality, frozen only
  when its lot ships.

---

## Entry points

A single skill has no natural mid-arc entry, so name yours before starting.

| Entry | What you check first |
|---|---|
| **A new feature** | nothing exists. Start in SPEC. |
| **A validated spec exists** | it is committed, its lot breakdown is readable, and you know which lot is next. Start in CONSTRUCTION. |
| **An amendment** | one or more DECISIONs have been answered and the answers change what the product does on parts a lot has already built. One R2.4 batch groups all active initial, supplemental and conflict-resolved answers in one file. It has its own phases — `prompts/amendment/MODE.md`. |

After a PRODUCT REVIEW amendment lands, **post-amendment C2** checks the built plan's
current controller-owned task contract against the amended product. A filled Design and
optional Disagreement stay the historical implementation record; C2 never turns them into
new promises. Its per-counter rules replace ordinary current-spec source-copy checks: the
built `Covers:`, `Descends from:` and copied Global Constraints remain historical, while
an explicit controller-contract contradiction still fails. Amendment-created
implementation work remains mandatory input to the fresh
complete PRODUCT REVIEW. It is not added retroactively to the built plan's `Covers:` or
`Descends from:`. A real controller-contract mismatch uses the bounded C2.5 plan-only
successor.

In every case: **the workspace comes first**, before any child, and the watchdog right
after.

## How you move between modes

Each mode's own file says where its exits land. What holds from outside:

| Leaving | When | Arriving |
|---|---|---|
| **SPEC** | the human approves the spec | **CONSTRUCTION** |
| **CONSTRUCTION** | every task of the lot is green | **PRODUCT REVIEW** |
| **PRODUCT REVIEW** | a pass leaves confirmed findings | **CONSTRUCTION**, as a sub-lot |
| **PRODUCT REVIEW** | a complete pass yields nothing | the lot is delivered — next lot, or stop |
| **anywhere** | a DECISION changes what the product does, on a part a lot has already built | **AMENDMENT** — and back to where you were when it closes; on the one branch where its reach will not close, through a full spec review first |

---

## The DECISION channel

Open in every mode, at every moment. **Never a phase of its own.**

The trigger appears verbatim in every child's prompt:

> **You are about to choose a behaviour the spec does not state. Stop.**

### What you do with one

**Analyse it before you ask.** It ends in exactly one of three outcomes:

- **REFUTE** — the premise is false, and the spec or the code settles it. Tell the raiser
  with the evidence, record it, continue. An escalation you could have closed yourself
  spends the human's attention for nothing, and teaches them to distrust the next one.
- **DECIDE** — the spec does settle it and the raiser missed it. Same, with the citation.
- **ESCALATE** — only a human can answer. Batch it with any others, and give each option
  its **user-visible consequence**, never its implementation cost. Present the question
  through *How you ask*'s human-judgment rule before opening the widget.

**Never hand a DECISION to a worker as if it were a finding.** A product choice made by
the agent least equipped to make it surfaces much later, when the human sees the built
thing and reverses it.

### Where the answer goes

| | |
|---|---|
| No lot has implemented the part it touches | **edit the current spec in place** |
| A lot has implemented it | **an amendment** — a complete, short change to the spec. `prompts/amendment/MODE.md`. One product-review decision batch puts all of its active built-part answers into the same amendment. |

Either way, **the answer reaches the spec before any code is written against it.**

Every product answer also joins one **run-wide product-answer state**. A later decision
must preserve every earlier active answer, whether its source batch is open or closed and
whether it came from a batch or one individual ruling. Applied code and a batch close end
work routing; they do not retire product authority. Only a later human conflict resolution
can supersede or qualify an answer.

**And while a spec review loop is open — the first, or a re-entry after an amendment —
neither row applies.** The loop's fixer is the document's live writer, and everything it
writes is re-verified before the close: route the ruling to it as a finding, and the
loop's own machinery does the rest.

**An in-place edit ends with a commit, immediately — the spec, that path alone.** The
spec is a committed file by now: edited and left in the tree, it makes every clean-tree
check refuse — the next attempt cannot start — and no later commit names that path. One
script commits it and settles what the commit disturbs:

```sh
<workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" <lot|->
```

A single product ruling binds its identity with one additional argument:

```sh
<workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" <lot|-> R<N>
```

R2.4 binds an in-place commit to its durable decision-batch item with two additional
arguments:

```sh
<workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" <lot|-> <batch-number> <decision-id>
```

An adverse breach conflict binds its exact spec repair with three additional arguments:

```sh
<workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" <lot|-> breach <breach-number> <conflict-number>
```

**Every bound form requires one current `spec.edit.ready` before the repository spec is
edited.** Its source is the complete state artifact that already carries the effective
answer, active/superseded state, current route and exact proposed change. Hash that file;
allocate one edit `op`; record the source `HEAD`; and hash the exact spec-path argument,
byte for byte:

```sh
progress.py note spec.edit.ready \
  --data '{"op":"<edit op>","owner":"R1","status":"active","route":"spec-in-place","state_kind":"ruling.ready","state_ref":"R1","source_sha":"<HEAD sha>","spec_path_sha256":"<sha256 of the exact spec-path argument>","artifact_sha256":"<sha256 of the complete state artifact>"}' \
  --text "reports/answers/R1-state.md"

# batch owner: "owner":"B2/D1"
# breach repair: "owner":"breach-1/C4","route":"spec-repair",
#                "state_kind":"decision.conflict.ready","state_ref":"B2/C4"
```

The text is one workspace-relative real file under `reports/`. `state_kind` is the exact
**latest** complete authority boundary this artifact represents: `ruling.ready`,
`decision.batch.ready`, `decision.batch.supplemented`, an accepted `decision.recheck.completed`,
or `decision.conflict.ready`. Its `state_ref` mechanically selects that event: ruling or
batch identity, supplement or recheck operation, or `<owner>/C<C>`. Except for a
supplement, which is itself the atomic latest answer group, the source boundary and
`spec.edit.ready` name the same hashed artifact. An accepted complete recheck and a ready conflict
carry an `actions` array with each
current-owner answer's fully qualified identity, `active` or `superseded` status and
current route. A ready restore-baseline conflict also carries `effect:"spec-repair"` or
`effect:"authority-only"`.

Only after this line may the controller edit the repository spec and call the matching
bound form. On a fresh call, `spec-commit.sh` authenticates before `git add` and before
its pending marker:

- exactly one unconsumed `spec.edit.ready` matches the owner, active route, current HEAD
  and exact spec-path hash;
- its referenced authority chain exists, is the latest complete state generation, and
  gives that answer the claimed current route; a batch D also appears in its sourced
  stable-D index and in one atomic initial or supplemental answer group;
- no unfinished conflict or other breach outranks it, and no later authority boundary
  superseded it;
- its artifact is a real workspace report whose bytes match `artifact_sha256`;
- a breach repair belongs to this open breach's latest `purpose:"restore-baseline"`
  conflict, whose ready result has `effect:"spec-repair"`.

Any mismatch refuses read-only: no staging and no pending marker. The pending marker then
freezes the ready `op`; a retry authenticates that same generation even if later journal
state exists. `spec.committed` carries `ready_op`, `state_kind`, `state_ref` and
`artifact_sha256`, so every recheck can recover the exact authority artifact it consumes.

**The script does not interpret the proposal prose.** It does not claim that arbitrary
Markdown can mechanically prove the working spec equals the intended semantic change.
Its payload marker proves only that retries commit the same prepared tree. The bound
post-commit global recheck must compare the named answer's exact proposal from the hashed
artifact with the committed spec, as well as preserving every other active answer. A
mismatch on the named proposal is a bound spec breach; it never becomes an ordinary
“same answer still owed” route. This is the semantic proof the pre-commit script cannot
provide.

**The third argument is the lot whose implementer sits blocked mid-attempt**, or `-` when
nothing is in flight. This commit can land while that attempt waits on the very answer
being written in: it moves `HEAD`, and the mark that says where the attempt began moves
with it — or an implementer that resumes and commits nothing could report this very
commit, and every check would pass.

*It runs the equivalent of:*

```sh
git add -- <spec path>
git -c core.hooksPath=/dev/null commit -m "<subject>" -- <spec path>
git update-ref refs/bwr/<run>/<lot>/attempt-base HEAD    # only when a lot is in flight

progress.py note spec.committed --data '{"sha":"<sha>","op":"<the operation's mark>","spec_round":<N>,"review_sha256":"<final full-round snapshot sha256>","spec_sha256":"<committed spec sha256>"}'
# the unbound close adds the three SPEC proof fields above
# a single-ruling form adds: "ruling":"R1"
# R2.4's bound form adds: "batch":<B>,"decision":"D1"
# a breach-repair form adds: "breach":<K>,"conflict":<C>
# every bound form also adds: "parent":"<the authorised parent sha>"
# when an attempt is in flight, every bound form also adds: "mark_lot":"lot-N"
# every bound form also adds: "ready_op", "state_kind", "state_ref", "artifact_sha256"
```

The unbound three-argument form is the SPEC-loop close. Before staging, it validates one
exact clean final full round, every immutable accepted report, no later fixer work,
run-wide authority quiescence, and only the documented status-line delta from the
reviewed snapshot. Its pending marker freezes that round and both content identities.
A retry finishes the exact prepared commit or journal tail. It never re-admits a newer
round or repeats a landed commit.

This controller-owned commit disables project hooks. The script also compares the
committed spec path with the exact prepared marker tree before it moves an attempt mark or
writes `spec.committed`. A hook cannot replace accepted spec bytes and still reach a
terminal. The implementer's own task commit keeps project hooks; task acceptance compares
that commit's complete tree with its frozen final-gate tree instead.

When the third argument is `-`, no live implementer will provide that later proof. After
the bound global recheck succeeds, run one construction `gate-check.sh open baseline`
operation on this exact clean spec commit. Use its parent as the predecessor. Close it
green and unchanged before a product pass or new attempt consumes the commit.

`ruling` names a single product answer. `batch` and `decision` name an R2.4 answer, whose
full identity is `B<B>/D<N>`. `breach` and `conflict` name a recovery repair. Their shared
`ready_op` is the binding to the exact durable authority generation and hashed state
artifact. The later `decision.recheck.completed` binds a whole run-wide recheck snapshot
to that commit's unique `op`; `ruling.applied` follows only when the named proposal is
implemented exactly and every active product answer still coexists. A cut after the
commit resumes the snapshot, never the edit.

**An answer that lives only in your context dies at the next compaction.** Record every
outcome as it happens. An escalated product DECISION outside R2.4 first allocates `R<N>`,
one more than the highest `R<N>` already carried by `decision.escalated`. Publish its
identity and exact question before asking:

```
progress.py note decision.refuted --text-file "$JOURNAL_TEXT_FILE"
progress.py note decision.escalated --data '{"ruling":"R1"}' --text-file "$JOURNAL_TEXT_FILE"
progress.py note ruling --data '{"ruling":"R1","route":"spec-in-place"}' --text-file "$JOURNAL_TEXT_FILE"
```

The direct-ruling route vocabulary is closed: `closed`, `spec-in-place`, `amendment`,
`spec-fixer`, or `amendment-fixer`. Use no synonym. `progress.py` refuses an identified
`ruling`, conflict update or complete recheck action that gives a direct R any other
value. An operational human choice has no `ruling` field; it
never enters the product-answer state. A cut after an identified escalation but before
its identified `ruling` asks the same `R<N>` question. It never allocates another
identity.

After the answer, ensure `<workspace>/reports/answers/` exists and write
`<workspace>/reports/answers/R<N>-state.md`. Reconstruct every identified product answer
and ready conflict resolution in journal order. The artifact contains every fully
qualified identity, exact effective answer, source authority, active/superseded status and
current obligation. For this new answer it also contains its exact proposed spec or
amendment change and the compatibility result against every earlier active answer. Then:

```sh
progress.py note ruling.ready --data '{"ruling":"R1"}' --text "reports/answers/R1-state.md"
```

This and every authority artifact path is workspace-relative under `reports/`, traverses
no symlink and names a complete real file. No edit, fixer dispatch or amendment opens before `ruling.ready`. A `ruling` without
`ruling.ready` rewrites that same state artifact from durable inputs and never asks the
human again. If its proposal conflicts with any active identity, open the conflict
generation below before routing either answer.

**Every direct route carries its exact current authority generation.** Select the latest
complete state that gives this R its effective answer, active status and route. Carry
`authority_kind`, `authority_ref` and `authority_sha256`. The authority kind is
`ruling.ready`, with ref `R<N>`, or the last `decision.conflict.ready` that changed this
R, with ref `<owner>/C<C>`. The SHA-256 names that boundary's complete artifact bytes.
Later global rechecks can change the mechanical route, but only a human conflict changes
this answer authority. Every owner-linked dispatch or amendment opening copies the tuple.
Its one `ruling.applied` terminal copies it again. An applied line closes only the
generation it names; a later conflict can change the same stable R and requires its own
new route and terminal. `progress.py` reconstructs the current route and authority,
authenticates the route-specific opening, commit and proof, and refuses a false or duplicate
terminal before journaling it.

**Every fresh product-route consumer also requires run-wide authority quiescence.** This
is one shared mechanical predicate used by `spec-commit.sh` and by `progress.py` before a
direct-R amendment opening, owner-linked fixer dispatch or terminal. It requires every
identified ruling to have its one ordered escalation, answer and ready state; every opened
batch to have its one ordered source, settlement and ready state; and every conflict
generation to have its one ordered source, settlement and ready state. It also refuses an
unresolved spec breach, the latest adverse SPEC-loop preservation proof, or a current
unconsumed `spec.edit.ready`. A stale ready line superseded by a later authority boundary
does not own the run. The matching bound edit and exact breach repair are the only fresh
consumer exceptions; their script authenticates that exact operation and recovery owner.
The frozen pending-marker retry remains a tail of its already-authenticated generation.

The same predicate protects a grouped-batch amendment opening and every batch
`ruling.applied` terminal. Conflict and breach lifecycle boundaries do not consume a route;
they remain able to publish the state that makes the predicate quiescent. Once any
conflict opening lands, no old direct authority can dispatch, open or terminalize. Resume
the exact conflict chain through `decision.conflict.ready`, then consume only its current
state.

**An accepted route publishes its terminal before a new conflict can open.** A successful
direct in-place recheck, accepted SPEC-loop proof or committed direct amendment is a
tail-only state. Write its `ruling.applied` next, before scanning or journaling another
conflict. `progress.py` refuses an ordinary `decision.conflict.opened` while one such exact
proof lacks its direct terminal. It does not apply that check to a
`purpose:"restore-baseline"` breach-recovery conflict. A `closed` route has no separate
accepted gesture: its terminal is the route. If a conflict opens first, the old closed
capability is invalid and only the ready conflict state can route it. Never repeat a route
to manufacture a terminal.

A `closed` route performs no document gesture. Once its complete ready state is current
and conflict-free, write its terminal immediately:

```sh
progress.py note ruling.applied \
  --data '{"answer":"R1","ruling":"R1","route":"closed","authority_kind":"ruling.ready","authority_ref":"R1","authority_sha256":"<state artifact sha256>"}'
```

For a direct `spec-in-place` route, the ready artifact's exact proposal is the pre-commit
compatibility proof. Recompare it with the latest global state, publish
`spec.edit.ready` from that exact hashed artifact, change the spec exactly as proposed,
then call `spec-commit.sh ... R<N>`. Before waking work, regenerate a fresh
finding-verifier verdict for every active product answer against the committed spec and
reviewed code, then write
`<workspace>/reports/answers/R<N>-recheck-<sha>.md`: every active or superseded answer,
its effective text and authority, whether the committed spec still carries it, and its
current obligation. Publish it with:

```sh
progress.py note decision.recheck.completed \
  --data '{"owner":"R1","sha":"<sha>","commit_op":"<spec.committed op>","accepted":true,"missing":[],"artifact_sha256":"<recheck artifact sha256>","actions":[{"answer":"R1","status":"active","route":"spec-in-place"}]}' \
  --text "<the recheck path>"
```

A bound commit without that recheck regenerates it. A mismatch records
`accepted:false`, every missing or contradicted identity, the complete owner action state
and the immutable artifact hash. It never changes the current route or writes an applied
line. Its existing breach opening owns the next gesture. If the recheck contradicts the
hashed authority artifact — the named proposal is not implemented exactly, or an earlier
active answer was erased — follow **Bound spec breach recovery** below. A conflict after
the commit cannot retroactively authorise it. Only a recheck that proves the exact named
proposal and preserves every active answer permits:

```sh
progress.py note ruling.applied \
  --data '{"answer":"R1","ruling":"R1","route":"spec-in-place","sha":"<sha>","recheck_op":"<spec.committed op>","authority_kind":"<current ruling.ready or decision.conflict.ready>","authority_ref":"<R1 or owner/C>","authority_sha256":"<authority artifact sha256>"}'
```

The bound commit's separate `ready_op`, `state_kind`, `state_ref` and artifact hash prove
the complete pre-commit state. The terminal's authority tuple proves that no later human
conflict changed R1 before application. Both bindings must hold.

An `amendment` route gives MODE AMENDMENT this same global state and authority tuple;
`amendment.opened` owns the dispatch, and A4 writes the matching terminal after its
commit and consolidation proof.

A `spec-fixer` route writes an owner-linked dispatch **before** sending anything to the
already-open SPEC fixer:

```sh
progress.py note fixer.dispatched \
  --data '{"ruling":"R1","route":"spec-fixer","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}' \
  --text "<the complete authority artifact path>"
```

Send that artifact's exact answer and every active preservation identity. The SPEC loop
then follows its ordinary fixer, scoped and full-round sequence. Its generic clean round
does not close R1. After the clean full round and shared spec commit, MODE SPEC publishes
one complete global recheck bound to that commit and every pending owner-linked
assignment. Only an accepted recheck permits one matching `ruling.applied` per R. A
failed recheck reopens the fixer loop from its durable discrepancies and applies none.
Several R answers may share that close and proof, but each keeps its own terminal.

An `amendment-fixer` route uses the same owner-linked `fixer.dispatched` shape inside the
open amendment. The amendment gives the R its own decision section. A4's consolidation
and shared commit then permit its matching `amendment-fixer` terminal. A generic SPEC or
amendment close never substitutes for a direct R terminal.

**R2.4 is the one answer-group exception.** Its `decision.batch.settled` event carries every
initial answer and route under stable IDs before any route runs. If one of its own
in-place edits reactivates unanswered DECISIONs, one atomic
`decision.batch.supplemented` event carries that recheck's whole new answer group.
Its actions artifact is also its complete run-wide product-answer state: local `D<N>`
answers are addressed as `B<B>/D<N>`, and every earlier `B…/D…` or `R<N>` answer appears.
If active answers cannot coexist, one atomic `decision.conflict.settled` event carries
the human's reconciliation before any resolving edit or amendment route. Its preceding
`decision.conflict.opened` and `decision.conflict.sourced` boundaries freeze the
owner (`B<N>` or `R<N>`), generation, fully qualified incompatible IDs and exact global
source state. Its later
`decision.conflict.ready` boundary proves one complete active/superseded answer state is
available to resume, recheck, amend or carry into R2.5. Sequential conflicts append new
generations; they never revise an earlier one.
Individual `ruling` notes there would create a half-recorded group, so it writes none;
its source, actions, recheck and conflict-resolution artifacts carry every finding,
proof, effective standing answer, active/superseded state and latest verdict.

Conflict `<C>` counts from 1 inside its owner. Its source and resolution live at
`<workspace>/reports/answers/<owner>-conflict-<C>-{source,resolution}.md`. The opening is
the first gesture; the source boundary precedes the human question; the atomic settlement
names every affected fully qualified identity with action `keep`, `supersede`, `qualify`,
`replace` or `reconcile`; and the ready boundary follows the complete run-wide
replacement state. A combined or qualified answer uses the current owner's lowest active
answer identity as its carrier. If the current owner is wholly superseded by an unchanged
older answer, no resolving spec edit is owed. The resolution can therefore say that
`B2/D1` supersedes `B1/D2`, or the reverse, without changing either identity's history.
The ready boundary carries the resolution artifact's SHA-256. `progress.py` verifies the
opening membership, complete settlement, complete owner action state and unchanged
artifact bytes before that state can route work.

### Bound spec breach recovery

This route applies only when a completed post-commit global recheck proves that a direct
bound `R<N>` or `B<N>/D<M>` spec commit erased an active product answer. The bad commit is
not authorised after the fact, reset, amended or hidden. It remains in history as
evidence, and one corrective child restores the exact spec from its authorised parent.

Allocate breach `<K>` once, one more than the highest run-wide `spec.breach.opened`
number. **The opening is the first recovery gesture.** Copy the bound commit's owner,
answer, `op`, SHA, parent and optional `mark_lot`; name every erased active authority from
the completed bad-state recheck:

```sh
progress.py note spec.breach.opened \
  --data '{"breach":<K>,"owner":"R1","answer":"R1","bad_op":"<spec.committed op>","bad_sha":"<sha>","authorized_sha":"<parent sha>","erased":["B1/D2"]}' \
  --text-file "$JOURNAL_TEXT_FILE"

# batch owner example: "owner":"B2","answer":"B2/D1"
# add "mark_lot":"lot-N" only when spec.committed carries it
```

No normal mode route, new attempt, human conflict or second breach opening may pass that
line. Run the one corrective operation:

```sh
<workspace>/prompts/common/spec-breach-recover.sh <K> "<corrective commit subject>"
```

The script authenticates the opening against the exact bound `spec.committed` line. It
publishes `spec-breach-recovery-in-progress` before touching the spec, restores only the
spec path from `authorized_sha`, and creates a new corrective commit whose parent is the
preserved bad commit. It does not reset or amend history. It preserves every unrelated
working-tree and index change. If the attempt named by `mark_lot` is still active, it
moves that attempt's `attempt-base` to the corrective commit; if that attempt has already
closed for a pause, no stale mark moves. The script then writes:

```sh
progress.py note spec.breach.corrected \
  --data '{"breach":<K>,"owner":"R1","answer":"R1","bad_op":"<bad op>","bad_sha":"<bad sha>","authorized_sha":"<parent sha>","sha":"<corrective sha>","op":"<repair op>","mark_moved":false}'
```

The batch form carries its batch answer identity; a live-attempt form also carries
`mark_lot` and `mark_moved:true`. A cut before the corrective commit reruns the same
marker. A cut after the commit or mark move reruns only the missing tail under the same
repair `op`. The marker falls only after `spec.breach.corrected` is durable.
While that marker exists, a triplet `stop.sh` call refuses before staging or moving
anything. Finish the recovery with the exact same `spec-breach-recover.sh` call first.
Even when `spec.breach.corrected` already exists, only that call may authenticate and
remove an orphan marker; never remove this recovery marker by hand.

After that line, reconstruct the preservation baseline from the complete state that
authorised the bad commit. The exact `answer` consumed by that commit returns to its
previous **future obligation**; its absence from the rolled-back spec is expected. Every
other active authority retains its exact effective text, status and previous obligation.
An already-owed route is not `missing` merely because it was not yet in the spec.
Regenerate fresh finding-verifier verdicts against the corrective SHA and determine
whether every baseline authority again has its authorised state and obligation. Write a
complete immutable breach recheck under `<workspace>/reports/answers/`. It contains every
active or superseded answer; the bad proposal and SHA as evidence; and every absent,
contradicted or unreconstructable baseline identity. A partial artifact proves nothing.

Every complete breach recheck records its result explicitly. Its `basis_kind` and
`basis_ref` identify the exact state it checked: the first uses
`spec.breach.corrected` and its repair `op`; a later spec repair uses `spec.committed` and
that commit `op`; a human resolution needing no edit uses `decision.conflict.ready` and
`<owner>/C<C>`. Success carries an empty `missing` list. Failure carries every absent
fully qualified identity and never claims success:

```sh
progress.py note decision.recheck.completed \
  --data '{"owner":"R1","breach":<K>,"basis_kind":"spec.breach.corrected","basis_ref":"<repair op>","sha":"<corrective sha>","restored":true,"missing":[]}' \
  --text "<the complete breach-recheck path>"

# adverse result
progress.py note decision.recheck.completed \
  --data '{"owner":"R1","breach":<K>,"basis_kind":"spec.breach.corrected","basis_ref":"<repair op>","sha":"<corrective sha>","restored":false,"missing":["B1/D2"]}' \
  --text "<the complete adverse breach-recheck path>"
```

Only `restored:true` permits:

```sh
progress.py note spec.breach.restored \
  --data '{"breach":<K>,"owner":"R1","bad_op":"<bad op>","basis_kind":"<checked basis kind>","basis_ref":"<checked basis ref>","sha":"<checked sha>"}'
```

For `restored:false`, open the owner's next existing decision-conflict generation before any
repair. Its opening carries `breach:<K>`, `purpose:"restore-baseline"`, the original
owner answer, every authority erased by the bad commit and every currently missing
identity. Its `state_kind` is `decision.recheck.completed`; its `state_ref` is the adverse
recheck's `basis_ref`. The source artifact asks one exact human question: preserve each
missing active answer and repair the spec or obligation to carry it, or revise, qualify
or supersede that authority. It also gives the original proposed change as a **future**
change, never as an authorised bad commit.

The normal `decision.conflict.{sourced,settled,ready}` boundaries make that answer
durable. Its ready artifact is a complete global target state. When preserving an answer
requires a spec repair, it gives the exact repair and every active preservation target.
Its `decision.conflict.ready` data carries `effect:"spec-repair"`; publish
`spec.edit.ready` from the hashed resolution artifact, then apply it from the current
corrective or repair SHA through:

```sh
<workspace>/prompts/common/spec-commit.sh <spec path> "<repair subject>" <lot|-> breach <K> <C>
```

This six-argument form uses the existing pending marker, path-only commit and live-attempt
mark move. Its `spec.committed` line carries `breach`, `conflict`, `parent`, and optional
`mark_lot`. Regenerate the whole breach recheck against that new SHA, with
`basis_kind:"spec.committed"` and the new commit `op`. If the ready resolution changes
authority without a spec edit, recheck the unchanged SHA with
`basis_kind:"decision.conflict.ready"` and `basis_ref:"<owner>/C<C>"`. Another adverse
result opens the next conflict generation. The same human question never repeats after
its `decision.conflict.settled` line.

Only `spec.breach.restored` permits the original owner to return to its **pre-commit**
state. On the fast success path, open its next conflict generation from the original
durable proposal, the erased authorities and the restored complete state. Its opening
uses `state_kind:"spec.breach.restored"`, `state_ref:<K>` and `breach:<K>`. After an
adverse path, the latest `purpose:"restore-baseline"` ready conflict already includes the
original owner and every erased authority; consume that resolution after restoration and
do not ask it again. In both paths, any future edit uses a **new** bound
`spec-commit.sh` operation and post-commit recheck. The bad `op` is never reused.

**These answer boundaries outrank every mode's normal resume table.** An identified
`decision.escalated` without its `ruling` re-asks the same `R<N>` question. A `ruling`
without `ruling.ready` rewrites its state. A conflict opening without sourced rewrites
its source; sourced without settled asks the exact durable conflict; settled without
ready rewrites the resolution; ready continues from its complete global state. For each
current direct R generation, a matching `ruling.applied` is terminal and never repeats.
Without one, route by the exact vocabulary: `closed` writes only its terminal;
`spec-in-place` follows its bound commit and global recheck; `amendment` follows its
owner-linked opening and A4; `spec-fixer` follows its owner-linked dispatch, SPEC loop,
shared close and global proof; `amendment-fixer` follows its owner-linked dispatch and
A4. An accepted route missing only `ruling.applied` writes that line; it never repeats
the dispatch, edit, commit or review. A bound
`spec.edit.ready` with no `spec.committed` carrying its `ready_op` resumes only its
matching bound call. A pending marker freezes that ready generation and owns its tail,
even if later journal state exists. Without a pending marker, any later authority
boundary makes the unconsumed ready state stale: reconstruct and publish a new ready
generation from the latest complete state, and never consume the old one. A bound
`spec.committed.op` without `decision.recheck.completed` regenerates the whole global
recheck. A completed bad-state recheck with no breach opening opens its one breach; an
opening without correction reruns the corrective script; and a correction or ready
recovery conflict without its keyed breach recheck regenerates that artifact and every
verifier. A complete `restored:false` recheck opens or resumes its recovery conflict. A
complete `restored:true` recheck without `spec.breach.restored` writes only that boundary.
A restored breach then resumes the original owner from the applicable ready conflict, or
opens the fast path's original-proposal conflict. No ordinary phase can route past one of
these unfinished states.

Before applying any direct or batch route in those rows, run the shared authority-
quiescence rule above. An incomplete boundary for another owner still owns the whole run.
Complete that exact chain first. A route proof whose only missing act is its terminal
finishes that terminal before a new conflict opening; after an opening, its old capability
cannot be consumed.

### What zero DECISIONs does not prove

A phase that raises none has two possible causes, and they look the same from outside:
**nothing was ambiguous**, or **nobody stopped**. Nothing in the result tells them apart.

So when a phase produces code and not one DECISION, ask the question once. It costs a
message. The other way to find out is the human meeting the built thing and reversing it.

What gets decided silently is never obvious from inside the task: a dialog promising a
notification the backend never sends, a banner claiming a limit that does not exist. Each
of them looked like a detail to whoever wrote it.

**And the trigger never depends on a count.** It fires on a moment, and it holds even if
it is the first of the day. A channel opened only at the end is a channel that stays
empty.

---

## Lots, sub-lots, and what freezes

- **The code is one tree, not a stack of lots.** Once a lot is merged, its code is just
  code. *"Going back to lot 1"* means nothing; work happens forward, on the tree as it is.
- **Re-reviewing earlier lots after a spec change is free.** The review is global and
  runs against the current spec anyway.
- **What freezes:** a delivered lot's plan, and the spec as it stood when that lot was
  built. What stays alive: the current spec file, and the current lot's plan.
- **Two signals, both numbers, neither a rule.** The size of a sub-lot against the lot it
  corrects; and three sub-lots touching the same area. Report both. Somebody has to decide
  when a correction has stopped being one.

### When work becomes a task, and when it becomes a lot

One rule decides it: **before the whole exists, you go back. After, you go forward.**

| Situation | What it becomes |
|---|---|
| The lot is **not delivered yet** and something is missing or wrong in it | **a change to the lot itself.** Add the task, re-cut, redo one — construction is not finished, nothing has been reviewed, nothing is owed to anyone. |
| The lot is **delivered** and a review finds something | **a sub-lot `N.n`**: its own plan file, back to the start of CONSTRUCTION's planning. The lot's own plan is never touched again. |
| A **DECISION** changes the spec, and it blocks the lot being built | **a task inside that lot**, once the spec is amended |
| A **DECISION** changes the spec, and it does not block anything | **a lot inserted after** the current one |

**A sub-lot may correct code from any earlier lot.** The code is one tree.

---

## Human checkpoints

**A human checkpoint goes where losing this session's detail costs nothing** — the spec is committed,
the lot is committed, the plan is in the workspace. Nothing useful is left in the
conversation, and a fresh session starts cheaper and reasons better.

**No checkpoint before the spec is validated ever moves the work to a new session.** The
brainstorming, the writing and the review stay in one session: what the human said lives
in it, and a new session would rediscover from a document what it could have had from a
conversation. The settings checkpoints still run where the table below puts them — the
first one right before the first reviewer exists — and they hand nothing over.

### How you ask

- **Every question of a human checkpoint goes in one widget call.** The widget takes
  four; a human checkpoint that needs five makes a second call immediately. Never one call per question.
- **Offer `not applicable`** where an answer may not apply — and **ignore that answer when
  it does not apply**, whatever was picked. A question somebody cannot answer sensibly is a
  question they answer at random.
- **Say `orchestrator`, never `controller`.** That is the human's word for the session that
  drives the work.

#### Before a human-judgment widget

**The widget is the last step, never the explanation.** This rule applies to every
DECISION and every human checkpoint that needs a judgement. Before the widget, explain
the decision in ordinary prose so the human can answer without having followed the
whole run:

- why the answer is necessary now, and what cannot continue without it;
- who detected it, in which role and phase, and what evidence confirmed it;
- why an earlier phase did not settle it. If the evidence shows that an earlier phase
  missed it, say so factually. If the reason is unknown, say that. **Do not invent
  causality, fault or a missed opportunity;**
- for every option: what it means, its product or workflow consequence, its advantages,
  its downsides and risks, and what the workflow does next if the human selects it.

Use **one numbered context block per question** when several judgements are batched.
Keep the same IDs and short labels in the widget, in the same order. Then send one widget
call, up to its normal capacity. A short widget description may summarise the prose; it
never replaces it.

**No fixed prose template.** Write the amount and structure the decision needs. This is
presentation only: it creates no new artifact or schema and no mechanical validator
judges the explanation.

A routine setup choice stays concise: provider, concurrency cap, session placement and
the ordinary worktree question do not need this account. If setup exposes an abnormal
state that needs human judgement, explain that judgement through this rule.

### The human checkpoints that set things up

| | The questions, in one call |
|---|---|
| **Before the first child** — the spec review is about to start | provider for the **spec reviewers** · provider for the **fixer** · **how many reviewers at once** |
| **The spec is validated** | what happens next: **a new session** *(recommended)* · here · stop — then provider for the **orchestrator** · for the **implementers** · for the **review lenses** |
| **A lot is delivered**, its review pass clean | the same four, with *the next lot* in place of *what happens next* |
| **An amendment opens** | provider for the **amendment fixer** · provider for the **reach sweep** |
| **The feature is finished** | the workspace and the git refs: **keep them to read the run back, or clean up** |

- **The cap is asked once, at the first human checkpoint, for the whole feature.** Every later
  orchestrator is handed it rather than asking again.
- **The provider questions are asked at every human checkpoint, even when the human stays
  here.**
  They are not the same children each time.
- **`stop` is a pause, never an abort.** Everything stays where it is, and a later session
  picks the feature up from the workspace.

### The worktree question — at the spec checkpoint, and nowhere else

**Ask it only when you are not already in a worktree.** `mcp__twicc__project` on your own
project answers that: a worktree carries `worktree_of`. If you are in one, the whole
feature stays in it and there is nothing to ask.

If you are not, this is the last moment to move cheaply — no code exists yet. Add the
question, in a second widget call:

> The work is about to start. Do you want it in a git worktree?
> **No, build here** · **Yes — create it for me** · **Yes — I will create it myself**

| | |
|---|---|
| **No** | nothing changes |
| **Create it for me** | you make it, following the project's own conventions when it states any, and say which branch and which path before you do |
| **I will create it myself** | **stop and wait.** Say *"tell me when it is ready, and where"*. Nothing is created until they answer. |

**Either way, the workspace moves with the work, and it moves before the new session
exists.** `prompts/common/handover-to-construction-rules.md` carries the order and the
script — read it there rather than improvising here.

**No code exists, but the run already does.** The workspace holds the journal, the spec
review's reports and the frozen prompts, git ignores it, and `git worktree add` therefore
leaves it behind. Every script of this workflow derives the repository from the
workspace's own path: left where it was, the next commit lands in the checkout nobody is
working in, on another branch, and nothing downstream can tell.

**From then on every session of this feature lives in that project.** A handover between
lots never moves it again.

### The human checkpoints that need a judgement

| | |
|---|---|
| **Every DECISION** | the question, with each option's user-visible consequence. Batched. |
| **An amendment's reach will not close** | *this is not an amendment* — confirm a full spec review |
| **A sub-lot outgrows the lot it corrects** | *this is no longer a fix* — arbitrate |
| **A task fails the same way after an outside diagnosis** | *classification is not the problem* — the analysis, and nothing launched until they answer |
| **An abort** | keep the workspace and the refs, or clean up |
| **The baseline is not clean** | **not a question** — a halt |
| **`.superpowers/` is not ignored by git** | `.gitignore` or `.git/info/exclude` — nothing is created until they answer |

**Control changes hands at exactly two hops:** after the spec, and between lots. Everywhere
else you keep it, and the human keeps one session to watch.

**A sub-lot is not one of them**, and that is deliberate: the pass that opened it settled
things that live only in this session.

---

## Stopping a run — pause and abort

The human can stop a run at any moment. **Neither of these is a human checkpoint and
neither is offered**: you receive it, and it interrupts whatever you were doing.

| | |
|---|---|
| **Pause** | the work will be picked up later. Everything is kept. |
| **Abort** | the work stops here. The tree goes back to its last validated state. |

**They stop the same way. They differ only in what survives.**

### What both do, in this order

1. **Launch nothing more.** No session, no subagent.
2. **Stop every live child's process** — `mcp__twicc__processes_stop`. **Annotating a
   session does not stop it**, and a child still running writes into a tree you are about
   to move.
3. **Let your own subagent calls end — returned, or errored out.** A subagent is not
   a session: step 2 cannot stop it, and it dies only with YOU, at the very end —
   which is after the cleanup below, not before it. A gate runner can still be
   running the project's commands in the tree, a verifier still writing in its
   disposable copy, a diagnostic still reading its worktree: reset, clean or remove
   that state under a live call and the run reports stopped while its last writer is
   still writing. **You wait for each call's end, never for its answer** — the
   results are discarded either way.
4. **Deal with the work in flight.** Each mode's file says what that means there.
5. **Put the tree back to the last validated state, and record the stop** — one script
   does both, and it is the same one in every mode:

   ```sh
   <workspace>/prompts/common/stop.sh pause [<lot> <task N> <attempt K>]
   <workspace>/prompts/common/stop.sh abort [<lot> <task N> <attempt K>] [<path to spare>...]
   ```

   **The arguments are your mode's business**, and its file says which apply — the attempt
   to preserve, on a pause and on an abort alike, and on an abort **the documents the
   mode vouches for**, which the clean would otherwise remove. It reports the SHA of
   the last validated commit and what it preserved. **An abort with no attempt named
   refuses a tree it cannot account for**: dirty state beyond the vouched documents is
   work no attempt owns, and erasing it is the human's decision, never the stop's —
   ask, settle it, then run the call again.

   **An attempt's work never rides through a stop in the working tree** — pause and
   abort alike take it to its try ref and step back, and on an abort its unaccepted
   commits leave the branch the same way. The run's documents are their modes' business:
   a mode that keeps one in the tree through a stop says so, and names it on an abort.
   **Validated work is not yours to undo** — a recorded task, a landed document:
   reverting those is the human's decision, on their branch.

   Every stop refuses while `document-copy-in-progress` exists; rerun the exact owning
   plan-commit, plan-publish or amendment-commit call, and never remove that marker by
   hand. A triplet stop also refuses while a controller-owned spec commit, amendment
   commit or spec-breach recovery marker exists. Settle that operation with its own exact
   retry before stopping. For `spec-breach-recovery-in-progress`, always rerun the same
   `spec-breach-recover.sh` call. Do this even after `spec.breach.corrected`; only the
   recovery script validates and removes that marker, so never remove it by hand.

   A call with **no attempt triplet** publishes `bare-stop-in-progress` before its first
   tree or journal gesture. That marker binds one operation nonce, the exact pause or
   abort mode, and every normalized spared path. Its `tree-settled` phase carries the
   last validated SHA and the lossless stop report. The matching `paused` or `aborted`
   line carries the nonce. A retry with the same call finishes only the missing phase or
   note; after the note it reports the same completed operation and never appends another
   stopping point. A different call cannot replace an unfinished or still-current stop.
   The completed marker remains the stop's identity. A later `resumed` line makes a
   completed pause stale, so the next legitimate bare stop allocates a new nonce even
   when its command text is identical. Every fresh repository mutator also refuses a
   completed pause until that later `resumed` line exists. A completed abort blocks every
   later normal mutation permanently; abort has no resume route.
6. **Every stopped child: the terminal status follows its ASSIGNMENT's durable
   boundary, never the accident that its session was still open one more gesture.**
   The boundary is each role's own "accepted", as its mode file defines it — a task
   ref posted; a spec reviewer's `report.received`; a sweep's complete official preflight,
   frozen in `amendment-sweep-preflight.json`, after which its successful retirement and
   the marker-consuming `sweep.reported` are immediately owed; **a
   product-review lens's report settled
   WHOLE — every finding verified, reprises included — never its first receipt**,
   which accepts the write while the assignment is still being adjudicated: a lens
   retired `done` on a mere receipt loses its one restatement and its one
   recalibration to the authorless routes, and a real finding with them. A child past
   its boundary **delivered: retire it `done`** — the stop merely performs the
   retirement its route owed a moment later. Everything else — an assignment still
   unsettled — is **`cancelled`**: abandoned before it delivered. `cancelled`
   describes **the assignment**, never the fate of the feature — a paused run resumes
   with fresh sessions, and that is why an unsettled child is `cancelled` on a pause
   as much as on an abort. **The watchdog keeps its own step** — the next one retires
   it `done`: ticking was its whole assignment, and it did it. Two terminal statuses
   on one session is a journal that contradicts itself — **so a resume tail that
   names a retirement treats the stop's as already satisfied**: a child the stop
   retired is never terminalized again.

   ```
   progress.py session-retired <id> done --archive --hide         its acceptance already landed
   progress.py session-retired <id> cancelled --archive --hide    everything else
   ```
7. **Retire the watchdog `done`** — `progress.py session-retired <id> done --archive
   --hide`. Its process is already stopped, with every child's, at the step that stops
   them all. The retirement is what stops its cron: left unretired, TwiCC relaunches it
   and the next tick wakes the session the human has just stopped.
8. **Report, with the SHAs `stop.sh` printed.** The last validated commit, and anything it
   preserved — a git ref's name is no use to somebody reading the report in a week. Say
   where the work stands: which lot, which mode, where inside it, what is verified and
   what is not, and any question still open with the human.

   *`stop.sh` already wrote the journal line, at step 5. It is the equivalent of:*

   ```
   progress.py note paused --task <N> --text-file "$JOURNAL_TEXT_FILE" --data '{"sha":"<sha>","attempt":<K>}'
   progress.py note aborted --task <N> --data '{"sha":"<sha>","attempt":<K>}'
   ```

   *— the task and attempt only when the call named one.*

   **And write the same stopping point into the journal yourself** — the report above
   lives in a conversation, and a conversation dies; the journal is what a resume reads:

   ```
   progress.py note paused --text-file "$JOURNAL_TEXT_FILE"
   ```

   `aborted` on an abort. A second line of the same kind is normal: `stop.sh` wrote the
   tree's, this one is yours.
9. **Say the run is stopped, and stop.** The human stops your own session; you never do.

**Subagents are not retired — they carry no annotations, and they die with whoever
launched them. But dying with you is not having ended:** the wait step exists because
your own calls outlive every child session, and cleanup under a live call races its
last writes. One consequence to record: a verifier caught mid-flight takes its
verdicts with it.

### Pause — what survives

**Everything.** The workspace, the plans, `reports/`, every git ref, every commit.

**On the way back in, one line before anything else:** `progress.py note resumed`. That
line also releases the completed bare-pause identity for a later stop. It never releases
an unfinished marker: its terminal `paused` line must exist first.

**The workspace carries the state, not your context** — so the work resumes in **this
session restarted, or in a new one**, indifferently. Whoever picks it up finds the
workspace, runs `progress.py notes`, and continues from what it says. **That is what the
stopping point of step 7 is for**, and why it is written precisely.

**One thing is deliberately in neither: the provider choices.** They are the human's,
given per checkpoint, for children that no longer continue — a recorded one would be
replayed instead of asked. So **a resume re-asks them, in one widget call, for whatever
children the resumed phase must create** — reviewers, a fixer, implementers, lenses. The
human is there: a resume is their own gesture. The cap is not re-asked; `run.started`
carries it.

### Abort — what survives

The validated commits, and nothing else that is yours to keep. **Including the files the
work created**: `stop.sh` removes them and lists what it removed, because a `reset` alone
puts back what was changed and leaves behind what was added. **An attempt's own commits
are not validated and do not stay either** — name the attempt in the call and they leave
the branch with the rest of it, preserved on its try ref: the refs' fate is the question
you are about to ask anyway.

**One exception, and you name it in the call: the documents the mode vouches for.** In
practice that is one path — **the spec**: untracked while it is first being written, the
only document this workflow keeps in the repository before its commit, or committed and
carrying the fixer's round edits when the loop re-entered after an amendment. A plan and
an amendment live in the workspace, out of any git gesture's reach. It is not code,
nothing was built on it, and its mode says plainly never to delete it — but the clean
cannot tell it from a task's leftovers, and the refusal above cannot tell it from work
that is not the run's, so whoever knows where it is says so.

**The workspace and the git refs go together, and it is the human's call**: keep them to
read the run back afterwards, or clean up. Ask, and do nothing until they answer. Both are
the trace of this run, both are private to it, and neither touches the repository's own
history.

| | |
|---|---|
| **Keep** | leave the refs alone. A failed attempt's ref is the only handle on commits nothing else points at. |
| **Clean up** | First write the durable cleanup order below. Then run `<workspace>/prompts/product-review/refs-clear.sh`, then `<skill dir>/prompts/common/workspace-delete.sh <workspace>` — in that order, since the second takes the first away. The watchdog is already retired. |

```sh
progress.py note cleanup.started --data '{"reason":"aborted","scope":"whole-run","choice":"clean"}'
```

**The note precedes the first ref deletion.** Once it exists, `keep` is no longer an
available answer and the cleanup question never repeats. A cut resumes the cleanup tail,
not the aborted mode: clear the refs again, then delete the workspace.

The reports need no decision of their own: they live in the workspace, so they follow it.

---

## Controller duties

### What you never do

- **You never write code.** Not a fix, not a typo, not a line you are sure about, and not
  a test. Every change to the tree goes through an implementer and the gate.
- **You never verify a finding yourself**, and you never re-run a child's work to check
  it. What you delegate comes back to you as a verdict, never as pieces to reassemble —
  that is what lets one session drive a whole feature from end to end. **The one redo
  you owe is the opposite case**, and the next list prescribes it: the spot-check on a
  report that found nothing. A finding carries its proof; an absence of findings
  carries nothing, and two or three redone checks are what stand in for it.
- **You never poll a child.** After creating it or messaging it, stop. Children ping
  `parent`; you advance from their messages and from the watchdog's ticks.
- **You never let a child talk to the human.** Everything is routed, batched, and arrives
  in one place.

### What you do write

The spec — it belongs to the session that held the brainstorming — **and an amendment,
which is a spec**: short, written the same way, handed to the same fixer. The high-level plan.
The journal, **only through `progress.py`**. And **the status line in a document's header —
one edit at each close that changes what it records**: the spec loop's close, an amendment
landing, a re-entered loop's close, each mode naming its own. It is a status word in a
header, it changes no behaviour, and no gate or reviewer has anything to say about it.

**And five artifacts of the machinery itself, each with no other valid writer:**

- **`gate.md`** — the runner proposes, the human validates, **you publish through
  `gate-write.sh`**: written by anyone earlier, the file would read as approved before
  it was; the helper exposes only a complete atomically renamed file. A full-line `#`
  comment preserves validated rationale but is never a command or a gate-surface
  exemption;
- **`<workspace>/gate-policy.json`** — one workspace-local positive parallel maximum and
  exact human compatibility rulings. Ask the maximum once for a fresh workspace. Publish
  each complete human-owned generation through `gate_execution.py`; schedule replacement
  never changes this file;
- **`<workspace>/gate-execution.json`** — after the exact gate list exists, derive one
  semantic command schedule under the current policy. Admit a shared pair only through a
  RARE or EXCEPTIONAL interference analysis, or one exact compatible human ruling. Publish
  through `gate_execution.py`. Proven absence means singleton groups. Every logical gate
  freezes the complete schedule and policy snapshot;
- **the confirmed-findings file** that closes a review pass — the sub-lot's source,
  distilled from verdicts only you hold together, and no child is assigned to it;
- **the `.superpowers/` ignore rule** when workspace creation refuses —
  `.git/info/exclude`, or the `.gitignore` line edited **and committed, that path
  alone**: this happens before the workspace exists, so there is no implementer to
  send it through.

Nothing else. **Code never comes from you**: everything else that reaches the tree
reaches it through an implementer.

### What you always do

- **Correct one local helper invocation before you classify its result.** Compare the
  command you issued with the exact documented command and its supplied runtime values.
  If they differ, correct only the local invocation once in the same live actor. This does
  not consume a provider replacement, report repair, logical round or workflow retry. Do
  not import an executable helper as a Python module when the skill gives a CLI command.
  Do not change or infer an authoritative input. If the exact corrected invocation reaches
  the helper and refuses, that refusal is authoritative. Follow its documented blocker or
  correction route; never repeat the same exact failed call.
- **Audit what comes back.** A report without its completion block goes back; a block
  with an unticked item and no stated reason goes back — **once, and journaled as it
  goes**: `progress.py note bound.spent --mandate <slug, when the role has one> --text
  "malformed block returned - <role> <its session id>"` — the id is the generation,
  and after a compaction that line is what says the next return is the second. The
  session stays live for that one repair. **A second return still malformed is a
  producer that cannot supply the contract** — not a block to repair: treat it as a
  silent child — stop its process, retire it `failed`, free its path, replace it —
  a fixer by its own recreation rule, anyone else by a fresh session on the same
  assignment. And once only: a replacement failing the same way is a stable blocker —
  `not-converging`, the human, nothing relaunched before they answer. **Not every
  role owes a completion block** — a role whose work is proved by running it owes
  none, and its mode file says so.
  - **A `NOT DONE` whose reason you cannot lift is retried through one fresh reader at
    most** — its mode says how the retry happens there. The same reason coming back
    honest from fresh eyes is a stable blocker, never a lapse of attention: stop
    retrying, record it — `progress.py note not-converging --text-file
    "$JOURNAL_TEXT_FILE"` — and take it to the human, with what you tried to lift.
    Nothing re-runs until they answer.
- **Spot-check a report that found nothing.** Pick two or three of its claimed checks at
  random and redo them. On a report carrying findings, check nothing — they carry it
  either way. Announcing which checks you redo publishes the exam.
- **Record as you go**, through `progress.py` — never afterwards, from memory.
- **Report at each lot's end**: what was built, and what the review found.

---

# The machinery

Everything below is the same in every mode.

**Where a script replaces a command, the block underneath it says what it is the
equivalent of.** That block is the **gesture**, not the script: the guards, the quiet
flags, the paths it prints and the journal line it writes are the script's own. **You run
the script.** The block is there so you can see what it does without opening it — and you
may open it, they are short and they are in the frozen copy. And in a block as in a
command, **a `<…>` that stands for a path is read quoted** — `vocabulary.md`'s rule; the
blocks write it bare for the eye alone.

## The workspace

**Your first action is to run the script that creates it.** A feature is often built
across several sessions, and only the first one creates anything — **so you run this
unconditionally, and the script decides.**

```sh
<skill dir>/prompts/common/workspace-init.sh <feature>
```

It answers `CREATED <path>`, `EXISTS <path>`, or `CLEANED <path>`, and it refuses a
`<feature>` that is not a slug. **It is the only script called from the skill directory**,
because the workspace it creates does not exist yet.

**`CLEANED` means the final-name workspace had already become its `.deleting`
tombstone.** Cleanup already owned this run. The script finished only that deletion and
did not create a replacement. Stop this invocation: never enter setup or a mode after
`CLEANED`.

**A workspace identity is a real directory at the checkout's physical
`<repo>/.superpowers/bwr` ground.** The ground, workspace root, and `.deleting`
tombstone are never symlinks. `workspace-init.sh` refuses an alias before adoption,
deletion, or creation. Birthmarks read through a symlink do not identify a run.

**The project gate has a real leaf identity too.**
`<repo>/.superpowers/bwr/gate.md` is absent before first discovery or is one real regular
file at that exact checkout-local path. Workspace init, handover and C0 refuse every
symlink, dangling symlink or other occupant before reading, comparing, copying, adopting
or writing. `gate-write.sh` is the only C0 or task-reconciliation writer; the authenticated
handover copy only transfers an already validated gate between checkouts. First discovery
writes only to a path proven absent immediately beforehand. Growth authenticates the exact
old blob. Both prepare the complete command list in one real same-directory temporary and
publish it by atomic rename, so interruption cannot expose a partial final leaf.

The optional workspace-local `gate-policy.json` owns the positive parallel maximum and
exact human compatibility rulings for the complete workspace. The separate optional
`gate-execution.json` binds one exact gate blob to one ordered semantic compatibility
partition and one immutable snapshot of that policy. The controller publishes either
artifact only through `gate_execution.py`, and only between logical gate operations.
Proven schedule absence derives singleton groups under the effective policy. A changed
gate, policy or narrow compatibility trigger refuses before any gate command. Baseline,
ordinary and final gates use the same executor. Fresh marker publication and every policy
or schedule mutation share one workspace authority lock. One side completes first; the
other then consumes that generation or refuses the live marker. Each operation
freezes its schedule and keeps one atomically published account directory. A small
canonical manifest authenticates one independently seekable raw output per command with
whole and fixed-chunk hashes. Metadata reads touch no raw output, and bounded output reads
touch only the requested command chunks. A crash reruns that frozen schedule only when no
complete account exists; it never adopts a later config.
One op also owns one executor lock. Concurrent callers join it. Active command processes
inherit it, so replacement cannot overlap an orphaned wave after executor death. Abandon
refuses until that ownership is idle.

**The sibling disposable ground has the same physical identity rule.**
`<repo>/.superpowers/bwr/tmp` is a real directory at that exact checkout-local path.
Workspace init and handover create or validate it. Every verifier and diagnostic
worktree operation validates `.superpowers`, `bwr`, `tmp`, each deterministic owner and
the leaf again before it creates, registers or removes anything. A symlink or a physical
escape at any component is a read-only refusal. An existing leaf is owned only when this
exact repository lists that exact physical path as its Git worktree. No deterministic
name, directory contents or birthmark substitutes for that registration. Cleanup uses
`git worktree remove --force` only after this proof and has no recursive filesystem
fallback; an unregistered directory is foreign state and remains untouched.

**It also refuses to create anything if `.superpowers/` is not ignored by git**, and that
one is a question for the human. **Ask, do what they answer, then run the script again.**

| | |
|---|---|
| **`.git/info/exclude`** | local to this clone, shared by its worktrees, **not tracked** — add the line, and there is nothing else to do |
| **`.gitignore`** | versioned, so every clone of the repository gets it — add the line **and commit it, that path alone** |

```sh
git add -- .gitignore
git commit -m "<subject>" -- .gitignore
```

**The subject is yours, in the project's own conventions** — this commit lands in the
repository's history, and the Git section's rule applies to it like any other.

**Both lines.** A repository that had no `.gitignore` at all has an untracked one now, and
`git commit -- <path>` refuses a path git does not know yet. The pathspec stays on the
commit for the usual reason: without it, the commit takes the whole index.

**Never leave that modification uncommitted.** Nobody downstream is allowed to carry it: a
plan commit names the plan, a task commit names its write set. It would sit in the tree
for the whole run, and **every task ends on a clean-tree check that would refuse it** —
the first one would never be recorded and construction would not advance.

**If `.gitignore` already carried changes of the human's**, stop and say so rather than
committing: that pathspec would take theirs too, and what they do with them is their call.

The workspace being outside git is not tidiness: it is what stops a `reset` from taking
the plan away with the code, and what stops a failed attempt's `git add -A` from sweeping
this run's own prompts, journal and reports into a commit that claims to carry a task.

*It runs the equivalent of:*

```sh
# only if neither <repo>/.superpowers/bwr/*-<feature>/ nor its .deleting
# tombstone exists — the date is not today's when the workspace was created on
# another day. A tombstone is finished and returns CLEANED, never replaced.
# Creation is built whole under a staging name the existence check cannot
# match, then renamed once complete: a copy that dies halfway must never leave
# a directory a later session adopts as a complete workspace.
mkdir -p <staging>/{plans,amendments,additional-prompts,reports/{spec-review,amendment,construction,product-review}}
cp -r <skill dir>/prompts <staging>/prompts
cp <skill dir>/SKILL.md <staging>/SKILL.md
cp -r <skill dir>/dashboard <staging>/dashboard
mv <staging> <repo>/.superpowers/bwr/<date>-<feature>
```

`.superpowers/` is git-ignored. `<date>` is the day the workspace was created, and
**every plan path of this feature is built from that same name** — see below.

**On `EXISTS`, no run content was created or copied.** The script may create the sibling
checkout-local `bwr/tmp` ground when it was absent; it never changes the existing
workspace. Run `progress.py notes` to learn where the work stands, then **reread
`<workspace>/SKILL.md`** — the frozen copy is what this feature was started under.
Re-copying `prompts/` would swap the instructions under sessions that are still running,
and would silently change the rules mid-feature if the skill was updated in the meantime.

**A current bare stop outranks every normal resume route.** A present
`bare-stop-in-progress` without its nonce-matched `paused` or `aborted` line means the
human already chose the exact stop and its tail is incomplete. Rerun only the stored
workspace-relative call. A completed pause remains current until a later `resumed`
boundary; a completed abort remains current permanently. Never write `resumed` for an
unfinished stop or an abort. Never open a session or verifier, start an attempt, commit
a plan/spec/amendment, begin a breach recovery or rewind, or return to a mode while the
stop is current. The direct repository mutators — `attempt-started.sh`, fresh
`plan-commit.sh`, fresh `spec-commit.sh`, fresh `amendment-commit.sh`, fresh
`spec-breach-recover.sh`, fresh `rewind.sh`, and every triplet `stop.sh` — refuse this
marker before mutation. A bare stop also refuses while `plan-commit-in-progress`,
`spec-commit-in-progress`, `amendment-commit-in-progress`,
`spec-breach-recovery-in-progress`, `rewind-in-progress` or
`gate-check-in-progress` exists. It changes no stop,
repository or journal state in that refusal. Settle the exact operation owner first,
then run the bare stop. An operation tail remains retryable only before a later bare
stop can be admitted, so no owner marker can cross the human stop boundary.

**One whole-run boundary outranks every normal resume route.** While the final-name
workspace exists, that boundary is `cleanup.started` with `scope:"whole-run"`. It means
the human already chose destructive cleanup. Never write `resumed`, return to a mode,
repeat a checkpoint, or offer `keep`. Finish only the recorded tail:

1. Run `refs-clear.sh` again. Its whole-run delete is idempotent, including a namespace
   whose earlier loop deleted only some refs.
2. For `reason:"feature-complete"`, stop the watchdog process if it still runs, then
   retire its session `done` if it is still open. A gesture already recorded or already
   terminal does not repeat. For `reason:"aborted"`, the stop procedure already settled
   the watchdog before the cleanup choice.
3. Run `<skill dir>/prompts/common/workspace-delete.sh <workspace>`. It is always last.
   A retry may pass either the absent final path or its present `.deleting` tombstone.

**After step 3's atomic rename, the sibling `<workspace>.deleting` is the boundary
itself.** It exists only after refs cleanup and watchdog settlement completed. Therefore
a takeover that finds the tombstone runs only `workspace-delete.sh` again. It never
needs the deleted journal to reconstruct the earlier tail, never offers `keep`, and never
adopts what remains. The next unconditional `workspace-init.sh` performs this retry and
answers `CLEANED`.

Successful deletion removes the tombstone itself. No closing note can or needs to follow
it.

**From that moment, every path in this skill means `<workspace>/…`** — including this
file, which you are reading from the skill directory right now. Read the copy from here
on, and hand children paths into the copy.

**Why a copy.** A child reads a project-relative path with no permission prompt, and it
has no question widget to answer one. The skill's own directory differs per provider and
per install. And the copy **freezes** the instructions for the whole feature: editing the
skill halfway through cannot change what anyone was told.

**It lives as long as the feature does** — through every lot, every sub-lot, and every
review pass. **You delete it only when the human says the whole feature is done**, and
you retire the watchdog first, since its script lives inside it.

**Delete it with the skill's own script**, which refuses any path that is not a bwr
workspace:

```sh
<skill dir>/prompts/common/workspace-delete.sh <workspace>
```

Before it classifies a final name or a `.deleting` tombstone, the script proves
the deletion ground. The lexical parents must be exactly
`<checkout>/.superpowers/bwr`; `.superpowers` and `bwr` must be real,
non-symlink directories; the derived checkout must be the exact Git toplevel;
and the physical ground must be exactly that checkout's `.superpowers/bwr`.
A matching suffix outside Git, below a repository subdirectory, or reached
through a ground symlink is foreign state and is refused read-only. A partial
tombstone needs no birthmarks, but it still needs this checkout-ground proof.

**The skill's own, never the frozen copy** — bash reads a script as it executes it, so a
copy asked to delete the directory it lives in breaks midway.

*It runs the equivalent of:*

```sh
mv <workspace> <workspace>.deleting
find <workspace>.deleting -delete
```

**The same-parent rename is atomic.** The adoptable final name disappears before any
content does. A killed `find` leaves a non-adoptable `.deleting` tombstone; the next
unconditional `workspace-init.sh` finishes it and answers `CLEANED`. The delete script
also accepts the original final path or the tombstone directly for an idempotent retry.

**`find`, never `rm -rf`.** Many permission setups refuse `rm -rf` outright: the call is
denied, and you spend a turn rewriting a command you already knew. `-delete` walks
depth-first, so a directory goes only once its contents are gone — there is no `-r` to
forget.

What it holds:

| | |
|---|---|
| `SKILL.md` | the frozen copy of this file |
| `prompts/` | the frozen copy of every role prompt |
| `additional-prompts/` | optional human runtime instructions: `global.md`, then one exact mirror path per role |
| `plans/` | **where every plan actually lives** — see below |
| `amendments/` | and every amendment, for the same reason |
| `progress.jsonl` | the run's journal, written **only** through `prompts/common/progress.py` |
| `dashboard/` | the run seen as a timeline — the script refreshes its copy of the journal |
| `reports/` | see below |

**The three paths a feature uses**, all built from the same short name — `<feature>` is
the feature's short name, **a slug**, no date and no suffix, `peer-revocation`:

```
docs/plans/<date>-<feature>-design.md              the spec
docs/plans/<date>-<feature>-<lot>-plan.md          one plan per lot, a copy
docs/plans/<date>-<feature>-amendment-<N>.md       one per amendment, a copy
<repo>/.superpowers/bwr/<date>-<feature>/          the workspace, where both actually live
```

**The workspace's name is the stem of everything the run produces.** One date, fixed the
day the workspace was created, carried by every plan and every amendment — including a
sub-lot opened weeks later. Two consequences, and both are why: **the files of one feature
sort together**, and **any script builds a path from the lot or the amendment number
alone**, so two of them cannot disagree about which file they mean.

**The spec keeps its own date**, and it is the only one that may differ. It says when the
product was decided; the stem says when the work started. A feature can begin from a spec
validated months earlier.

### `plans/` and `reports/`

**Every plan lives in `<workspace>/plans/`**, and `docs/plans/` only ever receives a copy.
**Nothing is ever written into `docs/plans/` directly: it is an output, not a source.** The
workspace is outside git, so nothing that resets, cleans or stages the repository can reach
a document that is still being written — safe by construction, not by anyone remembering a
command.

**An amendment lives there too**, under `<workspace>/amendments/`, for exactly that
reason: it is written across several rounds while an interrupted task may sit uncommitted
in the tree beside it.

**`reports/` has one directory per producer**, because their reports are read by different
people at different moments and must never be taken as one set:

```
reports/
├── answers/                         run-wide product-answer states and conflicts
├── construction/                    one file per failed attempt
├── product-review/<root lot>/       one directory per subject
├── spec-review/                     no lot level: it reviews the whole spec
└── amendment/<N>/                   one directory per amendment
```

`answers/` is created lazily by the controller before its first product ruling or batch
state; it is not a subagent report. Each mode says what is written elsewhere and under
what name. Two rules hold across all of them: **nothing is ever overwritten**, and
**subagents write nothing** — every file under `reports/` has a session behind it.

The private `*-risk-filtered.md` files are the narrow reviewer-memory exception. Fresh
occurrences of one SPEC mandate or PRODUCT REVIEW lens append to their own fixed history
path. All design-checker rounds and physical regenerations in one attempt use
`reports/construction/<lot>/task-<N>-attempt-<K>-design-risk-filtered.md`. All code-checker
rounds and regenerations use the matching `-code-risk-filtered.md` path. A new attempt
uses new paths. They never rewrite old entries. These best-effort files are not reports
or workflow authority, no other actor reads them, and losing one does not block the run.

---

## The tools you use

**Prefer the `mcp__twicc__*` tools over the `twicc` CLI.** Same surface, no subprocess,
and the connection carries your identity — a session you create is recorded as spawned by
you. Use the CLI only for something the MCP surface does not expose.

| What you do | Tool |
|---|---|
| Create a child session | `mcp__twicc__create_session` — carries the prompt, the provider, the preset, and the annotations in one call |
| Talk to a child, or to your own parent | `mcp__twicc__send_message`, target `parent` for yours |
| Change one child's annotations | `mcp__twicc__update_session_annotations` |
| Change several | `mcp__twicc__update_sessions_annotations`, **with exact ids** |
| Find sessions again | `mcp__twicc__sessions` with `--annotation` filters |
| Archive, hide, unhide | `mcp__twicc__update_session_archive` / `_hide` |
| Read a child's own state | `mcp__twicc__session` |
| **Stop a child's process** | `mcp__twicc__processes_stop` — **the only thing that actually stops one.** Annotating, retiring, archiving and hiding all leave it running |

The `twicc-*` skills document the same surface in depth if you need the details of one
call.

### Everything a session needs exists before you create it

The directory its report goes in. The ref that marks where it starts. The workspace it will
open. The document it was made to read. **All of it is in place before the call, never
after it.**

**You are not owed a next turn**, and the child does not wait for one: it can be reading
its prompt while you are still deciding what to do next. A thing put in place afterwards is
a thing that may never be put in place at all — and the failure lands on the child, hours
later, at the one moment it needed what nobody made.

### Every session you create names its project

**`create_session` does not inherit yours.** Pass the project explicitly, every time, and
pass **your own** — `mcp__twicc__whoami` gives it.

A child created in another project opens **another checkout**: its gate runs against a tree
nobody else is working in, its commits land somewhere else, and everything it reports is
true of a repository that is not this one.

**Right after a `create_session` succeeds:**

```
progress.py session-started <id>
```

The command owns the short interval in which creation has returned an id but the exact
session is not yet readable. It retries only that exact `session not found` result. If
the command still refuses for that reason, keep the returned id, create no replacement,
wait until that exact session is readable, then retry only the same `session-started`
boundary. Nothing was journaled by the refused call.

**A creation can land while its result is lost** — the call cut, timed out, or your
turn gone before the id reached you. **Never retry on trust, and never write it off**:
a blind retry seats a second owner on one assignment — two writers on one report path,
two fixers on one document and one cumulative log, two watchdogs on one chain, two
controllers facing the human — and a blind write-off abandons a live child nobody will
ever track, nudge or retire. The assignment already has a durable identity: **the
annotation set travels in the creation call itself.** Query it back before any retry —
the exact annotations, `--include-archived --include-hidden` — and route on the count:

| | |
|---|---|
| **exactly one match** | the creation landed. Adopt that id, write its `session-started` line, continue as if the call had returned it. |
| **no match** | it never landed. Create it now — this is not a retry. |
| **several matches** | a duplicate already exists. Stop their processes and take it to the human: which one owns the assignment is not yours to guess — both may have written. |

**One creature mutates the very identity you would query: a transferred
orchestrator.** It owns its `bwr.mode`, `bwr.lot` and `bwr.status` from its first
turn — the freshness rule orders it to — and it starts working the moment it exists,
without ever reporting back to you. By the time a lost result is recovered, its
creation values can be gone, and the zero-match row above would seat a second
controller over one run: two sessions facing the human, owning one workspace, one
branch, one journal. **For that one session, the immutable identity is the spawn
relation**: query the feature's controllers **spawned by you** — `--spawned-by` your
own id, `--include-archived --include-hidden` — and subtract every id your OWN
`handover` notes already name. One remainder is the lost creation; none means it
never landed. Nothing else needs subtracting, and that is what makes the remainder
exact: the feature's older controllers were never spawned by you — the initial one
is the human's, each later one its own predecessor's. Never judge an orchestrator by
its creation-time mode, lot or status.

**And adopting it is not always announcing it.** A creation lost for long enough can
have finished its leg, set itself `done`, and handed over to a successor of its own.
Write your missing `handover` note for YOUR creation — that record is true either
way — then read the journal for `handover` notes written BY the recovered id, and
follow the chain to its end: **the link the human gets is the chain's last
controller, the one that owns the conversation now.**

**When you name a session to the human, give a link, never a bare id:**
`[<title>](/project/<project id>/session/<session id>)`. They click it; an id they have to
paste is an id they will paste wrong.

### You give paths, never contents

**Every document you hand to a session or a subagent, you hand as a path.** The spec, the
plan, a role prompt, a report — always the path, never the text.

### Every child receives its runtime inputs

Every session and subagent message carries this fixed block, with absolute paths:

```text
RUNTIME INPUTS
repository: <absolute repository path>
workspace: <absolute workspace path>
role prompt: <absolute role-prompt path>
global prompt: <workspace>/additional-prompts/global.md
additional prompt: <absolute mirrored additional-prompt path>
```

The role's own launch contract adds its assignment, document paths, identities and output
path. Those fields never replace this block. A TwiCC session also receives the repository's
exact project in `create_session`; the message does not substitute for that setting.

The global prompt has one fixed path: `<workspace>/additional-prompts/global.md`.
After every official prompt, every child and every later controller must read the global
additional prompt through this command:

```sh
python3 <workspace>/prompts/common/additional-prompt.py read-global \
  <workspace> <workspace>/additional-prompts/global.md
```

Treat its stdout as human instructions. The helper emits the exact global bytes, or
nothing for proven absence. A controller entering or resuming an existing workspace
performs this read before its role-specific
additional prompt. A running controller that just received the human instruction already
knows it; every future launch reads the file.

Build the role-specific additional path mechanically: replace the role prompt's
`<workspace>/prompts/` prefix with `<workspace>/additional-prompts/`. For example,
`prompts/construction/implementer.md` maps only to
`additional-prompts/construction/implementer.md`. Then read the role-specific additional
prompt through this command:

```sh
python3 <workspace>/prompts/common/additional-prompt.py read \
  <workspace> <role-prompt> <additional-prompt>
```

Treat its stdout as human instructions. The helper emits the exact file bytes, or nothing
for proven absence. It blocks on an alias or other invalid occupant in the workspace-owned
path. Read no other optional prompt path. Follow both instruction sets during the
assignment. The later role-specific instruction wins on contradiction.

Copy this complete rule without shortening or paraphrasing it into every child message:
absent input means that the input field has no value. It never means that an optional prompt
file or its parent directory is absent. The `global prompt` and `additional prompt` fields are required absolute path values, but
their files may be absent. Always call both helpers. Empty stdout is valid absence and
never a blocker. Non-empty stdout is human instructions. Only a helper refusal blocks.
Never test either file directly.

The human may ask the controller to create, replace or remove one of these files during
the run. Never mutate the target path directly. For create or replace, write the exact
content to one fresh real non-symlink draft with the file-editing tool, then run:

```sh
python3 <workspace>/prompts/common/additional-prompt.py publish \
  <workspace> <role-prompt> <additional-prompt> <draft-file>
```

Remove the draft after success. For removal, run:

```sh
python3 <workspace>/prompts/common/additional-prompt.py remove \
  <workspace> <role-prompt> <additional-prompt>
```

The helper validates every physical path component and owns the atomic mutation. The
content is the human's runtime instruction; this workflow does not constrain it, journal
it or make it authority. It applies to future launches that read it. The directory moves
and disappears with the workspace.

The global file uses the same draft and owner. Create or replace it with:

```sh
python3 <workspace>/prompts/common/additional-prompt.py publish-global \
  <workspace> <workspace>/additional-prompts/global.md <draft-file>
```

Remove the draft after success. Remove the global file with:

```sh
python3 <workspace>/prompts/common/additional-prompt.py remove-global \
  <workspace> <workspace>/additional-prompts/global.md
```

**The current working directory is never the workspace.** Never omit the workspace because
the role prompt sits inside it or because the child opens in the repository. Tell every
child to stop before reading or writing any project or workspace path when one required
runtime input field has no value, or one supplied value is relative, unresolved or
contradictory. It reports the blocker to its
parent. It never guesses, derives or creates a replacement workspace.

---

## Sessions

### Two natures, and never a third

| | Internal machinery | The work continuing |
|---|---|---|
| Role | bounded, it ends | **it takes over from you** |
| Title prefix `- ` | yes | **no** |
| Question widget | **disabled** | enabled |
| Reports to | its spawner (`parent`) | **the human, directly** |

**Tick all three or none.** A half-transferred session leaves the human talking to someone
who is still reporting to you.

The `- ` prefix (dash, space) is how the human spots your machinery in a list that also
holds their own sessions: `- Implement task 4 (peer revocation)`.

### Who is a session, who is a subagent

| Actor | Kind |
|---|---|
| Task implementer | **session, one per attempt** |
| Product reviewer | session |
| Spec reviewer | session |
| Spec fixer | session |
| Reach-sweep reviewer (amendment) | session |
| Completeness reviewer | **subagent** |
| Consolidation-diff checker | **subagent** |
| Design checker and code checker | **subagents** — inside the implementer's session |
| Finding verifier | **subagent** — one per reviewer report |

**A session for what the human must be able to reread separately. A subagent for what is
consumed on the spot.**

A session carries machinery — annotations, retirement, a row in the human's list — and
what it buys is inspectability: they can watch it work and read it afterwards. A subagent
returns its result inline and disappears.

**The dividing line is not who judges — it is who the result is handed to.** The two task
checkers judge, and they are subagents: their verdict goes to the implementer, whose
session already carries the trace, so there is nothing to reread on its own. The finding
verifiers are the same. A reviewer reports to *you*, and its work has to be auditable by
itself.

### Three rules for every subagent you launch

**A subagent is your provider's own mechanism, never a TwiCC session.** The `Agent` tool
on Claude Code, its equivalent on Codex. If you find yourself calling `create_session`
where this workflow says subagent, you are doing the wrong thing.

**1 · It must never inherit your context.** It starts with its prompt and nothing else —
the required outcome, on every provider. Whether there is a setting to make depends on the
tool in front of you: if it exposes the choice, set it explicitly rather than trusting a
default.

*A subagent that inherits your context is a subagent that agrees with you.*

**2 · It runs in the background if your provider offers the option.** On Claude Code, say
so explicitly when you launch it. On Codex, nothing to do — you can send and receive
messages while one runs.

*Otherwise you are frozen until it answers, and everything else that was working for you
waits with you.*

**3 · Its physical bracket reaches one terminal before you forget it.** A
`subagent-started` line proves only that the provider call is unsettled. It does not prove
that the provider still runs it. Before you duplicate a call, classify it as lost, or end
your own turn, inspect the provider's active-subagent roster. On Codex, use its subagent
list. Do not use TwiCC session process tools for provider subagents.

Every successful opening also prints a `SUBAGENT OPEN` reminder on stderr. It does not
change the call's stdout. Keep the provider-native handle and follow that reminder until
the exact bracket has one durable terminal.

- Still active: keep that call, continue useful work, and reconcile it again before your
  turn ends.
- Completed: write its exact `subagent-ended` terminal before you act on the result.
- Absent or result unavailable: use the call site's unusable terminal, when it defines
  one, before any regeneration.

The supported discovery, gate-runner, completeness, SPEC-loop finding-verifier and
amendment-consolidation loss routes all define that terminal. Each replacement starts
only after the prior physical bracket closes. A gate replacement also proves that its
executor and orphaned commands no longer own the operation.

Never end a turn with a required provider subagent forgotten. If no other useful work
remains, use the provider-native result or wait mechanism. A TwiCC child session is
different: it messages you asynchronously, and the watchdog owns a missing wake-up.
Never start a TwiCC process-wait loop for a child session.

### When a subagent fails

An error, an empty result, or an answer that does not address the question.

**Relaunch it once, same prompt** — and journal the spend as you relaunch, because after
a compaction the count lives nowhere else:

```
progress.py note bound.spent [--mandate <slug>] [--task <N>] [--round <K>] --text "<which call> relaunched after a failure"
```

**The line carries the failed call's own identity — the same flags its bracket
carried, and a `--text` that names the call**: the verifier for `unlooked`, the
diagnostic for task 5, design checker round 2, C2 pass 2's completeness,
consolidation round 3's checker, the gate runner of the growth re-run. The retry is
bounded PER CALL, `notes` hides the subagent brackets, and several calls of one kind
can be live at once or repeated across a run — a bare "kind relaunched" line counts
them together, and a later call is then denied its first retry, or the same call
granted a second. **Before repeating, count only the lines that name THIS call.**

Models fail transiently, and a second call usually returns.

The PRODUCT finding verifier is the exact structured exception. Its unusable terminal
and alternating physical bracket count carry its one relaunch. Do not add this generic
`bound.spent` counter to that call.

**Twice means the problem is in its prompt or in what you gave it**, not in the agent.
Treat it as a blocker: say what you asked, what came back twice, and stop.

**Never do its work yourself.** That is the exact moment where a controller starts writing
code it must not write, or a reviewer starts verifying its own findings.

### When a compaction takes a result

**A subagent's result lives only in the conversation that received it, and a
conversation dies.** Its ordinary ending bracket keeps the aggregate — a count, a
verdict, a classification — never the substance the next step must act on: its payloads
carry no free text. The four bounded domain calls below add one explicit consumption note
because their limit makes blind regeneration at the final round impossible; every other
lost result follows the ordinary rule directly.

What makes the loss safe is already the design: a subagent is handed **paths, never
contents**, so every input it read — a frozen prompt, a report, a ref, the tree — is
still there. **A result lost before it was consumed is regenerated, never remembered:
close its exact open bracket first when its call site has an unusable terminal, then
relaunch the subagent with the same prompt and act on what comes back.** The relaunch
writes a new journal bracket, and kinds repeat. Never rebuild a lost verdict from memory,
and never act on the journal's aggregate alone — the counts say how much came back, never
what to act on.

A PRODUCT REVIEW finding verifier uses its report identity as the physical-call identity.
Its terminal is the complete structured finding account or `{"unusable":"error"}`,
`{"unusable":"empty"}`, `{"unusable":"lost"}` or `{"unusable":"unusable"}`, together
with the unchanged pass commit, gate and report SHA-256. The unusable terminal does not
settle the report. It permits one physical relaunch against the same report. A second
unusable call is a stable blocker. A complete result forbids another call.

**A bounded domain round is not the physical call that returns its result.** At the four
call sites that pair `bound.spent` with `verdict.consumed` — design checker, code checker,
amendment consolidation, construction diagnostic — the spend allocates one LOGICAL
round. On a successful return, before any edit or route, `verdict.consumed` identifies
the check and outcome in `--data`. Consolidation and diagnostic preserve adverse text
through `--text-file`. Design and code review publish strict immutable result artifacts.
Both bind the accepted task contract, accepted Design generation, checked evidence and
exact Finding 1..N set. Code review also binds the gated candidate and finite file
manifest. Each admitted finding carries its consequence-based impact. Probability stays
private and controls only admission of new candidates. Existing admitted identities
bypass fresh admission. Filtered observations remain only in the attempt-scoped
best-effort `design-risk-filtered.md` or `code-risk-filtered.md` history and enter no
result, count, journal event, correction, handoff or final message.

The immutable admitted result derives `critical`, `important`, and `minor` counts for
its physical terminal and consumed verdict. Callers never supply these counts.
These file transports preserve code, quotes, newlines and shell-looking lines without
parsing them.

A design- or code-checker result-validation refusal does not yet make its physical call
unusable. The implementer sends the exact refusal and same manifest back to that checker
and asks for one complete replacement JSON. It permits at most two repair requests on
the same open call and stops early if the same refusal repeats. Only then does it close
the call unusable and use the ordinary one-relaunch boundary. Neither result repair nor
physical regeneration allocates another logical round or another domain spend. This is a
**live repair context** only. **After compaction**, takeover, loss of its exact count or
refusal, or loss of checker addressability, the controller sends no guessed follow-up.
It writes `{"unusable":"lost"}` to **close the exact open call before regeneration**.

Before a newly written Design enters its first Design-checker round, the implementer
runs one **Design self review**. It checks the complete Design against the frozen task
contract, parent product obligation, directly relevant repository evidence, internal
composition, decisions and supported outcomes. It fixes the Design inside that same
pass. The self review creates no journal event and spends no checker round. Checker
corrections do not repeat it. A retry that preserves an accepted Design skips it; a
retry that writes a new Design runs it once.

The pair is the resume test:

- latest domain `bound.spent`, no matching `verdict.consumed` → the result was never made
  durable. First inspect its physical brackets. A still-open bracket receives its exact
  terminal before any relaunch. For design and code review, continue a bounded repair
  only when its live context survives; otherwise close it as `lost`. Then relaunch the
  same prompt under the same round identity, with a fresh subagent bracket and **no new
  domain spend**;
- matching `verdict.consumed` → never regenerate. Act or finish acting from that exact
  note;
- only a consumed adverse verdict whose correction is complete may allocate the next
  logical round. Consolidation stops after its third logical round. Design and code
  checker rounds 1 through 9 allocate the next round only after one complete correction
  account. Code additionally requires a green ordinary gate. The next immutable manifest
  carries every prior finding for explicit `addressed` or `still-open` verification.
  Design rounds use `design.review.resolved`; code rounds use `code.review.resolved`.
  The exact controller-owned blocker terminal is the only route that stops a Design
  findings batch without that settlement or another round.
  Both checkers have ten logical rounds at most.
  A code finding which proves that valid work is absent from the frozen controller
  contract stops at its current round. `code.review.blocked` freezes the complete batch
  as `contract-blocked` and `carried`. It does not spend later rounds and it is not a
  settlement. The controller uses the reportless C3.9b or C3.9d plan-fault route. The
  corrected plan crosses its normal commit, C2 and baseline boundary. The replacement
  attempt gives the same immutable batch to its first code-checker manifest. An existing
  accepted Design or code obligation composes with this blocker. Failure, pause and abort
  preserve every member until one successful retry gives each member to its matching
  first checker.
  A Design finding with the exact location `frozen task contract` follows the same
  early boundary. At its current round, `design.review.blocked` freezes the complete
  immutable batch without an implementer disposition. It allocates no later Design
  round. The controller uses the reportless C3.9b or C3.9d plan-fault route.
  Round 10 never allocates round 11. Its implementer-owned settlement statuses are
  `accepted`, `refuted` and `alternative`.
  An accepted defect fails through C3.9. A complete account
  containing only refuted findings and valid alternatives can reach the final gate; the
  alternatives remain in the plan's exact `### Disagreement` block. A contract-owned
  `Blocked` uses its distinct terminal before the controller's reportless C3.9b or
  C3.9d plan-fault route. Other `Blocked` or `DECISION` cases stop before settlement. A
  lost result regenerates its current logical round, including design- or code-checker
  round 10.

  A final accepted defect cannot use a generic or reportless failure close. The exact
  immutable checker batch and complete disposition account enter the failure report.
  `attempt-failed.sh` authenticates and hashes that artifact before mutation. The next
  `attempt-started.sh` call must name the same report. Its first design- or code-checker
  generation, according to the source obligation, verifies every accepted identity. The
  obligation propagates through another failure and ends only with the successful retry
  that consumed it. An accepted Design defect stops before implementation and cannot use
  C3.9a. A zero-accepted round-10 Design settlement can authorize implementation without
  changing the adverse checker result to clean. There is no design round 11. A human
  triplet `pause` or `abort` remains immediate. When it follows an accepted final Design
  settlement, the stop note itself preserves the exact verdict, settlement, result hash
  and accepted identities. The next attempt uses `-` instead of a failure-report path,
  and its first Design manifest receives those identities. A later stop propagates an
  inherited obligation until one successful retry consumes it.

  A frozen-task-contract blocker from any Design round uses no failure report and no implementer
  settlement. Its `design.review.blocked` proof and complete immutable batch enter the
  C3.9b or C3.9d `attempt.failed` note directly. A C3.9b controller-contract correction
  then crosses `plan-commit.sh`, the repeated C2 proof, and a fresh green baseline before
  the next attempt starts. C3.9d keeps its existing re-cut route. The next attempt passes
  `-`; its first Design manifest carries every blocked-batch identity as `contract-blocked` or
  `carried`. That exact obligation also propagates until one successful retry consumes
  it.

The per-call failure retry remains separate. An errored, empty or unusable physical call
uses *When a subagent fails*'s own `bound.spent`, named as that call's retry; it never
allocates another domain round either.

---

## Presets

**A session takes a preset. You pass its name, you never reason about model tiers.**

| Preset | What it is |
|---|---|
| **Reviewer** | the strongest model, effort high |
| **ReviewerMedium** | a strong model, effort medium |
| **ReviewerLight** | a light model, effort medium |
| **Fixer** | the strongest model, effort high |
| **Implementer** | the strongest model, effort high |
| **Controller** | the strongest model, effort high — a session that takes the work over from you |
| **Minimal** | the watchdog only — it relays, it never reasons |

**Which role takes which preset is in each mode's file**, not here.

**Subagents take no preset.** You set their **model and effort** explicitly, in the call
that spawns them, and each mode file names both. The level-to-model mapping lives in
`prompts/common/vocabulary.md`, which the workers read too — defined once, for everyone.

---

## Annotations

Every session you create carries a complete annotation set, passed in the same
`create_session` call. Annotations describe the assignment. They do not replace
the journal, the process state, `hidden` or `archived`.

| Key | Values |
|---|---|
| `bwr.schema` | integer `1` |
| `bwr.job` | `implementer` · `reviewer` · `fixer` · `controller` · `watchdog` |
| `bwr.status` | `working` · `idle` · `blocked` · `done` · `failed` · `cancelled` · `superseded` |
| `bwr.mode` | `spec` · `construction` · `product-review` · `amendment` — the mode's own name. **One session carries none: the watchdog**, which lives through every mode. |
| `bwr.feature` | the feature's short name |
| `bwr.lot` | `lot-1`, `lot-1.1` — **keep the `lot-` prefix**, a bare `1.1` parses as a number |
| `bwr.task` | integer from 1; implementers only |
| `bwr.attempt` | integer from 1; implementers only |
| `bwr.round` | integer from 1; spec reviewers only |
| `bwr.mandate` | stable lowercase slug; reviewers only. The mode file fixes the list — never invent one. |

- **You own every annotation.** You set the complete set at creation and make every later
  update. Children never touch their own. Only `status` changes during an assignment.
- **A status change goes through the script, and only through it** — it makes the change
  and records it in one call:

  ```
  progress.py session-status <id> <status>
  ```
- **Your own are the exception, and you set them yourself.** The first orchestrator of a
  feature was started by the human, so nobody annotated it. **When the human tells you to
  start writing — not during the discussion before it — check whether you carry the set,
  and give it to yourself if you do not**: `bwr.job=controller`, the feature, the mode, and
  `working`. An orchestrator created by a handover already has them. **And keep your own
  `bwr.mode` and `bwr.lot` current — update them when you enter another mode or move to
  another lot.** The journal derives every line's context from the caller's annotations;
  a stale value stamps the wrong one on everything you record from then on.
- `status` is workflow state, not process state. `working` = active · **`idle` = parked
  with nothing pending**, a reviewer whose report is being verified, a fixer between two
  rounds · **`blocked` = it cannot finish until you answer** · `done` = accepted, no reuse
  · `failed`, `cancelled`, `superseded` = terminal.
  - **A child running a long command is `working`.** It is not waiting for anyone.
  - The two parked states are not interchangeable, and the watchdog treats them
    differently: **nothing is owed to an `idle` child, an answer is owed to a `blocked`
    one.**
  - The three terminal ones are not interchangeable either: **`failed`** = it did not
    deliver what it was asked · **`superseded`** = it was working correctly and something
    upstream replaced it · **`cancelled`** = the human stopped the run.
- **Never use a broad annotation filter as the target of a destructive mutation.** Batch
  updates take exact ids.
- A failed annotation update: retry once, record it, continue, report the stale annotation
  at close. A malformed set that blocks creation is fixed before retrying — never
  knowingly create an unannotated session.

### Reading them back

A finished child is archived **and** hidden. Any query that must find it needs both flags
and a limit:

```
mcp__twicc__sessions
  --annotation bwr.feature=<feature> --annotation bwr.lot=<lot>
  --include-archived --include-hidden --limit 500
```

Without the first two flags the query returns `[]` for everything already finished — an
empty list that reads like "nothing there" and is nothing of the kind. Without `--limit`
you get 20 rows and no warning about the rest.

---

## Concurrency and visibility

- **Never hide a running session.** Hide it at its retirement point, where you also
  archive it.
- **In SPEC and PRODUCT REVIEW, the cap counts only exact reviewer sessions in that
  review pool.** Match `job`, `mode`, feature workspace, lot, round and mandate as the
  mode defines them. A fixer, implementer, watchdog, other generation or provider
  subagent does not consume that reviewer pool. A reviewer whose verifier is running is
  parked and still owns its one reviewer slot.
- **A child holds its slot until its work is accepted**, which can be well after the
  moment its report lands. Launch the next wave on that, or you go over the cap.
- **The human sets the cap**, once, in the same widget call as the provider. Record it and
  apply it throughout. Never raise it because a phase has more work.
- **Never refill a review pool from memory.** At every possible slot change, run the
  frozen read-only helper for the current mode:

  ```sh
  python3 "<workspace>/prompts/common/review-pool.py" spec
  python3 "<workspace>/prompts/common/review-pool.py" product-review
  ```

  Launch every assignment under `launch now`, record each `session-started` immediately,
  and rerun the helper. Continue only when the pool is full or the pending queue is empty.
  Then return to the exact report or verifier result that triggered the checkpoint.
- Run this checkpoint after every accepted retirement, every incoming reviewer or verifier
  message, every replacement, and before yielding while review assignments remain. An
  incoming second message never cancels a refill already exposed by the journal.

**Where parallelism actually exists**

| | |
|---|---|
| Spec review | parallel — one session per mandate |
| Completeness | a single subagent |
| **Construction** | **strictly sequential. No exception.** |
| Product review | parallel — one session per lens, and one verifier launched per report **as it arrives**, never waiting for the others |

**Never run two implementers at once, however independent the tasks look.** They commit on
the same branch, so they commit over each other, reset each other, and fight over the git
refs. Making it safe would need one worktree per task and one full gate per worktree.

The two task checkers are not an exception: they run inside the implementer's own session,
so they add no second writer.

---

## Question routing — one session faces the human

- **Every child is created with the question widget disabled.** They cannot ask, so their
  prompts tell them what to do instead: a minor ambiguity becomes a stated assumption; a
  genuine blocker, or anything only a human can answer, goes to `parent` and they stop.
- You answer what the spec, the plan and the code settle. You escalate the rest as **one
  batched question**. The human monitors one session: yours.
- A child that cannot finish before you answer goes `blocked`, and back to `working`
  immediately before you send the answer.
- **Escalation is the cheap path, not a last resort.** A requirement the spec never settled
  costs one question now, or every remaining phase plus a reversal later.

---

## Disagreements

**Arbitrate yourself, from the code — for two exchanges, then stop.**

Two shapes: a finding a worker declined that a later reviewer re-raises, and a claim you
sent back that the worker re-asserts. Count the round trips on the **same subject**:
stated, refuted from the code, re-stated, refuted again. At the third you are no longer the
arbiter — a disagreement surviving two exchanges is the signal that the problem lies
elsewhere. Write the analysis and escalate.

**A worker that never declines anything is not a worker with perfect inputs.** Declining
with evidence is a success. A run where every single finding was accepted is worth a look
at whether anybody is checking, or whether confidence alone is carrying the day.

---

## Git

### Who may touch what

| Role | Rights |
|---|---|
| **Implementer** | `git add` and `git commit`, on **its own task's write set — the code, and the plan copy it refreshed into `docs/plans/`**. Nothing else. |
| **You, the controller** | working git refs, `reset`, diagnostic worktrees, and **the document commits: the spec, the initial plan, an amendment with the spec it lands in — and the one-line `.gitignore` commit when workspace creation requires it** |
| **Reviewer** | nothing |
| **Spec fixer** | edits files, **never commits** |

**The implementer produces, you record.** An implementer never resets: it would destroy
evidence, and it is a process decision.

### You name the files you commit

**Never `git commit -a`, never `git add -A`.** List the paths, every time — **and
literally**: even quoted, git reads `*`, `?`, `[…]` and a leading `:` in a path as
pathspec syntax, a pattern that can stage files the actor never named. The workflow's
scripts set literal semantics themselves; a git command typed by hand with a path
argument is prefixed `git --literal-pathspecs …` — `vocabulary.md`'s rule.

A blanket add takes whatever else the tree happens to hold — a file touched to debug and
forgotten, another actor's half-written work, a document nobody has reviewed — and puts it
in a commit that claims to carry something else. **The tree is shared, and it is rarely
clean:** a spec commit can land while a task is half-written, and a task commit can land
while a plan copy is one design behind.

**One exception, and its intent is the opposite:** preserving a whole state you are about
to erase — a failed attempt, a paused one. There, taking everything is the point, and the
commit's subject says so.

**That exception rests on one thing: the tree is the run's.** Construction refuses to
start on somebody else's uncommitted work, and that check is what makes taking everything
safe. Without it, the same command sweeps a human's change into a commit it never belonged
to, and the reset that follows takes it out of the tree.

**And the check opens a contract; it does not close one.** It is taken once, and every
later gesture relies on it staying true: **the tree is the run's until the run stops.**
A human who must touch the checkout pauses the run first — the pause puts the tree on
validated work and preserves what was in flight, and the resume re-enters through the
same checks. Work that arrives from outside mid-run has no protection a script can give
it: during an attempt nothing can tell it from the attempt's own, and a preserve takes
it onto the try ref with the rest. **Wherever the run expects a clean tree — an abort
with nothing in flight, a rewind — anything found there is treated as the ground check
treats it: stop and ask. Never commit it, stash it, or reset it yourself.**

### Refs, not tags

A tag that moves is a surprise, and it pollutes a namespace the human owns. This workflow
records where each task landed as git refs under **`refs/bwr/<run>/`**, `<run>` being the
workspace's own name — invisible to `git tag`, never pushed, deletable in one sweep.
**That segment is what keeps two features of one repository apart**, and a git worktree
does not: it shares its repository's refs. Their naming is in
`prompts/common/vocabulary.md`; the commands that post, move and read them are in the mode
that does it.

**A result ref is not an attempt close.** `attempt-in-flight` falls only after the owning
success, failure or stop call has made every required tail durable. While that file
exists, a stable task ref proves only that success posted its first gesture; a try ref
proves only that preserve and reset reached it. The note, diagnostic checkout, stopping
point or identity removal can still be missing. Before its first preserve or reset, a
failure or triplet stop atomically extends that existing identity with `closer
<failure|stop> <call-hash>` and `call <workspace-relative-lossless-shell-spelling>`. The hash binds every
result-defining argument: the failure classification, or the stop mode and normalized
spared paths. The call line gives a takeover the exact recovery call without relying on
session memory; no script evaluates it. The exact owner may consume its own ref and
finish idempotently. A different closer, classification, mode, spared-path set or
terminal note refuses before mutation. Success needs no closer binding: its stable task
ref selects `attempt-succeeded.sh`. Its exact final gate operation is recovered from the
unique accepted task result with `gate-check.sh find-task`, and the closer consumes both.
It also refuses a failure or stop binding. Every other operation refuses the identity, even when either ref exists, and
prints the frozen call or the documented success tail. It never removes or replaces the
file. Only the absence of `attempt-in-flight` lets the next normal operation begin.

**A controller-operation marker also outranks every attempt closer.** While
`document-copy-in-progress`, `spec-commit-in-progress`,
`amendment-commit-in-progress`, `spec-breach-recovery-in-progress` or
`gate-check-in-progress` exists,
`attempt-succeeded.sh`, `attempt-failed.sh` and triplet `stop.sh` refuse before their
first ref, tree, journal or attempt-identity gesture. The exact document, spec,
amendment, breach or logical-gate owner settles its own marker first. A malformed or
symlink marker is foreign state: every closer refuses it read-only and leaves it for the
human.

### What is never written here

**How to commit.** The message body, the trailers, the conventional-commit format, the
co-author: that lives in the project's `CLAUDE.md` and the agent reads it. You say **what**
to commit — the task's write set — and the subject line. Nothing else. **Every commit that
lands in the repository's history follows the project's conventions** — the scripts that
make one take the subject as an argument for exactly that reason.

**And a subject travels like any free text.** Inside plain double quotes the shell
expands `$…` and executes backticks before any script sees the argument. Write a subject
that contains shell-sensitive characters to a fresh real file with your provider's
file-write tool. Pass `"$(<"$SUBJECT_FILE")"` as the script's subject argument, then
remove the file. The shell reads the fixed file path; it does not parse the file's
contents as source. A commit subject is one physical line and has no trailing newline.

**The preserving commits are the one exception, in the other direction.** `— FAILED`,
`— PAUSED`, `— ABORTED` are bookkeeping behind a ref, never history: they carry the
workflow's own subject and skip the project's hooks (`--no-verify`) — a message
convention governs the history humans read, and a hook must not kill a preserve halfway.

**And you never create a branch on your own initiative.** Work happens on the current
branch; isolation is the human's decision. **The one branch you ever create is the one
their *create it for me* answer at the worktree checkpoint orders**: a new worktree
needs a branch attached at the validated commit — the current branch is already checked
out here, and git will not attach it to a second worktree — so creating that branch is
part of the operation the human just authorized, and you announced it, name and path,
before making it.

---

## The watchdog

A heartbeat session that reports the state of your open children every 30 minutes. Launch
it once, right after the workspace exists, from
`<workspace>/prompts/common/watchdog-prompt.md` — that file is a template you fill in and
send as the creation prompt.

- **Always `claude_code`, preset `Minimal`**, whatever provider the human chose for
  everything else: the cron it schedules is a Claude Code mechanism, and it relays without
  ever reasoning.
- **Pass the repository's exact TwiCC project explicitly.** The watchdog's whole message
  carries the fixed repository, workspace and source-role identity from its template.
- **Visible, never hidden**, with the `- ` prefix like every internal session. The human
  sees its ticks arrive in your conversation and must be able to find the session behind
  them.
- **One per orchestration session, not per phase.** It lives through every mode and, if
  this session goes on to drive another lot, through that one too.
- A controller that stops mid-work stays silent, and at night nobody notices. Its tick is
  what wakes you.
- Each tick carries, per child, its live state, **how long it has been in that state**, and
  **how long since it last wrote anything**. Together those separate a child that is
  working from one that is stuck; neither number does it alone.
- Each tick also reports every exact open provider-subagent bracket from the journal.
  The controller checks the named owner's provider-native roster. It never invents a
  result, launches a duplicate or uses TwiCC process wait for that call.
- Every tick ends with a `RESUME CHECK`. With open provider subagents, reconcile them
  first and then resume interrupted work. Without one, resume unfinished work now. A
  blocked controller pings the human once only when that exact blocker is new or unseen.
- A watchdog dependency error keeps the state unknown. Its final `RESUME CHECK` requires
  one exact state-inspection retry before dependent work can resume. It never reports an
  empty child or provider-subagent set by inference.
- `⚠` marks 40 minutes without a write, and it marks **what somebody has to act on**.
  - A child whose status is `idle` is **never** marked: you parked it with nothing
    pending, and it may sit there for hours doing exactly what it should.
  - **A `blocked` child is marked**, and that is the point: it means an answer is owed, by
    you. Its silence is normal for it, and it is the visible symptom of a debt somebody
    forgot.
  - A `working` child silent inside a long command is marked too. You ask it where it
    stands before concluding anything.
- **Stop its process, then retire it — in that order — before you delete the
  workspace**, not with the other sessions. Retiring stops the cron's future ticks; a
  tick already running is stopped only by `mcp__twicc__processes_stop`, and its script
  lives in the workspace's `prompts/` copy — deleted under a live tick, it fails into a
  run that already succeeded.
- **Stop its process and retire it before handing a lot to a new session too** — the
  same order; the handover rules carry it. That session launches its own, and two
  heartbeats on one chain means two sets of ticks and no owner.

---

## The journal

**Every run writes one journal**, `<workspace>/progress.jsonl` — one line per event,
appended and never rewritten. It is what a session reads after a compaction, what a new
orchestrator reads when it takes over, and what the dashboard draws.

**You never write it by hand.** `<workspace>/prompts/common/progress.py` owns it, and
**the rules for calling it are in `prompts/common/progress-rules.md`** — read that file
before your first call. The exact subcommand and its flags are written wherever you have
to make a call — and **`progress.py` there is a shorthand**: nothing puts the script on
`PATH`, so every call is really `python3 "<workspace>/prompts/common/progress.py" …` —
the path quoted, like every path in every command (`vocabulary.md`'s rule).

**Some of its subcommands also do the thing they record** — changing a session's status,
retiring one. Where they do, **you never make the TwiCC call separately**: a record
produced by the act itself cannot drift from it.

**A bounded gesture journals its spend, as it spends it.** Design and code each have ten
logical checker rounds. Consolidation has three. Each task has one logical diagnostic, one
send-back and one relaunch. Every such count lives in `bound.spent` notes and nowhere
else once a compaction has passed. **Before allocating a new bounded gesture, count its
lines in the notes.** A physical regeneration of an unconsumed bounded verdict reuses
its latest identity under the `verdict.consumed` rule above; it is not another gesture.
Each bounded route's call site carries the exact line.

```
python3 "<workspace>/prompts/common/progress.py" notes
                           what was ruled, what was refuted, where the work stands
```

---

## Retirement and housekeeping

- **Retire a child the moment its work is accepted.** Do not wait for the phase to end.
  **What "accepted" means depends on the role, and its mode file says so** — never your
  impression that it looks finished.
  - **A child whose output is still being checked is not done.** Retire it once the check
    has ruled and anything sent back has come back corrected. Retire it earlier and there
    is no longer anyone to send anything back to.
- **One call does all three, in the right order:**

  ```
  progress.py session-retired <id> <status> --archive --hide
  ```

  The order is: terminal status, then archive, then hide. Hiding first silences later
  broadcasts, so the archive never reaches the UI — the script does it in that order, and
  records what actually succeeded.
- **Never archive an orchestrator, yourself included.** Those sessions are where the
  human's own conversation lives. An outgoing orchestrator sets itself `done` once its
  successor exists, and stops there: archiving them is the human's call, whenever they want
  it.
- **Never clear annotations at retirement** — they are how the run is reconstructed
  afterwards.
- **Never re-launch a child because a watchdog tick surprised you.** The journal says
  what exists; the tick says what state it is in. Only both together justify an action.
- A child that went quiet without delivering is retired `failed`, and its replacement is a
  fresh session, never a resumed one — and the replacement is worth a line:

  ```
  progress.py note session.replaced --text-file "$JOURNAL_TEXT_FILE"
  ```

  **Stop its process before you retire it** — `mcp__twicc__processes_stop`. **Silent is
  not stopped**, and retiring a session does not stop it either: it can wake at any
  moment, into a run that has already replaced it. Whatever it then writes lands beside
  its replacement's work — the same report file, the same tree — and nothing says which
  of the two produced what. **Its mode's file says what else that costs**, where it
  writes to the tree.

  **And free the report path it was given, before its replacement exists.** Whatever the
  dead child left there moves aside — the same name with `-failed`, `-failed-2` if that
  one is taken. Nothing is overwritten: the partial reading stays readable under a name
  that says what it is, and the fresh session finds the path it is handed empty.

  **A cumulative log is not a report, and it never moves.** The fixer's decisions log
  carries every round before this one; its replacement inherits it and appends, exactly
  as a rotated fixer does. What moves aside is a file that held one assignment's
  deliverable, nothing else.

---

## Red Flags — STOP

These fire in any mode. Each mode file carries its own, phase by phase.

| What you are telling yourself | The reality |
|---|---|
| "I'll just fix this one line myself" | Every change goes through a worker and the gate. A line you did not test is a line nobody tested. |
| "This is a small product choice, I'll make it" | It is the one thing only the human answers, and it never looks big from here. |
| "The worker accepted every finding, quality is high" | Or nobody is checking. Declining with evidence is a success. |
| "This one is true but minor, I'll drop it" | You are judging its value. That is the one thing you never do. |
| "The spec was wrong, I'll edit it" | Only if no lot was built on that part. Otherwise an amendment. |
| "This amendment touches a lot of things, but I'll manage" | If its reach will not close, it is not an amendment. |
| "The lot is done, the watchdog can stay" | Its cron keeps pinging you about a run that ended. Stop its process, then retire it, before deleting the workspace. |
