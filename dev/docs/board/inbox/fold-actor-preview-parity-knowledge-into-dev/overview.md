+++
priority = "p2"
kind = "owner-question"
summary = "Owner approval to fold the actor-preview parity knowledge into dev/docs (architecture 'Preview internals' + a rationale/ entry)."
+++

# Fold actor-preview parity knowledge into dev/docs

The parity build (`actor-preview-unrealed-render-parity-new-csg`, in `done/`) is spec-ephemeral.
`CLAUDE.md` forbids editing `dev/docs/` (architecture, rationale, unrealed) without the owner's yes, so
this parks the proposed edits for approval rather than making them:

1. **`architecture.md` "Preview internals"** — record that `actor preview --faces textured` is now the
   CSG-SOLVED world via `preview_native.solve_world_surfaces` → `build_geometry_bspcsg`, drawn through
   `preview.py`'s ortho pipeline (`_solved_scene`), with a per-view backface cull by the surviving
   fragment's normal; `flat` and the old per-brush textured are gone; the wire/textured split, the
   black background, and the pre-solve zero-surface / point-mover-only guards.

2. **A `rationale/` entry** for the two implementation calls the spec flagged for `rationale/`:
   - the **decal-once rule** (one source poly split into N fragments draws ONE index label, on the
     largest-projected-area fragment; alternative "first fragment" rejected — a sliver);
   - the **bspcsg-core choice** for the preview (the default core mis-renders overlapping-subtract
     doorways; the faithful core's residual byte-divergences are accepted for a visual preview).

3. **`unrealed/rendering.md`** "uedcli's offline actor preview" section still says light-grey background
   and describes the old per-brush modes — needs updating for black bg + the solved model.

Propose exact text on approval. (The `direction/` home is a separate item:
`actor-preview-parity-direction-home`.)
