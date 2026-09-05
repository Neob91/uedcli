+++
priority = "p2"
kind = "debug"
summary = "Island (01_nyc_unatcoisland) FAILS the parity gate from N=5 in the world Model2 Points its zone Pass D creates. The pooling half is fixed (fbcfc17 + 15de9ce, 16/59 differing points down to 6, order exact); what remains is six 1-5 ULP split-vertex values."
+++

# Island N5+ world-`Model2` Pass-D point-order residual

## Status: REAL and OPEN. The 2026-09-05 "stale-ref false alarm" disproof was itself wrong.

That disproof was run in a worktree whose cached Island trunk held **102 actors starting at
`PathNode838`** — a truncated extraction with no `LevelInfo` and no brushes. Its N=1..16 subsets were
pathnodes and weapons, so they gated PASS trivially. A fresh extraction of
`01_NYC_UNATCOIsland.dx` gives **3653 actors starting `LevelInfo0, Brush296, Brush570, …`** (two
independent extractions agree). Re-verified 2026-09-05 against a **freshly editor-built** ref on the
correct trunk: Island **N=5 FAILS**. See `corrupt-trunk-cache-silently-passes-the-ladder`.

## Symptom (Island N=5, world `Model2`, post-`a56f6dc` faithful-dedup native)

One gate residual: `BODY model model2`. Everything else matches.

- Nodes (32) byte-identical — plane, `W`, flags, all ten indices. Surfs byte-identical. Vectors
  identical. `Points[0..42]` identical. Counts equal: 59 points both sides.
- `Points[43..58]` differ in **ORDER**, plus 1-5 float32-ULP value differences on six of them; `Verts`
  differ only in the resulting `pVertex` indices.

Points 0..42 come from the incremental CSG (`bspcsg.rs` `bsp_add_point_tol`) and match exactly.
Points 43..58 come from **zone Pass D**'s ring fill, `uedcli-native/src/zones.rs` `fill_ring_verts`.

Both sides create the same point SET (one box, x∈{-13056,13312}, y∈{-11776,11648}, z∈{128,-896}, plus
two y-cut pairs per side face). Only the visit order differs:

- UED22: the whole `x=+13312` side face, then its `x=+13312` y-cut ring, then the `x=-13056` face, then
  its ring. Grouped per side face.
- native: the `z=+128` face ring, then the `z=-896` face ring, then the two side-face rings.

The ULP differences are downstream of the order: two near-coincident values (≤5 ULP apart, well inside
the 0.015 NEAR ring threshold) share one pool slot, and whichever is added FIRST wins.

N=1..4 PASS (fresh editor refs, 2026-09-05), so N=5 is the first failing N.

## Pooling half FIXED 2026-09-05 — `fbcfc17` + `15de9ce`

Two commits, both decoded rather than tuned:

1. `fbcfc17` — Pass D pools its ring points with the editor's `FindNearestVertex` descent
   (`bspAddPoint(v, 0)`, `Editor.dll 0x10035465-0x1003547d`) instead of a first-within-0.015 scan of
   the whole pool. 16/59 differing Points → 8/59; the x=+13312 / x=-13056 grouping matches UED22.
2. `15de9ce` — the rings Pass D is still filling are visible to that descent. `bspAddNode` links its
   node (`0x100352c5`), zeroes `NumVertices` (`0x100352d4`) and re-increments it inside the fill loop
   (`0x10035348`), and `FindNearestVertex`'s vert loop is bounded by that byte (`Engine.dll
   0x101add6b`) — so a point pooled earlier in the same fill, and every earlier landing of the same
   chain node (`AssignAllZones` only zeroes them at the END of that node's body), is poolable.
   8/59 → 6/59, and the Points ORDER now matches UED22 exactly.

## What is left at N=5

Six 1-5 ULP split-vertex values (e.g. `10873.62793` vs `10873.62305`) — nothing else. Same class as
`oceanlab-n13-csg-soup-split-vertex-1-ulp`: a computed intersection a hair off, from an input that
diverged upstream. One cause for both, chased there.

All six are Pass-D landing vertices where an OBLIQUE node plane cuts `x=±13312`/`z=-144`, so they come
out of `filter_through`'s `split_with_plane`, i.e. `FPoly::SplitWithNode`.

One input to that expression is now known-correct and one is not:

- FIXED (`5d52f79`): the split PLANE. `filter_plane` synthesized `plane.xyz * plane.w`;
  `FPoly::SplitWithNode` (`Engine.dll 0x101517e0`, disassembled) reads
  `Model->Points(Surf.pBase)` / `Model->Vectors(Surf.vNormal)`. Native now does too. The residual
  MOVED rather than shrank (still six; `Points[49]`/`[58]` became exact, `[48]`/`[56]` broke) — a
  second divergence in the same expression, not a reason to keep the wrong plane.
- OPEN: the edge endpoints, i.e. the polygon that reaches the split. `node_poly` reads the node's
  ring back out of `Model.Points`, so a pool point that is itself a hair off feeds straight in; and
  `filter_through` descends, so each fragment's vertices are themselves earlier cut results.

Also tried, decode-backed, and KEPT even though it did not move the residual (`61d3633`): Pass D now
goes through `bspNodeToFPoly`'s full sequence — the pooled `Base`/`Normal` plus
`FPoly::RemoveColinears` (`Editor.dll 0x10036804`, IAT `0x100cee2c`), whose result the node's landing
gate reads (`0x1003680a`). The hypothesis was that a dropped colinear vertex changes which segment
the plane cuts; it does not fire on these polys.

Ruled out by disassembly: float summation ORDER. `FPoly::SplitWithPlane`'s per-vertex distance
(`Engine.dll 0x10151a03-0x10151a15`) and `FLinePlaneIntersection`'s numerator (`0x10150747-0x10150764`)
both emit `((dy*n.y) + (dx*n.x)) + dz*n.z` where native's `Vec3::dot` does X first — but IEEE addition
is COMMUTATIVE, so the two associate identically and are bit-equal. Measured: swapping native to the
engine's operand order changes nothing on Island N=5. The intersection's denominator uses X-first in
the same function, which is the tell that this is compiler scheduling, not semantics.

## Candidate defects (as diagnosed before the fix)

1. **Pass-D dedup rule** — CONFIRMED, and what `fbcfc17` fixes.
2. **Pass D filters against a frozen tree** — RULED OUT by measurement: native's Pass-D emission
   sequence already matches UED22 slot-for-slot (vert range 96..279, 46 four-vert rings, identical
   live `iVertPool` set and identical orphan runs). Native's `passd_walk` recurses `i_back`
   (= engine `iChild[1]`, FRONT) then `i_front` (= `iChild[0]`, BACK), post-order — exactly the
   decoded `AssignAllZones` order (`passD-assignzones-7400.md` §Pseudo-C); `model_write.rs` lines
   83-84 confirm the field swap.

The "different order" symptom came from lookup VISIBILITY, not from ordering: UED22 mints ~15 more
Pass-D points than native did (max stale orphan `iVertex` 85 vs native's pool peak of 71), because
each corner a killed landing left behind is invisible to the descent and gets re-minted by the next
landing — and the re-minted copy is the one a live ring references, so it is the one that survives
the order-preserving GC.

Instrument with `UEDCLI_PASSD_DUMP=1`: it logs each `Emit` and each Pass-D pool point creation.

## Earlier measurement (pre-`a56f6dc`, kept for history)

At N=8 on the pre-dedup-fix native the same cell showed verts 511 vs 507 (+4 orphan `FVert`) and
points 79 vs 78 (+1). Nodes 45=45, live-ring slots 186=186, vectors 18=18 matched. The `a56f6dc`
dedup fix cut Island N=5 from three gate residuals to this one, so the counts now agree and only the
order does not — same cell, same mechanism.

## Repro

    ladder_run.py --dx <…>/Maps/01_NYC_UNATCOIsland.dx --from 5 --to 5 --force-ref --keep-native
    token_diff.py  <…>/native_N5.dx <…>/ref_N5.dx model2
    model_dump.py  <…>/native_N5.dx <…>/ref_N5.dx Model2
