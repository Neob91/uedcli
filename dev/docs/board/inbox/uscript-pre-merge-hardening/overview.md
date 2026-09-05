+++
priority = "p2"
kind = "chore"
summary = "uscript pre-merge hardening: pin flag maps + latent struct/state Super + default byte-parity"
+++

# uscript pre-merge hardening (from the adversarial Opus re-review)

The 2026-09-05 Opus re-review (board item `uedcli-unrealscript-compiler`, merge gate) confirmed and
fixed the critical finding (export-table Super uncompared/miswired — commit landed). These residual
findings are NOT byte-parity bugs on the current corpus but should be closed before merge:

- **Flag maps unpinned by goldens (medium).** `_CLASS_MODIFIER_FLAGS`, `_VAR_MODIFIER_FLAGS`,
  `_FUNC_MODIFIER_FLAGS`, `CPF_EDIT` (`compile.py`) are RE'd but only `event`/`final`/`input` are
  exercised by a committed golden. Add goldens compiling classes that use each modifier
  (abstract/native/transient/config/globalconfig/localized/simulated/static/singular/`var()`
  editability/…) and assert byte-parity, per the project's "pin every checkable finding" rule.
- **Latent Super omission in struct/state exports (low).** `Export(... super_ref=0 ...)` for
  Struct/State (`compile.py`) is correct only because no fixture has a struct/state that `extends` a
  base; a base-extending struct/state would repeat the function Super bug. Wire + add a golden.
- **Array/enum/struct default emission is only load-tested, not byte-parity'd (low).** Add golden
  byte-parity coverage for dynamic-array / static-array / struct defaults.
- **perm_gate exclusion set is documented in the `gate.py` docstring but `parity.md` was never
  written** — write `dev/docs/unrealed/unrealscript/parity.md` (owner-approved) stating the exact set
  (GUID + table ORDER + FName CASE) and what IS compared (Super, ObjectFlags, bodies, name flags).

Survived the review unchallenged: appStrCrc, the bytecode codec round-trip (3581 fns), lowering
"raise-don't-guess" discipline, and perm_gate's other checks.
