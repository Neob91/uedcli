"""The class resolver every mover-aware uedcli entry point now takes — for the spike harnesses.

Since 2026-07-25 (`decisions.md` 2026-07-25 10:18 UTC) `movers.is_mover` is SCHEMA-AWARE: it asks
whether the actor's class descends from `Engine.Mover` by walking the class hierarchy in a
`classindex.ClassIndex` built over the game's own `.u` packages, instead of guessing from the class
name. So `native.materialize._in_world_csg`, `_build_level_model` and `run_materialize_native`
(and `movers.canonicalize_*`) all take that index explicitly — there is deliberately NO name-guess
fallback, because a wrong answer is invisible: every mover would read as a static world brush and
get carved into the BSP.

The harnesses run outside the CLI, so they build the index the same way `dispatch._class_index`
does: from the resolved uedcli project (this repo) plus the per-user games config
(`~/.uedcli/config.toml`). Memoized — the scan is per-process work, not per-call.

    from spike_classindex import class_index
    ... M.run_materialize_native(level=lvl, out_path=out, class_index=class_index(), ...)
"""
from __future__ import annotations

_INDEX = None


def class_index():
    """The `ClassIndex` over this repo's composed package search path (memoized). Raises if no
    project or no games config resolves — the harness must fail loudly rather than mis-classify
    every mover."""
    global _INDEX
    if _INDEX is None:
        from uedcli import config
        from uedcli.classindex import ClassIndex
        project = config.resolve_project(
            cwd="/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
        if project is None:
            raise RuntimeError("spike_classindex: no uedcli project resolved (need uedcli.toml)")
        user_config = config.load_user_config()
        if user_config is None:
            raise RuntimeError("spike_classindex: no per-user games config (~/.uedcli/config.toml) "
                               "— needed to resolve the game's `.u` packages for mover detection")
        _INDEX = ClassIndex.from_project(project, user_config)
    return _INDEX
