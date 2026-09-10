# `brush relation` basics

Mechanics shared by every skill in the `uedcli` plugin. Not a skill itself — linked from
skills that need it.

## The two-stage split

- **`brush relation find --relative-to REF[:idx] [candidates...] [--max-gap N] [--min-gap N]
  [--footprint LIST] [--plane {coplanar,parallel}] [--top N|all] [--json]`** — searches for
  candidate faces related to REF. Reports IDENTITY ONLY: stdout is `candidate:poly` lines
  (pipeable), stderr is one aggregate count, `--json` gives `{ref, ref_poly, candidate, poly}`.
  No geometry — filters by gap/footprint/plane but never shows the numbers.
- **`brush relation measure REF TARGET...`** (or `REF -` to read TARGET selectors from stdin,
  e.g. piped straight from `find`) — the only source of geometric detail: for each ref-vs-target
  pair, plane relationship (`coplanar`/`parallel`), both faces' outward normals, signed
  perpendicular distance, 2-D footprint classification, and centroid/edge deltas.
- `find | measure REF -` is the intended pipeline: narrow with `find`, then get full detail on
  exactly that set with `measure`.

## Key details

- `REF[:idx]`: a bare brush Name ranks/compares against every one of its polys; `Name:idx` pins
  one exact face. Distance/delta signs are relative to REF's own normal.
- `--top N` (default 1) caps ranked pairs per candidate/target; `--top all` shows every
  qualifying pair — use `all` when you need to see everything, not just the closest match.
- `--allow-self` permits REF and a candidate/target to name the same brush (comparing two faces
  of one brush); without it, that's a clean exit 2.
- `footprint_2d` values: `none` (no overlap), `vertex` (touch at a point), `edge` (touch along a
  line, zero area), `partial` (real overlap, neither contains the other), `contains_a_in_b` /
  `contains_b_in_a` (one fully inside the other), `coincident` (identical footprint both ways —
  usually a stray duplicate).
- Deltas (`centroid_u/v`, `edge_u/v`) are measured in the shared plane's own U/V axes, not world
  X/Y/Z — U/V come from the reference face's own orientation.
- `plane` is `coplanar` (same plane, touching) or `parallel` (same orientation, offset) — `find`'s
  `--plane` filter and `measure`'s report both use these two values only.
