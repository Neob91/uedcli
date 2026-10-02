+++
priority = "p3"
kind = "implement"
summary = "Rust rasterizer for the consolidated offline preview (perf follow-on)"
+++

# Rust rasterizer for the consolidated offline preview (perf follow-on)

Owner ruling (2026-08-05, on `consolidate-level-preview-native-onto-the-actor`): the consolidated
offline preview ships on the pure-Python `preview.py` rasterizer even over a whole level, accepting
whatever it costs; a **Rust rasterizer refactor is planned separately** and is NOT a gate on the
consolidation.

This item tracks that planned refactor: a Rust rasterizer for the unified offline renderer, once the
consolidation has landed and `preview.py` is the single offline draw path. Note this is a DIFFERENT
Rust rasterizer from the retired `render.rs` — it draws whatever the consolidated `preview.py`
produces (its projection, its CSG-solved surfaces, its concave-correct fill, its exit-2 rules), not
the old `preview_native` scene model.

Depends on: `consolidate-level-preview-native-onto-the-actor` landing first. Related:
`make-actor-preview-faster` (the same rasterizer hot path; decide whether these merge).
