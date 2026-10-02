# Recipe: a door mover  [ENGINE]

A door that swings or slides open. One brush promoted to a `Mover`, with key 0 = closed and key 1 =
open, triggered by `Tag`/`Event`. Read [../movers.md](../movers.md) first for the keyframe model and
the inverted-record trap.

## Editor procedure

1. Build the door brush (e.g. 128×128×16) somewhere clear, texture it, check its alignment.
2. Promote it to a mover ("Add Mover") — it turns purple.
3. Set the poses (mind the inverted flow). With the mover selected:
   - Select Key 1 first, then move/rotate the brush to the open pose (for a swing door, rotate
     about the hinge edge; for a slide door, translate it).
   - Then select Key 0 to return to (and lock in) the closed base pose.
4. Wire the trigger (for an automatic door): place a `Trigger`, set its `Event` (e.g. `frontdoor`),
   set the mover's `Tag` to the same name, and set the mover's `InitialState` to `TriggerOpenTimed`.
   Duplicate the trigger on the far side so it opens from either approach. (For a bump-to-open door, skip
   the trigger and leave `InitialState=BumpOpenTimed`.)
5. Set the reaction with `MoverEncroachType` (default `ME_ReturnWhenEncroach` — reopens if it hits
   someone).
6. (Optional) Give the mover open/close sounds; rebuild and test.

## uedcli pipeline

```
# 1. build the door as a mover (one brush)
brush build cube --mover-class Engine.Mover --height 128 --width 64 --breadth 8 --at 256,0,64 | actor add -   # e.g. Mover2

# 2. key 1 = open pose (it already exists — NumKeys defaults to 2). --from-world takes an ABSOLUTE
#    world pose, not a delta. This door slides UP (a portcullis): base is at 256,0,64 and it's 128
#    tall, so the open pose is 256,0,192 (equivalently --from-base --to 0,0,128). Slide along the
#    door's own plane or up — NOT along its thin normal (Y here), which would park it inside the room.
mover key move Mover2 1 --from-world --to 256,0,192
#    (for a SWING door instead, key the open pose as a rotation: `mover key rotate Mover2 1 --by 0,16384,0`
#     — 16384 = 90°. NOTE: rotation is about the mover's own PIVOT (its Location/center by default), not a
#     hinge edge. To hinge on an edge, set `--prop PrePivot=X,Y,Z` to shift the rotation center to the
#     hinge (or model a double-width panel with the far half buried in the wall). A panel *centered* on the
#     hinge would sweep through the wall on both sides.)

# 3. trigger wiring: mover Tag ↔ trigger Event; open on trigger
actor prop set Mover2 Tag=frontdoor InitialState=TriggerOpenTimed MoverEncroachType=ME_ReturnWhenEncroach
actor build Engine.Trigger --prop Event=frontdoor --at 256,-96,48 | actor add -

# 4. build
level materialize --out maps/mylevel.dx
```

- Max 8 keyframes. A simple door uses just key 0 and key 1.
- If the door renders black after moving, it's the mover self-lighting quirk — flag its faces
  `Unlit` or set `bDynamicLightMover=True` ([../movers.md](../movers.md)).
- Deus Ex doors are the `DeusExMover` family (`bIsDoor`, `bLocked`, `KeyIDNeeded`, …) instead of
  `Engine.Mover` — see [../../deusex/](../../deusex/).

## Related

- [../movers.md](../movers.md) — keyframes, encroachment, triggering, the black-door fix.
- [lift.md](lift.md) — the same mechanism for a vertical lift.
- [the door mover flow](../../../usage/door-mover-flow.md) — the terse CLI-only version of this recipe.
