"""`actor survey NAME` — every raw and CSG-resolved spatial fact about one actor.

Resolves its own source, class index and class defaults the way every actor feature module does
(`preview.py` is the closest analog: it also drives a native CSG solve). Every failure mode is
mapped to exit 2 with a message naming the offending value — never a traceback (`CLAUDE.md`).
"""
from __future__ import annotations

import sys

from ... import level_sources, resources
from ...errors import CommandError
from .... import actor_survey, actorgraph, uprops
from ....classdefaults import ClassDefaults
from ....preview_native import NativePreviewError


def run(args) -> int:
    """`actor survey` entry. Dispatch routes every `actor survey` here."""
    project = resources.resolve_project(args)
    src = level_sources.resolve_level_source(args)
    index = resources.mover_index(args, "actor survey", project)
    level = src.load()
    try:
        # The `SchemaError` caught below is raised by `defaults.for_class(...)` inside `survey`, not
        # by `schema_resolver_for` — that one returns a resolver over an empty search path rather
        # than raising (`packages.schema_search_dirs`). Catching it here instead of letting
        # `dispatch.py`'s generic `except SchemaError` (dispatch.py:69) take it is what puts the
        # surveyed actor's name in the message.
        defaults = ClassDefaults(resources.schema_resolver_for(project))
        result = actor_survey.survey(level, index, args.name, defaults)
    except actor_survey.ActorNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except actorgraph.DegenerateBrushError as e:
        print(f"actor survey: {e}", file=sys.stderr)
        return 2
    except actor_survey.ActorHasNoLocationError as e:
        print(f"actor survey: {e}", file=sys.stderr)
        return 2
    except actor_survey.CollisionPropertyError as e:
        print(f"actor survey: {e}", file=sys.stderr)
        return 2
    except uprops.SchemaError as e:
        raise CommandError(
            f"actor survey: cannot resolve a class schema while surveying {args.name!r} — the "
            f"collision gate needs it ({e}). Qualify the class as Package.Class and put its "
            f"package on the project's search paths") from None
    except NativePreviewError as e:
        raise CommandError(f"actor survey: {e}") from None
    for _bad_name, reason in result.skipped:
        print(f"actor survey: skipping {reason}", file=sys.stderr)
    for line in actor_survey.format_lines(result):
        print(line)
    if result.warning:
        print(result.warning, file=sys.stderr)
    print(f"actor survey: {len(result.raw)} raw fact(s), {len(result.csg)} resolved CSG fact(s) "
          f"for {args.name}", file=sys.stderr)
    return 0
