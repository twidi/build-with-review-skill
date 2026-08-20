#!/usr/bin/env bash
# Shared physical-ownership checks for verifier and diagnostic worktrees.
# Sourced by callers that already define die().

disposable_real_directory() {
    local path=$1 subject=$2 physical
    [ ! -L "$path" ] || die "refused: $subject is a symlink: $path
Nothing was followed, created, removed, or registered."
    if [ -e "$path" ] && [ ! -d "$path" ]; then
        die "refused: $subject is not a directory: $path
Nothing was followed, created, removed, or registered."
    fi
    if [ ! -e "$path" ]; then
        mkdir -- "$path" || die "cannot create $subject: $path"
    fi
    physical=$(cd "$path" 2>/dev/null && pwd -P) \
        || die "cannot resolve $subject: $path"
    [ "$physical" = "$path" ] || die "refused: $subject resolves outside its exact path:
  written   $path
  physical  $physical
Nothing was followed, created, removed, or registered."
}

disposable_ground_prepare() {
    local repo=$1 repo_physical component
    repo_physical=$(cd "$repo" 2>/dev/null && pwd -P) \
        || die "cannot resolve the disposable checkout: $repo"
    [ "$repo_physical" = "$repo" ] || die "refused: the disposable checkout is not its exact physical path:
  written   $repo
  physical  $repo_physical"
    for component in "$repo/.superpowers" "$repo/.superpowers/bwr" \
                     "$repo/.superpowers/bwr/tmp"; do
        disposable_real_directory "$component" "the disposable-worktree ground component"
    done
    DISPOSABLE_GROUND="$repo/.superpowers/bwr/tmp"
}

disposable_parent_prepare() {
    local ground=$1 parent=$2
    [ "$(dirname -- "$parent")" = "$ground" ] \
        || die "refused: the disposable owner is not a direct child of its ground: $parent"
    disposable_real_directory "$parent" "the disposable-worktree owner"
}

disposable_parent_if_present() {
    local ground=$1 parent=$2
    [ "$(dirname -- "$parent")" = "$ground" ] \
        || die "refused: the disposable owner is not a direct child of its ground: $parent"
    [ ! -L "$parent" ] || die "refused: the disposable-worktree owner is a symlink: $parent
Nothing was followed or removed."
    if [ ! -e "$parent" ]; then
        return 1
    fi
    disposable_real_directory "$parent" "the disposable-worktree owner"
}

disposable_leaf_validate() {
    local parent=$1 leaf=$2 physical
    [ "$(dirname -- "$leaf")" = "$parent" ] \
        || die "refused: the disposable leaf is not a direct child of its owner: $leaf"
    [ ! -L "$leaf" ] || die "refused: the disposable-worktree leaf is a symlink: $leaf
Nothing was followed or removed."
    if [ ! -e "$leaf" ]; then
        return 1
    fi
    [ -d "$leaf" ] || die "refused: the disposable-worktree leaf is not a directory: $leaf
Nothing was followed or removed."
    physical=$(cd "$leaf" 2>/dev/null && pwd -P) \
        || die "cannot resolve the disposable-worktree leaf: $leaf"
    [ "$physical" = "$leaf" ] || die "refused: the disposable-worktree leaf resolves outside its exact owner:
  written   $leaf
  physical  $physical
Nothing was followed or removed."
}

disposable_worktree_registered() {
    local repo=$1 leaf=$2 record
    while IFS= read -r -d '' record; do
        case "$record" in
            "worktree "*) [ "${record#worktree }" = "$leaf" ] && return 0 ;;
        esac
    done < <(git -C "$repo" worktree list --porcelain -z)
    return 1
}

disposable_assert_available() {
    local repo=$1 parent=$2 leaf=$3
    if disposable_leaf_validate "$parent" "$leaf"; then
        die "refused: an object already occupies the disposable-worktree leaf: $leaf"
    fi
    disposable_worktree_registered "$repo" "$leaf" \
        && die "refused: Git still registers the absent disposable-worktree leaf: $leaf"
    return 0
}

disposable_require_owned_worktree() {
    local repo=$1 parent=$2 leaf=$3
    disposable_leaf_validate "$parent" "$leaf" \
        || die "the disposable worktree is absent: $leaf"
    disposable_worktree_registered "$repo" "$leaf" \
        || die "refused: the existing disposable leaf is not a worktree registered by this repository:
  $leaf
Nothing was followed or removed."
}

disposable_remove_owned_worktree() {
    local repo=$1 parent=$2 leaf=$3
    disposable_require_owned_worktree "$repo" "$parent" "$leaf"
    git -C "$repo" worktree remove --force "$leaf" \
        || die "Git refused to remove its registered disposable worktree: $leaf
No recursive filesystem fallback ran. Inspect the registration before retrying."
    [ ! -e "$leaf" ] && [ ! -L "$leaf" ] \
        || die "Git reported success but the disposable-worktree leaf still exists: $leaf"
}
