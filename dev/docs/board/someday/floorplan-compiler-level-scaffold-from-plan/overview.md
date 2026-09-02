+++
priority = "p?"
kind = "unknown"
summary = "Floorplan compiler: `level scaffold --from plan`"
+++

# Floorplan compiler: `level scaffold --from plan`

Compile a 2D floorplan (ASCII grid or
small JSON: rooms with heights, door/corridor edges) into the grid-aligned subtract set + door cuts +
a PlayerStart. One level of abstraction above the tracked wall-run/ring generators: those place one
shape; this roughs out a whole connected level in one call — the natural LLM interface ("draw the
map as text, extrude it"). Output is ordinary trunk actors, editable by every existing verb.
(AI brainstorm 2026-07-16.) NB the `level scaffold` name is unrelated to the rejected `project
scaffold` (project init) ruling.
