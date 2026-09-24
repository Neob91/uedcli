# Spec — GUI builder brushes

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** Let a GUI session build a parametric shape (cube/cylinder/cone/sheet/staircase, plus the
2D-profile sweeps extrude/revolve), see it rendered as UED22's red **builder brush** — a single
scratch brush actor, not yet part of the level — reposition/rotate/re-shape it, then press **Add** or
**Subtract** to clone it into a new placed brush with that CSG operation. All of this reuses the
existing model-side brush machinery; no brush-geometry or CSG logic is duplicated in the GUI frontend
(`web/`) or written fresh for this feature.

**Add/Subtract do not consume or modify the builder brush.** Each press clones the builder brush's
CURRENT actor — same shape/`Location`/`Rotation`/`PrePivot`/other props, a freshly allocated Name,
`CsgOper` set to `CSG_Add` or `CSG_Subtract` per which button was pressed — into a **new staged
actor** in the project's existing per-session staging store (`uedcli/serve/snapshots.py`, the same
"unsaved" store `actor move` already stages into). The builder brush itself is left exactly as it
was, ready for another Add/Subtract. The staged clone reaches the trunk only when the user hits the
existing **Save** action — same as any other staged edit.

**Non-goals.**

- **`brush build spiral`** (spiral staircase) is excluded from the builder-brush shape registry.
  `builders.spiral_staircase()` returns `list[Brush]` (N+1 actors: one column + one tread per step,
  `uedcli/builders.py:638`) — it cannot be represented as UED22's single builder-brush actor. It stays
  CLI/pipe-only (`brush build spiral | actor add -`), unchanged.
- No multi-builder-brush support (settled: one per session, see "Data model").
- No new CLI verb, flag, or `--tree` kind. The CLI never resolves, reads, or writes a builder brush
  (settled during design). Reuse happens at the Python-function level, not by making the builder-brush
  box reachable from `_resolve_level_source`/`--tree`.
- No persistent `CsgOper` on the builder brush itself. `CsgOper` is stamped only at Add/Subtract time,
  on the CLONE — the builder brush has no add-vs-subtract "mode" to toggle.
- No conflict-detection/merge machinery for the builder brush (unlike staged actor `Location` edits,
  `uedcli/serve/edits.py`). A session's builder brush is session-pinned (see "Data model") and is never
  silently overwritten by another session's changes, so there is nothing to reconcile. A staged
  Add/Subtract clone likewise has no conflict to detect: it is a brand-new Name, so Save can never find
  a trunk-side change to compare it against.
- Texture/solidity/folder/label/base-name/mover-class — the extra flags `_common_build_opts` adds to
  every `brush build <shape>` subparser (`uedcli/cli/parsers/brush.py:121-151`) — are NOT part of the
  builder-brush "build" call. Only each shape's own geometry params are. See "Builder registry".

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
  handles both, and every other prop, uniformly. Editing the builder brush's Location, Rotation, or
  any other property reuses THAT one path (see "Reuse strategy") — no dedicated move/rotate operation.
  *(Owner ruling, this design round: the GUI backend must never fork Location/Rotation away from
  regular props the way `SceneActor`/`StagingStore` already do — see `gui_backend_no_special_cased_
  props` memory and the follow-up item below.)*
- **`StagingStore` (`uedcli/serve/snapshots.py`) does not fit the builder brush's OWN state.** It
  stages `Location` edits to actors that already exist in the trunk — `stage()`/`save_staged()`
  require `query.resolve_actor_name` to resolve against the trunk first (`edits.py:74-76`). The
  builder brush itself has no trunk baseline, so its own live-editing state (Tier 0/Tier 1 below) needs
  a separate, smaller mechanism rather than bending `StagingStore`'s baseline/conflict fields onto a
  case they don't apply to.
- **`StagingStore` DOES need to grow a new capability for Add/Subtract's output, though.** Today it
  only stages a MOVE of an existing trunk actor — there is no path for staging a brand-new actor that
  isn't in the trunk yet. Add/Subtract needs exactly that (a staged NEW actor, not a staged move), so
  this spec requires extending `StagingStore`/`edits.py` with a "stage a new actor" operation, alongside
  the existing "stage a move" one — real new work on an existing module, not free reuse. Once staged,
  it needs no conflict handling (see "Non-goals": a fresh Name can't collide with a concurrent trunk
  change), so it is simpler than the existing move-staging path, not harder.
- **`GET /api/session/{id}/scene` serves the raw trunk, unmodified by session state.** Staged actor
  moves are NOT merged into it server-side — only `POST /rebuild`'s CSG solve does that, via
  `edits.apply_staged_overlay` (`uedcli/serve/app.py:551-560`). The builder brush follows the same
  principle: it is served through its own endpoint (below), not folded into `/scene`'s actor list.
- **`SceneActor` (`uedcli/serve/scene.py`) itself special-cases `location`/`rotation` as dedicated
  fields, separate from its generic `props` list — the exact anti-pattern this spec's props ruling
  rejects, just pre-existing.** This spec deliberately does NOT reuse `SceneActor` for the builder
  brush's own responses (see "API surface") rather than propagate that special-casing into new code.
  Fixing `SceneActor` itself is out of scope here — it ripples into `/scene`, `/rebuild`, staged
  moves, and existing FE/test code — and is filed separately at p1:
  `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/`.
- **Two build pins, two failure postures — the precedent this spec's persistence follows.**
  `uedcli/serve/build_pin.py` docstring: `sessions/<sid>/build.json` is "this session's own current
  pin while it edits — corrupt-and-instruct, since a session's own state is closer to 'work' than to a
  cache"; `build/pin/<level>/current.json` (this spec renames to `levels/<level>/build.json`, see
  "On-disk layout") is "the level's pin ... silent-degrade to 'never built' on any read failure, since
  it's purely regenerable." The builder brush's own two tiers (below) copy this exact split, with one
  difference noted under "Error handling": a *persisted* builder brush is not regenerable the way a
  build pin is, so its level-tier file does NOT get the silent-degrade posture.

## Data model

**The builder brush itself — two tiers, never touches the trunk:**

1. **Tier 0 — session, git-untracked, the session's live working copy.** At most one builder-brush
   actor per session (settled: matches UED22, which has exactly one builder brush at a time; building
   a new shape replaces it). Every live interaction (build/rebuild-shape, or a prop edit — Location,
   Rotation, or anything else settable, all through the one generic path) writes here immediately.
   **Session-pinned**: once a session has created a builder brush, it is NEVER refreshed
   from Tier 1 for the rest of that session's life, even if another session's Save changes Tier 1 for
   the same level. A brand-new session seeds its Tier 0 from whatever Tier 1 currently holds. This
   mirrors `build_pin.py`'s session pin pinning to one `(geom_hash, light_hash)` instead of always
   tracking the level's latest build.
2. **Tier 1 — level, git-untracked, persisted across sessions.** One box per level. Updated only by
   the existing **Save** action (`POST /api/session/{id}/save`) — this spec extends that route to
   also flush the session's Tier 0 builder brush into Tier 1. Plain overwrite, no conflict check
   (there is nothing to diverge from: per Tier 0's pinning rule above, a session's working copy never
   observes concurrent Tier-1 changes mid-session).

**Add/Subtract — a clone into the existing staging store, not a trunk write:**

Pressing **Add** or **Subtract** clones Tier 0's CURRENT actor (shape/`Location`/`Rotation`/`PrePivot`/
other props verbatim) into a new actor with a freshly `allocate_name`d Name (invariant D6,
`dev/docs/architecture.md`) and `CsgOper` set to `CSG_Add` or `CSG_Subtract` per the button pressed.
This new actor is **staged** — written into the same per-session "unsaved" staging store
`actor move` already uses (`uedcli/serve/snapshots.py`), via the new "stage a new actor" capability
described under "Background". **Tier 0 is not read-and-cleared, only read** — the builder brush is
completely unaffected, exactly as if Add/Subtract had never been pressed, matching UED22 and enabling
the real workflow of pressing Subtract right after Add on the same shape (e.g. to carve a doorway).

The staged clone reaches the trunk only when the user hits the existing **Save** action, same as any
other staged edit — there is no separate "commit" step. Save's existing flush logic (today:
staged-`Location`-move application) gains a second job: applying every staged NEW actor via the trunk
write path `actor add -` already uses. These two staged-edit kinds (move an existing actor, add a new
one) are applied independently within one Save call — a failure/conflict in one is not blocked by the
other.

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
levels/<level>/builder-brush.json                          (new — Tier 1)
sessions/<sid>/{index.json, staged.json, build.json, builder-brush.json}   (new file alongside the
                                                                             existing three — Tier 0)
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
`brush.py:121-151`), since `--at` is handled by the separate `move`/`rotate` operations on the
builder-brush box, and `--csg` is not a builder-brush property at all — it is chosen only by which of
Add/Subtract the user presses (see "Non-goals").

**Icon** has no CLI analog — one small new hand-authored table, shape id → icon name/path, is the only
new declarative data this feature adds per shape.

`spiral` is excluded from this registry entirely (see "Non-goals").

## API surface

All new routes are session-scoped, matching every existing GUI route (`/api/session/{id}/...`,
`uedcli/serve/app.py`) — not the shape-in-URL-path form floated early in design.

**Response shape — builder-brush-specific, NOT `SceneActor`.** Every route below that returns the
builder-brush actor uses one new shape: geometry for rendering (reusing `BrushHighlight`'s
poly/local-origin fields, `uedcli/serve/scene.py:89-118` — geometry rendering is unrelated to the
props special-casing this spec avoids) plus **one generic `props` list** covering every property,
Location and Rotation included, with no dedicated `location`/`rotation` fields. This is deliberately
narrower than `SceneActor` (see "Background") rather than propagating its special-casing.

- `GET /api/builders` — the shape registry above. No session; static per install (derived from the
  CLI parser tree).
- `POST /api/session/{id}/builder-brush/build` `{shape, params}` — construct/rebuild Tier 0's brush
  geometry via `builders.<shape>(**params)`, then swap-in-place via the extracted pure function
  described below. If Tier 0 has no builder brush yet, creates one via `make_brush_actor` at a default
  Location (world origin); `make_brush_actor` requires SOME `CsgOper` to produce valid T3D, so it is
  given `CsgOper=CSG_Add` as an inert default — never shown or settable through `prop` (see
  "Non-goals"), and irrelevant once Add/Subtract stamps its own value on the clone. Returns the
  updated actor in the response shape above.
- `POST /api/session/{id}/builder-brush/prop` `{name, value}` — set ONE property on Tier 0's actor,
  through the same generic plan/apply `actor prop set` uses model-side (`uedcli/propedit/edit.py`) —
  covers `Location`, `Rotation`, and any other settable property uniformly, no shape recompute, no
  per-field endpoint. Returns the updated actor in the response shape above.
- `GET /api/session/{id}/builder-brush` — current Tier 0 actor (same response shape as `build`
  returns), or `null` if the session has none yet.
- `DELETE /api/session/{id}/builder-brush` — discard Tier 0 (does not touch Tier 1, the staging store,
  or the trunk).
- `POST /api/session/{id}/builder-brush/add` and `POST /api/session/{id}/builder-brush/subtract` —
  clone Tier 0's current actor into a new staged actor with `CsgOper` stamped per the route, per "Data
  model". Returns the new actor's allocated Name and its serialized form (`SceneActor`/`BrushHighlight`
  — this one DOES land in the trunk on Save and become an ordinary actor, so it goes through the
  regular actor read path like any other trunk actor once staged; the follow-up item covers fixing
  that path's own special-casing). Tier 0 is left unchanged.
- `POST /api/session/{id}/save` (existing route, `app.py:829`) — extended to also (a) flush Tier 0 →
  Tier 1 for the builder brush, and (b) apply every staged NEW actor (from `add`/`subtract`) into the
  trunk, alongside its existing staged-`Location`-move flush.

## Reuse strategy (no logic duplication, backend or frontend)

- **CLI stays untouched** — no `--tree builder-brush` kind, no new argparse. The serve layer calls
  Python functions directly, the same way `uedcli/serve/edits.py` already calls the model-side
  `actor move` write pattern directly rather than shelling out to the CLI (`edits.py`'s own docstring:
  "Writes go through `TrunkLevelSource`, the exact model-side path `cli/commands/actor/edit.py`'s
  `_move` already uses").
- **`prop` reuses `propedit`'s plan/apply, not a hand-rolled Location/Rotation setter.** The route
  builds a `PropToken`/plan the same way `actor prop set` does (`uedcli/propedit/edit.py`) against
  Tier 0's single actor, so `Location`'s typed-field validation (Decimal precision, PrePivot
  invariant D8) and any struct-typed prop's grammar are enforced identically to the CLI, with zero
  reimplementation — and zero special-casing of which property is being set.
- **The "swap only PolyList" logic in `_replace()`** (`uedcli/cli/commands/brush/edit.py:502-543`,
  specifically lines 537-541) is extracted into a small pure function — proposed home `builders.py`,
  alongside the other builder functions — called by both the CLI's `_replace()` (unchanged behavior)
  and the new serve-layer `build` route.
- **Frontend renders the builder brush exactly like it renders any other brush actor** — the `build`/
  `GET` responses reuse `SceneActor`/`BrushHighlight`'s existing shape, so the FE's existing
  brush-rendering code (whatever already consumes a `SceneActor.brush` from `/scene`) needs no new
  per-builder-brush branch beyond wiring up the new endpoint and (per the registry) a generic
  param-form renderer — never a per-shape hand-written form.
- **Add/Subtract reuse the trunk write path at Save time, not a new one.** Once staged, a new actor
  from `add`/`subtract` is applied into the trunk via the exact same path `actor add -` already uses
  (`TrunkLevelSource.save` on a freshly allocated Name) — Save's extended flush calls that path, it
  does not reimplement "how a new actor gets into the trunk". The only genuinely new code is the
  staging-store capability noted under "Background" (staging a NEW actor, not a move) and the
  clone-with-CsgOper-override step itself (copy an `Actor`, mint a Name, set `CsgOper`).

## Error handling

- Same rule as every other GUI route: no Python exception reaches the user; a build/move/add/subtract
  failure returns a structured error naming the offending value.
- **Tier 0 (session) read failure**: corrupt-and-instruct — same posture as `sessions/<sid>/build.json`
  (`build_pin.py`'s `SessionPointerCorruptError`), since it is the session's own unsaved work.
- **Tier 1 (level) read failure**: corrupt-and-instruct, NOT silent-degrade — this is the one place
  this feature's persistence deliberately does NOT copy `levels/<level>/build.json`'s posture. A build
  pin is purely regenerable (a fresh Rebuild replaces it); a persisted builder brush is the user's
  actual placed shape/position and cannot be regenerated from nothing, so losing it silently would be
  a real data loss, not a cheap cache miss.
- `add`/`subtract`'s geometry validation reuses whatever `actor add -`/`brush replace`'s existing
  `validate_brush` already enforces (`edit.py:541`, `geometry.validate_brush`) — a degenerate shape is
  rejected the same way it already is on every other model-side write path.
- **A staged NEW actor cannot conflict at Save** (see "Non-goals") — its Name did not exist before it
  was staged, so there is no trunk-side value to compare against; Save simply applies it. This differs
  from the existing staged-`Location`-move path, which does need the conflict check because the target
  actor already existed and may have changed trunk-side since staging.

## Testing

- **Backend**: Tier 0 write/read round-trip (build; `prop` setting `Location`, `Rotation`, and at
  least one other property, all through the one endpoint — no code path that special-cases which
  property name was sent); the extracted poly-swap function
  produces byte-identical results to today's `_replace()` for the same inputs (no behavior change to
  the CLI verb); Save flushes Tier 0 → Tier 1 correctly and leaves Tier 0 untouched; a session created
  AFTER another session's Save picks up the new Tier 1 state, while an already-running session does
  not (the pinning rule); `add`/`subtract` clone Tier 0's current actor (shape/Location/Rotation/other
  props preserved, fresh Name, correct `CsgOper`) into the staging store and leave Tier 0 byte-for-byte
  unchanged; pressing Add then Subtract on the same builder brush produces two independent staged
  actors, not one overwritten; Save applies a staged new actor via the same path `actor add -` uses,
  with no conflict check and no dependency on any staged move in the same Save call succeeding or
  failing; `GET /api/builders` output matches the real argparse subparser tree (a regression test
  comparing the two, so a new shape/param added to `builders.py`+its parser is caught if the registry
  route wasn't updated to expose it — though per design it should need no update, since it's pure
  introspection).
- **Frontend**: the shape-picker form renders purely from `GET /api/builders` with no per-shape code;
  adding a fake extra param to the registry response in a test renders a generic field for it.
- Scope tests to the touched module while iterating (`bin/test -k serve`, `web/`'s vitest run); full
  suite once before merge, per `dev/docs/rules/tests.md`.

## Refs

- `dev/docs/architecture.md` "The core write pattern", "The `LevelSource` seam and `--tree`" (the
  seam this feature deliberately does NOT extend), module map entries for `builders.py`/`profile.py`.
- `uedcli/cli/commands/brush/edit.py:502-543` (`_replace`, the poly-swap this feature extracts).
- `uedcli/cli/parsers/brush.py:121-278` (`_common_build_opts` + all `brush build` shape subparsers —
  the registry's source of truth).
- `uedcli/serve/snapshots.py`, `uedcli/serve/edits.py` (`StagingStore`/staged-actor-move flow — the
  precedent Tier 0/Tier 1's own persistence follows without reusing the store itself, AND the actual
  store Add/Subtract stage their new actors into, extended with a new "stage a new actor" capability).
- `uedcli/serve/build_pin.py` (the two-pin, two-failure-posture precedent Tier 0/Tier 1 copy).
- `uedcli/build_cache.py`, `uedcli/preview_game.py` (on-disk paths renamed by this spec).
- `uedcli/serve/scene.py:89-118` (`BrushHighlight` — its geometry fields are reused for the builder
  brush's own rendering; its parent `SceneActor` is NOT reused, see "Background"/"API surface").
- `uedcli/propedit/edit.py`, `uedcli/propedit/fields.py:275` (`TYPED_FIELDS` — the generic plan/apply
  the new `prop` route calls, unmodified).
- `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/` (p1 follow-up: fold
  `SceneActor`'s dedicated `location`/`rotation` fields into its generic `props`, out of scope here).
- Memory `gui_backend_no_special_cased_props` (owner ruling this spec round: never special-case
  Location/Rotation away from regular props in the GUI backend).
