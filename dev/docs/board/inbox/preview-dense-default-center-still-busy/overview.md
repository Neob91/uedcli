+++
priority = "p3"
kind = "implement"
summary = "preview dense-default center still busy` — with the hybrid tint+legend, a scene of ~8 overlapping brushes at `--size 460` still crowds the center: adjacent smal"
+++

# preview dense-default center still busy` — with the hybrid tint+legend, a scene of ~8 overlapping brushes at `--size 460` still crowds the center: adjacent smal

preview dense-default center still busy` — with the hybrid tint+legend, a scene of
~8 overlapping brushes at `--size 460` still crowds the center: adjacent small poly-index labels'
tints take effort to separate at that size. `--focus <brush>` is the intended remedy (spotlights one
brush, dims the rest — scored ~4.7 vs ~4.0 for the all-at-once view). A future non-focus improvement
could be a larger default label font in dense regions, or auto-`--focus` hints. Noted from the
2026-07-22 hybrid-tint cold-reader loop.
