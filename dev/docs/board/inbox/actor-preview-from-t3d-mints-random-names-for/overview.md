+++
priority = "p3"
kind = "debug"
summary = "actor diagram --from-t3d gives unnamed brushes a fresh random Name per render, so --json is not reproducible."
spikes = ["dev/docs/spikes/2026-08-30-a1-grid-blind-usability/"]
+++

# `actor diagram --from-t3d` mints random Names for unnamed brushes

Rendering the same T3D twice produces different Names for the brushes that carry none: each render
mints a fresh `Brush_<random>`. On `hexagon_good.t3d` (307 actors) 299 Names are stable across runs
and 8 differ — `Brush_ei4244` in one run, `Brush_2t943a` in the next.

Consequences: `--json` output is not reproducible, two renders of one file cannot be diffed by name,
and a name carried out of one render's legend may not resolve in another.

Found while building `dev/docs/spikes/2026-08-30-a1-grid-blind-usability/` (which is unaffected — both
arms used a single render). Not investigated further: whether the Name is minted at T3D parse or at
render, and whether the same happens on the level path rather than `--from-t3d`.
