#!/usr/bin/env bash
# The whole feature is finished: drop every working ref in one sweep.
#
# Only when the human says so. A sub-lot may follow immediately, the next lot
# may follow after it, and every one of them reads these refs.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"

[ $# -le 1 ] || die "0 or 1 argument expected, $# given — usage: refs-clear.sh [<lot>]   no lot means every ref of this run"
# The argument reaches git as a ref PATTERN, where glob characters expand: a
# `lot-*` would select every sibling lot and delete the only handles on their
# failed and rewound commits. The grammar makes a glob impossible.
if [ $# -eq 1 ]; then
    [[ $1 =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] \
        || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros, never a pattern — got \`$1\`"
fi

# Scoped to this workspace's own namespace, never to refs/bwr/ as a whole:
# another feature of the same repository lives under its own, and a git worktree
# shares the repository's refs.
RUN="refs/bwr/$(basename "$WORKSPACE")"
PREFIX="$RUN/${1:+$1/}"

# Recheck a legacy pass-opening abort owner before the first ref mutation.
CLEANUP_SCOPE=whole-run
if [ $# -eq 1 ]; then CLEANUP_SCOPE=lot; fi
python3 "$WORKSPACE/prompts/common/progress.py" \
    pass-opening-cleanup-check refs-clear "$CLEANUP_SCOPE"

cd "$REPO"
mapfile -t refs < <(git for-each-ref "$PREFIX" --format='%(refname)')
if [ ${#refs[@]} -eq 0 ]; then
    printf 'NOTHING TO DELETE under %s\n' "$PREFIX"
    exit 0
fi

for ref in "${refs[@]}"; do
    git update-ref -d "$ref"
done

printf 'DELETED %d refs under %s\n' "${#refs[@]}" "$PREFIX"
