+++
priority = "p?"
kind = "owner-question"
summary = "§82 §10.16's Points diagnosis was WRONG and is now superseded by §10.18 (2026-07-18)"
+++

# §82 §10.16's Points diagnosis was WRONG and is now superseded by §10.18 (2026-07-18)

§10.16 blamed the Points gap on "the repartition CLEAR" and proposed a risky no-clear
repartition. Disproven: gating out the clear leaves `refd_points=1681` unchanged; the real cause was
the DROPPED authored `FPoly::Base` (surf pBase defaulted to `verts[0]`), fixed cheaply by plumbing
T3D `Origin`. No no-clear repartition is needed. (Doc note only — §10.16's VERT diagnosis
= `zones.rs` Pass-D ring re-emit still stands.)
