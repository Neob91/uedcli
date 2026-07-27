# UnrealEngine-1 package format — and why v68/v69 is a red herring

This doc answers one recurring question: **is a Deus Ex package (`.u`/`.dx`/`.utx`)
different from a stock Unreal/Unreal Tournament package, and is the v68-vs-v69 version
number a compatibility gate?**

**Short answer: the format is the same; the version number is a red herring.** A Deus Ex
package and an Unreal/UT package are the same UnrealEngine-1 binary format. The reason a
Deus Ex *code* package won't load into the UT-lineage UED22 editor is **class-graph
divergence** (a DeusEx-flavored `Engine`/`Core`) plus a **mesh-format difference** — not
the version field.

> **Confidence:** ✅ = byte-level offline verification against the real install + the
> editor substrate · 🔬 = live-probed.
>
> Evidence: [`../spikes/2026-06-28-deusex-vs-unreal-package-format/`](../spikes/2026-06-28-deusex-vs-unreal-package-format/)
> (harness `verify.py`). The parser is `uedcli/dxpkg.py`.

---

## The format is identical ✅

Every UnrealEngine-1 package — code (`.u`), map (`.dx`/`.unr`), texture (`.utx`), sound
(`.uax`), music (`.umx`) — begins with the same `FPackageFileSummary`:

```
uint32 Tag          = 0x9E2A83C1   # same magic for ALL versions; there is no "Deus Ex magic"
uint16 FileVersion                 # 61 / 68 / 69 — the number this doc is about
uint16 LicenseeVersion
uint32 PackageFlags
uint32 NameCount,  NameOffset
uint32 ExportCount, ExportOffset
uint32 ImportCount, ImportOffset
... (GUID + generations for version >= 68)
```

`uedcli/dxpkg.py` reads the magic, version, name table, and import table for **versions
61, 68, and 69** — and **68 and 69 share the exact same code path** (`ver>=64`:
compact-index length + string + 4-byte flags). Only **version 61** (five old content
packages: `CoreTexDetail`/`CoreTexWater`/`Palettes`/`Render`/`TITAN`) uses a different
name-table encoding (null-terminated string, no length prefix). So:

- **61 → 68** is a real name-table format change.
- **68 → 69** is a minor bump that changes **nothing** in the header / name table / import
  table that uedcli parses.

Verified directly: the v68 `DeusEx.u` (11293 names, 3151 imports) and the v69 `DeusEx.u`
(7017 names, 1952 imports) both parse through the identical `ver>=64` reader.

---

## The decisive fact: the v69 editor ships and loads v68 packages ✅

The committed UED22 substrate — the **UT-lineage v69 editor's own code** — contains
**7 version-68 packages** alongside 25 version-69 ones (`ConSys.u` in `uned/UED22/` is
itself version 68):

```
UED22 (UT-lineage v69 editor substrate):  version 68: 7   version 69: 25
Deus Ex install (real game):              version 68: 17
```

A "v69 tooling can't load v68" rule is false by the editor's own substrate. Independently,
UED22's v469 UCC was forced to a genuine `Ver: 68` load (by hiding the v69 copy) and
decompiled v68 classes + textures fine (🔬 `decisions.md` 2026-06-22).

---

## The real load blocker: class-graph divergence, not version

Every package's import table names the packages its objects come from. `DeusEx.u`'s
imports name `Core` and `Engine` — the classes it inherits from and the natives it calls.
Those references resolve **by name** against whatever `Engine.u`/`Core.u` the editor has
loaded. Deus Ex ships its own `Engine`/`Core` whose class members and native function
signatures differ from Unreal Tournament's. Load a Deus Ex code package into the UT-lineage
editor and its references hit **UT's** `Engine`/`Core`, where the expected symbol is absent
or different → link failure. The version byte is irrelevant to this.

Two contributing facts (both already grounded in earlier spikes):

- **Engine/Core divergence** — the v469 UCC can't link decompiled Deus Ex function bodies
  against UT's DLLs; this is why the "stubbing" pipeline strips every function/state body.
- **Mesh format** — Deus Ex `FMeshVert` is 8-byte int16; stock Unreal expects 4-byte
  packed (`spikes/2026-06-27-decontainerize-uedcli/02-native-mesh-format.md`).

Both are content/class-graph problems. **Neither is a package-version problem.** (The whole
stubbing subsystem exists to bridge these for the editor; a native read/write path deletes
it — there was never a version "conversion" to do. See `decisions.md` 2026-06-27 and the
`architecture.md` "Package stubbing" section.)

---

## The asymmetry: code packages vs map packages

The version is a red herring for both, but the artifacts behave differently:

| Artifact | Loads into UT-lineage UED22? | Loads into the v68 Deus Ex game? | Why |
|---|---|---|---|
| **Code** (`DeusEx.u`, `DeusExItems.u`) | No — Engine/Core class-graph + mesh format | Yes (it's the game's own) | code re-links the engine class graph |
| **Map** (`.dx`) | Yes (authored there) | **Yes — a v69 UED22-authored `.dx` loads in the v68 game** | a map carries geometry + actors-by-name, no engine re-link |

The one time a UED22-authored `.dx` failed to load in the game, the cause was missing
CSG/BSP (a brush imported via `MAP IMPORTADD`, which skips CSG, left the world solid → the
player "encroaches everywhere" → `SpawnActor` returns None → `Failed to spawn player
actor`). Rebuilding through the `EDIT PASTE` path produced 68 BSP nodes and it loaded,
spawned, and rendered in-game first try (🔬 verified 2026-06-28, `quirks.md` "How brushes
enter the level"). The version gap had nothing to do with it.

---

## Object body layouts (byte-exact) 🔬

Native readers decode object bodies straight from the package with no editor. Two representative
layouts, verified against real Deus Ex files:

### `FReachSpec` — the on-disk navigation-edge record (21 bytes) 🔬

The `ULevel` export stores its navigation graph as an array of fixed-shape `FReachSpec` records —
the directed pathnode→pathnode edges the editor builds with `PATHS DEFINE`. Each record is **21 bytes**:

```
FReachSpec (21 B):
  INT  Distance          (4 B)
  ci   Start             (FCompactIndex export ref → NavigationPoint actor)
  ci   End               (FCompactIndex export ref → NavigationPoint actor)
  INT  CollisionRadius   (4 B)
  INT  CollisionHeight   (4 B)
  INT  reachFlags        (4 B; R_WALK=1 confirmed, DeusEx door/jump flags unconfirmed)
  BYTE bPruned           (1 B)
```

`Start`/`End` are export refs to `NavigationPoint` actors (directed, one-way edges); the array lives
in the `ULevel` body after the actor-ref list and an `FURL`. Read natively from real `.dx`, BFS from
`PlayerStart` correctly surfaced unreachable nav regions across 4 maps with no editor/game. Caveats:
the record *count* isn't decoded (found as the longest self-validating run) and the exact header
before the records is undecoded — validate the count against the editor's `PATHS` for production.
(spike: `../spikes/2026-06-27-uedcli-direction-ideas/02-level-nav-reachability.md`, native read 2026-06-27)

### `UMusic` / `USound` — audio object body 🔬

The body of a `UMusic` (`.umx`) or `USound` (`.uax`) object is, in order: **tagged properties**
(terminated by the `None` name) → a **format `FName`** (`it`/`s3m`/`xm`/`mod`/`wav`, = the asset's
extension) → a **`TLazyArray` blob** that *is* the raw asset file byte-for-byte. On v68/69 the
`TLazyArray` header is `i32 skip` + `ci count` + `count` bytes (the same lazy-array primitive textures
and meshes use). There is **no re-encoding** — extraction is a straight copy. Verified by extracting
`Training_Music` (`format=it`, 1,449,937 B) from `Area51Bunker_Music.umx` to a valid, playable Impulse
Tracker `.it`; `USound` parses identically (66 `wav` objects with correct sizes from `MoverSFX.uax`).
(spike: `../spikes/2026-06-27-uedcli-direction-ideas/15-native-audio.md`, native read 2026-06-27)

### `RF_HasStack` is a per-EXPORT flag, not an "is it an actor?" flag 🔬

An object body may begin with an `FStateFrame` — the UnrealScript execution state (`Node` ref,
`StateNode` ref, `ProbeMask` u64, `LatentAction` u32, and an `Offset` compact **only when `Node` is
non-zero**) — and it does so exactly when the export table's flags word for that object carries
`RF_HasStack` (`0x02000000`). Everything else in the body, including the `None`-terminated
tagged-property list, follows it.

It is natural to assume only actors are affected, because an actor is the thing that runs
UnrealScript. **That assumption is wrong and it silently breaks parsers.** In retail Deus Ex maps a
small number of `Model` and `Polys` exports — plain data objects, not actors — also carry
`RF_HasStack` and therefore also carry a StateFrame. Measured over the first twelve `DX/Maps/*.dx`
(2026-07-27, host-native decode with `upackage`):

| map                      | `Model` exports | with `RF_HasStack` | `Polys` exports | with `RF_HasStack`
|--------------------------|----------------:|-------------------:|----------------:|---
| `00_Intro.dx`            |             948 |                  0 |             948 | 0
| `00_Training.dx`         |            1018 |                  2 |            1018 | 2
| `00_TrainingCombat.dx`   |             577 |                 13 |             577 | 13
| `01_NYC_UNATCOIsland.dx` |            1435 |                  2 |            1435 | 2
| `02_NYC_Bar.dx`          |             210 |                  1 |             210 | 1
| `02_NYC_BatteryPark.dx`  |             883 |                  3 |             883 | 3
| (the other six sampled)  |               — |                  0 |               — | 0

The count always matches between a map's `Model`s and its `Polys` — a flagged brush model and its
polygon list come as a pair. Skipping the StateFrame on those exports makes
`native.umodel.parse_model_body` reach EOF on **21 of 21** of them; entering the body at its raw
`soff` instead desyncs by the StateFrame's length and fails with a truncated read.

**Rule for any body reader: decide on the EXPORT's flags, never on the object's class.** uedcli's
`mapimport._skip_state_frame` takes the export record for exactly this reason.

### The `Actors` array is the AUTHORITY on a level's contents, not the export table 🔬

A map file holds two different answers to "what actors are in this level":

- the `Engine.Level` object's **`Actors` array** — the roster the engine walks; and
- the **export table** — every object stored in the file.

They are NOT the same, and the array wins. Measured over the 88 retail Deus Ex maps (2026-07-27,
host-native decode) and checked against UnrealEd's own `UCC batchexport` of the same maps:

| Divergence | Retail incidence | What UnrealEd's exporter does |
|-------------------------------------|-------------------------------------------|---
| actor-classed export NOT in `Actors` | 1115 objects across 14 of 88 maps | exports **none** of them
| an actor listed TWICE in `Actors`    | `DXMP_Cathedral` (`Brush636`), `DXMP_Area51Bunker` (`Light77`) | emits its block **twice**
| viewport `Camera` actors (on the roster) | 4 per map, every map | omits **all** of them

The off-roster objects are overwhelmingly `PathNode`s (923 of the 1115), plus `PatrolPoint`,
`Light`, `Spotlight`, `HidePoint`, `Teleporter`, `PlayerStart`, `MapExit`, `ZoneInfo`. They look like
actors a designer deleted whose export was never reclaimed: dead weight in the file, not level
content. Confirmed by exporting three of the affected maps (`02_NYC_Warehouse` 3 orphans,
`DXMP_Cathedral` 14, `DXMP_Area51Bunker` 221): **zero** orphans appeared in the editor's output, and
nothing outside the roster ever did. The accounting is exact — on `02_NYC_Warehouse`, 2131 roster
entries minus 4 viewport cameras = 2127 actors exported.

**Rule for any reader: walk the `Actors` array, and treat an off-roster actor object as absent.**
`mapimport.import_map` does, reporting each skip rather than failing (it used to refuse, which made
14 retail maps unimportable).

### The v69 editor cannot export every retail map — `Engine.CameraPoint` 🔬

`UCC batchexport` from the committed v69 UED22 substrate **fails outright** on a retail map holding an
`Engine.CameraPoint` (`00_Intro`): `Failed loading package: Can't find Class in file 'Class
Engine.CameraPoint'`. The class is real in the game's own v68 `Engine.u` — ancestry
`CameraPoint → Keypoint → Actor → Object` — and simply absent from the UT-lineage v69 one, another
instance of the class-graph divergence above.

Two consequences. First, the native decoder handles those maps and the editor route does not, so an
editor export is not available as an oracle for all 88 maps. Second, **resolve retail classes against
the GAME's `System/`, never against UED22** — doing the latter makes `Engine.CameraPoint` look like it
is not an actor at all, and two Endgame maps then look like decode failures when the decode is right.

### `FPoly.ItemName` — name index 0 is a REAL name, and `None` is not index 0 🔬

A polygon's per-face label (`Begin Polygon Item=Base`) is an `FName`: a compact index into the
package's own name table. Two things about that table trip up a decoder:

- **Index 0 is an ordinary name, not a sentinel.** In every Deus Ex map sampled (2026-07-27) name
  index 0 is `OUTSIDE` — the editor's own default face label — and it is genuinely used: 7399 of
  `02_NYC_Street.dx`'s 10690 authored polygons carry it.
- **"No label" is the index of the name `None`**, wherever that happens to sit (index 2 in
  `00_Training.dx`). The name table's order is per package; nothing pins `None` to a fixed slot.

So the test for an unset `Item` is `pkg.names[idx] == "None"`, never `idx == 0`. Treating 0 as unset
silently deletes every `Item=OUTSIDE` from a decoded map — a data loss that no error reports and
that only shows up by reading the emitted T3D. The same reasoning applies to any `FName`-valued
field, including the property-list terminator (`UPolys`' body begins with a compact `None` index,
which is not `0` either).

**Further raw byte-level detail** (package internals beyond the header and the bodies above) lives in
these kept evidence spikes:

- [`../spikes/2026-06-28-umodel-serialize-byte-exact.md`](../spikes/2026-06-28-umodel-serialize-byte-exact.md)
  — `UModel` serialize order + `FBspNode`, `FZoneProperties`, `FCompactIndex`, `UPrimitive` layouts.
- [`../spikes/2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`](../spikes/2026-06-27-decontainerize-uedcli/01-native-texture-decode.md)
  — `UTexture` body, `FMipmap`/`UPalette`, and the `FPropertyTag` (tagged-property) encoding.
- [`../spikes/2026-06-27-decontainerize-uedcli/03-native-package-write.md`](../spikes/2026-06-27-decontainerize-uedcli/03-native-package-write.md)
  — the order package sections are written on disk (summary / name / import / export tables).
- [`../spikes/2026-06-27-decontainerize-uedcli/07-native-actor-bodies.md`](../spikes/2026-06-27-decontainerize-uedcli/07-native-actor-bodies.md)
  — an actor object body: the `StateFrame` prefix followed by tagged properties.
- [`../spikes/2026-06-27-decontainerize-uedcli/10-native-upolys-fpoly.md`](../spikes/2026-06-27-decontainerize-uedcli/10-native-upolys-fpoly.md)
  — `UPolys` container and `FPoly` field order.

---

## Practical takeaways

- Treat `.u`/`.dx`/`.utx`/`.uax`/`.umx` as one UnrealEngine-1 format. uedcli's offline
  parser (`dxpkg.py`) already reads v61/68/69; extend it by name-table encoding, never by
  assuming a version means a different file shape.
- Never explain a Deus-Ex-won't-load-in-Unreal (or vice-versa) symptom as "wrong version".
  Look at the **class graph** (which `Engine`/`Core` is loaded) for code, and at **CSG/BSP**
  (did the brushes carve?) for maps.
- The committed substrate deliberately mixes v68 and v69 packages; that is expected and
  fine.

## See also

- [`t3d.md`](t3d.md) — the T3D on-the-wire *text* format (a different thing: the
  `MAP EXPORT`/`IMPORTADD` actor/geometry text, not the binary package).
- [`quirks.md`](quirks.md) "How brushes enter the level" — the CSG-not-version spawn proof;
  "Containers / package resolution" — the version-tolerant closure reader.
- [`../architecture.md`](../architecture.md) "Package stubbing" / "Code vs. content split".
- `decisions.md` 2026-06-21 / 2026-06-22 / 2026-06-27 — the stubbing rationale and its
  correction (version is not the reason).
