+++
priority = "p3"
kind = "implement"
summary = "Gray out Rebuild when it would not change anything"
+++

# gray out Rebuild when it would not change anything

Owner request: `web/src/App.tsx`'s `BuildToolbar` only disables Rebuild while a request is already
in flight (`disabled={busy !== null}`) -- it's always clickable otherwise, even when clicking it
would just re-solve the exact same content and produce an identical `(geom_hash, light_hash)` pin.
Want it grayed out in that case too, as a signal there's nothing to gain from clicking it.

The hard part is CHEAPLY knowing "would not change anything" without doing the solve. A Rebuild's
real input is the trunk's current content plus whatever this session currently has staged
(`edits.apply_staged_overlay`) -- so the no-op case is: nothing staged has changed since the
session's own last Rebuild, AND the trunk hasn't changed since then either
(`status.changes_available` already tracks the second half via `LevelContext.generation`, but
there's no existing "has staged state changed since the last Rebuild" signal to pair it with).
Whether that pairing can be done cheaply (a staged-state fingerprint compared at Rebuild-click time,
not a real solve) or needs a real design pass is open -- not scoped out here, just not designed yet.
