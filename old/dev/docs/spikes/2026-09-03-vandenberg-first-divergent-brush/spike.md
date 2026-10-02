# Vandenberg Gas: first divergent brush of the +659-node residual (2026-09-03)

Question: run the per-brush Pass-1 count trace on `12_Vandenberg_Gas` (worst level, nodes +659 /
surfs +7 / leaves +309 vs its cached golden) to find the FIRST brush where native's committed-tree
counts diverge from the editor's, characterize it, and fix the mechanism if unambiguous.

## Result: no brush diverges — the counts were never the right lens

One live gdb capture of the full golden rebuild (`vdb_editor_trace.py`, 728 `bspBrushCSG` Pass-1
calls + node-array dumps) against native's `UEDCLI_BSPCSG_BRUSH_STATE` trace: editor and native
agree on nodes/surfs at EVERY one of the 728 structural steps (both end Pass 1 at 16404/4118), and
the final Pass-1 trees are structurally identical (16404 nodes, zero linkage diffs). The divergence
was 2996 nodes whose plane FLOATS differ (up to ~32 ULPs) — first at node 734, created by k=13
`Brush41`, an UNSCALED, UNROTATED `CSG_Add` (not scaled, not mirrored, not the `Brush154` family).
Bit-level attribution of all 2996 (`vdb_model_check.py`) found three stacked mechanisms, two now
CONFIRMED and fixed, one localized:

1. **GMath sine table built with double π — CONFIRMED, fixed (`b2199cd`).** The editor's
   `FGlobalMath::TrigFLOAT[k] = sin(f32(k · 2 · π_f32 / 16384))` — float32 π (`0x40490fdb`).
   `rotation.py` used double π: 4683/16384 entries wrong, up to ~32 ULPs, hitting every
   non-cardinal index (cardinal entries agree, which is why the cardinal-only levels never saw
   it and the idx-8192 spike pin passed). Evidence: full 16384-entry table dumped from the live
   editor's memory (`vdb_sintab_capture.py` → `logs/sintab-live.bin`; core.dll static VA
   `0x1013e934`, runtime-rebased — resolved via `/proc/<pid>/maps`); the π32 formula reproduces it
   0/16384 (`vdb_sintab_formula.py`). Pinned: `test_gmath_table_matches_live_captured_noncardinal_entries`.

2. **Per-face normal rule — CONFIRMED, fixed (`a7be107`).** The editor's importer STORES
   `CalcNormal(local winding)` over the authored T3D normal — live golden bytes: `Brush41`'s stored
   Polys normal is `bf75341a/3e931f43` (= CalcNormal) while the authored text parses to
   `bf753416/3e931f47` — and `FPoly::Transform` maps it by VectorXform + `SafeNormalSlow`
   unconditionally. So every face normal is `SNS(X · CalcNormal(local))`, X = VectorXform
   (scaled/mirror) or the rotation (unscaled). This replaces the old three-way split
   (Add-keeps-authored / §48 Subtract-only recompute / dot<0.9999 guard); the castle's
   "Add keeps authored" evidence was coincidental (its authored values ARE `SNS(CalcNormal)`
   — castle cargo goldens stay green). Mirrors now signal `BrushInput::orientation = -1` and get
   the editor-faithful POST-transform ring reversal (spike 2026-06-25) instead of the marshal
   pre-reverse, so their local CalcNormal keeps the editor's bits (the pre-reversed ring's
   CalcNormal is NOT the exact bit-negation). `unbuilt.py::_calc_normal`'s doc had already
   established the import-recompute fact independently on the writer side.

   Pass-1 plane diff: 2996 → 65 nodes (all ~1-ULP, mostly `plw` — a small base-snap/plane-w
   residual, no measured count effect; left open).

3. **The count residual lives ENTIRELY in the world `bspRepartition` — localized, not fixed.**
   Second capture (`vdb_editor_trace_pass2.py`: all 870 `bspBrushCSG` calls + every
   `bspRepartition` entry + `bspOptGeom` entry): the editor enters Pass 2 at **8702 nodes / 4118
   surfs**; native at **9191 / 3839** (nodes +489). The surf gap is orphan-trim TIMING only
   (native compacts at repartition; the editor keeps its 4118 and later drops exactly 279:
   frontier-repartition surfs peak 4833 → final 4554; native final 4553, d=-1). The editor
   reaches its final node count (10683) right after Pass 2; native's Pass-2 delta nearly matches
   (+1889 vs editor +1981), so the shipped +397 is the repartition's +489 minus Pass-2 cancellation.
   Discriminator for the next round: the world `FindBestSplit` soup sizes are near-identical —
   editor 6158 polys (`fbs_world_poly_order.py` capture,
   `2026-08-29-unatco-repart-live-diff/logs/fbs-world-poly-order-vandenberg-gas.log`) vs native
   6156 (`UEDCLI_REPART_FBS_DUMP`, root pick `best_i=4912` plane `(1,-0,-0,501)`) — so the
   mechanism is 2 soup polys and/or scoring/order inside the repartition recursion, the same
   diffuse-repartition class as UNATCO's old open problem.

## Vandenberg / corpus numbers (offline, cached goldens, d = native − golden)

Vandenberg: `+659/+7/+309` → **`+397/-1/+238`** (verts +6557→+3378, points +669→+435).

17-level cached-corpus A/B, same script both sides (`vdb_corpus_ab.py`; before = master `3d3bd78`,
after = `a7be107`): NO node/surf/leaf-exact level loses exactness (DX and NYC Bar stay 6/6
byte-identical — DX build sha unchanged). Wins: OceanLab `+390/+0/+86` → `+1/+0/+0`, Helibase
verts +94→+35, 747 verts +702→+632. Already-non-exact levels whose delta magnitude GREW (the
error-cancellation exposure precedent, same as this level's own `-6 → +659` history): Area51
`+85/+0/+51` → `-321/+0/-120`, NSFHQ `-92/+1/-26` → `-356/-2/-59`, TrainingFinal `-59/+0/-11` →
`+158/+0/-17`. Full tables: `logs/corpus-before.txt` / `logs/corpus-after.txt`.

## Harness

`harness/`: `vdb_lib.py` (cache paths + world-CSG list), `vdb_editor_trace.py` /
`vdb_editor_trace_pass2.py` (gdb per-brush captures; Pass-2 twin adds `bspRepartition`/`bspOptGeom`
breakpoints), `vdb_native_counts.py` (native `BRUSHSTATE` twin — now Pass 2 too),
`vdb_node_diff.py` / `vdb_attrib_planes.py` / `vdb_dump_brush_diffs.py` (bit-level plane diff +
per-brush attribution), `vdb_model_check.py` (the normal-rule validator), `vdb_brush_props.py`
(scaled/mirror/sheer census), `vdb_binary_normal.py` (original-.dx binary Polys reader),
`vdb_sintab_capture.py` / `vdb_sintab_formula.py` / `vdb_trig_probe.py` (live table dump + formula
identification), `vdb_corpus_ab.py` (offline corpus counts+sha sweep). Logs: `logs/` — count
traces, `sintab-live.bin`, and only the FINAL editor node dumps (`p1nodes/nfinal.bin`,
`p2nodes/nrepart1.bin`+`nfinal.bin`); the ~450MB of per-brush dumps stay uncommitted (re-capture
via the trace scripts).
