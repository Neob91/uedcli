+++
priority = "p1"
kind = "owner-question"
summary = "[OWNER — confirm] a direction/ home for the actor-preview parity rules (textured = CSG-solved world, wire+textured only, bspcsg core, black bg)."
+++

# [OWNER — confirm] direction/ home for the actor-preview parity rules

`actor-preview-unrealed-render-parity-new-csg` landed (in `done/`). Its spec is ephemeral and is
deleted; `CLAUDE.md` requires the durable product intent to live in `direction/` first. There is no
actor-preview direction topic yet. Proposed text (verbatim, awaiting a yes — suggested home a new
actor-preview topic, or a section of `direction/trunk-and-editor.md`):

> **`actor preview` render modes.** `actor preview` (and `stash`/`prefab preview`) render the trunk
> offline, matching UnrealEd's viewport, on a BLACK background. `--faces` has exactly two values:
> - **`wire`** (default) — CSG-coloured outlines only; a content-free schematic that needs no game
>   install and works on `--from-t3d` from anywhere.
> - **`textured`** — the CSG-SOLVED textured world, as UnrealEd's 3D viewport draws it: the set is run
>   through the native CSG solve and only the surfaces that SURVIVE are drawn, each through its real
>   texture and authored UV frame. Visibility is spatial CONTAINMENT, not a per-brush rule — an
>   additive brush not inside subtracted space is invisible — and a subtracted room shows its interior
>   via a per-view backface cull (each surviving fragment whose post-CSG normal faces away from the
>   camera is dropped). Texture alignment holds across CSG splits. Movers are excluded from the world
>   solve and draw as a magenta overlay; point actors keep their sprite/marker overlay.
> - The solve routes through the faithful `build_geometry_bspcsg` core (not the default core, which
>   mis-renders overlapping-subtract doorways). Its residual byte-divergences are acceptable for a
>   visual preview.
> - `textured` needs a resolved project, the games config, and every texture a SURVIVING surface
>   references readable (a needed-but-unreadable texture is a refusal, never a placeholder); it rejects
>   `--brush-colors` and scaled/sheared brushes. A solve that leaves zero surfaces (with world brushes
>   present) is exit 2; a point/mover-only set draws its overlays over black at exit 0.

Known open question that should be resolved alongside this (or noted as accepted): the bspcsg core
starts from an EMPTY world, so an ADDS-ONLY set renders instead of being invisible — see board item
`actor-preview-bspcsg-starts-from-an-empty-world`. If seeded solid, the "invisible add" wording above
holds for the no-subtract case too.

This SUPERSEDES the older proposal in `four-actor-preview-faces-rulings-need-a-durable` (flat mode,
per-brush textured, grey ground) — see the supersession note there.
