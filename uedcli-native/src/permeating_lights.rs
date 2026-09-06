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
//! ## Two things the board item flags as unverified before porting — status 2026-08-31
//!
//! 1. **Which filter result lands in `FPortal.iFrontLeaf` vs `iBackLeaf`.** Get it backwards and
//!    the `d < 0` gate inverts and every leaf set comes out empty or wrong. This port reuses
//!    `zones::collect_portals`'s existing `Portal{a: front_leaf, b: back_leaf}` convention (already
//!    load-bearing for the zone union-find, so its front/back assignment is trustworthy) and
//!    derives the flood's outward-oriented polygon per source leaf directly from it: leaving `b`
//!    toward `a` uses `+normal` (the node's own plane, which points toward the front/`a` side);
//!    leaving `a` toward `b` uses `-normal` with the polygon wound in reverse. NOT independently
//!    live-verified via a fresh `MakePortals` gdb capture — resolved instead by measurement against
//!    UNATCO's own golden: 727/762 leaves (95.4%) now match EXACTLY (order + content), including the
//!    leaf-0 reference run. A backward orientation would invert the `d<0` gate on every portal
//!    uniformly, which collapses the flood to near-nothing (the seed leaf only) rather than producing
//!    a 95%-correct, narrowly-wrong-at-the-margins result — the observed error shape (see point 2) is
//!    inconsistent with a global orientation bug and consistent with a boundary-epsilon one, so this
//!    is now trusted, though a live capture would still be stronger evidence.
//! 2. **`FPoly::SplitWithPlaneFast`** (`Engine.dll 0x10151f90`, image base `0x10000000`) — decoded by
//!    static disassembly 2026-08-31 (`pefile`+`capstone`, `dev/docs/unrealed/extracting-from-dll.md`
//!    method). It is NOT a plain per-vertex Sutherland-Hodgman clip: every vertex's signed distance to
//!    the plane is compared against `THRESH_SPLIT_POLY_WITH_PLANE = 0.25` (`.rdata` constants at RVA
//!    `0x206780`/`-0x20b580`, both extracted directly from `Engine.dll`'s bytes, not assumed), and a
//!    polygon that isn't decisively split beyond that epsilon on BOTH sides is returned WHOLE
//!    (`SP_Front`) or REJECTED WHOLE (`SP_Back`) rather than chopped to a sliver — see
//!    [`split_with_plane_fast`] for the exact port and the one still-unconfirmed branch (`SP_Coplanar`
//!    caller behavior). Before this fix, the old plain-clip `clip_beam` was measurably too permissive:
//!    on UNATCO, native's leaf runs were a strict superset of the golden's in 82/87 mismatching
//!    leaves (extra lights only, never missing, never reordered) — the exact signature of a clip that
//!    keeps slivers the real epsilon-gated function would have discarded outright. This fix closed
//!    87/762 mismatches to 35/762 (727/762 exact, was 675/762) and fully eliminated the 5-leaf
//!    under-reach case (`Light127`) that existed before it. **2026-09-06:** that epsilon was still
//!    inert, because [`clip_beam`] fed it an UNNORMALIZED plane — `FPlane(A,B,C)` normalizes
//!    (`core.dll 0xb440` -> `FVector::SafeNormal`), so `0.25` is a world-unit distance, and native
//!    was dividing it by the cross product's length. Fixed with [`safe_normal`]/[`plane_w`]/
//!    [`plane_dot`]; spike `dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/`.

use crate::fpoly::safe_normal;
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

/// `THRESH_SPLIT_POLY_WITH_PLANE`, live-extracted from `Engine.dll`'s `.rdata` (2026-08-31): the
/// two float constants `SplitWithPlaneFast` (`0x10151f90`) compares each vertex's signed plane
/// distance against are `+0.25`/`-0.25` at RVA `0x206780`/`0x20b580`. See [`split_with_plane_fast`].
const THRESH_SPLIT_POLY_WITH_PLANE: f32 = 0.25;

/// The editor stops clipping once the working poly reaches 14 vertices
/// (`Editor.dll 0x100a7083 cmp eax, 0xe / jge`), checked BEFORE each edge -- it keeps the poly it
/// has and recurses with it, it does not truncate.
const MAX_CLIP_VERTS: usize = 14;

/// `FPlane(A, B, C)`'s `W` (`core.dll 0x1000b440`): `A | Normal`, summed as
/// `(A.y*N.y + A.x*N.x) + A.z*N.z` (`0x1000b4e3`/`0x1000b4f1`/`0x1000b4fe`/`0x1000b50b`).
fn plane_w(a: &Vec3, normal: &Vec3) -> f32 {
    (a.y * normal.y + a.x * normal.x) + a.z * normal.z
}

/// `FPlane::PlaneDot` (`core.dll 0x10024e60`): a SIMD horizontal add of
/// `(x*Nx, y*Ny, z*Nz, -W)` that pairs the terms as `(x*Nx + y*Ny) + (z*Nz - W)`.
fn plane_dot(normal: &Vec3, w: f32, v: &Vec3) -> f32 {
    (v.x * normal.x + v.y * normal.y) + (v.z * normal.z - w)
}

/// Clip `target` against the beam formed by `light` and each edge of `clip`: for edge
/// `(clip[jPrev], clip[j])`, the editor builds `FPlane(Light, clip[j], clip[jPrev])`
/// (`Editor.dll 0x100a70b7`-`0x100a7146`; the ctor's args land Location-first, see [`plane_w`]) and
/// keeps the front half. The plane is **normalized** — that is what makes `SplitWithPlaneFast`'s
/// `0.25` a real 0.25-world-unit epsilon rather than an effectively-zero one.
///
/// The one deliberate departure is the ORIENTATION. The editor inherits it from its portal poly's
/// vertex winding; `leaf_portal_map` re-winds the reverse direction of every `zones::Portal`, so the
/// plane is oriented explicitly instead: flip it when `clip`'s own remaining (convex) vertices fall
/// on the negative side, which reproduces the editor's "keep the beam interior" for either winding.
fn clip_beam(light: &Vec3, clip: &[Vec3], target: &[Vec3]) -> Option<Vec<Vec3>> {
    let mut poly = target.to_vec();
    let n = clip.len();
    for j in 0..n {
        if poly.len() >= MAX_CLIP_VERTS {
            break;
        }
        let a = clip[(j + n - 1) % n];
        let b = clip[j];
        let Some(mut normal) = safe_normal(&(b.sub(light)).cross(&(a.sub(light)))) else {
            continue; // degenerate edge (through the light or zero-length): no constraint
        };
        let mut sign_sum = 0.0f32;
        for &v in clip {
            sign_sum += normal.dot(&v.sub(light));
        }
        if sign_sum < 0.0 {
            normal = Vec3::new(-normal.x, -normal.y, -normal.z);
        }
        poly = split_with_plane_fast(&poly, &normal, plane_w(light, &normal))?;
    }
    if poly.len() >= 3 {
        Some(poly)
    } else {
        None
    }
}

/// Port of `FPoly::SplitWithPlaneFast` (`Engine.dll 0x10151f90`, disassembled 2026-08-31, image
/// base `0x10000000`), specialized to this caller's use (keep the front/kept half of `poly` for the
/// half-space `PlaneDot(v) >= 0`; the real function also produces a back-half output, unused here).
///
/// The real function is NOT a plain per-vertex Sutherland-Hodgman clip: it first classifies every
/// vertex by the SIGN of its signed distance (`>= 0.0` exactly, no epsilon, ties go to front — the
/// `jb` branch at `0x10152021` only fires on strictly-negative), but only calls it decisively
/// "positive" (`0x1015202f`/`0x10152036`, sets a `Positive` flag) if that distance exceeds
/// `+THRESH_SPLIT_POLY_WITH_PLANE` (`0.25`, `.rdata` RVA `0x206780`), and decisively "negative" (sets
/// `Negative`, `0x10152051`/`0x10152059`) only past `-0.25` (RVA `0x20b580`). Only when BOTH flags
/// are set does it build a clipped polygon at all (`0x101520ab` on): otherwise it returns the WHOLE
/// input polygon unclipped if the front side isn't empty (`SP_Front`, `!negative`), or discards it
/// entirely if the front side IS empty (`SP_Back`, `!positive`) — verified via the flag-check block
/// at `0x10152070`-`0x101520a2` (`eax=2`/`SP_Back` when `!positive && negative`, `eax=ebx+1=1`/
/// `SP_Front` when `!negative`). A poly with every vertex inside the epsilon band of the plane
/// (`SP_Coplanar`, neither flag set) is treated here as kept-whole — the real caller's `ActorVisibility`
/// (`Editor.dll`, not yet disassembled for this call site) may differ; the one remaining unconfirmed
/// branch of the two the board item flagged.
fn split_with_plane_fast(poly: &[Vec3], normal: &Vec3, w: f32) -> Option<Vec<Vec3>> {
    let n = poly.len();
    if n == 0 {
        return None;
    }
    let dots: Vec<f32> = poly.iter().map(|v| plane_dot(normal, w, v)).collect();
    let positive = dots.iter().any(|&d| d > THRESH_SPLIT_POLY_WITH_PLANE);
    let negative = dots.iter().any(|&d| d < -THRESH_SPLIT_POLY_WITH_PLANE);
    if !negative {
        return Some(poly.to_vec()); // SP_Front (or SP_Coplanar) -- kept whole, unclipped.
    }
    if !positive {
        return None; // SP_Back -- rejected entirely.
    }
    // SP_Split: real per-edge clip. Ties at exactly 0.0 go to the front/kept bucket.
    let mut out = Vec::with_capacity(n + 1);
    for i in 0..n {
        let cur = poly[i];
        let prev = poly[(i + n - 1) % n];
        let (ds, dp) = (dots[i], dots[(i + n - 1) % n]);
        let (cur_front, prev_front) = (ds >= 0.0, dp >= 0.0);
        if cur_front != prev_front {
            let t = dp / (dp - ds);
            out.push(Vec3::new(
                prev.x + t * (cur.x - prev.x),
                prev.y + t * (cur.y - prev.y),
                prev.z + t * (cur.z - prev.z),
            ));
        }
        if cur_front {
            out.push(cur);
        }
    }
    if out.len() >= 3 {
        Some(out)
    } else {
        None
    }
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

    /// A 100-unit-square beam at `z = 100` seen from a light at the origin.
    fn beam_clip_poly() -> Vec<Vec3> {
        vec![
            Vec3::new(-100.0, -100.0, 100.0),
            Vec3::new(100.0, -100.0, 100.0),
            Vec3::new(100.0, 100.0, 100.0),
            Vec3::new(-100.0, 100.0, 100.0),
        ]
    }

    // The beam plane must be NORMALIZED (`FPlane(A,B,C)` runs `SafeNormal`), or
    // `SplitWithPlaneFast`'s +/-0.25 epsilon is divided by the cross product's length -- order 1e4
    // for room-scale geometry -- and stops gating anything. This target sits 0.1 units INSIDE the
    // beam's left plane at its near edge and 10 units outside at its far edge: with the epsilon
    // alive nothing is decisively positive, so the whole poly is `SP_Back` and the flood stops. An
    // unnormalized plane calls both ends decisive, splits, and carries a sliver onward -- which is
    // exactly how native reached leaves UED22 leaves dark.
    #[test]
    fn clip_beam_rejects_a_poly_that_only_grazes_the_beam() {
        let light = Vec3::new(0.0, 0.0, 0.0);
        // Left beam plane: 0.7071*(x + z) -- 0.1 at x = -199.859, -10 at x = -214.142 (z = 200).
        let target = vec![
            Vec3::new(-199.859, -50.0, 200.0),
            Vec3::new(-199.859, 50.0, 200.0),
            Vec3::new(-214.142, 50.0, 200.0),
            Vec3::new(-214.142, -50.0, 200.0),
        ];
        assert_eq!(clip_beam(&light, &beam_clip_poly(), &target), None);
    }

    #[test]
    fn clip_beam_keeps_a_poly_well_inside_the_beam() {
        let light = Vec3::new(0.0, 0.0, 0.0);
        let target = vec![
            Vec3::new(-50.0, -50.0, 200.0),
            Vec3::new(-50.0, 50.0, 200.0),
            Vec3::new(50.0, 50.0, 200.0),
            Vec3::new(50.0, -50.0, 200.0),
        ];
        assert_eq!(clip_beam(&light, &beam_clip_poly(), &target), Some(target));
    }

    // `split_with_plane_fast` regression tests. Before the 2026-08-31 fix, `clip_beam` used a plain
    // Sutherland-Hodgman half-space clip (kept side = `dot >= 0.0`, no epsilon) in place of the real
    // `FPoly::SplitWithPlaneFast` (`Engine.dll 0x10151f90`). Measured against a UNATCO golden, that
    // made native's per-leaf light runs a strict superset of the editor's in 82/87 mismatching
    // leaves — over-permissive, never missing. This case is the mechanism: a polygon with two
    // vertices weakly on the "kept" side (never past `+0.25`) and two decisively on the other side
    // (well past `-0.25`). A plain clip keeps a thin sliver (interpolated crossing points plus the
    // two weak vertices); the real function sees no vertex past `+0.25` (`positive` stays false)
    // while `negative` is true, classifies the WHOLE polygon `SP_Back`, and rejects it outright.
    #[test]
    fn split_with_plane_fast_rejects_a_weakly_kept_poly_wholesale() {
        let normal = Vec3::new(1.0, 0.0, 0.0);
        // dot(v) = v.x here (origin at 0, normal = +X): 0.1 (kept, but < 0.25) / -10.0 (rejected,
        // well past -0.25).
        let poly = vec![
            Vec3::new(0.1, -10.0, 0.0),
            Vec3::new(0.1, 10.0, 0.0),
            Vec3::new(-10.0, 10.0, 0.0),
            Vec3::new(-10.0, -10.0, 0.0),
        ];
        // A plain Sutherland-Hodgman clip would return Some(4 points) here (2 kept + 2 interpolated).
        assert_eq!(split_with_plane_fast(&poly, &normal, 0.0), None);
    }

    #[test]
    fn split_with_plane_fast_keeps_a_decisively_positive_poly_whole() {
        // No vertex past -0.25 (`negative` stays false) -- SP_Front: returned UNCLIPPED, even
        // though the plane technically passes near two vertices' epsilon band.
        let normal = Vec3::new(1.0, 0.0, 0.0);
        let poly = vec![
            Vec3::new(10.0, -10.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.1, 10.0, 0.0),
            Vec3::new(0.1, -10.0, 0.0),
        ];
        assert_eq!(split_with_plane_fast(&poly, &normal, 0.0), Some(poly));
    }

    #[test]
    fn split_with_plane_fast_clips_a_decisively_split_poly_normally() {
        // Both sides decisively past the epsilon -- behaves like a normal half-space clip.
        let normal = Vec3::new(1.0, 0.0, 0.0);
        let poly = vec![
            Vec3::new(10.0, -10.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(-10.0, 10.0, 0.0),
            Vec3::new(-10.0, -10.0, 0.0),
        ];
        let out = split_with_plane_fast(&poly, &normal, 0.0).unwrap();
        assert_eq!(out.len(), 4, "2 kept corners + 2 interpolated crossing points");
        for v in &out {
            assert!(v.x >= -1e-4, "every kept vertex must be on the front side: {v:?}");
        }
    }

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
            orientation: 1,
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
