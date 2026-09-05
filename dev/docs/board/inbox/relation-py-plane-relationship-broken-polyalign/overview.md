+++
priority = "p1"
kind = "bug"
summary = "relation.py plane_relationship broken: polyalign missing _PARALLEL_EPS/_PLANE_EPS"
+++

# relation.py plane_relationship broken: polyalign missing _PARALLEL_EPS/_PLANE_EPS

`uedcli/relation.py:41,48` reference `polyalign._PARALLEL_EPS`/`polyalign._PLANE_EPS`, but commit
`252c4ad` (the `poly align wall|floor|run` rewrite) deleted both constants from `polyalign.py`
without updating `relation.py`. Any call into `relation.plane_relationship`/`relation.compute` now
raises `AttributeError: module 'uedcli.polyalign' has no attribute '_PARALLEL_EPS'`.

Verified 2026-09-05 on master (`3fa2e3d`): `uedcli/tests/test_relation.py` — 12 of 27 tests fail on
this. `brush measure relation` is broken end to end.

Fix: restore the two tolerance constants (values were `_PARALLEL_EPS = 1e-3`, `_PLANE_EPS = 0.5`,
per `git show 252c4ad -- uedcli/polyalign.py`) — either back in `polyalign.py`, or move them into
`relation.py` itself if `polyalign.py` no longer has a reason to own them post-rewrite.

Flagged as a required precursor in `dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md`
(the `brush relation measure/find/set` design) — that work reuses `plane_relationship` directly and
can't validate against a green baseline until this is fixed.
