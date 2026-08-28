#!/usr/bin/env bash
# Closes the diagnostic worktree that attempt-failed.sh opened.
#
# It rebuilds the path from the same ordinary or Correction identity, so
# nobody has to carry it across turns — and a path printed twenty messages ago is exactly what a
# compaction takes away.
#
# --force: the worktree is disposable by construction, and a reader who left a
# file in it must not be able to block the cleanup.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/disposable-worktree.sh"

CORRECTION=
if [ "${1:-}" = "--correction" ]; then
    shift
    [ $# -eq 4 ] || die "4 arguments expected after --correction, $# given — usage: diagnostic-close.sh --correction <built> <round> <task N> <attempt K>"
    LOT=$1 CORRECTION=$2 N=$3 K=$4
    [[ $CORRECTION =~ ^[1-9][0-9]*$ ]] \
        || die "the Correction round must be a positive integer without leading zeros, got \`$CORRECTION\`"
    MANIFEST="reports/construction/$LOT/correction-$CORRECTION/task-$N-attempt-$K-diagnostic.json"
    "$WORKSPACE/prompts/common/progress.py" construction-diagnostic-account \
        "$MANIFEST" >/dev/null
else
    [ $# -eq 3 ] || die "3 arguments expected, $# given — usage: diagnostic-close.sh <lot> <task N> <attempt K>"
    LOT=$1 N=$2 K=$3
fi
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\`"
[[ $K =~ ^[1-9][0-9]*$ ]] || die "the attempt number must be a positive integer without leading zeros, got \`$K\`"
# Rebuilt exactly as attempt-failed.sh built it: inside this repository's own
# ignored ground — /tmp is shared across repositories — and namespaced by the
# run, so neither another repository's checkout nor another feature's can ever
# be the path this removes.
disposable_ground_prepare "$REPO"
if [ -n "$CORRECTION" ]; then
    TMP="$DISPOSABLE_GROUND/bwr-$(basename "$WORKSPACE")-$LOT-correction-$CORRECTION-task-$N-try-$K"
else
    TMP="$DISPOSABLE_GROUND/bwr-$(basename "$WORKSPACE")-$LOT-task-$N-try-$K"
fi

cd "$REPO"

# An attempt that left the tree untouched — a failure at the design stage — had
# nothing to preserve, so attempt-failed.sh opened no worktree. Closing what was
# never opened is a no-op, not an error: the routing calls this every time, and
# it must not stop the run over a directory that was never meant to exist.
#
# The prune is not decoration: a registration can outlive its checkout — a
# /tmp sweep, a killed operation — and Git would then refuse the next open of
# this same path. This route is the cleanup, so it clears that state too.
if [ ! -e "$TMP" ] && [ ! -L "$TMP" ]; then
    git worktree prune
    printf 'NOTHING TO REMOVE — %s was never opened, or its checkout was already gone\n' "$TMP"
    exit 0
fi

disposable_remove_owned_worktree "$REPO" "$DISPOSABLE_GROUND" "$TMP"
printf 'REMOVED %s\n' "$TMP"
