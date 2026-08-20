#!/usr/bin/env bash
# The DECISION channel's in-place edit: the spec, that path alone, committed —
# and the live attempt's mark moved with HEAD when a lot is in flight.
#
# The re-marking is the reason this is a script. This commit can land while an
# implementer sits blocked mid-attempt, waiting on the very answer being
# written in. It moves HEAD, and the mark that says where that attempt began
# has to move with it — without that, an implementer that resumes and commits
# nothing can report this very commit, and every check passes: a clean tree, a
# HEAD past the mark, a reported hash that equals HEAD. The task would be
# certified built.
set -euo pipefail
# The spec path is data: git would otherwise read *, ?, […] and a leading `:`
# in it as pathspec syntax, and "that path alone" could stage and commit OTHER
# files that merely match the pattern. Literal semantics for every git call —
# this script uses no pathspec magic anywhere.
export GIT_LITERAL_PATHSPECS=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"
source "$WORKSPACE/prompts/common/bare-stop.sh"

if [ $# -ne 3 ] && [ $# -ne 4 ] && [ $# -ne 5 ] && [ $# -ne 6 ]; then
    die "3, 4, 5 or 6 arguments expected, $# given — usage:
  spec-commit.sh <spec path> \"<commit subject>\" <lot|->
  spec-commit.sh <spec path> \"<commit subject>\" <lot|-> <ruling-id>
  spec-commit.sh <spec path> \"<commit subject>\" <lot|-> <batch-number> <decision-id>
  spec-commit.sh <spec path> \"<commit subject>\" <lot|-> breach <breach-number> <conflict-number>
Quote the subject, it contains spaces. The third argument is the lot whose attempt is
still running, or \`-\` when no attempt is in flight. The fourth argument alone binds
one product ruling. The batch form binds an R2.4 commit to one durable decision-batch
item. The six-argument form binds an adverse breach's spec repair to its ready human
conflict. Every bound form requires one current spec.edit.ready boundary before this
script is called."
fi
SPEC=$1 SUBJECT=$2 LOT=$3 BATCH= DECISION= RULING= BREACH= CONFLICT=
if [ $# -eq 4 ]; then
    RULING=$4
elif [ $# -eq 5 ]; then
    BATCH=$4
    DECISION=$5
elif [ $# -eq 6 ]; then
    [ "$4" = "breach" ] \
        || die "the six-argument form's fourth argument must be the literal word \`breach\`, got \`$4\`"
    BREACH=$5
    CONFLICT=$6
fi
[ -n "$SUBJECT" ] || die "the commit subject is empty"
[ -n "$LOT" ] || die "the third argument is a lot, or \`-\` — it may not be empty"
if [ $# -eq 4 ]; then
    [[ $RULING =~ ^R[1-9][0-9]*$ ]] \
        || die "the ruling must read R<N> with a positive integer and no leading zeros, got \`$RULING\`"
elif [ $# -eq 5 ]; then
    [ -n "$BATCH" ] || die "the batch may not be empty"
    [ -n "$DECISION" ] || die "the decision may not be empty"
    [[ $BATCH =~ ^[1-9][0-9]*$ ]] \
        || die "the batch must be a positive integer with no leading zeros, got \`$BATCH\`"
    [[ $DECISION =~ ^D[1-9][0-9]*$ ]] \
        || die "the decision must read D<N> with a positive integer and no leading zeros, got \`$DECISION\`"
elif [ $# -eq 6 ]; then
    [[ $BREACH =~ ^[1-9][0-9]*$ ]] \
        || die "the breach must be a positive integer with no leading zeros, got \`$BREACH\`"
    [[ $CONFLICT =~ ^[1-9][0-9]*$ ]] \
        || die "the conflict must be a positive integer with no leading zeros, got \`$CONFLICT\`"
fi

cd "$REPO"
[ -f "$SPEC" ] || die "no spec at $SPEC"

# The marker identity is %q-encoded to ONE line: a pathname may carry any byte,
# newlines included — vocabulary.md's own rule — and a raw newline in the spec
# path would shift every later marker field, making the real retry refuse
# forever. The encoding is only ever COMPARED, never decoded, and an ordinary
# path reads through it almost unchanged.
ID=$(printf '%q' "$LOT $SPEC $RULING $BATCH $DECISION $BREACH $CONFLICT")
BOUND=
AUTH_FORM= AUTH_OWNER=
if [ $# -eq 4 ]; then
    BOUND=1 AUTH_FORM=ruling AUTH_OWNER=$RULING
elif [ $# -eq 5 ]; then
    BOUND=1 AUTH_FORM=batch AUTH_OWNER="B$BATCH/$DECISION"
elif [ $# -eq 6 ]; then
    BOUND=1 AUTH_FORM=breach AUTH_OWNER="breach-$BREACH/C$CONFLICT"
fi

# Everything is checked before the commit, because a commit cannot be re-run:
# once the spec is in, the command has nothing left to commit, so a refusal
# afterwards leaves the caller unable to correct the argument by doing what
# the workflow told it to do.
[ "$LOT" = "-" ] || [[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] \
    || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — or \`-\`, got \`$LOT\`"

# The marker's fate is settled FIRST. A marker whose operation already carries
# its completion note is an ORPHAN — the kill fell between the note and the
# marker's removal — and this call is then a later operation, never a retry:
# the same spec and lot legitimately commit again at every in-place ruling.
# The note carries the marker's own per-operation mark (`op`) for exactly this
# test — NEVER the payload tree: a later ruling can legitimately return the
# spec to an earlier committed state, its write-tree then repeats, and a
# tree-keyed test would let the OLD note consume the NEW live marker — whose
# own completion could then never be recorded. The tree stays in the marker
# for payload integrity, nothing else.
PENDING="$WORKSPACE/spec-commit-in-progress"
JOURNAL="$WORKSPACE/progress.jsonl"
marker_read() { P_ID=; P_TREE=; P_OP=; P_READY=; P_CLOSE_ROUND=; P_CLOSE_REVIEW=; P_CLOSE_SPEC=;
    { IFS= read -r P_ID; IFS= read -r P_TREE; IFS= read -r P_OP; IFS= read -r P_READY; IFS= read -r P_CLOSE_ROUND; IFS= read -r P_CLOSE_REVIEW; IFS= read -r P_CLOSE_SPEC; } < "$PENDING" || true
    [ -n "$P_ID" ] || die "the pending marker is unreadable — remove it (rm -f $PENDING)
and take the state to the human. Nothing was done."; }
if [ -f "$PENDING" ]; then
    marker_read
    # One pass, one process — never `grep | grep -q`: under pipefail the -q
    # side's early exit SIGPIPEs the producer, and a successful lookup reads
    # as false — the orphan then blocks a legitimate later operation forever.
    if [ -n "$P_OP" ] && [ -f "$JOURNAL" ] \
       && awk -v k='"kind":"spec.committed"' -v o="\"op\":\"$P_OP\"" \
              'index($0,k) && index($0,o) {found=1; exit} END {exit !found}' "$JOURNAL"; then
        rm -f "$PENDING"
        P_ID=; P_TREE=; P_OP=; P_READY=; P_CLOSE_ROUND=; P_CLOSE_REVIEW=; P_CLOSE_SPEC=
    fi
fi

# A bound commit consumes one durable authority generation. The matching
# spec.edit.ready line names the exact current state artifact and its hash. On
# a fresh call, authenticate it before staging or publishing this script's
# marker. On a retry, use only the ready operation frozen in that marker: a
# later authority event cannot steal a tail whose commit may already exist.
READY_OP= READY_KIND= READY_REF= READY_ARTIFACT_SHA= READY_SOURCE=
if [ -n "$BOUND" ]; then
    SPEC_PATH_SHA=$(printf '%s' "$SPEC" | sha256sum | cut -d' ' -f1)
    AUTH_MODE=fresh AUTH_SELECTOR=$(git rev-parse HEAD)
    if [ -f "$PENDING" ]; then
        [ -n "$P_READY" ] || die "the interrupted bound spec commit has no durable
spec.edit.ready identity. Take this state to the human; nothing was staged."
        AUTH_MODE=retry AUTH_SELECTOR=$P_READY
    fi
    mapfile -d '' -t AUTH_STATE < <(
        python3 "$HERE/spec_edit_auth.py" "$AUTH_MODE" "$AUTH_FORM" "$AUTH_OWNER" "$AUTH_SELECTOR" "$SPEC_PATH_SHA"
    )
    [ ${#AUTH_STATE[@]} -eq 5 ] || die "no exact current spec.edit.ready authorises
$AUTH_OWNER. The refusal happened before staging and before a new pending marker."
    READY_OP=${AUTH_STATE[0]} READY_KIND=${AUTH_STATE[1]} READY_REF=${AUTH_STATE[2]}
    READY_ARTIFACT_SHA=${AUTH_STATE[3]} READY_SOURCE=${AUTH_STATE[4]}
fi

# The unbound three-argument form is the SPEC loop close. Its existing
# pending marker freezes the already-admitted clean round. A fresh call must
# prove that round before staging. The check permits only the documented
# status-line change after the reviewed immutable snapshot.
CLOSE_ROUND= CLOSE_REVIEW_SHA= CLOSE_SPEC_SHA=
if [ -z "$BOUND" ]; then
    if [ -f "$PENDING" ]; then
        [ -n "$P_CLOSE_ROUND" ] && [ -n "$P_CLOSE_REVIEW" ] && [ -n "$P_CLOSE_SPEC" ] \
            || die "the interrupted unbound spec close has no frozen clean-round proof.
Keep the marker and take this state to the human. Nothing was staged."
        CLOSE_ROUND=$P_CLOSE_ROUND CLOSE_REVIEW_SHA=$P_CLOSE_REVIEW CLOSE_SPEC_SHA=$P_CLOSE_SPEC
    else
        CLOSE_OUTPUT=$(python3 "$WORKSPACE/prompts/common/progress.py" spec-close-check "$SPEC") \
            || die "the current SPEC loop is not ready for its unbound close. Nothing was staged or marked."
        mapfile -t CLOSE_STATE <<< "$CLOSE_OUTPUT"
        [ ${#CLOSE_STATE[@]} -eq 3 ] \
            || die "the SPEC close validator returned no exact clean-round proof. Nothing was staged."
        CLOSE_ROUND=${CLOSE_STATE[0]} CLOSE_REVIEW_SHA=${CLOSE_STATE[1]} CLOSE_SPEC_SHA=${CLOSE_STATE[2]}
    fi
fi

# The lot-or-none answer is authenticated, never taken on trust: attempt-base
# survives an attempt's closing, so the ref's existence proves nothing, and a
# false `-` while an attempt runs commits under it without moving its mark —
# the implementer's own commit then reads as a broken multi-commit task, and
# the failure route resets this very commit off the branch. The identity file
# is the durable proof, exactly as for the closing scripts. Only a FRESH call
# is judged here: an interrupted call's tail belongs to the state recorded
# when it opened, and moving a since-closed attempt's mark is benign — nothing
# reads a mark without the identity file beside it.
if [ ! -f "$PENDING" ]; then
    if ! controller_operation_refuse_pending "$WORKSPACE" gate-check; then
        die "$CONTROLLER_OPERATION_ERROR. This fresh spec commit cannot pass the frozen gate candidate. Nothing was staged or committed."
    fi
    if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
        die "$BARE_STOP_ERROR. This fresh spec commit cannot pass it. Nothing was
committed, staged or marked."
    fi
    INFLIGHT="$WORKSPACE/attempt-in-flight"
    ACTIVE= F_LOT= F_N= F_K=
    if [ -f "$INFLIGHT" ]; then
        read -r F_LOT F_N F_K < "$INFLIGHT" || true
        RUNS="refs/bwr/$(basename "$WORKSPACE")"
        if SHA=$(git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N"); then
            die "attempt-in-flight still owns the success tail for $F_LOT task $F_N
attempt $F_K. Recover its gate with gate-check.sh find-task $F_LOT $F_N $F_K $SHA,
then rerun attempt-succeeded.sh $F_LOT $F_N $SHA <that op>. This fresh spec commit
cannot pass that closer. Nothing was committed, staged or marked."
        elif git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N-try-$F_K" >/dev/null; then
            ROUTE=$(attempt_closer_route "$INFLIGHT" || true)
            die "attempt-in-flight still owns the failure or stop tail for $F_LOT task $F_N
attempt $F_K. $ROUTE This
fresh spec commit cannot pass that closer. Nothing was committed, staged or marked."
        else
            ACTIVE=$F_LOT
        fi
    fi
    if [ "$LOT" = "-" ]; then
        [ -z "$ACTIVE" ] || die "an attempt IS in flight — $ACTIVE task $F_N attempt $F_K,
says the identity file — and this commit would move HEAD under it without moving its
mark. Rerun with \`$ACTIVE\` as the third argument. Nothing was committed, and nothing
was staged."
    else
        [ -n "$ACTIVE" ] || die "no attempt is in flight — the identity file is absent, or
the attempt it names is closed — so there is no mark to move, and \`$LOT\` would move a
stale one. Rerun with \`-\`. Nothing was committed, and nothing was staged."
        [ "$LOT" = "$ACTIVE" ] || die "the attempt in flight is $ACTIVE task $F_N attempt
$F_K — this call says $LOT. The mark that must move is the active attempt's. Rerun with
\`$ACTIVE\`. Nothing was committed, and nothing was staged."
    fi
fi

BASE=
if [ "$LOT" != "-" ]; then
    BASE="refs/bwr/$(basename "$WORKSPACE")/$LOT/attempt-base"
    git rev-parse --verify --quiet "$BASE" >/dev/null \
        || die "the identity file says this attempt is in flight, but its mark $BASE
does not exist — a state no killed start can leave, since the mark is posted before
the identity: something removed the ref. Take it to the human. Nothing was committed."
fi

# The pending marker is the operation's identity AND its prepared payload,
# published atomically. The index is what tells the two recoverable states
# apart: the spec still staged — the commit never landed (a kill, or a hook
# that refused), and the same operation retries it — or the index empty — the
# commit landed, and only the tail remains.
# Identity is validated BEFORE anything is staged: a refused call must leave
# the index exactly as it found it, or the refusal itself changes the pending
# operation's payload and no later rerun can ever match it.
if [ -f "$PENDING" ]; then
    [ "$P_ID" = "$ID" ] || die "an interrupted spec commit is pending for
\`$P_ID\`, and this call says \`$ID\` — the tail belongs to the call that opened
it. Rerun with those values. Nothing was done, and nothing was staged."
    if [ -n "$BOUND" ]; then
        [ "$P_READY" = "$READY_OP" ] || die "the interrupted commit belongs to
spec.edit.ready $P_READY, not $READY_OP. Nothing was done, and nothing was staged."
    fi
fi
git add -- "$SPEC"
if ! git diff --cached --quiet -- "$SPEC"; then
    TREE=$(git write-tree)
    if [ -f "$PENDING" ]; then
        [ "$P_TREE" = "$TREE" ] || die "the prepared content changed since the interrupted
call — what is staged now is not what that call meant to commit, and merging the two is
nobody's to decide but the human's. Nothing was committed; the new content sits staged."
        # same operation, same payload, commit never landed: retry the commit
        OP_NONCE=$P_OP
    else
        OP_NONCE="$(date +%s%N).$$"
        printf '%s\n%s\n%s\n%s\n%s\n%s\n%s\n' \
            "$ID" "$TREE" "$OP_NONCE" "$READY_OP" "$CLOSE_ROUND" "$CLOSE_REVIEW_SHA" "$CLOSE_SPEC_SHA" \
            > "$PENDING.tmp"
        mv "$PENDING.tmp" "$PENDING"
    fi
    git -c core.hooksPath=/dev/null commit -q -m "$SUBJECT" -- "$SPEC"
else
    # Empty index: the commit landed — a tail only if this same operation's
    # marker says one is pending. Its identity was already checked above.
    [ -f "$PENDING" ] || die "nothing to commit at $SPEC and no interrupted spec commit is
pending — there is no in-place edit to land. Nothing was done."
    SPEC_REL=$(git ls-files --full-name -- "$SPEC" | head -1)
    git diff-tree --root --no-commit-id --name-only -r HEAD | grep -Fxq "${SPEC_REL:-$SPEC}" \
        || die "a spec commit is pending but HEAD does not carry $SPEC — this state is
not the script's to repair. Ask the human. Nothing was done."
    OP_NONCE=$P_OP
fi
[ -n "${P_TREE:-}" ] || P_TREE=$TREE
git diff --quiet "$P_TREE" HEAD -- "$SPEC" \
    || die "the created spec commit does not contain the exact prepared spec payload.
The pending marker remains. No attempt mark or journal terminal was written."
SHA=$(git rev-parse HEAD)
PARENT=
if [ $# -ge 4 ]; then
    PARENT=$(git rev-parse "$SHA^")
    [ "$PARENT" = "$READY_SOURCE" ] || die "the bound commit's parent $PARENT is not
the source SHA $READY_SOURCE authenticated by spec.edit.ready. The commit exists; keep
the pending marker and take this protocol breach to the human."
fi

MARKED="no attempt in flight"
if [ -n "$BASE" ]; then
    # The commit is real and does not repeat. A mark that stays behind is the
    # exact hazard this script exists to close — so a failure here is loud,
    # names the state, and hands back the one remaining gesture.
    if ! git update-ref "$BASE" HEAD; then
        {
            printf '**script WARNING** · the spec IS committed, but the attempt mark did NOT move —\n'
            printf 'the very hazard this script closes is open. Retry the ref alone, first:\n\n'
            printf '    git update-ref %q %q\n' "$BASE" "$SHA"
            printf '\nThen run this same call again — the pending marker is still in place, and the\n'
            printf 'script then finishes only the journal tail. The commit does not repeat.\n'
        } >&2
        printf 'COMMITTED %s\nSHA %s\nMARK FAILED — see the warning\n' "$SPEC" "$SHA"
        exit 1
    fi
    MARKED="$BASE moved to this commit"
fi

# The journal line must not kill the script: the commit and the mark move are
# done and do not repeat. Finish, say the real state, hand back the one
# retryable line.
# The note carries the operation's own mark: it is what lets a later call
# tell this completed operation's orphan marker from a live interrupted one.
NOTE_DATA="{\"sha\":\"$SHA\",\"op\":\"$OP_NONCE\""
if [ $# -eq 3 ]; then
    NOTE_DATA+=",\"spec_round\":$CLOSE_ROUND,\"review_sha256\":\"$CLOSE_REVIEW_SHA\""
    NOTE_DATA+=",\"spec_sha256\":\"$CLOSE_SPEC_SHA\""
elif [ $# -eq 4 ]; then
    NOTE_DATA+=",\"ruling\":\"$RULING\",\"parent\":\"$PARENT\""
elif [ $# -eq 5 ]; then
    NOTE_DATA+=",\"batch\":$BATCH,\"decision\":\"$DECISION\",\"parent\":\"$PARENT\""
elif [ $# -eq 6 ]; then
    NOTE_DATA+=",\"breach\":$BREACH,\"conflict\":$CONFLICT,\"parent\":\"$PARENT\""
fi
if [ -n "$BOUND" ]; then
    NOTE_DATA+=",\"ready_op\":\"$READY_OP\",\"state_kind\":\"$READY_KIND\""
    NOTE_DATA+=",\"state_ref\":\"$READY_REF\",\"artifact_sha256\":\"$READY_ARTIFACT_SHA\""
fi
if [ $# -ge 4 ] && [ "$LOT" != "-" ]; then
    NOTE_DATA+=",\"mark_lot\":\"$LOT\""
fi
NOTE_DATA+="}"
NOTE=("$WORKSPACE/prompts/common/progress.py" note spec.committed --data "$NOTE_DATA")
JOURNAL_MISSING=
"${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
# The marker lives until the whole tail is durable — the journal line included.
[ -n "$JOURNAL_MISSING" ] || rm -f "$PENDING"
printf 'COMMITTED %s\nSHA %s\nMARK %s\n' "$SPEC" "$SHA" "$MARKED"
if [ -n "$JOURNAL_MISSING" ]; then
    {
        printf '**script WARNING** · everything above IS done, but its journal line is missing.\n'
        printf 'The commit does not repeat. Retry the line alone and then remove the marker —\n\n'
        printf '    %s\n' "$JOURNAL_MISSING"
        printf '    rm -f %q\n' "$PENDING"
        printf '\n— or run this same call again: the pending marker is still in place, and the\n'
        printf 'script then finishes only this tail.\n'
    } >&2
    exit 1
fi
