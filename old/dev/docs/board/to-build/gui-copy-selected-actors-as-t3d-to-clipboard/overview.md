+++
priority = "p?"
kind = "implement"
summary = "GUI: a Copy button next to the Inspector's selection header, copying the selected actors to the clipboard as a Begin Map/End Map T3D snippet, pasteable into real UnrealEd"
+++

# GUI: copy selected actors as T3D to clipboard

Add a Copy button (icon + label) next to the Inspector panel's selection header — the single-actor
name or the `{N} actors selected` line — that copies the current actor selection to the system
clipboard as a T3D snippet: `Begin Map`/`End Map`-wrapped, actors in CSG order, reflecting any
staged (unsaved) `Location`, with uedcli's folder/label carrier comments included, faithfully
pasteable into a real running UnrealEd 2.2 via `EDIT PASTE`. GUI-only — no CLI verb. See `spec.md`.
