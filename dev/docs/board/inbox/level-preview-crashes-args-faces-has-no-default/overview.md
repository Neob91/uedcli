+++
priority = "p2"
kind = "debug"
summary = "level preview crashes: args.faces has no default in test/CLI paths lacking it"
+++

# level preview crashes: args.faces has no default in test/CLI paths lacking it

Found while running `bin/test -k "preview or rendering"` for an unrelated change (pre-existing on
master, not caused by that work).

`uedcli/cli/commands/level.py:603` (`if use_game and args.faces is not None:`) and `:712`
(`if (args.faces or "textured") == "wire":`) read `args.faces` directly, no `getattr` default.
`uedcli/tests/test_dispatch.py`'s `_preview_args` fixture (predates the `--faces` flag added in
`11f5ada` "Add `level photo --native --faces wire`...") never sets `faces`, so any `SimpleNamespace`
built the old way raises `AttributeError: 'types.SimpleNamespace' object has no attribute 'faces'`.

10 failures in `test_dispatch.py`/`test_env_level_and_echo.py`, all this same error:
`test_level_preview_native_routes_shots_to_render`, `test_level_preview_bad_token_errors_before_any_work`,
`test_level_preview_game_routes_to_preview_game`, `test_level_preview_bare_defaults_to_game_backend`,
`test_level_preview_bad_size_named`, `test_level_preview_native_error_is_clean_exit_2`,
`test_level_preview_list_actors_requires_game_and_map`, `test_level_preview_list_actors_routes_and_prints`,
`test_level_preview_negative_sample_rejected`, `test_preview_tree_with_map_is_rejected`.

Likely fix: either `_preview_args` grows a `faces=None` default, or `level.py` switches to
`getattr(args, "faces", None)` like `cli/rendering.py:734` already does. Whichever is right also
needs checking against the real argparse definition for `level photo` (does `--faces` always get a
parsed default, so is this a test-fixture-only staleness, or can real CLI invocations also hit this
path without `.faces` set?).
