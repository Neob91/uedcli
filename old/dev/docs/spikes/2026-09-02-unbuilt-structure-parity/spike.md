# Unbuilt-structure byte parity vs UED22 — findings + harness

Goal (owner-ruled 2026-09-02): `assemble_unbuilt`'s output byte-identical to a fresh UED22
`MAP NEW` → `MAP IMPORT` (whole-level T3D) → `MAP SAVE`, excluding only the fields proven
nondeterministic between two identical editor runs: the GUID, every StateFrame's LatentAction
(stack garbage), `TimeSeconds`/`AIProfile` (session clock/counters), the six viewport Camera
bodies (viewport state), and name-table tail order.

Reference recipes compared first (owner-directed): `MAP IMPORT` vs `EDIT PASTE` vs the hybrid
IMPORTADD+PASTE. Paste = import + `bSelected` on every pasted actor + a stray clipboard builder
brush + float-ULP Location damage from the ±32uu drift round-trip; import is the only recipe that
reproduces authored content exactly, and is fully deterministic (A/B golden pairs byte-identical
in all three tables). The editor's T3D parser TRUNCATES unquoted strings at whitespace, so the
golden builder quotes every StrProperty value (`_quote_str_props`).

## Facts derived (each pinned in `uedcli/tests/test_ued22_save_facts.py` or the writer)

- **Export-table order, closed form**: `[LevelInfo, Polys3, Camera6, Camera7, Model2]`, then the
  creation stream (points, brush actors, per-brush `(Model, Polys)` pairs with LevelSummary just
  before the last Polys) with `stream[R]`, `R = (n_points + 3·n_brushes − 1) // 2`, hoisted into
  the last freed slot and Camera11 taking its place; then `Camera8..10`, `MyLevel`. Element-exact
  on four goldens (toysmall/toy30/toy150/UNATCO).
- **Actors array**: `[LevelInfo, first brush, None] + points + [None] + brushes[1:] +
  Camera6..11`; no synthesized builder brush.
- **Naming**: `Model2`/`Polys3`/`Camera6..11` fixed boot signature; brush *i*'s Polys is
  `Polys(6+2i)`; brush shape Models keep their T3D names.
- **Tag encodings**: bools are size-code 5 + a zero size byte (`0xd3/0x53 00`); sizes 1/2/4/12/16
  use the fixed codes; static-array element 0 is a plain tag (no array bit/index byte).
- **Property order**: the per-class `UStruct.Children` chain of the EDITOR's own `.u` packages
  (not the game's — different prop sets and order), most-derived class first
  (`uprops.uclass.class_serialization_order`; 100% of actors across six goldens). Decoder fix:
  UField bodies start with a full tagged-prop header, not always a bare None (UED22
  `Engine.Actor.Touching` carries a real tag).
- **Editor import stamps**: `Region=(Zone=LevelInfo,-1,0)` on every actor;
  `Base=LevelInfo` iff effective `bStatic=False ∧ bCollideWorld=True ∧ Physics=PHYS_None`
  (141/1250 split on UNATCO, zero exceptions); `previousPath`/`VisNoReachPaths` reset (dropped);
  LevelInfo gains `TimeSeconds`/`AIProfile`/`Summary`; movers' `BasePos`/`BaseRot` are NOT
  derived at import (only at rebuild). Poly `iLink` runs the bspValidateBrush link phase; poly
  normals are recomputed from winding (`CalcNormal`, double-sqrt `NormalizeSlow`); an unlabeled
  poly's `Item` is the NAME `None`.
- **Flags**: movers are load-all (`0x02070001`, shape `0x00070001`) unlike static brushes'
  edit-only; name-table flags are `0x10 | union of referencing-context load bits` (+ intrinsic
  upper bits on a fixed engine-name set); LevelSummary `0x00070004`, Cameras `0x02340000`.
- **Model bodies**: brush shape models carry computed bbox (IsValid=1) + FSphere with
  `W = f32(sqrt_f64(max r²) · 1.001f)` rounded ONCE (734/734; the twice-rounded chain misses
  130), `NumSharedSides=4`, trailing `RootOutside=Linked=1`; the world model is `Model2` with
  empty `Polys3` and `NumSharedSides=4`. URL is `unreal://…:7777` regardless of game.
- **Texture binding**: the importer binds poly textures by BARE name against the loaded packages
  (ASCII load order), even ignoring an explicit qualifier when the name exists elsewhere
  (`area51textures.Area51Wall_A` → `CoreTexMetal`).

## Final state (2026-09-03)

- Mover shape models: `csgPrepMovingBrush` ported to the Rust core
  (`build_brush_model`; `SplitPolyList` RebuildSimplePolys mode, GOOD/Balance=15) — 28/28 UNATCO
  mover models AND mover-`Polys` iLink arrays byte-exact; wired into the writer.
- Table order SOLVED (disasm `UObject::SavePackage`, core.dll 0x277c0 + live traces): both tables
  are collected in CREATION order, reference-counted during the tag pass, then MSVC-qsorted
  DESCENDING by count (unstable CRT qsort, ported). The creation-order model (boot constants +
  per-package CreateExport/FName order with a one-step root delay + the map-time walk incl. the
  `Brush1` builder-name intern) lives in `uedcli/native/saveorder.py`; `assemble_unbuilt` runs
  two-pass and emits both tables generatively. Import tables: byte-exact on all four goldens.
  Name tables: exact on the three toys; UNATCO/OceanLab retain same-count TIE order differences
  (map-time actor names intern in first-REFERENCE order — owner-excluded from the parity bar).
- Gate verdict: `byte_gate.py` **BYTE PARITY: YES** on toysmall (fully generative) and on
  UNATCO + OceanLab (name order equalized via the oracle; everything else generative) — i.e.
  byte-identity modulo the ruled exclusions on all three, the two big levels additionally modulo
  the excluded name-tie permutation in fully-generative mode.
- **Ruled deviation (owner, 2026-09-03): a simple builder brush is ALWAYS synthesized**
  (`DefaultBrush` + shape `Brush` + `Polys4`, Actors[1], no first-brush hoist, no None holes).
  Live-measured why: UED22 adopts Actors[1] as its red builder brush and excludes it from CSG at
  EVERY rebuild — even the editor's own import-save loses its first content brush's geometry at
  any later `MAP REBUILD` (toysmall: same-session import+rebuild AND load+rebuild both carve only
  the second cube). The parity gates above were byte-proven on the pre-deviation layout; the
  builder triple is the one intentional difference from an import-save.

## Harness

`build_native_unbuilt.py` (trunk → native unbuilt, optional table oracle) ·
`build_ued_import_golden.py` / `build_ued_paste_golden.py` (editor references) ·
`structure_diff.py` (table/field/body diff, order-explicit) · `canon_diff.py` (index-canonical
content diff) · `byte_gate.py` (full-file compare modulo the exclusion masks) ·
`predict_export_order.py` (the closed form). State at writing: UNATCO byte-clean outside the
mover models and the two oracle-seeded table orders.
