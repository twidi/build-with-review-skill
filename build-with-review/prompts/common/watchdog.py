#!/usr/bin/env python3
"""Watchdog snapshot: the controller's open direct children.

Usage: python3 watchdog.py <controller-session-id> [stale-minutes] [--print-only]

Sends the snapshot to the controller itself, through the `twicc` CLI, so no
model has to relay it. `--print-only` prints and sends nothing.

Reports one entry per open child — not archived, no terminal `bwr.status`,
and never the session running this script. Quietest first. Each entry carries two
durations, and it takes both to tell a working child from a stuck one:

  * the TURN — how long the child has been in its current process state;
  * the QUIET — how long since it last wrote anything.

A child generating for 45 minutes that wrote 30 seconds ago is working. The same
child quiet for 45 minutes is stuck. `⚠` marks a quiet longer than
<stale-minutes> (default 40).

Reads session metadata through the `twicc` CLI. Writes nothing.
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

TERMINAL = {"done", "failed", "cancelled", "superseded"}
TITLE_MAX = 58

# The CLI resolves WHICH TwiCC instance it talks to from its working directory:
# inside a git worktree that wins over everything. Running from a neutral
# directory lets the inherited TWICC_DATA_DIR decide — and TwiCC exports it
# pointing at the instance that owns these sessions.
TWICC = shlex.split(os.environ.get("TWICC_BIN") or "twicc")
NEUTRAL_CWD = tempfile.gettempdir()


def fail(what, detail):
    """A broken CLI must never look like an empty result."""
    print(f"**watchdog ERROR** · {what}")
    print()
    print(f"    {str(detail)[:400]}")
    print()
    print("**YOUR CHILDREN WERE NOT CHECKED.** This is not a report of zero children:")
    print("their state is unknown. Change nothing on the strength of this tick.")
    sys.exit(1)


def run(args):
    try:
        out = subprocess.run(
            TWICC + args, cwd=NEUTRAL_CWD, capture_output=True, text=True, timeout=90
        )
    except Exception as exc:
        fail(f"could not run: {' '.join(TWICC + args)}", exc)
    if out.returncode != 0:
        fail(f"`{' '.join(args)}` exited {out.returncode}", out.stderr.strip() or out.stdout.strip())
    try:
        return json.loads(out.stdout)
    except ValueError as exc:
        fail(f"`{' '.join(args)}` returned unreadable output", f"{exc} — first bytes: {out.stdout[:200]!r}")


def minutes_since(stamp):
    """Whole minutes between <stamp> and now. None when there is nothing to read."""
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - t).total_seconds() // 60))


def duration(minutes):
    """A duration nobody has to count digits to read."""
    if minutes is None:
        return "unknown"
    if minutes == 0:
        return "<1min"
    if minutes < 60:
        return f"{minutes}min"
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{mins:02d}"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def short_title(title):
    """Drop the internal-session prefix, keep the line inside one screen."""
    text = (title or "(untitled)").strip()
    if text.startswith("- "):
        text = text[2:].strip()
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1] + "…"


def own_session_id():
    """The session running this script — never reported to itself."""
    me = run(["whoami"])
    return me.get("session_id") if isinstance(me, dict) else None
    # A failure here already exited: excluding nobody is safe, reporting nobody is not.


def deliver(controller, text):
    """Send the snapshot ourselves: a relayed message is a message that can be garbled."""
    print(text)
    if "--print-only" in sys.argv:
        return
    try:
        out = subprocess.run(
            TWICC + ["send-message", controller, text],
            cwd=NEUTRAL_CWD, capture_output=True, text=True, timeout=90,
        )
    except Exception as exc:
        fail("could not deliver the snapshot", exc)
    if out.returncode != 0:
        fail("delivering the snapshot failed", out.stderr.strip() or out.stdout.strip())


def main():
    controller = sys.argv[1]
    stale_after = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 40

    parent = run(["session", controller])
    parent_title = parent.get("title") if isinstance(parent, dict) else None
    mine = own_session_id()
    # `--spawned-by` is what makes hidden children visible here: a plain `processes`
    # call omits them, and a running child would be reported as having no process.
    procs = {p.get("session_id"): p for p in run(["processes", "--spawned-by", controller])}

    rows = []
    for c in run(["sessions", "--spawned-by", controller, "--include-hidden"]):
        if c.get("archived") or c.get("id") == mine:
            continue
        status = ((c.get("annotations") or {}).get("bwr") or {}).get("status")
        if status in TERMINAL:
            continue
        proc = procs.get(c.get("id")) or {}
        rows.append({
            # `last_updated_at`, not `last_new_content_at`: the question here is
            # liveness, and ANY write proves it. Durations of finished work are a
            # different question, answered elsewhere with the stricter field.
            "quiet": minutes_since(c.get("last_updated_at")),
            "state": proc.get("state") or "no live process",
            "turn": minutes_since(proc.get("last_state_change_at")),
            "status": status or "no status",
            "title": short_title(c.get("title")),
            "id": c.get("id"),
        })

    now = datetime.now().strftime("%H:%M")
    of_whom = f' of "{parent_title}"' if parent_title else ""
    noun = "child" if len(rows) == 1 else "children"

    if not rows:
        deliver(controller, f"**watchdog {now}** · NO open {noun}{of_whom}")
        return

    # An unreadable timestamp sorts and marks as the worst case: a child whose
    # silence cannot be measured is the one to look at, never the one to skip.
    #
    # `idle` is never stale, whatever its silence. It means the controller parked
    # it with nothing pending — a fixer between two rounds — and it may sit there
    # for hours doing exactly what it should. Marking it would light the one symbol
    # that has to stay rare. It stays listed, with its duration: a parked child
    # nobody un-parks is the controller's problem, not a dead session.
    #
    # `blocked` IS stale-able, and that is the point: it means an answer is owed,
    # by the controller. A blocked child gone quiet is the visible symptom of a
    # debt somebody forgot.
    def is_stale(row):
        return row["status"] != "idle" and (row["quiet"] is None or row["quiet"] >= stale_after)

    # Loudest first among the ones that matter, then the parked ones.
    rows.sort(key=lambda r: (
        r["status"] == "idle",
        -(r["quiet"] if r["quiet"] is not None else 10 ** 9),
    ))
    stale = [r for r in rows if is_stale(r)]

    # The report is read in a chat that renders Markdown. Bold carries the two
    # numbers and the status — the values that decide what the reader does —
    # never a whole line, which bolds nothing at all. The trailing DOUBLE SPACE
    # before each \n is a Markdown hard break: strip it and the three lines of an
    # entry collapse into one paragraph.
    head = f"**watchdog {now}** · **{len(rows)}** open {noun}{of_whom}"
    if stale:
        head += f"  \n⚠ **{len(stale)}** with nothing written for **{stale_after}min** or more"

    blocks = [head]
    for r in rows:
        state = f"`{r['state']}`"
        turn = state if r["turn"] is None else f"{state} for **{duration(r['turn'])}**"
        blocks.append(
            f"{'⚠' if is_stale(r) else '•'} **{r['title']}**  \n"
            f"{turn} · quiet for **{duration(r['quiet'])}** · status **{r['status']}**  \n"
            f"`{r['id']}`"
        )
    blocks.append(
        "_turn = time in the current process state · quiet = time since the child last wrote anything_"
    )
    deliver(controller, "\n\n".join(blocks))


if __name__ == "__main__":
    main()
