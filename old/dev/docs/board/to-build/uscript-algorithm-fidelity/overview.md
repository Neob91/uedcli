+++
priority = "p1"
kind = "implement"
summary = "Make the uscript compiler reproduce UCC's algorithm (drop fitted ordering + silent fallbacks)"
depends-on = ["uedcli-unrealscript-compiler"]
+++

# uscript algorithm fidelity — reproduce UCC, no fits/hacks (owner ruling 2026-09-05)

Owner: "Strive for our algorithm to be on par with UCC's. Don't do hacks just to satisfy a single
package scenario." A Fable adversarial review confirmed the gap. Autonomous order reproduction today:
only `UscHello` gets names+imports+exports right; `UscVars` names DIFF, `UscBB` imports DIFF, all
other fixtures DIFF on all three — `perm_gate`'s order/case exclusions hide a near-total absence of
the ordering algorithm.

## A. Ordering — replace the fitted tables with UCC's real algorithm (the big one)
- `global_index.py` `OBJECT_ORDER`/`NAME_ORDER` are FITTED permutations (proof: `NAME_ORDER` puts
  `ScriptText` before boot-intrinsic `Core`/`Class`; no predictive power). DELETE; replace with the
  real global order.
- `compile.py` `_general_orders`/`_obj_streams` is a SECOND, contradictory refcount model missing
  refs (own `Class`, PackageImports own-name, `Children`, both `Dependencies`, `ClassWithin`;
  properties lose their `None` refs+tag name) → wrong TIERS, not just ties. Unify on ONE model.
- Real mechanism (all three tables = gather then count-desc `msvc_qsort`, which is already correctly
  ported in `ordering.py` — only its INPUTS are wrong):
  - **names gather** = global `FName` index order = core.dll `EName` table (intrinsics, @0x10a778c)
    ++ each loaded package's name table in EditPackages LOAD order (deduped) ++ this package's new
    names in COMPILE ENCOUNTER order. RE the encounter order via controlled compiles.
  - **imports gather** = `GObjObjects` creation index (needs the engine object-registration order,
    from a boot dump or DLL RE — not a hand list).
  - **exports gather** = UCC's object-creation order (import pass = class objects; compile pass =
    fields in class-tree order), then count sort. Current `_creation_order`/`_multi_export_order`
    invent "class, ScriptText, fields…" which the goldens contradict (UscFn: local `X` first).
- **FName case**: from the same global pool. `env.py:109` uses the file STEM (`editor` not `Editor`);
  fix by taking casing from the global name pool / package self-name.
- Done → `perm_gate`'s only remaining exclusion is the per-build-random GUID (collapses to strict).

## B. Remove hacks / fixture-shaped scaffolding
- Delete single-class `compile_package`'s package==class assumption + the `order_override` scaffold
  (`compile.py`); `compile_package_dir` is the real path (no back-compat rule).
- Remove `test_uscript_compile.py` `_mask_name_flags` (stale; flags reproduce now).
- Reconcile the two "None index" models (`serialize.py` vs `ordering.py`).

## C. No silent fallbacks (conventions rule) — raise, don't guess
`natives.py:218` `cands[0]` on no arity match; `lower.py:801` flat scope-less catalog fallback;
`compile.py:975` unknown class → silent `Core.<name>`; swallowed load errors (`env.py:110`,
`natives.py:346`); `conimport.py` RandomLabel/`bDisplayAsSpeech` ignored. Each → a clear error.

## D. Unpinned / latent rules to fix or pin
- Inherited-default emission must DIFF vs the super CDO (confirmed latent bug, `compile.py:736`).
- `_auto_emit_defaults` native-OR-transient rule: derive the real mechanism; pin `transient` + a
  native-with-explicit-`X=0` with committed goldens.
- `_VAR_MODIFIER_FLAGS["native"]=0` — UE1 `CPF_Native=0x1000`; pin `var native`, `const`.
- Port UCC `ConversionCost` for operator overload resolution (`natives.py` `_WIDEN` is invented).
- `_function_positions` should use lexer token positions, not a 2nd regex lexer.
- `_compile_order` must handle reference CYCLES (real DX packages are cyclic; it currently drops an
  edge silently) — a two-pass signature graph (collect all in-package signatures before lowering).

## Fine (keep)
`ordering.py` mechanism + `msvc_qsort`; `crc.py`; strict `gate`; ClassFlags/CPF/FUNC enum tables;
`_CLASS_INHERIT_MASK`; `_class_chain`; params→ReturnValue→locals; `ENGINE_NAME_POOL`/
`HIGHLIGHT_NAME_POOL` (reconstructed engine state — though the exact derivation is the DLLs'
`RegisterNames` + core.dll `EName`); all `NotImplementedError`/`LowerError` frontiers (honest).

Sequencing: runs after the conversation emitter frees `compile.py`. A/C/D can share one pass; A is
the make-or-break. Reviews use the Fable model.
