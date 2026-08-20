#!/usr/bin/env bash
# Opens, or authenticates as already open, one failed attempt's diagnostic worktree.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/disposable-worktree.sh"

[ $# -eq 3 ] || die "3 arguments expected, $# given — usage: diagnostic-open.sh <lot> <task N> <attempt K>"
LOT=$1 N=$2 K=$3
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\`"
[[ $K =~ ^[1-9][0-9]*$ ]] || die "the attempt number must be a positive integer without leading zeros, got \`$K\`"

RUN_NAME=$(basename "$WORKSPACE")
TRY="refs/bwr/$RUN_NAME/$LOT/task-$N-try-$K"
git -C "$REPO" rev-parse --verify --quiet "$TRY" >/dev/null \
    || die "$TRY does not exist — no preserved attempt owns a diagnostic checkout"
TRY_SHA=$(git -C "$REPO" rev-parse "$TRY")

disposable_ground_prepare "$REPO"
TMP="$DISPOSABLE_GROUND/bwr-$RUN_NAME-$LOT-task-$N-try-$K"
git -C "$REPO" worktree prune
if [ -e "$TMP" ] || [ -L "$TMP" ]; then
    disposable_require_owned_worktree "$REPO" "$DISPOSABLE_GROUND" "$TMP"
    [ "$(git -C "$TMP" rev-parse HEAD 2>/dev/null)" = "$TRY_SHA" ] \
        || die "the registered diagnostic worktree does not stand at $TRY: $TMP"
    printf 'ALREADY OPEN %s\n' "$TMP"
    exit 0
fi

disposable_assert_available "$REPO" "$DISPOSABLE_GROUND" "$TMP"
git -C "$REPO" worktree add --detach "$TMP" "$TRY" >/dev/null \
    || die "could not open the diagnostic worktree at $TMP"
disposable_require_owned_worktree "$REPO" "$DISPOSABLE_GROUND" "$TMP"
printf 'OPENED %s\n' "$TMP"
