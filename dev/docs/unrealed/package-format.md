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

### `UTexture` — TWO mip arrays, the second gated on a PROPERTY ✅

A `UTexture` body is a tagged-property list, the `None` terminator, and then **up to two**
`TArray<FMipmap>`. The second one, `CompMips`, holds a **block-compressed copy of the same image**
and is present **iff the body's `bHasComp` property is true**:

```
UTexture body
  <tagged property list>        # Format, Palette, bHasComp, CompFormat, bMasked, ...
  None                          # property-list terminator (a name-table compact index)
  Mips     : TArray<FMipmap>    # compact-index count, then count x FMipmap
  [if bHasComp]
  CompMips : TArray<FMipmap>    # SAME encoding; present iff the bHasComp PROPERTY is true

FMipmap (per mip)
  WidthOffset : uint32   # TLazyArray skip offset: the ABSOLUTE file offset just past Data.
                         # PRESENT when Ar.Ver >= 63 (v68/v69); ABSENT in v61.
  DataCount   : compact index    # number of pixel bytes in this mip
  Data        : byte[DataCount]  # palette indices (P8) or block bytes
  USize       : uint32           # mip width
  VSize       : uint32           # mip height
  UBits       : uint8
  VBits       : uint8
```

**`bHasComp` and `CompFormat` are TAGGED PROPERTIES, not raw bytes after `Mips`.** This is the trap:
the natural reading of "the body is `Mips`, then `bHasComp`/`CompFormat`/`CompMips`" is wrong, and a
parser built on it fails on every real sample. Measured over the whole Deus Ex tree (2026-07-25):
reading two raw bytes after `Mips` and then a second array gives **107 skip-offset mismatches + 100
non-EOF bodies**; reading the flags out of the property list and parsing `CompMips` **immediately**
after `Mips` lands exactly on the declared body end for **207 / 207** previously-failing `Texture`
exports, and consumes **zero** bytes when the flag is absent or false.

**This is the cause of every "trailing bytes" failure on class `Texture`** — a one-array parser stops
after `Mips` and overruns. Counts: 39 in the Deus Ex `System`+`Textures` roots, 30 in the project's
own `LUM/Textures/LUM_CoreTex.utx`, 207 over the whole tree — and `CompMips` explains **100 %** of
them on every root measured. Every `bHasComp` texture measured is `(Format ⇒ 0, CompFormat = 3)`: a
P8 original with a DXT1 copy. **Prefer `Mips`** — it is the higher-fidelity original; `CompMips` is
lossy.

**`Format` names the `Mips` array's layout and `CompFormat` the `CompMips` array's.** They are
different codes for different arrays and judging one array against the other's code is a wrong
image, not an error: all 69 measured `CompMips` arrays are DXT1 while their `Mips` are P8.

**Two integrity signals, and on v61 there is only one.** For v68/v69 each mip's `WidthOffset` is a
free per-mip check — after reading `Data` the cursor must equal it. v61 has no skip offsets at all,
so the only check is that the body ends exactly where the export table says. uedcli's decoder
therefore records the body's leftover byte count for *every* texture rather than raising, and both
checks span both arrays.

**An empty mip is not a corrupt body.** Procedural textures serialize mips whose `DataCount` is `0`
— over the whole Deus Ex tree: 208 `FireTexture`, 42 `WetTexture`, 14 `WaveTexture`, 8 `IceTexture`,
50 `ScriptedTexture`. Only `FireTexture` *also* trails bytes (a `TArray<FSpark>`, 8 B per spark
matching `NumSparks`); the others end clean. So "carries no pixels" is detectable from the data
(`len(mip.data) == 0`) and never from a class name — which matters because a class-name rule would
miss every modded procedural class.

#### Which pixel layout is it? Read it off the mip chain ✅

**A mip chain is self-describing.** Block-compressed formats store `ceil(w/4) × ceil(h/4)` blocks,
so their chains **floor at one block** — an 8- or 16-byte tail. Linear formats keep scaling as
`w·h·N` all the way to 1×1. That is enough to name the layout without any per-game table, which
matters because **slot numbers are not portable**: `ETextureFormat` dumped from three installs has
8 slots (Unreal Gold v69), 122 (UED22/227 v69) and 5 (Deus Ex v68), and slot 2 is 8 bytes/px in one
(`RGB64`) but 2 in another (`R5G6B5`). A hardcoded table mis-slices real data and then reports a
bogus size mismatch.

**But the data is not always decisive.** A `w × h` mip of `w·h` bytes is byte-identically explained
by P8 (`w·h·1`) *and* by a 16-byte block layout (`(w/4)(h/4)·16 = w·h`) whenever both dimensions are
multiples of 4 — the chain only gives itself away once it descends below one block. Measured over
18,176 texture exports: **45.8 % fit two or more layouts.** So the `Format` code is a **primary**
path, not an edge case.

**The code breaks ties and vetoes; it never contradicts the data and never sizes a chain.** Four
slots, and all three dumped enums agree on them (Deus Ex is *silent* on 6 and 7 rather than
disagreeing — five slots — so it cannot contradict):

| effective code | layout |
|----------------|--------|
| `0`            | P8 (palettized, 1 byte/px) |
| `3`            | BC1 / DXT1 (8-byte blocks) |
| `6`            | BC2 / DXT3 (16-byte blocks, explicit 4-bit alpha) |
| `7`            | BC3 / DXT5 (16-byte blocks, interpolated alpha) |
| anything else  | **vetoes the array** — no pixels, even if the data fits exactly one layout |

**"Effective" means the stored byte if the property is present, else 0.** UE1 omits any property
equal to its class default, so an absent `Format` is not a missing code — it *is* the byte 0, which
is P8 in all three enums. Measured: a `Format` property is physically present on **11 of 18,176**
exports, so the implied 0 is what resolves 8,324 of the 8,327 ambiguous chains.

**The veto is not pedantry.** 227's slot **8** is `TEXF_BC4`, a single-channel **8-byte-block**
format whose mip chain is byte-for-byte the size of BC1's and fits it uniquely. Without the veto a
BC4 texture is drawn as BC1 — a confident wrong image on a file whose own code says it is not BC1.
Slot 9 collides the same way; 10 and 11 collide with the 16-byte class. Measured firing rate on real
content: **zero** (all 11 stored codes are 3 or 7).

Consequently **an uncoded 8-byte-block chain is taken for BC1 by ASSUMPTION, not deduction** — the
data cannot separate BC1 from BC4. The assumption is safe because a genuine BC4 export has
`Format = 8 ≠ 0` and therefore writes the byte, which the veto catches; what is really assumed is
that no writer emits a non-BC1 8-byte-block chain while omitting `Format`.

**THE STATED LIMIT ON UNIVERSALITY — and it must always be written with its scope.**

> **A BC2 or BC3 texture whose chain fits the 16-byte class UNIQUELY and stores no `Format` code
> does NOT decode.** It reports `ambiguous-alpha` and no pixels. BC2 and BC3 have byte-identical
> sizes and mip chains and differ only in how each block's alpha half is encoded; nothing in the
> data separates them and no future measurement will.
>
> **A code-less BC1 file whose chain fits the 8-byte class UNIQUELY DOES decode** — 8-byte blocks
> are shared with no other layout read here.
>
> **Where the chain ALSO fits P8, the implied `Format = 0` decodes it as P8.** Both halves above are
> false without the word *uniquely*: re-measured 2026-07-26 over `uned/UED22`, of 1,137 ambiguous
> chains **1,089 fit `{P8, 16-byte}` and 48 fit `{P8, 8-byte}`** — e.g. `uwindow.u:WhiteTexture`
> (32×32 truncated at 4×4) and `DeusExUI.u:HUDItemsBorder_Center` (64×2).

Where the data leaves a real choice and no code names a fitted candidate, the answer is a named
error rather than a guess. Measured frequency of that on real content: **zero**, because P8 is a
fitted candidate in every ambiguous chain that stores no code.

**BC3's alpha half is what identifies it.** All 4,096 blocks of `DmRiot.unr:Poster01`'s mip 0 carry
`0005ffffffffffff`. As BC3 (`a0 = 0 ≤ a1 = 5`, six-interpolant mode, every index 7) that is
uniformly opaque; as BC2 the same eight bytes are sixteen explicit nibbles giving alpha 0/85/255
noise. One distinct value across a whole mip is nonsense for per-texel alpha and exactly what a
fully-opaque BC3 export looks like.

(uedcli's `utexture.detect_layout` implements this; `utexture.decode_texture` reads the layout
above. **Every measurement quoted in this section — the census in both units, the three enum dumps,
the eleven stored codes, the oracle tables and the method behind them — is recorded in
[`../spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`](../spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md).**
Spikes
`../spikes/2026-07-25-native-texture-formats/` and
`../spikes/2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`, which proved the P8 path
pixel-exact against `UCC batchexport` across the whole install. Measured 2026-07-25.)

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
