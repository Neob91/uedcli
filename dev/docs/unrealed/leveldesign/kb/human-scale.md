# Human-scale numbers  [ENGINE] + [DX] 🔬

Figures for building playable geometry: player size, step height, ceiling height, doorway width,
`PlayerStart` position, path-node spacing. Get these wrong and the map builds but is unwalkable —
steps too tall, ceilings too low, doorways the collision cylinder can't fit through.

Two tiers of confidence:

- ✅🔬 real Deus Ex figures, uedcli-decoded. Read from shipped `DX/System/DeusEx.u` by building a
  throwaway class instance and reading the resolved property default — no editor, no UT proxy. An
  unset property resolves to its class default (offline decode-read semantics — see `direction.md`
  "One package-format core"), the number an author wants. Authoritative; supersede any tutorial
  figure.
- [ENGINE] conventions — engine-generic sizing rules (unit scale, stair/ceiling/doorway/grid) from
  the Legacy wikis, Steve Tack, and Wolf. Design conventions, not binary constants; recommended
  bands, not hard limits (the hard limits — zone count, poly budget, node ceiling — are called out
  separately).

> Scope discipline. DX numbers are not stock UnrealEngine-1 numbers — Deus Ex is an earlier engine
> build than UT99 with a different-sized player pawn. UT99 proxy values are listed at the bottom only
> so an author who finds them in a UT tutorial recognises the wrong substrate — never build DX
> geometry to them.

---

## 1. The real DX figures  ✅🔬 (uedcli-decoded from `DeusEx.u`)

### 1.1 The player  — `JCDentonMale` / `JCDentonFemale`

| Property | Value | Meaning for the author |
|---|---|---|
| `CollisionRadius` | **20** | Cylinder is 40 uu wide (2×radius). Any gap the player passes through — doorway, vent, catwalk edge — needs > 40 uu clear width. |
| `CollisionHeight` | **47.5** | Cylinder is 95 uu tall (2×height). A ceiling below ~95 uu blocks the player; see §3 for standing clearance. |
| `Mass` | **150** | Buoyancy/physics reference — a decoration with `Buoyancy` > 150 floats a body-sized object. |
| `BaseEyeHeight` | **40** | Camera sits 40 uu above the cylinder center, i.e. ~87 uu above the floor (47.5 half-height + 40, minus the small `EyeHeight`/`BaseEyeHeight` settle). Eye-level details (signs, screens) read best at ~80–90 uu. |

### 1.2 Movement  — `JCDentonMale` / `DeusExPlayer` defaults

| Property | Value | Meaning for the author |
|---|---|---|
| `JumpZ` | **300** | Vertical jump impulse. Ledges more than a jump-arc above a foothold are unreachable without an aug/crate. |
| `GroundSpeed` | **320** | Walk/run speed. Sets how big a room feels to cross. |
| `WaterSpeed` | **300** | Swim speed (see the water recipe in [`textures.md`](./textures.md) / [`zones-performance.md`](./zones-performance.md)). |
| `MaxStepHeight` | **25** | The player auto-steps up ledges ≤ 25 uu without jumping. Stairs must have rise ≤ 25 or the player can't climb them. The recommended stair rise of 16 (§3) sits under this ceiling. |
| `AccelRate` | **1000** | Ground acceleration — how quickly the player reaches `GroundSpeed`. |

### 1.3 A representative NPC  — `MJ12Troop`

Confirms the human NPC shares the player's footprint, so a corridor sized for the player fits guards:

| Property | Value |
|---|---|
| `CollisionRadius` × `CollisionHeight` | **20 × 47.5** (identical cylinder to the player) |
| `MaxRange` | **1000** (engagement range) |
| `BaseAccuracy` | **0.2** (lower = more accurate — see [`dx-npcs.md`](./dx-npcs.md)) |
| `Health` | **100** |

### 1.4 Common placed actors

| Class / property | Value | Note |
|---|---|---|
| `Engine.Light` — `LightRadius` | **64** | reach ≈ (Radius+1)×25 ≈ 1625 uu; default 64 often bleeds between rooms — see [`lighting.md`](./lighting.md). |
| `Engine.Light` — `LightBrightness` | **64** | ≈ a quarter of full (255) — brightness, not reach (`LightRadius` sets reach). |
| `Engine.Light` — `LightHue` | **0** | colour wheel, byte 0–255, wraps. |
| `Engine.Light` — `LightSaturation` | **255** | 255 = white/no tint; lower = more saturated (inverted). |
| `Engine.Light` — `LightType` / `LightEffect` | **LT_Steady** / **LE_None** | temporal / spatial defaults. |
| `SecurityCamera` — `cameraFOV` | **4096** | rotator units; 4096 = 22.5° (65536 = 360°). |
| `SecurityCamera` — `cameraRange` | **1024** | view distance. |
| `SecurityCamera` — `swingAngle` | **8192** | 8192 = 45° sweep. |
| `NanoKey` — cylinder | **2.05 × 3.11** | a tiny pickup — illustrates how small collision extents get for hand items. |

(Not recoverable this way: truly `native` C++ classes with empty script `defaultproperties` — e.g.
`Fire.u` fractal-texture `FX_*`/`RenderHeat` values — have no default in the package; see
[`sources.md`](./sources.md). Everything script-defaulted — pawns, lights, movers, particles,
decorations, cameras — reads cleanly.)

---

## 2. Unit scale  [ENGINE] (DX authors think in it explicitly)

| Quantity | Value |
|---|---|
| 1 Unreal unit (uu) | **0.75 inch** |
| **1 foot** | **16 uu** |
| 1 metre | ≈ 52.5 uu |
| 256 uu | **16 ft** (a common room-module size) |
| Max world extent | **65536 uu (2¹⁶) per axis** |

The `16 uu = 1 ft` convention is cross-confirmed by Steve Tack's DX tutorials and the OldUnreal
Legacy wiki. An engine convention DX inherits; DX authors size doors, steps, and panels in
feet-as-16-uu. It is why the default grid is 16 (§4) — one grid square is one foot and one stair
rise.

---

## 3. Architectural sizing  [ENGINE] (recommended bands)

| Element | Value | Why |
|---|---|---|
| Stair rise | recommended **16** (hard max **25** — the player's `MaxStepHeight`, §1.2) | 16 uu = 1 ft = 1 grid square; under the 25 auto-step ceiling. |
| Stair run (tread depth) | 16 steep · **32 good** · 48–64 stately | shallower run = more monumental stairs. |
| Ceiling height | min **~96–100** · recommended **128** | the player cylinder is 95 tall, so standing needs >95; the widely-quoted "83" is the UT99 minimum (78-tall pawn) and will not clear a DX pawn. 128 gives comfortable headroom. |
| Corridor width | min **48** | the player cylinder is 40 wide; 48 is the tight minimum, more for two-way traffic or NPCs. |
| Doorway | ~**128 tall × 64 wide** (generic); **[DX]** doors **144×72** or **128×64**, 1–8 uu thick | must clear the 40-wide × 95-tall player cylinder with margin. |
| Duck / crouch passage | ~52 w × 66 t (UT99 figure — verify for DX) | ⚠ this 52×66 is the UT99 Legacy-wiki crouch minimum, sized for UT's smaller 34-wide/78-tall pawn. DX's crouched cylinder dimensions are not established here — treat 52×66 as a rough lower bound and verify against the DX pawn before relying on it. |

Prefer clean multiples: 96 / 112 / 128 over 100 — see §4 and the BSP-hole mechanism in
[`csg-bsp.md`](./csg-bsp.md) (off-grid coordinates land inside the CSG tolerance bands and get
mis-classified into holes).

---

## 4. Grid discipline  [ENGINE]

| Rule | Value |
|---|---|
| Grid steps | **powers of two** only (…2, 4, 8, **16**, 32, 64, 128, 256…) |
| Default grid | **16** ( = 1 ft = default stair rise ) |
| Detail grid | 8 / 4 / 2 for trim and fine detail |
| Rotation | **solid brushes: 90° increments** (off-90° → irrational coords → BSP holes); **semisolid/nonsolid/decoration: any angle** (they don't cut the world) |

uedcli does not snap for you — grid discipline is authoring guidance, not enforced. The off-grid
failure signature is a coordinate reading `15.999976` where `16` belongs (see
[`csg-bsp.md`](./csg-bsp.md)).

---

## 5. Engine limits & placement numbers  [ENGINE] + [DX]

| Quantity | Value | Scope |
|---|---|---|
| **Poly budget** | **~150 polys in view** (a rule of thumb, not a hard engine limit; modern hardware handles 400+) | [ENGINE] |
| **Zones** | **≤ ~63–64 zones/map** (exceed → zones merge unpredictably); **~3-zone practical see-through depth** (a rule of thumb, not a hard cap — often conflated with the separate mirror/WarpZone recursion limit) | [ENGINE] |
| **Node / point ceiling** | ~2:1 node:poly good (retail 2.5–2.6); past ~4:1 unstable; **~65536 static nodes (overflow blocks the *save*) / ~128000 points (overflow *crashes*)**; instability ~45–55k (stock DX) | [ENGINE] |
| **Mover keyframes** | max **8** (0–7) | [ENGINE] |
| **Mesh skins/textures** | max **8** | [ENGINE] (`MultiSkins[8]` — a texture-slot limit, not a poly-count) |
| **Texture size** | power-of-two, **max 256** renderable (512+ won't render on UE1) | [ENGINE] |
| **`PlayerStart` height** | **40 uu above the floor** | [ENGINE] |
| **PathNode spacing** | **300–700 uu** (≤ 300–350 on ramps/stairs; ≥ 50 min or "paths too close" error; ≥ 50 from corners); **[DX]**: < 700 uu, < 350 on stairs | [ENGINE] + [DX] |
| **Corona `DrawScale`** | 0.1–0.3 | [ENGINE] |
| **Light `LightRadius` → reach** | ≈ **(LightRadius + 1) × 25 uu** | [ENGINE] |

See [`zones-performance.md`](./zones-performance.md) for the poly/zone/node workflow and
[`actors-collision-pathing.md`](./actors-collision-pathing.md) for `PlayerStart` and pathing detail.

---

## 6. DX device / gameplay strengths  [DX]

| Device | Strength |
|---|---|
| Lockpick target (`DeusExMover.lockStrength`) | 20% |
| Hackable device (`HackableDevices.hackStrength`) | 20% |
| Door (`DeusExMover.doorStrength`) | 25% |
| AutoTurret gun (`AutoTurretGun.hackStrength`) | 50% (fixed) |
| BreakableWall (`doorStrength`) | 40% |

See [`dx-classes.md`](./dx-classes.md) for the device classes these strengths belong to.

---

## 7. UT99 proxy values — historical only, do not build to these  ⚠

If you find these in a UT / Unreal tutorial, they are the wrong substrate — Deus Ex is an earlier
engine build with a differently-sized pawn. Listed only so an author recognises and rejects them:

| Quantity | UT99 (wrong for DX) | DX (correct, §1) |
|---|---|---|
| Player collision radius | 17 | **20** |
| Player collision height | 39 | **47.5** |
| Player eye height above center | ~23 (→ ~62 above floor) | **40** (→ ~87 above floor) |
| `JumpZ` | 325 | **300** |

---

## 8. How to read any other default  ✅ (the decode route)

Every ✅🔬 figure above came from this route — offline, no editor:

```
bin/uedcli actor build <Package.Class> | actor add - | actor prop get - <Prop>
```

`actor build` allocates a throwaway instance; `actor add -` writes it into the trunk; `actor prop get`
reads the resolved default (unset → class default). Examples:

```
bin/uedcli actor build DeusEx.JCDentonMale | actor add - | actor prop get - CollisionRadius   # → 20
bin/uedcli actor build DeusEx.MJ12Troop    | actor add - | actor prop get - MaxRange           # → 1000
bin/uedcli actor build Engine.Light        | actor add - | actor prop get - LightRadius         # → 64
```

`class show <Class>` prints property names and types only, never default values — source numbers
from the `actor build … | actor prop get` route above, not `class show`.

(Architectural dimensions of shipped maps — real room/corridor extents an author might copy — are
not class defaults; they live in map geometry and can only be measured by exporting a shipped `.dx`
to a T3D corpus and measuring model-side with `actor bbox` / `brush poly list`. The one genuinely
editor-bound measurement; see residual gaps in [`sources.md`](./sources.md).)

---

*Siblings: [`README.md`](./README.md) (index) · [`design-craft.md`](./design-craft.md) ·
[`sources.md`](./sources.md) · [`csg-bsp.md`](./csg-bsp.md) · [`lighting.md`](./lighting.md) ·
[`actors-collision-pathing.md`](./actors-collision-pathing.md) · [`dx-npcs.md`](./dx-npcs.md).*
