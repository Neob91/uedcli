# 85 — Hong Kong / WanChai Market generalization cross-check (native materialize vs a dense urban shipped level)

**Status:** measurement + diagnosis, CLOSED for this session. **Date:** 2026-07-19.
**Scope:** VALIDATION, not a fix. All native byte-parity tuning to date rides on the 95-brush
`Test_Castle.dx`, with a first generalization pass on the office-scale `03_NYC_UNATCOHQ` (§84). This
is the SECOND cross-check, against a **dense urban** shipped level packed with many small brushes —
**06_HongKong_WanChai_Market** — to see whether the two UNATCO findings (surf-set matches, BSP
over-splits, zones over-fragment) hold or flip on a level of a different *character*.
**Reproduce:** `harness/ingest_dx_trunk.py` (trunk) → `harness/build_native_hkmarket.py` (native
build) → `harness/ground_truth_bytediff.py NativeHKMarket.dx 06_HongKong_WanChai_Market.dx` (raw
on-disk diff). Nothing normalized; RAW bytes only.

### Confidence legend
✅ live-verified against the real `.dx` this session.

---

## 1. Trunk↔golden identity — DEFINITIONAL here, cross-checked by Brush count ✅

Unlike UNATCO (where a pre-existing trunk had to be matched to one of four candidate maps), this
trunk was **ingested directly FROM `06_HongKong_WanChai_Market.dx`** via `ingest_dx_trunk.py`, so
identity is definitional. Cross-checked by Brush-class export count anyway:

| | trunk | golden `.dx` |
|---|---:|---:|
| Brush actors | 1304 | **1305** |
| DeusExMover | 23 | 23 |
| brush-bearing total | 1327 | 1328 |
| Model exports | — | 1332 |

The single extra golden Brush is **`Brush2071`** — the level's active/builder brush (the LevelInfo
`Brush`, not a placed CSG actor), which UCC's `Level→T3D` batchexport omits by design. Every other
Brush name is present in both. Ingest qualified **8229 texture refs, 0 misses** across 2288 actors.

> **Ingest needed the sound/music dirs, not just Textures.** UCC `batchexport` demand-loads the
> level's whole package closure; HK Market references `Ambient.uax`/`MoverSFX.uax` (in `DX/Sounds`)
> and `HongKong_Music.umx` (in `DX/Music`), which are NOT under either Textures dir, so the UNATCO
> two-`--search`-dir invocation fails with a UCC load error (exit 1). The working call adds
> `--search DX/Sounds --search DX/Music`. (Also: `ingest_dx_trunk.py` had drifted from the current
> `ephemeral_build_container(state_dir=…)` API — it still passed the retired `repo_root=…` kwarg;
> fixed in the harness this session.)

## 2. The native build SUCCEEDS at dense-market scale ✅

`build_native_hkmarket.py` (default core `bspcsg`, **UNLIT**) built `DX/Maps/NativeHKMarket.dx`
(1,282,915 B) in **~26 s wall / 22.4 s user / 110 MB RSS**. No crash, no BuildError, all 17 Model
body sections emitted, the always-on offline self-check passed. This is the biggest brush count
thrown at the native core yet — **1330 brush-bearing actors, 8229 source polys** (vs UNATCO's 762 /
5545) — and it builds in seconds without OOM. Building at this density is itself a positive finding.
Built UNLIT deliberately: the native LIGHT-APPLY bake OOMs at DX scale (board 2026-07-17), and
geometry is lighting-independent. The **11,881 warnings are ALL `not in class schema (skipped)`**
tagged-property drops on DeusEx game classes (ATM, AmbientSound, …) — expected, non-fatal, and
touch actor props, NOT geometry. **Zero geometry/CSG warnings; no brush dropped.**

## 3. Ground-truth RAW byte diff — the honest numbers ✅

**Whole-body RAW:** native Model body **863,053 B** (unlit) vs editor **2,414,725 B**; positional
byte match over the common prefix = **131,843 / 863,053 = 15.28 %**. As with UNATCO this floor is
depressed by structural facts, not just geometry drift:
- **Unlit build.** Editor `LightMap`+`LightBits`+`Lights` = 134,174+297,007+41,203 = **472,384 B =
  19.6 % of the editor body** that native (unlit) does not emit.
- **Universal shift.** The first length-diff is `Vectors` (right after the 42-byte prefix), so every
  downstream section is byte-shifted — positional matching understates section-local similarity.
- **~2× geometry gap (NEW, see §4).** Unlike UNATCO, here native emits roughly HALF the geometry the
  editor does, so even a shift-corrected compare cannot approach parity — the section COUNTS
  themselves diverge ~2×.

**Per-section RAW map (native vs editor 06), with COUNTS:**

| section | nat len | ed len | **nat #** | **ed #** | equal | Δcount |
|---|---:|---:|---:|---:|:--:|---:|
| prefix | 42 | 42 | — | — | no | — |
| Vectors | 4478 | 5702 | **373** | **475** | no | **−21.5 %** |
| Points | 100635 | 205383 | **8386** | **17115** | no | **−51.0 %** |
| Nodes | 259225 | 569202 | **5428** | **11849** | no | **−54.2 %** |
| Surfs | 51996 | 100837 | **2664** | **5224** | no | **−49.0 %** |
| Verts | 270732 | 717732 | **78403** | **174179** | no | **−55.0 %** |
| NumSharedSides | 4 | 4 | 12492 | 43690 | no | — |
| NumZones / Zones | 1093 | 91 | **64** | **5** | no | **+1180 %** |
| field_0x54 (Polys) | 1 | 2 | — | — | no | — |
| LightMap (a8) | 1 | 134174 | 0 | 4470 | no | *(unlit)* |
| LightBits (b4) | 1 | 297007 | 0 | 297004 | no | *(unlit)* |
| Bounds (c0) | 59427 | 120977 | **2377** | **4839** | no | **−50.9 %** |
| LeafHulls (cc) | 99787 | 174183 | **24946** | **43545** | no | **−42.7 %** |
| Leaves | 15622 | 48178 | **1420** | **3800** | no | **−62.6 %** |
| Lights (e4) | 1 | 41203 | 0 | 32203 | no | *(unlit)* |
| trailing (RootOutside,Linked) | 8 | 8 | — | — | **YES** | — |

`LightMap`/`LightBits`/`Lights` native `#=0` is the UNLIT build, NOT a geometry defect. Object-table
ORDER differences (iActor / texture-ref numbering) are expected authoring-history divergence per
§82b and are NOT counted as defects.

## 4. GEOMETRY-generalization verdict — the UNATCO pattern PARTLY INVERTS ✅

Three findings, two of which **contradict** the UNATCO cross-check (§84). The castle-tuned core
still builds cleanly and completely at this scale, but its geometry does NOT generalize the way
UNATCO suggested — the divergence is **level-character-dependent, not a fixed bias**:

**(a) The surface SET does NOT match — Surfs −49.0 % (native 2664 vs editor 5224). THE headline
break.** UNATCO's clean result — "`Surfs` count is essentially exact (3581 vs 3589, −0.2 %), the
world-surface set generalizes; only the tree that carves them over-splits" — **FAILS here.** On the
dense market native produces roughly HALF the surfaces the editor keeps. This is a real
surface-generation divergence, not a mere BSP-balancing artifact, and it is the first thing to chase
for HK-market geometry parity.

**(b) The whole BSP is UNDER-built, not over-split — the OPPOSITE SIGN from UNATCO.** Native is
~−50 to −55 % across Nodes (−54.2 %), Verts (−55.0 %), Points (−51.0 %), Bounds (−50.9 %), Leaves
(−62.6 %), LeafHulls (−42.7 %), Vectors (−21.5 %). At UNATCO native was *over-split* (+9…+21 %); here
it is *under-built* by roughly half. So the sign of the BSP-count divergence flips between levels —
castle-tuned byte-parity work cannot predict even the *direction* of the gap on an unseen level.
Corroborating the absolute scale: native's HK body (863 KB) is actually SMALLER than native's UNATCO
body (1.05 MB) despite HK having **1.8× the brushes and 1.5× the source polys** — native is
collapsing far more of the dense, overlapping additive geometry than the editor does.

**(c) Over-zoning PERSISTS and is more extreme — 64 native zones vs 5 editor (+1180 %).** Same
kind as UNATCO (45 vs 7) but worse: the editor treats this whole market as nearly **single-zone**
(5 zones; neither trunk nor golden has any `ZoneInfo` actor, so all zones arise from portal
surfaces), while native fragments it into 64. The leaf `iZone` histogram is a broad spray across
dozens of small zones rather than one merged flood. Over-zoning is now confirmed on TWO independent
real levels — it is a **standing, level-independent** native defect (unlike the BSP-count sign, which
flips), and gameplay-affecting (zone render/sound/water).

**What the castle AND UNATCO both missed:** a level where the *surface set itself* halves and the BSP
*under-builds*. This did not appear at 95 brushes (castle) or at office scale (UNATCO); it takes a
dense level of **many small, tightly-packed, overlapping additive brushes** to surface it.

## 5. Root-cause note (NOT chased this session)

Diagnostics gathered, not pursued to a fix:
- **Additive-dominance alone is not the trigger.** Both levels are additive-dominant — HK 1035
  `CSG_Add` : 268 `CSG_Subtract` (≈3.9:1, 8229 polys); UNATCO 519 : 214 (≈2.4:1, 5545 polys) — yet
  UNATCO's surf set matched and HK's halves. The differentiator is **density** (many small
  overlapping additive brushes), not the add/subtract ratio.
- **No brushes were dropped and no geometry warning fired** — every one of the 1330 brush-bearing
  actors fed CSG; all 11,881 warnings are actor-prop schema skips. So the −49 % Surfs is native's
  CSG **merging/absorbing** overlapping coplanar surfaces the editor keeps as distinct — an
  incremental-`bspBrushCSG` fidelity gap on dense overlap, not a load/parse loss.

These are the leading suspects to chase for dense-level geometry parity; per the measurement remit
they were characterized, not fixed.

## 6. Playability
Not booted this session (native DX builds have a documented, separate load-hang blocker — §84 §5).
This run is geometry measurement only.

## 7. Reproduce
```
cd Tools/uedctl
# trunk (needs Sounds+Music dirs, not just Textures — see §1):
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ingest_dx_trunk.py \
    DX/Maps/06_HongKong_WanChai_Market.dx _scratch/hkmarket/uedctl/maps/hkmarket \
    --search DX/Textures --search DX/LUM/Textures --search DX/Sounds --search DX/Music
# native build (UNLIT) + raw diff:
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_native_hkmarket.py
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ground_truth_bytediff.py \
    DX/Maps/NativeHKMarket.dx DX/Maps/06_HongKong_WanChai_Market.dx
```
