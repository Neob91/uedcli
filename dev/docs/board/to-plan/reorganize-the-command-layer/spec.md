# Command-layer reorganization

*Two behavior reviews and a four-model layout review with follow-up rounds produced the boundary and
gates below. No further spec review is planned.*

## Goal

Make adding or changing one command local to that command family. Today almost every CLI change edits
both `cli.py` and `dispatch.py`, which combine unrelated command families and create merge conflicts.
The reorganization must preserve every user-visible and persistence behavior.

At the start of this work:

- `cli.py` is 1,836 lines; `build_parser` is 1,471 of them.
- `dispatch.py` is 5,118 lines, references 50 production modules across module and function-local
  imports, and has 111 top-level definitions.
- `dispatch._dispatch` is a 1,217-line route plus handler.
- `userdocs.py` and `preview_game.py` import private names from `dispatch.py`, forming an import cycle.
- Tests patch `dispatch._resolve_level_source` at more than 100 call sites, making its location an
  accidental interface.

## Target structure

```text
uedcli/
  __main__.py
  cli/
    __init__.py              docstring only
    main.py                  parser assembly and `main`
    dispatch.py              selected-family routing and process error boundary
    errors.py                command-facing errors
    resources.py             project and game-resource resolution
    level_sources.py         level/stash/prefab loading, saving and selection
    ingest.py                cross-family T3D input and validation
    targets.py               cross-family name/stdin and selector resolution
    rendering.py             actor/stash/prefab rendering orchestration
    placement.py             stash/prefab apply merge
    generators.py            actor/brush generator post-processing
    parsers/
      __init__.py            docstring only
      _arguments.py          internal argument types and shared flags
      actor.py               one registrar per top-level command family
      brush.py
      mover.py
      level.py
      event.py
      project.py
      classes.py             registers the `class` family
      stash.py
      prefab.py
      docs.py
      texture.py
      substrate.py
      cache.py
    commands/
      __init__.py            docstring only
      actor/
        __init__.py          docstring only
        routes.py
        query.py             find, show and bbox
        edit.py              add, duplicate, order, delete, move and rotate
        build.py
        folder.py
        label.py
        prop.py
        preview.py           actor-specific selection and `--from-t3d`
      brush/
        __init__.py          docstring only
        routes.py
        build.py
        edit.py              scale, apply-transform, clip, replace and CSG intersect
        poly.py
        vertex.py
      mover.py
      level.py
      event.py
      project.py
      classes.py             handles the `class` family
      stash.py
      prefab.py
      docs.py
      texture.py
      substrate.py
      cache.py
```

Every top-level command family has one parser registrar and one handler module or package.
`classes.py` is the sole spelling exception because `class` is a Python keyword. A handler family is
a package when its parser has at least two sibling command-group namespaces directly below
`<family>`; today this means actor (`folder`, `label`, `prop`) and brush (`build` shapes, `poly`,
`vertex`). Size alone does not change the shape. Their `routes.py` modules import only the selected
feature module.

Existing model, geometry, package, editor, storage, preview-service and native modules stay in their
current flat locations. `level_select.py` folds into `cli/level_sources.py`, and preview orchestration
currently embedded in `dispatch.py` moves; services such as `preview_game.py` remain outside the CLI
boundary. Grouping the other flat subsystems is a separate change after their existing dependency
cycles are addressed.

## Dependency rules

The intended direction is:

```text
__main__ -> cli.main -> cli.parsers
                       \-> cli.dispatch -> selected cli.commands family
                                             |-> named cross-family orchestrators
                                             |-> model/domain services
                                             \-> infrastructure adapters
```

The implementation must enforce these structural rules with an AST import test:

1. `__main__.py` uses `from .cli.main import main`, importing the function rather than the `main`
   module.
2. `cli.main` imports parser registrars at module scope and imports `cli.dispatch` only inside
   `main()`, after argument parsing.
3. Modules under `cli.parsers` may import within that subtree, especially `_arguments`, and lower
   services outside `cli/`. They import no other `cli` module. Only `cli.main` imports the parser tier.
4. Execution dependencies follow this total order: `errors`, `resources`, `level_sources`, `ingest`,
   `targets`, `rendering`, `placement`, `generators`, `commands`, `dispatch`, then `main`. A module may
   import an earlier owner and lower services outside `cli/`, never a later owner.
5. `ingest`, `targets`, `rendering`, `placement` and `generators` are the cross-family orchestrators.
   They never import a command family. A command family never imports another family.
6. `cli.dispatch` uses explicit function-local imports to load only the selected family and contains
   no command implementation. To preserve the current ordered process boundary, it may import these
   error owners at module scope: `cli.errors`, `config.ConfigError`, `model.CoordinateError`,
   `geometry.GeometryError`, `driver.DriverError`, `classindex.ClassRefError`, `uprops.SchemaError`
   and `schema_cache.CacheWriteError`.
7. No production module outside `cli/`, except `__main__.py`, imports any `cli` module.
8. Every `__init__.py` under `cli/` is docstring-only: no imports or re-exports.
9. No strongly connected component contains a `cli` module.

The test walks every `Import` and `ImportFrom` node, including function bodies, and names both modules
and the forbidden edge. Routing uses ordinary local imports rather than dynamic `importlib` calls, so
it remains statically enforceable. Fresh-process route tests—not the AST test—prove that actor and
brush `routes.py` load only the selected feature module. The AST test applies to every production
module without freezing existing low-level cycles.

Introduce a port only where implementations already share a real boundary. The level/stash/prefab
source seam qualifies. Do not add an interface, wrapper or dependency container for every helper.

## Parser adapter

`cli/main.py` creates the root parser, invokes one registrar per top-level command family, and imports
the dispatch entry point only after parsing. It contains no command-family parser definitions.

`cli/parsers/_arguments.py` owns scalar argument parsers, negative-coordinate behavior and shared
flags. Its private spelling keeps the public modules in `cli/parsers/` in one-to-one correspondence
with command families.
Each family module registers its own parser subtree. Registration order, parser class, `dest` names,
defaults, choices, required groups, metavars, descriptions and help text remain exact.

The first delivery commit contains only baseline fixtures generated from the unchanged parser. They
contain:

- every reachable `--help` result with `prog` and terminal width pinned;
- an action-tree representation containing parser and action class names, action order, option
  strings, `dest`, `nargs`, `const`, normalized default, `required`, choices, metavar, converter
  name, and mutually-exclusive group membership and order;
- valid and invalid argv cases for negative coordinates, `-X`/`-Y`/`-Z`, prefix abbreviation,
  required and mutually-exclusive groups, and multiple simultaneous mistakes.

Callable converters compare by stable `__name__`, not object identity or defining module, because the
move changes that module. The argv corpus compares normalized `Namespace`, exit code, stdout and
stderr. A fresh-process fixture also pins the parser's exact non-CLI production service-module
closure. The fixtures and existing help-completeness tests must match after each parser move.

## Command handlers and routing

`cli/dispatch.py` retains only:

- the public `dispatch(args) -> int` process boundary;
- explicit function-local routing to the selected family;
- the current ordered process-error guard.

The guard remains central and preserves its arm order: `CommandError` (including project and level
selection), `ConfigError`, `CoordinateError`, `GeometryError`, `DriverError`/`TimeoutError`,
`ClassRefError`, `SchemaError`, `CacheWriteError`, `BrokenPipeError`, then `OSError`. Keeping
`TimeoutError` before its `OSError` base preserves the editor-specific message. `UserDocsError` is the
only new translation into `CommandError`; existing family-local translations stay local. One
regression case for every exception class in today's guard proves identical stderr and exit status.

Parser construction may import all `cli.parsers` modules but no `cli.dispatch` or `cli.commands`
module. Dispatch loads only the selected family; actor and brush routes then load only the selected
feature module. Fresh-process `sys.modules` tests invoke every top-level family and prove it loads no
other family's command module. `docs` and `cache` additionally serve as low-dependency sentinels: they
load no command module except their own. The actor and brush route matrix proves each subcommand loads
only its owning feature module. Service dependencies are pinned separately from command modules.
Parser construction, `docs` and `cache` must not load `apply`, `materialize`, `editor`, `preview_game`,
`preview_native`, `native.*`, `uedcli_native`, or optional image/native dependencies; a selected heavy
family may load only the heavy stack it actually uses.

Handlers move by cohesive vertical slice. The first move is literal: preserve control flow, validation
order, lazy resolution, output and exception handling before doing local cleanup. Function-local
imports stay function-local during that move; hoisting them could change startup dependencies or
reintroduce a cycle. A later cleanup may extract repeated logic within that slice, but code movement
and behavior changes must not be combined.

A handler may coordinate model and infrastructure modules and write its CLI output. Domain operations
and reusable formatting stay in their existing focused modules. `argparse.Namespace` must not spread
into model/domain APIs that do not already receive it. A cross-family orchestrator owns only behavior
used by at least two families; family-specific code never moves there merely to shorten a file.

## Cross-family seams

### Errors

`cli/errors.py` defines `CommandError`, `ProjectError` and `LevelSelectionError`. `ProjectError` and
`LevelSelectionError` specialize `CommandError`; `_SelectionExit` becomes `CommandError`, and the old
private classes are deleted when callers move.

`userdocs.py` defines a service-specific `UserDocsError` instead of importing the CLI boundary.
`cli/commands/docs.py` translates it to `CommandError`. The central guard retains every other current
cross-family catch. Error text and exit codes remain unchanged.

### Resources

Moved seams take public names (`resolve_project`, `composed_dirs`, `class_defaults`, `mover_index`,
and so on); their old private names are deleted when callers move.

`cli/resources.py` owns project and game-resource resolution shared across command families: project
resolution, prefab-root resolution, composed dirs/load set, schema resolver, class schema and
defaults, struct and enum lookup, class and mover indexes, texture resolution, and effective default
Location lookup.

`preview_game.py` does not import the CLI boundary. Its caller passes a zero-argument provider that
returns a frozen, keyword-only value containing composed dirs, load set and schema resolver. The
preview service invokes it only when materialization needs those values: never before shot/PlayerStart
validation and never on a materialized-map cache hit. Characterization tests pin both cases.

Resolution otherwise remains lazy: a command that does not need a project, game config, schema,
texture or native extension must not start needing one because modules were reorganized.

### Level sources

Move `TrunkLevelSource`, `StashLevelSource`, `PrefabLevelSource`, `resolve_level_source`,
`resolve_level_only`, ambient-level selection and announcement behavior into
`cli/level_sources.py`. Fold the current `level_select.py` helpers into this owner. Resolver functions
take public names; old private names and `level_select.py` are deleted when callers move. The module
uses `cli.resources`, never the reverse.

Stash-register storage remains in `stash_register.py`, which gains a public project-scoped factory.
`cli/level_sources.py` uses that factory for `--tree stash/NAME`; `cli/commands/stash.py` owns
argument-level register resolution for stash verbs.

The shared source protocol exposes the capabilities handlers actually use:

- `kind`, `display_name` and `is_from_ambient_level`;
- `ranks`, empty for a stash or prefab;
- optional `git_scope`, replacing concrete-type and `trunk_dir` checks;
- `load()`;
- `save(..., ranks=...)`, including the rank-override channel.

Preserve exactly:

- trunk delta writes, per-level locking and rank overrides;
- trunk folder and label sidecars, including folder-only and label-only deltas;
- current stash/prefab metadata, folder and tree behavior; this does not add label persistence to
  their wrapper currency or widen the trunk-only label-editing scope;
- explicit `--tree` validation and path-safety checks;
- level-only rejection behavior;
- the one-time `$UEDCLI_LEVEL` mutation announcement and capture announcement;
- validation before writes and all-or-nothing batches.

### Cross-family orchestrators and test seams

A family may use these owners without importing another family:

- T3D input and validation: `cli.ingest`;
- name/stdin and selector resolution: `cli.targets`;
- actor/stash/prefab rendering: `cli.rendering`;
- stash/prefab apply merge: `cli.placement`;
- actor/brush generator post-processing: `cli.generators`.

Patchable cross-family seams have one owner:

- project, schema, class, mover and texture resolution: `cli.resources`;
- level, stash and prefab source resolution: `cli.level_sources`;
- cross-family coordination: its named `cli` module;
- feature-local coordination: that feature's command module.

Handlers use module-qualified lookup for these seams, such as `resources.mover_index(...)`, rather
than binding a directly imported alias that an owner-module patch cannot replace. Explicit injection
is allowed where clearer. Tests patch the owner. Moving a seam includes a mechanical, total patch-path
and name sweep across production, tests, scripts, committed harnesses and comments in the same slice;
a repository-wide stale-owner check follows each deletion. Feature-specific tests otherwise move with
their handler. No forwarding export remains at an old path.

## Behavior preservation

This change must not alter:

- command, flag, argument or help spelling;
- argparse acceptance, rejection or error order;
- stdout, stderr, JSON, exit code or broken-pipe behavior;
- which commands need a project, game config, schema, texture data, editor or native extension;
- validation order, including errors that must occur before expensive resolution;
- empty-stdin no-ops, including whether source resolution currently happens before the no-op;
- name resolution, deduplication or batch atomicity;
- save, stdout and stderr order, including commands that currently print before saving and ambient
  announcements emitted inside `TrunkLevelSource.save`;
- T3D parsing, emission, transforms or geometry;
- trunk, stash or prefab persistence and concurrency semantics;
- editor, container, package or native materialization behavior.

Before a handler moves or any of its resource/source calls are rewired, ordering characterization
tests record its relevant sequence of argument checks, source resolution/load, expensive resolver
construction, mutation, save, stdout and stderr. They cover at least materialize output checks,
preview mode/shot validation, brush scale's cheap checks, folder/label validation, empty stdin inside
and outside a project, and mutation success output. They also prove that `actor order` and non-default
`actor add --order` reject stash/prefab targets without resolving a project or ambient level, and that
`actor preview --from-t3d` runs without resolving an ambient level. Existing CLI-consistency and
name-not-found sweep tests remain part of this baseline. Extraction must preserve the recorded order
rather than normalize it.

No compatibility aliases or forwarding exports remain after callers and tests move. The old internal
location is deleted in the same change that establishes the new one. Code comments and docstrings that
name a moved owner are updated in that slice.

Because no user-visible behavior changes, `docs/usage.md` and `docs/leveldesign/` do not change.
Before implementation, inventory every affected file under `dev/docs/`, propose its exact replacement
text and wait for the owner's approval; this includes rationale statements changed by the reverse-
dependency removal and links broken by file moves. Propose the final `dev/docs/architecture.md` module
map separately when the implementation has settled, and wait again before editing it.

## Delivery boundaries

Land this as reviewable, behavior-preserving slices:

1. Add parser, parser-import, ordering, source-behavior and current error-boundary characterization
   in a tests-only commit. Include one stderr/exit assertion for every exception class currently
   caught by `dispatch()`. Change no production path or patch target.
2. Remove the two reverse dependencies while files are still in their current locations. The existing
   docs dispatcher catches `UserDocsError` and re-raises `_SelectionExit` until the docs family moves.
   `preview_game.py` receives the lazy provider above, which stays uncalled on validation refusal and
   cache hit.
3. Atomically move `cli.py` to `cli/main.py` and `dispatch.py` to `cli/dispatch.py`; add import-free
   package initializers and update every production module, test, script, committed spike/integration
   harness, comment and patch path. In the same slice, change `pyproject.toml`'s console entry point to
   `uedcli.cli.main:main`, include every new package in setuptools' static package list, and smoke-test
   the console script from a built wheel. Also smoke-test `python -m uedcli` and `bin/uedcli`, proving
   `__main__.py` imported the function rather than its module. A repository-wide stale-import check
   covers callers outside `bin/test`. Do no extraction or cleanup in this path-only slice, and leave
   no forwarding module. Every later slice that creates a package updates the static list and reruns
   the wheel-content and installed-command checks.
4. Extract `cli.errors`, `cli.resources` and `cli.level_sources`; fold `level_select.py`, add the
   stash-register factory, and complete the cross-family patch-path sweep. Move source classes
   literally before adding public capabilities and replacing concrete attribute checks.
5. Split parser registration into `cli.parsers`.
6. Extract `cli.ingest`, `cli.targets`, `cli.rendering`, `cli.placement` and `cli.generators` without
   moving family-specific behavior into them.
7. Move low-coupling families (`docs`, `cache`, `project`, `classes`, `texture`, `substrate`).
8. Move cross-family actor/stash/prefab rendering orchestration, then each thin family route; keep level
   preview in the level family.
9. Move the remaining stash, prefab, level and event handlers.
10. Move actor, brush and mover handlers, starting with a small query such as `actor bbox`; add the
    final AST boundary and import-isolation assertions as each forbidden edge disappears.

The AST test starts by enforcing no reverse imports and import-free package initializers, then gains
each final rule in the slice that makes it true. No transitional allow-list remains after slice 10.
Do not retain a half-moved family that imports another family or reaches back through the monolith.
Run targeted tests after each commit and the complete host-native offline suite at the end of every
numbered slice; "green" means both passed.

## Out of scope

- Reorganizing `model.py`, T3D parsing/emission, geometry, package readers, editor drivers, preview
  services, storage or stubbing into subsystem packages. That follows after the command boundary and
  existing cycles are stable.
- Refactoring `uedcli/native/` or the Rust crate.
- Fixing the low-level `emit`/`model`/`rotation`/`transform`/`writes`, `driver`/`xfer`,
  `schema_cache`/`uprops`, or `builders`/`query`/`surface`/`texframe` cycles. Those are separate
  changes after the command boundary is stable.
- Changing command behavior while moving it.
- Adding a general dependency-injection framework.

## Acceptance

1. The complete command boundary lives under `cli/`; only `__main__.py` imports it from outside.
2. `cli/main.py` assembles parsers and imports dispatch after parsing; family registrars live in
   `cli/parsers`.
3. `cli/dispatch.py` routes lazily and handles the stated process-wide failures; implementation lives
   in the selected `cli.commands` family or a named cross-family orchestrator.
4. Actor and brush are packages under the stated sibling-command-group rule; every other command family
   is an enumerated module, and `classes.py` is the only keyword-driven spelling exception.
5. No family imports another family, every CLI package initializer is import-free, dependencies obey
   the stated leftward order, and no CLI strongly connected component exists.
6. The AST boundary test enforces every structural dependency rule above, including function-local
   imports.
7. The complete help, action-tree and valid/invalid argv corpus matches the pre-move baseline.
8. Fresh-process tests prove parser construction has the exact baseline service closure; every
   top-level family invocation avoids all other families' command modules; and low-dependency commands
   plus every actor/brush route avoid unneeded optional dependencies and heavy stacks beyond the exact
   allowances above. Only parser construction must avoid `cli.dispatch` itself.
9. Every exception class caught by the original process boundary retains its stderr text and exit
   code, with no user-facing traceback.
10. Ordering tests prove unchanged validation, resolution, load, save and output order for every
    moved slice, including the source-free guards named above.
11. Source tests prove unchanged interleaved-writer, lock, rank-override, unchanged-file,
    folder-only and trunk-label-only behavior.
12. A package-metadata test proves every discovered package under `uedcli/cli/` appears in setuptools'
    static package list. Every package-creating slice builds a wheel, verifies its `cli` contents, and
    smoke-tests the installed console script; slice 3 also tests `python -m uedcli` and `bin/uedcli`.
13. Targeted tests pass after every commit and the complete host-native offline suite passes after
    every numbered slice.
14. The final diff contains no user-facing behavior or user-documentation change.
