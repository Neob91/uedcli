"""`class` command-family parser registrar (module named `classes`; `class` is a keyword)."""
from __future__ import annotations

import argparse

from ._arguments import depth_value, parse_coord, _nonempty_class


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
    kcls = klist.add_mutually_exclusive_group()
    kcls.add_argument("--classified", action="store_true",
                      help="in the --flat list, keep ONLY classes that have a stored classification "
                           "shard (requires --flat — a tree can't be filtered this way; exit 2 "
                           "otherwise)")
    kcls.add_argument("--unclassified", action="store_true",
                      help="in the --flat list, keep ONLY classes with NO classification shard yet — "
                           "the worklist (requires --flat; exit 2 otherwise)")
    klist.add_argument("--json", action="store_true",
                       help="emit one JSON object per class (JSONL) instead of bare lines: "
                            "{ref, classified, preview} where preview is a cached thumbnail path or "
                            "null (list NEVER renders — it reports only an already-cached preview)")
    # `--all` was split (2026-07-18): --include-non-actor / --include-abstract / --depth all. Kept
    # hidden so it errors with a targeted pointer instead of an opaque argparse "unrecognized argument".
    klist.add_argument("--all", dest="legacy_all", action="store_true", help=argparse.SUPPRESS)
    kshow = ksub.add_parser(
        "show",
        help="print a class's OWN editable properties grouped by editor category (the UnrealEd "
             "property-browser view: Movement/Display/Lighting/…) + super chain + abstract/placeable, "
             "then a Facts block (DrawType, default Mesh, signed mesh-local extents, collision "
             "cylinder, PrePivot, parent). Non-editable internals hidden; inherited props collapse "
             "to per-category counts; --depth all lists every inherited prop too.")
    kshow.add_argument("fqcn", metavar="Package.Class", type=_nonempty_class,
                       help="fully-qualified class to describe, e.g. DeusEx.ammocrate")
    kshow.add_argument("--json", action="store_true",
                       help="print ONLY the file-facts as one JSON object (ref, drawtype, mesh, "
                            "extents, collision, prepivot, parent, abstract, placeable) instead of "
                            "the property schema. Extents are the default Mesh's signed mesh-local "
                            "bounding box in integer uu (Scale applied, pre-Origin/RotOrigin, "
                            "DrawScale not) — a SEATING/footprint fact; it does not assert world "
                            "facing. A non-mesh class reports mesh/extents as null. Also carries the "
                            "stored classification ({tags, description}) or null if unclassified.")
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

    kprev = ksub.add_parser(
        "preview",
        help="render a class's default Mesh as an orthographic PNG thumbnail (native software "
             "raster: decodes the mesh + P8 skins from the game .u — no editor, no game). The shot is "
             "in the SAME mesh-local frame as `class show`'s extents (Scale applied, pre-Origin/"
             "RotOrigin), iso (front-3/4) by default. Prints `<ref><TAB><path>` to stdout. A non-mesh "
             "class has nothing to render (a stderr note, exit 0); an unresolvable Mesh or an "
             "undecodable skin exits 2 naming it.")
    kprev.add_argument("fqcn", metavar="Package.Class", type=_nonempty_class,
                       help="fully-qualified class to preview, e.g. DeusEx.CrateUnbreakableLarge")
    kprev.add_argument("--rotate", type=parse_coord, default=None, metavar="PITCH,YAW,ROLL",
                       help="pose the mesh at this mesh-local FRotator (unreal rotator units, "
                            "16384 = 90deg, 65536 = a full turn) BEFORE the iso camera shoots it — the "
                            "pose oracle: preview a CANDIDATE placement rotation before committing it. "
                            "The reported azimuth reflects --rotate's yaw. Default: no pose (the "
                            "extents frame). Does NOT claim world facing (RotOrigin unreconciled).")
    kprev.add_argument("--size", type=int, default=512, metavar="PX",
                       help="output image edge length in pixels (default 512)")
    kprev.add_argument("--out", default=None, metavar="PATH",
                       help="host path to write the PNG to (relative -> cwd). Always a PNG: whatever "
                            "extension you give is replaced by .png. Optional: with no --out a unique "
                            "temp file (uedcli-class-preview-*.png) is created. The path is printed to "
                            "stdout after the ref.")
    kprev.add_argument("--json", action="store_true",
                       help="print one JSON object {ref, path, azimuth, rotate} instead of the "
                            "`<ref><TAB><path>` line — azimuth is the camera's mesh-local yaw in "
                            "unreal rotator units (65536 = 360deg), rotate the applied pose or null.")

    _register_classify(ksub)


def _csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


# The stored classification is what an LLM decides a class IS, handed back to the tool (the tool
# never infers it). One shard per class, git-tracked; tags + description only (no override field).
def _register_classify(ksub) -> None:
    kclass = ksub.add_parser(
        "classify",
        help="record / inspect what a class IS — the LLM's classification, stored one git-tracked "
             "shard per class (tags + description). The tool stores it, never infers it.")
    csub = kclass.add_subparsers(dest="csub", required=True)

    cset = csub.add_parser(
        "set",
        help="record a class's classification. tags UNION-merge on re-set (through a strip/lowercase/"
             "de-dupe normalizer); a DIFFERENT non-empty description exits 2 (pass --replace). The "
             "single token - reads JSONL rows {ref, tags, description} from stdin (validate-all-then-"
             "write; empty stdin is a clean no-op, exit 0).")
    cset.add_argument("ref", nargs="?", default=None, metavar="Package.Class",
                      help="the class to classify (fully qualified), or - to read JSONL rows from stdin")
    cset.add_argument("--tags", type=_csv, default=None, metavar="A,B",
                      help="comma list, UNION-merged onto the stored tags. A tag matching "
                           "`faces:AXIS` needs an axis token (+x -x +y -y +z -z); `mount:VALUE` needs "
                           "a non-empty value — shape is checked, meaning never is.")
    cset.add_argument("--description", default=None,
                      help="prose description. A DIFFERENT non-empty description exits 2 printing the "
                           "stored text unless --replace; identical text is a no-op.")
    cset.add_argument("--replace", action="store_true",
                      help="overwrite a conflicting stored description instead of exiting 2 "
                           "(also governs each JSONL row under -).")

    cunset = csub.add_parser(
        "unset",
        help="undo classification on one or more classes. Exactly one of --tags[=A,B] / --description "
             "/ --all. The single token - reads a newline-separated ref list from stdin (empty stdin "
             "is a clean no-op, exit 0).")
    cunset.add_argument("refs", nargs="*", metavar="Package.Class",
                        help="class(es) to unset, or - to read a newline ref list from stdin")
    cg = cunset.add_mutually_exclusive_group(required=True)
    cg.add_argument("--tags", type=_csv, nargs="?", const=[], default=None, metavar="A,B",
                    help="remove the named tags (comma list); BARE --tags clears the whole tags field")
    cg.add_argument("--description", action="store_true", help="clear the description field")
    cg.add_argument("--all", dest="clear_all", action="store_true",
                    help="delete the whole shard (the only full clear)")

    cstat = csub.add_parser(
        "status", help="classification progress: how many classes on the path have a shard, of the "
                       "total. --json for a machine object.")
    cstat.add_argument("--json", action="store_true", help="emit one JSON object instead of a line")

    ctags = csub.add_parser(
        "tags", help="the tag vocabulary in use across all shards, with occurrence counts (curbs "
                     "drift). --json for a machine object.")
    ctags.add_argument("--json", action="store_true", help="emit one JSON object instead of lines")
