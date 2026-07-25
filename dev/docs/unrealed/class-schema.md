# UClass on-disk facts — abstractness + shipped source (offline)

How uedctl reads a class's *abstractness* and its `.uc` source directly from a v68 `.u` package,
with no editor. Consumed by `uedctl/uprops.py` (`class_is_abstract`, `_class_script_source`) and
`uedctl/classindex.py` (the `class list` placeable filter). See `package-format.md` for the header/
name/import/export table layout these build on.

All facts here were **live-verified 2026-07-17** against the real Deus Ex `Engine.u` (89 classes),
`DeusEx.u` (1158), and `DeusExDeco.u` (5). Confidence: ✅ (uedctl-used / live-verified) unless noted.

> **Cache-version note.** These layouts feed the persistent package-schema cache (`schema_cache.py`,
> `architecture.md` "Package schema cache"). Any change to the documented UClass-tail / UProperty /
> TextBuffer layout — or to what the discovery decoders (`iter_classes`, `class_index_map`,
> `super_fqcn_by_index`, `class_is_abstract`, `own_class_properties`) emit — **MUST bump
> `schema_cache.SCHEMA_CACHE_VERSION`** (and refresh the committed frozen-golden bundle
> `tests/fixtures/schema_golden_fire_v1.marshal`), or a post-upgrade uedctl will read stale,
> wrongly-shaped cache entries an older build wrote. The `test_schema_cache.py` frozen-golden guard
> trips red to force this. When it trips on a REAL decoder change, the correct remedy is to **bump the
> version** (making already-written on-disk entries unreachable); refreshing the golden blob ALONE
> silences the test but leaves any deployed cache serving stale, wrongly-shaped entries.

## Abstractness: read the SOURCE, not `ClassFlags`

A class's `abstract` modifier is the `CLASS_Abstract` bit (bit 0) of the UClass `ClassFlags` DWORD.
But `ClassFlags` is **not reliably reachable by an offline byte-seek**:

- The UClass body is `UField(SuperField, Next)` → `UStruct(ScriptText, Children, FriendlyName, Line,
  TextPos, ScriptSize, <script bytecode>)` → `UState(...)` → `UClass(ClassFlags, ...)`. Everything
  before `ScriptSize` is **variable-length compact indices**, so a constant offset to `ClassFlags`
  is only coincidentally right for low-index classes.
- Worse, the **on-disk UnrealScript bytecode length ≠ the stored `ScriptSize`** (which is the
  in-memory size). The bytecode is serialized token-by-token with no stored on-disk byte count, so
  you cannot skip it to reach the trailing `ClassFlags` without a full `SerializeExpr` token walker
  (~60 opcodes). 🔬 Confirmed: naively skipping `ScriptSize` bytes lands in garbage (e.g. `Pawn` →
  `0xff6a7900`). `ClassFlags` IS cleanly readable for a **script-free** class (`ScriptSize == 0`,
  e.g. `Light`/`Brush` = `0x32`, `Info`/`Keypoint`/`Decoration` = `0x33`), but that's the minority.

**So uedctl reads the class's shipped `.uc` SOURCE instead** — uniform across all classes, no
bytecode walker. Every DX class ships its source in a `TextBuffer` referenced by `UStruct.ScriptText`
(89/89, 1158/1158, 5/5 — ✅). Parse the class declaration for the `abstract` keyword:
`abstract_from_source` strips `//` and `/* */` comments FIRST (a `;` inside a comment must not
truncate the declaration), matches `\bclass\b(.*?);` DOTALL (declarations are routinely multi-line,
e.g. `class Pawn extends Actor\n\tabstract\n\tnative;`), and tests `\babstract\b` (word-boundary — a
class or parent whose NAME contains "abstract", like `AbstractFoo`, must not match). `CLASS_Abstract`
is **per-class-declared, not inherited** (`Actor` abstract, its concrete subclass `Light` not), so
reading the class's OWN declaration is correct — there is no "abstract via an abstract super" case.

A class with no shipped source (a future source-stripped substrate) yields `None`, which the
placeable filter treats as **placeable** (fail-open: list a maybe-unplaceable class rather than hide
a placeable one). DX always ships source, so `None` is a forward-compat concession only.

## TextBuffer body layout (the `ScriptText` object)

To read the source, resolve `UStruct.ScriptText` (the 3rd compact in the UClass body, after the two
UField refs) to its export, confirm it is class `TextBuffer`, and decode its body:

```
[UObject tagged-property list: here just the terminating "None" name index — 1 compact]
Pos   : u32
Top   : u32
Text  : FString   (compact length, then `length` latin-1 bytes, NUL-terminated within)
```

✅ **The leading `None` terminator is easy to miss** — every UObject serializes its tagged-property
list (for a TextBuffer, which has no UProperties, that is just the "None" name ref = 1 compact)
BEFORE the native `Pos/Top/Text`. Decode straight from `Pos` and you land 1 byte short → garbage.
With the `None` skip, the FString length lands **exactly at `soff + ssize`** — a free integrity
check `_class_script_source` asserts (a mismatch ⇒ our layout read is wrong ⇒ return `None` rather
than hand back garbage). For abstractness only the declaration head is needed, so the decoder caps at
16 KB (with a full-source fallback if no `class … ;` is found in the head).

## UProperty body layout — and the editor Category (`var(Category)`)

✅ **RE'd byte-exact 2026-07-18** by two independent methods that agree perfectly: (1) an empirical
decode that consumes to `soff+ssize` for all 18,316 property exports across Engine/Core/DeusEx with
zero desync, and (2) disassembly of `UProperty::Serialize` @ `0x10164fd0` in `DX/System/Core.dll`
(base `0x10100000`). A serialized `UProperty` export body (a `UProperty` is a `UField` is a
`UObject`, base-most `Serialize` first) is:

```
[UObject tagged-prop-list terminator: FName compact — always 0 ("None")]
[UField.SuperField: object compact]  [UField.Next: object compact]
[UProperty.ArrayDim: u32]  [UProperty.PropertyFlags: u32]
[UProperty.Category: FName compact]                     ← the editor group
[UProperty.RepOffset: u16]   — ONLY if PropertyFlags & CPF_Net (0x20)
[subclass type tail: object compact ref(s)]  — Enum / PropertyClass / Struct / Inner;
                                                ClassProperty has TWO (PropertyClass + MetaClass)
```

`ElementSize` is **not** serialized (relinked at load). Fields are variable-width compacts, so the
Category is NOT at a fixed byte offset — parse sequentially (3 compacts, two u32s, then the Category
compact). `Category` is a name-table index: `0` = `"None"` (no editor group); otherwise
`pkg.names[idx]`.

**The `var()` class-name default is written on disk, not applied at load.** An editable property with
no explicit category (`var() Type P;`) stores its **declaring class name** as the Category
(`Engine.Brush.CsgOper` → `Brush`, `Engine.Mover.KeyNum` → `Mover`). An explicit `var(Group)` stores
`Group` (`Actor.Mass` → `Movement`, `Actor.LightType` → `Lighting`, `Actor.CollisionRadius` →
`Collision`, `Actor.Mesh` → `Display`). A non-editable `var` stores `None`. Categories are abundant:
**633 in Engine.u, 534 in DeusEx.u, 20 in Core.u**. (The claim "DX has no categories" was a decode
bug — see below.)

**The old decode bug (fixed 2026-07-18):** `_decode_property` read the FIRST compact (the always-`0`
`None` terminator) AS "category", then mis-offset the header — so `property_flags` was garbage for
every property (it read the Super/Next region) and `array_dim` was wrong for any static array whose
size didn't survive the `(combined>>16)&0xFF` hack (`Touching[4]`, `PRIArray[32]`, `BlendTweenRate[4]`
all read as `1`). No test caught it because `property_flags` had no asserting consumer and the pinned
array cases (`KeyPos[8]`) happened to fall in the byte the hack read. The correct layout fixes all
three; `Prop` now carries `category`. Reusable disasm harness:
`dev/docs/spikes/2026-07-15-native-materialize/harness/pe.py`.

## Class enumeration

`iter_classes(pkg)` = every export whose own class-type resolves to `Class` (or the root `Object`,
whose class-ref is 0/None). Header-only — the export table only, no property decode. `class_index_map`
gives an O(1) `casefold(name) → 1-based export index` map that replaces repeated linear
`class_export_index` scans in the ancestry walk (the placeable list walks every class's super chain).

## UClass body: full layout, the script walker, and the DEFAULTS block ✅

✅ **RE'd + corpus-verified 2026-07-18** (uedctl-used: `uprops.class_default_tags` / `_walk_expr`;
validated by exact-EOF landing on **1914/1914 classes** across every v68+ `.u` in the DX install —
integration test `test_uprops_defaults.py`; consumed live by `actor prop get`'s default fallback).

The full UClass export body (v68/v69):

```
[UField.SuperField: compact] [UField.Next: compact]        ← NO leading None terminator (below)
[UStruct: ScriptText: compact] [Children: compact] [FriendlyName: name compact]
[Line: u32] [TextPos: u32] [ScriptSize: u32] [script bytecode …]
[UState: ProbeMask: u64] [IgnoreMask: u64] [LabelTableOffset: u16] [StateFlags: u32]
[UClass: ClassFlags: u32] [ClassGuid: 16 bytes]
[Dependencies: TArray{Class: compact, Deep: u32, ScriptTextCRC: u32}]
[PackageImports: TArray{name compact}]
[ClassWithin: compact] [ClassConfigName: name compact]     ← v>=62
[DEFAULTS: tagged-property list, "None"-terminated]        ← must land EXACTLY at soff+ssize
```

- **UClass objects skip the leading UObject tagged-property "None" terminator** that every other
  export starts with (`UProperty`/`TextBuffer`/`Struct` bodies DO start with it): for a UClass the
  object's own properties ARE the class defaults, serialized at the TAIL instead. This is why
  `_class_script_source` reads `[SuperField][Next][ScriptText]` straight from `soff` and why the
  defaults sit last.
- **The script walker.** The bytecode has no on-disk byte length: `ScriptSize` counts the
  IN-MEMORY stream, and FNames/object refs are compacts on disk but 4 bytes in memory — so the
  only way past the script is REPLAYING `UStruct::SerializeExpr` token-by-token, tracking disk and
  memory cursors separately (`uprops._walk_expr`: the v68 opcode set — variables/jumps/cases/
  constants/contexts/iterators/conversions 0x39–0x5F, native calls ≥0x60 with the 2-byte extended
  form 0x60–0x6F, function calls consuming args to `EX_EndFunctionParms` 0x16). An unknown opcode
  or any desync raises `SchemaError` (no-fallback); a CLASS's own script is small (replication
  conditions), so the exercised subset is modest and the corpus gate is decisive.
- **The DEFAULTS block is a sparse diff against the SUPER's defaults** (`Engine.Light` re-states
  only what it changes vs `Actor`; a prop absent in the whole chain is the type's ZERO). Effective
  defaults = overlay every ancestor's block root→leaf (`uprops.resolve_class_defaults`).
- **In-struct binary value encodings** (`UStructProperty` tag values — member-wise `SerializeBin`
  in Children-chain declaration order, super-struct members first): Byte 1 B; Int/Float 4 B;
  Object/Class/Name compacts (against the TAG's package tables); Str an FString; **Bool ONE byte**
  (0/1); nested structs recurse; member static arrays repeat `array_dim` times. All validated by
  the exact-consume check (a wrong size desyncs loudly). Struct member lists come from the
  `Struct` export's `Children` linked list (`uprops.struct_members`) — the EXPORT-TABLE order is
  not reliable, the chain order is the binary layout order.
- **Negative fact:** the shipped v68 ScriptText contains NO `defaultproperties` block (the source
  ends at the `#exec` directives; live-verified 2026-07-18 across Engine/DeusEx classes) — class
  defaults exist ONLY in this binary tail, so a textual route was never viable.
- Value rendering to T3D-form text (enum names incl. cross-package resolution, object refs
  qualified via the outer chain, trimmed floats) is pinned by fixtures: `Engine.Light`
  `LightPeriod=32` / `LightType=LT_Steady` / `Texture=Texture'Engine.S_Light'`;
  `DeusEx.Greasel` `InitialAlliances(0)=(AllianceName=Karkian,AllianceLevel=1,bPermanent=True)`.
- Side effect: `ClassFlags` is now reachable exactly (post-walker), so abstractness COULD read the
  real `CLASS_Abstract` bit; the source-regex route above remains what `classindex` uses today.
