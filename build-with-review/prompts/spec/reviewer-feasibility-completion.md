# Completion block — feasibility reviewer

**8 items.** Your report opens with this block, above the findings, and you paste it verbatim into your `parent` message. How to fill it: `completion-rules.md`.


    COMPLETION (8 items)
    - [ ] contracts levelled — N obvious, N needs work, N very complex, N infeasible
    - [ ] platform claims — N verified against the real runtime, N assumed, N false
    - [ ] how each was verified — run, probed, or implementation read
    - [ ] contracts raised as DECISION — N
    - [ ] (r1) as one implementation — N decisions undone by another
    - [ ] (r2) as the user's experience — N paths walked, N undecided
    - [ ] (r3) by meaning, not by string — N concepts swept
    - [ ] (r4) where nobody has looked — N long-green claims re-derived

## For this mandate

- `how each was verified` names the method per claim — `run`, `probed` or `implementation read`. A claim you could not verify is `assumed`, and it says so on the line above.
