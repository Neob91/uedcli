+++
priority = "p3"
kind = "investigate"
summary = "RETRACTED claim -- do not act on it. Real question (does UED22 hide the pivot cross for a single selection?) is still open, needs real RE"
+++

# Pivot cross visibility vs selection count -- claim retracted, question still open

Originally filed investigating `brush-pivot-cross-multiselect-and-toggle` (2026-09-18), citing
`GUI-PARITY.md`'s "Pivot-cross visibility toggle" finding.

**Owner ruling, 2026-09-18: that finding is RETRACTED.** It was built entirely on a third-party UE1
engine source (`fgsfdsfgs/UE1`), which this project must never cite or use for GUI-PARITY RE --
only the actual UED22 binary (`uned/UED22/`) counts as evidence, via disassembly or a live capture.
The claim ("UED22 hides the pivot cross for a single selected actor, shows it only on multi-select/
an active snap-drag") was never confirmed against our own `Editor.dll`/`render.dll` and must not be
treated as fact or acted on.

Our GUI's own current behavior is unchanged and, as far as this item establishes, not confirmed to be
wrong: `PivotMarker` renders unconditionally for every selected brush, including exactly one.

If this is picked up again: RE the real question from scratch against `uned/UED22`'s own binaries
(disassembly or a live capture, per `GUI-PARITY.md`'s Method section) -- do not reuse or cite the
retracted third-party-sourced claim as a starting point or a hint.
