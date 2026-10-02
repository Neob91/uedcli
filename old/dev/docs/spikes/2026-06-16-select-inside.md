# D1 — `ACTOR SELECT INSIDE` characterization (Task 0a)  ⚠️ KEY FINDINGS

Probed 2026-06-16/17 against live `dx-lum-uned`, driving the real builder-box select flow
(import builder cube → BRUSH MOVETO → ACTOR SELECT NONE/INSIDE → EDIT COPY read-back).

## What is solid
- **Point / placed actors (Lights): reliably selected** iff their pivot (Location) is inside
  the builder box. `predict_inside` models this exactly. Proven end-to-end: add→move→delete a
  Light passes as an integration test.

## Brushes: NOT reliably selectable via SELECT INSIDE
Investigated thoroughly; the mechanism is opaque and could not be made to work for a controlled
brush:
- **Bigger boxes are needed for built-level brushes**, but inconsistently. In club_entrance a
  box near a brush selected its *neighbors* but often not the intended brush; results were not
  reproducible across editor state.
- **A fresh, well-formed CSG_Add brush at a known pivot (2000,2000,0) was NOT selected at any
  box size 256–1024, before OR after `MAP REBUILD`** — even though its pivot sat in the box.
  So brush selection is neither pivot-in-box nor simple containment.
- The earlier "~2.5x span" reading was an artifact of two bugs (below) + stale editor state, not
  a real rule.

## Two real bugs found and fixed along the way
- **`actor_bounds` ignored `PrePivot`.** World position is `Location + (vertex − PrePivot)`;
  the old bounds (`Location + vertex`) mis-centered the select box by PrePivot for any brush
  with PrePivot≠0 (e.g. Brush2228 off by 496 in Y). select_by_name no longer measures brush
  geometry to place the box — it centers on the pivot (Location) — so this no longer affects
  selection. (actor_bounds is still used by preview; its PrePivot omission is a known minor gap.)
- **Parser dropped omitted `Location` axes.** UnrealEd omits zero components on export
  (`Location=(X=..,Y=..)` when Z==0); the `_LOC` regex required X,Y,Z and returned None. Fixed
  to parse axes independently (absent → 0.0); regression test added.

## What uedcli does now (per design decision)
`select_by_name` centers a builder cube at the targets' PIVOT (no geometry measuring) and tries
3 fixed sizes [256, 1024, 4096] smallest-first, caching the smallest working size PER ACTOR
(UEDCLI_BOX_CACHE) so later selects start there. It keeps the D1 fail-safe: it returns only when
every named target is in the read-back, else raises. **Consequence:** the by-name
select/delete/modify pipeline works for Lights/placed actors; a brush target typically exhausts
the ladder and raises (fail-safe — never a wrong edit). Brush *add* works (IMPORTADD); brush
delete/modify are gated.

## Open follow-up / blocker
A reliable brush-selection mechanism is unsolved. Investigating it further needs either base
Deus Ex content mounted (to reload a real built level — the crashed-editor restart lost
club_entrance, and the stub boots empty) or a synthetic multi-brush CSG room that's rebuilt.
Candidate mechanisms to try: select via built BSP/surface, `SELECT ALL` + class/name filter,
brush-by-index, or operating on brushes purely through the text model without SELECT INSIDE.
