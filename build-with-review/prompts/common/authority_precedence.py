"""Shared run-wide authority-precedence checks for product-route consumers.

The journal remains the source of truth.  A consumer may act only after every
authority generation that precedes it has reached its complete state boundary.
"""

import re


class AuthorityPrecedenceError(ValueError):
    """The journal has a higher-precedence authority state that is not settled."""


AUTHORITY_BOUNDARY_KINDS = {
    "decision.escalated",
    "ruling",
    "ruling.ready",
    "decision.batch.opened",
    "decision.batch.sourced",
    "decision.batch.settled",
    "decision.batch.ready",
    "decision.batch.supplemented",
    "decision.recheck.completed",
    "decision.conflict.opened",
    "decision.conflict.sourced",
    "decision.conflict.settled",
    "decision.conflict.ready",
    "spec.breach.opened",
    "spec.breach.corrected",
    "spec.breach.restored",
    "spec.edit.ready",
}

RULING_ID = re.compile(r"R[1-9][0-9]*")
BATCH_ID = re.compile(r"B[1-9][0-9]*")
BATCH_ANSWER_ID = re.compile(r"B[1-9][0-9]*/D[1-9][0-9]*")
BREACH_REPAIR_ID = re.compile(r"breach-[1-9][0-9]*/C[1-9][0-9]*")
CONFLICT_REF = re.compile(r"(?:R[1-9][0-9]*|B[1-9][0-9]*)/C[1-9][0-9]*")
DECISION_ID = re.compile(r"D[1-9][0-9]*")
OPERATION_ID = re.compile(r"[A-Za-z0-9._:-]+")
ANSWER_ID = re.compile(r"(?:R[1-9][0-9]*|B[1-9][0-9]*/D[1-9][0-9]*)")
SHA_ID = re.compile(r"[0-9a-f]{40,64}")
ARTIFACT_SHA = re.compile(r"[0-9a-f]{64}")
DIRECT_ROUTES = {
    "closed", "spec-in-place", "amendment", "spec-fixer", "amendment-fixer",
}
BATCH_ROUTES = {"closed", "implementation", "sublot", "spec-in-place", "amendment"}
CONFLICT_ACTIONS = {"keep", "supersede", "qualify", "replace", "reconcile"}
SPEC_EDIT_STATE_KINDS = {
    "ruling.ready",
    "decision.batch.ready",
    "decision.batch.supplemented",
    "decision.recheck.completed",
    "decision.conflict.ready",
}


def note_data(entry):
    data = entry.get("data")
    return data if isinstance(data, dict) else {}


def positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def require_pattern(value, pattern, subject):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise AuthorityPrecedenceError(f"malformed {subject}: {value!r}")
    return value


def require_operation(value, subject):
    return require_pattern(value, OPERATION_ID, subject)


def validate_spec_edit_state_ref(kind, value):
    patterns = {
        "ruling.ready": RULING_ID,
        "decision.batch.ready": BATCH_ID,
        "decision.batch.supplemented": OPERATION_ID,
        "decision.conflict.ready": CONFLICT_REF,
    }
    if kind == "decision.recheck.completed":
        if isinstance(value, str) and (
            OPERATION_ID.fullmatch(value) or CONFLICT_REF.fullmatch(value)
        ):
            return value
        raise AuthorityPrecedenceError(
            f"malformed spec.edit.ready {kind} state_ref: {value!r}"
        )
    return require_pattern(value, patterns[kind], f"spec.edit.ready {kind} state_ref")


def authority_boundary_identity(entry):
    """Return one boundary's durable key, or None for a non-authority event.

    An operational `ruling` deliberately has no `ruling` key. Every other
    authority kind is fail-closed: malformed data is ambiguous durable state.
    """
    kind = entry.get("kind")
    if kind not in AUTHORITY_BOUNDARY_KINDS:
        return None
    raw_data = entry.get("data")
    if kind == "ruling" and (
        raw_data is None or isinstance(raw_data, dict) and "ruling" not in raw_data
    ):
        return None
    if not isinstance(raw_data, dict):
        raise AuthorityPrecedenceError(f"malformed {kind}: data must be an object")
    data = raw_data

    if kind in {"decision.escalated", "ruling", "ruling.ready"}:
        ruling = require_pattern(data.get("ruling"), RULING_ID, f"{kind} ruling identity")
        return kind, ruling

    if kind in {
        "decision.batch.opened", "decision.batch.sourced",
        "decision.batch.settled", "decision.batch.ready",
    }:
        batch = data.get("batch")
        if not positive_integer(batch):
            raise AuthorityPrecedenceError(f"malformed {kind} batch identity: {batch!r}")
        return kind, batch

    if kind == "decision.batch.supplemented":
        batch = data.get("batch")
        if not positive_integer(batch):
            raise AuthorityPrecedenceError(f"malformed {kind} batch identity: {batch!r}")
        after_op = require_operation(data.get("after_op"), f"{kind} after_op")
        return kind, batch, after_op

    if kind == "decision.recheck.completed":
        if "breach" in data:
            breach = data.get("breach")
            if not positive_integer(breach):
                raise AuthorityPrecedenceError(f"malformed breach recheck identity: {breach!r}")
            owner = data.get("owner")
            if not isinstance(owner, str) or not (
                RULING_ID.fullmatch(owner) or BATCH_ID.fullmatch(owner)
            ):
                raise AuthorityPrecedenceError(f"malformed breach recheck owner: {owner!r}")
            basis_kind = data.get("basis_kind")
            if basis_kind not in {
                "spec.breach.corrected", "spec.committed", "decision.conflict.ready",
            }:
                raise AuthorityPrecedenceError(
                    f"malformed breach recheck basis_kind: {basis_kind!r}"
                )
            basis_ref = data.get("basis_ref")
            if basis_kind == "decision.conflict.ready":
                require_pattern(basis_ref, CONFLICT_REF, "breach recheck basis_ref")
            else:
                require_operation(basis_ref, "breach recheck basis_ref")
            return kind, "breach", breach, basis_kind, basis_ref
        if "batch" in data:
            batch = data.get("batch")
            if not positive_integer(batch):
                raise AuthorityPrecedenceError(f"malformed batch recheck identity: {batch!r}")
            decision = require_pattern(
                data.get("decision"), DECISION_ID, "batch recheck decision identity"
            )
            commit_op = require_operation(data.get("commit_op"), "batch recheck commit_op")
            return kind, "batch", batch, decision, commit_op
        owner = data.get("owner")
        if owner != "spec-loop":
            require_pattern(owner, RULING_ID, "direct recheck owner")
        commit_op = require_operation(data.get("commit_op"), "direct recheck commit_op")
        return kind, "owner", owner, commit_op

    if kind.startswith("decision.conflict."):
        owner = data.get("owner")
        if not isinstance(owner, str) or not (
            RULING_ID.fullmatch(owner) or BATCH_ID.fullmatch(owner)
        ):
            raise AuthorityPrecedenceError(f"malformed {kind} owner: {owner!r}")
        conflict = data.get("conflict")
        if not positive_integer(conflict):
            raise AuthorityPrecedenceError(f"malformed {kind} conflict identity: {conflict!r}")
        return kind, owner, conflict

    if kind.startswith("spec.breach."):
        breach = data.get("breach")
        if not positive_integer(breach):
            raise AuthorityPrecedenceError(f"malformed {kind} breach identity: {breach!r}")
        return kind, breach

    if kind == "spec.edit.ready":
        operation = require_operation(data.get("op"), "spec.edit.ready operation identity")
        owner = data.get("owner")
        if not isinstance(owner, str) or not (
            RULING_ID.fullmatch(owner)
            or BATCH_ANSWER_ID.fullmatch(owner)
            or BREACH_REPAIR_ID.fullmatch(owner)
        ):
            raise AuthorityPrecedenceError(f"malformed spec.edit.ready owner: {owner!r}")
        state_kind = data.get("state_kind")
        if state_kind not in SPEC_EDIT_STATE_KINDS:
            raise AuthorityPrecedenceError(
                f"malformed spec.edit.ready state_kind: {state_kind!r}"
            )
        state_ref = validate_spec_edit_state_ref(state_kind, data.get("state_ref"))
        return kind, operation, owner, state_kind, state_ref

    raise AuthorityPrecedenceError(f"no identity schema for authority boundary {kind}")


def validate_authority_boundary_identities(entries):
    for entry in entries:
        authority_boundary_identity(entry)


def is_authority_boundary(entry):
    return authority_boundary_identity(entry) is not None


def exact_order(entries, kinds, predicate, subject):
    positions = []
    for kind in kinds:
        matches = [index for index, entry in enumerate(entries)
                   if entry.get("kind") == kind and predicate(note_data(entry))]
        if len(matches) != 1:
            raise AuthorityPrecedenceError(
                f"unfinished or ambiguous {subject}: expected one {kind}, found {len(matches)}"
            )
        positions.append(matches[0])
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise AuthorityPrecedenceError(f"out-of-order {subject} authority chain")


def validate_rulings(entries):
    identities = set()
    for entry in entries:
        if entry.get("kind") not in {"decision.escalated", "ruling", "ruling.ready"}:
            continue
        identity = note_data(entry).get("ruling")
        if isinstance(identity, str) and re.fullmatch(r"R[1-9][0-9]*", identity):
            identities.add(identity)
    for identity in identities:
        exact_order(
            entries,
            ("decision.escalated", "ruling", "ruling.ready"),
            lambda data, wanted=identity: data.get("ruling") == wanted,
            f"identified ruling {identity}",
        )


def validate_batches(entries):
    identities = set()
    batch_kinds = {
        "decision.batch.opened", "decision.batch.sourced",
        "decision.batch.settled", "decision.batch.ready", "decision.batch.supplemented",
    }
    for entry in entries:
        if entry.get("kind") in batch_kinds:
            batch = note_data(entry).get("batch")
            if isinstance(batch, int) and batch > 0:
                identities.add(batch)
    for batch in identities:
        exact_order(
            entries,
            ("decision.batch.opened", "decision.batch.sourced",
             "decision.batch.settled", "decision.batch.ready"),
            lambda data, wanted=batch: data.get("batch") == wanted,
            f"decision batch B{batch}",
        )
    supplements = set()
    for entry in entries:
        if entry.get("kind") != "decision.batch.supplemented":
            continue
        data = note_data(entry)
        identity = data["batch"], data["after_op"]
        if identity in supplements:
            raise AuthorityPrecedenceError(
                f"ambiguous decision batch supplement B{identity[0]} after {identity[1]}"
            )
        supplements.add(identity)


def exact_indexed(entries, kind, predicate, subject, *, before=None):
    end = len(entries) if before is None else before
    matches = [(index, entry) for index, entry in enumerate(entries[:end])
               if entry.get("kind") == kind and predicate(note_data(entry))]
    if len(matches) != 1:
        raise AuthorityPrecedenceError(
            f"{subject}: expected one {kind}, found {len(matches)}"
        )
    return matches[0]


def answer_route(identity, route):
    routes = DIRECT_ROUTES if RULING_ID.fullmatch(identity) else BATCH_ROUTES
    return route in routes


def validate_answer_action(action, subject, *, key="answer"):
    if not isinstance(action, dict):
        raise AuthorityPrecedenceError(f"{subject} has a malformed action")
    identity = action.get(key)
    require_pattern(identity, ANSWER_ID, f"{subject} answer identity")
    status, route = action.get("status"), action.get("route")
    if status not in {"active", "superseded"}:
        raise AuthorityPrecedenceError(f"{subject} has an invalid status for {identity}")
    if status == "active" and not answer_route(identity, route):
        raise AuthorityPrecedenceError(f"{subject} has an invalid active route for {identity}")
    if status == "superseded" and route is not None:
        raise AuthorityPrecedenceError(
            f"{subject} gives superseded answer {identity} a route"
        )
    return identity, status, route


def global_answer_state(entries, before):
    """Reconstruct structured answer status and route before one boundary."""
    state = {}
    for index, entry in enumerate(entries[:before]):
        data, kind = note_data(entry), entry.get("kind")
        if kind == "ruling" and isinstance(data.get("ruling"), str) \
                and RULING_ID.fullmatch(data["ruling"]):
            state[data["ruling"]] = {"status": "active", "route": data.get("route")}
        elif kind in {"decision.batch.settled", "decision.batch.supplemented"} \
                and positive_integer(data.get("batch")):
            batch = data["batch"]
            for answer in data.get("answers") or []:
                if isinstance(answer, dict) and DECISION_ID.fullmatch(str(answer.get("id"))):
                    identity = f"B{batch}/{answer['id']}"
                    state[identity] = {"status": "active", "route": answer.get("route")}
        elif kind == "decision.recheck.completed" and data.get("accepted") is True \
                and data.get("missing") == [] and "breach" not in data \
                and data.get("owner") != "spec-loop":
            for action in data.get("actions") or []:
                if isinstance(action, dict) and ANSWER_ID.fullmatch(str(action.get("answer"))):
                    state[action["answer"]] = {
                        "status": action.get("status"), "route": action.get("route"),
                    }
        elif kind == "decision.conflict.ready":
            owner, conflict = data.get("owner"), data.get("conflict")
            settlements = [candidate for candidate in entries[:index]
                           if candidate.get("kind") == "decision.conflict.settled"
                           and note_data(candidate).get("owner") == owner
                           and note_data(candidate).get("conflict") == conflict]
            if len(settlements) == 1:
                for update in note_data(settlements[0]).get("updates") or []:
                    if isinstance(update, dict) and update.get("id") in state:
                        state[update["id"]] = {
                            "status": update.get("status"), "route": update.get("route"),
                        }
            for action in data.get("actions") or []:
                if isinstance(action, dict) and action.get("answer") in state:
                    state[action["answer"]] = {
                        "status": action.get("status"), "route": action.get("route"),
                    }
    return state


def latest_owner_generation(entries, before, owner):
    if RULING_ID.fullmatch(owner):
        exact_indexed(
            entries, "ruling.ready", lambda data: data.get("ruling") == owner,
            f"authority generation for {owner}", before=before,
        )
        generation = "ruling.ready", owner
    else:
        batch = int(owner.split("/", 1)[0][1:])
        exact_indexed(
            entries, "decision.batch.ready", lambda data: data.get("batch") == batch,
            f"authority generation for {owner}", before=before,
        )
        generation = "decision.batch.ready", f"B{batch}"

    for index, entry in enumerate(entries[:before]):
        data, kind = note_data(entry), entry.get("kind")
        if kind == "decision.batch.supplemented" and not RULING_ID.fullmatch(owner) \
                and data.get("batch") == batch:
            generation = kind, data.get("after_op")
        elif kind == "decision.recheck.completed" and data.get("accepted") is True \
                and data.get("missing") == [] and any(
                    isinstance(action, dict) and action.get("answer") == owner
                    for action in data.get("actions") or []
                ):
            generation = kind, data.get("commit_op")
        elif kind == "decision.conflict.ready":
            conflict_owner, conflict = data.get("owner"), data.get("conflict")
            changed = any(
                isinstance(action, dict) and action.get("answer") == owner
                for action in data.get("actions") or []
            )
            if not changed:
                settlements = [candidate for candidate in entries[:index]
                               if candidate.get("kind") == "decision.conflict.settled"
                               and note_data(candidate).get("owner") == conflict_owner
                               and note_data(candidate).get("conflict") == conflict]
                changed = len(settlements) == 1 and any(
                    isinstance(update, dict) and update.get("id") == owner
                    for update in note_data(settlements[0]).get("updates") or []
                )
            if changed:
                generation = kind, f"{conflict_owner}/C{conflict}"
    return generation


def validate_recheck_generation(entries, recheck_index):
    """Authenticate one direct or batch post-commit replacement snapshot."""
    entry = entries[recheck_index]
    data = note_data(entry)
    if entry.get("kind") != "decision.recheck.completed" or "breach" in data \
            or data.get("owner") == "spec-loop":
        return

    if "batch" in data:
        batch, decision = data.get("batch"), data.get("decision")
        if not positive_integer(batch):
            raise AuthorityPrecedenceError("a batch recheck has no positive batch identity")
        require_pattern(decision, DECISION_ID, "batch recheck decision identity")
        owner = f"B{batch}/{decision}"
        commit_predicate = lambda item: item.get("batch") == batch \
            and item.get("decision") == decision \
            and item.get("op") == data.get("commit_op") \
            and item.get("sha") == data.get("sha")
    else:
        owner = require_pattern(data.get("owner"), RULING_ID, "direct recheck owner")
        commit_predicate = lambda item: item.get("ruling") == owner \
            and item.get("op") == data.get("commit_op") \
            and item.get("sha") == data.get("sha")

    require_operation(data.get("commit_op"), "recheck commit_op")
    require_pattern(data.get("sha"), SHA_ID, "recheck SHA")
    commit_index, commit = exact_indexed(
        entries, "spec.committed", commit_predicate,
        f"recheck for {owner}", before=recheck_index,
    )
    commit_data = note_data(commit)
    ready_op = require_operation(commit_data.get("ready_op"), "bound commit ready_op")
    ready_index, ready = exact_indexed(
        entries, "spec.edit.ready",
        lambda item: item.get("op") == ready_op and item.get("owner") == owner,
        f"bound commit for {owner}", before=commit_index,
    )
    ready_data = note_data(ready)
    for field in ("state_kind", "state_ref", "artifact_sha256"):
        if commit_data.get(field) != ready_data.get(field):
            raise AuthorityPrecedenceError(
                f"recheck for {owner} has a commit that changes ready field {field}"
            )
    require_pattern(commit_data.get("artifact_sha256"), ARTIFACT_SHA,
                    "bound commit authority artifact SHA-256")
    if ready_data.get("status") != "active" or ready_data.get("route") != "spec-in-place":
        raise AuthorityPrecedenceError(f"bound commit for {owner} has no active spec-in-place capability")
    if (ready_data.get("state_kind"), ready_data.get("state_ref")) \
            != latest_owner_generation(entries, ready_index, owner):
        raise AuthorityPrecedenceError(f"bound commit for {owner} does not consume its current generation")
    if any(is_authority_boundary(candidate)
           for candidate in entries[ready_index + 1:commit_index]):
        raise AuthorityPrecedenceError(f"a later authority boundary supersedes {owner}'s bound commit")
    if any(is_authority_boundary(candidate)
           for candidate in entries[commit_index + 1:recheck_index]):
        raise AuthorityPrecedenceError(f"a later authority boundary supersedes {owner}'s recheck")

    accepted, missing = data.get("accepted"), data.get("missing")
    if not isinstance(accepted, bool) or not isinstance(missing, list) \
            or any(not isinstance(identity, str) or not ANSWER_ID.fullmatch(identity)
                   for identity in missing) or len(missing) != len(set(missing)) \
            or accepted != (missing == []):
        raise AuthorityPrecedenceError(f"recheck for {owner} has an inconsistent accepted result")
    require_pattern(data.get("artifact_sha256"), ARTIFACT_SHA,
                    "recheck artifact SHA-256")

    prior = global_answer_state(entries, commit_index)
    if owner not in prior or prior[owner] != {"status": "active", "route": "spec-in-place"}:
        raise AuthorityPrecedenceError(f"recheck commit owner {owner} was not active and spec-in-place")
    expected = {owner} if RULING_ID.fullmatch(owner) else {
        identity for identity in prior if identity.startswith(owner.split("/", 1)[0] + "/")
    }
    if not RULING_ID.fullmatch(owner):
        _, source = exact_indexed(
            entries, "decision.batch.sourced", lambda item: item.get("batch") == batch,
            f"batch recheck source for {owner}", before=recheck_index,
        )
        source_items = note_data(source).get("items")
        if not isinstance(source_items, list):
            raise AuthorityPrecedenceError(f"batch recheck for {owner} has no immutable source index")
        source_ids = [item.get("id") for item in source_items if isinstance(item, dict)]
        recheck_items = data.get("items")
        if not isinstance(recheck_items, list) or len(source_ids) != len(source_items) \
                or len(source_ids) != len(set(source_ids)) \
                or any(not re.fullmatch(r"[FD][1-9][0-9]*", str(identity))
                       for identity in source_ids) \
                or len(recheck_items) != len(source_ids) \
                or {item.get("id") for item in recheck_items if isinstance(item, dict)} != set(source_ids) \
                or any(not isinstance(item, dict) or item.get("verdict") not in {"confirmed", "refuted"}
                       for item in recheck_items):
            raise AuthorityPrecedenceError(
                f"batch recheck for {owner} has no complete immutable item replacement state"
            )
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise AuthorityPrecedenceError(f"recheck for {owner} has no complete action state")
    actual = {}
    for action in actions:
        identity, status, route = validate_answer_action(action, f"recheck for {owner}")
        if identity in actual:
            raise AuthorityPrecedenceError(f"recheck for {owner} repeats {identity}")
        actual[identity] = {"status": status, "route": route}
    if set(actual) != expected:
        raise AuthorityPrecedenceError(f"recheck for {owner} has an incomplete owner action state")
    if RULING_ID.fullmatch(owner) and accepted \
            and actual[owner] != {"status": "active", "route": "spec-in-place"}:
        raise AuthorityPrecedenceError(
            f"an accepted direct recheck cannot replace {owner}'s bound route"
        )

    duplicates = [candidate for candidate in entries[:recheck_index]
                  if candidate.get("kind") == "decision.recheck.completed"
                  and note_data(candidate).get("commit_op") == data.get("commit_op")
                  and "breach" not in note_data(candidate)]
    if duplicates:
        raise AuthorityPrecedenceError(f"bound commit {data.get('commit_op')} already has a recheck")


def authority_tuple(data):
    fields = (data.get("authority_kind"), data.get("authority_ref"), data.get("authority_sha256"))
    if fields[0] not in {"ruling.ready", "decision.conflict.ready"} \
            or not isinstance(fields[1], str) or not ARTIFACT_SHA.fullmatch(str(fields[2])):
        return None
    return fields


def pending_spec_fixer_assignments(entries, before):
    state = global_answer_state(entries, before)
    pending = {}
    for identity, answer in state.items():
        if not RULING_ID.fullmatch(identity) \
                or answer != {"status": "active", "route": "spec-fixer"}:
            continue
        generation = latest_owner_generation(entries, before, identity)
        matches = []
        for index, entry in enumerate(entries[:before]):
            data = note_data(entry)
            if entry.get("kind") != "fixer.dispatched" or data.get("ruling") != identity \
                    or data.get("route") != "spec-fixer" \
                    or (data.get("authority_kind"), data.get("authority_ref")) != generation:
                continue
            authority = authority_tuple(data)
            if authority is None:
                raise AuthorityPrecedenceError(
                    f"spec-fixer assignment for {identity} has malformed authority"
                )
            terminal = any(
                candidate.get("kind") == "ruling.applied"
                and note_data(candidate).get("ruling") == identity
                and authority_tuple(note_data(candidate)) == authority
                for candidate in entries[index + 1:before]
            )
            if not terminal:
                matches.append((index, data, authority))
        if len(matches) != 1:
            raise AuthorityPrecedenceError(
                f"pending spec-fixer {identity} requires one exact owner-linked dispatch; found {len(matches)}"
            )
        _, data, authority = matches[0]
        pending[identity] = {
            "ruling": identity,
            "authority_kind": authority[0],
            "authority_ref": authority[1],
            "authority_sha256": authority[2],
        }
    return pending


def validate_spec_loop_generation(entries, recheck_index):
    entry = entries[recheck_index]
    data = note_data(entry)
    if entry.get("kind") != "decision.recheck.completed" or data.get("owner") != "spec-loop":
        return
    commit_op = require_operation(data.get("commit_op"), "SPEC-loop recheck commit_op")
    sha = require_pattern(data.get("sha"), SHA_ID, "SPEC-loop recheck SHA")
    commit_index, commit = exact_indexed(
        entries, "spec.committed",
        lambda item: item.get("op") == commit_op and item.get("sha") == sha
        and not any(key in item for key in ("ruling", "batch", "breach")),
        "SPEC-loop shared close", before=recheck_index,
    )
    commit_data = note_data(commit)
    if not positive_integer(commit_data.get("spec_round")) \
            or not ARTIFACT_SHA.fullmatch(str(commit_data.get("review_sha256"))) \
            or not ARTIFACT_SHA.fullmatch(str(commit_data.get("spec_sha256"))):
        raise AuthorityPrecedenceError("SPEC-loop shared close lacks its clean-round proof")
    if any(is_authority_boundary(candidate) for candidate in entries[commit_index + 1:recheck_index]):
        raise AuthorityPrecedenceError("a later authority boundary supersedes the SPEC-loop recheck")

    expected_rulings = pending_spec_fixer_assignments(entries, commit_index)
    if not expected_rulings:
        raise AuthorityPrecedenceError("SPEC-loop recheck has no pending spec-fixer assignment")
    supplied_rulings = data.get("rulings")
    if not isinstance(supplied_rulings, list):
        raise AuthorityPrecedenceError("SPEC-loop recheck has no complete ruling set")
    actual_rulings = {}
    for member in supplied_rulings:
        if not isinstance(member, dict) or set(member) != {
            "ruling", "authority_kind", "authority_ref", "authority_sha256",
        } or not RULING_ID.fullmatch(str(member.get("ruling"))) \
                or authority_tuple(member) is None or member["ruling"] in actual_rulings:
            raise AuthorityPrecedenceError("SPEC-loop recheck has a malformed or duplicate ruling member")
        actual_rulings[member["ruling"]] = member
    if actual_rulings != expected_rulings:
        raise AuthorityPrecedenceError("SPEC-loop recheck does not name the exact pending spec-fixer set")

    prior = global_answer_state(entries, commit_index)
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise AuthorityPrecedenceError("SPEC-loop recheck has no complete global action state")
    actual_actions = {}
    for action in actions:
        identity, status, route = validate_answer_action(action, "SPEC-loop recheck")
        if identity in actual_actions:
            raise AuthorityPrecedenceError(f"SPEC-loop recheck repeats {identity}")
        actual_actions[identity] = {"status": status, "route": route}
    if actual_actions != prior:
        raise AuthorityPrecedenceError("SPEC-loop recheck changes or omits the prior global answer state")

    verifier_results = data.get("verifiers")
    if not isinstance(verifier_results, list):
        raise AuthorityPrecedenceError("SPEC-loop recheck has no complete verifier result set")
    actual_verifiers = {}
    for result in verifier_results:
        if not isinstance(result, dict) or set(result) != {"ruling", "present"} \
                or result.get("ruling") not in expected_rulings \
                or not isinstance(result.get("present"), bool) \
                or result["ruling"] in actual_verifiers:
            raise AuthorityPrecedenceError("SPEC-loop recheck has a malformed verifier result")
        actual_verifiers[result["ruling"]] = result["present"]
    if set(actual_verifiers) != set(expected_rulings):
        raise AuthorityPrecedenceError("SPEC-loop recheck omits a pending ruling verifier")
    for ruling, member in expected_rulings.items():
        starts = [(index, candidate) for index, candidate in enumerate(entries[commit_index + 1:recheck_index], commit_index + 1)
                  if candidate.get("event") == "subagent-started"
                  and candidate.get("kind") == "finding-verifier"
                  and note_data(candidate).get("owner") == "spec-loop"
                  and note_data(candidate).get("commit_op") == commit_op
                  and note_data(candidate).get("ruling") == ruling]
        ends = [(index, candidate) for index, candidate in enumerate(entries[commit_index + 1:recheck_index], commit_index + 1)
                if candidate.get("event") == "subagent-ended"
                and candidate.get("kind") == "finding-verifier"
                and note_data(candidate).get("owner") == "spec-loop"
                and note_data(candidate).get("commit_op") == commit_op
                and note_data(candidate).get("ruling") == ruling]
        common = {
            "owner": "spec-loop", "commit_op": commit_op, "sha": sha, "ruling": ruling,
            **{key: member[key] for key in ("authority_kind", "authority_ref", "authority_sha256")},
        }
        if not 1 <= len(starts) == len(ends) <= 2:
            raise AuthorityPrecedenceError(
                f"SPEC-loop recheck lacks one bounded completed verifier chain for {ruling}"
            )
        for call, ((start_index, start), (end_index, end)) in enumerate(zip(starts, ends), 1):
            if start_index >= end_index or call < len(starts) \
                    and end_index >= starts[call][0]:
                raise AuthorityPrecedenceError(
                    f"SPEC-loop verifier physical calls for {ruling} are out of order"
                )
            start_data, end_data = note_data(start), note_data(end)
            expected_end = ({**common, "present": actual_verifiers[ruling]}
                            if call == len(starts) else {**common, "unusable": end_data.get("unusable")})
            if start_data != common or end_data != expected_end \
                    or call < len(starts) and end_data.get("unusable") not in {
                        "error", "empty", "lost", "unusable",
                    }:
                raise AuthorityPrecedenceError(
                    f"SPEC-loop verifier bracket for {ruling} changes its identity or result"
                )

    missing = data.get("missing")
    expected_missing = sorted(ruling for ruling, present in actual_verifiers.items() if not present)
    accepted = data.get("accepted")
    if not isinstance(accepted, bool) or missing != expected_missing or accepted != (missing == []):
        raise AuthorityPrecedenceError("SPEC-loop recheck has an inconsistent accepted/missing result")
    require_pattern(data.get("artifact_sha256"), ARTIFACT_SHA, "SPEC-loop recheck artifact SHA-256")
    duplicates = [candidate for candidate in entries[:recheck_index]
                  if candidate.get("kind") == "decision.recheck.completed"
                  and note_data(candidate).get("owner") == "spec-loop"
                  and note_data(candidate).get("commit_op") == commit_op]
    if duplicates:
        raise AuthorityPrecedenceError(f"SPEC-loop close {commit_op} already has a recheck")


def validate_rechecks(entries):
    for index, entry in enumerate(entries):
        data = note_data(entry)
        if entry.get("kind") != "decision.recheck.completed" or "breach" in data:
            continue
        if data.get("owner") == "spec-loop":
            validate_spec_loop_generation(entries, index)
        else:
            validate_recheck_generation(entries, index)


def validate_adverse_bound_rechecks(entries):
    """A failed bound recheck owns the run until its existing breach opens."""
    for index, entry in enumerate(entries):
        data = note_data(entry)
        if entry.get("kind") != "decision.recheck.completed" \
                or "breach" in data or data.get("owner") == "spec-loop" \
                or data.get("accepted") is not False:
            continue
        if "batch" in data:
            owner, answer = f"B{data.get('batch')}", f"B{data.get('batch')}/{data.get('decision')}"
        else:
            owner = answer = data.get("owner")
        opened = any(
            candidate.get("kind") == "spec.breach.opened"
            and note_data(candidate).get("owner") == owner
            and note_data(candidate).get("answer") == answer
            and note_data(candidate).get("bad_op") == data.get("commit_op")
            and note_data(candidate).get("bad_sha") == data.get("sha")
            for candidate in entries[index + 1:]
        )
        if not opened:
            raise AuthorityPrecedenceError(
                f"adverse bound recheck {data.get('commit_op')!r} requires its spec breach opening"
            )


def validate_conflict_generation(entries, owner, conflict):
    exact_order(
        entries,
        ("decision.conflict.opened", "decision.conflict.sourced",
         "decision.conflict.settled", "decision.conflict.ready"),
        lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
        f"decision conflict {owner}/C{conflict}",
    )
    opening_index, opening = exact_indexed(
        entries, "decision.conflict.opened",
        lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
        f"decision conflict {owner}/C{conflict}",
    )
    _, sourced = exact_indexed(
        entries, "decision.conflict.sourced",
        lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
        f"decision conflict {owner}/C{conflict}",
    )
    _, settled = exact_indexed(
        entries, "decision.conflict.settled",
        lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
        f"decision conflict {owner}/C{conflict}",
    )
    _, ready = exact_indexed(
        entries, "decision.conflict.ready",
        lambda data: data.get("owner") == owner and data.get("conflict") == conflict,
        f"decision conflict {owner}/C{conflict}",
    )
    opening_data, settlement_data, ready_data = (
        note_data(opening), note_data(settled), note_data(ready)
    )
    state_kind, state_ref = opening_data.get("state_kind"), opening_data.get("state_ref")
    source_predicates = {
        "decision.batch.ready": lambda item: state_ref == f"B{item.get('batch')}",
        "decision.batch.supplemented": lambda item: item.get("after_op") == state_ref,
        "decision.recheck.completed": lambda item: item.get("commit_op") == state_ref
        or item.get("basis_ref") == state_ref,
        "ruling.ready": lambda item: item.get("ruling") == state_ref,
        "decision.conflict.ready": lambda item: state_ref == f"{item.get('owner')}/C{item.get('conflict')}",
        "spec.breach.restored": lambda item: item.get("breach") == state_ref,
    }
    source_predicate = source_predicates.get(state_kind)
    if source_predicate is None:
        raise AuthorityPrecedenceError(
            f"decision conflict {owner}/C{conflict} has an unknown source-state kind"
        )
    exact_indexed(
        entries, state_kind, source_predicate,
        f"decision conflict {owner}/C{conflict} source state", before=opening_index,
    )
    ids = opening_data.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) \
            or any(not isinstance(identity, str) or not ANSWER_ID.fullmatch(identity)
                   for identity in ids):
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has invalid opened IDs")
    if not isinstance(sourced.get("text"), str) or not sourced["text"]:
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has no source artifact")
    if not isinstance(settled.get("text"), str) or not settled["text"]:
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has no durable settlement")

    prior = global_answer_state(entries, opening_index)
    if any(identity not in prior for identity in ids):
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} opens an unknown answer")
    owner_prefix = owner + "/" if BATCH_ID.fullmatch(owner) else None
    owner_ids = {identity for identity in prior
                 if identity == owner or owner_prefix and identity.startswith(owner_prefix)}
    if not owner_ids:
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has no current owner state")

    updates = settlement_data.get("updates")
    if not isinstance(updates, list):
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has no atomic updates")
    updated = {}
    for update in updates:
        identity, status, route = validate_answer_action(
            update, f"decision conflict {owner}/C{conflict} settlement", key="id"
        )
        if update.get("action") not in CONFLICT_ACTIONS:
            raise AuthorityPrecedenceError(
                f"decision conflict {owner}/C{conflict} has an invalid action for {identity}"
            )
        if identity not in prior or identity in updated:
            raise AuthorityPrecedenceError(
                f"decision conflict {owner}/C{conflict} changes an unknown or duplicate answer"
            )
        replacement = update.get("by")
        if replacement is not None and (
            not isinstance(replacement, str) or not ANSWER_ID.fullmatch(replacement)
        ):
            raise AuthorityPrecedenceError(
                f"decision conflict {owner}/C{conflict} has an invalid replacement identity"
            )
        updated[identity] = {"status": status, "route": route}
    if not set(ids).issubset(updated):
        raise AuthorityPrecedenceError(
            f"decision conflict {owner}/C{conflict} settlement omits an opened answer"
        )

    actions = ready_data.get("actions")
    if not isinstance(actions, list):
        raise AuthorityPrecedenceError(f"decision conflict {owner}/C{conflict} has no ready state")
    actual = {}
    for action in actions:
        identity, status, route = validate_answer_action(
            action, f"decision conflict {owner}/C{conflict} ready state"
        )
        if identity in actual:
            raise AuthorityPrecedenceError(
                f"decision conflict {owner}/C{conflict} repeats {identity}"
            )
        actual[identity] = {"status": status, "route": route}
    if set(actual) != owner_ids:
        raise AuthorityPrecedenceError(
            f"decision conflict {owner}/C{conflict} ready state adds or omits an owner answer"
        )
    expected = {identity: dict(prior[identity]) for identity in owner_ids}
    for identity, action in updated.items():
        if identity in expected:
            expected[identity] = action
    if actual != expected:
        raise AuthorityPrecedenceError(
            f"decision conflict {owner}/C{conflict} ready state contradicts its settlement"
        )
    require_pattern(ready_data.get("artifact_sha256"), ARTIFACT_SHA,
                    f"decision conflict {owner}/C{conflict} artifact SHA-256")


def validate_conflicts(entries):
    identities = set()
    conflict_kinds = {
        "decision.conflict.opened", "decision.conflict.sourced",
        "decision.conflict.settled", "decision.conflict.ready",
    }
    for entry in entries:
        if entry.get("kind") in conflict_kinds:
            data = note_data(entry)
            owner, conflict = data.get("owner"), data.get("conflict")
            if isinstance(owner, str) and owner and isinstance(conflict, int) and conflict > 0:
                identities.add((owner, conflict))
    for owner, conflict in identities:
        validate_conflict_generation(entries, owner, conflict)


def validate_breach_restoration(entries, breach):
    """Authenticate the one successful keyed recheck that releases a breach."""
    def exact(kind, predicate, subject):
        matches = [(index, entry) for index, entry in enumerate(entries)
                   if entry.get("kind") == kind and predicate(note_data(entry))]
        if len(matches) != 1:
            raise AuthorityPrecedenceError(
                f"{subject}: expected one {kind}, found {len(matches)}"
            )
        return matches[0]

    opening_index, opening = exact(
        "spec.breach.opened", lambda data: data.get("breach") == breach,
        f"breach {breach} restoration chain",
    )
    corrected_index, corrected = exact(
        "spec.breach.corrected", lambda data: data.get("breach") == breach,
        f"breach {breach} restoration chain",
    )
    restored_index, restored = exact(
        "spec.breach.restored", lambda data: data.get("breach") == breach,
        f"breach {breach} restoration chain",
    )
    if not opening_index < corrected_index < restored_index:
        raise AuthorityPrecedenceError(f"breach {breach} restoration chain is out of order")

    opening_data, corrected_data, restored_data = (
        note_data(opening), note_data(corrected), note_data(restored)
    )
    owner = opening_data.get("owner")
    if not isinstance(owner, str) or not (RULING_ID.fullmatch(owner) or BATCH_ID.fullmatch(owner)):
        raise AuthorityPrecedenceError(f"breach {breach} has a malformed owner")
    answer = opening_data.get("answer")
    if owner.startswith("R"):
        valid_answer = answer == owner
    else:
        valid_answer = bool(
            isinstance(answer, str)
            and answer.startswith(f"{owner}/")
            and BATCH_ANSWER_ID.fullmatch(answer)
        )
    if not valid_answer:
        raise AuthorityPrecedenceError(f"breach {breach} has a malformed owner answer")
    for field in ("owner", "answer", "bad_op", "bad_sha", "authorized_sha"):
        if corrected_data.get(field) != opening_data.get(field):
            raise AuthorityPrecedenceError(
                f"breach {breach} correction does not match its opening field {field}"
            )
    if (corrected_data.get("mark_lot") or "-") != (opening_data.get("mark_lot") or "-"):
        raise AuthorityPrecedenceError(
            f"breach {breach} correction does not match its opening field mark_lot"
        )
    if restored_data.get("owner") != owner or restored_data.get("bad_op") != opening_data.get("bad_op"):
        raise AuthorityPrecedenceError(f"breach {breach} restoration does not match its opening")

    rechecks = [(index, entry) for index, entry in enumerate(entries[:restored_index])
                if entry.get("kind") == "decision.recheck.completed"
                and note_data(entry).get("breach") == breach]
    if not rechecks:
        raise AuthorityPrecedenceError(f"breach {breach} restoration has no keyed recheck")
    recheck_index, recheck = rechecks[-1]
    recheck_data = note_data(recheck)
    if recheck_index <= corrected_index:
        raise AuthorityPrecedenceError(f"breach {breach} recheck predates its correction")
    basis_kind, basis_ref = recheck_data.get("basis_kind"), recheck_data.get("basis_ref")
    same_basis = [entry for _, entry in rechecks
                  if note_data(entry).get("basis_kind") == basis_kind
                  and note_data(entry).get("basis_ref") == basis_ref]
    if len(same_basis) != 1:
        raise AuthorityPrecedenceError(f"breach {breach} has an ambiguous latest keyed recheck")
    sha = recheck_data.get("sha")
    if recheck_data.get("owner") != owner or recheck_data.get("restored") is not True \
            or recheck_data.get("missing") != [] \
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        raise AuthorityPrecedenceError(f"breach {breach} latest keyed recheck is not successful")
    for field, expected in (
        ("basis_kind", basis_kind), ("basis_ref", basis_ref), ("sha", sha)
    ):
        if restored_data.get(field) != expected:
            raise AuthorityPrecedenceError(
                f"breach {breach} restoration does not match its latest recheck field {field}"
            )

    if basis_kind == "spec.breach.corrected":
        if basis_ref != corrected_data.get("op") or sha != corrected_data.get("sha"):
            raise AuthorityPrecedenceError(
                f"breach {breach} recheck does not consume its exact correction"
            )
    elif basis_kind == "spec.committed":
        commit_index, _ = exact(
            "spec.committed",
            lambda data: data.get("breach") == breach and data.get("op") == basis_ref
            and data.get("sha") == sha,
            f"breach {breach} repair recheck basis",
        )
        if not corrected_index < commit_index < recheck_index:
            raise AuthorityPrecedenceError(f"breach {breach} repair commit is out of order")
    elif basis_kind == "decision.conflict.ready":
        match = CONFLICT_REF.fullmatch(str(basis_ref))
        if not match:
            raise AuthorityPrecedenceError(f"breach {breach} has a malformed conflict basis")
        conflict_owner, conflict = basis_ref.rsplit("/C", 1)
        conflict = int(conflict)
        conflict_index, ready = exact(
            "decision.conflict.ready",
            lambda data: data.get("owner") == conflict_owner and data.get("conflict") == conflict,
            f"breach {breach} authority-only recheck basis",
        )
        _, conflict_opening = exact(
            "decision.conflict.opened",
            lambda data: data.get("owner") == conflict_owner and data.get("conflict") == conflict,
            f"breach {breach} authority-only recheck basis",
        )
        if note_data(conflict_opening).get("breach") != breach \
                or note_data(conflict_opening).get("purpose") != "restore-baseline" \
                or note_data(ready).get("effect") != "authority-only" \
                or not corrected_index < conflict_index < recheck_index:
            raise AuthorityPrecedenceError(
                f"breach {breach} recheck does not consume its exact authority-only resolution"
            )
        prior_rechecks = [entry for index, entry in rechecks if index < recheck_index]
        if not prior_rechecks or note_data(prior_rechecks[-1]).get("sha") != sha:
            raise AuthorityPrecedenceError(
                f"breach {breach} authority-only recheck changed the checked SHA"
            )
    else:
        raise AuthorityPrecedenceError(f"breach {breach} has an unknown recheck basis")

    later_basis = any(
        (
            entry.get("kind") == "spec.committed"
            and note_data(entry).get("breach") == breach
        )
        or (
            entry.get("kind") == "decision.conflict.ready"
            and any(
                opening.get("kind") == "decision.conflict.opened"
                and note_data(opening).get("breach") == breach
                and note_data(opening).get("purpose") == "restore-baseline"
                and note_data(opening).get("owner") == note_data(entry).get("owner")
                and note_data(opening).get("conflict") == note_data(entry).get("conflict")
                for opening in entries
            )
        )
        for entry in entries[recheck_index + 1:restored_index]
    )
    if later_basis:
        raise AuthorityPrecedenceError(f"breach {breach} restoration recheck is stale")


def validate_breaches(entries, allowed_open_breach):
    openings = {}
    corrected = set()
    restored = set()
    for index, entry in enumerate(entries):
        data = note_data(entry)
        if entry.get("kind") == "spec.breach.opened":
            breach = data.get("breach")
            if not isinstance(breach, int) or breach < 1 or breach in openings:
                raise AuthorityPrecedenceError("an ambiguous spec breach owns the run")
            openings[breach] = index
        elif entry.get("kind") == "spec.breach.corrected":
            breach = data.get("breach")
            if breach not in openings or breach in corrected or index < openings[breach]:
                raise AuthorityPrecedenceError("an invalid spec breach correction owns the run")
            corrected.add(breach)
        elif entry.get("kind") == "spec.breach.restored":
            breach = data.get("breach")
            if breach not in corrected or breach in restored or index < openings[breach]:
                raise AuthorityPrecedenceError("an invalid spec breach restoration owns the run")
            restored.add(breach)
    open_breaches = set(openings) - restored
    for breach in restored:
        validate_breach_restoration(entries, breach)
    allowed = set() if allowed_open_breach is None else {allowed_open_breach}
    if open_breaches != allowed:
        raise AuthorityPrecedenceError(
            f"unfinished spec breach(es) outrank this route: {sorted(open_breaches)}"
        )


def validate_spec_loop(entries):
    checks = [note_data(entry) for entry in entries
              if entry.get("kind") == "decision.recheck.completed"
              and note_data(entry).get("owner") == "spec-loop"]
    if checks and checks[-1].get("accepted") is False:
        raise AuthorityPrecedenceError("an adverse SPEC-loop global recheck still owns the run")


def validate_edit_ready(entries, allowed_ready_op):
    committed = {note_data(entry).get("ready_op") for entry in entries
                 if entry.get("kind") == "spec.committed" and note_data(entry).get("ready_op")}
    for index, entry in enumerate(entries):
        if entry.get("kind") != "spec.edit.ready":
            continue
        operation = note_data(entry)["op"]
        if operation in committed:
            continue
        later_authority = any(
            is_authority_boundary(later)
            for later in entries[index + 1:]
        )
        if not later_authority and operation != allowed_ready_op:
            raise AuthorityPrecedenceError(
                f"unconsumed current spec.edit.ready {operation!r} outranks this route"
            )


def validate_global_authority_precedence(
    entries, *, allowed_open_breach=None, allowed_ready_op=None
):
    """Reject one consumer unless the preceding run-wide authority state is quiescent."""
    validate_authority_boundary_identities(entries)
    validate_rulings(entries)
    validate_batches(entries)
    validate_rechecks(entries)
    validate_conflicts(entries)
    validate_adverse_bound_rechecks(entries)
    validate_breaches(entries, allowed_open_breach)
    validate_spec_loop(entries)
    validate_edit_ready(entries, allowed_ready_op)
