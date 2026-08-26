+++
priority = "p2"
kind = "debug"
summary = "Native-materialize floor texture is rotated/skewed vs the editor build (UNATCO)"
+++

# Native-materialize floor texture is rotated/skewed vs the editor build (UNATCO)

Same camera anchor (`at:@PathNode0;rot:0,0`), same UNATCO level, `level preview --game`, two builds:

- **Real-editor build** (`MAP LOAD` + `MAP REBUILD` + `LIGHT APPLY`, from the earlier `--game`
  demo this session): the floor's grate/plank texture tiles in a clean rectangular pattern,
  axis-aligned with the room -- planks run parallel to the wall seam.
- **Native build** (`UEDCLI_NATIVE_MATERIALIZE=1`, `e01fb53`): the SAME texture on the SAME floor
  surface renders rotated/sheared at an angle relative to the room -- planks run diagonally, not
  parallel to the walls.

The wall tiling in both shots looks comparably aligned; the defect is visible on this floor surface
specifically (not checked exhaustively across every surface in the level).

Not yet root-caused. Two candidate areas, neither confirmed:

- The on-disk `TextureU`/`TextureV`/`PanU`/`PanV` fields `model_write.rs`'s `serialize_model`
  writes for this surf, vs. what the native CSG core (`bspcsg.rs`/`fpoly.rs`) computed for it.
- Whether this is the same class of issue the "Covariant UV" fix (`43fe45b`) already addressed for
  the `--native` software rasterizer, or a distinct bug specific to the on-disk/game-engine path --
  that fix was for in-process rendering; this defect is observed via the real game reading the
  WRITTEN package, a different code path.

No live-editor evidence gathered yet (which surf, which brush, its authored `TextureU`/`TextureV`
in the trunk) -- next step if picked up.
