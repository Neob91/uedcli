+++
priority = "p?"
kind = "unknown"
summary = "Geometry bundle (unattended build #3)"
+++

# Geometry bundle (unattended build #3)

— BUILT 2026-07-18 (spec
`spec.md`; plan `plan.md`; decisions
2026-07-18 20:09 UTC). Two offline items: (8) **`brush build staircase` redo** — `builders.staircase`
now returns `list[Brush]` (one convex box per step, filled floor-to-tread column) instead of one
non-convex brush; each box passes `level doctor` (the old single brush tripped 60+ phantom
watertight errors and hung one `rise` below the floor); `_build_brushes` unwraps the list (N actors
`Staircase0…`); parity goldens re-blessed offline (`stair_*` only); the UED single-brush reference
preserved as engine-fact guard. **[SUPERSEDED 2026-07-21: staircase reverts to ONE non-convex brush
(T-junctions handled by the now T-junction-aware `check_watertight`); the guard test is now
`test_builder_matches_ued_linear_stair_taxonomy`. See the 2026-07-21 entry above / `direction/generators.md`
12:06 UTC.]** (9)
**`brush replace <name> -`** — in-place shape swap taking only the piped generator's PolyList while
keeping the target's Name/`order_value`/Group/CsgOper/actor-level PolyFlags/Location/PrePivot (7
clean error paths, all exit-2/no-traceback; empty stdin → exit 0); supersedes the dropped `brush
resize`. Post-build 2-cold-reviewer gate run: added the missing `brush replace` regression suite
(7 dispatch paths + on-disk rank-preservation round-trip) + doc fixes. Python suite green (1713);
committed HEAD verified green in isolation.
