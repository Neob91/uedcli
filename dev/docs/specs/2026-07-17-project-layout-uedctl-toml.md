# Spec: project layout reorg — a free `uedctl.toml` at the repo root

*2026-07-17. Ephemeral (see docs rules); the durable record is `decisions.md` 2026-07-17 20:58 UTC.
Origin: board `inbox.md` "Reorganize the project layout" (Andrzej, 2026-07-13); folds in the
`to-spec.md` "Relocate locks + tmp from `<repo>/.uedctl/` to the project dir" item. Cold-reviewed
2026-07-17 (two reviewers); all findings folded in, the two design-level ones resolved by Andrzej
(decision entry §6/§7).*

## 1. What this changes, in one paragraph

Today a **project** is a subdirectory (conventionally `uedctl/`) holding a `config.toml`, found by
scanning each ancestor's *child dirs* for a project-schema config; the **project root** is that
dir's *parent*, and everything uedctl manages (`maps/`, `texture-catalog/`, `prefabs/`, gitignored
`tmp/`) nests inside the project dir. After this change a project is simply **a repo with a
free-standing `uedctl.toml` at its root** (à la `pyproject.toml`): the dir containing `uedctl.toml`
IS the project root, the file declares (as relative paths, with conventional defaults) where each
managed dir lives — so uedctl can point at a repo's *existing* `Maps/`/`Prefabs/` instead of a
parallel tree — and all machine-local throwaway state moves into one in-repo, gitignored,
**self-ignoring** `.uedctl/` beside it. The per-user `~/.uedctl/` is untouched. The legacy
`repo_paths.py` repo-root machinery (CLAUDE.md-marker walk-up, `state_root`, repo-root
`Prefabs/`/`texture-catalog/` fallbacks and their env overrides) retires with it; the tool's OWN
install assets (compose dir, UED22, umodel) re-anchor **package-relative** (§6a).

## 2. Glossary (for a cold reader)

- **project root** — the directory containing `uedctl.toml`. It is the project's identity (a path;
  there is no project id — decisions.md 2026-07-05 14:58) and the anchor every relative path in
  the file resolves against. (Containers do NOT mount the root wholesale — mount mechanics are
  unchanged: the composed search *dirs* are bind-mounted individually, `/resources/<n>`.)
- **managed dirs** — the dirs uedctl reads/writes for a project: the **maps dir** (T3D trunks, one
  `<level>/` per level), the **prefabs dir** (durable prefab library), the **texture-catalog dir**
  (tracked classification manifests).
- **state dir** — `<root>/.uedctl/`: machine-local, never-tracked scratch (stash, locks, staging,
  delivered preview maps, the selected-level pointer). Derivable/throwaway; safe to delete.
- **per-user home** — `~/.uedctl/` (or `$UEDCTL_HOME`): the `[games.*]` config (`config.toml`) and
  the cross-project derivable `cache/{textures,stubs}`. **Unchanged by this spec.**
- **tool-install assets** — files that belong to the uedctl *installation*, not to any project:
  the docker-compose dir + UED22 substrate (`Tools/uedctl/uned/`), `Tools/umodel_win32`. See §6a.

## 3. `uedctl.toml` — schema

```toml
# minimal
game = "deusex"

# everything
game = "deusex"                      # required: selects [games.deusex] in ~/.uedctl/config.toml
paths = "Textures:System"            # optional overlay dirs, colon-separated, relative to root
maps = "uedctl/maps"                 # optional, default "maps"
prefabs = "Prefabs"                  # optional, default "prefabs"
catalog = "texture-catalog"          # optional, default "texture-catalog"
```

- **`game`** (required, string) — names a `[games.<name>]` block in the per-user config. No
  default, no sole-game fallback (decisions.md 2026-07-01 04:36 stands).
- **`paths`** (optional, string) — colon-separated overlay *directories*, each relative to the
  project root (absolute allowed), same semantics as today (bare dirs, not globs; project shadows
  base; decisions.md 2026-07-14 03:30). Unchanged except for what "root" means.
- **`maps` / `prefabs` / `catalog`** (optional, string) — the managed dirs, **relative to the
  project root** (absolute allowed). Omitted ⇒ the root-relative defaults `maps/`, `prefabs/`,
  `texture-catalog/` (decision §2: defaults over required keys; lowercase conventional names, not
  one repo's capitalization).
- **Dropped keys:** `id`, `name` (the registry they served is dead — 2026-07-05 14:58 §4). An
  `uedctl.toml` containing them → the standard unknown-key `ConfigError`.
- **Schema guard kept:** a `[games.*]` table inside `uedctl.toml` (or a `game` key inside
  `~/.uedctl/config.toml`) is a named `ConfigError` — the two files keep mutually-exclusive
  schemas even though the filename now disambiguates discovery.

## 4. Project discovery

Precedence (highest wins, no silent default — unchanged shape, new targets):

1. **`--project PATH`** — a path to the project **root dir** or to the **`uedctl.toml` file
   itself**. (Bare *names* stay an error naming the registry's absence, as today.)
2. **`UEDCTL_PROJECT`** — same handling.
3. **Walk-up:** from cwd toward the filesystem root, the **first ancestor directory containing an
   `uedctl.toml` file** is the project root. Nearest wins (nested projects shadow outer ones,
   `.git`-style). No child-dir scanning, no schema-sniffing during discovery — the distinctive
   filename replaces both. The 2026-07-01 07:45 "two matching child dirs → ambiguity error" case
   disappears (an ancestor has at most one `uedctl.toml`).
4. None found → `None`; verbs that need a project keep their clean exit-2 `_ProjectError`, whose
   generic message now names `uedctl.toml` ("no uedctl.toml found here or above …").

`~/.uedctl/` can never be mistaken for a project: its config is named `config.toml`, and the
schema guard rejects a project-shaped file there anyway. A **malformed or unreadable**
`uedctl.toml` found by walk-up is a **hard `ConfigError`** (both cases — a permission-denied
marker is NOT silently climbed past; it *is* the project marker, and binding a nested repo to an
outer project would be worse than erroring). Accepted edge: an old-layout project nested *inside*
a new-layout outer repo binds silently to the outer project (the old-layout hint of §8 fires only
when walk-up finds nothing) — tolerable, since exactly one migrated project exists.

## 5. The `.uedctl/` state dir

All machine-local project state converges on `<root>/.uedctl/`:

| Entry | Holds | Today |
|---|---|---|
| `.uedctl/stash/<id>/` | stash register entries | `<project>/tmp/stash/` |
| `.uedctl/preview/` | hash-named delivered maps for `--game` preview | `<project>/tmp/preview/` |
| `.uedctl/locks/` | editor/target `flock`s *(texture flocks moved post-build to the catalog-adjacent `<catalog>/.locks/` — decisions.md 2026-07-18 07:53)* | `<repo>/.uedctl/locks/` (repo_paths) |
| `.uedctl/tmp/` | materialize/qualify staging, override inis, docker-cp temps, `keep_build` rejects | `<repo>/.uedctl/tmp/` (repo_paths) |
| `.uedctl/current-level` | the machine-local selected-level pointer (`level select`) | `<project>/tmp/current-level` (level_select.py) |

- **Self-ignoring:** whenever uedctl creates `.uedctl/`, it also writes `.uedctl/.gitignore`
  containing `*` (decision §3 — the cargo/direnv pattern). No repo-`.gitignore` edit is needed and
  the dir can never be committed by accident. Creation-detection rule: the ignore file is written
  **iff the dir was absent at the start of that call** (`mkdir` catching `FileExistsError`, not a
  blind `exist_ok=True`) — so an existing dir is left alone (a user who deliberately deleted the
  file isn't fought), and a torn create (dir made, ignore write lost) is the accepted worst case.
  `level_select`'s own `tmp/.gitignore` writer (the `*` + `!.gitignore` variant) retires — the
  dir-level ignore covers it; bare `*` is the canonical content.
- The old `repo_paths.state_root()` was *already* `<repo>/.uedctl/`, so for a root-level project
  the locks/tmp paths are byte-identical — what changes is **derivation** (from `uedctl.toml`
  discovery, not the CLAUDE.md-marker repo walk) and that stash/preview/current-level join them
  there.
- Atomicity note: materialize staging stays under `.uedctl/tmp/` precisely so `os.replace` onto an
  in-repo `--out` stays same-filesystem (the existing EXDEV fallback covers the rest).
- The per-user `~/.uedctl/game-preview.lock` (warm game-preview container serialization) stays
  per-user — the warm container is per-*user*, not per-project. While touching it: route the path
  through `config._user_home()` so it honors `$UEDCTL_HOME` like everything else per-user.
- Degenerate edge, accepted as harmless: a project rooted at `$HOME` makes the state dir literally
  `~/.uedctl/` — the state subdirs and a `*` `.gitignore` land beside the games `config.toml` and
  `cache/`. Nothing collides (distinct names) and nothing breaks; not worth a guard.

## 6. What retires (`repo_paths.py` and friends)

| Retiree | Replacement |
|---|---|
| `host_repo_root()` (CLAUDE.md-marker walk-up) + `UEDCTL_REPO_ROOT` | project root from `uedctl.toml` discovery for PROJECT state; the package-relative anchor (§6a) for TOOL assets |
| `state_root()` | `<root>/.uedctl/` via the resolved project |
| `prefab_library_root()` + `UEDCTL_PREFAB_DIR` | `uedctl.toml` `prefabs` key (default `prefabs/`) |
| `texture_catalog_root()` + `UEDCTL_TEXTURE_CATALOG` | `uedctl.toml` `catalog` key (default `texture-catalog/`) |
| `to_host_path()` legacy `/repo/...` + repo-relative resolution | relative CLI paths (`--out`, `--map`, `--from-t3d`, …) resolve against **cwd**, standard CLI semantics; the `/repo/` container-root remap is dead code and goes |

- **Behavior change, stated explicitly:** prefab and texture-catalog verbs today fall back to the
  repo-root walk (+ env overrides) and so can run outside any project; after this change they
  need a resolved `Project` — no project ⇒ the clean exit-2 `_ProjectError`. The per-invocation
  **`--prefab-dir` / `--catalog-dir` flags survive** as explicit overrides (an override given ⇒ no
  project needed for that verb, as today).
- **Test seam for the retired env vars:** tests that used `UEDCTL_REPO_ROOT`/`UEDCTL_PREFAB_DIR`/
  `UEDCTL_TEXTURE_CATALOG` for isolation switch to a tmp-dir project fixture (write a minimal
  `uedctl.toml`, point `UEDCTL_PROJECT`/`--project` at it) — the same seam production uses.
- Survivors: `stub_cache_root()`/`texture_images_root()` (already per-user `~/.uedctl/cache/`,
  `config.user_cache_home`) — they merely stop accepting the vestigial `start` arg;
  `install_system_root()`/`install_content_dirs()` (integration-test pointers into the gitignored
  baked install) move behind a test-only env (`UEDCTL_TEST_INSTALL`, resolved in conftest), out of
  the production module. If nothing production-side remains, `repo_paths.py` is deleted.
- Threading (the folded to-spec item): the resolved `Project` reaches `editor.py` / `apply.py` /
  `qualify.py` / `level_select.py` / the texture verbs instead of each calling
  `state_root()`/`host_repo_root()` themselves — the implementation plan slices this; the spec's
  requirement is only *no CLAUDE.md-marker or env-repo-root resolution remains*.

### 6a. Tool-install assets go package-relative (decision entry §6)

`host_repo_root()` was doing double duty: besides project state it anchored the **tool's own
assets** — `editor._compose_dir()` (`Tools/uedctl/uned/`, the docker-compose dir + pre-bake inis),
the UED22 substrate path (`packages.editor_search_dirs`, `packages._remap_to_container`), and
`Tools/umodel_win32` (`stub.py`). These are installation state, not project state — pointing them
at the project root only works when the project happens to be the dx_lum repo. They re-anchor
**package-relative**: resolved from the installed `uedctl` package's own location
(`Path(__file__)` → the source tree's `Tools/uedctl/`), via one new helper (e.g.
`tool_assets.tool_root()`). Zero config for the dev checkout; how these assets ship under
pipx/Nuitka is the (stale, to-be-respecced) global-CLI packaging item's problem, and is explicitly
out of scope here.

## 7. `config.py` + `dispatch.py` deltas

- `Project`: `project_dir` and `root` collapse into one `root` field; `id`/`name` fields go;
  `catalog`/`prefabs`/`maps` resolve against `root` (defaults per §3).
- `load_project(path)` accepts the root dir or the `uedctl.toml` path; `_project_toml_path` looks
  for `uedctl.toml` (not `config.toml`).
- `walk_up_project_dir` → `walk_up_root`: ancestor-file scan (§4), no child-dir listing, no
  ambiguity branch. `_is_project_config_file`'s schema-sniff is no longer used for discovery but
  the schema classification stays for load-time validation of both files. The stale module
  docstring (it still claims "the legacy hardcoded fallback stays in packages.py") is rewritten.
- `resolve_project` signature/precedence unchanged.
- Composition (`composed_search_dirs`/`composed_search_files`, `select_substrate`, `resolve_dirs`)
  unchanged except `paths` anchoring to the new `root`.
- `dispatch._project_show` prints the new shape: `root` (replacing the `project:` project-dir
  line), `game`, all **three** managed dirs (`maps`, `prefabs`, `catalog`), then the composed
  search path with provenance as today.
- `dispatch._resolve_project`'s generic error message names `uedctl.toml` (§4.4).

## 8. Migration (hard cutover, LUM in the same change)

- **No dual support** (decision §4). If walk-up finds no `uedctl.toml` but an old-layout
  `<child>/config.toml` project *would* have matched, the `_ProjectError` message says so
  explicitly: `found old-layout project dir <path>/uedctl/ — this layout is retired; move its
  config.toml to <path>/uedctl.toml (see docs) and delete its tmp/`. (Detection: the same cheap
  child-scan the old walk-up did, run only on the failure path to improve the error — not a
  supported layout.)
- **LUM migrates in the same change** (decision entry §7 — zero-move option):
  - `uedctl/config.toml` → `<repo>/uedctl.toml`, **dropping the retired `name` key**, gaining
    `maps = "uedctl/maps"` (the trunks stay in place; the old `uedctl/` dir lives on as a plain
    content dir) and `prefabs = "Prefabs"` (the existing library dir). **No `catalog` key** — LUM
    has no catalog dir yet, and the new default (`<root>/texture-catalog/`) equals the legacy
    `texture_catalog_root()` default location.
  - `uedctl/tmp/` is throwaway — deleted, not moved (stash is scratch by definition), along with
    `uedctl/.gitignore` (whose only job was ignoring `tmp/`).
  - The pre-existing `<repo>/.uedctl/` (old `state_root()` output) is deleted — throwaway by
    definition — so its next creation writes the self-ignore file; the `.uedctl/` line in the
    repo-root `.gitignore` comes out (self-ignore covers it).
- **Docs updated in the same change:** `architecture.md` (Terminology, Premise, stash/prefab/
  texture/level-select path mentions, the retired env vars), `direction.md` ("Projects,
  substrates, and the global CLI" — including its stale "the editor container mounts [the
  project root]" sentence — and the trunk-path mentions), and every `<project>/uedctl/…` path
  mention elsewhere.
- **Board updated in the same change:** the origin entry leaves `inbox.md`; the folded "Relocate
  locks + tmp" item leaves `to-spec.md`; `to-plan.md`'s global-CLI item drops its now-false
  "`project init` in particular must scaffold the NEW layout" sentence (decision §5: no scaffold
  verb) in favor of a pointer to this spec.

## 9. Out of scope

- The `[games.*]` per-user config, cache layout, container mount mechanics, composition/shadowing
  semantics — all unchanged.
- Name-based `--project` / any registry (still dead).
- A `project init` scaffold verb (decision §5 — hand-written file; docs carry the template).
- Content-addressed texture-cache keying (separate to-spec item).
- How tool-install assets ship under pipx/Nuitka (§6a — the global-CLI packaging item).

## 10. Acceptance criteria

1. A repo with only `game = "deusex"` in `<root>/uedctl.toml` resolves: root = that dir;
   maps/prefabs/catalog default to `<root>/{maps,prefabs,texture-catalog}`; `project show` prints
   root, game, and all three.
2. A repo pointing `prefabs = "Prefabs"` at an existing dir uses it in place (no parallel tree).
3. First state-dir use (`level select`, stash write, materialize, `--game` preview) creates
   `.uedctl/` **with** a `*` `.gitignore`; `git status` in a fresh repo shows only `uedctl.toml`
   and tracked managed dirs.
4. No code path resolves a CLAUDE.md-marker repo root or reads
   `UEDCTL_REPO_ROOT`/`UEDCTL_PREFAB_DIR`/`UEDCTL_TEXTURE_CATALOG`; editor-driving verbs still
   find the compose dir/UED22/umodel via the package-relative anchor from any cwd.
5. Old-layout LUM checkout (pre-migration) gets the explicit old-layout error, exit 2.
6. Migrated LUM: full offline suite green; `level materialize`/`preview --game` work against the
   migrated tree.
7. Nested-project case: cwd inside an inner repo with its own `uedctl.toml` binds to the inner
   one.
8. A relative `--out` resolves against cwd (verified from a non-root cwd).
