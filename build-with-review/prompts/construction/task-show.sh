#!/usr/bin/env bash
# One file as it was at a past task.
#
# Read-only by construction: nothing in the working tree, the index or HEAD
# moves, so this is how you look at an earlier state without opening a checkout.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"

if [ "${1:-}" = manifest ]; then
    [ $# -eq 4 ] || die "usage: task-show.sh manifest <checker manifest> <prior task N> <path>"
    exec python3 "$WORKSPACE/prompts/common/progress.py" \
        construction-checker-task-show "$2" "$3" "$4"
fi

[ $# -eq 3 ] || die "3 arguments expected, $# given — usage: task-show.sh <lot> <task N> <path>   the path is relative to the repository root"
LOT=$1 N=$2 FILE=$3
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\` — task-0 is the lot's starting point, not a task"
RUN="refs/bwr/$(basename "$WORKSPACE")"   # this run's own ref namespace — see vocabulary.md
REF="$RUN/$LOT/task-$N"

cd "$REPO"
git rev-parse --verify --quiet "$REF" >/dev/null || die "$REF does not exist"

git show "$REF:$FILE"
