# The plan document — format

One file per lot. **It lives in `<workspace>/plans/<lot>-plan.md`** and `plan-publish.sh`
copies it into `docs/plans/<date>-<feature>-<lot>-plan.md` just before each commit — the
date being the workspace's, for every lot of the feature. Read and write the workspace
copy; `docs/plans/` is an output.

Two writers, never overlapping:

- **the controller** writes the contract down to `To verify`, then the exact `### Design`
  placeholder, at C1, before any code exists;
- **each task's implementer** replaces that task's placeholder with the `### Design`
  contents, at C3.1, with the real tree in front of it.

Every task has exactly one structural `### Design` heading outside fenced examples from
its first plan commit. The heading is the physical ownership boundary between the
controller contract and implementer-owned Design. `plan-commit.sh` refuses the complete
plan if any task omits or duplicates it.

**Everything below is one worked example, on an invented Django feature.** Read the
shape, never the content: the sections, their order, and what each holds. Another
project's plan names other files, other constraints, other technologies.

---

## The document

```markdown
# Peer revocation — lot 1

Goal: the owner can revoke a peer, and a revoked peer receives nothing
Architecture: a lifecycle state in the database, one transition gate under a lock
Spec: docs/plans/2026-08-13-peer-revocation-design.md
Covers: spec 4.2 a revoked peer receives nothing
        spec 4.3 revocation is atomic

## Global Constraints
- Django 6, Python >= 3.13
- every peer state mutation goes through a row lock
- no destructive migration

## Responsibility map
core/models.py                  the peer's lifecycle fields
services/peer_lifecycle.py      NEW - the transitions, under a lock
api/peer_views.py               the owner endpoint
frontend/stores/peers.js        the revoked state on the client

---

## Task 1 - the lifecycle foundation

Descends from: spec 4.2 "a revoked peer receives nothing"
Depends on: -
Achieves:
  - the lifecycle state exists on the peer
  - an invalid transition is impossible in the database
  - the migration puts existing peers in the active state
Files: core/models.py, core/migrations/
To verify: a forbidden transition raises, an existing peer survives the migration

### Design
[written at C3.1 - see below]

### Disagreement
[optional - see below. Only for final-checker alternatives that both satisfy the plan]

---

## Task 2 - the transition gate

Descends from: spec 4.3 "revocation is atomic"
Depends on: task 1 - needs the lifecycle state to exist in the database
Achieves:
  - one single function moves a peer to revoked
  - the transition is atomic from read to write
  - two concurrent revocations produce one effect
Files: services/peer_lifecycle.py
To verify: two simultaneous revocations, only one takes effect

### Design
[written at C3.1 - see below]
```

**`Covers:`** is what this lot owes, one line each. **It is the reference every reviewer
is given**, so it must be readable without opening anything else.

- **a normal lot** lists the spec decisions it carries, as the spec's lot breakdown
  assigns them;
- **a sub-lot** lists the findings it was opened to fix, and points at the file holding
  them:
  ```
  Covers: F1, F3, F4 confirmed after lot-2
          <workspace>/reports/product-review/lot-2/lot-2-confirmed.md
  ```
  Findings carry stable identifiers, `F1`, `F2`, … A sub-lot's task writes
  `Descends from: F3` where a normal task names a spec decision.
  **Nothing is added to the spec for a sub-lot.** It corrects an implementation; it does
  not change what the product must do.

**Global Constraints** are copied verbatim from the spec — version floors, dependency
limits, naming and copy rules, platform requirements. One line each, exact values.
Every task implicitly includes them.

**`Depends on`** is `task N — why`, or `-`.

**`Achieves`** is three to six bullets.

---

## The `### Design` block

Written by the implementer at C3.1, into its own task's section only.

```markdown
### Design

**Step 1 - the enums and the fields**
core/models.py
Add `PeerLifecycle(models.TextChoices)`: ACTIVE, REVOKING, REVOKED.
Add on `Peer`: `lifecycle` (CharField, choices, default ACTIVE) and
`revoked_at` (DateTimeField, null).
`enabled` is not touched - it stays the manual activation flag, and confusing
the two is this task's trap.

**Step 2 - the database constraints**
core/models.py, Meta.constraints
Two CheckConstraints: `revoked_at` is non-null if and only if lifecycle is
REVOKED; lifecycle is one of the three enum values.
In the database, not in application code - see below.

**Step 3 - the migration**
core/migrations/
AddField for both columns, then the constraints. No RunPython: the ACTIVE
default covers existing rows, and a data migration here would fail on
databases where `enabled` is false for unrelated reasons.

**Exposed signatures**
Peer.lifecycle -> PeerLifecycle
Peer.revoked_at -> datetime | None

**Chosen / discarded**
Chosen: the constraint lives in the database.
Discarded: validation in `clean()` - `bulk_update` does not call it, so the
constraint would be bypassable through the very path task 2 will use.

**Behaviours tested**
- REVOKED without `revoked_at` is refused by the database
- an existing peer comes out ACTIVE after migration, `enabled` unchanged
- `bulk_update` cannot write an inconsistent state
```

Five parts, always in this order: **the steps**, one heading each · **exposed
signatures** · **chosen / discarded** · **behaviours tested**.

A step names the files it touches and says what it does there. Behaviours are
sentences about the product, never test names.

---

## The `### Disagreement` block

Written only when the implementer decided after design-checker or code-checker round 10.

```markdown
### Disagreement
#### Finding 1 — design alternative
The design checker held that the lock belongs in the service.
I kept it at the task boundary because both routes satisfy the accepted ownership rule.

#### Finding 2 — code alternative
The code checker held that the ownership test belongs in the service.
I kept it in the view because the service is also called by a channel with no request.
Both implementations satisfy the plan's lock constraint.
```

Use one exact `#### Finding N — design alternative` or
`#### Finding N — code alternative` section per alternative. Preserve the round-10
finding number. Each section says what the checker held, what was done instead, and why
the accepted plan permits both. A refuted finding and an accepted defect do not belong
here.

**Its own heading, never buried inside `Design`.** The product review has to find it
without reading the whole plan.

---

## Who reads what — this is what stops the plan from rotting

| Block | Read by |
|---|---|
| `Covers:` | every reviewer of this lot |
| `Depends on` | **the controller and the completeness checker only** — ordering and graph closure |
| `Achieves`, `Files`, `To verify` | the implementer of **that** task |
| `### Design` | its own implementer on the next attempt, and the design checker |
| `### Disagreement` | the product review |
| **What an earlier task actually produced** | **the code. Never the plan.** |

The last row is the one that matters:

> **The plan tells you what you must achieve. The code tells you what exists.** Never look
> in the plan for something the code can tell you.

**That is what lets the plan be dated instead of maintained.** A `### Design` written at
task 1 may well be out of date by task 6, and it costs nothing, because nobody whose work
depends on it reads it. Keeping it in sync would be the real trap: a document that must
track the code, and that is always the copy that rots.

---

## What never appears anywhere in this file

- function bodies
- commands
- line numbers
- signatures, **except** in a `Design` block's *exposed signatures*, where they are
  real and decided against the tree

Illustrative code is allowed outside a `Design` block, and is never prescriptive. Say
so where you use it.
