# Construction Diagnostic Report Contract

A Construction Diagnostic Report compares repeated comparable failed Attempts and identifies the required restart point.

It contains:

- every input Implementer Report path;
- the relevant Plan, Task, Design, and commit identifiers;
- the material similarities and differences between Attempts;
- the evidence from each failure;
- one cause classification;
- the required restart point and reason.

Use one classification:

- `IMPLEMENTATION`: restart with a new implementation Attempt;
- `DESIGN`: replace the Task Design before implementation;
- `EARLIER_TASK`: correct an already completed Task first;
- `PLAN`: revise the active Plan before construction continues;
- `BLOCKED`: indispensable external information or action is missing.

For `BLOCKED`, state the exact missing information or action.

The restart recommendation must identify the concrete Plan, Task, or Attempt boundary.

Support the classification with observable evidence. Separate confirmed facts from diagnostic inference.
