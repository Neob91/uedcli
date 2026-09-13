+++
priority = "p2"
kind = "implement"
summary = "wire #exec TEXTURE IMPORT into uedcli's uscript compiler (RE done, plumbing not started)"
spikes = ["dev/docs/spikes/2026-09-13-texture-import-re/"]
+++

# uscript texture import: compiler integration

`#exec TEXTURE IMPORT` is one of the uscript-compiler campaign's scoped-out `#exec` types
(`USCRIPT-COMPILER.md`); it blocks a real community package (`GiveMeItems`, one line in
`GMIClientWindow.uc`) from compiling at all. The RE is done — `dev/docs/spikes/
2026-09-13-texture-import-re/spike.md` — but nothing is wired into `uedcli/uscript/compile.py`.
`_reject_unsupported` still rejects TEXTURE IMPORT.

## What the spike settled

- Export/name/import table shape for the new `UPalette` + `UTexture` pair (structural — falls
  straight out of `ordering.py`'s existing `ObjInput` machinery once fed correctly).
- The PCX 8bpp/RLE decode.
- The mip-chain quantization algorithm: box-average the true palette-resolved RGB recursively from
  the original pixels, then search the WHOLE palette for the luma-weighted (79, 158, 19) nearest
  match. Verified against 4 independent live-UCC probes with zero exceptions outside exact ties.
- `harness/mip_formula.py` in the spike dir is a ready-to-use, already-tested implementation of
  that algorithm — reuse it rather than re-deriving.

## What's still open (read the spike before touching either)

1. **`InternalTime`** (a `UTexture` property) is per-compile non-deterministic, like the package
   GUID — but it is a SECOND non-deterministic field, not yet an approved exclusion.
   `USCRIPT-COMPILER.md`'s `gate()` currently excludes only the 16-byte GUID. Needs an owner
   decision (a candidate-exclusion review, same bar as any other `NATIVE-MATERIALIZE.md`-style
   exclusion) before any texture-bearing package can pass the strict gate — ask via
   `AskUserQuestion`, do not just add the exclusion.
2. **The mip-quantization tie-break** is unresolved for the (rare, real-content-unlikely) exact-tie
   case — spike.md's "Open: the tie-break rule". Not a blocker for real content; document the gap
   in `compile-model.md` when this lands, don't guess a rule.
3. **Plumbing**: `compile.py`'s `_reject_unsupported` needs a texture-import carve-out (mirroring
   the `_CONV_IMPORT_RE` one), a builder analogous to `conimport.py` that emits the `ObjInput`s +
   serialized bodies for the new `UPalette`/`UTexture` exports INTO the compiling package (not a
   sibling package, unlike conversation import), and `serialize.py` needs to write a `UPalette`
   body (compact-index count + `TArray<FColor>`, alpha always `0xFF`) and a `UTexture` body (the
   tagged-property list documented in the spike, then `Mips`/`CompMips` via the SAME encoding
   `uedcli/utexture.py` already decodes).
4. Once wired: compile a real `GiveMeItems`-style fixture (or `GiveMeItems` itself, if its other
   classes compile cleanly) and verify against the strict `gate()`.

## Doc updates once this lands

`dev/docs/unrealed/unrealscript/compile-model.md` gets a "`#exec TEXTURE IMPORT`" section (mirroring
its "defaultproperties block" style); `USCRIPT-COMPILER.md`'s status table gets a new row.
