+++
priority = "p1"
kind = "debug"
summary = "test_csg_native_differential.py::_actor_to_brush still builds the texture bundle as a 4-tuple ([], [], [], []) while committed lib.rs takes 5 (textures_flat added) — 7 tests fail with `expected tuple of length 5, but got tuple of length 4` on ANY freshly built .so. Same staleness class the sweep round's 'stale .so' incidental finding hit in parity_compare, but here the TEST is the stale side. Fix: append [] for textures_flat in the test helper."
+++

# test_csg_native_differential passes a 4-field texture bundle; lib.rs wants 5 (textures_flat)

Hit 2026-09-02 (full `bin/test` for p_base round 15, whose diff touches neither file — confirmed
present on origin/master: `git show origin/master:uedcli/tests/test_csg_native_differential.py`
line ~66 vs `origin/master:uedcli-native/src/lib.rs` line 137). Anyone running against a stale
venv `.so` (predating `textures_flat`) sees these pass; a fresh `ensure_native_ext` build fails all
7 (`test_native_surfset_matches_editor_golden[*]`, `test_case_{a,d,f}_full_compare*`). One-line fix
in `_actor_to_brush`; not made here (out of the round's scope, and the fix should re-verify the
goldens still pin what they claim).
