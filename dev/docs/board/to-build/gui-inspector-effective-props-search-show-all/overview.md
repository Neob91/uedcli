+++
priority = "p2"
kind = "implement"
summary = "GUI Inspector: effective props (search, show-all/overrides, struct/array expansion)"
+++

# GUI Inspector: effective props (search, show-all/overrides, struct/array expansion)

Read-only Inspector redesign, brainstormed 2026-09-22/23: search by property name, a toggle between
today's overrides-only view and a show-all (incl. class defaults) view, per-property/per-struct-member
not-set marking, typed display (enum dropdown-ready, bool checkbox), struct properties expanded into
member sub-rows, static arrays expandable to per-element rows, and a Folder/Labels display refresh
(chip labels, dash empty state). Surface detail gains the real `Package.Group.Name` texture identity
plus poly area/normal.

Deliberately excludes: actual editing (enum `<select>`/numeric-input write-back, surface texture
reassignment) — sketched at the shape level only, held for after the in-flight "Persistent GUI
Editing Sessions" staging rewrite lands. That rewrite is not yet on this board (as of 2026-09-23 it
exists only as an unmerged plan, `docs/superpowers/plans/2026-09-22-persistent-gui-editing-sessions.md`,
in a separate `gui-sessions-brainstorm` worktree not yet squash-merged to master) — check whether it
has landed/moved to the board before picking up this item's own editing follow-on. Object-ref
properties, multi-select comparison, and copy-to-clipboard were considered and declined for this
round.

Filed alongside a separate p0 bug this design work surfaced:
`dev/docs/board/inbox/trunk-texture-refs-strip-group-which-is/` (texture refs wrongly strip Group,
sometimes losing real identity) — unrelated to this item's own scope, not a dependency.
