+++
priority = "p1"
kind = "owner-question"
summary = "Four `actor preview --faces` rulings need a durable `direction/` home before their spec is deleted"
+++

# Four `actor preview --faces` rulings need a durable `direction/` home before their spec is deleted

`specs/2026-07-26-actor-preview-textured-faces.md` is ephemeral and
is deleted on build; `CLAUDE.md` requires a decision you made to land in `direction/` first. These
four are product policy, not implementation detail. Proposed text (verbatim, awaiting a yes —
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
> image is kept with the reasoning.

If you would rather these stay agent-side, say so and they go to `rationale/` instead — but they
cannot stay only in an ephemeral spec. *(2026-07-26.)*
