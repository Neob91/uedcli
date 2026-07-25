# Actors, collision, physics & pathing  [ENGINE] (+ DX)

Part of the split-out **level-design knowledge base**. FULL dev reference for the **non-geometry actor
layer** — what turns clean geometry into a buildable, playable level: the cylinder collision model, the
physics enum, decorations, effects (and why UE1 has no particle emitters), `PlayerStart`, the KeyPoint
family, and NavigationPoint pathing. Siblings: [`lighting.md`](lighting.md) · [`textures.md`](textures.md)
· [`movers.md`](movers.md). Parent monolith: [`README.md`](README.md).
Engine-driving: [`../../commands.md`](../../commands.md).

**Confidence markers:** ✅ uedctl-used / live-verified · 🔬 live-probed against the real DX binary/editor ·
📖 tutorial-corpus. **[ENGINE]** = generic UE1 · **[DX]** = Deus-Ex-specific.

**uedctl seat** ✅: point actors are placed with `actor build Package.Class --prop KEY=VALUE --at X,Y,Z
--rotate P,Y,R | actor add -`; properties are read/edited with `actor prop get`/`actor prop set`; classes
are discovered with `class list` / `class show`. Any class default is read offline with
`actor build <Class> | actor add - | actor prop get - <Prop>` (an unset property resolves to its class
default; `class show` prints names/types only, **not** values).

---

## 1. Collision — the cylinder model  [ENGINE] 🔬

**UE1 actor collision is CYLINDER-BASED.** Every actor has one upright collision cylinder:

- `CollisionRadius` — half-width. `CollisionHeight` — **half**-height (total height = 2 × `CollisionHeight`).
- The cylinder is **always upright regardless of the actor's rotation.**
- **There is NO per-poly, box, or capsule actor collision in UE1** (that is UE2). A rotated crate still
  collides as an upright cylinder.

### 1.1 The flag families  🔬

UE1 splits collision into **colliding** (do I participate at all / can I be touched) and **blocking** (do
I physically stop movement):

| Flag | Meaning |
|---|---|
| `bCollideActors` | **Master switch** — required for any `Touch()` event or actor-vs-actor collision. |
| `bCollideWorld` | Collides against world geometry (falls, rests on floors). |
| `bCollideWhenPlacing` | Placement/spawn is collision-checked — the actor is nudged out of overlapping geometry/actors when placed (it does **not** floor-snap). |
| `bBlockActors` | Physically blocks **other actors**. |
| `bBlockPlayers` | Physically blocks **players** (UE1 splits these two — UE2 merges them). |
| `bProjTarget` | **Shootable** — a valid trace / projectile target. |

### 1.2 Collision recipes  🔬

| Want | Recipe |
|---|---|
| **Invisible wall** | A `BlockAll` actor (small area) **or** an **Invisible Collision Hull** (semisolid, all-invisible polys — large areas/doorways). The ICH **must NOT touch walls or zone boundaries** (wrecks the BSP → HOM). |
| **Non-blocking decoration** | All collide/block flags **off** — walk straight through. |
| **Shootable but walk-through** | `bCollideActors` + `bProjTarget` **on**, block flags **off** (a switch/panel you shoot but pass). |
| **Glass / grille** | A visual **sheet** (see [`textures.md`](textures.md)) + an **ICH behind it** to block — because **sheets NEVER block on their own.** For breakable glass use [DX] `BreakableGlass` ([`movers.md`](movers.md)). |

> **CRITICAL:** **A sheet never collides on its own.** A sheet is purely visual — to make it block, pair
> it with an Invisible Collision Hull or a 1-unit blocking cube.

`bBlockZeroExtentTraces` / `BlockingVolume` are **UE2** — out of scope.

---

## 2. The `Physics` enum  [ENGINE] 🔬

`Physics` sets how the engine moves the actor each tick:

| Value | Use |
|---|---|
| `PHYS_None` | **Default** for static props / KeyPoints — never moved by the engine. |
| `PHYS_Walking` | Pawns — needs a `Base` (the floor under it), else it falls. |
| `PHYS_Falling` | Drop-and-rest props / debris — obeys zone gravity, then rests. |
| `PHYS_Flying` | Flying pawns. |
| `PHYS_Swimming` | Actors in a water zone. |
| `PHYS_Rotating` | Spinning skybox / fan / pickup — uses `RotationRate`. |
| `PHYS_Projectile` | Fired projectiles. |
| `PHYS_Rolling` | Rolling objects. |
| `PHYS_Interpolating` | Follows `InterpolationPoint`s (+ `bInterpolating`). |
| `PHYS_MovingBrush` | **Every Mover** (see [`movers.md`](movers.md)). |
| `PHYS_Spider` | Wall-crawling. |
| `PHYS_Trailer` | Follows its `Owner` (trails, smoke). |

`PHYS_Ladder / PHYS_Karma / PHYS_Hovering / PHYS_RootMotion / PHYS_CinMotion` are **UE2 — out of scope.**
*(Note: ladders in DX are **texture-driven**, not a physics mode — see [`textures.md`](textures.md) §7.1.)*

**Companions:**
- `bStatic` — fully inert (no `Tick`/`Timer`/trigger). **Don't** set it just to stop a pickup spinning —
  it disables all scripting.
- `bMovable` — the actor may be moved.
- `bNoDelete` — cannot be `Destroy()`ed (set on brushes / nav points).
- `bHidden`, `bBounce`, `Mass`, `Buoyancy` (**> Mass → floats**).

---

## 3. Decorations  [ENGINE] (+ [DX]) 🔬

Place a concrete `Decoration` subclass for props (crates, furniture, debris, drinkables):

- `DrawType` — `DT_Sprite` / **`DT_Mesh`** / `DT_Brush` / `DT_None`.
- `Mesh` — the vertex mesh (a UE1 mesh takes **≤ 8 skins/textures** via `MultiSkins[8]` — this is a
  texture-slot limit, not a surface/poly-count limit; see [`README.md`](README.md) §15).
- `DrawScale` — **single uniform float** (`DrawScale3D` is UE2).
- `Skin` / `MultiSkins[8]` — the mesh's skin textures.
- **Gameplay:** `bPushable` (+ `PushSound`), the `contents`/`content2`/`content3` + `EffectWhenDestroyed`
  loot-spill fields (a breakable that spills loot when destroyed), `bBobbing` + `Buoyancy` (floats/bobs on
  water). **Damageability in DX is `DeusExDecoration.HitPoints`** — `Engine.Decoration` has **no `Health`**
  property (Health is a pawn field, not a decoration one in this build).
- **[DX]** uses its own **`DeusExDecoration`** family — adds a highlight **Name** label, `HitPoints`, and
  invincibility fields. Containers (`CrateBreakableMed{Combat,General,Medical}`) and info devices
  (DataCubes, books — `textTag` / `TextPackage`) are `DeusExDecoration` subclasses (see
  [`README.md`](README.md) §10).

---

## 4. Effects — UE1 has NO particle emitters  [ENGINE] 🔬 ❌ **Debunked**

> **UE1 / UT has NO particle `Emitter`s.** Emitters are **UE2+**. Do not reach for an `Emitter` class in
> a DX level — it does not exist.

UE1 effects are **sprite / trail-based**: `AnimatedSprite`, explosions, `SmokeTrail`, blood/sparks
(`BloodSpurt` / `Spark`), and trails driven by `PHYS_Trailer`. (All extend `Engine.Effects`.)

- **Coronas are a Light MODE, not an actor** — `bCorona=True` on a `Light` (see [`lighting.md`](lighting.md) §5.1).
- **[DX] adds its OWN particle system** — the `ParticleGenerator` family (`WaterDrips`, `LaserEmitter`,
  `ElectricityEmitter`, `Fire`, `ProjectileGenerator`, `TrashGenerator`), documented in
  [`README.md`](README.md) §10.1. That is DX-specific and does **not** exist in stock
  UT99.

---

## 5. `PlayerStart`  [ENGINE] 🔬

A `PlayerStart` (a `NavigationPoint` subclass) marks a spawn point:

- `bEnabled`; `bSinglePlayerStart` (def True); `bCoopStart` (def True); `TeamNumber`.
- Spawns the player **facing the actor's Yaw** (a directional arrow shows the facing).
- **Placed 40 uu above the floor** — its `CollisionHeight` decodes to 40, so a center 40 uu up rests the
  spawn cylinder's base on the floor. ✅🔬
- **Add MORE PlayerStarts than the max simultaneous players** (too few → telefrag on spawn).

---

## 6. The KeyPoint family  [ENGINE] 🔬

`KeyPoint` is the abstract base for **invisible location markers** (no own visible geometry):

- `AmbientSound` (Engine) / `AmbientSoundTriggered` (**[DX]** — `DeusEx.AmbientSoundTriggered`) — positional sound sources.
- `InterpolationPoint` — a node on a camera/mover interpolation path.
- `SpecialEvent` — fires scripted events. (**Not actually a `KeyPoint` in this build** — it's
  `Engine.SpecialEvent extends Triggers`; listed here for the scripting toolkit.)
- `BlockAll` / `BlockMonsters` / `BlockPlayer` — invisible blocking markers (collision recipes, §1.2).
- `LocationID` — names a HUD region ("the map name shown for this area").

*(Stock Unreal's `ThingFactory` / `GuardPoint` / `HoldSpot` are Unreal-AI markers **absent** in DX;
`WayBeacon` is present in `Engine.u` but unused by DX's `ScriptedPawn`-driven AI — see §7 and
[`README.md`](README.md) §11.2.)*

---

## 7. NavigationPoint & pathing  [ENGINE] (+ [DX]) 🔬

**Paths are COMPILED** into **reachspecs** — precomputed edges between `NavigationPoint`s that record
line-of-sight, traversability, and the **width/height/distance** of the connection (so bots know whether
they physically fit through). Without built paths, AI pawns **do not move** (silently).

- **Build:** console **`PATHS BUILD [HIGHOPT|LOWOPT]`** — this builds the **reachspecs**
  (`FPathBuilder::buildPaths` = `definePaths` → `createPaths` → `Prune`). **`PATHS DEFINE` alone only
  spawns marker NavigationPoints — no reachspecs** (`commands.md`, disassembly-corrected 2026-07-15).
- **Debug:** **Show Paths** (press `Q` to hide the BSP and see just the path graph). Paths **won't form
  over bad BSP** — a missing path graph is a BSP-hole symptom (see
  [`csg-bsp.md`](./csg-bsp.md)).

**Per-node controls** 🔬: `bOneWayPath` (a one-way edge), `ExtraCost` (bias the AI away from a node).
(`bNoAutoConnect`, `ForcedPaths[4]`, and `ProscribedPaths[4]` are **UE2** — verified **absent** from this
build's `Engine.PathNode`; do not use them.)

**Subclasses** 🔬: `PathNode` (generic), `PlayerStart` (§5), `InventorySpot` (auto-created at pickups),
`LiftCenter` / `LiftExit` (let AI ride elevators — one `LiftCenter` on the platform, one `LiftExit` **per served floor**, beside the shaft), `Teleporter`.
(There is **no** `Ladder` NavigationPoint and **no** `JumpSpot`/`JumpDest` in this DX build — climbable
ladders are **texture-driven**, see [`textures.md`](textures.md) §7.1.) **Single-player patrol markers:**
`Engine.PatrolPoint` (a route chain — set each point's editable **`Nextpatrol`** to the *next* point's
`Tag`; `NextPatrolPoint` is the runtime-resolved object ref, not editable — paired with a `ScriptedPawn`
whose `Orders=Patrolling` and whose `OrderTag` = the FIRST point's `Tag`; see NPC population in
[`README.md`](README.md) §10.3).

> **[DX] nuance** 🔬: `PatrolPoint` is `Engine.PatrolPoint` — there is **no** `DeusEx.PatrolPoint` (a
> bare-name lookup resolves to the Engine class). `AmbushPoint` **does** exist as a stock `Engine.u`
> NavigationPoint, but DX drives NPCs through `ScriptedPawn` orders rather than the Unreal-AI ambush
> system, so it is effectively unused; `AlarmPoint` does **not** exist in this build at all. Prefer the
> `ScriptedPawn` / `PatrolPoint` workflow over `AmbushPoint` in a DX level.

### 7.1 Spacing  🔬📖

- **300–700 uu** between path nodes on flat ground.
- **≤ 300–350 uu** on ramps / stairs.
- **≥ 50 uu** minimum (closer → "paths too close" build error); keep **≥ 50 uu from corners**.
- **[DX]:** **< 700 uu** general, **< 350 uu** on stairs.

---

## 8. Human-scale anchors (the numbers you build to)  ✅🔬

The load-bearing figures, decoded from the shipped `DeusEx.u` (full table in
[`../README.md`](../README.md) and [`README.md`](README.md) §9):

| Quantity | Value |
|---|---|
| Unit scale | 1 ft = **16 uu**; 1 m ≈ 52.5 uu; world max 65536 uu/axis |
| **Player collision cylinder** [DX] | JC Denton **Radius 20 (40 wide) × Height 47.5 (95 tall)**, Mass 150 |
| **Player eye height** [DX] | `BaseEyeHeight=40` above center → **~87 uu above floor** |
| Jump / speed / step [DX] | `JumpZ=300`, `GroundSpeed=320`, **`MaxStepHeight=25`** |
| Stair rise / run | rise **16**; run 16 steep / **32 good** / 48–64 stately |
| Ceiling / corridor / doorway | ceiling min **~96–100** (the DX player cylinder is 95 tall, so the UT "83" won't clear a DX pawn), rec **128**; corridor min **48**; DX doors **144×72 or 128×64**, 1–8 thick |
| PlayerStart height / PathNode spacing | **40 uu** above floor / **300–700 uu** (≤350 on stairs) |

*Read any other default:* `bin/uedctl actor build <Package.Class> | actor add - | actor prop get - <Prop>`.

---

## 9. Quick verb reference (uedctl)  ✅

| Task | Verb pipeline |
|---|---|
| Place a point actor | `actor build Engine.PlayerStart --at X,Y,Z --rotate 0,16384,0 \| actor add -` |
| Place a decoration | `actor build DeusEx.<Decoration> --at X,Y,Z --prop DrawScale=1.0 \| actor add -` |
| Read a collision default | `actor build DeusEx.JCDentonMale \| actor add - \| actor prop get - CollisionRadius` |
| Set flags on placed actors | `actor find --subclass-of … \| actor prop set - bBlockPlayers=True bProjTarget=True` |
| Discover classes | `class list --subclass-of Engine.NavigationPoint`; `class show <Class>` |

Pathing (`PATHS BUILD`) and NPC population run through the editor / substrate — see
[`../../commands.md`](../../commands.md) and the ScriptedPawn workflow in
[`README.md`](README.md) §10.3.
