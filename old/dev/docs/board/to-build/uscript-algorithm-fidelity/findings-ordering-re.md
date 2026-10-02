# Ordering RE findings (2026-09-05) — what's solved, what's the residual

Reusable tooling committed under `harness/`: `extract_ename.py` (per-substrate `core.dll` EName
extractor), `ename_ued22.json` (281 names), `refcount_{name,import}_model.py`.

## Solved (verified against goldens)
- **Intrinsic EName order** = the boot `REGISTER_NAME` sequence in `core.dll` (`None`@0, `ByteProperty`
  @1, … `Core`@16, `Engine`@17, `Editor`@18 (canonical case!), … `All`@280). NOT a pointer table —
  recovered from the registration routine's `push` order. Gives canonical FName CASE for intrinsics
  (fixes `env.py` file-stem casing).
- **Name refcount** (the `msvc_qsort` DESC key) = literal `<<FName` refs in EXPORT BODIES only: the
  tagged-prop `None` terminators, each `UProperty` `Category`, the `UClass` `FriendlyName`, the
  **own-package name in `PackageImports`** (why UscHello's class name counts 2), `ClassConfigName`
  (`System`), and a `defaultproperties` tag per own property + any name-typed value. Import/export
  NAMES are NOT counted. Reproduces the count TIERS of UscHello/UscVars/UscBB exactly.
- **Import refcount** = `<<UObject` refs (outer-chain recursion) + the correction that the tag pass
  counts the UClass export's REAL metaclass `Class` (on disk Class=0/None, but `Ar<<Class` still
  runs) — makes all counts consistent.
- **Export order** reproduces byte-exact from creation order + these counts.

## The residual — SOLVED by a runtime dump (2026-09-05)

The tie-break gather is simply **the global engine array in ASCENDING index** (nulls skipped),
qsort'd DESC by count. Disassembly of `SavePackage` (core.dll @0x277c0) confirmed:

- name gather @0x27ea0 iterates `GObjNames`  (Data@0x10139d50, Count@0x10139d54) by index, appends
  `i` where `FNameEntry->Flags(+4) & 0x10`; then `msvc_qsort` DESC by count.
- import gather @0x28020 iterates `GObjObjects` (Data@0x1013a260, Count@0x1013a264) by index,
  appends objects with the RF_Tag bit at `UObject->ObjectFlags(+0x1c)`; then `msvc_qsort` DESC.
- struct offsets: FNameEntry Index@+0, Flags@+4, string@+0xc (UTF-16LE); UObject Outer@+0x18,
  ObjectFlags@+0x1c, Name(FName idx)@+0x20, Class@+0x24.

So the order is a pure boot+load artifact. The EName-index guess failed only because it stopped at
the 281 intrinsics — UCC.exe also boots the Engine/Editor intrinsics and loads Core.u, so e.g. `Alpha`
is a Core.u name (global index 1394) and `Gamma` a pre-existing Editor config name (1573), not
package-own. **DUMPED** the real order under winedbg (`harness/dump_gobj.py`: plant INT3 at
SavePackage via a `set` memory write — winedbg's own `break` can't insert into core's code — then walk
both arrays; core.dll loads at fixed 0x10000000, no ASLR). Shipped as
`uedcli/uscript/data/{gobjnames,gobjobjects}_ued22.json`.

`harness/reproduce_from_dump.py` confirms the dump reproduces every fixture's NAME order (the
UscVars residual included) and IMPORT order (UscBB included) byte-exact. One `ordering.py` fix was
needed: `None` (FName index 0) stays IN the gather+qsort (not prepended) — its presence changes the
unstable qsort's permutation of count-tied names.

## Wired in
`global_index.default_global_index()` now loads the dumped JSON (casefolded) — the fitted
`OBJECT_ORDER`/`NAME_ORDER` are gone. The SCALAR autonomous path (UscHello/UscVars/UscBB) passes the
STRICT gate with no `order_override` (`test_uscript_compile.test_scalar_autonomous_byte_exact`), incl.
the name-typed default value (`Naym=Wobbl`) now spliced into the class gather.

## General path unified (2026-09-05)
`compile_package`/`compile_package_dir` now order autonomously via a TWO-PASS compile: emit
provisionally, decode the bodies back into their `<<FName`/`<<UObject` reference streams
(`uscript/reorder.py`), run `order_package` with the dumped global index + faithful qsort, re-emit in
that order. `_general_names`/`_multi_names` are gone as the source of truth (used only for the
provisional pass). FName case comes from the dumped pool (`global_index.pool_case`; fixes env stem
`editor`->`Editor` and member `a`->`A`). Export identity uses the full outer chain.

Key RE facts recovered: the UObject Children list is stored `[non-property fields reverse-decl] ++
[properties forward-decl]` (UE1 prepends); forward declaration = the property suffix as-is then the
non-property prefix reversed. NAME registration is two-pass (declarations incl. function params/
return, then function-body locals); OBJECT creation is children-inline. Both drive `order_package`.

STRICT gate PASS (no order_override): UscHello, UscVars, UscBB, **UscFn**.

## Residual — CONFIRMED: the `msvc_qsort` port diverges on large name arrays
UscW, FrameBuilder, DavesBrushBuilders, ExtendedBuilders, Fire reproduce imports + name-table
CONTENT + FName case, but the name-table PERMUTATION of the large count-tied own-new tier diverges
(`perm_gate` passes, `gate` does not). Root cause isolated with a runtime dump (2026-09-05):

- Dumped GObjNames DURING a UscW compile (INT3 at SavePackage). UscW's own-new names register in
  EXACTLY the order `reorder.name_creation_order` reconstructs (functions in decl order, params/
  locals interleaved) — so the gather is right.
- Fed that TRUE runtime gather + the golden's counts through `ordering.msvc_qsort`: it yields
  `CallFinal` at name index 10 where UCC's golden has `Bits`. So with a provably-correct gather and
  counts, the ported qsort produces a different permutation.

Narrowed further: the divergence is the equal-key PERMUTATION within a large count-tie run (UscW's
count-1 functions). A fresh, literal textbook `qsort.c` port gives the SAME result as `ordering.
msvc_qsort` and BOTH differ from UCC's golden at the same spot — so it is not a porting typo; UCC's
actual behavior differs from textbook modern-MSVC qsort on large equal-key runs. Two candidates, both
resolvable with the runtime dump (no fitting):

1. UCC's qsort @0x77cb0 has a subtle non-textbook difference in the equal-key gathering — re-port it
   instruction-by-instruction (the disasm is `0x77cb0`; partition 0x77f35-0x78058) and diff against
   the textbook port on the cached UscW ground truth.
2. The sort KEY differs: dump UCC's `NameIndices` count array (the qsort comparator reads it) during
   the compile and compare to `_reference_counts` — a count off-by-one on one count-1 name would
   move it between the many equal keys and change the whole permutation.

Regression-test any fix against the cached UscW gather+counts -> golden table AND the passing
UscHello/UscVars/UscBB/UscFn. Fixing this unlocks all five remaining fixtures (same qsort step).
Ground-truth harness: `_scratch/re/qsort_test.py` (kept locally; the dump is `raw_uscw.txt`).

## Update (2026-09-05, fresh pass): candidate 1 (qsort itself) is RULED OUT; real cause is candidate 2, but not a count off-by-one — it's the GATHER of "value-only" names

Re-disassembled the full partition + `_shortsort` + entry/exit (`0x77cb0`-`0x781a0`) instruction by
instruction against `ordering.py`'s current `msvc_qsort`/`_shortsort`. Every step matches exactly,
including the parts not previously hand-traced:

- The `higuy` downward scan (`0x77fc1`-`0x78003`) is the textbook `do{higuy-=width}while(higuy>mid &&
  comp(higuy,mid)>0)`, byte for byte (same comp-argument order, same CFG-guard call shape).
- The post-break equal-run handling (`0x78003`-`0x780e1`, the two sequential `if`s) matches
  `ordering.py` lines 87-94 exactly, including which exit path from the first `if`'s loop falls
  through into the second.
- The `[ebp-0x118]`/`[ebp+ecx*4-0x7c]`/`[ebp+ecx*4-0xf4]` array at the tail (`0x78107`-`0x78150`) is
  **not** an equal-key-index collector — it is the ordinary `lostk`/`histk` recursion stack + `stkptr`
  push, exactly what `ordering.py`'s `stack.append((lo, hi))` already does. The final `js`-then-pop
  block (`0x78173`-`0x78199`, reassembled past the objdump range-cut) is the ordinary `stkptr==0 ->
  return` / `--stkptr; lo=lostk[stkptr]; hi=histk[stkptr]; goto recurse` — matches `if not stack:
  break` / `lo, hi = stack.pop()`.
- `_shortsort` (`0x77d44`-`0x77df5`, the `size<=8` path) also matches `ordering.py` exactly, incl. the
  `comp(p,max)` argument order and the `max==hi` no-op-swap skip.

Conclusion: **`msvc_qsort`/`_shortsort` are already instruction-exact. No change was made to
`ordering.py`.** Two independent Python ports (the current one and a from-scratch literal one) agree
with each other and with this disassembly, so a shared porting bug is very unlikely.

Traced the real cause instead on `RahnemBrushBuilders` (a committed golden + the *official*
`default_global_index()` dump — no wine-runtime-dump uncertainty, unlike the UscW ground truth above).
`gate` fails there at name-table offset 292: golden has `RahnemBrushBuilders`(the package's own name,
self-injected into the class's `PackageImports`) immediately before `BreadthSegments` (a `var()` on
line 10 of `LandscapeBuilder.uc`); our output has them swapped. Both are tied (count=1, both absent
from `global_index` since they're own-new). Root cause: `ordering._gather_names` adds every **object's**
`.disp`/`.outer` while walking `name_creation_order`, then — *only after that whole walk finishes* —
appends any name that is not an object's own name at all (a "value-only" name, e.g. a literal spliced
into `PackageImports`) via a trailing `for n in name_key: add(n)`. That treats every value-only name as
if it registered *last*, but a package's own self-reference actually registers essentially at
compile-unit setup — earlier than a variable declared on line 10. `BreadthSegments` is a real object's
`.disp` (an `IntProperty`), so it enters during the main walk (early); `RahnemBrushBuilders` is
value-only, so it's deferred to the trailing catch-all (late) — backwards from golden.

This is a **gather-order modeling gap in `ordering.py`'s `_gather_names` (used by `order_package`, via
`reorder.py` and `compile.py`)**, not a qsort bug. Fixing it needs either (a) a real RE of when
`PackageImports`-style value-only names register relative to declared identifiers (the doc's
`0x27ea0` gather note doesn't cover this), or (b) some other principled rule — not a fitted "put value-
only names first" heuristic, since that has not been checked against other value-only cases (default
`name`-typed property values, `Category` strings, `ClassConfigName`, etc., which may register at yet
different points). Not attempted here — it needs its own investigation + the owner's sign-off on the
model change, per this project's "no fitting" rule.

Also spot-checked `ExtendedBuilders`/`DavesBrushBuilders`: these fail `gate` on raw **byte count**
(+5 / +1 bytes vs golden), not table order — `perm_gate` still passes. `ExtendedBuilders` is a
genuinely multi-source-file (two `.uc`) package. Not investigated further; likely a different, unrelated
gap (possibly multi-class handling), out of scope for this pass.

Net: `FrameBuilder` is still the only `realpkg` fixture passing the STRICT gate outright.
`RahnemBrushBuilders`'s remaining gap is understood and evidenced (above) but unfixed pending a
scoped follow-up. `ExtendedBuilders`/`DavesBrushBuilders` remain unexplained size diffs.

## Fixed (2026-09-05): value-only names gather at their real registration point, not a trailing pass

RE'd the two registration points evidence pointed at, using `RahnemBrushBuilders` (a committed golden
+ the official `default_global_index()` dump — no runtime-dump uncertainty):

- **A package self-name** (spliced into `PackageImports`) registers at CLASS-HEADER time — with the
  rest of the class-header body (`FriendlyName`, `Dependencies`, `PackageImports`, `ClassWithin`,
  `ClassConfigName`), essentially as soon as the class object itself is processed. Evidence:
  `RahnemBrushBuilders` (self-name) sorts before `BreadthSegments`, a `var()` on line 10 — i.e. before
  a class member declared after the header is done.
- **A defaultproperties tag VALUE that is itself a new name** (e.g. `GroupName="Landscape"`, a
  `name`-typed default) registers LATER — after every member AND every function in the source, because
  `defaultproperties` is the last block UCC compiles. Evidence: brute-forcing the tail permutation
  (only permutation search that reproduces `RahnemBrushBuilders` byte-exact, incl. two unrelated
  count=7 imports `Vertex3f`/`GetVertexCount` whose relative order a wrong tail perturbs via the
  qsort's position-sensitive median-of-3 pivot) requires `Landscape` after `BreadthSeg`/`_Terrain`/
  `BreadthStep` — three `BuildTerrain` function PARAMS declared earlier in the source than
  `defaultproperties`. A **naive single-rule fix — interleave every value-only name at its referencing
  object's main-walk position — is WRONG**: it moves defaultproperties-tag names too early and breaks
  the qsort's tie permutation elsewhere (confirmed via exhaustive brute force: no permutation of the
  own-new tail alone reproduces golden without also splitting the timing).

  A defaultproperties tag NAME (e.g. `BreadthSegments` as `t.name`) needs no separate handling — it's
  always a dup of an already-declared member's own name, so its gather position is a no-op wherever it
  lands.

**Fix**: `reorder.py`'s `_Decoder` now splits a class body's decoded refs into `_class_split_streams`
(header refs vs. the defaultproperties tag-stream refs); `ObjInput` gained a `late_name_refs` field
carrying the tag-stream ones. `ordering._gather_names` interleaves `name_refs` inline (at each
object's position in the main walk — the general "value-only names register at their referencing
declaration's compile point" rule, now correctly scoped) and adds a SECOND trailing pass over every
object's `late_name_refs` after the whole main walk (modeling "defaultproperties compiles last").
`_reference_counts` counts `late_name_refs` the same as `name_refs` (timing doesn't affect counts).

**Result**: `RahnemBrushBuilders` passes the STRICT gate (`test_uscript_realpkg.
test_realpkg_strict_byte_exact`). `FrameBuilder` still passes (no regression). `UscHello`/`UscVars`/
`UscBB`/`UscFn` still pass. **`UscW`** (21 functions, a stock-colliding member name `Add`) now ALSO
passes the STRICT gate FULLY AUTONOMOUSLY (no `order_override`, no name-flag masking) — the old
`test_usc_w_byte_exact_modulo_name_pool_flags` test's premise (the `+0x04000000` boot-pool bit is
"underivable") was never true; it was masked by this same gather-order bug. That test is folded into
`test_autonomous_byte_exact` and the stale masking helper removed. Full offline uscript suite: 214
passed, 0 failed.

Side effect (not chased further, per scope): `DavesBrushBuilders` used to fail on raw byte COUNT
(+2 bytes); with this fix the byte count now matches and it fails on name-table ORDER instead, at an
enum's own value list (`DB_Tetrahedron`/`DB_Stellate2`/… — the same *class* of value-only-name
problem, but internal to a single Enum object's own value list, not the class-header/defaultproperties
split above). `ExtendedBuilders` is unaffected (still +5 bytes, unrelated — likely multi-class/
multi-source handling). Both remain open, tracked here for a future pass.

## ExtendedBuilders +5-byte diff (2026-09-13) — mechanism confirmed, cause still open

Re-checked: `perm_gate` passes (84 names in both, same string SET), but the two name tables are a
different PERMUTATION of the same 84 names (`BeginBrush` at index 12 in ours / 10 in golden,
`EndBrush` at 10 / 17, etc.) — and since every `NameConst`/obj-ref in the file encodes its target's
TABLE INDEX as a `FCompactIndex` (1 byte under 64, 2+ above), a different permutation shifts which
names land under/over that width threshold, changing the file's total byte count with the exact same
name SET. The "+5 bytes" is a symptom of table order, not a separate bug — this narrows it to the
same bug CLASS as `DavesBrushBuilders` below.

**Correction to an earlier version of this note**: `compile_package_dir` (`ExtendedBuilders` is a
two-class package, `ExtParallelepiped`+`ExtWave`) DOES call `reorder.true_order`, the same real
ordering pipeline as the single-class path (`compile.py` end of `compile_package_dir`) — a stale
comment atop the multi-class section claimed otherwise ("assigns creation order... rather than
reproducing UCC's refcount sort"; fixed in the same pass as this note). So this is NOT an
architectural gap — it is a real, fixable gather-order bug, most likely the SAME multi-class
interleaving question as the enum-tag scatter below, just not yet isolated to one specific object.
Not root-caused this pass; revisit alongside `DavesBrushBuilders`.

## DavesBrushBuilders enum-tag scatter (2026-09-12) — looked at, not fixed, evidence recorded

Current code (`reorder.py` `streams()`, "Enum" kind) treats an enum's whole value list as one
`name_refs` clump registering at the Enum export's own position — wrong. Golden interleaves the tags
with unrelated declarations (`DB_Tetrahedron` right after the last function; `DB_Stellate2` after
`System`; `DB_Cube` after `Editor`; `DB_Octahedron`/`DB_Dodecahedron` after `BitmapFilename`; …), not
clustered. This rules out "all tags register at enum-declaration time." It's also NOT explained by
bytecode value-references: `bytecode.md` already established enum tags used as values compile to
`ByteConst(ordinal)` — no `<<FName` in the script, so a `switch`/comparison against a tag can't be
the registration point either. Mechanism not identified. Low priority: 2 fixtures, pure name-table
permutation (zero functional effect, same class as the already-accepted indexing non-issues).
Re-open with a controlled multi-enum probe (vary which function references each tag, vary enum
position in source) rather than reasoning from one real package.

## Update (2026-09-13): controlled probes run; a clean gather-order baseline recovered, full rule still open

Ran controlled UED22 compiles varying which function references which tag (`_scratch/enum_probe*.py`,
not committed). Two findings:

- **`var` must precede every function in an UnrealScript class** (a hard grammar rule — `Error, 'Var'
  is not allowed here` if declared after a function). So a real class's enum is always textually
  before its functions; the "vary enum position relative to functions" idea from the note above isn't
  a valid axis to probe.
- Comparing ABSOLUTE name-table positions across probes with different total identifier counts is
  invalid — the table is SORTED by reference count first, gather order only breaks ties, so a
  differently-sized probe reshuffles unrelated items around any one name. The only clean readout is a
  probe where every new name ties at refcount 1 (nothing referenced twice), so gather order is the
  entire story with no sort to strip away.

That clean baseline — `class UscEnumP2 expands Actor; var() enum _MyEnum { Tag_First, Tag_Second }
MyVar; function Marker1(){} function Marker2(){}` (the ONLY reference to either tag is the enum's own
declaration) — gathers as: `MyVar, Tag_Second, Tag_First, Core, Marker1, System, Marker2, Package,
ScriptText, Actor, TextBuffer, _MyEnum, Object, Enum, Function, ByteProperty, Class`. Two surprises,
neither yet explained:

1. The tags gather in REVERSE declared order (`Tag_Second` before `Tag_First`) — consistent with the
   campaign's general "last declared, first" prepend convention (function/state-label chains), so
   plausibly the same mechanism, but not confirmed against a 3+-tag case.
2. The enum's OWN name (`_MyEnum`) gathers AFTER both its tags, `Core`, `Marker1`, `System`,
   `Marker2`, several unrelated import names — i.e. an enum's UEnum export doesn't register at
   textual-declaration time at all; something defers it well past the functions that follow it in
   source. Not identified.

Not fixed — this needs the SAME rigor as the original `RahnemBrushBuilders` breakthrough (multiple
cross-checked probes + an explicit registration-point model), not a guess from one baseline.

**The 2-tag reading above does NOT generalize — the "clean baseline" methodology is unsound for 3+
tied items.** Same class, same source shape, one more tag (`_MyEnum { Tag_First, Tag_Second,
Tag_Third }`, still nothing but the declaration referencing any of them): `Marker1, Tag_Third,
Tag_Second, Tag_First, MyVar, Core, System, Marker2, …` — `MyVar` now sorts AFTER `Marker1` and all
three tags, where with 2 tags it sorted BEFORE `Marker1` and its tags. Nothing about the SOURCE
changed except tag count, so this is not a gather-order fact about `MyVar` — it is the qsort itself:
MSVC's `qsort` (median-of-3 quicksort) is **not a stable sort**, so a run of tied keys does not
preserve insertion order once there are enough tied elements for the partition to touch them
differently — confirmed here since going from 2 to 3 tied-in items reordered the group. Reading
"gather order" directly off sorted output only works for a strictly 2-tied-item run (no partition
freedom) or by coincidence; it is NOT a valid general probing method. The
`RahnemBrushBuilders` breakthrough correctly used the harder brute-force-permutation-against-the-real-
qsort method for exactly this reason — this note's baseline claims should be treated as unconfirmed
until re-derived that way. Next step: adapt `RahnemBrushBuilders`'s brute-force tail-permutation
harness to this enum case (search the *gather* order that, once run through the ALREADY-verified
`msvc_qsort`, reproduces golden) rather than reading positions by eye.

## Update (2026-09-13): no committed harness exists to adapt; brute force is NOT tractable here — the tied group is too large

Searched the repo and git history for the `RahnemBrushBuilders` brute-force harness referenced
above. It never existed as a reusable script — the fix (commit `5c595b13`) hand-edits
`ordering.py`/`reorder.py` directly, and the permutation search that led to it was ephemeral,
uncommitted exploration in a prior session. There is nothing to adapt; a search for
`DavesBrushBuilders` would have to be written from scratch.

Tried one concrete hypothesis first, since it's cheap to test: reverse each enum's value list
(mirroring the "last declared, first" prepend convention already confirmed for function/state-label
chains). Result: it exactly reverses both enums' internal sub-order in OUR output, but golden's
`_Platonic` tags are in FORWARD declared order (`Tetrahedron, Cube, Octahedron, Dodecahedron,
Icosahedron` — which the UNREVERSED code already gets right) while `_Stellate`'s are in NEITHER
forward nor reverse order (`Stellate2, NoStellate, Stellate1`). So it's not a uniform per-enum
direction flip; reverted (`reorder.py` is back to its original Enum branch, no residual diff).

**Why brute force doesn't work here**: computed the actual reference counts our own
`ordering._reference_counts` assigns (`_scratch/daves_refcounts2.py`) for every "new" identifier in
the ambiguous zone — all 8 enum tags AND 14 unrelated names (`StellateType`, `PlatonicType`, `Build`,
`BadParameters`, `System`, `Editor`, `BitmapFilename`, …) come back `refcount=1`, genuinely tied.
That's a 22+-item tied group feeding one `msvc_qsort` call — nothing close to `RahnemBrushBuilders`'s
"tail permutation" (a small handful of items). Brute-forcing a 22-item permutation space (`22!`) is
not tractable by any means available here.

**What this actually needs**: the same rigor as the original table-ordering breakthrough — a live
runtime dump (an INT3 breakpoint under `winedbg` capturing the real FName registration sequence
during a controlled UCC compile of a small enum-bearing class), not a permutation search. This is a
scoped, known-shape task (the infrastructure for it already exists — see `USCRIPT-COMPILER.md`'s
table-ordering section for the method), just not attempted this pass given the setup cost. Left open;
next session should budget for the live-dump approach specifically, not more static probing.

## Update (2026-09-13, later pass): live `AllocateNameEntry` capture — locals-timing bug found and fixed; the enum-vs-property interleaving bug is real, root-caused, and NOT fixable from compiled bytes alone

Did the live-dump the previous update called for. Found the real registration function — NOT
`SavePackage` (that only gives the SAVE-time global index) but `FName::FName(const TCHAR*,
EFindName)` @ `core.dll` VA `0x1005cad0`, which calls `AllocateNameEntry` @ VA `0x1005cdc0` exactly
once per genuinely NEW name, cdecl args `(Name, Index, Flags, HashNext)` on the stack at
`$esp+4/8/c/10`. Both addresses found by matching the `objdump -p core.dll` export tables by NAME
POINTER TABLE INDEX (not by the ordinal number printed in the `+base[N]` column — those are two
different numbers per row; matching by ordinal instead of index silently gives the WRONG function).
Confirmed self-consistent: `FName::FName`'s "append new slot" branch calls
`TArray::AddZeroed`(`0x1001a9b0`) on `0x10139d50` — the exact same array `dump_gobj.py` already
established as `GObjNames`.

**Method**: unlike `dump_gobj.py`'s one-shot `SavePackage` breakpoint (never needs to resume
correctly — the process is about to end), this needs MANY hits across one compile. winedbg's own
`break *ADDR` (not a raw one-shot memory-patched `0xCC`) manages the restore/step/re-arm dance
correctly across repeated hits — tested live, works. One big batch (`cont` + `x/64b
*(int*)($esp+4)`, repeated ~6400 times) piped to a single `winedbg UCC.exe make` invocation, against
a container with `DavesBrushBuilders`'s sources already in `EditPackages` (this repo's baked UED22
image already has it). Took ~14 minutes wall-clock for 6400 hits (~0.11s/hit); the harness is
committed as `harness/dump_name_creation_order.py` (supersedes nothing — `dump_gobj.py` still owns
the SavePackage/GObjNames dump, a different question).

**Ground truth captured** (own-new names only, boot/Core.u/Engine.u/Editor.u/Fire/IpDrv/Extension
already-registered names filtered out since `AllocateNameEntry` never fires for a name that's already
interned):

    DavesBrushBuilders, PlatonicsBuilder,
    _Stellate, DB_NoStellate, DB_Stellate1, DB_Stellate2, StellateType,
    StellatePercent,
    _Platonic, DB_Tetrahedron, DB_Cube, DB_Octahedron, DB_Dodecahedron, DB_Icosahedron, PlatonicType,
    Extrapolate3, im, Extrapolate4, Extrapolate5, dR, BuildOctahedron, BuildIcosahedron,
    BuildDodecahedron, Platonics (the `GroupName="Platonics"` defaultproperties value)

(`Radius`, `GroupName`, `Build`, `BadParameters`, `BeginBrush`, `EndBrush`, `Vertex3f`, `Vertexv`,
`Poly3i`/`Poly4i`/`Polyi`, `PolyBegin`/`PolyEnd`, `GetVertex`, `BitmapFilename`, `ToolTip`,
`BuildTetrahedron`, `BuildCube`, and every function's params (`A`/`B`/`C`/`D`/`E`/`Count`/`R`/
`SphereExtrapolation`/`ReturnValue`) never fire `AllocateNameEntry` at all — they're all pre-existing
names, reused from `BrushBuilder`'s own script or another already-loaded brush-builder package.)

**Finding 1 — FIXED: a function's body LOCALS register immediately after that function, not deferred
to a trailing pass.** `im` (an `Extrapolate3` local) sits directly between `Extrapolate3` and the next
function `Extrapolate4`; `dR` (a `BuildCube` local — `BuildCube` itself is a pre-existing name, so it
never appears in this stream, but its own local still lands at `BuildCube`'s SOURCE POSITION) sits
directly between `Extrapolate5` and `BuildOctahedron`. This directly refutes the previous "NAME
registration is two-pass (declarations incl. function params/return, then function-body locals)"
model (`compile-model.md`, `reorder.py`'s old `name_creation_order`): under that model the combined
own-new sequence would be `…Extrapolate3, Extrapolate4, Extrapolate5, BuildOctahedron,
BuildIcosahedron, BuildDodecahedron, im, dR` (all functions' signatures first, then ALL locals in one
trailing block) — measurably different from, and refuted by, the captured order above.

**Fix**: `reorder.py`'s `name_creation_order` no longer special-cases `Function` (params-only inline +
locals deferred to a second `for fi in funcs` pass); it now recurses into EVERY child inline,
identical in shape to `creation_order` (which never had the bug — object/export creation was already
fully inline). `_CPF_PARM`/`_prop_flags`, only used by the removed two-pass split, are deleted as dead
code. No regression: full offline uscript suite still 210 passed (was 209 — the fix adds a new
pinning test, `test_davesbrushbuilders_locals_register_inline_not_deferred`, asserting the two
captured orderings directly against `DavesBrushBuilders.u`'s own committed golden). `FrameBuilder`/
`RahnemBrushBuilders`/`UnrealShare` still pass the strict gate.

**Finding 2 — ROOT-CAUSED, NOT FIXED: property-vs-non-property interleaving is lost once the class is
compiled, and cannot be recovered from a `.u` file's bytes alone.** The SAME capture shows
`_Stellate`+its 3 tags register BEFORE `StellateType` (the enum-typed property), and `StellatePercent`
registers BETWEEN `StellateType` and `_Platonic` — i.e. registration follows plain interleaved SOURCE
TEXTUAL declaration order (`Radius; enum _Stellate{...} StellateType; StellatePercent; GroupName; enum
_Platonic{...} PlatonicType;`), enums and properties freely mixed as declared.

But `_decl_forward` (used by both `creation_order` and the fixed `name_creation_order`) reconstructs a
class's own children as `[properties, forward] ++ [non-properties (enums/consts/structs/functions),
forward]` — ALL properties as one leading group, ALL non-properties after. This is not a `reorder.py`
bug: decoding the REAL UCC golden `DavesBrushBuilders.u` directly (not our own compiler's output)
shows its own on-disk `Children` chain is genuinely stored this way — `[Build,BuildDodecahedron,…,
Extrapolate3, _Platonic, _Stellate]` (one combined non-property group, reverse-of-declared, enums AND
functions correctly interleaved WITHIN that group) `++ [Radius, StellateType, StellatePercent,
GroupName, PlatonicType]` (properties, forward). Reversing the non-property group recovers its own
internal order exactly (confirmed: `_Platonic` before `_Stellate` reversed gives `_Stellate` before
`_Platonic`, matching declaration order) — but the chain provides NO signal for where the property
GROUP as a whole should interleave against the non-property group, because UCC's own class-body
storage genuinely bins them into two separate sub-chains before serializing. The interleaving
information (needed bit-for-bit, since these are all refcount-tied names whose exact gather position
feeds the position-sensitive unstable `msvc_qsort`) is not present in ANY compiled `.u` — ours or the
real UCC's — once compilation finishes.

Confirmed this is DavesBrushBuilders's whole remaining divergence, and it did not move at all: the
strict-gate first-diff point (name-table offset 306, `NAME[14]`) is byte-for-byte IDENTICAL before and
after the Finding-1 fix — the locals-timing bug never touched this package's failure (its enum tags
all sit before any function is even parsed), so Finding 1 is a real, separately-verified correctness
fix that happens not to move THIS package's gate result. `ExtendedBuilders` still fails on the same
symptom shape (a table-order-driven byte-count diff, unaffected by the fix) and is very likely the
same underlying bug in its multi-class form — not reinvestigated this pass.

**Why `reorder.py`'s whole architecture can't close this alone**: `compile.py` compiles PROVISIONALLY
once (no order), serializes it, and `reorder._Decoder` decodes THOSE bytes to derive the target order
for a second, final compile — i.e. the only order information available is whatever survives one trip
through `serialize.py`'s Children-chain encoding, which (matching real UCC) already lost the
prop/non-prop interleaving. Fixing this needs the compiler's own AST-walk order — which `compile.py`
HAS while it is building the class the first time, before that information gets binned away — threaded
through to the name-gather step directly, instead of (or alongside) reconstructing it from decoded
bytes. That is a real architecture change (a new order-source parallel to `reorder.true_order`, not a
`reorder.py` patch), scoped, not attempted this pass — flagged as the concrete next step.

## FIXED (2026-09-13): AST-order threading recovers the enum-vs-property interleaving

Did the architecture change the previous section flagged as the concrete next step. UCC's name
registration follows plain SOURCE-TEXTUAL order — a property and a later `var() enum` register side
by side, exactly as declared. The compiled `.u`'s own `Children` chain cannot reproduce that order
after the fact — it structurally bins every property into one forward sub-chain and every
non-property into a separate reverse sub-chain (confirmed against the real UCC golden, not just our
own output) — so `reorder.py`'s decode-the-compiled-bytes architecture can never recover it, no
matter how the decode is written.

**Fix**: thread the compiler's own AST-walk order through directly, bypassing the decode for this
one piece. `ClassDecl.decl_order` (`ast.py`) is every top-level declaration in true source order —
the parser's single top-to-bottom class-body loop already sees this order, it just used to discard
it when splitting into `members`/`callables`. `compile._top_level_name_order` turns it into a display
-name list. `reorder._Decoder.name_creation_order` gained `class_order`/`top_level_by_class` params:
supplied, it walks the true top-level order per class (still recursing into each field's own
children via the existing `_decl_forward`, since a function's params/locals or a struct's members
were never binned — only the top-level mix of properties and non-properties was); omitted, it's the
same binned walk as before. `compile_package`/`compile_package_dir` supply both from the parsed AST.

**Result**: `DavesBrushBuilders` went from diverging at name-table index 14/74 (cascading through
most of the table) to matching golden in all but one swapped pair — indices 21/22 (`Core`/the
package's own self-name), both refcount 1. That pair is a DIFFERENT, narrower bug: a qsort-tie-
permutation between a real engine-pool name and an own-new value-only name, confirmed present
(masked) in the PRE-fix output too, so this fix did not introduce it. Root-caused as far as: `Core`'s
dumped global index (16) already sorts it far ahead of `DavesBrushBuilders` (sentinel, no dumped
index) in `order_package`'s presort, so the swap must happen inside the `msvc_qsort` permutation of
the refcount=1 tied group itself, not in gather order — tracked separately,
`dev/docs/board/inbox/uscript-name-order-core-vs-package-self-name/`. `ExtendedBuilders` is
unaffected by this fix (still fails `gate`, still passes `perm_gate`) — its divergence starts at a
9-name tied group of the same apparent bug class, not the interleaving bug this fix targets; its
multi-class cross-class registration-order model is also unverified. No regression: full offline
uscript suite, 217 passed (was 216). Full detail + the fixed board item:
`dev/docs/board/done/uscript-name-order-enum-vs-property/`.

## FIXED (2026-09-13): ExtendedBuilders's multi-class registration-order model — the cross-class
## piece flagged above as unverified

Confirmed and fixed: `reorder._Decoder.objinputs()` split a class's header refs from its
defaultproperties tag refs (`late_name_refs`) only for `self.class_i` (the first class export by
array position, not necessarily the first class in true compile order) — the OTHER class in a
multi-class package routed through the merged `_class_streams` path instead, so its
defaultproperties tag value (`ExtendedBuilders`'s own `GroupName="Parellelepiped"`/`"Wave"`, both
own-new) registered as an ordinary early ref right after that class's header, not after its own
members. `ordering._gather_names` compounded this: it flushed `late_name_refs` in ONE trailing pass
over the whole package, which for a multi-class compile defers the FIRST class's own
defaultproperties past the SECOND class's entire body — wrong, since a multi-class package compiles
one class fully (through its own defaultproperties) before starting the next
(`compile_package_dir`'s own sequencing, confirmed via the alphabetical fixture filenames matching
`_compile_order`'s output: `ExtParallelepiped` before `ExtWave`, matching golden's own placement of
`Parellelepiped` immediately before `ExtWave`'s first property).

Fix: `objinputs()` splits every class export (`e["cls"] == 0`), not just `self.class_i`;
`_gather_names` flushes each class's `late_name_refs` right before the next class object starts (or
at the end, for the last class). Verified: `Parellelepiped`/`Wave` now land at golden's exact
name-table index (`test_extendedbuilders_defaultproperties_values_land_per_class`).

**Does NOT close `ExtendedBuilders`**. The first `gate()` diff moved from name-table index 12
(`Core` vs `Vertex3f`) to index 7 (`BuildCube` vs `GetVertexCount`, both refcount 3) — this fix
changed the array's own-new TAIL, and `msvc_qsort`'s median-of-3 pivot reads `a[lo]`/`a[mid]`/`a[hi]`
of the CURRENT recursion slice, so a tail change can shift an unrelated front tie's permutation
without either tie's own local comparator values changing. Verified this isn't a counting/gather
bug for the front group specifically: decoded BOTH `mine`'s own bytes and golden's bytes
independently through `_reference_counts` and got IDENTICAL refcounts and IDENTICAL
`default_global_index()` lookups for all 11 names in the diverging range (`BuildCube`,
`GetVertexCount`, `Editor`, `Core`, `GroupName`, `Vertex3f`, `Width`, `System`, `EndBrush`,
`Breadth`, `BeginBrush`) — so the divergence is not in what these entries ARE, only in what
surrounds them in the full gather array at qsort time. The interacting tail region is a ~90-item
refcount-0 tie (function params/locals across BOTH classes that are addressed by object ref in
bytecode, never referenced by `<<FName`, so they never earn a real name refcount) — the same shape
as `DavesBrushBuilders`'s enum-tag scatter above, which needed a live `AllocateNameEntry` capture to
resolve, not static reasoning. Not attempted this pass (no live UED22/winedbg environment
available). Board item: `dev/docs/board/done/extendedbuilders-multi-class-defaultproperties/`.

## Update (2026-09-13, later pass): ExtendedBuilders front-tie re-examined — three candidate causes
## cleared by measurement, confirmed blocked on live capture, not a research dead end

Re-checked all three angles the board item's own investigation left open — own-new gather timing for
shared engine-pool names, class-1-tail/class-2-head interleaving, a possible refcount miscount —
against the code as it stands post-`7c2cd1ea`. All three are cleared:

- **Engine-pool names are gathered once, correctly.** `_gather_names`'s `seen` list dedups by
  identity — a name is never re-touched or repositioned once added, regardless of which class's walk
  reaches it. Moot check either way: all 11 names in the diverging name-table range (index 7-17:
  `BuildCube`, `GetVertexCount`, `Editor`, `Core`, `GroupName`, `Vertex3f`, `Width`, `System`,
  `EndBrush`, `Breadth`, `BeginBrush`) turn out to carry a REAL dumped `global_index` (`Core`=16,
  `Editor`=18, `System`=204, the rest 4241-4289 — pre-existing names from `BrushBuilder`'s own script,
  same "reused, never own-new" class `DavesBrushBuilders` already established for its own tied pair).
  `order_package`'s presort (`sorted(gathered, key=by_name_index)`) sorts by this index NUMERICALLY, so
  raw gather-array position is provably irrelevant for all 11 — confirmed by manually re-splicing each
  into different raw-gather positions and observing zero change in `msvc_qsort`'s output.
- **Class-boundary interleaving is already correct.** Decoded `mine`'s own compiled bytes and
  `golden`'s bytes independently through `name_creation_order(class_order, top_level_by_class)` +
  `_gather_names`: byte-identical 84-item gather arrays AND identical refcounts for every name, not
  just the 11 in question. The `7c2cd1ea` per-class `late_name_refs` flush is doing its job.
- **The refcounts are not miscounted.** Traced `BuildCube`/`GetVertexCount` (refcount 3, the pair
  heading the tied range) to real provenance: each is a `<<FName` token in a function-call op (not an
  object ref) — `BuildCube`: its own `FriendlyName` (1) + two calls in `ExtParallelepiped.Build`
  (Hollow branch calls it twice) = 3. `GetVertexCount`: one call in `ExtParallelepiped.BuildCube` +
  two in `ExtWave.BuildTerrain` = 3. Confirmed from real decoded body bytes in BOTH packages
  independently, identical. The "genuinely tied" claim holds, on a verified-correct count.

**New finding: a second, previously unreported divergence.** Name-table index 70-76: golden has
`Vector, LRi, LRj, LRk, Ri, Rj, Rk`; ours has `LRi, LRj, LRk, Ri, Rj, Rk, Vector` (`Vector` moved to the
tail of the run instead of the front). `Vector` carries a real global index (31) and refcount 0;
`LRi`/`LRj`/`LRk` (`BuildCube`'s own params) and `Ri`/`Rj`/`Rk` (`Build`'s own locals) are genuinely
own-new, refcount 0, no global index — their OWN mutual order is already right (matches golden), only
`Vector`'s slot relative to them is wrong. Same bug class as `DavesBrushBuilders`'s still-open
enum-tag scatter (an intrinsic/type name's registration point relative to a tied run of declared
identifiers) — now confirmed present in a second package.

**Corrected tier size**: the refcount=0 tier both this scatter and (via `msvc_qsort`'s whole-array
recursion sensitivity) the front swap sit near is **39 names**, not the "~90" the prior pass estimated
— `ScriptText`, `Direction`, `LRi/LRj/LRk`, `_tessellated`, `N/i/j/k`, `ReturnValue`, `Ri/Rj/Rk`,
`dx/dy/dz`, `WidthSeg`, `DepthSeg`, `nbottom`, `X/Y`, `idx`, `WidthStep`, `DepthStep`, plus intrinsic
type names with real global indices (`Package`, `Object`, `Class`, `Vector`, `Struct`,
`FloatProperty`, `IntProperty`, `StructProperty`, `BoolProperty`, `Function`, `NameProperty`,
`TextBuffer`, `BrushBuilder`). Still far past brute-force reach (39!), and — since the front-group
swap sits in the refcount 2/3 tiers, OUTSIDE this refcount-0 tier — getting this tier's true order
right could, in principle, resolve the front swap too as a side effect of a shifted recursion boundary
(matches this board item's own prior observation that a tail change moved the front tie from index 12
to index 7); untested, no way to try without the true order.

**Conclusion: confirmed blocked on docker/winedbg availability in this environment, not a research
dead end.** Every static angle available here is exhausted. What a live `AllocateNameEntry` capture
(`core.dll` VA `0x1005cdc0`, `harness/dump_name_creation_order.py`) of a real `UCC.exe make` of
`ExtendedBuilders` specifically needs to answer:

1. Where does `Vector` (the `vector` type keyword, referenced only via each `LRi`/`LRj`/`LRk`/`Ri`/
   `Rj`/`Rk` declaration's type-tail, never by an explicit `<<FName` in this package's own source)
   actually get interned relative to those six params/locals?
2. The true relative registration order of `BuildCube`/`GetVertexCount` (refcount 3) against
   `Editor`/`Core`/`GroupName`/`Vertex3f`/`Width`/`System`/`EndBrush`/`Breadth`/`BeginBrush` (refcount
   2) — all 11 already carry real dumped indices (independently validated: `FrameBuilder`/
   `RahnemBrushBuilders`/`DavesBrushBuilders` contain several of the same names with no issue), so this
   is either a dump correction for one of them, or (more likely) confirmation that `msvc_qsort`'s
   recursion does something on THIS array's shape that the existing instruction-level disassembly
   re-verification (covering the algorithm's structure, not every recursion shape) didn't catch — an
   instrumented capture of the actual `SavePackage` sort call's input array would settle this directly.

No code changed this pass (`uedcli/uscript/reorder.py`/`ordering.py` unmodified). Diagnostic scripts
used were ephemeral (`_scratch/`, not committed — none produced a new checkable rule to pin).

## Update (2026-09-13, later pass): live capture done — refutes the registration-order hypothesis; the real bug is in `order_package` itself, isolated to two distinct mechanisms, neither fixed (no fitting)

Ran the live `AllocateNameEntry` capture the previous update asked for
(`harness/dump_name_creation_order.py --package ExtendedBuilders --hits 7200`, matching the real
`bake_ued22.sh` `EditPackages` order — `DavesBrushBuilders, FrameBuilder, RahnemBrushBuilders,
ExtendedBuilders, …` — via `reference.ucc_container` so the container's `unrealtournament.ini` is the
real one, not a synthetic single-package ini). Result: **6249 names registered total, and the capture
ends at `ExtendedBuilders`'s own class self-name.** This settles REGION 1's 11 names (`BuildCube`,
`GetVertexCount`, `Editor`, `Core`, `GroupName`, `Vertex3f`, `Width`, `System`, `EndBrush`, `Breadth`,
`BeginBrush`), which are all header/class-level refs the capture directly observes registering before
that self-name: each is already interned before `ExtendedBuilders`'s own compile starts — confirmed
independently, since this live capture's own indices for all of them (e.g. `Width`@4241,
`BuildCube`@4275, `Breadth`@4289) are byte-for-byte identical to the committed `gobjnames_ued22.json`
dump. So the dump is NOT stale, and — directly answering question 1 for region 1 — there is no "true
registration order" left to discover for these 11 names by more live capture: they register during
the Editor/Fire/IpDrv/Extension/DavesBrushBuilders/FrameBuilder/RahnemBrushBuilders load, not during
`ExtendedBuilders`, and both a fresh live run and the shipped dump agree on exactly where.

**Region 2's names (`Vector`, `LRi`/`LRj`/`LRk`/`Ri`/`Rj`/`Rk`, index 70-76) are NOT settled by this
capture.** Per the campaign's own established fact (the `DavesBrushBuilders` capture: a class
self-name registers at class-header time, before any of that class's own members are parsed), a
capture that ends at the class self-name stops BEFORE it could observe body-local registrations —
so it says nothing about when `LRi`/`LRj`/`LRk`/`Ri`/`Rj`/`Rk` register. These six are genuinely
own-new (absent from `gobjnames_ued22.json`, and from every other package in the corpus) — the
question 1 the previous pass posed for `Vector`'s relative order against them is still open and
would need a deeper capture (past class-header registration, into the class body) to answer.

**This refutes the registration-order framing question 2 posed.** It is not "which of these 11 names
is mis-dumped" (question 2's first guess) — a self-consistency test proves it directly: decode
`ExtendedBuilders.u` (golden) itself back into its own `ObjInput`s/refcounts/gather and feed that
straight through our own `order_package`/`msvc_qsort` (`_scratch/trace3_selfconsistency.py`, not
committed). Using GOLDEN's own objectively-correct membership, refcounts, and dumped indices still
reproduces the *exact same* 16-entry divergence as compiling from source. Since every input to
`order_package` is now independently verified correct (refcounts hand-checked against source
occurrences; gidx values confirmed twice — the shipped dump and a fresh live capture agree), the bug
is squarely inside `order_package`/`msvc_qsort`'s own mechanics, not in gather-order derivation from
compile order. This is a materially different, and more precisely located, finding than every prior
pass on this item.

Traced `msvc_qsort` with instrumentation (`_scratch/trace5_qsort_debug.py`) on the real 84-item
presorted array (`_gather_names` output, stably presorted by `default_global_index()`). Two distinct
mechanisms, not one:

1. **The `BuildCube`/`GetVertexCount` swap (index 7-8) and the 9-item `Editor`/`Core`/`GroupName`/…
   run (index 9-17) are both resolved by one `_shortsort` call** (`shortsort[3:16]`, an 8-and-a-6-item
   pair of size-≤8 runs after an outer split). `_shortsort` is a selection sort: for a tie
   (`comp(a[p], a[mx]) > 0` false when equal), the FIRST-encountered element of a tied run keeps `mx`
   and gets extracted-to-the-end LAST, landing it EARLIEST in final (descending) output — i.e. ties
   preserve *input* order under our port. Diagnostic: changing the strict `> 0` to `>= 0` in
   `_shortsort`'s selection test (untested against disassembly — NOT committed) closes exactly 2 of
   the 16 diffs (the `BuildCube`/`GetVertexCount` swap and one downstream index) and leaves 14. So
   *some* real discrepancy lives in the tie-handling convention here, but `>=` is not the whole
   answer and is unconfirmed against the binary — flagged, not applied.
2. **The `Vector`/`LRi..Rk` swap (index 70-76) is NOT a shortsort matter at all.** It sits inside a
   39-item all-refcount-0 run (index 45-83) handled by ONE big (`size` 39 `>` `_CUTOFF` 8) partition
   call. Traced instruction-by-instruction: because every element in this call's range is tied
   (`comp` always 0 against the pivot), the three median-of-3 swaps are all no-ops, and the
   loguy/higuy scan runs off both ends (`loguy` reaches `84` past `hi=83`, `higuy` reaches `lo=45`)
   without ever executing the inner swap — this call is a **provable no-op**: whatever order this
   39-item range had going IN is exactly what comes out. The `>=` diagnostic above changes nothing
   here (it only touches `_shortsort`, never reached for a 39-item run). So `Vector`'s wrong position
   is not a qsort-recursion artifact at all — it is set by the OUTER `qsort[0:83]` call's partition,
   which (unlike this no-op) DOES swap: `Vector`, having a real low `gidx` (31, an intrinsic boot
   name) starts at raw presort position 9, while `LRi..Rk` (own-new, no `gidx`) start at position
   70-75 — the outer partition's positional Hoare-style scan (splitting the full 84 items into a
   `{0:44}`/`{45:83}` pair by refcount) relocates `Vector` into the low-refcount half via a swap
   against whatever the `higuy` scan currently holds, and THAT swap — not a simple "ascending gidx"
   rule — is what determines its final neighbor. This is provably NOT explained by the "presort by
   dumped index, own-new last" model in isolation: `Vector`'s presort position (9) is confirmed
   correct (matches its true dumped/live-captured `gidx`), yet the outer partition's specific
   swap sequence, which is sensitive to every OTHER element's position too, does not preserve that
   ordering relative to `LRi..Rk` the way the (already twice disassembly-verified) shortsort's
   tie behavior would predict for a smaller run.

**Conclusion, per the owner's standing rule against hacks ("don't do hacks just to satisfy a single
package scenario"): NOT fixed.** Both mechanisms are real, evidenced, and distinct from anything
closed so far in this campaign — but the available static/dynamic evidence (two disassembly passes on
the qsort structure, a fresh live registration-order capture, and a self-consistency decode of
golden's own bytes) is now exhausted without pinning WHY the outer partition's positional swap (item
2) or the shortsort tie convention (item 1) diverges from `core.dll`'s actual behavior on an array
this size/shape. What would settle it: a live capture of the ACTUAL array `SavePackage`'s own
`msvc_qsort` call receives and produces for `ExtendedBuilders`'s name table specifically (hooking
`appQsort`@`0x315c0` or `qsort`@`0x77cb0` directly, not `AllocateNameEntry` — a fundamentally
different probe than anything built so far in this campaign) — out of scope for this pass. No code
changed (`ordering.py`/`reorder.py` unmodified); `ExtendedBuilders` stays at `perm_gate`-only.
Diagnostic scripts (`_scratch/trace2.py`, `trace3_selfconsistency.py`, `trace4_qsort_isolate.py`,
`trace5_qsort_debug.py`, `dump_extendedbuilders.py`) are ephemeral, not committed.

## Update (2026-09-13, later pass): mechanism 1 (`_shortsort` tie test) DEFINITIVELY REFUTED by fresh
## disassembly; mechanism 2 confirmed NOT a qsort bug

Extracted `core.dll` straight from the `ued-x86-runtime:latest` image (`docker create --entrypoint cat
... /opt/UED22/core.dll`, `docker cp`) and re-disassembled `qsort` (`objdump -d -M intel
--start-address=0x10077c80 --stop-address=0x100781c0`, ImageBase `0x10000000`) from scratch — a fresh
pass, not a re-read of the prior notes, specifically to settle the `>` vs `>=` question the last pass
left open.

**`_shortsort`'s tie test, traced instruction-by-instruction (`0x10077d63`-`0x10077d92`):**

    10077d63: push eax          ; push mx
    10077d64: push esi          ; push p            (cdecl: p is comp's 1st arg, mx the 2nd)
    10077d67: call [0x1009b20c] ; CFG check thunk
    10077d6d: call ebx          ; comp(p, mx)
    10077d72: test eax,eax
    10077d74: jle 0x10077d80    ; result <= 0  ->  KEEP old mx (skip)
    10077d76: mov eax,esi       ; result  > 0  ->  mx = p

`jle` skips the update on a tie (`comp == 0`) exactly like a strictly-greater test — this is **`>`,
not `>=`**. It matches `ordering.py`'s current `_shortsort` (`if comp(a[p], a[mx]) > 0: mx = p`)
exactly. **The diagnostic `>=` tweak the prior pass flagged (closing 2/16 `ExtendedBuilders` diffs) is
REFUTED by the actual binary — it was curve-fitting on that one package's array shape, not a real bug.
Not applied; `ordering.py` is unchanged.**

**The median-of-3 pivot selection (`0x10077e0a`-`0x10077e94`, all three swaps) and the main Hoare
loguy/higuy scan (`0x10077f35`-`0x10078058`) were also re-traced end to end**, independently
confirming the prior two static passes: every comparison in the port (all three median-of-3 swaps,
both loguy scan loops, the higuy scan loop, the post-scan swap, and the `mid == higuy` re-pivot) uses
the same `jle`-skips-on-`<=0` (i.e. strict `>`) convention as `_shortsort`, and every loop bound
(`mid > loguy`, `loguy <= hi`, `higuy > mid`, `higuy < loguy`) matches `ordering.py`'s Python
line-for-line. No `>=` anywhere in the ported region.

**Conclusion for mechanism 2**: since the qsort port is now confirmed instruction-exact by a third,
independent disassembly pass (on top of the two static passes and the self-consistency decode test),
the `Vector`/`LRi..Rk` swap is NOT a qsort algorithm bug — this only reinforces the prior self-
consistency finding, it doesn't newly explain it. The open question stays exactly where the live
`AllocateNameEntry` capture pass left it: the true registration order of names inside a class BODY
(past the point any capture so far reached — every capture stopped at the class self-name) is
unknown, and settling it needs a deeper live capture, not more qsort tracing. Not attempted this pass
(a multi-thousand-hit `winedbg` capture, same cost class as the DavesBrushBuilders capture — scoped as
a separate follow-up, not part of verifying the qsort port). `ordering.py`/`reorder.py` unmodified;
`ExtendedBuilders` stays at `perm_gate`-only. Extracted `core.dll` + the objdump listing are ephemeral
(`_scratch/re/`, gitignored, not committed).

## Update (2026-09-13, later pass): the deeper capture — harness bug found; region 2's RELATIVE order confirmed, index-reuse question still open

Went to run the deeper capture the previous update called for and found why every prior attempt
(including this campaign's own) stalled at the class self-name: it was never a natural stopping
point. `dump_name_creation_order.py`'s `_setup_package` deletes the stale `<Package>.u` but never
staged that package's `.uc` sources — the baked UED22 image ships only the compiled `.u` for every
`realpkg` corpus fixture, no source tree. Confirmed directly: a plain follow-up `wine UCC.exe make`
in the same container right after a capture prints `Can't find files matching
..\ExtendedBuilders\Classes\*.uc` and exits — a clean error, not a crash, and it happens before a
single line of the class body is parsed. **Fix**: `_setup_package` now stages the same committed
fixture sources `ucc_compile` uses under `/opt/<Package>/Classes/`, mirroring `reference.py`.

With sources staged, the capture ran the real compile to completion (6556 `AllocateNameEntry` hits,
up from the 6249 every prior run stalled at; `ExtendedBuilders.u` rebuilt at the correct 11429
bytes). Result:

- `LRi`, `LRj`, `LRk`, `Ri`, `Rj`, `Rk` register in EXACTLY that order, immediately after
  `ExtParallelepiped`'s other own-new properties and before the `GroupName` default value — matching
  `reorder.name_creation_order`'s existing AST-derived walk exactly. Nothing to fix.
- `Vector` never fires `AllocateNameEntry` anywhere in the whole 6556-name transcript (checked with a
  full-file grep). It registers exactly once, at global index 31, during boot, with no relationship
  to `ExtendedBuilders`'s compile timing at all. Its presort position is set entirely by that dumped
  index, which `order_package` already uses correctly.

**Conclusion: region 2's RELATIVE registration order (the six names' order among themselves, and
`Vector`'s irrelevance to their timing) is confirmed correct — this narrows, but does not close, the
open question.** This capture only reads the `AllocateNameEntry` breakpoint's `Name` argument, never
its `Index` argument, so it cannot observe whether any of these names (or any other name in the
package) reuses a freed `FName` slot instead of appending at the tail — `FName::FName` is documented
(this same harness's own docstring) as popping from an `Available` array first. `ordering.py`'s
`by_name_index` sentinel — every own-new name sorts after all dumped names — is an unverified
assumption this capture cannot rule out, and is the one candidate explanation left standing: combined
with the three independent disassembly passes confirming `msvc_qsort` itself is instruction-exact
(same comparisons, same branches, same loop bounds — a deterministic algorithm), a genuine residual
on a truly-identical sort can only mean the INPUT array our port builds differs from the one
`SavePackage` actually passes to `qsort`. So the residual is an input-array question, not a
qsort-partitioning question — "inside how msvc_qsort partitions this array" (this update's own
earlier framing, now corrected) risks misdirecting the next probe toward the wrong side. The
cheapest next step is extending this same capture to also read the `Index` argument at the
`AllocateNameEntry` breakpoint, directly testing the freed-slot-reuse hypothesis; a live hook on
`appQsort`@`0x315c0` or `qsort`@`0x77cb0` during `ExtendedBuilders`'s own `SavePackage`, dumping the
actual array it sorts, is the more expensive but fully conclusive fallback. Neither attempted this
pass. Board item: `dev/docs/board/inbox/extendedbuilders-name-table-qsort-residual/`.

