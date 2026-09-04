---
kind: finding
---

# Why UED22's world BSP differs by ingest verb — ROOT CAUSE: the Actors[1] builder-brush slot

Measured on `03_NYC_UNATCOHQ` (734 non-mover world brushes, identical coordinates on every path).

## The observation

Same brushes, different world `Model` (nodes / surfs / leaves) depending on how they enter the editor:

| build                                        | nodes | surfs | leaves | Actors[1] |
|----------------------------------------------|-------|-------|--------|-----------|
| MAP NEW + EDIT PASTE + MAP REBUILD (paste)   | 6314  | 3616  | 762    | MAP NEW builder brush (sacrificial) |
| native `build_geometry_bspcsg`               | 6314  | 3616  | 762    | synthesized `DefaultBrush` (sacrificial) |
| MAP IMPORT / MAP IMPORTADD FILE= + REBUILD   | 6270  | 3611  | 770    | **`Brush74` — the first REAL world brush** |
| SHIPPED retail `.dx`                          | 5188  | 3589  | 2266   | (GUI-optimal over authoring history — unreproducible) |

## Root cause (confirmed, static + known rule)

**UED22 excludes `Actors[1]` from CSG at every rebuild** — it adopts that slot as its red builder
brush (owner ruling 2026-09-03; commits `a098cbe`/`3d2176f`; `uedcli/native/unbuilt.py:328`, which
synthesizes a sacrificial builder there for exactly this reason: "even the editor's OWN import-save
loses its first content brush's geometry at any later MAP REBUILD").

- **paste** (via `MAP NEW`) and **native** (via synthesis) both place a throwaway builder brush in
  `Actors[1]`, so excluding it costs nothing and all 734 real brushes are CSG'd → 6314.
- **whole-file MAP IMPORT/IMPORTADD** as previously run had **no builder brush**, so the first real
  brush `Brush74` occupied `Actors[1]` and was silently dropped from CSG. Static proof (two cached
  goldens, byte-compared): `Brush74` and `Brush132` brush models are byte-identical across paste and
  import (ingest does NOT alter geometry); `Brush74` owns 4 surfs in paste and **0 in import** — the
  only brush in the level that vanishes. Its loss also removes `Brush132`'s abutting semisolid sliver
  (collateral), giving the 5-surf difference and the 44-node / 892-plane cascade through the
  order-sensitive BSP.

So the 6270 "import tree" is a **defective build missing its first content brush**, not a legitimate
alternative partition. The earlier "semisolid Brush132" framing was a symptom; the cause is the
missing builder-brush slot.

## Confirmation — minimal repro (live editor)

`Actors[1]` exclusion is by POSITION, independent of the brush there or the ingest verb:

| build                                            | Actors[1]          | world surfs |
|--------------------------------------------------|--------------------|-------------|
| native CSG `{Brush74,Brush132}`                  | (native excludes nothing) | 7 (both kept) |
| editor IMPORTADD `{Brush74,Brush132}`            | Brush74 (only solid) | **0** (excluded ⇒ empty) |
| editor IMPORTADD `{Brush663,Brush74,Brush132}`   | Brush663 (sacrificed) | 8 (Brush74 kept) |

## Fix / implication

The whole-file ingest golden needs an **explicit** sacrificial builder brush emitted as `Actors[1]`
(the throwaway native's `assemble_unbuilt` already synthesizes — `DefaultBrush`/`Brush`/`Polys4`).
`MAP NEW` before `MAP IMPORTADD` does NOT work: `MAP IMPORTADD FILE=` discards MAP NEW's builder
(measured — the golden had 734 brush actors, not paste's 735, and still built 6270). So the reference
builder must PREPEND a builder-brush actor to the imported T3D. Full-build validation of that
(expect 6314/3616/762) is the next step, teed up for the parity-ladder phase.

Net: **MAP IMPORTADD of a T3D whose first brush is a sacrificial builder** yields native's geometry
(6314) AND carries movers with their models AND matches native's serialization — a single valid
full-binary reference. Retail (5188) stays unreproducible and is not a byte target.
[[incremental-actor-parity]]

## Owner ruling 2026-09-04 — the symmetric dummy-builder convention

ALWAYS add a dummy builder brush; make the two builds symmetric so
`UED22 IMPORTADD-with-dummy == native materialize`:
- **UED22 IMPORTADD reference**: emit an explicit dummy builder brush as `Actors[1]` (MAP NEW's
  builder is discarded by `MAP IMPORTADD FILE=`, so it must be in the imported T3D). Match native's
  synthesized builder (`unbuilt.py` `_BUILDER` = `DefaultBrush`/`Brush`) so the two packages align.
- **native build**: skip `Actors[1]` by POSITION, dropping the `is_builder_brush` heuristic from
  `build_world_model` (materialize.py:266). For a real content trunk this is a no-op (the extracted
  trunk carries no builder brush — 0 `is_builder_brush` hits on UNATCO — and native's synthesized
  dummy is already excluded from CSG by not being a CSG input). Keep the `is_builder_brush` function:
  it has many other callers (add/parse/stash/preview filters).
- Both then exclude `Actors[1]` identically ⇒ world = CSG(`Actors[2..]`) = real brushes = 6314.
