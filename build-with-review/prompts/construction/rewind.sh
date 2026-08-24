#!/usr/bin/env bash
# C3.9c and C3.9d: go back to before task K, and take every ref from K to N out
# of the way.
#
# They move, they are not deleted. Left in place, `task-K` would hand the next
# implementer of K+1 code that is no longer in the tree. Deleted, nothing would
# point at those commits at all — the rewound/ namespace is the only handle left
# on them, exactly as a failed attempt's try-<K> ref is on its own.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ "${1:-}" = "--correction" ]; then
    shift
    exec python3 "$HERE/correction_rewind.py" "$@"
fi
# The re-land paths come verbatim from controller commits and go to
# `git checkout <sha> -- <paths>`: read as pathspecs, a committed literal
# `docs/*.md` would restore every matching file from that commit's tree —
# resurrecting rewound content — and a leading-colon name would refuse AFTER
# the destructive half, on every resume alike. Literal semantics for every
# git call — this script uses no pathspec magic anywhere.
export GIT_LITERAL_PATHSPECS=1
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/bare-stop.sh"
source "$WORKSPACE/prompts/common/attempt-closer.sh"

[ $# -eq 4 ] || die "4 arguments expected, $# given — usage: rewind.sh <lot> <first task K> <last task N> \"<subject for the re-land commit>\"
Quote the subject, it contains spaces. The re-land commit lands in the repository's
history — write it in the project's own conventions. It is used only when the rewind has
controller commits to re-land."
LOT=$1 K=$2 N=$3 SUBJECT=$4
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $K =~ ^[1-9][0-9]*$ ]] || die "the first task number must be a positive integer without leading zeros, got \`$K\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the last task number must be a positive integer without leading zeros, got \`$N\`"
[ "$K" -le "$N" ] || die "K=$K is after N=$N"
[ -n "$SUBJECT" ] || die "the commit subject is empty"
[[ $SUBJECT != *$'\n'* && $SUBJECT != *$'\r'* ]] \
    || die "the re-land commit subject must be one line"

RUN_NAME=$(basename "$WORKSPACE")
RUN="refs/bwr/$RUN_NAME"                  # this run's own ref namespace — see vocabulary.md
BASE="$RUN/$LOT/task-$((K - 1))"
cd "$REPO"
git rev-parse --verify --quiet "$BASE" >/dev/null \
    || die "$BASE does not exist — there is nothing to reset to"

# The whole plan of this rewind is written to the workspace BEFORE anything
# moves, and every later step works from that record: a rewind that dies
# halfway is finished by running the same call again — its plan was computed
# from a branch that no longer exists by then, so it must never be recomputed.
STATE="$WORKSPACE/rewind-in-progress"
JOURNAL="$WORKSPACE/progress.jsonl"
RESUME=
if [ -e "$STATE" ]; then
    read -r S_LOT S_K S_N < "$STATE"
    S_NONCE=$(grep '^op ' "$STATE" | cut -d' ' -f2 || true)
    # A record whose operation already carries its completion note is an
    # ORPHAN — the kill fell between the note and the record's removal — and
    # this call is then a NEW rewind, never a resume. Rewinding the same range
    # again after rebuilding it is legitimate, and resuming the old record
    # would reset to the old base, move the newly rebuilt task refs, and
    # re-land only the commits the old operation knew — silently erasing every
    # document commit since. The note carries the record's own mark (`op`) for
    # exactly this test, so the discriminator is mechanical on both branches.
    # One pass, one process — never `grep | grep -q`: under pipefail the -q
    # side's early exit SIGPIPEs the producer, and a SUCCESSFUL lookup reads
    # as false — the completed orphan then resumes as an unfinished record,
    # the exact destructive replay this binding exists to prevent. awk's
    # index() is fixed-string: nothing in the nonce is a pattern.
    if [ -n "$S_NONCE" ] && [ -f "$JOURNAL" ] \
       && awk -v k='"kind":"rewind.done"' -v o="\"op\":\"$S_NONCE\"" \
              'index($0,k) && index($0,o) {found=1; exit} END {exit !found}' "$JOURNAL"; then
        rm -f "$STATE"
    else
        [ "$S_LOT $S_K $S_N" = "$LOT $K $N" ] \
            || die "an unfinished rewind of \`$S_LOT\` tasks $S_K..$S_N is recorded in
$STATE — no \`rewind.done\` carries its mark, so it never completed. Finish it first,
with the same call that started it."
        RESUME=1
    fi
fi
if [ -n "$RESUME" ]; then
    NONCE=${S_NONCE:-legacy}
    BASE_SHA=$(grep '^base ' "$STATE" | cut -d' ' -f2)
    mapfile -t REPLAY < <(grep '^replay ' "$STATE" | cut -d' ' -f2)
else
    if ! controller_operation_refuse_pending "$WORKSPACE" gate-check; then
        die "$CONTROLLER_OPERATION_ERROR. This fresh rewind cannot pass the frozen gate candidate. Nothing was moved."
    fi
    if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
        die "$BARE_STOP_ERROR. This fresh rewind cannot pass it. Nothing was moved."
    fi
    # A fresh rewind expects a clean tree: every route into it has just
    # preserved and reset an attempt, or had nothing in flight. Whatever is
    # here now arrived from outside, and the reset below would erase it — that
    # is not this script's to decide. (A resumed rewind skips this check: its
    # own re-land can legitimately sit staged.)
    DIRTY=$(git status --porcelain)
    [ -z "$DIRTY" ] || die "the tree is not clean, so this rewind cannot start:
$DIRTY
Nothing was moved. Whatever this is, it is not the run's — never commit it, stash it, or
reset it yourself. Ask the human what becomes of it, then run this call again."
    # Everything the reset is about to take off the branch, and which of those
    # commits are tasks. What is left over is the controller's own: an
    # amendment that landed mid-lot, a plan re-committed by an earlier re-cut.
    # Those decide nothing about the code being rewound and they must survive
    # it — an amendment silently unlanded leaves the rebuilt tasks working
    # against a spec that no longer says what the human settled, with the
    # journal claiming otherwise.
    mapfile -t ABOVE < <(git rev-list --reverse "$BASE"..HEAD)
    TASKS=()
    for ((t = K; t <= N; t++)); do
        sha=$(git rev-parse --verify --quiet "$RUN/$LOT/task-$t") || continue
        TASKS+=("$sha")
    done
    REPLAY=()
    for sha in ${ABOVE[@]+"${ABOVE[@]}"}; do
        keep=1
        for task in ${TASKS[@]+"${TASKS[@]}"}; do
            [ "$sha" = "$task" ] && keep=0
        done
        [ "$keep" = 1 ] && REPLAY+=("$sha")
    done
    BASE_SHA=$(git rev-parse "$BASE")
    # Published atomically: a record visible at its final name is complete. A
    # death mid-write must never leave a truncated REPLAY list that a resume
    # would take for the whole plan — the omitted commits would be reset away
    # and never re-landed. The `op` mark is this operation's identity in the
    # completion note, unique per call.
    NONCE="$(date +%s%N).$$"
    {
        printf '%s %s %s\n' "$LOT" "$K" "$N"
        printf 'op %s\n' "$NONCE"
        printf 'base %s\n' "$BASE_SHA"
        for sha in ${REPLAY[@]+"${REPLAY[@]}"}; do printf 'replay %s\n' "$sha"; done
    } > "$STATE.tmp"
    mv "$STATE.tmp" "$STATE"
fi

SUBJECT_ID=$(printf '%s' "$SUBJECT" | git hash-object --stdin)

# A re-land commit has its own prepared-state boundary inside the rewind
# record. The five lines arrive in one atomic rewrite, after the final index is
# ready and before `git commit`. Their presence distinguishes the two states a
# retry must never confuse: the exact tree is still staged at the recorded
# parent, so the commit has not landed; or HEAD is the exact direct child with
# that tree and subject, so only the journal tail remains. Any partial or
# contradictory state is foreign and is refused before a reset can erase it.
RELAND_PENDING=
mapfile -t RELAND_LINES < <(grep '^reland-' "$STATE" || true)
if [ "${#RELAND_LINES[@]}" -gt 0 ]; then
    [ "${#RELAND_LINES[@]}" -eq 5 ] \
        || die "the rewind's re-land boundary is incomplete in $STATE.
Nothing was reset, staged or committed. Take this state to the human."
    state_value() {
        local key=$1
        local values=()
        mapfile -t values < <(awk -v key="$key" '$1 == key {print $2}' "$STATE")
        [ "${#values[@]}" -eq 1 ] \
            || die "the rewind's re-land boundary has no unique $key in $STATE.
Nothing was reset, staged or committed. Take this state to the human."
        printf '%s' "${values[0]}"
    }
    RELAND_OP=$(state_value reland-pending)
    RELAND_PARENT=$(state_value reland-parent)
    RELAND_TREE=$(state_value reland-tree)
    RELAND_SUBJECT=$(state_value reland-subject)
    RELAND_COUNT=$(state_value reland-count)
    [ "$RELAND_OP" = "$NONCE" ] \
        || die "the re-land boundary belongs to operation $RELAND_OP, not $NONCE.
Nothing was reset, staged or committed. Take this state to the human."
    [ "$RELAND_PARENT" = "$BASE_SHA" ] \
        || die "the re-land boundary names parent $RELAND_PARENT, not the rewind base $BASE_SHA.
Nothing was reset, staged or committed. Take this state to the human."
    [[ $RELAND_TREE =~ ^[0-9a-f]+$ ]] \
        || die "the re-land boundary has an invalid tree identity. Nothing was done."
    [[ $RELAND_SUBJECT =~ ^[0-9a-f]+$ ]] \
        || die "the re-land boundary has an invalid subject identity. Nothing was done."
    [[ $RELAND_COUNT =~ ^[1-9][0-9]*$ ]] \
        || die "the re-land boundary has an invalid replay count. Nothing was done."
    [ "$RELAND_SUBJECT" = "$SUBJECT_ID" ] \
        || die "this retry's subject is not the subject frozen by the unfinished rewind.
Nothing was reset, staged or committed. Rerun the exact call that opened it."
    RELAND_PENDING=1
fi

moved=0
replayed=0
COMMIT_NEEDED=
if [ -n "$RELAND_PENDING" ]; then
    replayed=$RELAND_COUNT
    HEAD_SHA=$(git rev-parse HEAD)
    if [ "$HEAD_SHA" = "$RELAND_PARENT" ]; then
        INDEX_TREE=$(git write-tree)
        [ "$INDEX_TREE" = "$RELAND_TREE" ] \
            || die "the unfinished rewind expects prepared tree $RELAND_TREE at
$RELAND_PARENT, but the index now writes $INDEX_TREE. Nothing was reset or committed.
Take this state to the human."
        COMMIT_NEEDED=1
    else
        read -r -a HEAD_LINE <<< "$(git rev-list --parents -n 1 HEAD)"
        [ "${#HEAD_LINE[@]}" -eq 2 ] && [ "${HEAD_LINE[1]}" = "$RELAND_PARENT" ] \
            || die "the unfinished rewind expects its re-land commit as the direct child of
$RELAND_PARENT, but HEAD is $HEAD_SHA. Nothing was reset or committed.
Take this state to the human."
        HEAD_TREE=$(git rev-parse 'HEAD^{tree}')
        [ "$HEAD_TREE" = "$RELAND_TREE" ] \
            || die "HEAD has tree $HEAD_TREE, not the prepared re-land tree $RELAND_TREE.
Nothing was reset or committed. Take this state to the human."
        git diff --cached --quiet \
            || die "the re-land commit is at HEAD, but the index is not clean.
Nothing was reset or committed. Take this state to the human."
        HEAD_SUBJECT=$(git log -1 --format=%s HEAD)
        [ "$HEAD_SUBJECT" = "$SUBJECT" ] \
            || die "HEAD has a different subject from the unfinished re-land operation.
Nothing was reset or committed. Take this state to the human."
        # The prepared commit already landed. Never reset it or run its hooks
        # again; only rewind.done and record removal remain.
    fi
else
    git reset -q --hard "$BASE_SHA"

    for ((t = K; t <= N; t++)); do
        ref="$RUN/$LOT/task-$t"
        sha=$(git rev-parse --verify --quiet "$ref") || continue
        # A task can be rewound more than once. Overwriting would drop the earlier
        # commit out of every ref at once, and this namespace is the only thing
        # holding it — so a taken name gets a suffix rather than a new owner.
        dest="$RUN/$LOT/rewound/task-$t"
        n=2
        while existing=$(git rev-parse --verify --quiet "$dest"); do
            # A destination already holding this very sha is an interrupted earlier
            # call's finished create: nothing to add, only the source to delete —
            # two handles for one rewind would be indistinguishable.
            if [ "$existing" = "$sha" ]; then dest=; break; fi
            dest="$RUN/$LOT/rewound/task-$t-$n"
            n=$((n + 1))
        done
        [ -z "$dest" ] || git update-ref "$dest" "$sha"
        git update-ref -d "$ref"
        moved=$((moved + 1))
    done

    # Re-landed by CONTENT, never by patch, and in one commit.
    #
    # A cherry-pick replays a diff against a base that no longer holds what the diff
    # was made against: a plan commit from an earlier re-cut and every task commit
    # touch the same plan copy, so it would conflict — and it would do so AFTER the
    # reset and AFTER the refs have moved, leaving a destructive sequence half done
    # and a mid-cherry-pick tree for somebody to repair by hand.
    #
    # Restoring the paths cannot conflict. Oldest first, so the newest state of each
    # file wins: for a spec amended twice, that is exactly the state wanted.
    for sha in ${REPLAY[@]+"${REPLAY[@]}"}; do
        # -z, and a NUL-delimited reader: line output C-quotes an unusual pathname,
        # and `git checkout` would then refuse the false path — HERE, after the
        # hard reset and the ref moves, on every retry alike, and the destructive
        # operation could never finish. With -z the paths are verbatim bytes.
        mapfile -d '' -t paths < <(git diff-tree --no-commit-id --name-only --diff-filter=d -r -z "$sha")
        if [ ${#paths[@]} -eq 0 ]; then
            continue
        fi
        git checkout "$sha" -- "${paths[@]}"
        replayed=$((replayed + 1))
    done
    # The restored content can be exactly what BASE already holds — a commit undone
    # by a later one, a state the reset already put back. `git commit` on an empty
    # index exits 1, and under `set -e` that would kill the script here, AFTER the
    # reset and the ref moves — for a case where there was nothing to re-land.
    if [ "$replayed" -gt 0 ] && git diff --cached --quiet; then
        replayed=0
    fi
    if [ "$replayed" -gt 0 ]; then
        [ "$(git rev-parse HEAD)" = "$BASE_SHA" ] \
            || die "the prepared re-land parent is not the recorded rewind base.
Nothing further was committed. Take this state to the human."
        RELAND_TREE=$(git write-tree)
        {
            cat "$STATE"
            printf 'reland-pending %s\n' "$NONCE"
            printf 'reland-parent %s\n' "$BASE_SHA"
            printf 'reland-tree %s\n' "$RELAND_TREE"
            printf 'reland-subject %s\n' "$SUBJECT_ID"
            printf 'reland-count %s\n' "$replayed"
        } > "$STATE.reland.tmp"
        mv "$STATE.reland.tmp" "$STATE"
        COMMIT_NEEDED=1
    fi
fi
# The completion is journaled by the script itself: the preserve that precedes
# a rewind writes `attempt.failed`, and nothing else says the rewind that had
# to follow actually ran — a resume must be able to tell the two apart.
NOTE=("$WORKSPACE/prompts/common/progress.py" note rewind.done --data "{\"first\":$K,\"last\":$N,\"relanded\":$replayed,\"op\":\"$NONCE\"}")
if [ "$replayed" -gt 0 ] && [ -n "$COMMIT_NEEDED" ]; then
    # A hook can refuse the commit — after the reset and the ref moves, which
    # are real and do not repeat. Say so, and hand back the remaining gestures
    # instead of dying as if nothing had happened. The note is one of them: it
    # is the durable proof the resume routes on, and a recovery that skips it
    # leaves a completed rewind the journal still calls incomplete.
    if ! git -c core.hooksPath=/dev/null commit -q -m "$SUBJECT"; then
        printf 'TREE AT %s\nMOVED %d refs to %s/%s/rewound/ (task-%s..task-%s)\nRE-LAND PENDING — see the warning\n' \
            "$BASE" "$moved" "$RUN" "$LOT" "$K" "$N"
        {
            printf '**script WARNING** · the reset and the ref moves ARE done, and the re-landed\n'
            printf 'content is STAGED — only its commit was refused. The prepared tree, parent,\n'
            printf 'subject and operation are frozen in the rewind record. Correct the hook\n'
            printf 'condition, then run this exact rewind call again. It retries this commit.\n'
            printf 'If the exact commit was made manually, the same call recognizes it and\n'
            printf 'finishes only the journal tail; it never repeats the commit.\n'
        } >&2
        exit 1
    fi
fi
if [ "$replayed" -gt 0 ]; then
    [ "$(git rev-parse 'HEAD^{tree}')" = "$RELAND_TREE" ] \
        || die "the created re-land commit does not contain the exact prepared tree.
The rewind record remains. No completion terminal was written."
fi

# The record falls only after the note: removed first, a kill between the two
# leaves neither the recovery plan nor the completion proof, and the resume
# discriminator then runs this same call again as a FRESH rewind, against a
# branch that already carries the result.
JOURNAL_MISSING=
"${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
[ -n "$JOURNAL_MISSING" ] || rm -f "$STATE"
printf 'TREE AT %s\nMOVED %d refs to %s/%s/rewound/ (task-%s..task-%s)\nRE-LANDED %d commit(s) that were not tasks\n' \
    "$BASE" "$moved" "$RUN" "$LOT" "$K" "$N" "$replayed"
if [ -n "$JOURNAL_MISSING" ]; then
    {
        printf '**script WARNING** · the rewind IS done, but its journal line is missing.\n'
        printf 'Run this exact rewind call again: the record authenticates the existing\n'
        printf 're-land commit, so the reset and commit do not repeat, and only this tail runs.\n'
        printf 'Or retry the line alone, then remove the rewind record:\n\n'
        printf '    %s\n' "$JOURNAL_MISSING"
        printf '    rm -f %q\n' "$STATE"
    } >&2
    exit 1
fi
