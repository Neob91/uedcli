# actor find

`actor find [filters…] [--json] [--exclude] [-]` — print names of matching actors, one per line,
for piping; with no filters, prints **every** actor; a trailing `-` restricts the search to a
piped name-set (boolean queries — see below).

**Filters** (repeat any flag; within a flag the patterns OR, across flags they AND):
- `--exact-class C` — match the class EXACTLY (bare or `Package.Name`, case-insensitive). Does NOT
  include subclasses — `--exact-class Light` skips `Spotlight`. (This replaced a plain `--class`,
  which was ambiguous about whether subclasses counted; bare `--class` is not a flag at all.)
- `--subclass-of C` — match `C` OR any class that descends from it (`--subclass-of Engine.Light`
  also matches `Spotlight`, `TriggerLight`, …). Descendant-aware; needs the class schema (the game
  `.u` install). ORs with `--exact-class` within the class dimension.
- `--group G` — membership in the T3D `Group=` prop (comma-joined groups are split).
- `--name GLOB` — fnmatch glob over the actor Name (case-insensitive, whole-name anchored).
- `--prop KEY[.PATH]=VALUE` — match the **EFFECTIVE** value (stored, else the class default decoded
  from the game `.u`, else zero) with a **type-aware** compare (`True`≡`1`, `4`≡`4.0`, enum
  name≡ordinal). Dot-paths reach into arrays/structs (`Location.X=512`). An actor whose class
  doesn't declare KEY simply doesn't match; a KEY *no* considered class declares errors (exit 2).
  Needs the class schema (the game `.u` install).
- `--kind point|brush` — the brush-vs-point split. `brush` = actors carrying a PolyList (CSG
  brushes, builders, movers — the ones `brush`/`poly`/`vertex` verbs accept); `point` =
  location-only actors (Light, LevelInfo, nav points, **and mesh decorations** — a mesh deco has
  visible geometry but is still a point actor).
- `--within-bbox X0,Y0,Z0,X1,Y1,Z1` — match actors whose **world bounding box is fully inside** the
  given axis-aligned box (two opposite corners in any order, unreal units — same space as `--at` —
  **edge-inclusive**). Honours each actor's full transform (a scaled/rotated brush's TRUE world box
  is tested); a point actor is its `Location` point. **Single-valued** (not repeatable). Matches
  **every** contained actor (lights, nav points, decorations too), so add `--kind brush` for geometry
  only. Being full **containment**, a brush straddling the box edge (a room shell poking past a tight
  box) is **not** matched — size the box to enclose the whole feature, or use `--overlapping-bbox`.
- `--overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — the looser companion: match actors whose **world bounding
  box overlaps** the given box (same arguments, transform-honoured, **edge-inclusive**). Contained vs
  straddling: `--within-bbox` drops a room shell / wall poking past the box edge, `--overlapping-bbox`
  grabs it — better for "everything in this area." **Single-valued**; ANDs with the other filters
  (passing both degenerates to `--within-bbox`, since contained ⊆ overlapping). Caveat: it tests the
  **world AABB**, so a diagonal or L-shaped brush can match on its bounding box with no solid geometry
  actually inside the box.
- `--folder PATTERN` / `--no-folder` — see [`actor folder`](folder.md).
- `--label GLOB` / `--no-label` — see [`actor label`](label.md).
- `--json` — emit the names as a JSON array.

```bash
uedcli actor find --group cells | uedcli actor delete -
uedcli actor find --folder castle.tower.** | uedcli actor bbox -   # enclosing box of a subtree
uedcli actor find --within-bbox -512,0,-256,512,768,256 --kind brush | uedcli actor diagram -   # render a region
```

**Discover brushes by CSG type** (additive vs subtractive) uses the existing `--prop` — there is no
`brush find`/`brush list` verb and no `--csg` filter:

```bash
uedcli actor find --kind brush --prop CsgOper=CSG_Subtract   # every carve
uedcli actor find --kind brush --prop CsgOper=CSG_Add         # every additive
```

`CsgOper` is a declared enum, matched type-aware. Keep `--kind brush`: an unset `CsgOper` reads the
class default `CSG_Active`, not `CSG_Add` — only the transient builder brush omits it, so every placed
world brush carries an explicit `CSG_Add`/`CSG_Subtract`; and `--prop CsgOper=` over a set with no
brush exits 2. To author CSG sets use [`brush intersect`/`brush deintersect`](../brush/intersect.md);
to change CSG precedence use [`actor order`](order.md).

**Boolean queries — `find <filters> -`:** with a trailing `-`, `find` reads a newline actor-name list
from stdin and searches ONLY that set; the filters are the predicate. `--exclude` keeps the
non-matches instead. This composes into full boolean logic:

    actor find --group A | actor find --group B -            # A AND B
    actor find --group A | actor find --group B --exclude -  # A but NOT B
    { actor find --group A; actor find --group B; } | sort -u | actor find -   # A OR B (re-normalized)

Unknown piped names are a hard error (exit 2). `find -` with no filters echoes the piped set (a strict
validator).

See also: [`actor show`](show.md), [`actor bbox`](bbox.md), [`actor folder`](folder.md),
[`actor label`](label.md).
