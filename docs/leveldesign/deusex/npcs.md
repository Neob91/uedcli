# Populating a level with NPCs — `ScriptedPawn`  [DX]

Deus Ex NPCs are `ScriptedPawn`s. Never place the abstract bases — place a concrete leaf
(a specific troop, civilian, or animal) and configure its orders, alliances, reactions, and inventory.

## Workflow order

NPCs move by walking the level's path network, so do this in sequence:

1. Pathnode the level and rebuild paths first. With no paths, an NPC stands still forever and
   gives no error. Drop `PathNode`s 300–700 uu apart (≤350 on stairs), each visible from the next,
   then rebuild paths. (Pathing basics are in the [general actors guide](../general/).)
2. Place a concrete `ScriptedPawn` leaf on the floor.
3. Set `Orders` + `OrderTag` — what the NPC does.
4. Set `InitialAlliances` — who it likes and hates.
5. Tune reactions / fears / alarm — usually leave the class defaults.
6. Set `InitialInventory` — weapons and items it carries.
7. Set `BindName` if a conversation, flag, or trigger references this NPC.
8. Rebuild paths again and playtest.

```
actor build DeusEx.MJ12Troop --at 512,256,80 --rotate 0,16384,0 \
  --prop Orders=Patrolling --prop OrderTag=warehouse_patrol \
  --prop BindName=mj12_guard_a | actor add -
```

---

## Orders — what the NPC does

`Orders` is a state name (not an enum): the pawn does `GotoState(Orders)`. Default is
`Wandering`. Mapper-set values, most paired with an `OrderTag` naming the target:

- `Idle` — stand and do nothing (no wandering).
- `Standing` — hold a post. Leash radius via `HomeTag` / `HomeExtent` (default 800).
- `Sitting` — occupy a seat.
- `Patrolling` — walk a chain of `Engine.PatrolPoint` actors: `OrderTag` = the first point's
  `Tag`, and each point's editable `Nextpatrol` names the next point's `Tag`. (`NextPatrolPoint` is
  the runtime-resolved object ref, not the field you set.)
- `WaitingFor`, `Following`, `Shadowing` (stealth-tail).
- `Wandering` — the roaming default.
- `Dancing`.

`GoingTo` / `RunningTo` are scripting-only (conversation/mission scripting, not an initial `Orders`).
`Seeking`, `Fleeing`, `Attacking`, `Alerting` are combat/alert states the AI enters
itself — shape them via the reactions/fears/alliances below; don't author them as an `Orders`.

A conversation can reprogram an NPC via `ConvOrders` / `ConvOrderTag`, applied when the
conversation ends.

## Alliances — who is friend or foe

`InitialAlliances[0..7]` is an array of `(AllianceName, AllianceLevel, bPermanent)`:

- `AllianceLevel` runs −1 (hostile) … 0 (neutral) … +1 (friendly).
- The player's alliance name is `"Player"`. To make an NPC hostile to the player, add `"Player"` at
  level −1.
- `bPermanent` locks the relationship so it can't decay or flip.

## Reactions, hate, and fears — usually leave the defaults

Three stimulus blocks control temperament. Class defaults are tuned per role (soldiers
engage and raise alarms; civilians flee), so you rarely touch these:

- Reactions (`bReact*`) — do I engage? `bReactPresence` (default true → attack on sight),
  `bReactShot`, `bReactAlarm`, `bReactCarcass`, `bReactDistress`, `bReactLoudNoise`, `bReactProjectiles`.
- Hate (`bHate*`) — what turns me hostile? `bHateShot` / `bHateInjury` (default true), `bHateWeapon`,
  `bHateHacking`, `bHateCarcass`.
- Fears (`bFear*`) — what makes me flee? `bFearWeapon`, `bFearShot`, `bFearInjury`, `bFearCarcass`,
  `bFearAlarm`, `bFearProjectiles`, `bFearHacking`.

Alarm: `RaiseAlarm` (vanilla default `RAISEALARM_BeforeFleeing`; `Animal`/`Robot` = `RAISEALARM_Never`
— `actor prop get` returns `BeforeAttacking` from the UED22 editing package, a recompile divergence
from shipped behaviour), `bEmitDistress`, `MaxProvocations` (default 1).

> These UT/Unreal knobs do not exist in DX — don't set them: `bFearDarkness`, `bFearIndoors`,
> `bFearZones`, `HateTag`, `HateThreshold`, `IdealRange`, `SeekTag`,
> `bCanClimb`, `bGenerateFleshFrag`, `ThingFactory`. DX drives NPCs via ScriptedPawn orders rather
> than the stock `AmbushPoint` marker; `AlarmPoint` doesn't exist at all.

## Combat tuning and inventory

- `InitialInventory[0..7]` — `(class, Count)` pairs; the weapons/items the NPC spawns with.
  `bKeepWeaponDrawn` keeps a weapon out.
- `MaxRange` / `MinRange`, `MinHealth`, `EnemyTimeout`, and `BaseAccuracy` (lower = more accurate).

## Binding

- `BindName` — a spaces-free identifier that conversations, flags, and triggers key off of (e.g. a
  flag `BindName$"_Dead"` fires when this NPC dies). Set it on any NPC story logic references.
- `FamiliarName` / `UnfamiliarName` — the HUD labels before/after you know them.
- `bImportant` / `bInvincible` — protect a plot-critical NPC.

---

## The roster (place a concrete leaf)

Regenerate the full tree with `class list --subclass-of DeusEx.ScriptedPawn`. The families:

- `HumanMilitary` — `MJ12Troop`, `MJ12Commando`, `UNATCOTroop`, `Soldier`, `Terrorist`.
- `HumanCivilian` — `Bartender`, `Businessman1`–`3`, `Doctor`, `Sailor`, `ScientistMale` /
  `ScientistFemale`, …
- `HumanThug` → `TerroristCommander`.
- `Animal` — `Rat`, `Greasel`, `Karkian`, `Gray`, `Doberman`, `Pigeon`, `Fish`.
- `Robot` — `MilitaryBot`, `SecurityBot2`–`4`, `SpiderBot`, `CleanerBot`, `MedicalBot`.

Each killable pawn has a paired `<Name>Carcass` (its `CarcassType`) for the death body.

---

## See also

- [`classes.md`](classes.md) — the rest of the DX class catalog.
- [`gameplay-wiring.md`](gameplay-wiring.md) — alliance triggers, alarms, and event wiring.
- [`conversations-and-computers.md`](conversations-and-computers.md) — giving NPCs dialogue via `BindName`.
- [`design-philosophy.md`](design-philosophy.md) — placing guards to make readable stealth.
