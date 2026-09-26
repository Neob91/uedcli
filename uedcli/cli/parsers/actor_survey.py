"""`actor survey NAME` subparser."""
from __future__ import annotations

from ._arguments import _tree_flag


def add_survey_subparser(asub) -> None:
    """Wire `survey` under the `actor` command's subparsers object `asub`."""
    p = asub.add_parser(
        "survey",
        help="every raw and CSG-resolved spatial fact about one actor (brush or not): what it "
             "touches, contains, carves, connects to, and crosses into")
    p.add_argument(
        "name", metavar="NAME",
        help="the actor to survey — exactly one, never a set (both tiers are computed over a "
             "bounded neighborhood of this actor, which is what keeps the cost flat)")
    _tree_flag(p)     # read a named tree explicitly instead of $UEDCLI_LEVEL, like actor show/bbox
