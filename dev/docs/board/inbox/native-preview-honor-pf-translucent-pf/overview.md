+++
priority = "p2"
kind = "implement"
summary = "native preview: honor PF_Translucent / PF_Modulated (blended transparency)"
+++

# native preview: honor `PF_Translucent` / `PF_Modulated`

`level preview --native` renders **translucent** and **modulated** surfaces (glass, water sheets,
additive glows, screen overlays) as fully OPAQUE — a draft-tier limitation. `PF_Masked` (the
alpha-TEST cutout — grates/fences/foliage) is handled separately (its own change); this item is the
harder, BLENDED case.

## Why it's not a quick fix
True translucency/modulation needs real compositing against the framebuffer, which forces a
back-to-front pass the current single-pass z-buffer rasterizer (`uedcli-native/src/render.rs`) does
not do:
- draw OPAQUE faces first (unchanged z-buffer),
- then draw translucent/modulated faces **sorted back-to-front** (painter's), z-TESTED but NOT
  z-written, blended per mode:
  - `PF_Translucent` — UE1's screen-door/additive-ish blend,
  - `PF_Modulated` — multiply (glass darkening / decals).
Order-dependent transparency + the two blend modes; per-triangle sort or a BSP-order walk.

## What's already in place
- Per-poly `PolyFlags` reach the rasterizer (`lib.rs` sets `p.poly_flags` per face, incl.
  `PF_Translucent`/`PF_Modulated`).
- Texture RGB is decoded and plumbed.
What's needed: the sorted second pass + the blend-mode math (and the exact UE1 blend coefficients —
verify against the engine, `dev/docs/unrealed/`).

## Scope note
Draft-tier fidelity, not editor parity. Related: the `PF_Masked` cutout change (alpha-test, shipped
separately). Surfaced 2026-08-24 from a retail `--native` render where glass/water read opaque.
