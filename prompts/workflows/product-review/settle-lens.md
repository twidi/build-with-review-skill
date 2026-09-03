# Settle one Product Review lens

Execute this Workflow when a Product reviewer returns for one lens in the current Pass.

The complete lens chain keeps one Review Concurrency place until this Workflow settles it.

## Route the Reviewer Handoff

Require the Handoff summary to start with the Reviewer Report verdict.

For `CLEAN`, do not read the Reviewer Report. Retire the reviewer with `bwr.status: done`.

Record the lens as settled with no confirmed Finding. Its review place is now free.

For `FINDINGS`, do not read the Reviewer Report. Keep the reviewer in `idle` and start one Finding verifier.

For `BLOCKED`, read the available Reviewer Report. Resolve the blocker and follow up with the same reviewer.

For `FAILED`, read the available Reviewer Report and retire the reviewer with `bwr.status: failed`.

If the unchanged lens assignment remains executable, start a replacement reviewer with the same Report path.

Otherwise, present the exact assignment failure to the Human.

## Start the Finding verifier

Use the `Finding verifiers` provider group and the `ReviewerLight` preset.

Use this Report path:

```text
<BWR_WORKSPACE>/reports/product-review/<LOT>/<PASS>/verifier-<lens>.md
```

Set these annotations:

```text
bwr.role: finding-verifier
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: product-review
bwr.lot: <LOT>
bwr.pass: <PASS>
bwr.mandate: <lens>
```

Provide the frozen Pass inputs, exact Reviewer Report path, lens name, and assigned Verification Report path.

Update `PROGRESS.md` with both Report paths and the active lens-chain state.

## Receive the verifier

Read the complete Verification Report for every Handoff.

For `BLOCKED`, resolve the named blocker and follow up with the same verifier.

For `FAILED`, retire the verifier with `bwr.status: failed`.

If the unchanged verification assignment remains executable, start a replacement verifier with the same Verification Report path.

Otherwise, present the exact assignment failure to the Human.

For `READY`, inspect the verdicts recorded for the source Findings.

If one or more verdicts are `UNVERIFIABLE`, keep both sessions and Report paths for the same lens assignment.

Send the Verification Report path to the same reviewer. Ask it to revise its complete Reviewer Report for every `UNVERIFIABLE` result.

After the reviewer returns an accepted revised Report, send that same Reviewer Report path to the same verifier.

The verifier overwrites its complete Verification Report. Repeat this alternation while an `UNVERIFIABLE` result remains.

## Close the lens chain

When every verification verdict is `CONFIRMED` or `DISPROVED`, accept the Verification Report.

Retire the verifier and reviewer with `bwr.status: done`. This frees the lens-chain review place.

Record in `PROGRESS.md`:

- the settled lens;
- the Reviewer and Verification Report paths;
- every confirmed source Finding identifier;
- the confirmed and disproved counts.

## Exit

- Reviewer `CLEAN` → return to the current Pass with one free review place.
- Verification settled → return to the current Pass with one free review place.
- `UNVERIFIABLE` remains → remain in this Workflow with the same reviewer and verifier.
- Resolvable assignment blocker → remain in this Workflow.
- Frozen subject changed → return to the current Pass Workflow.
