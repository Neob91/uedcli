+++
priority = "p3"
kind = "debug"
summary = "bspcsg core: `first_add_seed` treats ANY leading `CSG_Add` as the convex world SHELL"
+++

# bspcsg core: `first_add_seed` treats ANY leading `CSG_Add` as the convex world SHELL

*(No longer blocks the CSG merge verbs — `brush deintersect` prepends a distant
seed-subtract so the shortcut cannot fire, and all 17 goldens match the editor. Still open
for `level materialize` and any other caller whose first brush is a non-shell Add, hence
demoted to p3 rather than dropped.)* When the first brush filtered into a node-less world is an Add, the core skips
classification and SEEDS its faces as world root nodes stored REVERSED (`bspcsg.rs`, the §92 §32
convex seed). That is right for the one case every real level opens with — the first Add IS the
world box — and wrong for an Add that is a small solid sitting inside what a later subtract turns
into void: the seeded faces survive as splitters. **Verified divergent against the live editor**
2026-07-25, case `h_leading_additive_deintersect` (`brush deintersect` over `[Add pillar,
Subtract room]`): UnrealEd classifies normally, the later subtract cuts the pillar's faces away,
and it returns the plain 6-poly room void; native returns 22 polys — the void with the pillar
punched out. The code comment already states the assumption ("a NON-convex first Add would need a
real recursive `bsp_build`"); this is the first measured case where it bites. NOT fixable in the
verbs: `deintersect` cannot prepend scaffolding to move the seed off the user's first brush,
because any synthetic brush INSIDE the builder hull contributes faces that Phase 2 collects as
caps (a leading no-op wrap-ADD was measured to turn the doorway plug into the whole padded box) —
the working fix was a subtract placed OUTSIDE the hull. Golden `h_leading_additive_deintersect`
is committed and PASSING. (Found building intersect/deintersect, 2026-07-25.)
