# Recipe: a water zone (and pain zones)  [DX]

Deus Ex has a swimming skill, an aqualung aug, and rebreathers — so underwater areas are real
gameplay. A water volume is **a zone whose `ZoneInfo` has `bWaterZone=True`**, with a translucent
portal **sheet** at the surface. DX ships the class **`WaterZone`** — a `ZoneInfo` presetting
`bWaterZone=True` **plus** splash `EntrySound`/`ExitSound`, an underwater `ViewFog` tint, and an ambient
underwater sound. A plain `bWaterZone` `ZoneInfo` is swimmable but loses those cues, so prefer `WaterZone`.

> **There is no `LavaZone`/`SlimeZone` class in DX** (those are stock-Unreal `UnrealShare` classes DX
> doesn't ship), and there is **no `PainZone` class** in any UE1 game — a hazard volume is just an
> ordinary `ZoneInfo` with `bPainZone=True` (covered at the end).

## A: a swimmable water volume

### Procedure

1. **Subtract the pool.** Carve the empty basin out of the floor. **Align it to the 16-uu grid** — an
   off-grid pool is a classic BSP-hole source.
2. **Build the surface sheet.** Make a **Sheet** brush lying flat (horizontal, `--plane xy`) sized to
   exactly cover the pool opening, and place it **just below the rim** (a surface flush with the very
   top looks wrong). This sheet is the water surface plane.
3. **Make the sheet a translucent zone portal** — a **nonsolid** translucent portal the player passes
   through (the `portal` + `translucent` surface flags). Texture it from **`CoreTexWater`** (static or
   animated). This is the visible waterline.
4. **Place the water `ZoneInfo` below the surface.** Add a `WaterZone` (or a plain `ZoneInfo` with
   `bWaterZone=True`) *inside* the pool, under the sheet. Everything in that zone below the sheet now
   behaves as water — you swim in it.
5. **Rebuild** and go for a swim.

### With uedctl

```bash
# 1. Carve the pool (grid-aligned).
brush build cube --csg subtract --width 256 --breadth 256 --height 128 \
  --at 0,0,-64 | actor add -

# 2-3. The surface: a nonsolid translucent zone-portal sheet, just below the rim, CoreTexWater-textured.
#      Horizontal water surface = --plane xy; sheet extents are --width and --height (no --breadth).
brush build sheet --plane xy --width 256 --height 256 \
  --solidity nonsolid --flag portal --flag translucent \
  --texture CoreTexWater.bluewater --at 0,0,-8 | actor add -

# 4. The water zone info, inside the pool under the sheet.
actor build DeusEx.WaterZone --at 0,0,-48 | actor add -
#   (equivalently, but MINUS the splash-sound/fog/ambient presets: actor build Engine.ZoneInfo --prop bWaterZone=True --at 0,0,-48 | actor add -)
```

> **BSP tip:** keep the water sheet a single **oversized simple square** — don't intersect it to an
> odd shape. Add any protruding objects (pillars, ladders) *before* the water sheet. For a large body
> of water, one big brush works: everything below its waterline is underwater (as in
> `01_NYC_UNATCOIsland.dx`).

## B: pain / gas / hazard zones

A pain zone damages anyone inside it. It is a normal sealed zone whose `ZoneInfo` has `bPainZone=True`.

### Procedure

1. **Seal the room as its own zone.** Put **Zone Portal** sheets across every opening (doorways) so
   the room is a distinct zone. (Zoning openings is good practice regardless — it aids culling.)
2. **Verify the zone exists** — after a rebuild, Zone/Portal view should show the room a different
   colour from its neighbours (the zone count went up).
3. **Add a `ZoneInfo` inside** and set `bPainZone=True` + `DamagePerSec` (higher = more damage) +
   `DamageType`. The `DamageType` **name** sets the HUD damage icon: `Shot`, `TearGas`, `PoisonGas`,
   `HalonGas`, `Radiation`, `Flamed` (catches fire), `Burned`, `Shocked`, `EMP`, `Drowned`, `Stunned`.
   (`NanoVirus` exists but has no effect.)
4. **(Optional) cosmetics** — add a `ParticleGenerator` (e.g. `particleTexture=Effects.Gas_Poison`) or
   `ElectricityEmitter` for a visible/audible cue matching the damage type (see
   [`particles.md`](particles.md)).

### With uedctl

```bash
# 1. Seal the doorway as a zone portal. A vertical sheet across the opening = --plane xz (the
#    default); extents are --width (first axis) and --height (Z).
brush build sheet --plane xz --width 64 --height 128 \
  --solidity nonsolid --flag portal --flag invisible --at 128,0,64 | actor add -

# 3. Radiation zone.
actor build Engine.ZoneInfo \
  --prop bPainZone=True --prop DamagePerSec=5 --prop DamageType=Radiation \
  --at 0,0,64 | actor add -
```

> **NPCs and pain zones:** path nodes tend not to work inside a pain zone, so an NPC that must cross
> one is better hurt with a `DamageTrigger` (circular area, easier to set up) than by zoning. Zone
> portals with no `ZoneInfo` are still worth adding — they help optimize the map.

## Properties reference

| Actor / property        | Meaning |
| ----------------------- | --- |
| `WaterZone`             | `ZoneInfo` preset with `bWaterZone=True` — place inside the pool |
| water surface           | a **nonsolid** translucent zone-portal sheet, `CoreTexWater`, just below the rim |
| `ZoneInfo.bPainZone`    | Marks a hazard zone |
| `ZoneInfo.DamagePerSec` | Damage rate |
| `ZoneInfo.DamageType`   | HUD icon / effect: `Radiation`, `PoisonGas`, `Flamed`, `Shocked`, … |
| Zone Portal sheet       | Nonsolid, **invisible** `portal` sheet across each opening that seals a zone |

## Caveats and gotchas

- **Grid-align the pool and keep the surface sheet simple** — the two biggest water BSP pitfalls.
- **`DamageType` is a Name**, matched by name — spelling matters.
- **No `LavaZone`/`SlimeZone`/`PainZone` class** — always a `ZoneInfo` (or `WaterZone`) with the right bool.
- **Rising/falling water needs scripting** — zone portals are immovable geometry.
- **A zone needs its portals watertight** — a gap merges the zone with its neighbour ("whole level
  full of water"). Diagnose in Zone/Portal view.

## See also

- [`particles.md`](particles.md) — steam/gas/electric cues for hazard zones.
- [`../classes.md`](../classes.md) — the DX zone presets.
- [`../../general/geometry-and-bsp.md`](../../general/geometry-and-bsp.md) — zones, portals, and
  avoiding BSP holes/leaks.
