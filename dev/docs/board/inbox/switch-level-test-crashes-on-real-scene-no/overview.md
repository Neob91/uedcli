+++
priority = "p3"
kind = "debug"
summary = "test_switch_level_resets_all_three_cache_slots crashes on its own real /scene call -- pre-existing, only just became visible (native ext never built in this sandbox before today)"
+++

# switch-level test crashes on real /scene: no resolvable games config in isolated test env

`uedcli/tests/test_serve_app.py::test_switch_level_resets_all_three_cache_slots` (added
`b607ba29`, 2026-09-18) fails: `c.get("/api/level/Other/scene")` (its final call, after `PUT
/api/level` switches to "Other") crashes trying to resolve a real `_scene_inputs(project)` — the
test's fake `project = SimpleNamespace(root=..., maps=None)` is missing fields a real `Project`
(`config.py:115-121`) has, and even with those added there is no real per-user games config
visible in this test's isolated `UEDCLI_HOME` (the autouse `_isolate_uedcli_home` fixture points it
at an empty per-test tmp dir), so `config.load_user_config()` returns `None` and
`select_substrate` has nothing to resolve either way.

## Why this was invisible until now

This test is gated behind `_require_ued22()` (`pytest.importorskip("uedcli_native")`), and until
today this sandbox's `uedcli_native` build always failed (rootless docker daemon on a separate
`dind` sidecar, no shared filesystem — see `bin/_venv.sh`'s rewritten `ensure_native_ext`, board
`gui-serve-rebuilds-classindex-on-every-request`'s follow-on docker-build fix). So this test has
never actually run to completion in this environment before; there's no evidence it ever passed.

## Root cause

Every OTHER test in this file either monkeypatches `serve_app._scene_inputs` directly, or seeds
`_trunk_ref`/`_scene_inputs_ref` by calling `app.state.get_trunk(...)` manually with a real,
already-built `index`/`defaults` pair (bypassing `_scene_inputs(project)` entirely). This is the
ONE test where a plain HTTP `/scene` call reaches the real, uncached `_scene_inputs(project)` path
-- deliberately, per its own docstring ("A fresh trunk-read for 'Other' happens lazily on the
next real request") -- but nothing in its setup gives that real path anything to resolve.

Partial fix already applied (harmless, but not sufficient alone): the fake `project` now sets
`paths=None` explicitly, matching a real `Project`'s own default (config.py:118) -- this moves the
crash from `AttributeError: no attribute 'paths'` to the next missing field
(`AttributeError: no attribute 'game'`), and even with `game` added, `select_substrate` still needs
a real, non-`None` `user_config.games` entry this test's isolated environment has no way to supply
without writing one into the per-test `UEDCLI_HOME`.

## What to do

Either: (a) give this test its own minimal `~/.uedcli/config.toml`-equivalent in the isolated
`UEDCLI_HOME` (write a `[games.x]` block with a real, empty-but-valid `paths` dir, matching how
other tests that need a genuinely resolvable project set one up), so the real `/scene` call
resolves to an empty-but-valid search path; or (b) seed `_scene_inputs_ref` for "Other" too (via
`app.state`, same as it already does for "TestLevel") before the final assertion, if the test's
real intent is just to confirm the SLOT was cleared and re-derived at all, not to prove a fully
real end-to-end resolve. Whichever is chosen, re-verify with a real `uedcli_native` build (this
sandbox's fix above makes that possible for the first time) rather than trusting a skip.

## Where to look

`uedcli/tests/test_serve_app.py:681-720` (the test), `uedcli/tests/conftest.py`'s
`_isolate_uedcli_home` (the autouse fixture that empties `UEDCLI_HOME` per test), `uedcli/config.py`
(`Project`, `select_substrate`, `_composed_dirs_with_provenance`).
