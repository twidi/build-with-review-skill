# Lens: by meaning, not by string

**Read these first**, at the paths your parent gives you:

1. `<workspace>/prompts/common/vocabulary.md`
2. `<workspace>/prompts/common/worker.md`
3. `<workspace>/prompts/common/review-risk.md`
4. `<workspace>/prompts/product-review/lens-common.md` — what a finding is, how to prove
   one, how to write your report

Then the spec, the plan, and the product.

---

## How you read

**A concept is not a word.** It appears under several names, in several layers, in
several languages — a database column, a model field, an API key, a store property, a
label on screen, a line of spec. **Your job is to sweep one concept through all of
them and find where the product stops agreeing with itself.**

A grep on one phrasing finds one family member and misses the rest. That is the failure
this lens exists to avoid.

Work concept by concept:

1. **Take a concept the spec names.** Start with the ones this lot is about, then the
   ones it touches.
2. **List every form it takes**, everywhere. The stored name, the transported name, the
   displayed name, the tested name. Include the ones that mean the same thing under a
   different word, and the ones that use the same word for something else.
3. **Follow it end to end**, from where it is created to where a user sees it.
4. **Ask, at every hop: is this still the same thing?**

---

## What you are looking for

**The same word for two things.** `status` meaning the lifecycle state in one module
and the HTTP result in another, and somewhere a place where the two meet.

**Two words for the same thing**, with a boundary where a translation should happen and
does not, or happens twice.

**A concept that loses a piece as it travels.** Five states in the database, three in
the API, two on screen — and nothing saying which collapse into which.

**A default that means something different at each layer.** Null, empty, absent and
zero are four things; a concept that treats them as one somewhere and as four elsewhere
will produce a defect nobody can reproduce.

**A rule stated once and applied unevenly.** The spec says every mutation goes through
one path; find the mutation that does not.

**A name that lies.** A function whose name says one thing and whose body does another.
Not a style question — the next person to call it will be wrong.

---

## How to prove what you find

**Most of it is an exhibition**, and it is the natural form for this lens: cite the two
or three places, line by line, and the disagreement is visible.

> `models.py:88` stores `state` with five values; `serializers.py:34` maps them onto
> three; `stores/peers.js:12` expects two

**Some of it is a test** — where the disagreement produces a wrong result for someone.
Draft it.

**Some of it is a DECISION** — where the spec itself uses one word for two things, and
nobody has decided which. That is not yours to settle.

---

## What you do not do

**You do not report naming preferences.** A concept named differently in two layers is
not a finding if both are consistent and the boundary translates. It becomes one when
something crosses that boundary unchanged, or when a name says something false.

**You do not stop at the first hit.** One inconsistency in a concept usually means
three; sweep the whole family before moving to the next concept.

## Fixed completion account

Copy this block as the first non-empty content in your report. Replace every value
marker with concrete evidence.

    COMPLETION (10 items)
    - [ ] whole product read by concept — <product areas read beyond the lot diff>
    - [ ] current spec read — <exact spec path>
    - [ ] subject concepts inventoried — <concepts traced>
    - [ ] storage forms traced — <fields, records or files>
    - [ ] transport forms traced — <APIs, messages or events>
    - [ ] display and test forms traced — <UI labels and tests>
    - [ ] same words with different meanings checked — <terms and boundaries>
    - [ ] different words with the same meaning checked — <translations and boundaries>
    - [ ] null, empty, absent, zero and defaults checked — <states and observed rules>
    - [ ] whole concept families swept and findings proved — <family endpoints and proofs>
