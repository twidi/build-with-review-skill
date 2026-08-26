#!/usr/bin/env bash
# Restore the last authorised spec after a bound in-place commit breaches an
# active product answer. The bad commit stays in history as evidence; one new
# corrective commit restores only the spec path, and moves a still-live
# attempt's mark with HEAD.
set -euo pipefail
export GIT_LITERAL_PATHSPECS=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
REPO=$(cd "$WORKSPACE/../../.." && pwd)
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }
[ -e "$REPO/.git" ] || die "$REPO is not a git repository"
source "$WORKSPACE/prompts/common/attempt-closer.sh"
source "$WORKSPACE/prompts/common/bare-stop.sh"

[ $# -eq 2 ] || die "2 arguments expected, $# given — usage:
  spec-breach-recover.sh <breach-number> \"<corrective commit subject>\"
Quote the subject, it contains spaces. The breach must already have one
spec.breach.opened line."
BREACH=$1 SUBJECT=$2
[[ $BREACH =~ ^[1-9][0-9]*$ ]] \
    || die "the breach number must be a positive integer without leading zeros, got \`$BREACH\`"
[ -n "$SUBJECT" ] || die "the corrective commit subject is empty"

JOURNAL="$WORKSPACE/progress.jsonl"
PENDING="$WORKSPACE/spec-breach-recovery-in-progress"
[ -f "$JOURNAL" ] || die "the run has no journal, so breach $BREACH cannot be authenticated"

# Read only durable identities. The controller can describe a breach, but the
# script trusts the journal and the bad commit. NUL separators preserve paths
# carried in event text, although this parser deliberately returns identifiers
# only. Exactly one opening and at most one correction may own the ordinal.
mapfile -d '' -t STATE < <(python3 - "$JOURNAL" "$BREACH" <<'PY'
import json
import re
import sys

journal, wanted = sys.argv[1], int(sys.argv[2])
notes = []
with open(journal, encoding="utf-8") as source:
    for number, raw in enumerate(source, 1):
        try:
            entry = json.loads(raw)
        except ValueError as exc:
            raise SystemExit(f"journal line {number} is not valid JSON: {exc}")
        if entry.get("event") == "note":
            notes.append(entry)

opened = [entry for entry in notes
          if entry.get("kind") == "spec.breach.opened"
          and (entry.get("data") or {}).get("breach") == wanted]
if len(opened) != 1:
    raise SystemExit(f"expected exactly one spec.breach.opened for breach {wanted}, found {len(opened)}")
data = opened[0].get("data") or {}
required = ("owner", "answer", "bad_op", "bad_sha", "authorized_sha", "erased")
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit("breach opening lacks: " + ", ".join(missing))
owner = data["owner"]
answer = data["answer"]
bad_op = data["bad_op"]
bad_sha = data["bad_sha"]
authorised = data["authorized_sha"]
mark_lot = data.get("mark_lot") or "-"
if not re.fullmatch(r"(?:R[1-9][0-9]*|B[1-9][0-9]*)", owner):
    raise SystemExit(f"invalid breach owner {owner!r}")
if owner.startswith("R"):
    if answer != owner:
        raise SystemExit("a ruling-owned breach must use that ruling as its answer identity")
else:
    if not re.fullmatch(re.escape(owner) + r"/D[1-9][0-9]*", answer):
        raise SystemExit("a batch-owned breach answer must read B<N>/D<M> under its owner")
if not isinstance(data["erased"], list) or not data["erased"]:
    raise SystemExit("the breach must name at least one erased authority")
if not all(isinstance(item, str) and item for item in data["erased"]):
    raise SystemExit("every erased authority must be a non-empty identity")
if not re.fullmatch(r"[0-9a-f]{40,64}", bad_sha) or not re.fullmatch(r"[0-9a-f]{40,64}", authorised):
    raise SystemExit("bad_sha and authorized_sha must be full hexadecimal commit IDs")
if mark_lot != "-" and not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", mark_lot):
    raise SystemExit(f"invalid mark_lot {mark_lot!r}")

bound = []
for entry in notes:
    if entry.get("kind") != "spec.committed":
        continue
    candidate = entry.get("data") or {}
    if candidate.get("op") != bad_op:
        continue
    if owner.startswith("R"):
        matches = candidate.get("ruling") == owner
    else:
        batch, decision = answer.split("/", 1)
        matches = candidate.get("batch") == int(batch[1:]) and candidate.get("decision") == decision
    if matches:
        bound.append(candidate)
if len(bound) != 1:
    raise SystemExit(f"expected exactly one matching bound spec.committed, found {len(bound)}")
commit = bound[0]
if commit.get("sha") != bad_sha or commit.get("parent") != authorised:
    raise SystemExit("the breach opening disagrees with its bound spec.committed SHA or parent")
if (commit.get("mark_lot") or "-") != mark_lot:
    raise SystemExit("the breach opening disagrees with its bound spec.committed mark_lot")

corrected = [entry.get("data") or {} for entry in notes
             if entry.get("kind") == "spec.breach.corrected"
             and (entry.get("data") or {}).get("breach") == wanted]
if len(corrected) > 1:
    raise SystemExit(f"more than one spec.breach.corrected owns breach {wanted}")
corrected_sha = repair_op = mark_moved = ""
if corrected:
    correction = corrected[0]
    expected = {
        "owner": owner,
        "answer": answer,
        "bad_op": bad_op,
        "bad_sha": bad_sha,
        "authorized_sha": authorised,
    }
    if any(correction.get(key) != value for key, value in expected.items()):
        raise SystemExit("spec.breach.corrected disagrees with its opening")
    if (correction.get("mark_lot") or "-") != mark_lot:
        raise SystemExit("spec.breach.corrected disagrees with the opening's mark_lot")
    corrected_sha = correction.get("sha") or ""
    repair_op = correction.get("op") or ""
    mark_moved = "true" if correction.get("mark_moved") is True else "false"
    if not re.fullmatch(r"[0-9a-f]{40,64}", corrected_sha):
        raise SystemExit("spec.breach.corrected lacks a full corrective SHA")
    if not repair_op:
        raise SystemExit("spec.breach.corrected lacks its operation identity")

for value in (owner, answer, bad_op, bad_sha, authorised, mark_lot,
              corrected_sha, repair_op, mark_moved):
    sys.stdout.buffer.write(str(value).encode() + b"\0")
PY
)
[ ${#STATE[@]} -eq 9 ] || die "the breach state is incomplete or unreadable"
OWNER=${STATE[0]} ANSWER=${STATE[1]} BAD_OP=${STATE[2]} BAD_SHA=${STATE[3]}
AUTHORIZED_SHA=${STATE[4]} MARK_LOT=${STATE[5]} CORRECTED_SHA=${STATE[6]}
RECORDED_REPAIR_OP=${STATE[7]} RECORDED_MARK_MOVED=${STATE[8]}

cd "$REPO"
[ "$(git rev-parse "$BAD_SHA^")" = "$AUTHORIZED_SHA" ] \
    || die "the recorded authorised state is not the bad commit's parent"

mapfile -d '' -t CHANGED < <(git diff-tree --no-commit-id --name-only -r -z "$AUTHORIZED_SHA" "$BAD_SHA")
[ ${#CHANGED[@]} -eq 1 ] \
    || die "the offending bound commit changes ${#CHANGED[@]} paths, not one spec path"
SPEC=${CHANGED[0]}
git cat-file -e "$AUTHORIZED_SHA:$SPEC" 2>/dev/null \
    || die "the authorised parent does not contain the spec path changed by the bad commit"
AUTH_BLOB=$(git rev-parse "$AUTHORIZED_SHA:$SPEC")
BAD_BLOB=$(git rev-parse "$BAD_SHA:$SPEC")
[ "$AUTH_BLOB" != "$BAD_BLOB" ] \
    || die "the bad commit did not change the spec content"

validate_correction() {
    local sha=$1
    [ "$(git rev-parse "$sha^")" = "$BAD_SHA" ] \
        || die "the corrective commit is not a direct child of the preserved bad commit"
    mapfile -d '' -t corrected_paths < <(git diff-tree --no-commit-id --name-only -r -z "$BAD_SHA" "$sha")
    [ ${#corrected_paths[@]} -eq 1 ] && [ "${corrected_paths[0]}" = "$SPEC" ] \
        || die "the corrective commit changes something other than the exact spec path"
    [ "$(git rev-parse "$sha:$SPEC")" = "$AUTH_BLOB" ] \
        || die "the corrective commit does not restore the authorised spec content"
}

# A recorded correction owns the result. Remove only its orphan marker, then
# validate the immutable history. The corrective commit never repeats.
if [ -n "$CORRECTED_SHA" ]; then
    validate_correction "$CORRECTED_SHA"
    if [ -f "$PENDING" ]; then
        mapfile -t DONE_MARKER < "$PENDING"
        [ ${#DONE_MARKER[@]} -eq 9 ] \
            || die "the recovery marker is unreadable; do not remove it by hand"
        [ "${DONE_MARKER[0]}" = "$BREACH" ] && [ "${DONE_MARKER[7]}" = "$RECORDED_REPAIR_OP" ] \
            || die "the recovery marker belongs to another operation"
        rm -f "$PENDING"
    fi
    printf 'ALREADY CORRECTED breach %s\nSHA %s\nMARK %s\n' \
        "$BREACH" "$CORRECTED_SHA" "$RECORDED_MARK_MOVED"
    exit 0
fi

SUBJECT_ID=$(printf '%q' "$SUBJECT")
REPAIR_OP=
# A fresh recovery is not an attempt closer. A result ref can exist while the
# owning success, failure or stop call still owes its authenticated tail. Refuse
# before publishing this recovery's marker; a retry with a marker keeps owning
# the recovery state it already opened.
if [ ! -f "$PENDING" ]; then
    controller_physical_admission_acquire "$WORKSPACE" \
        || die "$CONTROLLER_PHYSICAL_ADMISSION_ERROR"
    if ! controller_operation_refuse_pending "$WORKSPACE"; then
        die "$CONTROLLER_OPERATION_ERROR. This fresh breach recovery published no marker."
    fi
    if ! bare_stop_refuse_unfinished "$WORKSPACE"; then
        die "$BARE_STOP_ERROR. This fresh breach recovery cannot pass it. Nothing was
restored, committed, staged or marked."
    fi
    INFLIGHT="$WORKSPACE/attempt-in-flight"
    if [ -f "$INFLIGHT" ]; then
        F_LOT=; F_N=; F_K=
        read -r F_LOT F_N F_K < "$INFLIGHT" || true
        RUNS="refs/bwr/$(basename "$WORKSPACE")"
        if SHA=$(git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N"); then
            die "attempt-in-flight still owns the success tail for $F_LOT task $F_N
attempt $F_K. Recover its gate with gate-check.sh find-task $F_LOT $F_N $F_K $SHA,
then rerun attempt-succeeded.sh $F_LOT $F_N $SHA <that op>. This fresh breach recovery
cannot pass that closer. Nothing was restored, committed, staged or marked."
        elif git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N-try-$F_K" >/dev/null; then
            ROUTE=$(attempt_closer_route "$INFLIGHT" || true)
            die "attempt-in-flight still owns the failure or stop tail for $F_LOT task $F_N
attempt $F_K. $ROUTE This
fresh breach recovery cannot pass that closer. Nothing was restored, committed, staged or marked."
        fi
    fi
fi
if [ -f "$PENDING" ]; then
    mapfile -t MARKER < "$PENDING"
    [ ${#MARKER[@]} -eq 9 ] \
        || die "the recovery marker is unreadable; do not remove it by hand"
    [ "${MARKER[0]}" = "$BREACH" ] \
        || die "an unfinished recovery for breach ${MARKER[0]} owns the workspace"
    [ "${MARKER[1]}" = "$OWNER" ] && [ "${MARKER[2]}" = "$ANSWER" ] \
        && [ "${MARKER[3]}" = "$BAD_OP" ] && [ "${MARKER[4]}" = "$BAD_SHA" ] \
        && [ "${MARKER[5]}" = "$AUTHORIZED_SHA" ] && [ "${MARKER[6]}" = "$MARK_LOT" ] \
        || die "the recovery marker disagrees with spec.breach.opened"
    [ "${MARKER[8]}" = "$SUBJECT_ID" ] \
        || die "the corrective subject differs from the interrupted recovery"
    REPAIR_OP=${MARKER[7]}
else
    [ "$(git rev-parse HEAD)" = "$BAD_SHA" ] \
        || die "HEAD is not the preserved bad commit; nothing was changed"
    git diff --cached --quiet "$BAD_SHA" -- "$SPEC" \
        || die "the spec has staged changes outside this recovery; nothing was changed"
    [ "$(git hash-object -- "$SPEC")" = "$BAD_BLOB" ] \
        || die "the spec has uncommitted changes outside this recovery; nothing was changed"
    REPAIR_OP="$(date +%s%N).$$"
    {
        printf '%s\n' "$BREACH" "$OWNER" "$ANSWER" "$BAD_OP" "$BAD_SHA"
        printf '%s\n' "$AUTHORIZED_SHA" "$MARK_LOT" "$REPAIR_OP" "$SUBJECT_ID"
    } > "$PENDING.tmp"
    mv "$PENDING.tmp" "$PENDING"
    controller_physical_admission_release
fi

# Authenticate the current attempt. A live attempt that existed at the bad
# commit must move with the corrective HEAD. A closed attempt needs no move;
# no later attempt may start while this higher-precedence recovery is open.
INFLIGHT="$WORKSPACE/attempt-in-flight"
ACTIVE= F_LOT= F_N= F_K=
if [ -f "$INFLIGHT" ]; then
    read -r F_LOT F_N F_K < "$INFLIGHT" || true
    RUNS="refs/bwr/$(basename "$WORKSPACE")"
    if git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N" >/dev/null \
       || git rev-parse --verify --quiet "$RUNS/$F_LOT/task-$F_N-try-$F_K" >/dev/null; then
        :
    else
        ACTIVE=$F_LOT
    fi
fi
if [ -n "$ACTIVE" ]; then
    [ "$MARK_LOT" = "$ACTIVE" ] \
        || die "active attempt $ACTIVE does not match the attempt mark bound to this breach"
elif [ "$MARK_LOT" = "-" ]; then
    :
fi

BASE=
if [ -n "$ACTIVE" ]; then
    BASE="refs/bwr/$(basename "$WORKSPACE")/$ACTIVE/attempt-base"
    CURRENT_BASE=$(git rev-parse --verify --quiet "$BASE") \
        || die "the active attempt's base ref is missing"
fi

HEAD=$(git rev-parse HEAD)
if [ -n "$BASE" ]; then
    [ "$CURRENT_BASE" = "$BAD_SHA" ] || [ "$CURRENT_BASE" = "$HEAD" ] \
        || die "the active attempt's base points at neither the bad nor current recovery commit"
fi
if [ "$HEAD" = "$BAD_SHA" ]; then
    WORK_BLOB=$(git hash-object -- "$SPEC")
    [ "$WORK_BLOB" = "$BAD_BLOB" ] || [ "$WORK_BLOB" = "$AUTH_BLOB" ] \
        || die "the spec content is neither the bad state nor the authorised recovery state"
    if ! git diff --cached --quiet "$BAD_SHA" -- "$SPEC"; then
        git diff --cached --quiet "$AUTHORIZED_SHA" -- "$SPEC" \
            || die "the staged spec is neither the bad state nor the authorised recovery state"
    fi
    git restore --source="$AUTHORIZED_SHA" --worktree -- "$SPEC"
    git add -- "$SPEC"
    git commit -q -m "$SUBJECT" -- "$SPEC"
    HEAD=$(git rev-parse HEAD)
elif [ "$(git rev-parse "$HEAD^")" != "$BAD_SHA" ]; then
    die "HEAD is neither the bad commit nor its corrective child; the recovery cannot choose a history"
fi
validate_correction "$HEAD"

MARK_MOVED=false
if [ -n "$BASE" ]; then
    CURRENT_BASE=$(git rev-parse --verify --quiet "$BASE") \
        || die "the active attempt's base ref disappeared after the corrective commit"
    if [ "$CURRENT_BASE" = "$BAD_SHA" ]; then
        git update-ref "$BASE" "$HEAD" "$BAD_SHA"
    elif [ "$CURRENT_BASE" != "$HEAD" ]; then
        die "the active attempt's base points at neither the bad nor corrective commit"
    fi
    MARK_MOVED=true
fi

NOTE_DATA="{\"breach\":$BREACH,\"owner\":\"$OWNER\",\"answer\":\"$ANSWER\",\"bad_op\":\"$BAD_OP\",\"bad_sha\":\"$BAD_SHA\",\"authorized_sha\":\"$AUTHORIZED_SHA\",\"sha\":\"$HEAD\",\"op\":\"$REPAIR_OP\",\"mark_moved\":$MARK_MOVED"
if [ "$MARK_LOT" != "-" ]; then
    NOTE_DATA+=",\"mark_lot\":\"$MARK_LOT\""
fi
NOTE_DATA+="}"
NOTE=("$WORKSPACE/prompts/common/progress.py" note spec.breach.corrected --data "$NOTE_DATA")
JOURNAL_MISSING=
"${NOTE[@]}" || JOURNAL_MISSING=$(printf '%q ' "${NOTE[@]}")
[ -n "$JOURNAL_MISSING" ] || rm -f "$PENDING"
printf 'CORRECTED breach %s\nBAD %s\nSHA %s\nMARK %s\n' \
    "$BREACH" "$BAD_SHA" "$HEAD" "$MARK_MOVED"
if [ -n "$JOURNAL_MISSING" ]; then
    {
        printf '**script WARNING** · the corrective commit and any mark move ARE done, but\n'
        printf 'spec.breach.corrected is missing. Run this same call again. The marker\n'
        printf 'keeps the operation identity, and the commit does not repeat.\n\n'
        printf '    %s\n' "$JOURNAL_MISSING"
    } >&2
    exit 1
fi
