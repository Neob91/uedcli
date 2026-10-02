"""`docs` command-family parser registrar."""
from __future__ import annotations


def register(sub) -> None:
    docs = sub.add_parser(
        "docs", help="read uedcli's own user documentation (the CLI reference and the "
                     "level-design guides) without leaving the terminal")
    docssub = docs.add_subparsers(dest="sub", required=True)

    dlist = docssub.add_parser(
        "list", help="print the topic key of every documentation page, one per line")
    dlist.add_argument(
        "--json", action="store_true",
        help="emit a JSON array of {path,title} objects instead of bare lines; `path` holds the "
             "topic key (what `docs show` takes), not a filesystem path")

    dshow = docssub.add_parser(
        "show", help="print a documentation page's markdown to stdout, exactly as written")
    dshow.add_argument(
        "topic",
        help="topic key of the page to print, as `docs list` prints it (a trailing .md is "
             "optional). `-` instead reads topic keys from stdin, one per line, and prints them "
             "all: every key must resolve or nothing is printed at all")

    dsearch = docssub.add_parser(
        "search", help="rank documentation pages by how well they match a text query, printing "
                       "the topic keys that `docs show` takes")
    dsearch.add_argument(
        "query",
        help="literal, case-insensitive text matched against each page's title and its body "
             "lines; a title match is worth ten matching body lines, so a page ABOUT the query "
             "usually outranks one that merely mentions it")
    dsearch.add_argument(
        "--json", action="store_true",
        help="emit a JSON array of {path,title,snippet} objects instead of bare lines; `path` "
             "holds the topic key (what `docs show` takes), not a filesystem path")
