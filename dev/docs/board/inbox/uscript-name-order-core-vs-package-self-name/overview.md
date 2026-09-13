+++
priority = "p3"
kind = "debug"
summary = "uscript name order: Core vs package self-name qsort tie"
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
