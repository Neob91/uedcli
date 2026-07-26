# Recipe: fire & fog  [ENGINE]

Two atmosphere effects. **Fire** is a *static masked decoration* (crossed sheets or a volumetric star
textured with a fire texture) plus a *separate coloured light* — the flame has no light of its own.
**Fog** is a zone property on the `ZoneInfo`.

---

## Fire

### What you're building

1. A **masked decoration** — a star of sheets (or crossed sheets) textured with an animated fire
   texture, flagged 2-sided + masked + nonsolid + **Unlit**.
2. A **separate coloured light** at the flame's base, ideally animated (`LE_FireWaver` /
   `LE_TorchWaver`).

### Editor procedure (the mechanism)

1. **Position a Volumetric brush** (a star of sheets) where the flame goes — or build crossed sheets.
2. **Select an animated fire texture** from the catalog.
3. **Add Special → Masked Decoration** — this makes it **2-sided, transparent (masked), and nonsolid**,
   so only the flame shape shows and you can walk through it.
4. **Flag the flame faces `Unlit`** (surface properties → Flags → Unlit) and rebuild — the flame should
   glow, not be lit by the room.
5. **Place a light at the flame's centre**, tint it orange, and set its `LightEffect` to **`LE_FireWaver`**
   (or `LE_TorchWaver`) so the cast light flickers like fire.

### uedcli pipeline (what you run)

```
# 1. the flame: a masked, 2-sided, nonsolid, Unlit decoration sheet (all flags set at build; sheets are 2-sided + nonsolid by default)
brush build sheet --plane xz --width 48 --height 96 --flag masked --flag unlit --texture <a fire texture — see note> --at 256,256,64 | actor add -

# 2. the light it casts — orange, flickering
actor build Engine.Light --prop LightHue=25 --prop LightSaturation=64 --prop LightBrightness=200 \
    --prop LightEffect=LE_FireWaver --prop LightType=LT_Flicker --at 256,256,72 | actor add -
```

- **Fire textures:** DX's animated flame textures come from the procedural **`Fire.u`** family (painted
  in the Texture Browser) — there is **no `CoreTexFire` package**. Pick an animated fire texture in the
  browser and use its `Package.Name`.
- The flame is `Masked` (palette index 0 transparent) — a fire texture is authored with a black
  background for exactly this ([../textures-and-surfaces.md](../textures-and-surfaces.md)).
- `LightSaturation=64` gives a visible warm tint (remember: **lower = more colourful**,
  [../lighting.md](../lighting.md)).

---

## Fog

Distance fog is a **zone** property, not an actor. Set it on the zone's `ZoneInfo`:

```
actor prop set MyZone bFogZone=True FogDistance=1200 FogColor=(R=80,G=80,B=100)
```

- Fog is **invisible across zone boundaries** — build an **L-bend** at a foggy zone's edge so the fog
  doesn't pop in abruptly as the player rounds the corner
  ([../zones-and-performance.md](../zones-and-performance.md)).
- Volumetric light shafts through fog use per-light `VolumeBrightness` / `VolumeFog` / `VolumeRadius`.

## Related

- [../lighting.md](../lighting.md) — `LightEffect` / `LightType` animation for the fire glow.
- [../textures-and-surfaces.md](../textures-and-surfaces.md) — the Masked / 2-Sided / Unlit flags.
- [../zones-and-performance.md](../zones-and-performance.md) — zone fog and the L-bend trick.
