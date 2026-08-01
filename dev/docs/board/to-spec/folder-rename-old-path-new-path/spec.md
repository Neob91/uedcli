# Spec — `actor folder rename <old-path> <new-path>`

## Goal

Re-parent / rename a whole folder subtree in one call: rewrite the `folder` sidecar of every actor
filed under `<old-path>` so its prefix becomes `<new-path>`. Deferred from actor-folders v1
(assign-only). Example: `actor folder rename castle.tower keep.spire` moves `castle.tower` and
`castle.tower.roof` → `keep.spire`, `keep.spire.roof`.

## Naming / home

**`actor folder rename`, not a top-level `folder rename`.** `direction/organization.md` rules out a
top-level `folder`/`label` verb family ("they organize actors, `actor` is where a user looks"); the
board title predates that ruling. The item lives under the existing `actor folder set|unset|get`
group (`uedcli/cli/parsers/actor.py:162-191`, `uedcli/cli/commands/actor/folder.py`).

## Current state

- Folder sub-verbs parser: `uedcli/cli/parsers/actor.py:162-191` (`set` uses `--to PATH`; `set`/
  `unset`/`get` take variadic names or `-`). Add a `rename` sub-parser here.
- Handler: `uedcli/cli/commands/actor/folder.py:18-59` — resolves the trunk source, reads names,
  validates path, writes each `level.actors[n].folder`, saves via `src.save(...)`, echoes touched
  names to stdout + count to stderr (producer). `rename` follows the same save/echo shape but selects
  its actor set by **path**, not by a name list.
- Path grammar: `folderlib.validate_folder_path` (`folderlib.py:39-53`).
- Subtree/prefix semantics already codified in `folderlib.matches` wildcard-free branch
  (`folderlib.py:124-125`): `f == p or f.startswith(p + ".")`.
- Trunk-only guard: `routes.py:65-66` rejects `--tree stash|prefab` for `actor folder …`
  (fires on `sub == "folder"` unconditionally, so `rename` is covered automatically).

## Design

    frn = fsub.add_parser("rename",
        help="re-parent/rename a whole folder subtree: rewrite every actor filed at OLD or under it "
             "(OLD and OLD.*) so its OLD prefix becomes NEW. `castle.tower` also moves "
             "`castle.tower.roof`. Folders have no existence apart from the actors filed in them, so "
             "this is purely a bulk sidecar rewrite. Prints the touched actor Names to stdout, the "
             "count to stderr. Trunk-only (rejects --tree stash|prefab).")
    frn.add_argument("old", metavar="OLD-PATH",
        help="the literal source folder path to move (its whole subtree comes with it); "
             "case-insensitive. A path no actor is filed under is an error (exit 2).")
    frn.add_argument("new", metavar="NEW-PATH",
        help="the literal destination folder path; the matched actors' OLD prefix is replaced with "
             "it (segments [A-Za-z0-9_+-], stored as authored).")
    _tree_flag(frn)

Two positionals (not `--from`/`--to`): `rename` has no stdin name-set competing for a greedy
positional, so the ambiguity that forced `folder set` onto `--to` (organization.md "Rejected") does
not arise here, and `<old> <new>` reads naturally. No `-`/stdin: the set is defined by the path.

Rewrite algorithm (single pass over current values, model-side):

    validate_folder_path(old); validate_folder_path(new)     # both, before any write → exit 2
    oldf = old.casefold()
    touched = []
    for n, a in level.actors.items():
        f = a.folder
        if f is None: continue
        ff = f.casefold()
        if ff == oldf:
            a.folder = new;                touched.append(n)
        elif ff.startswith(oldf + "."):
            a.folder = new + f[len(old):]; touched.append(n)   # preserve the tail's authored case
    # not-found handling: see open question
    save + echo touched (mirrors folder.py:52-58)

Case: match is case-insensitive (folder matching always is); `new` is stored as authored, and the
preserved subtree tail keeps its stored case. Prefix swap is mechanical and one-pass, so renaming a
folder into its own subtree (`a` → `a.b`) rewrites originals only (`a`→`a.b`, existing `a.b`→`a.b.b`)
— acceptable, note it in help is not needed but record here.

No collision concern: folders are not unique keys — many actors share a folder — so a rewrite that
lands two subtrees on the same path is fine, it is just re-filing.

## Edge cases & errors

- `old`/`new` fails grammar (empty, `a..b`, bad char, wildcard) → `validate_folder_path` raises →
  exit 2 naming the value. Both validated before any mutation.
- **`old` matches no actor** → recommend **exit 2** naming `old` (conventions: "an exact name
  matching nothing is an error" — `old` is an exact path, not a glob, so a typo should not pass
  silently). This is the one genuine owner call → `questions/`.
- Empty level / stash|prefab target: `--tree stash|prefab` already rejected in `routes.py`.
- `new == old` (case-insensitive): rewrites in place to the authored `new` casing; touched set
  non-empty; effectively a case-normalize. Harmless.
- Producer contract: touched Names to stdout, `renamed <old> → <new> on N actor(s)` to stderr.

## Tests

New cases in `uedcli/tests/test_folders.py`:

- Fixture with actors at `castle.tower`, `castle.tower.roof`, and an unrelated `barn`:
  `rename castle.tower keep.spire` → first two become `keep.spire` / `keep.spire.roof`, `barn`
  untouched; the two names echoed to stdout.
- Segment-boundary safety: a `castle.towerhouse` actor is NOT moved by `rename castle.tower …`.
- Case-insensitive `old`; `new` stored as authored.
- Nest-into-self (`a` → `a.b`) rewrites one pass as specified.
- Bad `old`/`new` grammar → exit 2, no traceback.
- `old` matching nothing → per the answered open question (exit 2 by recommendation).
- `--tree stash` rejected.
- Persisted via the delta save (reload shows new folders) — mirror
  `test_folder_only_change_persists_via_delta_write`.

`docs/usage.md` Folders "Manage" bullet (~line 341): add `actor folder rename <old> <new>`.

## Open questions

- `questions/old-path-not-found.md` — is `rename OLD NEW` where no actor is filed under OLD an error
  (exit 2) or a clean no-op (exit 0)?
