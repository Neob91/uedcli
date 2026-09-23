# Persistent GUI editing sessions — spec

## Problem

`uedcli serve` today (`serve/app.py`, `serve/edits.py`, `serve/snapshots.py`) has no client/session
identity anywhere:

- Staged edits (`StagingStore`, currently only actor `Location`) are keyed by **level name only** —
  every browser tab pointed at the same level reads and mutates the same staged set. Two tabs
  silently collide.
- The server holds exactly **one level "hot" in memory** per process; `PUT /api/level` swaps it for
  every connected client.
- `POST /rebuild` solves the trunk only, never a client's staged-but-unsaved edits — so a staged
  actor move never shows solved (CSG/lighting) geometry, only the client-side visual override
  (`stagedOffsets`).
- Nothing survives a page refresh except staged edits themselves (written through to disk
  immediately on `POST /stage`) — there is no notion of "this browser tab" at all.

## Goals

- A **session**: a durable, uniquely-identified unit of GUI state, bound to one level for its whole
  life, holding its own staged edits and its own independently-solved geometry/lighting build.
- Survives a browser refresh **and** a server restart (durable, on disk).
- One session per browser tab, auto-created — gives multi-tab isolation with no explicit
  create/pick step in the common case.
- Two sessions on two different levels are both servable at once (the process holds a context per
  *active* level, not just one).
- Sessions never auto-expire. Only explicit close removes one.

## Non-goals (deferred, recorded so they aren't lost)

- **Undo/redo.** A from-session-start ledger, every entry independently undoable (even out of
  order), an undo itself becoming a new named ledger entry. Not designed here. One binding decision
  from this spec's own scope: **the ledger, once built, is session-bound** and lives exactly as long
  as its session does (including past Save) — this is why sessions have no auto-expiry (see
  "Cleanup", below) and is the reason this spec exists in its current shape rather than a lighter
  one. Needs its own board item before design starts. Naming note for whoever designs it:
  `direction/safety.md` already describes a distinct, not-yet-built "GUI audit-snapshot store" (the
  one exemption to "no backups," explicitly "an editor convenience, not a recovery mechanism"). Worth
  one line settling whether the future ledger *is* that store, supersedes it, or is a third thing —
  don't let the two designs drift into overlapping, differently-named versions of the same idea.
- **Fine-grained incremental CSG cache sharing** (two sessions differing by one moved brush share
  most of a solve, not just identical-content solves). Tracked in the existing
  `csg-checkpoint-resume-in-native-bsp-core-for` board item (extended with this spec's motivation);
  not scoped into this item. What this spec *does* get for free: the existing geometry/lighting
  split cache already shares the CSG-solve stage across sessions whenever their non-light actor
  content is byte-identical (e.g. sessions differing only by a light-only staged edit).
- **Staged edit types beyond `Location`.** Unchanged from today — this spec re-keys the existing
  staging mechanism to sessions, it doesn't widen what can be staged.

## Session identity & lifecycle

- Id: `uuid7` (matches the ephemeral-editor convention already used elsewhere, D5/D7 in
  `architecture.md`).
- Created for exactly one level; never switches levels (switching levels means switching sessions).
- The frontend carries the session id in the URL (`?session=<id>` on the app's root path). A tab
  with no session id in its URL auto-creates one and updates the URL via `history.replaceState`. A
  second tab with no session id gets its own new session. A session list/dropdown lets the user
  switch to (navigate to the URL of) any other existing session, across levels.
- No `beforeunload`/`sendBeacon` close-on-tab-close hook — unnecessary given no auto-expiry, and
  unreliable anyway.
- Any request scoped to a session updates that session's `last_active_at` — no separate heartbeat
  endpoint. (`last_active_at` is kept for display/sorting in the session list; it drives no cleanup,
  since there is none.) The write is throttled, not unconditional on every request — a 3s status
  poll from every open tab would otherwise mean an `index.json` rewrite roughly every 3 seconds per
  tab. A simple staleness gate (skip the write if the existing value is under some small threshold,
  e.g. 30s, old) keeps the field's purpose (rough recency for the session list) with a bounded write
  rate.
- **A `?session=<id>` that doesn't resolve to a real session** (a bookmark to one already closed, a
  typo, a session from a different project) is a **hard error, not auto-create.** This is different
  from no session id at all — an empty URL is the expected, normal fresh-tab case; a *present but
  invalid* id is unexpected state, and per this project's "refuse and instruct, never guess"
  convention (already applied to corrupt session files, above), unexpected state surfaces as an
  explicit error naming the id, not a silent fallback that papers over it. The frontend shows a
  "session not found" state; creating a new one from there is a deliberate action the user takes
  (a button/link), never something that happens on its own.
- **Closing the session your own tab is currently viewing** follows the same no-automatic-behavior
  rule, even though it's the direct result of an action you just took rather than unexpected state:
  after a successful `DELETE`, this tab lands on a neutral "session closed" state, not an
  automatically created replacement. Starting a new session from there is a separate, explicit
  button click.

### The same session, open in two windows — claim tokens, not a silent race

Not addressed until now: pasting a session's URL into a second window, duplicating a tab, or a
browser restoring old tabs can put the *same* session id live in two places at once — a different
situation from two sessions on one level (which this spec fully supports) and from a stale/invalid
id (handled above). Two real problems, both previously unaddressed:

- The trunk already guards against concurrent writers this way (`direction/safety.md`, "Concurrent
  writers compose"): before writing, it re-reads current on-disk state against what it loaded and
  refuses on any difference — never merges, never silently drops a side. Nothing in this spec gave a
  session's own `staged.json` the same protection, so two windows on the same session staging edits
  near-simultaneously is a genuine last-writer-wins race today.
- `LevelContext` tracks WS connections per level, and a session can now have more than one open
  (one per window) — any wording elsewhere that assumes "a session's WS connection" (singular) is
  wrong once this is accounted for.

**Fix: ownership by claim token, not detect-and-retry.** Two different sessions genuinely need to
coexist (the point of this whole feature); the *same* session in two windows is always an accident,
never an intended workflow — so instead of catching the race after it happens (the trunk's model,
built for two different authors who both have a legitimate claim), this forecloses it up front: only
one window is ever the write-authority for a session at a time.

- `GET /api/session/{id}` and `POST /api/level/{level}/sessions` (creation — nothing to supersede
  yet, so this trivially establishes the first claim) both mint a fresh `claim_token` and return it.
  **In-memory only, never written to `index.json`** — no `GET /api/sessions`/`GET
  /api/session/{id}` needs one (you can't need a token to obtain one; both stay pure reads).
- **Three states, not two, when a mutating call's token is checked**: no claim recorded for this
  session at all → establish this token as the claim and proceed (this is what makes a restart safe,
  below); claim recorded and it matches → proceed; claim recorded and it's a *different* token →
  refuse `409`. Absence of a claim is never treated the same as someone else's claim. **One claim
  record per session, one lookup** — the WS connect-time check and every mutating HTTP call's
  check-then-write both consult that same record; there's no separate bookkeeping for "the WS's view"
  versus "the HTTP endpoints' view" to drift apart.
- **The check and the write are one atomic step, under a per-session lock** — not the per-level write
  lock (that would over-serialize every other session on the level for no reason). Without this, a
  request that validated against the still-current token a moment ago could still land after a newer
  claim superseded it; every other race in this spec (`staging/blobs/` pruning, `build/cache/`
  eviction, above) gets this same treatment and this one is no different. A long-running Rebuild
  (~24s CPU) re-runs this check at write time, not just at request start — if superseded mid-solve,
  the result is dropped (logged, not written), the same "wasted work, not a correctness problem" the
  unthrottled-concurrency note above already accepts.
- **Restart safety follows directly from the three-state rule**: a restart wipes the whole in-memory
  claim map, so every session starts a fresh process with *no* claim recorded — the previously-sole,
  entirely legitimate window's next write hits the first state above and just quietly re-establishes
  itself, no error, no "opened elsewhere" message (which would be false — nothing else opened it, the
  server only forgot). One narrow, accepted residual: if the SAME session was open in two windows
  right before the restart (already the accident this whole feature treats it as), whichever one
  writes first after the restart becomes the claim again, possibly the one that had been superseded
  a moment before the crash. Not solved further — persisting claim ownership durably would reintroduce
  exactly the disk-write complexity this was deliberately kept in-memory to avoid, for an edge case
  inside an already-degenerate scenario (no data is at risk either way, only which of two identical
  windows keeps write access).
- **The WS connection carries the claim token too** (`WS /ws?session={id}&claim={token}`) — a stale
  token at connect time is refused the same way a stale token is refused on a write. When a new claim
  supersedes an old one, the server sends `{"type": "superseded"}` on the superseded connection
  *before* closing it — a real message, not a bare disconnect. **This is what the frontend actually
  watches for, not the close event itself**: an ordinary `onclose` (server restart, an idle proxy
  timeout, a laptop sleeping, a network blip) triggers the frontend's normal reconnect-with-backoff,
  which then just re-resolves the session and carries on — only a received `superseded` message shows
  the full-page takeover. **The `superseded` message is the fast path, not the only path**: if it's
  ever lost (a dropped connection before delivery), the window doesn't stay silently stale — its next
  mutating call gets the same `409` any stale token gets, and a `409` on a mutating call is *itself*
  always treated as a supersession, triggering the identical takeover, regardless of whether the WS
  message ever arrived. The WS message just makes the takeover instant instead of waiting for the
  next click:

  > **This session is now open in another window.** Reload to keep using it here.
  > `[Reload]`

  Reloading re-resolves the session fresh, mints a new claim, and — by the same rule — supersedes
  whichever window currently holds it. The cascade is intentional: whichever window last loaded
  always wins. Treating every WS close as "superseded" (an earlier draft of this section did) would
  have shown this takeover on every ordinary server restart — directly against this feature's own
  "survives a server restart" goal (`## Goals`) — since a restart closes every open connection
  process-wide with no way to tell it apart from a real supersession.
- Reads (`scene`/`atlas`/`lightmap`/`status`/`staged`) don't check the claim token — a superseded
  window can keep *viewing* harmlessly; only a write can lose data, so only writes are gated.
- `DELETE`'s WS-connection cleanup (`## API surface`, below) closes *every* open connection for that
  session, not "the" connection — plural, since two windows means two sockets.

## Storage layout

All still per-project, under `<project.root>/.uedcli/` (`config.state_subdir`), replacing the
current shapes outright (no migration — unreleased software, `conventions.md`). This leaves an
existing project's old `preview/`/`snapshots/`/`build/` trees orphaned on disk — nothing reads or
cleans them after this ships. Accepted, not fixed here: a one-time cleanup (or a `level doctor`-style
sweep) is a separate, later concern if it matters in practice.

```
sessions/<sid>/index.json    # {id, level, created_at, last_active_at, last_seen_generation}
sessions/<sid>/staged.json   # staged-edit manifest: {actor_name: {baseline_location, staged_location, blob_hash}}
sessions/<sid>/build.json    # build pin for this session: {geom_hash, light_hash}
staging/blobs/<hash[:2]>/<hash>              # content-addressed staged actor bodies — SHARED, unchanged
build/cache/v3/<level>/geometry/<geom_hash>.marshal              # CSG-solved, not-yet-lit — SHARED
build/cache/v3/<level>/lighting/<geom_hash>/<light_hash>.marshal # fully-lit scene — SHARED
build/pin/<level>/current.json                                  # PER-LEVEL pin: the build matching the level's last-SAVED trunk state
```

**`build/pin/<level>/current.json` — restoring, not discarding, `build_pin.py`'s original design.**
An earlier draft of this spec moved the pin entirely into `sessions/<sid>/build.json` and dropped
the per-level pointer outright. That was wrong: the two serve different purposes and both are
needed. The geometry/lighting build should behave exactly like a staged actor edit — session-scoped
while a session is actively editing, promoted somewhere durable on Save — **except** what it's
promoted *to* differs from a staged `Location`. A staged `Location` becomes part of the git-tracked
trunk on Save. A build is never git-tracked (it's regenerable build output, `direction/materialize.md`/
`safety.md`) — so on Save, the *session's own* `build.json` pin (its `geom_hash`/`light_hash`) is
instead copied into this per-level file, gitignored under `.uedcli/` like everything else here, one
per level rather than one per session. This is exactly `build_pin.py`'s pre-existing, already-
documented intent (*"Save (P2, doesn't exist yet) owns the write, atomically with its own trunk
write"*) — this spec's job is to wire that up, not replace it. A brand-new session with no staged
edits computes the exact same `geom_hash`/`light_hash` as the per-level pin on its first Rebuild
anyway (same content, same hash, by construction) — the per-level pin mainly exists so a freshly
opened session, or a non-GUI consumer (`level photo`, some other CLI tool) that has no notion of
sessions at all, can see "the level's current known-good build" without needing one to exist.
True cross-file atomicity with the trunk write isn't attempted (two separate files, two separate
atomic replaces) — instead, the pin write is sequenced strictly after a successful trunk write,
under the same per-level lock, so a crash between them leaves the trunk saved and the pin merely
stale (self-correcting on the next Rebuild), never corrupted.

`index.json` fields, pinned: `id` (the session's own `uuid7`, canonical string form — same value as
the directory name, kept in the file too so it round-trips from a bare read), `level` (level name,
string), `created_at`/`last_active_at` (ISO-8601 UTC — `stub_cache.py` already uses
`datetime.now(timezone.utc).isoformat()` elsewhere in the codebase, though with microseconds and a
`+00:00` offset rather than the `Z`-suffixed, no-microseconds shape proposed here
(`"2026-09-21T18:32:00Z"`); deliberately terser for a value only ever read back programmatically, not
a match to that precedent's exact format), `last_seen_generation` (int — the `LevelContext` generation
counter's value as of this session's last Load; see "API surface"'s `/status` entry for why this
lives here, server-side, rather than as frontend state). `staged.json`'s field names (`baseline_location`, `staged_location`,
`blob_hash`) are unchanged from today's `StagingStore` manifest — just re-homed. `build.json` and
`build/pin/<level>/current.json` both carry the same two fields `build_pin.py`'s `load_pointer`
already reads (`geom_hash`/`light_hash`) — that pointer has no writer yet ("Save... doesn't exist
yet", per its own docstring; this feature is what adds one, see "restoring, not discarding" below).
`build.json` drops the `level` key the per-level file's path already encodes, for the same reason
`index.json`/`staged.json` don't repeat it either (recorded once, in `index.json`).

Why this split: `sessions/<sid>/` holds everything that is genuinely per-session and non-shared —
closing a session is one directory removal. `staging/blobs/` and `build/cache/` stay outside any
session's own directory because they are deliberately *shared*, content-addressed stores (the actual
dedup mechanism) — a blob or a cache entry can be referenced by more than one session at once.

`v3/` is `preview_cache.py`'s existing `_CACHE_VERSION`, moved from a filename prefix
(`scenegeo3__...`) to a path segment — a version bump becomes a directory-level sweep instead of a
filename-prefix scan. `build/cache/<level>/lighting/<geom_hash>/<light_hash>.marshal` nests lit
entries under their geometry hash, since a lit scene's cache key is genuinely the pair
`(geom_hash, light_hash)`, not either hash alone. `geom_hash` keeps its existing render-rule suffix
(visibility/include_meshes/include_movers) unchanged.

This is a full rename+restructure of the current `preview/`/`snapshots/`/`build/` (pin) trees:
`preview_cache.py` → `build_cache.py` (module rename; `load_geometry`/`store_geometry`/
`load_scene`/`store_scene` keep their names — only the path-construction helpers
`_compose_stem`/`_dir`/`_prune_prefix`/`_sweep_old_versions` change to build the new nested paths).
`snapshots.py`'s `StagingStore` is re-keyed from `.uedcli/snapshots/staged/<level>.json` to
`sessions/<sid>/staged.json` plus the shared `staging/blobs/`. `build_pin.py` gains a second,
session-scoped pointer path (`sessions/<sid>/build.json`, dropping the `level` parameter there — a
session's level is fixed and already recorded in `index.json`) alongside its existing per-level one,
which moves from `build/<level>/current.json` to `build/pin/<level>/current.json` (nested under
`build/` for the same reason `cache/` is — see "Build cache & dedup" — but otherwise unchanged: same
shape, same read-only-until-Save semantics, per the "restoring, not discarding" note above).

Naming note: `architecture.md` already uses "session store" for an unrelated, already-deleted
pre-git-native concept (per its own "Git-native migration complete" note). This spec's "session"
is a different, current thing — worth one disambiguating line wherever this lands in `architecture.md`
proper, so a reader doesn't conflate the two.

### `staging/blobs/` pruning — reference-aware, per `direction/safety.md`

`direction/safety.md` documents the GUI's on-disk snapshot store as the one exemption to "uedcli
keeps no backups," and states it should be LRU-pruned. Applied here: a blob is **live** (never
evicted, regardless of age) as long as *any* session's `staged.json` still names its hash as a
`blob_hash`. A blob becomes an eviction **candidate** only once no session references it any longer
— which happens when that session's staged edit for the actor changes to a different value, or the
session Saves, Discards, or is closed. Among candidates, eviction is LRU (oldest-accessed first,
`atime`-based, same mechanism as `build_cache`'s eviction) once `staging/blobs/` exceeds its own
budget (`staging_blobs_max_bytes`, `<project.root>/uedcli.toml` — see "Build cache & dedup" above for
why it lives there, not `~/.uedcli/config.toml`). The eviction check itself runs opportunistically on
every `StagingStore.stage()` call — a cheap current-size check every time, with the full
candidate-scan-and-evict routine only actually invoked when that check finds the budget exceeded —
not a periodic background sweep. Same trigger shape `build_cache`'s eviction uses (below).

Liveness is computed by scanning `sessions/*/staged.json` for the hash at eviction-check time — no
separate refcount index is maintained (self-healing: a crashed write can't leave a stale refcount
behind, since there's no refcount to go stale; matches the project's existing preference for deriving
truth from the manifest of record rather than a secondary index). This never touches session data
itself and never contradicts "sessions never auto-expire" (`## Cleanup`, below) — a live session's own
`staged.json` is what keeps its blobs alive in the first place; pruning only ever removes content
nothing points to anymore.

**Race, and the fix**: today's `StagingStore.stage()` checks whether a blob already exists, and only
writes it if not — that check-then-write is two separate steps, and so is eviction's
scan-then-delete. Interleaved without a lock, eviction could delete a blob between another session's
existence check and its own manifest write, leaving that session's `staged.json` pointing at nothing.
`uedcli serve` is one process, so this needs no file lock (unlike the trunk's per-level `flock`,
which guards against *separate processes*) — an in-process `threading.Lock` closes the race, but its
scope matters: **the O(sessions) liveness scan itself runs unlocked**, only the brief re-check+delete
per candidate is locked. A stale (slightly-old) scan is safe by construction — it can only under-count
references (treat a blob as still-live when a session just freed it, deferring its eviction a cycle),
never over-count one into deletion — so building the candidate list doesn't need to hold the lock at
all. Only right before deleting an individual candidate does it briefly take the lock, re-verify no
`staged.json` references that hash, and delete — and that re-verify must be a **full, fresh
O(sessions) scan for that one hash, entirely inside the lock**, never a cheaper check against the
earlier (now-stale) candidate-building scan's own data. That's the detail the whole argument rests
on: the stale scan alone can transiently over-count a blob as unreferenced (miss a session's
brand-new reference), which is fine on its own — what actually prevents a wrongful delete is that
this fresh re-check and `StagingStore.stage()`'s own write (existence-check + write + manifest
update) share the same lock, so they can never interleave: either the write fully lands before the
re-check (which then sees it and aborts the delete) or the delete fully completes first (and the
write, finding the blob gone, just rewrites it). A re-check that reused any part of the stale scan
would reopen exactly the race this design exists to close. This bounds a staging write's wait on this lock to
"one candidate's re-check+delete," not "however long the whole session set takes to scan" — which
matters because, with no session auto-expiry (`## Cleanup`), the number of `sessions/*/staged.json`
files to scan only grows over a project's life; a lock held for the full scan would make every
staging write progressively slower as sessions accumulate, an `app.py`-wide stall (the lock also
serializes `StagingStore.stage()` across every level, not just the one being pruned) that would only
get worse with age.

**Atomic writes, per `direction/safety.md`'s "every write is atomic"**: `sessions/<sid>/index.json`,
`staged.json`, and `build.json` all get temp-file-then-`os.replace` writes, same convention the trunk
and `preview_cache.py`'s `_store` already use. Worth noting as a pre-existing gap this touches:
`StagingStore.stage`/`clear_actor`/`discard` today write their manifest with a bare
`manifest_path.write_text(...)`, not atomically — since this spec re-keys that exact write path to
`sessions/<sid>/staged.json`, the re-key is also where that gap gets closed, not left as-is.

**Corrupt-file read posture — refuse-and-instruct, the default going forward for this feature's own
files.** `index.json`, `staged.json`, and `build.json` all hold real state a session cannot recover
by regenerating — `staged.json` in particular is unsaved work, closer to `safety.md`'s definition of
"work" than to a cache. A corrupt or malformed read on any of the three exits/errors naming the file
and the recovery (delete the session, or the one file, and start over) — never a silent degrade to
some default, and never a guess at a partial repair. This deliberately does **not** extend to
`build/cache/*.marshal` or `build/pin/<level>/current.json`: both are pure regenerable build output
in `safety.md`'s own sense (a corrupt one just means "rebuild"), and `preview_cache.py`/`build_pin.py`
already treat a corrupt read there as an ordinary cache miss — that existing behavior is unchanged,
not overridden by this new default. Two different postures for two different classes of file, drawn
along the same "work vs. regenerable build output" line `safety.md` already uses, not a blanket rule
applied without regard to what's actually at risk.

## Multi-level concurrent serving

`serve/app.py`'s current single set of holder-cells (`_current_level`, `_trunk_ref`,
`_geometry_ref`, `_payload_ref`, `_scene_inputs_ref`, `_generation`, `_changes_available`,
`_build_status`, one `TrunkWatcher`) becomes a `dict[level_name, LevelContext]`, one entry per
*level* — not per session. Any number of sessions can point at the same level (a session is bound to
one level; many sessions may share it), and every session on a given level shares that level's one
`LevelContext`, created lazily on first session request touching that level.

**`LevelContext` is *not* where a solved build lives.** It holds only what's genuinely safe to share
across every session on that level: the loaded trunk (`_trunk_ref`), the generation counter and
`_changes_available` flag, the `TrunkWatcher`, the set of WS connections subscribed to that level, and
a lock serializing writes to that level (mirroring the trunk's own per-level `flock`,
`direction/safety.md`). It drops `_geometry_ref`/`_payload_ref`/`_scene_inputs_ref`/`_build_status`
outright — those describe one *solved build*, and two sessions on the same level can have different
staged edits, so they need different solved geometry; a per-level shared slot can't hold that. A
session's solved build instead lives only in the shared, hash-addressed `build/cache/` store (below)
plus that session's own `build.json` pointer into it — never in `LevelContext`. The one exception is
the *level's* own pin (`build/pin/<level>/current.json`, written on Save — see "Storage layout"'s
"restoring, not discarding" note) — that one genuinely is level-scoped, not session-scoped, since it
represents the saved trunk's build, not any particular session's in-progress one; it's a plain file
read/written on demand, not something `LevelContext` needs to hold open in memory.

A level's context can be dropped once none of its sessions have an open WS connection for a while (a
memory optimization; on-disk session state is unaffected either way — it's already durable).

A fresh tab with no `?session=` in its URL needs a level to create a session against.
`uedcli serve <level>` already takes a level argument at startup today — that stays the default level
for a bare URL with no session id; picking a different level means using the session list/dropdown
(which can also create a new session for a different level), not a `?level=` URL parameter.

**Rebuild concurrency is deliberately unthrottled.** Once solving works on independent copies
(`## Build cache & dedup`, below), nothing stops N sessions from Rebuilding at the same instant — no
process-wide solve lock, no cap on simultaneous CSG solves. Considered and rejected: a throttle would
protect against many concurrent ~24s-CPU solves competing for resources, but this is a local,
single-user tool where that many simultaneous Rebuilds is not a realistic pattern — a deliberate "no"
rather than an omission.

## Build cache & dedup

A session's Rebuild solves `trunk + that session's own staged overlay` and stores/loads through the
existing `build_cache` (renamed `preview_cache`) hash/store path unchanged in mechanism — the hash is
a pure function of resulting actor content, so identical effective trees (whether from the same
session across rebuilds, or two different sessions) converge on the same cache entry automatically.
This module is also used by the CLI (`level photo --native`, via `preview_native.py`), unaffected by
the session concept — it stays keyed by level + content hash either way, never by session.

**"Trunk + staged overlay" is built on a copy, never on `LevelContext`'s shared `_trunk_ref`.**
`_trunk_ref` is shared by every session on that level; applying one session's staged edits by
mutating it in place — the pattern `edits.save_staged` already uses on the trunk itself — would
corrupt what every *other* session on that level sees, and race a sibling session's own concurrent
Rebuild doing the same. The overlay only touches the actors a session has actually staged, so the
copy is a shallow one — replace just those entries in a copied actor dict, not a deep copy of the
whole `Level`. This is also what makes concurrent Rebuilds across sessions safe with no lock at all
(`## Multi-level concurrent serving`'s "unthrottled" note, above): each solves against its own
independent copy, and the shared cache they write to is content-addressed, so there's nothing for
two concurrent solves to corrupt in each other.

**An in-memory cache sits in front of `build_cache` too, keyed by the same content hash** — without
one, every `/scene`/`/atlas`/`/lightmap` call would re-run the expensive per-actor class-resolution
work from disk on every request, reintroducing a real, already-fixed-once regression (`app.py`'s own
comment on this: a WanChai-scale request went from ~28s warm to ~0.06s once this was added the first
time). Shared across every session and level, not one per session — the whole point of hashing by
content is that identical results are reusable regardless of who asked. Sized the same way the byte
budgets are: a reasonable starting default (e.g. keep the last several deserialized payloads
in-process), flagged as adjustable, not measured.

**Prerequisite this feature's own scope now includes**: `serve/scene.py`'s `_BuiltGeometry` already
has `geom_hash`/`light_hash` fields, but they're always `None` today — `build_scene` computes both
internally (`_scene_hashes`) but doesn't thread them out to its caller yet (`_BuiltGeometry`'s own
docstring flags this as open, "OQ1"). A session's `build.json` pin needs real values here, so this
feature's implementation also wires `build_scene`'s already-computed hashes through into
`_BuiltGeometry`'s existing fields and updates the call sites that construct/consume it — not a new
dataclass, just populating the one that already has the right shape. Scoped as part of this item's
own plan, not a separate prerequisite to sequence around.

What changes: eviction moves from the current "keep newest 8 by mtime, prefix-wide" scheme to a real
byte-budget LRU, reusing the atime-based LRU pattern already used elsewhere in the codebase
(`schema_cache.evict_lru`, `pkg_cache.evict_lru`) rather than inventing a third eviction style — with
one real difference from both: those walk one flat directory (`os.scandir`), while `build/cache/`'s
new `v3/<level>/{geometry,lighting}/` layout is nested, so the eviction walk needs to recurse (or
maintain a flat side-index) rather than reuse `evict_lru`'s scan verbatim.

The budget is a **project setting**, not a per-user one — `schema_cache`/`pkg_cache`'s own real
precedent is an env var + hardcoded default, not TOML at all, and `~/.uedcli/config.toml`'s schema is
closed to everything but `games` (`direction/projects-and-config.md`: "nothing else lives in that
file"; `config.py`'s `_reject_unknown` enforces it). Since the budget is inherently per-project
anyway, it belongs in the tracked `<project.root>/uedcli.toml`, alongside `maps`/`prefabs`/`catalog`,
as two new flat keys matching that file's existing style (no nested table there today):

```toml
build_cache_max_bytes = 4_000_000_000
staging_blobs_max_bytes = 500_000_000
```

`Project`'s dataclass (`config.py`) gains these two fields, defaulting when absent — a plain
default-if-missing, not the directory-path resolution `_project_subdir` does for `maps`/`prefabs`/
`catalog`. Both new keys also need adding to `_PROJECT_KEYS` (`config.py`) — a separate set from the
`Project` dataclass, used by `load_project()`'s own `_reject_unknown(raw, _PROJECT_KEYS, toml_path)`;
missing this would reject the keys in their new home the same way they were rejected in their old
one. **Adding them to `_PROJECT_KEYS` alone is not enough**: `load_project()`'s own constructor call
only forwards the fields it explicitly reads off `raw` today (`game`/`paths`/`catalog`/`prefabs`/
`maps`/`source`) — that call also needs `raw.get("build_cache_max_bytes")`/
`raw.get("staging_blobs_max_bytes")` added, or a value the user actually sets in `uedcli.toml` stops
being rejected but is silently dropped, never reaching the `Project` object. Default `4_000_000_000` (4 GB) for
`build_cache_max_bytes` is a proposed starting point, not a measured one — no existing per-entry size
data was found to derive it from; flagging it as adjustable rather than presenting it as load-bearing.
`staging_blobs_max_bytes`'s default (`500_000_000`, 500 MB) carries the identical caveat — a proposed
starting point, not measured, smaller than the build-cache default because staged actor bodies (text)
are inherently much smaller per-entry than solved geometry/lighting payloads. Both budgets are
**per-project** caps: they bound `<project.root>/.uedcli/build/cache/`'s and `.uedcli/staging/blobs/`'s
own total size respectively, checked independently for each project. Both are validated as positive
integers on load (a zero or negative value is a `ConfigError` naming the offending value), matching
`config.py`'s existing validation precedent for its other optional keys — a byte budget of `0` reads
as "always empty," `-1` as garbage input, neither a sensible thing to silently accept.

Separately, since these are genuinely new *project* config keys, `direction/projects-and-config.md`'s
own documented key table (currently `game`/`paths`/`maps`/`prefabs`/`catalog`) needs updating to list
them too — a `direction/` edit, which per `CLAUDE.md` needs the owner's explicit yes at
implementation time, not assumed here.

**Eviction is reference-aware, the same way `staging/blobs/` pruning is (above) — never evict a
cache entry that's *current* for anything.** A `build/cache/` entry is live as long as either (a) any
session's `build.json` currently pins it, or (b) any level's `build/pin/<level>/current.json` pins
it. It becomes an eviction candidate only once neither is true. Same mechanics as the blob-store
fix: the O(sessions + levels) liveness scan runs unlocked, and only the brief per-candidate
re-check+delete (a fresh, full re-scan of *both* reference kinds for that one hash, entirely inside
the lock) is locked — for the identical reason: a lock held for the whole scan would stall
concurrent Rebuilds across every level, and would only get slower as sessions accumulate. Closing a
session never deletes cache entries by itself (they may still be referenced by another session or by
the level's own pin); only becoming genuinely unreferenced, and then the size budget, evicts them.

The budget stays **project-wide**, not split per level — matching today's actual eviction scope
(`_prune_prefix` already globs across the whole `.uedcli/preview/` directory, not per level) rather
than introducing a new per-level fairness boundary nothing asked for. A busy level's frequent
rebuilds can still consume more of the shared budget than a quiet level's, same as today.

## Cleanup

No auto-expiry, full stop — not even for a session with zero staged edits. A session persists until
the user explicitly closes it (session list UI or a CLI verb), which discards its staged edits and
(once built) its undo ledger. This is a deliberate choice, not an oversight: it's what lets the
future undo ledger survive past Save without the two features fighting over when a session may be
reaped. Accepted tradeoff: disk usage grows with however many sessions are ever created and never
explicitly closed — on the user to manage via the session list, the same as any other
nothing-auto-deletes system (git branches, browser tabs).

## API surface

- `POST /api/level/{level}/sessions` — create a session for `{level}`. No request body. `201`,
  body `{"id": "<uuid7>", "level": "<level>", "created_at": "<iso8601>", "claim_token": "<token>"}` —
  see the claim-token note under "Session identity & lifecycle": creating a session establishes its
  first claim, same as resolving one does.
- `GET /api/sessions` — `200`, body `{"sessions": [{"id", "level", "created_at",
  "last_active_at"}, ...]}` (same per-session shape as create's response, plus `last_active_at`). No
  filtering/pagination — session counts are expected to stay small (local, single-user), so the
  client filters/sorts for the dropdown itself.
- `GET /api/session/{id}` — `200` with that same shape plus a fresh `claim_token` (see the
  claim-token note under "Session identity & lifecycle" — this call is what mints one, on every
  fresh resolution, superseding whatever token existed before), or `404` if the id doesn't exist.
- `DELETE /api/session/{id}` — explicit close: removes the entire `sessions/<sid>/` directory
  (`index.json` included, not just `staged.json`/`build.json` — a closed session shouldn't keep
  showing up in `GET /api/sessions` or resolving `GET /api/session/{id}`) and, once built, its undo
  ledger; does **not** touch shared `staging/blobs/` or `build/cache/` entries (they may be
  referenced elsewhere). Also drops *every* open WS connection for that session from its
  `LevelContext`'s connection set — plural; the same session can be open in more than one window
  (`## Session identity & lifecycle`'s claim-token note, above) — nothing should keep listening on
  behalf of a session that no longer exists. A mutation, so it needs a valid `claim_token` like any
  other (a superseded window can't close the session out from under the one that superseded it).
  Destructive, so it also follows the project's "never irretrievably clobber" convention
  (`direction/safety.md`): if `staged.json` is non-empty, `DELETE` refuses with `409` unless called
  as `DELETE /api/session/{id}?force=true` — the frontend's close button shows a confirmation before
  ever sending `force=true`. `204` on success, `404` if the id doesn't exist. An in-flight Rebuild for that session
  isn't cancelled — it's left to finish, and its eventual write to `sessions/<sid>/build.json` needs
  to tolerate the directory already being gone (log and drop the result, not raise) rather than
  surface as an unhandled error in a background thread.
- The existing per-level verbs move to per-session, same request/response shapes as today, just
  re-addressed: `GET /api/session/{id}/scene|atlas|lightmap`,
  `POST /api/session/{id}/load|rebuild|stage|discard|save`, `GET /api/session/{id}/staged`. The
  `POST` verbs all mutate session state (`load` updates `last_seen_generation`; `rebuild` writes
  `build.json`; `stage`/`discard`/`save` write `staged.json`) and so all require the caller's current
  `claim_token`, refusing `409` on a stale one — see the claim-token note above. The `GET` verbs are
  reads and check nothing.
- `GET /api/session/{id}/status` — replaces today's `/api/level/{level}/status`. Body:
  `{"changes_available": bool, "geometry_pinned": bool, "build_status": ...}`. The last two are
  genuinely per-session (each session has its own `build.json`/in-flight Rebuild state) and carry
  over unchanged in shape. `changes_available` can no longer be a bare level-shared flag — polled
  every ~3s per open tab, it drove Session A's Load silently clearing Session B's banner in an
  earlier draft, even though B never loaded anything. Fixed by comparing `LevelContext`'s own
  generation counter against a new `last_seen_generation` field in *this session's* `index.json`,
  bumped to the level's current generation whenever this session Loads. Server-side and durable (not
  client/React state) on purpose — per the frontend-stays-dumb principle this spec already leans on
  elsewhere (the frontend renders what the server says, it doesn't track its own copy of "have I seen
  this" and risk it going stale or resetting on refresh).
- `WS /ws?session={id}&claim={token}` — the session id still scopes which level's changes a
  connection is told about (unchanged broadcast mechanism, now filtered by the connecting session's
  own level instead of being process-global), and `{"type": "changes_available", "level": ...}` is
  unchanged. The `claim` param is new (see the claim-token note above): a stale claim is refused at
  connect time, and an already-open connection receives `{"type": "superseded"}` immediately before
  the server closes it when a newer claim supersedes it — the frontend's one and only trigger for the
  "open in another window" takeover, never the close event by itself.

Save's conflict-check semantics (compare current trunk `Location` against the baseline captured at
stage time) are unchanged — only re-keyed from `(level)` to `(session)`. Two sessions independently
staging edits to the same actor is possible and already handled by the existing per-actor
conflict-detection path; nothing new needed there.

**`GET /api/health`'s current shape is stale under this design** — it returns `{"status", "level"}`,
naming the one level the whole process used to hold "hot." There's no longer a single current level
to report. Drop the `level` field; `{"status": "ok"}` alone is enough for a liveness check (a client
that wants to know which levels are actually active already has `GET /api/sessions` for that).

**Save also promotes the session's build pin.** After a successful trunk write, `POST
/api/session/{id}/save` copies that session's current `build.json` (`geom_hash`/`light_hash`) into
`build/pin/<level>/current.json` — see "Storage layout"'s "restoring, not discarding" note. Sequenced
strictly after the trunk write, under the same per-level lock; a session with no pin yet (never
Rebuilt) has nothing to promote and leaves the level's existing pin as-is.

## Frontend changes

`App.tsx` gains a session id (from the URL) instead of assuming a single implicit global state; a
session-list dropdown (new, small component) lets the user resume/switch. Everything else
(`stagedNames`, `stagedOffsets`, the Load/Rebuild flow, `ConflictResolver`) is unchanged in shape,
just addressed through `/api/session/{id}/...` instead of `/api/level/{level}/...`.

**The existing in-place level-switch machinery is removed, not reused.** `App.tsx`'s
`handleSwitchLevel`/`levelSwitching`/`levelSwitchError` state and its `PUT /api/level` call, plus
`LevelPicker.tsx`, exist to switch which level the *same* implicit state points at — a concept this
spec deletes ("switching levels means switching sessions," `## Session identity & lifecycle`).
`PUT /api/level` and `GET /api/levels` have no place in the new API surface. The session-list
dropdown replaces `LevelPicker.tsx` outright; picking a different session/level is navigation (to
that session's URL), not an in-place mutation of shared client state.
