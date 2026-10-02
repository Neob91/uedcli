# General level design — engine-generic craft

The engine-generic craft of building UnrealEngine-1 levels with uedcli. Everything here applies to
any UE1 game; the Deus Ex-specific layer (DX classes, NPCs, the `CoreTex*` palette, the immersive-sim
philosophy) is one level up in [../deusex/](../deusex/). The composing pattern and verb families are in
the [top README](../README.md).

## Topic guides

| Guide                                                | Covers |
| ---------------------------------------------------- | --- |
| [geometry-and-bsp.md](geometry-and-bsp.md)           | Subtract-then-add, solidity, brush order, and avoiding BSP holes / HOM |
| [zones-and-performance.md](zones-and-performance.md) | Zones, zone-portal sheets, the poly/zone/sightline budgets, breaking sightlines |
| [lighting.md](lighting.md)                           | Placing `Engine.Light`, the key light properties, and lighting craft (motivate, key+fill, radius, guiding) |
| [textures-and-surfaces.md](textures-and-surfaces.md) | `brush poly` texturing, surface flags, alignment & scrolling, MyLevel, skybox flags |
| [movers.md](movers.md)                               | Doors/lifts/crushers — `--mover-class` + `mover key`, keyframes, encroachment, the black-door fix |
| [actors.md](actors.md)                               | Collision cylinders & blocking, decorations & breakables, PlayerStart, pathnodes |
| [brush-shapes.md](brush-shapes.md)                   | The `brush build` shapes (cube, cylinder, cone, sheet, staircase, spiral, extrude, revolve) and their parameters |
| [human-scale.md](human-scale.md)                     | The engine-generic numbers — units, stairs, ceilings, doorways, grid — and how to read any class default |
| [design-craft.md](design-craft.md)                   | Composition, lighting mood, and flow — what makes a level good (engine-generic) |

## Recipes

Full step-by-step builds (numbered editor actions **and** the uedcli verb pipeline) in
[recipes/](recipes/):

- [water.md](recipes/water.md) — a nonsolid translucent sheet + a `bWaterZone` ZoneInfo
- [skybox.md](recipes/skybox.md) — a sealed sky room + `SkyZoneInfo` + Fake-Backdrop+Unlit windows
- [glass.md](recipes/glass.md) — a translucent 2-sided sheet + an Invisible Collision Hull
- [mover-door.md](recipes/mover-door.md) — a `--mover-class` brush + `mover key move`
- [lift.md](recipes/lift.md) — a vertical mover + `StandOpenTimed` / trigger
- [fire-and-fog.md](recipes/fire-and-fog.md) — a masked decoration + coloured light; `bFogZone`

## Where to start

New to UE1 mapping? Read [geometry-and-bsp.md](geometry-and-bsp.md) and
[human-scale.md](human-scale.md) first — clean on-grid geometry at the right scale is 80% of a working
level. Then [zones-and-performance.md](zones-and-performance.md) so it runs, and
[lighting.md](lighting.md) so it looks like anything. The recipes tie it all together.
