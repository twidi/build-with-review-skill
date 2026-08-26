#!/usr/bin/env python3
"""Recover the inverted A4 attempt settlement without losing consolidated Spec bytes."""

import json
import fcntl
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

COMMON = Path(__file__).resolve().parent.parent / "common"
sys.path.insert(0, str(COMMON))
import progress  # noqa: E402


WORKSPACE = Path(progress.WORKSPACE)
REPO = Path(progress.REPO)
MARKER = Path(progress.AMENDMENT_ATTEMPT_SETTLE_MARKER)
RECOVERY_ROOT = WORKSPACE / "recovery" / "amendment-attempt-settle"
OWNER_LOCK = WORKSPACE / "amendment-attempt-settle.lock"
PHYSICAL_ADMISSION_LOCK = WORKSPACE / "controller-physical-admission.lock"


def die(message):
    print(f"**settlement ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def run(command, *, env=None):
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        die(result.stderr.strip() or result.stdout.strip() or f"command failed: {command}")
    return result.stdout


def atomic_bytes(path, payload, mode):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as target:
            descriptor = -1
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def test_barrier(name):
    if os.environ.get("BWR_TEST_AMENDMENT_SETTLE_BARRIER") != name:
        return
    directory = Path(os.environ["BWR_TEST_AMENDMENT_SETTLE_BARRIER_DIR"])
    ready = directory / f"{name}.ready"
    release = directory / f"{name}.release"
    ready.write_text("ready\n", encoding="utf-8")
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() >= deadline:
            die(f"test barrier {name} timed out")
        time.sleep(0.01)


def read_marker(amendment, lot, task, attempt):
    marker = progress.amendment_attempt_settle_marker(
        "the Amendment attempt settlement", required=True,
    )
    owner = marker["owner"]
    if (owner["amendment"], owner["lot"], owner["task"], owner["attempt"]) != (
        amendment, lot, task, attempt,
    ):
        die("the retained marker belongs to another Amendment attempt")
    progress.validate_amendment_attempt_settle_owner(
        progress.journal_entries(), len(progress.journal_entries()), owner,
        "the Amendment attempt settlement",
    )
    recovery = WORKSPACE / owner["recovery"]
    if not recovery.exists() and marker["phase"] == "terminal-recorded" \
            and existing_terminal(progress.journal_entries(), marker["owner_sha256"]):
        return marker
    if recovery.is_symlink() or not recovery.is_file() \
            or progress.sha256_bytes(recovery.read_bytes()) != owner["consolidated_spec_sha256"]:
        die("the immutable consolidated-Spec recovery changed or is absent")
    return marker


def exact_implementer(entries, lot, task, attempt):
    starts = [(index, entry) for index, entry in enumerate(entries)
              if entry.get("event") == "session-started"
              and entry.get("mode") == "construction"
              and entry.get("job") == "implementer"
              and entry.get("lot") == lot and entry.get("task") == task
              and entry.get("attempt") == attempt]
    if len(starts) != 1:
        die("the inverted prefix has no one exact physical implementer opening")
    index, start = starts[0]
    progress.validate_construction_session_start(
        start, "the inverted A4 settlement", entries=entries, index=index,
    )
    if any(entry.get("event") == "session-retired"
           and entry.get("session") == start.get("session") for entry in entries):
        die("the exact implementer is already retired")
    return index, start


def prepare_new(amendment, lot, task, attempt):
    entries = progress.journal_entries()
    progress.validate_construction_verdict_history(entries)
    identity = progress.active_attempt_identity(
        {"lot": lot, "task": task, "attempt": attempt},
        "the inverted A4 settlement",
    )
    if os.path.lexists(progress.BARE_STOP_MARKER):
        die("a bare stop already owns the workspace")
    openings = progress.amendment_openings(entries)
    if not openings:
        die("the inverted prefix has no current Amendment opening")
    opening_index, opening = openings[-1]
    if progress.note_data(opening).get("amendment") != amendment:
        die("the requested Amendment is not the current generation")
    state = progress.current_amendment_review(entries, len(entries), "the inverted A4 settlement")
    sweep_index = progress.journal_entry_from_proof(
        entries,
        next(progress.journal_line_proof(index) for index, entry in reversed(list(enumerate(entries)))
             if entry.get("kind") == "sweep.reported"),
        "the inverted A4 settlement",
    )[0]
    _, fixer_index = progress.amendment_deferred_prefix(
        entries, len(entries), opening_index, sweep_index, "the inverted A4 settlement",
    )
    failure_source = progress.amendment_deferred_failure_source(
        entries, opening_index, lot, task, attempt, "the inverted A4 settlement",
        current_before=len(entries),
    )
    current_task = progress.read_construction_plan_state(
        lot, task, "the inverted A4 settlement",
    )
    if any(current_task.get(key) != failure_source["logical"].get(key) for key in (
        "plan_ownership_sha256", "contract_sha256", "design_sha256",
        "plan_projection_sha256", "disagreement_sha256",
    )):
        die("the controller task changed before the deferred failure boundary")
    start_index, start = exact_implementer(entries, lot, task, attempt)
    start_data = start.get("data") or {}
    base = start_data.get("attempt_base")
    base_tree = start_data.get("attempt_base_tree")
    if not base:
        base_ref = f"refs/bwr/{WORKSPACE.name}/{lot}/attempt-base"
        base, base_tree = progress.git_commit_and_tree(base_ref, "the inverted A4 settlement")
    head, head_tree = progress.git_commit_and_tree("HEAD", "the inverted A4 settlement")
    if head != base or head_tree != base_tree:
        die("HEAD is not the exact attempt base")
    spec_path = os.path.relpath(state["spec_path"], REPO)
    status = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True,
    )
    expected_status = b" M " + os.fsencode(spec_path) + b"\0"
    if status.returncode != 0 or status.stdout != expected_status:
        die("the worktree or index differs from attempt-base by more than the unstaged living Spec")
    consolidated = Path(state["spec_path"]).read_bytes()
    base_blob = subprocess.run(
        ["git", "-C", REPO, "show", f"{base}:{spec_path}"], capture_output=True,
    )
    if base_blob.returncode != 0 or consolidated == base_blob.stdout:
        die("the living Spec has no exact consolidated change above attempt-base")
    consolidated_sha = progress.sha256_bytes(consolidated)
    recovery_relative = f"recovery/amendment-attempt-settle/{consolidated_sha}.spec"
    owner = {
        "schema": 1,
        "amendment": amendment,
        "opening": progress.journal_line_proof(opening_index),
        "sweep": progress.journal_line_proof(sweep_index),
        "fixer": progress.journal_line_proof(fixer_index),
        "lot": lot, "task": task, "attempt": attempt,
        "attempt_identity": identity,
        "attempt_base": base,
        "attempt_base_tree": base_tree,
        "spec_path": spec_path,
        "base_spec_sha256": progress.sha256_bytes(base_blob.stdout),
        "consolidated_spec_sha256": consolidated_sha,
        "recovery": recovery_relative,
        "session": start["session"],
        "started": progress.journal_line_proof(start_index),
        "failure_source": failure_source,
    }
    progress.validate_amendment_attempt_settle_owner(
        entries, len(entries), owner, "the inverted A4 settlement",
    )
    test_barrier("final-admission")
    RECOVERY_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    recovery = WORKSPACE / recovery_relative
    if recovery.exists():
        if recovery.is_symlink() or recovery.read_bytes() != consolidated:
            die("the content-addressed recovery name has a foreign occupant")
    else:
        descriptor = os.open(recovery, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(consolidated)
            target.flush()
            os.fsync(target.fileno())
        fsync_directory(RECOVERY_ROOT)
    marker = {
        "schema": 1, "operation": "amendment-attempt-settle", "phase": "owned",
        "owner": owner, "owner_sha256": progress.canonical_digest(owner),
    }
    descriptor = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(marker, target, sort_keys=True, separators=(",", ":"))
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    fsync_directory(WORKSPACE)
    return marker


def prepare(amendment, lot, task, attempt):
    if MARKER.exists() or MARKER.is_symlink():
        return read_marker(amendment, lot, task, attempt)
    with open(PHYSICAL_ADMISSION_LOCK, "a+b") as physical_lock:
        fcntl.flock(physical_lock, fcntl.LOCK_EX)
        with open(progress.JOURNAL_LOCK, "a+b") as journal_lock:
            fcntl.flock(journal_lock, fcntl.LOCK_EX)
            if MARKER.exists() or MARKER.is_symlink():
                return read_marker(amendment, lot, task, attempt)
            return prepare_new(amendment, lot, task, attempt)


def set_phase(marker, phase):
    marker = dict(marker)
    marker["phase"] = phase
    current = progress.amendment_attempt_settle_marker("the settlement phase update", required=True)
    if current != {**marker, "phase": current["phase"]}:
        die("the retained settlement marker changed before its phase update")
    atomic_bytes(MARKER, (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode(), 0o600)
    return marker


def test_interrupt_after(phase):
    if os.environ.get("BWR_TEST_AMENDMENT_SETTLE_STOP_AFTER") == phase:
        print(f"TEST INTERRUPTION AFTER {phase}")
        raise SystemExit(75)


def exact_spec_state(owner):
    spec = REPO / owner["spec_path"]
    if spec.is_symlink() or not spec.is_file():
        die("the living Spec changed outside the retained settlement phase")
    digest = progress.sha256_bytes(spec.read_bytes())
    status = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True,
    )
    head, tree = progress.git_commit_and_tree("HEAD", "the retained settlement phase")
    if head != owner["attempt_base"] or tree != owner["attempt_base_tree"]:
        die("the retained settlement no longer owns the exact attempt-base HEAD")
    dirty_status = b" M " + os.fsencode(owner["spec_path"]) + b"\0"
    if status.returncode == 0 and status.stdout == dirty_status \
            and digest == owner["consolidated_spec_sha256"]:
        return "consolidated"
    if status.returncode == 0 and status.stdout == b"" \
            and digest == owner["base_spec_sha256"]:
        return "base"
    die("the repository or index changed outside the retained settlement phase")


def require_spec_state(owner, expected):
    if exact_spec_state(owner) != expected:
        die("the living Spec has the wrong exact retained settlement state")


def existing_terminal(entries, owner_sha):
    matches = [entry for entry in entries if entry.get("kind") == "amendment.attempt.settled"
               and progress.note_data(entry).get("owner_sha256") == owner_sha]
    if len(matches) > 1:
        die("the Amendment attempt settlement has duplicate terminals")
    if matches:
        index = entries.index(matches[0])
        progress.validate_amendment_attempt_settled_entry(entries, index, matches[0])
    return bool(matches)


def existing_failure(entries, owner):
    matches = progress.amendment_attempt_settlement_failures(
        entries, len(entries), owner, "the Amendment attempt settlement",
    )
    if not matches:
        return False
    return True


def existing_retirement(entries, owner):
    matches = [(index, entry) for index, entry in enumerate(entries)
               if entry.get("event") == "session-retired"
               and entry.get("session") == owner["session"]]
    if len(matches) > 1:
        die("the Amendment attempt settlement has duplicate implementer retirements")
    if not matches:
        return False
    _index, retired = matches[0]
    if retired.get("status") != "superseded" or retired.get("archived") is not True \
            or retired.get("hidden") is not True \
            or any(retired.get(key) != owner[key] for key in ("lot", "task", "attempt")):
        die("the implementer retirement changed its exact settlement identity")
    return True


def settle(amendment, lot, task, attempt):
    if not MARKER.exists() and not MARKER.is_symlink():
        entries = progress.journal_entries()
        completed = [(index, entry) for index, entry in enumerate(entries)
                     if entry.get("kind") == "amendment.attempt.settled"
                     and isinstance(progress.note_data(entry).get("owner"), dict)
                     and tuple(progress.note_data(entry)["owner"].get(key)
                               for key in ("amendment", "lot", "task", "attempt"))
                     == (amendment, lot, task, attempt)]
        if completed:
            if len(completed) != 1:
                die("the requested Amendment attempt has duplicate settlement terminals")
            progress.validate_amendment_attempt_settled_entry(
                entries, completed[0][0], completed[0][1],
            )
            print(f"AMENDMENT ATTEMPT ALREADY SETTLED {amendment} {lot} {task} {attempt}")
            return
    marker = prepare(amendment, lot, task, attempt)
    owner = marker["owner"]
    owner_sha = marker["owner_sha256"]
    recovery = WORKSPACE / owner["recovery"]
    spec = REPO / owner["spec_path"]
    mode = stat.S_IMODE(spec.stat().st_mode)
    test_interrupt_after(marker["phase"])

    if existing_terminal(progress.journal_entries(), owner_sha):
        marker["phase"] = "terminal-recorded"
    if marker["phase"] == "owned":
        state = exact_spec_state(owner)
        if state == "consolidated":
            base = subprocess.run(
                ["git", "-C", REPO, "show", f"{owner['attempt_base']}:{owner['spec_path']}"],
                capture_output=True, check=True,
            ).stdout
            atomic_bytes(spec, base, mode)
            test_interrupt_after("base-bytes-written")
        elif state != "base":
            die("the base restore has no exact resumable Spec state")
        marker = set_phase(marker, "base-restored")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "base-restored":
        require_spec_state(owner, "base")
        if not existing_failure(progress.journal_entries(), owner):
            environment = dict(os.environ)
            environment["BWR_AMENDMENT_ATTEMPT_SETTLE_OWNER"] = owner_sha
            run([
                str(WORKSPACE / "prompts/construction/attempt-failed.sh"),
                lot, str(task), str(attempt), "C3.9b",
            ], env=environment)
        marker = set_phase(marker, "failure-recorded")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "failure-recorded":
        if not existing_failure(progress.journal_entries(), owner):
            die("the settlement restore has no exact durable attempt failure")
        state = exact_spec_state(owner)
        if state == "base":
            atomic_bytes(spec, recovery.read_bytes(), mode)
            test_interrupt_after("consolidated-bytes-written")
        elif state != "consolidated":
            die("the consolidated restore has no exact resumable Spec state")
        marker = set_phase(marker, "spec-restored")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "spec-restored":
        require_spec_state(owner, "consolidated")
        run([str(WORKSPACE / "prompts/construction/diagnostic-close.sh"), lot, str(task), str(attempt)])
        marker = set_phase(marker, "diagnostic-closed")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "diagnostic-closed":
        require_spec_state(owner, "consolidated")
        if not existing_retirement(progress.journal_entries(), owner):
            run([
                str(WORKSPACE / "prompts/common/progress.py"), "session-retired",
                owner["session"], "superseded", "--archive", "--hide",
            ])
        marker = set_phase(marker, "implementer-retired")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "implementer-retired":
        require_spec_state(owner, "consolidated")
        run([
            str(WORKSPACE / "prompts/common/progress.py"), "amendment-attempt-settle-terminal",
            str(amendment), lot, str(task), str(attempt), owner_sha,
        ])
        marker = set_phase(marker, "terminal-recorded")
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "terminal-recorded":
        entries = progress.journal_entries()
        if not existing_terminal(entries, owner_sha):
            die("the settlement marker reached cleanup without its exact durable terminal")
        require_spec_state(owner, "consolidated")
        if recovery.exists():
            recovery.unlink()
        MARKER.unlink()
        try:
            RECOVERY_ROOT.rmdir()
        except OSError:
            pass
    print(f"AMENDMENT ATTEMPT SETTLED {amendment} {lot} {task} {attempt}")


def main():
    if len(sys.argv) != 5:
        die("usage: amendment-attempt-settle.sh <amendment> <lot> <task> <attempt>")
    try:
        amendment, task, attempt = (int(sys.argv[1]), int(sys.argv[3]), int(sys.argv[4]))
    except ValueError:
        die("amendment, task and attempt must be positive integers")
    if min(amendment, task, attempt) < 1:
        die("amendment, task and attempt must be positive integers")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(OWNER_LOCK, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            die("the settlement owner lock is not one real regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        test_barrier("owner-held")
        settle(amendment, sys.argv[2], task, attempt)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    main()
