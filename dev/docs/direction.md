# uedctl — direction (what we're building toward)

This is the **compiled target**: the coherent end-state uedctl is being built toward, stated
in the present tense even where the code doesn't match yet. It is *synthesized from*
[`decisions.md`](decisions.md) — newer decisions override older ones and the superseded points
are dropped here (this doc shows the **net** philosophy, not the history). Each section cites
the decision entries it distills.

How the three dev docs relate:

| Doc | Role | Mutability |
|---|---|---|
| [`decisions.md`](decisions.md) | the **ledger** — every choice + rejected alternatives, timestamped | append-only, never reworded; supersession via new entries |
| **`direction.md`** (this) | the **compiled target** — what we want, conflicts resolved | rewritten/reconciled as decisions land; superseded points removed |
| [`architecture.md`](architecture.md) | **what is** — current implementation | tracks the code |

**Maintenance rule:** when a decision is made or superseded, reconcile this doc. If `direction.md`
and `architecture.md` disagree, that gap is intended (it's the work not yet done); if `direction.md`
and the latest `decisions.md` disagree, this doc is stale — fix it.

---

## Scope: a generic UnrealEngine-1 tool

**MIGRATED** → [`direction/scope.md`](direction/scope.md).

## Projects, substrates, and the global CLI

uedctl is a **globally-installed CLI** (`pipx install`, one binary on `$PATH`) that operates on many
independent **projects**, not a tool living inside one content repo. Three things are cleanly
separated:

- **A game (internally "substrate") per `[games.*]` block.** A per-user `~/.uedctl/config.toml`
  declares each game once — where its base asset packages live (`[games.<game>].paths`). So one
  install serves Deus Ex, Unreal, and other UE1 games; a project names which game it targets via its
  `game` key. The **editor is a single shared UED22 image** for every game — the game's paths are
  wired into its `[Core.System] Paths` ini at launch — so a game block carries no image key. The
  build editor (`level materialize`, incl. `preview --game`'s internal materialize) runs in a
  **warm per-user editor container** (`uedctl-editor-<uid>`): reuse gated by ONE `docker inspect`
  on a fingerprint label (image + mounts + mutable package `(path,size,mtime)` tuples — resident
  editor state survives `MAP NEW` and the ini is boot-time-fixed, so staleness reboots), a
  nonblocking per-user flock,
  and a 10-min-idle self-death watchdog. On contention (lock held, or pinned with another config)
  the invocation falls back to its own **per-command ephemeral container** (created, driven, torn
  down within the one invocation) — the ephemeral container remains the concurrency story
  (parallel builds still compose; no session, no queue), the warm one is a fast path in front of
  it. Every other editor-driving command stays per-command ephemeral. *(decisions: per-command
  editor identity, 2026-07-06 05:12; warm editor container for materialize, 2026-07-18 21:52)*
- **Project = a repo with a free `uedctl.toml` at its root.** A project is identified by a
  free-standing **`uedctl.toml`** at the repo root (à la `pyproject.toml`; discovered by walking up
  from cwd to the first ancestor containing one — nearest wins, `.git`-style). The file declares the
  substrate (`game`), the overlay `paths`, and — as **relative paths with conventional defaults** —
  where each managed dir lives: the **maps dir** (per-level T3D trunks; default `maps/`), the
  **prefabs dir** (default `prefabs/`), and the **texture-catalog dir** (default `texture-catalog/`)
  — so uedctl can point at a repo's EXISTING dirs instead of forcing a parallel tree. There is no
  fixed `uedctl/` project subdir; the **root path is the project identity** (no id, no registry).
  `paths` resolve against the root. *(decision: project layout reorg, 2026-07-17 20:58)*
- **Layered packages.** Config `paths` are **bare directories** (colon-separated), NOT globs —
  uedctl owns the five package extensions (`.u .dx .utx .uax .umx`) and scans the dirs itself. The
  effective set is the project's overlay dirs first, then the selected game's base dirs, deduped
  project-shadows-base — the engine's own search-path shadowing — at TWO granularities: by directory
  for the container mounts (`composed_search_dirs`), and by package stem for the load set scanned out
  of those dirs (`composed_search_files`). There is **no stored package manifest**: `level
  materialize` wires the **whole composed search path** into the editor's `Paths` ini and lets `MAP
  IMPORT`/`REBUILD` resolve every ref against it — no per-level derivation, no transitive-closure
  walk *(decisions: materialize load contract 2026-07-05 23:00; config lists bare dirs 2026-07-14
  03:30)*.
- **Per-project state is in the tree, not central.** The content tree holds the tracked authored
  artifacts (`uedctl.toml` + the declared maps/prefabs/catalog dirs); ALL machine-local throwaway
  state (stash, `flock`s, staging temps, delivered preview maps) sits in
  ONE in-repo, gitignored, **self-ignoring** **`.uedctl/`** beside `uedctl.toml` (uedctl writes
  `.uedctl/.gitignore` containing `*` on creation). The per-user **`~/.uedctl/`** holds only
  `config.toml` (the `[games.*]` config) and `cache/{textures,stubs,schema}` — the image + stub
  caches (content-addressed) and the per-package decoded-schema cache (stat-tuple-keyed), shared
  cross-project, derivable, never committed. There is no central
  per-project bucket and no project `id`. **Tool-install assets** (compose dir, UED22 substrate,
  umodel) resolve package-relative — from the uedctl installation, never from a repo or project.

*(decisions: global-CLI/projects 2026-06-29 + 2026-06-30; in-tree state / no-id 2026-07-05;
project layout reorg — free `uedctl.toml`, in-repo `.uedctl/`, package-relative tool assets —
2026-07-17 20:58; substrate split / generic-UE1 2026-06-21/23)*

## The trunk and the editor

**MIGRATED** → [`direction/trunk-and-editor.md`](direction/trunk-and-editor.md).

## Terminology

**MIGRATED** → [`direction/terminology.md`](direction/terminology.md).

## Folders and labels

**MIGRATED** → [`direction/organization.md`](direction/organization.md).

## Materializing the map file

**MIGRATED** → [`direction/materialize.md`](direction/materialize.md).

## Safety

**MIGRATED** → [`direction/safety.md`](direction/safety.md).

## Container isolation and the code/content substrate split

No container writes into the repo tree: the substrate is baked into the image, content is exposed
read-only, and the only mutable exchange is a container-local scratch dir. Editor **code** (`.u`)
is substrate-authoritative (UED22's v69 packages); a game's own v68 code is converted on demand to
v69 "stubs" (mesh-preserving) rather than loaded directly. Editor **content** (textures/sounds/
music) is a separate, user-supplied concern. *(decisions: container-fs isolation, package stubbing,
bake-UED22, 2026-06-21/22)*

## Generator pattern: stateless T3D producers

Shape-building and point-actor verbs are **generators** — stateless commands that write a
T3D snippet to stdout (typically one actor; `brush build spiral` emits a central column plus one wedge-tread actor per step).
Generators write to neither the trunk nor the stash; the caller decides what to do with the
output (pipe to `actor add -`, redirect to a file, compose with `stash`). **Name allocation and
the write into the trunk T3D tree live exclusively at `actor add`**, the only consumer that holds
both the target level and the incoming T3D at once — but generators DO set the actor's authored
identity, including its organization: `--folder`/`--label` (emitted as `// uedctl-folder:`/
`// uedctl-labels:` carriers), `--csg`, `--solidity`, `--texture`, `--rotate`, `--prop`; a plain
engine prop like `Group` is set with `--prop Group=` (no dedicated flag). **`brush intersect`/
`brush deintersect` are generators too** — they read a **T3D brush set on stdin** (`-`), CSG-merge it
model-side, and emit one brush/mover actor, sharing the same output flags; the tiers feed them by piping
`actor show`/`stash show`/`prefab show` (so there are no `stash`/`prefab` intersect/deintersect verbs).
**Two of the generators sweep a profile the AUTHOR draws** rather than sizing a fixed shape:
`brush build extrude` (straight, `--depth`) and `brush build revolve` (around an in-plane axis,
`--angle`/`--segments`) take a repeatable `--point U,V` ring, a shared `--axis x|y|z`, and anchor
`--at` on profile coordinate `(0,0)`; a concave or over-16-vertex profile stays ONE brush with its
caps tiled into convex faces. **Every builder angle is expressed in unreal rotation units at the
CLI, like `--rotate`** — never degrees (`spiral --angle-per-step`, `revolve --angle`) — except where
the only real use is a boolean, which is why `cylinder`/`cone` take `--align-to-side` (a
half-segment offset, matching UnrealEd's own `AlignToSide`) instead of a free angle.
*(decisions: profile generators + UU builder angles, 2026-07-25 00:14/01:05/02:30)*

`brush build --mover-class <Package.Name>` (and `brush deintersect --mover-class`) produce a **base Mover**
(no `CsgOper`, base pose only); keyframes are then authored with the trunk-editing `mover key`
verbs. *(decisions: generator pattern, 2026-06-24 14:30 UTC; mover support, 2026-06-25; native
intersect/deintersect + generator-flag cleanup, 2026-07-24 16:32/17:04)*

## One package-format core

All Unreal package files (`.u .dx .utx .uax .umx .unr`) are one on-disk format; uedctl parses
them through **one shared low-level reader** (`upackage.py` — header, compact index, name/import/
export tables, tagged-property lists), with per-use-case decoders (class schema + defaults,
textures, import closure) layered on top. No use-case or extension reimplements the low-level
parsing. (The pre-existing private copies in `utexture`/`dxpkg` migrate onto the core as a
follow-up.) Property READS have the engine's semantics: an unset property resolves to its class
default, decoded offline from the game's own `.u` (bytecode-walker route), zero when unspecified.
*(decision: `actor prop` subcommands + unified core, 2026-07-18 10:02)*

Meshes are part of that core: the full UE1 `UMesh`/`ULodMesh` body decodes natively, with the
**vertex stride self-detected** from the `Verts` TLazyArray skip offset (8 bytes for Deus Ex's
`int16` quad, 4 for stock Unreal's packed dword), so one decoder serves every UE1 substrate with no
per-game flag. Rendering a mesh — a catalog thumbnail, an actor preview — is therefore pure offline
compute: **no editor, no container, and no `umodel.exe`**, which survives only inside the stub
pipeline. *(decision + spike: native mesh decode, 2026-07-25 03:40)*

## The asset catalog: uedctl lists and shows, the LLM supplies meaning

Level design by an LLM agent needs to **discover** what can be placed, not just place it. One
**asset catalog engine** serves four kinds — **texture, class, sound, music** — each with its own CLI
noun and the same verb family (`list`/`search`/`show`/`preview`/`classify`/`tags`/`prewarm`);
"unified" means one implementation, never a `--kind` selector on a generic noun.

**The tool does not infer.** It does four things: **lists** what exists on the composed search path;
**reports facts literally stored in the package** (image dimensions, mesh bbox, collision
radius/height, pivot, parent class, `DrawType`); **produces the picture** (decodes a texture, renders
a mesh natively); and **stores + queries the classification it is handed**. What an asset *is*, what
it is *for*, and *where the game uses it* are the LLM's findings, recorded as classification — never
numbers the tool computed, which would be unreviewable and uncorrectable. The one deliberate
exception is **texture colours**, pre-filled from that texture's own pixels and ordered by
importance, so colour search works before any classification exists.

Mechanically: a lazily-built per-`(kind, package)` derived index gated on a
`(realpath, size, st_mtime_ns)` stat tuple, a content-addressed per-user preview cache, and
**git-tracked classifications sharded one file per asset** so concurrent agents never merge-conflict.
Identity is the **content hash** where content exists and decodes (textures) and the **name**
otherwise (class, sound, music) — so a changed texture simply reads unclassified and its old
classification becomes a prunable *outdated entry*, with no `stale` flag to maintain. Two verbs, two
jobs: **`show` returns facts + classification, `preview` returns image artifacts** — and `preview` is
the *only* producer, so no exploratory `list`/`search` can trigger a long render. Classification is
batch-capable (`classify set -` reads JSONL) and a **byproduct of looking** (`preview --skeleton`
emits fill-in rows for exactly the refs just previewed), never a bulk campaign. Cache eviction lives
on the existing `cache` noun. *(decisions: unified asset catalog 2026-07-25 03:40; the tool does not
infer 2026-07-25 05:10; spec `specs/2026-07-25-unified-asset-catalog.md`)*

## Conventions (no back-compat cruft; explicit, discoverable, model-side)

**MIGRATED** → [`direction/conventions.md`](direction/conventions.md).
