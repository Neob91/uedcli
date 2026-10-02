+++
priority = "p3"
kind = "docs"
summary = "grid caption \"major = 8x drawn\" is imprecise once --grid-size escalates -- confirmed, resolved by removal"
+++

# grid caption "major = 8x drawn" is imprecise once `--grid-size` escalates

**Resolved, 2026-08-30.** Found while building `add-visual-grid-for-2d-views-in-level-actor`: the
caption's `major = 8 * drawn` only matches the true on-screen major-line spacing (`8 * step`) when
`shift == 0` (no escalation) — an explicit fine `--grid-size` forcing escalation makes the printed
`major` value diverge from the lattice actually drawn (which was always correct). Owner confirmed by
pixel measurement; spec §6 was updated to drop the `major`/`minor` caption fields outright rather than
correct the formula.
