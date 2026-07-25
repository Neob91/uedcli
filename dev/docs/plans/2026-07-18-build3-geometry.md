# Plan: build group #3 — geometry (items 8 & 9)

Ephemeral build scratch for the two offline geometry items on `to-build.md`. Durable record lands
in `architecture.md` / `docs/usage.md` / `decisions.md` per item.

## Item 8 — `brush build staircase` redo
Spec + full decision: `specs/2026-07-18-staircase-redo.md`, `decisions.md` 2026-07-18 20:09 UTC.
Spec-review gate run (two cold reviewers), all findings resolved in the spec. Built:
`builders.staircase` now returns `list[Brush]` (one convex box per step), `dispatch._build_brushes`
unwraps it, goldens re-blessed offline, tests rewritten + doctor-clean test added. DONE.

## Item 9 — `brush replace <name> -`  (well-specified; no separate spec gate)

**Goal.** In-place SHAPE SWAP: replace a trunk brush's PolyList/geometry from a piped generator T3D
snippet on stdin (`-`), KEEPING the target's Name, `order_value` (CSG rank), Group, CsgOper,
PolyFlags, AND its old Location/PrePivot. The incoming shape's own Location/PrePivot/Name are
ignored — only its polys are taken. Model-side (no editor). Supersedes the dropped `brush resize`.

**Design (mirrors `brush clip`).**
1. Parser: `brush replace <name> <shape>` where `<shape>` is the literal `-` (sole shape source,
   the `build → add -` T3D-snippet stdin convention — NOT a name list). `+ _target_flag`.
2. Handler:
   - Read stdin. **Empty/whitespace-only stdin → clean no-op, exit 0** (per the `-` convention).
   - Parse the snippet with `parse_t3d_actors`, drop the transient builder brush
     (`is_builder_brush`), keep brush actors. **0 brush actors (non-empty input) → clean error,
     exit 2** ("no brush geometry in the T3D input"). **>1 brush actor → clean error, exit 2**
     (naming the count — a single-shape swap is unambiguous; a staircase/spiral pipe is rejected
     rather than silently dropping boxes).
   - `src.load()`; `resolve_actor_name(name)` — unknown → clean error naming the value, exit 2.
   - target `= level.actors[canonical]`; `target.brush is None` → "not a brush", exit 2.
   - **Swap polys only:** `target.brush.polys = incoming.brush.polys`. Keep the target `Brush`
     object (its `model_name` stays `Model_<name>`, matching the actor's `Brush=` prop), and keep the
     actor's Location/PrePivot/props (CsgOper/Group/PolyFlags/Rotation) untouched.
   - `validate_brush(target.brush)`; `src.save(verb="replace", touched=[canonical])`. The
     TrunkLevelSource.save same-name path preserves `order_value` automatically (name still in
     `level.actors` ⇒ `resolved[name]=self._ranks[name]`).
3. Regressions: identity preservation (rank/Group/CsgOper/Location/PrePivot kept, geometry swapped),
   unknown name → exit 2, empty stdin → exit 0 no-op, non-brush input → exit 2, >1 brush → exit 2,
   not-a-brush target → exit 2. Plus a usage.md entry.
