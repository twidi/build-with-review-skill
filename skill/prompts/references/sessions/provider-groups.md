# Provider groups

Provider groups let one Human choice supply the provider for related session roles.

Use these groups:

| Provider group | Session roles |
|---|---|
| Document reviewers | Spec reviewers, Reach reviewers, Plan completeness checker, Consolidation checker |
| Fixers | Spec fixer, Amendment fixer |
| Implementer | Implementer |
| Implementer checkers | Design checker, Code checker, Construction diagnostic |
| Product reviewers | Product reviewers for every lens |
| Finding verifiers | Finding verifier |

The current provider map lives in `PROGRESS.md`.

When a Role or Workflow names a provider group, use that group's current provider.

The Human can change a group during the run. The Orchestrator records the replacement in `PROGRESS.md`.
