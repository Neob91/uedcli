# Reported coordinates — why a printed number is not the stored one

Engineering decisions about the coordinates uedcli reports (`actor bbox`, `brush vertex list`,
`stash`/`prefab` summaries, the `rotate`/`scale` pivot lines), versus the ones it stores
(`uedcli/emit.py`, the trunk) and the ones it decides on (`doctor`, the CSG core, preview cameras).
Owner rulings about the pivot live in [`../direction/conventions.md`](../direction/conventions.md).

UE1's GMath rotator table is not exact: a 180° yaw carries `sin = -8.742278e-08` rather than 0
(`uedcli/rotation.py`, `uedcli/tests/test_rotation.py`), so a ±64 vertex offset leaks ~6e-06 into the
cross axis. A brush whose trunk says exactly `Y=228` computes to `227.999994`.

## A derived coordinate is tolerance-snapped for reporting, never for deciding

`commands.actor.query._bbox_of`, `query._coord_component` and `stashlib.format_summary` run their values through
`emit.clean` (`CLEAN_EPS` = 0.001) before formatting. `writes.union_bounds`, `writes.actor_bounds`
and `rotation.world_vertices` do not — every consumer that makes a geometric judgement reads raw.

**Why:** printing `227.999994` for geometry whose trunk is exact reads as "the rotate pushed my
geometry off-grid", a false alarm; the noise is ~170x below `doctor.WELD` (1e-3), so snapping hides
nothing real. But `doctor`'s and the CSG core's tolerances exist to catch near-degenerate geometry,
and feeding them pre-cleaned values would mask the faults they detect. The split is display vs
decision, not module boundaries.

**Rejected:** snapping inside `union_bounds`/`world_vertices` — one line instead of three, but it
puts the cleaned value in front of `doctor`, `preview_native` and the Rust CSG core.
**Rejected:** not snapping and documenting the noise — measured cost: an agent building
`TubePlatform` read the raw numbers as evidence its rotate had gone wrong.
**Refs:** `uedcli/cli/commands/actor/query.py` (`_bbox_of`) · `uedcli/query.py` (`_coord_component`) ·
`uedcli/stashlib.py` (`format_summary`) · `uedcli/emit.py` (`clean`, `CLEAN_EPS`) ·
`uedcli/tests/test_bbox.py` (`test_bbox_snaps_gmath_rotator_noise_to_the_grid`,
`test_bbox_snap_preserves_a_genuine_fraction`)

## `--within-bbox` compares within the same tolerance

`writes.aabb_within` widens the outer box by `CLEAN_EPS` per axis.

**Why:** the two sides are different kinds of number. `inner` is raw `actor_bounds` (carrying the
rotator noise); `outer` is authored — typed by a user, or piped from `actor bbox --field min/max`,
which reports snapped values. An exact compare makes a rotated actor fail to be contained in its own
reported bounding box, so the documented `bbox --field min | find --within-bbox` composition returns
an empty set at exit 0. That regression shipped 2026-07-26 (`5d4506e`) and was caught by the build
gate; `architecture.md`'s same-bounds claim holds only with this tolerance.

**Rejected:** reporting raw values from `--field`/`--json` and snapping only the human text — it
makes the machine-readable output the noisy one, and leaves two spellings of the same box.
**Refs:** `uedcli/writes.py` (`aabb_within`) · `uedcli/tests/test_bbox.py`
(`test_a_rotated_actor_is_within_its_own_reported_bbox`) · `uedcli/tests/test_find_spatial.py` ·
[`../architecture.md`](../architecture.md) "Spatial filtering"

## One formatter for reporting, one for files

`emit.fmt_coord` (string) and `emit.num_coord` (JSON number) are the single definitions;
`commands.brush.edit._fmt_coord_component`, `commands.brush.vertex._num_coord_component`,
`query._coord_component` and `query.list_mover_keys` all delegate. They are separate from `fmt_vertex`/`fmt_loc`, which pad to
T3D's fixed 6-dp form because a file is their destination.

**Why:** four independent copies of "int when integral, else decimal" had already drifted —
`query._coord_component` used `str(d)` (so `2.500000` kept its zeros) and was unsnapped, so
`brush vertex list` and `actor bbox` printed different numbers for the same corner. Snapping is not
folded into `fmt_coord`: a caller reporting a derived coordinate pairs it with `clean`, while one
echoing an authored value formats it as given.

**Rejected:** `fmt_coord` cleaning internally — it would silently snap authored input, so
`--pivot 227.9999` would echo as `228` while the code used the real value.
**Refs:** `uedcli/emit.py` (`fmt_coord`, `num_coord`) · `uedcli/cli/commands/brush/edit.py`
(`_fmt_coord_component`) · `uedcli/cli/commands/brush/vertex.py` (`_num_coord_component`) ·
`uedcli/query.py` (`_coord_component`, `list_mover_keys`) · `uedcli/tests/test_bbox.py`
(`test_vertex_list_and_bbox_report_the_same_corner`)

## Every reporting formatter guards its input

`fmt_coord`/`num_coord` take `_guard`, not a bare `Decimal()`.

**Why:** `parse_coord` builds coordinates with `Decimal(p)`, which accepts `inf` and `nan`, and
`int(Decimal("Infinity"))` raises `OverflowError` — which `dispatch()` does not catch, so
`brush scale --to inf,1,1` printed a traceback. `_guard` converts it to `CoordinateError` and the
named exit 2 that `direction/conventions.md` "No Python exception ever reaches the user" requires.

**Rejected:** catching `OverflowError` in `dispatch()` — it turns one formatter's bug into a blanket
catch that would swallow unrelated overflows elsewhere.
**Refs:** `uedcli/emit.py` (`_guard`) · `uedcli/tests/test_emit.py`
(`test_fmt_coord_rejects_a_non_finite_instead_of_tracebacking`)

## A tuple repr is never user-facing output

Pivot and target lines format through the coordinate formatter (`emit.fmt_coord`), not `f"{tuple(...)}"`.

**Why:** `rotated 1 actor(s) about ('1056.0', '228.0', '112.0')` leaked Python's repr — quotes,
brackets, trailing `.0` — into an interface whose every other coordinate is `X,Y,Z`.
`stashlib.format_summary` was worse: it rendered `tuple(int(c) …)`, and `int()` on a `Decimal`
truncates toward zero, so rotator noise at `227.999994` printed as `227` (a whole unit wrong) and a
genuine `-2.5` min corner printed as `-2`, under-reporting the box.

**Rejected:** keeping `int()` and documenting the truncation — a reported box smaller than the real
one reads as "contained" when it is not.
**Refs:** `uedcli/cli/commands/actor/edit.py` (the `rotate` pivot lines) · `uedcli/cli/commands/brush/edit.py` (the `scale` pivot lines) · `uedcli/stashlib.py`
(`format_summary`) · `uedcli/tests/test_stashlib.py`
(`test_summary_bbox_does_not_truncate_a_fraction`, `test_summary_bbox_snaps_rotator_noise`)
