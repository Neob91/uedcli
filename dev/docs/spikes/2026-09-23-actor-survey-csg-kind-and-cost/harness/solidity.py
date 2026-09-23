"""`point_is_solid` — the engine's own point-in-solid test, ported to Python over a parsed
`native/umodel.Model`.

Why not `native/materialize._model_point_region`: that is `UModel::PointRegion`, which answers
"which ZONE LEAF holds this point". A SEMISOLID brush's nodes are added in the editor's LOOP 3,
AFTER `TestVisibility` has already assigned leaves and zones (`uedcli-native/src/bspcsg.rs`: zone
pass then the detail-brush pass), so a semisolid's interior carries no leaf of its own and
`PointRegion` reports the surrounding void's leaf for it. Measured here, not assumed:
`kind_semantics.py` shows a semisolid pillar reading `void` inside under `PointRegion` while an
identical Add pillar reads `solid`. Semisolid is ~29% of brush actors in shipped Deus Ex content,
so using `PointRegion` as a solidity oracle would systematically under-report.

What the engine really uses during a collision trace is `FBspNode::IsCsg` plus the walker's
running "outside" state — never a leaf index and never a `PolyFlags` read
(`dev/docs/unrealed/quirks.md`, "World collision is structural, not per-poly"). This is the
zero-extent form of that walk, a direct port of `uedcli-native/src/linecheck.rs`'s
`is_csg`/`combine_state`/`child` and `collision.rs`'s `CollisionModel::point_check` entry state.
"""
from __future__ import annotations

FRONT, BACK = 1, 0
NF_NOT_CSG = 0x01
NF_IS_NEW = 0x20


def _plane_dot(plane, v) -> float:
    return plane[0] * v[0] + plane[1] * v[1] + plane[2] * v[2] - plane[3]


def _is_csg(node, extra_flags: int) -> bool:
    """`FBspNode::IsCsg(ExtraFlags)` — does this node bound solid space?"""
    return node.num_vertices > 0 and (node.node_flags & (extra_flags | NF_NOT_CSG | NF_IS_NEW)) == 0


def point_is_solid(model, p, *, extra_flags: int = 0) -> bool:
    """True iff `p` is in SOLID space. `state` is the walker's "positive evidence of open space":
    going FRONT of a CSG-solid node proves open, BACK of one proves solid, a non-CSG node passes the
    state through unchanged (`linecheck.rs::combine_state`)."""
    if not model.nodes:
        return not model.root_outside
    state = bool(model.root_outside)
    i = 0
    while i != -1:
        n = model.nodes[i]
        side = FRONT if _plane_dot(n.plane, p) >= 0.0 else BACK
        csg = _is_csg(n, extra_flags)
        state = (state or csg) if side == FRONT else (state and not csg)
        i = n.i_back if side == FRONT else n.i_front
    return not state
