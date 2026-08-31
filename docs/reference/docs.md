# docs

uedcli carries its own user documentation, queryable from the tool itself — no network, no repo
checkout, always the version matching the binary you are running. `uedcli docs show reference/docs`
prints this file.

```bash
# every page's topic key, one per line
uedcli docs list [--json]

# print one page's markdown, verbatim
uedcli docs show leveldesign/general/lighting

# rank pages matching a text query, printing the keys `docs show` takes
uedcli docs search "mover" [--json]

# search feeds show directly
uedcli docs search voussoir | uedcli docs show -
```

**A topic key** is how a page is addressed: its path with the `.md` dropped, so
`leveldesign/general/lighting` (a trailing `.md` is accepted too, and matching is
case-insensitive). A directory's overview page is addressed by the **directory's own name** —
`uedcli docs show leveldesign/deusex` gives that section's overview — and this usage reference is
`usage`, with the docs landing page at `index`.

- **`docs list`** prints every topic key to stdout, sorted, with the count on stderr. `--json`
  gives `[{"path": <topic key>, "title": …}]` — `path` holds the topic key, not a filesystem path.
- **`docs show <topic>`** writes the page's markdown to stdout byte-for-byte and nothing to
  stderr. `docs show -` instead reads topic keys from stdin, one per line, and prints them all,
  each preceded by a `<!-- topic: <key> -->` marker line. That form is **all-or-nothing**: if any
  key is unknown, nothing is printed and it exits 2 naming the offending keys. Empty stdin is a clean
  no-op (exit 0).
- **`docs search <query>`** matches a literal, case-insensitive substring against every page's title
  and body lines, and prints the matching topic keys best-first. The ranking is simple: **a title
  match is worth ten matching body lines**, matching body lines one each. So a page *about* your
  query usually leads — but a long page that mentions it eleven times outranks a short page with it
  in the title, working as intended. No matches is a normal empty success (exit 0); an empty query is
  refused (exit 2), since a blank substring would "match" every page. `--json` adds a `snippet` — the
  first matching **body** line, up to 120 characters. The page's heading is its `title`, not a body
  line, so a snippet never just repeats it.

An unknown topic exits 2 with `Doc not found: <topic>` and, where there is an obvious near miss, a
`did you mean:` hint. A bare page name that exists in two places (`human-scale`) does *not* resolve —
the hint lists both candidates.

There are no partial answers. If any part of the docs tree cannot be read — a permission problem on
a directory, say — every `docs` verb exits 2 naming that directory, rather than quietly serving the
pages it *could* read.

Every `docs` verb is read-only and fully offline: no project, no selected level, no game install, so
it works in a bare checkout or install.
