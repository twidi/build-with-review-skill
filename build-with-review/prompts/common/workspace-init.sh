#!/usr/bin/env bash
# Creates the run's workspace. The ONLY script called from the skill directory,
# because the workspace it creates does not exist yet.
set -euo pipefail
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }

[ $# -eq 1 ] || die "1 argument expected, $# given — usage: workspace-init.sh <feature>   the short name, no date, no suffix"
FEATURE=$1

[[ $FEATURE =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] \
    || die "the feature must be a slug: lowercase letters, digits, single hyphens — e.g. peer-revocation"
[[ ! $FEATURE =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}- ]] \
    || die "the feature carries a date — pass the short name alone, e.g. peer-revocation"

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
case "$SKILL" in
    */.superpowers/bwr/*) die "this is a workspace copy — run this script from the skill directory" ;;
esac
source "$SKILL/prompts/common/disposable-worktree.sh"

REPO=$(git rev-parse --show-toplevel) || die "not inside a git repository"
REPO=$(cd "$REPO" && pwd -P)

# Workspace identity belongs to this checkout's physical ground. Neither the
# ground nor a workspace root may be a symlink: birthmarks reached through an
# alias do not prove which run or checkout owns the object behind it.
SUPER="$REPO/.superpowers"
GROUND="$SUPER/bwr"
for component in "$SUPER" "$GROUND"; do
    [ ! -L "$component" ] \
        || die "refused: the workspace ground contains a symlink: $component
Nothing was adopted, deleted, or created. Replace the alias with a real checkout-local
directory only after the human has classified what it points to."
    if [ -e "$component" ] && [ ! -d "$component" ]; then
        die "refused: the workspace ground component is not a directory: $component"
    fi
done
if [ -d "$GROUND" ]; then
    GROUND_PHYSICAL=$(cd "$GROUND" && pwd -P)
    [ "$GROUND_PHYSICAL" = "$GROUND" ] \
        || die "refused: the workspace ground resolves outside its checkout-local path:
  written   $GROUND
  physical  $GROUND_PHYSICAL
Nothing was adopted, deleted, or created."
fi

# gate.md is project-owned executable policy, not an arbitrary object reached
# through this now-authenticated ground. It is either absent for first
# discovery or one real regular file at the exact checkout-local leaf.
GATE="$GROUND/gate.md"
if [ -L "$GATE" ] || { [ -e "$GATE" ] && [ ! -f "$GATE" ]; }; then
    die "refused: gate.md is neither absent nor a real checkout-local regular file:
  $GATE
Nothing was followed, adopted, deleted, or created. A human must classify this foreign
state before workspace setup can continue."
fi

# The workspace must be outside git, and nothing else in the run checks it. That
# is what keeps a reset from taking the plan away with the code, and what keeps a
# failed attempt's `git add -A` from sweeping this run's own machinery — prompts,
# journal, reports — into a commit that claims to carry a task.
#
# check-ignore answers from every source at once: .gitignore, .git/info/exclude,
# the global one. It needs no existing file, only the path.
if ! git -C "$REPO" check-ignore -q .superpowers/bwr; then
    die "\`.superpowers/\` is not ignored by git, so the workspace would be inside the repository.

Nothing is created until that is settled. Ask the human where to put the rule, and add the
line \`.superpowers/\` yourself once they have answered:

  .git/info/exclude   local to this clone, shared by its worktrees, not tracked — nothing
                      else to do afterwards
  .gitignore          versioned, every clone gets it — you must also COMMIT it, that path
                      alone, or the modification sits in the tree and every task's
                      clean-tree check refuses

Then run this script again."
fi

# A feature is built across several sessions, and only the first one creates
# anything. The search ignores the date — the workspace was made on another day —
# and re-copying prompts/ would swap the instructions under sessions that are
# still running.
#
# The date is spelled out rather than globbed. `*-auth` would match
# `2026-08-18-user-auth`, and the run would resume another feature's prompts,
# plans, reports and journal as if they were its own.
FOUND=()
for candidate in "$REPO"/.superpowers/bwr/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-"$FEATURE"; do
    if [ -e "$candidate" ] || [ -L "$candidate" ]; then FOUND+=("$candidate"); fi
done
DELETING=()
for candidate in "$REPO"/.superpowers/bwr/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-"$FEATURE".deleting; do
    if [ -e "$candidate" ] || [ -L "$candidate" ]; then DELETING+=("$candidate"); fi
done

if [ ${#FOUND[@]} -gt 1 ]; then
    die "several workspaces answer to \`$FEATURE\`, and only a human can say which one this run continues:
$(printf '  %s\n' "${FOUND[@]}")"
fi
if [ ${#DELETING[@]} -gt 1 ]; then
    die "several deletion tombstones answer to \`$FEATURE\`, and no new run can start:
$(printf '  %s\n' "${DELETING[@]}")"
fi
if [ ${#FOUND[@]} -eq 1 ] && [ ${#DELETING[@]} -eq 1 ]; then
    die "both a workspace and its deletion tombstone answer to \`$FEATURE\`:
  ${FOUND[0]}
  ${DELETING[0]}
Nothing was changed. A human must resolve this collision."
fi
if [ ${#DELETING[@]} -eq 1 ]; then
    # The final-name workspace vanished before its contents did. The tombstone
    # is the durable cleanup boundary after progress.jsonl itself can be gone.
    # Finish only that deletion. This invocation must never create a new run.
    [ ! -L "${DELETING[0]}" ] && [ -d "${DELETING[0]}" ] \
        || die "refused: the deletion tombstone is not a real directory: ${DELETING[0]}
Nothing was followed or deleted. A human must classify this foreign state."
    DELETING_PHYSICAL=$(cd "${DELETING[0]}" && pwd -P)
    [ "$DELETING_PHYSICAL" = "${DELETING[0]}" ] \
        || die "refused: the deletion tombstone resolves to another filesystem object:
  written   ${DELETING[0]}
  physical  $DELETING_PHYSICAL
Nothing was followed or deleted."
    "$SKILL/prompts/common/workspace-delete.sh" "${DELETING[0]}" >/dev/null
    printf 'CLEANED %s\n' "${DELETING[0]%.deleting}"
    exit 0
fi
if [ ${#FOUND[@]} -eq 1 ]; then
    # Adopted only when it really is a frozen run: SKILL.md and prompts/ are
    # the workspace's birthmark — the same minimum the move script proves. The
    # .partial staging protects a killed CREATE. workspace-delete first renames
    # a run to .deleting, so its partial deletion cannot answer this final-name
    # search. A malformed final-name directory is therefore legacy or manual
    # state, and only a human can classify it.
    [ ! -L "${FOUND[0]}" ] && [ -d "${FOUND[0]}" ] \
        || die "refused: the workspace root is not a real directory: ${FOUND[0]}
Birthmarks reached through a symlink do not identify a run. Nothing was adopted."
    FOUND_PHYSICAL=$(cd "${FOUND[0]}" && pwd -P)
    [ "$FOUND_PHYSICAL" = "${FOUND[0]}" ] \
        || die "refused: the workspace resolves outside its checkout-local identity:
  written   ${FOUND[0]}
  physical  $FOUND_PHYSICAL
Nothing was adopted."
    if [ -f "${FOUND[0]}/SKILL.md" ] && [ -d "${FOUND[0]}/prompts" ]; then
        disposable_ground_prepare "$REPO"
        printf 'EXISTS %s\n' "${FOUND[0]}"
        exit 0
    fi
    die "a directory answers to \`$FEATURE\` but is not a complete workspace — no frozen
SKILL.md and prompts/ inside:
  ${FOUND[0]}
Only a human can say what it is: remove it, or recover what it still holds. Nothing was
created."
fi

# The workspace is checkout-local; the refs are repository-wide — every
# worktree shares refs/bwr/. A second checkout starting the same feature would
# share the first run's attempt-base, task refs and cleanup namespace, and git
# accepts every overwrite without a word. So the search crosses every worktree
# before anything is created, and a run found elsewhere is a refusal, never an
# adoption: the scripts derive the repository from the workspace's own path,
# so adopting it from here would aim every gesture at the other checkout.
# -z, and a NUL-delimited reader: without it git C-quotes an unusual checkout
# path, the parsed value is not the real path, the glob under it misses an
# existing run — and the very corruption this sweep exists to prevent becomes
# silent. With -z the path field is verbatim bytes.
validate_other_candidate() {
    local candidate=$1 checkout=$2 physical super ground component candidate_physical
    physical=$(cd "$checkout" && pwd -P) \
        || die "cannot resolve the registered checkout: $checkout"
    super="$physical/.superpowers"
    ground="$super/bwr"
    for component in "$super" "$ground"; do
        [ ! -L "$component" ] \
            || die "refused: another checkout's workspace ground contains a symlink:
  $component
Nothing was followed, deleted, or created."
        [ -d "$component" ] \
            || die "refused: another checkout's workspace ground is not a directory:
  $component"
    done
    [ ! -L "$candidate" ] && [ -d "$candidate" ] \
        || die "refused: another checkout has a non-directory or symlink at a run identity:
  $candidate
Nothing was followed, deleted, or created."
    candidate_physical=$(cd "$candidate" && pwd -P)
    [ "$candidate_physical" = "$ground/$(basename -- "$candidate")" ] \
        || die "refused: another checkout's run identity resolves outside its workspace ground:
  written   $candidate
  physical  $candidate_physical
Nothing was followed, deleted, or created."
}

while IFS= read -r -d '' rec; do
    case "$rec" in
        "worktree "*) wt=${rec#worktree } ;;
        *) continue ;;
    esac
    WT_PHYSICAL=$(cd "$wt" && pwd -P) || die "cannot resolve the registered checkout: $wt"
    [ "$WT_PHYSICAL" = "$REPO" ] && continue
    for candidate in "$WT_PHYSICAL"/.superpowers/bwr/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-"$FEATURE"; do
        if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then continue; fi
        validate_other_candidate "$candidate" "$WT_PHYSICAL"
        die "this feature already has a run in another checkout of this repository:
  $candidate
A repository's worktrees share refs/bwr/, so two runs answering to one feature would
corrupt each other's refs. Continue that run in its own checkout — or move it there
first, with workspace-move.sh. Nothing was created here."
    done
    for candidate in "$WT_PHYSICAL"/.superpowers/bwr/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-"$FEATURE".deleting; do
        if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then continue; fi
        validate_other_candidate "$candidate" "$WT_PHYSICAL"
        # Cleanup already removed the final name in that checkout. Finish its
        # only remaining tail, then stop. Never create a replacement here.
        "$SKILL/prompts/common/workspace-delete.sh" "$candidate" >/dev/null
        printf 'CLEANED %s\n' "${candidate%.deleting}"
        exit 0
    done
done < <(git -C "$REPO" worktree list --porcelain -z)

# Built under a name the existence glob cannot match, then renamed once whole:
# a copy that dies halfway must never leave a directory that the next call —
# or a later session — adopts as a complete frozen workspace. A leftover
# .partial is a predecessor of this same creation: remove it and start clean.
disposable_ground_prepare "$REPO"
WORKSPACE="$REPO/.superpowers/bwr/$(date +%F)-$FEATURE"
STAGE="$WORKSPACE.partial"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{plans,amendments,additional-prompts,reports/{spec-review,amendment,construction,product-review}}
cp -r "$SKILL/prompts"   "$STAGE/prompts"
cp    "$SKILL/SKILL.md"  "$STAGE/SKILL.md"
cp -r "$SKILL/dashboard" "$STAGE/dashboard"
mv "$STAGE" "$WORKSPACE"
printf 'CREATED %s\n' "$WORKSPACE"
