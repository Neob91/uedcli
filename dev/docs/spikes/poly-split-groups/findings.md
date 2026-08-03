# Spike: non-shadowing poly-number groups for on-face labeling

> **SUPERSEDED 2026-07-23.** This spike drove the `--split` feature, which was replaced by
> `--breakdown` (per-brush zoomed panes) the same week.
> The decal-overlap finding below is still true engine behaviour, but no shipped feature depends on
> it now. Kept as history.

**Question.** On-face poly numbers become ambiguous when the small painted number decals
overlap on screen (a number on a near face lands over the region of a far face). Can we split
a scene's face-numbers **deterministically** into groups such that, for a fixed camera, no two
numbers in a group overlap — so each group renders as its own image with every number
unambiguous?

**Answer: yes**, modeled as graph coloring:

1. Project every poly for the chosen view and place its number decal exactly as the real
   renderer would (`_plan_onface_texture`). Faces whose number is **not rendered** (omitted by
   world-size, or not selected by the `--annotate` filters) do not participate — there is
   nothing to disambiguate.
2. Build a conflict graph: two rendered numbers F,G are adjacent iff their **decal bounding
   boxes** overlap after a small pixel padding. **This is the load-bearing choice: the conflict
   is between the NUMBERS, not the faces.** Two faces can overlap hugely in projection while
   their small centered numbers never touch.
3. Color it greedily in **Welsh-Powell** order — highest-overlap-degree number first, ties
   broken by the actor's **name** (a stable identity, NOT the input-list position) + poly index —
   and, at each node, take the **least-populated group it may join** (not the lowest-index one), so
   the panes end up balanced rather than pane 0 hogging every non-colliding number.
   Deterministic regardless of the order actors arrive in — greedy coloring is order-sensitive, so
   keying the tie-break on input position would let incidental caller order change the partition;
   the name removes that. Welsh-Powell is a heuristic (near-minimal in practice, not provably
   optimal — the pane count is not canonical).

Each color class is an independent set = numbers with zero mutual overlap. `--split` renders
one image per class (faint full-scene wireframe for context + that class's faces outlined in
the brush tint with the number painted on). It is a **superset of the normal render**: when no
numbers collide it yields ONE image identical to the default; it only splits where numbers
actually overlap.

**Group counts (iso, `pad=3` px), face-overlap vs the correct decal-overlap criterion:**

| scene                          | faces | face-overlap | decal-overlap |
|--------------------------------|-------|--------------|---------------|
| subtract room                  | 6     | 2            | **1**         |
| add cube + 8-side add cylinder | 16    | 4            | **1**         |
| room + add pillar              | 12    | 5            | **2**         |

Face-overlap massively over-splits (it separates faces whose numbers were never in conflict);
decal-overlap collapses to a single image unless numbers genuinely collide. The decal-overlap
counts are stable between `pad=2` and `pad=3` (the numbers in these scenes clear each other by
well over 3 px), so `pad=3` is the pinned value.

Note the conflict test uses each decal's **axis-aligned bounding box** (`_DecalPlan.bbox()`), which
encloses the rotated/foreshortened glyph quad. That over-approximates the true ink, so the error is
one-directional and SAFE — a real overlap is never missed (no ambiguous pane), the only cost is an
occasional extra split for slanted decals whose AABBs graze. Right tradeoff for a disambiguation
tool.

**Criterion is pure screen overlap, not depth.** Any decal overlap creates ambiguity
regardless of which face is nearer, so two numbers conflict iff their (padded) boxes intersect
— independent of the depth ordering the renderer uses for opacity grading. Within a pane the
numbers keep their normal depth-graded opacity; the split only controls WHICH pane each appears
in.

**Decisions (Andrzej, 2026-07-22):**
- Conflict = **rendered number-decal overlap** (with small padding), NOT face overlap; only
  faces whose number is actually drawn (per `--annotate` filters + world-size) participate.
- Expose as a **filmstrip of one view** (`--split`; groups laid out horizontally in one image).
- Use **Welsh-Powell** ordering (fewer groups, still deterministic), with a **load-balanced** color
  pick (least-populated allowed group, not lowest-index) so panes get even sizes (`[30,9,3]` →
  `[14,14,14]`) at a near-minimal pane count (usually equal to lowest-index packing; can rarely add one
  pane) — decided 2026-07-23 after seeing lopsided real-Hexagon splits.
- Per-perspective: a split is valid only for the view it was computed in.

`polysplit_spike.py` is the harness (three test scenes; prints group membership + writes a
per-scene filmstrip to `_scratch/polysplit/`). Run: `cd Tools/uedcli && env PYTHONPATH=.
.venv/bin/python dev/docs/spikes/poly-split-groups/polysplit_spike.py`.
