# Human scale  [ENGINE]

The numbers that make a level feel right to walk through. Build to these and spaces read as human. These
are the engine-generic UE1 figures.

> **Deus Ex player dimensions** (JC Denton's cylinder, eye height, jump, step) differ from stock UE1 and
> live in [../deusex/human-scale.md](../deusex/human-scale.md). Use those when authoring for DX.

## Units

1 unreal unit (uu) ≈ 0.75 inch. `1 foot = 16 uu`. ✅ (1 m ≈ 52.5 uu; 256 uu = 16 ft.) A 128-uu ceiling
is 8 feet. The world maxes out at 65,536 uu per axis.

## Grid

Build on a power-of-two grid. 16 is the default working grid (= 1 foot = the default stair rise); drop to
8 / 4 / 2 for fine detail. Never build sub-grid — off-grid coordinates are the main cause of BSP holes
([geometry-and-bsp.md](geometry-and-bsp.md)). uedcli does not snap for you.

## Key dimensions

| Quantity               | Value |
| ---------------------- | --- |
| **Stair rise**         | recommended **16**; keep ≤ the pawn's auto-step (`MaxStepHeight`, **25** in Deus Ex) — a taller step needs a jump |
| **Stair run**          | 16 (steep) / **32** (comfortable) / 48–64 (stately) |
| **Ceiling height**     | min **83** (fits a ~78-tall stock-UE1/UT pawn; the **DX** player is 95 tall and needs **~96–100** — see [../deusex/human-scale.md](../deusex/human-scale.md)); recommended **128** (8 ft) |
| **Corridor width**     | min **48** |
| **Doorway**            | ~**128 tall × 64 wide** |
| **PlayerStart height** | **40 uu** above the floor |
| **PathNode spacing**   | **300–700 uu** (≤300–350 on ramps/stairs; ≥50 min or "paths too close") |
| **Grid**               | power-of-two; 16 default, 8/4/2 for detail |

Reference limits from the other guides that are really scale numbers:

| Quantity                | Value |
| ----------------------- | --- |
| Polys in view           | ~**150** (rule of thumb, not a hard limit — [zones-and-performance.md](zones-and-performance.md)) |
| Zones per map           | ≤ ~**64**; ~3-zone practical see-through depth (a rule of thumb, not a hard cap) |
| Mover keyframes         | max **8** |
| Texture size            | power-of-two, **≤ 256** (larger won't render on UE1) |
| `Engine.Light` defaults | Radius **64**, Brightness **64**, Hue **0**, Saturation **255**; reach ≈ (Radius+1)×25 |

## Reading any other default

uedcli decodes a class's default properties offline, with no editor. An unset property resolves to its
class default:

```
bin/uedcli actor build <Package.Class> | actor add - | actor prop get - <Prop>
```

For example, `actor build Engine.Light | actor add - | actor prop get - LightRadius` prints `64`. Use
this route whenever you need a number this page doesn't list. (`class show` prints property names and
types only — the values come from `actor prop get` on a built instance.)

## Related

- [geometry-and-bsp.md](geometry-and-bsp.md) — why on-grid, power-of-two matters.
- [../deusex/human-scale.md](../deusex/human-scale.md) — DX player size, jump, step, door presets.
