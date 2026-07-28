# Lighting  [ENGINE]

In UE1 lights are actors: place `Engine.Light` actors into the trunk to light the level. There is no
light-editing mode and no bake verb — lighting bakes automatically on `level materialize` or
`level preview`.

## How UE1 lighting works

Two halves that behave differently:

- **BSP surfaces** (walls/floors/ceilings) are lit by a precomputed lightmap — baked once, free at
  runtime.
- **Actors** (players, movers, decorations) are lit at runtime from the level's lights.

The baked lightmap is a 1-bit-per-lumel visibility mask (does this spot see the light); brightness,
hue, saturation, and falloff are applied at render time from the light's properties. A light's world
reach ≈ (LightRadius + 1) × 25 uu. ✅

## Placing a light

```
actor build Engine.Light --prop LightRadius=8 --prop LightBrightness=200 --at 128,128,200 | actor add -
```

A plain property edit — no editor round-trip.

## Key properties

All HSB / animation fields are a byte, 0–255. ✅ Defaults are from `Engine.Light`:

| Property          | Default     | Meaning |
| ----------------- | ----------- | --- |
| `LightBrightness` | 64          | intensity (≈ a quarter of full, 255) — brightness only; `LightRadius` sets reach |
| `LightRadius`     | 64          | reach; world reach ≈ (Radius+1)×25 uu — your primary shaping tool |
| `LightHue`        | 0           | colour wheel, wraps at 255 |
| `LightSaturation` | 255         | 255 = white / no tint; lower = more colourful — the scale is inverted |
| `LightType`       | `LT_Steady` | temporal animation (see below) |
| `LightEffect`     | `LE_None`   | spatial shape (see below) |
| `LightPeriod`     | —           | animation speed — lower = faster |
| `LightCone`       | —           | spotlight cone width |
| `bSpecialLit`     | —           | this light hits only Special-Lit surfaces |
| `bCorona`         | —           | draws a 2D corona sprite (needs a `Skin`; `DrawScale` ~0.1–0.3) |

**`LightType`** (temporal animation): `LT_None, LT_Steady, LT_Pulse, LT_Blink` (random, mostly on),
`LT_Flicker` (random, mostly off), `LT_Strobe, LT_BackdropLight, LT_SubtlePulse,
LT_TexturePaletteOnce, LT_TexturePaletteLoop`. ✅

**`LightEffect`** (spatial shape). This build's `ELightEffect` has 20 members: `LE_None,
LE_TorchWaver, LE_FireWaver, LE_WateryShimmer, LE_Searchlight, LE_SlowWave, LE_FastWave, LE_CloudCast,
LE_StaticSpot, LE_Shock, LE_Disco, LE_Warp, LE_Spotlight, LE_NonIncidence, LE_Shell, LE_OmniBumpMap,
LE_Interference, LE_Cylinder, LE_Rotor, LE_Unused`. ✅

> No negative light in this build. `LE_Negative` (a later UE2-era value, UT2003+) does not exist —
> you cannot subtract light. Darken by placing fewer or dimmer lights, or by lowering the zone's
> `AmbientBrightness` (keep it ≤ ~32 so surfaces don't go flat). ✅

## Lighting craft

- **Motivate every light.** A pool of light with no visible source reads as fake. Put a lamp, window,
  fire, or glowing panel at the source.
- **Don't light flat.** A single fill light looks like a rendered box. Use at least two lights per
  space — a bright key plus a dim fill — for a hotspot and falloff.
- **Radius is your main tool.** The default 64 usually bleeds and washes a room out. Shrink it for
  distinct pools — ~5 for a tight tunnel, up to ~175 for an outdoor wash.
- **Guide and hide.** Crisp bright patterns pull the eye toward where the player should go; a
  spotlight beacons a landmark; shadow hides a secret or a dull surface.
- **Colour for zone identity.** Drop `LightSaturation` toward ~64 for a visible tint and give each
  zone its own hue — players navigate by colour without noticing.
- **Prefer many small lights over few huge ones.** Cost scales roughly with radius² (lumels sit on
  2-D surfaces, so reach-area grows with the square), and small lights give more control over where
  light lands.

## Related

- Animated fire/torch light: [recipes/fire-and-fog.md](recipes/fire-and-fog.md) (`LE_FireWaver` /
  `LE_TorchWaver` + a masked flame decoration).
- Moving objects lit wrong: see the black-door quirk in [movers.md](movers.md).
- [textures-and-surfaces.md](textures-and-surfaces.md) — the `Unlit` / `Special Lit` surface flags that
  interact with lighting.
