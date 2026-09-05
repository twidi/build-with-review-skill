# Task Design Contract

A Task Design defines the complete implementation approach for one Task and Attempt.

Write it inside that Task's tracked `Design` section.

Use flexible headings. Include:

- the selected approach;
- ordered implementation steps;
- affected areas or files;
- interfaces, formats, state, and events;
- material alternatives and selection reasons;
- the behaviors that implementation must prove.

Each step states:

- the affected area;
- the intended change;
- the expected result.

The Design can define concrete signatures, formats, states, and events.

It describes implementation structure without containing the full implementation code.

Every product behavior must trace to the Task, parent Plan, or Current Spec.

When those sources do not resolve a required product choice, identify that decision instead of selecting new behavior.

Use the smallest complete mechanism that satisfies the authoritative obligations and fits the existing architecture.

`Smallest` means the least added mechanism that fully satisfies the contract. It does not mean the shortest patch.

Trace each new state, abstraction, persistent field, version, lock, retry, synchronization mechanism, service, or compatibility layer to an exact obligation or admitted scenario. Explain why a simpler solution is insufficient.

Implementation cost alone does not create a product decision.
