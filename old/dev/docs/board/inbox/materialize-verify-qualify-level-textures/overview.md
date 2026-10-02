+++
priority = "p1"
kind = "debug"
summary = "materialize post-verify: qualify_level_textures cannot match some retail brushes' polys to an OBJ DEPENDENCIES Engine.Polys block, so verified builds of real maps fail even when the build is correct."
+++

# materialize verify: `qualify_level_textures` fails to match retail brushes

Surfaced building the full retail map list (see `level-materialize-on-full-retail-list-geometry`).
Once the save-wedge and verify-sync-timeout blockers are cleared, `06_HongKong_WanChai_Garage`
builds a valid lit map but its post-verify fails:

```
qualify_level_textures: no OBJ DEPENDENCIES Engine.Polys block matches brush 'Brush126''s 20
textured polys ['drtywater_a', 'DrtyIronWOriv_A', ...] — 24 of 202 non-empty blocks still unclaimed
(dump poly-order drift or a missing/misnamed texture?)
```

- The `OBJ DEPENDENCIES` dump completed (202 blocks), so this is NOT the sync-timeout issue — it is
  the matching logic in `qualify.qualify_level_textures` failing on retail content.
- Garage is geometrically clean (0 brushes refused by `validate_brush`), so it is not a
  non-planar / stubbed-geometry artifact.
- The build itself is sound: `--no-verify` produces a 797 KB map, 576/1083 surfaces lit, comparable
  to the spike's MAP LOAD build (569/1004).
- 24 of 202 blocks unclaimed suggests a systematic mismatch (poly-order drift between the built
  map's dump order and the trunk, or a repeated-texture disambiguation gap), not a one-off.

This blocks the DEFAULT (verified) `level materialize` on real maps. Needs its own investigation of
`qualify_level_textures`'s block-to-brush matching. Reproduce: build any retail trunk with verify
on (probe `$CLAUDE_JOB_DIR/tmp/probe_materialize.py --wait-rebuild`, or the shipped CLI once the
driver fixes land).

## Likely a SECOND verify-vs-build gap behind it: viewport cameras

The built garage map carries 6 `Camera` actors (`Camera6`–`Camera11`) — UnrealEd's own viewport
cameras, which the editor creates and `MAP SAVE` writes. `level import` strips them, so the trunk
has none, and the verify's expected level has none. So even past the texture-match, the verify would
see 6 actors in the built map that are not in the intended level. Retail maps DO normally ship
viewport cameras (spike §5: 4 per map), so the verify should treat them as an editor artifact
(ignore like a computed prop), not a mismatch. Confirm and handle both before verified retail builds
can pass.
