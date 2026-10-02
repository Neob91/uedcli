+++
priority = "p3"
kind = "chore"
summary = "spiral column/tread seam is polygonal-vs-chord` — the central column is a `SPIRAL_COLUMN_SIDES`-gon (16) prism, so its facets don't align to each wedge tread's "
+++

# spiral column/tread seam is polygonal-vs-chord` — the central column is a `SPIRAL_COLUMN_SIDES`-gon (16) prism, so its facets don't align to each wedge tread's 

spiral column/tread seam is polygonal-vs-chord` — the central column is a
`SPIRAL_COLUMN_SIDES`-gon (16) prism, so its facets don't align to each wedge tread's STRAIGHT inner
chord over `degrees_per_step` (a straight chord vs a run of column facets). Tiny cosmetic seam
gaps/overlaps are possible where a tread meets the column. Harmless under additive CSG (the union
still fills solid); would matter only if someone wants a pixel-tight seam. Deferred from the spiral
redo fix batch.
