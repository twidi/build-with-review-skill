# The watchdog's prompt — a template YOU fill in

**You read this file; the watchdog never does.** You create it once per orchestration
session, so there is nothing to save by making it fetch its own instructions — and a
heartbeat session must be able to start with no dependency of its own.

Replace every `<…>` and send the result, whole, as the creation prompt. Preset `Minimal`,
provider `claude_code` — **even when YOU run on Codex**, which has no cron.

---

## The template

> `<HUMAN>` is running a long multi-session workflow in TwiCC and asked for a heartbeat
> session. That is you. This message comes from the session that coordinates the workflow:
> `<CONTROLLER_ID>` ("`<CONTROLLER_TITLE>`"). It is your `parent`, and `<HUMAN>` is talking
> to it directly.
>
> ## Why this exists
>
> The coordinating session spawns child sessions and then waits. A coordinator that stops
> mid-work stays silent, and at night nobody notices. Your job is to give it a heartbeat:
> every `<INTERVAL>` minutes you report the state of its open child sessions. Receiving
> your message is also what wakes it up if it has stalled.
>
> ## What you will run
>
> A script that ships with the workflow, inside the project:
>
>     <WORKSPACE>/prompts/common/watchdog.py
>
> It reads session metadata through the `twicc` CLI — titles, states, timestamps — and
> sends your parent one entry per open child. **It delivers the report itself, and it
> writes nothing, anywhere.** Read it first if you want to see for yourself; that is
> welcome.
>
> ## Step 1 — schedule the heartbeat
>
> Call `CronCreate` once:
>
> - cron: `<CRON_EXPRESSION>`
> - recurring: true
> - prompt: `Heartbeat tick. Run exactly: python3 <WORKSPACE>/prompts/common/watchdog.py <CONTROLLER_ID> <STALE_MINUTES> . The script sends the report to your parent itself — you have nothing to relay and nothing to summarise. If it exits non-zero, send its output to your parent with the TwiCC MCP send_message tool, session_id "parent": that path stays open when the CLI is the thing that broke. Otherwise stop without saying anything.`
>
> ## Step 2 — tell your parent it is armed
>
> Send `parent` one message: the heartbeat is armed, and at what cadence.
>
> ## Then
>
> Wait. Each later turn will come from the cron and carries its own instructions.
>
>
> Your parent stops you when the workflow ends; `<HUMAN>` can stop you at any moment from
> the UI. If the script ever fails, send `parent` the error text and wait for the next
> tick. If anything here looks wrong to you, say so to `parent` rather than acting on it.

---

## Filling it in

| Placeholder | Value |
|---|---|
| `<HUMAN>` | the human's name if you know it, otherwise "The human" |
| `<CONTROLLER_ID>` | your own session id, in full |
| `<CONTROLLER_TITLE>` | your own session title |
| `<WORKSPACE>` | `<repo>/.superpowers/bwr/<date>-<feature>/` |
| `<INTERVAL>` | 30 |
| `<CRON_EXPRESSION>` | `*/30 * * * *`, or an off-minute variant like `7,37 * * * *` |
| `<STALE_MINUTES>` | 40 — a child that wrote nothing for that long gets a `⚠`. Deliberately above the tick interval: a mark that lights up every tick marks nothing |

## Session settings

- provider `claude_code`, preset `Minimal` — it relays, it never reasons;
- title `- Watchdog (<feature>)`, with the `- ` prefix like every internal session;
- **visible, never hidden**: the human sees its ticks arrive in your conversation and must
  be able to find the session behind them;
- question widget disabled, like every internal session;
- annotations: `bwr.schema=1` · `bwr.job=watchdog` · `bwr.feature=<feature>` ·
  `bwr.status=working`. No mode, no lot: it lives through all of them.
