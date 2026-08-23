#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$HERE/correction_product_authority.py" "$@"
