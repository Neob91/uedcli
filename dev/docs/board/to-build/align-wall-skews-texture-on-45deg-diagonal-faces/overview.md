+++
priority = "p1"
kind = "debug"
summary = "align wall on a 45deg diagonal wall face yields a skewed, non-square texture frame"
+++

# align wall skews the texture on 45° diagonal wall faces

On an **axis-aligned** wall/ramp face, `brush poly align wall` + `brush poly scale`
produce a clean, square texture frame. On a **45° diagonal** wall face they do not:
the resulting TextureU/TextureV are not orthonormal-to-panel, so the texture tiles
skewed and the artist has to fix every diagonal face by hand.

Found while building the 19_Multiport cove lights (semisolid right-triangle prisms on
diagonal corridor walls). `poly scale`/`poly rotate` themselves are **not** broken — an
earlier belief that they no-op on angled faces did not reproduce; see repro.

## Repro (level 19_Multiport, dx_scratch project)

`poly scale` works on an angled face (2× exactly):
```
diagonal ramp face BEFORE: U +0.265,-0.735,-0.353
brush poly scale <ramp> --by 0.5,0.5
diagonal ramp face AFTER:  U +0.529,-1.471,-0.706   (== 2× — verb is fine)
```

`align wall` + `scale 0.5` — axis vs diagonal ramp face of the SAME fixture family:
```
AXIS ramp   (Cove334):   U +0,-2,0                V +1,0,-1                -> |U|=2    |V|=1.414  square
DIAGONAL    (CoveDIAG*): U +0.529,-1.471,-0.706   V -0.706,-0.706,-1.059   -> |U|=1.71 |V|=1.46   skewed
```
The diagonal U/V are neither equal-length nor aligned to the face's run/rise, so the
panel renders rotated/sheared.

## Expected

`align wall` on any planar wall face (including a 45° diagonal) should set U along the
face's horizontal run and V up its slope, at matching texel scale — the same square
frame it gives axis faces — so `scale` then just changes tiles/uu uniformly.

## Notes
- Faces are correct geometrically (grid-8, `contains`); this is texture-frame only.
- Workaround in use: artist aligns the diagonal ramp faces manually.
