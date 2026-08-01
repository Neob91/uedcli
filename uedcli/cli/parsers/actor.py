"""`actor` command-family parser registrar."""
from __future__ import annotations

from decimal import Decimal

from ._arguments import (
    _nonempty,
    _nonempty_class,
    parse_bbox,
    parse_coord,
    _preview_opts,
    _tree_flag,
)


def register(sub) -> None:
    actor = sub.add_parser("actor", help="actor query/mutate verbs")
    asub = actor.add_subparsers(dest="sub", required=True)

    find = asub.add_parser(
        "find",
        help="print names of matching actors (one per line) for piping into name-taking verbs; "
             "with no filters, prints every actor")
    find.add_argument(
        "--exact-class", dest="cls", action="append", default=[], type=_nonempty_class,
        metavar="C",
        help="match actors whose class is EXACTLY C (bare or fully-qualified Package.Name, "
             "case-insensitive) — does NOT include subclasses (`--exact-class Light` skips "
             "Spotlight); use --subclass-of for descendant-aware matching. Repeat to OR classes")
    find.add_argument(
        "--subclass-of", dest="subclass_of", action="append", default=[], type=_nonempty_class,
        metavar="C",
        help="match actors whose class IS C or DESCENDS from it (e.g. --subclass-of Engine.Light "
             "also matches Spotlight, TriggerLight, …) — the descendant-aware class filter, matching "
             "`class list --subclass-of`'s spelling. Needs the class schema (the game .u install). "
             "Repeat to OR multiple bases; ORs with --exact-class")
    find.add_argument(
        "--group", dest="group", action="append", default=[], type=_nonempty,
        metavar="G",
        help="match actors that are members of group G (case-insensitive, comma-joined "
             "groups are split — repeat to OR multiple groups)")
    find.add_argument(
        "--name", dest="name", action="append", default=[], type=_nonempty,
        metavar="GLOB",
        help="match actors whose Name matches the fnmatch glob GLOB (case-insensitive, "
             "whole-name anchored — use wildcards for prefix/substring, e.g. 'Helper*'); "
             "repeat to OR multiple patterns")
    find.add_argument(
        "--prop", dest="prop", action="append", default=[], type=_nonempty,
        metavar="KEY[.PATH]=VALUE",
        help="match actors on the EFFECTIVE value of KEY (dot-paths reach array elements and "
             "struct members, e.g. Location.X=512): the stored value if present, else the "
             "class default decoded from the game packages; comparison is type-aware (True==1, "
             "4==4.0, enum name==ordinal). An actor whose class does not declare KEY simply "
             "does not match; a KEY no considered class declares errors. Needs the class "
             "schema (the game .u install). Repeat to AND multiple props")
    find.add_argument(
        "--within-bbox", dest="within_bbox", default=None, type=parse_bbox,
        metavar="X0,Y0,Z0,X1,Y1,Z1",
        help="match actors whose world bounding box is FULLY INSIDE the given axis-aligned box — two "
             "opposite corners in any order, unreal units (same space as --at), edge-inclusive. "
             "Honours each actor's full transform (a scaled/rotated brush's TRUE world box is tested); "
             "a point actor (Light, mesh deco, nav point) is its Location point. Single-valued; ANDs "
             "with the other filters. Selects a region's actors to pipe into a set verb (add --kind "
             "brush for geometry only, e.g. `… --within-bbox … --kind brush | actor preview -`). "
             "(A looser 'also catch straddling brushes' variant, --overlapping-bbox, does not "
             "exist yet.)")
    find.add_argument(
        "--kind", choices=["point", "brush"], default=None,
        help="Filter by actor kind: 'brush' = actors that carry brush geometry (a PolyList — "
             "CSG brushes, builders, movers; the ones brush/poly/vertex verbs accept); "
             "'point' = location-only actors with no brush (Light, LevelInfo, navigation points, "
             "AND mesh decorations — a mesh deco has visible geometry but is still a point actor). "
             "This is the brush-vs-point split, not 'has any geometry'. Distinct from "
             "--exact-class/--subclass-of, which match the UnrealScript class name. Omit to match "
             "both kinds.")
    fldg = find.add_mutually_exclusive_group()
    fldg.add_argument(
        "--folder", dest="folder", action="append", default=[], type=_nonempty, metavar="PATTERN",
        help="match actors by uedcli-side folder (globstar): a WILDCARD-FREE pattern like 'castle' "
             "selects that folder AND its WHOLE SUBTREE (so bare = subtree — there is no short form "
             "for 'just the castle node'); '*' = exactly one segment; '**' = any depth (zero+). NOTE "
             "the subtree/glob asymmetry: a WILDCARDED pattern is a pure glob with NO subtree "
             "extension — '**.roof' matches roof NODES only, not their contents (use "
             "--folder '**.roof' --folder '**.roof.**' for 'every roof and everything inside'). "
             "Case-insensitive; '?'/'['/']' are rejected. Repeat to OR patterns; ANDs with "
             "--exact-class/--subclass-of/--group/--name/--kind")
    fldg.add_argument(
        "--no-folder", dest="no_folder", action="store_true",
        help="match only UNFOLDERED actors (folder unset) — the ONLY way to query them, since a "
             "None folder matches no --folder pattern. Mutually exclusive with --folder")
    lblg = find.add_mutually_exclusive_group()
    lblg.add_argument(
        "--label", dest="label", action="append", default=[], type=_nonempty, metavar="GLOB",
        help="match actors by uedcli-side label (flat `*`-glob): an actor matches if ANY of its "
             "labels matches GLOB. `*` is the ONLY wildcard ('dup-*' finds a duplicate batch, "
             "'lighting' matches that exact label); '?'/'['/']' are rejected. Case-insensitive. "
             "Repeat to OR patterns; ANDs with --exact-class/--subclass-of/--group/--name/--kind/"
             "--folder")
    lblg.add_argument(
        "--no-label", dest="no_label", action="store_true",
        help="match only UNLABELLED actors (empty label set) — the ONLY way to query them, since an "
             "unlabelled actor matches no --label pattern. Mutually exclusive with --label")
    find.add_argument(
        "--json", action="store_true",
        help="print the matching names as a JSON array instead of one name per line "
             "(for scripts that want structured output)")
    find.add_argument(
        "restrict", nargs="?", default=None, metavar="-",
        help="the single token - reads a newline-separated actor-name list from stdin and uses THAT "
             "set as the universe `find` searches (the filters become a predicate over it): "
             "`actor find --group A | actor find --group B -` = A AND B. Omit to search the whole tree.")
    find.add_argument(
        "--exclude", action="store_true",
        help="with -, keep the piped actors that do NOT match the filters instead of those that do "
             "(set difference): `find --group A | find --group B --exclude -` = A but not B. "
             "Requires -.")
    _tree_flag(find)

    show = asub.add_parser("show", help="print named actors' full T3D blocks")
    show.add_argument("name",
                      help="ONE actor Name (case-insensitive; NOT a glob — `actor find` owns "
                           "patterns), or - to read a newline-separated name list from stdin "
                           "(e.g. `actor find 'Light*' | actor show -`; concatenated blocks in "
                           "piped order). A name that matches no actor errors (exit 2); empty "
                           "stdin is a clean no-op (exit 0)")
    show.add_argument("--t3d-only", dest="t3d_only", action="store_true",
                      help="suppress the `// uedcli-folder:` comment for a byte-exact editor export "
                           "(rarely needed). By DEFAULT each foldered block carries the comment — "
                           "importable into UnrealEd unchanged (it silently strips bare `//` lines) "
                           "AND round-trips the folder through `actor show A | actor add -`")
    _tree_flag(show)      # read a named tree explicitly instead of $UEDCLI_LEVEL

    dup = asub.add_parser(
        "duplicate",
        help="copy one or more actors (sugar for `actor show <names> | actor add -`): each copy "
             "gets a fresh Name, is appended last in CSG order, INHERITS its source's labels, and "
             "additionally gets one fresh `dup-<rand>` batch label (so the whole copied batch is "
             "re-addressable via `actor find --label dup-<rand>`). A placement is REQUIRED (--by or "
             "--at) so copies never silently overlap their originals. Prints the allocated Names to "
             "stdout (one per line); the count + batch label go to stderr")
    dup.add_argument("names", nargs="+",
                     help="actor Names (case-insensitive) to duplicate, or the single token - to "
                          "read a newline-separated name list from stdin (e.g. `actor find … | "
                          "actor duplicate -`); - is the sole source, not mixable with names")
    dupg = dup.add_mutually_exclusive_group(required=True)
    dupg.add_argument("--by", type=parse_coord, metavar="DX,DY,DZ",
                      help="world delta added to EACH copy's Location (relative offset; preserves "
                           "the set's relative layout)")
    dupg.add_argument("--at", type=parse_coord, metavar="X,Y,Z",
                      help="anchor the copied set's bounding-box minimum corner at this world "
                           "coordinate (the whole set shifts together, preserving relative layout)")
    dup.add_argument("--label", action="append", default=[], type=_nonempty, metavar="L",
                     help="an extra label token stamped on every copy IN ADDITION to the inherited "
                          "labels and the fresh dup-<rand> batch token; repeat for many")
    dup.add_argument("--folder", default=None, metavar="PATH",
                     help="place the copies in this uedcli-side folder path (overrides each "
                          "original's folder); omit to keep each original's folder")
    _tree_flag(dup)       # duplicate within a named tree (defaults to $UEDCLI_LEVEL)


    folder = asub.add_parser(
        "folder",
        help="manage an actor's uedcli-side FOLDER: a hierarchical dotted organization path "
             "(castle.tower.roof) stored in a trunk sidecar — NOT the T3D Group prop, never emitted "
             "to the built map. Sub-verbs: set / unset / get")
    fsub = folder.add_subparsers(dest="foldersub", required=True)
    _NAMES_OR_STDIN = ("actor Names (case-insensitive), or the single token - to read a "
                       "newline-separated name list from stdin (e.g. `actor find … | actor folder "
                       "set --to a.b -`); - is the sole source, not mixable with names")
    fset = fsub.add_parser("set", help="assign a folder path to one or more actors (validate-all "
                                       "before any write; all sidecars land or none do). Echoes "
                                       "touched Names to stdout")
    fset.add_argument("--to", required=True, metavar="PATH",
                      help="the dotted folder path to assign, e.g. castle.tower.roof — segments are "
                           "[A-Za-z0-9_+-], separated by '.', each non-empty; stored as authored "
                           "(case preserved), matched case-insensitively")
    fset.add_argument("names", nargs="+", help=_NAMES_OR_STDIN)
    _tree_flag(fset)
    funset = fsub.add_parser("unset", help="clear the folder (remove the sidecar file) on one or "
                                           "more actors. Echoes touched Names to stdout")
    funset.add_argument("names", nargs="+", help=_NAMES_OR_STDIN)
    _tree_flag(funset)
    fget = fsub.add_parser("get", help="print each actor's folder path, one line per actor in "
                                       "argument order; an unfoldered actor prints `(none)`")
    fget.add_argument("names", nargs="+", help=_NAMES_OR_STDIN)
    fget.add_argument("--json", action="store_true",
                      help="emit a JSON object mapping each canonical actor Name to its folder path "
                           "(an unfoldered actor maps to null, not the literal `(none)` string) — "
                           "for scripts that would otherwise choke on the sentinel")
    _tree_flag(fget)

    label = asub.add_parser(
        "label",
        help="manage an actor's uedcli-side LABELS: a flat, multi-valued set of classification "
             "tokens (lighting, flammable, dup-a1f) stored in a trunk sidecar — orthogonal to the "
             "FOLDER path, the T3D Group prop, and the T3D Tag prop, never emitted to the built "
             "map. Sub-verbs: add / remove / clear / get. Level-only (rejects --tree stash|prefab)")
    lsub2 = label.add_subparsers(dest="labelsub", required=True)
    _LABEL_NAMES_OR_STDIN = ("actor Names (case-insensitive), or the single token - to read a "
                             "newline-separated name list from stdin (e.g. `actor find … | actor "
                             "label add --label lit -`); - is the sole source, not mixable with names")
    _LABEL_HELP = ("a label token to add/remove: [A-Za-z0-9_+-], no '.', no leading '-'; stored as "
                   "authored (case preserved), matched case-insensitively. Repeat --label for many")
    ladd = lsub2.add_parser("add", help="add label(s) to one or more actors (set union; adding a "
                                        "present label is a no-op). Validate-all before any write; "
                                        "echoes touched Names to stdout")
    ladd.add_argument("--label", action="append", default=[], type=_nonempty, metavar="L",
                      help=_LABEL_HELP)
    ladd.add_argument("names", nargs="+", help=_LABEL_NAMES_OR_STDIN)
    _tree_flag(ladd)
    lrem = lsub2.add_parser("remove", help="remove label(s) from one or more actors (set difference; "
                                           "an absent label is a no-op). Echoes touched Names to stdout")
    lrem.add_argument("--label", action="append", default=[], type=_nonempty, metavar="L",
                      help=_LABEL_HELP)
    lrem.add_argument("names", nargs="+", help=_LABEL_NAMES_OR_STDIN)
    _tree_flag(lrem)
    lclr = lsub2.add_parser("clear", help="remove ALL labels (delete the sidecar) on one or more "
                                          "actors. Echoes touched Names to stdout")
    lclr.add_argument("names", nargs="+", help=_LABEL_NAMES_OR_STDIN)
    _tree_flag(lclr)
    lget = lsub2.add_parser("get", help="print each actor's labels, one line per actor in argument "
                                        "order as `Name<TAB>l1,l2` (sorted, comma-joined); an "
                                        "unlabelled actor prints `Name<TAB>(none)`")
    lget.add_argument("names", nargs="+", help=_LABEL_NAMES_OR_STDIN)
    lget.add_argument("--json", action="store_true",
                      help="emit a JSON object mapping each canonical actor Name to its sorted list "
                           "of labels (an unlabelled actor maps to []) — for scripts")
    _tree_flag(lget)

    abuild = asub.add_parser("build",
                             help="build a point actor T3D and write to stdout (stateless; no level needed)")
    abuild.add_argument("aclass", metavar="Package.Class",
                        help="fully-qualified actor class, e.g. Engine.Light")
    abuild.add_argument("--at", type=parse_coord, default=(Decimal(0), Decimal(0), Decimal(0)),
                        metavar="X,Y,Z", help="world Location (default origin)")
    abuild.add_argument("--base-name", dest="base_name", default=None,
                        help="base Name (stem) for the emitted actor; a unique `_<rand>` suffix is "
                             "appended at `actor add`, so this is a prefix, not the final Name "
                             "(default: the class name, e.g. Light). Give distinct base names when "
                             "batching several `actor build`s so `actor add` keeps them all.")
    abuild.add_argument("--prop", action="append", default=[],
                        metavar="KEY[.PATH]=VALUE",
                        help="extra actor property (repeat for multiple), schema-validated "
                             "against the class before emit — same grammar as `actor prop set` "
                             "(dot-paths, array tuple form, Vector/Rotator comma sugar); "
                             "member edits compose onto the class default")
    abuild.add_argument("--rotate", type=parse_coord, default=None, metavar="PITCH,YAW,ROLL",
                        help="SET the emitted actor's Rotation field to this ABSOLUTE orientation "
                             "in unreal rotation units (16384 = 90°, 65536 = a full turn; a fresh "
                             "generated actor starts at identity, so no add-vs-override ambiguity). "
                             "Convenience shorthand for --prop Rotation=PITCH,YAW,ROLL")
    abuild.add_argument("--folder", default=None, metavar="PATH",
                        help="hierarchical organization PATH (dotted, e.g. castle.wall.north) for the "
                             "emitted actor — a uedcli-side sidecar, NEVER emitted to the built map, "
                             "rides the T3D as a `// uedcli-folder:` carrier that `actor add` persists.")
    abuild.add_argument("--label", action="append", default=[], type=_nonempty, metavar="L",
                        help="cross-cutting classification label for the emitted actor (repeat for "
                             "several) — a uedcli-side sidecar, NEVER emitted to the built map, rides "
                             "the T3D as a `// uedcli-labels:` carrier `actor add` persists.")

    add = asub.add_parser("add", help="add actors from a T3D file (or - for stdin) to the "
                                      "$UEDCLI_LEVEL's trunk")
    add.add_argument("file", help="T3D snippet file, or - to read from stdin")
    # NOTE: `actor add` is a PURE carrier-consumer — it has NO --folder/--label (removed 2026-07-24
    # 17:04). Organization is set on the GENERATOR (`brush build`/`actor build` --folder/--label, which
    # emit the `// uedcli-folder:`/`// uedcli-labels:` carriers `actor add` reads back) or changed on the
    # trunk afterward with `actor folder set` / `actor label`.
    add.add_argument("--order", metavar="POS", default="last",
                     help="CSG-order placement of the added actor(s): first | last (default) | "
                          "before=NAME | after=NAME. `first` mints an order_value below every "
                          "existing actor (lowest CSG order, carves first); before=/after=NAME "
                          "places adjacent to NAME. Multiple actors added at once land as a block "
                          "preserving their input order. Level target only (rejected on "
                          "--tree stash|prefab, which have no order_value sidecar)")
    _tree_flag(add)

    order = asub.add_parser(
        "order",
        help="reorder EXISTING actors' CSG precedence by minting new order_values (no geometry "
             "change). CSG order is the (order_value, name) sort; --first makes an actor carve/add "
             "BEFORE everything else. Multiple actors move as a block preserving their relative order")
    order.add_argument("names", nargs="+",
                       help="actor Names to reorder (case-insensitive), or the single token - to "
                            "read a newline-separated name list from stdin (e.g. `actor find … | "
                            "actor order - --first`); - is the sole source, not mixable with names")
    og = order.add_mutually_exclusive_group(required=True)
    og.add_argument("--first", action="store_true",
                    help="place before the current LOWEST CSG order (new minimum — carves first)")
    og.add_argument("--last", action="store_true",
                    help="place after the current HIGHEST CSG order (new maximum)")
    og.add_argument("--before", metavar="NAME",
                    help="place immediately before NAME in CSG order (NAME must exist and not be in "
                         "the moved set)")
    og.add_argument("--after", metavar="NAME",
                    help="place immediately after NAME in CSG order (NAME must exist and not be in "
                         "the moved set)")
    _tree_flag(order)

    dele = asub.add_parser("delete", help="delete one or more actors from $UEDCLI_LEVEL")
    dele.add_argument("names", nargs="+",
                      help="actor Names to delete (case-insensitive), or the single token - to "
                           "read a newline-separated name list from stdin (e.g. `actor find … | "
                           "actor delete -`); - is the sole source, not mixable with names")
    _tree_flag(dele)

    bbox = asub.add_parser(
        "bbox",
        help="print the world axis-aligned bounding box (min/max/size/center) enclosing the given "
             "actors — ONE box over the whole set (a single actor prints its own box; the "
             "multi-actor case IS the union, so there is no --union flag: "
             "`actor find --folder castle.* | actor bbox -` gives the union). Honours each actor's "
             "rotation/scale/location; a point actor contributes a zero-size box at its Location")
    bbox.add_argument(
        "names", nargs="+",
        help="actor Names to bound together (case-insensitive), or the single token - to read a "
             "newline-separated name list from stdin (e.g. `actor find … | actor bbox -`); - is "
             "the sole source, not mixable with names. Empty stdin is a clean no-op (exit 0)")
    bboxg = bbox.add_mutually_exclusive_group()
    bboxg.add_argument(
        "--field", choices=["min", "max", "size", "center"], default=None,
        help="print ONLY this one vector as a bare `x,y,z` line (pipe-friendly single-value form) "
             "instead of the default four labeled min/max/size/center lines")
    bboxg.add_argument(
        "--json", action="store_true",
        help="emit the box as JSON ({min,max,size,center}, each {x,y,z}) instead of the text lines")
    _tree_flag(bbox)

    mv = asub.add_parser("move", help="move a single actor to/by a world coordinate")
    mv.add_argument("name", help="actor Name to move (case-insensitive)")
    g = mv.add_mutually_exclusive_group(required=True)
    g.add_argument("--to", type=parse_coord, metavar="X,Y,Z",
                   help="absolute world target position")
    g.add_argument("--by", type=parse_coord, metavar="DX,DY,DZ",
                   help="world delta applied to the actor's current Location")
    _tree_flag(mv)

    pr = asub.add_parser(
        "prop",
        help="read, set, or clear an actor's properties model-side, validated against the "
             "actor's class schema (no editor). Sub-verbs: set / unset / get")
    prsub = pr.add_subparsers(dest="propsub", required=True)
    prs = prsub.add_parser(
        "set",
        help="set properties in ONE atomic, schema-validated edit. KEY=VALUE replaces the "
             "whole value (a static array takes the tuple form KEY=(0=V,3=W), clearing "
             "unmentioned elements); KEY.N=V edits one array element; KEY.Member=V edits one "
             "struct member (other members preserved; unset props base on the class default). "
             "A Vector/Rotator prop also takes the comma form KEY=X,Y,Z")
    prs.add_argument("name",
                     help="actor to edit (case-insensitive; the level's canonical name is used), "
                          "or - to read a newline-separated name list from stdin and apply the "
                          "same tokens to EVERY piped actor (e.g. `actor find … | actor prop set "
                          "- Texture=…`); atomic across all actors (a bad token touches none)")
    prs.add_argument("tokens", nargs="+", metavar="KEY[.PATH]=VALUE",
                     help="assignments; KEY and path segments are case-insensitive and stored "
                          "in the class's canonical spelling; VALUE is stored verbatim minus "
                          "surrounding quotes. The T3D KEY(N) spelling is rejected — write "
                          "KEY.N. Overlapping targets in one invocation are rejected")
    _tree_flag(prs)
    pru = prsub.add_parser(
        "unset",
        help="clear properties (revert to the class default): KEY clears the whole prop "
             "(every element of a static array); KEY.N clears one element; KEY.Member removes "
             "one member from the stored value (that member reverts to its class default). "
             "`unset Location` resets to the origin. Clearing something not stored succeeds "
             "silently")
    pru.add_argument("name",
                     help="actor to edit (case-insensitive; the level's canonical name is used), "
                          "or - to read a newline-separated name list from stdin and clear the "
                          "same tokens on EVERY piped actor; atomic across all actors")
    pru.add_argument("tokens", nargs="+", metavar="KEY[.PATH]",
                     help="properties/paths to clear (case-insensitive; dot-paths as in set)")
    _tree_flag(pru)
    prg = prsub.add_parser(
        "get",
        help="print EFFECTIVE property values: the stored value if present, else the class "
             "default decoded offline from the game packages, else the type's zero — one line "
             "per KEY, in argument order (a whole static array prints as one (0=V,1=W,…) "
             "line; a whole struct prints every member). With no KEYs, dumps the actor's "
             "STORED props (plus Location) as round-trippable KEY=VALUE lines")
    prg.add_argument("name",
                     help="actor to read (case-insensitive), or - to read a newline-separated "
                          "name list from stdin and dump EVERY piped actor. Piped output is "
                          "name-prefixed KV (`<name>\\t<key>=<value>`) so a multi-actor, "
                          "multi-key dump stays parseable; a single named actor keeps the bare "
                          "(or --kv) output")
    prg.add_argument("tokens", nargs="*", metavar="KEY[.PATH]",
                     help="properties/paths to read (dot-paths as in set; e.g. Location.X, "
                          "MultiSkins.2, Rotation.Yaw). Omit to dump all stored props. NOTE: a "
                          "Rotation/angle reads back in raw rotator UNITS (16384 = 90°), the T3D "
                          "storage form — NOT degrees (the degree-based verb is `actor rotate`); "
                          "`prop set` takes the same units, so get/set round-trip")
    prgfmt = prg.add_mutually_exclusive_group()
    prgfmt.add_argument("--kv", action="store_true",
                        help="print KEY=VALUE lines (canonical spelling) instead of bare values — "
                             "round-trips into `actor prop set`")
    prgfmt.add_argument("--json", action="store_true",
                        help="emit the effective values as JSON instead of text lines: a single "
                             "named actor prints one {key: value} object; a piped multi-actor read "
                             "(`-`) prints a {name: {key: value}} object. Values are emitted as "
                             "STRINGS (heterogeneous props/structs can't be uniformly typed), unlike "
                             "`mover key list --json`/`brush vertex list --json` which emit typed "
                             "numbers. Mutually exclusive with --kv")
    _tree_flag(prg)

    rot = asub.add_parser("rotate",
                          help="rotate a group of actors around a pivot (PITCH,YAW,ROLL in unreal "
                               "rotation units, 16384 = 90°)")
    rot.add_argument("names", nargs="+",
                     help="actor Names to rotate together (case-insensitive), or the single token "
                          "- to read a newline-separated name list from stdin (e.g. `actor find … "
                          "| actor rotate - --by 0,90,0`); - is the sole source, not mixable")
    rtg = rot.add_mutually_exclusive_group(required=True)
    rtg.add_argument("--by", type=parse_coord, default=None, metavar="PITCH,YAW,ROLL",
                     help="RELATIVE rotation in unreal rotation units, 16384 = 90° (negatives "
                          "allowed) — orbits each Location about the pivot and composes into Rotation")
    rtg.add_argument("--to", type=parse_coord, default=None, metavar="PITCH,YAW,ROLL",
                     help="ABSOLUTE rotation in unreal rotation units (16384 = 90°): sets each "
                          "actor's Rotation field to this value IN PLACE (Location never moves); "
                          "excludes --pivot/--pivot-actor")
    rg = rot.add_mutually_exclusive_group()
    rg.add_argument("--pivot", type=parse_coord, default=None, metavar="X,Y,Z",
                    help="explicit world pivot (with --by only; default: the LOCATION of the set "
                         "member nearest the bbox center — an authored point, so the pivot keeps "
                         "the grid you built on and a lone actor turns in place)")
    rg.add_argument("--pivot-actor", dest="pivot_actor", default=None,
                    help="use this actor's Location as the pivot (with --by only)")
    _tree_flag(rot)

    aprev = asub.add_parser(
        "preview",
        help="self-rendered orthographic wireframe of actors from $UEDCLI_LEVEL (brushes coloured "
             "by CSG op; point actors as sprites/markers). Model-side, host-only — no editor")
    aprev.add_argument("names", nargs="*",
                       help="actors to render (case-insensitive), or the single token - to read a "
                            "newline-separated name list from stdin (`actor find … | actor preview "
                            "-`). Ignored when --from-t3d is given")
    aprev.add_argument("--from-t3d", dest="from_t3d", nargs="+", default=None, metavar="FILE",
                       help="render the actors in these T3D file(s) instead of the level, or - for a "
                            "T3D snippet on stdin (`brush build spiral | actor preview --from-t3d -`). "
                            "Multiple files concatenate in order; - is the sole value if present. "
                            "Mutually exclusive with the names source")
    _preview_opts(aprev)
