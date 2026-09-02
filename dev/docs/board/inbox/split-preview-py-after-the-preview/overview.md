+++
priority = "p3"
kind = "implement"
summary = "Split `preview.py` into cohesive units — deferred out of the god-module split, and NOT covered by the consolidation item."
depends-on = ["consolidate-level-preview-native-onto-the-actor"]
+++

# Split `preview.py` after the preview consolidation lands

`preview.py` was the worst offender in the god-module survey — 2714 lines then, 2290 after `6d8f770`
removed the legend and name machinery. `refactor-god-modules-into-cohesive-units` excludes it and
splits the other three, because `consolidate-level-preview-native-onto-the-actor` is rewriting the
file right now.

**That consolidation does not split it.** Its step 1 extracts one `Projection` seam; step 2 ADDs a
perspective camera, a Sutherland-Hodgman near clipper and a second fill inner-loop. The file gets
bigger, not decomposed. So without this item the survey's worst offender is untracked.

Scope, once the consolidation lands: the seams the survey named — annotation-spec parsing, selector
categorisation, brush classification, projection/iso math, buffer allocation, and the software
rasterizer (line/circle/diamond/blit, face fill, textured fill, mip selection, UV/affine, occlusion,
shading) — plus whatever the consolidation adds. At least three units: geometry/projection, the
rasterizer, and the preview orchestration.

Blocked until then: re-splitting a file mid-rewrite would collide, and the consolidation's gate is
byte-identical `actor diagram` goldens, which a concurrent split would muddy.

Use the same method the god-module split used — build the intra-module reference graph with `ast`,
assign every top-level symbol, and assert no edge points up the chosen layer order before moving any
code.
