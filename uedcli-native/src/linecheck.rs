//! `UModel::LineCheck` shadow ray — a segment-vs-BSP solid line-of-sight test.
//!
//! Used by the lightmap bake (`light::bake`) as the per-lumel occlusion test (spike section
//! 20-lighting-bake.md §5). Ported from the EDITOR's own bake-time walker (`Editor.dll
//! 0x17ce190`, reached from `illuminateSurf`'s per-lumel loop via `Model` vtable slot `+0x58`) —
//! the function `LIGHT APPLY` actually calls, live-disassembled and verified round 3-8 of
//! `line-clear-shadow-ray-algorithm-gap-found-real` (see `dev/docs/native-materialize-findings.md`).
//!
//! Node convention on the FINALIZED level Model (spike section 60 §2.2, byte-decoded from the
//! game's `Engine.dll`, and independently re-confirmed live against the editor's own walker round
//! 1): the engine indexes `iChild[1]` (serial `+0x24` == our `i_back`) for the FRONT (positive,
//! `PlaneDot >= 0`) halfspace and `iChild[0]` (`+0x20` == our `i_front`) for BACK.
//! `finalize_leaves_and_bbox` has already swapped our build-time slots to this convention, so here
//! `i_back` = FRONT child, `i_front` = BACK child.  Solidity of a node is `FBspNode::IsCsg`
//! (`Engine 0xf68b0`): `NumVertices > 0 && (NodeFlags & (NF_NotCsg|NF_IsNew)) == 0`.  Non-CSG faces
//! (semisolid/portal/masked, `NF_NotCsg` set) never block — matching the engine (the shadow ray
//! only occludes on solid surfaces).
//!
//! The walker THREADS an accumulating open/solid `state` across the whole recursion (see
//! `combine_state`/`terminal` below) rather than deciding a terminal from its direct parent alone:
//! a terminal's solidity depends on whether the walk has POSITIVE evidence of open space anywhere
//! along its ancestry, not just the immediately enclosing node. Round 4 tried the crossing formula
//! without this threading and regressed Wanchai/UNATCO badly; round 7/8 pinned and live-verified
//! the full threaded shape.

use crate::model::{BspNode, Model, Plane, Vec3};

/// Whole-segment classification epsilon (`Editor.dll 0x17ce21e`/`0x17ce26a`, live-read as exactly
/// +/-0.001 this round): a node whose plane-dot for BOTH endpoints falls within this band of a
/// strict `>=0`/`<0` split still counts as "whole segment" on the corresponding side, rather than
/// forcing a crossing split. Round 6/7 pinned this value; round 8 re-confirmed it live
/// (`linecheck_walker_state_trace.py`: `CONST1=-0.00100000005`, `CONST2=0.00100000005`).
const WHOLE_SEGMENT_EPS: f32 = 0.001;

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
/// mirrored here by not setting `seen_empty` in `terminal`'s suppressing branch — pinned by
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

/// The crossing point: `p2 + t*(p2-p1)` — the real walker's own formula (`Editor.dll 0x17ce2ae`-
/// `0x17ce300`, live-verified round 3/4/8 to full float32 precision), NOT a symmetric two-point
/// lerp: the `t` this is paired with is keyed on `d2` (point2's own plane-dot), not the segment
/// fraction from `p1`.
#[inline]
fn crossing_mid(p1: Vec3, p2: Vec3, t: f32) -> Vec3 {
    Vec3::new(
        p2.x + (p2.x - p1.x) * t,
        p2.y + (p2.y - p1.y) * t,
        p2.z + (p2.z - p1.z) * t,
    )
}

/// `FBspNode::IsCsg(ExtraFlags)` — does this node bound solid space (`Engine 0xf68b0`)?
///
/// `strip_bright_corners` controls whether `NF_BrightCorners` is stripped from the mask before the
/// test: the real walker (`Editor.dll 0x17ce190`) strips it at the two whole-segment classification
/// sites (`0x17ce23e`/`0x17ce282`, `and al,0xef`) but NOT at the near-call incoming-state or
/// far-continuation sites (`0x17ce32d`/`0x17ce34c`/`0x17ce3d5`/`0x17ce3ef` — no `and 0xef` there),
/// live-confirmed round 7/8. Its meaning is the start-in-solid rule in `terminal`, not "this node is
/// see-through" — but the two whole-segment sites treat it as ordinary occlusion state (round 7's
/// "self-correction": CSG-solid on the BACK side FORCES the state to solid, not "unchanged").
#[inline]
fn is_csg(node: &BspNode, extra_flags: u8, strip_bright_corners: bool) -> bool {
    let mask = if strip_bright_corners { extra_flags & !NF_BRIGHT_CORNERS } else { extra_flags }
        | NF_NOT_CSG | NF_IS_NEW;
    node.num_vertices > 0 && (node.node_flags & mask) == 0
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

/// The single state-update rule used at all three classification sites in the real walker (whole
/// FRONT/BACK segment, the near recursive call's incoming state, and the far continuation after it
/// returns clear) — algebraically identical at each site once written this way (round 7/8): going
/// FRONT of a CSG-solid node PROVES open space (state becomes/stays true); going BACK of one PROVES
/// solid (state becomes/stays false); a non-CSG node never changes the incoming state either way.
#[inline]
fn combine_state(side: i32, state: bool, csg: bool) -> bool {
    if side == FRONT {
        state || csg
    } else {
        state && !csg
    }
}

/// `state`'s meaning at a terminal (`inode == -1`): true = the walk has POSITIVE evidence the ray is
/// in open space (it went FRONT of some CSG-solid node, or inherited that from an ancestor through a
/// chain of non-CSG pass-throughs); false = no such evidence yet (either genuinely solid, or the walk
/// started there and every node crossed so far was a non-occluding pass-through).
///
/// `Editor.dll 0x17ce442`-`0x17ce4be`, live-confirmed round 7/8 (122 mechanical checks + the live
/// top-level-args capture below): `state==true` always reports clear and marks `seen_empty` (the ray
/// has now demonstrably left solid space, so a LATER solid terminal is a real hit, not start-in-
/// solid). `state==false` reports clear ONLY as the `NF_BrightCorners` start-in-solid suppression
/// (same rule as v1's `descend`, folded in here) — and does NOT itself mark `seen_empty`.
#[inline]
fn terminal(state: bool, extra_flags: u8, seen_empty: &mut bool) -> bool {
    if state {
        *seen_empty = true;
        return true;
    }
    if *seen_empty {
        return false;
    }
    extra_flags & NF_BRIGHT_CORNERS != 0
}

/// True if the open segment `start`->`end` has clear line-of-sight (never crosses into solid
/// space).  An empty node array (no geometry) is trivially clear.
/// `extra_flags` is the engine's `ExtraNodeFlags` argument: `VIS_EXTRA_FLAGS` for an ordinary
/// surface, `VIS_BRIGHT_CORNERS` for a `PF_BrightCorners` one.
///
/// Mirrors the real walker's own point roles (live-confirmed round 3/8, top-level-args capture):
/// `point1` starts as `end` (the light location), `point2` starts as `start` (the lumel/query
/// point) — point2 stays fixed across the near-recursion chain while point1 gets replaced by each
/// crossing's `mid`, matching round 5's structural-invariant finding.
pub fn line_clear(model: &Model, start: Vec3, end: Vec3, extra_flags: u8) -> bool {
    if model.nodes.is_empty() {
        return true;
    }
    let mut seen_empty = false;
    seg_clear(model, 0, end, start, false, 0, extra_flags, &mut seen_empty)
}

/// The real recursive walker (`Editor.dll 0x17ce190`), disassembled and live-verified round 3-8.
///
/// Shape: a LOOP over whole-segment (non-crossing) nodes — no recursion, `state` updated in place —
/// until a crossing is found. A crossing makes exactly ONE genuine recursive call, into the child on
/// `p2`'s side of the plane (`near_side`) over `[mid, p2]` with a freshly computed incoming state;
/// if that returns blocked, the whole call short-circuits blocked. Otherwise the loop continues into
/// the OTHER child (`far_side`) over `[p1<-mid, p2]` with `state` updated by the same
/// `combine_state` rule — a tail continuation, not a second recursive call (round 6's resolution of
/// the recursion shape).
///
/// `depth` bounds the total number of nodes visited across the WHOLE call tree (tail steps and
/// recursive near-calls alike), not just this frame's own tail loop — a real C-stack recursion, so
/// this is what actually keeps `line_clear` from blowing the stack on a pathological tree, not just
/// looping forever.
#[allow(clippy::too_many_arguments)]
fn seg_clear(
    model: &Model,
    mut inode: i32,
    mut p1: Vec3,
    mut p2: Vec3,
    mut state: bool,
    mut depth: u32,
    extra_flags: u8,
    seen_empty: &mut bool,
) -> bool {
    loop {
        if depth > MAX_DEPTH {
            return true; // fail-open (cosmetic, not a false shadow) on a pathological tree
        }
        if inode == -1 {
            return terminal(state, extra_flags, seen_empty);
        }
        let node = &model.nodes[inode as usize];
        let d1 = plane_dot(&node.plane, &p1);
        let d2 = plane_dot(&node.plane, &p2);

        if d1 > -WHOLE_SEGMENT_EPS && d2 > -WHOLE_SEGMENT_EPS {
            // Whole FRONT segment.
            let csg = is_csg(node, extra_flags, true);
            state = combine_state(FRONT, state, csg);
            inode = child(node, FRONT);
            depth += 1;
            continue;
        }
        if d1 < WHOLE_SEGMENT_EPS && d2 < WHOLE_SEGMENT_EPS {
            // Whole BACK segment.
            let csg = is_csg(node, extra_flags, true);
            state = combine_state(BACK, state, csg);
            inode = child(node, BACK);
            depth += 1;
            continue;
        }

        // Crossing: split at the plane. Near side + fraction key on `d2` (point2's own dot), not
        // `d1` (round 7 live re-capture, corrected from an earlier mislabeling).
        let t = d2 / (d1 - d2);
        let mid = crossing_mid(p1, p2, t);
        let near_side = if d2 > 0.0 { FRONT } else { BACK };
        let far_side = if near_side == FRONT { BACK } else { FRONT };
        let csg_nostrip = is_csg(node, extra_flags, false);

        let near_state = combine_state(near_side, state, csg_nostrip);
        if !seg_clear(model, child(node, near_side), mid, p2, near_state, depth + 1, extra_flags,
                      seen_empty) {
            return false;
        }

        state = combine_state(far_side, state, csg_nostrip);
        inode = child(node, far_side);
        p2 = mid;
        depth += 1;
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
        //
        // Round 8 (threaded `state`, see `combine_state`): a terminal's solidity now depends on
        // whether the walk has POSITIVE evidence of open space anywhere in its ancestry, not the
        // flagged node alone — matching the real UNATCO ratio (160/6314 flagged, the rest genuinely
        // solid), a ray always crosses real solid geometry before it can reach a flagged one. So
        // `NodeA` (genuinely solid) sits ahead of `NodeB` (the node under test) on the ray's path:
        // crossing NodeA's FRONT proves open space; `NodeB` must not be able to erase that by being
        // flagged, nor introduce a NEW block when it isn't.
        let node_a = BspNode {
            plane: Plane { x: 1.0, y: 0.0, z: 0.0, w: 300.0 },
            zone_mask: u64::MAX,
            node_flags: 0, // genuinely CSG-solid
            i_vert_pool: 0,
            i_surf: 0,
            i_back: 1,  // FRONT child (engine convention) -- NodeB
            i_front: -1, // BACK child -- unreached by this ray
            i_plane: -1,
            i_collision_bound: -1,
            i_render_bound: -1,
            i_zone: [0, 0],
            num_vertices: 1,
            i_leaf: [-1, -1],
        };
        let mut node_b = BspNode {
            plane: Plane { x: 0.0, y: 1.0, z: 0.0, w: 50.0 },
            zone_mask: u64::MAX,
            node_flags: 0, // baseline: also genuinely CSG-solid
            i_vert_pool: 0,
            i_surf: 0,
            i_back: -1, // FRONT child -- unreached by this ray
            i_front: -1, // BACK child -- terminal, this is where the ray ends up
            i_plane: -1,
            i_collision_bound: -1,
            i_render_bound: -1,
            i_zone: [0, 0],
            num_vertices: 1,
            i_leaf: [-1, -1],
        };
        let start = Vec3::new(400.0, 0.0, 0.0);
        let end = Vec3::new(350.0, 0.0, 0.0);
        let m = Model { nodes: vec![node_a.clone(), node_b.clone()], ..Model::default() };
        assert!(!line_clear(&m, start, end, VIS_EXTRA_FLAGS),
                "baseline: NodeB occludes when genuinely solid");
        node_b.node_flags |= NF_NOT_VIS_BLOCKING;
        let m = Model { nodes: vec![node_a, node_b], ..Model::default() };
        assert!(line_clear(&m, start, end, VIS_EXTRA_FLAGS),
                "an NF_NotVisBlocking node must not block a visibility trace, even though the ray \
                 already has positive open-space evidence from crossing NodeA");
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

    #[test]
    fn ancestor_solid_state_survives_a_non_csg_pass_through() {
        // Round 8: the real walker (`Editor.dll 0x17ce190`) THREADS an accumulating open/solid
        // state across the whole recursion (see `combine_state` in the module), not just the
        // direct parent of a terminal. Two nodes on a straight line: NodeA (x=100, genuinely
        // CSG-solid) then NodeB (x=150, flagged NF_NotCsg -- a non-occluding pass-through, e.g. a
        // portal/semisolid split). A ray from x=200 (in front of NodeA, open space) to x=-50
        // (behind NodeA, i.e. inside what NodeA calls solid) must be BLOCKED: it demonstrably
        // crosses NodeA's solid interior, and NodeB's own non-occluding classification must not
        // erase that. The pre-fix `descend`, which classifies a terminal from its DIRECT parent
        // alone, loses NodeA's verdict at NodeB's non-CSG pass-through and wrongly reports CLEAR
        // -- confirmed RED against that code before this fix, restored GREEN after. Same shape as
        // a real Wanchai mismatch this round traced end-to-end (record 14, `Light42`, v=3 u=0/1:
        // golden CLEAR, the pre-fix native bake wrongly BLOCKED there -- opposite polarity, same
        // "direct parent only" gap): `line-clear-shadow-ray-algorithm-gap-found-real`.
        let node_a = BspNode {
            plane: Plane { x: 1.0, y: 0.0, z: 0.0, w: 100.0 },
            zone_mask: u64::MAX,
            node_flags: 0, // genuinely CSG-solid
            i_vert_pool: 0,
            i_surf: 0,
            i_back: -1,  // FRONT child (engine convention) -- terminal, open space
            i_front: 1,  // BACK child -- NodeB
            i_plane: -1,
            i_collision_bound: -1,
            i_render_bound: -1,
            i_zone: [0, 0],
            num_vertices: 1,
            i_leaf: [-1, -1],
        };
        let node_b = BspNode {
            plane: Plane { x: 1.0, y: 0.0, z: 0.0, w: 150.0 },
            zone_mask: u64::MAX,
            node_flags: NF_NOT_CSG, // non-occluding pass-through
            i_vert_pool: 0,
            i_surf: 0,
            i_back: -1, // FRONT child -- unreached by this ray
            i_front: -1, // BACK child -- terminal, inherits NodeA's solid verdict
            i_plane: -1,
            i_collision_bound: -1,
            i_render_bound: -1,
            i_zone: [0, 0],
            num_vertices: 1,
            i_leaf: [-1, -1],
        };
        let m = Model { nodes: vec![node_a, node_b], ..Model::default() };
        assert!(
            !line_clear(&m, Vec3::new(200.0, 0.0, 0.0), Vec3::new(-50.0, 0.0, 0.0),
                        VIS_EXTRA_FLAGS),
            "a ray that demonstrably crosses NodeA's solid interior must stay blocked through \
             NodeB's non-CSG pass-through, not reset to clear"
        );
    }
}
