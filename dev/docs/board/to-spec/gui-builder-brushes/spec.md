# Spec — GUI builder brushes

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** Let a GUI session build a parametric shape (cube/cylinder/cone/sheet/staircase, plus the
2D-profile sweeps extrude/revolve), see it rendered as UED22's red **builder brush**, reposition/
rotate/re-shape it, then press **Add** or **Subtract** to clone it into a new placed brush with that
CSG operation. The builder brush is **exposed to the GUI transparently, as one more ordinary actor**
in `GET /api/session/{id}/scene`'s actor list, under a reserved, permanent Name — even though its own
unsaved state is kept in a small store separate from `StagingStore` (see "Data model" for why). All of
this reuses existing model-side brush machinery; no brush-geometry or CSG logic is duplicated in the
GUI frontend (`web/`) or written fresh for this feature.

**Add/Subtract do not consume or modify the builder brush.** Each press clones the builder brush's
CURRENT actor — same shape/`Location`/`Rotation`/`PrePivot`/other props, a freshly allocated Name,
`CsgOper` set to `CSG_Add` or `CSG_Subtract` per which button was pressed — into a **new staged
actor** in the project's existing `StagingStore` (`uedcli/serve/snapshots.py`, the same "unsaved"
store `actor move` already stages into). The builder brush itself is left exactly as it was, ready
for another Add/Subtract. The staged clone reaches the trunk only when the user hits the existing
**Save** action — same as any other staged edit.

**Non-goals.**

- **`brush build spiral`** (spiral staircase) is excluded from the builder-brush shape registry.
  `builders.spiral_staircase()` returns `list[Brush]` (N+1 actors: one column + one tread per step,
  `uedcli/builders.py:638`) — it cannot be represented as UED22's single builder-brush actor. It stays
  CLI/pipe-only (`brush build spiral | actor add -`), unchanged.
- No multi-builder-brush support: one reserved Name, one builder brush, per level (see "Data model").
- No new CLI verb, flag, or `--tree` kind. The CLI never resolves, reads, or writes a builder brush.
  Reuse happens at the Python-function level, not by making the builder-brush box reachable from
  `_resolve_level_source`/`--tree`.
- No persistent `CsgOper` on the builder brush itself. `CsgOper` is stamped only at Add/Subtract time,
  on the CLONE — the builder brush has no add-vs-subtract "mode" to toggle.
- No conflict-detection/merge machinery for the builder brush's own edits, and none for a staged
  Add/Subtract clone either — see "Data model" for why neither can conflict.
- Texture/solidity/folder/label/base-name/mover-class — the extra flags `_common_build_opts` adds to
  every `brush build <shape>` subparser (`uedcli/cli/parsers/brush.py:121-151`) — are NOT part of the
  builder-brush "build" call. Only each shape's own geometry params are; Location/Rotation/CsgOper are
  set (or, for CsgOper, chosen) through the operations described below. See "Builder registry".
- No separate, builder-brush-only edit endpoints for move/rotate/prop-set. The FE stages an edit to
  the builder brush through the exact same `POST /api/session/{id}/stage` call it uses for a real
  actor — see "API surface" for how the backend routes that one reserved Name differently without the
  FE (or the route's own request/response shape) knowing or caring.

## Background — what exists, reused as-is

- **`uedcli/builders.py`** already has pure, stateless shape constructors: `cube`, `cylinder`, `cone`,
  `sheet`, `staircase`, `spiral_staircase` → `Brush` (or `list[Brush]`), plus `extrude`/`revolve`
  (2D-profile sweeps via `profile.py`) and `make_brush_actor(name, brush, location=, csg=, group=,
  poly_flags=, mover_class=) -> Actor` (`dev/docs/architecture.md` module map).
- **In-place shape swap already exists and does exactly what "rebuild this shape" needs.**
  `brush replace NAME -` (`uedcli/cli/commands/brush/edit.py:502-543`) takes a piped `brush build`
  T3D snippet and swaps **only `target.brush.polys`** — Name, `order_value`, Group, CsgOper,
  PolyFlags, Rotation, Location, and PrePivot are all left untouched (comment at `edit.py:503-506`).
  This is the exact "regenerate the shape, keep everything else" operation UED22's per-shape Build
  buttons perform on its one builder brush.
- **Property edits are already generic at the model layer — the GUI must not re-special-case them.**
  `actor prop set` reaches `Location` through `propedit`'s typed-field registry
  (`uedcli/propedit/fields.py:275`, `TYPED_FIELDS`) and `Rotation` as an ordinary struct-typed prop
  (it isn't even in that registry) — ONE generic plan/apply path (`uedcli/propedit/edit.py`) already
  handles both, and every other prop, uniformly. *(Owner ruling — see memory
  `gui_backend_no_special_cased_props` and the follow-up item below.)* The builder brush's own prop
  edits reuse this path directly, through the SAME `/stage` route a real actor's edits use (see "API
  surface") — this spec generalizes that route's request shape from Location-only to any property, for
  every actor it names, builder brush included.
- **`StagingStore` (`uedcli/serve/snapshots.py`) keeps its own code exactly as it is today — the
  dispatch lives one layer up, in the route handler, not inside `StagingStore` itself.** `stage()`/
  `save_staged()`/`discard_staged()` keep their existing trunk-baseline/conflict-check contract,
  untouched, for every name they're called with. `POST /api/session/{id}/stage` (and `/discard`,
  `/save`) each gain ONE small dispatch at the top: if the named actor is the reserved builder-brush
  Name, call the small dedicated builder-brush module (below) instead of `StagingStore`; for every
  other name, behave exactly as today. This is the one clean seam this spec's special-casing is
  confined to — an earlier draft put the equivalent exceptions (skip the conflict check for one Name,
  don't clear it after Save, exclude it from `GET /api/session/{id}/staged`'s listing) INSIDE
  `StagingStore`'s own methods; moving the branch up to the route handler means `StagingStore`'s tests
  and behavior for real actors need no new cases at all. `StagingStore` separately gains ONE new
  capability regardless of any of this — staging a brand-new actor, for Add/Subtract's output — which
  needs no conflict handling either (fresh Name, nothing to diverge from).
- **`GET /api/session/{id}/scene` serves the raw trunk today, unmodified by session state.** Staged
  actor moves are NOT merged into it server-side — only `POST /rebuild`'s CSG solve does that, via
  `edits.apply_staged_overlay` (`uedcli/serve/app.py:551-560`). **This spec adds ONE narrow overlay**:
  the session's builder-brush actor (from its own store, not `StagingStore`) is appended to `/scene`'s
  actor list, through the same per-actor serialization `_build_actors` already applies to a trunk
  actor (`uedcli/serve/scene.py:571`) — not a general "overlay session state into `/scene`" change; a
  real actor's staged `Location` move still does not appear there, unchanged from today.
- **`SceneActor` (`uedcli/serve/scene.py`) special-cases `location`/`rotation` as dedicated fields,
  separate from its generic `props` list.** Because the builder brush is exposed as a genuine
  `SceneActor` like any other (not a bespoke response shape — an earlier draft of this spec invented
  one specifically to dodge this; that workaround is gone now that "transparent" is the actual goal),
  it inherits this pre-existing special-casing exactly as much as every other actor does — no more, no
  less. Fixing `SceneActor` itself stays out of scope here (ripples into `/scene`, `/rebuild`, staged
  moves, existing FE/test code) and is filed separately at p1:
  `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/`.
- **The reserved Name must not be `"Brush0"` — confirmed by this project's own RE findings, not a
  style preference.** `uedcli/normalize.py:96-99,174-177`: a fresh UnrealEd numbers its builder brush
  `Brush1`, `Brush2`, … depending on the editor session's counter — `"Brush0"` is not even reliably
  correct for UnrealEd's OWN builder brush, which is why `normalize.py`'s own comment says "Name is no
  longer used" for identifying it (the ground truth is ARRAY POSITION, `Actors(1)`, per
  `dev/docs/spikes/2026-09-15-builder-brush-is-actors1-not-a-content-heuristic/spike.md`). Reusing the
  literal string `"Brush0"` for uedcli's own reserved GUI sentinel would collide, in a reader's mind,
  with `normalize.BUILDER_BRUSH_NAME` — a same-spelled constant serving a completely different job
  (skipping an accidental builder-brush T3D snippet at ingest). This spec's reserved Name is a NEW,
  uedcli-owned sentinel, visibly distinct from that constant — see "Data model".

## Data model

**One reserved Name, one builder brush, per level.** Proposed sentinel: `*Builder` — chosen to be
**illegal as a real UnrealEngine object name**, not merely a value nothing happens to mint: FNames are
alnum/underscore only (`uedcli/preview_shots.py:21`'s stated basis for its own filename-safety logic),
and `*` is neither, so this string can never be a real actor Name. It is never minted through
`allocate_name` either (invariant D6 mints `Uedcli<Class><n>` with a numeric/random suffix, a disjoint
scheme), but that is now a second, redundant guarantee, not the only one.

One thing `*Builder` does NOT get, that an earlier `/`-containing candidate would have:
`t3dtree.check_safe_segment` (`uedcli/t3dtree.py:153-157`) only rejects a name containing `/`/`\` or
equal to `.`/`..` — a bare `*` passes it unchanged, so a bug that somehow routed this sentinel through
the trunk-write path would not be caught there the way it would with a `/`-containing name. Not
load-bearing (this design never passes the reserved Name to a trunk-write path — only its D6-allocated
clones ever reach the trunk), but worth recording as a conscious trade for readability.

**Where it lives — two tiers, neither is the trunk, neither is `StagingStore`'s own storage — but both
reached through the SAME `/stage`/`/discard`/`/save` routes a real actor's edits use:**

1. **The session's own working copy — a small, separate, purpose-built store**, e.g.
   `sessions/<sid>/builder-brush.json` (git-untracked). Every live interaction (build/rebuild-shape,
   or a `/stage`d prop edit) writes here immediately. The route handler dispatches to this store for
   the reserved Name and to `StagingStore` for everything else — see "Background" for why the branch
   lives there rather than inside `StagingStore` itself.
2. **The level's persisted box, `levels/<level>/builder-brush.json` (git-untracked, across
   sessions).** Written only by the existing **Save** action. Plain overwrite, no conflict check —
   there is nothing to diverge from, per the pinning rule below.

**Session-pinned.** A session's own builder-brush store is seeded ONCE, when the session is created:
from `levels/<level>/builder-brush.json` if it exists, else from a small hard-coded default shape (a
cube; exact dimensions are an implementation-plan detail) with `CsgOper=CSG_Add` as an inert default
(see "Non-goals" — never shown, irrelevant once Add/Subtract stamps its own value). It is **never**
re-seeded from another session's later Save — an already-running session keeps its own view for its
whole life, mirroring `build_pin.py`'s session pin pinning to one `(geom_hash, light_hash)` rather than
always tracking the level's latest build.

**Save.** `POST /api/session/{id}/save` does two independent jobs, unchanged as ONE route: (a)
`StagingStore`'s existing apply-to-trunk flow runs unchanged for every staged real-actor move AND
every staged Add/Subtract clone (the new "stage a whole new actor" capability); (b) the session's
builder-brush store is flushed, as a whole, into `levels/<level>/builder-brush.json` — a plain
overwrite, not cleared afterward (unlike a `StagingStore` entry, which IS cleared once applied — the
builder brush is not "consumed" by Save; the session keeps working on the same store).

**Discard.** `POST /api/session/{id}/discard {"actors": ["*Builder"]}` — the SAME route a real actor's
discard uses. For the reserved Name, the handler's dispatch (see "Background") routes it to the
builder-brush store instead of `StagingStore.clear_actor`, and — because there is no trunk copy to
fall back to the way a real actor's discard has — it **re-seeds** the session's store the same way
session-creation does (from `levels/<level>/builder-brush.json`, else the default cube), rather than
leaving it empty.

**Why nothing here needs conflict/merge machinery.** The builder brush's own store has no trunk
baseline to diverge from (Save never writes IT to the trunk — only Add/Subtract's clones reach the
trunk, through `StagingStore`, as brand-new Names with nothing to conflict against either), and a
session's own store is never touched by any other session's writes.

## `/scene` overlay

`GET /api/session/{id}/scene` appends ONE synthetic entry — the session's own builder-brush actor,
read from its own store — to the trunk-derived actor list, serialized through the exact same
per-actor path `_build_actors` (`uedcli/serve/scene.py:571`) already applies to every trunk actor. No
second serialization path, no bespoke response shape. The FE distinguishes it (for the red
builder-brush rendering, and to route edits/Add/Subtract UI at it) by Name equality against the
reserved sentinel — no new boolean flag needed, since the Name is already unique and known.

This overlay is scoped to exactly this one entry — it does not change `/scene`'s existing behavior for
any real actor's staged edits, which still only appear through client-side optimistic rendering and
`POST /rebuild`'s CSG solve, unchanged from today.

## On-disk layout

This spec also restructures existing `.uedcli/` state to keep the new per-level/cache split uniform
(decided together with the builder-brush addition, not purely additive):

```
cache/build/v{N}/<level>/geometry/<hash>.marshal          (was build/cache/v{N}/<level>/geometry/…)
cache/build/v{N}/<level>/lighting/<geom_hash>/<light_hash>.marshal
cache/preview/materialized__<level>__<hash12>.dx          (was preview/materialized__…)
levels/<level>/build.json                                 (was build/pin/<level>/current.json;
                                                             ONE file — {geom_hash, light_hash}
                                                             together, same atomic-write shape as
                                                             sessions/<sid>/build.json — NOT split
                                                             into separate geometry.json/lighting.json
                                                             files, which would need new coordination
                                                             to stay atomic)
levels/<level>/builder-brush.json                          (new — the level's persisted builder brush)
sessions/<sid>/{index.json, staged.json, build.json,
                builder-brush.json}                        (new file, sibling to the existing three —
                                                             the session's OWN builder-brush store,
                                                             separate from staged.json/StagingStore)
staging/blobs/, stash/, tmp/                                (unchanged)
```

`<level>` segments stay level-scoped everywhere (not deduped globally) — no change to
`build_cache.evict_unreferenced`'s per-level eviction logic. `.uedcli/` is fully derivable/throwaway
(`uedcli/config.py:20-21`), so this rename needs no migration: stale old-path files are simply dead
weight until manually cleared.

**Files/functions this rename touches** (path-prefix edits, not behavior changes):
`uedcli/build_cache.py` (`_dir`, module docstring), `uedcli/preview_game.py` (`_preview_dir` and its
callers/comments), `uedcli/serve/build_pin.py` (`level_pointer_path`).

## Builder registry — backend-declared, zero FE per-shape code

**Goal**: adding a new shape to `builders.py` + its CLI parser entry makes it available in the GUI's
shape picker with no frontend changes.

**Source of truth: the existing argparse subparsers**, not a new hand-declared schema. Each shape's
own `add_argument` calls in `uedcli/cli/parsers/brush.py` (e.g. `bcyl.add_argument("--radius",
type=float, required=True, help="circumscribed radius")`, `brush.py:197`) already carry the type,
default/required-ness, `choices=` (for enum-like params, e.g. `--axis`'s `choices=["x","y","z"]`,
`brush.py:209`), and a real `help=` string (required for every arg by this project's CLI conventions).
`GET /api/builders` introspects these subparsers and serves, per shape: its id (the subparser name,
e.g. `"cylinder"`), its own `help=` as the label, and one entry per **shape-specific** argument (name,
type, default, choices if any, help text) — **excluding** every argument `_common_build_opts` adds
(`--at`, `--base-name`, `--csg`, `--solidity`, `--folder`, `--label`, `--texture`,
`brush.py:121-151`), since `--at` is handled by the builder-brush `prop` route (see "API surface"),
and `--csg` is not a builder-brush property at all — it is chosen only by which of Add/Subtract the
user presses (see "Non-goals").

**Icon** has no CLI analog — one small new hand-authored table, shape id → icon name/path, is the only
new declarative data this feature adds per shape.

`spiral` is excluded from this registry entirely (see "Non-goals").

## API surface

- `GET /api/builders` — the shape registry above. No session; static per install (derived from the
  CLI parser tree).
- `POST /api/session/{id}/builder-brush/build` `{shape, params}` — rebuild the builder brush's
  geometry via `builders.<shape>(**params)`, then swap-in-place via the extracted pure function
  described under "Reuse strategy" (only `PolyList` changes; Location/Rotation/CsgOper untouched).
  Writes to the session's own builder-brush store. Returns the actor re-serialized through the same
  per-actor path `/scene`'s overlay uses, so the FE has an immediate render without a second round
  trip.
- `POST /api/session/{id}/stage` (existing route, generalized) `{"actors": {name: {prop: value,
  ...}}}` — moving Location off its own hardcoded shape onto the generic form is what lets the SAME
  call the FE already makes for a real actor's move also cover the builder brush's move/rotate/any-
  other-prop needs. The route handler's ONE dispatch point (see "Background") sends a write for
  `*Builder` to the session's own store (through `propedit`'s plan/apply, same as `actor prop set`)
  and a write for any other name to `StagingStore`, exactly as today. Neither the request/response
  shape nor the FE's call site differs by which kind of actor is named.
- `POST /api/session/{id}/builder-brush/add` and `POST /api/session/{id}/builder-brush/subtract` —
  clone the builder brush's current actor into a new `StagingStore`-staged actor with a freshly
  `allocate_name`d Name and `CsgOper` stamped per the route. Returns the new actor's allocated Name and
  its `SceneActor`/`BrushHighlight` form (it now IS an ordinary staged actor, read the ordinary way).
  The builder brush's own store is untouched. These stay their own routes — cloning into a brand-new
  actor has no "real actor" analog to piggyback on, unlike move/rotate/prop-set.
- `POST /api/session/{id}/discard` (existing route, no change to its shape) — `{"actors":
  ["*Builder"]}` dispatches to the builder-brush store and re-seeds it per "Data model", rather than
  clearing it to nothing the way a real actor's discard does.
- `POST /api/session/{id}/save` (existing route, `app.py:829`, extended) — gains a second, independent
  job: flush the session's builder-brush store into `levels/<level>/builder-brush.json`, without
  clearing it. Its existing `StagingStore`-apply behavior (real actor moves, and now staged
  Add/Subtract clones) is unchanged.
- No dedicated `GET`/`POST .../prop`/`POST .../move`/`POST .../reset` builder-brush routes — reading
  it is superseded by the `/scene` overlay; editing and resetting it ride `/stage` and `/discard`,
  the same routes a real actor's edits use. Only `build` and `add`/`subtract` are genuinely new
  operations with no real-actor equivalent, so only those stay their own routes.

## Reuse strategy (no logic duplication, backend or frontend)

- **CLI stays untouched** — no `--tree builder-brush` kind, no new argparse. The serve layer calls
  Python functions directly, the same way `uedcli/serve/edits.py` already calls the model-side
  `actor move` write pattern directly rather than shelling out to the CLI.
- **The generalized `/stage` route reuses `propedit`'s plan/apply, not a hand-rolled per-prop
  setter, for the builder-brush half of its dispatch.** It builds a plan the same way `actor prop set`
  does (`uedcli/propedit/edit.py`) against the builder brush's single stored actor, so `Location`'s
  typed-field validation (Decimal precision, PrePivot invariant D8) and any struct-typed prop's
  grammar are enforced identically to the CLI, with zero reimplementation — and zero special-casing of
  WHICH property is being set (only which ACTOR, at the one dispatch point — see "Background").
- **The "swap only PolyList" logic in `_replace()`** (`uedcli/cli/commands/brush/edit.py:502-543`,
  specifically lines 537-541) is extracted into a small pure function — proposed home `builders.py`,
  alongside the other builder functions — called by both the CLI's `_replace()` (unchanged behavior)
  and the new serve-layer `build` route.
- **The `/scene` overlay and the FE's rendering both reuse existing per-actor code paths** — see
  "`/scene` overlay" and "Background". The FE needs no per-builder-brush branch in its
  brush-rendering/edit-call code at all — `/stage`/`/discard` are called identically either way; only
  `build`/`add`/`subtract` need a Name-aware call site, since those have no real-actor equivalent.
- **Add/Subtract reuse the trunk write path at Save time, not a new one.** Once staged, a new actor
  from `add`/`subtract` is applied into the trunk via the exact same path `actor add -` already uses
  (`TrunkLevelSource.save` on a freshly allocated Name) — Save's existing `StagingStore` flush calls
  that path, it does not reimplement "how a new actor gets into the trunk". The only genuinely new
  code is `StagingStore`'s "stage a NEW actor" capability and the clone-with-CsgOper-override step
  itself (copy an `Actor`, mint a Name, set `CsgOper`).

## Error handling

- Same rule as every other GUI route: no Python exception reaches the user; a build/stage/add/subtract
  failure returns a structured error naming the offending value.
- **The session's builder-brush store read failure**: corrupt-and-instruct — same posture as
  `sessions/<sid>/build.json` (`build_pin.py`'s `SessionPointerCorruptError`), since it is the
  session's own unsaved work.
- **`levels/<level>/builder-brush.json` read failure**: corrupt-and-instruct, NOT silent-degrade —
  deliberately different from `levels/<level>/build.json`'s posture (silent-degrade to "never built",
  since a build pin is purely regenerable). A persisted builder brush is the user's actual placed
  shape/position and cannot be regenerated from nothing, so losing it silently would be real data
  loss, not a cheap cache miss.
- `build`/`add`/`subtract`'s geometry validation reuses whatever `actor add -`/`brush replace`'s
  existing `validate_brush` already enforces (`edit.py:541`, `geometry.validate_brush`) — a degenerate
  shape is rejected the same way it already is on every other model-side write path.
- **A staged NEW actor (from `add`/`subtract`) cannot conflict at Save** — its Name did not exist
  before it was staged, so there is no trunk-side value to compare against; Save simply applies it.
  This differs from the existing staged-move path, which does need the conflict check because the
  target actor already existed and may have changed trunk-side since staging.

## Testing

- **Backend**: session creation seeds the builder-brush store from `levels/<level>/builder-brush.json`
  when present, else the default cube; `/scene` includes exactly one `*Builder` entry, serialized
  through the same per-actor path as a real actor; `build` swaps only `PolyList` (byte-identical to
  today's `_replace()` for the same inputs); `POST /stage` dispatches a `*Builder` entry to the
  builder-brush store (setting `Location`, `Rotation`, and at least one other property through the
  SAME `propedit` plan/apply path `actor prop set` uses) and every other name to `StagingStore`
  exactly as before, from the SAME request — a single test asserting both branches of one call proves
  the dispatch point, not two divergent code paths; `StagingStore`'s own move-staging/conflict/clear
  behavior for REAL actors is completely unchanged by this feature (a regression check, since it's the
  module most at risk of accidental special-casing creeping back in); Save writes the builder-brush
  store's content to `levels/<level>/builder-brush.json` without clearing the store, and separately
  applies every `StagingStore`-staged actor (moves and Add/Subtract clones) exactly as it does today;
  `POST /discard {"actors": ["*Builder"]}` re-seeds the store rather than leaving it empty, while
  discarding a real actor's Name still clears it to nothing, unchanged; a session created AFTER
  another session's Save picks up the new persisted state, while an already-running session does not
  (the pinning rule);
  `add`/`subtract` clone the builder brush's current actor (shape/Location/Rotation/other props
  preserved, fresh Name, correct `CsgOper`) into `StagingStore` and leave the builder brush's own store
  byte-for-byte unchanged; pressing Add then Subtract produces two independent staged actors, not one
  overwritten; `GET /api/builders` output matches the real argparse subparser tree (a regression test
  comparing the two).
- **Frontend**: the shape-picker form renders purely from `GET /api/builders` with no per-shape code;
  the builder brush renders through the exact same code path as any other `SceneActor.brush` from
  `/scene`, with Name-equality against the reserved sentinel the only builder-brush-specific branch.
- Scope tests to the touched module while iterating (`bin/test -k serve`, `web/`'s vitest run); full
  suite once before merge, per `dev/docs/rules/tests.md`.

## Refs

- `dev/docs/architecture.md` "The core write pattern", "The `LevelSource` seam and `--tree`" (the
  seam this feature deliberately does NOT extend), module map entries for `builders.py`/`profile.py`.
- `uedcli/cli/commands/brush/edit.py:502-543` (`_replace`, the poly-swap this feature extracts).
- `uedcli/cli/parsers/brush.py:121-278` (`_common_build_opts` + all `brush build` shape subparsers —
  the registry's source of truth).
- `uedcli/serve/snapshots.py`, `uedcli/serve/edits.py`, `uedcli/serve/app.py:772-827` (`StagingStore`/
  staged-actor flow — kept exactly as-is for real actors, plus one new "stage a new actor" capability
  for Add/Subtract's output; NOT where the builder brush's own state lives).
- `uedcli/serve/build_pin.py` (the two-pin, two-failure-posture precedent the session-store/
  `levels/<level>/builder-brush.json` split follows).
- `uedcli/build_cache.py`, `uedcli/preview_game.py` (on-disk paths renamed by this spec).
- `uedcli/serve/scene.py:571` (`_build_actors` — the per-actor serialization the `/scene` overlay and
  `build`'s response both reuse).
- `uedcli/propedit/edit.py`, `uedcli/propedit/fields.py:275` (`TYPED_FIELDS` — the generic plan/apply
  the generalized `/stage` route's builder-brush dispatch calls, unmodified).
- `uedcli/t3dtree.py:153-157` (`check_safe_segment` — the guard an earlier `/`-based sentinel would
  have tripped; `*Builder` passes it, a noted trade-off, see "Data model").
- `uedcli/preview_shots.py:21` (FNames are alnum/underscore — why `*Builder` is illegal).
- `uedcli/normalize.py:96-99,174-177`, `dev/docs/spikes/2026-09-15-builder-brush-is-actors1-not-a-
  content-heuristic/spike.md` (why the reserved Name is not `"Brush0"`).
- `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/` (p1 follow-up: fold
  `SceneActor`'s dedicated `location`/`rotation` fields into its generic `props`; the builder brush is
  now subject to this exactly like every other actor).
- Memory `gui_backend_no_special_cased_props` (owner ruling: never special-case Location/Rotation
  away from regular props in the GUI backend).
