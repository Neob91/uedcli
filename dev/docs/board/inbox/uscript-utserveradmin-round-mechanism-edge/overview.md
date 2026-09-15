+++
priority = "p3"
kind = "investigate"
summary = "uscript: UTServerAdmin-round mechanism edge cases needing live verification"
+++

# uscript: UTServerAdmin-round mechanism edge cases needing live verification

Found in code review of the `UTServerAdmin` corpus win (commits `e6ce4a3d`/`9b46a69d`). None are
exercised by any current fixture, so none are proven wrong — but none are measured either. Settle
each with a controlled fixture + live UCC before trusting it on a future package.

1. **FUNC_Net/RepOffset dropped across a 3-level same-package override chain.** `_prepass_signatures`
   (`compile.py`, `_build_class_unit`'s pass-1 pre-pass) inherits a function's FuncBody from its super
   via `functions.update(sup.functions)`, then unconditionally overwrites an own-declared/overridden
   function with a fresh `FuncBody(flags=...)` that has no FUNC_NET/rep_offset. If same-package class
   A overrides a `FUNC_Net` function inherited from a disk ancestor, and same-package class B extends
   A and overrides it again, B's override loses the replication flags A had inherited.

2. **`ConfigName` inheritance only fires for an EXPLICIT bare `config;` modifier**, not for a subclass
   of a `config(X)` class that writes no `config` keyword at all (`_class_header`, `compile.py:535`).
   The function's own docstring already flags this as untested/unguessed — this item just tracks it
   as open rather than leaving it undiscoverable.

3. **`_record_dep` no longer skips a Context through a SUPER-typed reference** (only self-typed is
   pinned by the `SelfDep` fixture) — dropping the old `super_name` skip may be consistent with the
   already-established "one Dependency entry per syntactic Context occurrence, never deduped by
   class" rule (see `USCRIPT-COMPILER.md`'s cross-class-Dependency finding), or may not be; unverified
   either way for THIS specific shape (`lower.py` around `_record_dep`).

4. **`_prepass_signatures` never clears a stale `class<T>` meta-class entry** when a same-package
   subclass redeclares an inherited `class<T>`-typed member as a plain type — unlike the disk-based
   `ClassGraph.class_sig`, which does `member_meta.pop(nm_cf, None)` in that case (`compile.py`
   around line 2204).

5. **A Context through a cast to an IMPORT-ONLY class (no export anywhere, e.g. `Engine.NetConnection`)
   records no Dependency entry** — `lower._record_dep`'s `class_sig(cf) is None` early-return, new
   parity gap opened by the same fix that made the cast itself compile (`Scope.is_known_class`).
