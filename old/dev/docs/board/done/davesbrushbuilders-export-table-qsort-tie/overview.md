+++
priority = "p3"
kind = "debug"
summary = "DavesBrushBuilders export table qsort tie (found while fixing the name-table Core/self-name tie)"
+++

# DavesBrushBuilders export table qsort tie

FIXED 2026-09-13. Not a qsort bug: `reorder.true_order` fed the export gather the old binned
`_decl_forward` walk after the name gather had already been switched to the AST-derived true
top-level order (the enum-vs-property interleaving fix). Object creation and FName registration are
the SAME single top-to-bottom declaration walk in real UCC, so both gathers need the same order.
`reorder._Decoder.creation_order()` (export-only) is removed; `name_creation_order()` (now the sole
gather-order source) feeds both `order_package` args in `true_order`. `DavesBrushBuilders` passes the
strict `gate()` outright. `ExtendedBuilders`'s open name-table diff is unaffected — a different tie
group, unresolved. `uedcli/uscript/reorder.py`, `uedcli/tests/test_uscript_realpkg.py`.
