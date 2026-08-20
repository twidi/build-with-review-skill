#!/usr/bin/env bash
# The human stopped the run. Pause keeps everything; abort keeps the validated
# state and nothing else. They stop the same way — they differ in what
# survives.
#
# The tree, and the journal line, in one call: the script knows the SHA it has
# just posted, so nobody has to read one and type it back.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"
source "$WORKSPACE/prompts/common/bare-stop.sh"

USAGE="usage: stop.sh pause [<lot> <task N> <attempt K>]  |  stop.sh abort [<lot> <task N> <attempt K>] [<path to spare>...]"
[ $# -ge 1 ] || die "at least 1 argument expected, $# given — $USAGE"
MODE=$1; shift
case "$MODE" in
    pause|abort) ;;
    *) die "$USAGE" ;;
esac
cd "$REPO"

# The attempt in flight, when the caller names one. Its work — uncommitted,
# committed, or both — is preserved on its try ref, and the branch goes back to
# the attempt's own start mark: attempt-base..HEAD is the implementer's ground,
# unvalidated by construction, and the state this script reports must never
# include it. Preserved on an abort too — the try ref is the only record left
# of an attempt the reset erases, and what becomes of the refs is the human's
# question at the end of an abort anyway.
LOT= N= K=
if [ $# -ge 3 ] && [[ ${2:-} =~ ^[1-9][0-9]*$ ]] && [[ ${3:-} =~ ^[1-9][0-9]*$ ]]; then
    LOT=$1 N=$2 K=$3
    [[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
    shift 3
elif [[ ${1:-} == lot-* ]]; then
    # A first argument shaped like a lot announces a triplet. A malformed one
    # must be refused, never re-read as a list of paths to spare: that branch
    # would skip the preserve and the reset, and report a completed stop that
    # preserved nothing.
    die "the first argument looks like a lot, so a triplet was meant — <lot> <task N> <attempt K>, both numbers positive integers without leading zeros. Got: $MODE $*"
fi
if [ "$MODE" = pause ] && [ $# -gt 0 ]; then
    die "pause takes no further argument, or three — <lot> <task N> <attempt K>: everything survives a pause, so there is nothing to spare
$USAGE"
fi

# The spared paths, resolved before anything stages. They are the run's own
# DOCUMENTS — a spec being written (untracked), or the same spec dirty with a
# re-entered loop's fixer edits (tracked). They are not code, nothing was
# built on them, and their mode says in so many words never to delete them. The
# caller names them because only the caller knows where they are — and they
# must not ride into an attempt's preserve commit either, or the reset takes
# them out of the tree with it. In general: a spared path is the one dirty
# state the caller vouches for, and the bare abort below refuses any other.
SPARES=()
for keep in "$@"; do
    case "$keep" in
        "$REPO"/*) keep=${keep#"$REPO/"} ;;
        /*) die "\`$keep\` is outside $REPO — a path to spare is inside the repository" ;;
    esac
    SPARES+=("$keep")
done

# A stop with no attempt has no attempt-in-flight identity. Its own marker
# therefore owns the exact mode and normalized spared paths. A completed pause
# remains the same operation until a later resumed boundary; only then can a
# new bare stop allocate another operation identity.
JOURNAL="$WORKSPACE/progress.jsonl"
BARE_MARKER="$WORKSPACE/bare-stop-in-progress"
BARE_OWNER_STATE=
if [ -z "$LOT" ]; then
    if ! bare_stop_owner_inspect "$BARE_MARKER" "$JOURNAL" "$MODE" \
        prompts/common/stop.sh "$MODE" ${SPARES[@]+"${SPARES[@]}"}; then
        die "$BARE_STOP_ERROR. Nothing was reset, cleaned or journaled."
    fi
    # A bare stop cannot cross an operation that already owns the workspace.
    # The owner settles first; only then can this stop publish its own marker.
    if [ "$BARE_STOP_OWNER_STATE" = fresh ] && \
        ! controller_operation_refuse_pending "$WORKSPACE" \
            plan-commit spec-commit amendment-commit spec-breach-recovery rewind gate-check; then
        die "$CONTROLLER_OPERATION_ERROR. Settle that exact owner, then run this bare
$MODE again. No bare-stop marker, ref, tree or journal state was changed."
    fi
    if [ "$BARE_STOP_OWNER_STATE" = completed ]; then
        printf 'STOPPED %s (already recorded)\nLAST VALIDATED %s\nPRESERVED %s\n' \
            "$MODE" "$BARE_STOP_SHA" "$BARE_STOP_REPORT"
        exit 0
    fi
else
    if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
        die "$BARE_STOP_ERROR. This triplet stop cannot pass it. Nothing was moved,
staged or journaled."
    fi
fi

# A document copy can precede any caller-specific operation marker. Every stop
# therefore uses the shared read-only controller-operation guard for it.
if ! controller_operation_refuse_pending "$WORKSPACE" document-copy; then
    die "$CONTROLLER_OPERATION_ERROR. Then run this stop again. Nothing was moved or staged."
fi

# "No attempt in flight" is authenticated, never read off the call's shape.
# A bare stop owns no attempt tail. While the identity exists, either the
# attempt is live or its original closer still owes a note, diagnostic or final
# removal. A result ref proves only an earlier gesture and never lets this
# non-owning call pass it.
INFLIGHT="$WORKSPACE/attempt-in-flight"
if [ -z "$LOT" ] && [ -f "$INFLIGHT" ]; then
    A_LOT=; A_N=; A_K=
    read -r A_LOT A_N A_K < "$INFLIGHT" || true
    RUNS="refs/bwr/$(basename "$WORKSPACE")"
    if SHA=$(git rev-parse --verify --quiet "$RUNS/$A_LOT/task-$A_N"); then
        ROUTE="Recover the final gate with gate-check.sh find-task $A_LOT $A_N $A_K $SHA,
then rerun attempt-succeeded.sh $A_LOT $A_N $SHA <that op> to finish its tail."
    elif git rev-parse --verify --quiet "$RUNS/$A_LOT/task-$A_N-try-$A_K" >/dev/null; then
        ROUTE="$(attempt_closer_route "$INFLIGHT" || true) It finishes the note,
diagnostic or identity-removal tail."
    else
        HINT=
        if [ "$MODE" = abort ]; then HINT=' [<path to spare>...]'; fi
        ROUTE="The attempt is still live. Rerun with its triplet:
stop.sh $MODE $A_LOT $A_N $A_K$HINT."
    fi
    die "attempt-in-flight still names $A_LOT task $A_N attempt $A_K. A bare $MODE
cannot pass or replace its owning closer. $ROUTE
Only that closer or the exact tail it printed may remove the identity. Nothing was
moved, staged or journaled."
fi

# A pending controller-owned commit is never the attempt's work. Triplet stop
# shares the exact same marker guard as the success and failure closers.
if [ -n "$LOT" ]; then
    if ! controller_operation_refuse_pending "$WORKSPACE" \
        spec-commit amendment-commit spec-breach-recovery gate-check; then
        die "$CONTROLLER_OPERATION_ERROR. Then run this stop again. Nothing was moved or staged."
    fi
fi

# A fresh bare abort accounts for the tree before it publishes its operation
# identity. Once that identity exists, the human's exact destructive order is
# durable. Its retry must finish the reset/clean tail even when an earlier
# partial gesture already changed what this read-only check would see.
if [ -z "$LOT" ] && [ "$MODE" = abort ] && [ "$BARE_STOP_OWNER_STATE" = fresh ]; then
    FOREIGN=
    # -z: pathnames arrive as verbatim bytes, never C-quoted. A rename record
    # carries the original name as one more NUL field; only its current name is
    # compared with the caller's vouched paths.
    while IFS= read -r -d '' rec; do
        status=${rec:0:2}
        path=${rec:3}
        case "$status" in
            [RC]?|?[RC]) IFS= read -r -d '' _from || true ;;
        esac
        vouched=
        for keep in ${SPARES[@]+"${SPARES[@]}"}; do
            [ "$path" = "$keep" ] && vouched=1
        done
        [ -n "$vouched" ] || FOREIGN="$FOREIGN$status $path
"
    done < <(git status --porcelain=v1 -z -uall)
    if [ -n "$FOREIGN" ]; then
        die "the tree holds work no attempt owns, and an abort would erase it:
$FOREIGN
Nothing was reset and nothing was removed. Whatever this is, it is not the run's — never
commit it, stash it, or reset it yourself. Ask the human what becomes of it, then run
this call again."
    fi
fi

if [ -z "$LOT" ] && [ "$BARE_STOP_OWNER_STATE" = fresh ]; then
    if ! bare_stop_allocate "$BARE_MARKER" "$MODE" prompts/common/stop.sh \
        "$MODE" ${SPARES[@]+"${SPARES[@]}"}; then
        die "$BARE_STOP_ERROR. Nothing was reset, cleaned or journaled."
    fi
    BARE_STOP_OWNER_STATE=retry
fi

PRESERVED="nothing in flight"
if [ -n "$LOT" ]; then
    RUN_NAME=$(basename "$WORKSPACE")
    RUN="refs/bwr/$RUN_NAME"          # this run's own ref namespace — see vocabulary.md
    FEATURE=${RUN_NAME#????-??-??-}   # for the commit subject, which a human reads
    WORD=PAUSED; [ "$MODE" = abort ] && WORD=ABORTED
    MARK="$RUN/$LOT/attempt-base"
    git rev-parse --verify --quiet "$MARK" >/dev/null \
        || die "$MARK does not exist — this attempt was never marked as started"
    BASE=$(git rev-parse "$MARK")
    # The identity file binds the mark to a task and an attempt. Present, it
    # must match the triplet: preserving under a wrong identity journals a
    # stopping point the resume will trust, and the real assignment is gone
    # from the durable state.
    [ -f "$INFLIGHT" ] || die "no attempt is in flight — the identity file is absent: either
no attempt was started this way, or its closing already completed. An absent proof is a
refusal, never a bypass — rerun without the triplet if nothing is in flight. Nothing was
moved, and nothing was staged."
    F_LOT=; F_N=; F_K=
    read -r F_LOT F_N F_K < "$INFLIGHT" || true
    [ "$F_LOT $F_N $F_K" = "$LOT $N $K" ] || die "the attempt in flight is $F_LOT task $F_N
attempt $F_K — this call says $LOT task $N attempt $K. The stop takes the attempt's own
identity. Nothing was moved, and nothing was staged."
    if SHA=$(git rev-parse --verify --quiet "$RUN/$LOT/task-$N"); then
        die "$RUN/$LOT/task-$N already records a successful closer at $SHA while
attempt-in-flight still owns its tail. Recover the final gate with gate-check.sh find-task
$LOT $N $K $SHA, then rerun attempt-succeeded.sh $LOT $N $SHA <that op>.
Nothing was moved, and nothing was staged."
    fi
    STOP_KIND=paused
    [ "$MODE" = abort ] && STOP_KIND=aborted
    JOURNAL="$WORKSPACE/progress.jsonl"
    if [ -f "$JOURNAL" ] \
       && awk -v allowed="\"kind\":\"$STOP_KIND\"" -v l="\"lot\":\"$LOT\"" \
              -v t="\"task\":$N," -v a1="\"attempt\":$K," -v a2="\"attempt\":$K}" '
            {
                identity = index($0,l) && index($0,t) && (index($0,a1) || index($0,a2))
                terminal = index($0,"\"kind\":\"attempt.succeeded\"") \
                        || index($0,"\"kind\":\"attempt.failed\"") \
                        || index($0,"\"kind\":\"paused\"") \
                        || index($0,"\"kind\":\"aborted\"")
                if (identity && terminal && !index($0,allowed)) {found=1; exit}
            }
            END {exit !found}' "$JOURNAL"; then
        die "attempt $K of $LOT task $N already has a different terminal outcome.
This $MODE call cannot replace its closer. Nothing was moved, and nothing was staged."
    fi
    if ! attempt_closer_bind "$INFLIGHT" stop prompts/common/stop.sh \
        "$MODE" "$LOT" "$N" "$K" ${SPARES[@]+"${SPARES[@]}"}; then
        die "$ATTEMPT_CLOSER_ERROR. Rerun only the frozen call. Nothing was moved, and
nothing was staged."
    fi
    TRYBASE="$RUN/$LOT/task-$N-try-$K"
    if git rev-parse --verify --quiet "$TRYBASE" >/dev/null \
       && [ -z "$(git status --porcelain -uall)" ] \
       && [ "$(git rev-parse HEAD)" = "$BASE" ]; then
        # An earlier stop of this same attempt was killed after its preserve
        # and reset: its try ref is the half already done, and this call
        # recognises it — the handle survives in the report — instead of
        # recording that the attempt left nothing beside it.
        PRESERVED="$TRYBASE at $(git rev-parse "$TRYBASE")"
    else
        TRY=$TRYBASE
        # A taken try name is an earlier, incomplete stop of this same attempt —
        # its preserve is the fuller record, and this pass must not overwrite
        # the only ref holding it. A taken name gets a suffix, never a new
        # owner.
        n=2
        while git rev-parse --verify --quiet "$TRY" >/dev/null; do
            TRY="$TRYBASE-$n"
            n=$((n + 1))
        done
        # Everything, on purpose: preserving a whole state that is about to be
        # erased is the one case where taking the tree wholesale IS the point,
        # and the commit subject says so. It is only sound because C0 refused
        # to start on a tree holding somebody else's uncommitted work.
        # Everything except the spared documents, which are not the attempt's.
        ADD_EXCLUDE=()
        for keep in ${SPARES[@]+"${SPARES[@]}"}; do
            # `literal` magic beside `exclude`: without it the spared path is a
            # PATTERN, and a name carrying *, ?, […] or a leading `:` would not
            # match itself — the preserve would sweep the vouched document in.
            ADD_EXCLUDE+=(":(exclude,literal)$keep")
        done
        git add -A -- . ${ADD_EXCLUDE[@]+"${ADD_EXCLUDE[@]}"}
        if git diff --cached --quiet && [ "$(git rev-parse HEAD)" = "$BASE" ]; then
            PRESERVED="nothing — the attempt left the tree untouched"
        else
            if ! git diff --cached --quiet; then
                # --no-verify: this commit is bookkeeping behind a ref, never
                # history — the project's message convention governs the
                # history humans read, and a hook must not kill a preserve
                # halfway.
                git commit -q --no-verify -m "$FEATURE $LOT task $N attempt $K — $WORD"
            fi
            git update-ref "$TRY" HEAD
            PRESERVED="$TRY at $(git rev-parse HEAD)"
        fi
        git reset -q --hard "$BASE"
    fi
fi

# The task travels as a flag and the attempt in the data when one was named:
# the untouched branch posts no try ref, and without them a resume reading the
# journal cannot name the attempt it must relaunch.
CTX=()
if [ -n "$LOT" ]; then
    CTX=(--task "$N")
fi

JOURNAL_MISSING=
STOP_NOTE_PRESENT=
STOP_KIND=paused
[ "$MODE" = abort ] && STOP_KIND=aborted
if [ -n "$LOT" ] && [ -f "$WORKSPACE/progress.jsonl" ] \
   && awk -v k="\"kind\":\"$STOP_KIND\"" -v l="\"lot\":\"$LOT\"" \
          -v t="\"task\":$N," -v a1="\"attempt\":$K," -v a2="\"attempt\":$K}" \
          'index($0,k) && index($0,l) && index($0,t) && (index($0,a1) || index($0,a2)) {found=1; exit}
           END {exit !found}' "$WORKSPACE/progress.jsonl"; then
    STOP_NOTE_PRESENT=1
fi
case "$MODE" in
pause)
    if [ -z "$LOT" ]; then
        if [ "$BARE_STOP_PHASE" = prepared ]; then
            SHA=$(git rev-parse HEAD)
            if ! bare_stop_settle_tree "$BARE_MARKER" "$SHA" "$PRESERVED"; then
                die "$BARE_STOP_ERROR. The stop note was not written."
            fi
        else
            SHA=$BARE_STOP_SHA
            PRESERVED=$BARE_STOP_REPORT
        fi
        DATA="{\"sha\":\"$SHA\",\"op\":\"$BARE_STOP_OP\"}"
    else
        SHA=$(git rev-parse HEAD)
        DATA="{\"sha\":\"$SHA\",\"attempt\":$K}"
    fi
    NOTE=("$WORKSPACE/prompts/common/progress.py" note paused
        ${CTX[@]+"${CTX[@]}"} --text "$PRESERVED" --data "$DATA")
    if [ -z "$STOP_NOTE_PRESENT" ]; then
        "${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
    fi
    ;;
abort)
    if [ -z "$LOT" ] && [ "$BARE_STOP_PHASE" = tree-settled ]; then
        SHA=$BARE_STOP_SHA
        PRESERVED=$BARE_STOP_REPORT
    else
        git reset -q --hard HEAD
        # `reset --hard` leaves untracked files behind, and a task creates them
        # all the time. No -x: ignored paths are not ours, and the workspace is
        # one of them. Every spared path is relative and anchored.
        EXCLUDE=()
        for keep in ${SPARES[@]+"${SPARES[@]}"}; do
            # clean -e speaks gitignore, a pattern language. Escape its
            # metacharacters and every trailing space in the literal path.
            esc=$(printf '%s' "$keep" | sed -e 's/\\/\\\\/g' -e 's/[][*?]/\\&/g')
            TRAIL=
            while [ "${esc% }" != "$esc" ]; do
                esc="${esc% }"
                TRAIL="\\ $TRAIL"
            done
            esc="$esc$TRAIL"
            EXCLUDE+=(-e "/$esc")
        done
        REMOVED=$(git clean -fd "${EXCLUDE[@]+"${EXCLUDE[@]}"}" | sed 's/^Removing /  /')
        SHA=$(git rev-parse HEAD)
        if [ -n "$REMOVED" ]; then
            PRESERVED="$PRESERVED
Untracked files removed:
$REMOVED"
        fi
        if [ -z "$LOT" ]; then
            if ! bare_stop_settle_tree "$BARE_MARKER" "$SHA" "$PRESERVED"; then
                die "$BARE_STOP_ERROR. The stop note was not written."
            fi
        fi
    fi
    if [ -z "$LOT" ]; then
        DATA="{\"sha\":\"$SHA\",\"op\":\"$BARE_STOP_OP\"}"
        NOTE=("$WORKSPACE/prompts/common/progress.py" note aborted
            --text "$PRESERVED" --data "$DATA")
    else
        DATA="{\"sha\":\"$SHA\",\"attempt\":$K}"
        NOTE=("$WORKSPACE/prompts/common/progress.py" note aborted
            ${CTX[@]+"${CTX[@]}"} --data "$DATA")
    fi
    if [ -z "$STOP_NOTE_PRESENT" ]; then
        "${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
    fi
    ;;
esac

# The identity outlives the destructive work and falls only once the journal
# carries the stopping point: removed earlier, a kill in between leaves an
# untouched paused attempt nobody can ever attribute again.
if [ -n "$LOT" ] && [ -z "$JOURNAL_MISSING" ]; then
    rm -f "$INFLIGHT"
fi

printf 'STOPPED %s\nLAST VALIDATED %s\nPRESERVED %s\n' "$MODE" "$SHA" "$PRESERVED"

# The journal line must not kill the script: the preserve, the reset and the
# clean are done. The exact same owning call recognizes its result ref or bare
# operation marker and any existing stopping note, so it finishes only the
# remaining tail.
if [ -n "$JOURNAL_MISSING" ]; then
    {
        printf '**script WARNING** · everything above IS done, but its journal line is missing.\n'
        printf 'Rerun this exact same call, or retry the line below. No different\n'
        printf 'operation may pass its durable identity:\n\n'
        printf '    %s\n' "$JOURNAL_MISSING"
        [ -z "$LOT" ] || printf '    rm -f %q\n' "$INFLIGHT"
    } >&2
    exit 1
fi
