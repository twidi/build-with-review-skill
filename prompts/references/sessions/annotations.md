# Session annotations

This Reference is for Parents that create and manage sessions. Child sessions do not read it.

## Purpose

Annotations make the live TwiCC topology readable.

They describe session identity and current state.

They never prove a Workflow transition or replace an authoritative artifact.

## Ownership

The parent sets the complete applicable annotation set when it creates a child.

The child can later change only its own `bwr.status`.

The parent changes `bwr.status` for follow-up, final acceptance, cancellation, or supersession.

The parent can correct a stale `bwr.status` only after observing the real session state.

Do not clear annotations when retiring a session.

## Status

Use this mapping:

| Event | Actor | `bwr.status` |
|---|---|---|
| Session creation | Parent | `working` |
| Follow-up starts | Parent | `working` |
| `READY` Handoff sent | Child | `idle` |
| `BLOCKED` Handoff sent | Child | `blocked` |
| `FAILED` Handoff sent | Child | `failed` |
| `READY` receives final acceptance | Parent | `done` |
| Human cancels the assignment | Parent | `cancelled` |
| A changed subject replaces the assignment | Parent | `superseded` |

`idle` means that no work is pending, but the same assignment can receive a follow-up.

`blocked` means that specified external information or action is required before work can resume.

Terminal values are `done`, `failed`, `cancelled`, and `superseded`.

BWR has no `paused` or `stopped` status.

## Common keys

Every session covered by this Reference receives:

- `bwr.role`: the exact value declared by the current Role or Workflow;
- `bwr.status`: one value from the status mapping;
- `bwr.feature`: the complete stable Feature identifier.

Do not add an inapplicable key. Do not use `null`, `none`, an empty string, or `0` as a placeholder.

## Assignment keys

Add only the keys that identify the session's actual assignment.

| Key | Value |
|---|---|
| `bwr.phase` | `spec`, `planning`, `construction`, `product-review`, or `amendment` |
| `bwr.lot` | The exact Lot identifier, including the `lot-` prefix |
| `bwr.task` | The exact Task identifier |
| `bwr.attempt` | The exact Attempt identifier |
| `bwr.round` | The exact Round identifier |
| `bwr.pass` | The exact Pass identifier |
| `bwr.mandate` | The assigned stable lowercase mandate |
| `bwr.correction` | The exact Correction Round identifier |

Keep identifiers as strings. For example, use `lot-1.10`, never `1.10`.

## Assignment-specific values

The current Role or Workflow defines:

- the exact `bwr.role` value;
- the applicable assignment keys;
- the exact values for those keys.

Use only that declared set. Do not infer keys from another Role or copy a broader example.
