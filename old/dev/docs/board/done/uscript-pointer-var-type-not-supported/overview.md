+++
priority = "p3"
kind = "implement"
summary = "DONE — 'pointer' is now a real PointerProperty in _SCALAR_KINDS, no type-tail, PT_POINTER sentinel raises instead of guessing a default"
+++

# uscript pointer var type not supported

`compile._resolve_var_type` raises `NotImplementedError` for `var private native const pointer
X[N];` (a raw native internal field, e.g. `WebRequest.VariableMap`/`WebResponse.ReplacementMap` in
the real UT99/UED22 `UWeb` package: `TMultiMap<FString, FString>`/`TMap<FString, FString>` behind a
C++ pointer). `pointer` isn't in `_SCALAR_KINDS` and isn't a class/enum/struct name, so it falls
through to the "unknown type" raise.

Found compiling real UWeb while validating the `Dependencies`-array counting fix (see
`USCRIPT-COMPILER.md`'s UWeb entry). Worked around in that validation with a scratch-only monkeypatch
(treat `pointer` as an `IntProperty`) — not a real fix, not committed.

Real UCC's on-disk representation for a `pointer` property (`PointerProperty`? `IntProperty`? some
opaque fixed-size blob?) isn't RE'd yet. Blocks `WebRequest`/`WebResponse` (and so all of `UWeb`) from
compiling through the real (unpatched) compiler.

## Fixed (2026-09-13)

`PointerProperty` is confirmed a real UProperty subclass with no type-tail — present in the dumped
global index (`gobjnames_ued22.json`/`gobjobjects_ued22.json`) and in `uedcli/uprops/base.py`'s
closed `PROPERTY_TYPES` set, absent from `_KINDS_WITH_TYPE_REF` (same shape as `IntProperty`/
`FloatProperty`). Added `"pointer": _Kind(prop_class="PointerProperty", ptype=PT_POINTER)` to
`_SCALAR_KINDS` (`compile.py`), where `PT_POINTER` is a local sentinel `_emit_default` raises a named
`NotImplementedError` for instead of guessing a `_SCALAR_ZERO` value — a pointer has no UnrealScript
default-literal syntax and only appears on native classes, which skip unset defaults, so this path is
never actually hit for real content. General (works via the existing `_SCALAR_KINDS` dispatch for
member vars, function params/locals, and array elements alike), not UWeb-specific. Verified against a
fresh live UED22 UCC compile: `pkg_PointerVar` fixture (`test_uscript_package.py`,
`test_pointer_var_static_array_on_native_class`), mirroring real UWeb's `var native const pointer
Ptr[2];` shape. Real UWeb now compiles past this point (see `USCRIPT-COMPILER.md`'s UWeb entry for
its current overall status).
