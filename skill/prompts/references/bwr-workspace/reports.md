# Report paths

This Reference is for Parents that assign Reports.

Store every Report under `<BWR_WORKSPACE>/reports/`.

Create and assign its absolute path before creating the child.

One logical assignment has one Report path and one writer.

A new logical assignment gets a new path.

A follow-up to the same assignment keeps the same path. The child replaces the Report with its current complete result.

Use the exact path pattern declared by the current Workflow. Do not invent another pattern.

Use only the directories needed to identify the assignment and prevent collisions.

Do not add a session identifier, checksum, inode, generation identifier, `v2`, or `v3`.

Reports remain available for the complete BWR run. Do not commit them to the product repository.
