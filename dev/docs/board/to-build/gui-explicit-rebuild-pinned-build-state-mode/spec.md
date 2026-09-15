# Spec — GUI explicit rebuild

Written for a reader with no prior context. Records the owner's design decisions from a 2026-09-14
conversation, in the order they were settled.

## Goal and non-goals

**Goal.** Match UnrealEd's own build model: BSP geometry + lighting are a **built artifact that
persists exactly as it was until explicitly rebuilt** — never silently recomputed because the trunk
changed underneath it. Editing a brush (in UnrealEd, or here: adding/subtracting one through the
GUI) shows immediately as a rough, unlit ("fullbright") preview of its own raw shape; it does not
affect the real, lit geometry until a Rebuild.

**Two independent axes, revised (2026-09-14, second pass) — do not conflate them:**
1. **The trunk/actor view** — what actors exist, their properties, their raw shapes. Updated ONLY
   by an explicit **Load** action for any change AFTER a level is opened, never automatically, even
   in P1 (no staging exists yet, but the owner wants no silent auto-refresh regardless — "it might
   make it harder to understand what happened"). **Exception, resolving an open question from the
   first review pass: opening a level for the first time in a given `serve` process IS an implicit,
   automatic Load** — there is nothing to "pull in over" yet, exactly like opening a map file in
   UnrealEd loads it without asking "load changes?". Only a *subsequent* external change, after the
   level is already open, needs an explicit Load. In P2, Load can conflict with staged-but-unsaved
   edits (see `questions/p2-editing-and-concurrency-model.md`) — same warn/name/confirm treatment as
   Save-time conflicts, just triggered the other direction (external change meeting a local staged
   edit, instead of a local Save meeting an external change). Sprite resolution
   (`resolve_actor_sprites`) belongs to this axis, not the geometry axis below — it's actor-derived,
   no CSG/lighting solve involved, so a freshly-Loaded point actor should show its icon immediately
   without waiting for a Rebuild (matches the scene-cache spec's `_LoadedTrunk` slot, which owns
   `sprite_table`/`actor_sprites` for exactly this reason).
2. **The solved-geometry build** — CSG + lighting. Updated ONLY by an explicit **Rebuild** action.
   Loading fresh trunk data does **not** itself trigger a rebuild — the two are independent user
   actions. A first pass of this spec wrongly folded "see new/changed actors" and "get solved
   geometry for them" into one pinned-hash mechanism; this revision splits them. A `Load` can leave
   the viewport showing actors the current pinned geometry build knows nothing about yet (e.g. a
   newly-loaded brush with no BSP solve behind it) — that gap IS the real UnrealEd feel this whole
   item exists to reproduce, not a bug to hide.

**Why.** Two owner concerns converge here: (1) auto-rebuilding on every trunk change would keep the
CPU busy continuously during an active AI editing session even when nobody's watching the GUI; (2)
independent of that, the owner wants the GUI to look and behave like a UED22-built level, and
UED22's own workflow is explicit-rebuild — this isn't a compromise invented to solve (1), it's the
actual target behavior, and it happens to also solve (1) for free (nothing ever solves without a
user asking).

**Non-goals.**
- Not a general P2 editing spec. This item covers ONLY the rebuild/render-state model; the staging
  buffer, Save mechanics, and Save-time conflict handling for human edits are already ruled on
  separately (`dev/docs/board/to-plan/uedcli-human-gui/questions/p2-editing-and-concurrency-model.md`)
  and are not repeated here.
- Not the render-mode-picker UI itself (wireframe/unlit/flat/lit toggle) — that's already planned in
  Slice 2 of the main GUI spec. This item only adds the availability GATING rule (see below); the
  picker's own build is unaffected in scope.
- The "flat" mode's exact definition is a separate open item (`uedcli-human-gui/spec.md`, "Also
  open") — irrelevant to this spec either way, since the gating rule here applies uniformly to
  "any mode that needs solved geometry," regardless of what each mode turns out to mean exactly.

## Design

### 0. Relationship to the scene-cache spec — read this first

`dev/docs/board/to-spec/uedcli-serve-share-one-in-process-scene-cache/spec.md` (a separate,
narrower fix, in review in parallel) introduces two in-process cache slots: `_LoadedTrunk`
(trunk/actor data) and `_BuiltGeometry` (CSG+lighting output), both currently cleared together by
the `TrunkWatcher` for THAT spec's own P1-only scope. **This spec supersedes only the trigger, not
the shape**: build this item by changing WHO clears/populates each slot —
`_trunk_ref` becomes Load-owned, `_geometry_ref` becomes Rebuild-owned (backed by the in-memory pin
described below) — and by making the watcher's settle callback stop clearing either slot, instead
only flipping the "changes available" signal section 2 describes. Do not reintroduce a third,
different state-holding mechanism; extend that spec's dataclasses and holders in place.

### 1. Persisted build state — reuse `preview_cache`, don't invent a new store

The CSG-solved, lit geometry is already persisted exactly the way this needs: `preview_cache.py`'s
`store_geometry`/`store_scene`/`load_geometry`/`load_scene`, keyed by `(project, level_name,
geom_hash12, light_hash12)` — content-addressed, compressed, already binary, already git-untracked
(under the project's `.uedcli/` state dir). **No new storage format is needed.**

**Eviction caveat (found in review): the on-disk pointer can outlive its own cache entry.**
`store_geometry`/`store_scene` prune to the newest `PREVIEW_KEEP = 8` entries per prefix
(`preview_cache.py`'s `_prune_prefix`), and that glob is **not scoped per level** — every level in
the project competes for the same 8 slots, so ordinary Rebuild activity on a *different* level can
evict the blob a saved pointer names. Resolution: **do not try to defeat the LRU** (exempting pinned
hashes from pruning is a real cross-cutting change to a shared, project-wide cache — out of scope
here). Instead, treat a pointer that resolves to a missing cache entry exactly like "never built":
fall back to wireframe-only, surface a clear status ("previous build no longer cached — Rebuild to
restore it"), and let the user re-solve. This matches `preview_cache`'s own existing philosophy
elsewhere in this codebase (a cache miss is always survivable by recomputing, never an error) — it
is a performance cache, not a source of truth; git plus the trunk remain that.

What's missing is a **pin**: today, `preview_native.build_scene()` always recomputes the CURRENT
trunk's `(geom_hash, light_hash)` and looks that up — so it always reflects the live trunk (once the
scene-cache fix elsewhere lands, "always" means "once per settled trunk state," but still
automatic). To get UnrealEd's actual behavior, the GUI needs to remember which hash pair was **last
explicitly built** and keep rendering that, regardless of what the live trunk's hash currently is.

A small pointer per level, e.g. `.uedcli/build/<level>/current.json`: `{"geom_hash": "...",
"light_hash": "..."}`. This is NOT a new binary geometry format — it's a tiny pointer into the
existing `preview_cache` store.

**When this pointer touches disk — ruled 2026-09-14, mirrors UnrealEd exactly.** In UnrealEd,
Rebuild updates the in-memory Model; the BSP only reaches disk when you Save the map file. Same
split here:
- **In-memory, on every Rebuild**: the running `serve` process always holds the current pin in
  memory and serves `/scene`/`/atlas`/`/lightmap` from it immediately — a Rebuild is instantly
  visible in the session that triggered it, no disk round-trip needed for that.
- **On disk, ONLY via Save, bundled atomically with whatever trunk write Save performs.** The
  pointer file must never be written outside a Save — writing it independently would let it name a
  hash that reflects staged-but-unsaved edits (P2) or, at any time, a pending Rebuild nobody has
  committed to yet. If the process restarts before a Save, that in-memory pin is gone; the on-disk
  pointer (if any) still names the last genuinely SAVED build, never a discarded one. P1 has no Save
  action at all (read-only) — under this rule, a P1 Rebuild's pin is memory-only for the life of
  that `serve` process and is never written to disk; a restart loses the pin (not the expensive
  solve itself — `preview_cache`'s own blobs are unaffected and still likely a cache hit), and the
  user just clicks Rebuild again. Acceptable: P1 never has "saved-but-then-lost" content to protect
  against in the first place.
- Absent on-disk pointer (never saved with a build attached, or a fresh checkout) means "never
  built" for a freshly started process (see mode gating below) — it does NOT mean the in-memory pin
  is empty on an already-running process that has Rebuilt since starting.

### 2. The Load action (trunk/actor view — separate from Rebuild)

The existing `TrunkWatcher` still detects a settled trunk change, but it no longer auto-pushes a
silent reload. Instead it flips a "changes available" signal the client shows as a banner/badge —
the "The local files have changed — load changes?" idea from earlier in the same conversation,
confirmed still wanted, just now precisely scoped: **Load only refreshes the trunk/actor view
(axis 1 in the Goal above)**. It does **not** call Rebuild and does **not** touch the pinned
geom/light hash (axis 2 above, mechanism in section 3 below).

- **P1 (no staging):** Load is a plain refresh — re-read the trunk, re-derive `SceneActor`s, show
  them. No conflict is possible (nothing local to conflict with).
- **P2 (staging exists):** Load can collide with a staged-but-unsaved local edit to the same actor.
  This needs the same warn/name-the-actors/require-confirm treatment already ruled for Save-time
  conflicts (`questions/p2-editing-and-concurrency-model.md`) — record it there as the symmetric
  case, don't re-derive a second conflict model here.

### 3. The Rebuild action (solved geometry — separate from Load)

A new `serve` action (an HTTP route, e.g. `POST /api/level/{level}/rebuild`) that:
1. Reads the CURRENT trunk/actor view (whatever section 2's Load last put there — NOT necessarily
   the live on-disk trunk if a Load hasn't happened since the last external change).
2. Computes its `(geom_hash, light_hash)` and runs `build_scene()` against it (a `preview_cache` hit
   if nothing's changed since some other trigger already solved this exact state; a real solve
   otherwise).
3. Updates the **in-memory** pin to this new hash pair — overwriting it, never accumulating. **One
   current build, not a history of past builds** — `preview_cache`'s own dedup/LRU is an
   implementation-level disk substrate underneath this, not a user-visible version history; the pin
   always names exactly one build, same as UnrealEd has exactly one current BSP, not a stack of past
   ones. Does NOT touch the on-disk pointer file (section 1) — that only happens at Save.
4. The GUI's `/scene`/`/atlas`/`/lightmap` routes, from then on, read `preview_cache` at the
   **pinned** hash — until the next Rebuild. A Load (section 2) never changes this pin by itself.

Save (P2, already ruled elsewhere) additionally writes the CURRENT in-memory pin to the on-disk
pointer file, atomically alongside the trunk write it's already performing for the staged edits —
one persisted unit, never the pointer alone.

### 4. Render-mode gating and bootstrap (fixes a review-found gap: this used to gate on the wrong thing)

The render-mode picker (Slice 2, main spec) offers wireframe / textured-unlit / flat / textured+lit.
**The gating condition is "no in-memory geometry pin currently held" — not "no on-disk pointer
file."** Stated as a file check, the gate could never unlock in P1 (P1 never writes the file at
all, per section 1 — see "Revision history"). Stated correctly:

- At Load (including the automatic initial one, section "Two independent axes" above): if an
  on-disk pointer exists (a previous Save left one), populate the in-memory pin FROM it immediately
  — a `preview_cache` lookup, likely a hit — so opening a previously-saved level shows its already-
  built geometry right away, exactly like opening a `.dx`/`.unr` file shows its already-baked BSP.
  If the pointer is missing, or resolves to an evicted cache entry (section 1's eviction caveat),
  the in-memory pin starts/stays empty.
- While the in-memory pin is empty, only wireframe is selectable — the other three modes all need
  solved BSP + baked lighting, which doesn't exist until a Rebuild populates the pin. Wireframe
  alone renders straight from the trunk's authored brush shapes, no solve needed.
- **This supersedes the main spec's "cold-open instant wireframe... then swap to solved+lit when
  the (~24s) solve finishes" automatic-background-solve behavior** (`uedcli-human-gui/spec.md`,
  "Loading & performance") for a level with no saved build — that text predates this ruling and
  described an automatic initial solve, which this spec's whole point rules out. Corrected
  behavior: cold-open shows wireframe (from the automatic initial Load) and **stays** wireframe-only
  until the user explicitly Rebuilds — no background auto-solve, matching real UnrealEd (a brand
  new or freshly-imported level shows nothing built until you explicitly Build, ever). A level that
  already has a saved build (the bullet above) skips this entirely and opens already-lit.

### 5. Fullbright overlay — scoped to GUI-made edits only, not general trunk changes

Originally discussed as "any new/changed brush shows fullbright until rebuilt," then narrowed:
**the fullbright overlay applies ONLY to a brush added or CSG-modified through the GUI's own editing
action** (P2 — human editing in the GUI), not to arbitrary external trunk changes (an AI verb, or
any other process editing the trunk). Reasoning: the GUI already knows exactly what it just did in
that case (no diffing needed — it performed the add/subtract itself), whereas a change from
elsewhere is exactly the kind of thing the audit/diff machinery (Slice 3) exists to show properly,
not approximate with an unlit guess.

**Consequence: this piece is entirely P2-scoped.** P1 is read-only — there is no GUI-originated
add/subtract for it to overlay. Sections 1–4 above (pinned build, Load, Rebuild, mode gating) have
no such dependency and can be built against P1 as it exists today; section 5 cannot be built (there
is nothing to test it against) until P2 editing exists. This section of the spec is a forward
record of the decision, not something to implement now.

## What is open / left to planning

- Where in `serve`'s route surface the rebuild/load actions and "changes available"/"pin empty"
  status get exposed (dedicated status fields, a new endpoint each, a WS event vs. poll) —
  planning-time detail, not a design fork.
- Whether the "rebuild available" / "changes available" indicators are passive badges or an
  interactive banner ("The local files have changed — load changes?" / "Rebuild available") —
  cosmetic, planning-time.
- Section 5 (fullbright overlay) is explicitly deferred to whenever P2 editing is actually planned —
  not designed further here since there's nothing to design against yet (no GUI edit action exists
  to define "what did the GUI just add/change" from).
- Done: `uedcli-human-gui/spec.md` (`to-plan/`, already reviewed) now carries "Superseded" notes on
  its "File watcher → live reload" bullet and its "Loading & performance" cold-open/re-solve text,
  each pointing here — a planner reading only the to-plan spec won't be misled by the now-stale
  automatic-refresh/auto-solve description (review finding).

## Testing (sections 1–4 only — section 5 has no test surface yet)

- A test that with no on-disk pointer AND no in-memory pin (a freshly started process), `/scene` (or
  whatever route serves geometry) returns a wireframe-only-capable response / the mode-gating signal
  reflects "wire only."
- A test that `POST /rebuild` updates the in-memory pin (a subsequent `/scene` request serves from
  it) but does **not** write the on-disk pointer file — the file must be byte-for-byte unchanged (or
  still absent) immediately after a rebuild with no Save.
- A test that a trunk change AFTER a rebuild does NOT change what `/scene` serves (still the pinned
  hash) until another explicit rebuild.
- A test that two rebuilds in a row, with no trunk change between them, are a `preview_cache` hit
  (no wasted re-solve) — same content hash, same cached entry.
- A test that Load and Rebuild are independent: after a Load pulls in a new actor, the pinned
  geometry hash is UNCHANGED (the new actor has no solved geometry yet) until a separate Rebuild.
- A test that Rebuild alone (no Load first) rebuilds against whatever the CURRENT view already
  is — it does not implicitly pull fresh trunk data first.
- A test that a successful Rebuild UNLOCKS the other three render modes (review finding — the
  original test list only ever checked the locked state, which would pass even if the gate never
  reopened).
- A test that opening a level with an existing on-disk pointer (a prior Save) populates the
  in-memory pin from it immediately and unlocks all modes on the very first `/scene` fetch — no
  Rebuild needed.
- A test that a pointer resolving to an evicted `preview_cache` entry degrades to "no build"
  (wireframe-only, clear status) rather than erroring.
- **(P2, once Save exists)** A test that Save writes the on-disk pointer file to match whatever the
  in-memory pin was at Save time, atomically with the trunk write — and that a process restart
  immediately after (no further Rebuild) still serves the SAVED build, not "no build."
- **(P2, once Save exists)** A test that a Rebuild with no subsequent Save leaves the on-disk pointer
  file untouched, and a simulated restart (fresh process, same on-disk state) falls back to whatever
  the last SAVED pointer was (or "no build" if none) — the discarded Rebuild leaves no trace on disk.

## Revision history

- First adversarial review of this spec (2026-09-14, joint with the scene-cache spec) found: (A1)
  the mode-gating condition checked the on-disk pointer file, which P1 never writes, so modes could
  never unlock in P1 — self-contradicting section 1's own in-memory-pin rule; (A2) undefined
  behavior for a Rebuild before any Load had ever happened, and unclear interaction with the main
  spec's automatic cold-open solve; (A3) the on-disk pointer's durability claim ignored
  `preview_cache`'s actual project-wide, 8-entry LRU eviction; (A4) no test ever exercised the mode
  gate re-opening after a successful Rebuild; (B) the scene-cache spec's single-atomic-snapshot
  cache and this spec's independent-axes model were incompatible as literally written, in either
  build order — not a small clarifying note. This revision: makes the initial per-process Load
  automatic (resolving A2 and the cold-open tension), restates the gate as "no in-memory pin held"
  with the pin bootstrapped from the on-disk pointer at Load time (resolving A1), adds graceful
  degradation for an evicted pointer instead of trying to defeat the LRU (resolving A3), adds the
  gate-reopening and bootstrap-from-disk tests (resolving A4), adds an explicit section 0 stating
  this spec supersedes only the scene-cache spec's invalidation TRIGGER (not its `_LoadedTrunk`/
  `_BuiltGeometry` shape, which the scene-cache spec's own revision now anticipates), assigns
  `resolve_actor_sprites` to the Load axis, and adds "Superseded" notes to the already-reviewed main
  GUI spec so it doesn't read as still describing automatic reload/solve.
