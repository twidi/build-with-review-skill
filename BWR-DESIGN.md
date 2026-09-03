# Build With Review Design

This document defines the detailed design of Build With Review. It translates the operating philosophy into role contracts, artifacts, and workflows. `PHILOSOPHY.md` defines the product philosophy.

`OPERATING-PHILOSOPHY.md` defines the general operating model. This document controls the implementation of the BWR skill and its prompts.

## 1. Design principles

BWR coordinates trusted agents. It does not build a proof engine around them.

The design uses:

- Git for durable product history;
- tracked Markdown for the Current Spec and plans;
- untracked Markdown reports for handoffs;
- TwiCC for sessions, live state, and annotations;
- independent review for confidence.

BWR has no checksum protocol. It has no inode or symlink protocol. It has no structured event ledger.

It has no automatic history validator. It has no parser for reports, `PROGRESS.md`, or `GUIDE.md`. An agent reports its work.

The next responsible actor can challenge that work.

Only one session writes tracked product files at a time. Parallel reviewers write separate report files.

## 2. Stable vocabulary

### Feature

A Feature identifies one complete BWR run. Its identifier uses this format:

```text
YYYY-MM-DD-<slug>
```

The date uses the Orchestrator's local date. The slug uses lowercase letters, digits, and hyphens.

Example:

```text
2026-09-01-session-notifications
```

The identifier remains stable for the complete run.

### Lot

A Lot is one planned delivery stage from the Current Spec. Every Lot identifier starts with `lot-`. Examples are `lot-1`, `lot-1.1`, and `lot-1.10`.

The string prefix prevents tools from treating `1.10` as a decimal number.

### Task

A Task is one coherent construction unit inside a plan. Tasks run sequentially.

### Attempt

An Attempt is one Implementer session for one Task. A failed Attempt does not continue in a replacement session. The replacement starts a new Attempt.

### Round

A Round identifies one review or check assignment. Round numbers provide identity only. They never impose a retry limit.

### Pass

A Pass is one complete Product Review of one frozen commit. All five Product Review lenses belong to the same Pass.

### Correction Round

A Correction Round handles one bounded correction set after Product Review. It is not a sub-lot. Its identifier uses the parent Lot and a correction number.

Example:

```text
lot-1 / correction-1
```

### BWR workspace

The phrase is always **BWR workspace**. Do not use `workspace` alone for this concept. The only prompt placeholder is `<BWR_WORKSPACE>`.

No `BWR_WORKSPACE_ROOT` variable exists.

## 3. Sources of authority

Use the following priority when two sources conflict:

1. System instructions and project instructions.
2. Explicit Human decisions.
3. Current Spec.
4. Current Lot, sub-lot, or Correction Round plan.
5. Accepted Task Design.
6. Real Git state.
7. `GUIDE.md`.
8. `PROGRESS.md`.
9. Reports.
10. Annotations.

This order does not make every source interchangeable. The Current Spec controls product intent.

The plan controls the current decomposition. The Design controls the implementation approach for one Task. Git shows the real technical state.

`GUIDE.md` stores current run instructions. `PROGRESS.md` stores durable operating memory. Reports store observations and handoffs.

Annotations make live sessions readable. If project instructions make `GUIDE.md` stale, the project instructions win. The Orchestrator then updates `GUIDE.md`.

## 4. Tracked product documents

BWR follows existing repository conventions first. When the repository has no relevant convention, use these paths:

```text
docs/specs/<feature>.md
docs/specs/<feature>-amendment-1.md
docs/specs/<feature>-amendment-2.md
docs/plans/<feature>-lot-1.md
docs/plans/<feature>-lot-1.1.md
docs/plans/<feature>-lot-1-correction-1.md
```

Amendments stay beside the Current Spec. BWR does not create a separate Amendment directory. Plans and Correction Round plans stay beside other plans.

The BWR workspace never contains authoritative copies of these documents.

### Current Spec contract

The Current Spec contains, with flexible headings:

- the goal;
- the users and expected result;
- scope and out-of-scope behavior;
- product behaviors;
- states and transitions;
- errors, retries, and recovery;
- important interactions;
- global constraints;
- verification behaviors and proof boundaries;
- the Lot breakdown;
- dependencies between Lots.

Each Lot states its responsibility, obligations, dependencies, and end state. The approved Current Spec has no necessary unresolved product question. It does not predefine future functions, signatures, commands, tasks, or reports.

BWR has no global requirement identifier registry. Actors reference an obligation with its heading path and a short exact quote.

### Lot plan contract

A Lot plan contains:

- Feature and Lot identifiers;
- the Current Spec path;
- the covered Current Spec headings and short quotes;
- responsibilities;
- probable areas;
- ordered Tasks.

Each Task contains:

- `Sources`;
- `Depends on`;
- `Achieves`;
- `Probable locations`;
- `To verify`;
- an empty `Design` section.

The plan stays thin. It does not copy global constraints from the Current Spec. It does not predefine signatures, functions, commands, or detailed tests.

After delivery, the committed plan becomes historical.

### Task Design contract

The Implementer writes the Design inside the tracked Task section. The Design contains:

- the approach;
- ordered steps;
- affected areas or files;
- interfaces and state;
- material alternatives;
- behaviors to prove.

A step states the area, change, and expected result. The Design can define concrete signatures, formats, states, and events. It does not contain full implementation code.

It does not invent a product decision. A material Design change during coding stops the affected work. The Implementer updates the Design, self-reviews it, and starts a fresh Design checker.

Coding resumes only after a clean Design check.

### Correction Round plan contract

A Correction Round plan contains:

- Feature, Lot, and correction identifiers;
- Current Spec path;
- reviewed commit;
- parent plan path;
- every confirmed source finding;
- every verification report;
- the resulting correction obligations;
- obligations that must remain preserved;
- ordered Tasks with empty Design sections.

Each source uses `<reviewer-report>#<finding-id>`. The Orchestrator self-reviews this plan. A fresh Plan completeness checker must return clean before commit.

### Sub-lot plan contract

A sub-lot plan contains:

- Feature and sub-lot identifiers;
- Current Spec path;
- reviewed commit;
- parent plan path;
- all source findings;
- parent, Current Spec, and earlier correction obligations to preserve;
- ordered Tasks with empty Design sections.

The sub-lot follows the normal plan check, construction, and Product Review workflows.

## 5. BWR workspace

The BWR workspace is inside the active checkout or worktree. Its path is:

```text
<ACTIVE_PROJECT_ROOT>/bwr_workspace/<FEATURE>
```

This complete path is `<BWR_WORKSPACE>`. The parent directory can contain several BWR workspaces. BWR does not commit the BWR workspace.

BWR does not modify `.gitignore` automatically. BWR does not modify user-level Git ignore rules. The Human can choose an ignore mechanism.

Committers must exclude the BWR workspace from every commit. The standard structure is:

```text
<BWR_WORKSPACE>/
├── PROGRESS.md
├── GUIDE.md
├── ADDITIONAL-INSTRUCTIONS.md  # optional and Human-owned
└── reports/
```

`PROGRESS.md` and `GUIDE.md` always exist after initial setup. `ADDITIONAL-INSTRUCTIONS.md` is optional. The Orchestrator does not create it by default.

### `PROGRESS.md`

Only the active Orchestrator writes `PROGRESS.md`. It contains:

- Feature and goal;
- Current Spec path;
- current Git commit;
- provider choices;
- Review Concurrency;
- completed Lots;
- current Lot;
- Human decisions;
- Amendments;
- durable route changes;
- durable blockers;
- final result.

It does not contain:

- Gate commands;
- Git conventions;
- detailed session state;
- active topology;
- complete findings;
- complete reports;
- transcripts;
- checksums;
- noisy events.

`PROGRESS.md` is free Markdown. No tool parses it. Ordinary children do not read it.

The Human, active Orchestrator, successor Orchestrator, and Recovery Orchestrator use it.

The Orchestrator edits current configuration in place. It appends only durable events to the chronological log.

BWR performs no automatic `PROGRESS.md` compaction.

### `GUIDE.md`

Only the active Orchestrator writes `GUIDE.md`. It contains run-specific operating instructions. The required sections are:

```markdown
# BWR Guide

## Git

- Commit style: <short description>
- Language: <language>
- Scope rules: <rules or none>
- Project instructions: <paths>

## Gate

### Included commands

- `<command>` — <purpose>

### Excluded commands

- `<command>` — <reason>

### Execution groups

#### Group 1

Run in parallel:

- `<command>`
```

The Orchestrator can adapt headings to the repository. No tool parses this file. Every Orchestrator and Implementer reads it.

A Construction diagnostic reads it when Git, Gate, or environment facts are relevant. Other actors do not read it by default.

### `ADDITIONAL-INSTRUCTIONS.md`

This file belongs to the Human. The Orchestrator never rewrites it. When it exists, every newly created BWR session receives its content.

These instructions do not replace higher authority. A later edit applies automatically to sessions created after the edit. It does not automatically change an active session.

The Human can ask the Orchestrator to send a follow-up to active sessions.

## 6. Report storage

Reports are durable working memory for one BWR run. They are not product authority.

They are not committed. The parent constructs an exact unique report path before session creation. One report has one active writer.

A new logical assignment gets a new file. A follow-up for the same assignment overwrites the same file. BWR creates no `v2` file for a follow-up.

A replacement session for the same logical assignment inherits that Report path only after the failed writer stops and retires. Recovery assigns a fresh path for unfinished work.

BWR performs no report compaction. BWR uses this structure:

```text
<BWR_WORKSPACE>/reports/
├── spec/
│   ├── full-round-1/
│   │   ├── enumerator.md
│   │   ├── verifier.md
│   │   ├── feasibility.md
│   │   └── judge.md
│   ├── scoped-round-1.md
│   ├── scoped-round-2.md
│   ├── fixer.md
│   └── risk-filtered/
│       ├── enumerator.md
│       ├── verifier.md
│       ├── judge.md
│       ├── ripple.md
│       └── scoped.md
├── amendments/
│   └── amendment-1/
│       ├── round-1-reach.md
│       ├── fixer.md
│       ├── consolidation-round-1.md
│       └── risk-filtered-reach.md
├── planning/
│   └── lot-1/
│       └── check-round-1.md
├── construction/
│   └── lot-1/
│       └── task-1/
│           └── attempt-1/
│               ├── implementer.md
│               ├── design-check-round-1.md
│               ├── code-check-round-1.md
│               ├── risk-filtered-design.md
│               └── risk-filtered-code.md
└── product-review/
    └── lot-1/
        ├── risk-filtered/
        │   ├── unlooked.md
        │   ├── user.md
        │   ├── meaning.md
        │   └── quality.md
        └── pass-1/
            ├── reviewer-unlooked.md
            ├── verifier-unlooked.md
            └── ...
```

The Orchestrator can add directories that preserve the same identity rules. No script validates this tree.

The Implementer uses one `implementer.md` report for the complete Attempt. A failed Attempt records its failure information in that same report. BWR creates no separate failure report.

## 7. Common handoff protocol

Every child writes its assigned report before its handoff. It then sends this concise message to its parent:

```text
RESULT: READY | BLOCKED | FAILED
REPORT: <assigned absolute path>
SUMMARY: <one short result>
PARENT ACTION: <next expected action, or none>
```

The parent always checks that:

- the message announces one valid result;
- the report path matches the assignment;
- the report exists at that path.

The current Workflow explicitly tells the parent to read or not read the report.

A routing parent does not read it. It passes the exact path to the next child.

The parent reads it when it must act on details, make a detailed decision, inform the Human, or analyze an exceptional result.

When it reads, it checks visible completeness only. It does not repeat the assignment or verify the report's claims.

The parent does not reconstruct hidden work history.

The parent does not parse the report or require a checksum.

`READY` means that the current deliverable is ready for routing. The child can remain `idle` while its assignment can receive a follow-up. Final acceptance changes the status to `done`.

Creation and follow-up use `working`. `BLOCKED` uses `blocked`, and `FAILED` uses `failed`.

## 8. TwiCC session rules

TwiCC is the only session system. BWR does not support provider subagents.

A parent manages only its direct children. The Orchestrator owns all children except Design and Code checkers. The Implementer owns its Design and Code checkers.

### Creation rules

Every parent creates a child in the same TwiCC project. This rule preserves the active checkout or worktree.

Every non-Orchestrator child title starts with the exact prefix `- `.

An Orchestrator title never starts with this prefix. This rule includes initial, successor, and Recovery Orchestrators.

Every non-Orchestrator child uses:

- CLI: `--mute-on-user-turn`;
- MCP: `mute_on_user_turn: true`.

This rule includes the watchdog. An Orchestrator remains unmuted. Muted sessions still notify for questions, approvals, failures, and usage alerts.

Every non-Orchestrator child uses `--no-question-widget` or `question_widget: false`.

Every Orchestrator keeps the Human question widget enabled. Children stay visible while they work. BWR does not create them with `--hidden`.

The parent supplies only applicable annotations. The parent also supplies:

- the selected provider and role preset;
- exact input paths;
- exact report path;
- `<BWR_SKILL>`;
- `<BWR_WORKSPACE>`;
- the dynamic assignment.

The child uses only its assigned inputs, role instructions, and report paths. It does not depend on parent or sibling transcripts.

It reports blockers to its parent. It never asks the Human directly.

### Retirement rules

After final acceptance of a non-Orchestrator child, the direct parent:

1. sets the terminal annotation status;
2. archives the session;
3. hides the session.

The child never archives or hides itself.

BWR never archives or hides an Orchestrator. This rule also applies to an old Orchestrator after accepted succession.

### Status values

BWR uses:

- `working`;
- `idle`;
- `blocked`;
- `done`;
- `failed`;
- `cancelled`;
- `superseded`.

Terminal values are `done`, `failed`, `cancelled`, and `superseded`. BWR has no `paused` or `stopped` state. The child maintains its status.

The parent can correct a stale status after observing real state.

`BLOCKED` work resumes in the same session. `FAILED` work never does.

The owning Workflow can stop the work, create a new logical assignment, or replace the failed session. A replacement for the same assignment starts only after the old writer stops and retires.

### Annotations

BWR uses these optional keys:

- `bwr.role`;
- `bwr.status`;
- `bwr.phase`;
- `bwr.feature`;
- `bwr.lot`;
- `bwr.task`;
- `bwr.attempt`;
- `bwr.round`;
- `bwr.pass`;
- `bwr.mandate`;
- `bwr.correction`.

Every BWR session receives `bwr.role`, `bwr.status`, and `bwr.feature`. It receives other keys only when they apply. Do not write empty placeholder values.

Annotations never prove a workflow transition.

Use this applicability map:

| Session | Applicable assignment annotations |
|---|---|
| Orchestrator | `bwr.phase`, plus Lot or correction when applicable |
| Watchdog | no additional assignment key |
| Spec reviewer | `bwr.phase=spec`, `bwr.round`, `bwr.mandate` |
| Spec fixer | `bwr.phase=spec` |
| Reach reviewer | `bwr.phase=amendment`, `bwr.round` |
| Amendment fixer | `bwr.phase=amendment` |
| Consolidation checker | `bwr.phase=amendment`, `bwr.round` |
| Plan completeness checker | `bwr.phase=planning`, `bwr.lot`, `bwr.round` |
| Implementer | `bwr.phase=construction`, Lot, Task, Attempt, and correction when applicable |
| Design or Code checker | Implementer keys plus `bwr.round` |
| Construction diagnostic | construction, Lot, Task, and correction when applicable |
| Product reviewer | `bwr.phase=product-review`, Lot, Pass, and mandate |
| Finding verifier | Product reviewer assignment keys |

## 9. Session ownership

### Orchestrator contract

The Orchestrator owns workflow, routing, and durable operating memory. It does not replace specialist roles.

It writes the initial Spec, Amendments, and plans. It also corrects its own plans.

It creates sessions, assignments, report paths, annotations, handoffs, and commits for its owned documents. It maintains `PROGRESS.md` and `GUIDE.md`.

It checks visible handoff completeness only. It does not redo a reviewer, fixer, checker, Implementer, verifier, or diagnostic mandate.

It is the only normal Human interlocutor. It presents every Human decision with complete context and consequences.

The Orchestrator directly owns:

- watchdog;
- Spec reviewers;
- Spec fixer;
- Reach reviewer;
- Amendment fixer;
- Consolidation checker;
- Plan completeness checker;
- Implementers;
- Construction diagnostic;
- Product reviewers;
- Finding verifiers;
- successor Orchestrator.

The Implementer directly owns:

- Design checkers;
- Code checkers.

One session owns one logical assignment. The same session handles follow-ups for that assignment. A new Round, Pass, Task, Attempt, or mandate creates a fresh session.

## 10. Provider setup

The first Orchestrator asks all routine provider choices during initial setup. It asks one choice for each group:

1. Document reviewers: Spec, Reach, Plan, and Consolidation.
2. Fixers: Spec and Amendment.
3. Implementer.
4. Implementer checkers: Design, Code, and Construction diagnostic.
5. Product reviewers.
6. Finding verifiers.

The provider can require several consecutive widgets. The design defines no widget count.

The initial setup does not ask for the current Orchestrator provider. The Human can change a provider choice at any time. The Orchestrator updates `PROGRESS.md`.

When an Orchestrator creates a successor, it asks for the successor provider. The successor receives the previous provider map as recommended defaults.

### Presets

The role controls the preset.

| Role | Preset |
|---|---|
| Orchestrator | `Controller` |
| Watchdog | `Minimal` |
| Spec Enumerator and Ripple | `ReviewerLight` |
| Other Spec reviewers | `Reviewer` |
| Reach reviewer | `Reviewer` |
| Plan completeness checker | `ReviewerMedium` |
| Consolidation checker | `ReviewerMedium` |
| Spec fixer and Amendment fixer | `Fixer` |
| Implementer | `Implementer` |
| Design checker, Code checker, and diagnostic | `Reviewer` |
| Finding verifier | `ReviewerLight` |
| Product `unlooked`, `user`, and `quality` | `Reviewer` |
| Product `meaning` and `coverage` | `ReviewerMedium` |

The watchdog always uses provider `claude_code` and preset `Minimal`.

## 11. Review Concurrency

The Human selects one Review Concurrency value during initial setup. The Orchestrator records it in `PROGRESS.md`.

The value applies to Spec full-round fanout and Product lens chains. It does not apply to Reach, Plan, Consolidation, Design, or Code checks. It never creates parallel Implementers.

No scheduler or pool script enforces it.

The Human can change the value during the run. The Orchestrator records the new value and uses it for future launches.

### Spec use

Each active Spec reviewer occupies one slot. A completed reviewer frees its slot.

### Product Review use

One Product lens chain holds one slot from reviewer launch through verification settlement. For a report with findings:

1. The reviewer finishes and becomes `idle`.
2. The verifier starts in the same logical slot.
3. An `UNVERIFIABLE` verdict returns to the same reviewer.
4. The same verifier checks the revised report.
5. Final settlement retires both sessions and frees the slot.

A clean reviewer closes directly and frees its slot. The Orchestrator starts another lens as soon as a slot becomes free.

## 12. Common review contract

A review report uses this base shape:

```markdown
# <Role> Report

Subject: <exact subject>
Verdict: CLEAN | FINDINGS | BLOCKED

## Coverage

<what the mandate examined>

## Findings

<admitted findings, or none>
```

`CLEAN` means that the role completed its complete mandate and admitted no finding. `FINDINGS` means that the role completed its mandate and reported all admitted findings. `BLOCKED` means that an exact operational obstacle prevents the mandate.

A DECISION uses the `FINDINGS` report verdict. The reviewer proposes no fix unless its role requires correction work.

The complete review subject remains frozen while the reviewer works. A changed subject supersedes the review and requires a fresh session.

## 13. Finding model

### Severity

Severity measures consequence only. It uses three values. **CRITICAL** means one of these consequences:

- data loss;
- destructive action;
- serious security failure;
- silent wrong delivery;
- loss of an authoritative decision.

**IMPORTANT** means one of these consequences:

- incorrect behavior;
- blocked work;
- broken recovery;
- a false result that remains detectable or recoverable.

**MINOR** means limited friction, clarity, diagnostics, or maintainability impact. It has no credible wrong product result. Probability never lowers Severity.

A concrete incorrect behavior is at least IMPORTANT unless it is CRITICAL. DECISION is separate from Severity. Every confirmed finding requires correction.

### Probability

Probability describes the concrete scenario frequency. It does not describe reviewer confidence. It uses four values.

**FREQUENT** means repeated occurrence on a normal path. **PLAUSIBLE** means ordinary use, common mistakes, common failures, or common configuration. **RARE** means an unusual but supported environment, timing, or combination.

**EXCEPTIONAL** means deliberate internal manipulation, unsupported corruption, or several independent exceptional conditions. An adversarial action is not automatically exceptional.

### Admission matrix

| Severity / Probability | FREQUENT | PLAUSIBLE | RARE | EXCEPTIONAL |
|---|---:|---:|---:|---:|
| CRITICAL | Report | Report | Report | Filter |
| IMPORTANT | Report | Report | Filter | Filter |
| MINOR | Report | Filter | Filter | Filter |

The reviewer uses Probability privately. The public finding contains Severity only. The Finding verifier never receives or discusses Probability.

### Cases without Probability filtering

The Spec Feasibility reviewer reports every infeasible written contract. The Product `coverage` reviewer reports every concrete missing obligation. A direct violation of the Current Spec or Task contract is always reported.

This rule applies to Design, Code, and Product review. Probability applies only to a new inferred risk beyond an explicit contract. Plan completeness and Consolidation do not use Probability.

The Finding verifier never uses Probability.

### Public finding

An ordinary public finding uses:

```markdown
## IMPORTANT F1 — <checkable claim>

Where: <file and lines, user path, or document passage>

Scope edge: <direct connection with the reviewed subject>

Observed: <observable fact>

Expected: <required behavior or property>

Consequence: <what can go wrong>

Evidence: <reproduction, citation, or absence search>
```

The heading states a verifiable claim. The finding includes a direct scope link and concrete consequence. Evidence uses one of these forms:

- reproduction;
- citation;
- absence;
- spec silence for a DECISION.

Finding identifiers are local to one report. The stable identity is `<report-path>#F<number>`.

### DECISION finding

A DECISION uses:

```markdown
## DECISION F4 — <unresolved product question>

Where: <where the question appears>

Scope edge: <connection with the reviewed subject>

Spec silence: <what the Current Spec does not decide>

Evidence: <observed behavior or contradiction>

Options:
- <option and user consequence>
- <option and user consequence>
```

The reviewer does not decide the answer.

### Risk-filtered history

Reviewers keep filtered candidates in one private Markdown file per stable role and scope. The parent supplies the path. The same corresponding role reads and writes that file across its loop.

The file uses:

```markdown
## <occurrence>

- MINOR × PLAUSIBLE — <candidate>
  Probability basis: <conditions>
```

The private history includes Severity, Probability, and the basis. A recurring candidate does not receive a duplicate entry. If a later review admits it, the reviewer creates a normal public finding.

The old private entry remains. A missing history file never blocks work. BWR does not compact or validate this file.

Stable scopes are:

- one file per Spec mandate across the Spec loop;
- one file per Product lens and root Lot across Product passes;
- one file per Design or Code role and Attempt across rounds;
- one file per Reach role and Amendment across rounds.

## 14. Finding verifier contract

The Finding verifier validates the reality of reported Product findings. It does not perform a second Product Review.

For each finding, it checks:

- the observed fact;
- the expected requirement;
- the scope connection;
- the consequence;
- the evidence.

For a DECISION, it checks Current Spec silence. It uses a concrete verification action. The verdicts are:

- `CONFIRMED`;
- `DISPROVED`;
- `UNVERIFIABLE`.

An environment failure is `BLOCKED`, not `UNVERIFIABLE`. The verifier does not:

- edit the product;
- fix or rewrite a finding;
- decide whether the finding is worthwhile;
- change Severity;
- receive or reassess Probability.

One verifier checks every finding in one reviewer report. A clean reviewer report receives no verifier. The verification report uses:

```markdown
## F1 — <finding title>

Verdict: CONFIRMED

Checked: <concrete action>

Observed: <result>
```

`UNVERIFIABLE` returns the assignment to the same reviewer. The reviewer overwrites its report. The same verifier then overwrites its verification report.

## 15. Spec Review roles

### Enumerator

The Enumerator performs an exhaustive mechanical scan. It checks:

- internal references;
- cited paths, symbols, commands, and tests;
- closed value lists;
- counts and absolute statements;
- table definitions;
- named behaviors without a validation method.

It does not sample. It does not judge quality, feasibility, ambiguity, indirect effects, or the complete narrative.

### Verifier

The Verifier checks factual truth against:

- code;
- runtime behavior;
- dependencies;
- project documentation.

It also checks internal factual consistency and terminology. It does not judge product value, completeness, feasibility, Lot decomposition, or mechanical references.

### Feasibility

The Feasibility reviewer asks whether each written contract can be built here as written. It checks actual runtime, dependencies, platforms, permissions, and compatibility. Normal difficulty is not a finding.

An impossible contract without a defined product choice becomes a DECISION. It does not estimate work. It does not use Probability filtering.

### Judge

The Judge checks:

- ambiguity;
- completeness of affected states;
- errors and recovery;
- procedure sequence;
- Lot decomposition.

### Ripple

Ripple starts with the second full Spec round. It follows the semantic consequences of earlier Spec edits. It checks dependent restatements, examples, procedures, and behaviors.

It does not repeat Enumerator work or perform another complete review.

### Scoped

Scoped runs after the Spec fixer. It checks:

- every previous finding disposition;
- all touched sections;
- direct dependents of those sections;
- new issues caused by the correction.

It does not validate the complete Spec alone.

### Spec fixer

One Spec fixer session remains active across the complete correction loop. It is the only Spec writer during that loop. It processes all review reports together.

It verifies findings before changing the Spec. It records:

- `APPLIED`;
- `DECLINED` with evidence;
- `SELF-DETECTED` corrections.

It also applies exact Human-requested Spec corrections and records their results and touched locations.

It self-reviews the complete corrected Spec. It does not write code, write plans, commit, or make product decisions. A missing product decision returns to the Orchestrator.

## 16. Spec workflow

The Orchestrator writes the first Spec and self-reviews it. The first full round launches:

- Enumerator;
- Verifier;
- Feasibility;
- Judge.

Later full rounds also launch Ripple. A full round with findings follows this sequence:

```text
Full round
-> same Spec fixer
-> fresh Scoped reviewer
-> same Spec fixer when needed
-> fresh Scoped reviewer until clean
-> fresh full round
```

A clean full round skips the Fixer and Scoped stages. Spec findings do not use Finding verifiers. A clean full round goes to Human approval.

When the Human requests a change, the same Spec fixer applies it. The correction then receives Scoped Review and a fresh full round.

Human approval makes the document the Current Spec. The Orchestrator commits it and retires the Spec fixer.

## 17. Amendment roles and workflow

After initial Spec approval, every confirmed Human product change uses an Amendment. During initial Spec Review, the Spec fixer integrates decisions directly.

### Amendment contract

Each Amendment has a sequential run-wide number. It contains:

- title;
- exact Human decision;
- reason;
- changes;
- preserved behavior;
- origin phase, Lot, report, and finding identifiers.

One Amendment contains one coherent decision set. It stays at product level. It does not name implementation functions or files.

The committed Amendment remains historical. Implementers read the Current Spec, not the Amendment chain.

### Reach reviewer

One Reach reviewer runs per Round. It follows direct and transitive semantic dependencies through:

- Current Spec;
- user flows;
- states;
- triggers;
- errors and recovery;
- tests;
- active decisions.

It does not rejudge the untouched baseline. Reach Review does not use Finding verifiers.

### Amendment fixer

One Amendment fixer session handles two stages. In stage one, it edits only the Amendment after Reach findings or a returned Human decision. It records and applies that decision exactly. The loop continues until a fresh Reach reviewer returns clean.

The accepted Amendment then freezes. In stage two, the fixer produces the Updated Spec from the old Current Spec and accepted Amendment. Consolidation corrections change only the Updated Spec.

The fixer does not write code, write plans, commit, or contact the Human directly.

### Consolidation checker

The checker verifies exactly:

```text
old Current Spec + accepted Amendment = Updated Spec
```

It checks both directions. It finds missing decisions and unauthorized edits. It does not rejudge the Amendment or Reach.

Each correction receives a fresh checker.

### Amendment workflow

```text
Human decision
-> Orchestrator writes initial Amendment
-> fresh Reach reviewer
-> same Amendment fixer when needed
-> fresh Reach reviewer until clean
-> accepted Amendment freezes
-> Amendment fixer writes Updated Spec
-> fresh Consolidation checker
-> Amendment fixer corrects Updated Spec when needed
-> fresh Consolidation checker until clean
-> Orchestrator commits Amendment and Updated Spec together
-> Updated Spec becomes Current Spec
```

Any Product Review pass against the old Current Spec becomes obsolete. The corrected product later receives a complete new Product Review pass.

The Orchestrator also re-evaluates interrupted work. Work with the same objective can continue after the required Design validation.

Work created under a now-false objective starts again from the appropriate plan or Attempt boundary.

## 18. Planning roles and workflow

### Plan completeness checker

The checker validates:

- complete obligation coverage;
- justification for every Task;
- backward dependencies;
- compatibility;
- preservation of existing obligations.

It does not choose implementation preferences. It does not design signatures or code.

### Planning workflow

The Orchestrator:

1. reads current inputs;
2. writes a thin plan;
3. self-reviews the complete plan;
4. corrects it until internally clean;
5. freezes the plan;
6. creates a fresh Plan completeness checker;
7. corrects findings when required;
8. repeats self-review and fresh checking until clean;
9. commits the plan before creating an Implementer.

The Orchestrator does not write Task Designs.

## 19. Construction roles

### Implementer

One Implementer owns one Task and one Attempt. It is the only tracked writer during the Attempt. It:

- inspects the repository;
- writes the Task Design;
- owns Design and Code checker sessions;
- writes tests and code;
- performs self-review loops;
- runs the complete Gate;
- creates the Attempt commit;
- writes one Implementer report.

It cannot make product decisions. It can mark a checker finding `APPLIED` or `DISAGREED` with evidence. A disagreement does not close review.

Only a fresh clean checker closes the relevant review stage.

### Design checker

The Design checker receives:

- Task contract;
- parent obligations;
- Current Spec;
- plan;
- complete Design;
- relevant repository state.

It checks:

- contract coverage;
- ordered steps;
- interfaces and state;
- project fit;
- edge cases and recovery;
- planned tests;
- invented behavior.

It tries to falsify the Design. It reports a Task-contract blocker instead of silently widening scope. A fresh checker reviews every corrected complete Design.

### Code checker

The Code checker receives the complete diff, files, tests, Task contract, and accepted Design. It checks:

- scope;
- correctness;
- errors and edge cases;
- tests that fail for the wrong behavior;
- untested branches;
- swallowed errors;
- cost;
- duplication;
- contract changes;
- maintainability.

It does not reopen an architecture preference already settled by the accepted Design. A fresh checker reviews every corrected complete candidate.

### Construction diagnostic

The Orchestrator can launch a diagnostic after repeated comparable failed Attempts. No counter forces this choice. The diagnostic classifies the cause as:

- `IMPLEMENTATION`;
- `DESIGN`;
- `EARLIER_TASK`;
- `PLAN`;
- `BLOCKED` only when indispensable information is missing.

It reports evidence and the required restart point. It modifies nothing.

## 20. Construction workflow

Tasks run sequentially. Only one Implementer is active.

For one Attempt:

```text
Inspect repository
-> write Design
-> self-review and correct until internally clean
-> fresh Design checker
-> correct, self-review, and use fresh checker until clean
-> write tests and code
-> self-review and correct until internally clean
-> fresh Code checker
-> correct, self-review, and use fresh checker until clean
-> full Gate
-> commit
-> report and handoff
```

The mandatory full Gate occurs after the final clean Code checker. The Implementer can run targeted, partial, or full checks earlier. The final Implementer report states whether the final Gate ran and passed.

The Orchestrator trusts the visible handoff and report.

### Implementer report

One report belongs to the complete Attempt. The Implementer updates it throughout the Attempt. It contains:

- Design Review rounds;
- Code Review rounds;
- finding dispositions;
- validation performed;
- final Gate declaration;
- delivered result;
- commit identifier;
- failure information when applicable.

A new checker receives:

- the previous checker report;
- the current Implementer report;
- the corrected complete subject.

### Attempt outcomes

`READY` requires a complete report, passing full Gate, and commit. `BLOCKED` resumes in the same session after the blocker is removed. `FAILED` means the Implementer cannot produce a valid result in the current Attempt.

A Gate failure first returns to correction in the same Attempt.

A fresh Attempt after failure receives the selected restart boundary, relevant failed Implementer Report paths, and any Diagnostic Report path. The new Implementer reads them as evidence. The Current Spec, Plan, Task, and project state remain authoritative.

A `DESIGN` restart produces a new complete Design. It does not preserve the failed approach as authority.

## 21. Failed Attempt Git workflow

If a failed Attempt has assigned tracked changes, the Implementer creates a preservation commit. It can include the Design, tests, and code.

If no assigned tracked change exists, it creates no empty commit. The Orchestrator never resets history.

The next commit reverts the failed Attempt and can include the revised plan.

An `EARLIER_TASK` or `PLAN` route enters the Plan write Workflow. It provides the relevant failed Implementer Reports, any Diagnostic Report, and the selected restart boundary.

The pending revert becomes explicit Planning commit scope. The clean revised Plan and that revert form one commit. Construction resumes from the earliest incomplete or revised Task.

The history becomes:

```text
Plan commit
-> Failed Attempt commit
-> Revert and revised plan commit
-> New Attempt commit
```

The Orchestrator uses basic Git revert behavior. BWR creates no private refs. Product Review findings never revert a successful Attempt.

They move forward through correction work.

## 22. Product Review roles

All Product reviewers receive:

- root Lot and all sub-lots or corrections;
- exact frozen commit;
- Current Spec;
- plans;
- source findings when applicable.

Each reviewer reads the complete product through one lens. It judges what the Lot owed, regressions caused by the Lot, and preservation of future obligations. It does not report an absence explicitly assigned to a future Lot.

The Current Spec is authoritative. The plan is historical after construction.

### `unlooked`

This lens finds blind spots in:

- passing tests;
- seams between Tasks;
- unspecified behavior;
- responsibilities between roles.

### `user`

This lens follows real external paths. It covers setup, normal use, invalid or mistimed action, correction, interruption, failure, restart, and recovery. It covers concurrency and ambiguous retry when applicable.

### `meaning`

This lens follows one concept through:

- Current Spec;
- models;
- storage;
- APIs;
- events;
- user interface;
- logs;
- tests.

It detects one word with two meanings, two words with one meaning, state collapse, and incorrect null, empty, or default behavior.

### `quality`

This lens checks durable maintenance cost. It covers duplication, hidden coupling, diffuse responsibility, mixed responsibilities, speculative abstraction, ineffective tests, unjustified repository divergence, and misleading names.

### `coverage`

This lens checks the presence of every Lot obligation in the Current Spec. It also checks confirmed sub-lot corrections, global constraints, and Lot boundaries. It uses absence evidence.

It does not use Probability filtering.

## 23. Product Review workflow

The Orchestrator freezes one exact commit and all current inputs. It launches the five lenses under Review Concurrency.

No tracked file changes during the Pass. If the subject changes, all active sessions become `superseded`. The Orchestrator archives and hides them.

A fresh Pass reviews the new subject. A clean report closes its lens chain. A report with findings starts one Finding verifier in the same lens-chain slot.

A lens settles when:

- its reviewer is clean; or
- every finding is `CONFIRMED` or `DISPROVED`.

`UNVERIFIABLE` returns to the same reviewer and verifier. The Pass closes only after all five lenses settle. The Orchestrator can merge duplicates or split the set into traceable obligations.

It does not rejudge findings. A combined obligation cites every source identity. BWR creates no extra consolidated finding file.

If no confirmed finding remains, the Pass is clean. After correction, all five lenses run again on the new commit. No old verdict carries forward.

A `DISPROVED` finding closes without work. A confirmed ordinary finding becomes a correction obligation.

A confirmed DECISION goes to the Human before correction planning. The resulting product change uses the Amendment workflow.

## 24. Correction routing

The Orchestrator routes the complete actionable finding set together. It does not split one Product Review outcome between a Correction Round and a sub-lot.

Finding count and Severity do not select the route. The structural nature of the complete correction set selects it.

Use a Correction Round when:

- the correction is bounded and local;
- general architecture remains valid;
- responsibilities remain valid;
- the Task graph stays small;
- each Task maps directly to confirmed findings.

Use a sub-lot when the correction changes:

- structural responsibility;
- decomposition;
- important interfaces;
- migration;
- coordination across several areas.

Both routes use normal plan checking, construction, Gate, and Product Review.

## 25. Gate

The Gate is a Human-approved execution plan. It is not an actor.

It needs no BWR script.

### Initial discovery

Before creating the BWR workspace, the first Orchestrator searches:

- project instructions;
- project documentation;
- CI configuration;
- package manager scripts;
- repository configuration;
- existing tooling.

It presents every credible validation command to the Human. The Human selects:

- included commands;
- excluded commands;
- reasons for exclusions;
- execution order;
- commands that can run in parallel.

The Orchestrator records the result in `GUIDE.md`. An existing Gate is inherited during Recovery or succession.

### Execution

Gate groups run in order. Commands inside one parallel group start together. The next group waits for the complete previous group.

A failed parallel command does not cancel siblings that already run. Every included command must pass. Excluded commands remain visible with their reasons.

The final Gate record gives a concise command-result summary. It does not copy raw output.

A corrected Gate failure does not remain in the final Report. An unresolved failure keeps a concise diagnosis and useful evidence.

The final Task Gate validates all accumulated work.

Product Review needs no duplicate Gate when tracked files remain unchanged after the final Task Gate.

### Changes

A validation command created by an Implementer automatically joins the Gate. The Implementer runs it in the current final Gate. It records the command and recommended group in its report.

The Orchestrator updates `GUIDE.md`. When the correct group is uncertain, use a new sequential group. Removing a command without replacement requires a Human decision.

Reducing coverage also requires a Human decision.

A preexisting validation command discovered later requires a Human inclusion decision. A simple command rename replaces the previous command automatically.

## 26. Git commits

Only the Orchestrator and Implementer can create BWR commits.

### Orchestrator commit scope

The Orchestrator commits:

- approved Current Spec;
- Lot, sub-lot, and Correction Round plans;
- Amendment and Updated Spec;
- failed Attempt revert and revised plan.

### Implementer commit scope

The Implementer commits:

- successful Attempt;
- useful failed Attempt preservation state.

No reviewer, fixer, checker, verifier, diagnostic, or watchdog commits. A committer includes only its assigned commit scope. The scope can include work produced by a Fixer when the Orchestrator owns the final document commit.

Before commit, the committer:

1. inspects `git status`;
2. stages explicit paths or hunks;
3. avoids broad `git add .` or unscoped `git add -A`;
4. inspects `git diff --cached`;
5. excludes the BWR workspace;
6. preserves unrelated changes.

After context compaction, a provider summary can describe the committer's earlier changes as pre-existing changes. The committer does not infer ownership from that wording. It inspects the diff and includes matching assigned work.

The first Orchestrator determines commit style once. It uses this priority:

1. project instructions such as `AGENTS.md` or `CLAUDE.md`;
2. repository-specific Git rules;
3. recent commit history.

It records a short convention in `GUIDE.md`. Future committers reuse it. Project instructions remain authoritative.

## 27. Human decisions

The Orchestrator is the only normal Human interlocutor. Every decision request contains:

- context;
- problem;
- evidence;
- reason the decision is needed now;
- each option;
- resulting behavior;
- user consequence;
- advantages;
- disadvantages;
- risks;
- next workflow route;
- recommendation when useful.

The question widget comes after this explanation. The Human does not need to read reports, transcripts, topology, or `PROGRESS.md`. An agent never silently decides undefined product behavior.

Before asking, the Orchestrator checks three outcomes: the Current Spec already answers, facts disprove the question, or a real product choice remains. Only the third outcome reaches the Human.

## 28. Initial run setup

The initial configuration occurs before any BWR workspace write. The sequence is:

1. The Human confirms BWR launch.
2. The Orchestrator inspects the repository.
3. It discovers project rules and commit style.
4. It discovers possible Gate commands.
5. It discusses Gate inclusion, exclusion, order, and parallelism with the Human.
6. It asks all provider choices.
7. It asks Review Concurrency.
8. It presents the Feature identifier.
9. It creates `<BWR_WORKSPACE>`.
10. It writes `GUIDE.md` and `PROGRESS.md`.
11. It starts the muted watchdog.
12. It writes and self-reviews the first Spec.
13. It launches the first Spec Review immediately.

Steps five through eight form one Human setup phase. After setup, the Human can leave the screen.

The Feature identifier does not require a separate question when it is obvious. If its exact BWR workspace already exists, the Orchestrator asks whether to use Recovery or choose another identifier.

## 29. Continuation, succession, and Recovery

### Continuation

The same Orchestrator can receive a later message and continue. It keeps its context. BWR defines no pause or resume protocol.

### Succession

Succession is optional between Lots. The old Orchestrator:

1. completes the current Lot;
2. updates `PROGRESS.md`;
3. asks for the successor provider;
4. stops its watchdog;
5. creates the successor in the same TwiCC project;
6. waits for acceptance.

The successor receives:

- `<BWR_SKILL>`;
- `<BWR_WORKSPACE>`;
- repository path;
- new Lot;
- Current Spec;
- current Git state;
- `PROGRESS.md`;
- `GUIDE.md`;
- provider map as defaults;
- Review Concurrency;
- Gate through `GUIDE.md`.

It does not receive topology, transcripts, old session lists, or watchdog state. It starts its own muted watchdog.

After acceptance, the old Orchestrator remains visible, unmuted, unarchived, and not hidden.

### Recovery

Recovery uses a new independent Orchestrator after loss or abandonment of the old one. It starts only after the Human confirms that the old Orchestrator no longer works. BWR creates no lock.

The Recovery Orchestrator uses an exact BWR workspace path supplied by the Human when it contains `PROGRESS.md` and `GUIDE.md`. Otherwise, it inspects direct children of `<ACTIVE_PROJECT_ROOT>/bwr_workspace/` that contain both files.

It asks the Human to confirm one discovered candidate. When discovery finds none or several, it asks for the exact path. It sets `<BWR_WORKSPACE>` only after that confirmation.

It reads `ADDITIONAL-INSTRUCTIONS.md` when that file exists.

The Recovery Orchestrator reads:

- `PROGRESS.md`;
- `GUIDE.md`;
- Current Spec;
- current plans;
- durable reports named by the current work.

It preserves valid commits. It can reuse a clearly complete report. It ignores incomplete or ambiguous reports.

It creates fresh sessions for unfinished work. It does not depend on old transcripts or topology. It never assigns a report path that an old active session still uses.

When activity is uncertain, it asks the Human to confirm that the old session stopped.

It reuses provider choices, Review Concurrency, Gate, and Git guidance when they remain valid. It asks only for missing or invalid configuration.

## 30. Watchdog

The watchdog is the only BWR runtime script. The implementation reuses the legacy watchdog behavior.

It removes only provider-subagent support. Remove:

- `journal_context` import;
- `PROGRESS` integration;
- `open_provider_subagents`;
- `provider_subagent_blocks`;
- subagent resume wording.

Preserve:

- direct-child discovery through `spawned_by`;
- hidden session inclusion;
- archived session exclusion;
- self exclusion;
- terminal-status exclusion;
- quiet time from `last_updated_at`;
- turn time from `last_state_change_at`;
- live-process information;
- default 40-minute threshold;
- configurable threshold;
- idle sessions never stale;
- blocked sessions eligible for stale reporting;
- existing ordering;
- self-message snapshot;
- loud error reporting.

The watchdog observes and reminds. It does not change workflow state. It does not repair annotations.

It does not detect a specific report-acceptance state. Its reminder says that unfinished work without a blocker should resume. The Orchestrator stops it before succession and final delivery.

## 31. Prompt architecture

`PROMPT-DESIGN.md` owns the authoring rules. This section owns the exact runtime inventory and include graph.

### Runtime inventory

The installed BWR skill uses:

```text
<BWR_SKILL>/
├── SKILL.md
├── prompts/
│   ├── entries/
│   │   ├── orchestrator.md
│   │   ├── watchdog.md
│   │   ├── spec/
│   │   │   ├── enumerator.md
│   │   │   ├── verifier.md
│   │   │   ├── feasibility.md
│   │   │   ├── judge.md
│   │   │   ├── ripple.md
│   │   │   ├── scoped.md
│   │   │   └── fixer.md
│   │   ├── planning/
│   │   │   └── completeness.md
│   │   ├── construction/
│   │   │   ├── implementer.md
│   │   │   ├── design-checker.md
│   │   │   ├── code-checker.md
│   │   │   └── diagnostic.md
│   │   ├── product-review/
│   │   │   ├── unlooked.md
│   │   │   ├── user.md
│   │   │   ├── meaning.md
│   │   │   ├── quality.md
│   │   │   ├── coverage.md
│   │   │   └── finding-verifier.md
│   │   └── amendments/
│   │       ├── reach.md
│   │       ├── fixer.md
│   │       └── consolidation.md
│   ├── common/
│   │   ├── workflow.md
│   │   ├── child.md
│   │   ├── reviewer.md
│   │   ├── product-reviewer.md
│   │   ├── fixer.md
│   │   └── parent.md
│   ├── roles/
│   │   ├── orchestrator.md
│   │   ├── watchdog.md
│   │   ├── spec/
│   │   │   ├── enumerator.md
│   │   │   ├── verifier.md
│   │   │   ├── feasibility.md
│   │   │   ├── judge.md
│   │   │   ├── ripple.md
│   │   │   ├── scoped.md
│   │   │   └── fixer.md
│   │   ├── planning/
│   │   │   └── completeness.md
│   │   ├── construction/
│   │   │   ├── implementer.md
│   │   │   ├── design-checker.md
│   │   │   ├── code-checker.md
│   │   │   └── diagnostic.md
│   │   ├── product-review/
│   │   │   ├── unlooked.md
│   │   │   ├── user.md
│   │   │   ├── meaning.md
│   │   │   ├── quality.md
│   │   │   ├── coverage.md
│   │   │   └── finding-verifier.md
│   │   └── amendments/
│   │       ├── reach.md
│   │       ├── fixer.md
│   │       └── consolidation.md
│   ├── workflows/
│   │   ├── startup/
│   │   │   ├── initial.md
│   │   │   ├── successor.md
│   │   │   └── recovery.md
│   │   ├── spec/
│   │   │   ├── write.md
│   │   │   ├── review-round.md
│   │   │   ├── review.md
│   │   │   ├── correction-loop.md
│   │   │   ├── fix.md
│   │   │   └── human-approval.md
│   │   ├── planning/
│   │   │   ├── write.md
│   │   │   ├── validate-and-commit.md
│   │   │   └── completeness-check.md
│   │   ├── construction/
│   │   │   ├── attempt.md
│   │   │   ├── design.md
│   │   │   ├── design-review-loop.md
│   │   │   ├── design-check.md
│   │   │   ├── implement.md
│   │   │   ├── code-review-loop.md
│   │   │   ├── code-check.md
│   │   │   ├── validate-and-deliver.md
│   │   │   ├── report-failure.md
│   │   │   ├── diagnose-failures.md
│   │   │   ├── diagnostic.md
│   │   │   └── restart-after-failure.md
│   │   ├── product-review/
│   │   │   ├── pass.md
│   │   │   ├── review.md
│   │   │   ├── settle-lens.md
│   │   │   ├── verify-findings.md
│   │   │   └── route-outcome.md
│   │   ├── amendments/
│   │   │   ├── write.md
│   │   │   ├── reach-loop.md
│   │   │   ├── reach-review.md
│   │   │   ├── fix-amendment.md
│   │   │   ├── update-spec.md
│   │   │   ├── consolidation-loop.md
│   │   │   ├── consolidation-check.md
│   │   │   └── finalize.md
│   │   └── delivery/
│   │       ├── close-lot.md
│   │       ├── handoff-successor.md
│   │       └── close-run.md
│   ├── contracts/
│   │   ├── session/
│   │   │   ├── handoff.md
│   │   │   └── orchestrator-handoff.md
│   │   ├── review/
│   │   │   ├── report.md
│   │   │   └── finding.md
│   │   ├── spec/
│   │   │   └── current-spec.md
│   │   ├── amendments/
│   │   │   └── amendment.md
│   │   ├── correction/
│   │   │   └── fixer-report.md
│   │   ├── planning/
│   │   │   ├── plan.md
│   │   │   ├── lot-plan.md
│   │   │   ├── sub-lot-plan.md
│   │   │   └── correction-plan.md
│   │   ├── construction/
│   │   │   ├── task-design.md
│   │   │   ├── implementer-report.md
│   │   │   └── diagnostic-report.md
│   │   ├── product-review/
│   │   │   └── verification-report.md
│   │   └── bwr-workspace/
│   │       ├── guide.md
│   │       └── progress.md
│   └── references/
│       ├── construction/
│       │   └── checker-loop.md
│       ├── review/
│       │   ├── severity.md
│       │   ├── risk-filtering.md
│       │   ├── frozen-subject.md
│       │   └── concurrency.md
│       ├── git/
│       │   └── commit.md
│       ├── sessions/
│       │   ├── annotations.md
│       │   ├── provider-groups.md
│       │   ├── presets.md
│       │   └── watchdog.md
│       └── bwr-workspace/
│           └── reports.md
└── scripts/
    └── watchdog.py
```

BWR creates no empty runtime directories. Every listed file has a defined reader.

`SKILL.md` is a minimal Router. It loads an Initial or Recovery Orchestrator and selects its Startup Workflow. It contains no phase procedure, report format, review rubric, Gate detail, or full transition table.

The Watchdog is a muted `claude_code` session with the `Minimal` preset. `prompts/roles/watchdog.md` contains its self-contained runtime task. Each applicable Startup Workflow owns its launch procedure. `scripts/watchdog.py` is the only BWR script.

### Entry composers and Role prompts

Each session Role has one fixed entry composer under `prompts/entries/`. The composer contains only fixed `@@` markers.

It includes applicable Common prompts and the pure Role prompt. The successor Orchestrator entry also includes its immediate Startup Workflow.

Common prompts and Role prompts contain no active nested `@@` includes. TwiCC can include them through a composer.

An agent can also read them directly. A prompt-composition example can show resolved top-level `@@` syntax.

Workflows, Contracts, and References are on-demand files after startup. An agent reads them when its current Workflow requires them.

The successor entry includes its immediate Startup Workflow. Later routing uses normal read instructions instead of `@@` markers.

The fixed include map is:

| Entry composer | Fixed includes |
|---|---|
| Orchestrator | `workflow.md`, `parent.md`; then `startup/successor.md` |
| Implementer | `workflow.md`, `child.md`, `parent.md` |
| Watchdog | None; its Role prompt is self-contained |
| Product reviewer | `workflow.md`, `child.md`, `reviewer.md`, `product-reviewer.md` |
| Ordinary reviewer or checker | `workflow.md`, `child.md`, `reviewer.md` |
| Spec fixer or Amendment fixer | `workflow.md`, `child.md`, `fixer.md` |
| Every other Role | `workflow.md`, `child.md` |

The Initial, successor, and Recovery Orchestrators use the same pure Role file. No Orchestrator loads `child.md`.

`SKILL.md` selects the Initial or Recovery Startup Workflow. The successor entry includes `startup/successor.md`.

An initial or manually assigned Role reads its applicable Common prompts and pure Role prompt directly. A session created through TwiCC receives the corresponding entry composer.

For example, `prompts/entries/construction/implementer.md` contains:

```md
@@../../common/workflow.md
@@../../common/child.md
@@../../common/parent.md
@@../../roles/construction/implementer.md
```

Only entry composers contain these nested markers. TwiCC resolves each relative path from the composer that contains it.

### Session prompt composition

The parent sends one fixed Role entry, optional Human instructions, then the dynamic assignment. The two entry markers must contain resolved absolute paths before the parent creates the session.

A runtime prompt can look like:

```text
@@/opt/bwr/prompts/entries/construction/implementer.md
@@/srv/project/bwr_workspace/feature-a/ADDITIONAL-INSTRUCTIONS.md

BWR_SKILL: /opt/bwr
BWR_WORKSPACE: /srv/project/bwr_workspace/feature-a
LOT: lot-3
TASK: task-2
ATTEMPT: attempt-1
```

The example paths are illustrative. At runtime, the parent sends the real absolute paths. TwiCC does not substitute `BWR_SKILL`, `BWR_WORKSPACE`, shell variables, or angle-bracket placeholders inside an `@@` marker.

The first marker selects the fixed entry composer. The second marker includes the optional Human instructions. TwiCC removes that marker line when `ADDITIONAL-INSTRUCTIONS.md` does not exist.

The dynamic suffix repeats the resolved `BWR_SKILL` and `BWR_WORKSPACE` values because the session needs them for later on-demand reads. It also supplies the current assignment values and exact artifact paths.

TwiCC expands all markers before the session receives the prompt. Expansion is recursive, with a maximum depth of five levels and a final size limit of 500 KB. BWR keeps its inclusion graph shallow.

Fixed Common content precedes fixed Role content. Optional Human instructions follow the fixed entry. Dynamic values come last. This order supports provider prompt caching.

The parent sends the entry-composer marker without reading, copying, or repeating the fixed content in its own context.

Later Workflows, Contracts, and References use explicit on-demand reads for their dependencies. They do not load dependencies through `@@`.

### Shared Contract ownership

`prompts/contracts/review/report.md` owns the common `CLEAN | FINDINGS | BLOCKED` Review Report. Spec, Reach, Consolidation, Plan completeness, Design, Code, and Product reviews use it. BWR creates no domain copy of that Contract.

`prompts/contracts/review/finding.md` owns the public Finding shape. `prompts/references/review/risk-filtering.md` owns Probability, admission, and filtered private observations. Only an applicable Reviewer loads it. A Finding verifier never loads it.

One `prompts/contracts/session/handoff.md` owns the common Report and return-message interface. Specialized Contracts extend the useful Report content without copying the common Handoff format.

One Implementer Report covers one complete Attempt. The same Contract covers `READY`, `BLOCKED`, and `FAILED`. BWR has no separate failure Report Contract.

`prompts/contracts/spec/current-spec.md` also validates an Updated Spec. BWR creates no duplicate Updated Spec Contract.

## 32. Self-review

Self-review uses the same author and current complete subject. It creates no new session and no report.

The author checks the full subject after its last edit. It corrects findings and repeats until internally clean. Self-review applies to:

- Orchestrator Spec and plans;
- Spec fixer changes;
- Amendment fixer changes;
- Implementer Design;
- Implementer code and tests.

A simple handoff declaration is sufficient. BWR requires no proof token, checksum, or minimum pass count. Self-review never replaces independent review.

## 33. Loop termination

BWR sets no maximum Round, Pass, Correction Round, or Attempt count. The loop ends only with:

- a clean result;
- a necessary Human decision;
- a real blocker;
- a diagnostic route to an earlier stage.

Numbers provide identity only. Difficulty and elapsed time do not create failure.

## 34. Delivery and closure

BWR delivers only when:

- all Lots, sub-lots, and corrections are complete;
- the final full Gate passes;
- the final full Product Review is clean;
- no confirmed finding remains;
- no product decision remains;
- no blocker remains;
- the Current Spec contains all accepted Amendments;
- no tracked BWR work remains uncommitted.

The Orchestrator then:

1. updates the final result in `PROGRESS.md`;
2. records Current Spec, commits, Gate, final Pass, and accepted limits;
3. stops the watchdog;
4. retires remaining non-Orchestrator children;
5. reports the result to the Human;
6. asks whether to keep or delete the BWR workspace.

Keeping the BWR workspace is the recommended choice. BWR never deletes it automatically. BWR does not merge, push, delete branches, or remove worktrees automatically.

## 35. Deliberate omissions

BWR deliberately has no:

- `progress.py`;
- Gate runner actor;
- provider-subagent support;
- checksum or inode evidence;
- special Git refs;
- automatic worktree creation;
- manifest or lifecycle database;
- report parser;
- report compaction;
- automatic lock;
- pause or stop protocol;
- arbitrary loop limit;
- runtime script other than the watchdog.

These omissions are product decisions. They keep BWR understandable, inspectable, and repairable by normal agents.
