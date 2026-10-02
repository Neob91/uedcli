# 86 — Paris-Catacombs generalization cross-check (heavy-overlapping-SUBTRACT stress test)

**Status:** measurement + diagnosis, CLOSED for this session. **Date:** 2026-07-19.
**Scope:** VALIDATION, not a fix. Sibling of §84 (UNATCO). All native byte-parity tuning to date
rides on the 95-brush `Test_Castle.dx`; §84 cross-checked the castle-tuned core on the 734-brush
**03_NYC_UNATCOHQ**. This section pushes further — onto **10_Paris_Catacombs**, dense underground
tunnels carved by **heavily-overlapping SUBTRACT brushes** (1283 Brush actors, ~1.75× UNATCO), the
hardest case for the CSG tree + T-junction handling. **Reproduce:** `harness/ingest_dx_trunk.py`
(offline UCC batchexport → trunk) → `harness/build_native_catacombs.py` (native UNLIT build) →
`harness/ground_truth_bytediff.py NativeCatacombs.dx 10_Paris_Catacombs.dx`. Nothing normalized;
RAW on-disk bytes only.

### Confidence legend
✅ live-verified against the two real `.dx` this session.

---

## 1. Which shipped map is the golden — and how it was confirmed ✅

The trunk `_scratch/catacombs/uedcli/maps/catacombs` (2710 actors) was ingested from
**`DX/Maps/10_Paris_Catacombs.dx`**. Trunk↔golden identity pinned by the **Brush-class export
count**, which is exact and unambiguous:

| map | Brush exports | Model exports | DeusExMover |
|---|---:|---:|---:|
| **10_Paris_Catacombs** | **1283** | **1315** | **18** |
| 10_Paris_Catacombs_Tunnels | 568 | 583 | 14 |

The trunk has **1283 `Brush`-class actors + 18 `DeusExMover`** — matches ONLY the non-`_Tunnels`
map. Corroborated: Model count 1315 = 1314 brush-bearing trunk actors + 1 level model. Ingest
qualified **9984 texture refs, 0 misses** (all `Texture=` package qualifiers recovered from the
`.dx` import table). The golden IS a genuine multi-zone level (17 editor zones, §4) — unlike the
near-single-zone castle.

### Ingest note — search dirs and a harness API-drift fix (both pre-existing, not this section's)
UCC batchexport demand-loads every imported package. Beyond the two Textures dirs the UNATCO ingest
used, the catacombs map imports **sound/music content** not on that path — it fails fast with
`Can't find file for package 'Ambient'` until `DX/Sounds` (`Ambient.uax`, `MoverSFX.uax`),
`DX/Music` (`ParisCathedral_Music.umx`) — and, defensively, `DX/System` — are added as `--search`
dirs. (The 22 other top-level imports — `Effects`, `Catacombs`, `NYCBar`, `Constructor`,
`FreeClinic`, `CoreTex*`, `Paris`, … — are all `.utx` textures already covered.) Separately,
`ingest_dx_trunk.py` had drifted from the current `ephemeral_build_container` signature (`repo_root=`
→ `state_dir=`, config-state-dir refactor); a concurrent agent's working-tree fix was in place and
used as-is.

## 2. The native build SUCCEEDS at catacombs scale ✅ — building at all is the headline

`build_native_catacombs.py` (default core `bspcsg`, **UNLIT**) built `DX/Maps/NativeCatacombs.dx`
(2,777,937 B) in **61 s wall / 60 s user / 176 MB RSS**. **No crash, no `BuildError`, no CSG
degenerate/hang**, all 17 Model body sections emitted, the always-on offline self-check passed. Built
UNLIT deliberately: the native LIGHT-APPLY bake OOMs at DX scale (board/inbox 2026-07-17), and
geometry is lighting-independent. The **16,949 warnings are all `not in class schema (skipped)`**
tagged-property drops on DeusEx game classes — expected, non-fatal, actor-props not geometry.

> **The heavy-overlapping-SUBTRACT tunnels did NOT trip the CSG.** The predicted worst-case (a CSG
> divergence / degenerate / hang on subtract density) did **not** materialize: the incremental
> `build_geometry_bspcsg` core carved 1283 brushes to a complete, self-consistent BSP in ~1 min at a
> modest RSS. Building the densest overlapping-subtract retail level clean is itself the finding.

## 3. Ground-truth RAW byte diff — the honest numbers ✅

**Whole-body RAW:** native Model body **2,325,914 B** (unlit) vs editor **3,608,017 B** (Δ
−1,282,103); positional byte match over the common prefix = **378,330 / 2,325,914 = 16.27 %**. As at
UNATCO, this floor is depressed by two structural facts, not just geometry drift:
- **Unlit build.** The editor body's `LightMap`+`LightBits`+`Lights` = 181,734+1,302,234+57,936 =
  **1,541,904 B = 42.7 % of the editor body** that native (unlit) simply does not emit.
- **Universal shift.** The first length-diff is `Vectors` (right after the 42-byte prefix), so every
  downstream section is byte-shifted — positional matching understates true section-local similarity.

**Per-section RAW map (native vs editor 10_Paris_Catacombs), with COUNTS:**

| section | nat len | ed len | **nat #** | **ed #** | equal | **Δcount** |
|---|---:|---:|---:|---:|:--:|---:|
| prefix | 42 | 42 | — | — | no | — |
| Vectors | 9830 | 8570 | **819** | **714** | no | **+14.7 %** |
| Points | 259203 | 234843 | **21600** | **19570** | no | +10.4 % |
| Nodes | 639164 | 550814 | **13234** | **11420** | no | +15.9 % |
| Surfs | 135324 | 127246 | **6927** | **6491** | no | **+6.7 %** |
| Verts | 857137 | 743813 | **202265** | **174458** | no | +15.9 % |
| NumSharedSides | 4 | 4 | **29039** | **25358** | no | +14.5 % |
| NumZones / Zones | 563 | 291 | **33** | **17** | no | **+94.1 %** |
| field_0x54 (Polys) | 1 | 2 | — | — | no | *(ref vs null)* |
| LightMap (a8) | 1 | 181734 | 0 | 6048 | no | *(unlit)* |
| LightBits (b4) | 1 | 1302234 | 0 | 1302230 | no | *(unlit)* |
| Bounds (c0) | 165727 | 150302 | **6629** | **6012** | no | +10.3 % |
| LeafHulls (cc) | 201339 | 193287 | **50334** | **48321** | no | +4.2 % |
| Leaves | 57565 | 56887 | **5233** | **4485** | no | +16.7 % |
| Lights (e4) | 1 | 57936 | 0 | 40269 | no | *(unlit)* |
| trailing (RootOutside,Linked) | 8 | 8 | — | — | **YES** | — |

`LightMap`/`LightBits`/`Lights` native `#=0` is the UNLIT build, NOT a geometry defect. Object-table
ORDER differences (iActor / texture-ref export/import numbering) are expected authoring-history
divergence per §82b and are NOT counted as defects. Native leaf `iZone` histogram: `{2:3333, 1:1120,
4:364, 3:111}` + a long tail of ~29 singleton zones (§4).

## 4. GEOMETRY-generalization verdict ✅

**The castle-tuned core HOLDS structurally at the densest retail subtract geometry — it builds
clean, complete, and dimensionally close — and it reproduces the two §84 gaps, but it ALSO surfaces a
NEW one the castle+UNATCO never did: the world SURFACE SET itself diverges.**

**(a) NEW — the surface SET diverges: Surfs +436 (+6.7 %). The heavy-subtract-specific break.**
On the castle `Surfs` was **485 = 485 exact**; at UNATCO it was **3581 vs 3589 (−0.2 %)** — the
*set of world surfaces* generalized cleanly and only the *tree carving them* over-split. **Here native
emits MORE surfaces than the editor (6927 vs 6491).** Overlapping SUBTRACT brushes are exactly where
CSG must decide coplanar-merge / T-junction / fragment questions, and native fragments the world
surface set differently (extra splits and/or under-merged coplanars) than UnrealEd's `bspBrushCSG`.
This is no longer "same surfaces, over-split tree" — the surface set generalizes *less* cleanly under
subtract density. **First thing to chase for catacombs geometry parity, and the reason to keep a
heavy-subtract level in the loop.**

**(b) Over-zoning persists — 33 native vs 17 editor (+94 %).** Same pathology as UNATCO's 45-vs-7,
milder ratio (~1.9× vs ~6.4×) but on a genuinely multi-zone golden: native assigns 2 dominant zones
(leaves 3333 + 1120) plus medium zones (364, 111) plus a long tail of ~29 tiny/singleton zones,
where the editor merges connectivity into 17. The native zone-flood fragments connected leaves
instead of merging them — real divergence with gameplay consequences (zone rendering/sound/water).

**(c) BSP over-split — uniform +10 to +17 %, NOT worse than UNATCO despite the subtract density.**
Leaves +16.7 %, Nodes +15.9 %, Verts +15.9 %, Vectors +14.7 %, NumSharedSides +14.5 %, Points
+10.4 %, Bounds +10.3 %, LeafHulls +4.2 %. This band is comparable to UNATCO's (+9…+21 %) — the
subtract density did **not** blow up the tree-split gap. So the extra hardness of catacombs shows up
in **(a) the surface set**, not in a worse over-split. The BSP-balancing difference is stable across
scale and geometry style; the surface-set fragmentation is the newly-exposed lever.

**Nothing crashed, no count is wildly wrong, no CSG degenerate, no pass failed to scale (61 s
build).** Generalization gaps, in priority order: **(a) surface-set fragmentation under overlapping
subtracts (NEW, heavy-subtract-specific)**, (b) over-zoning (structural, ~1.9×), (c) uniform BSP
over-split (stable ~+15 %). Byte-parity work tuned on the castle reveals none of these; (a) needs a
heavy-subtract level in the loop.

## 5. Playability
Not booted this session (measurement + geometry diagnosis only, matching §84 §5). A native-built DX
`.dx` is a known-open playability blocker (board 2026-07-17, load-time hang); unchanged by this
measurement. The over-zoning §4(b) and surface-set §4(a) divergences are the leading geometry
suspects; re-booting would only re-confirm a documented blocker.

## 6. Reproduce
```
cd Tools/uedcli
# 1. ingest trunk from the shipped map (offline UCC; needs Sounds/Music/System search dirs)
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ingest_dx_trunk.py \
    /home/neob91/Games/LutrisDX/drive_c/DX/Maps/10_Paris_Catacombs.dx \
    /home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/catacombs/uedcli/maps/catacombs \
    --search DX/Textures --search DX/LUM/Textures \
    --search DX/Sounds --search DX/Music --search DX/System
# 2. native UNLIT build (rebuild core first if src changed:
#    . "$HOME/.cargo/env" && .venv/bin/maturin develop --release -m uedcli-native/Cargo.toml)
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_native_catacombs.py
# 3. raw on-disk diff
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ground_truth_bytediff.py \
    DX/Maps/NativeCatacombs.dx DX/Maps/10_Paris_Catacombs.dx
```
