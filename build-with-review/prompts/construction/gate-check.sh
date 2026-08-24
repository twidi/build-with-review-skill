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
GATE_EXECUTION="$WORKSPACE/prompts/construction/gate_execution.py"
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
    [ "${#M_LINES[@]}" -eq 11 ] || [ "${#M_LINES[@]}" -eq 12 ] \
        || die "the gate-check marker has ${#M_LINES[@]} lines; expected 11 or 12"
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
    M_EXECUTION=-
    if [ "${#M_LINES[@]}" -eq 12 ]; then
        M_EXECUTION=$(marker_value execution)
    fi
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
    M_EXECUTION_HASH=-
    if [ "$M_EXECUTION" != - ]; then
        M_EXECUTION_HASH=$(python3 "$GATE_EXECUTION" validate-token \
            "$M_EXECUTION" "$M_GATE" "$M_TREE") \
            || die "the gate-check marker has an invalid frozen execution"
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
    # Print zero, one or many accepted physical-result terminals for this op.
    python3 - "$JOURNAL" "$1" <<'PY'
import json, pathlib, sys
path, op = pathlib.Path(sys.argv[1]), sys.argv[2]
if not path.exists():
    raise SystemExit(0)
for raw in path.read_text(encoding="utf-8").splitlines():
    event = json.loads(raw)
    if event.get("event") == "subagent-ended" and event.get("kind") == "gate-runner" \
            and (event.get("data") or {}).get("op") == op \
            and "unusable" not in (event.get("data") or {}):
        print(json.dumps(event, separators=(",", ":"), sort_keys=True))
PY
}

open_gate_call() {
    python3 - "$JOURNAL" "$1" <<'PY'
import json, pathlib, sys
path, op = pathlib.Path(sys.argv[1]), sys.argv[2]
balance = 0
if path.exists():
    for raw in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        if event.get("kind") != "gate-runner" or (event.get("data") or {}).get("op") != op:
            continue
        if event.get("event") == "subagent-started":
            balance += 1
        elif event.get("event") == "subagent-ended":
            balance -= 1
        if balance not in {0, 1}:
            raise SystemExit("the gate operation has malformed physical-call brackets")
print("yes" if balance == 1 else "no")
PY
}

event_data() {
    local audit=${1:-} unusable=${2:-}
    python3 - "$M_OP" "$M_SCOPE" "$M_OWNER" "$M_LOT" "$M_TASK" "$M_ATTEMPT" \
        "$M_HEAD" "$M_BASE" "$M_TREE" "$M_GATE" "$M_CODE" "$M_EXECUTION_HASH" \
        "$audit" "$unusable" <<'PY'
import json, sys
keys = ("op", "scope", "owner", "lot", "task", "attempt", "head", "base", "tree", "gate", "code", "execution")
values = sys.argv[1:13]
data = dict(zip(keys, values))
data["task"] = int(data["task"])
data["attempt"] = int(data["attempt"])
if data["execution"] == "-":
    del data["execution"]
if sys.argv[14]:
    if sys.argv[14] not in {"error", "empty", "lost", "unusable"}:
        raise SystemExit("the gate-runner unusable reason is invalid")
    data["unusable"] = sys.argv[14]
elif sys.argv[13]:
    outcome = json.loads(sys.argv[13])
    if set(outcome) != {"green", "surface", "report", "report_sha256", "commands"}:
        raise SystemExit("the gate report audit has an invalid result shape")
    data.update(outcome)
print(json.dumps(data, separators=(",", ":")))
PY
}

audit_report() {
    python3 "$GATE_REPORT" "$1" "$2" "$3" "$4"
}

runner_input() {
    local op=$1
    read_marker
    [ "$M_OP" = "$op" ] || die "the live gate marker belongs to $M_OP, not $op"
    validate_frozen_state
    python3 - "$M_OP" "$GATE" "$M_GATE" "$M_TREE" "$M_HEAD" "$M_BASE" \
        "$M_EXECUTION_HASH" "$WORKSPACE/reports/gate/$M_OP.json" \
        "$HERE/gate-check.sh" "$GATE_EXECUTION" <<'PY'
import json, sys

op, gate_path, gate, tree, head, base, execution, report, gate_check, gate_execution = sys.argv[1:]
print(json.dumps({
    "schema": 1,
    "operation": op,
    "gate_path": gate_path,
    "gate_blob": gate,
    "candidate_tree": tree,
    "head": head,
    "predecessor": base,
    "execution": execution,
    "report_path": report,
    "commands": {
        "verify": ["bash", gate_check, "verify", op],
        "run": ["python3", gate_execution, "run", op],
        "inspect": ["python3", gate_execution, "inspect", op],
        "publish_report": ["bash", gate_check, "publish-report", op],
    },
}, separators=(",", ":"), sort_keys=True))
PY
}

publish_report() {
    local op=$1
    read_marker
    [ "$M_OP" = "$op" ] || die "the live gate marker belongs to $M_OP, not $op"
    validate_frozen_state
    python3 "$GATE_REPORT" publish "$M_OP" "$M_GATE" "$M_TREE" "$M_EXECUTION_HASH"
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
    local head base tree op round marker_draft
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
        marker_draft=$(mktemp "$WORKSPACE/.gate-check-in-progress.XXXXXX")
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
        } > "$marker_draft"
        python3 "$GATE_EXECUTION" open-marker "$marker_draft" \
            || { rm -f "$marker_draft"; die "the logical gate could not freeze its exact policy and schedule"; }
        rm -f "$marker_draft"
        read_marker
    fi
    "$PROGRESS" subagent-started gate-runner --data "$(event_data)"
    printf 'OP %s\nGATE %s\nTREE %s\nHEAD %s\nBASE %s\nEXECUTION %s\n' \
        "$M_OP" "$M_GATE" "$M_TREE" "$M_HEAD" "$M_BASE" "$M_EXECUTION_HASH"
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
            audit=$(audit_report "$M_OP" "$M_GATE" "$M_TREE" "$M_EXECUTION_HASH") \
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
    audit=$(audit_report "$M_OP" "$M_GATE" "$M_TREE" "$M_EXECUTION_HASH") \
        || die "the physical gate report for $M_OP is absent, incomplete or invalid"
    "$PROGRESS" subagent-ended gate-runner --data "$(event_data "$audit")"
    rm -f "$MARKER"
    green=$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1])["green"]).lower())' "$audit")
    surface=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["surface"])' "$audit")
    printf 'GATE RESULT %s green=%s surface=%s\n' "$op" "$green" "$surface"
}

lost_check() {
    local op=$1
    read_marker
    [ "$M_OP" = "$op" ] || die "the live gate marker belongs to $M_OP, not $op"
    [ -z "$(journal_gate_result "$op")" ] \
        || die "gate check $op already has a durable result and cannot become lost"
    [ "$(open_gate_call "$op")" = yes ] \
        || die "gate check $op has no one exact open physical runner"
    if [ "$M_EXECUTION" != - ]; then
        python3 "$GATE_EXECUTION" idle "$op" \
            || die "gate check $op still has a live executor or command; do not lose its owner"
    fi
    "$PROGRESS" subagent-ended gate-runner --data "$(event_data "" lost)"
    printf 'GATE RUNNER LOST %s\n' "$op"
}

validate_result() {
    local op=$1 mode=$2 lot=${3:--} task=${4:-0} attempt=${5:-0} commit=${6:-} historical=${7:-false} result code_proof=- tree
    validate_gate
    result=$(journal_gate_result "$op")
    [ "$(printf '%s\n' "$result" | sed '/^$/d' | wc -l)" -eq 1 ] \
        || die "logical gate check $op has no unique terminal result"
    if [ "$mode" = task ]; then
        if [ "$historical" = true ]; then
            code_proof=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["data"]["code"])' "$result") \
                || die "the historical task gate has no stored final code proof"
            tree=$(git rev-parse "$commit^{tree}")
            "$PROGRESS" construction-verdict-check historical-code \
                "$lot" "$task" "$attempt" "$code_proof" "$tree" >/dev/null \
                || die "the task gate consumes no exact historical final code-review result"
        else
            code_proof=$(latest_code_proof "$lot" "$task" "$attempt") \
                || die "the task gate consumes no exact proved final code-review result"
        fi
    fi
    python3 - "$JOURNAL" "$result" "$op" "$mode" "$lot" "$task" "$attempt" "$commit" "$GATE_SHA" "$REPO" "$GATE_REPORT" "$code_proof" <<'PY'
import hashlib, json, pathlib, subprocess, sys

journal, accepted, op, mode, lot, task, attempt, commit, gate, repo, report_helper, code_proof = sys.argv[1:]
task, attempt = int(task), int(attempt)
raw_lines = pathlib.Path(journal).read_bytes().splitlines()
event = json.loads(accepted)
if event.get("event") != "subagent-ended" or event.get("kind") != "gate-runner" \
        or (event.get("data") or {}).get("op") != op \
        or "unusable" in (event.get("data") or {}):
    raise SystemExit("the selected gate result is not one accepted terminal")
d = event["data"]
events = [json.loads(raw) for raw in raw_lines]
terminal_indexes = [index for index, candidate in enumerate(events) if candidate == event]
if len(terminal_indexes) != 1:
    raise SystemExit("the selected gate result has no unique historical terminal")
active = None
for candidate in events[:terminal_indexes[0]]:
    if candidate.get("kind") != "gate-runner" or (candidate.get("data") or {}).get("op") != op:
        continue
    if candidate.get("event") == "subagent-started":
        if active is not None:
            raise SystemExit("the selected gate result has overlapping physical openings")
        active = candidate["data"]
    elif candidate.get("event") == "subagent-ended":
        if active is None:
            raise SystemExit("the selected gate result has a terminal without its opening")
        active = None
if active is None:
    raise SystemExit("the selected gate result has no exact physical opening")
identity = {
    "op", "scope", "owner", "lot", "task", "attempt", "head", "base", "tree", "gate", "code",
}
if "execution" in d:
    identity.add("execution")
if set(active) != identity or any(active[key] != d[key] for key in identity):
    raise SystemExit("the selected gate result changes its physical opening identity")
required = {"op","scope","owner","lot","task","attempt","head","base","tree","gate","code",
            "green","surface","report","report_sha256","commands"}
if set(d) not in (required, required | {"execution"}) \
        or d["green"] is not True or d["surface"] != "unchanged" or d["gate"] != gate:
    raise SystemExit("the gate result is not one exact green, unchanged result for the current gate")
audit = json.loads(subprocess.check_output(
    [sys.executable, report_helper, op, d["gate"], d["tree"], d.get("execution", "-")], text=True
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
        if (item.get("kind") in {
                "verdict.consumed", "code.review.resolved", "code.review.blocked",
            }
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
    validate_result "$op" "$scope" "$lot" "$task" "$attempt" "$head" true
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
           and e.get("kind") == "gate-runner" and (e.get("data") or {}).get("op") == op
           and "unusable" not in (e.get("data") or {})]
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
    validate_result "$op" "$scope" "$lot" "$task" "$attempt" "$commit" true
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
    validate_result "$op" task "$lot" "$task" "$attempt" "$commit" true
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
    runner-input)
        [ $# -eq 2 ] || die "usage: gate-check.sh runner-input <op>"
        runner_input "$2"
        ;;
    publish-report)
        [ $# -eq 2 ] || die "usage: gate-check.sh publish-report <op>"
        publish_report "$2"
        ;;
    close)
        [ $# -eq 2 ] || die "usage: gate-check.sh close <op>"
        close_check "$2"
        ;;
    lost)
        [ $# -eq 2 ] || die "usage: gate-check.sh lost <op>"
        lost_check "$2"
        ;;
    abandon)
        [ $# -eq 2 ] || die "usage: gate-check.sh abandon <op>"
        read_marker
        [ "$M_OP" = "$2" ] || die "the live gate marker belongs to $M_OP, not $2"
        [ -z "$(journal_gate_result "$2")" ] \
            || die "gate check $2 already has a durable result and cannot be abandoned"
        if [ "$M_EXECUTION" != - ]; then
            python3 "$GATE_EXECUTION" idle "$2" \
                || die "gate check $2 still has a live executor or command; do not abandon its owner"
        fi
        if [ "$(open_gate_call "$2")" = yes ]; then
            "$PROGRESS" subagent-ended gate-runner --data "$(event_data "" unusable)"
        fi
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
        die "usage: gate-check.sh <open|runner-input|publish-report|verify|close|lost|abandon|require-review|require-task|require-baseline|require-current|require-pass|find-task> ..."
        ;;
esac
