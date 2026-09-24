# Spec — GUI builder brushes

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** Let a GUI session build a parametric shape (cube/cylinder/cone/sheet/staircase, plus the
2D-profile sweeps extrude/revolve), see it rendered as UED22's red **builder brush**, reposition/
rotate/re-shape it, then press **Add** or **Subtract** to clone it into a new placed brush with that
CSG operation. The builder brush is **exposed to the GUI transparently, as one more ordinary actor**:
a reserved, permanent Name, always present in `GET /api/session/{id}/scene`'s actor list, edited
through the same staged-edit mechanism a real actor's edits use — not a parallel API surface. All of
this reuses existing model-side brush machinery; no brush-geometry or CSG logic is duplicated in the
GUI frontend (`web/`) or written fresh for this feature.

**Add/Subtract do not consume or modify the builder brush.** Each press clones the builder brush's
CURRENT actor — same shape/`Location`/`Rotation`/`PrePivot`/other props, a freshly allocated Name,
`CsgOper` set to `CSG_Add` or `CSG_Subtract` per which button was pressed — into a **new staged
actor** in the same staging store the builder brush itself now lives in
(`uedcli/serve/snapshots.py`). The builder brush is left exactly as it was, ready for another
Add/Subtract. The staged clone reaches the trunk only when the user hits the existing **Save**
action — same as any other staged edit.

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
  handles both, and every other prop, uniformly. *(Owner ruling, this design round — see memory
  `gui_backend_no_special_cased_props` and the follow-up item below.)*
- **`StagingStore` (`uedcli/serve/snapshots.py`) needs two new capabilities, not a parallel
  mechanism.** Today it only stages a `Location` MOVE of an actor that already exists in the trunk —
  `stage()`/`save_staged()` require `query.resolve_actor_name` to resolve against the trunk first
  (`edits.py:74-76`), and only `Location` is settable. This spec needs:
  1. **Generic per-property staging**, not Location-only — the existing `POST /api/session/{id}/stage`
     route's request shape (`{"actors": {name: [x,y,z]}}`, `app.py:789-790`) generalizes to `{"actors":
     {name: {prop: value, ...}}}`, backed by `propedit`'s plan/apply instead of a hardcoded Location
     setter. This is the SAME reuse point noted above, wired into the ALREADY-EXISTING stage endpoint
     rather than a new one.
  2. **Staging a brand-new actor**, for Add/Subtract's output — there is no such path today. Once
     staged, it needs no conflict handling (fresh Name, nothing to diverge from).
  3. **One reserved, permanent Name treated specially by `stage()`/`save_staged()` only** (see "Data
     model") — every other actor Name keeps today's trunk-baseline/conflict behavior unchanged.
- **`GET /api/session/{id}/scene` serves the raw trunk today, unmodified by session state.** Staged
  actor moves are NOT merged into it server-side — only `POST /rebuild`'s CSG solve does that, via
  `edits.apply_staged_overlay` (`uedcli/serve/app.py:551-560`). **This spec adds ONE narrow overlay**:
  the session's own staged entry for the reserved builder-brush Name is appended to `/scene`'s actor
  list, through the same per-actor serialization `_build_actors` already applies to a trunk actor
  (`uedcli/serve/scene.py:571`) — not a general "overlay every staged edit into `/scene`" change; a
  real actor's staged `Location` move still does not appear there, unchanged from today.
- **`SceneActor` (`uedcli/serve/scene.py`) special-cases `location`/`rotation` as dedicated fields,
  separate from its generic `props` list.** Because the builder brush is now a genuine `SceneActor`
  like any other (not a bespoke response shape — an earlier draft of this spec invented one
  specifically to dodge this; that workaround is gone now that "transparent" is the actual goal), it
  inherits this pre-existing special-casing exactly as much as every other actor does — no more, no
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

**One reserved Name, one builder brush, per level.** Proposed sentinel: `uedcli/builder-brush` —
chosen to be **structurally impossible** as a real UnrealEngine object name, not merely a value the
allocator promises never to mint. `t3dtree.check_safe_segment` (`uedcli/t3dtree.py:153-157`) rejects
any name containing `/` or `\`, precisely because "a real UnrealEngine object name can never contain"
either — the same guard every `actors/<name>` trunk-tree write already goes through. A name with a
`/` in it can therefore never collide with a real actor's Name, and — as a bonus — if a bug ever
routed this sentinel through the trunk-write path by mistake, `check_safe_segment` would reject it
loudly there rather than silently writing something wrong. It is never minted through `allocate_name`
either (invariant D6 mints `Uedcli<Class><n>` with a numeric/random suffix, a disjoint scheme), but
that is now a second, redundant guarantee, not the only one.

**Where it lives — two tiers, neither is the trunk:**

1. **The session's staged entry (git-untracked, in the existing staging store).** The reserved Name's
   current actor state lives as one more entry in that session's `staged.json` +
   `staging/blobs/` (`uedcli/serve/snapshots.py`) — no separate per-session file. Every live
   interaction (build/rebuild-shape, or a prop edit through the generalized `/stage` route) writes here
   immediately, same as it already does for a real actor's staged move.
2. **The level's persisted box, `levels/<level>/builder-brush.json` (git-untracked, across
   sessions).** Written only by the existing **Save** action. Plain overwrite, no conflict check —
   there is nothing to diverge from, per the pinning rule below.

**Session-pinned.** A session's staged entry for the reserved Name is seeded ONCE, when the session is
created: from `levels/<level>/builder-brush.json` if it exists, else from a small hard-coded default
shape (a cube; exact dimensions are an implementation-plan detail) with `CsgOper=CSG_Add` as an inert
default (see "Non-goals" — never shown, irrelevant once Add/Subtract stamps its own value). It is
**never** re-seeded from another session's later Save — an already-running session keeps its own view
for its whole life, mirroring `build_pin.py`'s session pin pinning to one `(geom_hash, light_hash)`
rather than always tracking the level's latest build.

**Save.** For every OTHER staged actor, Save behaves exactly as it does today (apply to the trunk,
conflict-checked, cleared from staging once applied). For the ONE reserved Name specifically, Save
instead (a) overwrites `levels/<level>/builder-brush.json` with its current staged content, and (b)
does **NOT** clear it from the session's staging store afterward — unlike every other staged edit,
the builder brush is not "consumed" by Save; the session keeps working on the same staged entry.

**Discard.** `POST /api/session/{id}/discard {"actors": ["uedcli/builder-brush"]}` reuses the existing
route, but — because there is no trunk copy to fall back to the way a real actor's discard has — it
**re-seeds** the reserved Name's staged entry the same way session-creation does (from
`levels/<level>/builder-brush.json`, else the default cube), rather than leaving it staged-absent.

**`GET /api/session/{id}/staged`** (the existing pending-changes list, `app.py:873`) **excludes the
reserved Name.** It is not a comparable "pending change to review" — there is no trunk baseline to
diff against, and per the pinning rule it is always present, so listing it there would read as a
permanent, unclearable "unsaved change" notice.

**Why nothing here needs conflict/merge machinery.** The reserved Name never has a trunk-side value to
diverge from (Save never writes it to the trunk), and a session's own staged entry is never touched by
any other session's writes. Add/Subtract's clone is a brand-new, freshly allocated Name — Save can
never find a pre-existing trunk value to compare it against either.

## `/scene` overlay

`GET /api/session/{id}/scene` appends ONE synthetic entry — the session's current staged actor for
`uedcli/builder-brush` — to the trunk-derived actor list, serialized through the exact same per-actor
path `_build_actors` (`uedcli/serve/scene.py:571`) already applies to every trunk actor. No second
serialization path, no bespoke response shape. The FE distinguishes it (for the red builder-brush
rendering, and to route edits/Add/Subtract UI to it) by Name equality against the reserved sentinel —
no new boolean flag needed, since the Name is already unique and known.

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
sessions/<sid>/{index.json, staged.json, build.json}       (unchanged — the reserved Name is just one
                                                             more entry inside the existing staged.json,
                                                             no new per-session file)
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
`brush.py:121-151`), since `--at` is handled by the generalized `/stage` route on the builder-brush
actor, and `--csg` is not a builder-brush property at all — it is chosen only by which of Add/Subtract
the user presses (see "Non-goals").

**Icon** has no CLI analog — one small new hand-authored table, shape id → icon name/path, is the only
new declarative data this feature adds per shape.

`spiral` is excluded from this registry entirely (see "Non-goals").

## API surface

- `GET /api/builders` — the shape registry above. No session; static per install (derived from the
  CLI parser tree).
- `POST /api/session/{id}/builder-brush/build` `{shape, params}` — rebuild the reserved actor's brush
  geometry via `builders.<shape>(**params)`, then swap-in-place via the extracted pure function
  described under "Reuse strategy" (only `PolyList` changes; Location/Rotation/CsgOper untouched).
  Writes into the same staging-store entry as any other edit to this Name. Returns the actor
  re-serialized through the same per-actor path `/scene`'s overlay uses, so the FE has an immediate
  render without a second round trip.
- `POST /api/session/{id}/stage` (existing route, generalized) `{"actors": {name: {prop: value,
  ...}}}` — moving Location off its own hardcoded shape onto the generic form covers the builder
  brush's move/rotate needs with ZERO builder-brush-specific code: `uedcli/builder-brush` is just
  another name in the same map real actors use. No new route.
- `POST /api/session/{id}/builder-brush/add` and `POST /api/session/{id}/builder-brush/subtract` —
  clone the reserved Name's current staged actor into a new staged actor with a freshly
  `allocate_name`d Name and `CsgOper` stamped per the route. Returns the new actor's allocated Name and
  its `SceneActor`/`BrushHighlight` form (it now IS an ordinary staged actor, read the ordinary way).
  The reserved Name's own staged entry is untouched.
- `POST /api/session/{id}/discard` (existing route, no change to its shape) — `{"actors":
  ["uedcli/builder-brush"]}` re-seeds it per "Data model", rather than leaving it absent.
- `POST /api/session/{id}/save` (existing route, `app.py:829`, extended) — for the reserved Name:
  flush to `levels/<level>/builder-brush.json` instead of the trunk, and do not clear it from staging.
  For every other staged actor: unchanged.
- No dedicated `GET`/`DELETE /api/session/{id}/builder-brush` — superseded by the `/scene` overlay
  (GET) and `/discard` (the re-seeding "reset" case) respectively. An earlier draft of this spec had
  both as bespoke routes; removed once "transparent, ordinary actor" became the actual design.

## Reuse strategy (no logic duplication, backend or frontend)

- **CLI stays untouched** — no `--tree builder-brush` kind, no new argparse. The serve layer calls
  Python functions directly, the same way `uedcli/serve/edits.py` already calls the model-side
  `actor move` write pattern directly rather than shelling out to the CLI.
- **The generalized `/stage` route reuses `propedit`'s plan/apply, not a hand-rolled per-prop
  setter.** It builds a plan the same way `actor prop set` does (`uedcli/propedit/edit.py`), so
  `Location`'s typed-field validation (Decimal precision, PrePivot invariant D8) and any struct-typed
  prop's grammar are enforced identically to the CLI, with zero reimplementation, for EVERY staged
  actor — the reserved Name included, with no special case in the plan/apply call itself (the special
  case is confined to `stage()`/`save_staged()` recognizing that one Name, per "Data model").
- **The "swap only PolyList" logic in `_replace()`** (`uedcli/cli/commands/brush/edit.py:502-543`,
  specifically lines 537-541) is extracted into a small pure function — proposed home `builders.py`,
  alongside the other builder functions — called by both the CLI's `_replace()` (unchanged behavior)
  and the new serve-layer `build` route.
- **The `/scene` overlay and the FE's rendering both reuse existing per-actor code paths** — see
  "`/scene` overlay" and "Background". The FE needs no per-builder-brush branch in its
  brush-rendering code, only in knowing which Name to route Add/Subtract/build UI at.
- **Add/Subtract reuse the trunk write path at Save time, not a new one.** Once staged, a new actor
  from `add`/`subtract` is applied into the trunk via the exact same path `actor add -` already uses
  (`TrunkLevelSource.save` on a freshly allocated Name) — Save's extended flush calls that path, it
  does not reimplement "how a new actor gets into the trunk". The only genuinely new code is the
  staging-store capability noted under "Background" (staging a NEW actor, not a move) and the
  clone-with-CsgOper-override step itself (copy an `Actor`, mint a Name, set `CsgOper`).

## Error handling

- Same rule as every other GUI route: no Python exception reaches the user; a build/stage/add/subtract
  failure returns a structured error naming the offending value.
- **The reserved Name's staged-entry read failure** inherits whatever `StagingStore`'s existing
  `staged.json` read behavior already is — this spec does not change that (unlike the dedicated Tier-0
  file an earlier draft proposed, which would have needed its own posture; that file no longer exists).
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

- **Backend**: session creation seeds the reserved Name's staged entry from `levels/<level>/
  builder-brush.json` when present, else the default cube; `/scene` includes exactly one
  `uedcli/builder-brush` entry, serialized through the same per-actor path as a real actor; `build`
  swaps only `PolyList` (byte-identical to today's `_replace()` for the same inputs); the generalized
  `/stage` route sets `Location`, `Rotation`, and at least one other property on the reserved Name
  through the SAME code path used for a real actor's staged move — no code path that special-cases
  which Name or which property was sent; Save writes the reserved Name's staged content to
  `levels/<level>/builder-brush.json`, does NOT clear it from staging, and leaves every other staged
  actor's apply/clear/conflict behavior unchanged; discard on the reserved Name re-seeds rather than
  leaving it absent; a session created AFTER another session's Save picks up the new Tier-1 state,
  while an already-running session does not (the pinning rule); `add`/`subtract` clone the reserved
  Name's current staged actor (shape/Location/Rotation/other props preserved, fresh Name, correct
  `CsgOper`) into a new staged actor and leave the reserved Name's entry byte-for-byte unchanged;
  pressing Add then Subtract produces two independent staged actors, not one overwritten; `GET
  /api/session/{id}/staged` never lists the reserved Name; `GET /api/builders` output matches the real
  argparse subparser tree (a regression test comparing the two).
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
  staged-actor flow — generalized to hold the builder brush itself, not a separate mechanism).
- `uedcli/serve/build_pin.py` (the two-pin, two-failure-posture precedent the reserved-Name/
  Tier-1 split follows).
- `uedcli/build_cache.py`, `uedcli/preview_game.py` (on-disk paths renamed by this spec).
- `uedcli/serve/scene.py:571` (`_build_actors` — the per-actor serialization the `/scene` overlay and
  `build`'s response both reuse).
- `uedcli/propedit/edit.py`, `uedcli/propedit/fields.py:275` (`TYPED_FIELDS` — the generic plan/apply
  the generalized `/stage` route calls, unmodified).
- `uedcli/t3dtree.py:153-157` (`check_safe_segment` — why the reserved Name contains `/`).
- `uedcli/normalize.py:96-99,174-177`, `dev/docs/spikes/2026-09-15-builder-brush-is-actors1-not-a-
  content-heuristic/spike.md` (why the reserved Name is not `"Brush0"`).
- `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/` (p1 follow-up: fold
  `SceneActor`'s dedicated `location`/`rotation` fields into its generic `props`; the builder brush is
  now subject to this exactly like every other actor).
- Memory `gui_backend_no_special_cased_props` (owner ruling: never special-case Location/Rotation
  away from regular props in the GUI backend).
