#!/usr/bin/env bash
# Moves a run's workspace into another checkout of the same repository.
#
# One case calls it, and only one: the feature moves into a git worktree once
# its spec is validated. The workspace holds the run's whole memory — the
# journal, the reports, the plans, the frozen prompts — and git ignores it, so
# `git worktree add` does not bring it along. Every script of this workflow
# derives the repository from the workspace's own path, so a workspace left
# behind means every commit, reset and ref lands in the checkout where the work
# is no longer being done. Silently, and on another branch.
#
# It lives in the skill directory, like the two other workspace-lifecycle
# scripts, and for a related reason: a script that moves the directory it runs
# from can be read out from under itself when the move crosses filesystems.
set -euo pipefail
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
SELF=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source "$SELF/disposable-worktree.sh"

[ $# -eq 2 ] \
    || die "2 arguments expected, $# given — usage: workspace-move.sh <workspace> <the checkout it moves to>"
TARGET=$(cd "$2" 2>/dev/null && pwd -P) || die "no such directory: $2"

# The name is checked before anything else, on the argument itself: it survives
# every partial state a killed move can leave. A parent of .superpowers/bwr no
# longer identifies a workspace on its own — the disposable checkouts live in
# bwr/tmp/, a direct sibling, and moving THAT would carry live diagnostic and
# verification worktrees away while reporting a moved run.
NAME=$(basename "${1%/}")
[[ $NAME =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(-[a-z0-9]+)*$ ]] \
    || die "refused: \`$NAME\` is not a run workspace's name — a workspace reads <date>-<feature>.
\`tmp\`, a \`.partial\`, and anything else under .superpowers/bwr/ is not a workspace."

# The source CHECKOUT outlives the workspace directory: a completed move
# removes only <bwr>/<name>, never its parents. Derive the checkout from the
# argument's LEXICAL parents first. Canonicalizing a symlinked bwr/ and then
# walking ../.. would silently replace the checkout identity with the alias's
# target.
SOURCE_INPUT=${1%/}
SRC_BWR_INPUT=$(dirname -- "$SOURCE_INPUT")
SRC_SUPER_INPUT=$(dirname -- "$SRC_BWR_INPUT")
[ "$(basename -- "$SRC_BWR_INPUT")" = bwr ] \
    && [ "$(basename -- "$SRC_SUPER_INPUT")" = .superpowers ] \
    || die "refused: $1 is not a workspace path — its parent must be .superpowers/bwr"
SRC_REPO=$(cd "$(dirname -- "$SRC_SUPER_INPUT")" 2>/dev/null && pwd -P) \
    || die "no such source checkout for: $1"
SRC_TOP=$(git -C "$SRC_REPO" rev-parse --show-toplevel 2>/dev/null) \
    || die "$SRC_REPO is not a git checkout"
SRC_TOP=$(cd "$SRC_TOP" && pwd -P)
[ "$SRC_TOP" = "$SRC_REPO" ] \
    || die "refused: the source workspace ground is not at its checkout root:
  checkout root  $SRC_TOP
  workspace root $SRC_REPO
Nothing was moved or deleted."
TGT_TOP=$(git -C "$TARGET" rev-parse --show-toplevel 2>/dev/null) \
    || die "$TARGET is not a git checkout"
TGT_TOP=$(cd "$TGT_TOP" && pwd -P)
[ "$TGT_TOP" = "$TARGET" ] \
    || die "refused: pass the target checkout root, not one of its subdirectories:
  checkout root  $TGT_TOP
  argument       $TARGET
Nothing was moved or deleted."
SRC_SUPER="$SRC_REPO/.superpowers"
SRC_BWR="$SRC_SUPER/bwr"

# The source ground is an identity boundary, not a route to some other object.
for component in "$SRC_SUPER" "$SRC_BWR"; do
    [ ! -L "$component" ] \
        || die "refused: the source workspace ground contains a symlink: $component
Nothing was moved or deleted."
    [ -d "$component" ] \
        || die "refused: the source workspace ground is not a real directory: $component"
done
SRC_BWR_PHYSICAL=$(cd "$SRC_BWR" && pwd -P)
[ "$SRC_BWR_PHYSICAL" = "$SRC_BWR" ] \
    || die "refused: the source workspace ground resolves outside its checkout:
  written   $SRC_BWR
  physical  $SRC_BWR_PHYSICAL
Nothing was moved or deleted."

# The target ground may not exist yet. Every component that does exist must be
# a real directory at this physical checkout path.
TGT_SUPER="$TARGET/.superpowers"
TGT_BWR="$TGT_SUPER/bwr"
for component in "$TGT_SUPER" "$TGT_BWR"; do
    [ ! -L "$component" ] \
        || die "refused: the target workspace ground contains a symlink: $component
Nothing was moved or deleted."
    if [ -e "$component" ] && [ ! -d "$component" ]; then
        die "refused: the target workspace ground component is not a directory: $component"
    fi
done
if [ -d "$TGT_BWR" ]; then
    TGT_BWR_PHYSICAL=$(cd "$TGT_BWR" && pwd -P)
    [ "$TGT_BWR_PHYSICAL" = "$TGT_BWR" ] \
        || die "refused: the target workspace ground resolves outside its checkout:
  written   $TGT_BWR
  physical  $TGT_BWR_PHYSICAL
Nothing was moved or deleted."
fi

GONE=
SOURCE="$SRC_BWR/$NAME"
if [ -L "$SOURCE" ]; then
    die "refused: the source workspace root is a symlink: $SOURCE
Birthmarks reached through an alias do not identify a movable workspace. Nothing was
moved or deleted."
fi
if [ -e "$SOURCE" ] && [ ! -d "$SOURCE" ]; then
    die "refused: the source workspace root is not a directory: $SOURCE"
fi
if [ -d "$SOURCE" ]; then
    SOURCE_PHYSICAL=$(cd "$SOURCE" && pwd -P)
    [ "$SOURCE_PHYSICAL" = "$SOURCE" ] \
        || die "refused: the source workspace resolves outside its checkout identity:
  written   $SOURCE
  physical  $SOURCE_PHYSICAL
Nothing was moved or deleted."
else
    # The source is gone. A completed move whose report was lost — the earlier
    # call died between its source removal and its last line — leaves exactly
    # this. Answer for it instead of failing on a directory nothing brings
    # back — but only for a destination that really is the moved workspace
    # (the frozen SKILL.md and prompts/ are its birthmark), and only once
    # every identity check below has passed, exactly as on a fresh move.
    DONE="$TGT_BWR/$NAME"
    [ ! -L "$DONE" ] && [ -d "$DONE" ] \
        || die "no such directory: $1"
    DONE_PHYSICAL=$(cd "$DONE" && pwd -P)
    [ "$DONE_PHYSICAL" = "$DONE" ] \
        || die "refused: the completed destination resolves outside its checkout identity:
  written   $DONE
  physical  $DONE_PHYSICAL
Nothing was moved or deleted."
    [ -f "$DONE/SKILL.md" ] && [ -d "$DONE/prompts" ] \
        || die "no such directory: $1"
    GONE=1
fi

case "$SELF" in
    "$SOURCE"/*) die "this copy lives inside the workspace it was asked to move — run the skill's own" ;;
esac

# The same repository, not merely a repository: the run's refs live in the
# repository's shared store — that is the whole reason a worktree move is safe —
# and an unrelated clone or a foreign checkout satisfies an `-e .git` test just
# as well. Two checkouts of one repository share one common dir; nothing else
# does.
SRC_COMMON=$(cd "$SRC_REPO" && cd "$(git rev-parse --git-common-dir)" && pwd -P) \
    || die "cannot read the source repository at $SRC_REPO"
TGT_COMMON=$(cd "$TARGET" && cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P) \
    || die "$TARGET is not a git checkout"
[ "$SRC_COMMON" = "$TGT_COMMON" ] \
    || die "$TARGET is not a checkout of the same repository — its git store is
$TGT_COMMON, the workspace's is $SRC_COMMON. The run's refs live in the repository's
shared store, so a move to a foreign checkout strands every commit, reset and ref the
frozen scripts would make there. Nothing was moved. Pass a worktree of THIS repository."

# Same repository is not enough: the run continues WHERE it stood, and every
# task commit lands on the target's HEAD. Both facts are checked here, read-only,
# before any branch of this script — fix the worktree, then run the same call.
#
# Attached, first: on a detached HEAD every task commit would land on no branch
# at all. The run's task refs keep them reachable just long enough to finish —
# then the end-of-feature cleanup deletes those refs, and no named branch holds
# the delivered feature.
git -C "$TARGET" symbolic-ref -q HEAD >/dev/null \
    || die "$TARGET is on a detached HEAD — every commit the run makes there would land on
no branch, kept reachable only by the run's own refs until the cleanup deletes them.
Nothing was moved. Check out a branch in that worktree, then run this again."

# And at the same commit: the source's HEAD is the validated state the handover
# transfers — the spec commit sits there, and the journal and reports describe
# it. A worktree cut earlier, or left on another branch, silently swaps the
# document everything downstream builds against.
SRC_HEAD=$(git -C "$SRC_REPO" rev-parse HEAD)
TGT_HEAD=$(git -C "$TARGET" rev-parse HEAD)
[ "$SRC_HEAD" = "$TGT_HEAD" ] \
    || die "$TARGET does not stand at the validated state the run leaves from —
its HEAD is $TGT_HEAD, the workspace's checkout is at $SRC_HEAD, where the committed
spec lives. Nothing was moved. Put the worktree's branch on that commit — or take the
difference to the human if the branch has real work of its own — then run this again."

# The same condition creation refused to start without, and for the same reason:
# a worktree carries its own .gitignore, and it may not be the one you left.
git -C "$TARGET" check-ignore -q .superpowers/bwr \
    || die "\`.superpowers/\` is not ignored in $TARGET.

Nothing was moved. Settle it there exactly as at creation — the human chooses between
\`.gitignore\`, which must then be committed, and \`.git/info/exclude\` — then run this again."

# The gate file sits BESIDE the workspaces, not inside one: it belongs to the
# project, and the next feature inherits it. Git ignores it too, so a fresh
# worktree has none — and the run would walk into a first discovery it has
# already been through, interrupting the human for a list they validated.
#
# Settled by EACH BRANCH, after its own eligibility and before its irreversible
# gesture — never earlier: settled up front, an ordinary refusal (an alias, a
# differing destination, a stripped source) would already have installed this
# run's gate into a checkout the human may keep as it is, and a later C0 would
# read a file no human validated for it. The source's gate.md sits beside the
# workspaces and was never deleted, so the comparison holds whether or not the
# workspace itself is still here.
validate_gate_leaf() {
    local path=$1 side=$2
    if [ -L "$path" ] || { [ -e "$path" ] && [ ! -f "$path" ]; }; then
        die "refused: the $side gate.md is neither absent nor a real checkout-local
regular file:
  $path
Nothing was followed, copied, moved, or deleted. A human must classify this foreign
state before handover can continue."
    fi
}

settle_gate() {
    GATE="$SRC_BWR/gate.md"
    TGATE="$TGT_BWR/gate.md"
    # Classify both leaves before disposable_ground_prepare creates anything
    # in the target. A dangling alias is occupied, never first discovery.
    validate_gate_leaf "$GATE" source
    validate_gate_leaf "$TGATE" target
    disposable_ground_prepare "$TARGET"
    GATE_TAKEN="none to carry"
    if [ -f "$GATE" ]; then
        if [ ! -f "$TGATE" ]; then
            cp "$GATE" "$TGATE"
            GATE_TAKEN="gate.md carried over"
        elif cmp -s "$GATE" "$TGATE"; then
            GATE_TAKEN="gate.md already there, identical"
        else
            # Which list this run closes tasks against is not a script's
            # decision: the source's was validated by this run, the target's by
            # somebody at some time — silently keeping either hands every later
            # task a gate nobody chose.
            die "the two checkouts hold DIFFERENT gate.md files, and which one this run
closes tasks against is not a script's decision:
  source  $GATE
  target  $TGATE
Nothing was moved. Take both to the human, then carry their choice onto BOTH files —
copy the chosen list over the other one, whichever side they picked — and run this
again. The retry proceeds on two identical files; aligning the target alone cannot
encode a choice of the target's own list, and would refuse forever."
        fi
    fi
}

# The recovery answers once every identity and invariant check above has passed
# for this target, exactly as on a fresh move — the gate settled last, its own
# eligibility being those same checks.
if [ -n "$GONE" ]; then
    settle_gate
    printf 'MOVED (already — the source is gone)\n   TO %s\nGATE %s\n' \
        "$TGT_BWR/$NAME" "$GATE_TAKEN"
    exit 0
fi

DEST="$TGT_BWR/$NAME"
STAGE="$DEST.partial"
# Both paths name exact physical checkout-local grounds. Equality means the
# target IS the checkout the workspace already lives in. Refused before every
# other branch: recovery must never delete the run's only object through an
# alias.
if [ "$DEST" = "$SOURCE" ]; then
    die "the target is the checkout this workspace already lives in — source and
destination are the same directory. Nothing was touched. Pass the worktree the work is
moving TO, never the checkout it is moving from."
fi
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    [ ! -L "$DEST" ] && [ -d "$DEST" ] \
        || die "refused: the existing destination is not a real directory: $DEST
Nothing was moved or deleted."
    DEST_PHYSICAL=$(cd "$DEST" && pwd -P)
    [ "$DEST_PHYSICAL" = "$DEST" ] \
        || die "refused: the destination resolves outside its checkout identity:
  written   $DEST
  physical  $DEST_PHYSICAL
Nothing was moved or deleted."

    SOURCE_ID=$(stat -Lc '%d:%i' -- "$SOURCE") \
        || die "cannot read the source workspace identity: $SOURCE"
    DEST_ID=$(stat -Lc '%d:%i' -- "$DEST") \
        || die "cannot read the destination workspace identity: $DEST"
    [ "$SOURCE_ID" != "$DEST_ID" ] \
        || die "refused: source and destination are aliases of the same directory:
  source       $SOURCE
  destination  $DEST
Nothing was moved or deleted."

    # Both ends exist. An interrupted earlier call can leave this state only
    # AFTER its rename — the copy was complete, and what did not finish is the
    # source removal — so the two trees are identical, and finishing is this
    # script's to do. Anything else is not.
    if diff -rq "$SOURCE" "$DEST" >/dev/null 2>&1; then
        settle_gate
        find "$SOURCE" -delete
        printf 'MOVED %s\n   TO %s\nGATE %s\n' "$SOURCE" "$DEST" "$GATE_TAKEN"
        exit 0
    fi
    die "$DEST already exists and differs from $SOURCE — nothing was moved.
If an earlier call was interrupted, the destination holds the complete workspace — the
rename is atomic — and the source is the leftover of its half-done removal: check, then
remove the source with \`find <source> -delete\`. Otherwise two workspaces answer to one
name, and only a human can say which one this run continues."
fi

# A fresh move carries a complete workspace or nothing: the frozen SKILL.md and
# prompts/ are what the new controller runs on, and a directory without them is
# not this run, whatever its name. Checked only here — the recovery branches
# above legitimately meet a source a killed deletion has already stripped.
[ -f "$SOURCE/SKILL.md" ] && [ -d "$SOURCE/prompts" ] \
    || die "refused: $SOURCE does not hold a frozen SKILL.md and prompts/ — it is not a
complete workspace, and moving it would hand the new controller a run with no
instructions. Nothing was moved."

# Eligibility is proved; the gate settles now, still before the irreversible
# copy-rename-delete below.
settle_gate

# A move that crosses filesystems is a copy plus a removal, never one gesture.
# Copied whole onto the destination filesystem under a name nothing adopts,
# made real by an atomic rename, the source removed only then: a death at any
# point leaves a complete source or a complete destination, never two halves.
# A leftover .partial is a dead predecessor of this same move — remove it and
# start clean.
rm -rf "$STAGE"
cp -a "$SOURCE" "$STAGE"
mv -T -- "$STAGE" "$DEST"
find "$SOURCE" -delete
printf 'MOVED %s\n   TO %s\nGATE %s\n' "$SOURCE" "$DEST" "$GATE_TAKEN"
