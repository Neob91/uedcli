+++
priority = "p2"
kind = "implement"
summary = "Unify the logic behind level preview --native and actor preview"
+++

# Unify the logic behind level preview --native and actor preview

Two separate renderers draw the same brush geometry today:

- `actor preview` → `uedcli/preview.py`: pure-Python, ORTHOGRAPHIC (top/front/side/iso). Solves and
  draws the brush polys itself (`_scene_geometry` / `_solved_scene`), textures via
  `texframe.world_uv_frame`.
- `level preview --native` → `uedcli/preview_native.py`: the Rust core — `uedcli_native.build_geometry`
  (CSG) + `uedcli_native.render_frame` (PERSPECTIVE software rasterizer), textures via `utexture` +
  `texframe`.

They share only `texframe` (UV framing) and `preview_shots` (pose). The CSG solve, texture paint,
backface cull, and the scale/sheer handling are each implemented twice. The scale gate is the sharpest
duplication: both reject non-identity `MainScale`/`PostScale`/`SheerRate`, independently and with
different messages — `preview.py` ("the UV frame uses rotation only, so the texture would not follow
the transformed geometry") vs `preview_native._reject_scaled` (the Rust CSG core errors on scale). So
when scale support lands it has to be built twice, and the two tiers can already diverge on the same
level.

Proposal: one geometry/CSG/texture pipeline feeding two projection front-ends (orthographic +
perspective), with a single scale/sheer policy and one texture-paint path. Benefits: consistent output
across tiers, one place to add scale support and fix CSG, less drift.

Surfaced 2026-08-05 rendering OG Deus Ex levels: both tiers refused the maps' scaled brushes (mirror
`X=-1`, pervasive), each for its own reason, and the offline textured render was only reachable by
stripping scales to identity — a gap a unified pipeline would own in one place.
