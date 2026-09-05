# Route a Product Review outcome

Execute this Workflow after every lens in one frozen Pass has settled.

## Build the confirmed source set

Use the settled lens records in `PROGRESS.md`.

When those records contain a confirmed Finding:

Read once; reread as needed:

- `<BWR_SKILL>/prompts/contracts/review/report.md`;
- `<BWR_SKILL>/prompts/contracts/review/finding.md`;
- `<BWR_SKILL>/prompts/contracts/product-review/verification-report.md`.

Read each Verification Report that contains a `CONFIRMED` verdict.

Read the corresponding Reviewer Reports. Keep every confirmed Finding identity with its verification path.

Keep confirmed ordinary Findings and confirmed `DECISION` Findings as separate sets.

When accepted Amendment paths return to this Workflow, read each Amendment. Match its exact source Finding identities to the confirmed `DECISION` set.

Mark each matched `DECISION` as resolved by that Amendment. Keep the Finding-to-Amendment mapping in `PROGRESS.md`.

Do not start another Amendment for a resolved source Finding identity.

Group duplicate Findings into one correction obligation when they describe the same required outcome.

Split a compound Finding into traceable obligations when its corrections have different outcomes.

Preserve every source `<reviewer-report-path>#F<number>` in the resulting obligations.

## Route a clean Pass

When the source set contains no confirmed Finding, record the Pass as `CLEAN` in `PROGRESS.md`.

Execute the Lot closure Workflow.

## Resolve confirmed decisions

Every pending confirmed `DECISION` has passed Finding verification as a Human product decision.

Present the complete verified context and options. The Human must not need to read either source Report.

Record each answer and its source Finding identities in `PROGRESS.md`.

Execute one Amendment Workflow for each coherent decision set.

Keep all confirmed ordinary Findings pending while the Amendments run.

After every required Amendment becomes part of the Current Spec, continue this Workflow with the Updated Spec and accepted Amendment paths.

Add the implementation obligations created by those Amendments to the complete correction set. Preserve their Amendment paths and source Finding identities.

When the accepted Amendments create no implementation obligation and no confirmed ordinary Finding remains, record the old Pass as historical. Start a fresh complete Pass against the Updated Spec and current commit.

## Select one correction route

Route the complete remaining correction obligation set together.

Use a Correction Round when the work is bounded and local. Keep the existing architecture, responsibilities, and small Task graph.

Use a Sub-lot when the work changes structural responsibility, decomposition, important interfaces, migration, or broad coordination.

When either route could apply to different obligations, use one Sub-lot for the complete set.

Finding count and Severity do not select the route.

## Start planning

Assign the next sequential identifier for the selected route.

Use `correction-<number>` for a Correction Round. Its number is sequential within the root Lot.

Use the Sub-lot identifier format from the Sub-lot Plan Contract.

For a Correction Round, replace your complete applicable annotation set with:

```text
bwr.role: orchestrator
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: planning
bwr.lot: <root LOT>
bwr.correction: <CORRECTION>
```

For a Sub-lot, replace your complete applicable annotation set with:

```text
bwr.role: orchestrator
bwr.status: working
bwr.feature: <FEATURE>
bwr.phase: planning
bwr.lot: <SUB_LOT>
```

Update `PROGRESS.md` with:

- the completed Pass and frozen commit;
- the selected correction route and identifier;
- every correction obligation and source Finding identity;
- every Verification Report path;
- every accepted Amendment path.

Provide those inputs, the Current Spec, the parent Plan, and the reviewed commit to the Plan writing Workflow.

## Exit

- No confirmed Finding → execute `<BWR_SKILL>/prompts/workflows/delivery/close-lot.md`.
- Pending confirmed `DECISION` remains → execute `<BWR_SKILL>/prompts/workflows/amendments/write.md`.
- Every `DECISION` resolved and no correction obligation remains → execute `<BWR_SKILL>/prompts/workflows/product-review/pass.md` with the Updated Spec.
- Correction Round selected → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for a Correction Round Plan.
- Sub-lot selected → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for a Sub-lot Plan.
