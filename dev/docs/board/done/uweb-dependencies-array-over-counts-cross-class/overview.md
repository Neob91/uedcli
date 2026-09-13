+++
priority = "p2"
kind = "unknown"
summary = "UWeb's real class Dependencies arrays carry far more entries than our per-distinct-class model produces"
+++

# UWeb Dependencies array over-counts cross-class references

Attempting the real UT99 stock package `UWeb` (7 classes: `HelloWeb`, `ImageServer`,
`WebApplication`, `WebConnection`, `WebRequest`, `WebResponse`, `WebServer`) for the uscript-compiler
byte-parity campaign (`USCRIPT-COMPILER.md`) got the whole package compiling and matching UCC's real
build on EVERY export body except each class's own `Dependencies` array.

## What matches

Fetched the UT99 substrate (`uedcli/uscript/fetch_ut99.sh`), decompiled `UWeb.u` via `ucc batchexport`,
recompiled the same sources with `uedcli`'s compiler and with a fresh UT99 `UCC.exe make`. `perm_gate`
now agrees on: import table content, `PackageImports` (a property TYPE reference to another package,
e.g. `var LevelInfo Level;`, must NOT pull that package into `PackageImports` — only the super chain's
transitive deps do; this WAS wrong on 4 of 6 real classes, fixed in review), every property/function/
enum body, function `Super` fields (including in-package overrides), `class<T>`-typed property
type-tails referencing a sibling class, same-package class-literal (`class'X'`/`new(...) class'X'`)
resolution disambiguated from a same-NAMED member (`var WebServer WebServer;` — real UnrealScript
allows this), implicit `Return(Nothing)` for a non-native body-less function (`function Foo();`),
`CPF_Native` (0x1000) on a `native` var (only when the owning class is ALSO native — narrowed in
review, see `test_cpf_native_requires_native_class`), and static-array param/local dims (`byte
B[255]`).

Seven real, previously-unexercised compiler bugs were fixed along the way (six from the original
UWeb attempt, one — the `PackageImports` one — found independently by review). Each is now pinned by
a committed, live-UCC-verified regression fixture in `test_uscript_package.py`
(`pkg_SamePkgMisc`/`pkg_PoolCaseDedup`/`pkg_InheritedObjMember`/`pkg_GlobalEnumTag`/`pkg_MiscFlags`/
`pkg_NoSpuriousPkgImport`/`pkg_CPFNativeProbe`) — this is real, tested progress even though the
package doesn't gate clean yet.

**A defaultproperties concern raised in the same review did NOT reproduce.** The claim was that an
own var whose type is declared but never explicitly assigned gets a spurious zero-value default tag
(e.g. `Level=None`, `Path=""`) our compiler emits but golden omits. Tested directly against a live
UED22 build on the exact reported shape (`class TinyApp expands Object; var LevelInfo Level; var
string Path; function Init(); defaultproperties {}`, both via `compile_package` and
`compile_package_dir`) and on the real `WebResponse`/`WebRequest` fields after the `PackageImports`
fix: both sides emit `Level=None`/`Path=""` identically in every case tried. Not reproduced — most
likely the reviewer's read of a truncated `_perm_short`-limited diff attributed a different field's
(most likely `PackageImports`'s) divergence to `defaultproperties`. A REAL, but unrelated, defaults
divergence was found investigating this (a native class's own UNSET plain property sometimes gets a
spurious zero default) — filed separately, not reproduced on real `WebRequest`:
`dev/docs/board/inbox/native-class-lone-plain-var-gets-a-spurious-zero-default/`.

## FIXED 2026-09-13 — the real rule

Decoded the committed `uned/UED22/uweb.u` directly (it's UWeb's own stock UED22 build — a
self-consistent (source, binary) pair with `UCC batchexport`-decompiled sources of it, no fresh
docker rebuild needed) and correlated every `Dependencies` entry against `HelloWeb.Query`'s source
line by line. The real rule: **one entry per SYNTACTIC Context occurrence, never deduped by class**
(confirmed exactly — count AND order — against all 7 real UWeb classes, not just `HelloWeb`). Two
ordering sub-rules, both confirmed: within one function, occurrences record in source-textual order
(an outer Context's entry precedes one nested in its own call's arguments — opposite the natural
bottom-up codegen order); across functions/states, the class's array gathers them in REVERSE
declaration order (the same reversal already known to apply building the Children chain).

Fixed in `lower.py` (`_call_method` records before lowering its own args; `_context` gains a
`record=` flag to avoid double-counting; `_record_dep` no longer dedups) and `compile.py`
(`_build_callables` collects each callable's own Context sequence into a slice, then assembles
`b.extra_deps` from the slices in REVERSE order). Full mechanism + evidence:
`compile-model.md`'s "Cross-class `Dependency` entries".

Verified: all 7 real `uweb.u` classes' `Dependencies` arrays decoded byte-exact (count + order)
against the fixed compiler; a new controlled regression, `pkg_DepOrderProbe`
(`test_uscript_package.py`), isolates all three mechanics in one small fixture and passes both
`perm_gate` offline and a docker-gated fresh-UCC rebuild; the full offline + integration uscript
suites are green with no regression on any previously byte-exact package.

**Not a corpus win yet** — two SEPARATE, pre-existing compiler gaps (found compiling real UWeb while
validating this fix, not fixed here) still block `compile_package_dir` on the real UWeb sources:
`dev/docs/board/inbox/uscript-pointer-var-type-not-supported/` (a `pointer` var type) and
`dev/docs/board/inbox/uscript-explicit-none-object-default-not/` (an explicit `Foo=None` object
default). `USCRIPT-COMPILER.md`'s UWeb entry has the current status.
