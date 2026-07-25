# Native `.dx` materialize — the ULevel body, actor bodies, reachspecs, GUID mint, and end-to-end assembly

**Scope.** This section specifies, byte-for-byte, the "glue" a from-scratch native
`.dx` writer must emit *around* the already-proven pieces (package container, `UModel`
serialize, texture decode, property list). It covers: (1) the `ULevel` object body,
(2) every actor-body kind a map needs, (3) v68/69 header **GUID + generation** minting,
(4) the AI-path (**reachspec**) build — data format *and* algorithm, (5) the end-to-end
object set + assembly order, (6) import/name-table synthesis.

It builds directly on and does not re-derive: the **package container writer** (byte-exact
v61/68/69, `2026-06-27-decontainerize-uedctl/03-native-package-write.md`,
`harness/package_rw.py`), the **`UModel` serializer** (byte-exact 72419/72419 Model exports,
`2026-06-28-umodel-serialize-byte-exact.md`, `bspspike/umodel_serialize.py`), the **property
list** reader/writer (`07-native-actor-bodies.md`, `harness/prop_writer.py` +
`utexture_decode.read_props`), and the **`UPolys`/`FPoly`** format (`10-native-upolys-fpoly.md`).

Confidence markers: ✅ = byte-exact verified against real `.dx` this spike · 🔬 = live-probed /
disassembly-confirmed · 📖 = extracted/inferred, not byte-verified.

Harnesses for this section live in `../harness/`:
`level_roundtrip.py` (the 100/100 byte-exact ULevel-body proof — the keystone),
`dissect_level.py` (field-by-field walk of one map), `guid_generations.py` (GUID/gen mint
analysis), `dissect_assembly.py` (full object-set + import/name dump), plus the disassembly
harnesses `decode_level.py`/`walk_level.py` (ULevel::Serialize, 308-map EOF walk) and
`adis.py`/`dump.py`/`pe.py` (PATHS/reachspec disasm). (The `lightmap_*.py`/`verify_csg_build.py`
files in that dir belong to sibling geometry/lighting work.)

---

## 0. Ground truth: the whole `ULevel` body round-trips byte-exact ✅

`level_roundtrip.py` parses the `Level` export body of **every** retail `.dx` into the
field structure specified below, re-serializes it, and compares to the original serial
extent. **Result: 100/100 maps BYTE-EXACT** (v68 and v69, from 22-actor `DXOnly.dx` to
the 12 514-reachspec `01_NYC_UNATCOIsland.dx`). So the layout in §1 is not inferred — it
reproduces the engine's own bytes exactly. This also closes the prior open caveat
(`unrealed/package-format.md`: "the reachspec record *count* isn't decoded"): the count is
a normal `TArray` compact-index prefix, decoded here.

```
100/100 Level bodies BYTE-EXACT round-trip     (level_roundtrip.py --all)
```

---

## 1. The `ULevel` object body

The `Level` object is exported under the object name **`MyLevel`** (constant across
100/100 maps), class `Engine.Level` (an import), export flags **`0x00070001`**
(`RF_Transactional | RF_NotForClient | RF_NotForServer | RF_TagExp`), **`RF_HasStack`
clear** (a `ULevel` is a `UObject`, not an `AActor` — no `StateFrame`). Its body is:

```
ULevel body =
  <UObject property list>              # UObject::Serialize — normally EMPTY: just the
                                       #   "None" terminator (1 byte, ci = name-index of "None").
                                       #   ULevel has no editable UProperties in retail maps.
  --- ULevelBase::Serialize ---
  INT32   Actors.Num                   # element count of the Actors array (incl. null slots)
  INT32   Actors.Max                   # capacity; retail always == Num
  Actors.Num × ci  ActorRef            # each an object reference (see §"object refs"):
                                       #   >0 export ref, <0 import ref, 0 = null/deleted slot
  FURL    URL                          # see below
  --- ULevel::Serialize (Engine.dll ?Serialize@ULevel@@ RVA 0x16a660) ---
  ci      ModelRef                     # object ref → the level BSP UModel export (ULevel+0x98)
  ci      ReachSpecs.Count             # TArray compact-index count (ULevel+0x8c)
  ReachSpecs.Count × FReachSpec        # 17–21 bytes each, see §4
  --- ULevel trailing (22–23 bytes) — FULLY DECODED ---
  FLOAT   TimeSeconds                  # ULevel+0xdc as (i64 * 2^-32); load-DISCARDED (see below)
  ci      FirstDeleted                 # ULevel+0x100 — always None (0) in every retail map
  16 × ci ObjRef                       # ULevel+0x9c[0..15]: slot[6] = the level UTextBuffer ref,
                                       #   ALL 15 other slots = None (0). This 16-ref array is the
                                       #   whole "trailing zeros" region; slot[6]'s 1-vs-2-byte
                                       #   width is why the tail is 22 or 23 bytes.
  ci      TravelInfo.Count             # TArray<{FString,FString}> (only if FileVersion > 62);
  TravelInfo.Count × (FString, FString)#   retail always 0 (empty). ver 61/62 use a legacy path.
```

**Important encoding notes (all ✅ unless marked):**

- **The Actors array is NOT a standard `TArray`.** A stock UE1 `TArray<T>` serializes its
  count as a *compact index*; the `ULevel.Actors` array (a `TTransArray`) instead writes
  **two raw `INT32`s — `Num` then `Max`** — followed by `Num` elements. Verified: the first
  8 body bytes after the property `None` decode as `Num,Max` (e.g. `602,602` for
  `02_NYC_Bar`), and the element refs then resolve to real actors. Element refs are
  compact-index object references.
- **`ReachSpecs` count is a compact index (standard `TArray`), NOT the raw form.** Confirmed
  two ways: the round-trip encodes it with `write_ci` and is byte-exact, and the disassembly
  (Engine.dll `0x167520`) shows the ci-count `TArray` serializer. Only the `Actors`
  (`TTransArray`) uses the raw `INT32 Num,Max` form — do not confuse the two.
- **Object refs** (`ci`): value `v` encodes `v==0` → null; `v>0` → export index `v-1`
  (0-based); `v<0` → import index `-v-1`. This is the standard UE1 package object-index
  encoding. The `write_ci`/`read_ci` in `package_rw.py` are the exact codec.
- **Actors ordering is load-bearing** (the array is authoritative, not export order):
  - `Actors[0]` = the **`LevelInfo`** singleton — **engine class `LevelInfo`, exactly** (✅
    verified: `Actors[0]` is class `LevelInfo` / object `LevelInfo0` on every real map checked).
    **NOT `DeusExLevelInfo`** — that is a *separate* actor whose `Super` is **`Info`** (✅ read from
    `DeusEx.u`), a metadata holder placed elsewhere in the array, never the singleton. (`LevelInfo`
    need NOT be export 0 — 13/100 maps don't have `LevelInfo` at export 0 (12 a `Light`, 1 a
    `Spotlight` — a `Light` subclass) — only the `Actors[0]` *slot* matters.)
  - `Actors[1]` = the level's **Default Brush** (the "red builder brush"): a `Brush` actor
    whose `Brush=` points to a small `UModel` conventionally object-named `Brush`. ✅
  - Remaining slots: every placed actor, in the editor's actor-list order; **null (0) refs
    are deleted-slot holes and are preserved** (the editor never compacts the array).
- **`Actors.Max == Actors.Num`** for every retail map; emit them equal.

### FURL layout ✅

`FURL` serializes as (verified byte-exact; strings are UE1 `FString`):

```
FURL =
  FString Protocol      # e.g. "deusex"
  FString Host          # "" (empty) for a single-player map
  FString Map           # the *default travel map* (NOT this map's name): conventionally "Index.dx"
                        #   for a .dx target, "Index.unr" for a .unr target — NOT strictly tied to
                        #   file version (a few retail maps mismatch: 1 v68 uses Index.unr, 2 v69 use Index.dx)
  FString Portal        # ""
  ci      OpCount        # TArray<FString> Op — retail always 0
  OpCount × FString Op
  INT32   Port           # 7790 for deusex-protocol maps (7777 for unreal-protocol: 87/100 vs 13/100)
  INT32   Valid          # retail always 1
```

**`FString` (UE1) ✅:** `ci Length` then the string bytes. `Length >= 0` → **ANSI**,
`Length` bytes **including the trailing NUL** (so `"deusex"` → `ci 7` + `deusex\0`).
`Length < 0` → **UTF-16LE**, `(-Length)` *characters* = `-2*Length` bytes including a
wide NUL. `Length == 0` → empty string, no bytes. `enc_fstring`/`read_fstring` in
`level_roundtrip.py` are the codec.

**For a fresh map, emit:** `Protocol="deusex"`, `Host=""`, `Map="Index.dx"` (or `"Index.unr"`
when writing a `.unr`/v69 target), `Portal=""`, `OpCount=0`, `Port=7790`, `Valid=1`. (These are
constants; `Map` is the boot/travel map, not the level being written — the level's own identity
is its package filename + the `MyLevel` object, never the URL.)

### The trailing block — fully decoded ✅🔬

Every field is now identified (disasm `?Serialize@ULevel@@` @ `0x16a660`, cross-checked by
decoding the tail on 100 maps — all consume exactly to serial EOF):

- **`FLOAT TimeSeconds`** (`ULevel+0xdc` serialized as `i64 * 2^-32`). The disassembly shows
  the load path reads this into a local and **never stores it back** — it is *write-only*,
  discarded on load. Emit **`0.0`** for a fresh map (the game sets real time at play start).
- **`ci FirstDeleted`** (`ULevel+0x100`) — a reserved/first-deleted ref, **always `None` (0)**
  in all 100 maps. Emit `0`.
- **`16 × ci` object refs** (`ULevel+0x9c[0..15]`). In every retail map **only slot[6] is
  set — to the level's `UTextBuffer` export** ("MyLevel" script text) — and the other 15 slots
  are `None (0)`. This is the entire "trailing zeros" region; **slot[6]'s ref being a 1-byte
  vs 2-byte compact index is exactly why the tail is 22 vs 23 bytes** (my earlier mystery "V"
  = this TextBuffer ref). If the map has no TextBuffer, emit all 16 as `None`.
- **`ci TravelInfo.Count`** + `Count × (FString key, FString value)` (`ULevel+0xe4`, only when
  `FileVersion > 62`). **Retail always `0`** (empty). Emit `0`.

**For a fresh map, emit:** `FLOAT 0.0`, `ci 0` (FirstDeleted), then 16 `ci`s (`slot[6]` = the
TextBuffer ref if one is emitted, else all `None`), then `ci 0` (TravelInfo). None of this is
load-bearing: `TimeSeconds` is discarded, `FirstDeleted`/TravelInfo are empty, and the
TextBuffer is editor-only script text — a map with all-`None` slots loads and plays.

---

## 2. Actor bodies (all kinds a map needs)

A serial actor body is:

```
actor body = [StateFrame] + <property list> + [class-specific trailing]
```

`StateFrame` present **iff** the export's flags carry `RF_HasStack = 0x02000000` — true for
**every `AActor`** in retail maps (LevelInfo, Brush, Light, NavigationPoint, Mover, …),
false for non-actor helper objects (`UModel`, `UPolys`, `LevelSummary`, `TextBuffer`).

### 2.1 The `StateFrame` prefix — exact bytes ✅

For a resting DeusEx actor the editor writes a **populated** StateFrame (not a cleared one):

```
StateFrame =
  ci   Node          # = the actor's CLASS reference (same value as export.Class; an import ref)
  ci   StateNode     # = the same class reference
  u64  ProbeMask     # = 0xFFFFFFFFFFFFFFFF
  u32  LatentAction  # = 0
  ci   Offset        # PRESENT because Node != 0; value = -1 (0x81) = INDEX_NONE
```

Measured bytes (e.g. `LevelInfo0`, class ref −10): `8a 8a ff ff ff ff ff ff ff ff 00 00
00 00 81` — 15 bytes. `Brush` actors (class ref −9): `89 89 ff…ff 00000000 81`. This closes
Spike-7's deferred question: **emit `Node=StateNode=<class ref>`, `ProbeMask=~0`,
`LatentAction=0`, `Offset=-1`.** (An empty `Node=0` StateFrame — `00 00 <u64 0> <u32 0>`,
no Offset — is the theoretical stackless alternative, but the proven, game-loaded form is
the populated one above; emit it.)

### 2.2 Property-tag encoding (`FPropertyTag`) ✅

Each property, then a terminating `None`:

```
Name  : ci   (name-table index; "None" terminates the list)
Info  : u8   bits0-3 = type, bits4-6 = size code, bit7 = array-flag (= the value, for Bool)
[if type==Struct(10)] StructName : ci
[size extension] size code 0-4 → fixed {1,2,4,12,16}; 5 → u8; 6 → u16; 7 → u32
[if array-flag and not Bool] array index : 1–4 bytes (see reader)
value : <size> bytes   (Bool has NO value bytes — the value is bit7 of Info)
```

Type nibble: `Byte=1, Int=2, Bool=3, Float=4, Object=5, Name=6, Str=13(0x0D), Struct=10`.
Encoders in `prop_writer.py` (round-trips Byte/Int/Bool/Float/Name/Object/Struct). Value
encodings: `Int`=`<i` 4B; `Float`=`<f` 4B; `Byte`=1B; `Bool`=none; `Object`/`Name`=`ci`
(object ref / name index) written as the value bytes; `Struct`=raw struct bytes;
`Str`=an embedded `FString` (`ci len`+bytes). The writer picks any valid size code (the
loader accepts canonical encodings; byte-match with the editor is not required).

**Common struct value layouts** (raw bytes of the `Struct` value) ✅ measured:
- `Vector` (12 B): `f32 X, f32 Y, f32 Z`.
- `Rotator` (12 B): `i32 Pitch, i32 Yaw, i32 Roll`.
- `Scale` (14 B): `Vector(12) Scale` + `f32 SheerRate` + `u8 SheerAxis`.
  (`MainScale`/`PostScale` = `1,1,1 / 0 / 5` → `0000803f 0000803f 0000803f 00000000 05`.)
- `PointRegion` (6 B): `ci Zone(actor ref)` + `i32 iLeaf` + `u8 ZoneNumber`, e.g.
  `01 00000000 01` or `01 ffffffff 00`. **`Region` is recomputed by the game** on
  `setLocation` at load — emit a placeholder (`Zone=0, iLeaf=-1, ZoneNumber=0`) and the
  engine fixes it. ✅
- `Color` (4 B): `u8 R,G,B,A`.

### 2.3 The specific actor kinds

**LevelInfo (the `Actors[0]` singleton).** Props (retail `LevelInfo0`): `TimeSeconds`
(Float), `Summary` (Object → the `LevelSummary` export), `Song` (Object → a `Music`
import, optional), `SongSection` (Byte), `AIProfile` (Int), `bFogZone` (Bool),
`DistanceFromPlayer` (Float — recomputed), `Level` (Object → **itself**), `Tag` (Name),
`Region` (Struct PointRegion — recomputed). DeusEx maps ALSO place a **separate**
**`DeusExLevelInfo`** actor (class `DeusExLevelInfo`, `Super`=`Info` — a metadata holder, **not** a
`LevelInfo` and **not** the `Actors[0]` singleton) carrying `MapName`/`MapAuthor`/`MissionLocation`/
`missionNumber` (Str/Str/Str/Int) + `Location`/`OldLocation`; it sits elsewhere in the actor array.
**Minimal requirement: `Actors[0]` is exactly one engine-class `LevelInfo` actor whose `Level` points
to itself** (the `DeusExLevelInfo` metadata actor is optional and independent).

**Brush actors.** Two roles, identical body shape (both `RF_HasStack`, class `Engine.Brush`):
- *Default (builder) Brush* = `Actors[1]`: props `MainScale`, `PostScale`,
  `DistanceFromPlayer`, `Level`(→LevelInfo), `Tag`(="Brush"), `Region`, `Location`(Vector),
  `Brush`(Object → its own `UModel` shape, conventionally named `Brush`). **No `CsgOper`.**
- *CSG Brush* (each world-geometry brush): the same, **plus `CsgOper`** (Byte: `1`=Add,
  `2`=Subtract) and, when non-default, `PolyFlags` (Int) and `Location`/`Rotation`. Its
  `Brush=` points to that brush's own `UModel` (shape), which in turn has a `Polys`
  (`UPolys`) child. The `Brush` object property carries the **authored** shape; the *world*
  BSP is the separate level `UModel` in the `ULevel.ModelRef` (built by CSG, §5).

**Light actors.** `RF_HasStack`, class `Engine.Light`. Point-actor body = StateFrame +
property list, no trailing. Typical props: `Location`, `LightBrightness`(Byte),
`LightRadius`(Byte), `LightHue`(Byte), `LightSaturation`(Byte), `LightType`/`LightEffect`
(Byte enums), `Tag`, `Region`, `Level`. Lights are **inputs to the lightmap bake**, not
themselves geometry; the baked lightmap lives in the level `UModel`.

**Mover / point actors** (`Mover`/`DeusExMover`, `AmbientSound`, decorations, `Camera`,
`PlayerStart`, …). All are point actors: StateFrame + property list, **no class-specific
trailing**. A `Mover` carries keyframe props (`KeyPos[]`/`KeyRot[]` static arrays,
`Brush`=its mesh/brush ref, `MoverEncroachType`, …) but still serializes purely as tagged
properties (static-array elements use the array-index byte in the tag). A `PlayerStart` is
a bare NavigationPoint-family point actor.

**NavigationPoint / PathNode actors.** `RF_HasStack`, class e.g. `Engine.PathNode`,
`Engine.PlayerStart`, `DeusEx.PatrolPoint`. Body = StateFrame + property list. The
path-graph fields they carry **on disk** (see §4) are tagged properties like any other:
`Location`, `Tag`, plus (only if the map was path-built) the recomputed nav fields. For a
fresh map you may write nav actors with **no** path fields and run the path build (§4)
to fill them, or ship them path-less (map still loads and is human-playable).

**Non-actor helper objects (no StateFrame):**
- `UModel` (brush shape *and* the level BSP): body = property `None` + the `UModel` serial
  data (`bspspike/umodel_serialize.py`, byte-exact). The 42-byte "UPrimitive prefix"
  already **includes** the leading property-`None` byte.
- `UPolys`: body = property `None` + `INT Num` + `INT Max` + `Num × FPoly`
  (`10-native-upolys-fpoly.md`).
- `LevelSummary` (class `Engine.LevelSummary`, `RF_Public`): body = property list only —
  just `Title` (Str). The engine's map browser reads it; small (≈14 B). Referenced by
  `LevelInfo.Summary`. **Conventional (all 100 retail maps have one) but NOT load-critical:**
  `native/assemble` MAY synthesize one + set `LevelInfo.Summary`→it, or omit both (leave
  `LevelInfo.Summary` = `None`) — the map still loads. It is NOT part of the mandatory
  `Actors[0]`/`Actors[1]` synthesis invariant.
- `TextBuffer` (class `Core.TextBuffer`): body = property `None` + `INT32 Pos` + `INT32 Top`
  + `FString Text`. Retail maps store the **editor camera state** here; it is **not
  game-load-critical** and can be omitted or emitted empty.

---

## 3. GUID + generation minting ✅

The v68/69 header tail (after the 36 fixed bytes) is:

```
FGuid  (16 bytes)
u32    GenerationCount
GenerationCount × (u32 ExportCount, u32 NameCount)     # FGenerationInfo
```

Measured across **100/100** retail maps (`guid_generations.py --all`):

- **`GenerationCount == 1` for every map.** A map is written with a *single* generation.
  (Multi-generation tables occur for code packages saved repeatedly; a from-scratch map
  emits exactly one.)
- **`generation[0] == (final ExportCount, final NameCount)`** — always, 100/100. So the one
  generation record is simply the package's own final export and name counts.
- **`PackageFlags == 0x00000001`** (`PKG_AllowDownload`) and **`LicenseeVersion == 0`** for
  every map. `FileVersion` = 68 (or 69 — the on-disk shape is identical; write 68 for
  Deus Ex).
- **The FGuid is unconstrained.** It occurs **exactly once** in the file (`guid_occ==1`) —
  nothing else references it (imports resolve other packages **by name**, never by GUID).
  Retail v68 GUIDs share a Windows-v1 node suffix (they were `appCreateGuid`-minted on one
  machine); v69 maps (`02_NYC_Smug`, `Test_Castle`, …) have fully random GUIDs. **Any random
  16 bytes is valid.**

**Mint rule:** `FGuid = os.urandom(16)`; `GenerationCount = 1`; `generation[0] =
(len(exports), len(names))`; `PackageFlags = 1`; `LicenseeVersion = 0`; `FileVersion = 68`.
The generation record is written **after** the export/name tables are finalized (their
counts are known), i.e. as part of the header back-patch already performed by the container
writer.

---

## 4. AI paths / reachspecs (`PATHS DEFINE`) — build output

Reachspecs are **build output**, like lighting: regenerable, never authored, never in the
level hash. A map with an **empty** ReachSpecs array (count 0) and nav actors carrying no
path fields **still loads and is fully playable by a human** — only monster/NPC AI
navigation is absent. (Ground truth: `DXOnly.dx`, `Entry.dx`, `Test_Castle.dx` ship with
`ReachSpecs.Count == 0` and load/play. ✅) So a first native materialize MAY emit
`ReachSpecs.Count = 0` and skip the build entirely; the algorithm below is what a full
native path build must do.

### 4.1 `FReachSpec` on-disk record ✅

Inside the `ULevel.ReachSpecs` `TArray` (ci count), each element:

```
FReachSpec =
  INT32 Distance          # path cost (see 4.4)
  ci    Start             # object ref → the source NavigationPoint actor
  ci    End               # object ref → the destination NavigationPoint actor
  INT32 CollisionRadius   # radius of the largest pawn that fits this edge
  INT32 CollisionHeight   # height of same
  INT32 reachFlags        # bitmask (see 4.3)
  u8    bPruned           # 1 = redundant edge kept but excluded from routing
```

This is **variable length** (17–21 bytes: the two `ci` refs are 1–3 bytes each), *not* a
fixed 21 as an earlier note assumed. Decoded byte-exact for all 100 maps in the round-trip.
Directed edges: `Start→End` is one-way; a two-way connection is two records. `Start`/`End`
are export refs to NavigationPoint actors.

### 4.2 The build entry point — it is `PATHS BUILD`, not `PATHS DEFINE` 🔬

**Correction to `t3d.md`/`commands.md`:** the reachspec graph is built by **`PATHS BUILD`**
(`UEditorEngine::Exec` @ Editor.dll `0x10064f11` → `FPathBuilder::buildPaths(ULevel*, INT opt)`
@ Engine.dll `0x177770`). `PATHS DEFINE` (`FPathBuilder::definePaths` `0x178c10`) **only spawns
auto-marker NavigationPoints** (an `InventorySpot` under every `Inventory`, a `WarpZoneMarker`
under every `WarpZoneInfo`) and touches **no** ReachSpecs. `opt`: `LOWOPT`→0, default→1,
`HIGHOPT`→2. `buildPaths` pipeline: strip stale auto-PathNodes → `undefinePaths` → `definePaths`
(place markers) → `getScout` → set scout params → **`createPaths(opt)`** (builds all reachspecs)
→ destroy scout → refresh markers → log `"Built Paths: %d"`.

### 4.3 ReachFlags bit constants 🔬

| Flag | Value | Evidence |
|---|---|---|
| `R_WALK` | **1** | ✅ `walkReachable` `0x10184718 or [flags],1` |
| `R_FLY` | **2** | ✅ `flyReachable` `0x101822f6 or [flags],2` |
| `R_SWIM` | **4** | ✅ `swimReachable` `0x10183ccb or [flags],4` |
| `R_JUMP` | **8** | ✅ `jumpReachable` `0x10182c88 or esi,8` |
| `R_DOOR` | 16 | 📖 inferred (standard UE1 enum; the free bit for Mover/door edges) |
| `R_SPECIAL` | **32** | ✅ `addReachSpecs` writes `reachFlags=0x20` for Lift/Teleporter/WarpZone edges |
| `R_PLAYERONLY` | 64 | 📖 inferred (standard UE1 enum) |

Membership test `FReachSpec::supports(r,h,flags)` (`0x11aa40`): an edge serves a query pawn iff
`spec.CollisionRadius >= r && spec.CollisionHeight >= h && (spec.reachFlags & flags) == flags`
(the spec's flags must be a superset of the query's).

### 4.4 The reachability test + constants 🔬

**Scout (test pawn).** The master graph is built with a scout sized `SetCollisionSize(Radius=52.0,
Height=40.0)` (`createPaths` `0x10177a4f`). For each candidate edge, `findBestReachable`
(`0x193dd0`, used by `FReachSpec::defineFor`) **sweeps the scout size** from `(18.0, 39.0)` upward
(max radius **70.0**) to record the **largest pawn that can still traverse the edge** — that
radius/height is what gets stored in `CollisionRadius`/`CollisionHeight`. (`BotOnlyPath`: radius
< 24 ⇒ bot-only; auto-marker/PathNode default height 48.0.)

**Candidate pairing.** `createPaths` only attempts a connection between two NavigationPoints whose
**squared straight-line distance** is within `16384` (=128²) for the near pass and up to `640000`
(=800²) for the extended `TestReach` pass — effective max node spacing ≈ 800 uu.

**The trace.** `APawn::Reachable(Dest)` (`0x17d8f0`) dispatches on the scout's `Physics`:
- `walkReachable` (`0x1846e0`): step the scout collision **cylinder** from Start toward End in
  segments of **`MAXTESTMOVESIZE = 128.0`** (base step 16.0), applying gravity/step-up/max-fall
  (slope-parabola constant `0.8`), ≤ ~100 iterations; success ⇒ set `R_WALK`.
- `flyReachable`/`swimReachable`/`jumpReachable` (`0x1822c0`/`0x183c90`/`0x182c50`): set
  `R_FLY`/`R_SWIM`/`R_JUMP`; jump uses a max jump height ≈ 48.0 and defers the landing to
  `walkReachable`.

**Distance** = straight-line Euclidean `(End.Location - Start.Location).Size()`, stored as `INT`
in `FReachSpec.Distance`. (The trace decides *whether* the edge exists; it does not set Distance
to path length.) Multi-hop composition `FReachSpec::operator+` (`0x193a20`):
`Distance = a+b`, `Radius = min`, `Height = min`, `flags = a|b`.

**Special edges** (`addReachSpecs` `0x1770a0`): `LiftCenter→LiftExit` is a hardcoded edge
`Distance=500, Radius=60, Height=60, flags=R_SPECIAL`; Teleporter/WarpZone edges also carry
`R_SPECIAL`.

### 4.5 Attachment, pruning, and what is on-disk vs recomputed 🔬

**In-memory `FReachSpec` = 28 bytes** (`+0` Distance, `+4` Start`AActor*`, `+8` End`AActor*`,
`+0xc` CollisionRadius, `+0x10` CollisionHeight, `+0x14` reachFlags, `+0x18` bPruned) — exactly
the 21-byte on-disk record with Start/End as compact-index refs and bPruned as a byte. The array
lives at `ULevel+0x8c`.

**Per-NavigationPoint index arrays** (each `16 × INT`, `-1` = empty slot):
- `upstreamPaths[16]` (`NavPt+0x214`) — indices of incoming edges,
- `Paths[16]`/`PathList` (`NavPt+0x254`) — indices of outgoing edges,
- `prunedPaths[16]` (`NavPt+0x294`) — indices of pruned edges.

**Pruning** (`FPathBuilder::Prune` `0x176790`): for each node `N`, for every incoming `A→N` and
outgoing `N→B`, if a **direct** edge `A→B` exists and the two-hop route is nearly as good, mark
the direct edge redundant:

> prune `A→B` iff `combined(A→N→B).Distance ≤ 1.2 × direct(A→B).Distance` **and** the direct edge
> adds no reachability the combined route lacks.

On prune: set `ReachSpecs[i].bPruned = 1`; remove `i` from `A.Paths[]` and `B.upstreamPaths[]`
(shift-compact with `-1` fill); append `i` to `A.prunedPaths[]`. **Pruned specs stay in the
array** (kept as the AI's expensive-path fallback) but are excluded from the primary `Paths[]`
walk.

**On-disk (must be written into the `.dx`):**
- the `ULevel.ReachSpecs` array (§4.1) — the edge records;
- each NavigationPoint's serialized `Paths[16]`/`upstreamPaths[16]`/`prunedPaths[16]` (indices
  into ReachSpecs) + authored `bEndPoint`/`bSpecialCost`/`ExtraCost`/`bAutoBuilt`, as tagged
  properties (the 16-int arrays are **static-array** property tags — one tag per element carrying
  its array index; validate this encoding against a real NavigationPoint at write bring-up).

**Recomputed at load / per-search (do NOT put on disk):** `nextNavigationPoint` and the
`LevelInfo.NavigationPointList` linked list (rebuilt at `BeginPlay`), and per-search scratch
`visitedWeight`/`bestPathWeight`/`startPath`/`bestPathTo`.

**Empty-paths verdict ✅:** ULevel load does **no** path validation or rebuild — reachspecs are
consumed lazily only by AI (`findPathToward`/`Reachable`). With `ReachSpecs.Count = 0` and every
NavigationPoint's `Paths[]` all `-1`, **the human player plays normally**; AI just can't route
(falls back to direct movement/idle). A first native materialize MAY ship zero reachspecs and add
the graph later — it is an AI enhancement, not a load requirement.

### 4.6 Porting the build (algorithm summary)

To reproduce natively (all against the **built level BSP** — necessarily downstream of the CSG/BSP
build): (1) gather all NavigationPoint actors + their Locations/radii; (2) for each ordered pair
within √640000 ≈ 800 uu, run the cylinder-trace reachability (walk, then fly/swim/jump as the
zone allows) with `findBestReachable`'s size sweep to get `(CollisionRadius, CollisionHeight,
reachFlags)`, `Distance` = straight-line; emit one directed `FReachSpec` per successful direction;
(3) fill each node's `Paths[]`/`upstreamPaths[]`; (4) run the 1.2× `Prune` pass, setting `bPruned`
and moving indices to `prunedPaths[]`; (5) write the ReachSpecs array into the ULevel body and the
per-node index arrays as NavigationPoint tagged properties.

---

## 5. End-to-end assembly

### 5.1 The minimal object set (grounded on `DXOnly.dx`, 25 exports) ✅

A minimal materialized `.dx` contains these **exports** (order flexible — see below):

| Object | Class | Notes |
|---|---|---|
| `LevelInfo0` | `LevelInfo` (engine class, exactly) | the `Actors[0]` singleton; `Level`→self. NOT `DeusExLevelInfo` |
| (`DeusExLevelInfo0`) | `DeusExLevelInfo` (`Super`=`Info`) | a **separate** DeusEx map-info actor (MapName/Author), elsewhere in the array — optional but conventional |
| `Brush0` (Default Brush) | `Brush` | `Actors[1]`; `Brush`→a small `UModel` named `Brush` |
| `Brush` | `Model` | the Default Brush's shape (builder cube) |
| one `Brush<N>` per CSG brush | `Brush` | `CsgOper` + `Brush`→its shape `UModel` |
| one `Model<N>` per CSG brush | `Model` | that brush's authored shape; child `Polys` |
| one `Polys<N>` per brush model | `Polys` | authored `FPoly` list |
| **the level BSP** `Model<N>` | `Model` | the built world geometry (largest Model); `ULevel.ModelRef` |
| `PlayerStart0` | `PlayerStart` | spawn point (required for the game to spawn the player) |
| Lights, Movers, decorations, Cameras, PathNodes… | various | placed actors |
| (`LevelSummary`) | `LevelSummary` | `RF_Public`; `LevelInfo.Summary`→this — conventional (all retail maps) but omittable (`Summary`=`None` loads) |
| (`TextBuffer0`) | `TextBuffer` | editor camera state — omittable |
| **`MyLevel`** | `Level` | the `ULevel`; last (or near-last) export |

**Export order is NOT load-bearing** — the engine resolves every reference by index and
finds the `ULevel` by class, not position (88/100 maps put `MyLevel` last; the rest within a
few of the end; 13/100 don't even have LevelInfo at export 0). The **`Actors` array order**
inside the ULevel body is the only ordering that matters (§1). Recommendation: emit actors
and helpers in any stable order, then `MyLevel` last.

### 5.2 Assembly algorithm

Reusing the proven container writer (`package_rw.write_full` layout: **header → names →
object bodies → imports → exports@EOF**):

```
1.  Build the in-memory object graph: LevelInfo, Default Brush + its Model, each CSG brush
    + its Model + Polys, the built level UModel (from the CSG/BSP build — §note), lights,
    nav points, movers, decorations, PlayerStart, LevelSummary, and the ULevel.
2.  SYNTHESIZE THE NAME TABLE (§6): collect every string referenced by any body (class
    names, package names, every actor/object name, every property name, struct names,
    "None", the URL strings, FPoly ItemNames, Str property contents that are names…),
    dedup, assign each an index. Name order is arbitrary.
3.  SYNTHESIZE THE IMPORT TABLE (§6): one entry per external package, class, and content
    object (textures/sounds/music) any body references; dedup; assign each a negative ref.
4.  Serialize each object BODY to bytes using the proven writers:
      - actors   → StateFrame(§2.1) + prop list(§2.2)
      - UModel   → umodel_serialize (brush shapes AND the level BSP)
      - UPolys   → None + Num/Max + FPoly list
      - LevelSummary/TextBuffer → prop list (+ TextBuffer trailing)
      - ULevel   → §1 (Actors Num/Max/refs, FURL, ModelRef, ReachSpecs, trailing)
    Record each body's length; its SerialOffset is assigned in step 6.
5.  Build the EXPORT TABLE entries: (Class ref, Super=0, Outer=0 (pkg root), Name idx,
    Flags, SerialSize) — SerialOffset filled in step 6. Flags per kind (actors
    0x00070001-ish with RF_HasStack 0x02000000 set; ULevel 0x00070001; Model/Polys clear
    RF_HasStack; LevelSummary RF_Public 0x00000004).
6.  LAY OUT THE FILE (container writer): emit header (offsets back-patched), then the name
    table, then each object body in export order — recording each body's start as that
    export's SerialOffset — then the import table, then the export table; back-patch
    NameOffset/ImportOffset/ExportOffset and the header counts; write the GUID + the single
    generation record = (ExportCount, NameCount) (§3).
```

**Offset recomputation on relocation.** Bodies are laid out contiguously at fresh offsets,
so any body that embeds an **internal absolute file offset** must have it patched:
- `UModel` bodies: **none** — all indices, no absolute offsets (`2026-06-28` spike, note 2).
  Safe to place anywhere. ✅
- Texture (`FMipmap` WidthOffset/skip), mesh/`TLazyArray`, sound/music `TLazyArray`: **carry
  absolute skip-offsets** and MUST be patched to the final position if such a body is
  *embedded* in the map. A minimal generated map **imports** all textures/sounds/meshes and
  embeds none, so in practice **no body needs offset patching**. If a future map embeds a
  `MyLevel`-package texture, patch its `FMipmap` skip to `bodyStart + (skipField - origBodyStart)`.
- `UPolys`, actor bodies, `LevelSummary`, `TextBuffer`, `ULevel`: no internal absolute
  offsets — relocate freely. ✅

The container writer already recomputes the export-table `SerialOffset`/`SerialSize` and the
name/import/export table offsets (proven byte-exact and in the resized-body `native_edit.py`
path).

---

> **Ordering is "arbitrary" for LOADING only — NOT for editor byte-parity.** Everything below
> notes name/import/export order is arbitrary because refs are by index; that is true for the
> *game*. It does **not** make a from-scratch package byte-identical to an UnrealEd save: the
> editor's name-table order (global FName-pool order), object numbering (`Polys<N>`, `Camera<N>`),
> and editor-only actors (viewport `Camera`s, `LevelSummary`) are session-global state absent
> from the trunk, so full wrapper byte-parity is impossible — see
> [`31-package-wrapper-parity.md`](31-package-wrapper-parity.md). Per-class **export flags** ARE
> content-derivable and now match the editor (brush actors `0x02340001`, CSG brush Polys
> `0x00070000`).

## 6. Import / name table synthesis ✅

**Import entry** = `(ci ClassPackage, ci ClassName, INT32 PackageIndex, ci ObjectName)`.
Three entry shapes (all observed in `DXOnly.dx`):

- **A package import** (e.g. `Engine`, `DeusEx`, `Core`, `DeusExItems`, `DeusExDeco`, a
  content sub-package like `Skins`, a music package): `ClassPackage="Core"`,
  `ClassName="Package"`, `PackageIndex=0` for a root package or the import ref of its parent
  package (e.g. `Skins` outer = `DeusExItems`), `ObjectName=<package name>`.
- **A class import** (e.g. `Brush`, `Light`, `Model`, `Polys`, `LevelInfo`, `Level`,
  `PlayerStart`, `LevelSummary`, `Camera`, `DeusExLevelInfo`, `DXText`): `ClassPackage="Core"`,
  `ClassName="Class"`, `PackageIndex=<import ref of the defining package>` (Engine for
  engine classes, DeusEx for DeusEx classes, Core for `TextBuffer`), `ObjectName=<class name>`.
- **A content-object import** (a texture/sound/music the map references): `ClassPackage=<its
  package, e.g. "Engine">`, `ClassName=<"Texture"/"Music"/"Sound">`, `PackageIndex=<import
  ref of its sub-package, e.g. Skins>`, `ObjectName=<object name>`.

**Synthesis procedure:**
1. Walk every object body; collect each external reference: the class of every export, the
   defining package of each such class, every texture/sound/music/mesh object referenced by a
   property or an `FPoly.Texture`, and the sub-package + root package of each.
2. Emit package imports first-needed (root packages with `PackageIndex=0`; sub-packages with
   `PackageIndex` = their parent's import ref — so parent must precede child, or two-pass:
   allocate refs then fill `PackageIndex`).
3. Emit a class import for each distinct class (`Core.Class`, `PackageIndex`=its package import).
4. Emit content-object imports (`Package.<Kind>`, `PackageIndex`=its sub-package import).
5. **Dedup** by `(ClassPackage, ClassName, PackageIndex, ObjectName)`; each unique tuple once.
   Import **order is arbitrary** (refs are by index) as long as every `PackageIndex` points at
   an already-defined import (satisfy by allocating all refs, then writing `PackageIndex`).

**Name table** = each entry `ci Length + bytes(incl NUL) + u32 Flags` (v≥64). Collect **every
string** any table or body references — class names, package names, all object/actor names,
all property names, struct names (`Vector`/`Rotator`/`Scale`/`Color`/`PointRegion`), the
literal `"None"`, `Protocol`/`Map` URL strings, `FPoly` ItemNames, and any `Name`-typed
property value — **dedup**, assign indices. **Name order is arbitrary** (everything refers by
index; there is no reserved slot — `"None"` may sit anywhere). Name `Flags` is a per-name
`u32` (retail uses the object flags of the name's "referencing" object; `0` is accepted — the
loader ignores name flags for map loading). The container writer's `enc_names` is the codec.

---

## Appendix: Engine.dll / Editor.dll RVAs (image base 0x10000000) 🔬

| RVA | Symbol / role |
|---|---|
| `0x16a660` | `?Serialize@ULevel@@` — Model ref, ReachSpecs, trailing |
| `0x16a8c0` | `?Serialize@ULevelBase@@` — Actors array + URL |
| `0x1afef0` | `operator<<(FArchive&, FURL&)` |
| `0x167520` | ReachSpecs `TArray<FReachSpec>` serializer (ci count) |
| `0x167960` | `FReachSpec` element serializer |
| `0x53...`(core) | `operator<<(FArchive&, FString&)` |
| `[0x101f90ac]` | `FCompactIndex` codec (TArray counts) |
| `[Ar+0x18]` vtable slot 6 | `operator<<(UObject*&)` — object-ref-as-compact-index |
| `0x064f11`(Editor) | `UEditorEngine::Exec` PATHS dispatch |
| `0x177770` | `FPathBuilder::buildPaths` (the reachspec build; PATHS BUILD) |
| `0x178c10` | `FPathBuilder::definePaths` (markers only; PATHS DEFINE) |
| `0x176790` | `FPathBuilder::Prune` (bPruned, 1.2× criterion) |
| `0x193dd0` | `findBestReachable` (scout size sweep 18/39→70) |
| `0x1846e0` | `walkReachable` (cylinder trace, MAXTESTMOVESIZE=128) |
| `0x11aa40` | `FReachSpec::supports` (radius/height/flags membership) |

## Residual unknowns + how to close them

1. **The ULevel trailing block — CLOSED.** ✅🔬 Fully decoded (FLOAT TimeSeconds [load-discarded]
   + `ci` FirstDeleted[=0] + 16 `ci` refs with slot[6]=TextBuffer + `ci` TravelInfo[=0]); tail
   consumes to EOF on all 100 maps and none of it is load-bearing for a fresh map.
2. **`R_DOOR=16` / `R_PLAYERONLY=64`** are the only reachflag bits still 📖 inferred (5 of 7 are
   binary-confirmed). Close by disassembling the Mover/door edge path in `addReachSpecs`
   (`0x1770a0`+) or live-probing `describeSpec` (`0x171fe0`) on a door. Not needed to ship
   walk/fly/swim/jump/special paths or an empty set.
3. **The NavigationPoint 16-int static-array property encoding** (`Paths`/`upstreamPaths`/
   `prunedPaths` as `FPropertyTag`s) is not yet byte-verified — validate against a real DeusEx
   `.dx` NavigationPoint during native-write bring-up. (The ReachSpecs array format itself is
   ✅ byte-exact.)
4. **Game-load acceptance of a fully native-written `.dx`** (not editor-`MAP SAVE`d). Every
   body/layout here is byte-exact against retail files, so a native writer that reproduces them
   is loadable by construction; the one untested composite is a *from-scratch* file with a
   *natively built* level `UModel` (the CSG/BSP build, out of this section's scope). Close with
   a game-load smoke test once the BSP build (D2) emits a level Model.
```
