# UnrealEd 2.2 — `POLY TEXALIGN`, the surface-alignment modes

What each `POLY TEXALIGN` mode does to a BSP surface's texture frame, in the committed UED22
substrate. Command syntax is in [`commands.md`](commands.md); the texture-frame convention
(`U = (Vertex − Origin)·TextureU + PanU`, texel scale in the magnitude of `TextureU`) is in
[`t3d.md`](t3d.md) — read that first; everything below uses its terms.

Evidence: [`../spikes/2026-07-26-unrealed-texalign-semantics/`](../spikes/2026-07-26-unrealed-texalign-semantics/README.md)
(live 2026-07-26: 44 faces × 9 modes twice — once from a zero pan and once from an authored
`Pan U=7 V=13` — plus eight one-wedge levels bracketing the guard thresholds, plus disassembly of
`UEditorEngine::polyTexAlign`, `Editor.dll` RVA `0x4c6c0`). Pinned by
`test_engine_facts.py::test_texalign_*` (six regressions).

> **Confidence:** ✅ = live-verified · 🔬 = read out of the shipped binary and consistent with every
> live measurement · 📖 = binary only, unconfirmed live.

---

## Vocabulary ✅

```
POLY TEXALIGN DEFAULT|FLOOR|WALLDIR|WALLPAN|WALLCOLUMN|ONETILE|WALLX|WALLY|CLAMP [TEXELS=<n>]
```

Nine tokens, not the six `commands.md` used to list (`DEFAULT`, `WALLPAN`, `WALLCOLUMN` were
missing). All nine parse, none errors. An absent or unknown token is silently ignored: `POLY
TEXALIGN` and `POLY TEXALIGN BOGUS` each changed nothing on any face.

- `TEXELS=<n>` is parsed then ignored ✅ 🔬 — `polyTexAlign`'s third parameter is never read.
  Live: `FLOOR`/`ONETILE`/`WALLDIR` with `TEXELS=64` gave output identical to the same command
  without it, on all 11 faces of the probe level.
- The verb is selection-scoped ✅: it walks `Model->Surfs` and acts only on surfaces carrying
  `PF_Selected (0x02000000)`. Live: `POLY SELECT NONE` then `TEXALIGN WALLDIR` changed 0 of 11
  faces where `POLY SELECT ALL` then the same changed 6.
- It also needs a built BSP ✅ — `Model->Surfs` is what CSG produces, so without a `MAP REBUILD`
  there is nothing to walk and nothing changes (measured: 0 of 11 faces). Driving this verb costs a
  paste + rebuild per alignment, one reason uedcli aligns model-side.
- Each touched surface gets `iLightMap = −1` (lightmap invalidated) then
  `polyUpdateMaster(Model, iSurf, 1, 1)` 🔬, which writes the new frame back into the originating
  brush polygon — which is why the change survives into `MAP EXPORT` and a saved `.dx` (that
  survival is itself ✅: the whole spike reads its results back through `MAP EXPORT`).

## It uses the surface normal ✅

CSG reverses a subtractive brush's polygons, so a room's inward-facing surfaces have the opposite
normal to the brush polygons `MAP EXPORT` prints. Every formula below takes that surface normal `N`.
(The exception is `DEFAULT`/`CLAMP`, which regenerate from the master polygon's own winding and so
use the brush polygon's outward normal.) Getting this backwards flips `WALLDIR`'s U direction.

## No mode changes texel density to fit a face ✅

Every mode writes a frame at 1 texel per world unit along the projection it uses; none reads a
texture's `USize`/`VSize` except `CLAMP`, which reads `VSize` for one pan value. There is no
fit-a-tile-to-a-face operation in UnrealEd 2.2 — see `ONETILE` below.

---

## The modes

`N` = unit surface normal · `d = N·P` for any point `P` of the plane · `proj(A) = A − N (N·A)`
(not renormalized, so `|proj(A)| = sqrt(1 − (N·A)²) ≤ 1`).

### `FLOOR` / `WALLX` / `WALLY` — orthographic projection down a world axis ✅

One family. Each drops one world axis, re-anchors the texture where the surface plane crosses that
axis, and builds the frame by projecting the other two world axes onto the face and negating them:

| mode    | axis | guard            | new `Origin`    | `TextureU` | `TextureV`
|---------|------|------------------|-----------------|------------|---
| `FLOOR` | Z    | `\|N.Z\| > 0.05` | `(0, 0, d/N.Z)` | `−proj(X̂)` | `−proj(Ŷ)`
| `WALLX` | X    | `\|N.X\| > 0.05` | `(d/N.X, 0, 0)` | `−proj(Ŷ)` | `−proj(Ẑ)`
| `WALLY` | Y    | `\|N.Y\| > 0.05` | `(0, d/N.Y, 0)` | `−proj(X̂)` | `−proj(Ẑ)`

`Pan` is zeroed (measured against an authored non-zero pan, not merely observed to stay zero). A
face failing the guard is left untouched, pan included. The guard threshold `0.05` is 🔬 (an
`.rdata` double the case bodies `comisd` against); the comparison direction is ✅.

Two consequences:

- A tilted face is stretched by `1/|proj|` — a planar projection, as if the texture were painted on
  a plane perpendicular to the dropped axis and shone onto the face. Measured: a 45° ramp
  (`N = (0.7071, 0, 0.7071)`) under `FLOOR` gets `|TextureU| = 0.70711`; a face with
  `N = (0.211, 0.281, −0.936)` under `WALLX` gets `|TextureV| = 0.35112` (≈2.8× stretch).
- The anchor is a world axis, not the face. Two faces on the same plane, or on different planes at
  the same height, therefore share one continuous texture grid keyed to the world origin. Measured:
  a 128³ cube centred at `(512, 96, 48)` has its top face's `Origin` moved from `(512, 96, 112)` to
  `(0, 0, 112)`, after which it spans `U ∈ [−576, −448]`.

### `WALLDIR` — a unit frame along the wall's own direction ✅

Guard: `|N.Z| < 0.95` 🔬 (anything but a near-horizontal face).

```
TextureU = normalize( (N.Y, −N.X, 0) )        # horizontal, along the wall
TextureV = normalize( TextureU × N )          # in-plane, down the face
if TextureV.Z > 0:  negate BOTH
Origin  unchanged;  Pan = (0, 0)               # actively zeroed
```

Both axes are unit on every face it accepts, slanted ones included — `WALLDIR` never stretches. The
final flip guarantees `TextureV.Z ≤ 0` (V points downwards), the correct orientation for a UE1
texture (whose `V = 0` row is its top). Measured on `N = (0.6, 0.8, 0)`:
`TextureU = (−0.8, 0.6, 0)`, `TextureV = (0, 0, −1)`.

The flip is coded as a conditional but is unconditional in practice: `(TextureU × N).Z` works out to
`(N.x² + N.y²)/|(N.y, −N.x, 0)|`, positive on every face the `|N.Z| < 0.95` guard admits. If you
reimplement this, the mode is just `TextureU = normalize(−N.Y, N.X, 0)`,
`TextureV = −normalize(TextureU × N)` — a reader who assumes the branch sometimes does not fire gets
both signs wrong.

### `WALLPAN` — slide the anchor to world Z = 0 ✅

Guards: `|N.Z| < 0.95` 🔬 and `|TextureV.Z| > 0.05` 🔬 (the current V must have a vertical
component). Both thresholds are 🔬 only — read from `.rdata` and pinned by reference count, but not
bracketed live the way `FLOOR`/`WALLX`/`WALLY`/`WALLDIR`'s are (§5.1 of the spike): the one live
datum is a face whose `TextureV.Z` was exactly 0, which shows a guard near zero exists but not where
it sits.

```
Origin ← Origin + TextureV · ( −Origin.Z / TextureV.Z )
TextureU, TextureV, Pan  ALL unchanged
```

Keep the frame (`TextureU`, `TextureV`, `Pan` all left as they were, verified against an authored
non-zero pan) and walk the anchor along V until its Z reaches zero, so every wall's vertical texture
phase agrees. Measured: a +X face of a cube centred at `z = 48` moved its `Origin` from
`(576, 96, 48)` to `(576, 96, 0)` with axes and pan byte-identical; across a 44-face fixture
`WALLPAN` altered `Origin` lines and nothing else. The second guard is real and was exercised: a
vertical face whose `TextureV` was horizontal (`(0.8, −0.6, 0)`, `TextureV.Z = 0`) was left alone
even though its anchor sat at `z = 30` — without a vertical component in V there is no direction to
slide along.

### `DEFAULT` — regenerate the frame from the polygon's own winding ✅

The editor pulls the master brush polygon, blanks its texture vectors, and lets `FPoly::Finalize`
regenerate them:

```
TextureU = normalize( (Vertex[0] − Vertex[i]) × N_poly )   # first i ≥ 1 that is non-degenerate
TextureV = normalize( N_poly × TextureU )
Origin  unchanged;  Pan = (0, 0)               # actively zeroed, on every face — no guard
```

Unit axes. Because the result depends on which corner the polygon's vertex list starts at, this is a
"reset this face to a valid frame" operation, not a design tool — two coplanar faces wound from
different corners come out 90° apart.

### `CLAMP` — `DEFAULT`, plus `PanV = VSize − 1` ✅

Identical to `DEFAULT` except `PanV`, set to the bound texture's height in texels minus one.
Measured across three textures: `256×256 → PanV 255`, `256×64 → 63`, `128×256 → 255` — the 256-wide,
64-tall one is decisive, so the field is `VSize`, not `USize`. `PanU` is zeroed. What it is for was
not determined — only what it writes was measured. No render was made and no interaction with
texture addressing or `PolyFlags` was probed, so do not infer a rendering behaviour from this entry.

### `ONETILE` and `WALLCOLUMN` — not implemented in UED22 ✅ 🔬

- `WALLCOLUMN` does nothing. Its `switch` entry is the same address as the `default:` branch, which
  only advances the surface loop. Live: after `POLY TEXALIGN WALLCOLUMN` not one
  `Origin`/`TextureU`/`TextureV`/`Pan` line differs from the control export — 0 of 44 faces moved.
- `ONETILE` changes no alignment. Its `switch` entry lands on the shared epilogue (invalidate the
  lightmap, `polyUpdateMaster`) with no case body, so it merely re-syncs each selected surface's
  existing frame onto its brush polygon. Live: the only differences from the control are sign-of-zero
  and last-bit float noise from that round trip (`+0.000000` → `−0.000000`,
  `−21.333332` → `−21.333313`). No axis, density, anchor or pan moved on any face.

A level designer's memory of "one tile" in UnrealEd is the GUI's Surface-properties scaling
(`POLY TEXSCALE`/`TEXMULT`), not this verb. ⚠ This is a statement about the committed `uned/UED22`
substrate; other UnrealEd builds were not checked.

---

## How uedcli differs

uedcli aligns surfaces model-side and does not drive `POLY TEXALIGN` at all (it would need a live
editor and a built BSP). `brush poly align --wall|--floor` with `--fresh-frame` synthesizes a frame
from `builders._tex_basis(n̂)` at unit density anchored at the seed face's centroid; without
`--fresh-frame` it adopts the seed face's frame. That is not any of the editor's rules:

| face                     | editor mode | UnrealEd `TU / TV`        | uedcli `_tex_basis` `TU / TV` | relationship
|--------------------------|-------------|---------------------------|-------------------------------|---
| +X wall                  | `WALLDIR`   | `(0,1,0) / (0,0,−1)`      | `(0,1,0) / (0,0,1)`           | V flipped (uedcli's V points up)
| −X wall                  | `WALLDIR`   | `(0,−1,0) / (0,0,−1)`     | `(0,1,0) / (0,0,−1)`          | U mirrored
| +Y wall                  | `WALLDIR`   | `(−1,0,0) / (0,0,−1)`     | `(1,0,0) / (0,0,−1)`          | U mirrored
| −Y wall                  | `WALLDIR`   | `(1,0,0) / (0,0,−1)`      | `(1,0,0) / (0,0,1)`           | V flipped
| yawed wall `(0.6,0.8,0)` | `WALLDIR`   | `(−0.8,0.6,0) / (0,0,−1)` | `(0,0,1) / (0.8,−0.6,0)`      | different axes (uedcli's U runs vertically)
| floor `(0,0,1)`          | `FLOOR`     | `(−1,0,0) / (0,−1,0)`     | `(1,0,0) / (0,1,0)`           | 180° rotation
| ceiling `(0,0,−1)`       | `FLOOR`     | `(−1,0,0) / (0,−1,0)`     | `(1,0,0) / (0,−1,0)`          | U mirrored

Plus: uedcli anchors on the seed face's centroid where the editor's projection modes anchor on a
world axis, so uedcli's result depends on which face was listed first and two invocations on one
plane need not agree. uedcli has no analogue of `WALLX`/`WALLY`/`WALLPAN`/`CLAMP`, and `--ring`
(cylinder wrap) has no analogue in the editor. Whether any of this should change is a product
question, parked on `board/inbox/` for the `poly-surface-verbs` spec.
