#!/usr/bin/env python3
"""Validate immutable content-addressed Correction Round authority objects."""

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile

LOT_RE = re.compile(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?")
HASH_RE = re.compile(r"[0-9a-f]{64}")
SUFFIXES = {".md", ".json"}
MAX_OBJECT_BYTES = 1_048_576
MANDATES = ("unlooked", "user", "meaning", "quality", "coverage")
ALLOCATION_KEYS = {
    "schema", "built", "round", "predecessor_supersession", "parent", "pass",
    "items", "refuted", "admission",
}
CONTROLLER_SUCCESSOR_COMMON_KEYS = {
    "schema", "kind", "transition", "built", "position",
    "predecessor_generation_sha256", "authorities", "commit", "gate",
}
ADMISSION_KEYS = {
    "items", "spec", "human_decisions", "controller_contract", "ownership",
    "decomposition", "coordination", "repetition", "reason",
}
EMPTY_FINAL_CHECKER_SET = {"schema": 1, "entries": []}
EMPTY_FINAL_CHECKER_SET_SHA256 = hashlib.sha256(
    json.dumps(EMPTY_FINAL_CHECKER_SET, sort_keys=True, separators=(",", ":")).encode(),
).hexdigest()
AT_FDCWD = -100
RENAME_NOREPLACE = 1
CORRECTION_LOCK_NAME = "correction-authority.lock"


class CorrectionAuthorityLease:
    """One non-serializable owner of the workspace Correction Round lock."""

    def __init__(self, workspace, operation, descriptor, identity):
        self.workspace = pathlib.Path(workspace)
        self.operation = _exact_text(operation, "the correction operation")
        self.acquisition_generation = None
        self._descriptor = descriptor
        self._identity = identity
        self._closed = False

    @classmethod
    def acquire(cls, workspace, operation):
        workspace = pathlib.Path(workspace)
        if not workspace.is_absolute():
            raise ValueError("the correction authority workspace is not absolute")
        _lstat_real_directory(workspace, "the correction authority workspace")
        path = workspace / CORRECTION_LOCK_NAME
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            opened = os.fstat(descriptor)
            current = path.lstat()
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode) \
                    or not stat.S_ISREG(opened.st_mode) \
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("the correction authority lock changed during acquisition")
            return cls(workspace, operation, descriptor, (opened.st_dev, opened.st_ino))
        except BaseException:
            os.close(descriptor)
            raise

    def __enter__(self):
        self.verify(self.operation)
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    def __reduce__(self):
        raise TypeError("a correction authority lease is not serializable")

    def bind_generation(self, generation):
        generation = _exact_text(generation, "the correction acquisition generation")
        if self.acquisition_generation is None:
            self.acquisition_generation = generation
        elif self.acquisition_generation != generation:
            raise ValueError("the correction lease already owns another acquisition generation")
        self.verify(self.operation, generation)

    def verify(self, operation, generation=None):
        if self._closed:
            raise ValueError("the correction authority lease is closed")
        if _exact_text(operation, "the correction operation") != self.operation:
            raise ValueError("the correction authority lease owns another operation")
        if generation is not None and generation != self.acquisition_generation:
            raise ValueError("the correction authority lease owns another acquisition generation")
        opened = os.fstat(self._descriptor)
        current = (self.workspace / CORRECTION_LOCK_NAME).lstat()
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode) \
                or (opened.st_dev, opened.st_ino) != self._identity \
                or (current.st_dev, current.st_ino) != self._identity:
            raise ValueError("the correction authority lease no longer owns its lock")

        probe = os.open(
            self.workspace / CORRECTION_LOCK_NAME,
            os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            fcntl.flock(probe, fcntl.LOCK_UN)
            raise ValueError("the correction authority lease does not hold its lock")
        finally:
            os.close(probe)

    def close(self):
        if self._closed:
            return
        self._closed = True
        os.close(self._descriptor)


def _positive_integer(value, subject, *, allow_zero=False):
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{subject} is not a valid integer")
    return value


def _exact_text(value, subject):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{subject} is not exact text")
    return value


def _source_key(identity):
    mandate, finding = identity.split("/F", 1)
    return MANDATES.index(mandate), int(finding)


def _carry_key(identity):
    match = re.fullmatch(r"B([1-9][0-9]*)/([FD])([1-9][0-9]*)", identity)
    return int(match.group(1)), {"F": 0, "D": 1}[match.group(2)], int(match.group(3))


def _source_account(values, subject):
    if not isinstance(values, list) or any(
        not isinstance(item, str)
        or not re.fullmatch(rf"(?:{'|'.join(MANDATES)})/F[1-9][0-9]*", item)
        for item in values
    ) or values != sorted(set(values), key=_source_key):
        raise ValueError(f"{subject} is not a canonical source account")
    return values


def _carry_account(values, subject):
    if not isinstance(values, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"B[1-9][0-9]*/[FD][1-9][0-9]*", item)
        for item in values
    ) or values != sorted(set(values), key=_carry_key):
        raise ValueError(f"{subject} is not a canonical carried account")
    return values


def normalize_allocation(value):
    if not isinstance(value, dict) or set(value) != ALLOCATION_KEYS or value.get("schema") != 2:
        raise ValueError("the correction allocation has an invalid shape")
    built = value.get("built")
    if not isinstance(built, str) or not LOT_RE.fullmatch(built):
        raise ValueError("the correction allocation has an invalid built unit")
    round_number = _positive_integer(value.get("round"), "the correction round")
    predecessor = value.get("predecessor_supersession")
    if predecessor is not None and (not isinstance(predecessor, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", predecessor,
    )):
        raise ValueError("the correction allocation has an invalid predecessor")

    parent = value.get("parent")
    if not isinstance(parent, dict) or set(parent) != {
        "position", "generation_sha256", "commit", "gate",
    }:
        raise ValueError("the correction allocation has an invalid parent")
    position = _positive_integer(parent.get("position"), "the parent position", allow_zero=True)
    if round_number != position + 1 \
            or not HASH_RE.fullmatch(str(parent.get("generation_sha256"))) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(parent.get("commit"))) \
            or not HASH_RE.fullmatch(str(parent.get("gate"))):
        raise ValueError("the correction allocation contradicts its parent generation")

    source_pass = value.get("pass")
    if not isinstance(source_pass, dict) or set(source_pass) != {
        "ordinal", "opening", "commit", "gate",
    }:
        raise ValueError("the correction allocation has an invalid source pass")
    _positive_integer(source_pass.get("ordinal"), "the source pass ordinal")
    if not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(source_pass.get("opening"))) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(source_pass.get("commit"))) \
            or not HASH_RE.fullmatch(str(source_pass.get("gate"))):
        raise ValueError("the correction allocation has malformed source-pass authority")

    items = value.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("the correction allocation has no item")
    seen_sources = set()
    seen_carries = set()
    for ordinal, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != {"id", "sources", "carries"} \
                or item.get("id") != f"F{ordinal}":
            raise ValueError("the correction allocation items are not exact and sequential")
        sources = _source_account(item.get("sources"), f"the allocation {item['id']} sources")
        carries = _carry_account(item.get("carries"), f"the allocation {item['id']} carries")
        if not sources and not carries or seen_sources.intersection(sources) \
                or seen_carries.intersection(carries):
            raise ValueError("the correction allocation repeats or omits item authority")
        seen_sources.update(sources)
        seen_carries.update(carries)
    _source_account(value.get("refuted"), "the correction allocation refutations")

    admission = value.get("admission")
    if not isinstance(admission, dict) or set(admission) != ADMISSION_KEYS:
        raise ValueError("the correction allocation has an invalid admission account")
    admission_items = admission.get("items")
    if not isinstance(admission_items, list) or len(admission_items) != len(items):
        raise ValueError("the correction admission does not cover every item")
    for ordinal, item in enumerate(admission_items, 1):
        if not isinstance(item, dict) or set(item) != {"id", "classification", "reason"} \
                or item.get("id") != f"F{ordinal}" \
                or item.get("classification") != "implementation-correction":
            raise ValueError("the correction item admission is malformed")
        _exact_text(item.get("reason"), f"the correction {item['id']} admission reason")
    fixed = {
        "spec": "current-and-settled",
        "human_decisions": "settled",
        "controller_contract": "preserved",
        "ownership": "preserved",
        "decomposition": "preserved",
        "coordination": "bounded",
    }
    if any(admission.get(key) != expected for key, expected in fixed.items()) \
            or admission.get("repetition") not in {"independent", "reassessed-bounded"}:
        raise ValueError("the correction admission does not preserve its route boundaries")
    _exact_text(admission.get("reason"), "the complete correction admission reason")
    return json.loads(json.dumps(value))


def normalize_controller_successor(value):
    if not isinstance(value, dict) or value.get("schema") != 1 \
            or value.get("kind") != "controller-successor":
        raise ValueError("the controller-successor generation has an invalid shape")
    transition = value.get("transition")
    proof_key = {
        "in-pass-product-authority": "source_pass",
        "amendment-or-plan-successor": "voided_pass",
    }.get(transition)
    if proof_key is None or set(value) != CONTROLLER_SUCCESSOR_COMMON_KEYS | {proof_key}:
        raise ValueError("the controller-successor generation has an invalid transition")
    if not isinstance(value.get("built"), str) or not LOT_RE.fullmatch(value["built"]):
        raise ValueError("the controller-successor generation has an invalid built unit")
    _positive_integer(value.get("position"), "the controller-successor position", allow_zero=True)
    if not HASH_RE.fullmatch(str(value.get("predecessor_generation_sha256"))) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(value.get("commit"))) \
            or not HASH_RE.fullmatch(str(value.get("gate"))) \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(value.get(proof_key))):
        raise ValueError("the controller-successor generation has malformed authority")
    authorities = value.get("authorities")
    if not isinstance(authorities, list) or not authorities or any(
        not isinstance(proof, str)
        or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", proof)
        for proof in authorities
    ):
        raise ValueError("the controller-successor authority account is malformed")
    indices = [int(proof.split(":", 1)[0]) for proof in authorities]
    if indices != sorted(set(indices)):
        raise ValueError("the controller-successor authority account is not ordered and unique")
    return json.loads(json.dumps(value))


def product_report_path(built, position, pass_ordinal, mandate):
    if not isinstance(built, str) or not LOT_RE.fullmatch(built):
        raise ValueError("the product report has an invalid built unit")
    _positive_integer(position, "the correction position", allow_zero=True)
    _positive_integer(pass_ordinal, "the product pass ordinal")
    if mandate not in MANDATES:
        raise ValueError("the product report has an invalid mandate")
    root = built.split(".", 1)[0]
    return pathlib.PurePosixPath(
        "reports", "product-review", root,
        f"{built}-c{position}-p{pass_ordinal}-{mandate}.md",
    )


def product_confirmed_path(built, position, pass_ordinal):
    if not isinstance(built, str) or not LOT_RE.fullmatch(built):
        raise ValueError("the confirmed artifact has an invalid built unit")
    _positive_integer(position, "the correction position", allow_zero=True)
    _positive_integer(pass_ordinal, "the product pass ordinal")
    root = built.split(".", 1)[0]
    return pathlib.PurePosixPath(
        "reports", "product-review", root,
        f"{built}-c{position}-p{pass_ordinal}-confirmed.md",
    )


def private_risk_history_path(built, mandate):
    if not isinstance(built, str) or not LOT_RE.fullmatch(built) or mandate not in MANDATES:
        raise ValueError("the private risk history has an invalid identity")
    root = built.split(".", 1)[0]
    return pathlib.PurePosixPath(
        "reports", "product-review", root, f"{built}-{mandate}-risk-filtered.md",
    )


def occurrence_label(position, pass_ordinal):
    _positive_integer(position, "the correction position", allow_zero=True)
    _positive_integer(pass_ordinal, "the product pass ordinal")
    return f"c{position}-p{pass_ordinal}"


def generation_sha256(account):
    if isinstance(account, dict) and account.get("kind") == "controller-successor":
        normalized = normalize_controller_successor(account)
        return hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()
    expected_keys = {
        "schema", "kind", "built", "position", "origin", "plan", "tasks",
        "terminal", "commit", "gate", "final_checker_set_sha256",
    }
    if not isinstance(account, dict) or set(account) != expected_keys \
            or account.get("schema") != 1 or account.get("kind") != "built":
        raise ValueError("the built generation has an invalid preimage")
    built = account.get("built")
    if not isinstance(built, str) or not LOT_RE.fullmatch(built) or account.get("position") != 0:
        raise ValueError("the built generation has an invalid subject identity")
    origin = account.get("origin")
    if not isinstance(origin, dict) or set(origin) != {"kind", "opening", "source"} \
            or origin.get("kind") not in {"root-lot", "sublot"} \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(origin.get("opening"))) \
            or not re.fullmatch(r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(origin.get("source"))):
        raise ValueError("the built generation has an invalid origin")
    plan = account.get("plan")
    if not isinstance(plan, dict) or set(plan) != {"path", "sha256"} \
            or not isinstance(plan.get("path"), str) \
            or pathlib.PurePosixPath(plan["path"]).is_absolute() \
            or ".." in pathlib.PurePosixPath(plan["path"]).parts \
            or pathlib.PurePosixPath(plan["path"]).parts[:2] != ("docs", "plans") \
            or not HASH_RE.fullmatch(str(plan.get("sha256"))):
        raise ValueError("the built generation has an invalid plan authority")
    tasks = account.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("the built generation has no task")
    for ordinal, task in enumerate(tasks, 1):
        if not isinstance(task, dict) or set(task) != {
            "task", "attempt", "commit", "gate", "success",
        } or task.get("task") != ordinal:
            raise ValueError("the built generation tasks are not exact and sequential")
        _positive_integer(task.get("attempt"), f"the built task {ordinal} attempt")
        if not re.fullmatch(r"[0-9a-f]{40,64}", str(task.get("commit"))) \
                or not HASH_RE.fullmatch(str(task.get("gate"))) \
                or not re.fullmatch(
                    r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(task.get("success")),
                ):
            raise ValueError("the built generation has malformed task authority")
    if account.get("commit") != tasks[-1]["commit"] or account.get("gate") != tasks[-1]["gate"] \
            or not re.fullmatch(
                r"(?:0|[1-9][0-9]*):[0-9a-f]{64}", str(account.get("terminal")),
            ) or account.get("final_checker_set_sha256") != EMPTY_FINAL_CHECKER_SET_SHA256:
        raise ValueError("the built generation has an invalid terminal authority")
    payload = json.dumps(account, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def content_object_path(workspace, built, digest, suffix):
    if not isinstance(built, str) or not LOT_RE.fullmatch(built):
        raise ValueError("the correction authority has an invalid built unit")
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        raise ValueError("the correction authority has an invalid SHA-256")
    if suffix not in SUFFIXES:
        raise ValueError("the correction authority has an invalid object type")
    workspace = pathlib.Path(workspace)
    if not workspace.is_absolute():
        raise ValueError("the correction authority workspace is not absolute")
    return workspace / "corrections" / built / "objects" / f"sha256-{digest}{suffix}"


def _lstat_real_directory(path, subject):
    try:
        status = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{subject} does not exist") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise ValueError(f"{subject} is not one real directory")


def validate_content_object(workspace, built, digest, suffix):
    target = content_object_path(workspace, built, digest, suffix)
    workspace = pathlib.Path(workspace)
    _lstat_real_directory(workspace, "the correction authority workspace")
    cursor = workspace
    for component in ("corrections", built, "objects"):
        cursor = cursor / component
        _lstat_real_directory(cursor, "a correction authority parent")
    try:
        status = target.lstat()
    except FileNotFoundError as exc:
        raise ValueError("the correction authority object does not exist") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise ValueError("the correction authority object is not one real regular file")
    if status.st_nlink != 1:
        raise ValueError("the correction authority object has more than one link")
    if status.st_mode & 0o222:
        raise ValueError("the correction authority object is writable")
    if status.st_size < 1 or status.st_size > MAX_OBJECT_BYTES:
        raise ValueError("the correction authority object has invalid bytes")
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if opened.st_dev != status.st_dev or opened.st_ino != status.st_ino:
            raise ValueError("the correction authority object changed during validation")
        payload = b""
        while len(payload) <= MAX_OBJECT_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_OBJECT_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
    finally:
        os.close(descriptor)
    if not payload or len(payload) > MAX_OBJECT_BYTES:
        raise ValueError("the correction authority object has invalid bytes")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("the correction authority object does not match its name")
    return target


def _ensure_real_directory(path, subject):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _lstat_real_directory(path, subject)


def _rename_without_replace(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOSYS, "renameat2 is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD, os.fsencode(source), AT_FDCWD, os.fsencode(target), RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def publish_content_object(workspace, built, payload, suffix):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_OBJECT_BYTES:
        raise ValueError("the correction authority publication has invalid bytes")
    digest = hashlib.sha256(payload).hexdigest()
    target = content_object_path(workspace, built, digest, suffix)
    workspace = pathlib.Path(workspace)
    _lstat_real_directory(workspace, "the correction authority workspace")
    cursor = workspace
    for component in ("corrections", built, "objects"):
        cursor = cursor / component
        _ensure_real_directory(cursor, "a correction authority parent")
    if target.exists() or target.is_symlink():
        return validate_content_object(workspace, built, digest, suffix)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    temporary = pathlib.Path(temporary_name)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short correction authority object write")
            offset += written
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o444)
        os.close(descriptor)
        descriptor = -1
        try:
            _rename_without_replace(temporary, target)
        except FileExistsError:
            return validate_content_object(workspace, built, digest, suffix)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    return validate_content_object(workspace, built, digest, suffix)
