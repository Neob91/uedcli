"""`actor preview` — model-only, host-side still shots of actors (no editor, no container).

Two forms, one entry:

- `--from-t3d <FILE…|->` renders the actors in a T3D snippet with NO level. Its no-source guard runs
  before any source resolution, so it never touches `$UEDCLI_LEVEL` (pinned by `test_ordering_baseline`).
- Otherwise it resolves the trunk level source, reads the requested names and renders them. The
  source is resolved before the empty-stdin no-op, matching the pre-move order.

The shared render machinery (world bounds, highlight/focus/frame interpretation, PNG write) lives in
`cli.rendering`; this module only selects the actors and hands them over.
"""
from __future__ import annotations

import sys

from ... import ingest, level_sources, rendering, targets
from ...errors import CommandError
from .... import query, trunk
from ....model import parse_t3d_actors


def run(args) -> int:
    """`actor preview` entry. Dispatch routes every `actor preview` here."""
    if getattr(args, "from_t3d", None):
        return _from_t3d(args)
    # Every non-T3D preview resolves the trunk level source first — before the empty-stdin no-op, so
    # the resolution order matches the pre-move dispatch flow (no project ⇒ clean exit 2).
    src = level_sources.resolve_level_source(args)
    if not args.names:                                      # no names AND no `-`: nothing to render
        raise CommandError(
            "actor preview: no actors to render — pass names or - (a piped set)")
    raw = targets.resolve_target_names(args.names)         # `-` → names from stdin (spec §1)
    if not raw:
        return 0                                            # `-` with empty stdin: no-op, exit 0
    level = src.load()
    try:
        names = query.resolve_actor_names(level, raw)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    actors = [level.actors[n] for n in names]
    return rendering.render_actors_to_out(actors, args)


def _from_t3d(args) -> int:
    """`actor preview --from-t3d <FILE…|->` — render every actor in the given snippet(s), NO level
    required. Multiple files concatenate in order; duplicate Names are uniquified so all render."""
    if args.names:
        raise CommandError("--from-t3d is mutually exclusive with actor names (T3D mode "
                             "renders every actor in the snippet)")
    parsed = parse_t3d_actors(ingest.read_t3d_files(args.from_t3d))
    seen: set[str] = set()
    for a in parsed:
        if a.name in seen:
            a.name = trunk.alloc_name(a.name.rstrip("0123456789") or a.name, seen)
        seen.add(a.name)
    return rendering.render_actors_to_out(parsed, args)
