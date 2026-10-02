# Lighting — the bake pipeline, light properties, and lighting craft  [ENGINE] (+ DX enums)

Part of the level-design knowledge base. How UnrealEngine 1 / Deus Ex lighting is computed, every
light property with its byte semantics and default, the two animation/shape enums, and how to light a
level. Siblings: [`textures.md`](textures.md) · [`movers.md`](movers.md) ·
[`actors-collision-pathing.md`](actors-collision-pathing.md). Parent monolith:
[`README.md`](README.md). Engine-driving mechanics: [`../../commands.md`](../../commands.md),
[`../../rendering.md`](../../rendering.md).

**Confidence markers** (repo convention): ✅ uedcli-used / live-verified · 🔬 live-probed against the
real DX binary/editor · 📖 extracted from the community tutorial corpus (vocabulary real, semantics to
confirm). **[ENGINE]** = generic UnrealEngine 1 · **[DX]** = Deus-Ex-specific.

---

## 1. The bake pipeline — where lighting is computed  [ENGINE]

UE1 lighting has two halves computed at different times:

- **BSP surfaces** (floors, walls, ceilings) are lit at build time into per-surface lightmaps, one
  small light-texture per surface, computed once and stored in the map file. At render time the GPU
  samples the baked lightmap, so they are free.
- **Actors** (player, movers, decorations, pawns, pickups) are lit at runtime by sampling the level's
  lights each frame. A mover is an actor, so its self-lighting follows this second path — the source
  of the "black door" trap (see [`movers.md`](movers.md) §7).

### 1.1 The console verbs and what each does  🔬✅

| Verb | Effect | Wipes what |
|---|---|---|
| `LIGHT APPLY` | **Bakes** lightmaps for all BSP surfaces from the current lights | nothing |
| `MAP REBUILD` | Rebuilds geometry + BSP | **wipes all lighting** (must re-bake after) |
| GUI **Build All** (Ctrl-B), or the **Build Options** dialog (F8) → Build | Runs geometry → BSP → **lighting** → paths in sequence | — |

Rebuilding geometry/BSP erases lighting, so any geometry change means a relight. Keep **Build
Visibility Zones** checked during a rebuild (unchecking wipes zones too). See
[`../../commands.md`](../../commands.md) for the full exec-verb reference; the build order (Geometry →
BSP → Lighting → Paths) is in [`zones-performance.md`](./zones-performance.md).

### 1.2 What a lightmap actually stores — the bake mechanism  🔬

Verified by the native-materialize spike
([`../../../spikes/2026-07-15-native-materialize/`](../../../spikes/2026-07-15-native-materialize/)):

- The lightmap is a 1-bit-per-lumel visibility mask — for each lumel (lightmap texel) and each light,
  one bit: "does this light reach this point, unobstructed?" It is a shadow map, not a colour map.
- Brightness, hue, saturation, and attenuation are applied at render time from the light's own
  properties; they are not baked into the mask. So re-tinting a light (`LightHue`, `LightSaturation`,
  `LightBrightness`) does not require re-running the visibility bake: the colour/falloff maths run
  per-frame from the live property values. (From the uedcli seat you re-`materialize`/`photo` to see
  the change regardless — there is no partial-bake verb.)
- **Radius → world reach** ≈ **(LightRadius + 1) × 25 uu**. A default `LightRadius=64` reaches
  ≈ 1625 uu.

### 1.3 The uedcli seat: there is NO standalone bake verb  ✅

From uedcli, lights are pure `actor` edits — placing and tuning a light is authoring trunk state:

```
actor build Engine.Light --prop LightRadius=8 --prop LightBrightness=200 --at 128,128,220 | actor add -
actor find --subclass-of Engine.Light | actor prop set - LightHue=28 LightSaturation=64   # re-tint a set
```

There is no `uedcli light bake` / `uedcli relight` verb. The lightmap bake happens inside
`level materialize` and `level photo` — author lights as actors, then materialize/photo to see the
result. The old GUI advice "run `LIGHT APPLY` after retinting" becomes: re-`materialize`/`photo`.

> **UnrealEd GUI equivalent:** place a `Light` actor (L+RMB), edit its *Lighting* property category, then
> Build Lighting (or F8's lighting pass).

**Debunked** ❌: "high light count is a runtime cost like modern dynamic lights." For BSP surfaces it is
not — the lighting is baked and free at runtime. The real cost is bake time and lightmap memory, plus
per-light render-time attenuation maths. Actor lighting (runtime) is the only per-frame lighting cost,
and it is cheap in UE1.

### 1.4 The render-time color/falloff formula — conceptual RE, NOT byte-exact  🔬

For `uedcli`'s native `level photo` preview (`bake-lighting-into-level-photo-native`), not for byte
parity (that bar is explicitly out of scope for this finding — see the board item). Probed live
against `level photo --game` (the real in-game renderer) with a single `Engine.Light` over a flat
floor, varying one property at a time; findings recorded here are the CONCEPTUAL shape only, fit
by eye against a handful of samples — a future byte-parity effort should re-derive this from
disassembly, the same way the rest of this doc's `LIGHT APPLY` findings were.

- **`LightBrightness` scales linearly** up to a clamp/overbright ceiling. Doubling `LightBrightness`
  in the unsaturated range doubles the measured channel value (e.g. 64→111.7, 128→222.3 — ratio
  1.99, matches). Above roughly half-to-two-thirds of 255 the channel saturates at a fixed ceiling
  (texture-dependent, not literally 255 — a real-engine overbright clamp, not a uedcli artifact).
- **`LightHue` is a standard HSV-style colour wheel, RED at 0, moving toward YELLOW as it
  increases** — `LightHue=0` gave a pure `(R,0,0)`; `LightHue=32` (≈45° on a 360° wheel) gave `R`
  still near-max with `G` risen to 180 and `B` still 0, exactly the red→yellow HSV region shape.
  Only 2 points probed (0, 32) — the wheel DIRECTION is solid, the exact per-region curve was not
  swept further (`Hue`/`Saturation` §2 already documents the wheel is continuous, no fixed slots).
- **`LightSaturation` is confirmed inverted** (255 = white/no tint, 0 = fully saturated — matches
  §2) but the desaturation curve is strongly NON-linear / front-loaded: `LightSaturation=128` (the
  byte midpoint) already reads as a barely-tinted near-white `(251.8, 233.4, 206.4)`, not the
  roughly-half-saturated colour a naive linear read of the byte would suggest — expected from a
  standard HSV conversion (S/V blending is inherently non-linear in RGB space), not evidence of
  anything exotic. `G` and `B` came back slightly UNEQUAL at that one sample (a plain HSV formula at
  `Hue=0` predicts them equal); a hue-offset hypothesis was tried to explain it (the historically-
  published UE1 SDK header's `FGetHSV` reportedly pre-rotates the hue byte before bucketing) but it
  fits the `Hue=32` sample WORSE than the plain offset-free formula (predicted `G/R` ratio 0.753 vs
  observed 0.720, vs. a far-off prediction with the offset applied) — dropped. The `G`≠`B` residual
  is most likely sampling noise: the test floor's texture has a visible fine dimpled/patterned
  albedo (confirmed separately — widening the sample box on a fixed light changed the reading by
  20-40 units, the signature of averaging in neighbouring, differently-lit texels), enough on its
  own to explain a ~27-unit gap. Implemented as a plain, offset-free standard byte-HSV conversion.
- **Falloff with distance was NOT cleanly pinned.** At an unsaturated brightness (96), samples at
  distance 25/100/400 uu gave 123/169/151 (rise then fall, not monotonic) — most likely a
  methodology confound (a close light casts a small, steep-gradient pool on the floor, so even a
  small sampling box mixes in laterally-adjacent, less-lit texels; widening the sample box showed
  exactly this — the close-light reading dropped much faster with box size than the far-light one,
  the signature of a tight vs. wide illumination footprint, not necessarily of the true on-axis
  peak-intensity curve). The RADIUS CUTOFF itself is solid and already documented (§1.2,
  `(LightRadius+1)×25 uu`) — both 25 uu and 400 uu are well inside a `LightRadius=64` light's
  ≈1625 uu reach and both lit. Implemented as a simple linear falloff (full at the light, zero at
  the radius-derived reach) — a reasonable, common choice, NOT confirmed as the real curve shape.
- Harness + raw samples: `dev/docs/spikes/2026-09-11-light-color-falloff-re/`.

---

## 2. Light properties — full list, byte 0–255 semantics, defaults  🔬

All HSB / animation fields are a single byte, 0–255. Defaults below are ✅🔬 read from the shipped
`Engine.Light` class default via `actor build Engine.Light | actor add - | actor prop get - <Prop>`
(an unset property resolves to its class default — the offline decode route; `class show` prints
names/types only, not values).

| Property | Default | Semantics (byte 0–255 where noted) |
|---|---|---|
| `LightBrightness` | **64** | Peak intensity at the light. 64 ≈ a quarter of full (255). 255 = blazing. |
| `LightRadius` | **64** | Reach, **not** in uu — world reach ≈ (LightRadius+1)×25 uu (§1.2). |
| `LightHue` | **0** | Colour-wheel position; **wraps at 255** (continuous, no fixed slots). |
| `LightSaturation` | **255** | Inverted: 255 = white / no tint; lower = more saturated. ~64 = a strong visible tint. |
| `LightPeriod` | — | Animation speed for animated `LightType`s — **lower = faster**. |
| `LightPhase` | — | Animation phase offset (stagger two blinking lights so they don't sync). |
| `LightCone` | — | Spot-cone width for `LE_Spotlight` / `LE_StaticSpot` (byte; wider = larger cone). |
| `bSpecialLit` | False | If True, this light **only** affects surfaces flagged `PF_SpecialLit` (see [`textures.md`](textures.md)). Lets you light one surface in isolation. |
| `bCorona` | False | Draw a 2D **corona** sprite at the light (a glare/glint billboard). Needs `Skin` (the corona texture) + `DrawScale` **0.1–0.3**; turn on Volumetric Lighting in the viewport to preview. |
| `Skin` | — | The corona sprite texture when `bCorona=True`. |
| `DrawScale` | — | Corona sprite size (single uniform float; **0.1–0.3** is the usable corona range). |
| `VolumeBrightness` / `VolumeFog` / `VolumeRadius` | — | Per-light volumetric-fog contribution (paired with `ZoneInfo bFogZone`; see [`zones-performance.md`](./zones-performance.md)). |
| `bDynamicLight` | — | Marks the light as re-computed at runtime (for lit movers / moving lights), rather than baked-only. |

- `bLensFlare` is obsolete 🔬 — superseded by `bCorona`. Do not use it.
- Hue-wheel values differ between tutorials 📖 (Steve Tack: R0/O20/Y40/G80/C120/B160/P200; Wolf:
  R0/O25/Y50/G60/B150/P190). The wheel is a continuous byte 0–255; treat any table as approximate, not
  canonical. `LightSaturation` is inverted (255 = white).

*To read any other default:* `bin/uedcli actor build Engine.Light | actor add - | actor prop get -
<Prop>` — offline, no editor.

---

## 3. `LightType` — temporal animation  (enum names 🔬 from `Engine.u`; per-value behaviour 📖 tutorial-sourced)

`LightType` controls how the light changes over time. The DX enum (verified present in the shipped
`Engine.u`):

| Value | Behaviour |
|---|---|
| `LT_None` | Off (no contribution). |
| `LT_Steady` | **Default.** Constant, unchanging. |
| `LT_Pulse` | Smooth sine pulse (breathing). |
| `LT_Blink` | Random on/off, **mostly on**. |
| `LT_Flicker` | Random on/off, **mostly off** (guttering / broken fixture). |
| `LT_Strobe` | Hard on/off flashing. |
| `LT_BackdropLight` | Lights the backdrop/skybox specially. |
| `LT_SubtlePulse` | A gentle, shallow pulse (less than `LT_Pulse`). |
| `LT_TexturePaletteOnce` | Drives an animated-texture palette cycle **once**. |
| `LT_TexturePaletteLoop` | Drives an animated-texture palette cycle **on a loop**. |

Animation speed is `LightPeriod` (lower = faster); `LightPhase` staggers multiple animated lights.
DX includes `LT_Pulse`/`LT_Blink` (confirmed in the embedded enum source) — not a UT-only set.

---

## 4. `LightEffect` — spatial shape  (20-member roster ✅ from `Engine.u`; per-effect descriptions 📖)

`LightEffect` controls the spatial shape of the light — its projected pattern. The DX enum has
exactly 20 members (the standard UE1 roster; binary/decoder-verified via `actor prop set`):

`LE_None, LE_TorchWaver, LE_FireWaver, LE_WateryShimmer, LE_Searchlight, LE_SlowWave, LE_FastWave,
LE_CloudCast, LE_StaticSpot, LE_Shock, LE_Disco, LE_Warp, LE_Spotlight, LE_NonIncidence, LE_Shell,
LE_OmniBumpMap, LE_Interference, LE_Cylinder, LE_Rotor, LE_Unused`.

Useful ones for an author: `LE_TorchWaver`/`LE_FireWaver` (a flickering-flame cast — pair with a fire
decoration, see [`textures.md`](textures.md)); `LE_WateryShimmer` (caustics under/near water);
`LE_Spotlight`/`LE_StaticSpot` (a cone — sized by `LightCone`); `LE_Searchlight`/`LE_SlowWave`/
`LE_FastWave` (sweeping/moving patterns); `LE_Cylinder` (a column of light).

### 4.1 Deus Ex has no `LE_Negative`  ✅ ❌ **Debunked**

`LE_Negative` is a UE2-era (UT2003+) value, absent from this engine build's `Engine.u` (verified — the
20 members above are the complete set, and include `LE_Shock` / `LE_Disco` / `LE_Shell` / `LE_Rotor`).
DX lacks other UE2 effects too, so `LE_Negative` isn't uniquely absent — it's just the one the old
guide wrongly told mappers to use. Any older guide that says "place a negative light to carve shadow"
is describing a later engine.

To darken an area in DX you do not subtract light — you:
- place fewer or dimmer lights (lower `LightBrightness`, smaller `LightRadius`), and/or
- lower the zone's ambient — `ZoneInfo AmbientBrightness` (keep it ≤ ~32; see §5).

This was a live doc bug in the old lighting guide (it claimed "`LE_Negative` subtracts light
(Settled; verified)") — corrected here from the binary.

---

## 5. Lighting craft — how to light a level well  [ENGINE] 📖

From the tutorial corpus.

- **Motivate every light.** Each light should have a visible in-world fixture (lamp, torch, window,
  screen) — a glow with no source reads as a bug. Arch doorways and detail surfaces to mount motivated
  lights.
- **Never light flat.** Use a minimum of two lights per space: a key (the bright hotspot) plus a fill
  (a dimmer light filling the falloff). A single even light kills depth and shape.
- **Radius shapes distinct pools of light.** The default `LightRadius=64` often bleeds across a whole
  room — drop to ~5 for a tight tunnel/alcove, raise to ~175 for an outdoor expanse. Size pools with
  radius, not just brightness.
- **Use light and shadow to guide the eye.** A crisp, high-contrast pattern (see the
  `PF_HighShadowDetail` surface flag in [`textures.md`](textures.md)) pulls attention; a spotlight
  beacons toward a goal or route. Use shadow to hide (secrets, lurking enemies) — in DX, shadow is a
  stealth mechanic, not just mood (see [`README.md`](README.md) §12 immersive-sim craft).
- **Colour for zone identity.** Give each zone a subtle colour signature so the player can navigate by
  it. Drop `LightSaturation` from 255 to ~64 for a visible tint (lower = more saturated).
- **Keep ambient low.** Zone `AmbientBrightness` ≤ ~32 — high ambient flattens everything into uniform
  grey and destroys the key/fill contrast. Prefer darkness broken by motivated pools over a floodlit
  room.
- **Cost model:** light cost scales roughly with r² (lumels live on 2-D surfaces, so a bigger radius
  touches surface area growing with the square of the radius). Prefer many small-radius lights over a
  few enormous ones — cheaper to bake and more controllable.
- **Break up your innovations.** Don't stack a strobe + fog + high-shadow-detail + a big fight in one
  wide-open view — keep the most complex lighting in enclosed, short-sightline areas (also a perf win;
  see [`zones-performance.md`](./zones-performance.md)).

### 5.1 Coronas, fog, and fire lighting  🔬

- **Coronas are a Light mode, not an actor** — `bCorona=True` + `Skin` + `DrawScale` 0.1–0.3 (§2).
  There is no `Corona` actor class in UE1. Set `LightBrightness=0` for a pure glint (a visible corona
  that casts no light). UE1 has no particle emitters — see
  [`actors-collision-pathing.md`](actors-collision-pathing.md) §4; [DX] adds its own
  `ParticleGenerator` family, documented in [`README.md`](README.md) §10.1.
- **Fire is a decoration plus a light, never self-lit.** A fire is a static masked decoration (crossed
  sheets / a cylinder textured with a fire texture, `Masked Decoration` + `Unlit`) plus a separate
  coloured light (`LE_FireWaver`/`LE_TorchWaver`, `LT_Flicker`). The fire texture emits no light of its
  own. See the fire recipe in [`textures.md`](textures.md) and the procedural `Fire.u` family there.
- **Fog needs `ZoneInfo bFogZone=True` as the master gate** — fog is skipped entirely in any zone
  without it. With it on: distance fog = `FogColor` + `FogDistance` (both in the `var(ZoneLight)`
  category — the runnable prop path is bare `FogColor=`, not `ZoneLight.FogColor`; the whole zone fades
  to `FogColor` by `FogDistance`); volumetric (light-cone) fog adds the per-light `VolumeBrightness`/
  `VolumeFog`/`VolumeRadius` terms (§2). These `ZoneInfo` fog fields are engine-generic (present in
  stock UT99 too; the DX-vs-UT99 difference is renderer-level — see
  [`zones-performance.md`](./zones-performance.md)). ✅🔬

---

## 6. Quick verb reference (uedcli)  ✅

| Task | Verb pipeline |
|---|---|
| Place a light | `actor build Engine.Light --prop LightRadius=… --prop LightBrightness=… --at X,Y,Z \| actor add -` |
| Animated / shaped light | add `--prop LightType=LT_Flicker --prop LightEffect=LE_FireWaver` |
| Tint a set of lights | `actor find --subclass-of Engine.Light \| actor prop set - LightHue=28 LightSaturation=64` |
| Read a light default | `actor build Engine.Light \| actor add - \| actor prop get - LightRadius` |
| See the result | `level materialize` / `level photo` (the bake runs **inside** these — no standalone bake verb) |

Lighting-related numbers live in the human-scale table in [`../README.md`](../README.md) and
[`README.md`](README.md) §9 (`Engine.Light` defaults: Radius 64 / Brightness 64 /
Hue 0 / Saturation 255 / `LT_Steady` / `LE_None`; reach ≈ (Radius+1)×25).
