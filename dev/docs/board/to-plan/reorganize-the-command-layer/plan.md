# Plan: reorganize the command layer

*Implements `spec.md`. Ephemeral: read the spec first; this plan only sequences it. File references
are to `626a1db`; re-run each inventory before moving code.*

## Ground rules

- Work only in the dedicated worktree. Stage named paths and keep unrelated index content out of every
  commit.
- Move before cleaning. A movement commit changes paths, imports and tests only. Cleanup follows in a
  separate green commit.
- No compatibility modules, aliases or old patch paths. Each deletion gets a repository-wide stale-
  owner search covering production, tests, scripts and committed harnesses.
- Preserve validation, resolution, save and output order. The characterization fixtures, not a
  preferred new order, decide disagreements.
- Run targeted tests after every commit and `bin/test` after every numbered slice. A slice that creates
  a package also builds and inspects a wheel and smoke-tests the installed command.
- Keep `cli/dispatch.py`'s expected-error arms in their current order. Only the three CLI-owned errors
  collapse into `CommandError`.
- Keep each slice as green local worktree commits for review. The repository's standard final squash
  merge still lands the completed feature on `master` as one commit.

## Approval gate — developer documentation

Before implementation, inventory every affected path and assertion under `dev/docs/`, prepare the
exact patch and get the owner's approval. The initial inventory includes:

- hard links to `uedcli/cli.py` or `uedcli/dispatch.py`, including `rationale/surface.md`;
- rationale that names an owner being changed, especially `rationale/userdocs.md`, `rationale/cli.md`,
  `rationale/mapimport.md`, `rationale/driver.md` and `rationale/reported-coordinates.md`;
- every committed spike and integration harness import found by a repository-wide grep, including the
  current poly-rotate, brush-idiom, preview-focus and preview-pose matches;
- command references in `unrealed/commands.md` and `unrealed/quirks.md`.

Do not edit those files until that patch is approved. If a later inventory finds another affected
`dev/docs/` path, stop and obtain approval for its exact patch before editing it. Propose the final
`architecture.md` module-map patch separately after the implementation settles.

After the reviewed plan and initial documentation patch are approved, move the item from `to-plan/`
to `to-build/` before slice 1.

## Slice 1 — freeze current behavior in tests only

Add no production code.

### Parser baseline

Create a fixture generator and checked-in fixtures for:

- every reachable help screen at a pinned terminal width and `prog`;
- the normalized argparse action tree: parser/action classes, order, option strings, `dest`, `nargs`,
  `const`, defaults, required state, choices, metavar, converter name and mutually-exclusive groups;
- the valid/invalid argv corpus from the spec, including simultaneous mistakes and negative-coordinate
  cases;
- the parser's exact non-CLI production-module closure in a fresh process.

The comparison normalizes callable converters by name. Regeneration is an explicit test helper, never
an automatic update on failure.

### Ordering and error baseline

Add call-order probes around the existing seams for:

- materialize output validation;
- preview shot/mode validation and the preview-game cache-hit/PlayerStart/`--map` gates;
- the resource-call matrix: plain actor find, typed-field-only property edits, wire preview,
  point-only preview, pure-brush wire preview and each mover/schema/index-dependent variant;
- brush scale's cheap checks;
- folder and label target validation;
- empty stdin inside and outside a project;
- save-before-output ingest, plus each distinct output-before-save branch in actor rotate, brush scale,
  apply-transform and poly align, including a failing save and ambient announcement;
- stash preview's project/register/existence/read order and prefab preview's name/path/read order before
  rendering;
- the missing-project and missing-games-config paths through mover-index translation, including actor
  preview's tailored error;
- `actor order` and non-default `actor add --order` against stash/prefab without a project or ambient
  level;
- `actor preview --from-t3d` without an ambient level.

Before each later seam or handler move, name the characterization test that covers its ordering and
add a missing one first.

Add one stderr/exit regression for every class in the current `dispatch()` guard, including the
`TimeoutError`-before-`OSError` distinction.

### Source baseline

Fill only missing coverage in the existing source tests: interleaved writers, rank override,
unchanged-file, folder-only and label-only trunk writes, plus stash/prefab metadata and folder
behavior. Prove `LOCK_EX` occurs before the trunk write and remains held during it. Add a parameterized
stash/prefab round trip proving actor labels are neither persisted nor restored.

**Commit:** tests and fixtures only.

## Slice 2 — remove the two reverse imports

### `userdocs.py`

Add `UserDocsError` and raise it with the current messages. The existing `_dispatch_docs` catches it
and re-raises `_SelectionExit` during the transition. When the docs family moves, its handler converts
it to `CommandError` directly.

### `preview_game.py`

Add a frozen, keyword-only value for composed dirs, load set and schema resolver. Thread a required,
keyword-only zero-argument provider from `_level_preview` through `render_shots` to `materialized_dx`.
Invoke it only after PlayerStart validation and the materialized-map cache miss. Keep map-file preview
independent of it; do not add a `None` default or fallback.

Verify the provider is untouched on cache hit, `--map`, and PlayerStart refusal. Confirm production has
no `from .dispatch` edge.

Add the first AST assertion here: production modules outside the command boundary do not import
`dispatch` for command-owned helpers.

**Commit:** reverse-import removal and its tests. Apply the approved developer-doc patch for this
slice in the same commit.

## Slice 3 — atomically establish the `cli/` package

This is a path-only flag day:

- `git mv uedcli/cli.py uedcli/cli/main.py`;
- `git mv uedcli/dispatch.py uedcli/cli/dispatch.py`;
- add a docstring-only `uedcli/cli/__init__.py`;
- change relative imports for the extra package depth without moving or cleaning code;
- make `uedcli/__main__.py` use `from .cli.main import main`;
- change the console entry point to `uedcli.cli.main:main`;
- add `uedcli.cli` to setuptools' static package list.

Update all production imports, tests, patches, scripts, committed spike/integration harnesses, comments
and approved developer-doc links in the same commit. Search for the deleted module paths afterward;
there is no forwarding module.

Add the import-free CLI-initializer AST assertion. Add a metadata test scoped to packages under
`uedcli/cli/` and require each in the static list. The pre-existing omission of non-CLI runtime
subpackages is tracked separately and is not widened into this reorganization. Build a wheel and
prove:

- every current CLI package is present;
- the installed `uedcli --help` works;
- `python -m uedcli --help` works;
- `bin/uedcli --help` works.

**Commit:** path relocation, packaging metadata and mechanical caller updates only.

## Slice 4 — extract errors, resources and level sources

Use separate green commits inside the slice.

### 4A — command errors and resources

Create `cli/errors.py` with `CommandError` and `ProjectError`; retain the current `.message`
attribute. Keep the existing `level_select.LevelSelectionError` arm until 4B. Audit every local catch
while introducing the hierarchy: a generic `CommandError` catch must re-raise `ProjectError` before
translating command errors, preserving the mover-index and actor-preview messages pinned in slice 1.
Preserve the central guard's order and messages for `ConfigError`, `CoordinateError`, `GeometryError`,
`DriverError`/`TimeoutError`, `ClassRefError`, `SchemaError`, `CacheWriteError`, `BrokenPipeError` and
`OSError`.

Move the project/game resolution seams literally to `cli/resources.py`: project and prefab roots,
composed dirs/load set, schema resolver, class schema/defaults, struct/enum lookup, class/mover indexes,
the shared `propedit.ClassCtx` construction, texture resolver and effective default Location. Rename
them publicly and switch all tests to patch this owner with module-qualified lookup.

### 4B — source implementations

Move the three source classes and source/ambient selection into `cli/level_sources.py`. Move
`LevelSelectionError` into `cli/errors.py` in the same commit, fold `level_select.py` into the new
owner and delete that file. Add the project-scoped stash-register factory to `stash_register.py`;
leave argument-level stash resolution in `cli/dispatch.py` until the stash family moves.

First preserve concrete attributes exactly. In a later commit, add the protocol capabilities
(`kind`, `display_name`, ambient marker, `ranks`, optional `git_scope`, `load`, `save`) and replace
`isinstance`/private-attribute checks.

Extend the AST test with the leftward order for the newly established owners.

**Wheel:** no new package, but run the normal slice suite.

## Slice 5 — split parser registration

Create `cli/parsers/` with docstring-only `__init__.py`, private `_arguments.py`, and all 13 family
registrars. `_arguments.py` owns scalar converters, `_CoordArgumentParser`, shared flags and shared
parser helpers. Keep family-only helpers with their registrar; keep function-local imports local.

`cli/main.py` creates the root parser and invokes registrars in the current order. It imports
`cli.dispatch` inside `main()` after parsing. `classes.py` is the only spelling exception for the
`class` family.

Compare help, action tree and argv fixtures after each registrar move. Add `uedcli.cli.parsers` to the
static package list, build the wheel and rerun all three command smoke tests.

**Commits:** parser package skeleton and shared arguments; then registrar moves in small groups; then
`main.py` cleanup.

## Slice 6 — extract the five cross-family orchestrators

Move only logic used by at least two command families:

- `cli/ingest.py`: the cross-family `_read_t3d_input`, `_read_t3d_files` and
  `_validate_ingest_actors` logic only; stash capture stays with stash and actor ingestion stays with
  actor;
- `cli/targets.py`: names/stdin and actor target-token resolution only; polygon and surface selector
  parsing stays in `surface.py`;
- `cli/rendering.py`: the shared block from world bounds through render output, brush extraction,
  point/render-data preparation and related preview argument interpretation; family-specific preview
  entry functions stay in dispatch until slice 8;
- `cli/placement.py`: stash/prefab apply merge;
- `cli/generators.py`: actor/brush generator organization and rotation post-processing.

Respect the spec's leftward order. In particular, placement may use ingest; no orchestrator imports a
command family. Leave thin family routes in the monolith for now. Move tests and patch paths to the
new owner; do not export old names from dispatch.

**Commits:** one orchestrator at a time, each green.

## Slice 7 — move low-coupling families

First remove the currently unused module-scope `editor` import from `cli/dispatch.py` in its own green
cleanup commit and re-baseline the import-closure fixture. Then create docstring-only
`cli/commands/__init__.py` and move these complete families, one per commit where practical:

1. docs;
2. cache;
3. project;
4. classes;
5. texture;
6. substrate.

Each module exposes the same family entry shape. `cli/dispatch.py` selects it with an explicit
function-local import. A family imports orchestrators/resources/services, never another family.

After docs and cache move, add their fresh-process heavy-import sentinels. Add one fresh-process
family-isolation case for every moved family. Add `uedcli.cli.commands` to package metadata and rerun
the wheel/content/installed-command checks.

## Slice 8 — move cross-family rendering routes

Move the thin actor/stash/prefab preview entry functions out of dispatch and make them call the
shared `cli.rendering` API established in slice 6. Do not move level preview into it.

- Add docstring-only `cli/commands/actor/__init__.py`, `actor/routes.py` and `actor/preview.py`.
  Dispatch enters the family through `routes.py`; it handles preview while explicitly returning other
  actor subcommands to the transitional dispatch branch without importing dispatch. `--from-t3d`
  performs its no-source guard before source resolution.
- Route stash/prefab preview through their target modules. Preserve the complete current prologues in
  those preview paths: stash resolves the project/register and validates existence before reading;
  prefab validates the name before any path or filesystem operation. Their other subverbs remain in
  the monolith until slice 9; these modules never import back through dispatch.
- Keep level preview with the level family.

Add the actor preview feature-isolation cases. Add `uedcli.cli.commands.actor` to package metadata and
rerun wheel and installed-command checks.

## Slice 9 — complete stash, prefab, level and event

Move the remaining stash and prefab handlers into their existing family modules, then move complete
level and event families. Preserve:

- stash/prefab validation before reads or writes;
- level import destination and path-safety order;
- materialize/preview validation before expensive resources;
- source resolution timing and ambient announcements;
- save/output ordering.

Add one fresh-process family-isolation invocation for each family. No family imports another; stash and
prefab share placement/rendering through the named orchestrators.

**Commits:** stash+prefab; level; event.

## Slice 10 — finish actor, brush and mover; reduce dispatch to the boundary

### Actor package

Extend the existing `routes.py`, starting with `actor bbox` as a green pilot, then move:

- `query.py`: find, show, bbox;
- `edit.py`: add, duplicate, order, delete, move, rotate;
- `build.py`, `folder.py`, `label.py`, `prop.py`;
- the already-moved `preview.py`.

The route owns source-free guards and imports only the selected feature module. It preserves the
non-default order rejection and `--from-t3d` early route before source resolution.

### Brush package

Create the docstring-only package and move:

- `routes.py`;
- `build.py`;
- `edit.py`: scale, apply-transform, clip, replace, intersect and deintersect;
- `poly.py`;
- `vertex.py`.

`routes.py` preserves the current eager, single source resolution before every source-consuming brush
branch, including empty stdin and cheap branch validation, and imports only the selected feature
module.

### Mover and final boundary

Move mover to `commands/mover.py`. Delete the last implementation from `cli/dispatch.py`; it retains
only function-local family routing and the ordered process-error guard. Delete every old owner and
patch path.

Complete the AST dependency test and the full actor/brush route matrix. Add
`uedcli.cli.commands.brush` to package metadata, then build and inspect the wheel and run all command
smokes.

**Done when:** `cli/main.py` is parser assembly, `cli/dispatch.py` is routing/error handling, every
family and orchestrator has one owner, all structural/import-isolation tests pass, no stale path
remains, and the complete offline suite is green.

## Final documentation and board work

After the module layout has settled, prepare the exact `architecture.md` module-map patch and obtain
the owner's approval. Apply it, rerun doc links and the full offline suite, then move the board item to
`done/` and trim `overview.md` to a one-line record only when implementation lands. The user-facing
docs remain unchanged.

## Risks

- **Atomic path move:** source tests do not cover committed harnesses or every markdown link. The
  repository-wide caller inventory and approved doc patch are required gates.
- **Parser equivalence:** argparse behavior depends on registration order, action classes and shared
  object identity. The baseline compares all of them except converter module paths.
- **Exception drift:** moving catches into families would miss cross-family failures. Keep the current
  central chain and its order.
- **Lazy-resolution drift:** preview cache hits, source-free actor routes and empty stdin are the main
  places a convenient eager resolver would change behavior.
- **Package omission:** setuptools uses a static list. The metadata test plus wheel checks at every
  package-creating slice prevent source-tree-green but broken installs.
- **Concurrent edits:** `cli.py` and `dispatch.py` are conflict hotspots. Build only in the worktree,
  stage explicit paths and keep movement commits narrow.
