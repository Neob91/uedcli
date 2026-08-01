"""Internal argument types for the parser tier: the scalar converters, the
negative-coordinate parser `_CoordArgumentParser`, and the flags/helpers shared
across command families (`_preview_opts`, `_tree_flag`, `_apply_flags`)."""
from __future__ import annotations

import argparse
import math
import re
from decimal import Decimal, InvalidOperation

from ...model import Vec3
from ...preview import DEFAULT_ANNOTATIONS


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


def parse_decimal(text: str) -> Decimal:
    """Parse ONE scalar number into an exact Decimal — the single validator every
    Decimal-valued CLI argument goes through.

    The bare `Decimal` constructor must NEVER be used as an argparse `type=`, for two
    independent reasons this function fixes:

    1. **Non-numeric input escapes as a traceback.** argparse only converts `ValueError`
       and `TypeError` into a clean parser error; `Decimal("abc")` raises
       `decimal.InvalidOperation`, which is an `ArithmeticError` — so it propagates out of
       argparse as a raw traceback, breaking "no Python exception ever reaches the user".
    2. **`Decimal` ACCEPTS `"nan"`, `"snan"` and `"inf"`.** They construct fine and then
       misbehave silently downstream: a NaN coordinate compares false against everything,
       an infinite one matches every actor on that axis, and a signaling NaN raises an
       `InvalidOperation` from deep inside later arithmetic rather than at parse time.

    Both cases raise `ArgumentTypeError`, which argparse turns into a clean message naming
    the offending value plus exit 2. Accepts optional surrounding whitespace.

    **What this does NOT guarantee: that no infinite value reaches the geometry layer.** It
    rejects the non-finite SPELLINGS, and `Decimal` has arbitrary exponent range, so
    `1e999999999` is a perfectly finite `Decimal` and passes — then becomes `inf` when a
    computed-geometry module converts it to `float`. That overflow lives at the
    `Decimal`→`float` boundary, not here, and closing it means bounding coordinates to what a
    float can represent (see `board/inbox/`, "`parse_decimal` admits an INFINITY by another
    spelling"). Nothing observable breaks today — such a value ends as a clean no-op or a clean
    `GeometryError` — but do not read this validator as a range check."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None
    if not value.is_finite():
        raise argparse.ArgumentTypeError(f"number must be finite, got {text!r}") from None
    return value


def parse_coord(text: str) -> Vec3:
    """Parse a single `X,Y,Z` coordinate token into an exact Decimal triple.

    Decimal (not float) so authored fractional coords carry no binary-representation
    drift and match stored vertices exactly. Accepts integers and decimals, optional
    surrounding whitespace. Each component goes through `parse_decimal`, so a non-numeric
    OR non-finite (`nan`/`snan`/`inf`) component raises ArgumentTypeError (clean CLI
    error), never a traceback and never a silently poisoned coordinate.

    The component's OWN reason is carried through verbatim — "expected a number" and "must be
    finite" are different mistakes and must not collapse into one message: telling someone who
    typed `abc` that it "must be finite" describes a problem their input does not have."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"coordinate must be X,Y,Z (3 comma-separated numbers), got {text!r}"
        )
    try:
        return tuple(parse_decimal(p) for p in parts)
    except argparse.ArgumentTypeError as e:
        raise argparse.ArgumentTypeError(f"coordinate {text!r}: {e}") from None


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
    # `parse_decimal` rejects both the non-numeric component and the non-finite one
    # ("nan"/"snan"/"inf" all CONSTRUCT as Decimals): a NaN would raise a signaling
    # InvalidOperation from the min/max below, and an infinity would silently match every
    # actor on that axis. A bbox coord must be a finite number. The component's own reason is
    # carried through — "expected a number" and "must be finite" are different mistakes.
    try:
        nums = [parse_decimal(p) for p in parts]
    except argparse.ArgumentTypeError as e:
        raise argparse.ArgumentTypeError(f"bbox {text!r}: {e}") from None
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
    pan is integer-only, decimal pan is a deferred fast-follow).

    Pan does NOT go through `parse_decimal`: it is int-valued, and `int()` already rejects
    every non-finite spelling (`int("nan")`/`int("inf")` raise `ValueError`, which argparse
    converts cleanly) as well as any non-integer text. A regression test pins that."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"pan must be U,V (2 comma-separated integers), got {text!r}")
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        raise argparse.ArgumentTypeError(f"pan has a non-integer component: {text!r}")


def parse_factor_pair(text: str) -> tuple[float, float]:
    """Parse a single `FU,FV` pair of positive scale factors (`brush poly scale --by`).

    Float-valued, unlike `parse_pan`: a texture scale is a ratio, and `--by 1.5,1.5` is an ordinary
    request. It does NOT go through `parse_decimal` — the texture frame is stored and computed in
    float throughout (`architecture.md` "Coords": texture vectors stay float; only vertex/Location
    coords are `Decimal`), so a Decimal here would only be converted back.

    `float()` accepts `nan`/`inf`, so those are rejected explicitly rather than reaching the model
    as a texture axis of infinite length. The ZERO/NEGATIVE rejection deliberately lives in the
    model (`surface.apply_scale`) instead, so a programmatic caller is covered by it too; this
    validates the SHAPE of the token."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"scale must be FU,FV (2 comma-separated numbers), got {text!r}")
    out = []
    for p in parts:
        try:
            value = float(p)
        except ValueError:
            raise argparse.ArgumentTypeError(f"scale has a non-numeric component: {text!r}")
        if not math.isfinite(value):
            raise argparse.ArgumentTypeError(f"scale factor must be finite: {text!r}")
        out.append(value)
    return (out[0], out[1])


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
    pp.add_argument("--faces", default="wire", choices=["wire", "flat", "textured"],
                    help="how brush faces are drawn (default 'wire'). 'wire' = outlines only, the "
                         "schematic — needs no game content. 'flat' = every face also filled solid in "
                         "its brush's colour, the nearest face winning per pixel, with the wireframe "
                         "kept over it in the paler/darker partner of that same brush colour so the "
                         "outlines read against their own fills: a diagram of what occludes what. "
                         "'textured' = each face filled by sampling its OWN texture through its authored "
                         "UV frame (Origin/TextureU/TextureV/Pan), NO wireframe — so alignment, panning, "
                         "mirroring and tiling are visible offline (no editor, no container, no "
                         "lighting). Under BOTH 'flat' and 'textured' a SUBTRACT brush "
                         "shows only its far (interior) faces, so geometry inside a subtracted room "
                         "stays visible instead of being hidden by a solid box. 'flat' and 'textured' "
                         "both LOAD the game's class hierarchy (to tell a mover, which is never carved "
                         "into the world, from a real subtraction), so unlike 'wire' they need BOTH a "
                         "resolved project and the per-user games config — 'wire' needs neither and "
                         "works on --from-t3d from anywhere. 'textured' additionally needs every texture "
                         "the scene references to be readable, and rejects --brush-colors and any scaled "
                         "or sheared brush")
    pp.add_argument("--brush-colors", dest="brush_colors", default=None, choices=["csg", "legend"],
                    help="how to colour brushes — both the wireframe and the '--faces flat' fills: "
                         "'csg' (the default) = by CSG op (added blue, subtracted gold, semisolid pink, "
                         "nonsolid green, mover magenta); 'legend' = each brush in its own per-actor "
                         "legend tint (drops the CSG cue but tells same-op brushes apart at a glance, "
                         "matching the legend swatches)")
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
                         "BRUSH:all work too) — those polys draw with a bolder line, in their brush's "
                         "vivid CSG hue under --faces wire; under --faces flat the highlighted face "
                         "also swaps its fill for the other member of its brush's colour pair, which is "
                         "what makes it stand out from its neighbours over an opaque fill. Under flat it "
                         "re-colours what is VISIBLE and never x-rays: a face hidden behind something at "
                         "this --view draws nothing. A stderr note names any selector that ended up not "
                         "visible for ANY reason — hidden, culled, or outside the frame. A token "
                         "WITHOUT a colon is an ACTOR NAME: a brush actor "
                         "highlights ALL its polys; a point actor gets corner brackets (a selection "
                         "reticle) framing its sprite/marker")
    pp.add_argument("--focus", metavar="BRUSH", default=None,
                    help="spotlight ONE brush: only it shows face indices (in its label tint); "
                         "every OTHER brush recedes — its wireframe to faint (dimmed) lines, and under "
                         "--faces flat its fills to a faint wash of their own colour. It changes "
                         "BRIGHTNESS ONLY, never what is visible or what hides what: a crate inside a "
                         "subtracted room stands in front of the room's far wall, a brush between the "
                         "camera and the focused one still covers it, and a brush sealed inside a solid "
                         "added brush stays hidden. All "
                         "actor names still appear in the legend. --highlight OVERRIDES this — a "
                         "highlighted poly/actor stays vivid+bold and undimmed and keeps its index even "
                         "when its brush is not the focus — but under --faces flat it does not x-ray: a "
                         "highlighted face that something in front of it hides draws nothing. "
                         "An unknown name / a point actor → clean exit 2. "
                         "Not applied under --layout breakdown, which focuses each pane itself (a value "
                         "is still validated)")
    pp.add_argument("--show", default="", metavar="SET",
                    help="comma-set (union) of range overlays to draw for POINT actors (default none): "
                         "'collision' = a faint light-red collision cylinder for every colliding point "
                         "actor (bCollideActors true) — a circle in TOP, a 2·radius × 2·height rect in "
                         "FRONT/SIDE, an 8-sided wire cylinder in ISO; 'light-range' = a faint orange "
                         "sphere of a light's reach (25·(LightRadius+1) UU); 'sound-range' = a faint "
                         "blue sphere of an AmbientSound's reach (25·(SoundRadius+1) UU). Brush actors "
                         "(incl. movers) are excluded, so under --faces wire their preview stays "
                         "schema-free (no class lookup). --faces flat does look classes up, but only to "
                         "tell a mover from a real subtraction for its face cull — it draws no extra "
                         "overlay")
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
