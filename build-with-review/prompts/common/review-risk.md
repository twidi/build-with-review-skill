# Risk admission for discovery reviews

This file applies only when the controller or implementer gives it to a severity-bearing
discovery reviewer: every SPEC mandate, every PRODUCT REVIEW lens, and the CONSTRUCTION
code checker. It does not apply to CONSTRUCTION completeness, the design checker,
finding verifiers, diagnostics, consolidation, gate work, or amendment reach.

## Impact

Classify the consequence if the scenario occurs. Do not include probability in the
impact.

| Impact | Meaning |
|---|---|
| **CRITICAL** | Data loss, destructive action, serious security failure, silent wrong delivery, or loss of an authoritative decision. |
| **IMPORTANT** | Incorrect behaviour, blocked work, broken recovery, or a false result that remains detectable and recoverable. |
| **MINOR** | Limited friction, clarity, diagnostics, or maintainability without a credible wrong result. |

## Probability

Classify the probability of the finding's concrete scenario in this project's real use
and threat model. Do not classify how confident you are that the finding is correct.

| Probability | Meaning |
|---|---|
| **FREQUENT** | Expected repeatedly on a normal path. |
| **PLAUSIBLE** | Can result from ordinary use, common mistakes, normal failures, or routine configuration. |
| **RARE** | Requires an unusual but supported environment, timing, or combination of conditions. |
| **EXCEPTIONAL** | Requires deliberate internal manipulation, unsupported corruption, or several independent exceptional conditions. |

An adversarial action is not automatically exceptional. It is plausible when the
product normally exposes that action to an untrusted actor.

## Admission

This table applies only to a newly discovered candidate. Apply it after that candidate
passes your existing relevance and proof rules.

A finding already admitted is not admitted again. A verification pass preserves its
identity and records whether it is fixed or still open without using this table. New
candidates discovered during verification still use this admission table normally.

| Impact / Probability | FREQUENT | PLAUSIBLE | RARE | EXCEPTIONAL |
|---|---:|---:|---:|---:|
| **CRITICAL** | report | report | report | risk-filter |
| **IMPORTANT** | report | report | risk-filter | risk-filter |
| **MINOR** | report | risk-filter | risk-filter | risk-filter |

`report` means the finding goes into your normal report. `risk-filter` means the
observation stops being a review candidate. Only its private history entry remains. It
does not appear in your report, completion block, counts, final message, or any workflow
route.

The CONSTRUCTION code checker does not own a `DECISION` output route. It applies this
table to each concrete new observation. `report` means that the observation enters its
strict JSON result with its consequence impact. The implementer later owns any
classification as plan ambiguity, `Blocked`, or unsettled product behaviour.

For SPEC mandates and PRODUCT REVIEW lenses, a `DECISION` uses the same table. Assign it
the impact of leaving that product question unsettled, then combine that impact with its
probability. This impact stays internal to your admission decision. When reported, the
public finding keeps the existing `DECISION` format unchanged.

For those SPEC and PRODUCT REVIEW roles, every shared rule that reports a `DECISION`,
pings `parent`, or stops work applies only after this table returns `report`. When the
table returns `risk-filter`, record the question only in your private history.
Do not report it, ping `parent`, or stop.

## Your private risk-filtered history

Your parent gives you one risk-filtered history path and one occurrence label. The same
mandate uses that path throughout its review scope. This file is private working memory,
not workflow authority.

For a CONSTRUCTION code checker, every logical round and physical regeneration in one
attempt uses `reports/construction/<lot>/task-<N>-attempt-<K>-code-risk-filtered.md`.
Use `Code checker round <R>` as the occurrence label. A new attempt uses a new path.

At the start of your review, read the file when it exists. A missing, partial, or lost
file never blocks the review. No controller, fixer, verifier, other mandate, or
`progress.py` consumer reads it.

When you risk-filter a candidate that the file does not already describe, append this
minimal entry:

```text
## <occurrence label>

- <IMPACT> × <PROBABILITY> — <the candidate, stated precisely enough to recognise again>
  Probability basis: <the conditions that justify this probability>
```

For a filtered product question, use
`DECISION (impact <IMPACT>) × <PROBABILITY>` in the first line. Replace every placeholder
with the actual value.

The file is append-only history. Never remove or rewrite an earlier entry. If the same
candidate remains below the admission threshold, do not append it again. If you now
classify it above the threshold, report the current finding normally. The old entry
remains private history. The public finding must never mention the earlier private
occurrence or its filtering basis.

Do not report the history path, its count, or its contents to anyone. Its loss is
accepted.
