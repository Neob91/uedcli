# Spike: builder world-geometry parity via DEINTERSECTION (2026-06-19)

**Goal:** establish whether each of uedcli's Python brush builders (`cube`, `cylinder`,
`cone`, `staircase`, `spiral_staircase`, `sheet`) can be parity-checked against the live
editor, and how — so the reimplemented builders get continuous regression coverage, not
just offline structural checks. Builds on the DEINTERSECTION world-geometry readout proven
for a single rotated box in
[`2026-06-19-group-rotate-exact-parity.md`](2026-06-19-group-rotate-exact-parity.md). Run on
`dx-lum-uned` (UED22).

## What parity is even possible here

UnrealEd's native `BrushBuilders` are GUI-dialog-only (`WDlgBrushBuilder::OnBuild` →
builder `Build()`); `SET <BuilderClass>` only writes class defaults, so the editor can NOT
be driven to "build a cylinder" from the console. There is therefore **no way to compare
our builder algorithm against UED's**. What is capturable, and what the suite guards, is
that the geometry uedcli EMITS for each builder round-trips through the real importer + CSG
with the same WORLD-CORNER SET — i.e. world-transform/coordinate faithfulness per shape.

Scope limits worth stating plainly (the comparison is an unlabelled vertex SET):
- It does **not** see WINDING — the set is winding-invariant. A flipped face is only
  exercised live, where an inverted solid makes CSG reject/mis-carve it; offline can never
  catch it. (There is no longer an offline face-for-face winding guard: the old
  `test_staircase_matches_ued_reference` fixture-diff test was removed when the linear staircase
  was redone — `direction/generators.md`. **UPDATE 2026-07-21:** the staircase reverted to
  ONE non-convex brush (direction/generators.md, 2026-07-21 12:06 UTC); it is now `OFFLINE_ONLY` in the parity
  suite — NOT live-re-blessed — so its winding rests on reuse of the live-blessed `_face` helper plus
  the offline taxonomy guard `test_builder_matches_ued_linear_stair_taxonomy` and the T-junction-aware
  `check_watertight` reporting clean.)
- A **centrally-symmetric** solid (cube / cylinder / cone) has a vertex set invariant under
  reflection and any rigid transform, so a coordinate MIRROR there is invisible to a set
  match — only the genuinely asymmetric `stair_*` cases catch a mirror.
- It says nothing about `Item` labels or per-face semantics. A cheap offline poly-count
  check is added on top to catch a dropped/duplicated face that moves no unique corner.

## Capture method (the rotate-parity readout, generalized)

For one brush: EDIT PASTE it as `CSG_Subtract`, pre-shifted −32uu on all axes to cancel
EDIT PASTE's +32uu drift → MAP REBUILD (engine carves the world cavity) → BRUSH IMPORT a
large enclosing `CSG_Add` box → BRUSH FROM DEINTERSECTION (cavity → active brush) → BRUSH
EXPORT. The exported `Vertex` lines are the cavity's world vertices, compared by GEOMETRY
(vertex set, count + bidirectional nearest-neighbour) to `world_vertices(actor)`.

## TL;DR (verified)

- **Single-brush builders reconstruct their CORNERS exactly.** `cube` (8 verts), `cylinder`
  (sides 3..16, with/without `angle_offset`), `cone` (sides 3..8, with/without `angle_offset`),
  and the **non-convex `staircase`** (e.g. 26 verts for 4 steps) all match `world_vertices` to
  ≤3e-6uu — i.e. the editor's float32 vertex storage + 6-dp emit floor, no larger residual
  (corner positions only; not the face graph — see scope above). The non-convex staircase
  reconstructing cleanly was the open question; it does.
- **`spiral_staircase` must be captured PER-SLAB, not combined.** It is a LIST of
  overlapping convex slabs; a single DEINTERSECTION over the whole stack invents interior
  vertices where slabs meet at the column (measured: 24 predicted vs 34 editor, ~38uu worst
  error). Capturing each slab into its own fresh cavity and unioning the results matches
  exactly. Each slab is a convex box whose `_rotate_z` is vertex-baked (no `Rotation`
  field), so per-slab capture is the box case.
- **`sheet` is NOT capturable by this method.** It is `TwoSided|NotSolid` and zero-volume,
  so it never carves CSG and DEINTERSECTION yields nothing. It stays on its offline
  structural test in `test_builders.py`.
- **Enclosure must enclose the cavity** or pitch/extent gets silently clipped; sizing an
  origin-centred `CSG_Add` cube to `2·maxabs(predicted) + 512uu` is comfortably safe for
  every case tried.

## Outcome

Built as a golden-fixture suite: `uedcli/tests/builder_parity_cases.py` (registry + capture
+ `regenerate`), `test_builder_parity.py` (offline regression, default suite),
`test_builder_parity_capture.py` (`@pytest.mark.integration` live parity + re-bless),
fixture `uedcli/tests/fixtures/builder_parity.json`. Re-bless with
`python -m uedcli.tests.builder_parity_cases`.
