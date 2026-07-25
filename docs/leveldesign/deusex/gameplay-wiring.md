# DX gameplay wiring  [DX]

Deus Ex adds a rich trigger/flag vocabulary on top of the engine's basic `Trigger` / `Tag` / `Event`
mechanism. This is how you build reactive, stateful levels — locked doors, alarms, goals, and
environmental effects. Place each actor and wire it with `Tag`/`Event` the same way as any actor:

```
actor build DeusEx.FlagTrigger --prop flagName=door_unlocked --prop bSetFlag=True --at X,Y,Z | actor add -
```

The generic wiring model (a trigger's `Event` matches a target actor's `Tag`) is covered in the
[general guides](../general/). This guide covers the DX-specific additions (plus a couple of stock
engine triggers a DX level leans on, flagged where they're not DX-only).

---

## Persistent flags — `FlagTrigger`

The **flag database** is DX's persistent boolean store (survives across the mission). `FlagTrigger` is
the mapper's face on it:

- **`flagName`** — the flag to read or write.
- **`bSetFlag`** — when true, this trigger **writes** the flag (`flagValue`) when fired.
- **`bTrigger`** — when true, this trigger acts as a **gate**: it fires its own `Event` only if the flag
  already matches `flagValue`.
- **`flagExpiration`** — the **mission number** after which the flag is auto-purged (not a duration);
  **`-1` = permanent** (the usual setting for story flags).
- **`bWhileStandingOnly`** — only holds while the player stands in it.

Use one `FlagTrigger` to *set* a flag (e.g. `alarm_disabled`) and another as a *gate* elsewhere that
only opens a door if that flag is set — that's how state persists and cross-references across the level.

## Mission goals — `GoalCompleteTrigger`

**`GoalCompleteTrigger`** (`goalName`) marks complete a goal the mission's `MissionScript` created with
`AddGoal`. Fire it when the player reaches the objective (enters a room, retrieves an item via a wired
trigger, etc.).

## Boolean logic — `LogicTrigger`

**`LogicTrigger`** combines two trigger inputs — matched by each input actor's `Group` against
**`inGroup1`/`inGroup2`** — with a gate **`Op`** (**AND / OR / XOR**), plus **`Not`** (invert the output)
and **`OneShot`**. Use it to require two conditions before an event fires — e.g. *both* keypads pressed
(group them into `inGroup1`/`inGroup2`, `Op=GATE_AND`), or the alarm off *and* the door hacked.

## Delayed and sequenced events

- **`Dispatcher`** (a **stock `Engine` class**, present in Unreal/UT too — not a DX addition) — fires
  **up to 8 events**, each after its own delay. One trigger → a timed cascade (lights, then a door, then
  an alarm).
- **`SequenceTrigger`** (`SeqNum`) + **`MultiMover`** (`SeqKey1..4` / `SeqTime1..4`, `bReverseKeyframes`)
  + `ElevatorMover` (`bFollowKeyframes`) — multi-stop elevator/mover sequencing.
- **`LaserTrigger`** / **`BeamTrigger`** — directional laser tripwires (`bNoAlarm` is on `LaserTrigger`
  only; `BeamTrigger` has no auto-alarm).

## Hackable devices

The hackable devices (see [`classes.md`](classes.md)) participate in wiring: a `Keypad` fires its
`Event` on the correct code, a `SecurityCamera` or `AutoTurret` responds to alarm state, an `AlarmUnit`
raises the alarm. Give each a `Tag`, and target it (or have it target) via `Event`.

## Particle emitters — steam, sparks, drips, fire

DX ships a real particle system (stock UnrealEngine 1 has none). Place these under environmental
atmosphere:

- **`ParticleGenerator`** — the general emitter. Key props: `frequency` (1.0), `checkTime` (0.1s),
  `numPerSpawn`, `riseRate` (10), `particleLifeSpan` (4s), `particleDrawScale` (0.1), `particleTexture`.
  The DX enhancement over Unreal is **`bTriggered`** — spawn only after a `Trigger`.
- **`WaterDrips`** — ceiling drips; they fall by gravity (`bGravity`, on by default). Rotation has no effect (`ejectSpeed`=0).
- **`ElectricityEmitter`** — a damaging electric arc (`bDirectional` aims it; carries its own light) —
  for sparking wires and shorts.
- **`Fire`** — a flame sprite with an `LE_FireWaver` light attached.
- Related effects: `LaserEmitter` (the laser **beam visual** — NOT the tripwire; the tripwire is
  `LaserTrigger`/`BeamTrigger` above, which spawns a `LaserEmitter`), `ProjectileGenerator`,
  `TrashGenerator` (wind-blown debris).

```
actor build DeusEx.WaterDrips --at 256,256,240 --rotate -16384,0,0 | actor add -   # drips from a ceiling
actor build DeusEx.ParticleGenerator --prop bTriggered=True --prop particleTexture=… --at X,Y,Z | actor add -
```

## Security cameras → the hacked-computer feed

**DX does not paint a camera feed onto a world monitor surface.** The feed is a live render composited
into the **hackable-computer UI**. To wire a camera to a screen the player can hack:

1. Place a **`SecurityCamera`** and give it a `Tag`.
2. Place a **`ComputerSecurity`**.
3. Set the computer's **`Views[i].cameraTag`** to the camera's `Tag`. Each view can also take a
   `turretTag` and `doorTag` so the player, once in, can slew turrets and open doors.

The camera's feed then renders inside that computer's console UI when the player hacks or logs into it.
There is no `ScriptedTexture` monitor and no world-mounted screen showing the camera.

---

## See also

- [`classes.md`](classes.md) — the devices and movers these triggers drive.
- [`npcs.md`](npcs.md) — alarms, alliances, and making guards react.
- [`conversations-and-computers.md`](conversations-and-computers.md) — computers and datacubes.
- [`design-philosophy.md`](design-philosophy.md) — using flags/consequences to make choices matter.
