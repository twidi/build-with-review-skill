#!/usr/bin/env bash
# End of C1: the plan leaves the workspace, gets committed, and the lot's
# starting point is posted.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/bare-stop.sh"
source "$WORKSPACE/prompts/common/attempt-closer.sh"

[ $# -eq 2 ] || die "2 arguments expected, $# given — usage: plan-commit.sh <lot> \"<commit subject>\"
Quote the subject, it contains spaces. This commit lands in the repository's history, so
its wording is the project's business — write it in the project's own conventions."
LOT=$1 SUBJECT=$2
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[ -n "$SUBJECT" ] || die "the commit subject is empty"
DOCUMENT_COPY="$WORKSPACE/prompts/common/document-copy.sh"
SOURCE_REL="plans/$LOT-plan.md"
# Authenticate every source component before the first grep or sed reads it.
SOURCE=$("$DOCUMENT_COPY" source "$SOURCE_REL")

# The workspace's name is the stem of every plan path: one date per feature,
# fixed when the workspace was created.
RUN_NAME=$(basename "$WORKSPACE")
TARGET="docs/plans/$RUN_NAME-$LOT-plan.md"

TASKS=$(grep -c '^## Task ' "$SOURCE" || true)
[ "$TASKS" -gt 0 ] || die "$SOURCE declares no task — expected '## Task <N>' headings"

# The identities, not only the count. Every number downstream — an implementer,
# a report path, an annotation, a git ref — is keyed on these headings reading
# exactly 1..N, once each, in order. A duplicate would give two sections one
# ref; a gap would make the recorded count disagree with what exists.
# The whole grammar, not a numeric prefix: '## Task 1.1', '## Task 1foo' and a
# bare '## Task 1' must all fail here, or the visible identity and the numeric
# one diverge and the ambiguity this check exists to stop is certified instead.
mapfile -t IDS < <(sed -n 's/^## Task \([1-9][0-9]*\) - ..*$/\1/p' "$SOURCE")
[ "${#IDS[@]}" -eq "$TASKS" ] \
    || die "a '## Task' heading is malformed — every heading reads '## Task <N> - <title>', N a positive integer without leading zeros"
n=0
for id in ${IDS[@]+"${IDS[@]}"}; do
    n=$((n + 1))
    [ "$id" = "$n" ] \
        || die "task headings must read 1..$TASKS in order, exactly once each — heading $n says '## Task $id'"
done

cd "$REPO"
# The pending marker is the operation's identity AND its prepared payload,
# published atomically. "HEAD touches the plan copy" cannot be an identity —
# every task commit republishes that same copy — and the index is what tells
# the two recoverable states apart: the target still staged — the commit never
# landed (a kill, or a hook that refused), and the same operation retries it —
# or the index empty — the commit landed, and only the tail remains.
PENDING="$WORKSPACE/plan-commit-in-progress"
JOURNAL="$WORKSPACE/progress.jsonl"
marker_read() { P_ID=; P_TREE=; P_OP=; { read -r P_ID; read -r P_TREE; read -r P_OP; } < "$PENDING" || true
    [ -n "$P_ID" ] || die "the pending marker is unreadable — remove it (rm -f $PENDING)
and take the state to the human. Nothing was done."; }
# The marker's fate is settled FIRST. A marker whose operation already carries
# its completion note is an ORPHAN — the kill fell between the note and the
# marker's removal — and this call is then a later operation, never a retry:
# the same lot legitimately commits its plan again at every re-cut. The note
# carries the marker's own per-operation mark (`op`) for exactly this test —
# NEVER the payload tree: a later re-cut can legitimately restore an earlier
# plan, its write-tree then repeats, and a tree-keyed test would let the OLD
# note consume the NEW live marker — whose own completion could then never be
# recorded. The tree stays in the marker for payload integrity, nothing else.
if [ -f "$PENDING" ]; then
    marker_read
    # One pass, one process — never `grep | grep -q`: under pipefail the -q
    # side's early exit SIGPIPEs the producer, and a successful lookup reads
    # as false — the orphan then blocks a legitimate later operation forever.
    if [ -n "$P_OP" ] && [ -f "$JOURNAL" ] \
       && awk -v k='"kind":"plan.written"' -v o="\"op\":\"$P_OP\"" \
              'index($0,k) && index($0,o) {found=1; exit} END {exit !found}' "$JOURNAL"; then
        rm -f "$PENDING"
        P_ID=; P_TREE=; P_OP=
    else
        [ "$P_ID" = "$LOT" ] || die "an interrupted plan commit is pending for \`$P_ID\`,
not \`$LOT\` — the tail belongs to the call that opened it. Rerun with \`$P_ID\`.
Nothing was done, and nothing was staged."
    fi
fi
if [ ! -f "$PENDING" ] && ! bare_stop_refuse_unfinished "$WORKSPACE"; then
    die "$BARE_STOP_ERROR. This fresh plan commit cannot pass it. Nothing was copied,
staged, committed or marked."
fi
if [ ! -f "$PENDING" ] && ! controller_operation_refuse_pending "$WORKSPACE" gate-check; then
    die "$CONTROLLER_OPERATION_ERROR. This fresh plan commit cannot pass the frozen gate candidate. Nothing was copied, staged or committed."
fi
# The shared copy boundary revalidates the source and every repository
# component, writes a real same-directory temporary, then renames atomically.
"$DOCUMENT_COPY" copy "$SOURCE_REL" "$TARGET" replace
# The pathspec on the commit is not decoration: `git add X && git commit -m …`
# commits the WHOLE index, including anything somebody else had staged.
git add -- "$TARGET"
if ! git diff --cached --quiet -- "$TARGET"; then
    TREE=$(git write-tree)
    if [ -f "$PENDING" ]; then
        [ "$P_TREE" = "$TREE" ] || die "the prepared content changed since the interrupted
call — what is staged now is not what that call meant to commit, and merging the two is
nobody's to decide but the human's. Nothing was committed; the new content sits staged."
        # same operation, same payload, commit never landed: retry the commit
        OP_NONCE=$P_OP
    else
        OP_NONCE="$(date +%s%N).$$"
        printf '%s\n%s\n%s\n' "$LOT" "$TREE" "$OP_NONCE" > "$PENDING.tmp"
        mv "$PENDING.tmp" "$PENDING"
    fi
    # Workflow-owned document commits do not run project hooks. A successful
    # hook can replace the exact staged bytes after the controller accepted
    # them. The implementer's task commit keeps normal hooks and proves its
    # result against a frozen final-gate tree instead.
    git -c core.hooksPath=/dev/null commit -q -m "$SUBJECT" -- "$TARGET"
    "$DOCUMENT_COPY" finish "$SOURCE_REL" "$TARGET" replace
else
    # Empty index: the commit landed — a tail only if this same operation's
    # marker says one is pending. Its identity was already checked above.
    if [ ! -f "$PENDING" ]; then
        "$DOCUMENT_COPY" finish "$SOURCE_REL" "$TARGET" replace
        die "nothing to commit — the plan has no change to land, and no
interrupted plan commit is pending. Nothing was done."
    fi
    git diff-tree --no-commit-id --name-only -r HEAD | grep -Fxq "$TARGET" \
        || die "a plan commit is pending but HEAD does not carry $TARGET — this state is
not the script's to repair. Ask the human. Nothing was done."
    OP_NONCE=$P_OP
    "$DOCUMENT_COPY" finish "$SOURCE_REL" "$TARGET" replace
fi
[ -n "${P_TREE:-}" ] || P_TREE=$TREE
git diff --quiet "$P_TREE" HEAD -- "$TARGET" \
    || die "the created plan commit does not contain the exact prepared plan payload.
The pending marker remains. No task ref or journal terminal was written."
RUN="refs/bwr/$(basename "$WORKSPACE")"   # this run's own ref namespace — see vocabulary.md
# task-0 is posted once, and it never moves afterwards. This script also runs
# when a plan is rewritten mid-lot — a re-cut decomposition, a completeness pass
# sent back to C1 — and by then HEAD sits on top of the tasks already built.
# Moving task-0 there would make "where the lot started" a commit that comes
# after part of the lot: the product review would take it as the base and lose
# everything built before, and a past-task diff would run backwards.
if git rev-parse --verify --quiet "$RUN/$LOT/task-0" >/dev/null; then
    START=$(git rev-parse "$RUN/$LOT/task-0")
    KEPT=" (unchanged — the lot had already started)"
else
    # The commit above is real and does not repeat: a ref failure here must
    # not read as if nothing happened. Say the state, hand back the gesture.
    START=$(git rev-parse HEAD)
    if ! git update-ref "$RUN/$LOT/task-0" HEAD; then
        {
            printf '**script WARNING** · the plan IS committed, but task-0 was not posted.\n'
            printf 'Retry the ref alone, first:\n\n'
            printf '    git update-ref %q %q\n' "$RUN/$LOT/task-0" "$START"
            printf '\nThen run this same call again — the pending marker is still in place, and the\n'
            printf 'script then finishes only the journal tail. The commit does not repeat.\n'
        } >&2
        printf 'COMMITTED %s\nTASKS %s\ntask-0 FAILED — see the warning\n' "$TARGET" "$TASKS"
        exit 1
    fi
    KEPT=
fi

# The journal line must not kill the script: the git work above is done and
# does not repeat, so a failed note makes THIS call the only way to know what
# happened. Finish, say the real state, and hand back the one retryable line.
# The note carries the operation's own mark: it is what lets a later call
# tell this completed operation's orphan marker from a live interrupted one.
NOTE=("$WORKSPACE/prompts/common/progress.py" note plan.written --data "{\"tasks\":$TASKS,\"op\":\"$OP_NONCE\"}")
JOURNAL_MISSING=
"${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
# The marker lives until the whole tail is durable — the journal line included.
[ -n "$JOURNAL_MISSING" ] || rm -f "$PENDING"
printf 'COMMITTED %s\nTASKS %s\ntask-0 %s%s\n' "$TARGET" "$TASKS" "$START" "$KEPT"
if [ -n "$JOURNAL_MISSING" ]; then
    {
        printf '**script WARNING** · everything above IS done, but its journal line is missing.\n'
        printf 'The git work does not repeat. Retry the line alone and then remove the marker —\n\n'
        printf '    %s\n' "$JOURNAL_MISSING"
        printf '    rm -f %q\n' "$PENDING"
        printf '\n— or run this same call again: the pending marker is still in place, and the\n'
        printf 'script then finishes only this tail.\n'
    } >&2
    exit 1
fi
