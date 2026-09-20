+++
priority = "p1"
kind = "implement"
summary = "DONE: reverted 11a1f357 exactly (selection.ts/tapSelect.ts/Viewport3D.tsx/OrthoViewport.tsx + tests) -- Ctrl+click on a poly never deselects a brush, only Shift does; wireframe-outline-line Ctrl-deselect (isLineHit branch, untouched) pinned with a new regression test."
+++

# ctrl-poly-deselect-should-be-wireframe-only-not

Reverted. See `ctrl-click-on-selected-brush-poly-should-deselect/overview.md` for the original fix
and correction note.
