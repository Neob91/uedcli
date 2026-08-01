"""`texture` command-family parser registrar."""
from __future__ import annotations

# Shared help for the `--catalog-dir` flag every texture verb carries (load-bearing for
# project-less texture use). One string so `sync`/`list`/`search`/`tags`/`classify status|set`
# all document the default-resolution the same way (audit L3).
_CATALOG_DIR_HELP = ("tracked manifest dir (default: the resolved project's catalog dir — "
                     "the uedcli.toml `catalog` key, or <root>/texture-catalog/)")


def register(sub) -> None:
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
