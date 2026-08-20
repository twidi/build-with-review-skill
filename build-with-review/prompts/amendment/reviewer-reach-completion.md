# Completion block — reach sweep

**6 items.** Your report opens with this block, above the hop counts and the findings, and
you paste it verbatim into your `parent` message. How to fill it: `completion-rules.md`.


    COMPLETION (6 items)
    - [ ] hops walked — <N> hops, last one returning <M> new places
    - [ ] places found — <N> total: <N> kept, <N> moved, <N> removed, <N> DECISION
    - [ ] phrasings swept for every changed thing — active <B1/D1, R2>; <N> unique terms or hits
    - [ ] places reached by purpose and not by name — <N>
    - [ ] tests asserting any changed behaviour — <N> found, <N> still asserting it after the amendment
    - [ ] frontier — closed at hop <N>

## For this mandate

- **`places reached by purpose and not by name` is the line that matters.** A zero says
  every dependency named the thing being changed — possible, and rare. It is where the
  defect lives, so a zero is a claim you are making, not a silence.
- **`frontier` is never a judgement from depth or size.** A zero-new-place hop closes it.
  Otherwise, continue while the next finite frontier can be enumerated from the available
  durable inputs. `NOT CLOSED` is valid only when those inputs cannot enumerate the next
  hop.
- `tests asserting any changed behaviour` is `n/a` only when the change set touches nothing
  the suite exercises. Write `n/a; suites read: <exact suites>`.
- For an open frontier, write one of these exact forms on the frontier line:
  `NOT CLOSED: <N, N, N> new places by hop; next hop cannot be enumerated — missing durable input: <exact input and why it is absent>` or
  `NOT CLOSED: <N, N, N> new places by hop; next hop cannot be enumerated — unbounded input: <exact input and why it has no finite frontier>`.
  Positive counts alone are not `NOT CLOSED`. A closed frontier uses the form above.
- Replace every angle-bracket template with concrete evidence. The receipt rejects an
  untouched or partly filled template.
