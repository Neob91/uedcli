+++
priority = "p?"
kind = "implement"
summary = "P2 GUI editing, slice 1: move selected actors via Ctrl/Cmd-drag, staged with explicit Save."
depends-on = ["uedcli-human-gui"]
+++

# GUI P2 slice 1 — move selected actors (staged, explicit Save)

First buildable slice of P2 (editing), scoped to Location-only moves. Builds on the P1 read-only
GUI (`uedcli-human-gui`) and its already-ruled P2 persistence model (staged + explicit Save,
warn-and-confirm on a Save/Load conflict — see that item's `spec.md` "Deferred" section and
`dev/docs/rationale/gui-editing.md`). See `spec.md` for the full design.

Decided with the owner (2026-09-20):

- The interaction reuses the SAME three mouse-button combos as the existing perspective camera-nav
  (LMB-drag / RMB-drag / LMB+RMB-drag), gated by holding Ctrl or Cmd, one axis per combo — not a
  modern on-screen gizmo (real UnrealEd 1.x had none).
- Ortho panes use a single combo, plain Ctrl/Cmd+LMB-drag, moving along both of that pane's visible
  axes at once (no per-axis combo needed there — only 2 axes are ever visible per ortho pane).
- The drag can start anywhere in a viewport (not only on the actor itself) and moves the WHOLE
  current selection together.
- The modifier check is `e.ctrlKey || e.metaKey` (matches the existing multi-select convention,
  `web/src/scene/dragGesture.ts`) — never an OS-specific Ctrl→Cmd swap.
- Save/Load conflict merge is **per-property, with mandatory explicit resolution on a real
  same-property conflict** — never a blanket confirm-and-overwrite. A trunk-side change to a
  DIFFERENT property than the staged edit merges in automatically, no prompt; a trunk-side change to
  the SAME property (here, `Location`) blocks that actor's Save until the user explicitly picks
  staged-or-trunk. See `spec.md` "Persistence".

Rotate/scale, property/inspector edits, actor create/delete, and the atomic-chained-verb
transaction idea (`dev/docs/board/to-plan/uedcli-human-gui/questions/
atomic-chained-verb-transaction.md`) are out of scope for this slice.
