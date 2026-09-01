+++
priority = "p1"
kind = "debug"
summary = "Area51 Entrance's entire +85 node/+51 leaf residual live-localized to Brush1852 (CsgOper-absent-first-brush pattern ruled out); mechanism not yet found. Training Final open, static lead only."
+++

# Area51 Entrance residual localized to Brush1852; Training Final still open

Breadth-sweep check (per the standing worst-first queue): does the shipped `CsgOper::Active` fix
(`528e602`) retroactively close any of Area51 Entrance's or Training Final's residual? **No** — neither
level's first world-CSG brush (or any brush) lacks a `CsgOper=` property; both are pure Add/Subtract.
Full detail, live evidence, and the decisive removal test: `dev/docs/native-materialize-findings.md`,
search "Area51 Entrance / Training Final breadth check".

## Area51 Entrance — localized, mechanism open

Live prefix binary search (reusing `dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/
prefix_search_lib.py`, the method that found FreeClinic08's `Brush586`/NSFHQ04's `Brush8321`)
localizes Area51's entire `d_nodes=+85 d_leaves=+51` (surfs already exact) residual to ONE brush:
prefix n=506 (`Brush1851`) is byte-exact; n=507 (adding `Brush1852`) diverges.

**Decisive test, live-verified**: removing `Brush1852` from the FULL 1343-brush level closes the
residual to **d_nodes=+0 d_surfs=+0 d_leaves=+0** on both native (in-process) and a fresh
`build_ued_golden.py --world-only --no-light --no-obj-load` editor rebuild. One brush fully explains
the level's entire structural residual — same shape as FreeClinic08's `Brush586`.

**Not yet root-caused.** Adding `Brush1852` (`CsgOper=CSG_Add`, 6 polys, `Rotation=(Yaw=-49152)`, no
mirror scale) to the 1342-brush base: native gains +135 nodes/+51 leaves, the real editor gains only
+50 nodes/+0 leaves — the editor absorbs it with no new leaf region, native creates 51. It is one of 4
placements of an identical-shape prop (`Brush1849`/`1850`/`1851`/`1852`); the first 3 (different
`Location`s) build byte-exact, so the divergence is not the brush's own geometry but something
position/context-dependent about how it CSGs against the accumulated world tree. No disassembly or
live gdb done this round — per the no-guessing rule, no fix shipped. Next step: isolate a minimal
synthetic repro (this brush's shape at its own `Location` against a small hand-built solid context) and
live-trace `bsp_brush_csg`/`filter_world_through_brush` the way the Vandenberg/mirror-determinant
investigations did.

## Training Final — open, static lead only

Residual (nodes native=11227 golden=11122 `d=+105`, surfs exact, leaves `d=+13`) not live-localized
this round. Static per-brush node-owner attribution is diffuse (297/764 brushes differ, no dominant
outlier — same "wrong level of attribution" trap as everywhere else), but flags a lead: 4
near-consecutive small (6-poly `CSG_Add`) brushes `Brush907`/`909`/`911`/`915` (world-CSG idx 660-668)
carry large, partially-offsetting diffs (`+71`/`+71`/`-52`/`+77`). Needs its own live prefix binary
search (same harness, adapted) to confirm or refute before trusting this lead.

## Harness

Committed under `dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/`:
`area51_attrib.py`/`tf_attrib.py` (static per-brush node-owner attribution), `area51_prefix_search.py`
(prefix binary search), `area51_remove1852.py` (decisive removal test).
