# The trunk and the editor

## What we want

The durable source of truth is the **git-tracked T3D trunk** — the per-actor directory tree at
`<maps-dir>/<level>/`, committed to the project's git repo. The `.dx`/`.unr` **map file is a build
artifact**: never the merge unit, never edited.

- Every `actor`/`brush`/`poly`/`vertex` read and mutation is **model-side compute** against the T3D
  — no `docker exec`, no `MAP EXPORT`, no liveness check during a content verb.
- **UnrealEd is not in the read/edit loop.** It is reached at one seam, `level materialize` (which
  `level photo --game` calls internally). Nothing else drives it.
- The LLM issues semantic by-name commands; T3D is internal plumbing.

**A level is edited on an ordinary git feature branch** and merged into trunk with `git merge`. There
is no session and no session store — git is the history and merge engine. uedcli reads and writes the
T3D files; it grows no branch/merge/commit verbs.

- **Per-actor files make merges work.** One directory per actor (`actors/<name>/`) holding a
  constant-named `actor.t3d`, so disjoint edits touch disjoint files and auto-merge, while a
  same-actor edit conflicts cleanly on the changed property line. Canonical emit is enforced:
  reordering two adjacent property lines is a semantic no-op that would otherwise produce a spurious
  conflict.
- **CSG order is a per-actor sortable key** (`order_value`, LexoRank), a sidecar not a shared `order`
  file (which would conflict on every concurrent add), so a reorder never dirties the geometry diff.
  Effective order sorts by `(order_value, name)`; the name tiebreak fires only on equal values, for
  determinism across clones.
- **An actor's name lives only in its directory name** — stripped from the stored body, re-injected
  as `Name=` at materialize, so directory name and body can't drift.
- The one bespoke store that survives is the **stash** (captured actor sets), machine-local throwaway
  under the gitignored `.uedcli/`.

**One T3D tree format across trunk, stash and prefab (INVARIANT).** All three use the same per-actor
layout (`actors/<name>/{actor.t3d, order_value[, folder][, labels]}`; no shared `order` file), read
and written through **one shared code path**. Per-tree extras (a stash/prefab `meta.json`, a
`packages` list) sit beside the shared `actors/` tree. Folder and label sidecars are persisted per
member in all three.

**Trunk saves are delta writes under a per-level flock**, detecting and refusing a same-actor
concurrent edit rather than losing it — see [`safety.md`](safety.md).

### `level import` — the inverse of materialize, editor-less

A compiled `.dx`/`.unr` is decoded **natively** into a trunk or stash (`level import MAPFILE --tree
level/NAME | stash/NAME`), so a retail level becomes queryable, diffable and remixable. It uses no
editor and no UCC (UCC is the test oracle only). After import the only remaining editor seam is
`level materialize`.

- **Import creates the box and refuses to overwrite** an existing one without `--overwrite`,
  mirroring materialize's `--out` guard ([`safety.md`](safety.md)).
- **Fidelity is equivalence to `MAP EXPORT` through the canonical lens, not byte-identity.** Property
  ordering and default-omission may differ; enum names and all geometry must match.
- **UCC-text fidelity is produced at decode time** (structs member-stripped against the class
  default, floats at 6dp), so the schema-free hash path backing materialize's verify is untouched.
- **Every actor is imported verbatim**; class/texture refs are qualified and validated before the
  write, so an off-path package fails the import rather than producing a trunk that won't
  re-materialize.

### Preview is two tiers behind one verb

`level photo` shares one batched pose grammar (`at:…;rot:…` / `look:@actor` / `orbit:…`):

- **`--game` (the default) — faithful.** Delivers the map into a warm per-user headless game
  container and renders truly-lit first-person stills: freezes the world, ghosts the player, poses
  the pawn per shot, captures the engine's frame over a uedcli-owned TCP link (VNC is dev-debug
  only). What the player sees — for hero shots and lighting judgment.
- **`--native` — the opt-in offline draft.** No container, no editor: the Rust CSG core carves the
  trunk in-process and a software rasterizer renders freely-posed textured stills in seconds
  (flat-shaded v1; a `--lit` mode consuming the native lightmap bake follows). Fast, docker-free,
  geometry-only iteration.

The tradeoff in making `--game` the default: it pays a container + game boot every loop, but
`--native` mis-renders overlapping-subtract geometry (doorways) and shows no lighting, meshes or sky
— a fast picture an agent may read as correct. Use `--native` when iterating on geometry, `--game`
when lighting or the final look matters.

The editor drives neither tier; the editor-screenshot renderer is deleted.

## Rejected

- **The editor-centric model** — a live UnrealEd as the authoritative level holder, every read a
  `MAP EXPORT`, every write a console exec. It crashed mid-read even when idle and serialized all
  work through one container.
- **A bespoke event-sourced session store**, or squashing sessions into trunk commits — git branches
  plus `git merge` give the same merge semantics for free.
- **uedcli wrapping git** (branch/merge verbs) — git stays git, driven by the user.
- **Storing `order_value` inside `actor.t3d`** — dirties the geometry diff on every reorder.
- **Tiebreaking equal order by insertion order** (nondeterministic) or **by content hash** (shifts
  when the actor is edited).
- **Repeating the actor name as the `.t3d` filename or a body `Name=`** — two more places to drift.
- **Divergent stash/prefab formats** (flat `actors/<name>.t3d` + shared `order`; a single `Begin Map`
  blob + JSON sidecar) — one shared format instead.
- **Auto-converting old-format prefabs on read, or a `prefab migrate` verb** — migration is a hard
  cutover (re-capture); reading an old-format prefab fails with a clean exit-2 error.
- **Folder as placement-time-only** for stash/prefab members — literal parity across all three trees.
- **Bespoke `--level`/`--stash` flags on `level import`** instead of the uniform `--tree KIND/NAME`.
- **Byte-identity to `MAP EXPORT` text** as import's fidelity bar — ordering and default-omission
  legitimately differ.
- **Filtering engine/boilerplate actors out on import** — every actor is imported verbatim.
- **Compare-time struct reconciliation** for import fidelity — done at decode time to keep the hash
  path schema-free.
- **A lenient "import anyway, keep unresolved refs + warn" mode** — boarded, not adopted: produces a
  trunk that won't re-materialize.
- **`level photo` as an interactive VNC handoff** — VNC is dev-debug; batched snapshots avoid a
  teardown/identity model.
- **One shot per photo invocation** — the boot is the expensive part; a pose list renders in one
  boot.
- **The editor as the photo driver** — the headless editor render can't be freely posed
  (`CAMERA ALIGN` auto-frames from one angle) and editor-lit isn't in-game baked lighting.
- **Shooting in another tool or its session** — uedcli owns the trunk, materialize, the hash and
  the verb.
- **Always re-materializing before a photo** — a level-hash freshness check reuses an up-to-date
  build.
- **Native replacing the in-game photo** (loses the lit/sky/mesh ground truth), or **native as an
  interim tier to be demoted** once `--game` lands — the draft tier stays.
- **Keeping `--native` as the default and merely documenting its blind spots** — an agent does not
  read caveats mid-loop, so a misleading render is the problem; `--game` is the default and `--native`
  an explicit opt-in.
- **A detached spectator/camera actor instead of posing the real pawn** — deferred, not adopted.
- **Keeping the editor-screenshot backend as a third `--editor` option.**
- **A separate verb per tier** (`level render`/`level draft`) — two overlapping pose surfaces.
- **Rendering the materialized `.dx` for `--native`** — keeps docker and editor boots in the draft
  loop.
- **The old `TARGET[:MODE][=NAME]` auto-frame grammar** — `look:@actor` covers the auto-frame case.

## Refs

`../architecture.md` "Premise (git-native trunk)" · "The `LevelSource` seam and `--tree`" ·
`../unrealed/t3d.md` · `../spikes/2026-07-01-git-merge-t3d-tree/` ·
`../spikes/2026-07-05-git-merge-t3d-layout/` · `../spikes/2026-07-12-preview-pose-calibration/` ·
`../spikes/2026-07-06-level-preview-headless-shots/`
