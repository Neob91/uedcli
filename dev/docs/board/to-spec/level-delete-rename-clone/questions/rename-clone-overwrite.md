# rename/clone onto an existing destination — hard-refuse (delete-first) or add `--overwrite`?

## Context

`safety.md` gives materialize/import/stash their `--overwrite` because their destination is a
rebuildable map or a throwaway box. A rename/clone destination is a whole authored level trunk —
overwriting it destroys authored work that only git can recover.

Options:
- (a) **Hard-refuse an existing destination, no override** (recommend) — the user runs `level delete`
  first, an explicit two-step for a catastrophic action.
- (b) Add `--overwrite` for tool-wide uniformity — one flag, but makes clobbering a whole level as
  easy as clobbering a rebuildable map.

Recommend (a): the asymmetry (authored trunk vs rebuildable artifact) justifies the extra friction.

## Answer

<!-- Empty = open. -->
