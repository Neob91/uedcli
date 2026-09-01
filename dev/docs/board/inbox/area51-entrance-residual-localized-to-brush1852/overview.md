+++
priority = "p1"
kind = "debug"
summary = "Area51 Entrance's entire +85 node/+51 leaf residual live-localized to Brush1852; live-traced to classify-BSP over-fragmentation (26 vs 17 terminal fragments), NOT a keep/discard bug (disassembly-verified). Exact split-divergence node not yet pinned. Training Final open, static lead only."
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

**Not yet root-caused at the full-level scale, but narrowed live this round (2026-09-01).** Adding
`Brush1852` (`CsgOper=CSG_Add`, 6 polys, `Rotation=(Yaw=-49152)`, no mirror scale) to the 1342-brush
base: native gains +135 nodes/+51 leaves, the real editor gains only +50 nodes/+0 leaves. It is one of
4 placements of an identical-shape prop (`Brush1849`/`1850`/`1851`/`1852`); the first 3 (different
`Location`s) build byte-exact, so the divergence is not the brush's own geometry but something
position/context-dependent about how it CSGs against the accumulated world tree.

Live gdb-traced this round (real editor's `AddBrushToWorldFunc`, `Editor.dll` RVA `0x31770`, vs
native's `bspcsg.rs::leaf_func`) at the n=506→507 prefix transition (Brush1852 is the last brush of
the exact n=507 prefix, so its own incremental CSG call is cleanly isolated). Result:
**the keep/discard decision logic is disassembly-confirmed byte-identical** (same `Filter==0/2` add
unconditionally, `Filter==5` add-unless-`PF_Semisolid` gate, same `bspAddNode` call signature). The
divergence is instead that **native's classify-BSP descent produces 26 terminal fragments for
Brush1852's 6 polys against the n=506 world, vs the editor's 17** (14 kept/12 discarded vs 13
kept/4 discarded) — over-fragmentation during `FilterEdPoly`'s split, not the leaf callback. One
authored poly (`i_brush_poly=4`) alone accounts for 10 of native's 26 fragments. The "editor absorbs
with 0 new leaves" full-level number is NOT reproduced at this reduced prefix scale (editor keeps 13
fragments here, not 0) — that number is apparently specific to the much larger accumulated 1343-brush
context. No fix shipped — the exact node/plane where the two descents first disagree (Front/Back/
Split/Coplanar) is not pinned; needs a `FilterEdPoly`-loophead-level trace (like `editor_descent.py`)
on both sides, correlated finer than Base/Normal (full vertex list or split-path). See
`dev/docs/native-materialize-findings.md`, search "OVER-FRAGMENTATION" for full detail, including a
sandbox infrastructure fix (`docker cp` is broken here whenever a `:ro` mount is present; use `docker
exec -i ... cat` instead — affects `editor_tree_oracle.py`/`editor_descent.py` too).

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
(prefix binary search), `area51_remove1852.py` (decisive removal test), `area51_subset.py` (N-brush
editor golden builder), `area51_addfunc_oracle.py` (live gdb trace of the editor's
`AddBrushToWorldFunc`), `area51_native_leaf_dump.py` (native's matching classify trace),
`area51_compare_tail.py` / `area51_frag_diff.py` (tail-diff and fragment comparison).
