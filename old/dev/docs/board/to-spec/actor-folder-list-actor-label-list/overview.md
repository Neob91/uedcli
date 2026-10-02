+++
priority = "p2"
kind = "implement"
summary = "`actor folder list` + `actor label list` — enumerate the folders/labels in use"
+++

# `actor folder list` + `actor label list` — enumerate the folders/labels in use

p2.
Today you can find actors BY a folder/label (`actor find --folder/--label`) but cannot ask *what
folders/labels exist*. Add two read verbs UNDER `actor` (the top-level-promotion question is CLOSED —
keep everything under `actor`, `direction/organization.md`, 2026-07-25 00:43 UTC): `folder list` prints the distinct
folder paths in use (one per line, sorted — the pipe-friendly producer form); `label list` prints the
distinct labels (flat, so no tree). Spec the exact output: per-path/per-label actor COUNTS (to stderr,
or a `--count` column?); a `folder tree` view rendering the hierarchy indented (labels have none); do
they take `-`/stdin to scope the enumeration to a piped actor set; `--json`. Both are uedcli-side
sidecars, never emitted to the built map; query stays on `actor find`, this is pure enumeration.
(Andrzej, 2026-07-25 — reframed from the closed "promote folder/label to top-level" item.)
