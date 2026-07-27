+++
priority = "p?"
kind = "unknown"
summary = "`brush poly rotate` turns against the VISIBLE surface normal"
+++

# `brush poly rotate` turns against the VISIBLE surface normal

Owner
  ruling: pick sane defaults, existing content is not a constraint. So `n̂` is flipped when the brush
  is subtractive — the author selects a face they can see, and a texture verb should turn the way that
  face turns from where they are standing. The `CsgOper` dependency was the stated reason to prefer
  the raw polygon normal; it is the lesser evil, because an author knows whether they are texturing a
  room interior or a pillar, whereas "the sign silently inverts indoors" is not discoverable at all.
  This also makes all five verbs consistent: `wall`/`floor` and `run` are already invariant under
  `n̂ → −n̂` by construction, so `rotate` was the only one that read differently inside a room.
  Folded into `plans/2026-07-26-poly-surface-step1-plan.md` and `rationale/surface.md`.

---
