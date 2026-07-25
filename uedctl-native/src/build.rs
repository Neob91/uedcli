//! CSG/BSP build (§6): pooling (`bspAddVector`/`bspAddPoint`), `bspAddNode`, the
//! `FindBestSplit`/`SplitPolyList`/`bspBuild` partition, and the brush-list driver that runs
//! the CSG leaf-filter (`csg::bsp_brush_csg`) per brush then emits the final `Model`.
//!
//! The fresh world is SOLID (`root_outside=false`, engine `UModel::RootOutside`): a Subtract
//! carves a room out of solid space, an Add fills — confirmed by the editor golden (a single
//! Subtract yields 6 inward-facing walls; §6 gate 3 fixtures).

use crate::csg::{self, CsgOper};
use crate::fpoly::{
    FPoly, Split, MAX_VERTICES, THRESH_POINTS_ARE_SAME, THRESH_SPLIT_POLY_WITH_PLANE,
};
use crate::model::{BspLeaf, BspNode, BspSurf, BspVert, BuildError, Model, Plane, Vec3};
use crate::passes;
use rayon::prelude::*;

const THRESH_NORMALS_ARE_SAME: f32 = 2.0e-5;
const THRESH_POINTS_ARE_NEAR: f32 = 0.015;
const NF_IS_NEW: u8 = 0x20;
/// Transient marker for a synthetic solid-bound node inserted by `bound_leaked_solid_leaves`.
/// Not a real engine NodeFlag on disk — `finalize_leaves_and_bbox` clears it after `zones` reads it.
pub const NF_SOLID_BOUND: u8 = 0x40;
// MAP REBUILD partition params (§6.1, byte-verified): Balance=50, PortalBias=70, OPTIMAL.
const BALANCE: i32 = 50;
const PORTAL_BIAS: i32 = 70;
const MAX_DEPTH: usize = 4096;

// ENodePlace
const NODE_BACK: i32 = 0;
const NODE_FRONT: i32 = 1;
const NODE_PLANE: i32 = 2;
const NODE_ROOT: i32 = 3;

// --- pooling (§6.4) --------------------------------------------------------

/// `bspAddPoint` — dedup a vertex/base point into `Points`.  `exact` uses the tight
/// `THRESH_POINTS_ARE_SAME` (0.002); non-exact the looser `THRESH_POINTS_ARE_NEAR` (0.015).
fn bsp_add_point(model: &mut Model, v: Vec3, exact: bool) -> i32 {
    let tol = if exact {
        THRESH_POINTS_ARE_SAME
    } else {
        THRESH_POINTS_ARE_NEAR
    };
    for (i, p) in model.points.iter().enumerate() {
        if v.sub(p).size() < tol {
            return i as i32;
        }
    }
    model.points.push(v);
    (model.points.len() - 1) as i32
}

/// `bspAddVector` — dedup a normal/texture axis into `Vectors`.  `exact` uses
/// `THRESH_NORMALS_ARE_SAME` (2e-5); non-exact a looser tolerance for texture vectors.
fn bsp_add_vector(model: &mut Model, v: Vec3, exact: bool) -> i32 {
    let tol = if exact {
        THRESH_NORMALS_ARE_SAME
    } else {
        0.001
    };
    for (i, p) in model.vectors.iter().enumerate() {
        if v.sub(p).size() < tol {
            return i as i32;
        }
    }
    model.vectors.push(v);
    (model.vectors.len() - 1) as i32
}

/// Derive `NodeFlags` from a surf's PolyFlags (§5).
fn derive_nf(pf: u32, base: u8) -> u8 {
    let mut nf = base;
    if pf & 0x08 != 0 {
        nf |= 1; // PF_NotSolid -> NF_NotCsg
    }
    if pf & 0x0400_0001 != 0 {
        nf |= 4; // PF_Portal | PF_Invisible
    }
    if pf & 0x02 != 0 {
        nf |= 2;
    }
    if pf & 0x1002_0000 != 0 {
        nf |= 2;
    }
    nf
}

// --- bspAddNode (§6.4) -----------------------------------------------------

/// `bspAddNode` — emit a node (and, on demand, a shared surf + pooled verts) for `edpoly`,
/// linked under `i_parent` per `place`.  Handles the coplanar-chain walk and the >16-vert
/// storage split.  Returns the new node index.
fn bsp_add_node(
    model: &mut Model,
    mut i_parent: i32,
    place: i32,
    node_flags: u8,
    edpoly: &FPoly,
) -> i32 {
    // NODE_PLANE: walk to the end of the parent's coplanar chain.
    let mut place = place;
    if place == NODE_PLANE {
        let mut i = i_parent;
        while model.nodes[i as usize].i_plane != -1 {
            i = model.nodes[i as usize].i_plane;
        }
        i_parent = i;
    }

    // >16 verts: split for storage (A = first 16, B = verts[14..], sharing 2 verts).
    if edpoly.verts.len() > MAX_VERTICES {
        let mut a = edpoly.clone();
        a.verts = edpoly.verts[..MAX_VERTICES].to_vec();
        let mut b = edpoly.clone();
        b.verts = edpoly.verts[MAX_VERTICES - 2..].to_vec();
        let i = bsp_add_node(model, i_parent, place, node_flags, &a);
        bsp_add_node(model, i, NODE_PLANE, node_flags, &b);
        return i;
    }

    let i_node = model.nodes.len() as i32;

    // Surf sharing: allocate a new surf unless iLink points at an existing one.
    let i_surf = if edpoly.i_link < 0 || edpoly.i_link as usize >= model.surfs.len() {
        alloc_surf(model, edpoly)
    } else {
        edpoly.i_link
    };

    let surf_pf = model.surfs[i_surf as usize].poly_flags;
    let nf = derive_nf(surf_pf, node_flags);

    let i_vert_pool = model.verts.len() as i32;
    let verts: Vec<Vec3> = edpoly.verts.clone();
    for v in &verts {
        let iv = bsp_add_point(model, *v, true);
        model.verts.push(BspVert {
            i_vertex: iv,
            i_side: -1,
        });
    }

    let w = edpoly.base.dot(&edpoly.normal);
    let mut node = BspNode::leaf(
        Plane {
            x: edpoly.normal.x,
            y: edpoly.normal.y,
            z: edpoly.normal.z,
            w,
        },
        i_surf,
        i_vert_pool,
        edpoly.verts.len() as i32,
    );
    node.node_flags = nf;
    model.nodes.push(node);

    match place {
        NODE_BACK => model.nodes[i_parent as usize].i_back = i_node,
        NODE_FRONT => model.nodes[i_parent as usize].i_front = i_node,
        NODE_PLANE => model.nodes[i_parent as usize].i_plane = i_node,
        _ => {} // NODE_ROOT: no parent
    }
    i_node
}

// --- AABB fast-path for splitter classification (behavior-preserving) ------

/// A poly's world-space axis-aligned bounding box (min, max over its vertices).
fn poly_aabb(p: &FPoly) -> (Vec3, Vec3) {
    let mut mn = Vec3::new(f32::INFINITY, f32::INFINITY, f32::INFINITY);
    let mut mx = Vec3::new(f32::NEG_INFINITY, f32::NEG_INFINITY, f32::NEG_INFINITY);
    for v in &p.verts {
        mn = Vec3::new(mn.x.min(v.x), mn.y.min(v.y), mn.z.min(v.z));
        mx = Vec3::new(mx.x.max(v.x), mx.y.max(v.y), mx.z.max(v.z));
    }
    (mn, mx)
}

/// FP-safety guard for the AABB fast-path: the two arithmetic paths (this box-projection vs
/// `split_with_plane`'s per-vertex dot) can disagree by a few hundredths of a uu at world scale
/// (coords up to ~32768, f32 ~7 digits => ~0.01 per term).  We only take the fast path when the
/// box clears the ±`t` band by this guard, so the category we return is provably the one
/// `split_with_plane` would compute.  The fast path is purely an optimization — a poly inside the
/// guard band falls through to the exact `split_with_plane` — so the guard's size affects only how
/// often we skip the expensive call, NEVER the result.
const AABB_GUARD: f32 = 0.25;

/// Classify poly `(bmin,bmax)` against candidate plane `(base,normal)` using ONLY the poly's AABB.
/// Returns `Some(Front|Back|Coplanar)` when the box alone proves the category `split_with_plane`
/// (threshold `t`) would return, else `None` (the box straddles the band — caller must do the exact
/// per-vertex `split_with_plane`).  `normal` need not be unit; the same non-unit `normal` feeds
/// `split_with_plane`, so the projection is on the identical scale.
#[inline]
fn aabb_side(bmin: &Vec3, bmax: &Vec3, base: &Vec3, normal: &Vec3, t: f32) -> Option<Split> {
    let d0 = base.dot(normal);
    // proj range of (v - base)·normal over the box: pick the box corner extremising each axis term.
    let (xl, xh) = if normal.x >= 0.0 {
        (bmin.x * normal.x, bmax.x * normal.x)
    } else {
        (bmax.x * normal.x, bmin.x * normal.x)
    };
    let (yl, yh) = if normal.y >= 0.0 {
        (bmin.y * normal.y, bmax.y * normal.y)
    } else {
        (bmax.y * normal.y, bmin.y * normal.y)
    };
    let (zl, zh) = if normal.z >= 0.0 {
        (bmin.z * normal.z, bmax.z * normal.z)
    } else {
        (bmax.z * normal.z, bmin.z * normal.z)
    };
    let proj_min = xl + yl + zl - d0;
    let proj_max = xh + yh + zh - d0;
    if proj_min >= t + AABB_GUARD {
        Some(Split::Front)
    } else if proj_max <= -t - AABB_GUARD {
        Some(Split::Back)
    } else if proj_max < t - AABB_GUARD && proj_min > -t + AABB_GUARD {
        Some(Split::Coplanar)
    } else {
        None
    }
}

// --- FindBestSplit / SplitPolyList / bspBuild (§6.3) -----------------------

/// `FindBestSplit` (§6.3): pick the poly whose plane best partitions the list.  OPTIMAL stride
/// (evaluate every candidate).  Structural (0x28) non-portal polys are skipped as candidate
/// splitters unless every remaining poly is structural; a `PF_Portal` poly is ALWAYS a
/// candidate splitter (that is how zone-boundary planes cut the world).
///
/// **Split-minimizing variant (documented deviation).** The engine's raw score
/// `(100−Balance)·Splits + Balance·|F−B|` with the byte-verified MAP REBUILD `Balance=50` lets a
/// well-balanced *interior* plane win over a zero-split boundary plane, then RECOVERS the whole
/// faces in `bspOptGeom`'s redundant-node removal (`Editor.dll 0x36870`, NOT decoded to
/// instruction level — §7.2/§10).  Porting that trim faithfully is out of N-2 scope, so to reach
/// the same surf SET without it we make Splits dominate (`SPLIT_WEIGHT`): a zero-split splitter
/// always beats a splitting one, the engine balance term only breaking ties among equal split
/// counts.  A `PF_Portal` candidate keeps the `PortalBias` discount on its split cost so a
/// zone-boundary plane can still be chosen.  This reproduces the surviving surf set for a/c/d/e
/// exactly; the residual node-COUNT gap on the wedge/portal cases (b, f) is exactly the
/// un-ported `bspOptGeom` trim (see the differential's xfail notes).
fn find_best_split(polys: &[FPoly]) -> usize {
    const SPLIT_WEIGHT: f32 = 1.0e6;
    const T: f32 = THRESH_SPLIT_POLY_WITH_PLANE;
    let structural = |pf: u32| (pf & 0x28) != 0 && (pf & csg::PF_PORTAL) == 0;
    let all_structural = polys.iter().all(|p| structural(p.poly_flags));
    let balance = (100 - BALANCE) as f32;
    let pbias = PORTAL_BIAS as f32 / 100.0;
    // Precompute each poly's AABB ONCE (candidate-independent), so the O(M^2) inner loop can cull a
    // poly whose box provably sits entirely front/back/coplanar to the candidate plane without the
    // expensive per-vertex `split_with_plane` — the dominant build cost (the per-brush classify tree
    // rebuild over the growing world poly list).  Behavior-preserving: `aabb_side` returns the exact
    // category `split_with_plane` would, or `None` (then we call it).
    let aabbs: Vec<(Vec3, Vec3)> = polys.iter().map(poly_aabb).collect();
    // Score one candidate splitter `i` (None if it is an ineligible structural non-portal poly).
    let eval = |i: usize| -> Option<(f32, usize)> {
        let cand = &polys[i];
        if !all_structural && structural(cand.poly_flags) {
            return None;
        }
        let cand_portal = (cand.poly_flags & csg::PF_PORTAL) != 0;
        let (mut front, mut back, mut splits) = (0i32, 0i32, 0f32);
        for (j, p) in polys.iter().enumerate() {
            if j == i {
                continue;
            }
            let side = match aabb_side(&aabbs[j].0, &aabbs[j].1, &cand.base, &cand.normal, T) {
                Some(s) => s,
                None => p.split_with_plane(&cand.base, &cand.normal, false),
            };
            match side {
                Split::Front => front += 1,
                Split::Back => back += 1,
                Split::Coplanar => {} // stays with the node
                Split::Split(_, _) => {
                    splits += if (p.poly_flags & csg::PF_PORTAL) != 0 {
                        16.0
                    } else {
                        1.0
                    };
                }
            }
        }
        let split_cost = SPLIT_WEIGHT * splits + balance * splits;
        let mut score = split_cost + BALANCE as f32 * (front - back).abs() as f32;
        if cand_portal {
            score -= split_cost * pbias;
        }
        Some((score, i))
    };
    // Pick the min-score candidate, tie-broken by LOWEST index — bit-identical to the sequential
    // `if score < best_score` scan (strict `<` keeps the earliest of equal scores).  The `(score,
    // index)` lexicographic reduce makes the winner independent of evaluation ORDER, so the rayon
    // parallel path (used only for large lists, where the O(M^2) scoring dominates and the split
    // work is embarrassingly parallel across candidates) yields the SAME index as the sequential
    // path.  Small lists stay sequential to avoid pool overhead.
    let combine = |a: (f32, usize), b: (f32, usize)| -> (f32, usize) {
        if b.0 < a.0 || (b.0 == a.0 && b.1 < a.1) {
            b
        } else {
            a
        }
    };
    let best = if polys.len() >= 128 {
        (0..polys.len())
            .into_par_iter()
            .filter_map(eval)
            .reduce(|| (f32::INFINITY, usize::MAX), combine)
            .1
    } else {
        let mut acc = (f32::INFINITY, usize::MAX);
        for i in 0..polys.len() {
            if let Some(s) = eval(i) {
                acc = combine(acc, s);
            }
        }
        acc.1
    };
    if best == usize::MAX {
        0
    } else {
        best
    }
}

/// `SplitPolyList` (§6.3): make `FindBestSplit`'s plane a node, chain its coplanars, partition
/// the rest, recurse front/back.
fn split_poly_list(
    model: &mut Model,
    i_parent: i32,
    place: i32,
    polys: Vec<FPoly>,
    depth: usize,
) -> Result<(), BuildError> {
    if polys.is_empty() {
        return Ok(());
    }
    if depth > MAX_DEPTH {
        return Err(BuildError("BSP build exceeded max recursion depth".into()));
    }
    let i_best = find_best_split(&polys);
    let splitter = polys[i_best].clone();
    let i_node = bsp_add_node(model, i_parent, place, NF_IS_NEW, &splitter);

    let mut front: Vec<FPoly> = Vec::new();
    let mut back: Vec<FPoly> = Vec::new();
    for (j, p) in polys.into_iter().enumerate() {
        if j == i_best {
            continue;
        }
        // AABB fast-path: a poly whose box provably sits entirely front/back/coplanar to the
        // splitter is placed WHOLE (identical to `split_with_plane`'s Front/Back/Coplanar arms)
        // without the per-vertex split; only a genuine straddle (`None`) does the exact cut.
        let (bmin, bmax) = poly_aabb(&p);
        let fast = aabb_side(
            &bmin,
            &bmax,
            &splitter.base,
            &splitter.normal,
            THRESH_SPLIT_POLY_WITH_PLANE,
        );
        let split = match fast {
            Some(s) => s,
            None => p.split_with_plane(&splitter.base, &splitter.normal, false),
        };
        match split {
            Split::Front => front.push(p),
            Split::Back => back.push(p),
            Split::Coplanar => {
                bsp_add_node(model, i_node, NODE_PLANE, NF_IS_NEW, &p);
            }
            Split::Split(mut f, mut b) => {
                if f.fix() >= 3 {
                    front.push(f);
                }
                if b.fix() >= 3 {
                    back.push(b);
                }
            }
        }
    }
    split_poly_list(model, i_node, NODE_FRONT, front, depth + 1)?;
    split_poly_list(model, i_node, NODE_BACK, back, depth + 1)?;
    Ok(())
}

/// `bspBuild` — build a `Model`'s node tree from a world FPoly list.  Used both to build the
/// final level Model and (by `csg`) the transient classify trees.
///
/// `share_surfs`: give every face that belongs to the SAME source brush face (same owning
/// `actor` + `i_brush_poly`) ONE shared surf, tagging each poly's `iLink` to it.  A brush face
/// that CSG clipped into several coplanar fragments then resolves to ONE surf referenced by
/// several nodes (matching the editor: a clipped wall is one surf, many nodes) — while the
/// abutting-subtracts case (golden d) keeps two rooms' coplanar-but-distinct faces as two surfs
/// (different `actor`).  The BSP's own split fragments of a face further reuse that surf via
/// `bspAddNode`'s `iLink==NumSurfs` sharing.  The transient classify trees pass `false`.
pub fn build_bsp_opt(polys: &[FPoly], share_surfs: bool) -> Model {
    let mut model = Model::default();
    if polys.is_empty() {
        return model;
    }
    // finalize() already ran on brush polys, but a merged/collected poly may need it.
    let mut ready: Vec<FPoly> = polys
        .iter()
        .filter_map(|p| {
            let mut q = p.clone();
            q.finalize().ok().map(|_| q)
        })
        .collect();
    if share_surfs {
        // One surf per (actor, i_brush_poly) brush-face identity; coplanar fragments share it.
        let mut by_face: Vec<((i32, i32), i32)> = Vec::new();
        for p in ready.iter_mut() {
            let key = (p.actor, p.i_brush_poly);
            let existing = by_face.iter().find(|(k, _)| *k == key).map(|(_, s)| *s);
            let i_surf = match existing {
                Some(s) => s,
                None => {
                    let s = alloc_surf(&mut model, p);
                    by_face.push((key, s));
                    s
                }
            };
            p.i_link = i_surf;
        }
    }
    let _ = split_poly_list(&mut model, -1, NODE_ROOT, ready, 0);
    model
}

/// Default in-plane texture axes for a face whose poly carries none: an orthonormal `(U, V)` basis
/// lying IN the surface plane (perpendicular to `normal`).  The engine's `FLightManager::
/// SetupForSurf` maps the lumel grid through the stored `TextureU/TextureV`; a basis NOT in the
/// plane makes a wall's extent project to ~0 on one axis, `UScale`/`VScale` -> 0, and the engine
/// divides by it -> "Anomalous singularity in URender::DrawWorld" (crash observed live 2026-07-15
/// on the X/Y walls, whose world-axis fallback was out of plane).  A world-axis fallback is only
/// in-plane for Z-normal faces, so derive from the normal instead.
fn default_texture_axes(n: Vec3) -> (Vec3, Vec3) {
    // Helper = the world axis LEAST aligned with n; cross(helper, n) is then well-conditioned and
    // lies in the plane perpendicular to n.
    let (ax, ay, az) = (n.x.abs(), n.y.abs(), n.z.abs());
    let helper = if ax <= ay && ax <= az {
        Vec3::new(1.0, 0.0, 0.0)
    } else if ay <= az {
        Vec3::new(0.0, 1.0, 0.0)
    } else {
        Vec3::new(0.0, 0.0, 1.0)
    };
    let norm = |v: Vec3| {
        let l = v.size();
        if l < 1e-8 {
            Vec3::new(1.0, 0.0, 0.0)
        } else {
            Vec3::new(v.x / l, v.y / l, v.z / l)
        }
    };
    let u = norm(helper.cross(&n));
    let v = norm(n.cross(&u));
    (u, v)
}

/// Allocate a surf for a poly (the surf-creation body of `bspAddNode`); returns its index.
fn alloc_surf(model: &mut Model, edpoly: &FPoly) -> i32 {
    let pf = edpoly.poly_flags & 0x3cff_ffff;
    let p_base = bsp_add_point(model, edpoly.base, true);
    let v_normal = bsp_add_vector(model, edpoly.normal, true);
    // Keep explicit (authored) texture axes; else derive an in-plane basis from the normal (a
    // world-axis fallback is only in-plane for Z-normal faces — see default_texture_axes).
    let have_u = edpoly.texture_u.dot(&edpoly.texture_u) > 1e-8;
    let have_v = edpoly.texture_v.dot(&edpoly.texture_v) > 1e-8;
    let (tu, tv) = if have_u && have_v {
        (edpoly.texture_u, edpoly.texture_v)
    } else {
        default_texture_axes(edpoly.normal)
    };
    let v_texture_u = bsp_add_vector(model, tu, false);
    let v_texture_v = bsp_add_vector(model, tv, false);
    model.surfs.push(BspSurf {
        texture_ref: edpoly.texture,
        poly_flags: pf,
        p_base,
        v_normal,
        v_texture_u,
        v_texture_v,
        i_actor: edpoly.actor,
        i_brush_poly: edpoly.i_brush_poly,
        i_zone: edpoly.i_zone,
        i_light_map: -1,
    });
    (model.surfs.len() - 1) as i32
}

/// Classify-tree build (no surf sharing) — used by `csg` for the transient world/brush trees.
pub fn build_bsp(polys: &[FPoly]) -> Model {
    build_bsp_opt(polys, false)
}

// --- leaf-bounding repair (§80) --------------------------------------------

/// `IsCsg` in BUILD convention: a solid partitioning face.  Ignores `NF_IsNew` (0x20, set on every
/// freshly built node — `finalize` clears it) but honours `NF_NotCsg` (0x01) and portal (0x04), so
/// it matches the propagation `finalize`+`zones` will compute post-swap.
fn is_csg_build(n: &BspNode) -> bool {
    n.num_vertices > 0 && (n.node_flags & 0x05) == 0
}

/// A region half-space: interior satisfies `n·p - w >= 0` when `keep_front`, else `<= 0`.
#[derive(Clone, Copy)]
struct HalfSpace {
    n: Vec3,
    w: f32,
    keep_front: bool,
}

impl HalfSpace {
    /// Signed slack: `>= 0` means `p` is inside this half-space.
    fn slack(&self, p: &Vec3) -> f32 {
        let d = self.n.dot(p) - self.w;
        if self.keep_front {
            d
        } else {
            -d
        }
    }
}

/// Find a point strictly interior to the convex `region` (projections-onto-convex-sets from
/// `seed`).  Returns `None` if the region looks empty/degenerate (still violating after the
/// iteration budget) — the caller then conservatively skips the cell.
fn region_interior_point(region: &[HalfSpace], seed: Vec3) -> Option<Vec3> {
    const MARGIN: f32 = 0.5;
    let mut p = seed;
    for _ in 0..64 {
        // most-violated half-space
        let mut worst = f32::INFINITY;
        let mut wi = usize::MAX;
        for (i, h) in region.iter().enumerate() {
            let s = h.slack(&p);
            if s < worst {
                worst = s;
                wi = i;
            }
        }
        if worst >= MARGIN - 1e-3 || wi == usize::MAX {
            return Some(p);
        }
        // project p onto that half-space's boundary + MARGIN inside (n is unit).
        let h = &region[wi];
        let dir = if h.keep_front { 1.0 } else { -1.0 };
        let need = MARGIN - h.slack(&p);
        p = Vec3::new(
            p.x + h.n.x * dir * need,
            p.y + h.n.y * dir * need,
            p.z + h.n.z * dir * need,
        );
    }
    // final feasibility check
    if region.iter().all(|h| h.slack(&p) >= -1e-2) {
        Some(p)
    } else {
        None
    }
}

/// The vertex-average (a point ON the plane) of node `ni`'s face polygon.
fn node_face_centroid(model: &Model, ni: usize) -> Vec3 {
    let n = &model.nodes[ni];
    let cnt = n.num_vertices.max(1) as usize;
    let mut c = Vec3::new(0.0, 0.0, 0.0);
    for k in 0..cnt {
        let vi = model.verts[(n.i_vert_pool + k as i32) as usize].i_vertex as usize;
        let p = model.points[vi];
        c = Vec3::new(c.x + p.x, c.y + p.y, c.z + p.z);
    }
    let inv = 1.0 / cnt as f32;
    Vec3::new(c.x * inv, c.y * inv, c.z * inv)
}

/// Collect every LEAKED-solid terminal cell (tree propagation reads EMPTY, but the point-in-solid
/// oracle says SOLID) and repair each by inserting a bound-node that flips its live propagation to
/// SOLID.  `world_brushes` is the oracle; `_world_polys` retained for signature symmetry.
fn bound_leaked_solid_leaves(
    model: &mut Model,
    _world_polys: &[FPoly],
    world_brushes: &[csg::WorldBrush],
    root_outside: bool,
) {
    if model.nodes.is_empty() {
        return;
    }
    // DFS (build convention: front child = i_front, back = i_back) collecting repair targets first,
    // so the insertions (which append nodes) never perturb the walk.  Each target is (parent node,
    // ENodePlace of the leaked child slot).
    let mut targets: Vec<(i32, i32)> = Vec::new();
    let mut region: Vec<HalfSpace> = Vec::new();
    collect_leaks(
        model,
        0,
        root_outside,
        &mut region,
        world_brushes,
        root_outside,
        &mut targets,
    );

    for (parent, place) in targets {
        insert_solid_bound(model, parent, place);
    }
}

/// Insert a node `M` at parent `ni`'s child slot `place` (a `-1` leaked-solid leaf), whose plane is
/// the parent plane FLIPPED.  `M` coincides with the parent plane (zero-volume front sliver) but is
/// a solid CSG node, so descending into the leaked cell now crosses `M` onto its BACK (solid) side:
/// the live `outside` propagation reads SOLID, `assign_leaves` marks it solid, and `bspBuildBounds`
/// emits its hull bounded by the cell's real ancestor faces (the floor plane it should rest on).
/// `M`'s front sliver becomes a degenerate (zero-area) empty leaf — ignored by the area-thresholded
/// portal pass.  Build convention (pre-finalize): `i_front` = empty leaf, `i_back` = solid leaf.
fn insert_solid_bound(model: &mut Model, ni: i32, place: i32) {
    let (plane, i_surf, i_vp, nv) = {
        let n = &model.nodes[ni as usize];
        (n.plane, n.i_surf, n.i_vert_pool, n.num_vertices)
    };
    // Copy the parent's face verts so NumVertices > 0 (required by IsCsg); positions are unused by
    // collision (which reads node PLANES), only the count matters.
    let i_vert_pool = model.verts.len() as i32;
    for k in 0..nv {
        let v = model.verts[(i_vp + k) as usize];
        model.verts.push(v);
    }
    let m = model.nodes.len() as i32;
    let mut node = BspNode::leaf(
        Plane {
            x: -plane.x,
            y: -plane.y,
            z: -plane.z,
            w: -plane.w,
        },
        i_surf,
        i_vert_pool,
        nv,
    );
    // NF_SOLID_BOUND (0x40): our transient marker for a synthetic leaf-bound node.  IsCsg-true
    // (not in the 0x21/0x25 IsCsg masks), and cleared before serialization; `zones` reads it to
    // suppress the zero-volume EMPTY sliver leaf on the node's front side (else each becomes a
    // spurious isolated zone).
    node.node_flags = NF_SOLID_BOUND;
    model.nodes.push(node);
    match place {
        NODE_FRONT => model.nodes[ni as usize].i_front = m,
        NODE_BACK => model.nodes[ni as usize].i_back = m,
        _ => {}
    }
}

#[allow(clippy::too_many_arguments)]
fn collect_leaks(
    model: &Model,
    ni: i32,
    outside: bool,
    region: &mut Vec<HalfSpace>,
    world_brushes: &[csg::WorldBrush],
    root_outside: bool,
    out: &mut Vec<(i32, i32)>,
) {
    if ni < 0 {
        return;
    }
    let (i_front, i_back, csg, plane) = {
        let n = &model.nodes[ni as usize];
        (n.i_front, n.i_back, is_csg_build(n), n.plane)
    };
    let pn = Vec3::new(plane.x, plane.y, plane.z);
    // build convention: FRONT child = i_front (+normal); BACK child = i_back (-normal)
    for (is_front, child, place) in [(true, i_front, NODE_FRONT), (false, i_back, NODE_BACK)] {
        let child_out = if csg { is_front } else { outside };
        let hs = HalfSpace {
            n: pn,
            w: plane.w,
            keep_front: is_front,
        };
        if child == -1 {
            // leaked SOLID cell: tree says empty (outside) but the oracle says solid.
            if child_out {
                region.push(hs);
                let seed = {
                    let c = node_face_centroid(model, ni as usize);
                    let dir = if is_front { 1.0 } else { -1.0 };
                    Vec3::new(
                        c.x + pn.x * dir * 2.0,
                        c.y + pn.y * dir * 2.0,
                        c.z + pn.z * dir * 2.0,
                    )
                };
                if let Some(rep) = region_interior_point(region, seed) {
                    if csg::point_in_solid_world(&rep, world_brushes, root_outside) {
                        out.push((ni, place));
                    }
                }
                region.pop();
            }
        } else {
            region.push(hs);
            collect_leaks(
                model,
                child,
                child_out,
                region,
                world_brushes,
                root_outside,
                out,
            );
            region.pop();
        }
    }
}

// --- final-model finishing -------------------------------------------------

/// Finalize the built tree's COLLISION TOPOLOGY (the parts LineCheck/PointRegion require), then
/// hand off leaf/zone enumeration to `zones::assign_leaves_and_zones`.  The topology fixes here
/// are live-verified load-bearing (spike 60): without them the pawn falls through the floor.
fn finalize_leaves_and_bbox(model: &mut Model) {
    for ni in 0..model.nodes.len() {
        let n = &mut model.nodes[ni];
        // (1) TOPOLOGY (collision + PointRegion). The engine indexes iChild[1] (serial +0x24 ==
        //     our `i_back`) for the FRONT (positive PlaneDot) halfspace and iChild[0] (+0x20 ==
        //     `i_front`) for BACK; our build put the FRONT child in `i_front`. Exchange so FRONT
        //     lands in `i_back`, matching DXOnly (spike 60 §2.2).
        std::mem::swap(&mut n.i_front, &mut n.i_back);
        // (2) Clear NF_IsNew so FBspNode::IsCsg() treats a solid wall as a blocker; a transient
        //     NF_IsNew (0x20) makes every node non-CSG and the pawn falls through (spike 60 §2.1).
        n.node_flags &= !NF_IS_NEW;
        // (3) Render bound stays -1: OccludeBsp's guard skips the bound test on -1; a >=0 index
        //     into the empty Bounds array derefs a NULL FBox -> "Anomalous singularity" (spike 50).
        //     (iCollisionBound is set later by bsp_build_bounds; iLeaf/iZone by zones::assign.)
        n.i_render_bound = -1;
    }
    // Real leaves + multi-zone flood + per-node iZone/ZoneMask + the Zones array (replaces the old
    // single-zone stub); see zones.rs.  Runs on the finalized (engine-order) topology; reads the
    // NF_SOLID_BOUND marker to suppress synthetic-bound slivers.
    // (legacy path: ignore the byte-parity node-emit-order — only the bspcsg pipeline relabels)
    let _ = crate::zones::assign_leaves_and_zones(model);
    // Clear the transient NF_SOLID_BOUND marker — never a real on-disk NodeFlag.
    for n in model.nodes.iter_mut() {
        n.node_flags &= !NF_SOLID_BOUND;
    }

    // bbox over all points
    if model.points.is_empty() {
        model.bbox_min = Vec3::new(0.0, 0.0, 0.0);
        model.bbox_max = Vec3::new(0.0, 0.0, 0.0);
        return;
    }
    let mut mn = model.points[0];
    let mut mx = model.points[0];
    for p in &model.points {
        mn = Vec3::new(mn.x.min(p.x), mn.y.min(p.y), mn.z.min(p.z));
        mx = Vec3::new(mx.x.max(p.x), mx.y.max(p.y), mx.z.max(p.z));
    }
    model.bbox_min = mn;
    model.bbox_max = mx;
}

/// One brush in the CSG input (already local-space polys + a transform).
pub struct BrushInput {
    pub polys: Vec<FPoly>,
    pub oper: CsgOper,
    pub poly_flags: u32,
    pub rot: [[f32; 3]; 3],
    pub prepivot: Vec3,
    pub location: Vec3,
    pub scale: Vec3,
    /// `ABrush::BuildCoords` VectorXform `(L⁻¹)ᵀ` for a SCALED brush (`None` = unscaled/identity).
    /// When set, `bsp_brush_csg` computes each face normal the editor's way — the LOCAL winding
    /// normal covariant-mapped by this matrix then `SafeNormalSlow` — instead of `calc_normal` over
    /// the L-warped world winding (which is 1 ULP under unit on asymmetric faces; §92 §43).
    pub vec_xform: Option<[[f32; 3]; 3]>,
}

/// The N-1 pipeline: run the CSG leaf-filter per brush (actor order), merge coplanars, build
/// the final BSP, finish leaves/bbox.  Returns the level `Model`.
pub fn build_geometry_from_brushes(brushes: &[BrushInput]) -> Result<Model, BuildError> {
    let world_root_outside = false; // a DX level is solid; Subtract carves.
    let mut world_polys: Vec<FPoly> = Vec::new();
    // Accumulated world-space brushes in CSG order — the point-in-solid oracle the CSG classifier
    // replays to decide which fragments survive (see csg::point_in_solid).
    let mut world_brushes: Vec<csg::WorldBrush> = Vec::new();

    for (bi, b) in brushes.iter().enumerate() {
        if (b.scale.x - 1.0).abs() > 1e-6
            || (b.scale.y - 1.0).abs() > 1e-6
            || (b.scale.z - 1.0).abs() > 1e-6
        {
            return Err(BuildError(format!(
                "brush {} has non-identity Scale {:?} — scaled brushes are not yet supported \
                 (reject, never silently mis-build); apply scale upstream",
                bi,
                (b.scale.x, b.scale.y, b.scale.z)
            )));
        }
        // Portal force (§5): a Portal brush is forced NotSolid (Semisolid cleared) before CSG,
        // so it cuts zones for visibility but never blocks (`csgRebuild` 0x4a814).
        let mut poly_flags = b.poly_flags;
        if poly_flags & csg::PF_PORTAL != 0 {
            poly_flags = (poly_flags & !csg::PF_SEMISOLID) | csg::PF_NOTSOLID;
        }
        // Transform brush polys to world space.  Tag each with its owning brush index so the
        // coplanar merge (§7.1) can reassemble the fragments of ONE brush face while keeping
        // distinct brushes' coplanar faces separate (golden d).
        let mut wp: Vec<FPoly> = Vec::new();
        for p in &b.polys {
            let mut q = p.clone();
            q.actor = bi as i32;
            if q.transform(&b.rot, &b.prepivot, &b.location).is_ok() {
                wp.push(q);
            }
        }
        // Record this brush's world-space convex hull for the point-in-solid oracle BEFORE running
        // CSG, so the oracle reflects FULL solidity including this brush.  Recompute each face
        // normal from the winding: a SHEARED brush (e.g. a diagonal wall) stores its PRE-shear
        // AXIS normal, which is not perpendicular to the actual slanted face — trusting it makes
        // the convex membership test reject interior points and the brush's solid never registers.
        // Zeroing forces `finalize` -> `calc_normal` (CCW winding => outward), matching the editor.
        // (Only the oracle uses winding normals; the CSG split path keeps the authored normals so
        // the surf identity / editor goldens are unchanged.)
        let non_solid = poly_flags & csg::PF_NOTSOLID != 0;
        let mut solid_polys: Vec<FPoly> = Vec::new();
        for p in &wp {
            let mut q = p.clone();
            q.normal = Vec3::new(0.0, 0.0, 0.0);
            if q.finalize().is_ok() {
                solid_polys.push(q);
            }
        }
        world_brushes.push(csg::WorldBrush {
            polys: solid_polys,
            oper: b.oper,
            non_solid,
        });
        world_polys = csg::bsp_brush_csg(
            world_polys,
            &wp,
            b.oper,
            poly_flags,
            world_root_outside,
            &world_brushes,
        );
    }

    // §7.1 bspMergeCoplanars: reassemble each brush face's clipped fragments into one poly, so
    // it becomes a single shared surf (bspBuild re-splits it into nodes that share the surf).
    let mut world_polys = passes::bsp_merge_coplanars(world_polys);
    // Re-derive each surviving face's plane normal from its (reassembled) winding before the final
    // partition.  The engine's FPoly::Finalize always recomputes the normal; our brush polys carry
    // the authored T3D normal, which for a SHEARED brush (a diagonal wall) is the PRE-shear AXIS
    // normal — geometrically wrong for the slanted face.  Left uncorrected it makes the FINAL BSP
    // node plane axis-aligned instead of slanted, so the descent misroutes a point behind that
    // face and the wall's solid is not seen (DWallSE).  Doing this AFTER the coplanar merge (which
    // reassembles fragments by their authored normal identity) keeps surf sharing intact while
    // giving the partition true planes.  calc_normal follows the current winding, so a Subtract
    // face reversed by the leaf-filter keeps its (negated) orientation.
    for p in world_polys.iter_mut() {
        let mut w = p.clone();
        w.normal = Vec3::new(0.0, 0.0, 0.0);
        if w.calc_normal() && p.normal.dot(&w.normal) < 0.9999 {
            p.normal = w.normal;
        }
    }
    // bspBuild: partition into the node tree (surfs shared across a face's split fragments).
    let mut model = build_bsp_opt(&world_polys, true);
    model.root_outside = world_root_outside;
    // Leaf-bounding repair (§80): our merge+single-rebuild collapses the CSG fragments, so the
    // partition LEAKS — some solid terminal cells are reached with the live CSG `outside`
    // propagation reading EMPTY (a distant splitter plane's unbounded extension flips it), where
    // the editor's incrementally-built tree bounds every solid leaf by real faces.  A leaked cell
    // is invisible to swept-box collision (`if Outside: return` before the hull read) and gets no
    // LeafHull, so the pawn sinks/falls through.  Bound each leaked-solid cell by grafting the real
    // world faces that pass through it, so its live propagation reads SOLID and bspBuildBounds emits
    // its hull (spike `80-bspbuild-topology.md`).  Runs in BUILD convention (front=i_front), before
    // finalize swaps to engine order and clears NF_IsNew.
    bound_leaked_solid_leaves(&mut model, &world_polys, &world_brushes, world_root_outside);
    // §7.3 bspRefresh: drop unreferenced surfs, re-pack the vert pool.
    passes::bsp_refresh(&mut model);
    // TestVisibility (leaves/zones) — single-zone first cut (§8.3).
    finalize_leaves_and_bbox(&mut model);
    // §7.4 bspBuildBounds: build the per-solid-leaf COLLISION HULLS (LeafHulls + iCollisionBound)
    // so the pawn stands (a box sweep is non-solid without them); Bounds/iRenderBound stay empty/-1.
    passes::bsp_build_bounds(&mut model);

    // Correct mis-flooded SOLID leaves.  zones::assign_leaves (Pass A) derives each terminal cell's
    // solidity by the SAME `outside` propagation the CSG classifier used — and for complex geometry
    // it mis-marks some SOLID cells as empty (a wall's interior swallowed by a distant diagonal
    // wall's extended splitter plane, whose back cell is never subdivided by the wall's own faces).
    // Re-derive each terminal leaf's solidity from the reliable point-in-solid oracle and clear the
    // spurious empty-leaf reference so the region reads solid.  Only solid corrections are made (we
    // never invent empty leaves), and this runs AFTER bspBuildBounds so the collision hulls — built
    // from the flood result and known-good — are untouched; only the render/zone `iLeaf` slot the
    // point-region descent reads is fixed.  A no-op on simple single-zone geometry (a/c/d/e), where
    // the propagation already agrees with point-in-solid.
    let nn = model.nodes.len();
    for ni in 0..nn {
        let (npv, ivp, plane, i_front, i_back, leaf0, leaf1) = {
            let n = &model.nodes[ni];
            (
                n.num_vertices as usize,
                n.i_vert_pool,
                n.plane,
                n.i_front,
                n.i_back,
                n.i_leaf[0],
                n.i_leaf[1],
            )
        };
        if npv == 0 || (i_back != -1 && i_front != -1) {
            continue;
        }
        let mut c = Vec3::new(0.0, 0.0, 0.0);
        for k in 0..npv {
            let vi = model.verts[(ivp + k as i32) as usize].i_vertex as usize;
            let p = model.points[vi];
            c = Vec3::new(c.x + p.x, c.y + p.y, c.z + p.z);
        }
        let inv = 1.0 / npv as f32;
        c = Vec3::new(c.x * inv, c.y * inv, c.z * inv);
        let nl = Vec3::new(plane.x, plane.y, plane.z);
        const EPS: f32 = 0.5;
        // side 1 = FRONT (i_back child, +normal half-space); side 0 = BACK (i_front, −normal).
        if i_back == -1 && leaf1 >= 0 {
            let s = Vec3::new(c.x + nl.x * EPS, c.y + nl.y * EPS, c.z + nl.z * EPS);
            if csg::point_in_solid_world(&s, &world_brushes, world_root_outside) {
                model.nodes[ni].i_leaf[1] = -1;
            }
        }
        if i_front == -1 && leaf0 >= 0 {
            let s = Vec3::new(c.x - nl.x * EPS, c.y - nl.y * EPS, c.z - nl.z * EPS);
            if csg::point_in_solid_world(&s, &world_brushes, world_root_outside) {
                model.nodes[ni].i_leaf[0] = -1;
            }
        }
    }
    Ok(model)
}

// --- M0 stand-in (kept: §6 gate 5 pins Python carved_box_model to this) -----

/// A single subtracted box: six inward-facing walls, one leaf, single zone.  Built directly
/// (NOT via CSG) so it stays byte-identical to the Python `carved_box_model` for the dual-
/// serializer cross-check.
pub fn carved_box(size: f32, height: f32) -> Model {
    let hx = size / 2.0;
    let hy = size / 2.0;
    let hz = height / 2.0;
    let pts = [
        Vec3::new(-hx, -hy, -hz),
        Vec3::new(hx, -hy, -hz),
        Vec3::new(hx, hy, -hz),
        Vec3::new(-hx, hy, -hz),
        Vec3::new(-hx, -hy, hz),
        Vec3::new(hx, -hy, hz),
        Vec3::new(hx, hy, hz),
        Vec3::new(-hx, hy, hz),
    ];
    let faces: [(Vec3, usize, [usize; 4]); 6] = [
        (Vec3::new(0.0, 0.0, 1.0), 0, [0, 1, 2, 3]),
        (Vec3::new(0.0, 0.0, -1.0), 4, [7, 6, 5, 4]),
        (Vec3::new(1.0, 0.0, 0.0), 0, [0, 3, 7, 4]),
        (Vec3::new(-1.0, 0.0, 0.0), 1, [2, 1, 5, 6]),
        (Vec3::new(0.0, 1.0, 0.0), 0, [1, 0, 4, 5]),
        (Vec3::new(0.0, -1.0, 0.0), 3, [3, 2, 6, 7]),
    ];
    let mut vectors: Vec<Vec3> = Vec::new();
    let mut surfs: Vec<BspSurf> = Vec::new();
    let mut nodes: Vec<BspNode> = Vec::new();
    let mut verts: Vec<BspVert> = Vec::new();
    for (fi, (normal, base_pt, corners)) in faces.iter().enumerate() {
        let n_idx = vectors.len() as i32;
        vectors.push(*normal);
        let u_idx = vectors.len() as i32;
        vectors.push(Vec3::new(1.0, 0.0, 0.0));
        let v_idx = vectors.len() as i32;
        vectors.push(Vec3::new(0.0, 1.0, 0.0));
        surfs.push(BspSurf {
            texture_ref: 0,
            poly_flags: 0,
            p_base: *base_pt as i32,
            v_normal: n_idx,
            v_texture_u: u_idx,
            v_texture_v: v_idx,
            i_actor: 0,
            i_brush_poly: fi as i32,
            i_zone: [0, 0],
            i_light_map: -1,
        });
        let vp = verts.len() as i32;
        for &c in corners.iter() {
            verts.push(BspVert {
                i_vertex: c as i32,
                i_side: -1,
            });
        }
        let bp = &pts[*base_pt];
        let w = normal.dot(bp);
        nodes.push(BspNode::leaf(
            Plane {
                x: normal.x,
                y: normal.y,
                z: normal.z,
                w,
            },
            fi as i32,
            vp,
            corners.len() as i32,
        ));
    }
    Model {
        vectors,
        points: pts.to_vec(),
        nodes,
        surfs,
        verts,
        num_shared_sides: 0,
        zones: Vec::new(),
        field_0x54: 0,
        bounds: Vec::new(),
        leaf_hulls: Vec::new(),
        leaves: vec![BspLeaf::default()],
        light_map: Vec::new(),
        light_bits: Vec::new(),
        lights: Vec::new(),
        none_index: 0,
        bbox_min: Vec3::new(-hx, -hy, -hz),
        bbox_max: Vec3::new(hx, hy, hz),
        root_outside: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A box brush centred at `loc`, half-extents `(hx,hy,hz)`, OUTWARD normals (a normal
    /// solid brush).  Winding CCW as seen from outside.
    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> BrushInput {
        // 8 corners
        let c = |sx: f32, sy: f32, sz: f32| Vec3::new(sx * hx, sy * hy, sz * hz);
        // faces with OUTWARD normals, CCW from outside
        let faces = [
            // +X
            (
                Vec3::new(1.0, 0.0, 0.0),
                [
                    c(1.0, -1.0, -1.0),
                    c(1.0, 1.0, -1.0),
                    c(1.0, 1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                ],
            ),
            // -X
            (
                Vec3::new(-1.0, 0.0, 0.0),
                [
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, -1.0, -1.0),
                    c(-1.0, -1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            // +Y
            (
                Vec3::new(0.0, 1.0, 0.0),
                [
                    c(1.0, 1.0, -1.0),
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, 1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                ],
            ),
            // -Y
            (
                Vec3::new(0.0, -1.0, 0.0),
                [
                    c(-1.0, -1.0, -1.0),
                    c(1.0, -1.0, -1.0),
                    c(1.0, -1.0, 1.0),
                    c(-1.0, -1.0, 1.0),
                ],
            ),
            // +Z
            (
                Vec3::new(0.0, 0.0, 1.0),
                [
                    c(-1.0, -1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            // -Z
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

    /// Golden surf-set matcher: (rounded normal, rounded offset=normal·base).
    fn surf_planes(m: &Model) -> Vec<(i32, i32, i32, i32)> {
        let mut out = Vec::new();
        for s in &m.surfs {
            let n = m.vectors[s.v_normal as usize];
            let b = m.points[s.p_base as usize];
            let off = n.dot(&b);
            out.push((
                (n.x * 1e3).round() as i32,
                (n.y * 1e3).round() as i32,
                (n.z * 1e3).round() as i32,
                (off).round() as i32,
            ));
        }
        out.sort();
        out
    }

    /// Tier-S surf-set key: for each surf, (signed-normal plane, offset, sorted node-poly
    /// vertex set) — the exact quantity the editor golden freezes (§6 gate 3).
    fn surf_tier_s(m: &Model) -> Vec<((i32, i32, i32, i32), Vec<(i32, i32, i32)>)> {
        // map surf -> the first node referencing it, gather that node's verts
        let mut out = Vec::new();
        for (si, s) in m.surfs.iter().enumerate() {
            let n = m.vectors[s.v_normal as usize];
            let b = m.points[s.p_base as usize];
            let off = n.dot(&b);
            let plane = (
                (n.x * 1e3).round() as i32,
                (n.y * 1e3).round() as i32,
                (n.z * 1e3).round() as i32,
                off.round() as i32,
            );
            let node = m.nodes.iter().find(|nd| nd.i_surf == si as i32);
            let mut verts: Vec<(i32, i32, i32)> = Vec::new();
            if let Some(nd) = node {
                for k in 0..nd.num_vertices {
                    let vi = m.verts[(nd.i_vert_pool + k) as usize].i_vertex as usize;
                    let p = m.points[vi];
                    verts.push((p.x.round() as i32, p.y.round() as i32, p.z.round() as i32));
                }
            }
            verts.sort();
            out.push((plane, verts));
        }
        out.sort();
        out
    }

    #[test]
    fn case_a_single_subtract_full_surf_set() {
        // subtract cube(512,512,256) at origin -> 6 inward walls (golden case a), FULL surf set.
        let brushes = [box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];
        let m = build_geometry_from_brushes(&brushes).unwrap();
        assert_eq!(m.surfs.len(), 6, "case a surf count");
        let got = surf_tier_s(&m);
        let s = |mut v: Vec<(i32, i32, i32)>| {
            v.sort();
            v
        };
        // Editor golden (subagent capture): plane + cleaned vertex set per wall.
        let expect = {
            let mut e: Vec<((i32, i32, i32, i32), Vec<(i32, i32, i32)>)> = vec![
                (
                    (-1000, 0, 0, -256),
                    s(vec![
                        (256, -256, -128),
                        (256, 256, -128),
                        (256, 256, 128),
                        (256, -256, 128),
                    ]),
                ),
                (
                    (1000, 0, 0, -256),
                    s(vec![
                        (-256, -256, -128),
                        (-256, 256, -128),
                        (-256, 256, 128),
                        (-256, -256, 128),
                    ]),
                ),
                (
                    (0, -1000, 0, -256),
                    s(vec![
                        (-256, 256, -128),
                        (256, 256, -128),
                        (256, 256, 128),
                        (-256, 256, 128),
                    ]),
                ),
                (
                    (0, 1000, 0, -256),
                    s(vec![
                        (-256, -256, -128),
                        (256, -256, -128),
                        (256, -256, 128),
                        (-256, -256, 128),
                    ]),
                ),
                (
                    (0, 0, -1000, -128),
                    s(vec![
                        (-256, -256, 128),
                        (256, -256, 128),
                        (256, 256, 128),
                        (-256, 256, 128),
                    ]),
                ),
                (
                    (0, 0, 1000, -128),
                    s(vec![
                        (-256, -256, -128),
                        (256, -256, -128),
                        (256, 256, -128),
                        (-256, 256, -128),
                    ]),
                ),
            ];
            e.sort();
            e
        };
        assert_eq!(
            got, expect,
            "case a Tier-S surf set (plane + vertex set) vs editor golden"
        );
    }

    #[test]
    fn case_c_add_in_subtract_pillar_outward() {
        // subtract cube(512,512,256), then ADD cube(128) -> 12 surfs (golden case c)
        let brushes = [
            box_brush(
                256.0,
                256.0,
                128.0,
                Vec3::new(0.0, 0.0, 0.0),
                CsgOper::Subtract,
            ),
            box_brush(64.0, 64.0, 64.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add),
        ];
        let m = build_geometry_from_brushes(&brushes).unwrap();
        assert_eq!(m.surfs.len(), 12, "case c surf count");
        let planes = surf_planes(&m);
        // pillar faces: outward normals, offset +64
        assert!(
            planes.contains(&(-1000, 0, 0, 64)),
            "pillar -X face outward off=64"
        );
        assert!(
            planes.contains(&(1000, 0, 0, 64)),
            "pillar +X face outward off=64"
        );
        // room walls still present
        assert!(planes.contains(&(-1000, 0, 0, -256)), "room +X wall");
    }

    #[test]
    fn case_d_abutting_subtracts_annihilate_shared_wall() {
        // two cube(256^3) subtracts at x=-128 and x=+128 -> 10 surfs, NO surf at x=0 (golden d)
        let brushes = [
            box_brush(
                128.0,
                128.0,
                128.0,
                Vec3::new(-128.0, 0.0, 0.0),
                CsgOper::Subtract,
            ),
            box_brush(
                128.0,
                128.0,
                128.0,
                Vec3::new(128.0, 0.0, 0.0),
                CsgOper::Subtract,
            ),
        ];
        let m = build_geometry_from_brushes(&brushes).unwrap();
        let planes = surf_planes(&m);
        // No surf coincident with the x=0 plane (a wall at x=0 would have normal ±X, offset 0).
        let at_x0 = planes
            .iter()
            .filter(|(nx, ny, nz, off)| {
                ny.abs() < 1 && nz.abs() < 1 && nx.abs() > 900 && off.abs() < 1
            })
            .count();
        assert_eq!(at_x0, 0, "shared x=0 wall must be annihilated (§6.5)");
        assert_eq!(
            m.surfs.len(),
            10,
            "case d surf count (annihilated shared wall)"
        );
    }

    #[test]
    fn box_model_serializes() {
        let m = carved_box(512.0, 256.0);
        assert_eq!(m.nodes.len(), 6);
        assert_eq!(m.surfs.len(), 6);
    }

    #[test]
    fn subtract_box_builds_collision_hulls_with_correct_orientation() {
        // A single subtracted room: every node bounds a solid exterior cell, so every node must
        // carry a collision hull (`iCollisionBound >= 0`) or the pawn falls through (the box
        // sweep is non-solid without hulls).  The hull's plane refs, oriented (negated on the FLIP
        // bit 0x40000000), must have the SOLID exterior on their NEGATIVE side (normals point out
        // of solid) — checked here by sampling a point just outside each wall.
        let brushes = [box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];
        let m = build_geometry_from_brushes(&brushes).unwrap();
        assert!(!m.leaf_hulls.is_empty(), "no collision hulls built");
        let n_hull = m.nodes.iter().filter(|n| n.i_collision_bound >= 0).count();
        assert_eq!(
            n_hull,
            m.nodes.len(),
            "every node must carry a solid-exterior hull"
        );
        const FLIP: i32 = 0x4000_0000;
        for (ni, node) in m.nodes.iter().enumerate() {
            let start = node.i_collision_bound;
            assert!(start >= 0);
            // read the run's plane refs up to the -1 terminator.
            let mut k = start as usize;
            let mut refs = Vec::new();
            while m.leaf_hulls[k] != -1 {
                refs.push(m.leaf_hulls[k]);
                k += 1;
            }
            assert!(!refs.is_empty(), "node {ni} hull has no planes");
            // the 6 bbox ints follow the -1.
            assert!(k + 6 < m.leaf_hulls.len(), "node {ni} hull missing bbox");
            // a point 8uu OUTSIDE this node's wall (on the solid side) must satisfy EVERY oriented
            // hull plane (PlaneDot < 0 = inside the solid cell).
            let p = m.plane_from_node(ni);
            // outward (into solid) = the node's back side; step along -normal from the wall.
            let base = m.wall_point(ni);
            let probe = Vec3::new(base.x - p.0 * 8.0, base.y - p.1 * 8.0, base.z - p.2 * 8.0);
            for &r in &refs {
                let idx = (r & !FLIP) as usize;
                let pl = m.nodes[idx].plane;
                let (nx, ny, nz, w) = if r & FLIP != 0 {
                    (-pl.x, -pl.y, -pl.z, -pl.w)
                } else {
                    (pl.x, pl.y, pl.z, pl.w)
                };
                let dot = nx * probe.x + ny * probe.y + nz * probe.z - w;
                assert!(
                    dot < 1e-2,
                    "node {ni} solid probe outside hull plane (dot={dot})"
                );
            }
        }
    }

    // --- small test-only helpers on Model for the hull-orientation check ---
    impl Model {
        fn plane_from_node(&self, ni: usize) -> (f32, f32, f32, f32) {
            let p = self.nodes[ni].plane;
            (p.x, p.y, p.z, p.w)
        }
        /// A point ON node `ni`'s plane (project the origin onto it): `w * n` for a unit normal.
        fn wall_point(&self, ni: usize) -> Vec3 {
            let p = self.nodes[ni].plane;
            Vec3::new(p.x * p.w, p.y * p.w, p.z * p.w)
        }
    }

    /// Build-convention propagation solidity at `p` (front child = i_front; IsCsg ignores NF_IsNew).
    fn prop_solid_build(model: &Model, p: Vec3) -> bool {
        let mut ni = 0i32;
        let mut outside = model.root_outside;
        for _ in 0..1000 {
            let n = &model.nodes[ni as usize];
            let pd = n.plane.x * p.x + n.plane.y * p.y + n.plane.z * p.z - n.plane.w;
            let csg = is_csg_build(n);
            // build convention: front child (+normal) = i_front; back = i_back.
            let (child, is_front) = if pd >= 0.0 {
                (n.i_front, true)
            } else {
                (n.i_back, false)
            };
            outside = if csg { is_front } else { outside };
            if child == -1 {
                return !outside;
            }
            ni = child;
        }
        false
    }

    #[test]
    fn leaf_bounding_flips_a_leaked_solid_cell_to_solid() {
        // A hand-built LEAK: one wall node (x=0) whose FRONT (x>0) child is a terminal that the
        // tree propagation reads EMPTY, while the oracle (fully-solid world, no brushes) says SOLID.
        // `bound_leaked_solid_leaves` must graft a flip node so the front cell reads SOLID.
        let mut model = Model::default();
        model.root_outside = false; // solid world; empty world_brushes => oracle solid everywhere
                                    // a quad face on the x=0 plane so the node has verts (NumVertices>0 for IsCsg + a centroid).
        model.points = vec![
            Vec3::new(0.0, -10.0, -10.0),
            Vec3::new(0.0, 10.0, -10.0),
            Vec3::new(0.0, 10.0, 10.0),
            Vec3::new(0.0, -10.0, 10.0),
        ];
        model.verts = (0..4)
            .map(|i| BspVert {
                i_vertex: i,
                i_side: -1,
            })
            .collect();
        model.surfs = vec![BspSurf {
            texture_ref: 0,
            poly_flags: 0,
            p_base: 0,
            v_normal: 0,
            v_texture_u: 0,
            v_texture_v: 0,
            i_actor: 0,
            i_brush_poly: 0,
            i_zone: [0, 0],
            i_light_map: -1,
        }];
        model.vectors = vec![Vec3::new(1.0, 0.0, 0.0)];
        let mut node = BspNode::leaf(
            Plane {
                x: 1.0,
                y: 0.0,
                z: 0.0,
                w: 0.0,
            },
            0,
            0,
            4,
        );
        node.node_flags = NF_IS_NEW; // as the real build emits (IsCsg ignores this bit)
        model.nodes.push(node);

        // Precondition: the front (x>0) cell LEAKS — propagation reads empty though it is solid.
        assert!(
            !prop_solid_build(&model, Vec3::new(10.0, 0.0, 0.0)),
            "front cell should leak empty"
        );
        assert!(
            prop_solid_build(&model, Vec3::new(-10.0, 0.0, 0.0)),
            "back cell is solid"
        );

        let before = model.nodes.len();
        bound_leaked_solid_leaves(&mut model, &[], &[], false);
        assert!(model.nodes.len() > before, "a flip node must be grafted");
        // Postcondition: the leaked front cell now reads SOLID; the back stays solid.
        assert!(
            prop_solid_build(&model, Vec3::new(10.0, 0.0, 0.0)),
            "leaked cell must now read solid"
        );
        assert!(
            prop_solid_build(&model, Vec3::new(-10.0, 0.0, 0.0)),
            "back cell still solid"
        );
        // The grafted node carries the solid-bound marker and its plane is the parent's, flipped.
        let m = model.nodes.last().unwrap();
        assert_eq!(m.node_flags & NF_SOLID_BOUND, NF_SOLID_BOUND);
        assert!(
            (m.plane.x + 1.0).abs() < 1e-6,
            "flip node plane is parent-flipped"
        );
    }

    #[test]
    fn leaf_bounding_is_noop_on_a_convex_room() {
        // A single subtracted box is fully watertight already: no cell leaks, so the pass adds
        // nothing (guards against the repair spuriously firing on convex geometry / the goldens).
        let brushes = [box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];
        let m = build_geometry_from_brushes(&brushes).unwrap();
        // exactly the 6 walls, no synthetic bound nodes (which would carry a duplicated flip plane).
        assert_eq!(
            m.nodes.len(),
            6,
            "convex room must stay 6 nodes (no leak repair)"
        );
    }
}
