# Amendment Contract

An Amendment records one verified Human product decision after approval of the initial Current Spec.

Each Amendment has one sequential run-wide number.

It contains:

- a descriptive title;
- the exact Human decision;
- the reason for the decision;
- every required product behavior change;
- every existing behavior that must remain preserved;
- the origin phase and Lot;
- applicable source Report paths and Finding identifiers.

One Amendment covers one coherent decision set.

Its changes stay at product level. They describe observable behavior, states, transitions, errors, recovery, and constraints as applicable.

The accepted Amendment must contain enough information to produce the complete Updated Spec without another product choice.

Finding sources use `<report-path>#F<number>`.
