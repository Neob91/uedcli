# Human-scale numbers  [ENGINE] + [DX] 🔬

The load-bearing figures an author needs to build **playable** geometry: how big the player is, how
high a step, how tall a ceiling, how wide a doorway, where a `PlayerStart` sits, how far apart path
nodes go. Get these wrong and the map builds but is unwalkable (steps too tall, ceilings too low,
doorways the collision cylinder can't fit through).

**Two tiers of confidence live in this file, and the difference matters:**

- **✅🔬 real Deus Ex figures, uedcli-decoded.** These were read **directly from the shipped
  `DX/System/DeusEx.u`** by building a throwaway instance of the class and reading the resolved
  property default — no editor, no guessing, no UT proxy. An unset property resolves to its class
  default (the offline decode-read semantics — see `direction.md` "One package-format core"), which
  is exactly the number an author wants. These are the **authoritative DX numbers** and supersede any
  tutorial figure.
- **[ENGINE] conventions** — engine-generic sizing rules (unit scale, stair/ceiling/doorway/grid
  guidance) drawn from the Legacy wikis, Steve Tack, and Wolf. These are *design conventions*, not
  binary constants; treat them as recommended bands, not hard engine limits (the hard limits — zone
  count, poly budget, node ceiling — are called out separately).

> **Scope discipline.** DX numbers do **not** equal stock UnrealEngine-1 numbers. Deus Ex is an
> **earlier** engine build than UT99, and its player pawn is a **different size**. Historical UT99
> proxy values are listed at the bottom **only** so an author who finds them in a UT tutorial knows
> they are the *wrong* substrate — never build DX geometry to them.

---

## 1. The real DX figures  ✅🔬 (uedcli-decoded from `DeusEx.u`)

### 1.1 The player  — `JCDentonMale` / `JCDentonFemale`

| Property | Value | Meaning for the author |
|---|---|---|
| `CollisionRadius` | **20** | The player's cylinder is **40 uu wide** (2×radius). Any gap the player must pass through — doorway, vent, catwalk edge — needs > 40 uu clear width. |
| `CollisionHeight` | **47.5** | The player's cylinder is **95 uu tall** (2×height). A ceiling below ~95 uu blocks the player entirely; see §3 for standing clearance. |
| `Mass` | **150** | Buoyancy/physics reference — a decoration with `Buoyancy` > 150 floats a body-sized object. |
| `BaseEyeHeight` | **40** | The camera sits 40 uu above the cylinder **center**, i.e. **~87 uu above the floor** (47.5 half-height + 40, minus the small `EyeHeight`/`BaseEyeHeight` settle). Eye-level details (signs, screens) read best at ~80–90 uu. |

### 1.2 Movement  — `JCDentonMale` / `DeusExPlayer` defaults

| Property | Value | Meaning for the author |
|---|---|---|
| `JumpZ` | **300** | Vertical jump impulse. Ledges more than a jump-arc above a foothold are unreachable without an aug/crate. |
| `GroundSpeed` | **320** | Walk/run speed. Sets how "big" a room *feels* to cross. |
| `WaterSpeed` | **300** | Swim speed (see the water recipe in [`textures.md`](./textures.md) / [`zones-performance.md`](./zones-performance.md)). |
| `MaxStepHeight` | **25** | **The single most important geometry number.** The player auto-steps up ledges **≤ 25 uu** without jumping. **Stairs must have rise ≤ 25** or the player can't climb them. The recommended stair rise of **16** (§3) sits safely under this ceiling. |
| `AccelRate` | **1000** | Ground acceleration — how quickly the player reaches `GroundSpeed`. |

### 1.3 A representative NPC  — `MJ12Troop`

Confirms the human NPC shares the player's footprint, so a corridor sized for the player fits guards:

| Property | Value |
|---|---|
| `CollisionRadius` × `CollisionHeight` | **20 × 47.5** (identical cylinder to the player) |
| `MaxRange` | **1000** (engagement range) |
| `BaseAccuracy` | **0.2** (**lower = more accurate** — see [`dx-npcs.md`](./dx-npcs.md)) |
| `Health` | **100** |

### 1.4 Common placed actors

| Class / property | Value | Note |
|---|---|---|
| `Engine.Light` — `LightRadius` | **64** | reach ≈ (Radius+1)×25 ≈ **1625 uu**; default 64 often *bleeds* between rooms — see [`lighting.md`](./lighting.md). |
| `Engine.Light` — `LightBrightness` | **64** | ≈ a quarter of full (255) — brightness, not reach (`LightRadius` sets reach). |
| `Engine.Light` — `LightHue` | **0** | colour wheel, byte 0–255, wraps. |
| `Engine.Light` — `LightSaturation` | **255** | **255 = white/no tint; LOWER = more saturated** (inverted). |
| `Engine.Light` — `LightType` / `LightEffect` | **LT_Steady** / **LE_None** | temporal / spatial defaults. |
| `SecurityCamera` — `cameraFOV` | **4096** | rotator units; **4096 = 22.5°** (65536 = 360°). |
| `SecurityCamera` — `cameraRange` | **1024** | view distance. |
| `SecurityCamera` — `swingAngle` | **8192** | **8192 = 45°** sweep. |
| `NanoKey` — cylinder | **2.05 × 3.11** | a tiny pickup — illustrates how small collision extents get for hand items. |

*(Not recoverable this way:* truly `native` C++ classes with empty script `defaultproperties` — e.g.
the `Fire.u` fractal-texture `FX_*`/`RenderHeat` values — have no default in the package; see
[`sources.md`](./sources.md). Everything **script-defaulted** — pawns, lights, movers, particles,
decorations, cameras — reads cleanly.)*

---

## 2. Unit scale  [ENGINE] (DX authors think in it explicitly)

| Quantity | Value |
|---|---|
| 1 Unreal unit (uu) | **0.75 inch** |
| **1 foot** | **16 uu** |
| 1 metre | ≈ 52.5 uu |
| 256 uu | **16 ft** (a common room-module size) |
| Max world extent | **65536 uu (2¹⁶) per axis** |

The **`16 uu = 1 ft`** convention is the one cross-confirmation worth stressing: Steve Tack's DX
tutorials and the OldUnreal Legacy wiki **agree** on it. It is an engine convention DX inherits, and
DX authors size doors, steps, and panels in feet-as-16-uu deliberately. It is also why the **default
grid is 16** (§4) — one grid square is one foot and one stair rise.

---

## 3. Architectural sizing  [ENGINE] (recommended bands)

| Element | Value | Why |
|---|---|---|
| **Stair rise** | recommended **16** (hard max **25** — the player's `MaxStepHeight`, §1.2) | 16 uu = 1 ft = 1 grid square; comfortably under the 25 auto-step ceiling. |
| **Stair run** (tread depth) | 16 steep · **32 good** · 48–64 stately | shallower run = more monumental stairs. |
| **Ceiling height** | min **~96–100** · recommended **128** | the player cylinder is **95 tall**, so standing needs >95; the widely-quoted "83" is the **UT99** minimum (78-tall pawn) and will NOT clear a DX pawn. 128 gives comfortable headroom. |
| **Corridor width** | min **48** | the player cylinder is 40 wide; 48 is the tight minimum, more for two-way traffic or NPCs. |
| **Doorway** | ~**128 tall × 64 wide** (generic); **[DX]** doors **144×72** or **128×64**, 1–8 uu thick | must clear the 40-wide × 95-tall player cylinder with margin. |
| **Duck / crouch passage** | ~52 w × 66 t *(UT99 figure — verify for DX)* | ⚠ this 52×66 is the **UT99** Legacy-wiki crouch minimum, sized for UT's smaller 34-wide/78-tall pawn. DX's crouched cylinder dimensions are **not established here** — treat 52×66 as a rough lower bound and verify against the DX pawn before relying on it. |

Prefer clean multiples: **96 / 112 / 128** over 100 — see grid discipline (§4) and the BSP-hole
mechanism in [`csg-bsp.md`](./csg-bsp.md) (off-grid coordinates land inside the CSG tolerance bands
and get mis-classified into holes).

---

## 4. Grid discipline  [ENGINE]

| Rule | Value |
|---|---|
| Grid steps | **powers of two** only (…2, 4, 8, **16**, 32, 64, 128, 256…) |
| Default grid | **16** ( = 1 ft = default stair rise ) |
| Detail grid | 8 / 4 / 2 for trim and fine detail |
| Rotation | **solid brushes: 90° increments** (off-90° → irrational coords → BSP holes); **semisolid/nonsolid/decoration: any angle** (they don't cut the world) |

uedcli does **not** snap for you — grid discipline is authoring guidance, not an enforced operation.
The off-grid failure signature to hunt for is a coordinate reading **`15.999976`** where `16` belongs
(see [`csg-bsp.md`](./csg-bsp.md)).

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

## 7. UT99 proxy values — HISTORICAL ONLY, do NOT build to these  ⚠

If you find these in a **UT / Unreal** tutorial, they are the **wrong substrate**. Deus Ex is an
earlier engine build with a differently-sized pawn. Listed here only so an author recognises and
**rejects** them:

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

**`class show <Class>` prints property NAMES and TYPES only — never the default VALUES.** The values
come from the `actor build … | actor prop get` route above. Do not source numbers from `class show`.

*(Architectural dimensions of **shipped maps** — the real room/corridor extents an author might want
to copy — are NOT class defaults; they live in the map geometry and can only be measured by exporting
a shipped `.dx` to a T3D corpus and measuring it model-side with `actor bbox` / `brush poly list`.
That is the one genuinely editor-bound measurement; see the residual gaps in [`sources.md`](./sources.md).)*

---

*Siblings: [`README.md`](./README.md) (index) · [`design-craft.md`](./design-craft.md) ·
[`sources.md`](./sources.md) · [`csg-bsp.md`](./csg-bsp.md) · [`lighting.md`](./lighting.md) ·
[`actors-collision-pathing.md`](./actors-collision-pathing.md) · [`dx-npcs.md`](./dx-npcs.md).*
