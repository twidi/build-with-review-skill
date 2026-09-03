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
