# Safety — never irretrievably clobber

## What we want

Work is never destroyed in a way that cannot be recovered. What counts as *work* is narrow: the
git-tracked T3D trunk, a committed prefab, and any file a user put at a path by hand. A built map
file, a lightmap and a rebuilt BSP are regenerable build output and are not protected — losing them
costs a rebuild ([`materialize.md`](materialize.md)).

### Git is the recovery route — uedcli keeps no backups

There is no uedcli-side backup, snapshot, undo or history. The trunk is git-tracked, so recovery is
the user's own `git checkout` / `git reflog`, and `git fsck` plus git's content addressing give
corruption and tamper detection. uedcli reads and writes the T3D files and never wraps version control
([`trunk-and-editor.md`](trunk-and-editor.md)). Work that was never committed is protected only by the
mechanisms below, like any other uncommitted file.

### A destination that already exists is never written over silently

Every verb that **creates** something at a named destination refuses when that destination exists —
exit 2 naming it — and takes one explicit opt-in flag: `level materialize --out` / `--overwrite`,
`level import --tree KIND/NAME` / `--overwrite`, `stash capture --force`, `stash promote --force`.
Default-refuse plus an explicit opt-in is uniform, so no verb needs its own judgement about how
precious its destination is.

**Refuse and instruct; never guess.** Where uedcli finds state it does not understand — a corrupt box,
leftovers from a crashed write — it exits 2 naming the file and the recovery, rather than repairing or
overwriting it. `--force` over an already-corrupt stash or prefab box exits 2; recovery is removing the
directory by hand.

### Concurrent writers compose; they never silently destroy each other

Several agent sessions work one project at once, so every trunk write assumes a concurrent writer.

- **Trunk saves are delta writes.** A save writes only the actors whose stored body, rank, folder or
  labels differ from that process's own load snapshot, and prunes only the actors that process
  deleted. An actor directory the process never loaded belongs to someone else and is left untouched.
  The changed set is a content diff, never the verb's "touched" hint — a stale in-memory model
  rewritten wholesale resurrects a concurrently-deleted actor and reverts a concurrently-edited one.
- **Each save runs under a short per-level `flock`**; loads take no lock, so a long-running load-only
  verb does not block writers.
- **A lock lives beside the resource it guards, in a self-ignoring directory** — `<maps-dir>/.locks/`,
  `<catalog>/.locks/`. The lock domain matches the thing locked (two checkouts sharing one catalog
  serialize against each other), and lock litter can't be committed.
- **Actor names carry a random suffix**, so two processes — or two branches — adding at once never
  collide on a directory name.
- **Same-actor concurrent edits are detected and refused, not lost.** Under the flock, before writing,
  a save re-reads the current on-disk state of every actor in its changed-or-deleted set and compares
  against its load snapshot; any difference exits 2 naming the conflicting actors and writes nothing.
  It aborts, it does not merge — git is the merge engine, and the loser re-runs against fresh state
  with nothing stranded.

### Every write is atomic, and a killed writer leaves a readable tree

- **Per-actor atomicity.** Each actor's rank is written first, then its `actor.t3d`, each via a temp
  file plus `os.replace`; the organization sidecars land the same way. A lock-free reader never sees a
  torn actor, and a killed writer never wedges the level.
- **Self-healing.** An empty `actor.t3d` — the signature of a crashed pre-atomic write — is skipped on
  read, so a wedged trunk repairs itself on the next write. An empty or missing `order_value` on an
  actor that has a valid body is illegal: a named exit 2, never a silently front-sorting empty rank,
  and never auto-repaired.
- **Map files swap atomically** into place at the end of a build.

### Loss at the edges is a defect

- **Ingest never collapses duplicates.** User-supplied concatenated T3D is parsed as an ordered list
  preserving duplicate `Name=`s; each incoming actor is minted a distinct name, and the verb prints
  how many it added.
- **Level names are single-segment.** A dotted or nested name is rejected, because the maps-dir lock
  home is a self-ignoring `.locks/` and a level created inside it would be invisible to git.
- **Two actors sharing an `order_value` is warned, never blocked** — at `level doctor` and again at
  the build. Determinism holds through the `(order_value, name)` tiebreak; the warning surfaces that
  CSG precedence was settled by a random suffix rather than intent, and that a duplicate is the canary
  for any bug that sorts by `order_value` alone.

## Rejected

**Recovery and backups**
- **A uedcli-side backup of the build artifact** — the authored work is in git and the map file
  regenerates.
- **A `backups/` copy of the written T3D tree** — git already holds the prior committed state.
- **The name guards A/B and the level-name-matching guard family** — level identity, rename and
  history are git's job; a blunt "never write over an existing destination" covers the real risk with
  a fraction of the surface.
- **One `--allow-name-mismatch` covering both rename and writing onto an unrelated level** — one
  override meaning two different things.
- **Testing "shared ancestor" by raw actor-name intersection** — inert: the universal `LevelInfo`
  singleton and auto-allocated names made the overlap never empty.
- **Reimplementing the old store's deep-verify or a merge-sessions verb on git** — `git fsck`, content
  addressing and `git merge` subsume both; "is this trunk well-formed?" is a `level doctor` lint.
- **Auto-restoring leftovers from a crashed write** — refuse-and-instruct beats guessing.
- **Stating a repo/dirty pre-flight as unconditional when it is not.**

**Clobber guards**
- **Overwriting freely** (build output is regenerable) — an accidental overwrite of a hand-placed file
  is still worth preventing.
- **A strict refusal with no opt-in escape** — rebuilding to the same path is the inner loop.
- **Auto-repairing, or silently clobbering, a corrupt box under `--force`.**

**Concurrency**
- **Accepting the write race, or deferring the lock.**
- **A `flock` spanning load→save** — a load-only verb that then builds for minutes would block every
  writer on that level.
- **Staged-swap whole-tree writes** — file-level atomicity without delta semantics still loses
  concurrent adds.
- **Driving the changed set from the verb's own `touched` hint** rather than a content diff.
- **Same-actor last-writer-wins**, and **a three-way merge inside `save`** — the first loses
  acknowledged work; the second is git's job.
- **Bringing level creation under the per-level lock** — it refuses a populated level, so its actor
  set is disjoint from every concurrent editor's.
- **A project-derived lock home for a resource that is not project-scoped** — two checkouts sharing one
  catalog would each get their own lock domain and lose concurrent writes.
- **Guaranteeing distinct `order_value`s across branches** — needs a central allocator offline
  branches lack; the name tiebreak makes equal values harmless.
- **Hard-erroring on a duplicate `order_value`**, **auto-respreading them at build time**, or **a
  `--fix` verb** — nothing is broken, so a blocker is false urgency and an automatic rewrite is
  surprising.

**Atomicity and corruption**
- **Leaving `order_value` on a bare non-atomic write** while its sibling sidecars are atomic — the
  direct cause of a torn read whose empty rank sorts the actor to the front.
- **Tolerating an empty `order_value` as a valid rank.**
- **Auto-repairing a missing rank by minting one on read** — a read must not mutate.

**Loss at the edges**
- **Erroring on duplicate incoming names at ingest** — a batch of identically-named merlons is
  legitimate input; uniquifying is the right answer.
- **Uniquify-then-filter when capturing a named subset** — reintroduces the silent drop, because the
  bare-name filter then matches only the first.
- **Making the stored level's actor map a list** — the name-keyed map is correct everywhere a level is
  stored; the collapse is a defect only at the raw-ingest boundary.

## Refs

`../architecture.md` "The core write pattern" · `../architecture.md` "The `LevelSource` seam"
