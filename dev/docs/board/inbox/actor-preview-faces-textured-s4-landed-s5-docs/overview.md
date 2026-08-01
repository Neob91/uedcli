+++
priority = "p2"
kind = "implement"
summary = "actor preview --faces textured (S4) is built; S5 (cross-cutting docs, rationale, direction confirm, spec deletion) is left."
+++

# `actor preview --faces textured` — S4 done, S5 remains

S4 of board item `actor-preview-faces` shipped in the `actor-preview-textured` worktree (two commits):
the texel renderer in `preview.py`, and the flag + dispatch resolution + `docs/usage.md`. `bin/test`
green (9839 passed, 76 skipped).

What is left is **S5** of the plan (`actor-preview-faces-plan-cites-dev-docs`), all owner-gated and so
NOT done here:

- `dev/docs/architecture.md` "Preview internals" — describe the texel path (the `TextureData` seam, the
  shared plane solver, the per-face mip pick, masking, the `textured` no-wireframe rule).
- `dev/docs/rationale/preview.md` — the agent-side textured choices (nearest-neighbour + wrap, mip from
  per-face gradients not a view-global gain, DEFAULT_GREY, the shared `_plane_screen_probes`).
- `docs/leveldesign/general/textures-and-surfaces.md` — craft guidance for the three modes
  (owner-approval-gated; do not add without a yes).
- `direction/` confirm of the owner rulings parked for this feature, then delete the ephemeral spec
  (`four-actor-preview-faces-rulings-need-a-durable`) and plan, and remove `to-build/actor-preview-faces`.

## Not done in S4, by design / by environment

- **No real fill-cost measurement** (plan S4's last Done-when). It needs the game corpus, which this
  container has no games config or `.u` for; `usage.md` deliberately states NO cost number, so nothing
  false shipped. Take the measurement on real content before any doc states a number.
- `masked` treats the decoder's `b_masked is None` (no reachable class-default source) as falsy, per the
  existing note `inbox/bmasked-with-no-reachable-class-default-source`.
