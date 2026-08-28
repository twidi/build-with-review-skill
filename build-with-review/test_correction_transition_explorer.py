#!/usr/bin/env python3
"""Fast bounded explorer for the normalized Correction Round lifecycle."""

import importlib.util
import pathlib
import sys
from collections import deque
from typing import NamedTuple


HERE = pathlib.Path(__file__).resolve().parent
COMMON = HERE / "prompts" / "common"
MAX_DEPTH = 10
EXPECTED_STATES = 119
EXPECTED_TRANSITIONS = 1904


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


lifecycle = load_module("correction_lifecycle", COMMON / "correction_lifecycle.py")

ACTIONS = (
    "allocate", "open", "start-1", "start-2", "succeed", "fail", "retry",
    "pause", "resume", "amendment-open", "amendment-return", "obligation-add",
    "obligation-consume", "built", "resolved", "escalated",
)
TERMINALS = {"built", "resolved", "escalated"}


class Rejected(ValueError):
    """One action is outside the projected lifecycle."""


class State(NamedTuple):
    phase: int = 0
    tasks: tuple = ("pending", "pending")
    active_task: int | None = None
    active_attempt: int | None = None
    paused_task: int | None = None
    paused_attempt: int | None = None
    failed_task: int | None = None
    failed_attempt: int | None = None
    retry_used: bool = False
    amendment: bool = False
    amendment_returned: bool = False
    obligation: bool = False
    terminal: str | None = None


def replace_tuple(values, position, value):
    result = list(values)
    result[position - 1] = value
    return tuple(result)


def oracle_step(state, action):
    """Apply only the independent bounded lifecycle invariants."""
    if state.terminal is not None:
        raise Rejected("a terminal state has no successor")
    if action == "allocate":
        if state.phase != 0:
            raise Rejected("the allocation is unique")
        return state._replace(phase=1)
    if action == "open":
        if state.phase != 1:
            raise Rejected("opening lacks its allocation")
        return state._replace(phase=2)
    if action in {"start-1", "start-2"}:
        task = int(action[-1])
        if state.phase != 2 or state.active_task is not None \
                or state.paused_task is not None or state.amendment:
            raise Rejected("task work overlaps another owner")
        first_pending = next(
            (index for index, status in enumerate(state.tasks, 1) if status != "done"),
            None,
        )
        if task != first_pending or state.tasks[task - 1] != "pending":
            raise Rejected("the task prefix is not contiguous")
        return state._replace(active_task=task, active_attempt=1)
    if action == "succeed":
        if state.active_task is None or state.amendment:
            raise Rejected("success lacks its task owner")
        return state._replace(
            tasks=replace_tuple(state.tasks, state.active_task, "done"),
            active_task=None, active_attempt=None, failed_task=None, failed_attempt=None,
        )
    if action == "fail":
        if state.active_task is None or state.amendment:
            raise Rejected("failure lacks its task owner")
        return state._replace(
            tasks=replace_tuple(state.tasks, state.active_task, "failed"),
            failed_task=state.active_task, failed_attempt=state.active_attempt,
            active_task=None, active_attempt=None,
        )
    if action == "retry":
        if state.failed_task is None or state.retry_used or state.amendment \
                or state.active_task is not None or state.paused_task is not None:
            raise Rejected("retry lacks one failed predecessor")
        return state._replace(
            tasks=replace_tuple(state.tasks, state.failed_task, "pending"),
            active_task=state.failed_task, active_attempt=state.failed_attempt + 1,
            retry_used=True,
        )
    if action == "pause":
        if state.active_task is None or state.amendment:
            raise Rejected("pause lacks one task owner")
        return state._replace(
            paused_task=state.active_task, paused_attempt=state.active_attempt,
            active_task=None, active_attempt=None,
        )
    if action == "resume":
        if state.paused_task is None or state.amendment:
            raise Rejected("resume lacks one stop owner")
        return state._replace(
            active_task=state.paused_task, active_attempt=state.paused_attempt,
            paused_task=None, paused_attempt=None,
        )
    if action == "amendment-open":
        if state.phase != 2 or state.amendment or state.active_task is not None \
                or state.paused_task is not None:
            raise Rejected("AMENDMENT overlaps another owner")
        return state._replace(amendment=True)
    if action == "amendment-return":
        if not state.amendment:
            raise Rejected("AMENDMENT return lacks its owner")
        return state._replace(amendment=False, amendment_returned=True)
    if action == "obligation-add":
        if state.phase != 2 or state.obligation or state.amendment \
                or state.active_task is not None or state.paused_task is not None:
            raise Rejected("final-checker obligation overlaps another owner")
        return state._replace(obligation=True)
    if action == "obligation-consume":
        if not state.obligation or state.amendment:
            raise Rejected("final-checker consumption lacks its authority")
        return state._replace(obligation=False)
    if action in TERMINALS:
        if state.phase != 2 or state.active_task is not None \
                or state.paused_task is not None or state.amendment or state.obligation:
            raise Rejected("terminal has work outstanding")
        if action == "built" and state.tasks != ("done", "done"):
            raise Rejected("built lacks the complete task prefix")
        if action == "resolved" and not state.amendment_returned:
            raise Rejected("resolved lacks its AMENDMENT return")
        if action == "escalated" and state.failed_task is None \
                and not state.amendment_returned:
            raise Rejected("escalated lacks its producer")
        return state._replace(terminal=action)
    raise AssertionError(f"unknown oracle action: {action}")


def accepted_tasks(state):
    return next(
        (index for index, status in enumerate(state.tasks) if status != "done"),
        len(state.tasks),
    )


def active_owner(state):
    if state.active_task is not None:
        return "task"
    if state.paused_task is not None:
        return "stop"
    if state.amendment:
        return "amendment"
    return None


def production_step(state, action):
    """Call the shared production projector, then apply the accepted state change."""
    owner = active_owner(state)
    accepted = accepted_tasks(state)
    opened = state.phase == 2

    if action in {"allocate", "open"}:
        lifecycle.admit_entry(lifecycle.EntryFacts(
            allocation_present=state.phase >= 1,
            opening_present=opened,
            active_owner=owner,
            terminal=state.terminal,
        ), action)
        return state._replace(phase=1 if action == "allocate" else 2)

    if action in {"start-1", "start-2", "retry", "succeed", "fail", "pause", "resume"}:
        if action == "retry":
            task = state.failed_task or 1
            attempt = (state.failed_attempt or 0) + 1
            projected_action = "retry"
        elif action in {"start-1", "start-2"}:
            task = int(action[-1])
            attempt = 1
            projected_action = "start"
        elif action == "resume":
            task = state.paused_task or 1
            attempt = state.paused_attempt or 1
            projected_action = action
        else:
            task = state.active_task or 1
            attempt = state.active_attempt or 1
            projected_action = action
        lifecycle.admit_task(lifecycle.TaskFacts(
            opening_present=opened,
            active_owner=owner,
            accepted_tasks=accepted,
            task_count=len(state.tasks),
            task=task,
            attempt=attempt,
            expected_attempt=attempt,
            retry_available=state.failed_task is not None,
            retry_used=state.retry_used,
            terminal=state.terminal,
        ), projected_action)
        if action in {"start-1", "start-2"}:
            return state._replace(active_task=task, active_attempt=attempt)
        if action == "retry":
            return state._replace(
                tasks=replace_tuple(state.tasks, task, "pending"),
                active_task=task, active_attempt=attempt, retry_used=True,
            )
        if action == "succeed":
            return state._replace(
                tasks=replace_tuple(state.tasks, task, "done"),
                active_task=None, active_attempt=None, failed_task=None, failed_attempt=None,
            )
        if action == "fail":
            return state._replace(
                tasks=replace_tuple(state.tasks, task, "failed"),
                failed_task=task, failed_attempt=attempt,
                active_task=None, active_attempt=None,
            )
        if action == "pause":
            return state._replace(
                paused_task=task, paused_attempt=attempt,
                active_task=None, active_attempt=None,
            )
        return state._replace(
            active_task=task, active_attempt=attempt,
            paused_task=None, paused_attempt=None,
        )

    if action in {"amendment-open", "amendment-return"}:
        lifecycle.admit_amendment(lifecycle.AmendmentFacts(
            opening_present=opened,
            active_owner=owner,
            accepted_tasks=accepted,
            task_count=len(state.tasks),
            return_task=accepted + 1,
            terminal=state.terminal,
        ), action.removeprefix("amendment-"))
        if action == "amendment-open":
            return state._replace(amendment=True)
        return state._replace(amendment=False, amendment_returned=True)

    if action in {"obligation-add", "obligation-consume"}:
        before = int(state.obligation)
        after = 1 if action == "obligation-add" else 0
        lifecycle.admit_obligation(lifecycle.ObligationFacts(
            opening_present=opened,
            active_owner=owner,
            producer_owner=None,
            outstanding_before=before,
            outstanding_after=after,
            terminal=state.terminal,
        ), "produce" if action == "obligation-add" else "consume")
        return state._replace(obligation=bool(after))

    if action in TERMINALS:
        lifecycle.admit_terminal(lifecycle.TerminalFacts(
            opening_present=opened,
            active_owner=owner,
            accepted_tasks=accepted,
            task_count=len(state.tasks),
            outstanding_obligations=state.obligation,
            amendment_returned=state.amendment_returned,
            escalation_producer=(
                state.failed_task is not None or state.amendment_returned
            ),
            terminal=state.terminal,
        ), action)
        return state._replace(terminal=action)
    raise AssertionError(f"unknown production action: {action}")


def replay(step, trace):
    state = State()
    for action in trace:
        state = step(state, action)
    return state


def oracle_replay(trace):
    return replay(oracle_step, trace)


def production_replay(trace):
    return replay(production_step, trace)


def accepted(function, trace):
    try:
        return True, function(trace)
    except (Rejected, ValueError):
        return False, None


def explore(production_projector=production_replay):
    queue = deque([((), State())])
    seen = {State()}
    transition_count = 0
    terminal_routes = set()
    rejected_classes = set()
    while queue:
        trace, oracle_state = queue.popleft()
        for action in ACTIONS:
            candidate = trace + (action,)
            oracle_ok, next_oracle = accepted(oracle_replay, candidate)
            production_ok, _next_production = accepted(production_projector, candidate)
            transition_count += 1
            if oracle_ok != production_ok:
                raise AssertionError(
                    "minimal transition mismatch: " + " -> ".join(candidate)
                    + f" (oracle={oracle_ok}, production={production_ok})"
                )
            if not oracle_ok:
                if action in TERMINALS and oracle_state.terminal is not None:
                    rejected_classes.add("duplicate")
                elif oracle_state.terminal is not None:
                    rejected_classes.add("post-terminal")
                elif action == "succeed" and oracle_state.active_task is None:
                    rejected_classes.add("missing-authority")
                elif action == "start-2" and oracle_state.tasks[0] != "done":
                    rejected_classes.add("reorder")
                elif action in {"amendment-open", "start-1", "start-2"} \
                        and (oracle_state.amendment or oracle_state.active_task is not None):
                    rejected_classes.add("overlap")
                continue
            if next_oracle.terminal is not None:
                terminal_routes.add(next_oracle.terminal)
            if len(candidate) < MAX_DEPTH and next_oracle not in seen:
                seen.add(next_oracle)
                queue.append((candidate, next_oracle))
    required_rejections = {
        "overlap", "duplicate", "reorder", "missing-authority", "post-terminal",
    }
    if terminal_routes != TERMINALS:
        raise AssertionError(f"terminal route coverage changed: {sorted(terminal_routes)}")
    if rejected_classes != required_rejections:
        raise AssertionError(f"rejected transition coverage changed: {sorted(rejected_classes)}")
    return len(seen), transition_count


def verify_minimal_counterexample():
    def changed_projector(trace):
        if trace == ("allocate", "open"):
            raise Rejected("injected projector mismatch")
        return production_replay(trace)

    expected = "minimal transition mismatch: allocate -> open (oracle=True, production=False)"
    try:
        explore(changed_projector)
    except AssertionError as exc:
        if str(exc) != expected:
            raise AssertionError(f"counterexample is not minimal: {exc}") from exc
    else:
        raise AssertionError("the explorer did not report an injected mismatch")


def verify_preserved_prefix_projection():
    task_count = lifecycle.complete_task_count([1, 2], [3])
    if task_count != 3:
        raise AssertionError("the preserved Correction task prefix changed its total")
    lifecycle.admit_amendment(lifecycle.AmendmentFacts(
        opening_present=True,
        active_owner=None,
        accepted_tasks=2,
        task_count=task_count,
        return_task=3,
        terminal=None,
    ), "open")
    lifecycle.admit_amendment(lifecycle.AmendmentFacts(
        opening_present=True,
        active_owner="amendment",
        accepted_tasks=2,
        task_count=task_count,
        return_task=3,
        terminal=None,
    ), "return")
    lifecycle.admit_task(lifecycle.TaskFacts(
        opening_present=True,
        active_owner="stop",
        accepted_tasks=2,
        task_count=task_count,
        task=3,
        attempt=1,
        expected_attempt=1,
        retry_available=False,
        retry_used=False,
        terminal=None,
    ), "resume")


SENSITIVITY_CASES = (
    ("admit_entry", "open", ("allocate", "open")),
    ("admit_task", "start", ("allocate", "open", "start-1")),
    ("admit_task", "succeed", ("allocate", "open", "start-1", "succeed")),
    ("admit_task", "pause", ("allocate", "open", "start-1", "pause")),
    ("admit_task", "resume", ("allocate", "open", "start-1", "pause", "resume")),
    ("admit_amendment", "open", ("allocate", "open", "amendment-open")),
    ("admit_amendment", "return", ("allocate", "open", "amendment-open", "amendment-return")),
    ("admit_obligation", "produce", ("allocate", "open", "obligation-add")),
    ("admit_obligation", "consume", ("allocate", "open", "obligation-add", "obligation-consume")),
    ("admit_terminal", "built", (
        "allocate", "open", "start-1", "succeed", "start-2", "succeed", "built",
    )),
    ("admit_terminal", "resolved", (
        "allocate", "open", "amendment-open", "amendment-return", "resolved",
    )),
    ("admit_terminal", "escalated", (
        "allocate", "open", "start-1", "fail", "escalated",
    )),
)


def verify_projector_sensitivity():
    for function_name, selected_action, trace in SENSITIVITY_CASES:
        original = getattr(lifecycle, function_name)

        def reject_selected(facts, action, *, target=selected_action, delegate=original):
            if action == target:
                raise Rejected(f"injected {target} projector mismatch")
            return delegate(facts, action)

        setattr(lifecycle, function_name, reject_selected)
        expected = (
            "minimal transition mismatch: " + " -> ".join(trace)
            + " (oracle=True, production=False)"
        )
        try:
            try:
                explore()
            except AssertionError as exc:
                if str(exc) != expected:
                    raise AssertionError(
                        f"{function_name}/{selected_action} counterexample is not minimal: {exc}"
                    ) from exc
            else:
                raise AssertionError(
                    f"the explorer did not call {function_name} for {selected_action}"
                )
        finally:
            setattr(lifecycle, function_name, original)


def main():
    verify_minimal_counterexample()
    verify_preserved_prefix_projection()
    verify_projector_sensitivity()
    states, transitions = explore()
    print(f"CORRECTION TRANSITION EXPLORER states={states} transitions={transitions}")
    if (states, transitions) != (EXPECTED_STATES, EXPECTED_TRANSITIONS):
        raise AssertionError(
            "the bounded explorer count changed: "
            f"expected {(EXPECTED_STATES, EXPECTED_TRANSITIONS)}, "
            f"actual {(states, transitions)}"
        )


if __name__ == "__main__":
    main()
