# Textures & surfaces  [ENGINE]

Texturing in UE1 is per-surface: you pick a texture from a package for a face, set its alignment,
and set flags that change how it renders. Flags never change geometry — only appearance and a couple
of render behaviours.

## The `brush poly` verbs

uedcli edits surfaces model-side. The pattern is find faces, then set them:

```
brush poly find Wall1                               # print ALL faces of brush Wall1 (positional name)
brush poly find Wall1 --facing +Z                   # or filter by facing: +Z floor / -Z ceiling / +X,±Y wall
brush poly find Wall1 | brush poly set - --texture CoreTexMetal.ClenGrayMetal_A
brush poly find Wall1 --facing +X | brush poly set - --add-flag Masked --remove-flag Unlit
brush poly find Sign | brush poly pan - --by 0,32                      # nudge alignment (whole texels)
brush poly find Sign | brush poly rotate - --by 16384                   # turn the texture a quarter turn
brush poly find Sign | brush poly scale - --by 2,2                      # make the texture look twice as big
brush poly find Floor1 --facing +Z | brush poly align - --floor        # auto-align (the `-` reads the piped faces)
```

- `brush poly find <BrushName>` is a query verb — it prints matching `BRUSH:idx` faces for another verb
  to consume. The brush Name is positional; narrow the set with `--facing +X|-X|+Y|-Y|+Z|-Z|slant`
  (a floor is `--facing +Z`, a ceiling `--facing -Z`, a wall `--facing +X` or `±Y`), `--item NAME`, or
  `--texture REF`.
- `brush poly set` assigns a face's stored attributes — its texture and surface flags.
- `brush poly pan|rotate|scale` transform the texture frame on the faces on stdin: where the pattern
  sits, which way up it runs, how big it is.
- All four of `set|pan|rotate|scale` take `BRUSH:SELECTOR` (or `-`) only — unlike `align`, a bare
  brush name is not accepted, so "every face of this brush" has to be typed `Wall1:all`.
- `brush poly align --wall|--floor|--ring` auto-aligns (walls, floors/ceilings, or around a cylinder).

## Surface flags

The flags you reach for (editor: F5 Surface Properties → Flags):

| Flag              | Effect |
| ----------------- | --- |
| **Unlit**         | fullbright — ignores the lightmap. For skyboxes, screens, self-lit panels |
| **Masked**        | palette index 0 renders transparent (grates, chain-link, ladders). Renders last — small framerate cost |
| **Translucent**   | additive blend — masks dark colours (glass, energy, decals) |
| **Modulated**     | multiply (2×) blend — 50% grey is neutral; darker darkens, lighter brightens (grime, decals, shadow overlays) |
| **Fake Backdrop** | draws the skybox through this face — needs an `Unlit` companion on the same face |
| **2-Sided**       | renders both faces (banners, chain-link). uedcli's `brush build sheet` is 2-sided by default, so you don't add this to a plain sheet |
| **Mirror**        | reflective; editor-invisible; not a portal |
| **Special Lit**   | lit only by lights with `bSpecialLit` |

> Bright Corners (and Small/Big Wavy, High/Low Shadow Detail) exist in the editor's F5 Surface
> Properties GUI but are not values uedcli's `--add-flag` / `--remove-flag` accept. The 16 flags uedcli
> can set by name are: `invisible`,
> `masked`, `translucent`, `notsolid`, `environment`, `semisolid`, `modulated`, `fakebackdrop`,
> `twosided`, `autoupan`, `autovpan`, `nosmooth`, `speciallit`, `unlit`, `portal`, `mirror`.

Combinations: `Fake Backdrop` + `Unlit` shows sky; `Mirror` + `Unlit`; a glass sheet is
`Translucent` + `2-Sided`.

## Alignment & scrolling

- Align with `brush poly align`. After any CSG change a rebuild can disturb texturing —
  re-align after rebuilding. ⚠ `brush poly align` is uedcli's own alignment, not a copy of
  the editor's Floor / Wall-Direction auto-align: measured against UnrealEd 2026-07-26, the two
  choose different in-plane texture directions and pin the pattern's phase to different points, so
  the same face aligned each way does not come out looking the same. Use one or the other on a given
  surface, not both.
- Pan with `brush poly pan --to U,V` (absolute) or `--by dU,dV` (relative), in whole texels.
  Pan after aligning, never before — every align mode stamps `Pan` on the faces it touches, so a
  pan applied first is discarded. And pan the whole of an aligned run or none of it: panning a
  subset shifts those faces relative to their neighbours and breaks the seams (easy to do by
  accident, since `brush poly find` filters).
- Rotate with `brush poly rotate --by UU`, in unreal rotation units (16384 = a quarter turn).
  The turn follows the face's visible surface normal, so it looks the same from where you stand
  whether the face is the outside of an added pillar or the inside of a subtracted room — uedcli
  flips the sign on a subtract for you. ⚠ It still comes out backwards on a mirrored
  brush — one whose scale has an odd number of negative components, e.g. `MainScale=(-1,1,1)` —
  because the engine draws its faces with reversed winding, so the visible normal is the opposite of
  the one uedcli computes; negate the angle there. An even number of negative components
  (`(-1,-1,1)`) is a 180° rotation rather than a mirror and is unaffected. (Geometric argument from
  the determinant's sign, not measured against the editor.) The verb needs the brush's `CsgOper` to be `CSG_Add` or
  `CSG_Subtract` (absent counts as `CSG_Add`); any other value exits 2 naming it — a brush with
  no inside and outside gives the turn no direction to follow, so uedcli refuses rather than guessing
  one.
- Scale with `brush poly scale --by FU,FV`, named for what you see: `--by 2,2` makes the texture
  look twice as big. Scale before `align --ring`, never after — a ring wrap computes its seam
  phases for the density it saw.
- ⚠ `rotate` and `scale` give no continuity across faces: each pivots or grows about its own
  centre, so applying either across an aligned set breaks the seams. They are for a one-off face —
  a sign, a monitor, a light panel.
- Scrolling surfaces (conveyors, flowing water, scrolling signs): set the auto-pan flags on the face
  (`PF_AutoUPan` / `PF_AutoVPan` — the flag just means "this scrolls", with no speed), and set the
  speed on the zone's `ZoneInfo` (`TexUPanSpeed` / `TexVPanSpeed`), shared by every auto-pan face in
  that zone. ✅

## MyLevel — embedding assets in the map

`MyLevel` is a pseudo-package: import a texture (or sound) into it and it's embedded in the map file,
making the level self-contained.

- A texture imported into MyLevel is discarded when the map is saved (or the editor is closed) unless
  it's applied to a surface first — a save serializes only referenced objects, so apply it before
  saving or it vanishes. (The trigger is save/close, not a geometry rebuild.)
- A level screenshot texture must be named exactly `ScreenShot`, with mipmaps off.

## Skybox surface flags

The player-facing side of a skybox: any wall/ceiling that should show the sky is flagged `Fake
Backdrop` + `Unlit`. The actual sky is a separate sealed room with a `SkyZoneInfo` — see
[recipes/skybox.md](recipes/skybox.md).

## Add Special presets

The editor's Add Special Brush dropdown bundles common flag sets. Each recipe reproduces with
`brush build` + `brush poly set`:

| Preset                       | Is really |
| ---------------------------- | --- |
| **Transparent Window**       | a translucent sheet (add 2-Sided for glass) |
| **Masked Decoration**        | 2-sided + masked + nonsolid (crossed-sheet foliage, fire, grilles) |
| **Invisible Collision Hull** | a semisolid with all faces invisible — see [actors.md](actors.md) |
| **Zone Portal**              | a nonsolid, invisible, 2-sided portal sheet (the portal plane doesn't render) — see [zones-and-performance.md](zones-and-performance.md) |
| **Water**                    | a nonsolid translucent portal sheet — see [recipes/water.md](recipes/water.md) |
| **Semi-Solid Pillar**        | a semisolid brush |

## Related

- [recipes/glass.md](recipes/glass.md), [recipes/skybox.md](recipes/skybox.md),
  [recipes/water.md](recipes/water.md) — surface flags in full context.
- [lighting.md](lighting.md) — how `Unlit` / `Special Lit` interact with the lightmap.
