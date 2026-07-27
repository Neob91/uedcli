# Plan: uedcli global CLI over multiple projects

Implements `spec.md`. **Ephemeral** — folds into
`architecture.md`/`decisions.md` on landing.

## Strategy: additive, behind a legacy fallback; safe slices first

The spec mandates a legacy fallback (§9.1): until a `uedcli.toml` exists, the current
repo-bound resolution stays. Every slice below is built **additively** so that, with no
`uedcli.toml`/`config.toml` present, behavior is **byte-identical to today** and the existing test
suite stays green. The gated slices (migration, container overlay) are explicitly deferred.

## Resolutions from plan review (round 1) — READ FIRST

Two cold reviews surfaced findings that **shrink the safe-autonomous scope**. Folded:

- **CRITICAL — Slice C is NOT trivially additive (file↔dir impedance).** Today
  `substrate_search_dirs` returns **directories** that `_present`/`_first_match`/`enumerate` feed to
  `os.listdir()`. The spec's `composed_search_files` returns **files** (globs). You cannot swap one
  for the other. Resolution: the new path resolution yields a **resolved file list**, and the
  consumers must be refactored to operate on that file list (not re-list dirs) — a real change, not
  an optional arg. **⇒ Slice C is reclassified GATED/SUPERVISED** (needs the consumer refactor +
  golden snapshot). Not built in this pass.
- **CRITICAL — tier-3 (session's recorded project id) needs a session-schema change** that lives in
  the deferred Slice F (sessions don't record a `project_id` today). **⇒ `resolve_project` returns
  `None` at tier 3 in this pass** (documented); `--session` + project-scoped resolution is untested
  until F. Flagged.
- **Env precedence (defined):** `--project` > `UEDCLI_PROJECT` (NEW env, distinct from
  `UEDCLI_SESSION`) > tier-3 (deferred) > walk-up > None. The existing `UEDCLI_REPO_ROOT` stays the
  legacy repo-root locator (used only on the legacy path). `UEDCLI_TEXTURE_CATALOG`/`PREFAB_DIR`
  remain honored as overrides on the legacy path; under a project they're superseded by the
  configured `catalog`/prefab paths. No env knob is removed in this pass.
- **Dependency direction (no circular import):** `config.py` is **lower-level** and does NOT import
  `packages.py`. The legacy fallback list stays in `packages.py`; when no user config/project is in
  scope, the *caller* (dispatch/packages) uses the legacy `substrate_search_dirs` directly — not
  `config.py`. `config.py` only loads/validates TOML + resolves globs + resolves the project.
- **Slice B `resolve_project` returns `None` cleanly when nothing resolves** — the caller decides
  error-vs-legacy. B builds as a **standalone, fully-unit-tested module, NOT yet wired** into any
  verb. Wiring is Slice C/E (supervised).
- **DECODE_SCHEMA testability:** `gc(decode_schema=…)` takes it as a parameter (not only the module
  constant) so schema-bump GC is unit-testable without monkey-patching.
- **Catalog relocation (Slice D) data-loss risk:** the committed `texture-catalog/` must not become
  a stale second copy. ⇒ the catalog-relocation **wiring** is deferred; only the pure store module
  is built now. Legacy `repo_paths.texture_catalog_root()` stays the path until a supervised pass.
- **Slice A:** actually run `pip install -e` in a throwaway venv to verify the entry point — don't
  assume.
- **Doc-upkeep:** landed pieces → `architecture.md`; this is also a `direction.md`-level shift
  (global-CLI) → note it there when the core lands; mark the `board/to-plan/` entry when done.

**Revised autonomous scope for THIS pass:** build **A (packaging)** + **B (`config.py` standalone +
tests)** only — both are genuinely safe and unwired. Build **D's pure store module** if budget
allows. **C, E, F, G, H deferred/supervised** (C reclassified gated by the impedance fix). The
existing offline suite stays green (nothing is wired, so it can't regress).

---

Slices, in dependency order:

| # | Slice | Gated? | Risk | Build now? |
|---|---|---|---|---|
| A | **Packaging / pipx** (`pyproject.toml`, entry point) | no | low | **YES** |
| B | **Config + path resolution** (`config.py`: TOML load, colon-glob `paths`, project resolution) | no | low (pure) | **YES** |
| C | **Wire B into `packages.py`** behind the legacy fallback | no | medium | **YES (careful)** |
| D | **Content-addressed texture store** (`texture_store.py` + catalog at configured path) | no | medium | partial |
| E | **`project`/`config` CLI verbs** + `--project`/`--config`/`--explain-paths` | no | low | **YES** |
| F | **Session store relocation** to `~/.uedcli/projects/<id>/` | no | **high** (touches store/apply/locks) | **NO — supervised** |
| G | **`uedcli migrate`** | **gated #1** | high (destructive) | **NO** |
| H | **Container overlay mounts** for apply/preview | **gated #2** | high | **NO** |

This plan builds **A, B, E, and the pure core of D** autonomously (each with tests), starts **C**
behind the fallback, and **stops before F/G/H** (high-blast-radius / gated) — flagged for a
supervised pass.

---

## Slice A — packaging / pipx  (build now)

**Goal:** `pipx install` (or `pip install -e`) puts `uedcli` on `$PATH` with Pillow bundled; the
`No module named PIL` host-interpreter bug disappears.

**Steps:**
1. Add `Tools/uedcli/pyproject.toml`:
   - `[project]` name `uedcli`, version, `requires-python = ">=3.12"`, `dependencies = ["Pillow>=11"]`.
   - `[project.scripts] uedcli = "uedcli.cli:main"` (entry point → existing `cli.main`).
   - `[tool.setuptools] packages = ["uedcli"]` (or `find`), exclude `tests`.
2. Confirm `uedcli/__main__.py` + `cli.main()` need no change (entry point reuses `main`).
3. README/architecture note: install via `pipx install ./Tools/uedcli` (editable for dev:
   `pip install -e`).

**Tests/verify:** `python -m build` (or `pip install -e .` in a throwaway venv) succeeds; `uedcli
--help` runs; `import PIL` resolves from the installed env. (No unit test; a smoke check.)

**Risk:** none to existing behavior — purely adds packaging metadata.

---

## Slice B — `config.py`: TOML load + colon-glob path resolution + project resolution  (build now)

**Goal:** a pure, fully-unit-tested module that loads the two TOML files, resolves the composed
package path (§3.4), and resolves the current project (§4) — with **no I/O side effects beyond
reading the configs + globbing**, and a **legacy fallback** when no config is present.

**New module `uedcli/config.py`:**
- `@dataclass(frozen=True) UedcliConfig` — parsed `~/.uedcli/config.toml`: `substrates: dict[str,
  Substrate]`, `defaults`. `Substrate{paths, catalog, image}`.
- `@dataclass(frozen=True) Project` — parsed `<project>/uedcli.toml`: `root, id, name, substrate,
  paths, catalog`.
- `load_user_config(path=None) -> UedcliConfig | None` — `tomllib`; `None` if absent. `--config`
  override. **Validation:** unknown keys → error naming key+file; missing required → error; a
  relative glob in `config.toml` → error (must be absolute, §3.1).
- `load_project(dir_or_toml) -> Project` — read `uedcli.toml`; validate; relative `paths`/`catalog`
  resolve against the project root.
- `expand_paths(paths_str, base_dir) -> list[str]` — split on `:`, glob each (non-recursive,
  sorted case-folded), resolve relative against `base_dir`, **dedup by case-folded package stem
  keeping first**. Returns absolute file paths in composed order.
- `composed_search_files(project, user_cfg) -> list[(path, provenance)]` — project globs first,
  then the project's substrate base globs; dedup keep-first (→ provenance per §3.4).
- `resolve_project(*, project_flag, env, session_project_id, cwd) -> Project | None` — the §4
  precedence (1 flag → 2 env → 3 session-recorded id → 4 walk-up `uedcli.toml` → else None).
  **No silent default**; the caller decides whether `None` is an error (most verbs) or fine
  (sessionless texture browse = base-only, but base needs a substrate ⇒ still needs config — see
  open Q below).
- `is_pkg_file(name)` / `pkg_stem(name)` — reuse `packages._PKG_EXTS`.

**Tests `tests/test_config.py`** (pure, tmp dirs + fixture tomls):
- glob expansion: order preserved across `:`; within-glob sorted; case-insensitive dedup keep-first
  (`A/Foo.utx:B/foo.utx` → one, from A); empty glob silent; `**` rejected.
- relative-in-config.toml → error; unknown key → error naming it; missing required → error.
- `composed_search_files`: project shadows base on same stem; provenance correct; no project → base
  only.
- `resolve_project` precedence: each tier in isolation + the fallthrough to walk-up + None.
- uuid `id` round-trips; `name` is display-only.

**Risk:** none — new module, not yet wired into any verb.

**Open Q for the build (flag, don't block):** sessionless `texture list` with *no* config at all —
spec says "base only", but "base" needs a `config.toml` substrate. With neither config nor project,
that's the legacy hardcoded path. Decision: when no user config exists, `composed_search_files`
falls back to **legacy `packages.substrate_search_dirs(repo_root)`** so today's behavior is intact.

---

## Slice C — wire `config.py` into `packages.py` behind the legacy fallback  (build now, careful)

**Goal:** package resolution uses the composed path **when a project/config is in scope**, else the
exact legacy list.

**Steps:**
1. `packages.substrate_search_dirs(repo_root, *, project=None, user_cfg=None)` gains optional args.
   When both are None (or no user config) → **return the legacy hardcoded list unchanged**. When
   present → derive **directories** from `composed_search_files` (the dir set, preserving order +
   shadowing) so the existing dir-listing consumers (`_present`/`_first_match`/`enumerate`) keep
   working with minimal change.
2. Thread an optional resolved `(project, user_cfg)` from `dispatch` into the call sites that build
   manifests (closure/missing/paths/enumerate). Default None everywhere → legacy.
3. Do **not** touch `_remap_to_container` yet (that's the container/overlay slice H).

**Tests:** extend `tests/test_packages*.py`: with no project → identical results to today (snapshot);
with a fixture project overlay → project package shadows a same-named base one in `_first_match`,
and `enumerate` yields the deduped union with provenance.

**Risk:** medium — this is the seam everything routes through. Mitigated by the None-default ⇒
legacy invariant + a snapshot test proving no-config behavior is unchanged.

---

## Slice D — content-addressed texture store  (build the pure core now; wire later)

**Goal:** the store layout of §6 + the catalog-at-configured-path of §6.2, with GC + schema cache
key, as a **pure module** first; wiring `texture sync` to it is a follow-on.

**New `uedcli/texture_store.py`:**
- `store_root()` = `~/.uedcli/textures/` (overridable). `package_dir(pkg_hash, schema)`,
  `data_path(pixel_hash)`.
- `read_index(pkg_hash, schema)` / `write_index(...)` — `index.json` per §6 schema (atomic temp+
  `os.replace`, per-`<pkg-hash>.<schema>` flock).
- `put_image(pixel_hash, png_bytes)` — content-addressed write if absent (dedup).
- `live_pixel_hashes()` — union over all present indexes. `gc(dry_run) -> removed` — delete
  unreferenced `data/*.png` + superseded `packages/*` dirs (store-wide lock).
- `DECODE_SCHEMA = 1` constant (bump on any decode-pipeline change).

**Tests `tests/test_texture_store.py`:** index round-trip; dedup (two names same pixels → one png);
GC removes only orphans, keeps live; schema bump makes old dir GC-eligible; concurrent-write safety
(same pixel_hash → identical bytes).

**Catalog at configured path:** `texture_catalog` manifest read/write moves to the path from
`project.catalog` / `substrate.catalog` (default `<project>/texture-catalog/` and the substrate
default). Keep the manifest schema; only the *location* + the pixel-hash join changes. **This is a
behavior change to where the catalog reads/writes — gate it on a project being in scope; legacy
path (`repo_paths.texture_catalog_root()`) when none.**

**Wiring `texture sync` to the store: FLAG as a follow-on** (it changes the live sync I/O shape and
needs the container/decode path; do it supervised with the integration container).

**Risk:** medium; the pure store module is safe, the catalog-relocation + sync-rewire is the risky
part → deferred/flagged.

---

## Slice E — `project` / `config` CLI verbs + global flags  (build now)

**Goal:** the surface from §4.1.
- `project init [--name] [--substrate]` (mint `uedcli.toml` + uuid), `project ls/show/rm`.
- `config get/set` (edit `~/.uedcli/config.toml`).
- Global `--project`, `--config`, `--explain-paths` on the top parser; `dispatch` resolves the
  project via `config.resolve_project` and passes it down (default None → legacy).
- `--explain-paths` prints `composed_search_files` with provenance + shadow notes.

**Tests:** `project init` writes a valid parseable toml with a uuid; `ls` reflects registered
projects; `--explain-paths` output is deterministic. Argparse wiring tests.

**Risk:** low — new verbs; the global flags default to None (legacy) so existing invocations are
unchanged.

---

## Slices F / G / H — DEFERRED (supervised / gated)

- **F (session relocation):** `repo_paths.session_store_root` → `~/.uedcli/projects/<id>/store`.
  Touches `session.py`, `apply.py` (commit still writes the artifact into the content tree — spec
  §5), every lock path, `session verify`. High blast radius across the store-centric core →
  **supervised**, with the full integration suite. Flagged.
- **G (`uedcli migrate`):** destructive move of in-repo `.uedcli/` → `~/.uedcli/`. **Gated on
  Andrzej's carry-vs-drop decision.** Flagged.
- **H (container overlay mounts):** `_remap_to_container` + compose/`docker run` to mount both
  layers with project precedence. **Gated on the mount-strategy decision.** Flagged.

---

## Verification per slice
After each built slice: `cd Tools/uedcli && .venv-uedcli/bin/python -m pytest uedcli -q` (offline
suite stays green) + the new slice's tests. Commit per slice. Update `architecture.md` for the
*landed* pieces; leave gated pieces in this plan + `flagged.md`.

## Done-definition for this autonomous pass
A, B, E built + tested; C wired behind the fallback + snapshot-proven no-op when no config; D's
pure store module built + tested (sync-rewire flagged); F/G/H flagged for supervised/gated work.
The existing offline test suite stays green throughout.
