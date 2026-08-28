#!/usr/bin/env python3
"""The run's journal: <workspace>/progress.jsonl, one JSON line per event,
appended and never rewritten.

Usage:
  progress.py session-started <id>
  progress.py session-status  <id> <status>
  progress.py session-retired <id> <status> [--archive] [--hide]
  progress.py subagent-started <kind> [--mandate S] [--task N] [--round K]
  progress.py subagent-ended   <kind> [--mandate S] [--task N] [--round K] [--data '<json>']
  progress.py subagents-open
  progress.py note <kind> [--mandate S] [--task N] [--round K]
                   [--text "<sentence>" | --text-file PATH] [--data '<json>']
  progress.py notes

The script resolves alone everything it can resolve alone: the caller (`twicc
whoami`), the workspace (two directories above this file), and the context —
the `bwr` annotations of whoever the event describes: the target's for the
`session-*` events, the caller's for `note` and `subagent-*`. The context
flags override or complete what was derived.

The `session-*` commands also PERFORM what they record, through the `twicc`
CLI: a record produced by the act itself cannot drift from it. A refused or
failed call journals nothing — the journal never carries an act that did not
happen. `notes` prints the notes back, and writes nothing.

The rules for calling this script are in progress-rules.md, next to it.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from authority_precedence import (
    AuthorityPrecedenceError,
    authority_boundary_identity,
    global_answer_state,
    latest_owner_generation,
    validate_breach_restoration,
    validate_conflict_generation,
    validate_global_authority_precedence,
    validate_recheck_generation,
    validate_spec_loop_generation,
)

# The two closed vocabularies. An unknown name is refused: a vocabulary that
# is not enforced is not a vocabulary, and a dashboard cannot count what it
# cannot name.
NOTE_KINDS = {
    "run.started", "spec.written", "round.opened", "report.received",
    "fixer.returned", "spec.committed", "plan.written", "attempt.failed",
    "attempt.succeeded", "attempt.launch.abandoned",
    "lot.built", "pass.opened", "pass.closed", "sublot.allocated",
    "sublot.opened", "lot.delivered", "amendment.opened",
    "amendment.written", "sweep.reported",
    "amendment.committed", "paused", "resumed", "aborted", "cleanup.started", "handover",
    "ruling", "ruling.ready", "decision.refuted", "decision.escalated", "session.replaced",
    "decision.batch.opened", "decision.batch.sourced", "decision.batch.settled",
    "decision.batch.ready", "decision.recheck.completed", "decision.batch.supplemented",
    "decision.conflict.opened", "decision.conflict.sourced", "decision.conflict.settled",
    "decision.conflict.ready",
    "spec.breach.opened", "spec.breach.corrected", "spec.breach.restored", "spec.edit.ready",
    "ruling.applied", "decision.batch.closed",
    "not-converging", "sublot.oversized", "reach.not-closed", "reach.recovery.authorized",
    "bound.spent",
    "rewind.done", "fixer.dispatched", "verdict.consumed", "design.review.resolved",
    "design.review.blocked",
    "code.review.resolved", "code.review.blocked", "amendment.attempt.settled",
}
SUBAGENT_KINDS = {
    "gate-runner", "completeness", "design-checker", "code-checker",
    "diagnostic", "finding-verifier", "consolidation",
}
STATUSES = ("working", "idle", "blocked", "done", "failed", "cancelled", "superseded")
TERMINAL = ("done", "failed", "cancelled", "superseded")
DIRECT_RULING_ROUTES = {
    "closed", "spec-in-place", "amendment", "spec-fixer", "amendment-fixer",
}
BATCH_ROUTES = {"closed", "sublot", "spec-in-place", "amendment"}
BATCH_CLOSE_OUTCOMES = {"no-correction", "sublot"}
DIRECT_AUTHORITY_KINDS = {"ruling.ready", "decision.conflict.ready"}
PRODUCT_REVIEW_MANDATES = ("unlooked", "user", "meaning", "quality", "coverage")
AMENDMENT_ORIGINS = {"construction", "product-review"}
AMENDMENT_SECTIONS = (
    "Order and return", "Decisions", "Why", "What it changes",
    "What it preserves", "Where it was raised",
)
AMENDMENT_REACH_LABELS = (
    "hops walked",
    "places found",
    "phrasings swept for every changed thing",
    "places reached by purpose and not by name",
    "tests asserting any changed behaviour",
    "frontier",
)

# One CLI command reads one immutable journal/workspace generation until its
# admission succeeds. Cache only exact historical projectors inside that
# command. Direct module callers and the next process always start uncached.
COMMAND_VALIDATION_CACHE = None
AMENDMENT_REACH_COMPLETION_TEMPLATE = (
    "COMPLETION (6 items)",
    "- [ ] hops walked — <N> hops, last one returning <M> new places",
    "- [ ] places found — <N> total: <N> kept, <N> moved, <N> removed, <N> DECISION",
    "- [ ] phrasings swept for every changed thing — active <B1/D1, R2>; <N> unique terms or hits",
    "- [ ] places reached by purpose and not by name — <N>",
    "- [ ] tests asserting any changed behaviour — <N> found, <N> still asserting it after the amendment",
    "- [ ] frontier — closed at hop <N>",
)
REACH_RECOVERY_REASON = "reviewed-contract-correction"
REACH_RECOVERY_TEXT = "The reviewed Reach contract correction authorizes one new physical reviewer."
CONSTRUCTION_CHECKERS = {"design": "design-checker", "code": "code-checker"}
CONSTRUCTION_CHECKER_ROUNDS = {"design": 10, "code": 10}
CONSTRUCTION_CLASSIFICATIONS = {"C3.9a", "C3.9b", "C3.9c", "C3.9d"}
CONSTRUCTION_UNUSABLE_RESULTS = {"error", "empty", "lost", "unusable"}
CODE_CORRECTION_STATUSES = {"corrected", "unchanged"}
CODE_FINAL_RESOLUTION_STATUSES = {"accepted", "refuted", "alternative"}
CODE_BLOCKER_STATUSES = {"contract-blocked", "carried"}
DESIGN_CORRECTION_STATUSES = {"corrected", "unchanged"}
DESIGN_FINAL_RESOLUTION_STATUSES = {"accepted", "refuted", "alternative"}
REPORT_COUNT_KEYS = {"critical", "important", "minor", "decision"}
SPEC_FIRST_MANDATES = ("enumerator", "verifier", "feasibility", "judge")
SPEC_LATER_MANDATES = ("enumerator", "ripple", "verifier", "feasibility", "judge")
SPEC_MANDATES = set(SPEC_LATER_MANDATES) | {"scoped"}
SPEC_FINDING_CLASSES = ("CRITICAL", "IMPORTANT", "MINOR", "DECISION")
SPEC_STATUS_LINE = re.compile(r"^(?:\*\*|__)?Status(?:\*\*|__)?\s*:", re.IGNORECASE)

# The seven context fields a line may carry. `feature`, `schema` and `status`
# stay out: they describe the run or the moment, never the event's subject.
CONTEXT_FIELDS = ("mode", "lot", "task", "attempt", "round", "mandate", "job")
# Canonical key order of a line, after ts/by/event — so the file reads the
# same by hand from the first line to the last.
LINE_FIELDS = ("session", "status", "kind") + CONTEXT_FIELDS + ("archived", "hidden", "text", "data")

# The script lives at <workspace>/prompts/common/progress.py, so the workspace
# needs no argument — it is two directories above.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
JOURNAL = os.path.join(WORKSPACE, "progress.jsonl")
JOURNAL_LOCK = f"{JOURNAL}.lock"
CONSTRUCTION_HISTORY_VALIDATION = os.path.join(
    WORKSPACE, "construction-history-validation.json",
)
CONSTRUCTION_HISTORY_PROJECTOR = "construction-history-v1"
AMENDMENT_SWEEP_PREFLIGHT = os.path.join(WORKSPACE, "amendment-sweep-preflight.json")
AMENDMENT_ATTEMPT_SETTLE_MARKER = os.path.join(
    WORKSPACE, "amendment-attempt-settle-in-progress.json",
)
ATTEMPT_SUCCESS_MARKER = os.path.join(WORKSPACE, "attempt-success-in-progress.json")
BARE_STOP_MARKER = os.path.join(WORKSPACE, "bare-stop-in-progress")
DASHBOARD_DIR = os.path.join(WORKSPACE, "dashboard")
DASHBOARD_COPY = os.path.join(DASHBOARD_DIR, "data", "progress.jsonl")
GATE_CHECK = os.path.join(WORKSPACE, "prompts", "construction", "gate-check.sh")
GATE_REPORT = os.path.join(WORKSPACE, "prompts", "construction", "gate_report.py")
GATE_EXECUTION = os.path.join(WORKSPACE, "prompts", "construction", "gate_execution.py")
CONSTRUCTION_REVIEW = os.path.join(
    WORKSPACE, "prompts", "construction", "construction_review.py",
)
GATE_MARKER = os.path.join(WORKSPACE, "gate-check-in-progress")
REPO = str(Path(WORKSPACE).parent.parent.parent.resolve())

# The CLI resolves WHICH TwiCC instance it talks to from its working directory:
# inside a git worktree that wins over everything. Running from a neutral
# directory lets the inherited TWICC_DATA_DIR decide — and TwiCC exports it
# pointing at the instance that owns these sessions.
TWICC = shlex.split(os.environ.get("TWICC_BIN") or "twicc")
NEUTRAL_CWD = tempfile.gettempdir()
SESSION_VISIBILITY_ATTEMPTS = 21
SESSION_VISIBILITY_DELAY_SECONDS = 0.25


def fail(what, detail=None, journaled=False):
    """A refused or broken call must never look like a recorded event."""
    print(f"**progress ERROR** · {what}")
    if detail:
        print()
        print(f"    {str(detail)[:400]}")
    print()
    if journaled:
        print("**The event WAS journaled**, with what actually succeeded. The step named")
        print("above did not happen — retry the call, or finish it and tell your parent.")
    else:
        print("**NOTHING WAS JOURNALED.** If this command was also performing the act,")
        print("the act did not happen either.")
    sys.exit(1)


def attempt(args):
    """One CLI step that may fail without ending the call — `session-retired`
    has to journal what actually happened before failing loudly."""
    try:
        out = subprocess.run(
            TWICC + args, cwd=NEUTRAL_CWD, capture_output=True, text=True, timeout=90
        )
    except Exception as exc:
        return False, str(exc)
    if out.returncode != 0:
        return False, out.stderr.strip() or out.stdout.strip()
    return True, out.stdout


def run(args):
    ok, out = attempt(args)
    if not ok:
        fail(f"`{' '.join(['twicc'] + args)}` failed", out)
    try:
        return json.loads(out)
    except ValueError as exc:
        fail(f"`{' '.join(args)}` returned unreadable output", f"{exc} — first bytes: {out[:200]!r}")


def created_session(session_id):
    """Read a just-created session across the CLI's short visibility lag.

    The creation result already supplied the authoritative id. Only the exact
    not-found response is transient here. Every other CLI failure stays final.
    """
    command = ["session", session_id]
    not_found = re.compile(
        rf"^(?:Error:\s*)?session\s+['\"]{re.escape(session_id)}['\"]\s+not found\.?$",
        re.IGNORECASE,
    )
    for read_number in range(SESSION_VISIBILITY_ATTEMPTS):
        ok, out = attempt(command)
        if ok:
            try:
                return json.loads(out)
            except ValueError as exc:
                fail(
                    f"`{' '.join(command)}` returned unreadable output",
                    f"{exc} — first bytes: {out[:200]!r}",
                )
        if not not_found.fullmatch(out.strip()):
            fail(f"`{' '.join(['twicc'] + command)}` failed", out)
        if read_number + 1 < SESSION_VISIBILITY_ATTEMPTS:
            time.sleep(SESSION_VISIBILITY_DELAY_SECONDS)
    fail(
        f"`{' '.join(['twicc'] + command)}` stayed temporarily unavailable",
        f"Keep created session id {session_id}. Create no replacement. "
        "After the exact session is readable, retry only this session-started command.",
    )


def whoami():
    """The session running this script. An event nobody signs is an event
    nobody can trust, so a failure here stops everything."""
    me = run(["whoami"])
    if not isinstance(me, dict) or not me.get("session_id"):
        fail("`twicc whoami` returned no session_id", me)
    return me


def context_of(payload):
    """The context fields of one session, read from its `bwr` annotations."""
    bwr = ((payload or {}).get("annotations") or {}).get("bwr") or {}
    return {k: bwr[k] for k in CONTEXT_FIELDS if bwr.get(k) not in (None, "")}


def caller_context(me):
    """`whoami` already carries the caller's session payload; a CLI that
    omits it costs one more call instead of an empty context."""
    payload = me.get("session")
    if not isinstance(payload, dict):
        payload = run(["session", me["session_id"]])
    return context_of(payload)


def with_flag_overrides(context, args):
    """The flags name what the derived context does not describe — a subagent
    working on another actor's subject. They win over the derived value."""
    merged = dict(context)
    for key in ("mandate", "task", "round"):
        value = getattr(args, key, None)
        if value is not None:
            merged[key] = value
    return merged


def parse_data(raw):
    if raw is None or raw == "":
        return None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        fail("`--data` is not valid JSON — the call is refused", f"{exc} — received: {raw[:200]!r}")
    # An object, not any JSON: `--data` carries named, countable values. A
    # list or a bare string lands here exactly when free text went into the
    # wrong flag — that belongs in `--text`.
    if not isinstance(data, dict):
        fail("`--data` must be a JSON object — the call is refused",
             f"expected {{\"key\": value, ...}}, received: {raw[:200]!r}")
    return data


def journal_entries():
    if not os.path.exists(JOURNAL):
        return []
    entries = []
    with open(JOURNAL, "rb") as source:
        for line_number, raw in enumerate(source, 1):
            if not raw.endswith(b"\n"):
                fail("the journal has an incomplete line",
                     f"progress.jsonl line {line_number}")
            try:
                entry = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                fail("the journal has an unreadable line",
                     f"progress.jsonl line {line_number}: {exc}")
            if not isinstance(entry, dict):
                fail("the journal has a non-object line",
                     f"progress.jsonl line {line_number}")
            entries.append(entry)
    return entries


CONSTRUCTION_HISTORY_DEPENDENCY_PAIRS = (
    ("report", "report_sha256"),
    ("manifest", "manifest_sha256"),
    ("result", "result_sha256"),
    ("artifact", "artifact_sha256"),
)
CONSTRUCTION_HISTORY_DEPENDENCY_ROOTS = {"reports"}


def construction_history_dependencies(entries):
    dependencies = {}

    def add(raw_path, expected_sha256):
        if not isinstance(raw_path, str) or not isinstance(expected_sha256, str) \
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            return
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or not relative.parts \
                or relative.parts[0] not in CONSTRUCTION_HISTORY_DEPENDENCY_ROOTS:
            return
        path = exact_real_file(
            WORKSPACE, raw_path, "the validated construction-history dependency",
        )
        actual = sha256_bytes(Path(path).read_bytes())
        if actual != expected_sha256:
            fail("a validated construction-history dependency changed", raw_path)
        previous = dependencies.get(raw_path)
        if previous is not None and previous != expected_sha256:
            fail("a construction-history dependency path has two content generations", raw_path)
        dependencies[raw_path] = expected_sha256

    def walk(value):
        if isinstance(value, dict):
            for path_key, hash_key in CONSTRUCTION_HISTORY_DEPENDENCY_PAIRS:
                add(value.get(path_key), value.get(hash_key))
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    for entry in entries:
        walk(entry)
        data = note_data(entry)
        if isinstance(entry.get("text"), str):
            add(entry["text"], data.get("artifact_sha256"))
    return [
        {"path": path, "sha256": dependencies[path]}
        for path in sorted(dependencies)
    ]


def validate_construction_history_dependencies(dependencies):
    if not isinstance(dependencies, list):
        fail("the construction-history checkpoint has malformed dependencies")
    paths = []
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"path", "sha256"}:
            fail("the construction-history checkpoint has an open dependency account")
        path, expected = dependency.get("path"), dependency.get("sha256")
        if not isinstance(path, str) or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            fail("the construction-history checkpoint has a malformed dependency")
        relative = PurePosixPath(path)
        if relative.is_absolute() or not relative.parts \
                or relative.parts[0] not in CONSTRUCTION_HISTORY_DEPENDENCY_ROOTS:
            fail("the construction-history checkpoint has a foreign dependency", path)
        physical = exact_real_file(
            WORKSPACE, path, "the construction-history checkpoint dependency",
        )
        if sha256_bytes(Path(physical).read_bytes()) != expected:
            fail("a validated construction-history dependency changed", path)
        paths.append(path)
    if paths != sorted(set(paths)):
        fail("the construction-history checkpoint has duplicate or unordered dependencies")


def merge_construction_history_dependencies(previous, current):
    merged = {item["path"]: item["sha256"] for item in previous}
    for dependency in current:
        path, sha256 = dependency["path"], dependency["sha256"]
        if path in merged and merged[path] != sha256:
            fail("a construction-history dependency path has two content generations", path)
        merged[path] = sha256
    return [{"path": path, "sha256": merged[path]} for path in sorted(merged)]


def construction_history_checkpoint_account(raw, line_count, dependencies):
    account = {
        "schema": 1,
        "projector": CONSTRUCTION_HISTORY_PROJECTOR,
        "journal_bytes": len(raw),
        "journal_lines": line_count,
        "journal_sha256": sha256_bytes(raw),
        "dependencies": dependencies,
    }
    return {**account, "account_sha256": sha256_bytes(json.dumps(
        account, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))}


def preflight_construction_history_checkpoint_path():
    if os.path.lexists(CONSTRUCTION_HISTORY_VALIDATION) \
            and (os.path.islink(CONSTRUCTION_HISTORY_VALIDATION)
                 or not os.path.isfile(CONSTRUCTION_HISTORY_VALIDATION)):
        fail("the construction-history checkpoint path has a foreign occupant")


def read_construction_history_checkpoint(raw, entries):
    if not os.path.lexists(CONSTRUCTION_HISTORY_VALIDATION):
        return None
    preflight_construction_history_checkpoint_path()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(CONSTRUCTION_HISTORY_VALIDATION, flags)
        with os.fdopen(descriptor, encoding="utf-8") as source:
            descriptor = None
            checkpoint = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        fail("the construction-history checkpoint is malformed", exc)
    finally:
        if "descriptor" in locals() and descriptor is not None:
            os.close(descriptor)
    if not isinstance(checkpoint, dict) or set(checkpoint) != {
        "schema", "projector", "journal_bytes", "journal_lines",
        "journal_sha256", "dependencies", "account_sha256",
    }:
        fail("the construction-history checkpoint has an open account")
    unsigned = {key: value for key, value in checkpoint.items()
                if key != "account_sha256"}
    if checkpoint.get("account_sha256") != sha256_bytes(json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")):
        fail("the construction-history checkpoint changes its complete account")
    if checkpoint.get("schema") != 1:
        fail("the construction-history checkpoint has an unknown schema")
    if checkpoint.get("projector") != CONSTRUCTION_HISTORY_PROJECTOR:
        return None
    validate_construction_history_dependencies(checkpoint.get("dependencies"))
    byte_count = checkpoint.get("journal_bytes")
    line_count = checkpoint.get("journal_lines")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0 \
            or not isinstance(line_count, int) or isinstance(line_count, bool) \
            or line_count < 0:
        fail("the construction-history checkpoint has invalid journal bounds")
    if byte_count > len(raw) or line_count > raw.count(b"\n"):
        fail("the construction-history checkpoint is ahead of the journal")
    prefix = raw[:byte_count]
    if byte_count and not prefix.endswith(b"\n") \
            or prefix.count(b"\n") != line_count \
            or sha256_bytes(prefix) != checkpoint.get("journal_sha256"):
        fail("the journal changes its validated construction-history prefix")
    return checkpoint


def publish_construction_history_checkpoint(raw, line_count, dependencies):
    preflight_construction_history_checkpoint_path()
    account = construction_history_checkpoint_account(raw, line_count, dependencies)
    payload = (json.dumps(
        account, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".construction-history-validation.", dir=WORKSPACE,
    )
    try:
        with os.fdopen(descriptor, "wb") as target:
            descriptor = None
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        if os.path.lexists(CONSTRUCTION_HISTORY_VALIDATION) \
                and (os.path.islink(CONSTRUCTION_HISTORY_VALIDATION)
                     or not os.path.isfile(CONSTRUCTION_HISTORY_VALIDATION)):
            raise OSError(
                "the construction-history checkpoint path changed during publication"
            )
        os.replace(temporary, CONSTRUCTION_HISTORY_VALIDATION)
        temporary = None
        directory = os.open(WORKSPACE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def journal_notes():
    return [entry for entry in journal_entries() if entry.get("event") == "note"]


def note_data(entry):
    data = entry.get("data")
    return data if isinstance(data, dict) else {}


def journal_line_proof(index):
    with open(JOURNAL, "rb") as source:
        raw_lines = source.read().splitlines()
    if not isinstance(index, int) or isinstance(index, bool) \
            or index < 0 or index >= len(raw_lines):
        fail("a durable journal proof names no existing line", index)
    return f"{index}:{hashlib.sha256(raw_lines[index]).hexdigest()}"


def authority_artifact_sha(entry, subject="a product authority"):
    raw_path = entry.get("text")
    if not isinstance(raw_path, str) or not raw_path:
        fail(f"{subject} has no complete state artifact")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("reports",):
        fail(f"{subject} artifact must be workspace-relative under reports/", raw_path)
    path = os.path.join(WORKSPACE, *relative.parts)
    cursor = WORKSPACE
    for part in relative.parts:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            fail(f"{subject} artifact may not traverse a symlink", raw_path)
    if not os.path.isfile(path):
        fail(f"{subject} artifact is absent", raw_path)
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def validate_authority_artifact(entry, subject):
    expected = note_data(entry).get("artifact_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        fail(f"{subject} has no valid artifact SHA-256")
    actual = authority_artifact_sha(entry, subject)
    if actual != expected:
        fail(f"{subject} artifact changed", {"recorded": expected, "actual": actual})
    return actual


def validate_recheck_artifact(notes, index, entry):
    try:
        validate_recheck_generation(notes, index)
    except AuthorityPrecedenceError as exc:
        fail("a post-commit recheck has no exact bound operation and complete state", exc)
    validate_authority_artifact(entry, "the post-commit recheck")


def validate_spec_loop_artifact(entry):
    validate_authority_artifact(entry, "the SPEC-loop recheck")
    path = exact_real_file(WORKSPACE, entry.get("text"), "the SPEC-loop recheck artifact")
    try:
        with open(path, encoding="utf-8") as source:
            artifact = json.load(source)
    except (UnicodeError, ValueError) as exc:
        fail("the SPEC-loop recheck artifact is not one complete JSON object", exc)
    expected = dict(note_data(entry))
    expected.pop("artifact_sha256", None)
    if artifact != expected:
        fail("the SPEC-loop recheck artifact differs from its complete structured result")


def direct_ruling_generation(ruling, notes=None):
    notes = journal_entries() if notes is None else notes
    try:
        validate_global_authority_precedence(notes)
    except AuthorityPrecedenceError as exc:
        fail("an unfinished global product-authority boundary outranks this direct route", exc)
    answer_events = [entry for entry in notes if entry.get("kind") == "ruling"
                     and note_data(entry).get("ruling") == ruling]
    ready_events = [entry for entry in notes if entry.get("kind") == "ruling.ready"
                    and note_data(entry).get("ruling") == ruling]
    if len(answer_events) != 1 or len(ready_events) != 1:
        fail(f"{ruling} has no one exact ruling and ruling.ready chain")
    route, status = note_data(answer_events[0]).get("route"), "active"
    authority = ready_events[0]
    authority_kind, authority_ref = "ruling.ready", ruling

    for index, entry in enumerate(notes):
        data = note_data(entry)
        kind = entry.get("kind")
        if kind == "decision.recheck.completed" and data.get("accepted") is True \
                and data.get("missing") == [] and data.get("owner") == ruling:
            validate_recheck_artifact(notes, index, entry)
            matches = [action for action in (data.get("actions") or [])
                       if isinstance(action, dict) and action.get("answer") == ruling]
            if len(matches) == 1:
                status = matches[0].get("status", status)
                route = None if status == "superseded" else matches[0].get("route", route)
        elif kind == "decision.conflict.ready":
            try:
                validate_conflict_generation(notes, data["owner"], data["conflict"])
            except AuthorityPrecedenceError as exc:
                fail("a direct ruling conflict authority has no exact complete generation", exc)
            validate_authority_artifact(entry, "the conflict ready state")
            matches = [action for action in (data.get("actions") or [])
                       if isinstance(action, dict) and action.get("answer") == ruling]
            if not matches:
                owner, conflict = data.get("owner"), data.get("conflict")
                settlements = [candidate for candidate in notes
                               if candidate.get("kind") == "decision.conflict.settled"
                               and note_data(candidate).get("owner") == owner
                               and note_data(candidate).get("conflict") == conflict]
                if len(settlements) == 1:
                    matches = [update for update in (note_data(settlements[0]).get("updates") or [])
                               if isinstance(update, dict) and update.get("id") == ruling]
            if len(matches) == 1:
                status = matches[0].get("status", status)
                route = None if status == "superseded" else matches[0].get("route", route)
                authority = entry
                authority_kind = "decision.conflict.ready"
                authority_ref = f"{data.get('owner')}/C{data.get('conflict')}"
    if status not in {"active", "superseded"} \
            or status == "active" and route not in DIRECT_RULING_ROUTES \
            or status == "superseded" and route is not None:
        fail(f"{ruling} has no valid current direct route", {"route": route, "status": status})
    return notes, route, status, {
        "authority_kind": authority_kind,
        "authority_ref": authority_ref,
        "authority_sha256": authority_artifact_sha(authority),
    }


def direct_ruling_state(ruling, notes=None):
    notes, route, status, authority = direct_ruling_generation(ruling, notes)
    if status != "active":
        fail(f"{ruling} is not one active direct route", {"route": route, "status": status})
    return notes, route, authority


def validate_authority(data, subject, expected=None):
    required = ("authority_kind", "authority_ref", "authority_sha256")
    missing = [key for key in required if not data.get(key)]
    if missing:
        fail(f"{subject} lacks its exact authority generation",
             "missing: " + ", ".join(missing))
    if data["authority_kind"] not in DIRECT_AUTHORITY_KINDS:
        fail(f"{subject} has an unknown authority kind", data["authority_kind"])
    if not re.fullmatch(r"[0-9a-f]{64}", str(data["authority_sha256"])):
        fail(f"{subject} has an invalid authority SHA-256", data["authority_sha256"])
    if expected and any(data.get(key) != expected[key] for key in required):
        fail(f"{subject} does not consume the current effective ruling authority", expected)


def exact_matches(items, predicate, subject):
    matches = [item for item in items if predicate(item)]
    if len(matches) != 1:
        fail(f"{subject} requires exactly one durable proof", f"found {len(matches)}")
    return matches[0]


def exact_indexed(items, kind, predicate, subject):
    matches = [(index, entry) for index, entry in enumerate(items)
               if entry.get("kind") == kind and predicate(note_data(entry))]
    if len(matches) != 1:
        fail(f"{subject} requires exactly one durable {kind}", f"found {len(matches)}")
    return matches[0]


# ---------------------------------------------------------------- SPEC state

def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def project_root():
    """The workspace is <repo>/.superpowers/bwr/<run>."""
    return str(Path(WORKSPACE).parent.parent.parent)


def exact_real_file(root, raw_path, subject):
    """Return one regular file below root without following any symlink."""
    if not isinstance(raw_path, str) or not raw_path:
        fail(f"{subject} has no path")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        fail(f"{subject} must be a relative path below its owned root", raw_path)
    cursor = root
    for position, part in enumerate(relative.parts):
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            fail(f"{subject} may not traverse a symlink", raw_path)
        if position < len(relative.parts) - 1 and not os.path.isdir(cursor):
            fail(f"{subject} has a missing or non-directory parent", raw_path)
    if not os.path.isfile(cursor) or not stat.S_ISREG(os.stat(cursor, follow_symlinks=False).st_mode):
        fail(f"{subject} is not one real regular file", raw_path)
    return cursor


def spec_written(notes):
    matches = [(index, entry) for index, entry in enumerate(notes)
               if entry.get("kind") == "spec.written"]
    if len(matches) != 1:
        fail("SPEC requires one exact spec.written readiness boundary",
             f"found {len(matches)}")
    return matches[0]


def spec_file_from_written(entry):
    return exact_real_file(project_root(), entry.get("text"), "the specification")


def spec_lot_manifest(payload):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("the specification is not valid UTF-8", exc)
    headings = []
    ordinals = []
    pattern = re.compile(r"^## Lot ([1-9][0-9]*)\s+(?:[-—:]\s*)?\S.*$")
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            headings.append(line)
            ordinals.append(int(match.group(1)))
    if ordinals != list(range(1, len(ordinals) + 1)) or not ordinals:
        fail("the specification needs one exact sequential `## Lot N — title` manifest",
             ordinals)
    return headings


def normalize_spec_written(notes, data, text):
    if any(entry.get("kind") == "spec.written" for entry in notes):
        fail("spec.written already exists for this run")
    if not isinstance(data, dict) or set(data) != {"lots"} \
            or not isinstance(data.get("lots"), int) or isinstance(data.get("lots"), bool) \
            or data["lots"] < 1:
        fail("spec.written must declare one positive lot count", data)
    path = exact_real_file(project_root(), text, "the specification")
    with open(path, "rb") as source:
        payload = source.read()
    manifest = spec_lot_manifest(payload)
    if len(manifest) != data["lots"]:
        fail("spec.written lot count differs from the exact document manifest",
             {"declared": data["lots"], "manifest": manifest})
    return {
        "lots": data["lots"],
        "lot_manifest": manifest,
        "spec_sha256": sha256_bytes(payload),
    }


def validate_spec_written_history(entry):
    data = note_data(entry)
    if set(data) != {"lots", "lot_manifest", "spec_sha256"} \
            or not isinstance(data.get("lots"), int) or isinstance(data.get("lots"), bool) \
            or data["lots"] < 1 \
            or not isinstance(data.get("lot_manifest"), list) \
            or len(data["lot_manifest"]) != data["lots"] \
            or any(not isinstance(item, str) for item in data["lot_manifest"]) \
            or not isinstance(data.get("spec_sha256"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", data["spec_sha256"]):
        fail("spec.written has malformed durable readiness data", data)
    ordinals = []
    for heading in data["lot_manifest"]:
        match = re.fullmatch(r"## Lot ([1-9][0-9]*)\s+(?:[-—:]\s*)?\S.*", heading)
        if not match:
            fail("spec.written has a malformed lot manifest heading", heading)
        ordinals.append(int(match.group(1)))
    if ordinals != list(range(1, data["lots"] + 1)):
        fail("spec.written has a non-sequential lot manifest", ordinals)


def spec_snapshot_relative(round_number):
    return f"reports/spec-review/round-{round_number}-spec.md"


def workspace_output_path(relative, subject):
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or ".." in parsed.parts or parsed.parts[:2] != ("reports", "spec-review"):
        fail(f"{subject} must stay under reports/spec-review/", relative)
    cursor = WORKSPACE
    for part in parsed.parts[:-1]:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            fail(f"{subject} may not traverse a symlink", relative)
        if os.path.lexists(cursor) and not os.path.isdir(cursor):
            fail(f"{subject} has a non-directory parent", relative)
        if not os.path.exists(cursor):
            os.mkdir(cursor)
    leaf = os.path.join(WORKSPACE, *parsed.parts)
    if os.path.islink(leaf) or os.path.lexists(leaf) and not os.path.isfile(leaf):
        fail(f"{subject} has a foreign destination occupant", relative)
    return leaf


def publish_spec_snapshot(round_number, payload):
    relative = spec_snapshot_relative(round_number)
    destination = workspace_output_path(relative, "the immutable SPEC round snapshot")
    if os.path.exists(destination):
        with open(destination, "rb") as source:
            if source.read() != payload:
                fail("the SPEC round snapshot path already carries different bytes", relative)
        return relative
    descriptor, temporary = tempfile.mkstemp(prefix=f".round-{round_number}-spec.", dir=os.path.dirname(destination))
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        if os.path.lexists(destination):
            fail("the SPEC round snapshot destination changed during publication", relative)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return relative


def publish_fixer_spec_snapshot(round_number, payload):
    relative = f"reports/spec-review/round-{round_number}-fixer-spec.md"
    destination = workspace_output_path(relative, "the immutable SPEC fixer-result snapshot")
    if os.path.exists(destination):
        with open(destination, "rb") as source:
            if source.read() != payload:
                fail("the SPEC fixer-result snapshot already carries different bytes", relative)
        return relative
    descriptor, temporary = tempfile.mkstemp(prefix=f".round-{round_number}-fixer-spec.",
                                              dir=os.path.dirname(destination))
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        if os.path.lexists(destination):
            fail("the SPEC fixer-result snapshot destination changed during publication", relative)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return relative


def spec_round_entries(notes, before=None):
    limit = len(notes) if before is None else before
    return [(index, entry) for index, entry in enumerate(notes[:limit])
            if entry.get("kind") == "round.opened"
            and isinstance(note_data(entry).get("round"), int)]


def spec_receipts(notes, opening_index, before, round_number):
    return [(index, entry) for index, entry in enumerate(notes[opening_index + 1:before], opening_index + 1)
            if entry.get("kind") == "report.received"
            and entry.get("round") == round_number
            and entry.get("mandate") in SPEC_MANDATES]


def validate_spec_round_history(notes, opening_index):
    entry = notes[opening_index]
    data = note_data(entry)
    required = {"round", "kind", "mandates", "spec_sha256", "snapshot", "source_kind", "source_ref"}
    if set(data) != required:
        fail("a SPEC round opening has malformed durable data", data)
    round_number = data.get("round")
    if not isinstance(round_number, int) or isinstance(round_number, bool) or round_number < 1:
        fail("a SPEC round opening has no positive round number", round_number)
    earlier = spec_round_entries(notes, opening_index)
    expected_number = earlier[-1][1]["data"]["round"] + 1 if earlier else 1
    if round_number != expected_number:
        fail("SPEC round numbers must be unique and strictly sequential",
             {"expected": expected_number, "actual": round_number})
    expected_kind, expected_mandates, source_kind, source_ref, expected_sha = spec_round_due(
        notes, opening_index
    )
    if data["kind"] != expected_kind or data["mandates"] != list(expected_mandates) \
            or data["source_kind"] != source_kind or data["source_ref"] != source_ref:
        fail("the SPEC round opening does not match the exact phase owed", {
            "expected": {"kind": expected_kind, "mandates": list(expected_mandates),
                         "source_kind": source_kind, "source_ref": source_ref},
            "actual": data,
        })
    if expected_sha is not None and data["spec_sha256"] != expected_sha:
        fail("the SPEC round does not consume its exact source bytes")
    if data["snapshot"] != spec_snapshot_relative(round_number):
        fail("the SPEC round has a wrong immutable snapshot path", data["snapshot"])
    snapshot = exact_real_file(WORKSPACE, data["snapshot"], "the SPEC round snapshot")
    with open(snapshot, "rb") as source:
        actual_sha = sha256_bytes(source.read())
    if actual_sha != data["spec_sha256"]:
        fail("the SPEC round snapshot changed", {"recorded": data["spec_sha256"], "actual": actual_sha})


def spec_round_due(notes, before):
    _, written = spec_written(notes[:before])
    validate_spec_written_history(written)
    rounds = spec_round_entries(notes, before)
    if not rounds:
        return "full", SPEC_FIRST_MANDATES, "spec.written", note_data(written)["spec_sha256"], \
            note_data(written)["spec_sha256"]
    last_index, last = rounds[-1]
    last_data = note_data(last)
    later = notes[last_index + 1:before]
    amendments = [entry for entry in later if entry.get("kind") == "amendment.committed"]
    if amendments:
        latest = amendments[-1]
        ref = note_data(latest).get("sha") or str(note_data(latest).get("amendment"))
        return "full", SPEC_LATER_MANDATES, "amendment.committed", ref, None
    fixers = [entry for entry in later if entry.get("kind") == "fixer.returned"
              and note_data(entry).get("round") == last_data["round"]]
    if fixers:
        latest = fixers[-1]
        return "scoped", ("scoped",), "fixer.returned", f"round-{last_data['round']}", \
            note_data(latest).get("spec_sha256")
    if last_data.get("kind") == "scoped":
        receipts = spec_receipts(notes, last_index, before, last_data["round"])
        if len(receipts) == 1 and sum(
            note_data(receipts[0][1]).get(key, -1) for key in REPORT_COUNT_KEYS
        ) == 0:
            return "full", SPEC_LATER_MANDATES, "round.opened", f"round-{last_data['round']}", \
                last_data["spec_sha256"]
    fail("no new SPEC round is owed by the current phase")


def normalize_spec_round(notes, data):
    validate_spec_history(notes)
    if not isinstance(data, dict) or set(data) != {"round", "mandates"}:
        fail("round.opened must name exactly its round and complete mandate list", data)
    before = len(notes)
    kind, mandates, source_kind, source_ref, expected_sha = spec_round_due(notes, before)
    previous = spec_round_entries(notes)
    expected_round = previous[-1][1]["data"]["round"] + 1 if previous else 1
    if data.get("round") != expected_round or data.get("mandates") != list(mandates):
        fail("round.opened does not match the exact SPEC round owed", {
            "expected_round": expected_round, "expected_mandates": list(mandates), "actual": data,
        })
    _, written = spec_written(notes)
    path = spec_file_from_written(written)
    with open(path, "rb") as source:
        payload = source.read()
    actual_sha = sha256_bytes(payload)
    if expected_sha is not None and actual_sha != expected_sha:
        fail("round.opened sees spec bytes different from its durable source",
             {"expected": expected_sha, "actual": actual_sha})
    snapshot = publish_spec_snapshot(expected_round, payload)
    return {
        "round": expected_round,
        "kind": kind,
        "mandates": list(mandates),
        "spec_sha256": actual_sha,
        "snapshot": snapshot,
        "source_kind": source_kind,
        "source_ref": source_ref,
    }


def completion_template(mandate):
    filename = "fixer-completion.md" if mandate == "fixer" else f"reviewer-{mandate}-completion.md"
    path = os.path.join(WORKSPACE, "prompts", "spec", filename)
    if os.path.islink(path) or not os.path.isfile(path):
        fail(f"the {mandate} completion template is absent or aliased")
    with open(path, encoding="utf-8") as source:
        text = source.read()
    header = re.search(r"^    COMPLETION \(([1-9][0-9]*) items\)$", text, re.MULTILINE)
    labels = re.findall(r"^    - \[ \] (.+?) —", text, re.MULTILINE)
    if not header or int(header.group(1)) != len(labels) or not labels:
        fail(f"the {mandate} completion template is malformed")
    return labels


def audit_completion_block(report_text, mandate, *, require_verdict=True):
    labels = completion_template(mandate)
    lines = report_text.splitlines()
    nonempty = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]
    if not nonempty or nonempty[0][1] != f"COMPLETION ({len(labels)} items)":
        fail(f"the {mandate} report does not open with its exact completion header")
    if len(nonempty) < len(labels) + 1:
        fail(f"the {mandate} report has an incomplete completion block")
    completed = []
    for offset, label in enumerate(labels, 1):
        line = nonempty[offset][1]
        prefix = f"- [x] {label} — "
        if not line.startswith(prefix) or not line[len(prefix):].strip() or "NOT DONE" in line:
            fail(f"the {mandate} completion item is absent or not complete", label)
        completed.append(line)
    next_offset = len(labels) + 1
    verdict = None
    if require_verdict:
        if len(nonempty) <= next_offset or nonempty[next_offset][1] not in {"READY", "NOT READY"}:
            fail(f"the {mandate} report lacks one exact verdict after its completion block")
        verdict = nonempty[next_offset][1]
    return completed, verdict


def spec_report_findings(report_text, subject):
    counts = {key: 0 for key in REPORT_COUNT_KEYS}
    identities = []
    pattern = re.compile(r"^## (CRITICAL|IMPORTANT|MINOR|DECISION) F([1-9][0-9]*)\s+[—-]\s+\S.*$")
    for line in report_text.splitlines():
        if not line.startswith("## "):
            continue
        match = pattern.fullmatch(line)
        if line.startswith(tuple(f"## {kind}" for kind in SPEC_FINDING_CLASSES)) and not match:
            fail(f"{subject} has a finding without the fixed `<CLASS> F<N>` heading", line)
        if match:
            counts[match.group(1).lower()] += 1
            identities.append(int(match.group(2)))
    if identities != list(range(1, len(identities) + 1)):
        fail(f"{subject} has a non-contiguous finding index", identities)
    return counts, [f"F{number}" for number in identities]


def validate_spec_report_entry(notes, index, entry):
    round_number, mandate = entry.get("round"), entry.get("mandate")
    subject = f"SPEC round {round_number} {mandate} report"
    if mandate not in SPEC_MANDATES or not isinstance(round_number, int) or round_number < 1:
        fail(f"{subject} has malformed identity")
    openings = [(position, candidate) for position, candidate in spec_round_entries(notes, index)
                if note_data(candidate).get("round") == round_number]
    if len(openings) != 1 or openings[0][0] != spec_round_entries(notes, index)[-1][0]:
        fail(f"{subject} does not belong to the current exact round")
    opening_index, opening = openings[0]
    opening_data = note_data(opening)
    if mandate not in opening_data["mandates"]:
        fail(f"{subject} is outside the round's exact mandate set")
    duplicates = [candidate for candidate in notes[opening_index + 1:index]
                  if candidate.get("kind") == "report.received"
                  and candidate.get("round") == round_number
                  and candidate.get("mandate") == mandate]
    if duplicates:
        fail(f"{subject} already has an accepted receipt")
    data = note_data(entry)
    required = REPORT_COUNT_KEYS | {"report_sha256", "spec_sha256"}
    if set(data) != required or any(
        not isinstance(data.get(key), int) or isinstance(data.get(key), bool) or data[key] < 0
        for key in REPORT_COUNT_KEYS
    ) or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("report_sha256"))) \
            or data.get("spec_sha256") != opening_data["spec_sha256"]:
        fail(f"{subject} has malformed or stale durable receipt data", data)
    relative = f"reports/spec-review/round-{round_number}-{mandate}.md"
    path = exact_real_file(WORKSPACE, relative, subject)
    with open(path, "rb") as source:
        payload = source.read()
    if sha256_bytes(payload) != data["report_sha256"]:
        fail(f"{subject} changed after acceptance")
    try:
        report_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject} is not valid UTF-8", exc)
    _, verdict = audit_completion_block(report_text, mandate)
    counts, _ = spec_report_findings(report_text, subject)
    if counts != {key: data[key] for key in REPORT_COUNT_KEYS}:
        fail(f"{subject} counts differ from its fixed finding headings",
             {"receipt": data, "report": counts})
    if verdict != ("READY" if sum(counts.values()) == 0 else "NOT READY"):
        fail(f"{subject} verdict contradicts its findings", verdict)
    return counts


def normalize_spec_report(notes, data, round_number, mandate):
    validate_spec_history(notes)
    if not isinstance(data, dict) or set(data) != REPORT_COUNT_KEYS:
        fail("a SPEC report receipt must carry exactly four typed finding counts", data)
    candidate = {
        "kind": "report.received", "round": round_number, "mandate": mandate,
        "data": dict(data),
    }
    relative = f"reports/spec-review/round-{round_number}-{mandate}.md"
    path = exact_real_file(WORKSPACE, relative, "the current SPEC report")
    with open(path, "rb") as source:
        payload = source.read()
    opening = exact_matches(
        notes, lambda entry: entry.get("kind") == "round.opened"
        and note_data(entry).get("round") == round_number,
        f"SPEC round {round_number} opening",
    )
    candidate["data"].update(
        report_sha256=sha256_bytes(payload), spec_sha256=note_data(opening).get("spec_sha256")
    )
    validate_spec_report_entry(notes + [candidate], len(notes), candidate)
    return candidate["data"]


def current_spec_round(notes, before):
    rounds = spec_round_entries(notes, before)
    if not rounds:
        fail("the fixer return has no current SPEC round")
    return rounds[-1]


def fixer_assignment_ids(notes, opening_index, before, round_number):
    opening = notes[opening_index]
    ids = []
    for mandate in note_data(opening)["mandates"]:
        receipts = [(index, entry) for index, entry in enumerate(notes[opening_index + 1:before], opening_index + 1)
                    if entry.get("kind") == "report.received" and entry.get("round") == round_number
                    and entry.get("mandate") == mandate]
        if len(receipts) != 1:
            fail(f"fixer return requires one accepted {mandate} report for round {round_number}")
        validate_spec_report_entry(notes, receipts[0][0], receipts[0][1])
        total = sum(note_data(receipts[0][1])[key] for key in REPORT_COUNT_KEYS)
        ids.extend(f"R{round_number}/{mandate}/F{number}" for number in range(1, total + 1))
    previous_returns = [index for index, entry in enumerate(notes[:before])
                        if entry.get("kind") == "fixer.returned"]
    after = previous_returns[-1] + 1 if previous_returns else 0
    for entry in notes[after:before]:
        if entry.get("kind") != "fixer.dispatched":
            continue
        dispatch_data = note_data(entry)
        if re.fullmatch(r"R[1-9][0-9]*", str(dispatch_data.get("ruling"))):
            ids.append(f"ruling-{dispatch_data['ruling']}")
        elif isinstance(entry.get("text"), str) and entry["text"]:
            ids.append(f"dispatch-{sha256_bytes(entry['text'].encode('utf-8'))[:16]}")
    if len(ids) != len(set(ids)):
        fail("the fixer assignment set contains a duplicate durable identity", ids)
    if not ids:
        fail("fixer.returned has no current finding or dispatch assignment")
    return ids


def parse_fixer_account(report_text, subject):
    lines = report_text.splitlines()
    try:
        start = lines.index("## Correction account") + 1
    except ValueError:
        fail(f"{subject} has no fixed correction account")
    account = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if not line.strip():
            continue
        match = re.fullmatch(r"- ([A-Za-z0-9./-]+) \| (APPLIED|DECLINED) \| (\S.*) \| (\S.*)", line)
        if not match:
            fail(f"{subject} has a malformed correction-account line", line)
        account.append({"id": match.group(1), "outcome": match.group(2),
                        "evidence": match.group(3), "edit": match.group(4), "line": line})
    if not account:
        fail(f"{subject} has an empty correction account")
    return account


def validate_fixer_completion(lines, received, applied, declined, self_count, subject):
    patterns = {
        "findings": rf"^- \[x\] findings — {received} received, {applied} applied, {declined} declined$",
        "self-detected items": rf"^- \[x\] self-detected items — {self_count}$",
        "blocked on a human decision": r"^- \[x\] blocked on a human decision — 0$",
    }
    for label, pattern in patterns.items():
        matches = [line for line in lines if re.fullmatch(pattern, line)]
        if len(matches) != 1:
            fail(f"{subject} completion block does not account for {label}")


def validate_fixer_return_entry(notes, index, entry, current_spec_payload=None):
    data = note_data(entry)
    required = {"round", "applied", "declined", "self_detected", "report_sha256",
                "decisions_sha256", "spec_sha256", "spec_snapshot"}
    if set(data) != required or any(
        not isinstance(data.get(key), int) or isinstance(data.get(key), bool) or data[key] < 0
        for key in ("round", "applied", "declined", "self_detected")
    ) or data["round"] < 1 or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(data.get(key)))
        for key in ("report_sha256", "decisions_sha256", "spec_sha256")
    ):
        fail("fixer.returned has malformed durable proof data", data)
    opening_index, opening = current_spec_round(notes, index)
    round_number = note_data(opening)["round"]
    if data["round"] != round_number:
        fail("fixer.returned does not consume the current exact SPEC round")
    if any(candidate.get("kind") == "fixer.returned"
           and note_data(candidate).get("round") == round_number for candidate in notes[:index]):
        fail(f"SPEC round {round_number} already has a fixer return")
    try:
        validate_global_authority_precedence(notes[:index])
    except AuthorityPrecedenceError as exc:
        fail("fixer.returned is blocked by unfinished product authority", exc)
    expected = fixer_assignment_ids(notes, opening_index, index, round_number)
    report_relative = f"reports/spec-review/round-{round_number}-fixer.md"
    report_path = exact_real_file(WORKSPACE, report_relative, "the SPEC fixer return report")
    with open(report_path, "rb") as source:
        report_payload = source.read()
    if sha256_bytes(report_payload) != data["report_sha256"]:
        fail("the SPEC fixer return report changed after acceptance")
    try:
        report_text = report_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("the SPEC fixer return report is not UTF-8", exc)
    completion, _ = audit_completion_block(report_text, "fixer", require_verdict=False)
    account = parse_fixer_account(report_text, "the SPEC fixer return report")
    source = [item for item in account if not re.fullmatch(r"SELF[1-9][0-9]*", item["id"])]
    self_items = [item for item in account if re.fullmatch(r"SELF[1-9][0-9]*", item["id"])]
    if [item["id"] for item in source] != expected:
        fail("the SPEC fixer account does not cover the exact immutable assignment set",
             {"expected": expected, "actual": [item["id"] for item in source]})
    if [item["id"] for item in self_items] != [f"SELF{number}" for number in range(1, len(self_items) + 1)] \
            or any(item["outcome"] != "APPLIED" for item in self_items):
        fail("the SPEC fixer self-detected account is malformed")
    applied = sum(item["outcome"] == "APPLIED" for item in source)
    declined = sum(item["outcome"] == "DECLINED" for item in source)
    if (data["applied"], data["declined"], data["self_detected"]) != (
        applied, declined, len(self_items)
    ):
        fail("fixer.returned counts contradict its complete correction account")
    validate_fixer_completion(completion, len(expected), applied, declined, len(self_items),
                              "the SPEC fixer return")
    decisions_path = exact_real_file(
        WORKSPACE, "reports/spec-review/decisions-log.md", "the SPEC decisions log"
    )
    with open(decisions_path, "rb") as source_file:
        decisions_payload = source_file.read()
    decisions_text = decisions_payload.decode("utf-8")
    if any(item["line"] not in decisions_text for item in account):
        fail("the SPEC decisions log omits a fixer correction-account line")
    expected_snapshot = f"reports/spec-review/round-{round_number}-fixer-spec.md"
    if data["spec_snapshot"] != expected_snapshot:
        fail("fixer.returned has a wrong immutable spec-result snapshot")
    if current_spec_payload is None:
        snapshot = exact_real_file(WORKSPACE, expected_snapshot, "the SPEC fixer-result snapshot")
        with open(snapshot, "rb") as source_file:
            snapshot_payload = source_file.read()
    else:
        snapshot_payload = current_spec_payload
    if sha256_bytes(snapshot_payload) != data["spec_sha256"]:
        fail("the immutable fixer-result spec bytes changed")


def normalize_fixer_return(notes, data, round_number):
    validate_spec_history(notes)
    if not isinstance(data, dict) or set(data) != {"applied", "declined"} \
            or any(not isinstance(data.get(key), int) or isinstance(data.get(key), bool)
                   or data[key] < 0 for key in ("applied", "declined")):
        fail("fixer.returned must carry exactly typed applied and declined counts", data)
    opening_index, opening = current_spec_round(notes, len(notes))
    if round_number != note_data(opening)["round"]:
        fail("fixer.returned --round must name the current SPEC round")
    report_relative = f"reports/spec-review/round-{round_number}-fixer.md"
    report_path = exact_real_file(WORKSPACE, report_relative, "the SPEC fixer return report")
    decisions_path = exact_real_file(
        WORKSPACE, "reports/spec-review/decisions-log.md", "the SPEC decisions log"
    )
    _, written = spec_written(notes)
    spec_path = spec_file_from_written(written)
    with open(report_path, "rb") as source:
        report_sha = sha256_bytes(source.read())
    with open(decisions_path, "rb") as source:
        decisions_sha = sha256_bytes(source.read())
    with open(spec_path, "rb") as source:
        spec_payload = source.read()
    spec_sha = sha256_bytes(spec_payload)
    spec_snapshot = f"reports/spec-review/round-{round_number}-fixer-spec.md"
    candidate_data = {
        "round": round_number, "applied": data["applied"], "declined": data["declined"],
        "self_detected": 0, "report_sha256": report_sha,
        "decisions_sha256": decisions_sha, "spec_sha256": spec_sha,
        "spec_snapshot": spec_snapshot,
    }
    # Parse once to derive the self-detected count, then run the complete validator.
    with open(report_path, encoding="utf-8") as source:
        account = parse_fixer_account(source.read(), "the SPEC fixer return report")
    candidate_data["self_detected"] = sum(
        bool(re.fullmatch(r"SELF[1-9][0-9]*", item["id"])) for item in account
    )
    candidate = {"kind": "fixer.returned", "data": candidate_data}
    validate_fixer_return_entry(
        notes + [candidate], len(notes), candidate, current_spec_payload=spec_payload
    )
    publish_fixer_spec_snapshot(round_number, spec_payload)
    return candidate_data


def validate_spec_history(notes, before=None):
    limit = len(notes) if before is None else before
    relevant = notes[:limit]
    _, written = spec_written(relevant)
    validate_spec_written_history(written)
    for index, entry in enumerate(relevant):
        if entry.get("kind") == "round.opened" and isinstance(note_data(entry).get("round"), int):
            validate_spec_round_history(relevant, index)
        elif entry.get("kind") == "report.received" and entry.get("round") is not None \
                and entry.get("mandate") in SPEC_MANDATES:
            validate_spec_report_entry(relevant, index, entry)
        elif entry.get("kind") == "fixer.returned" and "round" in note_data(entry):
            validate_fixer_return_entry(relevant, index, entry)


def status_only_change(reviewed, current):
    if reviewed == current:
        return True
    try:
        old_lines = reviewed.decode("utf-8").splitlines(keepends=True)
        new_lines = current.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return False
    if len(old_lines) != len(new_lines):
        return False
    changed = [index for index, pair in enumerate(zip(old_lines, new_lines)) if pair[0] != pair[1]]
    return len(changed) == 1 and SPEC_STATUS_LINE.match(old_lines[changed[0]]) \
        and SPEC_STATUS_LINE.match(new_lines[changed[0]])


def spec_close_state(spec_argument=None):
    notes = journal_entries()
    validate_spec_history(notes)
    try:
        validate_global_authority_precedence(notes)
    except AuthorityPrecedenceError as exc:
        fail("the SPEC close is blocked by unfinished product authority", exc)
    _, written = spec_written(notes)
    spec_path = spec_file_from_written(written)
    if spec_argument is not None:
        argument_real = os.path.realpath(os.path.join(project_root(), spec_argument)
                                         if not os.path.isabs(spec_argument) else spec_argument)
        if argument_real != os.path.realpath(spec_path):
            fail("the SPEC close argument is not the one ready specification", spec_argument)
    rounds = spec_round_entries(notes)
    if not rounds:
        fail("the SPEC close has no reviewed round")
    opening_index, opening = rounds[-1]
    opening_data = note_data(opening)
    if opening_data.get("kind") != "full" or opening_data.get("mandates") != list(
        SPEC_FIRST_MANDATES if opening_data.get("round") == 1 else SPEC_LATER_MANDATES
    ):
        fail("the SPEC close does not follow one exact full round")
    receipts = spec_receipts(notes, opening_index, len(notes), opening_data["round"])
    if len(receipts) != len(opening_data["mandates"]):
        fail("the SPEC close lacks one receipt per final full-round mandate")
    seen = set()
    for index, receipt in receipts:
        mandate = receipt.get("mandate")
        if mandate in seen:
            fail("the SPEC close has duplicate final-round receipts", mandate)
        seen.add(mandate)
        counts = validate_spec_report_entry(notes, index, receipt)
        if sum(counts.values()) != 0:
            fail("the SPEC close's final full round is not finding-free", mandate)
    if seen != set(opening_data["mandates"]):
        fail("the SPEC close's final full round is incomplete", sorted(seen))
    later = notes[opening_index + 1:]
    if any(entry.get("kind") in {"fixer.returned", "fixer.dispatched"} for entry in later):
        fail("the SPEC close has unresolved fixer work after its final full round")
    snapshot = exact_real_file(WORKSPACE, opening_data["snapshot"], "the final SPEC snapshot")
    with open(snapshot, "rb") as source:
        reviewed = source.read()
    with open(spec_path, "rb") as source:
        current = source.read()
    if not status_only_change(reviewed, current):
        fail("the SPEC close changed normative bytes after the final full round")
    return opening_data["round"], opening_data["spec_sha256"], sha256_bytes(current)


def batch_source_items(data, batch):
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        fail(f"decision batch B{batch} has no structured immutable item index")
    items = {}
    for item in raw_items:
        if not isinstance(item, dict):
            fail(f"decision batch B{batch} has a malformed source item", item)
        identity, verdict = item.get("id"), item.get("verdict")
        if not isinstance(identity, str) or not re.fullmatch(r"[FD][1-9][0-9]*", identity) \
                or verdict not in {"confirmed", "refuted"} or identity in items:
            fail(f"decision batch B{batch} has a malformed or duplicate source item", item)
        items[identity] = verdict
    for prefix in ("F", "D"):
        ordinals = sorted(int(identity[1:]) for identity in items if identity.startswith(prefix))
        if ordinals != list(range(1, len(ordinals) + 1)):
            fail(f"decision batch B{batch} has a non-contiguous {prefix}<N> source index")
    decisions = data.get("decisions")
    expected_decisions = [identity for identity in items if identity.startswith("D")]
    if not isinstance(decisions, list) or len(decisions) != len(set(decisions)) \
            or set(decisions) != set(expected_decisions):
        fail(f"decision batch B{batch} has an inconsistent DECISION source index")
    return items


def validate_batch_answer(answer, batch, source_items, subject):
    if not isinstance(answer, dict):
        fail(f"{subject} has a malformed answer", answer)
    identity, route = answer.get("id"), answer.get("route")
    if identity not in source_items or not str(identity).startswith("D"):
        fail(f"{subject} names no stable DECISION in batch B{batch}", identity)
    if route not in BATCH_ROUTES:
        fail(f"{subject} has an unknown batch route",
             f"{identity}: {route!r}; use exactly one of: {', '.join(sorted(BATCH_ROUTES))}")
    if not isinstance(answer.get("choice"), str) or not answer["choice"]:
        fail(f"{subject} has no durable human choice", identity)
    return identity, route


def validate_batch_action(action, batch, answered, subject):
    if not isinstance(action, dict):
        fail(f"{subject} has a malformed action", action)
    identity = action.get("answer")
    match = re.fullmatch(rf"B{batch}/(D[1-9][0-9]*)", str(identity))
    if not match or match.group(1) not in answered:
        fail(f"{subject} names no answered decision in batch B{batch}", identity)
    status, route = action.get("status"), action.get("route")
    if status not in {"active", "superseded"}:
        fail(f"{subject} has an unknown answer status", action)
    if status == "active" and route not in BATCH_ROUTES:
        fail(f"{subject} has an unknown active batch route", action)
    if status == "superseded" and route is not None and route not in BATCH_ROUTES:
        fail(f"{subject} has an unknown superseded batch route", action)
    return match.group(1), status, route


def batch_state(notes, batch):
    """Reconstruct one batch's current structured item and answer state."""
    opened_index, _ = exact_indexed(
        notes, "decision.batch.opened", lambda data: data.get("batch") == batch,
        f"decision batch B{batch}",
    )
    sourced_index, sourced = exact_indexed(
        notes, "decision.batch.sourced", lambda data: data.get("batch") == batch,
        f"decision batch B{batch}",
    )
    settled_index, settled = exact_indexed(
        notes, "decision.batch.settled", lambda data: data.get("batch") == batch,
        f"decision batch B{batch}",
    )
    ready_index, _ = exact_indexed(
        notes, "decision.batch.ready", lambda data: data.get("batch") == batch,
        f"decision batch B{batch}",
    )
    if not opened_index < sourced_index < settled_index < ready_index:
        fail(f"decision batch B{batch} has an out-of-order authority chain")

    item_verdicts = batch_source_items(note_data(sourced), batch)
    item_state_indices = {identity: ready_index for identity in item_verdicts}
    generation_kind = "decision.batch.ready"
    generation_ref = f"B{batch}"
    source_items = set(item_verdicts)
    answers = {}
    initial = note_data(settled).get("answers")
    if not isinstance(initial, list):
        fail(f"decision batch B{batch} has no atomic initial answer list")
    for answer in initial:
        identity, route = validate_batch_answer(
            answer, batch, source_items, f"decision.batch.settled for B{batch}"
        )
        if identity in answers:
            fail(f"decision.batch.settled for B{batch} answers {identity} twice")
        answers[identity] = {
            "route": route, "status": "active", "state_index": ready_index,
            "conflict": None,
        }
    initially_confirmed = {identity for identity, verdict in item_verdicts.items()
                           if identity.startswith("D") and verdict == "confirmed"}
    if set(answers) != initially_confirmed:
        fail(f"decision.batch.settled for B{batch} does not answer every live initial DECISION")

    for index, entry in enumerate(notes[ready_index + 1:], ready_index + 1):
        data, kind = note_data(entry), entry.get("kind")
        if kind == "decision.batch.supplemented" and data.get("batch") == batch:
            after_op = data.get("after_op")
            prior_rechecks = [candidate for candidate in notes[:index]
                              if candidate.get("kind") == "decision.recheck.completed"
                              and note_data(candidate).get("batch") == batch
                              and note_data(candidate).get("commit_op") == after_op]
            if len(prior_rechecks) != 1:
                fail(f"decision batch B{batch} has a supplement without its exact recheck")
            supplement = data.get("answers")
            if not isinstance(supplement, list) or not supplement:
                fail(f"decision batch B{batch} has an empty or malformed supplement")
            for answer in supplement:
                identity, route = validate_batch_answer(
                    answer, batch, source_items, f"decision.batch.supplemented for B{batch}"
                )
                if identity in answers:
                    fail(f"decision batch B{batch} answers {identity} more than once")
                answers[identity] = {
                    "route": route, "status": "active", "state_index": index,
                    "conflict": None,
                }
            generation_kind = "decision.batch.supplemented"
            generation_ref = after_op
        elif kind == "decision.recheck.completed" and data.get("batch") == batch \
                and "decision" in data and data.get("accepted") is True \
                and data.get("missing") == []:
            validate_recheck_artifact(notes, index, entry)
            items = data.get("items")
            if not isinstance(items, list):
                fail(f"decision batch B{batch} recheck has no complete structured item state")
            rechecked = {}
            for item in items:
                if not isinstance(item, dict) or item.get("id") not in source_items \
                        or item.get("verdict") not in {"confirmed", "refuted"} \
                        or item["id"] in rechecked:
                    fail(f"decision batch B{batch} recheck has a malformed item", item)
                rechecked[item["id"]] = item["verdict"]
            if set(rechecked) != source_items:
                fail(f"decision batch B{batch} recheck is not a complete item replacement state")
            item_verdicts = rechecked
            item_state_indices = {identity: index for identity in rechecked}
            raw_actions = data.get("actions")
            if not isinstance(raw_actions, list):
                fail(f"decision batch B{batch} recheck has no complete action index")
            actions = {}
            for action in raw_actions:
                identity, status, route = validate_batch_action(
                    action, batch, answers, f"decision batch B{batch} recheck"
                )
                if identity in actions:
                    fail(f"decision batch B{batch} recheck repeats {identity}")
                actions[identity] = status, route
            if set(actions) != set(answers):
                fail(f"decision batch B{batch} recheck is not a complete answer replacement state")
            for identity, (status, route) in actions.items():
                answers[identity].update(status=status, route=route, state_index=index)
            generation_kind = "decision.recheck.completed"
            generation_ref = data.get("commit_op")
        elif kind == "decision.conflict.ready":
            try:
                validate_conflict_generation(notes, data["owner"], data["conflict"])
            except AuthorityPrecedenceError as exc:
                fail("a batch conflict authority has no exact complete generation", exc)
            validate_authority_artifact(entry, "the conflict ready state")
            owner, conflict = data.get("owner"), data.get("conflict")
            settlements = [candidate for candidate in notes[:index]
                           if candidate.get("kind") == "decision.conflict.settled"
                           and note_data(candidate).get("owner") == owner
                           and note_data(candidate).get("conflict") == conflict]
            if len(settlements) != 1:
                fail(f"ready conflict {owner}/C{conflict} has no exact settlement")
            updates = note_data(settlements[0]).get("updates")
            if not isinstance(updates, list):
                fail(f"ready conflict {owner}/C{conflict} has no structured updates")
            changed = set()
            for update in updates:
                if not isinstance(update, dict):
                    fail(f"ready conflict {owner}/C{conflict} has a malformed update")
                match = re.fullmatch(rf"B{batch}/(D[1-9][0-9]*)", str(update.get("id")))
                if not match:
                    continue
                identity = match.group(1)
                if identity not in answers or identity in changed:
                    fail(f"ready conflict {owner}/C{conflict} has an invalid B{batch} update")
                status, route = update.get("status"), update.get("route")
                if status not in {"active", "superseded"} \
                        or status == "active" and route not in BATCH_ROUTES \
                        or status == "superseded" and route is not None and route not in BATCH_ROUTES:
                    fail(f"ready conflict {owner}/C{conflict} has an invalid B{batch} action")
                answers[identity].update(
                    status=status, route=route, state_index=index,
                    conflict=(owner, conflict),
                )
                changed.add(identity)
            if owner == f"B{batch}":
                raw_actions = data.get("actions")
                if not isinstance(raw_actions, list):
                    fail(f"ready conflict {owner}/C{conflict} has no complete owner action index")
                owner_actions = {}
                for action in raw_actions:
                    identity, status, route = validate_batch_action(
                        action, batch, answers, f"ready conflict {owner}/C{conflict}"
                    )
                    if identity in owner_actions:
                        fail(f"ready conflict {owner}/C{conflict} repeats {identity}")
                    owner_actions[identity] = status, route
                if set(owner_actions) != set(answers):
                    fail(f"ready conflict {owner}/C{conflict} is not a complete owner state")
                for identity, (status, route) in owner_actions.items():
                    if identity in changed:
                        update = next(item for item in updates
                                      if item.get("id") == f"B{batch}/{identity}")
                        if update.get("status") != status or update.get("route") != route:
                            fail(f"ready conflict {owner}/C{conflict} contradicts its settlement for {identity}")
                    answers[identity].update(status=status, route=route, state_index=index)
            if changed or owner == f"B{batch}":
                generation_kind = "decision.conflict.ready"
                generation_ref = f"{owner}/C{conflict}"
        elif kind == "decision.refuted" and data.get("batch") == batch:
            identity = data.get("item")
            if identity not in source_items:
                fail(f"a keyed refutation names no item in decision batch B{batch}", identity)
            item_verdicts[identity] = "refuted"
            item_state_indices[identity] = index

    for identity, verdict in item_verdicts.items():
        if identity.startswith("D") and verdict == "confirmed" and identity not in answers:
            fail(f"decision batch B{batch} still has unanswered live DECISION {identity}")
    return {
        "items": item_verdicts,
        "item_state_indices": item_state_indices,
        "answers": answers,
        "ready_index": ready_index,
        "generation_kind": generation_kind,
        "generation_ref": generation_ref,
    }


def batch_amendment_members(state, batch):
    return [
        f"B{batch}/{identity}"
        for identity, answer in sorted(
            state["answers"].items(), key=lambda item: int(item[0][1:])
        )
        if answer["status"] == "active" and answer["route"] == "amendment"
    ]


def validate_grouped_amendment_opening(notes, data, *, reject_duplicate=True):
    """Bind one grouped amendment to one exact current batch generation."""
    amendment, batch = data.get("amendment"), data.get("batch")
    if not isinstance(amendment, int) or isinstance(amendment, bool) or amendment < 1:
        fail("a grouped amendment opening must name one positive amendment number")
    if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
        fail("a grouped amendment opening must name one positive decision batch")
    if data.get("origin") != "product-review":
        fail("a grouped amendment opening must have product-review origin")

    state = batch_state(notes, batch)
    expected_members = batch_amendment_members(state, batch)
    if not expected_members:
        fail(f"decision batch B{batch} has no active amendment-route member")
    members = data.get("members")
    if not isinstance(members, list) or any(not isinstance(item, str) for item in members) \
            or members != expected_members:
        fail(
            f"a grouped amendment opening does not name B{batch}'s exact current members",
            {"opening": members, "current": expected_members},
        )
    if data.get("state_kind") != state["generation_kind"] \
            or data.get("state_ref") != state["generation_ref"]:
        fail(
            f"a grouped amendment opening does not bind B{batch}'s current authority generation",
            {"expected_kind": state["generation_kind"],
             "expected_ref": state["generation_ref"]},
        )
    if reject_duplicate and any(
        entry.get("kind") == "amendment.opened"
        and note_data(entry).get("batch") == batch
        and note_data(entry).get("state_kind") == state["generation_kind"]
        and note_data(entry).get("state_ref") == state["generation_ref"]
        for entry in notes
    ):
        fail(f"decision batch B{batch}'s current authority generation already opened an amendment")
    return state, expected_members


def batch_identity(data, subject):
    batch, decision = data.get("batch"), data.get("decision")
    if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1 \
            or not isinstance(decision, str) or not re.fullmatch(r"D[1-9][0-9]*", decision) \
            or data.get("answer") != f"B{batch}/{decision}":
        fail(f"{subject} has an inconsistent B<N>/D<N> identity", data)
    return batch, decision


def real_workspace_file(relative, subject):
    path = WORKSPACE
    for part in PurePosixPath(relative).parts:
        path = os.path.join(path, part)
        if os.path.islink(path):
            fail(f"{subject} may not traverse a symlink", relative)
    if not os.path.isfile(path):
        fail(f"{subject} is not one real regular file", relative)
    return path


def exact_real_directory(root, relative, subject):
    path = root
    for part in PurePosixPath(relative).parts:
        path = os.path.join(path, part)
        if os.path.islink(path):
            fail(f"{subject} may not traverse a symlink", relative)
    if not os.path.isdir(path) or not stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode):
        fail(f"{subject} is not one real directory", relative)
    return path


def amendment_opening_digest(entry):
    data = dict(note_data(entry))
    data.pop("opening_sha256", None)
    payload = {
        "data": data,
        "text": entry.get("text"),
    }
    return sha256_bytes(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def amendment_openings(entries, before=None):
    limit = len(entries) if before is None else before
    return [(index, entry) for index, entry in enumerate(entries[:limit])
            if entry.get("kind") == "amendment.opened"]


CONSTRUCTION_AMENDMENT_SOURCE_KEYS = {
    "schema", "lot", "run", "origin", "plan_written", "commit",
    "plan", "plan_sha256", "spec", "spec_sha256",
}
CONSTRUCTION_AMENDMENT_SUBLOT_SOURCE_KEYS = (
    CONSTRUCTION_AMENDMENT_SOURCE_KEYS | {"spec_source"}
)
CONSTRUCTION_AMENDMENT_SPEC_SOURCE_KEYS = {
    "schema", "route", "opening", "pass", "built", "commit", "plan",
    "plan_sha256", "spec", "spec_sha256", "predecessor_spec_sha256",
}


def committed_regular_payload(commit, relative, subject):
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        fail(f"{subject} has no exact commit")
    if not isinstance(relative, str) or not relative:
        fail(f"{subject} has no repository path")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or parsed.as_posix() != relative or ".." in parsed.parts:
        fail(f"{subject} has no exact repository-relative path", relative)
    listed = subprocess.run(
        ["git", "--literal-pathspecs", "-C", project_root(), "ls-tree", "-z",
         commit, "--", relative],
        capture_output=True,
    )
    raw = listed.stdout.removesuffix(b"\0")
    fields = raw.split(b"\t", 1)
    metadata = fields[0].split(b" ") if len(fields) == 2 else []
    if listed.returncode != 0 or len(fields) != 2 or len(metadata) != 3 \
            or metadata[0] not in {b"100644", b"100755"} \
            or metadata[1] != b"blob" \
            or fields[1] != relative.encode("utf-8"):
        fail(f"{subject} is absent or not a regular file in its committed generation",
             relative)
    content = subprocess.run(
        ["git", "-C", project_root(), "cat-file", "blob", metadata[2].decode("ascii")],
        capture_output=True,
    )
    if content.returncode != 0:
        fail(f"{subject} cannot read its committed bytes", relative)
    return content.stdout


def committed_plan_spec_account(commit, plan_relative, subject, *, fallback_spec=None):
    plan_payload = committed_regular_payload(commit, plan_relative, f"{subject}'s plan")
    try:
        plan_text = plan_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject}'s committed plan is not valid UTF-8", exc)
    _, visible = markdown_structure_lines(plan_text)
    task_headings = [
        index for index, line in enumerate(visible)
        if isinstance(line, str) and re.fullmatch(r"## Task [1-9][0-9]* - .+", line)
    ]
    spec_lines = [
        (index, line[len("Spec: "):]) for index, line in enumerate(visible)
        if isinstance(line, str) and line.startswith("Spec: ")
    ]
    raw_spec_lines = [
        line for line in plan_text.splitlines() if line.lstrip().startswith("Spec:")
    ]
    if len(spec_lines) > 1 or not task_headings \
            or spec_lines and spec_lines[0][0] >= task_headings[0] \
            or not spec_lines and raw_spec_lines:
        fail(f"{subject}'s committed plan has no one exact root Spec source")
    used_fallback = not spec_lines
    if spec_lines:
        spec_relative = spec_lines[0][1]
    elif isinstance(fallback_spec, str) and fallback_spec:
        spec_relative = fallback_spec
    else:
        fail(f"{subject}'s committed plan has no one exact root Spec source")
    spec_payload = committed_regular_payload(
        commit, spec_relative, f"{subject}'s specification",
    )
    return {
        "commit": commit,
        "plan": plan_relative,
        "plan_sha256": sha256_bytes(plan_payload),
        "spec": spec_relative,
        "spec_sha256": sha256_bytes(spec_payload),
    }, used_fallback


def validate_inherited_spec_transition(
        entries, inherited, source, pass_index, subject,
):
    """Authenticate a changed inherited Spec through the latest exact Amendment."""
    if source["spec_sha256"] == inherited["spec_sha256"]:
        return
    inherited_pass_index, _ = journal_entry_from_proof(
        entries, inherited.get("pass"), subject,
    )
    source_built = note_data(entries[pass_index]).get("built")
    openings = {
        note_data(entry).get("amendment"): (index, entry)
        for index, entry in amendment_openings(entries, pass_index)
    }
    commits = []
    for index, entry in enumerate(
            entries[inherited_pass_index + 1:pass_index], inherited_pass_index + 1,
    ):
        data = note_data(entry)
        opening = openings.get(data.get("amendment"))
        if entry.get("kind") != "amendment.committed" or opening is None:
            continue
        opening_data = note_data(opening[1])
        opening_lot = opening_data.get("built") \
            if opening_data.get("origin") == "product-review" \
            else (opening_data.get("construction_source") or {}).get("lot")
        if opening_lot == source_built:
            commits.append((index, entry))
    if not commits:
        fail(f"{subject}'s inherited and source-pass specifications differ")
    commit_index, amendment_commit = commits[-1]
    proof = validate_amendment_commit_entry(entries, commit_index, amendment_commit)
    data = note_data(amendment_commit)
    ancestry = subprocess.run(
        ["git", "-C", project_root(), "merge-base", "--is-ancestor",
         data.get("sha", "-"), source["commit"]],
        capture_output=True,
    )
    if proof.get("spec_path") != source["spec"] \
            or data.get("spec_sha256") != source["spec_sha256"] \
            or ancestry.returncode != 0:
        fail(f"{subject}'s source pass does not preserve its latest exact Amendment Spec")


def construction_lot_origin_and_spec(entries, before, lot, subject):
    cache_key = ("construction-lot-origin-and-spec", before, lot)
    if COMMAND_VALIDATION_CACHE is not None and cache_key in COMMAND_VALIDATION_CACHE:
        return COMMAND_VALIDATION_CACHE[cache_key]
    origin, close = construction_lot_origin_account(entries, before, lot, subject)
    if origin == "root":
        return origin, None
    pass_index, pass_opening, _, _, _, built = close
    source_commit = note_data(pass_opening).get("commit")
    source_plan = f"docs/plans/{os.path.basename(WORKSPACE)}-{built}-plan.md"
    inherited_spec = None
    if "." in built:
        _, inherited_spec = construction_lot_origin_and_spec(
            entries, pass_index, built, subject,
        )
    source, used_fallback = committed_plan_spec_account(
        source_commit, source_plan, subject,
        fallback_spec=inherited_spec["spec"] if inherited_spec is not None else None,
    )
    if used_fallback:
        validate_inherited_spec_transition(
            entries, inherited_spec, source, pass_index, subject,
        )
    result = origin, {
        "schema": 1,
        "route": "sublot-pass",
        "opening": origin,
        "pass": journal_line_proof(pass_index),
        "built": built,
        **source,
    }
    if COMMAND_VALIDATION_CACHE is not None:
        COMMAND_VALIDATION_CACHE[cache_key] = result
    return result


def construction_run_and_plan(entries, before, lot, subject):
    starts = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
        entries[:before]
    ) if candidate.get("kind") == "run.started"]
    run = starts[0][1] if len(starts) == 1 else {}
    run_data = note_data(run)
    if len(starts) != 1 or run.get("event") != "note" \
            or run.get("mode") != "construction" or run.get("job") != "controller" \
            or not isinstance(run.get("lot"), str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*", run["lot"]) \
            or not isinstance(run.get("text"), str) \
            or not run["text"] or set(run_data) != {"cap"} \
            or not isinstance(run_data.get("cap"), int) or isinstance(run_data.get("cap"), bool) \
            or run_data["cap"] < 1:
        fail(f"{subject} has no one exact Construction run opening")
    plans = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
        entries[:before]
    ) if candidate.get("kind") == "plan.written" and candidate.get("lot") == lot]
    if not plans:
        fail(f"{subject} has no published plan for {lot}")
    plan_index, plan = plans[-1]
    plan_data = note_data(plan)
    if plan.get("event") != "note" or plan.get("mode") != "construction" \
            or plan.get("job") != "controller" \
            or not isinstance(plan_data.get("tasks"), int) \
            or isinstance(plan_data.get("tasks"), bool) \
            or plan_data["tasks"] < 1 or not isinstance(plan_data.get("op"), str) \
            or not plan_data["op"]:
        fail(f"{subject}'s latest plan publication is malformed")
    if plan_data.get("schema") != 2 and set(plan_data) != {"tasks", "op"}:
        fail(f"{subject}'s latest plan publication is malformed")
    validate_plan_written_entry(entries, plan_index, plan)
    return starts[0], (plan_index, plan)


def current_construction_amendment_source(entries, context, subject):
    lot = context.get("lot")
    if not isinstance(lot, str) or not re.fullmatch(
        r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot,
    ):
        fail(f"{subject} has no exact Construction lot")
    (run_index, _), (plan_index, _) = construction_run_and_plan(
        entries, len(entries), lot, subject,
    )
    commit_result = subprocess.run(
        ["git", "-C", project_root(), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True, text=True,
    )
    if commit_result.returncode != 0:
        fail(f"{subject} has no current committed tree", commit_result.stderr)
    commit = commit_result.stdout.strip()
    plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-{lot}-plan.md"
    origin, spec_source = construction_lot_origin_and_spec(
        entries, len(entries), lot, subject,
    )
    committed, used_fallback = committed_plan_spec_account(
        commit, plan_relative, subject,
        fallback_spec=spec_source["spec"] if spec_source is not None else None,
    )
    if used_fallback and committed["spec_sha256"] != spec_source["spec_sha256"]:
        fail(f"{subject}'s source-pass and predecessor specifications differ")
    live_plan = exact_real_file(project_root(), plan_relative, f"{subject}'s current plan")
    live_spec = exact_real_file(project_root(), committed["spec"], f"{subject}'s current spec")
    with open(live_plan, "rb") as source:
        live_plan_sha256 = sha256_bytes(source.read())
    with open(live_spec, "rb") as source:
        live_spec_sha256 = sha256_bytes(source.read())
    if live_plan_sha256 != committed["plan_sha256"] \
            or live_spec_sha256 != committed["spec_sha256"]:
        fail(f"{subject} does not start from its exact committed plan and specification")
    source = {
        "schema": 1,
        "lot": lot,
        "run": journal_line_proof(run_index),
        "origin": origin,
        "plan_written": journal_line_proof(plan_index),
        **committed,
    }
    if used_fallback:
        source["spec_source"] = {
            **spec_source,
            "predecessor_spec_sha256": committed["spec_sha256"],
        }
    return source


def validate_construction_amendment_source(entries, before, source, subject):
    if not isinstance(source, dict) or frozenset(source) not in {
        frozenset(CONSTRUCTION_AMENDMENT_SOURCE_KEYS),
        frozenset(CONSTRUCTION_AMENDMENT_SUBLOT_SOURCE_KEYS),
    } or source.get("schema") != 1:
        fail(f"{subject} has no exact frozen Construction spec source")
    lot = source.get("lot")
    if not isinstance(lot, str) or not re.fullmatch(
        r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot,
    ):
        fail(f"{subject} has a malformed Construction lot")
    run_index, run = journal_entry_from_proof(entries, source.get("run"), subject)
    plan_index, plan = journal_entry_from_proof(entries, source.get("plan_written"), subject)
    expected_run, expected_plan = construction_run_and_plan(entries, before, lot, subject)
    if not run_index < plan_index < before or run.get("kind") != "run.started" \
            or run.get("event") != "note" or run.get("mode") != "construction" \
            or plan.get("kind") != "plan.written" or plan.get("lot") != lot \
            or expected_run[0] != run_index or expected_plan[0] != plan_index:
        fail(f"{subject} does not bind its ordered Construction run and plan")
    expected_origin, expected_spec_source = construction_lot_origin_and_spec(
        entries, before, lot, subject,
    )
    committed, used_fallback = committed_plan_spec_account(
        source.get("commit"), source.get("plan"), subject,
        fallback_spec=(
            expected_spec_source["spec"] if expected_spec_source is not None else None
        ),
    )
    if used_fallback and committed["spec_sha256"] != expected_spec_source["spec_sha256"]:
        fail(f"{subject}'s source-pass and predecessor specifications differ")
    expected = {
        "schema": 1,
        "lot": lot,
        "run": source["run"],
        "origin": expected_origin,
        "plan_written": source["plan_written"],
        **committed,
    }
    if used_fallback:
        expected["spec_source"] = {
            **expected_spec_source,
            "predecessor_spec_sha256": committed["spec_sha256"],
        }
        if set(source.get("spec_source") or {}) != CONSTRUCTION_AMENDMENT_SPEC_SOURCE_KEYS:
            fail(f"{subject} has no exact sub-lot Spec provenance account")
    if source != expected:
        fail(f"{subject} changes its frozen Construction spec source", expected)
    return source


def validate_amendment_opening_entry(entries, index, entry):
    data = note_data(entry)
    number = data.get("amendment")
    origin = data.get("origin")
    text = entry.get("text")
    prior = amendment_openings(entries, index)
    if not isinstance(number, int) or isinstance(number, bool) or number != len(prior) + 1:
        fail("an amendment opening has the wrong generation ordinal",
             {"expected": len(prior) + 1, "actual": number})
    if origin not in AMENDMENT_ORIGINS:
        fail("an amendment opening has an unknown origin", origin)
    if not isinstance(text, str) or not text.strip():
        fail("an amendment opening lacks its durable order and return address")
    if data.get("opening_sha256") != amendment_opening_digest(entry):
        fail("an amendment opening does not freeze its exact order and identity")
    if "batch" in data and "ruling" in data:
        fail("an amendment opening cannot belong to both a batch and a direct ruling")

    if prior:
        previous_index, previous = prior[-1]
        commits = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
            entries[previous_index + 1:index], previous_index + 1
        ) if candidate.get("kind") == "amendment.committed"]
        if len(commits) != 1:
            fail("an amendment opening cannot replace an unfinished amendment generation")
        validate_amendment_commit_entry(entries, commits[0][0], commits[0][1])

    if origin == "product-review":
        if "construction_source" in data:
            fail("a product-review amendment opening cannot claim a Construction spec source")
        built = data.get("built")
        if not isinstance(built, str) or not re.fullmatch(
            r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", built
        ):
            fail("a product-review amendment opening has no exact built lot", built)
        opening_index, pass_opening, _, _ = current_pass_opening(
            entries, index, "a product-review amendment opening",
        )
        validate_pass_opening_history(entries, opening_index, "a product-review amendment opening")
        if note_data(pass_opening).get("built") != built:
            fail("a product-review amendment opening names another pass's built lot")
        if pass_closes(entries, opening_index, index):
            fail("a product-review amendment opening follows an already closed pass")
    else:
        if "built" in data:
            fail("a construction amendment opening may not claim a product-review built lot")
        readiness = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
            entries[:index]
        ) if candidate.get("kind") == "spec.written"]
        if readiness:
            _, written = spec_written(entries[:index])
            validate_spec_written_history(written)
            if "construction_source" in data:
                fail("a SPEC-backed amendment opening cannot claim a Construction spec source")
            if not any(candidate.get("kind") == "spec.committed"
                       for candidate in entries[:index]):
                fail("a construction amendment opening precedes the validated specification close")
        else:
            validate_construction_amendment_source(
                entries, index, data.get("construction_source"),
                "a construction-only amendment opening",
            )
        pass_events = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
            entries[:index]
        ) if candidate.get("kind") in {"pass.opened", "pass.closed"}]
        if pass_events and pass_events[-1][1].get("kind") == "pass.opened":
            fail("a construction amendment opening cannot bypass the current product-review pass")
    return data


def normalize_amendment_opened(entries, data, text, context):
    if not isinstance(data, dict):
        fail("amendment.opened requires structured identity data")
    candidate_data = dict(data)
    if candidate_data.get("origin") == "construction" \
            and not any(entry.get("kind") == "spec.written" for entry in entries):
        candidate_data["construction_source"] = current_construction_amendment_source(
            entries, context, "a construction-only amendment opening",
        )
    candidate = {"event": "note", "kind": "amendment.opened",
                 "data": candidate_data, "text": text}
    candidate_data["opening_sha256"] = amendment_opening_digest(candidate)
    candidate["data"] = candidate_data
    validate_amendment_opening_entry(entries + [candidate], len(entries), candidate)
    return candidate_data


def amendment_document_sections(payload, number, opening, subject):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject} is not valid UTF-8", exc)
    lines = text.splitlines()
    if not lines or lines[0] != f"# Amendment {number}":
        fail(f"{subject} has no exact amendment heading")
    headings = [(index, line[3:]) for index, line in enumerate(lines) if line.startswith("## ")]
    if [heading for _, heading in headings] != list(AMENDMENT_SECTIONS):
        fail(f"{subject} does not contain the complete ordered section manifest",
             [heading for _, heading in headings])
    bodies = {}
    for position, (start, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if not body:
            fail(f"{subject} has an empty `{heading}` section")
        bodies[heading] = body
    if bodies["Order and return"] != opening.get("text", "").strip():
        fail(f"{subject} does not reproduce the durable order and return address")
    opening_data = note_data(opening)
    members = opening_data.get("members") or ([opening_data["ruling"]]
                                                if opening_data.get("ruling") else [])
    for member in members:
        if not re.search(rf"(?<![A-Za-z0-9/]){re.escape(member)}(?![A-Za-z0-9/])",
                         bodies["Decisions"]):
            fail(f"{subject} omits amendment member {member}")
    return bodies


def amendment_written_entry(entries, opening_index, before, subject):
    opening = entries[opening_index]
    number = note_data(opening)["amendment"]
    matches = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "amendment.written"
        and note_data(entry).get("amendment") == number]
    if len(matches) != 1:
        fail(f"{subject} requires one exact amendment.written boundary", f"found {len(matches)}")
    index, entry = matches[0]
    data = note_data(entry)
    if data.get("opening_sha256") != note_data(opening).get("opening_sha256"):
        fail(f"{subject}'s readiness belongs to another amendment opening")
    relative = f"amendments/{number}.md"
    path = exact_real_file(WORKSPACE, relative, f"{subject}'s amendment document")
    expected_text = os.path.join(WORKSPACE, relative)
    if entry.get("text") != expected_text:
        fail(f"{subject}'s readiness names a non-canonical amendment path", entry.get("text"))
    snapshot_relative = f"reports/amendment/{number}/written.md"
    if data.get("snapshot") != snapshot_relative:
        fail(f"{subject}'s readiness has no canonical authoring snapshot")
    snapshot = exact_real_file(WORKSPACE, snapshot_relative,
                               f"{subject}'s amendment authoring snapshot")
    with open(snapshot, "rb") as source:
        payload = source.read()
    if data.get("document_sha256") != sha256_bytes(payload):
        fail(f"{subject}'s amendment document changed after readiness")
    amendment_document_sections(payload, number, opening, f"{subject}'s amendment document")
    exact_real_directory(WORKSPACE, f"reports/amendment/{number}",
                         f"{subject}'s report directory")
    return index, entry, path


def normalize_amendment_written(entries, data, text):
    if not isinstance(data, dict) or set(data) != {"amendment"}:
        fail("amendment.written takes only its amendment ordinal", data)
    openings = amendment_openings(entries)
    if not openings:
        fail("amendment.written has no current amendment opening")
    opening_index, opening = openings[-1]
    validate_amendment_opening_entry(entries, opening_index, opening)
    number = note_data(opening)["amendment"]
    if data["amendment"] != number:
        fail("amendment.written belongs to another amendment generation")
    if any(entry.get("kind") == "amendment.committed"
           for entry in entries[opening_index + 1:]):
        fail("amendment.written follows a committed amendment")
    if any(entry.get("kind") == "amendment.written"
           for entry in entries[opening_index + 1:]):
        fail("this amendment already has its readiness boundary")
    relative = f"amendments/{number}.md"
    expected_text = os.path.join(WORKSPACE, relative)
    if text != expected_text:
        fail("amendment.written must name the canonical workspace document", expected_text)
    path = exact_real_file(WORKSPACE, relative, "the amendment document")
    with open(path, "rb") as source:
        payload = source.read()
    amendment_document_sections(payload, number, opening, "the amendment document")
    directory = exact_real_directory(WORKSPACE, f"reports/amendment/{number}",
                                     "the amendment report directory")
    snapshot_relative = f"reports/amendment/{number}/written.md"
    snapshot = os.path.join(directory, "written.md")
    if os.path.islink(snapshot) or os.path.lexists(snapshot) and not os.path.isfile(snapshot):
        fail("the amendment authoring snapshot has a foreign occupant")
    if os.path.isfile(snapshot):
        with open(snapshot, "rb") as source:
            if source.read() != payload:
                fail("the amendment authoring snapshot belongs to different bytes")
    else:
        descriptor, temporary = tempfile.mkstemp(prefix=".written.", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, snapshot)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {
        "amendment": number,
        "opening_sha256": note_data(opening)["opening_sha256"],
        "document_sha256": sha256_bytes(payload),
        "snapshot": snapshot_relative,
    }


def markdown_structure_lines(text):
    """Return physical lines with fenced Markdown content hidden from structure parsing."""
    lines = text.splitlines()
    visible = []
    fence_character = None
    fence_length = 0
    for line in lines:
        stripped = line.lstrip()
        if fence_character is None:
            opening = re.match(r"(`{3,}|~{3,})(?:[^`~].*)?$", stripped)
            if opening:
                fence_character = opening.group(1)[0]
                fence_length = len(opening.group(1))
                visible.append(None)
            else:
                visible.append(line)
            continue
        if re.fullmatch(re.escape(fence_character) + "{" + str(fence_length) + r",}\s*", stripped):
            fence_character = None
            fence_length = 0
        visible.append(None)
    return lines, visible


def next_visible_line(lines, start, stop=None):
    stop = len(lines) if stop is None else stop
    for index in range(start, stop):
        if lines[index] is not None and lines[index].strip():
            return index
    return None


def amendment_reach_sources(entries, opening_index, before, opening):
    data = note_data(opening)
    if isinstance(data.get("members"), list) and data["members"]:
        sources = list(data["members"])
    elif isinstance(data.get("ruling"), str) and data["ruling"]:
        sources = [data["ruling"]]
    else:
        sources = [f"A{data['amendment']}/order"]

    dispatches = [
        entry for entry in entries[opening_index + 1:before]
        if entry.get("kind") == "fixer.dispatched"
        and note_data(entry).get("route") == "amendment-fixer"
    ]
    candidate_rulings = set()
    for entry in entries[opening_index + 1:before]:
        entry_data = note_data(entry)
        for value in (entry_data.get("ruling"), entry_data.get("answer")):
            if re.fullmatch(r"R[1-9][0-9]*", str(value)):
                candidate_rulings.add(value)
        for account in (entry_data.get("actions"), entry_data.get("updates"),
                        entry_data.get("rulings")):
            for member in account or []:
                if not isinstance(member, dict):
                    continue
                for key in ("answer", "id", "ruling"):
                    value = member.get(key)
                    if re.fullmatch(r"R[1-9][0-9]*", str(value)):
                        candidate_rulings.add(value)
    current_entries = entries[:before]
    for ruling in sorted(candidate_rulings, key=lambda value: int(value[1:])):
        _, route, status, authority = direct_ruling_generation(ruling, current_entries)
        if status != "active" or route != "amendment-fixer":
            continue
        owners = [entry for entry in dispatches
                  if note_data(entry).get("ruling") == ruling
                  and all(note_data(entry).get(key) == authority[key]
                          for key in ("authority_kind", "authority_ref", "authority_sha256"))]
        if len(owners) != 1:
            fail(f"the amendment Reach source {ruling} has no one exact owner-linked dispatch")
        authority_tuple = tuple(authority[key] for key in (
            "authority_kind", "authority_ref", "authority_sha256",
        ))
        if has_terminal(current_entries, ruling, authority_tuple):
            fail(f"the amendment Reach source {ruling} is already terminal")
        if ruling not in sources:
            sources.append(ruling)
    return sources


def collect_reach_error(errors, what, detail=None):
    if errors is None:
        fail(what, detail)
    errors.append((what, detail))


def diagnostic_reach_sources(value, subject, errors):
    sources = value.split(", ")
    if not sources or any(
        not re.fullmatch(r"(?:R[1-9][0-9]*|B[1-9][0-9]*/D[1-9][0-9]*|A[1-9][0-9]*/order)", source)
        for source in sources
    ) or len(set(sources)) != len(sources):
        collect_reach_error(errors, f"{subject} has an invalid place source account", value)
        return None
    return sources


def reach_completion_evidence_is_well_formed(block):
    if len(block) != len(AMENDMENT_REACH_LABELS):
        return False
    evidence = []
    for line, label in zip(block, AMENDMENT_REACH_LABELS):
        match = re.fullmatch(r"- \[x\] ([^—]+?) — (.+)", line)
        if not match or match.group(1).strip() != label or not match.group(2).strip():
            return False
        evidence.append(match.group(2).strip())
    return bool(
        re.fullmatch(r"([0-9]+) hops, last one returning ([0-9]+) new places", evidence[0])
        and re.fullmatch(
            r"([0-9]+) total: ([0-9]+) kept, ([0-9]+) moved, ([0-9]+) removed, ([0-9]+) DECISION",
            evidence[1],
        )
        and re.fullmatch(r"active (.+); ([0-9]+) unique terms or hits", evidence[2])
        and re.fullmatch(r"([0-9]+)", evidence[3])
        and (
            re.fullmatch(
                r"([0-9]+) found, ([0-9]+) still asserting it after the amendment", evidence[4],
            )
            or re.fullmatch(r"n/a; suites read: (\S.+)", evidence[4])
        )
        and (
            re.fullmatch(r"closed at hop ([0-9]+)", evidence[5])
            or re.fullmatch(
                r"NOT CLOSED: ([0-9]+(?:, [0-9]+)*) new places by hop; "
                r"next hop cannot be enumerated — "
                r"(missing durable input|unbounded input): (\S.+)",
                evidence[5],
            )
        )
    )


def diagnostic_indented_reach_prefix(text, subject, expected_sources):
    physical, visible = markdown_structure_lines(text)
    first = next_visible_line(visible, 0)
    marker = f"COMPLETION ({len(AMENDMENT_REACH_LABELS)} items)"
    if first is None or visible[first] == marker or visible[first].lstrip(" \t") != marker:
        return []

    errors = [(f"{subject}'s completion block is indented", None)]
    block = [line.lstrip(" \t") for line in physical[first + 1:first + 7]]
    if not reach_completion_evidence_is_well_formed(block):
        errors.append((f"{subject}'s completion block contains placeholder or malformed evidence", None))
    else:
        phrasings = re.fullmatch(
            r"- \[x\] phrasings swept for every changed thing — "
            r"active (.+); ([0-9]+) unique terms or hits",
            block[2],
        )
        completion_sources = diagnostic_reach_sources(phrasings.group(1), subject, errors)
        if completion_sources is not None and completion_sources != expected_sources:
            errors.append((
                f"{subject}'s completion names sources outside the current amendment",
                completion_sources,
            ))

    expected_source_set = set(expected_sources)
    for index, line in enumerate(visible):
        heading = re.fullmatch(r"## P([1-9][0-9]*) · .+", line or "")
        if not heading:
            continue
        source_index = next_visible_line(visible, index + 1)
        if source_index is None or not visible[source_index].startswith("Sources: "):
            continue
        sources = diagnostic_reach_sources(
            visible[source_index].removeprefix("Sources: "), subject, errors,
        )
        if sources is not None and not set(sources).issubset(expected_source_set):
            errors.append((
                f"{subject}'s P{heading.group(1)} names a source outside the current amendment",
                sources,
            ))
    return errors


def fail_reach_errors(subject, errors):
    detail = "\n    ".join(
        f"{what}: {value}" if value is not None else what
        for what, value in errors
    )
    fail(f"{subject} has {len(errors)} independent mechanical errors", detail)


def nonempty_reach_body(physical, start, stop, subject):
    content = [line for line in physical[start:stop]
               if line.strip() and not re.fullmatch(r"\s*(?:`{3,}|~{3,}).*", line)]
    if not content:
        fail(f"{subject} has empty mandatory evidence")


def audit_reach_account(text, subject, expected_sources, errors=None):
    physical, visible = markdown_structure_lines(text)
    marker = "## Reach account"
    markers = [index for index, line in enumerate(visible) if line == marker]
    completion_marker = f"COMPLETION ({len(AMENDMENT_REACH_LABELS)} items)"
    completion = [index for index, line in enumerate(visible) if line == completion_marker]
    first = next_visible_line(visible, 0)
    if completion != [first]:
        fail(f"{subject} does not open with one exact completion block")
    completion_end = first + 1 + len(AMENDMENT_REACH_LABELS)
    if markers != [next_visible_line(visible, completion_end)]:
        fail(f"{subject} has no one exact Reach account at the documented location")
    account = markers[0]
    cursor = next_visible_line(visible, account + 1)
    hops = []
    hop_indices = []
    while cursor is not None:
        match = re.fullmatch(r"Hop ([1-9][0-9]*): ([0-9]+) new( — closed)?", visible[cursor])
        if not match:
            break
        hops.append(match)
        hop_indices.append(cursor)
        cursor += 1
        if cursor >= len(visible) or visible[cursor] is None or not visible[cursor].strip():
            cursor = next_visible_line(visible, cursor)
            break
    if not hops or [int(match.group(1)) for match in hops] != list(range(1, len(hops) + 1)):
        fail(f"{subject} has no contiguous reach-hop account")
    closed = bool(hops[-1].group(3))
    hop_counts = [int(match.group(2)) for match in hops]
    if any(match.group(3) for match in hops[:-1]) \
            or closed and (hop_counts[-1] != 0 or any(count == 0 for count in hop_counts[:-1])) \
            or not closed and any(count == 0 for count in hop_counts):
        fail(f"{subject} has an inconsistent frontier close")
    places = sum(hop_counts)
    dispositions = []
    structural = {account, *hop_indices}
    expected_source_set = set(expected_sources)
    for ordinal in range(1, places + 1):
        if cursor is None:
            fail(f"{subject} is missing place P{ordinal}")
        heading = re.fullmatch(r"## P([1-9][0-9]*) · (.+)", visible[cursor])
        if not heading or int(heading.group(1)) != ordinal or not heading.group(2).strip() \
                or any(token in heading.group(2) for token in ("<", ">")):
            fail(f"{subject} has no exact contiguous P{ordinal} block")
        heading_index = cursor
        block_end = len(visible)
        for index in range(heading_index + 1, len(visible)):
            if visible[index] is not None and visible[index].startswith("## "):
                block_end = index
                break
        source_index = next_visible_line(visible, heading_index + 1, block_end)
        location_index = next_visible_line(visible, source_index + 1, block_end) \
            if source_index is not None else None
        disposition_index = next_visible_line(visible, location_index + 1, block_end) \
            if location_index is not None else None
        evidence_index = next_visible_line(visible, disposition_index + 1, block_end) \
            if disposition_index is not None else None
        if source_index is None or not visible[source_index].startswith("Sources: "):
            fail(f"{subject}'s P{ordinal} block has no exact Sources field")
        sources = diagnostic_reach_sources(
            visible[source_index].removeprefix("Sources: "), subject, errors,
        )
        if sources is not None and not set(sources).issubset(expected_source_set):
            collect_reach_error(
                errors,
                f"{subject}'s P{ordinal} names a source outside the current amendment",
                sources,
            )
        if location_index is None or not re.fullmatch(r"Location: \S.+", visible[location_index]) \
                or any(token in visible[location_index] for token in ("<", ">")):
            fail(f"{subject}'s P{ordinal} block has no exact Location field")
        disposition = visible[disposition_index].removeprefix("Disposition: ") \
            if disposition_index is not None else ""
        if disposition not in {"kept", "moved", "removed", "DECISION"}:
            fail(f"{subject}'s P{ordinal} block has no exact disposition")
        if evidence_index is None or visible[evidence_index] != "### Evidence":
            fail(f"{subject}'s P{ordinal} block has no exact Evidence section")
        handling_label = {
            "kept": "### Reason",
            "moved": "### Exact edit",
            "removed": "### Exact edit",
            "DECISION": "### Options",
        }[disposition]
        subheadings = [index for index in range(evidence_index, block_end)
                       if visible[index] is not None and visible[index].startswith("### ")]
        if len(subheadings) != 2 or visible[subheadings[0]] != "### Evidence" \
                or visible[subheadings[1]] != handling_label:
            fail(f"{subject}'s P{ordinal} block has an invalid evidence/handling shape")
        nonempty_reach_body(physical, subheadings[0] + 1, subheadings[1], subject)
        nonempty_reach_body(physical, subheadings[1] + 1, block_end, subject)
        structural.update({heading_index, source_index, location_index, disposition_index,
                           *subheadings})
        dispositions.append(disposition)
        cursor = next_visible_line(visible, block_end)
    structural_prefixes = (
        "## Reach account", "Hop ", "## P", "Sources:", "Location:", "Disposition:",
        "### Evidence", "### Reason", "### Exact edit", "### Options",
    )
    for index, line in enumerate(visible):
        if line is not None and line.startswith(structural_prefixes) and index not in structural:
            fail(f"{subject} has an orphan, duplicate or out-of-block Reach-account line", line)
    return {
        "hop": len(hops), "hop_counts": hop_counts, "places": places,
        "closed": closed, "dispositions": dispositions,
    }, physical, visible, first


def audit_reach_completion(
    physical, visible, start, subject, account, expected_sources, errors=None,
):
    block = visible[start + 1:start + 1 + len(AMENDMENT_REACH_LABELS)]
    if len(block) != len(AMENDMENT_REACH_LABELS) or any(line is None for line in block):
        fail(f"{subject}'s completion block is truncated")
    evidence = []
    for line, label in zip(block, AMENDMENT_REACH_LABELS):
        match = re.fullmatch(r"- \[x\] ([^—]+?) — (.+)", line)
        if not match or match.group(1).strip() != label or not match.group(2).strip():
            fail(f"{subject}'s completion block does not account for `{label}`")
        evidence.append(match.group(2).strip())
    hops = re.fullmatch(r"([0-9]+) hops, last one returning ([0-9]+) new places", evidence[0])
    places = re.fullmatch(
        r"([0-9]+) total: ([0-9]+) kept, ([0-9]+) moved, ([0-9]+) removed, ([0-9]+) DECISION",
        evidence[1],
    )
    phrasings = re.fullmatch(r"active (.+); ([0-9]+) unique terms or hits", evidence[2])
    purpose = re.fullmatch(r"([0-9]+)", evidence[3])
    tests = re.fullmatch(r"([0-9]+) found, ([0-9]+) still asserting it after the amendment", evidence[4])
    tests_na = re.fullmatch(r"n/a; suites read: (\S.+)", evidence[4])
    frontier_closed = re.fullmatch(r"closed at hop ([0-9]+)", evidence[5])
    frontier_open = re.fullmatch(
        r"NOT CLOSED: ([0-9]+(?:, [0-9]+)*) new places by hop; "
        r"next hop cannot be enumerated — (missing durable input|unbounded input): (\S.+)",
        evidence[5],
    )
    if not all((hops, places, phrasings, purpose)) or not (tests or tests_na) \
            or not (frontier_closed or frontier_open):
        collect_reach_error(
            errors, f"{subject}'s completion block contains placeholder or malformed evidence",
        )
        return False
    completion_sources = diagnostic_reach_sources(phrasings.group(1), subject, errors)
    if completion_sources is None:
        return False
    disposition_counts = [account["dispositions"].count(value)
                          for value in ("kept", "moved", "removed", "DECISION")]
    if completion_sources != expected_sources:
        collect_reach_error(
            errors,
            f"{subject}'s completion names sources outside the current amendment",
            completion_sources,
        )
    if int(hops.group(1)) != account["hop"] or int(hops.group(2)) != account["hop_counts"][-1] \
            or int(places.group(1)) != account["places"] \
            or [int(places.group(index)) for index in range(2, 6)] != disposition_counts \
            or int(purpose.group(1)) > account["places"]:
        fail(f"{subject}'s completion facts do not match its exact Reach account")
    if tests and int(tests.group(2)) > int(tests.group(1)):
        fail(f"{subject}'s test completion evidence is inconsistent")
    if account["closed"]:
        if not frontier_closed or int(frontier_closed.group(1)) != account["hop"]:
            fail(f"{subject}'s frontier completion does not match its closed account")
    else:
        frontier_counts = [int(value) for value in frontier_open.group(1).split(", ")] \
            if frontier_open else []
        if frontier_counts != account["hop_counts"]:
            fail(f"{subject}'s frontier completion does not match its open account")
        blocker = frontier_open.group(3) if frontier_open else ""
        if any(token in blocker for token in ("<", ">")):
            fail(f"{subject}'s open frontier carries placeholder blocker evidence")
    return True


def audit_reach_report(payload, subject, expected_sources):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject} is not valid UTF-8", exc)
    errors = diagnostic_indented_reach_prefix(text, subject, expected_sources)
    if errors:
        fail_reach_errors(subject, errors)
    account, physical, visible, completion_start = audit_reach_account(
        text, subject, expected_sources, errors,
    )
    done = audit_reach_completion(
        physical, visible, completion_start, subject, account, expected_sources, errors,
    )
    if errors:
        fail_reach_errors(subject, errors)
    finding_counts, _ = spec_report_findings(
        "\n".join(line if line is not None else "" for line in visible), subject,
    )
    if finding_counts["decision"] != account["dispositions"].count("DECISION"):
        fail(f"{subject}'s DECISION findings do not match its exact Reach account")
    return {
        "hop": account["hop"], "places": account["places"],
        "closed": account["closed"], "done": done,
        "finding_counts": finding_counts,
        "findings": sum(finding_counts.values()),
    }


def reach_sweep_is_actionable(audit):
    return audit["findings"] > 0


def reach_sweep_is_clean(audit):
    return audit["done"] is True and audit["closed"] is True and not reach_sweep_is_actionable(audit)


def reach_completion_contract_sha256():
    relative = "prompts/amendment/reviewer-reach-completion.md"
    path = exact_real_file(WORKSPACE, relative, "the Reach completion contract")
    with open(path, "rb") as source:
        payload = source.read()
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        fail("the Reach completion contract is not valid UTF-8", exc)
    matches = [
        index for index in range(0, len(lines) - len(AMENDMENT_REACH_COMPLETION_TEMPLATE) + 1)
        if tuple(lines[index:index + len(AMENDMENT_REACH_COMPLETION_TEMPLATE)])
        == AMENDMENT_REACH_COMPLETION_TEMPLATE
    ]
    markers = [index for index, line in enumerate(lines)
               if line == AMENDMENT_REACH_COMPLETION_TEMPLATE[0]]
    if len(markers) != 1 or matches != markers:
        fail("the Reach completion contract has no one exact column-zero template")
    return sha256_bytes(payload)


def validate_run_stop_precedence(entries, before, subject):
    boundaries = [(index, entry) for index, entry in enumerate(entries[:before])
                  if entry.get("event") == "note"
                  and entry.get("kind") in {"paused", "resumed", "aborted"}]
    aborted = [entry for _, entry in boundaries if entry.get("kind") == "aborted"]
    if aborted:
        fail(f"{subject} follows a completed run abort")
    if boundaries and boundaries[-1][1].get("kind") == "paused":
        fail(f"{subject} follows a run pause without its later resumed boundary")


def reach_recovery_authorization_account(entries, sweep, text, subject):
    validate_run_stop_precedence(entries, len(entries), subject)
    openings = amendment_openings(entries)
    if not openings:
        fail(f"{subject} has no current amendment")
    opening_index, opening = openings[-1]
    number = note_data(opening).get("amendment")
    amendment_written_entry(entries, opening_index, len(entries), subject)
    validate_reach_sweep_owed(entries, opening_index, len(entries), sweep, subject)

    sessions = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1,
    ) if entry.get("event") == "session-started"
        and entry.get("mode") == "amendment" and entry.get("mandate") == "reach"
        and entry.get("round") == sweep]
    if len(sessions) != 2:
        fail(f"{subject} requires exactly the original and replacement Reach owners",
             f"found {len(sessions)}")
    validate_reach_replacement_order(entries, opening_index, len(entries), sweep, subject)

    owner_proofs = []
    last_retirement_index = None
    for position, (started_index, started) in enumerate(sessions):
        stop = sessions[position + 1][0] if position + 1 < len(sessions) else len(entries)
        retirements = [(index, entry) for index, entry in enumerate(
            entries[started_index + 1:stop], started_index + 1,
        ) if entry.get("event") == "session-retired"
            and entry.get("session") == started.get("session")
            and entry.get("mode") == "amendment" and entry.get("mandate") == "reach"
            and entry.get("round") == sweep]
        if len(retirements) != 1 or retirements[0][1].get("status") not in {
            "failed", "cancelled", "superseded",
        }:
            fail(f"{subject} requires two exact unsuccessful Reach retirements",
                 started.get("session"))
        retirement_index, retirement = retirements[0]
        owner_proofs.append({
            "session": started.get("session"),
            "started": journal_line_proof(started_index),
            "retired": journal_line_proof(retirement_index),
            "status": retirement.get("status"),
        })
        last_retirement_index = retirement_index

    blockers = [(index, entry) for index, entry in enumerate(
        entries[last_retirement_index + 1:], last_retirement_index + 1,
    ) if entry.get("event") == "note" and entry.get("kind") == "not-converging"
        and entry.get("mode") == "amendment" and entry.get("job") == "controller"
        and entry.get("lot") == opening.get("lot")]
    if len(blockers) != 1 or not isinstance(blockers[0][1].get("text"), str) \
            or not blockers[0][1]["text"].strip():
        fail(f"{subject} requires one exact stable Reach blocker after both retirements")
    if any(entry.get("kind") == "reach.recovery.authorized"
           for entry in entries[opening_index + 1:]):
        fail(f"{subject} repeats a Reach recovery authorization")
    if text != REACH_RECOVERY_TEXT:
        fail(f"{subject} requires the exact reviewed correction reason")
    blocker_index, _ = blockers[0]
    return {
        "schema": 1,
        "reason": REACH_RECOVERY_REASON,
        "reason_sha256": sha256_bytes(text.encode("utf-8")),
        "amendment": number,
        "sweep": sweep,
        "opening": journal_line_proof(opening_index),
        "opening_sha256": note_data(opening).get("opening_sha256"),
        "owners": [owner["session"] for owner in owner_proofs],
        "owner_proofs": owner_proofs,
        "blocker": journal_line_proof(blocker_index),
        "completion_sha256": reach_completion_contract_sha256(),
    }


def normalize_reach_recovery_authorization(entries, data, text, round_number, context):
    if data != {"reason": REACH_RECOVERY_REASON}:
        fail("reach.recovery.authorized takes one exact reviewed correction reason", data)
    if not isinstance(round_number, int):
        fail("reach.recovery.authorized requires its exact --round")
    openings = amendment_openings(entries)
    opening = openings[-1][1] if openings else None
    if context.get("mode") != "amendment" or context.get("job") != "controller" \
            or context.get("mandate") is not None or context.get("task") is not None \
            or opening is None or context.get("lot") != opening.get("lot"):
        fail("reach.recovery.authorized requires its exact controller amendment context")
    return reach_recovery_authorization_account(
        entries, round_number, text, "reach.recovery.authorized",
    )


def validate_reach_recovery_authorization(entries, index, entry, sweep, subject):
    if entry.get("event") != "note" or entry.get("kind") != "reach.recovery.authorized" \
            or entry.get("mode") != "amendment" or entry.get("mandate") is not None \
            or entry.get("task") is not None or entry.get("round") != sweep \
            or entry.get("job") != "controller":
        fail(f"{subject} has a malformed Reach recovery authority")
    openings = amendment_openings(entries[:index])
    if not openings or entry.get("lot") != openings[-1][1].get("lot"):
        fail(f"{subject} has a Reach recovery authority for another lot")
    expected = reach_recovery_authorization_account(
        entries[:index], sweep, entry.get("text"), subject,
    )
    if note_data(entry) != expected:
        fail(f"{subject} has changed Reach recovery authority", expected)
    return expected


def validate_reach_replacement_order(entries, opening_index, before, sweep, subject):
    validate_run_stop_precedence(entries, before, subject)
    sessions = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("event") == "session-started"
        and entry.get("mode") == "amendment" and entry.get("mandate") == "reach"
        and entry.get("round") == sweep]
    for position in range(1, len(sessions)):
        prior_index, prior = sessions[position - 1]
        replacement_index, replacement = sessions[position]
        previous_session_ids = {entry.get("session") for _, entry in sessions[:position]}
        if replacement.get("session") in previous_session_ids:
            fail(f"{subject} reuses a prior physical Reach owner", replacement.get("session"))
        retirements = [(index, entry) for index, entry in enumerate(
            entries[prior_index + 1:replacement_index], prior_index + 1,
        ) if entry.get("event") == "session-retired"
            and entry.get("session") == prior.get("session")
            and entry.get("mode") == "amendment"
            and entry.get("mandate") == "reach"
            and entry.get("round") == sweep]
        if len(retirements) != 1:
            fail(f"{subject} has a Reach replacement before its prior owner retired",
                 prior.get("session"))
        retirement_index, retirement = retirements[0]
        if retirement.get("status") not in {"failed", "cancelled", "superseded"}:
            fail(f"{subject} has a Reach replacement after a successful owner",
                 prior.get("session"))
        if position < 2:
            continue
        authorities = [(index, entry) for index, entry in enumerate(
            entries[retirement_index + 1:replacement_index], retirement_index + 1,
        ) if entry.get("kind") == "reach.recovery.authorized"]
        if position != 2 or len(authorities) != 1:
            fail(f"{subject} has a Reach replacement beyond its one reviewed recovery")
        authority_index, authority = authorities[0]
        validate_reach_recovery_authorization(
            entries, authority_index, authority, sweep, subject,
        )


def exact_reach_session(entries, opening_index, before, sweep, subject):
    validate_reach_replacement_order(entries, opening_index, before, sweep, subject)
    sessions = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if candidate.get("event") == "session-started"
        and candidate.get("mode") == "amendment" and candidate.get("mandate") == "reach"
        and candidate.get("round") == sweep]
    completed = []
    for started_index, started in sessions:
        retirements = [candidate for candidate in entries[started_index + 1:before]
                       if candidate.get("event") == "session-retired"
                       and candidate.get("session") == started.get("session")
                       and candidate.get("mode") == "amendment"
                       and candidate.get("mandate") == "reach"
                       and candidate.get("round") == sweep]
        if len(retirements) != 1:
            fail(f"{subject} has a live or multiply retired reach session",
                 started.get("session"))
        if retirements[0].get("status") == "done":
            completed.append(started)
        elif retirements[0].get("status") not in {"failed", "cancelled", "superseded"}:
            fail(f"{subject} has a non-terminal reach session result")
    if len(completed) != 1:
        fail(f"{subject} has no one exact successful reach session")
    return completed[0]


def exact_live_reach_session(entries, opening_index, before, sweep, subject):
    validate_reach_replacement_order(entries, opening_index, before, sweep, subject)
    sessions = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if candidate.get("event") == "session-started"
        and candidate.get("mode") == "amendment" and candidate.get("mandate") == "reach"
        and candidate.get("round") == sweep]
    live = []
    for started_index, started in sessions:
        retirements = [candidate for candidate in entries[started_index + 1:before]
                       if candidate.get("event") == "session-retired"
                       and candidate.get("session") == started.get("session")
                       and candidate.get("mode") == "amendment"
                       and candidate.get("mandate") == "reach"
                       and candidate.get("round") == sweep]
        if len(retirements) > 1:
            fail(f"{subject} has a multiply retired reach session", started.get("session"))
        if not retirements:
            live.append(started)
            continue
        if retirements[0].get("status") == "done":
            fail(f"{subject} follows an already successful reach retirement",
                 started.get("session"))
        if retirements[0].get("status") not in {"failed", "cancelled", "superseded"}:
            fail(f"{subject} has a non-terminal reach session result")
    if len(live) != 1:
        fail(f"{subject} has no one exact live reach session")
    return live[0]


def validate_reach_sweep_owed(entries, opening_index, before, sweep, subject):
    if any(entry.get("kind") == "amendment.committed"
           for entry in entries[opening_index + 1:before]):
        fail(f"{subject} follows a closed amendment generation")
    prior = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "sweep.reported"]
    if sweep != len(prior) + 1:
        fail(f"{subject} has the wrong sweep ordinal",
             {"expected": len(prior) + 1, "actual": sweep})
    for position, (prior_index, prior_entry) in enumerate(prior):
        _, _, _, audit = validate_sweep_entry(
            entries, prior_index, prior_entry, validate_owed=False,
        )
        next_index = prior[position + 1][0] if position + 1 < len(prior) else before
        if reach_sweep_is_clean(audit):
            fail(f"{subject} follows a clean Reach close")
        if reach_sweep_is_actionable(audit) \
                and not any(entry.get("kind") == "fixer.returned"
                            and entry.get("mode") == "amendment"
                            for entry in entries[prior_index + 1:next_index]):
            fail(f"{subject} precedes the prior actionable sweep's fixer return")
    return prior


def amendment_sweep_generation(entries, sweep, subject, *, live):
    openings = amendment_openings(entries)
    if not openings:
        fail(f"{subject} has no current amendment")
    opening_index, opening = openings[-1]
    number = note_data(opening)["amendment"]
    _, amendment_written, _ = amendment_written_entry(
        entries, opening_index, len(entries), subject,
    )
    validate_reach_sweep_owed(entries, opening_index, len(entries), sweep, subject)
    relative = f"reports/amendment/{number}/sweep-{sweep}.md"
    report = exact_real_file(WORKSPACE, relative, "the reach report")
    with open(report, "rb") as source:
        payload = source.read()
    account = audit_reach_report(
        payload, "the reach report",
        amendment_reach_sources(entries, opening_index, len(entries), opening),
    )
    amendment_path = exact_real_file(WORKSPACE, f"amendments/{number}.md",
                                     "the amendment under reach review")
    with open(amendment_path, "rb") as source:
        amendment_sha = sha256_bytes(source.read())
    if sweep == 1 and amendment_sha != note_data(amendment_written)["document_sha256"]:
        fail("the first reach preflight does not consume the complete authored amendment")
    accepted = exact_live_reach_session(entries, opening_index, len(entries), sweep, subject) \
        if live else exact_reach_session(entries, opening_index, len(entries), sweep, subject)
    return {
        "amendment": number, "sweep": sweep, "session": accepted["session"],
        "opening_sha256": note_data(opening)["opening_sha256"],
        "report_sha256": sha256_bytes(payload), "amendment_sha256": amendment_sha,
        **{key: account[key] for key in ("hop", "places", "closed", "done")},
    }


def amendment_sweep_preflight(entries, sweep, subject):
    return amendment_sweep_generation(entries, sweep, subject, live=True)


def validate_amendment_sweep_preflight(proof, subject):
    exact = {
        "amendment", "sweep", "session", "opening_sha256", "report_sha256",
        "amendment_sha256", "hop", "places", "closed", "done",
    }
    if not isinstance(proof, dict) or set(proof) != exact \
            or not all(isinstance(proof[key], int) and not isinstance(proof[key], bool)
                       and proof[key] > 0 for key in ("amendment", "sweep", "hop")) \
            or not isinstance(proof["places"], int) or isinstance(proof["places"], bool) \
            or proof["places"] < 0 \
            or not isinstance(proof["session"], str) or not proof["session"] \
            or any(not isinstance(proof[key], str)
                   or not re.fullmatch(r"[0-9a-f]{64}", proof[key])
                   for key in ("opening_sha256", "report_sha256", "amendment_sha256")) \
            or not isinstance(proof["closed"], bool) or proof["done"] is not True:
        fail(f"{subject} has a malformed amendment-sweep preflight proof", proof)
    return proof


def amendment_sweep_preflight_payload(proof):
    return (json.dumps(
        proof, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf-8")


def read_amendment_sweep_preflight(subject, *, required=True):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(AMENDMENT_SWEEP_PREFLIGHT, flags)
    except FileNotFoundError:
        if required:
            fail(f"{subject} has no consumable amendment-sweep preflight")
        return None
    except OSError as exc:
        fail(f"{subject}'s amendment-sweep preflight is not one readable real file", exc)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail(f"{subject}'s amendment-sweep preflight is not one real regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            try:
                payload = source.read()
                proof = json.loads(payload.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                fail(f"{subject}'s amendment-sweep preflight is malformed", exc)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    proof = validate_amendment_sweep_preflight(proof, subject)
    if payload != amendment_sweep_preflight_payload(proof):
        fail(f"{subject}'s amendment-sweep preflight has non-canonical bytes")
    return proof


def remove_amendment_sweep_preflight(expected, subject, *, journaled=False):
    current = read_amendment_sweep_preflight(subject)
    if current != expected:
        fail(f"{subject}'s amendment-sweep preflight changed before consumption",
             journaled=journaled)
    try:
        os.unlink(AMENDMENT_SWEEP_PREFLIGHT)
    except OSError as exc:
        fail(f"{subject} could not consume its amendment-sweep preflight", exc,
             journaled=journaled)


def amendment_sweep_receipt_for_proof(entries, proof):
    return [(index, entry) for index, entry in enumerate(entries)
            if entry.get("kind") == "sweep.reported" and note_data(entry) == proof]


def preflight_session_retirement(entries, proof):
    starts = [(index, entry) for index, entry in enumerate(entries)
              if entry.get("event") == "session-started"
              and entry.get("session") == proof["session"]
              and entry.get("mode") == "amendment" and entry.get("mandate") == "reach"
              and entry.get("round") == proof["sweep"]]
    if len(starts) != 1:
        return None
    index, _ = starts[0]
    retirements = [entry for entry in entries[index + 1:]
                   if entry.get("event") == "session-retired"
                   and entry.get("session") == proof["session"]
                   and entry.get("mode") == "amendment"
                   and entry.get("mandate") == "reach"
                   and entry.get("round") == proof["sweep"]]
    if len(retirements) != 1:
        return None
    return retirements[0].get("status")


def publish_amendment_sweep_preflight(entries, proof, subject):
    current = read_amendment_sweep_preflight(subject, required=False)
    if current == proof:
        return
    if current is not None:
        receipts = amendment_sweep_receipt_for_proof(entries, current)
        replaceable = current.get("amendment") == proof["amendment"] \
            and current.get("sweep") == proof["sweep"] \
            and current.get("opening_sha256") == proof["opening_sha256"] \
            and (current.get("session") == proof["session"]
                 or preflight_session_retirement(entries, current)
                 in {"failed", "cancelled", "superseded"})
        if len(receipts) > 1:
            fail(f"{subject} follows duplicate receipts for one preflight generation")
        if len(receipts) == 1:
            remove_amendment_sweep_preflight(current, subject)
        elif not replaceable:
            fail(f"{subject} cannot replace an unsettled amendment-sweep preflight")
    payload = amendment_sweep_preflight_payload(proof)
    descriptor, temporary = tempfile.mkstemp(prefix=".amendment-sweep-preflight.", dir=WORKSPACE)
    try:
        with os.fdopen(descriptor, "wb") as target:
            descriptor = None
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        if os.path.lexists(AMENDMENT_SWEEP_PREFLIGHT) \
                and (os.path.islink(AMENDMENT_SWEEP_PREFLIGHT)
                     or not os.path.isfile(AMENDMENT_SWEEP_PREFLIGHT)):
            fail(f"{subject}'s amendment-sweep preflight path has a foreign occupant")
        os.replace(temporary, AMENDMENT_SWEEP_PREFLIGHT)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_sweep_entry(entries, index, entry, *, validate_owed=True):
    data = note_data(entry)
    number, sweep = data.get("amendment"), data.get("sweep")
    openings = [(candidate_index, candidate) for candidate_index, candidate in amendment_openings(entries, index)
                if note_data(candidate).get("amendment") == number]
    if len(openings) != 1 or not isinstance(sweep, int) or isinstance(sweep, bool) or sweep < 1:
        fail("a reach receipt has no exact amendment and sweep identity")
    opening_index, opening = openings[0]
    amendment_written_entry(entries, opening_index, index, "a reach receipt")
    if validate_owed:
        validate_reach_sweep_owed(
            entries, opening_index, index, sweep, "a reach receipt",
        )
    else:
        prior = [candidate for candidate in entries[opening_index + 1:index]
                 if candidate.get("kind") == "sweep.reported"]
        if sweep != len(prior) + 1:
            fail("a reach receipt has the wrong sweep ordinal",
                 {"expected": len(prior) + 1, "actual": sweep})
    accepted = exact_reach_session(entries, opening_index, index, sweep, "a reach receipt")
    if data.get("session") != accepted.get("session"):
        fail("a reach receipt has no one exact completed sweep session")
    relative = f"reports/amendment/{number}/sweep-{sweep}.md"
    report = exact_real_file(WORKSPACE, relative, "the reach report")
    with open(report, "rb") as source:
        payload = source.read()
    account = audit_reach_report(
        payload, "the reach report",
        amendment_reach_sources(entries, opening_index, index, opening),
    )
    expected = {
        "amendment": number, "sweep": sweep,
        "opening_sha256": note_data(opening)["opening_sha256"],
        "report_sha256": sha256_bytes(payload), "session": accepted["session"],
        "amendment_sha256": data.get("amendment_sha256"),
        **{key: account[key] for key in ("hop", "places", "closed", "done")},
    }
    if not isinstance(data.get("amendment_sha256"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", data["amendment_sha256"]):
        fail("a reach receipt has no frozen amendment content identity")
    if sweep == 1 and data["amendment_sha256"] != note_data(
        amendment_written_entry(entries, opening_index, index, "a reach receipt")[1]
    )["document_sha256"]:
        fail("the first reach sweep does not consume the complete authored amendment")
    if data != expected:
        fail("a reach receipt does not match its exact report and generation", expected)
    return opening_index, opening, expected, account


def normalize_sweep_report(entries, data, round_number):
    if not isinstance(data, dict) or set(data) != {"hop", "places", "closed"}:
        fail("sweep.reported requires exactly hop, places and closed", data)
    if not isinstance(round_number, int):
        fail("sweep.reported requires its exact --round")
    candidate_data = amendment_sweep_generation(
        entries, round_number, "sweep.reported", live=False,
    )
    if any(data.get(key) != candidate_data[key] for key in ("hop", "places", "closed")):
        fail("sweep.reported counts do not match the exact reach report", candidate_data)
    preflight = read_amendment_sweep_preflight("sweep.reported")
    if preflight != candidate_data:
        fail("sweep.reported does not consume its exact amendment-sweep preflight",
             {"preflight": preflight, "current": candidate_data})
    candidate = {"event": "note", "kind": "sweep.reported", "data": candidate_data}
    validate_sweep_entry(entries + [candidate], len(entries), candidate)
    return candidate_data


def finish_interrupted_sweep_receipt(entries, data, round_number):
    preflight = read_amendment_sweep_preflight(
        "the interrupted sweep receipt", required=False,
    )
    if preflight is None:
        return False
    receipts = amendment_sweep_receipt_for_proof(entries, preflight)
    if not receipts:
        return False
    if len(receipts) != 1 or round_number != preflight["sweep"] \
            or not isinstance(data, dict) or set(data) != {"hop", "places", "closed"} \
            or any(data[key] != preflight[key] for key in data):
        fail("the interrupted sweep receipt does not match its exact accepted generation")
    validate_sweep_entry(entries, receipts[0][0], receipts[0][1])
    remove_amendment_sweep_preflight(preflight, "the interrupted sweep receipt")
    return True


def product_review_amendment_spec_file(entries, opening_index, opening, subject):
    """Resolve a construction-only run's exact spec from its reviewed committed plan."""
    opening_data = note_data(opening)
    pass_index, _, built, commit = current_pass_opening(entries, opening_index, subject)
    if pass_index >= opening_index or opening_data.get("built") != built:
        fail(f"{subject} does not consume its exact product-review source pass")
    plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-{built}-plan.md"
    spec_source = None
    if "." in built:
        _, spec_source = construction_lot_origin_and_spec(
            entries, pass_index, built, subject,
        )
    committed, used_fallback = committed_plan_spec_account(
        commit, plan_relative, subject,
        fallback_spec=spec_source["spec"] if spec_source is not None else None,
    )
    if used_fallback and committed["spec_sha256"] != spec_source["spec_sha256"]:
        fail(f"{subject}'s source-pass and reviewed specifications differ")
    return exact_real_file(
        project_root(), committed["spec"], f"{subject}'s product-review specification",
    )


def amendment_spec_file(entries, before, opening_index, opening, subject):
    readiness = [(index, entry) for index, entry in enumerate(entries[:before])
                 if entry.get("kind") == "spec.written"]
    if readiness:
        _, spec_entry = spec_written(entries[:before])
        return spec_file_from_written(spec_entry)
    if note_data(opening).get("origin") == "construction":
        source = validate_construction_amendment_source(
            entries, opening_index, note_data(opening).get("construction_source"), subject,
        )
        return exact_real_file(
            project_root(), source["spec"], f"{subject}'s Construction specification",
        )
    return product_review_amendment_spec_file(
        entries, opening_index, opening, subject,
    )


def current_amendment_review(entries, before, subject):
    openings = amendment_openings(entries, before)
    if not openings:
        fail(f"{subject} has no current amendment opening")
    opening_index, opening = openings[-1]
    validate_amendment_opening_entry(entries, opening_index, opening)
    written_index, written, amendment_path = amendment_written_entry(
        entries, opening_index, before, subject,
    )
    sweeps = [(index, entry) for index, entry in enumerate(
        entries[written_index + 1:before], written_index + 1
    ) if entry.get("kind") == "sweep.reported"]
    if not sweeps:
        fail(f"{subject} has no accepted reach sweep")
    final_audit = None
    for sweep_index, sweep in sweeps:
        _, _, _, final_audit = validate_sweep_entry(entries, sweep_index, sweep)
    final_sweep_index, final_sweep = sweeps[-1]
    final_data = note_data(final_sweep)
    if not reach_sweep_is_clean(final_audit):
        fail(f"{subject}'s latest reach sweep is not one complete clean close")
    final_returns = [(index, entry) for index, entry in enumerate(
        entries[final_sweep_index + 1:before], final_sweep_index + 1
    ) if entry.get("kind") == "fixer.returned"]
    if not final_returns:
        fail(f"{subject} has no accepted final fixer return after the clean reach sweep")
    last_return_index = final_returns[-1][0]
    pending_dispatches = [entry for entry in entries[opening_index + 1:before]
                          if entry.get("kind") == "fixer.dispatched"]
    for dispatch in pending_dispatches:
        dispatch_index = entries.index(dispatch)
        if not any(entry.get("kind") == "fixer.returned"
                   for entry in entries[dispatch_index + 1:before]):
            fail(f"{subject} has an unsettled fixer dispatch")
    spec_path = amendment_spec_file(entries, before, opening_index, opening, subject)
    return {
        "opening_index": opening_index,
        "opening": opening,
        "written": written,
        "amendment_path": amendment_path,
        "spec_path": spec_path,
        "sweep": final_data["sweep"],
        "sweep_sha256": final_data["report_sha256"],
        "last_return_index": last_return_index,
    }


def amendment_content_identity(entries, before, subject):
    state = current_amendment_review(entries, before, subject)
    with open(state["amendment_path"], "rb") as source:
        amendment_payload = source.read()
    with open(state["spec_path"], "rb") as source:
        spec_payload = source.read()
    return state, sha256_bytes(amendment_payload), sha256_bytes(spec_payload)


def construction_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def active_attempt_identity(context, subject, *, allow_closer=False):
    lot, task, attempt_number = context.get("lot"), context.get("task"), context.get("attempt")
    if not isinstance(lot, str) or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot) \
            or not construction_positive_integer(task) \
            or not construction_positive_integer(attempt_number):
        fail(f"{subject} has no exact construction attempt context")
    path = os.path.join(WORKSPACE, "attempt-in-flight")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"{subject} has no real attempt-in-flight identity", exc)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail(f"{subject}'s attempt-in-flight identity is not a real regular file")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = None
            lines = handle.read().splitlines()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    allowed_lines = {2, 4} if allow_closer else {2}
    match = re.fullmatch(
        r"plan ([0-9a-f]{40,64}) ([1-9][0-9]*) ownership ([0-9a-f]{64}) "
        r"contract ([0-9a-f]{64}) retry (-|[0-9]+:[0-9a-f]{64})",
        lines[1] if len(lines) in allowed_lines else "",
    )
    if len(lines) not in allowed_lines or lines[0].split() != [lot, str(task), str(attempt_number)] \
            or match is None:
        fail(f"{subject} does not match the exact attempt-in-flight identity")
    retry = None if match.group(5) == "-" else match.group(5)
    return {
        "lot": lot, "task": task, "attempt": attempt_number,
        "plan_manifest": match.group(1), "plan_tasks": int(match.group(2)),
        "plan_ownership_sha256": match.group(3),
        "contract_sha256": match.group(4),
        "retry": retry,
    }


def git_commit_and_tree(name, subject):
    commit = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "--verify", f"{name}^{{commit}}"],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        fail(f"{subject} has no exact commit", commit.stderr)
    sha = commit.stdout.strip()
    tree = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "--verify", f"{sha}^{{tree}}"],
        capture_output=True, text=True,
    )
    if tree.returncode != 0:
        fail(f"{subject} has no exact tree", tree.stderr)
    return sha, tree.stdout.strip()


def construction_session_start_account(context, session, subject):
    identity = active_attempt_identity(context, subject)
    base_ref = (
        f"refs/bwr/{Path(WORKSPACE).name}/{identity['lot']}/attempt-base"
    )
    base, tree = git_commit_and_tree(base_ref, subject)
    identity_sha256 = sha256_bytes(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    account = {
        "schema": 2,
        "session": session,
        "attempt_identity": identity,
        "attempt_identity_sha256": identity_sha256,
        "attempt_base": base,
        "attempt_base_tree": tree,
    }
    account["authority_sha256"] = canonical_digest(account)
    return account


def validate_construction_session_start(entry, subject, *, entries=None, index=None):
    context = {key: entry.get(key) for key in ("lot", "task", "attempt")}
    if entry.get("event") != "session-started" \
            or entry.get("mode") != "construction" \
            or entry.get("job") != "implementer" \
            or not isinstance(entry.get("session"), str) or not entry["session"] \
            or not isinstance(context["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", context["lot"]) \
            or not construction_positive_integer(context["task"]) \
            or not construction_positive_integer(context["attempt"]):
        fail(f"{subject} has malformed implementer launch identity")
    data = entry.get("data")
    if data is None:
        return context  # historical schema-1 line, before launch accounts existed
    legacy_required = {
        "schema", "attempt_identity", "attempt_identity_sha256",
        "attempt_base", "attempt_base_tree",
    }
    current_required = legacy_required | {"session", "authority_sha256"}
    identity = data.get("attempt_identity") if isinstance(data, dict) else None
    if not isinstance(data, dict) or (
        data.get("schema") == 1 and set(data) != legacy_required
        or data.get("schema") == 2 and set(data) != current_required
        or data.get("schema") not in {1, 2}
    ) \
            or not isinstance(identity, dict):
        fail(f"{subject} has malformed frozen attempt authority")
    identity_required = {
        "lot", "task", "attempt", "plan_manifest", "plan_tasks",
        "plan_ownership_sha256", "contract_sha256", "retry",
    }
    if set(identity) != identity_required \
            or {key: identity.get(key) for key in ("lot", "task", "attempt")} != context \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(identity.get("plan_manifest"))) \
            or not construction_positive_integer(identity.get("plan_tasks")) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(identity.get("plan_ownership_sha256"))) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(identity.get("contract_sha256"))) \
            or identity.get("retry") is not None \
            and not re.fullmatch(r"[0-9]+:[0-9a-f]{64}", str(identity.get("retry"))):
        fail(f"{subject} has malformed frozen attempt identity")
    digest = sha256_bytes(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    commit, tree = git_commit_and_tree(data.get("attempt_base"), subject)
    current_authority = dict(data)
    current_digest = current_authority.pop("authority_sha256", None)
    if data.get("attempt_identity_sha256") != digest \
            or commit != data.get("attempt_base") \
            or tree != data.get("attempt_base_tree") \
            or data.get("schema") == 2 and (
                data.get("session") != entry["session"]
                or current_digest != canonical_digest(current_authority)
            ):
        fail(f"{subject} changed its frozen attempt authority")
    if entries is not None and index is not None \
            and identity.get("retry") != outstanding_retry_proof(entries[:index], context["lot"]):
        fail(f"{subject} changed its outstanding retry authority")
    return context


def construction_attempt_terminal(entry, lot, task, attempt_number):
    return entry.get("event") == "note" \
        and entry.get("kind") in {"attempt.failed", "attempt.succeeded", "paused", "aborted"} \
        and entry.get("lot") == lot and entry.get("task") == task \
        and note_data(entry).get("attempt") == attempt_number


def construction_launch_abandonment_account(
        entries, before, session, subject, *, live=False, recorded=None,
):
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if entry.get("event") == "session-started"
              and entry.get("session") == session
              and entry.get("mode") == "construction"
              and entry.get("job") == "implementer"]
    if len(starts) > 1:
        fail(f"{subject} has more than one implementer start", session)
    start_index, start = starts[0] if starts else (None, None)
    retirements = [(index, entry) for index, entry in enumerate(entries[:before])
                   if entry.get("event") == "session-retired"
                   and entry.get("session") == session
                   and entry.get("mode") == "construction"
                   and entry.get("job") == "implementer"]
    if len(retirements) != 1:
        fail(f"{subject} requires one exact implementer retirement", session)
    retired_index, retired = retirements[0]
    if start_index is not None and retired_index <= start_index:
        fail(f"{subject}'s retirement precedes its implementer start")
    if retired.get("status") != "failed" \
            or retired.get("archived") is not True or retired.get("hidden") is not True:
        fail(f"{subject} requires one failed, archived and hidden implementer")
    context_source = start if start is not None else retired
    context = validate_construction_session_start(
        start, subject, entries=entries, index=start_index,
    ) if start is not None else {
        key: retired.get(key) for key in ("lot", "task", "attempt")
    }
    if start is None and (
        retired.get("mode") != "construction" or retired.get("job") != "implementer"
        or not isinstance(retired.get("lot"), str)
        or not construction_positive_integer(retired.get("task"))
        or not construction_positive_integer(retired.get("attempt"))
    ):
        fail(f"{subject} has malformed retired implementer identity")
    if any(context_source.get(key) != retired.get(key)
           for key in ("lot", "task", "attempt")):
        fail(f"{subject}'s start and retirement name different attempts")
    lot, task, attempt_number = context["lot"], context["task"], context["attempt"]
    if any(construction_attempt_terminal(entry, lot, task, attempt_number)
           for entry in entries[:before]):
        fail(f"{subject} cannot replace a real attempt terminal")
    if any(entry.get("event") == "subagent-started"
           and entry.get("kind") in {"design-checker", "code-checker", "diagnostic"}
           and entry.get("lot") == lot and entry.get("task") == task
           and entry.get("attempt") == attempt_number for entry in entries[:before]):
        fail(f"{subject} cannot discard checker work from the orphan launch")
    if any(entry.get("event") == "note" and entry.get("kind") == "attempt.launch.abandoned"
           and note_data(entry).get("session") == session for entry in entries[:before]):
        fail(f"{subject} repeats an existing orphan-launch terminal")

    if live:
        for name in ("attempt-in-flight", "attempt-in-flight.tmp"):
            if os.path.lexists(os.path.join(WORKSPACE, name)):
                fail(f"{subject} cannot abandon a launch while {name} exists")
        dirty = subprocess.run(
            ["git", "-C", REPO, "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if dirty.returncode != 0 or dirty.stdout:
            fail(f"{subject} requires one clean repository tree", dirty.stdout or dirty.stderr)
        head, tree = git_commit_and_tree("HEAD", subject)
        base_ref = f"refs/bwr/{Path(WORKSPACE).name}/{lot}/attempt-base"
        attempt_base, _ = git_commit_and_tree(base_ref, subject)
        if attempt_base != head:
            fail(f"{subject}'s current HEAD differs from its unclaimed attempt-base")
        ref_root = f"refs/bwr/{Path(WORKSPACE).name}/{lot}"
        for ref in (f"{ref_root}/task-{task}-try-{attempt_number}", f"{ref_root}/task-{task}"):
            present = subprocess.run(
                ["git", "-C", REPO, "rev-parse", "--verify", "--quiet", ref],
                capture_output=True, text=True,
            )
            if present.returncode == 0:
                fail(f"{subject} cannot abandon a launch that owns {ref}")
        report = os.path.join(
            WORKSPACE, "reports", "construction",
            f"{lot}-task-{task}-try-{attempt_number}.md",
        )
        if os.path.lexists(report):
            fail(f"{subject} cannot abandon a launch with an attempt report")
    else:
        data = recorded if isinstance(recorded, dict) else {}
        head, tree = git_commit_and_tree(data.get("head"), subject)
        attempt_base = data.get("attempt_base")
        if head != data.get("head") or tree != data.get("tree") \
                or attempt_base != head:
            fail(f"{subject} changed its frozen clean repository account")

    return {
        "schema": 1,
        "reason": "missing-attempt-identity",
        "session": session,
        "lot": lot,
        "task": task,
        "attempt": attempt_number,
        "started": journal_line_proof(start_index) if start_index is not None else None,
        "retired": journal_line_proof(retired_index),
        "head": head,
        "tree": tree,
        "attempt_base": attempt_base,
        "retry": outstanding_retry_proof(entries[:before], lot),
    }


def validate_construction_launch_abandonment(entries, index, entry, subject):
    if entry.get("event") != "note" or entry.get("kind") != "attempt.launch.abandoned" \
            or entry.get("mode") != "construction" or entry.get("job") != "controller":
        fail(f"{subject} has malformed terminal context")
    data = note_data(entry)
    required = {
        "schema", "reason", "session", "lot", "task", "attempt", "started",
        "retired", "head", "tree", "attempt_base", "retry",
    }
    if set(data) != required or data.get("schema") != 1 \
            or data.get("reason") != "missing-attempt-identity" \
            or any(entry.get(key) != data.get(key) for key in ("lot", "task", "attempt")):
        fail(f"{subject} has malformed terminal data")
    expected = construction_launch_abandonment_account(
        entries, index, data.get("session"), subject, live=False, recorded=data,
    )
    if data != expected:
        fail(f"{subject} changed its exact orphan-launch account", expected)
    return expected


def validate_construction_launch_candidate(entries, lot, task, attempt_number, subject):
    if not isinstance(lot, str) or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot) \
            or not construction_positive_integer(task) \
            or not construction_positive_integer(attempt_number):
        fail(f"{subject} has malformed attempt identity")
    abandonments = {}
    for index, entry in enumerate(entries):
        if entry.get("event") != "note" or entry.get("kind") != "attempt.launch.abandoned" \
                or entry.get("lot") != lot or entry.get("task") != task:
            continue
        data = validate_construction_launch_abandonment(
            entries, index, entry, "a durable orphan-launch terminal",
        )
        key = (data["lot"], data["task"], data["attempt"], data["session"])
        if key in abandonments:
            fail(f"{subject} has duplicate orphan-launch terminals", key)
        abandonments[key] = data

    seen = set()
    orphan_sessions = []
    for entry_index, entry in enumerate(entries):
        if entry.get("event") == "session-started" \
                and entry.get("mode") == "construction" \
                and entry.get("job") == "implementer" \
                and entry.get("lot") == lot and entry.get("task") == task:
            context = validate_construction_session_start(
                entry, "a durable construction implementer start",
                entries=entries, index=entry_index,
            )
            number = context["attempt"]
            seen.add(number)
            owner = (lot, task, number, entry.get("session"))
            terminal = any(construction_attempt_terminal(candidate, lot, task, number)
                           for candidate in entries)
            retired = [candidate for candidate in entries
                       if candidate.get("event") == "session-retired"
                       and candidate.get("session") == entry.get("session")
                       and candidate.get("mode") == "construction"
                       and candidate.get("job") == "implementer"
                       and candidate.get("lot") == lot and candidate.get("task") == task
                       and candidate.get("attempt") == number
                       and candidate.get("status") in {"done", "failed", "cancelled", "superseded"}]
            if len(retired) != 1 or not terminal and owner not in abandonments:
                orphan_sessions.append(entry.get("session"))
        elif entry.get("event") == "session-retired" \
                and entry.get("mode") == "construction" \
                and entry.get("job") == "implementer" \
                and entry.get("lot") == lot and entry.get("task") == task \
                and construction_positive_integer(entry.get("attempt")):
            seen.add(entry["attempt"])
            owner = (lot, task, entry["attempt"], entry.get("session"))
            if not any(construction_attempt_terminal(candidate, lot, task, entry["attempt"])
                       for candidate in entries) \
                    and owner not in abandonments:
                orphan_sessions.append(entry.get("session"))
        elif entry.get("event") == "note" \
                and entry.get("kind") in {"attempt.failed", "attempt.succeeded", "paused", "aborted"} \
                and entry.get("lot") == lot and entry.get("task") == task \
                and construction_positive_integer(note_data(entry).get("attempt")):
            seen.add(note_data(entry)["attempt"])
    if orphan_sessions:
        fail(f"{subject} has an implementer launch with no attempt identity or terminal",
             orphan_sessions)
    highest = max(seen, default=0)
    if attempt_number != highest + 1:
        fail(f"{subject} must use the next attempt number",
             {"expected": highest + 1, "actual": attempt_number})
    return highest


def diagnostic_attempt_identity(entries, context, subject):
    lot, task = context.get("lot"), context.get("task")
    if not isinstance(lot, str) or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot) \
            or not construction_positive_integer(task):
        fail(f"{subject} has no exact construction lot and task context")
    failures = [entry for entry in entries if entry.get("event") == "note"
                and entry.get("kind") == "attempt.failed"
                and entry.get("lot") == lot and entry.get("task") == task]
    if not failures:
        fail(f"{subject} has no current failed attempt")
    failure = failures[-1]
    data = note_data(failure)
    attempt_number = data.get("attempt")
    if not construction_positive_integer(attempt_number) \
            or data.get("classification") not in CONSTRUCTION_CLASSIFICATIONS:
        fail(f"{subject}'s current failed attempt has malformed identity")
    return {"lot": lot, "task": task, "attempt": attempt_number}


def construction_logical_identity(entries, context, check, round_number, subject):
    if check in CONSTRUCTION_CHECKERS:
        round_limit = CONSTRUCTION_CHECKER_ROUNDS[check]
        if not construction_positive_integer(round_number) or round_number > round_limit:
            fail(f"{subject} requires a logical round from 1 through {round_limit}")
        identity = active_attempt_identity(context, subject)
        return {"check": check, **identity, "round": round_number}
    if check == "diagnostic":
        if round_number is not None:
            fail(f"{subject} does not take a logical round")
        return {"check": check, **diagnostic_attempt_identity(entries, context, subject)}
    fail(f"{subject} has an unknown construction check", check)


def read_construction_plan_state(lot, task, subject):
    result = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "plan-state",
         lot, str(task)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(f"{subject} cannot authenticate the current task contract and Design",
             result.stderr or result.stdout)
    try:
        state = json.loads(result.stdout)
    except ValueError:
        fail(f"{subject}'s task-state helper returned malformed JSON", result.stdout)
    required = {
        "plan", "plan_sha256", "plan_projection_sha256", "plan_ownership_sha256",
        "contract_sha256", "design_sha256", "disagreement_sha256",
    }
    if not isinstance(state, dict) or set(state) != required \
            or any(not re.fullmatch(r"[0-9a-f]{64}", state.get(key) or "")
                   for key in ("plan_sha256", "plan_projection_sha256",
                               "plan_ownership_sha256", "contract_sha256", "design_sha256")) \
            or state.get("disagreement_sha256") is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", state["disagreement_sha256"]):
        fail(f"{subject} returned a malformed task contract and Design")
    return state


def construction_plan_generation(identity, subject):
    state = read_construction_plan_state(identity["lot"], identity["task"], subject)
    if state.get("contract_sha256") != identity.get("contract_sha256") \
            or state.get("plan_ownership_sha256") != identity.get("plan_ownership_sha256"):
        fail(f"{subject} does not use the frozen controller contract and one complete Design")
    return {
        "contract_sha256": state["contract_sha256"],
        "design_sha256": state["design_sha256"],
        "plan_projection_sha256": state["plan_projection_sha256"],
        "plan_ownership_sha256": state["plan_ownership_sha256"],
        "disagreement_sha256": state["disagreement_sha256"],
    }


def construction_started_for(entries, before, base):
    return [entry for entry in entries[:before]
            if entry.get("event") == "subagent-started"
            and entry.get("kind") == CONSTRUCTION_CHECKERS.get(base["check"], "diagnostic")
            and entry.get("lot") == base["lot"] and entry.get("task") == base["task"]
            and entry.get("attempt") == base["attempt"]
            and (base["check"] == "diagnostic" or entry.get("round") == base["round"])]


def construction_frozen_logical(entries, before, base, subject):
    starts = construction_started_for(entries, before, base)
    if not starts:
        fail(f"{subject} has no physical-call opening")
    data = note_data(starts[0])
    if not isinstance(data, dict) or data.get("call") != 1:
        fail(f"{subject}'s first physical-call opening is malformed")
    logical = dict(data)
    logical.pop("call", None)
    expected_base = {key: logical.get(key) for key in base}
    if expected_base != base:
        fail(f"{subject}'s frozen logical identity contradicts its attempt")
    return logical


def validate_current_construction_generation(logical, subject):
    if logical.get("check") not in CONSTRUCTION_CHECKERS:
        return
    current = construction_plan_generation(logical, subject)
    if any(current[key] != logical.get(key) for key in current):
        fail(f"{subject} no longer uses its frozen task contract and Design")


def construction_design_proof(entries, before, identity, generation, subject):
    verdicts = [(index, entry) for index, entry in enumerate(entries[:before])
                if entry.get("event") == "note" and entry.get("kind") == "verdict.consumed"
                and entry.get("lot") == identity["lot"] and entry.get("task") == identity["task"]
                and entry.get("attempt") == identity["attempt"]
                and note_data(entry).get("check") == "design"]
    if not verdicts:
        fail(f"{subject} has no accepted Design checker result")
    index, verdict = verdicts[-1]
    data = note_data(verdict)
    stable_keys = (
        "contract_sha256", "design_sha256", "plan_projection_sha256",
        "plan_ownership_sha256",
    )
    if any(data.get(key) != generation[key] for key in stable_keys):
        fail(f"{subject} does not consume the exact current accepted Design")
    if data.get("outcome") == "clean":
        if data.get("disagreement_sha256") != generation.get("disagreement_sha256"):
            fail(f"{subject} changed Disagreement after its clean Design verdict")
    elif data.get("outcome") == "findings" \
            and data.get("round") == CONSTRUCTION_CHECKER_ROUNDS["design"] \
            and construction_positive_integer(data.get("findings")):
        resolutions = [(position, candidate) for position, candidate in design_resolutions(
            entries, before, identity["lot"], identity["task"], identity["attempt"],
        ) if note_data(candidate).get("round") == data["round"]]
        if len(resolutions) != 1 or resolutions[0][0] <= index:
            fail(f"{subject} has no exact final Design settlement")
        resolution_index, resolution = resolutions[0]
        resolution_data = note_data(resolution)
        if resolution_data.get("verdict") != journal_line_proof(index) \
                or resolution_data.get("accepted") != 0:
            fail(f"{subject} has an unresolved or accepted final Design defect")
        if resolution_data.get("disagreement_sha256") != generation.get("disagreement_sha256"):
            fail(f"{subject} does not carry the exact settled Design Disagreement")
        return resolution_index
    else:
        fail(f"{subject} has no accepted Design checker result")
    return index


def construction_review_gate(entries, before, base, gate, tree, subject):
    matches = [(index, note_data(entry)) for index, entry in enumerate(entries[:before])
               if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
               and note_data(entry).get("op") == gate
               and "unusable" not in note_data(entry)]
    if len(matches) != 1:
        fail(f"{subject} has no one exact ordinary gate terminal")
    index, data = matches[0]
    owner = f"{base['lot']}/task-{base['task']}/attempt-{base['attempt']}/code-round-{base['round']}"
    if data.get("scope") != "review" or data.get("owner") != owner \
            or (data.get("lot"), data.get("task"), data.get("attempt")) != (
                base["lot"], base["task"], base["attempt"],
            ) or data.get("tree") != tree or data.get("code") != "-" \
            or data.get("green") is not True or data.get("surface") != "unchanged":
        fail(f"{subject}'s ordinary gate belongs to another candidate or round")
    return index


def previous_code_batch(entries, base, subject):
    if base["round"] == 1:
        retry = base.get("retry")
        if not retry:
            return None, None
        if not retry_code_members(entries, retry, subject):
            return None, None
        return retry_code_batch(entries, retry, subject), None
    prior_round = base["round"] - 1
    verdicts = code_verdicts(
        entries, len(entries), base["lot"], base["task"], base["attempt"],
    )
    matches = [(index, entry) for index, entry in verdicts
               if note_data(entry).get("round") == prior_round]
    if len(matches) != 1 or note_data(matches[0][1]).get("outcome") != "findings":
        fail(f"{subject} has no exact prior findings verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    resolutions = [(index, entry) for index, entry in code_resolutions(
        entries, len(entries), base["lot"], base["task"], base["attempt"],
    ) if note_data(entry).get("round") == prior_round]
    if len(resolutions) != 1 or resolutions[0][0] <= verdict_index:
        fail(f"{subject} has no exact complete correction account for the prior findings")
    resolution_index, resolution = resolutions[0]
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail(f"{subject}'s correction account belongs to another findings verdict")
    report_relative = verdict_data.get("report")
    report_path = os.path.join(WORKSPACE, report_relative or "")
    try:
        raw = Path(report_path).read_bytes()
        report = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        fail(f"{subject} cannot read the prior immutable checker result", exc)
    if hashlib.sha256(raw).hexdigest() != verdict_data.get("report_sha256"):
        fail(f"{subject}'s prior immutable checker result changed")
    findings = report.get("findings") if isinstance(report, dict) else None
    if not isinstance(findings, list) or len(findings) != verdict_data.get("findings"):
        fail(f"{subject}'s prior immutable checker result has no exact findings")
    account = {
        "source": "round",
        "round": prior_round,
        "result": report_relative,
        "result_sha256": verdict_data["report_sha256"],
        "findings": [
            {key: item.get(key) for key in ("id", "where", "what", "why", "impact")}
            for item in findings
        ],
        "resolution": resolution_data.get("items"),
        "resolution_proof": journal_line_proof(resolution_index),
    }
    return account, resolution_index


def construction_review_generation(entries, base, gate, subject):
    if not isinstance(gate, str) or not re.fullmatch(r"[0-9a-f]{64}", gate):
        fail(f"{subject} requires one exact ordinary green-gate operation")
    generation = construction_plan_generation(base, subject)
    design_index = construction_design_proof(entries, len(entries), base, generation, subject)
    gate_check = subprocess.run(
        ["bash", GATE_CHECK, "require-review", gate, base["lot"],
         str(base["task"]), str(base["attempt"])],
        capture_output=True, text=True,
    )
    if gate_check.returncode != 0:
        fail(f"{subject} has no exact green full gate for its candidate",
             gate_check.stderr or gate_check.stdout)
    tree = gate_check.stdout.strip().splitlines()[-1] if gate_check.stdout.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        fail(f"{subject}'s ordinary gate returned no candidate tree")
    prior = [note_data(entry) for entry in entries
             if entry.get("event") == "subagent-started" and entry.get("kind") == "code-checker"
             and entry.get("lot") == base["lot"] and entry.get("task") == base["task"]
             and entry.get("attempt") == base["attempt"] and note_data(entry).get("call") == 1]
    if any(item.get("gate") == gate for item in prior):
        fail(f"{subject}'s ordinary gate was already consumed by another code round")
    if prior and prior[-1].get("tree") == tree:
        fail(f"{subject} did not change the candidate after the prior findings verdict")
    gate_index = construction_review_gate(entries, len(entries), base, gate, tree, subject)
    prior_verdicts = [(index, entry) for index, entry in enumerate(entries)
                      if entry.get("event") == "note" and entry.get("kind") == "verdict.consumed"
                      and entry.get("lot") == base["lot"] and entry.get("task") == base["task"]
                      and entry.get("attempt") == base["attempt"]
                      and note_data(entry).get("check") == "code"]
    previous, resolution_index = previous_code_batch(entries, base, subject)
    predecessor = resolution_index if resolution_index is not None else design_index
    if gate_index <= predecessor:
        fail(f"{subject}'s ordinary gate predates the result that authorizes this round")
    base_ref = f"refs/bwr/{Path(WORKSPACE).name}/{base['lot']}/attempt-base"
    base_commit = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        capture_output=True, text=True,
    )
    if base_commit.returncode != 0:
        fail(f"{subject} has no exact attempt-base commit", base_commit.stderr)
    manifest = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "manifest", base["lot"], str(base["task"]),
         str(base["attempt"]), str(base["round"]), gate, base_commit.stdout.strip(), tree],
        input=json.dumps(previous, ensure_ascii=False, separators=(",", ":")) if previous else "",
        capture_output=True, text=True,
    )
    if manifest.returncode != 0:
        fail(f"{subject} cannot freeze its complete candidate manifest",
             manifest.stderr or manifest.stdout)
    try:
        frozen = json.loads(manifest.stdout)
    except ValueError:
        fail(f"{subject}'s manifest helper returned malformed JSON", manifest.stdout)
    return {
        **generation, "gate": gate, "tree": tree,
        "manifest": frozen.get("path"), "manifest_sha256": frozen.get("sha256"),
    }


def validate_code_generation_history(entries, before, logical, subject):
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if construction_event_matches(entry, logical, "subagent-started")]
    if not starts:
        fail(f"{subject} has no code-checker opening")
    start_index = starts[0][0]
    expected_keys = {
        "check", "lot", "task", "attempt", "round", "plan_manifest", "plan_tasks",
        "plan_ownership_sha256", "contract_sha256", "design_sha256",
        "plan_projection_sha256", "disagreement_sha256", "gate", "tree", "manifest",
        "manifest_sha256", "retry",
    }
    if set(logical) != expected_keys \
            or any(not re.fullmatch(r"[0-9a-f]{64}", logical.get(key, ""))
                   for key in ("plan_ownership_sha256", "contract_sha256", "design_sha256",
                               "plan_projection_sha256", "gate", "manifest_sha256")) \
            or logical.get("disagreement_sha256") is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", logical.get("disagreement_sha256", "")) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", logical.get("tree", "")):
        fail(f"{subject} has a malformed exact code-review generation")
    gate_index = construction_review_gate(
        entries, start_index, logical, logical["gate"], logical["tree"], subject,
    )
    design_index = construction_design_proof(
        entries, start_index, logical, logical, subject,
    )
    prior = [(index, entry) for index, entry in code_verdicts(
        entries, start_index, logical["lot"], logical["task"], logical["attempt"],
    )]
    if len(prior) != logical["round"] - 1:
        fail(f"{subject} has the wrong number of prior code-review generations")
    previous, resolution_index = previous_code_batch(entries[:start_index], logical, subject)
    predecessor = resolution_index if resolution_index is not None else design_index
    if gate_index <= predecessor:
        fail(f"{subject}'s ordinary gate predates its required predecessor")
    if prior:
        prior_data = note_data(prior[-1][1])
        if prior_data.get("outcome") != "findings" or prior_data.get("tree") == logical["tree"]:
            fail(f"{subject} does not follow findings with one changed gated candidate")
    manifest_previous = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "previous", logical["manifest"]],
        capture_output=True, text=True,
    )
    try:
        frozen_previous = json.loads(manifest_previous.stdout) \
            if manifest_previous.returncode == 0 else object()
    except ValueError:
        frozen_previous = object()
    if frozen_previous != previous:
        fail(f"{subject}'s manifest does not carry its exact prior findings account", {
            "lot": logical["lot"], "task": logical["task"],
            "attempt": logical["attempt"], "round": logical["round"],
            "manifest": logical["manifest"],
            "frozen": manifest_previous.stderr or manifest_previous.stdout,
            "expected": previous,
        })
    reused = [entry for entry in entries[:start_index]
              if entry.get("event") == "subagent-started" and entry.get("kind") == "code-checker"
              and note_data(entry).get("gate") == logical["gate"]]
    if reused:
        fail(f"{subject} reuses another code round's ordinary gate")


def validate_design_generation_history(entries, before, logical, subject):
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if construction_event_matches(entry, logical, "subagent-started")]
    if not starts:
        fail(f"{subject} has no design-checker opening")
    start_index = starts[0][0]
    expected_keys = {
        "check", "lot", "task", "attempt", "round", "plan_manifest", "plan_tasks",
        "plan_ownership_sha256", "contract_sha256", "design_sha256",
        "plan_projection_sha256", "disagreement_sha256", "manifest",
        "manifest_sha256", "retry",
    }
    if set(logical) != expected_keys or any(
        not re.fullmatch(r"[0-9a-f]{64}", logical.get(key, ""))
        for key in (
            "plan_ownership_sha256", "contract_sha256", "design_sha256",
            "plan_projection_sha256", "manifest_sha256",
        )
    ) or logical.get("disagreement_sha256") is not None and not re.fullmatch(
        r"[0-9a-f]{64}", logical.get("disagreement_sha256", ""),
    ):
        fail(f"{subject} has a malformed exact design-review generation")
    manifest_path = exact_real_file(
        WORKSPACE, logical.get("manifest"), f"{subject}'s design-review manifest",
    )
    payload = Path(manifest_path).read_bytes()
    if sha256_bytes(payload) != logical["manifest_sha256"]:
        fail(f"{subject}'s design-review manifest changed")
    try:
        manifest = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"{subject}'s design-review manifest is malformed", exc)
    expected_manifest = {
        "lot": logical["lot"], "task": logical["task"],
        "attempt": logical["attempt"], "round": logical["round"],
        "plan_ownership_sha256": logical["plan_ownership_sha256"],
        "contract_sha256": logical["contract_sha256"],
        "design_sha256": logical["design_sha256"],
        "plan_projection_sha256": logical["plan_projection_sha256"],
        "disagreement_sha256": logical["disagreement_sha256"],
    }
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in expected_manifest.items()
    ):
        fail(f"{subject}'s design-review manifest contradicts its frozen generation")
    prior = design_verdicts(
        entries, start_index, logical["lot"], logical["task"], logical["attempt"],
    )
    if len(prior) != logical["round"] - 1:
        fail(f"{subject} has the wrong number of prior design-review generations")
    expected_previous = design_previous_batch(entries[:start_index], logical, subject)
    if manifest.get("previous") != expected_previous:
        fail(f"{subject}'s design manifest changes its prior findings account")


def construction_event_matches(entry, logical, event):
    if entry.get("event") != event:
        return False
    expected_kind = CONSTRUCTION_CHECKERS.get(logical["check"], "diagnostic")
    if entry.get("kind") != expected_kind:
        return False
    keys = ("lot", "task", "attempt")
    if any(entry.get(key) != logical[key] for key in keys):
        return False
    return logical["check"] == "diagnostic" or entry.get("round") == logical["round"]


def construction_result_shape(data, logical, call, subject):
    base = {**logical, "call": call}
    if not isinstance(data, dict):
        fail(f"{subject} has no structured physical result")
    if set(data) == {*base, "unusable"}:
        if data != {**base, "unusable": data.get("unusable")} \
                or data.get("unusable") not in CONSTRUCTION_UNUSABLE_RESULTS:
            fail(f"{subject} has an invalid unusable-result reason")
        return False
    if logical["check"] == "design":
        result_keys = {
            "outcome", "findings", "critical", "important", "minor",
            "report", "report_sha256", "manifest", "manifest_sha256",
        }
        if set(data) != {*base, *result_keys} \
                or data.get("outcome") not in {"clean", "findings"} \
                or not isinstance(data.get("findings"), int) \
                or isinstance(data.get("findings"), bool) or data["findings"] < 0 \
                or any(not isinstance(data.get(key), int) or isinstance(data.get(key), bool)
                       or data[key] < 0 for key in ("critical", "important", "minor")) \
                or data["findings"] != data["critical"] + data["important"] + data["minor"] \
                or data["outcome"] != ("clean" if data["findings"] == 0 else "findings") \
                or data.get("manifest") != logical.get("manifest") \
                or data.get("manifest_sha256") != logical.get("manifest_sha256") \
                or not isinstance(data.get("report"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", data.get("report_sha256", "")):
            fail(f"{subject} has an invalid audited design-checker result")
        audit = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "publish-design-result",
             logical["manifest"], os.path.join(WORKSPACE, data["report"])],
            capture_output=True, text=True,
        )
        if audit.returncode != 0:
            fail(f"{subject}'s design-checker result artifact is invalid",
                 audit.stderr or audit.stdout)
        try:
            expected = json.loads(audit.stdout)
        except ValueError:
            fail(f"{subject}'s design-checker result audit returned malformed JSON")
        if any(data.get(key) != value for key, value in expected.items()):
            fail(f"{subject}'s design-checker result contradicts its immutable artifact")
        return True
    if logical["check"] == "code":
        result_keys = {
            "outcome", "findings", "critical", "important", "minor",
            "report", "report_sha256",
            "manifest", "manifest_sha256",
        }
        if set(data) != {*base, *result_keys} \
                or data.get("outcome") not in {"clean", "findings"} \
                or not isinstance(data.get("findings"), int) \
                or isinstance(data.get("findings"), bool) or data["findings"] < 0 \
                or any(not isinstance(data.get(key), int) or isinstance(data.get(key), bool)
                       or data[key] < 0 for key in ("critical", "important", "minor")) \
                or data["findings"] != data["critical"] + data["important"] + data["minor"] \
                or data["outcome"] != ("clean" if data["findings"] == 0 else "findings") \
                or data.get("manifest") != logical.get("manifest") \
                or data.get("manifest_sha256") != logical.get("manifest_sha256") \
                or not isinstance(data.get("report"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", data.get("report_sha256", "")):
            fail(f"{subject} has an invalid audited code-checker result")
        audit = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "publish-result",
             logical["manifest"], os.path.join(WORKSPACE, data["report"])],
            capture_output=True, text=True,
        )
        if audit.returncode != 0:
            fail(f"{subject}'s code-checker result artifact is invalid",
                 audit.stderr or audit.stdout)
        try:
            expected = json.loads(audit.stdout)
        except ValueError:
            fail(f"{subject}'s code-checker result audit returned malformed JSON")
        if any(data.get(key) != value for key, value in expected.items()):
            fail(f"{subject}'s code-checker result contradicts its immutable artifact")
        return True
    classification = data.get("classification")
    if set(data) != {*base, "classification"} \
            or data != {**base, "classification": classification} \
            or classification not in CONSTRUCTION_CLASSIFICATIONS:
        fail(f"{subject} has an invalid diagnostic classification")
    return True


def construction_physical_calls(entries, before, logical, subject, *, require_closed):
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if construction_event_matches(entry, logical, "subagent-started")]
    ends = [(index, entry) for index, entry in enumerate(entries[:before])
            if construction_event_matches(entry, logical, "subagent-ended")]
    expected_calls = list(range(1, len(starts) + 1))
    if [note_data(entry).get("call") for _, entry in starts] != expected_calls \
            or any(note_data(entry) != {**logical, "call": call}
                   for (_, entry), call in zip(starts, expected_calls)):
        fail(f"{subject} has malformed or non-contiguous physical checker openings")
    paired = []
    for call, (start_index, start) in zip(expected_calls, starts):
        matches = [(end_index, entry) for end_index, entry in ends
                   if note_data(entry).get("call") == call]
        if len(matches) > 1 or require_closed and len(matches) != 1:
            fail(f"{subject} has an open or multiply closed physical call", call)
        if matches:
            end_index, end = matches[0]
            if end_index <= start_index:
                fail(f"{subject} has a physical result before its opening", call)
            successful = construction_result_shape(
                note_data(end), logical, call, subject,
            )
            paired.append((start, end, successful))
        else:
            paired.append((start, None, False))
    if any(note_data(entry).get("call") not in expected_calls for _, entry in ends):
        fail(f"{subject} has a physical result without its opening")
    return paired


def construction_domain_text(logical):
    if logical["check"] in CONSTRUCTION_CHECKERS:
        round_limit = CONSTRUCTION_CHECKER_ROUNDS[logical["check"]]
        return f"{logical['check']} checker round {logical['round']} of {round_limit}"
    return "diagnostic ran - once per task"


def construction_raw_domain_spends(entries, before, logical):
    spends = [entry for entry in entries[:before] if entry.get("event") == "note"
              and entry.get("kind") == "bound.spent"
              and entry.get("lot") == logical["lot"] and entry.get("task") == logical["task"]
              and entry.get("attempt") == logical["attempt"]
              and (logical["check"] == "diagnostic" or entry.get("round") == logical["round"])
              and entry.get("text") == construction_domain_text(logical)]
    if any(note_data(entry) != logical for entry in spends):
        fail(f"the {logical['check']} logical spend has malformed durable identity")
    return spends


def construction_spend_recoveries(entries, before, logical):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note"
            and entry.get("kind") == "construction.spend.recovered"
            and note_data(entry).get("check") == logical["check"]
            and entry.get("lot") == logical["lot"]
            and entry.get("task") == logical["task"]
            and entry.get("attempt") == logical["attempt"]
            and (logical["check"] == "diagnostic"
                 or entry.get("round") == logical["round"])]


def construction_spend_recovery_logical(data):
    return {key: value for key, value in data.items() if key not in {
        "schema", "physical_owner", "opening", "spends", "canonical_spend",
    }}


def construction_spend_recovery_account(entries, before, base, subject):
    logical = construction_frozen_logical(entries, before, base, subject)
    raw_spends = construction_raw_domain_spends(entries, before, logical)
    if len(raw_spends) < 2:
        fail(f"{subject} has no duplicate logical spends")
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if construction_event_matches(entry, logical, "subagent-started")]
    paired = construction_physical_calls(
        entries, before, logical, subject, require_closed=False,
    )
    if len(starts) != 1 or len(paired) != 1 or paired[0][1] is not None:
        fail(f"{subject} has no one exact first open physical call")
    opening_index, opening = starts[0]
    spend_indexes = [index for index, entry in enumerate(entries[:before])
                     if entry is not None and any(entry is spend for spend in raw_spends)]
    if any(index <= opening_index for index in spend_indexes):
        fail(f"{subject} has a logical spend outside its first physical bracket")
    opening_context = {key: opening[key] for key in CONTEXT_FIELDS if key in opening}
    expected_context = {
        "mode": "construction", "lot": logical["lot"], "task": logical["task"],
        "attempt": logical["attempt"],
    }
    if logical["check"] in CONSTRUCTION_CHECKERS:
        expected_context["round"] = logical["round"]
    if any(opening_context.get(key) != value for key, value in expected_context.items()) \
            or "mandate" in opening_context \
            or any({key: spend[key] for key in CONTEXT_FIELDS if key in spend}
                   != opening_context for spend in raw_spends):
        fail(f"{subject} changes its physical-call journal context")
    physical_owner = opening.get("by")
    if not isinstance(physical_owner, str) or not physical_owner \
            or any(spend.get("by") != physical_owner for spend in raw_spends):
        fail(f"{subject} changes its physical owner")
    return {
        **logical,
        "schema": 1,
        "physical_owner": physical_owner,
        "opening": journal_line_proof(opening_index),
        "spends": [journal_line_proof(index) for index in spend_indexes],
        "canonical_spend": journal_line_proof(spend_indexes[0]),
    }


def validate_construction_spend_recovery_entry(entries, index, entry):
    data = note_data(entry)
    check = data.get("check")
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt")}
    if check in CONSTRUCTION_CHECKERS:
        base["round"] = data.get("round")
    elif check != "diagnostic":
        fail("a durable logical-spend recovery has an unknown checker identity")
    if entry.get("mode") != "construction" or entry.get("job") != "controller" \
            or entry.get("lot") != base["lot"] or entry.get("task") != base["task"] \
            or entry.get("attempt") != base["attempt"] \
            or check in CONSTRUCTION_CHECKERS and entry.get("round") != base.get("round") \
            or check == "diagnostic" and "round" in entry \
            or "mandate" in entry or entry.get("text") is not None:
        fail("a durable logical-spend recovery changes its journal context")
    if construction_spend_recoveries(entries, index, data):
        fail("a logical-spend identity has more than one recovery")
    expected = construction_spend_recovery_account(
        entries, index, base, "the durable logical-spend recovery",
    )
    if data != expected:
        fail("a durable logical-spend recovery changes its complete authority", expected)


def construction_domain_spends(entries, before, logical):
    spends = construction_raw_domain_spends(entries, before, logical)
    recoveries = construction_spend_recoveries(entries, before, logical)
    if len(spends) <= 1:
        if recoveries:
            fail(f"the {logical['check']} logical spend has a recovery without duplicates")
        return spends
    if len(recoveries) != 1:
        fail(f"the {logical['check']} logical spend has unowned duplicate events")
    recovery_index, recovery = recoveries[0]
    validate_construction_spend_recovery_entry(entries, recovery_index, recovery)
    spend_indexes = [index for index, candidate in enumerate(entries[:before])
                     if any(candidate is spend for spend in spends)]
    spend_proofs = [journal_line_proof(index) for index in spend_indexes]
    if note_data(recovery).get("spends") != spend_proofs \
            or note_data(recovery).get("canonical_spend") != spend_proofs[0]:
        fail(f"the {logical['check']} logical spend recovery omits a duplicate event")
    return spends[:1]


def construction_task_diagnostic_spends(entries, before, lot, task):
    return [entry for entry in entries[:before] if entry.get("event") == "note"
            and entry.get("kind") == "bound.spent"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("text") == "diagnostic ran - once per task"]


def construction_consumed(entries, before, logical):
    return [entry for entry in entries[:before] if entry.get("event") == "note"
            and entry.get("kind") == "verdict.consumed"
            and entry.get("lot") == logical["lot"] and entry.get("task") == logical["task"]
            and entry.get("attempt") == logical["attempt"]
            and note_data(entry).get("check") == logical["check"]
            and (logical["check"] == "diagnostic" or entry.get("round") == logical["round"])]


def normalize_construction_started(entries, data, context, check, round_number):
    if check != "code" and data is not None:
        fail(f"subagent-started {CONSTRUCTION_CHECKERS.get(check, check)} derives its identity")
    if check == "code" and (
        not isinstance(data, dict) or set(data) != {"gate"}
    ):
        fail("subagent-started code-checker requires only its ordinary gate operation")
    validate_construction_verdict_history(entries)
    logical = construction_logical_identity(
        entries, context, check, round_number, f"a {check} physical checker opening",
    )
    if construction_consumed(entries, len(entries), logical):
        fail(f"the {check} logical result was already consumed")
    if check == "diagnostic":
        task_spends = construction_task_diagnostic_spends(
            entries, len(entries), logical["lot"], logical["task"],
        )
        exact_spends = construction_domain_spends(entries, len(entries), logical)
        if task_spends and task_spends != exact_spends:
            fail("this task's logical diagnostic belongs to another failed attempt")
    if check in CONSTRUCTION_CHECKERS:
        previous = [entry for entry in entries if entry.get("kind") == "verdict.consumed"
                    and entry.get("lot") == logical["lot"]
                    and entry.get("task") == logical["task"]
                    and entry.get("attempt") == logical["attempt"]
                    and note_data(entry).get("check") == check]
        if logical["round"] != len(previous) + 1:
            fail(f"the {check} checker has the wrong logical round")
        if previous and note_data(previous[-1]).get("outcome") != "findings":
            fail(f"a clean {check} verdict cannot open another logical round")
    starts = construction_started_for(entries, len(entries), logical)
    if starts:
        frozen = construction_frozen_logical(
            entries, len(entries), logical, f"the {check} logical round",
        )
        if check == "code" and frozen.get("gate") != data.get("gate"):
            fail("a regenerated code-checker call must keep the frozen ordinary gate")
        logical = frozen
    elif check in CONSTRUCTION_CHECKERS:
        generation = construction_plan_generation(logical, f"the {check} logical round")
        if check == "code":
            generation = construction_review_generation(
                entries, logical, data.get("gate"), "the code-checker opening",
            )
        else:
            previous_account = design_previous_batch(
                entries, {**logical, **generation}, "the design-checker opening",
            )
            manifest = subprocess.run(
                [sys.executable, CONSTRUCTION_REVIEW, "design-manifest",
                 logical["lot"], str(logical["task"]), str(logical["attempt"]),
                 str(logical["round"])],
                input=json.dumps(previous_account) if previous_account else "",
                capture_output=True, text=True,
            )
            if manifest.returncode != 0:
                fail("the design-checker opening cannot freeze its exact generation",
                     manifest.stderr or manifest.stdout)
            try:
                frozen_manifest = json.loads(manifest.stdout)
            except ValueError:
                fail("the design-review manifest helper returned malformed JSON")
            generation = {
                **generation,
                "manifest": frozen_manifest.get("path"),
                "manifest_sha256": frozen_manifest.get("sha256"),
            }
        logical = {**logical, **generation}
    paired = construction_physical_calls(
        entries, len(entries), logical, f"the {check} logical round", require_closed=True,
    )
    spends = construction_domain_spends(entries, len(entries), logical)
    if len(spends) > 1 or paired and not spends:
        fail(f"the {check} physical regeneration has no one exact logical spend")
    return {**logical, "call": len(paired) + 1}


def normalize_construction_spend(entries, data, text, context, check, round_number):
    if data is not None:
        fail(f"a {check} domain spend derives its identity and takes no --data")
    validate_construction_verdict_history(entries)
    logical = construction_logical_identity(
        entries, context, check, round_number, f"a {check} logical spend",
    )
    if check in CONSTRUCTION_CHECKERS:
        logical = construction_frozen_logical(
            entries, len(entries), logical, f"the {check} logical spend",
        )
    if text != construction_domain_text(logical):
        fail(f"a {check} logical spend has malformed text", {
            "expected": construction_domain_text(logical), "actual": text,
        })
    if check == "diagnostic" and construction_task_diagnostic_spends(
        entries, len(entries), logical["lot"], logical["task"],
    ):
        fail("the task-level logical diagnostic spend already exists")
    if construction_domain_spends(entries, len(entries), logical):
        fail(f"the {check} logical spend already exists")
    paired = construction_physical_calls(
        entries, len(entries), logical, f"the {check} logical spend", require_closed=False,
    )
    if len(paired) != 1 or paired[0][1] is not None:
        fail(f"the {check} logical spend does not follow its first open physical call")
    return logical


def normalize_construction_ended(entries, data, context, check, round_number):
    validate_construction_verdict_history(entries)
    logical = construction_logical_identity(
        entries, context, check, round_number, f"a {check} physical result",
    )
    if check in CONSTRUCTION_CHECKERS:
        logical = construction_frozen_logical(
            entries, len(entries), logical, f"the {check} physical result",
        )
        validate_current_construction_generation(logical, f"the {check} physical result")
    if len(construction_domain_spends(entries, len(entries), logical)) != 1:
        fail(f"a {check} physical result has no one exact logical spend")
    paired = construction_physical_calls(
        entries, len(entries), logical, f"the {check} logical round", require_closed=False,
    )
    open_calls = [index + 1 for index, (_, ended, _) in enumerate(paired) if ended is None]
    if open_calls != [len(paired)]:
        fail(f"a {check} physical result has no one exact latest open call")
    call = open_calls[0]
    if not isinstance(data, dict):
        fail(f"a {check} physical result requires structured data")
    if set(data) == {"unusable"}:
        result = {**logical, "call": call, "unusable": data.get("unusable")}
    elif check == "design" and set(data) == {"result"} \
            and isinstance(data.get("result"), str) and data["result"]:
        audit = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "publish-design-result",
             logical["manifest"], data["result"]], capture_output=True, text=True,
        )
        if audit.returncode != 0:
            fail("the design-checker physical result is not one complete audited result",
                 audit.stderr or audit.stdout)
        try:
            outcome = json.loads(audit.stdout)
        except ValueError:
            fail("the design-checker result helper returned malformed JSON", audit.stdout)
        result = {**logical, "call": call, **outcome}
    elif check == "code" and set(data) == {"result"} \
            and isinstance(data.get("result"), str) and data["result"]:
        audit = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "publish-result",
             logical["manifest"], data["result"]], capture_output=True, text=True,
        )
        if audit.returncode != 0:
            fail("the code-checker physical result is not one complete audited result",
                 audit.stderr or audit.stdout)
        try:
            outcome = json.loads(audit.stdout)
        except ValueError:
            fail("the code-checker result helper returned malformed JSON", audit.stdout)
        result = {**logical, "call": call, **outcome}
    elif check == "diagnostic" and set(data) == {"classification"}:
        result = {**logical, "call": call, "classification": data.get("classification")}
    else:
        fail(f"a {check} physical result has malformed structured data", data)
    construction_result_shape(result, logical, call, f"the {check} physical result")
    return result


def construction_expected_verdict(logical, result, text):
    result_data = note_data(result)
    call = result_data["call"]
    if logical["check"] == "design":
        if text is not None:
            fail("a design-checker verdict derives its evidence from the immutable result artifact")
        return dict(result_data)
    if logical["check"] == "code":
        if text is not None:
            fail("a code-checker verdict derives its evidence from the immutable result artifact")
        return dict(result_data)
    if not isinstance(text, str) or not text.strip():
        fail("a diagnostic verdict requires its exact non-empty analysis text")
    classification = result_data["classification"]
    return {**logical, "call": call, "outcome": classification}


def normalize_construction_verdict(entries, data, text, context, check, round_number):
    if not isinstance(data, dict) or set(data) != {"check", "outcome"} \
            or data.get("check") != check:
        fail(f"a {check} consumed verdict has malformed structured data", data)
    validate_construction_verdict_history(entries)
    logical = construction_logical_identity(
        entries, context, check, round_number, f"a {check} consumed verdict",
    )
    if check in CONSTRUCTION_CHECKERS:
        logical = construction_frozen_logical(
            entries, len(entries), logical, f"the {check} consumed verdict",
        )
        validate_current_construction_generation(logical, f"the {check} consumed verdict")
    if construction_consumed(entries, len(entries), logical):
        fail(f"the {check} logical result was already consumed")
    if len(construction_domain_spends(entries, len(entries), logical)) != 1:
        fail(f"a {check} consumed verdict has no one exact logical spend")
    paired = construction_physical_calls(
        entries, len(entries), logical, f"the {check} consumed verdict", require_closed=True,
    )
    successful = [ended for _, ended, success in paired if success]
    if not successful:
        fail(f"a {check} consumed verdict has no successful physical result")
    expected = construction_expected_verdict(logical, successful[-1], text)
    if data["outcome"] != expected["outcome"]:
        fail(f"a {check} consumed verdict contradicts its physical result")
    return expected


def validate_construction_verdict_entry(entries, index, entry):
    data = note_data(entry)
    check = data.get("check")
    if check not in {*CONSTRUCTION_CHECKERS, "diagnostic"}:
        fail("a durable construction verdict has an unknown checker identity")
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt")}
    if check in CONSTRUCTION_CHECKERS:
        base["round"] = data.get("round")
    if not isinstance(base["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", base["lot"]) \
            or not construction_positive_integer(base["task"]) \
            or not construction_positive_integer(base["attempt"]) \
            or check in CONSTRUCTION_CHECKERS and (
                not construction_positive_integer(base.get("round"))
                or base["round"] > CONSTRUCTION_CHECKER_ROUNDS[check]
            ):
        fail("a durable construction verdict has malformed logical identity")
    if any(entry.get(key) != base[key] for key in ("lot", "task", "attempt")) \
            or check in CONSTRUCTION_CHECKERS and entry.get("round") != base["round"]:
        fail("a durable construction verdict changes its journal context identity")
    logical = construction_frozen_logical(
        entries, index, base, "a durable construction verdict",
    ) if check in CONSTRUCTION_CHECKERS else base
    if check == "design":
        validate_design_generation_history(
            entries, index, logical, "a durable construction verdict",
        )
    elif check == "code":
        validate_code_generation_history(
            entries, index, logical, "a durable construction verdict",
        )
    spends = construction_domain_spends(entries, index, logical)
    if len(spends) != 1:
        fail("a durable construction verdict has no one exact logical spend")
    spend_index = next(position for position, candidate in enumerate(entries[:index])
                       if candidate is spends[0])
    start_indexes = [position for position, candidate in enumerate(entries[:index])
                     if construction_event_matches(candidate, logical, "subagent-started")]
    end_indexes = [position for position, candidate in enumerate(entries[:index])
                   if construction_event_matches(candidate, logical, "subagent-ended")]
    if not start_indexes or not end_indexes \
            or not start_indexes[0] < spend_index < min(end_indexes):
        fail("a durable construction logical spend is outside its first physical bracket")
    paired = construction_physical_calls(
        entries, index, logical, "a durable construction verdict", require_closed=True,
    )
    successful = [ended for _, ended, success in paired if success]
    if not successful:
        fail("a durable construction verdict has no successful physical result")
    expected = construction_expected_verdict(logical, successful[-1], entry.get("text"))
    if data != expected:
        fail("a durable construction verdict does not consume its latest successful result", expected)
    if construction_consumed(entries, index, logical):
        fail("a construction logical result was consumed more than once")
    if check in CONSTRUCTION_CHECKERS:
        previous = [candidate for candidate in entries[:index]
                    if candidate.get("kind") == "verdict.consumed"
                    and candidate.get("lot") == logical["lot"]
                    and candidate.get("task") == logical["task"]
                    and candidate.get("attempt") == logical["attempt"]
                    and note_data(candidate).get("check") == check]
        if logical["round"] != len(previous) + 1:
            fail(f"a durable {check} verdict has the wrong logical-round sequence")
    else:
        prior_task_spends = construction_task_diagnostic_spends(
            entries, index, logical["lot"], logical["task"],
        )
        if len(prior_task_spends) != 1:
            fail("a durable diagnostic verdict does not consume the task's one logical spend")


def code_resolution_text_items(text, subject, statuses):
    if not isinstance(text, str) or not text.strip():
        fail(f"{subject} requires one exact non-empty disposition account")
    lines = text.splitlines()
    headings = []
    for index, line in enumerate(lines):
        if not line.startswith("## Finding "):
            continue
        match = re.fullmatch(
            rf"## Finding ([1-9][0-9]*) — ({'|'.join(sorted(statuses))})", line,
        )
        if not match:
            fail(f"{subject} has a malformed finding heading", line)
        headings.append((index, int(match.group(1)), match.group(2)))
    if not headings or any(line.strip() for line in lines[:headings[0][0]]):
        fail(f"{subject} must begin with its first finding heading")
    expected_ids = list(range(1, len(headings) + 1))
    if [finding for _, finding, _ in headings] != expected_ids:
        fail(f"{subject} has non-contiguous or duplicate finding identities")
    items = []
    for position, (start, finding, status) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        evidence = "\n".join(line for line in lines[start + 1:end]).strip()
        if not evidence:
            fail(f"{subject} finding {finding} has no durable explanation")
        items.append({"id": finding, "status": status, "evidence": evidence})
    return items


def design_verdicts(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "verdict.consumed"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt and note_data(entry).get("check") == "design"]


def design_resolutions(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "design.review.resolved"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt]


def design_blockers(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "design.review.blocked"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt]


def immutable_design_result(verdict_data, subject):
    result_relative = verdict_data.get("report")
    result_path = exact_real_file(WORKSPACE, result_relative, f"{subject}'s design-checker result")
    payload = Path(result_path).read_bytes()
    if sha256_bytes(payload) != verdict_data.get("report_sha256"):
        fail(f"{subject}'s design-checker result changed")
    try:
        result = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"{subject}'s design-checker result is malformed", exc)
    findings = result.get("findings") if isinstance(result, dict) else None
    expected_ids = list(range(1, verdict_data.get("findings", 0) + 1))
    if not findings or len(findings) != verdict_data.get("findings") \
            or [item.get("id") for item in findings if isinstance(item, dict)] != expected_ids:
        fail(f"{subject} has no exact immutable Design findings batch")
    return result, findings


def design_previous_batch(entries, base, subject):
    if base["round"] == 1:
        retry = base.get("retry")
        if not retry:
            return None
        if not retry_design_members(entries, retry, subject):
            return None
        return retry_design_batch(entries, retry, subject)
    prior_round = base["round"] - 1
    verdicts = [(index, entry) for index, entry in design_verdicts(
        entries, len(entries), base["lot"], base["task"], base["attempt"],
    ) if note_data(entry).get("round") == prior_round]
    resolutions = [(index, entry) for index, entry in design_resolutions(
        entries, len(entries), base["lot"], base["task"], base["attempt"],
    ) if note_data(entry).get("round") == prior_round]
    if len(verdicts) != 1 or note_data(verdicts[0][1]).get("outcome") != "findings" \
            or len(resolutions) != 1 or resolutions[0][0] <= verdicts[0][0]:
        fail(f"{subject} has no exact prior findings and resolution account")
    verdict_index, verdict = verdicts[0]
    resolution_index, resolution = resolutions[0]
    verdict_data = note_data(verdict)
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail(f"{subject}'s prior resolution belongs to another design verdict")
    if resolution_data.get("next_design_sha256") != base.get("design_sha256") \
            or resolution_data.get("next_plan_projection_sha256") != base.get(
                "plan_projection_sha256"
            ):
        fail(f"{subject} does not use the exact Design produced by its prior correction")
    result_path = exact_real_file(
        WORKSPACE, verdict_data.get("report"), f"{subject}'s prior design-checker result",
    )
    payload = Path(result_path).read_bytes()
    if sha256_bytes(payload) != verdict_data.get("report_sha256"):
        fail(f"{subject}'s prior design-checker result changed")
    try:
        result = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"{subject}'s prior design-checker result is malformed", exc)
    findings = result.get("findings") if isinstance(result, dict) else None
    if not isinstance(findings, list) or len(findings) != verdict_data.get("findings"):
        fail(f"{subject}'s prior design-checker result has no exact findings batch")
    return {
        "source": "round", "round": prior_round,
        "result": verdict_data["report"],
        "result_sha256": verdict_data["report_sha256"],
        "findings": [
            {key: item[key] for key in ("id", "where", "what", "why", "impact")}
            for item in findings
        ],
        "resolution": resolution_data["items"],
        "resolution_proof": journal_line_proof(resolution_index),
    }


def code_verdicts(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "verdict.consumed"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt and note_data(entry).get("check") == "code"]


def code_resolutions(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "code.review.resolved"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt]


def code_blockers(entries, before, lot, task, attempt):
    return [(index, entry) for index, entry in enumerate(entries[:before])
            if entry.get("event") == "note" and entry.get("kind") == "code.review.blocked"
            and entry.get("lot") == lot and entry.get("task") == task
            and entry.get("attempt") == attempt]


def journal_entry_from_proof(entries, proof, subject):
    match = re.fullmatch(r"(0|[1-9][0-9]*):([0-9a-f]{64})", str(proof))
    if not match:
        fail(f"{subject} has a malformed journal proof")
    index = int(match.group(1))
    if index >= len(entries) or journal_line_proof(index) != proof:
        fail(f"{subject} names no exact durable journal line")
    return index, entries[index]


def design_failure_handoff(entries, before, lot, task, attempt, subject):
    blockers = design_blockers(entries, before, lot, task, attempt)
    if blockers:
        if len(blockers) != 1:
            fail(f"{subject} has more than one Design controller-contract blocker")
        blocker_index, blocker = blockers[0]
        blocker_data = note_data(blocker)
        round_number = blocker_data.get("round")
        verdicts = [(index, entry) for index, entry in design_verdicts(
            entries, blocker_index, lot, task, attempt,
        ) if note_data(entry).get("round") == round_number]
        resolutions = [(index, entry) for index, entry in design_resolutions(
            entries, blocker_index, lot, task, attempt,
        ) if note_data(entry).get("round") == round_number]
        if resolutions:
            fail(f"{subject} has both settlement and blocker terminals for one Design batch")
        if len(verdicts) != 1:
            fail(f"{subject} has no one exact Design verdict for its blocker")
        verdict_index, verdict = verdicts[0]
        verdict_data = note_data(verdict)
        if verdict_data.get("outcome") != "findings" or blocker_index <= verdict_index:
            fail(f"{subject} has no one ordered Design blocker terminal")
        if blocker_data.get("verdict") != journal_line_proof(verdict_index):
            fail(f"{subject}'s Design blocker belongs to another checker verdict")
        result, findings = immutable_design_result(verdict_data, subject)
        required = [item["id"] for item in findings]
        contract_blocked = [
            item["id"] for item in findings if item.get("where") == "frozen task contract"
        ]
        if blocker_data.get("required") != required \
                or blocker_data.get("contract_blocked") != contract_blocked \
                or blocker_data.get("result") != verdict_data.get("report") \
                or blocker_data.get("result_sha256") != verdict_data.get("report_sha256"):
            fail(f"{subject}'s Design blocker changes its immutable findings batch")
        obligation = {
            "schema": 1,
            "verdict": journal_line_proof(verdict_index),
            "blocked": journal_line_proof(blocker_index),
            "result": verdict_data["report"],
            "result_sha256": verdict_data["report_sha256"],
            "checker_result": result,
            "required": required,
            "contract_blocked": contract_blocked,
        }
        return {
            "unresolved": False, "blocked": True, "obligation": obligation,
            "required": required, "contract_blocked": contract_blocked,
        }

    intermediate_verdicts = [(index, entry) for index, entry in design_verdicts(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") < CONSTRUCTION_CHECKER_ROUNDS["design"]
       and note_data(entry).get("outcome") == "findings"]
    for verdict_index, verdict in intermediate_verdicts:
        round_number = note_data(verdict).get("round")
        resolutions = [(index, entry) for index, entry in design_resolutions(
            entries, before, lot, task, attempt,
        ) if note_data(entry).get("round") == round_number]
        if not resolutions:
            return {"unresolved": True}
        if len(resolutions) != 1 or resolutions[0][0] <= verdict_index:
            fail(f"{subject} has no one ordered intermediate design-review resolution")
        if note_data(resolutions[0][1]).get("verdict") != journal_line_proof(verdict_index):
            fail(f"{subject}'s intermediate Design resolution belongs to another verdict")

    verdicts = [(index, entry) for index, entry in design_verdicts(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == CONSTRUCTION_CHECKER_ROUNDS["design"]]
    if not verdicts:
        return None
    if len(verdicts) != 1:
        fail(f"{subject} has more than one final design-checker verdict")
    verdict_index, verdict = verdicts[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings":
        return None
    resolutions = [(index, entry) for index, entry in design_resolutions(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == CONSTRUCTION_CHECKER_ROUNDS["design"]]
    if not resolutions:
        return {"unresolved": True}
    if len(resolutions) != 1 or resolutions[0][0] <= verdict_index:
        fail(f"{subject} has no one ordered final design-review settlement")
    resolution_index, resolution = resolutions[0]
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail(f"{subject}'s final design settlement belongs to another checker verdict")
    if resolution_data.get("accepted") == 0:
        return None
    if not construction_positive_integer(resolution_data.get("accepted")):
        fail(f"{subject}'s final design settlement has a malformed accepted count")
    result_relative = verdict_data.get("report")
    result, findings = immutable_design_result(verdict_data, subject)
    dispositions = resolution_data.get("items")
    if not isinstance(findings, list) or len(findings) != verdict_data.get("findings") \
            or not isinstance(dispositions, list) or len(dispositions) != len(findings):
        fail(f"{subject} has no complete final design batch and disposition account")
    accepted = [item["id"] for item in dispositions if item.get("status") == "accepted"]
    if len(accepted) != resolution_data["accepted"]:
        fail(f"{subject}'s accepted Design count contradicts its exact account")
    handoff = {
        "schema": 1,
        "verdict": journal_line_proof(verdict_index),
        "resolution": journal_line_proof(resolution_index),
        "result": result_relative,
        "result_sha256": verdict_data["report_sha256"],
        "checker_result": result,
        "dispositions": dispositions,
    }
    return {"unresolved": False, "handoff": handoff, "accepted": accepted}


def final_code_failure_handoff(entries, before, lot, task, attempt, subject):
    if code_blockers(entries, before, lot, task, attempt):
        return None
    verdicts = [(index, entry) for index, entry in code_verdicts(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == CONSTRUCTION_CHECKER_ROUNDS["code"]]
    if not verdicts:
        return None
    if len(verdicts) != 1:
        fail(f"{subject} has more than one final code-checker verdict")
    verdict_index, verdict = verdicts[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings":
        return None
    resolutions = [(index, entry) for index, entry in code_resolutions(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == CONSTRUCTION_CHECKER_ROUNDS["code"]]
    if not resolutions:
        return {"unresolved": True}
    if len(resolutions) != 1 or resolutions[0][0] <= verdict_index:
        fail(f"{subject} has no one ordered final code-review resolution")
    resolution_index, resolution = resolutions[0]
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail(f"{subject}'s final resolution belongs to another checker verdict")
    if resolution_data.get("accepted") == 0:
        return None
    if not construction_positive_integer(resolution_data.get("accepted")):
        fail(f"{subject}'s final resolution has a malformed accepted count")
    result_relative = verdict_data.get("report")
    result_path = exact_real_file(
        WORKSPACE, result_relative, f"{subject}'s immutable final checker result",
    )
    try:
        with open(result_path, "rb") as source:
            result_payload = source.read()
        result = json.loads(result_payload)
    except (UnicodeError, ValueError) as exc:
        fail(f"{subject}'s immutable final checker result is malformed", exc)
    if sha256_bytes(result_payload) != verdict_data.get("report_sha256"):
        fail(f"{subject}'s immutable final checker result changed")
    findings = result.get("findings") if isinstance(result, dict) else None
    dispositions = resolution_data.get("items")
    if not isinstance(findings, list) or len(findings) != verdict_data.get("findings") \
            or not isinstance(dispositions, list) or len(dispositions) != len(findings):
        fail(f"{subject} has no complete final checker batch and disposition account")
    handoff = {
        "schema": 1,
        "verdict": journal_line_proof(verdict_index),
        "resolution": journal_line_proof(resolution_index),
        "result": result_relative,
        "result_sha256": verdict_data["report_sha256"],
        "checker_result": result,
        "dispositions": dispositions,
    }
    accepted = [item["id"] for item in dispositions if item.get("status") == "accepted"]
    if len(accepted) != resolution_data["accepted"]:
        fail(f"{subject}'s accepted disposition count contradicts its exact account")
    return {"unresolved": False, "handoff": handoff, "accepted": accepted}


def code_contract_failure_handoff(entries, before, lot, task, attempt, subject):
    blockers = code_blockers(entries, before, lot, task, attempt)
    if not blockers:
        return None
    if len(blockers) != 1:
        fail(f"{subject} has more than one code-review controller-contract blocker")
    blocker_index, blocker = blockers[0]
    blocker_data = note_data(blocker)
    round_number = blocker_data.get("round")
    matches = [(index, entry) for index, entry in code_verdicts(
        entries, blocker_index, lot, task, attempt,
    ) if note_data(entry).get("round") == round_number]
    if len(matches) != 1:
        fail(f"{subject}'s code-review blocker has no exact checker verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    result, findings = immutable_code_result(verdict_data, subject)
    items = blocker_data.get("items")
    if blocker_data.get("schema") == 2:
        expected = code_blocker_reclassification_account(
            entries, blocker_index, lot, task, attempt, round_number,
            blocker_data.get("contract_blocked"), subject,
            live=False, recorded=blocker_data,
        )
    else:
        expected = canonical_code_blocker(
            construction_frozen_logical(
                entries, blocker_index,
                {key: blocker_data[key]
                 for key in ("check", "lot", "task", "attempt", "round")},
                subject,
            ),
            verdict_index, verdict, items,
        )
    if blocker_data != expected:
        fail(f"{subject}'s code-review blocker changed", expected)
    obligation = {
        "schema": 1,
        "verdict": journal_line_proof(verdict_index),
        "blocked": journal_line_proof(blocker_index),
        "result": verdict_data["report"],
        "result_sha256": verdict_data["report_sha256"],
        "checker_result": result,
        "items": items,
        "required": [item["id"] for item in findings],
        "contract_blocked": blocker_data["contract_blocked"],
    }
    return {
        "unresolved": False,
        "blocked": True,
        "obligation": obligation,
        "required": obligation["required"],
        "contract_blocked": obligation["contract_blocked"],
    }


AMENDMENT_SUPERSESSION_TASK_KEYS = {
    "plan", "plan_sha256", "plan_projection_sha256", "plan_ownership_sha256",
    "contract_sha256", "design_sha256", "disagreement_sha256",
}

AMENDMENT_DEFERRED_PHASE = "deferred-post-amendment"


def canonical_digest(value):
    return sha256_bytes(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def amendment_attempt_settle_marker(subject, *, required=False):
    if not os.path.lexists(AMENDMENT_ATTEMPT_SETTLE_MARKER):
        if required:
            fail(f"{subject} has no retained settlement marker")
        return None
    path = exact_real_file(
        WORKSPACE, os.path.basename(AMENDMENT_ATTEMPT_SETTLE_MARKER), subject,
    )
    try:
        with open(path, encoding="utf-8") as source:
            marker = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"{subject} has a malformed settlement marker", exc)
    owner = marker.get("owner") if isinstance(marker, dict) else None
    if not isinstance(owner, dict) or set(marker) != {
        "schema", "operation", "phase", "owner", "owner_sha256",
    } or marker.get("schema") != 1 or marker.get("operation") != "amendment-attempt-settle" \
            or marker.get("phase") not in {
                "owned", "base-restored", "failure-recorded", "spec-restored",
                "diagnostic-closed", "implementer-retired", "terminal-recorded",
            } or marker.get("owner_sha256") != canonical_digest(owner):
        fail(f"{subject} has a malformed settlement owner")
    return marker


def amendment_deferred_prefix(entries, before, opening_index, sweep_index, subject):
    state = current_amendment_review(entries, before, subject)
    if state["opening_index"] != opening_index or state["last_return_index"] <= sweep_index:
        fail(f"{subject} has no exact post-sweep A4 fixer return")
    fixer_index = state["last_return_index"]
    forbidden = [entry for entry in entries[opening_index + 1:before]
                 if entry.get("kind") == "amendment.committed"
                 or entry.get("kind") == "verdict.consumed"
                 and note_data(entry).get("check") == "consolidation"
                 or entry.get("event") in {"subagent-started", "subagent-ended"}
                 and entry.get("kind") == "consolidation"
                 or entry.get("kind") == "bound.spent"
                 and str(entry.get("text", "")).startswith("consolidation round")]
    if forbidden:
        fail(f"{subject} is not the exact inverted pre-consolidation prefix")
    return state, fixer_index


def unresolved_checker_candidates(entries, before, lot, task, attempt, subject):
    candidates = []
    for checker, verdicts, resolutions, blockers, immutable_result in (
        ("design", design_verdicts, design_resolutions, design_blockers, immutable_design_result),
        ("code", code_verdicts, code_resolutions, code_blockers, immutable_code_result),
    ):
        for verdict_index, verdict in verdicts(entries, before, lot, task, attempt):
            verdict_data = note_data(verdict)
            if verdict_data.get("outcome") != "findings":
                continue
            round_number = verdict_data.get("round")
            settled = [entry for _, entry in resolutions(entries, before, lot, task, attempt)
                       if note_data(entry).get("round") == round_number]
            blocked = [entry for _, entry in blockers(entries, before, lot, task, attempt)
                       if note_data(entry).get("round") == round_number]
            if settled or blocked:
                continue
            _, findings = immutable_result(verdict_data, subject)
            candidates.append((checker, verdict_index, verdict, findings))
    return candidates


def amendment_deferred_failure_source(
        entries, before, lot, task, attempt, subject, *, current_before=None,
):
    current_before = before if current_before is None else current_before
    if current_before < before or current_before > len(entries):
        fail(f"{subject} has a malformed deferred checker source prefix")
    late_blockers = [
        (index, entry) for index, entry in (
            design_blockers(entries, current_before, lot, task, attempt)
            + code_blockers(entries, current_before, lot, task, attempt)
        ) if index >= before
    ]
    if late_blockers:
        fail(f"{subject}'s controller-owned blocker follows its Amendment opening")
    candidates = []
    for checker, verdict_index, verdict, findings in unresolved_checker_candidates(
        entries, before, lot, task, attempt, subject,
    ):
        verdict_data = note_data(verdict)
        logical = construction_frozen_logical(
            entries, verdict_index,
            {"check": checker, "lot": lot, "task": task, "attempt": attempt,
             "round": verdict_data.get("round")},
            subject,
        )
        candidates.append({
            "schema": 1,
            "type": "unresolved",
            "checker": checker,
            "verdict": journal_line_proof(verdict_index),
            "round": verdict_data["round"],
            "result": verdict_data["report"],
            "result_sha256": verdict_data["report_sha256"],
            "finding_ids": [item["id"] for item in findings],
            "logical": logical,
        })

    for checker, state in (
        ("design", design_failure_handoff(entries, before, lot, task, attempt, subject)),
        ("code", code_contract_failure_handoff(entries, before, lot, task, attempt, subject)),
    ):
        if state is None or not state.get("blocked"):
            continue
        obligation = state["obligation"]
        verdict_index, verdict = journal_entry_from_proof(
            entries, obligation["verdict"], subject,
        )
        blocker_index, blocker = journal_entry_from_proof(
            entries, obligation["blocked"], subject,
        )
        if blocker_index <= verdict_index or blocker_index >= before:
            fail(f"{subject}'s controller-owned blocker is outside its exact source prefix")
        blocker_data = note_data(blocker)
        logical = construction_frozen_logical(
            entries, blocker_index,
            {"check": checker, "lot": lot, "task": task, "attempt": attempt,
             "round": blocker_data.get("round")},
            subject,
        )
        candidates.append({
            "schema": 1,
            "type": "controller-blocker",
            "checker": checker,
            "verdict": obligation["verdict"],
            "blocker": obligation["blocked"],
            "round": blocker_data["round"],
            "result": obligation["result"],
            "result_sha256": obligation["result_sha256"],
            "finding_ids": [item["id"] for item in obligation["checker_result"]["findings"]],
            "required": state["required"],
            "contract_blocked": state["contract_blocked"],
            "logical": logical,
        })

    if len(candidates) != 1:
        fail(f"{subject} requires one exact deferred checker source", f"found {len(candidates)}")
    source = candidates[0]
    verdict_index, _verdict = journal_entry_from_proof(entries, source["verdict"], subject)
    if any(candidate.get("event") == "note" and candidate.get("kind") == "verdict.consumed"
           and note_data(candidate).get("check") in {"design", "code"}
           for candidate in entries[verdict_index + 1:before]):
        fail(f"{subject}'s deferred checker source is not the current construction verdict")
    return source


def amendment_supersession_failure_fields(failure_source, recorded):
    legacy = isinstance(recorded, dict) and "failure_source" not in recorded
    if not legacy:
        return {"failure_source": failure_source}
    if failure_source.get("type") != "unresolved" or set(failure_source) != {
        "schema", "type", "checker", "verdict", "round", "result",
        "result_sha256", "finding_ids", "logical",
    }:
        fail("a legacy AMENDMENT supersession cannot adopt a controller blocker")
    return {
        key: failure_source[key] for key in (
            "checker", "verdict", "round", "result", "result_sha256", "finding_ids",
        )
    }


def amendment_attempt_supersession_account(
        entries, before, lot, task, attempt, classification, subject, *, recorded=None,
):
    if classification != "C3.9b":
        fail(f"{subject}'s unresolved Design or code finding requires C3.9b")
    openings = amendment_openings(entries, before)
    if not openings:
        fail(f"{subject} has no current AMENDMENT authority")
    opening_index, opening = openings[-1]
    opening_data = note_data(opening)
    validate_amendment_opening_entry(entries, opening_index, opening)
    if opening_data.get("origin") != "construction" \
            or (opening_data.get("construction_source") or {}).get("lot") != lot:
        fail(f"{subject}'s AMENDMENT does not own this Construction lot")
    failure_source = amendment_deferred_failure_source(
        entries, opening_index, lot, task, attempt, subject, current_before=before,
    )
    failure_fields = amendment_supersession_failure_fields(failure_source, recorded)
    if any(entry.get("kind") == "amendment.committed"
           for entry in entries[opening_index + 1:before]):
        fail(f"{subject}'s AMENDMENT already committed before the attempt reset")
    sweeps = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1,
    ) if entry.get("kind") == "sweep.reported"]
    if not sweeps:
        fail(f"{subject}'s AMENDMENT has no accepted Reach result")
    sweep_index, sweep = sweeps[-1]
    _, _, sweep_data, audit = validate_sweep_entry(entries, sweep_index, sweep)
    if not reach_sweep_is_clean(audit):
        fail(f"{subject}'s AMENDMENT has no clean Reach close")

    logical = failure_source["logical"]
    previous_hashes = {
        key: logical.get(key) for key in (
            "plan_ownership_sha256", "contract_sha256", "design_sha256",
            "plan_projection_sha256", "disagreement_sha256",
        )
    }
    deferred = isinstance(recorded, dict) \
        and recorded.get("phase") == AMENDMENT_DEFERRED_PHASE
    marker = amendment_attempt_settle_marker(subject) if recorded is None else None
    if marker is not None:
        owner = marker["owner"]
        deferred = owner.get("lot") == lot and owner.get("task") == task \
            and owner.get("attempt") == attempt
    if deferred:
        _state, fixer_index = amendment_deferred_prefix(
            entries, before, opening_index, sweep_index, subject,
        )
        if recorded is None:
            previous = read_construction_plan_state(lot, task, subject)
            if any(previous.get(key) != value for key, value in previous_hashes.items()):
                fail(f"{subject}'s deferred route requires the unchanged frozen task")
            owner = marker["owner"]
            if owner.get("opening") != journal_line_proof(opening_index) \
                    or owner.get("sweep") != journal_line_proof(sweep_index) \
                    or owner.get("fixer") != journal_line_proof(fixer_index) \
                    or owner.get("failure_source") != failure_source:
                fail(f"{subject}'s settlement marker names another Amendment prefix")
            settlement_owner_sha256 = marker["owner_sha256"]
            consolidated_spec_sha256 = owner.get("consolidated_spec_sha256")
        else:
            previous = recorded.get("previous_task")
            if not isinstance(previous, dict) or set(previous) != AMENDMENT_SUPERSESSION_TASK_KEYS \
                    or previous.get("plan") != f"plans/{lot}-plan.md" \
                    or any(previous.get(key) != value for key, value in previous_hashes.items()):
                fail(f"{subject}'s durable deferred route changed its frozen prior task")
            settlement_owner_sha256 = recorded.get("settlement_owner_sha256")
            consolidated_spec_sha256 = recorded.get("consolidated_spec_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(settlement_owner_sha256)) \
                or not re.fullmatch(r"[0-9a-f]{64}", str(consolidated_spec_sha256)):
            fail(f"{subject}'s deferred settlement has malformed immutable authority")
        expected = {
            "schema": 1,
            "phase": AMENDMENT_DEFERRED_PHASE,
            "amendment": opening_data["amendment"],
            "opening": journal_line_proof(opening_index),
            "opening_sha256": opening_data["opening_sha256"],
            "sweep": sweep_data["sweep"],
            "sweep_proof": journal_line_proof(sweep_index),
            "fixer": journal_line_proof(fixer_index),
            "amendment_sha256": sweep_data["amendment_sha256"],
            **failure_fields,
            "previous_task": previous,
            "future_replacement_required": True,
            "consolidated_spec_sha256": consolidated_spec_sha256,
            "settlement_owner_sha256": settlement_owner_sha256,
        }
        if recorded is not None and recorded != expected:
            fail(f"{subject} changes its exact deferred AMENDMENT supersession", expected)
        return expected

    previous = previous_hashes
    if recorded is None:
        replacement = read_construction_plan_state(lot, task, subject)
    else:
        replacement = recorded.get("replacement_task") if isinstance(recorded, dict) else None
    if not isinstance(replacement, dict) or set(replacement) != AMENDMENT_SUPERSESSION_TASK_KEYS \
            or replacement.get("plan") != f"plans/{lot}-plan.md" \
            or any(not re.fullmatch(r"[0-9a-f]{64}", replacement.get(key) or "")
                   for key in ("plan_sha256", "plan_projection_sha256",
                               "plan_ownership_sha256", "contract_sha256", "design_sha256")) \
            or replacement.get("disagreement_sha256") is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", replacement["disagreement_sha256"]):
        fail(f"{subject} has no exact replacement task contract")
    if replacement["contract_sha256"] == previous["contract_sha256"] \
            or replacement["plan_ownership_sha256"] == previous["plan_ownership_sha256"]:
        fail(f"{subject}'s AMENDMENT did not replace the controller-owned task contract")
    if replacement["design_sha256"] != previous["design_sha256"] \
            or replacement["disagreement_sha256"] != previous["disagreement_sha256"]:
        fail(f"{subject}'s AMENDMENT route changed implementer-owned Design bytes")

    expected = {
        "schema": 1,
        "amendment": opening_data["amendment"],
        "opening": journal_line_proof(opening_index),
        "opening_sha256": opening_data["opening_sha256"],
        "sweep": sweep_data["sweep"],
        "sweep_proof": journal_line_proof(sweep_index),
        "amendment_sha256": sweep_data["amendment_sha256"],
        **failure_fields,
        "previous_task": previous,
        "replacement_task": replacement,
        "replacement_task_sha256": sha256_bytes(json.dumps(
            replacement, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")),
    }
    if recorded is not None and recorded != expected:
        fail(f"{subject} changes its exact AMENDMENT supersession account", expected)
    return expected


def active_amendment_plan_supersession(entries, before, lot, subject):
    candidates = []
    for index, entry in enumerate(entries[:before]):
        if entry.get("kind") != "attempt.failed" or entry.get("lot") != lot:
            continue
        data = note_data(entry)
        supersession = data.get("amendment_supersession")
        if not isinstance(supersession, dict):
            continue
        task = entry.get("task")
        attempt = data.get("attempt")
        later_terminal = any(
            candidate.get("lot") == lot and candidate.get("task") == task
            and candidate.get("kind") in {"attempt.failed", "attempt.succeeded", "paused", "aborted"}
            and construction_positive_integer(note_data(candidate).get("attempt"))
            and note_data(candidate)["attempt"] > attempt
            for candidate in entries[index + 1:before]
        )
        if not later_terminal:
            candidates.append((index, entry, supersession))
    if len(candidates) > 1:
        retained = []
        for position, candidate in enumerate(candidates):
            index = candidate[0]
            later_index = candidates[position + 1][0] if position + 1 < len(candidates) else before
            failure_proof = journal_line_proof(index)
            consumed_before_later_generation = any(
                entry.get("kind") == "plan.written" and entry.get("lot") == lot
                and note_data(entry).get("schema") == 2
                and (note_data(entry).get("amendment_supersession") or {}).get("failure")
                == failure_proof
                for entry in entries[index + 1:later_index]
            )
            if not consumed_before_later_generation:
                retained.append(candidate)
        candidates = retained
    if not candidates:
        return None
    if len(candidates) != 1:
        fail(f"{subject} has several active AMENDMENT plan supersessions")
    return candidates[0]


def normalized_committed_plan_state(lot, task, commit, subject):
    result = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "committed-plan-state",
         lot, str(task), commit],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(f"{subject} cannot authenticate its committed task contract",
             result.stderr or result.stdout)
    try:
        state = json.loads(result.stdout)
    except ValueError:
        fail(f"{subject}'s committed task-state helper returned malformed JSON")
    state["plan"] = f"plans/{lot}-plan.md"
    if set(state) != AMENDMENT_SUPERSESSION_TASK_KEYS \
            or any(not re.fullmatch(r"[0-9a-f]{64}", state.get(key) or "")
                   for key in ("plan_sha256", "plan_projection_sha256",
                               "plan_ownership_sha256", "contract_sha256", "design_sha256")) \
            or state.get("disagreement_sha256") is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", state["disagreement_sha256"]):
        fail(f"{subject}'s committed task-state helper returned a malformed account")
    return state


def deferred_amendment_c2_result_proof(
        entries, after, before, lot, subject, *, require_incomplete,
):
    terminals = [(index, entry) for index, entry in enumerate(
        entries[after + 1:before], after + 1,
    ) if entry.get("event") == "subagent-ended"
        and entry.get("kind") == "completeness" and entry.get("lot") == lot
        and isinstance(note_data(entry), dict)
        and note_data(entry).get("deferred_amendment_plan") is not None]
    usable = []
    for candidate_index, candidate in terminals:
        candidate_data = note_data(candidate)
        candidate_frozen = candidate_data["deferred_amendment_plan"]
        starts = [(start_index, start) for start_index, start in open_subagent_brackets(
            entries[:candidate_index]
        ) if start.get("kind") == "completeness" and start.get("lot") == lot
            and subagent_terminal_matches(start, candidate)]
        if len(starts) != 1:
            fail(f"{subject}'s deferred C2 result has no one exact physical opening")
        expected_frozen = deferred_amendment_c2_account(
            entries, starts[0][0], lot, subject,
            recorded=note_data(starts[0][1]).get("deferred_amendment_plan"),
        )
        normalized, outcome = deferred_amendment_c2_result_account(
            candidate_data, expected_frozen, subject, recorded=True,
        )
        if candidate_data != normalized:
            fail(f"{subject}'s deferred C2 result changes its canonical account")
        if outcome != "lost":
            usable.append((candidate_index, candidate, outcome))
    if len(usable) != 1:
        fail(f"{subject} has no one exact usable deferred C2 result")
    index, _terminal, outcome = usable[0]
    if require_incomplete and outcome != "incomplete":
        fail(f"{subject}'s C2 result does not authorize another plan generation")
    open_subagent_brackets(entries[:index + 1])
    return journal_line_proof(index)


def incomplete_completeness_proof(entries, after, before, lot, subject):
    terminals = [(index, entry) for index, entry in enumerate(
        entries[after + 1:before], after + 1,
    ) if entry.get("event") == "subagent-ended"
        and entry.get("kind") == "completeness" and entry.get("lot") == lot
        and "unusable" not in note_data(entry)]
    if not terminals:
        fail(f"{subject} has no C2 result authorizing a later plan successor")
    index, terminal = terminals[-1]
    data = note_data(terminal)
    if data.get("deferred_amendment_plan") is not None:
        return deferred_amendment_c2_result_proof(
            entries, after, before, lot, subject, require_incomplete=True,
        )
    required = {"decisions", "tasks", "deps", "constraints", "parent"}
    if set(data) not in (required, required | {"deferred_amendment_plan"}):
        fail(f"{subject}'s C2 successor proof is incomplete")
    complete_fraction = re.compile(r"([0-9]+)/\1")
    clean = all(complete_fraction.fullmatch(str(data[key])) for key in (
        "decisions", "tasks", "deps",
    )) and data["constraints"] == "ok" and data["parent"] in {"ok", "n/a"}
    if clean:
        fail(f"{subject}'s C2 result does not authorize another plan generation")
    starts = [candidate for candidate in entries[after + 1:index]
              if candidate.get("event") == "subagent-started"
              and candidate.get("kind") == "completeness"
              and candidate.get("lot") == lot
              and subagent_terminal_matches(candidate, terminal)]
    if len(starts) != 1:
        fail(f"{subject}'s C2 successor has no one exact physical checker opening")
    opening_account = note_data(starts[0]).get("deferred_amendment_plan")
    if opening_account is not None:
        start_index = entries.index(starts[0])
        expected_account = deferred_amendment_c2_account(
            entries, start_index, lot, subject, recorded=opening_account,
        )
        if data.get("deferred_amendment_plan") != expected_account:
            fail(f"{subject}'s C2 terminal changes its frozen deferred plan authority")
    open_subagent_brackets(entries[:index + 1])
    return journal_line_proof(index)


def deferred_amendment_c2_result_account(data, frozen, subject, *, recorded=False):
    if not isinstance(data, dict) or not isinstance(frozen, dict):
        fail(f"{subject} has malformed deferred C2 authority")
    supplied = dict(data)
    recorded_frozen = supplied.pop("deferred_amendment_plan", None)
    if recorded and recorded_frozen != frozen:
        fail(f"{subject} changes its frozen deferred plan generation")
    if supplied == {"unusable": "lost"}:
        return {"unusable": "lost", "deferred_amendment_plan": frozen}, "lost"
    required = {"decisions", "tasks", "deps", "constraints", "parent"}
    if set(supplied) != required:
        fail(f"{subject} has malformed deferred C2 result data")
    fraction = re.compile(r"(0|[1-9][0-9]*)/(0|[1-9][0-9]*)")
    complete = True
    for key in ("decisions", "tasks", "deps"):
        match = fraction.fullmatch(str(supplied[key]))
        if match is None or int(match.group(1)) > int(match.group(2)):
            fail(f"{subject} has a malformed canonical {key} fraction")
        complete = complete and match.group(1) == match.group(2)
    broken = re.compile(r"[1-9][0-9]* broken")
    if supplied["constraints"] != "ok" and not broken.fullmatch(str(supplied["constraints"])):
        fail(f"{subject} has a malformed constraints result")
    if supplied["parent"] not in {"ok", "n/a"} \
            and not broken.fullmatch(str(supplied["parent"])):
        fail(f"{subject} has a malformed parent result")
    complete = complete and supplied["constraints"] == "ok" \
        and supplied["parent"] in {"ok", "n/a"}
    normalized = {**supplied, "deferred_amendment_plan": frozen}
    return normalized, "clean" if complete else "incomplete"


def deferred_amendment_c2_generation_consumed(entries, before, lot, frozen, subject):
    usable = []
    for index, terminal in enumerate(entries[:before]):
        data = note_data(terminal)
        if terminal.get("event") != "subagent-ended" \
                or terminal.get("kind") != "completeness" or terminal.get("lot") != lot \
                or not isinstance(data, dict) \
                or data.get("deferred_amendment_plan") != frozen:
            continue
        starts = [(start_index, start) for start_index, start in open_subagent_brackets(
            entries[:index]
        ) if start.get("kind") == "completeness" and start.get("lot") == lot
            and subagent_terminal_matches(start, terminal)]
        if len(starts) != 1:
            fail(f"{subject} has no one exact deferred C2 opening")
        expected = deferred_amendment_c2_account(
            entries, starts[0][0], lot, subject,
            recorded=note_data(starts[0][1]).get("deferred_amendment_plan"),
        )
        normalized, outcome = deferred_amendment_c2_result_account(
            data, expected, subject, recorded=True,
        )
        if data != normalized:
            fail(f"{subject} changes its canonical deferred C2 terminal")
        if outcome != "lost":
            usable.append(journal_line_proof(index))
    if len(usable) > 1:
        fail(f"{subject} has duplicate usable deferred C2 terminals")
    return bool(usable)


def deferred_amendment_c2_account(entries, before, lot, subject, *, recorded=None):
    active = active_amendment_plan_supersession(entries, before, lot, subject)
    if active is None or active[2].get("phase") != AMENDMENT_DEFERRED_PHASE:
        return None
    failure_index, failure, supersession = active
    failure_proof = journal_line_proof(failure_index)
    settlements = [(index, entry) for index, entry in enumerate(
        entries[failure_index + 1:before], failure_index + 1,
    ) if entry.get("kind") == "amendment.attempt.settled"
        and note_data(entry).get("failure") == failure_proof]
    if len(settlements) != 1:
        fail(f"{subject} has no exact completed deferred attempt settlement")
    validate_amendment_attempt_settled_entry(entries, settlements[0][0], settlements[0][1])
    commits = [(index, entry) for index, entry in enumerate(
        entries[settlements[0][0] + 1:before], settlements[0][0] + 1,
    ) if entry.get("kind") == "amendment.committed"]
    if len(commits) != 1:
        fail(f"{subject} has no exact committed Amendment generation")
    commit_index, commit = commits[0]
    validate_amendment_commit_entry(entries, commit_index, commit)
    if note_data(commit).get("amendment") != supersession["amendment"]:
        fail(f"{subject} consumes another Amendment generation")
    prior = [entry for entry in entries[failure_index + 1:before]
             if entry.get("kind") == "plan.written" and entry.get("lot") == lot
             and note_data(entry).get("schema") == 2
             and note_data(entry).get("amendment_supersession", {}).get("failure")
             == failure_proof]
    if prior:
        return None
    task_state = read_construction_plan_state(lot, failure.get("task"), subject) \
        if recorded is None else recorded.get("task_state")
    if not isinstance(task_state, dict) or set(task_state) != AMENDMENT_SUPERSESSION_TASK_KEYS:
        fail(f"{subject} has no exact deferred task generation")
    previous = supersession["previous_task"]
    if task_state != previous:
        fail(f"{subject}'s deferred C2 does not read the exact unchanged prior task generation")
    expected = {
        "schema": 1,
        "failure": failure_proof,
        "settlement": journal_line_proof(settlements[0][0]),
        "amendment_commit": journal_line_proof(commit_index),
        "task": failure.get("task"),
        "task_state": task_state,
        "task_state_sha256": canonical_digest(task_state),
    }
    if recorded is not None and recorded != expected:
        fail(f"{subject} changes its exact deferred C2 plan authority", expected)
    return expected


def amendment_plan_publication_account(
        entries, before, lot, tasks, operation, subject, *, commit=None, live=False,
):
    if not isinstance(tasks, int) or isinstance(tasks, bool) or tasks < 1 \
            or not isinstance(operation, str) or not operation:
        fail(f"{subject} has malformed plan publication identity")
    active = active_amendment_plan_supersession(entries, before, lot, subject)
    if active is None:
        return {"tasks": tasks, "op": operation}
    failure_index, failure, supersession = active
    validate_attempt_failed_entry(entries, failure_index, failure)
    failure_proof = journal_line_proof(failure_index)
    task = failure.get("task")
    prior = [(index, entry) for index, entry in enumerate(
        entries[failure_index + 1:before], failure_index + 1,
    ) if entry.get("kind") == "plan.written" and entry.get("lot") == lot
        and note_data(entry).get("schema") == 2
        and note_data(entry).get("amendment_supersession", {}).get("failure") == failure_proof]
    if commit is None:
        state = read_construction_plan_state(lot, task, subject)
        commit_value = None
    else:
        if live:
            head = subprocess.run(
                ["git", "-C", project_root(), "rev-parse", "--verify", "HEAD^{commit}"],
                capture_output=True, text=True,
            )
            if head.returncode != 0 or head.stdout.strip() != commit:
                fail(f"{subject} is not the current committed plan generation")
        state = normalized_committed_plan_state(lot, task, commit, subject)
        target = f"docs/plans/{os.path.basename(WORKSPACE)}-{lot}-plan.md"
        payload = committed_regular_payload(commit, target, subject)
        if len(plan_task_manifest(payload, subject)) != tasks \
                or not commit_changes_only(commit, target):
            fail(f"{subject} changes another path or records another task manifest")
        commit_value = commit
    deferred = supersession.get("phase") == AMENDMENT_DEFERRED_PHASE
    amendment_commit_proof = None
    if deferred:
        commits = [(index, entry) for index, entry in enumerate(
            entries[failure_index + 1:before], failure_index + 1,
        ) if entry.get("kind") == "amendment.committed"]
        if len(commits) != 1:
            fail(f"{subject}'s deferred replacement requires one exact Amendment commit")
        amendment_commit_index, amendment_commit = commits[0]
        validate_amendment_commit_entry(entries, amendment_commit_index, amendment_commit)
        if note_data(amendment_commit).get("amendment") != supersession["amendment"]:
            fail(f"{subject}'s deferred replacement consumes another Amendment")
        amendment_commit_proof = journal_line_proof(amendment_commit_index)
        replacement = None
        if prior:
            root_publication = prior[0][1]
            root_state = normalized_committed_plan_state(
                lot, task, note_data(root_publication).get("commit"), subject,
            )
            root_digest = canonical_digest(root_state)
        else:
            root_digest = canonical_digest(state)
    else:
        replacement = supersession["replacement_task"]
        root_digest = supersession["replacement_task_sha256"]
    previous_publication = journal_line_proof(prior[-1][0]) if prior else None
    c2_proof = None
    if not prior:
        if deferred:
            c2_proof = deferred_amendment_c2_result_proof(
                entries, amendment_commit_index, before, lot, subject,
                require_incomplete=False,
            )
            c2_index, c2_terminal = journal_entry_from_proof(entries, c2_proof, subject)
            c2_account = note_data(c2_terminal).get("deferred_amendment_plan")
            previous = supersession["previous_task"]
            if not isinstance(c2_account, dict) or c2_account.get("task_state") != previous \
                    or c2_account.get("amendment_commit") != amendment_commit_proof:
                fail(f"{subject} does not consume C2 on the unchanged prior task generation")
            c2_openings = [(index, opening) for index, opening in open_subagent_brackets(
                entries[:c2_index]
            ) if opening.get("kind") == "completeness"
                and subagent_terminal_matches(opening, c2_terminal)]
            if len(c2_openings) != 1:
                fail(f"{subject} has no one exact deferred C2 physical opening")
            c2_opening_proof = journal_line_proof(c2_openings[0][0])
            if state["contract_sha256"] == previous["contract_sha256"] \
                    or state["plan_ownership_sha256"] == previous["plan_ownership_sha256"] \
                    or state["design_sha256"] != previous["design_sha256"] \
                    or state["disagreement_sha256"] != previous["disagreement_sha256"]:
                fail(f"{subject}'s first deferred successor violates its frozen task boundary")
        elif state != replacement:
            fail(f"{subject} changes the AMENDMENT replacement before its first publication")
    else:
        c2_proof = incomplete_completeness_proof(
            entries, prior[-1][0], before, lot, subject,
        )
        previous = supersession["previous_task"]
        if state["contract_sha256"] == previous["contract_sha256"] \
                or state["plan_ownership_sha256"] == previous["plan_ownership_sha256"] \
                or state["design_sha256"] != previous["design_sha256"] \
                or state["disagreement_sha256"] != previous["disagreement_sha256"]:
            fail(f"{subject}'s C2 successor loses the AMENDMENT replacement boundary")
    if commit is None:
        return {
            "failure": failure_proof,
            "previous_publication": previous_publication,
            "c2": c2_proof,
        }
    task_digest = sha256_bytes(json.dumps(
        state, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    publication_account = {
        "schema": 2,
        "tasks": tasks,
        "op": operation,
        "commit": commit_value,
        "plan_sha256": state["plan_sha256"],
        "amendment_supersession": {
            "failure": failure_proof,
            "root_replacement_task_sha256": root_digest,
            "previous_publication": previous_publication,
            "c2": c2_proof,
            "task": task,
            "task_state_sha256": task_digest,
        },
    }
    if deferred:
        publication_account["amendment_supersession"].update({
            "amendment_commit": amendment_commit_proof,
            "c2_opening": c2_opening_proof if not prior else None,
            "previous_task": supersession["previous_task"],
            "replacement_task": state,
            "replacement_task_sha256": canonical_digest(state),
        })
    return publication_account


def normalize_plan_written(entries, data, context, subject):
    if not isinstance(data, dict):
        fail(f"{subject} requires structured plan publication data")
    if data.get("schema") != 2:
        active = active_amendment_plan_supersession(
            entries, len(entries), context.get("lot"), subject,
        )
        if active is not None:
            fail(f"{subject} must publish the exact pending AMENDMENT replacement")
        if set(data) != {"tasks", "op"}:
            fail(f"{subject} has malformed legacy plan publication data")
        return data
    expected = amendment_plan_publication_account(
        entries, len(entries), context.get("lot"), data.get("tasks"), data.get("op"),
        subject, commit=data.get("commit"), live=True,
    )
    if data != expected:
        fail(f"{subject} changes its AMENDMENT plan publication account", expected)
    return expected


def validate_plan_written_entry(entries, index, entry):
    data = note_data(entry)
    if data.get("schema") != 2:
        if set(data) != {"tasks", "op"}:
            fail("a durable legacy plan publication is malformed")
        return
    expected = amendment_plan_publication_account(
        entries, index, entry.get("lot"), data.get("tasks"), data.get("op"),
        "a durable AMENDMENT plan publication", commit=data.get("commit"), live=False,
    )
    if data != expected:
        fail("a durable AMENDMENT plan publication changes its frozen account", expected)


def failure_report_state(
        entries, before, lot, task, attempt, classification, subject, *, allow_unresolved=False,
):
    design_state = design_failure_handoff(entries, before, lot, task, attempt, subject)
    code_state = final_code_failure_handoff(entries, before, lot, task, attempt, subject)
    code_blocked = code_contract_failure_handoff(entries, before, lot, task, attempt, subject)
    states = [state for state in (design_state, code_state, code_blocked) if state is not None]
    if len(states) > 1:
        fail(f"{subject} has conflicting checker failure obligations")
    state = states[0] if states else None
    if state is None:
        unresolved = unresolved_checker_candidates(
            entries, before, lot, task, attempt, subject,
        )
        if unresolved:
            if allow_unresolved:
                return {"unresolved": True}
            fail(f"{subject} cannot close unresolved checker findings")
        return None
    if state.get("unresolved"):
        if allow_unresolved:
            return {"unresolved": True}
        fail(f"{subject} cannot close unresolved checker findings")
    review = "design" if design_state is not None else "code"
    if review == "design" and state.get("blocked"):
        if classification not in {"C3.9b", "C3.9d"}:
            fail(f"{subject} must classify a final task-contract blocker as C3.9b or C3.9d")
        return {"design_review": compact_design_review_obligation(state)}
    if code_blocked is not None and state.get("blocked"):
        if classification not in {"C3.9b", "C3.9d"}:
            fail(f"{subject} must classify a code-review contract blocker as C3.9b or C3.9d")
        return {"code_review": compact_code_review_obligation(state)}
    if review == "design" and classification == "C3.9a":
        fail(f"{subject} cannot classify an accepted pre-implementation Design defect as C3.9a")
    relative = f"reports/construction/{lot}-task-{task}-try-{attempt}.md"
    path = exact_real_file(WORKSPACE, relative, f"{subject}'s failure report")
    try:
        with open(path, "rb") as source:
            payload = source.read()
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        fail(f"{subject}'s failure report is not UTF-8", exc)
    handoff_heading = f"## Final {review}-review handoff"
    headings = ["## What failed", "## Classification", "## Evidence read", handoff_heading]
    positions = [text.count(heading + "\n") for heading in headings]
    if positions != [1, 1, 1, 1] \
            or not all(text.index(headings[index]) < text.index(headings[index + 1])
                       for index in range(len(headings) - 1)):
        fail(f"{subject}'s accepted-defect report lacks its exact ordered four-part shape")
    classification_block = text.split("## Classification\n", 1)[1].split("\n## ", 1)[0]
    if not re.search(rf"(?m)^{re.escape(classification)}(?:\s|$)", classification_block):
        fail(f"{subject}'s failure report contradicts its C3.9 classification")
    match = re.search(
        rf"(?ms)^{re.escape(handoff_heading)}\n```json\n([^\n]+)\n```\s*$", text,
    )
    if not match:
        fail(f"{subject}'s failure report has no exact final {review}-review handoff block")
    try:
        embedded = json.loads(match.group(1))
    except ValueError as exc:
        fail(f"{subject}'s final code-review handoff is malformed JSON", exc)
    if embedded != state["handoff"]:
        fail(f"{subject}'s failure report omits or changes the final checker batch")
    return {
        "report": relative,
        "report_sha256": sha256_bytes(payload),
        f"{review}_review": {
            "verdict": state["handoff"]["verdict"],
            "resolution": state["handoff"]["resolution"],
            "result_sha256": state["handoff"]["result_sha256"],
            "accepted": state["accepted"],
        },
    }


def accepted_failure_from_proof(entries, proof, subject):
    index, entry = journal_entry_from_proof(entries, proof, subject)
    if entry.get("event") != "note" or entry.get("kind") != "attempt.failed":
        fail(f"{subject} does not identify a checker-obligation failure")
    data = note_data(entry)
    expected_report = failure_report_state(
        entries, index, entry.get("lot"), entry.get("task"), data.get("attempt"),
        data.get("classification"), subject,
    )
    expected = {
        "attempt": data.get("attempt"), "classification": data.get("classification"),
        **(expected_report or {}),
    }
    inherited = data.get("retry")
    if inherited is not None:
        accepted_retry_from_proof(entries, inherited, f"{subject}'s inherited retry obligation")
        expected["retry"] = inherited
    reviews = [name for name in ("design_review", "code_review")
               if isinstance(expected.get(name), dict)]
    if len(reviews) != 1 and not (not reviews and inherited is not None):
        fail(f"{subject} does not identify one checker correction obligation")
    if data != expected:
        fail(f"{subject}'s checker-obligation failure proof changed", expected)
    return index, entry, {
        key: expected[key] for key in (
            "report", "report_sha256", "design_review", "code_review", "retry",
        ) if key in expected
    }


def compact_design_review_obligation(state):
    if state.get("blocked"):
        obligation = state["obligation"]
        return {
            "verdict": obligation["verdict"],
            "blocked": obligation["blocked"],
            "result_sha256": obligation["result_sha256"],
            "required": state["required"],
            "contract_blocked": state["contract_blocked"],
        }
    handoff = state["handoff"]
    return {
        "verdict": handoff["verdict"],
        "resolution": handoff["resolution"],
        "result_sha256": handoff["result_sha256"],
        "accepted": state["accepted"],
    }


def compact_code_review_obligation(state):
    obligation = state["obligation"]
    return {
        "verdict": obligation["verdict"],
        "blocked": obligation["blocked"],
        "result_sha256": obligation["result_sha256"],
        "required": state["required"],
        "contract_blocked": state["contract_blocked"],
    }


def attempt_stop_design_state(entries, before, lot, task, attempt, subject):
    state = design_failure_handoff(
        entries, before, lot, task, attempt, subject,
    )
    if state is None or state.get("unresolved"):
        return None
    if not state.get("blocked") and not state.get("accepted"):
        return None
    return state


def attempt_stop_code_state(entries, before, lot, task, attempt, subject):
    return code_contract_failure_handoff(entries, before, lot, task, attempt, subject)


def expected_attempt_stop_data(entries, before, entry, subject, inherited_retry=None):
    data = note_data(entry)
    attempt_number = data.get("attempt")
    base = {"sha": data.get("sha"), "attempt": attempt_number}
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(base["sha"])) \
            or not construction_positive_integer(attempt_number) \
            or not isinstance(entry.get("lot"), str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", entry["lot"]) \
            or not construction_positive_integer(entry.get("task")):
        fail(f"{subject} has malformed construction identity")
    design_state = attempt_stop_design_state(
        entries, before, entry["lot"], entry["task"], attempt_number, subject,
    )
    code_state = attempt_stop_code_state(
        entries, before, entry["lot"], entry["task"], attempt_number, subject,
    )
    if design_state is not None and code_state is not None:
        fail(f"{subject} has conflicting checker obligations")
    expected = dict(base)
    if design_state is not None:
        expected["design_review"] = compact_design_review_obligation(design_state)
    if code_state is not None:
        expected["code_review"] = compact_code_review_obligation(code_state)
    retry = inherited_retry
    if retry is None:
        retry = outstanding_retry_proof(entries[:before], entry["lot"])
    if retry is not None:
        accepted_retry_from_proof(entries, retry, f"{subject}'s inherited retry obligation")
        expected["retry"] = retry
    return expected


def accepted_stop_from_proof(entries, proof, subject):
    index, entry = journal_entry_from_proof(entries, proof, subject)
    if entry.get("event") != "note" or entry.get("kind") not in {"paused", "aborted"}:
        fail(f"{subject} does not identify a stopped checker obligation")
    expected = expected_attempt_stop_data(entries, index, entry, subject)
    reviews = [name for name in ("design_review", "code_review")
               if isinstance(expected.get(name), dict)]
    if note_data(entry) != expected \
            or len(reviews) != 1 and not (not reviews and expected.get("retry") is not None):
        fail(f"{subject} does not identify one checker correction obligation")
    return index, entry, {
        key: expected[key] for key in ("design_review", "code_review", "retry")
        if key in expected
    }


def accepted_retry_from_proof(entries, proof, subject):
    _, entry = journal_entry_from_proof(entries, proof, subject)
    if entry.get("event") == "note" and entry.get("kind") == "attempt.failed":
        return accepted_failure_from_proof(entries, proof, subject)
    if entry.get("event") == "note" and entry.get("kind") in {"paused", "aborted"}:
        return accepted_stop_from_proof(entries, proof, subject)
    fail(f"{subject} does not identify a checker correction obligation")


def outstanding_retry_proof(entries, lot):
    terminals = [(index, entry) for index, entry in enumerate(entries)
                 if entry.get("event") == "note" and entry.get("lot") == lot
                 and entry.get("kind") in {
                     "attempt.failed", "attempt.succeeded", "paused", "aborted",
                 }]
    if not terminals:
        return None
    index, terminal = terminals[-1]
    data = note_data(terminal)
    if terminal.get("kind") == "attempt.succeeded":
        return None
    if terminal.get("kind") in {"paused", "aborted"}:
        expected = expected_attempt_stop_data(
            entries, index, terminal, "the durable stopped attempt",
        )
        if data != expected:
            fail("the durable stopped attempt changed its retry obligation", expected)
    if isinstance(data.get("code_review"), dict) or isinstance(data.get("design_review"), dict):
        proof = journal_line_proof(index)
        accepted_retry_from_proof(entries, proof, "the outstanding retry obligation")
        return proof
    retry = data.get("retry")
    if retry is not None:
        accepted_retry_from_proof(entries, retry, "the propagated retry obligation")
        return retry
    return None


def retry_obligation_chain(entries, proof, subject):
    proof_index, proof_entry, report = accepted_retry_from_proof(entries, proof, subject)
    inherited = report.get("retry")
    chain = retry_obligation_chain(
        entries, inherited, f"{subject}'s inherited obligation",
    ) if inherited is not None else []
    chain.append((proof, proof_index, proof_entry, report))
    return chain


def retry_code_member(entries, proof, proof_index, proof_entry, report, subject):
    compact = report["code_review"]
    if "blocked" in compact:
        state = code_contract_failure_handoff(
            entries, proof_index, proof_entry.get("lot"), proof_entry.get("task"),
            note_data(proof_entry).get("attempt"), subject,
        )
        if state is None or not state.get("blocked"):
            fail(f"{subject}'s retry proof has no code-review controller-contract blocker")
        obligation = state["obligation"]
        findings = [
            {key: item[key] for key in ("id", "where", "what", "why", "impact")}
            for item in obligation["checker_result"]["findings"]
        ]
        if all(set(item) == {"id", "status", "evidence"}
               for item in obligation["items"]):
            dispositions = obligation["items"]
        elif all(set(item) == {"id", "status"}
                 for item in obligation["items"]):
            dispositions = [{
                **item,
                "evidence": (
                    "The frozen task contract blocks this exact finding."
                    if item["status"] == "contract-blocked"
                    else "The recovered code blocker carries this exact finding."
                ),
            } for item in obligation["items"]]
        else:
            fail(f"{subject}'s code-review blocker has malformed retry dispositions")
        return {
            "source": "retry", "failure": proof,
            "result": obligation["result"],
            "result_sha256": obligation["result_sha256"],
            "findings": findings,
            "resolution": dispositions,
            "resolution_proof": obligation["blocked"],
        }
    if "report" not in report:
        fail(f"{subject} has no final code-review failure report")
    handoff_path = exact_real_file(WORKSPACE, report["report"], f"{subject}'s failure report")
    text = Path(handoff_path).read_text(encoding="utf-8")
    match = re.search(r"(?ms)^## Final code-review handoff\n```json\n([^\n]+)\n```\s*$", text)
    handoff = json.loads(match.group(1))
    accepted = set(report["code_review"]["accepted"])
    findings = [
        {key: item[key] for key in ("id", "where", "what", "why", "impact")}
        for item in handoff["checker_result"]["findings"] if item["id"] in accepted
    ]
    dispositions = [item for item in handoff["dispositions"] if item["id"] in accepted]
    return {
        "source": "retry", "failure": proof,
        "result": handoff["result"], "result_sha256": handoff["result_sha256"],
        "findings": findings, "resolution": dispositions,
        "resolution_proof": handoff["resolution"],
    }


def materialize_retry_batch(members, proof):
    if len(members) == 1:
        return {**members[0], "failure": proof}
    findings = []
    resolutions = []
    for member in members:
        for finding, resolution in zip(member["findings"], member["resolution"], strict=True):
            identity = len(findings) + 1
            findings.append({**finding, "id": identity})
            resolutions.append({**resolution, "id": identity})
    return {
        "source": "retry-set", "failure": proof,
        "members": members, "findings": findings, "resolution": resolutions,
    }


def retry_code_members(entries, proof, subject):
    return [
        retry_code_member(entries, member_proof, proof_index, proof_entry, report, subject)
        for member_proof, proof_index, proof_entry, report in retry_obligation_chain(
            entries, proof, subject,
        ) if "code_review" in report
    ]


def retry_code_batch(entries, proof, subject):
    members = retry_code_members(entries, proof, subject)
    if not members:
        fail(f"{subject} does not carry an accepted code obligation")
    return materialize_retry_batch(members, proof)


def retry_design_member(entries, proof, proof_index, proof_entry, report, subject):
    compact = report["design_review"]
    if "blocked" in compact:
        state = design_failure_handoff(
            entries, proof_index, proof_entry.get("lot"), proof_entry.get("task"),
            note_data(proof_entry).get("attempt"), subject,
        )
        if state is None or not state.get("blocked"):
            fail(f"{subject}'s retry proof has no Design controller-contract blocker")
        obligation = state["obligation"]
        blocked = set(state["contract_blocked"])
        findings = [
            {key: item[key] for key in ("id", "where", "what", "why", "impact")}
            for item in obligation["checker_result"]["findings"]
        ]
        dispositions = [{
            "id": item["id"],
            "status": "contract-blocked" if item["id"] in blocked else "carried",
            "evidence": (
                "The frozen task contract blocks this exact finding."
                if item["id"] in blocked
                else "The blocked Design generation carries this exact finding."
            ),
        } for item in findings]
        return {
            "source": "retry", "failure": proof,
            "result": obligation["result"],
            "result_sha256": obligation["result_sha256"],
            "findings": findings, "resolution": dispositions,
            "resolution_proof": obligation["blocked"],
        }
    if proof_entry.get("kind") == "attempt.failed":
        handoff_path = exact_real_file(WORKSPACE, report["report"], f"{subject}'s failure report")
        text = Path(handoff_path).read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^## Final design-review handoff\n```json\n([^\n]+)\n```\s*$", text,
        )
        if not match:
            fail(f"{subject}'s failure report has no exact Design handoff")
        handoff = json.loads(match.group(1))
    else:
        state = attempt_stop_design_state(
            entries, proof_index, proof_entry.get("lot"), proof_entry.get("task"),
            note_data(proof_entry).get("attempt"), subject,
        )
        if state is None:
            fail(f"{subject}'s stopped attempt has no accepted Design handoff")
        handoff = state["handoff"]
    accepted = set(compact["accepted"])
    findings = [
        {key: item[key] for key in ("id", "where", "what", "why", "impact")}
        for item in handoff["checker_result"]["findings"] if item["id"] in accepted
    ]
    dispositions = [item for item in handoff["dispositions"] if item["id"] in accepted]
    return {
        "source": "retry", "failure": proof,
        "result": handoff["result"], "result_sha256": handoff["result_sha256"],
        "findings": findings, "resolution": dispositions,
        "resolution_proof": handoff["resolution"],
    }


def retry_design_members(entries, proof, subject):
    return [
        retry_design_member(entries, member_proof, proof_index, proof_entry, report, subject)
        for member_proof, proof_index, proof_entry, report in retry_obligation_chain(
            entries, proof, subject,
        ) if "design_review" in report
    ]


def retry_design_batch(entries, proof, subject):
    members = retry_design_members(entries, proof, subject)
    if not members:
        fail(f"{subject} does not carry a final Design correction obligation")
    return materialize_retry_batch(members, proof)


def canonical_code_resolution(logical, verdict_index, verdict, items, disagreement_sha256=None):
    statuses = [item["status"] for item in items]
    result = {
        **logical,
        "verdict": journal_line_proof(verdict_index),
        "findings": note_data(verdict)["findings"],
        "items": items,
    }
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["code"]:
        return {
            **result,
            "corrected": statuses.count("corrected"),
            "unchanged": statuses.count("unchanged"),
        }
    return {
        **result,
        "accepted": statuses.count("accepted"),
        "refuted": statuses.count("refuted"),
        "alternative": statuses.count("alternative"),
        "disagreement_sha256": disagreement_sha256,
    }


def immutable_code_result(verdict_data, subject):
    result_relative = verdict_data.get("report")
    result_path = exact_real_file(WORKSPACE, result_relative, f"{subject}'s code-checker result")
    try:
        payload = Path(result_path).read_bytes()
        result = json.loads(payload)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"{subject}'s code-checker result is malformed", exc)
    if sha256_bytes(payload) != verdict_data.get("report_sha256"):
        fail(f"{subject}'s code-checker result changed")
    findings = result.get("findings") if isinstance(result, dict) else None
    expected_ids = list(range(1, verdict_data.get("findings", 0) + 1))
    if not isinstance(findings, list) or [
        item.get("id") for item in findings if isinstance(item, dict)
    ] != expected_ids or len(findings) != len(expected_ids):
        fail(f"{subject}'s code-checker result has no exact findings batch")
    return result, findings


def canonical_code_blocker(logical, verdict_index, verdict, items):
    verdict_data = note_data(verdict)
    statuses = [item["status"] for item in items]
    return {
        **logical,
        "verdict": journal_line_proof(verdict_index),
        "findings": verdict_data["findings"],
        "items": items,
        "result": verdict_data["report"],
        "result_sha256": verdict_data["report_sha256"],
        "required": [item["id"] for item in items],
        "contract_blocked": [
            item["id"] for item in items if item["status"] == "contract-blocked"
        ],
        "carried": [item["id"] for item in items if item["status"] == "carried"],
        "blocked": statuses.count("contract-blocked"),
    }


def code_blocker_reclassification_account(
        entries, before, lot, task, attempt, round_number, blocked_ids, subject,
        *, live, recorded=None,
):
    base = {
        "check": "code", "lot": lot, "task": task,
        "attempt": attempt, "round": round_number,
    }
    if not isinstance(lot, str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot) \
            or not all(construction_positive_integer(value)
                       for value in (task, attempt, round_number)) \
            or round_number >= CONSTRUCTION_CHECKER_ROUNDS["code"]:
        fail(f"{subject} has malformed code-review identity")
    logical = construction_frozen_logical(entries, before, base, subject)
    verdicts = [(index, entry) for index, entry in code_verdicts(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == round_number]
    resolutions = [(index, entry) for index, entry in code_resolutions(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == round_number]
    blockers = [(index, entry) for index, entry in code_blockers(
        entries, before, lot, task, attempt,
    ) if note_data(entry).get("round") == round_number]
    if len(verdicts) != 1 or len(resolutions) != 1 or blockers:
        fail(f"{subject} requires one settled code-review batch and no blocker")
    verdict_index, verdict = verdicts[0]
    resolution_index, resolution = resolutions[0]
    if resolution_index <= verdict_index:
        fail(f"{subject}'s settlement does not follow its checker verdict")
    validate_code_resolution_entry(entries, resolution_index, resolution)
    verdict_data = note_data(verdict)
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail(f"{subject}'s settlement belongs to another checker verdict")
    result, findings = immutable_code_result(verdict_data, subject)
    finding_ids = [item["id"] for item in findings]
    if not isinstance(blocked_ids, list) or not blocked_ids \
            or any(not construction_positive_integer(item) for item in blocked_ids) \
            or blocked_ids != sorted(set(blocked_ids)) \
            or any(item not in finding_ids for item in blocked_ids):
        fail(f"{subject} has no exact nonempty contract-blocked finding set")

    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if entry.get("event") == "session-started"
              and entry.get("mode") == "construction"
              and entry.get("job") == "implementer"
              and entry.get("lot") == lot and entry.get("task") == task
              and entry.get("attempt") == attempt]
    if len(starts) != 1:
        fail(f"{subject} has no one exact physical implementer start")
    start_index, start = starts[0]
    if start_index >= verdict_index:
        fail(f"{subject}'s implementer starts after its checker batch")
    validate_construction_session_start(
        start, subject, entries=entries, index=start_index,
    )
    start_account = start.get("data")
    if not isinstance(start_account, dict) or start_account.get("schema") != 2:
        fail(f"{subject} has no complete frozen implementer start account")
    if any(entry.get("event") == "session-retired"
           and entry.get("session") == start["session"] for entry in entries[:before]):
        fail(f"{subject} cannot replace a retired implementer's settlement")
    if any(construction_attempt_terminal(entry, lot, task, attempt)
           for entry in entries[:before]):
        fail(f"{subject} cannot replace a settlement after the attempt terminal")

    later_code_activity = [
        entry for entry in entries[resolution_index + 1:before]
        if entry.get("lot") == lot and entry.get("task") == task
        and entry.get("attempt") == attempt and (
            entry.get("event") in {"subagent-started", "subagent-ended"}
            and entry.get("kind") == "code-checker"
            or entry.get("event") == "note" and (
                entry.get("kind") in {
                    "verdict.consumed", "code.review.resolved", "code.review.blocked",
                } and note_data(entry).get("check") == "code"
                or entry.get("kind") == "bound.spent"
                and note_data(entry).get("check") == "code"
            )
        )
    ]
    if later_code_activity:
        fail(f"{subject} does not own the current code-review batch")
    if live:
        identity = active_attempt_identity(base, subject)
        if any(identity.get(key) != logical.get(key) for key in (
            "lot", "task", "attempt", "plan_manifest", "plan_tasks",
            "plan_ownership_sha256", "contract_sha256", "retry",
        )):
            fail(f"{subject} changes its active attempt identity")
        current = construction_plan_generation(logical, subject)
        if any(current.get(key) != logical.get(key) for key in current):
            fail(f"{subject} follows a changed controller contract or Design")

    items = [
        {"id": item, "status": "contract-blocked" if item in blocked_ids else "carried"}
        for item in finding_ids
    ]
    expected = {
        **canonical_code_blocker(logical, verdict_index, verdict, items),
        "schema": 2,
        "reclassification": {
            "schema": 1,
            "reason": "frozen-task-contract-omission",
            "resolution": journal_line_proof(resolution_index),
            "resolution_items": resolution_data["items"],
            "started": journal_line_proof(start_index),
            "session": start["session"],
            "start_account": start_account,
            "result": verdict_data["report"],
            "result_sha256": verdict_data["report_sha256"],
            "checker_result_sha256": canonical_digest(result),
        },
    }
    if recorded is not None and recorded != expected:
        fail(f"{subject} changes its exact settlement reclassification", expected)
    return expected


def code_blocker_reclassification_text(items):
    sections = []
    for item in items:
        if item["status"] == "contract-blocked":
            evidence = (
                "The frozen task contract omits work required by this checker finding."
            )
        else:
            evidence = (
                "The failed candidate is reset, so the replacement attempt must carry this finding."
            )
        sections.append(
            f"## Finding {item['id']} — {item['status']}\n{evidence}"
        )
    return "\n\n".join(sections) + "\n"


def canonical_design_resolution(
    logical, verdict_index, verdict, items, *, next_generation=None,
    disagreement_sha256=None,
):
    statuses = [item["status"] for item in items]
    result = {
        **logical,
        "verdict": journal_line_proof(verdict_index),
        "findings": note_data(verdict)["findings"],
        "items": items,
    }
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["design"]:
        return {
            **result,
            "corrected": statuses.count("corrected"),
            "unchanged": statuses.count("unchanged"),
            "next_design_sha256": next_generation["design_sha256"],
            "next_plan_projection_sha256": next_generation["plan_projection_sha256"],
        }
    return {
        **result,
        "accepted": statuses.count("accepted"),
        "refuted": statuses.count("refuted"),
        "alternative": statuses.count("alternative"),
        "disagreement_sha256": disagreement_sha256,
    }


def canonical_design_blocker(logical, verdict_index, verdict, findings):
    contract_blocked = [
        item["id"] for item in findings if item.get("where") == "frozen task contract"
    ]
    if not contract_blocked:
        fail("a Design blocker requires one exact frozen task contract finding")
    return {
        **logical,
        "verdict": journal_line_proof(verdict_index),
        "findings": note_data(verdict)["findings"],
        "result": note_data(verdict)["report"],
        "result_sha256": note_data(verdict)["report_sha256"],
        "contract_blocked": contract_blocked,
        "required": [item["id"] for item in findings],
    }


def normalize_design_blocker(entries, data, text, context, round_number):
    if data != {"check": "design"} or text is not None:
        fail("a Design blocker accepts only its derived design identity")
    validate_construction_verdict_history(entries)
    base = construction_logical_identity(
        entries, context, "design", round_number, "a Design blocker",
    )
    logical = construction_frozen_logical(
        entries, len(entries), base, "a Design blocker",
    )
    if any(note_data(entry).get("round") == logical["round"] for _, entry in design_resolutions(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )) or any(note_data(entry).get("round") == logical["round"] for _, entry in design_blockers(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this Design batch already has a terminal account")
    matches = [(index, entry) for index, entry in design_verdicts(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(entry).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a Design blocker has no exact current-round verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a Design blocker requires its exact findings verdict")
    _, findings = immutable_design_result(verdict_data, "the Design blocker")
    current = construction_plan_generation(base, "the Design blocker")
    for key in (
        "contract_sha256", "plan_ownership_sha256", "design_sha256",
        "plan_projection_sha256", "disagreement_sha256",
    ):
        if current.get(key) != logical.get(key):
            fail("a Design blocker follows a changed plan generation")
    return canonical_design_blocker(logical, verdict_index, verdict, findings)


def validate_design_blocker_entry(entries, index, entry):
    data = note_data(entry)
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt", "round")}
    if base["check"] != "design" or not isinstance(base["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", base["lot"]) \
            or not construction_positive_integer(base["task"]) \
            or not construction_positive_integer(base["attempt"]) \
            or not construction_positive_integer(base["round"]) \
            or base["round"] > CONSTRUCTION_CHECKER_ROUNDS["design"] \
            or any(entry.get(key) != base[key] for key in ("lot", "task", "attempt", "round")):
        fail("a durable Design blocker has malformed logical identity")
    logical = construction_frozen_logical(
        entries, index, base, "a durable Design blocker",
    )
    if design_resolutions(entries, index, logical["lot"], logical["task"], logical["attempt"]):
        final = [candidate for _, candidate in design_resolutions(
            entries, index, logical["lot"], logical["task"], logical["attempt"],
        ) if note_data(candidate).get("round") == logical["round"]]
        if final:
            fail("a Design batch has both settlement and blocker terminals")
    prior = [candidate for _, candidate in design_blockers(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(candidate).get("round") == logical["round"]]
    if prior:
        fail("a Design batch has more than one blocker terminal")
    matches = [(position, candidate) for position, candidate in design_verdicts(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(candidate).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a durable Design blocker has no exact checker verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a durable Design blocker does not follow exact findings")
    _, findings = immutable_design_result(verdict_data, "the durable Design blocker")
    expected = canonical_design_blocker(logical, verdict_index, verdict, findings)
    if data != expected or entry.get("text") is not None:
        fail("a durable Design blocker changes its immutable batch", expected)


def normalize_design_resolution(entries, data, text, context, round_number):
    if not isinstance(data, dict) or set(data) != {"check", "items"} \
            or data.get("check") != "design":
        fail("a design-review resolution has malformed structured data", data)
    validate_construction_verdict_history(entries)
    base = construction_logical_identity(
        entries, context, "design", round_number, "a design-review resolution",
    )
    logical = construction_frozen_logical(
        entries, len(entries), base, "a design-review resolution",
    )
    if any(note_data(entry).get("round") == logical["round"] for _, entry in design_resolutions(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this design-review round already has a resolution")
    if any(note_data(entry).get("round") == logical["round"] for _, entry in design_blockers(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this design-review round already has a controller-owned blocker terminal")
    matches = [(index, entry) for index, entry in design_verdicts(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(entry).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a design-review resolution has no exact round verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a design-review resolution requires its exact findings verdict")
    items = data.get("items")
    if not isinstance(items, list) or len(items) != verdict_data["findings"]:
        fail("a design-review resolution does not cover the exact findings count")
    allowed = DESIGN_FINAL_RESOLUTION_STATUSES \
        if logical["round"] == CONSTRUCTION_CHECKER_ROUNDS["design"] \
        else DESIGN_CORRECTION_STATUSES
    expected_ids = list(range(1, verdict_data["findings"] + 1))
    if any(not isinstance(item, dict) or set(item) != {"id", "status"}
           or item.get("status") not in allowed for item in items) \
            or [item.get("id") for item in items] != expected_ids:
        fail("a design-review resolution has malformed or non-contiguous items", items)
    detailed = code_resolution_text_items(text, "the design-review resolution", allowed)
    if [{key: item[key] for key in ("id", "status")} for item in detailed] != items:
        fail("the design-review resolution text contradicts its structured items")
    current = construction_plan_generation(base, "the design-review resolution")
    for key in ("contract_sha256", "plan_ownership_sha256"):
        if current[key] != logical[key]:
            fail("the design-review resolution changes controller-owned plan authority")
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["design"]:
        if current.get("disagreement_sha256") != logical.get("disagreement_sha256"):
            fail("an intermediate design correction changes Disagreement")
        return canonical_design_resolution(
            logical, verdict_index, verdict, detailed, next_generation=current,
        )
    if current["design_sha256"] != logical["design_sha256"] \
            or current["plan_projection_sha256"] != logical["plan_projection_sha256"]:
        fail("the final design settlement follows an unreviewed Design edit", {
            "frozen_design": logical["design_sha256"],
            "current_design": current["design_sha256"],
            "frozen_projection": logical["plan_projection_sha256"],
            "current_projection": current["plan_projection_sha256"],
        })
    if any(item["status"] == "accepted" for item in detailed):
        if current.get("disagreement_sha256") != logical.get("disagreement_sha256"):
            fail("an accepted final Design defect changed Disagreement before failure")
        disagreement_data = {"disagreement_sha256": current.get("disagreement_sha256")}
    else:
        alternative_ids = [
            item["id"] for item in detailed if item["status"] == "alternative"
        ]
        disagreement = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "design-disagreement", logical["lot"],
             str(logical["task"]), logical.get("disagreement_sha256") or "-",
             ",".join(map(str, alternative_ids)) or "-"],
            capture_output=True, text=True,
        )
        if disagreement.returncode != 0:
            fail("the final design-review settlement has no exact Disagreement projection",
                 disagreement.stderr or disagreement.stdout)
        try:
            disagreement_data = json.loads(disagreement.stdout)
        except ValueError:
            fail("the design Disagreement audit returned malformed JSON")
    return canonical_design_resolution(
        logical, verdict_index, verdict, detailed,
        disagreement_sha256=disagreement_data["disagreement_sha256"],
    )


def validate_design_resolution_entry(entries, index, entry):
    data = note_data(entry)
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt", "round")}
    if base["check"] != "design" or not isinstance(base["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", base["lot"]) \
            or not construction_positive_integer(base["task"]) \
            or not construction_positive_integer(base["attempt"]) \
            or not construction_positive_integer(base["round"]) \
            or base["round"] > CONSTRUCTION_CHECKER_ROUNDS["design"] \
            or any(entry.get(key) != base[key] for key in ("lot", "task", "attempt", "round")):
        fail("a durable design-review resolution has malformed logical identity")
    logical = construction_frozen_logical(
        entries, index, base, "a durable design-review resolution",
    )
    if any(note_data(candidate).get("round") == logical["round"] for _, candidate in design_resolutions(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("a design-review round has more than one durable resolution")
    if any(note_data(candidate).get("round") == logical["round"] for _, candidate in design_blockers(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("a design-review settlement follows a controller-owned blocker terminal")
    matches = [(position, candidate) for position, candidate in design_verdicts(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(candidate).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a durable design-review resolution has no exact checker verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a durable design-review resolution does not follow exact findings")
    items = data.get("items")
    allowed = DESIGN_FINAL_RESOLUTION_STATUSES \
        if logical["round"] == CONSTRUCTION_CHECKER_ROUNDS["design"] \
        else DESIGN_CORRECTION_STATUSES
    if not isinstance(items, list) or len(items) != verdict_data["findings"] \
            or code_resolution_text_items(
                entry.get("text"), "the durable design-review resolution", allowed,
            ) != items:
        fail("a durable design-review resolution has no complete item account")
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["design"]:
        next_generation = {
            "design_sha256": data.get("next_design_sha256"),
            "plan_projection_sha256": data.get("next_plan_projection_sha256"),
        }
        if any(not re.fullmatch(r"[0-9a-f]{64}", value or "")
               for value in next_generation.values()):
            fail("a durable design correction has malformed next-generation identity")
        expected = canonical_design_resolution(
            logical, verdict_index, verdict, items, next_generation=next_generation,
        )
    else:
        disagreement_sha256 = data.get("disagreement_sha256")
        if disagreement_sha256 is not None \
                and not re.fullmatch(r"[0-9a-f]{64}", disagreement_sha256):
            fail("a durable final design settlement has malformed Disagreement identity")
        has_accepted = any(item["status"] == "accepted" for item in items)
        has_alternative = any(item["status"] == "alternative" for item in items)
        if has_accepted:
            if disagreement_sha256 != logical.get("disagreement_sha256"):
                fail("an accepted durable Design settlement changed Disagreement")
        elif has_alternative and disagreement_sha256 is None \
                or not has_alternative and disagreement_sha256 != logical.get("disagreement_sha256"):
            fail("a durable final design settlement contradicts its Disagreement")
        expected = canonical_design_resolution(
            logical, verdict_index, verdict, items,
            disagreement_sha256=disagreement_sha256,
        )
    if data != expected:
        fail("a durable design-review resolution changes its proof or account", expected)


def normalize_code_resolution(entries, data, text, context, round_number):
    if not isinstance(data, dict) or set(data) != {"check", "items"} \
            or data.get("check") != "code":
        fail("a final code-review resolution has malformed structured data", data)
    validate_construction_verdict_history(entries)
    base = construction_logical_identity(
        entries, context, "code", round_number, "a final code-review resolution",
    )
    logical = construction_frozen_logical(
        entries, len(entries), base, "a final code-review resolution",
    )
    if any(note_data(entry).get("round") == logical["round"] for _, entry in code_resolutions(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this code-review round already has a resolution")
    if any(note_data(entry).get("round") == logical["round"] for _, entry in code_blockers(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this code-review round already has a controller-contract blocker")
    verdicts = code_verdicts(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )
    if not verdicts:
        fail("a final code-review resolution has no consumed checker verdict")
    matches = [(index, entry) for index, entry in verdicts
               if note_data(entry).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a code-review resolution has no exact round findings verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("round") != logical["round"] or verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a code-review resolution requires its exact findings verdict")
    items = data.get("items")
    if not isinstance(items, list) or len(items) != verdict_data["findings"]:
        fail("a final code-review resolution does not cover the exact findings count")
    expected_ids = list(range(1, verdict_data["findings"] + 1))
    allowed = CODE_FINAL_RESOLUTION_STATUSES \
        if logical["round"] == CONSTRUCTION_CHECKER_ROUNDS["code"] \
        else CODE_CORRECTION_STATUSES
    if any(not isinstance(item, dict) or set(item) != {"id", "status"}
           or item.get("status") not in allowed for item in items) \
            or [item.get("id") for item in items] != expected_ids:
        fail("a code-review resolution has malformed or non-contiguous items", items)
    detailed_items = code_resolution_text_items(text, "the code-review resolution", allowed)
    if [{key: item[key] for key in ("id", "status")} for item in detailed_items] != items:
        fail("the code-review resolution text contradicts its structured items")
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["code"]:
        return canonical_code_resolution(
            logical, verdict_index, verdict, detailed_items,
        )
    alternative_ids = [item["id"] for item in detailed_items if item["status"] == "alternative"]
    disagreement = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "disagreement", logical["lot"],
         str(logical["task"]), logical.get("disagreement_sha256") or "-",
         ",".join(map(str, alternative_ids)) or "-"],
        capture_output=True, text=True,
    )
    if disagreement.returncode != 0:
        fail("the final code-review resolution has no exact Disagreement projection",
             disagreement.stderr or disagreement.stdout)
    try:
        disagreement_data = json.loads(disagreement.stdout)
    except ValueError:
        fail("the Disagreement audit returned malformed JSON")
    return canonical_code_resolution(
        logical, verdict_index, verdict, detailed_items, disagreement_data["disagreement_sha256"],
    )


def validate_code_resolution_entry(entries, index, entry):
    data = note_data(entry)
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt", "round")}
    if base["check"] != "code" \
            or not isinstance(base["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", base["lot"]) \
            or not construction_positive_integer(base["task"]) \
            or not construction_positive_integer(base["attempt"]) \
            or not construction_positive_integer(base["round"]) \
            or base["round"] > CONSTRUCTION_CHECKER_ROUNDS["code"] \
            or any(entry.get(key) != base[key] for key in ("lot", "task", "attempt", "round")):
        fail("a durable final code-review resolution has malformed logical identity")
    logical = construction_frozen_logical(
        entries, index, base, "a durable final code-review resolution",
    )
    prior = code_resolutions(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )
    if any(note_data(candidate).get("round") == logical["round"] for _, candidate in prior):
        fail("a code-review round has more than one durable resolution")
    if any(note_data(candidate).get("round") == logical["round"] for _, candidate in code_blockers(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("a code-review settlement follows a controller-contract blocker")
    verdicts = code_verdicts(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )
    if not verdicts:
        fail("a durable final code-review resolution has no checker verdict")
    matches = [(position, candidate) for position, candidate in verdicts
               if note_data(candidate).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a durable code-review resolution has no exact checker verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("round") != logical["round"] or verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a durable code-review resolution does not follow its exact findings")
    items = data.get("items")
    allowed = CODE_FINAL_RESOLUTION_STATUSES \
        if logical["round"] == CONSTRUCTION_CHECKER_ROUNDS["code"] \
        else CODE_CORRECTION_STATUSES
    if not isinstance(items, list) or len(items) != verdict_data["findings"] \
            or code_resolution_text_items(
                entry.get("text"), "the durable code-review resolution", allowed,
            ) != items:
        fail("a durable code-review resolution has no complete matching item account")
    if logical["round"] < CONSTRUCTION_CHECKER_ROUNDS["code"]:
        expected = canonical_code_resolution(logical, verdict_index, verdict, items)
        if data != expected:
            fail("a durable code-review correction changes its checker proof or account", expected)
        return
    disagreement_sha256 = data.get("disagreement_sha256")
    if disagreement_sha256 is not None \
            and not re.fullmatch(r"[0-9a-f]{64}", disagreement_sha256):
        fail("a durable final code-review resolution has a malformed Disagreement identity")
    has_alternative = any(item["status"] == "alternative" for item in items)
    if has_alternative and disagreement_sha256 is None \
            or not has_alternative and disagreement_sha256 != logical.get("disagreement_sha256"):
        fail("a durable final code-review resolution contradicts its owned Disagreement")
    expected = canonical_code_resolution(
        logical, verdict_index, verdict, items, disagreement_sha256,
    )
    if data != expected:
        fail("a durable final code-review resolution changes its checker proof or counts", expected)


def normalize_code_blocker(entries, data, text, context, round_number):
    if not isinstance(data, dict) or set(data) != {"check", "items"} \
            or data.get("check") != "code":
        fail("a code-review controller-contract blocker has malformed structured data", data)
    validate_construction_verdict_history(entries)
    base = construction_logical_identity(
        entries, context, "code", round_number, "a code-review controller-contract blocker",
    )
    logical = construction_frozen_logical(
        entries, len(entries), base, "a code-review controller-contract blocker",
    )
    if code_blockers(entries, len(entries), logical["lot"], logical["task"], logical["attempt"]):
        fail("this attempt already has a code-review controller-contract blocker")
    if any(note_data(entry).get("round") == logical["round"] for _, entry in code_resolutions(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("this code-review batch already has a settlement")
    matches = [(index, entry) for index, entry in code_verdicts(
        entries, len(entries), logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(entry).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a code-review controller-contract blocker has no exact findings verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a code-review controller-contract blocker requires its exact findings verdict")
    supplied = data.get("items")
    expected_ids = list(range(1, verdict_data["findings"] + 1))
    if not isinstance(supplied, list) or len(supplied) != len(expected_ids) \
            or any(not isinstance(item, dict) or set(item) != {"id", "status"}
                   or item.get("status") not in CODE_BLOCKER_STATUSES for item in supplied) \
            or [item.get("id") for item in supplied] != expected_ids \
            or not any(item["status"] == "contract-blocked" for item in supplied):
        fail("a code-review blocker has no exact contract-blocked and carried account")
    detailed = code_resolution_text_items(
        text, "the code-review controller-contract blocker", CODE_BLOCKER_STATUSES,
    )
    if [{key: item[key] for key in ("id", "status")} for item in detailed] != supplied:
        fail("the code-review blocker text contradicts its structured items")
    current = construction_plan_generation(base, "the code-review controller-contract blocker")
    for key in (
        "contract_sha256", "plan_ownership_sha256", "design_sha256",
        "plan_projection_sha256", "disagreement_sha256",
    ):
        if current.get(key) != logical.get(key):
            fail("a code-review blocker follows a changed plan generation")
    immutable_code_result(verdict_data, "the code-review controller-contract blocker")
    return canonical_code_blocker(logical, verdict_index, verdict, detailed)


def validate_code_blocker_entry(entries, index, entry):
    data = note_data(entry)
    base = {key: data.get(key) for key in ("check", "lot", "task", "attempt", "round")}
    if base["check"] != "code" or not isinstance(base["lot"], str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", base["lot"]) \
            or not construction_positive_integer(base["task"]) \
            or not construction_positive_integer(base["attempt"]) \
            or not construction_positive_integer(base["round"]) \
            or base["round"] > CONSTRUCTION_CHECKER_ROUNDS["code"] \
            or any(entry.get(key) != base[key] for key in ("lot", "task", "attempt", "round")):
        fail("a durable code-review controller-contract blocker has malformed identity")
    logical = construction_frozen_logical(
        entries, index, base, "a durable code-review controller-contract blocker",
    )
    if data.get("schema") == 2:
        context = {key: entry[key] for key in CONTEXT_FIELDS if key in entry}
        expected_context = {
            "mode": "construction", "lot": base["lot"], "task": base["task"],
            "attempt": base["attempt"], "round": base["round"], "job": "controller",
        }
        if context != expected_context:
            fail("a durable reclassified code-review blocker changes its controller context")
        expected = code_blocker_reclassification_account(
            entries, index, base["lot"], base["task"], base["attempt"], base["round"],
            data.get("contract_blocked"),
            "a durable reclassified code-review controller-contract blocker",
            live=False, recorded=data,
        )
        if data != expected:
            fail("a durable reclassified code-review blocker changes its account", expected)
        return
    if code_blockers(entries, index, logical["lot"], logical["task"], logical["attempt"]):
        fail("an attempt has more than one durable code-review controller-contract blocker")
    if any(note_data(candidate).get("round") == logical["round"] for _, candidate in code_resolutions(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    )):
        fail("a code-review blocker follows a settlement for the same batch")
    matches = [(position, candidate) for position, candidate in code_verdicts(
        entries, index, logical["lot"], logical["task"], logical["attempt"],
    ) if note_data(candidate).get("round") == logical["round"]]
    if len(matches) != 1:
        fail("a durable code-review blocker has no exact findings verdict")
    verdict_index, verdict = matches[0]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") != "findings" \
            or not construction_positive_integer(verdict_data.get("findings")):
        fail("a durable code-review blocker does not follow exact findings")
    items = data.get("items")
    if not isinstance(items, list) or len(items) != verdict_data["findings"] \
            or code_resolution_text_items(
                entry.get("text"), "the durable code-review controller-contract blocker",
                CODE_BLOCKER_STATUSES,
            ) != items or not any(item["status"] == "contract-blocked" for item in items):
        fail("a durable code-review blocker has no complete matching item account")
    immutable_code_result(verdict_data, "the durable code-review controller-contract blocker")
    expected = canonical_code_blocker(logical, verdict_index, verdict, items)
    if data != expected:
        fail("a durable code-review blocker changes its immutable batch", expected)


def attempt_failure_account(
        entries, before, identity, classification, subject, *, recorded=None,
):
    base = {"attempt": identity["attempt"], "classification": classification}
    if classification not in CONSTRUCTION_CLASSIFICATIONS:
        fail(f"{subject} has an unknown C3.9 classification")
    report = failure_report_state(
        entries, before, identity["lot"], identity["task"], identity["attempt"],
        classification, subject, allow_unresolved=True,
    )
    blocked = isinstance(report, dict) and any(
        isinstance(report.get(key), dict) and "blocked" in report[key]
        for key in ("design_review", "code_review")
    )
    openings = amendment_openings(entries, before)
    active_construction_amendment = bool(openings) and (
        note_data(openings[-1][1]).get("origin") == "construction"
        and (note_data(openings[-1][1]).get("construction_source") or {}).get("lot")
        == identity["lot"]
        and not any(entry.get("kind") == "amendment.committed"
                    for entry in entries[openings[-1][0] + 1:before])
    )
    if report == {"unresolved": True} or blocked and active_construction_amendment:
        supersession = amendment_attempt_supersession_account(
            entries, before, identity["lot"], identity["task"], identity["attempt"],
            classification, subject,
            recorded=(recorded or {}).get("amendment_supersession"),
        )
        expected = {**base, "amendment_supersession": supersession}
    else:
        expected = {**base, **(report or {})}
    if identity.get("retry"):
        accepted_retry_from_proof(entries, identity["retry"], "the inherited retry obligation")
        expected["retry"] = identity["retry"]
    if recorded is not None and recorded != expected:
        fail("attempt.failed does not carry its exact checker obligation", expected)
    return expected


def normalize_attempt_failed(entries, data, context):
    if not isinstance(data, dict):
        fail("attempt.failed requires structured failure data")
    identity_context = {**context, "attempt": data.get("attempt")}
    identity = active_attempt_identity(
        identity_context, "the attempt failure", allow_closer=True,
    )
    return attempt_failure_account(
        entries, len(entries), identity, data.get("classification"),
        "the attempt failure", recorded=data,
    )


def validate_attempt_success_marker(marker, subject):
    owner = marker.get("owner") if isinstance(marker, dict) else None
    if not isinstance(owner, dict) or set(marker) != {
        "schema", "operation", "phase", "owner", "owner_sha256",
    } or marker.get("schema") != 1 or marker.get("operation") != "attempt-success" \
            or marker.get("phase") not in {
                "owned", "ref-writing", "ref-published", "terminal-writing",
                "terminal-recorded",
            } or marker.get("owner_sha256") != canonical_digest(owner):
        fail(f"{subject} has a malformed success owner")
    return marker


def attempt_success_marker(subject, *, required=False):
    if not os.path.lexists(ATTEMPT_SUCCESS_MARKER):
        if required:
            fail(f"{subject} has no retained success owner")
        return None
    path = exact_real_file(
        WORKSPACE, os.path.basename(ATTEMPT_SUCCESS_MARKER), subject,
    )
    try:
        with open(path, encoding="utf-8") as source:
            marker = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"{subject} has a malformed success owner", exc)
    return validate_attempt_success_marker(marker, subject)


def historical_final_code_proof(entries, proof, lot, task, attempt_number, tree, subject):
    proof_index, _ = journal_entry_from_proof(entries, proof, subject)
    prefix = entries[:proof_index + 1]
    verdicts = code_verdicts(prefix, len(prefix), lot, task, attempt_number)
    if not verdicts:
        fail(f"{subject} has no proved code-checker verdict")
    verdict_index, verdict = verdicts[-1]
    validate_construction_verdict_entry(prefix, verdict_index, verdict)
    verdict_data = note_data(verdict)
    manifest = verdict_data.get("manifest", "")
    disagreement = "-"
    expected_proof = journal_line_proof(verdict_index)
    if verdict_data.get("outcome") != "clean":
        if verdict_data.get("round") != CONSTRUCTION_CHECKER_ROUNDS["code"]:
            fail(f"{subject} consumes unfinished code findings")
        resolutions = [(index, entry) for index, entry in code_resolutions(
            prefix, len(prefix), lot, task, attempt_number,
        ) if note_data(entry).get("round") == verdict_data.get("round")]
        if len(resolutions) != 1:
            fail(f"{subject} has no exact final code resolution")
        resolution_index, resolution = resolutions[0]
        validate_code_resolution_entry(prefix, resolution_index, resolution)
        resolution_data = note_data(resolution)
        if resolution_data.get("verdict") != journal_line_proof(verdict_index) \
                or resolution_data.get("accepted") != 0:
            fail(f"{subject} has no accepted final code resolution")
        expected_proof = journal_line_proof(resolution_index)
        manifest = resolution_data.get("manifest", "")
        disagreement = resolution_data.get("disagreement_sha256") or "-"
    if proof != expected_proof:
        fail(f"{subject} names another final code proof")
    final = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "historical-final-tree",
         manifest, tree, disagreement],
        capture_output=True, text=True,
    )
    if final.returncode != 0:
        fail(f"{subject} does not bind its reviewed candidate", final.stderr or final.stdout)
    return proof


def attempt_success_gate_account(entries, before, lot, task, attempt_number, commit, operation,
                                 subject):
    active = None
    completed = []
    identity_keys = {
        "op", "scope", "owner", "lot", "task", "attempt", "head", "base",
        "tree", "gate", "code",
    }
    for index, entry in enumerate(entries[:before]):
        if entry.get("kind") != "gate-runner" or note_data(entry).get("op") != operation:
            continue
        data = note_data(entry)
        keys = identity_keys | ({"execution"} if "execution" in data else set())
        if entry.get("event") == "subagent-started":
            if active is not None or set(data) != keys:
                fail(f"{subject}'s final gate has overlapping or malformed openings")
            active = (index, data, keys)
            continue
        if entry.get("event") != "subagent-ended" or active is None:
            fail(f"{subject}'s final gate has a terminal without its opening")
        opening_index, opening_data, opening_keys = active
        if keys != opening_keys or any(data.get(key) != opening_data.get(key)
                                       for key in opening_keys):
            fail(f"{subject}'s final gate terminal changes its opening identity")
        active = None
        if "unusable" not in data:
            completed.append((opening_index, index, data))
    if active is not None or len(completed) != 1:
        fail(f"{subject} has no one complete physical final gate")
    opening_index, terminal_index, data = completed[0]
    expected_keys = identity_keys | {
        "green", "surface", "report", "report_sha256", "commands",
    } | ({"execution"} if "execution" in data else set())
    if set(data) != expected_keys or data.get("scope") != "task" \
            or (data.get("lot"), data.get("task"), data.get("attempt")) != (
                lot, task, attempt_number,
            ) or data.get("op") != operation or data.get("green") is not True \
            or data.get("surface") != "unchanged":
        fail(f"{subject}'s final gate changes its accepted task identity", data)
    _commit, tree = git_commit_and_tree(commit, subject)
    if data.get("tree") != tree:
        fail(f"{subject}'s final gate checked another task tree")
    historical_final_code_proof(
        entries, data.get("code"), lot, task, attempt_number, tree,
        f"{subject}'s final gate",
    )
    report = exact_real_file(WORKSPACE, data.get("report"), f"{subject}'s final gate report")
    with open(report, "rb") as source:
        report_bytes = source.read()
    if sha256_bytes(report_bytes) != data.get("report_sha256"):
        fail(f"{subject}'s final gate report changed")
    audit = subprocess.run(
        [sys.executable, GATE_REPORT, operation, data.get("gate"), tree,
         data.get("execution", "-")], capture_output=True, text=True,
    )
    try:
        audited = json.loads(audit.stdout) if audit.returncode == 0 else None
    except ValueError:
        audited = None
    if not isinstance(audited, dict) or any(data.get(key) != value
                                            for key, value in audited.items()):
        fail(f"{subject}'s final gate has no canonical physical report",
             audit.stderr or audit.stdout)
    return {
        "opening": journal_line_proof(opening_index),
        "terminal": journal_line_proof(terminal_index),
        "terminal_data": data,
    }


def attempt_success_commit_account(lot, task, commit, start_account, subject, *, live):
    start_identity = start_account["attempt_identity"]
    base = start_account["attempt_base"]
    resolved, tree = git_commit_and_tree(commit, subject)
    ancestry = subprocess.run(
        ["git", "-C", REPO, "merge-base", "--is-ancestor", base, resolved],
        capture_output=True, text=True,
    )
    count = subprocess.run(
        ["git", "-C", REPO, "rev-list", "--count", f"{base}..{resolved}"],
        capture_output=True, text=True,
    )
    if ancestry.returncode != 0 or count.returncode != 0 or count.stdout.strip() != "1":
        fail(f"{subject}'s task is not one exact commit above its attempt base")
    plan_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-{lot}-plan.md"
    committed = subprocess.run(
        ["git", "-C", REPO, "show", f"{resolved}:{plan_relative}"], capture_output=True,
    )
    changed = subprocess.run(
        ["git", "-C", REPO, "diff-tree", "--no-commit-id", "--name-only", "-r",
         resolved, "--", plan_relative], capture_output=True, text=True,
    )
    if committed.returncode != 0 or changed.returncode != 0 or not changed.stdout.strip():
        fail(f"{subject}'s task commit has no refreshed plan copy")
    headings = plan_task_manifest(committed.stdout, f"{subject}'s committed plan")
    manifest = subprocess.run(
        ["git", "-C", REPO, "hash-object", "--stdin"],
        input=("\n".join(headings) + "\n").encode(), capture_output=True,
    )
    if manifest.returncode != 0 or len(headings) != start_identity["plan_tasks"] \
            or manifest.stdout.decode().strip() != start_identity["plan_manifest"]:
        fail(f"{subject}'s committed task manifest changed from its frozen start")
    committed_state = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "committed-plan-state", lot, str(task), resolved],
        capture_output=True, text=True,
    )
    try:
        committed_account = json.loads(committed_state.stdout)
    except ValueError:
        committed_account = None
    if committed_state.returncode != 0 or not isinstance(committed_account, dict) \
            or committed_account.get("contract_sha256") != start_identity["contract_sha256"] \
            or committed_account.get("plan_ownership_sha256") \
            != start_identity["plan_ownership_sha256"]:
        fail(f"{subject}'s committed plan changes its frozen controller authority",
             committed_state.stderr or committed_state.stdout)
    if live:
        head, head_tree = git_commit_and_tree("HEAD", subject)
        status = subprocess.run(
            ["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True,
        )
        workspace_plan = exact_real_file(
            WORKSPACE, f"plans/{lot}-plan.md", f"{subject}'s workspace plan",
        )
        with open(workspace_plan, "rb") as source:
            workspace_bytes = source.read()
        current_account = read_construction_plan_state(lot, task, subject)
        if head != resolved or head_tree != tree or status.returncode != 0 or status.stdout \
                or workspace_bytes != committed.stdout \
                or current_account.get("contract_sha256") != start_identity["contract_sha256"] \
                or current_account.get("plan_ownership_sha256") \
                != start_identity["plan_ownership_sha256"]:
            fail(f"{subject} no longer owns the exact clean accepted task candidate")
    return {"base": base, "commit": resolved, "tree": tree, "plan": plan_relative}


def attempt_success_legacy_session_account(start, subject, *, live, recorded):
    """Freeze the provider identity missing from historical schema-1 starts.

    Live admission authenticates the provider session once. Historical replay
    can then authenticate only this durable snapshot and the exact start proof;
    the provider is not a historical event store.
    """
    expected_context = {
        key: start.get(key) for key in CONTEXT_FIELDS if start.get(key) is not None
    }
    if live:
        target = run(["session", start["session"]])
        target_id = target.get("id") or target.get("session_id")
        current_context = context_of(target)
        if target_id != start["session"] or current_context != expected_context:
            fail(f"{subject} has no exact live legacy implementer session")
        return {"session": start["session"], "context": current_context}
    if not isinstance(recorded, dict) or set(recorded) != {"session", "context"} \
            or recorded.get("session") != start["session"] \
            or recorded.get("context") != expected_context:
        fail(f"{subject} changes its frozen legacy implementer session")
    return recorded


def attempt_success_recovery_account(entries, before, lot, task, attempt_number, commit,
                                     operation, subject, *, live=False, recorded=None):
    if not isinstance(lot, str) or not re.fullmatch(
        r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot,
    ) or not construction_positive_integer(task) or not construction_positive_integer(
        attempt_number,
    ) or not re.fullmatch(r"[0-9a-f]{40,64}", str(commit)) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(operation)):
        fail(f"{subject} has malformed task success identity")
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if entry.get("event") == "session-started"
              and entry.get("mode") == "construction"
              and entry.get("job") == "implementer"
              and entry.get("lot") == lot and entry.get("task") == task
              and entry.get("attempt") == attempt_number]
    if len(starts) != 1:
        fail(f"{subject} has no one exact physical implementer start")
    start_index, start = starts[0]
    validate_construction_session_start(
        start, subject, entries=entries, index=start_index,
    )
    start_account = start.get("data")
    if not isinstance(start_account, dict):
        fail(f"{subject} has no complete frozen implementer start account")
    recorded_session = recorded.get("session_authority") \
        if isinstance(recorded, dict) else None
    session_authority = None
    if start_account.get("schema") == 1:
        session_authority = attempt_success_legacy_session_account(
            start, subject, live=live, recorded=recorded_session,
        )
    if any(construction_attempt_terminal(entry, lot, task, attempt_number)
           for entry in entries[:before]):
        fail(f"{subject} cannot replace an attempt terminal")
    if any(entry.get("event") == "session-retired" and entry.get("session") == start["session"]
           for entry in entries[:before]):
        fail(f"{subject} cannot recover a retired implementer")
    retry = start_account["attempt_identity"].get("retry")
    if retry is not None:
        accepted_retry_from_proof(entries, retry, f"{subject}'s retry authority")
    commit_account = attempt_success_commit_account(
        lot, task, commit, start_account, subject, live=live,
    )
    gate_account = attempt_success_gate_account(
        entries, before, lot, task, attempt_number, commit, operation, subject,
    )
    stable_ref = f"refs/bwr/{Path(WORKSPACE).name}/{lot}/task-{task}"
    expected = {
        "schema": 1,
        "session": start["session"],
        "session_authority": session_authority,
        "started": journal_line_proof(start_index),
        "start_account": start_account,
        "stable_ref": stable_ref,
        "commit": commit_account["commit"],
        "commit_account": commit_account,
        "gate": operation,
        "gate_account": gate_account,
        "retry": retry,
    }
    if recorded is not None and recorded != expected:
        fail(f"{subject} changes its exact success recovery account", expected)
    return expected


def attempt_success_terminal_account(entries, before, owner, subject, *, live=False):
    if not isinstance(owner, dict):
        fail(f"{subject} has no complete retained success owner")
    expected = attempt_success_recovery_account(
        entries, before, owner.get("start_account", {}).get("attempt_identity", {}).get("lot"),
        owner.get("start_account", {}).get("attempt_identity", {}).get("task"),
        owner.get("start_account", {}).get("attempt_identity", {}).get("attempt"),
        owner.get("commit"), owner.get("gate"), subject, live=live, recorded=owner,
    )
    return {**expected, "owner_sha256": canonical_digest(expected)}


def normalize_attempt_succeeded(entries, data, context):
    if not isinstance(data, dict):
        fail("attempt.succeeded requires structured success data")
    identity_context = {**context, "attempt": data.get("attempt")}
    identity = active_attempt_identity(identity_context, "the attempt success")
    expected = {
        "attempt": identity["attempt"], "lot": identity["lot"],
        "sha": data.get("sha"), "gate": data.get("gate"),
    }
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(expected["sha"])) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected["gate"])):
        fail("attempt.succeeded has malformed commit or gate identity")
    if identity.get("retry"):
        accepted_retry_from_proof(entries, identity["retry"], "the successful retry obligation")
        expected["retry"] = identity["retry"]
    if data != expected:
        fail("attempt.succeeded changes or drops its exact retry obligation", expected)
    candidate = {"event": "note", "kind": "attempt.succeeded", "lot": identity["lot"],
                 "task": identity["task"], "data": expected}
    validate_attempt_succeeded_entry(entries + [candidate], len(entries), candidate)
    return expected


def normalize_attempt_stop(entries, kind, data, context):
    if not isinstance(data, dict):
        fail(f"{kind} requires structured stop data")
    identity_context = {**context, "attempt": data.get("attempt")}
    identity = active_attempt_identity(
        identity_context, f"the {kind} attempt stop", allow_closer=True,
    )
    base = {"sha": data.get("sha"), "attempt": identity["attempt"]}
    if data != base:
        fail(f"{kind} accepts only its stop SHA and attempt number")
    candidate = {
        "event": "note", "kind": kind, "lot": identity["lot"],
        "task": identity["task"], "data": base,
    }
    return expected_attempt_stop_data(
        entries, len(entries), candidate, f"the {kind} attempt stop",
        inherited_retry=identity.get("retry"),
    )


def validate_attempt_failed_entry(entries, index, entry):
    data = note_data(entry)
    attempt_number, classification = data.get("attempt"), data.get("classification")
    if not construction_positive_integer(attempt_number) \
            or classification not in CONSTRUCTION_CLASSIFICATIONS \
            or not isinstance(entry.get("lot"), str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", entry["lot"]) \
            or not construction_positive_integer(entry.get("task")):
        fail("a durable attempt.failed has malformed construction identity")
    identity = {
        "lot": entry["lot"], "task": entry["task"], "attempt": attempt_number,
        "retry": data.get("retry"),
    }
    attempt_failure_account(
        entries, index, identity, classification,
        "the durable attempt failure", recorded=data,
    )


AMENDMENT_SETTLE_OWNER_KEYS = {
    "schema", "amendment", "opening", "sweep", "fixer", "lot", "task", "attempt",
    "attempt_identity", "attempt_base", "attempt_base_tree", "spec_path",
    "base_spec_sha256", "consolidated_spec_sha256", "recovery", "session", "started",
    "failure_source",
}


def validate_amendment_attempt_settle_owner(entries, before, owner, subject):
    if not isinstance(owner, dict) or set(owner) != AMENDMENT_SETTLE_OWNER_KEYS \
            or owner.get("schema") != 1 \
            or not construction_positive_integer(owner.get("amendment")) \
            or not construction_positive_integer(owner.get("task")) \
            or not construction_positive_integer(owner.get("attempt")) \
            or not isinstance(owner.get("lot"), str) \
            or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", owner["lot"]) \
            or not isinstance(owner.get("spec_path"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(owner.get("base_spec_sha256"))) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(owner.get("consolidated_spec_sha256"))) \
            or owner.get("recovery") != (
                "recovery/amendment-attempt-settle/"
                f"{owner.get('consolidated_spec_sha256')}.spec"
            ):
        fail(f"{subject} has a malformed settlement owner")
    opening_index, opening = journal_entry_from_proof(entries, owner["opening"], subject)
    sweep_index, sweep = journal_entry_from_proof(entries, owner["sweep"], subject)
    fixer_index, fixer = journal_entry_from_proof(entries, owner["fixer"], subject)
    if not opening_index < sweep_index < fixer_index < before \
            or opening.get("kind") != "amendment.opened" \
            or note_data(opening).get("amendment") != owner["amendment"] \
            or note_data(opening).get("origin") != "construction" \
            or (note_data(opening).get("construction_source") or {}).get("lot") != owner["lot"] \
            or sweep.get("kind") != "sweep.reported" \
            or fixer.get("kind") != "fixer.returned":
        fail(f"{subject} does not bind its ordered Amendment prefix")
    validate_amendment_opening_entry(entries, opening_index, opening)
    expected_source = amendment_deferred_failure_source(
        entries, opening_index, owner["lot"], owner["task"], owner["attempt"], subject,
        current_before=before,
    )
    if owner.get("failure_source") != expected_source:
        fail(f"{subject} changes its exact deferred checker source")
    _, _, _, audit = validate_sweep_entry(entries, sweep_index, sweep)
    if not reach_sweep_is_clean(audit):
        fail(f"{subject} does not bind one clean final Reach close")
    _state, exact_fixer_index = amendment_deferred_prefix(
        entries, before, opening_index, sweep_index, subject,
    )
    if exact_fixer_index != fixer_index:
        fail(f"{subject} does not bind the exact final A4 fixer return")
    starts = [(index, entry) for index, entry in enumerate(entries[:before])
              if entry.get("event") == "session-started"
              and entry.get("session") == owner.get("session")]
    if len(starts) != 1 or journal_line_proof(starts[0][0]) != owner.get("started"):
        fail(f"{subject} has no one exact implementer opening")
    start_index, start = starts[0]
    context = validate_construction_session_start(
        start, subject, entries=entries, index=start_index,
    )
    start_data = start.get("data")
    if context != {key: owner[key] for key in ("lot", "task", "attempt")} \
            or start_data is not None and (
                start_data.get("attempt_identity") != owner.get("attempt_identity")
                or start_data.get("attempt_base") != owner.get("attempt_base")
                or start_data.get("attempt_base_tree") != owner.get("attempt_base_tree")
            ):
        fail(f"{subject} changes its frozen implementer authority")
    base, tree = git_commit_and_tree(owner.get("attempt_base"), subject)
    if base != owner["attempt_base"] or tree != owner["attempt_base_tree"]:
        fail(f"{subject} changes its attempt-base authority")
    source = note_data(opening).get("construction_source") or {}
    if source.get("spec") != owner["spec_path"]:
        fail(f"{subject} names another living specification")
    blob = subprocess.run(
        ["git", "-C", REPO, "show", f"{base}:{owner['spec_path']}"],
        capture_output=True,
    )
    if blob.returncode != 0 or sha256_bytes(blob.stdout) != owner["base_spec_sha256"]:
        fail(f"{subject} changes its exact attempt-base specification")
    return owner


def amendment_attempt_settlement_failures(entries, before, owner, subject):
    owner_sha256 = canonical_digest(owner)
    expected = {
        "phase": AMENDMENT_DEFERRED_PHASE,
        "settlement_owner_sha256": owner_sha256,
        "opening": owner["opening"],
        "sweep_proof": owner["sweep"],
        "fixer": owner["fixer"],
        "failure_source": owner["failure_source"],
    }
    matches = []
    for index, entry in enumerate(entries[:before]):
        data = note_data(entry)
        if entry.get("kind") != "attempt.failed" or entry.get("lot") != owner["lot"] \
                or entry.get("task") != owner["task"] \
                or data.get("attempt") != owner["attempt"]:
            continue
        supersession = data.get("amendment_supersession")
        if not isinstance(supersession, dict) \
                or supersession.get("phase") != AMENDMENT_DEFERRED_PHASE:
            continue
        current_affinity = supersession.get("settlement_owner_sha256") == owner_sha256 \
            or supersession.get("opening") == owner["opening"] \
            or supersession.get("fixer") == owner["fixer"]
        exact = all(supersession.get(key) == value for key, value in expected.items())
        if current_affinity and not exact:
            fail(f"{subject}'s current deferred failure changes its settlement owner")
        if exact:
            validate_attempt_failed_entry(entries, index, entry)
            matches.append((index, entry))
    if len(matches) > 1:
        fail(f"{subject} has duplicate current deferred attempt failures")
    return matches


def amendment_attempt_settle_terminal_account(entries, before, owner, subject):
    validate_amendment_attempt_settle_owner(entries, before, owner, subject)
    owner_sha256 = canonical_digest(owner)
    failures = amendment_attempt_settlement_failures(entries, before, owner, subject)
    if len(failures) != 1:
        fail(f"{subject} has no one exact deferred attempt failure")
    failure_index, failure = failures[0]
    supersession = note_data(failure).get("amendment_supersession") or {}
    if supersession.get("phase") != AMENDMENT_DEFERRED_PHASE \
            or supersession.get("settlement_owner_sha256") != owner_sha256 \
            or supersession.get("consolidated_spec_sha256") != owner["consolidated_spec_sha256"] \
            or supersession.get("opening") != owner["opening"] \
            or supersession.get("sweep_proof") != owner["sweep"] \
            or supersession.get("fixer") != owner["fixer"]:
        fail(f"{subject}'s failure does not consume its exact settlement owner")
    retirements = [(index, entry) for index, entry in enumerate(entries[:before])
                   if entry.get("event") == "session-retired"
                   and entry.get("session") == owner["session"]]
    if len(retirements) != 1:
        fail(f"{subject} has no one exact implementer retirement")
    retired_index, retired = retirements[0]
    if retired_index <= failure_index or retired.get("status") != "superseded" \
            or retired.get("archived") is not True or retired.get("hidden") is not True \
            or any(retired.get(key) != owner[key] for key in ("lot", "task", "attempt")):
        fail(f"{subject} has no exact superseded archived hidden retirement")
    return {
        "schema": 1,
        "owner": owner,
        "owner_sha256": owner_sha256,
        "failure": journal_line_proof(failure_index),
        "restore_sha256": owner["consolidated_spec_sha256"],
        "retirement": journal_line_proof(retired_index),
    }


def validate_amendment_attempt_settled_entry(entries, index, entry):
    if entry.get("event") != "note" or entry.get("kind") != "amendment.attempt.settled" \
            or entry.get("mode") != "amendment" or entry.get("job") != "controller":
        fail("a durable Amendment attempt settlement has malformed context")
    data = note_data(entry)
    expected = amendment_attempt_settle_terminal_account(
        entries, index, data.get("owner") if isinstance(data, dict) else None,
        "the durable Amendment attempt settlement",
    )
    if data != expected or any(
        candidate.get("kind") == "amendment.attempt.settled"
        and isinstance(note_data(candidate).get("owner"), dict)
        and tuple(note_data(candidate)["owner"].get(key)
                  for key in ("amendment", "lot", "task", "attempt"))
        == tuple(expected["owner"][key] for key in ("amendment", "lot", "task", "attempt"))
        for candidate in entries[:index]
    ):
        fail("a durable Amendment attempt settlement changes or duplicates its authority", expected)
    return expected


def validate_attempt_succeeded_entry(entries, index, entry):
    data = note_data(entry)
    recovery = data.get("success_recovery")
    if recovery is not None:
        if not isinstance(recovery, dict) or "owner_sha256" not in recovery:
            fail("a recovered attempt.succeeded has no complete helper-owned account")
        owner = {key: value for key, value in recovery.items() if key != "owner_sha256"}
        expected_recovery = attempt_success_terminal_account(
            entries, index, owner, "the durable recovered attempt success",
        )
        identity = owner.get("start_account", {}).get("attempt_identity", {})
        expected = {
            "attempt": identity.get("attempt"),
            "lot": identity.get("lot"),
            "sha": owner.get("commit"),
            "gate": owner.get("gate"),
            "success_recovery": expected_recovery,
        }
        if owner.get("retry") is not None:
            expected["retry"] = owner["retry"]
        if recovery != expected_recovery or data != expected \
                or entry.get("lot") != identity.get("lot") \
                or entry.get("task") != identity.get("task"):
            fail("a durable recovered attempt success changes its exact owner", expected)
    retry = data.get("retry")
    if retry is None:
        return
    chain = retry_obligation_chain(
        entries, retry, "the successful retry obligation",
    )
    checkers = {
        checker for _, _, _, report in chain
        for key, checker in (
            ("design_review", "design-checker"), ("code_review", "code-checker"),
        ) if key in report
    }
    for checker in checkers:
        starts = [candidate for candidate in entries[:index]
                  if candidate.get("event") == "subagent-started"
                  and candidate.get("kind") == checker
                  and candidate.get("lot") == entry.get("lot")
                  and candidate.get("task") == entry.get("task")
                  and candidate.get("attempt") == data.get("attempt")
                  and candidate.get("round") == 1]
        if not starts or any(note_data(start).get("retry") != retry for start in starts):
            fail("attempt.succeeded did not give every retry obligation to its checker")


def construction_history_validation_start(entries):
    if COMMAND_VALIDATION_CACHE is None:
        return 0, None
    generation = COMMAND_VALIDATION_CACHE.get("construction-history-generation")
    if isinstance(generation, dict) \
            and generation.get("entries") is entries \
            and generation.get("entry_count") == len(entries):
        return generation["start"], generation["journal_sha256"]
    try:
        with open(JOURNAL, "rb") as source:
            raw = source.read()
    except FileNotFoundError:
        raw = b""
    physical_lines = raw.count(b"\n")
    if physical_lines < len(entries):
        return 0, sha256_bytes(raw)
    checkpoint = read_construction_history_checkpoint(raw, entries)
    start = 0 if checkpoint is None else min(checkpoint["journal_lines"], len(entries))
    COMMAND_VALIDATION_CACHE["construction-history-generation"] = {
        "journal_sha256": sha256_bytes(raw),
        "entry_count": len(entries),
        "entries": entries,
        "start": start,
        "checkpoint": checkpoint,
    }
    return start, sha256_bytes(raw)


def validate_construction_verdict_history(entries):
    start, journal_sha256 = construction_history_validation_start(entries)
    cache_key = ("construction-history", len(entries), journal_sha256)
    validation = COMMAND_VALIDATION_CACHE.get(cache_key) \
        if COMMAND_VALIDATION_CACHE is not None else None
    if isinstance(validation, dict) and validation.get("entries") is entries:
        return
    for index, entry in enumerate(entries[start:], start):
        if entry.get("event") == "session-started" \
                and entry.get("mode") == "construction" \
                and entry.get("job") == "implementer":
            validate_construction_session_start(
                entry, "the durable construction implementer start",
                entries=entries, index=index,
            )
    for index, entry in enumerate(entries[start:], start):
        if entry.get("event") == "note" \
                and entry.get("kind") == "construction.spend.recovered":
            validate_construction_spend_recovery_entry(entries, index, entry)
            construction_domain_spends(
                entries, len(entries), construction_spend_recovery_logical(note_data(entry)),
            )
    for index, entry in enumerate(entries[start:], start):
        if entry.get("event") != "note" or entry.get("kind") != "verdict.consumed":
            continue
        check = note_data(entry).get("check")
        if check == "consolidation":
            continue
        if check not in {*CONSTRUCTION_CHECKERS, "diagnostic"}:
            fail("a durable consumed verdict has an unknown checker identity", check)
        validate_construction_verdict_entry(entries, index, entry)
    for index, entry in enumerate(entries[start:], start):
        if entry.get("event") == "note" and entry.get("kind") == "design.review.resolved":
            validate_design_resolution_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "design.review.blocked":
            validate_design_blocker_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "code.review.resolved":
            validate_code_resolution_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "code.review.blocked":
            validate_code_blocker_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "attempt.failed":
            validate_attempt_failed_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "attempt.succeeded":
            validate_attempt_succeeded_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "attempt.launch.abandoned":
            validate_construction_launch_abandonment(
                entries, index, entry, "the durable orphan-launch terminal",
            )
        elif entry.get("event") == "note" and entry.get("kind") == "amendment.attempt.settled":
            validate_amendment_attempt_settled_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") == "plan.written":
            validate_plan_written_entry(entries, index, entry)
        elif entry.get("event") == "note" and entry.get("kind") in {"paused", "aborted"} \
                and isinstance(note_data(entry).get("attempt"), int):
            expected = expected_attempt_stop_data(
                entries, index, entry, "the durable stopped attempt",
            )
            if note_data(entry) != expected:
                fail("the durable stopped attempt changed its retry obligation", expected)
    if COMMAND_VALIDATION_CACHE is not None:
        COMMAND_VALIDATION_CACHE[cache_key] = {"entries": entries}


def normalize_consolidation_started(entries, data, round_number):
    if data is not None:
        fail("subagent-started consolidation derives its identity and takes no --data")
    if not isinstance(round_number, int) or round_number > 3:
        fail("a consolidation checker requires --round 1, 2 or 3")
    state, amendment_sha, spec_sha = amendment_content_identity(
        entries, len(entries), "a consolidation checker",
    )
    opening_index = state["opening_index"]
    consumed = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1
    ) if entry.get("kind") == "verdict.consumed"
        and note_data(entry).get("check") == "consolidation"]
    if consumed and note_data(consumed[-1][1]).get("outcome") == "exact":
        fail("the amendment already has an exact consolidation verdict")
    expected = len(consumed) + 1
    if round_number != expected:
        fail("a consolidation checker has the wrong logical round",
             {"expected": expected, "actual": round_number})
    if consumed:
        previous_index = consumed[-1][0]
        if not any(entry.get("kind") == "fixer.returned"
                   for entry in entries[previous_index + 1:]):
            fail("the next consolidation round precedes the discrepancy fixer's return")
    return {
        "amendment": note_data(state["opening"])["amendment"],
        "opening_sha256": note_data(state["opening"])["opening_sha256"],
        "written_sha256": note_data(state["written"])["document_sha256"],
        "sweep": state["sweep"], "sweep_sha256": state["sweep_sha256"],
        "amendment_sha256": amendment_sha, "spec_sha256": spec_sha,
    }


def consolidation_starts(entries, opening_index, before, round_number):
    return [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("event") == "subagent-started"
        and entry.get("kind") == "consolidation" and entry.get("round") == round_number]


def validate_consolidation_started(entries, index, entry):
    data = note_data(entry)
    number = data.get("amendment")
    openings = [(candidate_index, candidate) for candidate_index, candidate in amendment_openings(entries, index)
                if note_data(candidate).get("amendment") == number]
    if len(openings) != 1:
        fail("a consolidation opening belongs to no exact amendment")
    state, amendment_sha, spec_sha = amendment_content_identity(
        entries, index, "a consolidation opening",
    )
    expected = {
        "amendment": number,
        "opening_sha256": note_data(state["opening"])["opening_sha256"],
        "written_sha256": note_data(state["written"])["document_sha256"],
        "sweep": state["sweep"], "sweep_sha256": state["sweep_sha256"],
        "amendment_sha256": amendment_sha, "spec_sha256": spec_sha,
    }
    if data != expected:
        fail("a consolidation opening changes its exact reviewed content identity", expected)


def normalize_consolidation_ended(entries, data, round_number):
    if not isinstance(round_number, int) or round_number > 3 or not isinstance(data, dict):
        fail("a consolidation result requires one structured round 1, 2 or 3")
    unavailable = set(data) == {"unusable"} \
        and data.get("unusable") in CONSTRUCTION_UNUSABLE_RESULTS
    if "unusable" in data and not unavailable:
        fail("an unavailable consolidation result has an invalid shape", data)
    if not unavailable and data.get("exact") is True and set(data) != {"exact"}:
        fail("an exact consolidation result has unexpected fields", data)
    if not unavailable and data.get("exact") is False and (
        set(data) != {"exact", "discrepancies"}
        or not isinstance(data.get("discrepancies"), int)
        or isinstance(data.get("discrepancies"), bool) or data["discrepancies"] < 1
    ):
        fail("an adverse consolidation result needs one positive discrepancy count", data)
    if not unavailable and data.get("exact") not in {True, False}:
        fail("a consolidation result needs exact true or false")
    openings = amendment_openings(entries)
    if not openings:
        fail("a consolidation result has no current amendment")
    opening_index, _ = openings[-1]
    starts = consolidation_starts(entries, opening_index, len(entries), round_number)
    if not starts:
        fail("a consolidation result has no matching checker opening")
    start_index, start = starts[-1]
    if any(entry.get("event") == "subagent-ended" and entry.get("kind") == "consolidation"
           for entry in entries[start_index + 1:]):
        fail("this physical consolidation call already has a result")
    validate_consolidation_started(entries, start_index, start)
    start_data = note_data(start)
    if unavailable:
        return {**start_data, **data}
    state, amendment_sha, spec_sha = amendment_content_identity(
        entries, len(entries), "a consolidation result",
    )
    if amendment_sha != start_data.get("amendment_sha256") \
            or spec_sha != start_data.get("spec_sha256"):
        fail("the amendment or spec changed while the consolidation checker ran")
    return {**start_data, **data}


def normalize_consolidation_spend(entries, data, text, round_number):
    if data is not None or not isinstance(round_number, int) or round_number > 3 \
            or text != f"consolidation round {round_number} of 3":
        fail("a consolidation spend has malformed identity")
    openings = amendment_openings(entries)
    if not openings:
        fail("a consolidation spend has no current amendment")
    opening_index, _ = openings[-1]
    starts = consolidation_starts(entries, opening_index, len(entries), round_number)
    if not starts:
        fail("a consolidation spend precedes its checker opening")
    if any(entry.get("kind") == "bound.spent" and entry.get("round") == round_number
           and str(entry.get("text", "")).startswith("consolidation round")
           for entry in entries[opening_index + 1:]):
        fail("this logical consolidation round was already spent")
    return data


def normalize_consolidation_verdict(entries, data, text, round_number):
    if not isinstance(data, dict) or set(data) != {"check", "outcome"} \
            or data.get("check") != "consolidation" \
            or data.get("outcome") not in {"exact", "discrepancies"}:
        fail("a consolidation verdict has malformed structured data", data)
    if not isinstance(round_number, int) or round_number > 3:
        fail("a consolidation verdict requires --round 1, 2 or 3")
    if data["outcome"] == "exact" and text is not None:
        fail("an exact consolidation verdict takes no discrepancy text")
    if data["outcome"] == "discrepancies" and (not isinstance(text, str) or not text.strip()):
        fail("an adverse consolidation verdict requires its exact discrepancy text")
    openings = amendment_openings(entries)
    if not openings:
        fail("a consolidation verdict has no current amendment")
    opening_index, _ = openings[-1]
    if any(entry.get("kind") == "verdict.consumed"
           and note_data(entry).get("check") == "consolidation"
           and entry.get("round") == round_number
           for entry in entries[opening_index + 1:]):
        fail("this consolidation round already has a consumed verdict")
    spends = [entry for entry in entries[opening_index + 1:]
              if entry.get("kind") == "bound.spent" and entry.get("round") == round_number
              and entry.get("text") == f"consolidation round {round_number} of 3"]
    if len(spends) != 1:
        fail("a consolidation verdict has no one exact logical-round spend")
    ends = [entry for entry in entries[opening_index + 1:]
            if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "consolidation" and entry.get("round") == round_number]
    if not ends:
        fail("a consolidation verdict has no physical checker result")
    result = note_data(ends[-1])
    expected_outcome = "exact" if result.get("exact") is True else "discrepancies"
    if data["outcome"] != expected_outcome:
        fail("a consolidation verdict contradicts the checker result")
    expected = {key: result[key] for key in (
        "amendment", "opening_sha256", "written_sha256", "sweep", "sweep_sha256",
        "amendment_sha256", "spec_sha256",
    )}
    if expected_outcome == "discrepancies":
        expected["discrepancies"] = result["discrepancies"]
    return {**data, **expected}


def validate_consolidation_verdict_entry(entries, index, entry):
    data = note_data(entry)
    round_number = entry.get("round")
    if not isinstance(round_number, int) or isinstance(round_number, bool) \
            or round_number < 1 or round_number > 3 \
            or data.get("check") != "consolidation" \
            or data.get("outcome") not in {"exact", "discrepancies"}:
        fail("a durable consolidation verdict has malformed identity")
    openings = amendment_openings(entries, index)
    if not openings:
        fail("a durable consolidation verdict has no amendment opening")
    opening_index, opening = openings[-1]
    number = note_data(opening)["amendment"]
    if data.get("amendment") != number \
            or data.get("opening_sha256") != note_data(opening).get("opening_sha256"):
        fail("a durable consolidation verdict belongs to another amendment generation")
    previous = [candidate for candidate in entries[opening_index + 1:index]
                if candidate.get("kind") == "verdict.consumed"
                and note_data(candidate).get("check") == "consolidation"]
    if round_number != len(previous) + 1:
        fail("a durable consolidation verdict has the wrong logical round")
    spends = [candidate for candidate in entries[opening_index + 1:index]
              if candidate.get("kind") == "bound.spent"
              and candidate.get("round") == round_number
              and candidate.get("text") == f"consolidation round {round_number} of 3"]
    if len(spends) != 1:
        fail("a durable consolidation verdict has no one exact domain spend")
    ends = [(candidate_index, candidate) for candidate_index, candidate in enumerate(
        entries[opening_index + 1:index], opening_index + 1
    ) if candidate.get("event") == "subagent-ended"
        and candidate.get("kind") == "consolidation"
        and candidate.get("round") == round_number]
    if not ends:
        fail("a durable consolidation verdict has no checker result")
    end_index, result = ends[-1]
    starts = consolidation_starts(entries, opening_index, end_index, round_number)
    if not starts:
        fail("a durable consolidation result has no checker opening")
    _, start = starts[-1]
    identity_keys = (
        "amendment", "opening_sha256", "written_sha256", "sweep", "sweep_sha256",
        "amendment_sha256", "spec_sha256",
    )
    if any(note_data(start).get(key) != note_data(result).get(key) for key in identity_keys) \
            or any(data.get(key) != note_data(result).get(key) for key in identity_keys):
        fail("a durable consolidation chain changes its frozen content identity")
    expected_outcome = "exact" if note_data(result).get("exact") is True else "discrepancies"
    if data["outcome"] != expected_outcome:
        fail("a durable consolidation verdict contradicts its checker result")
    if expected_outcome == "exact":
        if set(data) != {"check", "outcome", *identity_keys} or entry.get("text") is not None:
            fail("an exact durable consolidation verdict has malformed proof")
    elif set(data) != {"check", "outcome", *identity_keys, "discrepancies"} \
            or data.get("discrepancies") != note_data(result).get("discrepancies") \
            or not isinstance(entry.get("text"), str) or not entry["text"].strip():
        fail("an adverse durable consolidation verdict has malformed proof")


def amendment_review_proof(entries, before, number, spec_argument=None, *, require_current=True):
    state = current_amendment_review(entries, before, "an amendment close")
    if note_data(state["opening"]).get("amendment") != number:
        fail("an amendment close names another current generation")
    spec_relative = os.path.relpath(state["spec_path"], project_root())
    if spec_argument is not None and spec_argument != spec_relative:
        fail("an amendment close names another specification path",
             {"expected": spec_relative, "actual": spec_argument})
    opening_index = state["opening_index"]
    verdicts = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "verdict.consumed"
        and note_data(entry).get("check") == "consolidation"]
    for verdict_index, verdict in verdicts:
        validate_consolidation_verdict_entry(entries, verdict_index, verdict)
    if not verdicts or note_data(verdicts[-1][1]).get("outcome") != "exact":
        fail("an amendment close has no exact consumed consolidation verdict")
    verdict_index, verdict = verdicts[-1]
    verdict_data = note_data(verdict)
    if any(entry.get("kind") in {"fixer.dispatched", "fixer.returned", "sweep.reported"}
           or entry.get("event") in {"subagent-started", "subagent-ended"}
           and entry.get("kind") == "consolidation"
           for entry in entries[verdict_index + 1:before]):
        fail("an amendment close has review work after its exact consolidation verdict")
    amendment_sha = verdict_data.get("amendment_sha256")
    spec_sha = verdict_data.get("spec_sha256")
    if require_current:
        with open(state["amendment_path"], "rb") as source:
            current_amendment_sha = sha256_bytes(source.read())
        with open(state["spec_path"], "rb") as source:
            current_spec_sha = sha256_bytes(source.read())
        if current_amendment_sha != amendment_sha or current_spec_sha != spec_sha:
            fail("the amendment or specification changed after its exact consolidation verdict")
    proof = {
        "amendment": number,
        "opening_sha256": note_data(state["opening"])["opening_sha256"],
        "written_sha256": note_data(state["written"])["document_sha256"],
        "sweep": state["sweep"], "sweep_sha256": state["sweep_sha256"],
        "consolidation_round": verdict.get("round"),
        "amendment_sha256": amendment_sha, "spec_sha256": spec_sha,
        "spec_path": spec_relative,
    }
    proof["review_sha256"] = sha256_bytes(json.dumps(
        proof, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    return proof


def validate_amendment_commit_entry(entries, index, entry, *, require_current=False):
    data = note_data(entry)
    required = {
        "amendment", "sha", "op", "opening_sha256", "written_sha256", "sweep",
        "sweep_sha256", "consolidation_round", "amendment_sha256", "spec_sha256",
        "review_sha256",
    }
    if set(data) != required or not isinstance(data.get("amendment"), int) \
            or isinstance(data.get("amendment"), bool) or data["amendment"] < 1 \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(data.get("sha"))) \
            or not isinstance(data.get("op"), str) or not data["op"]:
        fail("amendment.committed has malformed proof data", data)
    proof = amendment_review_proof(
        entries, index, data["amendment"], require_current=require_current,
    )
    public_proof = {key: value for key, value in proof.items() if key != "spec_path"}
    if any(data.get(key) != value for key, value in public_proof.items()):
        fail("amendment.committed does not consume the exact clean review state", public_proof)
    if any(candidate.get("kind") == "amendment.committed"
           and note_data(candidate).get("amendment") == data["amendment"]
           for candidate in entries[:index]):
        fail("this amendment generation already has a committed terminal")
    repo = project_root()
    if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{data['sha']}^{{commit}}"],
                      capture_output=True).returncode != 0:
        fail("amendment.committed names no real commit", data["sha"])
    spec_relative = proof["spec_path"]
    amendment_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-amendment-{data['amendment']}.md"
    names = subprocess.run(
        ["git", "-C", repo, "diff-tree", "--root", "--no-commit-id", "--name-only",
         "-r", data["sha"]], capture_output=True, text=True,
    )
    if names.returncode != 0 or set(names.stdout.splitlines()) != {amendment_relative,
                                                                    spec_relative}:
        fail("the amendment commit contains another path or omits an owned path")
    for relative, expected, subject in (
        (amendment_relative, data["amendment_sha256"], "amendment copy"),
        (spec_relative, data["spec_sha256"], "committed specification"),
    ):
        blob = subprocess.run(
            ["git", "-C", repo, "show", f"{data['sha']}:{relative}"], capture_output=True,
        )
        if blob.returncode != 0 or sha256_bytes(blob.stdout) != expected:
            fail(f"the {subject} does not match its frozen reviewed bytes")
    return proof


def validate_gate_subagent(event, data):
    """A gate receipt consumes the exact live logical check marker."""
    if isinstance(data, dict) and data.get("scope") == "discovery":
        expected = {"scope"} if event == "subagent-started" else None
        terminal_shape = set(data) in ({"scope", "green", "surface"}, {"scope", "unusable"})
        if event == "subagent-started" and set(data) != expected \
                or event == "subagent-ended" and not terminal_shape:
            fail(f"{event} discovery gate-runner has malformed data", data)
        if event == "subagent-ended" and "unusable" in data \
                and data["unusable"] not in CONSTRUCTION_UNUSABLE_RESULTS:
            fail("subagent-ended discovery gate-runner has an invalid unusable result", data)
        if event == "subagent-ended" and "unusable" not in data and (
                not isinstance(data.get("green"), bool)
                or data.get("surface") not in {"unchanged", "different"}
        ):
            fail("subagent-ended discovery gate-runner has an invalid result", data)
        entries = journal_entries()
        starts = [entry for entry in entries if entry.get("event") == "subagent-started"
                  and entry.get("kind") == "gate-runner"
                  and note_data(entry).get("scope") == "discovery"]
        ends = [entry for entry in entries if entry.get("event") == "subagent-ended"
                and entry.get("kind") == "gate-runner"
                and note_data(entry).get("scope") == "discovery"]
        completed = [entry for entry in ends if "unusable" not in note_data(entry)]
        if event == "subagent-started" and (completed or len(starts) >= 2):
            fail("the discovery gate-runner cannot open another physical call")
        return

    base_keys = {
        "op", "scope", "owner", "lot", "task", "attempt", "head", "base",
        "tree", "gate", "code",
    }
    result_keys = {"green", "surface", "report", "report_sha256", "commands"}
    identity_keys = base_keys | ({"execution"} if isinstance(data, dict) and "execution" in data else set())
    expected_shapes = (identity_keys,) if event == "subagent-started" else (
        identity_keys | result_keys, identity_keys | {"unusable"},
    )
    if not isinstance(data, dict) or set(data) not in expected_shapes:
        fail(f"{event} gate-runner has an incomplete logical-check identity", data)
    if not isinstance(data.get("op"), str) or not re.fullmatch(r"[0-9a-f]{64}", data["op"]):
        fail(f"{event} gate-runner has an invalid operation identity")
    if data.get("scope") not in {"task", "review", "baseline"}:
        fail(f"{event} gate-runner has an invalid scope")
    if "execution" in data and not re.fullmatch(r"[0-9a-f]{64}", str(data["execution"])):
        fail(f"{event} gate-runner has an invalid execution identity")
    if not isinstance(data.get("task"), int) or isinstance(data.get("task"), bool) \
            or not isinstance(data.get("attempt"), int) or isinstance(data.get("attempt"), bool):
        fail(f"{event} gate-runner has an invalid task identity")
    if event == "subagent-ended" and "unusable" in data:
        if data["unusable"] not in CONSTRUCTION_UNUSABLE_RESULTS:
            fail("subagent-ended gate-runner has an invalid unusable result")
    elif event == "subagent-ended":
        if not isinstance(data.get("green"), bool) \
                or data.get("surface") not in {"unchanged", "different"} \
                or not isinstance(data.get("report"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", data.get("report_sha256", "")) \
                or not isinstance(data.get("commands"), int) \
                or isinstance(data.get("commands"), bool) or data["commands"] < 1:
            fail("subagent-ended gate-runner has an invalid result")

    if os.path.islink(GATE_MARKER) or not os.path.isfile(GATE_MARKER):
        fail("a gate-runner event has no real live gate-check marker")
    marker = {}
    with open(GATE_MARKER, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    if len(lines) not in {11, 12}:
        fail("the live gate-check marker is malformed", {"lines": len(lines)})
    for line in lines:
        key, separator, value = line.partition(" ")
        if not separator or not value or key in marker:
            fail("the live gate-check marker is malformed", line)
        marker[key] = value
    if set(marker) not in (base_keys, base_keys | {"execution"}):
        fail("the live gate-check marker has an incomplete identity", marker)
    normalized = dict(marker)
    try:
        normalized["task"] = int(normalized["task"])
        normalized["attempt"] = int(normalized["attempt"])
    except ValueError:
        fail("the live gate-check marker has a non-numeric task identity")
    if "execution" in marker:
        execution = subprocess.run(
            [sys.executable, GATE_EXECUTION, "validate-token", marker["execution"],
             marker["gate"], marker["tree"]],
            capture_output=True,
            text=True,
        )
        if execution.returncode != 0:
            fail("the live gate-check marker has an invalid frozen execution", execution.stderr)
        normalized["execution"] = execution.stdout.strip()
    identity_keys = base_keys | ({"execution"} if "execution" in marker else set())
    if set(data) != (identity_keys if event == "subagent-started" else identity_keys | result_keys):
        if event != "subagent-ended" or set(data) != identity_keys | {"unusable"}:
            fail("the gate-runner event and marker disagree about execution identity", data)
    if any(data[key] != normalized[key] for key in identity_keys):
        fail("the gate-runner event does not match the live logical check", {
            "event": {key: data[key] for key in sorted(identity_keys)},
            "marker": {key: normalized[key] for key in sorted(identity_keys)},
        })

    if event != "subagent-ended" or "unusable" not in data:
        check = subprocess.run(
            ["bash", GATE_CHECK, "verify", data["op"]], capture_output=True, text=True
        )
        if check.returncode != 0:
            fail("the gate-runner candidate or gate changed before its event", check.stderr or check.stdout)
    elif "execution" in data:
        idle = subprocess.run(
            [sys.executable, GATE_EXECUTION, "idle", data["op"]],
            capture_output=True, text=True,
        )
        if idle.returncode != 0:
            fail("the unavailable gate-runner still owns a live executor or command",
                 idle.stderr or idle.stdout)

    if event == "subagent-ended" and "unusable" not in data:
        audit = subprocess.run(
            [sys.executable, GATE_REPORT, data["op"], data["gate"], data["tree"],
             data.get("execution", "-")],
            capture_output=True,
            text=True,
        )
        if audit.returncode != 0:
            fail("the gate-runner has no complete canonical physical result", audit.stderr or audit.stdout)
        try:
            outcome = json.loads(audit.stdout)
        except ValueError:
            fail("the physical gate result audit returned malformed JSON", audit.stdout)
        if set(outcome) != result_keys or any(data[key] != outcome[key] for key in result_keys):
            fail("the gate-runner terminal does not derive from its canonical physical result", {
                "terminal": {key: data[key] for key in sorted(result_keys)},
                "audit": outcome,
            })

    entries = journal_entries()
    matching_starts = [
        entry for entry in entries
        if entry.get("event") == "subagent-started" and entry.get("kind") == "gate-runner"
        and note_data(entry).get("op") == data["op"]
    ]
    matching_ends = [
        entry for entry in entries
        if entry.get("event") == "subagent-ended" and entry.get("kind") == "gate-runner"
        and note_data(entry).get("op") == data["op"]
    ]
    completed_ends = [entry for entry in matching_ends if "unusable" not in note_data(entry)]
    if event == "subagent-started":
        if completed_ends or len(matching_starts) >= 2:
            fail(f"logical gate check {data['op']} already has a terminal result")
    elif "unusable" not in data and completed_ends:
        fail(f"logical gate check {data['op']} already has a terminal result")


def validate_spec_loop_verifier(event, data):
    common_keys = {
        "owner", "commit_op", "sha", "ruling",
        "authority_kind", "authority_ref", "authority_sha256",
    }
    expected_shapes = (common_keys,) if event == "subagent-started" else (
        common_keys | {"present"}, common_keys | {"unusable"},
    )
    if not isinstance(data, dict) or set(data) not in expected_shapes \
            or data.get("owner") != "spec-loop" \
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", str(data.get("commit_op"))) \
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(data.get("sha"))) \
            or not re.fullmatch(r"R[1-9][0-9]*", str(data.get("ruling"))) \
            or data.get("authority_kind") not in DIRECT_AUTHORITY_KINDS \
            or not isinstance(data.get("authority_ref"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("authority_sha256"))) \
            or (event == "subagent-ended" and "present" in data
                and not isinstance(data.get("present"), bool)) \
            or (event == "subagent-ended" and "unusable" in data
                and data.get("unusable") not in CONSTRUCTION_UNUSABLE_RESULTS):
        fail("a SPEC-loop finding-verifier event has malformed exact identity or result", data)
    entries = journal_entries()
    commits = [entry for entry in entries if entry.get("kind") == "spec.committed"
               and note_data(entry).get("op") == data["commit_op"]
               and note_data(entry).get("sha") == data["sha"]
               and not any(key in note_data(entry) for key in ("ruling", "batch", "breach"))]
    if len(commits) != 1:
        fail("the SPEC-loop verifier has no one exact preceding shared close")
    dispatches = [entry for entry in entries if entry.get("kind") == "fixer.dispatched"
                  and note_data(entry).get("ruling") == data["ruling"]
                  and note_data(entry).get("route") == "spec-fixer"
                  and all(note_data(entry).get(key) == data[key]
                          for key in ("authority_kind", "authority_ref", "authority_sha256"))]
    if len(dispatches) != 1:
        fail("the SPEC-loop verifier has no one exact pending owner-linked assignment")
    starts = [entry for entry in entries if entry.get("event") == "subagent-started"
              and entry.get("kind") == "finding-verifier"
              and note_data(entry).get("owner") == "spec-loop"
              and note_data(entry).get("commit_op") == data["commit_op"]
              and note_data(entry).get("ruling") == data["ruling"]]
    ends = [entry for entry in entries if entry.get("event") == "subagent-ended"
            and entry.get("kind") == "finding-verifier"
            and note_data(entry).get("owner") == "spec-loop"
            and note_data(entry).get("commit_op") == data["commit_op"]
            and note_data(entry).get("ruling") == data["ruling"]]
    completed = [entry for entry in ends if "unusable" not in note_data(entry)]
    if event == "subagent-started" and (completed or len(starts) >= 2):
        fail("the SPEC-loop verifier cannot open another physical call")
    if event == "subagent-ended" and starts \
            and any(note_data(starts[-1]).get(key) != data[key] for key in common_keys):
        fail("the SPEC-loop verifier result changes its opening identity")
PASS_OPENING_KEYS = {
    "built", "commit", "gate", "source_scope", "source_owner",
    "source_lot", "source_task", "source_attempt",
}
PASS_OPENING_RECOVERY_KEYS = {
    "schema", "opening", "owner", "built", "commit", "gate", "from", "to", "stop",
}


def pass_opening_context(data, mode):
    return {"mode": mode, "lot": data["built"], "job": "controller"}


def validate_pass_opening_context(entries, opening_index, before, subject):
    opening = entries[opening_index]
    data = note_data(opening)
    expected = pass_opening_context(data, "product-review")
    actual = {key: opening[key] for key in CONTEXT_FIELDS if key in opening}
    recoveries = [
        (index, entry) for index, entry in enumerate(entries[opening_index + 1:before],
                                                       opening_index + 1)
        if entry.get("kind") == "pass.opening.context.recovered"
    ]
    if actual == expected:
        if recoveries:
            fail(f"{subject} has an unexpected pass-opening context recovery")
        return

    legacy = pass_opening_context(data, "construction")
    if actual != legacy:
        fail(f"{subject} has no exact PRODUCT REVIEW controller context", actual)
    if not isinstance(opening.get("by"), str) or not opening["by"]:
        fail(f"{subject} has no exact physical controller owner")

    proof = journal_line_proof(opening_index)
    if len(recoveries) != 1:
        fail(f"{subject} has no one exact pass-opening context recovery",
             f"found {len(recoveries)}")
    recovery_index, recovery = recoveries[0]
    stop_state = pass_opening_stop_suffix(
        entries, opening_index + 1, recovery_index, subject,
    )
    if stop_state["phase"] not in {"active", "resumed"}:
        fail(f"{subject}'s pass-opening context recovery crosses a current run stop")
    recovery_data = note_data(recovery)
    expected_data = {
        "schema": 1,
        "opening": proof,
        "owner": opening["by"],
        "built": data["built"],
        "commit": data["commit"],
        "gate": data["gate"],
        "from": legacy,
        "to": expected,
        "stop": pass_opening_stop_account(stop_state),
    }
    recovery_context = {key: recovery[key] for key in CONTEXT_FIELDS if key in recovery}
    if recovery.get("event") != "note" \
            or recovery.get("by") != opening["by"] \
            or set(recovery_data) != PASS_OPENING_RECOVERY_KEYS \
            or recovery_data != expected_data \
            or recovery_context != expected:
        fail(f"{subject} has a malformed pass-opening context recovery", recovery_data)


def pass_closes(entries, opening_index, before):
    return [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "pass.closed"]


def pass_opening_stop_suffix(entries, start, before, subject):
    opening = entries[start - 1]
    opening_data = note_data(opening)
    owner = opening.get("by")
    expected_context = pass_opening_context(opening_data, "product-review")
    state = {
        "phase": "active", "mode": None, "op": None, "pending": {},
        "terminal": None, "retirements": [], "report": None, "resumed": None,
        "cleanup": None,
    }
    with open(JOURNAL, "rb") as source:
        durable_lines = source.read().splitlines()

    def proof(index, entry):
        encoded = json.dumps(
            entry, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if index < len(durable_lines):
            payload = durable_lines[index]
            if payload != encoded:
                fail(f"{subject} changes a stop-owned durable journal event",
                     f"progress.jsonl line {index + 1}")
        elif index == len(durable_lines):
            payload = encoded
        else:
            fail(f"{subject} names a journal proof beyond its append boundary", index)
        return f"{index}:{hashlib.sha256(payload).hexdigest()}"

    def context(entry):
        return {key: entry[key] for key in CONTEXT_FIELDS if key in entry}

    def controller_event(entry):
        return entry.get("by") == owner and context(entry) == expected_context

    def active_sessions(at):
        starts = {}
        retired = set()
        for index, entry in enumerate(entries[:at]):
            event, session = entry.get("event"), entry.get("session")
            if event == "session-started":
                if not isinstance(session, str) or not session or session in starts:
                    fail(f"{subject} has a malformed physical-session history",
                         f"progress.jsonl line {index + 1}")
                starts[session] = entry
            elif event == "session-retired" and session in starts:
                if session in retired:
                    fail(f"{subject} has duplicate physical-session retirement",
                         f"progress.jsonl line {index + 1}")
                retired.add(session)
        return {session: entry for session, entry in starts.items()
                if session not in retired}

    def exact_helper_stop(entry):
        data = note_data(entry)
        return entry.get("event") == "note" \
            and entry.get("kind") in {"paused", "aborted"} \
            and controller_event(entry) \
            and set(data) == {"sha", "op"} \
            and isinstance(data["sha"], str) \
            and re.fullmatch(r"[0-9a-f]{40,64}", data["sha"]) \
            and isinstance(data["op"], str) \
            and re.fullmatch(r"[0-9a-f]{64}", data["op"]) \
            and isinstance(entry.get("text"), str) and bool(entry["text"])

    def exact_retirement(entry, started):
        session = entry.get("session")
        started_context = context(started)
        watchdog = started_context.get("job") == "watchdog"
        allowed_statuses = {"done"} if watchdog else {"done", "cancelled"}
        return entry.get("event") == "session-retired" \
            and entry.get("by") == owner \
            and context(entry) == started_context \
            and entry.get("status") in allowed_statuses \
            and entry.get("archived") is True \
            and entry.get("hidden") is True \
            and "kind" not in entry and "text" not in entry and "data" not in entry \
            and isinstance(session, str)

    def exact_controller_report(entry):
        return entry.get("event") == "note" \
            and entry.get("kind") == state["mode"] \
            and controller_event(entry) \
            and "data" not in entry \
            and isinstance(entry.get("text"), str) and bool(entry["text"])

    def exact_resume(entry):
        return entry.get("event") == "note" and entry.get("kind") == "resumed" \
            and controller_event(entry) and "data" not in entry and "text" not in entry

    def abort_account():
        return {
            "opening": proof(start - 1, opening),
            "owner": owner,
            "mode": "aborted",
            "op": state["op"],
            "terminal": state["terminal"],
            "retirements": state["retirements"],
            "report": state["report"],
        }

    def exact_cleanup(entry):
        return entry.get("event") == "note" \
            and entry.get("kind") == "cleanup.started" \
            and controller_event(entry) \
            and note_data(entry) == {
                "schema": 1,
                "reason": "aborted", "scope": "whole-run", "choice": "clean",
                "abort": abort_account(),
            } \
            and "text" not in entry

    for index, entry in enumerate(entries[start:before], start):
        phase = state["phase"]
        if phase == "active" and exact_helper_stop(entry):
            mode = entry["kind"]
            pending = active_sessions(index)
            watchdogs = [session for session, started in pending.items()
                         if context(started).get("job") == "watchdog"]
            if len(watchdogs) != 1:
                fail(f"{subject} has no one exact active watchdog at its stop boundary",
                     f"found {len(watchdogs)}")
            state = {
                "phase": "retirements" if pending else "controller-report",
                "mode": mode,
                "op": note_data(entry)["op"],
                "pending": pending,
                "terminal": proof(index, entry),
                "retirements": [],
                "report": None,
                "resumed": None,
                "cleanup": None,
            }
        elif phase == "retirements":
            session = entry.get("session")
            started = state["pending"].get(session)
            if started is None or not exact_retirement(entry, started):
                fail(f"{subject} has a foreign or malformed stop-owned retirement",
                     f"progress.jsonl line {index + 1}")
            if context(started).get("job") == "watchdog" \
                    and any(context(candidate).get("job") != "watchdog"
                            for candidate in state["pending"].values()):
                fail(f"{subject} retires its watchdog before another stopped child",
                     f"progress.jsonl line {index + 1}")
            state["pending"] = dict(state["pending"])
            state["pending"].pop(session)
            state["retirements"] = [*state["retirements"], proof(index, entry)]
            if not state["pending"]:
                state["phase"] = "controller-report"
        elif phase == "controller-report" and exact_controller_report(entry):
            state["phase"] = "pause-reported" \
                if state["mode"] == "paused" else "aborted"
            state["report"] = proof(index, entry)
        elif phase == "pause-reported" and exact_resume(entry):
            state["phase"] = "resumed"
            state["resumed"] = proof(index, entry)
        elif phase == "aborted" and exact_cleanup(entry):
            state["phase"] = "cleanup"
            state["cleanup"] = proof(index, entry)
        else:
            fail(f"{subject} has an event outside its exact stop-owned suffix",
                 f"progress.jsonl line {index + 1}")
    return state


def pass_opening_cleanup_account(entries, opening_index, before, subject):
    opening = entries[opening_index]
    state = pass_opening_stop_suffix(entries, opening_index + 1, before, subject)
    if state["phase"] != "cleanup" or state["mode"] != "aborted" \
            or state["pending"] or state["report"] is None \
            or state["cleanup"] is None or state["resumed"] is not None:
        fail(f"{subject} has no exact completed abort and whole-run cleanup account")
    abort = {
        "opening": journal_line_proof(opening_index),
        "owner": opening["by"],
        "mode": "aborted",
        "op": state["op"],
        "terminal": state["terminal"],
        "retirements": state["retirements"],
        "report": state["report"],
    }
    return {
        "schema": 1,
        "reason": "aborted", "scope": "whole-run", "choice": "clean",
        "abort": abort,
        "cleanup": state["cleanup"],
    }


def pass_opening_cleanup_data(entries, owner, supplied, subject):
    expected_input = {"reason": "aborted", "scope": "whole-run", "choice": "clean"}
    if supplied != expected_input or owner["stop"]["phase"] != "aborted":
        fail(f"{subject} has no exact completed abort cleanup request", supplied)
    state = owner["stop"]
    opening_index = owner["opening_index"]
    opening = owner["opening"]
    return {
        "schema": 1,
        **expected_input,
        "abort": {
            "opening": journal_line_proof(opening_index),
            "owner": opening["by"],
            "mode": "aborted",
            "op": state["op"],
            "terminal": state["terminal"],
            "retirements": state["retirements"],
            "report": state["report"],
        },
    }


def pass_opening_stop_account(state):
    if state["phase"] == "active":
        return None
    if state["phase"] != "resumed" or state["mode"] != "paused" \
            or state["pending"] or state["report"] is None or state["resumed"] is None:
        fail("the pass-opening context recovery has no complete pause/resume account")
    return {
        "mode": "paused",
        "op": state["op"],
        "terminal": state["terminal"],
        "retirements": state["retirements"],
        "report": state["report"],
        "resumed": state["resumed"],
    }


def validate_pass_opening_bare_stop_marker(entry, subject):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(BARE_STOP_MARKER, flags)
    except OSError as exc:
        fail(f"{subject} has no exact physical bare-stop owner", exc)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail(f"{subject}'s bare-stop owner is not one regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            payload = source.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject}'s bare-stop owner is not valid UTF-8", exc)
    lines = text.splitlines()
    data = note_data(entry)
    mode = {"paused": "pause", "aborted": "abort"}.get(entry.get("kind"))
    call_prefix = f"call prompts/common/stop.sh {mode}"
    valid_call = lines[3] == call_prefix if len(lines) == 6 else False
    if mode == "abort" and len(lines) == 6:
        valid_call = valid_call or lines[3].startswith(f"{call_prefix} ")
    if not payload.endswith(b"\n") or len(lines) != 6 \
            or lines[0] != f"op {data.get('op')}" \
            or lines[1] != f"mode {mode}" \
            or not re.fullmatch(r"hash [0-9a-f]{64}", lines[2]) \
            or not valid_call \
            or lines[4] != f"phase tree-settled {data.get('sha')}" \
            or not lines[5].startswith("report "):
        fail(f"{subject} does not match its exact physical bare-stop owner")
    encoded = lines[5][len("report "):]
    try:
        report = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        fail(f"{subject}'s bare-stop owner has a malformed report", exc)
    if base64.b64encode(report.encode("utf-8")).decode("ascii") != encoded \
            or report != entry.get("text"):
        fail(f"{subject} changes its physical bare-stop report")


def pending_malformed_pass_opening(entries, before, subject):
    openings = [(index, entry) for index, entry in enumerate(entries[:before])
                if entry.get("kind") == "pass.opened"]
    if not openings:
        return None
    opening_index, opening = openings[-1]
    if pass_closes(entries, opening_index, before):
        return None
    data = note_data(opening)
    if set(data) != PASS_OPENING_KEYS:
        return None
    actual = {key: opening[key] for key in CONTEXT_FIELDS if key in opening}
    if actual == pass_opening_context(data, "product-review"):
        return None
    if actual != pass_opening_context(data, "construction") \
            or not isinstance(opening.get("by"), str) or not opening["by"]:
        return None
    recoveries = [entry for entry in entries[opening_index + 1:before]
                  if entry.get("kind") == "pass.opening.context.recovered"]
    if recoveries:
        validate_pass_opening_context(entries, opening_index, before, subject)
        return None
    return {
        "opening_index": opening_index,
        "opening": opening,
        "data": data,
        "stop": pass_opening_stop_suffix(
            entries, opening_index + 1, before, subject,
        ),
    }


def validate_pending_pass_opening_append(entries, candidate, subject):
    owner = pending_malformed_pass_opening(entries, len(entries), subject)
    if owner is None:
        return
    kind = candidate.get("kind")
    event = candidate.get("event")
    state = owner["stop"]
    phase = state["phase"]
    if event == "note" and kind == "pass.opening.context.recovered" \
            and phase in {"active", "resumed"}:
        return
    if phase in {
        "active", "retirements", "controller-report", "pause-reported", "aborted",
    }:
        if phase == "active" and event == "note" and kind in {"paused", "aborted"}:
            validate_pass_opening_bare_stop_marker(candidate, subject)
        pass_opening_stop_suffix(
            [*entries, candidate], owner["opening_index"] + 1, len(entries) + 1,
            subject,
        )
        return
    fail(f"{subject} is blocked by the pending PRODUCT REVIEW opening-context recovery")


def exact_pass_gate_result(entries, before, data, subject):
    matches = [entry for entry in entries[:before]
               if entry.get("event") == "subagent-ended"
               and entry.get("kind") == "gate-runner"
               and note_data(entry).get("op") == data["gate"]
               and "unusable" not in note_data(entry)]
    if len(matches) != 1:
        fail(f"{subject} has no one exact durable gate result")
    result = note_data(matches[0])
    expected = {
        "scope": data["source_scope"], "owner": data["source_owner"],
        "lot": data["source_lot"], "task": data["source_task"],
        "attempt": data["source_attempt"],
    }
    if any(result.get(key) != value for key, value in expected.items()) \
            or result.get("green") is not True or result.get("surface") != "unchanged":
        fail(f"{subject}'s durable gate result changes its source identity", result)
    if data["source_scope"] == "baseline":
        if result.get("head") != data["commit"]:
            fail(f"{subject}'s baseline gate checked another commit")
    else:
        commit_tree = subprocess.run(
            ["git", "-C", project_root(), "rev-parse", "--verify",
             f"{data['commit']}^{{tree}}"],
            capture_output=True, text=True,
        )
        if commit_tree.returncode != 0 or result.get("tree") != commit_tree.stdout.strip():
            fail(f"{subject}'s task gate checked another candidate tree")
        successes = [entry for entry in entries[:before]
                     if entry.get("kind") == "attempt.succeeded"
                     and entry.get("lot") == data["source_lot"]
                     and entry.get("task") == data["source_task"]
                     and note_data(entry).get("attempt") == data["source_attempt"]
                     and note_data(entry).get("gate") == data["gate"]
                     and note_data(entry).get("sha") == data["commit"]]
        if len(successes) != 1:
            fail(f"{subject} has no exact accepted task success")
    return result


def commit_changes_only(commit, expected_path):
    result = subprocess.run(
        ["git", "-C", project_root(), "diff-tree", "--root", "--no-commit-id",
         "--name-only", "-r", commit], capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.splitlines() == [expected_path]


def validate_baseline_pass_successor(entries, before, built, commit, owner, subject):
    prior = [(index, entry) for index, entry in enumerate(entries[:before])
             if entry.get("kind") == "pass.opened"]
    if not prior:
        fail(f"{subject} cannot use a controller baseline as the first pass of a built lot")
    prior_index, prior_opening = prior[-1]
    prior_data = note_data(prior_opening)
    if prior_data.get("built") != built:
        fail(f"{subject}'s baseline does not succeed the same voided built lot")
    closes = pass_closes(entries, prior_index, before)
    if len(closes) != 1 or note_data(closes[0][1]) != {"voided": True}:
        fail(f"{subject}'s controller baseline does not follow one exact voided pass")
    amendments = [(index, entry) for index, entry in enumerate(
        entries[prior_index + 1:before], prior_index + 1
    ) if entry.get("kind") == "amendment.opened"
        and note_data(entry).get("origin") == "product-review"
        and note_data(entry).get("built") == built]
    if len(amendments) != 1:
        fail(f"{subject} has no one product-review amendment for its voided generation")
    amendment_index, amendment = amendments[0]
    amendment_number = note_data(amendment).get("amendment")
    commits = [(index, entry) for index, entry in enumerate(
        entries[amendment_index + 1:before], amendment_index + 1
    ) if entry.get("kind") == "amendment.committed"]
    if len(commits) != 1:
        fail(f"{subject}'s amendment successor has no one exact committed tail")
    commit_index, amendment_commit = commits[0]
    validate_amendment_commit_entry(entries, commit_index, amendment_commit)
    amendment_sha = note_data(amendment_commit).get("sha")
    expected_owner = f"amendment/{amendment_number}/{commit}"
    if commit != amendment_sha:
        plan_events = [entry for entry in entries[commit_index + 1:before]
                       if entry.get("kind") == "plan.written"]
        expected_plan = f"docs/plans/{os.path.basename(WORKSPACE)}-{built}-plan.md"
        parent = subprocess.run(
            ["git", "-C", project_root(), "rev-parse", f"{commit}^"],
            capture_output=True, text=True,
        ) if isinstance(amendment_sha, str) else None
        if not plan_events or parent is None or parent.returncode != 0 \
                or parent.stdout.strip() != amendment_sha \
                or not commit_changes_only(commit, expected_plan):
            fail(f"{subject} is not the amendment commit or its exact C2 plan successor")
        expected_owner = f"plan/{built}/{commit}"
    if owner != expected_owner:
        fail(f"{subject}'s baseline gate has the wrong controller owner",
             {"expected": expected_owner, "actual": owner})


def plan_task_manifest(payload, subject):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject} is not valid UTF-8", exc)
    headings = []
    ordinals = []
    malformed = []
    pattern = re.compile(r"^## Task ([1-9][0-9]*) - .+$")
    for line in text.splitlines():
        if not line.startswith("## Task "):
            continue
        match = pattern.fullmatch(line)
        if not match:
            malformed.append(line)
            continue
        headings.append(line)
        ordinals.append(int(match.group(1)))
    if malformed or ordinals != list(range(1, len(ordinals) + 1)) or not ordinals:
        fail(f"{subject} has no exact sequential `## Task N - title` manifest",
             {"ordinals": ordinals, "malformed": malformed})
    return headings


def git_object_name(name, subject):
    result = subprocess.run(
        ["git", "-C", project_root(), "rev-parse", "--verify", f"{name}^{{commit}}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(f"{subject} is absent or is not a commit", name)
    return result.stdout.strip()


def validate_built_task_success(entries, index, entry, built, task, task_sha, subject):
    data = note_data(entry)
    required = {"attempt", "lot", "sha", "gate"}
    allowed = required | {"retry", "success_recovery"}
    if not required.issubset(data) or not set(data).issubset(allowed) \
            or data.get("lot") != built or data.get("sha") != task_sha \
            or not construction_positive_integer(data.get("attempt")) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("gate"))):
        fail(f"{subject}'s stable task-{task} has malformed accepted-result authority", data)
    validate_attempt_succeeded_entry(entries, index, entry)
    return data


def validate_task_pass_completion(entries, before, data, subject, *, validate_origin=True):
    """Prove that a task-owned first pass follows one complete built lot."""
    built, commit = data["built"], data["commit"]
    if validate_origin:
        validate_construction_lot_origin(entries, before, built, subject)
    workspace_relative = PurePosixPath("plans", f"{built}-plan.md")
    workspace_plan = real_workspace_file(workspace_relative, f"{subject}'s current plan")
    with open(workspace_plan, "rb") as source:
        workspace_manifest = plan_task_manifest(source.read(), f"{subject}'s current plan")

    committed_relative = f"docs/plans/{os.path.basename(WORKSPACE)}-{built}-plan.md"
    committed = subprocess.run(
        ["git", "-C", project_root(), "show", f"{commit}:{committed_relative}"],
        capture_output=True,
    )
    if committed.returncode != 0:
        fail(f"{subject} has no committed plan for {built}", committed_relative)
    committed_manifest = plan_task_manifest(committed.stdout, f"{subject}'s committed plan")
    if committed_manifest != workspace_manifest:
        fail(f"{subject}'s workspace and committed task manifests differ",
             {"workspace": workspace_manifest, "committed": committed_manifest})

    final_task = len(workspace_manifest)
    if data["source_task"] != final_task:
        fail(f"{subject} does not follow the final task in {built}",
             {"source_task": data["source_task"], "final_task": final_task})

    ref_root = f"refs/bwr/{os.path.basename(WORKSPACE)}/{built}"
    base = git_object_name(f"{ref_root}/task-0", f"{subject}'s task-0 base")
    previous = base
    success_indexes = []
    for task in range(1, final_task + 1):
        task_sha = git_object_name(
            f"{ref_root}/task-{task}", f"{subject}'s stable task-{task} result",
        )
        ancestry = subprocess.run(
            ["git", "-C", project_root(), "merge-base", "--is-ancestor", previous, task_sha],
            capture_output=True,
        )
        if ancestry.returncode != 0 or previous == task_sha:
            fail(f"{subject}'s stable task-{task} omits its predecessor")
        matches = [(index, entry) for index, entry in enumerate(entries[:before])
                   if entry.get("kind") == "attempt.succeeded"
                   and entry.get("lot") == built and entry.get("task") == task
                   and note_data(entry).get("sha") == task_sha]
        if len(matches) != 1:
            fail(f"{subject}'s stable task-{task} has no one exact accepted result",
                 f"found {len(matches)}")
        success_index, success = matches[0]
        validate_built_task_success(
            entries, success_index, success, built, task, task_sha, subject,
        )
        success_indexes.append(success_index)
        previous = task_sha
    if success_indexes != sorted(success_indexes) or len(set(success_indexes)) != final_task:
        fail(f"{subject}'s accepted task results are not in strict task order")
    if previous != commit:
        fail(f"{subject}'s reviewed commit is not the final stable task result",
             {"stable": previous, "reviewed": commit})

    built_events = [(index, entry) for index, entry in enumerate(entries[:before])
                    if entry.get("kind") == "lot.built" and entry.get("lot") == built
                    and index > max(success_indexes)]
    if len(built_events) != 1:
        fail(f"{subject} has no one exact lot.built boundary after its completed tasks",
             f"found {len(built_events)}")
    built_data = note_data(built_events[0][1])
    if set(built_data) != {"tasks", "attempts"} \
            or built_data.get("tasks") != final_task \
            or not isinstance(built_data.get("attempts"), int) \
            or isinstance(built_data.get("attempts"), bool) \
            or built_data["attempts"] < final_task:
        fail(f"{subject}'s lot.built boundary contradicts its completed task manifest",
             built_data)


def validate_pass_opening_history(entries, opening_index, subject, *, validate_origin=True):
    opening = entries[opening_index]
    data = note_data(opening)
    if set(data) != PASS_OPENING_KEYS:
        fail(f"{subject} has a malformed current pass opening", data)
    built, commit, gate = data.get("built"), data.get("commit"), data.get("gate")
    if not isinstance(built, str) or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", built):
        fail(f"{subject} has a malformed built-lot pass identity", built)
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit) \
            or not isinstance(gate, str) or not re.fullmatch(r"[0-9a-f]{64}", gate):
        fail(f"{subject} has a malformed reviewed commit or gate identity")
    if data.get("source_scope") not in {"task", "baseline"} \
            or not isinstance(data.get("source_owner"), str) \
            or not re.fullmatch(r"[A-Za-z0-9._:/-]+", data["source_owner"]) \
            or not isinstance(data.get("source_task"), int) \
            or isinstance(data.get("source_task"), bool) \
            or not isinstance(data.get("source_attempt"), int) \
            or isinstance(data.get("source_attempt"), bool):
        fail(f"{subject} has a malformed pass source identity", data)
    exact_pass_gate_result(entries, opening_index, data, subject)
    if data["source_scope"] == "task":
        expected_owner = f"{built}/task-{data['source_task']}/attempt-{data['source_attempt']}"
        if data["source_lot"] != built or data["source_task"] < 1 \
                or data["source_attempt"] < 1 or data["source_owner"] != expected_owner:
            fail(f"{subject} does not consume the exact built task identity")
        validate_task_pass_completion(
            entries, opening_index, data, subject, validate_origin=validate_origin,
        )
        duplicates = [entry for entry in entries[:opening_index]
                      if entry.get("kind") == "pass.opened"
                      and note_data(entry).get("built") == built]
        if duplicates:
            fail(f"{subject} repeats a task-owned pass for {built}")
    else:
        if data["source_lot"] != "-" or data["source_task"] != 0 \
                or data["source_attempt"] != 0:
            fail(f"{subject} has a malformed baseline source identity")
        validate_baseline_pass_successor(
            entries, opening_index, built, commit, data["source_owner"], subject,
        )
    prior = [(index, entry) for index, entry in enumerate(entries[:opening_index])
             if entry.get("kind") == "pass.opened"]
    if prior and len(pass_closes(entries, prior[-1][0], opening_index)) != 1:
        fail(f"{subject} does not follow one exact closed prior pass")
    return data


def current_pass_opening(
    entries, before, subject, *, validate_origin=True, validate_context=False,
):
    openings = [(index, entry) for index, entry in enumerate(entries[:before])
                if entry.get("kind") == "pass.opened"]
    if not openings:
        fail(f"{subject} has no current product-review pass")
    opening_index, opening = openings[-1]
    data = validate_pass_opening_history(
        entries, opening_index, subject, validate_origin=validate_origin,
    )
    has_recovery = any(
        entry.get("kind") == "pass.opening.context.recovered"
        for entry in entries[opening_index + 1:before]
    )
    if validate_context or has_recovery:
        validate_pass_opening_context(entries, opening_index, before, subject)
    return opening_index, opening, data["built"], data["commit"]


def normalize_pass_opened(data, context):
    """A pass consumes one exact task success or amendment-owned successor."""
    if not isinstance(data, dict) or set(data) != {"built", "commit", "gate"}:
        fail("pass.opened must name one built lot, reviewed commit and accepted gate operation", data)
    built, commit, gate = data["built"], data["commit"], data["gate"]
    if not isinstance(built, str) or not re.fullmatch(r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", built):
        fail("pass.opened has an invalid built-lot identity", built)
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        fail("pass.opened has an invalid reviewed commit", commit)
    if not isinstance(gate, str) or not re.fullmatch(r"[0-9a-f]{64}", gate):
        fail("pass.opened has an invalid gate operation", gate)
    expected_context = pass_opening_context(data, "product-review")
    if {key: context[key] for key in CONTEXT_FIELDS if key in context} != expected_context:
        fail("pass.opened requires the exact PRODUCT REVIEW controller context",
             {key: context[key] for key in CONTEXT_FIELDS if key in context})
    entries = journal_entries()
    prior = [(index, entry) for index, entry in enumerate(entries)
             if entry.get("kind") == "pass.opened"]
    if prior and not pass_closes(entries, prior[-1][0], len(entries)):
        fail("pass.opened cannot replace an unfinished product-review pass")
    proof = subprocess.run(
        ["bash", GATE_CHECK, "require-pass", gate, commit], capture_output=True, text=True
    )
    if proof.returncode != 0:
        fail("pass.opened does not consume an accepted current full-gate proof", proof.stderr or proof.stdout)
    fields = proof.stdout.strip().split()
    if len(fields) != 5:
        fail("pass.opened received a malformed gate source proof", proof.stdout)
    scope, owner, source_lot, task, attempt = fields
    try:
        task, attempt = int(task), int(attempt)
    except ValueError:
        fail("pass.opened received a non-numeric gate source proof", fields)
    normalized = {
        **data, "source_scope": scope, "source_owner": owner,
        "source_lot": source_lot, "source_task": task, "source_attempt": attempt,
    }
    candidate = {
        "event": "note", "kind": "pass.opened", "data": normalized, **expected_context,
    }
    validate_pass_opening_history(entries + [candidate], len(entries), "the new product-review pass")
    return normalized


PRODUCT_RECEIPT_KEYS = REPORT_COUNT_KEYS | {"pass_commit", "pass_gate", "report_sha256"}


def product_completion_labels(mandate):
    path = os.path.join(WORKSPACE, "prompts", "product-review", f"lens-{mandate}.md")
    if os.path.islink(path) or not os.path.isfile(path):
        fail(f"the {mandate} lens prompt is absent or aliased")
    with open(path, encoding="utf-8") as source:
        text = source.read()
    header = re.search(r"^    COMPLETION \(([1-9][0-9]*) items\)$", text, re.MULTILINE)
    labels = re.findall(r"^    - \[ \] (.+?) —", text, re.MULTILINE)
    if not header or int(header.group(1)) != len(labels) or not labels:
        fail(f"the {mandate} lens has no one fixed completion block")
    return labels


def audit_product_completion(report_text, mandate):
    labels = product_completion_labels(mandate)
    nonempty = [line.strip() for line in report_text.splitlines() if line.strip()]
    if not nonempty or nonempty[0] != f"COMPLETION ({len(labels)} items)":
        fail(f"the {mandate} report does not open with its exact completion header")
    if len(nonempty) < len(labels) + 1:
        fail(f"the {mandate} report has an incomplete completion block")
    completed = []
    for offset, label in enumerate(labels, 1):
        line = nonempty[offset]
        prefix = f"- [x] {label} — "
        value = line[len(prefix):].strip() if line.startswith(prefix) else ""
        if not line.startswith(prefix) or not value \
                or value.startswith("<") and value.endswith(">") \
                or "NOT DONE" in line or "not done" in line.lower():
            fail(f"the {mandate} report did not complete its fixed lens duty", label)
        completed.append(line)
    if len(nonempty) > len(labels) + 1 \
            and re.match(r"^- \[[ xX]\] ", nonempty[len(labels) + 1]):
        fail(f"the {mandate} report added an item to its fixed completion block")
    return completed


def audit_product_findings(report_text, mandate):
    """Return exact severity counts for every structured finding outside code fences."""
    lines = report_text.splitlines()
    visible = []
    fence = None
    for number, line in enumerate(lines, 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            continue
        if fence is None:
            visible.append((number, line))

    headings = [position for position, (_, line) in enumerate(visible)
                if line.startswith("### ")]
    field_pattern = re.compile(r"^(Severity|Where|What|Why it matters|Proof):\s*(.*)$")
    if not headings:
        orphan = [(number, line) for number, line in visible if field_pattern.match(line)]
        if orphan:
            fail(f"the {mandate} report has finding fields without a finding heading", orphan)
        return {key: 0 for key in REPORT_COUNT_KEYS}

    first = headings[0]
    orphan = [(number, line) for number, line in visible[:first] if field_pattern.match(line)]
    if orphan:
        fail(f"the {mandate} report has finding fields before its first finding", orphan)

    counts = {key: 0 for key in REPORT_COUNT_KEYS}
    expected_fields = ["Severity", "Where", "What", "Why it matters", "Proof"]
    for offset, start in enumerate(headings):
        end = headings[offset + 1] if offset + 1 < len(headings) else len(visible)
        heading_number, heading = visible[start]
        if not heading[4:].strip():
            fail(f"the {mandate} report has an empty finding heading", heading_number)
        fields = []
        for number, line in visible[start + 1:end]:
            match = field_pattern.match(line)
            if match:
                fields.append((match.group(1), match.group(2).strip(), number))
        names = [name for name, _, _ in fields]
        if names != expected_fields or any(not value for _, value, _ in fields):
            fail(f"the {mandate} report finding at line {heading_number} has no exact field account",
                 {"expected": expected_fields, "actual": names})
        severity = fields[0][1]
        if severity not in {"CRITICAL", "IMPORTANT", "MINOR", "DECISION"}:
            fail(f"the {mandate} report finding at line {heading_number} has an unknown severity",
                 severity)
        counts[severity.lower()] += 1
    return counts


def product_report_relative(built, mandate):
    root = built.split(".", 1)[0]
    return PurePosixPath("reports", "product-review", root, f"{built}-{mandate}.md")


def validate_product_report_entry(entries, opening_index, index, entry, built, subject):
    mandate = entry.get("mandate")
    if mandate not in PRODUCT_REVIEW_MANDATES:
        fail(f"{subject} has an unknown product-review mandate", mandate)
    data = note_data(entry)
    opening_data = note_data(entries[opening_index])
    if set(data) != PRODUCT_RECEIPT_KEYS or any(
        not isinstance(data.get(key), int) or isinstance(data.get(key), bool) or data[key] < 0
        for key in REPORT_COUNT_KEYS
    ) or data.get("pass_commit") != opening_data["commit"] \
            or data.get("pass_gate") != opening_data["gate"] \
            or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("report_sha256"))):
        fail(f"{subject} has malformed or stale durable report proof", data)
    report = product_report_relative(built, mandate)
    path = real_workspace_file(report, f"{subject}'s report")
    with open(path, "rb") as source:
        payload = source.read()
    if sha256_bytes(payload) != data["report_sha256"]:
        fail(f"{subject}'s accepted report changed")
    try:
        report_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{subject}'s report is not valid UTF-8", exc)
    audit_product_completion(report_text, mandate)
    exact_counts = audit_product_findings(report_text, mandate)
    if any(data[key] != exact_counts[key] for key in REPORT_COUNT_KEYS):
        fail(f"{subject}'s typed counts contradict its exact report findings",
             {"receipt": {key: data[key] for key in REPORT_COUNT_KEYS},
              "report": exact_counts})
    if index <= opening_index:
        fail(f"{subject}'s report predates its pass")
    return data


def normalize_product_report(entries, data, mandate):
    if not isinstance(data, dict) or set(data) != REPORT_COUNT_KEYS or any(
        not isinstance(data.get(key), int) or isinstance(data.get(key), bool) or data[key] < 0
        for key in REPORT_COUNT_KEYS
    ):
        fail("a product-review receipt must carry exactly four typed finding counts", data)
    opening_index, opening, built, _ = current_pass_opening(
        entries, len(entries), "the new product-review receipt", validate_context=True,
    )
    if pass_closes(entries, opening_index, len(entries)):
        fail("a product-review receipt cannot enter a closed pass")
    previous = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1
    ) if entry.get("kind") == "report.received" and entry.get("mandate") == mandate]
    if previous:
        reopened = any(
            entry.get("kind") == "bound.spent" and entry.get("mandate") == mandate
            for entry in entries[previous[-1][0] + 1:]
        )
        if not reopened:
            fail(f"the {mandate} report already has a current accepted receipt")
    report = product_report_relative(built, mandate)
    path = real_workspace_file(report, f"the current {mandate} lens report")
    with open(path, "rb") as source:
        report_sha = sha256_bytes(source.read())
    opening_data = note_data(opening)
    normalized = {
        **data, "pass_commit": opening_data["commit"], "pass_gate": opening_data["gate"],
        "report_sha256": report_sha,
    }
    candidate = {
        "event": "note", "kind": "report.received", "mandate": mandate,
        "data": normalized,
    }
    validate_product_report_entry(
        entries + [candidate], opening_index, len(entries), candidate, built,
        f"the new {mandate} product-review receipt",
    )
    return normalized


def current_product_receipt(entries, opening_index, before, built, mandate, subject):
    receipts = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "report.received" and entry.get("mandate") == mandate]
    if not receipts:
        fail(f"{subject} has no accepted {mandate} report")
    index, receipt = receipts[-1]
    data = validate_product_report_entry(entries, opening_index, index, receipt, built, subject)
    return index, receipt, data


def product_verifier_identity(entries, before, mandate, subject):
    opening_index, opening, built, commit = current_pass_opening(entries, before, subject)
    if pass_closes(entries, opening_index, before):
        fail(f"{subject} belongs to a closed product-review pass")
    receipt_index, _, receipt_data = current_product_receipt(
        entries, opening_index, before, built, mandate, subject,
    )
    return opening_index, opening, built, commit, receipt_index, receipt_data


def validate_product_verifier_terminal(data, identity, receipt_data, mandate, subject):
    if set(data) == set(identity) | {"unusable"}:
        if data.get("unusable") not in CONSTRUCTION_UNUSABLE_RESULTS:
            fail(f"{subject} has an unknown unusable reason", data.get("unusable"))
        return "unusable"
    verdict_keys = {"confirmed", "disproved", "malformed", "claims"}
    if set(data) != set(identity) | verdict_keys:
        fail(f"{subject} has malformed identity or result", data)
    if any(not isinstance(data.get(key), int) or isinstance(data.get(key), bool)
           or data[key] < 0 for key in ("confirmed", "disproved", "malformed")):
        fail(f"the {mandate} finding-verifier has malformed verdict counts", data)
    claims = data.get("claims")
    expected_count = sum(receipt_data[key] for key in REPORT_COUNT_KEYS)
    if not isinstance(claims, list) or len(claims) != expected_count:
        fail(f"the {mandate} finding-verifier lacks one result per accepted report claim")
    expected_ids = [f"F{ordinal}" for ordinal in range(1, expected_count + 1)]
    actual_ids = []
    totals = {"confirmed": 0, "disproved": 0, "malformed": 0}
    kinds = {"correction": 0, "decision": 0}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "kind", "verdict"} \
                or claim.get("kind") not in kinds or claim.get("verdict") not in totals:
            fail(f"the {mandate} finding-verifier has a malformed claim", claim)
        actual_ids.append(claim["id"])
        totals[claim["verdict"]] += 1
        kinds[claim["kind"]] += 1
    if actual_ids != expected_ids or totals != {key: data[key] for key in totals} \
            or kinds["decision"] != receipt_data["decision"] \
            or kinds["correction"] != expected_count - receipt_data["decision"]:
        fail(f"the {mandate} finding-verifier result contradicts its accepted report")
    return "complete"


def product_verifier_calls(entries, receipt_index, mandate, identity, receipt_data, subject):
    events = [entry for entry in entries[receipt_index + 1:]
              if entry.get("kind") == "finding-verifier"
              and entry.get("mandate") == mandate
              and entry.get("event") in {"subagent-started", "subagent-ended"}]
    calls = []
    expecting = "start"
    complete = False
    for entry in events:
        if complete:
            fail(f"{subject} continues after its complete verifier result")
        if expecting == "start":
            if entry.get("event") != "subagent-started" or note_data(entry) != identity:
                fail(f"{subject} has a contradictory physical-call opening")
            calls.append({"start": entry, "end": None, "terminal": None})
            expecting = "end"
            continue
        if entry.get("event") != "subagent-ended" \
                or any(note_data(entry).get(key) != value for key, value in identity.items()):
            fail(f"{subject} changes its physical-call identity")
        terminal = validate_product_verifier_terminal(
            note_data(entry), identity, receipt_data, mandate, subject,
        )
        calls[-1]["end"] = entry
        calls[-1]["terminal"] = terminal
        expecting = "start"
        complete = terminal == "complete"
    return calls


def validate_product_finding_verifier(event, data, mandate, entries=None):
    if mandate not in PRODUCT_REVIEW_MANDATES:
        fail("a product finding-verifier has no fixed lens mandate", mandate)
    identity_keys = {"pass_commit", "pass_gate", "report_sha256"}
    if not isinstance(data, dict) or event == "subagent-started" \
            and set(data) != identity_keys:
        fail(f"{event} product finding-verifier has malformed identity or result", data)
    if entries is None:
        entries = journal_entries()
    _, opening, _, commit, receipt_index, receipt_data = product_verifier_identity(
        entries, len(entries), mandate, f"the {mandate} finding-verifier",
    )
    identity = {
        "pass_commit": commit, "pass_gate": note_data(opening)["gate"],
        "report_sha256": receipt_data["report_sha256"],
    }
    if any(data.get(key) != value for key, value in identity.items()):
        fail(f"the {mandate} finding-verifier does not consume the current report generation",
             {"expected": identity, "actual": data})
    calls = product_verifier_calls(
        entries, receipt_index, mandate, identity, receipt_data,
        f"the {mandate} finding-verifier",
    )
    if event == "subagent-started":
        if calls and (calls[-1]["end"] is None or calls[-1]["terminal"] == "complete"):
            fail(f"the current {mandate} report cannot open another finding-verifier call")
        return
    if not calls or calls[-1]["end"] is not None:
        fail(f"the {mandate} finding-verifier result has no one exact open bracket")
    if note_data(calls[-1]["start"]) != identity:
        fail(f"the {mandate} finding-verifier result changes its opening identity")
    validate_product_verifier_terminal(
        data, identity, receipt_data, mandate, f"the {mandate} finding-verifier",
    )


def pass_verifier_state(commit, report_name):
    entries = journal_entries()
    opening_index, opening, built, current_commit = current_pass_opening(
        entries, len(entries), "the physical finding-verifier",
    )
    if commit != current_commit or pass_closes(entries, opening_index, len(entries)):
        fail("verify-open.sh did not receive the current open pass commit", commit)
    matches = [mandate for mandate in PRODUCT_REVIEW_MANDATES
               if report_name == f"{built}-{mandate}.md"]
    if len(matches) != 1:
        fail("verify-open.sh did not receive the current pass report name", report_name)
    mandate = matches[0]
    receipt_index, _, receipt_data = current_product_receipt(
        entries, opening_index, len(entries), built, mandate,
        "the physical finding-verifier",
    )
    identity = {
        "pass_commit": commit, "pass_gate": note_data(opening)["gate"],
        "report_sha256": receipt_data["report_sha256"],
    }
    calls = product_verifier_calls(
        entries, receipt_index, mandate, identity, receipt_data,
        "the physical finding-verifier",
    )
    if not calls or calls[-1]["end"] is not None:
        fail("verify-open.sh has no one exact live finding-verifier bracket")


def validate_review_receipts(entries, opening_index, before, built, subject):
    """Prove every report and return its durable confirmed source identities."""
    confirmed_total = 0
    confirmed_corrections = []
    for mandate in PRODUCT_REVIEW_MANDATES:
        receipt_index, _, counts = current_product_receipt(
            entries, opening_index, before, built, mandate, subject,
        )
        reopened = [entry for entry in entries[receipt_index + 1:before]
                    if entry.get("kind") == "bound.spent"
                    and entry.get("mandate") == mandate
                    and isinstance(entry.get("text"), str)
                    and (
                        entry["text"].startswith("malformed block returned")
                        or entry["text"].startswith("malformed finding returned:")
                        or entry["text"].startswith("report returned whole for recalibration")
                    )]
        if reopened:
            fail(f"{subject} has a reopened {mandate} report without a fresh receipt")
        opening_data = note_data(entries[opening_index])
        identity = {
            "pass_commit": opening_data["commit"], "pass_gate": opening_data["gate"],
            "report_sha256": counts["report_sha256"],
        }
        calls = product_verifier_calls(
            entries[:before], receipt_index, mandate, identity, counts,
            f"{subject}'s {mandate} finding-verifier",
        )
        if not calls or calls[-1]["terminal"] != "complete":
            fail(f"{subject} has no one settled {mandate} finding-verifier result")
        verdict = note_data(calls[-1]["end"])
        confirmed_total += verdict["confirmed"]
        confirmed_corrections.extend(
            f"{mandate}/{claim['id']}"
            for claim in verdict["claims"]
            if claim["kind"] == "correction" and claim["verdict"] == "confirmed"
        )
    return {
        "confirmed_total": confirmed_total,
        "confirmed_corrections": confirmed_corrections,
    }


def validate_current_direct_terminals(entries, before, subject):
    state = global_answer_state(entries, before)
    for ruling, answer in state.items():
        if not re.fullmatch(r"R[1-9][0-9]*", ruling) or answer.get("status") != "active":
            continue
        state_kind, state_ref = latest_owner_generation(entries, before, ruling)
        if state_kind == "ruling.ready":
            authority = exact_matches(
                entries[:before],
                lambda entry: entry.get("kind") == state_kind
                and note_data(entry).get("ruling") == ruling,
                f"{subject}'s current authority for {ruling}",
            )
            terminal_authority = state_kind, state_ref, authority_artifact_sha(authority)
        elif state_kind == "decision.conflict.ready":
            match = re.fullmatch(r"(.+)/C([1-9][0-9]*)", str(state_ref))
            if match is None:
                fail(f"{subject}'s current conflict authority for {ruling} is malformed", state_ref)
            owner, conflict = match.groups()
            authority = exact_matches(
                entries[:before],
                lambda entry: entry.get("kind") == state_kind
                and note_data(entry).get("owner") == owner
                and note_data(entry).get("conflict") == int(conflict),
                f"{subject}'s current authority for {ruling}",
            )
            terminal_authority = state_kind, state_ref, authority_artifact_sha(authority)
        elif state_kind == "decision.recheck.completed":
            recheck = exact_matches(
                entries[:before],
                lambda entry: entry.get("kind") == state_kind
                and note_data(entry).get("commit_op") == state_ref
                and note_data(entry).get("accepted") is True
                and note_data(entry).get("missing") == []
                and any(isinstance(action, dict) and action.get("answer") == ruling
                        for action in (note_data(entry).get("actions") or [])),
                f"{subject}'s current recheck for {ruling}",
            )
            recheck_data = note_data(recheck)
            recheck_index = next(index for index, entry in enumerate(entries[:before])
                                 if entry is recheck)
            if recheck_data.get("owner") == ruling:
                validate_recheck_artifact(entries[:before], recheck_index, recheck)
                commit = exact_matches(
                    entries[:recheck_index],
                    lambda entry: entry.get("kind") == "spec.committed"
                    and note_data(entry).get("ruling") == ruling
                    and note_data(entry).get("op") == state_ref
                    and note_data(entry).get("sha") == recheck_data.get("sha"),
                    f"{subject}'s current recheck commit for {ruling}",
                )
                commit_data = note_data(commit)
                terminal_authority = (
                    commit_data.get("state_kind"), commit_data.get("state_ref"),
                    commit_data.get("artifact_sha256"),
                )
            elif recheck_data.get("owner") == "spec-loop":
                try:
                    validate_spec_loop_generation(entries[:before], recheck_index)
                except AuthorityPrecedenceError as exc:
                    fail(f"{subject}'s current SPEC-loop recheck for {ruling} is invalid", exc)
                validate_spec_loop_artifact(recheck)
                members = [member for member in (recheck_data.get("rulings") or [])
                           if isinstance(member, dict) and member.get("ruling") == ruling]
                if len(members) != 1:
                    fail(f"{subject}'s current SPEC-loop recheck for {ruling} is incomplete")
                terminal_authority = tuple_from(members[0])
            else:
                fail(f"{subject}'s current recheck for {ruling} has an unknown owner",
                     recheck_data.get("owner"))
            if terminal_authority is None or not all(terminal_authority):
                fail(f"{subject}'s current recheck for {ruling} has no terminal authority")
        else:
            fail(f"{subject}'s current authority for {ruling} has an unknown generation", state_kind)
        authority_kind, authority_ref, authority_sha = terminal_authority
        terminals = [entry for entry in entries[:before]
                     if entry.get("kind") == "ruling.applied"
                     and note_data(entry).get("ruling") == ruling
                     and note_data(entry).get("route") == answer.get("route")
                     and note_data(entry).get("authority_kind") == authority_kind
                     and note_data(entry).get("authority_ref") == authority_ref
                     and note_data(entry).get("authority_sha256") == authority_sha]
        if len(terminals) != 1:
            fail(f"{subject} requires one current terminal for {ruling}", f"found {len(terminals)}")


def validate_zero_close_batches(entries, opening_index, before, verifier_confirmed, subject):
    opened = {note_data(entry).get("batch") for entry in entries[:before]
              if entry.get("kind") == "decision.batch.opened"}
    closed = {note_data(entry).get("batch") for entry in entries[:before]
              if entry.get("kind") == "decision.batch.closed"}
    current_batches = {batch for batch in opened - closed
                       if isinstance(batch, int) and not isinstance(batch, bool)}
    source_batches = {note_data(entry).get("batch") for entry in entries[opening_index + 1:before]
                      if entry.get("kind") == "decision.batch.opened"}
    if verifier_confirmed["confirmed_total"] and not source_batches:
        fail(f"{subject} cannot close clean while current verifier findings lack a durable batch")

    for batch in sorted(current_batches):
        state = batch_state(entries[:before], batch)
        for identity, verdict in state["items"].items():
            if identity.startswith("F") and verdict == "confirmed":
                fail(f"{subject} still carries confirmed correction B{batch}/{identity}")
        for decision, answer in state["answers"].items():
            if answer["status"] == "superseded":
                continue
            if answer["route"] not in {"closed", "spec-in-place"}:
                fail(f"{subject} still carries correction route B{batch}/{decision}", answer["route"])
            terminals = [(index, entry) for index, entry in enumerate(entries[:before])
                         if index > answer["state_index"]
                         and entry.get("kind") == "ruling.applied"
                         and note_data(entry).get("batch") == batch
                         and note_data(entry).get("decision") == decision]
            if len(terminals) != 1:
                fail(f"{subject} requires one current terminal for B{batch}/{decision}")
            terminal_index, terminal = terminals[0]
            validate_batch_applied(
                entries[:terminal_index], note_data(terminal), reject_duplicate=False,
            )


def required_positive_carries(entries, before, subject):
    """Return every current batch item that the next confirmed file must carry."""
    opened = {note_data(entry).get("batch") for entry in entries[:before]
              if entry.get("kind") == "decision.batch.opened"}
    closed = {note_data(entry).get("batch") for entry in entries[:before]
              if entry.get("kind") == "decision.batch.closed"}
    required_all = set()
    for batch in sorted(batch for batch in opened - closed
                        if isinstance(batch, int) and not isinstance(batch, bool)):
        state = batch_state(entries[:before], batch)
        required = {(batch, identity) for identity, verdict in state["items"].items()
                    if identity.startswith("F") and verdict == "confirmed"}
        for decision, answer in state["answers"].items():
            if answer["status"] == "superseded":
                continue
            if answer["route"] in {"sublot", "amendment"}:
                required.add((batch, decision))
            if answer["route"] == "sublot":
                continue
            terminals = [(index, entry) for index, entry in enumerate(entries[:before])
                         if index > answer["state_index"]
                         and entry.get("kind") == "ruling.applied"
                         and note_data(entry).get("batch") == batch
                         and note_data(entry).get("decision") == decision]
            if len(terminals) != 1:
                fail(f"{subject} requires one current terminal for B{batch}/{decision}")
            terminal_index, terminal = terminals[0]
            validate_batch_applied(
                entries[:terminal_index], note_data(terminal), reject_duplicate=False,
            )
        required_all.update(required)
    return required_all


def validate_positive_close_batches(entries, before, built, subject):
    required = required_positive_carries(entries, before, subject)
    carries = confirmed_carries(built)
    missing = required - carries
    if missing:
        fail(f"{subject}'s confirmed artifact omits current batch work",
             ", ".join(f"B{batch}/{item}" for batch, item in sorted(missing)))


def source_identity_key(identity):
    mandate, ordinal = identity.split("/F", 1)
    return PRODUCT_REVIEW_MANDATES.index(mandate), int(ordinal)


def carry_identity_key(identity):
    match = re.fullmatch(r"B([1-9][0-9]*)/([FD])([1-9][0-9]*)", identity)
    return int(match.group(1)), {"F": 0, "D": 1}[match.group(2)], int(match.group(3))


def validate_allocation_account(entries, opening_index, before, built, data, subject):
    """Bind one allocation to the complete fresh-source and carried-work dedupe."""
    if not isinstance(data, dict) or set(data) != {"built", "items", "refuted"} \
            or data.get("built") != built:
        fail(f"{subject} has no exact built-lot dedupe account", data)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        fail(f"{subject} has an empty or malformed dedupe account")

    all_confirmed_sources = set(validate_review_receipts(
        entries, opening_index, before, built, subject,
    )["confirmed_corrections"])
    refuted = data.get("refuted")
    if not isinstance(refuted, list) or any(
        not isinstance(identity, str) or not re.fullmatch(
            rf"(?:{'|'.join(PRODUCT_REVIEW_MANDATES)})/F[1-9][0-9]*", identity
        ) for identity in refuted
    ) \
            or refuted != sorted(set(refuted), key=source_identity_key):
        fail(f"{subject} has no canonical source-refutation index", refuted)
    raw_refutations = [
        note_data(entry).get("source")
        for entry in entries[opening_index + 1:before]
        if entry.get("kind") == "decision.refuted" and "source" in note_data(entry)
    ]
    if any(not isinstance(identity, str) or not re.fullmatch(
        rf"(?:{'|'.join(PRODUCT_REVIEW_MANDATES)})/F[1-9][0-9]*", identity
    ) for identity in raw_refutations) or len(raw_refutations) != len(set(raw_refutations)):
        fail(f"{subject} has a malformed or duplicate durable source refutation")
    durable_refutations = set(raw_refutations)
    if set(refuted) != durable_refutations or not durable_refutations.issubset(all_confirmed_sources):
        fail(
            f"{subject}'s source-refutation index has no exact durable proof",
            {"account": refuted, "journal": sorted(durable_refutations)},
        )
    expected_sources = all_confirmed_sources - durable_refutations
    expected_carries = {
        f"B{batch}/{item}"
        for batch, item in required_positive_carries(entries, before, subject)
    }
    seen_sources = set()
    seen_carries = set()
    account = {}
    for ordinal, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != {"id", "sources", "carries"} \
                or item.get("id") != f"F{ordinal}":
            fail(f"{subject} has a malformed or non-contiguous dedupe item", item)
        sources, carries = item.get("sources"), item.get("carries")
        if not isinstance(sources, list) or not isinstance(carries, list) \
                or not sources and not carries:
            fail(f"{subject}'s {item['id']} has no source identity")
        if any(not isinstance(identity, str) or not re.fullmatch(
            rf"(?:{'|'.join(PRODUCT_REVIEW_MANDATES)})/F[1-9][0-9]*", identity
        ) for identity in sources):
            fail(f"{subject}'s {item['id']} has a malformed fresh source", sources)
        if any(not isinstance(identity, str) or not re.fullmatch(
            r"B[1-9][0-9]*/[FD][1-9][0-9]*", identity
        ) for identity in carries):
            fail(f"{subject}'s {item['id']} has a malformed carried source", carries)
        if sources != sorted(set(sources), key=source_identity_key):
            fail(f"{subject}'s {item['id']} fresh sources are not one canonical set", sources)
        if carries != sorted(set(carries), key=carry_identity_key):
            fail(f"{subject}'s {item['id']} carried sources are not one canonical set", carries)
        repeated_sources = seen_sources.intersection(sources)
        repeated_carries = seen_carries.intersection(carries)
        if repeated_sources or repeated_carries:
            fail(
                f"{subject} accounts for one source more than once",
                sorted(repeated_sources | repeated_carries),
            )
        seen_sources.update(sources)
        seen_carries.update(carries)
        account[item["id"]] = {"sources": sources, "carries": carries}

    if seen_sources != expected_sources:
        fail(
            f"{subject} does not account for every confirmed fresh correction exactly once",
            {"missing": sorted(expected_sources - seen_sources, key=source_identity_key),
             "unexpected": sorted(seen_sources - expected_sources, key=source_identity_key)},
        )
    if seen_carries != expected_carries:
        fail(
            f"{subject} does not account for every current carried item exactly once",
            {"missing": sorted(expected_carries - seen_carries, key=carry_identity_key),
             "unexpected": sorted(seen_carries - expected_carries, key=carry_identity_key)},
        )
    return account


def validate_source_refutation(entries, data, text, subject):
    if set(data) != {"source"} or not isinstance(text, str) or not text:
        fail(f"{subject} must name one source and its exact observation", data)
    opening_index, _, built, _ = current_pass_opening(entries, len(entries), subject)
    receipts = validate_review_receipts(entries, opening_index, len(entries), built, subject)
    source = data.get("source")
    if source not in receipts["confirmed_corrections"]:
        fail(f"{subject} names no confirmed fresh correction", source)
    if any(entry.get("kind") == "decision.refuted"
           and note_data(entry).get("source") == source
           for entry in entries[opening_index + 1:]):
        fail(f"{subject} repeats the refutation of {source}")


def validate_allocation_identity(entries, opening_index, before, built, lot, subject):
    root = built.split(".", 1)[0]
    match = re.fullmatch(rf"{re.escape(root)}\.([1-9][0-9]*)", str(lot))
    if not match:
        fail(f"{subject} has an allocation outside its root lot", lot)
    used = [int(opened.group(1)) for entry in entries[:opening_index]
            if entry.get("kind") == "sublot.opened"
            and (opened := re.fullmatch(rf"{re.escape(root)}\.([1-9][0-9]*)", str(entry.get("text"))))]
    if int(match.group(1)) != (max(used, default=0) + 1):
        fail(f"{subject} does not allocate the next available sub-lot", lot)
    return root


def validate_sublot_allocation(entries, data, text, subject, *, validate_origin=True):
    before = len(entries)
    opening_index, _, built, _ = current_pass_opening(
        entries, before, subject, validate_origin=validate_origin,
    )
    if any(entry.get("kind") == "pass.closed" for entry in entries[opening_index + 1:before]):
        fail(f"{subject} cannot follow a closed pass")
    if any(entry.get("kind") == "sublot.allocated" for entry in entries[opening_index + 1:before]):
        fail(f"{subject}'s current pass already has an allocation")
    try:
        validate_global_authority_precedence(entries[:before])
    except AuthorityPrecedenceError as exc:
        fail(f"an unfinished global product-authority boundary outranks {subject}", exc)
    validate_current_direct_terminals(entries, before, subject)
    validate_allocation_identity(entries, opening_index, before, built, text, subject)
    validate_allocation_account(entries, opening_index, before, built, data, subject)


def validate_sublot_opening(entries, data, text, subject):
    """Prove that one sub-lot consumes its exact closed positive review pass."""
    if data is not None:
        fail(f"{subject} takes no structured data", data)
    if not isinstance(text, str) or not re.fullmatch(
        r"lot-[1-9][0-9]*\.[1-9][0-9]*", text,
    ):
        fail(f"{subject} has no exact sub-lot identity", text)
    if any(entry.get("kind") == "sublot.opened" and entry.get("text") == text
           for entry in entries):
        fail(f"{subject} repeats the opening of {text}")

    close = current_pass_close(
        entries, subject, validate_origin=False, validate_current_gate=False,
    )
    opening_index, _, close_index, _, confirmed, built = close
    if confirmed < 1:
        fail(f"{subject} does not consume a positive product-review pass close", confirmed)
    allocations = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:close_index], opening_index + 1,
    ) if entry.get("kind") == "sublot.allocated" and entry.get("text") == text]
    if len(allocations) != 1:
        fail(f"{subject} has no one exact allocation for {text}", f"found {len(allocations)}")
    allocation_index, allocation = allocations[0]
    validate_sublot_allocation(
        entries[:allocation_index], note_data(allocation), allocation.get("text"), subject,
        validate_origin=False,
    )
    if note_data(allocation).get("built") != built:
        fail(f"{subject}'s allocation belongs to another reviewed lot", built)

    opened_batches = {note_data(entry).get("batch") for entry in entries
                      if entry.get("kind") == "decision.batch.opened"}
    closed_batches = {note_data(entry).get("batch") for entry in entries
                      if entry.get("kind") == "decision.batch.closed"}
    unfinished = sorted(
        batch for batch in opened_batches - closed_batches
        if isinstance(batch, int) and not isinstance(batch, bool)
    )
    if unfinished:
        fail(f"{subject} still has open decision-batch routing", unfinished)
    return close


def construction_lot_origin_account(entries, before, lot, subject):
    """Return one validated sub-lot opening and its exact source pass close."""
    if not isinstance(lot, str) or not re.fullmatch(
        r"lot-[1-9][0-9]*(?:\.[1-9][0-9]*)?", lot,
    ):
        fail(f"{subject} has a malformed lot identity", lot)
    if "." not in lot:
        return "root", None
    cache_key = ("construction-lot-origin", before, lot)
    if COMMAND_VALIDATION_CACHE is not None and cache_key in COMMAND_VALIDATION_CACHE:
        return COMMAND_VALIDATION_CACHE[cache_key]
    openings = [(index, entry) for index, entry in enumerate(entries[:before])
                if entry.get("kind") == "sublot.opened" and entry.get("text") == lot]
    if len(openings) != 1:
        fail(
            f"{subject} requires one exact sub-lot `sublot.opened` terminal",
            f"{lot}: found {len(openings)}",
        )
    opening_index, opening = openings[0]
    close = validate_sublot_opening(
        entries[:opening_index], opening.get("data"), opening.get("text"), subject,
    )
    result = journal_line_proof(opening_index), close
    if COMMAND_VALIDATION_CACHE is not None:
        COMMAND_VALIDATION_CACHE[cache_key] = result
    return result


def validate_construction_lot_origin(entries, before, lot, subject):
    """Authenticate the PRODUCT REVIEW terminal that created a construction sub-lot."""
    return construction_lot_origin_account(entries, before, lot, subject)[0]


def confirmed_account(path, subject):
    account = {}
    current = None
    with open(path, encoding="utf-8") as source:
        for raw in source:
            heading = re.match(r"^## (F[1-9][0-9]*)\b", raw)
            if heading:
                current = heading.group(1)
                if current in account:
                    fail(f"{subject} repeats confirmed entry {current}")
                account[current] = {"sources": None, "carries": None}
                continue
            if current is None:
                continue
            for field, prefix in (("sources", "Sources:"), ("carries", "Carries:")):
                if not raw.startswith(prefix):
                    continue
                if account[current][field] is not None:
                    fail(f"{subject}'s {current} repeats {prefix[:-1]}")
                tokens = [token.strip() for token in raw.removeprefix(prefix).split(",")
                          if token.strip()]
                if field == "sources":
                    if any(not re.fullmatch(
                        rf"(?:{'|'.join(PRODUCT_REVIEW_MANDATES)})/F[1-9][0-9]*", token
                    ) for token in tokens):
                        fail(f"{subject}'s {current} has a malformed Sources line", tokens)
                    account[current][field] = tokens
                else:
                    normalized = []
                    for token in tokens:
                        match = re.fullmatch(
                            r"(?:batch\s+|B)([1-9][0-9]*)/([FD][1-9][0-9]*)", token,
                        )
                        if not match:
                            fail(f"{subject}'s {current} has a malformed Carries line", token)
                        normalized.append(f"B{match.group(1)}/{match.group(2)}")
                    account[current][field] = normalized
    for item in account.values():
        item["sources"] = item["sources"] or []
        item["carries"] = item["carries"] or []
    return account


def covers_values(plan):
    """Return only the logical lines in the document's one Covers block."""
    values = []
    active = False
    for raw in plan.splitlines():
        if raw.startswith("Covers:"):
            if active or values:
                return None
            active = True
            value = raw.removeprefix("Covers:").strip()
            if value:
                values.append(value)
            continue
        if not active:
            continue
        if raw.startswith((" ", "\t")):
            value = raw.strip()
            if value:
                values.append(value)
            continue
        break
    return values if active else None


def validate_positive_close_artifacts(entries, opening_index, before, built, confirmed, subject):
    allocations = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:before], opening_index + 1
    ) if entry.get("kind") == "sublot.allocated"]
    if len(allocations) != 1:
        fail(f"{subject} requires one current sub-lot allocation", f"found {len(allocations)}")
    _, allocation = allocations[0]
    lot = allocation.get("text")
    root = validate_allocation_identity(entries, opening_index, before, built, lot, subject)
    expected_account = validate_allocation_account(
        entries, opening_index, before, built, note_data(allocation), subject,
    )

    confirmed_relative = PurePosixPath("reports", "product-review", root, f"{built}-confirmed.md")
    confirmed_path = real_workspace_file(confirmed_relative, f"{subject}'s confirmed artifact")
    actual_account = confirmed_account(confirmed_path, f"{subject}'s confirmed artifact")
    finding_ids = [int(identity[1:]) for identity in actual_account]
    if finding_ids != list(range(1, confirmed + 1)):
        fail(f"{subject}'s confirmed artifact does not match its confirmed count", finding_ids)
    if actual_account != expected_account:
        fail(
            f"{subject}'s confirmed artifact does not consume its allocated dedupe account",
            {"allocated": expected_account, "confirmed": actual_account},
        )

    plan_relative = PurePosixPath("plans", f"{lot}-plan.md")
    plan_path = real_workspace_file(plan_relative, f"{subject}'s allocated sub-lot plan")
    with open(plan_path, encoding="utf-8") as source:
        plan = source.read()
    values = covers_values(plan)
    valid_pointers = {
        str(confirmed_relative), os.path.basename(confirmed_path), confirmed_path,
    }
    if values is None or len(valid_pointers.intersection(values)) != 1:
        fail(f"{subject}'s allocated plan does not name its confirmed source", confirmed_relative)
    return lot


def validate_current_technical_gate(opening, subject):
    """Modern pass generations cannot close over a later un-gated commit."""
    if "gate" not in note_data(opening):
        return  # legacy unit fixtures predate the pass-opening gate capability
    proof = subprocess.run(
        ["bash", GATE_CHECK, "require-current"], capture_output=True, text=True
    )
    if proof.returncode != 0:
        fail(f"{subject} has no green full-gate proof for the current HEAD and gate.md",
             proof.stderr or proof.stdout)


def validate_pass_close(
    entries, data, subject, *, validate_origin=True, validate_current_gate=True,
):
    before = len(entries)
    opening_index, opening, built, _ = current_pass_opening(
        entries, before, subject, validate_origin=validate_origin,
        validate_context=validate_current_gate,
    )
    if any(entry.get("kind") == "pass.closed" for entry in entries[opening_index + 1:before]):
        fail(f"{subject}'s current pass is already closed")
    if any(entry.get("kind") == "lot.delivered" for entry in entries[opening_index + 1:before]):
        fail(f"{subject}'s current pass is already delivered")

    if data == {"voided": True}:
        amendments = [entry for entry in entries[opening_index + 1:before]
                      if entry.get("kind") == "amendment.opened"
                      and note_data(entry).get("origin") == "product-review"
                      and note_data(entry).get("built") == built
                      and isinstance(note_data(entry).get("amendment"), int)
                      and not isinstance(note_data(entry).get("amendment"), bool)
                      and note_data(entry).get("amendment") > 0]
        if len(amendments) != 1:
            fail(f"{subject} has no one exact product-review amendment opening")
        return opening_index, opening, None, built

    if set(data) != {"confirmed"}:
        fail(f"{subject} has a malformed ordinary close payload", data)
    confirmed = data.get("confirmed")
    if not isinstance(confirmed, int) or isinstance(confirmed, bool) or confirmed < 0:
        fail(f"{subject} has an invalid confirmed count", confirmed)
    if any(entry.get("kind") == "amendment.opened"
           and note_data(entry).get("origin") == "product-review"
           and note_data(entry).get("built") == built
           for entry in entries[opening_index + 1:before]):
        fail(f"{subject} must void the pass owned by its product-review amendment")
    if any(entry.get("kind") == "sublot.opened" for entry in entries[opening_index + 1:before]):
        fail(f"{subject} cannot close after its sub-lot already opened")
    if validate_current_gate:
        validate_current_technical_gate(opening, subject)
    try:
        validate_global_authority_precedence(entries[:before])
    except AuthorityPrecedenceError as exc:
        fail(f"an unfinished global product-authority boundary outranks {subject}", exc)
    verifier_confirmed = validate_review_receipts(entries, opening_index, before, built, subject)
    validate_current_direct_terminals(entries, before, subject)
    if confirmed == 0:
        if any(entry.get("kind") == "sublot.allocated"
               for entry in entries[opening_index + 1:before]):
            fail(f"{subject} cannot close clean after allocating a sub-lot")
        validate_zero_close_batches(entries, opening_index, before, verifier_confirmed, subject)
    else:
        validate_positive_close_artifacts(
            entries, opening_index, before, built, confirmed, subject,
        )
        validate_positive_close_batches(entries, before, built, subject)
    return opening_index, opening, confirmed, built


def current_pass_close(
    entries, subject, *, validate_origin=True, validate_current_gate=True,
):
    opening_index, opening, built, _ = current_pass_opening(
        entries, len(entries), subject, validate_origin=validate_origin,
        validate_context=validate_current_gate,
    )
    closes = [(index, entry) for index, entry in enumerate(
        entries[opening_index + 1:], opening_index + 1
    ) if entry.get("kind") == "pass.closed"]
    if len(closes) != 1:
        fail(f"{subject} requires one current pass close", f"found {len(closes)}")
    close_index, close = closes[0]
    _, _, confirmed, _ = validate_pass_close(
        entries[:close_index], note_data(close), subject,
        validate_origin=validate_origin,
        validate_current_gate=validate_current_gate,
    )
    if confirmed is None:
        fail(f"{subject} has no ordinary confirmed-count pass close")
    return opening_index, opening, close_index, close, confirmed, built


def validate_lot_delivered(entries, data):
    subject = "a lot delivery"
    if set(data) != {"sha", "passes"}:
        fail(f"{subject} has a malformed payload", data)
    sha, passes = data.get("sha"), data.get("passes")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        fail(f"{subject} has a malformed reviewed SHA", sha)
    if not isinstance(passes, int) or isinstance(passes, bool) or passes < 1:
        fail(f"{subject} has no positive pass count", passes)

    opening_index, opening, close_index, _, confirmed, built = current_pass_close(entries, subject)
    opening_data = note_data(opening)
    if confirmed != 0:
        fail(f"{subject} requires an exact clean current pass close", confirmed)
    if sha != opening_data.get("commit"):
        fail(f"{subject} does not name the current pass's reviewed commit", opening_data.get("commit"))
    if any(entry.get("kind") == "lot.delivered" for entry in entries[opening_index + 1:]):
        fail(f"{subject} is already recorded for the current pass")
    if any(entry.get("kind") == "pass.opened" for entry in entries[close_index + 1:]):
        fail(f"{subject} uses a stale pass generation")
    validate_current_technical_gate(opening, subject)

    opened_batches = {note_data(entry).get("batch") for entry in entries
                      if entry.get("kind") == "decision.batch.opened"}
    closed_batches = {note_data(entry).get("batch") for entry in entries
                      if entry.get("kind") == "decision.batch.closed"}
    unfinished_batches = sorted(batch for batch in opened_batches - closed_batches
                                if isinstance(batch, int) and not isinstance(batch, bool))
    if unfinished_batches:
        fail(f"{subject} still has open decision-batch work", unfinished_batches)

    root = built.split(".", 1)[0]
    completed = 0
    active_root = None
    for entry in entries:
        if entry.get("kind") == "pass.opened":
            candidate = note_data(entry).get("built")
            active_root = candidate.split(".", 1)[0] if isinstance(candidate, str) else None
        elif entry.get("kind") == "pass.closed" and active_root == root:
            close_data = note_data(entry)
            confirmed_count = close_data.get("confirmed")
            if isinstance(confirmed_count, int) and not isinstance(confirmed_count, bool) \
                    and confirmed_count >= 0 and close_data.get("voided") is not True:
                completed += 1
    if passes != completed:
        fail(f"{subject} has the wrong completed-pass count", {"recorded": passes, "actual": completed})


def sublot_close_proof(notes, lot, subject):
    if not isinstance(lot, str) or not re.fullmatch(r"lot-[1-9][0-9]*\.[1-9][0-9]*", lot):
        fail(f"{subject} has a malformed sub-lot identity", lot)
    opening_index, opening, close_index, close, confirmed, built = current_pass_close(notes, subject)
    allocations = [(index, entry) for index, entry in enumerate(
        notes[opening_index + 1:close_index], opening_index + 1
    ) if entry.get("kind") == "sublot.allocated"]
    if len(allocations) != 1 or allocations[0][1].get("text") != lot or confirmed < 1:
        fail(f"{subject} has no matching allocated and positively closed sub-lot operation")
    return opening_index, opening, close_index, close, confirmed, built


def validate_batch_applied(notes, data, *, reject_duplicate=True):
    batch, decision = batch_identity(data, "a batch ruling terminal")
    state = batch_state(notes, batch)
    answer = state["answers"].get(decision)
    if not answer:
        fail(f"a batch ruling terminal names no answered decision B{batch}/{decision}")
    if answer["status"] != "active":
        fail(f"a batch ruling terminal cannot apply superseded answer B{batch}/{decision}")
    route = data.get("route")
    if route not in BATCH_ROUTES or route != answer["route"]:
        fail(f"a batch ruling terminal does not match B{batch}/{decision}'s current route",
             {"terminal": route, "current": answer["route"]})
    current_conflict = answer["conflict"]
    if current_conflict is None:
        if "conflict" in data:
            fail(f"a batch ruling terminal invents a conflict authority for B{batch}/{decision}")
    elif data.get("conflict") != current_conflict[1]:
        fail(f"a batch ruling terminal does not name B{batch}/{decision}'s current conflict",
             f"expected {current_conflict[0]}/C{current_conflict[1]}")

    if route == "spec-in-place":
        sha, operation = data.get("sha"), data.get("recheck_op")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha) \
                or not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9._:-]+", operation):
            fail("a batch spec-in-place terminal lacks its exact commit and recheck proof")
        commit_index, _ = exact_indexed(
            notes, "spec.committed",
            lambda item: item.get("batch") == batch and item.get("decision") == decision
            and item.get("op") == operation and item.get("sha") == sha,
            f"batch spec-in-place terminal B{batch}/{decision}",
        )
        recheck_index, recheck = exact_indexed(
            notes, "decision.recheck.completed",
            lambda item: item.get("batch") == batch and item.get("decision") == decision
            and item.get("commit_op") == operation and item.get("sha") == sha,
            f"batch spec-in-place terminal B{batch}/{decision}",
        )
        if not commit_index < recheck_index or recheck_index != answer["state_index"]:
            fail(f"a batch spec-in-place terminal does not consume the current recheck for B{batch}/{decision}")
        actions = [item for item in (note_data(recheck).get("actions") or [])
                   if isinstance(item, dict) and item.get("answer") == f"B{batch}/{decision}"
                   and item.get("status") == "active" and item.get("route") == route]
        if len(actions) != 1:
            fail(f"a batch spec-in-place terminal's recheck does not prove B{batch}/{decision}")
    elif route == "amendment":
        amendment, sha = data.get("amendment"), data.get("sha")
        if not isinstance(amendment, int) or isinstance(amendment, bool) or amendment < 1 \
                or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            fail("a batch amendment terminal lacks its exact amendment and commit proof")
        opening_index, opening = exact_indexed(
            notes, "amendment.opened",
            lambda item: item.get("amendment") == amendment and item.get("batch") == batch,
            f"batch amendment terminal B{batch}/{decision}",
        )
        opening_data = note_data(opening)
        _, opening_members = validate_grouped_amendment_opening(
            notes[:opening_index], opening_data, reject_duplicate=False,
        )
        same_generation_openings = [
            entry for entry in notes
            if entry.get("kind") == "amendment.opened"
            and note_data(entry).get("batch") == batch
            and note_data(entry).get("state_kind") == opening_data.get("state_kind")
            and note_data(entry).get("state_ref") == opening_data.get("state_ref")
        ]
        if len(same_generation_openings) != 1:
            fail(f"batch amendment {amendment} does not own one unique B{batch} generation")
        identity = f"B{batch}/{decision}"
        if identity not in opening_members:
            fail(f"a batch amendment terminal names no member of amendment {amendment}", identity)
        current_members = batch_amendment_members(state, batch)
        if opening_data.get("members") != current_members \
                or opening_data.get("state_kind") != state["generation_kind"] \
                or opening_data.get("state_ref") != state["generation_ref"]:
            fail(f"batch amendment {amendment} no longer carries B{batch}'s current generation")
        next_openings = [index for index, entry in enumerate(notes[opening_index + 1:], opening_index + 1)
                         if entry.get("kind") == "amendment.opened"]
        amendment_end = next_openings[0] if next_openings else len(notes)
        commit_index, amendment_commit = exact_indexed(
            notes[opening_index + 1:amendment_end], "amendment.committed",
            lambda item: item.get("sha") == sha,
            f"batch amendment terminal B{batch}/{decision}",
        )
        commit_index += opening_index + 1
        validate_amendment_commit_entry(notes, commit_index, amendment_commit)
        if not answer["state_index"] < opening_index < commit_index:
            fail(f"a batch amendment terminal does not consume B{batch}/{decision}'s current state")
    elif route == "sublot":
        _, _, close_index, _, _, _ = sublot_close_proof(
            notes, data.get("lot"), f"batch sub-lot terminal B{batch}/{decision}"
        )
        if answer["state_index"] >= close_index:
            fail(f"a batch sub-lot terminal predates B{batch}/{decision}'s current state")

    if reject_duplicate:
        duplicates = [entry for index, entry in enumerate(notes)
                      if index > answer["state_index"] and entry.get("kind") == "ruling.applied"
                      and note_data(entry).get("batch") == batch
                      and note_data(entry).get("decision") == decision]
        if duplicates:
            fail(f"B{batch}/{decision}'s current batch route already has its terminal")
    return state, answer


def confirmed_carries(built):
    root = built.split(".", 1)[0]
    relative = PurePosixPath("reports", "product-review", root, f"{built}-confirmed.md")
    path = WORKSPACE
    for part in relative.parts:
        path = os.path.join(path, part)
        if os.path.islink(path):
            fail("a confirmed correction artifact may not traverse a symlink", str(relative))
    if not os.path.isfile(path):
        fail("the batch close has no real confirmed correction artifact", str(relative))
    carries = set()
    with open(path, encoding="utf-8") as source:
        for raw in source:
            if not raw.startswith("Carries:"):
                continue
            for token in raw.removeprefix("Carries:").strip().split(","):
                match = re.fullmatch(r"(?:batch\s+|B)([1-9][0-9]*)/([FD][1-9][0-9]*)", token.strip())
                if match:
                    carries.add((int(match.group(1)), match.group(2)))
    return carries


def validate_batch_closed(notes, data):
    batch = data.get("batch")
    if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
        fail("a decision batch close must name one positive integer batch", batch)
    outcome = data.get("outcome")
    if outcome not in BATCH_CLOSE_OUTCOMES:
        fail("a decision batch close has an unknown outcome",
             f"use exactly one of: {', '.join(sorted(BATCH_CLOSE_OUTCOMES))}")
    if any(entry.get("kind") == "decision.batch.closed"
           and note_data(entry).get("batch") == batch for entry in notes):
        fail(f"decision batch B{batch} is already closed")
    state = batch_state(notes, batch)

    # Re-authenticate every historical terminal for this batch. An invalid
    # free-form line from an older writer can never satisfy this close.
    for index, entry in enumerate(notes):
        if entry.get("kind") == "ruling.applied" and note_data(entry).get("batch") == batch:
            validate_batch_applied(notes[:index], note_data(entry), reject_duplicate=False)

    opening_index, _, close_index, _, confirmed, built = current_pass_close(
        notes, f"decision batch B{batch} close"
    )
    if any(index >= close_index for index in state["item_state_indices"].values()) \
            or any(answer["state_index"] >= close_index for answer in state["answers"].values()):
        fail(f"decision batch B{batch} current state is newer than its pass close")
    carries = set()
    if outcome == "no-correction":
        if confirmed != 0 or "lot" in data:
            fail(f"decision batch B{batch} no-correction close does not match its pass close")
    else:
        lot = data.get("lot")
        proof = sublot_close_proof(notes, lot, f"decision batch B{batch} close")
        if proof[2] != close_index or proof[0] != opening_index:
            fail(f"decision batch B{batch} close does not consume the current pass operation")
        carries = confirmed_carries(built)

    required_carries = set()
    for identity, verdict in state["items"].items():
        if identity.startswith("F") and verdict == "confirmed":
            required_carries.add((batch, identity))
    for decision, answer in state["answers"].items():
        if answer["status"] == "superseded":
            if answer["conflict"] is None:
                fail(f"B{batch}/{decision} is superseded without a ready conflict authority")
            continue
        current_terminals = [(index, entry) for index, entry in enumerate(notes)
                             if index > answer["state_index"]
                             and entry.get("kind") == "ruling.applied"
                             and note_data(entry).get("batch") == batch
                             and note_data(entry).get("decision") == decision]
        if len(current_terminals) != 1:
            fail(f"decision batch B{batch} close requires one current terminal for B{batch}/{decision}",
                 f"found {len(current_terminals)}")
        if answer["route"] in {"sublot", "amendment"}:
            required_carries.add((batch, decision))

    if outcome == "no-correction" and required_carries:
        fail(f"decision batch B{batch} still has correction work", sorted(required_carries))
    missing = required_carries - carries
    if missing:
        fail(f"decision batch B{batch} confirmed artifact omits current work",
             ", ".join(f"B{owner}/{item}" for owner, item in sorted(missing)))


def tuple_from(data):
    keys = ("authority_kind", "authority_ref", "authority_sha256")
    if all(data.get(key) for key in keys):
        return tuple(data[key] for key in keys)
    return None


def has_terminal(notes, ruling, authority):
    return any(
        entry.get("kind") == "ruling.applied"
        and note_data(entry).get("ruling") == ruling
        and tuple_from(note_data(entry)) == authority
        for entry in notes
    )


def conflict_ready_changes(notes, ruling, after_index):
    for entry in notes[after_index + 1:]:
        if entry.get("kind") != "decision.conflict.ready":
            continue
        data = note_data(entry)
        actions = [item for item in (data.get("actions") or [])
                   if isinstance(item, dict) and item.get("answer") == ruling]
        if actions:
            return True
        settlements = [candidate for candidate in notes
                       if candidate.get("kind") == "decision.conflict.settled"
                       and note_data(candidate).get("owner") == data.get("owner")
                       and note_data(candidate).get("conflict") == data.get("conflict")]
        if len(settlements) == 1 and any(
            isinstance(item, dict) and item.get("id") == ruling
            for item in (note_data(settlements[0]).get("updates") or [])
        ):
            return True
    return False


def accepted_direct_tails(notes):
    """Return direct routes whose durable acceptance proof still lacks its terminal."""
    pending = set()

    for index, entry in enumerate(notes):
        data = note_data(entry)
        if entry.get("kind") != "decision.recheck.completed" \
                or data.get("accepted") is not True or data.get("missing") != []:
            continue
        if isinstance(data.get("owner"), str) and re.fullmatch(r"R[1-9][0-9]*", data["owner"]):
            ruling = data["owner"]
            actions = [item for item in (data.get("actions") or [])
                       if isinstance(item, dict) and item.get("answer") == ruling
                       and item.get("status") == "active" and item.get("route") == "spec-in-place"]
            commits = [candidate for candidate in notes[:index]
                       if candidate.get("kind") == "spec.committed"
                       and note_data(candidate).get("ruling") == ruling
                       and note_data(candidate).get("op") == data.get("commit_op")]
            if len(actions) == 1 and len(commits) == 1:
                commit_data = note_data(commits[0])
                authority = (
                    commit_data.get("state_kind"), commit_data.get("state_ref"),
                    commit_data.get("artifact_sha256"),
                )
                if all(authority) and not has_terminal(notes, ruling, authority) \
                        and not conflict_ready_changes(notes, ruling, index):
                    pending.add(ruling)
        elif data.get("owner") == "spec-loop":
            actions = {item.get("answer"): item for item in (data.get("actions") or [])
                       if isinstance(item, dict)}
            for member in data.get("rulings") or []:
                if not isinstance(member, dict):
                    continue
                ruling = member.get("ruling")
                authority = tuple_from(member)
                action = actions.get(ruling)
                if re.fullmatch(r"R[1-9][0-9]*", str(ruling)) and authority \
                        and action and action.get("status") == "active" \
                        and action.get("route") == "spec-fixer" \
                        and not has_terminal(notes, ruling, authority) \
                        and not conflict_ready_changes(notes, ruling, index):
                    pending.add(ruling)

    openings = [(index, entry) for index, entry in enumerate(notes)
                if entry.get("kind") == "amendment.opened"]
    for position, (opening_index, opening) in enumerate(openings):
        end = openings[position + 1][0] if position + 1 < len(openings) else len(notes)
        commits = [(index, entry) for index, entry in enumerate(notes[opening_index + 1:end], opening_index + 1)
                   if entry.get("kind") == "amendment.committed"]
        if len(commits) != 1:
            continue
        commit_index, commit = commits[0]
        validate_amendment_commit_entry(notes, commit_index, commit)
        opening_data = note_data(opening)
        ruling, authority = opening_data.get("ruling"), tuple_from(opening_data)
        candidates = []
        if re.fullmatch(r"R[1-9][0-9]*", str(ruling)) and authority:
            candidates.append((ruling, authority))
        for entry in notes[opening_index + 1:commit_index]:
            data = note_data(entry)
            if entry.get("kind") == "fixer.dispatched" and data.get("route") == "amendment-fixer":
                ruling, authority = data.get("ruling"), tuple_from(data)
                if re.fullmatch(r"R[1-9][0-9]*", str(ruling)) and authority:
                    candidates.append((ruling, authority))
        for ruling, authority in candidates:
            if not has_terminal(notes, ruling, authority) \
                    and not conflict_ready_changes(notes, ruling, commit_index):
                pending.add(ruling)
    return sorted(pending)


def conflict_source_boundary(notes, data):
    kind, ref = data.get("state_kind"), data.get("state_ref")
    predicates = {
        "decision.batch.ready": lambda item: ref == f"B{item.get('batch')}",
        "decision.batch.supplemented": lambda item: item.get("after_op") == ref,
        "decision.recheck.completed": lambda item: item.get("commit_op") == ref
        or item.get("basis_ref") == ref,
        "ruling.ready": lambda item: item.get("ruling") == ref,
        "decision.conflict.ready": lambda item: ref == f"{item.get('owner')}/C{item.get('conflict')}",
        "spec.breach.restored": lambda item: item.get("breach") == ref,
    }
    predicate = predicates.get(kind)
    if predicate is None:
        fail("a conflict opening has an unknown source-state kind", kind)
    exact_matches(
        notes,
        lambda entry: entry.get("kind") == kind and predicate(note_data(entry)),
        "a conflict opening's source state",
    )


def validate_conflict_partial(notes, kind, data, text):
    owner, conflict = data["owner"], data["conflict"]
    subject = f"decision conflict {owner}/C{conflict}"
    openings = [(index, entry) for index, entry in enumerate(notes)
                if entry.get("kind") == "decision.conflict.opened"
                and note_data(entry).get("owner") == owner
                and note_data(entry).get("conflict") == conflict]
    if kind == "decision.conflict.opened":
        if openings:
            fail(f"{subject} already has an opening")
        try:
            validate_global_authority_precedence(notes)
        except AuthorityPrecedenceError as exc:
            fail(f"{subject} cannot open from unfinished product authority", exc)
        conflict_source_boundary(notes, data)
        ids = data.get("ids")
        state = global_answer_state(notes, len(notes))
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) \
                or any(not isinstance(identity, str) or not re.fullmatch(
                    r"(?:R[1-9][0-9]*|B[1-9][0-9]*/D[1-9][0-9]*)", identity
                ) or identity not in state for identity in ids):
            fail(f"{subject} has an invalid or unknown opened answer set", ids)
        return
    if len(openings) != 1:
        fail(f"{subject} has no one exact opening")
    opening_index, opening = openings[0]
    sourced = [(index, entry) for index, entry in enumerate(notes)
               if entry.get("kind") == "decision.conflict.sourced"
               and note_data(entry).get("owner") == owner
               and note_data(entry).get("conflict") == conflict]
    if kind == "decision.conflict.sourced":
        if sourced:
            fail(f"{subject} already has a source boundary")
        authority_artifact_sha({"text": text}, f"{subject} source")
        return
    if len(sourced) != 1 or not opening_index < sourced[0][0]:
        fail(f"{subject} has no one ordered source boundary")
    settled = [entry for entry in notes
               if entry.get("kind") == "decision.conflict.settled"
               and note_data(entry).get("owner") == owner
               and note_data(entry).get("conflict") == conflict]
    if kind == "decision.conflict.settled":
        if settled:
            fail(f"{subject} already has a settlement")
        if not isinstance(text, str) or not text:
            fail(f"{subject} has no durable human settlement")
        opened_ids = set(note_data(opening).get("ids") or [])
        prior = global_answer_state(notes, opening_index)
        updates = data.get("updates")
        seen = set()
        if not isinstance(updates, list):
            fail(f"{subject} has no atomic update list")
        for update in updates:
            if not isinstance(update, dict):
                fail(f"{subject} has a malformed settlement update")
            identity, status, route = update.get("id"), update.get("status"), update.get("route")
            routes = DIRECT_RULING_ROUTES if re.fullmatch(r"R[1-9][0-9]*", str(identity)) \
                else BATCH_ROUTES
            if identity not in prior or identity in seen \
                    or update.get("action") not in {
                        "keep", "supersede", "qualify", "replace", "reconcile",
                    } or status not in {"active", "superseded"} \
                    or status == "active" and route not in routes \
                    or status == "superseded" and route is not None:
                fail(f"{subject} has an invalid settlement update", update)
            seen.add(identity)
        if not opened_ids.issubset(seen):
            fail(f"{subject} settlement omits an opened answer", sorted(opened_ids - seen))


def validate_note_data(kind, data, text=None, *, round_number=None, mandate=None, context=None,
                       notes=None):
    notes = journal_entries() if notes is None else notes
    context = context or {}
    if kind == "attempt.launch.abandoned":
        fail("attempt.launch.abandoned is helper-owned; use construction-launch-abandoned")
    if kind == "amendment.attempt.settled":
        fail("amendment.attempt.settled is helper-owned; use amendment-attempt-settle.sh")
    if kind == "attempt.failed":
        data = normalize_attempt_failed(notes, data, context)
    elif kind == "attempt.succeeded":
        data = normalize_attempt_succeeded(notes, data, context)
    elif kind in {"paused", "aborted"} and isinstance(data, dict) \
            and "attempt" in data:
        data = normalize_attempt_stop(notes, kind, data, context)
    elif kind == "spec.written":
        data = normalize_spec_written(notes, data, text)
    elif kind == "round.opened":
        data = normalize_spec_round(notes, data)
    elif kind == "report.received" and round_number is not None:
        if mandate not in SPEC_MANDATES:
            fail("a round-carrying SPEC receipt has an unknown mandate", mandate)
        data = normalize_spec_report(notes, data, round_number, mandate)
    elif kind == "report.received" and mandate in PRODUCT_REVIEW_MANDATES:
        data = normalize_product_report(notes, data, mandate)
    elif kind == "fixer.returned" and round_number is not None:
        data = normalize_fixer_return(notes, data, round_number)
    elif kind == "amendment.opened":
        data = normalize_amendment_opened(notes, data, text, context)
    elif kind == "amendment.written":
        data = normalize_amendment_written(notes, data, text)
    elif kind == "sweep.reported":
        data = normalize_sweep_report(notes, data, round_number)
    elif kind == "reach.recovery.authorized":
        data = normalize_reach_recovery_authorization(
            notes, data, text, round_number, context,
        )
    elif kind == "bound.spent" and isinstance(text, str) \
            and text.startswith("consolidation round"):
        data = normalize_consolidation_spend(notes, data, text, round_number)
    elif kind == "bound.spent" and isinstance(text, str) and re.fullmatch(
        r"(?:(?:design|code) checker round (?:[1-9]|10) of 10)",
        text,
    ):
        check = text.split()[0]
        data = normalize_construction_spend(
            notes, data, text, context, check, round_number,
        )
    elif kind == "bound.spent" and text == "diagnostic ran - once per task":
        data = normalize_construction_spend(
            notes, data, text, context, "diagnostic", round_number,
        )
    elif kind == "verdict.consumed" and isinstance(data, dict) \
            and data.get("check") == "consolidation":
        data = normalize_consolidation_verdict(notes, data, text, round_number)
    elif kind == "verdict.consumed" and isinstance(data, dict) \
            and data.get("check") in {*CONSTRUCTION_CHECKERS, "diagnostic"}:
        data = normalize_construction_verdict(
            notes, data, text, context, data["check"], round_number,
        )
    elif kind == "verdict.consumed":
        fail("verdict.consumed has an unknown or malformed check identity", data)
    elif kind == "design.review.resolved":
        data = normalize_design_resolution(notes, data, text, context, round_number)
    elif kind == "design.review.blocked":
        data = normalize_design_blocker(notes, data, text, context, round_number)
    elif kind == "code.review.resolved":
        data = normalize_code_resolution(notes, data, text, context, round_number)
    elif kind == "code.review.blocked":
        data = normalize_code_blocker(notes, data, text, context, round_number)

    try:
        authority_boundary_identity({"kind": kind, "data": data})
    except AuthorityPrecedenceError as exc:
        fail("a global product-authority boundary has malformed identity data", exc)

    if kind == "decision.batch.sourced" and data:
        batch_source_items(data, data["batch"])

    if kind == "decision.recheck.completed" and data and "batch" in data \
            and "decision" in data:
        notes = journal_notes()
        sourced = exact_matches(
            notes,
            lambda entry: entry.get("kind") == "decision.batch.sourced"
            and note_data(entry).get("batch") == data["batch"],
            f"decision batch B{data['batch']} recheck source",
        )
        source_items = set(batch_source_items(note_data(sourced), data["batch"]))
        recheck_items = data.get("items")
        if not isinstance(recheck_items, list) or {
            item.get("id") for item in recheck_items if isinstance(item, dict)
        } != source_items or len(recheck_items) != len(source_items) or any(
            not isinstance(item, dict) or item.get("verdict") not in {"confirmed", "refuted"}
            for item in recheck_items
        ):
            fail(f"decision batch B{data['batch']} recheck lacks its complete structured item state")

    if kind == "decision.recheck.completed" and data and "breach" not in data \
            and data.get("owner") != "spec-loop":
        notes = journal_notes()
        candidate = {"kind": kind, "data": data, "text": text}
        validate_recheck_artifact(notes + [candidate], len(notes), candidate)

    if kind == "decision.recheck.completed" and data and data.get("owner") == "spec-loop":
        entries = journal_entries()
        candidate = {"event": "note", "kind": kind, "data": data, "text": text}
        try:
            validate_spec_loop_generation(entries + [candidate], len(entries))
        except AuthorityPrecedenceError as exc:
            fail("the SPEC-loop recheck has no exact close, authority state and verifier proof", exc)
        validate_spec_loop_artifact(candidate)

    if kind in {"decision.conflict.opened", "decision.conflict.sourced",
                "decision.conflict.settled"}:
        validate_conflict_partial(journal_entries(), kind, data, text)

    if kind == "decision.conflict.ready":
        candidate = {"kind": kind, "data": data}
        try:
            validate_conflict_generation(
                journal_notes() + [candidate], data["owner"], data["conflict"]
            )
        except AuthorityPrecedenceError as exc:
            fail("decision.conflict.ready has no exact opened, sourced and settled chain", exc)
        candidate["text"] = text
        validate_authority_artifact(candidate, "the conflict ready state")

    if kind == "spec.breach.restored":
        candidate = {"kind": kind, "data": data}
        try:
            validate_breach_restoration(journal_notes() + [candidate], data["breach"])
        except AuthorityPrecedenceError as exc:
            fail("spec.breach.restored has no exact successful latest recheck", exc)

    if kind == "spec.committed" and data and not any(
        key in data for key in ("ruling", "batch", "breach")
    ):
        required = {"sha", "op", "spec_round", "review_sha256", "spec_sha256"}
        if set(data) != required:
            fail("an unbound SPEC close has malformed proof data", data)
        round_value, review_sha, current_sha = spec_close_state()
        if data["spec_round"] != round_value or data["review_sha256"] != review_sha \
                or data["spec_sha256"] != current_sha:
            fail("the unbound SPEC close does not consume the exact clean full round")
        head = subprocess.run(
            ["git", "-C", project_root(), "rev-parse", "HEAD"], capture_output=True, text=True
        )
        if head.returncode != 0 or head.stdout.strip() != data["sha"]:
            fail("the unbound SPEC close SHA is not current HEAD", head.stderr or head.stdout)

    if kind in {"decision.recheck.completed", "decision.conflict.settled",
                "decision.conflict.ready"} and data:
        members = data.get("updates") if kind == "decision.conflict.settled" else data.get("actions")
        for member in members or []:
            if not isinstance(member, dict):
                continue
            identity = member.get("id") if kind == "decision.conflict.settled" else member.get("answer")
            route = member.get("route")
            if isinstance(identity, str) and re.fullmatch(r"R[1-9][0-9]*", identity) \
                    and route is not None and route not in DIRECT_RULING_ROUTES:
                fail(f"{kind} gives a direct ruling an unknown route",
                     f"{identity}: {route!r}; use exactly one of: {', '.join(sorted(DIRECT_RULING_ROUTES))}")

    if kind == "decision.conflict.opened" and data and data.get("purpose") != "restore-baseline":
        pending = accepted_direct_tails(journal_notes())
        if pending:
            fail(
                "an accepted direct route must publish its terminal before a new conflict opens",
                ", ".join(pending),
            )

    if kind == "ruling" and data and "ruling" in data:
        if not re.fullmatch(r"R[1-9][0-9]*", str(data.get("ruling"))):
            fail("an identified ruling must read R<N>", data.get("ruling"))
        if data.get("route") not in DIRECT_RULING_ROUTES:
            fail("an identified ruling has an unknown route",
                 f"use exactly one of: {', '.join(sorted(DIRECT_RULING_ROUTES))}")

    if kind == "amendment.opened" and data and "ruling" in data:
        ruling = str(data.get("ruling"))
        _, route, authority = direct_ruling_state(ruling)
        if route != "amendment":
            fail(f"{ruling} does not currently route to an amendment", route)
        validate_authority(data, "the direct amendment opening", authority)

    if kind == "amendment.opened" and data and "batch" in data:
        notes = journal_entries()
        try:
            validate_global_authority_precedence(notes)
        except AuthorityPrecedenceError as exc:
            fail("an unfinished global product-authority boundary outranks this batch amendment", exc)
        validate_grouped_amendment_opening(notes, data)

    if kind == "amendment.committed":
        candidate = {"event": "note", "kind": kind, "data": data}
        validate_amendment_commit_entry(
            notes + [candidate], len(notes), candidate, require_current=True,
        )

    if kind == "fixer.dispatched" and data and "ruling" in data:
        ruling = str(data.get("ruling"))
        if not re.fullmatch(r"R[1-9][0-9]*", ruling):
            fail("an owner-linked fixer dispatch must name R<N>", ruling)
        if data.get("route") not in {"spec-fixer", "amendment-fixer"}:
            fail("an owner-linked fixer dispatch has an unknown route",
                 "use exactly spec-fixer or amendment-fixer")
        notes, route, authority = direct_ruling_state(ruling)
        if data.get("route") != route:
            fail("the owner-linked fixer dispatch does not match the current route", route)
        validate_authority(data, "the owner-linked fixer dispatch", authority)
        duplicates = [entry for entry in notes
                      if entry.get("kind") == "fixer.dispatched"
                      and note_data(entry).get("ruling") == ruling
                      and all(note_data(entry).get(key) == authority[key]
                              for key in ("authority_kind", "authority_ref", "authority_sha256"))]
        if duplicates:
            fail("the current ruling authority already has its owner-linked fixer dispatch")

    if kind == "ruling.applied" and data and "ruling" in data:
        ruling = str(data.get("ruling"))
        if not re.fullmatch(r"R[1-9][0-9]*", ruling) or data.get("answer") != ruling:
            fail("a direct ruling terminal has inconsistent identity", data)
        route = data.get("route")
        if route not in DIRECT_RULING_ROUTES:
            fail("a direct ruling terminal has an unknown route",
                 f"use exactly one of: {', '.join(sorted(DIRECT_RULING_ROUTES))}")
        notes, current_route, authority = direct_ruling_state(ruling)
        if route != current_route:
            fail("the direct ruling terminal does not match the current route", current_route)
        validate_authority(data, "the direct ruling terminal", authority)
        if route in {"spec-in-place", "spec-fixer"}:
            if not data.get("sha") or not data.get("recheck_op"):
                fail(f"a {route} terminal must name its checked SHA and recheck operation")
        elif route in {"amendment", "amendment-fixer"} and (
            not data.get("sha")
            or not isinstance(data.get("amendment"), int)
            or data["amendment"] < 1
        ):
            fail(f"an {route} terminal must name its amendment and committed SHA")

        if route == "spec-in-place":
            commit = exact_matches(
                notes,
                lambda entry: entry.get("kind") == "spec.committed"
                and note_data(entry).get("ruling") == ruling
                and note_data(entry).get("op") == data["recheck_op"]
                and note_data(entry).get("sha") == data["sha"],
                "a spec-in-place terminal",
            )
            commit_data = note_data(commit)
            recheck = exact_matches(
                notes,
                lambda entry: entry.get("kind") == "decision.recheck.completed"
                and note_data(entry).get("owner") == ruling
                and note_data(entry).get("commit_op") == commit_data["op"]
                and note_data(entry).get("sha") == commit_data["sha"]
                and note_data(entry).get("accepted") is True
                and note_data(entry).get("missing") == [],
                "a spec-in-place terminal's global recheck",
            )
            if note_data(recheck).get("artifact_sha256") != authority_artifact_sha(recheck):
                fail("a spec-in-place terminal's global recheck artifact changed")
        elif route == "spec-fixer":
            exact_matches(
                notes,
                lambda entry: entry.get("kind") == "fixer.dispatched"
                and note_data(entry).get("ruling") == ruling
                and note_data(entry).get("route") == route
                and all(note_data(entry).get(key) == data[key]
                        for key in ("authority_kind", "authority_ref", "authority_sha256")),
                "a spec-fixer terminal's owner-linked dispatch",
            )
            exact_matches(
                notes,
                lambda entry: entry.get("kind") == "spec.committed"
                and note_data(entry).get("op") == data["recheck_op"]
                and note_data(entry).get("sha") == data["sha"],
                "a spec-fixer terminal's shared commit",
            )
            recheck = exact_matches(
                notes,
                lambda entry: entry.get("kind") == "decision.recheck.completed"
                and note_data(entry).get("owner") == "spec-loop"
                and note_data(entry).get("commit_op") == data["recheck_op"]
                and note_data(entry).get("sha") == data["sha"]
                and note_data(entry).get("accepted") is True
                and note_data(entry).get("missing") == []
                and any(isinstance(item, dict) and item.get("ruling") == ruling
                        and all(item.get(key) == data[key]
                                for key in ("authority_kind", "authority_ref", "authority_sha256"))
                        for item in (note_data(entry).get("rulings") or [])),
                "a spec-fixer terminal's owner-linked global recheck",
            )
            if note_data(recheck).get("artifact_sha256") != authority_artifact_sha(recheck):
                fail("a spec-fixer terminal's global recheck artifact changed")
        elif route in {"amendment", "amendment-fixer"}:
            if route == "amendment":
                opening = exact_matches(
                    notes,
                    lambda entry: entry.get("kind") == "amendment.opened"
                    and note_data(entry).get("amendment") == data["amendment"]
                    and note_data(entry).get("ruling") == ruling
                    and all(note_data(entry).get(key) == data[key]
                            for key in ("authority_kind", "authority_ref", "authority_sha256")),
                    "an amendment terminal's owner-linked opening",
                )
            else:
                exact_matches(
                    notes,
                    lambda entry: entry.get("kind") == "fixer.dispatched"
                    and note_data(entry).get("ruling") == ruling
                    and note_data(entry).get("route") == route
                    and all(note_data(entry).get(key) == data[key]
                            for key in ("authority_kind", "authority_ref", "authority_sha256")),
                    "an amendment-fixer terminal's owner-linked dispatch",
                )
                openings = [entry for entry in notes if entry.get("kind") == "amendment.opened"
                            and note_data(entry).get("amendment") == data["amendment"]]
                if len(openings) != 1:
                    fail("an amendment-fixer terminal has no one exact amendment opening")
                opening = openings[0]
            opening_index = notes.index(opening)
            amendment_commit = exact_matches(
                notes[opening_index + 1:],
                lambda entry: entry.get("kind") == "amendment.committed"
                and note_data(entry).get("sha") == data["sha"],
                f"an {route} terminal's amendment commit",
            )
            validate_amendment_commit_entry(notes, notes.index(amendment_commit), amendment_commit)

        duplicates = [entry for entry in notes
                      if entry.get("kind") == "ruling.applied"
                      and note_data(entry).get("ruling") == ruling
                      and note_data(entry).get("authority_kind") == data["authority_kind"]
                      and note_data(entry).get("authority_ref") == data["authority_ref"]
                      and note_data(entry).get("authority_sha256") == data["authority_sha256"]]
        if duplicates:
            fail("this exact direct ruling authority already has its terminal", ruling)

    if kind == "ruling.applied" and data and "batch" in data and "ruling" not in data:
        try:
            notes = journal_entries()
            validate_global_authority_precedence(notes)
        except AuthorityPrecedenceError as exc:
            fail("an unfinished global product-authority boundary outranks this batch terminal", exc)
        validate_batch_applied(notes, data)

    if kind == "decision.batch.closed":
        try:
            notes = journal_entries()
            validate_global_authority_precedence(notes)
        except AuthorityPrecedenceError as exc:
            fail("an unfinished global product-authority boundary outranks this batch close", exc)
        validate_batch_closed(notes, data or {})

    if kind == "decision.refuted" and data and "source" in data:
        validate_source_refutation(
            journal_entries(), data, text, "a fresh product-review source refutation",
        )

    if kind == "sublot.allocated":
        validate_sublot_allocation(
            journal_entries(), data or {}, text, "a product-review sub-lot allocation",
        )

    if kind == "sublot.opened":
        validate_sublot_opening(
            journal_entries(), data, text, "a product-review sub-lot opening",
        )

    if kind == "plan.written":
        data = normalize_plan_written(
            journal_entries(), data or {}, context, "a Construction plan publication",
        )
        validate_construction_lot_origin(
            journal_entries(), len(journal_entries()), context.get("lot"),
            "plan.written construction entry",
        )

    if kind == "lot.built":
        validate_construction_lot_origin(
            journal_entries(), len(journal_entries()), context.get("lot"),
            f"{kind} construction entry",
        )

    if kind == "pass.opened":
        data = normalize_pass_opened(data or {}, context)

    if kind == "pass.closed":
        validate_pass_close(journal_entries(), data or {}, "a product-review pass close")

    if kind == "lot.delivered":
        validate_lot_delivered(journal_entries(), data or {})

    return data


def _tail_start(fd, end):
    """Return the byte after the last newline, or zero for the first line."""
    cursor = end
    while cursor:
        size = min(cursor, 64 * 1024)
        cursor -= size
        chunk = os.pread(fd, size, cursor)
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            return cursor + newline + 1
    return 0


def _repair_incomplete_tail(fd):
    """Settle a writer killed inside its final append before another append."""
    end = os.lseek(fd, 0, os.SEEK_END)
    if not end or os.pread(fd, 1, end - 1) == b"\n":
        return end, None

    start = _tail_start(fd, end)
    tail = os.pread(fd, end - start, start)
    try:
        entry = json.loads(tail.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        entry = None

    if isinstance(entry, dict):
        written = os.write(fd, b"\n")
        if written != 1:
            raise OSError(f"short journal-tail repair: wrote {written} of 1 byte")
        return end + 1, "completed a newline missing from the interrupted final event"

    os.ftruncate(fd, start)
    return start, "discarded an incomplete final event left by an interrupted writer"


def repair_journal_tail():
    """Recover only the final fragment. Interior damage is never guessed."""
    with open(JOURNAL_LOCK, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not os.path.exists(JOURNAL):
            return
        fd = os.open(JOURNAL, os.O_RDWR | os.O_APPEND)
        try:
            _, recovery = _repair_incomplete_tail(fd)
        finally:
            os.close(fd)
    if recovery:
        print(f"**progress WARNING** · {recovery}")


def write_line(entry):
    write_validated_line(lambda _entries: entry)


def write_validated_line(builder, *, attempt_success=False):
    """Validate one semantic event against the exact locked append prefix."""
    recovery = None
    checkpoint_warning = None
    with open(JOURNAL_LOCK, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if attempt_success_marker("the pending attempt success") is not None \
                and not attempt_success:
            fail("the pending attempt success owns every workflow mutation")
        preflight_construction_history_checkpoint_path()
        fd = os.open(JOURNAL, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            append_start, recovery = _repair_incomplete_tail(fd)
            entries = journal_entries()
            checkpoint_start, journal_sha256 = construction_history_validation_start(entries)
            entry = builder(entries)
            validate_pending_amendment_attempt_settlement_append(entries, entry)
            validate_pending_attempt_success_append(entries, entry)
            validate_pending_pass_opening_append(
                entries, entry, "the journal append",
            )
            generation = COMMAND_VALIDATION_CACHE.get(
                "construction-history-generation", {},
            ) if COMMAND_VALIDATION_CACHE is not None else {}
            checkpoint = generation.get("checkpoint") \
                if generation.get("entry_count") == len(entries) else None
            checkpoint_exact = checkpoint is not None and checkpoint_start == len(entries)
            validation = COMMAND_VALIDATION_CACHE.get(
                ("construction-history", len(entries), journal_sha256),
            ) if COMMAND_VALIDATION_CACHE is not None else None
            history_validated = isinstance(validation, dict) \
                and validation.get("entries") is entries
            checkpoint_enabled = checkpoint_exact or history_validated
            if attempt_success and not checkpoint_exact:
                checkpoint_enabled = False
            checkpoint_dependencies = None
            if checkpoint_enabled:
                dependency_start = generation.get("start", 0) \
                    if checkpoint is not None else 0
                checkpoint_dependencies = merge_construction_history_dependencies(
                    checkpoint.get("dependencies", []) if checkpoint is not None else [],
                    construction_history_dependencies([*entries[dependency_start:], entry]),
                )
            payload = (
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            try:
                written = os.write(fd, payload)
            except OSError:
                os.ftruncate(fd, append_start)
                raise
            if written != len(payload):
                os.ftruncate(fd, append_start)
                raise OSError(
                    f"short journal write: wrote {written} of {len(payload)} bytes"
                )
            os.fsync(fd)
            end = os.lseek(fd, 0, os.SEEK_END)
            raw = os.pread(fd, end, 0)
            if checkpoint_dependencies is not None:
                try:
                    publish_construction_history_checkpoint(
                        raw, len(entries) + 1, checkpoint_dependencies,
                    )
                except OSError as exc:
                    checkpoint_warning = str(exc)
        finally:
            os.close(fd)
    if recovery:
        print(f"**progress WARNING** · {recovery}")
    if checkpoint_warning:
        print(
            "**progress WARNING** · the construction-history checkpoint was not "
            f"advanced: {checkpoint_warning}"
        )


def validate_pending_attempt_success_append(entries, entry):
    marker = attempt_success_marker("the pending attempt success")
    if marker is None:
        return
    recovery = note_data(entry).get("success_recovery")
    if entry.get("event") == "note" and entry.get("kind") == "attempt.succeeded" \
            and isinstance(recovery, dict) \
            and recovery.get("owner_sha256") == marker["owner_sha256"]:
        return
    fail("the pending attempt success owns every workflow mutation", {
        "event": entry.get("event"), "kind": entry.get("kind"),
        "session": entry.get("session"), "status": entry.get("status"),
        "lot": entry.get("lot"), "task": entry.get("task"),
        "attempt": entry.get("attempt"),
    })


def validate_pending_amendment_attempt_settlement_append(entries, entry):
    marker = amendment_attempt_settle_marker("the pending Amendment attempt settlement")
    if marker is None:
        return
    owner = marker["owner"]
    if entry.get("event") == "note" and entry.get("kind") == "attempt.failed":
        data = note_data(entry)
        supersession = data.get("amendment_supersession") if isinstance(data, dict) else None
        if entry.get("lot") == owner["lot"] and entry.get("task") == owner["task"] \
                and data.get("attempt") == owner["attempt"] \
                and isinstance(supersession, dict) \
                and supersession.get("settlement_owner_sha256") == marker["owner_sha256"]:
            return
    if entry.get("event") == "session-retired" \
            and entry.get("session") == owner["session"] \
            and entry.get("status") == "superseded" \
            and entry.get("archived") is True and entry.get("hidden") is True \
            and all(entry.get(key) == owner[key] for key in ("lot", "task", "attempt")):
        return
    if entry.get("event") == "note" and entry.get("kind") == "amendment.attempt.settled" \
            and note_data(entry).get("owner_sha256") == marker["owner_sha256"]:
        return
    fail("the pending Amendment attempt settlement owns every workflow mutation", {
        "event": entry.get("event"), "kind": entry.get("kind"),
        "session": entry.get("session"), "status": entry.get("status"),
        "lot": entry.get("lot"), "task": entry.get("task"), "attempt": entry.get("attempt"),
        "archived": entry.get("archived"), "hidden": entry.get("hidden"),
    })


def event_entry(by, event, **fields):
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": by,
        "event": event,
    }
    for key in LINE_FIELDS:
        value = fields.get(key)
        if value is not None:
            entry[key] = value
    return entry


def append_event(by, event, **fields):
    write_line(event_entry(by, event, **fields))


def refresh_dashboard():
    """Always last, so a failure here leaves the journal already correct."""
    if not os.path.isdir(DASHBOARD_DIR):
        return  # the dashboard is not part of this workspace (yet) — not an error
    if not os.path.exists(JOURNAL):
        return
    try:
        os.makedirs(os.path.dirname(DASHBOARD_COPY), exist_ok=True)
        # Hold one publication lock across BOTH the snapshot and its rename.
        # A writer that copied an older journal must publish before a later
        # writer can take and publish its newer snapshot. PID-specific temps
        # prevent collisions; the lock prevents publication order reversal.
        lock_path = f"{DASHBOARD_COPY}.lock"
        with open(lock_path, "a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with open(JOURNAL_LOCK, "a+b") as journal_lock:
                fcntl.flock(journal_lock, fcntl.LOCK_SH)
                tmp = f"{DASHBOARD_COPY}.{os.getpid()}.tmp"
                shutil.copyfile(JOURNAL, tmp)
                os.replace(tmp, DASHBOARD_COPY)
    except OSError as exc:
        # Loud but non-fatal: failing the call now would make the caller retry
        # a command whose journal line already landed, duplicating the event.
        print(f"**progress WARNING** · the dashboard copy was not refreshed: {exc}")


def cmd_session_started(args):
    me = whoami()
    target = created_session(args.session_id)
    context = context_of(target)
    data = None
    if context.get("mode") == "product-review" and context.get("job") == "reviewer":
        entries = journal_entries()
        _, _, built, _ = current_pass_opening(
            entries, len(entries), "the product-review reviewer start",
            validate_context=True,
        )
        caller = caller_context(me)
        expected_caller = {"mode": "product-review", "lot": built, "job": "controller"}
        if context.get("lot") != built \
                or {key: caller[key] for key in CONTEXT_FIELDS if key in caller} != expected_caller:
            fail("the product-review reviewer start has no exact current pass controller")
    if context.get("mode") == "construction" and context.get("job") == "implementer":
        entries = journal_entries()
        validate_construction_launch_candidate(
            entries, context.get("lot"), context.get("task"), context.get("attempt"),
            "the construction implementer start",
        )
        data = construction_session_start_account(
            context, args.session_id, "the construction implementer start",
        )
        validate_construction_session_start(
            {
                "event": "session-started", "session": args.session_id,
                "data": data, **context,
            },
            "the construction implementer start",
            entries=entries, index=len(entries),
        )
    if context.get("mode") == "amendment" and context.get("mandate") == "reach":
        sweep = context.get("round")
        entries = journal_entries()
        openings = amendment_openings(entries)
        if not openings or not isinstance(sweep, int) or isinstance(sweep, bool) or sweep < 1:
            fail("the Reach reviewer start has no exact amendment and sweep")
        opening_index, _ = openings[-1]
        candidate = {
            "event": "session-started", "session": args.session_id, **context,
        }
        validate_reach_sweep_owed(
            entries, opening_index, len(entries), sweep, "the Reach reviewer start",
        )
        validate_reach_replacement_order(
            entries + [candidate], opening_index, len(entries) + 1, sweep,
            "the Reach reviewer start",
        )
    append_event(me["session_id"], "session-started",
                 session=args.session_id, data=data, **context)


def cmd_construction_launch_abandoned(args):
    me = whoami()
    caller = caller_context(me)
    target = created_session(args.session_id)
    target_context = context_of(target)
    target_status = (((target.get("annotations") or {}).get("bwr") or {}).get("status"))
    if caller.get("mode") != "construction" or caller.get("job") != "controller" \
            or target_context.get("mode") != "construction" \
            or target_context.get("job") != "implementer" \
            or caller.get("lot") != target_context.get("lot") \
            or target_status != "failed":
        fail("the orphan-launch terminal requires its exact failed construction owner")
    entries = journal_entries()
    validate_construction_verdict_history(entries)
    data = construction_launch_abandonment_account(
        entries, len(entries), args.session_id,
        "the orphan-launch terminal", live=True,
    )
    append_event(
        me["session_id"], "note", kind="attempt.launch.abandoned",
        mode="construction", lot=data["lot"], task=data["task"],
        attempt=data["attempt"], job="controller", data=data,
    )


def cmd_construction_launch_check(args):
    validate_construction_launch_candidate(
        journal_entries(), args.lot, args.task, args.attempt,
        "the construction attempt start",
    )
    print(args.attempt)


def cmd_session_status(args):
    if args.status not in STATUSES:
        fail(f"unknown status `{args.status}`", "Statuses: " + " · ".join(STATUSES))
    me = whoami()
    target = run(["session", args.session_id])
    context = context_of(target)

    def build(entries):
        candidate = event_entry(
            me["session_id"], "session-status",
            session=args.session_id, status=args.status, **context,
        )
        validate_pending_pass_opening_append(
            entries, candidate, "the session status change",
        )
        validate_pending_attempt_success_append(entries, candidate)
        # The act and its record share the journal transaction. A refused
        # pending owner therefore changes no external session state.
        run([
            "update-session", args.session_id, "annotations",
            f"set:bwr.status={args.status}",
        ])
        return candidate

    write_validated_line(build)


def cmd_session_retired(args):
    if args.status not in TERMINAL:
        fail(f"`{args.status}` is not a terminal status",
             "session-retired takes: " + " · ".join(TERMINAL)
             + ". For a non-terminal change, use session-status.")
    me = whoami()
    target = run(["session", args.session_id])
    target_context = context_of(target)
    result = {"reach_preflight": None, "failed_step": None}

    def build(entries):
        if target_context.get("mode") == "amendment" \
                and target_context.get("mandate") == "reach" and args.status == "done":
            sweep = target_context.get("round")
            if not isinstance(sweep, int) or isinstance(sweep, bool) or sweep < 1:
                fail("the Reach reviewer retirement has no exact sweep identity")
            result["reach_preflight"] = amendment_sweep_preflight(
                entries, sweep, "the Reach reviewer retirement",
            )
            frozen = read_amendment_sweep_preflight("the Reach reviewer retirement")
            if frozen != result["reach_preflight"] or frozen["session"] != args.session_id:
                fail("the Reach reviewer retirement does not consume its exact preflight")

        provisional = event_entry(
            me["session_id"], "session-retired",
            session=args.session_id, status=args.status,
            archived=True if args.archive else None,
            hidden=True if args.hide else None,
            **target_context,
        )
        validate_pending_amendment_attempt_settlement_append(entries, provisional)
        validate_pending_attempt_success_append(entries, provisional)
        validate_pending_pass_opening_append(
            entries, provisional, "the session retirement",
        )
        ok, detail = attempt([
            "update-session", args.session_id, "annotations",
            f"set:bwr.status={args.status}",
        ])
        if not ok:
            fail("the status change failed, so the retirement did not happen", detail)

        # Status, then archive, then hide. The journal lock retains the
        # preflight owner until this complete external sequence is recorded.
        outcome = {}
        for step, wanted, key in (("archive", args.archive, "archived"),
                                  ("hide", args.hide, "hidden")):
            if not wanted:
                continue
            if result["failed_step"]:
                outcome[key] = False
                continue
            ok, detail = attempt(["update-session", args.session_id, step])
            outcome[key] = ok
            if not ok:
                result["failed_step"] = (step, detail)
        return event_entry(
            me["session_id"], "session-retired",
            session=args.session_id, status=args.status,
            archived=outcome.get("archived"), hidden=outcome.get("hidden"),
            **target_context,
        )

    write_validated_line(build)
    if target_context.get("mode") == "amendment" \
            and target_context.get("mandate") == "reach" and args.status != "done":
        frozen = read_amendment_sweep_preflight(
            "the non-successful Reach retirement", required=False,
        )
        if frozen is not None and frozen.get("session") == args.session_id:
            remove_amendment_sweep_preflight(frozen, "the non-successful Reach retirement")
    if result["failed_step"]:
        refresh_dashboard()  # the line above must reach the dashboard before we exit
        step, detail = result["failed_step"]
        fail(f"`{step}` failed after the status change", detail, journaled=True)


def cmd_subagent_started(args):
    if args.kind not in SUBAGENT_KINDS:
        fail(f"unknown subagent kind `{args.kind}`",
             "Look the name up where the call was given to you — never invent a variant.")
    data = parse_data(args.data)
    me = whoami()
    context = with_flag_overrides(caller_context(me), args)
    product_finding_verifier = args.kind == "finding-verifier" and not (
        isinstance(data, dict) and data.get("owner") == "spec-loop"
    )
    deferred_completeness = args.kind == "completeness"
    if args.kind == "gate-runner":
        validate_gate_subagent("subagent-started", data)
    elif args.kind == "finding-verifier" and isinstance(data, dict) \
            and data.get("owner") == "spec-loop":
        validate_spec_loop_verifier("subagent-started", data)
    elif product_finding_verifier:
        pass
    elif args.kind == "consolidation":
        data = normalize_consolidation_started(journal_entries(), data, args.round)
    elif args.kind == "completeness":
        if data is not None:
            fail("subagent-started completeness derives its identity and takes no --data")
    elif args.kind in {*CONSTRUCTION_CHECKERS.values(), "diagnostic"}:
        check = args.kind.removesuffix("-checker")
        data = normalize_construction_started(
            journal_entries(), data, context, check, args.round,
        )
        context.update({key: data[key] for key in ("lot", "task", "attempt")})
        if check == "diagnostic":
            context.pop("round", None)
    elif data is not None:
        fail(f"subagent-started {args.kind} does not take structured data")
    if deferred_completeness:
        def build(entries):
            account = deferred_amendment_c2_account(
                entries, len(entries), context.get("lot"),
                "the deferred post-Amendment C2 opening",
            )
            frozen_data = None
            if account is not None:
                if deferred_amendment_c2_generation_consumed(
                        entries, len(entries), context.get("lot"), account,
                        "the deferred post-Amendment C2 opening"):
                    fail("the deferred plan generation already has one usable C2 result")
                frozen_data = {"deferred_amendment_plan": account}
            validate_subagent_transition(
                entries, "subagent-started", me["session_id"], args.kind,
                context, frozen_data,
            )
            return event_entry(
                me["session_id"], "subagent-started", kind=args.kind,
                data=frozen_data, **context,
            )

        write_validated_line(build)
    elif product_finding_verifier:
        def build(entries):
            validate_product_finding_verifier(
                "subagent-started", data, args.mandate, entries,
            )
            validate_subagent_transition(
                entries, "subagent-started", me["session_id"], args.kind, context, data,
            )
            return event_entry(
                me["session_id"], "subagent-started", kind=args.kind, data=data, **context,
            )

        write_validated_line(build)
    else:
        validate_subagent_transition(
            journal_entries(), "subagent-started", me["session_id"], args.kind, context, data,
        )
        append_event(me["session_id"], "subagent-started", kind=args.kind, data=data, **context)
    if args.kind in {"design-checker", "code-checker"}:
        print(json.dumps({
            "manifest": data["manifest"], "manifest_sha256": data["manifest_sha256"],
            **({"tree": data["tree"], "gate": data["gate"]}
               if args.kind == "code-checker" else {}),
            "call": data["call"],
        }, separators=(",", ":"), sort_keys=True))
    print(
        "SUBAGENT OPEN\n"
        "Keep the exact provider handle.\n"
        "Do not end this turn while this bracket remains open.\n"
        "Continue other useful work, then inspect the provider-native subagent roster.\n"
        "If no useful work remains, use the provider-native result or wait mechanism.\n"
        "Record subagent-ended before acting on the result.\n"
        "Never use TwiCC process wait for this provider subagent.",
        file=sys.stderr,
    )


def cmd_subagent_ended(args):
    if args.kind not in SUBAGENT_KINDS:
        fail(f"unknown subagent kind `{args.kind}`",
             "Look the name up where the call was given to you — never invent a variant.")
    data = parse_data(args.data)
    me = whoami()
    context = with_flag_overrides(caller_context(me), args)
    product_finding_verifier = args.kind == "finding-verifier" and not (
        isinstance(data, dict) and data.get("owner") == "spec-loop"
    )
    deferred_completeness = args.kind == "completeness"
    if args.kind == "gate-runner":
        validate_gate_subagent("subagent-ended", data)
    elif args.kind == "finding-verifier" and isinstance(data, dict) \
            and data.get("owner") == "spec-loop":
        validate_spec_loop_verifier("subagent-ended", data)
    elif product_finding_verifier:
        pass
    elif args.kind == "consolidation":
        data = normalize_consolidation_ended(journal_entries(), data, args.round)
    elif args.kind == "completeness":
        pass
    elif args.kind in {*CONSTRUCTION_CHECKERS.values(), "diagnostic"}:
        check = args.kind.removesuffix("-checker")
        data = normalize_construction_ended(
            journal_entries(), data, context, check, args.round,
        )
        context.update({key: data[key] for key in ("lot", "task", "attempt")})
        if check == "diagnostic":
            context.pop("round", None)
    if deferred_completeness:
        requested_data = data

        def build(entries):
            openings = [(index, entry) for index, entry in open_subagent_brackets(entries)
                        if entry.get("kind") == "completeness"
                        and subagent_event_context(entry) == context]
            if len(openings) != 1:
                fail("the completeness terminal has no one exact physical opening")
            opening_index, opening = openings[0]
            frozen = note_data(opening).get("deferred_amendment_plan")
            normalized = requested_data
            if frozen is not None:
                expected = deferred_amendment_c2_account(
                    entries, opening_index, context.get("lot"),
                    "the deferred post-Amendment C2 result", recorded=frozen,
                )
                current = deferred_amendment_c2_account(
                    entries, len(entries), context.get("lot"),
                    "the deferred post-Amendment C2 result",
                )
                if current != expected:
                    fail("the deferred workspace plan changed while C2 was open")
                normalized, _outcome = deferred_amendment_c2_result_account(
                    requested_data, expected, "the deferred post-Amendment C2 result",
                )
            validate_subagent_transition(
                entries, "subagent-ended", me["session_id"], args.kind,
                context, normalized,
            )
            return event_entry(
                me["session_id"], "subagent-ended", kind=args.kind,
                data=normalized, **context,
            )

        write_validated_line(build)
    elif product_finding_verifier:
        def build(entries):
            validate_product_finding_verifier(
                "subagent-ended", data, args.mandate, entries,
            )
            validate_subagent_transition(
                entries, "subagent-ended", me["session_id"], args.kind, context, data,
            )
            return event_entry(
                me["session_id"], "subagent-ended", kind=args.kind, data=data, **context,
            )

        write_validated_line(build)
    else:
        validate_subagent_transition(
            journal_entries(), "subagent-ended", me["session_id"], args.kind, context, data,
        )
        append_event(me["session_id"], "subagent-ended", kind=args.kind, data=data, **context)


def subagent_event_context(entry):
    return {key: entry[key] for key in CONTEXT_FIELDS if key in entry}


def subagent_terminal_matches(opening, terminal):
    if opening.get("by") != terminal.get("by") \
            or opening.get("kind") != terminal.get("kind") \
            or subagent_event_context(opening) != subagent_event_context(terminal):
        return False
    opening_data = opening.get("data")
    if opening_data is None:
        return True
    terminal_data = terminal.get("data")
    return isinstance(terminal_data, dict) and all(
        terminal_data.get(key) == value for key, value in opening_data.items()
    )


def open_subagent_brackets(entries):
    """Return exact unsettled provider calls from one validated journal history."""
    open_calls = []
    for index, entry in enumerate(entries):
        event = entry.get("event")
        if event not in {"subagent-started", "subagent-ended"}:
            continue
        if not isinstance(entry.get("ts"), str) or not entry["ts"] \
                or not isinstance(entry.get("by"), str) or not entry["by"] \
                or entry.get("kind") not in SUBAGENT_KINDS \
                or "data" in entry and not isinstance(entry.get("data"), dict):
            fail("the journal has a malformed provider-subagent boundary",
                 f"progress.jsonl line {index + 1}")
        if event == "subagent-started":
            duplicate = [candidate for _, candidate in open_calls
                         if subagent_terminal_matches(candidate, entry)
                         and subagent_terminal_matches(entry, candidate)]
            if duplicate:
                fail("the journal opens the same provider-subagent identity twice",
                     f"progress.jsonl line {index + 1}")
            open_calls.append((index, entry))
            continue
        matches = [(position, item) for position, item in enumerate(open_calls)
                   if subagent_terminal_matches(item[1], entry)]
        if len(matches) != 1:
            fail("the journal has no one exact opening for a provider-subagent terminal",
                 f"progress.jsonl line {index + 1}")
        position, (opening_index, opening) = matches[0]
        frozen = note_data(opening).get("deferred_amendment_plan")
        if opening.get("kind") == "completeness" and frozen is not None:
            expected = deferred_amendment_c2_account(
                entries, opening_index, opening.get("lot"),
                "the historical deferred post-Amendment C2 terminal", recorded=frozen,
            )
            normalized, _outcome = deferred_amendment_c2_result_account(
                note_data(entry), expected,
                "the historical deferred post-Amendment C2 terminal", recorded=True,
            )
            if note_data(entry) != normalized:
                fail("the historical deferred C2 terminal changes its canonical account")
        del open_calls[position]
    return open_calls


def validate_subagent_transition(entries, event, owner, kind, context, data):
    candidate = {"event": event, "by": owner, "kind": kind, **context}
    if data is not None:
        candidate["data"] = data
    open_calls = open_subagent_brackets(entries)
    if event == "subagent-started":
        duplicates = [opening for _, opening in open_calls
                      if subagent_terminal_matches(opening, candidate)
                      and subagent_terminal_matches(candidate, opening)]
        if duplicates:
            fail("this exact provider-subagent physical call is already open")
        return
    matches = [opening for _, opening in open_calls
               if subagent_terminal_matches(opening, candidate)]
    if len(matches) != 1:
        fail("the provider-subagent terminal has no one exact open physical call")


def cmd_subagents_open(args):
    rows = []
    for index, entry in open_subagent_brackets(journal_entries()):
        rows.append({
            "kind": entry["kind"],
            "owner": entry["by"],
            "started": entry["ts"],
            "context": subagent_event_context(entry),
            "identity": entry.get("data") or {},
            "opening": journal_line_proof(index),
        })
    print(json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def note_text(args):
    """Read arbitrary journal text as data, without shell-source transport."""
    if args.text_file is None:
        return args.text
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(args.text_file, flags)
    except OSError as exc:
        fail("the journal text file is not one readable real file", str(exc))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail("the journal text file is not one real regular file", args.text_file)
        with os.fdopen(descriptor, encoding="utf-8", newline="") as handle:
            descriptor = None
            return handle.read()
    except UnicodeError as exc:
        fail("the journal text file is not valid UTF-8", str(exc))
    finally:
        if descriptor is not None:
            os.close(descriptor)


def cmd_note(args):
    if args.kind not in NOTE_KINDS:
        fail(f"unknown note kind `{args.kind}`",
             "Look the name up where the call was given to you — never invent a variant.")
    text = note_text(args)
    data = parse_data(args.data)
    me = whoami()
    context = with_flag_overrides(caller_context(me), args)
    if args.kind == "sweep.reported" and finish_interrupted_sweep_receipt(
        journal_entries(), data, context.get("round"),
    ):
        return
    if args.kind == "cleanup.started":
        def build(entries):
            locked_data = validate_note_data(
                args.kind, data, text, round_number=context.get("round"),
                mandate=context.get("mandate"), context=context, notes=entries,
            )
            owner = pending_malformed_pass_opening(
                entries, len(entries), "the whole-run cleanup append",
            )
            if owner is not None:
                locked_data = pass_opening_cleanup_data(
                    entries, owner, locked_data, "the whole-run cleanup append",
                )
            return event_entry(
                me["session_id"], "note", kind=args.kind,
                text=text if text is not None else None, data=locked_data,
                **context,
            )

        write_validated_line(build)
        return
    if args.kind == "bound.spent":
        def build(entries):
            locked_context = dict(context)
            locked_data = validate_note_data(
                args.kind, data, text, round_number=locked_context.get("round"),
                mandate=locked_context.get("mandate"), context=locked_context,
                notes=entries,
            )
            if isinstance(locked_data, dict) \
                    and locked_data.get("check") in {*CONSTRUCTION_CHECKERS, "diagnostic"}:
                locked_context.update({key: locked_data[key]
                                       for key in ("lot", "task", "attempt")})
                if locked_data.get("check") == "diagnostic":
                    locked_context.pop("round", None)
            return event_entry(
                me["session_id"], "note", kind=args.kind,
                text=text if text is not None else None, data=locked_data,
                **locked_context,
            )

        write_validated_line(build)
        return
    data = validate_note_data(
        args.kind, data, text, round_number=context.get("round"),
        mandate=context.get("mandate"), context=context,
    )
    if args.kind in {
        "bound.spent", "verdict.consumed", "design.review.resolved", "design.review.blocked",
        "code.review.resolved", "code.review.blocked",
    } \
            and isinstance(data, dict) \
            and data.get("check") in {*CONSTRUCTION_CHECKERS, "diagnostic"}:
        context.update({key: data[key] for key in ("lot", "task", "attempt")})
        if data.get("check") == "diagnostic":
            context.pop("round", None)
    append_event(me["session_id"], "note", kind=args.kind,
                 text=text if text is not None else None, data=data,
                 **context)
    if args.kind == "sweep.reported":
        remove_amendment_sweep_preflight(data, "sweep.reported", journaled=True)


def cmd_construction_spend_recover(args):
    me = whoami()
    caller = caller_context(me)
    if caller.get("mode") != "construction" or caller.get("job") != "controller" \
            or caller.get("lot") != args.lot:
        fail("logical-spend recovery requires the exact Construction controller and lot")
    if args.check in CONSTRUCTION_CHECKERS and args.round is None:
        fail("checker logical-spend recovery requires its exact round")
    if args.check == "diagnostic" and args.round is not None:
        fail("diagnostic logical-spend recovery takes no round")
    context = {
        "mode": "construction", "lot": args.lot, "task": args.task,
        "attempt": args.attempt, "job": "controller",
    }
    if args.round is not None:
        context["round"] = args.round

    def build(entries):
        validate_construction_verdict_history(entries)
        base = construction_logical_identity(
            entries, context, args.check, args.round,
            "the duplicate logical-spend recovery",
        )
        logical = construction_frozen_logical(
            entries, len(entries), base, "the duplicate logical-spend recovery",
        )
        if construction_spend_recoveries(entries, len(entries), logical):
            fail("this logical-spend identity already has its recovery")
        data = construction_spend_recovery_account(
            entries, len(entries), base, "the duplicate logical-spend recovery",
        )
        candidate = event_entry(
            me["session_id"], "note", kind="construction.spend.recovered",
            data=data, **context,
        )
        validate_construction_spend_recovery_entry(
            [*entries, candidate], len(entries), candidate,
        )
        return candidate

    write_validated_line(build)


def cmd_pass_opening_context_recover(args):
    me = whoami()
    caller = caller_context(me)
    expected_caller = {
        "mode": "product-review", "lot": caller.get("lot"), "job": "controller",
    }
    if {key: caller[key] for key in CONTEXT_FIELDS if key in caller} != expected_caller \
            or not isinstance(caller.get("lot"), str):
        fail("pass-opening recovery requires the exact PRODUCT REVIEW controller context")

    def build(entries):
        owner = pending_malformed_pass_opening(
            entries, len(entries), "the pass-opening recovery",
        )
        if owner is None:
            fail("pass-opening recovery has no durable pass.opened boundary")
        opening_index, opening, data = (
            owner["opening_index"], owner["opening"], owner["data"]
        )
        if owner["stop"]["phase"] not in {"active", "resumed"}:
            fail("pass-opening recovery cannot cross a current run stop")
        if opening.get("by") != me["session_id"]:
            fail("pass-opening recovery requires the original physical controller owner")
        if data.get("built") != caller.get("lot"):
            fail("pass-opening recovery does not match the controller's current lot")
        legacy = pass_opening_context(data, "construction")
        opening_context = {key: opening[key] for key in CONTEXT_FIELDS if key in opening}
        if opening_context != legacy:
            fail("pass-opening recovery requires one exact Construction-context opening")
        expected = pass_opening_context(data, "product-review")
        recovery_data = {
            "schema": 1,
            "opening": journal_line_proof(opening_index),
            "owner": me["session_id"],
            "built": data["built"],
            "commit": data["commit"],
            "gate": data["gate"],
            "from": legacy,
            "to": expected,
            "stop": pass_opening_stop_account(owner["stop"]),
        }
        candidate = event_entry(
            me["session_id"], "note", kind="pass.opening.context.recovered",
            data=recovery_data, **expected,
        )
        validate_pass_opening_history(
            [*entries, candidate], opening_index, "the recovered product-review pass",
        )
        validate_pass_opening_context(
            [*entries, candidate], opening_index, len(entries) + 1,
            "the recovered product-review pass",
        )
        return candidate

    write_validated_line(build)


def cmd_pass_opening_cleanup_check(args):
    entries = journal_entries()
    owner = pending_malformed_pass_opening(
        entries, len(entries), "the whole-run cleanup consumer",
    )
    if owner is None:
        return
    pass_opening_cleanup_account(
        entries, owner["opening_index"], len(entries),
        "the whole-run cleanup consumer",
    )
    if args.scope != "whole-run":
        fail("a pending whole-run cleanup cannot authorize one lot-scoped consumer",
             {"consumer": args.consumer, "scope": args.scope})


def cmd_spec_close_check(args):
    round_number, reviewed_sha, current_sha = spec_close_state(args.spec_path)
    print(round_number)
    print(reviewed_sha)
    print(current_sha)


def cmd_spec_state_check(args):
    entries = journal_entries()
    if any(entry.get("kind") == "spec.written" for entry in entries):
        validate_spec_history(entries)
    for index, entry in enumerate(entries):
        if entry.get("kind") == "decision.recheck.completed" \
                and note_data(entry).get("owner") == "spec-loop":
            try:
                validate_spec_loop_generation(entries, index)
            except AuthorityPrecedenceError as exc:
                fail("the durable SPEC-loop recheck is invalid", exc)
            validate_spec_loop_artifact(entry)
    print("SPEC STATE VALID")


def cmd_pass_verifier_check(args):
    """Authenticate the exact pass and report generation before opening a copy."""
    pass_verifier_state(args.commit, args.report_name)


def cmd_amendment_close_check(args):
    proof = amendment_review_proof(journal_entries(), len(journal_entries()),
                                   args.amendment, args.spec_path)
    for key in (
        "review_sha256", "opening_sha256", "written_sha256", "sweep",
        "sweep_sha256", "consolidation_round", "amendment_sha256", "spec_sha256",
    ):
        print(proof[key])


def cmd_amendment_state_check(args):
    entries = journal_entries()
    openings = amendment_openings(entries)
    for position, (opening_index, opening) in enumerate(openings):
        validate_amendment_opening_entry(entries, opening_index, opening)
        end = openings[position + 1][0] if position + 1 < len(openings) else len(entries)
        written = [entry for entry in entries[opening_index + 1:end]
                   if entry.get("kind") == "amendment.written"]
        if len(written) > 1:
            fail("an amendment generation has duplicate readiness boundaries")
        if written:
            amendment_written_entry(entries, opening_index, end, "amendment history")
        for index, entry in enumerate(entries[opening_index + 1:end], opening_index + 1):
            if entry.get("kind") == "sweep.reported":
                validate_sweep_entry(entries, index, entry)
            elif entry.get("kind") == "verdict.consumed" \
                    and note_data(entry).get("check") == "consolidation":
                validate_consolidation_verdict_entry(entries, index, entry)
            elif entry.get("kind") == "amendment.committed":
                validate_amendment_commit_entry(entries, index, entry)
    print("AMENDMENT STATE VALID")


def cmd_construction_verdict_check(args):
    entries = journal_entries()
    validate_construction_verdict_history(entries)
    if args.check == "history":
        if any(value is not None for value in (args.lot, args.task, args.attempt)):
            fail("construction verdict history takes no lot, task or attempt")
        print("CONSTRUCTION VERDICTS VALID")
        return
    if args.check == "historical-code":
        if not isinstance(args.lot, str) \
                or not construction_positive_integer(args.task) \
                or not construction_positive_integer(args.attempt) \
                or not re.fullmatch(r"[0-9a-f]{40,64}", str(args.tree)):
            fail("a historical code proof requires lot, task, attempt, proof and tree")
        proof_index, _ = journal_entry_from_proof(
            entries, args.proof, "the historical task gate's code proof",
        )
        prefix = entries[:proof_index + 1]
        validate_construction_verdict_history(prefix)
        verdicts = code_verdicts(prefix, len(prefix), args.lot, args.task, args.attempt)
        if not verdicts:
            fail("the historical task gate has no proved code-checker verdict")
        verdict_index, verdict = verdicts[-1]
        verdict_data = note_data(verdict)
        manifest = verdict_data.get("manifest", "")
        disagreement = "-"
        expected_proof = journal_line_proof(verdict_index)
        if verdict_data.get("outcome") != "clean":
            if verdict_data.get("round") != CONSTRUCTION_CHECKER_ROUNDS["code"]:
                fail("the historical task gate consumes unfinished code findings")
            resolutions = [(index, entry) for index, entry in code_resolutions(
                prefix, len(prefix), args.lot, args.task, args.attempt,
            ) if note_data(entry).get("round") == verdict_data.get("round")]
            if len(resolutions) != 1:
                fail("the historical task gate has no exact final code resolution")
            resolution_index, resolution = resolutions[0]
            resolution_data = note_data(resolution)
            if resolution_data.get("verdict") != journal_line_proof(verdict_index) \
                    or resolution_data.get("accepted") != 0:
                fail("the historical task gate has no accepted final code resolution")
            expected_proof = journal_line_proof(resolution_index)
            manifest = resolution_data.get("manifest", "")
            disagreement = resolution_data.get("disagreement_sha256") or "-"
        if args.proof != expected_proof:
            fail("the historical task gate names another final code proof")
        final = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "historical-final-tree",
             manifest, args.tree, disagreement],
            capture_output=True, text=True,
        )
        if final.returncode != 0:
            fail("the historical task gate does not bind its reviewed candidate",
                 final.stderr or final.stdout)
        print(args.proof)
        return
    if args.check not in {"design", "code"} or not isinstance(args.lot, str) \
            or not construction_positive_integer(args.task) \
            or not construction_positive_integer(args.attempt) \
            or args.proof is not None or args.tree is not None:
        fail("a checker verdict proof requires design or code, lot, task and attempt")
    if args.check == "design":
        verdicts = design_verdicts(
            entries, len(entries), args.lot, args.task, args.attempt,
        )
        if not verdicts:
            fail("this attempt has no proved design-checker verdict")
        _, latest = verdicts[-1]
        base = {key: note_data(latest)[key] for key in (
            "lot", "task", "attempt", "round",
        )}
        base["check"] = "design"
        logical = construction_frozen_logical(
            entries, len(entries), base, "the accepted Design proof",
        )
        generation = construction_plan_generation(logical, "the accepted Design proof")
        proof_index = construction_design_proof(
            entries, len(entries), base, generation, "the accepted Design proof",
        )
        print(journal_line_proof(proof_index))
        return
    verdicts = code_verdicts(entries, len(entries), args.lot, args.task, args.attempt)
    if not verdicts:
        fail("this attempt has no proved code-checker verdict")
    verdict_index, verdict = verdicts[-1]
    verdict_data = note_data(verdict)
    if verdict_data.get("outcome") == "clean":
        tree = subprocess.run(
            ["git", "-C", REPO, "write-tree"], capture_output=True, text=True,
        )
        final = subprocess.run(
            [sys.executable, CONSTRUCTION_REVIEW, "final-tree",
             verdict_data.get("manifest", ""), tree.stdout.strip()],
            capture_output=True, text=True,
        )
        if tree.returncode != 0 or final.returncode != 0:
            fail("the final gate candidate is not the exact code-reviewed candidate",
                 final.stderr or final.stdout or tree.stderr)
        print(journal_line_proof(verdict_index))
        return
    if verdict_data.get("round") != CONSTRUCTION_CHECKER_ROUNDS["code"]:
        fail("code findings before round ten require correction and another checker round")
    resolutions = [(index, entry) for index, entry in code_resolutions(
        entries, len(entries), args.lot, args.task, args.attempt,
    ) if note_data(entry).get("round") == verdict_data.get("round")]
    if len(resolutions) != 1:
        fail("the final code-checker findings have no one exact implementer resolution")
    resolution_index, resolution = resolutions[0]
    resolution_data = note_data(resolution)
    if resolution_data.get("verdict") != journal_line_proof(verdict_index):
        fail("the final code-review resolution belongs to another checker verdict")
    if resolution_data.get("accepted") != 0:
        fail("the final code-review resolution contains an accepted defect")
    plan = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "plan-state", args.lot, str(args.task)],
        capture_output=True, text=True,
    )
    try:
        current_disagreement = json.loads(plan.stdout).get("disagreement_sha256") \
            if plan.returncode == 0 else None
    except ValueError:
        current_disagreement = None
    if plan.returncode != 0 \
            or current_disagreement != resolution_data.get("disagreement_sha256"):
        fail("the final candidate does not carry the exact resolved Disagreement projection",
             plan.stderr or plan.stdout)
    tree = subprocess.run(["git", "-C", REPO, "write-tree"], capture_output=True, text=True)
    final = subprocess.run(
        [sys.executable, CONSTRUCTION_REVIEW, "final-tree",
         resolution_data.get("manifest", ""), tree.stdout.strip(),
         resolution_data.get("disagreement_sha256") or "-"],
        capture_output=True, text=True,
    )
    if tree.returncode != 0 or final.returncode != 0:
        fail("the final gate candidate is not the exact resolved code-reviewed candidate",
             final.stderr or final.stdout or tree.stderr)
    print(journal_line_proof(resolution_index))


def cmd_construction_origin_check(args):
    proof = validate_construction_lot_origin(
        journal_entries(), len(journal_entries()), args.lot,
        "the construction lot origin",
    )
    print(proof)


def cmd_construction_failure_handoff(args):
    entries = journal_entries()
    validate_construction_verdict_history(entries)
    design_state = design_failure_handoff(
        entries, len(entries), args.lot, args.task, args.attempt,
        "the final design-review failure handoff",
    )
    code_state = final_code_failure_handoff(
        entries, len(entries), args.lot, args.task, args.attempt,
        "the final code-review failure handoff",
    )
    if design_state is not None and code_state is not None:
        fail("this attempt has both final design and code-review failure obligations")
    state = design_state if design_state is not None else code_state
    if state is None or state.get("unresolved") or not state.get("accepted"):
        fail("this attempt has no settled accepted round-10 checker defect")
    review = "design" if design_state is not None else "code"
    canonical = json.dumps(
        state["handoff"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    print(f"## Final {review}-review handoff")
    print("```json")
    print(canonical)
    print("```")


def cmd_construction_code_blocker_recover(args):
    me = whoami()
    caller = caller_context(me)
    if caller.get("mode") != "construction" or caller.get("job") != "controller" \
            or caller.get("lot") != args.lot \
            or any(caller.get(key) is not None
                   for key in ("task", "attempt", "round", "mandate")):
        fail("code-review blocker recovery requires the exact Construction controller and lot")

    def build(entries):
        validate_construction_verdict_history(entries)
        data = code_blocker_reclassification_account(
            entries, len(entries), args.lot, args.task, args.attempt, args.round,
            args.contract_blocked, "the code-review blocker recovery",
            live=True,
        )
        context = {
            "mode": "construction", "job": "controller", "lot": args.lot,
            "task": args.task, "attempt": args.attempt, "round": args.round,
        }
        return event_entry(
            me["session_id"], "note", kind="code.review.blocked",
            text=code_blocker_reclassification_text(data["items"]),
            data=data, **context,
        )

    write_validated_line(build)
    print(
        f"CODE REVIEW BLOCKER RECOVERED {args.lot} {args.task} "
        f"{args.attempt} {args.round}"
    )


def cmd_amendment_sweep_check(args):
    entries = journal_entries()
    proof = amendment_sweep_preflight(entries, args.round, "the amendment sweep preflight")
    publish_amendment_sweep_preflight(entries, proof, "the amendment sweep preflight")
    print(json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def cmd_construction_failure_check(args):
    entries = journal_entries()
    validate_construction_verdict_history(entries)
    context = {"lot": args.lot, "task": args.task, "attempt": args.attempt}
    identity = active_attempt_identity(context, "the failure closer", allow_closer=True)
    expected = attempt_failure_account(
        entries, len(entries), identity, args.classification, "the failure closer",
    )
    print(json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def cmd_amendment_attempt_settle_terminal(args):
    me = whoami()

    def build(entries):
        marker = amendment_attempt_settle_marker(
            "the Amendment attempt settlement terminal", required=True,
        )
        owner = marker["owner"]
        if marker["owner_sha256"] != args.owner \
                or (owner["amendment"], owner["lot"], owner["task"], owner["attempt"]) != (
                    args.amendment, args.lot, args.task, args.attempt,
                ):
            fail("the Amendment attempt settlement terminal names another retained owner")
        data = amendment_attempt_settle_terminal_account(
            entries, len(entries), owner, "the Amendment attempt settlement terminal",
        )
        candidate = event_entry(
            me["session_id"], "note", kind="amendment.attempt.settled",
            mode="amendment", lot=args.lot, task=args.task, attempt=args.attempt,
            job="controller", data=data,
        )
        validate_pending_amendment_attempt_settlement_append(entries, candidate)
        return candidate

    write_validated_line(build)


def cmd_amendment_attempt_settle_owner_check(args):
    marker = amendment_attempt_settle_marker(
        "the official failure closer's Amendment settlement owner", required=True,
    )
    owner = marker["owner"]
    if marker["owner_sha256"] != args.owner \
            or (owner["lot"], owner["task"], owner["attempt"]) != (
                args.lot, args.task, args.attempt,
            ):
        fail("the official failure closer names another Amendment settlement owner")
    print(marker["owner_sha256"])


def cmd_construction_plan_publication_check(args):
    entries = journal_entries()
    amendment_plan_publication_account(
        entries, len(entries), args.lot, args.tasks, "preflight",
        "the Construction plan publication preflight",
    )


def cmd_construction_plan_publication_account(args):
    entries = journal_entries()
    head = subprocess.run(
        ["git", "-C", project_root(), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True, text=True,
    )
    if head.returncode != 0:
        fail("the Construction plan publication has no committed HEAD")
    account = amendment_plan_publication_account(
        entries, len(entries), args.lot, args.tasks, args.operation,
        "the Construction plan publication", commit=head.stdout.strip(), live=True,
    )
    print(json.dumps(account, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def cmd_construction_plan_successor_check(args):
    entries = journal_entries()
    active = active_amendment_plan_supersession(
        entries, len(entries), args.lot, "the replacement attempt admission",
    )
    if active is None:
        return
    failure_index, failure, _supersession = active
    if failure.get("task") != args.task:
        return
    failure_proof = journal_line_proof(failure_index)
    publications = [(index, entry) for index, entry in enumerate(
        entries[failure_index + 1:], failure_index + 1,
    ) if entry.get("kind") == "plan.written" and entry.get("lot") == args.lot]
    bound = [(index, entry) for index, entry in publications
             if note_data(entry).get("schema") == 2
             and note_data(entry).get("amendment_supersession", {}).get("failure")
             == failure_proof]
    if not bound or publications[-1][0] != bound[-1][0]:
        fail("the replacement attempt has no exact current AMENDMENT plan publication")
    for index, entry in bound:
        validate_plan_written_entry(entries, index, entry)
    head = subprocess.run(
        ["git", "-C", project_root(), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or note_data(bound[-1][1]).get("commit") != head.stdout.strip():
        fail("the replacement attempt is not on its exact published plan commit")


def cmd_construction_retry_check(args):
    entries = journal_entries()
    validate_construction_verdict_history(entries)
    proof = outstanding_retry_proof(entries, args.lot)
    if proof is None:
        if args.report != "-":
            fail("no final checker correction obligation authorizes this retry report")
        print("-")
        return
    _, proof_entry, report = accepted_retry_from_proof(
        entries, proof, "the next attempt's retry input",
    )
    expected_report = report.get("report", "-")
    if proof_entry.get("kind") in {"paused", "aborted"} and expected_report != "-":
        fail("a stopped Design obligation unexpectedly owns a failure report")
    if args.report != expected_report:
        fail("the next attempt must receive the exact checker-obligation report argument",
             {"expected": expected_report, "actual": args.report})
    print(proof)


def cmd_notes(args):
    """Print the notes back — never the session and subagent traffic. This is
    what a session reads after a compaction or a takeover, so it is written
    for a human and an agent alike."""
    if not os.path.exists(JOURNAL):
        print("No journal yet — nothing has been recorded for this run.")
        return
    notes, unreadable = [], 0
    with open(JOURNAL, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except ValueError:
                unreadable += 1
                continue
            if entry.get("event") == "note":
                notes.append(entry)
    if unreadable:
        print(f"**progress WARNING** · {unreadable} unreadable line(s) skipped")
        print()
    if not notes:
        print("No notes in the journal yet.")
        return
    for entry in notes:
        context = " ".join(f"{key}={entry[key]}" for key in CONTEXT_FIELDS if key in entry)
        head = f"{entry.get('ts', '?')} · {entry.get('kind', '?')} · by {entry.get('by', '?')}"
        if context:
            head += f" · {context}"
        print(head)
        if entry.get("text"):
            print(f"    {entry['text']}")
        if "data" in entry:
            print(f"    data: {json.dumps(entry['data'], ensure_ascii=False)}")
        print()


def positive_int(value):
    """Tasks and rounds count from 1: the report paths and git refs built on
    these numbers have one spelling per ordinal, and no zeroth member."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer, counting from 1")
    return number


def positive_id_list(value):
    if not re.fullmatch(r"[1-9][0-9]*(?:,[1-9][0-9]*)*", value):
        raise argparse.ArgumentTypeError("must be one sorted comma-separated positive ID list")
    ids = [int(item) for item in value.split(",")]
    if ids != sorted(set(ids)):
        raise argparse.ArgumentTypeError("must contain unique IDs in increasing order")
    return ids


def add_context_flags(parser):
    parser.add_argument("--mandate", metavar="SLUG")
    parser.add_argument("--task", type=positive_int, metavar="N")
    parser.add_argument("--round", type=positive_int, metavar="K")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="progress.py",
        description="The run's journal. The rules for calling it are in progress-rules.md.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("session-started", help="record a session the caller just created")
    sp.add_argument("session_id")
    sp.set_defaults(func=cmd_session_started)

    sp = sub.add_parser("construction-launch-abandoned", help=argparse.SUPPRESS)
    sp.add_argument("session_id")
    sp.set_defaults(func=cmd_construction_launch_abandoned)

    sp = sub.add_parser("construction-launch-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.set_defaults(func=cmd_construction_launch_check)

    sp = sub.add_parser("construction-spend-recover", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.add_argument("check", choices=(*CONSTRUCTION_CHECKERS, "diagnostic"))
    sp.add_argument("round", nargs="?", type=positive_int)
    sp.set_defaults(func=cmd_construction_spend_recover)

    sp = sub.add_parser("pass-opening-context-recover", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_pass_opening_context_recover)

    sp = sub.add_parser("pass-opening-cleanup-check", help=argparse.SUPPRESS)
    sp.add_argument("consumer", choices=("audit", "refs-clear", "workspace-delete"))
    sp.add_argument("scope", choices=("whole-run", "lot"))
    sp.set_defaults(func=cmd_pass_opening_cleanup_check)

    sp = sub.add_parser("session-status", help="change a session's bwr.status, and record it")
    sp.add_argument("session_id")
    sp.add_argument("status")
    sp.set_defaults(func=cmd_session_status)

    sp = sub.add_parser("session-retired", help="terminal status, then archive, then hide — and record it")
    sp.add_argument("session_id")
    sp.add_argument("status")
    sp.add_argument("--archive", action="store_true")
    sp.add_argument("--hide", action="store_true")
    sp.set_defaults(func=cmd_session_retired)

    sp = sub.add_parser("subagent-started", help="record a subagent launch")
    sp.add_argument("kind")
    add_context_flags(sp)
    sp.add_argument("--data", metavar="JSON")
    sp.set_defaults(func=cmd_subagent_started)

    sp = sub.add_parser("subagent-ended", help="record a subagent's return")
    sp.add_argument("kind")
    add_context_flags(sp)
    sp.add_argument("--data", metavar="JSON")
    sp.set_defaults(func=cmd_subagent_ended)

    sp = sub.add_parser("subagents-open", help="print exact unsettled provider-subagent brackets")
    sp.set_defaults(func=cmd_subagents_open)

    sp = sub.add_parser("note", help="record one event of the run")
    sp.add_argument("kind")
    add_context_flags(sp)
    text_source = sp.add_mutually_exclusive_group()
    text_source.add_argument("--text", metavar="SENTENCE")
    text_source.add_argument("--text-file", metavar="PATH")
    sp.add_argument("--data", metavar="JSON")
    sp.set_defaults(func=cmd_note)

    sp = sub.add_parser("spec-close-check", help=argparse.SUPPRESS)
    sp.add_argument("spec_path")
    sp.set_defaults(func=cmd_spec_close_check)

    sp = sub.add_parser("spec-state-check", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_spec_state_check)

    sp = sub.add_parser("pass-verifier-check", help=argparse.SUPPRESS)
    sp.add_argument("commit")
    sp.add_argument("report_name")
    sp.set_defaults(func=cmd_pass_verifier_check)

    sp = sub.add_parser("amendment-close-check", help=argparse.SUPPRESS)
    sp.add_argument("amendment", type=positive_int)
    sp.add_argument("spec_path")
    sp.set_defaults(func=cmd_amendment_close_check)

    sp = sub.add_parser("amendment-state-check", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_amendment_state_check)

    sp = sub.add_parser("amendment-sweep-check", help=argparse.SUPPRESS)
    sp.add_argument("round", type=positive_int)
    sp.set_defaults(func=cmd_amendment_sweep_check)

    sp = sub.add_parser("construction-verdict-check", help=argparse.SUPPRESS)
    sp.add_argument("check", choices=("history", "design", "code", "historical-code"))
    sp.add_argument("lot", nargs="?")
    sp.add_argument("task", nargs="?", type=positive_int)
    sp.add_argument("attempt", nargs="?", type=positive_int)
    sp.add_argument("proof", nargs="?")
    sp.add_argument("tree", nargs="?")
    sp.set_defaults(func=cmd_construction_verdict_check)

    sp = sub.add_parser("construction-origin-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.set_defaults(func=cmd_construction_origin_check)

    sp = sub.add_parser("construction-failure-handoff", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.set_defaults(func=cmd_construction_failure_handoff)

    sp = sub.add_parser("construction-code-blocker-recover", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.add_argument("round", type=positive_int)
    sp.add_argument("contract_blocked", type=positive_id_list)
    sp.set_defaults(func=cmd_construction_code_blocker_recover)

    sp = sub.add_parser("construction-failure-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.add_argument("classification", choices=tuple(sorted(CONSTRUCTION_CLASSIFICATIONS)))
    sp.set_defaults(func=cmd_construction_failure_check)

    sp = sub.add_parser("amendment-attempt-settle-terminal", help=argparse.SUPPRESS)
    sp.add_argument("amendment", type=positive_int)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.add_argument("owner")
    sp.set_defaults(func=cmd_amendment_attempt_settle_terminal)

    sp = sub.add_parser("amendment-attempt-settle-owner-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("attempt", type=positive_int)
    sp.add_argument("owner")
    sp.set_defaults(func=cmd_amendment_attempt_settle_owner_check)

    sp = sub.add_parser("construction-plan-publication-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("tasks", type=positive_int)
    sp.set_defaults(func=cmd_construction_plan_publication_check)

    sp = sub.add_parser("construction-plan-publication-account", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("tasks", type=positive_int)
    sp.add_argument("operation")
    sp.set_defaults(func=cmd_construction_plan_publication_account)

    sp = sub.add_parser("construction-plan-successor-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.set_defaults(func=cmd_construction_plan_successor_check)

    sp = sub.add_parser("construction-retry-check", help=argparse.SUPPRESS)
    sp.add_argument("lot")
    sp.add_argument("task", type=positive_int)
    sp.add_argument("report")
    sp.set_defaults(func=cmd_construction_retry_check)

    sp = sub.add_parser("notes", help="print the notes back, and nothing else")
    sp.set_defaults(func=cmd_notes)

    return parser


def main():
    global COMMAND_VALIDATION_CACHE
    args = build_parser().parse_args()
    read_only = {
        "subagents-open", "construction-failure-check",
        "amendment-attempt-settle-owner-check", "construction-verdict-check",
    }
    # A retained success owner admits only its helper-owned terminal. Do not
    # repair shared bytes before that locked admission can refuse another
    # command.
    COMMAND_VALIDATION_CACHE = {}
    try:
        pending_attempt_success = os.path.lexists(ATTEMPT_SUCCESS_MARKER)
        if pending_attempt_success and args.command not in read_only:
            fail("the pending attempt success owns every workflow mutation")
        if args.command not in read_only and not pending_attempt_success:
            preflight_construction_history_checkpoint_path()
            repair_journal_tail()
        args.func(args)
        if args.command not in read_only:
            refresh_dashboard()
    finally:
        COMMAND_VALIDATION_CACHE = None


if __name__ == "__main__":
    main()
