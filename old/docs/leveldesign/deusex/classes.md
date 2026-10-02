# DX class catalog  [DX]

Deus-Ex-specific classes for mappers. These substrate classes live in
`DeusEx.u`, not stock UnrealEngine 1. Generic actors (`Engine.Light`, `Engine.ZoneInfo`,
`Engine.PlayerStart`, `Engine.SkyZoneInfo`, plain `Trigger`) are covered in the [general
guides](../general/).

## Placing and discovering classes

Place any class by building an instance (optionally with properties and a pose) and piping it into the trunk:

```
actor build DeusEx.<Class> --prop KEY=VALUE --at X,Y,Z --rotate Pitch,Yaw,Roll | actor add -
```

Discover what's available and inspect a class's properties:

```
class list --subclass-of DeusEx.ScriptedPawn      # the inheritance tree under a base
class list --flat --subclass-of DeusEx.DeusExMover
class show DeusEx.NanoKey                          # property names + types (NOT default values)
```

`class show` prints names and types only. To read a default value, decode it offline:
`actor build DeusEx.<Class> | actor add - | actor prop get - <Prop>` (an unset property resolves to its
class default). See [`human-scale.md`](human-scale.md).

---

## Doors, glass, walls, lifts — the DX mover family

DX ships its own `Engine.Mover` subclasses instead of a bare `Engine.Mover` for doors and panels.
`DeusExMover` (with its `BreakableGlass` / `BreakableWall` children) is the door/panel branch;
`ElevatorMover` and `MultiMover` are separate `Engine.Mover` subclasses for lifts and sequenced
travel (not `DeusExMover` descendants). Build any as movers and key them with the `mover key` verbs
(see [`../general/`](../general/) movers guide):

```
brush build cube --mover-class DeusEx.DeusExMover | actor add -
```

- **`DeusExMover`** — the general door/panel base (extends `Engine.Mover`). Key props: `bIsDoor`,
  `bLocked`, `lockStrength`, `doorStrength`, `bBreakable`, `bOneWay`, `bPickable`, `KeyIDNeeded` (which
  `NanoKey` opens it).
- **`BreakableGlass`** (a `DeusExMover`) — a thin translucent pane that shatters when hit.
- **`BreakableWall`** (a `DeusExMover`) — a wall segment destroyable with the right tool (lower
  `doorStrength` = easier to crowbar through).
- **`ElevatorMover`** — a lift (a direct `Engine.Mover` subclass, not a `DeusExMover`); combine with
  `MultiMover`/`SequenceTrigger` for multi-stop travel (see [`gameplay-wiring.md`](gameplay-wiring.md)).

## Ladders — a texture, not an actor

DX has no ladder actor and no ladder flag. A ladder is any surface textured with a texture whose
`Group` is `Ladder` — the engine treats that reserved group as climbable. Built-in ladder textures
include `ladder_a` and `LadrBrwnMetal` in `CoreTexMetal`. Texture the wall with one
(`brush poly set - --texture CoreTexMetal.LadrBrwnMetal`) and it becomes climbable in-game.

## Zones — water and pain

DX uses `ZoneInfo` presets, not bespoke zone classes:

- **Water** — `DeusEx.WaterZone` is exactly `Engine.ZoneInfo` with `bWaterZone=True`. Place either.
- **Pain** — an ordinary `ZoneInfo` with `bPainZone=True` + `DamagePerSec` (an int) + a `DamageType`
  name (`TearGas`, `Radiation`, `Flamed`, `Drowned`, …). No UE1 game has a `PainZone` class, and
  `LavaZone`/`SlimeZone` are stock-Unreal `UnrealShare` classes DX doesn't ship — pain is a
  `ZoneInfo` flag, not a class.

```
actor build DeusEx.WaterZone --at <inside-the-pool> | actor add -
actor build Engine.ZoneInfo --prop bPainZone=True --prop DamagePerSec=5 --prop DamageType=Radiation --at <inside> | actor add -
```

(The water surface is a translucent portal sheet — a geometry recipe in the general zoning guide.)

## Hackable devices

Most share the `HackableDevices` base (`bHackable`, `hackStrength` — a 0..1 resistance). Place the
device, give it a `Tag` if something wires to it:

- **`Keypad1` / `Keypad2` / `Keypad3`** — code-entry panels (open doors, disable alarms). 20% hack.
- **`SecurityCamera`** — a swinging camera; its feed shows up in a hacked `ComputerSecurity` UI (see
  [`gameplay-wiring.md`](gameplay-wiring.md)), not on a world monitor. 20% hack.
- **`AutoTurret` / `AutoTurretSmall`** — ceiling/wall turrets. Place these, not the `…Gun` variants.
  The turret body is a `DeusExDecoration` (not a `HackableDevices`); the hackable part is its
  attached gun (`AutoTurretGun`, a `HackableDevices`), fixed at 50% hack strength.
- **`AlarmUnit`** — raises the level alarm when triggered (no sight of its own; alerted NPCs run to
  it to sound it). Hackable to disable. 20% hack.

## Pickups and keys

- **`NanoKey`** — a key item; its `KeyID` matches a door's `KeyIDNeeded`. `SkinColor` tints it.
- **`PickupDistributor`** — distributes NanoKeys to NPCs at level start (payload `NanoKeyData`), then self-destructs.
- Weapons, ammo, tools, and augmentation canisters are `DeusExPickup` subclasses — discover them with
  `class list --subclass-of DeusEx.DeusExPickup`.

## Decorations and info devices — the `DeusExDecoration` family

DX props extend `DeusExDecoration` (adds a highlight Name label shown on frob, and `HitPoints`).
Two groups mappers use:

- **Containers** — `CrateBreakableMedCombat`, `CrateBreakableMedGeneral`, `CrateBreakableMedMedical`,
  etc. Break them to spill their `contents`. Good for diegetically teaching the crowbar affordance.
- **Info devices** — DataCubes, books, and newspapers. A DataCube's `textTag` / `TextPackage` names
  the text it displays; reading a DataCube writes its text into the player's Notes. See
  [`conversations-and-computers.md`](conversations-and-computers.md).

## Level info — `DeusExLevelInfo`

Every DX map needs exactly one `DeusExLevelInfo` (alongside the engine's `LevelInfo`). Key props:

- **`missionNumber`** — the mission this map belongs to (must match its conversation package's
  mission number, or conversation state won't bind).
- **`Script`** — the `MissionScript` subclass driving the mission's goals and logic.
- **`ConversationPackage`** — the compiled conversation package (default `"DeusExConversations"`).
- **`TrueNorth`** — a single yaw angle (an `int` in rotator units, 0–65535) defining world-north for
  the in-HUD compass (DX-specific; not a 3-component rotator).
- **`MapName`**, `MapAuthor`, `MissionLocation`, `startupMessage[4]` (text shown on level entry).

```
actor build DeusEx.DeusExLevelInfo --prop missionNumber=16 --prop MapName="Warehouse District" | actor add -
```

---

## See also

- [`npcs.md`](npcs.md) — the `ScriptedPawn` roster and how to populate a level.
- [`gameplay-wiring.md`](gameplay-wiring.md) — triggers, flags, and hooking these devices together.
- [`human-scale.md`](human-scale.md) — device strengths, camera FOV, and how to decode any default.
- [`../general/`](../general/) — engine-level movers, zones, and geometry these classes build on.
