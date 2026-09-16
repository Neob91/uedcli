+++
priority = "p?"
kind = "unknown"
summary = "GUI ortho marquee spec omits UnrealEd's brush-full-containment vs point-pivot select rule"
depends-on = ["ortho-marquee-drag-select-rubber-band-multi"]
+++

# GUI ortho marquee spec omits UnrealEd's brush-full-containment vs point-pivot select rule

Filed from a UED22-vs-GUI-spec gap audit (2026-09-15) of `dev/docs/board/to-plan/uedcli-human-gui/
spec.md` and the deferred `ortho-marquee-drag-select-rubber-band-multi` board item.

## UED22 fact

`dev/docs/unrealed/quirks.md` "Selection": "**Brush selection needs full containment, point actors
select by pivot.** A brush is INSIDE-selected only when the builder box fully encloses its geometry
(not pivot-inside, the rule for Lights etc.)." This is a real, asymmetric box-select rule: a
rectangle/box drag in UnrealEd only picks up a brush if the WHOLE brush lies inside the drag region;
a point actor (Light, etc.) is picked up as soon as its pivot point is inside, regardless of any
visual radius/sprite extent.

## What the GUI spec says

The main spec's "Selection & inspector (read-only)" section: "LMB tap ... selects in any pane;
Ctrl+tap multi-selects; **ortho marquee**; clicking an actor in the tree selects + frames it." No
containment rule is stated. The deferred build item, `dev/docs/board/inbox/
ortho-marquee-drag-select-rubber-band-multi/overview.md`, scopes the mechanism (projecting each
candidate actor's AABB into ortho screen space, testing against the dragged rectangle) and flags two
real gaps of its own (a new projection mechanism; an unresolved drag-vs-pan button conflict) — neither
mentions a containment rule at all.

## The gap

The deferred item's own framing — "project every candidate actor's AABB ... and test which projected
boxes intersect a dragged screen rectangle" — describes an ANY-INTERSECTION test (the common
web/game-editor marquee default), not UnrealEd's actual FULL-CONTAINMENT test for brushes. If built
as scoped, a brush partially inside the drag rectangle would be selected in the GUI but would NOT be
selected in real UnrealEd — a real behavior mismatch a UnrealEd-experienced user would notice and be
confused by, silently baked in by the natural reading of "intersect a dragged rectangle." Point-actor
marquee-select (pivot-in-box) is not itself wrong under an AABB-intersection test only because a point
actor's AABB collapses to (approximately) its pivot — but that convergence isn't called out either, so
it reads as coincidence rather than a verified match.

## Why this matters

This is exactly the kind of non-obvious per-actor-kind selectability rule `quirks.md`'s own framing
warns about (it lives in a document titled specifically to catch "non-obvious behaviors that silently
bite"). Marquee-select is deferred, not built yet, so this is the cheapest point to fix it — before an
implementation locks in the wrong test.

## Not filed as an implement task

Marquee-select itself is already deferred (its own item, `ortho-marquee-drag-select-rubber-band-
multi`) pending an owner ruling on the drag-vs-pan button conflict. This finding should fold into
that item's spec once it's picked up — flagged here separately per this audit's scope (findings go to
inbox, not silently merged into another item's file).
