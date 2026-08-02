+++
priority = "p?"
kind = "unknown"
summary = "`poly align` + `brush poly find` BUILT"
+++

# `poly align` + `brush poly find` BUILT

(build #5, 2026-07-18; item 11; `direction/conventions.md`,
2026-07-18 21:40 UTC; spec `spec.md`). `polyalign.py`: a stateless
`brush poly find <brush> [--item/--facing/--texture/--json]` producer printing `BRUSH:idx`
selectors, and `brush poly align (--wall|--floor|--ring) [--fresh-frame][--fit-perimeter]
(targets…|-)` that makes a texture flow continuously across a face set. UV convention
`U=(V−Origin)·TextureU+PanU` (scale in `|TextureU|`); continuity defined in WORLD space, written
back per-brush via each brush's own inverse rotation (offset in float `Origin`, `Pan` kept
integer). `--ring` advances U by chord `2r·sin(π/N)`; leave-seam default + `--fit-perimeter`.
31 tests in `test_polyalign.py` (UV-continuity goldens across shared seams, ring wrap, adopt-seed
vs `--fresh-frame`, find filters, every error path, + 2 engine-fact regressions). Docs: usage.md,
architecture.md "Surface texture alignment", t3d.md UV convention. **Deferred → inbox:** `--face`
fit-to-surface, turning (non-coplanar) wall runs, sphere wrap, `--seam` anchor, scaled-brush
textured continuity, `poly find` across multiple brushes, `--fit-perimeter` true pixel-tile meet.
