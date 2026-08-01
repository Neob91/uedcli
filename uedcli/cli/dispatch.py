"""The CLI process boundary. `_dispatch` routes each verb to the selected command family with a
function-local import (so invoking one family loads no other), and `dispatch` wraps it in the ordered
process-error guard that turns every expected failure into a clean exit-2 message rather than a
traceback. All command behavior lives in `cli.commands.<family>`; this module owns only routing and
that guard.

To preserve the guard's ordered catch it imports the error owners at module scope (spec "Dependency
rules" rule 6): `cli.errors`, `config.ConfigError`, `model.CoordinateError`, `geometry.GeometryError`,
`driver.DriverError`, `classindex.ClassRefError`, `uprops.SchemaError`, `schema_cache.CacheWriteError`.
"""
from __future__ import annotations

import os
import sys

from ..classindex import ClassRefError
from ..config import ConfigError
from ..driver import DriverError            # DriverError → top-level clean-exit catch (no traceback)
from ..geometry import GeometryError
from ..model import CoordinateError
from ..schema_cache import CacheWriteError
from ..uprops import SchemaError
from .errors import CommandError, ProjectError


def dispatch(args) -> int:
    try:
        return _dispatch(args)
    except CommandError as e:                            # command + project + level-selection errors
        print(e.message, file=sys.stderr)                # (ProjectError and LevelSelectionError subclass it)
        return 2
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2
    except CoordinateError as e:
        # A coordinate that cannot be written as T3D at all (non-finite, or past emit.MAX_COORD).
        # Raised from the single write path, so it covers every generator and every mutating verb
        # rather than one flag on one shape.
        print(f"invalid coordinate: {e}", file=sys.stderr)
        return 2
    except GeometryError as e:
        # Degenerate/invalid brush geometry from a model-side verb (actor add, brush clip/vertex,
        # mover key, the brush builders, stash/prefab apply) — the message carries a precise per-poly
        # diagnostic; surface it, never a traceback. (`level materialize` catches its own build-time
        # GeometryError locally with a "materialize failed" message.)
        print(f"invalid brush geometry: {e}", file=sys.stderr)
        return 2
    except (DriverError, TimeoutError) as e:
        # Any editor-driving verb (level materialize/preview) whose ephemeral editor is wedged or
        # crashes mid-drive → clean error, never a traceback. (`EditorNotReadyError` subclasses
        # TimeoutError, so a startup death lands here too.)
        print(f"editor error: {e}", file=sys.stderr)
        return 2
    except ClassRefError as e:
        # An unknown/ambiguous class ref reached the top level (a `class` verb or an ingest gate that
        # didn't translate it locally) → clean exit 2, never a traceback.
        print(str(e), file=sys.stderr)
        return 2
    except SchemaError as e:
        # A `.u` layout desync (a corrupt package on the path) surfacing from a class/schema read —
        # the corrupt-package backstop so it never tracebacks (dispatch did NOT catch this before).
        print(f"schema error: {e}", file=sys.stderr)
        return 2
    except CacheWriteError as e:
        # The persistent schema cache is unwritable (classically a root-owned ~/.uedcli/cache from a
        # container run). Surfaced with an actionable fix, never swallowed — a dead cache otherwise
        # re-decodes every package every run with no hint why (2026-07-18). The message is
        # self-contained (chown hint + UEDCLI_SCHEMA_CACHE=off escape hatch).
        print(str(e), file=sys.stderr)
        return 2
    except BrokenPipeError:
        # stdout consumer went away (`uedcli … | head`) — the conventional silent exit, not an
        # error. Detach stdout so the interpreter's shutdown flush can't re-raise into noise.
        sys.stdout = open(os.devnull, "w")
        return 0
    except OSError as e:
        # Filesystem backstop (read-only checkout, a managed-dir key pointing at a file, a full
        # disk, …): the message names the path; a raw PermissionError/NotADirectoryError traceback
        # must never reach the user (review fix, 2026-07-18). Ordered AFTER TimeoutError (an
        # OSError subclass) so editor timeouts keep their specific message.
        print(f"filesystem error: {e}", file=sys.stderr)
        return 2


def _dispatch(args) -> int:
    # --- class group: offline class discovery (no editor, no ambient level needed) ---
    if args.cmd == "class":
        from .commands import classes as classes_cmd
        return classes_cmd.run(args)

    # --- docs group: uedcli's own user documentation (no editor, no project, no level) ---
    if args.cmd == "docs":
        from .commands import docs as docs_cmd
        return docs_cmd.run(args)

    # --- level group ---
    if args.cmd == "level":
        from .commands import level as level_cmd
        return level_cmd.run(args)

    # --- event group: read-only Tag<->Event wiring analysis over the current level (no editor) ---
    if args.cmd == "event":
        from .commands import event as event_cmd
        return event_cmd.run(args)

    # --- project group: read-only project/search-path diagnostic (no ambient level needed) ---
    if args.cmd == "project" and args.sub == "show":
        from .commands import project as project_cmd
        return project_cmd.run(args)

    # --- stash group: model-side register (capture/show/list/drop), no editor ---
    if args.cmd == "stash":
        from .commands import stash as stash_cmd
        return stash_cmd.run(args)

    # Brush family route: `cli.commands.brush` owns the whole family — the stateless build/merge
    # generators (routed source-free, before the eager level-source resolution below) and the
    # source-consuming poly/vertex/scale/apply-transform/clip/replace verbs (the route resolves the
    # single trunk source itself, in the pre-move order). `routes.run` returns `None` only for a sub
    # argparse can't produce, so the guard below is defensive.
    if args.cmd == "brush":
        from .commands.brush import routes as brush_routes
        handled = brush_routes.run(args)
        if handled is not None:
            return handled

    # --- prefab group: tier-2 library. Reads touch only the tracked dir; `prefab apply`
    # resolves its own trunk level source inside the family's `run`. ---
    if args.cmd == "prefab":
        from .commands import prefab as prefab_cmd
        return prefab_cmd.run(args)

    # --- texture group: substrate utility — pure offline UCC batchexport, no live editor,
    # no model touch. ---
    if args.cmd == "texture":
        from .commands import texture as texture_cmd
        return texture_cmd.run(args)
    if args.cmd == "substrate":
        from .commands import substrate as substrate_cmd
        return substrate_cmd.run(args)
    if args.cmd == "cache":
        from .commands import cache as cache_cmd
        return cache_cmd.run(args)

    # Actor family route: `cli.commands.actor` owns the whole family — the source-free trunk-only
    # surface guards (folder/label/order rejection of `--tree stash|prefab`), the stateless `build`
    # generator, `actor preview` (incl. the `--from-t3d` no-source guard), and every feature verb.
    # Entering here, before the eager level-source resolution below, keeps every source-free
    # guarantee; each feature module resolves its own source when it needs one. `routes.run` returns
    # `None` only for a sub argparse can't produce, so the guard below is defensive.
    if args.cmd == "actor":
        from .commands.actor import routes as actor_routes
        handled = actor_routes.run(args)
        if handled is not None:
            return handled

    # Mover family route: `cli.commands.mover` owns the family — it resolves its own trunk source
    # (the ambient $UEDCLI_LEVEL; no project ⇒ a clean `ProjectError`, not a traceback). `run`
    # returns `None` only for a sub argparse can't produce, so the fallback below is defensive.
    if args.cmd == "mover":
        from .commands import mover as mover_cmd
        handled = mover_cmd.run(args)
        if handled is not None:
            return handled

    print(f"unhandled verb: {args.cmd}/{getattr(args, 'sub', '')}", file=sys.stderr)
    return 2
