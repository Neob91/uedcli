+++
priority = "p?"
kind = "docs"
summary = "Superseded handoff for native full-parity BSP; its core premise (zones were the blocker) was wrong."
+++

# Native full-parity handoff (SUPERSEDED)

Kept rather than deleted, per owner decision 2.6 — nothing is deleted to tidy the board. It is
**shelved as stale** because its first line marks it superseded and no board item owns it: the
premise it was written on (zones being the playability blocker) was disproved live on 2026-07-16.
Migration rule 7 gives an orphan like this an item directory rather than dropping it.

The body below is the handoff verbatim.

---

> **⚠ SUPERSEDED 2026-07-16 — this handoff's core premise (zones are the playability blocker) was
> WRONG.** Live diagnosis found the pawn fell through the floor because the native build shipped no
> **collision hulls** (`LeafHulls`/`iCollisionBound`), not because of zones. Porting the editor's
> `bspBuildBounds` made `NativeCastle` PLAYABLE (`phys=1`, `uplayctl shot` renders the castle
> first-person — `_scratch/shots/native_castle_playable.png`). See the board entry in `board/inbox/`, `sections/70-zones-portalization.md` (zones fully RE'd, now a
> parity-only slice), and `re-raw-zones/linecheck-oracle.md` (the root-cause decode). Zones/side-pool
> /render-bounds/node-flags remain for byte-parity but are NOT needed for a walkable map. Read the
> sections below only for the (still-valid) RE pointers and tooling gotchas, not the diagnosis.

# HANDOFF — full-parity native `.dx` build (2026-07-16)

**Goal:** make a native-materialized `.dx` a **fully PLAYABLE** Deus Ex level — not just one that
loads/renders. The single acceptance gate (per Andrzej): **`uplayctl shot` must show the rendered
world first-person** (like a stock map / the editor-built `Test_Castle.dx` does), with the player
`phys=1` (walking) and the level STAYING (not bouncing to the menu). "Just uplayctl shot, or it ain't
working."

---

## 0. TL;DR — where we are

- **Render is DONE and PROVEN.** Geometry + lighting + textures all render correctly in-game. A
  fast-timed screenshot of the native castle shows the real interior (stone/wood textures, lighting,
  geometry) — see `_scratch/shots/nc_fast_1.png`. The per-frame lit-render AV was a `FBspSurf`
  field-order bug, now fixed (spike §14); textures needed group-qualified imports + `ClassPackage=Engine`
  (spike §15); the game container needs the project overlay wired (`game-entrypoint.sh` `/overlay`).
- **The map is NOT playable.** In-game the pawn is `phys=0` (PHYS_None — a menu/attract spectator,
  `health=-1`), the level never logs "Bringing Level <map> up for play", and the game bounces to
  `DXOnly.dx` (the menu-backdrop map — this is the `DXONLY` you see from `GetCurrentLevelName`). So
  `uplayctl shot` catches the Deus Ex menu logo, not the world.
- **Root cause = the native BSP is MINIMAL: no real zones, one leaf, no side pool, no bounds.** Zone
  portalization (`TestVisibility`) is a **stub** (`uedcli-native/src/zones.rs`). This is the whole
  remaining job.

**IMPORTANT correction to prior belief:** the zoning mechanism was **NOT** fully reverse-engineered.
Only the *output format* of leaves/zones/`FZoneProperties` is decoded (spike §50/§60). The
`TestVisibility` **algorithm** (`Engine.dll 0xaa940`, ImageBase `0x10300000`) is **not** instruction-level
decoded. The current build ships a "single-zone first cut" (all interior = zone 1, one leaf) which is
valid *for collision* but does not make the level a playable multi-zone world.

---

## 1. The binary diff that proves it — native vs editor (SAME castle)

`NativeCastle.dx` (native, from the `foobar` trunk) vs `Test_Castle.dx` (UnrealEd, the same castle).
Decode both with `dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness/utexture_decode.load_package`
+ `uedcli.native.umodel.parse_model_body`:

| Model field | editor (Test_Castle, **plays**) | native (NativeCastle, **menu**) |
|---|---|---|
| zones | **4** (ZoneActor refs → ZoneInfo 122/135) | **2** (both `actor_ref=0` / NULL) |
| leaves | **384** | **1** |
| num_shared_sides | **2739** | **0** |
| nodes w/ iCollisionBound≥0 | **308** | **0** |
| node_flags | varied (0x08×598, 0x0d, 0x18, 0x10, 0x05) | **all 0x00** |
| distinct node iZone pairs | 5 | 1 |

Single-room `NativeLit.dx` matches `DXOnly.dx` (2 zones NULL, 1 leaf) exactly — but **`DXOnly.dx` is
the menu backdrop**, not a gameplay map, so matching it is NOT sufficient for playability. The real
gameplay maps (Test_Castle, `02_NYC_Bar`) all have **zones that reference ZoneInfo actors** and a full
leaf tree.

---

## 2. Remaining work for FULL PARITY (the build side)

All in the native core (`uedcli-native/src/`), then wired through `uedcli/native/`:

1. **Real leaf construction.** Build one `FBspLeaf` per convex empty BSP region (not the single leaf
   `finalize_leaves_and_bbox` emits today, `build.rs` ~line 375). Each node terminal on the empty
   (front/`iChild[1]`) side belongs to a convex leaf; group co-region terminals.
2. **Zone portalization = `TestVisibility`.** Flood-fill the leaf/portal graph: leaves connected
   across a **non-`PF_Portal`, non-solid** boundary are the SAME zone; a `PF_Portal` face SEPARATES
   zones. Assign a zone number per connected component. RE `Engine.dll 0xaa940` instruction-level OR
   implement the standard UE1 zone-flood from first principles, then validate MEMBERSHIP (not counts)
   against `DXOnly` (1 zone) and `Test_Castle` (4 zones). `uedcli-native/src/zones.rs` is the stub to
   fill; design spec §10.8.
3. **`FZoneProperties` + ZoneInfo assignment.** For each zone, `ZoneActor` = the `ZoneInfo`/`SkyZoneInfo`
   actor whose Location point-region-resolves into that zone; the default/interior zone with no ZoneInfo
   → the **LevelInfo** (Actors[0], which is itself an AZoneInfo). The trunk HAS these actors (castle:
   `ZoneInfo_93iu8d`, `SkyZone_1zdw8v`) but the native build leaves `Zone.actor_ref = 0`. Because export
   refs aren't known until assembly, this likely needs an assembly-time patch (mirror
   `assemble._patch_light_refs`): Rust tags each zone with the *name/index* of its ZoneInfo, assembly
   rewrites to the export ref. Also fill real `Connectivity`/`Visibility` masks (today hard-coded
   `0x1`/`0x2`/`u64::MAX`).
4. **Per-node `iZone[front]/iZone[back]` + `zone_mask`** derived from the leaf zones (today `[0,1]` /
   `0b10` blanket).
5. **Side pool — `num_shared_sides` + `FBspVert.iSide`.** Today `num_shared_sides=0`, `iSide=-1`.
   `bspRefresh` shares sides between coplanar node faces; needed for parity (and correct rendering of
   shared edges). See section 50/§7.3.
6. **Node bounds — `iCollisionBound`/`iRenderBound` + the Bounds/`LeafHulls` arrays** (today `-1` /
   empty). Collision does NOT need them (§60.2.3 proved the hull is optional), and render works without
   render bounds, but full parity + render-bound culling wants `bspBuildBounds` (`passes.rs`
   `bsp_build_bounds` currently emits empty).
7. **Node flags.** Editor sets `NF_` bits (0x08 = `NF_PolyOccluded`? etc.); ours are all 0. Determine
   which the engine needs for zones/rendering (the collision predicate only cares about
   `NF_NotCsg|NF_IsNew`, §60.2.1, and we already clear `NF_IsNew`).

**Open RE question that gates #1/#2:** is `TestVisibility` (0xaa940) worth an instruction-level decode,
or is the textbook UE1 zone-flood (leaf graph + portal cut) enough to match membership? The design spec
(§10.8) calls this "a bounded follow-on RE." Validate against real maps by MEMBERSHIP, never counts (D2
was emphatic: equal counts never prove equal zoning).

---

## 3. What is already DONE (do NOT redo)

- CSG→BSP geometry (nodes/surfs/verts, coplanar merge, refresh partial) — `csg.rs`, `build.rs`,
  `passes.rs`. Byte-validated vs real maps for the pieces that exist.
- **Lighting bake (N-4)** + the **`FBspSurf` `iLightMap`/`iActor` field-order fix** (spike §14):
  lit maps render 0 `Anomalous singularity` (was 254 AVs). `run_materialize_native` now defaults
  `no_light=False` (lit). `umodel._enc_surf`/`_parse_surf` + `model_write.rs::put_surf`.
- **Texture imports**: group-qualified (`LUM_CoreTex.Concrete.concrete_02`) + `ClassPackage=Engine`
  (spike §15). `pkgref.build_texture_group_index` + `run_materialize_native(pkg_dirs=…)`.
- **Overlay wiring**: `game-entrypoint.sh` mounts `/overlay` (project packages shadow base);
  `session-run.sh` honours `DX_OVERLAY`; boot scripts pass it. Custom `LUM_*` packages now resolve.
- Collision child-order + `NF_IsNew` clear (player no longer falls through the floor — the `phys=2`
  fall is fixed; the remaining `phys=0` is a *zone/playability* issue, NOT the fall). Section 60.

**Caveat / do NOT chase these dead ends (all disproven this session):** the render crash was NOT an FP
singularity, NOT the `Model.Lights` pointer, NOT geometry-completeness — it was the surf field order
(§14). `DeusExLevelInfo` is NOT required for playability (Test_Castle has none). A textureless map is
not an acceptable substitute (must use real textures).

---

## 4. Verification recipe (the acceptance gate)

```
cd Tools/uplayctl
export DX_OVERLAY=/home/neob91/Games/LutrisDX/drive_c/DX/LUM        # so LUM_* textures resolve
SID=$(bin/uplayctl session start --map NativeCastle | tail -1)      # "link up on NativeCastle"
export UPLAYCTL_SESSION=$SID
bin/uplayctl shot /tmp/out.png                                      # <-- MUST show the castle, not the menu
# check gameplay:
docker exec uplayctl-$SID python3 -c '<link GetCurrentLevelName / GetPlayerPosition / GetMovementDebug>'
#   PASS  = level stays NativeCastle, phys=1 (walking)
#   FAIL  = bounces to DXONLY, phys=0
```
Reference (known-good): `bin/uplayctl session start --map Test_Castle` → shot shows the castle interior,
`phys=1`. `bin/uplayctl session start --map 02_NYC_Bar` → shot shows the bar, `phys=1`. Also diff the
native `.dx` vs `Test_Castle.dx` for leaf/zone MEMBERSHIP parity.

### Tooling gotchas (save hours)
- `uplayctl shot` (855 KB image) works for playable maps; a 241-byte / 74 KB output = the map didn't
  enter gameplay (menu). `import -window <DeusEx-WID>` fails (241 B); use `import -window root` or
  `uplayctl shot`.
- Player state over the link: `GetCurrentLevelName`, `GetPlayerPosition`, `GetMovementDebug` (`phys=`).
- `GetCurrentLevelName == DXONLY` ⇒ the game fell back to the menu map `DXOnly.dx` (`pos -404,0,-127`).
- `DeusEx.log` is **buffered** — it lags the live state and a hard kill loses the tail; poll the link
  for ground truth, don't trust the log tail.
- The boot map `DX.dx` (`game/inputs/DX.dx`, 4.4 MB, `LUMGameInfo`) auto-travels to `Test_Castle` with a
  `LiamRykerPlayer` before the entrypoint travels to the requested map — normal, ignore.
- Renderer: `DXVK` (D3D9→Vulkan) is present (`DeusEx_d3d9.log`) but **`SoftDrv` `Render.dll` @
  `0x10b00000` is the active renderer** (the render RE / `+seh` AVs were all in it).
- Engine-internals capture recipe (registers at a game fault): `engine-internals/gotchas.md` §4 —
  binary-patch store-to-scratch works; ptrace-INT3 and `+seh` registers do NOT.

---

## 5. Key files / pointers

- **Build:** `uedcli-native/src/zones.rs` (STUB — the work), `build.rs::finalize_leaves_and_bbox`
  (~L375, current single-zone cut), `passes.rs::bsp_build_bounds` (empty bounds), `model.rs`
  (FBspNode/Leaf/Zone structs), `model_write.rs` (serializer — pinned to `umodel.py` oracle).
- **Assembly:** `uedcli/native/assemble.py` (add a zone-actor-ref patch like `_patch_light_refs`),
  `umodel.py` (Model struct + serialize/parse; zones at `write_model_body`), `materialize.py`
  (`run_materialize_native`, `pkg_dirs`).
- **RE docs:** design spec in board item `native-level-materialize` §10.8 (zones scope);
  spike `sections/60-leaf-solidity-collision.md` (leaf/collision, engine descent), `50-...` (on-disk
  FBspNode/Leaf/Zone layout), `10-bsp-csg-build.md` (CSG/BSP).
- **RE harness:** `spikes/2026-07-15-native-materialize/harness/`: `leaf_dump_nodes.py`,
  `leaf_fix_classify.py`, `leaf_descent.py` (engine descent sim), `leaf_disas.py`/`leaf_scan.py`
  (Engine.dll disasm), `dishere.py` (disassembler), `pe.py`.
- **Test corpus:** `_scratch/castle/uedcli/maps/foobar` (the castle trunk — `trunk.read_level`);
  `DX/Maps/Test_Castle.dx` (editor parity reference); `DX/Maps/DXOnly.dx` (menu backdrop, single-zone).
- **Verify offline suite:** `cd Tools/uedcli && bin/test` (1161 pass; native ext rebuilds via
  `maturin develop --release` in `bin/_venv.sh`).

---

## 6. Suggested order of attack

1. RE or re-derive `TestVisibility`/zone-flood; write `zones.rs` producing leaves+zones+FZoneProperties.
   Validate leaf/zone MEMBERSHIP vs `DXOnly` then `Test_Castle` offline (no boot needed).
2. Wire ZoneInfo→zone actor refs through assembly (`_patch_zone_refs`).
3. Boot NativeCastle → confirm `phys=1`, stays, `uplayctl shot` shows the castle. (This is the gate.)
4. Add side pool (#5), bounds (#6), node flags (#7) for full byte-ish parity + render-bound culling.
5. Fold the learnings into `sections/60` (or a new `70-zones.md`), `architecture.md`, `direction/materialize.md`;
   flip board items; commit + push per the tool `CLAUDE.md`.
