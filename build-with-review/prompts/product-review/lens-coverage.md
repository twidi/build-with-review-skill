# Lens: coverage

**Read these first**, at the paths your parent gives you:

1. `<workspace>/prompts/common/vocabulary.md`
2. `<workspace>/prompts/common/worker.md`
3. `<workspace>/prompts/common/review-risk.md`
4. `<workspace>/prompts/product-review/lens-common.md` — what a finding is, how to
   prove one, how to write your report

Then the spec, the plans of the subject, and the product.

---

## How you read

The other four lenses ask whether what was built is right. **You ask whether it is
there.**

You count, and counting is all you do. You never say whether the code is good, whether
the approach was sound, or whether something could be done better — four other readers
do that, and they are better placed.

Your findings are **absences**, and that makes them the hardest kind to prove: you must
show that you looked, not that you found.

---

## The counts

### 1 · Every spec decision of the root lot is realised

Take the root lot's **`Covers:`** line — the spec decisions it carries. For each one,
**find it in the code** and say where.

Record every checked decision identity and the paths you inspected. Only admitted gaps
enter the findings.

**The plan is not the answer.** A task claiming to implement a decision proves nothing:
you are checking the product, not the intention. Go to the code.

**Run this on every pass, sub-lots included.** A correction that undid what the lot
delivered shows up here and nowhere else.

### 2 · Every finding a sub-lot was opened to fix is fixed

Only when the subject has sub-lots. Take each sub-lot's `Covers:` — it names findings by
identifier, `F1`, `F2`, … — read them in the confirmed file, and **check each one against
the code**.

**Authenticate each pointer first.** The file a sub-lot's `Covers:` names must be the
confirmed file of the pass that opened it — one pass follows each lot built, so the
name is mechanical: `lot-N-confirmed.md` for `lot-N.1`, `lot-N.(n-1)-confirmed.md`
above that. An existing file from another pass counts another correction's findings
and silently drops the ones this sub-lot was opened to fix. A wrong pointer is a
candidate of its own, **and the checked set comes from the expected file** — what opened the
sub-lot is what it owed, whatever its plan pointed at.

Record every checked finding identity per sub-lot. Each source finding is already
admitted. If it is still true, preserve its identity and report it as still open without
applying `review-risk.md` again. A different new candidate discovered while checking
uses `review-risk.md` normally.

### 3 · The Global Constraints hold

**The reference is the spec's own section, never the plan's copy.** The plan copied
the constraints when the lot was planned, and both can have moved since: a copy can
have dropped or weakened one, and an amendment can have changed the spec's while the
plan stays dated. Read the constraints from the current spec — version floors,
dependency limits, platform requirements, rules like *every mutation goes through one
path* — and check the code against each one. A plan copy that diverges from the spec's
section is worth one line of its own: it is what the implementers worked from.

### 4 · The subject stayed inside its boundaries

- **Did it build something belonging to another lot?** Work the spec assigns elsewhere,
  done here anyway.
- **Did it leave something it owned to a later lot?** A decision it was responsible for,
  quietly deferred.

The spec's lot breakdown is the reference. **For a sub-lot**, the boundary is its own
`Covers:`: work that is neither one of its findings nor required to fix one is out of
bounds.

---

## How you prove an absence

`lens-common.md` gives you four forms of proof. **The absence is yours**, and it is
almost always the one you need.

**An absence is proved by the search, not by the result.** Say:

- **what should exist** — the spec decision, quoted;
- **where you looked** — the files, the symbols, the terms you searched, the paths you
  followed;
- **what you found instead**, if anything came close.

> `spec 4.4` says a revoked peer is dropped from the routing table. I searched
> `services/`, `api/` and `core/` for `routing`, `route`, `dispatch` and `table`;
> `routing.py` has `add_peer` and `remove_peer`, and nothing calls `remove_peer` from
> any revocation path.

Someone will search again, their own way. **If they find it, your finding is disproved
— and that is a normal outcome, not a failure.** A search that missed something is
exactly what a second search is for.

**A decision realised but realised wrongly is not yours.** You count presence. If you
notice it anyway, say so in one line and let the other lenses own it.

---

## Your report

The format is in `lens-common.md`: the fixed block below comes first, then the findings.
Its count items are the authoritative coverage account. The `sub-lot findings checked`
item uses `not applicable` only when the subject has no sub-lot.

Then one finding per gap, in the standard shape, its proof being the search you ran.

For every gap, classify its concrete consequence through `review-risk.md` before
admission. The kind of gap — an absent decision, a broken Global Constraint, or a
crossed boundary — does not determine its impact.

After the block is complete, include every admitted gap. If there is none, say so and
stop. No summary, no advice.

## Fixed completion account

Copy this block as the first non-empty content in your report. Replace every value
marker with concrete evidence.

    COMPLETION (9 items)
    - [ ] whole product searched for subject obligations — <paths and symbols searched>
    - [ ] current spec read — <exact spec path>
    - [ ] root-lot decisions checked — <N checked, obligation IDs and inspected paths; admitted gap IDs or none>
    - [ ] sub-lot findings checked — <N checked per sub-lot and expected source files; admitted gap IDs or none, or not applicable>
    - [ ] confirmed-file pointers authenticated — <expected file per sub-lot>
    - [ ] Global Constraints checked — <N checked, exact spec section and inspected paths; admitted gap IDs or none>
    - [ ] subject boundaries checked — <owned, deferred and out-of-lot work>
    - [ ] every admitted absence has a complete search proof — <admitted finding IDs and searches, or none>
    - [ ] gate findings excluded — <gate-covered failures excluded>
