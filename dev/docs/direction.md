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

## The T3D trunk is the source of truth; the editor is a build tool

The durable source of truth is the **git-tracked T3D trunk** (`<maps-dir>/<level>/`, the maps dir
declared in `uedctl.toml`),
not a live editor. Every read and mutation is pure model-side compute against the T3D.
**`level materialize`** drives **UnrealEd** to build the map file (until the native build replaces
it) — in the warm per-user editor container, falling back to a per-command ephemeral one on
contention *(decision 2026-07-18 21:52)*. **`level preview` is two-tier behind one verb**, sharing one batched
pose grammar (`at:…;rot:…` / `look:@actor` / `orbit:…`):
- **`--game` (the DEFAULT) — the faithful tier.** Delivers the map into a **warm** per-user headless
  DeusEx container (booted once, then reused across previews, self-terminating on idle) and renders
  truly-lit first-person stills: freezes the world, ghosts the player, poses the pawn per shot, and
  screenshots the engine's own frame over a uedctl-owned TCP link (VNC is dev-debug only) — what the
  *player* sees, for hero shots and lighting judgment. It is the default because it shows lighting,
  meshes and sky, and because the offline draft mis-renders overlapping-subtract geometry (doorways)
  silently — a misleading default feedback loop is worse than a slow one.
- **`--native` — the opt-in offline draft tier.** No container at all: the Rust CSG core carves the
  trunk in-process and a software rasterizer renders freely-posed, textured perspective stills in
  seconds (flat-shaded v1; a `--lit` mode consuming the native lightmap bake follows). Fast,
  docker-free geometry-only iteration; no lighting, meshes, or sky.

The editor is no longer the preview driver in either tier (the editor-screenshot renderer is
retired). The LLM issues semantic by-name commands; T3D is internal plumbing. *(decisions:
store-centric model 2026-06-18; durable store is git, 2026-07-05; preview renders in-game via a
TCP link, 2026-07-13 — supersedes the editor snapshot-renderer of 2026-07-06 12:01; two-backend
preview 2026-07-16 12:13; `--game` becomes the DEFAULT / `--native` opt-in, 2026-07-17 18:46)*

## The trunk: a git-committed T3D tree, edited on feature branches

The durable trunk is a **T3D tree committed to real git** — the authored content in version control
— with **map files (`.dx`/`.unr`) demoted to pure build artifacts**. A level is edited on an
ordinary **git feature branch** in the project's own repo and merged into trunk with `git merge`;
per-actor `.t3d` files merge natively, and a **per-actor sortable order key** (replacing the shared
`order` file) keeps disjoint edits conflict-free.

**One T3D tree format across trunk, stash, and prefab (INVARIANT).** All three on-disk T3D trees —
the git **trunk**, a machine-local **stash** entry, and a git-committed library **prefab** — **MUST**
use the same per-actor layout (`actors/<name>/{actor.t3d, order_value[, folder]}`; no shared `order`
file), read and written through ONE shared code path, with any per-tree extras (a stash/prefab
`meta.json`, `packages`) sitting *beside* the shared `actors/` tree. There are not three divergent
formats to keep in sync — a stash or prefab is structurally the same kind of T3D tree as a level.
*(decision: T3D-tree consistency invariant, 2026-07-18 23:01 UTC; spec `specs/2026-07-18-unify-t3d-trees.md`)*

**The bespoke session store is being removed in favor of this git trunk.** There is no
event-sourced session store, no session, and no session `id`; `session.py`/`replay.py`/`merge.py`
and the store tree collapse into git. Work-in-progress is simply an uncommitted / feature-branch
state in the project's own repo — **git is the history and the merge engine**, not a private store.
(The one thing that survives is the **stash** — captured actor sets — but it is machine-local
throwaway scratch under the gitignored in-repo `.uedctl/`, *not* a session and not durable state.)
*(decisions: git-branches-replace-sessions 2026-07-05 14:58; un-defers 2026-07-01 06:16; git-merge
spike 2026-07-01 07:05)*

## Terminology

**MIGRATED** → [`direction/terminology.md`](direction/terminology.md).

## Folders and labels

**MIGRATED** → [`direction/organization.md`](direction/organization.md).

## Materializing the map file: `level materialize`

Editing produces the git-tracked T3D trunk; **`level materialize`** is the pure build step that
materializes the current trunk into the `.dx`/`.unr` **build artifact** — **map-file output only**
(the T3D tree is the source, reached via git, not a build *target*). It names its destination
explicitly (`--out`), **refuses to overwrite an existing file**, and keeps the **H3 post-verify**
(the rebuilt map matches the trunk). The post-verify compares **TYPED EFFECTIVE VALUES, not text**:
every property of both sides resolves to the stored value if the actor states one, else the class
default, decoded by its declared type — so two actors are equal iff they would import to the same
object, and the editor's default-diffing spellings (`4.0` vs `4`, `(Yaw=8192)` vs
`(Pitch=0,Yaw=8192,Roll=0)`, an omitted `LightRadius=0`) are simply the same values rather than
mismatches to be tolerated. That needs the game's `.u` packages for the class schema + defaults —
resolved before the editor starts, with **no "assume zero" fallback**, so an unqualified or
unresolvable actor class exits 2 in ~0.1 s naming the actor. Symmetrically, **a write path never
omits a property to mean zero**: an omitted property re-imports as the class default, so the trunk
and the import payload state every authored value explicitly and the typed expansion stays
compare-only. (The editor build path holds this today; four mover/native emitters still test against
a constant and are filed on `board/inbox.md`.)
*(decision: typed effective-value compare, 2026-07-25 02:15 UTC — supersedes the class-default
contraction of 2026-07-25 00:36 UTC)*

**Committing is the user's own `git`** — uedctl reads/writes the T3D files and never wraps version
control. A level's durable identity is its **level name**.
*(decisions: sessions→git branches + `apply`→pure `level materialize` 2026-07-05; explicit-out /
name-as-identity 2026-06-23)*

The **native** build's fidelity bar is **byte-identity with UnrealEd's build of the same trunk** (the
`UModel` body + object tables, GUID/timestamps aside) — reached by porting the editor's incremental
`bspBrushCSG` pipeline in place of the point-in-solid classifier, and judged by materializing the
same trunk both ways and byte-diffing. Byte-identity is a fidelity target, not a functional one: the
build is already playable. *(decisions: byte-identity ⇒ incremental `bspBrushCSG` 2026-07-17;
spec `specs/bspbrushcsg-port.md`)*

## Safety: never irretrievably clobber

Authored work and on-disk work are never destroyed in a way that can't be recovered:

- **Guards** — `level materialize` refuses to overwrite an existing map file (opt in with
  `--overwrite`, exit 2 otherwise). Level *identity, rename, and history are git's job*, not a
  bespoke guard: a level is a branch, divergent edits reconcile through `git merge`, and there is
  no session-target matching to police (the old "nameless-vs-named session onto a target" guards
  are superseded with the store).
- **Pre-flight** — git repo + no-uncommitted-changes checks before a T3D-tree write; a per-target
  `flock` serializes concurrent writes to the same destination — including a **per-level flock on
  trunk saves**, which are **delta writes**: a save prunes only the actors its own process deleted,
  so concurrent disjoint edits (parallel `actor add` sessions) compose instead of overwriting each
  other. *(decision: trunk delta writes, 2026-07-18 08:08)*
- **Atomic writes** — map files swap atomically with a binary backup; trunk T3D writes are
  **per-actor atomic** (each `actor.t3d` lands via tmp + `os.replace`, rank before body), so a
  lock-free reader never sees a torn actor and a killed writer never wedges the level. **Git
  history is the recovery route** (there is no store snapshot to fall back on — the store is
  gone). *(decision: trunk delta writes, 2026-07-18)*

*(decisions: new-level guards 2026-06-23, superseded in part by git-branches-replace-sessions
2026-07-05 14:58)*

## Lighting, BSP and engine runtime state are build output, not authored state

Lightmaps and rebuilt BSP/geometry are **regenerable build output**, not authored state. Losing
them on a rebuild/re-materialize is a non-concern; they are never part of the level hash and never
block an operation.

The same rule governs **engine/editor-injected per-actor runtime fields** — the ones the editor's
export adds that the authored trunk never wrote (`Region`, `BasePos`/`BaseRot`, `bSelected`, the
mover `SavedPos`/`SavedRot` sentinels, …). They are never authored, never emitted, and never
compared; the canonical list is `normalize.COMPUTED_PROPS` and the taxonomy behind it is
`unrealed/t3d.md` "Authored-vs-computed field taxonomy". A field earns a place there only with
evidence that the engine really does overwrite it, and only when stripping it is right for **every**
class declaring that name — the set is keyed by bare name, so `Engine.TriggerLight`'s own
`SavedTrigger` is why that one name stays out. *(decisions: drop `--reapply`/`--continue`,
2026-06-23; materialize relight; mover `Saved*` are engine-stamped, 2026-07-25 03:07 UTC)*

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

## No back-compat cruft: uedctl is unreleased, so a removed thing is DELETED

uedctl has **never been released** — no external users, no pinned versions, no scripts in the wild.
So **nothing is kept for backward compatibility.** When a flag, verb, option value, output format,
or code path is removed or renamed, it is **deleted outright** in the same commit that introduces
the replacement; the new spelling is the only spelling. Explicitly forbidden: deprecated aliases,
no-op flags kept so old invocations still run, migration-error shims (a flag defined only to
`parser.error("X was renamed to Y")`), dual-format support kept to avoid re-writing callers, and
"the old way" branches lingering in code, tests, or docs.

Every such shim is permanent maintenance surface and a second thing to keep true in the docs —
the direct cause of the stale-help class of bug (`--png`'s help described behavior the code had
not had for months). An unreleased tool's one advantage is that it can simply change. **This is
superseded on release**, when a real deprecation policy replaces it.

*(decision: no back-compat cruft, 2026-07-24 21:57)*

## Explicit, discoverable, model-side

- Verbs compose; prefer a query verb whose output feeds another over per-command filter flags.
- Every flag/arg has a real `help=`; no Python exception reaches the user; errors name the
  offending value.
- Content reads/mutations are model-side (no editor); the editor is touched only to build/preview.
- **`find` vs `search` — two verbs by a naming RULE, never renamed into one.** **`find`** = a
  deterministic query over concrete **T3D-tree state** (actors, polys, brushes that exist in the
  trunk) — exact, produces a name/selector SET to pipe into a mutating verb (`actor find`, `brush poly
  find`). **`search`** = ranked / fuzzy **discovery over a catalog or corpus** (textures, the asset
  catalog, docs) — finding out *what exists* by relevance, not enumerating a known set (`texture
  search`; the future `catalog search` / `docs search`). Pick the verb by which of the two a new
  command is. *(decision: find-vs-search naming rule, 2026-07-25 00:43)*
- **No silent half-answers.** A command that cannot fully satisfy a request fails cleanly (exit 2,
  naming the offending value) rather than returning a partial result with a warning on stderr —
  stderr scrolls away and the caller believes the partial answer was complete. *(decision:
  `class show` degrade removal, 2026-07-24 21:58)*
- **A question about an actor's CLASS is answered from the class hierarchy, never from its name.**
  "Is this a Mover?" means "does its class descend from `Engine.Mover`?", resolved offline against
  the game's own `.u` packages — one shared predicate (`movers.is_mover`), no per-substrate class
  list, no name-suffix guess, and no optional heuristic fallback. The cost is accepted deliberately:
  every mover-aware verb (`mover key`, `level doctor`, `event graph`, `brush scale`/
  `apply-transform`/`intersect`/`deintersect`, `stash capture`, `level preview --native`, the native
  build) needs a resolvable package search path, and without one exits 2 naming the verb and what is
  missing rather than guessing. *(decision: schema-aware `is_mover` / "doctor may require config",
  2026-07-25 10:18)*

*(uedctl `CLAUDE.md` conventions; store-centric model)*
