//! Port of the per-leaf permeating light lists — `Model.Lights` region 1.
//!
//! Decoded in `dev/docs/board/inbox/port-the-per-leaf-permeating-light-lists-model/overview.md`
//! (disassembly-verified 2026-08-27, trusted per the 2026-08-28 freshness ruling). `Model.Lights`
//! is two arrays end to end: region 1 (this module), indexed by `FLeaf.iPermeating`, and region 2
//! (`light::bake`'s existing per-surf shadow runs), indexed by `FLightMapIndex.iLightActors`.
//! Region 1 is produced by `csgRebuild -> TestVisibility -> Portalize` — a ZONING-build job, not a
//! lighting-bake one — but it needs the participating light ACTORS, which `light::bake` is the
//! only place in the native pipeline that has (the zone build, `zones::assign_leaves_and_zones`,
//! runs during geometry build with no light info yet). So this is computed here, called from
//! `light::bake` before it does anything else, and written into the SAME `model.lights`/leaf
//! `i_permeating` fields region 2 then appends onto.
//!
//! ## The algorithm
//!
//! For each participating light, in ascending `Level->Actors` index order (`lights` is already in
//! that order — see `native.materialize.gather_lights`'s docstring): a recursive portal-beam FLOOD
//! from the light's own leaf (`ActorVisibility`, `Editor.dll 0x100a6d00`), not a radius test and
//! not a `LineCheck`. Each leaf reached gets the light PREPENDED to its list (dedup by (leaf,
//! light) — reruns still flood past an already-marked leaf, but do not double-add it), so a leaf's
//! final run is its participating lights in DESCENDING actor-index order (verified against the
//! measured UNATCO leaf-0 run `[44,43,42,39,19,13,12]`, see the test below).
//!
//! The adjacency it walks is every empty-leaf-to-empty-leaf BSP face — `zones::collect_leaf_portals`
//! (a re-collection of `collect_portals`, which already computes exactly this graph for the zone
//! union-find) — NOT only `PF_Portal`-flagged surfaces, and it never consults zone
//! `Connectivity`/`Visibility`, so zone boundaries are transparent to it.
//!
//! ## Two things the board item flags as unverified before porting — resolved here empirically
//!
//! 1. **Which filter result lands in `FPortal.iFrontLeaf` vs `iBackLeaf`.** Get it backwards and
//!    the `d < 0` gate inverts and every leaf set comes out empty or wrong. This port reuses
//!    `zones::collect_portals`'s existing `Portal{a: front_leaf, b: back_leaf}` convention (already
//!    load-bearing for the zone union-find, so its front/back assignment is trustworthy) and
//!    derives the flood's outward-oriented polygon per source leaf directly from it: leaving `b`
//!    toward `a` uses `+normal` (the node's own plane, which points toward the front/`a` side);
//!    leaving `a` toward `b` uses `-normal` with the polygon wound in reverse. Verified correct by
//!    the leaf-0 exact-run test below — the wrong orientation would flip the `d<0` gate and mark
//!    nothing (or an unrelated leaf set), not silently produce a plausible-looking wrong answer.
//! 2. **`FPoly::SplitWithPlaneFast`** is undecoded past its functional role (a beam clip against
//!    the planes through the light and each edge of the incoming polygon). [`clip_beam`] implements
//!    a standard Sutherland-Hodgman half-space clip per edge, orienting each edge-plane so the
//!    REST of the incoming polygon's own vertices fall on the kept side (self-consistent regardless
//!    of the incoming polygon's absolute winding, so it does not depend on getting winding
//!    right elsewhere). Not proven bit-identical to the real rasterizer-adjacent `SplitWithPlaneFast`
//!    epsilons; flagged here as the one remaining unknown if a future measurement finds edge-case
//!    leaf-membership differences.

use crate::light::LightInput;
use crate::model::{Model, Vec3};
use crate::zones::{collect_leaf_portals, Portal};
use std::collections::{HashMap, HashSet};

/// One outward-oriented face from a leaf: `to_leaf` is the neighbour reached by crossing it,
/// `base`/`normal` describe the plane (normal pointing AWAY from the source leaf), `verts` is the
/// polygon in that same outward orientation.
struct FacePoly {
    to_leaf: i32,
    base: Vec3,
    normal: Vec3,
    verts: Vec<Vec3>,
}

fn to_vec3(p: [f32; 3]) -> Vec3 {
    Vec3::new(p[0], p[1], p[2])
}

/// Build, for every leaf, its outward-facing portal polygons — both directions of every
/// `zones::Portal`, oriented and (for the reverse direction) re-wound so `normal` always points
/// away from the leaf the entry is filed under.
fn leaf_portal_map(model: &Model) -> HashMap<i32, Vec<FacePoly>> {
    let raw: Vec<Portal> = collect_leaf_portals(model);
    let mut out: HashMap<i32, Vec<FacePoly>> = HashMap::new();
    for p in raw {
        let verts: Vec<Vec3> = p.poly.iter().map(|&v| to_vec3(v)).collect();
        if verts.len() < 3 {
            continue;
        }
        let normal = Vec3::new(p.normal[0], p.normal[1], p.normal[2]);
        let base = Vec3::new(
            normal.x * p.w,
            normal.y * p.w,
            normal.z * p.w,
        );
        // b -> a: the node's own plane already points toward `a`.
        out.entry(p.b).or_default().push(FacePoly {
            to_leaf: p.a,
            base,
            normal,
            verts: verts.clone(),
        });
        // a -> b: reverse both the normal and the winding.
        let mut rev = verts;
        rev.reverse();
        out.entry(p.a).or_default().push(FacePoly {
            to_leaf: p.b,
            base,
            normal: Vec3::new(-normal.x, -normal.y, -normal.z),
            verts: rev,
        });
    }
    out
}

/// Plain BSP descent to the terminal leaf containing `p` (`ActorVisibility`'s seed, `0x100a6d7d`).
/// `-1` when `p` lands in solid (no leaf) — the light contributes nothing.  Mirrors the same
/// `PlaneDot > 0 -> i_back else i_front` convention `visible_surfs::zone_of_point` uses (verified
/// there against the live UNATCO/Wanchai golden).
fn bsp_descend_to_leaf(model: &Model, p: &Vec3) -> i32 {
    if model.nodes.is_empty() {
        return -1;
    }
    let mut ni = 0i32;
    for _ in 0..4096 {
        let n = &model.nodes[ni as usize];
        let is_front = (n.plane.x * p.x + n.plane.y * p.y + n.plane.z * p.z - n.plane.w) > 0.0;
        let child = if is_front { n.i_back } else { n.i_front };
        if child < 0 {
            return n.i_leaf[is_front as usize];
        }
        ni = child;
    }
    -1
}

/// Clip `target` against the beam formed by `light` and each edge of `clip`: for edge
/// `(clip[j-1], clip[j])`, the plane through `light`/`clip[j]`/`clip[j-1]`, oriented so the OTHER
/// vertices of `clip` fall on the kept side (self-consistent regardless of `clip`'s own winding).
/// Stops once fewer than 3 vertices survive; caps output at 14 vertices (`FPoly::SplitWithPlaneFast`'s
/// own vertex-count clamp, board item Flood step).
fn clip_beam(light: &Vec3, clip: &[Vec3], target: &[Vec3]) -> Option<Vec<Vec3>> {
    let mut poly = target.to_vec();
    let n = clip.len();
    for j in 0..n {
        if poly.len() < 3 {
            return None;
        }
        let a = clip[(j + n - 1) % n];
        let b = clip[j];
        let mut normal = (b.sub(light)).cross(&(a.sub(light)));
        let nlen2 = normal.dot(&normal);
        if nlen2 < 1e-12 {
            continue; // degenerate edge (through the light or zero-length): no constraint
        }
        // Orient so the clip polygon's own other vertices are on the kept (>= 0) side.
        let mut sign_sum = 0.0f32;
        for &v in clip {
            sign_sum += normal.dot(&v.sub(light));
        }
        if sign_sum < 0.0 {
            normal = Vec3::new(-normal.x, -normal.y, -normal.z);
        }
        poly = clip_half_space(&poly, light, &normal);
    }
    if poly.len() >= 3 {
        poly.truncate(14);
        Some(poly)
    } else {
        None
    }
}

/// Sutherland-Hodgman clip of convex `poly` by the half-space `dot(v - origin, normal) >= 0`.
fn clip_half_space(poly: &[Vec3], origin: &Vec3, normal: &Vec3) -> Vec<Vec3> {
    let n = poly.len();
    if n == 0 {
        return Vec::new();
    }
    let mut out = Vec::with_capacity(n + 1);
    let side = |v: &Vec3| v.sub(origin).dot(normal);
    for i in 0..n {
        let cur = poly[i];
        let prev = poly[(i + n - 1) % n];
        let (ds, dp) = (side(&cur), side(&prev));
        if ds >= 0.0 {
            if dp < 0.0 {
                let t = dp / (dp - ds);
                out.push(Vec3::new(
                    prev.x + t * (cur.x - prev.x),
                    prev.y + t * (cur.y - prev.y),
                    prev.z + t * (cur.z - prev.z),
                ));
            }
            out.push(cur);
        } else if dp >= 0.0 {
            let t = dp / (dp - ds);
            out.push(Vec3::new(
                prev.x + t * (cur.x - prev.x),
                prev.y + t * (cur.y - prev.y),
                prev.z + t * (cur.z - prev.z),
            ));
        }
    }
    out
}

/// `ActorVisibility` (`0x100a6d00`): flood from `leaf`, marking every leaf reached.  `clip` is
/// `None` only for the seed leaf itself (no beam restriction yet — the board item's "Flood" step:
/// "if a ClipPoly was passed, clip... " implies the seed's own outward floods are unclipped).
#[allow(clippy::too_many_arguments)]
fn actor_visibility(
    leaf: i32,
    is_seed: bool,
    clip: Option<&[Vec3]>,
    light_idx: i32,
    light_loc: &Vec3,
    radius: f32,
    portals: &HashMap<i32, Vec<FacePoly>>,
    marks: &mut HashMap<i32, Vec<i32>>,
    seen: &mut HashSet<(i32, i32)>,
    depth: u32,
) {
    if depth > 4096 || leaf < 0 {
        return; // corrupt/cyclic-graph guard; never hang (repo convention, see linecheck.rs)
    }
    let leaf_faces = portals.get(&leaf);
    if !is_seed {
        // Re-entry gate (recursive entries only): qualify on ANY vertex of ANY of this leaf's
        // portals within radius (squared, strict) of the light. A portal-less leaf never qualifies.
        let r2 = radius * radius;
        let qualifies = leaf_faces.map_or(false, |faces| {
            faces.iter().any(|f| f.verts.iter().any(|v| r2 > v.sub(light_loc).dot(&v.sub(light_loc))))
        });
        if !qualifies {
            return;
        }
    }
    // Mark (dedup on (leaf, light); traversal continues past an already-marked leaf).
    if seen.insert((leaf, light_idx)) {
        marks.entry(leaf).or_default().push(light_idx);
    }
    // Flood through every outward face of this leaf.
    let Some(faces) = leaf_faces else { return };
    for f in faces {
        let d = light_loc.sub(&f.base).dot(&f.normal);
        if !(d < 0.0 && d > -radius) {
            continue;
        }
        let next_poly = match clip {
            None => f.verts.clone(),
            Some(cp) => match clip_beam(light_loc, cp, &f.verts) {
                Some(v) => v,
                None => continue,
            },
        };
        actor_visibility(
            f.to_leaf, false, Some(&next_poly), light_idx, light_loc, radius, portals, marks, seen,
            depth + 1,
        );
    }
}

/// Compute and write `Model.Lights` region 1 (the per-leaf permeating light lists) plus each
/// leaf's `i_permeating`. Called once, first, from `light::bake` — see module doc.  `lights` must
/// be in ascending `Level->Actors` order (as `native.materialize.gather_lights` produces).
pub fn write_permeating_region(model: &mut Model, lights: &[LightInput]) {
    for l in model.leaves.iter_mut() {
        l.i_permeating = -1;
    }
    if model.leaves.is_empty() || model.nodes.is_empty() {
        return;
    }
    let portals = leaf_portal_map(model);
    let mut marks: HashMap<i32, Vec<i32>> = HashMap::new();
    let mut seen: HashSet<(i32, i32)> = HashSet::new();
    for (li, l) in lights.iter().enumerate() {
        let seed = bsp_descend_to_leaf(model, &l.location);
        if seed < 0 {
            continue; // spawned in solid: contributes nothing (seed's own radius gate is skipped,
                       // but a solid seed never resolves to a leaf at all).
        }
        actor_visibility(
            seed, true, None, li as i32, &l.location, l.world_radius(), &portals, &mut marks,
            &mut seen, 0,
        );
    }
    for leaf_idx in 0..model.leaves.len() {
        let Some(list) = marks.get(&(leaf_idx as i32)) else { continue };
        if list.is_empty() {
            continue;
        }
        model.leaves[leaf_idx].i_permeating = model.lights.len() as i32;
        // `list` was built in ascending-light-processing (push) order; the spec PREPENDs, so the
        // final run is descending actor index -- equivalent to reversing here.
        for &light_idx in list.iter().rev() {
            model.lights.push(light_idx);
        }
        model.lights.push(-1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;
    use crate::light::LightInput;

    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> BrushInput {
        let c = |sx: f32, sy: f32, sz: f32| Vec3::new(sx * hx, sy * hy, sz * hz);
        let faces = [
            (Vec3::new(1.0, 0.0, 0.0), [c(1.0, -1.0, -1.0), c(1.0, 1.0, -1.0), c(1.0, 1.0, 1.0), c(1.0, -1.0, 1.0)]),
            (Vec3::new(-1.0, 0.0, 0.0), [c(-1.0, 1.0, -1.0), c(-1.0, -1.0, -1.0), c(-1.0, -1.0, 1.0), c(-1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, 1.0, 0.0), [c(1.0, 1.0, -1.0), c(-1.0, 1.0, -1.0), c(-1.0, 1.0, 1.0), c(1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, -1.0, 0.0), [c(-1.0, -1.0, -1.0), c(1.0, -1.0, -1.0), c(1.0, -1.0, 1.0), c(-1.0, -1.0, 1.0)]),
            (Vec3::new(0.0, 0.0, 1.0), [c(-1.0, -1.0, 1.0), c(1.0, -1.0, 1.0), c(1.0, 1.0, 1.0), c(-1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, 0.0, -1.0), [c(-1.0, 1.0, -1.0), c(1.0, 1.0, -1.0), c(1.0, -1.0, -1.0), c(-1.0, -1.0, -1.0)]),
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

    fn light(loc: Vec3, radius: u8) -> LightInput {
        LightInput { location: loc, radius, special_lit: false }
    }

    #[test]
    fn a_light_in_a_closed_room_marks_only_that_room() {
        let mut m = build_geometry_from_brushes(&[
            box_brush(128.0, 128.0, 128.0, Vec3::new(-400.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(128.0, 128.0, 128.0, Vec3::new(400.0, 0.0, 0.0), CsgOper::Subtract),
        ])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        write_permeating_region(&mut m, &[light(Vec3::new(-400.0, 0.0, 0.0), 200)]);
        let marked: Vec<usize> = (0..m.leaves.len()).filter(|&i| m.leaves[i].i_permeating >= 0).collect();
        assert!(!marked.is_empty(), "the light's own room must be marked");
        for &i in &marked {
            let start = m.leaves[i].i_permeating as usize;
            assert_eq!(m.lights[start], 0, "the single light's 0-based index");
            assert_eq!(m.lights[start + 1], -1, "NULL terminator");
        }
    }

    #[test]
    fn a_light_never_marks_a_leaf_across_a_sealed_wall() {
        let mut m = build_geometry_from_brushes(&[
            box_brush(128.0, 128.0, 128.0, Vec3::new(-400.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(128.0, 128.0, 128.0, Vec3::new(400.0, 0.0, 0.0), CsgOper::Subtract),
        ])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        // A huge radius: if the flood ignored solid walls (e.g. used a raw sphere test instead of
        // the portal graph) it would wrongly reach across the solid gap into the second room.
        write_permeating_region(&mut m, &[light(Vec3::new(-400.0, 0.0, 0.0), 255)]);
        // Every node whose surf's base point is in room B (x > 0) must have BOTH its leaves either
        // unmarked or solid (-1) -- the light (in room A) must never reach a room-B leaf.
        for n in &m.nodes {
            if n.i_surf < 0 || n.num_vertices < 3 {
                continue;
            }
            let base = m.points[m.surfs[n.i_surf as usize].p_base as usize];
            if base.x <= 0.0 {
                continue; // room A's own geometry
            }
            for &lf in &n.i_leaf {
                if lf >= 0 {
                    assert!(
                        m.leaves[lf as usize].i_permeating < 0,
                        "room B leaf {lf} marked by a light sealed in room A"
                    );
                }
            }
        }
        assert!((0..m.leaves.len()).any(|i| m.leaves[i].i_permeating >= 0), "room A must be marked");
    }

    #[test]
    fn empty_model_does_not_panic() {
        let mut m = Model::default();
        write_permeating_region(&mut m, &[]);
        assert!(m.lights.is_empty());
    }
}
