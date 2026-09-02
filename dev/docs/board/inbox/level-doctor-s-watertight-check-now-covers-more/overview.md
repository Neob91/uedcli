+++
priority = "p3"
kind = "chore"
summary = "`level doctor`'s watertight check now covers MORE mover subclasses — including the known glass false positive"
+++

# `level doctor`'s watertight check now covers MORE mover subclasses — including the known glass false positive

`docs/leveldesign/general/recipes/glass.md` already documents that
`check_watertight` false-flags welded mover glass; with mover-ness now schema-aware,
`DeusEx.BreakableGlass`/`BreakableWall` brushes are newly IN scope for that check (the name-suffix
gate skipped them). Either narrow the check for movers or downgrade the finding — the existing
glass-recipe note now applies to strictly more actors. (2026-07-25, cold review of #9.4.)
