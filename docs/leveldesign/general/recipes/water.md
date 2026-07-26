# Recipe: water  [ENGINE]

A swimmable pool. The mechanism: a **zone whose `ZoneInfo` has `bWaterZone=True`** is water, and its
surface is a **nonsolid translucent sheet** flagged as a zone portal (the "Add Special → Water" preset).
The water sheet is the portal between the air zone above and the water zone below. 📖 (the
`portal`+`translucent` sheet + `bWaterZone` mechanism is community-sourced; swimmability in this exact
build is not yet live-verified.)

## What you're building

1. A pool cavity subtracted into the floor.
2. A flat **sheet** across the top of the pool — translucent, 2-sided, zone-portal — with a water
   texture (this is the visible water surface).
3. A **ZoneInfo** placed *inside* the pool with `bWaterZone=True` — this makes the volume swimmable.

## Editor procedure (the mechanism)

1. **Subtract the pool.** Carve a cavity into the floor where the water goes (e.g. 400×176 wide, 200
   deep — keep it on the 16-uu grid).
2. **Load a water texture** (an animated water texture from the catalog).
3. **Build the water sheet.** Sheet builder → orientation **Floor/Ceiling**, U/V matched to the pool
   dimensions. Place it **slightly below the rim** so the water doesn't look like it's overflowing.
4. **Add Special → Water** with the water texture selected — this stamps the sheet as a nonsolid,
   translucent, portal, 2-sided surface with the correct water settings.
5. **Place the water zone.** From the class browser pick a water `ZoneInfo` and place it **inside the
   pool, below the sheet**.
6. **Rebuild** geometry + BSP.
7. *(Optional)* On the water surface, check **Small Wavy** for animated ripples, and give the ZoneInfo a
   water `AmbientSound`.

**Tips:** keep the water sheet an **oversized simple square** — don't intersect it into odd shapes (that
invites BSP holes). Any object that pokes through the surface must be added **before** the water sheet.
The sheet is immovable, so rising/falling water needs scripting, not geometry.

## uedcli pipeline (what you run)

```
# 1. carve the pool cavity into the floor
brush build cube --csg subtract --height 200 --width 400 --breadth 176 --at 512,512,-100 | actor add -

# 2. build the water surface: a nonsolid sheet, translucent + 2-sided + portal, just below the rim
brush build sheet --plane xy --width 400 --height 176 --flag portal --flag translucent \
    --texture CoreTexWater.bluewater --at 512,512,-8 | actor add -          # lands ready: nonsolid + 2-sided by default; portal + translucent from --flag

# 3. place the ZoneInfo inside the pool, marked a water zone (set at build — no follow-up needed)
actor build Engine.ZoneInfo --prop bWaterZone=True --prop ZoneName=Pool --at 512,512,-100 | actor add -

# 4. build & check
level materialize --out maps/mylevel.dx
```

- The portal sheet **must be watertight** across the opening or the water and air zones leak into one
  (see [zones-and-performance.md](../zones-and-performance.md)).
- Deus Ex ships a `WaterZone` class — a `ZoneInfo` presetting `bWaterZone` **plus** splash sounds and an
  underwater fog tint (a plain `bWaterZone` ZoneInfo loses those) — see [../../deusex/](../../deusex/).

## Related

- [../zones-and-performance.md](../zones-and-performance.md) — zones, portals, and the leak diagnosis.
- [../textures-and-surfaces.md](../textures-and-surfaces.md) — the Translucent / 2-Sided / portal flags.
