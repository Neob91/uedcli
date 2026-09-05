# The compile model — ordering, flags, CRC, defaults

How UCC turns resolved declarations into the ordered, flagged package the serializer emits
(`u-format.md`). Everything here is measured against UCC compiles and pinned by `test_uscript_*`.

## Table ordering (name / import / export)

**Algorithm (DLL-confirmed from `core.dll` `UObject::SavePackage` @ 0x277c0):** each of the three
tables is built by gathering into a base order, then `appQsort` (the MSVC CRT `qsort`, unstable)
**DESCENDING by an integer reference-count key**; ties keep the base order via the unstable sort's
seeding. During the import/name tagging+counting pass, each `FName` reference does
`NameIndices[name]++` and each `UObject` reference does `ObjectIndices[obj]++` (recursing into an
import's Outer — why `Core` sorts first among imports).

| table | descending key | base / gather order |
|-------|----------------|---------------------|
| names   | `NameIndices[globalNameIndex]`   | global `FName` registration order |
| imports | `ObjectIndices[obj.globalIndex]` | global `GObjObjects` creation order |
| exports | `ObjectIndices[obj.globalIndex]` | `GObjObjects` = the package's own object PARSE order |

**Status (2026-09-05, superseding the exclusion proposal below — owner ruling: reproduce, don't
exclude):** export and import order reproduce byte-exact from the runtime-dumped `GObjNames`/
`GObjObjects` tables (`global_index.py`, dumped from a booted `UCC.exe` under `winedbg`, an INT3
planted at `SavePackage`) plus an instruction-exact port of `core.dll`'s CRT `qsort`. **Name order
also reproduces byte-exact**, including member-bearing and multi-function classes (`UscHello`/
`UscVars`/`UscBB`/`UscFn`/`UscW`, and real-world `FrameBuilder`/`RahnemBrushBuilders`): UCC's
compile-time `FName`-registration is a per-object declaration walk, plus two extra rules for
"value-only" names (a name that is never an object's own name): a **package self-reference** (spliced
into `PackageImports`) registers at **class-header time**; a `defaultproperties` tag's **name-typed
VALUE** (e.g. `GroupName="Landscape"`) registers **last**, after every member and function, since
`defaultproperties` compiles last. Modeled in `ordering._gather_names` + `ObjInput.late_name_refs`.
The former "permutation exclusion" proposal (gate masks name/import ORDER) is retired — see
`parity.md` for the current, much narrower exclusion set (just the GUID, for the packages that fully
reproduce). Open: an Enum's own value-list may carry its own un-RE'd sub-order (`DavesBrushBuilders`);
`ExtendedBuilders` diverges on raw byte count, unrelated to ordering. Historical example orders:

- `UscHello` names: `None, UscHello, Core, System, Class, TextBuffer, ScriptText, Package, Object`.
- `UscVars` exports: `ScriptText, Alpha, Beta, Gamma, UscVars` (Children chain in decl order,
  `ScriptText` first, `Class` last).

## Name-table flags

`u32` per name = `0x10 | 0x00070000 | extra`, where `extra` is the OR of two independent name-pool
bits (both keyed on the engine pools, not on whether this package imports the name):
- `+0x04000000` **RF_Native** — the name is in the engine boot global name pool: the union of every
  RF_Native name across the stock `.u` tables (197) ∪ `core.dll`'s hardcoded `RegisterNames` block
  (268) = 341 names (`global_index.ENGINE_NAME_POOL`). Note `ScriptText`/`ReturnValue` appear in
  Core.u but are NOT RF_Native, and intrinsics like `Add` are RF_Native but in no stock table — so
  neither the naive string-union nor stock-flags-alone is right; the measured pool is both sources.
- `+0x00000400` **RF_HighlightName** — the name is a reserved keyword or intrinsic type/struct name
  (the 30 names carrying `0x400` across stock tables: `None Class Package Function Struct Enum Const
  State String Name Vector Rotator Color ...`; `global_index.HIGHLIGHT_NAME_POOL`).
- names introduced by THIS package (class name, `ScriptText`, non-colliding members) get neither.

## ClassFlags

Plain `class Foo expands Object;` → `ClassFlags = 0x12`. Modifier→bit mapping (abstract, transient,
native, config(...), etc.) mapped per feature rung. `ClassGuid` is always all-zero.

## PropertyFlags (CPF_) in a UProperty body

Plain `var int/float` → `0`. `var string` (dynamic StrProperty) → `0x00400000` (needs-ctor-link).
Full CPF_ derivation (`var()` editability, `const`, `config`, arrays, etc.) per rung.

## ScriptTextCRC

`UClass.Dependencies[].ScriptTextCRC` = `appStrCrc` of the class's stored CRLF `ScriptText`
(`uscript/crc.py`): CRC-32/BZIP2 (poly `0x04C11DB7`, init/xor `0xFFFFFFFF`, non-reflected) over the
UTF-16LE bytes, no trailing NUL. **For an imported dependency (a parent in another package), the CRC
is read from that class's own self-dependency in its home package**, not recomputed. Deep is `1`.

## defaultproperties block

The UClass body tail is a `None`-terminated tagged-property list of the class default object.
**Rule (measured 2026-09-04): emit a tag for every property the class ITSELF declares — in
`Children` (declaration) order — regardless of value**, plus any INHERITED property whose default is
overridden here. So a class with `var int A; var float B;` and no `defaultproperties` still emits
`A=0, B=0`; `UscHello` (no own properties) emits an empty block. This is why `Gamma=""` appeared —
it is an own property, not a set default. Values are the CDO values (from `defaultproperties`, else
type-zero). Static arrays emit one tag per element (`array_index` 0..n-1); dynamic `array<T>` emits
one tag. Bools carry their value in the tag info byte. Tag encoding reuses
`native/actor_write.write_props`.

**Inherited overrides** (a class setting a parent's member in `defaultproperties`) emit their tag(s)
**after** all own-member tags, in the super's field-iteration order (most-derived ancestor first,
`Children` order within); the member's type is resolved by walking the super chain across packages.
Only inherited members whose value the class actually changes emit (it's a diff vs the super CDO).

**Golden gotcha:** the shipped `uned/UED22/*.u` are EDITOR-serialized — they drop own zero-valued
props (e.g. `FrameBuilder.Tessellated=False` is absent) and carry accreted `None`-holes. They are
NOT a valid compile reference; always compare against a fresh `reference.ucc_compile` of the same
sources.

## Native classes (RE'd 2026-09-05 vs UT99 UCC, e.g. `Fire`)
A `class X … native;` (or `intrinsic`): the UClass export carries `RF_Native` (0x08000000) in its
ObjectFlags; ClassFlags inherit the `CLASS_Inherit` subset (SafeReplace/Transient/…) from the super.
**Defaults rule differs for a native OR transient class:** it emits ONLY explicitly-set defaults (a
plain class emits a type-zero tag for every own property; a native/transient one does not).
`PackageImports` inherit the super chain's transitive package deps (own package first, then supers'
packages, then Core; case-insensitive dedup, spelled as the existing import). A class-reference
default (`AcceptClass=Class'Foo'`) emits an object tag; `class`→object coerce and `new` (`EX_New`)
are supported. A body-less native FUNCTION emits one `EX_NativeParm` per param, `FUNC_Native`, with
the `optional` param flag; TextPos sits at its terminating `;`.

## Function Line / TextPos
Both point at the FIRST EXECUTABLE STATEMENT: `Line` = its 1-based source line, `TextPos` = its byte
offset into the CRLF `ScriptText` — skipping the `{`, comments, AND leading `local …;` decls. (Not
the declaration line — that only coincided for single-line test functions.) An empty body points at
the closing `}`. A UFunction overriding an inherited one sets its body `SuperField` to the parent
UFunction (added as a `Function`-class import, Outer = the declaring parent class).
