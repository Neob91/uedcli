# Where should the day-to-day level-editing loop how-to live?

## Context

The doc describes the user's loop: branch → edit trunk model-side → `level preview` → `level
materialize` → commit/merge. It spans several verb families plus git, so it is a narrative, not a
verb reference. Options for its home under `docs/` (user-facing; it must never point at `dev/docs/`):

- (a) **New `docs/workflow.md`**, cross-linked from `docs/usage.md`'s intro and `docs/README.md`.
  A user looking for "how do I actually work day to day" finds one page. Recommended.
- (b) **A "Workflow" section inside `docs/usage.md`.** One fewer file, but `usage.md` is a per-verb
  reference and the narrative gets buried; the file is already ~1300 lines.
- (c) **Under `docs/leveldesign/general/`.** That tree is design CRAFT (lighting, brush shapes,
  human scale), not the tool-operation loop — a poor fit.

Recommendation: (a).

## Answer

<!-- Empty = open. -->
