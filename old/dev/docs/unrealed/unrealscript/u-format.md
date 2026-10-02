# `.u` write-side format — code-object serialization

What the compiler must emit to be byte-identical to UCC. The container plumbing (header, name/
import/export tables, FCompactIndex/FName/FString) is reused from the map-parity writer
(`uedcli/native/pkg_write.py`, `codec.py`) — this doc covers the code-object BODIES and the fields
UCC computes. Every fact here is pinned by the parity gate against a UCC compile
(`test_uscript_*`). Package version is **69** (`v69/0`).

## Determinism / exclusion set (measured 2026-09-04)

Two clean compiles of identical source differ in **exactly the 16-byte package GUID** (header
offsets 36–51) and nothing else. So byte-parity == the gate passing with only the GUID masked. No
timestamps, no ordering jitter. `ClassGuid` inside a UClass body is **all-zero** (not random).

## Header (v69, 64 bytes for a tiny package)

`u32 magic(0x9E2A83C1) | u32 version(low16=69,high16=licensee 0) | u32 packageflags | u32 nameCount
| u32 nameOff | u32 exportCount | u32 exportOff | u32 importCount | u32 importOff | FGuid(16) | u32
generationCount | generationCount×(u32 exportCount, u32 nameCount)`. A freshly compiled package has
**one** generation = (final exportCount, final nameCount). Package flags = `0x1` for a plain script
package. Layout order in the file: header → names → export bodies → imports → exports.

## Name table entry

`ci(len incl NUL) + latin-1 bytes + NUL + u32 flags`. Flags = `0x10 | 0x00070000 | extra`:
- base `0x00070010` (the RF_LoadFor* context bits + 0x10).
- `+0x04000000` for names referenced by the **import table** (import class-package, class-name,
  object-name) and the class **config name** (e.g. `System`).
- `+0x04000400` for the structural names **None**, **Class**, **Package**.
- the package's own name and its objects' names (e.g. `UscHello`, `ScriptText`) get only the base.

(`NameTable._INTRINSIC`/`.mark()` already encode this scheme for maps; code packages differ only in
which names get `0x04000000`. Exact rule still being widened across the corpus — see
`compile-model.md`.) **Name ORDER matters** and is UCC's encounter order — see `compile-model.md`.

## Import table entry

`ci ClassPackage(nameIdx) + ci ClassName(nameIdx) + i32 PackageIndex(objref of outer) + ci
ObjectName(nameIdx)`. A root package import has PackageIndex 0; a class/object import points its
PackageIndex at its outer import (e.g. `-1` = import[0]). For `class Foo expands Object;` the imports
are, in order: `Core`(Package), `Object`(Class in Core), `TextBuffer`(Class in Core), `Class`(Class
in Core).

## Export table entry

`ci Class + ci Super + i32 Outer + ci Name + u32 ObjectFlags + ci SerialSize + (ci SerialOffset iff
SerialSize>0)`. Refs are signed: `0`=None, `>0`=export idx (1-based), `<0`=import (`-idx-1`).

- **A UClass export's Class field is `0` (None)**, NOT a ref to the `Class` metaclass. (UE1 quirk;
  verified — a class's class is left None on disk.)
- A `ScriptText` (UTextBuffer) export: Class = the `TextBuffer` import, Super = 0, Outer = the owning
  class export.
- ObjectFlags seen: UClass `0x000f0004`, TextBuffer `0x00340000`, UProperty/UFunction `0x00070004`.

## Object bodies

### UTextBuffer (`ScriptText`)
`ci(None=0) + u32 Pos(0) + u32 Top(0) + FString(text)`. `text` is the class source normalised to
CRLF line endings, **truncated at the `defaultproperties` block** — UCC stores the source only up to
(not including) `defaultproperties`. The class self-dependency `ScriptTextCRC` is computed over this
same truncated CRLF text.

### UClass
`ci SuperField(super class ref) + ci Next(0) + ci ScriptText(export ref) + ci Children(first child
field ref, 0 if none) + ci FriendlyName(nameIdx) + u32 Line(0xFFFFFFFF) + u32 TextPos(0xFFFFFFFF) +
u32 ScriptSize + <script bytecode> + u64 ProbeMask(0) + u64 IgnoreMask(0xFFFFFFFFFFFFFFFF) + u16
LabelTableOffset(0xFFFF) + u32 StateFlags(0) + u32 ClassFlags + FGuid ClassGuid(all-zero) + TArray
Dependencies{ci Class, u32 Deep, u32 ScriptTextCRC} + TArray PackageImports{ci nameIdx} + ci
ClassWithin(default Object) + ci ClassConfigName(default `System`) + <defaults: None-terminated
tagged-property list>`.

- `ClassFlags` for a plain `class Foo expands Object;` = `0x12`. (Bit derivation from class modifiers
  still being mapped — `compile-model.md`.)
- `Dependencies`: self first (this class, Deep=1, CRC), then each parent/referenced class (Deep=1,
  CRC). **`ScriptTextCRC` of an imported class is read from that class's own self-dependency in its
  home package** (transitive), not recomputed. The CRC algorithm for classes we compile is under RE
  (`compile-model.md`).
- `PackageImports`: name indices of the packages this class pulls in (own package first, then
  `Core`, …).

### UProperty (scalar)
`ci(None=0) + ci(SuperField=0) + ci(Next = next sibling property, 0 if last) + u32 ArrayDim(1 scalar)
+ u32 PropertyFlags + ci(Category=0)` — 12 bytes for int/float/bool/name/str. **ByteProperty adds a
trailing `ci(Enum ref, 0 if none)` → 13 bytes.** PropertyFlags: 0 for int/float/bool/byte/name;
`0x00400000` for string (StrProperty, ctor-link). The class `Children` points at the first property;
properties form a `Next` singly-linked chain in declaration order. ObjectFlags (export table)
`0x00070004`. (Object/Class/Struct/Array/FixedArray property type-tails: their rungs.)

### UFunction / UState / UStruct / UEnum / UConst
Layouts and the bytecode token stream: `bytecode.md` (emitter) and this doc's later revisions as each
is reached on the feature ladder.
