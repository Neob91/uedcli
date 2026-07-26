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
