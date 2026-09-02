Do you still want a translucent x-ray preview mode, given you ruled `--faces flat`/`textured` OPAQUE and non-x-ray?

## Context

This p3 item's original ask was "filled faces (back-to-front grey ALPHA compositing for
stacked/concentric geometry), depth-sorted". The filled + depth-sorted half shipped as `--faces
flat` (opaque, z-buffered). But `flat`/`textured` were then ruled, deliberately and more than once,
to be OPAQUE and NON-x-ray (board `four-actor-preview-faces-rulings-need-a-durable`: "A SOLID BRUSH
IS OPAQUE", "nearest surface wins per pixel", "never an x-ray").

A translucent grey compositing mode is the exact opposite: its whole purpose is to see THROUGH shells
so concentric/stacked volumes are legible. It would be an ADDITIONAL mode, not a change to `flat` — a
`--faces ghost` value that composites every face back-to-front in translucent grey. It reads
occupancy, not what the game shows.

Options:
- **Add `--faces ghost`** — legible stacked/concentric geometry; a fourth mode alongside the opaque
  ones, no change to them.
- **Drop it** — the opaque `flat` + on-face index placement already disambiguate faces; keep the one
  visibility model.

Recommendation: this is genuinely your call — the mode is useful for nested-room authoring but
reintroduces exactly the x-ray behaviour you removed from the opaque modes. If yes, decide grey-only
vs faint CSG tint and how `--highlight`/`--focus` behave under it.

## Answer

<!-- Empty = open. -->
