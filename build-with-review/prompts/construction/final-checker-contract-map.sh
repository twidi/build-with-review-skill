#!/usr/bin/env bash
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$HERE/final_checker_contract_map.py" "$@"
