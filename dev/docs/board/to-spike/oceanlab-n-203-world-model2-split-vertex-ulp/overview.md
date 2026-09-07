+++
priority = "p2"
kind = "debug"
summary = "OceanLab byte-exact N=1..202, FAILS at N=203: one world Model2 point pair off by ~1-2 ULP near x=-256, same shape as the fixed N=13/WanChai-N40 MergeNearPoints bug but not the same cause."
+++

# OceanLab N=203 world Model2 split-vertex ULP divergence

Found 2026-09-07 chasing the N=203 bail (`ladder_run.py --dx 14_OceanLab_Lab.dx --from 203 --to 203
--force-ref --keep-native`). Gate residual: `BODY model model2` only (`Polys@Model2` soup also
differs downstream of the same points). `token_diff.py`/`body_token_diff.py` first show a raw token
COUNT mismatch (63317 vs 63319) that's a red herring — `model_dump.py` narrows it to exactly the
`points` array: same length both sides (3776), and as a MULTISET only 2 values differ.

## The divergence

    native only: (-256.0001220703125, 600.000244140625, -1800.0)  at points[617]
                 (-256.0001220703125, 504.000244140625, -1704.0)  at points[619]
    ued22  only: (-256.00006103515625, 600.000244140625, -1800.0) at points[612]
                 (-256.00006103515625, 504.000244140625, -1704.0) at points[614]

x differs by exactly 2 ULP at this magnitude (2 * 2^-15 = 6.103515625e-05); y/z are identical.
Neither side's value appears anywhere in the OTHER side's points array (not an index/order shift —
confirmed by full-array multiset diff). Everything else in `Model2` — vectors, nodes (2640/2640,
byte-identical apart from the expected iVertPool-index shift these two slots cause), surfs, verts,
lightmap, bounds, leaves, lights — is untouched; this is a pure 2-point value divergence.

## What's ruled out

- **Not the raw brush transform.** `brush483` (a "2D loft" builder shape: `2DLoftSIDE`/`2DLoftEND`/
  `2DLoftTOP` faces) is the last actor at N=203. Its own CSG-soup ring vertices near this region
  (`(-260.0001220703125, 600.000244140625, -1800.0)`, `soup_poly_dump.py --near`) are byte-IDENTICAL
  between native and UED22 — same raw authored/transformed float, confirmed via `soup_poly_dump.py`
  on both `native_N203.dx` and `ref_N203.dx`. So the divergence is a CSG-time computation, not a
  transform/GMath issue.
- **Not a single-hop `line_plane_intersection` crossing against the obvious candidate plane.**
  `brush1423`'s "OUTSIDE" face is a perfectly axis-aligned wall at `base=(-256.0,-252.0,0.0)`,
  `normal=(-1,0,0)` (both exact floats). Feeding `fpoly.rs::line_plane_intersection`'s exact formula
  (verified in numpy float32) with either edge-direction ordering of the brush483 ring edge
  `(-260.0001220703125, 600.000244140625, -1800.0) -> (-236.0001220703125, ...)` against this plane
  yields **exactly -256.0** — neither side's stored value (which are both ~1-2 ULP off `-256.0` in
  the OTHER direction from what a clean crossing gives). So this specific wall is not the (only)
  input to whatever produced the divergent point.
- **Live crossing-vertex instrumentation** (a temporary `eprintln!` in `fpoly.rs::split_with_plane`'s
  cut branch, gating on `|inter.x - (-256.0)| < 0.001`, reverted after use — not committed) logged
  every crossing near x=-256 during a native N=203 build. None of the ~5500 logged crossings produced
  `inter.x` bit-equal to native's stored `-256.0001220703125` (`0xc3800004`) or UED's
  `-256.00006103515625` (`0xc3800002`); the closest values were `0xc3800000` (exact -256.0),
  `0xc37fffff`/`0xc37ffffe`/`0xc37fffeb`, `0xc3800002`, `0xc3800008` — so the divergent point in the
  final `Model2.points` array is **not produced by a `split_with_plane` crossing directly**, at least
  not one whose `inter.x` value survives unmodified into the final array.
- One instrumented crossing used `base = (-256.00012, 600.00024, -1800.0)` — i.e. exactly native's
  divergent value — as a plane's `Base` parameter with `normal=(0,-1,0)`. That means this point
  (or one bit-identical to it) already exists as a real stored Points-array entry *before* this
  crossing runs, most likely a genuine (non-computed) vertex of `brush483` itself — consistent with
  it being the 2D-loft's own fan-center/axis point. Neither side's stored final value showed up as a
  raw soup vertex of `brush483` when searched directly (the point may already be consumed/replaced by
  fragments by the time the soup is dumped).

## Working hypothesis (unconfirmed)

This looks like the same BUG CLASS as the already-fixed OceanLab N=13 / WanChai N=40 issue
(`db857032`, `dev/docs/board/done/oceanlab-n13-csg-soup-split-vertex-1-ulp/`): a point that should be
WELDED onto (or already IS) a nearby existing pool point ends up with two builds picking different
final coordinates for what is conceptually the same location, 1-2 ULP apart. That fix was specifically
`MergeNearPoints` failing to remap `FBspSurf.pBase` alongside `FVert.iVertex` — confirmed NOT the gap
here (the current `bspoptgeom.rs::merge_near_points` already remaps both, per `db857032`/`d213832f`).
So this is either:

1. A different point-pooling/insertion-order divergence (native's incremental per-brush `AddPoint`
   dedup, `bspcsg.rs::find_nearest_vertex`, vs. the same-radius batch `merge_near_points` pass,
   picking different existing candidates at slightly different times), or
2. A genuinely new numeric-provenance divergence not yet isolated to a specific engine routine.

Neither could be pinned down at the level of static disassembly re-reading + numeric replay used for
the campaign's other same-shaped fixes today (`gather-box-verdict`, `oceanlab-n153-temp-brush-rsp`).
Closing it for real likely needs the same kind of live-editor-probe or fresh disassembly pass those
spikes used (e.g. instrument the editor's own `bspAddPoint`/`MergeNearPoints` call for this exact
brush/vertex under `winedbg`, the way `URender::BoundVisible` and `FLinePlaneIntersection` were
captured this session) — out of scope for a single diagnostic pass; parking here rather than forcing
an unconfirmed fix (`NATIVE-MATERIALIZE.md` prime directive: no masking, no guessing).

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
      --dx <…>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/model_dump.py \
      <native_N203.dx> <ref_N203.dx> model2

No exclusion proposed — this is flagged as a reproducible algorithm difference per
`NATIVE-MATERIALIZE.md`'s prime directive, not a candidate for the closed exclusion set.
