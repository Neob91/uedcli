+++
priority = "p2"
kind = "debug"
summary = "the brush local-origin (PrePivot) vertex dot only draws on the primary selected brush, not every selected brush"
+++

# vertex-local-origin-dot-only-shows-on-primary

Fixed: `SelectionMarkers.tsx`'s local-origin dot no longer gates on `primaryName` — it renders once
per selected brush, same as the poly-vertex dots, matching `preview.py`'s `_scene_geometry`. The
global pivot cross (`pivotAnchor`) is untouched. Regression: `SelectionMarkers.test.tsx`.
