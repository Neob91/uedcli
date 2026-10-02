+++
priority = "p3"
kind = "docs"
summary = "`--native` is flat-shaded gray with no lights/meshes/lighting; movers need close-ups"
+++

# `--native` is flat-shaded gray with no lights/meshes/lighting; movers need close-ups

By design (documented), but the consequence for authoring: lighting mood, every decoration/fixture,
and mover open/close STATE are all authored BLIND offline — a closed-door mover is nearly
indistinguishable from the wall at distance. Native is a geometry/proportion tool only; verifying
lighting + decoration needs the `--game` tier. Worth stating plainly in the "how to build" guide so
an agent shoots movers/lights close-up and defers lighting judgment to `--game`. (A + B.)
