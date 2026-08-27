//! `UModel::LineCheck` shadow ray — a segment-vs-BSP solid line-of-sight test.
//!
//! Used by the lightmap bake (`light::bake`) as the per-lumel occlusion test (spike section
//! 20-lighting-bake.md §5).  The game's shadow ray is `Level->Model->LineCheck` (`Engine
//! 0xf3560`); we mirror the boolean `FastLineCheck` variant — "is the open segment start->end
//! clear of solid space?".
//!
//! Node convention on the FINALIZED level Model (spike section 60 §2.2, byte-decoded from the
//! game's `Engine.dll`): the engine indexes `iChild[1]` (serial `+0x24` == our `i_back`) for the
//! FRONT (positive, `PlaneDot >= 0`) halfspace and `iChild[0]` (`+0x20` == our `i_front`) for
//! BACK.  `finalize_leaves_and_bbox` has already swapped our build-time slots to this convention,
//! so here `i_back` = FRONT child, `i_front` = BACK child.  A terminal (`== -1`) BACK child of a
//! solid CSG node is SOLID; a terminal FRONT child is empty.  Solidity of a node is
//! `FBspNode::IsCsg` (`Engine 0xf68b0`): `NumVertices > 0 && (NodeFlags & (NF_NotCsg|NF_IsNew)) ==
//! 0`.  Non-CSG faces (semisolid/portal/masked, `NF_NotCsg` set) never block — matching the
//! engine (the shadow ray only occludes on solid surfaces).

use crate::model::{BspNode, Model, Plane, Vec3};

const NF_NOT_CSG: u8 = 0x01;
const NF_NOT_VIS_BLOCKING: u8 = 0x04;
/// `ExtraNodeFlags & 0x10` does NOT exempt a node from being solid — it suppresses the hit while the
/// ray has not yet passed through any open space.
///
/// The engine's walker (`Engine 0x101ae190`) gates a solid terminal on a per-CALL flag, a global at
/// `0x102dbbb4` reset at entry (`0x101ae54a`) and set to 1 only when an EMPTY terminal is reached
/// (`0x101ae4ac`). At a solid terminal it compares that global against zero (`0x101ae449`): non-zero
/// ⇒ record the hit; zero ⇒ test `0x10` and, if set, report clear (`0x101ae451`–`0x101ae45b`). Since
/// the walker takes the near half of every crossing first, "the global is still zero" means every
/// cell so far has been solid, i.e. the ray started inside solid and has not left it.
///
/// So the suppression does NOT set the flag itself: a ray that begins inside a run of several solid
/// cells is suppressed at each of them, and only a blocker met AFTER some open space blocks. That is
/// mirrored here by not setting `seen_empty` in the suppressing branch — pinned by
/// `bright_corners_suppresses_a_whole_leading_run_of_solid_cells`.
pub const NF_BRIGHT_CORNERS: u8 = 0x10;
const NF_IS_NEW: u8 = 0x20;
/// The `ExtraNodeFlags` an ordinary shadow ray passes.  `FBspNode::IsCsg(ExtraFlags)` calls a node
/// solid only when `NodeFlags & (ExtraFlags|0x21) == 0` (`Engine 0xf68b0`, spike section 60 §2.1), so
/// this exempts `NF_NotVisBlocking` nodes from occluding.  The literal is the editor's own
/// (`Editor 0x100a597a` pushes `4`).
pub const VIS_EXTRA_FLAGS: u8 = NF_NOT_VIS_BLOCKING;
/// What the editor passes instead for a `PF_BrightCorners` surface: `0x14` (`0x100a597a` selects it
/// with a `cmove` on `surf.PolyFlags & 0x80000`).  The extra `0x10` is the start-in-solid
/// suppression above, and it is the whole reason those surfaces stay lit where a plain surface goes
/// black: a lumel grid is the surface's texture-space BOUNDING BOX, so on a non-rectangular or
/// corner-adjacent face many lumels sit inside neighbouring solid brushes.
pub const VIS_BRIGHT_CORNERS: u8 = NF_NOT_VIS_BLOCKING | NF_BRIGHT_CORNERS;
/// Recursion-depth backstop.  A well-formed BSP is far shallower; if a pathological tree ever
/// exceeds this we fail OPEN (report clear) — a missed shadow is cosmetic, a false shadow is not.
const MAX_DEPTH: u32 = 4096;

// Conceptual halfspace sides (engine convention).
const FRONT: i32 = 1;
const BACK: i32 = 0;

#[inline]
fn plane_dot(p: &Plane, v: &Vec3) -> f32 {
    p.x * v.x + p.y * v.y + p.z * v.z - p.w
}

#[inline]
fn lerp(a: Vec3, b: Vec3, t: f32) -> Vec3 {
    Vec3::new(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t,
    )
}

/// `FBspNode::IsCsg(ExtraFlags)` — does this node bound solid space (`Engine 0xf68b0`)?
///
/// `NF_BrightCorners` is stripped from the mask: the engine's walker strips it in the two
/// non-crossing branches (`0x101ae23e`, `and al,0xef`) and its meaning is the start-in-solid rule in
/// `seg_clear`, not "this node is see-through". (The crossing branches do NOT strip it, but no writer
/// of that bit into `NodeFlags` exists anywhere in `Editor.dll`, so on a freshly built model the
/// distinction cannot be observed.)
#[inline]
fn is_csg(node: &BspNode, extra_flags: u8) -> bool {
    node.num_vertices > 0
        && (node.node_flags & ((extra_flags & !NF_BRIGHT_CORNERS) | NF_NOT_CSG | NF_IS_NEW)) == 0
}

/// The engine child index for a conceptual side (FRONT -> iChild[1] == `i_back`).
#[inline]
fn child(node: &BspNode, side: i32) -> i32 {
    if side == FRONT {
        node.i_back
    } else {
        node.i_front
    }
}

/// True if the open segment `start`->`end` has clear line-of-sight (never crosses into solid
/// space).  An empty node array (no geometry) is trivially clear.
/// `extra_flags` is the engine's `ExtraNodeFlags` argument: `VIS_EXTRA_FLAGS` for an ordinary
/// surface, `VIS_BRIGHT_CORNERS` for a `PF_BrightCorners` one.
pub fn line_clear(model: &Model, start: Vec3, end: Vec3, extra_flags: u8) -> bool {
    if model.nodes.is_empty() {
        return true;
    }
    // The walk descends the NEAR half of every crossing first, so the first terminal it reaches is
    // the cell holding `start`. That is what makes "no empty cell seen yet" mean "the ray starts
    // inside solid" for `NF_BrightCorners` (see that constant).
    let mut seen_empty = false;
    seg_clear(model, 0, start, end, 0, extra_flags, &mut seen_empty)
}

/// Descend into `child_i` over sub-segment `[a,b]`; `side`/`parent_csg` classify a terminal cell.
#[inline]
#[allow(clippy::too_many_arguments)]
fn descend(
    model: &Model,
    child_i: i32,
    side: i32,
    parent_csg: bool,
    a: Vec3,
    b: Vec3,
    depth: u32,
    extra_flags: u8,
    seen_empty: &mut bool,
) -> bool {
    if child_i == -1 {
        // Terminal cell.  The BACK side of a solid CSG node is solid -> the ray is blocked.
        if !(side == BACK && parent_csg) {
            *seen_empty = true;
            return true;
        }
        // Solid, and no open cell has been crossed yet, so the ray STARTED in solid.
        return !*seen_empty && extra_flags & NF_BRIGHT_CORNERS != 0;
    }
    seg_clear(model, child_i, a, b, depth + 1, extra_flags, seen_empty)
}

fn seg_clear(model: &Model, inode: i32, start: Vec3, end: Vec3, depth: u32, extra_flags: u8,
             seen_empty: &mut bool) -> bool {
    if depth > MAX_DEPTH {
        return true; // fail-open (cosmetic)
    }
    let node = &model.nodes[inode as usize];
    let ds = plane_dot(&node.plane, &start);
    let de = plane_dot(&node.plane, &end);
    let csg = is_csg(node, extra_flags);

    // Whole segment on one side: follow that child (PlaneDot >= 0 -> FRONT, matching PointRegion).
    if ds >= 0.0 && de >= 0.0 {
        return descend(model, child(node, FRONT), FRONT, csg, start, end, depth, extra_flags,
                       seen_empty);
    }
    if ds < 0.0 && de < 0.0 {
        return descend(model, child(node, BACK), BACK, csg, start, end, depth, extra_flags,
                       seen_empty);
    }
    // Crossing: split at the plane, test the NEAR half then the far half.
    let t = ds / (ds - de);
    let mid = lerp(start, end, t);
    if ds >= 0.0 {
        descend(model, child(node, FRONT), FRONT, csg, start, mid, depth, extra_flags, seen_empty)
            && descend(model, child(node, BACK), BACK, csg, mid, end, depth, extra_flags,
                       seen_empty)
    } else {
        descend(model, child(node, BACK), BACK, csg, start, mid, depth, extra_flags, seen_empty)
            && descend(model, child(node, FRONT), FRONT, csg, mid, end, depth, extra_flags,
                       seen_empty)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;

    /// An axis-aligned box brush, OUTWARD normals, CCW-from-outside (mirrors build.rs's fixture).
    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> BrushInput {
        let c = |sx: f32, sy: f32, sz: f32| Vec3::new(sx * hx, sy * hy, sz * hz);
        let faces = [
            (
                Vec3::new(1.0, 0.0, 0.0),
                [
                    c(1.0, -1.0, -1.0),
                    c(1.0, 1.0, -1.0),
                    c(1.0, 1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                ],
            ),
            (
                Vec3::new(-1.0, 0.0, 0.0),
                [
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, -1.0, -1.0),
                    c(-1.0, -1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 1.0, 0.0),
                [
                    c(1.0, 1.0, -1.0),
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, 1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, -1.0, 0.0),
                [
                    c(-1.0, -1.0, -1.0),
                    c(1.0, -1.0, -1.0),
                    c(1.0, -1.0, 1.0),
                    c(-1.0, -1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 0.0, 1.0),
                [
                    c(-1.0, -1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 0.0, -1.0),
                [
                    c(-1.0, 1.0, -1.0),
                    c(1.0, 1.0, -1.0),
                    c(1.0, -1.0, -1.0),
                    c(-1.0, -1.0, -1.0),
                ],
            ),
        ];
        let mut polys = Vec::new();
        for (n, verts) in faces {
            let mut p = FPoly::new(verts.to_vec());
            p.normal = n;
            polys.push(p);
        }
        BrushInput {
            polys,
            oper,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
        }
    }

    #[test]
    fn convex_room_interior_is_all_clear() {
        // Single subtracted room (±256 X/Y, ±128 Z): any two interior points see each other.
        let m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        let pts = [
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(200.0, 200.0, 100.0),
            Vec3::new(-200.0, -200.0, -100.0),
            Vec3::new(200.0, -200.0, 100.0),
            Vec3::new(0.0, 0.0, 120.0),
        ];
        for (i, a) in pts.iter().enumerate() {
            for b in pts.iter().skip(i + 1) {
                assert!(
                    line_clear(&m, *a, *b, VIS_EXTRA_FLAGS),
                    "interior segment {:?}->{:?} must be clear in a convex room",
                    a,
                    b
                );
            }
        }
    }

    #[test]
    fn a_not_vis_blocking_node_does_not_occlude() {
        // `IsCsg(ExtraFlags)` calls a node solid only when `NodeFlags & (ExtraFlags|0x21) == 0`
        // (`Engine 0xf68b0`), and a shadow ray is a VISIBILITY trace, so it passes
        // `NF_NotVisBlocking` as `ExtraFlags` and a node carrying that flag stops occluding.
        //
        // Teeth, measured on the editor's own `LIGHT APPLY` of the UNATCO trunk: 160 of its 6314
        // nodes carry the flag, and treating them as occluders left 54157 lumels dark that the
        // editor lights. Honouring it cut that to 3902 — the largest single correction in the bake.
        // So the flag stays in the mask: flip it back and every one of those nodes casts a shadow
        // the editor does not.
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract)]).unwrap();
        let out = Vec3::new(600.0, 0.0, 0.0);
        assert!(!line_clear(&m, Vec3::new(0.0, 0.0, 0.0), out, VIS_EXTRA_FLAGS),
                "baseline: the +X wall occludes");
        for n in m.nodes.iter_mut() {
            n.node_flags |= NF_NOT_VIS_BLOCKING;
        }
        assert!(line_clear(&m, Vec3::new(0.0, 0.0, 0.0), out, VIS_EXTRA_FLAGS),
                "an NF_NotVisBlocking node must not block a visibility trace");
        assert_eq!(VIS_EXTRA_FLAGS & NF_NOT_VIS_BLOCKING, NF_NOT_VIS_BLOCKING,
                   "the shadow ray's ExtraNodeFlags must include NF_NotVisBlocking");
    }

    #[test]
    fn bright_corners_reports_clear_when_the_ray_starts_in_solid() {
        // `ExtraNodeFlags & NF_BrightCorners` is NOT a see-through flag: it makes the trace report
        // CLEAR when the ray's START is inside solid space, while a blocker met after the ray has
        // crossed open space still blocks. That is the rule that keeps `PF_BrightCorners` surfaces
        // lit where a plain surface goes black, because a lumel grid is the surface's texture-space
        // BOUNDING BOX and many of its lumels sit inside neighbouring solid brushes. On UNATCO it
        // took the editor-lit-but-native-dark lumel count from 3902 to 442 and the solid-blob
        // disagreements from 593 to 2.
        let m = build_geometry_from_brushes(&[box_brush(
            256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract)]).unwrap();
        let inside_solid = Vec3::new(400.0, 0.0, 0.0);      // beyond the +X wall
        let interior = Vec3::new(0.0, 0.0, 0.0);
        assert!(!line_clear(&m, inside_solid, interior, VIS_EXTRA_FLAGS),
                "a ray starting in solid is blocked without the flag");
        assert!(line_clear(&m, inside_solid, interior, VIS_BRIGHT_CORNERS),
                "with NF_BrightCorners a start inside solid must report CLEAR");
        // The suppression is start-only: a ray that starts in the open and runs into a wall still
        // blocks, flag or not.
        assert!(!line_clear(&m, interior, inside_solid, VIS_BRIGHT_CORNERS),
                "the flag must not make a real occluder transparent");
    }

    #[test]
    fn bright_corners_suppresses_a_whole_leading_run_of_solid_cells() {
        // The suppression is gated on a per-CALL flag the engine sets only at an EMPTY terminal, so
        // it fires at EVERY solid cell the ray meets before it first reaches open space — not just
        // the one containing the start. Two rooms with solid between them: a ray starting outside
        // both and passing through the gap crosses several solid cells first.
        //
        // Teeth: setting `seen_empty` in the suppressing branch (the intuitive reading, and what an
        // earlier version of this comment described) would make the SECOND solid cell a hit and turn
        // this assertion red.
        let m = build_geometry_from_brushes(&[
            box_brush(128.0, 128.0, 128.0, Vec3::new(-400.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(128.0, 128.0, 128.0, Vec3::new(400.0, 0.0, 0.0), CsgOper::Subtract),
        ]).unwrap();
        // Start deep in the solid slab left of the far room and aim at the far room's interior: the
        // ray leaves solid, crosses the near room, re-enters solid, then arrives.
        let start = Vec3::new(-900.0, 0.0, 0.0);
        let end = Vec3::new(400.0, 0.0, 0.0);
        assert!(!line_clear(&m, start, end, VIS_EXTRA_FLAGS),
                "baseline: the run of solid blocks without the flag");
        assert!(!line_clear(&m, start, end, VIS_BRIGHT_CORNERS),
                "a blocker met AFTER open space must still block, flag or not");
        // Same start, but stopping inside the FIRST room: only leading solid is crossed.
        assert!(line_clear(&m, start, Vec3::new(-400.0, 0.0, 0.0), VIS_BRIGHT_CORNERS),
                "leading solid must be suppressed all the way to the first open cell");
    }

    #[test]
    fn ray_from_interior_into_solid_is_blocked() {
        // A ray from the room centre out through a wall into solid space is occluded.
        let m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        // interior (0,0,0) to a point well outside the +X wall (x=256): passes through solid.
        assert!(
            !line_clear(&m, Vec3::new(0.0, 0.0, 0.0), Vec3::new(600.0, 0.0, 0.0),
                        VIS_EXTRA_FLAGS),
            "centre -> outside +X wall must be blocked (crosses solid)"
        );
        assert!(
            !line_clear(&m, Vec3::new(0.0, 0.0, 0.0), Vec3::new(0.0, 0.0, 400.0),
                        VIS_EXTRA_FLAGS),
            "centre -> above ceiling must be blocked"
        );
    }
}
