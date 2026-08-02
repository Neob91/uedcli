"""`stash` command-family parser registrar."""
from __future__ import annotations

from ._arguments import _apply_flags, _preview_opts, _tree_flag


def register(sub) -> None:
    stash = sub.add_parser(
        "stash",
        help="capture/replay named actor sets (private register); edit a stored one in place with "
             "any content verb + --tree stash/<id>")
    stsub = stash.add_subparsers(dest="sub", required=True)

    cap = stsub.add_parser("capture", help="capture actors into a register entry")
    cap.add_argument("names", nargs="*",
                     help="actors to capture; empty = the whole source. A leading - reads a T3D "
                          "snippet from stdin as the SOURCE (`… | stash capture -`); any remaining "
                          "names still subset it")
    cap.add_argument("--id", default=None, help="register id (default: auto-slug)")
    cap.add_argument("--force", action="store_true", help="overwrite an existing --id")
    cap.add_argument("--from-t3d", dest="from_t3d", nargs="+", default=None, metavar="FILE",
                     help="capture from these T3D file(s) instead of $UEDCLI_LEVEL. Multiple files "
                          "concatenate in order. (`names` still selects a subset of the source; to "
                          "read the T3D from stdin use a leading - instead)")
    _tree_flag(cap)       # name the SOURCE tree explicitly instead of $UEDCLI_LEVEL;
                            # only consulted when neither a leading - nor --from-t3d is given

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
