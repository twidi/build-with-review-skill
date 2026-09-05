# Reuse and abstraction

Use this Reference when designing or reviewing a material mechanism.

Perform a targeted search for an equivalent repository mechanism or suitable dependency. Search nearby code, modules with the same concept, shared services, utilities, validation, storage, and installed dependencies.

For a standard non-trivial capability, also examine suitable established dependencies available to the project.

Compare candidates by:

- meaning and authoritative rules;
- ownership and lifecycle;
- failure and state behavior;
- expected future evolution.

Reuse a mechanism when these semantics match.

Consider a suitable dependency when the capability is standard and non-trivial. Compare its project fit and maintenance burden with custom code.

Keep separate implementations when their meanings or expected evolution differ. Similar code shape alone does not justify reuse.

Special modes, unrelated branches, or case-specific flags indicate a wrong abstraction. A small duplication can be the smaller complete mechanism.

Record only material selections among credible reuse, dependency, and new-implementation alternatives. Do not produce a search log.

A review Finding cites the existing alternative, establishes the semantic match, and states a concrete maintenance or correctness consequence.
