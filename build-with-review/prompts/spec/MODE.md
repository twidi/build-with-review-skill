# MODE SPEC

**This file governs the spec.** Everything you need is here, in `<workspace>/SKILL.md`,
and in the files this one names.

You are the controller. You design a feature with the human, you write its specification,
and you put that specification through an adversarial review until it holds. **You write
the spec yourself** — it belongs to the session that held the brainstorming, and a spawned
session did not hear the human.

**A spec defect costs a multiple of a plan defect**: every task built on it inherits the
error. So no single pass may conclude, and no reviewer's word ends the loop. Coverage
comes from three mechanisms:

- **narrow mandates** — a reviewer with one job cannot hide behind breadth;
- **fresh reviewers every round** — blind spots do not accumulate;
- **exhaustible enumerations** — completeness stops being a matter of attention.

**Each round fans out into reviewers with ONE mandate each, all reading the whole
document.** One fixer session, reused across the loop, is the spec's only writer.

**This mode overrides two instructions of `superpowers:brainstorming`:** commit the spec
only when the end condition is met, and never invoke `writing-plans` — construction
follows here, in this workflow.

---

## Before you start

You need, in hand:

- **which feature** you are specifying, and whether this is a new spec or an amendment;
- the **concurrency cap** and the **providers**, answered by the human.

**The workspace** — the first thing you do, before any child: run the script that creates
it, unconditionally — only a feature's first session creates anything, and the script
decides. `SKILL.md` has the call, in the section *The workspace*. Then launch the
watchdog, once, if it is not already running.

*Until the workspace exists you are reading this skill from where it is installed. From
the moment it does, read the frozen copy under `<workspace>/prompts/` — and that is the
path you hand to every child.*

**An amendment does not enter here.** It has its own file and its own phases —
`<workspace>/prompts/amendment/MODE.md` — and nothing below runs for it. **One route
comes back all the same**: an amendment whose reach would not close lands first, under
its own mode's order, and then the whole spec re-enters at S3 — every mandate, the
document as it now stands, already committed. **The round counter continues, never
restarts**: the first re-entry round is the journal's last `round.opened` plus one — a
fresh round 1 would overwrite the first loop's reports and write a second round 1 into
the journal. **And `ripple` runs from that first round**: its trigger is edits since the
last full round, and the amendment landing is exactly that. That first round's third
list is empty — nothing is pending verification, since the landing was proved by diff
at A4; its job is discovery, over the whole document.

---

## Spec altitude — what belongs in a spec

**A spec states decisions.** Anything an implementer could derive belongs to the plan.
This is enforced at S2, before the first review.

- **Cite paths and symbols, not lines.** `src/app/core/models.py` plus the symbol; `:NN`
  only when no symbol identifies the spot. A line number rots on its own and costs a
  verification every round.
- **Separate what exists from what is decided.** One section holds every claim about
  current behaviour; the rest holds decisions only. A reviewer then spends verification
  where it applies and judgement where it applies.
- **No summary sentences.** *"The full inventory"*, *"nothing else changes"*, *"every
  caller"*, a count of things listed elsewhere — delete them: any later edit falsifies
  them. Normative absolutes (*"an agent may never clear a password"*) stay: they are
  rules, checked against code.
- **Name what must be verified and by what means; the steps belong to the plan.** A named
  means must be able to fail: name the bug it catches and what you would see instead when
  that bug is present. A means whose correct and incorrect observations are identical is
  not a means — write *"unverified"* and move on. **A verification is a leaf: nothing
  inherits it, so it earns no spec-level review.**
- **Enumerate the states of every entity the feature touches.** A feature meets an entity
  in all of its states, not the one you pictured: a session is also hidden, archived, a
  draft, in an unlisted project; an account is also deactivated; a file is also missing.
  Give every state a decision — or mark it for the human as a DECISION.
- **Give every contract a feasibility level, and verify the claim it rests on.** One of:
  `obvious`, `needs work`, `very complex`, `infeasible on this platform`.
  - The level is not an estimate of effort. It answers one question: **can this be built
    as written, here?**
  - **Verify every platform claim against the real runtime** — a browser API, a runtime
    behaviour, a library guarantee. Run it, or read the implementation. A standard that no
    implementation follows is not a platform.
  - `very complex` and `infeasible` are DECISIONs, raised before the loop ends.
- **Git state is phase-specific.** During authoring and the first review the spec is
  untracked and its workspace is git-ignored; **re-entered after an amendment, it is
  committed, and the fixer's round edits sit in the working tree until the close.**
  Reviewers and the fixer may use read-only Git inspection to verify source and history,
  but must not make findings about either temporary state, or pull the spec or the
  workspace into implementation scope. **You commit the spec alone, at the close.**

---

## S1 — Brainstorm

Follow `superpowers:brainstorming` faithfully: context exploration, one question at a
time, two or three approaches, a sectioned design presentation, the human's approval.

**Do not commit. Do not invoke `writing-plans`.**

---

## S2 — Write the spec

**You write it, obeying *Spec altitude* above**, and you run its inline self-review.

**Where:** the project's own design-doc directory when it has one — dated design docs
under `docs/plans/`, `docs/design/`, or a location named in `CLAUDE.md` / `AGENTS.md`.
Otherwise `docs/superpowers/specs/`. Name it `YYYY-MM-DD-<topic>-design.md` either way.

**Publish authoring atomically.** Write the complete document through your file-editing
tool to a same-directory `<name>.writing` file. Re-read it whole. Require the final
path to be absent, then rename the real temporary file to the final path in one gesture.
Never write the final path incrementally. A cut leaves either no final file or the whole
document. A symlink or other occupant at either path is foreign state and stops the run.

**The spec carries the lot breakdown.** You cut the lots yourself, and approving the spec
approves them — nothing asks the human to confirm them separately.

Every lot starts with one exact second-level heading, in strict order:

```text
## Lot 1 — <title>
## Lot 2 — <title>
```

The headings are the machine-readable lot manifest. Do not skip or repeat an ordinal.

**How many.** As many as the work needs; there is no expected number. A correction
inserted after lot 1 is `1.1`, then `1.2`: these are **ordering labels, never decimals**,
and they never renumber what follows.

**Cutting them is a trade-off, and it is yours.** A large lot carries a long review and a
wide blast radius when something in it is wrong. A small one is reviewed quickly, but a
lot cut too small tends to be undone by the next one, because it delivered something the
following lot had to reshape. **Cut where the product has a natural seam** — a surface, a
layer, a user-visible capability — not where the line count is even.

```
progress.py note spec.written --text "<path>" --data '{"lots":<N>}'
```

`progress.py` refuses an aliased or non-regular spec, recomputes the exact heading
manifest, and records both that manifest and the complete file SHA-256. The path is
project-relative. A later round consumes this exact readiness generation.

---

## S3 — Spec review

### S3.0 · The human checkpoint before the first child

**Nothing has been spawned yet for this feature.** One widget call, three questions:
the provider for the **reviewers**, the provider for the **fixer**, and **how many
reviewers may run at once** — 3 recommended, 4, 5.

**The cap is asked here and nowhere else, for the whole feature.** Record it, apply it
throughout, and hand it to whoever takes the run over later.

**On a re-entry after an amendment this checkpoint narrows**: the cap is known and is
not re-asked; the two provider questions are — reviewers and fixer are new children.
**And `run.started` is not written again**: the run started once, and a second start
line would read as a second run.

```
progress.py note run.started --text "<feature>" --data '{"cap":<N>}'
```

### S3.1 · The five mandates

**Split the job, not the text.** A spec's sections reference each other constantly, so
every reviewer reads the **whole** document and looks for **one** thing. The count does
not grow with the document: a longer spec means each reviewer reads more, never that there
are more of them.

| `bwr.mandate` | Preset | Job | Rounds |
|---|---|---|---|
| `enumerator` | `ReviewerLight` | lists, not judgement | every |
| `ripple` | `ReviewerLight` | restatements the edits falsified, that name no identifier | from round 2 |
| `verifier` | `Reviewer` | Reality and Consistency, against the code | every |
| `feasibility` | `Reviewer` | can this be built here? platform claims RUN | every |
| `judge` | `Reviewer` | Ambiguity, Completeness, Sequence, Decomposition | every |
| `scoped` | `Reviewer` | after every fixer return — see S3.5 | — |

**Those slugs are fixed. Never invent a variant** — they are how a round is found again
afterwards.

`ReviewerLight` is the same role on a lighter model at moderate effort — moderate, not
low: the risk on a mechanical mandate is skimming, not faulty reasoning.

Each mandate's full instructions live in `<workspace>/prompts/spec/reviewer-<slug>.md`,
and its completion block in `<workspace>/prompts/spec/reviewer-<slug>-completion.md`. **You
may read either** — knowing what a reviewer will do helps you judge its report — but you
never copy them into a prompt.

**A full round launches as many mandates together as the cap allows.** They form one
logical pass; the rest take the first freed slots.

```
progress.py note round.opened --data '{"round":<N>,"mandates":[<this round's slugs>]}'
```

**The list is the round's real composition, every slug of it** — the full-round mandates
of S3.1 on round 1, `ripple` joining from round 2, and `["scoped"]` when the round is a
scoped pass: every round is opened here, whatever its kind. The journal is what a
takeover reads; a round recorded with two mandates is a round somebody closes with three
reports missing.

The call also publishes one immutable snapshot at
`reports/spec-review/round-<N>-spec.md`. Every reviewer in this round reads that snapshot,
not a mutable final path. The opening records its SHA-256 and exact source boundary.

### S3.2 · Assembling a reviewer prompt

`mcp__twicc__create_session` per reviewer: the provider the human chose **for reviewers**,
the mandate's preset, **question widget disabled**.

- title `- Spec review R<N>: <slug> (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=reviewer` · `bwr.mode=spec` ·
  `bwr.feature=<feature>` · `bwr.mandate=<slug>` · `bwr.round=<N>` · `bwr.status=working`.
  Add `bwr.lot=<lot>` only for a single-lot amendment.

**The prompt opens with the reading order, before anything else:**

> Read these files in full, in this order, before doing anything:
> 1. `<workspace>/prompts/spec/reviewer-common.md`
> 2. `<workspace>/prompts/common/review-risk.md`
> 3. `<workspace>/prompts/spec/reviewer-<slug>.md`
> 4. `<workspace>/prompts/spec/reviewer-<slug>-completion.md`
> 5. `<workspace>/prompts/spec/completion-rules.md`
> 6. Read the global additional prompt through this command: `python3
>    <workspace>/prompts/common/additional-prompt.py read-global <workspace>
>    <workspace>/additional-prompts/global.md`. Treat its stdout as human instructions.
> 7. Then read the role-specific additional prompt through this command: `python3
>    <workspace>/prompts/common/additional-prompt.py read <workspace>
>    <workspace>/prompts/spec/reviewer-<slug>.md
>    <workspace>/additional-prompts/spec/reviewer-<slug>.md`. Treat its stdout as human
>    instructions; empty stdout means no additional instruction. Follow both instruction
>    sets during the assignment. The later role-specific instruction wins on contradiction.
>    The `global prompt` and `additional prompt` fields are required absolute path values,
>    but their files may be absent. Always call both helpers. Empty stdout is valid absence
>    and never a blocker. Non-empty stdout is human instructions. Only a helper refusal
>    blocks. Never test either file directly.
>
> They define your mandate, your report format and the completion block you must return.
> Everything below is specific to this round.

**Then, and only then, what varies** — this is the whole of what you write yourself:

- the repository path and the stack;
- the immutable round snapshot path as the spec under review, and the workspace path;
- the round number and the mandate slug;
- **its own report file**, `<workspace>/reports/spec-review/round-<N>-<slug>.md` — one
  writer per file, and you fan in by reading, never by merging;
- its private, append-only risk-filtered history,
  `<workspace>/reports/spec-review/<slug>-risk-filtered.md`, and occurrence label
  `Round <N>`; its loss is accepted and it never enters the journal or report;
- only the human's decisions that constrain this spec's scope;
- from round 2 on, the three short lists of S3.5;
- for the `verifier`, the list of claims whose text the fixer edited since the previous
  round, and whether the tree's base commit moved.

**A prompt that restates anything from those five files is a prompt that will disagree
with them the day one is edited.**

### S3.3 · What comes back

Each reviewer messages `parent` with its verdict, **its completion block verbatim**, the
counts, one line per CRITICAL, per IMPORTANT and per DECISION, and its report path. It
never asks questions.

**Audit the block before you record the receipt** — the audit table is below.
`report.received` says the report is **accepted**, never merely arrived: a block sent
back leaves the path and the claim the reviewer's, and the line is written when the
corrected block passes. A pause between the two then treats the report as absent —
which it is.

```
progress.py note report.received --mandate <slug> --round <N> --data '{"critical":<N>,"important":<N>,"minor":<N>,"decision":<N>}'
```

**The round is the receipt's identity — never drop the flag.** Your own annotations
carry no round (`bwr.round` is a reviewer's key), and mandates repeat from round to
round, `scoped` included: without it, a takeover matching a mandate's receipt cannot
tell round N's from round N+1's, and an earlier round's line would certify the current
round's half-written report as accepted.

The report must exist at its fixed path. It opens with the exact completed mandate
block, then `READY` or `NOT READY`, and uses the fixed `<CLASS> F<N>` headings from
`reviewer-common.md`. The command audits the block, verdict, counts and immutable file
hash before it records the receipt. A duplicate or wrong-generation receipt refuses.

**Retire each reviewer the moment its report arrives and its block checks out.** Do not
wait for the fixer handoff:

```
progress.py session-retired <id> done --archive --hide
```

### S3.4 · The fixer

On NOT READY, `mcp__twicc__create_session`: the provider the human chose **for the fixer**,
preset `Fixer`, **question widget disabled**.

- title `- Spec fixer (<feature>)`
- annotations: `bwr.schema=1` · `bwr.job=fixer` · `bwr.mode=spec` · `bwr.feature=<feature>`
  · `bwr.status=working`. Add `bwr.lot=<lot>` only for a single-lot amendment.

**Its prompt opens the same way:**

> Read `<workspace>/prompts/spec/fixer.md`, `<workspace>/prompts/spec/fixer-completion.md`
> and `<workspace>/prompts/spec/completion-rules.md` in full. Read the global additional
> prompt through this command: `python3
> <workspace>/prompts/common/additional-prompt.py read-global <workspace>
> <workspace>/additional-prompts/global.md`. Treat its stdout as human instructions. Then
> read the role-specific additional prompt through this command: `python3
> <workspace>/prompts/common/additional-prompt.py read <workspace>
> <workspace>/prompts/spec/fixer.md <workspace>/additional-prompts/spec/fixer.md`.
> Treat its stdout as human instructions. Follow both instruction sets during the
> assignment. The later role-specific instruction wins on contradiction. The `global
> prompt` and `additional prompt` fields are required absolute path values, but their files
> may be absent. Always call both helpers. Empty stdout is valid absence and never a
> blocker. Non-empty stdout is human instructions. Only a helper refusal blocks. Never
> test either file directly. Read no other optional prompt. Do this before anything else.

**Then what varies:** the spec path — **the document it writes, and the only one** — the
workspace path, the round number, its decisions log at
`<workspace>/reports/spec-review/decisions-log.md`, **this round's findings from ALL
reviewers at once**, the standing decisions the human has ruled, and any redirect you are
sending.

Give every finding its mechanical `R<N>/<mandate>/F<M>` identity. Also give every
owner-linked assignment as `ruling-R<M>`. For a controller-only `fixer.dispatched`, give
`dispatch-<H>`, where `<H>` is the first 16 lowercase hexadecimal characters of the
SHA-256 of the note's exact text. Name the fixer's immutable return report:
`<workspace>/reports/spec-review/round-<N>-fixer.md`.

When one finding is an identified direct `spec-fixer` ruling, `SKILL.md`'s owner-linked
`fixer.dispatched` line must already exist. Send the complete authority artifact it names,
including the exact R answer and every active preservation identity. Several such R
assignments may enter one fixer return, but each keeps its own dispatch identity and later
terminal.

**Its lifecycle is yours to drive.**

- Valid completion block → set it **`idle`**. Back to `working` before sending it a later
  round's findings.

  ```
  progress.py note fixer.returned --round <N> --data '{"applied":<N>,"declined":<M>}'
  progress.py session-status <id> idle
  progress.py session-status <id> working
  ```

  The return call accepts only one complete account over every current assignment. It
  audits the fixed fixer block, the exact correction-account lines copied into the
  decisions log, and the resulting spec bytes. Its stored hashes bind the scoped round.
- **Reuse this same session all loop** — its accumulated context is the asset, and it
  stays the spec's only writer.
- One exception: it is **rotated** on a redirect dissolving its own construction — see
  *Recurring findings* below.
- **It is retired `done` at the close.** The fixer belongs to this mode; a later amendment
  re-enters SPEC and spawns its own.

### S3.5 · The loop

A reviewer's asset is fresh eyes and it decays: a reused reviewer returns to the areas it
opened, while different reviewers have different blind spots and their coverage compounds.
**Every round gets new reviewer sessions.**

**A full re-fan** repeats S3.1 and S3.2, with three short lists in the prompt, never a
history:

1. **the human's decisions**, to judge on honest statement and never re-litigate;
2. **findings declined with their evidence**, so they are not re-raised;
3. **the findings to verify this round**, each with its exact edit.

**After EVERY fixer return, the next step is ONE scoped verification reviewer** — a fresh
session, never a re-fan. Preset `Reviewer`, `bwr.mandate=scoped`, and the **next**
`bwr.round`. Its instructions are in `<workspace>/prompts/spec/reviewer-scoped.md`.

- **A scoped pass is a round like any other and increments the counter** — the sequence
  reads `4 full, 5 scoped, 6 scoped, 7 full`. The slug stays `scoped` throughout, so one
  annotation filter returns every verification pass of the loop.
- You supply, in its prompt: the findings it must verify with their exact edits, and the
  list of sections the fix touched.
- Nothing found → the next round is a full re-fan. Something found → back to the fixer,
  then a NEW scoped reviewer, and so on.
- **Re-fan over the whole document whenever a construction is replaced rather than
  edited** — a mechanism removed, reinstated or redesigned — whatever its severity. A
  replaced construction has no bounded ripple.
- **A scoped round catches REGRESSION, never DISCOVERY.** What was always wrong and never
  examined stays invisible to it. Full rounds must keep happening.

### S3.6 · The end condition

**The loop ends on a full round that produces nothing at all — on text no fixer has
touched since.** That is the invariant the close certifies: the spec that commits is
the spec a full round read, unchanged. A full round with no CRITICAL and no IMPORTANT
is therefore not yet the end when it produced anything:

| | |
|---|---|
| **it produced findings** — MINORs, DECISIONs already ruled | the fixer applies them, the scoped round that follows must find nothing — **and then the next round is a FULL re-fan, as S3.5 orders after every fixer return's clean verification.** The scoped pass proved the edits did what they said; nobody has read the document those edits produced — a ruling's new normative text, a MINOR fix falsifying a distant restatement — and scoped catches regression, never discovery. |
| **it produced none at all** | **the loop is over.** There is nothing to fix, so no fixer runs, and the text is exactly what this round read. |

**And no block of that closing round carries a `NOT DONE`.** A `NOT DONE` is a
category nobody reviewed, and an unreviewed category closes nothing: the loop
continues, and the next full round's fresh reviewers cover what it names by
construction — every mandate reads the whole document, every round. **Once, though — never forever**: the same reason returned by the next round's
fresh reviewer is a stable blocker, not a lapse of attention. Stop opening rounds and
take it to the human — `SKILL.md`'s audit duty carries the gesture and its journal
line — and nothing runs until they answer.

Never a reviewer simply writing READY. Expect three to five full rounds.

**A scoped chain that does not converge is itself a DECISION.** Alternate fixer and scoped
verification while each pass closes findings. When the same defect survives several passes
— the fixer's edits circling one spot — stop: the construction, or the requirement behind
it, is wrong. Analyse it as *Recurring findings* requires, write the analysis to the human,
then ask. **This is the one place where the loop may stop and wait**; everywhere else it
runs unattended.

---

## Closing the spec

In this order, and it is an order:

1. **Run the self-sufficiency check** — it can still hand the fixer a finding, and that
   reopens the loop.
2. **Set the spec's status line** — your one permitted edit, see *Controller duties* below.
3. **Commit the spec — through the script, never a bare `git commit`:**

   ```sh
   <workspace>/prompts/common/spec-commit.sh <spec path> "<subject>" -
   ```

   `-`, because nothing is in flight at a close — a re-entry ended its
   interrupted attempt back at A4. **The script writes the `spec.committed`
   line itself, and that is what makes this close survivable**: a bare commit
   killed before its note leaves a valid close the journal never saw, and a
   resume re-running the close then dies on "nothing to commit" with no route
   to the missing line — the script's pending marker absorbs exactly that
   window. The rounds the loop ran need no place in the payload: the journal
   already carries one `round.opened` per round.
4. **Prove every pending direct `spec-fixer` ruling against the committed close.** This
   step is omitted when no owner-linked `spec-fixer` dispatch lacks its matching
   `ruling.applied`. Otherwise regenerate a fresh finding-verifier verdict for every
   active product answer against the committed spec and reviewed code. Write one complete
   immutable artifact under `<workspace>/reports/answers/`. It contains every active or
   superseded answer and one exact result for every still-pending owner-linked assignment.
   Then publish one shared boundary:

   Bracket one fresh physical finding-verifier call per pending assignment. The opening
   and result copy the assignment's exact authority tuple:

   ```sh
   progress.py subagent-started finding-verifier \
     --data '{"owner":"spec-loop","commit_op":"<closing op>","sha":"<closing sha>","ruling":"R1","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}'
   progress.py subagent-ended finding-verifier \
     --data '{"owner":"spec-loop","commit_op":"<closing op>","sha":"<closing sha>","ruling":"R1","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>","present":true}'
   ```

   `present` is the verifier's structured result. A lost final message consumes this
   durable result and does not launch another physical call.

   ```sh
   progress.py note decision.recheck.completed \
     --data '{"owner":"spec-loop","sha":"<closing sha>","commit_op":"<closing spec.committed op>","accepted":true,"missing":[],"artifact_sha256":"<recheck artifact sha256>","rulings":[{"ruling":"R1","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}],"actions":[{"answer":"R1","status":"active","route":"spec-fixer"}],"verifiers":[{"ruling":"R1","present":true}]}' \
     --text "<the complete recheck artifact path>"
   ```

   The artifact is one JSON object exactly equal to the structured data above, except
   that it omits its own `artifact_sha256` field. `artifact_sha256` freezes it.
   `rulings` contains every pending direct assignment exactly once and copies its
   authority tuple. `actions` is the complete structured run-wide answer state, in the
   same form as every other global recheck. `verifiers` contains every fresh durable
   result exactly once. Publish `accepted:true, missing:[]` only when every named answer
   is present exactly and every earlier active answer survived. Otherwise `missing`
   contains exactly the sorted absent `R<N>` identities and `accepted` is false.

   On success, write one terminal per entry, copying the tuple and shared proof:

   ```sh
   progress.py note ruling.applied \
     --data '{"answer":"R1","ruling":"R1","route":"spec-fixer","sha":"<closing sha>","recheck_op":"<closing spec.committed op>","authority_kind":"<kind>","authority_ref":"<ref>","authority_sha256":"<sha256>"}'
   ```

   On any mismatch, publish `accepted:false` and every missing or contradicted fully
   qualified identity. Apply no ruling. Journal the exact discrepancies through a
   proof-linked correction, not a second owner-linked R dispatch:

   ```sh
   progress.py note fixer.dispatched \
     --data '{"spec_loop_recheck":"<rejected closing spec.committed op>"}' \
     --text-file "$JOURNAL_TEXT_FILE"
   ```

   Send them to the fixer, and reopen the normal scoped-then-full
   loop from the committed SHA. A later clean full round creates a new close commit and
   a new keyed recheck. The rejected close and proof remain history; they never become a
   terminal.
5. **Report to the human** what the loop did: how many rounds, what the last one found,
   what was escalated and how they ruled.
6. **Retire the fixer `done`, when one exists and is still open** — archive, hide. A
   loop whose rounds never produced a finding never created a fixer, and there is
   nothing to retire — and one a stop already retired is not retired again: a
   terminal status is written once.
   Every reviewer was retired as it reported, so nothing else is open.
7. **Go to the `Spec validated` human checkpoint** — one widget call, four questions: what
   happens next (**a new session**, recommended · here · stop), then the provider for the
   **orchestrator**, for the **implementers**, and for the **review lenses**. `stop` is a
   pause: everything stays, and a later session picks the feature up.
   - **Plus the worktree question, in a second call, and only if you are not already in
     one.** `SKILL.md` has it. **This is the only moment it is ever asked** — no code
     exists yet, so moving is still free.

**Re-entered after an amendment, the close narrows.** Steps 1 to 6 run as written — the
check, the status line, the commit, any direct-ruling proof, the report, and the fixer
retired when one exists. **Step 2's status
line extends the record, never replaces it** — the amendment stays written: *validated
…, amended … (amendment N), revalidated …*, in the document's own vocabulary. **Step 7 does not**:
the feature already has its shape, so no checkpoint, no worktree question, no handover.
You are the controller the amendment interrupted — pick the run back up where it stood,
with what the exit door deferred: **the plan work and the launch** when an attempt was
ended, or **whatever was waiting** when nothing was in flight — a voided review pass
relaunched from its start, the lot's next task, the plan being written — against the
spec as it now stands, and back to the mode you were in.

**The self-sufficiency check.** *The spec must be enough, on its own, to build the lots.
What is not in the spec does not exist.* Walk **every active product answer in the
run-wide state**, not only decisions from this loop. Put one in the document when it constrains an in-scope implementation choice, a
verification case, or a plausible adjacent alternative. **A ruling that EXCLUDES an
adjacent topic is the trap:** silence lets a literal implementer add it, so state the
exclusion. Do not copy unrelated standing decisions or global invariants. Anything relevant
and missing goes to the fixer as a finding **before** the commit — never through a side
channel — **and journaled before it is dispatched**:

```
progress.py note fixer.dispatched --text-file "$JOURNAL_TEXT_FILE"
```

*(the heredoc transport when it quotes anything).* The closing round's reports carry no
findings, so this note is the only durable copy of the assignment: a pause after the
dispatch would otherwise cancel the fixer and drop the very correction that reopened
the loop — the resume replays reports, and this note is the report a
controller-originated finding has.

**The workspace stays. The watchdog stays.** They live through construction and every
review pass; only the human's *"the whole feature is done"* removes them.

**If the human hands the next step to a new session**, read
`<workspace>/prompts/common/handover-to-construction-rules.md` and follow it. It carries
the whole handover: what to check first, how to create the session, what its message says,
and what you do once it exists.

---

## Controller duties in this mode

### Your write access ended with authoring

**Your last edit to the spec is the moment you finish writing it at S2.** From the first
round on you are a message-passer: every modification — a fix, a typo, a wording touch-up
you noticed — goes through the fixer. An edit of yours has no decisions-log entry and no
re-review; it is invisible to the loop.

**Findings you notice yourself go to the fixer as findings — journaled as you dispatch
them**, the closing check's own `fixer.dispatched` note: a noticed finding is in no
reviewer's report, and the resume replays only what is durable — a pause before the
fixer's accepted return would otherwise erase the assignment while its edits sit
half-made in the document.

**One exception, and one only: the status line in the document's header, once the loop has
ended.** You edit that line yourself, in the document's own vocabulary, just before the
commit. Do not invent a status line for a document that has none.

- **Never route it through the fixer.** The status records the loop *you* ran; no reviewer
  raised it and none will verify it. Sending it to the fixer costs a dispatch, a fixer
  turn, and the scoped round that every fixer return mandates — to change one line about
  your own bookkeeping.
- **That one line, and nothing else.** A second line you want to touch is a finding, and a
  finding reopens the loop.

### Auditing a completion block

The block arrives verbatim in the ping, so the check needs no file opened. **Compare it
line by line against `<workspace>/prompts/spec/reviewer-<slug>-completion.md`: same items,
same order.**

| What you see | What you do |
|---|---|
| **the block is missing from the ping** | send it back. **Do not read the report file instead** — accepting it elsewhere teaches the next agent to drop it. |
| **a line is missing** | which item, and what is its datum? |
| **a line without its datum** | the number or the name, not a restatement |
| **a box unticked with no `NOT DONE`** | ask, spelled out: *"these boxes are unticked — did you do those items or not? Tick each one you settled and give its datum; write `NOT DONE: <why>` on any you did not."* The data underneath may be perfectly good; never guess which it is. |
| **a `NOT DONE: <why>`, correctly formed** | **valid — it is a hole, not a defect of the block.** Read the why. A cause you can lift — a blocker you can answer, a path it lacked — lift it, and the reviewer finishes: it is still live. One you cannot: accept the block and retire it normally. **The round now carries a category nobody reviewed, and the end condition consumes that.** |

**The session stays live and `working` for ONE repair, journaled as you send it back**
— `progress.py note bound.spent --mandate <slug> --text "malformed block returned -
<its session id>"`. A second return still malformed is not a block to repair:
`SKILL.md`'s audit duty carries the route — the silent-child treatment, and its
stable-blocker exit.

### An infeasible contract

**It is a DECISION you analyse first, not one you relay.** Reproduce the failing claim
yourself, or read what the feasibility reviewer ran. Then say what the contract could
become — the nearest buildable behaviour, and what it costs the user. **A contract dropped
for a platform limit the human cannot check is a contract they cannot rule on.**

The three outcomes of a DECISION, and the rule that no round starts while one is open, are
in `SKILL.md`. An escalated product answer receives its `R<N>`, `ruling` and complete
run-wide `ruling.ready` state there. Compare the proposed fixer assignment with every
active product answer, including closed-batch answers. Resolve any conflict before the
assignment. One addition here: **no fixer round starts while a DECISION or its global
answer state is open.**

### Recurring findings, and rotating the fixer

When rounds circle one root cause, **first name the cause: a construction, or a requirement
nobody decided?** The tell is what the successive findings propose.

| The findings propose | What it means |
|---|---|
| different **mechanisms** for one user-visible behaviour | a construction — redirect the design |
| different **user-visible behaviours** | the requirement was never decided. Stop fixing, raise a DECISION, and let the answer be the redirect. |

Redirecting a construction when the requirement is the problem swaps one undecided design
for another, and the findings resume.

On a construction, stop patching: **give the fixer a construction that dissolves the
findings, and let it argue back with evidence — journaled as you send it**:

```
progress.py note fixer.dispatched --text-file "$JOURNAL_TEXT_FILE"
```

The redirect exists in no reviewer's report — it is yours — and a pause while the
fixer applies it would otherwise resume into the very patch cycle it ended, or leave
half a replacement construction with no exact assignment for the scoped round to
verify.

**Before sending that redirect, ask: did the current fixer author the construction being
dissolved?**

- **Yes** → spawn a NEW fixer for this round. It owes nothing to what it did not write,
  while the incumbent has just spent two rounds defending it. The new fixer inherits the
  decisions log, gets the complete annotation set with `status=working`, becomes the
  incumbent, and is told plainly it did not write the thing being removed. **Set the
  outgoing fixer `superseded`, then archive and hide it right away.**
- **No — the construction came from the original document** → keep the incumbent: its
  accumulated reading of the code is worth keeping.

---

## When the human stops the run

`SKILL.md` carries the procedure, pause and abort alike. What this mode owes it is the step
called **the work in flight**.

**The spec is untracked at this point** — you commit it only at the close. It survives with
whatever the fixer had already written into it, reviewed or not, and **never delete it**:
an untracked document the human may still want is not yours to remove.

**Which is why you name it in the call.** `stop.sh abort` removes untracked files, and the
spec is one of them:

```sh
<workspace>/prompts/common/stop.sh abort <the spec path>
<workspace>/prompts/common/stop.sh pause
```

`pause` never takes an attempt here: nothing in this mode writes to the tree, so there is
no half-built task to preserve.

*Re-entered after an amendment, the spec is committed instead: a pause leaves the fixer's
edits in the tree, and an abort puts the file back to the amendment commit. **Name the
spec path in the abort call all the same** — it is the one dirty state this mode vouches
for, and the abort refuses a tree it cannot account for.*

| | |
|---|---|
| **In flight** | the fixer's edits, already in the file, and any reviewer reports on disk |
| **Pause** | everything stays. **The resume lands on the boundary the journal names and finishes what that boundary owes** — never a blanket next round. The routes are below. |
| **Abort** | the spec stays untracked and unreviewed. **Say so in the report**, with its path — a half-fixed spec that nobody flags is worse than no spec. |

Before interpreting any resume row, validate every durable SPEC boundary and immutable
artifact already present:

```sh
python3 "<workspace>/prompts/common/progress.py" spec-state-check
```

A refusal is ambiguous or damaged durable state. Stop and take its exact diagnostic to
the human. Do not infer a route from the remaining lines.

**The resume reads the validated notes and routes on the last boundary.** Every UNSETTLED child
was cancelled by the stop — one whose acceptance had already landed, a reviewer caught
between its accepted receipt and its ordinary retirement, was retired `done`, exactly
as its route owed. The reports, the decisions log and the journal survived, and they
say which of four states the loop was in. Providers are re-asked either way — the
pause rule in `SKILL.md` — since everything launched below is a new child.

**Partition direct `spec-fixer` rulings before these ordinary rows.** A current ready R
generation with no matching owner-linked `fixer.dispatched` writes that dispatch and
sends its exact authority artifact before the loop advances. Once dispatched, and until
the shared close recheck is accepted, it resumes through the ordinary round/fixer rows
below. An accepted shared recheck with no matching `ruling.applied` writes only the
terminal. A matching current-generation terminal removes that R from this partition;
never dispatch, prove or terminalize it again.

This partition consumes a product route, so `SKILL.md`'s run-wide authority-quiescence
predicate applies before its owner-linked dispatch or terminal. An unfinished authority
boundary anywhere in the run wins first. An accepted shared proof is a tail-only state:
write every permitted direct terminal before opening any new ordinary conflict.

- **Before the loop's first round.** On a first validation — no `round.opened` in the
  journal at all — pick the authoring back up where the stopping point says: S1's
  conversation, S2's document. The loop owes nothing yet, and no round is opened over
  an unfinished spec. **On a re-entry that test can never match** — the journal is
  append-only, and the first loop's rounds are in it for good — so it is sliced: **no
  `round.opened` since the `amendment.committed` that sent the spec back here** means
  the re-review is owed whole. There is no authoring to resume — the document already
  landed — so open the first re-entry round: the last `round.opened` plus one, every
  mandate, as the re-entry rules at the top of this file say.
- **A round is open and reports are missing** — its `round.opened` lists mandates with
  no `report.received` **carrying that round** — the receipt's own `--round` value,
  since mandates repeat from round to round: **finish the round.** Fresh reviewers for the
  missing mandates only, same round number, each partial file moved aside first — an
  accepted report stands, and its reviewer owes nothing.
- **The round is complete and its findings are not applied** — no `fixer.returned`
  since that round's reports: **recreate the fixer** — a fresh session, created as
  S3.4 says, inheriting the decisions log — **and dispatch the round's findings again,
  all of them — plus the text of any `fixer.dispatched` note since those reports,
  replayed verbatim**: a closing-check finding, a noticed finding, a redirect live in
  no report, and that note is their only durable copy. The dead fixer may have
  applied some: its replacement verifies every finding against the document as it
  stands, so what already landed is declined as moot and what did not lands now.
  Nothing is read off the half-written state.
- **A fixer return is accepted and its scoped round has not closed** — `fixer.returned`
  stands, and no scoped round's `report.received` since reports empty counts: **the
  scoped round is owed, and it runs before anything else.** Its findings and their
  exact edits are read from the decisions log — the cumulative record in the
  workspace, never anyone's memory.
- **A fixer return has its clean scoped round behind it** — `fixer.returned` stands,
  and a scoped round's `report.received` since it carries empty counts: **the full
  re-fan is owed, and it runs before anything else** — open it, the last
  `round.opened` plus one, every mandate. A clean scoped round is never the end:
  nobody has read the document the fixes produced, and scoped catches regression,
  never discovery.
- **The end condition is met and only the close remains** — the last FULL round's
  reports all arrived with nothing to fix at all, no fixer has touched the text
  since, **and no `fixer.dispatched` note sits unanswered** — one with no
  `fixer.returned` after it is an owed dispatch, not a met end: recreate the fixer,
  send that note's text, and the scoped-then-full sequence follows as always. Only
  then is nothing owed inside the loop, **and the close itself splits on one durable
  line**. No `spec.committed` since this loop began — since `spec.written` on
  a first validation, since the `amendment.committed` that sent the spec back here on
  a re-entry; the journal is append-only, and earlier loops and in-place rulings left
  their own lines — **: resume at *Closing the spec* from its first step, and launch
  nobody.** No reviewer is missing, a fixer dispatched zero findings would contradict
  the very condition that ended the loop, and the close's commit runs through its
  script, whose marker absorbs a half-done commit. **The line present: the close's
  commit is done and never re-runs.** If pending owner-linked `spec-fixer` assignments
  have no `decision.recheck.completed` for that close's exact `op`, regenerate the
  complete global proof. An accepted proof with missing `ruling.applied` lines writes
  only those terminals. An adverse proof with no later discrepancy dispatch writes that
  exact `fixer.dispatched` note and reopens the loop; its close never terminalizes an R.
  Once every pending assignment is applied, what remains is the report, the fixer retired
  `done` when one exists, and the checkpoint or the re-entry hand-back. A direct R whose
  matching current-generation terminal already exists never dispatches or closes again.

---

## Who runs on what

| Actor | Kind | Preset |
|---|---|---|
| `enumerator`, `ripple` | session | `ReviewerLight` |
| `verifier`, `feasibility`, `judge`, `scoped` | session | `Reviewer` |
| the fixer | session | `Fixer` |
| a new controller session, at the close | session | `Controller` |

**No subagent runs in this mode.** Every actor is a session, because every one of them
produces something the human must be able to reread on its own.

---

## Red flags

### While writing the spec — S1, S2

| What you are telling yourself | The reality |
|---|---|
| "Brainstorming says commit and invoke writing-plans" | Overridden. Commit when the end condition is met; construction follows here. |
| "The human approved the design in dialogue, the review is redundant" | Dialogue approval checks intent, not the written artefact. |
| "The spec should cite exact lines, it is more precise" | A line number rots on its own and costs a verification every round. Path plus symbol. |
| "Spelling the verification out in the spec is safer" | Steps are plan material. The spec names the means. |
| "The design is sound, feasibility is the plan's problem" | A contract nobody can build costs four rounds of planning and a spec amendment. Level it here, and verify the platform claim by running it. |
| "The standard says the browser does this" | No implementation may follow it. Verify against the real runtime. |

### While the loop runs — S3

| | |
|---|---|
| "It said READY, we are done" | READY is an opinion, not the end condition. |
| "One reviewer with all the axes is simpler" | Its attention goes to the biggest fish and the rest is never looked at. |
| "I'll reuse the reviewer, it already knows the document" | Its blind spots are stable. Reuse the **fixer**, never a reviewer. |
| "I'll give the reviewer the previous rounds' findings for context" | Three short lists only. A history anchors it onto old ground. |
| "I'll paste the mandate into the prompt, it is clearer" | A copy that will disagree with the file the day one is edited. Point at the files. |
| "The fix is applied, the round is done" | One scoped verification reviewer follows **every** fixer return. |
| "Only MINORs left, we can stop" | A MINOR-fixing round has produced an IMPORTANT, in text that very fix wrote. |
| "The rounds should get quieter every time" | Removing vagueness makes the next round louder. A spike after a precision pass is the mechanism working. |
| "The enumerations are green, the document is clean" | They exhaust themselves. Verifier, feasibility and judge run four reading modes and report a datum per mode. |
| "This edit is tiny, I'll make it myself" | Authoring ended your write access. Every edit goes through the fixer. |
| "They keep hitting this area — time to redirect the design" | First ask what they propose: mechanisms, or behaviours? Behaviours means nobody decided it. |
| "The fixer built this mechanism, it knows best how to remove it" | It has defended it for two rounds. Rotate the fixer, then retire the outgoing one. |
| "This contract is very complex, the plan will find a way" | `very complex` and `infeasible` are DECISIONs. The human chooses; the fixer never waters a contract down. |
| "It's a technical gap, not a product question" | Ask what fixing it makes the user SEE. |
| "This finding just needs a sensible default" | A default for something the human never decided **is** a product choice. |

### At the close

| | |
|---|---|
| "The spec is READY, I'll start building" | The gate is the human's: approval, then the question. |
| "The spec is READY — I'll ask the fixer to set the status line" | You set it. A fixer return mandates another scoped round, for a line no reviewer will read. |
| "I'm already editing the status, I'll fix this typo too" | That is a finding, and a finding reopens the loop. One line, nothing else. |
| "The loop is over, I'll clean up the workspace" | It lives through the whole feature. Only the human's *"the whole feature is done"* removes it. |
| "The human ruled it in conversation, that is enough" | A ruling that constrains this spec or an adjacent alternative belongs **in** the spec. |
