+++
priority = "p2"
kind = "docs"
summary = "brush poly move: spec/help \"most non-axis moves rejected\" is geometrically false for quad brushes"
+++

# brush poly move: spec/help "most non-axis moves rejected" is geometrically false for quad brushes

Filed while building `brush-poly-move`. The verb ships and works; this is about inaccurate wording I
implemented verbatim from the spec (decision rule: implement as given, file the flaw, don't fix).

## The claim

`spec.md` and the `--by` help I copied from it both say non-axis moves are the rejected majority:

- spec §Design: "Most non-axis-aligned moves push a neighbour non-planar and are REJECTED (exit 2);
  moving a face along its own normal is the safe case."
- plan Slice 1 test: "In-plane `--by 32,0,0` on a cube face → `GeometryError` (neighbour non-planar)."
- The `--by` help (`cli/parsers/brush.py`) and `docs/usage.md` repeat this.

## Measurement (this build)

Moving a whole cube TOP face `--by 32,0,0` is **VALID**, not rejected: every side quad stays a planar
trapezoid, so the brush becomes a valid parallelepiped. `apply_move` accepts it and `validate_brush`
passes. Verified:

    apply_move(mk('B1'), ['B1:4'], by=(32,0,0))   # -> touched ['B1'], 8 welds, no raise

Two adjacent faces `--by 0,0,64` is also valid (the plan expected this to trip the dedupe path only,
which it does — but the result is watertight, not rejected). A move is rejected only when the result
is DEGENERATE/coincident (e.g. top face `--by 0,0,-64` collapses the cube -> `GeometryError`) or a
neighbour genuinely goes non-planar (needs a face sharing a DIAGONAL, a >4-gon cap, etc. — not the
common quad case). For quad-faced brushes, valid is the majority and rejection the exception — the
inverse of what the wording says.

Why the spec's intuition is wrong: translating an EDGE (two adjacent corners) of a planar quad by a
constant vector leaves the quad planar (trapezoid). A cube's top face shares an edge, never a
diagonal, with each side face, so a single-face move never breaks a neighbour's planarity.

## Proposed correction (needs owner yes)

Reword the `--by` help + `docs/usage.md` + spec to say: moving a whole face by a constant delta keeps
quad neighbours planar, so such moves are usually VALID (they shear/deform the brush); a move is
rejected (exit 2) only when it makes the solid degenerate (a face collapses to zero area / corners
coincide) or pushes a genuinely non-planar neighbour off-plane. Drop "most non-axis moves are
rejected". Tests in `test_poly_move.py` already assert the real behavior and reference this item.

Left AS SPEC'D in this build; awaiting the reword decision.
