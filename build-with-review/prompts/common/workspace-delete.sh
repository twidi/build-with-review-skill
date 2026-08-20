#!/usr/bin/env bash
# Deletes a run's workspace, once the human says the whole feature is done.
#
# It lives in the skill directory and is never called from the copy: bash reads
# a script as it executes it, so a script that deletes itself breaks midway.
set -euo pipefail
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }

[ $# -eq 1 ] || die "1 argument expected, $# given — usage: workspace-delete.sh <workspace>"
INPUT=${1%/}
[ -n "$INPUT" ] || die "the workspace path is empty"
NAME=$(basename -- "$INPUT")

# Derive ownership from lexical parents before canonicalization. A matching
# suffix proves only spelling: the destructive target must belong to the exact
# physical .superpowers/bwr ground of one Git checkout root.
BWR_INPUT=$(dirname -- "$INPUT")
SUPER_INPUT=$(dirname -- "$BWR_INPUT")
CHECKOUT_INPUT=$(dirname -- "$SUPER_INPUT")
[ "$(basename -- "$BWR_INPUT")" = bwr ] \
    && [ "$(basename -- "$SUPER_INPUT")" = .superpowers ] \
    || die "refused: $INPUT is not a workspace root — its lexical parent must be
<checkout>/.superpowers/bwr. Nothing was followed or deleted."

for component in "$SUPER_INPUT" "$BWR_INPUT"; do
    [ ! -L "$component" ] \
        || die "refused: the workspace deletion ground contains a symlink:
  $component
Nothing was followed or deleted."
    [ -d "$component" ] \
        || die "refused: the workspace deletion ground is not a real directory:
  $component
Nothing was followed or deleted."
done

CHECKOUT=$(cd "$CHECKOUT_INPUT" 2>/dev/null && pwd -P) \
    || die "no such checkout directory: $CHECKOUT_INPUT"
TOP=$(git -C "$CHECKOUT" rev-parse --show-toplevel 2>/dev/null) \
    || die "refused: $CHECKOUT is not a Git checkout. Nothing was followed or deleted."
TOP=$(cd "$TOP" && pwd -P)
[ "$TOP" = "$CHECKOUT" ] \
    || die "refused: the deletion ground is not at its Git checkout root:
  checkout root  $TOP
  derived root   $CHECKOUT
Nothing was followed or deleted."

PARENT=$(cd "$BWR_INPUT" && pwd -P)
EXPECTED="$CHECKOUT/.superpowers/bwr"
[ "$PARENT" = "$EXPECTED" ] \
    || die "refused: the deletion ground resolves outside the exact checkout-local path:
  written   $BWR_INPUT
  physical  $PARENT
  expected  $EXPECTED
Nothing was followed or deleted."

# The final name and its one deletion tombstone are the only accepted names.
# The disposable checkouts live in bwr/tmp/, and a .partial belongs only to
# workspace-init. Neither can enter this destructive route.
if [[ $NAME =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    FINAL_NAME=$NAME
    INPUT_KIND=final
elif [[ $NAME =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(-[a-z0-9]+)*\.deleting$ ]]; then
    FINAL_NAME=${NAME%.deleting}
    INPUT_KIND=tombstone
else
    die "refused: \`$NAME\` is not a run workspace or its deletion tombstone.
A workspace reads <date>-<feature>. Only the exact sibling <date>-<feature>.deleting
can resume its deletion. \`tmp\`, a \`.partial\`, and every other name are refused."
fi

WORKSPACE="$PARENT/$FINAL_NAME"
TOMBSTONE="$WORKSPACE.deleting"

workspace_exists=false
tombstone_exists=false
if [ -e "$WORKSPACE" ] || [ -L "$WORKSPACE" ]; then workspace_exists=true; fi
if [ -e "$TOMBSTONE" ] || [ -L "$TOMBSTONE" ]; then tombstone_exists=true; fi

if $workspace_exists && $tombstone_exists; then
    die "refused: both the final workspace and its deletion tombstone exist:
  $WORKSPACE
  $TOMBSTONE
Nothing was deleted. A human must resolve this collision."
fi

if [ "$INPUT_KIND" = tombstone ] && ! $tombstone_exists; then
    die "no such deletion tombstone: $TOMBSTONE"
fi
if [ "$INPUT_KIND" = final ] && ! $workspace_exists && ! $tombstone_exists; then
    die "no workspace or deletion tombstone exists for: $WORKSPACE"
fi

if $workspace_exists; then
    [ -d "$WORKSPACE" ] && [ ! -L "$WORKSPACE" ] \
        || die "refused: the workspace is not a real directory: $WORKSPACE"
fi
if $tombstone_exists; then
    [ -d "$TOMBSTONE" ] && [ ! -L "$TOMBSTONE" ] \
        || die "refused: the deletion tombstone is not a real directory: $TOMBSTONE"
fi

SELF=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
case "$SELF" in
    "$WORKSPACE"|"$WORKSPACE"/*|"$TOMBSTONE"|"$TOMBSTONE"/*)
        die "this copy lives inside the workspace it was asked to delete — run the skill's own" ;;
esac

# The rename is the durable operation boundary. It removes the adoptable final
# name atomically before any file inside can disappear. A killed find leaves a
# non-adoptable tombstone that either accepted input form can finish.
if $workspace_exists; then
    mv -T -- "$WORKSPACE" "$TOMBSTONE"
fi

# -delete walks depth-first, so a directory goes only once its contents are
# gone: there is no -r to forget, and no `rm -rf` for a permission setup to
# refuse.
find "$TOMBSTONE" -delete
printf 'DELETED %s\n' "$WORKSPACE"
