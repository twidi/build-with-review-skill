# Route a Product Review outcome

Execute this Workflow after every lens in one frozen Pass has settled.

## Build the confirmed source set

Use the settled lens records in `PROGRESS.md`.

Read each Verification Report that contains a `CONFIRMED` verdict.

Read the corresponding Reviewer Reports. Keep every confirmed Finding identity with its verification path.

Group duplicate Findings into one correction obligation when they describe the same required outcome.

Split a compound Finding into traceable obligations when its corrections have different outcomes.

Preserve every source `<reviewer-report-path>#F<number>` in the resulting obligations.

## Route a clean Pass

When no confirmed Finding remains, record the Pass as `CLEAN` in `PROGRESS.md`.

Execute the Lot closure Workflow.

## Resolve confirmed decisions

Before correction planning, resolve every confirmed `DECISION` through the Orchestrator Human-decision procedure.

Present the complete verified context and options. The Human must not need to read either source Report.

Record each answer and its source Finding identities in `PROGRESS.md`.

Execute one Amendment Workflow for each coherent decision set.

Keep all confirmed ordinary Findings pending while the Amendments run.

After every required Amendment becomes part of the Current Spec, continue this Workflow with the Updated Spec and accepted Amendment paths.

Include the implementation obligations created by those Amendments in the complete correction set.

## Select one correction route

Route the complete remaining correction obligation set together.

Use a Correction Round when the work is bounded and local. Keep the existing architecture, responsibilities, and small Task graph.

Use a Sub-lot when the work changes structural responsibility, decomposition, important interfaces, migration, or broad coordination.

When either route could apply to different obligations, use one Sub-lot for the complete set.

Finding count and Severity do not select the route.

## Start planning

Assign the next sequential Correction Round or Sub-lot identifier.

Update `PROGRESS.md` with:

- the completed Pass and frozen commit;
- the selected correction route and identifier;
- every correction obligation and source Finding identity;
- every Verification Report path;
- every accepted Amendment path.

Provide those inputs, the Current Spec, the parent Plan, and the reviewed commit to the Plan writing Workflow.

## Exit

- No confirmed Finding → execute `<BWR_SKILL>/prompts/workflows/delivery/close-lot.md`.
- Confirmed `DECISION` remains → execute `<BWR_SKILL>/prompts/workflows/amendments/write.md`.
- Correction Round selected → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for a Correction Round Plan.
- Sub-lot selected → execute `<BWR_SKILL>/prompts/workflows/planning/write.md` for a Sub-lot Plan.
