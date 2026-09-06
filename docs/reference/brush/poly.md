# brush poly

list / find / set / pan / rotate / scale / move / align

**`brush poly list`** is the precise surface reference. Columns: `idx | facing (flat/wall/ramp
orientation) | texture | flags (decoded to NAMES) | pan | centroid | area | nverts`. Flags decode to
names (`masked`/`translucent`/`fakebackdrop`/`unlit`/…, plus a hex tail for unknown bits). `--json`
emits `{actor, polys:[…]}`, each poly carrying the visible unit `normal` (`[nx,ny,nz]`),
`orientation` (flat/wall/ramp), and `role` (floor/ceiling/null).

**`brush poly find`** is a stateless producer over ONE OR MORE brushes: it prints their matching
faces as `BRUSH:idx` selectors, one per line (a match count → stderr). It takes brush Name(s), or `-`
to read the set from stdin (bare names, or the `BRUSH:idx` lines a prior find/per-face verb prints —
the `:idx` is stripped to the brush); empty stdin is a clean no-op. A non-brush actor is warned and
skipped; an unknown name is an error. Filters AND together:
- `--item NAME` — the builder ItemName (`Side`/`Cap`/`Step`/…, case-insensitive).
- `--facing SPEC` — a predicate on the face's **visible** unit normal `(nx,ny,nz)`, each in `[-1,1]`.
  `;` = AND across terms, `,` = OR within one axis, `..` = an inclusive range. Presets: `flat`/`wall`/
  `ramp` (orientation) and `floor`/`ceiling` (up/down role). Or `AXIS:SPEC` on `nx`/`ny`/`nz`, e.g.
  `'floor'`, `'wall;ny:0.7..1'`, `'nz:-1,1'` (flat), `'nx:1'`. Polarity is resolved for **subtract**
  brushes, so `floor` returns the walkable surface even inside a carved room (where the geometric
  outward normal points the other way).
- `--texture REF` — the texture ref (exact or last dot-component, case-insensitive).
- `--json` — an array of `{brush,poly,item,normal,orientation,role,texture}`.

Its output feeds `brush poly set|pan|rotate|scale -` and `brush poly align -` — and those four
per-face verbs print the same `BRUSH:idx` form, so they chain into each other directly.

**`brush poly move --by DX,DY,DZ`** is the whole-face counterpart: it translates every vertex of each
selected face by a world delta, model-side and rotation-aware like `brush vertex move`. It takes the
same `BRUSH:SELECTOR` targets as the poly texture verbs below (`-` for stdin). Because a brush stores
welded corners, a corner shared with an unselected face moves too and that neighbour deforms — the
solid stays watertight. Most non-axis-aligned moves push a neighbour off its plane and are rejected
(exit 2 naming the face); moving a face along its own normal is the safe case.

Two different jobs, two verbs. **`brush poly set`** assigns a face's stored **attributes** — which
texture is on it, which surface flags it carries. **`brush poly pan` / `rotate` / `scale`** transform
the face's **texture frame** — where the texture sits, which way up it runs, how big it is.
**`brush poly align`** (next section) derives a whole frame from geometry.

**Targets, for all four.** `BRUSH:SELECTOR` positionals (SELECTOR = `all` or comma-separated poly
indices; repeatable, e.g. `Wall1:3,5 Wall2:all`), **or `-`** to read `BRUSH:idx` lines from stdin
(empty stdin = clean no-op, exit 0; `-` is the sole source and cannot be mixed with positionals).
A face named twice is edited **once**. Unlike `align`, which *also* accepts a bare brush name meaning
all its faces, **`set`/`pan`/`rotate`/`scale` do not** — say `Tower:all`. A whole brush is a
meaningful unit for an alignment mode ("wrap this cylinder"), but a whole-brush pan or rotate is a
blanket nudge of every face including ones you never looked at, and the relative forms compound it
silently, so "yes, all of them" has to be typed out.

**`brush poly set`** takes `--texture REF` (qualified `Package[.Group].Name`) and
`--add-flag`/`--remove-flag` (flag by **name**, case-insensitive — `Unlit`, `unlit`, `MASKED` all
work; repeatable). At least one of the three is required.

```bash
uedcli brush poly find WALL --facing floor | uedcli brush poly set - --texture DeusExDeco.Wood
```

**`brush poly pan (--to | --by) U,V`** shifts the texture across the face by whole **texels**.
Exactly one of `--to` (absolute) / `--by` (relative to the current pan, which counts as `0,0` when
unset) is required; both take negatives. A pan of `0,0` **is** the unpanned state, so `--to 0,0`
clears the pan and `brush poly list` then shows `-` in the `pan` column — there is no separate
"explicitly zero" pan.

**`brush poly rotate --by UU`** turns the texture within the face's own plane. `UU` is in **unreal
rotation units** — 16384 = 90°, 65536 = a full turn — the same units as `brush build --rotate` and
`mover key rotate`; negative turns the other way (`--by -16384` ≡ `--by 49152`). The face's own
centre keeps its texture coordinate, so the texture **spins in place** instead of sliding. There is
**no `--to`**: an absolute angle could only be measured against an internal canonical frame whose
in-plane direction you cannot see or predict, so it would mean something different on every face
normal. A *known* orientation is `brush poly align`'s job.

**`brush poly scale (--by FU,FV | --to U,V)`** resizes the texture. **`--by`** names what you
**see**: `--by 2,2` makes the texture look twice as big, `--by 0.5,1` halves its width only — pure
math, no project needed. **`--to U,V`** sets the **absolute** density in **world units per tile**:
`--to 128,128` means each face's own bound texture repeats every 128 uu each way (a smaller `U,V`
looks like a bigger texture — fewer, larger tiles). It needs a project on the package path to read
that texture's pixel size; a face with no bound texture, or an unresolvable ref, exits 2 naming
every offender before writing anything. Either way, U and V are independent and must be positive,
and the face's own centre keeps its texture coordinate, so the texture grows in place rather than
sliding off.

⚠ Ordering rules:

- Pan comes after align, never before. Every `brush poly align` mode stamps `Pan` on each face
  it touches, so a dialled-in pan applied first is discarded.
- Scale comes before `align run`, never after. A ring wrap computes each face's phase offset
  for the density it saw; rescaling afterwards leaves those offsets describing the old size and the
  seams no longer meet.
- Panning a subset of an aligned run breaks its continuity, since those faces shift relative to
  their neighbours while the rest stay put. Easy to do by accident — the natural idiom is
  `brush poly find … | brush poly pan -`, and `find` filters. Pan the whole run or none of it.
- `rotate` and `scale` give no continuity guarantee: each face pivots or grows about its own centre,
  so applying either across an aligned set breaks the seams `align` matched — and a shared wall/floor
  grid. They are for a one-off face (a sign, a monitor, a soffit). The run-aware turn is a flag on the
  alignment itself, not this verb.

`rotate` turns the texture the way you see it turn: the direction follows the face's visible surface
normal, so the same `--by 16384` looks the same whether you stand outside an additive pillar or
inside a subtractive room — uedcli flips the sign on a subtract. So `rotate` requires the brush's
`CsgOper` to be `CSG_Add` or `CSG_Subtract` (an absent one counts as `CSG_Add`) and exits 2 naming
any other value — `CSG_Intersect`, `CSG_Deintersect`, `CSG_Active` or anything unrecognised — because
a brush with no inside and outside gives the turn no direction to follow.

⚠ One case is still backwards: a **mirrored** brush — one whose scale has an **odd** number of
negative components, e.g. `MainScale=(-1,1,1)` — has its faces' winding reversed as the engine draws
them, so the visible normal is opposite the one uedcli computes and the turn inverts again. Negate
the angle there. An **even** number of negative components (`(-1,-1,1)`) is a 180° rotation, not a
mirror, and is **not** affected. (A geometric argument from the sign of the scale matrix's
determinant — uedcli's own frame math ignores scale entirely — not checked against the running editor.)

**Identifying a surface to edit:** `brush poly list <brush>` for the exact index/facing/texture,
then `actor diagram <brush> --highlight <brush>:N` (below) to see it emphasised (or
`--frame <brush>:N` to frame it).

### Continuous texture alignment (`brush poly align`)

**`brush poly align <mode> (targets…|-)`**, with `<mode>` one of **`wall`**, **`floor`**, **`run`** or
**`one-tile`**, sets each face's texture frame (offline texture-vector math — `wall`/`floor`/`run`
flow continuously across a set, `one-tile` fits each face independently; `wall`/`floor` reproduce
the editor's projection modes, `run`/`one-tile` are uedcli's own). The mode is a **subcommand**, so
`brush poly align run -h` lists exactly the flags that apply. The face set is `BRUSH:SELECTOR`
positionals (or a bare brush Name = all its polys) **or** `-` reading the set from stdin (bare names,
or the `BRUSH:idx` lines `poly find` prints); empty stdin is a clean no-op. Every mode zeroes `Pan`.
The touched faces → stdout as `BRUSH:idx` selectors, a summary → stderr.

- **`wall`** / **`floor`** — each face gets a **world-space** frame that reproduces UnrealEd's
  `POLY TEXALIGN` `WALLX`/`WALLY`/`FLOOR` (measured 2026-07-26): the texture anchored where the face's
  plane crosses a world axis, its U/V the other two world axes projected into the face. `floor`
  projects down Z; `wall` projects down whichever of X/Y the face faces more. Because the anchor is a
  **world axis, not the face**, faces on the same plane — or different planes at the same height —
  share one continuous grid, and the result does not depend on which faces were selected together or
  in what order. A face too near edge-on to its projection axis (`|N·axis| ≤ 0.05`) is a hard error
  naming every offender (`brush poly find --facing` filters upstream). A tilted face carries the
  planar-projection stretch (`|TextureU| = |proj| ≤ 1`); a face square to its axis is unit.
  ⚠ Two coplanar faces pointing **opposite** ways get an identical frame, so the texture reads
  **mirrored** on the back one — this is the editor's own polarity-blind behaviour, not a bug.
  ⚠ **Destructive on imported content:** real maps carry deliberate texel scales and pans; `wall`/
  `floor` replace them with the projection's density and zero the pan. Re-scale afterwards with
  `brush poly scale` if you need a specific density.
- **`run`** — lay one texture **continuously along a connected run** of faces: U follows the run, V
  across it, the phase carried across every seam. It wraps a cylinder (U advances by each facet's
  chord `2·r·sin(π/N)`, V along the axis), walks a wall run, or follows a flat/curved **bend**.
  Coplanar sets are allowed (a curved track bed). `run` **derives its own walk order** from the
  geometry, so the order faces are passed in has no bearing on the result — and spans any number of
  brushes (a straight corridor brush run into a corner brush walks as one continuous run). It must be
  one un-forking strip: a set that **branches** (a face with 3+ neighbours — a cylinder's cap touches
  every side) or is **disconnected** exits 2 naming the faces, with the hint to exclude caps via
  `brush poly find <brush> --item Side`. V runs **down** (a UE1 texture's `V=0`
  row is its top). On a subtractive brush's inner wall U reads mirrored (the same polarity-blindness
  as `wall`/`floor`), so a run and the walls around it stay consistent.
- **`--turn UU`** (`run` only) rotates the texture uniformly in each face's own run frame, in unreal
  rotation units (16384 = 90°). Any angle is allowed. A **cylinder** run stays exact at every angle;
  a **flat bend** shears at its seams (one axis at a quarter turn, both otherwise) — `run` reports the
  worst seam shear to stderr so you can mitre a bad corner or accept it.
- **`--fit-perimeter`** (`run` only) snaps the scale so a whole number of **tiles** exactly closes
  the loop — it needs a **closed** run, a **quarter** `--turn`, and every face bound to the **same**
  texture (else exit 2 naming why), and a project on the package path to read that texture's pixel
  size. Default leaves the seam.
- **`one-tile`** — fit exactly **one texture tile** to each face, independently: no shared frame, no
  continuity, and no orientation guard (any face works — the fit axis is always the world axis the
  face faces most over all three, so it's never edge-on). It stretches non-uniformly to fill the
  face's own extent — the point, for a sign or a monitor a letterboxed fit would be wrong. Needs a
  project on the package path: every targeted face's bound texture must resolve, or exit 2 naming
  every offending face/ref before writing anything.

```bash
uedcli brush poly find Tower --item Side | uedcli brush poly align run -
uedcli actor find --folder castle.hall.northwall | uedcli brush poly align wall -
```

⚠ The per-face verbs print faces, not actor names. `brush poly set` / `pan` / `rotate` / `scale` /
`align` print `BRUSH:idx` selectors — one per touched face — because a bare brush name means all of
that brush's faces, so printing one would hand the next verb a wider set than it edited. The names
are canonical and `all` is expanded, so `brush poly pan wall:all …` prints `WALL:0 … WALL:5`, ready
to feed the next verb's `-`.

See also: [`brush vertex`](vertex.md), [`brush measure relation`](measure.md), [`actor diagram`](../actor/diagram.md), [Textures & surfaces](../../leveldesign/general/textures-and-surfaces.md) (the level-design craft of texture alignment).
