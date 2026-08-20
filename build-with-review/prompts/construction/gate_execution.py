#!/usr/bin/env python3
"""Freeze and execute one human-approved gate-command schedule."""
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

from gate_file import GateFileError, read_gate_commands


HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPO = WORKSPACE.parent.parent.parent.resolve()
GATE = REPO / ".superpowers" / "bwr" / "gate.md"
CONFIG = WORKSPACE / "gate-execution.json"
MARKER = WORKSPACE / "gate-check-in-progress"
REPORT_GROUND = WORKSPACE / "reports" / "gate"
OUTPUT_CHUNK_BYTES = 65536


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


def index_tree():
    return git_output("write-tree")


def evidence_path(value):
    if value == ".":
        return value
    if not isinstance(value, str) or not value or "\\" in value \
            or value.startswith("/") or posixpath.normpath(value) != value \
            or ".." in pathlib.PurePosixPath(value).parts:
        refuse("a compatibility evidence path must be one canonical repository-relative path")
    return value


def evidence_identity(tree, path):
    path = evidence_path(path)
    if path == ".":
        raw = f"040000 tree {tree}\t.\0".encode()
    else:
        result = subprocess.run(
            ["git", "-C", str(REPO), "ls-tree", "-z", tree, "--", path],
            capture_output=True,
        )
        if result.returncode or not result.stdout or result.stdout.count(b"\0") != 1:
            refuse(f"compatibility evidence path has no one exact Git object: {path}")
        raw = result.stdout
    return hashlib.sha256(raw).hexdigest()


def evidence_account(paths, tree=None):
    tree = tree or index_tree()
    normalized = [evidence_path(path) for path in paths]
    if len(set(normalized)) != len(normalized) or normalized != sorted(normalized):
        refuse("compatibility evidence paths must be unique and sorted")
    return [{"path": path, "identity": evidence_identity(tree, path)} for path in normalized]


def validate_execution(value, gate_sha, commands, tree=None):
    if not isinstance(value, dict) or set(value) != {
        "schema", "gate", "max_parallel", "compatible_groups", "compatibility_evidence"
    }:
        refuse("gate execution has an incomplete top-level shape")
    maximum = value.get("max_parallel")
    groups = value.get("compatible_groups")
    evidence = value.get("compatibility_evidence")
    if value.get("schema") != 1 or value.get("gate") != gate_sha:
        refuse("gate execution belongs to another gate.md generation")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        refuse("max_parallel must be one positive integer")
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
    if not isinstance(evidence, list):
        refuse("compatibility_evidence must be one complete ordered list")
    paths = []
    for number, item in enumerate(evidence, 1):
        if not isinstance(item, dict) or set(item) != {"path", "identity"} \
                or not isinstance(item.get("identity"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", item["identity"]):
            refuse(f"compatibility evidence item {number} has an invalid shape")
        paths.append(evidence_path(item.get("path")))
    if len(set(paths)) != len(paths) or paths != sorted(paths):
        refuse("compatibility evidence paths must be unique and sorted")
    if any(len(group) > 1 for group in groups) and not evidence:
        refuse("a parallel compatible group requires explicit project evidence")
    if tree is not None:
        current_evidence = evidence_account(paths, tree)
        if evidence != current_evidence:
            changed = [expected["path"] for expected, current in zip(evidence, current_evidence)
                       if expected != current]
            refuse("project evidence for parallel gate compatibility changed: "
                   + ", ".join(changed))
    return value


def default_execution(gate_sha, commands):
    return {
        "schema": 1,
        "gate": gate_sha,
        "max_parallel": 1,
        "compatibility_evidence": [],
        "compatible_groups": [[command] for command in commands],
    }


def configured_execution():
    gate_sha, commands = gate_state()
    if not CONFIG.exists() and not CONFIG.is_symlink():
        return default_execution(gate_sha, commands)
    regular_file(CONFIG, "gate-execution.json")
    try:
        value = json.loads(CONFIG.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"gate-execution.json is not complete JSON: {exc}")
    return validate_execution(value, gate_sha, commands, index_tree())


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


def marker_data(op=None):
    lines = regular_file(MARKER, "the gate-check marker").read_text(encoding="utf-8").splitlines()
    marker = {}
    for line in lines:
        key, separator, value = line.partition(" ")
        if not separator or not value or key in marker:
            refuse("the gate-check marker is malformed")
        marker[key] = value
    expected = {
        "op", "scope", "owner", "lot", "task", "attempt", "head", "base", "tree", "gate", "code"
    }
    if set(marker) not in (expected, expected | {"execution"}):
        refuse("the gate-check marker has an incomplete identity")
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


def publish(source):
    if MARKER.exists() or MARKER.is_symlink():
        refuse("finish or abandon the live gate operation before changing gate execution")
    source = pathlib.Path(source)
    if not source.is_absolute():
        refuse("the gate execution draft path must be absolute")
    source = regular_file(source, "the gate execution draft")
    try:
        value = json.loads(source.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        refuse(f"the gate execution draft is not complete JSON: {exc}")
    gate_sha, commands = gate_state()
    validate_execution(value, gate_sha, commands, index_tree())
    atomic_publish(CONFIG, canonical_bytes(value), replace=True)
    print(f"PUBLISHED {CONFIG}")


def remove():
    if MARKER.exists() or MARKER.is_symlink():
        refuse("finish or abandon the live gate operation before removing gate execution")
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
def execution_lock(op, *, blocking=True):
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
            refuse("the exact gate executor or one of its command processes is still live")
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
        if command == "show" and len(sys.argv) == 2:
            sys.stdout.buffer.write(canonical_bytes(configured_execution()))
        elif command == "token" and len(sys.argv) == 2:
            print(json.dumps(encode_execution(configured_execution()), separators=(",", ":")))
        elif command == "validate-token" and len(sys.argv) in {4, 5}:
            expected_tree = sys.argv[4] if len(sys.argv) == 5 else None
            _, execution_hash = decode_execution(sys.argv[2], sys.argv[3], expected_tree)
            print(execution_hash)
        elif command == "evidence" and len(sys.argv) >= 3:
            print(json.dumps(evidence_account(sys.argv[2:]), separators=(",", ":"), sort_keys=True))
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
            refuse("usage: gate_execution.py <show|token|validate-token|evidence|publish|remove|run|inspect|result|output|idle> [argument]")
    except (GateExecutionError, OSError) as exc:
        print(f"**gate execution ERROR** · {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
