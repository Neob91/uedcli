+++
priority = "p2"
kind = "implement"
summary = "GUI: group inspector properties into UnrealEd-style categories"
+++

# GUI: group inspector properties into UnrealEd-style categories

Spec's "Selection & inspector" section currently says the inspector shows "the full raw T3D
property set (grouped, collapsible)" but doesn't specify a grouping — today it's a flat list.

**Want:** group properties into UnrealEd-style categories (e.g. `Display`, `Movement`, `Collision`,
`Lighting`, `Advanced`, …), matching how the real editor's property window organizes them, rather
than one flat list.

Owner-raised (2026-09-14), not yet spec'd. Needs the per-property category mapping (likely derived
from the class schema / `.u` metadata, not hand-maintained per property) — scope during Slice 2
planning alongside the rest of the inspector work.
