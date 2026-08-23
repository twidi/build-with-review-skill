#!/usr/bin/env bash
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$HERE/correction_round_baseline.py" "$@"
