# Zones, portals, occlusion & performance  [ENGINE]

How UE1 seals a level into visibility regions, what its occlusion model actually is (and is not), the hard
limits you design against, and the concrete optimization/finishing workflow. This file is the sibling of
[csg-bsp.md](./csg-bsp.md) (a leak/zone-merge is a BSP failure on a portal face) and
[lighting.md](./lighting.md) (fog and ambient live on the `ZoneInfo`).

---

## 1. Zones and zone portals  [ENGINE]

- A **zone** is a watertight region — any solid brush shape — sealed from its neighbours by **zone-portal
  SHEET brushes**. Each zone carries a `ZoneInfo` actor placed **inside** it, resolved to that zone at
  rebuild. Verify zones in **Zone/Portal view** (one colour per zone).
  - **uedcli:** `actor build Engine.ZoneInfo --prop … | actor add -`; portal sheet via `brush build sheet
    --width 128 --height 128 --flag portal --flag invisible | actor add -` (invisible so the portal plane
    itself doesn't render; a *water* surface is the visible exception — it's `portal`+`translucent`).
  - *(GUI equivalent: place a `ZoneInfo`; build a Sheet brush over the opening → Add Special → Zone
    Portal.)*

### "Portals need solid" — the precise truth

This is a widely-mangled rule. **Corrected and reconciled** (Steve Tack, Wolf, tactical-ops all agree):

- The **zone-portal SHEET is NON-SOLID** (a `brush build sheet` is already NotSolid by default).
- It is the **zone-BOUNDARY geometry that must be SOLID** — a semisolid on a boundary won't seal, and a
  **semisolid abutting a portal/boundary is the real BSP-wrecker** (§ [csg-bsp.md](./csg-bsp.md) §4).
- **Size the portal to cover the OPENING** (a doorway). Excess sheet **buried in solid** is clipped by
  BSP and harmless — you can safely oversize a portal *into a wall* (see §1.1's "oversized simple square"
  water sheet). What you must NOT do is leave portal area **exposed in open air**: any portal fragment
  hanging in open space stays visible and keeps its zone from ever culling. So cover the opening fully;
  just don't let portal area hang in the open. **For culling, still fit portals near the opening** —
  "buried is harmless" is about **sealing**; an oversized portal can cull *less* well than a snug one
  (visibility is tested against the portal's own geometry), so tight beats oversized when you can. 🔬-verify
  in this DX build if it matters.

### 1.1 The water recipe (the first concrete zone recipe)

A water volume is a **zone** whose `ZoneInfo` has `bWaterZone=True`, with the water's top surface being a
**translucent** sheet that also acts as the **zone portal** between the water zone and the air zone above.
A `brush build sheet` is already NotSolid, and its surface flags are set at build time with `--flag`, so
the whole thing is two one-step commands (no separate `brush poly` pass):

```
# 1. the water surface: a portal + translucent sheet spanning the opening between air and water.
#    Sheets default to NotSolid; --flag sets the surface flags at build time, so it lands ready.
brush build sheet --width W --height H --plane xy --flag portal --flag translucent | actor add -

# 2. the water zone marker, placed inside the flooded region below the sheet
actor build Engine.ZoneInfo --prop bWaterZone=True --at <x,y,z-inside-water> | actor add -
#    (DeusEx.WaterZone is the substrate-specific alternative to a bWaterZone Engine.ZoneInfo)
```

**Recipe notes** (📖 Steve Tack / Wolf): subtract a pool → build a **Sheet** (Floor/Ceiling, U/V matched,
placed just below the rim) → *Add Special → Water* → place the water `ZoneInfo` under the sheet. Keep the
water sheet an **oversized simple square** (don't intersect it to odd shapes — BSP tip). Protruding objects
must be added *before* the water sheet. Rising/falling water needs scripting (zone portals are immovable).

The flag **names** (`portal`, `translucent`) are settled (in `query.py PF_NAMES`). What is not yet
live-verified is the **semantics** in this specific UED22/DeusEx build — whether a `portal`+`translucent`
NotSolid sheet plus a `bWaterZone` actor actually yields a swimmable water zone. That is a build-gate probe
(open question Q1), not a settled fact.

See [textures.md](./textures.md) for the wider water/fog/fire/skybox recipe set.

---

## 2. The occlusion model  [ENGINE]  — **no antiportals**

UE1's occlusion is **solid BSP + zones ONLY.**

- **There are NO antiportals.** *(Debunked:* antiportal occlusion is **UE2+**; in UE1 "portal" means zone
  portal only.) Do not design around occluder brushes — they don't exist here.
- **Zone culling:** if no part of a zone's sealing portal is visible, the **whole zone is culled** (its
  polys are rejected before rendering).
- **Long sightlines are the enemy.** They defeat zone culling (many zones stay visible at once) and blow
  the poly budget. Break them with structure — bends, doorways, level changes.
- **Zone culling in practice:** put portals at **both ends** of a hallway; keep portal sheets **simple**
  (a flat quad, not an intersected odd shape) and order them **To Last**; maximise the number of
  *non-adjacent* zones so more can be rejected at once.

---

## 3. Hard limits  [ENGINE]

| Limit | Value | Note |
|---|---|---|
| **Zones per map** | **max ~63–64** | exceed → zones merge unpredictably ("whole map underwater") |
| **Zone see-through depth** | **~3 (practical)** | a mapping rule of thumb — plan for ~3 zones visible through portals before a far portal starts showing its own texture. NOT a hardcoded engine counter (visibility is frustum + occlusion driven); the crisp "3" is also the *separate* mirror/WarpZone recursion limit, which the two facts are often conflated |
| **Poly budget (in view)** | **~150 (rule of thumb)** | originally "~150 in view"; modern hardware handles 400+ easily. A safe target near 150, **not** an engine-enforced ceiling |
| **Node:poly ratio** | **≈2:1 target** | retail UT maps ~2.5–2.6; an unsplit cube is 1.0; a high ratio (rule of thumb: roughly >4:1) is a warning sign, not a hard threshold |
| **Node / point ceiling** | **~65,536 nodes / ~128,000 points** | static-node overflow blocks the **save**; the ~128,000-point (`MAX_POINTS`) limit is what **crashes**; UT-era reports put practical instability well before the ceiling. The OldUnreal 227j patch raises the **node** ceiling (to 262,144) — don't design DX maps to 227j limits |

*(All engine-generic; the DX pawn dims that set the human scale these budgets are spent on are in
[human-scale.md](./human-scale.md).)*

---

## 4. Distance fog  [ENGINE]  🔬

Fog is engine-generic and lives on the `ZoneInfo`:

- `ZoneInfo` `bFogZone=True` enables it; `FogColor` (color) + `FogDistance` (float) set it. (Both live in
  the `var(ZoneLight)` property *category* — the runnable prop path is bare `FogColor=`/`FogDistance=`,
  **not** `ZoneLight.FogColor`.)
- Per-light volume settings interact: `VolumeBrightness` / `VolumeFog` / `VolumeRadius`.
- **Fog is invisible across zone boundaries** — build an **L-bend** at a zone boundary so fog doesn't
  "pop in" as you cross.
- **A far sightline with neither a skybox nor distance fog to fill it → HOM** at the far plane (the
  un-cleared framebuffer shows through). See [csg-bsp.md](./csg-bsp.md) §5.4 HOM cause (3).
- **uedcli:** all `actor` edits on the `ZoneInfo` — `actor prop set` / `actor build Engine.ZoneInfo --prop
  bFogZone=True --prop FogDistance=… | actor add -`. DX adds **no bespoke fog class**.
- *(UT99 vs DX:* the `FogColor`/`FogDistance`/`bFogZone` *fields* exist in stock UT99's `ZoneInfo` too, but
  stock Unreal/UT99 barely implements **distance** fog from them — its `bFogZone` mainly gates **volumetric
  light fog** (the per-light `Volume*` terms above). **DX** actually renders per-zone **distance** fog from
  `FogColor`/`FogDistance`. Full distance-fog support arrived in Unreal later, via the OldUnreal 227 patch.)

---

## 5. Optimization workflow  [ENGINE]

### 5.1 Node vs poly

- **Node** = a BSP tree node, each carrying a surface fragment. **Poly** = a rendered surface. Zone/Portal
  view colours by *zone* (not by node). **Target node:poly ≈ 2:1** (retail 2.5–2.6; unsplit cube 1.0).
- Rebuild with **Optimal** BSP + geometry optimization (**never "Lame"**). The optimization level sets how
  many candidate splitter polys the builder evaluates (`uedcli-native/src/bspcsg.rs`: LAME strides
  `NumPolys/4` → ~4 candidates, GOOD strides `NumPolys/20` → ~20, Optimal every poly) — **more candidates
  → better splitters → fewer nodes**, so Lame (fewest candidates) leaves the most nodes. **Coplanar-merge
  is a separate pass, not gated by this level**. A full **geometry** rebuild is deterministic from the
  brush list and does not accumulate splits pass-over-pass, so "always rebuild 3×" is cargo-cult for a full
  rebuild (repeated *BSP-only* rebuilds can shave the node ratio slightly, plateauing after ~3).

### 5.2 Readout commands  [ENGINE]

- `STAT FPS` — frame time / fps.
- `STAT ZONE` — **visible vs rejected** zones (confirms culling is working).
- `STAT GLOBAL` / `STAT POLYC` / `STAT MESH` — render breakdown / poly counts / mesh census (`POLYC`/`MESH`
  are `STAT` **subcategories**, not bare commands). *(These STAT names are UT99-documented; confirm against
  the DX build — `STAT RENDER` is not a command, the render figures live under `STAT GLOBAL`.)*
- `MEMSTAT`, `OBJ LIST` — memory / object census.
- Viewport **rmode** views: wireframe; **Zone/Portal = THE optimization view** (one colour per zone,
  colored nodes); lighting-only. *(Depth-complexity rmode is UE2 — may be absent in DX.)*

### 5.3 Build order  [ENGINE]

**Geometry → BSP → Lighting → Paths.** Two traps:

- **Rebuilding Geometry+BSP ERASES lighting** → you must **relight after any geometry change**. (From the
  uedcli seat there is no standalone bake verb — re-`materialize`/`preview` re-bakes; see
  [lighting.md](./lighting.md).)
- **Keep "Build Visibility Zones" checked** — unchecking it **wipes zones**.

### 5.4 Brush vs mesh  [ENGINE]

- **CSG for the sealed shell** — it holds the zones; only solid BSP can seal.
- **Decoration/mesh actors + movers for ornament** that shouldn't cut BSP. Converting a detail brush to a
  mover **removes its BSP nodes** (a mover is `PHYS_MovingBrush`, not world geometry).
- See [geometry-builders.md](./geometry-builders.md) (MeshMaker: turn a faceted brush pillar into a mesh
  Decoration — no BSP holes, cheaper many-face render) and
  [actors-collision-pathing.md](./actors-collision-pathing.md) (decoration collision).

---

## 6. Finishing  [ENGINE]

The pre-ship checklist:

- **MyLevel `ScreenShot` texture** (256×256, P8, mipmaps off) + `LevelInfo` Title/Author (see
  [textures.md](./textures.md) for `MyLevel`).
- **Walk the level for HOM.**
- **Hunt stray polys in the default/null zone (zone 0) in Zone/Portal view** — a semisolid meeting the
  world edge can land there; it signals a **sealing gap** (a leak), which is what to clean up.
- **An ambient sound on every `ZoneInfo`** (silence is a bug): the zone's inherited `AmbientSound` (a
  looping bed), plus optional `EntrySound` / `ExitSound` at the boundary. There is **no** property literally
  named `ZoneSound`.
- **Check `bKillZone` zones** — a `ZoneInfo` flagged `bKillZone=True` kills anything that enters it, so
  keep spawn points and reachable areas out of one. (This build has **no `KillZ` Z-threshold** — that is a
  later-engine field; UE1/DX uses the whole-zone `bKillZone` flag.)
- **Verify node:poly + `STAT FPS`** in the busiest views.
- *(editor-console)* **Never run `TEXTURE CULL` with hidden brushes present** — it wipes their textures.

---

## 7. uedcli verb summary for this file

| Task | uedcli | GUI equivalent |
|---|---|---|
| Place a zone | `actor build Engine.ZoneInfo --prop … \| actor add -` | place `ZoneInfo` |
| Zone portal | `brush build sheet --width W --height H --flag portal --flag invisible \| actor add -` | Sheet brush → Add Special → Zone Portal |
| Water zone | portal+translucent sheet + `bWaterZone` ZoneInfo (§1.1) | translucent portal + `bWaterZone` ZoneInfo |
| Fog | `actor build Engine.ZoneInfo --prop bFogZone=True --prop FogDistance=… \| actor add -` | `ZoneInfo` fog fields |
| Portal ordering | `actor order <names…> --last` (portals To Last; or `… \| actor order - --last`) | Order → To Last |

Optimization readouts (STAT/rmode) and the build passes are **editor-side** — from the uedcli seat they
run inside `level materialize`/`level preview`.
