"""`class` command-family parser registrar (module named `classes`; `class` is a keyword)."""
from __future__ import annotations

import argparse

from ._arguments import depth_value, _nonempty_class


def register(sub) -> None:
    klass = sub.add_parser(
        "class",
        help="discover the substrate's actor classes and their property schemas (offline; reads the "
             "game's own .u packages — no editor, no level needed)")
    ksub = klass.add_subparsers(dest="sub", required=True)
    klist = ksub.add_parser(
        "list",
        help="browse actor classes as an indented inheritance TREE (rooted at Engine.Actor; abstract "
             "classes marked *; a collapsed node shows its hidden direct-subclass count as (N)). Depth "
             "auto-fits ~60 lines; --depth to go deeper, --subclass-of to reroot, --flat for a "
             "pipeable one-per-line list.")
    klist.add_argument("--flat", action="store_true",
                       help="print a flat one-Package.Class-per-line list instead of the tree (the "
                            "pipeable form: DEFAULT = the ~40 top-level categories; --subclass-of "
                            "drills to placeable leaves; --package/--depth as documented below)")
    klist.add_argument("--package", default=None,
                       help="restrict to this package (bare stem, e.g. DeusEx): in the tree, prune to "
                            "its classes + the branches reaching them; with --flat, list its classes")
    klist.add_argument("--subclass-of", dest="subclass_of", default=None, metavar="Package.Class",
                       help="reroot: the tree (or, with --flat, the placeable-leaf list) of classes "
                            "that are, or descend from, this base (e.g. --subclass-of Engine.Mover)")
    klist.add_argument("--depth", type=depth_value, default=None, metavar="N|all",
                       help="tree/browse depth below the SHOWN root: N levels (overrides the auto "
                            "~60-line fit), or `all` for the WHOLE tree (unlimited, no (N) collapse). "
                            "Counts from the --subclass-of root when given, else Engine.Actor. "
                            "--depth 1 = that root's direct children; --depth 0 = the root only.")
    klist.add_argument("--include-non-actor", dest="include_non_actor", action="store_true",
                       help="also list non-Actor classes (Object, Texture, Sound, field/property "
                            "classes) by rerooting the tree/flat root at Core.Object. Default scope is "
                            "Actor subclasses only. No-op with --subclass-of (which sets the root).")
    klist.add_argument("--include-abstract", dest="include_abstract", action="store_true",
                       help="in the --flat --subclass-of drill and the --package flat list, ALSO show "
                            "abstract / non-placeable classes (hidden there by default). REJECTED "
                            "(exit 2) anywhere it can't act — the tree, the bare category view, or a "
                            "--depth browse — which already show abstract (branch-points marked *).")
    # `--all` was split (2026-07-18): --include-non-actor / --include-abstract / --depth all. Kept
    # hidden so it errors with a targeted pointer instead of an opaque argparse "unrecognized argument".
    klist.add_argument("--all", dest="legacy_all", action="store_true", help=argparse.SUPPRESS)
    kshow = ksub.add_parser(
        "show",
        help="print a class's OWN editable properties grouped by editor category (the UnrealEd "
             "property-browser view: Movement/Display/Lighting/…) + super chain + abstract/placeable. "
             "Non-editable internals hidden; inherited props collapse to per-category counts; "
             "--depth all lists every inherited prop too.")
    kshow.add_argument("fqcn", metavar="Package.Class", type=_nonempty_class,
                       help="fully-qualified class to describe, e.g. DeusEx.ammocrate")
    kshow.add_argument("--depth", type=depth_value, default=None, metavar="N|all",
                       help="how many superclass levels of inherited props to include: N (1 = the "
                            "immediate parent; 0 = own props only) or `all` for the WHOLE super chain. "
                            "Passing --depth switches to the EXPANDED view (own + inherited per "
                            "category, inherited tagged with their source class). --category also "
                            "expands the whole chain.")
    kshow.add_argument("--category", dest="categories", action="append", default=[], metavar="NAME",
                       help="show ONLY this editor category (e.g. Movement, Lighting), EXPANDED (own + "
                            "inherited props, inherited tagged with their source class) — repeat to OR "
                            "several. Exact, case-insensitive. Like --depth all this expands the whole "
                            "chain (unlimited superclass depth); --depth N still clips it. An unknown "
                            "category exits 2, listing the class's categories.")
    # `--all` was renamed to `--depth all` (2026-07-18). Hidden so it errors with a pointer.
    kshow.add_argument("--all", dest="legacy_all", action="store_true", help=argparse.SUPPRESS)
