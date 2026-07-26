# 89 — The UnrealEd-golden pipeline (the correct native-parity basis)

**Status:** infrastructure landed + first measurement. **Date:** 2026-07-19.
**Scope:** establish and PROVE the corrected parity basis — native `level materialize` output judged
against **UnrealEd's OWN build of the SAME trunk**, not the hand-authored shipped `.dx`.
**Harness:** `harness/build_ued_golden.py` (golden builder) + `harness/ground_truth_bytediff.py`
(raw byte diff) + `harness/bsp_health_check.py` (structural validity).

> **⚠️ CORRECTION (2026-07-19, see [§91 §9](91-leaves-overproduction.md)).** The `MAP REBUILD`-only
> pipeline this section landed builds a golden with a **STALE, non-1:1 `Leaves` array** (and an
> under-built `Verts` pool) at UNATCO scale: `MAP REBUILD` runs csgRebuild+bspBuild but NOT the
> visibility/leaf pass (`AssignLeaves`), which is gated on the `BSP REBUILD … ZONES` keyword. So the
> §2 claim "passes every `bsp_health_check.py` structural assertion / valid, complete" and the §3
> per-count deltas (Leaves 762 / "native 3.6×", Verts +24 %, Zones +2) are **against a CORRUPT
> golden** — superseded. The fixed pipeline is the **two-step** `MAP REBUILD; BSP REBUILD OPTIMAL
> OPTGEOM ZONES` (now `build_ued_golden.py`'s default), and `bsp_health_check.py` now asserts
> refs/leaf==1.0. The corrected deltas are in §91 §9.4: **Leaves native −6 % (both 1:1), Verts native
> −3.5 %, Zones EQUAL (9=9); the ONLY real residual is Vectors +24 %.** The §5 "fold the idle-barrier
> back into production" follow-up still stands, but production must issue the two-step full rebuild,
> not a bare `MAP REBUILD`.

### Confidence legend
✅ live-verified this session against real editor builds and real `.dx`.

---

## 1. Why the basis changed ✅

Native parity was long measured against the shipped `03_NYC_UNATCOHQ.dx` (§84). That is an UNFAIR
golden: the shipped map is **hand-authored, built incrementally** (each brush CSG'd into the tree as
it was placed over the level's authoring history), and carries authoring-order state (object-table /
export order, `iActor`, texture-import order) a trunk cannot reproduce. A byte diff against it
conflates real native geometry drift with (a) pure object renumbering and (b) the incremental-vs-batch
build difference. The **correct** golden is UnrealEd building **our trunk**, the same input native
consumes: `MAP NEW` → re-add the trunk's actors → `MAP REBUILD` → (`LIGHT APPLY`) → `MAP SAVE`.

**§2 below proves this matters:** UnrealEd building our trunk vs the shipped map — *same tool, same
734 brushes* — still differ by **+21.7 % nodes and −66 % leaves**. Two-thirds of the leaf divergence
§84 blamed on native was actually the incremental-vs-batch build gap.

## 2. Does UnrealEd build our trunk HEADLESS? — YES, with one fix ✅

**Yes.** A per-command ephemeral UED22 editor (`editor.ensure_editor`) built the 734-brush UNATCO
world trunk deterministically: OBJ-LOAD 20 texture packages → `MAP NEW` → paste 734 brushes →
`MAP REBUILD` (idle ~29 s) → `MAP SAVE` → a **1,772,217-byte** `.dx`. Two independent runs produced
**byte-identical** output, and the result passes every `bsp_health_check.py` structural assertion
(child/leaf/zone/surf ranges in bounds, no BSP cycles, node-reachability 74 % — on par with
native 73 % and shipped 77 %). So the golden is a **valid, complete, reproducible** build.

**THE BLOCKER (and the fix — the load-bearing infra finding).** The production
`apply.run_materialize` path does NOT build a real level headless at scale. The editor driver's
`wine_ctl exec` **fires a console command and returns after ~0.3 s** — it never waits for the command
to finish. On the 95-brush castle a `MAP REBUILD` completes inside that window, so `run_materialize`
works and is integration-green. On UNATCO (734 brushes) the rebuild takes tens of seconds;
`run_materialize` fires `MAP REBUILD`, then immediately `LIGHT APPLY` / `MAP SAVE` / `docker cp`, and
the cp fails — *"materialize failed (nothing written)"* — because the `.dx` does not exist yet. First
attempt reproduced exactly this.

`build_ued_golden.py` fixes it by driving the editor itself (the same library helpers:
`ensure_editor`, `ensure_load`, `writes._re_add`, `xfer`) with a **CPU-idle barrier** (`_wait_idle`,
polling `docker stats`) after the paste, the rebuild and the light bake, plus a saved-file-stable
wait before `docker cp`. The quiet window must be **generous** (≥8 consecutive sub-8 % reads): a
too-short window fires during an inter-phase CPU lull mid-rebuild and `MAP SAVE` then captures a
partially-built tree (observed once: 762 leaves at 2 quiet reads — here coincidentally the *correct*
count, but the failure mode is real; a truncated Leaves array is the tell).

> **Generalization / cost.** ~30 s of editor drive per level at UNATCO scale; no crash, no wedge.
> The path is O(brush count) and should hold across OG levels; the only per-level input is the trunk.
>
> **`--world-only` is REQUIRED for a faithful geometry golden — a full-trunk build is contaminated.**
> OG trunks name actor classes BARE (`Class=DeusExMover`); with no v69 stub for `DeusEx.u` the editor
> cannot resolve them. Point actors then just fail to import (harmless — they never carve CSG). But a
> **`DeusExMover` carries a brush**, and `_re_add` pastes any brush-bearing actor as a brush — so an
> unresolved mover is pasted as a **plain world brush and CSG'd into the level**, inflating the world
> Model (measured: full-trunk golden nodes 7669 / surfs 3860 vs world-only 6314 / 3616 — the 28
> movers added ~244 surfaces that a real build keeps in a SEPARATE mover model). A full+lit golden is
> ALSO under-lit: only engine `Class=Light` imports, so the DX-specific light-emitting actors are
> skipped (golden bakes 17506 light entries vs the shipped map's 23923). **Therefore the canonical
> golden is `--world-only --no-light`** (just `Brush`+`LevelInfo`, unlit) — exactly the 734 CSG
> brushes native's level Model is built from, no mover/lighting contamination. The full+lit golden is
> kept only as a rough lit reference, not a parity target.

## 3. Native vs the UED golden — THE goal metric (RAW bytes) ✅

`Native_unatco.dx` (unlit, current `bspcsg` core) vs `UEDGolden_unatco_world.dx` (UnrealEd, world,
unlit) — both unlit, so lighting sections are empty on *both* sides (a fair compare, unlike §84):

| section | native # | UED-golden # | Δ | note |
|---|---:|---:|---:|---|
| Vectors | 745 | 599 | **+24.4 %** | native over-produces plane vectors |
| Points | 10744 | 10752 | **−0.07 %** | **near-exact** |
| Nodes | 6425 | 6314 | +1.8 % | close |
| Surfs | 3698 | 3616 | +2.3 % | close |
| Verts | 94766 | 76488 | **+23.9 %** | native over-produces FVerts |
| NumZones | 9 | 7 | +2 | native slightly over-zones |
| Bounds | 3649 | 3641 | **+0.2 %** | **near-exact** |
| LeafHulls | 24926 | 25084 | −0.6 % | **near-exact** |
| Leaves | 2759 | 762 | **native 3.6×** | headline divergence |
| trailing | — | — | = | byte-identical |

**Compiled byte parity = 0.00 %** of the golden body sits in fully byte-identical sections (only the
three empty lighting sections + the 8-byte trailing match to the byte). Every populated section
differs on raw bytes — expected: the first length difference is `Vectors`, so all downstream sections
are byte-shifted, and the ref-bearing sections (Surfs/Zones) also carry each file's own object-table
numbering. RAW byte parity is therefore a floor, not the useful signal at this stage; the **per-count
deltas** above are. Native is dimensionally very close on Points/Bounds/LeafHulls/Nodes/Surfs but
**over-splits Leaves 3.6×** and over-produces Vectors/Verts ~+24 % — i.e. native builds a
*less-merged* BSP than UnrealEd's `GOOD` rebuild of the identical brushes. This is a cleaner, more
actionable target than §84's native-vs-shipped (which mixed in authoring history).

## 4. UED golden vs shipped `.dx` — validates the methodology ✅

`UEDGolden_unatco_world.dx` vs shipped `03_NYC_UNATCOHQ.dx` — *same tool (UnrealEd), same 734
brushes*, differing ONLY in build procedure (our one-shot batch `MAP REBUILD` vs the shipped map's
incremental authoring) + our world-only/unlit trim:

| section | UED-golden # | shipped # | Δ |
|---|---:|---:|---:|
| Vectors | 599 | 596 | **+0.5 %** (same brush set) |
| NumZones | 7 | 7 | **identical** (only the zone actor-ref bytes differ) |
| Points | 10752 | 9671 | +11.2 % |
| Nodes | 6314 | 5188 | **+21.7 %** |
| Surfs | 3616 | 3589 | +0.8 % |
| Verts | 76488 | 82487 | −7.3 % |
| Bounds | 3641 | 3142 | +15.9 % |
| LeafHulls | 25084 | 22087 | +13.6 % |
| Leaves | 762 | 2266 | **−66.4 %** |
| LightMap/LightBits/Lights | 0 / 0 / 0 | 3325 / 468145 / 23923 | shipped is lit; golden `--no-light` |

**The point:** two UnrealEd builds of the identical geometry diverge by **+21.7 % nodes / −66 %
leaves / +15.9 % bounds**, purely from batch-rebuild vs incremental-authoring. That is a large slice
of the gap §84 attributed to native. Judging native against the shipped map penalised it for a
difference that is UnrealEd-vs-UnrealEd. The batch-built golden is the apples-to-apples target,
because native also builds in one batch.

## 5. Reproduce
```
cd Tools/uedcli
# native (unlit) from the trunk
.venv/bin/python -c "from pathlib import Path; from uedcli import trunk; from uedcli.native import materialize as M; \
  lvl,_=trunk.read_level(Path('_scratch/unatco/uedcli/maps/unatco')); \
  M.run_materialize_native(level=lvl, out_path='_scratch/uedgolden/Native_unatco.dx', overwrite=True, version=68, no_light=True, \
  pkg_dirs=['/home/neob91/Games/LutrisDX/drive_c/DX/Textures','/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures'])"
# UnrealEd golden (world, unlit) from the SAME trunk — RUN AS A BOUNDED BACKGROUND JOB
.venv/bin/python -u dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
  --trunk _scratch/unatco/uedcli/maps/unatco --out _scratch/uedgolden/UEDGolden_unatco_world.dx \
  --world-only --no-light --overwrite
# the goal metric, and the methodology-validation diff
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ground_truth_bytediff.py \
  _scratch/uedgolden/Native_unatco.dx _scratch/uedgolden/UEDGolden_unatco_world.dx
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ground_truth_bytediff.py \
  _scratch/uedgolden/UEDGolden_unatco_world.dx /home/neob91/Games/LutrisDX/drive_c/DX/Maps/03_NYC_UNATCOHQ.dx
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/bsp_health_check.py \
  _scratch/uedgolden/UEDGolden_unatco_world.dx
```
Outputs (all under the gitignored `_scratch/uedgolden/`, editor-built maps never enter the tree).

## 6. Follow-ups (to inbox)
- **Native over-splits Leaves 3.6× vs UnrealEd's `GOOD` batch rebuild** (2759 vs 762) and
  over-produces Vectors/Verts ~+24 %. This is now the sharpest geometry target — chase against the
  golden, not the shipped map. (The near-exact Points/Bounds/LeafHulls say the geometry SOUP is
  right; the *tree that carves it* over-splits.)
- **A faithful FULL golden needs the `DeusEx.u` v69 stub built** (empty stub cache here). With it,
  movers resolve to their real class and go into a separate mover model instead of contaminating the
  world CSG, and DX light actors import so `LIGHT APPLY` bakes the real light set — turning the full
  golden into a proper lit + mover-complete reference. Until native lighting stops OOMing at DX scale
  (board 2026-07-17), native stays unlit and only the `--world-only --no-light` golden is the parity
  target anyway.
- **Fold the idle-barrier back into production?** `apply.run_materialize` cannot build a real level
  headless without it; either the driver's `exec` should optionally wait-for-idle, or `run_materialize`
  should barrier before `MAP SAVE`. Filed for the owning session (do not edit the concurrent file here).
