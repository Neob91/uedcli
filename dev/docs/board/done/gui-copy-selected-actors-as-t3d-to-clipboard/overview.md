+++
priority = "p?"
kind = "implement"
summary = "GUI: a Copy button next to the Inspector's selection header, copying the selected actors to the clipboard as a Begin Map/End Map T3D snippet, pasteable into real UnrealEd"
+++

# GUI: copy selected actors as T3D to clipboard

— BUILT 2026-09-28. A Copy button next to the Inspector panel's selection header (single-actor or
`{N} actors selected`) copies the current selection to the clipboard as `Begin Map`/`End Map` T3D:
`emit.emit_map_with_carriers` over `POST /api/session/{id}/t3d` (`uedcli/serve/app.py`), CSG-ordered
via `level.order`, staged `Location` reflected via `apply_staged_overlay`, folder/label carriers
included, no `bSelected`. GUI-only, no CLI verb. Salvaged a live UED22 paste-drift spike and
regression test from an earlier, unmerged attempt at this feature
(`dev/docs/spikes/2026-09-15-gui-copy-paste-ued22-parity/`) confirming the endpoint must NOT
pre-shift by `-32uu` — real `EDIT PASTE` drift is uniform across every actor kind, and reproducing
it (not masking it) is what makes the pasted result behave like any other UED22 paste.
