# Spec — share one in-process scene cache across `/scene`, `/atlas`, `/lightmap`

Written for a reader with no prior context on this problem. **Revised after adversarial review** —
see "Revision history" at the end for what changed and why.

## Goal and non-goals

**Goal.** One page load of the `uedcli serve` GUI fires three requests: `GET /scene`, `GET /atlas`,
`GET /lightmap`. Today each independently re-reads and re-parses the whole trunk from disk, then
independently calls `build_scene()` and `resolve_actor_sprites()` again, even when the trunk hasn't
changed since the last request. Fix: compute all of that **once per settled trunk state**, as one
atomically-published snapshot, and have all three routes read from it.

**Why now.** Measured on the real WanChai level (2288 actors) behind a Cloudflare quick tunnel:
`/atlas` alone took **2m44s**, exceeding the tunnel's ~100s timeout and failing the page load
outright. This is a real user-facing failure, not a latency nice-to-have. (Review note: this
specific number was NOT fully decomposed — see "What this fix does and does not claim to fix"
below. The redundant-work diagnosis is independently code-verified regardless.)

**Non-goals.**
- Not touching the CSG solve or lighting bake themselves — those are correctly cached today via
  `preview_cache` (disk, content-hash-keyed) and are not what this fix targets.
- No disk-tier cache for this specific fix. The trunk is exactly what edits (AI or, later, human)
  target, so this cache's value is intra-session only (between now and the next edit) — see
  `rationale/` note below. In-process, gone on restart, is correct and sufficient. (A *separate*,
  larger, explicit-rebuild-model spec is being scoped independently — not this one.)
- No change to `TrunkWatcher`'s debounce behavior.
- No change to what data any endpoint returns — same JSON shapes, same content.
- No level-picker support. `create_app(project, level)` fixes one level for the app's lifetime
  today (`app.py`'s own docstring); this fix keeps that assumption but — per review finding —
  makes it an *enforced* invariant instead of a merely-documented one (see `_require_level` below).

## What this fix does and does not claim to fix

The 164s measurement is real, but this spec does not claim to fully explain it. Confirmed
code-level redundancy (see "Background"):
- A full trunk re-read + re-parse, independently, in `/scene`, `/atlas`, and `/lightmap`.
- `preview_native.build_scene()`'s `_scene_hashes` re-serializing every actor to compute a cache
  key, on every call, even when the result will be a `preview_cache` hit.
- `resolve_actor_sprites()` — a full texture-decode pass over every point actor — called
  independently by `/scene` (via `build_scene_payload`) and again by `/atlas`.

What this fix does NOT change: the underlying CSG solve/lighting bake time for a genuinely COLD
`preview_cache` (first ever build of a given geometry). If most of the 164s was actually an
uncached cold solve rather than the redundant work above, this fix will not bring `/atlas` down to
"low single-digit seconds" — it removes the *repeated* non-solve cost, which on a 2288-actor level
is still substantial (see numbers below) but is a distinct thing from solve time. Verification
(below) is written to measure the two separately rather than assume.

## Background: what exists and where the confirmed redundant cost is

Measured this session, both via direct Python profiling and cProfile, and re-verified against the
current code by an independent review pass:

- `uedcli/serve/scene.py::build_scene_payload` calls `trunk.read_level_with_bodies(maps_dir /
  level_name)` itself, on every call. Measured ~2.4-2.7 ms/actor. At 336 actors: ~900 ms. At
  WanChai's 2288: several seconds, just for this step, just once.
- `preview_native.build_scene()` additionally recomputes a geometry/light content hash on every
  call (`_scene_hashes` → `canonical_actor_t3d`, a re-serialize-and-hash of every actor) *before* it
  checks the disk `preview_cache` — so even a solve/lighting **cache hit** pays a real,
  actor-count-scaling cost every time.
- `resolve_actor_sprites(level, index, search_files)` (`preview_native.py`) is called independently
  by `scene.py::build_scene_payload` (line ~196) AND by `app.py`'s `atlas` route (line ~144) — a
  second full point-actor texture-decode pass per page load, building a fresh `TextureResolver`
  each time.
- `uedcli/serve/app.py`'s three routes (`scene`, `atlas`, `lightmap`) each independently do some or
  all of the above:
  - `GET /scene` → `build_scene_payload(...)` (trunk-read + `build_scene` + `resolve_actor_sprites`).
  - `GET /atlas` → its own `trunk.read_level_with_bodies(...)` + its own `build_scene(...)` call +
    its own `resolve_actor_sprites(...)` call.
  - `GET /lightmap` → its own `trunk.read_level_with_bodies(...)` + its own `build_scene(...)` call.
  - `solve_lock` (added to stop two concurrent COLD SOLVES racing `preview_cache`'s write) wraps
    only the `build_scene`/`_build_scene` call in each route — the trunk reads in `/atlas` and
    `/lightmap` happen *outside* the lock (review correction: not "all serialized back to back" as
    an earlier draft of this spec said). The lock prevents the three from corrupting each other's
    `preview_cache` write; it does not avoid the redundant work.

## Design

**Revised after a second, joint review with the explicit-rebuild spec (`dev/docs/board/to-spec/
gui-explicit-rebuild-pinned-build-state-mode/spec.md`)** — see that spec for the full reasoning.
Summary: a single atomically-swapped snapshot bundling trunk data and `build_scene` output was
correct for *this* spec's own goal (no torn reads), but the explicit-rebuild spec's whole point is
that trunk data and solved geometry update on **independent triggers** (Load vs. Rebuild) and are
*expected* to disagree in between (a freshly-Loaded actor with no solved geometry yet) — a single
bundled snapshot cannot represent that. This revision splits the cache into the two slots that
design needs, so this spec's fix doesn't have to be half-rewritten when that one lands.

Two independently-published, independently-atomic slots — not one merged snapshot, and not an
unstructured dict either:

```python
@dataclass(frozen=True, kw_only=True)
class _LoadedTrunk:          # "Load"-owned: trunk/actor data, no solve involved
    level: Level
    ranks: dict[str, str]
    folders: dict[str, str | None]
    sprite_table: list[tuple]            # resolve_actor_sprites — actor-derived, no CSG/lighting
    actor_sprites: dict[str, ActorSprite]  # needed, belongs here, not with the geometry slot

@dataclass(frozen=True, kw_only=True)
class _BuiltGeometry:         # "Rebuild"-owned: CSG + lighting output, keyed by its own hash pair
    geom_hash: str
    light_hash: str
    polys: list[tuple]
    texture_table: list[tuple]
    owners: list[str | None]
```

In `create_app`'s closure, each gets its own single-cell atomic-swap holder, same
`None`-means-needs-(re)build convention and the same double-checked-locking pattern as before —
this part of the earlier design was correct and carries over unchanged, just duplicated across two
independent cells instead of one:

```python
_trunk_ref: list[_LoadedTrunk | None] = [None]
_geometry_ref: list[_BuiltGeometry | None] = [None]

def _get_trunk() -> _LoadedTrunk: ...      # double-checked lock, same shape as before, own dataclass
def _get_geometry() -> _BuiltGeometry: ... # same, using _get_trunk()'s level for the build_scene call
```

- **Why two slots, not one** (correcting the prior "single snapshot" design): see the explicit-
  rebuild spec's Goal, "Two independent axes" — a `_LoadedTrunk` newer than the current
  `_BuiltGeometry` is not a torn read to prevent, it is the exact state UnrealEd itself shows after
  you import a brush but before you rebuild. Each slot is still individually atomic (no torn read
  *within* a slot — the original single-reference-swap argument applies to each one separately); the
  two slots are allowed to disagree with each other by design.
- **For THIS spec's scope (P1, no Load/Rebuild actions exist yet)**: both slots are still populated
  together and invalidated together, by the *same* trigger — the existing `TrunkWatcher` settle
  callback clears both `_trunk_ref[0]` and `_geometry_ref[0]` (in that order; still before
  broadcasting the WS reload, still without taking `solve_lock` — same reasoning as before). This
  preserves today's actual live-reload behavior (the one currently built and tested in Slice 1)
  without waiting for the explicit-rebuild spec to land. **The explicit-rebuild spec changes ONLY
  who clears/populates each slot** (Load owns `_trunk_ref`, Rebuild owns `_geometry_ref`, the
  watcher stops clearing either and just flips a signal flag) — it does not need to change either
  dataclass's shape or the double-checked-locking mechanism. Building this spec first, with this
  shape, means the later spec is a trigger swap, not a rewrite.
- **Invalidation ordering / lock hazard**: unchanged from the original design — clear before
  broadcasting, never take `solve_lock` from the async watcher callback (the event-loop-freeze
  hazard `app.py`'s own comment already warns about).
- **`solve_lock`** keeps its existing job for `_get_geometry()`'s build step (serializing concurrent
  first-requests so they don't both cold-solve). `_get_trunk()`'s read is cheap enough that it
  probably doesn't need the same lock at all — a plain double-checked-null-check without a shared
  lock is likely sufficient for a trunk read (no external resource contention like `preview_cache`'s
  write) — decide at plan time; either is compatible with this design.
- **Route bodies**: `_require_level(level_name)` → `trunk = _get_trunk()`; `geometry =
  _get_geometry()` (using `trunk.level` as `build_scene`'s input) → assemble the response from both.
  `/scene`'s `SceneActor`s come from `trunk` (+ `trunk.actor_sprites`), `ScenePoly`s from `geometry`.
  `/atlas` uses `geometry.texture_table + trunk.sprite_table`. `/lightmap` uses `geometry.polys`.
  `build_scene_payload` (`scene.py`) is refactored to take both already-built pieces instead of
  loading/building anything itself.
- **`_require_level` tightened** (review finding): today it only checks `(maps_root /
  level_name).is_dir()`, never that `level_name` equals the app's fixed `level` — harmless today
  since every route independently reloads whichever `level_name` was requested, but with a
  single-level cache, a request for a *different* (still-valid-on-disk) level name would silently
  return the WRONG level's cached data. Add `level_name != level` to the existing reject condition
  in `_require_level`, so a mismatched name gets the same clean "level not found" treatment instead
  of silently serving wrong data. (This is arguably a latent correctness gap today too, independent
  of this fix — worth fixing regardless.)

## Testing

- A test proving `/scene`, `/atlas`, `/lightmap` share **one** trunk-read call and **one**
  `build_scene`/`resolve_actor_sprites` call each, for three requests against an unchanged trunk
  (spy-based call-count assertion, matching `test_serve_scene.py`'s existing
  `test_build_scene_payload_second_call_is_a_cache_hit` pattern — extend to cover all three routes).
- A test proving a trunk change (the watcher firing) invalidates BOTH slots, and the next request
  rebuilds both fully.
- **A concurrency test** (review finding — was missing entirely): fire concurrent requests against
  the running app that race an invalidation, and assert every response is internally consistent
  within each slot (never a `/scene` payload whose `ranks`/`folders` came from a different trunk
  read than the OTHER `ranks`/`folders` a concurrent request got — i.e. no torn read *within*
  `_LoadedTrunk` or *within* `_BuiltGeometry`). Do NOT assert the two slots agree with each other —
  by this spec's own design (both cleared by the same trigger, for now) they will in practice, but
  that's incidental to this spec's scope, not a guarantee to test for (the explicit-rebuild spec
  owns and tests the "they may legitimately disagree" behavior once it changes the trigger).
- A test proving `_require_level` rejects a syntactically-valid but non-matching level name (e.g.
  a second real level directory that happens to exist under the same project's `maps/`).
- Existing tests (`test_serve_app.py`, `test_serve_scene.py`, `test_serve_textures.py`) must still
  pass with `build_scene_payload`'s new signature — update call sites, no back-compat shim (project
  convention: no back-compat cruft, this tool is unreleased).

## Verification (pre-merge)

- `bin/test -k serve` (full serve suite), scoped per `dev/docs/rules/tests.md`.
- Live, measuring the redundant work specifically (not conflating it with cold-solve time):
  1. Restart `uedcli serve` against WanChai (cold — first `/scene` fetch pays the real CSG/lighting
     solve, unaffected by this fix; record its time as the baseline "solve cost").
  2. Immediately fetch `/atlas` and `/lightmap` (this is the "already warm, redundant work only"
     case this fix targets) — record their time before and after the fix. This is the number that
     should drop sharply; it is a distinct measurement from step 1's solve time, and the spec makes
     no promise about step 1.
  3. Confirm a real trunk edit (e.g. `actor move`) still produces a correct live-reload with fresh
     data on all three endpoints, not stale data from before the edit.

## Revision history

- Initial draft assumed two independently-cached slots (trunk, scene) with no cross-field
  consistency guarantee and no concurrency test. An adversarial review (2026-09-14) found this
  could serve a persistently torn response under concurrent access (not just a momentary stale
  read), found the cache shape omitted `owners` (breaks click-to-select) and ignored
  `resolve_actor_sprites`'s identical redundancy, found the invalidation/broadcast ordering and
  lock-in-async-callback hazards unaddressed, found the single-level assumption enforced nowhere,
  and found the "low single-digit seconds" verification target unsubstantiated against the actual
  164s measurement. This revision replaces the two-slot design with one atomically-swapped
  snapshot, includes the sprite-table work in scope, specifies invalidation ordering and forbids
  locking in the async callback, tightens `_require_level`, adds a concurrency test, and separates
  the "redundant work" claim from the (unaffected, out of scope) cold-solve time.
- A second, joint review (with the explicit-rebuild spec) found the single-atomic-snapshot design,
  while internally correct on its own terms, could not represent that spec's required "Load and
  Rebuild legitimately disagree" state — the two specs' cache designs were incompatible as literally
  written, in either build order. This revision splits `_ServeState` into `_LoadedTrunk` (Load-owned)
  and `_BuiltGeometry` (Rebuild-owned) slots now, both still cleared together by the watcher for
  this spec's own scope, so the explicit-rebuild spec only needs to change the trigger later, not
  the shape.
