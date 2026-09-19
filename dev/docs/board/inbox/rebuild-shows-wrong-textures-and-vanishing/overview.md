+++
priority = "p3"
kind = "debug"
summary = "during a geometry rebuild, wrong textures briefly show on surfaces and some brushes temporarily vanish"
+++

# Wrong textures and vanishing brushes during rebuild (transient)

Owner report (2026-09-19): "when rebuilding, I can see wrong textures applied surfaces, and some
brushes temporarily vanish."

Owner explicitly asked for lowest priority and no work on it now -- filed for the record only.

## What's known

Nothing investigated yet. Transient, during the geometry-rebuild flow specifically (not a steady-
state bug) -- symptoms clear once the rebuild finishes, per the report's phrasing ("temporarily").
Two distinct visual glitches reported together, possibly related, possibly not:

1. Wrong textures applied to surfaces during the rebuild.
2. Some brushes disappear entirely for a moment during the rebuild.

## Where to look, when picked up

Whatever mid-rebuild rendering state exists between the old payload and the new one landing --
likely `uedcli/serve/app.py`'s rebuild/publish flow and however the frontend transitions scene state
across a rebuild (`web/src/scene/`'s payload-swap logic). The recent mesh/mover build-independence
work (`mesh-actors-should-render-independent-of`, `mover-triangles-not-build-state-independent`)
changed how actors resolve textures across the pre-/post-build boundary and may be relevant, but this
is a guess, not established -- confirm before assuming.
