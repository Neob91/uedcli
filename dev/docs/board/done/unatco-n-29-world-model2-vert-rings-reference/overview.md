+++
priority = "p2"
kind = "debug"
summary = "DONE — UNATCO N=29's world Model2 divergence was one surf's Texture ref, not the vertex rings: an untextured poly shipped `brush_marshal`'s per-brush texture dedup ordinal as an object ref. Byte-exact, no mask."
+++

# UNATCO N=29 world-`Model2` — the untextured surf's `Texture` ref

Fixed 2026-09-06.

**The vertex-ring framing was wrong.** All 91 live node rings were coordinate-identical in both
builds; the 391 differing `FVert`s were all ORPHAN slots (in no live node ring), which the gate
already excludes. `harness/ring_diff.py` (added with this fix) compares rings by resolved
coordinate rather than by pool index, so that confusion is one command to rule out.

The single failing gate token was `model model2` surf 86's `Texture`: native `polys@model brush`,
UED22 `None`. `brush_marshal` gives each of a brush's polys a per-brush texture dedup ordinal (0, 1,
2 … in first-appearance order) so the Rust core can answer "same texture?" in
`bsp_validate_brush_links`; the core copies it into `FBspSurf.Texture`, where the editor holds a
`UTexture*`. `unbuilt._patch_native_surf_refs` only OVERWROTE that slot when the source poly named a
texture, so `Brush516`'s poly 2 — no `Texture=` at all — shipped its ordinal `2` as an object ref,
which resolved to the builder brush's `Polys`. Latent since the ordinal was introduced: it is only
visible when a brush's untextured face is not its first face.

The patch now ASSIGNS `texture_ref` for every surf (`0` = None unless the poly names a texture).
Pinned by `uedcli/tests/test_native_surf_texture_ref.py`. Follow-up (the source-level fix):
`native-csg-core-stores-a-texture-dedup-ordinal`.

UNATCO gates byte-exact at N=29 with no new mask. Re-verified: UNATCO 1..29, WanChai 1..44, NYC_Bar
1..58, Island 1..9, OceanLab 1..45 — every level's ceiling unchanged.
