+++
priority = "p2"
kind = "unknown"
summary = "Native point/vert-pool byte-parity: port the Pass-D orphan-ring re-emit (`zones.rs`) + a no-clear repartition (`bspcsg.rs`)"
+++

# Native point/vert-pool byte-parity: port the Pass-D orphan-ring re-emit (`zones.rs`) + a no-clear repartition (`bspcsg.rs`)

The final geometry-body byte item (`points 2035 / verts 16163
/ nss 2739`). **RE-SCOPED 2026-07-18 (`sections/82` §10.16) — the prior "CSG over-production /
z=0 graze" framing was FACTUALLY WRONG, proven by a live oracle sweep** (`editor-tree-oracle/
repart_pool_oracle.py`, `repart_stage_oracle.py`). Native does NOT over-produce: the editor's CSG-phase
pool (**4939 pts / 17120 verts**, `bspRepartition` entry) is *bigger* than native's, nodes/surfs match
exactly (2316/524). The editor's `bspBuild` then COMPACTS to **4405 verts / 2088 pts** (`EmptyModel(0,0)`
keeps Points/Vectors/Surfs, `SplitPolyList` appends+dedups, `bspRefresh NoRemapSurfs=1` keeps referenced
+ all 524 surf bases). Live ring sums are IDENTICAL (Σnv=4521 both). The two real gaps are pure orphan
bookkeeping:
- **Verts (native 4521 vs editor 10518 — dominant) = `TestVisibility`/Pass-D ring RE-EMISSION.
  ~~Fix is in `zones.rs`~~ DONE 2026-07-18 (`sections/70` §11).** Ported the per-landing orphan
  re-emit in `zones.rs`: **Verts 10407→16183** (editor 16163, +20 residual), **NumSharedSides
  2707→2739 byte-identical**, all guards intact (1156/1156 planes, soup
  853/853). **+20 residual half-closed 2026-07-18 (`42-bspoptgeom-decode.md §9`):** +2 of it was a
  `bspOptGeom` pass-1 over-weld (missing live-table dup-guard update, fixed in `bspoptgeom.rs`) →
  welds 977→975, **Verts 16183→16172**, NumSharedSides still 2739. **Remaining +9 = Pass-D orphan
  slots** (native pool 10527 vs editor 10518 at `bspOptGeom` ENTRY) whose stale-pre-`bspRefresh`
  `iVertex` bytes are still not editor-faithful — see next item.
