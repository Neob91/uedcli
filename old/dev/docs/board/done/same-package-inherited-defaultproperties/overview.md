+++
priority = "p3"
kind = "debug"
summary = "Same-package inherited defaultproperties override crashes (not a member of super chain)"
+++

# Same-package inherited defaultproperties override crashes (not a member of super chain)

Found (not chased) while building a controlled fixture for a different fix (2026-09-14): a
multi-class package where a subclass's `defaultproperties` overrides a field it INHERITS from a
SAME-PACKAGE super (not a cross-package one) raises:

```
NotImplementedError: inherited default 'Health': not a member of super chain of 'MPBase'
```

Repro shape: `MPBase` declares `var int Health;` with its own default; `MPSub expands MPBase;`
(same package) sets `Health=9` in its own `defaultproperties` without redeclaring the field.
`compile._emit_inherited_defaults`'s super-chain walk apparently only resolves a CROSS-package
super (via `env`/on-disk lookups), not an in-package one (needs the same `_PkgSigGraph`/pass-1-
signature fallback `_build_callables`'s member/function resolution already uses). Not investigated
further — worked around in the fixture that hit it by dropping the override rather than fixing the
compiler. `dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/probe_default_meta_class.py`
originally used this shape before being simplified.

**FIXED.** `_super_field_order` walked the super chain via `graph._locate`, which decodes a COMPILED
export's Children chain — a same-package super mid-compile has none yet. Fixed with an AST-based
fallback: `b.in_pkg_decls` (casefold -> `ClassDecl`, populated in `compile_package_dir`) lets
`_super_field_order` read an in-package super's own properties from its declaration (`members_of`,
forward order — a var's chain position is always forward, only non-var fields ever reverse) instead
of a disk export, then continues up its `super_name`. Regression: `pkg_SamePkgInheritedDefault`
(`test_uscript_package.py`), the exact `MPBase`/`MPSub` repro shape — `perm_gate` byte-exact against
a fresh live UED22 UCC build.
