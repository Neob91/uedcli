# Spec — GUI builder brushes

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** Let a GUI session build a parametric shape (cube/cylinder/cone/sheet/staircase, plus the
2D-profile sweeps extrude/revolve), see it rendered as UED22's red **builder brush** — a single
scratch brush actor, not yet part of the level — reposition/rotate/re-shape/toggle CSG add-vs-subtract
on it, and commit it into the trunk as a real placed brush (CSG Add/Subtract). All of this reuses the
existing model-side brush machinery; no brush-geometry or CSG logic is duplicated in the GUI frontend
(`web/`) or written fresh for this feature.

**Non-goals.**

- **`brush build spiral`** (spiral staircase) is excluded from the builder-brush shape registry.
  `builders.spiral_staircase()` returns `list[Brush]` (N+1 actors: one column + one tread per step,
  `uedcli/builders.py:638`) — it cannot be represented as UED22's single builder-brush actor. It stays
  CLI/pipe-only (`brush build spiral | actor add -`), unchanged.
- No multi-builder-brush support (settled: one per session, see "Data model").
- No new CLI verb, flag, or `--tree` kind. The CLI never resolves, reads, or writes a builder brush
  (settled during design). Reuse happens at the Python-function level, not by making the builder-brush
  box reachable from `_resolve_level_source`/`--tree`.
- No conflict-detection/merge machinery for the builder brush (unlike staged actor `Location` edits,
  `uedcli/serve/edits.py`). A session's builder brush is session-pinned (see "Data model") and is never
  silently overwritten by another session's changes, so there is nothing to reconcile.
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
- **Whole-actor edits already exist and need no new logic.** `actor move`/`actor rotate`/`actor prop
  set` are pure model-side verbs (load → mutate one field → `LevelSource.save`,
  `dev/docs/architecture.md` "The core write pattern"). Moving/rotating the builder brush and toggling
  its `CsgOper` (add vs subtract) reuse these same mutations — only the target (a builder-brush box,
  not the trunk) differs.
- **`StagingStore` (`uedcli/serve/snapshots.py`) does NOT fit.** It stages `Location` edits to actors
  that already exist in the trunk — `stage()`/`save_staged()` require `query.resolve_actor_name` to
  resolve against the trunk first (`edits.py:74-76`). A builder brush has no trunk baseline, so this
  spec introduces a separate, smaller mechanism (below) rather than bending `StagingStore`'s
  baseline/conflict fields onto a case they don't apply to.
- **`GET /api/session/{id}/scene` serves the raw trunk, unmodified by session state.** Staged actor
  moves are NOT merged into it server-side — only `POST /rebuild`'s CSG solve does that, via
  `edits.apply_staged_overlay` (`uedcli/serve/app.py:551-560`). The builder brush follows the same
  principle: it is served through its own endpoint (below), not folded into `/scene`'s actor list.
- **Two build pins, two failure postures — the precedent this spec's persistence follows.**
  `uedcli/serve/build_pin.py` docstring: `sessions/<sid>/build.json` is "this session's own current
  pin while it edits — corrupt-and-instruct, since a session's own state is closer to 'work' than to a
  cache"; `build/pin/<level>/current.json` (this spec renames to `levels/<level>/build.json`, see
  "On-disk layout") is "the level's pin ... silent-degrade to 'never built' on any read failure, since
  it's purely regenerable." The builder brush's own two tiers (below) copy this exact split, with one
  difference noted under "Error handling": a *persisted* builder brush is not regenerable the way a
  build pin is, so its level-tier file does NOT get the silent-degrade posture.

## Data model — three tiers

1. **Tier 0 — session, git-untracked, the session's live working copy.** At most one builder-brush
   actor per session (settled: matches UED22, which has exactly one builder brush at a time; building
   a new shape replaces it). Every live interaction (build/rebuild-shape, move, rotate, CSG toggle)
   writes here immediately — same write-immediately timing as the existing staged-actor-move flow,
   just one step removed (that flow's "unsaved" layer is `StagingStore`; this feature's is the new
   store below). **Session-pinned**: once a session has created a builder brush, it is NEVER
   refreshed from Tier 1 for the rest of that session's life, even if another session's Save changes
   Tier 1 for the same level. A brand-new session seeds its Tier 0 from whatever Tier 1 currently
   holds. This mirrors `build_pin.py`'s session pin pinning to one `(geom_hash, light_hash)` instead
   of always tracking the level's latest build.
2. **Tier 1 — level, git-untracked, persisted across sessions.** One box per level. Updated only by
   the existing **Save** action (`POST /api/session/{id}/save`) — this spec extends that route to
   also flush the session's Tier 0 builder brush into Tier 1, alongside its existing staged-`Location`
   flush. Plain overwrite, no conflict check (there is nothing to diverge from: per Tier 0's pinning
   rule above, a session's working copy never observes concurrent Tier-1 changes mid-session).
3. **Tier 2 — the trunk (git-tracked).** Reached only by a separate, explicit **commit** action
   (independent of Save) — the CSG Add/Subtract equivalent. Reads Tier 0 (the session's live working
   copy) directly and writes it into the trunk as a new actor with a freshly `allocate_name`d Name
   (invariant D6, `dev/docs/architecture.md`) — the same outcome `actor add -` already produces from
   piped T3D. Per the "post-commit state" decision: the builder brush is left in place afterward
   (Tier 0 unchanged), ready for the next Add/Subtract — matches UED22, and enables the real workflow
   of subtracting the same brush just added (e.g. to carve a doorway).

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
`brush.py:121-151`), since those are handled by separate actor-level operations on the builder-brush
box (move/rotate/CSG-toggle), not by the build call (see "Non-goals").

**Icon** has no CLI analog — one small new hand-authored table, shape id → icon name/path, is the only
new declarative data this feature adds per shape.

`spiral` is excluded from this registry entirely (see "Non-goals").

## API surface

All new routes are session-scoped, matching every existing GUI route (`/api/session/{id}/...`,
`uedcli/serve/app.py`) — not the shape-in-URL-path form floated early in design.

- `GET /api/builders` — the shape registry above. No session; static per install (derived from the
  CLI parser tree).
- `POST /api/session/{id}/builder-brush/build` `{shape, params}` — construct/rebuild Tier 0's brush
  geometry via `builders.<shape>(**params)`, then swap-in-place via the extracted pure function
  described below. If Tier 0 has no builder brush yet, creates one via `make_brush_actor` at a default
  Location (world origin) and `CsgOper=CSG_Add`. Returns the updated actor, serialized the same way
  `scene.py` already serializes any brush actor (`SceneActor`/`BrushHighlight`,
  `uedcli/serve/scene.py:89-118,208-231`) — reusing that serialization is what keeps the FE from
  needing its own brush-to-render-shape logic.
- `POST /api/session/{id}/builder-brush/move` `{location}` — `Location` only, no shape recompute.
- `POST /api/session/{id}/builder-brush/rotate` `{rotation}`.
- `POST /api/session/{id}/builder-brush/csg` `{op: "add" | "subtract"}`.
- `GET /api/session/{id}/builder-brush` — current Tier 0 actor (same serialized shape as `build`
  returns), or `null` if the session has none yet.
- `DELETE /api/session/{id}/builder-brush` — discard Tier 0 (does not touch Tier 1 or the trunk).
- `POST /api/session/{id}/builder-brush/commit` — Tier 0 → Tier 2 (the trunk), per "Data model" #3.
  Returns the newly allocated trunk actor Name. Tier 0 is left unchanged afterward.
- `POST /api/session/{id}/save` (existing route, `app.py:829`) — extended to also flush Tier 0 → Tier
  1 for the builder brush, alongside its existing staged-`Location` flush.

## Reuse strategy (no logic duplication, backend or frontend)

- **CLI stays untouched** — no `--tree builder-brush` kind, no new argparse. The serve layer calls
  Python functions directly, the same way `uedcli/serve/edits.py` already calls the model-side
  `actor move` write pattern directly rather than shelling out to the CLI (`edits.py`'s own docstring:
  "Writes go through `TrunkLevelSource`, the exact model-side path `cli/commands/actor/edit.py`'s
  `_move` already uses").
- **The "swap only PolyList" logic in `_replace()`** (`uedcli/cli/commands/brush/edit.py:502-543`,
  specifically lines 537-541) is extracted into a small pure function — proposed home `builders.py`,
  alongside the other builder functions — called by both the CLI's `_replace()` (unchanged behavior)
  and the new serve-layer `build` route.
- **Frontend renders the builder brush exactly like it renders any other brush actor** — the `build`/
  `GET` responses reuse `SceneActor`/`BrushHighlight`'s existing shape, so the FE's existing
  brush-rendering code (whatever already consumes a `SceneActor.brush` from `/scene`) needs no new
  per-builder-brush branch beyond wiring up the new endpoint and (per the registry) a generic
  param-form renderer — never a per-shape hand-written form.

## Error handling

- Same rule as every other GUI route: no Python exception reaches the user; a build/move/commit
  failure returns a structured error naming the offending value.
- **Tier 0 (session) read failure**: corrupt-and-instruct — same posture as `sessions/<sid>/build.json`
  (`build_pin.py`'s `SessionPointerCorruptError`), since it is the session's own unsaved work.
- **Tier 1 (level) read failure**: corrupt-and-instruct, NOT silent-degrade — this is the one place
  this feature's persistence deliberately does NOT copy `levels/<level>/build.json`'s posture. A build
  pin is purely regenerable (a fresh Rebuild replaces it); a persisted builder brush is the user's
  actual placed shape/position and cannot be regenerated from nothing, so losing it silently would be
  a real data loss, not a cheap cache miss.
- `commit`'s geometry validation reuses whatever `actor add -`/`brush replace`'s existing
  `validate_brush` already enforces (`edit.py:541`, `geometry.validate_brush`) — a degenerate shape is
  rejected the same way it already is on every other model-side write path.

## Testing

- **Backend**: Tier 0 write/read round-trip (build, move, rotate, csg toggle); the extracted
  poly-swap function produces byte-identical results to today's `_replace()` for the same inputs (no
  behavior change to the CLI verb); Save flushes Tier 0 → Tier 1 correctly and leaves Tier 0 untouched;
  a session created AFTER another session's Save picks up the new Tier 1 state, while an
  already-running session does not (the pinning rule); commit writes a real trunk actor via the same
  path `actor add -` uses, with a freshly allocated Name, and leaves Tier 0 unchanged afterward;
  `GET /api/builders` output matches the real argparse subparser tree (a regression test comparing the
  two, so a new shape/param added to `builders.py`+its parser is caught if the registry route wasn't
  updated to expose it — though per design it should need no update, since it's pure introspection).
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
  precedent this feature's Tier 0/Save split follows, without reusing the store itself).
- `uedcli/serve/build_pin.py` (the two-pin, two-failure-posture precedent Tier 0/Tier 1 copy).
- `uedcli/build_cache.py`, `uedcli/preview_game.py` (on-disk paths renamed by this spec).
- `uedcli/serve/scene.py:89-118,208-231` (`BrushHighlight`/`SceneActor` — reused for the builder
  brush's own serialization).
