# Textures & surfaces — flags, alignment, procedural textures, the DX catalog  [ENGINE] (+ DX)

Part of the split-out **level-design knowledge base**. FULL dev reference for UE1/DX surface texturing:
the surface poly-flag catalog with hex values, alignment and scrolling, `MyLevel` embedding, detail/
environment mapping, the procedural `Fire.u` texture family internals, and the Deus Ex `CoreTex*`
catalog. Siblings: [`lighting.md`](lighting.md) · [`movers.md`](movers.md) ·
[`actors-collision-pathing.md`](actors-collision-pathing.md). Parent monolith:
[`README.md`](README.md). Engine-driving: [`../../commands.md`](../../commands.md),
[`../../t3d.md`](../../t3d.md).

**Confidence markers:** ✅ uedctl-used / live-verified · 🔬 live-probed against the real DX binary/editor ·
📖 tutorial-corpus (vocabulary real, semantics to confirm). **[ENGINE]** = generic UE1 · **[DX]** =
Deus-Ex-specific.

Texturing is **per-surface**: you pick a texture from a package and set its alignment + flags. Flags
change how a surface *renders*, never its geometry.

**uedctl seat** ✅: `brush poly find` prints face selectors → `brush poly set - --texture … --add-flag …
--remove-flag … --pan-to/--pan-by`; `brush poly align --wall|--floor|--ring`; `brush poly list` inspects.
Flags are always set **by NAME** (`--add-flag Masked`), never by bit value. Faces are targeted by
`BRUSH:SELECTOR` (`Wall1:3,5` or `Wall2:all`).

> **UnrealEd GUI equivalent:** select faces, open *Surface Properties* (F5), set texture / flags / pan /
> align.

---

## 1. Surface flags — the poly-flag catalog  🔬

Surface flags are a bitmask on each poly. Sum the hex values to combine. Hex values are 🔬 binary-verified
(they match UE1's `EPolyFlags` and uedctl's `query.py PF_NAMES`). **Not every flag is settable via
`--add-flag`:** uedctl exposes 16 names; `Bright Corners`, `Small/Big Wavy`, and `High/Low Shadow Detail`
are real poly-flags but are **not** in that set (they would need a raw bit write) — listed here for
completeness and tagged *(no `--add-flag`)*.

| Flag (F5 name / uedctl) | Hex | Effect |
|---|---|---|
| **Unlit** | `0x400000` (`PF_Unlit`) | Fullbright — skips the lightmap entirely (always max brightness). |
| **Masked** | `0x2` (`PF_Masked`) | **Palette index 0 → transparent.** Span-clipped but **non-occluding**, drawn in the deferred pass with translucent/modulated (a small framerate cost). Grilles, foliage, cut-outs. |
| **Translucent** | `0x4` (`PF_Translucent`) | Additive blend — **masks DARK colours** (black → invisible; bright → glows). Glass, holograms, energy. |
| **Modulated** | `0x40` (`PF_Modulated`) | Modulate (2×) blend — **50% grey is neutral/transparent**; darker darkens the backdrop, lighter brightens it. Dirt, decals, grime overlays. |
| **Fake Backdrop** | `0x80` (`PF_FakeBackdrop`) | Draws the **skybox** through this surface (a "sky window"). **Requires an `Unlit` companion** on the same surface. |
| **2-Sided** | `0x100` (`PF_TwoSided`) | Renders both faces (sheets, banners, chain-link). |
| **Mirror** | `0x8000000` (`PF_Mirrored`) | Reflective surface. **Editor-invisible.** NOT a zone portal. |
| **Special Lit** | `0x100000` (`PF_SpecialLit`) | Lit ONLY by lights with `bSpecialLit=True` (see [`lighting.md`](lighting.md)). Lets you light one surface in isolation. |
| **Bright Corners** *(no `--add-flag`)* | `0x80000` (`PF_BrightCorners`) | Kills dark seams at surface edges (lightmap edge brightening). |
| **Small Wavy** *(no `--add-flag`)* | `0x2000` (`PF_SmallWavy`) | Small ripple distortion. |
| **Big Wavy** *(no `--add-flag`)* | `0x1000` (`PF_BigWavy`) | Large ripple distortion. |
| **No Smooth** | `0x800` (`PF_NoSmooth`) | Disables bilinear texture smoothing (crisp pixels). |
| **High Shadow Detail** *(no `--add-flag`)* | `0x800000` (`PF_HighShadowDetail`) | **Per-surface lightmap RESOLUTION control — high.** Crisp shadows (more lumels, more memory). |
| **Low Shadow Detail** *(no `--add-flag`)* | `0x8000` (`PF_LowShadowDetail`) | Per-surface lightmap resolution — **low** (coarse, cheap). |
| **Portal** | `0x4000000` (`PF_Portal`) | Zone-portal surface (see [`zones-performance.md`](./zones-performance.md)). |
| **Auto U-Pan** | `0x200` (`PF_AutoUPan`) | Scrolls in U (speed set on the zone — §2.1). |
| **Auto V-Pan** | `0x400` (`PF_AutoVPan`) | Scrolls in V (speed set on the zone — §2.1). |
| **Environment** | `0x10` (`PF_Environment`) | Environment/reflection mapping (gated by the renderer `ShinySurfaces` ini). |

Key semantic distinctions to keep straight:
- **`Masked`** = palette index 0 is transparent (binary cut-out); **`Translucent`** (additive) masks
  *dark* (black → invisible); **`Modulated`** (2× multiply) treats **50% grey as neutral** — darker
  darkens the backdrop, lighter brightens it. Three different transparency models, not synonyms.
- **Shadow detail is a pair of FLAGS, not a number** — `PF_HighShadowDetail` / `PF_LowShadowDetail`
  control per-surface lightmap resolution; there is no numeric "lightmap resolution" field on a UE1
  surface.
- **`Fake Backdrop` always needs `Unlit`** on the same surface, or the sky draws lit/wrong.
- **`Mirror` is a surface flag, editor-invisible, and NOT a portal** — a common confusion.

---

## 2. Alignment & scrolling  🔬

- **Auto-align:** Floor/Ceiling alignment vs Wall / Wall-Panning alignment (project the texture onto the
  face by its dominant axis). uedctl: `brush poly align --floor|--wall|--ring` (`--ring` wraps a texture
  around a cylinder's side faces).
- **Manual:** Pan / Rotate / Scale. uedctl: `brush poly set - --pan-to U,V` (absolute) / `--pan-by dU,dV`
  (relative). Console: `POLY TEXPAN`, `POLY TEXSCALE`, `POLY TEXALIGN`, `POLY TEXINFO`.
- **Re-align after CSG changes** — a rebuild can disturb texturing; re-run alignment after geometry
  edits.

### 2.1 Scrolling surfaces — flag on the face, SPEED on the zone  🔬

A scrolling surface is **not** configured with a per-surface speed. Instead:
1. Set the poly flag `PF_AutoUPan` (0x200) and/or `PF_AutoVPan` (0x400) on the face — the flag means
   "this face scrolls," with **no speed of its own**.
2. The **speed lives on the `ZoneInfo` / `LevelInfo`** as `TexUPanSpeed` / `TexVPanSpeed`, **shared by
   every auto-pan face in that zone.**

This drives conveyors, flowing water, scrolling signs. Because the speed is zone-wide, group faces that
should scroll at the same rate into the same zone.

---

## 3. `MyLevel` — embedding assets in the map file  [ENGINE]

Importing a resource (texture/sound) into the pseudo-package **`MyLevel`** embeds it directly in the
`.dx`/`.unr` map file, making the map self-contained (no external package dependency).

- **A `MyLevel` resource is DISCARDED when the map is SAVED (or the editor is closed) UNLESS it is applied
  to a surface first** — a save serializes only reachable objects, so an unreferenced embed is dropped.
  Apply it to at least one poly before saving, or it silently vanishes. (The trigger is save/close, **not**
  a geometry rebuild.)
- **A level screenshot texture must be named exactly `ScreenShot`** (256×256, P8), **mipmaps off**. Set
  it plus `LevelInfo` Title/Author to finish a level (see [`README.md`](README.md) §13).
- **Open question for uedctl:** whether uedctl exposes a `MyLevel`-embed path or it stays editor-only is
  tracked as spec Q3 — treat `MyLevel` as an editor/engine mechanism until the `texture`/materialize
  verb surface confirms an embed path.

---

## 4. Detail, macro & environment mapping  🔬

- **`DetailTexture` is a Texture-CLASS property** — set once on the *base* texture, and it applies to
  **every surface** using that base texture (you do not set it per-surface). It modulates a fine texture
  in up close for near-field detail. **There is NO `DetailScale` in UE1** (that value-8 figure is UE2) —
  the detail tiling comes from the **detail texture's own import Scale** (~0.25). DX feeds these from
  `CoreTexDetail` (`DMetal_A`, `DScanline`).
- **`MacroTexture`** exists on the Texture class but is engine-commented **"not currently used"** in this
  build.
- **Environment mapping** = poly flag `PF_Environment` (world surfaces) or `bMeshEnviroMap` + `Skin`
  (meshes), **gated by the renderer `ShinySurfaces` ini setting**.
- **`MultiSkins[8]`** is an actor **mesh-skin** array, unrelated to BSP surface texturing (see
  [`actors-collision-pathing.md`](actors-collision-pathing.md) decorations).

---

## 5. Add Special presets  [ENGINE] 📖

*Add Special* (a GUI convenience that commits a builder brush with a preset flag+solidity combination):

| Preset | Is |
|---|---|
| **Transparent Window** | Translucent surface. |
| **Masked Decoration** | 2-sided + transparent + masked + **nonsolid** (foliage, grilles, fire sheets). |
| **Invisible Collision Hull** | Semisolid, all-invisible polys — a blocking volume (see [`actors-collision-pathing.md`](actors-collision-pathing.md) collision recipes). |
| **Zone Portal** | A nonsolid, **invisible**, 2-sided portal sheet (`portal`+`invisible`+`twosided`) — the portal plane itself doesn't render. (A *water* surface is the visible exception: a `portal`+`translucent` sheet.) See [`zones-performance.md`](./zones-performance.md). |
| **Water** | The translucent water-surface sheet for a `bWaterZone` (water recipe — [`zones-performance.md`](./zones-performance.md) §1.1). |
| **Semi-Solid Pillar** | A semisolid detail brush. |

uedctl reaches these via `brush build … --flag …` at build time (a sheet is NotSolid by default), so
most presets are a one-line pipe: e.g. `brush build sheet --width 256 --height 256 --flag portal --flag
translucent | actor add -` for the water surface.

---

## 6. The procedural `Fire.u` texture family  🔬 (internals — dev-only)

Deus Ex ships **animated fire and water surface textures** in a **separate `Fire.u` package** (NOT
`Engine.u`). For level authoring, the useful fact is that these appear in the Texture Browser and are
**applied like any other texture** to give animated fire/water surfaces. The painting internals below
are dev-only depth (the user subset drops them).

**Class tree** 🔬: `FractalTexture extends Texture`; `FireTexture` / `WaterTexture` / `IceTexture extends
FractalTexture`; `WaveTexture` / `WetTexture extends WaterTexture`. **`PaletteModifier` does NOT exist in
shipping DX** (it is an OldUnreal-227 addition).

### 6.1 `FireTexture` — `var(FirePaint)`  🔬

- `bRising` — a **two-algorithm switch** (there is **no** `FireType` field — a common misnomer).
- `byte RenderHeat` — overall intensity / "heat".
- `ESpark SparkType`, `DMode DrawMode`, `int SparksLimit`.
- Byte FX params: `FX_Size / FX_AuxSize / FX_Heat / FX_Area / FX_Frequency / FX_Phase / FX_HorizSpeed /
  FX_VertSpeed` — the speed/frequency ones are **signed, centred on 128** (128 = no movement).
- **`ESpark` (29 values)** 🔬: `SPARK_Burn, _Sparkle, _Pulse, _Signal, _Blaze, _OzHasSpoken, _Cone,
  _BlazeRight, _BlazeLeft, _Cylinder, _Cylinder3D, _Lissajous, _Jugglers, _Emit, _Fountain, _Flocks,
  _Eels, _Organic, _WanderOrganic, _RandomCloud, _CustomCloud, _LocalCloud, _Stars, _LineLightning,
  _RampLightning, _SphereLightning, _Wheel, _Gametes, _Sprinkler`.
- **`DMode`**: `DRAW_Normal, DRAW_Lathe, DRAW_Lathe_2, DRAW_Lathe_3, DRAW_Lathe_4` (first lathe value
  is `DRAW_Lathe`, no `_1` suffix).

### 6.2 `WaterTexture` — `var(WaterPaint)`  🔬

- `WDrop DropType`, `byte WaveAmp`, bump/phong bytes, `FX_*`.
- **`WDrop` (20 values)** 🔬: `DROP_FixedDepth, _PhaseSpot, _ShallowSpot, _HalfAmpl, _RandomMover,
  _FixedRandomSpot, _WhirlyThing, _BigWhirly, _HorizontalLine, _VerticalLine, _DiagonalLine1,
  _DiagonalLine2, _HorizontalOsc, _VerticalOsc, _DiagonalOsc1, _DiagonalOsc2, _RainDrops, _AreaClamp,
  _LeakyTap, _DrippyTap`.

### 6.3 `WetTexture` / `IceTexture`  🔬

Both distort a `SourceTexture` by the wave field. `IceTexture` adds `GlassTexture` + `PanningStyle`
(`SLIDE_Linear/Circular/Gestation/WavyX/WavyY`) + `TimeMethod` (`TIME_RealTimeScroll/FrameRateSync`).

### 6.4 Native defaults & painting  🔬

- **Numeric defaults are `native` C++** — the classes have empty script `defaultproperties`, so those
  specific values are **not recoverable offline** from the package (the one residual gap for uedctl's
  decode route; everything script-defaulted reads cleanly).
- **Painting is a Texture-Browser GUI task with no uedctl verb:** Texture Browser → New → set Class +
  Size (**locked at creation**) → set `FX_*` / `RenderHeat` / `WaveAmp` **before painting** → **left-drag
  paints, right-drag erases** (lightning is click-drag-release).

---

## 7. The Deus Ex `CoreTex*` catalog  [DX] 🔬

The **`CoreTex*` set is the reusable cross-level material palette** — **18 packages on disk** 🔬:
`CoreTexBrick, CoreTexCeramic, CoreTexConcrete, CoreTexDetail, CoreTexEarth, CoreTexFoliage,
CoreTexGlass, CoreTexMetal, CoreTexMisc, CoreTexPaper, CoreTexSky, CoreTexStone, CoreTexStucco,
CoreTexTextile, CoreTexTiles, CoreTexWallObj, CoreTexWater, CoreTexWood`.

- **Level-named packages are one-offs** — `UNATCO`, `Paris`, `NewYorkCity`, the `HK_*` family (there is
  **no** single "HongKong" package). Reach for `CoreTex*` for reusable material; use level-named packages
  only for their specific level.
- **Naming:** `<condition><descriptor>_<variant>` with **condition prefixes** `Clen` (clean) / `Drty`
  (dirty) / `Damg` (damaged) / `Corg` (corroded) / `Olde` (old) / `Fros` (frosted) — e.g.
  `ClenGrayMetal_A`, `DrtyGrayMetal_A`. The `_A/_B/_C` suffix is the variant.
- `CoreTexMetal` is the **largest structural set**; `CoreTexDetail` (`DMetal_A`, `DScanline`) feeds other
  packages' `DetailTexture` slots (§4).

### 7.1 The reserved `Ladder` texture group — CRITICAL  📖 (DX SDK / community)

In the Texture Browser you pick a package, then a **`Group`** to narrow the list. `Group=` is
**browser-convenience only** for every group **EXCEPT one**:

> **A texture whose Group is `Ladder` makes the surface a climbable LADDER in-game.** This is a native
> (C++) `case 'Ladder':` group check in the DeusEx player movement — a **texture-driven** ladder.
> 📖 (DX SDK + community-documented; the `Ladder` token is absent from `DeusEx.u`'s script name table, so
> the switch is in native engine code, not script we can probe offline.)

- **Ladders are NOT a `bIsLadder` actor or flag** — there is no ladder actor and no ladder zone in DX.
  You make a wall climbable by texturing it with a `Ladder`-group texture. (This corrects an earlier
  tentative `bIsLadder`/`LadderZone` assumption wherever it appears.)
- Built-in ladder textures: `ladder_a`, `LadrBrwnMetal` (in `CoreTexMetal`).

*(The other three unrelated "group" senses — the `Group=` **actor** property, texture
`Package.Group.Name`, and the `var(Group)` property category — are all distinct from the reserved
`Ladder` texture group and from uedctl's actor `folder`; see [`README.md`](README.md)
terminology.)*

---

## 8. `ScriptedTexture` — a draw-on surface, NOT a camera feed  🔬

Worth pinning because it is widely misunderstood: `ScriptedTexture` (chain `Bitmap → Texture →
ScriptedTexture`) is a **draw-on** surface. Each frame it resets to `SourceTexture`, then calls
`NotifyActor.RenderTexture()` where script draws `DrawTile` / `DrawText` / `DrawColoredText` /
`ReplaceTexture`. Renderer-dependent — renders under D3D; software/other renderers vary (a runtime concern, not
offline-probed 📖). Used for scoreboards, counters, tombstones.

- **Camera-view-to-surface (`DrawPortal`) is a UE1 `Canvas` native that DX never calls** — do NOT attribute DX monitors to it (it exists in `Engine.u`, but `DeusEx.u` has 0 refs).
- **DX security-camera monitors do NOT use `ScriptedTexture`** 🔬 (no `ScriptedTexture` ref in
  `DeusEx.u`). The camera feed is a live 3D render composited into the **hackable-computer UI**, not a
  world-mounted monitor surface (see the security-camera→console recipe in
  [`README.md`](README.md) §10.2).

---

## 9. Quick verb reference (uedctl)  ✅

| Task | Verb pipeline |
|---|---|
| Texture faces | `brush poly find Wall1 \| brush poly set - --texture CoreTexMetal.ClenGrayMetal_A` |
| Add/remove a flag | `brush poly set Wall1:all --add-flag Masked --remove-flag Unlit` |
| Align | `brush poly align Wall1:all --wall` (or `--floor` / `--ring`) |
| Pan | `brush poly set Floor1:all --pan-to 64,0` (or `--pan-by 8,0`) |
| Inspect | `brush poly list Wall1` |
| Water surface | `brush build sheet --width W --height H --flag portal --flag translucent \| actor add -` (recipe: [`zones-performance.md`](./zones-performance.md) §1.1) |
