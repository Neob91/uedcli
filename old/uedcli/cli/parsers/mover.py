"""`mover` command-family parser registrar."""
from __future__ import annotations

from ._arguments import parse_coord, _tree_flag


def register(sub) -> None:
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
