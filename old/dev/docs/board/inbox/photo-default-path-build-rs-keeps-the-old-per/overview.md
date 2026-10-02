+++
priority = "p3"
kind = "debug"
summary = "photo/default-path build.rs keeps the old per-face normal logic (not the uniform SNS(X·CalcNormal) rule)"
+++

# photo/default-path build.rs keeps the old per-face normal logic

The 2026-09-03 Vandenberg round (`a7be107`) replaced `bspcsg.rs::brush_loop1`'s three-way normal
split with the editor's uniform rule — every face normal = `SafeNormalSlow(X · CalcNormal(local))`,
authored normals ignored (proven from a trunk-built golden's own Polys bytes; spike
`2026-09-03-vandenberg-first-divergent-brush`). `build.rs::build_geometry_from_brushes` (the
`level photo --native` / `brush intersect` default path) still trusts authored normals with the
old dot<0.9999 disagree-guard (`build.rs` ~858), so the two paths now derive normals differently.
It DOES honour the new `BrushInput::orientation` mirror reversal (shared LOOP-1 shape), so mirrors
are consistent. No known observable defect today (photo output is a render, not a byte-parity
target); unify when convenient.
