#!/usr/bin/env bash
# The finding verifier checks every proof form in a copy of the tree, at the
# reviewed pass commit and at no other revision.
#
# It prints the path of that copy, and nothing else: the caller runs tests,
# reads cited lines and searches there, then closes it with verify-close.sh.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/disposable-worktree.sh"

[ $# -eq 2 ] || die "2 arguments expected, $# given — usage: verify-open.sh <reviewed commit> <report file name>   the SHA the report was written against, and the report's own file name"
SHA=$1 LABEL=$2
case "$LABEL" in
    */*) die "the second argument is a file NAME, not a path — e.g. lot-1-user.md" ;;
esac

# The journal owns the physical verification generation. Refuse before pruning,
# removing or creating anything unless this exact pass, report receipt and live
# finding-verifier bracket all agree.
python3 "$WORKSPACE/prompts/common/progress.py" pass-verifier-check "$SHA" "$LABEL"

cd "$REPO"
git rev-parse --verify --quiet "$SHA^{commit}" >/dev/null || die "$SHA is not a commit"

# The path is deterministic: the run's name plus the report's. One verifier
# runs per report. An existing worktree registered by this exact repository is
# a dead predecessor of the same verification and is removed. Any other object
# is foreign state and is refused untouched.
#
# Prune first: a registration can outlive its checkout — a /tmp sweep, a
# killed operation — and `worktree add` refuses a path Git still owns even
# when its directory is gone.
# Inside this repository's own ignored ground, never under a shared /tmp: the
# location separates two repositories that share a workspace name, and the
# run's name separates two features of this one — the dead-predecessor premise
# below is only true once both hold.
disposable_ground_prepare "$REPO"
OWNER="$DISPOSABLE_GROUND/bwr-verify-$(basename "$WORKSPACE")-$LABEL"
TMP="$OWNER/w"
git worktree prune
disposable_parent_prepare "$DISPOSABLE_GROUND" "$OWNER"
if [ -e "$TMP" ] || [ -L "$TMP" ]; then
    disposable_remove_owned_worktree "$REPO" "$OWNER" "$TMP"
fi
disposable_assert_available "$REPO" "$OWNER" "$TMP"
if ! git worktree add --detach "$TMP" "$SHA" >/dev/null; then
    rmdir "$OWNER" 2>/dev/null || true
    die "could not open the verification copy at $TMP — nothing is left behind"
fi
disposable_require_owned_worktree "$REPO" "$OWNER" "$TMP"

printf '%s\n' "$TMP"
