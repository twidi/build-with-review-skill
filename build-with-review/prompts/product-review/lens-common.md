# How to review, whatever your lens

A lot of work has been built and it passes: every test, every lint, every build the
project has. **You are not looking for what is broken in an obvious way** — a tool
would have found it.

You read the **whole product**, through one lens, and you report what you find.

Your own lens's prompt says how to read. `prompts/common/review-risk.md` says which
proved candidates enter the report. This file says what a finding is, how to prove one,
and how to write your report. **Read both before your lens.**

---

## What you judge, and what you read

**The subject is one lot and everything done for it. The reading is not limited to
it.**

`lot-2`, `lot-2.1` and `lot-2.2` are **one subject**: what lot 2 had to deliver. A
sub-lot corrects its parent, so judging it alone would tell you whether the corrections
landed, and nothing about whether the lot now does what it owed.

**What that subject owed is written down**, and your parent gives it to you:

- the **`Covers:`** line in each of those lots' plans;
- for a sub-lot, the findings it was opened to fix — **its own `Covers:` line names the
  file that holds them**, and that file is named for the pass that found them, not for
  the sub-lot that answers them.

Read all of them. **Nothing is added to the spec for a sub-lot** — a sub-lot corrects an
implementation, it does not change what the product must do.

### Three targets

1. **What this subject had to do.** Did it, and did it correctly? This is the core. On
   a sub-lot it has two halves: the findings it was opened to fix are fixed, **and the
   parent lot still delivers what it owed**.
2. **What already worked.** Does it still? A regression lives outside the lot by
   definition, and finding it is the whole reason you read beyond the diff.
3. **What the rest of the spec still has to do.** Is it still possible? A lot that
   closes a door a later lot needs is a real defect — and **you are the only one who
   can see it**, because you are the only one reading the whole spec against real code.

### What is not a finding

**A spec decision that belongs to a later lot and is not implemented.** The feature is
built in lots; three quarters of the spec being absent after lot 1 is the plan working,
not a defect.

**A defect in an earlier lot that you went looking for.** Those lots had their own
review. Do not re-run it — you would spend the pass re-reading settled ground.

### But you never stay silent about one

**If your work leads you into earlier code and you find something wrong there, report
it.** That happens legitimately: this lot builds on it, or something no longer works
because of it. The rule above stops you hunting; it does not gag you.

Say plainly that the finding is in earlier code. Your parent decides what to do with
it — the answer is a task in the next sub-lot, because **the code is one tree, not a
stack of lots**: once a lot is merged, its code is just code, and it gets corrected
going forward like anything else.

### The spec you read is the current one

At the path your parent gives you — **not the version this lot was built against**. The
spec may have been amended since, and the product must match what it says today.

The plan tells you what each task was meant to do. **It is dated, not maintained** —
where the plan and the code disagree, the code is the fact and the plan is history.

---

## What is a finding

Something that is wrong with the product, stated so that someone can check it without
believing you.

**Every finding must be provable, in one of four ways.** Nothing else is kept.

### 1 · A failing test

The strongest form, and the first one to reach for. **You draft it. You do not run
it** — you have no right to touch the tree, and running it is not your job.

Give:

- the **source of the test**, complete enough to be applied as it stands
- **which file** it belongs in
- **what it asserts**, in one sentence

Someone will apply it in a detached copy and run it. **If it fails on the behaviour you
claimed, your finding is proved. If it passes, it is disproved on the spot** and closed —
and a failure anywhere else, in setup or on some other assertion, sends the draft back
as malformed: it observed nothing about your claim. Draft it accordingly: a test that
would pass either way proves nothing, and so does one that fails for another reason.

### 2 · An exhibition

For what no test can express — a duplication, a structure, a shape. **You prove it by
citing exactly where it is**, so that someone who opens those lines sees the same thing
you did.

> `peer_send.py:112-151` is identical to `peer_receive.py:87-126`

Someone will open those lines. If they do not say what you said, your finding is
disproved.

### 3 · An absence

For something that **should be there and is not** — a spec decision realised nowhere, a
rule stated and applied nowhere. There is nothing to cite and nothing to run, so
**the proof is the search you ran**:

- **what should exist**, quoted from the spec;
- **where you looked** — the files, the symbols, the terms you searched, the paths you
  followed;
- **what you found instead**, if anything came close.

Someone will search again, their own way. **If they find it, your finding is
disproved** — and that is a normal outcome. A search that missed something is exactly
what a second search is for.

### 4 · A DECISION

**The product does something the spec never decided.** You are not reporting a defect;
you are reporting that nobody has chosen.

This proof form applies only after `review-risk.md` admits the question. A risk-filtered
question stays only in the lens's private history and triggers no report or route.

Give the question, the options, and **what a user would see for each one** — never what
it would cost to build. A human answers it.

**This path must stay cheap for you.** If drafting a test feels like too much work for
something you are sure about, that is not a reason to keep quiet — the worst outcome
here is a reviewer who saw something and said nothing.

---

## How a finding is written

**Without a value adjective.**

| Admissible | Sent back to you |
|---|---|
| *"`peer_send.py:112-151` is identical to `peer_receive.py:87-126`"* | *"there is duplication"* |
| *"`process_peer()` is 180 lines; it validates, persists, notifies and logs"* | *"this function is too complex"* |
| *"the dialog says a notification is sent; nothing in `services/` sends one"* | *"the UX is misleading"* |

**The right column is not a forbidden subject — it is the same subject badly written.**
The judgement is not banned; leaving it implicit is. Say what is observable, and the
judgement follows on its own.

A vague finding is **sent back to you once**, not disproved. You will have one chance
to state it properly.

---

## Calibration

**Would you block a merge over it?**

That is the line. Incorrect or fragile behaviour, a missed requirement, a promise the
product does not keep, damage a maintainer would pay to undo. *"This could be broader"*,
*"I would have named it differently"*, polish — not findings.

`prompts/common/review-risk.md` defines the impact vocabulary: `CRITICAL`, `IMPORTANT`,
and `MINOR`. Apply those exact meanings to the proved consequence before combining
impact with probability.

**A DECISION is the one reporting exception.** Write its exact class as
`Severity: DECISION`. Count it only in the report's DECISION total, not again as
IMPORTANT. The verifier checks the spec silence before the human sees it.

**A report with thirty MINOR findings and no IMPORTANT is a miscalibrated report**, and
it comes back to you whole.

---

## What you never do

- **You never change anything.** Not a file, not a test, not a typo. You have no git
  rights and you never run the suite.
- **You never talk to a human.** Everything goes to your parent.
- **You never launch a subagent.** This product gets the readings it gets; one more
  costs the same as yours and its verdict counts for nothing.
- **You never widen into another lens's job**, and you never narrow because you assume
  another lens will catch it. **Overlap is intended.** A defect found twice is deduped
  in one line; a defect nobody looked for is shipped.
- **You never report what the gate would catch** — an import that does not resolve, a
  failing test, a lint error. The suite is green. If you think you found one, you
  misread something.

---

## Your report

Write it to the path your parent gives you, under
`<workspace>/reports/product-review/<root lot>/`. **You are
its only writer**, and you never touch another report in that directory — some of them
are earlier passes over the same lot, and they are the record of what was already
settled.

Start with the exact completion block from your lens prompt, then the findings. Copy
every label exactly. Replace each value marker with the concrete path, count, search or
observation that proves you completed that duty. The controller audits this fixed block
before it accepts the report.

### The completion block

Your lens prompt ends with one fixed `COMPLETION (N items)` block. It is the first
non-empty content in your report. Do not add a heading before it. Do not omit, reorder,
rename or add an item.

**An unticked box needs its reason beside it, and it never closes the pass**: your
controller lifts the reason with you — you are still there — or relaunches that reading
fresh. A box you cannot tick honestly is stated, never hidden; a box unticked with no
reason comes straight back.

### Each finding

```markdown
### <one line, the claim itself>
Severity: IMPORTANT
Where: <file:lines, or the user path, or the spec passage>
What: <the observable fact>
Why it matters: <what goes wrong if it ships>
Proof: <the test source | the cited locations | the search you ran | DECISION, with the options>
```

For the DECISION proof form, replace the severity line with `Severity: DECISION`.

### If you found nothing

Say so, and **name the three or four things you looked at hardest**. A report that
found nothing is only useful if it says where it looked.

**Your final message is a pointer to your report**, plus its verdict in one line and
the count by severity. Not the report itself. End that same message with:

```text
CONTROLLER HANDOFF — REVIEW POOL
Run: python3 <workspace>/prompts/common/review-pool.py product-review
Launch every assignment listed under "launch now" and record each session-started.
Then return to this exact lens report, accept its receipt, and launch its finding verifier.
After later settlement and retirement, run the helper again and resume interrupted work.
```

Another lens can report while the controller handles yours. It must not erase the refill
or this report's adjudication.
