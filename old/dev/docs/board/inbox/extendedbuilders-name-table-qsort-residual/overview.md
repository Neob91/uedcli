+++
priority = "p3"
kind = "unknown"
summary = "ExtendedBuilders name-table qsort residual: relative order confirmed, index-reuse question open"
+++

# ExtendedBuilders name-table qsort residual: relative order confirmed, index-reuse question open

`ExtendedBuilders` still fails the strict `gate()` (passes `perm_gate` only). Two name-table regions
diverge from golden: index 7-17 (11 names, all pre-existing/dumped) and index 70-76 (`Vector` vs
`BuildCube`'s params `LRi`/`LRj`/`LRk` and `Build`'s locals `Ri`/`Rj`/`Rk`, all refcount 0).

## Harness bug found and fixed (2026-09-13)

Every prior live `AllocateNameEntry` capture of `ExtendedBuilders` (across multiple sessions) stopped
exactly at the class's own self-name and was read as a natural stopping point ("ran out of names to
register"). It wasn't: `dump_name_creation_order.py`'s `_setup_package` deleted the stale
`ExtendedBuilders.u` but never staged the package's `.uc` sources — the baked UED22 image ships only
the compiled `.u` for every `realpkg` corpus fixture, never a source tree. `UCC.exe make` aborted
immediately with `Can't find files matching ..\ExtendedBuilders\Classes\*.uc` (a clean exit, not a
crash) before parsing a single line of the class body. Fixed: `_setup_package` now stages the same
committed fixture sources `ucc_compile` uses, mirroring `reference.py`.

## New capture result: region 2's RELATIVE order confirmed correct — but index-reuse unverified

With sources staged, the capture ran the real compile to completion (6556 `AllocateNameEntry` hits,
up from 6249; `ExtendedBuilders.u` rebuilt at the correct 11429 bytes) and reached well past the class
body. Findings:

- `LRi`, `LRj`, `LRk`, `Ri`, `Rj`, `Rk` register in EXACTLY that order, immediately after
  `ExtParallelepiped`'s other own-new properties (`BaseX`/`BaseY`/`InclineX`/`InclineY`/`DipX`/`DipY`)
  and before `Parellelepiped` (the `GroupName` default value) — matching what
  `reorder.name_creation_order`'s AST-derived walk already produces. No fix needed for these six.
- `Vector` **never fires `AllocateNameEntry` anywhere in the whole 6556-name capture** (grepped the
  full transcript). It registers exactly once, at global index 31, during boot — long before any
  package-specific compile. It has no "registration point" relative to `LRi..Rk` to capture; its
  presort position is set entirely by its dumped `global_index` (31), which `order_package` already
  uses correctly (independently confirmed earlier the same day: `Vector`'s presort position, 9 of 84,
  is unaffected by gather order one way or the other).

So the RELATIVE registration order sub-question is answered for these six names, and `Vector`'s
irrelevance to their timing is confirmed. But this capture only reads the `AllocateNameEntry`
breakpoint's `Name` argument, never its `Index` argument — so it cannot see whether any name (here or
elsewhere in the package) reuses a freed `FName` slot instead of appending at the tail. `FName::FName`
is documented (this harness's own docstring) as popping from an `Available` array first. `ordering.py`'s
`by_name_index` sentinel — every own-new name sorts after all dumped names — is an unverified
assumption this capture cannot rule out. Given the qsort port is independently confirmed
instruction-exact (three disassembly passes: same comparisons, same branches, same loop bounds — a
deterministic algorithm), a genuine residual on a truly-identical sort can only mean the INPUT array
our port builds differs from the one `SavePackage` actually passes to `qsort`. So the open question is
this index-reuse possibility specifically — not, as an earlier pass phrased it, "how msvc_qsort
partitions the array" (qsort's own mechanics are cleared).

## What's actually still open

The candidate left standing is freed-FName-slot reuse changing an own-new name's absolute index (see
above) — not directly ruled out by any capture so far, since none has read the `Index` argument. The
cheapest next step is extending this same harness's `AllocateNameEntry` breakpoint to also capture
`*(int*)($esp+8)` (the `Index` arg) alongside `Name`, directly testing that hypothesis. Failing that,
a live hook on `appQsort`@`0x315c0` or the CRT `qsort`@`0x77cb0` during `ExtendedBuilders`'s own
`SavePackage`, dumping the actual input/output array it sorts, is the more expensive but fully
conclusive fallback (needs the target's own array layout, not just a name string per hit). Neither
attempted this pass; scoped as its own follow-up given the setup cost.

## Evidence

- `dev/docs/board/to-build/uscript-algorithm-fidelity/findings-ordering-re.md`'s 2026-09-13 sections.
- Harness fix: `dev/docs/board/to-build/uscript-algorithm-fidelity/harness/dump_name_creation_order.py`.
