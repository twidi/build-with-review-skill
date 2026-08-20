#!/usr/bin/env bash
# Publish one complete, human-validated gate command list. The final gate leaf
# changes through one same-directory atomic rename; an interrupted write can
# leave only a non-authoritative temporary file.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
EXPECTED_REPO=$(cd "$WORKSPACE/../../.." && pwd -P)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }

USAGE='usage: gate-write.sh create -- "<command>"...  |  gate-write.sh replace <current gate blob SHA> -- "<command>"...'
[ $# -ge 3 ] || die "$USAGE"
MODE=$1
shift
EXPECTED=
case "$MODE" in
    create) ;;
    replace)
        [ $# -ge 3 ] || die "$USAGE"
        EXPECTED=$1
        shift
        [[ $EXPECTED =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]] \
            || die "the current gate blob SHA must be 40 or 64 lowercase hexadecimal characters"
        ;;
    *) die "$USAGE" ;;
esac
[ "$1" = -- ] || die "$USAGE"
shift
[ $# -gt 0 ] || die "the complete gate list must contain at least one command"

cd "$EXPECTED_REPO"
REPO=$(git rev-parse --show-toplevel 2>/dev/null) \
    || die "$EXPECTED_REPO is not a Git repository"
REPO=$(cd "$REPO" && pwd -P)
[ "$REPO" = "$EXPECTED_REPO" ] \
    || die "the workspace does not belong to the exact repository root: expected $EXPECTED_REPO, got $REPO"
SUPER="$REPO/.superpowers"
GROUND="$SUPER/bwr"
GATE="$GROUND/gate.md"

validate_ground() {
    local path
    for path in "$SUPER" "$GROUND"; do
        [ -d "$path" ] && [ ! -L "$path" ] \
            || die "$path must be one real checkout-local directory. Nothing was written."
        [ "$(cd "$path" && pwd -P)" = "$path" ] \
            || die "$path resolves outside its checkout-local location. Nothing was written."
    done
}

validate_target() {
    validate_ground
    case "$MODE" in
        create)
            [ ! -e "$GATE" ] && [ ! -L "$GATE" ] \
                || die "$GATE is no longer absent. Nothing was replaced or followed."
            ;;
        replace)
            [ -f "$GATE" ] && [ ! -L "$GATE" ] \
                || die "$GATE is not one real regular file. Nothing was replaced or followed."
            ACTUAL=$(git hash-object "$GATE")
            [ "$ACTUAL" = "$EXPECTED" ] \
                || die "gate.md changed since the human validated its replacement: expected $EXPECTED, got $ACTUAL. Nothing was replaced."
            ;;
    esac
}

declare -A SEEN=()
for command in "$@"; do
    [ -n "$command" ] || die "a gate command is empty"
    case "$command" in
        *$'\n'*|*$'\r'*) die "one gate command contains a line break; each argument must be one complete command" ;;
    esac
    [ -z "${SEEN[$command]+x}" ] || die "the complete gate list repeats this command: $command"
    SEEN[$command]=1
done

validate_target
umask 077
TMP=$(mktemp "$GROUND/.gate.md.tmp.XXXXXX") \
    || die "could not create the same-directory gate temporary"
cleanup() {
    if [ -n "${TMP:-}" ] && { [ -e "$TMP" ] || [ -L "$TMP" ]; }; then
        rm -f -- "$TMP"
    fi
}
trap cleanup EXIT HUP INT TERM
printf '%s\n' "$@" > "$TMP"
[ -f "$TMP" ] && [ ! -L "$TMP" ] \
    || die "the prepared gate is not one real regular temporary file"
[ "$(wc -l < "$TMP")" -eq "$#" ] \
    || die "the prepared gate does not contain the complete command list"
PREPARED=$(git hash-object "$TMP")

# Recheck immediately before publication. For creation, --no-clobber prevents
# replacing an occupant that appeared after the check. For growth, only this
# helper is a valid writer and the expected blob authenticates its input state.
validate_target
if [ "$MODE" = create ]; then
    mv -nT -- "$TMP" "$GATE"
    [ ! -e "$TMP" ] \
        || die "$GATE appeared before publication. The prepared temporary remains non-authoritative and will be removed."
else
    mv -T -- "$TMP" "$GATE"
fi
TMP=
[ -f "$GATE" ] && [ ! -L "$GATE" ] \
    || die "the atomic publication did not leave one real gate file"
[ "$(git hash-object "$GATE")" = "$PREPARED" ] \
    || die "the published gate bytes differ from the prepared complete list"
printf 'GATE %s\nCOMMANDS %s\n' "$PREPARED" "$#"
