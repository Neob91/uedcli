# Movers — doors, lifts, crushers  [ENGINE]

A mover is a single brush promoted to an actor that animates between keyframed poses: doors, lifts,
crushers, drawbridges, rotating fans. The UE1 base class is `Engine.Mover` (`class Mover extends
Brush`); games subclass it. This DX build's `Engine.u` ships only the base `Mover`; stock Unreal/UT99
also ships `RotatingMover`/`LoopMover`/etc., absent in the DX substrate. 🔬

> Deus Ex uses its own `DeusExMover` door/panel family (`BreakableGlass`, `BreakableWall`, doors with
> `bIsDoor`/`bLocked`/`KeyIDNeeded`); `ElevatorMover` and `MultiMover` are separate `Engine.Mover`
> subclasses, not `DeusExMover` — see [../deusex/](../deusex/).

## Building a mover

Build the brush with `--mover-class` and add it, then author keyframes model-side:

```
brush build cube --mover-class Engine.Mover --width 64 --breadth 8 --height 112 | actor add -   # prints the mover's name
mover key move <that-name> 1 --from-base --to 0,0,112        # key 1 = open pose (offset from base): slide UP 112, a portcullis-style door. Slide along the door's own plane or up — NOT along its thin normal.
```

`mover key` is a family of model-side verbs: `count`, `move`, `rotate`, `remove`, `list`.

> The one brush can be a composite. For a door with a window, a grate with a frame, any non-box
> mover: build the pieces (solid frame + subtracted openings + semisolid glass/detail panes) and
> `brush intersect` them into the single mover brush, which keeps each face's own solidity (solid
> frame, semisolid+translucent glass). This is the only way to get glass in a mover — a separate
> glass actor can't ride it. Full recipe:
> [recipes/glass.md](recipes/glass.md#glass-in-one-brush-the-intersect-composite-window).

## Keyframes

- Maximum 8 keyframes (0–7); minimum 2. `NumKeys` is the waypoint count — set it with `mover key
  count <name> <n>` (or the equivalent `actor prop set <name> NumKeys=<n>`). A fresh mover has
  `NumKeys=2` (keys 0 and 1), so a two-pose door needs no count change.
- Key 0 is the base (closed / bottom) pose. Additional keys are stored as offsets from the base —
  uedcli stores the base at key 0 and never emits an absolute `BasePos`/`BaseRot`. `mover key
  move`/`rotate <i>` edit an existing key `1 ≤ i < NumKeys` (raise the count first with `mover key
  count`); `--to` needs a frame — `--from-base` (coords are the offset from base) or `--from-world`
  (an absolute world pose, uedcli subtracts the base). `--by` takes a frame-agnostic delta.
- The editor's GUI "record" flow is inverted: you add the mover (key 0), then select the target key
  before moving the brush — get the order backwards and you move the base. uedcli's `mover key
  move …` names the target key + pose directly.

```
# a two-pose door: closed (key 0, implicit) then open by sliding UP (a portcullis)
brush build cube --mover-class Engine.Mover --width 64 --breadth 8 --height 112 | actor add -   # prints the mover's name
mover key move <that-name> 1 --from-base --to 0,0,112        # open pose as an offset from base (slides up its own height)
```

## Triggering

Movers use standard `Tag` / `Event` wiring:

- Give the mover a `Tag`; give a `Trigger` (or button, or another mover) an `Event` with the same
  name — firing the event moves the mover.
- A mover fires its own `Event` when its keyframes finish — chain movers this way.

```
actor prop set DoorMover Tag=frontdoor InitialState=TriggerOpenTimed
actor build Engine.Trigger --prop Event=frontdoor --at 0,-64,32 | actor add -
```

`InitialState` picks the mover's behaviour: `BumpOpenTimed` (default — opens when touched),
`TriggerOpenTimed` (opens on its event), `StandOpenTimed` (opens while stood on — lifts),
`TriggerToggle`, `TriggerControl`, `TriggerPound`, `BumpButton`, `None`. ✅

## Encroachment

`MoverEncroachType` sets the reaction when the mover runs into a pawn — distinct from
return-groups, don't conflate them:

| Value                             | Behaviour |
| --------------------------------- | --- |
| `ME_ReturnWhenEncroach` (default) | reverses toward the previous key (normal doors) |
| `ME_CrushWhenEncroach`            | keeps going and damages (crushers) |
| `ME_StopWhenEncroach`             | halts until clear |
| `ME_IgnoreWhenEncroach`           | passes through — two-way bump doors |

## The "black door" fix

A mover is lit from its key-0 pose only, so a door swinging into a differently-lit spot can render
solid black. Fixes:

- Flag the mover's surfaces `Unlit` (simplest), or use Special-Lit rings around it.
- Set `bDynamicLightMover=True` so it re-lights as it moves.
- Or set `WorldRaytraceKey` / `BrushRaytraceKey` to pick a better pose to light from.

```
brush poly find DoorMover | brush poly set - --add-flag Unlit
# or:
actor prop set DoorMover bDynamicLightMover=True
```

## Related

- Full builds: [recipes/mover-door.md](recipes/mover-door.md), [recipes/lift.md](recipes/lift.md).
- Movers don't cut BSP — good for detail that shouldn't add nodes ([geometry-and-bsp.md](geometry-and-bsp.md)).
