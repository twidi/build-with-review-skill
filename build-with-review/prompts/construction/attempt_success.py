#!/usr/bin/env python3
"""Publish or recover one ordinary task success as one durable operation."""

import fcntl
import json
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
MARKER = Path(progress.ATTEMPT_SUCCESS_MARKER)
OWNER_LOCK = WORKSPACE / "attempt-success.lock"
PHYSICAL_LOCK = WORKSPACE / "controller-physical-admission.lock"
INFLIGHT = WORKSPACE / "attempt-in-flight"


def die(message):
    print(f"**attempt success ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*arguments, ok=True):
    result = subprocess.run(
        ["git", "-C", str(REPO), *arguments], capture_output=True, text=True,
    )
    if ok and result.returncode != 0:
        die(result.stderr.strip() or result.stdout.strip() or "Git command failed")
    return result


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_marker_generation(subject):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(MARKER, flags)
    except OSError as exc:
        die(f"{subject} has no exact retained success owner: {exc}")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            die(f"{subject} is not one real regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            payload = source.read()
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    ):
        die(f"{subject} changed while it was read")
    try:
        marker = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        die(f"{subject} is malformed: {exc}")
    progress.validate_attempt_success_marker(marker, subject)
    return {
        "marker": marker,
        "payload": payload,
        "device": before.st_dev,
        "inode": before.st_ino,
    }


def require_marker_generation(generation, subject):
    current = read_marker_generation(subject)
    if any(current[key] != generation[key] for key in (
        "payload", "device", "inode",
    )):
        die(f"{subject} changed its exact retained marker generation")
    return current["marker"]


def atomic_marker(marker, predecessor):
    require_marker_generation(predecessor, "the attempt success phase predecessor")
    descriptor, temporary = tempfile.mkstemp(prefix=".attempt-success.", dir=WORKSPACE)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            descriptor = -1
            json.dump(marker, target, sort_keys=True, separators=(",", ":"))
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        require_marker_generation(predecessor, "the attempt success phase predecessor")
        os.replace(temporary, MARKER)
        fsync_directory(WORKSPACE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)
    return read_marker_generation("the published attempt success phase")


def set_phase(generation, phase):
    marker = require_marker_generation(generation, "the attempt success phase")
    updated = {**marker, "phase": phase}
    return atomic_marker(updated, generation)


def test_substitute_marker_after(boundary):
    if os.environ.get("BWR_TEST_ATTEMPT_SUCCESS_SUBSTITUTE_AFTER") != boundary:
        return
    generation = read_marker_generation("the attempt success substitution test")
    descriptor, temporary = tempfile.mkstemp(prefix=".attempt-success-substitute.", dir=WORKSPACE)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(generation["payload"])
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, MARKER)
        fsync_directory(WORKSPACE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def test_interrupt_after(phase):
    if os.environ.get("BWR_TEST_ATTEMPT_SUCCESS_STOP_AFTER") == phase:
        print(f"TEST INTERRUPTION AFTER {phase}")
        raise SystemExit(75)


def test_owner_barrier():
    directory = os.environ.get("BWR_TEST_ATTEMPT_SUCCESS_OWNER_BARRIER")
    if not directory:
        return
    root = Path(directory)
    ready = root / "owner.ready"
    release = root / "owner.release"
    ready.write_text("ready\n", encoding="utf-8")
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() >= deadline:
            die("the attempt success owner test barrier timed out")
        time.sleep(0.01)


def test_physical_barrier(boundary):
    directory = os.environ.get("BWR_TEST_ATTEMPT_SUCCESS_PHYSICAL_BARRIER")
    wanted = os.environ.get("BWR_TEST_ATTEMPT_SUCCESS_PHYSICAL_BOUNDARY")
    if not directory or boundary not in (wanted or "").split(","):
        return
    root = Path(directory)
    ready = root / f"{boundary}.ready"
    release = root / f"{boundary}.release"
    ready.write_text("ready\n", encoding="utf-8")
    deadline = time.monotonic() + 30
    while not release.exists():
        if time.monotonic() >= deadline:
            die("the attempt success physical test barrier timed out")
        time.sleep(0.01)


def terminal_matches(entries, owner):
    owner_sha = progress.canonical_digest(owner)
    matches = [(index, entry) for index, entry in enumerate(entries)
               if entry.get("event") == "note"
               and entry.get("kind") == "attempt.succeeded"
               and progress.note_data(entry).get("success_recovery", {}).get("owner_sha256")
               == owner_sha]
    if len(matches) > 1:
        die("the attempt success has duplicate helper-owned terminals")
    if not matches:
        return False
    progress.validate_attempt_succeeded_entry(entries, matches[0][0], matches[0][1])
    return True


def exact_existing_terminal(entries, lot, task, commit, gate):
    matches = [(index, entry) for index, entry in enumerate(entries)
               if entry.get("event") == "note"
               and entry.get("kind") == "attempt.succeeded"
               and entry.get("lot") == lot and entry.get("task") == task
               and progress.note_data(entry).get("sha") == commit]
    if not matches:
        return False
    if len(matches) != 1 or progress.note_data(matches[0][1]).get("gate") != gate:
        die("the stable task already has another durable success terminal")
    progress.validate_attempt_succeeded_entry(entries, matches[0][0], matches[0][1])
    return "helper" if isinstance(
        progress.note_data(matches[0][1]).get("success_recovery"), dict,
    ) else "ordinary"


def stable_ref_state(stable_ref):
    existing = git("rev-parse", "--verify", "--quiet", stable_ref, ok=False)
    if existing.returncode not in {0, 1}:
        die("the stable task ref cannot be read")
    return None if existing.returncode == 1 else existing.stdout.strip()


def select_attempt(entries, lot, task):
    if INFLIGHT.exists():
        first = INFLIGHT.read_text(encoding="utf-8").splitlines()
        fields = first[0].split() if first else []
        if len(fields) != 3 or fields[:2] != [lot, str(task)] \
                or not fields[2].isdigit() or int(fields[2]) < 1:
            die("attempt-in-flight belongs to another task")
        attempt = int(fields[2])
        progress.active_attempt_identity(
            {"lot": lot, "task": task, "attempt": attempt}, "the task success",
        )
        return attempt
    candidates = []
    for entry in entries:
        if entry.get("event") != "session-started" \
                or entry.get("mode") != "construction" \
                or entry.get("job") != "implementer" \
                or entry.get("lot") != lot or entry.get("task") != task \
                or not progress.construction_positive_integer(entry.get("attempt")):
            continue
        attempt = entry["attempt"]
        if any(progress.construction_attempt_terminal(candidate, lot, task, attempt)
               for candidate in entries):
            continue
        if any(candidate.get("event") == "session-retired"
               and candidate.get("session") == entry.get("session") for candidate in entries):
            continue
        candidates.append(attempt)
    if len(candidates) != 1:
        die("the legacy task ref has no one exact open implementer attempt")
    return candidates[0]


def refuse_competing_owner():
    names = (
        "bare-stop-in-progress", "document-copy-in-progress", "plan-commit-in-progress",
        "spec-commit-in-progress", "amendment-commit-in-progress",
        "spec-breach-recovery-in-progress", "amendment-attempt-settle-in-progress.json",
        "rewind-in-progress", "gate-check-in-progress",
    )
    present = [name for name in names if os.path.lexists(WORKSPACE / name)]
    if present:
        die(f"another physical owner already controls the workspace: {present[0]}")


def reproject_marker(generation, lot, task, commit, gate, subject):
    marker = require_marker_generation(generation, subject)
    entries = progress.journal_entries()
    phase = marker["phase"]
    owner = marker["owner"]
    terminal = None
    if phase in {"terminal-writing", "terminal-recorded"}:
        candidates = [
            (index, entry) for index, entry in enumerate(entries)
            if entry.get("event") == "note"
            and entry.get("kind") == "attempt.succeeded"
            and entry.get("lot") == lot and entry.get("task") == task
            and progress.note_data(entry).get("sha") == commit
            and progress.note_data(entry).get("gate") == gate
            and isinstance(progress.note_data(entry).get("success_recovery"), dict)
        ]
        if len(candidates) > 1 or phase == "terminal-recorded" and len(candidates) != 1:
            die(f"{subject} has no one exact helper-owned terminal")
        if candidates:
            terminal_index, terminal = candidates[0]
            progress.validate_attempt_succeeded_entry(entries, terminal_index, terminal)
            recovery = progress.note_data(terminal)["success_recovery"]
            terminal_owner = dict(recovery)
            terminal_owner_sha = terminal_owner.pop("owner_sha256", None)
            if terminal_owner != owner or terminal_owner_sha != progress.canonical_digest(owner):
                die(f"{subject} changes its terminal-owned recovery account")
            attempt = progress.note_data(terminal).get("attempt")
            before = terminal_index
        else:
            attempt = select_attempt(entries, lot, task)
            before = len(entries)
    else:
        attempt = select_attempt(entries, lot, task)
        before = len(entries)
    expected = progress.attempt_success_recovery_account(
        entries, before, lot, task, attempt, commit, gate, subject,
        live=True, recorded=owner,
    )
    canonical_ref = f"refs/bwr/{WORKSPACE.name}/{lot}/task-{task}"
    ref_value = stable_ref_state(canonical_ref)
    if expected["stable_ref"] != canonical_ref:
        die(f"{subject} changes its canonical stable task ref")
    if phase == "owned" and ref_value is not None:
        die(f"{subject} published a stable ref before its owned phase gesture")
    if phase == "ref-writing" and ref_value not in {None, commit}:
        die(f"{subject} has a foreign stable ref during publication")
    if phase in {"ref-published", "terminal-writing", "terminal-recorded"} \
            and ref_value != commit:
        die(f"{subject} has no exact canonical stable task ref")
    return marker, expected, terminal


def prepare(lot, task, commit, gate):
    if MARKER.exists() or MARKER.is_symlink():
        generation = read_marker_generation("the retained attempt success")
        reproject_marker(
            generation, lot, task, commit, gate, "the retained attempt success",
        )
        return generation

    with open(PHYSICAL_LOCK, "a+b") as physical_lock:
        fcntl.flock(physical_lock, fcntl.LOCK_EX)
        with open(progress.JOURNAL_LOCK, "a+b") as journal_lock:
            fcntl.flock(journal_lock, fcntl.LOCK_EX)
            if MARKER.exists() or MARKER.is_symlink():
                return prepare(lot, task, commit, gate)
            refuse_competing_owner()
            entries = progress.journal_entries()
            stable_ref = f"refs/bwr/{WORKSPACE.name}/{lot}/task-{task}"
            existing = git("rev-parse", "--verify", "--quiet", stable_ref, ok=False)
            if existing.returncode == 0 and existing.stdout.strip() != commit:
                die("the stable task ref names another commit")
            if existing.returncode not in {0, 1}:
                die("the stable task ref cannot be read")
            existing_terminal = exact_existing_terminal(entries, lot, task, commit, gate)
            if existing_terminal:
                if existing.returncode != 0:
                    die("the durable success terminal has no exact stable task ref")
                if existing_terminal != "helper":
                    progress.validate_construction_verdict_history(entries)
                return None
            if existing.returncode == 0:
                # A stable ref without a terminal is the closed legacy crash
                # prefix. It has no helper-owned admission marker, so it must
                # still pass the complete historical gate before recovery.
                progress.validate_construction_verdict_history(entries)
            attempt = select_attempt(entries, lot, task)
            owner = progress.attempt_success_recovery_account(
                entries, len(entries), lot, task, attempt, commit, gate,
                "the task success", live=True,
            )
            marker = {
                "schema": 1,
                "operation": "attempt-success",
                "phase": "ref-published" if existing.returncode == 0 else "owned",
                "owner": owner,
                "owner_sha256": progress.canonical_digest(owner),
            }
            test_physical_barrier("success-before-marker")
            descriptor = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                json.dump(marker, target, sort_keys=True, separators=(",", ":"))
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            fsync_directory(WORKSPACE)
            test_physical_barrier("success-marker-published")
            return read_marker_generation("the published attempt success owner")


def append_terminal(generation, owner):
    me = progress.whoami()
    context = progress.caller_context(me)
    identity = owner["start_account"]["attempt_identity"]

    def build(entries):
        current = require_marker_generation(
            generation, "the attempt success terminal",
        )
        if current["owner"] != owner or current["phase"] != "terminal-writing":
            die("the retained success owner changed before its terminal")
        if terminal_matches(entries, owner):
            return None
        expected = progress.attempt_success_recovery_account(
            entries, len(entries), identity["lot"], identity["task"], identity["attempt"],
            owner["commit"], owner["gate"], "the attempt success terminal",
            live=True, recorded=owner,
        )
        recovery = {**expected, "owner_sha256": progress.canonical_digest(expected)}
        data = {
            "attempt": identity["attempt"], "lot": identity["lot"],
            "sha": owner["commit"], "gate": owner["gate"],
            "success_recovery": recovery,
        }
        if owner["retry"] is not None:
            data["retry"] = owner["retry"]
        candidate = progress.event_entry(
            me["session_id"], "note", kind="attempt.succeeded",
            lot=identity["lot"], task=identity["task"], data=data, **{
                key: value for key, value in context.items()
                if key not in {"lot", "task", "attempt"}
            },
        )
        progress.validate_attempt_succeeded_entry([*entries, candidate], len(entries), candidate)
        return candidate

    # Avoid a duplicate write when a prior process appended the terminal but
    # died before advancing the marker.
    entries = progress.journal_entries()
    if terminal_matches(entries, owner):
        return

    def required_builder(entries):
        candidate = build(entries)
        if candidate is None:
            die("the attempt success terminal appeared during its locked append")
        return candidate

    progress.write_validated_line(required_builder, attempt_success=True)


def finish(lot, task, commit, gate):
    generation = prepare(lot, task, commit, gate)
    if generation is None:
        print(f"task-{task} {commit} (already recorded)")
        return
    marker, owner, _ = reproject_marker(
        generation, lot, task, commit, gate, "the attempt success phase",
    )
    stable_ref = f"refs/bwr/{WORKSPACE.name}/{lot}/task-{task}"
    test_interrupt_after(marker["phase"])
    if marker["phase"] == "owned":
        generation = set_phase(generation, "ref-writing")
        marker, owner, _ = reproject_marker(
            generation, lot, task, commit, gate, "the attempt success phase",
        )
    if marker["phase"] == "ref-writing":
        require_marker_generation(generation, "the attempt success ref publication")
        existing = stable_ref_state(stable_ref)
        if existing is None:
            update = git("update-ref", stable_ref, commit, "", ok=False)
            if update.returncode != 0:
                die(update.stderr.strip() or "the stable task ref publication failed")
        elif existing != commit:
            die("the stable task ref changed before publication")
        test_interrupt_after("ref-written")
        reproject_marker(
            generation, lot, task, commit, gate, "the attempt success ref phase transition",
        )
        test_substitute_marker_after("ref-written")
        generation = set_phase(generation, "ref-published")
        marker, owner, _ = reproject_marker(
            generation, lot, task, commit, gate, "the attempt success phase",
        )
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "ref-published":
        if stable_ref_state(stable_ref) != commit:
            die("the stable task ref changed before the success terminal")
        generation = set_phase(generation, "terminal-writing")
        marker, owner, _ = reproject_marker(
            generation, lot, task, commit, gate, "the attempt success phase",
        )
    if marker["phase"] == "terminal-writing":
        require_marker_generation(generation, "the attempt success terminal publication")
        append_terminal(generation, owner)
        test_interrupt_after("terminal-written")
        reproject_marker(
            generation, lot, task, commit, gate,
            "the attempt success terminal phase transition",
        )
        test_substitute_marker_after("terminal-written")
        generation = set_phase(generation, "terminal-recorded")
        marker, owner, _ = reproject_marker(
            generation, lot, task, commit, gate, "the attempt success phase",
        )
        test_interrupt_after(marker["phase"])
    if marker["phase"] == "terminal-recorded":
        reproject_marker(
            generation, lot, task, commit, gate, "the attempt success cleanup",
        )
        test_substitute_marker_after("before-cleanup")
        require_marker_generation(generation, "the attempt success cleanup")
        if INFLIGHT.exists():
            identity = owner["start_account"]["attempt_identity"]
            current = progress.active_attempt_identity(
                {key: identity[key] for key in ("lot", "task", "attempt")},
                "the attempt success cleanup",
            )
            if current != identity:
                die("attempt-in-flight changed before the success cleanup")
            INFLIGHT.unlink()
            fsync_directory(WORKSPACE)
        require_marker_generation(generation, "the attempt success cleanup")
        MARKER.unlink()
        fsync_directory(WORKSPACE)
    print(f"task-{task} {commit}")


def recorded_only(lot, task, commit, gate):
    entries = progress.journal_entries()
    stable_ref = f"refs/bwr/{WORKSPACE.name}/{lot}/task-{task}"
    if stable_ref_state(stable_ref) != commit:
        die("the completed attempt success has no exact stable task ref")
    if exact_existing_terminal(entries, lot, task, commit, gate) != "helper":
        die("the completed attempt success has no exact helper-owned terminal")
    print(f"task-{task} {commit} (already recorded)")


def main():
    recorded = len(sys.argv) == 6 and sys.argv[1] == "--recorded-only"
    offset = 2 if recorded else 1
    if len(sys.argv) != offset + 4:
        die("usage: attempt_success.py [--recorded-only] <lot> <task> <commit> <gate operation>")
    try:
        task = int(sys.argv[offset + 1])
    except ValueError:
        die("the task number must be a positive integer")
    if task < 1:
        die("the task number must be a positive integer")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(OWNER_LOCK, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            die("the attempt success lock is not one real regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        test_owner_barrier()
        arguments = sys.argv[offset:offset + 4]
        if recorded:
            recorded_only(arguments[0], task, arguments[2], arguments[3])
        else:
            finish(arguments[0], task, arguments[2], arguments[3])
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    main()
