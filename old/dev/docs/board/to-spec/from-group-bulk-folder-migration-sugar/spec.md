# Spec — `--from-group` bulk folder-migration sugar

## Goal

Fold a whole level's flat engine `Group=` values into uedcli folders in one call. Existing
`Group=`-organized levels start with EMPTY folders (folders and `Group` are independent — `Group` is
never auto-absorbed, `direction/organization.md`). Today's per-group recipe is:

    actor find --group cellblock | actor folder set --to act2.cellblock -

`--from-group` derives each actor's folder from **its own** `Group` value, so one call migrates every
group at once instead of one invocation per group.

## Why this can't be plain find|set

`actor folder set --to X` writes the **same** path to every actor. Migration needs a **per-actor**
path (each actor's folder = its own group), which no `find … | set --to …` pipeline expresses. So a
derivation surface is genuinely warranted despite the "prefer one stateless find" convention — that
convention targets redundant filter flags, not a per-actor value map.

## Current state

- Group read: `query._group_matches` (`query.py:146-160`) reads the FIRST `Group` prop, splits on
  comma, case-insensitive. A shared "read this actor's group value" helper does not exist yet;
  factor one out (`group_value(actor) -> str | None`, the raw first `Group` prop).
- Folder set handler + producer/echo shape: `uedcli/cli/commands/actor/folder.py:18-59`.
- Folder path grammar: `folderlib.validate_folder_path` (`folderlib.py:39-53`). Group values are
  FNames; a group token with a char outside `[A-Za-z0-9_+-]` (e.g. a `.`) is not a valid folder
  segment.
- Parser: `folder set` at `uedcli/cli/parsers/actor.py:171-179` (`--to` currently `required=True`).
- Trunk-only guard: `routes.py:65-66` (`sub == "folder"` → reject stash/prefab). Covered.

## Design (recommended surface — see `questions/`)

Put it on `actor folder set` as an alternative to `--to`:

    # --to becomes NOT required; exactly one of --to / --from-group is required (mutually exclusive).
    fset_src = fset.add_mutually_exclusive_group(required=True)
    fset_src.add_argument("--to", metavar="PATH", help=<existing help>)
    fset_src.add_argument("--from-group", dest="from_group", action="store_true",
        help="derive EACH actor's folder from its own engine Group prop instead of a fixed --to "
             "path (bulk-migrate a Group-organized level into folders in one call). With --under P, "
             "the folder is P.<group>; without it, just <group>. An actor with no Group, or with a "
             "multi-valued Group, is an error naming it (see below) — never silently skipped.")
    fset.add_argument("--under", metavar="PREFIX", default=None,
        help="with --from-group only: parent path prepended to each derived folder, so "
             "Group=cellblock becomes <PREFIX>.cellblock (e.g. --under act2 → act2.cellblock).")

Actors still come from the positional names or `-` (unchanged). Derivation, all-or-nothing batch:

    for each resolved actor a:
        g = group_value(a)
        if g is None:                      -> collect as "ungrouped"     (error set A)
        elif "," in g:                     -> collect as "multi-group"   (error set B)
        else:
            path = f"{under}.{g}" if under else g
            validate_folder_path(path)     # bad char/segment -> error set C, naming actor+value
            plan[a] = path
    if any error set non-empty: exit 2, naming all offenders (batch is all-or-nothing)
    else apply plan, save, echo touched names (producer, as folder set does today)

Multi-group and ungrouped handling is an **open question** (recommend: error naming them, per the
no-silent-half-answer rule — a folder is single-valued, so a comma group cannot be mapped, and an
absent group cannot be derived). `--under` prefix surface is the other open question.

## Edge cases & errors

- `--to` and `--from-group` together → argparse mutually-exclusive error (exit 2).
- `--under` without `--from-group` → reject with a clear message (exit 2); it is meaningless with
  `--to`.
- Empty stdin (`-`) → clean no-op, exit 0 (unchanged from `folder set`).
- Actor with `Group=A,B` (multi) or no `Group` → exit 2 naming every such actor (recommended; see
  question), never a partial migration.
- Derived path fails folder grammar (a group value with `.` or other bad char) → exit 2 naming the
  actor and the offending group value.
- Trunk-only: covered by the existing `routes.py` folder guard.

## Tests

New cases in `uedcli/tests/test_folders.py`:

- Fixture: actors with `Group=cellblock`, `Group=lab`, one ungrouped, one `Group=a,b`.
  `folder set --from-group --under act2 -` over the grouped ones → folders `act2.cellblock`,
  `act2.lab`; touched names echoed.
- Without `--under`: folder == bare group value.
- Ungrouped actor in the set → exit 2 naming it, nothing written (reload shows folders unchanged).
- Multi-group actor → exit 2 naming it (per the answered question).
- Group value with a bad folder char → exit 2 naming actor + value.
- `--to` + `--from-group` → exit 2. `--under` without `--from-group` → exit 2.
- Empty stdin → exit 0 no-op.
- Case-insensitive group read; folder stored as authored group casing.

`docs/usage.md` Folders section: add the `--from-group [--under PREFIX]` migration recipe and note it
errors (does not skip) on multi-valued / absent Group.

## Open questions

- `questions/multigroup-and-ungrouped.md` — how to handle an actor with a multi-valued `Group=A,B`
  or no `Group` at all under `--from-group`.
- `questions/surface-and-prefix.md` — flag on `actor folder set` vs a distinct sub-verb, and whether
  the `--under PREFIX` nesting option is wanted.
