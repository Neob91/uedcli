+++
priority = "p?"
kind = "unknown"
summary = "`level preview --native` — the offline draft preview backend"
+++

# `level preview --native` — the offline draft preview backend

— BUILT 2026-07-16 (spec +
plan 2026-07-16, decision 12:13 UTC). `level preview` now renders freely-posed textured stills
entirely offline (Rust CSG carve + `render.rs` rasterizer + native `utexture.py` decode; SHOT
grammar shared with the future `--game` tier); the editor-screenshot backend
(`preview_render.py`, `TARGET[:MODE][=NAME]`, `MODE_INI`, `query.overview_brush`) is DELETED.
U/V/Pan mapping pinned against live editor+game references
(`spikes/2026-07-16-native-preview-anchor/`); golden blessed post-anchor. `--game` = clean
reserved exit-2. **Remnants:** `--lit` fast-follow (spec §8, consumes the N-4 bake); the
in-game `--game` tier itself (spec 2026-07-13).
