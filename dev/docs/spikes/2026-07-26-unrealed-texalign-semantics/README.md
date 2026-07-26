# `POLY TEXALIGN` — what UnrealEd 2.2's surface-alignment modes actually do

**Spike, 2026-07-26.** Live measurement in the committed UED22 substrate (`uned/UED22`, driven in
`dx-lum-uned:latest`) plus static disassembly of `Editor.dll`. Answers: what each `POLY TEXALIGN`
mode does to a surface's texture frame, and how that compares to what uedcli's `brush poly align`
does today.

> **Confidence markers** — ✅ = live-verified in this spike · 🔬 = read out of the shipped binary
> (disassembly / `.rdata`) and consistent with every live measurement · 📖 = read out of the binary
> only, no live confirmation.
>
> **Who should read what:** the one-paragraph answer is §0; the per-mode formulas are §3; the
> uedcli diff table the `poly-surface-verbs` spec is waiting on is §6.

---

## 0. The answer in one paragraph

`POLY TEXALIGN` never changes texel DENSITY to fit a face, and there is no
"fit-one-tile-to-this-face" mode in UnrealEd 2.2 at all — **`ONETILE` is a no-op** in this build,
and so is `WALLCOLUMN`. What the working modes do is pick an **in-plane orientation** and an
**anchor point tied to a world axis**, at a fixed density of **1 texel per world unit**. Two
families: `WALLDIR` builds a *unit* frame from the face's own direction (no stretch, anchor left
alone), while `FLOOR`/`WALLX`/`WALLY` **project the world axes orthographically onto the face**
(so a slope is stretched by `1/cos`) and re-anchor the texture on a world axis, which is what makes
a whole floor or a whole wall run share one continuous texture grid. `DEFAULT` resets a face to a
frame derived from its own winding; `CLAMP` is `DEFAULT` with `PanV` set to the texture's
`VSize − 1`; `WALLPAN` only slides the anchor to world `Z = 0`.

---

## 1. The vocabulary is bigger than `commands.md` recorded ✅ 🔬

`dev/docs/unrealed/commands.md` listed six mode tokens. The exec parser accepts **nine**:

```
POLY TEXALIGN DEFAULT|FLOOR|WALLDIR|WALLPAN|WALLCOLUMN|ONETILE|WALLX|WALLY|CLAMP [TEXELS=<n>]
```

`DEFAULT`, `WALLPAN` and `WALLCOLUMN` were missing from the doc. All nine were driven live and all
nine are accepted (no error, no crash).

The parser (`Editor.dll` RVA `0x68984`–`0x68b21`, a `ParseCommand` chain) maps each token to an
`ETexAlign` value and passes it, with the parsed `TEXELS=` integer, to
`UEditorEngine::polyTexAlign(UModel*, ETexAlign, DWORD Texels)` (export
`?polyTexAlign@UEditorEngine@@UAEXPAVUModel@@W4ETexAlign@@K@Z`, RVA `0x4c6c0`). The transaction is
described in the editor's own undo stack as `Poly Texalign` / `(Type=%i,Texels=%i)`.

| token        | `ETexAlign` 🔬 | switch target 🔬
|--------------|----------------|---
| `DEFAULT`    | 0              | `0x4c7d6`
| `FLOOR`      | 1              | `0x4cac6`
| `WALLDIR`    | 2              | `0x4cd71`
| `WALLPAN`    | 3              | `0x4cee3`
| `ONETILE`    | 4              | `0x4d5c3` — **the shared epilogue, no case body**
| `WALLCOLUMN` | 5              | `0x4d5e5` — **the `default:` branch, i.e. nothing at all**
| `WALLX`      | 6              | `0x4d011`
| `WALLY`      | 7              | `0x4d2bf`
| `CLAMP`      | 8              | `0x4c985`

`TEXELS=<n>` is **parsed and then ignored** 🔬: the third parameter arrives at `[ebp+0x10]` and that
stack slot is never read anywhere in the 725-instruction function body (only `[ebp+8]` = the model
and `[ebp+0xc]` = the mode are). Live check: `POLY TEXALIGN FLOOR TEXELS=64`,
`… ONETILE TEXELS=64` and `… WALLDIR TEXELS=64` each left every face's frame identical to the same
command without `TEXELS=` (§5.2).

---

## 2. How it was measured

**The subject.** A single level of eight brushes chosen so that every competing hypothesis is
separable — see `fixture.py`:

| brush      | what it contributes
|------------|---
| `Room`     | a **subtractive** 2048 × 1024 × 512 box: six inward-facing faces (floor, ceiling, ±X walls, ±Y walls) of three different aspect ratios
| `CubeA`    | additive 128³ cube — six equal square faces
| `BoxB`     | additive 256 × 64 × 32 box — every face a different aspect ratio, so a fit-to-face rule would show
| `CubeC`    | additive 128³ cube at `(512, 96, 48)` — same shape as `CubeA` but **off-centre**, so a world-anchored rule is distinguishable from a face-anchored one
| `SlantXZ`  | 45° ramp, face normal `(0.7071, 0, 0.7071)`
| `SlantYZ`  | non-45° slope, face normal `(0, 0.8, 0.6)`
| `SlantXYZ` | corner tetrahedron, face normal `(0.5774, 0.5774, 0.5774)`
| `WallYaw`  | a **vertical** prism yawed off both world axes: faces normal `(0.6, 0.8, 0)` and `(0.8, −0.6, 0)`, plus a general slanted top `(0.211, 0.281, −0.936)`. This is the face that separates `WALLDIR` from `WALLX` from `WALLY`.

Three textures of three different pixel sizes are bound — `GameMisc.ex_Bricks` 256×256,
`GameMisc.AirCount_A00` 256×64, `GameMisc.Calendar_2` 128×256 — so any dependence on the texture's
dimensions is visible and `USize` is distinguishable from `VSize`.

**The drive** (`probe.py`). One ephemeral editor; one round per mode, each round a single
`EXEC <file>` console script:

```
MAP NEW
MAP GRID X=1 Y=1 Z=1
OBJ LOAD FILE=Z:\resources\r000\GameMisc.utx PACKAGE=GameMisc
EDIT PASTE                    ← the eight brushes, pre-shifted −32 uu for paste drift
MAP REBUILD
POLY SELECT ALL
POLY TEXALIGN <MODE>
MAP EXPORT FILE=Z:\work\<uuid>.t3d      ← last line: doubles as the completion marker
```

A tenth round applies no alignment at all (`NONE`) and is the control. The host polls for the export
file rather than sleeping (console driving is fire-and-forget). A re-run of the control round at the
end of the session came back **identical except for the engine-assigned `LevelInfo`/builder-brush
names** — the operation is deterministic and the reuse of one editor across rounds does not
contaminate the result.

**Why the readback works at all.** `POLY TEXALIGN` edits `Model->Surfs` — BSP surfaces, which exist
only after a `MAP REBUILD` — but it finishes each surface with
`UEditorEngine::polyUpdateMaster(Model, iSurf, 1, 1)`, which writes the surface's frame back down
into the **originating brush polygon**. That is what `MAP EXPORT` prints, so an ordinary whole-level
export is a faithful readback. The fixture's brushes are deliberately non-touching so CSG splits no
face and every brush polygon maps to exactly one surface.

**The analysis** (`analyze.py`, `summarize.py`). Each exported polygon's stored
`Origin`/`TextureU`/`TextureV`/`Pan` is lifted to world space with the same transform the renderer
uses (`preview_native._world_uv_frame`), then reported with `|TextureU|`, `|TextureV|`, the face's
world normal, and the `(U, V)` range the face spans under the canonical convention
`U = (Vertex − Origin)·TextureU + PanU` (`dev/docs/unrealed/t3d.md`).

**⚠ The normal `TEXALIGN` sees is the SURFACE normal, not the brush polygon's** ✅. CSG reverses a
**subtractive** brush's polygons, so for `Room` every formula below takes the *negated* exported
normal — the one pointing into the room. This is not cosmetic: it flips `WALLDIR`'s U direction.
Additive brushes are unaffected. The reference model encodes this and it is what makes all 396
predictions land (§4).

---

## 3. The measured semantics, mode by mode

Notation: `N` = the **surface** normal (unit); `P` = any point of the surface plane; `d = P·N`;
`X̂ Ŷ Ẑ` = the world axes; `proj(A) = A − N (N·A)` is `A` projected into the face plane (note
`|proj(A)| = sqrt(1 − (N·A)²) ≤ 1`, i.e. **not** renormalized). Every mode writes
`iLightMap = −1` (forces the lightmap to be rebuilt) and then `polyUpdateMaster`.

### 3.1 `FLOOR` / `WALLX` / `WALLY` — orthographic projection down a world axis ✅

One family, three instances. Each drops one world axis `a`, anchors the texture where the face's
plane crosses that axis, and builds `TextureU`/`TextureV` by projecting the other two world axes
onto the face and **negating** them:

| mode    | axis `a` | guard            | new `Origin`    | `TextureU` | `TextureV`
|---------|----------|------------------|-----------------|------------|---
| `FLOOR` | Z        | `\|N.Z\| > 0.05` | `(0, 0, d/N.Z)` | `−proj(X̂)` | `−proj(Ŷ)`
| `WALLX` | X        | `\|N.X\| > 0.05` | `(d/N.X, 0, 0)` | `−proj(Ŷ)` | `−proj(Ẑ)`
| `WALLY` | Y        | `\|N.Y\| > 0.05` | `(0, d/N.Y, 0)` | `−proj(X̂)` | `−proj(Ẑ)`

`Pan` is set to `(0, 0)` — measured, not assumed: see §5.3, which re-runs the fixture with a
non-zero authored pan. A face failing the guard is left untouched, pan included.

Consequences, all of them visible in the numbers:

- **Density is 1 texel/uu only on a face perpendicular to the dropped axis.** On anything tilted the
  texture is **stretched** by `1/|proj|`. Measured on `SlantXZ:3` (normal `(0.7071, 0, 0.7071)`)
  under `FLOOR`: `TextureU = (−0.5, 0, +0.5)`, `|TextureU| = 0.70711` — exactly `sqrt(1 − N.X²)`,
  a 41 % stretch along U. On `WallYaw:2` (normal `(0.211, 0.281, −0.936)`) under `WALLX`:
  `|TextureV| = 0.35112 = sqrt(1 − N.Z²)`, a ~2.8× stretch. This is a **planar projection**, exactly
  like painting the texture on a plane perpendicular to `a` and shining it onto the face.
- **The anchor is a world axis, not the face.** `CubeC` is a 128³ cube centred at `(512, 96, 48)`;
  its top face lies at `z = 112`. `FLOOR` moved that face's `Origin` from the authored centroid
  `(512, 96, 112)` to **`(0, 0, 112)`**, and the face then spans `U ∈ [−576, −448]`,
  `V ∈ [−160, −32]`. Every horizontal face at the same height therefore shares one texture grid
  keyed to the world origin — which is the entire point of the mode. The same face under `WALLDIR`
  or `ONETILE` keeps `Origin = (512, 96, 112)` and spans `U, V ∈ [−64, 64]`.
- **The guards are what stop the anchor exploding.** `d/N[a]` diverges as the face turns parallel to
  the anchor axis, and the 0.05 floor caps the multiplier at 20×. Note WHICH offset gets amplified:
  `d/N[a] = P[a] + (the other two components of P·N)/N[a]`, so it is the face's offset TRANSVERSE
  to the anchor axis that blows up, not its offset along it. A wedge 1600 uu off the origin
  transversely, with `|N| = 0.049` on the anchor axis, anchors ~32,600 uu out — right at the edge of
  UE1's ±32768 world. A caller that mimics these modes must keep the guard. *No claim is made that a
  large anchor crashes the editor: an earlier guard fixture did kill it twice on the `WALLX` round,
  but a later run of the same fixture died on a round that ran no `TEXALIGN` at all, so those deaths
  are the ordinary UED22 flakiness (`quirks.md` "Stability"), not evidence about the anchor.*

### 3.2 `WALLDIR` — a unit frame along the wall's own direction ✅

Guard: `|N.Z| < 0.95` (i.e. anything but a near-horizontal face).

```
TextureU = normalize( (N.Y, −N.X, 0) )        # horizontal, along the wall
TextureV = normalize( TextureU × N )          # in-plane, down the face
if TextureV.Z > 0:  TextureU, TextureV = −TextureU, −TextureV
Origin  unchanged;  Pan = (0, 0)               # zeroed — measured in §5.3
```

Both axes are **unit**, on every face including slanted ones, so `WALLDIR` never stretches. The final
flip guarantees `TextureV.Z ≤ 0` — **V points downwards**, which is the correct orientation for a
UE1 texture (whose V=0 row is its top). The `Origin` is left exactly where it was, so `WALLDIR`
changes orientation and nothing else.

The conditional is written as a conditional in the binary (`Editor.dll` 0x4ce3c–0x4ce7c) but is in
fact **unconditional**: `(TextureU × N).Z = (N.x² + N.y²)/|(N.y,−N.x,0)|`, which is positive on every
face the `|N.Z| < 0.95` guard admits. So the whole mode reduces to
`TextureU = normalize(−N.Y, N.X, 0)`, `TextureV = −normalize(TextureU × N)`. Worth knowing if you
reimplement it: the branch never has to be evaluated, and a reader who assumes it sometimes does not
fire will get the sign wrong.

Worked example, `WallYaw:3`, normal `(0.6, 0.8, 0)`:
`TextureU = (−0.8, 0.6, 0)`, `TextureV = (0, 0, −1)`, `|TextureU| = |TextureV| = 1`,
`Origin` unchanged at `(688, 384, 30)`. The same face under `WALLX` instead gets
`TextureU = (0.48, −0.36, 0)` (`|TextureU| = 0.6`) anchored at `(1200, 0, 0)`, and under `WALLY`
`TextureU = (−0.64, 0.48, 0)` (`|TextureU| = 0.8`) anchored at `(0, 900, 0)`. **That is the whole
difference between the three wall modes**: `WALLDIR` follows the face, `WALLX`/`WALLY` project down
a world axis and stretch by `1/|N-perp component|`.

### 3.3 `WALLPAN` — slide the anchor to world Z = 0 ✅

Guards: `|N.Z| < 0.95` 🔬 **and** `|TextureV.Z| > 0.05` 🔬 — both from `.rdata`, and **neither is
bracketed live**: §5.1's wedges cover the other four guards, and the one live `WALLPAN` datum is a
face whose `TextureV.Z` was exactly 0. So "a guard near zero exists" is ✅ and "it is 0.05" is 🔬.

```
Origin ← Origin + TextureV · ( −Origin.Z / TextureV.Z )
TextureU, TextureV, Pan  ALL unchanged
```

That is: keep the frame, walk the anchor along `TextureV` until its Z reaches 0. Measured on
`CubeC:0` (a +X face of a cube whose centre is at `z = 48`): `Origin` went from `(576, 96, 48)` to
`(576, 96, 0)`, with `TextureU`/`TextureV`/`Pan` byte-identical. Across the whole fixture `WALLPAN`
touched **only `Origin` lines** — 12 of them, spread over the five brushes with a face whose anchor
Z was non-zero (`CubeC` 4, `SlantXYZ` 3, `SlantXZ` 2, `SlantYZ` 2, `WallYaw` 1). It is the "make every wall's vertical texture phase agree" operation.

### 3.4 `DEFAULT` — regenerate the frame from the polygon's own winding ✅

`polyTexAlign` pulls the master brush polygon (`polyFindMaster`), blanks its texture vectors, and
calls `FPoly::Finalize`, which regenerates them from the winding:

```
TextureU = normalize( (Vertex[0] − Vertex[i]) × N_poly )     # first i ≥ 1 that is non-degenerate
TextureV = normalize( N_poly × TextureU )
Origin  unchanged;  Pan = (0, 0)               # zeroed on EVERY face — no guard (§5.3)
```

Note `N_poly` here is the **brush polygon's own** outward normal (what `Finalize` recomputes from
the winding), *not* the surface normal — verified on the subtractive `Room`, whose `DEFAULT` result
matches the un-negated normal. Both axes are unit. Worked example, `Room:0` (vertices
`(1024,−512,−256), (1024,512,−256), (1024,512,256), (1024,−512,256)`, polygon normal `(1,0,0)`):
`(V0−V1) × N = (0,−1024,0) × (1,0,0) = (0,0,1024)` → `TextureU = (0,0,1)`,
`TextureV = N × TextureU = (0,−1,0)`. Measured exactly that.

Because the result depends on **which vertex the polygon happens to start at**, `DEFAULT` is a
"reset this face to a valid frame" operation, not a design tool: two coplanar faces wound from
different corners get frames 90° apart.

### 3.5 `CLAMP` — `DEFAULT`, plus `PanV = VSize − 1` ✅

Identical to `DEFAULT` in every field except `PanV`, which is set to the bound texture's **height in
texels minus one** 🔬 (`Texture->[+0x38] − 1`). Measured across the three fixture textures:

| texture                 | USize × VSize | `CLAMP` `Pan`
|-------------------------|---------------|---
| `GameMisc.ex_Bricks`    | 256 × 256     | `(0, 255)`
| `GameMisc.AirCount_A00` | 256 × 64      | `(0, 63)`
| `GameMisc.Calendar_2`   | 128 × 256     | `(0, 255)`

`AirCount_A00` is the decisive one: 256 wide, 64 tall, pan 63 ⇒ the field is **`VSize`**, not
`USize`. `PanU` is always 0 — and §5.3 shows it is actively ZEROED, not merely left at zero. All that is *measured* is the write. Since `Pan` is added to the texel
coordinate, it shifts the face's V phase by one full texture height less one texel — but what that
is FOR, and what it looks like on screen, **was not determined**: no render was made and no
interaction with texture addressing or `PolyFlags` was probed. Do not infer a rendering behaviour
from this entry.

### 3.6 `ONETILE` and `WALLCOLUMN` — not implemented ✅ 🔬

- **`WALLCOLUMN` does nothing whatsoever.** Its switch entry is the same address as the `default:`
  branch (`0x4d5e5` = the `ja` target of `cmp eax, 8`), which just advances the surface loop. Live:
  the export after `POLY TEXALIGN WALLCOLUMN` has **not one changed `Origin`/`TextureU`/`TextureV`/
  `Pan` line** against the control export — 0 of 44 faces moved. (The two files are not byte-equal
  overall, but only because the engine renumbers `LevelInfo`/the builder brush on every `MAP NEW`.)
- **`ONETILE` changes no alignment either.** Its switch entry lands on the shared epilogue
  (`iLightMap = −1` then `polyUpdateMaster`), with no case body of its own — so it re-syncs each
  selected surface's existing frame down onto its brush polygon and stops. Live: 13 changed *lines*
  across the whole fixture, and every one of them is a sign-of-zero or last-bit float difference
  from the frame's round trip through `Model->Vectors` (`TextureV +0.000000,−1.000000,+0.000000` →
  `−0.000000,−1.000000,−0.000000`; `Origin −21.333332` → `−21.333313`). No axis, no density, no
  anchor and no pan moved on any face.

**So UnrealEd 2.2 has no fit-a-tile-to-a-face operation at all**, and nothing anywhere in
`polyTexAlign` reads a texture's `USize`/`VSize` except `CLAMP`'s single `PanV` write. Any
"one tile" behaviour a level designer remembers from UnrealEd came from the GUI's Surface-properties
scaling controls (`POLY TEXSCALE`/`TEXMULT`), not from this verb.

---

## 4. The rules above are executable, and they reproduce every measurement ✅

`texalign_model.py` is a pure-Python statement of §3. `verify_model.py` runs it against the captured
exports and compares `Origin`, `TextureU`, `TextureV` and `Pan` for **every (mode, face) pair**:

```
$ python3 verify_model.py <outdir>
396/396 (mode, face) predictions match
```

44 faces × 9 modes, with tolerances of 2e-3 on a texture vector (`bspAddVector(…, Exact=0)` shares
near-equal vectors between surfaces) and 0.2 uu on an anchor point (`bspAddPoint` plus the float32
world↔brush-local round trip). `Pan` is compared exactly.

`measured.json` is the distilled golden: every face's geometry, and every mode's resulting frame,
straight out of the editor. `uedcli/tests/test_engine_facts.py` re-runs the model against it, so a
drift in the documented rule trips a red test. (The two goldens are committed DATA, so they cannot
by themselves detect a substrate swap; the three byte-pattern regressions watch `Editor.dll`.)

⚠ **This capture cannot test `Pan`.** All 44 control faces already carried `Pan = (0,0)`, so a mode
that zeroes it and a mode that ignores it produce identical exports here. §5.3 is the run that
separates them, and `pans.json` its golden.

---

## 5. Guards, arguments, grammar and scope ✅

A second fixture (`fixture2.py`) puts ONE wedge per level, whose single test face has a normal
straddling a guard threshold; `probe2.py` exports the level with and without the mode under test, in
one console script, and `guards.py` reports whether that face's frame moved.

### 5.1 Both guard thresholds, bracketed live to ±0.001

| level   | test-face normal      | mode      | result
|---------|-----------------------|-----------|---
| `NZ049` | `(0.9988, 0, 0.0490)` | `FLOOR`   | **UNCHANGED**
| `NZ051` | `(0.9987, 0, 0.0510)` | `FLOOR`   | **CHANGED**
| `NY049` | `(0.9988, 0.0490, 0)` | `WALLY`   | **UNCHANGED**
| `NY051` | `(0.9987, 0.0510, 0)` | `WALLY`   | **CHANGED**
| `NX049` | `(0.0490, 0.9988, 0)` | `WALLX`   | **UNCHANGED**
| `NX051` | `(0.0510, 0.9987, 0)` | `WALLX`   | **CHANGED**
| `NZ949` | `(0.3153, 0, 0.9490)` | `WALLDIR` | **CHANGED**
| `NZ951` | `(0.3092, 0, 0.9510)` | `WALLDIR` | **UNCHANGED**

So `FLOOR`/`WALLX`/`WALLY` act iff `|N[axis]| > 0.05` and `WALLDIR` acts iff `|N.Z| < 0.95`, with
each threshold pinned live to a 0.002-wide window around the `.rdata` constant. **`WALLPAN`'s two guards are NOT bracketed** — no wedge targets them. The main fixture shows only
that a guard near zero exists on the second one: a vertical face whose `TextureV` was horizontal
(`(0.8, −0.6, 0)`, `TextureV.Z` exactly 0) was left alone even though its anchor sat at `z = 30`.
Their *values* rest on `.rdata` (🔬) alone. Closing that would take two more wedges and is the one
loose end §7 carries forward.

### 5.2 Arguments, grammar, selection scope, BSP dependency

Each row is a face-by-face comparison of two exports of the same level (11 faces):

| probe                                                        | result
|--------------------------------------------------------------|---
| `TEXALIGN FLOOR TEXELS=64` vs `TEXALIGN FLOOR`               | **0/11 faces differ** — `TEXELS=` is inert
| `TEXALIGN WALLDIR TEXELS=64` vs `TEXALIGN WALLDIR`           | **0/11 differ**
| `TEXALIGN ONETILE TEXELS=64` vs `TEXALIGN ONETILE`           | **0/11 differ**
| `TEXALIGN ONETILE` vs the state immediately before it        | **0/11 differ** — `ONETILE` is inert (2nd, independent confirmation)
| `POLY TEXALIGN` with **no mode token**                       | **0/11 differ** — rejected cleanly, nothing changes, no crash
| `POLY TEXALIGN BOGUS`                                        | **0/11 differ** — same
| `POLY SELECT NONE` then `TEXALIGN WALLDIR`                   | **0/11 differ** — the verb is SELECTION-SCOPED
| `POLY SELECT ALL` then `TEXALIGN WALLDIR` (positive control) | **6/11 differ**
| `TEXALIGN WALLDIR` with **no `MAP REBUILD`**                 | **0/11 differ** — no BSP, no surfaces, nothing to align

**No mode token and an unknown token behave identically to doing nothing** — the parser's chain falls
through and the verb is not executed. Neither errors visibly nor destabilises the editor.

**The BSP dependency is the practical one for uedcli**: `POLY TEXALIGN` walks `Model->Surfs`, which
only CSG produces, so driving it would cost a paste + `MAP REBUILD` per alignment. That is a strong
independent reason for `brush poly align` to stay model-side whatever it decides about matching the
editor's *rules*.

### 5.3 Which modes ZERO the `Pan`, measured against a NON-ZERO one

The main fixture cannot answer this: all 44 of its faces already carried `Pan = (0,0)`, so "the mode
sets the pan to zero" and "the mode does not touch the pan" produce identical exports. `probe3.py`
re-runs the same fixture with **`Pan U=7 V=13` authored on every face**, which separates them
(counts are over the 44 faces):

| mode         | resulting `Pan`
|--------------|---
| *control*    | `(7,13)` ×44
| `WALLCOLUMN` | `(7,13)` ×44 — untouched
| `ONETILE`    | `(7,13)` ×44 — untouched
| `WALLPAN`    | `(7,13)` ×44 — untouched (it moves the anchor, never the pan)
| `DEFAULT`    | `(0,0)` ×44 — zeroed on every face (no guard)
| `FLOOR`      | `(0,0)` ×16, `(7,13)` ×28 — zeroed on exactly the 16 faces with `\|N.Z\| > 0.05`
| `WALLDIR`    | `(0,0)` ×32, `(7,13)` ×12 — zeroed on exactly the 32 with `\|N.Z\| < 0.95`
| `WALLX`      | `(0,0)` ×19, `(7,13)` ×25
| `WALLY`      | `(0,0)` ×19, `(7,13)` ×25
| `CLAMP`      | `(0,255)` ×33, `(0,63)` ×11 — `PanU` zeroed, `PanV` = that face's texture `VSize − 1`

Three things fall out at once. The **pan half of every mode's rule is now measured**, not inferred
from a fixture that could not tell. The **guards are re-confirmed independently** — the split
16/28 and 32/12 is exactly the guard partition of the fixture, from a completely different signal
than §5.1's. And `CLAMP`'s `VSize` dependence is re-confirmed on a second run: the 11 faces textured
`AirCount_A00` (VSize 64) came back `(0,63)` while the other 33 came back `(0,255)`.

`verify_pan.py` checks the model's pan prediction against all of it: **396/396 match**.
`pans.json` is the committed golden.

⚠ **These probes never got a fresh editor for free.** On this box (under 1 GB free RAM) UnrealEd
died roughly every second round regardless of what was being driven — including on rounds that ran
no `TEXALIGN` at all — so `probe2.py` re-spins the container on failure and skips already-captured
rounds. That is `quirks.md` "Stability", not a property of this verb. (`probe3.py`, run later with
memory freed, completed all ten of its exports in a single editor session.)

---

## 6. Diff against uedcli — the part the spec is waiting on

uedcli today (`uedcli/polyalign.py`) has `brush poly align --wall|--floor|--ring`, each of which
either **adopts the seed face's frame** (default) or, with `--fresh-frame`, synthesizes one from
`builders._tex_basis(n̂)` — a canonical basis seeded from the world axis *least* aligned with the
normal — at **unit** density, anchored at the **seed face's centroid**, with `Pan = (0, 0)`.

| UnrealEd mode | what it does (§3)                | uedcli equivalent                    | verdict
|---------------|----------------------------------|--------------------------------------|---
| `FLOOR`       | project down world Z, stretch    | `brush poly align --floor`           | **diverges** on orientation, anchor AND slope handling — §6.1, §6.2
| `WALLDIR`     | unit frame along the face        | `brush poly align --wall`            | **closest analogue, still diverges** — different axes, different anchor, and uedcli's V can point UP
| `WALLX`       | project down world X, stretch    | —                                    | **no equivalent**
| `WALLY`       | project down world Y, stretch    | —                                    | **no equivalent**
| `WALLPAN`     | re-anchor the phase to world Z=0 | —                                    | **no equivalent** — `brush poly set --pan-to/--pan-by` moves the *integer texel* pan, a different quantity
| `DEFAULT`     | frame from the polygon winding   | —                                    | **no equivalent, and none wanted** — winding-order dependent
| `CLAMP`       | `DEFAULT` + `PanV = VSize − 1`   | —                                    | **no equivalent**; what it is for is undetermined (§7)
| `ONETILE`     | **nothing**                      | proposed `brush poly align one-tile` | **there is nothing to conform to** — the spec's `one-tile` is a uedcli invention, not a port of an editor mode
| `WALLCOLUMN`  | **nothing**                      | —                                    | n/a
| —             | —                                | `brush poly align --ring`            | **uedcli-only** — UnrealEd has no cylinder-wrap mode

### 6.1 The orientations side by side

`builders._tex_basis(n̂)` against the editor's rule for the same face, on the seven directions that
matter (computed by `texalign_model.py` and `builders._tex_basis`; each cell is `TextureU / TextureV`):

| face                     | editor mode | UnrealEd `TU / TV`        | uedcli `_tex_basis` `TU / TV` | relationship
|--------------------------|-------------|---------------------------|-------------------------------|---
| +X wall                  | `WALLDIR`   | `(0,1,0) / (0,0,−1)`      | `(0,1,0) / (0,0,1)`           | **V flipped** (uedcli's V points UP)
| −X wall                  | `WALLDIR`   | `(0,−1,0) / (0,0,−1)`     | `(0,1,0) / (0,0,−1)`          | **U mirrored**
| +Y wall                  | `WALLDIR`   | `(−1,0,0) / (0,0,−1)`     | `(1,0,0) / (0,0,−1)`          | **U mirrored**
| −Y wall                  | `WALLDIR`   | `(1,0,0) / (0,0,−1)`      | `(1,0,0) / (0,0,1)`           | **V flipped**
| yawed wall `(0.6,0.8,0)` | `WALLDIR`   | `(−0.8,0.6,0) / (0,0,−1)` | `(0,0,1) / (0.8,−0.6,0)`      | **different axes** — uedcli's U runs VERTICALLY, 90° from the editor's
| floor `(0,0,1)`          | `FLOOR`     | `(−1,0,0) / (0,−1,0)`     | `(1,0,0) / (0,1,0)`           | **180° rotation**
| ceiling `(0,0,−1)`       | `FLOOR`     | `(−1,0,0) / (0,−1,0)`     | `(1,0,0) / (0,−1,0)`          | **U mirrored**

Read that as: **the two rules never agree on a single one of the seven**, and the way they disagree
is not even consistent — sometimes a mirror, sometimes a rotation, sometimes a different pair of
axes entirely. `WALLDIR` always drives V downwards (its final `TextureV.Z ≤ 0` flip); `_tex_basis`
lets V point up or down depending on which way the face happens to face, so a texture with an
up/down asymmetry comes out inverted on roughly half the walls of a room. And on a wall that is not
axis-aligned the two are 90° apart, because `_tex_basis` seeds from the world axis *least* aligned
with the normal — which for a vertical yawed wall is Ẑ — whereas `WALLDIR` derives U from the wall's
own horizontal direction.

### 6.2 The anchors side by side

`FLOOR`/`WALLX`/`WALLY` anchor on a **world axis**; `--fresh-frame` anchors on the **seed face's
centroid**; `WALLDIR`/`DEFAULT`/`CLAMP` leave the anchor alone. Measured: `CubeC`'s top face
(a 128×128 face at `z = 112`, centred at `x=512, y=96`) came back from `FLOOR` anchored at
`(0, 0, 112)`, from every non-projecting mode at `(512, 96, 112)`. On a slope they disagree further
still: `FLOOR` stretches by `1/|proj|` while uedcli stays at unit density.

Note what uedcli's slant handling actually is, because it is easy to misread: `_check_orientation`
(`uedcli/polyalign.py`) is a **dominant-normal-axis** test, not a "is this face axis-aligned?" test. It
rejects a face from `--wall` iff its dominant axis is Z and from `--floor` iff it is not — so a
45° ramp `(0.7071, 0, 0.7071)` is **accepted** by `--wall`, a 30° ramp `(0.5, 0, 0.866)` is
**accepted** by `--floor`, and the corner face `(0.577, 0.577, 0.577)` is **accepted** by `--wall`
(all three checked by calling it). uedcli therefore already aligns most slanted faces — silently, at
unit density, with `_tex_basis`. The divergence from the editor on a slope is not "we refuse and it
doesn't"; it is **"we lay an undistorted frame where the editor lays a projected, stretched one"**.

### 6.3 What this means for `dev/docs/specs/2026-07-26-poly-surface-verbs.md` §4b

**Reported, not applied.** The spike was commissioned with an explicit instruction not to edit that
spec, so nothing below was written into it — including the three plain factual corrections, which
need no ruling at all. ⚠ **Until someone applies them, §4b tells its reader three false things**:
"six modes against our two" (there are nine), "we cannot currently say what any of them does" (all
nine are measured), and "`ONETILE` … fit exactly one tile to the face" (it is a no-op and fits
nothing). Whoever builds §4b should fix those first and then rule on the four questions below.

1. **`align wall|floor` "orientation from `builders._tex_basis(n̂)`" does not match UnrealEd.**
   Neither the sign convention (V up vs V down) nor, on a wall, the axis choice. If matching the
   editor matters — and for a tool whose output sits beside retail Deus Ex geometry it plausibly
   does — `wall` should use `WALLDIR`'s rule and `floor` should use `FLOOR`'s. If matching does not
   matter, the divergence is fine but should be a **stated** decision, because right now the spec
   reads as if `_tex_basis` were the editor's rule.
2. **The anchor differs and that is the bigger deal.** UnrealEd anchors `FLOOR`/`WALLX`/`WALLY` on a
   **world axis**, which is precisely what makes separately-aligned faces across a level share one
   grid. uedcli anchors on the **seed face's centroid**, which makes the result depend on which face
   you happened to list first, and makes two independently-run `poly align` invocations on the same
   plane disagree. A world-axis anchor would make `poly align --floor` idempotent and
   set-order-independent.
3. **`one-tile` has no UnrealEd counterpart** — `ONETILE` does nothing in UED22. The spec's
   stretch-to-fill-anchored-at-the-min-corner design is therefore an original uedcli feature and
   should say so rather than implying it ports an editor mode. Nothing in this spike argues against
   the feature; it just cannot be justified by "that's what the editor does".
4. **Two modes worth adding, both cheap and both absent:** a `WALLPAN`-equivalent (re-phase a wall's
   texture to world `Z = 0` without touching its axes) and the `WALLX`/`WALLY` projection pair
   (a stretched but perfectly continuous run across walls that are not quite parallel). The
   projection modes are the only thing in UnrealEd that handles a *turning* wall run, which is what
   `align run` is reaching for.
5. **`--fresh-frame`'s unit density matches** — every UnrealEd mode is 1 texel/uu on a face square to
   the projection, and none of them scales to fit. That part of the spec is right.
6. **Slanted faces — uedcli already aligns them, and differently.** `_check_orientation` is a
   dominant-axis test, so a 45° ramp goes through `--wall` and a 30° ramp through `--floor` today,
   getting an undistorted unit frame. UnrealEd's projection family instead stretches by `1/|proj|`.
   Both are defensible; the point is that this is a live behavioural difference on real geometry,
   not a missing feature, and the spec does not currently say which one it wants.

---

## 7. What was NOT determined

- **What `CLAMP` is for.** Its write is measured exactly (`DEFAULT` + `PanV = VSize − 1`), but the
  *rendering* consequence was not observed: no render was made and no interaction with texture
  addressing or `PolyFlags` was probed. Settling it would need a `--game` render of one face under
  `CLAMP` beside the same face under `DEFAULT`.
- **Whether `ONETILE`/`WALLCOLUMN` are implemented in other UnrealEd builds.** This is a statement
  about the committed `uned/UED22` substrate only. Retail UnrealEd 2.0 / UT's `UnrealEd` may differ;
  nothing here was checked against another binary.
- **Behaviour on a ROTATED or SCALED brush.** Every fixture brush has identity `Rotation`,
  `MainScale` and `PostScale`. `polyTexAlign` composes with `ABrush::BuildCoords` only in the
  `DEFAULT`/`CLAMP` path (which transforms the master polygon into world space); the other modes work
  in world space throughout and should be indifferent, but that was not measured.
- **Behaviour when a brush polygon is split into several surfaces by CSG.** The fixture deliberately
  avoids it; with several surfaces writing back to one master polygon, the last one wins, but that
  was not measured.
- **What the projection modes do with an OFF-PLANE base point.** They anchor at
  `(Surf->pBase · N)/N[a]` — the surface's own base point, which after CSG always lies in the face's
  plane, so the fixture cannot separate "the base point" from "any point of the plane". A caller
  feeding an authored frame whose `Origin` has drifted off-plane (uedcli's adopt-seed path can
  produce one) is outside what was measured, and `texalign_model.py` follows the binary rather than
  guessing.
- **`WALLPAN`'s two guard THRESHOLDS.** `|N.Z| < 0.95` and `|TextureV.Z| > 0.05` are read from
  `.rdata` and pinned by reference count, but no wedge brackets them live the way §5.1 brackets the
  other four. Two more one-wedge levels would close it.

---

## 8. Files

| file                        | what
|-----------------------------|---
| `fixture.py`                | builds the eight-brush measurement level
| `probe.py`                  | drives one ephemeral editor through all nine modes + the control
| `analyze.py`                | per-face world texture frame, densities and `(U,V)` spans
| `summarize.py`              | the cross-mode table quoted throughout §3
| `fixture2.py` / `probe2.py` | the guard-threshold brackets and the argument/grammar/scope probes (§5)
| `guards.py`                 | reads the §5.1/§5.2 captures; writes `guards.json`
| `probe3.py`                 | re-runs the main fixture with a NON-ZERO authored pan (§5.3)
| `verify_pan.py`             | model-vs-measurement check for `Pan`; writes `pans.json`
| `texalign_model.py`         | the executable statement of §3
| `verify_model.py`           | model-vs-measurement check; writes `measured.json`
| `disasm.py`                 | the `Editor.dll` disassembly helper used for §1 and the formulas
| `measured.json`             | golden: every face's geometry + every mode's resulting frame
| `guards.json`               | golden: whether the editor touched each near-threshold face
| `pans.json`                 | golden: the `Pan` each mode produced from an authored `(7,13)`

`disasm.py` needs `capstone` and `pefile`; nothing else in the harness has a dependency outside
uedcli itself, and the two `verify_*.py` checkers and `guards.py` are read-only (no editor).

Throwaway output (the `MAP EXPORT` T3Ds, logs) stayed in `_scratch/texalign/` per `CLAUDE.md`.

## 9. Where this landed

- `dev/docs/unrealed/texalign.md` — the engine-fact doc (this spike's durable half).
- `dev/docs/unrealed/commands.md` — the `POLY` section now points at it and lists all nine tokens.
- `uedcli/tests/test_engine_facts.py` — six regressions: `test_texalign_parser_maps_nine_tokens…`,
  `…onetile_and_wallcolumn_are_unimplemented…`, `…guard_thresholds_are_005_and_095_and_texels_is_ignored`,
  `…model_reproduces_every_measured_editor_frame`, `…guards_match_the_editor_on_near_threshold_faces`,
  `…pan_handling_matches_the_editor_against_a_non_zero_pan`.
- `dev/docs/architecture.md` and `uedcli/polyalign.py`'s module docstring both called `poly align`
  "the offline analogue of UnrealEd's `TEXTURE ALIGN`" — a verb that does not exist, describing a
  rule this spike disproved. Both corrected.
- `dev/docs/board/` — the `[spike]` item is closed (`done.md`); the four spec decisions the findings
  raise are filed as an `[OWNER — decide]` item on `inbox.md`.
- `docs/usage.md` + `docs/leveldesign/general/textures-and-surfaces.md` — both said or implied that
  `brush poly align` reproduces UnrealEd's own auto-align. It does not; corrected.
