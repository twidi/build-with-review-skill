# Filling a completion block

Your block's items and their order are fixed by your own `*-completion.md`. These rules apply to every block in this loop.

For a discovery reviewer that reads `review-risk.md`, keep coverage and results separate:

- A checked-surface datum counts or names every unit you actually examined.
- An adverse-result datum counts or names only admitted findings. A risk-filtered
  observation is not a public candidate and changes no public number, name, or result.
- For coverage evidence, never encode a pass/fail fraction that can reveal a filtered
  observation. Record the checked set and the admitted finding identities instead.

- **Every line carries a NUMBER or a NAME.** `[x] anchors — 47 in slice, 41 verified, 6 deferred` is auditable; a bare tick is not. The datum is what makes a spot-check possible, and a spot-check is the only defence against a fabricated line.
- `[x]` = settled, with its evidence, or genuinely not applicable — then write `n/a: <why>`.
- `[ ]` = not settled, and the line then says `NOT DONE: <why>`.
- **The box is a claim you make, not a character you copy.** A returned box left unticked with no `NOT DONE` is this block's most likely failure — a template pasted through rather than a report written — and the controller will send it back.
- **A zero is a claim**, not a silence: it says you ran that item and it produced nothing.
- **One line per item, always**, even when the evidence is a list: the line carries the aggregate, the list goes in the report or the log. Twenty-one lines, one per identifier, break the controller's line-by-line check and bloat every ping.
- **A line that does not apply is `n/a`, never omitted** — an absent line and a forgotten one look identical.
- `NOT DONE` exists so an agent that ran out of room, or was blocked, can say so instead of quietly dropping the line. A round carrying one is honest, not failed.
- **Keep the items and their order exactly as your file gives them:** the controller compares what you return against that file, term by term.

The block opens your report, above everything else, and you paste it verbatim into your `parent` message. It has one consumer beyond the controller: the next agent that reads your report assumes whatever is absent from your findings is clean — which is exactly wrong under a `NOT DONE`. A `NOT DONE` category is unreviewed, never clean.
