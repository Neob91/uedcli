# Recipes  [ENGINE]

Step-by-step builds for the classic UnrealEngine-1 set-pieces. Each recipe gives the numbered editor
procedure (what the GUI flow does, so you understand the mechanism) and the uedcli verb pipeline (what
you run — the trunk is the source of truth; the editor only builds it via `level materialize`).

> Names in the pipelines are placeholders. `actor add` allocates each actor a name with a random
> suffix (e.g. `Sheet_ab12cd`, not `Sheet4`), so the `Sheet4`-style names below are only for
> readability — feed the actual allocated name `actor add` prints to any follow-up verb
> (`brush poly find <name>`, `actor prop set <name> …`, etc.).

| Recipe                             | Builds |
| ---------------------------------- | --- |
| [water.md](water.md)               | A swimmable pool — a nonsolid translucent portal sheet + a `bWaterZone` ZoneInfo |
| [skybox.md](skybox.md)             | A sky — a separate sealed room + `SkyZoneInfo` + Fake-Backdrop+Unlit windows |
| [glass.md](glass.md)               | A window — a translucent 2-sided sheet + an Invisible Collision Hull |
| [mover-door.md](mover-door.md)     | A door — a `--mover-class` brush + `mover key move` + a trigger |
| [lift.md](lift.md)                 | An elevator — a vertical mover + `StandOpenTimed` / trigger |
| [fire-and-fog.md](fire-and-fog.md) | Flame — a masked decoration + coloured light; and zone fog |
| [shapes/](shapes/)                 | **Shape** recipes — chamfered box, wedge, octagon column, ring cornice, add/subtract twin, L-ledge, arch voussoir, curved corridor, moulded cornice (the non-box brush constructions) |

These recipes assume the mechanisms in the topic guides — [geometry-and-bsp.md](../geometry-and-bsp.md),
[zones-and-performance.md](../zones-and-performance.md),
[textures-and-surfaces.md](../textures-and-surfaces.md), [movers.md](../movers.md).
