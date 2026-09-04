---
kind: finding
---

# UED22 world BSP differs per ingest verb; retail tree is unreproducible; native ≡ paste

Measured on `03_NYC_UNATCOHQ` (734 non-mover world brushes, identical coordinates on every path).
World `Model` counts (nodes / surfs / leaves):

| build                                   | nodes | surfs | leaves | verts | note |
|-----------------------------------------|-------|-------|--------|-------|------|
| SHIPPED retail `.dx`                    | 5188  | 3589  | 2266   | 82487 | GUI-optimal over authoring history |
| MAP NEW + IMPORTADD/PASTE + MAP REBUILD | 6314  | 3616  | 762    | 76488 | native reproduces this EXACTLY |
| MAP IMPORT (whole T3D) + MAP REBUILD    | 6270  | 3611  | 770    | 74934 | 892-plane node-multiset diff vs paste |
| MAP LOAD + MAP REBUILD                  | 6254  | 3705  | 776    | —     | (prior campaign measurement) |
| native `build_geometry_bspcsg`          | 6314  | 3616  | 762    | 76494 | node-plane multiset == paste, diff 0 |

Findings:
- **Retail is a fourth, different tree and is NOT reproducible from the extracted trunk** by any single
  rebuild (5188 nodes / 2266 leaves = full `OPTIMAL OPTGEOM ZONES` GUI rebuild accreted over the
  designers' incremental authoring). Confirms the campaign rule: compare against a SELF-BUILT golden,
  never the shipped map. So "parity with retail bytes" is impossible by construction — the parity
  target is a self-built rebuild, a convention.
- **The editor carves a different world BSP per ingest verb** (paste 6314 / import 6270 / load 6254)
  from the identical brushes and identical coordinates (no ±32uu shift — point ranges equal).
- **native's node-plane multiset == the PASTE tree exactly (symmetric diff 0);** it is 892 planes from
  the import tree. So native firmly targets paste, not import/load.
- **Root of paste-vs-import: a localized CSG *carve* difference, not just partition.** Surf multisets
  differ by exactly 5 — paste keeps a ~4×16×2 sliver at ≈(450,55,415), one face `PolyFlags=32`
  (PF_Semisolid), that import drops/merges. That 5-surf carve difference cascades through the
  order-sensitive BSP into the 892-plane / 44-node gap.

Implication for full-binary parity (owner wants movers + serialization + geometry, no carveouts):
only **MAP IMPORT** can be a full-package reference (imports movers with models; native's tables
already match it closely — imports 305=305). PASTE matches native's geometry but excludes movers and
uses a different table order. So the reference should be MAP IMPORT built, and native's geometry must
be re-targeted paste→import — starting from the semisolid sliver carve difference above (likely a
paste artifact native currently mirrors). Owner decision pending. [[incremental-actor-parity]]
