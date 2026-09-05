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
