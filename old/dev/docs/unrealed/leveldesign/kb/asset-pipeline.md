# Custom-content / asset pipeline  [DX]

Getting custom content into Deus Ex — packages and `ucc make`, meshes,
textures, sounds, music, custom pickups/augs, the credits screen. Reference for
when a level needs a bespoke mesh, texture, sound or item; authoring geometry
through verbs touches little of this.

Everything here is `[DX]` (the `ucc`/package/`#exec` mechanics are UE1-generic
but the class names, flag values and constraints are the DX build). Confidence
is mostly 📖 (SDK manual / tutorial corpus) with ⟨bin⟩ where verified against
the shipped packages this session.

> Siblings. [`dx-classes.md`](dx-classes.md) (`DeusExPickup`, `DeusExDecoration`,
> the texture-Group `Ladder` rule) · [`dx-conversations-computers.md`](dx-conversations-computers.md)
> (text/image packages for computers & datacubes) · [`editor-ui.md`](editor-ui.md)
> (the browsers you import through). Full compiled reference:
> [`README.md`](README.md); the DX texture catalog is in [`textures.md`](textures.md).

---

## 1. Packages & `ucc make`  [DX] 📖

- A code package lives at `\DeusEx\<Pkg>\Classes` (mesh/model data under
  `\<Pkg>\Models`). It needs ≥1 `.uc` class file.
- Declare it for the compiler by adding `EditPackages=<Pkg>` to the ini.
- Compile with `ucc make`. Delete the old `.u` first — `ucc make` will not
  rebuild over an existing compiled package.
- Post-Mar-2001 SDK: build your text into your own package instead of
  overwriting stock `DeusExText.u`.

The `#exec` directives below go inside a `.uc` class's header and run at compile
time (`ucc make`) to import external assets into the package.

---

## 2. Meshes  [DX] 📖 ⟨bin: MESHMAP scales⟩

DX characters/props are vertex meshes (not skeletal).

- Maximum 8 surfaces (material slots) per mesh. ⟨bin⟩ Skins map to
  `MultiSkins(0..7)`.
- Data files are `_a.3d` / `_d.3d` pairs (anim + data).
- Import directives:
  - `#exec MESH IMPORT` / `#exec MESH ORIGIN` / `#exec MESH SEQUENCE`
  - `#exec MESHMAP NEW` / `#exec MESHMAP SCALE` / `#exec MESHMAP SETTEXTURE`
  - `#exec MESH LODPARAMS STRENGTH` — LOD aggressiveness (default 1.0; DX
    characters use 0.5).
- `MESHMAP SCALE` depends on the source format: `1` for MilkShape-exported
  meshes, or `0.00390625` (= 1/256) for the native DX mesh format.
- Rotations are in byte-angles: 64 = 90°, 128 = 180°, 256 = 360° (the engine
  rotator convention, one byte per 1/256 turn).
- DX ships 17 generic character meshes / 68 total; each killable character has a
  paired `<Name>Carcass` mesh for its death body (referenced via the pawn's
  `CarcassType` — see [`dx-npcs.md`](dx-npcs.md) §4).

External tool MeshMaker converts a brush/prefab `.t3d` into a mesh `Decoration`
(cheaper many-face render, no BSP holes) at the cost of ≤8 textures, no tiling,
cylinder-only collision. See [`README.md`](README.md).

---

## 3. Textures  [DX] 📖 ⟨bin: flag bits⟩

- Power-of-two dimensions, ≤ 256 each axis. 512+ won't render on UE1.
- Source is 8-bit PCX or BMP (palettized).
- Import with `#exec TEXTURE IMPORT … FLAGS=<bitmask>`. Sum the bits you want
  ⟨bin⟩:

  | Bit | Value | Meaning |
  |---|---|---|
  | Masked | **2** | palette index 0 = transparent |
  | Transparent | **4** | translucent |
  | Environment | **16** | environment-mapped |
  | Modulated | **64** | modulated blend |
  | FakeBackdrop | **128** | draws the skybox |
  | TwoSided | **256** | two-sided |
  | AutoUPan | **512** | auto-scroll U |
  | AutoVPan | **1024** | auto-scroll V |
  | NoSmooth | **2048** | no bilinear smoothing |
  | BigWavy | **4096** (0x1000) | large wavy distortion |
  | SmallWavy | **8192** (0x2000) | small wavy distortion |

- Masked transparency: the colour at palette slot 0 becomes transparent.
- Animated textures chain via numbered names + `AnimNext` (and `MinFrameRate` /
  `MaxFrameRate`), so `flame1 → flame2 → …` loops.
- Detail textures: `Texture → DetailTexture` points at a fine texture
  (`CoreTexDetail` supplies `DMetal_A`, `DScanline`) that modulates up close.
  It is a Texture-class property, shared by every surface using the base
  texture. No `DetailScale` in UE1 — tiling comes from the detail texture's own
  import Scale (~0.25). ⟨bin⟩

Level screenshot / `MyLevel`. A texture imported into the pseudo-package
`MyLevel` embeds in the map file; it is discarded on rebuild unless applied to a
surface first, and a level-screenshot texture must be named exactly
`ScreenShot`, mipmaps off. See [`./textures.md`](./textures.md).

The reusable in-game material palette is the `CoreTex*` set (18 packages),
catalogued in [`textures.md`](textures.md). The reserved texture Group `Ladder`
makes a surface a climbable ladder ⟨bin⟩
([`dx-classes.md`](dx-classes.md) §1).

---

## 4. Sounds  [DX] 📖

- Import with `#exec AUDIO IMPORT` into a `.uax` package.
- Format: 16-bit / 22 kHz / mono WAV.
- Play in-world via `AmbientSound` KeyPoints, decoration `PushSound`s, etc.

---

## 5. Music  [DX] 📖

- Music is tracker modules in a `.umx` package.
- DX uses 6 dynamic patterns per song, one per game state:
  Ambient1 / Dying / Ambient2 / Combat / Conversation / Outro — the engine
  transitions between them by game state.
- A pattern of 256 lines freezes UnrealEd — keep it ≤ 255. ≤ 32 channels.
- Assign the song via F6 → Audio → Song.
- Mid-level music change = a `MusicEvent` actor: `Song`, `SongSection`,
  `Transition` (= `MTRAN_*`), `bSilence`; `CdTrack` 255 = ignore.

```
actor build Engine.MusicEvent --prop Song=… --prop Transition=MTRAN_Fade \
  --prop Tag=combat_start --at 0,0,0 | actor add -
```

---

## 6. Custom pickups & augmentations  [DX] 📖

- Pickups: subclass `DeusExPickup` — fields `ItemName`, `Description`,
  `Mesh`, `Icon`, and the inventory-slot dimensions. Compile with `ucc make`,
  then place the class like any actor.
- Augmentations: define via `AugmentationCannister → AddAugs`, a 2-element array
  of augmentation names (`var() travel Name AddAugs[2]`, not class references);
  the canister offers those two and the player installs one. Standard vanilla
  pairs (one per slot): Cloak / RadarTrans, Speed / Stealth, Muscle / Combat,
  EMP / Ballistic, Healing / Shield, … Set each element with the dot index
  (`KEY.N`; the CLI rejects the T3D `KEY(N)` form):

```
actor build DeusEx.AugmentationCannister --prop AddAugs.0=AugSpeed --prop AddAugs.1=AugStealth \
  --at 128,128,16 | actor add -
```

---

## 7. Credits screen  [DX] 📖

- Subclass `CreditsWindow` with `CreditsBannerTextures`, `TeamPhotoTextures`,
  `ScrollMusicString`.
- The credits banner is 505×75 px.

---

## Multiplayer note  [DX] 📖

Registering an MP map, `PlayerStart` limits and MP-weapon physics live in
[`README.md`](README.md) (mostly N/A for a single-player mod). UT gametype
content (DM/CTF/DOM/AS) does not transfer to DX.
