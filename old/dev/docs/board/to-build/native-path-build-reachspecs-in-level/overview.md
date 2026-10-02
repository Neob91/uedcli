+++
priority = "p1"
kind = "implement"
summary = "Build the AI path graph natively in level materialize; add level paths define to auto-place PathNodes into the trunk"
spikes = ["dev/docs/spikes/2026-09-05-pathing-build-re/"]
+++

# Native path build: reachspecs in `level materialize` and a `level paths define` placer

Reproduce UnrealEd's path build inside uedcli, with no editor: `level materialize` writes the
reachspec graph the game's AI routes on, and a new `level paths define` places PathNodes into the
trunk the way the editor's `PATHS BUILD` would. Rule set selected per game in the user config.
`spec.md` is the spec; the decoded algorithms live in `PATHING-BUILD.md`.
