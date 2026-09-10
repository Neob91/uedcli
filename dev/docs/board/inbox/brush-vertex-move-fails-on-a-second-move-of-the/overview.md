+++
priority = "p2"
kind = "bug"
summary = "brush vertex move fails on a second move of the same brush after an earlier vertex move"
+++

# brush vertex move fails on a second move of the same brush after an earlier vertex move

`brush vertex move` fails with a bogus "no brush vertex at" error on the SECOND call against a
brush that was already vertex-moved once, even when `--at` names a coordinate `brush vertex list`
itself reports as a real corner.

Repro (UNATCO trunk, any project):
```
brush vertex move Brush420 --at 448,64,416 --at 448,304,416 --at 448,304,240 --at 448,64,240 --by 48,0,0
# succeeds
brush vertex list Brush420   # correctly reports (496,64,416) etc. — world coords, first move applied
brush vertex move Brush420 --at 496,64,416 --by -1,0,0
# FAILS: no brush vertex at ('225.882300', '-128', '80'); corners are
#   [('-192', '-128', '80'), ('225.882345', '-128', '80'), ...]
```

The error's own "corners are" list doesn't match the brush's real (world) geometry at all — small
symmetric numbers (192/128/80) unrelated to the actual office wall (x -96..496, y 64..304, z
240..416). Looks like the second call's `--at` world→local match uses a stale Location/PrePivot
snapshot from before the first move, or compares against the wrong reference frame. `brush vertex
list` (read-only) is unaffected — only a second `move` call breaks.

Workaround used: build the "second edit" from the pristine baseline instead of double-editing an
already-moved brush (apply both deltas' worth of edits in one derivation from the original trunk).

Found while building INCORRECT reference states for `dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference/`.
