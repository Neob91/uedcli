+++
priority = "p?"
kind = "chore"
summary = "Stale test: test_load_pulls_in_a_new_actor_but_geometry_stays_pinned"
+++

# Stale test: test_load_pulls_in_a_new_actor_but_geometry_stays_pinned

`uedcli/tests/test_serve_load_rebuild.py::test_load_pulls_in_a_new_actor_but_geometry_stays_pinned_until_a_separate_rebuild`
fails on current master (found while verifying an unrelated squash-merge, 2026-09-20):

```
AssertionError: assert {('Room', 0), ('Room', 1), ..., ('Room', 5)} == {'Room'}
```

## Root cause

`06fdef6e` ("Identify a selectable surface by BRUSH:IDX, not solved-fragment position",
2026-09-16) changed `ScenePoly`'s surface-selection identity from a bare actor-name string to
`(owner, i_brush_poly)`. This test still asserts `{p["owner"] for p in ...} == {"Room"}` -- the
old, pre-change shape -- and was never updated for the new one. Confirmed pre-existing: `06fdef6e`
predates this session's work entirely, and no commit in the squash-merge under verification
touches `scene.py`, `preview_native.py`, or this test.

## Fix

Read `uedcli/serve/scene.py`'s current `ScenePoly` dataclass to confirm whether `owner`/
`i_brush_poly` are separate fields (in which case this test's assertion just needs updating to
compare only `p["owner"]`, or to compare the full `(owner, i_brush_poly)` set against the expected
per-fragment set) or whether the test is reading the wrong field entirely. Not diagnosed further
here -- flagged for whoever picks it up.
