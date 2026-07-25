# Brush geometry & the shape toolchain  [ENGINE]

The native brush builders (with their real UnrealEd parameters), the third-party extended builders, brush
clipping, curved geometry, UE1 terrain, and MeshMaker. This is the "how do I make *this shape*" reference
that feeds [csg-bsp.md](./csg-bsp.md) (a builder produces the `FPoly` list a CSG op commits).

**uedctl mapping.** uedctl exposes a subset of the native builders as `brush build {cube, cylinder, cone,
sheet, staircase, spiral}` generators, plus the 2D-shape-editor sweeps `brush build {extrude, revolve}`
(§4) — each prints a T3D snippet to stdout, committed with `… | actor add -`. Where a builder maps to a uedctl verb it is noted inline; the rest are editor-GUI shapes preserved
here for completeness (and because their params inform what a good shape looks like).

---

## 1. Native brush builders  [ENGINE]

Right-click a builder's toolbar button to open its parameter dialog. Numeric fields accept `=` math
expressions (e.g. `=64+128`) 📖, and each builder **remembers its params for the session**.

| Builder | Key params | uedctl verb | Notes |
|---|---|---|---|
| **`CubeBuilder`** | Height / Width / Breadth, WallThickness, **Hollow**, **Tessellated** | `brush build cube` | default 256³; Hollow makes a room shell; Tessellated splits faces (for vertex-editing) |
| **`CylinderBuilder`** | Height, OuterRadius, InnerRadius, **Sides**, AlignToSide, Hollow | `brush build cylinder` | default 8 sides, h256, r512. **Engine caps a single poly at 16 sides** — a cap face above 16 sides is invalid. **`AlignToSide` maps 1:1** to uedctl's `--align-to-side` (half a segment, `180/sides`°) since 2026-07-25 |
| **`ConeBuilder`** | Height, CapHeight, Outer/InnerRadius, Sides | `brush build cone` | actually a **pyramid / frustum** (a truncated cone when CapHeight < Height) |
| **`TetrahedronBuilder`** | `SphereExtrapolation` (subdivision) | — | the **"Sphere"** toolbar button; a geodesic sphere. Subdivision **max ~5** (higher → node blowup) |
| **`SheetBuilder`** | one flat poly (U/V, orientation) | `brush build sheet` | zone portals, water surfaces, banners; **NotSolid by default**; sheets **never collide** on their own |
| **`VolumetricBuilder`** | a **star of sheets** | — | crossed sheets for torches / flame / volumetric FX |
| **`LinearStairBuilder`** | StepHeight / StepWidth / StepLength / NumSteps / AddToFirstStep | `brush build staircase` | a straight run of steps |
| **`CurvedStairBuilder`** | InnerRadius, StepHeight, StepWidth, AngleOfCurve, NumSteps, CounterClockwise | — (no uedctl verb; `brush build staircase` is **linear only**) | curving run. 📖 Community advises keeping StepHeight ≤ the pawn auto-step (`MaxStepHeight` = **25** in DX; the oft-quoted "32" is looser general-stair lore, not a builder-specific limit) |
| **`SpiralStairBuilder`** | InnerRadius, StepWidth/Height/Thickness, NumStepsPer360, NumSteps, SlopedCeiling/SlopedFloor | `brush build spiral` | **native spiral-stair brushes CANNOT be subtracted** (known limit — build them additive, or use Tarquin's mk2) |
| **`TerrainBuilder`** | WidthSegments / DepthSegments | — | a tessellated cube → vertex-edit into terrain (see §4) |

---

## 2. Tarquin's Extended Brush Builders  [ENGINE]  📖

Third-party `.u` add-ons (installing them edits the `[UnrealEd.EditorEngine]` builder entries). They fill
gaps in the native set:

- **mk2 Cylinder** — partial revolutions / wedges via `SidesUsed`.
- **mk2 Spiral / Curved Stair** — **CAN be subtracted** (fixes the native spiral limit); Top/Bottom Style
  Flat / Sloped / Stepped.
- **mk2 Torus** — Outer/Tube radius, Wheel/Tube sides (drops polys above 16×16).
- **mk2 Panorama** — a ring of sheets for **skybox backdrops / waterfalls**.
- **Parallelepiped**, **Wave** (sine-grid terrain).
- **Extruder** — sweep a 2D profile along a `PathPoints[]` list (absolute or relative) for **pipes / curved
  tubes**; auto-caps unless the path is a closed loop.

These are not exposed as uedctl verbs; they are GUI builders. Their existence matters because they are the
sanctioned way to get subtractable spirals and swept tubes without off-grid vertex editing.

---

## 3. Brush clipping  [ENGINE] 📖

The clip tool cuts an existing brush against a plane:

- Place **clip markers with Ctrl+RMB in a 2D view** — **2 markers define a cut plane** (vertical in that
  view); a **3rd marker tilts that plane to an arbitrary angle** — still ONE planar cut, not a compound
  multi-plane cut.
- **Clip** discards one side (the marker tick indicates which side is kept); **Split** keeps **both**
  halves as separate brushes; **Flip Clipping Normal** swaps which side is kept.
- **Transform-Permanent the brush first** (so the cut operates on baked coords).

---

## 4. Curved geometry  [ENGINE] 📖

- **Every 2D-shape-editor operation yields ONE brush** ✅ — extrude, revolve and sheet all produce the
  single red **builder brush**, faceted, which you then Add/Subtract once. It is not one brush per
  facet or per segment. *(Andrzej, from direct UnrealEd use, 2026-07-25.)* This is what
  `brush build revolve` mirrors: one non-convex brush per sweep, not one per segment — `decisions.md`
  2026-07-25 00:14 UTC (D5).
- **Curved corridors** — 2D-editor **Revolve**: move the green pivot *away* from the cross-section, then
  revolve. 16 pieces = 360°; `Use`=4 → a 90° bend.
  **Revolve HAS a uedctl verb since 2026-07-25**: `brush build revolve --point U,V … --angle UU
  [--segments N]`. Its axis is fixed at the profile's own `u = 0` line, so "move the pivot away from the
  cross-section" is spelled by drawing the profile away from `u = 0` (`decisions.md` 2026-07-25 01:05 UTC,
  D10). The `--segments` default is one facet per 22.5°, i.e. the 16-pieces-per-turn density above — which
  is a 📖-level fact, so the default rests on inferred semantics rather than a measurement. The straight
  case is `brush build extrude --point U,V … --depth D`.
- **Curved arches** — 2D-editor **Bézier** segments traced on a reference BMP.
- **The iris doorway** — **8 quarter/eighth-segment movers** all keyed to one `Event` (see
  [movers.md](./movers.md)).
- **Vertex-edited curves** need a **rebuild BEFORE editing** (moves won't take otherwise) and **destroy
  surface alignment** (re-align after — see [textures.md](./textures.md)).

> *Wolf:* "vertex manipulation in UnrealEd is buggy at best" — **prefer clean brush CSG** to vertex-edited
> curves wherever possible. Off-grid vertex edits are a prime source of the tolerance-band holes in
> [csg-bsp.md](./csg-bsp.md).

---

## 5. UE1 terrain  [ENGINE]

**UE1 terrain is 100% brush-based — there is NO heightmap `TerrainInfo` actor.** *(Debunked:* the heightmap
`TerrainInfo` is **UE2**; do not look for it in DX.)

Ways to build terrain:
- **`TerrainBuilder` + vertex editing** — a tessellated cube sculpted by hand.
- **An external tool** — TerrainED → UnrealText / `.t3d` import.
- **Iterative intersect-before-add rock CSG** — build up rock masses from intersected convex brushes.

Outdoor philosophy: keep **≤150 polys in view** ([zones-performance.md](./zones-performance.md) §3); block
sightlines with the terrain itself so total polys can be high but never all visible at once.

---

## 6. MeshMaker  [ENGINE]  📖

**MeshMaker** (external) converts a brush / prefab `.t3d` into a **mesh `Decoration`**. Trade-offs:

- **Wins:** meshes render more faces cheaply, have **no BSP holes** (they aren't world geometry), and can
  be pushable / destructible / rotating.
- **Costs:** **≤8 textures, no tiling, cylinder-only collision** (the UE1 actor-collision model — see
  [actors-collision-pathing.md](./actors-collision-pathing.md)).

The canonical fix for an ugly faceted brush pillar: convert it to a mesh Decoration so it stops cutting the
BSP and stops risking holes.

---

## 7. uedctl verb summary for this file

| Shape | uedctl | Native builder |
|---|---|---|
| Box / room shell | `brush build cube` (no `--hollow`; subtract a solid cube for a shell) | `CubeBuilder` |
| Cylinder / tube | `brush build cylinder --sides N` (poly cap ≤16) | `CylinderBuilder` |
| Pyramid / frustum | `brush build cone` | `ConeBuilder` |
| Flat sheet (portal/water/banner) | `brush build sheet` (NotSolid by default) | `SheetBuilder` |
| Straight stairs (linear only) | `brush build staircase` | `LinearStairBuilder` (the `CurvedStairBuilder` has no uedctl verb) |
| Spiral stairs | `brush build spiral` | `SpiralStairBuilder` (**native can't subtract**) |
| Drawn profile, swept straight | `brush build extrude --point U,V … --depth D` | the 2D shape editor's **Extrude** |
| Drawn profile, swept around an axis | `brush build revolve --point U,V … --angle UU` | the 2D shape editor's **Revolve** |

Geodesic spheres, volumetric star-sheets, terrain tessellation, the Tarquin extended builders, clipping,
Bézier curves, and MeshMaker are **editor-GUI / external-tool** shapes with no uedctl generator — author
their output as a T3D snippet (or a prefab) and bring it in via the normal `actor add -` path.
