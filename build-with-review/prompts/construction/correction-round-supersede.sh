#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

[ $# -eq 5 ] || {
    printf '%s\n' '**correction-round-supersede ERROR** · usage: correction-round-supersede.sh <built> <round> <allocation proof> <sublot|reclassify> "<durable reason>"' >&2
    exit 1
}

exec python3 "$HERE/correction_round_supersede.py" "$@"
