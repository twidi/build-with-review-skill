# Write the initial Spec

Execute this Workflow to create or complete the first candidate Current Spec.

## Load

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/spec/current-spec.md`.

Read the current Human request, applicable project instructions, and relevant repository evidence.

## Write

Write the complete candidate Spec at the path recorded in `PROGRESS.md`.

Derive product behavior from authoritative Human decisions and verified project facts.

When a required product choice remains unresolved, present it to the Human through the Orchestrator decision procedure.

## Self-review

Review the complete candidate against:

- the Human request and decisions;
- the Current Spec Contract;
- factual repository evidence;
- internal consistency;
- every Lot boundary and dependency.

Correct every issue found.

Repeat the complete self-review after each correction until it finds no remaining issue.

Update `PROGRESS.md` with the candidate Spec path and current Spec phase.

## Exit

- Internally clean candidate → read and execute `<BWR_SKILL>/prompts/workflows/spec/review-round.md`.
- Required Human decision → remain in this Workflow and continue after the answer.
- External blocker → record it in `PROGRESS.md` and present it to the Human.
