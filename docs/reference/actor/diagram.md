# actor diagram

A self-rendered **colour** image (no editor) so you can see geometry and map **poly index ↔
face**. Reads named actors from the current level, model-side. **`--faces`** picks how faces are drawn:
`wire` (the default) is a content-free schematic of outlines; `textured` is the **CSG-solved textured
world**, as UnrealEd's 3D viewport draws it. (`actor diagram` renamed from `brush preview` in
2026-07-21; `actor diagram`/`stash diagram`/`prefab diagram` all renamed to `diagram` since.)

```
actor diagram [<names…> | --from-t3d <FILE…|->]
              [--layout quad|single|breakdown] [--view top|front|side|iso]
              [--faces wire|textured]
              [--brush-colors csg|legend] [--annotate SELECTORS]
              [--frame BRUSH[:IDX] | X0,Y0,Z0,X1,Y1,Z1] [--frame-tightness N]
              [--highlight POLY|NAME ...] [--focus BRUSH]
              [--show collision,light-range,sound-range]
              [--iso-angle 30] [--size 1024] [--locator-cells N | --no-locator-cells] [--grid-size N]
              [--json] [--out PATH]
```

- **Target set** — actor names, or `-` to read a newline name list from stdin (`actor find … | actor
  diagram -`), or **`--from-t3d <FILE…|->`** to render the actors in one-or-more T3D files (or a `-`
  stdin snippet: `brush build spiral | actor diagram --from-t3d -`). Multiple files concatenate in
  order; `-` is the sole value. `--from-t3d` is mutually exclusive with names. Giving no target set
  at all (no names, no `-`, no `--from-t3d`) is an error (exit 2); an empty `-` stdin stays a clean
  no-op (exit 0).
- **`--layout {quad,single,breakdown}`** (default `quad`) picks the pane layout. **`quad`** is the
  UED-style 2×2 grid (Top / Front / Iso / Side). **`single`** renders one `--view`. **`breakdown`** is
  described next.
- **`--layout breakdown`** renders a near-square **grid** of panes that walks the scene **actor by
  actor**. Pane 0 is the whole scene in CSG colour — a plain spatial **map** with **no labels** (no
  legend, no names, no on-face numbers); you identify each actor from its own captioned pane below. Each
  following pane is **one actor**: a **brush** is `--focus`ed and zoomed to its own AABB with all its
  faces numbered; a **point actor** is zoomed to a box around its Location with its marker/sprite drawn
  (no face numbers — a point has none). Every pane is captioned with the actor name. Panes follow the
  actor-set order (brushes and point actors intermixed) and are square cells laid out in
  `ceil(sqrt(N))` columns (near-square, slightly wider than tall). One view (uses `--view`); composes
  with `--annotate` (the per-brush number set), `--brush-colors`, `--highlight` (a highlighted poly
  re-lights in every pane), `--show`, `--size`. It sets its own focus and zoom per pane, so
  **`--focus`/`--frame` are ignored** under it. Brush + point-actor counts are reported on stderr;
  breakdown is a small-selection inspector (it warns past ~16 panes — a whole level makes an unusably
  large grid, and point actors add panes too, so subset first).
- **`--faces {wire,textured}`** picks how faces are drawn.
  - **`wire`** (default) draws outlines only — the schematic, CSG-coloured (added blue, subtracted gold,
    …). It needs no game content at all and works on `--from-t3d` from anywhere.
  - **`textured`** is the **CSG-solved textured world**, exactly what UnrealEd's 3D viewport shows: the
    set is run through the native CSG **solve** and only the surfaces that **survive** are drawn, each
    filled by **sampling its own texture** through the face's authored UV frame
    (`Origin`/`TextureU`/`TextureV`/`Pan`), with **no wireframe**. Because it is a real solve, an
    additive brush that is **not inside subtracted (empty) space is invisible** — visibility is spatial
    containment, not a per-brush rule — and a subtracted **room shows its interior** (its camera-facing
    near walls are dropped, so you see in) instead of a solid box. Texture **alignment, panning and
    tiling** stay correct **across CSG splits**, so a wall cut by a doorway keeps one continuous texture.
  - It shades each face by a fixed key light (no scene lighting), picks a mip level per face from how
    densely the texture lands on screen, and honours a **masked** texture's cut-out holes. A surviving
    surface with no `Texture` fills a neutral grey; that is normal, not an error.
  - **Movers** are excluded from the world solve (a mover carries no world `CsgOper`) and draw as a
    **magenta overlay** against the same depth buffer, so a mover behind a wall is hidden and one in
    front occludes. **Point actors** keep their sprite/marker overlay.
  - **`textured` reads the game's class hierarchy** (to tell a mover from a world brush), so unlike
    `wire` it needs **both a resolved project and the per-user games config**, plus **every texture a
    surviving surface references to be readable** — miss one and it exits 2 naming the ref (a bare
    `Texture=Name` is rejected; qualify it as `Package.Name`). A scene that references no texture needs
    no texture source. It also **rejects `--brush-colors`** (it samples real textures) — a clean exit
    2; use `wire` instead. Scaled, mirrored, and sheared brushes render — the UV frame follows the
    full transform, same as the geometry; only a **non-invertible (degenerate) scale** (a zero or
    sub-epsilon axis) is refused, exit 2 naming the brush.
  - A solve that leaves **no surface** (e.g. adds with nothing to carve empty space around them) is a
    clean exit 2 naming the cause; a set of only point actors and/or movers (no world brushes) draws its
    overlays over the dark background at exit 0. `textured` composes with every other option here — `--focus`,
    `--highlight` (its vivid outline is the only line art it keeps) and `--layout breakdown` included.
- **Brushes are coloured by CSG op** (UnrealEd's legend): added-solid **blue**, subtracted
  **gold/yellow**, semi-solid **pink**, non-solid **green**, mover **magenta**; front and
  obscured/back faces draw in the same shade (facing-blind). This says what each brush *does*.
- **`--brush-colors {csg,legend}`** picks the colour source for the `--faces wire` wireframe.
  `csg` (default) is the CSG-op colouring above. **`legend`** instead draws each brush in *its own
  per-actor tint* — every brush a distinct colour (you trade the CSG cue for telling same-op brushes
  apart at a glance). It has no meaning under `--faces textured`, which colours nothing from it, so
  passing it there is a clean exit 2.
- **Labels use a HYBRID per-actor TINT.** The CSG palette has only ~5 hues, so two brushes with the
  SAME CSG op share ONE wireframe colour; to tell them apart, each **actor** is assigned a distinct
  **tint** from a categorical palette (~10 hues, cycled). A brush's **on-face poly-index decal** (the
  painted digits and their 6/9 baseline underline) carries that tint; a point actor's **marker** is
  drawn in it — so a number shared across brushes (every brush has a face `1`) is disambiguated by its
  tint. **Actor names are not drawn on the diagram**; identify each actor from its locator cell
  reported on stderr (below).
- **Poly face indices are painted ON the face (on-face numbers).** Each face's index is a **number
  texture lying flat in the face's own 3-D plane** — it foreshortens with the surface under the
  projection, so it reads as decaled onto the geometry. It is placed at the **roomiest spot on the
  face** (the largest spot where it fits *inside* the face polygon — off to a side on a triangle/arch,
  not centred over a narrow point) and sized to **75% of the largest number that would fit there**.
  Sizing always assumes a **2-digit width** and centres the actual number in that slot, so a single
  digit (`5`) renders at the same scale as a two-digit one (`12`) rather than ballooning. Numbers
  **hang by gravity** on walls and slopes (strokes run straight up the surface) and align to the
  **world Y axis** on floors/ceilings/caps, with a short underline as a `6`/`9` cue. This is the only
  way poly faces are labelled — there is no leader-box mode.
- **Overlapping numbers: a tiny nudge, then a white outline.** Two faces can project close together on
  screen — including two faces of the **same brush** — so numbers can overlap. First, a **tiny
  reshuffle**: a number overlapping another (or a point-actor marker) may **shrink by at most 10%**
  and **move by at most 10% of its own diagonal**; it never makes a big jump or shrinks to a speck. A
  number with no overlap doesn't move. Second, wherever two numbers still overlap, a thin **white
  outline (1 screen pixel, constant width at any zoom)** is drawn just outside the strokes in the
  overlap, so you can trace each number apart. Numbering is **facing-blind**: front AND back faces get
  a number (the front/back distinction is carried by opacity, below, not by hiding back faces), and
  `--annotate`'s `poly` selectors still choose *whether* poly numbers draw at all (e.g. `none`,
  `poly:hi`). (Under `--layout breakdown` each brush is alone in its pane, so cross-brush overlap
  disappears and the outline only marks the occasional same-brush overlap.)
- **On-face numbers are graded translucent by depth.** A visible face is drawn at 56% opacity, and each
  face in front of it keeps 60% of that (near faces clear, buried faces faint), so the nearer faces'
  numbers stand out. A face counts as "in front" under the **self-or-solid** rule: a nearer front face
  that covers it dims it only when that occluder is a **solid** CSG op (added/semi-solid/mover) or
  belongs to the **same brush**. So a hollow room's near walls dim its own far walls, while a solid
  brush sitting **inside** a room is **not** dimmed by the room's walls; solid brushes still dim across
  brushes. A number **unreadable on screen** is omitted — a **view-dependent** verdict: a face too
  small, too edge-on, or too zoomed-out gets no number, and the same face is numbered once it's big
  enough (zoomed in, or in its `--layout breakdown` pane). There is no fallback for an omitted face.
  Under **`--faces textured`** the fills are opaque but the numbers are not hidden by them: a face you
  cannot see still shows its index, at 60% of a visible face's opacity, so a number can sit on a wall
  in front of the face it belongs to. Read indices off `--faces wire`, or pass `--annotate none` for a
  clean filled picture.
- **`--annotate`** takes a **comma-set of `poly` selectors** (the drawn numbers are their **union**).
  Bare **`poly`** means every face index; each colon **filter** narrows; multiple filters on one
  selector intersect; commas union. Tokens are case/whitespace-insensitive. **Actor names are never
  drawn** — locate a brush by its locator cell (printed on stderr, below).
  - `poly` filters: **`vis`** (retained as an inert alias of bare `poly` — see the note below),
    **`hi`** (highlighted faces only). (`highlighted` is accepted as a synonym for `hi`.)
  - Examples: `poly:vis` = every face (same as bare `poly`); `poly:hi` = highlighted faces only.
  - Whole-value keywords (stand alone): **`none`** = nothing; **`all`** = `poly`;
    **`highlighted`** = `poly:hi`.
  - **Default:** `none` — poly numbers are opt-in. Pass `--annotate all` (every face) or
    `--annotate poly:hi` (highlighted faces only) to draw them. (On-face numbering is facing-blind, so
    `poly:vis` — now an inert alias of bare `poly` — numbers every face once drawn; opacity, not
    presence, is the front/back cue. `vis` is kept only so pre-facing-blind specs still parse.)
  - An invalid token is a clean exit 2 naming it (e.g. `--annotate: unknown filter 'foo' for kind 'poly'`).
- **Point actors** render as their **DT_Sprite** billboard (footprint `DrawScale·USize × DrawScale·
  VSize`) or, for DT_Mesh/DT_None (or a sprite that does not decode), a small **marker** (a filled
  diamond in the actor's tint, with a white halo) at Location. A sprite that does not decode prints a
  stderr note **naming why** — `unknown-texture` (nothing of that name on the search path),
  `unqualified-ref` (write it as `Package.Name`), `unverified-format` (a real texture in a pixel
  layout uedcli cannot read yet), and so on. With **no texture search path configured**, the note says
  so instead of naming a case — run `project show` to see what is on the path. Its **name is not
  drawn**; find it by the locator cell reported on stderr.
- **`--frame TARGET`** frames a target to fill the view (frames only — never highlights), in one of two
  forms. A **selector** — a bare **`BRUSH`** name frames that actor's whole AABB, or **`BRUSH:IDX`**
  frames ONE poly (a multi-index / `:all` value is an error). OR an **explicit world AABB** — six
  comma-separated numbers **`X0,Y0,Z0,X1,Y1,Z1`**, framed **exactly** (+ a small margin). **`--frame-
  tightness N`** (default `0.8`, must be in `[0, 1]`) sets framing tightness toward a **selector**
  target only: `0` = whole-set frame, `1` = tightest (target + margin); no `--frame` ⇒ no-op. An
  explicit-AABB `--frame` is always framed exactly — `--frame-tightness` does NOT modulate it.
- **`--highlight POLY|NAME`** emphasises a poly or actor; repeatable, no effect on framing. A token
  **with a colon** is a poly selector `BRUSH:IDX` (set form `BRUSH:1,2` / `BRUSH:all` too) — those
  polys draw with a **bolder line** in their brush's vivid CSG hue. Under `--faces textured` a
  highlighted face keeps its texture and takes only that vivid outline. A token **without a colon** is an
  **actor name**: a brush actor highlights **all** its polys; a point actor gets **corner brackets**
  (a selection reticle) framing its sprite/marker. An unknown name / a selector on a non-brush → clean
  exit 2. Under a filled mode a highlight re-colours **what is visible** and never x-rays: a
  highlighted face that something in front of it hides shows nothing, and a **stderr note** names any
  selector that landed on nothing visible for any reason (hidden, culled, invisible, or off-frame) —
  under `--layout quad` that means no pane showed it.
- **`--focus BRUSH`** spotlights ONE brush: only it shows face indices (in its tint), and every OTHER
  brush recedes — for reading one brush's faces in a busy scene. Under `--faces wire` those brushes
  recede to a **faint (dimmed)** wireframe; under `--faces textured` their solved **fills** fade too, to
  a faint wash of their own colour. **`--focus` changes brightness only — never what is visible or what
  hides what**, so the picture stays physically honest either way: a crate inside a subtracted room stands in
  front of the room's far wall, a brush between the camera and the focused one still covers it, and a
  brush sealed inside a solid *added* brush stays hidden.
  **`--highlight` overrides `--focus`'s dimming**: a highlighted poly/actor draws at full strength and
  keeps its index even when its brush is not the focus. It does **not** override depth — a highlighted
  face something hides is still hidden (focus dims; highlight re-lights what is visible).
  An unknown name / a point actor → clean exit 2.
- **`--show SET`** is a **comma-set (union)** of range overlays for **POINT** actors (default: none).
  Members: **`collision`** — a faint light-red collision cylinder for every colliding point actor
  (`bCollideActors`): a circle in TOP, a `2·CollisionRadius × 2·CollisionHeight` rect in FRONT/SIDE, an
  8-sided wire cylinder in ISO (`CollisionHeight` is a HALF-height); **`light-range`** — a faint orange
  sphere of a light's reach (`25·(LightRadius+1)` UU); **`sound-range`** — a faint blue sphere of an
  AmbientSound's reach (`25·(SoundRadius+1)` UU). Brush actors (including movers) are excluded, so a
  brush diagram needs no class schema. An unknown member is a clean exit 2 naming it.
- **Locator cells are drawn on every diagram by default** — a **label gutter** with columns `A,B,C…`
  across the top and rows `1,2,3…` down both sides (no gridlines), so every region of the image has a
  text address like `D4` (a letter is always a column, a number always a row). It is **on by default**
  and orthogonal to `--annotate`, so `--annotate none` still carries the gutter. Each actor's cell is
  reported as a **legend on stderr**: a density header, then one line per actor — `Pillar  D4  (C3–E5)`
  (the centroid cell, plus the covered range in parens) under `single`/`breakdown`, or pane-qualified
  `Pillar  Top:D4 Front:B7 Side:C7 Iso:E5` under `quad`. An actor that draws no pixel (e.g. one hidden
  behind solid geometry under `--faces textured`) still gets a cell, flagged `(hidden)`. Two actors in
  the same cell each keep their own line. **The address is a region of the image/projection, never a
  world coordinate** — carry a cell back into a name set with `actor find`.
- **`--locator-cells N`** sets the density: `N` equal columns × `N` equal rows. Must be in `[1, 52]`
  (else a clean exit 2 naming the value). Without it (and without `--no-locator-cells`), the density
  is picked automatically, and how depends on the view: on an **ortho** view (`top`/`front`/`side`)
  cells are ANCHORED to the world gridline overlay — a locator boundary lands on an actual drawn
  line, picking the finest power-of-two multiple of the grid's own step that still keeps labels
  clear (cells are then not all equal — the first/last are partial, absorbing whatever the frame's
  edge doesn't land on exactly). On `iso` (no world gridline lattice to anchor to) the density falls
  back to the equal-division picker: the finest `N` whose cell is an independently-chosen
  power-of-two pixel span without its own column/row labels crowding each other. Either way a bigger
  `--size` auto-picks a finer, more useful density, never a fixed count regardless of render size.
  Under `--layout quad` each of the 4 panes resolves its OWN auto density independently (Top/Front/
  Side can each anchor to a different gridline step; Iso always uses the pixel-fit fallback), so the
  stderr legend/`--json` report ONE shared density only when every pane happens to agree, else a
  line/key per pane. Under `breakdown` the locator + legend ride pane 0 (the whole-scene pane) only.
  **`--no-locator-cells`** turns the whole
  feature off — gutter, stderr legend and the `--json` cell data together — and gives the geometry
  the wider drawable rect back. The two flags are mutually exclusive (a clean exit 2 naming both if
  given together).
- **Every orthographic pane** (`top`/`front`/`side`) **carries a world-space gridline overlay** —
  a ruler for scale and position, ported from UnrealEd's own 2D-viewport grid — **whether or not
  `--grid-size` is given**; the flag only overrides the spacing it picks automatically. **`iso` never
  gets one** (its screen axes mix world axes, so a world lattice would not be a ruler there); giving
  `--grid-size` together with `--view iso` under `single`/`breakdown` is a clean exit 2 (`quad` always
  renders the ortho panes regardless of `--view`, so it is unaffected). Two tiers: a **minor** line
  every step and a **major** line every 8th, both drawn as neutral greys never confused with the CSG
  palette. **`--grid-size N`** sets the minor spacing in world units and must be a **power of two >= 1**
  (else a clean exit 2 naming the value); without it, each pane picks its own step — the largest power
  of two `<= span/16` of that pane's own framed world extent, landing 16-32 minor divisions across the
  pane at any zoom, so the grid reads as a ruler rather than a lone crosshair. A spacing too fine for
  the pane **escalates** to a coarser one instead of erroring (matching the editor; the auto step never
  needs this — it already clears the density threshold); one too coarse to show any line at all draws
  nothing (exit 0) — the stderr report (below) always names the step, so neither substitution is
  silent. **Nothing about the grid is drawn into the image beyond the lattice itself** — no caption, no
  legend; every gridded pane instead gets **one line printed to stderr**: the framed world extent in
  the pane's own two axes, plus `set` (the step asked for — explicit `--grid-size` or the auto default)
  and `visible` (`set` after escalation, what is actually on screen — equal to `set` on every default
  render, differing only when an explicit `--grid-size` escalated), e.g. `X -1024..2048  Y -512..1536
  grid set 32, visible 64`. Pane-qualified under `quad`/`breakdown` (`Top: X -1024..2048  Y -512..1536
  grid set 32, visible 64`), unqualified under `single`; printed unconditionally, independent of
  `--locator-cells`/`--json`. (Major-tier spacing is deliberately not reported — the tier test is on the
  pre-escalation step, so it is pinned to `8 * set` world units, not `8 * visible`, and a caption
  printing the latter reads wrong once escalated.) Under `quad`/`breakdown`, each pane frames (and so
  may escalate) independently, so panes can report different steps. The grid is a backdrop: it never
  covers geometry, is never dimmed by `--focus`, and is unaffected by `--faces`.
- **`--json`** prints a JSON object to stdout **instead of** the bare image path. With locator cells on
  (the default), it is the machine form of the legend:
  `{image, locator:{cols,rows}, actors:{<name>:{panes:{<Pane>:{cell,span}}, hidden}}}`, pane-keyed for
  every layout (a `single` render has one pane keyed by its `--view`). With `--no-locator-cells`, the
  addressing drops out but `hidden` stays a real answer: `{image, actors:{<name>:{hidden}}}` — no
  `locator` key, no `panes`/`cell`/`span`. The stderr legend is unchanged (and likewise absent with
  `--no-locator-cells`).
- `--out PATH` is the host image path. **A diagram is always a PNG** (written via **Pillow**, the
  LLM-viewable form — no flag and no other way to get raw PPM out). Whatever extension you pass is
  **replaced** by `.png`, so `--out shot.jpg` writes `shot.png` and `--out shot` writes `shot.png`.
  `--out` is **optional**: with no `--out`, a unique temp file is minted (`uedcli-preview-*.png`).
  Either way, unless `--json` is given, the **absolute path actually written is printed to stdout**.

See also: [`actor find`](find.md), [`stash diagram`/`prefab diagram`](../stash.md).
