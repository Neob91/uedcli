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

## ProbeMask (EProbe table, RE'd 2026-09-12)
`ProbeMask`/`IgnoreMask` (the first two UState fields in a UClass body) gate whether native code calls
into script for a fixed set of ~48 "probe" events (Tick, Timer, Touch, Trigger, …) without the
overhead of a virtual dispatch when no override exists anywhere in the ancestry. The bit table is
recovered from the boot-registered `EName` ordinals (`global_index.py`'s dumped table): probe function
names occupy consecutive ordinals starting at `Spawned`=217; an unused slot registers a literal
`ProbeN` placeholder instead of a real name, where N is exactly its own bit index (`Probe34`@251 =
251-217 = bit 34 — every gap self-confirms the offset). Full table + the bit-computation helper:
`uedcli/uscript/compile.py` `_EPROBE_TABLE`/`_probe_bits`. `ProbeMask` **accumulates through
inheritance**: `ProbeMask(class) = ProbeMask(super) | bits for this class's own probe-named
functions`. `IgnoreMask` stays all-ones absent state `ignores` blocks (not yet implemented).
Cross-checked against two measured facts plus a live UCC compile:
`UnrealShare.UnrealTestInfo` overriding only `Tick` → `ProbeMask=0x1000000000` = bit 36 = `Tick`@253;
`Engine.Pawn`'s real mask (`0xf8040c02`) decodes to `Destroyed/Falling/Landed/BaseChange/
EncroachingOn/EncroachedBy/FootZoneChange/HeadZoneChange/PainTimer` — all plausible Pawn overrides;
`UnrealShare` itself now byte-exact via `gate()` against a fresh UCC build (see `USCRIPT-COMPILER.md`).

## UState label tables (RE'd 2026-09-13, live UED22 compiles)

A `state Foo { Label: ... }` body's compiled script ends with an `EX_LabelTable` (opcode `0x0C`)
token: a run of `(FName label, u32 iCode)` pairs in REVERSE source declaration order (the same
"last declared, first" convention as the class `Children` chain), terminated by `(NAME_None,
0x0000FFFF)` — confirmed live, token-exact vs UCC on a 2-label case, and already matches
`bytecode.py`'s decode/encode (no codec change needed). `iCode` is the DISK byte offset of the
label's first token within the state's own script stream (`Begin` at offset 0 when it's the first
label). `UState`'s tail after the script is `[ProbeMask u64][IgnoreMask u64][LabelTableOffset
u16][StateFlags u32]`; `LabelTableOffset` is the disk byte offset of the `0x0C` token within the
state's own script bytes (always equal to the script's total length minus the label table's own
encoded size). Implemented in `lower.py`'s `lower_state_body`/`_label_table_tok`.

### `EX_Nothing` padding before the label table — SOLVED

UCC always appends a compiler-synthesized `EX_Stop` after the state's real code, then a variable
number of `EX_Nothing` (`0x0B`) padding tokens before the label table (present only when the state
declares a label at all). Formula, confirmed on 13 controlled one-state compiles
(`_scratch/state_probe*.py`) plus 3 full end-to-end byte-exact package compiles:

    pad = (N_gotostate_or_finishanim_calls - N_explicit_stop_statements + 2) % 4

`N_explicit_stop_statements` counts the bare `Stop;` KEYWORD statement (not a function call — it
lowers to its own `EX_Stop`, distinct from the compiler's trailing one), which SUBTRACTS from the
count, opposite-signed to the two natives:

| State body (single label `Begin` unless noted) | GotoState/FinishAnim | explicit `Stop;` | Nothing count |
|---|---|---|---|
| empty | 0 | 0 | 2 |
| `Sleep(1.0);` (×1 or ×3) | 0 | 0 | 2 |
| `Sleep(1.0); GotoState('');` (1 or 2 labels) | 1 | 0 | 3 |
| `GotoState('');` alone | 1 | 0 | 3 |
| `GotoState(''); GotoState('');` | 2 | 0 | 0 |
| `FinishAnim();` alone | 1 | 0 | 3 |
| `Stop;` alone | 0 | 1 | 1 |
| `Stop; Stop;` | 0 | 2 | 0 |
| `GotoState(''); Stop;` | 1 | 1 | 2 |

The MECHANISM (why exactly these three constructs, and why `Stop;` is opposite-signed) is not
understood — this is an empirical formula, not a derivation from source. Implemented as
`_NOTHING_PAD_NATIVES`/the `explicit_stops` count in `lower.py`'s `lower_state_body`; pinned by
`test_uscript_states.py::test_state_nothing_padding_formula` (offline, no docker) and by
`test_state_and_foreach_strict_byte_exact` (a full `Trigger`→`GotoState`→state-with-`Sleep`
class, byte-exact end to end).

## `foreach` / `EX_Iterator` (RE'd 2026-09-13, live UED22 compile)

`foreach <IteratorCall>(...) { ... }` lowers to: `EX_Iterator(call, u16 end_offset)`, the loop
body, `EX_IteratorNext` (`0x31`), `EX_IteratorPop` (`0x30`) — `<IteratorCall>` (e.g. `AllActors`) is
lowered exactly like any other call (no special bytecode form of its own). `end_offset` points at
`IteratorPop` itself, NOT past it: both `break` and an empty first `Next` still execute `Pop` to
release the iterator, they only skip the body and the `Next` attempt. `continue` jumps to
`IteratorNext` (the runtime remembers the loop's own start position per nested iterator, so neither
opcode carries an explicit "jump back" operand). Implemented in `lower.py`'s `_st_foreach`/`_Body.
iterator`; verified byte-exact against a fresh UCC build of `AllActors(class'Inventory', Inv) {
Inv.Destroy(); }`.

## Cross-class `Dependency` entries (RE'd 2026-09-13, live UED22 compiles)

A UClass body's `Dependencies` array is NOT always just `[self, super]`. Calling a member
function (or accessing a member) THROUGH an object typed to a class other than self or the
immediate super — `p.Destroy()` where `local Pawn p` — adds one more `Dependency` entry per
DISTINCT such class, `deep=0` (vs `deep=1` for self/super), in first-Context-use order across the
whole class (all functions, in declaration order). Merely declaring a local/param of that type, or
using a `class'X'` literal without a member access through it, does NOT add an entry — confirmed by
4 controlled compiles isolating each case. Implemented via `lower.py`'s `_record_dep`/`_context`
(populates a `extra_deps` list threaded through `compile.py`'s `_Build`), consumed when building
each class's `Dependencies` tuple in `_class_export`/`_multi_class_export`.

`Sleep` and `FinishAnim` share identical `FunctionFlags` (`0x409`, both `FUNC_LATENT`) yet give 2 vs 3;
`GotoState` is NOT latent (`0x401`) yet also gives 3; two `GotoState` calls give 0. This rules out
"one Nothing per latent call" and "one Nothing per statement" as the rule. Likely compiler-internal
(a two-pass jump-backpatch reservation in UCC's own statement compiler, not something a runtime
SavePackage dump can reveal — this needs UCC.exe's own `CompileStatement`/state-compiling code
disassembled, a different kind of RE than the SavePackage-ordering dump). Do not guess/fit a table for
this — it would violate the "reproduce, don't hack" rule. Blocks byte-exact state-block compilation
until solved.
