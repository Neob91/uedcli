+++
priority = "p3"
kind = "chore"
summary = "`zones.rs` `fix_ring` — two latent faithfulness caveats (§70 §12, cold-review 2026-07-18)"
+++

# `zones.rs` `fix_ring` — two latent faithfulness caveats (§70 §12, cold-review 2026-07-18)

(a) `fix_ring` (and the existing `fpoly::fix` it mirrors) compares each vertex to its immediate
ORIGINAL predecessor, not the last-KEPT vertex like UnrealEd's real `FPoly::Fix` — diverges only on
a monotonic sub-0.002 drift chain `[A,A',A'']` (none on the calibration castle). (b) `fix_ring` is
applied ONLY to Pass-D `Orphan` emissions; the real editor runs `Fix` on EVERY fragment before
`bspAddNode`, so a future map with a coincident-vertex pair on a LIVE (`OriginalRing`/`Frag`) ring
would keep it in native (wrong `iVertPool`/`NumVertices`) while the editor drops it. Byte-equivalent
on `Test_Castle.dx` (no live ring has a within-0.002 dup); restricted to orphans to avoid touching
the live ring-sum / `NumSharedSides` guards. Make `Fix` universal + last-kept-vertex-faithful if a
future map shows live-ring drift.
