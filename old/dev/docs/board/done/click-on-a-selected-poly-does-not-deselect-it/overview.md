+++
priority = "p1"
kind = "debug"
summary = "clicking a selected poly does not deselect it; should toggle off when it's the sole selection"
+++

# click on a selected poly does not deselect it

Fixed: `selectionSet.ts`'s `toggleSelection` gained an opt-in `deselectSole` param, used by poly/
surface selection only (actor selection's no-op-reselect stays as documented). Reviewed; two
test-quality gaps the review found (no integration-level regression, a stale `QuadLayout.test.tsx`
mock) are fixed too.
