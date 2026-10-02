+++
priority = "p2"
kind = "implement"
summary = "class arm C2 preview cache pool not built; list --json preview always null"
+++

# class arm C2 preview cache pool not built; list --json preview always null

The class-arm spec (§2, §9 C2 row) has C2 ship a content-addressed catalog preview cache
(`~/.uedcli/cache/catalog/v<N>/previews/<hh>/<hash>.png`) plus a per-`(kind, package)` derived row
mapping a class to its cached preview, reclaimed by `cache gc --previews`. C2 as merged did **not**
build any of this: `class preview` writes only to `--out` or a temp file, and there is no cache
lookup keyed by class.

C3's `class list --json` carries `preview: path|null` (cached only). With no preview cache to
consult, the field is **always `null`** — see `uedcli/cli/commands/classes.py` `_cached_preview`,
which is a documented stub returning `None`. The contract ("a cached path, else null; never render")
is correct; there is just nothing cached yet.

**To finish:** build the C2 preview cache pool + the class->preview index, wire `_cached_preview` to
it, and add `cache gc --previews`. Then `list --json` reports real paths for previously-rendered
classes. Pin with a test: render -> `list --json` shows the path; `cache gc --previews` -> back to null.
