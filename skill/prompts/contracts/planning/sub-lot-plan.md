# Sub-lot Plan Contract

A Sub-lot Plan follows the common Plan Contract.

It adds:

- the exact `lot-<parent>.<number>` identifier;
- the reviewed commit;
- the parent Plan path;
- every source Finding;
- the parent, Current Spec, and earlier correction obligations that must remain preserved.

Identify each source Finding with `<reviewer-report-path>#F<number>`.

The combined Tasks must resolve the complete source Finding set.

Each correction obligation must appear in at least one Task `Sources` field.

The Plan must state which inherited obligations each Task preserves while making its correction.
