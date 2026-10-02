# bspOptGeom T-junction detector — edge-INTERIOR prototype (evidence for §10.13)

**Date:** 2026-07-18. **Status:** diagnostic prototype (NOT committed to `bspoptgeom.rs` — proves
the byte-parity lever is the detector, not the partitioner).

## What this proves

The full-castle vertex/point-pool gap (native `verts 4630 / points 1797 / nss 1161` vs golden
`verts 16163 / points 2035 / nss 2739`) is **entirely** a `bspOptGeom` T-junction-detector gap, NOT a
`SplitPolyList` ring-distribution gap. The pre-`bspOptGeom` BSP tree native builds is already
**byte-isomorphic** to the editor's (see `editor_preopt_nodes.py` + the §10.13 numbers): 0 plane/link
diffs across all 1156 nodes, identical per-node `NumVertices` histogram, identical live vert sum
(4521). The only difference is that the editor's `bspOptGeom` welds ~975 T-junction vertices native's
does not.

`bspoptgeom.rs::tjunction_edge` (as committed) only welds a point that projects within `0.25 uu` of an
edge **endpoint** (`proj <= -THRESH → skip`), i.e. a *near-vertex* weld. But the editor welds points
in the **interior** of an edge. Concrete case (index-aligned node 1, plane `(-1,0,0,48)`):

```
native node 1 ring : (-48,-380,0) (-48,-530,0) (-48,-530,12) (-48,-380,12)          nv=4
editor node 1 ring : (-48,-380,0) (-48,-410,0) (-48,-500,0) (-48,-530,0) (-48,-530,12) (-48,-380,12)  nv=6
```

`(-48,-410,0)` and `(-48,-500,0)` lie EXACTLY on native's z=0 edge `(-48,-380,0)→(-48,-530,0)` — at
`proj = -120` / `-90` from the `cur` endpoint (deep interior). Both points already exist in native's
pool (owned by nodes 4/44/52 etc.), so this is NOT a missing-point problem — the detector rejects them
because the interior is out of its `±0.25` band. Editor pre-opt node 1 is also `nv=4` (verified
`editor-preopt-nodes.log`), so the editor introduces these via `bspOptGeom`, not `SplitPolyList`.

## The prototype (drop-in replacement for the `tjunction_edge` scan loop)

Replaces the `proj`/midpoint-capsule scan (lines ~339–381) with a clean point-on-segment-INTERIOR
test: weld at edge `(v_prev→v_cur)` if the point's parameter `t = E·(P−v_prev)/|E|²` is strictly
interior (`margin < t < 1−margin`, `margin = 0.002/|E|`) and the perpendicular distance is tight
(`|P − (v_prev + t·E)|² ≤ THRESH²`), keeping the last accepted edge.

```rust
    let p = &model.points[point as usize];
    let mut best = -1i32;
    for j in 0..nv {
        let prev = if j > 0 { j - 1 } else { nv - 1 };
        let v_prev = &model.points[model.verts[(base + prev) as usize].i_vertex as usize];
        let v_cur = &model.points[model.verts[(base + j) as usize].i_vertex as usize];
        let e = v_cur.sub(v_prev);
        let elen2 = e.dot(&e) as f64;
        if elen2 <= DEGEN_EDGE_LEN2 as f64 { continue; }
        let d = p.sub(v_prev);
        let t = (e.dot(&d) as f64) / elen2;      // 0 at prev, 1 at cur
        let margin = 0.002_f64 / elen2.sqrt();
        if t <= margin || t >= 1.0 - margin { continue; }
        let closest = Vec3::new(
            (v_prev.x as f64 + t * e.x as f64) as f32,
            (v_prev.y as f64 + t * e.y as f64) as f32,
            (v_prev.z as f64 + t * e.z as f64) as f32,
        );
        let r = p.sub(&closest);
        if (r.dot(&r) as f64) > (THRESH * THRESH) as f64 { continue; } // not on the edge line
        best = j;
    }
    if best >= 0 { Some(best) } else { None }
```

## Measured effect (castle_build.load_both, full castle)

| quantity        | committed native | PROTOTYPE native | editor golden |
|-----------------|------------------|------------------|---------------|
| isomorphic nv-diff nodes | 555        | **25**           | 0 (self)      |
| sum(node nv) (live verts)| 4543       | **5533**         | 5496          |
| NumSharedSides  | 1161             | **2728**         | 2739          |
| Verts array     | 4630             | 10418            | 16163         |
| Points          | 1797             | 1797             | 2035          |

The prototype is an APPROXIMATION (25 residual nv-diffs, slight over-weld of +37 verts, and it does
not close the point-pool gap). Byte-exactness needs a proper re-decode of `AddPointLink`'s inner scan
(`Editor.dll 0x326fc`–0x32977) — the committed decode's `proj vs ±0.25` band is the mis-read. But the
direction is unambiguous: the detector, fixed, collapses the gap from 555→25 nv-diffs and lands
`NumSharedSides` within 11 of the golden. The partitioner needs no change.

## Two residual sub-gaps (for whoever re-decodes the detector)

1. **Detector band (primary).** Re-decode `AddPointLink` so it welds edge-INTERIOR points (this
   prototype), byte-exact. This is where the 16163/5496/2739 parity lives.
2. **Repartition point pool (secondary, `bspcsg.rs`).** Native's `bsp_build` clears+rebuilds the
   Point pool to 1797; the editor keeps its incremental CSG pool → 2091 pre-opt / 2035 post-opt.
   Native's raw (uncleared) CSG pool is 6627 (3× the editor's) — native's incremental CSG
   over-produces transient points (rolled-back grazes leak). Even with the detector fixed, native
   stays at 1797 points; the last ~238 points want either the editor's `MergeNearPoints` (`0x33dc0`,
   radius 0.25) applied during/after CSG or a faithful non-clearing pool that matches the editor's
   ~2091. Minor next to (1).
