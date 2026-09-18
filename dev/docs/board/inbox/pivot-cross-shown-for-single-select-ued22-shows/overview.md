+++
priority = "p3"
kind = "investigate"
summary = "UED22's real pivot cross hides for a single selected actor; ours always shows it"
+++

# Pivot cross shown for single-select; UED22 shows it only on multi-select/drag

Found investigating `brush-pivot-cross-multiselect-and-toggle` (2026-09-18), out of that item's
scope -- filed separately rather than folded in.

`GUI-PARITY.md`'s "Pivot-cross visibility toggle" finding (📖 `fgsfdsfgs/UE1`,
`Source/Editor/Src/UnEdCam.cpp`) established that real UED22's own pivot-cross mechanism is NOT
"draw one per selected brush, always" (what `SelectionMarkers.tsx`'s `PivotMarker` does today) --
it's a single GLOBAL crosshair, gated by `GPivotShown`, which `SetPivot()` sets to
`SnapCount>0 || Count>1`. Concretely: selecting exactly ONE actor (`NoteSelectionChange`'s
`Count==1` branch) leaves `GPivotShown` false -- the real editor's pivot cross is invisible for a
lone selection, and only appears once 2+ actors are selected, or during an active grid-snap drag.

Our GUI does the opposite: `PivotMarker` renders unconditionally for every selected brush, including
exactly one. This is a real, sourced (not yet live-verified against the actual DeusEx `Editor.dll`)
fidelity gap -- not something to silently fix, since it would change a long-standing, deliberately
reviewed and shipped behavior (multiple past commits treat "show the pivot on any selected brush" as
the wanted feature). Needs an explicit owner call: reproduce UED22's hide-for-single-select rule, or
keep the current always-visible convenience on purpose (the "campaign toggle-button conventions" this
item cited -- Grid/Radii/Movers -- already include some GUI-only conveniences with no strict UED22
one-to-one, so "always visible" may be an intentional divergence, not an oversight).

No live/binary confirmation yet (📖 source-only, same caveat as every other `fgsfdsfgs/UE1`-sourced
finding in `GUI-PARITY.md`) -- worth a live UED22 capture before acting, per that doc's own method.
