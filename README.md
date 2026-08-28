# Build With Review

Build With Review is an agent skill for developing a feature from an idea to reviewed, committed code.
It combines product specification, implementation planning, task-by-task construction, technical checks, and product review in one resumable workflow.

The skill was designed to run in [TwiCC](https://github.com/twidi/twicc).
It uses TwiCC projects, sessions, agent orchestration, annotations, and process controls as part of its workflow.

The skill is designed for work where correctness matters more than speed alone.
It separates product decisions, implementation, verification, and review so that no actor approves its own work.

## How it works

The workflow uses three main modes and one temporary mode:

1. **SPEC** defines product behaviour and divides the feature into ordered lots. Independent mandates review the specification before construction begins.
2. **CONSTRUCTION** creates a plan for one lot, validates its completeness, and implements it as sequential tasks. Each task passes design review, code review, and the project's complete verification gate before acceptance.
3. **PRODUCT REVIEW** examines the working product through independent lenses. The complete actionable set selects one exclusive construction route. A bounded implementation correction opens a Correction Round on the built unit. A structural correction opens a sub-lot. A clean pass delivers the lot.
4. **AMENDMENT** handles an answered product decision that changes already-built behaviour. It verifies the change and its reach, updates the specification, and returns control to the interrupted mode.

SPEC mode starts from the [Superpowers `brainstorming` skill](https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md) for product discovery and design dialogue.
This currently requires Superpowers to be installed and available as a skill for both Claude Code and Codex.
Build With Review then applies its own specification structure and review system.
(This dependency may change. A future version may integrate only the brainstorming mechanisms that Build With Review needs.)

This cycle continues through the selected correction route until every lot is built and a complete product-review pass finds no remaining issue.

```text
SPEC -> CONSTRUCTION -> PRODUCT REVIEW
            ^                 |
            | bounded implementation correction -> Correction Round on the built unit
            | structural correction -> sub-lot
            | clean pass -> delivered lot
            +----------------+

Any mode -> AMENDMENT -> interrupted mode
```

## Core principles

- **Run before judging.** Product review starts only after the full project gate passes.
- **Independent proof.** Findings require evidence and another actor verifies or resolves them.
- **One human channel.** Agents route product questions to the orchestrator. Only the human decides unspecified product behaviour.
- **Strict ownership.** The orchestrator coordinates but does not write code. Implementers own code changes. Reviewers do not fix what they review.
- **Risk-based discovery.** Discovery reviewers combine impact with probability. Low-risk observations remain private and do not enter workflow state.
- **Exact generations.** Plans, task contracts, review inputs, checker results, gates, and commits are bound to the exact artifacts they validate.
- **Durable recovery.** An append-only journal and a run workspace preserve state across interruptions, compaction, and session handovers.
- **Bounded work.** Review loops, retries, diagnostics, and checker calls have explicit limits and recovery routes.

## Workflow building blocks

The skill coordinates several specialized roles:

- the **orchestrator**, which owns workflow state and human communication;
- **spec reviewers** and a **spec fixer**;
- one **implementer session per task attempt**;
- independent **design and code checker subagents** inside each attempt;
- **product-review lenses** and dedicated finding verifiers;
- an **amendment fixer** and a reach reviewer;
- a **watchdog**, which reports stalled or forgotten sessions.

The workflow also uses Git refs, immutable artifacts, atomic helper scripts, and a structured `progress.jsonl` journal.
These mechanisms make retries and handovers explicit instead of relying on conversation memory.

## Human involvement

The human remains the product owner.
The workflow asks for input only at defined checkpoints or when the specification does not determine user-visible behaviour.

Ordinary findings do not go directly to the human.
Agents prove, verify, and route them through the normal correction flow.

## Repository layout

- [`build-with-review/SKILL.md`](build-with-review/SKILL.md) contains the orchestrator contract and shared machinery.
- [`build-with-review/prompts/spec/`](build-with-review/prompts/spec/) defines specification authoring and review.
- [`build-with-review/prompts/construction/`](build-with-review/prompts/construction/) defines planning, implementation, task checks, gates, and recovery.
- [`build-with-review/prompts/product-review/`](build-with-review/prompts/product-review/) defines the product-review lenses and adjudication flow.
- [`build-with-review/prompts/amendment/`](build-with-review/prompts/amendment/) defines specification amendments and reach analysis.
- [`build-with-review/prompts/common/`](build-with-review/prompts/common/) contains shared vocabulary, journal rules, risk admission, worker rules, and workspace helpers.
- `build-with-review/test_*.py` contains the workflow contract and runtime regression suites.
- [`build-with-review/dashboard/`](build-with-review/dashboard/) contains the journal dashboard.

The detailed operational contract lives in the skill itself.
This README only describes its purpose and overall structure.

---

Made by @twidi and @codex.
