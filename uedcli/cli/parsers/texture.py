"""`texture` command-family parser registrar — the offline texture catalog noun."""
from __future__ import annotations

# Shared help for the `--catalog-dir` flag every texture verb carries (load-bearing for
# project-less `classify tags`). One string so every verb documents default-resolution identically.
_CATALOG_DIR_HELP = ("tracked classification-shard dir (default: the resolved project's catalog dir "
                     "— the uedcli.toml `catalog` key, or <root>/texture-catalog/)")


def _csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def register(sub) -> None:
    texture = sub.add_parser(
        "texture",
        help="discover, view and classify the substrate's textures (offline; decodes the game's own "
             ".utx/.u packages — no editor, no level needed)")
    texsub = texture.add_subparsers(dest="sub", required=True)

    tlist = texsub.add_parser(
        "list",
        help="enumerate every texture on the composed path (Engine.Texture and its descendants — "
             "FireTexture, sprites, …), one ref per line, sorted. Filter with --package/--group/"
             "--masked/--classified/--unclassified; --json for a machine row per texture.")
    tlist.add_argument("--package", default=None, help="restrict to this package (bare stem)")
    tlist.add_argument("--group", default=None, metavar="G",
                       help="keep only textures whose group (Outer) is G, e.g. Ladder")
    tlist.add_argument("--masked", action="store_true",
                       help="keep only textures whose effective bMasked flag is true (decodes each "
                            "to read the flag)")
    tlg = tlist.add_mutually_exclusive_group()
    tlg.add_argument("--classified", action="store_true",
                     help="keep only textures whose content identity has a classification shard")
    tlg.add_argument("--unclassified", action="store_true",
                     help="keep only textures with NO shard yet — the worklist")
    tlist.add_argument("--json", action="store_true",
                       help="emit one JSON object per texture (JSONL): {ref, identity, classified, "
                            "group, masked, preview} where preview is a cached path or null (list "
                            "NEVER renders)")
    tlist.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tshow = texsub.add_parser(
        "show",
        help="print a texture's Layer-2 facts (size, format, group, masked) + its Layer-1 content "
             "identity + any stored classification (tags, description, colors). A procedural texture "
             "shows no bitmap size; a bad/undecodable ref exits 2 naming the case.")
    tshow.add_argument("refs", nargs="*", metavar="Package[.Group].Name",
                       help="texture ref(s) to describe, or - to read a newline ref list from stdin")
    tshow.add_argument("--json", action="store_true",
                       help="print one JSON object per ref {ref, width, height, format, group, "
                            "masked, identity, colors, classification} instead of the text block")
    tshow.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tprev = texsub.add_parser(
        "preview",
        help="write a texture's mip-0 bitmap as a PNG (native decode: P8/BC1/BC2/BC3 from the game "
             ".utx — no editor). The bitmap is the opaque Layer-1 image (mask NOT applied). Prints "
             "`<ref><TAB><path>`. A procedural or undecodable ref exits 2 naming the case.")
    tprev.add_argument("refs", nargs="*", metavar="Package[.Group].Name",
                       help="texture ref(s) to render, or - to read a newline ref list from stdin")
    tprev.add_argument("--out", default=None, metavar="PATH",
                       help="host path to write the PNG to (relative → cwd); the extension is "
                            "replaced by .png. With no --out a unique temp file is minted. With "
                            "several refs the LAST written path wins a fixed --out.")
    tprev.add_argument("--skeleton", action="store_true",
                       help="stream a ready-to-fill JSONL row per ref {ref, preview, tags:[], "
                            "description:'', colors:[…]} (colours pre-filled from the pixels) instead "
                            "of the `<ref><TAB><path>` line — pipe it into `classify set -`")
    tprev.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    tsearch = texsub.add_parser(
        "search",
        help="RANKED discovery over the texture corpus: given one or more terms, print the textures "
             "whose name / stored tags / description match, best first (exact Name > exact tag > ref "
             "substring > tag substring > description substring; a texture must match EVERY term). "
             "Terms are REQUIRED — to enumerate without ranking use `texture list`.")
    tsearch.add_argument("terms", nargs="*", metavar="TERM",
                         help="one or more search terms (case-insensitive); a texture must match "
                              "EVERY term. At least one is required (term-less exits 2 → `list`).")
    tsearch.add_argument("--tag", action="append", default=[], metavar="TAG",
                         help="keep only textures carrying this exact stored tag (repeat to AND)")
    tsearch.add_argument("--color", action="append", default=[], metavar="C",
                         help="keep only textures whose colours include C — stored colours for a "
                              "classified texture, else derived live from pixels (repeat to OR). "
                              "Must be a palette name.")
    tsearch.add_argument("--package", default=None, help="restrict to this package (bare stem)")
    tsearch.add_argument("--group", default=None, metavar="G", help="restrict to group G")
    tsearch.add_argument("--masked", action="store_true", help="keep only masked textures")
    tcg = tsearch.add_mutually_exclusive_group()
    tcg.add_argument("--classified", action="store_true", help="keep only classified textures")
    tcg.add_argument("--unclassified", action="store_true", help="keep only unclassified textures")
    tsearch.add_argument("--json", action="store_true",
                         help="emit one JSON object per match (JSONL), best first: {ref, score, "
                              "classified, tags, description, colors}")
    tsearch.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    twarm = texsub.add_parser(
        "prewarm",
        help="decode every texture on the path ahead of an offline session, so a later list/show/"
             "search/classify starts with the ref→identity map warm. Progress → stderr.")
    twarm.add_argument("--package", default=None, help="warm only this package (bare stem)")
    twarm.add_argument("--force", action="store_true",
                       help="re-decode even a texture already warmed this run (reserved; decode is "
                            "per-invocation today)")
    twarm.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    _register_classify(texsub)


# The stored classification is what an LLM decides a texture IS, handed back to the tool (the tool
# never infers it). One shard per CONTENT identity, git-tracked; tags + description + colours.
def _register_classify(texsub) -> None:
    tclass = texsub.add_parser(
        "classify",
        help="record / inspect what a texture IS — the LLM's classification, stored one git-tracked "
             "shard per content identity (tags + description + colours). The tool stores it, never "
             "infers it (colours are pre-filled from the pixels as the one exception).")
    csub = tclass.add_subparsers(dest="csub", required=True)

    cset = csub.add_parser(
        "set",
        help="record a texture's classification against its content identity. Over an EXISTING shard "
             "it REFUSES (exit 2 naming it); --force REPLACES it wholesale (no tag union). The single "
             "token - reads JSONL rows {ref, tags?, description?, colors?} from stdin (validate-all-"
             "then-write; empty stdin is a clean no-op, exit 0).")
    cset.add_argument("ref", nargs="?", default=None, metavar="Package[.Group].Name",
                      help="the texture to classify, or - to read JSONL rows from stdin")
    cset.add_argument("--tags", type=_csv, default=None, metavar="A,B",
                      help="comma list of tags (strip/lowercase/de-dupe normalized)")
    cset.add_argument("--description", default=None, help="prose description")
    cset.add_argument("--colors", type=_csv, default=None, metavar="A,B",
                      help="comma list of palette colour names, OVERRIDING the pixel pre-fill "
                           "(unknown names exit 2). Omit to keep the derived colours.")
    cset.add_argument("--force", action="store_true",
                      help="replace an existing classification for this identity instead of exiting "
                           "2 (wholesale — no tag union; also governs each JSONL row under -)")
    cset.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    cunset = csub.add_parser(
        "unset",
        help="undo classification on one or more textures (by their content identity). Any of "
             "--tags[=A,B] / --description / --colors / --all (combine field clears; --all deletes "
             "the whole shard). The single token - reads a newline ref list from stdin (empty stdin "
             "is a clean no-op, exit 0).")
    cunset.add_argument("refs", nargs="*", metavar="Package[.Group].Name",
                        help="texture(s) to unset, or - to read a newline ref list from stdin")
    cug = cunset.add_mutually_exclusive_group(required=True)
    cug.add_argument("--tags", type=_csv, nargs="?", const=[], default=None, metavar="A,B",
                     help="remove the named tags (comma list); BARE --tags clears the whole field")
    cug.add_argument("--description", action="store_true", help="clear the description field")
    cug.add_argument("--colors", action="store_true",
                     help="clear the colour override (search falls back to live-derive)")
    cug.add_argument("--all", dest="clear_all", action="store_true",
                     help="delete the whole shard (the only full clear)")
    cunset.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    cstat = csub.add_parser(
        "status", help="classification progress: how many textures on the path have a shard, of the "
                       "total. --json for a machine object.")
    cstat.add_argument("--json", action="store_true", help="emit one JSON object instead of a line")
    cstat.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)

    ctags = csub.add_parser(
        "tags", help="the tag vocabulary in use across all shards, with occurrence counts (curbs "
                     "drift). Reads only the shard tree, so --catalog-dir runs it outside a project.")
    ctags.add_argument("--json", action="store_true", help="emit one JSON object instead of lines")
    ctags.add_argument("--catalog-dir", default=None, help=_CATALOG_DIR_HELP)
