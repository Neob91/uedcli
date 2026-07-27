+++
priority = "p3"
kind = "unknown"
summary = "`brush build revolve` should NOT merge its faces — leave them separate so textures can be aligned per face"
+++

# `brush build revolve` should NOT merge its faces — leave them separate so textures can be aligned per face

(Owner request, 2026-07-26.) What merges today, and it is not one thing:
  - **The CAPS are fused, deliberately.** A non-convex or >16-vertex profile is ear-clipped and then
    merged back across shared diagonals for as long as each piece stays convex and fits the 16-vertex
    `FPoly` bound (Hertel–Mehlhorn, `profile.convex_pieces`). So a cap that is conceptually many
    facets arrives as a few large ones, and there is no face to align a texture onto separately. The
    fusion exists on purpose — its own docstring: *"merging matters, because every extra face is BSP
    nodes and rendering cost"* — so removing it is a **trade** (more faces, more nodes, more render
    cost) and not a pure win. That is why this is `[spec]` and not `[chore]`.
  - **The SIDES are already unmerged model-side** — `builders.revolve` emits `n × s` separate quads,
    one per (profile edge, segment). But every segment of profile edge `k` carries the SAME
    `ItemName=Side<k>`, so `--item Side0` selects the whole swept strip and there is no item-level
    handle on a single facet. Individual facets ARE addressable as `BRUSH:idx` selectors from
    `brush poly find`, so this may be a selector-ergonomics gap rather than a geometry one.
  - **The ENGINE merges coplanar surfaces at `MAP REBUILD`** (`bspMergeCoplanars`, within
    `THRESH_NORMALS_ARE_SAME = 2e-5` — `unrealed/quirks.md` "More build thresholds"). Anything the
    generator keeps separate can still be fused in the built map, so a model-side-only fix may not
    reach the surfaces the level designer actually aligns against.

  **Do not guess which of the three was meant — settle it at triage.** Then the real design questions
  are: is unmerged the DEFAULT or a flag (`--no-merge-caps`, or a general "one face per facet" mode);
  does it apply to `extrude` and the other cap-tiling builders too (same `convex_pieces` seam, so
  they would diverge otherwise); and what happens to the node-count budget on a full-turn revolve,
  where `inbox.md`'s own poly-budget note already flags a 16-segment revolve of an 8-point profile as
  128 swept faces plus caps.

  **MEASURED 2026-07-26 — the goal is a curved TRAIN TRACK whose textures run properly around the
  bend, and on that evidence the merge framing above is mostly a red herring.** Ran
  `brush build revolve --point 64,0 --point 96,0 --point 96,32 --point 64,32 --angle 16384
  --segments 4` and read the emitted T3D:
  - **`Link=` is NOT the mechanism and is not ours.** uedcli emits **zero** `Link=` lines (0 across
    18 polys), `model.Polygon` has no `link` field so ingest drops it, and `normalize.py` says
    outright *"The emitter drops Link."* `unrealed/t3d.md`'s polygon reference: *"computed BSP surface
    link; never authored, **ignored on import**."* A real editor export of a 6-poly cube in `_scratch`
    carries `Link=0,1,2,3,4,5` — one per poly, all distinct. So a `Link=N` seen on a revolve came back
    from the editor and is a per-poly index, not evidence of merging; editing it separates nothing.
  - **The CURVING faces are already separate AND correctly parameterised.** `Side1` (outer) has **4
    distinct normals** — four distinct planes, so `bspMergeCoplanars` cannot touch them — and each
    facet carries its own plane-derived axes: `TextureU=(0,1,0)` along the revolve axis, `TextureV`
    rotating with the facet (`-0.195,0,0.981` → `-0.556,0,0.831` → `-0.831,0,0.556` →
    `-0.981,0,0.195`), unit length (scale 1 texel/uu). These are individually alignable today.
  - **The FLAT faces are one surface by geometry, not by choice.** `Side0` has exactly **one**
    distinct normal across all 4 facets — a flat annular fan. The engine fuses those at `MAP REBUILD`
    however the T3D is written, because a flat annulus is flat. Nothing model-side reaches it.
  - **THE ACTUAL DEFECT: `Pan lines: 0`.** No facet carries any pan offset, so every facet's texture
    starts at the same phase and the pattern **restarts at each segment boundary** — a seam every
    22.5° at `--segments 4`. For track, sleepers jump and bunch at every facet edge. This is
    independent of merging entirely, and it is what makes a curved sweep unusable for a repeating
    run.

  **So the feature actually wanted is an arc-length-continuous parameterisation along the sweep** —
  each successive facet's `Pan` (or `Origin`) advanced by the arc length consumed so far, so the
  pattern flows around the bend as one run. Model-side, no editor, consistent with generators already
  owning texture vectors. **The one design question that changes the implementation, ASKED AND NOT
  ANSWERED (owner deferred it 2026-07-26 — do not guess):** arc length is radius-dependent (the inner
  strip sweeps `64·Δθ` per segment, the outer `96·Δθ`), so what drives the run?
  (a) **per-strip arc length** — texels stay square on every face, but inner and outer rails drift out
  of phase around a long bend; (b) **one reference radius for the whole brush** (centreline, or a
  `--texture-radius` flag) — sleepers stay in lockstep across the track width, which is what real
  track looks like, at the cost of slight stretch outer / squeeze inner; (c) **per-facet fit** —
  predictable, seam-aligned, but the pattern restarts each segment, so wrong for track.
  Secondary, cheap, and independent: **all cap faces share ONE `Item=Cap` label** (measured: a
  concave 6-point profile yields 28 polys = 24 sides + 4 cap tiles, all labelled `Cap`), so the two
  ends cannot even be selected apart, while sides get per-edge `Side0..SideN`. Per-cap labels would
  cost nothing.

<!-- Surfaced by the blind-build idiom test (5 cold agents built real-DX shapes using only the CLI +
     user docs, no source, 2026-07-25). All 5 shapes built correctly; these are the CLI papercuts they hit. -->
