+++
priority = "p3"
kind = "chore"
summary = "Two brush-identity checks are still NAME tests, next to the hierarchy rule that replaced one"
+++

# Two brush-identity checks are still NAME tests, next to the hierarchy rule that replaced one

`doctor._is_closed_solid_brush` decides world-brush-ness with
`cls == "Brush"`, and `preview_native.is_builder_brush` keys on the bare string too, so a
`MyPkg.MyBrush` subclass of `Engine.Brush` is silently outside both. Same failure shape as the
mover suffix guess that 2026-07-25 10:18 UTC removed; the fix is the same `ClassIndex` walk, but
`is_builder_brush` in particular is load-bearing for the transient red builder brush and must not
become resolver-dependent lightly. (2026-07-25, cold review of #9.4.)
