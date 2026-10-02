# Documentation — the docs are an asset of the tool

## What we want

uedcli's user-facing documentation ships inside uedcli and is readable through it (`uedcli docs
list|show|search`), the way `git help <topic>` and `rustc --explain` work. A consumer that needs to
point a user at a page — including a shipped Claude skill or plugin — **queries the tool** and ships
**zero** copies of the docs. There is one source of truth, and a user always reads the pages that
match the binary they are running: version-locked, offline, cross-platform. *(Owner ruling,
2026-07-24.)*

## Rejected

- Bundling the documentation under a consuming skill's own `references/` — duplicates the corpus,
  inverts ownership (the skill would own uedcli's docs), and needs a bake/sync step that is one more
  thing to keep true.
- Referencing hosted docs by URL — needs a network and drifts from the installed version.

## Refs

`../board/done/uedcli-docs-list-show-search/overview.md` · `../../../docs/usage.md` "Documentation"
