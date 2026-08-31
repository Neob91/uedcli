# Recipe: skybox  [ENGINE]

Build a small sealed room off to the side, put a `SkyZoneInfo` in it (the sky camera / parallax
viewpoint), and flag every surface in the real level that should show sky as `Fake Backdrop` +
`Unlit`. The engine renders the sky room through those faces. Usually one sky room per level (UE1
permits more than one `SkyZoneInfo` — e.g. a high/low-detail pair via `bHighDetail` — but one is the
norm).

## Editor procedure

1. Build a sealed sky room off to the side — a box, dome, or wedge with no holes. Recommended size
   around 1024×1024×768 (big enough to look distant, small enough to stay cheap).
2. Texture and light it — sky textures, colours, whatever your sky is. Add colour with lights, but
   avoid dynamic lights, coronas, and fog in the sky room — they're expensive and misbehave here.
3. Place the `SkyZoneInfo` inside the sky room (class browser → ZoneInfo → SkyZoneInfo, drop it in
   the 3D view). This is the camera the sky is parallaxed from.
4. Flag the sky-showing surfaces. In the real level, open the surface properties of every face that
   should show sky (a window, an open ceiling), enable Fake Backdrop, and add Unlit on the same face.
5. Test in-game. In the editor's 3D viewport the Fake-Backdrop faces show the sky only when realtime
   preview is on (with it off they show their assigned texture); the sky always renders in-game / in
   a preview render.

Tips: use one sky room for the whole level — every Fake-Backdrop face references the same
`SkyZoneInfo`. For a moving sky, set `SkyZoneInfo bStatic=False` + `Physics=PHYS_Rotating` +
`RotationRate` + `bFixedRotationDir=True` (without the fixed-direction flag it won't spin as intended).

## uedcli pipeline

```
# 1. a sealed sky room off to the side (subtract a hollow box)
brush build cube --csg subtract --height 768 --width 1024 --breadth 1024 \
    --texture CoreTexSky.SkyClouds_A --at 8000,8000,4000 | actor add -

# 2. the sky viewpoint
actor build Engine.SkyZoneInfo --at 8000,8000,4000 | actor add -

# 3. in the real level, flag the window/ceiling faces Fake Backdrop + Unlit
brush poly find Window1 | brush poly set - --add-flag FakeBackdrop --add-flag Unlit

# 4. build & photo (Fake-Backdrop faces show the sky in a realtime editor viewport and in a render)
level materialize --out maps/mylevel.dx
```

- `FakeBackdrop` without `Unlit` lets the level's own lighting pollute the backdrop (the sky renders
  lit/wrong) — always pair them ([../textures-and-surfaces.md](../textures-and-surfaces.md)).
- For a spinning sky: `actor prop set <SkyZoneInfo> bStatic=False Physics=PHYS_Rotating RotationRate=(Yaw=2000) bFixedRotationDir=True`.

## Related

- [../textures-and-surfaces.md](../textures-and-surfaces.md) — the Fake Backdrop + Unlit flag pairing.
- [../zones-and-performance.md](../zones-and-performance.md) — the sky room is its own zone.
