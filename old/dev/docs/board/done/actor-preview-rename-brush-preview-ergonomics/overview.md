+++
priority = "p?"
kind = "unknown"
summary = "`actor preview` — rename `brush preview` + ergonomics + point actors + overlays"
+++

# `actor preview` — rename `brush preview` + ergonomics + point actors + overlays

— BUILT
2026-07-21 (both coupled specs in one pass). The wireframe verb moved from the `brush` group to
`actor` (no alias; `--tree` still excluded). Ergonomics: unified `--from-t3d <FILE…|->` (also
migrated onto `stash capture`, dropped `--from-stdin`); `--zoom-poly` is now a `BRUSH:idx` selector
that frames-only; split `--highlight-poly` (repeatable set form); the renderer `highlight` param is
a `(name,idx)` set; six-way CSG-op brush colouring (highlight = the brush's own vivid hue + bolder
line, red retired); `--zoom-factor` (default 0.8). Point actors: DT_Sprite billboards (masked blit,
`DrawScale·USize×VSize`), DT_Mesh/DT_None markers, `--show-collision` cylinders + `--show-light-
range`/`--show-sound-range` spheres — fields resolved in dispatch via the `_class_defaults` seam +
a `TextureResolver.resolve_masked`, schema-unavailable degrading to a marker + note (no traceback).
Engine facts (sprite footprint, `25·(x+1)` radii, 2·CollisionHeight box) pinned in
`test_engine_facts.py`. Specs `spec-brush-preview-ergonomics.md` +
`spec.md`; UED palette/radii facts folded into `unrealed/rendering.md`.
