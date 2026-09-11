+++
priority = "p3"
kind = "unknown"
summary = "`level photo --lit` — the scoped fast-follow (native-preview spec §8, decision 2026-07-16 12:13): consume the N-4 `bake_lighting` arrays in `render_frame` (raw dot-product lumel frame, NOT the panned texel frame — spec §8 pins the math)"
+++

# `level photo --lit` — the scoped fast-follow (native-preview spec §8, decision 2026-07-16 12:13): consume the N-4 `bake_lighting` arrays in `render_frame` (raw dot-product lumel frame, NOT the panned texel frame — spec §8 pins the math)

p3. v1 shipped flat-shaded
2026-07-16; `render_frame`'s FFI grows optional lightmap arrays.

## 2026-09-11 — the spec §8 referenced above is gone

Investigated this alongside `bake-lighting-into-level-photo-native` (its overview has the full
findings). The "native-preview spec §8" cited here — which would have pinned the exact math for
consuming `bake_lighting`'s arrays (the "raw dot-product lumel frame" decision) — no longer exists as
a file; specs are ephemeral and commit `9c0f7874` moved/removed the standalone doc. No surviving copy
of its content was found. So the decision this item's summary refers to needs to be re-made, not
looked up, before this can be built. See `bake-lighting-into-level-photo-native/overview.md` for why
this is bigger than a wire-up (bake output is a geometric shadow mask, not a lit color — no light
brightness/hue/color reading exists anywhere in uedcli).
