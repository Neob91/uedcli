# Textures & surfaces  [ENGINE]

Texturing in UE1 is **per-surface**: you pick a texture from a package for a face, set its alignment,
and set flags that change how it *renders*. Flags never change geometry — only appearance and a couple
of render behaviours.

## The `brush poly` verbs

uedctl edits surfaces model-side. The pattern is **find faces → set them**:

```
brush poly find Wall1                               # print ALL faces of brush Wall1 (positional name)
brush poly find Wall1 --facing +Z                   # or filter by facing: +Z floor / -Z ceiling / +X,±Y wall
brush poly find Wall1 | brush poly set - --texture CoreTexMetal.ClenGrayMetal_A
brush poly find Wall1 --facing +X | brush poly set - --add-flag Masked --remove-flag Unlit
brush poly find Sign | brush poly set - --pan-by 0,32                  # nudge alignment
brush poly find Floor1 --facing +Z | brush poly align - --floor        # auto-align (the `-` reads the piped faces)
```

- `brush poly find <BrushName>` is a query verb — it prints matching `BRUSH:idx` faces for another verb
  to consume. The brush Name is **positional**; narrow the set with `--facing +X|-X|+Y|-Y|+Z|-Z|slant`
  (a floor is `--facing +Z`, a ceiling `--facing -Z`, a wall `--facing +X` or `±Y`), `--item NAME`, or
  `--texture REF`.
- `brush poly set` applies texture / flag / pan changes to the faces on stdin.
- `brush poly align --wall|--floor|--ring` auto-aligns (walls, floors/ceilings, or around a cylinder).

## Surface flags

The flags you actually reach for (editor: F5 Surface Properties → Flags):

| Flag              | Effect |
| ----------------- | --- |
| **Unlit**         | fullbright — ignores the lightmap. For skyboxes, screens, self-lit panels |
| **Masked**        | palette **index 0** renders transparent (grates, chain-link, ladders). Renders last — small framerate cost |
| **Translucent**   | additive blend — masks **DARK** colours (glass, energy, decals) |
| **Modulated**     | multiply (2×) blend — **50% grey is neutral**; darker darkens, lighter brightens (grime, decals, shadow overlays) |
| **Fake Backdrop** | draws the **skybox** through this face — **needs an `Unlit` companion** on the same face |
| **2-Sided**       | renders both faces (banners, chain-link). uedctl's `brush build sheet` is 2-sided by default, so you don't add this to a plain sheet |
| **Mirror**        | reflective; editor-invisible; **not** a portal |
| **Special Lit**   | lit only by lights with `bSpecialLit` |

> **Bright Corners** (and **Small/Big Wavy**, **High/Low Shadow Detail**) exist in the editor's F5 Surface
> Properties GUI but are **not** values uedctl's `--add-flag` / `--remove-flag` accept. The 16 flags uedctl
> can set by name are: `invisible`,
> `masked`, `translucent`, `notsolid`, `environment`, `semisolid`, `modulated`, `fakebackdrop`,
> `twosided`, `autoupan`, `autovpan`, `nosmooth`, `speciallit`, `unlit`, `portal`, `mirror`.

Combinations matter: `Fake Backdrop` **+** `Unlit` shows sky; `Mirror` **+** `Unlit`; a glass sheet is
`Translucent` **+** `2-Sided`.

## Alignment & scrolling

- **Align** with `brush poly align` (or the editor's Floor/Ceiling vs Wall auto-align). After any CSG
  change a rebuild can disturb texturing — **re-align after rebuilding**.
- **Pan / scale** with `--pan-to X,Y`, `--pan-by dX,dY`.
- **Scrolling surfaces** (conveyors, flowing water, scrolling signs): set the auto-pan flags on the face
  (`PF_AutoUPan` / `PF_AutoVPan` — the flag just means "this scrolls", with no speed), and set the
  **speed on the zone's `ZoneInfo`** (`TexUPanSpeed` / `TexVPanSpeed`), shared by every auto-pan face in
  that zone. ✅

## MyLevel — embedding assets in the map

`MyLevel` is a pseudo-package: import a texture (or sound) into it and it's embedded in the map file,
making the level self-contained.

- **A texture imported into MyLevel is discarded when the map is *saved* (or the editor is closed) unless
  it's applied to a surface first** — a save serializes only referenced objects, so apply it before
  saving or it vanishes. (The trigger is save/close, not a geometry rebuild.)
- A level **screenshot** texture must be named exactly `ScreenShot`, with **mipmaps off**.

## Skybox surface flags

The player-facing side of a skybox: any wall/ceiling that should *show the sky* is flagged **`Fake
Backdrop` + `Unlit`**. The actual sky is a separate sealed room with a `SkyZoneInfo` — see the full
[recipes/skybox.md](recipes/skybox.md).

## Add Special presets

The editor's *Add Special Brush* dropdown bundles common flag sets. Knowing the recipe behind each lets
you reproduce it with `brush build` + `brush poly set`:

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
