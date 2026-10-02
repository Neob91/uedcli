# Spec — `actor folder list` + `actor label list`

## Goal

Two read verbs that answer *what folders / labels exist*, which `actor find --folder/--label`
(find actors BY one) cannot: `actor folder list` prints the distinct folder paths in use;
`actor label list` prints the distinct labels in use. Enumeration only — the query stays on
`actor find`. This is the closed direction (`direction/organization.md` "Enumeration lives under
`actor` too"; top-level-promotion CLOSED per the overview): keep both under `actor`.

## Current state

- Folders/labels are per-actor trunk sidecars, read into `Actor.folder: str | None` and
  `Actor.labels: frozenset[str]` at load (`trunk.read_level`; `dev/docs/architecture.md` "Folders"/
  "Labels"). Never emitted to the built map, never in the level hash.
- The `folder`/`label` sub-verb families live at `uedcli/cli/commands/actor/folder.py` and
  `label.py`, parsed in `uedcli/cli/parsers/actor.py:162-228` (`fsub`/`lsub2` subparsers), routed in
  `uedcli/cli/commands/actor/routes.py:42-47`. Today: folder = `set|unset|get`, label =
  `add|remove|clear|get`. There is **no `list`**.
- `get` is the closest existing shape: reads the resolved level source, resolves a name set, prints
  per-actor values (`folder.py:40-50`, `label.py:44-52`), `--json` → an object keyed by name.
- `actor find` is the model for a pure producer: distinct result to stdout one/line, `--json` → a
  JSON array of strings, human count to stderr (`query.py:_find`, `:146-152`).
- Trunk-only guard: `routes._apply_source_free_guards` rejects `--tree stash|prefab` for every
  `sub == "folder"` / `sub == "label"` invocation unconditionally (`routes.py:65-73`). A new `list`
  sub inherits that rejection with no extra code.

## Design

### Decided by convention + `direction/organization.md` (resolved in-spec)

- **Base output.** Distinct folder paths / distinct labels, one per line to **stdout**, sorted;
  a one-line human count to **stderr** (`N folder(s) in use` / `N label(s) in use`). Pure producer,
  so `actor folder list | actor find --folder - …`-style chaining stays clean. Ungrouped/unlabelled
  actors contribute nothing — an unset value is not a "folder"/"label" (reach the unset set with
  `actor find --no-folder/--no-label`, unchanged).
- **`--json`.** A JSON array of strings (matches `actor find --json`). Sorted identically to the
  line output.
- **Sort + dedup.** Dedup by the exact stored string; sort case-insensitively then by the raw string
  (the `folderlib.best_grid_pivot` tiebreak convention), so two case-variant spellings are both
  listed, deterministically ordered. Folders sort lexicographically on the whole dotted path (no tree
  grouping in the flat list — see the tree question).
- **Empty tree / no folders.** Empty stdout, exit 0 (a legitimately-empty enumeration is grep-like,
  not an error — `direction/conventions.md`).
- **`--tree`.** Follows the sibling folder/label verbs: `--tree level/NAME` selects the box;
  `--tree stash|prefab` is rejected (exit 2) by the existing source-free guard. No new surface.
- **No Python exception to the user.** No name resolution happens (whole-tree enumeration), so the
  only failure is an unresolvable project/level — the shared `resolve_level_source` clean exit 2.

### Proposed CLI surface

```
actor folder list [--json]      "list the distinct uedcli-side folder paths in use in this level "
                                "(one per line to stdout, sorted; the count to stderr). Answers "
                                "WHAT folders exist — use `actor find --folder` to find actors BY "
                                "one. Ungrouped actors are not listed (see `actor find --no-folder`)."
    --json                      "emit the distinct folder paths as a JSON array of strings instead "
                                "of one per line — for scripts"

actor label list [--json]       "list the distinct uedcli-side labels in use in this level (one per "
                                "line to stdout, sorted; the count to stderr). Answers WHAT labels "
                                "exist — use `actor find --label` to find actors BY one. Unlabelled "
                                "actors are not listed (see `actor find --no-label`)."
    --json                      "emit the distinct labels as a JSON array of strings instead of one "
                                "per line — for scripts"
```

Implementation: add a `list` parser under `fsub`/`lsub2` (`parsers/actor.py`); route
`foldersub == "list"` / `labelsub == "list"` in `folder.py` / `label.py`; body is
`src.load()` then `sorted({a.folder for … if a.folder is not None})` / `sorted(union of a.labels)`
with the tiebreak sort, printed one/line or as `--json`. No new module.

### Open forks (owner questions, below)

- **Per-value counts** — pure value producer vs an opt-in `--count` TSV column
  (`count<TAB>value`). Recommendation: pure producer now; no `--count`.
- **Stdin `-` scoping** — whether `list` takes `-` to enumerate over a piped actor set (symmetry
  with composable `actor find -`) or always enumerates the whole box. Recommendation: whole-box only
  now.
- **`folder tree` view** — a separate indented hierarchical rendering (labels have none).
  Recommendation: defer to its own item; keep this one to the two flat `list` verbs.

## Edge cases & errors

- No project / unresolvable level → clean exit 2 from `resolve_level_source` (shared).
- `--tree stash|prefab` → exit 2 "folders/labels apply only to a level" (existing guard, inherited).
- Level with zero foldered/labelled actors → empty stdout, exit 0, `0 folder(s)/label(s) in use` on
  stderr.
- `--json` on an empty result → `[]`, exit 0.
- Two actors carrying case-variant spellings (`Castle` vs `castle`) → both listed, deterministic
  order (dedup is by exact string).

## Tests

- `folder list` / `label list`: distinct values, sorted, one/line to stdout; count to stderr.
- Empty level → empty stdout, exit 0.
- `--json` → sorted JSON array; `[]` on empty.
- Ungrouped/unlabelled actors excluded from the output.
- Case-variant spellings both appear, deterministically ordered.
- `--tree stash/X` / `prefab/X` → exit 2 (guard).
- Homes: `test_folders.py` / `test_labels_verbs.py` / `test_query_labels.py`; parser wiring in
  `test_cli.py` / `test_help_completeness.py`.
- User doc: add `actor folder list` / `actor label list` to `docs/usage.md` in the same change
  (tool-behavior doc, no owner gate).

## Open questions

Three real forks, each its own `questions/` file: per-value counts, stdin `-` scoping, and the
`folder tree` view.
