"""`project` command-family parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    project = sub.add_parser("project", help="inspect the resolved uedcli project")
    prsub = project.add_subparsers(dest="sub", required=True)
    pshow = prsub.add_parser("show",
                     help="print the resolved project root, its game, the managed dirs "
                          "(maps/prefabs/catalog), and the composed package search path (each "
                          "entry tagged project/base)")
    pshow.add_argument("--json", action="store_true",
                       help="emit the resolved project as JSON ({root, game, maps, prefabs, "
                            "catalog, search_path:[{path, provenance}]}) instead of the text report")
