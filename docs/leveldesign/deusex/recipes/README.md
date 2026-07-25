# Deus Ex recipes  [DX]

Task-by-task walkthroughs for common Deus Ex authoring jobs. Each recipe is the **complete
procedure** — numbered steps that explain *what* you are building and why — followed by a **"With
uedctl"** block that gives the exact verb pipeline. Where a classic UnrealEd tutorial relies on a
GUI-only gesture (grabbing a brush with Intersect, clicking a pivot vertex, snapping to grid), the
recipe says so and gives the closest model-side path.

You author the git-tracked **T3D trunk** with small composing verbs; the editor is touched only to
`level materialize` / `level preview`. Nothing here is done by hand inside the editor.

## How these recipes read

Every recipe uses the same four verb families (full reference in
[`../../general/`](../../general/) and [`../classes.md`](../classes.md)):

| Verb                                                                                   | Role |
| -------------------------------------------------------------------------------------- | --- |
| `brush build <shape> … \| actor add -`                                                 | *generator → writer*: print a CSG brush or mover, write it into the trunk |
| `brush build <shape> --mover-class <Pkg.Class> \| actor add -`                         | build a **mover** (door/lift/breakable) directly — no editor Intersect/Create-Mover ritual |
| `actor build DeusEx.<Class> --prop K=V --at X,Y,Z \| actor add -`                      | place a point actor (device, pickup, NPC, ZoneInfo) with initial props |
| `brush poly find … \| brush poly set - --texture …`                                    | per-surface texture + flag edits |
| `actor prop set <name> K=V`, `mover key count/move/list`, `actor order --first/--last` | per-actor property, keyframe, and CSG-order edits |

`actor add -` prints the **allocated actor name(s)** to stdout — capture them and feed them to
`actor prop set` / `mover key`. Human-readable summaries go to stderr, so the pipe stays clean.

> **Rotation is in unreal rotation units — a full turn is 65536.** So **90° = 16384**, 45° = **8192**,
> 22.5° = **4096**, 180° = **32768**, 270° = **49152**. This one unit system is what everything uses:
> the `--rotate` flag (`actor build`/`brush build`), `--rot`/`--by`/`--to` on `mover key`, `actor
> rotate`, the `--prop Rotation=Pitch,Yaw,Roll` sugar, AND stored property values you pass verbatim
> (a `SecurityCamera`'s `cameraFOV`/`swingAngle`, a literal `Rotation=(Yaw=16384)`). Rotators are
> `Pitch,Yaw,Roll`. (Note: *mesh-import* `#exec` angles are a different, 8-bit scale where 64 = 90° —
> that's the asset pipeline, not level authoring.)

> **On-grid by construction.** The editor's "snap to grid" step has no uedctl equivalent because you
> author coordinates directly — choose integer, power-of-two positions (16/32/64/128/256) and your
> geometry is already on-grid. Off-grid coordinates are the #1 cause of BSP holes (see
> [`../../general/geometry-and-bsp.md`](../../general/geometry-and-bsp.md)).

## The recipes

| Recipe                                       | What you build |
| -------------------------------------------- | --- |
| [`deusex-door.md`](deusex-door.md)           | A `DeusExMover` door — swinging or sliding, lockable, pickable, breakable, key-openable |
| [`elevator.md`](elevator.md)                 | An `ElevatorMover` lift, and the Carone-elevator multi-floor setup (doors, call buttons, sequence triggers) |
| [`ladder.md`](ladder.md)                     | A climbable ladder — a **texture**, not an actor |
| [`keypad-and-locks.md`](keypad-and-locks.md) | Keypads, hackable devices, control panels + laser/beam triggers, and locking a door to them |
| [`security-camera.md`](security-camera.md)   | A `SecurityCamera` wired to a `ComputerSecurity` console, plus auto-turrets |
| [`breakables.md`](breakables.md)             | Breakable glass, breakable walls, and loot-spilling breakable crates |
| [`nanokey.md`](nanokey.md)                   | A `NanoKey` that opens a locked door — placed in the world or carried by an NPC via `PickupDistributor` |
| [`datacube.md`](datacube.md)                 | DataCubes, books, and newspapers — in-world text with DX markup |
| [`npc-patrol.md`](npc-patrol.md)             | A `ScriptedPawn` guard walking a `PatrolPoint` chain, with player-hostile alliances |
| [`water-zone.md`](water-zone.md)             | A swimmable water volume, and pain/gas zones |
| [`particles.md`](particles.md)               | DX particle emitters — steam/dust, water drips, electricity arcs, fire |

## The real DX numbers you will need

Verified against the shipped `DeusEx.u` (decode any other default with `actor build DeusEx.<Class> |
actor add - | actor prop get - <Prop>`):

- **Player collision cylinder:** 40 wide × 95 tall (Radius 20, Height 47.5). Eye height ~87 uu above
  the floor; `MaxStepHeight=25`; `JumpZ=300`.
- **1 ft = 16 uu** (the DX grid unit). A DX door is **144×72 or 128×64**, 1–8 uu thick. Doorway ~128
  tall × 64 wide. Ceiling min 83, recommended 128.
- **Device strengths (fraction of full):** lockpick doors ~**0.20**, hackable devices ~**0.20**,
  door blow-up `doorStrength` ~**0.25**, breakable wall ~**0.40**, auto-turret **fixed 0.50** hack.
- **SecurityCamera:** `cameraFOV` **4096** (22.5°), `cameraRange` **1024**, `swingAngle` **8192**
  (45°).

## See also

- [`../classes.md`](../classes.md) — the DX class catalog these recipes place.
- [`../npcs.md`](../npcs.md) — the full `ScriptedPawn` reference behind the patrol recipe.
- [`../../general/`](../../general/) — the engine-generic craft (CSG, zones, lighting, movers) every
  recipe builds on. **Read the geometry and movers guides first.**
