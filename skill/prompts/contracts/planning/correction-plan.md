# Correction Round Plan Contract

A Correction Round Plan follows the common Plan Contract.

Its identifier is `correction-<number>`. The number is sequential within the root Lot.

Keep the root Lot and Correction Round identifiers separate. For example, use `lot-1` with `correction-2`.

It adds:

- the exact Lot and Correction Round identifiers;
- the reviewed commit;
- the parent Plan path;
- every confirmed source Finding;
- every corresponding verification Report;
- every accepted Amendment that creates a correction obligation in this Plan;
- the resulting correction obligations;
- the obligations that the correction must preserve.

Identify each source Finding with `<reviewer-report-path>#F<number>`.

Associate each source Finding with its verification Report.

Associate each Amendment-created obligation with its Amendment path and resolved source Finding identities.

The combined Tasks must resolve the complete correction obligation set.

Each correction obligation must appear in at least one Task `Sources` field.

The Plan must state which existing obligations each Task preserves while making its correction.
