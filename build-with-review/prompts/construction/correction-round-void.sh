#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

[ $# -eq 1 ] || {
    printf '%s\n' '**correction-round-void ERROR** · usage: correction-round-void.sh <built>' >&2
    exit 1
}

exec python3 "$HERE/correction_round_void.py" "$@"
