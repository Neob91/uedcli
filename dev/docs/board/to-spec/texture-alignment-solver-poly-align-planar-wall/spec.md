# Spec — texture-alignment solver (`brush poly align`): planar + curved

Status: DRAFT for owner review. This item predates most of what it asked for; the spec re-scopes to
what is genuinely unbuilt (sphere/dome) and records the rest as done. Blocking forks in `questions/`.

## Goal

Make a texture flow continuously across a set of adjacent faces — no seam at every brush/facet
boundary — as pure offline texture-vector math. The item names: planar wall/floor, curved
cylinder/sphere, plus `texture scale`/`texture rotate`.

## Current state (most of the item is already built)

- **Planar `--wall` / `--floor`**: `polyalign._coplanar_align` (`uedcli/polyalign.py:230`) — one
  shared world-space frame across a strictly coplanar, co-oriented set; continuity offset lives in
  each face's `Origin`, inverse-transformed through that brush's own rotation
  (`_write_world_frame`, `polyalign.py:120`). `--fresh-frame` synthesises a unit frame from the
  normal (`builders._tex_basis`); default adopts the seed. **DONE.**
- **Curved cylinder `--ring`**: `polyalign._ring_align` (`polyalign.py:287`) — U advances by each
  facet's chord around the ring, V along the axis; `--fit-perimeter` snaps density for an exact
  closing seam (`polyalign.py:377`). **DONE.**
- **`texture rotate` / `texture scale`**: shipped as `brush poly rotate` / `brush poly scale`
  (`uedcli/surface.py:424,484`, owner ruling 2026-07-27), plus `brush poly pan`. In-plane turn/resize
  re-anchored on the face centroid, with the out-of-plane and writability guards. **DONE** — the
  "2 of 4 canonical ops flagged missing by the 2026-07-19 probe" have since landed.
- **`brush poly find`** producer (`polyalign.py:186`): `--item`/`--facing`/`--texture` filters
  feeding `poly align -`. CLI: `uedcli/cli/parsers/brush.py:494-537`. **DONE.**
- **UnrealEd `POLY TEXALIGN` parity** is deliberately NOT matched — `--wall`/`--floor` anchor on the
  seed centroid where the editor's modes anchor on a world axis, and match none of its nine modes
  (`dev/docs/unrealed/texalign.md`). Whether to change that is a **separate** owner decision already
  parked (`board/inbox/` `poly-surface-verbs`), and is out of scope here.

So the only unbuilt piece the item names is **sphere/dome** alignment, plus two deferrals recorded
below.

## Design — sphere/dome `--sphere` (the new work)

A dome/sphere is not produced by any current builder (the family is cube/cylinder/cone/sheet/
staircase/spiral/extrude/revolve) — such geometry arrives as a `revolve` of a semicircle or a
hand-built geodesic. So `--sphere` takes an arbitrary faceted face set and assigns each face a frame
from spherical coordinates about a centre and pole axis. Like `--ring`, continuity is exact per facet
edge only where facets share the tessellation; across a general geodesic it is a best-fit per-face
tangent frame.

### Method (fork — `questions/sphere-projection-method.md`)

- **A. Equirectangular (lat-long), recommended.** For each face: direction `r̂` = centroid − centre;
  local *east* `ê = axis × r̂` (normalised), local *north* `n̂ = r̂ × ê`. Set `TextureU` along `ê`
  scaled to arc-length-per-texel (U ∝ azimuth·radius), `TextureV` along `−n̂` (down the face, V=0 at
  top, matching UE1), `Origin` so the centroid maps to its `(azimuth, polar)` texel. Handles a
  geodesic and a revolve dome uniformly; poles are the one degenerate case (below).
- **B. Stacked rings.** Reuse `--ring` per latitude band, V advancing by band. Exact seams, but only
  valid for a lat-long-tessellated dome (revolve output), not a geodesic — and needs the caller to
  group faces per band. Narrower, more editor work.

Recommendation: **A** — one rule for any tessellation, symmetric with how `--ring` already works.

### Centre and axis (fork — `questions/sphere-center-and-axis.md`)

`--sphere` needs a centre and a pole axis. Options: **require `--center X,Y,Z` and `--axis x|y|z`**
(explicit, matches "never synthesize a reference point" / "the tool does not infer"; the author knows
the dome's centre, e.g. the revolve bend centre); or **derive the centre** from the face-set vertex
centroid and take only `--axis`. Recommendation: **require `--center`** (with `--axis` defaulting to
`z`, reusing the generator `--axis` precedent, `generators.md`), because a derived centre of a partial
dome is off the true centre and warps the wrap — the same class of error `conventions.md` warns about
for synthesized pivots.

### CLI surface

```
brush poly align --sphere --center X,Y,Z [--axis x|y|z] [--fresh-frame] TARGETS|-
```
- `--sphere` joins the existing `--wall`/`--floor`/`--ring` mutually-exclusive mode group
  (`brush.py:517`). help=: "wrap a texture over a dome/sphere: U follows longitude around --axis, V
  follows latitude; needs --center (and --axis, default z)."
- `--center X,Y,Z` (help=: "the sphere/dome centre in world units — U/V are measured as
  longitude/latitude about it; required for --sphere, rejected for other modes"). Parsed by
  `cli.parse_coord`.
- `--axis x|y|z` (help=: "the pole axis longitude wraps around (default z)").
- `--fresh-frame`: unit density (1 texel/uu of arc); default adopts the seed face's texel scale, as
  `--ring` does.
- `--fit-perimeter` stays ring-only (rejected with `--sphere`, or extended to snap the equatorial
  wrap — recommend keeping it ring-only in v1).

## Deferred (documented, not built here)

- **Slanted / non-axis-aligned walls.** `_check_orientation` (`polyalign.py:215`) rejects a face
  that is neither vertical nor horizontal ("turning runs deferred"). Extending `--wall` to a slanted
  coplanar run is a small generalisation but a behaviour change to a shipped verb — left as a
  follow-up item unless the owner pulls it in (`questions/` does not raise it; flag if wanted).
- **`--to` absolute texel density** (world-units-per-tile) for `brush poly scale` and align — needs
  the texture catalog for a texture's pixel size, which is why the parser reserves it
  (`brush.py:479`). Out of scope until the catalog lands.

## Edge cases & errors

- `--center` given with a non-sphere mode, or omitted with `--sphere` → exit 2 naming the flag
  (mode/flag consistency, enforced in the CLI like `--fit-perimeter`'s ring-only guard,
  `polyalign.align` `polyalign.py:400`).
- A face whose centroid coincides with `--center` (zero `r̂`), or a face straddling a pole (`r̂ ∥
  axis`, so `ê` degenerates) → `PolyAlignError` naming the face (a pole has no defined longitude
  frame), mirroring the existing degenerate-face raises (`polyalign.py:116`).
- Empty stdin / empty target set → clean no-op exit 0 (existing `align` contract, `polyalign.py:403`).
- All existing `--wall`/`--floor`/`--ring` behaviour and errors unchanged.

## Tests

- `test_polyalign.py`: two facets of a dome share a texel coordinate at their shared edge under
  `--sphere` (the seam-continuity assertion pattern of `face_uv`, `polyalign.py:412`).
- `--fresh-frame` gives unit arc density; adopt keeps the seed scale.
- Pole face and centre-coincident face each raise, naming the face.
- `--center` omitted / wrong-mode combinations exit 2.
- Regression: `--wall`/`--floor`/`--ring` goldens unchanged (this is additive).

## Open questions

- `questions/sphere-projection-method.md` — equirectangular per-face frame (A) vs stacked-rings (B),
  and confirm sphere/dome is wanted at all given no builder emits it yet.
- `questions/sphere-center-and-axis.md` — require explicit `--center`/`--axis`, or derive the centre
  from the face set.
