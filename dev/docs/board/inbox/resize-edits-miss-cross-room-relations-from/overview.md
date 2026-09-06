+++
priority = "p?"
kind = "docs"
summary = "brush relation find defaults/workflow let an agent verify only the moved face, missing a stretched neighbor face"
+++

# resize edits miss cross-room relations from unmoved faces

## What happened

Widening a room via `brush vertex move` (move the 4 corners on one face of a box-shaped
`CSG_Subtract` room brush) also stretches every OTHER face that shares those corner vertices —
ceiling, floor, and the adjacent walls all grow with it, not just the face being edited.

An agent doing this kind of edit (dx_lum, `feat/unatco-manderley-office-bigger`) ran
`brush relation find --relative-to <room-brush>:<face-idx>`, pinned to the ONE face it moved, to
confirm nearby wall-mounted decor (plaques) landed flush. That check passed. It missed that the
SAME edit had also stretched the room's north wall face — a face the agent never touched directly —
so that face's footprint now newly covered the position of an unrelated decoration (a painting)
belonging to the neighboring room, sitting on the shared wall. That face carries no texture (normal
for a coincident-plane seam the real editor's CSG/BSP solve would hide), so the offline `level photo
--native` draft renderer showed the neighboring room's painting with no backdrop behind it —
"floating."

The agent had actually found the painting's actor once already, in a plain neighbor-bbox sweep
*before* making the edit, and dismissed it as "outside the room, not my concern" because it checked
against the room's boundary as it stood *before* the move, not where the move would put it.

Only re-running `brush relation find --relative-to <room-brush>` **with no face pin** (ranks against
every one of the brush's polys) surfaced the real relation: the north face, untouched by the edit
directly, coplanar and now fully containing the painting's footprint.

## Why an agent would miss this

- `brush relation find --relative-to REF:idx` (pin to one face) is the natural first reach when you
  know which face you moved — but a vertex move on a shared-corner box brush silently affects
  sibling faces too, and there's nothing in the CLI's own output that says "these other faces also
  changed."
- A neighbor sweep (`actor find --overlapping-bbox`) taken relative to the CURRENT footprint, run
  before an edit that's about to grow that footprint, structurally cannot see the thing the edit is
  about to reach into being a problem.

## Possible fixes (needs a spec — filing this un-triaged)

- **Docs**: add a "resizing a room" checklist somewhere findable (`docs/reference/brush.md`? a new
  `dev/docs/unrealed/quirks.md` entry?) — after any `brush vertex move`/`brush scale` that changes a
  room-brush's box extent, run `brush relation find --relative-to <room-brush>` bare (no face pin,
  the whole brush) both before AND after, and diff the two — new coplanar/`contains` pairs that
  weren't there before are the things worth a look.
- **Tooling**: could `level doctor` gain a check along the lines of "a `CSG_Add` brush's footprint
  is fully contained in a `CSG_Subtract` room's face that carries no texture" — this is close to the
  existing `csg_order` family of checks and might generalize past this one incident.
- **CLI UX**: `brush vertex move` could print which OTHER faces of the same brush also changed as
  part of the move (their old/new footprint), so the fact that siblings moved isn't silent.

No spec written yet — needs triage on which of these (if any) is worth building versus just being a
sharper docs note.
