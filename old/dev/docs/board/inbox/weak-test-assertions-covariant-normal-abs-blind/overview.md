+++
priority = "p2"
kind = "implement"
summary = "weak test assertions: covariant-normal abs()-blind; exit-2 tests dont check offending value"
+++

# weak test assertions let real regressions pass green

Two clusters.

Sign-blind / circular geometry tests:

- `test_native_scale.py:236-238` — `assert abs(abs(n[1]) - 1.0) < 1e-4` takes `abs()` of the normal
  component, so it can't tell an outward normal from an inverted (inside-out) one. A cofactor-sign bug
  in `rotation.inverse` for scaled+rotated brushes ships wrong-facing surfaces and stays green.
- `test_native_scale.py:266-297` — the "independent reference" is the SAME formula as the code under
  test (`transform.covariant_axes`), not an oracle; a shared sign/order bug cancels. The docstring's
  claimed alternate formula doesn't exist in the code (stale comment).
- Also `test_polyalign.py` seam-continuity compares `face_uv` against itself; `test_vertex.py:49-51`,
  `test_snap.py:84-90` use bare `pytest.raises(GeometryError)` with no `match=` where the CAUSE is the
  point (contrast `test_geometry.py`, which pins every cause).

Exit-2 tests that never check the named offending value (CLAUDE.md: "error messages include the
offending value"): `test_ingest_validation.py:498,509` (no `capsys`); `test_dispatch.py:773-789`;
the shared `test_name_not_found_sweep.py:154` helper (checks only the phrase "not found", never the
bad name — a verb blaming the wrong argument passes); `test_stash_dispatch.py:78`;
`test_scale_verbs.py:170,194`; `test_find_compose.py` `_run()` (captures stdout only);
`test_actor_prop.py` (8+ cases rc-only; `:133,151` never read back the stored value);
`test_import_verb.py:214,188`.

Fix: assert the offending value in each; give geometry raises a `match=`; make the covariant-normal
test sign-sensitive with a real oracle.
