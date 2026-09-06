"""`brush` command-family parser registrar (build/edit/poly/vertex)."""
from __future__ import annotations

import argparse
from decimal import Decimal

from ._arguments import (
    _nonempty,
    parse_coord,
    parse_decimal,
    parse_factor_pair,
    parse_pan,
    _tree_flag,
)


def register(sub) -> None:
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
                    help="explicit world pivot (with --by only; default: the LOCATION of the set "
                         "member nearest the bbox center — an authored point, so the pivot keeps "
                         "the grid you built on and a lone brush mirrors/scales in place)")
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
    clip = bsub.add_parser(
        "clip",
        help="clip every brush in a piped T3D SET by one world plane, keeping one half; T3D to "
             "stdout (stateless; no level). To clip a placed actor: `actor show X | brush clip - "
             "… | brush replace X -`")
    clip.add_argument(
        "set", metavar="-|FILE",
        help="read the brush SET as a T3D snippet from stdin (`-`) or from a saved FILE (the "
             "`brush build … | brush clip - | actor add -` convention). `-` is the sole names "
             "source. A non-brush (point) actor is refused (exit 2). Empty stdin is a clean no-op "
             "(exit 0)")
    clip.add_argument("--axis", choices=["x", "y", "z"],
                      help="axis-aligned plane; use with --offset")
    clip.add_argument("--offset", type=parse_decimal,
                      help="plane offset along --axis, in world units")
    clip.add_argument("--plane", type=parse_coord, nargs=2,
                      metavar=("PX,PY,PZ", "NX,NY,NZ"),
                      help="general plane: a world point on it (PX,PY,PZ) plus its normal "
                           "(NX,NY,NZ); need not be unit")
    clip.add_argument("--keep", choices=["below", "above"], default="below",
                      help="keep the half below the plane (opposite the normal — DEFAULT) or "
                           "above (the normal side)")

    snap = bsub.add_parser(
        "snap",
        help="round every brush's near-grid LOCAL vertices in a piped T3D SET to a grid; T3D to "
             "stdout (stateless; no level). Cleans float noise / slop that causes BSP holes while "
             "preserving intentional off-grid angles. To snap a placed actor: `actor show X | brush "
             "snap - … | brush replace X -`")
    snap.add_argument(
        "set", metavar="-|FILE",
        help="read the brush SET as a T3D snippet from stdin (`-`) or from a saved FILE. `-` is the "
             "sole names source. A non-brush (point) actor is refused (exit 2). Empty stdin is a "
             "clean no-op (exit 0)")
    snap.add_argument("--grid", type=parse_decimal, required=True, metavar="N",
                      help="grid size in world units to round each LOCAL vertex component to "
                           "(e.g. 16, 8, 1). Required — no default grid")
    snap.add_argument("--tolerance", type=parse_decimal, required=True, metavar="T",
                      help="max distance in world units from the nearest grid line to snap. A "
                           "component farther than T from the grid is LEFT IN PLACE, so intentional "
                           "off-grid geometry (angled, rotated, curved) is preserved and only "
                           "near-grid float noise is cleaned. Snapping is per-axis: a slant vertex "
                           "keeps its off-grid axis and snaps the others. Rounds half toward "
                           "+infinity. Required — no default tolerance")

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
                      help="prism height along its long axis (--axis, Z by default), in world units (uu)")
    bcyl.add_argument("--radius", type=float, required=True, help="circumscribed radius")
    bcyl.add_argument("--sides", type=int, default=8, help="polygon side count (default 8)")
    bcyl.add_argument("--align-to-side", dest="align_to_side", action="store_true",
                      help="turn a FACE rather than a vertex toward the axes, by offsetting the "
                           "cross-section half a segment (180/--sides degrees). Without it vertex "
                           "0 sits on the cross-section's first axis (+X at --axis z), so an "
                           "octagonal pillar meets an axis-aligned wall on a "
                           "CORNER, leaving two thin wedge gaps; with it a flat face sits flush. "
                           "Same parameter as UnrealEd's own CylinderBuilder AlignToSide checkbox. "
                           "For any other cross-section angle use --rotate, which is whole-actor "
                           "placement")
    bcyl.add_argument(
        "--axis", choices=["x", "y", "z"], default="z",
        help="world axis the prism's long axis runs along — the axis its n-gon cross-section is "
             "NORMAL to (default z, the current +Z prism). Builds the vertices oriented directly and "
             "emits NO Rotation field, so a horizontal pipe/beam needs no --rotate. The (u,v) map "
             "onto the other two world axes in right-handed cyclic order, matching extrude/revolve: "
             "z -> cross-section in X,Y; x -> Y,Z; y -> Z,X. For any other orientation use --rotate")
    _common_build_opts(bcyl)

    bcone = bshape.add_parser("cone", help="n-faced cone (height, base radius, sides)")
    bcone.add_argument("--height", type=float, required=True,
                       help="cone height (base to apex) along its long axis (--axis, Z by default), in world units (uu)")
    bcone.add_argument("--radius", type=float, required=True, help="base circumscribed radius")
    bcone.add_argument("--sides", type=int, default=8, help="polygon side count (default 8)")
    bcone.add_argument("--align-to-side", dest="align_to_side", action="store_true",
                       help="turn a FACE of the base ring rather than a vertex toward the axes, "
                            "by offsetting it half a segment (180/--sides degrees), so the cone "
                            "sits flush against an axis-aligned wall instead of meeting it on a "
                            "corner. Same parameter as UnrealEd's own AlignToSide checkbox; for "
                            "any other angle use --rotate")
    bcone.add_argument(
        "--axis", choices=["x", "y", "z"], default="z",
        help="world axis the cone's long axis runs along — the axis its base-ring cross-section is "
             "NORMAL to (default z, the current +Z cone). Builds the vertices oriented directly and "
             "emits NO Rotation field, so a horizontal cone needs no --rotate. The (u,v) map onto "
             "the other two world axes in right-handed cyclic order, matching extrude/revolve: "
             "z -> cross-section in X,Y; x -> Y,Z; y -> Z,X. For any other orientation use --rotate")
    _common_build_opts(bcone)

    bsheet = bshape.add_parser("sheet", help="flat two-sided non-solid panel (width, height)")
    bsheet.add_argument("--width", type=float, required=True,
                        help="panel size along the plane's first axis, in world units (uu)")
    bsheet.add_argument("--height", type=float, required=True,
                        help="panel size along the plane's second axis, in world units (uu)")
    bsheet.add_argument("--plane", choices=["xy", "xz", "yz"], default="xz",
                        help="world plane the sheet lies in (default xz)")
    from ...query import PF_NAMES as _PF_NAMES
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
        "engine (`level photo --game`) build such a brush correctly, but the offline draft "
        "renderer `level photo --native` assumes convex solids and draws a concave notch FILLED "
        "IN — a rendering artefact, not a geometry bug."
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

    # poly lives UNDER brush (a brush sub-element editor, peer to `brush vertex`).
    poly = bsub.add_parser("poly", help="per-surface (polygon) query/edit verbs")
    psub = poly.add_subparsers(dest="polysub", required=True)
    pl = psub.add_parser("list", help="list a brush's polys: facing/texture/flags/pan/centroid/area")
    pl.add_argument("name", help="brush actor Name to list polys of (case-insensitive)")
    pl.add_argument("--json", action="store_true",
                    help="emit the polys as JSON ({actor, polys:[…]}, each poly with idx/facing/"
                         "texture/flags/pan/centroid/area/nverts) instead of the aligned text table")
    _tree_flag(pl)

    from ...query import PF_NAMES
    flag_names = [name for _, name in PF_NAMES]
    # The per-face target grammar shared by `set`/`pan`/`rotate`/`scale`. Deliberately NARROWER than
    # `align`'s, which also takes a bare brush Name: a whole brush is a meaningful unit for a mode
    # ("wrap this cylinder"), whereas a whole-brush pan/rotate/scale is a blanket nudge of every face
    # including the ones the author never looked at — so `Tower:all` makes "yes, all of them" a
    # deliberate act rather than a name typed one selector short.
    _POLY_TARGETS_HELP = (
        "BRUSH:SELECTOR (SELECTOR = 'all' or comma-separated poly indices); repeatable, e.g. "
        "Wall1:3,5 Wall2:all. A bare brush name is NOT accepted — say Wall1:all. Or the single "
        "token - to read the targets from stdin (the BRUSH:idx lines `brush poly find` and every "
        "per-face verb print); - is the sole source, not mixable with BRUSH:SELECTOR args, and "
        "empty stdin is a clean no-op (exit 0)")

    pset = psub.add_parser(
        "set", help="assign stored per-face ATTRIBUTES (texture, surface flags), model-side")
    pset.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR", help=_POLY_TARGETS_HELP)
    pset.add_argument("--texture", default=None, metavar="REF",
                      help="qualified Package[.Group].Name (e.g. DeusExDeco.Textures.Wood); "
                           "omit the group unless given one explicitly")
    pset.add_argument("--add-flag", dest="add_flags", action="append", default=[],
                      type=str.lower, choices=flag_names, metavar="FLAG",
                      help="repeatable; surface flag by name (case-insensitive), not bit value")
    pset.add_argument("--remove-flag", dest="remove_flags", action="append", default=[],
                      type=str.lower, choices=flag_names, metavar="FLAG",
                      help="repeatable; surface flag by name (case-insensitive), not bit value")
    _tree_flag(pset)

    # `pan`/`rotate`/`scale`: the texture-FRAME transforms, peers of `align`. They are separate
    # verbs from `set` because assigning a stored attribute and transforming the frame are different
    # jobs (dev/docs/rationale/surface.md "The verb split: attributes vs the frame").
    ppan = psub.add_parser(
        "pan", help="shift a face's texture by whole texels (the Pan field); never moves the frame")
    ppan.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR", help=_POLY_TARGETS_HELP)
    ppanm = ppan.add_mutually_exclusive_group(required=True)
    ppanm.add_argument("--to", dest="pan_to", type=parse_pan, metavar="U,V",
                       help="set the absolute integer texel pan. --to 0,0 CLEARS the pan (that is "
                            "the unpanned state — `brush poly list` then shows - in the pan column)")
    ppanm.add_argument("--by", dest="pan_by", type=parse_pan, metavar="U,V",
                       help="offset the current pan by this many texels (an unset pan counts as "
                            "0,0); negatives allowed, e.g. --by -5,3")
    _tree_flag(ppan)

    prot = psub.add_parser(
        "rotate", help="turn a face's texture within its own plane (no continuity across faces)")
    prot.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR", help=_POLY_TARGETS_HELP)
    prot.add_argument("--by", dest="by", type=int, required=True, metavar="UU",
                      help="turn angle in UNREAL ROTATION UNITS (16384 = 90 degrees, 65536 = a full "
                           "turn), matching `brush build --rotate` and `mover key rotate`. Negative "
                           "turns the other way (--by -16384 == --by 49152). Turn direction follows "
                           "the VISIBLE surface normal, so it looks the same from where you stand "
                           "whether the face is the outside of an added pillar or the inside of a "
                           "subtracted room. That needs the brush's CsgOper to be CSG_Add or "
                           "CSG_Subtract (absent counts as CSG_Add): ANY other value exits 2 naming "
                           "it, because a brush with no inside and outside gives the turn no "
                           "direction to follow. A MIRRORED brush (scale determinant negative, i.e. "
                           "an odd number of negative components) does still invert it. There is "
                           "deliberately no --to: an absolute angle could only be measured against "
                           "an internal canonical frame whose in-plane direction you cannot see or "
                           "predict, so it would mean something different per face — reaching for a "
                           "KNOWN orientation is what `brush poly align` is for. The face's own "
                           "centre keeps its texture coordinate, so the texture spins in place "
                           "rather than sliding; each face pivots about ITSELF, so this breaks the "
                           "seams `align` matched")

    _tree_flag(prot)

    pscl = psub.add_parser(
        "scale", help="resize a face's texture in place (no continuity across faces)")
    pscl.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR", help=_POLY_TARGETS_HELP)
    psclm = pscl.add_mutually_exclusive_group(required=True)
    psclm.add_argument("--by", dest="by", type=parse_factor_pair, metavar="FU,FV",
                       help="multiply the texture's APPARENT SIZE: --by 2,2 makes it look twice as "
                            "big, --by 0.5,1 halves its width only. U and V are independent. "
                            "(Internally this DIVIDES the stored TextureU/TextureV magnitudes, "
                            "because T3D density is texels per world unit — the flag is named for "
                            "what you see.) Factors must be positive. The face's own centre keeps "
                            "its texture coordinate, so the texture grows in place rather than "
                            "sliding off; scale BEFORE `brush poly align run`, never after, since "
                            "the run's seam phases are computed for the density they saw. Pure "
                            "math — needs no project")
    psclm.add_argument("--to", dest="to", type=parse_factor_pair, metavar="U,V",
                       help="set the ABSOLUTE density in WORLD UNITS PER TILE: --to 128,128 means "
                            "the face's own bound texture repeats every 128 uu each way (how a "
                            "level designer thinks about it) — a SMALLER U,V looks like a BIGGER "
                            "texture (fewer, larger tiles). Needs a project on the package path to "
                            "read that texture's pixel size; a face with no bound texture, or an "
                            "unresolvable ref, exits 2 naming every offender before writing "
                            "anything. U and V are independent and must be positive")
    _tree_flag(pscl)

    # `poly move`: a GEOMETRY verb (not a texture-frame transform) — translate whole faces. Peer of
    # `brush vertex move`, sharing the poly texture verbs' BRUSH:SELECTOR grammar. Plain required
    # `--by`, not a one-member group (mirrors `scale`; `--to` centroid-target is deferred to v2).
    pmove = psub.add_parser(
        "move", help="translate whole faces: move every vertex of each face by a world delta")
    pmove.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR", help=_POLY_TARGETS_HELP)
    pmove.add_argument("--by", dest="by", type=parse_coord, required=True, metavar="DX,DY,DZ",
                       help="world delta added to every vertex of each selected face. Moves the "
                            "brush's WELDED corners, so a corner shared with an UNSELECTED face moves "
                            "too and that neighbour deforms. Most non-axis-aligned moves push a "
                            "neighbour non-planar and are REJECTED (exit 2); moving a face along its "
                            "own normal is the safe case. Rotation/PrePivot/scale-aware, per brush")
    _tree_flag(pmove)

    # `poly find`: a stateless PRODUCER — prints matching `BRUSH:idx` selectors (one per line) that
    # `brush poly align -` / `brush poly set` consume. Narrows a brush's faces by intrinsic labels.
    pfind = psub.add_parser(
        "find", help="print matching faces of one or more brushes as BRUSH:idx selectors (feed to "
                     "poly align/set)")
    pfind.add_argument("names", nargs="*", metavar="NAME",
                       help="brush actor Name(s) to search (case-insensitive), or the single token "
                            "- to read the set from stdin (bare names, or the BRUSH:idx lines a "
                            "prior find/per-face verb prints — the :idx is stripped to the brush). "
                            "- is the sole source, not mixable; empty stdin is a clean no-op. Omit "
                            "entirely (no names, no -) to search every brush in the level. A "
                            "non-brush actor is warned and skipped; an unknown name is an error")
    pfind.add_argument("--item", default=None, metavar="NAME",
                       help="keep only faces whose builder ItemName equals NAME (case-insensitive; "
                            "e.g. Side to drop a cylinder's Cap faces)")
    pfind.add_argument("--facing", default=None, metavar="SPEC",
                       help="keep only faces whose VISIBLE normal matches SPEC (';'=AND, ','=OR on "
                            "one axis, '..'=range). Presets: flat|wall|ramp (orientation) and "
                            "floor|ceiling (up/down role). Or AXIS:SPEC on nx|ny|nz components in "
                            "[-1,1], e.g. 'floor', 'wall;ny:0.7..1', 'nz:-1,1' (flat), 'nx:1'. "
                            "Polarity is resolved for subtract brushes, so 'floor' is the walkable "
                            "surface even in a carved room")
    pfind.add_argument("--texture", default=None, metavar="REF",
                       help="keep only faces textured with REF (case-insensitive; exact ref or its "
                            "last dot-component)")
    pfind.add_argument("--json", action="store_true",
                       help="emit the matches as a JSON array of "
                            "{brush,poly,item,normal,orientation,role,texture} objects instead of "
                            "BRUSH:idx lines")
    _tree_flag(pfind)

    # `poly align`: make a texture flow continuously across a face set (model-side). The geometry
    # MODE is a SUBCOMMAND (wall/floor/run), not a flag — each mode's flags are disjoint (only `run`
    # takes --fit-perimeter), so `-h` per mode lists exactly what applies, mirroring `brush build
    # <shape>`. Every mode writes a canonical frame (unit density, Pan zeroed).
    palign = psub.add_parser(
        "align", help="align faces' texture frames: wall|floor|run flow continuously across a set, "
                     "one-tile fits each face independently")
    pamode = palign.add_subparsers(dest="align_mode", required=True)

    # Targets grammar shared by all three modes: BRUSH:SELECTOR positionals or a bare brush Name
    # (= all its polys — a whole brush IS the natural unit of a mode), or `-` for stdin.
    _ALIGN_TARGETS_HELP = (
        "faces to align: BRUSH:SELECTOR (SELECTOR = 'all' or comma indices) or a bare brush Name "
        "(= all its polys). Use `-` to read the set from stdin instead (bare names, or the "
        "BRUSH:idx lines `poly find` prints; empty stdin is a clean no-op)")

    pawall = pamode.add_parser(
        "wall", help="stamp a world-projected frame on each VERTICAL face (brickwork does not reset "
                     "at each brush edge)")
    pawall.add_argument("targets", nargs="*", metavar="BRUSH:SELECTOR", help=_ALIGN_TARGETS_HELP)
    _tree_flag(pawall)

    pafloor = pamode.add_parser(
        "floor", help="stamp a world-projected frame on each HORIZONTAL face (floor/ceiling)")
    pafloor.add_argument("targets", nargs="*", metavar="BRUSH:SELECTOR", help=_ALIGN_TARGETS_HELP)
    _tree_flag(pafloor)

    parun = pamode.add_parser(
        "run", help="lay one continuous texture along a connected RUN of faces: U follows the run, "
                    "V across it, phase carried across every seam. Wraps a cylinder, walks a wall "
                    "run or a curved/flat bend; derives its own walk order from geometry, so the "
                    "order faces are passed in does not matter. Exclude a cylinder's caps")
    parun.add_argument("targets", nargs="*", metavar="BRUSH:SELECTOR", help=_ALIGN_TARGETS_HELP)
    parun.add_argument("--turn", dest="turn", type=int, default=0, metavar="UU",
                       help="rotate the texture uniformly in each face's own run frame, in UNREAL "
                            "ROTATION UNITS (16384 = 90 degrees), matching `brush build --rotate`. "
                            "Any angle is allowed; on a flat bend a non-quarter turn shears both "
                            "axes at the seams (the amount is reported to stderr), while a cylinder "
                            "run stays exact at every angle")
    parun.add_argument("--fit-perimeter", dest="fit_perimeter", action="store_true",
                       help="snap the texture scale so a whole number of TILES exactly closes the "
                            "loop (needs a CLOSED run, a quarter --turn, and every face bound to "
                            "the SAME texture, else exit 2 naming why). Needs a project on the "
                            "package path to read that texture's pixel size. Default leaves the "
                            "closing seam")
    _tree_flag(parun)

    paone = pamode.add_parser(
        "one-tile", help="fit exactly ONE texture tile to each face, independently (a sign, a "
                        "monitor, a light panel) — stretches non-uniformly to fill, no shared "
                        "frame, no orientation guard (any face works). Needs a project on the "
                        "package path: every face's bound texture must resolve, or exit 2 naming "
                        "every offender")
    paone.add_argument("targets", nargs="*", metavar="BRUSH:SELECTOR", help=_ALIGN_TARGETS_HELP)
    _tree_flag(paone)

    def _top_arg(s: str):
        if s == "all":
            return "all"
        try:
            n = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--top must be a positive integer or 'all', got {s!r}")
        if n < 1:
            raise argparse.ArgumentTypeError(f"--top must be a positive integer or 'all', got {s!r}")
        return n

    def _parse_footprint_list(s: str) -> set[str]:
        valid = {"none", "vertex", "edge", "partial", "contains", "coincident"}
        parts = {p.strip() for p in s.split(",") if p.strip()}
        bad = parts - valid
        if bad:
            raise argparse.ArgumentTypeError(
                f"--footprint: unknown value(s) {sorted(bad)} (valid: {sorted(valid)})")
        return parts

    relation = bsub.add_parser(
        "relation", help="cross-brush geometric relationships: measure/find/set")
    rsub = relation.add_subparsers(dest="relationsub", required=True)

    _FOOTPRINT_EPILOG = (
        "footprint_2d values (the 2-D outline relationship, projected onto the shared or\n"
        "parallel plane -- independent of `distance`, the out-of-plane gap):\n"
        "  none        no touching or overlap at all\n"
        "  vertex      touch at a single point\n"
        "  edge        touch along a line segment, zero area overlap\n"
        "  partial     real area overlap, neither fully contains the other\n"
        "  contains    one fully inside the other's footprint (direction stated)\n"
        "  coincident  identical footprint both ways -- usually a stray duplicate\n"
    )

    rmeasure = rsub.add_parser(
        "measure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between a reference face selector and one "
             "or more target selectors (plane, normals, distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
    rmeasure.add_argument(
        "ref", metavar="REF_SELECTOR",
        help="reference face selector: a bare brush Name (all its polys) or Name:SELECTOR "
             "(SELECTOR = 'all' or comma indices). Sign conventions (distance, deltas) are "
             "relative to THIS selector")
    rmeasure.add_argument(
        "target", nargs="+", metavar="TARGET_SELECTOR",
        help="one or more other face selectors, same grammar as REF_SELECTOR, or '-' alone to "
             "read a newline selector list from stdin (e.g. `brush relation find`'s output; "
             "empty stdin: clean no-op). Repeated selectors naming the same brush have their "
             "polys unioned into one comparison rather than duplicated")
    rmeasure.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked candidate poly-pairs to show (default 1); 'all' shows every "
             "qualifying pair with no cap")
    rmeasure.add_argument(
        "--allow-self", dest="allow_self", action="store_true",
        help="permit REF_SELECTOR and TARGET_SELECTOR to name the SAME brush (comparing two "
             "faces of one brush). Without it, naming the same brush on both sides is a clean "
             "exit 2 -- it usually means a typo or a copy-paste left the same name twice")

    rfind = rsub.add_parser(
        "find",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="print faces of one or more candidate brushes related to a reference face, "
             "filtered by gap/footprint/plane, as candidate:idx selectors",
        epilog=_FOOTPRINT_EPILOG,
    )
    rfind.add_argument(
        "candidates", nargs="*", metavar="NAME",
        help="candidate brush Name(s) to search, or '-' to read a newline name list from "
             "stdin (empty stdin: clean no-op). Omit entirely (no names, no '-') to search "
             "every OTHER brush in the level")
    rfind.add_argument(
        "--relative-to", dest="relative_to", required=True, metavar="REF[:idx]",
        help="the reference: a bare brush Name (rank against every one of its polys) or "
             "Name:idx (pin to exactly one reference poly)")
    rfind.add_argument(
        "--max-gap", dest="max_gap", type=float, default=None, metavar="N",
        help="keep only pairs whose perpendicular gap (absolute distance) is at most N world "
             "units (a tiny float-dust tolerance is built in, so a genuinely flush pair always "
             "passes --max-gap 0). Given without --footprint, also enables a stderr note when a "
             "same-plane candidate with NO footprint overlap sits within N of REF but is hidden "
             "by the default footprint filter")
    rfind.add_argument(
        "--min-gap", dest="min_gap", type=float, default=None, metavar="N",
        help="keep only pairs whose perpendicular gap (absolute distance) is at least N world units")
    rfind.add_argument(
        "--footprint", dest="footprint", type=_parse_footprint_list, default=None, metavar="LIST",
        help="comma-separated footprint_2d values to keep (none,vertex,edge,partial,contains,"
             "coincident -- 'contains' matches either direction). Omit: no filter")
    rfind.add_argument(
        "--plane", dest="plane", choices=["coplanar", "parallel"], default=None,
        help="keep only pairs of this plane relationship. Omit: either")
    rfind.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked qualifying pairs to show PER CANDIDATE (default 1); 'all' shows "
             "every qualifying pair")
    rfind.add_argument(
        "--allow-self", dest="allow_self", action="store_true",
        help="permit the reference's OWN brush among the candidates (finding other faces of "
             "the same brush related to its reference face). Without it, the reference's own "
             "brush is excluded from the default level-wide search and rejected if named "
             "explicitly")
    rfind.add_argument(
        "--json", action="store_true",
        help="emit each match's identity (ref, ref_poly, candidate, poly) as a JSON array on "
             "stdout, instead of bare candidate:idx lines; suppresses the plain-text match "
             "listing/summary on stderr (the near-miss note from --max-gap, if any, still "
             "prints). For the geometric detail (plane, normals, distance, footprint_2d, "
             "deltas) on a specific match, pipe into `brush relation measure REF -`")

    rset = rsub.add_parser(
        "set",
        help="translate a brush (by its Location) so one of its faces hits a target gap/"
             "centroid/edge offset from a reference face")
    rset.add_argument(
        "target", nargs="+", metavar="TARGET:idx",
        help="the face to move, as an exact BRUSH:idx (a bare name or index list is not "
             "allowed). Repeat, or pass the single token '-' to read a newline TARGET:idx "
             "list from stdin (empty stdin: clean no-op) -- every target moves relative to "
             "the SAME --relative-to reference")
    rset.add_argument(
        "--relative-to", dest="relative_to", required=True, metavar="REF:idx",
        help="the fixed reference face, as an exact BRUSH:idx. Never moves")
    rset.add_argument(
        "--gap", type=float, default=None, metavar="N",
        help="set the signed perpendicular distance to the reference plane to exactly N "
             "(along the reference's own normal; 0 = flush/coplanar). Omit: leave untouched")
    ucg = rset.add_mutually_exclusive_group()
    ucg.add_argument(
        "--centroid-u", dest="centroid_u", type=float, default=None, metavar="N",
        help="set the footprint centroid's U offset from the reference to exactly N")
    ucg.add_argument(
        "--edge-u-min", dest="edge_u_min", type=float, default=None, metavar="N",
        help="set the offset between this face's U-min extent and the reference's to exactly N")
    ucg.add_argument(
        "--edge-u-max", dest="edge_u_max", type=float, default=None, metavar="N",
        help="set the offset between this face's U-max extent and the reference's to exactly N")
    vcg = rset.add_mutually_exclusive_group()
    vcg.add_argument(
        "--centroid-v", dest="centroid_v", type=float, default=None, metavar="N",
        help="set the footprint centroid's V offset from the reference to exactly N")
    vcg.add_argument(
        "--edge-v-min", dest="edge_v_min", type=float, default=None, metavar="N",
        help="set the offset between this face's V-min extent and the reference's to exactly N")
    vcg.add_argument(
        "--edge-v-max", dest="edge_v_max", type=float, default=None, metavar="N",
        help="set the offset between this face's V-max extent and the reference's to exactly N")
