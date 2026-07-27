+++
priority = "p3"
kind = "implement"
summary = "A non-quad face in an `align --run` set exits 2 — generalise it later if a builder ever emits one"
+++

# A non-quad face in an `align --run` set exits 2 — generalise it later if a builder ever emits one

Decided in `specs/2026-07-26-poly-surface-verbs.md` §6 rather than
deferred to the implementer. The quad assumption is load-bearing: a terminal face's free edge is
found as the OPPOSITE edge of the quad (`entry = (exit + 2) % 4`), and an n-gon needs a different
rule for "the far edge". No shipped builder currently produces a non-quad swept face, so the error
is correct today; this item exists so the limitation is findable if one ever does.
