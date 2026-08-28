#!/usr/bin/env bash
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$#" -eq 2 ] || { [ "$#" -eq 3 ] && [[ "$3" == *:* ]]; }; then
    exec python3 "$HERE/correction_round_escalate.py" "$@"
fi
exec python3 "$HERE/correction_round_return.py" sublot "$@"
