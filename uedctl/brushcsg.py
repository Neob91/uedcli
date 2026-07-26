"""`brush intersect` / `brush deintersect` — CSG-merge a brush SET into ONE brush, natively.

These are **generators** (`CLAUDE.md` "Verbs compose"): they consume a T3D brush set on stdin and
produce one brush (or Mover) actor T3D on stdout.  No editor, no trunk write — the caller decides
what to do with the output (`… | actor add -`, `> plug.t3d`).

**What they compute.**  Both merge the set into one brush and differ only in the assumed background:

| verb          | background     | the set's role                              | result                                  |
|---------------|----------------|---------------------------------------------|-----------------------------------------|
| `intersect`   | **empty**      | additives make solid, subtractives carve it | the resulting SOLID's boundary, welded   |
| `deintersect` | **full/solid** | subtractives carve VOIDS out of solid       | the VOID as a solid — the "plug"/negative |

`intersect` welds an additive cluster (an additive block with a subtractive notch → one brush
shaped like block-minus-notch).  `deintersect` produces the solid that exactly fills what the set
carves — the door-plug that fits a subtracted doorway, which is why it pairs with `--mover-class`.

**How.**  UnrealEd's `BRUSH FROM INTERSECTION`/`DEINTERSECTION` is `builder-brush ∩ world`, so it
structurally needs a live red builder brush AND a surrounding carved room.  uedctl has neither, so
this module SYNTHESIZES both internally — a padded-bbox builder cube, plus (for `intersect`) a
wrap-subtract cube that forces the empty background — and runs the real decoded algorithm on them
(`uedctl_native.intersect_brushset`, the `bspcsg.rs:1845` tail).  The user never sees the
scaffolding; the operation is a faithful port, not a lookalike.

Spec: `dev/docs/specs/2026-07-24-intersect-deintersect-native-brushset.md`.
RE: `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`.
Decisions: `dev/docs/decisions.md` 2026-07-24 16:32 / 17:04 / 17:56 / 18:12 / 18:33 UTC.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from . import builders
from .emit import clean, fmt_loc
from .model import Brush, Polygon

# --- internal scaffolding geometry ------------------------------------------------------------
#
# Both cubes are `bbox + 2*PAD` on every axis, CENTRED on the set — i.e. THE SAME BOX.  The builder
# then strictly contains the set with a `PAD` margin, and (for intersect) the wrap-subtract carves
# exactly the builder's own volume empty, so every builder face is cospatial with the void boundary
# and Phase 1 keeps none of them: the whole result comes from the set's own surfaces (the Phase-2
# world caps).  A wrap SMALLER than the builder would leave the protruding part of the builder in
# untouched solid background, and Phase 1 would weld a hollow shell of scaffolding onto the result.
#
# ⚠️ This CORRECTS the spec (§4), which read the editor-driven `_stash_intersect_impl` as placing
# the wrap at `(cx-32, cy-32, cz-32)` — "DIFFERENT boxes; the -32 offset is load-bearing".  It is
# not: that -32 is the standing compensation for UnrealEd's **`EDIT PASTE` +32uu drift on all three
# axes** (`unrealed/quirks.md` "EDIT PASTE drift"), which the wrap goes through and the
# `BRUSH IMPORT`ed builder does not.  In WORLD space the editor's two cubes coincide exactly.  The
# native path has no paste, so it must not re-apply the compensation.  Confirmed against the live
# editor oracle 2026-07-24: driving the editor path over one additive 256x256x128 cube returns the
# SOURCE box (6 faces, x/y [-128,128], z [-64,64]), not the [-160,160] builder-shelled form the
# offset reading predicts.  Re-derivable: `tests/editor_oracle.py` +
# `tests/test_integration_intersect_oracle.py`, whose output is the committed
# `tests/fixtures/intersect/` goldens.
BUILDER_PAD = 32.0
WRAP_PAD = 32.0

# The `deintersect` seed-subtract (see `build_scaffolding`): a small cube parked clear of the
# builder purely so the set's first brush never meets an empty tree.  `SEED_GAP` is added to the
# set's own largest span, so the clearance scales with the geometry instead of being a magic
# absolute that a large enough set could swallow.
SEED_HALF = 32.0
SEED_GAP = 512.0

# T3D-visible poly flags: drop the editor-internal high bits (PF_EdProcessed 0x40000000,
# PF_EdCut 0x80000000, PF_Memorized …) that the CSG descent sets as scratch state.  They must never
# reach the trunk.  Mirrors the mask the CSG core applies at `alloc_surf`/`bsp_node_to_fpoly`.
POLY_FLAG_MASK = 0x3CFFFFFF
# PF_NotSolid | PF_Semisolid — the per-face solidity bits `--solidity` overrides.
SOLIDITY_BITS = 0x28


class BrushCsgError(Exception):
    """A merge failure carrying the offending value (surfaces as a clean exit-2)."""


def _oper_of(actor) -> str:
    return next((v for k, v in actor.props if k == "CsgOper"), "CSG_Add")


def check_all_csg_brushes(actors, *, verb: str, index) -> None:
    """Every actor in the stream must be a world-CSG brush — else exit-2, naming the offenders.
    `index` is the `classindex.ClassIndex` the schema-aware `movers.is_mover` gate resolves the
    class hierarchy against (via `_in_world_csg`).

    A non-brush (a light that rode along in the pipe) or a Mover (a dynamic actor UnrealEd keeps out
    of world CSG entirely) cannot contribute to the merge.  Silently dropping it and warning on
    stderr would hand back a plug that is quietly missing a piece — the caller reads the T3D as the
    complete answer and the warning scrolls away.  So we refuse and say how to narrow the pipe.
    *(`dev/docs/direction/conventions.md` "No silent half-answers", decision 2026-07-24 21:58 — this SUPERSEDES the spec's
    original warn-and-skip, which predates that rule.)*
    """
    from .native.materialize import _in_world_csg

    bad = []
    for a in actors:
        if a.brush is None or not a.brush.polys:
            bad.append(f"{a.name} ({a.cls or 'no class'}) is not a brush actor")
        elif not _in_world_csg(a, index):
            bad.append(f"{a.name} ({a.cls}) is a Mover, which never participates in world CSG")
    if bad:
        raise BrushCsgError(
            f"brush {verb}: the piped set contains actors that cannot be merged:\n  "
            + "\n  ".join(bad)
            + "\nNarrow the pipe to CSG brushes, e.g. `actor find --kind brush …`.")


def check_guards(actors, *, deintersect: bool) -> None:
    """`intersect` needs >=1 additive, `deintersect` needs >=1 subtractive — else exit-2 with
    cross-verb guidance (mirrors the editor-driven impl this replaces)."""
    opers = [_oper_of(a) for a in actors]
    if not deintersect and "CSG_Add" not in opers:
        raise BrushCsgError(
            "brush intersect: the set has no additive brush — intersect merges additives "
            "against an EMPTY background; use `brush deintersect` for a subtractive set")
    if deintersect and "CSG_Subtract" not in opers:
        raise BrushCsgError(
            "brush deintersect: the set has no subtractive brush — deintersect extracts the void "
            "carved out of SOLID background; use `brush intersect` for an additive set")


def check_unscaled(actors) -> None:
    """Reject a scaled source brush, naming it (spec §6).

    Inherited from the incremental bspcsg core, which errors on a non-identity `MainScale`/
    `PostScale` (`bspcsg.rs:2064`) — a pre-existing CORE gap, not an intersect-specific one, tracked
    as its own board item ("bspcsg core: apply scaled brushes").  Until it lands we refuse loudly
    instead of silently mis-building: a scaled brush would carve at the wrong size.
    """
    from . import rotation as ROT

    for a in actors:
        if not (ROT.actor_main_scale(a).is_identity() and ROT.actor_post_scale(a).is_identity()):
            raise BrushCsgError(
                f"brush actor {a.name} has a non-identity MainScale/PostScale — scaled source "
                f"brushes are not supported yet; bake it first with `brush apply-transform {a.name}`")


def _cube_actor(name: str, center, half, *, csg: str | None, oper_prop: str | None = None):
    """One axis-aligned scaffolding cube as a brush Actor (so it marshals through the same
    `_build_brush_input` path as a real source brush)."""
    b = builders.cube(half[0] * 2, half[1] * 2, half[2] * 2)
    a = builders.make_brush_actor(name, b, location=center, csg=csg or "add")
    if oper_prop is not None:
        a.props = [(k, oper_prop if k == "CsgOper" else v) for k, v in a.props]
    return a


def build_scaffolding(actors, *, deintersect: bool):
    """The internally-synthesized builder + (for intersect) wrap-subtract cubes.

    Returns `(world_actors, builder_actor)`: `world_actors` is the CSG set in STDIN ORDER (never
    re-sorted — CSG over a mixed add/subtract set is order-dependent, spec §6) with the
    wrap-subtract PREPENDED for `intersect`; `builder_actor` carries `CsgOper=CSG_Intersect` or
    `CSG_Deintersect`, which is what selects the operation in the native tail.
    """
    from . import writes

    lo, hi = writes.union_bounds(actors)
    center = tuple((float(lo[i]) + float(hi[i])) / 2 for i in range(3))
    span = tuple(float(hi[i]) - float(lo[i]) for i in range(3))
    bhalf = tuple(span[i] / 2 + BUILDER_PAD for i in range(3))
    builder = _cube_actor("BuilderBrush", center, bhalf, csg=None,
                          oper_prop="CSG_Deintersect" if deintersect else "CSG_Intersect")
    world = list(actors)
    if not deintersect:
        whalf = tuple(span[i] / 2 + WRAP_PAD for i in range(3))
        world.insert(0, _cube_actor("WrapSubtract", center, whalf, csg="subtract"))
    else:
        # A DISTANT seed-subtract, far outside the builder — the fix for the leading-additive case.
        #
        # `deintersect` wants the engine's default SOLID background, so it must not wrap the set.
        # But that leaves the set's FIRST brush filtering into a node-LESS world, and the CSG core
        # treats that specially: a leading `CSG_Add` is not classified at all, it is SEEDED as the
        # convex world shell (root nodes, stored reversed).  That shortcut is exactly right for the
        # brush every real level opens with — the box enclosing the map — and wrong for an Add that
        # is a small solid inside what a later subtract carves away: the seeded faces survive as
        # splitters, so the plug came back with the additive punched out of it (editor: the plain
        # void).  Fixed golden `h_leading_additive_deintersect`.
        #
        # Seeding the world with a SUBTRACT first takes the shortcut out of play entirely — every
        # user brush then filters into a non-empty world, whatever its CsgOper.  (The shortcut itself
        # is UNCHANGED and still correct for the world-shell case it exists for — see the
        # `first_add_seed` comment in `bspcsg.rs`, and the p3 board item for the general fix.)  Placing it far
        # outside the builder keeps it inert: Phase 2 prunes the world tree by the builder's bound
        # SPHERE, so this cube's faces are never reached, and its planes are far enough away that
        # every face in the working region lies wholly on one side of them (no stray splits).  It is
        # scaffolding, exactly like `intersect`'s wrap — the user never sees it.
        #
        # (A leading no-op wrap-ADD was tried first and is WRONG: an additive's faces land INSIDE the
        # builder hull, so Phase 2 collects them as caps and the doorway plug comes back as the whole
        # padded box.  The seed must be a subtract, and it must be outside the hull.)
        gap = max(span) + SEED_GAP
        seed_at = (center[0], center[1], center[2] + span[2] / 2 + BUILDER_PAD + gap)
        world.insert(0, _cube_actor("SeedSubtract", seed_at,
                                    (SEED_HALF, SEED_HALF, SEED_HALF), csg="subtract"))
    return world, builder


def merge(actors, *, deintersect: bool):
    """Run the native merge; return the result faces as `(Polygon, source_actor_or_None)` pairs.

    The CSG core never sees textures (they are not part of a `BrushTuple`), so each result face
    carries the `(actor, i_brush_poly)` identity of the SOURCE face it was cut from and we resolve
    `Texture`/`PanU`/`PanV` back out of that source poly here.  `actor == -1` marks a Phase-1 face
    off the synthesized builder cube, which has no authored texture.
    """
    import uedctl_native
    from .native.materialize import _build_brush_input

    world, builder = build_scaffolding(actors, deintersect=deintersect)
    tuples = [_build_brush_input(a.name, a) for a in world]
    btuple = _build_brush_input(builder.name, builder)
    faces = uedctl_native.intersect_brushset(tuples, btuple)

    out = []
    for verts, normal, base, tu, tv, flags, link, ai, ibp in faces:
        src_actor = world[ai] if 0 <= ai < len(world) else None
        src_poly = None
        if src_actor is not None and 0 <= ibp < len(src_actor.brush.polys):
            src_poly = src_actor.brush.polys[ibp]
        p = Polygon(
            flags=int(flags) & POLY_FLAG_MASK,
            texture=getattr(src_poly, "texture", None),
            item=getattr(src_poly, "item", None),
            pan=getattr(src_poly, "pan", None),
            origin=(clean(base[0]), clean(base[1]), clean(base[2])),
            normal=(clean(normal[0]), clean(normal[1]), clean(normal[2])),
            texture_u=(clean(tu[0]), clean(tu[1]), clean(tu[2])),
            texture_v=(clean(tv[0]), clean(tv[1]), clean(tv[2])),
            vertices=[(clean(verts[i]), clean(verts[i + 1]), clean(verts[i + 2]))
                      for i in range(0, len(verts), 3)],
        )
        out.append((p, src_actor))
    return out


# --- placement (spec §6b: movability & pivot) ---------------------------------------------------

def parse_anchor_spec(spec, *, flag: str, allow_keep: bool):
    """`--origin`/`--pivot` grammar: a keyword, or an explicit `X,Y,Z` world point."""
    if spec is None:
        return None
    words = ("center", "min", "max") + (("keep",) if allow_keep else ())
    if spec in words:
        return spec
    parts = [p.strip() for p in str(spec).split(",")]
    if len(parts) != 3:
        raise BrushCsgError(
            f"{flag}: expected one of {'|'.join(words)} or an explicit X,Y,Z world point, "
            f"got {spec!r}")
    try:
        return tuple(Decimal(p) for p in parts)
    except Exception:
        raise BrushCsgError(f"{flag}: {spec!r} is not a valid X,Y,Z world point") from None


def resolve_anchor(spec, lo, hi):
    """`center` (default) | `min` | `max` | an explicit `X,Y,Z` -> a world point."""
    if spec is None or spec == "center":
        return tuple((lo[i] + hi[i]) / 2 for i in range(3))
    if spec == "min":
        return tuple(lo)
    if spec == "max":
        return tuple(hi)
    return tuple(Decimal(str(c)) for c in spec)


def recenter(polys, *, anchor, pivot):
    """Rebase the result onto `anchor` and set its rotation pivot to the world point `pivot`.

    A brush's world geometry is `world = Location + R·(v − PrePivot)`, so the point that stays put
    under rotation is the one where `v == PrePivot`, and it always maps to `Location`.  To preserve
    the carved world position AND rotate about a chosen world pivot `P`, all three move together:

        v_local  = v_world − anchor       (the poly ORIGIN rebases too — it is a point;
                                           Normal/TextureU/TextureV are DIRECTIONS, unchanged)
        PrePivot = P − anchor             (local)
        Location = P                      (world)

    At rest (R = I): `Location + (v_world − anchor) − (P − anchor) == v_world` ✓, and the rotation
    centre is `Location = P` ✓.  With the default `P == anchor` this collapses to the plain
    re-centre: `PrePivot = 0`, `Location = anchor`.

    Returns `(location, prepivot)`; `polys` are rebased IN PLACE.
    """
    for p in polys:
        p.vertices = [tuple(v[i] - anchor[i] for i in range(3)) for v in p.vertices]
        if p.origin is not None:
            p.origin = tuple(p.origin[i] - anchor[i] for i in range(3))
    return tuple(pivot), tuple(pivot[i] - anchor[i] for i in range(3))


def apply_solidity(polys, solidity: str | None) -> int:
    """The ONLY post-extraction flag step (spec §3).

    The DEFAULT (`solidity is None`) is the faithful per-face rule, and it is already baked in by
    the merge: LOOP-1 strips `PF_NotSolid|PF_Semisolid` off a subtractive/builder source face while
    an additive source keeps its solidity, so a semisolid face can only have come from a
    deliberately semisolid additive.  It is NOT re-derived here — after extraction an FPoly no
    longer knows its source `CsgOper`, so re-deriving would be ill-posed.

    `solid` clears the solidity bits on every face (a clean brush).  `semisolid`/`nonsolid` set the
    ACTOR-level PolyFlags (which governs) and clear the per-face bits.  Returns the actor-level
    PolyFlags to stamp.
    """
    if solidity is None:
        return 0
    for p in polys:
        p.flags &= ~SOLIDITY_BITS
    return builders.SOLIDITY_FLAGS.get(solidity, 0)


def component_count(polys) -> int:
    """Number of DISCONNECTED solids in the result (faces joined by a shared vertex).

    A set can merge into several disjoint pieces (two far-apart clusters under `intersect`).  The
    editor returns them as ONE brush with several face groups and so do we — there is deliberately
    no `--split` (decision 2026-07-24 18:12); the caller who wants separate movers runs the verb on
    each subset.  We only COUNT them so the verb can say so on stderr.
    """
    parent = list(range(len(polys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[tuple, int] = {}
    for i, p in enumerate(polys):
        for v in p.vertices:
            key = tuple(v)
            j = seen.setdefault(key, i)
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj
    return len({find(i) for i in range(len(polys))}) if polys else 0


def result_bounds(polys):
    verts = [v for p in polys for v in p.vertices]
    lo = tuple(min(v[i] for v in verts) for i in range(3))
    hi = tuple(max(v[i] for v in verts) for i in range(3))
    return lo, hi


def make_result_actor(polys, *, name: str, location, prepivot, csg: str,
                      poly_flags: int, mover_class: str | None):
    """Wrap the merged face set into the ONE emitted actor (placeholder `Name=` — allocation is
    `actor add`'s job, per the generator convention)."""
    brush = Brush(model_name="Model", polys=polys)
    actor = builders.make_brush_actor(name, brush, location=location, csg=csg,
                                      poly_flags=poly_flags, mover_class=mover_class)
    if any(c != 0 for c in prepivot):
        # Emit through `fmt_loc`, the same formatter `Location` and `transform.bake`'s PrePivot use.
        # A bare `Decimal` repr would put `(X=-48,…)` next to `Location=(X=-48.000000,…)` on the same
        # actor, and would render a large coordinate in exponent form, which
        # `rotation.actor_prepivot`'s `(-?[0-9.]+)` regex silently reads as 0.
        actor.props.insert(
            0, ("PrePivot", f"(X={fmt_loc(prepivot[0])},Y={fmt_loc(prepivot[1])},"
                            f"Z={fmt_loc(prepivot[2])})"))
    return actor
