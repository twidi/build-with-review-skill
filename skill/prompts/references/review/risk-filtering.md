# Risk filtering

Use this Reference when the current Role or Workflow selects risk filtering.

Probability measures the complete concrete scenario across real opportunities relevant to the assigned role. It measures exposure, not reviewer confidence.

## Build the scenario

Before classifying Probability:

1. State the complete minimal scenario.
2. List every necessary condition.
3. Identify dependent causal steps.
4. Identify independent coincidences.
5. Evaluate the complete chain.

Evidence must establish that the scenario belongs to the supported domain. It must also establish that every necessary condition is reachable.

The complete scenario cannot be more frequent than its least-frequent necessary condition. Reduce it further when independent conditions must coincide.

Keep dependent causal steps in one chain. Do not count them as independent coincidences.

## Probability values

Use one value:

- `FREQUENT`: the scenario repeats on a normal path without an unusual precondition;
- `PLAUSIBLE`: ordinary use reaches it without special coordination, precise timing, internal manipulation, or multiple independent events;
- `RARE`: a supported scenario needs one unusual but credible condition, without precise timing or multiple independent coincidences;
- `EXCEPTIONAL`: the scenario needs one exceptional condition, multiple independent unusual conditions, deliberate coordination, precise timing, internal manipulation, unsupported corruption, or a speculative chain without real exposure evidence.

Classify adversarial action from its actual exposure and preconditions.

## Evidence burden

Choose a more frequent class only with positive evidence. When evidence cannot distinguish two classes, choose the less frequent class.

Useful evidence includes:

- a supported product flow;
- a reproducible sequence without artificial coordination;
- a durable reachable code state;
- a supported configuration;
- documented behavior;
- a normal platform failure;
- established project use.

Language, scheduler, or network possibility alone does not establish real exposure.

## Admission matrix

Classify Severity independently. Probability never changes Severity.

| Severity / Probability | FREQUENT | PLAUSIBLE | RARE | EXCEPTIONAL |
|---|---:|---:|---:|---:|
| CRITICAL | Report | Report | Report | Filter |
| IMPORTANT | Report | Report | Filter | Filter |
| MINOR | Report | Filter | Filter | Filter |

Keep Probability private. An admitted public Finding contains Severity only.

## Direct contract violations

Bypass Probability only when all these statements are true:

1. The Finding cites the exact authoritative obligation.
2. The complete scenario is inside that obligation's stated scope.
3. The contradiction needs no added or implicit guarantee.

Apply the admission matrix to every added or inferred guarantee.

Example: an obligation that saving updates the displayed item does not promise atomic live synchronization between browser tabs.

## Private history

The current Workflow assigns one private-history path for each stable reviewer role and scope.

Read an existing file before reviewing. A missing file permits the review to continue.

Record each filtered candidate with this shape:

```text
## <occurrence>

- <SEVERITY> × <PROBABILITY> — <candidate>
  Scenario: <complete minimal scenario>
  Probability basis: <conditions and evidence>
```

Keep one entry for the same candidate, conditions, and evidence. Reconsider it only after a material change to its evidence, conditions, authoritative contract, or observed behavior.

When later evidence admits it, create a normal public Finding. Keep the private entry.

The private history stays outside the Review Report and Handoff. Keep it uncommitted.
