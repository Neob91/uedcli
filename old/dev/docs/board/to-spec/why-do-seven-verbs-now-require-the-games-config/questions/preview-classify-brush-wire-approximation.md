# `preview.classify_brush` wire path: documented name-guess, or thread the real index?

## Context

`*preview` (actor/stash/prefab) has two paths. **Filled** modes already resolve the real
`is_mover` index via `cli/rendering.preview_movers` and already require a project — unchanged.
**Wire** (the default; resolver-free, works on `--from-t3d` outside a project) uses
`classify_brush(is_mover=None)`'s `bare.endswith("Mover")` name guess (`preview.py:361`) only to
pick the magenta mover COLOUR — it never affects geometry.

The item requires this to come out with ONE definite answer:

- **Recommended — documented cosmetic approximation.** Keep the name guess for wire; it only
  mis-colours a wireframe of a mover whose class name doesn't end in `Mover` (`CEDoor`,
  `BreakableGlass`, case-mismatched `fanmover`), never a filled render. Record it as deliberate in
  `architecture.md` "Mover support" and the `classify_brush` docstring (both already flag it pending
  this item). Wire stays resolver-free.
- **Alternative — thread the index into wire.** Correct colour always, but pulls `*preview` wire into
  the resolver-requiring set — the opposite of this item's aim, and it breaks `--from-t3d` preview
  outside a project.

## Answer

<!-- Empty = open. -->
