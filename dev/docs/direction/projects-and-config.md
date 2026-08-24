# Projects and config — one global CLI, many projects

## What we want

### One install, many games

uedcli is a **globally-installed CLI** (`pipx install`, one binary on `$PATH`) that operates on many
independent **projects**, not a tool that lives inside one content repo.

A per-user **`~/.uedcli/config.toml`** declares each game once, as `[games.<name>].paths`: a list of
**absolute directories** holding that game's base packages. One install serves Deus Ex, Unreal, and
any other UE1 game; nothing else lives in that file.

- **No `[defaults]` block at all** — no default game, no default container, no default image. A
  project names its game explicitly or it is an error; which game's assets a project builds against
  is never inherited from an ambient default.
- **No `image` key**: there is one shared editor image ([`containers.md`](containers.md)).
- **No `container` key and no `--container` flag**: container instances are ephemeral and derived.

The user-facing key is `game` and the internal concept stays `substrate` — see
[`scope.md`](scope.md).

### A project is a repo with a `uedcli.toml` at its root

A project is identified by a **free-standing `uedcli.toml` at the repo root**, as `pyproject.toml` or
`.git` identifies a tree. The directory containing that file **is** the project root. There is no
`uedcli/` subdir, no project `id`, no registry, and no scaffold verb — the root path is the project
identity, and the `project` verb is `project show` only.

**Discovery is a walk-up, nearest wins**, `.git`-style: `--project` beats `$UEDCLI_PROJECT`, which
beats walking up from cwd to the first ancestor containing a `uedcli.toml`. Nothing found is an
error, never a silent default. A marker that exists but is not a readable regular file **stops the
climb** — climbing past it would silently bind a nested repo to an outer project.

| Key | Required | Meaning |
|------------|----------|---
| `game` | yes | which `[games.<name>]` block this project builds against |
| `paths` | no | the project's own package **overlay** dirs, resolved against the root |
| `maps` | no | where the per-level T3D trunks live — default `maps/` |
| `prefabs` | no | the prefab library — default `prefabs/` |
| `catalog` | no | the tracked asset classification — default `asset-catalog/` |

The three managed dirs are **relative paths with conventional defaults**, so uedcli can be pointed at
a repo's **existing** directories instead of forcing a parallel tree beside them. A minimal project
file is one line: `game = "deusex"`.

### State lives in the tree or in the per-user home — never in a central bucket

- **Tracked, in the content tree:** `uedcli.toml` plus the declared maps / prefabs / catalog dirs.
- **Machine-local, in ONE in-repo `.uedcli/`** beside `uedcli.toml`: stash entries, delivered
  preview maps, `flock`s, staging temps. It is **self-ignoring** — uedcli writes `.uedcli/.gitignore`
  containing `*` when it first creates the dir — so it can never be committed by accident.
- **Per-user, in `~/.uedcli/`:** the `[games.*]` `config.toml`, and `cache/{textures,stubs,schema}`.
  All content-addressed or stat-tuple-keyed, shared across projects, derivable, never committed.
- **Tool-install assets resolve package-relative** — the compose dir, the UED22 substrate, umodel
  come from the installed package's own location, never from a repo. They are the tool, not project
  state, so they need no config key and no marker walk-up.

There is no central per-project directory, so no key to mint, nothing to register, and nothing to
garbage-collect.

### Layered packages: bare dirs, project shadows base

Config `paths` are **bare directories, never globs**. uedcli owns the five package extensions
(`.u .dx .utx .uax .umx`) and applies that knowledge itself, for both jobs that need it: scanning
dirs to resolve a package file, and crafting the editor's search path. Extensions live in one place,
the tool, not smeared across every config file.

The **effective set** is the project's overlay dirs first, then the selected game's base dirs, deduped
**project-shadows-base** — the engine's own search-path shadowing — at two granularities: **by
directory** for the container mounts, and **by package stem** for the load set scanned out of those
dirs, so a project package shadows a same-named base one.

**There is no stored package manifest.** The set of packages a build can reach is derived from the
composed dirs on demand; nothing is written down to drift out of sync.

### What a build actually loads

Two different sets:

- **The whole composed search path populates `[Core.System] Paths`** via the mounts, so any *indirect*
  reference the level never names can still resolve by demand-load.
- **`level materialize` explicitly loads only the packages the level's own actors reference.** The
  preload is **O(level), not O(install)**: pointed at a real game install, a whole-search-path load
  meant hundreds of explicit loads for a level that used one, each another chance for the crash-prone
  editor to wedge silently.

Shadowing on that explicit path is decided **host-side**: uedcli resolves each package to a file and
loads it by absolute path, so the composed-paths resolver — not the editor — picks which copy wins.
The ini's `Paths` order governs only the by-name / demand-load route, and is written in the same
project-first, stubs-first order so the two agree.

**No games config is a hard error**, exit 2, naming the file to create. There is no implicit
baked-image fallback: an image-defined load set is invisible and cannot express a project's overlay.

## Rejected

**Games and the global install**

- **A per-game editor `image` key**, or a built-in default image per game.
- **A `[defaults].container` key or a `--container` override** — with one image and derived instances,
  a container name selects nothing.
- **A `[defaults].game`**, or falling back to the sole `[games.*]` when only one is declared — both
  implicitly bind the thing that must be explicit.

**Project identity and layout**

- **A `<project>/uedcli/config.toml` project dir with the root as its parent** — indirection forcing a
  parallel tree beside the user's own dirs.
- **A tracked `.uedcli/` dotdir holding the project's config** — a hidden dir for visible, hand-edited
  config.
- **Anchoring `paths` at the project dir rather than the root** — real projects keep package content
  at the tree root, so anchoring below it would force `../` in every entry.
- **A shared `config.toml` filename for both the per-user home and the project** — bought a
  schema-sniffing discovery scan; a distinctive filename beats sniffing.
- **Walk-up that only recognizes a conventionally-named dir** — a project dir named anything else
  became invisible from inside its own tree.
- **Walk-up by schema, scanning each ancestor's child dirs** — read every candidate `config.toml` up
  to the filesystem root and needed an ambiguity error.
- **Bounding the climb at `$HOME`** — breaks trees outside the home dir.
- **Central per-project state under `~/.uedcli/projects/<id>/`** — the sole reason a project needed a
  stable id, a registry and a `project init`.
- **An XDG split** — more dirs and platform machinery for no gain.
- **Requiring all `uedcli.toml` keys**, or defaulting the managed dirs to one repo's capitalized
  spelling — more typing for no safety, and baking a single project's convention into the tool.
- **Transitional dual-layout support** — two documented layouts and more code, for one existing
  project.
- **Migration tooling that carries old state forward** — the durable record is the committed trunks.
- **Reintroducing `project init`** — dead surface for a one-line file that `.uedcli/` self-creates
  beside.
- **A user-managed `.gitignore` entry for `.uedcli/`** — a documented requirement someone will miss.
- **A config key, or a repo-marker walk-up, for the tool's own install assets** — the first makes a
  required setup step before any editor-driving verb works, the second keeps a repo-marker walk alive
  for state that is not the project's.
- **Putting classification or prefabs in the derivable cache** — both are non-regenerable.

**Packages and the load set**

- **Glob-based `paths`** — pushes extension knowledge into every config file.
- **Config-driving the editor image's own substrate or the stub cache** — they are editor code.
- **A separate `schema_search_dirs`** — a second hardcoded search path that drifts from the one the
  rest of uedcli resolves against, and misses a project's own overriding classes.
- **A stored package manifest** per level, plus a `package load` verb — redundant with the dirs the
  project already declares, and one more artifact to keep in sync.
- **Explicitly loading the whole composed search path at materialize** — correct on a toy install,
  fatal on a real one.
- **Keeping the whole-set load and merely making it skip failures**, or trimming the games config to
  fewer categories — the first is still O(install), the second blames the config for a bug.
- **Deriving the load set by walking the import-table transitive closure** — needs a closure walker
  *and* fully-qualified stored refs, which T3D class refs are not.
- **A code-vs-content directory split**, **a separate mount root for code dirs**, **a bare `<dir>/*`
  `Paths` line**, **filtering discovery to "content" extensions**, and **mounting the dirs without
  editing the ini** — see [`containers.md`](containers.md).
- **Legacy handling for the glob-to-dir change** — the few existing config files were simply edited.

## Refs

[`scope.md`](scope.md) · [`containers.md`](containers.md) · `../architecture.md` "Substrate" ·
`../parallel-editors.md` · `../unrealed/quirks.md` · `../spikes/2026-07-01-paths-precedence/`
