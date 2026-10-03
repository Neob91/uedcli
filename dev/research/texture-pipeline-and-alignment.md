# The texture pipeline — decode, catalog/search, and UV alignment

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** what is the state of texture decoding, agent-facing texture discovery, and UV alignment fidelity — and what are the open problems?

> **Confidence markers** used throughout: **[repo]** = verified in this checkout · **[src]** = read in
> a public UE1 source tree (community mirror of the UT99/licensee source) · **[comm]** =
> community-documented only · **[unver]** = not established.

## Summary

- **Decode is the strongest leg.** Four layouts decode (P8, BC1, BC2, BC3) plus the second
  `CompMips` array; an 18,176-export census found **zero** chains that fit no layout and **zero**
  that go ambiguous, and everything unsupported produces a named refusal rather than a wrong
  picture. The whole path is **integer-exact** — no floats from package bytes to the
  `sha256(w,h,rgb)` identity — so a Rust port can be bit-exact by construction, needing a PNG
  encoder and a BC decoder, not an image library. **[repo]**
- **The "Pillow NEAREST-resample colour derivation" the docs describe does not exist.**
  `old/pyproject.toml:13` and `old/dev/docs/architecture.md:729` both claim a 64×64 NEAREST
  resample pinned to a Pillow floor; `old/uedcli/texture_colors.py` actually uses a flat-index
  stride. The Pillow pin is vestigial for this purpose. **[repo]**
- **That stride aliases badly, and nothing tests it.** `step = w*h // 4096` over a row-major index
  samples only `w/step` distinct columns — 4 of a 1024², 2 of a 2048² (measured). No test file in
  `old/uedcli/tests/` imports `texture_colors` at all, so the palette, the 0.12 share floor, the cap
  of 3 and the tie-break order are all unpinned. **[repo]**
- **Agent-facing discovery is effectively name-grep.** No texture is classified on a clean clone
  (no `texture-catalog/` is committed), so `texture search`'s tag and description tiers are inert
  and "a grimy metal wall texture" returns nothing — every term must match. The project's own
  friction spike says exactly this. **[repo]**
- **Alignment fidelity is excellent and now independently corroborated.** The 2026-07-26 spike's
  nine measured `POLY TEXALIGN` modes reproduce the UE1 source's `UEditorEngine::polyTexAlign`
  verbatim for `WALLDIR`, `WALLPAN`, `DEFAULT`, `ONETILE` (no-op) and `WALLCOLUMN` (no case body),
  including the `0.95`/`0.05` guards and the paired sign flip. **[src]**
- **Two cross-check discrepancies worth a look**: the repo's `FLOOR` row writes `−proj(X̂)`/`−proj(Ŷ)`
  where the UE1 source reads as un-negated `proj`; and `WALLX`/`WALLY`/`CLAMP` do **not** exist in
  stock UE1 (6-value `ETexAlign`) — they are UED22/227-era extensions, which the repo's doc does
  not say.
- **UE1 has no paraxial projection at all.** It always stores explicit per-face U/V vectors, so it
  is structurally the Valve 220 / TrenchBroom "parallel" family, not Quake's `baseaxis` family —
  and `WALLDIR` is near-identical to TrenchBroom's parallel `computeInitialAxes`. The 45° diagonal
  bug was uedcli *opting into* the paraxial artefact via `WALLX`/`WALLY`; the fix was to stop. **[src]**
- Two unguarded engine limits found: `Pan` is `SWORD` (±32767) in the engine but uedcli accepts any
  `int`; and `UTexture::Scale` participates in the renderer's UV divisor but uedcli never reads it.

## What we have today

| Area | Files | LOC |
|---|---|---|
| Package load, mip/palette readers, `TextureResolver` | `old/uedcli/utexture.py` | 1,318 |
| Pixel decoders + layout detection | `old/uedcli/utexture_decode.py` | 329 |
| Procedural-texture painters | `old/uedcli/proceduraltex.py` | ~500 |
| Classification shard store | `old/uedcli/texture_catalog.py` | 252 |
| Colour pre-fill | `old/uedcli/texture_colors.py` | 84 |
| `texture` CLI | `old/uedcli/cli/commands/texture.py` + `cli/parsers/texture.py` | 470 + 167 |
| Alignment solver | `old/uedcli/polyalign.py` | 832 |
| Per-face frame edits (`pan`/`rotate`/`scale`) | `old/uedcli/surface.py` | ~700 |
| Tests | `test_polyalign.py` 97 · `test_surface.py` 92 · `test_utexture.py` 66 · `test_utexture_blocks.py` 26 · `test_utexture_layout.py` 15 · `test_texture_cli.py` 33 | — |

Verbs: `texture list|show|preview|search|prewarm|classify {set,unset,status,tags}`.
`texture sync` is **gone** — `old/dev/docs/architecture.md:699-737` still documents it, along with the
deleted UCC-batchexport/PCX/per-package-manifest catalog.

`brush poly align {wall,floor,run,one-tile,wall-pan}` plus `brush poly {find,set,pan,rotate,scale}`.

## Findings

### 1. Decode: what `utexture.py` reads

The `UTexture` body is a tagged-property list, the `None` terminator, then `Mips`, then — iff the
`bHasComp` **property** is true — a second identically-encoded `CompMips`. Per mip: a `TLazyArray`
skip offset (absolute file offset, present at file version ≥ 63, absent at v61), a compact-index
byte count, the bytes, then `USize`/`VSize`/`UBits`/`VBits`. `UPalette` is a `TArray` of 256 RGBA
with alpha dropped. **[repo** — `old/dev/docs/unrealed/package-format.md:159-199`; corroborated
**[src]** by `Engine/Inc/UnTex.h`'s `operator<<(FArchive&, FMipmap&)` and `UTexture::Serialize`.**]**

That array order is where UELib disagrees — it reads the comp array first. uedcli's order is the
measured one: reading the flags from the property list and parsing `CompMips` immediately after
`Mips` lands exactly on the declared body end for **207/207** previously-failing `Texture` exports
across the whole Deus Ex tree. So the repo settles a conflict the external sources leave open.
Layout is then read off the **data**, not a per-game format table, because slot numbers are not
portable: `ETextureFormat` dumped from three installs has 8 slots (Unreal Gold v69), 122
(UED22/227 v69) and 5 (Deus Ex v68), and slot 2 is 8 bytes/px in one and 2 bytes/px in another. The
`Format` byte may only break ties and veto. **[repo]**

#### Decode coverage

| Layout | UE1 slot | Detected | Decoded | Evidence / why not |
|---|---|---|---|---|
| `linear1` (P8 + palette) | 0 | yes, from data | **yes** | byte-identical to `UCC batchexport`'s PCX over the whole DX corpus |
| `bc1` (DXT1/BC1) | 3 | yes, from data | **yes** | byte-exact vs Pillow's DDS decoder, all 32/64 RGB565 endpoint values |
| `bc2` (DXT3/BC2) | 6 | code only | **yes** | size-identical to BC3; only the code separates them |
| `bc3` (DXT5/BC3) | 7 | code only | **yes** | ditto |
| 16-byte block, no code | — | — | refused | `ambiguous-alpha` — the stated limit on universality |
| `linear2` (`R5G6B5`/`RGB16`) | 2 | yes | no | `unverified-format`; zero samples on this machine |
| `linear3` (`RGB8`/`RGB24`) | 4 | yes | no | `unverified-format` |
| `linear4` (`RGBA7`/`BGRA8`, `RGBA8`/`BGRA8`) | 1, 5 | yes | no | `unverified-format`. **[src]**: slot 1 is a lightmap/fogmap format (0..127 → 0..2.0) and slot 5 is **BGRA** byte order, not RGBA — relevant when the board item lands |
| `linear8` (`RGB64`) | 2 (Unreal Gold) | yes | no | `unverified-format` |
| BC4+ | 8+ (227) | vetoed | no | row 2 veto: a BC4 chain is byte-identically BC1-sized |
| procedural (`FireTexture`, `WaveTexture`, `WetTexture`, `IceTexture`) | — | `no-mip-data` | **painted** | one static frame from the stored body; `layout_source="procedural"`, name-keyed identity |

Census, 18,176 `Texture` exports across DX / UED22 / Unreal Gold: 9,849 chains fit exactly one
layout; 8,327 (45.8 %) fit two or more and are resolved by the implied `Format = 0`; **0** fit none;
**0** go `ambiguous-layout`. A `Format` property is physically present on **11** exports. `bHasComp`
textures in retail Deus Ex content: 39 in `System`+`Textures`, 207 across the whole tree, all
`(Format ⇒ 0, CompFormat = 3)` — a P8 original with a DXT1 copy. That settles the externally
**[unver]** question of whether retail DX ships DXT1: it does, in `CompMips`. Unreal 226's `UnTex.h`
has no `bHasComp` at all **[src]**, which is why Unreal Gold's 10,742 exports had zero failures.
Twelve typed error cases, four about the ref and eight about the decode; `TextureError` is
deliberately truthy. Hostile input is capped in three layers (table counts bounded by file length,
32 mips / 65536 px / 256 MB per mip, plus a structural backstop on `resolve`). **[repo]**

### 2. The determinism contract, stated for the port

Everything below is integer arithmetic. There is no float, no RNG, no resample and no third-party
library in the path from package bytes to a classification shard key.

1. **P8 → RGB**: `out[i*3..] = palette[idx]`, alpha byte skipped; `mask[i] = idx != 0`.
2. **RGB565 → RGB888**: bit replication, `(v<<3)|(v>>2)` / `(v<<2)|(v>>4)` — explicitly **not**
   `round(v*255/31)`.
3. **BC interpolants**: integer `(2a+b)//3`, `(a+2b)//3`; BC1's three-colour mode (`c0 <= c1`) uses
   `(a+b)//2` with index 3 transparent black. BC2/BC3 have no punch-through mode. BC2 alpha = nibble
   × 17; BC3 alpha = sevenths if `a0 > a1`, else fifths plus hard 0/255 at indices 6/7.
4. **Block row writes are clipped to the mip's real `w`/`h`** — live at 8×2, 4×1 and 2×1 in every
   block chain reaching 1×1. `mask` is binary; graded BC2/BC3 alpha is thresholded at zero.
5. **Layout detection** is eight ordered, mutually exclusive rows (`utexture_decode.py:235-329`).
6. **Identity**: `sha256(u32le(width) ‖ u32le(height) ‖ rgb)`, mask not hashed, pinned by a
   hardcoded golden hex (`test_texture_enum.py:165`). Procedural identity is casefolded `Package.Name`.
7. **Colour derivation**: `step = max(1, w*h // 4096)`; for `i in range(0, w*h, step)` snap to the
   nearest of 12 fixed palette RGBs by **squared RGB distance**, strict `<` so the earlier entry
   wins a tie; rank by share; keep those `>= 0.12` up to 3, ordered by descending share then palette
   order; if nothing clears the floor keep the single most frequent.

Item 7 is the one the docs misdescribe. `old/pyproject.toml:13` says Pillow is "pinned to a floor
for the deterministic NEAREST-resample color derivation"; `architecture.md:729` says "quantize 64×64
NEAREST-resample histogram". Neither is what the code does, and no texture-catalog path calls any
resize — Pillow appears only as `Image.frombytes` + PNG write in `texture preview`. **[repo]**

This matters because a real Pillow-NEAREST port is *not* trivial. `resize(NEAREST)` goes through
`ImagingScaleAffine`, which computes the source index by **repeated addition**
(`xo = box_lo + scale*0.5; … xo += scale`), not the closed form. Over 400 random size pairs the
accumulated form matched Pillow 400/400 and the closed form 311/400, diverging on ~0.03 % of pixels
(smallest case 2→7). Every Rust crate checked uses the closed form and none claims Pillow
bit-exactness — `fast_image_resize` included, whose docs mention OpenCV and never Pillow. Pillow's
NEAREST also changed in 3.4.0 ("Respect pixel centers during transform") from `floor(dst*scale)` to
the half-pixel form. So the good news is that uedcli depends on none of it. **[src]**

### 3. Catalog and search: how an agent actually finds a texture

`texture search TERM…` scores each ref: 5 exact leaf `Name`, 4 exact stored tag, 3 ref substring,
2 tag substring, 1 description substring — and **returns `None` unless every term matches at some
tier** (`texture_catalog.py:221-252`). Filters: `--tag` (AND), `--color` (OR, closed 12-word
vocabulary), `--package`, `--group`, `--masked`, `--classified`/`--unclassified`.

Classification is **not** heuristic, name-based or learned. `tags` and `description` are whatever an
LLM or human hands to `classify set`; the tool stores them against the content identity and never
infers them. The one declared exception is colours. `old/dev/docs/direction/asset-catalog.md:30-33`
states the rule.

The honest answer to "how does an agent find a grimy metal wall texture": **it greps names.** No
`texture-catalog/` directory is committed anywhere in the repo, so on a clean clone every texture is
unclassified and the tag/description tiers contribute nothing. `texture search grimy metal wall`
matches nothing, because "grimy" appears in no ref. The project's own friction spike records this
verbatim (`old/dev/docs/spikes/levelbuild-friction/README.md:467-471`): *"Everything is
`unclassified`, so `texture search --tag` and description matching return nothing. Discovery is by
name grep, package, or colour only… the catalog's headline feature is inert until someone
classifies — and no agent had a reason to."* **[repo]**

Same spike, §5: `--color teal` and `--color cyan` both fail against the closed 12-word list, hit
while building a cyan neon level. Logged as `board/inbox/texture-search-color-accept-synonyms-or-nearest`.

**The inbox item about deriving colours.** `old/dev/docs/board/inbox/texture-search-derives-colours-for-the-whole/`
is **not present in this worktree** — it is untracked in the main checkout. Read read-only from
there, its content is: `_run_search` calls `_colors_for` for **every** candidate texture, but for
plain output (no `--json`, no `--color`) the derived colours are never read. Measured on the 4,393-texture
Deus Ex corpus: decode-all 38.5 s, derive-colours-all **80.4 s** — so a plain `texture search brick`
spends ~80 s on work it throws away, ~118 s total. Proposed fix: gate on `want_colors or args.json`,
mirroring `_run_list`'s existing `need_decode`. Note the title says "for the whole corpus", not "for
the whole texture".

Two adjacent cost facts: **`prewarm` cannot help** — `TextureResolver` caches per *invocation*
("Per-invocation caching only; no on-disk cache", `utexture.py:14`) and each CLI call is a fresh
process, so it warms a cache that dies with it and `--force` is never read
(`board/inbox/texture-prewarm-force-is-a-no-op-today`); every `texture search` re-decodes the corpus
from scratch. And **`_ref_facts` double-parses** — it calls both `resolver.dimensions(ref)` and
`resolver.resolve(ref)`, separate caches each running the full `decode_texture()`
(`board/inbox/texture-resolver-double-decode-and-cache-bypass`).

**Two colour-derivation defects, found here, not previously logged.**

1. **Column aliasing.** The stride walks a row-major flat index, so when `step` divides the width the
   sampler collapses onto a handful of columns — measured: 64² → all 64 columns; 256² → 16/256;
   512² → 8/512; 1024² → **4**/1024; 2048² → **2**/2048. Every row is sampled; 2-16 columns are. A
   texture with vertical banding (pipes, panelling, a doorframe) therefore takes its colours from
   whichever stripes those columns land on. A real 64×64 NEAREST resample would not do this, and the
   largest texture in the corpus is 2048², so the worst case is real content.
2. **Transparent texels count as `pink`.** `derive_colors` takes `res.rgb` and ignores `res.mask`;
   UE1 masking is the palette-index-0 convention and index 0 in DX cut-out textures is the magenta
   key, which snaps to `pink`. The friction spike noticed this from the other side and called it
   useful (`agent-reports.md:802-806`): *"Every cut-out texture in this level lists `pink`
   (`ClenChainlink_B`, `ladder_a`, `DangDoNoEnter_A`); none of the other 42 textures the level uses
   does. That is the `has_index0`/`masked_candidate` field the DiveBar note asked for."* So it is at
   once an accidental cut-out detector and a contaminated colour readout — which it should be is an
   owner call, not a bug report.

`texture_colors` is imported only by `cli/commands/texture.py`, and **no test file references
`derive_colors`, `nearest_color` or `texture_colors`.** The only coverage is incidental: three
`test_texture_cli.py` assertions that a fixture comes out `brown`/`grey`. **[repo]**

### 4. Alignment: the texture frame and the nine `POLY TEXALIGN` modes

The frame is per-polygon, stored in the brush's local space: `Origin` (a point), `TextureU`,
`TextureV` (covectors) and an integer `Pan`. The convention, pinned by
`test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`:

```
U = (Vertex − Origin) · TextureU + PanU          (V analogously)
```

so `Origin` is the world point mapping to `(PanU, PanV)` and the **texel scale lives in the
magnitude** of `TextureU` — a unit `TextureU` is 1 texel per world unit. There is no `UScale` field
on the poly. World mapping is `base_w = Location + L·(Origin − PrePivot)`,
`axes_w = (L⁻¹)ᵀ·axes` with `L = PostScale·R·MainScale`; `_write_world_frame` inverts that exactly
(`L⁻¹` for the point, `Lᵀ` for the covectors), which is what makes a shared world frame work across
differently-placed, rotated, scaled and mirrored brushes. **[repo]**

**[src] corroboration and two extensions.** `FBspSurf` stores `pBase`, `vNormal`, `vTextureU`,
`vTextureV` as *indices* into `UModel::Points`/`Vectors`, plus `SWORD PanU, PanV`. The D3D7 driver
computes `u = MapCoords.XAxis | (P − MapCoords.Origin)` then `(u − Pan.X) * UScale` with
`Pan = FVector(−PanU, −PanV, 0)` and `UScale = 1/(USize · UTexture::Scale)` — the repo's formula
exactly, with two things it does not model. First, **`Pan` is 16-bit signed in the engine**, while
`parse_pan` (`cli/parsers/_arguments.py:154`) accepts any Python `int` with no range check and
`_write_world_frame` writes `int(round(pan))`; `brush poly pan --to 100000,0` would reach T3D and
wrap at ±32768. Second, **`UTexture::Scale` divides the UV** and uedcli never reads it (grep: no
`"Scale"` lookup in `utexture.py`/`texframe.py`/`polyalign.py`) — whether any Deus Ex texture has
`Scale != 1` is **[unver]**, since the property is omitted at its class default of 1.0. Also
**[src]**: `FPoly::Transform` carries `TextureU`/`TextureV`/`Base` through a brush transform, so UE1
texture lock is structural, with no toggle — uedcli's inverse-transform write is the same idea from
the other direction.

#### `TexAlign` modes × uedcli support

Editor rows measured live in UED22 2.2 2026-07-26; `N` = unit surface normal, `d = N·P`,
`proj(A) = A − N(N·A)` (not renormalised).

| Editor mode | What it writes | Guard | uedcli | Confidence |
|---|---|---|---|---|
| `DEFAULT` (0) | regenerate U/V from the polygon's own winding via `FPoly::Finalize`; unit axes; `Pan = 0` | none | — | **[repo]** live + **[src]** |
| `FLOOR` (1) | `Origin = (0,0,d/N.Z)`, `U = ±proj(X̂)`, `V = ±proj(Ŷ)`, `Pan = 0` | `\|N.Z\| > 0.05` | **`align floor`**, exact | **[repo]** live + **[src]**; sign see below |
| `WALLDIR` (2) | `U = normalize(N.Y,−N.X,0)`, `V = normalize(U×N)`, negate **both** if `V.Z > 0`; `Origin` untouched; `Pan = 0` | `\|N.Z\| < 0.95` | **`align wall`**, exact except anchored on the face centroid | **[repo]** live + **[src]** verbatim |
| `WALLPAN` (3) | `Origin += V·(−Origin.Z/V.Z)`; U/V/`Pan` untouched | `\|N.Z\| < 0.95` and `\|V.Z\| > 0.05` | **`align wall-pan`**, exact | **[repo]** live + **[src]** |
| `ONETILE` (4) | **nothing** — switch entry lands on the shared epilogue, no case body | — | no analogue (`align one-tile` is uedcli's own) | **[repo]** live + disasm + **[src]** (no case) |
| `WALLCOLUMN` (5) | **nothing** — same address as `default:` | — | none | **[repo]** live + disasm + **[src]** (no case) |
| `WALLX` (6) | `Origin = (d/N.X,0,0)`, `U = ±proj(Ŷ)`, `V = ±proj(Ẑ)`, `Pan = 0` | `\|N.X\| > 0.05` | **none** (code path survives unreachable — see below) | **[repo]** live; **not in stock UE1** |
| `WALLY` (7) | `Origin = (0,d/N.Y,0)`, `U = ±proj(X̂)`, `V = ±proj(Ẑ)`, `Pan = 0` | `\|N.Y\| > 0.05` | **none** | **[repo]** live; **not in stock UE1** |
| `CLAMP` (8) | `DEFAULT` plus `PanV = VSize − 1`, `PanU = 0` | none | **none** | **[repo]** live (3 textures, decisive on a 256×64) |
| `TEXELS=<n>` | parsed, passed, **never read** | — | n/a | **[repo]** disasm (no `[ebp+0x10]` read in any encoding) + **[src]** |
| — | — | — | **`align run`** — connected-run walk, any number of brushes, cylinder wrap, `--turn`, `--fit-perimeter` | uedcli's own, no editor analogue |
| — | — | — | **`align one-tile`** — fit one tile per face, projection table Gram-Schmidt-orthogonalised | uedcli's own |

Two things the repo's `texalign.md` does not say, both from the external source read:

1. **Stock UE1 `ETexAlign` has six values** — `Default, Floor, WallDir, WallPan, OneTile,
   WallColumn` — identical in Unreal 226, Deus Ex 1112f and UT 432/436, and the UnrealEd 2.0 menu
   has no Wall Column item. `WALLX`/`WALLY`/`CLAMP` are therefore **UED22/227-era extensions**, not
   original UE1 behaviour. (OldUnreal 469 extends the enum differently again: `OneTileU=5,
   OneTileV=6, WallColumn=7, WallX=8, WallY=9, Walls=10, Auto=11, Clamp=12` — so even the numbering
   diverges from UED22's.) The repo's doc already carries the right scoping warning ("a statement
   about the committed `uned/UED22` substrate") but only for `ONETILE`/`WALLCOLUMN`. **[src]**
2. **The `FLOOR`/`WALLX`/`WALLY` sign.** The repo's table writes `TextureU = −proj(X̂)` etc.; the UE1
   source for `TEXALIGN_Floor` reads as `U = X̂ − N(X̂·N)` with no negation. Both cannot be right for
   the same build. The repo's version is live-measured against UED22 and is reproduced exactly by
   `test_texalign_model_reproduces_every_measured_editor_frame`, so it is right *for UED22*; whether
   stock UE1 differs, or the source reading dropped a negation, is unresolved. Worth one hour.

#### The WALLDIR rework and the 45° bug

`board/done/align-wall-skews-texture-on-45deg-diagonal-faces` was filed p1: a 45°-yawed vertical face
got `|TextureU| != |TextureV|` under `align wall`. **Resolved as not-a-bug.** `align wall` was
faithfully reproducing `WALLX`/`WALLY`, whose projection family stretches a tilted face by
`1/|proj|` by construction — a 45° wall gets `|proj| = 0.7071`, a 1.41× stretch. The repro's actual
want was a different editor mode.

`board/done/align-wall-walldir-style-axes-split-off-a-wall` then redefined `align wall` onto
`WALLDIR` (unit axes from the face's own horizontal run and downward slope — never stretches) and
split out `align wall-pan` for cross-face vertical phase sync. Along the way it needed two new
pieces, because `WALLDIR` — unlike the projection family — is **not** invariant under `n → −n`:
`query.csg_sign` (exact-case `CsgOper` sign, refuses Intersect/Deintersect) and
`polyalign._oriented_world_normal` (reflection-correct: local Newell mapped through `(L⁻¹)ᵀ`, since
plain Newell on world verts flips sign under a mirrored brush). Spec took 4 revisions / 3 review
rounds. Pinned by `test_wall_matches_walldir_yawed_face` (the doc's own measured example
`N=(0.6,0.8,0) → U=(−0.8,0.6,0), V=(0,0,−1)`) and `test_wall_no_longer_stretches_on_a_diagonal_face`.

**Residue:** `_projected_align` is now only ever called with `"floor"` (`polyalign.py:817`), so
`_projection_axis`'s X-vs-Y argmax branch and `_projection_guard_message`'s "horizontal" wording are
unreachable. `_AXIS_UV` is still live — `one-tile` uses it with a per-face argmax. Exposing
`align wall-x`/`wall-y` would be nearly free, if wanted.

#### Measurement method and confidence

The spike (`old/dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/`) drove the real editor in
the committed UED22 substrate: **44 faces × 9 modes, twice** (once from zero pan, once from an
authored `Pan U=7 V=13`), plus **eight one-wedge levels** bracketing the guard thresholds at ±0.001,
plus static disassembly of `UEditorEngine::polyTexAlign` at `Editor.dll` RVA `0x4c6c0`. Results read
back through `MAP EXPORT`.

Pinned by six `test_engine_facts.py` regressions, two unusually strong:
`test_texalign_model_reproduces_every_measured_editor_frame` runs the documented rules against
`measured.json` for **396 (mode, face) pairs** — the whole 44×9 grid — asserting `Origin` to 0.2 uu
and the axes to 2e-3; and `test_texalign_guard_thresholds_are_005_and_095_and_texels_is_ignored`
reads the two `.rdata` doubles at RVAs `0x0DE950`/`0x0E0578`, checks their reference counts inside
the function body (4 and 2), and asserts that no encoding of a read from `[ebp+0x10]` appears.

So: guard **directions** are live-measured, the constants are binary-read and bracketed live to a
0.002-wide window, and the per-mode formulas now have independent source-level corroboration they
did not have before this sweep. The spike's own caveat stands — both sides of the model test are
committed data, so it cannot see a substrate swap; the byte-pattern tests are what watch
`Editor.dll`.

### 5. The open "texture alignment solver" item

`board/to-spec/texture-alignment-solver-poly-align-planar-wall/` is the oldest live alignment item,
and **most of what it asks for has shipped**. Its own spec says so: planar wall/floor, cylinder
`--ring`, `texture rotate`/`scale`, and the `brush poly find` producer are all marked **DONE**. What
remains:

- **Sphere/dome alignment (`--sphere`).** Two forks are open in `questions/`: equirectangular
  per-face frame (`r̂` from centroid − centre, east `ê = axis × r̂`, north `n̂ = r̂ × ê`, U along `ê`
  scaled to arc-length-per-texel, V along `−n̂`) vs stacked rings per latitude band. The spec
  recommends equirectangular because it handles a geodesic and a revolve dome uniformly; the stated
  cost is that continuity is exact only where facets share a tessellation, and poles degenerate.
  Also open: require explicit `--center`/`--axis`, or derive the centre from the face set.
- **Fitting an open run.** `--fit-perimeter` is closed-run-only by ruling; "snap the density so a
  whole number of texels spans this wall run" has no verb
  (`board/inbox/fitting-a-texture-to-an-open-run`).

What makes it hard, from the shipped `run` code: continuity across faces is only achievable where
the faces share edges, and the frame must be **orthogonal** to stay usable. A run whose seams lie in
the turn plane (a flat bend) shears one axis by `2·sin(Δθ/2)·half_width`, exact only at quarter
turns; the rejected non-orthogonal alternative is continuous on both axes but stretches 86 % at the
end of a 90° bend, and that degradation does not reduce with more segments where the orthogonal
frame's shear halves each time. `run` therefore reports the worst internal seam shear to stderr and
tells the author to mitre or accept it. A sphere has the same problem in both directions at once.
Three further deliberate limits: non-quad faces are refused (a terminal face's free edge is
`(exit + 2) % 4`), the run cannot fork (degree ≥ 3), and it must be one connected component.

**The spec itself is stale** — it cites `_coplanar_align`, `_ring_align`, `_check_orientation`,
`--wall`/`--floor`/`--ring`/`--fresh-frame`, none of which exist (grep: 0 hits in `polyalign.py`).
`board/inbox/align-flag-rename-left-dev-docs-refs-stale` tracks the doc half and is partly resolved:
`texalign.md`'s "How uedcli differs" **has** been rewritten for the WALLDIR rework, but
`architecture.md` ~L1817/~L1861 and `unrealed/t3d.md` ~L485 still name deleted flags, and
`unrealed/leveldesign/kb/textures.md:66-70` still says `align floor|wall` reproduce
`FLOOR`/`WALLX`/`WALLY`. The *user*-facing `docs/leveldesign/general/textures-and-surfaces.md` was
fixed in `a8425be4`. All need the owner's yes.

Two inbox items in this family appear **already fixed** and could be closed:
`relation-py-plane-relationship-broken-polyalign` (the constants now live in `relation.py:17-18`) and
`brush-poly-align-still-prints-touched-brush` (`cli/commands/brush/poly.py:283` prints `BRUSH:idx`
per face). Two are open and unconfirmed: `generator-texture-basis-mirrors-lettered` (p2 —
`builders._tex_basis` uses `v = cross(normal, u)`; if that handedness disagrees with UnrealEd's
BrushBuilder every generated face is mirrored, and lettered textures were reported backwards) and
`brush-build-sheet-texture-origin-should-default` (p3 — sheet `Origin` at the centre, so a texture
lands half-shifted).

### 6. Prior art: paraxial vs parallel, and where WALLDIR sits

The classic Quake/Radiant texdef picks a **dominant axis** from an 18-vector `baseaxis` table (6
cases × snapped normal + U + V) by `dot > best`, first-wins in table order
floor/ceiling/west/east/south/north. The table is byte-identical across id's QBSP, `qbsp3`,
Half-Life `qcsg`, `q3map2` and ericw-tools; the tie-break is **not** (`q3map2` adds a `+0.0001f`
hysteresis for bug 637; ericw-tools exposes `-oldaxis`/`-nooldaxis`). **[src]**

That is **paraxial** projection, and TrenchBroom's manual names the artefact precisely: projecting
along a world axis rather than the face normal "leads to some distortion (shearing) that is
particularly apparent for slanted brush faces where the face's normal is linearly dependent on all
three coordinate system axes" — while noting the compensating virtue, that when the normal depends
on two or fewer axes the texture still *fits* without rescaling. Valve 220 exists to fix it by
storing explicit U and V axis vectors per face, which TrenchBroom calls **parallel** projection.
GtkRadiant's source comments on the 45° degeneracy by name ("for the plane `X == Y` the projection
axis could be either X or Y"). One nuance: on a 45° face whose normal lies *in* a coordinate plane —
`(0.707, 0.707, 0)`, exactly the uedcli repro — axial projection gives pure **foreshortening**
(≈1.414×), not shear; genuine shear needs all three components nonzero. **[comm/src]**

**UE1 is structurally in the parallel family.** It always stores `vTextureU`/`vTextureV` per surface,
with no paraxial mode and no texture-lock toggle. `TEXALIGN_WallDir` — `U = normalize(N × Ẑ)`,
`V = normalize(U × N)` — is the same construction as Q3's `ComputeAxisBase` and near-identical to
TrenchBroom's parallel `computeInitialAxes`. Three differences: UE1 refuses `|N.Z| ≥ 0.95` faces
where TrenchBroom falls back to `cross(+Ŷ, normal)`; UE1 flips both signs to force V downhill;
UE1's is a one-shot operation that resets pan and scale, not a persistent mode. `TEXALIGN_Floor`/
`WALLX`/`WALLY` are the paraxial-flavoured outliers inside that parallel engine — world axes
projected into the face, which is what buys a whole floor one world-anchored grid at the cost of the
`1/cos` stretch. **[src]**

**So the 45° bug reads, in prior-art terms, as uedcli having opted into the paraxial artefact via
`WALLX`/`WALLY` for a verb named `wall`.** Moving `wall` to `WALLDIR` moved it to parallel
projection — the same move Valve made in 1998 and TrenchBroom offers as a mode.

### 7. Perceptual colour, and whether distance is the right framing

- Averaging in **sRGB** averages a gamma-encoded quantity, so it is wrong; the mean belongs in
  **linear RGB**, converted afterwards for naming. CIELAB is for distance and naming, not averaging,
  and is itself non-uniform in blues — CIEDE2000's `R_T` hue-rotation term exists to patch that. Its
  advantage narrows in uedcli's regime, though: snapping to a **coarse** vocabulary means large
  distances, exactly where Euclidean measures are known to work poorly *and* where CIEDE2000's edge
  shrinks. It also has a documented discontinuity and needs the Sharma/Wu/Dalal (2005) vectors to
  validate an implementation. **[comm]**
- **Oklab** beats CIELAB on both published uniformity metrics (hue RMS 0.49 vs 0.69, lightness 0.20
  vs 1.70) and is far simpler — plain Euclidean distance, no hue-rotation term, no discontinuity. No
  published colour-*naming* benchmark compares the two, so "good enough for bucketing" is an
  inference. **[comm / unver]**
- **The palette makes this exact and cheap.** A P8 texture already *is* ≤256 colours plus an index
  histogram, so one O(pixels) pass gives an exact weighted colour histogram — no sampling, no
  stride, no RNG — and any quantizer then runs on ≤256 weighted points. That removes the only reason
  the current stride exists.
- Prior art for asset libraries is **tags, not colour distance**: ambientCG's API v2 has no colour
  parameter and no colour metadata at all; MatSynth's 4,069 materials carry descriptive tags,
  category and text descriptions; Unreal's own asset metadata is key-value tags filtered as
  `tagname=value`. For the non-colour half of a vocabulary the **Describable Textures Dataset**
  (Cimpoi et al., CVPR 2014) is an off-the-shelf 47-attribute human-centric adjective set — dotted,
  striated, cracked, veined. **[comm]** No prior art found on tagging texture libraries for AI
  agents specifically. **[unver]**

#### Crates and licences

| Crate | Ver | Role | Decode? | Licence | Status |
|---|---|---|---|---|---|
| `texpresso` | 2.0.2 | BC1-BC5 decompress + compress; pure Rust, `no_std`-capable | yes | MIT (Cargo metadata; **no `LICENSE` file in repo**) | active 2025-10; successor to `squish-rs` |
| `squish` | 2.0.0-beta1 | libsquish port | yes | MIT | **archived 2022 — do not use** |
| `image_dds` | 0.7.2 | safe Rust `bcdec` port, BCn only | yes | MIT | active 2025-09; heavier deps |
| `intel_tex_2` | 0.5.0 | ISPC BCn/ETC/ASTC | **encoder only** | MIT OR Apache-2.0 | active; wrong tool for reading `.utx` |
| `ddsfile` | 0.6.0 | DDS container envelope | **no codec** | MIT | container only |
| `image` | 0.25.9 | general image IO + `imageops::resize` | n/a | MIT OR Apache-2.0 | `Nearest` runs the full two-pass f32 convolution; **not** Pillow-exact |
| `fast_image_resize` | 6.1.0 | SIMD resize | n/a | MIT OR Apache-2.0 | structurally a Pillow port but uses the closed form; **no Pillow claim** |
| `resize` | 0.8.9 | resize | n/a | MIT | f32 coefficients; not Pillow-exact |
| `palette` | 0.7.7 | colour spaces + `Ciede2000`/`ImprovedCiede2000`/`HyAb`/`EuclideanDistance` | n/a | MIT OR Apache-2.0 | active; **CIEDE2000 on `Lab`/`Lch` only, not Oklab** |
| `oklab` | 1.1.2 | sRGB ↔ Oklab conversions only | n/a | **CC-PDDC** (public domain) | no distance function |
| `deltae` | 0.3.2 | DE1976/1994/2000/CMC over `LabValue` | n/a | MIT | no sRGB conversion; you supply Lab |
| `kmeans_colors` | 0.7.1 | k-means palettes, Lab or RGB | n/a | MIT OR Apache-2.0 | reproducible **only** with an explicit seed |
| `color_quant` | 2.0.0 | NeuQuant → ≤256 palette | n/a | MIT | no RNG (fixed prime strides) ⇒ deterministic |
| `dominant_color` | 0.4.0 | 8 fixed buckets, averaged in sRGB | n/a | MIT | stale 2023; wrong colour space — **not suitable** |
| UEViewer / umodel | — | reference UE1-UE4 decoder | yes | MIT (Nosov) | vendors `detex`/`nvtt`/`oodle` in `libs/` with **no per-library LICENSE files**; `oodle` is proprietary — do not lift code |
| UELib / `Eliot.UELib` | — | package/UnrealScript deserialiser | **no pixel decoder** | MIT | active; and it reads `CompMips` before `Mips`, which contradicts both Epic trees |

For a Rust `.utx` reader the minimal set is: own P8 path (trivial — 256 RGBA + index bytes),
`texpresso` for BC1-BC3, and a PNG encoder. Nothing in the colour or resize columns is needed to
reproduce today's behaviour.

## Options

Framing options for the colour pre-fill, since that is where the decode and discovery legs meet.
All three preserve the "tool stores, never infers" rule for tags and descriptions.

| Option | Pros | Cons |
|---|---|---|
| **A. Leave as-is; fix only the wasted work** (gate `_colors_for` on `want_colors or --json`) | Smallest change; the inbox item's own proposal; ~80 s → 0 on plain search; no identity or shard re-key | Column aliasing and the `pink` contamination stay; the docs stay wrong |
| **B. Exact palette histogram, same 12 names** (one O(pixels) index pass → weighted histogram over ≤256 palette entries → same snap/threshold/cap rules) | Removes the sampler entirely — exact, no aliasing, deterministic, *faster* than today; trivially portable to Rust; same output vocabulary | Changes derived colours for some textures, so already-stored `colors` pre-fills drift (stored LLM overrides are unaffected); needs the tests that do not exist yet |
| **C. B, plus exclude masked texels and snap in Oklab** | Removes the `pink` contamination; better bucket boundaries on blues; multi-label within a ΔE threshold would fix teal/cyan | Loses the accidental cut-out detector unless it is re-exposed deliberately (e.g. a `--cutout` filter on the real `mask`); introduces a colour-space dependency; new craft-visible behaviour, so owner approval |
| **D. Implement the documented 64×64 NEAREST resample** | Makes code and docs agree as written | Highest cost and lowest value: the accumulated-vs-closed-form trap, a Pillow version dependency the port would have to reproduce by hand, and it is strictly worse than B for a palettized source |

## Proposal (owner's call — not decided)

Proposed, in this order: take **option A** on its own merits (a pure win, already specced); then
consider **option B** as the shape for the Rust port, since the port must reimplement
`derive_colors` anyway and the palette histogram is both exact and cheaper than the stride — pinned
by the tests `texture_colors` currently lacks, written *before* anything changes so the drift is
visible. Separately, correct the two stale determinism claims (`pyproject.toml:13`,
`architecture.md:729-730`) so they stop describing a Pillow resample that is not there. Treat the
`FLOOR` sign discrepancy and the `Pan` 16-bit range as two short verification tasks, not design
work. And leave the alignment-solver item parked on sphere/dome — the only genuinely unbuilt piece —
recording in it that `WALLX`/`WALLY`/`CLAMP` are UED22-era extensions rather than UE1 behaviour,
which reframes "should uedcli have a `wall-x`?" as a substrate question, not a parity question.

No craft guidance is asserted here. Anything that changes what a level designer sees — whether
`align wall` should mirror, whether a `--cutout` filter should exist, whether colour buckets should
be multi-label — is the owner's to rule on, and new claims in `old/docs/` need explicit approval.

## Open questions / what to verify next

- Does stock UE1's `TEXALIGN_Floor` negate the projected axes, or does UED22 differ? One re-read of
  the spike's disassembly against the source settles it.
- Does any Deus Ex texture carry `UTexture::Scale != 1`? If none do, ignoring it costs nothing; if
  some do, every density claim on those faces is off by that factor.
- Is `Pan` ever written outside ±32767 today, by `align` (which zeroes it) or `pan --to` (which does
  not clamp)? Cheap to check over the committed trunks.
- Should the accidental `pink`-means-cut-out signal become a real field read off `mask`, or be
  allowed to vanish when the colour derivation is fixed?
- `board/inbox/generator-texture-basis-mirrors-lettered` is unconfirmed and would mirror every
  generated face — it needs one GUI-built brush exported from UnrealEd as an oracle.
- Board hygiene, owner's call: two inbox items look already-fixed, one spec is stale, and the
  untracked `board/inbox/texture-search-derives-colours-for-the-whole/` is in no worktree's index.

## Sources

**In-repo (all [repo]):** `old/uedcli/utexture.py`, `utexture_decode.py`, `texture_colors.py`,
`texture_catalog.py`, `polyalign.py`, `surface.py`, `cli/commands/texture.py`,
`cli/commands/brush/poly.py`, `cli/parsers/texture.py`, `cli/parsers/_arguments.py` ·
`old/dev/docs/unrealed/texalign.md`, `unrealed/t3d.md` §"The UV convention",
`unrealed/package-format.md` §"UTexture body", `unrealed/leveldesign/kb/textures.md` ·
`old/dev/docs/rationale/texture-decode.md`, `rationale/polyalign.md`, `rationale/surface.md` ·
`old/dev/docs/direction/asset-catalog.md` ·
`old/dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/` (README, `measured.json`,
`guards.json`, `texalign_model.py`) ·
`old/dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md` ·
`old/dev/docs/spikes/2026-07-26-ucc-texture-fixture/findings.md` ·
`old/dev/docs/spikes/levelbuild-friction/` (README §5, §11; `agent-reports.md`) ·
`old/uedcli/tests/test_engine_facts.py:593-780`, `test_polyalign.py`, `test_texture_enum.py:165` ·
board items under `old/dev/docs/board/{inbox,to-spec,done}/`.

**UE1 source — community mirrors, [src]:** https://github.com/maximqaxd/ut99dc
(`Editor/Inc/Editor.h` → `ETexAlign`; `Editor/Src/UnEdCsg.cpp` → `polyTexAlign`, `polyTexScale`;
`Editor/Src/UnEdSrv.cpp` → `POLY TEXALIGN` parse; `Render/Src/UnRender.cpp` → `MapCoords`/`Pan`;
`Engine/Src/UnTex.cpp` → `UTexture::Serialize`, `CreateMips`; `Engine/Classes/Texture.uc`;
`UnrealEd/Src/Res/UnrealEd.rc` → menu labels) ·
https://github.com/wrstone/ut432pubsrc (`Engine/Inc/UnObj.h` → `FBspSurf`, `EPolyFlags`;
`Engine/Inc/UnTex.h` → `UBitmap`/`UTexture`/`UPalette`, `ETextureFormat`; `Core/Inc/UnTemplate.h` →
`TLazyArray`; `D3DDrv/Src/Direct3D7.cpp`; `OpenGLDrv/Src/OpenGL.cpp`) ·
https://github.com/mmdanggg2/UE1-sdks (`sdk_dx1112f/`, `sdk_unreal226/` with no `bHasComp`,
`sdk_ut469e/Engine/Inc/UnTexFmt.h`) ·
https://github.com/cefege/harry-potter-2-chamber-of-secrets-pc (second tree, same mip order).

**Prior art / tooling:** https://trenchbroom.github.io/manual/latest/#material_projection_modes
(paraxial vs parallel) · https://github.com/id-Software/Quake-Tools/blob/master/qutils/QBSP/MAP.C
(`baseaxis`) · https://github.com/id-Software/GtkRadiant/blob/master/radiant/brush_primit.cpp
(`ComputeAxisBase`, `Texdef_transformLocked`) ·
https://developer.valvesoftware.com/wiki/MAP_(file_format) (valve220) ·
https://github.com/python-pillow/Pillow/blob/main/src/libImaging/Geometry.c (`ImagingScaleAffine`)
and `Resample.c` (filtered path) · https://github.com/gildor2/UEViewer ·
https://github.com/EliotVU/Unreal-Library · https://bottosson.github.io/posts/oklab/ ·
https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/ ·
https://docs.ambientcg.com/api/v2/full_json/ · https://huggingface.co/datasets/gvecchio/MatSynth ·
https://www.robots.ox.ac.uk/~vgg/data/dtd/ · crates.io / docs.rs for every crate above.

**Gaps:** retail Deus Ex DXT1 usage is settled in-repo (207 `CompMips` arrays) but was not
externally confirmable; no colour-naming benchmark compares Oklab against CIEDE2000; no prior art
found on texture-library tagging for AI agents; the UnrealEd Flags-tab source is in no public tree,
so the surface-settable `PF_*` checkbox list is **[comm]** only.
