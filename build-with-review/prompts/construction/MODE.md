# MODE CONSTRUCTION

**This file governs construction.** Everything you need is here, in `<workspace>/SKILL.md`,
and in the files this one names.

You are the controller. You turn a validated spec into a lot of committed code: the
ground, a thin plan, a completeness pass, then one task at a time until the gate is
green on all of them. **You write the plan. You write no code** — every line that
reaches the tree is written by an implementer session you launch.

Read `<workspace>/prompts/construction/plan-format.md` before C1. It holds the document's shape and its worked
examples.

---

## Before you start

You need, in hand:

- the **spec**, validated, committed, with its lot breakdown
- **which lot** you are building
- the **concurrency cap** and the **provider**, both answered by the human

**The workspace** — the first thing you do, before any child: run the script that
creates it, unconditionally — only a feature's first session creates anything, and the
script decides. `SKILL.md` has the call, in the section *The workspace*. On `EXISTS`,
create nothing, run `progress.py notes`, then run
`progress.py construction-verdict-check history`, and continue. The second command
revalidates every consumed design, code and diagnostic verdict before any resume route
uses it.

**If you arrived from a handover**, say so before anything else:
`progress.py note handover --data '{"from":"<the outgoing session id>"}'`

Then launch the watchdog, once, if it is not already running.

*Until the workspace exists you are reading this skill from where it is installed. From
the moment it does, read the frozen copy under `<workspace>/prompts/` — and that is the
path you hand to every child.*

**If the spec is not validated, you do not enter.** Go back to SPEC.

---

## C0 — The ground

The gate is this project's complete verification command list. It lives in
`<repo>/.superpowers/bwr/gate.md`, git-ignored, **one per project, not per feature** —
the next feature inherits it.

Its line grammar is closed. Every non-blank line is either one complete command, or a
full-line comment whose first non-whitespace character is `#`. Comments preserve the
human-validated rationale in the frozen file. They are never executed, reported or
counted as commands. A `#` later in a command remains part of that exact command. A
comment grants no machine exemption from the gate-surface scan. The file must contain at
least one command, and blank lines are refused.

**It contains every verification the project has** — the complete test suites, back and
front, the complete lint, type checks, build steps, anything the project runs to say that
it is sound. Not a subset chosen for the work at hand: **all of it, every time.**

Two reasons, and they are why nothing in this workflow ever closes on a narrowed
command — an implementer may run anything while it works, a verifier proves one claim
with one test, and neither of those closes a task:

- **A change breaks things far from where it was made.** A function passes its own tests
  and breaks three callers in another module; a file is edited and a lint rule fires in a
  file nobody touched. Any selective command is a bet on where the consequences will land.
- **Selecting is itself a defect class.** A `-k` selector that matches no test exits 5,
  which looks exactly like the expected red phase. An operand list typed by hand goes
  stale the moment a task's write set changes. *Run everything* deletes the category.

**You never run the gate yourself, here or anywhere.** C0 is the only place you have
it run at all. After this, the implementer runs it inside its own session — and the gate
is what **closes** a task, never a leash on how the implementer works while it works.

### C0.1 · The working tree must be empty of everybody else's work

**Before anything else**, and it costs one command:

```sh
git status --porcelain
```

**Anything at all, and you stop and ask.** Not a halt — the human decides what becomes of
their own work: commit it, stash it, or tell you to stop. **You never commit it, never
stash it, and never reset it yourself.**

This is the phase's real precondition, and it is what makes the rest of the mode sound.
**From here on, everything in the working tree belongs to this run** — which is the only
reason `git add -A` is allowed to preserve a failed or paused attempt wholesale. Start on
somebody else's uncommitted change and that same command sweeps it into a commit it never
belonged to, and the reset that follows takes it out of the tree.

The other end of it is just as bad: a change that is never committed makes every task's
clean-tree check refuse, and the first one would never be recorded.

### C0.2 · Read the gate file

First classify the exact leaf, before reading it:

```sh
GATE=<repo>/.superpowers/bwr/gate.md
if [ -L "$GATE" ] || { [ -e "$GATE" ] && [ ! -f "$GATE" ]; }; then
    # STOP — foreign state; follow and change nothing
fi
```

`gate.md` is valid only as one real regular file at that exact checkout-local path, or
as a proven-absent path: both `-e` and `-L` are false. A symlink, including a dangling
one, directory, device or other occupant is foreign state. Stop and ask the human to
classify it. Do not read, replace, remove or write through it.

If the real file exists, read it. If the path is proven absent, this is a first
discovery — C0.4 and C0.5 apply.

### C0.2a · Validate gate execution

`gate.md` owns the exact command list. The optional controller-owned
`<workspace>/gate-execution.json` owns only how that list can execute. It has this exact
shape:

```json
{
  "schema": 1,
  "gate": "<current gate.md Git blob>",
  "max_parallel": 2,
  "compatibility_evidence": [
    {"path": "<repository-relative definition or resource path>", "identity": "<SHA-256>"}
  ],
  "compatible_groups": [
    ["<command 1>", "<command 2>"],
    ["<command 3>"]
  ]
}
```

The groups form one exact ordered partition of every executable gate line. A group means
that every command in it is mutually compatible. Groups execute in order. The maximum
limits one active wave inside a group. Full-line comments remain in `gate.md`, but do not
enter this partition.

Validate the effective schedule at any entry through:

```sh
python3 <workspace>/prompts/construction/gate_execution.py show
```

It refuses a malformed, foreign-generation or incomplete config. With a proven-absent
config, it prints the derived sequential schedule.

After the human has validated the exact gate commands, propose a schedule. **Do not infer
compatibility from different command names.** Put a command in a shared group only when
project evidence establishes that concurrent runs cannot collide through repository
files, generated outputs, caches, databases, ports, services, processes, CPU or memory.
Account for internal parallelism in pytest, compilers and build tools. Uncertainty means
one singleton group.

Present the exact proposed groups and their evidence. Then ask one question:

> **Maximum parallel gate commands?**

Offer `2 (recommended)`, `1`, `3`, and `4`. A free-form answer may supply another positive
integer. The human validates both the grouping and the maximum. A missing answer or a
proven-absent config means strict sequential execution: maximum 1 and one singleton group
per command.

For every shared group, name the complete sorted set of project-local definitions,
targets and resource declarations that establish compatibility. A directory path covers
its complete tracked subtree. Use `.` when the whole candidate tree is the smallest proof
you can defend. If the complete compatibility basis cannot be named, use singleton groups.
Generate the exact identities for those approved paths from the current staged tree:

```sh
python3 <workspace>/prompts/construction/gate_execution.py evidence \
  <sorted-repository-relative-path>...
```

Copy that complete JSON list into `compatibility_evidence`. A parallel group requires a
non-empty list. The helper authenticates every identity before it publishes a config and
again before a logical gate can open. A changed definition, target or resource declaration
therefore refuses before any gate command. Return to the human for a replacement schedule,
or remove the stale config and use the sequential default. The later full surface scan
still reports every other gate drift candidate.

Write the complete approved JSON to one real draft file. Publish it only through:

```sh
python3 <workspace>/prompts/construction/gate_execution.py publish \
  <absolute-draft-path>
```

The helper authenticates the current gate blob, exact command partition and compatibility
evidence against the staged tree. It then replaces the workspace config atomically. Delete
only the draft you created after publication.
To return future gates to the absence default, use:

```sh
python3 <workspace>/prompts/construction/gate_execution.py remove
```

Both mutations refuse while `gate-check-in-progress` exists. A gate change makes the old
config stale. Reconcile the list with the human, then validate and publish a complete new
schedule. Do not patch the old schedule.

The setting belongs to this workspace, not to every machine. After a known machine or
resource change, ask the human to revalidate the maximum before the next gate. Until that
answer is published, remove the old config and use the sequential default.

An existing run whose C0 already finished adopts this feature between logical gate
operations. Ask at the next controller checkpoint. Do not restart C0, rewrite the journal,
or alter a live marker. Until one approved config exists, every new gate stays sequential.

### C0.3 · Spawn the gate runner

One subagent, **a light model, effort medium**, prompt
**`<workspace>/prompts/construction/gate-runner.md`**. Its message carries:

```text
RUNTIME INPUTS
repository: <absolute repository root>
workspace: <absolute workspace path>
role prompt: <workspace>/prompts/construction/gate-runner.md
global prompt: <workspace>/additional-prompts/global.md
additional prompt: <workspace>/additional-prompts/construction/gate-runner.md
```

Tell it to read the global additional prompt through this command: `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`. Tell it to treat its stdout as human
instructions. Then tell it to read the role-specific additional prompt through this
command: `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/construction/gate-runner.md
<workspace>/additional-prompts/construction/gate-runner.md` after its official prompt.
Tell it to treat its stdout as human instructions and follow both instruction sets during
the assignment. The later role-specific instruction wins on contradiction.

On first discovery, add `report: none`. That means no gate-specific input and no file or
directory write. It does not mean the runtime-input block is absent.

Bracket that first, non-authoritative discovery call only:

```sh
progress.py subagent-started gate-runner --data '{"scope":"discovery"}'
progress.py subagent-ended gate-runner \
  --data '{"scope":"discovery","green":<true|false>,"surface":"different"}'
```

This result proposes a list. It is not a gate proof and no consumer accepts it as one.

When the real gate exists, first open one logical controller baseline check:

```sh
bash <workspace>/prompts/construction/gate-check.sh open baseline \
  c0/<current-HEAD> - 0 0 HEAD
```

Give the runner the real gate path and the operation, gate blob, candidate tree and
predecessor, and gate-execution identity printed by that call. Also give these two exact
values:

```text
report: <workspace>/reports/gate/<op>.json
verify: bash <workspace>/prompts/construction/gate-check.sh verify <op>
```

Never copy a command list into its message. The runner reads the exact physical gate. It
uses the verify command around the shared executor and runs the frozen schedule only
through `gate_execution.py run <op>`.

The shared executor atomically publishes the complete per-command account directory. Its
small canonical manifest binds one separate raw output per command through exact size,
whole hash and fixed-size chunk hashes. Bounded metadata reads touch no raw output. A
bounded output read touches only its requested command chunks. The runner writes the whole
canonical result to `<workspace>/reports/gate/<op>.json`. That report binds the account,
contains every exact gate command in order, one result per command, the completed
cleanliness comparison and the completed gate-surface scan. Its final message is only a
readable view of the same result. It fixes nothing.

`gate-check.sh open` writes the structured start. Close the exact returned result with:

```sh
bash <workspace>/prompts/construction/gate-check.sh close \
  <op>
```

The close audits the real op-scoped report. It derives `green` and the surface state
from that report. No controller-supplied verdict can close the operation.

If the executor reports that one active group changed repository state, it has already
waited for that whole group and has published no command account or report. Record the
exact changed paths, run `gate-check.sh abandon <op>`, and route the dirty baseline through
C0.6. Never let another operation adopt those bytes.

One file, `<workspace>/gate-check-in-progress`, owns an unfinished logical check. It
freezes the operation, owner, `HEAD`, predecessor, index tree, real gate blob, exact gate
execution schedule and, for a task, the latest final code-review proof. That proof is one
clean checker verdict or one complete round-10 resolution without an accepted defect.
Resume it as follows:

- marker and no terminal result: if the whole canonical report exists, rerun `close`
  without regenerating the physical runner. Otherwise rerun the exact `open` call. It
  returns the same op only when every frozen value still matches. The regenerated runner
  reuses a complete durable command account, or reruns the same frozen schedule if no
  complete account landed. Its executor call first joins the op's ownership lock. If the
  prior executor died, every orphaned active command retains that lock until it exits, so
  the replacement cannot overlap it;
- terminal result and marker: rerun `close` with that op. It removes only the orphan tail;
- terminal result and no marker: consume it. Never run the gate again for lost output;
- changed candidate or gate: stop the physical runner. Use `gate-check.sh abandon <op>`,
  return to the owning code-checker or controller state, and open a new logical check.

Every other mutator refuses the live marker. A pause or abort first stops the physical
runner and settles or abandons this check. No commit, plan publication, ref or stopping
point may absorb its frozen candidate.

`gate-check.sh abandon <op>` also refuses while that executor lock is held. Never abandon
one op and open another while an old active wave can still run.

### C0.4 · Report — first discovery only

Report to the human: what ran, what came back. **The same report whether everything
passed or not.** Then ask what is missing — a command they run that the runner could
not find anywhere.

Their additions join the list — **unproved yet**: the runner's verdict covers what it
ran, and nothing else.

### C0.5 · Write the gate file — first discovery only

Publish the complete validated list with one call:

```sh
<workspace>/prompts/construction/gate-write.sh create -- \
    "# <optional human-validated rationale>" \
    "<first complete command>" "<second complete command>" ...
```

Immediately before this first write, repeat C0.2's leaf check. Write only while the path
is still proven absent: both `-e` and `-L` are false. Any occupant is a refusal, never a
target to replace. The script repeats the physical ground and leaf checks, writes the
whole argument list to one real same-directory temporary, verifies it, and atomically
renames it. An interruption leaves `gate.md` absent, never a partial authority. A
same-name occupant that appears before publication is not replaced.

**Not before.** The runner proposes; the human validates; you publish. A file written
earlier would be read as approved on the next entry.

**Then run C0.3 again — a fresh logical check on the real file as written.** A
human-supplied command can be RED on this same untouched baseline, and
the earlier green proves only the shorter list. The gate that closes tasks is the file
as it stands, so the verdict C0.6 routes on must be that list's own — or the first
implementer inherits a baseline nobody measured, and is blamed for a failure that
predates its task.

Complete C0.2a after the list is written and before this fresh logical check. The fresh
check then freezes the approved schedule, or the safe sequential default if no config
exists.

### C0.6 · The verdict

**The verdict is the last runner's, on the list `gate.md` now holds** — an addition
that never ran has no verdict.

- **All green** → C1.
- **Anything red** → **stop, and tell the human the baseline is not clean.**

After the final runner returns and before C1, repeat `git status --porcelain`. The first
check was empty, so any path now present is a gate side effect. Report the exact
difference and stop. Never clean, ignore, commit or attribute it automatically. A green
command result does not certify a dirty baseline.

C0.6 is a halt, not a question. Nothing built on a dirty baseline can be shown to be
clean afterwards, so there is no point starting.

### On later entries

The gate file exists. Run C0.1, C0.2, C0.3, C0.6, and continue. **Do not interrupt to
re-confirm a list the human already validated.**

**C0.1 runs every time, and it matters most on a later entry:** the previous lot ended
clean, so anything in the tree now arrived from outside the run.

Interrupt only on a real blocker: the tree is not yours, the baseline is dirty, or a
command no longer runs.

If the runner reports a changed gate surface, report it **after the command results**.
The old list's green result remains true, but no attempt launches until the human settles
the additions, removals and renames. The runner provides evidence; the human validates
the next complete list; only you publish it. Never classify a missing or renamed command
as an ordinary gate failure before this decision.

For growth or reconciliation, bind the replacement to the exact file the human saw:

```sh
CURRENT=$(git hash-object <repo>/.superpowers/bwr/gate.md)
<workspace>/prompts/construction/gate-write.sh replace "$CURRENT" -- \
    "# <optional human-validated rationale>" \
    "<first complete command>" "<second complete command>" ...
```

The helper refuses a changed hash, alias or foreign leaf before publication. It prepares
the whole list beside `gate.md` and atomically replaces the old real file. An interruption
therefore leaves either the old complete list or the new complete list, never a prefix.

**And a command that joins the file joins it measured**: run C0.3 again, a fresh
runner on the enlarged list, before the next attempt launches. The entry verdict
covered the old list, and an addition can be RED on a baseline nobody touched — that
RED is C0.6's halt, the human's to settle, never the next attempt's failure. Nothing
launches on a gate whose baseline was never measured.

Revalidate C0.2a for the complete replacement list before this fresh runner. The old
schedule belongs to the old gate blob and cannot authorize the new list.

---

## C1 — The plan

You write the plan yourself, in **`<workspace>/plans/<lot>-plan.md`**. That is where it
lives; `docs/plans/` only ever receives a copy.

It is thin on purpose: you are writing blind, before any of this lot's code exists.
**You cannot quote code that does not exist, and a signature invented before its
consumer is a guess.** The detail arrives in C3, against the real tree, where it is
true.

### C1.1 · The responsibility map

1. **Read the whole spec**, not only your lot's section. The Global Constraints apply
   everywhere, and a neighbouring lot's decision often says where something must live.
2. **List what this lot owes**, one by one, literally. That is your only source, and
   anything from elsewhere is scope creep that C2.2 will send back.
   - **a normal lot**: the spec decisions the breakdown assigns to it;
   - **a sub-lot**: the confirmed findings **of the pass that opened it** —
     `<workspace>/reports/product-review/<root lot>/<the lot that pass reviewed>-confirmed.md`,
     which is the file you wrote when you opened this sub-lot. **Never the sub-lot's own
     name:** `lot-1.1-confirmed.md` is what the pass over `lot-1.1` will write, later, if
     anything survives it. Read them, and the parent lot's `Covers:` line too — **and
     every earlier sub-lot's `Covers:` line, with the confirmed file each one names**:
     their corrections are delivered exactly as the root's decisions are, and a new
     correction must not undo any of it.
3. **For each decision, name the responsibility it imposes.** Not the code — the
   responsibility. *"something must carry the lifecycle transitions under a lock"*, not
   *"a `revoke_peer` function"*.
4. **For each responsibility, find where similar things live today.** Search the repo.
   A responsibility that resembles something existing goes to the same place. Name the
   file.
5. **What finds no existing home is new.** Decide where, following the repo's
   patterns — not the ones you would prefer. Mark it `NEW`.
6. **Reread the map.** Two unrelated responsibilities in one file means one of them is
   misplaced. One responsibility spread over four files means it is not one
   responsibility.
7. **Write it into the plan**: the list from step 2 as the header's **`Covers:`** line,
   and the map as the `## Responsibility map` section — one line per file, the file and
   what it is responsible for.

**`Covers:` is what every reviewer will be handed as the reference for this lot.** On a
sub-lot it lists the findings instead, and **carries the path of the file holding them** —
the one from step 2. That line is the only place that path is written down, and every
later reader takes it from there rather than building it from a name.

**You are not predicting which files the lot will touch.** Steps 4 and 5 are a reading
and a decision, never a guess. What the map misses is discovered at C3.1, task by
task, and that is expected.

### C1.2 · Split into tasks and fix the order

**What a task is.** A unit of work that means something on its own, and on which the
following ones can be built. **Not a feature** — a lot's feature only exists once
every task is done.

**What "stands alone" means, and what it does not mean.** A task ends in a coherent
state: the gate is green, and what it produced is usable as it stands. It never leaves
failing tests for the next task to satisfy. **It does not mean its code is frozen.** A
later task may freely modify what an earlier one wrote — task 1 writes a function that
must notify someone, the notification system only arrives at task 6, and task 6 changes
task 1's function. That is normal, and no rule forbids it.

Then:

1. **Group the responsibilities that must exist together to mean something.** Each
   group is a candidate task.
2. **Judge each candidate against the standing-alone test above.** You are not running
   anything — you are asking whether, once this task is written, the suite could pass
   and the result would hold up. **A candidate that fails this is not a task**: merge
   it with what it depends on, or cut elsewhere.
3. **Order them: what is used comes before what uses it.**
4. **Move the least certain interfaces early.** A hypothesis tested at task 2 costs two
   tasks to unwind; the same one at task 8 costs eight.
5. **Check the size, both ways.**
   - **Too large:** two parts of it could be judged, accepted or rejected
     independently. Split.
   - **Too small:** what it delivers means nothing on its own. The sign is that you
     cannot say what it achieves without naming the next task. Merge.
   - Fold setup, configuration, scaffolding and documentation into the task whose
     deliverable needs them.
6. **Name the dependencies.** For each task, which earlier task it needs, and why in
   one clause.

**Step 2 is the strongest constraint on the split.** If a lot cannot be cut so that
every task stands alone, the cut is wrong — go back to step 1, not forward.

### C1.3 · Write each task

Five blocks, in `<workspace>/prompts/construction/plan-format.md`'s shape.

- **`Descends from`** — what this task answers to. **On a normal lot, a spec decision;
  on a sub-lot, a finding by identifier — `F3`.** Every task has one, and it is what
  C2.2 checks. If you cannot name it, the task should not exist.
- **`Depends on`** — `task N — why`, or `-`. **An edge between tasks, not an interface
  contract.** It fixes the order and C2.3 closes on it. Nothing else ever reads it, so
  it does not need to describe anything.
- **`Achieves`** — three to six bullets. **What the task accomplishes, never the order
  it works in.** They exist so anyone can tell whether this is one task or three. The
  implementer decides its own sequence later, with the tree in front of it.
- **`Files`** — the files from your map that this task touches. Approximate, and known
  to be.
- **`To verify`** — what this task must be shown to do. **C3.2 checks that every line
  here is covered by a behaviour the implementer declared**, so a line you leave out is
  a thing nobody will ever prove.

### C1.4 · What the plan must never contain

**No function bodies. No commands. No signatures. No line numbers.**

Illustrative code is allowed and is never prescriptive — say so where you use it.

Two reasons, and they hold for every line you are tempted to add:

- **Detailed code written here is a guess**, and it turns into an order for an
  implementer whose prompt says the plan was validated.
- **Commands in a plan go stale** the moment a task's write set changes, and there is
  only one command list in this workflow: the gate.

### Then copy it, commit it, and post the lot's starting point

```sh
<workspace>/prompts/construction/plan-commit.sh <lot> "<subject>"
```

It counts the plan's tasks itself and writes the journal line with that count. **The
subject is yours, in the project's own conventions** — this commit lands in the
repository's history, and the Git section's rule applies to it.

*It runs the equivalent of:*

```sh
document-copy.sh source plans/<lot>-plan.md
document-copy.sh copy plans/<lot>-plan.md docs/plans/<workspace name>-<lot>-plan.md replace
git add -- docs/plans/<workspace name>-<lot>-plan.md
git -c core.hooksPath=/dev/null commit -m "<subject>" -- docs/plans/<workspace name>-<lot>-plan.md
document-copy.sh finish plans/<lot>-plan.md docs/plans/<workspace name>-<lot>-plan.md replace
git update-ref refs/bwr/<run>/<lot>/task-0 HEAD    # only if it does not exist yet

progress.py note plan.written --data '{"tasks":<N>,"op":"<the operation's mark>"}'
```

**The helper sequence is the physical copy boundary, not optional shorthand.** The
shared helper proves the exact real workspace source, exact Git toplevel, every real
repository parent and the destination leaf before it reads or writes. It refuses every
symlink and other occupant read-only. The copy goes to a real same-directory temporary,
is compared with the source, and atomically renames over an absent or real regular target.
An existing target must be tracked by Git or owned by this exact copy's durable workspace
marker. The marker lands before the copy and remains through the commit boundary;
`finish` removes it only after that boundary, closing the rename-to-stage crash window.
Every pending retry repeats the same checks.

**The commit names its path twice on purpose.** `git add X && git commit -m …` commits
the whole index, so anything somebody else had staged would land in a commit that claims
to carry the plan.

The script disables project hooks for this controller-owned document commit. It compares
the committed plan path with its exact prepared marker tree before `task-0` or
`plan.written`. A successful hook cannot replace accepted plan bytes.

**`task-0` is the lot's starting point.** Without it, the first implementer has no
previous ref and `reset to task-<K−1>` has no meaning for `K=1`. Every lot posts its
own, sub-lots included.

**It is posted once and never moves.** This script runs again whenever a plan is
rewritten mid-lot — a re-cut decomposition, a completeness pass sent back here — and by
then `HEAD` sits on top of the tasks already built. A `task-0` moved there would be a
starting point that comes **after** part of the lot: the product review takes it as its
base and loses everything built before, and a past-task diff runs backwards. The script
leaves it alone and says so.

This is your last **plan** commit before the implementers begin: from C3 on, **each
task's section is copied and committed by its own implementer**, with that task's
code. Your document commits are another matter and stay yours — a DECISION's in-place
spec commit, an amendment landing mid-lot, a rewind's re-land — each owned by the
route that prescribes it, never delegated to an implementer.

**`docs/plans/` is an output, never a source.** Two consequences to expect rather than
fix: a task that fails never copied, so that file is simply one design behind and the
workspace is right; and a human editing `docs/plans/` mid-run will see it overwritten at
the next copy — say so in the end-of-lot report. The history still works, since the copy
is committed at every task: `<workspace>/prompts/construction/task-show.sh <lot> 3 <plan>`
says what the plan said at that moment.

---

## C2 — Completeness

One subagent, **a strong model, effort medium**, prompt
**`<workspace>/prompts/construction/completeness.md`**. Give it that path, the
**workspace path**, its one optional additional prompt
`<workspace>/additional-prompts/construction/completeness.md`, **the path to the spec**
and **the path to the plan**.
Also give it `<workspace>/additional-prompts/global.md`. Tell it to read the global
additional prompt through this command: `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`. Tell it to treat its stdout as human
instructions. Then tell it to read the role-specific additional prompt through this
command: `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/construction/completeness.md
<workspace>/additional-prompts/construction/completeness.md` after its official prompt.
Tell it to treat its stdout as human instructions and follow both instruction sets during
the assignment. The later role-specific instruction wins on contradiction.

**On a sub-lot**, add the path to the parent lot's plan **and to every earlier
sub-lot's** — counter 5 reads all their `Covers:` lines, the root's spec decisions and
each earlier correction's findings alike, to check that no task undoes anything the
subject already delivered. An artifact the checker never receives is a check it cannot
make.

```
progress.py subagent-started completeness
progress.py subagent-ended completeness --data '{"decisions":"<N/N>","tasks":"<N/N>","deps":"<N/N>","constraints":"<ok, or N broken>","parent":"<ok, or N broken - on a sub-lot; n/a on a normal lot>"}'
```

**The counts are the checker's real ones, every marker filled.** A sample copied
verbatim is a journal that says the plan is incomplete — or complete — regardless of the
plan, and the journal is what a takeover reads.

It counts. It does not judge signatures — **nobody proves a signature before the code
exists**, and C3 surfaces any disagreement where it is real.

- **C2.1** — every decision this lot owes — **the plan's `Covers:` set, never the
  whole spec** — lands in at least one task. **N of N.** A later lot's decision
  absent here is the breakdown working, not a gap. **And the set itself is checked
  against its source first**: `Covers:` is your copy of what the breakdown assigns,
  and a decision assigned to this lot that the line omits is a finding — counted
  without it, every N of N closes over the wrong list.
- **C2.2** — every task traces back to a decision **of that same set**. **N of N.**
  No scope creep — a task citing a real decision the breakdown assigns to another
  lot is creep wearing a citation.
- **C2.3** — every `Depends on` points at a strictly lower task number, and the reason
  it states holds.
- **C2.4** — no task contradicts the Global Constraints — **the plan's copy compared
  with the spec's section first**: a constraint omitted or weakened in the copy is a
  finding, never a shorter list — the copy is what every implementer works from, and
  nothing downstream compares the two again.

**For a sub-lot the reference set changes:** every finding lands in a task, every task
traces back to a finding, and nothing breaks the parent lot's spec coverage — **and the
confirmed file the `Covers:` names is authenticated first**, as the opening pass's own:
one pass follows each lot built, so the expected name is mechanical, and an existing
file from another pass would have every counter close over the wrong findings.

### What comes back

- **C2.5** — a gap you can fix in the plan: amend it, then **run C2 again** — and
  journal the spend as you relaunch: `progress.py note bound.spent --text "C2 pass <n>"`.
  A fix changes the counts, so the previous pass no longer proves anything — and after
  a compaction, that note is the only thing that says which pass the next one is.
  **Count only the lines since the latest `plan.written` or `amendment.committed`,
  whichever is later**: each of those opens a fresh C2 phase — a re-cut, the mandatory
  post-amendment rerun — and an earlier phase's passes are not this one's. A normal
  second pass after an amendment is not the forbidden fourth of a phase that ended.
- **C2.6** — **the split itself is wrong**: a task tracing back to nothing, a
  dependency no ordering can satisfy, a decision that cannot land anywhere. Go back to
  **C1**. Do not patch a broken cut in place.
- **C2.7** — every counter full — the four, **and the fifth on a sub-lot**. The final
  C1/C2 plan commit changed the baseline after C0. Open and close one C0.3-style
  `baseline` gate for this exact clean `HEAD`, with owner `plan/<lot>/<HEAD>` and the
  plan commit's parent as predecessor. Only a green, clean, unchanged result goes to C3.

This phase terminates: the counters reach a ceiling. If you find yourself on a fourth
pass, you are not filling gaps any more, you are redesigning — that is C2.6.

---

## C3 — Task by task

**Every task is built by one implementer session that you launch**, and which does
everything from designing the task to committing it. You launch it, you read what it
reports, and you decide what happens next. You never write code and you never run the
gate.

**Strictly sequential.** Never two implementers at once, however independent two tasks
look: they commit on the same branch, so they commit over each other, reset each
other, and fight over the git refs.

**One attempt is one session.** A failed attempt is never resumed — its replacement is
a fresh session that reads the plan and the failure report, never the failed code.

### What the implementer does inside its session

You do not drive these steps. You need to know them to judge what comes back. Its full
instructions are in `<workspace>/prompts/construction/implementer.md`; **you never repeat them in the message you send
it.**

1. **C3.1 — Design.** It reads the real tree and writes a `### Design` block into its
   task's section of the plan: steps, exposed signatures, chosen and discarded
   alternatives, behaviours it will test. Not one line of code.
2. **C3.2 — Design checker.** A subagent it spawns judges that design alone. A finding
   sends it back to C3.1. **Three logical rounds at most; regenerating an unconsumed
   result keeps its round.**
3. **C3.3 — Implement.** Step by step. It never invents behaviour the plan does not
   state.
4. **C3.4 — Free work and the ordinary gate.** It runs any commands it needs. When it
   judges the candidate ready, it stages the exact candidate and runs the complete
   unchanged whole-repo gate through one durable `review` gate operation. **A red
   ordinary gate returns to free work.** A green gate freezes the candidate for one
   checker round.
5. **C3.5 — Self review, once.** It rereads its whole diff. A fix returns to free work,
   then the complete ordinary gate when the candidate is ready.
6. **C3.6 — Code checker.** A subagent judges the whole diff and returns every
   independent finding in one strict result artifact. Its finite manifest binds the
   controller-owned task contract, accepted Design, gated candidate and every changed
   file. The checker accounts for every manifest member and preserves concrete checked
   evidence even when clean. Newly discovered candidates use the impact/probability
   table in `prompts/common/review-risk.md`. Filtered observations remain only in the
   attempt-scoped best-effort history
   `reports/construction/<lot>/task-<N>-attempt-<K>-code-risk-filtered.md`; all rounds and
   regenerations share it, while a new attempt gets a new path. Admitted findings publish
   impact but never probability. The audited result derives public `critical`,
   `important`, and `minor` counts for the journal. Prior admitted identities bypass
   fresh admission. A result-shape refusal returns to the same checker and the
   **same open physical call** for one **complete replacement JSON**. Make **at most two
   repair requests**; stop early when the **same exact refusal** repeats. Only then close
   the call unusable and regenerate it under the same manifest and round, with **no
   second `bound.spent`**. The allowance exists only while the **live repair context**
   preserves the checker address, request count and last refusal. **After compaction**,
   takeover or loss of that context, send no guessed repair: write
   `{"unusable":"lost"}` to **close the exact open call before regeneration**. **Ten
   logical rounds at most; regenerating an unconsumed result keeps its round.** Rounds 1
   through 9 record one complete
   correction account, then return through the ordinary gate before a fresh checker.
   The next manifest carries every prior finding for exact verification. At round 10,
   the implementer alone owns `Blocked` and `DECISION` classification, then accounts for
   every finding as `accepted`, `refuted` or `alternative`. `Blocked` and `DECISION`
   still stop before settlement. An accepted defect fails through C3.9. A complete
   account without one can reach the final gate and carries every `alternative` in
   `### Disagreement`. It never allocates round 11.
7. **C3.7 — Final gate surface and commit.** After publishing its plan copy and staging
   the exact candidate, a fresh logical gate runner reads the real stored list. It scans
   additions, removals, renames, changed command definitions and uncovered new targets.
   It atomically publishes one op-scoped physical report with every executable gate
   command and result,
   the completed cleanliness comparison and the completed surface scan. The close derives
   its verdict from that audited report. Only `green` plus `Gate surface: unchanged`
   permits the one task commit.

### Launching an attempt

**Attempt numbers only ever go up.** A task's first attempt is 1; every later one is
one more than the highest number the task has seen, **whatever ended the previous
one** — a failure, a pause, a stop, a silent replacement, **or a success whose task
was later rewound**. A number is never reused: the try ref and the failure report
carry a preserved attempt's number, **and every closer journals a line carrying the
lot, the task and the attempt** — `attempt.succeeded`, `attempt.failed`, `paused`,
`aborted` — which is the only trace left by a rewound success, an untouched stop, or
a reportless failure. The start script refuses a number that left any of those traces.

**Mark where the attempt begins first, before the session that will run it exists:**

```sh
<workspace>/prompts/construction/attempt-started.sh <lot> <N> <K> [accepted-defect failure report]
```

*It runs the equivalent of:*

```sh
git status --porcelain                                  # must be empty
# validate the current plan's exact Task 1..T heading sequence
# require its hash and count to equal the current committed plan copy
# require N in 1..T; task-0 and every task before N present; N and every
# later stable task absent; task-(N-1), or task-0 for N=1, an ancestor of HEAD
git update-ref refs/bwr/<run>/<lot>/attempt-base HEAD   # the mark FIRST
{
    printf '%s %s %s\n' <lot> <N> <K>
    printf 'plan %s %s ownership %s contract %s retry %s\n' \
      <heading-manifest-hash> <T> <whole-plan-ownership-sha256> \
      <controller-contract-sha256> <accepted-failure-proof-or-dash>
} > <workspace>/attempt-in-flight.tmp
mv <workspace>/attempt-in-flight.tmp <workspace>/attempt-in-flight
                                   # the identity SECOND — written, it proves the
                                   # start completed against this exact plan-task
                                   # manifest; both lines publish atomically. A cut
                                   # before them leaves only a re-posted mark, and
                                   # the same call retries safely. Every closing
                                   # script checks the first line; plan publication
                                   # and task acceptance also consume line 2. The
                                   # closer removes the file.
```

**It is the only thing that can later say whether this implementer committed anything**,
and its whole value is that it was taken **before** the implementer could touch anything.
`create_session` returns when the prompt has been handed over, **not** when the session has
finished with it: mark afterwards and a quick implementer can already have committed, in
which case the mark lands on the task's own commit and the success check rejects a task
that was built correctly.

It also refuses to start on a tree that is not clean — whatever is there was left by
something else, and the implementer would read it as the codebase. **Refusing here costs
nothing**, since no session exists yet to stop.

**It also proves that this is the next task in the current committed plan before it moves
the mark.** The workspace plan must contain the exact `Task 1..T` heading sequence in the
current committed repository copy; N must be in that range; `task-0` and every earlier
task ref must exist; N and every later stable task ref must not; and the immediate
predecessor must be an ancestor of `HEAD`. Controller document commits may validly sit
above that predecessor. A rewind moves every task that will be rebuilt out of the stable
namespace, so a valid rebuild has the same shape. The atomic identity also stores the
heading-manifest hash, task count and complete plan ownership projection. That projection
removes only this task's `### Design` and authenticated `### Disagreement`. The start,
`plan-publish.sh` and `attempt-succeeded.sh` compare every other byte with the durable
committed plan. A failed or stopped attempt can leave its Design in the workspace plan,
but no controller-owned field or another task can become fresh authority. A legitimate
controller re-cut commits that copy first and therefore establishes the new manifest.
A typo, removed task, gap, reopened task, or branch that dropped its predecessor is
refused before any session or mutable start state exists.

**Then create the session.** `mcp__twicc__create_session`, one call carrying everything:

- preset **`Implementer`**, the provider the human chose, **question widget disabled**
- project: the repository's exact TwiCC project, passed explicitly
- title `- Task <N> attempt <K> (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=implementer` · `bwr.mode=construction` ·
  `bwr.feature=<feature>` · `bwr.lot=<lot>` · `bwr.task=<N>` · `bwr.attempt=<K>` ·
  `bwr.status=working`

The message starts with this fixed block, with absolute paths:

```text
RUNTIME INPUTS
repository: <absolute repository root>
workspace: <absolute workspace path>
role prompt: <workspace>/prompts/construction/implementer.md
global prompt: <workspace>/additional-prompts/global.md
additional prompt: <workspace>/additional-prompts/construction/implementer.md
```

Tell it to read the global additional prompt through this command: `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`. Tell it to treat its stdout as human
instructions. Then tell it to read the role-specific additional prompt through this
command: `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/construction/implementer.md
<workspace>/additional-prompts/construction/implementer.md` after its official prompts.
Tell it to treat its stdout as human instructions and follow both instruction sets during
the assignment. The later role-specific instruction wins on contradiction.

Tell it to stop before reading or writing any project or workspace path when one value
is absent, relative, unresolved or contradictory. The current working directory is never
the workspace. After that block, the message gives these role inputs, and nothing more:

1. **the lot** and **the task number**
2. the attempt number
3. on a retry: **which of C3.9a–d it was classified as**, and **the path to the failure
   report — the path the failed attempt reported, passed on as it is** — **when there is
   one.** The file carries its *writer's* task and attempt, so a path rebuilt from this
   launch's own numbers names a file that does not exist: an ordinary retry reads its
   predecessor's attempt, and on a `C3.9c` another task's report altogether. A retry without a report follows an attempt that never delivered one —
   stopped at C3.10 over a plan fault, interrupted by a pause, gone silent and
   replaced, ended by an amendment, or failed without landing a usable report, its
   one repair spent. **The message then states two facts, plainly
   and separately**: why the previous attempt ended, and **whether the plan has
   changed since** — corrected, realigned to an amended spec, or untouched. The list
   of cases is not the contract; the two facts are, and every combination of them is
   legitimate.

   When the previous failure carries an accepted round-10 defect, the report path is
   mandatory in `attempt-started.sh` as well as the message. The start freezes its exact
   journal and artifact proof. The first code-checker manifest gives every accepted
   identity to the checker as required retry input. A missing or different path refuses
   before the attempt mark moves.

**It builds its own paths from the lot.** The plan is at `<workspace>/plans/<lot>-plan.md`,
the repository copy is `plan-publish.sh`'s business, and a past task is read with
`task-diff.sh` — none of that has to travel in a message any more.

```
progress.py session-started <id>
```

**A `create_session` whose result was lost resolves by `SKILL.md`'s query rule** —
the exact annotations, and route on the count. What is specific here: the mark and
the identity file are already written, and `attempt-started.sh` refuses a re-run for
exactly that reason — **when the query proves no implementer exists, create the
session against the mark as it stands.** The start is done; only the child is missing.

**On a retry it never receives the previous attempt's code.** It reads the plan —
including the design that attempt wrote — and the failure report. It has nothing to
defend, which is what makes a fresh attempt rewrite freely instead of patching around
someone else's work.

### What comes back

**Gate execution drift.** An ordinary or final gate opening refused before running any
command because one or more approved compatibility-evidence paths changed. Keep the
attempt and implementer live. Report the exact paths and current schedule to the human.
Revalidate the complete groups and maximum against the changed definitions and resources.
Publish the approved replacement config, or remove the stale config and select the
sequential default. Before you release the implementer, verify `gate_execution.py show`
accepts that settled choice against the current staged candidate. Then tell the same
implementer to open a fresh logical gate. Do not classify this pre-execution refusal as a
RED command, Gate drift report, attempt failure or code defect.

**Gate drift.** The final task-boundary runner found one or more documented additions,
removals or renames. This is not `Failed`, `Blocked`, or a C3.9 classification. Keep the
attempt and its implementer live. Report the runner's exact old/new commands and sources
to the human. The implementer never edits `gate.md`.

The human validates the complete resulting list. Publish it through C0.5's
`gate-write.sh replace` call. That publication makes the old execution config stale.
**Before you release the implementer**, repeat C0.2a for the replacement list. Either
publish the complete human-approved replacement schedule and compatibility evidence, or
remove the stale config through `gate_execution.py remove` and explicitly select the
sequential default. Only then message this same implementer to reread `gate.md` and rerun
the fresh final gate runner. No next task starts. If the reconciled list is green, clean
and unchanged, the same attempt commits and reports `Done`. If it is red without further
surface drift, use the final-gate failure route. A newly retired or renamed command reaches
this decision before any failure classification.

**Done.** **A `Done` without a commit hash and final gate operation is not a `Done`**.
Ask for both before anything else.

First confirm that the implementer's latest final gate-runner report for this attempt is
green, says `Gate surface: unchanged`, and reports no repository-status difference. The
canonical `reports/gate/<op>.json` must account for every real gate line in order; the
controller cannot replace it with remembered booleans or a copied list.
**Then record it** — `attempt-succeeded.sh <lot> <N> <that hash> <gate op>`, see
*Recording a success* below. **That call is the check**. It consumes the exact logical
gate after the latest final code-review proof. It refuses a dirty tree, another
commit, another candidate tree, another gate file or a later code-review boundary.

Only then retire the session — `progress.py session-retired <id> done --archive --hide` —
and start task N+1 from **Launching an attempt** above, a new session, attempt 1.

**In that order, never the reverse.** If the call refuses, the session is still alive to
answer for what it reported.

If task N was the last one, go to **C3.11**.

**Blocked.** It stopped rather than invent. Go to **C3.10**.

**Failed.** It wrote its report to
`<workspace>/reports/construction/<lot>-task-<N>-try-<K>.md` and gave you the path. The
report says what failed and **classifies it as C3.9a, b, c or d**.

**Audit the report before you retire its only writer** — the completion-block
discipline, for the one artifact that has no block: the file exists, at the attempt's
own path, and carries its three parts — what failed, exactly one classification with
its subject, what was read to conclude it. Absent, mistyped or short of that, **send
it back once, journaled** — `progress.py note bound.spent --task <N> --text "failure
report returned - attempt <K>"` — the session is still alive, and it is the only
writer the only durable account of this failure will ever have. Still unusable after
its one return: proceed only when no accepted round-10 correction obligation exists —
the classification travels in the message and `attempt-failed.sh` journals it durably —
and the next attempt launches as a reportless retry, the two facts saying the report
never landed. An accepted round-10 obligation stays with this writer until the exact
machine-generated handoff is present; the generic reportless route cannot consume it.

**An accepted round-10 defect is never reportless.** The report must also end with the
exact `construction-failure-handoff` block. `attempt-failed.sh` authenticates the full
immutable checker result, every disposition and the report hash before its first
preserve or reset gesture. The resulting `attempt.failed` binds that artifact. Pass its
exact workspace-relative path as argument four to the next `attempt-started.sh` call.
That obligation propagates through another failed retry and ends only after a successful
attempt whose code checker consumed it.

**You hand that path to the next attempt, which reads the file itself.** That is why it is
a file and not a message: your context is not the only place that failure can live, and a
compaction between two attempts would lose exactly what the next one needs.

**Retire it `failed` only then.** Its work is on a ref and its reasoning is in a file,
audited whole; leaving it alive past that holds a slot for a session that will never
be asked anything again.

```
progress.py session-retired <id> failed --archive --hide
```

Then go to **C3.8**.

**Silent.** The watchdog reports no writes for a long stretch. **Do not kill it on the
first tick** — an agent that announced a step and stopped will usually resume when
asked. Send it one message asking where it stands — and journal the nudge
(`progress.py note bound.spent --task <N> --text "nudged the implementer - attempt <K>"`):
after a compaction, that line is what says the next silence is the second — **and the
attempt is in the line because task N can see several**: a replacement is a fresh
attempt that has never been nudged, so count only the lines naming THIS attempt. Then:

- it answers and moves → let it work;
- it does not answer, or a later tick shows the same standstill → **four gestures, in this
  order**, and the first two are the ones that keep two implementers off one task:

  1. **Stop its process** — `mcp__twicc__processes_stop`. Silent is not stopped, and
     retiring a session does not stop it. A process that wakes after its replacement has
     started is a second implementer on the same task, committing into the same tree.
  2. **Preserve and reset** — `attempt-failed.sh <lot> <N> <K> C3.9b`. It may have written
     code before it went quiet, and the replacement must not find it there.

     **Always `C3.9b`, and never `C3.9a`**, whatever the plan holds. `C3.9a` means *the
     design was sound*, and only its checker can say that. **A `### Design` block that is
     there tells you nothing**: it looks the same half-written, finished but never checked,
     and sent back by a checker whose findings the session went quiet on. You cannot see
     which, so the next attempt designs again — one design cycle against a run that
     implements something no reader ever closed.
  3. **Retire it `failed`**, archive, hide.
  4. **Launch a fresh session** — never a resumed one — with a line saying why.

  ```
  progress.py note session.replaced --text-file "$JOURNAL_TEXT_FILE"
  progress.py session-retired <id> failed --archive --hide
  ```

### C3.8 · When it fails

The implementer keeps its attempt and reports. **You do the git work, with one call**,
carrying the classification the implementer gave you:

```sh
<workspace>/prompts/construction/attempt-failed.sh <lot> <N> <K> <C3.9a|b|c|d>
```

Before this closer runs, settle every current `document-copy-in-progress`,
`spec-commit-in-progress`, `amendment-commit-in-progress` or
`spec-breach-recovery-in-progress` marker through its exact owning call. The failure
closer refuses all four before it binds itself, stages, preserves, resets or journals.
It never removes one.

It prints the ref it preserved, the state the tree is back to, and **the path of the
diagnostic worktree**. It also writes the journal line.

*It runs the equivalent of:*

```sh
BASE=$(git rev-parse refs/bwr/<run>/<lot>/attempt-base)    # the attempt's own ground begins there
# before any gesture, derive the exact ordinary or accepted-defect failure data;
# unresolved round-10 findings or an incomplete accepted-defect report refuse here
FAILURE_DATA=$(progress.py construction-failure-check <lot> <N> <K> <C3.9a|b|c|d>)

# a dirty tree — the common failure: commit everything, then preserve
git add -A && git commit --no-verify -m "<feature> <lot> task <N> attempt <K> — FAILED"
git update-ref refs/bwr/<run>/<lot>/task-<N>-try-<K> HEAD
git reset --hard "$BASE"

# a clean tree with HEAD past the mark — a refused Done, a stopped writer that
# had committed: nothing to commit, the existing HEAD is what is preserved
git update-ref refs/bwr/<run>/<lot>/task-<N>-try-<K> HEAD
git reset --hard "$BASE"

# an untouched tree — a failure at the design stage: nothing to preserve, only
# the reset runs, and there is no worktree to open
git reset --hard "$BASE"

# journaled BEFORE the worktree opens: an add that fails must leave a recorded
# failure and classification, never a silent hole
progress.py note attempt.failed --task <N> --data "$FAILURE_DATA"

# then, on the two preserving branches, the failed attempt opens as a checkout
diagnostic-open.sh <lot> <N> <K>
# after physical containment and exact registration checks, this performs:
git worktree add --detach <tmp> refs/bwr/<run>/<lot>/task-<N>-try-<K>
```

Before the preserve or reset, the script proves that `.superpowers`, `bwr` and `tmp` are
real directories at this checkout's exact physical path. A symlink at any component or
at the deterministic diagnostic leaf refuses without staging, preserving or resetting.
An existing leaf is resumable only when this repository registers that exact path as a
worktree at this attempt's try ref. A foreign directory is never adopted or removed.
If the post-preserve add fails, the printed retry is `diagnostic-open.sh`, not a raw Git
command. It repeats the same physical and registration checks before completing the tail.

The preserving lines put the failed attempt where it can still be read; the reset takes
the branch back to the attempt's own mark; the worktree **opens the failed attempt as a real
checkout**, without touching the working tree. The script prints that path, and
`diagnostic-close.sh` finds it again from the same three values.

**It steps back to the attempt's own start mark, and never to `task-<N-1>`.** Every
controller commit moves the mark with it, so `attempt-base..HEAD` is the implementer's
own ground — empty in the common case, its commits when it was stopped or refused after
committing — and all of it leaves the branch once preserved. Targeting the task ref
instead would also take off whatever the controller has committed since — an amendment
lands there, and would be silently unlanded by the next failure.

**The preserving commit never enters the history.** The reset takes the branch back, and
from then on only the `try-<K>` ref keeps that commit alive.

**A diagnosis gets a worktree, never a diff.** A diff forces its reader to rebuild the
file in their head, and rebuilding code in your head is the one thing this workflow never
relies on. A detached worktree is **not** a branch: nothing is created, nothing is named,
and `git worktree remove` leaves no trace.

**The reset does not touch the plan.** It lives in the workspace, outside git; only the
copy in `docs/plans/` goes back, and it was one design behind anyway. The next attempt
opens the workspace plan and finds the design where it expects it.

**Who reads that worktree.** Normally nobody: the implementer already classified its
own failure, and you route on that. It exists for the case below, and for the human.

**When you do not trust the classification.** Two attempts on the same task failing the
same way trigger one outside diagnosis. Repetition does not prove which classification is
correct: both attempts can implement a sound design incorrectly in the same way. Spawn a
diagnostic subagent, **a strong model, effort high**, prompt
`<workspace>/prompts/construction/diagnostic.md`, and give it: the workspace path, its
one optional additional prompt
`<workspace>/additional-prompts/construction/diagnostic.md`, the path to the detached
worktree **when the failure preserved one** — two design-stage
failures left the tree untouched, and you say so instead: the state those attempts faced
is the repository as it stands — the path to the plan, the task number, and the paths to
both failure reports. It returns one of C3.9a–d, with what it read to conclude. It changes nothing.
Also give it `<workspace>/additional-prompts/global.md`. Tell it to read the global
additional prompt through this command: `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`. Tell it to treat its stdout as human
instructions. Then tell it to read the role-specific additional prompt through this
command: `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/construction/diagnostic.md
<workspace>/additional-prompts/construction/diagnostic.md` after its official prompt.
Tell it to treat its stdout as human instructions and follow both instruction sets during
the assignment. The later role-specific instruction wins on contradiction.

```
progress.py subagent-started diagnostic --task <N>
progress.py note bound.spent --task <N> --text "diagnostic ran - once per task"
progress.py subagent-ended diagnostic --task <N> --data '{"classification":"<C3.9a|b|c|d>"}'
progress.py note verdict.consumed --task <N> --data '{"check":"diagnostic","outcome":"<C3.9a|b|c|d>"}' --text-file "$JOURNAL_TEXT_FILE"
```

An errored, empty or unusable diagnostic closes its physical bracket first:
`progress.py subagent-ended diagnostic --task <N> --data
'{"unusable":"<error|empty|lost|unusable>"}'`. A result lost before its ending bracket
uses `unusable:"lost"`. Only then launch the regenerated physical call. It reuses the
same task-level logical spend.

*The `bound.spent` note allocates the task's one LOGICAL diagnostic. Write
`verdict.consumed` immediately after the return, before routing another attempt, with
the exact analysis preserved through `progress-rules.md`'s `--text-file` transport. A
compacted controller reads the pair: one spend with no consumed verdict
means the result was lost and the same diagnostic must regenerate; the consumed note
means its classification and analysis are durable.*

**A regeneration is not a second diagnosis.** Relaunch the same prompt for the same task
under a fresh `subagent-started` / `subagent-ended` bracket, but write no second
`diagnostic ran` domain spend. Record the regenerated result in `verdict.consumed`, then
route it. Only a consumed diagnostic can launch the post-diagnostic attempt; only that
attempt's identical failure reaches the human. A bare spend never does.

**And it runs once logically per task.** Its consumed verdict routes one more attempt — the outside opinion
was already the second reading of this failure, and no third exists. **If that attempt
fails the same way again, stop launching.** The failed attempt is preserved and reset
like any other; what stops is the relaunch: the failure is not a classification problem,
and neither a fresh attempt nor a fresh diagnosis has anything left to add. Write the
analysis — both earlier reports, the diagnostic's verdict, what the attempt after it
changed and what it did not — and take it to the human. Nothing is launched until they
answer.

```
progress.py note not-converging --task <N> --text-file "$JOURNAL_TEXT_FILE"
```

### C3.9 · Where the next attempt starts

The classification says which part of the work was wrong, so it says how far back to
go. Erasing code is not a punishment: **an attempt built on a wrong design cannot be
patched into a right one**, because it carries decisions taken for the wrong reasons.

| | The classification | Where the next attempt starts | What is erased |
|---|---|---|---|
| **C3.9a** | The design was sound, the code was not | **C3.3** — the `### Design` block stays in the plan and the new attempt implements it again | task N's code |
| **C3.9b** | Task N's design was wrong, including a dependency only that design invented | **C3.1** — the new attempt redesigns the task from the plan's intent | task N's code, and its `### Design` block is rewritten |
| **C3.9c** | Earlier task K's exact accepted obligation was wrong or unmet by K's built result | **C3.1 on task K.** Reset the tree to task K−1 first. | the code of tasks K to N |
| **C3.9d** | The decomposition or an interface is wrong, including a dependency required by task N's accepted contract that no task owns | **C1**, on that area only, then C2, then C3.1 | the code of the affected tasks |

**Only code is erased. The plan is never erased** — it lives in the workspace, and the
next attempt finds it there. That is what lets a fresh session start from something
instead of from nothing.

**Once you have routed, close the diagnostic worktree:**

```sh
<workspace>/prompts/construction/diagnostic-close.sh <lot> <N> <K>
```

It rebuilds the path from the same three values `attempt-failed.sh` used, so you do not
have to have kept it. **Call it every time**: an attempt that left the tree untouched had
nothing to preserve and opened no worktree, and the script says so instead of failing.
Before force removal, it repeats the full physical-ground check and proves the exact leaf
is a worktree registered by this repository. A symlink, escaped component or unregistered
directory is a read-only refusal.

*It runs the equivalent of:*

```sh
git worktree remove --force <tmp>    # never opened — an untouched attempt — is a no-op, not an error
```

The attempt itself stays readable on its `try-<K>` ref. Leave the worktree open and
they pile up, one per failure, until `git worktree list` is unreadable.

For **C3.9c** and **C3.9d**, reset the tree **and take the refs of every task going back
to work out of the way**, before launching anything:

```sh
<workspace>/prompts/construction/rewind.sh <lot> <K> <N> "<subject for the re-land commit>"
```

**The subject is yours, in the project's own conventions** — the re-land commit stays on
the branch, and it is made only when the rewind removed controller commits to re-land.

*It runs the equivalent of:*

```sh
# the whole plan — base, refs to move, commits to re-land — is written to
# <workspace>/rewind-in-progress before anything moves: a rewind that dies
# halfway is finished by the same call, never recomputed from a branch that
# no longer exists
git reset --hard refs/bwr/<run>/<lot>/task-<K-1>
# for each task from K to N, if its ref exists — a taken rewound/ name gets a
# suffix, never a new owner:
git update-ref refs/bwr/<run>/<lot>/rewound/task-<t> <its sha>
git update-ref -d refs/bwr/<run>/<lot>/task-<t>
# then, oldest first, every commit the reset removed that was NOT a task —
# restored by content, and committed once, when anything is left to commit:
git checkout <that commit> -- <the paths it touched>
# before the commit, the rewind record atomically gains a re-land boundary:
# operation mark, base parent, intended index tree, subject identity and count
git -c core.hooksPath=/dev/null commit -m "<subject>"

progress.py note rewind.done --data '{"first":<K>,"last":<N>,"relanded":<count>,"op":"<the record's mark>"}'
```

**A ref left in place points at code that is no longer in the tree.** The next
implementer of task K+1 would be handed `task-K` as its previous state and read
abandoned work. Each one is posted again when its task goes green.

**They move rather than disappear**, under `rewound/`. **It is the only handle left on
those commits** — nothing else points at them once the tree has gone back, exactly as a
failed attempt's `try-<K>` ref is the only handle on its own. Nobody reads that namespace
during the run, and the end-of-feature sweep takes it with the rest.

**And what the reset removed that was not a task comes back.** Between two task commits
the controller may have committed a decision — an amendment landing mid-lot, a plan
recommitted by an earlier re-cut. **Those decide nothing about the code being rewound and
they must survive it**: an amendment silently unlanded leaves every rebuilt task working
against a spec that no longer says what the human settled, while the journal claims it was
committed. The script re-lands them, oldest first, and reports how many.

**They come back by content, never as a replayed patch.** A plan committed by an earlier
re-cut and every task commit write the same plan copy, so a patch would be applied against
a base that no longer holds what it was made against — and it would fail **after** the
reset and **after** the refs have moved, leaving a destructive sequence half done. Restoring
the paths cannot fail that way, and taking them oldest first leaves the newest state of
each file in place: for a spec amended twice, exactly the one that is wanted.

**The re-land commit does not repeat after a cut.** Once the final index is ready, the
script atomically adds its operation mark, base parent, intended tree, subject identity
and replay count to `rewind-in-progress`, before `git commit`. On the same-call retry,
that tree still staged at the base means the commit never landed and may be retried. A
controller-owned re-land disables project hooks and then authenticates `HEAD^{tree}`
against that frozen tree before `rewind.done`. A hook cannot replace restored bytes.
clean index with `HEAD` as the exact direct child, with the intended tree and subject,
means the commit already landed: the script skips the reset, restore and commit, and
writes only `rewind.done` before removing the record. Every other state is a read-only
refusal taken to the human. A refusing hook leaves the prepared boundary in place; fix
the hook condition and run the exact same call, or make that exact commit manually and
let the same call authenticate it and finish the tail.

**The plan copy comes back stale, and that is correct.** It is restored as it stood at that
commit, which is one or more designs behind — `docs/plans/` is an output, the workspace
holds the plan, and the next task commit republishes it.

**Say it in your report when the count is not zero** — a decision that was taken off the
branch and put back is worth one line.

For **C3.9d**, the decomposition changed, so rewrite the plan in the workspace, copy it,
and commit it — exactly as at the end of C1.

### After a C3.9c, the later tasks are rebuilt

**All of them, from C3.1, one attempt each, in order** — exactly as the C3.9 table says:
what is erased is the code of tasks K to N.

**There is no shortcut for replaying them**, and there was one here that did not hold. It
compared the redone task K against the one it replaced and, on a byte-identical tree,
declared the later tasks safe to replay. Two things were wrong with it. **A C3.9c means an
earlier task's exact accepted obligation was wrong or unmet by its built result**, so the
task is redesigned or corrected — a result identical to the one just rejected is not a
case worth a mechanism. And replaying is work nobody
here may do: the controller writes no code and runs no gate, and an implementer builds one
task from its own design.

**Rebuilding costs sessions, and it buys something.** Each later task is designed against
the new task K, judged by its two checkers, and closed by its own gate. A replayed commit
would carry code written against a task that no longer exists.

### Recording a success

```sh
<workspace>/prompts/construction/attempt-succeeded.sh \
  <lot> <N> <the reported commit> <final gate op>
```

This closer has the same controller-operation precondition as failure. It refuses all
four markers before both its fresh path and its already-recorded task-ref tail. Settle
the exact owner first, then retry success; the attempt identity remains unchanged.

**It is the check** *What comes back* sends you here for, and it prints the SHA it
recorded. **Ten refusals, and each has its route — the session stays alive until its
route has run:**

| The refusal | The route |
|---|---|
| the call's task does not match the attempt in flight | **the identity file names the attempt that was started** — `attempt-in-flight`, written by the start script. The recording takes the attempt's own identity: recheck which task this session was, and rerun with it. |
| the attempt was never marked as started | **your own launch order broke**, and nothing can attribute what sits on the branch — a mark cannot be taken after the fact. Stop and take it to the human, as you would a tree that is not yours. |
| the tree is not clean, or the final gate does not prove the exact commit tree | the task is not finished. **Any content repair returns to the code checker and opens a new logical final gate before `--amend`.** A path it does not recognise as its own is reported and never committed or removed. A second refused `Done` ends the attempt. The final gate proof is either a clean checker verdict or the complete round-10 resolution with no accepted defect. |
| `HEAD` is still the attempt's own starting mark | **the task delivered nothing**, whatever it reported. End it — `attempt-failed.sh <lot> <N> <K> C3.9b` records the failure and preserves nothing, since there is nothing — retire it `failed`, launch a fresh attempt. |
| the reported value is not a commit | a garbled report, not a bad state: **ask the live session again** — `git rev-parse HEAD` — and rerun this call. |
| `HEAD` is not the commit that was reported | the report and the branch disagree — nothing more is proved yet. **Read `attempt-base..HEAD` before choosing**: **exactly one commit, the implementer's own** → the branch is right and the report is wrong — a garbled hash, not a bad state: ask the live session again, `git rev-parse HEAD`, and rerun this call, as the row above does; **several commits, all the implementer's** → it committed more than once and reported an early one — the last row's route; **any commit that is not the implementer's** → **a foreign commit is on the branch: stop and ask the human**, as C0.1 does. |
| the commit does not carry the plan copy, or carries a stale one | **the write set is the code AND the refreshed plan copy**. Send it back once through the complete code-checker, pre-gate publication, staging and fresh final-gate boundary before `--amend`. A second refusal ends the attempt. |
| the workspace or committed plan has a different whole-plan ownership projection from the attempt's frozen line 2 | **the implementer changed controller-owned plan bytes.** Do not publish or accept it. Restore them. If the plan truly must change, fail the attempt and take the controller-owned re-cut route; only its plan commit establishes new authority. |
| the task's own ref already exists | **a validated ref never moves — and the script settles this first, before it requires the identity.** This closer has no journal note and no pending marker, so the ref is its only completion proof: **equal to the reported commit, the recording completed and only its output was lost** — the script answers `already recorded`, clears a matching stale identity, and what remains is yours: retire the implementer and advance, never rerun anything. A ref that differs refuses: the task number is wrong, or the report is — check which task you meant. A rebuilt task has no ref to collide with; the rewind took it out of the way. |
| more than one commit since that mark | **the task broke *one task, one commit*** — a rewind reads any commit not at a task ref as the controller's and re-lands it, so half a task would come back from the dead. The attempt cannot repair this — a reset is not the implementer's to make. Route it as a failed attempt, classification `C3.9a` — its design was closed by its checker — `attempt-failed.sh` preserves the commits on the try ref and puts the branch back to the mark; the next attempt implements the design again, in one commit. |

**The dirty-tree row grants one return, and the grant is journaled as it is given** —
`progress.py note bound.spent --task <N> --text "dirty Done sent back - attempt <K>"` —
because after a compaction that note is the only thing that says the return was already
used, and a second refusal must end the attempt instead of granting another.

*It runs the equivalent of:*

```sh
git rev-parse refs/bwr/<run>/<lot>/task-<N>             # settled FIRST, before the identity is required:
                                                        # equal to the reported commit — already recorded, done;
                                                        # different — refused. The completed call's one crash
                                                        # window leaves exactly ref present, identity absent
git status --porcelain                                  # must be empty
git rev-parse refs/bwr/<run>/<lot>/attempt-base         # must differ from HEAD
git rev-parse <the reported commit>                     # must equal HEAD
git rev-list --count refs/bwr/<run>/<lot>/attempt-base..HEAD    # must be exactly 1
<workspace>/attempt-in-flight                           # line 2 freezes headings, whole-plan ownership and task contract
git show HEAD:docs/plans/<run>-<lot>-plan.md            # must exist; its manifest and the
                                                        # workspace manifest must both equal line 2;
                                                        # their complete bytes must also be equal
bash <workspace>/prompts/construction/gate-check.sh require-task \
    <gate op> <lot> <N> <K> <reported commit>           # exact gate, code proof and tree
git update-ref refs/bwr/<run>/<lot>/task-<N> HEAD       # its absence was proved at the top

progress.py note attempt.succeeded --task <N> --data '{"attempt":<K>,"lot":"<lot>","sha":"<sha>","gate":"<op>"}'
                                                        # the permanent record that K was used — a
                                                        # rewound success leaves no other trace, and
                                                        # the start guard reads this line to never
                                                        # reuse the number. The identity file falls
                                                        # last, after the note it feeds.
```


**Why the attempt's own mark, and not the previous task's ref.** `HEAD` differing from
`task-<N-1>` proves nothing: **the controller's own commits validly sit between them** — an
amendment landing mid-lot, a rewind re-landing what it had removed.

**And why the reported hash does not answer it either.** An implementer that committed
nothing can read the current `HEAD` and report that; it is a commit, it equals `HEAD`, the
tree is clean. **Only a mark taken before the attempt ran cannot be produced after the
fact.** The two checks answer different questions, and neither replaces the other.

**What neither can catch is a commit from outside, made mid-attempt and then reported as
the implementer's own** — no after-the-fact check can. What closes it is the standing
contract of `SKILL.md`'s Git section: the tree is the run's while the run lives, and
nobody else commits on the branch — a human who must, pauses the run first.

### C3.10 · Blocked

The implementer stopped because the plan is silent or contradictory, or because it
reached a product choice the spec does not settle. **It never invents, so a blocked
implementer did the right thing.** Its session stays alive, parked `blocked`.

Read what it is asking, and answer in one of three ways:

- **The spec or the plan settles it** — quote the passage, set it back to `working`, send
  the answer. It continues from where it stopped.
- **The plan is at fault** — it is silent where it should not be, or it contradicts
  itself. Three gestures of your own, then the ordinary routing:

  1. **Fix the plan yourself**, in the workspace copy. You wrote it: a silence is yours to
     fill, a contradiction yours to resolve. **This gesture exists nowhere else** — a
     failed attempt says nothing about the plan, so no failure route corrects it.
     **Classify what you had to change: C3.9b if the task's own section was at fault,
     C3.9d if it reached the decomposition or an interface.** On a C3.9d, stop after
     classifying: the routing rewrites and recommits the plan itself, and you are not
     doing it twice.
  2. **Preserve and reset, exactly as a failed attempt**, before anything else is
     launched:

     ```sh
     <workspace>/prompts/construction/attempt-failed.sh <lot> <N> <K> <C3.9b|C3.9d>
     ```

     **A blocked implementer may have written code before it stopped**, and none of it may
     reach the next attempt — that is the whole point of one session per attempt.
  3. **Retire it `superseded`**, never `failed`. It did exactly what it had to by stopping
     instead of inventing. *The attempt did not deliver; the session did not fail. The
     script records the first, the retirement records the second, and they are allowed to
     say different things.*

  **Then go to C3.9 with that classification and follow it as written**, and nothing of it
  is repeated here — the rewind that takes the earlier tasks and their refs out of the way
  on a C3.9d, the plan rewrite that goes with it, and where the next attempt starts.

  **One thing C3.9 does not know:** this attempt wrote no failure report. It stopped before
  it had anything to report, and what the next one works from is the corrected plan.
- **Only a human can answer** — it is a DECISION. Escalate it through `SKILL.md`'s
  identified `R<N>` route and leave the session `blocked`. Publish the run-wide
  `ruling.ready` state and resolve any conflict with an earlier active answer before the
  spec edit or amendment route. Set the implementer back to `working` only after that
  route has put the effective answer in the spec, just before you send it down.

  ```
  progress.py session-status <id> blocked
  progress.py session-status <id> working
  ```

**Never answer a product question yourself** to unblock a session faster. That is the
one thing you do not decide.

### C3.11 · All tasks green

Go to PRODUCT REVIEW.

---

## When the human stops the run

`SKILL.md` carries the procedure, pause and abort alike. What construction owes it is
the step called **the work in flight**.

At most one implementer is alive, and it holds two things: a `### Design` block, and
uncommitted code.

**The design survives on its own.** It lives in the plan, in the workspace, outside git —
a reset cannot reach it, and there is nothing to do about it now.

**And the resume routes on the classification the stop found settled — `C3.9b` is the
default for an UNCLASSIFIED interruption only.** A stop can land wherever the
implementer happened to be, and **a `### Design` block that is there tells nobody
whether it was finished, whether its checker ever ran, or whether it was sent back** —
only that checker can say a design was sound, which is what `C3.9a` claims. So an
implementer stopped mid-work, or a silent one, resumes as `C3.9b`, and the launch
message of the fresh attempt says the previous one was **paused**, never that the plan
was corrected. **But a classification settled BEFORE the stop is a routing fact the
pause must not erase**, and three windows hold one:

- a `Failed` whose classification is settled — **an audited report on disk**, the
  strongest source, since the report itself survives the stop; **or a report whose one
  repair was spent, the classification accepted from the message** — the reportless
  retry's route, where the message is all there ever was. Either way the resume routes
  on THAT classification, the `C3.9c` rewind and the `C3.9d` re-cut included — and the
  second source survives only in the stopping point, so writing it there is what keeps
  it from dissolving into the default;
- a `Done` refusal whose row had already chosen its route — `C3.9b` for
  nothing-delivered, **`C3.9a` for the multi-commit and second-refusal rows**, whose
  checker-approved design the blanket default would needlessly discard;
- a plan fault already classified `C3.9b` or `C3.9d`, the workspace plan possibly
  carrying only the first half of that route.

**Write the settled classification into the stopping point — it is exactly what that
note exists for — and the resume routes on it: the C3.9 table as written, rewind and
re-cut included, never the blanket default.**

**The code:**

| | |
|---|---|
| **Pause** | preserve it on a ref, then step back. It is the one thing that would otherwise be built twice. |
| **Abort** | the same preserve and step back — **and any unaccepted commit leaves the branch with it**: the try ref is the only record naming that code an abandoned attempt, and the refs' fate is the human's question at an abort's end. Then the clean removes what the task created. |

**A task creates files as much as it changes them**, a new module, a new test, and a
`reset --hard` leaves those where they are. The script removes them and lists what it
removed. It leaves ignored paths alone, which is how the workspace survives its own abort.

**`SKILL.md` puts the tree back with one call, and this mode is what fills its arguments:**

```sh
<workspace>/prompts/common/stop.sh pause <lot> <N> <K>     an implementer was alive
<workspace>/prompts/common/stop.sh abort <lot> <N> <K>     the same, aborting
<workspace>/prompts/common/stop.sh pause                   nothing in flight
<workspace>/prompts/common/stop.sh abort
```

*It runs the equivalent of:*

```sh
# pause — preserve whatever the attempt holds: the commit only if anything is
# staged, the ref only if HEAD then sits past the mark — an untouched attempt
# preserves nothing. A taken try name — an earlier, incomplete stop of this
# same attempt — gets a suffix, never a new owner. Then step back to the
# attempt's own mark, never to the task ref.
BASE=$(git rev-parse refs/bwr/<run>/<lot>/attempt-base)
git add -A && git commit --no-verify -m "<feature> <lot> task <N> attempt <K> — PAUSED"
git update-ref refs/bwr/<run>/<lot>/task-<N>-try-<K> HEAD
git reset --hard "$BASE"

# abort with an attempt in flight — preserve and step back exactly as a pause,
# under the same two conditions, then clean
git add -A && git commit --no-verify -m "<feature> <lot> task <N> attempt <K> — ABORTED"
git update-ref refs/bwr/<run>/<lot>/task-<N>-try-<K> HEAD
git reset --hard refs/bwr/<run>/<lot>/attempt-base
git clean -fd            # the reset does not remove the files the task created

progress.py note paused --task <N> --text-file "$JOURNAL_TEXT_FILE" --data '{"sha":"<sha>","attempt":<K>}'
progress.py note aborted --task <N> --data '{"sha":"<sha>","attempt":<K>}'
```

**It prints the SHA of the last validated task**, and on a pause the SHA of the preserved
attempt. Report both.

**A diagnostic worktree that was open rides through a pause** — its path is rebuilt from
the lot, the task and the attempt, and a resumed diagnosis finds it where it was. **On an
abort, close it**: `diagnostic-close.sh <lot> <N> <K>` — a registered checkout is the one
thing the abort's reset and clean cannot reach, and nothing after the abort comes back
for it. **After the stop's wait step, as everything here**: a diagnostic still reading
that checkout must have ended — returned, or errored out — before its input is removed
from under it.

---

## Leaving construction

1. Check every task has its git ref and the tree is clean.
2. Report to the human: what was built, and how many attempts.

   ```
   progress.py note lot.built --data '{"tasks":<N>,"attempts":<M>}'
   ```
3. **Do not delete the refs.** PRODUCT REVIEW and the sub-lots still use them.
4. Go to **MODE PRODUCT REVIEW**.

---

## Who runs on what

| Actor | Kind | Level |
|---|---|---|
| **Implementer** | session | preset `Implementer` |
| **C0 and C3.7** — gate runner | subagent | light / medium |
| **C2** — completeness | subagent | strong / medium |
| **C3.8** — diagnostic, when needed | subagent | strong / high |
| **C3.2** — design checker | subagent | strong / high |
| **C3.6** — code checker | subagent | strong / high |

What a level means is in `<workspace>/prompts/common/vocabulary.md` — defined once, for everyone.

The two checkers are spawned **by the implementer**, so their level is set in
`<workspace>/prompts/construction/implementer.md`. You cannot impose it after the fact.

---

## Red flags

### While writing the plan — C1

| What you are telling yourself | The reality |
|---|---|
| "I'll list the files this lot will touch" | You have written nothing. Map the responsibilities and where they live. |
| "I'll put the exact code in, it will save the implementer time" | You are writing blind. It becomes an order to build something already known to be wrong. |
| "This task can't stand alone, the next one finishes it" | Then it is not a task. Merge it, or cut elsewhere. |
| "Task 6 would have to change task 1's code, that's a bad split" | No. A later task may change an earlier one's code. That is not what standing alone means. |

### While C2 runs

| | |
|---|---|
| "It found three gaps, I'll fix them and go to C3" | A fix changes the counts. Run C2 again. |
| "The split is wrong but I can patch the plan around it" | That is C2.6. Go back to C1. |

### While tasks are being built — C3

| | |
|---|---|
| "These two tasks are independent, run them together" | They commit over each other. Sequential, without exception. |
| "It reports green, that's the proof" | The gate says nothing tested broke. Both checkers have to close too. |
| "It went quiet, I'll kill it" | Ask where it stands first. Kill it on the second tick, or on no answer. |
| "I'll fix this one line myself" | Every change to the tree goes through an implementer and the gate. |
| "Task 5's attempt is nearly right, I'll have it patched" | An attempt built on a wrong design carries decisions taken for the wrong reasons. Erase its code, keep its plan section, redo it. |
| "The plan says task 1 exposes this signature, so task 6 can rely on it" | The plan is dated: it says what was true when task 1 was done. Read task 1's code — its git ref points at it. |
| "Third attempt, same failure, let's try again" | The classification is wrong. Diagnose it — once per task: a failure that survives the diagnosis goes to the human, with the analysis. |

### At any point

| | |
|---|---|
| "The baseline was already dirty, let's start anyway" | Then nothing you produce can be shown to be clean. Halt. |
