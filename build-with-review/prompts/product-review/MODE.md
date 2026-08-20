# MODE PRODUCT REVIEW

**This file governs review.** Everything you need is here, in `<workspace>/SKILL.md`, and in
the files this one names.

Construction is done: every task is green, the whole suite passes. **Now the product
gets judged** — not the plan, not the tasks, the thing that was built. What comes out
is findings, and a finding either becomes work in a new lot or is closed with evidence.

**You produce no code here, and neither does anyone you launch.** Reviewers read. The
work that answers them happens back in CONSTRUCTION.

---

## Before you start

You need, in hand:

- **the lot is finished** — every task has its git ref, the tree is clean, the gate is
  green
- **the current spec** — the living file, not the version this lot was built against
- **every plan of the subject** — the root lot's, and each sub-lot's if there are any
- the **workspace**, the **concurrency cap**, the **provider**

**No technical noise reaches this mode.** The gate is green, so nothing here is about
an import that does not resolve, a command that fails, or a name that does not exist.
If a reviewer reports one of those, something went wrong upstream — say so and check
the gate.

---

## R1 — The product review

**The subject is one lot and everything done for it. The reading is not limited to it.**

`lot-2`, `lot-2.1` and `lot-2.2` are **one subject**: what lot 2 had to deliver. Review
a sub-lot alone and you learn whether the corrections landed, and nothing about whether
the lot now does what it owed — a fix that breaks what its parent delivered would pass
unseen.

**One pass follows each lot built, and every pass judges the whole subject.** Reviewing
`lot-2.1` is the second pass over `lot-2`. All of them write into
`reports/product-review/lot-2/`, each file named for the lot that had just been built.

That distinction is the whole design of this mode:

- **the subject is one lot**, because the earlier ones had their own review, and because
  the spec decisions of later lots are legitimately absent — a reviewer told to judge
  "the whole spec" would report three quarters of it as missing after lot 1;
- **the reading is the whole product**, because a regression lives outside the lot by
  definition, and because a lot that closes a door a later lot needs is only visible to
  someone reading the entire spec against real code.

Against the **current** spec, every time — not the version this lot was built against.

**R1 always runs to completion before anything is acted on.** You never stop a pass
half-way because something looks serious. Whatever it had not reached would never be
reached at all.

**A finding in earlier code is legitimate** and it is not a reason to go back. It
becomes a task in the sub-lot, like any other: the code is one tree, not a stack of
lots. If a pass produces several of them, say so to the human — that is a signal about
the review of the lot they came from, not about this one.

### R1.1 · The five lenses

**Five sessions, one per lens.** Each reads the product a different way — they are ways
of reading, not territories, and they overlap on purpose.

| Lens | `bwr.mandate` | Prompt, under `<workspace>/prompts/product-review/` | Preset |
|---|---|---|---|
| **where nobody has looked** | `unlooked` | `lens-unlooked.md` | `Reviewer` |
| **the user's experience** | `user` | `lens-user.md` | `Reviewer` |
| **by meaning, not by string** | `meaning` | `lens-meaning.md` | `ReviewerMedium` |
| **internal quality** | `quality` | `lens-quality.md` | `Reviewer` |
| **coverage** | `coverage` | `lens-coverage.md` | `ReviewerMedium` |

**Those five slugs are fixed.** Never invent a variant — they are how a pass is found
again afterwards.

**Launch them in that order.** It is roughly longest first: `unlooked` has no list and
no natural stopping point, `coverage` is a bounded count. When the cap does not allow
five at once, the ones still waiting are the short ones, and they slot in as the others
finish.

**Create `<workspace>/reports/product-review/<root lot>/` before you launch anything.** A
reviewer told to write into a directory that does not exist fails on its very last action,
with all its work already done.

```
progress.py note pass.opened --data \
  '{"built":"<built lot>","commit":"<sha>","gate":"<accepted gate op>"}'
```

The gate operation must prove this exact reviewed commit **and its source identity**. A
last accepted implementer commit uses its task-final operation, whose lot must equal
`built`. For a first pass, `progress.py` also reads the current and committed plan's
exact `Task 1..T` manifest, consumes every stable task result through `T`, requires this
gate to belong to task `T`, and consumes the matching `lot.built` boundary. A controller
baseline can open only after the prior pass for this same built lot
closed `voided:true`: use owner `amendment/<N>/<commit>` for the exact committed amendment,
or `plan/<built lot>/<commit>` for its one exact C2 plan-only successor. A first pass can
never consume a baseline. `progress.py` also refuses a second opening while the prior
pass is open. Product review never substitutes semantic lenses for the technical gate.

```
product-review/lot-1/
├── lot-1-unlooked.md · lot-1-user.md · lot-1-meaning.md · lot-1-quality.md
│   lot-1-coverage.md           one per lens, five of them
├── lot-1-decision-batch-1-source.md · lot-1-decision-batch-1-actions.md
│   lot-1-decision-batch-1-recheck-<sha>.md
│                                rechecks exist only after in-place batch edits
├── lot-1-confirmed.md          → becomes the Covers: of lot-1.1
├── lot-1.1-unlooked.md · …
├── lot-1.1-confirmed.md        → becomes the Covers: of lot-1.2
└── lot-1.2-unlooked.md · …     no confirmed: that pass found nothing, the lot is done
```

Run-wide conflict pairs live outside one pass's report tree:
`<workspace>/reports/answers/B1-conflict-1-{source,resolution}.md`. They can name answers
from other open or closed batches and identified individual rulings.

For each lens, `mcp__twicc__create_session`, one call carrying everything:

- the preset above, the provider the human chose, **question widget disabled**
- title `- Review: <lens> (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=reviewer` · `bwr.mode=product-review` ·
  `bwr.feature=<feature>` · `bwr.lot=<lot>` · `bwr.mandate=<its slug from the table>` ·
  `bwr.status=working`

Then, per lens: `progress.py session-started <id>`.

The message gives it: **the workspace path**, the prompt to read first
(`<workspace>/prompts/product-review/<its lens>.md`), **the path to the current spec**,
its one optional additional prompt
`<workspace>/additional-prompts/product-review/lens-<slug>.md`,
**the path to every plan of the subject** — the root lot's and each sub-lot's, since
`Covers:` is read from all of them — **which lot is the subject**, **the two refs
below**, and **the path its report goes to** —
`<workspace>/reports/product-review/<root lot>/<built lot>-<slug>.md`.
Also give it `<workspace>/additional-prompts/global.md`. Tell it to run `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`, then `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/product-review/lens-<slug>.md
<workspace>/additional-prompts/product-review/lens-<slug>.md` after its official prompts.

Also give it its private, append-only risk-filtered history:
`<workspace>/reports/product-review/<root lot>/<slug>-risk-filtered.md`, with occurrence
label `<built lot>`. Every later pass for this root lot gives the same path. Its loss is
accepted. It never enters a receipt, the journal, or the public report.

**Two refs, and they are not interchangeable:**

| | |
|---|---|
| **the base** — `refs/bwr/<run>/<root lot>/task-0` | where the subject started, so a lens can see what it added |
| **the reviewed commit** — the SHA of `HEAD` when you launch the pass | **what everything is judged and verified against** |

Pass the **SHA**, not `HEAD`. A pass must mean the same thing when its findings are
verified an hour later.

**Name what the subject owed**, so five reviewers do not reconstruct it five times:

- the **`Covers:`** line of the root lot's plan — the spec decisions it carries;
- on a sub-lot pass, the `Covers:` of every sub-lot too. **Each of those lines names the
  confirmed file that opened its own sub-lot**, and that is where its findings live —
  `lot-2.1`'s `Covers:` points at `lot-2-confirmed.md`, because that is the pass whose
  findings it was opened to fix.

**Never build that path from the lot you have just built.** `lot-2.1-confirmed.md` is what
**this** pass will write if anything survives it; it does not exist yet, and telling a
reviewer to read it hands it a file nobody has written. The `Covers:` line is the only
place that path is stated, and it is stated by whoever opened the sub-lot.

**`<built lot>` is the lot that was just built** — `lot-2` on the first pass, `lot-2.1`
on the next. **One pass follows each lot built**, so that name identifies the pass on
its own and says what had just been made. Nothing is ever overwritten, and you keep
what was already disproved.

**On a later pass**, add one line: what changed since the previous pass. **A hint, not
a perimeter** — see the rule at the end of R2.

### R1.2 · What comes back

Each session returns a report. As each one arrives, **audit its fixed lens-specific
completion block before anything else**: a missing, added, omitted, reordered or
unticked item goes back to the
lens — **once, journaled as it goes** (`progress.py note bound.spent --mandate <slug>
--text "malformed block returned - lens <its session id>"`); a second return still
malformed takes the silent lens's route below — stop, retire `failed`, free the path,
relaunch fresh, and the relaunch-once stable-blocker rule holds. **An unticked box with a reason is not
settled either.** Lift the reason if you can — the lens is alive, and finishing its own
reading is always cheaper than replacing it. When you cannot, **treat it as a silent
lens**: stop its process, retire it `failed`, move its report aside, relaunch fresh. A
reading a lens honestly did not do is still a reading nobody did, **and no later pass
exists to do it** — this mode has no next round that re-covers everything. **And
relaunch once**: a replacement returning the same reason is a stable blocker, not
inattention — stop replacing and take it to the human; `SKILL.md`'s audit duty carries
the gesture and its journal line. The pass waits on their answer.

Then go to **R2.1** for that report — **do not wait for the others.**

**The receipt follows the audit, never precedes it** — `report.received` says accepted:
a report whose block is still being repaired has not arrived yet, however present its
file.

```
progress.py note report.received --mandate <slug> --data '{"critical":<N>,"important":<N>,"minor":<N>,"decision":<N>}'
```

The script reads the real report, audits the exact fixed block from that lens prompt,
parses every exact `###` finding and its five fixed fields, requires the four typed counts
to equal those findings, and freezes the current pass commit, gate operation and report
SHA-256 into the receipt. The counts do not substitute for that duty account. A changed report is a new generation
and needs a new receipt before another verifier can open.

The four classes are disjoint. CRITICAL, IMPORTANT and MINOR are correction severities.
A DECISION uses the exact `Severity: DECISION` line and increments only `decision`.

A session that **goes quiet** is handled like any other: the watchdog reports no writes,
you send one message asking where it stands — journaled as you send it,
`progress.py note bound.spent --mandate <slug> --text "nudged the lens <its session id>"`,
so a compaction cannot make the next silence a first one. **The id is the generation**:
a replacement lens shares the mandate and the report path, never the nudge — count only
the lines naming THIS session — and on the second tick or on no answer you
**stop its process, then retire it `failed`** — `SKILL.md` says why that order, and here
the cost is precise: **the two of them write to the same report path**, and a lens that
wakes late overwrites its replacement's work with an older reading.

**Relaunch it as a fresh session** — a pass with four lenses out of five is not a pass,
and its missing report is exactly where a defect would have been.

**And free its report path first** — the silent-child rule in `SKILL.md`'s *Retirement*
section carries the gesture: `<built lot>-<slug>.md` moves to
`<built lot>-<slug>-failed.md` before the replacement exists.

When all five reports are verified — **their blocks complete: every box ticked, lifted,
or its lens replaced** — and nothing survived, first check every `decision.batch.ready`
that has no `decision.batch.closed`. A batch from a pass voided by an amendment can still
carry corrections that the new lenses did not rediscover. If one exists, go through
R2.4's pending-batch merge and R2.5 even though the fresh reports were clean.

**Only when the current pass and every open decision batch have nothing left is the lot
done.** Close the pass first — every pass that opened is closed in the journal, the clean
ones included, or a takeover reads an open pass and re-runs work that was settled:

`progress.py` admits this boundary only for the latest pass generation. All five exact
mandates need a current settled receipt, a real report and a completed finding-verifier
bracket. A clean close has no allocation and no unresolved direct or batch work.

```
progress.py note pass.closed --data '{"confirmed":0}'
```

Then go to *Leaving review*.

---

## R2 — Adjudication

### R2.1 · Verify each report, as it arrives

**One verifier subagent per report, always.** No threshold, no exception for a report
with two findings.

**a light model, effort medium**, prompt
**`<workspace>/prompts/product-review/verifier.md`**. Give it that path, the workspace
path, its one optional additional prompt
`<workspace>/additional-prompts/product-review/verifier.md`, the path to the report, the
path to the spec, and **the reviewed commit** — the same SHA the lenses were given,
never the base.
Also give it `<workspace>/additional-prompts/global.md`. Tell it to run `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`, then `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/product-review/verifier.md
<workspace>/additional-prompts/product-review/verifier.md` after its official prompt.

It returns, per finding: **confirmed**, **disproved with what it observed**, or
**malformed**.

```
progress.py subagent-started finding-verifier --mandate <slug> \
  --data '{"pass_commit":"<receipt pass_commit>","pass_gate":"<receipt pass_gate>","report_sha256":"<receipt report_sha256>"}'
progress.py subagent-ended finding-verifier --mandate <slug> \
  --data '{"pass_commit":"<same pass_commit>","pass_gate":"<same pass_gate>","report_sha256":"<same report_sha256>","confirmed":<N>,"disproved":<N>,"malformed":<N>,"claims":[{"id":"F1","kind":"correction","verdict":"confirmed"},{"id":"F2","kind":"decision","verdict":"disproved"}]}'
```

`claims` contains every finding in report order. Its local IDs are exactly `F1..F<N>`.
Its three verdict totals equal the three counts above, and its `decision` count equals
the report receipt. The full durable source identity is `<mandate>/F<N>`, such as
`meaning/F2`. These identities survive cross-report dedupe; they are not the later IDs
of the confirmed file or a decision batch.

The bracket consumes the exact accepted report generation. The verifier then opens one
detached copy through `verify-open.sh`, at `pass_commit`, and uses it for every drafted
test, exhibition, absence search and DECISION spec check. The script refuses another
commit or report generation before it creates or removes a worktree.

**Launch it the moment the report arrives.** A malformed finding has to go back while
its reviewer is still alive.

**Set that reviewer `idle` as you launch its verifier.** It has stopped working and it is
not waiting on an answer — it is parked, and it may get work again if a finding comes
back. Leave it `working` and the watchdog flags it for silence it is entitled to. Set it
back to `working` just before you send it anything to restate.

### R2.2 · Act on the verdicts

| Verdict | What you do |
|---|---|
| **confirmed** | keep it. It becomes a task of the sub-lot this pass will open. |
| **disproved** | close it, with what the verifier observed — `progress.py note decision.refuted --text-file "$JOURNAL_TEXT_FILE"`. It stays closed unless an R2.4 source later gives it a stable batch ID and that batch's completed recheck records a newer verdict. |
| **malformed** | send it back to its reviewer, **once**. If it comes back still vague, close it. |

**What comes back restated is verified again, by a fresh verifier.** A restatement is a
new claim: the verdict that sent it back proved only that the old wording could not be
checked, and nobody has established the new one — so it goes through a verifier before
anything keeps it. **Journal the return as you send it** — `progress.py note bound.spent
--mandate <slug> --text-file "$JOURNAL_TEXT_FILE"` — the file contains the exact fixed
prefix, finding title and lens id. After a compaction that note is the only thing that says the one return was
used, **and the id is the generation that used it**: a voided pass relaunches the
mandate fresh, a replaced lens writes a fresh report, and neither inherits the old
producer's spent return — count only the lines naming THIS session. *Still vague* — seen by you, or returned `malformed` by that
verifier — closes it: it was sent back once already. **Settled means verified** —
confirmed, disproved, or closed — never merely returned. **And when the reprise
settles, record the fresh receipt** — a new `report.received` for the mandate, its
counts as they now stand: the pause table reads generations, and the last line must
say the path is settled again.

**Retire a reviewer only once its whole report is settled**, reprise included. It holds
a concurrency slot until then — count it before launching anything else. Park it while its
verifier runs:

```
progress.py session-status <id> idle
progress.py session-retired <id> done --archive --hide
```

### R2.3 · What you may judge, and what you may not

| | | |
|---|---|---|
| **Its form** | precise, situated, no value adjective? | vague → **sent back once** |
| **Its facts** | do the cited lines say what it says? | false → **disproved** |
| **Its value** | is it worth fixing? | **never** |

**Judge the value and you become a reviewer of the reviewer** — and your verdict is
exactly as arguable as the one it replaces. A well-formed, true finding is kept **even
when you find it minor**.

If a report is flooded with trivia, the problem is the report, not thirty independent
findings: **send the whole report back, once**, with the calibration — and journal the
spend as you send it: `progress.py note bound.spent --mandate <slug> --text "report
returned whole for recalibration - lens <its session id>"` — the id scopes the one
return to its generation, exactly as for a malformed finding. **What comes back
is a new report, and the first verifier's verdicts go with the one they described** —
nothing they confirmed is kept. Record its arrival and verify it exactly as a first
arrival: R1.2's line, R2.1's fresh verifier. **Still flooded after that one return, the
lens is the problem, not the report**: stop its process, retire it `failed`, move the
report aside, and relaunch the reading fresh — the silent lens's route, and the same
outcome as the authorless case. A single claim closes after its one return; a whole
reading is never closed, so it is redone.

One refutation stays yours: **refuting from the spec, with the citation.**

### R2.4 · Once all five reports are settled

1. **Dedupe across reports.** Two lenses see the same defect from two angles: that is
   one finding. Keep every `<mandate>/F<N>` source identity on its one survivor. A
   unique source has one survivor; duplicates name the same survivor. This needs the
   findings only, never the code, and it cannot be delegated.
2. **If no DECISION survived, do not create a decision batch.** Merge the pass's
   confirmed corrections with the still-open decision batches described below, then go
   to R2.5.
3. **If at least one DECISION survived, freeze the whole verified set before asking or
   routing anything.** The set includes every well-formed confirmed **and refuted**
   claim, not only the actionable items. A malformed claim closed without a verdict has
   no truth state to reactivate. One in-place answer can change the passage that refuted
   a claim, and a later amendment can void the reports that first held it.

   Allocate `<B>` once, one more than the highest `decision.batch.opened` number in the
   run, then publish its identity before writing an artifact:

   ```sh
   progress.py note decision.batch.opened --data '{"batch":<B>,"built":"<built lot>"}'
   ```

   Write
   `<workspace>/reports/product-review/<root lot>/<built lot>-decision-batch-<B>-source.md`.
   It contains every verified item in deterministic report-and-finding order after
   dedupe:

   - stable IDs `F1`, `F2`, … for every non-DECISION claim, confirmed or refuted;
   - stable IDs `D1`, `D2`, … for every DECISION claim, confirmed or refuted;
   - the complete claim, source reports and proof for every item;
   - its initial verifier verdict and exact observation — a refuted item has no route,
     but it keeps its identity;
   - for each DECISION, the question and option IDs exactly as the human will receive
     them if it becomes live, each with its user-visible consequence;
   - whether the touched part is already built, which is a fact about the current lot,
     not a route chosen from memory later.

   When the source file is whole:

   ```sh
   progress.py note decision.batch.sourced \
     --data '{"batch":<B>,"decisions":["D1","D2"],"items":[{"id":"F1","verdict":"confirmed"},{"id":"D1","verdict":"confirmed"},{"id":"D2","verdict":"refuted"}]}' \
     --text "<the source file path>"
   ```

   `decisions` contains every stable `D<N>` identity in the immutable source, including
   a DECISION that the current spec initially refuted. It has no duplicates. This index
   lets a later bound commit prove mechanically that its named D belongs to this batch.
   `items` contains every `F<N>` and `D<N>` exactly once, with the same initial
   `confirmed` or `refuted` verdict as the immutable source. Both ordinal sequences are
   contiguous. This structured index lets a later batch close prove that every source
   item was consumed without trying to interpret Markdown.

   No question is sent before this line. An opened batch without `sourced` is an
   interrupted source write: regenerate every lost verifier verdict from the durable
   reports, redo the dedupe, rewrite the same `<B>` source in full, then write the line.
   Never allocate another batch and never trust the partial file.
4. **Send every currently confirmed DECISION in that source to the human as one
   message.** A refuted DECISION stays silent unless a later recheck reactivates it. Each
   option says what a user would see, never what it costs to build. Then wait.

   The answer also lands as **one journal event**, before any route. The data binds every
   stable ID to its chosen option and its mechanical route. The text carries every exact
   human answer, headed by the same IDs. Use a quoted heredoc when the text needs it.

   ```sh
   progress.py note decision.batch.settled \
     --data '{"batch":<B>,"answers":[{"id":"D1","choice":"O2","route":"amendment"},{"id":"D2","choice":"other","route":"sublot"}]}' \
     --text-file "$JOURNAL_TEXT_FILE"
   ```

   The route vocabulary is closed here: `closed`, `sublot`, `spec-in-place`, or
   `amendment`. This single event replaces the individual `ruling` notes for an R2.4
   batch. A partial list is forbidden: the line carries every answer from the one message
   or none. A later supplemental message has its own atomic line below.
5. **Make the route artifact.** Write
   `<workspace>/reports/product-review/<root lot>/<built lot>-decision-batch-<B>-actions.md`
   in full from the immutable source plus `decision.batch.settled`, **and from the
   run-wide product-answer state**. Reconstruct every earlier identified `ruling`, batch
   settlement or supplement, and ready conflict resolution in journal order. A closed
   batch and an applied answer stay in this set.

   The artifact repeats every local item's proof and initial verdict. Its answered local
   DECISIONs have full identities `B<B>/D<N>`, exact answers, current routes and resulting
   correction obligations. It also repeats every earlier `B…/D…` and `R<N>` identity,
   exact effective answer, source authority, active/superseded status and current
   obligation. Refuted local claims remain inactive but present.

   For every current `spec-in-place` or `amendment` answer, include the exact proposed
   contract change, every spec passage it may alter, and its compatibility result against
   **every active product answer**, not only this batch. No spec byte changes and no
   amendment opens during this comparison. A built-part ruling that changes the spec
   always creates an implementation obligation: committing its amendment applies the
   contract, not the code. Routes in this first artifact are the starting global state:
   a completed recheck or conflict resolution can replace them.

   ```sh
   progress.py note decision.batch.ready --data '{"batch":<B>}' --text "<the actions file path>"
   ```

   No route runs before `ready`. A settled batch without `ready` means the actions file
   may be partial: rewrite it from the source and the one settled event, then write the
   line. Never ask the human again.
6. **Consume one ready batch as a durable product-answer fixed-point loop.** Its owner is
   `B<B>`. Start from the actions file. Then read every later complete global recheck,
   `ruling.ready` state or conflict resolution in journal order, and apply each later
   settlement or supplement to the state that preceded it. The last complete artifact
   plus every later durable answer is current. Never reconstruct current state from old
   `decision.refuted` notes or memory.

   1. Find the lowest stable active `B<B>/D<N>` owned by this batch whose **current** route is
      `spec-in-place` and whose exact answer is not yet present in the current spec. Apply
      it through the DECISION channel's bound commit only after its exact proposed change
      has been compared with every active product answer in the current complete state.
      If it would erase, qualify or contradict any external or local active answer, no
      spec byte changes: go to step 4 with the fully qualified identities. Otherwise:

      Write `spec.edit.ready` from the exact current complete artifact as `SKILL.md`
      requires. Its owner is `B<B>/D1`, its route is `spec-in-place`, and its state kind
      and reference name this exact actions, supplement, recheck or ready-conflict
      generation. Only then edit the repository spec and call:

      ```sh
      <workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" - <B> <D1>
      ```

      For a conflict-resolved answer, `B<B>/D1` names its stable carrier. The latest complete
      global state before this call names the exact effective answer and conflict authority that
      the commit consumes. The resulting unique `spec.committed.op` binds the following
      recheck to that state; a later conflict cannot retroactively change this commit.

      A later edit can make an earlier answer owned by this batch owed again. In that case the same `B<B>/D<N>`
      re-enters this scan and a new bound commit gets its own `spec.committed.op`. If
      satisfying one answer would make another active answer impossible to preserve, do
      not edit. Go to step 4 with every conflicting stable ID; alternating commits are
      not convergence.
   2. **After every such commit, write one complete global recheck snapshot before
      consuming any result.** Regenerate a fresh verifier verdict for every local `F<N>`
      and `D<N>` in the immutable source against the new spec and reviewed commit, through
      R2.1's fresh finding-verifier bracket. Also check every product-answer identity in
      the state that authorised the commit, including answers from closed batches and
      individual `R<N>` rulings. For each local item write:

      - its stable ID, full claim and previous latest state;
      - `confirmed` or `refuted`, with the verifier's exact observation;
      - for an answered DECISION, its full `B<B>/D<N>` identity, whether it is active or superseded, its exact effective
        answer, the initial, supplemental or conflict generation that currently
        authorises it, and, when active, the route now required: `closed`, `sublot`,
        `spec-in-place` or `amendment`;
      - for an unanswered DECISION, either `refuted` or `answer required`.

      For every external product answer, write its full identity, previous authority,
      active/superseded status, exact effective answer, whether the committed spec still
      carries it, and its current obligation. The snapshot is a complete run-wide
      replacement state, not a batch-local appendix.

      A new verdict on an answered DECISION never erases or revives a human answer. The
      snapshot carries forward every later conflict resolution. It asks a different
      mechanical question: whether each active effective answer now needs no change, a
      sub-lot, another in-place edit or the grouped amendment. A superseded answer stays
      superseded until a later human conflict resolution changes that state.

      The hashed `spec.edit.ready` artifact means the exact named proposal must be
      implemented, and every earlier active answer must still be present. If this
      post-commit recheck says the proposal differs, remains owed, or one earlier answer
      was erased or contradicted, follow `SKILL.md`'s **Bound spec breach recovery**.
      Never route a mismatched payload as an ordinary later obligation. Do not
      retroactively authorise the commit by opening a conflict after it. Restore the last
      authorised spec through its corrective commit, prove the global state restored,
      and only then open this owner's next conflict from the original durable proposal.

      Write the immutable file
      `<workspace>/reports/product-review/<root lot>/<built lot>-decision-batch-<B>-recheck-<full commit sha>.md`.
      It is a **complete replacement state**, not a delta. Then publish it with the exact
      bound commit's identity:

      ```sh
      progress.py note decision.recheck.completed \
        --data '{"batch":<B>,"decision":"D1","sha":"<sha>","commit_op":"<spec.committed op>","accepted":true,"missing":[],"artifact_sha256":"<recheck artifact sha256>","confirmed":<N>,"refuted":<N>,"unanswered":<N>,"items":[{"id":"F1","verdict":"confirmed"},{"id":"D1","verdict":"confirmed"},{"id":"D2","verdict":"refuted"}],"actions":[{"answer":"B<B>/D1","status":"active","route":"spec-in-place"}]}' \
        --text "<the recheck file path>"
      ```

      `items` contains every immutable source item exactly once and is the structured
      latest-verdict index. `actions` contains every answered current-owner
      `B<B>/D<N>` exactly once, including
      superseded members, with its current status and route. This is the structured route
      index for a later `spec.edit.ready`; the hashed artifact remains the full state.
      `accepted:true` requires `missing:[]`. A mismatched proposal or missing active
      authority writes `accepted:false` and every absent fully qualified identity. It
      never replaces the current route state. `progress.py` authenticates the exact bound
      commit, its current pre-commit generation, the complete item and action sets, and
      the artifact bytes before it appends either result.

      A partial file proves nothing. A `spec.committed` with no matching
      `decision.recheck.completed` for its `op` regenerates every lost verdict, rewrites
      that same SHA-named file and publishes the line. Once the line exists, later
      reconstruction reads that snapshot and never reapplies an older refutation over
      it.
   3. **Settle every newly live unanswered DECISION before another route runs.** Send all
      `answer required` items in this one snapshot to the human as one message. Record
      the whole answer group atomically:

      ```sh
      progress.py note decision.batch.supplemented \
        --data '{"batch":<B>,"after_op":"<spec.committed op>","answers":[{"id":"D3","choice":"O1","route":"amendment"}]}' \
        --text-file "$JOURNAL_TEXT_FILE"
      ```

      This is the same batch: only a claim already frozen in its source and reactivated
      by this batch's own in-place edit can enter the supplement. An item with an initial
      or supplemental answer is never asked its original question again; its standing
      answer is re-routed if a later snapshot changes what the current spec or code now
      owes. A later conflict question can still revise that answer under the boundary
      below. Its product-answer identity is `B<B>/D<N>` like an initial answer, and the
      supplement joins the run-wide state before another route runs.
   4. **Resolve incompatible standing answers as one durable conflict generation.**
      This generation's owner is `B<B>`; conflicting answers can belong to any earlier
      batch or identified individual ruling.
      Allocate `<C>` once, one more than the highest `decision.conflict.opened` number
      for this owner. Publish its identity, the durable state boundary that exposed it,
      and every conflicting fully qualified identity before writing an artifact or asking the human:

      ```sh
      progress.py note decision.conflict.opened \
        --data '{"owner":"B<B>","conflict":<C>,"state_kind":"decision.recheck.completed","state_ref":"<commit op>","ids":["B1/D2","B<B>/D1"]}'
      ```

      `state_kind` is `decision.batch.ready`, `decision.recheck.completed`,
      `decision.batch.supplemented`, `ruling.ready`, `decision.conflict.ready` or
      `spec.breach.restored`; `state_ref` is respectively `B<B>`, commit `op`,
      supplement `after_op`, ruling identity, preceding conflict owner/number, or breach
      number. A restored-breach opening also carries that `breach` number. Ensure
      `<workspace>/reports/answers/`
      exists, then write
      `<workspace>/reports/answers/B<B>-conflict-<C>-source.md`
      in full from that exact durable state. It repeats every source item, latest verdict,
      current correction obligation, and active or superseded standing answer. It also
      contains the conflicting IDs and their exact effective answers, the proof that they
      cannot coexist, and the one conflict question with the available user-visible outcomes.

      A breach recheck with `restored:false` uses this same lifecycle. Its opening adds
      `breach:<K>` and `purpose:"restore-baseline"`; `state_kind` is
      `decision.recheck.completed`, and `state_ref` is that recheck's exact `basis_ref`.
      Its IDs include the original owner answer, every authority erased by the bad commit
      and every current missing authority. Its question offers two outcomes: preserve the
      missing active answers through an exact spec repair, or explicitly revise, qualify
      or supersede those authorities. The resolution artifact contains the complete
      repair target or authority state before any byte changes.
      Then publish it:

      ```sh
      progress.py note decision.conflict.sourced \
        --data '{"owner":"B<B>","conflict":<C>}' --text "<the conflict source path>"
      ```

      Only now ask the human. Record the whole resolution atomically. Its `updates` list
      names every affected stable ID; the closed `action` is `keep`, `supersede`,
      `qualify`, `replace` or `reconcile`. Each update also carries its resulting `active`
      or `superseded` status, its current route when active, and the active ID that
      replaces it when superseded. Every ID from the opening appears exactly once; any
      other standing answer the resolution changes appears too. A partial update list is
      forbidden. The text carries the exact human resolution and every resulting
      effective answer:

      ```sh
      progress.py note decision.conflict.settled \
        --data '{"owner":"B<B>","conflict":<C>,"updates":[{"id":"B<B>/D1","action":"replace","status":"active","route":"spec-in-place"},{"id":"B1/D2","action":"supersede","status":"superseded","by":"B<B>/D1"}]}' \
        --text-file "$JOURNAL_TEXT_FILE"
      ```

      This one shape represents either answer superseding the other, a qualification,
      one combined replacement, or an explicit reconciliation that preserves both. A
      combined or qualified replacement uses the owner's lowest active `B<B>/D<N>` as
      its stable carrier and marks every replaced identity as superseded by it. If the
      whole current owner is superseded by an unchanged older answer, no spec edit is
      owed. A preserve-both resolution keeps all member identities active and adds the
      exact reconciliation to the owner's lowest active member. The source and settlement
      retain every original answer as history; only the complete effective state governs later work.

      Write
      `<workspace>/reports/answers/B<B>-conflict-<C>-resolution.md`.
      It is a complete replacement state: every source item and latest verdict; every
      active or superseded answer; every exact effective answer, authority and route;
      and every current correction obligation. Derive it only from the conflict source
      and its one settled event, then publish it:

      ```sh
      progress.py note decision.conflict.ready \
        --data '{"owner":"B<B>","conflict":<C>,"artifact_sha256":"<resolution artifact sha256>","actions":[{"answer":"B<B>/D1","status":"active","route":"spec-in-place"}]}' \
        --text "reports/answers/B<B>-conflict-<C>-resolution.md"
      ```

      `actions` contains every answer owned by the conflict owner exactly once. A
      direct R changed by this resolution can use the same ready artifact as its next
      authority generation; therefore this path is always workspace-relative under
      `reports/`, traverses no symlink and names the complete real file. The recorded
      SHA-256 freezes those exact bytes. `progress.py` refuses a settlement that omits an
      opened identity, an action that contradicts the settlement, or a ready state that
      adds, omits or changes an owner answer. A
      `purpose:"restore-baseline"` generation also adds `effect:"spec-repair"` when its
      target requires the bound repair commit, or `effect:"authority-only"` when the
      unchanged SHA is rechecked.

      No resolving spec edit, terminal line or amendment opens before `ready`. Return to
      step 1 from an ordinary resolution. A `purpose:"restore-baseline"` resolution
      instead returns to `SKILL.md`'s bound-breach branch: perform only its exact repair
      or unchanged-SHA recheck, and do not run the owner's normal route before
      `spec.breach.restored`. If that state or a later recheck exposes another
      incompatibility, open `<C+1>` by the same protocol. Conflict generations never
      overwrite or amend one another.
   5. Return to step 1. Each accepted completed recheck, `ruling.ready` state or conflict
      resolution replaces the effective-answer and route state of every earlier global
      artifact; local claim verdicts still follow this batch's source and rechecks. The
      loop reaches a fixed point only when no local unanswered DECISION is live, **every
      active product answer in the run can coexist**, and no current-owner route is
      `spec-in-place` with its effective answer absent.
   6. **Only at that fixed point record terminal routes.** Write one missing
      `ruling.applied` for each current `closed` answer and each in-place answer now
      present in the spec. Bind an in-place close to the snapshot and current SHA that
      prove the whole active answer set still coexists. When a conflict resolution is
      its current authority, carry that conflict number too:

      ```sh
      progress.py note ruling.applied --data '{"answer":"B<B>/D1","batch":<B>,"decision":"D1","route":"spec-in-place","sha":"<sha>","recheck_op":"<spec.committed op>","conflict":<C>}'
      ```

      Omit `conflict` when the effective answer still comes from the initial or a
      supplemental settlement.

      An external answer is a preservation constraint, not another applied line for this
      batch. A superseded answer needs no `ruling.applied`: its conflict-resolution artifact is
      the durable reason it no longer routes. Keep every current `sublot` answer and
      every currently confirmed `F<N>` as a pending correction. A current refutation is
      inactive because the immutable source or latest complete snapshot proves it, not
      because an older unkeyed note wins.
   7. If one or more active current-owner answers carry route `amendment`, open **one amendment for
      all of them**. `prompts/amendment/MODE.md` reads this batch's source, initial
      settled event, every supplemental answer event, its actions file, every ready
      conflict resolution, every identified product ruling and the latest completed
      global recheck snapshot. The opening carries `<B>`, and its document gives each
      active current-owner amendment decision its own section. Every other active product
      answer, from any open or closed batch or `R<N>`, is a preservation constraint.
      Never open one amendment per decision and never mix another batch's new change into
      this amendment. The opening also carries the complete sorted `members` list and the
      exact `state_kind` / `state_ref` of the latest durable boundary that changed this
      batch's answer state, in the shape defined by `prompts/amendment/MODE.md`. A zero,
      omitted, added, stale or already-opened generation is a mechanical refusal.

   The amendment voids the pass only after the whole batch is durable. Its void moves
   the five lens reports aside; it never moves the batch source, actions, rechecks or
   conflict-resolution artifacts. After the amendment lands, a fresh pass begins,
   but **every ready batch without
   `decision.batch.closed` remains required input**. The fresh pass still completes all
   five R1 readings before it reaches R2.4 and merges that input into R2.5. The batch
   cannot advance the fresh pass by itself, and rediscovery by new lenses is never its
   continuation.

   **You never build against a spec that does not yet say what was decided.** All
   in-place routes finish before the grouped amendment opens. No iteration order can
   change which human answers take effect.

   *A claim refuted before the batch opened keeps its old `decision.refuted` note as
   history. Its source entry and later complete recheck or conflict-resolution artifacts
   are the durable current state.*

### R2.5 · Open the sub-lot

**R2.5 never decides whether human answers coexist.** The run-wide fixed point above
must already prove that before this phase. `Carries:` preserves work provenance; it is not
a product-answer compatibility check.

Build the actionable set before allocating anything. It is the union of:

- the corrections confirmed in this pass;
- every currently confirmed `F<N>` in every `decision.batch.ready` without a matching
  `decision.batch.closed`, using its latest accepted complete recheck or conflict-resolution
  state when one exists;
- every current `sublot` answer and every implementation obligation created by a current
  active built-part ruling in those batches, including supplemental and
  conflict-resolved answers. A current owner's conflict obligation stays here when it
  supersedes or qualifies an answer from an older closed batch.

**A carried item is durable work, not a hint to the new lenses.** Reconstruct the
run-wide product-answer state first, from every identified ruling, batch answer and ready
conflict resolution in journal order. Then reconstruct each open batch's local findings
and work obligations from its source, supplements and last complete recheck — never from
an earlier unkeyed `decision.refuted`. A global conflict-ready supersession stays terminal
unless a later conflict-ready state activates that identity again. A closed batch
contributes active product constraints but no old work item. If a later amendment changed text its proof
depends on, regenerate its verifier verdict against the current spec and reviewed commit.
A disproved carried item closes only through a `decision.refuted` note whose data names
its batch and item:

```sh
progress.py note decision.refuted --data '{"batch":<B>,"item":"F1"}' --text-file "$JOURNAL_TEXT_FILE"
```

That keyed note is later than the batch's last complete state and therefore becomes the
item's latest verdict. Otherwise it stays. Dedupe
the union, but keep every source identity on the surviving entry so one correction can
consume `batch 2/F1`, `batch 3/D2`, and a fresh finding together.

If a later spec-dependent recheck refutes a fresh correction that R2.1 first confirmed,
record each affected report source before allocation:

```sh
progress.py note decision.refuted --data '{"source":"meaning/F2"}' \
  --text-file "$JOURNAL_TEXT_FILE"
```

This keyed close is only for a source that the current pass's verifier index confirmed.
It never replaces the existing batch-keyed refutation. The allocation lists every such
source under `refuted`, so a source cannot disappear between verification and dedupe.

If the union is empty, close the pass with `confirmed:0`, then close every open batch
whose active items now all carry a durable refutation, close, or applied no-correction
route, and whose superseded answers are accounted for by a ready conflict resolution:

```sh
progress.py note pass.closed --data '{"confirmed":0}'
progress.py note decision.batch.closed --data '{"batch":<B>,"outcome":"no-correction"}'
```

Then go to *Leaving review*. A batch close never precedes the pass close that proved no
correction survived.

If anything survives, the corrections become **lot `N.n`** — **`N` the root lot's own
number, `n` one more than the highest sub-lot identity that reached `sublot.opened` for
that root.** The pass over `lot-2` opens `lot-2.1`; the pass over `lot-2.1` opens
`lot-2.2` — never `lot-2.1.1`, the grammar has two levels only, and never a name already
used, whose plan and refs are frozen. Concretely:

1. **Resolve the identity before creating either artifact.** If this pass's slice already
   carries `sublot.allocated`, reuse that exact name and write no second line. Otherwise,
   take one more than the highest `sublot.opened` for the root and allocate it now:

   ```
   progress.py note sublot.allocated \
     --data '{"built":"<built lot>","items":[{"id":"F1","sources":["unlooked/F1","meaning/F2"],"carries":["B2/F1"]},{"id":"F2","sources":[],"carries":["B3/D2"]}],"refuted":["quality/F1"]}' \
     --text "<lot N.n>"
   ```

   This line records a pass-local choice, not an open sub-lot. Once it exists in this
   pass's slice, every retry uses **that exact identity**. It never runs “highest plus
   one” again over a file the interrupted close created itself. Across pass generations,
   only `sublot.opened` consumes the ordinal: an allocation in a voided slice is free for
   the fresh pass to allocate again. Its `items` are also the complete durable dedupe
   account. Each still-confirmed source identity and each carried batch identity occurs
   exactly once. Several source identities on one item are an explicit duplicate merge.
   `refuted` equals the pass's durable source-keyed refutations exactly. Every item has
   at least one source. The allocation is refused if one current source is omitted,
   repeated, invented or silently closed.
2. **Write the confirmed findings down**, in
   `<workspace>/reports/product-review/<root lot>/<built lot>-confirmed.md`: one entry
   each, with its proof. That file is the sub-lot's source, the way the spec is a normal
   lot's source.

   **Each entry carries an identifier — `F1`, `F2`, … — unique in the file.** A carried
   entry also has `Carries:` with every decision-batch item it consumes. The
   sub-lot's plan writes `Descends from: F3`, the completeness check counts on those
   identifiers, and the coverage lens uses them to check on the next pass that each one was
   actually fixed.
   Without them nothing downstream can be counted.

   ```markdown
   ## F1 · Two concurrent revocations both take effect
   From: unlooked · Severity: IMPORTANT
   Sources: unlooked/F1, meaning/F2
   Carries: batch 2/F1, B3/D2
   What: two simultaneous calls to revoke() both write
   Proof: test drafted, applied at <sha>, failed as claimed
          tests/test_peer_lifecycle.py::test_concurrent_revoke
   ```
3. **Create its plan file**, `<workspace>/plans/lot-<N.n>-plan.md` — construction writes
   it there, and copies it into `docs/plans/` at commit time. The previous lot's plan is
   not touched, ever.
4. **Only now, journal the close, batch consumption and the opening.** A lifecycle note records a state
   that exists:
   a takeover that reads `sublot.opened` must find the confirmed file the sub-lot's
   `Covers:` line will name already on disk — journaled first, a stop between the two
   hands the takeover a return point whose source was never written.

   `progress.py` rechecks that boundary. The five current reports and verifier brackets
   must be settled. The allocation must be the next available sub-lot. The confirmed
   artifact must contain exactly `F1..F<N>`. Each entry's `Sources:` and `Carries:` must
   equal the allocation account. The plan's actual `Covers:` block must name that exact
   confirmed file. Every current batch obligation must have its terminal or its
   `Carries:` entry.

   ```
   progress.py note pass.closed --data '{"confirmed":<N>}'
   progress.py note ruling.applied --data '{"answer":"B<B>/D2","batch":<B>,"decision":"D2","route":"sublot","lot":"<lot N.n>"}'
   progress.py note decision.batch.closed --data '{"batch":<B>,"outcome":"sublot","lot":"<lot N.n>"}'
   progress.py note sublot.opened --text "<lot N.n>"
   ```

   Add `"conflict":<C>` when that generation is the effective answer's current
   authority. Write `ruling.applied` only for an active `sublot` ruling that has no
   earlier applied line;
   `closed`, `spec-in-place` and `amendment` routes recorded theirs at their own durable
   completion. Write one `decision.batch.closed` per fully consumed open batch. Its line
   follows the pass close because that close proves the confirmed artifact is owned by
   this sub-lot operation; it precedes `sublot.opened` because a cut there resumes the
   already-closed pass by writing only the missing opening. Never close a batch while one
   active item lacks a carried confirmed entry or a durable refutation/close, or while a
   superseded answer lacks the ready conflict resolution that retired it.
5. **Go to MODE CONSTRUCTION, at C1**, and follow it as written.

**Nothing is added to the spec.** A sub-lot corrects an implementation; it does not
change what the product must do. If a finding says the spec itself is wrong, that was a
DECISION and it went to the human at R2.4.

**One thing changes in CONSTRUCTION:** the reference set. The plan works from the
**confirmed findings** instead of spec decisions, each task descends from a finding, and
the completeness check counts them that way. Its mode file says so.

Two numbers to report, neither of which is a rule:

- **the size of the sub-lot against the lot it corrects** — at some point a correction
  has stopped being one — `progress.py note sublot.oversized --text-file "$JOURNAL_TEXT_FILE"`;
- **three sub-lots touching the same area** — that is a design problem, not a series of
  corrections — `progress.py note not-converging --text-file "$JOURNAL_TEXT_FILE"`.

### The rule that governs every later pass

**A later pass may be told what changed. It is never restricted to it.**

A hint directs attention. A perimeter blinds: a pass fenced to the fixes only ever asks
*does this fix do what it says* — never *what else did it break*, and never *what was
always wrong here*.

---

## When the human stops the run

`SKILL.md` carries the procedure, pause and abort alike. What product review owes it is
the step called **the work in flight**.

**Nothing here writes to the tree**, so there is nothing to reset, nothing to preserve and
no untracked document of this mode's to spare — the reports live in the workspace, which
git ignores. Both calls are bare:

```sh
<workspace>/prompts/common/stop.sh pause
<workspace>/prompts/common/stop.sh abort
```

What is in flight is reports.

**And every test below reads inside the current pass's slice.** The journal is
append-only across the whole feature, and a pass voided by an amendment relaunches
over the SAME built lot — same mandates, same report paths — so a receipt or a return
can exist for this very mandate and belong to a dead generation. **The slice begins at
the journal's LAST `pass.opened` for this built lot, and every test below reads
nothing before it**: "the last line for its mandate" means the last line inside the
slice, and a mandate with no receipt since that opening has none, whatever an earlier
generation recorded — an old receipt read across the boundary would certify a
successor's half-written report as settled. The voided generation's outcomes do not
govern the fresh pass either: its receipts, its returns, its `decision.refuted`
verdicts all died with it at the void. A `sublot.allocated` with no `sublot.opened` died
there too: it reserved one pass's close, never the root lot's permanent ordinal.
**Identified product rulings and their ready states cross generations. A sourced or ready
decision batch crosses with its source, global actions, accepted completed rechecks, ready conflict resolutions and initial or supplemental answers, and
stays pending until `decision.batch.closed`.** Those records are the durable exception:
they froze every verified claim and its latest state before the void and are never moved
with the five lens reports.

| | |
|---|---|
| **A report whose last journal line for its mandate is `report.received`** — no `bound.spent` return after it, inside the slice | settled as of that receipt. At a resume it is verified exactly as if it had just arrived. |
| **A report file with no receipt — or whose last line for its mandate is a `bound.spent` return** | it may have been cut mid-write, or mid-rewrite — **a receipt proves the write it closed, never the one a return reopened**, and the completion block opens a report, so its presence proves a start, never an end. Treat it as absent: at a resume that reading is relaunched, fresh, **after its file moves aside**, exactly as for a silent lens. |
| **A verifier that was running** | its call ended at the stop's wait step — returned, or errored out — and its verdicts are discarded. Record **which reports are verified and which are not** — in the stopping-point note the stop procedure writes into the journal; a record left in the conversation dies with it. |
| **The copy of the tree that verifier was using** | it outlives the subagent that made it: `verify-close.sh` never ran. `git worktree list` shows it, at `<repo>/.superpowers/bwr/tmp/bwr-verify-<run>-<report file name>/w`; close it with `verify-close.sh <that report file name>` — **safe only because the wait step already ran**: a force-remove under a call still writing in the copy races its last writes. The closer repeats the physical-ground checks and removes only an exact worktree registration owned by this repository; a symlink or unregistered directory is refused untouched. |

**A finding whose author was cancelled has nobody to send it back to.** If it turns out
malformed at the resume, it is closed with that as the reason — the same outcome as a
finding that comes back still vague. **A report that would go back whole** — flooded
with trivia — **is never closed that way: a pass that drops a lens is not a pass.** It
takes the silent lens's route instead: its file moves aside, and a fresh session is
relaunched. One claim closes because it had its one return; a whole reading is redone
because nobody else covers it.

**And the resume lands on the last phase boundary the slice records — the report table
above governs a pass still in its readings, nothing later.** The pass's later phases
each left a durable note, and a resume that ignores them replays a close, re-opens a
sub-lot under a fresh ordinal, or delivers a lot twice:

**The whole-run cleanup boundary outranks this table and every checkpoint below.** A
`cleanup.started` with `scope:"whole-run"` means the human already chose cleanup. Follow
`SKILL.md`'s cleanup-resume tail and nothing else. Never offer another lot or `keep`.

**One boundary outranks every row below:** an `amendment.opened` whose data carries
`origin:"product-review"` and this built lot, after this pass's `pass.opened`. Its exact
generation is the last such opening before the amendment line. The human already ordered
the amendment, so this generation never resumes as an ordinary pass. Follow MODE
AMENDMENT's void-resume boundary: no `pass.closed {"voided":true}` after the amendment
opening means finish the idempotent void; the close present means continue to A2. Never
wake or replace a lens from the generation being voided.

**Decision batches have two roles. An unfinished route comes before the ordinary rows;
carried correction input does not.** Read every batch whose `decision.batch.opened` has
no `decision.batch.closed`. The following states are unfinished route work, wherever the
batch's source pass sits in the journal:

- a bound commit's completed global recheck proves an earlier active answer erased, with
  no matching `spec.breach.opened` → allocate the next run-wide breach and publish its
  exact owner, `B<B>/D<N>` answer, bad operation, bad SHA, authorised parent, erased
  authorities and optional attempt lot. Do not open a conflict against the bad state.
- `spec.breach.opened` without its matching `spec.breach.corrected` → run
  `spec-breach-recover.sh` for that same ordinal. Its marker decides whether the spec
  restore, corrective commit, attempt mark or journal tail remains. Nothing else routes.
- `spec.breach.corrected`, or a later ready `purpose:"restore-baseline"` conflict, with
  no `decision.recheck.completed` matching its exact `basis_kind` and `basis_ref` →
  regenerate every active target-state answer verdict against that SHA and rewrite the
  complete breach-recheck artifact. Publish `restored:true, missing:[]` or
  `restored:false, missing:[…]` exactly as the artifact proves. Never use the bad-state
  snapshot as current state.
- a complete breach recheck with `restored:false` and no later
  `decision.conflict.opened` carrying this breach, `purpose:"restore-baseline"`, the
  owner answer, every originally erased authority and every current `missing` identity →
  allocate the owner's next conflict generation from this adverse result. Its durable
  question offers preservation through an exact spec repair, or explicit authority
  revision. Never write `spec.breach.restored` from this event.
- a ready `purpose:"restore-baseline"` conflict whose target preserves missing answers
  through a spec repair, with no `spec.committed` carrying this breach and conflict → run
  the exact repair through `spec-commit.sh ... breach <K> <C>`. A matching commit with no
  keyed breach recheck regenerates that recheck; it never recommits.
- a ready `purpose:"restore-baseline"` conflict whose target changes authority without a
  spec edit, with no keyed breach recheck → recheck the unchanged SHA using
  `basis_kind:"decision.conflict.ready"` and `basis_ref:"<owner>/C<C>"`.
- a complete breach recheck with `restored:true` and no matching
  `spec.breach.restored` → write only that restored boundary from the exact checked basis.
- `spec.breach.restored` after one or more ready `purpose:"restore-baseline"` conflicts →
  return the original owner to pre-commit from the latest resolution; that resolution
  already covered its answer and every erased authority, so never ask it again. On the
  fast path with no recovery conflict, open the owner's next conflict from the original
  durable proposal and restored state. Any future edit gets a new bound operation.

- `opened` without `sourced` → regenerate lost verifier verdicts from the five durable
  reports, redo dedupe, rewrite that batch's source artifact in full, then write
  `decision.batch.sourced`. The human was not asked before this boundary.
- `sourced` without `settled` → the durable questions and IDs exist; ask that one batch
  and record its whole answer in one `decision.batch.settled`. No route has run.
- `settled` without `ready` → rewrite the actions artifact from the immutable source and
  settled event, then write `decision.batch.ready`. Never re-ask.
- a current `spec.edit.ready` for an owed `spec-in-place` answer, with no
  `spec.committed` carrying its `ready_op` → run only its matching bound
  `spec-commit.sh` call. Its pending marker freezes the generation if the call started.
  With no marker, any later authority boundary makes it stale: rebuild authorization
  from the latest complete state instead of consuming the old line.
- `ready`, with a `spec.committed` carrying this batch and decision whose `op` has no
  matching `decision.recheck.completed` → the edit committed already. Do not edit or
  commit again. Regenerate every item verdict, rewrite the SHA-named complete snapshot
  and publish its boundary.
- a completed recheck whose `answer required` IDs have no initial or
  `decision.batch.supplemented` answer → ask exactly those IDs as one group and record
  the atomic supplement. Never ask an already answered ID again.
- a complete run-wide actions, recheck, supplement, `ruling.ready` or
  conflict-resolution state that exposes incompatible active answers, with no later
  `decision.conflict.opened` for that exact state → allocate the next conflict generation
  under owner `B<B>` and write its opening with every fully qualified identity before its
  source artifact or human question. Do not run either answer's route.
- `decision.conflict.opened` without the matching `decision.conflict.sourced` → rewrite
  that same generation's source artifact from the exact `state_kind` and `state_ref` in
  its opening, then publish `sourced`. Never allocate another conflict and never use a
  partial source.
- `decision.conflict.sourced` without the matching `decision.conflict.settled` → the
  conflict IDs, current answers, proof and question are durable, but no human resolution
  is. Ask that exact conflict and atomically record the full result. No edit or amendment
  route has run.
- `decision.conflict.settled` without the matching `decision.conflict.ready` → derive and
  rewrite that generation's complete resolution artifact from its source and settled
  event, then publish `ready`. Never ask again and never reconstruct from memory.
- `decision.conflict.ready` → make its complete run-wide active/superseded answer state current,
  then apply any later complete recheck or conflict generation in journal order. A
  `purpose:"restore-baseline"` generation stays in the higher breach-recovery rows until
  `spec.breach.restored`; it never enters the ordinary fixed-point loop early. Otherwise,
  if the state exposes another conflict, allocate the next generation; if not, continue
  the fixed-point loop. Never revive an answer that this state superseded from an earlier
  source, action or recheck artifact.
- `ready` with a current `spec-in-place` answer still owed → continue the fixed-point
  loop from its lowest stable ID. With no bound commit for that owed state, perform the
  edit through `spec-commit.sh`; with its commit present, consume only the matching
  complete snapshot.
- `ready` at the in-place fixed point with a missing `closed` or `spec-in-place`
  `ruling.applied` → write only the missing terminal lines from the actions file or last
  complete snapshot. A per-item applied line never substitutes for the snapshot.
- `ready` with amendment routes, all earlier routes applied, and no `amendment.opened`
  carrying this batch's exact current member set and authority generation → read every
  ready conflict resolution, then open one grouped
  amendment for every active current-owner decision whose latest route is `amendment`.
  Give it every other active product answer as a preservation constraint. Never choose
  the first, revive a superseded answer or leave another active member pending.
- a grouped amendment opened for the batch **after this slice's `pass.opened`** → the
  amendment boundary above owns its void, document, commit and tail. That tail writes
  any missing `ruling.applied` lines, then opens the fresh pass. The batch itself remains
  open until a later R2.5 consumes every correction obligation.

Every route-consuming row above also requires `SKILL.md`'s run-wide authority quiescence.
An unfinished identified ruling, batch, conflict, breach, adverse SPEC-loop proof or
current spec-edit authorization for another owner wins first. Complete its exact durable
chain, then reconstruct this batch from the new global state. The conflict lifecycle rows
themselves remain writable because they build that state. A direct route whose acceptance
proof already landed writes its missing terminal before this mode opens another ordinary
conflict.

Once no unfinished `closed`, `spec-in-place` or `amendment` route remains, the batch is
pending correction input. Classify that role by journal order:

- a **source-pass batch** has its `decision.batch.opened` after this slice's
  `pass.opened`. R2.4 created it only after the five readings settled. Merge its pending
  items into R2.5 now;
- a **carried batch** has its `decision.batch.opened` before this slice's
  `pass.opened`. An amendment ended its source generation and opened this successor. It
  is input for this pass, not a phase boundary in this pass. Preserve its source,
  actions, supplemental answers, the run-wide state including every ready conflict
  resolution, the last completed snapshot when one exists, and
  applied/keyed-refuted state while the current pass follows the ordinary row below. Only when this pass reaches
  R2.4 through its own five settled readings does the live R2.4/R2.5 flow merge those
  items.

From an `amendment.opened` until its committed tail creates the successor
`pass.opened`, the amendment boundary above owns the transition. The batch becomes
carried input when that successor opening exists. A clean carried union cannot close a
pass whose readings are incomplete, and a non-empty one cannot open a sub-lot early.

`decision.batch.closed` is terminal for that batch's **work routing**. Nothing in it is
routed or merged again. Its active human answers remain in the run-wide product-answer
state until a later ready conflict resolution supersedes them.

- **No `pass.closed` and no `sublot.allocated` in the slice** → the pass is in its
  readings or its adjudication.
  The report table above says which reports stand; a lost verifier verdict is
  regenerated, never remembered; **an identified product ruling is reused, never
  re-asked** — its `R<N>` state is durable. Carried decision batches wait as durable input
  throughout this row; they do not make the pass leave it.
- **`sublot.allocated` in the slice, no `pass.closed` after it** → R2.5 chose the
  sub-lot identity and durable dedupe account before it was cut while creating its
  artifacts. Resume R2.5 for **the lot named by that line**. Read each named fresh source
  from its durable report and each carried identity from its durable batch state. The
  account already says which sources merge into each final `F<N>`; do not regenerate
  verdicts or redo dedupe after this boundary. **The existing confirmed file,
  complete-looking or not, is never an input to this reconstruction, and neither is
  remembered context.** Rewrite it in full from the allocation account and its durable
  inputs, create or reuse that lot's plan scaffold, then
  write `pass.closed` and `sublot.opened` in their prescribed order. **Never allocate
  again.** A partial artifact proves only an interrupted write; the allocation line is
  the identity.
- **`pass.closed` with `confirmed:<N>`, no `sublot.opened` after it** → the close is
  done and does not repeat: the confirmed file and the allocated sub-lot's plan file are
  on disk — the lifecycle notes follow the artifacts by design. Finish any missing
  `ruling.applied` and `decision.batch.closed` lines proved by that confirmed file, then
  **write the `sublot.opened` line for the lot named by `sublot.allocated`**, then construction C1.
  Never re-verify, never re-adjudicate, never re-close.
- **`sublot.opened` in the slice** → the sub-lot is open and its name is in the note:
  **go to construction C1 for THAT lot, and never allocate again.** R2.5 is complete;
  none of its artifacts or lifecycle lines repeats past this boundary.
- **`pass.closed` with `confirmed:0`, no `lot.delivered` after it** → the lot is done
  and the close does not repeat. First write any missing `decision.batch.closed` whose
  no-correction outcome this close proves, then resume at *Leaving review*, its first
  step.
- **`lot.delivered` in the slice** → the delivery is recorded: resume at the
  checkpoint — *Leaving review*'s next step — and never report or journal the
  delivery again.

**A `pass.closed` carrying `voided:true` is neither branch**: the amendment's order
wrote it, and the amendment owns what follows — A2 through its landing, then the fresh
`pass.opened`, a pass relaunched from its start. A grouped amendment does not close its
decision batch: the fresh pass completes all five readings, then carries every correction
obligation into R2.5 with any new work those readings found.

---

## Leaving review

**The loop ends on one complete R1 pass that yields nothing.** The lot is delivered.

1. **Report to the human**: what the review found across all passes, what was
   disproved, and what became a sub-lot.

   ```
   progress.py note lot.delivered --data '{"sha":"<sha>","passes":<N>}'
   ```
   `sha` is the reviewed commit in the current `pass.opened`. `passes` counts the
   ordinary completed passes over this root subject; a voided generation does not count.
   The script refuses this line without the exact current clean close, after an unfinished
   batch, or when the same delivery already exists.
2. **Ask what happens next** — one widget call, four questions: the next lot in **a new
   session** (recommended), here, or stop · then the provider for the **orchestrator**, for
   the **implementers**, and for the **review lenses**. The provider questions are asked
   even when the human stays here: they are not the same children each time. `stop` is a
   pause — everything stays where it is.
3. **If another lot follows here** → **MODE CONSTRUCTION, at C0**. Nothing is cleaned
   up: the workspace, the watchdog and the git refs all stay.
4. **If it follows in a new session** → read
   `<workspace>/prompts/common/handover-to-construction-rules.md` and follow it. It carries
   the whole handover, including retiring your own watchdog before you announce it.

**Only when the human says the whole feature is done, ask the final trace question from
`SKILL.md`: keep the workspace and refs, or clean them up.** `Keep` leaves both untouched.
For `Clean up`, first publish the choice and the whole-run scope:

```sh
progress.py note cleanup.started --data '{"reason":"feature-complete","scope":"whole-run","choice":"clean"}'
```

**This line must land before the first cleanup gesture.** Once present, it owns every
resume until the workspace is gone. Only then run:

```sh
<workspace>/prompts/product-review/refs-clear.sh
```

*It runs the equivalent of:*

```sh
# -r: an already-empty namespace is a no-op — a repeated cleanup must not fail
git for-each-ref refs/bwr/<run>/ --format='%(refname)' | xargs -rn1 git update-ref -d
```

Then the watchdog: **stop its process, then retire it `done` — in that order, and both
before deleting the workspace.** Retiring stops the cron's future ticks; a tick already
running is stopped only by `mcp__twicc__processes_stop`, and it reads its script from
the workspace you are about to delete — left running, it wakes or fails into a feature
already declared done. Then delete the workspace with
`<skill dir>/prompts/common/workspace-delete.sh <workspace>` — **the last gesture**.
It first renames the run atomically to its non-adoptable `.deleting` tombstone, then
removes that tombstone incrementally. The rename remains the cleanup boundary after
`progress.py` and the journal inside disappear. Nothing can be retired or recorded after
this gesture. Before either destructive step, the script proves that the lexical and
physical ground is the exact `.superpowers/bwr` directory of the derived Git checkout
root. A matching name elsewhere, below a repository subdirectory, or behind a ground
symlink is neither a workspace nor a deletion tombstone and is refused read-only.
Nothing needs to follow the deletion:
every child was retired at its own acceptance, the watchdog just above, and **the
only sessions left are orchestrators — the human's own conversations, never archived
by an agent.**

**Never clean up at the end of a lot.** A sub-lot may follow immediately, the next lot
may follow after it, and every one of them reads the refs and the prompts.

---

## Who runs on what

| Actor | Kind | Level |
|---|---|---|
| **R1.1** — the five lenses | sessions | presets in the table above |
| **R2.1** — verifier, one per report | subagent | light / medium |

What a level means, and what a preset is, are in `<workspace>/prompts/common/vocabulary.md`
and `<workspace>/SKILL.md`.

---

## Red flags

### While the lenses run

| What you are telling yourself | The reality |
|---|---|
| "This finding looks serious, let's fix it now" | Finish the pass. What it had not reached would never be reached. |
| "Four lenses are done, I'll start on those" | Verify them, yes. Dedupe and act, no — that needs all five. |
| "This lens found nothing, it was a waste" | A lens that finds nothing on a clean lot did its job. The one that never finds anything on any lot is the problem. |
| "One lens went quiet, four reports is enough" | A pass with four lenses out of five is not a pass. Relaunch it. |

### While adjudicating

| | |
|---|---|
| "Only two findings, I'll check them myself" | Every report gets its verifier. |
| "This one is true but minor, I'll drop it" | You are judging its value. That is the one thing you never do. |
| "The reviewer is certain, that is good enough" | Nothing is kept unproved. A test, an exhibition, an absence, or a DECISION. |
| "I'll answer this product question, it's obvious" | It is the one thing only the human answers. |
| "I'll retire the reviewers, their reports are in" | Not until every finding is settled. There is nobody to send a vague one back to afterwards. |

### On a later pass

| | |
|---|---|
| "Only re-review what the sub-lot changed" | A perimeter blinds. Say what changed; never restrict to it. |
| "Pass four found things again, this is not converging" | Say so to the human, with the numbers. That is a signal about the lot, not a reason to stop reviewing. |
