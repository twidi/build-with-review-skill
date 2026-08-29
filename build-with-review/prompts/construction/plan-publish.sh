#!/usr/bin/env bash
# The implementer refreshes the repository's copy of the plan, just before its
# commit, so its ### Design block travels with the code it describes.
#
# It prints the target path: that is what the implementer names in its commit.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"

if [ "${1:-}" = "--correction" ]; then
    shift
    exec python3 "$HERE/correction_artifact_publish.py" "$@"
fi

[ $# -eq 1 ] || die "1 argument expected, $# given — usage: plan-publish.sh <lot>   e.g. lot-1, lot-1.1"
LOT=$1
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
DOCUMENT_COPY="$WORKSPACE/prompts/common/document-copy.sh"
PROGRESS="$WORKSPACE/prompts/common/progress.py"
CONSTRUCTION_REVIEW="$WORKSPACE/prompts/construction/construction_review.py"
SOURCE_REL="plans/$LOT-plan.md"
# The source is authenticated before this script accepts it as the plan.
SOURCE=$("$DOCUMENT_COPY" source "$SOURCE_REL")

# The attempt identity freezes the controller-owned Task 1..T manifest before
# the implementer exists. Only this task's Design and authenticated Disagreement
# may travel in this refresh. Refuse any other plan change before the copy.
INFLIGHT="$WORKSPACE/attempt-in-flight"
[ -f "$INFLIGHT" ] || die "no attempt is in flight — the frozen plan manifest is absent,
so this task plan cannot be published"
F_LOT=; F_N=; F_K=; F_PLAN=; F_PLAN_ID=; F_TASKS=; F_OWNERSHIP=; F_OWNERSHIP_ID=; F_CONTRACT=; F_CONTRACT_ID=; F_RETRY=; F_RETRY_PROOF=; F_EXTRA=
{
    read -r F_LOT F_N F_K
    read -r F_PLAN F_PLAN_ID F_TASKS F_OWNERSHIP F_OWNERSHIP_ID F_CONTRACT F_CONTRACT_ID F_RETRY F_RETRY_PROOF F_EXTRA
} < "$INFLIGHT" || true
[ "$F_LOT" = "$LOT" ] \
    || die "the attempt in flight belongs to $F_LOT, not $LOT — no plan was published"
[ "$F_PLAN" = plan ] && [ -n "$F_PLAN_ID" ] \
    && [[ $F_TASKS =~ ^[1-9][0-9]*$ ]] \
    && [ "$F_OWNERSHIP" = ownership ] && [[ $F_OWNERSHIP_ID =~ ^[0-9a-f]{64}$ ]] \
    && [ "$F_CONTRACT" = contract ] && [[ $F_CONTRACT_ID =~ ^[0-9a-f]{64}$ ]] \
    && [ "$F_RETRY" = retry ] && [[ $F_RETRY_PROOF = - || $F_RETRY_PROOF =~ ^[0-9]+:[0-9a-f]{64}$ ]] \
    && [ -z "$F_EXTRA" ] \
    || die "the attempt identity has no valid frozen plan manifest on line 2 — no plan was published"
CURRENT_MANIFEST=$("$PROGRESS" construction-plan-task-manifest "$LOT") \
    || die "the workspace plan has no exact structural Task 1..T manifest. Nothing was copied."
read -r CURRENT_TASKS CURRENT_PLAN_ID CURRENT_MANIFEST_EXTRA <<< "$CURRENT_MANIFEST"
[ -z "$CURRENT_MANIFEST_EXTRA" ] \
    || die "the workspace plan returned a malformed structural task manifest account. Nothing was copied."
[ "$CURRENT_TASKS" = "$F_TASKS" ] && [ "$CURRENT_PLAN_ID" = "$F_PLAN_ID" ] \
    || die "the workspace plan's Task 1..T manifest changed after this attempt started.
The implementer may write its own Design, but may not change task headings or
decomposition. Restore the frozen manifest before publishing. Nothing was copied."
CURRENT_STATE=$(python3 "$CONSTRUCTION_REVIEW" plan-state "$LOT" "$F_N") \
    || die "the current plan ownership cannot be authenticated — nothing was copied"
CURRENT_CONTRACT_ID=$(printf '%s\n' "$CURRENT_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["contract_sha256"])')
CURRENT_OWNERSHIP_ID=$(printf '%s\n' "$CURRENT_STATE" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_ownership_sha256"])')
[ "$CURRENT_CONTRACT_ID" = "$F_CONTRACT_ID" ] \
    || die "the workspace plan changed the controller-owned contract for task $F_N.
Only the implementer-owned Design and the documented Disagreement projection may change.
Restore the frozen contract before publishing. Nothing was copied."
[ "$CURRENT_OWNERSHIP_ID" = "$F_OWNERSHIP_ID" ] \
    || die "the workspace plan changes controller-owned bytes outside task $F_N's Design
and documented Disagreement. Restore the frozen whole-plan ownership projection before
publishing. Nothing was copied."

# Same stem as plan-commit.sh, computed the same way: the workspace's name.
TARGET_REL="docs/plans/$(basename "$WORKSPACE")-$LOT-plan.md"
TARGET="$REPO/$TARGET_REL"

controller_physical_admission_acquire "$WORKSPACE" \
    || die "$CONTROLLER_PHYSICAL_ADMISSION_ERROR"
if ! controller_operation_refuse_pending "$WORKSPACE" amendment-attempt-settle gate-check; then
    die "$CONTROLLER_OPERATION_ERROR. Plan publication must happen before the final gate opens. Nothing was copied."
fi

# A task refresh requires the existing destination to remain one real file.
# The helper rechecks both sides, copies to a real same-directory temporary,
# then atomically replaces the target without following any alias.
"$DOCUMENT_COPY" copy "$SOURCE_REL" "$TARGET_REL" existing
"$DOCUMENT_COPY" finish "$SOURCE_REL" "$TARGET_REL" existing
controller_physical_admission_release
printf '%s\n' "$TARGET"
