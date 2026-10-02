# brush build

Parametric brush primitives (UnrealEd's GUI BrushBuilders, replicated model-side). Writes one actor
T3D (the **spiral** writes a central column plus one wedge-tread actor per step — `N+1` actors,
ascending monotonically around the column; the **staircase** is a single non-convex brush actor).

```
brush build cube      --width W --breadth B --height H
brush build cylinder  --height H --radius R [--sides 8] [--align-to-side] [--axis x|y|z]
brush build cone      --height H --radius R [--sides 8] [--align-to-side] [--axis x|y|z]
brush build sheet     --width W --height H [--plane xy|xz|yz] [--flag NAME …]
brush build staircase --steps N --depth D --rise R --breadth B
brush build spiral    --steps N --inner-radius R --step-width W --rise H [--angle-per-step 8192]
brush build extrude   --point U,V --point U,V --point U,V […] --depth D [--axis x|y|z]
brush build revolve   --point U,V --point U,V --point U,V […] --angle UU [--segments N] [--axis x|y|z]
```

Common options on **every** shape: `--at X,Y,Z` (world Location; see Pivots), `--base-name`,
`--csg add|subtract`, `--solidity solid|semisolid|nonsolid`, `--folder`, `--label`, `--texture`,
`--rotate PITCH,YAW,ROLL`, `--prop KEY[.PATH]=VALUE`, `--mover-class Package.Name`. (There is no
`--group` flag — the engine `Group` property is set with `--prop Group=<name>`.)

**Every dimension must be greater than zero.** A width, breadth, height, radius, depth, rise, inner
radius or step width that is negative or zero is rejected up front — exit 2, naming the flag and
value (`brush build staircase: --depth must be greater than 0, got -32.0`). A negative length would
otherwise build a self-overlapping, inside-out brush that looks fine until the map build fails with
an unrelated-looking BSP error. Counts and angles keep tighter rules: `--steps` needs at least 1,
`--sides` at least 3, `--angle-per-step` between 0 and 32768 unreal rotation units (a half turn), and
`--angle` between 0 and 65536.

**Builder angles are unreal rotation units, like `--rotate`** — `16384` = 90°, `65536` = a full
turn — never degrees. `spiral --angle-per-step` defaults to `8192` (45°). Thirds are not exactly
representable (`65536` is a power of two), so a 60° sweep is `10923` uu = 60.002°. `cylinder`/`cone`
take no angle at all: the useful control there is the **`--align-to-side`** flag, which offsets the
cross-section by half a segment (`180/--sides` degrees) so a flat FACE, rather than a vertex, meets
an axis-aligned wall — the same as UnrealEd's own `AlignToSide` checkbox. For any other cross-section
angle use `--rotate`, whole-actor placement. `--sides` has no upper bound: above 16 a round cap is
split into several convex `Cap`/`Base` faces (an engine face holds at most 16 vertices), so the brush
stays one solid built from valid faces.

**`cylinder`/`cone --axis x|y|z` (default `z`)** orients the prism's long axis along that world axis
directly — the vertices are built rotated, so **no `Rotation` field is emitted** and a horizontal
pipe or beam needs no `--rotate`. It is the axis the n-gon cross-section is normal to; the `(U,V)`
map onto the other two world axes in right-handed cyclic order, the same meaning as
`extrude`/`revolve --axis`: `z` → cross-section in X,Y; `x` → Y,Z; `y` → Z,X. For any other
orientation use `--rotate`, which stacks on top. `sheet` keeps `--plane` (the plane it lies in),
`cube` takes neither.

- **`--rotate PITCH,YAW,ROLL`** (unreal rotation units — 16384 = 90°, 65536 = a full turn) **SETS** the emitted actor's `Rotation` field absolutely (a
  fresh actor is at identity, so no add-vs-override ambiguity). The rotation is **stored on the
  actor, not baked into the vertices** (matching UnrealEd); a warning goes to stderr if it carries
  any vertex off the integer grid (the editor snaps them on import). It lives on the generators, not
  on `actor add`. Passing `--rotate 0,0,0` **writes** `Rotation=(Pitch=0,Yaw=0,Roll=0)` (an omitted
  `Rotation` means "the class default", which is not zero for every class); leave the flag off
  entirely to emit no `Rotation` at all.
- **`--prop KEY[.PATH]=VALUE`** (repeatable) bakes a property into the T3D, **schema-validated against
  the emitted actor's class** (`Engine.Brush`, or `--mover-class`) before emit — same grammar as
  `actor prop set`. Overrides compose over the generator's own fields (incl.
  `CsgOper`/`PolyFlags`/`Group`/`Rotation`), so a `--prop` can override a dedicated flag.
- **Pivots:** cube/cylinder/cone/**sheet** are **centered on the origin** (`--at` sets the geometric
  center on every axis, including Z); the **staircase uses a front-bottom-corner pivot** — its
  geometry spans `0..steps·depth` in X, `0..breadth` in Y, `0..steps·rise` in Z (entirely at/above the
  floor), so `--at` places that min corner; the **spiral anchors at the base of its column axis**
  (centred in XY, *bottom* in Z); **`extrude`/`revolve` anchor on profile coordinate `(0,0)`** —
  for a revolve that is the bend centre (see below).
- **Item labels:** every built face carries UED's `Item` (ItemName) tag (`Base`/`back`/`Step`/`Rise`/
  `Side` on the staircase, `OUTSIDE` on the cube, `Cap`/`Side<k>` on `extrude` and `revolve`,
  `Side`/`Cap`/`Base`/`Sheet` on the others) — a semantic selection handle for `brush poly find
  --item …`. Address a specific staircase face (a tread, a riser, one side strip) via its `Item`,
  since the whole staircase is one actor.
- **`sheet`** defaults to TwoSided + NotSolid (a fence / masked panel). **`--flag NAME`**
  (repeatable) ORs extra surface/poly flags onto the sheet's face AT BUILD TIME on top of that
  default — `--flag portal --flag translucent` bakes a zone portal in one step instead of a follow-up
  `brush poly set --add-flag`.
- **`staircase` = ONE non-convex brush** named `Staircase` (or `--base-name`): the UED
  `LinearStairBuilder` stepped wedge — `Base` + `back` + per-step `Step`/`Rise` + tiled convex `Side`
  strips, `2 + 4·steps` faces. Its per-step boundaries are watertight T-junctions that `level doctor`
  accepts. **Native caveat:** UnrealEd (the default `level materialize`) and the real engine (the
  default `level photo --game`) build this non-convex brush correctly, but the experimental native
  CSG core assumes convex brushes, so `level photo --native` mis-builds its concave notches — use
  `--game`/UnrealEd for staircases. **Spiral is currently rough** (rectangular slabs, gaps) — prefer
  a cylinder column + per-step wedges until it's redone.

### `extrude` — sweep a profile you draw

Every other shape is *fixed parametric*: you choose sizes, never a silhouette. `extrude` takes a
**profile** — a closed 2D polygon you draw point by point — and sweeps it in a straight line, so an
L-shaped ledge, an arch voussoir, a moulded cornice or a chamfered pillar is one command instead of
hand-written T3D or a chain of `brush clip` planes.

```bash
# an L-shaped ledge, 16 uu deep, swept along Y
uedcli brush build extrude --axis y --depth 16 --at 0,0,0 \
  --point 0,0 --point 96,0 --point 96,32 --point 32,32 --point 32,96 --point 0,96 \
  --folder castle.hall --texture CoreTexBrick.Brick.DrtyGrayWalks_A | uedcli actor add -
```

- **`--point U,V` (repeatable, ≥3)** is one profile vertex in the profile's own 2D coordinates;
  **argument order is ring order**. The ring is **closed implicitly** — do not repeat the first
  point as the last (harmless if you do: it is welded away). Either winding is accepted.
- **`--axis x|y|z` (default `z`)** names the world axis the profile plane is **normal to** —
  equivalently, the direction the sweep grows. `(U,V)` map onto the other two world axes in
  right-handed cyclic order:

  | `--axis`        | `U` | `V` | the sweep grows along |
  |-----------------|-----|-----|---|
  | `z` *(default)* | X   | Y   | +Z |
  | `x`             | Y   | Z   | +X |
  | `y`             | Z   | X   | +Y |

- **`--depth D`** is the sweep length in world units, and must be greater than 0.
- **`--at` is the world point profile coordinate `(0,0)` lands on.** The local vertices are the
  coordinates you drew, verbatim — nothing is re-centred — and the sweep runs `0..depth` from there.
  So a ring of voussoirs drawn at known offsets stays laid out as drawn. **Consequence:** `--rotate`
  turns an actor about its local origin, here profile `(0,0)`, not the brush's centre — a profile
  drawn away from `(0,0)` *swings through an arc* instead of turning in place.
- **The profile must be a simple ring.** Duplicate and collinear points are cleaned away silently
  (the engine drops them at build time anyway); a ring that crosses itself, touches itself, revisits
  a vertex, or encloses zero area is rejected with exit 2 naming the offending points — such a
  profile has no consistent inside, and the brush would be a self-intersecting solid (a guaranteed
  BSP defect).
- **Faces:** `Cap` at each end plus one `Side<k>` per profile edge, numbered in ring order — so
  `brush poly find --item Side0` selects "the face swept by my first profile edge". The numbering
  follows the *cleaned, counter-clockwise* ring: the same shape starting at a different vertex
  renumbers the sides.
- **Concave profiles are fully supported, as ONE brush.** The engine's polygon must be convex and
  holds at most 16 vertices, so a concave profile (an L, a notched cornice) or one longer than 16
  points has each of its two **caps tiled into several convex faces** — the brush itself stays
  single and non-convex, like `brush build staircase`. The tiling only adds *diagonals* of your
  profile, never a new point on its outline, so the solid stays watertight. Face count is
  therefore `points + 2 × cap-pieces`. **Native caveat:** UnrealEd (the default `level
  materialize`) and the real engine (the default `level photo --game`) build a concave brush
  correctly, but the offline draft renderer `level photo --native` assumes convex solids, so it
  draws a concave notch *filled in* — that is a rendering artefact, not a geometry bug.

### `revolve` — sweep a profile around an axis

Same profile, same `--axis`, same `--at`; instead of a straight `--depth` it sweeps the profile
**around the profile plane's own `V` axis** — the line `U = 0`, through profile coordinate `(0,0)`.
So `--at` is the world position of the **bend centre**, and how far the shape sits from it is written
in the profile: a profile drawn at `U ∈ [64, 192]` revolves at radii 64 to 192. (Hence no `--pivot`
flag — moving the profile and moving the axis are the same operation.)

```bash
# a 90° curved corridor, 128 uu wide and tall, bending around the world origin
uedcli brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 \
  --at 0,0,0 --folder castle.corridor | uedcli actor add -
```

- **`--angle UU`** is the total sweep in **unreal rotation units**, the same units as `--rotate`:
  `16384` = 90°, `65536` = a full turn. It must satisfy `0 < angle <= 65536`. Thirds are not
  exactly representable (`65536` is a power of two), so a 60° bend is `--angle 10923` = 60.002°.
- **`--segments N`** is how many flat facets the sweep is cut into. Default is **one facet per
  22.5°** — 4 for a 90° bend, 16 for a full turn, matching UnrealEd's density. A facet of 180° or
  more is flat (zero volume) and is rejected.
- **`--angle 65536` is a CLOSED turn:** the two caps would coincide, so both are omitted and the
  last facet's far ring is the first facet's near ring. It needs at least 3 segments.
- **The profile must sit strictly on the positive-`U` side of the axis** — every point's `U` > 0.
  A profile straddling the axis would sweep into a self-intersecting solid; one merely touching it
  would collapse the faces along the axis to zero width. To bulge the other way, mirror the
  profile's `U` values. (Solids of revolution, which need the touching case, are not supported.)
- **Faces:** a tiled `Cap` at each end (absent on a full turn) plus `points × segments` swept
  quads. Every quad of profile edge `k` is `Side<k>` **in every segment**, so
  `brush poly find --item Side0` selects the whole strip swept by your first profile edge ("the inner
  wall of the corridor").
- **A revolve is off the integer grid by construction** (every vertex away from `θ=0` lands on
  `radius · cos/sin θ`), and uedcli never snaps coordinates. An off-grid **solid** brush throws its
  BSP partition planes off-grid too, the primary cause of slivers, T-junctions and holes in the built
  map. Prefer **`--solidity semisolid`** where the swept shape is detail rather than structure: a
  semisolid receives cuts but emits no world-splitting planes.

**Two stderr advisories** fire on `extrude`/`revolve` (never on stdout, never changing exit status —
the brush is emitted either way):

- when the emitted brush has **off-grid vertices AND is solid** (the case above; not on a
  semisolid/nonsolid brush, where it is already handled, nor a `--mover-class` brush, which never
  partitions the world);
- when it has **more than 64 faces** — `points × segments` grows fast, and every face is BSP nodes
  and rendering cost. Use a simpler profile, fewer `--segments`, or `--solidity semisolid`.

See also: [`brush core`](core.md) (`brush clip`/`brush snap`/`brush replace`), [`actor build`](../actor/build.md), [the mover keyframe workflow](../../usage/mover-keyframes.md), [Brush shapes](../../leveldesign/general/brush-shapes.md) (the level-design craft this generator serves).
