+++
priority = "p3"
kind = "debug"
summary = "csg.rs::point_in_solid (the level photo --native replay-CSG oracle) treats a CsgOper-absent (CSG_Active) brush as an instant Subtract; the true editor semantics (decoded 2026-09-03, vandenberg-gas-csg-active-csgoper-brush-causes Round 4) defer the Active brush's solidity effect until the NEXT Add/Subtract brush's bspCleanup clears its NF_IsNew nodes, and never cut existing world faces. Materialize (bspcsg.rs) is fixed; the photo path is not."
+++

# photo-path `point_in_solid` models Active as instant Subtract

`uedcli-native/src/csg.rs::point_in_solid` replays CSG per brush: inside a brush's hull,
`solid = (oper == Add)` — so an Active brush empties its hull immediately, exactly like a Subtract.
The editor's real Active semantics (disassembly + the Paris Underground 2-brush live golden,
`vandenberg-gas-csg-active-csgoper-brush-causes` Round 4):

- pass 1 is Subtract-shaped (its faces enter the world),
- it never cuts existing world faces,
- its nodes stay `NF_IsNew` through the NEXT brush's op — that brush classifies against the
  PRE-Active solidity — and only become CSG-solid after that brush's `bspCleanup`.

A flat replay can't express the one-brush deferral; fixing it means threading brush order into the
oracle (the brush AFTER an Active must skip it in the replay). Affects `build.rs`
(`build_geometry_from_brushes` → `level photo --native`, preview) on the four known
`CsgOper`-absent-brush levels only (Vandenberg Gas, freeclinic08, nsfhq04, Paris Underground).
Materialize parity (`bspcsg.rs`) carries the correct semantics and is unaffected.
