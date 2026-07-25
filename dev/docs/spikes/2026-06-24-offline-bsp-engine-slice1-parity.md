# Offline BSP engine — slice 1: first port + differential parity vs the live editor

**Date:** 2026-06-24
**Method:** Python port (spike-grade, `_scratch/bspspike/bsp_port.py`) of the decoded CSG/BSP
pieces, diffed against a real UnrealEd build via an automated harness
(`_scratch/bspspike/oracle_diff.py`).
**Result:** ✅ the approach works end-to-end; node-count parity confirmed on the canonical box;
the oracle-extraction unknown (cost-driver #4) is retired.

This is the first executable step of the offline BSP engine (`decisions.md` 2026-06-24 09:07
UTC; doctor spec §7). It de-risks the project: the heuristic was decoded in
[`2026-06-24-bspbuild-partition-heuristic-from-binary.md`](2026-06-24-bspbuild-partition-heuristic-from-binary.md);
this proves a faithful port runs and matches the editor on a small input, and pins how the
differential harness works.

---

## 1. What was ported (`bsp_port.py`, spike-grade, in `_scratch/`)

- **`FPoly` classify/split** — `classify(poly, plane)` is `SplitWithPlaneFast` (Engine `0x151f90`,
  decoded this session): per-vertex `d>+0.25`→front / `d<−0.25`→back (the
  `THRESH_SPLIT_POLY_WITH_PLANE` band), returning `0=Coplanar 1=Front 2=Back 3=Split`. `split()`
  cuts a poly at the `d=0` crossings (Sutherland-Hodgman, both sides).
- **`find_best_split`** — a faithful port of `FindBestSplit` (Editor `0x335d0`): score
  `(100−Balance)·Splits + Balance·|Front−Back|`, portal candidate bonus + ×16 portal-split
  penalty, candidate/classify step by optimization (Optimal 1 / Good N/10 / Lame N/4), strict-`<`
  earliest tie-break. Score computed in float32 (`_f32`).
- **`split_poly_list`** — the textbook UE1 recursion: pick the best plane, partition polys
  front/back, coplanar-same become the node's surface, recurse.

It is **spike-grade and stays in `_scratch/`** (gitignored) until parity is locked across more
cases; it is NOT yet promoted to a `uedctl/` module.

## 2. The differential harness (`oracle_diff.py`) — and cost-driver #4 retired

The harness spins a **fresh isolated ephemeral editor** (`docker compose run` + its own
WINEPREFIX volume, per `parallel-editors.md`), drives it via uedctl's `Driver`, and tears it down:
`MAP NEW` → **`writes.add_actor` (EDIT PASTE)** the brush → `MAP REBUILD` → read `Editor.log` →
diff → cleanup.

**Cost-driver #4 (how to extract the editor's built BSP) is cheap — no binary `UModel` parser
needed.** The build logs the node count directly. Confirmed live channels:
- `Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes` — the final
  count + the **leaf/zone** numbers (needed later for collision).
- `Nodes: %i -> %i` (bspRefresh/bspOptGeom passes), `bspBuild built %i convex polys into %i
  nodes` (higher verbosity; not always flushed), `bspBuildBounds: Generated %i bounds, %i hulls`,
  `BspMergeCoplanars reduced %i->%i`.
The harness parses the final `Nodes:`/`Portalized:` value.

**Trap learned (cost a re-run):** a brush added via `MAP IMPORTADD` does **not** participate in
CSG — `MAP REBUILD` produced `0 nodes`. Brushes must enter via **EDIT PASTE**
(`writes.add_actor`), the same finding behind the FULL RE-IMPORT decision
(`decisions.md` 2026-06-18, `quirks.md` "How brushes enter the level"). Point actors IMPORTADD;
brushes paste.

## 3. Parity result

| Input | Python port | Editor (live) | |
|---|---|---|---|
| 256³ subtract box | **6 nodes** | **6 nodes** (`Portalized: 1 leaves, 6 nodes`) | ✅ MATCH |

Hand-reasoned cross-check: a convex solid's faces never straddle each other's planes (the shared
edge sits at `d=0`, inside the band), so every face classifies BACK of any chosen face plane →
the builder makes a 6-node linear back-chain. Both the port and the editor land at 6.

## 4. The important nuance (shapes the rest of the port)

The editor's log showed **`Nodes: 12 -> 6`**: raw `bspBuild` *over-splits* the box to 12 nodes,
then a merge/optimize pass (`bspMergeCoplanars`/`bspOptGeom`) reduces to 6. The textbook
`split_poly_list` lands at 6 directly. So:
- **Final-count parity holds, but the intermediate trees differ.** Matching the editor on
  non-trivial geometry therefore requires porting the **full pipeline** (`bspBuild` →
  `bspMergeCoplanars` → `bspOptGeom` → `bspRefresh`), not just the splitter — exactly as planned.
- **A single convex box is the easy case** — its final tree has no real splits, so it confirms
  the pipeline + harness but does **not** yet exercise `FindBestSplit`'s discriminating power
  (where Front/Back/Split counts actually vary between candidates). The next tests must use
  geometry where faces genuinely straddle.

> **Slices 1b/2/3 are done** — see
> [`2026-06-24-offline-bsp-engine-slices1b-2-3-parity.md`](2026-06-24-offline-bsp-engine-slices1b-2-3-parity.md):
> the discriminating corpus, the `MAP REBUILD` parameter pin (Balance=50, not 15), the CSG
> world-surface build, exact parity on the convex single-volume cases, the two located count
> gaps, and the honest feasibility verdict (feasible but multi-week faithful-port volume; node
> planes need a binary `UModel` parser). The list below is the original slice-1 plan, retained
> for provenance.

## 5. Next (slice 1b → slice 2)

1. **Discriminating parity cases** (harness already supports them): two abutting boxes, two
   overlapping subtracts, a room with an additive pillar, an L-shaped room — inputs where
   `FindBestSplit`'s choice and real splits matter. Diff final node/leaf counts.
2. **Port the merge/optimize passes** (`bspMergeCoplanars` @Editor `0x36200`, `bspOptGeom`
   `0x36870`, `bspRefresh` `0x36cd0`) so intermediate→final matches the editor, then compare not
   just counts but the **set of node planes**.
3. **Then slice 2** — the CSG filter (`bspBrushCSG`) for multi-brush worlds (the actual
   sliver/T-junction producer), and **slice 3** — the leaf/zone build for collision
   (fall-through / invisible-wall ground truth; the `Portalized: … leaves` channel is the oracle).
4. **Float32 discipline** — only matters once a case shows a boundary diff; the box didn't.

Promote `bsp_port.py` from `_scratch/` to a real `uedctl/bsp/` module once parity holds across
the slice-1b discriminating set (not on a single box).
