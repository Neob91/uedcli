"""Brush-family route: dispatch the stateless generators directly, resolve the single trunk source
once for the source-consuming verbs, then pick the feature module that owns a subverb.

`cli.dispatch` calls `run(args)` for every `brush` invocation. This package owns every `brush`
subverb; `run` returns the handler's exit code and hands nothing back (the `None` "not handled,
continue" sentinel is reachable only for a sub argparse cannot produce). Returning a value rather
than importing `cli.dispatch` keeps the forbidden inward edge out of the family (spec "Dependency
rules").

Two source guarantees this route owns:

- `build`, `intersect`/`deintersect`, and `clip` are STATELESS generators (T3D to stdout, no trunk):
  they are routed before any source resolution, matching their pre-move position ahead of the eager
  resolve in `cli.dispatch`.
- The other verbs consume the trunk source. The pre-move dispatch resolved it ONCE, before each
  verb's empty-stdin no-op and cheap argument checks; that order is behaviour, so this route owns
  the single `resolve_level_source` call and hands the source to the feature module. The owning
  module is imported BEFORE the resolution so it still loads when resolution refuses (no project ⇒
  `ProjectError`) — the import has no observable effect, and each subverb loading only its feature
  module (feature isolation) stays exact, proven by the fresh-process route matrix.
"""
from __future__ import annotations

from ... import level_sources


def run(args):
    """Route one `brush` invocation and return the handler's exit code. `None` (the dispatch "not
    handled, continue" sentinel) is returned only for a sub argparse cannot produce."""
    sub = args.sub
    if sub == "build":
        from . import build
        return build.run(args)
    if sub in ("intersect", "deintersect"):
        from . import edit
        return edit.merge(args)
    if sub == "clip":
        from . import edit
        return edit.clip(args)
    if sub == "poly":
        from . import poly as feature
    elif sub == "vertex":
        from . import vertex as feature
    elif sub in ("scale", "apply-transform", "replace"):
        from . import edit as feature
    else:
        return None
    src = level_sources.resolve_level_source(args)
    return feature.run(args, src)
