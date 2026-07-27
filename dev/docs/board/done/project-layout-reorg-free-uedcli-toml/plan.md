# Plan: project layout reorg — free `uedcli.toml` at the repo root

*2026-07-18. Ephemeral (see docs rules). Implements
`spec.md`; the durable record is `decisions.md`
2026-07-17 20:58 UTC. Read the spec first — this plan only sequences it.*

## Ground rules

- **Four slices, each one commit, suite green (`bin/test`) at every boundary.** Slice 1 is the
  flag-day: after it lands, uedcli only recognizes the new layout, and the LUM repo is migrated in
  the same commit — a concurrent session running *older* code against the migrated repo fails with
  the old code's "no project" error, and older *checkouts* get the new code's explicit old-layout
  error. Announce the flag-day commit in `board/inbox/` when it lands (concurrent-session
  courtesy), and land slices 1–2 close together.
- **No behavior change beyond the spec.** Composition/shadowing, mounts, materialize, preview
  mechanics stay untouched; every path below is a *derivation* change.
- File:line references are to the tree at commit `98f5f2b24`; expect drift from concurrent work —
  re-grep, don't trust blindly.

## Slice 1 — the new project model + `uedcli.toml` cutover + LUM migration (flag-day)

**`config.py` — the model:**
- `Project`: collapse `project_dir`/`root` → one `root`; drop `id`/`name` fields.
  `catalog`/`prefabs`/`maps` resolve against `root` via `_project_subdir` (defaults `maps`,
  `prefabs`, `texture-catalog` per spec §3).
- `_project_toml_path` → look for **`uedcli.toml`**; `load_project` accepts the root dir or the
  file. `_PROJECT_KEYS` loses `id`/`name` (they become unknown-key `ConfigError`s).
- `walk_up_project_dir` → `walk_up_root`: first ancestor **containing an `uedcli.toml` file**
  (nearest wins); no child-dir scan, no ambiguity branch. A malformed OR unreadable (OSError)
  `uedcli.toml` found by walk-up is a hard `ConfigError` (spec §4).
- Keep `_classify` for load-time schema validation of both files (games-table-in-project /
  project-keys-in-user rejections unchanged).
- Rewrite the stale module docstring (the "legacy hardcoded fallback stays in packages.py" claim).

**State-dir helper (new, small — in `config.py` or a tiny `statedir.py`):**
- `state_dir(root, *, create=False) -> <root>/.uedcli`. On create: `mkdir` catching
  `FileExistsError`; write `.gitignore` containing `*` **iff the dir was absent at the start of
  the call** (spec §5). Subdir accessors used by the consumers below
  (`stash/`, `preview/`, `locks/`, `tmp/`, `current-level`).

**Consumers of the old `project_dir` (all move to the state dir in this slice):**
- The stash register is built at **TWO** sites: `dispatch._resolve_stash_register`
  (dispatch.py:1022) AND `_resolve_level_source`'s `--target stash/NAME` branch
  (dispatch.py:989). Factor both through the one helper → `<root>/.uedcli/stash/`.
- `preview_game.py:124` delivery dir: `<root>/.uedcli/preview/`.
- `level_select`: the whole public API (`set_selected`/`get_selected`/`resolve_level`) takes
  `project_dir` — re-anchor the parameter (root or state dir) and update its ~8 dispatch call
  sites (dispatch.py:1013, 1051–1099, 1170–1171, 1274, 1289); pointer becomes
  `<root>/.uedcli/current-level`; retire level_select's own `tmp/.gitignore` writer
  (level_select.py:33–35 — the dir-level self-ignore covers it).
- `dispatch._prefab_root` (dispatch.py:357): `config.project_prefabs_dir(project)` with the
  existing `--prefab-dir` override kept; no project + no flag ⇒ clean `_ProjectError` (spec §6
  behavior change, stated in help text). (`--catalog-dir` needs NO change — dispatch.py:575
  already resolves the project lazily only when no override is given; add the symmetric
  regression test.)
- `dispatch._project_show`: print `root`, `game`, `maps`, `prefabs`, `catalog`, then the search
  path as today (spec §7).
- The generic no-project error exists at **TWO** sites: `dispatch._resolve_project`
  (dispatch.py:871) and `_resolve_level_source`'s inline resolve (dispatch.py:1011) — make the
  latter delegate to `_resolve_project` so the new message ("no uedcli.toml found here or
  above…") and the old-layout child-scan hint (spec §8) live in one place. `config.py:256`'s "no
  config.toml at" message renames with the file.
- `cli.py:143` `--project` help: "project root (or its uedcli.toml)".

**LUM migration (same commit):**
- Write `<repo>/uedcli.toml`: `game`, any `paths` carried over, `maps = "uedcli/maps"`,
  `prefabs = "Prefabs"`, no `catalog` key; **drop `name`** (decision §7).
- Delete `uedcli/config.toml`, `uedcli/tmp/` (throwaway), `uedcli/.gitignore`.
- Do **NOT** touch `<repo>/.uedcli/` or the repo-root `.gitignore` yet — locks/staging still live
  there until slice 2.

**Tests:** rewrite `test_config.py` (filename discovery, nearest-wins nesting, root-relative
defaults, dropped-key errors, unreadable-marker hard error). Build the shared tmp-project fixture
ONCE in `conftest.py` (write a minimal `uedcli.toml`, point `UEDCLI_PROJECT` at it) — it is the
replacement seam for the env overrides retired in slice 3, but it must ALSO keep setting
`UEDCLI_REPO_ROOT` until slice 3 lands (verbs still on `state_root()`/`host_repo_root()` can't
find a CLAUDE.md marker above a tmp path). Then migrate **every** test that writes an old-layout
`<child>/config.toml` or constructs an old-shaped `Project` — the real list is
`grep -rl "config.toml\|project_dir" uedcli/tests/`, at `98f5f2b24`: `test_project_show.py`,
`test_level_select.py`, `test_stash_dispatch.py`, `test_dispatch.py`, `test_target_flag.py`,
`test_level_verbs.py` (:15,38–49 — includes a config.toml-*file*-path test and a schema-sniff
walk-up test that both re-shape), `test_trunk_verbs.py` (:12,89,108,124), `test_stash_trunk.py`
(:14), `test_materialize_verb.py` (:80,114), `test_ingest_validation.py` (:123),
`test_class_discovery.py` (:182), `test_level_source.py` (:17),
`test_integration_stash_intersect.py`, `test_packages.py` (:188 — direct
`config.Project(project_dir=…)`), and `test_preview_game.py` (:48 — a
`SimpleNamespace(project_dir=…, root=…)` fake; breaks with the delivery-dir move). Regression
tests: old-layout error message; `--prefab-dir`/`--catalog-dir` override without a project;
self-ignore written once and not rewritten.

**Docs in the same commit (spec §8):** the layout-bearing `architecture.md` sections this slice
changes (Terminology "T3D tree" path, stash/prefab paths, `project show`, level-select pointer).
`direction.md` and the inbox/to-spec/to-plan board edits are ALREADY current — they landed with
the decision in `98f5f2b24` — so no deferred-stale-docs window exists; each later slice updates
the `architecture.md` sections *it* changes (architecture tracks the code, so per-slice is the
rule-compliant cadence).

**Acceptance mapped:** spec §10.1, .2, .5, .7, and .3 for the stash/preview/select paths.

## Slice 2 — thread the project into the `state_root()` consumers; finish the state-dir move

- Thread the resolved `Project` (or its `state_dir`) as an explicit parameter from `dispatch`
  into:
  - `editor.py` — `_locks_dir` (editor.py:39), override-ini + docker-cp tmp (editor.py:178, 236).
    Callers: `apply.run_materialize`, the stash `intersect`/`deintersect` drivers, preview.
  - `apply.py` — staging tmp (apply.py:176, 182).
  - `qualify.py` — export tmp ONLY (qualify.py:320, 345). Its `root = host_repo_root()`
    (qualify.py:323) is a **tool-asset** anchor (it feeds `editor_search_dirs`/
    `stub_missing_packages` `repo_root` args → UED22/stub cache), NOT project state — it retires
    in slice 3 with the `repo_root`-arg removal, exactly like dispatch.py:628/750. Do NOT thread
    the project into it.
  - The texture-verb `lock_dir` (dispatch.py:578) → `<root>/.uedcli/locks/` — but the derivation
    must move INSIDE the lazy `project()` path (today it computes eagerly at the top of
    `_dispatch_texture`; deriving it from the project there would break the tested guarantee that
    read verbs with an explicit `--catalog-dir` resolve no project —
    `test_dispatch.py::…read_verb_with_explicit_catalog_dir_needs_no_project`). Only `sync`
    consumes it (`tc.sync_package`). While there, delete `texture_catalog.py:392`'s
    `catalog_dir.parent / ".uedcli" / "locks"` fallback (make `lock_dir` required) — it is only
    coincidentally right under the new layout.
- Retire `repo_paths.state_root()` (nothing imports it after this slice).
- **LUM migration remainder:** delete the old `<repo>/.uedcli/` (throwaway) and drop the
  `.uedcli/` line from the repo-root `.gitignore` (self-ignore covers the recreated dir).
- Tests: `test_editor.py`, `test_editor_ini.py` (monkeypatches `editor.state_root` at :33,52),
  `test_qualify.py` (monkeypatches `qualifymod.host_repo_root` :490 / `repo_paths.state_root`
  :504 — both seams become the threaded parameter), `test_apply.py`/`test_materialize_verb.py`,
  texture lock tests; assert locks/staging land under `<root>/.uedcli/`.
- `architecture.md`: the editor/materialize/texture-lock path mentions this slice changes.

**Acceptance mapped:** §10.3 fully (all state-dir creators write the self-ignore).

## Slice 3 — package-relative tool assets; cwd-relative CLI paths; delete `repo_paths.py`

- **New `tool_assets.py`:** `tool_root() = Path(__file__).resolve().parent.parent` (→
  `Tools/uedcli/`), plus named accessors `uned_dir() = tool_root() / "uned"` (compose dir +
  UED22) and **`umodel_dir() = tool_root().parent / "umodel_win32"`** — umodel is a *sibling* of
  the tool dir (`Tools/umodel_win32`), i.e. it escapes the package-relative anchor; note that
  explicitly for the packaging item to inherit.
  Consumers: `editor._compose_dir` (editor.py:79), `packages.editor_search_dirs` +
  `_remap_to_container` (packages.py:40, 229 — their `repo_root=None → host_repo_root()` defaults
  and the `repo_root` args die), `stub.py` (stub.py:245–422: umodel path, `stub_cache_root`
  passthroughs, `ephemeral_build_container`'s `repo_root` arg), `dispatch.py:628/750` (the
  build-container call sites stop passing `host_repo_root()`), and `qualify.py:323` (deferred
  here from slice 2).
- **cwd-relative CLI paths:** `dispatch.py:269` (relative `--out` joins cwd, not
  `host_repo_root()`); delete `to_host_path` and its callers' indirection (`apply.py:38–43`, the
  materialize target at apply.py:185 AND the overwrite-guard at apply.py:216–220,
  `qualify.py:322`) — a relative path is `os.path.abspath`'d at the CLI boundary, the `/repo/`
  legacy remap goes.
- **Retire the env overrides** `UEDCLI_REPO_ROOT` / `UEDCLI_PREFAB_DIR` / `UEDCLI_TEXTURE_CATALOG`
  (grep-clean); the conftest fixture drops its `UEDCLI_REPO_ROOT` leg (slice 1 note).
  `install_system_root`/`install_content_dirs` move into `tests/conftest.py` — but they are NOT
  integration-only: `test_uprops.py:30` calls `install_system_root` at **module import** in the
  offline suite (self-skip via `_HAVE_INSTALL`) and `test_dxpkg.py:126–150` self-skips likewise.
  The conftest helper therefore keeps a no-env fallback (walk from the test file's location, as
  today) with `UEDCLI_TEST_INSTALL` as override, and the module-level call in `test_uprops.py`
  becomes lazy so collection never fails.
- **Delete `repo_paths.py`** — `stub_cache_root`/`texture_images_root` fold into
  `config`/`tool_assets` (they are already `user_cache_home`-based; drop the vestigial `start`
  arg).
- While touching `preview_game.py`: route `game-preview.lock` (preview_game.py:379) through
  `config._user_home()` so `$UEDCLI_HOME` is honored (spec §5).
- Tests: `test_repo_paths.py` shrinks to `tool_assets` tests; `test_stub.py`,
  `test_packages.py`, `test_editor.py` drop the `UEDCLI_REPO_ROOT` seam; `test_dxpkg.py`,
  `test_uprops.py`, `test_texture_integration.py` re-point their `repo_paths` imports at the
  conftest helper; new regression: relative `--out` from a non-root cwd (spec §10.8);
  editor-driving verb finds compose/UED22 from any cwd (§10.4 — offline-checkable by asserting
  the resolved paths, no container needed).
- `architecture.md`: module map (`repo_paths.py` out, `tool_assets.py` in), env-var mentions.

**Acceptance mapped:** §10.4, .8.

## Slice 4 — residual docs sweep + board close-out

(The load-bearing `architecture.md` sections update per-slice above; `direction.md` + the
inbox/to-spec/to-plan board edits landed with the decision commit `98f5f2b24`. This slice is the
verification sweep.)

- `architecture.md`: grep-sweep for any remaining `<project>/uedcli/`, `config.toml`-as-project,
  `repo_paths`, or retired-env-var mention the per-slice updates missed; Premise/Terminology
  read-through.
- `unrealed/*.md`: no changes expected (engine facts, not layout) — verify by grep.
- Tool `CLAUDE.md` / `docs/README.md`: any `uedcli/config.toml` mention.
- Board: remove the item from `board/to-build/`; `board/done/` gets the short tail entry. The spec+plan
  files stay until a later cleanup (ephemeral).
- Run the full offline suite one last time; then the live check: `level materialize` +
  `level preview --game` against migrated LUM (spec §10.6).

## Explicitly out of scope (per spec §9)

Per-user config/cache, mount mechanics, name-based `--project`, `project init`, texture-cache
keying, pipx/Nuitka asset shipping (the global-CLI re-spec owns how `tool_assets` generalizes).

## Risks

- **Flag-day coordination** (slice 1): other live sessions on this repo must pull before their
  next project-resolving verb. Mitigated by the explicit old-layout error + inbox note.
- **Missed `project_dir` consumer:** grep for `project_dir` and `\.root\b` after slice 1; the
  field collapse makes any straggler a loud `AttributeError` in tests, not silent misbehavior.
- **Threading breadth** (slice 2): `editor.py` params fan out to stash-CSG/preview/materialize
  call sites; the compiler-less risk is a missed kwarg — covered by the offline driver tests that
  exercise each verb's dispatch path.
- **`tool_root()` under a future frozen binary** (`__file__` inside a Nuitka onefile): known,
  accepted, and owned by the packaging item (spec §6a).
