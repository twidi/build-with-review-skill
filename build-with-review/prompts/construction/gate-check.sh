#!/usr/bin/env bash
# Freeze, verify and consume one logical full-gate check.
#
# The runner is a subagent, but its candidate is repository state. This helper
# keeps that state stable across a lost physical call. It also makes a green
# result consumable by the exact task commit or controller baseline it checked.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE=$(cd "$HERE/../.." && pwd)
EXPECTED_REPO=$(cd "$WORKSPACE/../../.." && pwd -P)
MARKER="$WORKSPACE/gate-check-in-progress"
JOURNAL="$WORKSPACE/progress.jsonl"
PROGRESS="$WORKSPACE/prompts/common/progress.py"
GATE_REPORT="$WORKSPACE/prompts/construction/gate_report.py"
die() { printf '**script ERROR** · %s\n' "$*" >&2; exit 1; }

cd "$EXPECTED_REPO"
REPO=$(git rev-parse --show-toplevel 2>/dev/null) \
    || die "$EXPECTED_REPO is not a Git repository"
REPO=$(cd "$REPO" && pwd -P)
[ "$REPO" = "$EXPECTED_REPO" ] \
    || die "the workspace does not belong to the exact repository root: expected $EXPECTED_REPO, got $REPO"
GATE="$REPO/.superpowers/bwr/gate.md"

validate_gate() {
    local path
    for path in "$REPO/.superpowers" "$REPO/.superpowers/bwr"; do
        [ -d "$path" ] && [ ! -L "$path" ] && [ "$(cd "$path" && pwd -P)" = "$path" ] \
            || die "$path must be one real checkout-local directory"
    done
    [ -f "$GATE" ] && [ ! -L "$GATE" ] \
        || die "$GATE must be one real checkout-local regular file"
    GATE_SHA=$(git hash-object "$GATE")
}

candidate_tree() {
    local dirty untracked
    dirty=$(git diff --name-only)
    untracked=$(git ls-files --others --exclude-standard)
    [ -z "$dirty$untracked" ] || die "the gate candidate is not fully staged.
Unstaged tracked paths:
${dirty:-<none>}
Untracked paths:
${untracked:-<none>}
Stage the exact candidate before opening the gate. Nothing was recorded."
    git write-tree
}

read_marker() {
    local tag value extra
    [ -f "$MARKER" ] && [ ! -L "$MARKER" ] \
        || die "the gate-check marker is not one real regular file: $MARKER"
    mapfile -t M_LINES < "$MARKER"
    [ "${#M_LINES[@]}" -eq 11 ] \
        || die "the gate-check marker has ${#M_LINES[@]} lines; expected 11"
    marker_value() {
        local wanted=$1 line found=()
        for line in "${M_LINES[@]}"; do
            read -r tag value extra <<< "$line"
            if [ "$tag" = "$wanted" ]; then
                [ -z "$extra" ] || die "the gate-check marker has extra data on $wanted"
                found+=("$value")
            fi
        done
        [ "${#found[@]}" -eq 1 ] || die "the gate-check marker has no unique $wanted"
        printf '%s' "${found[0]}"
    }
    M_OP=$(marker_value op)
    M_SCOPE=$(marker_value scope)
    M_OWNER=$(marker_value owner)
    M_LOT=$(marker_value lot)
    M_TASK=$(marker_value task)
    M_ATTEMPT=$(marker_value attempt)
    M_HEAD=$(marker_value head)
    M_BASE=$(marker_value base)
    M_TREE=$(marker_value tree)
    M_GATE=$(marker_value gate)
    M_CODE=$(marker_value code)
    [[ $M_OP =~ ^[0-9a-f]{64}$ ]] || die "the gate-check marker has an invalid operation identity"
    [[ $M_SCOPE =~ ^(task|baseline|review)$ ]] || die "the gate-check marker has an invalid scope"
    [[ $M_OWNER =~ ^[A-Za-z0-9._:/-]+$ ]] || die "the gate-check marker has an invalid owner"
    [[ $M_LOT =~ ^(-|lot-[1-9][0-9]*(\.[1-9][0-9]*)?)$ ]] || die "the gate-check marker has an invalid lot"
    [[ $M_TASK =~ ^[0-9]+$ ]] && [[ $M_ATTEMPT =~ ^[0-9]+$ ]] \
        || die "the gate-check marker has an invalid task or attempt"
    for value in "$M_HEAD" "$M_BASE" "$M_TREE" "$M_GATE"; do
        [[ $value =~ ^[0-9a-f]{40,64}$ ]] || die "the gate-check marker has an invalid Git identity"
    done
    if [ "$M_SCOPE" = task ]; then
        [[ $M_CODE =~ ^[0-9]+:[0-9a-f]{64}$ ]] \
            || die "the task gate-check marker has no valid final code-review proof"
    else
        [ "$M_CODE" = - ] || die "a baseline gate-check marker carries a task code proof"
    fi
}

validate_frozen_state() {
    validate_gate
    [ "$GATE_SHA" = "$M_GATE" ] \
        || die "gate.md changed during logical gate check $M_OP: expected $M_GATE, got $GATE_SHA"
    [ "$(git rev-parse HEAD)" = "$M_HEAD" ] \
        || die "HEAD changed during logical gate check $M_OP"
    local tree
    tree=$(candidate_tree)
    [ "$tree" = "$M_TREE" ] \
        || die "the candidate changed during logical gate check $M_OP: expected tree $M_TREE, got $tree.
Do not let a regenerated physical call adopt those bytes. Return to the owning checker or controller, then open a new logical gate check."
}

latest_code_proof() {
    "$PROGRESS" construction-verdict-check code "$1" "$2" "$3"
}

journal_gate_result() {
    # Print zero, one or many exact ended-event JSON objects for this op.
    python3 - "$JOURNAL" "$1" <<'PY'
import json, pathlib, sys
path, op = pathlib.Path(sys.argv[1]), sys.argv[2]
if not path.exists():
    raise SystemExit(0)
for raw in path.read_text(encoding="utf-8").splitlines():
    event = json.loads(raw)
    if event.get("event") == "subagent-ended" and event.get("kind") == "gate-runner" \
            and (event.get("data") or {}).get("op") == op:
        print(json.dumps(event, separators=(",", ":"), sort_keys=True))
PY
}

event_data() {
    local audit=${1:-}
    python3 - "$M_OP" "$M_SCOPE" "$M_OWNER" "$M_LOT" "$M_TASK" "$M_ATTEMPT" \
        "$M_HEAD" "$M_BASE" "$M_TREE" "$M_GATE" "$M_CODE" "$audit" <<'PY'
import json, sys
keys = ("op", "scope", "owner", "lot", "task", "attempt", "head", "base", "tree", "gate", "code")
values = sys.argv[1:12]
data = dict(zip(keys, values))
data["task"] = int(data["task"])
data["attempt"] = int(data["attempt"])
if sys.argv[12]:
    outcome = json.loads(sys.argv[12])
    if set(outcome) != {"green", "surface", "report", "report_sha256", "commands"}:
        raise SystemExit("the gate report audit has an invalid result shape")
    data.update(outcome)
print(json.dumps(data, separators=(",", ":")))
PY
}

audit_report() {
    python3 "$GATE_REPORT" "$1" "$2" "$3"
}

terminal_matches_audit() {
    local event=$1 audit=$2 expected
    expected=$(event_data "$audit")
    python3 - "$event" "$expected" <<'PY'
import json, sys
event, expected = json.loads(sys.argv[1]), json.loads(sys.argv[2])
if event.get("data") != expected:
    raise SystemExit("the recorded gate terminal does not match the canonical physical report")
PY
}

open_check() {
    local scope=$1 owner=$2 lot=$3 task=$4 attempt=$5 base_arg=$6 code=-
    [[ $scope =~ ^(task|baseline|review)$ ]] || die "gate-check open scope must be task, review or baseline"
    [[ $owner =~ ^[A-Za-z0-9._:/-]+$ ]] || die "the gate-check owner has invalid characters"
    validate_gate
    local head base tree op round
    head=$(git rev-parse HEAD)
    base=$(git rev-parse --verify "$base_arg^{commit}") \
        || die "$base_arg is not a commit"
    tree=$(candidate_tree)
    if [ "$scope" = task ] || [ "$scope" = review ]; then
        [[ $lot =~ ^lot-[1-9][0-9]*(\.[1-9][0-9]*)?$ ]] \
            && [[ $task =~ ^[1-9][0-9]*$ ]] && [[ $attempt =~ ^[1-9][0-9]*$ ]] \
            || die "a task gate needs one valid lot, task and attempt"
        if [ "$scope" = task ]; then
            [ "$owner" = "$lot/task-$task/attempt-$attempt" ] \
                || die "the task gate owner must be $lot/task-$task/attempt-$attempt"
        else
            round=${owner#"$lot/task-$task/attempt-$attempt/code-round-"}
            [[ $round =~ ^[1-9][0-9]*$ ]] \
                && [ "$owner" = "$lot/task-$task/attempt-$attempt/code-round-$round" ] \
                || die "the review gate owner must identify one code round of this attempt"
        fi
        read -r f_lot f_task f_attempt < "$WORKSPACE/attempt-in-flight" 2>/dev/null \
            || die "no readable attempt is in flight"
        [ "$f_lot $f_task $f_attempt" = "$lot $task $attempt" ] \
            || die "attempt-in-flight names $f_lot task $f_task attempt $f_attempt, not this gate owner"
        if [ "$scope" = task ]; then
            code=$(latest_code_proof "$lot" "$task" "$attempt") \
                || die "the task gate cannot open before its latest code review has one durable final proof"
        fi
    else
        [ "$lot $task $attempt" = "- 0 0" ] \
            || die "a baseline gate uses lot '-', task 0 and attempt 0"
        [ -z "$(git status --porcelain)" ] \
            || die "a controller baseline gate opens only on a clean committed tree"
        [ "$tree" = "$(git rev-parse 'HEAD^{tree}')" ] \
            || die "a controller baseline gate must check the exact HEAD tree"
    fi

    if [ -e "$MARKER" ] || [ -L "$MARKER" ]; then
        read_marker
        [ "$M_SCOPE $M_OWNER $M_LOT $M_TASK $M_ATTEMPT $M_HEAD $M_BASE $M_TREE $M_GATE $M_CODE" \
          = "$scope $owner $lot $task $attempt $head $base $tree $GATE_SHA $code" ] \
            || die "another logical gate check owns the workspace: $M_OP ($M_OWNER).
Finish or abandon that exact check before opening another."
        validate_frozen_state
    else
        op=$(printf '%s\0' "$scope" "$owner" "$head" "$base" "$tree" "$GATE_SHA" "$code" \
            "$(date +%s%N)" "$$" "$RANDOM" | sha256sum | cut -d' ' -f1)
        {
            printf 'op %s\n' "$op"
            printf 'scope %s\n' "$scope"
            printf 'owner %s\n' "$owner"
            printf 'lot %s\n' "$lot"
            printf 'task %s\n' "$task"
            printf 'attempt %s\n' "$attempt"
            printf 'head %s\n' "$head"
            printf 'base %s\n' "$base"
            printf 'tree %s\n' "$tree"
            printf 'gate %s\n' "$GATE_SHA"
            printf 'code %s\n' "$code"
        } > "$MARKER.tmp"
        mv "$MARKER.tmp" "$MARKER"
        read_marker
    fi
    "$PROGRESS" subagent-started gate-runner --data "$(event_data)"
    printf 'OP %s\nGATE %s\nTREE %s\nHEAD %s\nBASE %s\n' \
        "$M_OP" "$M_GATE" "$M_TREE" "$M_HEAD" "$M_BASE"
}

close_check() {
    local op=$1 existing count audit green surface
    existing=$(journal_gate_result "$op")
    count=$(printf '%s\n' "$existing" | sed '/^$/d' | wc -l)
    [ "$count" -le 1 ] || die "logical gate check $op has more than one terminal result"
    if [ "$count" -eq 1 ]; then
        if [ -e "$MARKER" ] || [ -L "$MARKER" ]; then
            read_marker
            [ "$M_OP" = "$op" ] || die "the live gate marker belongs to $M_OP, not $op"
            validate_frozen_state
            audit=$(audit_report "$M_OP" "$M_GATE" "$M_TREE") \
                || die "the physical gate report for $M_OP is absent, incomplete or invalid"
            terminal_matches_audit "$existing" "$audit" \
                || die "the recorded gate terminal does not match its physical report"
            rm -f "$MARKER"
        fi
        printf 'GATE RESULT %s (already recorded)\n' "$op"
        return 0
    fi
    read_marker
    [ "$M_OP" = "$op" ] || die "the live gate marker belongs to $M_OP, not $op"
    validate_frozen_state
    audit=$(audit_report "$M_OP" "$M_GATE" "$M_TREE") \
        || die "the physical gate report for $M_OP is absent, incomplete or invalid"
    "$PROGRESS" subagent-ended gate-runner --data "$(event_data "$audit")"
    rm -f "$MARKER"
    green=$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1])["green"]).lower())' "$audit")
    surface=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["surface"])' "$audit")
    printf 'GATE RESULT %s green=%s surface=%s\n' "$op" "$green" "$surface"
}

validate_result() {
    local op=$1 mode=$2 lot=${3:--} task=${4:-0} attempt=${5:-0} commit=${6:-} result code_proof=-
    validate_gate
    result=$(journal_gate_result "$op")
    [ "$(printf '%s\n' "$result" | sed '/^$/d' | wc -l)" -eq 1 ] \
        || die "logical gate check $op has no unique terminal result"
    if [ "$mode" = task ]; then
        code_proof=$(latest_code_proof "$lot" "$task" "$attempt") \
            || die "the task gate consumes no exact proved final code-review result"
    fi
    python3 - "$JOURNAL" "$op" "$mode" "$lot" "$task" "$attempt" "$commit" "$GATE_SHA" "$REPO" "$GATE_REPORT" "$code_proof" <<'PY'
import hashlib, json, pathlib, subprocess, sys

journal, op, mode, lot, task, attempt, commit, gate, repo, report_helper, code_proof = sys.argv[1:]
task, attempt = int(task), int(attempt)
events = []
raw_lines = pathlib.Path(journal).read_bytes().splitlines()
for raw in raw_lines:
    event = json.loads(raw)
    if event.get("event") == "subagent-ended" and event.get("kind") == "gate-runner" \
            and (event.get("data") or {}).get("op") == op:
        events.append(event)
if len(events) != 1:
    raise SystemExit("no unique gate result")
d = events[0]["data"]
required = {"op","scope","owner","lot","task","attempt","head","base","tree","gate","code",
            "green","surface","report","report_sha256","commands"}
if set(d) != required or d["green"] is not True or d["surface"] != "unchanged" or d["gate"] != gate:
    raise SystemExit("the gate result is not one exact green, unchanged result for the current gate")
audit = json.loads(subprocess.check_output(
    [sys.executable, report_helper, op, d["gate"], d["tree"]], text=True
))
if any(d.get(key) != value for key, value in audit.items()):
    raise SystemExit("the gate result does not match its canonical physical report")
if mode == "review":
    tree = commit
else:
    tree = subprocess.check_output(
        ["git", "-C", repo, "rev-parse", f"{commit or 'HEAD'}^{{tree}}"], text=True
    ).strip()
if d["tree"] != tree:
    raise SystemExit("the gate result checked a different candidate tree")
if mode == "review":
    if d["scope"] != "review" or (d["lot"], d["task"], d["attempt"]) != (lot, task, attempt):
        raise SystemExit("the ordinary gate result belongs to another review generation")
    if d["code"] != "-":
        raise SystemExit("an ordinary pre-review gate carries a final code proof")
elif mode == "task":
    if d["scope"] != "task" or (d["lot"], d["task"], d["attempt"]) != (lot, task, attempt):
        raise SystemExit("the gate result belongs to another attempt")
    if d["code"] != code_proof:
        raise SystemExit("the gate result does not consume the current proved code-checker verdict")
    try:
        code_index, code_hash = d["code"].split(":", 1)
        raw = raw_lines[int(code_index)]
    except Exception as exc:
        raise SystemExit("the gate result has an invalid code-checker proof") from exc
    if hashlib.sha256(raw).hexdigest() != code_hash:
        raise SystemExit("the code-checker proof no longer identifies its journal line")
    event = json.loads(raw)
    data = event.get("data") or {}
    clean = (
        event.get("kind") == "verdict.consumed" and event.get("lot") == lot
        and event.get("task") == task and event.get("attempt") == attempt
        and data.get("check") == "code" and data.get("outcome") == "clean"
    )
    resolved = (
        event.get("kind") == "code.review.resolved" and event.get("lot") == lot
        and event.get("task") == task and event.get("attempt") == attempt
        and event.get("round") == 10 and data.get("check") == "code"
        and data.get("round") == 10 and data.get("accepted") == 0
        and isinstance(data.get("findings"), int) and data.get("findings") > 0
        and isinstance(data.get("items"), list) and len(data["items"]) == data["findings"]
    )
    if not (clean or resolved):
        raise SystemExit("the gate result does not follow an accepted final code-review proof")
    later = [json.loads(line) for line in raw_lines[int(code_index)+1:]]
    for item in later:
        item_data = item.get("data") or {}
        if (item.get("kind") in {"verdict.consumed", "code.review.resolved"}
                and item.get("lot") == lot
                and item.get("task") == task and item.get("attempt") == attempt
                and item_data.get("check") == "code"):
            raise SystemExit("a later code-review boundary invalidates this final gate result")
elif mode == "baseline":
    if d["scope"] != "baseline" or d["head"] != commit:
        raise SystemExit("the gate result is not the baseline for this commit")
else:
    raise SystemExit("unknown validation mode")
PY
}

require_current() {
    validate_gate
    local head tree fields op scope lot task attempt
    head=$(git rev-parse HEAD)
    tree=$(git rev-parse 'HEAD^{tree}')
    [ -z "$(git status --porcelain)" ] || die "the current repository state is not clean"
    fields=$(python3 - "$JOURNAL" "$head" "$tree" "$GATE_SHA" "$REPO" <<'PY'
import json, pathlib, subprocess, sys
journal, head, tree, gate, repo = sys.argv[1:]
events = []
if pathlib.Path(journal).exists():
    events = [json.loads(line) for line in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
results = {e["data"]["op"]: e["data"] for e in events
           if e.get("event") == "subagent-ended" and e.get("kind") == "gate-runner"
           and (e.get("data") or {}).get("green") is True
           and (e.get("data") or {}).get("surface") == "unchanged"}
for op, data in reversed(list(results.items())):
    if data.get("gate") != gate or data.get("tree") != tree:
        continue
    if data.get("scope") == "baseline" and data.get("head") == head:
        print(op, "baseline", "-", 0, 0)
        raise SystemExit(0)
    if data.get("scope") == "task" and any(
        e.get("kind") == "attempt.succeeded" and (e.get("data") or {}).get("sha") == head
        and (e.get("data") or {}).get("gate") == op for e in events
    ):
        success = next(e for e in events if e.get("kind") == "attempt.succeeded"
                       and (e.get("data") or {}).get("sha") == head
                       and (e.get("data") or {}).get("gate") == op)
        print(op, "task", success["lot"], success["task"], success["data"]["attempt"])
        raise SystemExit(0)
raise SystemExit("current HEAD has no accepted green gate proof for the current gate.md")
PY
    ) || die "current HEAD has no accepted green gate proof for the current gate.md"
    read -r op scope lot task attempt <<< "$fields"
    validate_result "$op" "$scope" "$lot" "$task" "$attempt" "$head"
    printf '%s\n' "$op"
}

require_pass() {
    local op=$1 commit=$2 fields scope owner lot task attempt
    [ "$(git rev-parse HEAD)" = "$(git rev-parse --verify "$commit^{commit}")" ] \
        || die "the reviewed commit $commit is not the current HEAD"
    [ -z "$(git status --porcelain)" ] \
        || die "a product pass cannot open on a dirty repository state"
    fields=$(python3 - "$JOURNAL" "$op" "$commit" <<'PY'
import json, pathlib, sys
journal, op, commit = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
results = [e["data"] for e in events if e.get("event") == "subagent-ended"
           and e.get("kind") == "gate-runner" and (e.get("data") or {}).get("op") == op]
if len(results) != 1:
    raise SystemExit("the pass gate has no unique result")
d = results[0]
if d.get("scope") == "baseline":
    if d.get("head") != commit:
        raise SystemExit("the baseline gate checked another commit")
    print("baseline", d.get("owner"), "-", 0, 0)
    raise SystemExit(0)
matches = [e for e in events if e.get("kind") == "attempt.succeeded"
           and (e.get("data") or {}).get("gate") == op
           and (e.get("data") or {}).get("sha") == commit]
if len(matches) != 1:
    raise SystemExit("the task gate was not consumed by this reviewed commit")
data = matches[0]["data"]
print("task", d.get("owner"), matches[0]["lot"], matches[0]["task"], data["attempt"])
PY
) || die "gate operation $op is not an accepted proof for reviewed commit $commit"
    read -r scope owner lot task attempt <<< "$fields"
    validate_result "$op" "$scope" "$lot" "$task" "$attempt" "$commit"
    printf '%s\n' "$fields"
}

find_task() {
    local lot=$1 task=$2 attempt=$3 commit=$4 op
    validate_gate
    op=$(python3 - "$JOURNAL" "$lot" "$task" "$attempt" "$commit" "$GATE_SHA" "$REPO" <<'PY'
import json, pathlib, subprocess, sys
journal, lot, task, attempt, commit, gate, repo = sys.argv[1:]
tree = subprocess.check_output(["git", "-C", repo, "rev-parse", f"{commit}^{{tree}}"], text=True).strip()
events = [json.loads(line) for line in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
matches = [e["data"]["op"] for e in events if e.get("event") == "subagent-ended"
           and e.get("kind") == "gate-runner" and (e.get("data") or {}).get("scope") == "task"
           and e["data"].get("lot") == lot and e["data"].get("task") == int(task)
           and e["data"].get("attempt") == int(attempt) and e["data"].get("tree") == tree
           and e["data"].get("gate") == gate and e["data"].get("green") is True
           and e["data"].get("surface") == "unchanged"]
if len(matches) != 1:
    raise SystemExit("the attempt has no unique accepted final gate result")
print(matches[0])
PY
) || die "cannot recover one exact final gate operation for $lot task $task attempt $attempt"
    validate_result "$op" task "$lot" "$task" "$attempt" "$commit"
    printf '%s\n' "$op"
}

case ${1:-} in
    open)
        [ $# -eq 7 ] || die "usage: gate-check.sh open <task|baseline> <owner> <lot|-> <task|0> <attempt|0> <base commit>"
        shift
        open_check "$@"
        ;;
    verify)
        [ $# -eq 2 ] || die "usage: gate-check.sh verify <op>"
        read_marker
        [ "$M_OP" = "$2" ] || die "the live gate marker belongs to $M_OP, not $2"
        validate_frozen_state
        printf 'VERIFIED %s\n' "$M_OP"
        ;;
    close)
        [ $# -eq 2 ] || die "usage: gate-check.sh close <op>"
        close_check "$2"
        ;;
    abandon)
        [ $# -eq 2 ] || die "usage: gate-check.sh abandon <op>"
        read_marker
        [ "$M_OP" = "$2" ] || die "the live gate marker belongs to $M_OP, not $2"
        [ -z "$(journal_gate_result "$2")" ] \
            || die "gate check $2 already has a durable result and cannot be abandoned"
        rm -f "$MARKER"
        printf 'ABANDONED %s\n' "$2"
        ;;
    require-task)
        [ $# -eq 6 ] || die "usage: gate-check.sh require-task <op> <lot> <task> <attempt> <commit>"
        validate_result "$2" task "$3" "$4" "$5" "$6"
        printf 'ACCEPTED %s\n' "$2"
        ;;
    require-review)
        [ $# -eq 5 ] || die "usage: gate-check.sh require-review <op> <lot> <task> <attempt>"
        REVIEW_TREE=$(candidate_tree)
        validate_result "$2" review "$3" "$4" "$5" "$REVIEW_TREE"
        printf '%s\n' "$REVIEW_TREE"
        ;;
    require-baseline)
        [ $# -eq 3 ] || die "usage: gate-check.sh require-baseline <op> <commit>"
        validate_result "$2" baseline - 0 0 "$3"
        printf 'ACCEPTED %s\n' "$2"
        ;;
    require-current)
        [ $# -eq 1 ] || die "usage: gate-check.sh require-current"
        require_current
        ;;
    require-pass)
        [ $# -eq 3 ] || die "usage: gate-check.sh require-pass <op> <reviewed commit>"
        require_pass "$2" "$3"
        ;;
    find-task)
        [ $# -eq 5 ] || die "usage: gate-check.sh find-task <lot> <task> <attempt> <commit>"
        find_task "$2" "$3" "$4" "$5"
        ;;
    *)
        die "usage: gate-check.sh <open|verify|close|abandon|require-review|require-task|require-baseline|require-current|require-pass|find-task> ..."
        ;;
esac
