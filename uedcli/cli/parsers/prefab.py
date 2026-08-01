"""`prefab` command-family parser registrar."""
from __future__ import annotations

from ._arguments import _apply_flags, _preview_opts


def register(sub) -> None:
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
