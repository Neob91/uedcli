# Spike: UnrealEd (UE1) brush-wire colors — exact RGB + which C_ constant colors which brush type

**Date:** 2026-07-22
**Question:** What exact RGB does the original UnrealEngine-1 UnrealEd use for each
brush-wire color in its 2D/3D viewports, and specifically — are semisolid (pink) and
mover (magenta) genuinely similar colors, or is our palette diverging from UED?

**TL;DR:** The colors are `EditorEngine` config constants (`C_*`) with their default RGB in
`Engine/Config/Default.ini`. **The constant *names* are misleading**: a semisolid brush is
NOT drawn with `C_SemiSolidWire`. The drawing code in `UnEdRend.cpp` picks:
semisolid → **`C_ScaleBoxHi` = (223,149,157)** (a muted warm rose-pink), while
`C_SemiSolidWire` (chartreuse green) is actually used for **portal** brushes. Mover →
`C_Mover` = (255,0,255) vivid magenta. So in authentic UED, semisolid and mover ARE in the
same warm/purple-pink neighbourhood but differ sharply in **saturation** (dusty rose vs vivid
magenta) — see the distinguishability section.

---

## Sources

- **Default.ini** (RGB values): `https://raw.githubusercontent.com/fgsfdsfgs/UE1/master/Engine/Config/Default.ini`
  (retail UE1 v200 source mirror, `[Editor.EditorEngine]` section)
- **EditorEngine.uc** (the `var(Colors) config color C_*` declarations):
  `https://raw.githubusercontent.com/fgsfdsfgs/UE1/master/Source/Editor/Classes/EditorEngine.uc`
- **UnEdRend.cpp** (`DrawLevelBrush` — the code that maps brush type → C_ constant):
  `https://raw.githubusercontent.com/fgsfdsfgs/UE1/master/Source/Editor/Src/UnEdRend.cpp`
- BeyondUnreal wiki, UnrealEd Viewport (colour list):
  `https://beyondunrealwiki.github.io/pages/unrealed-viewport.html`
- BeyondUnreal wiki, Semisolid ("coloured pink in UnrealEd"):
  `https://beyondunrealwiki.github.io/pages/semisolid.html`
- BeyondUnreal wiki, EditorEngine:
  `https://wiki.beyondunreal.com/Legacy:EditorEngine` (403 to the fetcher; listed for completeness)
- Deus Ex SDK "How to add a Deus Ex style door" (confirms 3 stacked brushes: red selection,
  blue Addition, purple Mover): reached via
  `https://mirror.deusexnetwork.com/dxediting.com/` tutorials / DX SDK getting-started docs.

---

## The mapping: brush type → C_ constant → RGB

**All RGB values are `source-verified`** — quoted from `Default.ini`'s `[Editor.EditorEngine]`
section. **The type→constant mapping is `source-verified`** from `UnEdRend.cpp::DrawLevelBrush`.

| Brush type / viewport element             | C_ constant       | RGB                | Reads as        |
|-------------------------------------------|-------------------|--------------------|-----------------|
| Active BUILDER brush (`Level->Brush()`)   | `C_BrushWire`     | (255, 63, 63)      | red             |
| Additive solid (`CSG_Add`, default)       | `C_AddWire`       | (127, 127, 255)    | periwinkle blue |
| Subtractive (`CSG_Subtract`)              | `C_SubtractWire`  | (255, 192, 63)     | amber / yellow  |
| **Semisolid** (`PF_Semisolid`)            | **`C_ScaleBoxHi`**| **(223, 149, 157)**| dusty rose-pink |
| Non-solid (`PF_NotSolid`)                 | `C_NonSolidWire`  | (63, 192, 32)      | green           |
| Zone **portal** (`PF_Portal`)             | `C_SemiSolidWire` | (127, 255, 0)      | chartreuse      |
| Mover (`IsMovingBrush()`)                 | `C_Mover`         | (255, 0, 255)      | vivid magenta   |
| Other non-Add CSG oper                    | `C_GreyWire`      | (163, 163, 163)    | grey            |
| Custom (`Actor->bColored`)                | (Actor->BrushColor)| per-actor         | —               |

### The exact drawing logic (`source-verified`, `UnEdRend.cpp::DrawLevelBrush`)

```cpp
if( Actor==Level->Brush() )
{
    WireColor = C_BrushWire.Plane();          // active builder brush -> red
    LineFlags |= LINE_Transparent;
}
else if( Actor->IsMovingBrush() )
{
    WireColor = C_Mover.Plane();              // mover -> magenta
}
else if( Actor->IsStaticBrush() )
{
    WireColor
    =	(Actor->bColored                  ) ? Actor->BrushColor.Plane()
    :	(Actor->CsgOper==CSG_Subtract     ) ? C_SubtractWire.Plane()   // subtract -> amber
    :	(Actor->CsgOper!=CSG_Add          )	? C_GreyWire.Plane()       // other oper -> grey
    :	(Actor->PolyFlags & PF_Portal     )	? C_SemiSolidWire.Plane()  // PORTAL -> chartreuse (!)
    :	(Actor->PolyFlags & PF_NotSolid   ) ? C_NonSolidWire.Plane()   // nonsolid -> green
    :	(Actor->PolyFlags & PF_Semisolid  )	? C_ScaleBoxHi.Plane()     // SEMISOLID -> rose-pink
    :										  C_AddWire.Plane();           // plain add -> blue
}
```

**Key gotcha (`source-verified`):** despite the name, `C_SemiSolidWire` is used for
`PF_Portal` brushes, and `C_NonSolidWire` for `PF_NotSolid`; a *semisolid* brush
(`PF_Semisolid`) borrows `C_ScaleBoxHi` — the same rose the scaling-gizmo highlight uses.
The ordering also matters: `PF_Portal` is tested before `PF_NotSolid` before `PF_Semisolid`,
so a brush with several flags takes the first match. Do not trust the constant name; trust
`DrawLevelBrush`.

### Full `C_*` palette from Default.ini (`source-verified`, for reference)

```
C_WorldBox        = (0,0,107)      C_GroundPlane   = (0,0,63)       C_GroundHighlight = (0,0,127)
C_BrushWire       = (255,63,63)    C_Pivot         = (0,255,0)      C_Select          = (0,0,127)
C_AddWire         = (127,127,255)  C_SubtractWire  = (255,192,63)   C_GreyWire        = (163,163,163)
C_Invalid         = (163,163,163)  C_ActorWire     = (127,63,0)     C_ActorHiWire     = (255,127,0)
C_White           = (255,255,255)  C_SemiSolidWire = (127,255,0)    C_NonSolidWire    = (63,192,32)
C_WireGridAxis    = (119,119,119)  C_ActorArrow    = (163,0,0)      C_ScaleBox        = (151,67,11)
C_ScaleBoxHi      = (223,149,157)  C_Mover         = (255,0,255)    C_OrthoBackground = (163,163,163)
C_Current         = (0,0,0)        C_BrushVertex   = (0,0,0)        C_BrushSnap       = (0,0,0)
C_Black/C_Mask/C_WireBackground/C_ZoneWire = (0,0,0)
```

Note the earlier spike's `C_ActorArrow=(163,0,0)`, `C_Mover=(255,0,255)`,
`C_GroundHighlight=(0,0,127)` all match here. That spike read the collision/radii-overlay
usage; this spike adds the **brush-wire** usage, confirming `C_Mover` is shared between the
mover collision overlay and the mover brush wire, while the brush-type wires use
`C_AddWire/C_SubtractWire/C_ScaleBoxHi/C_NonSolidWire/C_SemiSolidWire/C_GreyWire`.

---

## Are semisolid and mover genuinely similar? (the key question)

**Yes — they are in the same red/purple-pink family and the confusion is authentic to UED,
but UED separates them by saturation and value, not hue alone.**

| Color             | RGB              | ~Hue  | ~Sat | ~Value | Character                    |
|-------------------|------------------|-------|------|--------|------------------------------|
| Semisolid (`C_ScaleBoxHi`) | (223,149,157) | ~354° | ~33% | ~87%   | light, washed-out warm rose  |
| Mover (`C_Mover`)          | (255,0,255)   | ~300° | 100% | 100%   | fully-saturated vivid magenta|

- **Hue:** ~54° apart — semisolid sits at the red end (~354°, essentially a pale red/salmon),
  mover at magenta/purple (~300°). Not identical, but close enough that both read as
  "pinkish" at a glance, especially thin antialiased wire lines.
- **What actually separates them in real UED:** *saturation and lightness*. Semisolid is a
  pale, desaturated dusty rose; mover is a screaming pure magenta. Against UED's near-black
  viewport background, the vivid magenta pops and the dusty rose stays muted, so they're
  distinguishable in practice — the eye keys off "vivid vs washed-out," not hue.
- **Why our palette conflates them:** if both are rendered as saturated "pink"/"magenta" of
  similar lightness (and on a *light* background, where the pale rose loses the low-contrast
  cue it relies on), the only remaining separator — saturation against a dark bg — is gone.
  On white, (223,149,157) is a low-contrast light tint and (255,0,255) is high-contrast; but
  if a palette bumps semisolid's saturation up to be visible on white, it collapses toward
  the mover's magenta.

### Recommendation for a LIGHT background (keep them distinct, stay faithful)

Preserve UED's *semantic* hues but re-target lightness/saturation for a light canvas, and
widen the hue gap so the separation survives even at equal contrast:

1. **Mover** — keep the magenta/purple identity but darken for white-bg contrast, e.g.
   ~`(200,0,200)` → `(170,0,170)` (a deep magenta/purple). It must stay the vivid,
   cool purple-pink.
2. **Semisolid** — push it *away* from magenta toward warm salmon/coral (lower the blue,
   nudge hue toward ~15–20°) and darken enough to show on white, e.g. a muted terracotta/
   rose like ~`(190,110,95)`..`(200,120,110)`. This turns the "pinkish vs pinkish" clash
   into "warm coral vs cool purple," which is unambiguous regardless of background.

The load-bearing move is **hue separation** (warm/orange-red for semisolid vs cool/purple
for mover), because that survives a light background where UED's dark-bg saturation cue does
not. Keeping semisolid on the red/warm side is also faithful — UED's semisolid rose already
leans red (~354°), so pushing it a bit warmer honors the original intent while fixing the
clash. Additive stays blue, subtract amber, nonsolid green — those are already well separated
from both.

---

## Reference images

Colored multi-brush UnrealEd viewport screenshots are surprisingly scarce online; most
surviving tutorials are text + monochrome diagrams. What exists:

- **`https://beyondunrealwiki.github.io/pages/unrealed-viewport.html`** — text (not an image)
  gives the canonical colour legend: *"Red: Builder Brush; Blue: Additive; Yellow:
  Subtractive; Green: Non-solid (zone portal, sky box); Purple: Mover."* Confirms the code
  mapping above. (Note it omits semisolid from the wire legend — consistent with semisolid
  borrowing the `C_ScaleBoxHi` gizmo color rather than a named "wire" color.)
- **`https://beyondunrealwiki.github.io/images/semisolid-example-roundedcor.gif`** — a
  semisolid usage diagram (rounded-corner construction), referenced from the Semisolid page,
  which states plainly *"They are coloured pink in UnrealEd."* Diagram, not a live viewport
  color shot.
- **Deus Ex SDK "How to add a Deus Ex style door"** (mirror.deusexnetwork.com / DXEditing) —
  text description confirming that when you build a mover you see *three stacked brushes in
  the 2D viewport: the red selection brush, the blue "Addition" brush, and a purple "Mover"
  brush* — a direct real-world confirmation that add (blue) and mover (purple/magenta) sit
  side by side and are told apart by hue.

**Verification status of images:** the two wiki image URLs above are `source-verified` to
exist and be referenced by the cited pages, but neither is a single frame showing add +
subtract + semisolid + nonsolid + mover simultaneously — that ideal reference image was not
located. The color *identities* are nonetheless fully pinned by the source-verified
`Default.ini` RGB + `UnEdRend.cpp` mapping above, which is stronger evidence than any
screenshot.

---

## Suggested regression (per the spikes "pin the finding" rule)

If uedctl grows a "faithful UED palette" the numbers above are checkable facts. Worth a
`test_engine_facts`-style assertion that our brush-type→RGB table matches the source-verified
values (builder 255,63,63 / add 127,127,255 / subtract 255,192,63 / semisolid 223,149,157 /
nonsolid 63,192,32 / mover 255,0,255), with this spike back-referenced, so a palette edit that
drifts from UED trips a red test instead of silently diverging.
