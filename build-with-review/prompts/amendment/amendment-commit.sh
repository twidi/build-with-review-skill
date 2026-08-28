#!/usr/bin/env bash
# A4: the amendment and the spec it landed in, one commit, explicit paths.
#
# One of the two places where the controller commits while a task can sit
# half-written in the tree — the other is spec-commit.sh, the DECISION
# channel's in-place edit — which is exactly why the paths are named and why
# the pathspec is on the commit itself, not only on the add.
#
# The subject stays an argument: how a commit is worded belongs to the project's
# own CLAUDE.md, not to this workflow.
set -euo pipefail
# The spec path is data: git would otherwise read *, ?, […] and a leading `:`
# in it as pathspec syntax, and the amendment commit could carry OTHER files
# that merely match the pattern — parked attempt work included. Literal
# semantics for every git call — this script uses no pathspec magic anywhere.
export GIT_LITERAL_PATHSPECS=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"
source "$WORKSPACE/prompts/common/bare-stop.sh"

[ $# -eq 4 ] || die "4 arguments expected, $# given — usage: amendment-commit.sh <N> <spec path> \"<commit subject>\" <lot|->
Quote the subject, it contains spaces. The last argument is the lot whose attempt is still
running, or \`-\` when no attempt is in flight."
N=$1 SPEC=$2 SUBJECT=$3 LOT=$4
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the amendment number must be a positive integer without leading zeros, got \`$N\` — amendments count from 1, and one ordinal gets one spelling"
[ -n "$SUBJECT" ] || die "the commit subject is empty"
[ -n "$LOT" ] || die "the last argument is a lot, or \`-\` — it may not be empty"

# The amendment lives in the workspace, outside git, exactly as a plan does.
# `docs/plans/` receives a copy here and nowhere else, with the same stem as
# every plan of this feature: the workspace's name.
DOCUMENT_COPY="$WORKSPACE/prompts/common/document-copy.sh"
PROGRESS="$WORKSPACE/prompts/common/progress.py"
SOURCE_REL="amendments/$N.md"
# Authenticate every source component before accepting this document.
"$DOCUMENT_COPY" source "$SOURCE_REL" >/dev/null
AMENDMENT="docs/plans/$(basename "$WORKSPACE")-amendment-$N.md"

cd "$REPO"
[ -f "$SPEC" ] || die "no spec at $SPEC"

# A Correction-origin AMENDMENT is one exclusive transition of its suspended
# round. The shell retains this lease through copy, index, marker, commit, ref,
# journal, and cleanup. The in-process append consumes the same descriptor.
CORRECTION_SCOPE=$("$PROGRESS" correction-amendment-commit-scope "$N") \
    || die "the current AMENDMENT commit has no exact authority scope. Nothing was changed."
CORRECTION_LEASE_FD= CORRECTION_LEASE_OPERATION=
if [ "$CORRECTION_SCOPE" = "correction" ]; then
    CORRECTION_LEASE_OPERATION="correction-amendment-commit:$N"
    exec {CORRECTION_LEASE_FD}<>"$WORKSPACE/correction-authority.lock"
    flock -x "$CORRECTION_LEASE_FD"
    "$PROGRESS" correction-amendment-commit-lease-check \
        "$N" "$CORRECTION_LEASE_FD" "$CORRECTION_LEASE_OPERATION" \
        || die "the Correction AMENDMENT changed before its commit owner acquired the lease. Nothing was changed."
elif [ "$CORRECTION_SCOPE" != "ordinary" ]; then
    die "the current AMENDMENT commit returned an unknown authority scope. Nothing was changed."
fi

# The marker identity is %q-encoded to ONE line: a pathname may carry any byte,
# newlines included — vocabulary.md's own rule — and a raw newline in the spec
# path would shift every later marker field, making the real retry refuse
# forever. The encoding is only ever COMPARED, never decoded, and an ordinary
# path reads through it almost unchanged.
ID=$(printf '%q' "$N $LOT $SPEC")

# Everything is checked before the commit, because a commit cannot be re-run:
# once the amendment and the spec are in, the command has nothing left to
# commit, so a refusal afterwards leaves the caller with no way to correct the
# argument by doing what the workflow told it to do.
[ "$LOT" = "-" ] || [[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] \
    || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — or \`-\`, got \`$LOT\`"

# The marker's fate is settled FIRST. A marker whose operation already carries
# its completion note is an ORPHAN — the kill fell between the note and the
# marker's removal. No later amendment shares this one's identity, but the
# orphan would still block IT: a fresh call for the next amendment would be
# told to rerun with the old values, toward a tail that has nothing left to do.
# The note carries the marker's own per-operation mark (`op`) for exactly this
# test — one mechanism across the three document-commit scripts; a payload
# tree is content, and content can legitimately repeat.
PENDING="$WORKSPACE/amendment-commit-in-progress"
JOURNAL="$WORKSPACE/progress.jsonl"
marker_read() {
    P_ID=; P_TREE=; P_OP=; P_REVIEW=; P_OPENING=; P_WRITTEN=; P_SWEEP=; P_SWEEP_SHA=
    P_CONSOLIDATION=; P_AMENDMENT_SHA=; P_SPEC_SHA=
    {
        read -r P_ID
        read -r P_TREE
        read -r P_OP
        read -r P_REVIEW
        read -r P_OPENING
        read -r P_WRITTEN
        read -r P_SWEEP
        read -r P_SWEEP_SHA
        read -r P_CONSOLIDATION
        read -r P_AMENDMENT_SHA
        read -r P_SPEC_SHA
    } < "$PENDING" || true
    [ -n "$P_ID" ] && [ -n "$P_SPEC_SHA" ] || die "the pending marker is unreadable or lacks its frozen amendment-review proof. Rerun no other operation and take $PENDING to the human. Nothing was done."
}
if [ -f "$PENDING" ]; then
    marker_read
    # One pass, one process — never `grep | grep -q`: under pipefail the -q
    # side's early exit SIGPIPEs the producer, and a successful lookup reads
    # as false — the orphan then blocks the NEXT amendment's commit forever.
    if [ -n "$P_OP" ] && [ -f "$JOURNAL" ] \
       && awk -v k='"kind":"amendment.committed"' -v o="\"op\":\"$P_OP\"" \
              'index($0,k) && index($0,o) {found=1; exit} END {exit !found}' "$JOURNAL"; then
        rm -f "$PENDING"
        P_ID=; P_TREE=; P_OP=
    fi
fi

# The lot-or-none answer is authenticated, never taken on trust: attempt-base
# survives an attempt's closing, so the ref's existence proves nothing, and a
# false `-` while an attempt runs commits under it without moving its mark —
# the implementer's own commit then reads as a broken multi-commit task, and
# the failure route resets this landed amendment off the branch while the
# journal says `amendment.committed`. The identity file is the durable proof,
# exactly as for the closing scripts. Only a FRESH call is judged here: an
# interrupted call's tail belongs to the state recorded when it opened, and
# moving a since-closed attempt's mark is benign — nothing reads a mark
# without the identity file beside it.
if [ ! -f "$PENDING" ]; then
    if ! controller_operation_refuse_pending "$WORKSPACE" gate-check; then
        die "$CONTROLLER_OPERATION_ERROR. This fresh amendment commit cannot pass the frozen gate candidate. Nothing was copied, staged or committed."
    fi
    if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
        die "$BARE_STOP_ERROR. This fresh amendment commit cannot pass it. Nothing was
copied, committed, staged or marked."
    fi
    INFLIGHT="$WORKSPACE/attempt-in-flight"
    ACTIVE= F_LOT= F_N= F_K=
    if [ -f "$INFLIGHT" ]; then
        read -r F_LOT F_N F_K < "$INFLIGHT" || true
        RUNS="refs/bwr/$(basename "$WORKSPACE")"
        if SHA=$(git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N"); then
            die "attempt-in-flight still owns the success tail for $F_LOT task $F_N
attempt $F_K. Recover its gate with gate-check.sh find-task $F_LOT $F_N $F_K $SHA,
then rerun attempt-succeeded.sh $F_LOT $F_N $SHA <that op>. This fresh amendment commit
cannot pass that closer. Nothing was copied, committed, staged or marked."
        elif git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N-try-$F_K" >/dev/null; then
            ROUTE=$(attempt_closer_route "$INFLIGHT" || true)
            die "attempt-in-flight still owns the failure or stop tail for $F_LOT task $F_N
attempt $F_K. $ROUTE This
fresh amendment commit cannot pass that closer. Nothing was copied, committed, staged or marked."
        else
            ACTIVE=$F_LOT
        fi
    fi
    if [ "$LOT" = "-" ]; then
        [ -z "$ACTIVE" ] || die "an attempt IS in flight — $ACTIVE task $F_N attempt $F_K,
says the identity file — and this commit would move HEAD under it without moving its
mark. Rerun with \`$ACTIVE\` as the last argument. Nothing was committed, and nothing
was staged."
    else
        [ -n "$ACTIVE" ] || die "no attempt is in flight — the identity file is absent, or
the attempt it names is closed — so there is no mark to move, and \`$LOT\` would move a
stale one. Rerun with \`-\`. Nothing was committed, and nothing was staged."
        [ "$LOT" = "$ACTIVE" ] || die "the attempt in flight is $ACTIVE task $F_N attempt
$F_K — this call says $LOT. The mark that must move is the active attempt's. Rerun with
\`$ACTIVE\`. Nothing was committed, and nothing was staged."
    fi

    PROOF_OUTPUT=$("$WORKSPACE/prompts/common/progress.py" amendment-close-check "$N" "$SPEC") \
        || die "the current amendment has no exact clean authoring, reach and consolidation proof. Nothing was copied, staged or committed."
    mapfile -t PROOF_LINES <<< "$PROOF_OUTPUT"
    [ "${#PROOF_LINES[@]}" -eq 8 ] \
        || die "the amendment close proof is malformed. Nothing was copied, staged or committed."
    P_REVIEW=${PROOF_LINES[0]}
    P_OPENING=${PROOF_LINES[1]}
    P_WRITTEN=${PROOF_LINES[2]}
    P_SWEEP=${PROOF_LINES[3]}
    P_SWEEP_SHA=${PROOF_LINES[4]}
    P_CONSOLIDATION=${PROOF_LINES[5]}
    P_AMENDMENT_SHA=${PROOF_LINES[6]}
    P_SPEC_SHA=${PROOF_LINES[7]}
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
# apart: the paths still staged — the commit never landed (a kill, or a hook
# that refused), and the same operation retries it — or the index empty — the
# commit landed, and only the tail remains.
# Identity is validated BEFORE anything is copied or staged: a refused call
# must leave the tree and the index exactly as it found them, or the refusal
# itself changes the pending operation's payload and no rerun can match it.
if [ -f "$PENDING" ]; then
    [ "$P_ID" = "$ID" ] || die "an interrupted amendment commit is pending for
\`$P_ID\` — this call says \`$ID\`. The tail belongs to the call that opened
it: rerun with those values. Nothing was done, and nothing was staged."
fi
# The shared copy boundary repeats the source and destination checks on every
# retry, then publishes the real repository leaf through an atomic rename.
"$DOCUMENT_COPY" copy "$SOURCE_REL" "$AMENDMENT" replace
git add -- "$AMENDMENT" "$SPEC"
if ! git diff --cached --quiet -- "$AMENDMENT" "$SPEC"; then
    TREE=$(git write-tree)
    if [ -f "$PENDING" ]; then
        [ "$P_TREE" = "$TREE" ] || die "the prepared content changed since the interrupted
call — what is staged now is not what that call meant to commit, and merging the two is
nobody's to decide but the human's. Nothing was committed; the new content sits staged."
        # same operation, same payload, commit never landed: retry the commit
        OP_NONCE=$P_OP
    else
        OP_NONCE="$(date +%s%N).$$"
        printf '%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n' \
            "$ID" "$TREE" "$OP_NONCE" "$P_REVIEW" "$P_OPENING" "$P_WRITTEN" \
            "$P_SWEEP" "$P_SWEEP_SHA" "$P_CONSOLIDATION" "$P_AMENDMENT_SHA" \
            "$P_SPEC_SHA" > "$PENDING.tmp"
        mv "$PENDING.tmp" "$PENDING"
    fi
    git -c core.hooksPath=/dev/null commit -q -m "$SUBJECT" -- "$AMENDMENT" "$SPEC"
    "$DOCUMENT_COPY" finish "$SOURCE_REL" "$AMENDMENT" replace
else
    # Empty index: the commit landed — a tail only if this same operation's
    # marker says one is pending. Its identity was already checked above.
    if [ ! -f "$PENDING" ]; then
        "$DOCUMENT_COPY" finish "$SOURCE_REL" "$AMENDMENT" replace
        die "nothing to commit and no interrupted amendment commit is
pending — there is no consolidation to land. Nothing was done."
    fi
    git diff-tree --no-commit-id --name-only -r HEAD | grep -Fxq "$AMENDMENT" \
        || die "an amendment commit is pending but HEAD does not carry $AMENDMENT — this
state is not the script's to repair. Ask the human. Nothing was done."
    OP_NONCE=$P_OP
    "$DOCUMENT_COPY" finish "$SOURCE_REL" "$AMENDMENT" replace
fi
[ -n "${P_TREE:-}" ] || P_TREE=$TREE
git diff --quiet "$P_TREE" HEAD -- "$AMENDMENT" "$SPEC" \
    || die "the created amendment commit does not contain the exact prepared document payload.
The pending marker remains. No attempt mark or journal terminal was written."

SHA=$(git rev-parse HEAD)

# A controller commit made while an attempt is in flight moves HEAD under that
# attempt — this script and spec-commit.sh are the two that can — and the mark
# has to move with it: without this, an implementer that goes on to commit
# nothing can report this very commit, and every check passes — a clean tree, a
# HEAD past the mark, a reported hash that equals HEAD — and the task is
# certified unbuilt.
MARKED="no attempt in flight"
if [ -n "$BASE" ]; then
    # The commit is real and does not repeat. A mark that stays behind is the
    # exact hazard the re-marking exists to close — so a failure here is loud,
    # names the state, and hands back the one remaining gesture.
    if ! git update-ref "$BASE" HEAD; then
        {
            printf '**script WARNING** · the amendment IS committed, but the attempt mark did NOT move —\n'
            printf 'the very hazard the re-marking closes is open. Retry the ref alone, first:\n\n'
            printf '    git update-ref %q %q\n' "$BASE" "$SHA"
            printf '\nThen run this same call again — the pending marker is still in place, and the\n'
            printf 'script then finishes only the journal tail. The commit does not repeat.\n'
        } >&2
        printf 'COMMITTED %s\n          %s\nSHA %s\nMARK FAILED — see the warning\n' "$AMENDMENT" "$SPEC" "$SHA"
        exit 1
    fi
    MARKED="$BASE moved to this commit"
fi

# The journal line must not kill the script: the copy, the commit and the mark
# move are done and do not repeat. Finish, say the real state, hand back the
# one retryable line.
# The note carries the operation's own mark: it is what lets a later call
# tell this completed operation's orphan marker from a live interrupted one.
NOTE_DATA=$(printf '{"amendment":%s,"sha":"%s","op":"%s","opening_sha256":"%s","written_sha256":"%s","sweep":%s,"sweep_sha256":"%s","consolidation_round":%s,"amendment_sha256":"%s","spec_sha256":"%s","review_sha256":"%s"}' \
    "$N" "$SHA" "$OP_NONCE" "$P_OPENING" "$P_WRITTEN" "$P_SWEEP" "$P_SWEEP_SHA" \
    "$P_CONSOLIDATION" "$P_AMENDMENT_SHA" "$P_SPEC_SHA" "$P_REVIEW")
if [ "$CORRECTION_SCOPE" = "correction" ]; then
    NOTE=("$PROGRESS" correction-amendment-commit-append "$N" "$NOTE_DATA" \
          "$CORRECTION_LEASE_FD" "$CORRECTION_LEASE_OPERATION")
else
    NOTE=("$PROGRESS" note amendment.committed --data "$NOTE_DATA")
fi
JOURNAL_MISSING=
"${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
# The marker lives until the whole tail is durable — the journal line included.
[ -n "$JOURNAL_MISSING" ] || rm -f "$PENDING"
printf 'COMMITTED %s\n          %s\nSHA %s\nMARK %s\n' "$AMENDMENT" "$SPEC" "$SHA" "$MARKED"
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
