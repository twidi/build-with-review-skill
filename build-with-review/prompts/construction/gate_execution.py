#!/usr/bin/env python3
"""Freeze and execute one semantically admitted gate-command schedule."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from gate_file import GateFileError, read_gate_commands


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
GATE = REPO / ".superpowers" / "bwr" / "gate.md"
POLICY = WORKSPACE / "gate-policy.json"
CONFIG = WORKSPACE / "gate-execution.json"
MARKER = WORKSPACE / "gate-check-in-progress"
AUTHORITY_LOCK = WORKSPACE / "gate-authority.lock"
REPORT_GROUND = WORKSPACE / "reports" / "gate"
OUTPUT_CHUNK_BYTES = 65536
MARKER_KEYS = (
    "op", "scope", "owner", "lot", "task", "attempt", "head", "base", "tree", "gate", "code"
)
CORRECTION_AUTHORITY_KEYS = (
    "contract_authority_sha256", "execution_authority_sha256",
    "final_checker_set_sha256",
)
CORRECTION_ATTEMPT_AUTHORITY_KEYS = (*CORRECTION_AUTHORITY_KEYS, "attempt_marker_sha256")
CORRECTION_SCOPES = {"correction-task", "correction-review", "correction-baseline"}
CORRECTION_OWNER_MARKERS = {
    "amendment-commit-in-progress",
    "document-copy-in-progress",
    "plan-commit-in-progress",
    "rewind-in-progress",
    "spec-breach-recovery-in-progress",
    "spec-commit-in-progress",
    "correction-allocation-supersede-in-progress",
    "correction-artifact-in-progress",
    "correction-attempt-failure-in-progress",
    "correction-attempt-stop-in-progress",
    "correction-product-authority-in-progress",
    "correction-round-built-in-progress",
    "correction-terminal-restore-in-progress",
    "correction-round-open-in-progress",
    "correction-round-revision-in-progress",
    "correction-round-void-in-progress",
    "correction-rewind-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
    "correction-round-escalation-in-progress",
}
CORRECTION_BASELINE_OWNER_MARKERS = {
    "correction-round-revision-in-progress",
    "correction-rewind-in-progress",
    "final-checker-contract-map-in-progress",
    "correction-amendment-return-in-progress",
}

COMMON = WORKSPACE / "prompts" / "common"
sys.path.insert(0, str(COMMON))

import progress  # noqa: E402
from correction_authority import (  # noqa: E402
    CorrectionAuthorityLease,
    WorkspaceFileAnchor,
)


class GateExecutionError(ValueError):
    """The gate execution configuration or account is invalid."""


def refuse(message):
    raise GateExecutionError(message)


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def regular_file(path, subject):
    if path.is_symlink() or not path.is_file():
        refuse(f"{subject} is not one real regular file: {path}")
    return path


def workspace_file(path, subject):
    try:
        relative = path.relative_to(WORKSPACE)
    except ValueError:
        refuse(f"{subject} is outside the workspace: {path}")
    current = WORKSPACE
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            refuse(f"{subject} traverses a symlink: {current}")
    return regular_file(current, subject)


def workspace_directory(path, subject):
    try:
        relative = path.relative_to(WORKSPACE)
    except ValueError:
        refuse(f"{subject} is outside the workspace: {path}")
    current = WORKSPACE
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            refuse(f"{subject} traverses a symlink: {current}")
    if not current.is_dir():
        refuse(f"{subject} is not one real directory: {current}")
    return current


def gate_state():
    try:
        commands = read_gate_commands(regular_file(GATE, "gate.md"))
    except (OSError, UnicodeError, GateFileError) as exc:
        refuse(str(exc))
    result = subprocess.run(
        ["git", "-C", str(REPO), "hash-object", str(GATE)], capture_output=True, text=True,
    )
    if result.returncode:
        refuse(result.stderr or "git hash-object failed for gate.md")
    return result.stdout.strip(), commands


def validate_policy(value):
    if not isinstance(value, dict) or set(value) != {"schema", "max_parallel", "rulings"}:
        refuse("gate policy has an incomplete top-level shape")
    maximum = value.get("max_parallel")
    rulings = value.get("rulings")
    if value.get("schema") != 1:
        refuse("gate policy uses an unsupported schema")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        refuse("gate policy max_parallel must be one positive integer")
    if not isinstance(rulings, list):
        refuse("gate policy rulings must be one ordered list")
    identifiers = []
    decisions = []
    for number, ruling in enumerate(rulings, 1):
        if not isinstance(ruling, dict) or set(ruling) != {
            "id", "commands", "concern", "decision", "reason"
        }:
            refuse(f"gate policy ruling {number} has an incomplete shape")
        identifier = ruling.get("id")
        commands = ruling.get("commands")
        concern = ruling.get("concern")
        decision = ruling.get("decision")
        reason = ruling.get("reason")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
            refuse(f"gate policy ruling {number} has an invalid id")
        if not isinstance(commands, list) or len(commands) != 2 \
                or any(not isinstance(command, str) or not command for command in commands) \
                or commands != sorted(commands) or commands[0] == commands[1]:
            refuse(f"gate policy ruling {number} has no one canonical exact command pair")
        if not isinstance(concern, str) or not concern.strip() or concern != concern.strip() \
                or decision not in {"compatible", "incompatible"} \
                or not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            refuse(f"gate policy ruling {number} has invalid values")
        identifiers.append(identifier)
        decisions.append((tuple(commands), concern))
    if len(set(identifiers)) != len(identifiers):
        refuse("gate policy ruling ids must be unique")
    if len(set(decisions)) != len(decisions):
        refuse("gate policy cannot decide one exact command concern twice")
    return value


def default_policy():
    return {"schema": 1, "max_parallel": 1, "rulings": []}


def configured_policy():
    if not POLICY.exists() and not POLICY.is_symlink():
        return default_policy()
    regular_file(POLICY, "gate-policy.json")
    try:
        raw = POLICY.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"gate-policy.json is not complete JSON: {exc}")
    validate_policy(value)
    if canonical_bytes(value) != raw:
        refuse("gate-policy.json is not canonical")
    return value


def policy_snapshot(value=None):
    value = validate_policy(configured_policy() if value is None else value)
    raw = canonical_bytes(value)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "value": value}


def index_tree():
    return git_output("write-tree")


def trigger_path(value):
    if value == ".":
        return value
    if not isinstance(value, str) or not value or "\\" in value \
            or value.startswith("/") or posixpath.normpath(value) != value \
            or ".." in pathlib.PurePosixPath(value).parts:
        refuse("a compatibility trigger path must be one canonical repository-relative path")
    return value


def trigger_identity(tree, path):
    path = trigger_path(path)
    if path == ".":
        refuse("a compatibility trigger must name one exact file, not the repository root")
    result = subprocess.run(
        ["git", "-C", str(REPO), "--literal-pathspecs", "ls-tree", "-z", tree, "--", path],
        capture_output=True,
    )
    if result.returncode:
        refuse(f"compatibility trigger cannot inspect its staged path: {path}")
    if not result.stdout:
        return "ABSENT"
    if result.stdout.count(b"\0") != 1:
        refuse(f"compatibility trigger does not name one exact staged file: {path}")
    header, separator, listed = result.stdout[:-1].partition(b"\t")
    fields = header.split()
    try:
        listed_path = listed.decode("utf-8")
    except UnicodeDecodeError:
        refuse(f"compatibility trigger path is not UTF-8: {path}")
    if not separator or len(fields) != 3 or fields[1] != b"blob" or listed_path != path:
        refuse(f"compatibility trigger does not name one exact staged file: {path}")
    return hashlib.sha256(result.stdout).hexdigest()


def trigger_account(path, tree=None):
    tree = tree or index_tree()
    path = trigger_path(path)
    return {"path": path, "identity": trigger_identity(tree, path)}


def validate_trigger(item, number, tree=None):
    if not isinstance(item, dict) or set(item) != {"path", "identity", "reason"}:
        refuse(f"compatibility trigger {number} has an incomplete shape")
    path = trigger_path(item.get("path"))
    identity = item.get("identity")
    reason = item.get("reason")
    if path == "." or not isinstance(identity, str) \
            or (identity != "ABSENT" and not re.fullmatch(r"[0-9a-f]{64}", identity)) \
            or not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
        refuse(f"compatibility trigger {number} has invalid values")
    if tree is not None and trigger_identity(tree, path) != identity:
        refuse(f"compatibility trigger changed: {path}")
    return path


def policy_ruling(policy, identifier):
    return next((ruling for ruling in policy["rulings"] if ruling["id"] == identifier), None)


def pair_commands(commands, pair):
    return sorted((commands[pair[0] - 1], commands[pair[1] - 1]))


def validate_compatibility(items, groups, commands, policy, tree=None):
    if not isinstance(items, list):
        refuse("gate execution compatibility must be one ordered list")
    admissions = {}
    previous_pair = None
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != {
            "commands", "decision", "basis", "triggers"
        }:
            refuse(f"compatibility admission {number} has an incomplete shape")
        pair = item.get("commands")
        if not isinstance(pair, list) or len(pair) != 2 \
                or any(not isinstance(index, int) or isinstance(index, bool) for index in pair) \
                or pair[0] < 1 or pair[0] >= pair[1] or pair[1] > len(commands):
            refuse(f"compatibility admission {number} has no one exact command pair")
        pair = tuple(pair)
        if previous_pair is not None and pair <= previous_pair:
            refuse("compatibility admissions must be unique and ordered by command pair")
        previous_pair = pair
        if item.get("decision") != "compatible":
            refuse(f"compatibility admission {number} is not compatible")
        basis = item.get("basis")
        if not isinstance(basis, dict):
            refuse(f"compatibility admission {number} has no exact basis")
        command_pair = pair_commands(commands, pair)
        incompatible = [ruling for ruling in policy["rulings"]
                        if ruling["commands"] == command_pair
                        and ruling["decision"] == "incompatible"]
        if incompatible:
            refuse(f"human ruling {incompatible[0]['id']} forbids concurrent execution")
        if basis.get("kind") == "analysis":
            if set(basis) != {"kind", "probability", "reason"} \
                    or basis.get("probability") not in {"RARE", "EXCEPTIONAL"} \
                    or not isinstance(basis.get("reason"), str) \
                    or not basis["reason"].strip() or basis["reason"] != basis["reason"].strip():
                refuse("an analysis admission requires RARE or EXCEPTIONAL probability and a reason")
        elif basis.get("kind") == "human-ruling":
            if set(basis) != {"kind", "ruling", "concern"} \
                    or not isinstance(basis.get("ruling"), str) \
                    or not isinstance(basis.get("concern"), str):
                refuse(f"compatibility admission {number} has an invalid human ruling basis")
            ruling = policy_ruling(policy, basis["ruling"])
            if ruling is None:
                refuse(f"compatibility admission {number} names no policy ruling")
            if ruling["decision"] != "compatible" or ruling["commands"] != command_pair \
                    or ruling["concern"] != basis["concern"]:
                refuse(f"compatibility admission {number} does not match its human ruling")
        else:
            refuse(f"compatibility admission {number} has an unknown basis")
        triggers = item.get("triggers")
        if not isinstance(triggers, list):
            refuse(f"compatibility admission {number} has no trigger list")
        paths = [validate_trigger(trigger, trigger_number, tree)
                 for trigger_number, trigger in enumerate(triggers, 1)]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            refuse(f"compatibility admission {number} triggers must be unique and sorted")
        admissions[pair] = item

    shared_pairs = set()
    offset = 0
    for group in groups:
        positions = list(range(offset + 1, offset + len(group) + 1))
        shared_pairs.update((positions[left], positions[right])
                            for left in range(len(positions))
                            for right in range(left + 1, len(positions)))
        offset += len(group)
    for pair in sorted(shared_pairs - admissions.keys()):
        refuse(f"parallel commands {pair[0]} and {pair[1]} have no exact compatibility admission")
    extra = set(admissions) - shared_pairs
    if extra:
        pair = sorted(extra)[0]
        refuse(f"compatibility admission for commands {pair[0]} and {pair[1]} is not used by a shared group")
    return items


def validate_execution(value, gate_sha, commands, tree=None, current_policy=None):
    if not isinstance(value, dict) or set(value) != {
        "schema", "gate", "policy", "max_parallel", "compatible_groups", "compatibility"
    }:
        refuse("gate execution has an incomplete top-level shape")
    maximum = value.get("max_parallel")
    groups = value.get("compatible_groups")
    compatibility = value.get("compatibility")
    snapshot = value.get("policy")
    if value.get("schema") != 2 or value.get("gate") != gate_sha:
        refuse("gate execution belongs to another gate.md generation")
    if not isinstance(snapshot, dict) or set(snapshot) != {"sha256", "value"} \
            or not isinstance(snapshot.get("sha256"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"]):
        refuse("gate execution has no exact policy snapshot")
    frozen_policy = validate_policy(snapshot.get("value"))
    if policy_snapshot(frozen_policy) != snapshot:
        refuse("gate execution policy snapshot has another identity")
    if current_policy is not None and snapshot != policy_snapshot(current_policy):
        refuse("gate execution belongs to another workspace policy generation")
    if maximum != frozen_policy["max_parallel"]:
        refuse("gate execution max_parallel differs from its frozen policy")
    if not isinstance(groups, list) or not groups:
        refuse("compatible_groups must be one non-empty ordered partition")
    flattened = []
    for number, group in enumerate(groups, 1):
        if not isinstance(group, list) or not group \
                or any(not isinstance(command, str) or not command for command in group):
            refuse(f"compatible group {number} is not one non-empty command list")
        flattened.extend(group)
    if flattened != commands:
        refuse("compatible_groups omitted, reordered, added or changed a gate command")
    validate_compatibility(compatibility, groups, commands, frozen_policy, tree)
    return value


def legacy_evidence_path(value):
    if value == ".":
        return value
    if not isinstance(value, str) or not value or "\\" in value \
            or value.startswith("/") or posixpath.normpath(value) != value \
            or ".." in pathlib.PurePosixPath(value).parts:
        refuse("a legacy compatibility evidence path is not canonical")
    return value


def legacy_evidence_identity(tree, path):
    path = legacy_evidence_path(path)
    if path == ".":
        raw = f"040000 tree {tree}\t.\0".encode()
    else:
        result = subprocess.run(
            ["git", "-C", str(REPO), "ls-tree", "-z", tree, "--", path],
            capture_output=True,
        )
        if result.returncode or not result.stdout or result.stdout.count(b"\0") != 1:
            refuse(f"legacy compatibility evidence has no one exact Git object: {path}")
        raw = result.stdout
    return hashlib.sha256(raw).hexdigest()


def validate_legacy_execution(value, gate_sha, commands, tree):
    if not isinstance(value, dict) or set(value) != {
        "schema", "gate", "max_parallel", "compatible_groups", "compatibility_evidence"
    }:
        refuse("legacy gate execution has an incomplete top-level shape")
    maximum = value.get("max_parallel")
    groups = value.get("compatible_groups")
    evidence = value.get("compatibility_evidence")
    if value.get("schema") != 1 or value.get("gate") != gate_sha:
        refuse("legacy gate execution belongs to another gate.md generation")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        refuse("legacy max_parallel must be one positive integer")
    if not isinstance(groups, list) or not groups:
        refuse("legacy compatible_groups must be one non-empty ordered partition")
    flattened = []
    for number, group in enumerate(groups, 1):
        if not isinstance(group, list) or not group \
                or any(not isinstance(command, str) or not command for command in group):
            refuse(f"legacy compatible group {number} is not one non-empty command list")
        flattened.extend(group)
    if flattened != commands:
        refuse("legacy compatible_groups omitted, reordered, added or changed a gate command")
    if not isinstance(evidence, list):
        refuse("legacy compatibility_evidence must be one complete ordered list")
    paths = []
    for number, item in enumerate(evidence, 1):
        if not isinstance(item, dict) or set(item) != {"path", "identity"} \
                or not isinstance(item.get("identity"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", item["identity"]):
            refuse(f"legacy compatibility evidence item {number} has an invalid shape")
        paths.append(legacy_evidence_path(item.get("path")))
    if len(set(paths)) != len(paths) or paths != sorted(paths):
        refuse("legacy compatibility evidence paths must be unique and sorted")
    if any(len(group) > 1 for group in groups) and not evidence:
        refuse("a legacy parallel compatible group requires explicit project evidence")
    current_evidence = [
        {"path": path, "identity": legacy_evidence_identity(tree, path)} for path in paths
    ]
    if evidence != current_evidence:
        changed = [expected["path"] for expected, current in zip(evidence, current_evidence)
                   if expected != current]
        refuse("project evidence for parallel gate compatibility changed: "
               + ", ".join(changed))
    return value


def validate_frozen_execution(value, gate_sha, commands, tree):
    if isinstance(value, dict) and value.get("schema") == 1:
        return validate_legacy_execution(value, gate_sha, commands, tree)
    return validate_execution(value, gate_sha, commands, tree)


def default_execution(gate_sha, commands, policy=None):
    policy = policy or configured_policy()
    return {
        "schema": 2,
        "gate": gate_sha,
        "policy": policy_snapshot(policy),
        "max_parallel": policy["max_parallel"],
        "compatible_groups": [[command] for command in commands],
        "compatibility": [],
    }


def configured_execution():
    gate_sha, commands = gate_state()
    policy = configured_policy()
    if not CONFIG.exists() and not CONFIG.is_symlink():
        return default_execution(gate_sha, commands, policy)
    regular_file(CONFIG, "gate-execution.json")
    try:
        raw = CONFIG.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"gate-execution.json is not complete JSON: {exc}")
    if canonical_bytes(value) != raw:
        refuse("gate-execution.json is not canonical")
    return validate_execution(value, gate_sha, commands, index_tree(), policy)


def encode_execution(execution):
    raw = canonical_bytes(execution)
    return {
        "execution": execution,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "token": base64.urlsafe_b64encode(raw).decode("ascii"),
    }


def decode_execution(token, expected_gate=None, expected_tree=None):
    try:
        raw = base64.b64decode(token.encode("ascii"), altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"the frozen gate execution token is malformed: {exc}")
    gate_sha, commands = gate_state()
    if expected_gate is not None and gate_sha != expected_gate:
        refuse("the living gate.md differs from the frozen gate identity")
    validate_execution(value, gate_sha, commands, expected_tree or index_tree())
    if canonical_bytes(value) != raw:
        refuse("the frozen gate execution is not canonical")
    return value, hashlib.sha256(raw).hexdigest()


def read_marker_file(path, subject, *, execution):
    lines = regular_file(path, subject).read_text(encoding="utf-8").splitlines()
    marker = {}
    for line in lines:
        key, separator, value = line.partition(" ")
        if not separator or not value or key in marker:
            refuse(f"{subject} is malformed")
        marker[key] = value
    expected = set(MARKER_KEYS)
    correction_draft = expected | {"correction"}
    correction_baseline = correction_draft | set(CORRECTION_AUTHORITY_KEYS)
    correction_attempt = correction_draft | set(CORRECTION_ATTEMPT_AUTHORITY_KEYS)
    allowed = (
        (
            expected, expected | {"execution"},
            correction_baseline, correction_baseline | {"execution"},
            correction_attempt, correction_attempt | {"execution"},
        )
        if execution else (expected, correction_draft, correction_baseline, correction_attempt)
    )
    if set(marker) not in allowed:
        refuse(f"{subject} has an incomplete identity")
    if not re.fullmatch(r"[0-9a-f]{64}", marker["op"]) \
            or marker["scope"] not in {"task", "baseline", "review", *CORRECTION_SCOPES} \
            or not re.fullmatch(r"[A-Za-z0-9._:/-]+", marker["owner"]) \
            or not re.fullmatch(r"(?:-|lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?)", marker["lot"]) \
            or not re.fullmatch(r"[0-9]+", marker["task"]) \
            or not re.fullmatch(r"[0-9]+", marker["attempt"]) \
            or any(not re.fullmatch(r"[0-9a-f]{40,64}", marker[key])
                   for key in ("head", "base", "tree", "gate")):
        refuse(f"{subject} has an invalid identity")
    if marker["scope"] in CORRECTION_SCOPES:
        if not re.fullmatch(r"[1-9][0-9]*", marker.get("correction", "")):
            refuse(f"{subject} has no correction-round identity")
        required_authority = CORRECTION_AUTHORITY_KEYS \
            if marker["scope"] == "correction-baseline" \
            else CORRECTION_ATTEMPT_AUTHORITY_KEYS
        if (execution or any(key in marker for key in required_authority)) \
                and any(not re.fullmatch(r"[0-9a-f]{64}", marker.get(key, ""))
                        for key in required_authority):
            refuse(f"{subject} has no complete correction authority")
    elif "correction" in marker:
        refuse(f"{subject} carries a correction round for an ordinary scope")
    if "execution" in marker and not marker["execution"]:
        refuse(f"{subject} has an empty execution token")
    return marker


def marker_data(op=None):
    marker = read_marker_file(MARKER, "the gate-check marker", execution=True)
    if op is not None and marker["op"] != op:
        refuse(f"the gate-check marker belongs to {marker['op']}, not {op}")
    return marker


def frozen_execution(op):
    marker = marker_data(op)
    token = marker.get("execution")
    if token is None:
        gate_sha, commands = gate_state()
        execution = default_execution(gate_sha, commands)
        return marker, execution, "-"
    execution, execution_hash = decode_execution(token, marker["gate"], marker["tree"])
    return marker, execution, execution_hash


def git_output(*arguments):
    result = subprocess.run(
        ["git", "-C", str(REPO), *arguments], capture_output=True, text=True,
    )
    if result.returncode:
        refuse(result.stderr or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def verify_frozen(marker):
    gate_sha, _ = gate_state()
    if gate_sha != marker["gate"]:
        refuse("gate.md changed during the logical gate operation")
    if git_output("rev-parse", "HEAD") != marker["head"]:
        refuse("HEAD changed during the logical gate operation")
    if git_output("write-tree") != marker["tree"]:
        refuse("the staged candidate changed during the logical gate operation")
    unstaged = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--quiet", "--exit-code"], capture_output=True,
    )
    if unstaged.returncode != 0:
        refuse("the gate operation has unstaged tracked changes")
    untracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
    )
    if untracked.returncode != 0 or untracked.stdout:
        refuse("the gate operation has untracked paths")
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain=v1", "-z"], capture_output=True,
    )
    if status.returncode:
        refuse(status.stderr.decode("utf-8", "replace") or "git status failed")
    return status.stdout


def ensure_report_ground():
    current = WORKSPACE
    for part in ("reports", "gate"):
        current /= part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                refuse(f"the gate report ground is not one real directory: {current}")
        else:
            current.mkdir()


def atomic_publish(target, payload, *, replace=False):
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            if target.exists() or target.is_symlink():
                regular_file(target, target.name)
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
                    refuse(f"{target.name} already exists with different or foreign bytes")
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def gate_authority():
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(AUTHORITY_LOCK, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            refuse("the gate authority lock is not one real regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def refuse_live_marker(action):
    if MARKER.exists() or MARKER.is_symlink():
        refuse(f"finish or abandon the live gate operation before {action}")


def correction_attempt_authority(marker):
    context = {
        "lot": marker["lot"],
        "correction": int(marker["correction"]),
        "task": int(marker["task"]),
        "attempt": int(marker["attempt"]),
    }
    identity = progress.active_attempt_identity(
        context, "the correction gate admission", include_completion=True,
    )
    with WorkspaceFileAnchor(
        WORKSPACE, "attempt-in-flight", "the correction gate attempt owner",
    ) as anchored:
        attempt_payload = anchored.read_regular()
    return {
        "contract_authority_sha256": identity["unit_authority_sha256"],
        "execution_authority_sha256": identity["execution_authority_sha256"],
        "final_checker_set_sha256": identity[
            "outstanding_final_checker_set_sha256"
        ],
        "attempt_marker_sha256": hashlib.sha256(attempt_payload).hexdigest(),
    }


def current_correction_owner_markers():
    return [
        name for name in sorted(CORRECTION_OWNER_MARKERS)
        if os.path.lexists(WORKSPACE / name)
    ]


def correction_baseline_owner(marker, entries, living_markers):
    from correction_round_baseline import (  # noqa: E402
        exact_opening,
        pending_final_checker_map,
        pending_revision,
        pending_rewind,
    )

    args = SimpleNamespace(
        built=marker["lot"], correction=int(marker["correction"]),
        round=int(marker["correction"]),
    )
    _opening_entries, opening, _close = exact_opening(args)
    if not living_markers:
        expected_owner = f"correction/{args.built}/c{args.round}/{opening['base_commit']}"
        if marker["owner"] != expected_owner \
                or marker["head"] != opening["base_commit"] \
                or marker["base"] != opening["base_commit"]:
            refuse("the correction base gate changes its frozen opening authority")
        return

    name = living_markers[0]
    if name == "correction-rewind-in-progress":
        account = pending_rewind(args, entries)
        if account is None:
            refuse("the correction baseline has no exact pending rewind owner")
        expected_owner = account["baseline_owner"]
        expected_commit = account["event_base"]["result_commit"]
    elif name == "final-checker-contract-map-in-progress":
        account = pending_final_checker_map(args, entries)
        if account is None:
            refuse("the correction baseline has no exact pending final-checker map owner")
        expected_owner = account["baseline_owner"]
        expected_commit = account["commit"]
    else:
        account = pending_revision(args, entries, opening)
        if account is None:
            refuse("the correction baseline has no exact pending revision owner")
        expected_owner = account["baseline_owner"]
        expected_commit = account["commit"]
    if marker["owner"] != expected_owner \
            or marker["head"] != expected_commit or marker["base"] != expected_commit:
        refuse("the correction baseline changes its pending transition owner")


def validate_correction_gate_owner(marker, entries):
    progress.require_no_current_correction_stop(
        entries, len(entries), marker["lot"], int(marker["correction"]),
        "the correction gate admission",
    )
    living = current_correction_owner_markers()
    return_baseline = marker["scope"] == "correction-baseline" \
        and living and all(name in {
            "correction-rewind-in-progress",
            "correction-amendment-return-in-progress",
        } for name in living)
    if not return_baseline:
        progress.require_no_active_correction_amendment(
            entries, len(entries), marker["lot"], int(marker["correction"]),
            "the correction gate admission",
        )
    if marker["scope"] != "correction-baseline":
        if living:
            refuse(f"the correction gate follows unfinished owner {living[0]}")
        return
    foreign = [name for name in living if name not in CORRECTION_BASELINE_OWNER_MARKERS]
    if foreign:
        refuse(f"the correction baseline follows unfinished owner {foreign[0]}")
    if len(living) > 1:
        refuse("the correction baseline has several pending transition owners")
    correction_baseline_owner(marker, entries, living)


def correction_baseline_authority(marker):
    entries = progress.journal_entries()
    built = marker["lot"]
    correction = int(marker["correction"])
    validate_correction_gate_owner(marker, entries)
    state = progress.current_correction_contract_state(
        entries, len(entries), built, correction, "the correction baseline gate",
    )
    current_set = progress.outstanding_final_checker_set(
        entries, len(entries), built, correction, "the correction baseline gate",
    )
    if marker["task"] != "0" or marker["attempt"] != "0":
        refuse("the correction baseline gate changes its current execution authority")
    return {
        "contract_authority_sha256": state["authority_sha256"],
        "execution_authority_sha256": state["execution_authority_sha256"],
        "final_checker_set_sha256": progress.final_checker_set_sha256(current_set),
    }


def correction_escalation_gate_lot(marker, entries):
    lot = marker["lot"] if marker["scope"] in {"task", "review"} else None
    if marker["scope"] == "baseline":
        match = re.fullmatch(
            r"plan/(lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?)/([0-9a-f]{40,64})",
            marker["owner"],
        )
        if match is not None and match.group(2) == marker["head"]:
            lot = match.group(1)
        if lot is None:
            candidates = []
            for entry in entries:
                data = progress.note_data(entry)
                candidate_lot = entry.get("lot")
                if entry.get("kind") == "plan.written" \
                        and data.get("schema") == 2 \
                        and data.get("origin") == "correction-round" \
                        and data.get("commit") == marker["head"] \
                        and progress.correction_escalation_plan_origin(entries, candidate_lot):
                    candidates.append(candidate_lot)
            if len(set(candidates)) == 1:
                lot = candidates[0]
    if lot is None or not progress.correction_escalation_plan_origin(entries, lot):
        return None
    return lot


def validate_correction_escalation_gate(marker, entries, lot):
    progress.require_no_open_correction_escalation_c2(
        entries, len(entries), lot, "the Correction escalation gate admission",
    )
    if marker["scope"] != "baseline":
        return
    progress.correction_escalation_require_quiescent(
        entries, len(entries), lot, "the Correction escalation C2.7 baseline",
        live=True,
    )
    clean_c2 = progress.correction_escalation_clean_c2_account(
        entries, len(entries), lot, "the Correction escalation C2.7 baseline",
    )
    commit = clean_c2["plan_account"]["commit"]
    parent = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"{commit}^"],
        capture_output=True, text=True,
    )
    if marker["owner"] != f"plan/{lot}/{commit}" \
            or marker["head"] != commit or parent.returncode != 0 \
            or marker["base"] != parent.stdout.strip():
        refuse("the Correction escalation baseline changes its plan or predecessor authority")


def gate_event_data(marker, execution_hash):
    data = {
        key: marker[key] for key in MARKER_KEYS
    }
    data["task"] = int(data["task"])
    data["attempt"] = int(data["attempt"])
    if "correction" in marker:
        data["correction"] = int(marker["correction"])
    data.update({
        key: marker[key] for key in CORRECTION_ATTEMPT_AUTHORITY_KEYS if key in marker
    })
    data["execution"] = execution_hash
    return data


def gate_started_args(data):
    return SimpleNamespace(
        kind="gate-runner", mandate=None, task=None, round=None,
        data=json.dumps(data, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def correction_gate_start(marker, execution_hash, lease, operation):
    data = gate_event_data(marker, execution_hash)
    entries = progress.journal_entries()
    starts = [
        entry for entry in entries
        if entry.get("event") == "subagent-started"
        and entry.get("kind") == "gate-runner"
        and progress.note_data(entry).get("op") == marker["op"]
    ]
    ends = [
        entry for entry in entries
        if entry.get("event") == "subagent-ended"
        and entry.get("kind") == "gate-runner"
        and progress.note_data(entry).get("op") == marker["op"]
    ]
    completed = [entry for entry in ends if "unusable" not in progress.note_data(entry)]
    if len(starts) > 2 or len(ends) > 2 or len(ends) > len(starts) \
            or len(starts) - len(ends) > 1 or completed:
        refuse("the correction gate has malformed durable physical-call brackets")
    if any(progress.note_data(entry) != data for entry in starts):
        refuse("the correction gate start changes its durable authority")
    for entry in ends:
        terminal = progress.note_data(entry)
        if any(terminal.get(key) != value for key, value in data.items()) \
                or terminal.get("unusable") not in {"lost", "unusable"}:
            refuse("the correction gate has a foreign physical-call terminal")
    if len(starts) > len(ends):
        return
    if len(starts) == 2:
        refuse("the correction gate exhausted its one physical replacement")
    progress.cmd_subagent_started(
        gate_started_args(data),
        correction_lease=lease,
        correction_operation=operation,
    )


def gate_ended_args(data):
    return SimpleNamespace(
        kind="gate-runner", mandate=None, task=None, round=None,
        data=json.dumps(data, sort_keys=True, separators=(",", ":")),
        mode=None, lot=None, job=None, attempt=None,
    )


def correction_gate_terminal(op, outcome):
    operation = f"correction-gate-terminal:{validate_op(op)}"
    with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
        with gate_authority():
            with WorkspaceFileAnchor(
                WORKSPACE, "gate-check-in-progress", "the correction gate owner",
            ) as anchored:
                marker_payload = anchored.read_regular()
                marker = marker_data(op)
                if marker["scope"] not in CORRECTION_SCOPES:
                    refuse("the correction gate terminal names an ordinary gate")
                expected = correction_baseline_authority(marker) \
                    if marker["scope"] == "correction-baseline" \
                    else correction_attempt_authority(marker)
                if any(marker.get(key) != value for key, value in expected.items()):
                    refuse("the correction gate terminal changes its frozen authority")
                token = marker.get("execution")
                if token is None:
                    execution_hash = "-"
                else:
                    _, execution_hash = decode_execution(
                        token, marker["gate"], marker["tree"],
                    )
                opening_data = gate_event_data(marker, execution_hash)
                data = dict(opening_data)
                if outcome == "lost":
                    data["unusable"] = "lost"
                elif outcome == "unusable":
                    data["unusable"] = "unusable"
                else:
                    try:
                        report = json.loads(outcome)
                    except ValueError as exc:
                        refuse(f"the correction gate report is not JSON: {exc}")
                    if not isinstance(report, dict) or set(report) != {
                        "green", "surface", "report", "report_sha256", "commands",
                    }:
                        refuse("the correction gate report has an invalid result shape")
                    data.update(report)
                    verify_frozen(marker)
                entries = progress.journal_entries()
                starts = [
                    entry for entry in entries
                    if entry.get("event") == "subagent-started"
                    and entry.get("kind") == "gate-runner"
                    and progress.note_data(entry).get("op") == op
                ]
                ends = [
                    entry for entry in entries
                    if entry.get("event") == "subagent-ended"
                    and entry.get("kind") == "gate-runner"
                    and progress.note_data(entry).get("op") == op
                ]
                completed = [
                    entry for entry in ends
                    if "unusable" not in progress.note_data(entry)
                ]
                if len(starts) not in {1, 2} or len(ends) > 2 \
                        or len(ends) > len(starts) or len(starts) - len(ends) > 1 \
                        or len(completed) > 1:
                    refuse("the correction gate has malformed durable physical-call brackets")
                if any(progress.note_data(entry) != opening_data for entry in starts):
                    refuse("the correction gate terminal changes its opening authority")
                matching = [entry for entry in ends if progress.note_data(entry) == data]
                if completed:
                    if outcome in {"lost", "unusable"} or len(matching) != 1:
                        refuse("the correction gate terminal changes its durable result")
                else:
                    if len(starts) != len(ends) + 1:
                        refuse("the correction gate terminal has no open physical owner")
                    progress.cmd_subagent_ended(
                        gate_ended_args(data),
                        correction_lease=lease,
                        correction_operation=operation,
                    )
                if outcome != "lost":
                    anchored.remove_exact(hashlib.sha256(marker_payload).hexdigest())


def open_marker(source):
    source = pathlib.Path(source)
    if not source.is_absolute():
        refuse("the gate marker draft path must be absolute")
    source = workspace_file(source, "the gate marker draft")
    marker = read_marker_file(source, "the gate marker draft", execution=False)
    if marker["scope"] == "baseline":
        if (marker["lot"], marker["task"], marker["attempt"], marker["code"]) != ("-", "0", "0", "-"):
            refuse("the gate marker draft has an invalid baseline identity")
    elif marker["scope"] == "correction-baseline":
        if marker["lot"] == "-" or (marker["task"], marker["attempt"], marker["code"]) \
                != ("0", "0", "-"):
            refuse("the gate marker draft has an invalid correction baseline identity")
    elif marker["lot"] == "-" or marker["task"] == "0" or marker["attempt"] == "0":
        refuse("the gate marker draft has an invalid task identity")
    if marker["scope"] in {"task", "correction-task"}:
        if not re.fullmatch(r"[0-9]+:[0-9a-f]{64}", marker["code"]):
            refuse("the gate marker draft has no final code-review proof")
    elif marker["code"] != "-":
        refuse("the gate marker draft carries an invalid code-review proof")
    if marker["scope"] in CORRECTION_SCOPES:
        operation = f"correction-gate:{marker['op']}"
        with CorrectionAuthorityLease.acquire(WORKSPACE, operation) as lease:
            if marker["scope"] == "correction-baseline":
                authority = correction_baseline_authority(marker)
            else:
                entries = progress.journal_entries()
                validate_correction_gate_owner(marker, entries)
                authority = correction_attempt_authority(marker)
            marker.update(authority)
            with gate_authority():
                verify_frozen(marker)
                encoded = encode_execution(configured_execution())
                payload = "".join(f"{key} {marker[key]}\n" for key in MARKER_KEYS)
                payload += f"correction {marker['correction']}\n"
                payload += "".join(
                    f"{key} {marker[key]}\n"
                    for key in CORRECTION_ATTEMPT_AUTHORITY_KEYS if key in marker
                )
                payload += f"execution {encoded['token']}\n"
                if MARKER.exists() or MARKER.is_symlink():
                    current = marker_data(marker["op"])
                    if any(current.get(key) != marker.get(key)
                           for key in (
                               *MARKER_KEYS, "correction", *CORRECTION_ATTEMPT_AUTHORITY_KEYS,
                           )):
                        refuse("the live correction gate belongs to another authority")
                else:
                    atomic_publish(MARKER, payload.encode(), replace=False)
                correction_gate_start(
                    marker, encoded["sha256"], lease, operation,
                )
    else:
        entries = progress.journal_entries()
        escalation_lot = correction_escalation_gate_lot(marker, entries)

        def publish_ordinary():
            nonlocal encoded
            with gate_authority():
                refuse_live_marker("opening another gate")
                verify_frozen(marker)
                encoded = encode_execution(configured_execution())
                payload = "".join(f"{key} {marker[key]}\n" for key in MARKER_KEYS)
                payload += f"execution {encoded['token']}\n"
                atomic_publish(MARKER, payload.encode(), replace=False)

        encoded = None
        if escalation_lot is None:
            publish_ordinary()
        else:
            operation = f"correction-escalation-gate:{marker['op']}"
            try:
                with CorrectionAuthorityLease.acquire(WORKSPACE, operation):
                    entries = progress.journal_entries()
                    validate_correction_escalation_gate(marker, entries, escalation_lot)
                    publish_ordinary()
            except (OSError, ValueError) as exc:
                refuse(f"the Correction escalation gate lease failed: {exc}")
    print(f"FROZEN {encoded['sha256']}")


def publish_policy(source):
    source = pathlib.Path(source)
    if not source.is_absolute():
        refuse("the gate policy draft path must be absolute")
    source = regular_file(source, "the gate policy draft")
    try:
        value = json.loads(source.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"the gate policy draft is not complete JSON: {exc}")
    validate_policy(value)
    with gate_authority():
        refuse_live_marker("changing gate policy")
        atomic_publish(POLICY, canonical_bytes(value), replace=True)
    print(f"PUBLISHED {POLICY}")


def schedule_from_draft(value, policy):
    if not isinstance(value, dict) or set(value) != {
        "schema", "gate", "compatible_groups", "compatibility"
    }:
        refuse("the gate execution draft has an incomplete top-level shape")
    return {
        "schema": value.get("schema"),
        "gate": value.get("gate"),
        "policy": policy_snapshot(policy),
        "max_parallel": policy["max_parallel"],
        "compatible_groups": value.get("compatible_groups"),
        "compatibility": value.get("compatibility"),
    }


def publish(source):
    source = pathlib.Path(source)
    if not source.is_absolute():
        refuse("the gate execution draft path must be absolute")
    source = regular_file(source, "the gate execution draft")
    try:
        value = json.loads(source.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"the gate execution draft is not complete JSON: {exc}")
    with gate_authority():
        refuse_live_marker("changing gate execution")
        gate_sha, commands = gate_state()
        policy = configured_policy()
        execution = schedule_from_draft(value, policy)
        validate_execution(execution, gate_sha, commands, index_tree(), policy)
        atomic_publish(CONFIG, canonical_bytes(execution), replace=True)
    print(f"PUBLISHED {CONFIG}")


def remove():
    with gate_authority():
        refuse_live_marker("removing gate execution")
        if not CONFIG.exists() and not CONFIG.is_symlink():
            print("ABSENT gate-execution.json")
            return
        regular_file(CONFIG, "gate-execution.json").unlink()
    print("REMOVED gate-execution.json; future gates default to sequential execution")


def account_path(op):
    return REPORT_GROUND / f"{op}.commands"


def account_manifest(directory):
    return directory / "account.json"


def command_output(directory, number):
    return directory / f"{number}.output"


def validate_op(op):
    if not re.fullmatch(r"[0-9a-f]{64}", op):
        refuse("the operation identity is malformed")
    return op


@contextlib.contextmanager
def execution_lock(op, *, blocking=True, busy_message=None):
    validate_op(op)
    ensure_report_ground()
    path = REPORT_GROUND / f"{op}.execution.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            refuse("the gate executor lock is not one real regular file")
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(descriptor, operation)
        except BlockingIOError:
            refuse(busy_message or "the exact gate executor or one of its command processes is still live")
        yield descriptor
    finally:
        # Do not call LOCK_UN here. Active commands inherit this open-file
        # description. Closing only our descriptor keeps ownership alive until
        # the last inherited descriptor closes, including on a partial launch.
        os.close(descriptor)


def assert_idle(op):
    with execution_lock(op, blocking=False):
        pass
    print(f"IDLE {op}")


def validate_account(value, op, execution_hash, commands, directory=None):
    if not isinstance(value, dict) or set(value) != {"schema", "op", "execution", "commands"} \
            or value.get("schema") != 2 or value.get("op") != op \
            or value.get("execution") != execution_hash:
        refuse("the gate command account belongs to another execution")
    results = value.get("commands")
    if not isinstance(results, list) or len(results) != len(commands):
        refuse("the gate command account has no one result per command")
    for number, (result, command) in enumerate(zip(results, commands), 1):
        if not isinstance(result, dict) or set(result) != {
            "command", "returncode", "output_sha256", "output_bytes", "output_chunk_bytes",
            "output_chunks", "example"
        }:
            refuse(f"gate command account item {number} has an invalid shape")
        if result.get("command") != command \
                or not isinstance(result.get("returncode"), int) \
                or isinstance(result.get("returncode"), bool) \
                or not re.fullmatch(r"[0-9a-f]{64}", result.get("output_sha256", "")) \
                or not isinstance(result.get("output_bytes"), int) \
                or isinstance(result.get("output_bytes"), bool) or result["output_bytes"] < 0 \
                or result.get("output_chunk_bytes") != OUTPUT_CHUNK_BYTES \
                or not isinstance(result.get("output_chunks"), list) \
                or any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                       for digest in result["output_chunks"]) \
                or not isinstance(result.get("example"), str) or not result["example"]:
            refuse(f"gate command account item {number} has invalid values")
        expected_chunks = (result["output_bytes"] + OUTPUT_CHUNK_BYTES - 1) // OUTPUT_CHUNK_BYTES
        if len(result["output_chunks"]) != expected_chunks:
            refuse(f"gate command account item {number} has an invalid chunk account")
    if directory is not None:
        expected_names = {"account.json"} | {
            f"{number}.output" for number in range(1, len(commands) + 1)
        }
        try:
            names = {entry.name for entry in directory.iterdir()}
        except OSError as exc:
            refuse(f"the gate command account directory is unreadable: {exc}")
        if names != expected_names:
            refuse("the gate command account has missing, added or reordered output artifacts")
        for number, result in enumerate(results, 1):
            path = regular_file(command_output(directory, number), f"gate command output {number}")
            if path.stat().st_size != result["output_bytes"]:
                refuse(f"gate command output {number} has a partial or changed size")
    return value


def output_descriptor(path, expected_size, subject):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    state = os.fstat(descriptor)
    if not stat.S_ISREG(state.st_mode) or state.st_size != expected_size:
        os.close(descriptor)
        refuse(f"{subject} is missing, partial, aliased or changed")
    return descriptor, state


def descriptor_identity(state):
    return (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns, state.st_ctime_ns)


def finish_output_read(descriptor, path, before, subject):
    after = os.fstat(descriptor)
    try:
        living = os.stat(path, follow_symlinks=False)
    except OSError:
        refuse(f"{subject} changed during authentication")
    if descriptor_identity(after) != descriptor_identity(before) \
            or not stat.S_ISREG(living.st_mode) \
            or (living.st_dev, living.st_ino) != (after.st_dev, after.st_ino):
        refuse(f"{subject} changed during authentication")


def authenticate_output(path, result, number):
    subject = f"gate command output {number}"
    descriptor, before = output_descriptor(path, result["output_bytes"], subject)
    whole = hashlib.sha256()
    try:
        for chunk_number, expected in enumerate(result["output_chunks"]):
            offset = chunk_number * OUTPUT_CHUNK_BYTES
            wanted = min(OUTPUT_CHUNK_BYTES, result["output_bytes"] - offset)
            raw = os.pread(descriptor, wanted, offset)
            if len(raw) != wanted or hashlib.sha256(raw).hexdigest() != expected:
                refuse(f"{subject} chunk {chunk_number + 1} changed")
            whole.update(raw)
        if whole.hexdigest() != result["output_sha256"]:
            refuse(f"{subject} does not match its complete hash")
        finish_output_read(descriptor, path, before, subject)
    finally:
        os.close(descriptor)


def read_account(op, execution_hash, commands, *, authenticate_outputs=False):
    directory = workspace_directory(account_path(op), "the gate command account")
    path = workspace_file(account_manifest(directory), "the gate command account manifest")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        refuse(f"the gate command account is not complete JSON: {exc}")
    validate_account(value, op, execution_hash, commands, directory)
    if canonical_bytes(value) != raw:
        refuse("the gate command account is not canonical")
    if authenticate_outputs:
        for number, result in enumerate(value["commands"], 1):
            authenticate_output(command_output(directory, number), result, number)
    return value, hashlib.sha256(raw).hexdigest()


def print_result(number, result):
    print(
        f"COMMAND {number} exit={result['returncode']} bytes={result['output_bytes']} "
        f"sha256={result['output_sha256']} example={json.dumps(result['example'])}"
    )


def account_state(op):
    validate_op(op)
    _, execution, execution_hash = frozen_execution(op)
    commands = [item for group in execution["compatible_groups"] for item in group]
    target = account_path(op)
    if not target.exists() and not target.is_symlink():
        with execution_lock(
            op,
            blocking=False,
            busy_message=(
                "gate command execution is still active; wait for its terminal result "
                "before inspecting the account"
            ),
        ):
            if not target.exists() and not target.is_symlink():
                refuse("gate command execution is idle but no complete account exists")
    account, account_hash = read_account(op, execution_hash, commands)
    return execution, execution_hash, account, account_hash


def result_item(op, item):
    _, _, account, _ = account_state(op)
    if not re.fullmatch(r"[1-9][0-9]*", item) or int(item) > len(account["commands"]):
        refuse("the gate command result item is outside the frozen account")
    result = dict(account["commands"][int(item) - 1])
    del result["output_chunks"]
    del result["output_chunk_bytes"]
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


def output_chunk(op, item, offset, length):
    _, _, account, _ = account_state(op)
    if not re.fullmatch(r"[1-9][0-9]*", item) or int(item) > len(account["commands"]):
        refuse("the gate command output item is outside the frozen account")
    if not re.fullmatch(r"0|[1-9][0-9]*", offset) \
            or not re.fullmatch(r"[1-9][0-9]*", length) or int(length) > 65536:
        refuse("output requires a non-negative offset and a length from 1 through 65536")
    number = int(item)
    result = account["commands"][number - 1]
    total = result["output_bytes"]
    start = int(offset)
    if start > total:
        refuse("the gate command output offset is past the exact output")
    end = min(total, start + int(length))
    path = command_output(account_path(op), number)
    subject = f"gate command output {number}"
    descriptor, before = output_descriptor(path, total, subject)
    chunk = bytearray()
    try:
        if start < end:
            first = start // OUTPUT_CHUNK_BYTES
            last = (end - 1) // OUTPUT_CHUNK_BYTES
            for chunk_number in range(first, last + 1):
                chunk_start = chunk_number * OUTPUT_CHUNK_BYTES
                wanted = min(OUTPUT_CHUNK_BYTES, total - chunk_start)
                raw = os.pread(descriptor, wanted, chunk_start)
                if len(raw) != wanted \
                        or hashlib.sha256(raw).hexdigest() != result["output_chunks"][chunk_number]:
                    refuse(f"{subject} chunk {chunk_number + 1} changed")
                left = max(start, chunk_start) - chunk_start
                right = min(end, chunk_start + wanted) - chunk_start
                chunk.extend(raw[left:right])
        finish_output_read(descriptor, path, before, subject)
    finally:
        os.close(descriptor)
    following = start + len(chunk)
    print(json.dumps({
        "offset": start,
        "bytes": len(chunk),
        "next": following,
        "done": following == total,
        "data": base64.b64encode(chunk).decode("ascii"),
    }, separators=(",", ":"), sort_keys=True))


def output_metadata(path, command, returncode):
    whole = hashlib.sha256()
    chunks = []
    size = 0
    preview = bytearray()
    with path.open("rb") as source:
        while True:
            raw = source.read(OUTPUT_CHUNK_BYTES)
            if not raw:
                break
            whole.update(raw)
            chunks.append(hashlib.sha256(raw).hexdigest())
            size += len(raw)
            if len(preview) < OUTPUT_CHUNK_BYTES:
                preview.extend(raw[:OUTPUT_CHUNK_BYTES - len(preview)])
    text = preview.decode("utf-8", "replace")
    example = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return {
        "command": command,
        "returncode": returncode,
        "output_sha256": whole.hexdigest(),
        "output_bytes": size,
        "output_chunk_bytes": OUTPUT_CHUNK_BYTES,
        "output_chunks": chunks,
        "example": example[:300] or f"exit {returncode}",
    }


def publish_account_directory(stage, target, account, op, execution_hash, commands):
    payload = canonical_bytes(account)
    manifest = account_manifest(stage)
    with manifest.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    validate_account(account, op, execution_hash, commands, stage)
    for number, result in enumerate(account["commands"], 1):
        authenticate_output(command_output(stage, number), result, number)
    descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if target.exists() or target.is_symlink():
        refuse("the gate command account final path is already occupied")
    os.rename(stage, target)
    descriptor = os.open(REPORT_GROUND, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_owned_commands(op, lock_descriptor):
    marker, execution, execution_hash = frozen_execution(op)
    commands = [command for group in execution["compatible_groups"] for command in group]
    before = verify_frozen(marker)
    if account_path(op).exists() or account_path(op).is_symlink():
        account, _ = read_account(op, execution_hash, commands, authenticate_outputs=True)
        for number, result in enumerate(account["commands"], 1):
            print_result(number, result)
        print(f"GATE COMMAND ACCOUNT {op} (already recorded)")
        return account

    ensure_report_ground()
    stage = pathlib.Path(tempfile.mkdtemp(prefix=f".{op}.commands.", dir=REPORT_GROUND))
    published = False
    try:
        results = []
        command_number = 0
        maximum = execution["max_parallel"]
        for group in execution["compatible_groups"]:
            for offset in range(0, len(group), maximum):
                wave = group[offset:offset + maximum]
                if verify_frozen(marker) != before:
                    refuse("the repository state changed before a parallel gate group")
                running = []
                for command in wave:
                    number = command_number + len(running) + 1
                    output_path = command_output(stage, number)
                    output = output_path.open("w+b")
                    try:
                        process = subprocess.Popen(
                            ["bash", "-c", command], cwd=REPO, stdout=output,
                            stderr=subprocess.STDOUT, pass_fds=(lock_descriptor,),
                        )
                    except Exception:
                        output.close()
                        for _, _, _, active_output in running:
                            active_output.close()
                        raise
                    running.append((number, command, process, output))
                completed = []
                for number, command, process, output in running:
                    returncode = process.wait()
                    output.flush()
                    os.fsync(output.fileno())
                    output.close()
                    completed.append((number, command, returncode))
                if verify_frozen(marker) != before:
                    refuse("a parallel gate group changed the candidate or repository state")
                for number, command, returncode in completed:
                    command_number += 1
                    result = output_metadata(command_output(stage, number), command, returncode)
                    results.append(result)
                    print_result(command_number, result)

        account = {"schema": 2, "op": op, "execution": execution_hash, "commands": results}
        publish_account_directory(stage, account_path(op), account, op, execution_hash, commands)
        published = True
        print(f"GATE COMMAND ACCOUNT {op}")
        return account
    finally:
        if not published:
            shutil.rmtree(stage, ignore_errors=True)


def run_commands(op):
    validate_op(op)
    with execution_lock(op) as lock_descriptor:
        return run_owned_commands(op, lock_descriptor)


def main():
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command == "policy-show" and len(sys.argv) == 2:
            sys.stdout.buffer.write(canonical_bytes(configured_policy()))
        elif command == "policy-publish" and len(sys.argv) == 3:
            publish_policy(sys.argv[2])
        elif command == "open-marker" and len(sys.argv) == 3:
            open_marker(sys.argv[2])
        elif command == "correction-terminal" and len(sys.argv) == 5:
            if sys.argv[3] not in {"result", "lost", "unusable"}:
                refuse("the correction gate terminal kind is invalid")
            correction_gate_terminal(
                sys.argv[2], sys.argv[4] if sys.argv[3] == "result" else sys.argv[3],
            )
        elif command == "show" and len(sys.argv) == 2:
            sys.stdout.buffer.write(canonical_bytes(configured_execution()))
        elif command == "token" and len(sys.argv) == 2:
            print(json.dumps(encode_execution(configured_execution()), separators=(",", ":")))
        elif command == "validate-token" and len(sys.argv) in {4, 5}:
            expected_tree = sys.argv[4] if len(sys.argv) == 5 else None
            _, execution_hash = decode_execution(sys.argv[2], sys.argv[3], expected_tree)
            print(execution_hash)
        elif command == "trigger" and len(sys.argv) == 3:
            print(json.dumps(trigger_account(sys.argv[2]), separators=(",", ":"), sort_keys=True))
        elif command == "publish" and len(sys.argv) == 3:
            publish(sys.argv[2])
        elif command == "remove" and len(sys.argv) == 2:
            remove()
        elif command == "run" and len(sys.argv) == 3:
            run_commands(sys.argv[2])
        elif command == "inspect" and len(sys.argv) == 3:
            execution, execution_hash, account, account_hash = account_state(sys.argv[2])
            print(json.dumps({
                "execution": execution,
                "execution_sha256": execution_hash,
                "command_account_sha256": account_hash,
                "commands": len(account["commands"]),
            }, separators=(",", ":"), sort_keys=True))
        elif command == "result" and len(sys.argv) == 4:
            result_item(sys.argv[2], sys.argv[3])
        elif command == "output" and len(sys.argv) == 6:
            output_chunk(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        elif command == "idle" and len(sys.argv) == 3:
            assert_idle(sys.argv[2])
        else:
            refuse(
                "usage: gate_execution.py <policy-show|policy-publish|open-marker|correction-terminal|show|token|"
                "validate-token|trigger|publish|remove|run|inspect|result|output|idle> [argument]"
            )
    except (ValueError, OSError) as exc:
        print(f"**gate execution ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
