#!/usr/bin/env bash
# One task validated: record where it landed.
#
# The clean-tree check is the one the controller is told to make by hand before
# posting the ref. A ref posted over a dirty tree points at a task that is not
# finished, and every later reset would restore that state.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
CONSTRUCTION_REVIEW="$WORKSPACE/prompts/construction/construction_review.py"
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"

[ $# -eq 4 ] \
    || die "4 arguments expected, $# given — usage: attempt-succeeded.sh <lot> <task N> <the commit the implementer reported> <final gate op>"
LOT=$1 N=$2 REPORTED=$3 GATE_OP=$4
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\` — and there is no task 0: task-0 is the lot's starting point, never a task"
[[ $GATE_OP =~ ^[0-9a-f]{64}$ ]] || die "the final gate operation must be one 64-character lowercase hexadecimal identity"

cd "$REPO"
RUN="refs/bwr/$(basename "$WORKSPACE")"   # this run's own ref namespace — see vocabulary.md

# A controller operation can be staged, committed or waiting on its durable
# tail while this attempt remains live. Neither the fresh success path nor the
# already-recorded task-ref tail may close the attempt across that owner.
if ! controller_operation_refuse_pending "$WORKSPACE"; then
    die "$CONTROLLER_OPERATION_ERROR. Rerun that owner first, then retry this success closer.
Nothing was recorded and attempt-in-flight remains unchanged."
fi

# Failure and stop freeze their exact owner in the existing attempt identity
# before they preserve or reset. Success cannot replace that owner, even when
# a stable ref is also present. An unbound two-line identity is the normal
# success path and stays unchanged.
INFLIGHT="$WORKSPACE/attempt-in-flight"
if [ -f "$INFLIGHT" ]; then
    if attempt_closer_read "$INFLIGHT"; then
        die "this attempt closer is already bound to: $ATTEMPT_CLOSER_CALL
attempt-succeeded.sh cannot replace it. Nothing was recorded."
    else
        STATUS=$?
        [ "$STATUS" -eq 1 ] \
            || die "$ATTEMPT_CLOSER_ERROR. Nothing was recorded."
    fi
fi

# An existing task ref is settled FIRST — before the clean-tree check, before
# the identity is required. This closer has no journal note and no pending
# marker: the stable ref is its only completion proof, and its one crash
# window — killed after the identity's removal, before the output reached the
# caller — leaves exactly ref present, identity absent. A retry that demanded
# the identity first could never reach this answer.
if EXISTING=$(git rev-parse --verify --quiet "$RUN/$LOT/task-$N"); then
    SHA=$(git rev-parse --verify --quiet "$REPORTED^{commit}") || SHA=
    if [ -n "$SHA" ] && [ "$EXISTING" = "$SHA" ]; then
        # The recording completed; only its tail may be owed — the success
        # note first (the permanent record that this K was used, which the
        # start guard reads forever after), then the identity's removal. A
        # stale identity naming this very attempt carries the K the note
        # needs; any other identity is another attempt's, and stays. An
        # absent identity means the removal — the last gesture — ran, so
        # nothing can be owed past it.
        if [ -f "$INFLIGHT" ]; then
            F_LOT=; F_N=; F_K=; F_RETRY=; F_RETRY_PROOF=
            {
                read -r F_LOT F_N F_K
                read -r _ _ _ _ _ _ _ F_RETRY F_RETRY_PROOF _
            } < "$INFLIGHT" || true
            if [ "$F_LOT $F_N" = "$LOT $N" ]; then
                JOURNAL="$WORKSPACE/progress.jsonl"
                if ! { [ -f "$JOURNAL" ] \
                   && awk -v k='"kind":"attempt.succeeded"' -v l="\"lot\":\"$LOT\"" \
                          -v t="\"task\":$N," -v a="\"attempt\":$F_K," \
                          'index($0,k) && index($0,l) && index($0,t) && index($0,a) {found=1; exit} END {exit !found}' "$JOURNAL"; }; then
                    bash "$WORKSPACE/prompts/construction/gate-check.sh" require-task \
                        "$GATE_OP" "$LOT" "$N" "$F_K" "$EXISTING" >/dev/null \
                        || die "the stable ref exists, but the supplied final gate does not prove this attempt's exact commit. The success tail remains open."
                    SUCCESS_DATA="{\"attempt\":$F_K,\"lot\":\"$LOT\",\"sha\":\"$EXISTING\",\"gate\":\"$GATE_OP\""
                    [ "$F_RETRY $F_RETRY_PROOF" = "retry -" ] \
                        || SUCCESS_DATA="$SUCCESS_DATA,\"retry\":\"$F_RETRY_PROOF\""
                    SUCCESS_DATA="$SUCCESS_DATA}"
                    NOTE=("$WORKSPACE/prompts/common/progress.py" note attempt.succeeded \
                        --task "$N" --data "$SUCCESS_DATA")
                    if ! "${NOTE[@]}"; then
                        {
                            printf '**script WARNING** · the task IS recorded, but the journal line naming this\n'
                            printf 'attempt number is missing — the start guard reads it to never reuse K.\n'
                            printf 'Retry the line alone, then remove the identity file:\n\n'
                            printf '    %s\n' "$(printf '%q ' "${NOTE[@]}")"
                            printf '    rm -f %q\n' "$INFLIGHT"
                        } >&2
                        printf 'task-%s %s (already recorded)\n' "$N" "$EXISTING"
                        exit 1
                    fi
                fi
                rm -f "$INFLIGHT"
            fi
        fi
        if [ ! -f "$INFLIGHT" ]; then
            [ -f "$WORKSPACE/progress.jsonl" ] && awk \
                -v k='"kind":"attempt.succeeded"' -v l="\"lot\":\"$LOT\"" \
                -v t="\"task\":$N," -v s="\"sha\":\"$EXISTING\"" \
                -v g="\"gate\":\"$GATE_OP\"" \
                'index($0,k) && index($0,l) && index($0,t) && index($0,s) && index($0,g) {found=1; exit} END {exit !found}' \
                "$WORKSPACE/progress.jsonl" \
                || die "the task ref is complete, but this retry does not name its recorded final gate operation"
        fi
        printf 'task-%s %s (already recorded)\n' "$N" "$EXISTING"
        exit 0
    fi
    die "$RUN/$LOT/task-$N already exists, and a validated task ref never moves.
It stands at $EXISTING — not the commit this call reports. Either the task number is
wrong, or the report is: check which task you meant. Nothing was recorded."
fi

DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ]; then
    die "the tree is not clean, so the task is not finished:
$DIRTY"
fi

# Two questions, and neither one answers the other.
#
# 1 · Did this implementer commit anything at all? Only the mark taken when its
#     attempt started can say. `HEAD` differing from `task-<N-1>` cannot: the
#     controller's own commits validly sit between them — an amendment landing
#     mid-lot, a rewind re-landing what it had removed. And the hash the
#     implementer reports cannot either: one that committed nothing can read the
#     current HEAD and report that, which satisfies every other test there is.
BASE="$RUN/$LOT/attempt-base"
git rev-parse --verify --quiet "$BASE" >/dev/null \
    || die "$BASE does not exist — this attempt was never marked as started"

# The identity file binds the mark to a task and an attempt — the mark alone
# is one SHA per lot, and cannot say WHOSE. Present, it must match; a wrong
# unused task number would otherwise pass every other check and be certified
# as another task.
[ -f "$INFLIGHT" ] || die "no attempt is in flight — the identity file is absent: either
no attempt was started this way, or its closing already completed. An absent proof is a
refusal, never a bypass. Nothing was recorded."
F_LOT=; F_N=; F_K=; F_PLAN=; F_PLAN_ID=; F_TASKS=; F_OWNERSHIP=; F_OWNERSHIP_ID=; F_CONTRACT=; F_CONTRACT_ID=; F_RETRY=; F_RETRY_PROOF=; F_EXTRA=
{
    read -r F_LOT F_N F_K
    read -r F_PLAN F_PLAN_ID F_TASKS F_OWNERSHIP F_OWNERSHIP_ID F_CONTRACT F_CONTRACT_ID F_RETRY F_RETRY_PROOF F_EXTRA
} < "$INFLIGHT" || true
[ "$F_LOT $F_N" = "$LOT $N" ] || die "the attempt in flight is $F_LOT task $F_N (attempt
$F_K) — this call says $LOT task $N. The recording takes the attempt's own identity.
Nothing was recorded."
[ "$F_PLAN" = plan ] && [ -n "$F_PLAN_ID" ] \
    && [[ $F_TASKS =~ ^[1-9][0-9]*$ ]] \
    && [ "$F_OWNERSHIP" = ownership ] && [[ $F_OWNERSHIP_ID =~ ^[0-9a-f]{64}$ ]] \
    && [ "$F_CONTRACT" = contract ] && [[ $F_CONTRACT_ID =~ ^[0-9a-f]{64}$ ]] \
    && [ "$F_RETRY" = retry ] && [[ $F_RETRY_PROOF = - || $F_RETRY_PROOF =~ ^[0-9]+:[0-9a-f]{64}$ ]] \
    && [ -z "$F_EXTRA" ] \
    || die "the attempt identity has no valid frozen plan manifest on line 2.
An absent proof is a refusal, never a bypass. Nothing was recorded."
if [ "$(git rev-parse "$BASE")" = "$(git rev-parse HEAD)" ]; then
    die "HEAD is still where this attempt started — the task committed nothing"
fi

# 2 · Is HEAD the commit that was reported? A different one means something has
#     committed since, and the ref would certify that instead of the task.
SHA=$(git rev-parse --verify --quiet "$REPORTED^{commit}") \
    || die "\`$REPORTED\` is not a commit — pass the hash the implementer reported"
if [ "$SHA" != "$(git rev-parse HEAD)" ]; then
    # A valid hash that is not HEAD proves only that the report and the branch
    # disagree. Whether something committed since, or the report itself is
    # wrong, is the caller's routing to make — and the commit count is the
    # fact it routes on, so it is in the message.
    N=$(git rev-list --count "$BASE"..HEAD)
    die "the implementer reported $REPORTED, but HEAD is $(git rev-parse --short HEAD).
Either something has committed since it reported, or the report itself is wrong —
$N commit(s) sit between the attempt's mark and HEAD. Read them before routing.
Nothing was recorded."
fi

# 3 · Exactly ONE commit since the mark. Every later reader relies on it:
#     task-diff reads the task as one commit against its parent, and a rewind
#     treats any commit not at a task ref as the controller's, re-landing it
#     after its reset — a two-commit task would have its first half
#     resurrected by the very rewind that meant to remove it.
COUNT=$(git rev-list --count "$BASE"..HEAD)
if [ "$COUNT" -ne 1 ]; then
    die "$COUNT commits between $BASE and HEAD — a task ends in exactly one.
The attempt cannot repair this: a reset is not the implementer's to make. Route it as a
failed attempt, classification C3.9a — attempt-failed.sh preserves the commits on the
try ref and puts the branch back to the mark. Nothing was recorded."
fi

# 4 · The commit carries the refreshed plan copy, byte-equal to the workspace
#     plan. The Design that was checked travels with the code it describes —
#     without this, task-show later returns the previous task's plan state and
#     the per-task record the mode promises never existed for this task.
PLANCOPY="docs/plans/$(basename "$WORKSPACE")-$LOT-plan.md"
# Path-scoped, no pipeline: a task commit's file list is unbounded, and feeding
# it to an early-exit grep can SIGPIPE the producer under pipefail — a valid
# commit would then read as refused, unrepairably, since republishing cannot
# change the discriminator. Asking git for the one path has no tail to cut off.
[ -n "$(git diff-tree --no-commit-id --name-only -r HEAD -- "$PLANCOPY")" ] \
    || die "the task's commit does not carry $PLANCOPY — every task commits the refreshed
plan copy beside its code. Send the attempt back once: plan-publish.sh, add the copy,
and \`git commit --amend\` its own unaccepted commit. Nothing was recorded."

# Byte equality below proves that the repository copy is the workspace file.
# These checks prove independently that neither representation changed the
# complete controller-owned plan projection frozen before the session existed.
mapfile -t CURRENT_HEADINGS < <(grep '^## Task ' "$WORKSPACE/plans/$LOT-plan.md" || true)
CURRENT_TASKS=${#CURRENT_HEADINGS[@]}
CURRENT_PLAN_ID=$(printf '%s\n' "${CURRENT_HEADINGS[@]}" | git hash-object --stdin)
[ "$CURRENT_TASKS" = "$F_TASKS" ] && [ "$CURRENT_PLAN_ID" = "$F_PLAN_ID" ] \
    || die "the workspace plan's Task 1..T manifest differs from the manifest frozen
when this attempt started. The implementer may write its own Design, but may not change
task headings or decomposition. Nothing was recorded."
git cat-file -e "HEAD:$PLANCOPY" 2>/dev/null \
    || die "the task commit has no readable plan copy at $PLANCOPY. Nothing was recorded."
mapfile -t COMMITTED_HEADINGS < <(git show "HEAD:$PLANCOPY" | grep '^## Task ' || true)
COMMITTED_TASKS=${#COMMITTED_HEADINGS[@]}
COMMITTED_PLAN_ID=$(printf '%s\n' "${COMMITTED_HEADINGS[@]}" | git hash-object --stdin)
[ "$COMMITTED_TASKS" = "$F_TASKS" ] && [ "$COMMITTED_PLAN_ID" = "$F_PLAN_ID" ] \
    || die "the committed plan copy's Task 1..T manifest differs from the manifest frozen
when this attempt started. Nothing was recorded."
CURRENT_STATE=$(python3 "$CONSTRUCTION_REVIEW" plan-state "$LOT" "$N") \
    || die "the current plan ownership cannot be authenticated. Nothing was recorded."
CURRENT_CONTRACT_ID=$(printf '%s\n' "$CURRENT_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["contract_sha256"])')
CURRENT_OWNERSHIP_ID=$(printf '%s\n' "$CURRENT_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_ownership_sha256"])')
[ "$CURRENT_CONTRACT_ID" = "$F_CONTRACT_ID" ] \
    || die "the workspace or committed plan changed the controller-owned task contract.
Only the accepted Design and documented Disagreement projection may change.
Nothing was recorded."
[ "$CURRENT_OWNERSHIP_ID" = "$F_OWNERSHIP_ID" ] \
    || die "the workspace plan changes controller-owned bytes outside this task's Design
and authenticated Disagreement. Nothing was recorded."
COMMITTED_STATE=$(python3 "$CONSTRUCTION_REVIEW" committed-plan-state "$LOT" "$N" HEAD) \
    || die "the committed whole-plan ownership cannot be authenticated. Nothing was recorded."
COMMITTED_OWNERSHIP_ID=$(printf '%s\n' "$COMMITTED_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_ownership_sha256"])')
[ "$COMMITTED_OWNERSHIP_ID" = "$F_OWNERSHIP_ID" ] \
    || die "the committed plan changes controller-owned bytes outside this task's Design
and authenticated Disagreement. Nothing was recorded."
git show "HEAD:$PLANCOPY" | cmp -s - "$WORKSPACE/plans/$LOT-plan.md" \
    || die "the committed plan copy differs from the workspace plan — the refresh did not
happen, or the plan moved since. Send the attempt back once to republish and \`--amend\`.
Nothing was recorded."

# 5 · The durable final-gate result follows this attempt's latest final
#     code-review proof: one clean checker verdict, or the complete round-10
#     resolution with no accepted defect. It covers the exact committed tree
#     and current gate.md, and reports both green commands and an unchanged gate surface.
#     A commit hook that changed the staged payload is caught here: HEAD's tree
#     no longer equals the tree frozen before the runner started.
bash "$WORKSPACE/prompts/construction/gate-check.sh" require-task \
    "$GATE_OP" "$LOT" "$N" "$F_K" "$SHA" >/dev/null \
    || die "the supplied final gate does not prove this attempt's exact accepted commit.
No stable ref or success terminal was written. Return the attempt to its code-checker and
final-gate boundary; a content-changing repair needs a new logical gate operation."

# The ref's absence was proved at the top, before anything else — a validated
# task ref never moves, and a rebuild has no ref to collide with: the rewind
# took it out of the way.
git update-ref "$RUN/$LOT/task-$N" HEAD
SHA_REC=$(git rev-parse HEAD)

# The success note is the permanent, K-bearing record that this attempt number
# was used. The try ref and the failure report carry a FAILED attempt's K; a
# success leaves only the stable task ref, which carries no K and which a
# later rewind moves aside — without this line, the rebuild after a rewind
# could allocate the same K and inherit this attempt's bounded spends (its
# nudge, its dirty-Done repair). The identity falls last, after the note it
# feeds: removed first, a kill in between would leave a used K that no guard
# can ever see again.
SUCCESS_DATA="{\"attempt\":$F_K,\"lot\":\"$LOT\",\"sha\":\"$SHA_REC\",\"gate\":\"$GATE_OP\""
[ "$F_RETRY_PROOF" = - ] || SUCCESS_DATA="$SUCCESS_DATA,\"retry\":\"$F_RETRY_PROOF\""
SUCCESS_DATA="$SUCCESS_DATA}"
NOTE=("$WORKSPACE/prompts/common/progress.py" note attempt.succeeded \
    --task "$N" --data "$SUCCESS_DATA")
if ! "${NOTE[@]}"; then
    {
        printf '**script WARNING** · the task IS recorded at its ref, but the journal line\n'
        printf 'naming this attempt number is missing — the start guard reads it to never\n'
        printf 'reuse K. Retry the line alone, then remove the identity file:\n\n'
        printf '    %s\n' "$(printf '%q ' "${NOTE[@]}")"
        printf '    rm -f %q\n' "$INFLIGHT"
    } >&2
    printf 'task-%s %s\nNOTE FAILED — see the warning\n' "$N" "$SHA_REC"
    exit 1
fi
rm -f "$INFLIGHT"   # the attempt is closed; its identity has served — and falls last
printf 'task-%s %s\n' "$N" "$SHA_REC"
