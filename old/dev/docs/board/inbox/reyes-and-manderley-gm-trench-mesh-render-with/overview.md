+++
priority = "p3"
kind = "investigate"
summary = "Reyes and Manderley (GM_Trench mesh) render with visible glasses, should be invisible placeholder"
+++

# Reyes and Manderley (GM_Trench mesh) render with visible glasses, should be invisible placeholder

Owner report (2026-09-16, live-testing the GUI): Jaime Reyes and Joseph Manderley show glasses in
BOTH selected and unselected states -- consistent between the two, so not a regression from the
same-day selection-highlight fixes (`GUI-PARITY.md`). Other NPCs render correctly (no visible
glasses).

## Confirmed by data (not a guess)

`uedcli/uprops/values.py`'s `resolve_class_defaults` against `DeusEx.JaimeReyes` /
`DeusEx.JosephManderley` (`DeusEx.u`):

```
JaimeReyes:      multiskins[6] = DeusExItems.Skins.GrayMaskTex   (frame)
                 multiskins[7] = DeusExItems.Skins.BlackMaskTex  (lens)
JosephManderley: multiskins[6] = DeusExItems.Skins.GrayMaskTex   (frame)
                 multiskins[7] = DeusExItems.Skins.BlackMaskTex  (lens)
```

Both use the EXACT SAME "no glasses" placeholder textures as every generic NPC (the "sunglasses"
bug fix, `sceneResources.ts`'s `resolveMaterialState` doc comment, 2026-09-15) -- under real UE1
blend formulas these are meant to be invisible (`GrayMaskTex` under 2x-multiply -> neutral,
`BlackMaskTex` under additive -> `dest+0=dest`). There is nothing in their class defaults that
makes these two characters special-cased to show real glasses. If they render visibly, it is a
bug, not intentional content -- but WHICH bug is not yet confirmed.

## A plausible, NOT confirmed, connection

`dev/docs/board/done/resolve-skins-keys-by-material-ordinal-not/overview.md`: a real, already-fixed
bug specifically on `DeusExCharacters.GM_Trench` (Manderley's own mesh) -- materials 3-6 of 7 had
`TextureIndex != their own ordinal`, so `resolve_skins` gave each the WRONG neighboring material's
skin texture until re-keyed by `UMesh`'s own texture index. That fix covers which TEXTURE lands on
which material slot. It's plausible (not verified here) that the same mesh's BLEND-MODE/PolyFlags
resolution (masked/translucent/modulated classification per material) has an analogous
ordinal-vs-texture-index mismatch that was never covered by that fix -- which would explain the
glasses placeholder landing on the right slot with texture-correct content but the WRONG blend
mode, rendering opaque instead of blending to invisible. NOT confirmed -- didn't have live
render access to this exact character to check, and didn't want to guess-fix per the owner's
explicit "don't fix unless certain" instruction.

## Next step

Live-inspect (or decode) `GM_Trench`/`GM_Trench_F`'s own material list for slots 6/7 (or wherever
`MultiSkins[6]`/`[7]` actually lands post-`resolve_skins`'s texture-index re-keying) -- confirm
whether the blend/PolyFlags resolution for those materials is keyed the same way the skins fix
re-keyed texture assignment, or still by raw material ordinal.
