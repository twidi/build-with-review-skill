#!/usr/bin/env python3
"""Report one BWR Orchestrator's open direct children.

Usage: python3 watchdog.py <orchestrator-session-id> [stale-minutes] [--print-only]

The script reads TwiCC session and process state. It writes no project state.
Without --print-only, it sends the report directly to the Orchestrator.
"""

import argparse
import json
import os
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone


TERMINAL_STATUSES = {"done", "failed", "cancelled", "superseded"}
TITLE_MAX = 58
TWICC = shlex.split(os.environ.get("TWICC_BIN") or "twicc")
NEUTRAL_CWD = tempfile.gettempdir()


def fail(summary, detail):
    """Report an unknown state loudly and stop."""
    print(f"**watchdog ERROR** · {summary}")
    print()
    print(f"    {str(detail)[:400]}")
    print()
    print("**THE WATCHDOG STATE WAS NOT CHECKED.**")
    print("This is not a report of zero children. Their state is unknown.")
    print()
    print(
        "**RESUME CHECK** — Retry this Watchdog inspection. "
        "Do not infer that no child exists. "
        "If the retry also fails, report this blocker to the Human once."
    )
    raise SystemExit(1)


def run_json(arguments):
    """Run one TwiCC command and decode its JSON response."""
    command = TWICC + arguments
    try:
        result = subprocess.run(
            command,
            cwd=NEUTRAL_CWD,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except Exception as exc:
        fail(f"could not run: {shlex.join(command)}", exc)

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"`{shlex.join(arguments)}` exited {result.returncode}", detail)

    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        fail(
            f"`{shlex.join(arguments)}` returned unreadable JSON",
            f"{exc}; first bytes: {result.stdout[:200]!r}",
        )


def minutes_since(stamp, now=None):
    """Return whole minutes since an ISO timestamp."""
    if not stamp:
        return None

    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)

    current = now or datetime.now(timezone.utc)
    return max(0, int((current - then).total_seconds() // 60))


def duration(minutes):
    """Format a duration for quick reading."""
    if minutes is None:
        return "unknown"
    if minutes == 0:
        return "<1min"
    if minutes < 60:
        return f"{minutes}min"

    hours, remaining_minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{remaining_minutes:02d}"

    days, remaining_hours = divmod(hours, 24)
    return f"{days}d{remaining_hours:02d}h"


def short_title(title):
    """Remove the internal-session prefix and limit display width."""
    text = (title or "(untitled)").strip()
    if text.startswith("- "):
        text = text[2:].strip()
    if len(text) > TITLE_MAX:
        return text[: TITLE_MAX - 1] + "…"
    return text


def bwr_status(session):
    annotations = session.get("annotations") or {}
    bwr = annotations.get("bwr") or {}
    return bwr.get("status")


def collect_rows(sessions, processes, own_session_id, now=None):
    """Build report rows for open direct children."""
    current = now or datetime.now(timezone.utc)
    processes_by_session = {
        process.get("session_id"): process
        for process in processes
        if process.get("session_id")
    }
    rows = []

    for session in sessions:
        status = bwr_status(session)
        if session.get("archived"):
            continue
        if session.get("id") == own_session_id:
            continue
        if status in TERMINAL_STATUSES:
            continue

        process = processes_by_session.get(session.get("id")) or {}
        rows.append(
            {
                "id": session.get("id"),
                "title": short_title(session.get("title")),
                "status": status or "no status",
                "quiet": minutes_since(session.get("last_updated_at"), current),
                "state": process.get("state") or "no live process",
                "turn": minutes_since(process.get("last_state_change_at"), current),
            }
        )

    return rows


def is_stale(row, stale_after):
    if row["status"] == "idle":
        return False
    return row["quiet"] is None or row["quiet"] >= stale_after


def resume_check():
    return (
        "**RESUME CHECK** — If you have unfinished work and no valid blocker, "
        "resume it now. If the Human has not received a current blocker, send it once. "
        "If the Human already acknowledged it and nothing changed, wait."
    )


def render_snapshot(orchestrator_title, rows, stale_after, now=None):
    """Render the Markdown snapshot sent to the Orchestrator."""
    current = now or datetime.now().astimezone()
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row["status"] == "idle",
            -(row["quiet"] if row["quiet"] is not None else 10**9),
        ),
    )
    stale_rows = [row for row in ordered_rows if is_stale(row, stale_after)]

    count = len(ordered_rows)
    noun = "child" if count == 1 else "children"
    owner = f' of "{orchestrator_title}"' if orchestrator_title else ""
    if count:
        heading = f"**watchdog {current.strftime('%H:%M')}** · **{count}** open {noun}{owner}"
    else:
        heading = f"**watchdog {current.strftime('%H:%M')}** · NO open {noun}{owner}"

    if stale_rows:
        heading += (
            f"  \n⚠ **{len(stale_rows)}** with nothing written for "
            f"**{stale_after}min** or more"
        )

    blocks = [heading]
    for row in ordered_rows:
        state = f"`{row['state']}`"
        turn = state if row["turn"] is None else f"{state} for **{duration(row['turn'])}**"
        marker = "⚠" if is_stale(row, stale_after) else "•"
        blocks.append(
            f"{marker} **{row['title']}**  \n"
            f"{turn} · quiet for **{duration(row['quiet'])}** · "
            f"status **{row['status']}**  \n"
            f"`{row['id']}`"
        )

    blocks.append(
        "_turn = time in the current process state · "
        "quiet = time since the child last wrote anything_"
    )
    blocks.append(resume_check())
    return "\n\n".join(blocks)


def deliver(orchestrator_session_id, report, print_only=False):
    """Print the report and optionally send it through TwiCC."""
    print(report)
    if print_only:
        return

    command = TWICC + ["send-message", orchestrator_session_id, report]
    try:
        result = subprocess.run(
            command,
            cwd=NEUTRAL_CWD,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except Exception as exc:
        fail("could not deliver the Watchdog report", exc)

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail("delivering the Watchdog report failed", detail)


def parse_arguments(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("orchestrator_session_id")
    parser.add_argument("stale_minutes", nargs="?", type=int, default=40)
    parser.add_argument("--print-only", action="store_true")
    parsed = parser.parse_args(arguments)
    if parsed.stale_minutes < 1:
        parser.error("stale-minutes must be positive")
    return parsed


def read_topology(topology, orchestrator_session_id):
    """Extract one Orchestrator and its direct children."""
    if not isinstance(topology, dict):
        fail("the TwiCC topology returned the wrong shape", type(topology).__name__)

    process_state = topology.get("processes") or {}
    if not process_state.get("available"):
        fail("live TwiCC process state is unavailable", process_state.get("reason") or "unknown reason")

    nodes = topology.get("nodes")
    if not isinstance(nodes, list):
        fail("the TwiCC topology has no node list", type(nodes).__name__)

    orchestrator = None
    sessions = []
    processes = []
    for node in nodes:
        session = node.get("session") or {}
        if node.get("id") == orchestrator_session_id:
            orchestrator = session
        if session.get("spawned_by") != orchestrator_session_id:
            continue

        sessions.append(session)
        process = node.get("process")
        if process:
            processes.append({**process, "session_id": session.get("id")})

    if orchestrator is None:
        fail("the Orchestrator is absent from its TwiCC topology", orchestrator_session_id)

    return orchestrator, sessions, processes


def main(arguments=None):
    options = parse_arguments(arguments)
    identity = run_json(["whoami"])
    if not isinstance(identity, dict) or not identity.get("session_id"):
        fail("the Watchdog session identity is missing", identity)

    topology = run_json(
        ["topology", options.orchestrator_session_id, "--full-sessions"]
    )
    orchestrator, sessions, processes = read_topology(
        topology, options.orchestrator_session_id
    )
    rows = collect_rows(sessions, processes, identity["session_id"])
    report = render_snapshot(
        orchestrator.get("title"),
        rows,
        stale_after=options.stale_minutes,
    )
    deliver(options.orchestrator_session_id, report, options.print_only)


if __name__ == "__main__":
    main()
