#!/usr/bin/env bash
# Authenticates and copies workflow-owned plans and amendments between the
# frozen workspace and the repository. No caller reads a workspace document or
# writes a repository document before this shared physical-path boundary.
set -euo pipefail
export GIT_LITERAL_PATHSPECS=1

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
WORKSPACE=$(cd "$HERE/../.." && pwd -P)
REPO=$(cd "$WORKSPACE/../../.." && pwd -P)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }

[ $# -ge 2 ] || die "usage:
  document-copy.sh source <workspace-relative-source>
  document-copy.sh copy <workspace-relative-source> <repo-relative-destination> <replace|existing>
  document-copy.sh finish <workspace-relative-source> <repo-relative-destination> <replace|existing>"
COMMAND=$1
COPY_MARKER="$WORKSPACE/document-copy-in-progress"

# The helper itself re-establishes both physical roots. A suffix is not
# ownership: the workspace must sit in the exact real bwr ground of the exact
# Git toplevel, and none of those ground components may be an alias.
TOP=$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null) \
    || die "$REPO is not a Git checkout"
TOP=$(cd "$TOP" && pwd -P)
[ "$TOP" = "$REPO" ] \
    || die "the derived repository $REPO is not its exact Git toplevel $TOP"
for component in "$REPO/.superpowers" "$REPO/.superpowers/bwr" "$WORKSPACE"; do
    [ ! -L "$component" ] \
        || die "the document ground contains a symlink: $component. Nothing was read or written."
    [ -d "$component" ] \
        || die "the document ground is not a real directory: $component. Nothing was read or written."
done
WORKSPACE_PARENT=$(cd "$(dirname "$WORKSPACE")" && pwd -P)
[ "$WORKSPACE_PARENT" = "$REPO/.superpowers/bwr" ] \
    || die "the workspace is outside the exact checkout-local bwr ground. Nothing was read or written."

parse_relative() {
    local value=$1
    local label=$2
    [ -n "$value" ] && [[ $value != /* ]] && [[ $value != */ ]] && [[ $value != *//* ]] \
        || die "$label must be one non-empty relative path without empty components"
    [[ $value != *$'\n'* && $value != *$'\r'* ]] \
        || die "$label contains a line break"
    IFS='/' read -r -a PARTS <<< "$value"
    local part
    for part in "${PARTS[@]}"; do
        [ -n "$part" ] && [ "$part" != . ] && [ "$part" != .. ] \
            || die "$label contains a forbidden path component: $value"
    done
}

validate_source() {
    local relative=$1
    parse_relative "$relative" "the workspace source"
    local cursor=$WORKSPACE
    local last=$((${#PARTS[@]} - 1))
    local i path
    for i in "${!PARTS[@]}"; do
        path="$cursor/${PARTS[$i]}"
        [ ! -L "$path" ] \
            || die "the workspace source traverses a symlink: $path. Nothing was read or written."
        if [ "$i" -eq "$last" ]; then
            [ -f "$path" ] \
                || die "the workspace source is not one real regular file: $path"
        else
            [ -d "$path" ] \
                || die "the workspace source parent is not one real directory: $path"
        fi
        cursor=$path
    done
    SOURCE_PATH=$cursor
    SOURCE_PARENT=$(cd "$(dirname "$SOURCE_PATH")" && pwd -P)
    case "$SOURCE_PARENT/" in
        "$WORKSPACE/"*) ;;
        *) die "the workspace source resolves outside $WORKSPACE. Nothing was read or written." ;;
    esac
}

# Validate every existing repository parent before creating any missing one.
# Creation then proceeds one component at a time, with the same real-directory
# check after each mkdir. No `mkdir -p` follows an existing alias.
prepare_destination_parent() {
    local relative=$1
    local policy=$2
    [ "$policy" = create ] || [ "$policy" = existing ] \
        || die "internal destination-parent policy must be create or existing"
    parse_relative "$relative" "the repository destination"
    DEST_PARTS=("${PARTS[@]}")
    local last_index=$((${#DEST_PARTS[@]} - 1))
    DEST_LEAF=${DEST_PARTS[$last_index]}
    unset "DEST_PARTS[$last_index]"
    local cursor=$REPO
    local part path
    for part in "${DEST_PARTS[@]}"; do
        path="$cursor/$part"
        if [ -e "$path" ] || [ -L "$path" ]; then
            [ ! -L "$path" ] \
                || die "the repository destination traverses a symlink: $path. Nothing was written."
            [ -d "$path" ] \
                || die "the repository destination parent is not a real directory: $path"
        elif [ "$policy" = existing ]; then
            die "the repository destination parent disappeared: $path. Nothing was written."
        fi
        cursor=$path
    done
    cursor=$REPO
    for part in "${DEST_PARTS[@]}"; do
        path="$cursor/$part"
        if [ ! -e "$path" ] && [ "$policy" = create ]; then
            mkdir -- "$path"
        fi
        [ ! -L "$path" ] && [ -d "$path" ] \
            || die "the repository destination parent changed identity: $path. Nothing was copied."
        cursor=$path
    done
    DEST_PARENT=$(cd "$cursor" && pwd -P)
    [ "$DEST_PARENT" = "$cursor" ] \
        || die "the repository destination parent resolves through an alias: $cursor"
    DEST_PATH="$DEST_PARENT/$DEST_LEAF"
}

destination_is_tracked_regular() {
    local line mode type path
    line=$(git -C "$REPO" ls-tree HEAD -- "$DEST_REL")
    [ -n "$line" ] || return 1
    mode=${line%% *}
    line=${line#* }
    type=${line%% *}
    path=${line#*$'\t'}
    { [ "$mode" = 100644 ] || [ "$mode" = 100755 ]; } \
        && [ "$type" = blob ] && [ "$path" = "$DEST_REL" ]
}

source_identity() {
    git -C "$REPO" hash-object --no-filters -- "$SOURCE_PATH"
}

read_copy_marker() {
    [ ! -L "$COPY_MARKER" ] && [ -f "$COPY_MARKER" ] \
        || die "the document-copy marker is not one real regular file: $COPY_MARKER"
    local lines=()
    mapfile -t lines < "$COPY_MARKER"
    [ "${#lines[@]}" -eq 4 ] \
        || die "the document-copy marker is incomplete. Nothing was read or written."
    [[ ${lines[0]} == source\ * && ${lines[1]} == destination\ * \
       && ${lines[2]} == mode\ * && ${lines[3]} == source-id\ * ]] \
        || die "the document-copy marker has an invalid shape. Nothing was read or written."
    M_SOURCE=${lines[0]#source }
    M_DEST=${lines[1]#destination }
    M_MODE=${lines[2]#mode }
    M_SOURCE_ID=${lines[3]#source-id }
}

require_matching_copy_marker() {
    read_copy_marker
    [ "$M_SOURCE" = "$SOURCE_REL" ] && [ "$M_DEST" = "$DEST_REL" ] \
        && [ "$M_MODE" = "$MODE" ] && [ "$M_SOURCE_ID" = "$SOURCE_ID" ] \
        || die "another document copy is unfinished:
  source       $M_SOURCE
  destination  $M_DEST
  mode         $M_MODE
Its exact call must finish first. Nothing was read or written."
}

publish_copy_marker() {
    local temp="$COPY_MARKER.tmp"
    if [ -e "$temp" ] || [ -L "$temp" ]; then
        [ ! -L "$temp" ] && [ -f "$temp" ] \
            || die "the document-copy marker temporary is not one real file: $temp"
    fi
    {
        printf 'source %s\n' "$SOURCE_REL"
        printf 'destination %s\n' "$DEST_REL"
        printf 'mode %s\n' "$MODE"
        printf 'source-id %s\n' "$SOURCE_ID"
    } > "$temp"
    mv -T -- "$temp" "$COPY_MARKER"
}

validate_destination_leaf() {
    local mode=$1
    if [ -e "$DEST_PATH" ] || [ -L "$DEST_PATH" ]; then
        [ ! -L "$DEST_PATH" ] \
            || die "the repository destination is a symlink: $DEST_PATH. Nothing was copied."
        [ -f "$DEST_PATH" ] \
            || die "the repository destination is not a real regular file: $DEST_PATH"
    else
        [ "$mode" = replace ] \
            || die "the repository destination does not exist as the required real file: $DEST_PATH"
    fi
}

case "$COMMAND" in
    source)
        [ $# -eq 2 ] || die "source expects 1 argument, $(($# - 1)) given"
        validate_source "$2"
        printf '%s\n' "$SOURCE_PATH"
        ;;
    copy)
        [ $# -eq 4 ] || die "copy expects 3 arguments, $(($# - 1)) given"
        SOURCE_REL=$2 DEST_REL=$3 MODE=$4
        [ "$MODE" = replace ] || [ "$MODE" = existing ] \
            || die "copy mode must be replace or existing, got: $MODE"
        validate_source "$SOURCE_REL"
        SOURCE_ID=$(source_identity)
        PARENT_POLICY=create
        [ "$MODE" = replace ] || PARENT_POLICY=existing
        prepare_destination_parent "$DEST_REL" "$PARENT_POLICY"
        validate_destination_leaf "$MODE"

        TEMP_PATH="$DEST_PATH.bwr-copy-in-progress"
        TEMP_EXISTS=
        if [ -e "$TEMP_PATH" ] || [ -L "$TEMP_PATH" ]; then
            [ ! -L "$TEMP_PATH" ] && [ -f "$TEMP_PATH" ] \
                || die "the document-copy temporary is not a real regular file: $TEMP_PATH"
            TEMP_EXISTS=1
        fi

        # An existing real file is not automatically workflow-owned. A fresh
        # operation accepts it only when HEAD tracks this exact path as a
        # regular file. An untracked leaf is accepted only through this exact
        # operation's durable copy marker, which survives the rename-to-stage
        # crash window. The absent leaf is the initial-copy case.
        if [ -e "$COPY_MARKER" ] || [ -L "$COPY_MARKER" ]; then
            require_matching_copy_marker
        else
            [ -z "$TEMP_EXISTS" ] \
                || die "an unowned document-copy temporary already exists:
  $TEMP_PATH
Nothing was written. Take this collision to the human."
            if [ -e "$DEST_PATH" ]; then
                destination_is_tracked_regular \
                    || die "the existing repository destination is not a tracked regular workflow file:
  $DEST_PATH
Nothing was written. Take this collision to the human."
            fi
            publish_copy_marker
        fi

        # The deterministic same-directory temporary belongs only to this
        # exact generated document. A real leftover is a killed copy and can
        # be rewritten. An alias or any other occupant is refused. The final
        # rename is atomic, so a kill never exposes a partial target.
        if [ -n "$TEMP_EXISTS" ]; then
            # The matching marker above proves this exact real leaf belongs to
            # the interrupted copy. Unlink it before recreation, so even a
            # hard-linked inode cannot turn the next write into an external
            # mutation.
            find "$TEMP_PATH" -delete
        fi
        (set -o noclobber; : > "$TEMP_PATH") 2>/dev/null \
            || die "could not create the document-copy temporary without following an alias: $TEMP_PATH"
        cp -- "$SOURCE_PATH" "$TEMP_PATH"
        cmp -s -- "$SOURCE_PATH" "$TEMP_PATH" \
            || die "the copied temporary does not equal the authenticated workspace source"

        # Recheck every filesystem identity immediately before the rename. A
        # retry repeats these checks even when a caller's commit marker exists.
        validate_source "$SOURCE_REL"
        [ "$(source_identity)" = "$SOURCE_ID" ] \
            || die "the workspace source changed during its copy. Nothing was renamed."
        prepare_destination_parent "$DEST_REL" existing
        validate_destination_leaf "$MODE"
        [ ! -L "$TEMP_PATH" ] && [ -f "$TEMP_PATH" ] \
            || die "the document-copy temporary changed identity before rename: $TEMP_PATH"
        cmp -s -- "$SOURCE_PATH" "$TEMP_PATH" \
            || die "the workspace source changed during its copy. Nothing was renamed."
        mv -T -- "$TEMP_PATH" "$DEST_PATH"
        [ ! -L "$DEST_PATH" ] && [ -f "$DEST_PATH" ] \
            || die "the repository destination is not a real regular file after rename: $DEST_PATH"
        ;;
    finish)
        [ $# -eq 4 ] || die "finish expects 3 arguments, $(($# - 1)) given"
        SOURCE_REL=$2 DEST_REL=$3 MODE=$4
        [ "$MODE" = replace ] || [ "$MODE" = existing ] \
            || die "finish mode must be replace or existing, got: $MODE"
        validate_source "$SOURCE_REL"
        SOURCE_ID=$(source_identity)
        require_matching_copy_marker
        prepare_destination_parent "$DEST_REL" existing
        # Whatever the opening mode, a finish can consume ownership only when
        # the atomic rename produced one real destination file.
        validate_destination_leaf existing
        [ ! -L "$COPY_MARKER" ] && [ -f "$COPY_MARKER" ] \
            || die "the document-copy marker changed identity before its removal"
        rm -f -- "$COPY_MARKER"
        ;;
    *)
        die "unknown command $COMMAND — expected source or copy"
        ;;
esac
