+++
priority = "p1"
kind = "implement"
summary = "HANDOFF — N-4 LIGHTMAP BAKE + lit-render crash: BOTH DONE (RESOLVED 2026-07-16)"
+++

# HANDOFF — N-4 LIGHTMAP BAKE + lit-render crash: BOTH DONE (RESOLVED 2026-07-16)

p1.
✅ **Lit maps now render clean** — root cause was `FBspSurf` on-disk **field order**: `iLightMap` and
`iActor` were serial-swapped (we wrote `iActor` in slot 7, `iLightMap` last; real maps DXOnly/DX/Entry
do the reverse). The game read `iLightMap` from our `iActor` value (`7`, a brush ref) → out-of-range
`Model.LightMap[7]` (only 6 records) → garbage `iLightActors` → bad `Model.Lights[]` pointer → the
`c0000005` AV in `AddLight` (`Render.dll 0x10b08b4a`, 254/254 exceptions). Fixed in `umodel._enc_surf`/
`_parse_surf` + Rust `model_write.rs::put_surf` (swap `i_light_map`/`i_actor` to the verified order);
156 tests pass; `+seh` re-measure of NativeLit = **0 AVs** (was 254). The earlier "FP singularity"
(§13) was a RED HERRING — see spike section 20 §14 for the full correction. The N-4 bake itself was
byte-correct all along. ✅ **DONE (2026-07-16):** `run_materialize_native` now defaults
`no_light=False` (lit); the **real castle** (161 actors → 418 lit surfs, 90 brushes, real LUM
textures) boots to `READY map=NativeCastle`, **0 texture errors, 0 singularities** — the fix
generalizes. Fixing the castle also required TWO asset-wiring fixes (spike §15): texture imports now
carry the GROUP (`LUM_CoreTex.Concrete.concrete_02`) and `ClassPackage=Engine` (both were wrong;
`native/pkgref.py` + `run_materialize_native(pkg_dirs=…)`), and `game-entrypoint.sh` now wires a
project OVERLAY (`/overlay` = `DX/LUM`) so custom `LUM_*` packages resolve. ⚠️ The original "needs a
fuller Model" and "FP singularity" framings below are SUPERSEDED (kept for history).
**N-4 is built + tested + committed:**
`uedcli-native/src/light.rs` (the `LIGHT APPLY` bake, rayon) + `linecheck.rs` (the `UModel::
LineCheck` BSP shadow ray) are real now; FFI `bake_lighting(built, lights)`; Python orchestration
collects participating lights, bakes, and `assemble._patch_light_refs` rewrites the `Lights` array
light-indices → export refs. Output is **byte-format-correct vs real maps** (decoded `NativeLit.dx`
beside `00_Intro.dx`: same unit basis, `FLightMapIndex` shape, `N×⌈U/8⌉×V` bit sizing, light-ref +
NULL runs). The map **loads + the pawn stands**. Regression tests + the gate-5 dual-serializer
cross-check pass; whole offline suite green (1159). **BLOCKER (fully characterized live, spike
`sections/20-lighting-bake.md` §11):** the DeusEx **software renderer** faults per-frame on ANY
lightmapped surface — `Render.dll FLightManager::SetupForSurf → SetupNormalSurface`, logged as
"Anomalous singularity in URender::DrawWorld" (headless game survives; screenshots black). Isolated:
`NativeUnlit` (no lightmaps) renders CLEAN; `NativeDark` (all-DARK records, no bits/lights) CRASHES;
real `DXOnly` (also dark records) renders CLEAN. The difference is **Model completeness** — real maps
have `num_shared_sides>0` + real vert `iSide` + real node **Bounds** (`iColl/iRend>=0`); our native
build ships the MINIMAL Model (empty Bounds, `iSide=-1`, `num_shared_sides=0`). The UNLIT path
tolerates it (why `NativeCSG` renders), the LIT path does not. **So `run_materialize_native` now
defaults `no_light=True`** (renderable unlit build); the bake is opt-in `no_light=False`. **NEXT
SLICE (own item below):** decode `Render.dll` `SetupNormalSurface`/`SetupForSurf` (base
`0x10b00000`; `SetupNormalSurface` guard str @ VA `0x10b2a350`, code @ `0x10b07136`) to pin whether
node **Bounds** (`bspBuildBounds` proper + serialize the `c0`/`cc` arrays our writer drops) or the
**`bspOptGeom` side pool** (or both) is the requirement, then port the minimum. Repro maps at
`DX/Maps/Native{Lit,Dark,Unlit}.dx` (scratch `_scratch/build_litcsg.py`).
**Collision-fix (commit aa243e38e) review-gate findings — ✅ ALL RESOLVED 2026-07-15:**
(1) `50-…md` §1.2 + the §4.3 table rows now annotate the front/back inversion + NF_IsNew as "benign
for RENDER but ARE the COLLISION bug, see §60"; (2) `60-…md` §4/§7 now record the live result
(`phys=Walking`, `z=-134` stable) instead of framing it as an open gate; (3) `60-…md` §5 iZone disasm
corrected to the BYTE read `mov al,[eax+esi+0x34]` (stride 1, node base via `shl eax,6`), re-verified
against the live `System/Engine.dll`; (4) multi-room single-zone is now GUARDED — `materialize.
_multizone_warning` emits a warning (>1 Subtract / PF_Portal / ZoneInfo) instead of silently shipping
wrong per-room zones (test `test_multizone_warning_fires_for_multi_room_and_is_quiet_for_single`).
**Infra:** drive the game with `bin/uplayctl session start --map <MAP>` (NOT raw `docker run`); it
needs the `dx-lum-uned` base image — do NOT `docker image prune -a` (it deletes that base; rebuild
via `Tools/uedcli/uned` docker-compose, cache-fast). Disk is at ~96% — `docker system prune -f`
periodically (NOT `-a`).
