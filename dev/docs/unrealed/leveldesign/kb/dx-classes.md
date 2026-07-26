# Deus Ex class catalog  [DX]

The substrate-specific actor classes an author reaches for in Deus Ex — the
classes that either **don't exist in stock UnrealEngine 1 / UT99** or that DX
**replaces** with its own subclass. This is the "which class do I place, and
what are its knobs" reference; the **NPC** classes (`ScriptedPawn` and roster)
have their own page ([`dx-npcs.md`](dx-npcs.md)), and the
**conversation/computer/info-device** classes theirs
([`dx-conversations-computers.md`](dx-conversations-computers.md)).

**Read the markers.** `[DX]` = Deus-Ex-specific (does NOT apply to raw UE1);
`[ENGINE]` = generic UnrealEngine 1 (flagged where a DX author leans on it).
Confidence: ✅ uedcli-used / live-verified · 🔬 live-probed against the real
`DeusEx.u` this session · 📖 from the DX SDK manual / tutorial corpus (vocabulary
real, semantics to confirm). Everything below marked 🔬 was grepped/decoded out
of the pristine shipped `DX/System/DeusEx.u`.

> **Siblings.** [`dx-npcs.md`](dx-npcs.md) · [`dx-conversations-computers.md`](dx-conversations-computers.md)
> · [`asset-pipeline.md`](asset-pipeline.md) · [`editor-ui.md`](editor-ui.md). The
> engine-generic actor layer (collision/physics/decoration/pathing base classes)
> and the full compiled reference live one level up in
> [`README.md`](README.md) (§8, §10). Movers overview:
> [`movers.md`](movers.md).

---

## How to discover and read any class

The catalog below is a **curated top-N** of the classes worth naming; the live
tree is the source of truth. Regenerate / verify with uedcli:

```
bin/uedcli class list --subclass-of DeusEx.HackableDevices   # inheritance tree
bin/uedcli class list --flat --subclass-of DeusEx.ScriptedPawn
bin/uedcli class show DeusEx.SecurityCamera                  # property NAMES + TYPES only
```

**`class show` prints names and types, NOT default values.** To read a default,
build a throwaway instance and query the resolved property (an unset property
resolves to its class default — the offline schema-decode route):

```
bin/uedcli actor build DeusEx.SecurityCamera | actor add - | actor prop get - cameraFOV
```

To place a configured actor into the trunk, the generator → `actor add -` pipe:

```
bin/uedcli actor build DeusEx.NanoKey --prop KeyID=tower_door --at 128,256,64 | actor add -
```

---

## 1. Movers & doors  [DX] 🔬

DX does **not** use the engine `Mover` family directly. It ships its own
**`DeusExMover`** subtree; place these instead of `Engine.Mover`.

**`DeusExMover`** — the DX base door/mover, adding the door/lock fields the
engine mover lacks:

| Property | Meaning |
|---|---|
| `bIsDoor` | this mover is a door (enables frob-to-open, lock logic) |
| `bLocked` | starts locked |
| `bOneWay` | opens from one side only |
| `lockStrength` | 0..1 fraction — resistance to lockpicking (see strengths table below) |
| `bPickable` | a lockpick can defeat `bLocked` |
| `doorStrength` | 0..1 fraction — resistance to being **destroyed** (crowbar/weapon) |
| `bBreakable` | can be destroyed rather than opened |
| `KeyIDNeeded` | the `NanoKey.KeyID` that unlocks it (a `name`, not a string) |

Subclasses (`expands DeusExMover`) 🔬:
- **`BreakableGlass`** — a 1-unit translucent breakable pane (windows).
- **`BreakableWall`** — a destructible wall; `doorStrength` **0.4** (lower it so a
  crowbar can break through for a hidden route).

Related lift mover (NOT a `DeusExMover` — it `expands Mover` directly 🔬):
- **`ElevatorMover`** — a lift; combine with the sequencing actors (§8) for
  multi-stop lifts (`bFollowKeyframes`).

**Authoring (uedcli).** A mover is one brush promoted to an actor. Author
model-side:
```
brush build cube --width 72 --height 144 --breadth 8 --mover-class DeusEx.DeusExMover \
  --prop bIsDoor=True --prop bLocked=True --prop KeyIDNeeded=tower_door | actor add -
mover key count … / mover key move … / mover key rotate …   # keyframes 0..7 (count sets NumKeys)
```
(UnrealEd GUI equivalent: *Add Mover*, then record keyframes — but note the GUI
record flow is inverted; see [`movers.md`](movers.md) and the keyframe trap
in [`README.md`](README.md) §7.) DX doors are typically
**144×72 or 128×64**, 1–8 uu thick.

**Ladders are NOT a mover or an actor** — they are texture-driven: any surface
whose texture's **Group name is `Ladder`** is climbable in-game (built-ins
`ladder_a`, `LadrBrwnMetal` in `CoreTexMetal`). 📖 (a native `case 'Ladder':`
group check in the DX player movement — DX-SDK/community-documented; the token is
native C++, absent from `DeusEx.u`'s script name table, so not offline-probable).
See [`asset-pipeline.md`](asset-pipeline.md) and the DX texture
catalog in [`README.md`](README.md) §4.1. There is **no**
`bIsLadder` prop and **no** `LadderZone` class.

---

## 2. Zones  [DX] 🔬

DX zoning uses the engine `ZoneInfo` with DX-relevant flags. There are **no**
`LavaZone`/`SlimeZone` classes in DX (those are stock-Unreal `UnrealShare` classes DX
doesn't ship), and **no `PainZone` class** in any UE1 game — pain is a `ZoneInfo` flag,
not a class.

- **Water** = `WaterZone` (a `ZoneInfo` preset with `bWaterZone=True`) — or a
  plain `Engine.ZoneInfo --prop bWaterZone=True`. ✅🔬
- **Pain/damage** = an ordinary `ZoneInfo` with `bPainZone=True` +
  `DamagePerSec` + a `DamageType` **name** (a `name` property on `Engine.ZoneInfo`, not a class):
  `TearGas`, `Radiation`, `Flamed`, `Drowned`, … 🔬 So a tear-gas room is a normal
  zone with `DamageType="TearGas"`, not a bespoke class.

```
actor build DeusEx.WaterZone --at <x,y,z-inside-water> | actor add -
actor build Engine.ZoneInfo --prop bPainZone=True --prop DamagePerSec=5 \
  --prop DamageType=TearGas --at <x,y,z> | actor add -
```

The water-surface recipe (translucent portal sheet + a `bWaterZone` marker) is
the engine zoning recipe — see [`./zones-performance.md`](./zones-performance.md)
and [`README.md`](README.md) §5.

---

## 3. Hackable devices  [DX] 🔬

Most descend from **`HackableDevices`** (`extends ElectronicDevices`, base props
`bHackable`, `hackStrength` = 0..1 resistance). Place the **device**, not the
underlying `…Gun` variant:

| Class | What it is | Notes |
|---|---|---|
| `Keypad1` / `Keypad2` / `Keypad3` | code-entry keypads | frob → code prompt; wire an `Event` on success; `hackStrength` **0.2** 🔬 |
| `SecurityCamera` | swiveling surveillance camera | Tag it, feed to `ComputerSecurity.Views[]` (see [`dx-conversations-computers.md`](dx-conversations-computers.md)); raises alarms; `hackStrength` **0.2** 🔬 |
| `AutoTurret` / `AutoTurretSmall` | ceiling/wall auto-turret | **place these, not the `…Gun` variants**. Note the turret **itself is a `DeusExDecoration`** 🔬; the hackable part is its auto-spawned **`AutoTurretGun`** (`extends HackableDevices`), `hackStrength` **0.5** (50%) |
| `AlarmUnit` | alarm panel | trips security state; hackable to disable; `hackStrength` **0.2** 🔬 |

**Device / hack strengths** ✅🔬 (the class-default resistance an aug/skill must
beat — decoded from `DeusEx.u`): lock (`DeusExMover.lockStrength`) **20%** · hack
(`HackableDevices.hackStrength`) **20%** · door (`DeusExMover.doorStrength`) **25%** ·
turret (`AutoTurretGun.hackStrength`) **50%** · wall (`BreakableWall.doorStrength`) **40%**.

**`SecurityCamera` key defaults** ✅🔬: `cameraFOV` **4096** (= 22.5°; the rotator
scale is 65536 = 360°), `cameraRange` **1024**, `swingAngle` **8192** (= 45° of
sweep). Tag the camera so a `ComputerSecurity` view or a `LogicTrigger` can
reference it.

```
actor build DeusEx.SecurityCamera --prop Tag=cam_lobby --prop cameraRange=1024 \
  --at 512,512,200 --rotate 0,16384,0 | actor add -
```

---

## 4. Pickups & keys  [DX] 🔬

- **`NanoKey`** — the DX key item. `KeyID` (a `name` that must match a door's
  `KeyIDNeeded`), `SkinColor`. Cylinder ~2.05×3.11 (tiny). Place it as a
  world pickup or hand it out via a `PickupDistributor`.
- **`PickupDistributor`** — distributes **NanoKeys** to NPCs at level start, then destroys itself (its payload is `NanoKeyData[8]`).
- General pickups subclass **`DeusExPickup`** (see [`asset-pipeline.md`](asset-pipeline.md)
  for the item-authoring fields ItemName/Description/Mesh/Icon/slot).

```
actor build DeusEx.NanoKey --prop KeyID=tower_door --at 200,140,48 | actor add -
```

---

## 5. Decorations, containers & info-devices  [DX] 🔬

DX replaces engine `Decoration` with **`DeusExDecoration`** — adds a highlight
**Name** label (the frob-target text) and `HitPoints` (destructibility). The
family includes:

- **Breakable containers** — `CrateBreakableMedCombat`, `CrateBreakableMedGeneral`,
  `CrateBreakableMedMedical` (and other sizes). They spill loot on destruction via the
  `contents`/`content2`/`content3` + `EffectWhenDestroyed` fields, gated by
  `DeusExDecoration.HitPoints` — **`Engine.Decoration` has no `Health`**
  ([`README.md`](README.md) §8). The `content2`/`content3` pick is a **weighted cascade**
  (each ~30% chance to override `contents`), not a uniform random draw.
- **Info devices** — `DataCube`, books, newspapers. Carry `textTag` +
  `TextPackage` (there is **no inline `Text`** property); **DataCube text goes into the
  player's Notes**. Markup and the full info-device authoring live in
  [`dx-conversations-computers.md`](dx-conversations-computers.md).
- **`WaterFountain`** — a *drinkable* `DeusExDecoration` (NOT an effect/emitter,
  despite the name).

```
actor build DeusEx.CrateBreakableMedMedical --at 320,64,16 | actor add -
```

---

## 6. Level info  [DX] 🔬

**`DeusExLevelInfo`** — the DX level header (one per map). It **`extends Info`** (a plain
metadata actor placed into the level) — **not** a `LevelInfo` subclass, which is why it
sits *alongside* the engine `LevelInfo` rather than replacing it:

| Property | Meaning |
|---|---|
| `MapName` | display name |
| `MapAuthor` | author |
| `MissionLocation` | location string |
| `missionNumber` | **must match** the conversation package's mission number (stock DX is ~1–15; **16–97 is the custom/fan-mission convention**, not a hard range) |
| `Script` | the `MissionScript` subclass that drives goals/flags |
| `ConversationPackage` | default `"DeusExConversations"` |
| **`TrueNorth`** | a **single `int` yaw angle (rotator units, 0–65535) defining world-north for the in-HUD compass** 🔬 — DX-specific; set so the compass points the right way. NOT a 3-component rotator |
| `startupMessage[4]` | the four intro strings shown on level entry |
| `bMultiPlayerMap` | flags an MP map (see [`README.md`](README.md) §18) |

`TrueNorth` is the one field with no UE1 analogue — the compass HUD reads it to
orient. Set it once per level (a scalar yaw, e.g. `16384` = 90°).

```
actor build DeusEx.DeusExLevelInfo --prop missionNumber=16 --prop MapName="Castle" \
  --prop TrueNorth=16384 | actor add -
```

---

## 7. The DX particle / effects family  [DX] 🔬

Stock UT99 has **no particle emitters** (UE1 effects are sprite/trail-based).
DeusEx adds a real, mapper-placeable particle system under *Actor → Effects*.

**`ParticleGenerator`** ✅🔬 — the base emitter (`extends Effects`). Defaults:

| Property | Default | Meaning |
|---|---|---|
| `frequency` | **1.0** | spawn frequency |
| `checkTime` | **0.1** s | spawn-check interval |
| `numPerSpawn` | **1** | particles per spawn event |
| `riseRate` | **10** | upward drift |
| `ejectSpeed` | **10** | initial particle speed |
| `particleLifeSpan` | **4** s | per-particle lifetime |
| `particleDrawScale` | **0.1** | per-particle scale |
| `particleTexture` | — | the sprite |
| `bParticlesUnlit` | — | fullbright particles |
| `bScale`/`bFade`/`bTranslucent`/`bGravity`/`bRandomEject` | — | behaviour toggles |
| **`bTriggered`** | **False** | **DX enhancement**: spawn only after a Trigger (Unreal's system is always-on) |

Concrete emitters in the DX **effects family** — note only some subclass
`ParticleGenerator`; the laser/electricity/fire ones are separate `Effects`-family classes:
- **`WaterDrips`** — a `ParticleGenerator` subclass: ceiling drips that fall by gravity
  (`bGravity=True`, the default). Rotation has **no** effect (`ejectSpeed=0`) — there's no arrow to aim.
- **`LaserEmitter`** — **the laser BEAM visual** (`extends Effects`, NOT a
  `ParticleGenerator`); up to **2 reflection points**; freezes its calc when the player
  is **>960 uu** away. **It trips nothing by itself** — the gameplay tripwires are
  `LaserTrigger`/`BeamTrigger` (§8), which spawn a `LaserEmitter` for the beam.
- **`ElectricityEmitter`** — a damaging arc (`extends LaserEmitter`); `DamageAmount=2`,
  `bDirectional` (the arrow aims it); carries its own light.
- **`Fire`** — a flame sprite plus an `LE_FireWaver` light (`extends Effects`).
- **`ProjectileGenerator`** — periodically fires a projectile (`ProjectileClass`,
  `WaitTime`, `bSpewUnseen`).
- **`TrashGenerator`** — wind-blown debris ("Paper"/tumbleweeds, `WindSpeed`).

**NOT mapper-emitters** (don't place them as such): `SmokeTrail` (code-spawned
projectile puff), `WaterFountain` (a drinkable `DeusExDecoration`, §5),
`SmokelessFire` (declared in source, not a mapper-facing class).

```
actor build DeusEx.WaterDrips --prop bGravity=True --at 256,256,240 --rotate -16384,0,0 | actor add -
# the laser TRIPWIRE (LaserTrigger) — it spawns its own LaserEmitter beam and fires Event when broken:
actor build DeusEx.LaserTrigger --prop Tag=laser1 --prop Event=alarm --at 128,0,64 | actor add -
```

---

## 8. Gameplay-wiring actors  [DX] 🔬 (from the DX SDK "Level Design" manual)

The triggers that connect devices, flags, goals and movers into gameplay logic.

### FlagTrigger — the flag database face

**`FlagTrigger`** is the mapper interface to the DX **flag database** — the
persistent boolean/expiring-flag store on the player
(`player.flagBase.SetBool/GetBool/GetExpiration/DeleteFlag`, confirmed rich in
the binary ✅🔬).

| Property | Meaning |
|---|---|
| `flagName` | the flag to read/write |
| `flagValue` | the value to write (or to compare against when gating) |
| `bSetFlag` | **write** mode — set `flagName` = `flagValue` when triggered |
| `bTrigger` | **gate** mode — fire this actor's `Event` **only if** the flag matches |
| `bWhileStandingOnly` | only while the player stands in it |
| `flagExpiration` | when the flag auto-clears; **`-1` = permanent** |

So one `FlagTrigger` in write mode records state (a door was opened, an NPC
died), and another in gate mode reads it later to branch. This is how a level
"remembers" the player's actions.

### The rest of the wiring set

- **`GoalCompleteTrigger`** (`goalName`) — completes a goal the `MissionScript`
  created via `AddGoal`. Wire it to the world event that finishes an objective.
- **`LogicTrigger`** — a boolean combiner of two trigger inputs. The two inputs are
  matched by the **instigating actor's `Group`** against **`inGroup1`/`inGroup2`** (each a
  `var() name`); the gate is **`Op`** (a `var() ELogicType`: `GATE_AND` / `GATE_OR` /
  `GATE_XOR`), with **`Not`** (invert the output) and **`OneShot`**. Fire `Event` only when
  the combination holds. (E.g. "both cameras disabled" = `GATE_AND` with the two cameras'
  triggers grouped into `inGroup1`/`inGroup2`.)
- **`SequenceTrigger`** (`SeqNum`) + **`MultiMover`** (`SeqKey1..4` / `SeqTime1..4`,
  `bReverseKeyframes`) + `ElevatorMover` (`bFollowKeyframes`) — the multi-stop
  elevator/mover sequencing set. A `SequenceTrigger` advances a `MultiMover`
  through its numbered stops.
- **`LaserTrigger`** / **`BeamTrigger`** — directional laser triggers; fire when the beam
  is broken (each spawns a `LaserEmitter` for the visible beam). **`bNoAlarm` is on
  `LaserTrigger` only** (suppresses the security alarm for a silent trip); `BeamTrigger`
  has no alarm of its own.

```
# write a permanent flag when a switch is thrown
actor build DeusEx.FlagTrigger --prop flagName=power_off --prop bSetFlag=True \
  --prop flagValue=True --prop flagExpiration=-1 --prop Tag=power_switch | actor add -

# gate a door's Event on that flag
actor build DeusEx.FlagTrigger --prop flagName=power_off --prop bTrigger=True \
  --prop flagValue=True --prop Event=open_vault | actor add -

# AND two inputs (each input actor's Group must match inGroup1 / inGroup2)
actor build DeusEx.LogicTrigger --prop Op=GATE_AND --prop inGroup1=cam1 --prop inGroup2=cam2 \
  --prop Event=unlock_final | actor add -
```

### Security-camera → console (no world monitor)

DX does **not** paint a camera feed onto a world monitor surface. The feed
renders inside the hackable-computer UI. Place `SecurityCamera` (Tag it), place
`ComputerSecurity`, set `Views[i].cameraTag=<tag>`. Full recipe (and why
`ScriptedTexture` is *not* a camera feed) in
[`dx-conversations-computers.md`](dx-conversations-computers.md).

---

## What DOES NOT exist in DX (don't offer it)

- **Zone classes** `LavaZone` / `SlimeZone` — stock-Unreal `UnrealShare` classes DX
  doesn't ship (and there is no `PainZone` class in any UE1 game); DX does pain via
  `ZoneInfo bPainZone` + `DamageType` name (§2).
- **`LE_Negative`** light effect — a UT2004-era value, **absent** from DX
  `Engine.u` ✅🔬. Darken with fewer/dimmer lights or lower zone
  `AmbientBrightness`, not a "negative light" (see [`lighting.md`](lighting.md)).
- **`bIsLadder` / `LadderZone`** — ladders are texture-Group-`Ladder` driven (§1).
- **Particle `Emitter`** (the UE2 emitter actor) — DX uses `ParticleGenerator`
  (§7); the *engine* has no emitters at all.
- The **`ScriptedPawn` UT-name knobs** (`HateTag`, `IdealRange`,
  `SeekTag`, `ThingFactory`, `AlarmPoint`, …) — see the absent-names list in
  [`dx-npcs.md`](dx-npcs.md). (**`AlarmTag` IS real** in DX; and `AmbushPoint`
  exists in `Engine.u` but DX drives NPCs via `ScriptedPawn` orders instead — do
  not list either as absent.)
