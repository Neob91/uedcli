+++
priority = "p2"
kind = "debug"
summary = "`brush build cylinder/cone --sides` has NO upper bound — >16 emits an invalid cap face"
+++

# `brush build cylinder/cone --sides` has NO upper bound — >16 emits an invalid cap face

An `FPoly` holds at most 16 vertices (`FPoly::VERTEX_THRESHOLD`; `kb/csg-bsp.md` §5.2), and
`kb/geometry-builders.md` §1 records the cap as invalid above 16 — but `builders.cylinder`/`cone`
accept any `sides >= 3` (`builders.py:204`, `:227`), so `brush build cylinder --sides 24` silently
emits a 24-vertex cap. Exactly the defect the new `extrude`/`revolve` cap tiling exists to prevent,
but in existing code. Fix: reject above 16, or tile the cap the way
`specs/2026-07-25-brush-profile-generators.md` §6 does. (Cold review, 2026-07-25.)
