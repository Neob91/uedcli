# `#exec TEXTURE IMPORT` — RE toward a byte-exact implementation

Started for the uscript-compiler campaign's path-to-30-packages work (a real community package,
`GiveMeItems`, is blocked on exactly one `#exec TEXTURE IMPORT` line). Scope: RE UCC's PCX import
and mip-chain generation well enough to serialize a byte-exact `UTexture`/`UPalette` pair. All
findings measured against a live UED22 `UCC.exe` via `uedcli/uscript/reference.ucc_compile`
(`extra_files` param added there to stage a PCX alongside the `.uc` source).

## Method

Every probe is a one-class package with a single `#exec TEXTURE IMPORT NAME=... FILE=Textures\...PCX
LODSET=0` directive, importing a tiny hand-built 8bpp RLE PCX (`harness/pcx.py`). `harness/
rebuild_probes.py` builds all of them against a live container in one pass; the resulting `.u` files
are the committed goldens (`golden_*.u`), decoded via `uedcli/utexture.py` (already-established,
UCC-batchexport-validated `UTexture`/`UPalette` body reader).

## Format — solid, structural findings

- The directive creates the `UTexture` **inside the compiling package** (unlike `#exec CONVERSATION
  IMPORT`, which emits sibling packages) plus an auto-created `UPalette` sibling EXPORT (also inside
  the same package), named `Palette1` for the first (only tested) texture import in a class.
- Export order (`ScriptText, Palette1, <ClassName>, <TextureName>`) and every name/import table entry
  reproduce through the EXISTING `ordering.py` machinery once fed the right `ObjInput`s — nothing
  texture-specific about the sort itself.
- `UPalette` body: tagged-property list (empty for a plain PCX import) terminated by `None`, then a
  `TArray<FColor>` — compact-index count (256), then 256 × `(R, G, B, 0xFF)`. Alpha is always `0xFF`.
  Preserves the PCX's 256-entry palette verbatim, in order.
- `UTexture` body: tagged properties `LODSet` (BYTE, `0` when `LODSET=0`), `Palette` (OBJECT ref to
  the `UPalette` export), `UBits`/`VBits` (BYTE, `log2` of width/height), `USize`/`VSize`/`UClamp`/
  `VClamp` (INT, image dimensions), `MipZero`/`MaxColor` (STRUCT `Color`, 4 bytes — see below),
  `InternalTime` (INT — **non-deterministic**, see below) — then `Mips`, a `TArray<FMipmap>` exactly
  like `uedcli/utexture.py` already reads: mip 0 is the source pixels verbatim, and a texture always
  gets a FULL mip chain generated down to 1x1 regardless of any import option.
- Two clean compiles of identical source (same PCX) differ in exactly two places: the package's
  16-byte GUID (**already** the campaign's sole documented exclusion) and `InternalTime`'s 4-byte INT
  value — confirmed by building the same fixture twice and diffing (only 21 bytes differ total: 16
  GUID + 4 InternalTime + 1 unexplained but ADJACENT to InternalTime, likely a compact-index length
  boundary artifact of the differing INT value, not a third independent field). **This needs a new,
  owner-approved exclusion** before any texture-bearing package can pass the strict `gate()` — see
  `USCRIPT-COMPILER.md`.

## Mip-chain quantization — the load-bearing finding

Every level beyond mip 0 is **not** a re-quantization of the previous (already-quantized) level; it
is the palette-resolved RGB **box average of the corresponding block of the ORIGINAL mip-0 pixels**,
computed once per level in full precision, THEN quantized. Confirmed by `Asym4x4`: its 1x1 level (a
2-level reduction) matches averaging all 16 original pixels (5.6875 → 6) but not averaging the
already-rounded 2x2 level's four bytes (2+5+15+0)/4 = 5.5 (also 6, but the two math paths coincide
here only because both landed at the same final integer after rounding — `mip_formula.py` implements
the ORIGINAL-pixels version, the only one distinguishable in principle).

Quantization is a **palette search, not naive index averaging**: two theories were tried and
falsified by direct measurement before landing on this one — see "Rejected theories" below. The
working formula:

1. `target = box_average(original 2x2 block's true RGB, resolved through the texture's own palette)`
   (recursed for a deeper chain — always from the true original colors, never from an intermediate
   quantized byte).
2. Quantized index = `argmin_i` over the WHOLE 256-entry palette of the **luma-weighted squared
   distance** `79*(R_i - target.R)² + 158*(G_i - target.G)² + 19*(B_i - target.B)²`. Weights sum to
   256 (a `>>8` fixed-point scale); no standard named luma constant (BT.601, BT.709, or the common
   77/151/28 approximation) fits.

**Caveat on confidence**: `RedGreen` and `RedBlue` are the only two probes whose target color is OFF
every palette's "natural axis" (a plain grey ramp, or `default_palette`'s single line through the
origin) — every OTHER probe's target lies exactly ON such an axis, where a plain "nearest point on
this line" holds regardless of the per-channel weights (any diagonal weighting projects to the same
point on a 1-D line). So the (79, 158, 19) weights are solved from exactly 2 independent equations
for 2 unknowns (given the constraint that they sum to 256) — a fit, not an over-determined
confirmation. `BlackWhite`'s target (127.5 on every channel) is symmetric and ties regardless of
weights, so it does not further constrain them either; it only confirms the search MAGNITUDE lands
near the right place. A future probe with a target off-axis in a THIRD independent direction (e.g. a
red/yellow mix) would over-determine and truly confirm the weights — not done here.

| Probe | Block colors | Predicted (this formula) | Measured | Match |
|---|---|---|---|---|
| RedGreen | 2×red(255,0,0) + 2×green(0,255,0) | 118.04→118 | 118 | ✅ |
| RedBlue | 2×red(255,0,0) + 2×blue(0,0,255) | 48.81→49 | 49 | ✅ |
| BlackWhite | 2×black + 2×white | 127.5 (exact tie) | 128 | tie — see below |
| Asym4x4 mip2 | 16-pixel true average (linear palette) | 5.6875→6 | 6 | ✅ |

`Gradient8x8`/`Asym4x4`'s non-tie levels and `RedGreen`/`RedBlue` are pinned as regression cases in
`uedcli/tests/test_uscript_textureimport_re.py`, reading the committed goldens with no live UCC
needed.

### Rejected theories (falsified by direct measurement, kept so nobody re-tries them)

- **Plain index averaging** (average the raw palette-index BYTES, ignore color): predicts `RedGreen`
  → 55 (average of 50 and 60), measured 118. Falsified.
- **Unweighted-Euclidean nearest palette search** (equal weight per channel): predicts `RedGreen` →
  85, measured 118. Falsified.
- **BT.709 luma weights (.2126/.7152/.0722)** (as a weighted-nearest search): predicts `RedGreen` ≈
  118.3 (a near-exact, deceptive match) but `RedBlue` ≈ 36.3 against a measured 49 — falsified by the
  SECOND probe. `RedGreen` alone cannot tell BT.709 apart from the real (79, 158, 19) weights (both
  land near 118); only a second, differently-oriented probe (`RedBlue`) separates them. Recorded so
  a future pass doesn't stop at one matching probe and ship the wrong weights.

### Open: the tie-break rule (unresolved)

Three probes hit an EXACT tie (equal weighted distance to two adjacent candidates):

| Probe | Tied indices | Winner |
|---|---|---|
| `Tie` (linear palette, indices 3/4 avg 3.5) | 3 vs 4 | **3** (lower) |
| `Asym4x4` block (0,0) (linear palette, indices 1-4 avg 2.5) | 2 vs 3 | **2** (lower) |
| `BlackWhite` (grey ramp, avg 127.5) | 127 vs 128 | **128** (higher) |

Two of three favor the lower candidate; `BlackWhite` favors the higher one. No rule tried (prefer
lower, prefer higher, prefer even, prefer odd, round-half-up per channel before search, round the
spatial average with an integer `+2>>2` bias before search) explains all three — each fits at most
2 of 3.

`MipZero` (the "average color" summary property) has a RELATED but not identical puzzle, on the same
probes' TRUE unquantized average (not the quantized pixel): `Tie` (10.5/17.5/24.5 → 10/17/24) and
`Asym4x4` (17.0625/28.4375/**39.8125** → 17/28/**39**) both round DOWN — the `Asym4x4` blue channel
is the clean evidence here, since `.8125` isn't a boundary case at all and STILL truncates, ruling out
"round to nearest" as the general rule for this field. But `RedGreen` (127.5/127.5/0 → 128/128/0),
`RedBlue` (127.5/0/127.5 → 128/0/128) and `BlackWhite` (127.5/127.5/127.5 → 128/128/128) all round UP
at an exact `.5`. A pure "always floor" rule is falsified by the second group; a "+2, then divide by
4" rounding bias before the floor is falsified by `Tie` (predicts 11/18/25, measured 10/17/24). No
consistent rule found.

Pinned as `xfail(strict=True)` in the regression test (`BlackWhite`'s pixel-quantization case) rather
than guessed around — per `USCRIPT-COMPILER.md`'s "no hacks, verify against real UCC" rule, a formula
that only fits 2 of 3 measured ties is not "reproduce it," it is a plausible-looking guess, and this
doc says so instead of shipping it silently. **Real content is exceedingly unlikely to hit an exact
tie** (it requires an average landing on an exact `.5` at every relevant channel simultaneously), so
this does not block a first real package from compiling — it would only matter for a pathological,
hand-crafted texture. `MipZero`'s rounding is not separately pinned by a test (it never blocks the
pixel data, which is the part a reader actually sees) — the numbers above are the full evidence.

## What this does NOT cover (compiler integration — not attempted)

This spike stops at "the bytes UCC would write, computed in isolation and checked against captured
goldens." It does NOT wire `#exec TEXTURE IMPORT` into `uedcli/uscript/compile.py`'s dispatch
(`_reject_unsupported` still rejects it), nor into `ordering.py`'s `ObjInput` graph construction, nor
into `serialize.py`'s body writer. That is real, scoped follow-up work — the RE is the expensive
part and is now done; the remaining work is plumbing this into the existing single-class compile path
the same way `conimport.py` plumbed conversation import in, PLUS resolving (or explicitly excluding,
with an owner's yes) the `InternalTime` non-determinism and the tie-break gap above. Tracked at
`dev/docs/board/inbox/uscript-texture-import-compiler-integration/`.

## Files

- `harness/pcx.py` — the minimal 8bpp RLE PCX encoder used by every probe.
- `harness/rebuild_probes.py` — rebuilds every `golden_*.u` from a live UCC (needs docker + UED22).
- `harness/mip_formula.py` — the derived quantization formula, importable and unit-testable.
- `golden_*.u` — the committed live-UCC outputs the regression test and this doc's numbers cite.
