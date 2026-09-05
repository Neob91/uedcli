# 30 — The script side: NavigationPoint classes, Scout/Pawn defaults, on-disk node bodies, script callers

Read offline from the `.u`/`.dx` bytes with `harness/scriptside.py` (subcommands `tree`, `defaults`,
`disk`, `xcheck`, `who`, `calls`, `refs`, `decls`, `census`) and `harness/layout.py`. Two package sets:

| Key   | Packages                                                   | Version |
|-------|------------------------------------------------------------|---------|
| `ued` | `uned/UED22/Engine.u`, `uned/UED22/DeusEx.u`               | v69 (469-lineage editor) |
| `dx`  | `dev/games/deusex/System/Engine.u`, `…/DeusEx.u`           | v68 (game, 1112fm) |

Maps: `dev/games/deusex/Maps/*.dx` (88 files, all v68). ✅ = read from the bytes · 🔬 = inferred
from them (inference stated) · 📖 = public UE1 knowledge, unconfirmed here.

## 1. The NavigationPoint family

**Class tree — identical set of 17 in both `ued` and `dx`** ✅ (`scriptside.py tree`). All are direct
children of `Engine.NavigationPoint` (no deeper nesting):

`Engine`: PathNode, PlayerStart, PatrolPoint, Ambushpoint, HomeBase, InventorySpot, WarpZoneMarker,
LiftCenter, LiftExit, Teleporter, TriggerMarker, ButtonMarker. `DeusEx`: SpawnPoint, WanderPoint,
HidePoint, MapExit.

### 1.1 `Engine.NavigationPoint` own variables (declaration order)

| Var | Type | `ued` flags | `dx` flags | Note |
|-----|------|-------------|------------|------|
| `ownerTeam` | Name | Edit | Edit | authored |
| `taken` | Bool | – | – | scratch (`Accept` event) |
| `upstreamPaths[16]` | Int | – | – | build output; `-1` default |
| `Paths[16]` | Int | – | – | build output; `-1` default |
| `PrunedPaths[16]` | Int | – | – | build output; `-1` default |
| `VisNoReachPaths[16]` | NavigationPoint | – | – | build output; `None` default |
| `visitedWeight` | Int | – | – | search scratch |
| `RouteCache` | Actor | – | – | search scratch |
| `bestPathWeight` | Int | Const | Const | search scratch |
| `nextNavigationPoint` | NavigationPoint | Const | Const | level list link |
| `nextOrdered`, `prevOrdered` | NavigationPoint | Const | Const | search scratch |
| `startPath`, `previousPath` | NavigationPoint | Const | Const | search scratch |
| `cost` | Int | – | – | search scratch |
| `ExtraCost` | Int | Edit | Edit | authored |
| `bPlayerOnly` | Bool | Edit | Edit | authored |
| `bEndPoint`, `bEndPointOnly`, `bSpecialCost` | Bool | – | – | internal |
| `bOneWayPath`, `bNeverUseStrafing` | Bool | Edit | Edit | authored |
| `bAutoBuilt` | Bool | – | **absent** | `ued` only (469 addition), +0x33c mask 0x40 |
| `bTwoWay` | Bool | – | **absent** | `ued` only, +0x33c mask 0x80 |

"–" = `PropertyFlags` 0. ✅ **No NavigationPoint var carries `CPF_Transient` (0x2000) or
`CPF_Native` (0x1000) in either version** — so every one of them is written to disk whenever its
value differs from the class default, editable or not. `Const` only blocks script writes. Editable
(`var()`) = `ownerTeam`, `ExtraCost`, `bPlayerOnly`, `bOneWayPath`, `bNeverUseStrafing`; all else is
engine-written. (`ued` `Actor` also lacks any `Transient` flag on the fields below; the game does not
either.)

Layout (`layout.py`): `ued` NavPt+0x214/0x254/0x294/0x2d4 = `upstreamPaths`/`Paths`/`PrunedPaths`/
`VisNoReachPaths`, `cost` +0x334, `ExtraCost` +0x338, bool word +0x33c, size 0x340. `dx` (bigger
`Actor`): +0x320/0x360/0x3a0/0x3e0, `cost` +0x440, `ExtraCost` +0x444, bool word +0x448 (bits 0–5
only), size 0x44c. ✅

### 1.2 Class defaults that matter to the build

`Engine.NavigationPoint` own defaults, both versions ✅: `bStatic=True`, `bHidden=True`,
`bCollideWhenPlacing=True`, `SoundVolume=0`, `CollisionRadius=12`, `CollisionHeight=15`, all 48
int slots `=-1`. Inherited from `Actor`: `DrawType=DT_Sprite`, `Texture=S_Actor`, `bMovable=True`,
`bHiddenEd=False`, `bNoDelete=False`, `bCollideActors/World=False`, `Physics=PHYS_None`.

Per subclass (own defaults only; everything else inherits the row above). Same in `ued` and `dx`
unless a `dx`/`ued` column is given:

| Class | Own defaults (both) | Differences |
|-------|---------------------|-------------|
| PathNode | `Texture=S_Pickup`, `SoundVolume=128` | – |
| PlayerStart | `bSinglePlayerStart/bCoopStart/bEnabled=True`, `bDirectional=True`, `Texture=S_Player`, `R=18`, `H=40` | `dx` adds vars `bTeamOnlyStart`, `bNonTeamOnlyStart` |
| PatrolPoint | `bDirectional=True`, `Texture=S_Patrol`; vars `Nextpatrol`(Edit,Name), `pausetime`, `PatrolAnim`, `PatrolSound`, `numAnims` (Edit); `lookDir`, `AnimCount`, `NextPatrolPoint` (internal) | – |
| Ambushpoint | `SightRadius=5000`, `bDirectional=True`; `bSniping` Edit | – |
| HomeBase | `Extent=700`, `Texture=S_Flag` | – |
| Teleporter | `bChangesYaw/bEnabled=True`, `RemoteRole=2`, `bDirectional=True`, `Texture=S_Teleport`, `bCollideActors=True`, `R=18`, `H=40` | – |
| LiftCenter | `MaxDist2D=400`, **`ExtraCost=400`**, `bStatic=False`, `bNoDelete=True`, `RemoteRole=0` | – |
| LiftExit | none | – |
| InventorySpot | `bEndPointOnly=True`, `bHiddenEd=True` | **`dx`**: `bCollideWhenPlacing=False`, `R=20`, `H=40`. **`ued`**: `bCollideActors/bBlockActors/bBlockPlayers=True`, no `bCollideWhenPlacing` override (stays True), `CollisionRadius=CollisionHeight=0x68670004` (≈4.4e24 — a garbage float; `Engine.u` export `InventorySpot` tail bytes `39 24 04 00 67 68 38 24 04 00 67 68`) |
| WarpZoneMarker | `bHiddenEd=True`, `bCollideWhenPlacing=False`, `R=20`, `H=40` | – |
| TriggerMarker, ButtonMarker | none | – |
| DeusEx.SpawnPoint | `bDirectional=True`, `Texture=S_Flag` | – |
| DeusEx.WanderPoint | `gazeDuration=6`, `bDirectional=True`; `gazeTag` Edit | – |
| DeusEx.HidePoint | `bDirectional=True` | – |
| DeusEx.MapExit | `Texture=S_Teleport`, `bCollideActors=True`; `DestMap`, `bPlayTransition`, `cameraPathTag` Edit | – |

So: every placeable node except InventorySpot(`dx`)/WarpZoneMarker has `bCollideWhenPlacing=True`
with a 12×15 cylinder (PlayerStart/Teleporter 18×40). Only LiftCenter ships a non-zero `ExtraCost`.
The same `0x68670004` float also sits in `Scout.CombatStyle` in **both** versions (`Engine.u`
`Scout` tail `49 0b 24 04 00 67 68` / `68 15 24 04 00 67 68`) — so it is a compiler artefact, not a
UED22 edit; whether `definePaths` overrides the spot's collision size is an engine-side question.

The `ued` v69 compiler writes a class's FULL own-var default block (every var, even zero); `dx` v68
writes a sparse diff. Same effective values except where the table says otherwise. ✅

## 2. Scout and Pawn defaults relevant to pathing

`Engine.Scout` declares no own vars; chain `Scout → Pawn → Actor`. Own default block is byte-identical
in `ued` and `dx` ✅: `AccelRate=1`, `SightRadius=4100`, `CombatStyle=0x68670004`,
`CollisionRadius=52`, `CollisionHeight=50`, `bCollideActors/bCollideWorld/bBlockActors/bBlockPlayers/
bProjTarget=False`. Inherited from `Pawn` (both): `GroundSpeed=320`, `JumpZ=325`, `MaxStepHeight=25`,
`WaterSpeed=200`, `AirSpeed=0`, `AirControl=0.05`; `bCanWalk/Fly/Swim/Jump/OpenDoors/DoSpecial/
Strafe=False` (no Pawn or Scout default sets them). `dx` `Pawn` adds `bCanGlide` (default True on
Pawn, False on ScriptedPawn) and `LastRenderTime`/`DistanceFromPlayer` on Actor.

So the scout's walk/jump ability and its 52×50 size come from the builder's native code, not the
class (matches `00-method.md`: `buildPaths` stores `GroundSpeed`/`JumpZ`/`MaxStepHeight` at
+0x26c/+0x27c/+0x280 — those offsets hold in both layouts: `ued` and `dx` `Pawn` place them at
+0x26c/+0x27c/+0x280 and +0x378/+0x388/+0x38c respectively).

Game pawns for scale (both versions, `defaults`): `ScriptedPawn` R=22 H=22, `GroundSpeed=320`,
`JumpZ=120`, `MaxStepHeight=25`, `bCanWalk/Swim/OpenDoors/Strafe=True`, `bCanJump=False`;
`JCDentonMale` R=20 H=47.5, `JumpZ=300`, `bCanJump=True`, `bIsPlayer=True`.

## 3. On-disk verification against retail maps ✅

Maps: `02_NYC_Bar.dx` (602 actors, 889 specs, 80 nav actors), `03_NYC_UNATCOHQ.dx` (1481 / 1778 /
244), `01_NYC_UNATCOIsland.dx` (3687 / 12514 / 1198). Class membership resolved against the game's
`Engine.u`/`DeusEx.u`; specs decoded from the `Level` body as in `level_roundtrip.py`.

### 3.1 Which NavigationPoint properties are on disk

Counts over all 88 retail maps (`census`), tags per NavigationPoint-family actor:

| Tag | Present | Value seen |
|-----|---------|------------|
| `upstreamPaths(i)`, `Paths(i)`, `PrunedPaths(i)` | every path-built map, every node with edges | spec indices |
| `VisNoReachPaths(i)` | most maps (1–1315 elements) | node refs |
| `visitedWeight` | **every node** in path-built maps | always `10000000` |
| `bestPathWeight` | nearly every node | small ints |
| `nextNavigationPoint` | every node but the roster-first | previous nav actor on the roster |
| `previousPath` | most nodes | node ref |
| `nextOrdered`/`prevOrdered` | 18 maps, a few nodes each | node refs |
| `bEndPoint=True` | 21 maps, 1–14 nodes | only on targets of the `cost` node's outgoing specs (UNATCOIsland: all 5 of PlayerStart0's `Paths`+`PrunedPaths` targets; FreeClinic: all 5; Intro: MapExit1's live target `PathNode14` but not its two pruned H=48 targets — 🔬 a seeker-size filter) |
| `cost=1000000` | 27 maps, exactly one node | a PlayerStart, Teleporter or MapExit (the level's entry point) |
| `ExtraCost`, `bSpecialCost`, `bPlayerOnly`, `bOneWayPath`, `bNeverUseStrafing`, `taken`, `ownerTeam`, `RouteCache`, `startPath`, `bEndPointOnly` | **never** | (class-default only) |
| `bAutoBuilt`, `bTwoWay` | never (not in the v68 class) | |
| `Level`, `Tag`, `Region`, `Location`, `OldLocation`, `Rotation`, `LastRenderTime`, `DistanceFromPlayer` | always | Actor fields |
| `CollisionRadius/Height`, `bCollideActors` | only authored overrides (Teleporters 60/80, one MapExit) | |

`LevelInfo0` also carries **`NavigationPointList`** on disk (Bar: `=HidePoint4`, UNATCOHQ:
`=PathNode9` — the LAST nav actor on the roster), plus `AIProfile`, `TimeSeconds`, `Summary`.

**Correction to the 2026-07-15 spike §4.5**, which listed `nextNavigationPoint`, `NavigationPointList`,
`visitedWeight`, `bestPathWeight`, `startPath` as "recomputed, do NOT put on disk": the retail files
DO carry `nextNavigationPoint` (every node), `NavigationPointList` (LevelInfo), `visitedWeight`
(=10000000, every node), `bestPathWeight`, `previousPath`, and sporadically `nextOrdered`/`prevOrdered`/
`bEndPoint`/`cost`. They are search residue that the engine never marks transient, so `MAP SAVE`
writes it. Harmless for the game (rebuilt/reset at play) but load-bearing for byte parity. `startPath`
and `RouteCache` are genuinely never on disk. Which editor-side code leaves this residue (a
`FindPathTo`-style sweep from the entry point?) is an engine-side question — see §6.

`nextNavigationPoint` chain ✅: on every node it equals the previous NavigationPoint on the `Actors`
roster (Bar 79/79, UNATCOHQ 243/243; the roster-first node has none); `NavigationPointList` is the
roster-last node. I.e. the list is built by walking the roster forward and pushing each node at the
head.

The DXMP maps are the exception: `DXMP_CMD` has 2229 specs but its 30 on-roster nodes carry no path
tags — the specs point at off-roster (deleted-but-unreclaimed) PathNode exports. Not a target.

### 3.2 Static-array tag encoding (the 16-int arrays) ✅

One `FPropertyTag` per element; element index in the info byte's bit7 + a packed index byte (absent
for element 0); only elements whose value differs from the class default (`-1` / `None`) are written;
in all three maps the written elements are always the contiguous prefix `0..k-1` with no `-1` and no
duplicate index (Bar 76/76 `Paths`, 75/75 `upstreamPaths`, 75/75 `PrunedPaths`; UNATCOIsland
1196/1196, 1179/1179, 1166/1166). Byte-level example, `02_NYC_Bar.dx` export #108 `PathNode0`
(class `Engine.PathNode`, body `soff=0x883e`, StateFrame 15 B, properties `0x884d..0x88f9`):

```
0x884d  0d 22 b1 02 00 00      upstreamPaths[0]  name=13 info=0x22 (Int, size code 2 → 4 B; bit7 clear = elem 0) = 689
0x8853  0d a2 01 d7 02 00 00   upstreamPaths[1]  info=0xa2 (bit7 set → 1-byte index 0x01) = 727
0x885a  0d a2 02 e9 02 00 00   upstreamPaths[2] = 745
0x8861  0d a2 03 e1 02 00 00   upstreamPaths[3] = 737
0x8868  0d a2 04 3a 00 00 00   upstreamPaths[4] = 58
0x886f  0e 22 92 00 00 00      Paths[0] = 146      (name 14)
0x8875  0e a2 01 93 00 00 00   Paths[1] = 147
0x887c  0e a2 02 95 00 00 00   Paths[2] = 149
0x8883  0e a2 03 94 00 00 00   Paths[3] = 148
0x888a  0e a2 04 90 00 00 00   Paths[4] = 144
0x8891  04 22 96 00 00 00      PrunedPaths[0] = 150   (name 4)
0x8897  04 a2 01 91 00 00 00   PrunedPaths[1] = 145
0x889e  04 a2 02 97 00 00 00   PrunedPaths[2] = 151
0x88a5  59 01 15 73 01         VisNoReachPaths[0]  name compact 59 01 → 89; info 0x15 (Object, 2 B); ref compact 73 01 → 115 = PatrolPoint30
0x88aa  17 22 80 96 98 00      visitedWeight = 10000000
0x88b0  19 22 7b 00 00 00      bestPathWeight = 123
0x88b6  18 15 46 05            nextNavigationPoint → ref 326 = Teleporter3
0x88ba  1b 15 6f 01            previousPath → ref 111 = PathNode60
0x88be  0f 24 73 52 01 43      LastRenderTime (Float)          ← Actor fields start here
0x88c4  08 24 0b 0a 10 45      DistanceFromPlayer
0x88ca  07 05 02               Level → LevelInfo0
0x88cd  06 06 1d               Tag = 'PathNode'
0x88d0  05 5a 03 06 <6 B>      Region (Struct PointRegion; size code 5 → u8 size 6)
0x88da  09 3a 01 <12 B>        Location (Struct Vector, size code 3 → 12 B)
0x88e9  0c 3a 01 <12 B>        OldLocation
0x88f8  02                     None
```

Tag order = the class chain's declaration order, **most-derived class first** (PatrolPoint's
`Nextpatrol`/`pausetime` precede the NavigationPoint block, which precedes Actor's), matching
`uprops.class_serialization_order`. Indices > 0x7f would use the 2/4-byte packed form
(`upackage.read_array_index`); never needed for 16-slot arrays.

### 3.3 Cross-check: indices point at ReachSpecs whose Start/End is that actor ✅

Every `Paths(i)` names a spec with `Start` = this actor and `bPruned=0`; every `upstreamPaths(i)` a
spec with `End` = this actor and `bPruned=0`; every `PrunedPaths(i)` a spec with `Start` = this
actor and `bPruned=1` (all sampled nodes in the three maps, `disk`; whole-map tally, `xcheck`):

| (in Start.Paths, in Start.PrunedPaths, in End.upstreamPaths, bPruned) | Bar | UNATCOHQ | UNATCOIsland |
|----------------|-----|-----|-----|
| (T, F, T, 0) — normal live edge | 304 | 767 | 5252 |
| (F, T, F, 0→**1**) — pruned: moved to `PrunedPaths`, dropped from End's `upstreamPaths` | 497 | 1005 | 6804 |
| (T, F, F, 0) — live, End's `upstreamPaths` never got it | 19 | 2 | 42 |
| (F, F, T, 0) — live, Start's `Paths` never got it | 44 | 4 | 281 |
| (F, F, F, 0) — live edge referenced by **no** node | 25 | 0 | 135 |

The unreferenced live edges all start at nodes whose `Paths`+`PrunedPaths` total exactly 16 (Bar: 21
such nodes, e.g. `PatrolPoint26` has 21 outgoing specs, 16 indexed). 🔬 So the per-node arrays are a
hard 16-slot cap filled at insertion time: an edge beyond the cap stays in `ReachSpecs` but is
invisible to that side's array. Max observed: `Paths` 10, `PrunedPaths` 14, `upstreamPaths` 13, sum
16. **`ReachSpecs` is ordered by `Start`**: all specs of one start node are contiguous (Bar 76 runs =
76 distinct starts; UNATCOIsland 1196 = 1196). Indices inside a node's `Paths` are not sorted
(`PatrolPoint26.Paths = 14,18,17,3`).

`ReachFlags` seen: `0x1` (walk) everywhere; `0x9` (walk|jump) on `MapExit0→PlayerStart0`; a pruned
edge keeps its `R`/`H` (`PatrolPoint27→PathNode24` R=15 H=27).

## 4. Script code that calls the pathing natives (game `dx` `DeusEx.u`) ✅

Native ids (`decls`, both versions unless noted): `MoveTo` 500, `MoveToward` 502, `LineOfSightTo`
514, `FindPathToward` 517, `FindPathTo` 518, `describeSpec` 519, `actorReachable` 520,
`pointReachable` 521, `ClearPaths` 522, `FindStairRotation` 524, `FindRandomDest` 525,
`PickWallAdjust` 526, `WaitForLanding` 527, `PickTarget` 531, `CanSee` 533,
`FindBestInventoryPath` 540. **`dx` only** (absent from the `ued` `Engine.u`): `AICanSee` 705,
`AICanHear` 706, `AICanSmell` 707, `AIDirectionReachable` 708, `AIPickRandomDestination` 709,
`ReachablePathnodes` 1004 (iterator), `ComputePathnodeDistances` 1020, and the `Actor.AI*Event`
family 700–716.

Bytecode callers in the game's `DeusEx.u` (`calls dx DeusEx`; a function is listed once per native):

| Native | Calling functions |
|--------|-------------------|
| `FindPathToward` | `ScriptedPawn.GetNextWaypoint`, `.Burning.PickDestination`, `.Following.PickDestination`, `.Shadowing.PickDestination`, `.Attacking.PickDestination` |
| `FindPathTo` | `ScriptedPawn.Seeking.GetNextLocation`, `.Alerting.GetNextAlarmPoint`, `.Wandering.GoHome` |
| `actorReachable` | `ScriptedPawn.GetNextWaypoint`, `.Following.PickDestination`, `.Attacking.PickDestination` |
| `pointReachable` | `ScriptedPawn.Seeking.GetNextLocation`, `.Alerting.GetNextAlarmPoint`, `.Wandering.GoHome`, `Bird.Flying.PickFinalDestination`, `Bird.Flying.CheckDestination` |
| `ReachablePathnodes` | `ScriptedPawn.ComputeAwayVector`, `.Seeking.GetOvershootDestination` |
| `AIDirectionReachable` | `ScriptedPawn.TryLocation`, `.GetNextVector`, `.Fleeing.PickDestination`, `.AvoidingPawn.PickDestination`, `.AvoidingProjectiles.PickDestination`, `.Following.PickDestination`, `.Seeking.GetNextLocation`, `.OpeningDoor.FindBackupPoint`, `Animal.GetFeedSpot`, `CleanerBot.Wandering.PickDestination` |
| `AIPickRandomDestination` | `ScriptedPawn.Fleeing/Burning/Shadowing/Attacking.PickDestination` |
| `ComputePathnodeDistances` | **no caller** in `DeusEx.u` (declared, unused by script) |

Engine-side script (`dx` and `ued` `Engine.u`, identical): `Mover.HandleTriggerDoor → actorReachable`,
`PlayerPawn.ShowPath → FindPathTo`. **The `ued` `DeusEx.u` is stubbed** (63 Function exports, 224
bytes of bytecode total, vs 4933 / 699 540 in the game's) — no editor-side script calls any
pathing native.

PatrolPoint chains (`refs`): `PatrolPoint.PreBeginPlay` resolves `Nextpatrol` (Name) into
`NextPatrolPoint` (object) at play start; consumers are `ScriptedPawn.Patrolling.PickDestination` and
`.PickStartPoint` (the latter also walks `LevelInfo.NavigationPointList`/`nextNavigationPoint` and
reads `visitedWeight`). `ScriptedPawn.Burning.PickDestination` and `LiftCenter.SpecialHandling` walk
the `NavigationPointList` too. Nothing in either `DeusEx.u` reads `Paths`/`upstreamPaths`/
`PrunedPaths`/`ExtraCost`/`bEndPoint`/`bSpecialCost` from script — those are native-only.

Events the build may call (script declarations, both versions ✅):

- `NavigationPoint.SpecialCost(Pawn)` — `event`, empty body (`04 0b` = return nothing), `iNative=0`,
  **no override anywhere** in `Engine.u` or `DeusEx.u`. 📖 The 469 builder consults it only when
  `bSpecialCost` is set; since nothing sets `bSpecialCost` and no class overrides it, it is dead for
  Deus Ex content.
- `NavigationPoint.Accept(Actor Incoming, Actor Source)` — `event`, defined (114 B, reads/writes
  `taken`); overridden by `Teleporter.Accept` (836 B). Runtime teleport hook, not a build hook.
- `WarpZoneInfo.Generate()` / `ForceGenerate()` — `simulated event`s; `Generate` is called from
  `WarpZoneInfo.PreBeginPlay`/`ActorEntered`, `ForceGenerate` from `Trigger`/`Generate`. Retail maps
  contain **zero** `WarpZoneInfo` actors, so the WarpZone marker path is dead for Deus Ex content.

## 5. Placement rules and the auto-built classes in retail maps ✅

- Scout fit is tested against each node's own cylinder: 12×15 for PathNode/PatrolPoint/Ambushpoint/
  HomeBase/LiftCenter/LiftExit/TriggerMarker/ButtonMarker/SpawnPoint/WanderPoint/HidePoint/MapExit,
  18×40 for PlayerStart/Teleporter, 20×40 for InventorySpot(`dx`)/WarpZoneMarker; all
  `bCollideWhenPlacing=True` except InventorySpot(`dx`)/WarpZoneMarker. Authored overrides on disk are
  rare (Teleporters at 60/80 in the three maps).
- **`bAutoBuilt=True`: 0 actors in all 88 maps** — the v68 class has no such var; a v68 map cannot
  carry it. Any `bAutoBuilt` in a UED22 golden is 469-only.
- **`InventorySpot`: 0 actors in all 88 maps; `WarpZoneMarker`: 0; `WarpZoneInfo`: 0** — while the
  maps hold 0–175 `Inventory` actors each (UNATCOIsland 59, UNATCOHQ 14, Bar 22). 🔬 So the Deus Ex
  editor's path build left no InventorySpots behind (either its `definePaths` does not spawn them, or
  it strips them before save). If UED22's `PATHS BUILD` does spawn one per `Inventory`, its golden
  will differ from retail in node count, `ReachSpecs`, and every neighbouring node's arrays.
- Nav classes actually present in the three maps: Bar PathNode 62 / PatrolPoint 8 / HidePoint 5 /
  Teleporter 4 / PlayerStart 1; UNATCOHQ 228 / 5 / 8 / 2 / 1; UNATCOIsland 1074 / 107 / 12 / 2 / 1 +
  SpawnPoint 1 + MapExit 1. No LiftCenter/LiftExit/Ambushpoint/HomeBase/WanderPoint in any of them.

## 6. Open questions for the engine-side findings

1. What writes `visitedWeight=10000000`, `bestPathWeight`, `previousPath`, `nextOrdered`/`prevOrdered`,
   `bEndPoint` and the single `cost=1000000` into the saved map — a `FindPathTo`-style sweep inside
   the DX builder (`dx-engine`), or a designer-time query? Byte parity needs its exact rule.
2. Insertion order that fills `Paths`/`upstreamPaths` (the 16-cap overflow decides which live edges
   become orphans) and the `PrunedPaths` append order.
3. Does UED22 `definePaths` spawn InventorySpots for a DX trunk, and with what collision size given
   the `0x68670004` class default?
4. `bAutoBuilt`/`bTwoWay` (469-only) — does the 469 builder write them on nodes it creates, making a
   UED22 golden diverge from any v68 reference by construction?
