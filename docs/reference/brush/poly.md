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

**`brush poly scale --by FU,FV`** resizes the texture. It names what you **see**: `--by 2,2` makes
the texture look twice as big, `--by 0.5,1` halves its width only. U and V are independent, and both
factors must be positive. The face's own centre again keeps its texture coordinate, so the texture
grows in place rather than sliding off.

⚠ Ordering rules:

- Pan comes after align, never before. Every `brush poly align` mode stamps `Pan` on each face
  it touches, so a dialled-in pan applied first is discarded.
- Scale comes before `align --ring`, never after. A ring wrap computes each face's phase offset
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

**`brush poly align (--wall | --floor | --ring) [--fresh-frame] [--fit-perimeter] (targets…|-)`** makes
one texture flow **continuously** across a set of faces instead of restarting the pattern at every
brush edge (offline texture-vector math — no editor involved).
Exactly one geometry mode is required. The face set is `BRUSH:SELECTOR` positionals (or a bare brush
Name = all its polys) **or** `-` reading the set from stdin (bare names, or the `BRUSH:idx` lines
`poly find` prints); empty stdin is a clean no-op. The **first face is the seam/seed**. Touched brush
names → stdout, a summary → stderr.

- **`--wall`** / **`--floor`** — a set of strictly **coplanar** faces gets ONE shared world texture
  frame (a seam vertex maps to the same coordinate from either face). `--wall` requires the faces
  **vertical** (normal ≈ ±X/±Y), `--floor` requires them **horizontal** (±Z) — an orientation guard.
- **`--ring`** — wrap a texture around a **cylinder's side faces**: U advances by each facet's true
  chord (`2·r·sin(π/N)`) around the ring, V runs along the axis. Exclude the two caps.
- **Frame source:** default **adopt-seed** (continue the seed face's already-dialled-in
  `TextureU/V` + `Pan`); `--fresh-frame` synthesizes a canonical frame from the face normal instead.
  ⚠ That canonical frame is **uedcli's own convention, not a reproduction of UnrealEd's
  "align to floor / wall direction"** — measured against the editor 2026-07-26, the two pick
  different in-plane axis directions (a mirror, a 180° turn, or on a non-axis-aligned wall a full 90°)
  and pin the texture's phase to a different point (uedcli to the seed face's centre, the editor to a
  world axis). A face aligned here and in the editor's GUI will not look the same; pick one tool per
  surface.
- **`--fit-perimeter`** (`--ring` only) snaps the scale so an integer number of texels fits the
  perimeter (an exact meet at the closing seam).

```bash
uedcli brush poly find Tower --item Side | uedcli brush poly align --ring -
uedcli actor find --folder castle.hall.northwall | uedcli brush poly align --wall -
```

⚠ The per-face verbs print faces, not actor names. `brush poly set` / `pan` / `rotate` / `scale`
print `BRUSH:idx` selectors — one per touched face — because a bare brush name means all of
that brush's faces, so printing one would hand the next verb a wider set than it edited. The names
are canonical and `all` is expanded, so `brush poly pan wall:all …` prints `WALL:0 … WALL:5`,
ready to feed the next verb's `-`.

⚠ `brush poly align` has not been converted and still prints brush names, so its output cannot be
piped into a per-face verb. It does not quietly widen the set — the per-face verbs take
`BRUSH:SELECTOR` only (see below), so a bare name is rejected and
`brush poly align … | brush poly rotate -` exits 2 with
`surface selector must be BRUSH:SELECTOR, got 'WALL'`. Re-select the faces with `brush poly find`
between the two verbs.

See also: [`brush vertex`](vertex.md), [`brush measure relation`](measure.md), [`actor diagram`](../actor/diagram.md), [Textures & surfaces](../../leveldesign/general/textures-and-surfaces.md) (the level-design craft of texture alignment).
