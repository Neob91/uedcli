# Spike: decoding `UProperty` typed bodies offline (typed / enum / array-bounds validation)

**Date:** 2026-06-26 · **Status:** RESOLVED — all three (typed, enum-values, array-bounds) are
feasible offline and reliable; v1-scope recommendation below.
**Question:** Can uedcli extend its offline class-property extraction from **name-only**
validation to **typed / enum / array-bounds** validation — by decoding each property's
`UProperty` serial body out of a `.u` package's export table, with NO wine/editor? This is the
follow-on deferred by `2026-06-26-class-property-extraction.md` ("Defer array-bounds + typed/enum
validation … live in the `UProperty` serial body … a later upgrade, not a redesign").

**Answer: yes — all three.** The type reference (enum / class / struct / meta-class / array
inner), the enum's ordered value-name list, and the static-array dimension are each recoverable in
pure Python from the `UProperty` (and `UEnum`) serial bodies. Proven against **14,193 class-member
properties across all 49 substrate+install packages (v68 & v69), zero failures**, with a worked
example below
(`Brush.CsgOper → ECsgOper → [CSG_Active, CSG_Add, CSG_Subtract, CSG_Intersect, CSG_Deintersect]`).
(The decoder *runs* on 35,004 `*Property` records total; 14,193 are real class members — the rest
are function parameters/locals, which the schema validator filters out, see "Reliability".)

> Reader with NO prior context: a `.u` file is an Unreal package. Its **export table** lists
> every object the package defines; the name-only spike established that a class's *properties* are
> the export records whose `Outer` is the class and whose own type is one of 11 `*Property`
> classes. Each such export also has a **serial body** (a byte range at the export's
> `SerialOffset`/`SerialSize`) holding that property's typed details. This spike decodes that body.
> "Compact index" = UE1's signed variable-length integer (`dxpkg._read_compact_index`); an "object
> reference" is a compact index where 0=None, positive=an export (idx−1), negative=an import
> (−idx−1) resolved through the import table. All offsets below are byte offsets from the start of
> a body.

---

## Method

Pure-offline byte parsing of the corpus, reusing the production compact-index primitive
(`uedcli.dxpkg._read_compact_index`) and the export-table reader proven by the name-only spike. No
wine, no editor, no container. The harness is committed alongside this doc
(`harness/uproperty_decode.py` + `harness/validate_corpus.py`); the latter validates the whole
corpus. The layout below was reverse-engineered by hex-dumping real bodies and confirmed by the
**cursor-lands-at-EOF** integrity check (a layout error desyncs and misses the body/EOF boundary)
plus an independent structural-vs-last-compact cross-check.

Corpus: `uned/UED22/*.u` (32 files, v69 substrate) + `uned/DeusExAssets/System/*.u` (17 files, v68
install, gitignored).

---

## The `UProperty` serial body layout (✅ verified, v68 & v69 identical)

A property export's body, from its first byte:

```
category : compact-index   the var's var(Category) FName index. For an uncategorized var it is
                           `None` — but `None` is NOT always name-index 0 / 1 byte: a package's
                           name table can hold a `None` entry at a >63 index (e.g. core.u at
                           362 -> bytes `6a 05`), so this compact is 1 OR 2 bytes wide. It MUST
                           be READ as a compact, not assumed to be a fixed `00`.
0x00                       one pad/separator byte.
combined : uint32          a PACKED dword (little-endian), at the offset AFTER category+pad:
                             bits  0-15  low PropertyFlags  (CPF_* — the bits we care about)
                             bits 16-23  ArrayDim           (ONE byte, max 255; 0 ⇒ scalar)
                             bits 24-31  high PropertyFlags
<per-kind middle>          ElementSize / RepOffset — widths vary by kind/flags; NOT needed for the
                           typed decode and not pinned to one uniform grammar (see "Honest limits").
type_ref : compact-index   the LAST compact index of the body = the type-specific tail object
                           reference, for the typed kinds (0 == None).
```

**Three load-bearing facts** (all initially got me wrong layouts; all verified against real bytes):

1. **The body starts with the `var(Category)` FName compact — read it, don't hardcode `combined`
   at offset 2.** An earlier draft hardcoded `combined @ offset 2`, which is right only when the
   category compact is exactly 1 byte (`Engine.u`, where `None` is name-index 0). It is WRONG for
   the 5,222 corpus bodies (e.g. all of `core.u`) whose `None` category sits at a ≥64 name index
   and so encodes in 2 bytes — there `combined` is at offset 3, and offset-2 reads a PropertyFlags
   byte as ArrayDim (e.g. `core.Object.Outer`, a scalar, mis-read as a 9-element array). The
   decoder reads `category` as a compact, skips the pad byte, then reads `combined`. (1,000 corpus
   array-dims change between the two reads; the structural read is the correct one.)
2. **`array_dim = (combined >> 16) & 0xFF`.** The `& 0xFF` mask is essential. A naive `combined >>
   16` folds the bits-24-31 PropertyFlags into the dimension and yields nonsense (e.g. a scalar
   `ObjectProperty` whose `combined` has byte-3 flag bits reads as ArrayDim 257). Masking to one
   byte gives the true dim: `Actor.MultiSkins[8]`, `Mover.KeyPos[8]`/`KeyRot[8]`,
   `ipdrv.B[255]`, `DeusEx.PendingCommands[100]`, `DeusEx.invSlots[30]`. A scalar's byte is 0 and
   is reported as 1 (UE1 doesn't serialize ArrayDim=1 distinctly). Max dim is 255 — the one-byte
   field is UE1's array-dim ceiling, so a larger real array cannot exist and be silently truncated.
3. **The type ref is the body's FINAL compact index.** Rather than fully parse the variable middle,
   read compacts from after `combined` to EOF and keep the last — it is reliably the type-specific
   tail. Independently corroborated corpus-wide (`crosscheck_typeref.py`): all 12,981 non-None type
   refs land on an object of the property-appropriate class (Byte→Enum, Object/Class→Class,
   Struct→Struct, Array→a `*Property`), **zero wrong-class targets**.

### Per-kind type tail (✅ verified)

| Kind | `type_ref` resolves to | Notes |
|---|---|---|
| `ByteProperty` | the **`Enum` object** (the enum type), or **None** | None ⇒ a plain `byte`, not an enum. THIS enables enum-value validation. The enum may be a cross-package import (see below). |
| `ObjectProperty` | the referenced object **class** (`Texture`, `Mesh`, `Pawn`, …) | cross-package via the import table (negative ref) |
| `ClassProperty` | the **meta-class** (last of two refs: `Class`, then the meta-class) | |
| `StructProperty` | the referenced **`Struct`** (`Vector`, `Rotator`, `PointRegion`, …) | |
| `ArrayProperty` | the **inner property export** — NOT the element type | the last compact is the inner `*Property`'s export; decode THAT and read its `type_ref` for the element type (one extra indirection — `element_type_ref`/`element_type_name`). e.g. `loadedSaveInfoPointers → (inner) → DeusExSaveInfo`. Dynamic array; rare in level data. |
| `Int/Float/Str/Name/Bool/Pointer` | **None** | no type ref (BoolProperty packs a bitmask; the others are scalar) |

**Cross-package enums.** A `ByteProperty`'s enum ref can be an *import* (negative ref): the enum is
defined in another package, so its value list is NOT in this package's bytes. `enum_values()`
decodes a LOCAL enum; `enum_values_for_type_ref()` detects an import and returns which package to
load. In the corpus, of 795 enum-typed ByteProperties (all packages, incl. function members),
the schema validator's class-member subset has 287 local enums + 21 cross-package import enums. To
validate `--set` against an imported enum, the schema builder must open that package and decode the
enum there — the same cross-package walk class-property *inheritance* already does via the import
table; not a new mechanism, but a real step the validator must take (flagged, not a blocker).

### Enum body (`UEnum::Serialize`) — byte-exact, lands at EOF (✅)

A `ByteProperty`'s enum ref points at a `UEnum` export whose body is:

```
None(compact)  Next(compact)  <one skipped compact>  Count(compact)  Count × Name(compact)
```

The `Count` names are the ordered enum tags. Decodes to **exactly EOF** for every enum in the
corpus (the integrity check). The single skipped compact between `Next` and `Count` is an unused
field (its meaning wasn't needed); skipping it lands every enum exactly, so it is structurally
benign.

---

## Worked example (real bytes from `uned/UED22/Engine.u`, v69)

`Brush.CsgOper` — the headline use case (`actor prop --set CsgOper=CSG_Subtract`), real bytes from
`uned/UED22/Engine.u`:

- Export record: name `CsgOper`, type `ByteProperty`, `SerialSize=16`, body bytes
  `00 00 40 2f 01 00 00 00 01 00 00 00 43 02 45 2e`.
- `category` compact = `00` (`None`, 1 byte here), pad `00`, then
  `combined = 0x00012f40` → `array_dim = (0x00012f40 >> 16) & 0xFF = 1` (scalar), low flags
  `0x2f40`.
- `type_ref` (the body's last compact, `45 2e`) → the `ECsgOper` `Enum` export.
- Decoding the `ECsgOper` enum body →
  **`['CSG_Active', 'CSG_Add', 'CSG_Subtract', 'CSG_Intersect', 'CSG_Deintersect']`** — cursor
  lands at EOF.

So `--set CsgOper=CSG_Subtract` is validatable: `CSG_Subtract` ∈ the legal tag set. Two more, end to
end from the corpus:

- `Actor.Physics : ByteProperty → EPhysics =
  [PHYS_None, PHYS_Walking, PHYS_Falling, PHYS_Swimming, PHYS_Flying, PHYS_Rotating,
   PHYS_Projectile, PHYS_Rolling, PHYS_Interpolating, PHYS_MovingBrush, PHYS_Spider, PHYS_Trailer]`
- `Actor.MultiSkins[8] : ObjectProperty → Texture` (static array, dim 8) — and
  `Mover.KeyPos[8] : StructProperty → Vector`, `Mover.KeyRot[8] : StructProperty → Rotator`,
  `Mover.NumKeys : ByteProperty → None` (plain byte). These are the mover-keyframe arrays the
  array-bounds check would gate (`KeyPos(N)` with `N < 8`).

---

## Reliability (no sampling — the whole corpus)

`harness/validate_corpus.py` (counts only real CLASS-MEMBER properties — Outer is a UClass; a
`*Property` whose Outer is a Function/State is a param/local, never a static array, and is excluded
so it can't inflate the array-dim stats), run 2026-06-26:

- **14,193 class-member properties decoded across all 49 packages** (32 v69 substrate + 17 v68
  install). For each: `array_dim`, low `property_flags`, and `type_ref`. **0 decode failures, 0
  dangling type refs, 0 empty local enums.** (The decoder runs cleanly on all 35,004 `*Property`
  records including function members; the validator reports the 14,193 schema-relevant ones.)
- **287 class-member properties typed by a LOCAL enum** — every one's `Enum` body decoded
  **byte-exact (cursor at EOF)** into a non-empty, plausible tag list (e.g. `EAttitude`,
  `EAugmentationLocation`, `EMusicMode`, `ESeekType`, `EBrushType`, `ECameraCommand`). A further
  **21 class-member properties use a cross-package import enum** (counted separately — the enum is
  in another package the validator must load to get its tags). Across ALL `*Property` records
  (incl. function members), 795 are enum-typed and all 795 type refs land on an `Enum`.
- **`array_dim` distribution is sane (1..255)** after the category-aware read + `& 0xFF` mask:
  13,720 scalars and a tail of real arrays, every large value a genuine buffer — `DeusEx.u`'s
  `Particles[64]`, `Pawns[32]`, `invSlots[30]`, `augClasses[25]`, `PendingCommands[100]`,
  `Engine.u`'s `MsgText[64]`, and the 4 `B[255]` byte buffers.
- **The decode *mechanism* is version-agnostic; the *schemas* are not.** v68 and v69 use the
  identical body layout (the only version branch is the name-table read already in `dxpkg`), so the
  decoder runs unchanged on both. But the SAME class differs between the v68 install and the v69
  substrate (e.g. `Engine.Actor` 210 vs 192 own props; `DeusEx.DeusExPlayer` 127 vs 223; casing
  splits like `OldRot`/`oldRot`) — so WHICH package you parse is load-bearing. Per `decisions.md`
  2026-06-26 14:10 UTC the validator parses the **game's real `.u`**, not the editor's UT-lineage
  substrate or stubs; this spike's "identical" claim is about the decoder, not the schema source.
- **Cross-package type refs resolve** via the import table (negative refs): `DeusEx.u`'s
  `Texture → Texture`, `TestEnemy → Pawn`, `BestActor → Actor`, `ConListItems → Object`.
- **Independent cross-check (`harness/crosscheck_typeref.py`, committed):** a whole-corpus
  target-KIND audit — every typed property's last-compact type ref must resolve to an object of the
  class the property demands. Result: **12,981 non-None type refs checked, 0 land on the wrong
  class** (ByteProperty→Enum ×795, ObjectProperty→Class ×8431, ClassProperty→Class ×372,
  StructProperty→Struct ×3355, ArrayProperty→a `*Property` ×28). This second, independent decode
  path corroborates the last-compact method with no assumed middle grammar.

---

## Honest limits

- **The variable middle region (ElementSize / RepOffset, after `combined`) was NOT pinned to one
  uniform grammar.** Its field widths vary by kind and by `CPF_Net`, and no single forward grammar
  made all `Actor` properties land at EOF. **This does not affect the deliverables** — `array_dim`
  comes from the `combined` dword (read at the offset AFTER the category compact + pad byte), and
  `type_ref` from reading the body's *last* compact; neither needs the middle parsed. If a future
  need arises for `RepOffset`, the middle would need more reverse-engineering.
- **Cross-package import enums need the defining package loaded.** ~21 class-member ByteProperties
  point their enum at an import; their tag list isn't in this package's bytes (the spike resolves
  the owning package name but cannot decode the body without opening it). The validator's schema
  builder must walk that import — the same cross-package step class-property inheritance already
  takes — to validate `--set` against such an enum.
- **`array_dim` cannot distinguish a true scalar from `Foo[1]`** (both serialize dim 0→reported 1).
  Harmless for bounds-checking: `Foo(0)` passes (`0 < 1`, the only valid index) and `Foo(1+)` is
  correctly rejected.
- **`PropertyFlags` is only decoded in its low 16 bits.** The high bits exist on disk (bits 24-31 of
  `combined`) but the validation use cases need none of them; the `& 0xFF` mask isolates ArrayDim
  from the bits-24-31 flags cleanly.
- **`ssize == 0` is rejected, not assumed.** A property with an empty serial body cannot be decoded
  and raises (the no-fallback contract). No such property exists in the corpus, but the guard is
  there rather than silently reading header bytes.
- **No kind's body is undecodable.** All 11 `*Property` kinds decode their (absent or present) type
  ref; `BoolProperty`/`Int`/`Float`/`Str`/`Name`/`Pointer` correctly report no type ref.
- **`ByteProperty → None` is meaningful, not a gap:** ~unlit/sound/light byte scalars
  (`LightBrightness`, `AmbientGlow`, …) are plain bytes with no enum; the decoder returns None and
  an enum-value check simply doesn't apply (any 0-255 byte is legal).

---

## v1 scope recommendation

Ranked cheap-and-reliable → fiddly:

1. **Type validation — CHEAP & RELIABLE. Recommend for v1.** Each property's value type
   (`Int`/`Float`/`Str`/`Name`/`Bool`/`Byte`/enum/object/struct/class) is decoded for free alongside
   the name (the export already gives the kind; the body gives the referenced type). A `--set
   KEY=VALUE` can check the value's *shape* against the kind (e.g. an int property rejects
   `foo`; a struct property expects `(X=..,Y=..)`).
2. **Enum-value validation — CHEAP & RELIABLE for LOCAL enums; one extra step for imported ones.
   Recommend for v1.** This is the highest-value addition: local enum bodies decode byte-exact
   (287/287 class-member local enums), directly enabling `--set CsgOper=CSG_Subtract` (and
   `Physics`, `DrawType`, `Style`, `LightType`, `LightEffect`, the mover
   `MoverGlideType`/`MoverEncroachType`, every DeusEx `E*` enum) to ERROR on an illegal tag and
   normalize tag casing to the canonical spelling (FName-insensitive, like the property-name
   normalization in the 2026-06-26 12:41 decision). The ~21 class-member properties whose enum is a
   cross-package import need the validator to open the defining package (it already walks imports
   for class inheritance) — a real but small extra step, not a blocker.
3. **Array-bounds validation (`Foo(N)` with `N < ArrayDim`) — RELIABLE, recommend for v1.**
   `array_dim` decodes correctly corpus-wide via the category-aware read + `(combined>>16)&0xFF`.
   One harmless subtlety: a true scalar and `Foo[1]` both report dim 1, so the bounds check can't
   *distinguish* them — but `Foo(0)` on a scalar is benign (the only valid index) and `Foo(1+)` is
   correctly rejected, so `N < array_dim` is sound.

**Recommended validation scope to add on top of name-only:** all three. Concretely, extend the
class-property catalog entry (today: name) to carry `(kind, type_ref_name, array_dim)`; then:
`actor prop`/`actor build --prop` (a) reject an unknown property name (existing), (b) for an enum
ByteProperty, reject a value not in the enum tag set and normalize its casing, (c) for an indexed
key `Foo(N)`, reject `N ≥ array_dim`. Type-shape checking (1) is a nice-to-have that can land in the
same pass since the kind is already in hand.

This stays within the no-fallback contract (`decisions.md` 2026-06-26 12:41 UTC): an unknown
enum value / out-of-bounds index is a hard ERROR, no opaque-accept. It reads the **game's real
`.u`** (not the stub cache — `decisions.md` 2026-06-26 14:10 UTC); the enum/type/dim live in the
same packages the name validation already parses, so no new search path.

---

## Verdict

Feasible and reliable, fully offline. **Typed and (local) enum-value validation are cheap and
rock-solid** (type ref = the body's last compact, 0 wrong-class targets over 12,981 refs; local
enum bodies decode byte-exact, 287/287 class-member + 795/795 over all records); **array-bounds is
also reliable** once the `combined` dword is read AFTER the variable-width category compact and
ArrayDim masked to its one byte (`(combined>>16)&0xFF`) — the two non-obvious gotchas, both fixed
and validated. 14,193 class-member properties (35,004 total records) across 49 v68+v69 packages
decode with zero failures. The two remaining caveats are bounded and non-blocking: cross-package
import enums need the owning package loaded (~21 cases), and the body's variable middle
(ElementSize/RepOffset) is unpinned but unneeded. **Ready to fold into the property-validation spec
as confirmed scope** (type + enum + array-bounds on top of name-only), reusing the committed harness.

## Refs

- Grounding: `2026-06-26-class-property-extraction.md` (name-only export-table reader; the 11-type
  closed set; cursor-to-EOF integrity check), `decisions.md` 2026-06-26 12:41 UTC (no-fallback,
  error-not-accept, normalize-casing) + 2026-06-26 14:10 UTC (parse the game's real `.u`, not
  stubs).
- Production primitives reused: `uedcli/dxpkg.py` (`_read_compact_index`, header/name/import/export
  parsing).
- Harness (committed): `harness/uproperty_decode.py` (the decoder — `load_package`,
  `decode_property`, `enum_values`, `enum_values_for_type_ref`, `class_properties`),
  `harness/validate_corpus.py` (whole-corpus validation, class-member filtered),
  `harness/crosscheck_typeref.py` (independent target-kind audit of the last-compact type ref).
