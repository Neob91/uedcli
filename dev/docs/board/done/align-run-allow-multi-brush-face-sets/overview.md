+++
priority = "p2"
kind = "implement"
summary = "brush poly align run: drop the one-brush restriction, walk a run across multiple brushes"
+++

# align run: allow multi-brush face sets

`brush poly align run` currently rejects a target set spanning more than one brush actor
(`_run_prewalk` step 1, `uedcli/polyalign.py:462`). Real corridors are usually built as chains of
separate brushes (straight segments + corner revolves); today each brush must be run-aligned
separately and seam continuity across brush boundaries matched by hand. The underlying geometry
(`_world_verts`, `_edges_coincide`) already operates in world space and already spans multiple
actors in `wall`/`floor` mode — the one-brush guard in `run` looks like scope boundary from the
step-4 build, not a structural limit. See `spec.md`.
