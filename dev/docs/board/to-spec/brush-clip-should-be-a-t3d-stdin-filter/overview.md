+++
priority = "p2"
kind = "implement"
summary = "`brush clip` should be a T3D-stdin FILTER (`-`), not only a by-name trunk edit"
+++

# `brush clip` should be a T3D-stdin FILTER (`-`), not only a by-name trunk edit

Today `brush clip <name> --plane …` mutates a placed trunk actor in place — but every other geometric
brush *transform* is a stateless T3D-in/T3D-out generator (`brush build`, `brush intersect`/
`deintersect`, and the proposed `brush snap`). Clip is the odd one out. Make it read a brush T3D on
**stdin** and emit the clipped brush on **stdout**, so it composes BEFORE the trunk:
`brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -` (a chamfered box in
ONE pipeline, vs today's add-then-clip-by-name). Spec: keep the by-name in-place form too, or replace
it with the filter + `brush replace` (`actor show X | brush clip - … | brush replace X -`)?; single
brush vs a SET on stdin. Aligns clip with the generator family; would simplify the shape recipes
(`docs/leveldesign/general/recipes/shapes/`), which currently show the two-step by-name form.
(Andrzej, 2026-07-25.)
