+++
priority = "p2"
kind = "implement"
summary = "#exec TEXTURE IMPORT is wired into the compiler and gates byte-exact (a controlled fixture)"
spikes = ["dev/docs/spikes/2026-09-13-texture-import-re/"]
+++

# uscript texture import: compiler integration

Wired into `uedcli/uscript/texture_import.py` (PCX decode, mip formula, directive parsing) +
`compile.py`/`serialize.py`/`gate.py`. `InternalTime` excluded from both gates (same bar as the
package GUID); the mip-quantization tie-break and `MipZero`'s `.5`-tie rounding are judgment calls,
documented as unresolved in `compile-model.md` and `spike.md`. Controlled single-class fixture
(`UscTexAsym4x4`, no tie on any channel) passes the STRICT gate byte-exact, not just `perm_gate`
(`test_uscript_textureimport.py`).

`GiveMeItems` (the real community package this was scoped for) does NOT fully compile: it needs the
UT99 substrate (now fetched) and hits an unrelated, pre-existing gap on its very next line after the
`#exec TEXTURE IMPORT` — calling an inherited `final` function with no local override finds no import
for it. Filed separately: `dev/docs/board/inbox/calling-an-inherited-final-function-needs-an/`.
