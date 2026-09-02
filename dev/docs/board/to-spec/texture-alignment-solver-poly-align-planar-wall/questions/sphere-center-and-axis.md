# Sphere alignment — require explicit `--center`/`--axis`, or derive the centre from the face set?

## Context

`--sphere` needs a centre point and a pole axis to measure longitude/latitude against.

- **Require `--center X,Y,Z` and `--axis x|y|z` (recommended).** Explicit, matches "never synthesize
  a reference point" (`conventions.md`) and "the tool does not infer" (`asset-catalog.md`). The
  author knows the dome's centre (e.g. the `revolve` bend centre). `--axis` defaults to `z`, reusing
  the generator `--axis` precedent.
- **Derive the centre** from the face-set vertex centroid, taking only `--axis`. Convenient, but the
  centroid of a partial dome (a ceiling half-dome) is not the true sphere centre, and a wrong centre
  warps the whole wrap — the same failure `conventions.md` cites for computed pivots.

Recommendation: **require `--center`**, `--axis` defaulting to `z`.

## Answer

<!-- Empty = open. -->
