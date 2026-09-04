+++
priority = "p3"
kind = "debug"
summary = "Two low-severity follow-ons from the N=6 prop-order fix (262280f): the unit test pins the UED22 fact but not the assembler wiring, and prop-emit order now reads UED22 while base-stamp/mover semantics still read the game v68 schema."
+++

# Prop-order fix (`262280f`) follow-ups

From the review of the ZoneInfo prop-order fix. Neither blocks the ladder (the 3×6 gate covers
integration), both worth hardening.

1. **Test doesn't guard the wiring (MEDIUM).** `test_zoneinfo_serialization_order_comes_from_the_ued22_substrate`
   re-derives the UED22 resolver and calls `class_serialization_order` directly — it never exercises
   `_assemble_once`/`rank_for`. Reverting the one-line resolver swap (back to `schema_paths`) would
   leave it green. Assert instead on an assembled `ZoneInfo` body / `rank_for` output from a built
   subset.
2. **Schema split (LOW).** Prop-emit ORDER now comes from the UED22 substrate; base-stamp/mover
   decisions (`cdefaults`, `class_index`, `is_mover`) still read the game v68 schema (`pkg_dirs`).
   Empirically fine at N<=6, but if a class's `bCollideWorld` default or ancestry differed between
   UED22 and the game/stub, the two answers would disagree. Add a code comment noting the split, or
   unify the source.
