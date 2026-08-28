#!/usr/bin/env python3
"""Pure lifecycle admission for one normalized Correction Round authority."""

from typing import NamedTuple


OWNER_KINDS = {None, "task", "stop", "amendment"}
TERMINAL_KINDS = {None, "built", "resolved", "escalated"}


class EntryFacts(NamedTuple):
    allocation_present: bool
    opening_present: bool
    active_owner: str | None
    terminal: str | None


class TaskFacts(NamedTuple):
    opening_present: bool
    active_owner: str | None
    accepted_tasks: int
    task_count: int
    task: int
    attempt: int
    expected_attempt: int
    retry_available: bool
    retry_used: bool
    terminal: str | None


class AmendmentFacts(NamedTuple):
    opening_present: bool
    active_owner: str | None
    accepted_tasks: int
    task_count: int
    return_task: int
    terminal: str | None


class ObligationFacts(NamedTuple):
    opening_present: bool
    active_owner: str | None
    producer_owner: str | None
    outstanding_before: int
    outstanding_after: int
    terminal: str | None


class TerminalFacts(NamedTuple):
    opening_present: bool
    active_owner: str | None
    accepted_tasks: int
    task_count: int
    outstanding_obligations: bool
    amendment_returned: bool
    escalation_producer: bool
    terminal: str | None


def require_bool(value, subject):
    if not isinstance(value, bool):
        raise ValueError(f"{subject} is not one boolean")


def require_count(value, subject):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{subject} is not one non-negative count")


def require_positive(value, subject):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{subject} is not one positive ordinal")


def complete_task_count(preserved_tasks, projected_tasks):
    if not isinstance(preserved_tasks, (list, tuple)) \
            or not isinstance(projected_tasks, (list, tuple)):
        raise ValueError("the Correction task identity set is not one sequence")
    identities = [*preserved_tasks, *projected_tasks]
    for task in identities:
        require_positive(task, "the Correction task identity")
    if identities != list(range(1, len(identities) + 1)):
        raise ValueError("the Correction task identity set is not contiguous")
    return len(identities)


def validate_common(opening_present, active_owner, terminal, subject):
    require_bool(opening_present, f"{subject} opening presence")
    if active_owner not in OWNER_KINDS:
        raise ValueError(f"{subject} has an unsupported active owner")
    if terminal not in TERMINAL_KINDS:
        raise ValueError(f"{subject} has an unsupported terminal")
    if terminal is not None:
        raise ValueError(f"{subject} follows a Correction Round terminal")


def admit_entry(facts, action):
    if not isinstance(facts, EntryFacts) or action not in {"allocate", "open"}:
        raise ValueError("the Correction entry transition has malformed facts")
    require_bool(facts.allocation_present, "the Correction allocation presence")
    validate_common(facts.opening_present, facts.active_owner, facts.terminal,
                    "the Correction entry transition")
    if facts.active_owner is not None:
        raise ValueError("the Correction entry transition overlaps another owner")
    if action == "allocate":
        if facts.allocation_present or facts.opening_present:
            raise ValueError("the Correction allocation is not unique")
    elif not facts.allocation_present or facts.opening_present:
        raise ValueError("the Correction opening has no one unconsumed allocation")


def admit_task(facts, action):
    if not isinstance(facts, TaskFacts) or action not in {
        "start", "retry", "succeed", "fail", "pause", "resume",
    }:
        raise ValueError("the Correction task transition has malformed facts")
    validate_common(facts.opening_present, facts.active_owner, facts.terminal,
                    "the Correction task transition")
    for value, subject in (
        (facts.accepted_tasks, "the accepted task prefix"),
        (facts.task_count, "the Correction task count"),
    ):
        require_count(value, subject)
    for value, subject in (
        (facts.task, "the Correction task"),
        (facts.attempt, "the Correction attempt"),
        (facts.expected_attempt, "the expected Correction attempt"),
    ):
        require_positive(value, subject)
    require_bool(facts.retry_available, "the prior Correction attempt state")
    require_bool(facts.retry_used, "the Correction retry consumption state")
    if not facts.opening_present or facts.accepted_tasks > facts.task_count:
        raise ValueError("the Correction task transition has no opened task authority")
    if action in {"start", "retry"}:
        if facts.active_owner is not None:
            raise ValueError("the Correction task start overlaps another owner")
        if facts.task != facts.accepted_tasks + 1 or facts.task > facts.task_count:
            raise ValueError("the Correction task start breaks the contiguous prefix")
        if facts.attempt != facts.expected_attempt:
            raise ValueError("the Correction task start skips its attempt sequence")
        if action == "start" and (facts.retry_available or facts.attempt != 1):
            raise ValueError("the first Correction attempt consumes retry authority")
        if action == "retry" and (not facts.retry_available or facts.retry_used):
            raise ValueError("the Correction retry has no unconsumed predecessor")
    elif action in {"succeed", "fail", "pause"}:
        if facts.active_owner != "task" or facts.task != facts.accepted_tasks + 1:
            raise ValueError("the Correction task terminal has no current task owner")
        if facts.attempt != facts.expected_attempt:
            raise ValueError("the Correction task terminal changes its attempt")
    elif facts.active_owner != "stop" or facts.attempt != facts.expected_attempt:
        raise ValueError("the Correction resume has no current stop owner")


def admit_amendment(facts, action):
    if not isinstance(facts, AmendmentFacts) or action not in {"open", "return"}:
        raise ValueError("the Correction AMENDMENT transition has malformed facts")
    validate_common(facts.opening_present, facts.active_owner, facts.terminal,
                    "the Correction AMENDMENT transition")
    require_count(facts.accepted_tasks, "the accepted task prefix")
    require_count(facts.task_count, "the Correction task count")
    require_positive(facts.return_task, "the Correction AMENDMENT return task")
    if not facts.opening_present or facts.accepted_tasks > facts.task_count:
        raise ValueError("the Correction AMENDMENT has no opened work unit")
    if facts.return_task != facts.accepted_tasks + 1:
        raise ValueError("the Correction AMENDMENT changes its return task")
    if action == "open" and facts.active_owner is not None:
        raise ValueError("the Correction AMENDMENT overlaps another owner")
    if action == "return" and facts.active_owner != "amendment":
        raise ValueError("the Correction AMENDMENT return has no current owner")


def admit_obligation(facts, action):
    if not isinstance(facts, ObligationFacts) or action not in {"produce", "consume"}:
        raise ValueError("the final-checker transition has malformed lifecycle facts")
    require_bool(facts.opening_present, "the final-checker opening presence")
    require_count(facts.outstanding_before, "the prior final-checker count")
    require_count(facts.outstanding_after, "the next final-checker count")
    if facts.active_owner not in OWNER_KINDS:
        raise ValueError("the final-checker transition has an unsupported active owner")
    if facts.producer_owner not in OWNER_KINDS:
        raise ValueError("the final-checker transition has an unsupported producer owner")
    if facts.terminal not in TERMINAL_KINDS:
        raise ValueError("the final-checker transition has an unsupported terminal")
    if not facts.opening_present or facts.terminal is not None:
        raise ValueError("the final-checker transition follows no active Correction Round")
    if action == "produce" and (
        facts.producer_owner not in {None, "task"}
        or facts.active_owner != facts.producer_owner
        or facts.outstanding_after <= facts.outstanding_before
    ):
        raise ValueError("the final-checker producer creates no outstanding obligation")
    if action == "consume" and (
        facts.active_owner == "amendment"
        or facts.producer_owner is not None
        or facts.outstanding_before < 1
        or facts.outstanding_after >= facts.outstanding_before
    ):
        raise ValueError("the final-checker consumer does not close its obligation")


def admit_terminal(facts, action):
    if not isinstance(facts, TerminalFacts) or action not in {
        "built", "resolved", "escalated",
    }:
        raise ValueError("the Correction terminal transition has malformed facts")
    validate_common(facts.opening_present, facts.active_owner, facts.terminal,
                    "the Correction terminal transition")
    require_count(facts.accepted_tasks, "the accepted task prefix")
    require_count(facts.task_count, "the Correction task count")
    for value, subject in (
        (facts.outstanding_obligations, "the outstanding final-checker state"),
        (facts.amendment_returned, "the AMENDMENT return state"),
        (facts.escalation_producer, "the escalation producer state"),
    ):
        require_bool(value, subject)
    if not facts.opening_present or facts.active_owner is not None \
            or facts.outstanding_obligations:
        raise ValueError("the Correction terminal has work outstanding")
    if action == "built" and facts.accepted_tasks != facts.task_count:
        raise ValueError("the built terminal has no complete task prefix")
    if action == "resolved" and not facts.amendment_returned:
        raise ValueError("the resolved terminal has no AMENDMENT return")
    if action == "escalated" and not facts.escalation_producer:
        raise ValueError("the escalated terminal has no exact producer")
