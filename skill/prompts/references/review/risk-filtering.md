# Risk filtering

This Reference is only for a reviewer whose current Workflow uses risk filtering.

Probability describes the frequency of one concrete scenario. It never describes reviewer confidence.

Use one value:

- `FREQUENT`: repeated occurrence on a normal path;
- `PLAUSIBLE`: ordinary use, common mistakes, common failures, or common configuration;
- `RARE`: an unusual but supported environment, timing, or combination;
- `EXCEPTIONAL`: deliberate internal manipulation, unsupported corruption, or several independent exceptional conditions.

An adversarial action is not automatically `EXCEPTIONAL`.

## Admission matrix

Classify Severity independently. Probability never lowers Severity.

| Severity / Probability | FREQUENT | PLAUSIBLE | RARE | EXCEPTIONAL |
|---|---:|---:|---:|---:|
| CRITICAL | Report | Report | Report | Filter |
| IMPORTANT | Report | Report | Filter | Filter |
| MINOR | Report | Filter | Filter | Filter |

An admitted public Finding contains Severity only. It never contains Probability.

## Cases without filtering

Always report a direct violation of the Current Spec or Task contract.

For Design, Code, and Product review, apply Probability only to a new inferred risk beyond an explicit contract.

The Spec Feasibility reviewer reports every infeasible written contract.

The Product `coverage` reviewer reports every concrete missing obligation.

Plan completeness and Consolidation do not use Probability.

A Finding verifier never receives, uses, or discusses Probability.

## Private history

The current Workflow assigns one private-history path for each stable reviewer role and scope.

If the file exists, read it before reviewing. A missing file never blocks work.

Record each filtered candidate with this shape:

```text
## <occurrence>

- <SEVERITY> × <PROBABILITY> — <candidate>
  Probability basis: <conditions>
```

Do not add a recurring candidate twice.

If a later review admits it, create a normal public Finding. Keep the old private entry.

The private history never enters a Review Report or Handoff. Do not commit it.
