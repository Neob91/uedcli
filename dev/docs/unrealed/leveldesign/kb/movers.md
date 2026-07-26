# Movers — doors, lifts, and moving brushes  [ENGINE] + [DX]

Part of the split-out **level-design knowledge base**. FULL dev reference for UE1/DX movers: what a
mover is, the engine subclass family vs the Deus Ex `DeusExMover` family, keyframe authoring (incl. the
inverted GUI record flow), encroachment behaviour, initial states, the mover self-lighting "black door"
fix, and the uedcli `mover key` verbs. Siblings: [`lighting.md`](lighting.md) · [`textures.md`](textures.md)
· [`actors-collision-pathing.md`](actors-collision-pathing.md). Parent monolith:
[`README.md`](README.md). Engine-driving: [`../../commands.md`](../../commands.md),
[`../../t3d.md`](../../t3d.md), [`../../quirks.md`](../../quirks.md).

**Confidence markers:** ✅ uedcli-used / live-verified · 🔬 live-probed against the real DX binary/editor ·
📖 tutorial-corpus. **[ENGINE]** = generic UE1 · **[DX]** = Deus-Ex-specific.

---

## 1. What a mover is  [ENGINE]

A **mover IS one brush** promoted to an actor. It is a single, self-contained brush that moves between
authored poses — the engine's mechanism for doors, lifts, elevators, drawbridges, crushers, rotating
fans, breakable glass, and anything else that shifts at runtime.

- A mover does **not** cut the BSP — converting a detail brush to a mover *removes* its BSP nodes (a
  perf lever; see [`zones-performance.md`](./zones-performance.md)).
- A mover always has `Physics = PHYS_MovingBrush` (see [`actors-collision-pathing.md`](actors-collision-pathing.md) §2).
- **Need a complex mover shape?** Intersect it down to **one clean single brush** first — keep the
  builder brush simple. **Reset ALL** (scale / rotation / pivot) before intersecting the brush destined
  to become a mover, or the live transform leaks into the result.

---

## 2. The subclass families — engine vs [DX]  🔬

**Engine mover class** [ENGINE] 🔬: in this DX build `Engine.u` ships **only the base `Mover`** — the
stock-Unreal subclasses (`RotatingMover`, `LoopMover`, `AttachMover`, `GradualMover`, `MixMover`,
`AssertMover`) are **NOT present**. DX supplies its own mover subclasses in `DeusEx.u` (below).

**Deus Ex ships its own mover classes** [DX] 🔬 — reach for these, not the raw engine `Mover`, in a DX
level. Only the door/panel classes extend `DeusExMover`; the lifts extend `Engine.Mover` **directly**:

| DX class | Extends | Is |
|---|---|---|
| `DeusExMover` | `Engine.Mover` | The base DX door/panel mover. |
| `BreakableGlass` | `DeusExMover` | A 1-unit translucent breakable pane. |
| `BreakableWall` | `DeusExMover` | A breakable wall (`doorStrength` ~40%). NOTE: breaking is gated by `minDamageThreshold` (default **20**); a crowbar (~6 dmg) can't break it until you lower THAT, not just `doorStrength`. |
| `ElevatorMover` | `Engine.Mover` (**not** `DeusExMover`) | A DX lift/elevator. |
| `MultiMover` | `Engine.Mover` (**not** `DeusExMover`) | A multi-stop mover driven by `SeqKey`/`SeqTime` (§8). |
| `CEDoor` (Carone) | `DeusExMover` | A **third-party** community door subclass — **not in stock `DeusEx.u`**; only if a mod ships it. |

**`DeusExMover` gameplay properties** 🔬: `bIsDoor`, `bLocked`, `bOneWay`, `lockStrength`, `bPickable`,
`doorStrength`, `bBreakable`, `KeyIDNeeded` (the `NanoKey` `KeyID` that unlocks it — see
[`actors-collision-pathing.md`](actors-collision-pathing.md) pickups). These distinguish a locked,
pickable, key-gated door from a plain moving brush.

---

## 3. Keyframes — max 8, authored offline  🔬✅

A mover interpolates between **keyframes**: numbered poses **0–7 (max 8)**.

- **Key 0 is the base / closed pose.** Higher keys are the open/intermediate poses.
- `NumKeys` **must equal the number of keys actually used** — a mismatch misbehaves.
- **`KeyPos(i)` / `KeyRot(i)` are OFFSETS from the base pose**, not absolute world coordinates. uedcli
  stores the base at `KeyNum=0` and **never emits `BasePos` / `BaseRot`** (the base is the brush's own
  authored location).
- The **pivot** (rotation centre for `KeyRot`) is set by clicking a vertex in the GUI.

### 3.1 The inverted GUI "record" flow  🔬 (a trap)

The UnrealEd keyframe recording flow is **inverted** and catches everyone:
1. The mover starts at **key 0** (its authored pose).
2. Select the **TARGET key first** (e.g. "Key 1"), **then** move/rotate the brush to where that key
   should be.

You are not "moving then recording" — you select the destination slot, then pose. uedcli sidesteps this
entirely: keys are authored as T3D offsets via the `mover key` verbs (§6), so the inverted record flow
never applies at the uedcli seat — but it is essential context for a GUI-aware reader.

---

## 4. `MoverEncroachType` — what a mover does when it hits something  🔬

`MoverEncroachType` controls the mover's behaviour when it **encroaches** (its motion runs into a pawn or
object):

| Value | Behaviour |
|---|---|
| `ME_ReturnWhenEncroach` | **Default.** Reverse back to the previous key (a door that re-opens when blocked). |
| `ME_CrushWhenEncroach` | Keep going and **damage** what it hits (a crusher). |
| `ME_StopWhenEncroach` | Halt in place until the obstruction clears. |
| `ME_IgnoreWhenEncroach` | Pass through — used for **two-way bump doors** (no re-open logic). |

🔬 `ME_ReturnWhenEncroach` is the base `Engine.Mover` default; **`DeusExMover` overrides its own default
to `ME_StopWhenEncroach`** — so a DX mover stops (rather than reverses) on encroach unless you set
`--prop MoverEncroachType=…`.

---

## 5. `InitialState` — how the mover is triggered  🔬

`InitialState` sets the mover's trigger mode:

| State | Behaviour |
|---|---|
| `BumpOpenTimed` | **Default.** Opens when bumped, auto-closes after a delay. |
| `TriggerOpenTimed` | Opens on `Trigger`, auto-closes after a delay. |
| `StandOpenTimed` | Opens while stood on (lifts). |
| `TriggerToggle` | Trigger toggles open/closed. |
| `TriggerControl` | Opens on `Trigger`, holds open while triggered, closes when the trigger ends. |
| `TriggerPound` | Repeatedly moves out-and-back while active (pistons / crushers). |
| `''` (empty) | Inert until scripted (the mover has no auto state). |

🔬 The valid states are the `state()` names in `Engine.Mover` — `BumpOpenTimed`, `BumpButton`,
`StandOpenTimed`, `TriggerOpenTimed`, `TriggerControl`, `TriggerPound`, `TriggerToggle`. **There is NO
`LoopMove` state.** A continuously spinning prop (a fan) is normally a **`PHYS_Rotating` decoration**
(`RotationRate`), not a mover; a mover that repeatedly cycles is `TriggerPound` or scripted.

- **Base default is `BumpOpenTimed`** 🔬 (read from `Engine.Mover`), but **`DeusExMover` overrides its
  own default to `TriggerToggle`** 🔬 — so a DX door built via `--mover-class DeusEx.DeusExMover` starts
  as a trigger-toggle unless you set `--prop InitialState=…`.

- **Triggering** uses the standard `Tag` / `Event` wiring: trigger a mover by matching its `Tag`; a mover
  **fires its own `Event`** when its keyframes finish (chain movers or fire other actors this way).
- **Return-groups and `MoverEncroachType` are DISTINCT** — do not conflate them. A **return-group** is
  several movers that move together under one **leader** (one mover drives the group); `MoverEncroachType`
  is the independent per-mover collision-response setting above.

---

## 6. Authoring movers with uedcli  ✅

uedcli authors movers entirely **model-side** — no editor:

```
# 1. build the mover shape as a mover-class brush (base pose only — no CsgOper, no keyframes yet)
brush build cube --mover-class DeusEx.DeusExMover --width 72 --breadth 8 --height 144 | actor add -

# 2. set the key count, then author each key. `count` gets/sets NumKeys (2..8, non-destructive);
#    `move`/`rotate <name> <index>` edit an EXISTING key (1<=index<NumKeys) with --to (needs a frame:
#    --from-base offset, or --from-world absolute) or --by (frame-agnostic delta).
mover key count  <MoverName> 3                    # 3 keys (0,1,2); raise before editing keys 1,2
mover key move   <MoverName> 1 --from-base --to 0,0,144   # key 1 = 144uu above base (a lift's top)
mover key move   <MoverName> 1 --by 0,0,8        # nudge key 1 up 8 more
mover key rotate <MoverName> 2 --by 0,16384,0    # rotate key 2 by +90 deg yaw
mover key list   <MoverName>                     # inspect
mover key remove <MoverName> 1                   # delete a key + compact (NumKeys--)
```

- `brush build <shape> --mover-class <Package.Name>` is the **generator** producing a **base Mover** (no
  `CsgOper`, base pose only); it prints a T3D snippet to stdout — the write into the trunk is always
  `… | actor add -` (name allocation happens at `actor add`).
- Keyframes are then authored with the **trunk-editing `mover key` verbs**
  (`add` / `move` / `rotate` / `remove` / `list`).

> **UnrealEd GUI equivalent:** *Add Mover*, then the inverted keyframe-record flow (§3.1).

---

## 7. The mover self-lighting "black door" fix  🔬

A mover is an **actor**, so — unlike baked BSP surfaces — it is **lit at runtime**, and by default it
samples lighting from its **key-0 pose ONLY**. A door that opens *away* from its lit key-0 position
therefore renders **black** in its open pose (the infamous "black door").

Fixes:
- Flag the mover's surfaces **`Unlit`** (fullbright — simplest, but loses shading).
- Use **Special-Lit rings** (`bSpecialLit` lights + `PF_SpecialLit` surfaces — see
  [`lighting.md`](lighting.md) / [`textures.md`](textures.md)) to light the mover independently of its
  pose.
- Set **`bDynamicLightMover=True`** and use **`WorldRaytraceKey` / `BrushRaytraceKey`** to control which
  key pose the mover is lit from.

*(This is the mover half of the two-tier lighting model in [`lighting.md`](lighting.md) §1: BSP surfaces
are baked; actors — including movers — are lit at runtime.)*

---

## 8. Related recipes & cross-links

- **Breakable glass / walls:** use `BreakableGlass` / `BreakableWall` (§2) — set `doorStrength` low
  enough that a crowbar breaks it. A visual glass sheet by itself does **not** block; see the glass/grille
  collision recipe in [`actors-collision-pathing.md`](actors-collision-pathing.md) §1.
- **A mover bordering a water zone:** the water-surface sheet is immovable (zone portals can't move), so
  rising/falling water needs scripting — see the water recipe in
  [`zones-performance.md`](./zones-performance.md) §4.1.
- **The iris doorway:** 8 quarter/eighth-segment movers all keyed to one shared `Event` (see
  [`README.md`](README.md) §6 curved geometry).
- **Multi-stop elevators [DX]:** `SequenceTrigger` + `MultiMover` (`SeqKey1..4`/`SeqTime1..4`) +
  `ElevatorMover` (`bFollowKeyframes`) — see [`README.md`](README.md) §10.2.
- **UnrealEd stability:** movers are a known editor-crash source; drive the editor defensively (see
  [`../../quirks.md`](../../quirks.md) "Stability").
