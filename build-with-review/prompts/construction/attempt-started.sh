#!/usr/bin/env bash
# Marks where an attempt begins — run BEFORE its session is created.
#
# It exists because nothing else can answer *did this implementer commit
# anything*. `HEAD` differing from `task-<N-1>` does not: the controller's own
# commits validly sit between them — an amendment landing mid-lot, a rewind
# re-landing what it removed. And the hash an implementer reports does not
# either: an implementer that committed nothing can read the current `HEAD` and
# report that.
#
# A mark taken before the attempt runs cannot be produced after the fact — which
# is why this runs BEFORE the session is created, and not after. `create_session`
# returns when the prompt has been handed over, not when the session is done with
# it: an implementer that is quick off the mark would already have committed, and
# the mark would land on the task's own commit.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
PROGRESS="$WORKSPACE/prompts/common/progress.py"
CONSTRUCTION_REVIEW="$WORKSPACE/prompts/construction/construction_review.py"
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"
source "$WORKSPACE/prompts/common/bare-stop.sh"

[ $# -ge 3 ] && [ $# -le 4 ] \
    || die "3 or 4 arguments expected, $# given — usage: attempt-started.sh <lot> <task N> <attempt K> [accepted-defect failure report]"
LOT=$1 N=$2 K=$3 RETRY_REPORT=${4:--}
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\`"
[[ $K =~ ^[1-9][0-9]*$ ]] || die "the attempt number must be a positive integer without leading zeros, got \`$K\`"

RUN="refs/bwr/$(basename "$WORKSPACE")"   # this run's own ref namespace — see vocabulary.md

cd "$REPO"
if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
    die "$BARE_STOP_ERROR. This attempt cannot start. Nothing was marked and no session exists."
fi
"$PROGRESS" construction-verdict-check history >/dev/null \
    || die "construction has a consumed checker or diagnostic verdict without its exact durable proof.
Recover that logical spend and physical result before starting another attempt. Nothing was marked and no session exists."
RETRY_PROOF=$("$PROGRESS" construction-retry-check "$LOT" "$N" "$RETRY_REPORT") \
    || die "the retry input does not consume the current accepted code-review obligation.
Nothing was marked and no session exists."
[[ $RETRY_PROOF = - || $RETRY_PROOF =~ ^[0-9]+:[0-9a-f]{64}$ ]] \
    || die "the retry obligation proof is malformed. Nothing was marked and no session exists."
# An attempt starts on a clean tree, always. Anything here now was left by
# whatever happened before, and the implementer would read it as the codebase.
DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ]; then
    die "the tree is not clean, so this attempt cannot start:
$DIRTY"
fi

# The caller's task number is not authority. The current workspace plan is:
# validate the same complete heading grammar and exact 1..T sequence as the
# plan commit, then bind this start to that manifest. This happens before the
# shared attempt mark moves, so a typo or stale task number creates no state.
PLAN="$WORKSPACE/plans/$LOT-plan.md"
[ -f "$PLAN" ] || die "no current plan exists at $PLAN — task $N cannot start"
TASKS=$(grep -c '^## Task ' "$PLAN" || true)
[ "$TASKS" -gt 0 ] \
    || die "$PLAN declares no task — expected '## Task <N>' headings"
mapfile -t HEADINGS < <(grep '^## Task ' "$PLAN" || true)
mapfile -t IDS < <(sed -n 's/^## Task \([1-9][0-9]*\) - ..*$/\1/p' "$PLAN")
[ "${#IDS[@]}" -eq "$TASKS" ] \
    || die "a '## Task' heading is malformed — every heading reads '## Task <N> - <title>', N a positive integer without leading zeros"
t=0
for id in ${IDS[@]+"${IDS[@]}"}; do
    t=$((t + 1))
    [ "$id" = "$t" ] \
        || die "task headings must read 1..$TASKS in order, exactly once each — heading $t says '## Task $id'"
done
[ "$N" -le "$TASKS" ] \
    || die "task $N does not exist in the current $LOT plan — it has tasks 1..$TASKS"
PLAN_ID=$(printf '%s\n' "${HEADINGS[@]}" | git hash-object --stdin)
PLAN_STATE=$(python3 "$CONSTRUCTION_REVIEW" plan-state "$LOT" "$N") \
    || die "the current task has no exact controller-owned plan state"
CONTRACT_ID=$(printf '%s\n' "$PLAN_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["contract_sha256"])')
OWNERSHIP_ID=$(printf '%s\n' "$PLAN_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_ownership_sha256"])')
[[ $CONTRACT_ID =~ ^[0-9a-f]{64}$ ]] \
    || die "the current task contract identity is malformed"
[[ $OWNERSHIP_ID =~ ^[0-9a-f]{64}$ ]] \
    || die "the current plan ownership identity is malformed"

# The workspace plan can keep this task's Design between attempts, but every
# other controller-owned plan byte is frozen. The repository copy is the durable
# boundary for the latest controller-owned plan commit or re-cut. A failed or
# stopped implementer can leave its workspace edit behind; it must not turn
# that edit into fresh task authority merely because attempt-in-flight closed.
PLANCOPY="docs/plans/$(basename "$WORKSPACE")-$LOT-plan.md"
git cat-file -e "HEAD:$PLANCOPY" 2>/dev/null \
    || die "HEAD has no committed plan copy at $PLANCOPY — task $N cannot start"
mapfile -t COMMITTED_HEADINGS < <(git show "HEAD:$PLANCOPY" | grep '^## Task ' || true)
COMMITTED_TASKS=${#COMMITTED_HEADINGS[@]}
COMMITTED_PLAN_ID=$(printf '%s\n' "${COMMITTED_HEADINGS[@]}" | git hash-object --stdin)
[ "$COMMITTED_TASKS" = "$TASKS" ] && [ "$COMMITTED_PLAN_ID" = "$PLAN_ID" ] \
    || die "the workspace plan's Task 1..T manifest is not the current committed
controller-owned manifest in $PLANCOPY. An implementer may write its own Design, but
may not change task headings or decomposition. Restore that manifest, or complete a
controller-owned plan re-cut and commit before starting another attempt. Nothing was
marked and no session exists."
COMMITTED_STATE=$(python3 "$CONSTRUCTION_REVIEW" committed-plan-state "$LOT" "$N" HEAD) \
    || die "the committed controller-owned plan state cannot be authenticated"
COMMITTED_OWNERSHIP_ID=$(printf '%s\n' "$COMMITTED_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_ownership_sha256"])')
[ "$OWNERSHIP_ID" = "$COMMITTED_OWNERSHIP_ID" ] \
    || die "the workspace plan changes controller-owned bytes from the current committed
plan. Only task $N's Design and documented Disagreement are implementer-owned. Restore
the committed controller-owned plan, or complete a controller-owned re-cut before
starting another attempt. Nothing was marked and no session exists."

# task-0 is the durable lot opening. Every real task before N must already be
# validated, N and every later task must not be. A rewind moves the whole
# rebuilt range out of this stable namespace, so a legitimate rebuild has the
# same shape as a first build and passes these checks.
START="$RUN/$LOT/task-0"
git rev-parse --verify --quiet "$START" >/dev/null \
    || die "$START does not exist — $LOT has not been opened by its plan commit"
for ((t = 1; t < N; t++)); do
    git rev-parse --verify --quiet "$RUN/$LOT/task-$t" >/dev/null \
        || die "task $N is not next: validated predecessor task-$t is missing.
Nothing was marked and no session exists."
done
mapfile -t LOT_REFS < <(git for-each-ref --format='%(refname)' "$RUN/$LOT/")
for ref in ${LOT_REFS[@]+"${LOT_REFS[@]}"}; do
    tail=${ref#"$RUN/$LOT/"}
    if [[ $tail =~ ^task-([1-9][0-9]*)$ ]]; then
        stable=${BASH_REMATCH[1]}
        if [ "$stable" -eq "$N" ]; then
            die "task $N is already validated at $ref. A validated task cannot reopen.
Nothing was marked and no session exists."
        fi
        if [ "$stable" -gt "$N" ]; then
            die "task $N is not next: later validated task-$stable already exists at $ref.
Nothing was marked and no session exists."
        fi
    fi
done
if [ "$N" -eq 1 ]; then
    PREDECESSOR=$START
else
    PREDECESSOR="$RUN/$LOT/task-$((N - 1))"
fi
PREDECESSOR_SHA=$(git rev-parse "$PREDECESSOR")
git merge-base --is-ancestor "$PREDECESSOR_SHA" HEAD \
    || die "the required predecessor $PREDECESSOR is not an ancestor of HEAD.
This branch omits validated work. Nothing was marked and no session exists."

# The current committed baseline must be the exact tree accepted by the real
# current gate.md. For task 1 this consumes the post-C2 controller baseline.
# For later tasks it consumes the predecessor task's accepted final gate. A
# spec or amendment commit above either proof invalidates it until the
# controller runs one new baseline gate.
bash "$WORKSPACE/prompts/construction/gate-check.sh" require-current >/dev/null \
    || die "the current HEAD has no accepted green gate proof for the current gate.md.
Run one controller baseline gate for this exact clean HEAD before creating an implementer.
Nothing was marked and no session exists."

# An attempt number is never reused. The try ref and the failure report carry
# a preserved attempt's K — but every closer that leaves neither still
# journals a line carrying the lot, the task and the attempt: a rewound
# success (attempt.succeeded — the task ref has no K and the rewind moves it
# aside), an untouched pause or abort (paused/aborted — no try ref was
# posted), a reportless failure (attempt.failed — the report never landed).
# Any of those lines is a used K, and without this check the next launch
# would re-allocate it and inherit the old attempt's bounded spends. One
# pass, one process — never `grep | grep -q`: under pipefail a successful
# lookup would read false. The attempt token is matched with its closing
# delimiter, `,` or `}`, so K=1 never matches K=12.
JOURNAL="$WORKSPACE/progress.jsonl"
if git rev-parse --verify --quiet "$RUN/$LOT/task-$N-try-$K" >/dev/null \
   || [ -e "$WORKSPACE/reports/construction/$LOT-task-$N-try-$K.md" ] \
   || { [ -f "$JOURNAL" ] \
        && awk -v l="\"lot\":\"$LOT\"" -v t="\"task\":$N," \
               -v a1="\"attempt\":$K," -v a2="\"attempt\":$K}" \
               '(index($0,"\"kind\":\"attempt.succeeded\"") || index($0,"\"kind\":\"attempt.failed\"") \
                 || index($0,"\"kind\":\"paused\"") || index($0,"\"kind\":\"aborted\"")) \
                && index($0,l) && index($0,t) && (index($0,a1) || index($0,a2)) {found=1; exit}
                END {exit !found}' "$JOURNAL"; }; then
    die "attempt $K of task $N already left its trace — a try ref, a failure report, or a
journal line closing it (a success, a failure, a pause, an abort). An attempt number is
never reused — a rewound success, an untouched stop and a reportless failure all count:
pass the next free number."
fi

# The mark alone authenticates a SHA, never an identity: nothing else could
# later prove WHICH task and attempt the mark belongs to, and every closing
# script consumes the caller's word for it. The identity file is that proof —
# written here, checked by every closer, removed by the one that closes.
INFLIGHT="$WORKSPACE/attempt-in-flight"
if [ -f "$INFLIGHT" ]; then
    F_LOT=; F_N=; F_K=
    read -r F_LOT F_N F_K < "$INFLIGHT" || true
    RESULT=
    STABLE="refs/bwr/$(basename "$WORKSPACE")/$F_LOT/task-$F_N"
    TRY="refs/bwr/$(basename "$WORKSPACE")/$F_LOT/task-$F_N-try-$F_K"
    if SHA=$(git rev-parse --verify --quiet "$STABLE"); then
        RESULT="The stable task ref exists at $SHA. Recover its gate operation with:
bash prompts/construction/gate-check.sh find-task $F_LOT $F_N $F_K $SHA
Then rerun attempt-succeeded.sh $F_LOT $F_N $SHA <that op>; that owning closer finishes
its attempt.succeeded and identity-removal tail."
    elif git rev-parse --verify --quiet "$TRY" >/dev/null; then
        ROUTE=$(attempt_closer_route "$INFLIGHT" || true)
        RESULT="The try ref exists. $ROUTE That owning closer finishes its note,
diagnostic or identity-removal tail."
    else
        RESULT="No result ref exists. The attempt or its session launch is still open. If
create_session's result was lost, query for the implementer by its annotations and create
it against the existing mark only when none exists. Otherwise close the active attempt."
    fi
    # A start is never the owner of an earlier attempt's tail. The identity
    # falls last, so even a result ref proves only that one closing gesture
    # landed. Replacing it would erase the only authentication for the rest.
    die "attempt-in-flight still names $F_LOT task $F_N attempt $F_K.
$RESULT
Only that closer or the exact tail it printed may remove the identity. Never replace it.
Nothing was marked and no session exists."
fi
# The MARK first, the identity SECOND — the order is load-bearing. The identity
# is the durable claim that a start completed; written before the mark, a cut
# between the two leaves the new identity beside the PREVIOUS attempt's
# still-valid mark — indistinguishable from a completed start — and a recovery
# seated on that stale mark makes the next controller commit read as the
# implementer's own, to be preserved and reset off the branch. Written after,
# a cut leaves a re-posted mark and no identity: no session exists yet, the
# tree is still clean, and rerunning this same call is a safe retry — the
# update-ref re-posts the same HEAD.
git update-ref "$RUN/$LOT/attempt-base" HEAD
{
    printf '%s %s %s\n' "$LOT" "$N" "$K"
    printf 'plan %s %s ownership %s contract %s retry %s\n' \
        "$PLAN_ID" "$TASKS" "$OWNERSHIP_ID" "$CONTRACT_ID" "$RETRY_PROOF"
} > "$INFLIGHT.tmp"
mv "$INFLIGHT.tmp" "$INFLIGHT"

printf 'ATTEMPT lot %s task %s try %s\nFROM %s\n' "$LOT" "$N" "$K" "$(git rev-parse HEAD)"
