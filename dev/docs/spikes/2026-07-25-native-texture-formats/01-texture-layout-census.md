# Texture layout census — how often the mip chain decides, and what the format codes say

**Date:** 2026-07-25, re-measured 2026-07-26 and 2026-07-27 · **Status:** complete

This is the **evidence** behind uedcli's native texture decoder. The format facts it establishes
live in [`../../unrealed/package-format.md`](../../unrealed/package-format.md) ("UTexture" and
"Which pixel layout is it?"); this file records *how they were measured*, over which corpora, so
the next reader can re-derive or challenge them. A test constant records what we expect and never
how it was found, which is why this is written down separately.

Terms, once. **P8** = one byte per texel indexing a 256-entry palette, UE1's normal storage.
**BC1/BC2/BC3** (vendor names DXT1/DXT3/DXT5) = block formats storing each 4×4 pixel block in 8 or
16 bytes. **Mip chain** = the halving pyramid, 256×256 → … → 1×1. **`Format`** = a numeric
`ETextureFormat` slot stored as a tagged property on the texture.

## Method

`utexture.load_package` plus a body parse that reads the tagged-property list, then `Mips`, then —
when the `bHasComp` property is true — `CompMips`, over every package under each root. Layout
candidates were computed by the same size rules the shipped `utexture.detect_layout` uses:
`n == w·h·N` for `linear{N}`, `n == ⌈w/4⌉·⌈h/4⌉·B` for `bc{B}`.

Roots, and whether a fresh checkout has them:

| corpus | path | committed? |
|-----------------------|--------------------------------------------------|---|
| **UED22 editor**      | `<repo>/uned/UED22/` | **yes** — 214 tracked files |
| **committed fixtures**| `<repo>/uedcli/tests/fixtures/*.utx` | **yes** |
| **Deus Ex install**   | outside the repo, reached via the tracked `uned/DeusExAssets` symlink | no |
| **Unreal Gold** (227i-patched; its `System/Engine.u` is the stock 8-slot build) | outside every repo, no in-tree pointer | no |

**The enumeration rule matters and must travel with any count.** Counting packages as RECURSIVE +
EXTENSION-EXACT `{.u,.utx,.uax,.umx}` over `uned/UED22` gives **34 packages / 1,998 `Texture`
exports** — the figures used everywhere below and in the tests. A loose `*.u*` glob also catches
the tracked `DeusEx.u.bak` (35 / 2,002); top-level-only misses two nested `Engine.u` copies
(32 / 1,934). All three are defensible; only one matches the asserted numbers.

**And state the unit.** *Textures* counts one `Mips` chain per `Texture`-classed export. *Mip
arrays* counts `Mips` plus each `CompMips`. They differ by exactly the 69 `CompMips` arrays.

## 1. What failed before `CompMips` support, and why

| corpus | pkgs | `Texture` exports | failed | explained by `CompMips` |
|-----------------------------------------------------|-------|--------|------|---|
| DX `System`+`Textures`(+`Maps`, which adds no textures) | 232 | 5,018 | 39 | 39 / 39 |
| whole DX tree (`drive_c/DX`, incl. LUM + the TNM mod)   | 1,154 | 33,262 | 207 | 207 / 207 |
| `LUM/Textures`                                          | 6 | 418 | 30 | 30 / 30 |
| …of which `LUM_CoreTex.utx` alone                       | 1 | 253 | **30** | 30 / 30 |
| `uned/UED22`                                            | 34 | 1,998 | 0 | — |
| Unreal Gold                                             | 268 | 10,742 | 0 | — |

`CompMips` explains **100 %** of `Texture`-class parse failures on every root measured. Every
`bHasComp` texture measured is `(Format ⇒ 0, CompFormat = 3)` — a P8 original with a DXT1 copy:
39 + 30 = **69 of 69** over Deus Ex + LUM, **207 of 207** over the whole tree.

Two end-to-end samples, both EOF-clean:

- `LUM_CoreTex.utx:ClenGreyWndow_C` (v69) — `Mips` P8 64×64 → 1×1, seven mips
  (4096, 1024, 256, 64, 16, 4, 1 B); `CompMips` DXT1, seven mips (2048, 512, 128, 32, 8, **8**,
  **8** B — the 8-byte block floor).
- `LUM_CoreTex.utx:quadrocks_logo_02` (v69) — `Mips` P8 512×128 → 1×1, ten mips bottoming out at
  8×2, 4×1, 2×1; `CompMips` DXT1 512×128 (32,768 B) → 1×1 (8 B).

**The earlier "147/147" figure reproduces against no single root** — measured, the counts are 39,
30, 69 and 207 depending on the root, and none is 147. What is invariant is the ratio above.

Separately, **procedural textures carry mips whose `DataCount` is 0** — over the whole DX tree:
208 `FireTexture`, 42 `WetTexture`, 14 `WaveTexture`, 8 `IceTexture`, 50 `ScriptedTexture`, 4
`TNMScriptedTexture`; over Unreal Gold: 153 `FireTexture`, 78 `WetTexture`, 7 `IceTexture`, 4
`WaveTexture`. **Only `FireTexture` also trails bytes** (a `TArray<FSpark>`, 8 B per spark matching
`NumSparks`); the others end clean. So "carries no pixels" is detectable from the data, never from
a class name.

## 2. How often the chain is decisive

A `w × h` mip of `w·h` bytes is byte-identically explained by P8 (`w·h·1`) and by BC2/BC3
(`⌈w/4⌉·⌈h/4⌉·16`) whenever both dimensions are multiples of 4. The chain only becomes decisive
once it descends **below one block**.

**Per texture** (one `Mips` chain each):

| corpus | chains | fit exactly ONE layout | fit ≥ 2 (need the tiebreak) |
|--------------------------------|------------|-------|---|
| DX (`System`+`Textures`+`Maps`) | 5,018 | 3,656 | 1,362 |
| `LUM/Textures` | 418 | 416 | 2 |
| `uned/UED22` | 1,998 | 861 | 1,137 |
| Unreal Gold | 10,742 | 4,916 | 5,826 |
| **total** | **18,176** | **9,849** | **8,327 (45.8 %)** |

**Per mip array** (`Mips` plus every `CompMips`): **18,245** arrays, **9,918** fitting one, the same
**8,327** ambiguous — the 69 `CompMips` arrays all fit `bc8` uniquely, so they add zero ambiguity.

So the `Format`-code tiebreak is **not an edge case with two samples** — it is the deciding path
for nearly half the corpus.

**Of the 1,137 ambiguous UED22 chains, 1,089 fit `{linear1, bc16}` and 48 fit `{linear1, bc8}`**
(re-measured 2026-07-26). That is what forces the word *uniquely* into the universality claim:
`uwindow.u:WhiteTexture` (32×32 truncated at 4×4) and `DeusExUI.u:HUDItemsBorder_Center` (64×2,
128 B) are code-less chains that also fit a block layout, and the implied `Format = 0` decodes them
as P8.

**How the ambiguity resolves** (per-texture unit, all four corpora):

| population | count | how it resolves |
|-------------------------------------------|-------|---|
| chains fitting exactly one layout | 9,849 | data alone; the code is not consulted |
| …of those, fitting something other than P8 | 8 | all eight store a code, and all eight name a mapped layout |
| chains fitting ≥ 2 layouts | 8,327 | the tiebreak |
| …resolved by a **stored** code | 3 | `SolModifié`, `Flotte`, `Uebergang3` — all `Format=7` |
| …resolved by the **implied 0** | 8,324 | P8 is a fitted candidate in **all** of them |
| ambiguous, P8 NOT a candidate, no stored code | **0** | so the ambiguous-layout error fires zero times |
| chains fitting **zero** layouts | **0** | — |
| exports storing a `Format` property at all | 11 | §3 lists every one |

## 3. Every stored `Format` code in existence here

`Format` is physically present on **11 of 18,176** texture exports (0.06 %), all in Unreal Gold.
This is the *complete* real-world evidence that a code never contradicts its own data:

| export | code | mip 0 | fitted candidates |
|-------------------------------|------|--------------------------------|---|
| `UnrealShare.u:TranslatorHUDHD` | 7 | 2048×2048, 4,194,304 B | `bc16` only |
| `DmRiot.unr:Poster01` | 7 | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster02` | 7 | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster03` | 7 | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Screenshot` | 7 | 512×512, 262,144 B | `bc16` only |
| `DmRiot.unr:SolMurJonction` | 7 | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Fenêtres` | 7 | 256×128, 32,768 B | `bc16` only |
| `DmRiot.unr:SolModifié` | 7 | 128×128, 16,384 B (**single mip**) | `linear1` + `bc16` |
| `DmRiot.unr:Flotte` | 7 | 64×64, 4,096 B (**single mip**) | `linear1` + `bc16` |
| `DMBeyondTheSun.unr:Uebergang3` | 7 | 256×128, 32,768 B (**single mip**) | `linear1` + `bc16` |
| `DmExar.unr:Screenshot` | 3 | 256×256, 32,768 B (**single mip**) | `bc8` only |

Every one is consistent with its own data. The lone `Format = 3` fits `bc8` uniquely at 0.5 B/px,
so **BC1 is decidable from a single mip**. The multi-mip `Format = 7` chains floor at **16 B**
(`Poster01`: … 8×8 = 64, 4×4 = 16, 2×2 = **16**, 1×1 = **16**), and `Fenêtres` supplies the
non-square partial-block case (4×2 = 16, 2×1 = 16).

**The BC3 identification.** All **4,096** of `Poster01` mip 0's blocks carry the alpha half
`0005ffffffffffff` — one distinct value across the whole mip. Decoded as **BC3** that block is
uniformly opaque (`a0 = 0 ≤ a1 = 5` selects the six-interpolant mode, and every 3-bit index is 7 ⇒
alpha 255). Decoded as **BC2** the same eight bytes are sixteen explicit 4-bit values
`0,0,0,5,15,15,…` ⇒ alpha 0 / 85 / 255 noise. One value across a whole mip is nonsense for
per-texel alpha and exactly what a fully-opaque BC3 export looks like. That asymmetry is the
identification.

## 4. The three `ETextureFormat` enums — why no per-game table

Dumped through the existing `uprops.enum_values` (re-run 2026-07-27 for the tracked one):

| install | slots | 0 | 3 | 6 | 7 | 8 |
|---------------------------------|-------|---|---|---|---|---|
| Unreal Gold `Engine.u` (v69) | 8 | `TEXF_P8` | `TEXF_DXT1` | `TEXF_DXT3` | `TEXF_DXT5` | *(undefined)* |
| UED22 / 227 `Engine.u` (v69) | 122 | `TEXF_P8` | `TEXF_BC1` | `TEXF_BC2` | `TEXF_BC3` | **`TEXF_BC4`** |
| Deus Ex `Engine.u` (v68) | 5 | `TEXF_P8` | `TEXF_DXT1` | *(undefined)* | *(undefined)* | *(undefined)* |

227's first twelve slots: `P8, BGRA8_LM, R5G6B5, BC1, RGB8, BGRA8, BC2, BC3, BC4, BC4_S, BC5,
BC5_S`. **122 slots, not the 118 an earlier draft recorded.**

**Slot numbers are NOT portable.** Slot 2 is 8 bytes/px in Unreal Gold (`RGB64`) but 2 bytes/px in
227 (`R5G6B5`) — a hardcoded table would mis-slice real data and then emit a *bogus* size mismatch,
turning an honest failure into a wrong diagnosis. That measurement is what killed the table.

**All three agree on 0 and 3; the two that define 6 and 7 agree on both, and Deus Ex is SILENT on
them** — five slots. Be precise: it is *not* true that all three agree on 6/7; one says nothing, so
it cannot contradict. DXT1 ≡ BC1, DXT3 ≡ BC2, DXT5 ≡ BC3.

**Slot 8 is why the veto exists.** `TEXF_BC4` is a single-channel **8-byte-block** format, so its
mip chain is byte-for-byte the size of BC1's and fits `bc8` *uniquely*. A "unique fit always wins"
decoder draws a BC4 texture as BC1: a confident wrong image on a file whose own code says it is not
BC1. Slot 9 (`BC4_S`) collides the same way; slots 10/11 (`BC5`, `BC5_S`) are 16-byte blocks and
collide with `bc16`.

## 5. The decode oracles, and what each one can and cannot catch

**Pillow 12.3.0** (uedcli's only third-party runtime dependency) decodes DXT1/DXT3/DXT5 from a
hand-built 128-byte DDS header at every edge shape the corpus contains — 4×4, 2×2, 1×1, 8×2, 4×1,
2×1, 512×128. Its conventions, checked exhaustively:

- RGB565 → 888 by **bit replication** (`(v<<3)|(v>>2)` and `(v<<2)|(v>>4)`), verified over all 32
  and all 64 values with **zero** mismatches. It is *not* `round(v·255/31)`.
- The 1/3 and 2/3 interpolants are the plain integer `(2a+b)/3` — white/black endpoints give 170
  and 85.

So **byte-exactness against Pillow is achievable**, not merely a tolerance.

**The `CompMips` pair** — the same picture stored twice by two different encoders. Mean absolute
channel error, our P8 decode vs Pillow's DXT1 decode of the same texture's `CompMips`:

| texture | mip 0 | mip 1 | mip 2 | mip 3 |
|----------------------------------|-------|-------|-------|---|
| `LUM_CoreTex:quadrocks_logo_02` | 0.605 | 1.623 | 3.083 | 3.991 |
| `LUM_CoreTex:ClenGreyWndow_C` | 1.980 | 4.316 | 5.717 | **8.469** |

Two conclusions an earlier draft got wrong: the bound **must be mip-0-only** (mip 3 already exceeds
8/255), and **a wrong decode does not reliably score 60–80** — four deliberately-wrong controls
over these two textures scored 20.3, 35.9, 39.3 and 62.0.

**And the tolerance cannot catch an index-decoding bug at all.** Measured against the committed
synthesized fixture (see [`../2026-07-26-ucc-texture-fixture/findings.md`](../2026-07-26-ucc-texture-fixture/findings.md)
§5): a colour-endianness swap scores 98.0 (34.6×) and a c0/c1 endpoint swap 40.7 (14.4×), but an
**index bit-offset off by one scores 4.801 (1.70×) and PASSES ≤ 8/255**. The ratio stayed 1.3–1.7×
across every artwork tried, because shifted index bits still select from the same four per-block
colours, so the error stays bounded by intra-block variation. **The tolerance covers layout and
endpoint errors only**; index decoding needs the byte-exact comparison.

## Where the findings are pinned

`uedcli/tests/test_utexture_corpus.py` (the offline census, the four-slot map, the tracked 227
enum), `test_utexture_corpus_installs.py` (both installs, the eleven stored codes, the other two
enums), `test_utexture_layout.py` (the arbitration rows), `test_utexture_blocks.py` (the Pillow
conventions and the block decoders).
