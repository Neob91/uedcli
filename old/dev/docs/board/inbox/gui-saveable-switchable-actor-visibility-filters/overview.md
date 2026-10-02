+++
priority = "p2"
kind = "implement"
summary = "GUI: saveable/switchable actor visibility filters"
+++

# GUI: saveable/switchable actor visibility filters

The `uedcli-human-gui` spec's organization panel (label filter facets, folder tree, find box) lets
you toggle visibility filters, but only by setting them manually each time -- the same qualm as
UnrealEd's Groups window: switching between two working sets of actors means re-toggling every
chip/facet by hand.

**Want:** named, saveable filter presets -- combinations of folder/label/find-box state a user can
save once and switch between with one click, instead of re-deriving them each session.

Owner-raised (2026-09-14), not yet spec'd. Scope this against the org panel in
`dev/docs/board/to-plan/uedcli-human-gui/spec.md` ("Structure & navigation") when that item is
picked up for planning -- likely a Slice 2 addition alongside the org panel itself, not a new slice.
