+++
priority = "p3"
kind = "debug"
summary = "uscript name order: enum-vs-property interleaving lost past compile, needs AST-order threading"
+++

# uscript name order: enum-vs-property interleaving lost past compile, needs AST-order threading

`DavesBrushBuilders`/`ExtendedBuilders` still fail the strict `gate()` on name-table order (both
already pass `perm_gate`). Root-caused 2026-09-13 via a live `AllocateNameEntry` capture (see
`dev/docs/board/to-build/uscript-algorithm-fidelity/findings-ordering-re.md`'s last section, and
`harness/dump_name_creation_order.py`): UCC registers names in plain interleaved SOURCE TEXTUAL
order — a property and a later `var() enum` register side by side, exactly as declared — but the
COMPILED `.u`'s own `Children` chain bins ALL properties into one forward sub-chain and ALL
non-properties (enums/consts/structs/functions) into a separate reverse sub-chain, genuinely losing
that interleaving. Confirmed against the real UCC golden directly, not just our own output, so this
is not a `reorder.py` decoding bug — the information is gone from any compiled `.u`, ours or UCC's.

`reorder.py`'s whole architecture (`compile.py` compiles provisionally once, serializes, and
`reorder._Decoder` decodes those bytes to derive the real order for a final re-compile) cannot
recover this: it only ever sees post-Children-chain bytes. The fix needs the compiler's own AST-walk
order — available in `compile.py` while it first builds the class, before that order gets binned away
— threaded through to the name-gather step directly, alongside (or instead of) `reorder.true_order`'s
byte-decode reconstruction. Scope: touches `compile.py`'s class-build path and `ordering.py`'s
`_gather_names` input, not just `reorder.py`.

A real, separately-verified sub-bug found by the SAME capture IS fixed: a function's body locals
register inline (right after that function), not deferred to a trailing pass —
`reorder.name_creation_order`, pinned by
`test_davesbrushbuilders_locals_register_inline_not_deferred`. It does not move either package's gate
result on its own; their divergence starts earlier, in the enum/property interleaving above.
