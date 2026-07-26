# Safety — never irretrievably clobber

## What we want

Work is never destroyed in a way that cannot be recovered. What counts as *work* is narrow
and deliberate: the git-tracked T3D trunk, a committed prefab, and any file a user put at a
path by hand. A built map file, a lightmap and a rebuilt BSP are **regenerable build output**
and are deliberately NOT protected — losing them costs a rebuild, so no mechanism here spends
anything on them (see [`materialize.md`](materialize.md)).

### Git is the recovery route — uedcli keeps no backups

There is no uedcli-side backup file, snapshot, undo or history. The trunk is git-tracked, so
recovery is the user's own `git checkout` / `git reflog`, and `git fsck` plus git's content
addressing give corruption and tamper detection for free. uedcli reads and writes the T3D
files and never wraps version control ([`trunk-and-editor.md`](trunk-and-editor.md)).

The consequence is accepted and stated plainly: work that was never committed is protected
only by the mechanisms below, exactly like any other uncommitted file in the repo.

### A destination that already exists is never written over silently

Every verb that **creates** something at a named destination refuses when that destination
already exists — exit 2 naming it — and takes one explicit opt-in flag to proceed anyway:
`level materialize --out` / `--overwrite`, `level import --tree KIND/NAME` / `--overwrite`,
`stash capture --force`, `stash promote --force`. Default-refuse plus an explicit opt-in is
uniform across the tool, so no verb needs its own judgement about how precious its
destination is.

**Refuse and instruct; never guess.** Where uedcli finds state it does not understand — a
corrupt box, leftovers from a crashed write — it exits 2 naming the file and the recovery
instead of repairing it or writing over it. Concretely, `--force` over an *already-corrupt*
stash or prefab box exits 2; recovery is removing the directory by hand. Silently clobbering
corruption is worse than naming it.

### Concurrent writers compose; they never silently destroy each other

Several agent sessions work one project at the same time, so every trunk write assumes a
concurrent writer.

- **Trunk saves are DELTA writes.** A save writes only the actors whose stored body, rank,
  folder or labels differ from **that process's own load snapshot**, and prunes only the
  actors that process itself deleted. An actor directory the process never loaded belongs to
  someone else and is left untouched. The changed set is a **content diff**, never the verb's
  own "touched" hint — a hint is only as good as the verb reporting it, and a stale in-memory
  model rewritten wholesale resurrects a concurrently-deleted actor and reverts a
  concurrently-edited one.
- **Each save runs under a short per-level `flock`**; loads take no lock, because a
  long-running load-only verb would otherwise block every writer on the level.
- **A lock lives beside the resource it guards, in a self-ignoring directory** —
  `<maps-dir>/.locks/`, `<catalog>/.locks/`. The lock domain then matches the thing locked
  (two checkouts sharing one catalog serialize against each other), and lock litter can never
  be committed from a tracked dir.
- **Actor names carry a random suffix**, so two processes — or two branches — adding at once
  never collide on a directory name.
- **Same-actor concurrent edits are DETECTED and REFUSED, not lost.** Under the flock, before
  writing, a save re-reads the current on-disk state of every actor in its own changed-or-
  deleted set and compares it against its load snapshot; any difference exits 2 naming the
  conflicting actors and writes nothing. It **aborts, it does not merge** — git is the merge
  engine, and a uedcli invocation is stateless, so the loser simply re-runs against fresh
  state with nothing stranded.

### Every write is atomic, and a killed writer leaves a readable tree

- **Per-actor atomicity.** Each actor's rank is written first, then its `actor.t3d`, each via
  a temp file plus `os.replace`; the organization sidecars land the same way. A lock-free
  reader therefore never sees a torn actor, and a killed writer never wedges the level.
- **Self-healing.** An empty `actor.t3d` — the signature of a crashed pre-atomic write — is
  skipped on read, so an already-wedged trunk repairs itself on the next write. An empty or
  missing `order_value` on an actor that *has* a valid body is **illegal**: a named exit 2,
  never a silently front-sorting empty rank, and never auto-repaired by minting a fresh rank.
- **Map files swap atomically** into place at the end of a build.

### Silent loss at the edges is a defect, never an ergonomic

- **Ingest never collapses duplicates.** User-supplied concatenated T3D is parsed as an
  ordered list that preserves duplicate `Name=`s; each incoming actor is minted a distinct
  name, and the verb prints how many it added, so a collapse could not pass unnoticed.
- **Level names are single-segment.** A dotted or nested name is rejected, because the
  maps-dir lock home is a self-ignoring `.locks/` and a level created inside it would be
  invisible to git.
- **Two actors sharing an `order_value` is warned, never blocked** — at `level doctor` and
  again at the build that ships the map. Determinism holds through the `(order_value, name)`
  tiebreak, so nothing is broken; what is worth surfacing is that the CSG precedence there
  was settled by a random suffix rather than by intent, and that a duplicate is the canary
  for any bug that sorts by `order_value` alone.

## Rejected

**Recovery and backups**

- **A uedcli-side backup of the build artifact** (the pre-write binary copy) — the authored
  work is in git and the map file regenerates, so the backup guarded the one thing that did
  not need guarding.
- **A `backups/` copy of the written T3D tree** — git already holds the prior committed state.
- **The name guards A/B** (a nameless session may only first-write a new target; a named one
  refuses a target whose recorded name differs) and the whole level-name-matching guard
  family — level identity, rename and history are git's job, and a blunt "never write over an
  existing destination" covers the real risk with a fraction of the surface.
- **One `--allow-name-mismatch` covering both the rename case and writing onto an unrelated
  level** — a single override meaning two very different things is a foot-gun.
- **Testing "shared ancestor" by raw actor-name intersection** — inert in practice: the
  universal `LevelInfo` singleton and deterministically auto-allocated names made the overlap
  never empty, so the guard never fired.
- **Reimplementing the old store's deep-verify, or a merge-sessions verb, on top of git** —
  `git fsck`, content addressing and `git merge` subsume both; the one genuinely new need,
  "is this trunk well-formed?", is a `level doctor` lint instead.
- **Auto-restoring leftovers from a crashed write** — refuse-and-instruct beats guessing at
  what the user meant.
- **Stating a repo/dirty pre-flight as unconditional when it is not** — an overstated
  guarantee is worse than none.

**Clobber guards**

- **Overwriting freely** (no clobber protection at all, on the grounds that build output is
  regenerable) — an accidental overwrite of a file the user placed by hand is still worth
  preventing.
- **A strict refusal with no opt-in escape** — rebuilding to the same path is the inner loop;
  forcing a manual delete every time is friction on the most-run command.
- **Auto-repairing, or silently clobbering, a corrupt box under `--force`.**

**Concurrency**

- **Accepting the write race, or deferring the lock** — never-irretrievably-clobber is the
  overriding concern.
- **A `flock` spanning load→save** — a load-only verb that then builds for minutes would block
  every writer on that level, and read-only verbs need no serializing at all.
- **Staged-swap whole-tree writes** — file-level atomicity without delta semantics still
  loses concurrent adds, because the destruction happens at the model level, not the file
  level.
- **Driving the changed set from the verb's own `touched` hint** rather than a content diff.
- **Accepting and documenting same-actor last-writer-wins**, and **a three-way merge inside
  `save`** — the first loses acknowledged work silently; the second is git's job.
- **Bringing level creation under the per-level lock** — it refuses a populated level, so its
  actor set is disjoint from every concurrent editor's by construction.
- **A project-derived lock home for a resource that is not project-scoped** (and a per-user
  fallback when no project is found) — two checkouts sharing one catalog would each get their
  own lock domain and silently lose concurrent writes.
- **Guaranteeing distinct `order_value`s across branches** — that needs a central allocator
  offline branches do not have, and the name tiebreak makes equal values harmless anyway.
- **Hard-erroring on a duplicate `order_value`**, **silently auto-respreading them at build
  time**, or **adding a `--fix` verb** — nothing is actually broken, so a blocker is false
  urgency, an automatic rewrite is surprising, and a dedicated verb is more surface than a
  warning needs.

**Atomicity and corruption**

- **Leaving `order_value` on a bare non-atomic write** while its sibling sidecars are atomic
  — the direct cause of a torn read whose empty rank sorts the actor to the front.
- **Tolerating an empty `order_value` as a valid rank.**
- **Auto-repairing a missing rank by minting one on read** — a read must not mutate, and
  renumbering hides the crash that caused it.

**Silent loss at the edges**

- **Erroring on duplicate incoming names at ingest** — a batch of identically-named merlons is
  legitimate, wanted input; uniquifying is the right answer, not a rejection.
- **Uniquify-then-filter when capturing a named subset** — it reintroduces the silent drop the
  ingest fix exists to kill, because the bare-name filter then matches only the first.
- **Making the stored level's actor map a list** — the name-keyed map is correct everywhere a
  level is stored; the collapse is a defect only at the raw-ingest boundary, so that is where
  it is fixed.

## Refs

`../architecture.md` "The core write pattern" · `../architecture.md` "The `LevelSource` seam"
