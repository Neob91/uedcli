"""`actor relation` subparser: compare/find/set -- the pairwise/scanning geometric-relation toolkit.
Moved wholesale out of `brush.py` when the family moved from `brush` to `actor`; the three helpers
below (`_top_arg`, `_parse_footprint_list`, `_FOOTPRINT_EPILOG`) came with it because nothing else in
`brush.py` used them."""
from __future__ import annotations

import argparse


def add_relation_subparser(asub) -> None:
    """Wire `relation` (compare/find/set) under the `actor` command's subparsers object `asub`."""
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

    relation = asub.add_parser(
        "relation", help="cross-brush geometric relationships: compare/find/set")
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

    rcompare = rsub.add_parser(
        "compare",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between a reference face selector and one "
             "or more target selectors (plane, normals, distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
    rcompare.add_argument(
        "ref", metavar="REF_SELECTOR",
        help="reference face selector: a bare brush Name (all its polys) or Name:SELECTOR "
             "(SELECTOR = 'all' or comma indices). Sign conventions (distance, deltas) are "
             "relative to THIS selector")
    rcompare.add_argument(
        "target", nargs="+", metavar="TARGET_SELECTOR",
        help="one or more other targets: a face selector (same grammar as REF_SELECTOR) for a "
             "brush, or a non-brush actor's bare Name (compared by its Location), or '-' alone "
             "to read a newline list from stdin (e.g. `actor relation find`'s output; empty "
             "stdin: clean no-op). Repeated face selectors naming the same brush have their "
             "polys unioned into one comparison rather than duplicated; a repeated non-brush "
             "Name is not")
    rcompare.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked candidate poly-pairs to show (default 1); 'all' shows every "
             "qualifying pair with no cap")
    rcompare.add_argument(
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
        help="candidate Name(s) to search -- a brush or a non-brush actor -- or '-' to read a "
             "newline name list from stdin (empty stdin: clean no-op). Omit entirely (no names, "
             "no '-') to search every OTHER BRUSH in the level")
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
             "deltas) on a specific match, pipe into `actor relation compare REF -`")

    rset = rsub.add_parser(
        "set",
        help="translate an actor (by its Location) so it -- or one of its brush faces -- hits a "
             "target gap/centroid/edge offset from a reference face")
    rset.add_argument(
        "target", nargs="+", metavar="TARGET",
        help="what to move: a brush face as an exact BRUSH:idx (a bare BRUSH name or an index "
             "list is not allowed), or a non-brush actor's bare Name (its Location moves). "
             "Repeat, or pass the single token '-' to read a newline list from stdin (empty "
             "stdin: clean no-op) -- every target moves relative to the SAME --relative-to "
             "reference")
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
