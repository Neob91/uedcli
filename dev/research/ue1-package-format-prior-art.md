# UE1 package format (`.u`/`.unr`/`.dx`/`.utx`) decoding — uedcli vs prior art

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What does uedcli's package decoding cover today, what does it still not cover, and
what external prior art should the Rust rewrite borrow from or validate against?

## Summary

- uedcli's read coverage is **deeper than every open-source UE1 reader on the class-schema axis**
  and roughly equal on textures. Nothing external decodes UE1 class defaults *and* resolves them
  across the super chain and package boundaries the way `uprops` does — except `UELib` (MIT, C#),
  which is the one genuine peer and the right reference.
- **No Rust UE1 reader exists.** Every Rust `unreal*` crate is UE4/5 (`unreal_asset`, `repak`,
  `uasset`). The rewrite has no dependency to adopt; it has references to port.
- The rewrite starts with real assets: `old/uedcli-native/resolve-core/src/package_read.rs` (582 L),
  `old/uedcli-native/src/mesh_read.rs` (923 L) and `model_read.rs`/`model_write.rs` are already
  pure Rust with `cargo test` unit tests and no PyO3 inside. They lift over as-is.
- The unification is **half done**. One Rust core exists, but six Python decoders still live
  (`utexture.py`, `proceduraltex.py`, `dxpkg.py`, `native/pkg_write.py`, `native/codec.py`,
  `uscript/gate.py`), one of which (`proceduraltex._compact_index`) is a known-wrong copy. PR2 of
  the unification item was never filed.
- **Deus Ex has no licensee version.** Measured locally: every committed package fixture, v61/v68/v69,
  has licensee 0. Ion Storm's own public `Core/Inc/UnObjVer.h` sets `PACKAGE_FILE_VERSION 68`; the
  famous "1100" is `ENGINE_VERSION`, not a package field. The only binary divergence from stock UE1
  is `FMeshVert` (8-byte int16 quad vs 4-byte packed dword) — and uedcli already detects it from the
  data rather than from the game.
- **No UE1 package is compressed or encrypted.** In-package compression first appears at package
  version 334 (UE3-era). `.uz`/`.uz2` are a download transport outside the package.
- Two layout cross-checks landed: uedcli's `UProperty` header layout is **independently confirmed**
  by SurrealEngine's working reader (and Cordero's doc is wrong on it); uedcli's `FPoly` `PanU`/`PanV`
  read is **independently confirmed wrong** (unsigned where the field is signed int16).
- Known hard refusals, all named rather than silent: `unverified-format` on every non-P8/BC1/BC2/BC3
  texture layout, `ambiguous-alpha` on a code-less 16-byte-block chain (permanent), `read_fstring`
  on a negative-length (UTF-16) generic FString, `PT_MAP`/`PT_FIXED`/legacy ptypes in value decode,
  and no `USkeletalMesh` path.
- Licence-wise the field is friendly: `UELib`, `UEViewer`, `unreal-package-lib`,
  `unreal-package-reader` are all MIT; SurrealEngine is zlib. GPL-3 (`UE-Explorer`, `Convedit_Plus`)
  and the Deus Ex SDK headers (EULA) are read-only, not borrow-from.

## What we have today

Roughly **8.1k lines** of read-path package code across Python and Rust (write path excluded):

| Area | Where | LOC | What it owns |
|---|---|---:|---|
| Rust read core | `old/uedcli-native/resolve-core/src/package_read.rs` | 582 | compact index, name entry (v<64 + v>=64 incl. UTF-16), FString, array index, header + name/import/export tables, tagged-property list, declared-count DoS guard |
| Python shell | `old/uedcli/upackage.py` | 328 | `Package`/`load_package`/`PropertyTag` over the Rust core; outer-chain qualification (`object_path`, `object_class_name`); two cache tiers; `SchemaError` no-fallback contract |
| Class schema + defaults | `old/uedcli/uprops/` (`base`/`ufield`/`uclass`/`values`) | 1,454 | `UProperty`/`UEnum`/`UStruct`/`UClass` bodies, the `ScriptText` `TextBuffer`, the bytecode skip walker, the class-defaults tail, super-chain union across packages, T3D-form value rendering |
| Textures | `old/uedcli/utexture.py` + `utexture_decode.py` | 1,647 | `UTexture` two mip arrays, `UPalette`, P8/BC1/BC2/BC3, layout detection from the chain with the `Format` code as tie-break/veto, `TextureResolver` with 12 named error cases |
| Procedural textures | `old/uedcli/proceduraltex.py` | 493 | `FireTexture` spark array, `WaterTexture` drop array, one painted static frame |
| Meshes | `old/uedcli-native/src/mesh_read.rs` (+ `old/uedcli/umesh.py`) | 1,072 | `UMesh`/`ULodMesh` body: verts (both strides), tris, anim seqs, connects, vert links, textures, LOD wedge/face/material arrays, `RemapAnimVerts` rebuild |
| BSP model | `old/uedcli-native/src/model_read.rs` + `old/uedcli/native/umodel.py` | 521 | `UModel` body for v>61 and v<=61 (two real layouts), `UPolys`/`FPoly` via `mapimport.py` |
| Import closure | `old/uedcli/dxpkg.py` | 247 | the set of packages a `.dx` depends on, from the import table |
| Audio | `old/uedcli/audioindex.py`, `umxtitle.py` | 174 | header-only `Sound`/`Music` enumeration; tracker-module title by magic |
| Write path | `old/uedcli/native/pkg_write.py`, `uscript/` | ~11k | from-scratch container writer, the UnrealScript declaration compiler, a byte-exact v69 bytecode codec, `#exec TEXTURE IMPORT` PCX→`UTexture`, `.con` conversation import |

Docs: `old/dev/docs/unrealed/package-format.md` (header, `FMipmap`, `FReachSpec`, `RF_HasStack`,
the `Actors`-array authority rule, `FPoly.ItemName` traps) and
`old/dev/docs/unrealed/class-schema.md` (the `UClass`/`UProperty`/`TextBuffer` layouts and the
script walker). Both are unusually well evidenced — byte-level measurements over the whole Deus Ex
tree, with counter-example counts.

Test corpus committed here: 86 real packages (1 × v61 `.utx`, 3 × v68 `.u`, 82 × v69), 3 `.dx` maps.
The retail game tree is **not** in this worktree, so nothing here re-measures against it.

## Findings

### 1. The read core is unified in Rust; six Python copies were never retired

`old/dev/docs/board/done/unify-ue1-package-read-primitives-into-one-rust/` landed PR1 only: the Rust
core plus `upackage.py` rewired onto it, with two cache tiers. Its own overview says PR2 — retiring
`dxpkg.py`, `utexture.py`, `proceduraltex.py`, `uscript/gate.py`, `native/pkg_write.py` onto the core
— "remains open… file it fresh when picked up". **Nothing is filed** (`grep -rl PR2` across the board
hits only that item's own files).

Compact-index decode exists in six separate Python functions today
(`upackage.read_compact_index`, `utexture._ci`, `proceduraltex._compact_index`, `dxpkg`'s reader,
`native/codec.read_ci`, `uscript/texture_import.py`) plus the Rust one. They are not identical:

- `utexture._ci` omits `upackage`'s `shift >= 27` termination guard.
- `proceduraltex._compact_index` *silently stops* on buffer overrun (`while pos < len(buf)`) instead
  of raising — the spec already calls this "a correctness bug, not a feature".
- `utexture.load_package` raises on a negative name length; the Rust core decodes it as UTF-16LE.

For the rewrite this is a feature, not a problem: there is exactly **one** decoder worth porting, and
the Python copies are the thing being deleted.

### 2. Gap table — what uedcli decodes, refuses, and does not touch

| Object / feature | Status | Notes |
|---|---|---|
| Header v61 / v68 / v69 | ✅ decoded | one code path for v>=64; v61 differs only in name-table encoding. Pre-v68 `Heritage` table not parsed (`guid_range` is `None`) |
| Name table, both encodings | ✅ decoded | incl. negative-length UTF-16LE (Rust core only) |
| Import/export tables, outer chains | ✅ decoded | full dotted `object_path`; out-of-range refs return `None`, never `IndexError` |
| Tagged property list | ✅ decoded | all 8 size codes, bool-in-bit-7, struct name, packed array index |
| `FStateFrame` (`RF_HasStack`) | ✅ decoded | decided on the export's flags, never the class — retail `Model`/`Polys` exports carry one |
| `UClass` body + defaults tail | ✅ decoded | exact-EOF on 1914/1914 classes in the DX install |
| UnrealScript bytecode (read) | ⚠️ skip-walk only | `uprops.ufield._walk_expr` replays `SerializeExpr` to find the end; v68 opcode subset; unknown opcode = `SchemaError`. Full decode+encode exists only for v69 in `uscript/bytecode.py` |
| `UProperty`, `UEnum`, `UStruct` | ✅ decoded | incl. `Children`-chain member order and `Category` |
| `UFunction`, `UState`, `UConst` schemas | ❌ not decoded | `UState`'s fixed prefix is skipped by width; `UFunction` exists only in the write model |
| `TextBuffer` | ✅ decoded | the `.uc` source, used for the `abstract` modifier |
| `UTexture` P8 / BC1 / BC2 / BC3 | ✅ decoded | pixel-exact vs `UCC batchexport` across the DX corpus |
| `UTexture` `CompMips` second array | ✅ decoded | gated on the `bHasComp` *property*, not raw bytes |
| `UTexture` RGB32/RGB64/RGB24/RGBA8, 227 BGRA8/R5G6B5/BC4+ | 🚫 refuses | `unverified-format`; zero samples exist on the dev machine (`board/inbox/the-remaining-ue1-texture-layouts/`) |
| Code-less 16-byte-block chain | 🚫 permanent refusal | `ambiguous-alpha` — BC2 and BC3 are byte-identical in size; nothing in the data separates them |
| `UPalette` | ✅ decoded | 256 RGBA |
| `FireTexture`/`WaterTexture` trailing arrays | ✅ shape decoded | pixel *rendering* is a reasoned approximation, not RE'd (`Fire.dll` not disassembled) |
| `UMesh` / `ULodMesh` | ✅ decoded | vertex stride detected from the `TLazyArray` skip offset, not from the game |
| `USkeletalMesh` / `UAnimation` | ❌ not decoded | and apparently not needed: Deus Ex ships no skeletal meshes |
| `UModel` (BSP) v>61 and v<=61 | ✅ decoded + written | with a Python oracle (`native/umodel.py`) pinning the Rust writer |
| `UPolys` / `FPoly` | ⚠️ one known bug | `PanU`/`PanV` read unsigned — see §7 |
| `ULevel` `Actors` array, `FURL`, `FReachSpec` | ⚠️ partial | `FReachSpec` record *count* is not decoded (found as the longest self-validating run); the header before the records is undecoded |
| `USound` / `UMusic` bodies | ✅ decoded | straight byte copy of the embedded asset |
| `UFont` | ❌ not decoded | |
| Value decode: `PT_MAP` (14), `PT_FIXED` (15), `PT_CLASS_LEGACY` (8), `PT_VECTOR_LEGACY` (11), `PT_ROTATOR_LEGACY` (12) | 🚫 hard-errors | constants exist in `upackage.py`; `render_default_tag` ends in `unsupported default value type`. Externally reported as unused in UE1 content |
| `PointerProperty` | ⚠️ in `PROPERTY_TYPES`, no value decode | hits `unsupported struct member kind` if it ever appears in a struct |
| Generic `read_fstring` with negative length | 🚫 hard-errors | the open board item below; the *name* path handles it |
| Imported super-struct | 🚫 hard-errors | `imported super-struct not supported` |
| Package compression / encryption | n/a | does not exist in UE1 — see §6 |

### 3. The class-schema layer is where uedcli is genuinely ahead

`uprops` does three things no other open-source UE1 reader does together:

1. **Walks the script to reach the defaults.** UE1 stores no on-disk byte length for bytecode
   (`ScriptSize` counts the in-memory stream, where compact refs are 4 bytes). `_walk_expr` replays
   `UStruct::SerializeExpr` token-by-token with two cursors to land on the `UClass` tail.
2. **Overlays the sparse defaults diff root→leaf** across packages, since each class re-states only
   what it changes (`resolve_class_defaults`).
3. **Renders values in T3D form** — enum names resolved cross-package, object refs qualified via the
   outer chain, and nested struct trees stripped member-wise against the default, which is what
   `MAP EXPORT` actually writes.

Prior art ranking on this axis (external): `UELib` (full `UStruct`→`Children` chains, typed
`UProperty` subclasses, `UDefaultProperty` tag decode) > `UTPT` (decompiles; fidelity unverified,
dead since 2004) > `SurrealEngine` (loads classes to *run* them, so the chains are real but the API
is an engine, not an extractor) > `unreal-package-lib` / `unreal-package-reader` / UModel
(per-object tagged properties only, no class schema) > everything else.

Note the asymmetry: UModel and friends read *instance* properties against hardcoded C++ class
tables. uedcli reads the schema out of the game's own `.u`, which is why it works on Deus Ex's
divergent `Engine`/`Core` with no per-game table. That property is worth preserving explicitly in
the rewrite — it is the design decision that makes a second substrate cheap.

### 4. Textures: the layout-arbitration rule is the valuable part

The decoder does not trust a per-game `ETextureFormat` table, and measurement justifies that: the
enum dumped from three installs has 8 slots (Unreal Gold v69), 122 (UED22/227 v69) and 5
(Deus Ex v68), and slot 2 is 8 bytes/px in one and 2 in another. So `detect_layout` sizes the mip
chain and uses the effective `Format` byte (stored, else 0 = P8) only to break ties and to **veto**
anything outside the four verified slots. 45.8 % of 18,176 texture exports fit two or more layouts,
so this is the primary path, not an edge case.

No external tool documents this. UModel and `unreal-package-lib` decode P8 and DXT from the format
code directly; that is the thing the census shows is unsafe across engines.

The catalog's colour derivation (`old/uedcli/texture_colors.py`, 12-name fixed `PALETTE`,
`nearest_color` by squared RGB distance, names over a 0.12 share capped at 3) is uedcli-specific
product behaviour with no prior art and no bearing on format fidelity.

### 5. Meshes: one divergence, detected from the data

`FMeshVert` is the only binary difference between Deus Ex and stock UE1 packages. Ion Storm's public
`Engine/Inc/UnMesh.h` has it under `HIGH_PRECISION_MODELS // DEUS_EX CNN` — `X:16;Y:16;Z:16;PAD:16`,
8 bytes — against stock's single packed dword (`X:11,Y:11,Z:10`). Gildor describes the same thing
from the UModel side and says UModel *rescales* DX verts down into the 10-bit form.

uedcli does better: `detect_vert_stride` computes `(skip_offset − first_element_offset) / count` off
the `TLazyArray` header and gets 8 or 4 with no game flag (falling back to a caller hint only for an
empty array). `old/uedcli/tests/test_mesh_decode.py` explicitly pins the correction that this is
*not* a licensee quirk. Keep that; it is strictly better prior art than UModel's rescale.

`old/dev/docs/unrealed/mesh-transform.md` separately derives world placement from `UMesh::GetFrame`
and flags that mesh rendering adds `PrePivot` **outside** the rotation while brush/CSG puts it
inside — a trap a naive port would hit by reusing the brush helpers.

### 6. Deus Ex specifics: version, licensee, compression

| Claim | Status |
|---|---|
| Package version 68 for Deus Ex `.u`, 69 for UED22-written `.dx` | ✅ verified internally and externally |
| Licensee version is **0** | ✅ measured here across all 86 committed fixtures; corroborated by `UELib`'s table (Deus Ex `68/000`) and by Ion Storm's `Core/Src/UnLinker.h`, where `FPackageFileSummary` has a single 32-bit `FileVersion` and no licensee field at all |
| "Deus Ex is version 1100" | ❌ wrong — `1100` is `ENGINE_VERSION` in `Core/Inc/UnObjVer.h`, not a package field |
| `.dx` is format-identical to `.unr` | ✅ extension only |
| No new property types, no changed tagged-property encoding | ✅ `Core/Inc/UnNames.h` registers exactly 1–15 |
| `ULevel`/`UModel` serialization is stock | ✅ no `DEUS_EX` markers in `UnLevel.h` |
| Deus Ex supports DXT1 | ✅ its D3D driver passes DXT1 through; internally, all 69 measured `CompMips` arrays are DXT1 over P8 `Mips` |
| No skeletal meshes | ✅ none in the DX headers; vertex `_d.3d`/`_a.3d` pairs only (one unverified report of a vestigial `USkeletalMesh` registration in the shipped binary) |
| UE1 packages are never compressed or encrypted | ✅ `CompressionFlags`/`CompressedChunks` first appear at package version 334; `.uz`/`.uz2` are external download transport. (`UELib` has `PackageFlag.Encrypted` and per-game stream decoders, but no UE1 title is listed as encrypted) |
| Negative-length (UTF-16) strings in UE1 | ⚠️ mixed. SurrealEngine's UE1-only reader has no negative branch at all, and the sign convention is documented only on the generic UE1–UE4 wiki page. But uedcli **observed one** in a v69 UED22-written retail map (`20_AireGardens.dx`), and a Deus Ex i18n toolkit implements both branches. Safe reading: stock v68 content is latin-1; v69 editor- and i18n-produced files are not |

### 7. Two layout conflicts, resolved by cross-checking

**`UProperty` header — uedcli is right, Cordero's spec is wrong.** uedcli reads
`[ArrayDim: u32][PropertyFlags: u32][Category: name compact][RepOffset: u16 if CPF_Net]` and
documents "`ElementSize` is not serialized (relinked at load)", derived from disassembling
`UProperty::Serialize` in the game's own `Core.dll` plus a zero-desync decode of 18,316 property
exports. Cordero's doc and the C++ header declaration both suggest `ArrayDimension(WORD) +
ElementSize(WORD)`. SurrealEngine's *working* reader settles it: `ArrayDimension = ReadInt32();`
then `PropFlags = ReadUInt32();` then `Category = ReadName();` then `ReplicationOffset =
ReadUInt16()` only under the Net flag — field for field identical to uedcli. Two independent
derivations agree; the published doc is the outlier.

**`FPoly.PanU`/`PanV` — uedcli is wrong.** `old/uedcli/mapimport.py` reads both with `struct "<H"`
(unsigned). SurrealEngine reads `stream->ReadInt16()` (signed), and `old/dev/docs/board/inbox/
mapimport-decodes-poly-pan-as-unsigned-u16/` already records the symptom ("negative pans break
offline post-verify"). That inbox item is a stub with no body; it now has external corroboration and
a one-line fix.

### 8. External prior art

| Tool | Lang | Licence | Maintained | UE1 scope | Class schema | Defaults | Textures | Meshes | Use to us |
|---|---|---|---|---|---|---|---|---|---|
| `UELib` / Unreal-Library (EliotVU) | C# | **MIT** | yes, 2026-08 (484★) | Unreal 100–226 (pkg 61), UT 338–436 (68/69), **Deus Ex 400–436 (68/0)**, RTNP | **yes** — `UClass`/`UStruct`/`UField`/`UProperty*` + chains + bytecode | **yes** (`UDefaultProperty`) | present, author calls them unconfirmed | no | **Best reference; MIT, safe to port from** |
| UE Explorer (EliotVU) | C# | GPL-3.0 | yes | GUI over `UELib` | via lib | via lib | via lib | no | Use as an oracle only; do not copy code |
| UModel / `UEViewer` (Gildor) | C++ | **MIT** | quiet since 2024-03 (2.9k★) | explicit `GAME_UE1` paths (`SerializeVertMesh1`, `SerializeSkelMesh1`) | no — hardcoded C++ class tables | tags only | yes, P8 + DXT, exports tga/dds/png | **yes**, vertex/LOD/skeletal, glTF/psk | Reference for mesh/texture codecs; **already used by uedcli** as the mesh extractor in the stubbing pipeline |
| SurrealEngine (dpjudas) | C++ | **zlib** | very active, 2026-09 (1.1k★) | full UE1 engine reimplementation; `Docs/PackageFormat.md` is the best current UE1 spec | yes (loads classes to run them) | yes | yes | yes | **Best byte-level cross-check.** Note its own `NO-AI Code Rule.md` asks that LLM-authored changes not be PR'd upstream — a constraint on contributing back, not on reading or on the zlib grant |
| `unreal-package-lib` (shrimpza) | Java | MIT | yes, 2026-08 | UE1/2/3 + UMOD + `.int` | **no** (README is explicit) | tags only | yes, P8 + DXT | no | Small, readable header/table/texture reference |
| `unreal-package-reader` (bunnytrack) | TS | MIT | yes, 2026-09 | **UE1 only** — UT, Deus Ex, Rune, Undying, … | partial | tags only | yes | brush + mesh data | Cleanest UE1-only reference |
| `upkg` (cterveen) | Perl | NOASSERTION | 2024-11 | reader; cites Cordero as its sole spec | no | no | no | no | Reference only (licence unclear) |
| `deus-ex-i18n-toolkit` (fmwizard) | Python | MIT | 2026-06 | UE1 FString/name decode exercised on real DX packages | no | no | no | no | The negative-length FString case, in code |
| UTPT + Delphi package lib (A. Cordero) | Delphi | custom, not OSS (doc is CC-BY-4.0) | dead, v2.0b5 2004 | UE1+UE2; the origin of the public format docs | decompiles, fidelity unverified | unverified | yes | yes | Read the **doc**; do not copy the code |
| `unreal_asset` (crates.io) | Rust | MIT | crate 2023 | **UE4/5 only** | n/a | n/a | n/a | n/a | Not applicable |
| any Rust UE1 reader | — | — | — | **none exists** (checked crates.io `unreal*` and GitHub) | — | — | — | — | — |
| OldUnreal 227 / UT 469 | UnrealScript / binaries | no licence / EULA | active | 227 publishes UnrealScript only; 469 repo is releases + issues, no source. Engine source is under NDA with Epic | no | no | no | no | Semantics only; **do not copy** |
| Deus Ex SDK headers (`onnoj/deus-ex-headers-fixed`) | C++ headers | **no licence** (Eidos/Ion Storm SDK EULA) | mirror, 2015 | the authoritative field-by-field truth for DX | yes | yes | yes | yes | Clean-room hazard: cite for facts, keep out of the implementation's provenance |
| `Convedit_Plus` (`.con` reader) | Delphi | GPL-3.0 | — | the `.con` format `uscript/conimport.py` reimplements | n/a | n/a | n/a | n/a | Oracle only (copyleft) |
| `dx-reverse-info` (JuggyMcNutty) | notes | **Zlib** | 2026-10 | DLL-level RE notes (`ConSys`, `d3ddrv`, engine) | — | — | — | — | Freely usable notes |
| `ucc batchexport` / UnrealEd | — | proprietary | — | ground-truth exporter | n/a | n/a | yes | partial (no mesh exporter) | **Differential oracle**, as uedcli already uses it |

Documentation, all prose and safe to read:
Cordero's *Unreal Tournament Package File Format* v1.6 (2001) — the canonical UE1 reference, with
chapters for Field/Const/Enum/Property/Struct/Function/State/Class, the native classes, and the
bytecode; the author himself calls it "very old and incomplete". The BeyondUnreal wiki has only
**two** UE1 pages (`Legacy:Package File Format` and `/Data Details`) — the per-class chapter
structure is Cordero's, not the wiki's. SurrealEngine's `Docs/PackageFormat.md` is the best current
UE1-specific spec. `bunnytrack.net/ut-package-format` is a good modern walkthrough but documents
name lengths as byte-prefixed, which breaks on names ≥ 64 chars.

### 9. Open board items touching package decode

| Item | One line |
|---|---|
| `to-spec/upackage-read-fstring-hard-errors-on-a-unicode/` | `read_fstring` raises on a negative length; the real case is a long multi-`Group` name with a non-ASCII char in `20_AireGardens.dx`, which kills the whole package load. Parked question: strict vs `errors="replace"` on genuinely bad UTF-16 (the written recommendation is strict) |
| `to-spec/on-demand-deus-ex-package-stubbing/` | Implemented end-to-end 2026-06-22; remnants are a `--deps` recursive-stub flag and broader cross-package asset resolution. The whole subsystem exists only to bridge Deus Ex's class-graph divergence for the real editor — a native read/write path deletes it |
| `done/unify-ue1-package-read-primitives-into-one-rust/` | PR1 merged (Rust core + caches). **PR2 — retiring the five remaining duplicate decoders — is open and unfiled** |
| `inbox/the-remaining-ue1-texture-layouts/` | Unreal Gold RGB32/RGB64/RGB24/RGBA8 and 227 BGRA8_LM/R5G6B5/RGB8/BGRA8/BC4+ still refuse with `unverified-format`. Sample acquisition comes first — zero samples exist locally, and slot numbers are not portable between engines |
| `inbox/mapimport-decodes-poly-pan-as-unsigned-u16/` | Stub item; the bug is real and now externally corroborated (§7) |
| `inbox/re-pin-ulevel-actors-array-layout-without-the/` | Deleting the native writer took the test that pinned the `Engine.Level` `Actors` array layout; the fact is now pinned on the read side only, if at all |
| `inbox/actor-state-frame-latentaction-is-serialized/` | The editor is not byte-deterministic: `FStateFrame.LatentAction` carries 4 uninitialized bytes per `RF_HasStack` export, so full byte parity has a hard ceiling and those bytes must be excluded from any parity definition |
| `stale/migrate-utexture-py-dxpkg-py-onto-the-unified/`, `stale/upackage-load-package-has-zero-caching-3404/` | Both superseded by the unification item |

## Options

| Option | Pros | Cons |
|---|---|---|
| Port the existing Rust (`package_read.rs`, `mesh_read.rs`, `model_read.rs`) forward unchanged, then port `uprops` to Rust | Keeps every measured fact and every named error; the three files already have `cargo test` coverage and no PyO3 inside; `uprops` is the hard, differentiating part and is well documented | The six Python duplicates still need deleting; `uprops` is ~1.5k lines of subtle layout code to re-derive |
| Depend on an external library | Zero maintenance of the format layer | **Not available.** No Rust UE1 crate exists; C#/C++/Java/TS would mean FFI or a subprocess, i.e. worse than what we have |
| Port `UELib`'s object model wholesale as the schema layer | MIT; the most complete UE1 class/defaults implementation in the wild | C# → Rust rewrite of a large OO graph; uedcli's own layer is already corpus-validated and carries the Deus Ex specifics `UELib` does not need |
| Reference-only use of external tools + differential testing | Cheapest; matches the rewrite spec's stated primary method | Depends on the retail game tree being present, which this worktree does not have |

## Proposal (owner's call — not decided)

Lift the three existing Rust decoders into the rewrite as the first non-trivial vertical slice after
the walking skeleton, and in the same pass fold the five surviving Python decoders into them rather
than porting them — i.e. do PR2 *as* part of the rewrite, not as a separate `old/` change. Treat
`UELib` (MIT) as the reference for anything in `uprops` that needs re-deriving, SurrealEngine (zlib)
as the byte-level cross-check, and `ucc batchexport` as the differential oracle, keeping the Deus Ex
SDK headers at arm's length from the implementation's provenance.

Two cheap wins worth taking first, independently of the rewrite's ordering: the `FPoly` `PanU`/`PanV`
signedness fix (one line, externally corroborated) and the `read_fstring` negative-length branch
(the Rust `read_name` already has the code).

## Open questions / what to verify next

- Is the `PanU`/`PanV` fix safe against the T3D goldens, or do the goldens encode the unsigned
  reading? Needs the retail tree, which is absent here.
- Does any retail v68 Deus Ex package actually contain a negative-length name/string, or is the only
  observed case UED22-written v69? The board item names one v69 map; nothing has swept v68.
- `PT_MAP`/`PT_FIXED`/`PT_CLASS_LEGACY` are reported externally as unused in UE1 content. Worth a
  one-off corpus sweep to turn "hard-errors on" into "proven absent", so the rewrite can refuse them
  with a citation instead of a guess.
- `FReachSpec`'s record count and the `ULevel` header before it are still undecoded — SurrealEngine's
  level loader probably settles both.
- Unverified: the reported vestigial `USkeletalMesh` registration in the shipped Deus Ex binary; the
  exact source terms on Cordero's Delphi unit; whether 227's extra texture slots can be sampled at
  all without a 227 content set.
- Does the root `Cargo.toml` need the MIT `license` field that `old/uedcli-native/Cargo.toml` has?
  Relevant if any ported code carries an attribution obligation.

## Sources

Internal (this repo): `old/dev/docs/unrealed/package-format.md`,
`old/dev/docs/unrealed/class-schema.md`, `old/dev/docs/unrealed/mesh-transform.md`,
`old/uedcli/upackage.py`, `old/uedcli/uprops/`, `old/uedcli/utexture.py`,
`old/uedcli/utexture_decode.py`, `old/uedcli/proceduraltex.py`, `old/uedcli/mapimport.py`,
`old/uedcli-native/resolve-core/src/package_read.rs`, `old/uedcli-native/src/mesh_read.rs`,
`old/uedcli-native/src/model_read.rs`, `old/uedcli/native/umodel.py`,
`old/dev/docs/board/done/unify-ue1-package-read-primitives-into-one-rust/`,
`old/dev/docs/board/to-spec/upackage-read-fstring-hard-errors-on-a-unicode/`,
`old/dev/docs/board/inbox/the-remaining-ue1-texture-layouts/`.

External:

- <https://github.com/EliotVU/Unreal-Library> — `UELib`, MIT; its README carries the engine/package
  version table, incl. Deus Ex = package 68, licensee 000.
- <https://github.com/EliotVU/UE-Explorer> — GPL-3.0 (the GUI, not the library).
- <https://github.com/gildor2/UEViewer> — UModel, MIT; UE1 mesh paths in
  `Unreal/UnrealMesh/UnMesh2.cpp`.
- <https://github.com/dpjudas/SurrealEngine> — zlib; `Docs/PackageFormat.md`,
  `SurrealEngine/Packages/Core/Properties/UProperty.cpp` (settles the `UProperty` header),
  `SurrealEngine/Packages/Engine/Resources/Level/UPolys.cpp` (`PanU`/`PanV` as `ReadInt16`),
  `SurrealEngine/Package/PackageStream.cpp` (UE1 `ReadString` has no negative branch),
  `NO-AI Code Rule.md`.
- <https://github.com/shrimpza/unreal-package-lib> — Java, MIT; UE1/2/3, no UnrealScript.
- <https://github.com/bunnytrack/unreal-package-reader> — TS, MIT; UE1-only.
- <https://github.com/fmwizard/deus-ex-i18n-toolkit> — MIT; `tools/ue1_fstring.py` implements both
  FString encodings against real Deus Ex packages.
- <https://github.com/cterveen/upkg> — Perl; licence NOASSERTION.
- <https://www.acordero.org/projects/unreal-tournament-package-delphi-library/> — Cordero's spec
  v1.6 (2001) and its successor Delphi unit; full text at
  <https://archive.org/details/ut-package-file-format>. The Scribd copy is misattributed to
  "Darren O'Shea" — ignore it.
- <https://beyondunrealwiki.github.io/pages/package-file-format.html> and
  <https://beyondunrealwiki.github.io/pages/package-file-format-data-de.html> — the only two UE1
  wiki pages. `wiki.beyondunreal.com` itself returns 403 to automated fetch; mirrors were used.
- <https://wiki.beyondunreal.com/Unreal_package> — the UE1–UE4 page; source of the "INDEX used
  before package version 178" and the per-game version numbers (via search snippets only; the page
  itself was not fetchable).
- <https://raw.githubusercontent.com/EliotVU/Unreal-Library/develop/src/Branch/PackageObjectLegacyVersion.cs>
  — `CompressionAdded = 334`, i.e. no in-package compression in UE1/UE2.
- <https://wiki.beyondunreal.com/UZ2_file> — `.uz`/`.uz2` as external download transport.
- <https://github.com/onnoj/deus-ex-headers-fixed> — mirror of the Deus Ex SDK headers, **no
  licence**: `Core/Inc/UnObjVer.h` (`PACKAGE_FILE_VERSION 68`, `ENGINE_VERSION 1100`),
  `Core/Src/UnLinker.h` (summary has no licensee field), `Core/Inc/UnNames.h` (property ids 1–15),
  `Engine/Inc/UnMesh.h` (`HIGH_PRECISION_MODELS // DEUS_EX CNN`), `Core/Inc/UnStack.h`
  (`FStateFrame`).
- <https://raw.githubusercontent.com/stephank/surreal/master/Core/Inc/UnNames.h> — the
  `REGISTER_NAME(1, ByteProperty) … REGISTER_NAME(15, FixedArrayProperty)` table that *is* the
  property-tag type enum.
- <https://github.com/JuggyMcNutty/dx-reverse-info> — Zlib; DLL-level notes on `ConSys`, `d3ddrv`
  (DXT1/`TEXF_RGBA7` handling), engine.
- <https://github.com/slserpent/deus-ex-package-extraction> — no licence; community format notes
  (the "mysterious 15–17 byte object header" is `FStateFrame`).
- <https://github.com/LoadLineCalibration/Convedit_Plus> — GPL-3.0; `ConFile.Reader.pas`, the `.con`
  format `uscript/conimport.py` reimplements.
- <https://www.gildor.org/smf/index.php?topic=14.15> — Gildor on Deus Ex's 16-bit `FMeshVert` and
  UModel rescaling it.
- <https://github.com/OldUnreal/Unreal-PubSrc> (no licence, UnrealScript only) and
  <https://github.com/OldUnreal/UnrealTournamentPatches> (releases + issues, no source);
  <https://www.oldunreal.com/phpBB3/viewtopic.php?t=7167> — engine source is under NDA.
- <https://www.snakebytestudios.com/2025/10/deus-ex-modding/> — that `ucc batchexport` fails partway
  through `DeusEx.u` and UnrealEd's "Export All" is the working route. **Unverified by us.**
- Unverified / could not reach: `web.archive.org` (blocked in the research environment), Epic's
  archived `Packages.htm` infobase page, Steve Tack's `unr2de`, Revision and "Han's patch" as format
  sources, and whether any retail Deus Ex package is corrupt in the ways community docs hint at.
