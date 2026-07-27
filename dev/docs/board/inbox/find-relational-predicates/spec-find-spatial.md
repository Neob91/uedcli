# `find` spatial predicates — `--near`, `--within-bbox`, `--overlapping`

**Status: PARTIALLY BUILT (2026-07-24).** `--within-bbox` (full containment, §7.2 resolved to
containment-only) is **BUILT + tested** — `decisions.md` 2026-07-24 21:44 UTC, `tests/test_find_spatial.py`
(fold this filter's prose into `usage.md`/`architecture.md` is DONE). The **`--overlapping-bbox`** region-grab
variant is a NEW `board/to-spec/` item. **STILL PARKED:** `--near` (§2/§3), `--overlapping <actor>` (§2/§3), and
`--within-brush` (§7.6, still being designed); the remaining §7 sub-choices await Andrzej's direction.
The AABB filters (§2–§6) are review-clean.
Ephemeral — fold into `usage.md` + `architecture.md` if/when built. Revised 2026-07-24 after two cold
reviews (the `parse_coord` reuse, the `@Actor` resolver, and the Decimal/float distance were all wrong
in the first draft; fixed below). **Code refs symbol-anchored** (lines drift).
**Decisions ledger:** append on confirmation of the §7 sub-choices.
**Sibling** of `spec.md`; **relational** is a deferred board item. Composes
with the composable-`find` boolean model — a spatial filter is just another ATOM.

---

## 1. Motivation & the geometry it reuses

No way to select actors by WHERE they are — "near this torch," "inside this room's box," "overlapping
this wall." All cheap on existing machinery: **`writes.actor_bounds(actor)`** returns an actor's
axis-aligned world `(lo, hi)` as **`Decimal` tuples**, honoring the FULL transform
(`Location + PostScale·R·MainScale·(v − PrePivot)`; a **non-brush actor → a zero-size box at its
Location**). So spatial filters are AABB tests over `actor_bounds` — no new geometry, model-side, offline.

**In scope (v1):** three filters, AABB-precision. **Out of scope:** precise poly/hull overlap (a later
`--precise` toggle, §7), swept/volume queries, pathfinding distance.

## 2. The three filters

| Filter | Argument | Matches when… |
|--------|----------|---------------|
| **`--near POINT RADIUS`** | `POINT` = `X,Y,Z` **or** `@Actor`; `RADIUS` = scalar uu | the actor's AABB is within `RADIUS` of the point — nearest-point (§3) |
| **`--within-bbox X0,Y0,Z0,X1,Y1,Z1`** | a world AABB (two opposite corners; min/max normalized) | the actor's AABB is **fully contained** in the box |
| **`--overlapping ACTOR`** | a **bare actor name** (NOT `@Actor` — the target is always an actor, so `@Wall` and `Wall` would mean the same; bare name only) | the actor's AABB **intersects** the target actor's AABB; the **target itself is excluded** |

- **Coords/radius are unreal units (uu)** — the same space as `--at`/`--by`. Negative coords are fine
  (see §5 on `_CoordArgumentParser`).
- **`@Actor` (in `--near`) needs a NEW trunk-side resolver — do NOT reuse `preview`'s.** The preview
  `@` handling is baked into `preview_shots.parse_shot` and its point callback `actor_aim_point`
  (`preview_native.py`) returns a FLOAT center and raises the preview-specific `NativePreviewError` —
  wrong module, wrong type, and center-only. Instead the find handler resolves `@Name` with
  **`query.resolve_actor_name` (strict — unknown → exit 2 naming it, like `actor bbox`)** then takes
  **`writes.actor_bounds`**; for `--near`'s point arg it uses the box's **Decimal midpoint**.
- **Point actors / mesh decorations:** every non-brush actor is a **zero-size box at Location** —
  including mesh decorations with real visible extent (`actor_bounds` does not measure mesh geometry).
  A doc caveat, not a bug: containment/overlap treat such actors as their Location point.

## 3. Semantics (exact — all-Decimal, no float)

- **`--near` — squared-distance test, no `sqrt`.** Per axis the nearest point of the AABB to the query
  point is `clamp(point_i, lo_i, hi_i)`; the match is `Σ_i (point_i − clamp_i)² ≤ RADIUS²`, computed
  **entirely in `Decimal`** (`actor_bounds` is Decimal; parse the radius as Decimal; midpoints stay
  Decimal). This avoids `sqrt` and the `Decimal + float → TypeError` trap the first draft's Euclidean
  form invited. *(Sub-choice §7.1: nearest-point (recommended) vs bounds-CENTER distance.)*
- **`RADIUS` validation:** parsed as `Decimal`; a **negative radius → clean exit 2** naming the value;
  `0` is allowed (exact-touch, mirroring `preview_shots`'s `radius<=0` guard but permitting 0 here).
- **`--within-bbox` — full containment, edge inclusive:** `lo_i ≥ box.lo_i AND hi_i ≤ box.hi_i` per
  axis (an actor whose face sits exactly on the box edge IS contained; a straddling actor is not). Box
  corners are min/max-normalized so any two opposite corners work; a degenerate zero-volume box is
  legal (contains only zero-size actors exactly on it). *(Sub-choice §7.2: containment-only vs also
  INTERSECTS.)*
- **`--overlapping` — AABB intersection, edge inclusive, target excluded:** per-axis
  `a.lo_i ≤ b.hi_i AND a.hi_i ≥ b.lo_i` (two boxes sharing a face exactly DO overlap); the target
  actor is removed from the result. AABB can FALSE-POSITIVE on two angled/L brushes whose boxes overlap
  but whose solids don't — acceptable for a "what's around this" query; `--precise` is the §7 follow-up.
- **Self-match asymmetry (stated so it doesn't read as a bug):** `--overlapping A` excludes A, but
  `--near @A R` and a `--within-bbox` derived from A's box self-INCLUDE A — because those take a
  *point/box*, not an *actor identity*. Filter A out with the composable-`find` model if unwanted.
- **Transform honored for free** via `actor_bounds`: a scaled/rotated brush's TRUE world box is tested.

## 4. Composition

- **Different filters AND** (unchanged): `find --near @Torch01 256 --class-exact Light` = lights near
  the torch.
- **Spatial filters are single-valued (NOT repeatable) in v1** (multi-token args read badly repeated).
  Same-filter OR and NOT go through composable-`find`: `{ find --near @A 128; find --near @B 128; } |
  sort -u | find -` (union), `find --overlapping Wall --exclude -` over a universe (NOT). *(Sub-choice
  §7.3.)* Because spatial is just an atom, `find --within-bbox … | find --prop 'Health>50' -` composes
  this spec with its sibling.

## 5. Module shape / touchpoints

- **`uedcli/cli.py`** — three new `find` flags, each with a real `help=`:
  - `--near`: **`nargs=2, type=str, metavar=("POINT","RADIUS")`** — a single `type=` cannot serve a
    point-or-`@Actor` first token and a scalar-radius second, so both arrive as strings and the handler
    parses them (point via `parse_coord` OR `@`-resolve; radius via `Decimal`). (`parse_coord`,
    `cli.py`, requires exactly 3 comma-separated numbers and rejects `@` and scalars — it fits ONLY the
    literal-point sub-token.)
  - `--within-bbox`: a **NEW `parse_bbox6`** `type=` — parse 6 comma-separated numbers → normalized
    `(lo, hi)` Decimal corners (3-number `parse_coord` can't do this).
  - `--overlapping`: `type=str` (a bare actor name).
  - Negative coordinates need no `nargs`/`=` gymnastics: subparsers inherit `_CoordArgumentParser`
    whose `_parse_optional` matches `_COORD_TOKEN` and passes `-128,0,0` as a VALUE. The bare `-` stdin
    token (composable-`find`) does not match `_COORD_TOKEN`, so no collision.
- **`uedcli/dispatch.py`** — the spatial predicates live in the **`find` handler, AFTER `list_actors`**
  (NOT in `list_actors`), mirroring the deliberate `--prop` placement (`list_actors` stays geometry-free
  / dependency-light; the handler already imports `writes`). The handler: resolves `@Actor` (strict) +
  literal points, validates the radius, builds each AABB predicate over `writes.actor_bounds(a)`, and
  filters the `names` list (AND with the other filters, alongside `--prop`, before the print).
- **`uedcli/writes.py`** — small AABB helpers beside `actor_bounds`: `aabb_within(inner, outer)`,
  `aabb_intersects(a, b)`, `point_aabb_sqdist(point, lo, hi)` — all `Decimal`.

No model/trunk change; a read-path/query feature over offline world bounds.

## 6. Test strategy (host-native `bin/test`)

1. **`--near` nearest-point (Decimal):** a big brush whose CENTER is > R from the point but whose EDGE
   is ≤ R MATCHES (pins nearest-point over center-distance); fractional coords + radius (Decimal, no
   float leak); a **literal `X,Y,Z`** point AND an `@Actor` point; a point actor at exactly R (boundary).
2. **`--near` radius guard:** a negative radius → exit 2 naming it; radius `0` = exact-touch only.
3. **`--within-bbox` containment:** fully-inside matches; straddling does not; an actor with a face
   EXACTLY on the edge IS contained (edge-inclusive); corner-order independence; degenerate zero-box.
4. **`--overlapping`:** intersecting AABBs match; two boxes sharing a face exactly overlap
   (edge-inclusive); the target is EXCLUDED from its own result; disjoint doesn't; the L-brush AABB
   false-positive is documented, not a failing test.
5. **Transform honored:** a `MainScale`/`Rotation` brush's TRUE world box drives the match (authored
   verts would fail, scaled box passes).
6. **Parse/errors:** unknown `@Name` → exit 2; a non-numeric radius or malformed point/bbox token →
   clean exit 2 (never a traceback); a negative-coord token parses as a value (`_CoordArgumentParser`).
7. **Composition:** `--near @T 256 --class-exact Light` ANDs; a spatial + `--prop` pipe composes.

Use artificial coordinates (`512,-256,64`, radius `1337`).

## 7. Open sub-choices for Andrzej

1. **`--near` metric** — nearest-point-of-AABB (recommended) vs bounds-center distance.
2. **`--within-bbox` mode** — containment-only v1 (recommended) vs also INTERSECTS.
3. **Repeatable spatial filters?** single-valued v1 (recommended; OR via the `find` union).
4. **AABB now, `--precise` later?** ship AABB-only (recommended); add convex-hull `--precise` only if
   AABB proves too coarse.
5. **Scope down to `--near` first?** (reviewer suggestion) — the shared AABB core is cheap, but each
   filter has a DISTINCT parser/`@Actor` story (the error-prone part), so `--near` (2-token, `@`-or-coord,
   nearest-point) is the right single proof-of-pattern if we want to land incrementally; `--overlapping`
   is the cheapest add, `--within-bbox` introduces the 6-number parser. Bundle all three, or stage?

### 7.6 UNFINISHED — `--within-brush <brush-name>` (true-volume containment)

The exact-volume counterpart to `--within-bbox` (box = fast approximation; brush = the real solid).
**Design so far (still open — not review-clean):**
- **`--within-brush <brush-name>`** (bare name, strict-resolve; error if the named actor has no brush)
  matches actors whose **`Location` is inside the brush's solid** — matching Unreal's own volume
  membership (an actor is "in" a PhysicsVolume/ZoneInfo iff its Location's region is that volume). NOT
  full-AABB containment.
- **Test = general point-in-solid, NO convex assumption.** Ray-casting **parity / crossing-number**
  over the brush's world-transformed faces (odd crossings = inside) — works for ANY closed brush,
  concave or convex. (Engine-exact alternative: the BSP `PointRegion` classifier the editor uses.)
  **Brushes are NOT convex** (a staircase is one non-convex brush of convex faces); an earlier
  convex-only framing was WRONG — `check_convex` guards FACE convexity, and the native
  `point_in_convex` (`csg.rs`) is a tracked defect, not a constraint. Do not gate on convexity.
- **Precondition:** the target is a CLOSED solid brush; a degenerate/open brush makes containment
  ill-defined → warn (that is a "not a solid" issue, orthogonal to convexity).
- **Reuses** the `actor_bounds`/`rotation` world-transform for the faces + a small model-side
  ray-parity helper (or the native BSP classifier for engine-exactness).
- **OPEN:** robustness of ray-parity at face edges/vertices (perturb the ray / consistent tie-break);
  whether to use ray-parity (offline, simple) or the BSP classifier (engine-exact, heavier); first-cut
  vs a slice after the AABB filters. Finish this section before build.

## 8. Docs to update on build

- **`docs/usage.md`** — the three spatial filters, `@Actor` (on `--near`), uu units, semantics, the
  point-actor/mesh caveat.
- **`docs/leveldesign/`** — a "select by region" note.
- **`architecture.md`** — spatial filtering as Decimal AABB predicates over `writes.actor_bounds`, in
  the find handler; the new `writes` AABB helpers.
- **`decisions.md`** — append the resolved §7 sub-choices.
