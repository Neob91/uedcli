# Build group #2 — three small offline features (ephemeral plan)

Board: `dev/docs/board/to-build/` items 5–7 (Small features). Offline, model-side, CI-testable.
Delete this plan once the work lands + is folded into the durable docs.

## Feature 5 — `actor bbox <names…|->`

World AABB of the passed actors as ONE enclosing box (single actor → its own box; multiple →
the combined box). This IS the union — **no `--union` flag** (`actor find … | actor bbox -`
already composes it).

- New `actor` sub-parser `bbox`: `names nargs="+"` (names, or the sole token `-` for a stdin
  name list, via `_resolve_target_names`); empty stdin = clean no-op exit 0. `_target_flag`.
- Output extractors (mutually exclusive group):
  - default: four labeled lines to **stdout** — `min/max/size/center` each `x,y,z`.
  - `--field min|max|size|center`: print just that vector, bare `x,y,z` (one value form).
  - `--json`: `{min,max,size,center}` each `{x,y,z}` (numbers), `indent=2` (doctor style).
- Human summary (`bbox of N actor(s)`) → **stderr**.
- Bounds reuse `writes.union_bounds` (→ `writes.actor_bounds`, itself built on the same
  `Location + PostScale·R·MainScale·(v − PrePivot)` transform as `rotation.world_vertices`; it
  additionally handles point actors as a zero-size box at Location). Respects rotation/scale/loc.
- Bad name → `Actor not found: <value>` + exit 2 (the existing `resolve_actor_names` KeyError
  message), never a traceback. Regression-tested.

## Feature 6 — `--json` on `actor find`, `brush poly list`, `project show` (+ `bbox`)

`--json` flag on each; default (non-json) output byte-unchanged. Matches the sole existing
convention (`level doctor --json` → `json.dumps(..., indent=2)`).

- `actor find --json`: JSON array of the matching names (the producer's items are names).
- `brush poly list --json`: `{"actor": name, "polys": [<list_polys rows>]}` (rows already dicts).
- `project show --json`: `{root, game, maps, prefabs, catalog, search_path:[{path,provenance}]}`.

## Feature 7 — `--rotate PITCH,YAW,ROLL` on the generators (`brush build …` / `actor build …`)

SETS the Rotation field absolutely (a fresh generated actor is identity — no override ambiguity).
Degrees, `parse_coord`, matching `actor rotate --to`. Added to `_common_build_opts` (every shape)
and to `actor build`. NOT on `actor add`.

- Convert deg→UU (`rotation.deg_to_uu`); inject `("Rotation", "(Pitch=..,Yaw=..,Roll=..)")` into
  the emitted actor's props (skip a spurious identity `(0,0,0)`), which `emit_actor` emits.
- Off-grid warning (stderr): after setting Rotation, a brush actor's `rotation.world_vertices`
  are checked for integrality; if any component is off the integer grid (> CLEAN_EPS from an
  integer) warn that the editor will snap on import/rebuild. (Point actors: no vertices, no warn.)

## Tests (offline; success + error each)
- `test_bbox.py`: single/multi union, rotation/scale honoured, `--field`, `--json`, stdin `-`,
  empty stdin no-op, unknown name exit 2, mixing `-`+names exit 2.
- extend generator/query/project tests for `--json` + `--rotate` (set field, off-grid warn).

## Docs
- `docs/usage.md`: new `actor bbox` verb; `--json` on find/poly-list/project-show; `--rotate` on
  generators. `architecture.md` unchanged (no module-map change).
