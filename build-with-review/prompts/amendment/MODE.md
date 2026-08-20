# MODE AMENDMENT

**This file governs an amendment.** Everything you need is here, in
`<workspace>/SKILL.md`, and in the files this one names.

An amendment is **a short spec of its own**: it states one coherent change set to what
the product must do, and it lands in the living spec. Most start from one DECISION. One
R2.4 decision batch puts all of its current built-part rulings — initial and
supplemental or conflict-resolved — into the same amendment, exactly like one amendment
to a quote can change several settled lines together. It never mixes decisions from
different batches as new changes. **Every amendment also receives the run-wide
product-answer state.** Active answers from other open or closed batches and identified
individual rulings are preservation constraints, not extra amendment members. It is
not a phase of anything — you enter it from
wherever you were, and you go back there when it closes. **One branch takes the
long way home**: a reach whose next frontier cannot be enumerated from the available
durable inputs sends the whole spec through a full review before the work resumes — the
exit door, in A3.

You arrive here with a workspace, a watchdog and a feature already under way. **Nothing is
created here except the amendment itself.**

---

## When you are in this mode, and when you are not

**The trigger is always one or more settled DECISIONs, and never anything else.** Every
decision in one grouped product-review amendment comes from the same durable decision
batch. Plus one condition:

| | |
|---|---|
| **no lot has built the part it touches** | **edit the spec in place and commit it, that path alone** — the DECISION channel in `SKILL.md` carries the gesture. This mode does not open. |
| **a lot has already built it** | **an amendment** |

DECISIONs arrive from everywhere — an implementer that stopped rather than invent, a
disagreement its checker could not settle, a review lens, or the human at any moment. They
all reach you, and **you** decide whether the answer opens this mode. R2.4 already made
that classification for its batch; read its actions artifact instead of classifying one
member at a time.

**And it never opens while a spec review loop is open** — the first, or a re-entry after
an amendment. The loop's fixer is the spec's live writer, its rounds re-verify everything
it writes, and its close commits it all at once: route the ruling there as a finding. A
nested amendment would consolidate against a document whose working copy already carries
unclosed edits, and park the very reviewers whose job is to re-verify the change.

### What stops, and what does not

- **The work in flight stops where it is — and stopping it is sometimes yours to do.**
  An implementer that raised the DECISION is already stationary: `blocked`, alive, its
  partial work uncommitted in the tree. **One that did not raise it is still writing** —
  the DECISION came from the human, or from anywhere else while an attempt was
  `working`. **Stop its process and set it `idle` the moment this mode opens**:
  annotating does not stop it, and a child still writing changes the tree under
  everything this mode does. Stopped, it is what the rest of this mode assumes — a
  stationary attempt, woken by the next message you send it if its row says it
  continues. A sub-lot waiting on a review answer keeps waiting.
- **Then look at the tree, once — a stopped attempt may already have committed.** Clean
  and past the attempt's own mark means it delivered its commit and was caught before
  reporting. **Settle it before anything else**: the amendment commit will move the
  mark, and a commit stranded below a moved mark can neither be accepted nor removed.
  Set it back to `working` — the status change precedes the message, as everywhere —
  then wake it, telling it to answer and wait. **Done, with its hash** → the ordinary
  acceptance — `attempt-succeeded.sh`, retire it `done` — and nothing is in flight.
  **Anything else** → it committed without being finished, which no route allows: end
  it — `attempt-failed.sh <lot> <N> <K> C3.9b` preserves committed work and puts the
  branch back to the mark — retire it `failed`, and the task's fresh attempt waits for
  the amendment to close, like every restart. **A dirty tree, or a clean one at the
  mark, needs nothing**: that is the stationary attempt the rest of this mode assumes,
  and the rows of *Going back* then always face uncommitted work.
- **A product-review pass in flight is parked the same way.** Stop each running lens's
  process and set it `idle` — their subject is the very contract being reopened. If A1
  ends with no amendment, wake them, `working` first, and the pass continues. **If the
  human ORDERS the amendment — A1's other exit — A1 writes `amendment.opened` first,
  then the pass is void and its void runs THERE, before any amendment child exists.**
  No lens retirement, report move or pass close precedes the opening: that line is what
  makes an interrupted void resumable. The reversible park exists only for the branch
  where no amendment happens; once the order is given that branch is gone, the pass will
  be relaunched against the spec as it lands, and nothing it could still produce survives
  that. **Deferring the void to the landing deadlocks the cap**:
  parked lenses stay open, an open child holds its concurrency slot until acceptance —
  `idle` frees nothing — so a pass-filling wave plus the fixer plus a sweep exceeds
  every allowed cap, and the landing that would finally retire the lenses sits behind
  sessions that can never launch. So, at the order: retire **every lens still open**
  `superseded` — they did nothing wrong. **One already retired `done` keeps that
  status**: its assignment was delivered and accepted when it closed, and a second
  terminal line would make the journal contradict itself — that its accepted report is
  now void is recorded once, for the whole generation, by the `pass.closed` line
  below. Move each report aside with the usual gesture, the suffix saying why
  (`-superseded`), and discard the verdicts of any verifier that was running: a
  subagent cannot be stopped alone, and its output belongs to the voided pass. **And
  close the voided pass in the journal, in the same gestures**:

  ```
  progress.py note pass.closed --data '{"voided":true}'
  ```

  Every pass that opened is closed, the voided ones included — the relaunch writes a
  fresh `pass.opened` for the same built lot, and without this line the old generation
  stays open forever: a takeover pairing openings with closes would read settled,
  voided readings as work still in flight. **Once the run is back in product review, relaunch the pass from its start** —
  fresh lenses, freed paths, against the spec as it now stands — **and not before every
  discarded verifier's call has ended — returned, or errored out**: it cannot be
  stopped, and while it runs its copy is live at the very path its successor will
  reuse. One that returns closes its own copy on the way out; one that dies without
  returning leaves a dead copy, which is exactly what the successor's open removes.
  **And a pass past its readings is void the same way** — five reports settled, the
  adjudication under way, its sub-lot not yet opened: completion does not make those
  reports valid against a changed contract, and what they never reported is still an
  accepted absence. Nothing is left to park or retire — no slots are at stake — but
  the trigger is the same: **at the order**, move the reports aside and **close the
  pass with the same `pass.closed` line**: this branch never
  reaches R2.5, the only findings route that closes a pass, so without it the completed
  adjudication stays open in the journal under the fresh generation. The relaunch is
  the same. A single recorded ruling survives. For an R2.4 group, its source, actions,
  completed global rechecks, ready conflict resolutions and initial or supplemental
  answers survive too: they froze every verified claim, latest verdict and run-wide
  effective human answer before this void, and the five
  lens-report move never touches them. The batch stays open until a later R2.5 consumes
  its remaining correction obligations.

  **A cut inside either void resumes by finishing it, never by replaying it.** Read the
  product pass named by `amendment.opened`, then reconcile each gesture from durable
  state: stop only lens processes still running; retire only sessions still open;
  move aside only canonical report paths still present; let discarded verifier calls
  end; and write `pass.closed {"voided":true}` only when no such close follows this
  amendment's opening. A terminal lens stays terminal, an already-moved report stays
  where it is, and a close already present never repeats. Only that close releases A2.
- **A completeness check in flight cannot be parked** — a subagent is not stoppable
  alone. Let it return; if the amendment lands, its verdict is void with the spec that
  fed it, and *Going back* says when the pass runs again.
- **Neither can a construction diagnostic.** Let it return. It classifies why past
  attempts failed, so its verdict survives the amendment only where its task's mandate
  does: intact mandate → route on it as construction says; changed mandate → the verdict
  is void, the realignment's own classification replaces it. **Either way, close its
  worktree once the routing is settled** — `diagnostic-close.sh <lot> <N> <K>` — or the
  checkout outlives everything that knew it existed.
- **Nothing is erased while the amendment is open.** What becomes of that half-written
  work is decided at the end, in *Going back*, and it depends on the answer: an attempt
  whose task still means the same thing carries on with it, one whose task changed ends
  and its code goes with it.
- **You never build against a spec that does not yet say what was decided.** That is the
  only reason anything waits.

---

## A1 — Discuss until the decision is settled

**You and the human talk.** No imposed form, no number of exchanges, no widget shape: the
subject decides how far it goes. Some answers take one message, some take twenty.

**One origin skips this discussion: an R2.4 decision batch is already settled.** Its
initial `decision.batch.settled` and any `decision.batch.supplemented` events carry every
human answer. Every `decision.conflict.ready` resolution updates which answers are active
and their exact effective text. Its ready actions artifact, conflict resolutions and
latest accepted completed global recheck, when one exists, select all active current-owner
built-part decisions as one amendment. Every external active identity is a preservation
constraint. Ask nothing again. A1 begins at the durable opening below for that whole group.

An identified individual product ruling also skips this discussion once its `ruling.ready`
state exists. The exact answer already belongs to owner `R<N>`. If its active route is
`amendment`, A1 begins at the same durable opening without asking it again.

It ends when **the human settles it and says to write the amendment.**

**It can also end with no amendment at all** — the human rules that the spec stays as it
is. Record the ruling, and the run resumes exactly where the entry stop left it: **a
parked attempt** goes back to `working` — the status change precedes the message, as
everywhere — and is woken with the answer; **one accepted `Done` at the
entry settlement** was recorded then, so construction simply moves on — the next task,
or the review if it was the last; **one ended there** is relaunched now, a fresh attempt
with nothing corrected, since there is no amendment to wait for; and **when nothing was
in flight**, the waiting work proceeds as it stood.

**For an identified product answer, the run-wide state must be ready first.** Its exact
proposed change must coexist with every earlier active identity, or its owner resolves a
global conflict before this mode opens. `amendment.opened` never precedes that proof.

**When the human orders the amendment, its first gesture is durable — before any pass
is voided and before any document exists.** Allocate `<N>` once, one more than the
highest amendment number carried by an `amendment.opened` note, then write:

```
progress.py note amendment.opened --data '{"amendment":<N>,"origin":"<origin mode>","built":"<built lot, product-review only>"}' --text-file "$JOURNAL_TEXT_FILE"
```

For an R2.4 group, the same opening binds the one source batch:

```sh
progress.py note amendment.opened \
  --data '{"amendment":<N>,"origin":"product-review","built":"<built lot>","batch":<B>,"members":["B<B>/D1","B<B>/D2"],"state_kind":"<kind>","state_ref":"<ref>"}' \
  --text-file "$JOURNAL_TEXT_FILE"
```

`members` is the complete ascending list of active current-owner decisions whose latest
route is `amendment`. It is never empty. `state_kind` / `state_ref` names the latest
durable boundary that changed this batch's answer state: `decision.batch.ready` / `B<B>`,
`decision.batch.supplemented` / its `after_op`, an accepted `decision.recheck.completed` / its
`commit_op`, or `decision.conflict.ready` / `<owner>/C<N>`. The journal before this line
reconstructs the full generation. `progress.py` refuses zero, omitted or added members,
a stale or invented state reference, and a second opening for the same generation.

For one identified product ruling, bind its owner instead:

```sh
progress.py note amendment.opened \
  --data '{"amendment":<N>,"origin":"<origin mode>","ruling":"R1","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}' \
  --text-file "$JOURNAL_TEXT_FILE"
```

`origin` is exactly `construction` or `product-review`. A construction opening follows
the validated SPEC close and cannot bypass an open product-review pass. A product-review
opening consumes the exact current pass and its built lot.

The line is the order's identity and return address. Its text is non-empty and contains
the complete order plus the exact phase return. Once it exists, the ruling is not
asked again and `<N>` is never reallocated. **If the origin is a product-review pass,
`origin` is `product-review`, `built` names its built lot, and the exact generation is
the last `pass.opened` for that built lot before this opening.** `batch` names the one
R2.4 source when this is a grouped amendment; `ruling` names an identified single product
answer and is mutually exclusive with `batch`. Its authority tuple copies the exact
latest complete state that selected this active `amendment` route; A4 copies it into the
terminal. Omit both for an operational amendment
that carries no product DECISION, and omit
`built` for every other origin. Only now run the product pass's void, exactly as *What
stops, and what does not* prescribes. A2 starts only after that void reaches its
`pass.closed {"voided":true}` boundary.

For a grouped opening, no later batch authority boundary may intervene before its commit
and terminals. Such a boundary makes the opening stale. It cannot authorize a terminal
or be silently folded into the amendment already written.

**A cut between the durable answer and this first gesture does not reopen the
decision.** An identified `ruling` plus `ruling.ready`, or the group's initial and
supplemental answers plus ready global actions, conflict-resolution and recheck artifacts,
already says that an amendment is ordered and
where it lands. Use that source to perform this gesture, with the return address from the
stopping point, and ask nothing again.

**Do not load `superpowers:brainstorming`.** The spec exists and is open in front of you;
its shape is the format you are writing into.

---

## A2 — Write the amendment

**A1 already allocated `<N>` and wrote `amendment.opened`.** Read that line and use its
exact identity and return address. Do not write a second opening. If its data carries
`origin:"product-review"`, the named pass's `pass.closed {"voided":true}` must follow
the opening before you write: absent means the void was cut, and the resume boundary
below finishes it first. The opening starts the amendment's generation; **it does not
say the document is ready.**

**Then you write the amendment**, as you wrote the spec. Then it stops being yours: from
A3 on, the fixer is its only writer.

For every identified product amendment, first reconstruct the **run-wide product-answer
state** from every identified ruling, batch settlement and supplement, ready state,
global recheck and conflict resolution in journal order. A closed batch remains in it.

When `amendment.opened` carries `batch:<B>`, also read that batch's immutable source.
First prove that its `members` and `state_kind` / `state_ref` still equal the batch's
current complete state. Then include **exactly every identity in `members`**, in that
stable local `D<N>` order. When the opening carries `ruling:"R<N>"`, include that active
`R<N>` as the amendment member. Do not include another authority as a new change, revive
a superseded answer or omit a named member because one section looks larger.

Every other active product answer — from an open or closed batch or an individual ruling
— is a preservation constraint. This amendment may extend the spec, but it may not erase,
qualify or contradict one. If its proposed change cannot preserve one, no document fixer
or commit consumes it: the current owner opens a conflict first under `SKILL.md`'s global
answer boundary.

### The document

```
<workspace>/amendments/<N>.md                        where it lives and is written
docs/plans/<workspace name>-amendment-<N>.md         the copy, made once, at A4
```

**It lives in the workspace, exactly as a plan does, and for the same reason.** The
workspace is outside git, so nothing that resets, cleans or stages the repository can reach
a document that is still being written. A `git add -A` preserving an interrupted task would
otherwise sweep it into that task's commit, and the reset behind it would take it out of
the tree — **the amendment safe by construction, not because somebody remembered.**

The directory is there: the workspace was created with it.

**`<N>` counts from 1, in the order amendments arrive, for the whole feature.** Nothing in
that name refers to a lot: an amendment can land mid-lot with no sub-lot in sight, and a
name that says otherwise would be false half the time.

**The copy's date is the workspace's**, like every plan of this feature — not the day you
write the amendment. One prefix for everything the workspace produced, so the files of one
feature sort together and any script can build the path from `<N>` alone. When the
amendment was actually decided is in the spec's status line, in the journal, and in the
commit.

It uses this exact section manifest. Every section is present once, in this order, and has
non-empty content:

```markdown
# Amendment <N>

## Order and return
<the exact amendment.opened text>

## Decisions
...

## Why
...

## What it changes
...

## What it preserves
...

## Where it was raised
...
```

It holds, and nothing else:

| | |
|---|---|
| **The decisions** | what the product must do now, stated as a spec states things; a grouped amendment gives each active `B<B>/D<N>` its own section and exact effective human answer, while a single amendment names its `R<N>` |
| **Why** | the DECISION or decision batch that triggered it, and how the human initially, supplementally or through a conflict settled every active member; superseded identities are named as history, never as requirements |
| **What it changes** | the passages of the spec it supersedes, quoted per decision |
| **What it preserves** | every other active product answer in the run, with its fully qualified identity, including answers from closed batches and identified individual rulings |
| **Where it was raised** | which lot was in flight, if any, and the decision-batch number for an R2.4 group |

**`What it preserves` is not prose for a reader — it is executed.** It names the behaviours
the existing suite already proves, so that a test deleted later has to point at a line
that authorised it. Deleting a test is the visible trace of a contract change.

**When the document is whole**, create `<workspace>/reports/amendment/<N>/`. The fixer
writes its decisions log there, and the sweeps their reports — **this mode's whole record
lives in it, and nothing else creates it.** Then journal the authoring boundary:

```
progress.py note amendment.written --data '{"amendment":<N>}' --text "<workspace>/amendments/<N>.md"
```

`progress.py` reads the canonical real document and real report directory. It checks the
complete section manifest, reproduces the durable order and return text, verifies every
identified amendment member, atomically publishes
`reports/amendment/<N>/written.md`, and adds that snapshot plus the opening and document
SHA-256 values to the same event. No caller supplies those proof fields. The snapshot
freezes complete controller authoring. The fixer continues to edit the live amendment.

No fixer or sweep exists before this line. An `amendment.opened` without its matching
`amendment.written` means the document may be partial; a resume returns to this A2 and
finishes the same `<N>`.

### Create the fixer

**First, a human checkpoint**: this mode spawns two kinds of child that no earlier checkpoint covered. One
widget call, two questions — the provider for the **amendment fixer**, and the provider for
the **reach sweep**.

Then create the fixer, and **whether or not the sweep finds anything**:

- provider chosen for the fixer, preset **`Fixer`**, **question widget disabled**
- title `- Amendment <N> fixer (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=fixer` · `bwr.mode=amendment` ·
  `bwr.feature=<feature>` · **`bwr.status=idle`**, plus `bwr.lot=<lot in flight>` when
  there is one. **`idle`, not `working`**: it is created before it has an assignment —
  parked with nothing pending is exactly what the status means, the watchdog leaves it
  alone, and it goes `working` just before each dispatch.

> Read `<workspace>/prompts/spec/fixer.md`,
> `<workspace>/prompts/spec/fixer-completion.md` and
> `<workspace>/prompts/spec/completion-rules.md` in full before doing anything.
> Then run `python3 <workspace>/prompts/common/additional-prompt.py read-global
> <workspace> <workspace>/additional-prompts/global.md`. Next run `python3
> <workspace>/prompts/common/additional-prompt.py read <workspace>
> <workspace>/prompts/spec/fixer.md <workspace>/additional-prompts/spec/fixer.md`.
> Its stdout is the one optional prompt. Read no other optional prompt.

Then what varies: **the amendment path, `<workspace>/amendments/<N>.md` — the document it
writes, and the only one until A4** — the spec path, **which it reads and does not touch**,
the workspace path, and its decisions log at
`<workspace>/reports/amendment/<N>/decisions-log.md`. *No round number: it is created
before the first sweep has run, and each dispatch of findings carries its own.*

**Say both halves.** Its prompt tells it that the document under review is its own to
write and that everything else is closed to it; if the spec arrives without that sentence,
a fixer holding both paths may well start editing the spec at round one — which is exactly
what A4 exists to do, once, under a check.

```
progress.py session-started <id>
```

**It is created now and not when findings arrive**, because it also carries out the
consolidation at A4 — so it is needed even when the sweep closes on its first pass. A rule
that holds every time beats a rule that is almost always right.

**You do not edit the amendment after this point.** An author defends its own text; that is
why the fixer exists.

---

## A3 — The reach sweep

**One mandate, and it is the whole review of this mode.**

### What it looks for

**Everything in the spec that depends on what the amendment changes** — and whether each
of those places is handled.

> The amendment says *"the dialog is removed"*. Elsewhere the spec says *"when the user
> validates, a mail goes out"*, and further on that the mail carries a link, that the link
> yields a code, **and that the code is entered in the dialog**.
>
> Remove the dialog and the last link breaks — and **nothing in the text ties the code to
> the dialog by a shared word.**

So the sweep works at two levels, and the second is the one that matters:

| | |
|---|---|
| **textual** | where is the changed thing named? |
| **functional** | **what loses its reason to exist if it disappears?** The code in the mail exists only to be entered in the dialog. |

### How it advances

**It does not predict the reach — it walks it and counts at each hop.**

```
hop 1 : the dialog        → 3 places depend on it
hop 2 : those 3           → 2 new (the mail, the confirmation)
hop 3 : those 2           → 0 new
                            closed
```

**Each place found is handled: kept · moved · removed · or raised as a DECISION.**

**A behaviour that lives in the code and not in the spec has its references in the test
suite.** The tests that assert it are the places to handle — found by reading the suite,
not by running anything. A test the amendment leaves asserting something the product no
longer does is a place, like any other.

### Launching it

One session per sweep, **fresh every time**: the provider chosen for the sweep, preset
**`Reviewer`**, **question widget disabled**.

- title `- Amendment <N> reach sweep R<K> (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=reviewer` · `bwr.mode=amendment` ·
  `bwr.feature=<feature>` · `bwr.mandate=reach` · `bwr.round=<K>` · `bwr.status=working`,
  plus `bwr.lot=<lot in flight>` when there is one

> Read these files in full, in this order, before doing anything:
> 1. `<workspace>/prompts/spec/reviewer-common.md`
> 2. `<workspace>/prompts/amendment/reviewer-reach.md`
> 3. `<workspace>/prompts/amendment/reviewer-reach-completion.md`
> 4. `<workspace>/prompts/spec/completion-rules.md`
> 5. Run `python3 <workspace>/prompts/common/additional-prompt.py read-global <workspace>
>    <workspace>/additional-prompts/global.md`. Its stdout is the optional global prompt.
> 6. Run `python3 <workspace>/prompts/common/additional-prompt.py read <workspace>
>    <workspace>/prompts/amendment/reviewer-reach.md
>    <workspace>/additional-prompts/amendment/reviewer-reach.md`. Its stdout is the one
>    optional prompt.

Then what varies: the repository path, the spec path, the amendment path
(`<workspace>/amendments/<N>.md`), the workspace path, the sweep number, its report file
`<workspace>/reports/amendment/<N>/sweep-<K>.md`, and the human's standing rulings that
bear on this change.

**From sweep 2 on, two more lists, and nothing else of the past:**

- **the places the fixer declined, with its evidence** — so this sweep does not re-raise
  them;
- **the places to verify this time**, each with the fixer's exact edit.

With the rulings, that is the three short lists `reviewer-common.md` announces from round
2 on. **Never pass the previous sweep's `kept` places:** a fresh sweep walks the frontier
again, and the amendment has changed since.

```
progress.py session-started <id>
progress.py session-retired <id> done --archive --hide
progress.py note sweep.reported --round <K> --data '{"hop":<N>,"places":<N>,"closed":<true|false>}'
```

The third line goes in when the sweep's block checks out — **acceptance, never mere
arrival**: a block still being repaired leaves the report the sweep's, and a resume
that finds no `sweep.reported` treats it as absent, which it is. **On a genuine open
frontier:** copy the report's exact `NOT CLOSED` line to a file, then run
`progress.py note reach.not-closed --text-file "$JOURNAL_TEXT_FILE"`. The line carries
every completed hop count and the exact missing or unbounded input.

Each report has one exact `## Reach account`. It uses contiguous lines `Hop 1: <N> new`
through `Hop <K>: 0 new — closed` when the frontier closes. It then has contiguous
`## P1 · ...` place entries in the fixed `Sources` / `Location` / `Disposition` /
`Evidence` / disposition-specific handling shape from `reviewer-reach.md`. The sum of the
hop counts equals the place-entry count. Every P block owns exactly one disposition.
`progress.py` derives the receipt from this account and reconciles its mechanical facts
with the concrete fixed completion block. Fenced examples cannot supply account lines.
It freezes the report SHA-256, opening generation and one exact retired successful session
in the same event. A second live reach session for that logical sweep blocks acceptance.

**Retire each sweep the moment its report arrives and its block checks out, before its
receipt** — never
wait for the loop to end. A sweep is fresh every round, so an accepted one has nothing
left to answer, and left open it holds a concurrency slot beside the fixer's: two open
sweeps and the fixer fill the recommended cap, and the sweep that would close the loop
can no longer be launched.

### The loop

**After every fixer return, a new sweep, a fresh session.** A correction has a reach of its
own: *"the mail now goes out at revocation"* opens a frontier nobody has looked at.

**The fixer's lifecycle is yours to drive, exactly as in a spec review.** `working` just
before you send it a round's findings; on its return, audit the completion block — the
same table as any fixer's — then:

```
progress.py note fixer.returned --data '{"applied":<N>,"declined":<M>}'
progress.py session-status <id> idle
```

It sits `idle` while the fresh sweep walks — parked with nothing pending, unflagged by
the watchdog — and goes `working` again just before the next dispatch. A compaction then
finds in the journal which sweep's findings reached it and which return was accepted.

```
you write the amendment
  → sweep 1        2 places to handle
  → the fixer      amendment v2
  → sweep 2        1 place to handle
  → the fixer      amendment v3
  → sweep 3        closes, nothing new
  → A4
```

**It ends when a sweep closes with no new reference and no finding — with a complete
block.** A sweep whose completion block carries a `NOT DONE` closes nothing, whatever its
frontier says: what that line names, nobody walked. Lift the why if you can — the session
is still live. When you cannot, **retire it as any accepted sweep — its block is honest
and checks out — then launch a fresh one, the next number**: it walks the whole frontier
again, so what the `NOT DONE` named is covered whole, and the slot the outgoing sweep
held is the one its replacement takes. **And once only**: the fresh sweep returning the
same reason makes the blocker stable — stop launching sweeps and take it to the human,
as the exit door takes a frontier that will not close; `SKILL.md`'s audit duty carries
the gesture and its journal line. Nothing runs until they answer.

### A DECISION raised by the sweep

It is the mandate where they belong: reaching the end of a broken chain does not produce a
defect to fix, it produces a question nobody has answered.

> There is no dialog any more. The mail carries a code that is entered in the dialog.
> So: no mail at all? A mail with no code? A code entered somewhere else?

**Escalate it, the human answers, the fixer rewrites, and the sweep runs again** — that
answer has a reach of its own.

This is a product ruling, not the exit door's operational choice. Allocate its `R<N>`
through `SKILL.md` before asking, settle it with route `amendment-fixer`, and publish its
run-wide `ruling.ready` state before dispatching the fixer. If it conflicts with an active
answer from any batch or earlier ruling, resolve that global conflict first. The amendment
then gives this active `R<N>` its own decision section, and A4 writes its applied line
after the shared commit. The exit-door ruling below has no `ruling` identity and never
enters this state.

Before sending the answer to the fixer, publish its owner-linked assignment:

```sh
progress.py note fixer.dispatched \
  --data '{"ruling":"R1","route":"amendment-fixer","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}' \
  --text "<the complete authority artifact path>"
```

Send the artifact's exact answer and every active preservation identity. A resume reuses
this assignment and never writes another dispatch for the same authority generation.

Some of them settle themselves: when the spec elsewhere already decides the question, the
reviewer handles the place and asks nothing. Only what changes what a user lives with
comes to you.

### The exit door

**Report it and stop only when the next finite frontier cannot be enumerated from the
available durable inputs.** Continue at every positive hop while those inputs can form the
next finite frontier. No hop number and no place count is a cutoff. A zero-new-place hop
is the only normal close.

**The criterion is enumerability and closure, never size.** Thirty places found, all
handled, and a later hop returning zero is an amendment. A small frontier can be
`NOT CLOSED` only when its next hop cannot be formed from the durable inputs.

**Report every completed count and the exact blocker** — the missing durable input, or
the unbounded input, that prevents the next hop. Then let the human confirm. They may
answer *"carry on as an amendment"*, and that is their call to make explicitly rather
than by drift. Record the ruling either way:

```
progress.py note ruling --text-file "$JOURNAL_TEXT_FILE"
```

**The hand-back clause matters most on this branch**: it is the one whose review can run
for rounds, cross a compaction, and end at a close that must route on a return nobody's
context still holds.

The reason this door exists is not the size of the work: **a structural change
invalidates the validation that came before it.** The spec was approved under a contract
that no longer exists.

**What happens once the human confirms — nothing is thrown away, and the order is
fixed.** First **A4, as written, to its end**: the tree settled, the consolidation
carried and checked, the commit made — with the sweep's counts as the amendment record's
closing line. That commit records the complete change set, not a validation: the human
ruled every member and the check proved their landing exact; what nobody has re-verified is the
document around it. Then **the whole spec re-enters MODE SPEC at S3** — every mandate,
the document as it now stands, fresh rounds — and the fixes land at that loop's own
close, as in any spec review. **Nothing is built in between**: the work resumes once
that review closes. The amendment document keeps its role as the record of the decisions,
the places already handled stay handled, and **the human's rulings are never replayed**.
Nothing is re-decided. Everything is re-verified.

**And on this branch *Going back* narrows: nothing resumes.** **When an implementer
sits interrupted**, it ends whatever its row would have said: no session sits `blocked`
through a multi-round review, and nobody can promise a task still means the same thing
under a document about to be re-verified whole. Three gestures, in this order:

- **Classify now, from the amendment as it stands** — the human has just confirmed the
  route, so its text is final; A4's own check and commit follow in this same phase.
  The two lower rows classify as they always do; on the two upper rows nothing was
  wrong with the task, so the label is **`C3.9b`**, as for a pause: no checker closed
  that design, and nobody can vouch for it.
- **Preserve, reset, retire `superseded` — and rewind on a `C3.9d`** — under A4's
  first step, before the commit, exactly as the lower rows do it.
  `attempt-failed.sh` takes the classification just made.
- **The plan work and the launch wait for the review to close**, and are done against
  the spec as it stands then. If the review's own fixes deepen the damage — a `C3.9b`
  that has become a `C3.9d` — run the rewind at that point: it is safe after the
  commit, since a rewind re-lands by content what its reset removes. **And record the
  reclassification** — the journal's last word is the one a takeover follows, and its
  previous word says `C3.9b`:

  ```
  progress.py note attempt.failed --task <N> --data '{"classification":"C3.9d","attempt":<K>}'
  ```

  The fresh attempt carries no failure report, and its launch message states the two
  facts construction's launch contract asks for: the attempt was ended by the
  amendment, and the plan has been realigned since.

**And when nothing is in flight** — a review's adjudication, the human between
attempts, the next lot being planned, an attempt the entry settlement already
settled — the three gestures collapse to nothing: there is no attempt to classify,
preserve or retire. The review simply runs, and its close hands back whatever was
waiting, against the spec as validated then: a voided review pass relaunched from its
start — its interrupted adjudication is void with the spec it read — the lot's next
task, the plan being written; the run resumes where it stood.

---

## A4 — Settle the tree, consolidate, check, commit

**In this order, and the first step is the one that is easy to skip.**

1. **Put the tree where the work will resume from, before anything is written to it.**

   *Going back*, below, says what becomes of the interrupted attempt. **Take that decision
   now.** If the attempt carries on, there is nothing to do here. **If it ends**, run
   everything that moves the tree before you go further: its preserve and reset, its
   retirement, and — when it was classified `C3.9d` — the rewind that C3.9 performs. Only
   then come back and let the fixer consolidate.

   **A reset takes every commit above its target off the branch, and this phase's commit
   is one of them.** Commit first and the spec on disk goes back to what it said before the
   amendment, while the journal says `amendment.committed` and nothing downstream can see
   the difference. A `C3.9d` makes it worse: its rewind targets a ref older still.

   **The principle, and it is the whole of this step: the amendment lands on the state the
   work will actually resume from.** Anything else commits a change set onto a tree that is
   about to be thrown away.

2. **The fixer carries the amendment into the living spec.** It has just spent the loop on
   this text, and the controller does not edit a validated document. Tell it, in the same
   message, to close the amendment record with the sweep's result:

   > *closed at hop 3 · 5 places handled · 1 DECISION escalated*

   That line is the evidence the change set was bounded, and the amendment document is the only
   place it can live.

   **The same lifecycle bracket as every dispatch**: `working` before this message —
   it has sat `idle` since its last return — audit, `fixer.returned` and `idle` on the
   return; and `idle` is where it waits while each consolidation checker runs, `working`
   again before each discrepancy round.

3. **You update the spec's status line** — your one permitted edit, in the document's own
   vocabulary: *validated on such a date, amended on such a date, amendment N*. **That line
   and nothing else.** A second line you want to touch is a finding, and a finding reopens
   the loop. Do this before the checker. Its exact result then covers the final bytes that
   the commit consumes.

4. **A subagent checks the consolidation** — bracket it:

   ```
   progress.py subagent-started consolidation --round <n>
   progress.py note bound.spent --round <n> --text "consolidation round <n> of 3"
   progress.py subagent-ended consolidation --round <n> --data '{"exact":true}'
   progress.py subagent-ended consolidation --round <n> --data '{"exact":false,"discrepancies":<N>}'
   progress.py note verdict.consumed --round <n> --data '{"check":"consolidation","outcome":"exact"}'
   progress.py note verdict.consumed --round <n> --data '{"check":"consolidation","outcome":"discrepancies"}' --text-file "$JOURNAL_TEXT_FILE"
   ```

   *The `bound.spent` line is the round count that survives a compaction: count those
   lines before spawning a checker — **since this amendment's `amendment.opened`,
   never before it**, and only the domain lines whose text says `consolidation round`:
   earlier amendments and per-call failure retries are different counts. Write exactly
   one `verdict.consumed` immediately after the return, before editing or dispatching.
   Preserve discrepancies through `progress-rules.md`'s `--text-file` transport. Never
   put their bytes into shell source. Three consumed adverse rounds mean the exit below, never a
   fourth logical round.*

   **a strong model, effort medium**, prompt
   `<workspace>/prompts/amendment/consolidation.md`. Give it that path, the workspace path,
   its one optional additional prompt
   `<workspace>/additional-prompts/amendment/consolidation.md`, the amendment path
   (`<workspace>/amendments/<N>.md`), the spec path, and the base commit. It answers one question:
   **is the spec now exactly the old spec plus the amendment, no more and no less?**
   Also give it `<workspace>/additional-prompts/global.md`. Tell it to run `python3
   <workspace>/prompts/common/additional-prompt.py read-global <workspace>
   <workspace>/additional-prompts/global.md`, then `python3
   <workspace>/prompts/common/additional-prompt.py read <workspace>
   <workspace>/prompts/amendment/consolidation.md
   <workspace>/additional-prompts/amendment/consolidation.md` after its official prompt.

   *It gets margin on a closed task for the usual reason: nothing downstream catches its
   mistake. A wrong consolidation puts text nobody decided into the document that every
   later phase reads as the truth.*

   **It comes back `exact`, or with N discrepancies.**

   - **`exact`** → on to the commit. The consumed note is the
     durable permission to advance; a resume never checks this round again.
   - **N discrepancies** → **send them to the fixer, as they are**, and journal that
     exact assignment as you dispatch it:

     ```
     progress.py note fixer.dispatched --text-file "$JOURNAL_TEXT_FILE"
     ```

     The four shapes it
     distinguishes — an unauthorised change, a decision that did not land, an unrelated
     edit, superseded text still present — are all transcription errors, not decisions, so
     there is nothing for you to arbitrate. It corrects, and you spawn **a fresh checker**;
     never reuse the previous one. Only the accepted fixer return after this dispatch
     permits the next logical round's spend.

   **A lost result does not spend another round.** A consolidation domain spend with no
   matching consumed verdict relaunches the same prompt at the same `--round`, under a
   fresh subagent bracket and **without another domain `bound.spent`**. Record the
   regenerated result, then route it.

   **Three rounds at most.** A third consumed verdict still finding discrepancies is not
   telling you the fixer transcribes badly — it is telling you **the amendment does not
   say clearly enough what it changes.** Carrying it over decides nothing, which is
   precisely why a diff can verify it; an intention nobody manages to transcribe twice
   was never settled.
   Stop there, and take the exact entries from `verdict.consumed` to the human. A third
   result that was merely lost takes this same round-three regeneration route instead.

5. **You commit both files, with explicit paths.** The subject is yours to write, in the
   project's own conventions; everything else is the script's:

   ```sh
   <workspace>/prompts/amendment/amendment-commit.sh <N> <spec path> "<subject>" <lot|->
   ```

   **The last argument is the lot whose attempt is still in flight** — a blocked or
   parked implementer counts — or `-` when nothing is. It is not bookkeeping: **this is
   one of the two commits of this workflow made while an attempt can be in flight** —
   the other is the DECISION channel's in-place spec commit — and both move `HEAD`
   under that attempt, so the mark that says where the attempt began has to move with
   them. Without that, an implementer that goes on to commit nothing can report this
   very commit — clean tree, `HEAD` past the mark, reported hash equal to `HEAD` — and
   its task is recorded as built.

   *It runs the equivalent of:*

   ```sh
   document-copy.sh source amendments/<N>.md
   document-copy.sh copy amendments/<N>.md docs/plans/<workspace name>-amendment-<N>.md replace
   git add -- docs/plans/<workspace name>-amendment-<N>.md <spec path>
   git -c core.hooksPath=/dev/null commit -m "<subject>" -- docs/plans/<workspace name>-amendment-<N>.md <spec path>
   document-copy.sh finish amendments/<N>.md docs/plans/<workspace name>-amendment-<N>.md replace
   git update-ref refs/bwr/<run>/<lot>/attempt-base HEAD    # only when a lot is in flight

   progress.py note amendment.committed --data '<the script-owned clean-review proof>'
   ```

   Before the first copy or staging gesture, the script asks `progress.py` for the exact
   current opening, written-document, clean sweep, settled fixer and consumed exact
   consolidation proof. It freezes that proof in its pending marker. A retry reuses that
   proof. The terminal records the same amendment ordinal, hashes, sweep, consolidation
   round, operation mark and created commit SHA.

   **The helper sequence is load-bearing.** It proves the source and destination
   component by component under the exact physical workspace and Git toplevel. Every
   symlink, non-directory parent and non-regular leaf is a read-only refusal. The helper
   copies through a verified same-directory temporary and atomic rename, and every
   pending retry repeats the checks before any staging or commit-marker publication. An
   existing destination must be Git-tracked or owned by this exact copy's earlier durable
   workspace marker. That marker lands before the copy and remains through the amendment
   commit boundary; `finish` removes it only after that boundary, closing the
   rename-to-stage crash window.

   **This is where the copy is made, and the only place.** Until now the amendment existed
   in the workspace alone.

   **Never `git add -A`, never `git commit -a`**, and the pathspec is on the commit and not
   only on the add. **When the interrupted attempt carries on** — and that is the common
   case — its half-written code is still in the tree right now, and anything already staged
   would ride along. **This route and the DECISION channel's in-place commit are the only two
   places in this workflow where you commit with a dirty tree** — the same hazards, the
   same protections, at both.

   *When the attempt ended instead, this phase's first step emptied the tree of it, and the
   pathspec costs nothing.*

   One commit, not two: an amendment's complete change set and its landing are one event,
   and splitting them leaves a state where the spec says something nothing explains.
   The helper disables project hooks for this controller-owned document commit and proves
   both committed paths against its frozen prepared tree before any mark or terminal.

   **For a grouped R2.4 amendment, bind that landed commit back to every member named by
   its opening.** After `amendment.committed`, first prove that the opening's member set
   and `state_kind` / `state_ref` still equal the batch's current complete state. Then
   write one missing line per named member:

   ```sh
   progress.py note ruling.applied --data '{"answer":"B<B>/D1","batch":<B>,"decision":"D1","route":"amendment","amendment":<N>,"sha":"<sha>"}'
   ```

   Add `"conflict":<C>` when that generation is the answer's current authority. These
   lines do not say the code is corrected. The batch's actions, supplements, ready
   conflict resolutions and recheck state carry one implementation obligation per
   active built-part ruling until a later R2.5 puts it in a confirmed file. They say only
   that the effective human answer now lives in the spec through this exact amendment. A
   cut after the commit writes only missing lines; it never repeats the commit. A
   superseded answer receives no applied line.

   For an individual product owner, and for every active identified ruling settled by a
   sweep inside this amendment, write each missing line instead:

   ```sh
   progress.py note ruling.applied \
     --data '{"answer":"R1","ruling":"R1","route":"amendment","amendment":<N>,"sha":"<sha>","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}'

   # a ruling raised by this amendment's sweep changes only "route":"amendment-fixer"
   ```

   A direct opening copies its tuple from `amendment.opened` and uses route `amendment`.
   A ruling raised by a sweep copies it from its owner-linked `fixer.dispatched` and uses
   route `amendment-fixer`. A terminal whose authority tuple does not match the ruling's
   latest effective state closes nothing.

   In both forms, the amendment and consolidation proved every other active run-wide
   answer survived. Their older applied lines do not repeat.

   When the call used `-`, no live implementer will supply a later final task gate. Before
   a fresh product pass or next attempt, run one construction-style logical `baseline`
   gate on this exact clean amendment commit. Its owner is
   `amendment/<N>/<amendment commit SHA>`. Use the amendment commit's parent as the
   predecessor. The fresh pass consumes only this exact owner, or the one exact later
   C2 plan-only successor owned by `plan/<built lot>/<plan commit SHA>`. When a live
   attempt exists, its later code-checker and final task gate
   cover the amended candidate instead; do not accept the task without that proof.

6. **Retire the fixer `done`**, archive, hide — `progress.py session-retired <id> done
   --archive --hide` — **when it is still open**: one a stop already retired is not
   retired again, a terminal status is written once. Every sweep reviewer was retired
   as it reported.

---

## Going back

**Route on one question: does the amendment change what the interrupted work must do?**

| | |
|---|---|
| **No** — it touches something an earlier lot built | the implementer goes back to `working`, you send it the answer and the spec path, **and it continues where it stopped**. Its design still holds, and so does its half-written code. |
| **It adds work that blocks nothing** | the same: the task finishes as planned, and the new work becomes **a lot inserted after this one** — `SKILL.md`'s placement rule, already settled, and here also the only mechanically safe answer: a current-lot task would mean re-cutting and committing the plan OVER the parked attempt — a controller commit `plan-commit.sh` makes without moving the attempt's mark, so the resumed implementer's own commit would read as a broken multi-commit task |
| **Yes**, it changes what that task must achieve | **the interrupted attempt ends.** Classified **C3.9b** — see below |
| **It changes the decomposition** | the same, classified **C3.9d** |

**When the exit door fired, this table narrows: nothing resumes and nothing is
launched** — the exit door in A3 says what replaces it.

**The two lower rows are C3.10's *the plan is at fault* route, with the spec as the cause
instead of the plan**, and construction owns every gesture of it. Do not improvise a
shorter one here.

**Everything below that moves the tree happens under A4's first step**, before the
amendment is committed. Only the restart waits for that commit.

1. **Bring the task's plan section in line with what the amendment decides** — the spec
   itself says it only once A4 has landed it, but the amendment's text is final by now —
   and classify what you had to change: `C3.9b` for that task's own section, `C3.9d` if
   it reaches the decomposition or an interface. On a `C3.9d`, stop after classifying:
   the routing rewrites the plan itself.
2. **Preserve and reset** — `attempt-failed.sh <lot> <N> <K> <the classification>`. **The
   blocked implementer left half-written code in the tree**, and a fresh attempt must not
   find it there.
3. **Retire it `superseded`**, never `failed`. It stopped rather than invent, which is
   what it had to do.
4. **On a `C3.9d`, run C3.9's rewind now** — the one that resets to `task-<K-1>` and takes
   the refs of the affected tasks out of the way. **It is the last thing that moves the
   tree**, so the amendment must land after it, not before.
5. **Then the rest of C3.9, as written** — the plan rewrite, C1 and C2 on a re-cut, and
   where the next attempt starts. **After A4 has committed**, and not before: nothing is
   built against a spec that does not yet say what was decided.

**Like a blocked implementer, this one wrote no failure report**, and the next attempt
works from the corrected plan instead.

**If nothing was in flight** — the DECISION came from a review, from the human between
attempts, or while the next lot was being planned — nothing is special: this table has no
subject. The work that waits — **a voided review pass, relaunched from its start**, the
lot's next task, the plan being written — starts against the spec as it now stands, and
where NEW work lands is `SKILL.md`'s task-or-lot rule: a task inside the lot it blocks,
or a lot inserted after. For an R2.4 group, its decision batch remains open: the fresh
pass first completes all five new readings, then merges every normal correction and
every amendment-created implementation obligation from its source, actions,
supplemental answers, run-wide product-answer state, ready conflict resolutions and last
completed global recheck when that
pass reaches R2.4/R2.5. The
open batch is durable input to the fresh pass; it never skips or shortens those readings.

**And once the amendment has landed and the plan is back in line — whatever the row,
whatever the origin — run construction's completeness pass (C2) again before anything is
built.** The amendment moved the reference set, and C2's own logic applies: a change to
the counts means the previous pass no longer proves anything. A completeness verdict
returned against the old spec — delivered before the amendment, or by a subagent that
was still running when it opened — proves the old coverage, and nothing else.

---

## When the human stops the run

`SKILL.md` carries the procedure. What this mode owes it is the step called **the work in
flight**.

**The amendment needs nothing done to it.** It lives in the workspace, outside git, so no
reset, clean or stage can reach it — the same protection a plan has, and for the same
reason. **Nothing is spared, because nothing is exposed.**

**What is in flight is the other half**: an attempt still open — an implementer that
stopped `blocked`, or one you parked at the mode's entry — often with half-written code
in the tree, and `SKILL.md`'s call to `stop.sh` needs it named:

```sh
<workspace>/prompts/common/stop.sh pause <lot> <N> <K>               an attempt was in flight — blocked or parked
<workspace>/prompts/common/stop.sh abort <lot> <N> <K>               the same, aborting — before A4
<workspace>/prompts/common/stop.sh abort <lot> <N> <K> <spec path>   the same, during A4
<workspace>/prompts/common/stop.sh pause                             nothing was in flight
<workspace>/prompts/common/stop.sh abort                             the same, aborting — before A4
<workspace>/prompts/common/stop.sh abort <spec path>                 the same, during A4
```

**During A4 the fixer's consolidation sits in the living spec — tracked, dirty,
uncommitted.** Name the spec path in the abort — **beside the triplet when an attempt
sits parked through A4, alone when nothing is in flight**; this is the one mode where
the two states coexist. It is the dirty state this mode vouches for: spared, it stays
out of the attempt's preserve commit — that commit is the attempt's, and the spec is
the mode's — the reset puts the file back to its last commit, and a bare abort refuses
a tree it cannot account for.

| | |
|---|---|
| **Pause** | the amendment stays where it is, and the attempt — blocked or parked alike — is preserved on its `try-<K>` ref. **The resume routes on the boundary the journal names — the table below** — and *Going back* then has no live implementer: whatever its row, the restart is a fresh attempt, whose launch message's two facts say what the pause and the amendment each did. |
| **Abort** | the amendment stays too — **unfinished and uncommitted before `amendment.committed`, landed after it: say which, the journal knows.** The attempt leaves the tree and the branch — named in the call, preserved on its `try-<K>` ref like a pause. **Say both in the report**, with the amendment's path — an unfinished amendment nobody flags is worse than none, and a landed one reported as uncommitted invites a commit that does not repeat. |

**A verifier's tree copy inherited from the parked pass outlives the subagent** —
`verify-close.sh` never ran on it, and this mode's stop is now the only one that can
reach it. `git worktree list` shows it, at
`<repo>/.superpowers/bwr/tmp/bwr-verify-<run>-<report file name>/w`;
close it with `verify-close.sh <that report file name>` — **after the stop's wait
step**: the abandoned verifier is your own call, it can still be writing in that copy,
and the wait is what makes the force-remove reach a dead directory, never a live one.

**An inherited construction diagnostic's worktree survives the same way.** On a pause
it rides through, as construction says — its path is rebuilt from the lot, the task
and the attempt. **On an abort, close it**: `diagnostic-close.sh <lot> <N> <K>`, after
the same wait — nothing after the abort comes back for it.

**A pause takes the fixer with it** — the stop retires it `cancelled`: a fixer between
dispatches is an unsettled assignment, whatever it already applied. At the resume,
**when an amendment is open and written** — the journal's last `amendment.opened` has
its `amendment.written` and no `amendment.committed` after it — create a fresh fixer
exactly as A2's *Create the fixer* says: the checkpoint's two provider questions again —
they are
new children — the same prompt and annotations — **created `idle`, like the original:
its first assignment may still be a sweep away** — and `session-started` for it. **But
no second `amendment.opened`**: the amendment is already open, and the journal already
says so. The new fixer inherits the decisions log, as every replacement fixer does, and
the boundary table below decides its first assignment.

**The resume lands on the boundary the journal names — read inside the current
amendment's slice.** The journal is append-only across the whole feature: every kind
below also exists for earlier amendments, permanently. **The slice begins at the
journal's LAST `amendment.opened` line, and every test below reads nothing before
it** — "absent" always means absent since that line. A slice that carries its
`amendment.committed` is a landed amendment, never an open one.

Before consuming those boundaries after a pause, compaction or takeover, run
`progress.py amendment-state-check`. It revalidates every opening ordinal and origin,
written-document identity, reach receipt, consolidation verdict and committed terminal.
An invalid historical boundary blocks resume. Do not route from its kind alone.

Before a ready direct R or grouped batch opens an amendment, and before A4 writes one of
their terminals, apply `SKILL.md`'s run-wide authority-quiescence predicate. An unfinished
boundary for another owner wins first. Once this amendment commits, its accepted direct
routes write their terminals before any new ordinary conflict opening. The conflict and
breach lifecycle events remain able to complete their own state.

- **No amendment is open** — no `amendment.opened` at all, or the last one is followed
  by its `amendment.committed`: the pause fell in A1 of a NEW amendment — no document,
  no directory, no fixer exists, and none is created. **First read the ruling and the
  stopping point:** an identified single ruling with `ruling.ready` that already orders
  the amendment, or a ready R2.4
  batch with current unapplied `amendment` routes in its latest complete actions,
  run-wide conflict-resolution and global recheck state, goes to A1's durable first
  gesture, with no question repeated. The ready batch opens one grouped amendment for all
  active current-owner routes and carries every external active answer as preservation.
  Only an unidentified or unsettled single decision resumes the discussion with the human. *The one
  neighbour it can look like: a landed amendment
  whose deferred tail is still owed — that is A4's committed branch below, and the
  stopping point plus the tail's own notes (a restart's `attempt.failed`, a voided
  pass's close and fresh opening) say which of the two you are reading.*
- **The current `amendment.opened` data carries `origin:"product-review"`, with no
  `pass.closed {"voided":true}` after the opening** — the human already ordered the
  amendment, and its void was cut. Do not return to A1, do not wake a lens, and do not
  write the amendment yet. Finish the void through *What stops, and what does not*'s
  idempotent reconciliation. Once its close lands, continue with the next row.
- **The current slice has `amendment.opened` but no matching `amendment.written`** — A2
  was cut during authoring. Resume A2 for **the same amendment number and return
  address**. The existing document may be partial: finish or rewrite it, ensure its
  report directory exists, then write `amendment.written`. Create no fixer and launch no
  sweep before that line. Never allocate another `<N>`.
- **A current direct `amendment-fixer` R generation has no matching owner-linked
  `fixer.dispatched`** — publish that assignment from its exact authority artifact, send
  it to the amendment fixer, and continue through its accepted return and fresh sweep.
  With the dispatch present and no current-generation `ruling.applied`, the ordinary
  fixer/sweep rows own it. With the terminal present, never dispatch or terminalize it
  again.
- **The amendment is written and a sweep was walking or had not started** — no accepted
  `sweep.reported` exists in the slice: move a partial report aside when one exists, then
  launch a fresh sweep at the next number — sweep 1 when none has run.
- **A sweep is accepted, with places to handle, and no `fixer.returned` since**: the
  recreated fixer goes `working` and receives that sweep's findings — read from its
  report file, never from memory.
- **A fixer return is accepted and no sweep followed** — `fixer.returned` is the last
  word of the loop: launch the fresh sweep, next number. A correction has a reach of
  its own.
- **The last sweep closed clean** — frontier closed, nothing to handle, block
  complete: **A4 is owed, and its own boundaries are read from the journal — never
  replayed.**
  - `amendment.committed` present — **in this amendment's slice, like every test
    here**: an earlier amendment's commit sits before the slice and proves nothing —
    → **the commit is done and does not repeat**: what remains is the close's tail —
    every missing grouped-batch `ruling.applied` for the exact members and generation
    frozen by the opening, and every missing identified-single `ruling.applied` for its
    latest active amendment route and exact authority generation,
    the fixer retired, and *Going back*'s
    deferred restart, routed on the return address in `amendment.opened` and on the exit
    door's `ruling` when that branch fired.
  - No `amendment.committed`, and the return address names an ended attempt whose
    `attempt.failed` note is **absent** since the amendment opened → nothing of A4
    has run: **from its first step** — settle the tree, then consolidate.
  - **Settled means every gesture of step 1, not the first one**: the
    `attempt.failed` note proves the preserve, and on a `C3.9d` classification —
    the note's own data says which — the rewind that had to follow proves itself
    with its `rewind.done` note. `attempt.failed` carrying `C3.9d` with no
    `rewind.done` after it → **resume at the rewind**, its own exact call, then
    consolidate. Its prepared re-land boundary distinguishes a still-staged commit
    from the exact commit already at `HEAD`, so neither the reset nor a successful
    re-land commit repeats.
  - Step 1 settled — or nothing was in flight — and **no `fixer.returned` follows
    the clean sweep's `sweep.reported` line** → the tree is
    settled and the consolidation is owed: dispatch it to the recreated fixer. **A
    half-consolidated document is safe to dispatch over**: the assignment is a target
    state, never a delta, and the checker diffs the result against the base commit
    either way.
  - **A `fixer.returned` follows the clean sweep's line, with no consolidation domain
    spend after that return** — that ordering makes it A4's return, whether the first
    consolidation or a discrepancy correction — → update the status line when this is
    the first consolidation, allocate the next logical round, open its checker bracket,
    then write its one domain spend.
  - **The latest consolidation domain spend has no matching
    `verdict.consumed` for its round** → its actionable result was lost before it became
    durable. Relaunch the same checker under the same round and a fresh bracket, **with
    no new domain spend**. Then record and route the regenerated verdict.
  - **The latest consolidation verdict is consumed as `exact`** → the check is closed
    and never repeats. The status line is already inside the checked bytes. Resume at the
    commit only.
  - **The latest consolidation verdict consumed discrepancies, round 1 or 2** → its
    exact text is the durable assignment. No `fixer.dispatched` after it: write that
    dispatch note and send it. A dispatch with no `fixer.returned` still owes that fixer
    return; recreate the fixer after a pause and replay the exact durable assignment.
    The accepted return then reaches the first row and allocates the next round.
  - **Round 3 consumed discrepancies** → no fixer dispatch and no fourth round. Take the
    exact durable entries to the human through the normal escalation route. A round 3
    spend without a consumed verdict matches the regeneration row above, not this exit.

  **Step 1 is never replayed past its notes.** A repeated `attempt-failed.sh` or
  `rewind.sh` meets this workflow's own consolidation sitting in the tree and refuses
  it as foreign work — that refusal is the symptom of replaying a settled boundary,
  never a state to take to the human.

---

## Who runs on what

| Actor | Kind | Level |
|---|---|---|
| the reach sweep, one per round | session | preset `Reviewer` |
| the fixer | session | preset `Fixer` |
| the consolidation check | **subagent** | strong / medium |

---

## Red flags

| What you are telling yourself | The reality |
|---|---|
| "No lot has built this part, but I'll write an amendment anyway" | Then edit the spec. An amendment exists because something was already built against the old text. |
| "The sweep found the three obvious places, that will do" | It found hop 1. The defect lives at hop 3, in what loses its purpose without ever naming the thing you removed. |
| "This amendment is big, it can't be an amendment" | Size is not the criterion. Thirty places, all handled, closed at hop three is an amendment. |
| "The frontier is still growing but I can see the end" | You cannot. Report the counts and let the human decide. |
| "The sweep closed, the fix is small, I'll apply it myself" | The author defends its own text. That is why the fixer exists. |
| "The consolidation found two discrepancies, but they are cosmetic" | A validated document does not get improved on the way through. Back to the fixer, then a fresh checker. |
| "The sweep found nothing, I don't need a fixer" | It still carries the consolidation. It is created with the amendment, every time. |
| "I'll commit everything, the task is nearly done anyway" | Explicit paths only. Unreviewed code in an amendment commit is the one mistake this step exists to prevent. |
| "The spec is updated, the implementer can carry on" | Only if the amendment leaves its task's mandate intact. Otherwise its design was written against a contract that no longer holds. |
| "This place in the spec is affected but the answer is obvious" | If it changes what a user lives with, it is a DECISION, however obvious it looks from here. |
| "We escalated once already, I'll settle this one" | Escalation is the cheap path. A product choice made here surfaces when the human meets the built thing. |
