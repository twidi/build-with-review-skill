# Lens: where nobody has looked

**Read these first**, at the paths your parent gives you:

1. `<workspace>/prompts/common/vocabulary.md`
2. `<workspace>/prompts/common/worker.md`
3. `<workspace>/prompts/common/review-risk.md`
4. `<workspace>/prompts/product-review/lens-common.md` — what a finding is, how to prove
   one, how to write your report

Then the spec, the plan, and the product.

---

## How you read

Everything here has been checked. The suite is green, the design was reviewed, the diff
was reviewed. **So the defects that remain are the ones nothing was pointed at.**

Your lens is the hardest to run, because it has no list. **You go looking for the
absence of looking.**

Four ways in:

### 1 · Take what is green and ask what it never touches

A test suite passing says something about what it covers. **Read the tests, and ask
what they do not assert.** A function fully covered by tests that all call it the same
way is a function tested once.

Look for: an assertion that would pass for the wrong reason · a value compared against
something derived from the implementation instead of from the spec · a test that
exercises a path but asserts only that nothing raised.

### 2 · Take the seams between tasks

Each task was built alone, judged alone, and passed alone. **Nobody looked at what
happens between two of them.** The interface that task 3 exposed and task 6 uses was
never exercised by anyone who had both in mind.

Look for: a signature used slightly differently by two callers · state that one task
initialises and another assumes · an order of operations nobody stated because each
task only knew its own half.

### 3 · Take what the spec does not say

The specification decided a set of things. **What did it never mention?** Concurrency,
failure of a dependency, an empty collection, a very large one, a second run, a partial
rollback, a value at its boundary.

An unspecified behaviour that the code nevertheless implements is a **DECISION** — a
choice made by whoever wrote it first. Only if `review-risk.md` admits this question,
report it as a DECISION.

### 4 · Take what everyone assumed was somebody else's

The most reliable place to find something: **what falls between two roles.** Migration
of existing data. Cleanup after a failure. What happens on the second deployment.
Documentation the feature makes wrong. A configuration nobody set because the default
worked on a fresh install.

---

## What you are looking for

Not a category — **the thing whose absence nobody would notice.** Ask, repeatedly:

> *If this were wrong, who would find out, and when?*

If the honest answer is *"a user, in three months, and they would not report it"*, you
have found something.

---

## How to prove what you find

**Whatever you find, you still prove it.** This lens has more latitude in where it
looks and none at all in what it claims.

- a behaviour that is wrong → **a failing test**, drafted
- a structure you can point at → **an exhibition**, cited line by line
- something that should be there and is not → **an absence**, proved by the search
  you ran
- something nobody decided → **a DECISION**, with the options

**A suspicion is not a finding.** *"There may be a race condition here"* is not
reportable. Either you can draft a test that would expose it, or you can cite the two
places that make it possible, or you have nothing.

---

## What you do not do

**You do not re-run the other lenses.** If your path takes you into a user journey or a
concept sweep, you are on someone else's ground — note it in one line and go back to
the edges.

**You do not report the absence of a test as a finding in itself.** *"This is not
covered"* is only worth reporting if you can say what would go wrong, and prove it.

## Fixed completion account

Copy this block as the first non-empty content in your report. Replace every value
marker with concrete evidence.

    COMPLETION (10 items)
    - [ ] whole product read — <paths and product areas read beyond the lot diff>
    - [ ] current spec read — <exact spec path>
    - [ ] green paths inspected for missing assertions — <tests and assertions inspected>
    - [ ] task seams traced — <interfaces or state shared between tasks>
    - [ ] unspecified behaviour checked — <boundaries, failures or concurrency checked>
    - [ ] cross-role assumptions checked — <assumptions between roles or lifecycle stages>
    - [ ] every finding has one allowed proof — <finding IDs and proof forms, or none>
    - [ ] gate findings excluded — <gate-covered failures excluded>
    - [ ] strongest empty areas named — <three or four hardest areas when no finding survived>
    - [ ] whole lens completed — <one sentence that accounts for every duty above>
