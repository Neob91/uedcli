# The trunk and the editor

## What we want

The durable source of truth is the **git-tracked T3D trunk** — the per-actor directory tree at
`<maps-dir>/<level>/`, committed to the project's own git repo. The `.dx`/`.unr` **map file is a
build artifact**: never the merge unit, never the thing edited.

- Every `actor`/`brush`/`poly`/`vertex` read and mutation is **pure model-side compute** against
  the T3D — no `docker exec`, no `MAP EXPORT`, no liveness check during a content verb.
- **UnrealEd is not in the read/edit loop.** It is reached at exactly one seam,
  `level materialize` (which `level preview --game` calls internally to build the map it
  renders). Nothing else drives it.
- The LLM issues semantic by-name commands; T3D is internal plumbing.

**A level is edited on an ordinary git feature branch** and merged into trunk with `git merge`.
There is **no session, no session id, and no event-sourced session store** — git is the history
and the merge engine, and work in progress is simply an uncommitted or feature-branch state in
the project's own repo.

- **uedctl reads and writes the T3D files; git is the user's.** No branch, merge, or commit
  verbs — the surface never grows a VCS layer.
- **Per-actor files are what make this work.** One directory per actor (`actors/<name>/`) holding
  a constant-named `actor.t3d`, so disjoint edits touch disjoint files and auto-merge with zero
  conflict, while a same-actor edit conflicts cleanly on the changed property line. **Canonical
  emit is load-bearing, not incidental** — reordering two adjacent property lines is a semantic
  no-op that produces a *spurious* conflict, so the sorted/normalized emit is an invariant to
  enforce, never to assume.
- **CSG order is a per-actor sortable key** (`order_value`, LexoRank), not a shared `order` file —
  a shared file conflicts on every concurrent add. It is a **sidecar**, so a reorder never
  dirties the geometry diff. Effective order sorts by `(order_value, name)`; the tiebreak fires
  only on equal values, where what is required is determinism across clones, not meaning.
- **An actor's name lives only in its directory name** — stripped from the stored body and
  re-injected as `Name=` at materialize, so a directory name and a body `Name=` can never drift.
- The one bespoke store that survives is the **stash** (captured actor sets), and it is
  machine-local throwaway under the gitignored in-repo `.uedctl/` — not a session, not durable
  state.

**One T3D tree format across trunk, stash and prefab (INVARIANT).** All three on-disk T3D trees —
the git **trunk**, a machine-local **stash** entry, and a git-committed library **prefab** —
**MUST** use the same per-actor layout (`actors/<name>/{actor.t3d, order_value[, folder]
[, labels]}`; no shared `order` file), read and written through **ONE shared code path**. Per-tree
extras (a stash/prefab `meta.json`, a `packages` list) sit *beside* the shared `actors/` tree.
Folder and label sidecars are **persisted per member** in all three, at full trunk parity. Stash
and prefab do not strictly need merge-freedom; consistency — one format, not three divergent
parsers to keep in sync — is the requirement, and a git-committed prefab gets conflict-free merges
out of it anyway.

**Trunk saves are DELTA writes under a per-level flock**, detecting and refusing a same-actor
concurrent edit rather than losing it — see [`safety.md`](safety.md) for the full mechanism.

### `level import` — the inverse of materialize, and it needs no editor

A compiled `.dx`/`.unr` is decoded **natively** into a trunk or a stash
(`level import MAPFILE --tree level/NAME | stash/NAME`), so a retail level becomes queryable,
diffable and remixable. It is **editor-less and UCC-less**: UCC is the test oracle only, never a
runtime dependency. This is what widens "the editor is a build tool" into "the editor is not even
the ingest tool" — after import, the only remaining editor seam is `level materialize`.

- **Import creates the box and refuses to overwrite an existing one** without `--overwrite`,
  mirroring materialize's `--out` guard ([`safety.md`](safety.md)).
- **Fidelity is equivalence to `MAP EXPORT` through the canonical lens, not byte-identity.**
  Property ordering and default-omission are free to differ; enum names and all geometry must
  match.
- **UCC-text fidelity is produced at DECODE time** — structs member-stripped against the class
  default, floats at 6dp — so the schema-free hash path that backs materialize's verify is never
  touched.
- **Every actor is imported verbatim**, and class/texture refs are strictly qualified and
  validated before the write, so an off-path package fails the import rather than producing a
  trunk that will not re-materialize.

### Preview is two tiers behind one verb

`level preview` shares one batched pose grammar (`at:…;rot:…` / `look:@actor` / `orbit:…`):

- **`--game` (the DEFAULT) — the faithful tier.** Delivers the map into a warm per-user headless
  game container and renders truly-lit first-person stills: freezes the world, ghosts the player,
  poses the pawn per shot, and captures the engine's own frame over a uedctl-owned TCP link (VNC
  is dev-debug only). What the *player* sees — for hero shots and lighting judgment. It is the
  default because a misleading default feedback loop is worse than a slow one: the offline draft
  silently mis-renders overlapping-subtract geometry (doorways) and shows no lighting, meshes or
  sky.
- **`--native` — the opt-in offline draft tier.** No container and no editor: the Rust CSG core
  carves the trunk in-process and a software rasterizer renders freely-posed, textured perspective
  stills in seconds (flat-shaded v1; a `--lit` mode consuming the native lightmap bake follows).
  Permanently valuable for fast, docker-free, geometry-only iteration — not a stopgap.

The editor is the preview driver in **neither** tier; the editor-screenshot renderer is deleted.

## Rejected

- **The editor-centric model** — a live UnrealEd as the authoritative level holder, every read a
  `MAP EXPORT` and every write a console exec. It crashed mid-read even when idle, serialized all
  work through one container, and made a session expensive to start.
- **Keeping the bespoke event-sourced session store**, or squashing sessions into trunk commits.
  Git branches plus `git merge` give the same merge semantics for free — per-actor T3D files merge
  natively — and collapse `session.py`/`replay.py`/`merge.py`/`audit.py`/`ownership.py`. Sessions
  as a concept are dropped, not squashed.
- **uedctl wrapping git** (branch/merge verbs). The cleanest surface is files-only; git stays git,
  driven by the user.
- **Keeping `apply`'s 3-way reconcile and its dual `--to-map-file` / `--to-t3d-tree` modes.** Git
  is the merge engine now and the trunk *is* the T3D tree, so "apply to a tree" is just a commit;
  the build is map-file-only.
- **Reimplementing `session verify --deep` or `merge --sessions` on git.** No residual value:
  `git merge` *is* merge-sessions, and `git fsck` plus git's content-addressing cover
  corruption/tamper detection. The one genuinely new need — a "is the trunk well-formed?" lint —
  folds into `level doctor`.
- **Storing `order_value` inside `actor.t3d`** — would dirty the geometry diff on every reorder
  and couple ordering to geometry.
- **Tiebreaking equal order by insertion order** (nondeterministic — varies by merge order) or **by
  content hash** (shifts when the actor is edited). Both fail the determinism-and-stability the
  tiebreak needs.
- **Repeating the actor name as the `.t3d` filename and/or a body `Name=`** — redundant with the
  directory, and two more places to drift.
- **Keeping the old divergent stash/prefab formats** (a flat `actors/<name>.t3d` + shared `order`
  for stash; a single `Begin Map` blob + JSON sidecar for prefab). The minor simplicity of the flat
  forms does not outweigh one shared format.
- **Auto-converting old-format prefabs on read, or a `prefab migrate` verb.** Migration is a
  **hard cutover** — existing prefabs are re-captured — because a single format with zero lingering
  back-compat code is the whole point; reading an old-format prefab must fail with a clean,
  actionable exit-2 error, never a traceback.
- **Folder as placement-time-only** for stash/prefab members. Literal parity across all three trees
  is the consistency the invariant demands.
- **Bespoke `--level`/`--stash` flags on `level import`** instead of the uniform `--tree KIND/NAME`
  seam.
- **Literal byte-identity to `MAP EXPORT` text** as import's fidelity bar — property ordering and
  default-omission legitimately differ.
- **Filtering engine/boilerplate actors out on import** — every actor is imported verbatim.
- **Compare-time struct reconciliation** for import fidelity — it threads a schema dependency and
  the `Scale=(1,1,1)` trap into the guarded hash path; doing it at decode time keeps that path
  schema-free.
- **A lenient "import anyway, keep unresolved refs + warn" mode** — boarded as a follow-up, not
  adopted: it produces a trunk that will not re-materialize.
- **`level preview` as an interactive VNC handoff** (a per-level container plus a `level stop`
  verb, or a shared preview container). VNC is dev-debug, not the product, and every
  persistent-editor option needs a teardown/identity model that batched snapshots avoid entirely.
- **One shot per preview invocation, composed N times.** The boot is the expensive part; a
  caller-supplied list of poses renders in a single boot.
- **Keeping the editor as the preview driver.** The headless editor render cannot be freely posed
  — `CAMERA ALIGN` auto-frames from one canonical angle and a free pose never reaches the pixels —
  and editor-lit is not in-game baked lighting.
- **Putting previewing in another tool, or shelling out to its session/link.** Previewing is a
  uedctl authoring concern — uedctl owns the trunk, materialize, the level hash and the verb — and
  routing through another tool's session lifecycle couples the two.
- **Always re-materializing before a preview.** Materialize is the expensive step; a level-hash
  freshness check reuses an up-to-date build, and because the hash guarantees "current for the
  trunk", a stale build is never silently rendered.
- **A detached spectator/camera actor instead of posing the real pawn** — deferred, not adopted.
- **Native replacing the in-game preview entirely** (loses the faithful lit/sky/mesh ground truth),
  and **native as an interim tier to be demoted once `--game` lands** (the draft tier is
  permanently valuable).
- **Keeping the editor-screenshot backend as a third `--editor` option**, or leaving it the default
  until `--game` shipped — three codepaths, and it keeps the crash-prone editor in the hot loop
  longest.
- **A separate verb for one of the tiers** (`level render` / `level draft`) — two overlapping pose
  surfaces.
- **Rendering the materialized `.dx` for `--native`** — exact editor geometry, but it keeps docker
  and editor boots in the draft loop.
- **Keeping the old `TARGET[:MODE][=NAME]` auto-frame grammar and bolting pose flags onto it** —
  two grammars diverging between tiers; `look:@actor` covers the auto-frame use case.
- **Keeping `--native` as the default and merely documenting its blind spots.** An agent does not
  read caveats mid-loop; the misleading render is the problem.

## Refs

`../architecture.md` "Premise (git-native trunk)" · `../architecture.md` "The `LevelSource` seam
and `--tree`" · `../unrealed/t3d.md` ·
`../spikes/2026-07-01-git-merge-t3d-tree/` (per-actor merge viability; the shared-`order` blocker;
canonical emit load-bearing) · `../spikes/2026-07-05-git-merge-t3d-layout/` ·
`../spikes/2026-07-12-preview-pose-calibration/` (the editor render cannot be freely posed) ·
`../spikes/2026-07-06-level-preview-headless-shots/`
