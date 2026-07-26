"""uedcli CLI — the LLM-facing verb surface. Query and mutate verbs operate
model-side on $UEDCLI_LEVEL's git-native T3D trunk (`maps/<level>/`); the
editor is reached only via a per-command ephemeral spin-up (materialize /
preview / the stash CSG generators). The project's OWN git is the history —
uedcli reads it but never runs git for you, so history/recovery exist only once
the project is its own repo (`level status` reports when it is not).
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from decimal import Decimal, InvalidOperation

from .model import Vec3
from .preview import DEFAULT_ANNOTATIONS

# A bare token like "-32,-32,32" or "-128" starts with '-', so argparse would treat
# it as an option and refuse to feed it to --at/--to/--by. Recognize coordinate
# tokens (signed numbers, optionally comma-joined) as VALUES so negative coords work
# without the awkward --at=-32,-32,32 equals form.
_COORD_TOKEN = re.compile(r"^[-+]?[0-9.]+(,[-+]?[0-9.]+)*$")

# The negative-facing VALUES for `--facing` (`brush poly find/align`): `-X`/`-Y`/`-Z`. argparse would
# otherwise read a leading-dash token as an option, forcing the `--facing=-Z` equals form. No
# single-dash option of these spellings exists in the CLI (only `-h`), so treating them as values is
# unambiguous. (Uppercase only — `-h` stays help.)
_FACING_NEG = re.compile(r"^-[XYZ]$")

# Shared help for the `--catalog-dir` flag every texture verb carries (load-bearing for
# project-less texture use). One string so `sync`/`list`/`search`/`tags`/`classify status|set`
# all document the default-resolution the same way (audit L3).
_CATALOG_DIR_HELP = ("tracked manifest dir (default: the resolved project's catalog dir — "
                     "the uedcli.toml `catalog` key, or <root>/texture-catalog/)")


class _CoordArgumentParser(argparse.ArgumentParser):
    def _parse_optional(self, arg_string):
        if _COORD_TOKEN.match(arg_string) or _FACING_NEG.match(arg_string):
            return None                  # a bare coord token (`-512,0,256`) or a `-X/-Y/-Z` facing is a value
        return super()._parse_optional(arg_string)   # VALUE for --at-style verbs, not an option


def _nonempty(s: str) -> str:
    """Reject empty or whitespace-only values (for --group / --name)."""
    if not s or not s.strip():
        raise argparse.ArgumentTypeError(f"value must not be empty, got: {s!r}")
    return s


def _nonempty_class(s: str) -> str:
    """Reject empty, whitespace-only, or any empty component in a dot-separated class ref.

    Valid forms: bare `Name` or qualified `Package.Name`. Rejected: leading dot
    (`.Foo`), trailing dot (`Foo.`), consecutive dots (`Foo..Bar`), or a dot-only
    string. Any empty component means the ref can never match a stored class.
    """
    _nonempty(s)
    # reject any empty component (leading dot, trailing dot, or consecutive dots)
    if any(part == "" for part in s.split(".")):
        raise argparse.ArgumentTypeError(
            f"class must have no empty component (e.g. '.Foo', 'Foo.', or 'Foo..Bar' "
            f"are all invalid), got: {s!r}"
        )
    return s


def parse_coord(text: str) -> Vec3:
    """Parse a single `X,Y,Z` coordinate token into an exact Decimal triple.

    Decimal (not float) so authored fractional coords carry no binary-representation
    drift and match stored vertices exactly. Accepts integers and decimals, optional
    surrounding whitespace. Raises ArgumentTypeError (clean CLI error) on bad input."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"coordinate must be X,Y,Z (3 comma-separated numbers), got {text!r}"
        )
    try:
        return tuple(Decimal(p) for p in parts)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"coordinate has a non-numeric component: {text!r}")


def parse_bbox(text: str):
    """Parse a world-AABB token `X0,Y0,Z0,X1,Y1,Z1` (two opposite corners) into a normalized
    `(lo, hi)` pair of exact Decimal triples — min/max per axis, so any two opposite corners work.
    Decimal (not float) so it compares exactly against stored/transformed vertices. Raises
    ArgumentTypeError (clean CLI error) on the wrong count or a non-numeric component."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 6:
        raise argparse.ArgumentTypeError(
            f"bbox must be X0,Y0,Z0,X1,Y1,Z1 (6 comma-separated numbers), got {text!r}"
        )
    try:
        nums = [Decimal(p) for p in parts]
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"bbox has a non-numeric component: {text!r}")
    # Decimal ACCEPTS "nan"/"snan"/"inf" — reject them: nan/snan raise a signaling InvalidOperation
    # (ArithmeticError, which argparse would NOT convert to a clean exit) on the min/max below, and inf
    # would silently match every actor on that axis. A bbox coord must be a finite number.
    if any(not n.is_finite() for n in nums):
        raise argparse.ArgumentTypeError(f"bbox coords must be finite numbers, got {text!r}")
    a, b = nums[:3], nums[3:]
    lo = tuple(min(a[i], b[i]) for i in range(3))
    hi = tuple(max(a[i], b[i]) for i in range(3))
    return (lo, hi)


def depth_value(text: str):
    """Parse a `--depth` value for `class list`/`class show`: a non-negative integer, or the keyword
    `all` (case-insensitive) meaning UNLIMITED depth (returned as `math.inf`). A negative or
    non-numeric token raises a clean ArgumentTypeError naming the offending value — never a bare
    int-parse traceback (CLI convention). Returns `int | float('inf')`."""
    s = text.strip()
    if s.casefold() == "all":
        return math.inf
    try:
        n = int(s)
    except ValueError:
        n = None
    if n is None or n < 0:
        raise argparse.ArgumentTypeError(
            f"invalid depth {text!r}: expected a non-negative integer or 'all'")
    return n


def parse_pan(text: str) -> tuple[int, int]:
    """Parse a single `U,V` integer pan offset (`model.Polygon.pan` is `tuple[int, int]` — v1
    pan is integer-only, decimal pan is a deferred fast-follow)."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"pan must be U,V (2 comma-separated integers), got {text!r}")
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        raise argparse.ArgumentTypeError(f"pan has a non-integer component: {text!r}")


def _preview_opts(pp):
    pp.add_argument("--layout", default="quad", choices=["quad", "single", "breakdown"],
                    help="pane layout (default quad). 'quad' = the UED-style 2x2 grid (Top / Front / "
                         "Iso / Side). 'single' = one view, per --view. 'breakdown' = a near-square "
                         "GRID that walks the scene actor by actor: pane 0 is the whole scene in CSG "
                         "colour (a plain spatial map — no legend, names or numbers), then ONE focused "
                         "+ zoomed pane per actor — a brush with all its faces numbered and captioned, "
                         "a point actor with its marker/sprite captioned. breakdown uses --view and "
                         "sets its OWN per-pane focus/zoom, so --frame/--focus are ignored under it")
    pp.add_argument("--view", default="iso", choices=["top", "front", "side", "iso"],
                    help="which single view 'single'/'breakdown' render (ignored by 'quad', which "
                         "shows all four); 'iso' separates opposite faces so index labels don't overlap")
    pp.add_argument("--iso-angle", type=float, default=30.0,
                    help="iso receding-edge angle from horizontal (default 30°)")
    pp.add_argument("--brush-colors", dest="brush_colors", default="csg", choices=["csg", "legend"],
                    help="how to colour the wireframe: 'csg' (default) = by CSG op (added blue, "
                         "subtracted gold, semisolid pink, nonsolid green, mover magenta); 'legend' = "
                         "each brush in its own per-actor legend tint (drops the CSG cue but tells "
                         "same-op brushes apart at a glance, matching the legend swatches)")
    pp.add_argument("--annotate", dest="annotate", default=DEFAULT_ANNOTATIONS,
                    help="comma-set of annotation selectors (union). A bare KIND = ALL of it; colon "
                         "FILTERs narrow; commas union. Kinds: poly (face indices), name (actor "
                         "names). poly filters: vis (inert alias of bare poly — on-face numbering is "
                         "facing-blind), hi (highlighted; 'highlighted' is an accepted synonym). name "
                         "filters: brush, point, hi. e.g. 'name:brush' = brush names only; 'poly:vis' "
                         "= every face index (same as bare poly). Keywords (stand alone): none, all "
                         "(=poly,name), highlighted (=poly:hi,name:hi). Default: all face indices + "
                         "all names")
    pp.add_argument("--frame", default=None, metavar="TARGET",
                    help="frame a target to fill the view; frames ONLY, does NOT highlight. Two forms: "
                         "a SELECTOR — a bare BRUSH name frames that actor's whole AABB, or BRUSH:IDX "
                         "(the selector `brush poly find` prints) frames ONE poly (a multi-index / "
                         "`:all` value is an error — use --highlight for a set); OR an explicit world "
                         "AABB — six comma-separated numbers X0,Y0,Z0,X1,Y1,Z1, framed exactly. "
                         "Not applied under --layout breakdown, which frames each pane itself "
                         "(a value is still validated)")
    pp.add_argument("--frame-tightness", dest="frame_tightness", type=float, default=0.8, metavar="N",
                    help="framing tightness toward a --frame SELECTOR target: 0 = no zoom (whole-set "
                         "frame), 1 = tightest (target + a small margin), in between interpolates; "
                         "must be in [0,1]. Default 0.8. No --frame ⇒ no-op. An explicit AABB --frame "
                         "is always framed exactly, unaffected by this")
    pp.add_argument("--highlight", metavar="POLY|NAME",
                    action="append", default=None,
                    help="emphasise a poly or an actor; repeatable, no effect on framing. A token "
                         "WITH a colon is a poly selector BRUSH:IDX (the set form BRUSH:1,2 and "
                         "BRUSH:all work too) — those polys draw in their brush's vivid CSG hue + a "
                         "bolder line. A token WITHOUT a colon is an ACTOR NAME: a brush actor "
                         "highlights ALL its polys; a point actor gets corner brackets (a selection "
                         "reticle) framing its sprite/marker")
    pp.add_argument("--focus", metavar="BRUSH", default=None,
                    help="spotlight ONE brush: only it shows face indices (in its label tint); "
                         "every OTHER brush recedes to a faint (dimmed) wireframe. All actor names "
                         "still appear in the legend. --highlight OVERRIDES this — a highlighted "
                         "poly/actor stays vivid+bold on top and keeps its index even when its brush is "
                         "not the focus. An unknown name / a point actor → clean exit 2. Not applied "
                         "under --layout breakdown, which focuses each pane itself (a value is still "
                         "validated)")
    pp.add_argument("--show", default="", metavar="SET",
                    help="comma-set (union) of range overlays to draw for POINT actors (default none): "
                         "'collision' = a faint light-red collision cylinder for every colliding point "
                         "actor (bCollideActors true) — a circle in TOP, a 2·radius × 2·height rect in "
                         "FRONT/SIDE, an 8-sided wire cylinder in ISO; 'light-range' = a faint orange "
                         "sphere of a light's reach (25·(LightRadius+1) UU); 'sound-range' = a faint "
                         "blue sphere of an AmbientSound's reach (25·(SoundRadius+1) UU). Brush actors "
                         "(incl. movers) are excluded — their preview stays schema-free (no class lookup)")
    pp.add_argument("--size", type=int, default=1024, metavar="PX",
                    help="output image edge length in pixels (default 1024)")
    pp.add_argument("--out", default=None, metavar="PATH",
                    help="host path to write the rendered PNG to (relative → resolved against the "
                         "cwd). The image is ALWAYS a PNG: whatever extension you give is replaced "
                         "by .png, so --out shot.jpg writes shot.png. Optional: with no --out a "
                         "unique temp file is created (uedcli-preview-*.png). The absolute path "
                         "actually written is ALWAYS printed to stdout")


def _tree_flag(parser, *, level_only=False):
    """Add `--tree KIND/NAME` to a verb so it operates on a named T3D tree (level / stash / prefab)
    instead of the ambient `$UEDCLI_LEVEL` (decisions 2026-07-20 — the three are one tree format, so
    the flag names a `tree`; it replaces the old `--target`). One helper, one help string — the single
    place a reader learns the set + default. It rides the mutating content verbs, the read verbs, AND
    (level-only) `level materialize`/`preview`. `level_only=True` restricts the value to `level/NAME`
    (materialize/preview build/walk a world — a stash/prefab has none; dispatch rejects the other
    kinds). Still NOT the generators (`actor build`/`brush build` — they read no tree; the ambient is
    consumed downstream at `actor add`) or `actor preview` (per-kind `stash|prefab preview` exists)."""
    if level_only:
        parser.add_argument(
            "--tree", metavar="level/NAME", default=None,
            help="build/preview this level instead of $UEDCLI_LEVEL: level/NAME (materialize and "
                 "preview operate on a level only — use `stash preview`/`prefab preview` for a "
                 "captured set). Default: the level named by $UEDCLI_LEVEL.")
        return
    parser.add_argument(
        "--tree", metavar="KIND/NAME", default=None,
        help="operate on this tree instead of $UEDCLI_LEVEL: KIND/NAME where KIND is "
             "level|stash|prefab and NAME is the level/stash/prefab name (may be nested, e.g. "
             "stash/hangar/arch). Default: the level named by $UEDCLI_LEVEL.")


def _apply_flags(ap):
    ap.add_argument("--at", type=parse_coord, default=None, metavar="X,Y,Z",
                    help="world Location to place the set at (default: its captured origin)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--group", default=None, help="Group for placed actors (default: the id/basename)")
    g.add_argument("--no-group", action="store_true",
                   help="place actors with no Group (default: group them under the id/basename)")
    ap.add_argument("--folder", default=None, metavar="PATH",
                    help="also stamp this uedcli-side folder (dotted path, e.g. castle.props) on the "
                         "placed actors — the trunk sidecar, INDEPENDENT of --group (the T3D Group "
                         "prop). No default: absent --folder, placed actors are unfoldered")


def build_parser() -> argparse.ArgumentParser:
    p = _CoordArgumentParser(prog="uedcli", description=__doc__)
    p.add_argument("--project", default=None,
                   help="project root (or its uedcli.toml); else $UEDCLI_PROJECT, else the nearest "
                        "ancestor dir containing an uedcli.toml walking up from the cwd")
    sub = p.add_subparsers(dest="cmd", required=True)

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
             "(A looser 'also catch straddling brushes' variant, --overlapping-bbox, is a separate "
             "deferred verb — see dev/docs/board/to-spec.md.)")
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

    show = asub.add_parser("show", help="print matching actors' full T3D blocks")
    show.add_argument("name",
                      help="actor Name or glob (case-insensitive; a glob may print several "
                           "actors), or - to read a newline-separated name list from stdin "
                           "(e.g. `actor find … | actor show -`; concatenated blocks in piped "
                           "order). An exact name that matches nothing errors (exit 2); a glob "
                           "with zero matches prints nothing (exit 0, grep-like)")
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
                    help="explicit world pivot (with --by only; default: the targets' computed "
                         "grid-aligned center)")
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

    brush = sub.add_parser("brush", help="brush geometry verbs")
    bsub = brush.add_subparsers(dest="sub", required=True)

    # `scale` + `apply-transform` set/bake MainScale/PostScale — brush-family properties (ABrush; a
    # mesh uses DrawScale), so they live under `brush`, not `actor` (renamed 2026-07-19). `brush`
    # verbs act on a brush actor (movers included — they carry a PolyList); a point actor is rejected.
    scl = bsub.add_parser(
        "scale",
        help="scale a group of BRUSH actors: set their MainScale (a negative axis mirrors). `mirror` "
             "is `brush scale --by -1,1,1` (no separate verb). A non-brush (point) actor is rejected")
    scl.add_argument("names", nargs="+",
                     help="brush actor Names to scale (case-insensitive), or the single token - to read "
                          "a newline-separated name list from stdin; - is the sole source, not mixable")
    stg = scl.add_mutually_exclusive_group(required=True)
    stg.add_argument("--to", type=parse_coord, default=None, metavar="SX,SY,SZ",
                     help="ABSOLUTE MainScale target (sets the field IN PLACE; Location never moves; "
                          "excludes --pivot/--pivot-actor). On a brush with a non-identity PostScale "
                          "the previewed world scale is PostScale*MainScale, not this value (rare, "
                          "ingested only)")
    stg.add_argument("--by", type=parse_coord, default=None, metavar="SX,SY,SZ",
                     help="RELATIVE scale factor: multiplies the current MainScale per-axis AND "
                          "orbits each Location about the pivot (Loc' = P + S*(Loc-P))")
    sg = scl.add_mutually_exclusive_group()
    sg.add_argument("--pivot", type=parse_coord, default=None, metavar="X,Y,Z",
                    help="explicit world pivot (with --by only; default: the targets' computed "
                         "grid-aligned center)")
    sg.add_argument("--pivot-actor", dest="pivot_actor", default=None,
                    help="use this actor's Location as the pivot (with --by only)")
    _tree_flag(scl)

    axf = bsub.add_parser(
        "apply-transform",
        help="bake MainScale + Rotation + PostScale permanently into the brush vertices and reset "
             "the fields (the offline ACTOR APPLYTRANSFORM). Reverses winding on a mirror/negative "
             "determinant; rewrites PrePivot; leaves Location. Rejects movers and non-brush actors")
    axf.add_argument("names", nargs="+",
                     help="brush actor Names to bake (case-insensitive), or the single token - to read "
                          "a newline-separated name list from stdin; - is the sole source, not mixable")
    ltg = axf.add_mutually_exclusive_group()
    ltg.add_argument("--lock-textures", dest="lock_textures", action="store_true", default=True,
                     help="transform the texture axes with the geometry so textures stay glued "
                          "(TEXTURELOCK; the DEFAULT)")
    ltg.add_argument("--no-lock-textures", dest="lock_textures", action="store_false",
                     help="leave the texture mapping fixed (the texture slides as the surface moves)")
    _tree_flag(axf)
    clip = bsub.add_parser("clip", help="clip a brush by a plane, keeping one half")
    clip.add_argument("name", help="brush actor Name to clip (case-insensitive)")
    clip.add_argument("--axis", choices=["x", "y", "z"],
                      help="axis-aligned plane; use with --coord")
    clip.add_argument("--coord", type=Decimal, help="coordinate of the axis plane (world)")
    clip.add_argument("--plane", type=parse_coord, nargs=2,
                      metavar=("PX,PY,PZ", "NX,NY,NZ"),
                      help="general plane: world point + normal")
    clip.add_argument("--keep", choices=["below", "above"], default="below",
                      help="keep the half below (opposite normal) or above (normal side)")
    _tree_flag(clip)

    replace = bsub.add_parser(
        "replace",
        help="swap a brush's shape from a piped generator T3D on stdin, keeping its identity")
    replace.add_argument("name", help="brush actor Name whose shape to replace (case-insensitive)")
    replace.add_argument(
        "shape", metavar="-",
        help="the literal `-`: read the new shape as a T3D snippet from stdin (e.g. `brush build "
             "cube … | brush replace WALL -`). Only the incoming PolyList is used; its own "
             "Location/PrePivot/Name are ignored. Empty stdin is a clean no-op.")
    _tree_flag(replace)

    # Model-side parametric brush builders (replicate UnrealEd's GUI BrushBuilders).
    def _common_build_opts(bp):
        bp.add_argument("--at", type=parse_coord, default=(Decimal(0), Decimal(0), Decimal(0)),
                        metavar="X,Y,Z", help="world Location for the emitted actor(s) (default "
                             "origin). For cube/cylinder/cone/sheet it is the brush's geometric "
                             "CENTER on EVERY axis, including Z. THE OTHER SHAPES anchor elsewhere: "
                             "the staircase at its front-bottom corner (min X/Y/Z); the spiral at "
                             "the base of its column axis (centred in XY, BOTTOM in Z); "
                             "extrude/revolve at the point profile coordinate (0,0) lands on — "
                             "for a revolve that is the bend centre, since the sweep axis passes "
                             "through it.")
        bp.add_argument("--base-name", dest="base_name",
                        help="base Name (stem) for the emitted actor(s); a unique `_<rand>` suffix "
                             "is appended at `actor add`, so this is a prefix, not the final Name "
                             "(default: the shape/mover-class name). The spiral, which emits one "
                             "actor per step, appends a per-step index; the staircase is one actor.")
        bp.add_argument("--csg", choices=["add", "subtract"], default=None,
                        help="CSG operation (default add; invalid with --mover-class)")
        bp.add_argument("--solidity", choices=["solid", "semisolid", "nonsolid"],
                        default=None,
                        help="brush solidity (default solid; invalid with --mover-class)")
        bp.add_argument("--folder", default=None, metavar="PATH",
                        help="hierarchical organization PATH (dotted, e.g. castle.tower.roof) for the "
                             "emitted actor(s) — a uedcli-side sidecar, INDEPENDENT of the engine Group "
                             "prop, NEVER emitted to the built map. Rides the T3D as a `// uedcli-folder:` "
                             "carrier that `actor add` persists to the trunk. No default = unfoldered.")
        bp.add_argument("--label", action="append", default=[], type=_nonempty, metavar="L",
                        help="cross-cutting classification label for the emitted actor(s) (repeat to add "
                             "several). A uedcli-side sidecar (flat set), NEVER emitted to the built map; "
                             "rides the T3D as a `// uedcli-labels:` carrier `actor add` persists. "
                             "The engine Group is a regular prop: use --prop Group=<name>.")
        bp.add_argument("--texture", help="texture for every face (default editor default)")
        bp.add_argument("--mover-class", dest="mover_class", default=None,
                        help="make a Mover of this fully-qualified class (e.g. "
                             "DeusEx.ElevatorMover); base pose only — author keyframes with "
                             "'mover key count' then 'mover key move'/'rotate'. Rejects "
                             "--csg/--solidity (a mover is not CSG).")
        bp.add_argument("--prop", action="append", default=[],
                        metavar="KEY[.PATH]=VALUE",
                        help="extra actor property (repeat for multiple), schema-validated against "
                             "the emitted actor's class (Engine.Brush, or --mover-class) before "
                             "emit — same grammar as `actor build --prop`/`actor prop set` "
                             "(dot-paths, array tuple form, Vector/Rotator comma sugar). Applied to "
                             "every emitted brush/mover actor; the way to set open-ended mover "
                             "config (MoverEncroachType, MoveTime, Tag/Event, collision flags) with "
                             "no dedicated flag. Composes onto the class default. Overrides compose "
                             "over the generator's own fields (incl. CsgOper/PolyFlags/Group/"
                             "Rotation), so a --prop can override a dedicated flag's value")
        bp.add_argument("--rotate", type=parse_coord, default=None, metavar="PITCH,YAW,ROLL",
                        help="SET the emitted actor's Rotation field to this ABSOLUTE orientation "
                             "in unreal rotation units (16384 = 90°, 65536 = a full turn; a fresh "
                             "generated actor starts at identity, so no add-vs-override ambiguity). "
                             "Rotation is stored on the actor, NOT "
                             "baked into the vertices; warns on stderr if it pushes any brush "
                             "vertex off the integer grid (overrides any --prop Rotation=…). "
                             "It turns the brush about the actor's LOCAL ORIGIN — the SAME point "
                             "--at anchors, so see --at for exactly where that is per shape: "
                             "cube/cylinder/cone/sheet centre it, while the staircase, the spiral "
                             "and extrude/revolve each anchor elsewhere. A shape whose origin is "
                             "not its centre SWINGS through an arc instead of turning in place")

    bbuild = bsub.add_parser("build",
                             help="build a parametric shape and write T3D to stdout (stateless; no level needed)")
    bshape = bbuild.add_subparsers(dest="shape", required=True)

    bcube = bshape.add_parser("cube", help="axis-aligned box (width X, breadth Y, height Z)")
    bcube.add_argument("--width", type=float, required=True,
                       help="box size along the X axis, in world units (uu)")
    bcube.add_argument("--breadth", type=float, required=True,
                       help="box size along the Y axis, in world units (uu)")
    bcube.add_argument("--height", type=float, required=True,
                       help="box size along the Z axis, in world units (uu)")
    _common_build_opts(bcube)

    bcyl = bshape.add_parser("cylinder", help="n-gon prism (height, radius, sides)")
    bcyl.add_argument("--height", type=float, required=True,
                      help="prism height along the Z axis, in world units (uu)")
    bcyl.add_argument("--radius", type=float, required=True, help="circumscribed radius")
    bcyl.add_argument("--sides", type=int, default=8, help="polygon side count (default 8)")
    bcyl.add_argument("--align-to-side", dest="align_to_side", action="store_true",
                      help="turn a FACE rather than a vertex toward the axes, by offsetting the "
                           "cross-section half a segment (180/--sides degrees). Without it vertex "
                           "0 sits on +X, so an octagonal pillar meets an axis-aligned wall on a "
                           "CORNER, leaving two thin wedge gaps; with it a flat face sits flush. "
                           "Same parameter as UnrealEd's own CylinderBuilder AlignToSide checkbox. "
                           "For any other cross-section angle use --rotate, which is whole-actor "
                           "placement")
    _common_build_opts(bcyl)

    bcone = bshape.add_parser("cone", help="n-faced cone (height, base radius, sides)")
    bcone.add_argument("--height", type=float, required=True,
                       help="cone height (base to apex) along the Z axis, in world units (uu)")
    bcone.add_argument("--radius", type=float, required=True, help="base circumscribed radius")
    bcone.add_argument("--sides", type=int, default=8, help="polygon side count (default 8)")
    bcone.add_argument("--align-to-side", dest="align_to_side", action="store_true",
                       help="turn a FACE of the base ring rather than a vertex toward the axes, "
                            "by offsetting it half a segment (180/--sides degrees), so the cone "
                            "sits flush against an axis-aligned wall instead of meeting it on a "
                            "corner. Same parameter as UnrealEd's own AlignToSide checkbox; for "
                            "any other angle use --rotate")
    _common_build_opts(bcone)

    bsheet = bshape.add_parser("sheet", help="flat two-sided non-solid panel (width, height)")
    bsheet.add_argument("--width", type=float, required=True,
                        help="panel size along the plane's first axis, in world units (uu)")
    bsheet.add_argument("--height", type=float, required=True,
                        help="panel size along the plane's second axis, in world units (uu)")
    bsheet.add_argument("--plane", choices=["xy", "xz", "yz"], default="xz",
                        help="world plane the sheet lies in (default xz)")
    from .query import PF_NAMES as _PF_NAMES
    bsheet.add_argument("--flag", dest="flags", action="append", default=[],
                        type=str.lower, choices=[name for _, name in _PF_NAMES], metavar="NAME",
                        help="repeatable; OR an extra surface/poly flag (by name, case-insensitive) "
                             "onto the sheet's face AT BUILD TIME, on top of its default "
                             "twosided|notsolid — e.g. --flag portal --flag translucent for a zone "
                             "portal, in one step instead of a follow-up 'brush poly set --add-flag'")
    _common_build_opts(bsheet)

    bstair = bshape.add_parser("staircase",
                               help="linear staircase — ONE non-convex brush (Base/back/Step/"
                                    "Rise/tiled Side), ascends +X, front-bottom-corner anchored")
    bstair.add_argument("--steps", type=int, required=True, help="number of steps")
    bstair.add_argument("--depth", type=float, required=True, help="step depth (X) per step")
    bstair.add_argument("--rise", type=float, required=True, help="step rise (Z) per step")
    bstair.add_argument("--breadth", type=float, required=True, help="step width (Y)")
    _common_build_opts(bstair)

    bspiral = bshape.add_parser("spiral",
                                help="spiral staircase — a central column plus one wedge tread "
                                     "per step climbing around it (prints N+1 actors)")
    bspiral.add_argument("--steps", type=int, required=True, help="number of steps")
    bspiral.add_argument("--inner-radius", dest="inner_radius", type=float, required=True,
                         help="inner column radius")
    bspiral.add_argument("--step-width", dest="step_width", type=float, required=True,
                         help="radial tread depth")
    bspiral.add_argument("--rise", type=float, required=True, help="rise (Z) per step")
    bspiral.add_argument("--angle-per-step", dest="angle_per_step", type=int, default=8192,
                         metavar="UU",
                         help="how far each tread turns around the column, in unreal rotation "
                              "units — 16384 = 90 degrees, 8192 = 45 degrees (the default), and "
                              "the whole stair climbs --steps of these. Must satisfy "
                              "0 < angle-per-step < 32768 (a half turn or more per tread would "
                              "make the wedge non-convex)")
    _common_build_opts(bspiral)

    # --- swept 2D profiles: the shapes whose cross-section the author DRAWS -----------------
    # UnrealEd's 2D shape editor, as two generators: draw a closed profile, then sweep it in a
    # straight line (extrude) or around an in-plane axis (revolve). Both take the same profile
    # grammar, the same --axis orientation and the same --at anchor; they differ only in the sweep.
    _PROFILE_POINT_HELP = (
        "one profile vertex as `U,V` in the profile's own 2D coordinates — REPEAT the flag once "
        "per vertex, in ring order (at least 3). The ring is closed implicitly, so do not repeat "
        "the first point last (harmless if you do — it is welded away). Either winding is "
        "accepted. `U,V` map onto world axes per --axis")
    _PROFILE_AXIS_HELP = (
        "the world axis the profile PLANE IS NORMAL TO — equivalently the direction the sweep "
        "grows (default z). The profile's (U,V) then map onto the other two world axes in "
        "right-handed cyclic order: z → U=X,V=Y; x → U=Y,V=Z; y → U=Z,V=X")

    # The two caveats spec §4.5 and §6 require in the verb's own --help. They belong to the
    # SHAPE, not to any one flag, so they ride the subparser description rather than being
    # bolted onto an unrelated flag's help.
    _PROFILE_CONCAVE_NOTE = (
        "CONCAVE PROFILES are fully supported, as ONE brush: the engine's polygon must be convex "
        "and holds at most 16 vertices, so a concave profile (an L, a notched cornice) or one "
        "longer than 16 points has each of its two caps tiled into several convex faces, adding "
        "only diagonals of your own outline. CAVEAT: UnrealEd (`level materialize`) and the real "
        "engine (`level preview --game`) build such a brush correctly, but the offline draft "
        "renderer `level preview --native` assumes convex solids and draws a concave notch FILLED "
        "IN — a preview artefact, not a geometry bug."
    )
    _REVOLVE_OFFGRID_NOTE = (
        "OFF-GRID BY CONSTRUCTION: every vertex away from theta=0 lands on radius*cos/sin theta, "
        "and uedcli never snaps coordinates for you. An off-grid SOLID brush throws its BSP "
        "partition planes off-grid too — the primary cause of slivers, T-junctions and holes in "
        "the built map. Prefer --solidity semisolid wherever the swept shape is detail rather "
        "than structure: a semisolid receives cuts but emits no world-splitting planes. uedcli "
        "warns on stderr when it emits an off-grid solid."
    )

    bextrude = bshape.add_parser(
        "extrude",
        help="sweep a drawn 2D profile in a straight line — the shape for an L-ledge, an arch "
             "voussoir, a cornice or any other non-box cross-section",
        description="Sweep a drawn 2D profile in a straight line along --axis. " + _PROFILE_CONCAVE_NOTE)
    bextrude.add_argument("--point", action="append", metavar="U,V", help=_PROFILE_POINT_HELP)
    bextrude.add_argument("--depth", type=float, required=True,
                          help="sweep length along +--axis, in world units (uu); must be > 0")
    bextrude.add_argument("--axis", choices=["x", "y", "z"], default="z", help=_PROFILE_AXIS_HELP)
    _common_build_opts(bextrude)

    brevolve = bshape.add_parser(
        "revolve",
        help="sweep a drawn 2D profile around an in-plane axis, in flat facets — a curved "
             "corridor, an arch ring, a turned column",
        description=("Sweep a drawn 2D profile around the profile plane's own V axis (the line "
                     "U=0, through profile coordinate (0,0), so --at is the bend centre). "
                     + _REVOLVE_OFFGRID_NOTE + " " + _PROFILE_CONCAVE_NOTE))
    brevolve.add_argument("--point", action="append", metavar="U,V", help=_PROFILE_POINT_HELP)
    brevolve.add_argument("--angle", type=int, required=True, metavar="UU",
                          help="total sweep in unreal rotation units — 16384 = 90°, 65536 = a "
                               "CLOSED full turn (which omits both caps); must satisfy "
                               "0 < angle <= 65536. Thirds are not exact in UU, so a 60° bend is "
                               "--angle 10923 (60.002°)")
    brevolve.add_argument("--segments", type=int, default=None, metavar="N",
                          help="how many flat facets the sweep is divided into (default: one per "
                               "22.5° — 4 for a 90° bend, 16 for a full turn, UnrealEd's own "
                               "density). Each segment costs one face per profile edge, so a high "
                               "count is a heavy brush for the BSP")
    brevolve.add_argument("--axis", choices=["x", "y", "z"], default="z", help=_PROFILE_AXIS_HELP)
    _common_build_opts(brevolve)

    # --- CSG set merge: intersect / deintersect ------------------------------------------------
    # Generators like `brush build`, but their SHAPE comes from a piped brush set rather than
    # parameters, so they share `_common_build_opts` — with two VERB-SPECIFIC default overrides
    # (`--at`, `--solidity`) plus the placement pair `--origin`/`--pivot`.
    def _merge_opts(mp, verb: str):
        mp.add_argument(
            "set", metavar="-|FILE",
            help="`-` reads the brush SET as a T3D snippet from stdin (e.g. "
                 f"`actor find --folder castle.door | actor show - | brush {verb} -`); a FILE path "
                 "is also accepted, for a set you saved earlier. Every tier "
                 "feeds it through its own `show` verb (actor/stash/prefab). STDIN ORDER IS THE "
                 "CSG ORDER and is never re-sorted — a mixed add/subtract set is order-dependent. "
                 "Non-brush actors and Movers are REFUSED (exit 2, naming them) rather than "
                 "skipped — a merge quietly missing a brush reads as a complete answer; narrow "
                 "the pipe with `actor find --kind brush`. Empty stdin is a clean no-op (exit 0)")
        _common_build_opts(mp)
        # `--at`: KEEP the carved position by default. `_common_build_opts` defaults it to (0,0,0),
        # which would silently teleport the merged result to the world origin.
        # `--solidity`: the faithful per-face rule, not `_common_build_opts`' blanket `solid`.
        # `--at` is the one default that genuinely differs from `_common_build_opts` (which places
        # a generated shape at the origin); `--solidity` already defaults to None there, so only
        # its HELP is overridden below — the flag means something different on these verbs.
        mp.set_defaults(at=None)
        for a in mp._actions:
            if a.dest == "at":
                a.default = None
                a.help = ("world Location for the result: the merged brush is placed so its PIVOT "
                          "sits here. DEFAULT (omitted) = keep the position it was carved at. "
                          "Rejected with --origin keep, which is already an absolute form")
            elif a.dest == "rotate":
                # `_common_build_opts`' text ends on the extrude/revolve local-origin caveat,
                # which is meaningless here — these verbs cannot build a swept profile, and
                # their local origin is set by --origin, not by a profile's (0,0).
                a.help = ("SET the emitted actor's Rotation field to this ABSOLUTE orientation "
                          "in unreal rotation units (16384 = 90°, 65536 = a full turn; a fresh "
                          "generated actor starts at identity, so no add-vs-override ambiguity). "
                          "Rotation is stored on the actor, NOT baked into the vertices; warns on "
                          "stderr if it pushes any brush vertex off the integer grid (overrides "
                          "any --prop Rotation=…). It turns the brush about the actor's LOCAL "
                          "ORIGIN, which on this verb is wherever --origin put it")
            elif a.dest == "solidity":
                a.help = ("override the result's solidity — world-brush result ONLY; INVALID with "
                          "--mover-class (a mover always keeps the source per-face solidity, since a "
                          "semisolid face blocks just like solid — only nonsolid is walk-through — so "
                          "there is nothing to override). DEFAULT (omitted) = the FAITHFUL per-face "
                          "rule: a face keeps the solidity of the ADDITIVE it came from, a face from a "
                          "subtractive is forced solid. `solid` clears the per-face solidity bits on "
                          "every face — use it to scrub a weld that pulled in a NONSOLID additive "
                          "(nonsolid faces are walk-through). `semisolid`/`nonsolid` set the "
                          "actor-level solidity instead.")
        mp.add_argument("--origin", default="center", metavar="center|min|max|keep|X,Y,Z",
                        help="where the result's LOCAL origin sits: `center` (DEFAULT) re-centres "
                             "on the result's bounding-box centre so the brush is trivially "
                             "relocatable; `min`/`max` use a bbox corner; `X,Y,Z` an explicit "
                             "world point; `keep` emits the raw faithful form (Location=0, "
                             "world-space vertices) for a direct compare against an editor "
                             "export — `keep` rejects --at")
        mp.add_argument("--pivot", default=None, metavar="center|min|max|X,Y,Z",
                        help="world point the result ROTATES about, written as its PrePivot "
                             "(default: the --origin anchor). For a door plug pass the hinge, e.g. "
                             "`--pivot min`, so `mover key rotate` swings it about the hinge "
                             "instead of the brush centre")

    bint = bsub.add_parser(
        "intersect",
        help="CSG-merge a piped brush SET into ONE brush against an EMPTY background: additives "
             "make solid, subtractives carve it, and the resulting solid's boundary is written as "
             "a single welded brush T3D to stdout. Needs at least one additive brush")
    _merge_opts(bint, "intersect")

    bdeint = bsub.add_parser(
        "deintersect",
        help="CSG-merge a piped brush SET into ONE brush against a SOLID background: the set's "
             "subtractives define voids and the VOID is written as a solid — the 'negative'/plug "
             "that exactly fills a carved doorway (pair with --mover-class for a door). Needs at "
             "least one subtractive brush")
    _merge_opts(bdeint, "deintersect")

    # Vertex editing — MOVE ONLY (add/delete are illegal: they'd break the closed
    # solid). Corners are addressed by coordinate; moving one moves every poly-vertex
    # sharing it so the brush stays watertight.
    vertex = bsub.add_parser("vertex", help="vertex query/edit (move-only; never add/delete)")
    vsub = vertex.add_subparsers(dest="vsub", required=True)
    vl = vsub.add_parser("list", help="welded brush corners: world coord + the polys sharing each")
    vl.add_argument("name", help="brush actor Name to list corners of (case-insensitive)")
    vl.add_argument("--json", action="store_true",
                    help="emit the corners as JSON ({actor, vertices:[…]}, each vertex with "
                         "coord {x,y,z}/polys/nrefs) instead of the aligned text table")
    _tree_flag(vl)
    vm = vsub.add_parser("move", help="move one or more corners (selected by coordinate)")
    vm.add_argument("name", help="brush actor Name whose corners to move (case-insensitive)")
    vm.add_argument("--at", type=parse_coord, action="append", required=True, metavar="X,Y,Z",
                    help="world coordinate of a corner to move; repeat to move several")
    vmg = vm.add_mutually_exclusive_group(required=True)
    vmg.add_argument("--to", type=parse_coord, metavar="X,Y,Z",
                     help="absolute world target (requires exactly one --at)")
    vmg.add_argument("--by", type=parse_coord, metavar="DX,DY,DZ",
                     help="world delta applied to every --at corner")
    _tree_flag(vm)

    mover = sub.add_parser("mover", help="mover (animated brush actor) keyframe verbs")
    msub = mover.add_subparsers(dest="sub", required=True)
    mkey = msub.add_parser("key", help="set a mover's keyframe count and edit its animation keyframes")
    mkeysub = mkey.add_subparsers(dest="keysub", required=True)

    mkc = mkeysub.add_parser(
        "count", help="get or set NumKeys, the mover's runtime waypoint count (2..8). With no N: "
                      "print the current count. With N: set it — NON-DESTRUCTIVE (only the count "
                      "changes; lowering leaves the now-inactive keys' stored offsets dormant, so a "
                      "later raise restores them). Exactly equivalent to `actor prop set NumKeys=N`.")
    mkc.add_argument("name", help="the mover actor's Name")
    mkc.add_argument("n", type=int, nargs="?", default=None, metavar="N",
                     help="new waypoint count in 2..8 (key 0 is the base pose); omit to PRINT the "
                          "current NumKeys to stdout instead of setting it")
    _tree_flag(mkc)

    def _frame_group(parser):
        """A required-when-`--to`, mutually-exclusive coordinate-frame pair (enforced in dispatch,
        since argparse can't tie it to `--to`)."""
        fg = parser.add_mutually_exclusive_group()
        fg.add_argument("--from-base", dest="from_base", action="store_true",
                        help="with --to: the coords are the offset FROM THE BASE POSE, written "
                             "straight into the key (no base subtraction) — e.g. --to 0,0,64 "
                             "--from-base is 64uu above base. Required unless --from-world is given")
        fg.add_argument("--from-world", dest="from_world", action="store_true",
                        help="with --to: the coords are an ABSOLUTE WORLD pose; uedcli subtracts "
                             "the base to store the offset (KeyPos = to - Location). Required "
                             "unless --from-base is given")

    mkm = mkeysub.add_parser("move", help="reposition an EXISTING keyframe (1 <= index < NumKeys); "
                                          "does NOT grow NumKeys — raise it first with `mover key "
                                          "count`")
    mkm.add_argument("name", help="the mover actor's Name")
    mkm.add_argument("index", type=int, help="existing keyframe index (1..NumKeys-1; 0 is the base "
                                             "pose, edited via `actor move`)")
    mkmg = mkm.add_mutually_exclusive_group(required=True)
    mkmg.add_argument("--to", type=parse_coord, metavar="X,Y,Z",
                      help="target position; REQUIRES a frame (--from-base or --from-world)")
    mkmg.add_argument("--by", type=parse_coord, metavar="DX,DY,DZ",
                      help="world delta on the current offset (frame-agnostic — rejects "
                           "--from-base/--from-world)")
    _frame_group(mkm)
    _tree_flag(mkm)

    mkr = mkeysub.add_parser("rotate", help="re-orient an EXISTING keyframe (1 <= index < NumKeys); "
                                            "does NOT grow NumKeys — raise it first with `mover key "
                                            "count`")
    mkr.add_argument("name", help="the mover actor's Name")
    mkr.add_argument("index", type=int, help="existing keyframe index (1..NumKeys-1; 0 is the base "
                                             "pose, edited via `actor rotate`)")
    mkrg = mkr.add_mutually_exclusive_group(required=True)
    mkrg.add_argument("--to", type=parse_coord, metavar="PITCH,YAW,ROLL",
                      help="target orientation in unreal rotation units (16384 = 90°); REQUIRES a "
                           "frame (--from-base or --from-world)")
    mkrg.add_argument("--by", type=parse_coord, metavar="PITCH,YAW,ROLL",
                      help="unreal-rotation-unit delta on the current offset (frame-agnostic — "
                           "rejects --from-base/--from-world; 16384 = 90°)")
    _frame_group(mkr)
    _tree_flag(mkr)

    mkrm = mkeysub.add_parser("remove", help="delete a keyframe (index >= 1) and compact indices")
    mkrm.add_argument("name", help="the mover actor's Name")
    mkrm.add_argument("index", type=int, help="keyframe index to remove (1..NumKeys-1)")
    _tree_flag(mkrm)

    mkl = mkeysub.add_parser("list", help="list a mover's keyframes: world pose + stored offset")
    mkl.add_argument("name", help="the mover actor's Name")
    mkl.add_argument("--json", action="store_true",
                     help="emit the keyframes as a JSON array of {idx, world_pos, world_rot, "
                          "off_pos, off_rot, base} objects (each pose an [x,y,z]/[pitch,yaw,roll] "
                          "triple) instead of the text table")
    _tree_flag(mkl)

    # poly lives UNDER brush (a brush sub-element editor, peer to `brush vertex`).
    poly = bsub.add_parser("poly", help="per-surface (polygon) query/edit verbs")
    psub = poly.add_subparsers(dest="polysub", required=True)
    pl = psub.add_parser("list", help="list a brush's polys: facing/texture/flags/pan/centroid/area")
    pl.add_argument("name", help="brush actor Name to list polys of (case-insensitive)")
    pl.add_argument("--json", action="store_true",
                    help="emit the polys as JSON ({actor, polys:[…]}, each poly with idx/facing/"
                         "texture/flags/pan/centroid/area/nverts) instead of the aligned text table")
    _tree_flag(pl)

    from .query import PF_NAMES
    flag_names = [name for _, name in PF_NAMES]
    pset = psub.add_parser("set", help="set flags/texture/pan on one or more surfaces, model-side")
    pset.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR",
                      help="BRUSH:SELECTOR (SELECTOR = 'all' or comma-separated poly indices); "
                           "repeatable, e.g. Wall1:3,5 Wall2:all. Or the single token - to read the "
                           "targets from stdin (the BRUSH:idx lines `brush poly find` prints, e.g. "
                           "`poly find WALL --facing +Z | poly set - --texture …`); - is the sole "
                           "source, not mixable with BRUSH:SELECTOR args, and empty stdin is a clean "
                           "no-op (exit 0)")
    pset.add_argument("--texture", default=None, metavar="REF",
                      help="qualified Package[.Group].Name (e.g. DeusExDeco.Textures.Wood); "
                           "omit the group unless given one explicitly")
    pset.add_argument("--add-flag", dest="add_flags", action="append", default=[],
                      type=str.lower, choices=flag_names, metavar="FLAG",
                      help="repeatable; surface flag by name (case-insensitive), not bit value")
    pset.add_argument("--remove-flag", dest="remove_flags", action="append", default=[],
                      type=str.lower, choices=flag_names, metavar="FLAG",
                      help="repeatable; surface flag by name (case-insensitive), not bit value")
    pang = pset.add_mutually_exclusive_group()
    pang.add_argument("--pan-to", dest="pan_to", type=parse_pan, metavar="U,V",
                      help="absolute integer texel pan")
    pang.add_argument("--pan-by", dest="pan_by", type=parse_pan, metavar="U,V",
                      help="relative integer texel pan (relative to 0,0 if unset)")
    _tree_flag(pset)

    # `poly find`: a stateless PRODUCER — prints matching `BRUSH:idx` selectors (one per line) that
    # `brush poly align -` / `brush poly set` consume. Narrows a brush's faces by intrinsic labels.
    pfind = psub.add_parser(
        "find", help="print a brush's matching faces as BRUSH:idx selectors (feed to poly align/set)")
    pfind.add_argument("name", help="brush actor Name to search the polys of (case-insensitive)")
    pfind.add_argument("--item", default=None, metavar="NAME",
                       help="keep only faces whose builder ItemName equals NAME (case-insensitive; "
                            "e.g. Side to drop a cylinder's Cap faces)")
    pfind.add_argument("--facing", default=None, metavar="DIR",
                       help="keep only faces snapping to this outward facing: "
                            "+X|-X|+Y|-Y|+Z|-Z|slant")
    pfind.add_argument("--texture", default=None, metavar="REF",
                       help="keep only faces textured with REF (case-insensitive; exact ref or its "
                            "last dot-component)")
    pfind.add_argument("--json", action="store_true",
                       help="emit the matches as a JSON array of {brush,poly,item,facing,texture} "
                            "objects instead of BRUSH:idx lines")
    _tree_flag(pfind)

    # `poly align`: make a texture flow continuously across a face set (model-side). Exactly one
    # geometry mode; targets are BRUSH:SELECTOR positionals OR `-` (stdin, bare names or the
    # BRUSH:idx lines `poly find` prints).
    palign = psub.add_parser(
        "align", help="align faces so a texture flows continuously across them (wall/floor/ring)")
    pamode = palign.add_mutually_exclusive_group(required=True)
    pamode.add_argument("--wall", dest="mode", action="store_const", const="wall",
                        help="one shared texture frame across a set of strictly COPLANAR VERTICAL "
                             "faces (brickwork does not reset at each brush edge)")
    pamode.add_argument("--floor", dest="mode", action="store_const", const="floor",
                        help="one shared texture frame across a set of strictly COPLANAR HORIZONTAL "
                             "faces (floor/ceiling)")
    pamode.add_argument("--ring", dest="mode", action="store_const", const="ring",
                        help="wrap a texture around a cylinder's side faces: U advances by each "
                             "facet's chord around the ring, V runs along the axis")
    palign.add_argument("targets", nargs="*", metavar="BRUSH:SELECTOR",
                        help="faces to align: BRUSH:SELECTOR (SELECTOR = 'all' or comma indices) or "
                             "a bare brush Name (= all its polys). Use `-` to read the set from "
                             "stdin instead (bare names, or the BRUSH:idx lines `poly find` prints; "
                             "empty stdin is a clean no-op). The first face is the seam/seed.")
    palign.add_argument("--fresh-frame", dest="fresh_frame", action="store_true",
                        help="synthesize a canonical texture frame from the face normal instead of "
                             "adopting the seed face's frame (default). Adopt means: --wall/--floor "
                             "continue the seed's exact TextureU/V+Pan; --ring keeps the seed's texel "
                             "SCALE+Pan but re-derives U along the ring tangent and V along the axis")
    palign.add_argument("--fit-perimeter", dest="fit_perimeter", action="store_true",
                        help="--ring only: snap the texture scale so an integer number of texels "
                             "fits the perimeter (exact seam meet); default leaves the closing seam")
    _tree_flag(palign)

    level = sub.add_parser("level",
                           help="level lifecycle verbs "
                                "(create/list/materialize/preview/status/doctor)")
    lsub = level.add_subparsers(dest="sub", required=True)
    llist = lsub.add_parser(
        "list",
        help="list the project's levels (trunk dirs under <maps>), one name per line to stdout "
             "(pipe-friendly, e.g. `level list | ...`); a count and the active level go to stderr")
    llist.add_argument("--json", action="store_true",
                       help="emit a JSON array of {name, active} objects to stdout instead of the "
                            "plain one-name-per-line list (active = matches $UEDCLI_LEVEL)")
    lcreate = lsub.add_parser(
        "create",
        help="scaffold a NEW level (maps/<name>/) with a LevelInfo actor (required by materialize); "
             "to edit it, export UEDCLI_LEVEL=<name>")
    lcreate.add_argument("name", help="the new level's name (used as the maps/<name>/ directory)")
    lmat = lsub.add_parser(
        "materialize",
        help="build $UEDCLI_LEVEL's trunk into a .dx/.unr map file (pure build; no merge)")
    lmat.add_argument("--out", help="destination map file (.dx or .unr); refuses to overwrite "
                                    "an existing file unless --overwrite")
    lmat.add_argument("--overwrite", action="store_true",
                      help="permit overwriting an existing --out file (default: refuse, exit 2)")
    lmat.add_argument("--no-verify", action="store_true",
                      help="skip the post-build verify and write the .dx even if it would NOT match "
                           "the intended level — for debugging, or when verify is known-buggy")
    lmat.add_argument("--keep-build", action="store_true",
                      help="on a verify FAILURE, cp the built map out to the project's "
                           ".uedcli/tmp/ for inspection instead of discarding it "
                           "(default: discard on failure)")
    _tree_flag(lmat, level_only=True)   # build a named level explicitly instead of $UEDCLI_LEVEL

    lprev = lsub.add_parser(
        "preview",
        help="render freely-posed still shots of $UEDCLI_LEVEL. The default --game "
             "backend is the faithful lit in-game tier: a warm reused headless-game container "
             "renders truly-lit first-person frames (first batch ~1-3 min: boot + travel; later "
             "batches reuse the warm container). "
             "--native is the opt-in offline draft rasterizer (no editor, no container, no game): "
             "textured + flat-shaded, seconds per batch, but no lighting/meshes/sky.")
    lprev.add_argument("shots", nargs="*", metavar="SHOT",
                       help="one shot per token, fields ;-separated: 'at:X,Y,Z;rot:PITCH,YAW' "
                            "(camera eye + aim angles in unreal rotation units, 16384 = 90°; positive pitch looks up), "
                            "'at:X,Y,Z;look:X,Y,Z' or 'at:@Actor;rot:...' / 'at:X,Y,Z;look:@Actor' "
                            "(camera eye AT / aim AT an actor — resolved against the trunk, or with "
                            "--game --map against the RUNNING game, e.g. 'at:@PathNode7;rot:-8,90'), "
                            "or 'orbit:@Actor;radius:R;azimuth:A[;elev:B]' (camera on a ring of R uu "
                            "around the actor, aimed inward; azimuth/elev are ring angles in "
                            "degrees). Append ';name:STEM' to name the output file (default: "
                            "shot-01, shot-02, ...; never overwrites within a run). Omit shots only "
                            "with --list-actors")
    lprev.add_argument("--out-dir", dest="out_dir", metavar="DIR",
                       help="directory to write the PNG shots into (created if absent). Required "
                            "unless --list-actors")
    lprev.add_argument("--list-actors", dest="list_actors", metavar="Package.Class", default=None,
                       help="--game --map QUERY mode: instead of shooting, print the map's actors of "
                            "this class as 'Name x y z' (e.g. Engine.PathNode blankets every walkable "
                            "spot) — discover @Actor refs to compose into preview shots. Add --sample "
                            "N for N evenly-spread. No screenshots; --out-dir not needed")
    lprev.add_argument("--sample", type=int, default=0, metavar="N",
                       help="with --list-actors: print only N actors, evenly indexed across the map")
    lback = lprev.add_mutually_exclusive_group()
    lback.add_argument("--native", action="store_true",
                       help="OPT IN to the offline draft renderer (the DEFAULT is --game): carves "
                            "the trunk with the native CSG core and software-rasterizes textured, "
                            "flat-shaded stills in-process. Movers render at their base pose; point "
                            "actors, meshes, sky projection, lighting and translucency do not render "
                            "(draft tier — translucent/masked faces render opaque)")
    lback.add_argument("--game", action="store_true",
                       help="the faithful in-game renderer (the DEFAULT — passing it is optional): "
                            "delivers the map into a WARM "
                            "per-user headless game container (booted once ~90s, then REUSED "
                            "across previews; self-terminates after 10 min idle) and captures "
                            "truly-lit first-person frames (real lighting/sky/textures). Pitch "
                            "is clamped to ±89.9°; movers at rest pose. First batch ~1-3 min "
                            "(boot + travel); later batches skip the boot")
    lprev.add_argument("--size", default="1280x960", metavar="WxH",
                       help="output resolution in pixels (default 1280x960, 4:3; shared by both "
                            "backends)")
    lprev.add_argument("--fov", type=float, default=None, metavar="DEG",
                       help="horizontal field of view in degrees, --native only (default 75 — "
                            "the game's first-person default, Engine.PlayerPawn DesiredFOV). "
                            "Native renders true straight-up/down; --game renders at the game's "
                            "own FOV and clamps pitch host-side to ±89.9°")
    lprev.add_argument("--map", default=None, metavar="PATH",
                       help="--game only: preview a prebuilt map file (.dx/.unr) instead of the "
                            "$UEDCLI_LEVEL trunk (skips the materialize cache). Actor-relative shots "
                            "(at:@/look:@/orbit:@) ARE supported with --map — they resolve against "
                            "the RUNNING game (use --list-actors to discover names). Rejected with "
                            "--native")
    lprev.add_argument("--rebuild", action="store_true",
                       help="--game only: force a fresh materialize of the trunk under a new "
                            "unique name (guarantees the game reloads it, ignoring the cached "
                            "build and any resident package); rejected with --native (native "
                            "always renders the current trunk — it has no cache)")
    lprev.add_argument("--keep-alive", dest="keep_alive", action="store_true",
                       help="--game only: PIN the warm game container (disable its idle "
                            "self-death) and print its noVNC URL for live inspection; the pin "
                            "sticks across later previews until you release it with docker rm "
                            "-f. Rejected with --native (no container)")
    _tree_flag(lprev, level_only=True)  # preview a named level explicitly instead of $UEDCLI_LEVEL

    lstat = lsub.add_parser("status",
                            help="thin read-only dashboard for $UEDCLI_LEVEL (or a --tree "
                                 "box): actor counts, duplicate order_values, git state")
    lstat.add_argument("--json", action="store_true",
                       help="emit the status as a JSON object ({kind, name, actors:{total,brush,"
                            "point}, duplicate_order_values, git, texture_packages}) instead of the "
                            "text dashboard; with nothing selected it prints {\"selected\": null}")
    _tree_flag(lstat)     # inspect a named tree explicitly instead of $UEDCLI_LEVEL

    ldoc = lsub.add_parser(
        "doctor",
        help="detect BSP/geometry issues (holes, solidity, CSG order) — "
             "static, offline, no editor")
    ldoc.add_argument("--json", action="store_true",
                      help="emit findings as JSON instead of the text report")
    ldoc.add_argument("--severity", choices=["info", "warn", "error"], default=None,
                      help="show only findings at or above this severity (does NOT affect the "
                           "exit code, which always reflects all findings)")
    ldoc.add_argument("--category", default=None,
                      help="comma-separated categories to show (degenerate,watertight,convex,"
                           "planar,solidity,csg_order,scale); others are hidden")
    _tree_flag(ldoc)      # lint a named tree explicitly instead of $UEDCLI_LEVEL

    event = sub.add_parser(
        "event",
        help="analyse the level's Tag<->Event trigger wiring (who-triggers-whom). Offline, "
             "model-side, no editor. Sub-verbs: graph")
    evsub = event.add_subparsers(dest="sub", required=True)
    egraph = evsub.add_parser(
        "graph",
        help="print $UEDCLI_LEVEL's trigger wiring — one edge per line "
             "'Src (Class) --Event--> Dst (Class)' — plus a lint (dangling wires, unreachable "
             "movers, cycles) on stderr. An edge A->B means actor A's Event property equals actor "
             "B's Tag property (A fires the event B listens for). Reads the trunk model-side; exits "
             "0 even with lint findings (a query verb — lint is advisory)")
    egout = egraph.add_mutually_exclusive_group()
    egout.add_argument(
        "--dot", action="store_true",
        help="emit the graph as Graphviz DOT to stdout (pipe into `dot -Tpng -o wiring.png`) "
             "instead of the one-edge-per-line text; the lint still goes to stderr")
    egout.add_argument(
        "--json", action="store_true",
        help="emit a structured {nodes, edges, lint} JSON object to stdout (lint folded IN, not "
             "on stderr) instead of the text wiring — for scripts")
    _tree_flag(egraph)    # analyse a named tree explicitly instead of $UEDCLI_LEVEL

    project = sub.add_parser("project", help="inspect the resolved uedcli project")
    prsub = project.add_subparsers(dest="sub", required=True)
    pshow = prsub.add_parser("show",
                     help="print the resolved project root, its game, the managed dirs "
                          "(maps/prefabs/catalog), and the composed package search path (each "
                          "entry tagged project/base)")
    pshow.add_argument("--json", action="store_true",
                       help="emit the resolved project as JSON ({root, game, maps, prefabs, "
                            "catalog, search_path:[{path, provenance}]}) instead of the text report")

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

    stash = sub.add_parser(
        "stash",
        help="capture/replay named actor sets (private register); edit a stored one in place with "
             "any content verb + --tree stash/<id>")
    stsub = stash.add_subparsers(dest="sub", required=True)

    cap = stsub.add_parser("capture", help="capture actors into a register entry")
    cap.add_argument("names", nargs="*", help="actors to capture; empty with --from-* = all")
    cap.add_argument("--id", default=None, help="register id (default: auto-slug)")
    cap.add_argument("--force", action="store_true", help="overwrite an existing --id")
    cap.add_argument("--from-t3d", dest="from_t3d", nargs="+", default=None, metavar="FILE",
                     help="capture from these T3D file(s) instead of $UEDCLI_LEVEL, or - for a T3D "
                          "stream on stdin. Multiple files concatenate in order; - is the sole value "
                          "if present. (`names` still selects a subset of the source)")
    _tree_flag(cap)       # name the SOURCE tree explicitly instead of $UEDCLI_LEVEL;
                            # only consulted when --from-t3d is not given

    stshow = stsub.add_parser("show", help="dump a register entry's T3D (default) or --summary")
    stshow.add_argument("id", help="register id to show")
    stshow.add_argument("names", nargs="*", help="actor subset; empty = whole set")
    stshow.add_argument("--summary", action="store_true",
                        help="print a one-line-per-actor summary instead of the full T3D")

    stsub.add_parser("list", help="list stash register ids")

    stprev = stsub.add_parser("preview", help="composite render of a register entry")
    stprev.add_argument("id", help="register id to render")
    stprev.add_argument("names", nargs="*", help="actor subset; empty = whole set")
    _preview_opts(stprev)

    stsub.add_parser("drop", help="remove a register entry").add_argument(
        "id", help="register id to remove")

    stapply = stsub.add_parser("apply", help="merge a register entry into $UEDCLI_LEVEL")
    stapply.add_argument("id", help="register id to merge")
    _apply_flags(stapply)

    stpromote = stsub.add_parser("promote", help="register -> durable library (the sharing step)")
    stpromote.add_argument("id", help="register id to promote")
    stpromote.add_argument("--as", dest="as_name", required=True, metavar="NAME",
                           help="name for the entry in the durable prefab library")
    stpromote.add_argument("--force", action="store_true",
                           help="overwrite an existing library entry of the same name")
    stpromote.add_argument("--prefab-dir", dest="prefab_dir", default=None,
                           help="override the library root (default: the resolved project's "
                                "prefabs dir; without a project this flag is required)")


    prefab = sub.add_parser(
        "prefab",
        help="the durable shared prefab library (tier 2); edit a stored one in place with any "
             "content verb + --tree prefab/<name>")
    prefab.add_argument("--prefab-dir", dest="prefab_dir", default=None,
                        help="override the library root (default: the resolved project's prefabs "
                             "dir; without a project this flag is required)")
    pfsub = prefab.add_subparsers(dest="sub", required=True)
    pfsub.add_parser("list", help="list prefab names in the durable library")
    pfshow = pfsub.add_parser("show", help="dump a prefab's T3D (default) or --summary")
    pfshow.add_argument("name", help="prefab name to show")
    pfshow.add_argument("names", nargs="*", help="actor subset; empty = whole set")
    pfshow.add_argument("--summary", action="store_true",
                        help="print a one-line-per-actor summary instead of the full T3D")
    pfprev = pfsub.add_parser("preview", help="composite render of a prefab")
    pfprev.add_argument("name", help="prefab name to render")
    pfprev.add_argument("names", nargs="*", help="actor subset; empty = whole set")
    _preview_opts(pfprev)
    pfapply = pfsub.add_parser("apply", help="merge a prefab into $UEDCLI_LEVEL")
    pfapply.add_argument("name", help="prefab name to merge")
    _apply_flags(pfapply)
    pfsub.add_parser("drop", help="remove a prefab from the durable library").add_argument(
        "name", help="prefab name to remove")

    def _csv(text: str) -> list[str]:
        return [s.strip() for s in text.split(",") if s.strip()]

    texture = sub.add_parser("texture", help="offline texture catalog (no level needed)")
    texsub = texture.add_subparsers(dest="sub", required=True)

    tsync = texsub.add_parser("sync", help="discover substrate packages, export textures, "
                                           "(re)build the per-package manifest")
    tsync.add_argument("--package", help="sync only this package (bare name); else all packages")
    tsync.add_argument("--force", action="store_true",
                       help="re-export even if the package file hash is unchanged")
    tsync.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tlist = texsub.add_parser("list", help="list catalog entries (offline, manifest-only)")
    tlist.add_argument("--package", help="restrict to one package")
    tlg = tlist.add_mutually_exclusive_group()
    tlg.add_argument("--unclassified", action="store_true", help="only entries never classified")
    tlg.add_argument("--classified", action="store_true", help="only classified entries")
    tlg.add_argument("--stale", action="store_true", help="only entries flagged for reclassification")
    tlg.add_argument("--removed", action="store_true", help="only entries gone from their package")
    tlist.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tsearch = texsub.add_parser("search", help="find texture refs by text/tag/color (ranked)")
    tsearch.add_argument("query", nargs="?", default=None,
                         help="text matched (AND) over name/tags/description; optional if "
                              "--tag/--color given")
    tsearch.add_argument("--tag", action="append", default=[], help="exact tag filter (repeatable)")
    tsearch.add_argument("--color", action="append", default=[],
                         help="palette-name color filter (repeatable, OR)")
    tsearch.add_argument("--package", help="restrict to one package")
    tsearch.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    ttags = texsub.add_parser("tags", help="list the tag vocabulary + counts")
    ttags.add_argument("--package", help="restrict to one package")
    ttags.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tclass = texsub.add_parser("classify", help="record/inspect texture classification")
    tcsub = tclass.add_subparsers(dest="csub", required=True)
    tcstat = tcsub.add_parser("status", help="classified/unclassified/stale/removed counts")
    tcstat.add_argument("--full", action="store_true", help="also list the unclassified+stale worklist")
    tcstat.add_argument("--package", help="restrict to one package")
    tcstat.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)
    tcset = tcsub.add_parser("set", help="set one texture's classification (replaces given fields)")
    tcset.add_argument("ref", help="texture ref, e.g. DeusExDeco.Wood (3-part on collision)")
    tcset.add_argument("--tags", type=_csv, default=None, help="comma list; replaces all tags")
    tcset.add_argument("--description", default=None, help="replaces the description")
    tcset.add_argument("--colors", type=_csv, default=None,
                       help="comma list of palette names; replaces the colors (sets source=set)")
    tcset.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    substrate = sub.add_parser("substrate", help="substrate build utilities (package stubbing)")
    subsub = substrate.add_subparsers(dest="sub", required=True)
    stub = subsub.add_parser(
        "stub", help="convert a Deus Ex v68 code package into a UED22-loadable v69 stub `.u`")
    stub.add_argument("package", nargs="?",
                      help="Deus Ex v68 code package to stub (bare name, no .u), e.g. DeusExItems")
    stub.add_argument("--force", action="store_true",
                      help="rebuild even if a current cache entry exists (bypass the cache hit)")
    stub.add_argument("--list", action="store_true",
                      help="print the stub cache manifest and exit (no build)")

    cache = sub.add_parser(
        "cache", help="manage the per-user derivable caches under ~/.uedcli/cache")
    cachesub = cache.add_subparsers(dest="sub", required=True)
    cachesub.add_parser(
        "clear",
        help="delete the persistent package-schema cache (~/.uedcli/cache/schema); it is pure "
             "derivable throwaway and rebuilds on the next command. Use for the schema-cache "
             "escape-hatch/paranoid case or to reclaim old decoder-version (v<N>/) dirs.")
    gc = cachesub.add_parser(
        "gc",
        help="shrink the package-schema cache without emptying it: delete the orphaned old "
             "decoder-version (v<N>/) dirs, then evict current-version entries least-recently-used "
             "until the cache fits its size/count cap. Cached entries are derivable, so an evicted "
             "one simply re-decodes the next time it is needed. Runs automatically (best-effort) "
             "after a cache write; this is the on-demand surface.")
    gc.add_argument("--max-bytes", type=int, metavar="N", default=None,
                    help="evict until the cache holds at most N bytes (default: the built-in cap, "
                         "256 MiB, or $UEDCLI_SCHEMA_CACHE_MAX_BYTES). 0 evicts everything.")
    gc.add_argument("--max-entries", type=int, metavar="N", default=None,
                    help="evict until the cache holds at most N blob files (default: no count cap "
                         "unless $UEDCLI_SCHEMA_CACHE_MAX_ENTRIES sets one). 0 evicts everything.")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from .dispatch import dispatch
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
