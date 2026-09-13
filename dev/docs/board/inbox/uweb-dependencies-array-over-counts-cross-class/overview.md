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

## What's still open: the `Dependencies` array

`compile-model.md`'s "Cross-class Dependency entries" section (RE'd 2026-09-13) says a class's
`Dependencies` array gets ONE entry per DISTINCT external class reached via a typed Context access,
in first-use order. That model produces the RIGHT class SET for `HelloWeb` (`WebApplication`,
`WebRequest`, `WebResponse`, `Engine.LevelInfo`) but the WRONG COUNT: UCC's real `HelloWeb` class
carries ~30 `Dependencies` entries with `WebRequest`/`WebResponse` repeated many times (not deduped),
where ours carries exactly one entry per distinct class (5 entries total). Every other class in the
package (`ImageServer`, `WebApplication`, `WebConnection`, `WebResponse`, `WebServer`) fails the same
way — this is systemic, not a `HelloWeb`-specific bug.

`HelloWeb.Query` (the function this was measured on) has roughly a dozen `Request.X`/`Response.X`
Context accesses across an if/switch with 4 cases — the repeat count in UCC's own Dependencies array
doesn't obviously equal "one per Context statement" either (needs a careful correlation pass against
the source, not attempted here). This needs the same kind of live-capture RE work the other open
items in `USCRIPT-COMPILER.md` used (a live UCC build probed for the real counting rule), not a guess.

## Where things are

- Compiler fixes: committed on this session's worktree (see `USCRIPT-COMPILER.md`'s updated table/
  status for the file list). Not yet merged to master.
- Harness used: `_scratch/uweb_probe.py`-style script (not committed — ad hoc, reproducible via
  `reference_ut99.ucc_decompile_ut99`/`ucc_compile_ut99` + `compile_package_dir` + `gate.perm_gate`,
  same pattern as `test_uscript_ut99.py`'s `test_ipserver_roundtrips`).
- Next step: a live `AllocateNameEntry`-style capture (or an `FLinkedProperty`/`FDependency`-focused
  one) on a `UCC.exe make` of `UWeb`, correlated statement-by-statement against `HelloWeb.Query`'s
  source, to find the real Dependency-counting rule.
