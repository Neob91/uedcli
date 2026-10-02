+++
priority = "p2"
kind = "debug"
summary = "Native materialize silently IGNORES `PostScale` and `SheerRate`"
+++

# Native materialize silently IGNORES `PostScale` and `SheerRate`

(only `MainScale` is
read — `materialize.py::_build_brush_input`; the Rust scale check never sees them), so a brush
carrying either mis-builds with no error — exactly the "silently mis-builds" class
`FPoly::Transform`'s scale rejection exists to prevent. p2. Surfaced by the native-preview spec
review (2026-07-16); the preview spec checks all three fields itself (§4.2) and does not inherit
the hole. Fix materialize's brush-input gate to match.
