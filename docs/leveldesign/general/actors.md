# Actors: collision, decorations, spawns, pathing  [ENGINE]

Actors make a level playable on top of CSG geometry: collision, props, spawn points, and the
navigation network the AI walks.

## Collision is a cylinder

Every actor collides as an upright cylinder — `CollisionRadius` and `CollisionHeight` (total height
= 2 × Height), always upright regardless of the actor's rotation. There is no per-poly or per-box
actor collision in UE1 (that's UE2); a mesh's shape never collides, only its cylinder.

### Blocking flags

UE1 splits colliding from blocking:

- **Colliding** — `bCollideActors` (master switch; required for any `Touch()` event), `bCollideWorld`,
  `bCollideWhenPlacing`.
- **Blocking** — `bBlockActors`, `bBlockPlayers` (UE1 keeps them separate), and `bProjTarget` (=
  shootable / trace target).

Common recipes:

| Want                          | Set |
| ----------------------------- | --- |
| Invisible wall (small)        | a `BlockAll` actor, or a 1-unit cube |
| Invisible wall (large area)   | an Invisible Collision Hull (a semisolid, all faces invisible) — must not touch walls or zone boundaries |
| Non-blocking decoration       | all blocking flags off |
| Shootable but walk-through    | collide + `bProjTarget` on, blocking off |
| Glass / grille you can't pass | a visual sheet + a collision hull behind it — sheets never block on their own ✅ |

```
brush build cube --csg add --solidity semisolid --width 128 --breadth 8 --height 128 | actor add -    # then flag its faces invisible → an ICH
actor prop set Crate1 bBlockPlayers=True bProjTarget=True
```

## Decorations

Prop actors placed into the world:

- `DrawType` = `DT_Sprite` / `DT_Mesh` / `DT_Brush` / `DT_None`; set `Mesh` for a mesh prop.
- `DrawScale` — a single uniform float (there is no `DrawScale3D` in UE1 — that's UE2).
- `Skin` / `MultiSkins[]` — the prop's textures.
- Breakables: the `contents` / `content2` / `content3` + `EffectWhenDestroyed` loot fields.
  `Engine.Decoration` has no `Health`; damageability in DX is `DeusExDecoration.HitPoints`.
  `bPushable` makes it shovable.

```
# Engine.Decoration is ABSTRACT — place a concrete subclass (DX props are DeusExDecoration subclasses)
actor build <ConcreteDecorationSubclass> --prop DrawScale=1.5 --at 256,256,0 | actor add -
```

> Deus Ex props are the `DeusExDecoration` family (with a highlight name label and `HitPoints`).
> `bInvincible` (make a decoration indestructible) is a `DeusExDecoration` property, not on
> `Engine.Decoration` — see [../deusex/](../deusex/).

## PlayerStart

Where players spawn — a NavigationPoint:

- Place it 40 uu above the floor (the spawn cylinder sits above the surface). ✅
- The player spawns facing the actor's Yaw — point it where you want them to look.
- Place more PlayerStarts than the max simultaneous players; `bEnabled`,
  `bSinglePlayerStart` / `bCoopStart` gate which get used.

```
actor build Engine.PlayerStart --at 256,256,40 --rotate 0,16384,0 | actor add -   # Yaw (middle) = facing; 16384 = 90° (unreal rotation units)
```

## Pathing (NavigationPoints)

AI paths compile into reachspecs — line-of-sight-plus-traversable links storing each connection's
width and height so bots know they fit. NPCs will not move without a path network.

- Drop `PathNode` actors 300–700 uu apart (≤300–350 on ramps and stairs; keep ≥50 uu apart or
  you get a "paths too close" error, and ≥50 from corners). Each node must be visible from its
  neighbour.
- Rebuild paths with console `PATHS BUILD` (constructs the reachspecs; `PATHS DEFINE` alone only
  spawns marker nodes, no reachspecs). `level materialize` does not run the paths pass, so a
  materialized map has no reachspecs and AI pawns won't move until paths are built in the editor.
  Debug with Show Paths.
- Per-node tuning: `bOneWayPath`, `ExtraCost`. (The UT/UE2 `bNoAutoConnect` / `ForcedPaths[4]` /
  `ProscribedPaths[4]` do **not** exist on this build's `Engine.PathNode`.)
- Related NavigationPoints: `PlayerStart`, `InventorySpot` (auto-made at pickups), `LiftCenter` /
  `LiftExit` (so bots ride a lift), `Teleporter`, `Engine.PatrolPoint` (NPC patrol routes). **There is no
  `Ladder` navigation node** — climbable ladders are texture-driven (a `Ladder`-group texture), see
  [../deusex/](../deusex/).

```
actor build Engine.PathNode --at 256,256,40 | actor add -
actor build Engine.PathNode --at 256,640,40 | actor add -     # ~384 uu along — within 300–700
```

## KeyPoint markers

Invisible marker actors for sound and scripting: `AmbientSound` (and DX's `AmbientSoundTriggered`),
`InterpolationPoint`, `SpecialEvent`, `BlockAll` / `BlockMonsters` / `BlockPlayer`,
`LocationID` (names a HUD region).

## Physics note

`Physics` controls how an actor moves: `PHYS_None` (default for static props), `PHYS_Walking` (pawns —
needs a `Base`), `PHYS_Falling` (drop-and-rest debris — obeys zone gravity), `PHYS_Rotating` (spinning
fans/pickups — uses `RotationRate`), `PHYS_MovingBrush` (every mover), and others. `bStatic` marks an
actor fully inert (no Tick/Timer/trigger) — don't set it just to stop a pickup spinning.

## Related

- [movers.md](movers.md) — animated brushes (a different actor kind).
- [human-scale.md](human-scale.md) — the collision-cylinder and spacing numbers.
