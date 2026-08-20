"""Authenticate one durable spec.edit.ready boundary for spec-commit.sh.

The controller writes the semantic state in a complete artifact, hashes that artifact,
then publishes spec.edit.ready before editing the repository spec. This helper checks
the structured identity, the exact source boundary and the artifact hash. It does not
interpret the proposal prose; the post-commit global recheck remains its semantic proof.
"""

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

from authority_precedence import (
    AuthorityPrecedenceError,
    is_authority_boundary,
    validate_authority_boundary_identities,
    validate_global_authority_precedence,
)

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
JOURNAL = WORKSPACE / "progress.jsonl"

SPEC_EDIT_STATE_KINDS = {
    "ruling.ready",
    "decision.batch.ready",
    "decision.batch.supplemented",
    "decision.recheck.completed",
    "decision.conflict.ready",
}


def fail(message):
    raise SystemExit(message)


def note_data(entry):
    data = entry.get("data")
    return data if isinstance(data, dict) else {}


def read_notes():
    if not JOURNAL.is_file():
        fail("the run has no journal")
    notes = []
    with JOURNAL.open(encoding="utf-8") as source:
        for line_number, raw in enumerate(source, 1):
            try:
                entry = json.loads(raw)
            except ValueError as exc:
                fail(f"journal line {line_number} is not valid JSON: {exc}")
            notes.append((line_number, entry))
    return notes


def find_exact(notes, kind, predicate, before_index):
    matches = [(index, entry) for index, (_, entry) in enumerate(notes[:before_index])
               if entry.get("kind") == kind and predicate(note_data(entry))]
    if len(matches) != 1:
        fail(f"expected exactly one matching {kind} before spec.edit.ready, found {len(matches)}")
    return matches[0]


def state_event(notes, ready_index, kind, ref):
    if kind == "ruling.ready":
        return find_exact(notes, kind, lambda data: data.get("ruling") == ref, ready_index)
    if kind == "decision.batch.ready":
        match = re.fullmatch(r"B([1-9][0-9]*)", ref)
        if not match:
            fail("a decision.batch.ready state_ref must read B<N>")
        number = int(match.group(1))
        return find_exact(notes, kind, lambda data: data.get("batch") == number, ready_index)
    if kind == "decision.batch.supplemented":
        return find_exact(notes, kind, lambda data: data.get("after_op") == ref, ready_index)
    if kind == "decision.recheck.completed":
        return find_exact(
            notes,
            kind,
            lambda data: data.get("commit_op") == ref or data.get("basis_ref") == ref,
            ready_index,
        )
    if kind == "decision.conflict.ready":
        match = re.fullmatch(r"(R[1-9][0-9]*|B[1-9][0-9]*)/C([1-9][0-9]*)", ref)
        if not match:
            fail("a decision.conflict.ready state_ref must read <owner>/C<N>")
        owner, conflict = match.group(1), int(match.group(2))
        result = find_exact(
            notes,
            kind,
            lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
            ready_index,
        )
        for required in ("opened", "sourced", "settled"):
            find_exact(
                notes,
                f"decision.conflict.{required}",
                lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
                ready_index,
            )
        return result
    fail(f"unsupported spec edit state_kind {kind!r}")


def current_route(notes, ready_index, owner):
    route = status = None
    batch_number = None
    if owner.startswith("R"):
        find_exact(notes, "decision.escalated", lambda data: data.get("ruling") == owner, ready_index)
        _, ruling = find_exact(notes, "ruling", lambda data: data.get("ruling") == owner, ready_index)
        find_exact(notes, "ruling.ready", lambda data: data.get("ruling") == owner, ready_index)
        route, status = note_data(ruling).get("route"), "active"
    else:
        batch, decision = owner.split("/", 1)
        batch_number = int(batch[1:])
        find_exact(notes, "decision.batch.opened", lambda data: data.get("batch") == batch_number, ready_index)
        _, sourced = find_exact(
            notes, "decision.batch.sourced", lambda data: data.get("batch") == batch_number, ready_index
        )
        source_decisions = note_data(sourced).get("decisions")
        if not isinstance(source_decisions, list) \
                or any(not isinstance(item, str) or not re.fullmatch(r"D[1-9][0-9]*", item)
                       for item in source_decisions) \
                or len(source_decisions) != len(set(source_decisions)) \
                or decision not in source_decisions:
            fail(f"{owner} is not one stable DECISION identity in its immutable batch source")
        _, settled = find_exact(
            notes, "decision.batch.settled", lambda data: data.get("batch") == batch_number, ready_index
        )
        find_exact(notes, "decision.batch.ready", lambda data: data.get("batch") == batch_number, ready_index)
        initial = [answer for answer in (note_data(settled).get("answers") or [])
                   if answer.get("id") == decision]
        if len(initial) == 1:
            route, status = initial[0].get("route"), "active"
        answered = len(initial) == 1

    # Complete later states replace the route in journal order. A ready
    # conflict can carry the whole current-owner action set; its settlement is
    # a fallback for older journals where only changed IDs were structured.
    for index, (_, entry) in enumerate(notes[:ready_index]):
        data = note_data(entry)
        kind = entry.get("kind")
        if kind == "decision.batch.supplemented" and owner.startswith("B") \
                and data.get("batch") == batch_number:
            decision = owner.split("/", 1)[1]
            matches = [answer for answer in (data.get("answers") or []) if answer.get("id") == decision]
            if len(matches) == 1:
                route, status = matches[0].get("route"), "active"
                answered = True
        elif kind == "decision.recheck.completed" and data.get("accepted") is True \
                and data.get("missing") == []:
            matches = [action for action in (data.get("actions") or []) if action.get("answer") == owner]
            if len(matches) == 1:
                route, status = matches[0].get("route"), matches[0].get("status")
        elif kind == "decision.conflict.ready":
            matches = [action for action in (data.get("actions") or []) if action.get("answer") == owner]
            if len(matches) == 1:
                route, status = matches[0].get("route"), matches[0].get("status")
                continue
            conflict_owner, conflict = data.get("owner"), data.get("conflict")
            settlements = [candidate for _, candidate in notes[:index]
                           if candidate.get("kind") == "decision.conflict.settled"
                           and note_data(candidate).get("owner") == conflict_owner
                           and note_data(candidate).get("conflict") == conflict]
            if len(settlements) == 1:
                updates = note_data(settlements[0]).get("updates") or []
                changed = [update for update in updates if update.get("id") == owner]
                if len(changed) == 1:
                    route, status = changed[0].get("route"), changed[0].get("status")
    if route is None or status is None:
        fail(f"no complete durable state gives {owner} a current route")
    if owner.startswith("B") and not answered:
        fail(f"no atomic batch answer group ever answered {owner}")
    return route, status


def validate_artifact(entry):
    data = note_data(entry)
    raw_path = entry.get("text")
    if not isinstance(raw_path, str) or not raw_path:
        fail("spec.edit.ready must name its exact state artifact in text")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("reports",):
        fail("the spec edit state artifact must be workspace-relative under reports/")
    path = WORKSPACE
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            fail(f"the spec edit state artifact may not traverse a symlink: {raw_path}")
    if not path.is_file():
        fail(f"the spec edit state artifact is absent or not a real file: {raw_path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = data.get("artifact_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or actual != expected:
        fail("the spec edit state artifact does not match its recorded SHA-256")
    return expected


def validate_spec_loop_artifacts(notes):
    for _, entry in notes:
        data = note_data(entry)
        if entry.get("kind") != "decision.recheck.completed" or data.get("owner") != "spec-loop":
            continue
        raw_path = entry.get("text")
        if not isinstance(raw_path, str) or not raw_path:
            fail("a SPEC-loop recheck has no immutable artifact")
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("reports",):
            fail("a SPEC-loop recheck artifact must be workspace-relative under reports/")
        path = WORKSPACE
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                fail("a SPEC-loop recheck artifact may not traverse a symlink")
        if not path.is_file():
            fail("a SPEC-loop recheck artifact is absent")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != data.get("artifact_sha256"):
            fail("a SPEC-loop recheck artifact changed")
        try:
            artifact = json.loads(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            fail(f"a SPEC-loop recheck artifact is not complete JSON: {exc}")
        expected = dict(data)
        expected.pop("artifact_sha256", None)
        if artifact != expected:
            fail("a SPEC-loop recheck artifact differs from its structured result")


def validate_ready(notes, ready_index, entry, form, owner, spec_path_sha256):
    data = note_data(entry)
    expected_route = "spec-repair" if form == "breach" else "spec-in-place"
    required = ("op", "owner", "status", "route", "state_kind", "state_ref",
                "source_sha", "spec_path_sha256", "artifact_sha256")
    missing = [key for key in required if key not in data]
    if missing:
        fail("spec.edit.ready lacks: " + ", ".join(missing))
    if data.get("owner") != owner or data.get("status") != "active" or data.get("route") != expected_route:
        fail("spec.edit.ready does not authorise this active owner and route")
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", str(data.get("op"))):
        fail("spec.edit.ready has an invalid operation identity")
    matching_ops = [candidate for _, candidate in notes
                    if candidate.get("kind") == "spec.edit.ready"
                    and note_data(candidate).get("op") == data.get("op")]
    if len(matching_ops) != 1:
        fail("spec.edit.ready does not have one unique operation identity")
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(data.get("source_sha"))):
        fail("spec.edit.ready has no full source SHA")
    if data.get("spec_path_sha256") != spec_path_sha256:
        fail("spec.edit.ready authorises a different exact spec path")

    kind, ref = data["state_kind"], str(data["state_ref"])
    source_index, source_state = state_event(notes, ready_index, kind, ref)
    complete_states = [index for index, (_, candidate) in enumerate(notes[:ready_index])
                       if candidate.get("kind") in SPEC_EDIT_STATE_KINDS]
    if not complete_states or source_index != complete_states[-1]:
        fail("spec.edit.ready does not reference the latest complete authority state")
    if kind != "decision.batch.supplemented" and source_state.get("text") != entry.get("text"):
        fail("spec.edit.ready does not hash the artifact published by its source boundary")
    if kind in {"decision.recheck.completed", "decision.conflict.ready"} \
            and note_data(source_state).get("artifact_sha256") != data.get("artifact_sha256"):
        fail("spec.edit.ready does not consume the source boundary's immutable artifact hash")
    validate_artifact(entry)

    if form in {"ruling", "batch"}:
        route, status = current_route(notes, ready_index, owner)
        if route != "spec-in-place" or status != "active":
            fail("the referenced durable state does not make this answer active and spec-in-place")
    else:
        if kind != "decision.conflict.ready":
            fail("a breach repair must consume decision.conflict.ready")
        match = re.fullmatch(r"(R[1-9][0-9]*|B[1-9][0-9]*)/C([1-9][0-9]*)", ref)
        conflict_owner, conflict = match.group(1), int(match.group(2))
        breach_match = re.fullmatch(r"breach-([1-9][0-9]*)/C([1-9][0-9]*)", owner)
        breach, wanted_conflict = int(breach_match.group(1)), int(breach_match.group(2))
        if conflict != wanted_conflict:
            fail("the ready conflict number disagrees with the requested breach repair")
        _, opening = find_exact(
            notes,
            "decision.conflict.opened",
            lambda item: item.get("owner") == conflict_owner and item.get("conflict") == conflict,
            ready_index,
        )
        opening_data = note_data(opening)
        if opening_data.get("breach") != breach or opening_data.get("purpose") != "restore-baseline":
            fail("the conflict is not this breach's restore-baseline generation")
        _, breach_opening = find_exact(
            notes, "spec.breach.opened", lambda item: item.get("breach") == breach, ready_index
        )
        if note_data(breach_opening).get("owner") != conflict_owner:
            fail("the recovery conflict does not belong to this breach's owner")
        if opening_data.get("state_kind") != "decision.recheck.completed":
            fail("the recovery conflict does not source this breach's adverse recheck")
        adverse_ref = str(opening_data.get("state_ref"))
        find_exact(
            notes,
            "decision.recheck.completed",
            lambda item: item.get("breach") == breach and str(item.get("basis_ref")) == adverse_ref
            and item.get("restored") is False,
            ready_index,
        )
        _, ready = state_event(notes, ready_index, kind, ref)
        if note_data(ready).get("effect") != "spec-repair":
            fail("the ready recovery resolution selected no spec repair")
        later_recovery = [item for _, item in notes[:ready_index]
                          if item.get("kind") == "decision.conflict.opened"
                          and note_data(item).get("breach") == breach
                          and note_data(item).get("purpose") == "restore-baseline"
                          and note_data(item).get("conflict", 0) > conflict]
        if later_recovery:
            fail("a later restore-baseline conflict supersedes this repair target")

    return data


def validate_no_unfinished_authority(notes, ready_index, form, owner):
    entries = [entry for _, entry in notes[:ready_index + 1]]
    allowed_breach = None
    if form == "breach":
        allowed_breach = int(re.fullmatch(r"breach-([1-9][0-9]*)/C[1-9][0-9]*", owner).group(1))
    ready_operation = note_data(notes[ready_index][1]).get("op")
    try:
        validate_global_authority_precedence(
            entries,
            allowed_open_breach=allowed_breach,
            allowed_ready_op=ready_operation,
        )
    except AuthorityPrecedenceError as exc:
        fail(str(exc))
    validate_spec_loop_artifacts(notes[:ready_index + 1])


def main():
    if len(sys.argv) != 6 or sys.argv[1] not in {"fresh", "retry"}:
        fail("usage: spec_edit_auth.py <fresh|retry> <ruling|batch|breach> <owner> <head|ready-op> <spec-path-sha256>")
    mode, form, owner, selector, spec_path_sha256 = sys.argv[1:]
    if not re.fullmatch(r"[0-9a-f]{64}", spec_path_sha256):
        fail("invalid exact spec-path SHA-256")
    if form == "ruling" and not re.fullmatch(r"R[1-9][0-9]*", owner):
        fail("invalid ruling owner")
    if form == "batch" and not re.fullmatch(r"B[1-9][0-9]*/D[1-9][0-9]*", owner):
        fail("invalid batch answer owner")
    if form == "breach" and not re.fullmatch(r"breach-[1-9][0-9]*/C[1-9][0-9]*", owner):
        fail("invalid breach repair owner")

    notes = read_notes()
    entries = [entry for _, entry in notes]
    try:
        validate_authority_boundary_identities(entries)
    except AuthorityPrecedenceError as exc:
        fail(str(exc))
    committed = {note_data(entry).get("ready_op") for _, entry in notes
                 if entry.get("kind") == "spec.committed"}
    candidates = []
    for index, (_, entry) in enumerate(notes):
        if entry.get("kind") != "spec.edit.ready":
            continue
        data = note_data(entry)
        if mode == "fresh":
            later_authority = any(is_authority_boundary(later)
                                  for _, later in notes[index + 1:])
            if data.get("owner") == owner and data.get("source_sha") == selector \
                    and data.get("op") not in committed and not later_authority:
                candidates.append((index, entry))
        elif data.get("op") == selector:
            candidates.append((index, entry))
    if len(candidates) != 1:
        fail(f"expected exactly one usable spec.edit.ready, found {len(candidates)}")
    ready_index, entry = candidates[0]
    data = validate_ready(notes, ready_index, entry, form, owner, spec_path_sha256)

    if mode == "fresh":
        validate_no_unfinished_authority(notes, ready_index, form, owner)
        later = [later for _, later in notes[ready_index + 1:]
                 if is_authority_boundary(later)]
        if later:
            fail("a later authority boundary supersedes spec.edit.ready")
    output = (data["op"], data["state_kind"], str(data["state_ref"]),
              data["artifact_sha256"], data["source_sha"])
    for value in output:
        sys.stdout.buffer.write(str(value).encode() + b"\0")


if __name__ == "__main__":
    main()
