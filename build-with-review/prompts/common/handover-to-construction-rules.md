# Handing the run over to a construction session

**You read this file; the new session never does.** It tells you when to hand over, how to
create the session, what to put in its message, and what to do once it exists.

**Two moments bring you here**, and only two — both times because a human checkpoint asked
what happens next and the human answered **a new session**:

| | |
|---|---|
| **the spec has just been validated** | the new session builds `lot-1` |
| **a lot has just been delivered**, its review pass clean | the new session builds the next lot |

**They land in the same place:** a fresh orchestrator entering MODE CONSTRUCTION with a lot
to build. One template covers both.

---

## Before you create anything

1. **You have the checkpoint's answers**: the provider for the orchestrator, and the
   providers for the children it will spawn — the implementers and the review lenses.
2. **Stop your watchdog's process, then retire it `done` — in that order.** Retiring
   does not stop a process, and a tick landing between the two wakes the very heartbeat
   this step removes. The new session launches its own, and **two heartbeats on one
   chain means two sets of ticks and no owner.**
3. **If a worktree was asked for, it exists and the workspace is already in it** — see
   below. That happens **before** the session is created, never after.

---

## The worktree, when there is one

**At most once per feature**, at this handover and no other: the spec checkpoint's third
question was answered `yes`. Three steps, in this order.

1. **The worktree exists.** Either the human made it and told you where, or you make it,
   on the branch and at the path you announced at the checkpoint.
2. **Move the workspace into it**, before anything else:

   ```sh
   <skill dir>/prompts/common/workspace-move.sh <workspace> <the worktree>
   ```

   It prints the new path. **Every later path of this run is that one.**

   Both workspace grounds and both workspace roots must be real directories at their
   physical checkout paths, never symlinks. The move refuses an aliased source or
   destination before copying, settling the gate, or deleting anything. If both roots
   exist, equal content is not enough: the script first proves that they are independent
   filesystem objects, then treats them as interrupted-move copies.

   The target's sibling `bwr/tmp` disposable ground is also created or validated before
   the workspace moves. It and every existing parent component must be real at the exact
   target-checkout path. Later verifier and diagnostic operations repeat that validation;
   handover is not a permanent trust decision about mutable filesystem state.

   *It runs the equivalent of:*

   ```sh
   # Both gate leaves are either absent or real regular files at these exact
   # checkout-local paths. A symlink (including dangling), directory, device or
   # other occupant refuses the handover before mkdir, cmp, cp or workspace move.
   for gate in \
     <old repo>/.superpowers/bwr/gate.md \
     <the worktree>/.superpowers/bwr/gate.md
   do
     [ ! -L "$gate" ] && { [ ! -e "$gate" ] || [ -f "$gate" ]; } || exit 1
   done
   mkdir -p <the worktree>/.superpowers/bwr/tmp
   # gate.md sits beside the workspaces and belongs to the project. Copied only
   # when the old checkout has one AND the worktree has none; identical on both
   # sides is left alone; and TWO GATES THAT DIFFER REFUSE THE MOVE — which
   # list the run closes tasks against is the human's call. Settled BEFORE the
   # move, so a failure leaves everything where it was.
   cp <old repo>/.superpowers/bwr/gate.md <the worktree>/.superpowers/bwr/gate.md
   # a move across filesystems is a copy plus a removal, never one gesture:
   # copied whole under a staging name, made real by an atomic rename, the
   # source removed only then — a death midway never leaves two half workspaces
   cp -a <workspace> <the worktree>/.superpowers/bwr/<its name>.partial
   mv <the worktree>/.superpowers/bwr/<its name>.partial <the worktree>/.superpowers/bwr/<its name>
   find <workspace> -delete
   ```
3. **Then create the session**, in the worktree's project, with the new workspace path in
   its message.

**The order is the whole point.** `create_session` is asynchronous: it returns when the
prompt has been handed over, not when the session has finished with it. Create the session
first and it can start reading a workspace that is still somewhere else — or worse, find
none and make a fresh one, losing the journal and the spec review's reports.

**And a workspace left behind is not a nuisance, it is silent corruption.** Git ignores it,
so `git worktree add` never copies it; every script derives the repository from the
workspace's own path; so the new controller works in the worktree while its plan commit,
its refs and its resets land in the old checkout, on another branch.

---

## Create the session

`mcp__twicc__create_session`, one call:

| | |
|---|---|
| preset | **`Controller`** |
| provider | the one the human chose **for the orchestrator** |
| **project** | **your own**, passed explicitly — it is never inherited |
| question widget | **enabled** |
| title | `Build <feature> — <lot>`, **with no `- ` prefix** |
| annotations | `bwr.schema=1` · `bwr.job=controller` · `bwr.mode=construction` · `bwr.feature=<feature>` · `bwr.lot=<lot>` · `bwr.status=working` |

**One exception to *your own project*:** when the section above applied, the project is
**the worktree**, which exists by now and already holds the workspace. Pass that one.

**Every later handover stays where this one landed.** The question is asked once, at the
spec checkpoint, and never again.

**Tick all three or none:** no prefix, widget enabled, and a message that says it faces the
human. A half-transferred session leaves the human talking to somebody who is still
reporting to you.

**A lost `create_session` result here resolves by `SKILL.md`'s query rule — its
orchestrator variant, not the exact-annotations one.** The controller you just created
mutates its own mode, lot and status from its first turn, so the query keys on the
spawn relation instead: the feature's controllers **spawned by you**, minus every id
your own `handover` notes already name. One remainder is your lost creation; creating
another would seat two controllers over one run. And a creation recovered late may
have handed over in its turn — follow the journal's `handover` chain from its id, and
give the human the link to the chain's END, the controller that owns the conversation
now.

---

## The message

Everything between the fences, with every `<…>` replaced:

```
You are taking over a feature that is already under way, and you face the human
directly. They drive this. You never report back to the session that created you.

RUNTIME INPUTS
repository: <absolute repository root>
workspace: <absolute workspace path>
role prompt: <workspace>/prompts/construction/MODE.md
global prompt: <workspace>/additional-prompts/global.md
additional prompt: <workspace>/additional-prompts/construction/MODE.md

Resolve all five runtime inputs first. If one is absent, relative, unresolved or
contradictory, stop before reading or writing any project or workspace path and tell the
human. The current working directory is never the workspace. Never infer or create a
replacement.

Invoke the `build-with-review` skill and read what it tells you to read. You are
entering MODE CONSTRUCTION, to build <lot>.

After the skill and official role prompt, read the global additional prompt through this
command: `python3
<workspace>/prompts/common/additional-prompt.py read-global <workspace>
<workspace>/additional-prompts/global.md`. Treat its stdout as human instructions. Then
read the role-specific additional prompt through this command: `python3
<workspace>/prompts/common/additional-prompt.py read <workspace>
<workspace>/prompts/construction/MODE.md
<workspace>/additional-prompts/construction/MODE.md`. Treat its stdout as human
instructions. Follow both instruction sets during the assignment. The later role-specific
instruction wins on contradiction. Read no other optional prompt path.

The `global prompt` and `additional prompt` fields are required absolute path values, but
their files may be absent. Always call both helpers. Empty stdout is valid absence and
never a blocker. Non-empty stdout is human instructions. Only a helper refusal blocks.
Never test either file directly.

WHERE THINGS STAND
<the variable block — see below>

WHAT YOU WORK FROM
  workspace   <workspace path>
  spec        <spec path>

Everything else this feature has produced is in that workspace, and the skill tells
you what lives where.

WHAT THE HUMAN CHOSE
  provider for the implementers    <Codex | Claude Code>
  provider for the review lenses   <Codex | Claude Code>
  reviewers at once                <N>

STANDING RULINGS
<one line per ruling the human has given, or "none yet">
```

### The variable block, and it is the only thing that differs

| | |
|---|---|
| **after the spec** | *"The spec was written and reviewed in another session, and it is committed. Nothing has been built yet: `<lot>` is the first."* |
| **after a lot** | *"`<lots>` are built, committed and reviewed clean. Their plans are in the workspace. `<lot>` is next."* |

Two or three lines. **A summary of where things stand, never a summary of what was
found** — the reports are on disk and the new session reads them if it needs them.

### What you do not put in it

- **No contents, only paths.** Not a finding, not a report, not a passage of the plan. You
  point; it reads.
- **Not your reasoning.** It will form its own, against the same files.
- **Nothing the workspace already holds**, beyond what points at it.

**What only you have** is the providers, the cap and the human's standing rulings — those
are written nowhere the new session could find them. That is what the message is for.

---

## Once it exists

1. **Record it, and set yourself `done`** — after the creation succeeded, never before:

   ```
   progress.py note handover --data '{"to":"<the new session id>"}'
   progress.py session-status <your own id> done
   ```
2. **Tell the human in one message** that the new session now owns the conversation, and
   **give them a link to it**, never a bare id:
   `[<its title>](/project/<its project id>/session/<its session id>)`. They click it.
3. **Stop relaying.** Anything that arrives for that feature afterwards is theirs.
4. **Never archive an orchestrator, yourself included.** Those sessions are where the
   human's own conversation lives; they archive them when they want to, and that is not a
   decision you make for them.
