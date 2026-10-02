"""`sound` command-family parser. The family builder is shared with `music` (`build_family`);
phase (a) `sound` and `music` carry the same verb surface (no `preview`/`prewarm` — those are the
deferred phase-(b) spectrogram work). `sound preview` staying absent is asserted by the tests."""
from __future__ import annotations


def _csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def build_family(sub, noun: str) -> None:
    """Register the `<noun>` catalog family (`list`/`show`/`search`/`classify`) on `sub`, keyed to
    `kind=<noun>` for `cli.commands.audio`. Shared by the `sound` and `music` parsers."""
    obj = "module" if noun == "music" else "sound"
    top = sub.add_parser(
        noun,
        help=f"discover and classify the substrate's {noun} objects (offline; reads the game's "
             f"own packages — no editor, no level needed)")
    top.set_defaults(kind=noun)
    nsub = top.add_subparsers(dest="sub", required=True)

    nlist = nsub.add_parser(
        "list",
        help=f"enumerate every {noun} object, one full dotted ref (Package[.Group].Name) per line; "
             f"count to stderr. No default filter — narrow with --package or a pipe.")
    nlist.add_argument("--package", action="append", default=None, metavar="NAME",
                       help="restrict to this EXACT package (bare stem, e.g. DeusExSounds); repeat "
                            "for the union. Not a glob. An unknown package exits 2 naming it.")
    ncls = nlist.add_mutually_exclusive_group()
    ncls.add_argument("--classified", dest="only_classified", action="store_true",
                      help="keep ONLY objects that have a stored classification shard")
    ncls.add_argument("--unclassified", dest="only_unclassified", action="store_true",
                      help="keep ONLY objects with NO classification shard yet — the worklist")
    nlist.add_argument("--json", action="store_true",
                       help="emit one JSON object per line (JSONL): {ref, identity, group, "
                            + ("classified, title, format}" if noun == "music" else "classified}"))

    nshow = nsub.add_parser(
        "show",
        help=f"print each {noun}'s facts (package, group, identity"
             + (", embedded module title + format" if noun == "music" else "")
             + ") and stored classification. Takes one or more refs, or - to read a newline ref "
               "list from stdin.")
    nshow.add_argument("refs", nargs="*", metavar="REF",
                       help=f"{noun} ref(s) — the full dotted Package.Group.Name or the 2-part "
                            "Package.Name identity (either resolves to the same object); or - to "
                            "read a newline ref list from stdin")
    nshow.add_argument("--json", action="store_true",
                       help="emit one JSON object per ref instead of the human block")

    nsearch = nsub.add_parser(
        "search",
        help=f"RANKED discovery over the {noun} corpus: given one or more terms, print the objects "
             f"whose name / stored tags / description match, best first. Ranking (per term, best "
             f"tier): exact leaf name > exact tag > substring of the ref > substring of a tag > "
             f"substring of the description; an object must match EVERY term (AND). Terms are "
             f"REQUIRED — to enumerate without ranking use `{noun} list`.")
    nsearch.add_argument("terms", nargs="*", metavar="TERM",
                         help="one or more search terms (case-insensitive); an object must match "
                              "EVERY term. At least one is required (term-less exits 2).")
    nsearch.add_argument("--tag", action="append", default=[], metavar="TAG",
                         help="keep only objects carrying this exact stored tag (repeat to require "
                              "several — AND). Applied before ranking.")
    nsearch.add_argument("--json", action="store_true",
                         help="emit one JSON object per match (JSONL), best first: "
                              "{ref, score, classified, tags, description}")

    _register_classify(nsub, noun, obj)


def _register_classify(nsub, noun: str, obj: str) -> None:
    kcls = nsub.add_parser(
        "classify",
        help=f"record / inspect what a {noun} object IS — the LLM's classification, stored one "
             f"git-tracked shard per object (tags + description). The tool stores it, never infers it.")
    csub = kcls.add_subparsers(dest="csub", required=True)

    cset = csub.add_parser(
        "set",
        help=f"record a {noun}'s classification against its identity. A `set` over an ALREADY-"
             f"classified object REFUSES (exit 2 naming the ref); --force replaces it WHOLESALE "
             f"(dropping any field the forcing set omits — no merge). The single token - reads JSONL "
             f"rows {{ref, tags, description}} from stdin (validate-all-then-write; empty stdin is a "
             f"clean no-op, exit 0; --force governs every row).")
    cset.add_argument("ref", nargs="?", default=None, metavar="REF",
                      help=f"the {noun} to classify (the dotted ref or the 2-part identity), or - "
                           "to read JSONL rows from stdin")
    cset.add_argument("--tags", type=_csv, default=None, metavar="A,B",
                      help="comma list of tags (strip/lowercase/de-dupe). Replaces the stored tags "
                           "on a --force re-set — not merged.")
    cset.add_argument("--description", default=None, help="prose description")
    cset.add_argument("--force", action="store_true",
                      help="replace an existing shard WHOLESALE instead of exiting 2 (also governs "
                           "each JSONL row under -)")

    cunset = csub.add_parser(
        "unset",
        help=f"undo classification on one or more {noun} objects. Exactly one of --tags[=A,B] / "
             "--description / --all. The single token - reads a newline ref list from stdin (empty "
             "stdin is a clean no-op, exit 0).")
    cunset.add_argument("refs", nargs="*", metavar="REF",
                        help=f"{noun}(s) to unset, or - to read a newline ref list from stdin")
    cg = cunset.add_mutually_exclusive_group(required=True)
    cg.add_argument("--tags", type=_csv, nargs="?", const=[], default=None, metavar="A,B",
                    help="remove the named tags (comma list); BARE --tags clears the whole tags field")
    cg.add_argument("--description", action="store_true", help="clear the description field")
    cg.add_argument("--all", dest="clear_all", action="store_true",
                    help="delete the whole shard (the only full clear)")

    cstat = csub.add_parser(
        "status", help=f"classification progress: how many {noun} objects on the path have a shard, "
                       "of the total. --json for a machine object.")
    cstat.add_argument("--json", action="store_true", help="emit one JSON object instead of a line")

    ctags = csub.add_parser(
        "tags", help="the tag vocabulary in use across all shards, with occurrence counts (curbs "
                     "drift). --json for a machine object.")
    ctags.add_argument("--json", action="store_true", help="emit one JSON object instead of lines")


def register(sub) -> None:
    build_family(sub, "sound")
