# The journal — how to call `progress.py`

**Every agent that launches something writes to the journal**, so every one of them reads
this file. It says how to call the script and what to be careful about. **It never says
what to record**: the exact command is written where you must call it, in your mode's file
or in your own prompt.

```
<workspace>/prompts/common/progress.py
```

**`progress.py` at a call site is a shorthand for that full path.** Nothing installs the
script and nothing puts it on `PATH`: the command you type is always

```
python3 "<workspace>/prompts/common/progress.py" <what the call site says>
```

The call site gives the subcommand and its flags exactly; the invocation is always this
one — **the script path quoted**, like every path in every command here: nothing
constrains a repository path to shell-safe characters.

---

## What it is

**One file, `<workspace>/progress.jsonl`, one line per event, appended and never
rewritten.** It is the run's memory: what happened, when, and what was decided.

Several agents write to it at once. The script handles that; you never open the file
yourself, and **you never write to it by hand.**

**Some subcommands also do the thing they record.** Changing a session's status, retiring
one — the script performs the action and writes the line in the same call. That is the
point: a record that is produced by the act itself cannot drift from it. **So you do not
make the TwiCC call separately.**

`session-started` also owns the short visibility interval after a successful child
creation. It retries only the exact not-found result for the returned id. If that
bounded wait still refuses, keep the exact id, create no replacement, and retry only the
same `session-started` call after the child becomes readable. The refused call journals
nothing.

A Construction implementer's `session-started` also requires the exact live
`attempt-in-flight` identity. It freezes that identity and its attempt-base account. If
the physical session exists without the marker, do not recreate the marker. Stop and
retire that session. The Construction mode gives the one helper-owned abandonment route.

---

## Two things you never pass

**Your own identity.** The script resolves the session it is running in, by itself. There
is no id to give and no way to attribute an event to the wrong session.

**Your context.** It reads your annotations and fills in the mode, the lot, the task, the
attempt, the round, the mandate. **Never repeat what your annotations already say** — a
value typed twice is a value that will disagree with itself.

### Flags fill what your annotations do not say

When you record something about a child whose context is not yours — a subagent working on
another actor's subject — name the difference, and name it with **the same words the
annotations use**. That is what lets a reader group the two together afterwards.

The command you are given at the call site says which flags it needs. **If it names none,
pass none.**

---

## Text transport — shell arguments are only for fixed workflow text

| | Outer quotes | Never inside |
|---|---|---|
| **`--data`**, structured payload | **single** `'…'` | **an apostrophe** — so **no free text**, only numbers, slugs and identifiers |
| **`--text`**, a fixed workflow literal, identifier or path | **double** `"…"` | `"` · `$` · `` ` `` · `\` · a newline |

JSON is full of double quotes and carries no apostrophe **as long as nothing free-form
goes into it**. A short fixed `--text` value is safe only when the workflow itself gives
its complete contents and none of the forbidden characters can occur.

**Every human answer, subagent finding, discrepancy, diagnostic analysis, tool output,
code excerpt or other arbitrary text uses `--text-file`.** The shell sees only the file
path. It never parses the payload.

Use this procedure:

```sh
JOURNAL_TEXT_FILE=$(mktemp "${TMPDIR:-/tmp}/bwr-journal-text.XXXXXXXX")
```

Write the exact UTF-8 payload to that real file with your provider's file-write or edit
tool. **Do not use a shell heredoc, `printf`, `echo`, command substitution or shell
redirection to put arbitrary text into it.** Then run:

```sh
python3 <workspace>/prompts/common/progress.py note ruling \
  --data '{"ruling":"R1","route":"spec-in-place"}' \
  --text-file "$JOURNAL_TEXT_FILE"
JOURNAL_RC=$?
rm -f -- "$JOURNAL_TEXT_FILE"
[ "$JOURNAL_RC" -eq 0 ]
```

`progress.py` reads one real regular UTF-8 file and preserves its complete contents,
including every newline. `--text` and `--text-file` are mutually exclusive. Remove the
temporary only after the call has consumed it. A physical line equal to any heredoc word
has no special meaning because no payload byte is shell source.

---

## The vocabulary is closed, and the script enforces it

Every kind of event has a name, and **the script refuses one it does not know**.

`reach.recovery.authorized` is one scoped operational authority. It binds one reviewed
Reach contract correction to one logical sweep after its original and replacement owners
both retire unsuccessfully and `not-converging` is durable. It authorizes one later
physical Reach owner. It is never `resumed`: it cannot release a run pause or cross an
abort boundary.

An identified direct `ruling` has a second closed vocabulary inside its data: exactly
`closed`, `spec-in-place`, `amendment`, `spec-fixer`, or `amendment-fixer`. The script
also authenticates every owner-linked fixer dispatch, direct amendment opening and
`ruling.applied` against that R's current authority artifact and route-specific proof.
Never abbreviate or invent a synonym.

Those consumers also share the run-wide authority-quiescence check used by bound spec
commits. A fresh call is refused while any identified ruling, batch, conflict, breach,
adverse SPEC-loop proof or current spec-edit authorization owns an unfinished higher-
precedence state. Grouped-batch amendment openings and batch terminals use the same gate.
The state-building conflict and breach events remain writable. An ordinary conflict
opening is refused only when an already accepted direct route still owes its exact
terminal; write that tail first.

Every global product-authority boundary has a required typed identity. Rulings use
`R<N>`; batches use a positive integer; conflicts use `R<N>` or `B<N>` plus a positive
integer; rechecks and edit authorizations also name their exact operation or basis.
`progress.py` refuses a missing, string-for-integer or malformed identity before append.
An older damaged journal fails closed at every consumer: an unkeyable boundary is never
ignored and never supersedes an earlier authorization. A `ruling` with no `ruling` key
remains an operational human choice and is not a product-authority boundary.

Every direct or batch post-commit recheck consumes one exact bound `spec.committed`
operation. Its SHA, pre-commit authority generation, complete owner action state and
immutable proof artifact must all match. A batch recheck also replaces every immutable
source item. Only `accepted:true` with `missing:[]` changes current route state.

SPEC review boundaries are admitted in the same way. `spec.written` freezes one real
project-relative document, its exact sequential `## Lot N — title` manifest and SHA-256.
Each `round.opened` is the previous maximum plus one, has the exact phase-owned mandate
list, and publishes one immutable spec snapshot. A round receipt audits the fixed
completion block, exact report path, finding headings, verdict, counts and SHA-256.
`fixer.returned` consumes every current assignment through one immutable correction
account and resulting spec snapshot. The unbound spec close consumes only a clean full
round and permits only its status-line delta.

A run that starts directly in Construction has no `spec.written`. A Construction-origin
`amendment.opened` freezes one schema-1 `construction_source` instead. It binds the exact
Construction `run.started`, current lot origin, latest `plan.written`, committed plan and
its one structural root `Spec:` source, plus both committed hashes. Append-time admission
requires the live plan and spec to equal those committed bytes. Historical consumers use
the frozen commit and objects without requiring it to remain current `HEAD`.

An `owner:"spec-loop"` recheck is not an exception. It follows one exact shared close.
It names every current pending `spec-fixer` authority, preserves the complete run-wide
answer state, and consumes one fresh bracketed finding-verifier result per pending R.
Its JSON artifact equals the structured result and is frozen by `artifact_sha256`.

A conflict opening names known standing answers. Its settlement covers every opened
identity with the closed action, status and route vocabulary. Its ready event carries the
complete current-owner action state and the resolution artifact's SHA-256. The script
refuses omitted, added or contradictory actions and changed artifact bytes.

Product-review phase terminals are also admitted, not merely recorded. `pass.opened`
consumes one exact task success for the built lot, or one exact amendment-owned
controller successor after a voided pass. A task-owned first pass also consumes the
matching workspace and committed task manifest, every stable task result, the final
task result and the exact `lot.built` boundary. It cannot hide an open prior pass. Each
lens has one fixed completion account. `report.received` audits it, derives the four
typed counts from every exact structured report finding, and freezes the pass
commit, gate and report SHA-256. Each finding-verifier physical call consumes those same
identities, and `verify-open.sh` refuses any other commit or report generation before
touching its detached copy. Calls alternate start and terminal. A terminal is one complete
finding account or one exact `error`, `empty`, `lost` or `unusable` result. An unusable
terminal never settles that receipt. Each unusable terminal permits the next diagnosed
physical call against the same receipt. The PRODUCT verifier has no fixed physical-call
ceiling. A complete result permits no later call. An ordinary `pass.closed` consumes the latest exact
pass opening, five settled report receipts and their final completed verifier calls. A positive close also authenticates its allocation,
confirmed artifact, plan and carried batch work. A clean close refuses any allocation or
unfinished answer work. A voided close consumes one exact product-review amendment
opening. That opening separates completed preservation carries from unfulfilled route
owners. A completed amendment answer remains a carry and never selects AMENDMENT again.
The opening freezes the exact current Correction Round allocation, `reclassify`
supersession, or null predecessor. No later allocation can compete with it. A current
Correction Round allocation void is helper-owned: its recoverable
owner moves every present canonical confirmed and correction artifact before appending
the exact physical close account. A `reclassify` supersession reuses its authenticated
moved account, and a null correction predecessor moves nothing. `lot.delivered` consumes
only the current clean close, its reviewed SHA, every complete non-voided pass over the
root subject — including schema-2 Correction successor passes and excluding every voided
generation — and every required batch-close tail.

`sublot.opened` consumes one exact positive close and its exact allocation. It is the
sub-lot's only CONSTRUCTION origin. Plan publication, attempt start, `lot.built` and the
first PRODUCT REVIEW pass all replay that origin. A missing or changed close/open pair
refuses before the next durable boundary. A root lot has no such origin.

If it rejects yours, you have the wrong name — **look it up where the call was given to
you, and never invent a variant.** A vocabulary that is not enforced is not a vocabulary,
and a dashboard cannot count what it cannot name.

Some kinds require a structured payload; the call site gives you its exact shape. **In
that shape, `<…>` is a marker you fill with the real value** — never typed verbatim, and
never left as the sample it replaces. A value written without a marker is exact, and you
type it as written.

---

## Reading it back

```
python3 "<workspace>/prompts/common/progress.py" notes
```

Prints only the notes — timestamped, with who wrote each one. **That is what a session
reads after a compaction**, or when it takes a run over: what the human ruled, what was
refuted and by what, and where the work stands. You never parse the journal yourself.

The watchdog has one separate read-only query:

```
python3 "<workspace>/prompts/common/progress.py" subagents-open
```

It prints one JSON array with every exact unsettled provider-subagent bracket. It repairs
nothing, refreshes nothing and writes nothing. The watchdog uses it; agents do not parse
the journal to reconstruct this state.

Every successful `subagent-started` has one exact physical terminal before another call
uses the same identity. A supported unavailable-result route writes an exact unusable
terminal first. Discovery, gate execution, SPEC-loop verification, completeness and
amendment consolidation all define that route at their direct call site.

Every successful `subagent-started` also prints `SUBAGENT OPEN` guidance on stderr. The
opening's defined stdout stays unchanged. Keep the provider-native handle and close the
exact bracket before acting on its result.

---

## What you never do

- **You never write `progress.jsonl` by hand**, and you never edit a line already in it.
- **You never record a duration.** The script stamps the time; whoever reads the journal
  subtracts. A duration you write down is a duration that can be wrong.
- **You never skip a call because it seems minor.** A missing line is a hole nobody can see
  afterwards — the reader has no way to tell it apart from a thing that never happened.
- **You never refresh anything for the dashboard.** The script does it, last, on its own.

**If a call fails: run the same call once more — every command here is safe to repeat.**
A status or a retirement re-run re-performs TwiCC changes that are idempotent and writes
the line that was missing; a note that failed **with a message** wrote nothing, so its
retry writes one line — every refusal this script prints happens before anything is
appended, and the one failure that can follow an append says so in its own message. **The failure message says where it stopped**: `NOTHING WAS JOURNALED` means
the act did not happen either — that is not a logging problem, and after a second
failure it goes to your parent as a blocker. An error that comes AFTER the TwiCC change
— a raw crash on the journal write — means the act happened and only the line is
missing: the retry supplies it.

**One window is the exception: a call that died printing nothing** — killed by a stop,
cut by the harness. It can have appended its line before dying, and no message exists to
say which. **Before retrying that one, read the tail** — `notes` prints the last
lines — and a line already there means the call landed: a second one would be read as a
second event, and the bounded routes count lines. The session events stay invisible to
`notes`; a duplicated one costs the dashboard a stray line and the routing nothing, so
those retry freely.
