# Sub-lot Plan Contract

A Sub-lot Plan follows the common Plan Contract.

Create its identifier by appending `.<next sequential number>` to the complete root Lot identifier.

For example, `lot-1` produces `lot-1.1` and later `lot-1.10`. Do not add another `lot-` prefix.

It adds:

- the exact Sub-lot identifier;
- the reviewed commit;
- the parent Plan path;
- every confirmed source Finding;
- every corresponding verification Report;
- every accepted Amendment that creates a correction obligation in this Plan;
- the resulting correction obligations;
- the parent, Current Spec, and earlier correction obligations that must remain preserved.

Identify each source Finding with `<reviewer-report-path>#F<number>`.

Associate each source Finding with its verification Report.

Associate each Amendment-created obligation with its Amendment path and resolved source Finding identities.

The combined Tasks must resolve the complete correction obligation set.

Each correction obligation must appear in at least one Task `Sources` field.

The Plan must state which inherited obligations each Task preserves while making its correction.
