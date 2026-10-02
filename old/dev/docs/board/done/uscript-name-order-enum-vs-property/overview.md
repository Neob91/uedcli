+++
priority = "p3"
kind = "debug"
summary = "uscript name order: enum-vs-property interleaving lost past compile, needs AST-order threading"
+++

# uscript name order: enum-vs-property interleaving lost past compile, needs AST-order threading

FIXED 2026-09-13. `DavesBrushBuilders`/`ExtendedBuilders` failed the strict `gate()` on name-table
order (both already passed `perm_gate`). Root-caused 2026-09-13 via a live `AllocateNameEntry`
capture (see `dev/docs/board/to-build/uscript-algorithm-fidelity/findings-ordering-re.md`): UCC
registers names in plain interleaved SOURCE TEXTUAL order — a property and a later `var() enum`
register side by side, exactly as declared — but the COMPILED `.u`'s own `Children` chain bins ALL
properties into one forward sub-chain and ALL non-properties (enums/consts/structs/functions) into a
separate reverse sub-chain, genuinely losing that interleaving (confirmed against the real UCC
golden directly, not just our own output).

**Fix**: `ClassDecl` gained `decl_order` (`uedcli/uscript/ast.py`) — every top-level member/callable
declaration in TRUE source order, populated by `parser.py`'s single top-to-bottom class-body loop
(which already walks the source in this order before splitting into the `members`/`callables`
sublists that lost it). `compile.py`'s new `_top_level_name_order(decl)` expands it to display names
(a `VarDecl` to each of its declared names). `reorder.py`'s `_Decoder.name_creation_order` gained
`class_order`/`top_level_by_class` params: given a class's true top-level order, it walks that
instead of the binned `_decl_forward(class_i)`, recursing into each field's own children exactly as
before (a function's params/locals/struct's members are NOT re-ordered — that substructure is
uniform-kind and was never binned, only the TOP-LEVEL property/non-property interleaving was).
`compile_package`/`compile_package_dir` thread `_top_level_name_order` per class into
`reorder.true_order`'s new params. Omitting both params keeps the old (binned) behavior — no change
for any caller that doesn't supply them.

**Result**: `DavesBrushBuilders`'s name table (74 entries) went from diverging at index 14 (the enum
scatter, with cascading effects through most of the table) to matching golden in ALL BUT ONE pair
(indices 21/22, `Core` vs the package self-name) — a narrower, PRE-EXISTING qsort-tie-permutation bug
(confirmed present, masked, in the pre-fix output too), tracked separately:
`dev/docs/board/inbox/uscript-name-order-core-vs-package-self-name/`. Pinned by
`test_davesbrushbuilders_ast_order_recovers_enum_property_interleaving`
(`uedcli/tests/test_uscript_realpkg.py`). No regressions: full offline uscript suite, 217 passed
(was 216).

`ExtendedBuilders` is UNCHANGED by this fix (still fails `gate`, still passes `perm_gate`) — its
divergence starts at a 9-name tied group (`Core`/`Editor`/`System`/import display names/the package
self-name) that is the SAME bug CLASS as the new Core-vs-self-name item above, not the
enum/property-interleaving bug this item was scoped to. Its multi-class cross-class registration
order is also unverified (see the new item's notes) — not this fix's scope.

A real, separately-verified sub-bug found by the SAME capture was fixed earlier the same session: a
function's body locals register inline (right after that function), not deferred to a trailing pass
— `reorder.name_creation_order`, pinned by `test_davesbrushbuilders_locals_register_inline_not_deferred`.
