+++
priority = "p3"
kind = "implement"
summary = "explicit 'Foo=None' object default raises, even though it's the same as the type-zero"
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
