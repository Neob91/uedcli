# Recipe: a lift (elevator)  [ENGINE]

A platform that carries the player between floors. Same mover mechanism as a
[door](mover-door.md) — one brush, key 0 = bottom, key 1 = top — but with a lift `InitialState`
so it rises when stood on (or triggered). Read [../movers.md](../movers.md) first.

## What you're building

1. A platform brush turned into a mover.
2. Key 0 = bottom (start) pose, key 1 = top pose.
3. A lift `InitialState` (`StandOpenTimed` = rises when stood on; or a trigger).
4. For bot navigation: `LiftCenter` / `LiftExit` NavigationPoints so AI rides it.

## Editor procedure

1. Build the platform brush — a squashed cube short enough to walk onto, sized to the shaft.
   Reset scaling first so collision behaves.
2. Position it at the bottom floor, where the player boards.
3. Promote it to a mover ("Add Mover") — it turns purple.
4. Set the poses (inverted flow): select Key 1 first, translate the mover vertically up
   to the top floor, then select Key 0 to lock in the bottom start pose.
5. Set `InitialState` to `StandOpenTimed` (rises while stood on, returns after), or wire a
   `Trigger` (button) as in the [door recipe](mover-door.md).
6. Rebuild and test (walk on / trigger).

Tip: for bots and DX NPCs to use the lift, add a `LiftCenter` on the platform and a `LiftExit` at
each floor, tagged to the mover, then rebuild paths.

## uedcli pipeline

```
# 1. the platform as a mover, at the bottom floor
brush build cube --mover-class Engine.Mover --height 16 --width 128 --breadth 128 --at 512,512,8 | actor add -   # e.g. Mover1

# 2. key 1 = top pose (it already exists — NumKeys defaults to 2). --from-world takes an ABSOLUTE
#    world pose, not a delta: the platform base sits at z=8, so the top floor 384 uu up is z=392
#    (equivalently --from-base --to 0,0,384).
mover key move Mover1 1 --from-world --to 512,512,392

# 3. rises when stood on (or use a trigger as in mover-door.md)
actor prop set Mover1 InitialState=StandOpenTimed MoverEncroachType=ME_StopWhenEncroach

# 4. (optional) lift navigation for AI
actor build Engine.LiftCenter --prop LiftTag=lift1 --at 512,512,24 | actor add -    # on the platform
actor build Engine.LiftExit   --prop LiftTag=lift1 --at 512,720,8   | actor add -   # beside the shaft, bottom floor
actor build Engine.LiftExit   --prop LiftTag=lift1 --at 512,720,392 | actor add -   # beside the shaft, top floor (one LiftExit per floor, on the walkable floor — not over the shaft)
actor prop set Mover1 Tag=lift1

# 5. build
level materialize --out maps/mylevel.dx
```

- `ME_StopWhenEncroach` keeps the lift from crushing a player against the ceiling; pick the
  `MoverEncroachType` that fits ([../movers.md](../movers.md)).
- Same black-door self-lighting fix applies if the platform renders dark.

## Related

- [mover-door.md](mover-door.md) — the shared mover mechanism and trigger wiring.
- [../movers.md](../movers.md) — keyframes, `InitialState`, encroachment.
- [../actors.md](../actors.md) — `LiftCenter`/`LiftExit` and pathing.
