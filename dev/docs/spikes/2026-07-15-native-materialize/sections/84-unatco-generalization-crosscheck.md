# 84 — UNATCO-HQ generalization cross-check (native materialize vs a real shipped level)

**Status:** measurement + diagnosis, CLOSED for this session. **Date:** 2026-07-18.
**Scope:** VALIDATION, not a fix. All native byte-parity tuning to date rides on the 95-brush
`Test_Castle.dx`. This is the occasional cross-check against a REAL, much larger shipped level —
**03_NYC_UNATCOHQ** — to see how the castle-tuned core generalizes on deterministic geometry.
**Reproduce:** `harness/build_native_unatco.py` (native build) → `harness/ground_truth_bytediff.py
NativeUnatco.dx 03_NYC_UNATCOHQ.dx` (raw on-disk diff). Nothing normalized; RAW bytes only.

### Confidence legend
✅ live-verified against the two real `.dx` this session.

---

## 1. Which shipped map is the golden — and how it was confirmed ✅

The trunk `_scratch/unatco/uedctl/maps/unatco` (1437 actors) was ingested from **one** of
`DX/Maps/0{1,3,4,5}_NYC_UNATCOHQ.dx`. Pinned to **`03_NYC_UNATCOHQ.dx`** by the **Brush-class
export count**, which is exact and unambiguous:

| map | Brush exports | Model exports |
|---|---|---|
| 01 | 721 | 749 |
| **03** | **734** | **763** |
| 04 | 735 | 764 |
| 05 | 730 | 760 |

The trunk has **734 `Brush`-class actors** (+ 28 `DeusExMover`, 1437 actors total) — matches ONLY
03. Corroborated: Model count 763 = 762 brush-bearing actors + 1 level model; trunk 1437 actors ≈
03's 1442 actor-ish exports (the ~5 gap is `Level`/`LevelSummary`/embedded palettes, which aren't
trunk actors). Neither trunk nor golden contains any `ZoneInfo` actor (relevant to §4).

## 2. The native build SUCCEEDS at UNATCO scale ✅

`build_native_unatco.py` (default core `bspcsg`, **UNLIT**) built `DX/Maps/NativeUnatco.dx`
(1,308,597 B) in **~14 s wall / 107 MB RSS**. No crash, no BuildError, all 17 Model body sections
emitted, the always-on offline self-check passed. Built UNLIT deliberately: the native LIGHT-APPLY
bake OOMs at DX scale (board/inbox 2026-07-17), and geometry is lighting-independent — this
cross-check is about geometry. The ~9,357 warnings are all `not in class schema (skipped)`
tagged-property drops on DeusEx game classes (ATM, AllianceTrigger, AmbientSound, …) — expected and
non-fatal; they touch actor props, not geometry.

> The `build_geometry_bspcsg` core is the only viable functional path at this scale; the default
> point-in-solid oracle (`build_geometry_from_brushes`) never finished in >45 min on this trunk
> (board note). `run_materialize_native` already defaults to `core="bspcsg"`.

## 3. Ground-truth RAW byte diff — the honest numbers ✅

**Whole-body RAW:** native Model body **1,056,399 B** (unlit) vs editor **1,541,036 B**; positional
byte match over the common prefix = **160,844 / 1,056,399 = 15.23 %**. This floor is depressed by two
structural facts, not just geometry drift:
- **Unlit build.** The editor body's `LightMap`+`LightBits`+`Lights` = 99,877+468,148+31,628 =
  **599,653 B = 38.9 % of the editor body** that native (unlit) simply does not emit. Even a
  byte-perfect *geometry* build tops out well under 62 % positional here.
- **Universal shift.** The first length-diff is the `Vectors` section (right after the 42-byte
  prefix), so every downstream section is byte-shifted — positional matching understates true
  section-local similarity (cf. the castle's per-section triage in §82b).

**Per-section RAW map (native vs editor 03), with COUNTS:**

| section | nat len | ed len | **nat #** | **ed #** | equal | Δcount |
|---|---:|---:|---:|---:|:--:|---:|
| prefix | 42 | 42 | — | — | no | — |
| Vectors | 8342 | 7154 | **695** | **596** | no | +16.6 % |
| Points | 126591 | 116055 | **10549** | **9671** | no | +9.1 % |
| Nodes | 301280 | 248077 | **6297** | **5188** | no | +21.4 % |
| Surfs | 69522 | 69670 | **3581** | **3589** | no | **−0.2 %** |
| Verts | 331588 | 305169 | **91481** | **82487** | no | +10.9 % |
| NumSharedSides | 4 | 4 | 65279 | 60138 | no | — |
| NumZones / Zones | 765 | 119 | **45** | **7** | no | **+543 %** |
| field_0x54 (Polys) | 1 | 2 | — | — | no | — |
| LightMap (a8) | 1 | 99877 | 0 | 3325 | no | *(unlit)* |
| LightBits (b4) | 1 | 468148 | 0 | 468145 | no | *(unlit)* |
| Bounds (c0) | 88227 | 78552 | **3529** | **3142** | no | +12.3 % |
| LeafHulls (cc) | 101695 | 88351 | **25423** | **22087** | no | +15.1 % |
| Leaves | 28327 | 28176 | **2575** | **2266** | no | +13.6 % |
| Lights (e4) | 1 | 31628 | 0 | 23923 | no | *(unlit)* |
| trailing (RootOutside,Linked) | 8 | 8 | — | — | **YES** | — |

`LightMap`/`LightBits`/`Lights` native `#=0` is the UNLIT build, NOT a geometry defect. Object-table
ORDER differences (iActor / texture-ref export/import numbering) are expected authoring-history
divergence per §82b and are NOT counted as defects.

## 4. GEOMETRY-generalization verdict ✅

**The castle-tuned core HOLDS structurally at 8× the brush count — it builds, it's complete, and it
is dimensionally in the right ballpark — but two things the near-single-zone castle never exercised
surface at scale:**

**(a) Zone count blows up — 45 native vs 7 editor (+543 %). THE headline generalization break.**
Neither trunk nor golden has any `ZoneInfo` actor, so all 7 editor zones arise from portalization of
portal-flagged surfaces. Native over-zones by ~6.4×: the leaf `iZone` histogram is one dominant zone
(zone 2 = 1263 leaves, zone 1 = 240) plus a long tail of ~40 tiny zones (many with just 1–2 leaves).
The castle is effectively single-zone, so its portalization/zone-flood path was never stress-tested;
at UNATCO scale the native zone assignment fragments the world instead of merging connected leaves.
This is a real divergence with gameplay consequences (zone rendering/sound/water) and is the first
thing to chase for functional UNATCO parity.

**(b) BSP is uniformly over-split — ~+9 to +21 % across nodes/verts/points/leaves/bounds/leafhulls.**
Nodes +21.4 %, Vectors +16.6 %, LeafHulls +15.1 %, Leaves +13.6 %, Bounds +12.3 %, Verts +10.9 %,
Points +9.1 %. The native BSP builds a less-optimal (more-split) tree than the editor — a
CSG/BSP-balancing difference that is negligible on the tiny castle but compounds at scale. Note this
is not a soup mismatch in kind: **`Surfs` count is essentially exact (3581 vs 3589, −0.2 %)** — the
set of world surfaces generalizes cleanly; it's the *tree that carves them* that over-splits.

**Nothing crashed, no count is wildly wrong, no pass failed to scale (14 s build).** The generalization
gaps are: over-zoning (structural, ~6×) and BSP over-split (uniform, low-double-digit %). Byte-parity
work tuned on the castle will not reveal either — they need a real multi-zone level in the loop.

## 5. Playability

Not re-booted this session. The board records (2026-07-17, still open) that a native-built UNATCO
`.dx` does **not** become playable — `--game` travel never possesses a pawn and the warm-container
link goes dead at LOAD, while shipped `03_NYC_UNATCOHQ.dx` travels fine in the same container — so
the failure is our build, diagnosed as a load-time hang needing a `DeusEx.log` capture. That blocker
is unchanged by this measurement; the over-zoning in §4(a) and the known collision-hull-leak
suspicion are the leading candidates. Re-running the boot would only re-confirm a documented,
recent blocker, so it was not repeated here.

## 6. Reproduce
```
cd Tools/uedctl
. "$HOME/.cargo/env" && .venv/bin/maturin develop --release -m uedctl-native/Cargo.toml
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_native_unatco.py
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/ground_truth_bytediff.py \
    DX/Maps/NativeUnatco.dx DX/Maps/03_NYC_UNATCOHQ.dx
```
