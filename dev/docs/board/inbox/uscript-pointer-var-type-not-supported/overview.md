+++
priority = "p3"
kind = "implement"
summary = "uscript compiler has no 'pointer' var type, blocking real UWeb (WebRequest/WebResponse)"
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
