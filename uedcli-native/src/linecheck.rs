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
const NF_IS_NEW: u8 = 0x20;
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

/// `FBspNode::IsCsg` — does this node bound solid space (Engine 0xf68b0)?
#[inline]
fn is_csg(node: &BspNode) -> bool {
    node.num_vertices > 0 && (node.node_flags & (NF_NOT_CSG | NF_IS_NEW)) == 0
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
pub fn line_clear(model: &Model, start: Vec3, end: Vec3) -> bool {
    if model.nodes.is_empty() {
        return true;
    }
    seg_clear(model, 0, start, end, 0)
}

/// Descend into `child_i` over sub-segment `[a,b]`; `side`/`parent_csg` classify a terminal cell.
#[inline]
fn descend(
    model: &Model,
    child_i: i32,
    side: i32,
    parent_csg: bool,
    a: Vec3,
    b: Vec3,
    depth: u32,
) -> bool {
    if child_i == -1 {
        // Terminal cell.  The BACK side of a solid CSG node is solid -> the ray is blocked.
        return !(side == BACK && parent_csg);
    }
    seg_clear(model, child_i, a, b, depth + 1)
}

fn seg_clear(model: &Model, inode: i32, start: Vec3, end: Vec3, depth: u32) -> bool {
    if depth > MAX_DEPTH {
        return true; // fail-open (cosmetic)
    }
    let node = &model.nodes[inode as usize];
    let ds = plane_dot(&node.plane, &start);
    let de = plane_dot(&node.plane, &end);
    let csg = is_csg(node);

    // Whole segment on one side: follow that child (PlaneDot >= 0 -> FRONT, matching PointRegion).
    if ds >= 0.0 && de >= 0.0 {
        return descend(model, child(node, FRONT), FRONT, csg, start, end, depth);
    }
    if ds < 0.0 && de < 0.0 {
        return descend(model, child(node, BACK), BACK, csg, start, end, depth);
    }
    // Crossing: split at the plane, test the near half then the far half.
    let t = ds / (ds - de);
    let mid = lerp(start, end, t);
    if ds >= 0.0 {
        descend(model, child(node, FRONT), FRONT, csg, start, mid, depth)
            && descend(model, child(node, BACK), BACK, csg, mid, end, depth)
    } else {
        descend(model, child(node, BACK), BACK, csg, start, mid, depth)
            && descend(model, child(node, FRONT), FRONT, csg, mid, end, depth)
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
                    line_clear(&m, *a, *b),
                    "interior segment {:?}->{:?} must be clear in a convex room",
                    a,
                    b
                );
            }
        }
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
            !line_clear(&m, Vec3::new(0.0, 0.0, 0.0), Vec3::new(600.0, 0.0, 0.0)),
            "centre -> outside +X wall must be blocked (crosses solid)"
        );
        assert!(
            !line_clear(&m, Vec3::new(0.0, 0.0, 0.0), Vec3::new(0.0, 0.0, 400.0)),
            "centre -> above ceiling must be blocked"
        );
    }
}
