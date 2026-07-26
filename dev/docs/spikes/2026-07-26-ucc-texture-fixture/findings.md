# Spike — building an offline texture fixture with the game's own toolchain (UCC)

**Date:** 2026-07-26 · **Status:** complete · **Unblocks:**
[`plans/2026-07-25-native-texture-formats-plan.md`](../../plans/2026-07-25-native-texture-formats-plan.md)
findings F8/F9 (the fixture's provenance and its decode oracle).

## The question

That plan proves its new BC1 (DXT1) decoder by comparing its output against a **P8 copy of the same
image** stored in the same package, and accepting a mean absolute channel error of ≤ 8/255. That is
evidence **only if something other than uedcli encoded both copies** — otherwise the check compares
our compressor against our decompressor and passes when both are wrong the same way.

The original fixture took that pair from a real Deus Ex texture. That is redistribution of
copyrighted content, and the owner ruled it out (2026-07-26): **the fixture must be our own artwork,
compressed by a named third-party encoder.** This spike answers *which* encoder, and whether the
plan's numbers survive the change.

Terms, once. **P8** = one byte per texel indexing a 256-entry palette — UE1's normal texture storage.
**DXT1 / BC1** = a block format storing each 4×4 pixel block as two 16-bit endpoint colours plus 2
bits per pixel. **Mip chain** = the halving pyramid (64×64 → 32×32 → … → 1×1). **`ucc`** = the
game's own command-line tool.

## Harness

`harness/build_fixture.sh` — generates the artwork, drives `ucc make` under wine, and verifies the
result. Needs wine and a Deus Ex install (`$UEDCLI_SPIKE_GAMESYS`). Its **output** is committed under
`fixture/` (20 KB, entirely our own artwork), so the plan's tests need neither wine nor the game.

## Finding 1 — UCC can build the P8 half, and it round-trips BYTE-EXACT

`#exec TEXTURE IMPORT NAME=… FILE=…pcx MIPS=ON` inside a class compiled by `ucc make` imports our
own PCX and **builds the whole mip chain itself**. Measured on the committed fixture:

| | |
|---|---|
| mips built by UCC | **7** — 64×64, 32×32, 16×16, 8×8, 4×4, 2×2, 1×1 |
| format | `fmt = 0` (P8), 256-entry palette |
| uedcli's decode of UCC's mip 0 vs our source artwork | **0.000 / 255** |

So uedcli's P8 decoder is **exactly** correct against the game's own importer, on artwork we authored.
No copyrighted bytes, and the encoder is the game's.

## Finding 2 — UCC CANNOT build the DXT1 half: this toolchain has no DDS importer

`ucc` exposes `mergedxt` (*"Merge DXT textures with standard textures"*, `ucc mergedxt srcpath
oldpath destpath`), and `Editor.dll` contains `UMergeDXTCommandlet` asserting
`i->CompFormat==TEXF_DXT1` — so that commandlet is how a package acquires a `CompMips` array, and it
only handles DXT1. **But it needs a source package that already holds DXT1 textures**, and this
Deus Ex-era toolchain cannot make one: importing a DXT1 `.dds` fails with

```
Bad image format for texture import
ExecWarning, Import texture DdsSpike from Classes\fixture.dds failed
```

(Consistent with the string scan: no DDS/PCX/BMP format vocabulary in `UED22/*.dll`; `D3D9Drv.dll`'s
`DXT1/DXT3/DXT5` strings are the *renderer's* surface formats, not an importer's.)

**Consequence for the plan:** the DXT1 payload comes from **Pillow's DDS writer**
(`Image.save(..., format="DDS", pixel_format="DXT1")`, verified on Pillow 12.3.0), which is
third-party to uedcli and already the repo's only runtime dependency. The oracle's independence is
preserved: the reference image is UCC's, the compressed copy is Pillow's, and only the container is
ours.

## Finding 3 — UCC reports SUCCESS when an `#exec` import fails

Both failures above printed `Success - 0 error(s), 1 warnings` and still produced a `.u`. This
independently reproduces the friction log's rule (*"Never trust `ucc`'s exit code or its `Success`
line — the only usable oracle is the artifact"*). The harness therefore greps the log for
`ExecWarning` / `Can't find file` **and** asserts on the artifact. Note the log must be filtered for
wine's own `err:ntoskrnl: … failed` lines first, or the guard fires on wine noise.

## Finding 4 — the artwork must have features WELL ABOVE the 4×4 block size

The first attempt used a 4-pixel checker — exactly DXT1's block size, which is adversarial to the
format. Measured mean absolute channel error of a **correct** decode against UCC's P8:

| artwork | correct decode | verdict
|-----------------------------------|----------------|---
| 4px checker (= block size) | **13.043** | fails the plan's own ≤ 8/255 bound
| smooth 2-axis gradient | 3.182 | fine
| **gradient + 16px quadrants** | **2.831** | chosen — comparable to the 1.98 measured on the real texture
| radial + diagonal edge | 3.756 | fine

So the plan's ≤ 8/255 bound **does transfer** to a synthesized fixture, but only with artwork chosen
for it. The committed fixture is the third row.

## Finding 5 — the mean-error oracle CANNOT catch an index-decoding bug

Measured on the committed fixture, against three deliberately-broken BC1 decoders:

| decode | error | ratio vs correct | caught by ≤ 8/255?
|-----------------------------------|--------|------------------|---
| correct | 2.831 | — | —
| colour endianness swapped | 98.035 | 34.6× | yes
| c0/c1 endpoints swapped | 40.661 | 14.4× | yes
| **index bit-offset off by one** | **4.801** | **1.70×** | **NO — 4.80 < 8**

**This refutes the plan's claim that the bound "discriminates by ~10×".** It discriminates *gross
layout* errors by 14–35×, and does not discriminate an index-level error at all: a bit-offset bug
scores inside the pass mark and ships green. The ratio stayed 1.3–1.7× across every artwork tried,
because shifting the index bits still selects from the same four per-block colours, so the error is
bounded by intra-block variation.

**The plan needs a second, exact pin for that class** — a byte-exact comparison of the decoded blocks
against a stored expected buffer, not a tolerance. The tolerance test keeps its value for layout
errors; it must not be described as covering index decoding.

## What the plan should now say

1. **Fixture provenance:** our own generated artwork; **P8 mips built by `ucc make`**; **DXT1 blocks
   written by Pillow**; container assembled by `pkgfixture`. No game content. `fixture/` here is the
   committed output, so no test needs wine.
2. **Bound:** keep ≤ 8/255, and record it as **measured at 2.831 on this fixture** — not the 1.98
   measured on the retired one.
3. **Coverage:** state that the tolerance check covers layout/endpoint errors only, and add a
   byte-exact pin for index decoding.
4. Delete the two surviving "real payload lifted" claims (plan F8).

## Committed artifacts

`fixture/UccFix.u` (7,702 B — UCC's package, 7 P8 mips), `fixture/fixture.pcx` (2,983 B — the source
artwork), `fixture/fixture.dds` (2,176 B — Pillow's DXT1 of the same image). All ours; nothing
derived from the game.
