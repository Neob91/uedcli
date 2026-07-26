"""The `brush intersect` / `brush deintersect` golden CASES — one definition, two consumers.

`editor_oracle.py` REGENERATES a golden per case by driving the live UnrealEd (`-m integration`);
`test_brush_merge.py` replays the same case through the native path OFFLINE and diffs it against
the committed golden.  Keeping the sets here means the two can never drift apart.

Each case is `(id, verb, [(name, Brush, csg, props)])`.  The brush list is the CSG set **in order**
— which is the operation's order, so never re-sort it.
"""
from __future__ import annotations

from uedcli import builders

# A case's brush set is built lazily (the builders return fresh mutable Brush objects).
CASES: dict[str, dict] = {
    # (a) The canonical intersect: an additive block with a subtractive notch bitten out of it.
    #     Result = block-minus-notch as ONE welded brush.
    "a_add_with_notch": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Block", builders.cube(256, 256, 128), "add", {}),
            ("Notch", builders.translate_brush(builders.cube(64, 64, 256), 96, 0, 0),
             "subtract", {}),
        ],
    },
    # (b) The canonical deintersect: a subtracted doorway -> the solid door PLUG that fills it.
    "b_doorway_plug": {
        "verb": "deintersect",
        "brushes": lambda: [
            ("Doorway", builders.cube(96, 32, 224), "subtract", {}),
        ],
    },
    # (c) FLAG RULE (spec §3): a SEMISOLID additive in the set must yield semisolid result faces,
    #     while a subtractive source is forced solid.  This is the mover-flags trap made explicit.
    "c_semisolid_additive": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Solid", builders.cube(256, 256, 128), "add", {}),
            ("Semi", builders.translate_brush(builders.cube(128, 128, 128), 192, 0, 0),
             "add", {"PolyFlags": str(builders.SOLIDITY_FLAGS["semisolid"])}),
        ],
    },
    # (e) A ROTATED source brush — the transform flows through `_build_brush_input` (FRotator ->
    #     the GMath sine table), so the merge must carve at the rotated pose.
    "e_rotated_source": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Slab", builders.cube(256, 128, 64), "add", {"Rotation": "(Yaw=8192)"}),
        ],
    },
    # (f) A DISJOINT set: two far-apart additive cubes merge into one actor with TWO disconnected
    #     components (there is no --split; the verb warns and emits one actor).
    "f_disjoint_pair": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Near", builders.cube(128, 128, 128), "add", {}),
            ("Far", builders.translate_brush(builders.cube(128, 128, 128), 1024, 0, 0),
             "add", {}),
        ],
    },
    # (h) A LEADING-ADDITIVE deintersect set — the convex-seed tripwire (spec §4): `deintersect`
    #     has no wrap-subtract, so the first stdin brush seeds the world.  When that brush is an
    #     Add, `bsp_brush_csg`'s `first_add_seed` path fires, which is untested for this shape.
    "h_leading_additive_deintersect": {
        "verb": "deintersect",
        "brushes": lambda: [
            ("Pillar", builders.cube(64, 64, 256), "add", {}),
            ("Room", builders.cube(256, 256, 192), "subtract", {}),
        ],
    },
    # --- ORDER-DEPENDENT CSG: the add -> subtract -> add-inside-the-subtract family --------------
    # (i) The classic: carve a cavity, then put a solid back INSIDE it.  Three ops on overlapping
    #     regions, so it only comes out right if op ORDER is honoured all the way through.  The
    #     result is a block with a hollow containing a free-floating pillar.
    "i_readd_inside_subtract": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Block", builders.cube(256, 256, 192), "add", {}),
            ("Cavity", builders.cube(128, 128, 128), "subtract", {}),
            ("Pillar", builders.cube(32, 32, 128), "add", {}),
        ],
    },
    # (j) Same region THREE times, add -> subtract -> add: last op on a region wins, so the block
    #     must come back WHOLE.  A build that dropped or reordered the trailing add returns a hole.
    "j_add_subtract_readd_same_box": {
        "verb": "intersect",
        "brushes": lambda: [
            ("A1", builders.cube(192, 192, 128), "add", {}),
            ("S1", builders.cube(96, 96, 256), "subtract", {}),
            ("A2", builders.cube(96, 96, 256), "add", {}),
        ],
    },
    # --- OVERLAP / SHARED-SURFACE cases ---------------------------------------------------------
    # (k) Two OVERLAPPING additives: the interior walls inside the union must be annihilated, not
    #     left as internal faces.
    "k_overlapping_adds": {
        "verb": "intersect",
        "brushes": lambda: [
            ("A", builders.cube(192, 192, 128), "add", {}),
            ("B", builders.translate_brush(builders.cube(192, 192, 128), 96, 96, 0), "add", {}),
        ],
    },
    # (l) Two ABUTTING additives sharing an exact COPLANAR face — the fragile classification case
    #     (`SplitWithPlane`'s +-0.25uu coplanar band, `quirks.md` "CSG model").
    "l_abutting_adds_coplanar": {
        "verb": "intersect",
        "brushes": lambda: [
            ("A", builders.cube(128, 128, 128), "add", {}),
            ("B", builders.translate_brush(builders.cube(128, 128, 128), 128, 0, 0), "add", {}),
        ],
    },
    # (m) Two adds meeting along an EDGE only — zero-volume contact, the degenerate connectivity
    #     case (is the result one component or two?).
    "m_edge_touching_adds": {
        "verb": "intersect",
        "brushes": lambda: [
            ("A", builders.cube(128, 128, 128), "add", {}),
            ("B", builders.translate_brush(builders.cube(128, 128, 128), 128, 128, 0), "add", {}),
        ],
    },
    # (n) Two OVERLAPPING subtractives -> deintersect: the plug of an L-shaped void, i.e. a
    #     non-convex result whose two lobes share interior volume.
    "n_overlapping_subtracts": {
        "verb": "deintersect",
        "brushes": lambda: [
            ("S1", builders.cube(192, 64, 128), "subtract", {}),
            ("S2", builders.translate_brush(builders.cube(64, 192, 128), 64, 64, 0),
             "subtract", {}),
        ],
    },
    # (o) A subtract NESTED inside a larger subtract — the second carves already-empty space, so it
    #     must contribute nothing and the plug must be the outer void alone.
    "o_nested_subtracts": {
        "verb": "deintersect",
        "brushes": lambda: [
            ("Outer", builders.cube(256, 256, 128), "subtract", {}),
            ("Inner", builders.cube(64, 64, 64), "subtract", {}),
        ],
    },
    # (p) Two DISJOINT subtractives -> a two-component plug (the disjoint case on the deintersect
    #     side; `f_disjoint_pair` covers intersect).
    "p_disjoint_subtracts": {
        "verb": "deintersect",
        "brushes": lambda: [
            ("S1", builders.cube(128, 128, 128), "subtract", {}),
            ("S2", builders.translate_brush(builders.cube(128, 128, 128), 1024, 0, 0),
             "subtract", {}),
        ],
    },
    # --- PRECISION / SHAPE edge cases -----------------------------------------------------------
    # (q) A THIN slab (2uu) with a subtract cutting through it — thin geometry is where
    #     `FPoly::Finalize`'s zero-area floor and `RemoveColinears` drop faces (`quirks.md`).
    "q_thin_slab_with_cut": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Slab", builders.cube(256, 256, 2), "add", {}),
            ("Cut", builders.cube(64, 512, 64), "subtract", {}),
        ],
    },
    # (r) A ROTATED additive OVERLAPPING an axis-aligned one — non-axis CSG, where the face normals
    #     come off the GMath sine table rather than exact unit axes.
    "r_rotated_overlap": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Axis", builders.cube(192, 192, 128), "add", {}),
            ("Turned", builders.cube(192, 192, 128), "add", {"Rotation": "(Yaw=8192)"}),
        ],
    },
    # (s) An OFF-GRID brush (fractional coordinates) — the off-grid hole class `level doctor` exists
    #     to catch; the merge must agree with the editor even where the ±0.25uu band bites.
    "s_off_grid_add_with_cut": {
        "verb": "intersect",
        "brushes": lambda: [
            ("Block", builders.cube(200, 200, 100), "add", {}),
            ("Cut", builders.translate_brush(builders.cube(64, 64, 256), 50.5, 0.25, 0),
             "subtract", {}),
        ],
    },
}


def build_actors(case_id: str):
    """The case's brush set as T3D-ready Actors, in CSG order."""
    case = CASES[case_id]
    actors = []
    for name, brush, csg, props in case["brushes"]():
        a = builders.make_brush_actor(name, brush, csg=csg)
        for k, v in props.items():
            a.props = [p for p in a.props if p[0] != k] + [(k, v)]
        actors.append(a)
    return actors
