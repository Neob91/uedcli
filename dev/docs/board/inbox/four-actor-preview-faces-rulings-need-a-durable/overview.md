+++
priority = "p1"
kind = "owner-question"
summary = "`actor preview --faces` rulings need a durable `direction/` home before their spec is deleted"
+++

# The `actor preview --faces` rulings need a durable `direction/` home before their spec is deleted

`spec.md` is ephemeral and
is deleted on build; `CLAUDE.md` requires a decision you made to land in `direction/` first. These
are product policy, not implementation detail. Proposed text (verbatim, awaiting a yes —
suggested home `direction/trunk-and-editor.md`, since it is about what the preview tiers show):

> **The offline preview tiers.** `actor preview` renders brush volumes as authored, before CSG.
> Its `--faces` modes are `wire` (outlines, the default, needing no game content at all), `flat`
> (solid CSG-coloured fills) and `textured` (each face painted with its real texture through its
> authored UV frame). **A subtract brush shows only its far faces**, because a subtraction's
> polys are not drawn from outside in the editor or the game. **`flat` and `textured` load the
> game's class hierarchy** to tell a mover from a real subtraction, and so — unlike `wire` — need
> the game content available. **A texture the render actually needs and cannot read is a refusal,
> never a placeholder**; a scene that references no texture needs no texture source. **No cost
> ceiling is imposed** on preview size or layout. **A visual constant is chosen by looking at a
> render, not by arithmetic** — where a preview's appearance is in question (how faint a
> de-emphasised brush should be), the value is picked from an actual before/after image and that
> image is kept with the reasoning. **A SUBTRACT's faces are visible inward and an ADDITIVE's
> outward; beyond that the preview shows what would really be seen** — nearest surface wins per
> pixel, no brush privileged. **`--focus` is a brightness filter and nothing more:** it never
> changes what is visible or what hides what, so a box inside a room is not occluded by the room's
> far wall whether the room is focused or not. **`--highlight` OVERRIDES `--focus`'s dimming** — a
> highlighted face is never faded — **but under a filled mode it re-colours only what is VISIBLE and is
> never an x-ray**: a highlighted face that depth hides shows no fill, no outline and no index, so
> highlighting it changes the render not at all. **A SOLID BRUSH IS OPAQUE**: under a filled mode an
> outline draws only where its face is visible, so a brush sealed inside a solid one shows nothing of
> itself — not its fill and not its wireframe.

**⚠ TWO OF THESE RULES REACHED THEIR CURRENT SHAPE THROUGH SUPERSEDED EARLIER RULINGS.** Both were ruled
more than once, in different directions, on the same feature. **A reader who finds an earlier ruling in
isolation — in a chat log, a superseded review report, or git history — and acts on it will undo a
deliberate decision.** The current answers are the ones in the blockquote above.

**The EDGE rule, three states.** (1) Spec §4.6: only *front-facing* faces draw edges. (2) Owner ruling:
*every filled* face draws its edges — because (1) left an away-facing single-sided sheet filled with no
outline at all, and two abutting such sheets read as one block. (3) Owner ruling: every *visible* filled
face — because (2) let a brush sealed inside a solid show its whole wireframe through it (421 px). **(3)
does not undo (2):** what (2) protects is a face with no cover, which is frontmost where it sits and so
still draws — pinned at exactly the 657 px (2) was measured to win. The surviving test is visibility, never
facing; reintroducing a facing test re-breaks (2).

*(State (3) also **resolves** the sub-pixel silhouette item that state (2) generated — a 16-segment
cylinder loses the 5 px it gained, because an edge that overhung a silhouette was on a hidden face by
definition. That item lives on `main` (commit `b19c621`), not on this feature branch, so it cannot be
folded out from here: **delete it when this branch merges.**)*

**The `--highlight` rule, three states**, below. On 2026-07-29
the owner first ruled that `--highlight` overrides `--focus` *including* drawing a highlighted face's solid
fill over nearer context, and accepted that consequence explicitly. Then it was narrowed to "the outline
carries a buried highlight", and finally, for consistency with the physical model, to nothing at all: a
highlight is a re-colouring of what is visible, never an x-ray. All three states are pinned by one test
that has been inverted twice
(`test_a_buried_highlighted_face_contributes_NOTHING_because_highlight_is_not_x_ray`), whose docstring
names the sequence. A highlight that lands on nothing visible now says so on **stderr**, naming the
selector — the owner considered dropping `--highlight` for being able to do nothing, and kept it with the
note instead.

**Consequences recorded with the ruling, so nobody re-derives them as defects:**

- **It SUPERSEDES TWO of the build plan's S3 Done-whens, and they are annotated as such in it.**
  (a) *"A focused brush fully enclosed by another brush is visible"* — a brush sealed inside a solid ADD
  is now invisible when focused, deliberately, because `--focus` is not x-ray vision. Its test was
  **inverted rather than deleted**
  (`test_a_focused_brush_inside_a_SOLID_ADD_stays_hidden_because_focus_is_not_x_ray`).
  (b) *"Two passes with **separate** depth buffers … the focused brush drawn after, never occluded by
  context"* — separate depth buffers let `--focus` decide which of two COPLANAR faces was visible (the
  de-emphasised pass rasterized first, and the depth test is strictly `<`), so it is ONE scene-order pass
  with a per-pixel dim mask instead. The "composited **once**" half of that Done-when is delivered; the
  two-buffer half is not, and must not be restored.
  Both reversals are visible to anyone reading the plan against the code.
- **On-face index opacity grading is NOT a defect.** A review round measured the focused brush's face
  numbers being faded by a brush *behind* it and proposed grading the focused brush against itself
  only. That rested on the focused brush being un-occludable; under this model a brush in front
  genuinely does hide it, so grading down is the correct signal, `_occluder_count`'s existing
  self-or-solid rule stands unchanged, and `test_focus_does_not_shift_decal_grading` stays. Do not
  "fix" it from the old reasoning.

If you would rather these stay agent-side, say so and they go to `rationale/` instead — but they
cannot stay only in an ephemeral spec. *(2026-07-26; the visibility model, the `--focus` and
`--highlight` sentences and the consequences added 2026-07-29, as the owner ruled them during S3 — the
slug's "four" is its permanent identity, not a count.)*
