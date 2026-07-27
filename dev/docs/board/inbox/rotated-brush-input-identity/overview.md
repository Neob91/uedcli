+++
priority = "p3"
kind = "unknown"
summary = "Rotated-brush input identity (byte-identity precondition for UNATCO-class content)"
+++

# Rotated-brush input identity (byte-identity precondition for UNATCO-class content)

p3 **Rotated-brush input identity (byte-identity precondition for UNATCO-class content).**
The castle is all identity-transform brushes so native `v+Location` is bit-trivial, but the editor's
`Actor::BuildCoords` FRotator→matrix uses the `GMath` sine LOOKUP TABLE (`FGlobalMath`), NOT libm
`sinf` — so reproducing rotated-brush world verts bit-exactly needs that table ported.
**UPDATE 2026-07-17: FUNCTIONAL rotation is now ENABLED** (no longer rejected).
`materialize.py::_build_brush_input` builds the rotation matrix via `rotation.actor_matrix` →
`euler_to_matrix_uu`, which ALREADY reads the ported `GMath` sine table (`rotation.gmath_sin/cos`,
indexed `(field>>2)&16383`) — the same table+convention `preview_native` uses and that
`spike 2026-06-19-frotator-convention` verified against the editor to ~1e-5uu. So the "port the
table" premise is already satisfied by `rotation.py`; verified on a controlled −90° Yaw box
(`+X(256,0,0)→(0,−256,0)`) and pure/combined Yaw/Pitch/Roll boxes matching `rotation.world_vertices`
exactly. The full 762-brush UNATCO trunk (283 rotated brushes) materializes clean. What remains for
BYTE-identity is only whether `euler_to_matrix_uu` reproduces `BuildCoords` bit-for-bit (matrix
ELEMENT order / rounding), folded into the `bspcsg` byte-identity port — not a functional blocker.
