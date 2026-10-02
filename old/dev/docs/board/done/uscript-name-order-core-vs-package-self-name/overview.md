+++
priority = "p3"
kind = "debug"
summary = "uscript name order: Core vs package self-name qsort tie (FIXED for DavesBrushBuilders)"
+++

# uscript name order: Core vs package self-name qsort tie

Isolated 2026-09-13 after the AST-order-threading fix
(`dev/docs/board/done/uscript-name-order-enum-vs-property/`) resolved `DavesBrushBuilders`'s dominant
enum-vs-property interleaving bug. Its name table (74 entries) now matches golden EXACTLY except one
swapped pair at indices 21/22: our output has `DavesBrushBuilders` (the package's own self-name, a
`PackageImports` entry) before `Core` (a real engine-pool name, global index 16); golden has `Core`
first. Both are reference-count 1 (a genuine tie) — pinned by
`test_davesbrushbuilders_ast_order_recovers_enum_property_interleaving`
(`uedcli/tests/test_uscript_realpkg.py`).

This is NOT a gather-order bug (`ordering._gather_names`): `Core` has a real dumped global index
(16, near the front of the engine's boot name pool) while `DavesBrushBuilders` has none (sentinel,
own-new), so `order_package`'s `sorted(gathered, key=by_name_index)` presort already places `Core`
far ahead of `DavesBrushBuilders` regardless of gather position (checked directly: gather order has
`DavesBrushBuilders` before `Core`, but presort key `by_name_index` is 16 vs 10**9 — the presort
should already put `Core` first). The divergence must happen INSIDE the `msvc_qsort` permutation of
the refcount=1 tied group itself (this pair is not adjacent after the presort, so the unstable
median-of-3 partition evidently does not preserve their relative order for this specific tied run).

Also present in `ExtendedBuilders`'s still-failing name table (indices 10-18, a 9-name tied group
mixing `Core`/`Editor`/`System` with import display names and the package self-name) — likely the
SAME bug class at a larger scale, not confirmed to be the identical mechanism. Not investigated
whether these two are one bug or several; `ExtendedBuilders`'s multi-class registration-order model
(cross-class name registration sequencing) is also unverified and could be a separate contributor
there.

Fixing this needs the same rigor as the original table-ordering breakthrough: either a live
`AllocateNameEntry`/`SavePackage` capture of a real `UCC.exe make` compiling a small controlled class
whose only new names are one self-reference plus a handful of stock-pool ties (to see the REAL qsort
permutation for this exact shape), or a from-scratch instruction trace of the `msvc_qsort` partition
on this specific presorted array (the qsort port itself was re-verified instruction-exact multiple
times against other fixtures, so a fresh divergence here would be a genuinely new finding about this
specific tie shape, not a known porting bug). Not attempted this pass — out of scope for the
AST-order-threading fix that surfaced it.

## FIXED (2026-09-13) for DavesBrushBuilders — not a qsort bug, a gather-order gap

Re-examined the presort array directly (`_scratch/investigate_core_tie.py`, not committed): `Core`'s
dumped global index (16) IS far ahead of `DavesBrushBuilders`'s sentinel position in the presort, as
already noted above — so the divergence is in the GATHER, not `msvc_qsort` itself, confirmed by
checking the class-header `name_refs` gather directly against the golden's own decoded header
stream: both mine and golden encode `PackageImports = [DavesBrushBuilders, Editor, Core]` identically
(ruling out an on-disk PackageImports-order difference).

The actual gap: `ordering._gather_names`'s main walk does `add(o.disp)` (the class's own FName, e.g.
`PlatonicsBuilder`) BEFORE walking `o.name_refs` (which is where the PackageImports self-reference
lives) — so our gather always registers a class's own name before its package's self-reference.
Recomputing the actual sentinel-only (own-new) gather order from `DavesBrushBuilders`'s decoded
bytes and diffing it against the LIVE `AllocateNameEntry` capture already recorded in
`findings-ordering-re.md` (2026-09-13, "Ground truth captured") shows the real order starts
`DavesBrushBuilders, PlatonicsBuilder, ...` — the self-reference registers BEFORE the class's own
name, not after. The earlier "registers at class-header time" model (from the `RahnemBrushBuilders`
breakthrough) only established self-name < first member; it never pinned self-name vs. the class's
own name specifically, and got it backwards.

**Fix**: `ordering._gather_names` now special-cases a `Class`-kind object (`o.class_name == "Class"`):
`o.name_refs[1]` (PackageImports[0], always the self-reference per `compile-model.md`'s "own package
first" rule) is added before `add(o.disp)`. Scoped narrowly to this one relationship — nothing else
in `name_refs` (FriendlyName dup, other `PackageImports` entries, `ClassConfigName`) is reordered.

**Result**: `DavesBrushBuilders`'s name table is now byte-exact (`test_davesbrushbuilders_name_table_
byte_exact`, replacing the old test that asserted the swap). Full offline uscript suite: 220 passed
(was 219 net of the renamed test), no regressions — `RahnemBrushBuilders`/`FrameBuilder`/
`UnrealShare` (the strict-gate packages) still pass; `RahnemBrushBuilders`'s own self-name-before-
first-member evidence is unaffected (self-name is now even earlier, still before the first member).

`ExtendedBuilders` is UNAFFECTED by this fix (still fails `gate`, still passes `perm_gate` — its
larger tied group is not resolved by this one relationship; not reinvestigated this pass).

`DavesBrushBuilders` still does NOT pass the full strict `gate()` — fixing the name table surfaced a
SEPARATE, previously-hidden EXPORT-table qsort tie (two isolated swapped pairs among tied-refcount
function params/locals), tracked at
`dev/docs/board/inbox/davesbrushbuilders-export-table-qsort-tie/`. This item can move to `done/`
for the NAME-table bug it was scoped to; the export-table bug is a new, separate item.
