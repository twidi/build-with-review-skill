# Vocabulary

The words this workflow uses, and what each one means concretely. Everyone reads this
one: the session that orchestrates, and every session or subagent it launches.

---

## The work

**Feature** — one specification document, cut into lots, in `docs/plans/`. `<feature>`
is its **short name, a slug, no date, no suffix** — `peer-revocation`. Every path in
this workflow is built from it:

```
docs/plans/<date>-<feature>-design.md              the spec
docs/plans/<date>-<feature>-<lot>-plan.md          one plan per lot, a copy
docs/plans/<date>-<feature>-amendment-<N>.md       one per amendment
<workspace>/plans/<lot>-plan.md                    where that plan actually lives
<repo>/.superpowers/bwr/<date>-<feature>/          the workspace
```

**The workspace's name is the stem of everything the run produces**, so a lot built weeks
later still carries the day the workspace was created. **The spec keeps its own date**: a
feature can start from a spec validated months earlier.

**Lot** — one delivery unit the spec declares: `lot-1`, then `lot-1.1` if a review
forces a correction. The suffix orders, it does not divide. **The name is exact**:
`lot-<N>`, or `lot-<N>.<M>` for a correction — both counting from 1, no leading zeros,
nothing else. It is a path segment, a git-ref segment and an annotation value at once,
and every script refuses any other spelling.

**Plan** — one document per lot. It says what each task must achieve, in what order.

**It lives in `<workspace>/plans/<lot>-plan.md`**, and is copied into
`docs/plans/<date>-<feature>-<lot>-plan.md` just before each commit. **Read and write
the workspace copy; never write into `docs/plans/` directly.** The workspace is outside
git, so a `reset` cannot take the plan with the code.

**It is dated, not maintained**: each section says what was true when that task was
done, and nobody refreshes it afterwards. When the plan and the code disagree, **the
code is right**.

**Task** — one unit of a lot's plan. It ends in exactly one commit. It means something
on its own, and the following tasks build on it. **A task is not a feature** — the
feature only exists once every task is done.

**Attempt** — one try at building a task. Numbered from 1. A failed attempt is kept on
a git ref and never resumed: its replacement is a fresh session.

---

## Verification

**The gate** — the project's complete verification command list: every test suite,
every lint, every type check, every build. Discovered at the first entry, stored in
`<repo>/.superpowers/bwr/gate.md`, **grown only by the human's validation** — a
candidate noticed at C0 or the final task boundary joins, leaves or is renamed only
through the same decision — and **run unchanged by whoever runs it**: never narrowed,
never partial, never a subset chosen for the work at hand. The controller publishes a
complete validated list through `gate-write.sh`; the implementer and runner never edit
it.
One non-blank line is one complete command, except a full-line comment whose first
non-whitespace character is `#`. That comment preserves human-readable rationale in the
frozen file. It is never executed, reported or counted, and it grants no machine
exemption from the gate-surface scan. A later `#` remains part of its exact command.
The path is either absent before first discovery or one real regular file at that exact
checkout-local leaf. A symlink, dangling symlink or other occupant is foreign state and
is never followed, compared, copied, adopted or replaced.

**Green** — the gate ran and reported nothing, and its commands left the tracked and
untracked repository state unchanged. **There is no partial green.**

A green gate proves that nothing tested broke. **It does not prove the code is right**:
a wrong test over wrong code is green, and so is a test that asserts nothing.

**Checker** — a subagent that judges one bounded thing and disappears. It reports to
whoever spawned it, changes nothing, and never spawns another checker.

**Finding** — a defect someone reports. It says where, what, and why it matters, and it
is stated so that it can be checked rather than believed.

### Two reviews, never the same one

| | **Spec review** | **Product review** |
|---|---|---|
| What is read | a specification, before it is built | a product, after it runs |
| Unit of work | a **round** | a **pass** |
| How it is cut | by **mandate** | by **lens** |
| What answers a finding | a **fixer** edits the document | a **sub-lot** builds the correction |
| Where | MODE SPEC, phase S3 | MODE PRODUCT REVIEW, phases R1 and R2 |

**Never say just "the review".** The words that go with each are different on purpose:
*round* and *mandate* belong to the spec, *pass* and *lens* to the product. If you are
reading one of those words, you already know which review you are in.

**Adjudication** — the controller's product-review work after reports arrive: verify each
finding, close what proof disproves, dedupe what remains, ask the human only for
DECISIONs, and route the surviving work. It is not a second review and it makes no
product choice.

---

## Model levels

Where this workflow asks for a level rather than a model, it means:

| Level | Claude | Codex |
|---|---|---|
| **strongest** | Fable | Sol |
| **strong** | Opus | Sol |
| **light** | Sonnet | Terra |

**Never the smallest tier** — Haiku, Luna. An agent that skims is worse than none: its
answer still looks like a verdict.

Effort is separate, and always stated with the model: `low`, `medium`, `high`.

---

## Decisions

**DECISION** — a choice about **what the product does** that the specification does not
settle. **Only a human answers one.**

**Ruling** — the human's answer to one DECISION. A ruling is final input to the run; it
is not a finding or a verifier verdict.

**Product-answer identity** — the collision-free name of one durable human answer.
`B<N>/D<M>` names decision `D<M>` from product-review batch `B<N>`. `R<N>` names one
product ruling raised outside a batch. An operational human choice, such as whether an
amendment sweep may continue, has no product-answer identity and never enters the
product-answer state.

**Product-answer state** — the run-wide complete state of every product-answer identity:
its exact effective answer, authority, active or superseded status, and current product
obligation. It is reconstructed from all identified `ruling`, batch settlement and
supplement events, followed by every ready conflict resolution in journal order. A batch
close, applied line or completed sub-lot does not remove its answer. Only a later human
conflict resolution can supersede or qualify one. Before any spec edit or amendment route,
the current owner writes one complete state artifact under `reports/answers/` and checks
its proposed change against every active answer.

**Authority quiescence** — the run-wide precondition for a fresh product-route consumer.
Every identified ruling has its complete ordered answer state. Every opened batch and
conflict generation has its complete ordered source, settlement and ready state. No open
spec breach, adverse SPEC-loop preservation proof or current unconsumed spec-edit
authorization owns the run. This condition is global: an unfinished boundary for one
owner blocks a route for another. Conflict and breach lifecycle events build this state;
they do not consume a product route and are not blocked by their own unfinished chain.
Every authority boundary must also have its exact typed identity and generation key. A
malformed or unkeyable line blocks the run as damaged state; it never disappears from
the check. An operational `ruling` has no `ruling` identity and stays outside this state.

**Direct ruling route** — one identified `R<N>` answer outside R2.4. Its exact route is
one of `closed`, `spec-in-place`, `amendment`, `spec-fixer`, or `amendment-fixer`; no
synonym is valid. Every route ends in one `ruling.applied` line bound to the latest
effective human authority generation by `ruling.ready` or the last
`decision.conflict.ready` that changed it, plus that boundary's reference and artifact
SHA-256. A complete recheck can change its mechanical route but not its human authority.
A later conflict can change the same stable R, but it creates a new effective generation
and never makes the old applied line terminal for the new answer. `closed` terminalizes
immediately. The two fixer routes terminalize only after their owner-linked assignment,
accepted review close, committed document and complete preservation proof.
Every direct route consumer requires authority quiescence and the exact current authority
tuple. An accepted route proof is followed immediately by its terminal. A new ordinary
conflict cannot open across that tail.

**Decision batch** — the durable record made when one product-review pass has at least
one DECISION to ask. It gives a stable ID to **every verified claim from that pass**,
including claims the current spec refuted. One of its in-place answers can change the
passage that refuted such a claim. If that makes an unanswered DECISION live, the human's
new answer supplements this same batch; only claims reactivated by this batch's own
in-place edits can do so. Its `decision.batch.sourced` boundary carries the unique list
of every stable D identity, including initially refuted ones, and the complete structured
F/D item-and-verdict index. Each completed batch recheck replaces that whole verdict
index. One decision batch can open **one amendment containing all of
its built-part rulings**, initial, supplemental and conflict-resolved. It stays open until
every answer has reached the spec or its close, and every remaining correction has
entered a sub-lot or been disproved against the changed spec.

**Recheck snapshot** — the complete latest state after an in-place spec commit. For a
batch owner, it repeats every stable local claim, its new verdict and exact observation.
For every owner, it also repeats the run-wide product-answer state: each identity's
active or superseded status, effective human answer, authority and current route. A
snapshot is an immutable artifact followed by one
`decision.recheck.completed` line. In journal order, the last completed recheck or
conflict-resolution state replaces earlier claim and answer state; a partial file and
remembered verifier results replace nothing.

**SPEC round snapshot** — the immutable `reports/spec-review/round-<N>-spec.md` bytes
published by one exact `round.opened`. Every reviewer and every receipt in that round
uses its SHA-256. A fixer return publishes its resulting spec under the parallel fixed
`round-<N>-fixer-spec.md` path. A later round consumes that identity, never the mutable
final-path file by memory.

**Spec edit authorization** — one `spec.edit.ready` boundary published before a bound
repository-spec edit. It names the active `R<N>`, `B<N>/D<M>` or breach-repair owner, its
current route, the latest complete authority generation, the current source SHA, the
exact spec-path argument and the SHA-256 of the complete state artifact. The bound
`spec-commit.sh` form authenticates these structured facts before staging and freezes
the ready operation in its pending marker. The script does not interpret the artifact's
proposal prose. Its post-commit global recheck proves that the exact named proposal was
implemented and all other active answers remain present; a mismatch is a spec breach.

**Decision conflict** — two or more active product answers that the current spec cannot
carry together. Its owner is one batch `B<N>` or one individual ruling `R<N>`; conflict
numbers count from 1 within that owner. `decision.conflict.opened` freezes the owner,
generation, fully qualified incompatible answer identities and exact complete state that
exposed them.
`decision.conflict.sourced` proves its immutable question is whole before the human is
asked. Its atomic settlement can keep, supersede, qualify or replace answers, combine
them, or state how all answers coexist. A combined or qualified replacement uses the
owner's lowest active answer identity as its stable carrier; the artifact keeps every
original answer as history. If the current owner is wholly superseded by an unchanged
older answer, no resolving spec edit is owed.
`decision.conflict.ready` proves the complete active/superseded answer state and all
current obligations are durable before any resolving route runs. Conflict generations
are ordered and never overwrite one another. A conflict with
`purpose:"restore-baseline"` is the same machinery applied to an adverse breach recheck:
the owner answer and missing active authorities cannot yet form an authorised baseline.
Its one human question either preserves those authorities through an exact spec repair,
or explicitly revises, qualifies or supersedes them.

**Spec breach** — a bound in-place spec commit whose complete post-commit recheck proves
that it erased an active product answer despite its pre-commit compatibility proof. Its
run-wide identity is `spec.breach.opened` number `<K>`. The bad commit stays in history as
evidence. `spec.breach.corrected` names its one corrective child, which restores only the
spec from the bad commit's authorised parent and moves a still-live attempt's mark.
Every complete breach recheck records `restored:true, missing:[]` or
`restored:false, missing:[…]`. An adverse result enters one durable decision-conflict
generation; its ready target can bind a crash-safe spec repair or an explicit authority
revision, followed by another whole recheck. `spec.breach.restored` follows only a
structured success that proves every preservation authority has its authorised state and
obligation again. The bad commit's exact owner answer stays a future obligation until
then; its absence after rollback is not itself a failure. Only then can the original
proposed change resume. No conflict retroactively authorises the bad commit.

The trigger, and it applies at any moment, in any phase:

> **You are about to choose a behaviour the spec does not state. Stop.**

Reporting one costs a message. Deciding one silently costs the feature being rebuilt
later, when someone sees what was built and reverses it.

---

## Command completion

**An intermediate tool result is not a command result.** A command is complete only when
the tool reports a terminal status for its process. Output returned without that status
is only an intermediate observation.

When the tool says the process continues and supplies a process handle:

1. Retain that handle.
2. Use the provider-native continuation or wait mechanism on the same process.
3. Never run the command again while that process remains active.
4. Do not classify, consume or replace the command from the intermediate result.

The handle's name and the continuation mechanism belong to the provider. This workflow
does not prescribe provider-specific fields or calls.

**Empty intermediate output is neither success nor failure.** It does not mean that the
completed command has empty output. Collect the terminal exit status, stdout and stderr
from the same process.

A non-zero terminal exit status is a failure. A zero terminal exit status is a success
only when the command's output contract is also satisfied. For example, a successful
command that promises a path must return that path. Missing required output is a
technical failure even when the terminal exit status is zero.

---

## Git

**Git ref** — a named pointer to a commit, like a branch or a tag but invisible to
both. This workflow records where each task landed under **`refs/bwr/<run>/`**, where
`<run>` is **the workspace's own name**:

```
refs/bwr/<run>/<lot>/task-0                the state before the lot's first task
refs/bwr/<run>/<lot>/task-<N>              task N, validated
refs/bwr/<run>/<lot>/task-<N>-try-<K>      attempt K at task N, which failed
refs/bwr/<run>/<lot>/rewound/task-<K>      task K as it was before it was redone
refs/bwr/<run>/<lot>/attempt-base          where the attempt now running began
```

**`attempt-base` is the only one that moves.** It is re-posted at every attempt, and it
answers a question nothing else can: whether that implementer committed anything.

**The run's name is in there for a reason.** A repository holds more than one feature
over its life, sometimes at the same time — and **a git worktree shares its
repository's refs**, so isolating a feature in one does not separate them. Without that
segment, two runs would both write `refs/bwr/lot-1/task-1`, git would accept the
overwrite without a word, and a reset would put the tree on another feature's commit.
And the name itself is kept unique across every worktree: **creation refuses a feature
that already has a run in another checkout**, because the refs those two runs would
write are one namespace.

**There is no task 0.** `task-0` is the lot's starting point, posted before task 1 —
which is what makes *"reset to `task-<K−1>`"* work for `K=1` like for any other. Every
lot posts its own, sub-lots included.

Read one exactly like a commit:

```sh
git show refs/bwr/<run>/lot-1/task-3                    what task 3 changed — one task, one commit
git show refs/bwr/<run>/lot-1/task-3:src/foo.py         a file as it was then
```

**A git ref is how you read a past task.** `refs/bwr/<run>/lot-1/task-1` **is** task 1.

Two scripts do exactly that, and they work the ref names out from the lot and the task
number — `<workspace>/prompts/construction/task-diff.sh lot-1 3` and
`task-show.sh lot-1 3 src/foo.py`. **Use them; the two lines above are here to say what a
ref is, not to be typed.**

**Write set** — the files one task is allowed to commit: the code it wrote, and its own
section of the plan. Nothing else.

---

## Paths in commands

**A path is data, and in a command it is always double-quoted** — the script you run as
much as the arguments you pass it:

```sh
"<workspace>/prompts/construction/task-diff.sh" lot-1 3
python3 "<workspace>/prompts/common/progress.py" notes
```

Nothing constrains a repository, worktree or file name to shell-safe characters:
unquoted, a space splits the path into several words, and a `$` or a backtick in it
expands before anything runs. Every script here quotes its paths internally — but the
shell must find the script and hand the arguments over intact first, and only the
caller's quotes do that. **Every `<…>` placeholder that stands for a path, in any
command or equivalent block of this workflow, is read with those quotes on.**

**And the quotes are only half the journey: git then reads the argument again, as a
PATHSPEC.** `*`, `?`, `[…]` and a leading `:` are pattern syntax to `git add`,
`commit`, `diff` and their kin, quoted or not — a path named `docs/[v].md` selects by
pattern, not by name. Where a path is data, git is told so: the workflow's scripts set
literal-pathspec semantics themselves, and **every git command you type by hand with a
path argument is prefixed `git --literal-pathspecs …`** — the flag costs nothing on an
ordinary name and is the only thing that makes an unusual one mean itself.

---

## Who is who

**The human** — decides what the product does. They are the only one who answers a
DECISION, and most workers never talk to them.

**The user** — lives with the feature once it ships. Nobody talks to them either; they
are who a DECISION is argued about.

**The controller** — the session that orchestrates a whole feature. It writes the spec
and the plan, launches everyone else, and faces the human alone.

**Your parent** — the session or agent that launched you. **It is not a human.** If you
have something to say, you say it there.

### Session and subagent are two different things

**Session** always means a **TwiCC session** — created with `mcp__twicc__create_session`
or the `twicc` CLI, visible in the human's list, carrying annotations, retired when it
is done.

**Subagent** always means **your provider's own internal mechanism** — the `Agent` tool
on Claude Code, its equivalent on Codex. It is not a TwiCC session, it does not appear
in any list, and it disappears when it has answered.

**When this workflow says subagent, never create a TwiCC session instead.** They are
not interchangeable: one is machinery the human watches, the other is a call you make
and consume.

**Workspace** — `<repo>/.superpowers/bwr/<date>-<feature>/`, git-ignored, created by the
controller and alive for as long as the feature is. It holds a frozen copy of every
prompt under `<workspace>/prompts/`, the run's journal `progress.jsonl`, and `reports/`.

**Your parent gives you its path**, and every prompt path in this workflow is written
relative to it. Read the copy, never a prompt from anywhere else — the copy is what was
frozen when this run started.
