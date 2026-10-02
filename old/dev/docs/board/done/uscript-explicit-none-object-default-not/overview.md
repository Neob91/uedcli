+++
priority = "p3"
kind = "implement"
summary = "DONE — explicit object defaults now resolve via _object_default_ref (the same helper the inherited-default path already used), not an unconditional raise"
+++

# uscript explicit `Foo=None` object default not supported

`compile._emit_default` raises `NotImplementedError("explicit object default for %r not supported
yet")` for ANY explicit `defaultproperties` entry on an object-typed property, unconditionally —
including `Foo=None`, which is the SAME value the property would get anyway if left unset (the
zero-object tag, `Prop(pname, PT_OBJECT, 0)`). Real UWeb hits this on `WebApplication.WebServer=None`
and `WebConnection.WebServer=None`.

Found compiling real UWeb while validating the `Dependencies`-array counting fix (see
`USCRIPT-COMPILER.md`'s UWeb entry). Worked around in that validation with a scratch-only monkeypatch
(treat any explicit object default as the zero tag) — not verified against a live UCC compile, not
committed as a real fix. A genuine non-None explicit object default (`Foo=SomeClass'Bar'`) is a
separate, still-unimplemented case this workaround did not address either.

Blocks `WebApplication`/`WebConnection` (and so all of `UWeb`) from compiling through the real
(unpatched) compiler.

## Fixed (2026-09-13)

`_emit_default`'s `PT_OBJECT` branch now resolves the explicit value (if any) through
`_object_default_ref` — the same helper the INHERITED-default path (`_emit_inherited_defaults`)
already used, which handles `noneconst` -> 0 and a genuine `Class'X'`/object-literal -> a deferred
ref, and still raises for anything else. No special-casing of `None` specifically: any explicit own
object default that `_object_default_ref` can resolve now works, not just `Foo=None`. Verified
against a fresh live UED22 UCC compile: `pkg_ExplicitNoneDefault` fixture
(`test_uscript_package.py`, `test_explicit_none_object_default_same_as_unset`), mirroring real
UWeb's `WebApplication.WebServer=None`/`WebConnection.WebServer=None` shape. Real UWeb now compiles
past this point (see `USCRIPT-COMPILER.md`'s UWeb entry for its current overall status).
