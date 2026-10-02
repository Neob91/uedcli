# Populating levels with NPCs — the DX `ScriptedPawn` system  [DX]

Deus Ex NPCs are `ScriptedPawn`s, a DX-specific system absent from stock
UnrealEngine 1 / UT99 (UT uses a different bot-AI `Pawn`/`ScriptedPawn` lineage
with different property names — see §8). Everything below is ✅🔬 verified present
in the pristine shipped `DX/System/DeusEx.u` unless noted.

> **Siblings.** [`dx-classes.md`](dx-classes.md) (movers/devices/triggers) ·
> [`dx-conversations-computers.md`](dx-conversations-computers.md) (wiring NPCs
> to conversations) · [`asset-pipeline.md`](asset-pipeline.md) (custom character
> meshes/skins). Engine pathing/NavigationPoint base layer:
> [`README.md`](README.md) §8.

Markers: `[DX]` throughout (this whole system is DX). ✅🔬 = decoded from the real
`DeusEx.u`; 📖 = DX SDK manual.

---

## 1. `Orders` is a state name, not an enum  [DX] ✅🔬

`FollowOrders()` does `GotoState(Orders)`: `Orders` is a string naming the state
the pawn enters, default `Wandering`. Set `Orders` (and usually a companion
`OrderTag` naming the target actor) to program the NPC. Mapper-facing order
states:

| `Orders` | Behaviour | Companion |
|---|---|---|
| **Idle** | stand and do nothing (no wandering) | — |
| **Standing** | hold a post | leashes to home via `HomeTag`/`HomeExtent` (def **800**) |
| **Sitting** | sit | a `Seat` actor tagged `OrderTag` |
| **Patrolling** | walk a **`PatrolPoint`** chain: `OrderTag` = the FIRST point's `Tag`; each point's editable **`Nextpatrol`** names the *next* point's `Tag` | `OrderTag` = first point's Tag |
| **WaitingFor** | wait for a tagged actor | `OrderTag` |
| **Following** | follow a tagged actor | `OrderTag` |
| **Shadowing** | stealth-tail a target | `OrderTag` |
| **Wandering** | roam (default); driven by `Restlessness`/`Wanderlust` | — |
| **Dancing** | dance in place | — |

Scripting-only orders (DX SDK manual — not normally set as an initial `Orders`):
`GoingTo` / `RunningTo` (walk/run to a tagged actor; used by conversation/mission scripting).

AI-entered states you do not author as an `Orders`: `Seeking`, `Fleeing`, `Attacking`,
`Alerting` are combat/alert states the AI enters on its own (shape them via Reactions/Fears/
alliances, §2/§5), plus `StartUp`, `Conversation`, `Burning`, `Stunned`, `Dying`, etc.

Runtime reprogramming: `SetOrders(name, newOrderTag, bImmediate)`. A conversation
reprograms an NPC via `ConvOrders` / `ConvOrderTag`, applied when the conversation
ends.

```
# a guard whose patrol starts at the point tagged "tower_p1"
actor build DeusEx.UNATCOTroop --prop Orders=Patrolling --prop OrderTag=tower_p1 \
  --at 256,256,16 | actor add -
# the patrol chain: OrderTag = the FIRST point; each point's Nextpatrol names the next point's Tag
actor build Engine.PatrolPoint --prop Tag=tower_p1 --prop Nextpatrol=tower_p2 --at 256,512,16 | actor add -
actor build Engine.PatrolPoint --prop Tag=tower_p2 --prop Nextpatrol=tower_p1 --at 512,512,16 | actor add -
```

---

## 2. The three stimulus blocks  [DX] ✅🔬

DX splits NPC reactivity into three property blocks of `bool` toggles; defaults
define the out-of-the-box temperament.

`var(Reactions) bReact*` — do I engage?
- `bReactPresence` (def True → attacks on seeing an enemy)
- `bReactShot`, `bReactAlarm`, `bReactCarcass`, `bReactDistress`
- `bReactLoudNoise` (→ seek the noise)
- `bReactProjectiles` (def True)
- `bReactFutz` (reacts to lightswitch/tampering "futzing")

`var(Stimuli) bHate*` — what turns me hostile? (feeds agitation)
- `bHateShot` (def True), `bHateInjury` (def True)
- `bHateWeapon` (drawn weapon nearby)
- `bHateHacking` (someone hacking a device)
- `bHateCarcass` (finding a body)

`var(Fears) bFear*` — what makes me flee?
- `bFearWeapon`, `bFearShot`, `bFearInjury`, `bFearCarcass`, `bFearAlarm`,
  `bFearProjectiles`, `bFearHacking`

> **Note:** `bReactFutz`, `bHateHacking`, `bHateCarcass`, `bFearHacking` are
> vanilla DX (binary-confirmed ✅🔬); a source fork (Deus-Ex-Plus) flagged them
> "new", but these four are stock.

Alarm broadcast: `RaiseAlarm` (`ERaiseAlarmType`: `RAISEALARM_Never` / `_BeforeAttacking` /
`_BeforeFleeing`). Vanilla default is `RAISEALARM_BeforeFleeing` on `ScriptedPawn`, with `Animal`
and `Robot` overriding to `RAISEALARM_Never`. ⚠ The UED22 editing package uedcli decodes shows
`_BeforeAttacking` uniformly (the `Animal`/`Robot` `Never` overrides dropped) — a recompile divergence,
like `Aggressiveness`; the shipped game uses the vanilla defaults above. Also `bEmitDistress`,
`MaxProvocations` (**def 1** — provocations before turning hostile).

```
# a civilian who flees on any weapon or shot, never engages
actor build DeusEx.Businessman1 --prop bReactPresence=False --prop bFearWeapon=True \
  --prop bFearShot=True --prop bFearInjury=True --at 0,0,16 | actor add -
```

---

## 3. Combat & behaviour tuning  [DX] ✅🔬

| Property | Meaning |
|---|---|
| `MaxRange` / `MinRange` | engagement distance band |
| `MinHealth` | flee/retreat threshold |
| `BaseAccuracy` | lower = better aim (0.2 is sharp; higher = wilder) |
| `EnemyTimeout` | how long a lost enemy stays "the enemy" |
| `bDefendHome` | defend the `HomeTag` area rather than chase |
| `Restlessness` / `Wanderlust` / `Cowardice` | temperament floats (drive Wandering/Fleeing) — **non-editable** plain `var`s (no browser category); the AI reads them, you don't author them |
| `InitialInventory[8]` | array of `struct { class<Inventory>; Count }` — the 8-slot loadout |
| `bKeepWeaponDrawn` | start with weapon out |

Reference defaults ✅🔬: MJ12Troop `MaxRange` **1000**, `BaseAccuracy` **0.2**,
`Health` **100**; cylinder **20×47.5** (same as JC Denton).

Arm NPCs via `InitialInventory` (8 slots; class + count each), not by dropping pickups nearby.

---

## 4. The class roster  [DX] ✅🔬

Place a concrete leaf class, never an `abstract` base. The bases group the
roster:

- **`HumanMilitary`** → `MJ12Troop`, `MJ12Commando`, `UNATCOTroop`, `Soldier`,
  `Terrorist`
- **`HumanCivilian`** → `Bartender`, `Businessman1`/`2`/`3`, `Doctor`, `Sailor`,
  `ScientistMale`/`ScientistFemale`, …
- **`HumanThug`** → `TerroristCommander`
- **`Animal`** → `Rat`, `Greasel`, `Karkian`, `Gray`, `Doberman`, `Pigeon`,
  `Fish`, …
- **`Robot`** → `MilitaryBot`, `SecurityBot2`/`3`/`4`, `SpiderBot`, `CleanerBot`,
  `MedicalBot`

Each killable class has a paired `<Name>Carcass` death body, referenced via the
pawn's `CarcassType`. Ambient spawners exist (`PawnGenerator`, `FishGenerator`,
`FlyGenerator`) for background critters.

Discover the live roster:
```
bin/uedcli class list --flat --subclass-of DeusEx.ScriptedPawn
```

---

## 5. Binding, alliances & identity  [DX] ✅🔬

| Property | Meaning |
|---|---|
| `BindName` | a space-free identifier the conversation system + flags key off (e.g. `BindName$"_Dead"`). This is how a con/flag targets this NPC. |
| `FamiliarName` / `UnfamiliarName` | HUD name shown before/after you "know" them |
| `bCanConverse` | whether the NPC can *currently* be talked to — **engine-managed** (a plain `var` the AI sets in its states, not a mapper `var()`); don't rely on setting it |
| `bImportant` / `bInvincible` | plot-critical protection |
| `InitialAlliances[8]` | array of `struct { AllianceName; AllianceLevel; bPermanent }`; `AllianceLevel` is −1 (hostile) .. 0 (neutral) .. +1 (friendly); the player alliance name is `"Player"` |

Make an NPC hostile to the player with an `InitialAlliances` entry
`AllianceName="Player"`, `AllianceLevel=-1`. Alliances can be flipped at runtime
by an `AllianceTrigger`.

```
actor build DeusEx.MJ12Troop --prop BindName=tower_guard \
  --prop Orders=Standing --prop OrderTag=tower_post \
  --prop InitialInventory.0=(Inventory=Class'DeusEx.WeaponPistol',Count=1) \
  --at 300,300,16 | actor add -
# (then add a "Player" @ -1 alliance entry to make him hostile)
```

---

## 6. AI perception internals  [DX] 🔬 (the knobs behind Orders/Reactions/Fears)

The perception model reads these below the mapper surface. Only some are editor-editable
(`var(Category)`, marked ✎); the rest are engine-internal plain `var`s you can't author:

| Property | Default | Editable? | Meaning |
|---|---|---|---|
| `HearingThreshold` | **0.15** | ✎ (AI) | min loudness heard |
| `SightPercentage` | **0.5** | — internal | fraction of a target that must be visible to "see" |
| `AIHorizontalFov` | **160** | ✎ (AI) | horizontal field of view (degrees) |
| `EnemyTimeout` | — | ✎ (AI) | see §3 |
| `SeekType`/`SeekLevel`/`SeekPawn` | — | — internal | `SEEKTYPE_None/Sound/Sight/Guess/Carcass` — drives `Seeking` |
| `HomeTag` / `HomeExtent` | — / **800** | ✎ (Orders) | leash anchor + radius for Standing/`bDefendHome` |

Agitation is per-alliance (`AllianceInfoEx.AgitationLevel`) with
`AgitationSustainTime` (**30**) / `AgitationDecayRate` (**0.05**); fear with
`FearSustainTime` (**25**) / `FearDecayRate` (**0.5**). (These sustain/decay constants are
engine-internal `var`s, not editor-editable.) Stimuli broadcast/receive
through `AIStartEvent`/`AIEndEvent` (`EAIEventType`: `EAITYPE_Visual`/`EAITYPE_Audio`/`EAITYPE_Olifactory`). Extra
home/flee toggles: `bDefendHome`, `bEmitDistress`, `bCower`, `bLeaveAfterFleeing`.

---

## 7. End-to-end placement workflow  [DX]

1. Pathnode the level first. With no path network an NPC won't move, silently
   (no error). Place `PathNode`s (engine class, spacing <700 uu, <350 on stairs)
   and build paths (`PATHS BUILD` / F8 → Paths Define). See
   [`README.md`](README.md) §8.
2. Place a concrete class on the floor (not an abstract base).
3. Set `Orders` + `OrderTag` (§1). Add `PatrolPoint`s if Patrolling.
4. Set `InitialAlliances` (hostile-to-player = add `"Player"` at −1) (§5).
5. Tune Reactions / Fears / `RaiseAlarm` (§2).
6. Fill `InitialInventory` (§3).
7. Set `BindName` and wire conversations / triggers
   ([`dx-conversations-computers.md`](dx-conversations-computers.md)).
8. Rebuild paths, playtest.

uedcli performs steps 2–7 as `actor build DeusEx.<Class> --prop … | actor add -`
plus `actor prop set` for later edits. Paths (step 1/8) are a build-time editor
operation, not a trunk edit.

---

## 8. UT names that do not exist in DX  [DX] ✅🔬 (do not offer them)

Stock-Unreal / UT ScriptedPawn-AI names confirmed absent from `DeusEx.u`.
Offering them produces "property not found" errors:

- **Fears/reactions:** `bFearIndoors`, `bFearDarkness`, `bFearZones`
- **Hate targeting:** `HateTag`, `HateThreshold`
- **Combat/aggression:** `IdealRange`
- **Seeking targeting:** `SeekTag` (but `AlarmTag` is a real DX property — a
  `var(Orders) name AlarmTag` declared on the DX-modified `Engine.Pawn` and inherited by
  `ScriptedPawn`, so it is editable on a placed NPC; do not list it as absent)
- **Gibbing:** `bGenerateFleshFrag`
- **Mobility:** `bCanClimb`
- **Spawning:** `ThingFactory` (NPC spawning)
- **AI marker actors:** `AlarmPoint` (absent from DX). Note `AmbushPoint` exists
  in `Engine.u` as a stock `NavigationPoint`, but DX drives NPCs via `ScriptedPawn`
  orders (+ `PatrolPoint`), not `AmbushPoint`.

> **Caveat — `Aggressiveness` (and `bAssaultAttack`/`bDefendPosition`/`DefendPoint`):** vanilla DX's
> `HumanMilitary` has no such vars, but the UED22 editing package (the `DeusEx.u` recompile uedcli
> validates against) added `var() float Aggressiveness` (and those others) on `HumanMilitary`. uedcli
> accepts `Aggressiveness` (won't error), but the shipped game ignores it — don't rely on it. Not in
> the absent list above for that reason.

For DX behaviour analogous to one of these: hostility →
`InitialAlliances`/`bHate*`; ranged tuning → `MaxRange`/`MinRange`/`BaseAccuracy`;
search → tune Reactions (`bReactLoudNoise`) and let the AI enter `Seeking` on its own (you don't author
`Orders=Seeking`, and `SeekType`/`SeekLevel`/`SeekPawn` are non-editable internals); patrol/ambush →
`PatrolPoint` chains + `Orders`.
