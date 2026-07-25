# Recipe: an elevator  [DX]

An elevator is an **`ElevatorMover`** (a direct `Engine.Mover` subclass) whose keyframes are the floor
positions, driven by triggers and buttons. There are two levels of ambition:

- **A simple platform/shaft lift** — one `ElevatorMover`, one keyframe per floor, a `SequenceTrigger`
  per floor, and a button per floor. This uses only stock DX classes.
- **A full Carone elevator** — the community **CaroneElevatorSet** mod adds `CaroneElevator`,
  `CESequenceTrigger`, `CEDoor` (auto-managed floor doors), `CEDoorButton`, call buttons, and inner
  doors that ride with the car. It requires shipping `CaroneElevatorSet.u` with your map; uedctl resolves
  the classes as long as that package is on the **composed search path** (no `EditPackages` ini edit —
  that's a `ucc make` / GUI-editor concept, not part of the uedctl flow).

Both are authored the same way in uedctl: build the mover, key the floors, place trigger/button
actors, wire tags and events.

## Part 1 — a basic lift

### Procedure

1. **Carve the shaft.** Subtract a vertical shaft tall enough to span every floor, plus a doorway
   into it at each floor (line the doorways up vertically). The car needs empty space to travel
   through.
2. **Build the car as an `ElevatorMover`** (or `CaroneElevator`), fully textured, at the **bottom
   floor** — that's key 0.
3. **Set the floor count, then place each floor.** Set the waypoint count with `mover key count
   <car> N` (N = number of floors, max 8 — key 0 = floor 1). Then position each higher floor with
   `mover key move <car> <i> --to 0,0,<height> --from-base` (key 1 = floor 2, key 2 = floor 3, …),
   the height measured **from the bottom-floor base pose**. (In the UnrealEd GUI, adding a keyframe
   auto-bumps `NumKeys`; via uedctl you set the count explicitly with `mover key count`, then edit
   each key by index.)
4. **Give the car a `Tag`** (e.g. `Elevator_A`) so buttons and triggers can address it.
5. **Add a `SequenceTrigger` per floor** (`CESequenceTrigger` with the Carone mod). Each one's
   `Event` = the car's `Tag`, its own `Tag` = a floor name (e.g. `ElevatorA_Floor2`), and its
   `SeqNum` (`seqnum`) = the **keyframe index** for that floor.
6. **Add a button per floor** inside the car (`Button1`, `ButtonType=BT_1`/`BT_2`/`BT_Up`/`BT_Down`).
   Each button's `Event` = the floor's SequenceTrigger tag; its `AttachTag` = the car's `Tag` so the
   button **rides with the car**.
7. **(Optional) elevator sounds** — set the car's mover-sound properties (the *MoverSounds* **category**
   in the property browser — `OpeningSound`, `ClosingSound`, `MoveAmbientSound`, `ClosedSound`; there is
   no single property literally named `MoverSounds`) from a sound package such as `MoverSFX`.

### With uedctl

```bash
# 2. Build the car at floor 1 (key 0), textured. (There is no --hollow flag: this emits a solid
#    platform block; for a walk-in car, assemble the shell from separate wall/floor/ceiling brushes.)
#    For a BASIC lift, DeusEx.ElevatorMover is fine; for the Carone floor/inner doors in Parts 2-3,
#    build it as --mover-class CaroneElevatorSet.CaroneElevator instead (the CE* props live only there).
brush build cube --width 96 --breadth 96 --height 128 \
  --mover-class DeusEx.ElevatorMover \
  --texture CoreTexMetal.ClenGrayMetal_A --at 0,0,64 | actor add -
#   -> ElevatorMover0

# 3. Set the floor count (keys 0..2), then place each higher floor's key at its ABSOLUTE world
#    pose with --from-world (uedctl subtracts the base to store the offset). The car base sits at
#    z=64, so these are floor heights, not offsets. Raise the count first — move/rotate are edit-only.
mover key count ElevatorMover0 3               # 3 floors = keys 0,1,2
mover key move ElevatorMover0 1 --from-world --to 0,0,256   # floor 2 = key 1 (absolute z=256, i.e. 192 above floor 1)
mover key move ElevatorMover0 2 --from-world --to 0,0,448   # floor 3 = key 2 (absolute z=448, 192 above floor 2)

# 4. Tag the car.
actor prop set ElevatorMover0 Tag=Elevator_A

# 5. One SequenceTrigger per floor; SeqNum = the floor's keyframe index.
actor build DeusEx.SequenceTrigger --prop Event=Elevator_A --prop Tag=ElevatorA_Floor1 \
  --prop SeqNum=0 --at 0,200,64 | actor add -
actor build DeusEx.SequenceTrigger --prop Event=Elevator_A --prop Tag=ElevatorA_Floor2 \
  --prop SeqNum=1 --at 0,200,256 | actor add -   # (place each floor's trigger at that floor; button-fired, so exact spot is flexible)

# 6. Interior buttons, attached to the car so they ride with it.
actor build DeusEx.Button1 --prop ButtonType=BT_1 --prop Event=ElevatorA_Floor1 \
  --prop AttachTag=Elevator_A --at 40,40,80 | actor add -
actor build DeusEx.Button1 --prop ButtonType=BT_2 --prop Event=ElevatorA_Floor2 \
  --prop AttachTag=Elevator_A --at 40,56,80 | actor add -   # spaced from BT_1 so they don't overlap
```

> With the stock classes, substitute `DeusEx.ElevatorMover` for `CaroneElevator` and
> `DeusEx.SequenceTrigger` for `CESequenceTrigger`. The Carone classes only resolve if
> `CaroneElevatorSet.u` is on the editor's package path at `level materialize` time.

## Part 2 — floor doors and call buttons (Carone)

> **The car must be a `CaroneElevator` for Parts 2–3.** `CEEvents`, `bCEControlsDoors`, `CESlaveMover`,
> and `bCEControlsSlave` exist **only** on `CaroneElevatorSet.CaroneElevator` — **not** on
> `DeusEx.ElevatorMover`. `actor prop set` is schema-validated, so setting them on a stock
> `ElevatorMover` fails. Build the Part-1 car with `--mover-class CaroneElevatorSet.CaroneElevator` (the
> commands below assume that car, still named `ElevatorMover0`).

### Procedure

1. **Call buttons** — add a `Button1` on the wall at *each* floor, `Event` = that floor's sequence
   trigger tag. **Do not** set `AttachTag` (a call button stays on the wall, it must not ride the car).
2. **Floor doors** — build them as **`CEDoor`** movers (a Carone mover that auto-syncs with the car).
   A pair of half-width panels that slide inward reads as classic elevator doors. Key 0 = closed,
   key 1 = open. Give every panel at one floor the **same `Tag`** (e.g. `ElevatorA_floor1_outerdoors`).
3. **Wire the doors to the car.** On the `CaroneElevator`, set `CEEvents[i]` = the door tag for
   keyframe `i` (CEEvents[0] = floor-1 doors, CEEvents[1] = floor-2 doors, …), and set
   `bCEControlsDoors=True`.

### With uedctl

```bash
# 1. A wall call button per floor (NOT attached to the car).
actor build DeusEx.Button1 --prop ButtonType=BT_Blank --prop Event=ElevatorA_Floor1 \
  --at 0,240,80 | actor add -

# 2. A pair of CEDoor panels at a floor, same Tag; key 1 = open (slide aside).
brush build cube --width 32 --breadth 4 --height 128 \
  --mover-class CaroneElevatorSet.CEDoor --texture CoreTexMetal.ClenGrayMetal_A --at 0,-48,64 | actor add -
#   -> CEDoor0   (in the -Y shaft-opening plane: WIDE in X, THIN in Y; positions illustrative — fit your shaft)
mover key move CEDoor0 1 --from-world --to 32,-48,64      # open = slide aside in +X; y & z held
actor prop set CEDoor0 Tag=ElevatorA_floor1_outerdoors

# 3. Associate doors with the car per keyframe, and let the car drive them.
actor prop set ElevatorMover0 \
  CEEvents.0=ElevatorA_floor1_outerdoors \
  CEEvents.1=ElevatorA_floor2_outerdoors \
  bCEControlsDoors=True
```

## Part 3 — inner doors and an open/close button (Carone)

### Procedure

1. **Inner doors** ride *with* the car — build them as `CEDoor` movers, give them all one `Tag`
   (e.g. `ElevatorA_innerdoors`), and set their `AttachTag` = the car's `Tag`. They need room to move
   both open/closed **and** up/down with the car.
2. **Open/close button** — a `CEDoorButton` inside the car, `Event` = the car's `Tag`, `AttachTag` =
   the car's `Tag`. It opens the doors if closed, closes them if open, whenever the car is at a floor.
3. **Wire the inner doors** — on the `CaroneElevator`, set `CESlaveMover` = the inner-door tag and
   `bCEControlsSlave=True`.

### With uedctl

```bash
# 1. Inner doors: CEDoor movers that ride the car.
brush build cube --width 32 --breadth 4 --height 128 \
  --mover-class CaroneElevatorSet.CEDoor --texture CoreTexMetal.ClenGrayMetal_A --at 0,-40,64 | actor add -
#   -> CEDoor2   (inner doors ride the car; WIDE in X, THIN in Y, just inside the -Y wall)
mover key move CEDoor2 1 --from-world --to 32,-40,64      # open = slide aside in +X
actor prop set CEDoor2 Tag=ElevatorA_innerdoors AttachTag=Elevator_A

# 2. Interior open/close button, attached to the car.
actor build CaroneElevatorSet.CEDoorButton --prop Event=Elevator_A --prop AttachTag=Elevator_A \
  --at 40,-40,80 | actor add -

# 3. Tell the car about its slave (inner) doors.
actor prop set ElevatorMover0 CESlaveMover=ElevatorA_innerdoors bCEControlsSlave=True
```

## Properties reference

| Actor / property                                   | Meaning |
| -------------------------------------------------- | --- |
| `ElevatorMover` / `CaroneElevator`                 | The car; keyframes = floor positions; `Tag` addresses it |
| `NumKeys`                                          | Number of floors (keyframes) — set with **`mover key count <name> <n>`** (or the equivalent `actor prop set <name> NumKeys=<n>`); `move`/`rotate` are edit-only |
| `SequenceTrigger` / `CESequenceTrigger` `.SeqNum`  | Which keyframe (floor) this trigger sends the car to |
| `Button1.ButtonType`                               | `BT_1`/`BT_2`/…/`BT_Up`/`BT_Down`/`BT_Blank` — the button face |
| `Button1.AttachTag`                                | Car tag → button rides the car; omit for a fixed wall/call button |
| `CEDoor`                                           | A Carone floor/inner door the car manages automatically |
| `CaroneElevator.CEEvents[i]`                       | Door tag opened at keyframe `i` |
| `CaroneElevator.bCEControlsDoors`                  | Car auto-operates the floor doors |
| `CaroneElevator.CESlaveMover` + `bCEControlsSlave` | Inner doors that ride the car |
| `CEDoorButton`                                     | In-car open/close-doors button |

## Caveats and gotchas

- **The Intersect/Create-Mover editor ritual is gone** — `brush build … --mover-class` emits the
  mover directly. Everything else (keyframes, tags, events) is `actor prop set` / `mover key`.
- **Texture the car** with `--texture` on `brush build`, or retexture it later with `brush poly set` —
  uedctl can edit a mover's faces at any time. (The "surfaces frozen after Add Mover" limit is a
  GUI-editor constraint, not a uedctl one.)
- **Carone classes are a shipped dependency.** They only resolve during `level materialize` if
  `CaroneElevatorSet.u` is on the composed package search path. Distribute it with the map, and
  credit Carone.
- **Elevators want LiftCenter/LiftExit path nodes** if NPCs are to ride them — see the pathing
  section of [`../../general/`](../../general/).

## See also

- [`deusex-door.md`](deusex-door.md) — the `DeusExMover` door mechanics these movers inherit.
- [`../classes.md`](../classes.md) — the DX mover family and gameplay-wiring actors.
- [`../../general/`](../../general/) — engine movers, keyframes, and lift path nodes.
