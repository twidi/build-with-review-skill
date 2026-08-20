#!/usr/bin/env bash
# Closes a verification copy. Always, whatever the verdict was.
#
# The path is REBUILT from the run and the report's name — never accepted from
# the caller: a force-remove must not be aimable at a checkout that is not this
# run's disposable copy. --force is required, not defensive: the verifier wrote
# a test file in there, so the worktree is dirty and `git worktree remove`
# refuses it. That refusal would leave one full copy of the tree behind per
# verified report.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/disposable-worktree.sh"

[ $# -eq 1 ] || die "1 argument expected, $# given — usage: verify-close.sh <report file name>   the same name verify-open.sh was given"
LABEL=$1
case "$LABEL" in
    */*) die "the argument is a file NAME, not a path — e.g. lot-1-user.md" ;;
esac

# Rebuilt exactly as verify-open.sh built it: inside this repository's own
# ignored ground — /tmp is shared across repositories — so the force-remove
# cannot reach another repository's live copy.
disposable_ground_prepare "$REPO"
OWNER="$DISPOSABLE_GROUND/bwr-verify-$(basename "$WORKSPACE")-$LABEL"
TMP="$OWNER/w"
cd "$REPO"

# Closing what is already gone is a no-op, not an error — and the prune clears
# a registration whose checkout disappeared under it.
if ! disposable_parent_if_present "$DISPOSABLE_GROUND" "$OWNER"; then
    git worktree prune
    printf 'NOTHING TO REMOVE — %s was not open\n' "$TMP"
    exit 0
fi
if [ ! -e "$TMP" ] && [ ! -L "$TMP" ]; then
    git worktree prune
    printf 'NOTHING TO REMOVE — %s was not open\n' "$TMP"
    exit 0
fi

disposable_remove_owned_worktree "$REPO" "$OWNER" "$TMP"
rmdir "$OWNER" 2>/dev/null || true

printf 'REMOVED %s\n' "$TMP"
