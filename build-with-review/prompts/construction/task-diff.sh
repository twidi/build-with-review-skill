#!/usr/bin/env bash
# What one past task actually changed.
#
# The plan says what a task had to achieve; this says what it did. When the two
# disagree, the code is right — the plan is dated, not maintained.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"

[ $# -eq 2 ] || die "2 arguments expected, $# given — usage: task-diff.sh <lot> <task N>"
LOT=$1 N=$2
[[ $LOT =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] || die "the lot must read lot-<N> or lot-<N>.<M> — positive integers, no leading zeros — got \`$LOT\`"
[[ $N =~ ^[1-9][0-9]*$ ]] || die "the task number must be a positive integer without leading zeros, got \`$N\` — and there is no task 0 to diff: task-0 is the lot's starting point, not a task"

RUN="refs/bwr/$(basename "$WORKSPACE")"   # this run's own ref namespace — see vocabulary.md
REF="$RUN/$LOT/task-$N"

cd "$REPO"
git rev-parse --verify --quiet "$REF" >/dev/null || die "$REF does not exist"

# One task, one commit: the ref IS the task's commit, and its diff against its
# own parent is exactly what the task changed. A range from task-<N-1> would
# also sweep in whatever the controller validly committed in between — an
# amendment landing mid-lot, a rewind re-landing what it removed — and hand it
# to the reader as if task N had made it.
git diff "$REF^" "$REF"
