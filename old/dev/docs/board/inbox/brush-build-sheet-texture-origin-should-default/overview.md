+++
priority = "p3"
kind = "implement"
summary = "brush build sheet anchors the texture Origin at the sheet centre, so a texture lands half-shifted; default it to a corner."
+++

# brush build sheet texture Origin should default to a corner not the centre

Source: `dev/docs/spikes/levelbuild-friction/` finding §6b (ContainerYard polish). A `brush build sheet`
places the texture `Origin` at the sheet's geometric centre, so an applied texture is offset by half
its size instead of aligning to the corner an author expects.

Change: default the sheet's texture `Origin` to a corner (the min-U/min-V vertex).

First task: confirm against the current sheet generator — this is a play-test observation, not yet
code-verified. (The size-mismatch-shows-one-quadrant sub-finding from the same section was deliberately
dropped as a design choice, not a bug.)
