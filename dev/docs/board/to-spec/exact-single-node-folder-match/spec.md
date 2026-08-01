# Spec — exact single-node folder match (no subtree)

## Goal

Give `actor find` a way to match **exactly one folder node, excluding its descendants**. Today a
wildcard-free `--folder castle.tower` selects `castle.tower` and its whole subtree, and there is no
form for "just this node." (`--prop Group=` cannot reach it — the folder is a sidecar, not a prop.)
Niche but real: "the actors filed directly at `castle.tower`, not the ones in `castle.tower.roof`."

## Current state

- Globstar match: `folderlib.matches(pattern, folder)` at `uedcli/folderlib.py:110-126`. A
  wildcard-free pattern matches the node **and** its subtree (`f == p or f.startswith(p + ".")`);
  any `*` switches to pure segment-glob with no subtree extension.
- Why the existing grammar can't express it: to match only the literal path `castle.tower` you'd need
  an all-literal pattern, but all-literal means subtree. Any wildcard added turns it into a glob but
  still can't pin the exact multi-segment path. So a new surface is genuinely required (overview,
  Andrzej 2026-07-18).
- Parser: `--folder`/`--no-folder` mutually-exclusive group, `uedcli/cli/parsers/actor.py:77-91`.
- Handler grammar-check + call: `query.py:37-43` (validate each pattern) and `query.py:57-67`
  (`folders=` into `query.list_actors`). Match plumbing: `query._folder_matches` (`query.py:163-168`)
  → `folderlib.matches`.
- Pattern validation: `folderlib.validate_pattern` (`folderlib.py:56-75`).

## Design

Two candidate surfaces (the fork is in `questions/`):

1. **`--folder-exact PATH` flag (recommended).** A separate repeatable flag holding a **literal**
   folder path (no `*`/`**`), matching that exact node only. Validated with
   `folderlib.validate_folder_path` (the stored-path grammar — rejects wildcards), not
   `validate_pattern`. Repeatable and OR-combined with itself and with `--folder`/`--no-folder`
   within the folder dimension; the dimension still ANDs with class/label/etc.

       find.add_argument(
           "--folder-exact", dest="folder_exact", action="append", default=[], metavar="PATH",
           help="match actors filed at EXACTLY this literal folder node, EXCLUDING its subtree "
                "(so --folder-exact castle.tower skips castle.tower.roof — the opposite of bare "
                "--folder, which includes the subtree). Literal only: no '*'/'**'. Case-insensitive; "
                "repeat to OR; ORs with --folder, ANDs with the other dimensions.")

   New pure helper in `folderlib.py`:

       def matches_exact(path: str, folder: str | None) -> bool:
           """True iff `folder` equals the literal `path` (case-insensitive), node only, no subtree."""
           return folder is not None and folder.casefold() == path.casefold()

   Plumb a `folders_exact: list[str] | None` param through `query.list_actors` alongside `folders`
   (OR within the folder dimension: an actor passes the folder dimension if it matches any `--folder`
   pattern **or** any `--folder-exact` path).

2. **`=PATH` sigil on `--folder`.** `--folder =castle.tower` means exact-node. `=` is outside the
   segment charset `[A-Za-z0-9_+-]`, so a leading `=` is an unambiguous marker. Keeps one flag, at
   the cost of a second grammar mode inside `--folder`'s already dense help.

Recommendation: option 1 (`--folder-exact`). A distinct predicate reads clearly in `--help`, is
independently repeatable, and keeps `--folder`'s globstar grammar untouched. Sigils inside a
value-flag are the kind of hidden mode this project's help conventions discourage.

Interaction with `--no-folder`: `--no-folder` stays mutually exclusive with `--folder`; whether
`--folder-exact` also excludes `--no-folder` is a small call — recommend adding it to the same
mutually-exclusive group is **wrong** (you may legitimately want `--folder-exact a --no-folder`? no —
they're contradictory per-actor but OR across the dimension is meaningless with the unset set). Keep
`--folder-exact` OUT of the `--no-folder` exclusivity group but note that combining `--no-folder`
with any positive folder predicate yields the empty set (an actor cannot be both unfoldered and at a
node); that is a legitimate empty result (exit 0), not an error.

## Edge cases & errors

- `--folder-exact 'a..b'` / a wildcard / bad char → `validate_folder_path` raises → exit 2 naming the
  value (same path as `--folder-exact` grammar-check in the handler, mirroring `query.py:37-43`).
- Matches nothing → empty stdout, exit 0 (a folder predicate is glob-like; an empty selection is
  legitimate pipeline data, per conventions "empty GLOB or set result is not [an error]").
- Trunk-only: `--folder-exact` is a folder surface, so it must join the `--tree stash|prefab`
  rejection in `routes.py:67` (extend the guard condition to also fire on `folder_exact`).
- `--folder-exact` + `--folder`: OR within the folder dimension (union of the two match sets).

## Tests

Extend `uedcli/tests/test_folders.py` / `test_folderlib.py`:

- Fixture with actors at `castle.tower` and `castle.tower.roof`: `--folder-exact castle.tower`
  returns only the former; bare `--folder castle.tower` returns both (regression contrast).
- Case-insensitive match.
- Repeated `--folder-exact` ORs; ORs with `--folder`.
- Invalid path (wildcard / `a..b`) exits 2, no traceback.
- `--tree stash` rejected.
- Unit test for `folderlib.matches_exact` (equal, subtree-child excluded, None excluded).

`docs/usage.md` Folders section (~line 331-351): document `--folder-exact` and contrast it with the
subtree-including bare `--folder`.

## Open questions

- `questions/surface-flag-vs-sigil.md` — separate `--folder-exact PATH` flag vs a `=PATH` sigil on
  `--folder`.
