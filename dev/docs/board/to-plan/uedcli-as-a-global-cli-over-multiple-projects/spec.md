# Spec: uedcli as a global CLI over multiple projects (config, projects, layered assets)

**Date:** 2026-06-29 · **Consolidated:** 2026-07-01 · **Status:** design (pre-implementation) ·
**Author:** design conversation with Andrzej, 2026-06-28 → 2026-07-01.

> **Reader orientation.** This spec turns uedcli from a tool that *lives inside one content repo and
> assumes that repo's layout* into a **globally-installed CLI that operates on many project
> directories**. It defines: (1) the tool / game / project / session separation; (2) the config
> files and the layered package-path scheme; (3) how the current project is chosen; (4) the per-user
> `~/.uedcli/` layout and the content-addressed texture store; (5) how the shared editor is wired.
> Terms are defined before use. This is the **consolidated** design — every *ratified* decision below
> is durably recorded in [`decisions.md`](../../../decisions.md) (cited inline); the items in **§9 are
> explicitly open/deferred, not decided**. This spec is ephemeral scratch and folds into
> `architecture.md`/`direction.md` on implementation.

---

## 1. Motivation

Today uedcli is **repo-bound by assumption**:
- `repo_paths.host_repo_root()` finds "the project" by walking up for a `CLAUDE.md` + `Tools/uedcli`
  marker — i.e. it assumes it is running *inside the dx_lum repo*.
- `packages.substrate_search_dirs(repo_root)` returns a **hardcoded list** conflating two unrelated
  things: the **substrate** (`uned/UED22`, `uned/DeusExAssets`) and the **repo's own content**
  (`System/ Textures/ Maps/ LUM/`).
- Runtime state (`.uedcli/`: sessions, locks, caches) sits at the repo root.

The goal: a tool you `pipx install` once and run against any number of independent content trees,
for any UnrealEngine-1 game. Reaching it means **separating things that are currently fused**.

## 2. Concepts (the separation)

| Concept | What it is | Lifetime / sharing | Where it lives (target) |
|---|---|---|---|
| **Tool** | the `uedcli` Python package | installed once | on `$PATH` (pipx) |
| **Game** (internally "substrate") | a UE1 game's base packages (the "OG Deus Ex" install); the editor is the single shared UED22 image | per-**game**, shared by all its projects | game asset paths declared in `~/.uedcli/config.toml` `[games.*]` |
| **Project** | a content tree whose authored work uedcli manages | per-content-tree | the tree's root; uedcli's home is a **project dir** inside it (conventionally `uedcli/`, marked by its `config.toml`) — see §3.3/§5 |
| **Session** | a unit of in-progress editing that merges into the project's committed trunk | transient; never in the content tree | `~/.uedcli/projects/<id>/` (central) — **but see §9: replacing sessions with git branches is a deferred pivot** |

**Terminology note (decisions.md 2026-06-30 21:07 UTC):** the user-facing config key is **`game`**;
the internal concept and code symbols keep the name **`substrate`** (the generic-UE1 abstraction — a
game's editor + base packages, decisions.md 2026-06-23). A substrate maps 1:1 to a game for every
game we support.

The load-bearing split: **the durable trunk (committed T3D trees / map files) is in the content
tree; sessions are uedcli's private, transient workspace** (`direction.md`).

## 3. Config files + the layered package-path scheme

### 3.1 `paths` — a colon-separated glob list

Both config files express *where packages are* with a single `paths` value — a colon-separated list
of globs, PATH-style:

```
paths = "Maps/*.dx:Textures/*.utx:System/*.u:Sounds/*.uax:Music/*.umx"
```

- Each element is a glob expanded at resolution time to a concrete set of package files.
- **Relative globs anchor on the right base dir:**
  - `~/.uedcli/config.toml` → globs **MUST be absolute** (no project root to anchor to; a relative
    glob there is a config error, named and rejected).
  - `<project-dir>/config.toml` → globs are **relative to the PROJECT ROOT** = the project dir's
    **parent** (`.git`-style, §3.3), **not** the dir holding the `config.toml`; absolute also allowed.
- Separator is `:` (POSIX hosts; Windows port out of scope). **Path values are POSIX**: a `:` inside
  a path element (e.g. a pasted `Z:\…` container path) is a **config error**, not a silent split.
- Globs use the stdlib `glob` vocabulary, **non-recursive** (`*`/`?`/`[…]`). `**` is a **named config
  error** (an explicit check — not silent literal-match-nothing); keep patterns shallow (`Maps/*.dx`),
  one element per asset dir (matches the engine's own flat `Paths=` list — a game with nested asset
  dirs needs one `paths` element per level, deliberately).

**Resolution rules (deterministic — the exact pipeline):**
1. **Expand** each glob to its matching files.
2. **Within a glob**, sort case-folded and keep-first per name (a within-glob same-name pair is
   resolved by sort, deterministically — surfaced by `--explain-paths`).
3. **Concatenate** globs left-to-right in `:` order.
4. **Across the composed list**, keep the **first** occurrence per name — this is what makes "project
   shadows base" fall out (project globs come first, §3.4).

- **Package identity is the bare name (stem), regardless of extension.** UE1's package namespace is
  **flat by name** — `OBJ LOAD Foo` binds the one package `Foo` whether it is `Foo.u` or `Foo.utx`
  (evidence: the `class-package-collision` spike; `packages._PKG_EXTS`). So `Foo.u` and `Foo.utx` are
  the SAME identity and one shadows the other; a same-stem/different-kind pair is a malformed layout
  and first-wins applies (visible in `--explain-paths`). Recognized extensions: `_PKG_EXTS`
  (`.u .dx .utx .uax .umx`).
- **Case-insensitive** (UE1 `FName`): `coretexmetal.utx` == `CoreTexMetal.utx`; compare case-folds,
  storage preserves case.
- **Empty glob is silent — but only for overlay COMPOSITION** (a project legitimately lacks
  `Sounds/`). This is NOT a hole in the no-silent-default rule: a *referenced* package that resolves
  to no file is a **named hard error at missing-check time** (§7). Composition-silence and
  reference-resolution-failure are different layers.

This **replaces the hardcoded `substrate_search_dirs` list** with declared, per-layer globs.

### 3.2 `~/.uedcli/config.toml` — the per-user base (games)

Per-user, machine-local. **Just `[games.*]` blocks** — one block per game, declaring where that
game's base packages live (absolute globs). Nothing else: no `image`, no `container`, no `[defaults]`
(decisions.md 2026-07-01).

```toml
[games.deusex]
paths = "/home/me/games/DeusEx/System/*.u:/home/me/games/DeusEx/Textures/*.utx:..."

[games.unreal]
paths = "/home/me/games/Unreal/System/*.u:/home/me/games/Unreal/Textures/*.utx:..."
```

- **One shared UED22 editor image serves every game** (decisions.md 2026-07-01 04:26 UTC): there is
  no per-game `image` key. The game's paths are wired into the editor's `[Core.System] Paths` ini
  before launch (§8), and each session gets its own container *instance* of that one image.
- **No configured container** (2026-07-01 04:33 UTC): container instances are ephemeral, derived per
  session/op (`uned-<uuid7>`), spun from the one image and torn down after.
- A game's *physical install path* is declared **here, once** — never in a project. Internally a
  `[games.*]` block is the "substrate" concept; the user-facing key is `game`.

### 3.3 `<project-dir>/config.toml` — the project (overlay)

A project is a content tree; uedcli's home inside it is the **project dir** — conventionally
`<project-root>/uedcli/`, but any name (it is identified by holding a `config.toml`, not by its
name). The project dir is tracked, travels with a clone, and holds everything uedcli manages:
`config.toml`, the texture `texture-catalog/`, the per-level T3D-tree trunks under `maps/<level>/`,
and the `prefabs/` library (§5). The **project root is the project dir's PARENT** (`.git`-style — the
project dir is to the root what `.git/` is to a repo); the root is where `paths` globs resolve and
what the editor container mounts.

```toml
name  = "lum"                                   # display label (see §4 for id semantics)
id    = "0192f3a1-..."                           # uuid, minted by `uedcli project init` (§4)
game  = "deusex"                                 # REQUIRED — selects a [games.*]; no default (§4)
paths = "Maps/*.dx:Textures/*.utx:System/*.u:LUM/*.u"   # relative to the PROJECT ROOT (the dir above this file's dir)
```

The project's `game` is a **name**, resolved to a physical location via the per-user `config.toml` —
a project never hardcodes an install path. (The two `config.toml`s share a filename and are
classified by schema, **mutually exclusively**: a config with any `[games.*]` table is a **user**
config and MUST NOT carry top-level project keys; a config with any top-level project key
(`id`/`game`/`paths`/…) is a **project** config and MUST NOT carry `[games.*]`; a hybrid is rejected
naming both. `--config <path>` overrides the **user** config only; `--project <path>` points at a
**project** dir/config. The `~/.uedcli/config.toml` home config never false-matches project walk-up
because its schema is the user one.)

Example tree:
```
my_cool_project/              # PROJECT ROOT — the user's tree (docs, their own stuff, ...)
  Maps/*.dx Textures/*.utx LUM/*.u   # the project's package overlay (the `paths` globs)
  uedcli/                     # PROJECT DIR — uedcli's home; conventionally `uedcli`
    config.toml               #   project config + marker
    texture-catalog/          #   classification (tracked; NO images — derivable, §6)
    maps/<level>/             #   the T3D-tree TRUNK per level (§5)
    prefabs/                  #   prefab library (subdirs become names, §6.4)
```

**Anchor invariant (stated once so no consumer disagrees):**

| key | resolves against |
|---|---|
| `paths` | the **project root** (the project dir's PARENT) |
| `catalog` / `prefabs` / `maps` | the **project dir** |

The container mount root == the `paths` anchor == the project dir's parent — enforce with a named
test. In the tree diagram above, the bare names (`texture-catalog/`, `maps/`, `prefabs/`) all sit
under the project dir; only `paths` reaches up to the root.

### 3.4 Resolution: base, overlaid by the in-scope project

The composed effective path is **project globs first, then the selected game's base globs**, one
dedup rule (first-occurrence-by-case-folded-name wins, §3.1). Two operations over that one path:

- **Resolve-one** (missing-check, qualify, single `_first_match`): walk the composed path, return the
  **first** match — so a project package shadows a same-named base one (the engine's own search-path
  shadowing / a mod overriding a base package).
- **Enumerate-all** (the texture catalog sweep): list **every distinct** package, deduped by
  case-folded name, each tagged **provenance** (`base` | `project`). Same dedup as resolve-one.

No project in scope → base only. Project in scope → project-shadowed base. **Shadowing is silent** (a
deliberate exception to §4's no-silent-default — it mirrors the engine's own search); a
`--explain-paths` flag prints the composed, deduped path with provenance + shadow notes.

### 3.5 TOML schema (the keys)

**`~/.uedcli/config.toml`** (per-user). At least one `[games.*]` table is required. No other tables.

| Key | Type | Req? | Meaning |
|---|---|---|---|
| `[games.<name>].paths` | string (colon-glob, **absolute**) | yes | the game's base package globs |

**`<project-dir>/config.toml`** (per-project, tracked; the project dir is conventionally `uedcli/`).

| Key | Type | Req? | Meaning |
|---|---|---|---|
| `name` | string | no | human-facing display label (NOT the id — see §4) |
| `id` | string (uuid) | yes (minted by `project init`) | the project's stable identity / state-bucket key (§4) |
| `game` | string | **yes** | which `[games.*]` to overlay onto — REQUIRED; no global default, a project omitting it errors |
| `paths` | string (colon-glob, relative to the **project root** = the project dir's parent) | no | the project's overlay package globs (absent = no overlay, base-only) |
| `catalog` | string (path, relative to the **project dir**) | no | the classification catalog (§6.2), tracked. Default `<project-dir>/texture-catalog/` |
| `prefabs` | string (path, relative to the **project dir**) | no | the prefab library (§6.4), tracked. Default `<project-dir>/prefabs/`. Subdirs become part of a prefab's name (slashes). |
| `maps` | string (path, relative to the **project dir**) | no | the T3D-tree trunk root — one `maps/<level>/` tree per level (§5). Default `<project-dir>/maps/`. `level apply --to-t3d-tree` defaults its `--out` here, by level name. |

Unknown keys are an error (named), not ignored. A missing required key errors naming file + key.
`game` resolving to no `[games.*]` entry is an error listing the known games.

## 4. Choosing the current project

> **SUPERSEDED IN PART — 2026-07-05 (decisions.md 2026-07-05 14:58 UTC).** There is **no project
> `id`, no `project init`, no name→id registry, and no `config` verb.** Project state is fully
> in-tree, so there is no central `~/.uedcli/projects/<id>/` bucket to key. Project resolution still
> works by the `config.toml` marker + the walk-up ladder below (path/env/walk-up); the `id`-based
> and name-registry tiers are gone. The `project` verb reduces to **`project show`** (resolved
> project + composed `paths` + shadow provenance — the old `--explain-paths`). The rest of §4
> (marker, walk-up, path resolution) stands.
The current project resolves by precedence — highest wins, **no silent default** (mirrors the
existing `--session`/`UEDCLI_SESSION` discipline):

1. **`--project <name|path>`** — explicit. A **path** (contains a separator, is `.`/`..`, is absolute,
   or ends `.toml`) is taken as a project dir (or its `config.toml`) and read directly. A bare **name**
   resolves via the project registry (§9.2) — **but the registry is an open item; until it lands,
   name-based resolution (`--project <name>`, `project ls`, `project rm <name>`) is NOT available and
   only path-based `--project` works.**
2. **`UEDCLI_PROJECT`** — ambient default (same path/name handling as tier 1).
3. **The selected session's recorded project** — consulted only if tiers 1–2 yielded nothing, and
   **never for `session start`** (there is no session to read back when you are creating one). A
   session carries the `id` it started against (§5); a fallback read, not a precondition (the project
   is *bound* at `session start` from tier 1/2/4, then *read back* here — no circularity, no loop).
4. **Walk-up from cwd** — find the nearest ancestor `D` with an **immediate child dir whose
   `config.toml` has the project schema** (conventionally `D/uedcli/`, but any name — identity is the
   schema, not the name, so a non-conventional dir is still discovered); project dir = that child,
   root = `D`. **Two matching child dirs under one ancestor → error** (ambiguous; pass `--project`).
   The convenience tier for commands run *inside* a project tree (incl. the first `session start`).
5. **Error** — list resolvable projects; never guess.

**Project id (DECIDED): a uuid in the project dir's `config.toml`, minted by `uedcli project init`.**
`<id>` keys the central state bucket `~/.uedcli/projects/<id>/`. The uuid lives in the tracked
`config.toml`, so moving/renaming the project dir keeps its sessions (id is in the file, not the
path), and two checkouts of the same project share the session bucket.
> **Deferred coupling (§9):** Andrzej proposed **id = the project's path**, which is clean *iff*
> sessions move to git branches (then drop the `id`/uuid/registry). While sessions stay under
> `~/.uedcli/projects/<id>/`, id stays a uuid (a path id would orphan sessions on move). See §9.

### 4.1 CLI surface (new/changed verbs)

- **`uedcli project init [--name N] --game G`** — create the project dir `<cwd>/uedcli/` and mint its
  `config.toml` (generates the `id`). **`project ls`** (id, name, root, game) · **`project show
  [<name|path>]`** · **`project rm <name>`** — removes ONLY the central state bucket
  `~/.uedcli/projects/<id>/` (sessions/locks/shots) after confirm, **never the tracked project dir**.
  A project is "registered" the first time uedcli resolves its `config.toml`. **NOTE:** `project
  init`/`ls`/`rm-by-name` + the name→id registry are **on hold** — do not build them until the §9
  sessions-vs-branches spike resolves (they are the machinery most likely to be deleted if id=path).
- **`uedcli config [get|set] …`** — read/edit `~/.uedcli/config.toml` (per-game paths).
- **Global flags everywhere:** `--project <name|path>`, `--config <path>`, `--explain-paths`.
- **`session start <level>`** — resolve a bare level name against `<project-dir>/maps/<level>/` (the
  trunk) as the primary entry point (a path still works). Adopted 2026-07-01.
- **`uedcli texture gc` / `sync --prune`** (§6.0). All existing verbs get project-scoped overlay
  resolution transparently (§3.4) — no per-verb flags.
- **Removed:** `package load` — the loadable set is derived on demand (§7); there is no manifest to
  add to.

## 5. The `~/.uedcli/` layout + the project dir

> **SUPERSEDED — 2026-07-05 (decisions.md 2026-07-05 14:58 UTC).** Machine-local **per-project**
> state is NOT central. It lives **in-tree** under `<project>/uedcli/`: tracked
> `config.toml`/`maps/`/`texture-catalog/`/`prefabs/`, plus a **gitignored `tmp/`** (stash, `flock`s,
> docker-cp/apply temps, shots). **There is no `~/.uedcli/projects/<id>/` and no session store** —
> a level is edited on a **git feature branch** and merged into trunk with `git merge` (§9's
> deferred pivot is now adopted). `~/.uedcli/` holds only per-user state: **`config.toml`** + a
> **`cache/{textures,stubs}`** (content-addressed image + stub caches — shared cross-project,
> derivable, never committed; regroups the `~/.uedcli/{textures,stubs}` below under `cache/`). The
> project-dir tracked layout below stands; the `projects/<id>/` block does not.

The global home is **`~/.uedcli/`** (decisions.md 2026-07-01; the XDG split was considered and
rejected — keep one obvious home dir). The project dir is the **non-dot** `uedcli/`, so `.uedcli`
means the home exclusively — no same-basename confusion (the collision the 2026-06-29 06:02 UTC
decision resolved).

```
~/.uedcli/
  config.toml                         # per-user games config (§3.2)
  projects/<id>/                      # per-project machine-local state (central, out of tree)
    config                            # generated: { project_dir, game, name } back-pointer
    store/                            # the session store (git plumbing) — sessions live here (see §9)
    locks/                            # flocks (editor/target serialization)
    tmp/                              # host<->container docker-cp scratch
    shots/                            # preview screenshots
  textures/                           # content-addressed texture IMAGE cache (§6) — shared, derivable
    packages/<pkg-hash>.<schema>/index.json
    data/<pixel-hash>.png
  stubs/                              # v69 stub cache (was <repo>/.uedcli/cache/stubs/) — derivable
```

- **Sessions, locks, tmp, shots are per-project** under `projects/<id>/`, central by design.
- The **texture image cache and stub cache are NOT per-project** — content-addressed / derivable,
  shared across projects. A `~/.uedcli` wipe loses only *un-applied sessions* (durable record is the
  committed trunk), so "apply often" is the habit.
- The per-project `config` is a **generated back-pointer** (id → project dir + resolved game; the
  project root is its parent), not authored config — **rewritten on every resolve**, so a moved
  project self-heals its `project_dir`.

**The project dir** (`<project-root>/uedcli/`, conventional name) holds the tracked, clone-travelling
artifacts: `config.toml`, `texture-catalog/` (§6.2), `maps/<level>/` T3D trunks, `prefabs/` (§6.4).

**T3D-tree trunks** live at `<project-dir>/maps/<level>/` — the authored source of truth per level.
`level apply --to-t3d-tree` defaults its `--out` to `<maps>/<level>/` by level name, overridable. A
built `.dx` via `--to-map-file` lands in the content tree like any other package (a build artifact).

**The store moves; the apply *output* does not.** Only the event log / session store relocates to
`~/.uedcli/projects/<id>/store/`. `level apply` still writes its durable artifact — the `.dx` / T3D
tree — into the content tree, and does `--git-commit` against that tree's working repo. Per-target /
per-session `flock`s live under `~/.uedcli/projects/<id>/locks/` (target lock keyed on the resolved
`--out` abspath, so two sessions can't race a destination).

## 6. Content-addressed texture image store

The decoded-image store is content-addressed under `~/.uedcli/textures/`, shared per-user across all
projects and games:

```
packages/<package-hash>.<schema>/index.json   # one per (package FILE version × decode schema)
data/<pixel-hash>.png                          # one per distinct image content (deduped)
```

- **`decode_schema`** is a hand-maintained **integer constant** (`DECODE_SCHEMA` in
  `texture_catalog.py`), bumped only when the decode *output shape* changes (PNG encoding, the
  color-name palette, the index layout). The cache dir is `packages/<pkg-hash>.<DECODE_SCHEMA>/`
  (`<pkg-hash>` = sha256 of the package file's raw bytes); a bump makes old dirs GC-eligible.
  Re-syncing a package whose bytes **and** schema are unchanged **skips decode entirely**.
- **`pixel_hash` (= `image_hash`) is schema-INDEPENDENT** — sha256 of the canonical decoded RGB bytes
  + dims (decisions.md 2026-06-22). `DECODE_SCHEMA` must NOT change it, so classification (§6.1, keyed
  on `pixel_hash`) stays **durable across a schema bump**. A change that genuinely alters decoded
  pixels is a rare migration event, not a routine schema bump.
- **`index.json`** (per package version): `{package, package_hash, decode_schema, textures:[{name
  (in-pkg Group.Name), ref (user-facing, §6.3), pixel_hash (=image_hash), w, h}]}`. `textures` is a
  **list** (two names may share one pixel content; a ref may need 3-part disambiguation). The reverse
  `pixel_hash → [refs]` index is built in memory over **all present `packages/*/index.json`** (per
  invocation; fine at install scale — revisit if slow).
- **`data/<pixel-hash>.png`** = the decoded PNG keyed by `pixel_hash` (= `image_hash`), **deduped**:
  identical content across packages/versions is stored once.

### 6.0 GC + concurrency

- **Orphan GC:** a `data/<pixel-hash>.png` is live iff some present index references it. `texture gc`
  (and opt-in `sync --prune`) deletes unreferenced PNGs and stale `packages/<hash>.<schema>/` dirs.
  GC is **never implicit** in a plain `sync` (a sync only adds).
- **Concurrency:** N agents may sync (D5/D7). Writes are atomic (temp + `os.replace`) under a
  per-`<package-hash>.<schema>` flock; `data/` writes are content-addressed (identical bytes, safe).
  **GC's store-wide lock is EXCLUSIVE and also blocks `sync`** (sync takes it *shared*) — otherwise
  the classic add-vs-sweep race bites: GC reads "pixel X unreferenced", a sync writes an index
  referencing X, GC deletes X. Under the shared/exclusive discipline GC can't run concurrently with a
  sync, and re-verifies references under the exclusive lock.

### 6.1 How the classification catalog relates

The **classification manifest** (tags/colors/description) is separate from the image store and
**keys on the pixel-hash** — the durable identity that carries classification across a rename.
`texture list/search` joins the classification manifest (by pixel-hash) × the package index × the
data store.

### 6.2 Classification in-project; images in the home cache; share by CLONING (2026-06-29 06:48 UTC)

- **Classification (tags/colors/description) lives ONLY in the project**, tracked at
  `<project-dir>/texture-catalog/` (the `catalog` key), keyed by **`pixel_hash`**. **No home/per-user
  catalog and no per-substrate base catalog.** It holds no pixels — metadata + the pixel-hash join
  key only, so it stays diff-friendly and committable.
- **Image files are NEVER in the project** — derived, living in the content-addressed home cache
  (`~/.uedcli/textures/`, §6). Regenerable via `texture sync`; a cache wipe costs only a re-decode.
- **Share classification across projects by CLONING, not a shared catalog.** `texture classify clone
  --from <other-project>` copies entries matched by `pixel_hash` — common assets (identical pixels ⇒
  identical hash) inherit tags/colors/description without re-classifying. No shared mutable store, no
  base/project merge, no staleness. Clone is a **point-in-time copy**, not a live link: a shared
  `pixel_hash` means shared *pixels*, NOT shared *intended* classification (the same vanilla wall may
  be "temple" in one project, "sewer" in another). Conflict policy: **skip if the target ref is
  already classified**; `--overwrite` to force; report copied vs skipped.

### 6.3 Refs and collisions

- Default ref is **2-part `Package.Name`**; a package with two same-`Name` textures in different
  `Group`s gets **3-part `Package.Group.Name`** for both. Both forms accepted by `texture classify
  set` / `poly set --texture`.
- Cross-package, same `Package.Name`, **different** pixels is allowed (distinct `pixel_hash`, distinct
  classification); the layering decides which is *live* (project shadows base), but `list`/`search`
  can surface both, provenance-tagged — never silently merged.
- Same `Package.Name`, **same** pixels → one `pixel_hash` → shared image + shared classification.

### 6.4 Prefabs

Prefabs are tracked in the project under `<project-dir>/prefabs/` (the `prefabs` key). **Subdirectories
are the organizing + naming mechanism: a prefab's name is its path under `prefabs/`** (names contain
slashes): `prefabs/furniture/chairs/office-chair.<ext>` → `furniture/chairs/office-chair`. Namespacing
is not required. `repo_paths.prefab_library_root()` becomes the project dir's `prefabs/`.

## 7. Package consumers under the layering (the analysis set)

The composed `paths` (§3.4) — real install `.u`/`.utx`/… — are the **analysis / authority set**,
consumed **model-side** by: closure, missing-check, qualify, and **class-property schema extraction**
(`actor prop`'s validator parses a class's `.u` export table). There is **no stored package manifest**
(decisions.md 2026-07-01): the loadable set is derived on demand from the level's qualified
`Texture=`/`Class=`/object refs + `paths`, so `package load` is retired.

**Class-property schema extraction reads the real `.u`, never stubs** (decisions.md 2026-06-26 14:10):
it filters the composed path to the `.u` subset (project overlay `.u` ++ the game's base `.u`,
project-shadowing-base). A game's `paths` point at the real game `.u` (authoritative); the stub cache
is derived, editor-load-only, and never on the authored `paths`.

**The on-demand derivation MUST walk the import-table transitive closure** (computed, not stored) —
direct-refs-only is a **known-broken** path for `apply`: a qualified `Texture=` does not auto-demand-
load its package, and content-to-content deps a level never names (e.g. `CoreTexMetal`→`CoreTexDetail`)
are absent from its refs (`quirks.md`). Retiring the *stored* manifest is fine; the closure walk is
not optional. What is genuinely **open (§9.2)** is only whether any part can instead lean on engine
demand-load — the walk itself stays.

## 8. Editor / container implications

The editor is reached only at `level apply`/`preview` (build/preview). When it loads, the overlay
must expose **both** layers (decisions.md 2026-06-29 05:18 UTC, option (a)):
- mount the **shared substrate** (the single shared **UED22** image bakes `/opt/UED22` — the same
  image for every game, instantiated per session; install content via a read-only mount) **and** the
  **project's asset dirs** (a read-only mount of the project root / its declared paths), and
- wire **both** onto the in-container `[Core.System] Paths` with **project precedence**.

**The editor loads STUBS for code, not the raw `paths`** (decisions.md 2026-07-01 06:16 UTC). A game's
`paths` are the *analysis* set (real `.u`, §7); UED22 can't load v68 code, so the editor-load view
substitutes v69 **stubs** — built/cached on demand (2026-06-21/22) and wired as a **high-priority
override entry** — plus the content mounts. The raw v68 `System/*.u` globs never reach the editor.

**How shadowing is actually enforced (paths-precedence spike, 2026-07-01, CONFIRMED live):**
- **At `apply`/materialize, shadowing is HOST-SIDE.** uedcli loads each package with an explicit
  `OBJ LOAD FILE=<resolved path>`, so *which* file loads is decided by the composed-`paths` resolver
  (§3.4 — first-wins, project-shadows-base) picking the file; **the editor does not shadow at load
  time.** The host resolver must therefore impose project-shadows-base when selecting files to load
  (it already does, §3.4), and the resolved code file is the **stub**, not the v68 original.
- **The editor's `[Core.System] Paths` first-match-wins is CONFIRMED** (both orderings; an override
  dir ahead of the baked substrate shadows it — spike H1/H2), but governs only the **indirect /
  by-name** path (UCC batchexport; demand-load). So the paths written to the ini must be
  **project-first, stubs ahead of substrate**, so by-name resolution agrees with host selection. Only
  **directory-glob** `Paths=` entries are searched (a full-file-path entry is ignored).
- **Operational (load-bearing):** the ini `Paths=` edit and the consuming op must be **one atomic
  `docker exec`** — the running GUI editor rewrites `unrealtournament.ini` from its boot-time config
  and clobbers a post-launch `Paths=` edit (`unrealed/quirks.md`). Full editor-load precedence,
  project → project code (stub, or first-party v69 like `LUM_Core.u` direct) → base code stubs →
  baked substrate + content.

As more verbs go native (no editor), this shrinks to just the apply/preview path.

## 9. Deferred / out of scope

### 9.1 Sessions vs git branches — ADOPTED (decisions.md 2026-07-05 14:58 UTC)

> **NO LONGER DEFERRED — 2026-07-05.** The pivot below is now the decision: the bespoke session
> store is dropped; a level is edited on a **git feature branch** and merged into trunk with `git
> merge`. This commits to replacing the shared `order` file with a **per-actor sortable order key**
> (fractional / LexoRank — the git-merge spike's one blocker, 2026-07-01 07:05). The coupled
> decisions below (id = path, drop registry/`project init`) all resolve to **no `id` at all**, since
> there is no central state to key. A fresh spike/spec should precede the build.

The current model is the store-centric event-sourced session store (2026-06-18;
`session.py`/`replay.py`/`merge.py`/`audit.py`/`integrity.py`). A candidate replacement: **the T3D
tree is real git; a session is a branch; merge is `git merge`; materialize (`.dx`) is a separate
build step.** It is **deferred — spike before any commitment.**

- **Attraction:** `direction.md` already targets a git-committed T3D trunk with map files as build
  artifacts; the trunk is per-actor text (`maps/<level>/actors/*.t3d` + `order`) that git merges
  natively; emit is canonical (clean diffs/merges); the manifest is gone. Branches parallelize for
  free; git's per-actor 3-way merge ≈ uedcli's hand-rolled per-actor merge — collapsing the
  store/replay/merge machinery.
- **Costs / risks:** supersedes the 2026-06-18 model and a lot of built code (real migration); the
  single-file `order` is a merge hotspot (mitigation: a per-actor ordering key); git merge is textual,
  not semantic (intra-actor property conflicts); how uedcli edits a branch (git worktree per session
  vs plumbing writes without checkout) is a design choice.
- **Spike RESULT (2026-07-01, `spikes/2026-07-01-git-merge-t3d-tree/`): git merge is VIABLE.**
  Disjoint per-actor edits/adds auto-merge clean (each actor is its own file); same-actor conflicts
  are clean and human/LLM-resolvable; **canonical emit is confirmed load-bearing** (a non-canonical
  property-reorder caused a spurious conflict — we already emit sorted/normalized, so enforce it, don't
  assume it). **The one required change: eliminate the shared `order` file** — it conflicts on every
  concurrent add (textual tail-adjacency). Replace CSG precedence with a **per-actor sortable order
  key** (fractional / LexoRank, to avoid renumbering), which the spike proved merges concurrent adds
  with zero conflict; reordering existing actors then genuinely conflicts (correct). So the pivot is
  more attractive than before; the residual gate for the eventual spec is the **migration cost** and
  the **worktree-vs-plumbing edit model**, not merge viability.
- **Coupled decisions (also deferred until this resolves):** **project id = path** (clean iff
  git-native — then drop `id`/uuid/`project init` minting/the name→id registry); while sessions stay
  central, id is a uuid. `session start <level>` is adopted regardless (§4.1).

### 9.2 Other open items

- **Editor-image bootstrap:** a `pipx`-installed uedcli has no repo, yet the single UED22 image is
  currently *built* from `Tools/uedcli/uned/`. How the installed tool obtains it — bundle the build
  context and build-on-first-use, pull a published image, or assume prebuilt — is **open**. (De-
  containerization eventually deletes the image entirely.)
- **Project registry store:** name-based `--project <name>` needs a name→id index; where it lives (a
  `~/.uedcli/projects.toml` index vs a scan of `projects/*/config`) is **open** (config.py stubs it as
  an injected `resolve_name` hook — slice E). **AT RISK / on hold:** the registry + `project init` uuid
  minting are the machinery most likely to be **deleted wholesale** if §9.1 lands (id = path, no
  registry). Do **not** build them until the spike resolves; path-based `--project` is the only
  selector until then.
- **Transitive-dep load contract** (§7) — pinned at build; lean: keep closure-walk on demand.
- **De-containerization** of apply/preview — separate roadmap (decisions.md 2026-06-27→29); this spec
  only states the mount/overlay contract it must satisfy.
- **Windows port** — the `:` separator + path handling would need revisiting.
- **Migration DROPPED** (decisions.md 2026-06-29 05:18 UTC): no `uedcli migrate`; existing in-repo
  `.uedcli/` + `texture-catalog/` are not carried. The legacy fallback (below) stays so nothing breaks
  on upgrade; users opt in by creating a project dir + `config.toml`.

### 9.3 Legacy fallback (transition)

Until a project `config.toml` exists, the current repo-bound resolution stays: a build detects "no
project config, has `Tools/uedcli`" and uses the legacy `host_repo_root`/`substrate_search_dirs` path.
Every slice is built additively behind this fallback — with no config present, behavior is
byte-identical to today.

## 10. Impact map (today → target)

| Today | Target |
|---|---|
| `host_repo_root()` walks up for `CLAUDE.md`+`Tools/uedcli` | project resolution per §4 (project-dir `config.toml` marker; root = the project dir's parent) |
| `substrate_search_dirs()` hardcoded list (substrate **and** repo content) | composed glob paths: project `config.toml` overlay (vs project root) ++ game base (§3.4) |
| `.uedcli/` at repo root (sessions/locks/caches in-tree) | `~/.uedcli/projects/<id>/` (sessions/locks/tmp/shots) + `~/.uedcli/{textures,stubs}` central |
| `.uedcli/textures/<package>/<name>.png` flat, per-repo | `~/.uedcli/textures/{packages/<pkg-hash>.<schema>/index.json, data/<pixel-hash>.png}` content-addressed, shared (§6) |
| catalog manifest tracked at repo root, substrate-wide | classification tracked in the project dir (`texture-catalog/`); no base catalog; shared by pixel-hash clone (§6.2) |
| stored `packages` manifest + `package load` verb | **DROPPED**: loadable set derived on demand from qualified refs + `paths` (§7) |
| per-game editor image / `--container` selection | one shared UED22 image; ephemeral per-session container instances (§3.2/§8) |
| `UEDCLI_*` env knobs only | per-user `config.toml` + project `config.toml`, env/flags still override (§4) |
| run via `.venv-uedcli/bin/python -m uedcli` | `pipx install uedcli` → `uedcli` on `$PATH` |

## 11. Decision references

Every decision above is durably recorded in [`decisions.md`](../../../decisions.md): 2026-06-29 (global-CLI
open decisions, migration dropped, overlay = mount + ini `Paths=`), 06-29 06:02/06:48 (tracked
project dir, texture model), 2026-06-30 06:18 (project dir = conventional `uedcli/`, root = parent),
06-30 18:47 (home `~/.uedcli/`, substrate=game, drop manifest), 06-30 21:07 (config key `game`),
2026-07-01 04:26/04:33/04:36 (drop image/container/default game), 07-01 06:16 (stubs via override
`Paths=`; DEFER sessions-vs-branches). Also 2026-06-21/22 (stubbing, bake UED22), 2026-06-22 (texture
catalog), 2026-06-23 (generic-UE1, terminology, T3D-trunk direction), 2026-06-26 14:10 (schema reads
real `.u`), 2026-06-27→29 (de-containerization). Folds into `architecture.md`/`direction.md` on
implementation.
