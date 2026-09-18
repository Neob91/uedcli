+++
priority = "p3"
kind = "docs"
summary = "dev/docs/GUI.md's selection-marker bullets describe behaviour two landed changes replaced -- needs the owner's yes to edit"
+++

# `dev/docs/GUI.md`'s selection-marker bullets are stale

Found in review of the pivot-cross change (2026-09-18). Two claims in the "Selection & the
Inspector" bullets no longer match the code, both from changes that landed after they were written.
`dev/docs/` needs the owner's explicit approval to edit, so this is a proposal, not an edit.

1. "The pre-existing red pivot crosshair **still renders per selected actor**; the same real-UED22
   evidence suggests it may have the same one-widget-per-selection mismatch, not yet addressed
   here." It is now ONE cross per selection, anchored to the actor most recently the sole selection
   and shown only for a grid-snapping (brush) anchor — `SelectionMarkers.tsx`'s `pivotBrush` +
   `selectionSet.ts`'s `pivotAnchor`, GUI-PARITY.md "Pivot-cross ... Part 4".
2. "`VERTEX_DOT_SIZE = 2` world units" and "the vertex dots, which stay world-scaled". They are now
   `VERTEX_DOT_SCREEN_PX = 6`, rescaled per frame to a constant screen size — the
   `vertex-handles-should-be-screen-size-constant` change.
