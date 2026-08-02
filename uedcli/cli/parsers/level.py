"""`level` command-family parser registrar."""
from __future__ import annotations

from ._arguments import _tree_flag


def register(sub) -> None:
    level = sub.add_parser("level",
                           help="level lifecycle verbs "
                                "(create/import/list/materialize/preview/status/doctor)")
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
    limport = lsub.add_parser(
        "import",
        help="decode a COMPILED map file (.dx/.unr) into a NEW T3D tree — the inverse of "
             "materialize. Reads the map's bytes directly: no UnrealEd, no container, no game. Use "
             "it to study, diff or remix an existing map with the ordinary query/edit verbs. The "
             "editor's own scratch objects (the red builder brush, the viewport cameras) are left "
             "out; every content actor is imported with its properties and brush geometry")
    limport.add_argument(
        "mapfile",
        metavar="MAPFILE",
        help="the compiled map file to read (.dx or .unr), relative to the current directory. A "
             "file that is missing, unreadable, or not a UE1 package errors (exit 2) naming it")
    limport.add_argument(
        "--tree", metavar="KIND/NAME", required=True,
        help="DESTINATION for the imported level, which this CREATES: KIND/NAME where KIND is "
             "level|stash (prefab is not a valid import target). e.g. level/m03-study writes a new "
             "level trunk at maps/m03-study/; stash/import-1337 writes a new stash entry. Refuses "
             "an existing destination unless --overwrite")
    limport.add_argument(
        "--overwrite", action="store_true",
        help="permit replacing an existing destination level/stash (default: refuse, exit 2). "
             "Checked BEFORE the map file is read, so a refusal costs nothing and touches nothing")
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
        help="detect MECHANICAL defects — BSP/geometry (holes, solidity, CSG order), zoning, and "
             "objectively-wrong footguns — static, offline, no editor. Does NOT judge gameplay or "
             "style: a clean report says nothing about whether the level is passable, well placed, "
             "detailed or good")
    ldoc.add_argument("--json", action="store_true",
                      help="emit findings as JSON instead of the text report")
    ldoc.add_argument("--severity", choices=["info", "warn", "error"], default=None,
                      help="show only findings at or above this severity (does NOT affect the "
                           "exit code, which always reflects all findings)")
    ldoc.add_argument("--category", dest="categories", action="append", default=[], metavar="NAME",
                      help="show ONLY findings in this category (degenerate, watertight, convex, "
                           "planar, solidity, csg_order, scale); repeat to OR several. Exact, "
                           "case-insensitive. Filters DISPLAY only — the exit code always reflects "
                           "all findings. An unknown category exits 2, listing the valid categories.")
    _tree_flag(ldoc)      # lint a named tree explicitly instead of $UEDCLI_LEVEL
