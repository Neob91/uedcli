+++
priority = "p3"
kind = "owner-question"
summary = "Should the >64-face POLY-BUDGET advisory cover every `brush build` shape, not just `extrude`/`revolve`?"
+++

# Should the >64-face POLY-BUDGET advisory cover every `brush build` shape, not just `extrude`/`revolve`?

Shipped 2026-07-25 with the profile generators, gated on
those two shapes (`dispatch._SWEPT_SHAPES`). The OFF-GRID advisory's gate is forced — an ungated
one turns `test_generators.py`'s "a solid 8-gon cylinder says nothing on stderr" red, and the
spec deliberately leaves `cylinder`/`cone` alone — but the poly-budget gate is a judgement call I
made rather than a spec requirement. Ungated it would also fire on e.g. `brush build staircase
--steps 16` (66 faces), which is arguably a true and useful warning. Deliberately NOT decided in
the build: it changes an existing verb's observable output.
