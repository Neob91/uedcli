"""Actor-family route: run the source-free guards, then pick the feature module that owns a subverb.

`cli.dispatch` calls `run(args)` for every `actor` invocation. This package owns every `actor`
subverb; `run` returns the handler's exit code and hands nothing back (the `None` "not handled,
continue" sentinel is reachable only for a sub argparse cannot produce). Returning a value rather
than importing `cli.dispatch` keeps the forbidden inward edge out of the family (spec "Dependency
rules").

Two source-free guarantees this route owns, both proven by fresh-process ordering tests:

- The trunk-only surface guards (`_apply_source_free_guards`) reject `--tree stash|prefab` for
  folder/label/order surfaces BEFORE any feature module resolves a project or ambient level — so a
  non-default `actor add --order` against a stash/prefab target fails without touching the trunk.
- `actor diagram` is routed here before the guards' peers resolve a source; its own `--from-t3d`
  no-source guard then runs inside `preview.run`, so T3D-only diagram never touches `$UEDCLI_LEVEL`.

To keep each subverb's feature module off the import path of the others, the owning module is
imported only inside the branch that selects it (feature isolation, proven by fresh-process route
tests). `actor build` is a stateless generator, routed first so it never runs the source-free guards
(they are no-ops for it) — matching its pre-move position ahead of the guard block in `cli.dispatch`.
"""
from __future__ import annotations

from ._guards import (reject_nonlevel_target_for_folders, reject_nonlevel_target_for_labels,
                      reject_nonlevel_target_for_order)


def run(args):
    """Route one `actor` invocation. Runs the source-free guards, then dispatches the subverb to its
    feature module and returns the handler's exit code. Every `actor` subverb is owned here now, so
    `None` (the dispatch "not handled, continue" sentinel) is returned only for a sub argparse cannot
    produce."""
    if args.sub == "build":
        from . import build
        return build.run(args)
    _apply_source_free_guards(args)
    if args.sub == "diagram":
        from . import preview
        return preview.run(args)
    if args.sub in ("find", "show", "bbox"):
        from . import query
        return query.run(args)
    if args.sub == "folder":
        from . import folder
        return folder.run(args)
    if args.sub == "label":
        from . import label
        return label.run(args)
    if args.sub == "prop":
        from . import prop
        return prop.run(args)
    if args.sub in ("add", "duplicate", "order", "delete", "move", "rotate"):
        from . import edit
        return edit.run(args)
    return None


def _apply_source_free_guards(args) -> None:
    """Reject `--tree stash|prefab` for the trunk-only folder/label/order surfaces, BEFORE any
    feature module resolves a project or ambient level (so the message is the right one and no
    stash/prefab source is ever loaded for a surface it cannot hold). `--tree level/NAME` is fine —
    these fire only on stash/prefab."""
    sub = args.sub
    # Folders are trunk-only (spec §4): `actor folder …` always; `actor find --folder/--no-folder`
    # when a folder surface is used.
    if sub == "folder":
        reject_nonlevel_target_for_folders(args)
    if sub == "find" and (getattr(args, "folder", None) or getattr(args, "no_folder", False)):
        reject_nonlevel_target_for_folders(args)
    # Labels are trunk-only this slice (plan scope-cut): `actor label …` always; `actor find
    # --label/--no-label` and `actor add --label` when a label surface is actually used.
    if sub == "label":
        reject_nonlevel_target_for_labels(args)
    if sub == "find" and (getattr(args, "label", None) or getattr(args, "no_label", False)):
        reject_nonlevel_target_for_labels(args)
    if sub == "add" and getattr(args, "label", None):
        reject_nonlevel_target_for_labels(args)
    # `duplicate` ALWAYS mints a fresh dup-<rand> batch label, and the stash/prefab box save carries
    # no labels channel (deferred scope-cut) — so it rejects stash/prefab UNCONDITIONALLY (not only
    # with an explicit --label), else the batch label would silently vanish on a box save.
    if sub == "duplicate":
        reject_nonlevel_target_for_labels(args)
    # `is not None` (not truthiness) so `--folder ""` still routes to the folder-guard message on a
    # stash/prefab target (it's still an invalid path — validate_folder_path rejects it later). The
    # CARRIER path (an incoming `// uedcli-folder:` with no explicit --folder) is guarded separately
    # in the add/duplicate ingest, where the parsed folders are known (review 2026-07-18).
    if sub in ("add", "duplicate") and getattr(args, "folder", None) is not None:
        reject_nonlevel_target_for_folders(args)
    # CSG ordering is trunk-only too (spec §7). `actor order` always; `actor add --order` only when a
    # non-default placement is requested (`last` == today's append, valid on any target).
    if sub == "order":
        reject_nonlevel_target_for_order(args)
    if sub == "add" and (getattr(args, "order", "last") or "last").strip().casefold() != "last":
        reject_nonlevel_target_for_order(args)
