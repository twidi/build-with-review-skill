#!/usr/bin/env bash
# C3.8: preserve the failed attempt where it can still be read, put the tree
# back to the last validated task, and open the attempt as a real checkout for
# whoever has to diagnose it.
#
# The preserving commit never enters the history: the reset takes the branch
# back, and only the try-<K> ref keeps that commit alive.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/disposable-worktree.sh"
source "$WORKSPACE/prompts/common/attempt-closer.sh"

[ $# -eq 4 ] \
    || die "4 arguments expected, $# given — usage: attempt-failed.sh <lot> <task N> <attempt K> <C3.9a|C3.9b|C3.9c|C3.9d>"
LOT=$1 N=$2 K=$3 CLASS=$4
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\`"
[[ $K =~ ^[1-9][0-9]*$ ]] || die "the attempt number must be a positive integer without leading zeros, got \`$K\`"
case "$CLASS" in
    C3.9a|C3.9b|C3.9c|C3.9d) ;;
    *) die "unknown classification \`$CLASS\` — one of C3.9a, C3.9b, C3.9c, C3.9d" ;;
esac

RUN_NAME=$(basename "$WORKSPACE")
RUN="refs/bwr/$RUN_NAME"                  # this run's own ref namespace — see vocabulary.md
FEATURE=${RUN_NAME#????-??-??-}           # for the commit subject, which a human reads

TRY="$RUN/$LOT/task-$N-try-$K"
# Inside this repository's own ignored ground, never under a shared /tmp. The
# run's name separates two features of one repository; the location separates
# two repositories that share a workspace name — /tmp is global, and a path
# built from the name alone would let one repository adopt, refuse over, or
# destroy another's checkout.
cd "$REPO"

# The preserve below stages everything and resets to attempt-base. It must not
# absorb or unland a controller-owned operation whose marker still owns the
# workspace. Refuse before binding this closer or changing any repository state.
if ! controller_operation_refuse_pending "$WORKSPACE"; then
    die "$CONTROLLER_OPERATION_ERROR. Rerun that owner first, then retry this failure closer.
Nothing was moved, staged, recorded or bound."
fi

# Where the branch goes back to — the attempt's own start mark, and NOT the
# previous task's ref. attempt-base..HEAD is the implementer's own ground:
# every commit the controller makes mid-attempt moves the mark with it, so
# whatever sits above the mark is the attempt's — nothing in the common case,
# one commit or more when it was stopped or refused after committing, with or
# without edits on top — and all of it must leave the branch once preserved.
# Resetting to `task-<N-1>` instead would also take off the branch anything the
# controller committed since: an amendment lands there, and would be silently
# unlanded by the next failure.
MARK="$RUN/$LOT/attempt-base"
git rev-parse --verify --quiet "$MARK" >/dev/null \
    || die "$MARK does not exist — this attempt was never marked as started"
BASE=$(git rev-parse "$MARK")

# The identity file binds the mark to a task and an attempt. Present, it must
# match all three values: preserving the real attempt under another identity
# records its code, its checkout and its journal line where nobody will look.
INFLIGHT="$WORKSPACE/attempt-in-flight"
[ -f "$INFLIGHT" ] || die "no attempt is in flight — the identity file is absent: either
no attempt was started this way, or its closing already completed. An absent proof is a
refusal, never a bypass. Nothing was moved, and nothing was staged."
F_LOT=; F_N=; F_K=
read -r F_LOT F_N F_K < "$INFLIGHT" || true
[ "$F_LOT $F_N $F_K" = "$LOT $N $K" ] || die "the attempt in flight is $F_LOT task $F_N
attempt $F_K — this call says $LOT task $N attempt $K. The preserve takes the attempt's
own identity. Nothing was moved, and nothing was staged."

# A checker findings batch owns failure admission before this closer binds or stages
# anything. The shared validator refuses an unsettled batch. It requires
# one exact immutable failure handoff for accepted items, or one exact blocker terminal
# for a controller-owned Design or code-review contract defect.
FAILURE_DATA=$("$WORKSPACE/prompts/common/progress.py" construction-failure-check \
    "$LOT" "$N" "$K" "$CLASS") \
    || die "the failure is not admitted by the exact checker state.
Settle implementer-owned Design or code round 10, or record the exact controller-owned
Design or code blocker at the round where it was found, before the plan changes.
An open Construction AMENDMENT can instead supersede one unresolved current checker
batch after its clean Reach close and one exact controller-owned task-contract change.
When it accepts an implementer-owned defect, complete its authenticated failure report
first. Nothing was moved, staged, recorded or bound."

# A result ref proves that one gesture of a closer landed. It never chooses
# that closer. Freeze the exact failure call before the first preserve/reset
# gesture, and refuse any terminal outcome that already chose another closer
# or another classification for this attempt.
if SHA=$(git rev-parse --verify --quiet "$RUN/$LOT/task-$N"); then
    die "$RUN/$LOT/task-$N already records a successful closer at $SHA while
attempt-in-flight still owns its tail. Recover the final gate with gate-check.sh find-task
$LOT $N $K $SHA, then rerun attempt-succeeded.sh $LOT $N $SHA <that op>.
Nothing was moved, and nothing was staged."
fi
JOURNAL="$WORKSPACE/progress.jsonl"
if [ -f "$JOURNAL" ] \
   && awk -v l="\"lot\":\"$LOT\"" -v t="\"task\":$N," \
          -v a1="\"attempt\":$K," -v a2="\"attempt\":$K}" \
          -v class="$CLASS" '
        {
            identity = index($0,l) && index($0,t) && (index($0,a1) || index($0,a2))
            terminal = index($0,"\"kind\":\"attempt.succeeded\"") \
                    || index($0,"\"kind\":\"attempt.failed\"") \
                    || index($0,"\"kind\":\"paused\"") \
                    || index($0,"\"kind\":\"aborted\"")
            allowed = index($0,"\"kind\":\"attempt.failed\"") \
                   && index($0,"\"classification\":\"" class "\"")
            if (identity && terminal && !allowed) {found=1; exit}
        }
        END {exit !found}' "$JOURNAL"; then
    die "attempt $K of $LOT task $N already has a different terminal outcome.
This failure call cannot replace its closer or classification. Nothing was moved, and
nothing was staged."
fi
if ! attempt_closer_bind "$INFLIGHT" failure prompts/construction/attempt-failed.sh \
    "$LOT" "$N" "$K" "$CLASS"; then
    die "$ATTEMPT_CLOSER_ERROR. Rerun only the frozen call. Nothing was moved, and
nothing was staged."
fi

disposable_ground_prepare "$REPO"
TMP="$DISPOSABLE_GROUND/bwr-$RUN_NAME-$LOT-task-$N-try-$K"

# The precondition is checked BEFORE anything is committed or reset. Dying
# halfway would leave the tree already moved, with no way to replay what was
# lost. (`[ -e … ] && die …` would itself exit under `set -e` when the test is
# FALSE: the && list returns 1 and nothing consumes it.)
#
# Prune first: a registration can outlive its checkout — a /tmp sweep, a
# killed operation — and `worktree add` refuses a path Git still owns even
# when its directory is gone. That refusal would land at the END, after the
# preserve and the reset.
git worktree prune
ALREADY_OPEN=
if [ -e "$TMP" ] || [ -L "$TMP" ]; then
    disposable_require_owned_worktree "$REPO" "$DISPOSABLE_GROUND" "$TMP"
    # An earlier call of this same failure can have opened it and died before
    # printing: a checkout sitting exactly on this attempt's try ref is that
    # call's finished half — answered for, never refused.
    if git rev-parse --verify --quiet "$TRY" >/dev/null \
       && [ "$(git -C "$TMP" rev-parse HEAD 2>/dev/null)" = "$(git rev-parse "$TRY")" ]; then
        ALREADY_OPEN=1
    else
        die "$TMP already exists — close that diagnostic worktree before retrying"
    fi
else
    disposable_assert_available "$REPO" "$DISPOSABLE_GROUND" "$TMP"
fi

# Everything, on purpose: this preserves a whole state that is about to be
# erased, and the commit subject says so. One of the two exceptions to the rule
# that a commit always names its paths.
#
# It is only sound because C0 refused to start on a tree holding somebody else's
# uncommitted work — and because that check opens a standing contract: the tree
# is the run's until the run stops, and a human who must touch it pauses first.
# Work that arrives outside that contract cannot be told from the attempt's own;
# it rides the preserve onto the try ref with the rest, recoverable there.
# The conflict is checked BEFORE anything is staged: a refusal must leave the
# index exactly as it found it — the human it sends the state to has to see
# the staging that existed when the conflict arose, not one this script made.
if git rev-parse --verify --quiet "$TRY" >/dev/null \
   && { [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$BASE" ]; }; then
    die "$TRY already exists while the tree holds fresh changes — an earlier
preserve of this attempt and new work both claim one name, and neither is this
script's to overwrite or merge. Nothing was moved, and nothing was staged; ask
the human."
fi

git add -A
if git diff --cached --quiet && [ "$(git rev-parse HEAD)" = "$BASE" ]; then
    # A clean tree at the mark reads as an untouched attempt — unless an
    # earlier call of this same failure was killed after its preserve and
    # reset: its try ref is then the half already done, and this call must
    # recognise it, not journal that the attempt left nothing beside it.
    if git rev-parse --verify --quiet "$TRY" >/dev/null; then
        PRESERVED=$TRY
    else
        git reset -q --hard "$BASE"
        PRESERVED=
    fi
else
    if ! git diff --cached --quiet; then
        # --no-verify: this commit is bookkeeping behind a ref, never history —
        # the project's message convention governs the history humans read, and
        # a hook must not kill a preserve halfway.
        git commit -q --no-verify -m "$FEATURE $LOT task $N attempt $K — FAILED"
    fi
    git update-ref "$TRY" HEAD
    git reset -q --hard "$BASE"
    PRESERVED=$TRY
fi

# The failure and its classification are true from here on, whatever happens
# next. The line goes in before the worktree so that a worktree which cannot be
# created leaves a correct journal and a loud error, never a silent hole.
#
# The task travels as a flag and the attempt in the data: the caller is the
# controller, whose annotations name neither — without them, a journal read
# after a compaction says WHAT failed but not WHERE, and the route that
# relaunches depends on both.
# The journal line must not kill the script: the preserve and the reset are
# done and do not repeat, and the worktree below must still open. On a failure,
# finish, say the real state, and hand back the one retryable line.
NOTE=("$WORKSPACE/prompts/common/progress.py" note attempt.failed \
    --task "$N" --data "$FAILURE_DATA")
JOURNAL_MISSING=
NOTE_PRESENT=
if [ -f "$JOURNAL" ] \
   && python3 - "$JOURNAL" "$LOT" "$N" "$K" "$FAILURE_DATA" <<'PY'
import json
import sys

journal, lot, task, attempt, expected = sys.argv[1:]
expected = json.loads(expected)
with open(journal, encoding="utf-8") as source:
    found = any(
        (entry := json.loads(line)).get("kind") == "attempt.failed"
        and entry.get("lot") == lot and entry.get("task") == int(task)
        and (entry.get("data") or {}).get("attempt") == int(attempt)
        and entry.get("data") == expected
        for line in source if line.strip()
    )
raise SystemExit(0 if found else 1)
PY
then
    NOTE_PRESENT=1
fi
if [ -z "$NOTE_PRESENT" ]; then
    "${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
fi
# The identity falls LAST, after EVERY gesture it authenticates — the journal
# line and, on the preserving branches, the diagnostic worktree. Removed before
# the add, a kill in that window leaves a recorded failure whose required
# checkout no rerun can ever open: this script refuses without the identity,
# and the add command then exists nowhere. So each branch settles what it owes,
# and one closer hands back whatever remains — the gestures in order, the
# identity's removal always the final one.
warn_tail() {   # $1: non-empty when the worktree open is still owed
    if [ -z "$1" ] && [ -z "$JOURNAL_MISSING" ]; then
        rm -f "$INFLIGHT"
        return 0
    fi
    {
        printf '**script WARNING** · the preserve and the reset ARE done and do not repeat.\n'
        printf 'Rerun this exact same call. It recognizes its try ref, journal note and\n'
        printf 'diagnostic checkout, then performs only the remaining gestures. They are:\n\n'
        [ -z "$1" ] || printf '    %q %q %q %q\n' \
            "$WORKSPACE/prompts/construction/diagnostic-open.sh" "$LOT" "$N" "$K"
        [ -z "$JOURNAL_MISSING" ] || printf '    %s\n' "$JOURNAL_MISSING"
        printf '    rm -f %q\n' "$INFLIGHT"
    } >&2
    exit 1
}

if [ -z "$PRESERVED" ]; then
    printf 'NOTHING PRESERVED — the attempt left the tree untouched\nTREE AT %s\n' "$BASE"
    warn_tail ""
    exit 0
fi

# A diagnosis gets a worktree, never a diff: rebuilding a file in your head is
# the one thing this workflow never relies on. If it cannot open, the preserve
# and the reset are still real — say so, and hand back the remaining gestures
# instead of dying as if nothing had happened.
if [ -n "$ALREADY_OPEN" ]; then
    printf 'PRESERVED %s\nTREE AT %s\nDIAGNOSTIC WORKTREE %s\n' "$TRY" "$BASE" "$TMP"
    warn_tail ""
    exit 0
fi
if ! "$WORKSPACE/prompts/construction/diagnostic-open.sh" "$LOT" "$N" "$K" >/dev/null; then
    printf 'PRESERVED %s\nTREE AT %s\nDIAGNOSTIC WORKTREE FAILED — see the warning\n' "$TRY" "$BASE"
    warn_tail add
fi
printf 'PRESERVED %s\nTREE AT %s\nDIAGNOSTIC WORKTREE %s\n' "$TRY" "$BASE" "$TMP"
warn_tail ""
