# Human scale — the real DX numbers  [DX]

Build to the player's actual size, not by eye. These figures were **decoded by uedcli straight from the
shipped `DeusEx.u`** — they are the game's real defaults, not tutorial lore. Getting scale right is what
separates a playable level from one where the player can't fit through a door or climb a step.

**16 units = 1 foot.** DX authors size everything — doors, steps, panels, ceilings — in this convention.
(1 uu = 0.75 in; 1 m ≈ 52.5 uu; 256 uu = 16 ft; world max 65536 uu per axis.)

---

## The player

| Quantity             | Value |
| -------------------- | --- |
| Collision cylinder   | **40 wide × 95 tall** (`CollisionRadius` 20 × `CollisionHeight` 47.5) |
| Eye height           | **~87 uu above the floor** (`BaseEyeHeight` 40 above center) |
| Jump                 | `JumpZ` **300** |
| Ground / water speed | `GroundSpeed` 320 / `WaterSpeed` 300 |
| **Auto-step height** | `MaxStepHeight` **25** — the player walks up steps ≤25 uu without jumping |
| Mass                 | 150 |

An `MJ12Troop` (and other human pawns) share the player's 40×95 cylinder — size guard posts and
corridors for it too.

## Architecture

| Element            | Recommended |
| ------------------ | --- |
| **Stairs**         | rise **16** (= 1 ft = the default grid); run **32** comfortable (16 steep, 48–64 stately). Keep any single step ≤ `MaxStepHeight` 25, or the player must jump. |
| **Ceiling**        | **128** recommended, **~96–100** minimum — the player cylinder is **95 tall**, so it can't stand under 95. (The "83" minimum seen in UT tutorials is for UT's shorter 78-tall pawn — do not use it for DX.) |
| **Corridor width** | **≥48**. |
| **Doorway**        | ~**128 tall × 64 wide**. DX doors are **144×72** or **128×64**, 1–8 uu thick. |
| **Grid**           | work on **16** for general geometry; drop to 8/4/2 for detail. Never build sub-grid. |

## DX device strengths & camera

These govern how hard the player's skills/tools have to work — tune obstacles against them:

| Device                          | Strength |
| ------------------------------- | --- |
| Lock (pick)                     | 20% (`DeusExMover.lockStrength` 0.2) |
| Hack (electronic)               | 20% |
| Door (force)                    | 25% |
| Wall (`BreakableWall`, crowbar) | 40% |
| Turret (hack)                   | 50% (fixed) |

**`SecurityCamera`:** `cameraFOV` **4096 = 22.5°** cone, `cameraRange` 1024, `swingAngle` 8192 = 45°
sweep. (FOV is in engine angle units: 65536 = 360°.)

---

## Decode any other default yourself

Every one of these numbers came from the same offline route — no editor needed. To read *any* class
default (a pawn's health, a decoration's collision extent, a light's radius):

```
bin/uedcli actor build DeusEx.<Class> | actor add - | actor prop get - <Prop>
```

An unset property resolves to its class default, which is exactly the shipped value. Note that
`class show <Class>` prints only property **names and types** — the **values** come from the
`actor prop get` route above.

A few more decoded this session, for reference: `Engine.Light` defaults `LightRadius` 64 / `LightBrightness`
64 / `LightHue` 0 / `LightSaturation` 255 / `LT_Steady` / `LE_None`; `NanoKey` cylinder 2.05×3.11;
`ParticleGenerator` `frequency` 1 / `checkTime` 0.1 / `particleLifeSpan` 4 / `riseRate` 10 /
`particleDrawScale` 0.1.

---

## See also

- [`classes.md`](classes.md) — the classes whose defaults you decode.
- [`design-philosophy.md`](design-philosophy.md) — designing obstacles against device strengths.
- [`../general/`](../general/) — engine-level geometry, grid, and BSP craft.
