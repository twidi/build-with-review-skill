#!/usr/bin/env bash
# Read one exact frozen code-review manifest without using a potentially
# truncated all-files diff.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"

HELPER="$WORKSPACE/prompts/construction/construction_review.py"
case ${1:-} in
    count)
        [ $# -eq 2 ] || die "usage: task-changes.sh count <manifest-relative-path>"
        python3 "$HELPER" count "$2"
        ;;
    item)
        [ $# -eq 3 ] || die "usage: task-changes.sh item <manifest-relative-path> <item N>"
        python3 "$HELPER" item "$2" "$3"
        ;;
    previous-count)
        [ $# -eq 2 ] || die "usage: task-changes.sh previous-count <manifest-relative-path>"
        python3 "$HELPER" previous-count "$2"
        ;;
    previous-item)
        [ $# -eq 3 ] || die "usage: task-changes.sh previous-item <manifest-relative-path> <finding N>"
        python3 "$HELPER" previous-item "$2" "$3"
        ;;
    read)
        [ $# -eq 6 ] || die "usage: task-changes.sh read <manifest> <item N> <diff|file> <byte offset> <byte count up to 65536>"
        python3 "$HELPER" read "$2" "$3" "$4" "$5" "$6"
        ;;
    contract|design)
        [ $# -eq 2 ] || die "usage: task-changes.sh <contract|design> <manifest-relative-path>"
        python3 "$HELPER" read-plan "$2" "$1"
        ;;
    *)
        die "usage: task-changes.sh <count|item|previous-count|previous-item|read|contract|design> ..."
        ;;
esac
