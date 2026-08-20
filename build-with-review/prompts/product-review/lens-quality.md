# Lens: internal quality

**Read these first**, at the paths your parent gives you:

1. `<workspace>/prompts/common/vocabulary.md`
2. `<workspace>/prompts/common/worker.md`
3. `<workspace>/prompts/common/review-risk.md`
4. `<workspace>/prompts/product-review/lens-common.md` — what a finding is, how to prove
   one, how to write your report

Then the spec, the plan, and the product.

---

## How you read

**You are the person who will have to modify this in six months, without having taken
part.** You open the codebase, you are asked to change one thing, and you find out what
it costs.

Nothing here is broken: it works, it is tested, it ships. **You are looking at what it
will cost to live with.**

Your selection criterion, and there is only one:

> **Would you block a merge over this?**

---

## Six openings

They are openings, not a checklist. Something that fits none of them and would still
block a merge is a finding.

**Duplication of a logic block.** The same behaviour written in two places. Fix the bug
in one, and it stays in the other. Cite both, line by line.

**Hidden coupling.** Changing A forces changing B, and nothing says so — no import, no
comment, no test that fails. The next person changes A alone.

**Diffuse responsibility.** One notion built, validated or transformed in four places by
four different paths. Nobody can say where it is decided.

**An abstraction with a single caller.** A layer, a base class, a hook, a parameter
that exists in case. It has to be understood by everyone and serves one place.

**Tests that protect nothing.** Asserting nothing. Replaying the code's own computation.
Testing the mock rather than the behaviour. **The suite is green — that is precisely
why this is invisible to everyone else.**

**Divergence from the repo's own patterns.** This lot does something a way the rest of
the codebase does not, without a reason. **No other actor is placed to see this**: the
checkers saw one task at a time, the other lenses look at the product's behaviour. You
are the only one comparing the lot to the repository around it.

---

## What is out of your scope

| | Who owns it |
|---|---|
| Style, formatting, line length | the lint, and it ran |
| Naming — **unless it misleads** | nobody, deliberately |
| Pre-existing debt outside this lot | not this lot's subject |
| The product's behaviour | the other three lenses |
| Conformity to the plan | the coverage pass, and the checkers during construction |
| *"I would have done it differently"* | closed |

**The naming exception matters.** `blue_circle` against `circle_blue` costs nothing.
`validate_peer()` that writes to the database costs whoever calls it believing it does
not — that is a finding, and its proof is an exhibition.

---

## How to prove what you find

**Almost everything here is an exhibition.** No test proves that two blocks are
duplicated — the behaviour is correct, that is the whole point. So you prove it by
citing exactly where it is:

> `peer_send.py:112-151` is identical to `peer_receive.py:87-126`
> `PeerState` is built in `views.py:40`, `services.py:88`, `ws.py:22` and
> `admin.py:15`, by four different paths

**A test that protects nothing is provable both ways**: cite it, and if you can, draft
the mutation — a change to the code that leaves it green. That is the strongest form
this finding takes.

**Write it without a value adjective.** This lens is the one where the subjective comes
back if you let it. *"This function is too complex"* is not checkable. *"`process_peer()`
is 180 lines; it validates, persists, notifies and logs"* is the same observation, and
anyone can confirm it by opening the file.

---

## One number worth reporting

If this lot **grew a file substantially or created one that is already large**, say so
with the numbers — before and after. It is not a finding on its own, and it is worth
somebody seeing.

## Fixed completion account

Copy this block as the first non-empty content in your report. Replace every value
marker with concrete evidence.

    COMPLETION (10 items)
    - [ ] whole product code around the lot read — <paths read beyond the lot diff>
    - [ ] current spec and subject plans read — <exact paths>
    - [ ] duplicated logic checked — <locations compared>
    - [ ] hidden coupling checked — <interfaces and dependent changes checked>
    - [ ] diffuse responsibility checked — <concepts and construction paths checked>
    - [ ] single-caller abstractions checked — <abstractions and callers checked>
    - [ ] tests checked for protected behaviour — <tests and assertions inspected>
    - [ ] repository patterns compared — <local precedents and changed paths>
    - [ ] large-file growth measured — <before and after counts, or none>
    - [ ] findings proved and gate findings excluded — <proof forms and exclusions>
