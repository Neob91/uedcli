+++
priority = "p2"
kind = "owner-question"
summary = "GUI texture/actor click-select modifier rules (Shift/Ctrl) are owner-spec + convention, not RE-confirmed against live UED22"
+++

# GUI texture/actor click-select modifier rules unverified against live UED22

The selection-model overhaul (plain LMB selects a surface's texture, Shift+LMB selects the whole
brush, Ctrl multi-selects each kind — `dev/docs/GUI.md` "Selection & the Inspector") was implemented
from the owner's own spec, which was itself asked to be confirmed against a live UED22 before
locking in. No live confirmation happened this session. Recording why, and what it would take.

## Why not attempted

- **No existing harness for this.** The project's console-verb RE method
  (`unrealed/extracting-from-dll.md`) mines wide-string literals + live `wine_ctl exec` driving —
  built for typed exec commands, not mouse clicks with held modifier keys in a rendered viewport.
  No prior spike in `dev/docs/spikes/` builds an xdotool-modifier-click harness (checked).
- **No query path for the fact that matters most.** `unrealed/quirks.md` "Selection" already
  states `PF_Selected` does not round-trip — "you can't ask the editor which poly is this surface."
  So even a live click could only be verified at the ACTOR level (via `EDIT COPY`'s `bSelected`),
  never at the polygon level — the actual claim needing verification (does a plain click select a
  surface not visible any other way) has no read-back mechanism today.
- **Resource risk.** The sandbox's root filesystem had 2.7 GB free (32 GB total, 91% used) when
  checked this session; `NATIVE-MATERIALIZE.md` logs real disk-exhaustion incidents on this project
  from concurrent editor use. A fresh UED22 container boot + exploratory click-testing was judged too
  risky to attempt opportunistically alongside other running work.

## What was used instead

The owner's spec text matches the well-known general UnrealEd 1.x convention (a bare click on a
brush face selects its texture/current-surface, used by the Surface Properties dialog; a separate
gesture selects the whole brush actor) — implemented faithfully as given, not re-derived or altered.

## What would settle it

1. Extend `driver.py`'s `click()` (already does a real XTEST click, unused by any current verb) with
   modifier-key support (xdotool `keydown`/`keyup` bracketing the click).
2. Place 2+ overlapping/adjacent brushes, click a shared face with/without Shift/Ctrl in solid and
   wireframe view.
3. Read back ACTOR-level results via `EDIT COPY`'s `bSelected` (confirms whether Shift toggled the
   whole-brush selection). Polygon-level results have no read-back path — would need a screenshot
   diff against the surface-highlight render, a genuinely new investigation.

## Partially settled by owner decree (2026-09-17), not RE

`shift-modifier-convention-broken-for-poly-and` fixed two real bugs in the poly-vs-line
half of this question, per a direct owner ruling ("Shift is only to select BRUSHES ... by clicking on
its VISIBLE POLY") rather than a live UED22 capture — so this settles the POLY-vs-LINE modifier
question by decree, not evidence, and the "not RE-verified" caveat above still stands for everything
else here (Ctrl multi-select semantics, the AABB-fallback Shift gate, and the poly-vs-actor fork
itself). Still open.

## Partially settled by disassembly (2026-09-20), not live

A DIFFERENT investigation (actor+surface selection coexistence, `GUI-PARITY.md`'s "Actor + surface
selection coexist; only a plain click clears both") disassembled `Editor.dll`'s click handlers as a
side effect and found the real Ctrl-vs-plain modifier mechanism: `UEditorEngine::SelectNone` (RVA
`0x45ee0`) is called on a plain-LMB click and skipped on a Ctrl-LMB click, in both the actor and
surface handlers — confirming Ctrl genuinely means "don't clear the other selection kind," not just
"add to this one." Confidence 📖 disassembly-only (the live-capture blocker above still applies —
this session's sandbox also couldn't boot a UED22 container). This answers part of "Ctrl multi-select
semantics" above; the AABB-fallback Shift gate and the poly-vs-actor fork itself remain open.
