# Recipe: a Deus Ex style door  [DX]

A door in Deus Ex is a **`DeusExMover`** — a brush promoted to a mover actor, with two keyframes
(closed and open) and DX door properties (lock, pick strength, blow-up strength, key). This is the
single most common interactive object in a DX level, and the one most worth getting right.

> **What the editor makes you do vs. what uedctl does.** In UnrealEd you build an Addition brush,
> texture it, size the red brush a little larger, hit **Intersect** to snap it to the door shape,
> select `DeusExMover` in the class browser, hit **Create Mover**, then delete the leftover Addition
> brush. **uedctl collapses that entire ritual into one generator verb:** `brush build cube
> --mover-class DeusEx.DeusExMover`. There is no Intersect step, no leftover brush, no Create-Mover
> button — the generator emits a mover actor directly.
>
> **Exception — a door with a WINDOW in it.** A plain slab needs no intersect, but a door that is not a
> single convex box (a glass window, a grate, a cutout) *is* a composite, so you build the pieces
> (solid slab + subtracted opening + **semisolid** glass pane) and `brush intersect … --mover-class
> DeusEx.DeusExMover` them into the one mover brush. The weld keeps per-face solidity, so the glass
> faces stay semisolid + translucent inside a solid frame — and no separate glass actor is needed (one
> couldn't ride the mover anyway). Full recipe:
> [../../general/recipes/glass.md](../../general/recipes/glass.md#glass-in-one-brush-the-intersect-composite-window).

## Procedure

1. **Decide the door's size and pose.** A DX door is typically **128×64×4** (or 144×72). Think of the
   brush as the closed slab, standing in the doorway you already subtracted. Author it on the 16-uu
   grid.
2. **Build the door as a `DeusExMover` brush** at its closed position. Texture it with `--texture` now,
   or retexture later with `brush poly set` — **uedctl can edit a mover's faces any time** (the "surfaces
   frozen after Add Mover" limit is a GUI-editor thing, not a uedctl one). Wood (`CoreTexWood`) and metal
   (`CoreTexMetal`) sets are the usual starting points.
3. **Set the closed pose as key 0 and the open pose as key 1.** Key 0 is the base pose (where you
   built it). Key 1 is where the door travels to when triggered:
   - **Swinging door** — rotate the slab **90°** off base (`mover key rotate … 1 --from-base --to
     0,16384,0`; 16384 units = 90°) about its hinge edge.
   - **Sliding door** — translate it its own width/height (e.g. slide up `--from-base --to 0,0,128`,
     or sideways into a wall pocket you subtracted for it).
   A DeusExMover allows up to **8 keyframes (0–7)**; a door uses 2 (the `NumKeys` default), so no
   count change is needed — you just edit key 1. To use more keys, raise `NumKeys` first with
   **`mover key count <name> <n>`** (or the equivalent `actor prop set <name> NumKeys=<n>`).
4. **Make it behave like a door.** Set `bIsDoor=True`. Then choose its security:
   - `bLocked=True` to start locked; `lockStrength` (0.0–1.0) sets lockpick difficulty (0.10 = 10%,
     one lockpick for an untrained player). `bPickable=False` to forbid picking entirely.
   - `doorStrength` (0.0–1.0) sets blow-up resistance (0.25 = 25%); `bBreakable=False` to make it
     indestructible.
   - `bOneWay=True` restricts opening to the side the mover's arrow points.
5. **Choose the crush behavior.** So a closing door doesn't stop dead when the player stands in it,
   set `MoverEncroachType=ME_IgnoreWhenEncroach` (a very common DX setting for two-way bump doors).
6. **(Optional) Give it a `Tag`** so a keypad, security console, or trigger can control it (see
   [`keypad-and-locks.md`](keypad-and-locks.md) and [`security-camera.md`](security-camera.md)).
7. **(Optional) Require a key** — set `KeyIDNeeded` to a `name`; a matching `NanoKey.KeyID` then unlocks it
   (see [`nanokey.md`](nanokey.md)).

## With uedctl

```bash
# 1-2. Build the door mover at its closed pose, textured, and write it into the trunk.
#      `actor add -` prints the allocated name (e.g. DeusExMover0) — capture it.
brush build cube --width 4 --breadth 64 --height 128 \
  --mover-class DeusEx.DeusExMover \
  --texture CoreTexWood.ClenWoodDoor_A --at 512,0,64 | actor add -
#   -> DeusExMover0

# 3. Key 0 is the built (closed) pose; key 1 already exists (NumKeys defaults to 2). Set its OPEN
#    pose. Swinging door: 90° of yaw off the base (--from-base; unreal rotation units, 16384 = 90°).
mover key rotate DeusExMover0 1 --from-base --to 0,16384,0
#    ...or a sliding door instead: --from-world is the ABSOLUTE world pose (base is at 512,0,64), so
#    sliding 128 up means z=192 (equivalently --from-base --to 0,0,128):
# mover key move DeusExMover0 1 --from-world --to 512,0,192

# 4-5. Door properties.
actor prop set DeusExMover0 \
  bIsDoor=True bLocked=True lockStrength=0.10 \
  doorStrength=0.25 bBreakable=True bOneWay=False \
  MoverEncroachType=ME_IgnoreWhenEncroach

# 6. Tag it so devices/triggers can reach it (optional).
actor prop set DeusExMover0 Tag=Door_Lab

# 7. Require a nanokey instead of / in addition to a lockpick (optional).
actor prop set DeusExMover0 KeyIDNeeded=lab_key

# Inspect the keyframes you authored:
mover key list DeusExMover0
```

## Properties reference

| Property            | Meaning                                                                             | Typical |
| ------------------- | ----------------------------------------------------------------------------------- | --- |
| `bIsDoor`           | Marks the mover as a door                                                           | `True` |
| `bLocked`           | Starts locked                                                                       | `True` for a secured door |
| `lockStrength`      | Lockpick difficulty, 0.0–1.0                                                        | `0.10` (one lockpick, untrained) |
| `bPickable`         | Can be lockpicked at all                                                            | `True` |
| `doorStrength`      | Resistance to being blown up, 0.0–1.0                                               | `0.25` |
| `bBreakable`        | Can be destroyed                                                                    | `True` |
| `bOneWay`           | Opens only from the arrow side                                                      | `False` |
| `KeyIDNeeded`       | Matching `NanoKey.KeyID` unlocks it                                                 | (blank) |
| `MoverEncroachType` | What happens when it hits the player                                                | `ME_IgnoreWhenEncroach` |
| `NumKeys`           | Keyframe count (2..8) — set with **`mover key count`** or `actor prop set NumKeys=` | 2 |
| `Tag`               | Name that keypads/consoles/triggers target                                          | (as needed) |

## Caveats and gotchas

- **The rotation pivot.** In the editor you set a swinging door's hinge by clicking a pivot vertex
  before rotating key 1. Model-side the mover rotates about its `PrePivot`, so a door built centred
  swings about its middle. Either position the brush so its origin sits on the hinge edge, or build
  the door with **`brush deintersect --pivot`** (below), which writes the `PrePivot` for you. See the
  movers guide in [`../../general/`](../../general/) for the pivot details.
- **A mover is lit from its key-0 pose only** — a door can look black in its open pose ("black door").
  Fix with `Unlit` surfaces, a Special-Lit light, or `bDynamicLightMover=True`.
- **Reset any scale/rotation before building.** uedctl's generator emits a clean brush, so this is a
  non-issue here — but it is the reason the editor tutorial insists on Reset → All.
- **Textures on a mover.** Pass `--texture` on `brush build`, or edit faces later with `brush poly set` —
  uedctl can retexture a mover at any time. (The "can't re-surface after Add Mover" restriction is
  GUI-editor-only, not a uedctl limitation.)

## Fitting a door to an existing doorway (`brush deintersect`)

When the doorway is already carved into the world, you do not have to measure a slab by hand — the
**void itself is the door**. Pipe the doorway's subtractive brush(es) through `brush deintersect`
and you get the solid plug that exactly fills them, already a Mover:

```bash
uedctl actor find --folder castle.gate | uedctl actor show - \
  | uedctl brush deintersect - --mover-class DeusEx.DeusExMover \
        --pivot min --texture CoreTexWood.ClenWoodDoor_A \
  | uedctl actor add -
#   -> DeusExMover1
uedctl mover key rotate DeusExMover1 1 --from-base --to 0,16384,0
```

Why the flags matter here:

- **`--pivot min`** puts the rotation centre on the doorway's low corner — the hinge edge — so key 1's
  90° yaw swings the door instead of spinning it about its middle. (`--pivot` accepts
  `center`/`min`/`max` or an explicit `X,Y,Z`.)
- **Solidity is automatic — no flag needed.** A `deintersect` plug's faces all come from *subtractive*
  brushes, which the per-face rule forces to **solid**, so the door is solid without asking.
  (`--solidity` is in fact **rejected with `--mover-class`**: a mover always keeps the source per-face
  solidity. If you deliberately weld in a semisolid pane — a glass window — it stays semisolid, which
  **still blocks**; only a *nonsolid* face is walk-through.)
- **`--texture`** retextures every face of the plug. Without it each face keeps the texture of
  the source surface it was cut from, so a door carved out of wall geometry comes out wearing
  the wall. The ref is validated at author time, so a typo fails loudly rather than silently.
- The plug lands at the doorway's own position; pass `--at X,Y,Z` to place it somewhere else.

See [`../../../usage.md`](../../../usage.md) for the full verb reference.

## See also

- [`../classes.md`](../classes.md) — the `DeusExMover` family (`BreakableGlass`, `BreakableWall`) and the
  separate lift movers (`ElevatorMover`, `MultiMover`). (`CEDoor` is a third-party `CaroneElevatorSet`
  mod class, covered in the elevator recipe — not in `classes.md`.)
- [`keypad-and-locks.md`](keypad-and-locks.md) — wire a keypad or control panel to this door.
- [`nanokey.md`](nanokey.md) — make a key that opens it.
- [`../../general/`](../../general/) — the engine movers guide (keyframes, pivots, encroachment).
