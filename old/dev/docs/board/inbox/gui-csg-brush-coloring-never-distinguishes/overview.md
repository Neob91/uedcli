+++
priority = "p?"
kind = "unknown"
summary = "GUI CSG brush coloring never distinguishes Intersect/Deintersect from Add"
+++

# GUI CSG brush coloring never distinguishes Intersect/Deintersect from Add

Filed from a UED22-vs-GUI-spec gap audit (2026-09-15) of `dev/docs/board/to-plan/uedcli-human-gui/`
and `dev/docs/board/to-build/gui-slice-2-quad-layout-ortho-views-matching/`.

## UED22 fact

`CsgOper` has (at least) four real, per-actor-authorable values: `CSG_Add`, `CSG_Subtract`,
`CSG_Intersect`, `CSG_Deintersect` — not just Add/Subtract. `dev/docs/unrealed/quirks.md` "CSG
model": `BRUSH FROM INTERSECTION` / `DEINTERSECTION` is a real editor operation, decoded to
instruction level and ported natively as `bspcsg.rs::intersect_brushset` — uedcli ships real
`brush intersect`/`brush deintersect` CLI verbs that write actors carrying these CsgOper values into
the trunk (not just transient builder-brush state). A trunk can genuinely contain an
Intersect/Deintersect brush actor today.

## What the GUI spec says

The main spec's "Shading & actor representation" section and `gui-slice-2-quad-layout-ortho-views-
matching/spec.md` section 2 both specify CSG-classification brush coloring by reusing
`actor diagram`'s (`uedcli/preview.py`) palette verbatim: "added-solid = blue, subtracted =
yellow/gold, semi-solid = warm coral, non-solid = green, mover = magenta/purple." Slice 2 explicitly
confirms the backend already computes this for every brush actor
(`uedcli/serve/scene.py:_brush_highlight` → `classify_brush`) and instructs extending the existing
draw logic to render every actor's `brush.color` in ortho panes, not inventing a new classification.

## The gap

`preview.classify_brush` (`uedcli/preview.py`) only tests `oper == "CSG_Subtract"`; every other
value — including `CSG_Intersect` and `CSG_Deintersect` — falls through to the `"add"` branch
(further refined only by `PolyFlags` into `semisolid`/`nonsolid`):

```python
oper = next((v for k, v in actor.props if k == "CsgOper"), "CSG_Add")
if oper == "CSG_Subtract":
    return "subtract"
pf = ...
if flags & PF_SEMISOLID: return "semisolid"
if flags & PF_NOTSOLID: return "nonsolid"
return "add"
```

So a real `CsgOper=CSG_Intersect`/`CSG_Deintersect` brush actor renders identically to a plain
additive brush — same blue wireframe, same "add" classification feeding `is_solid`/occluder
treatment — in `actor diagram` stills today, and (per Slice 2's own instruction to reuse this exact
logic for every ortho pane, plus the already-shared Perspective pane) in the live GUI viewport too.
No GUI spec's color legend mentions Intersect/Deintersect at all, so a level author using
`brush intersect`/`deintersect` gets no visual distinction for those brushes anywhere in the GUI —
they read as ordinary additive geometry.

## Why this matters

CSG classification coloring is the GUI's/`actor diagram`'s one at-a-glance way to understand a
level's brush composition. Intersect/Deintersect brushes are a real, distinct CSG semantic (`builder
∩ world` / its complement, quirks.md) that a level author can genuinely place in a trunk — silently
mislabeling them as additive is a real information loss, not a cosmetic nit.

## Not filed as an implement task

This finding doesn't pick a fifth palette color or a UX treatment (a design call, not investigation's
job) — it establishes that the gap is real and where it lives (`classify_brush`, `_CSG_PALETTE`,
every spec text listing the palette). Left for triage/spec.
