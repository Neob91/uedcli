//! BSP cleanup passes (§7 of the CSG-build spike section 10):
//! `bspMergeCoplanars` (§7.1), `bspRefresh` (§7.3), `bspBuildBounds` (§7.4).
//!
//! `bspOptGeom` (§7.2, T-junction linking) is intentionally NOT ported here — it affects
//! vertex adjacency (crack-free rendering), not the Tier-S surf SET the differential gates on,
//! so it is an N-2+ residual (see the design spec / section 10 §10).

use crate::fpoly::{FPoly, Split, THRESH_POINTS_ARE_SAME};
use crate::model::{BspNode, FBox, Model, Vec3};

const THRESH_NORMALS_ARE_SAME: f32 = 2.0e-5;
const MERGE_OFFSET_TOL: f32 = 0.002;

// --- bspMergeCoplanars (§7.1) ---------------------------------------------

/// True when two faces belong to the same source brush face (same owning actor + brush-poly
/// index).  The engine's `bspMergeCoplanars(Model,0,0)` is called with
/// `MergeDisparateTextures=0`: it reassembles the fragments of ONE surface, it does NOT fuse two
/// distinct surfaces that merely happen to be coplanar+adjacent (proven by the abutting-subtracts
/// golden `d`, whose two rooms' shared-plane floors stay two surfs).  Fragments of one planar
/// brush face are coplanar by construction.
fn same_surface(a: &FPoly, b: &FPoly) -> bool {
    a.actor == b.actor
        && a.i_brush_poly == b.i_brush_poly
        && (a.normal.x - b.normal.x).abs() < THRESH_NORMALS_ARE_SAME
        && (a.normal.y - b.normal.y).abs() < THRESH_NORMALS_ARE_SAME
        && (a.normal.z - b.normal.z).abs() < THRESH_NORMALS_ARE_SAME
        && (a.base.dot(&a.normal) - b.base.dot(&b.normal)).abs() < MERGE_OFFSET_TOL
}

/// Dedup a point into `pts`, returning its index (within `THRESH_POINTS_ARE_SAME`).
fn vid(pts: &mut Vec<Vec3>, v: Vec3) -> usize {
    for (i, p) in pts.iter().enumerate() {
        if v.sub(p).size() < THRESH_POINTS_ARE_SAME {
            return i;
        }
    }
    pts.push(v);
    pts.len() - 1
}

/// Parameter `t` of `c` along segment `a→b` if `c` lies strictly interior to it (colinear,
/// off the endpoints), else `None`.
fn seg_param(a: Vec3, b: Vec3, c: Vec3) -> Option<f32> {
    let ab = b.sub(&a);
    let len2 = ab.dot(&ab);
    if len2 < 1.0e-8 {
        return None;
    }
    let t = c.sub(&a).dot(&ab) / len2;
    if t <= 1.0e-4 || t >= 1.0 - 1.0e-4 {
        return None;
    }
    let proj = Vec3::new(a.x + ab.x * t, a.y + ab.y * t, a.z + ab.z * t);
    if c.sub(&proj).size() < THRESH_POINTS_ARE_SAME {
        Some(t)
    } else {
        None
    }
}

/// Union a group of coplanar, edge-tiling fragments of ONE surface into a single boundary
/// polygon.  This is the T-junction-aware reassembly the engine's `bspBuildFPolys` +
/// `bspMergeCoplanars` performs: it splits every edge at any interior vertex (killing
/// T-junctions), cancels the internal shared edges (each appears once in each direction), traces
/// the surviving boundary edges into one ring, then removes colinear verts.  Returns `None` (keep
/// the fragments unmerged) if the boundary is not a single simple ring.
fn union_group(group: &[FPoly]) -> Option<FPoly> {
    let mut pts: Vec<Vec3> = Vec::new();
    let mut raw: Vec<(usize, usize)> = Vec::new();
    for f in group {
        let n = f.verts.len();
        for i in 0..n {
            let a = vid(&mut pts, f.verts[i]);
            let b = vid(&mut pts, f.verts[(i + 1) % n]);
            if a != b {
                raw.push((a, b));
            }
        }
    }
    // Split every edge at interior vertices so all edges are atomic.
    let mut edges: Vec<(usize, usize)> = Vec::new();
    for &(a, b) in &raw {
        let (pa, pb) = (pts[a], pts[b]);
        let mut mids: Vec<(f32, usize)> = Vec::new();
        for (i, p) in pts.iter().enumerate() {
            if i == a || i == b {
                continue;
            }
            if let Some(t) = seg_param(pa, pb, *p) {
                mids.push((t, i));
            }
        }
        mids.sort_by(|x, y| x.0.partial_cmp(&y.0).unwrap_or(std::cmp::Ordering::Equal));
        let mut chain = vec![a];
        chain.extend(mids.iter().map(|&(_, i)| i));
        chain.push(b);
        for w in chain.windows(2) {
            edges.push((w[0], w[1]));
        }
    }
    // Cancel opposite directed edges (internal shared boundaries).
    let mut used = vec![false; edges.len()];
    for i in 0..edges.len() {
        if used[i] {
            continue;
        }
        for j in 0..edges.len() {
            if !used[j] && j != i && edges[j] == (edges[i].1, edges[i].0) {
                used[i] = true;
                used[j] = true;
                break;
            }
        }
    }
    let boundary: Vec<(usize, usize)> = edges
        .iter()
        .enumerate()
        .filter(|(i, _)| !used[*i])
        .map(|(_, &e)| e)
        .collect();
    if boundary.len() < 3 {
        return None;
    }
    // Trace one ring; a branch (a vertex with != 1 outgoing boundary edge) means the union is
    // not a single simple polygon — bail and keep the fragments.
    let mut next = vec![usize::MAX; pts.len()];
    for &(a, b) in &boundary {
        if next[a] != usize::MAX {
            return None;
        }
        next[a] = b;
    }
    let start = boundary[0].0;
    let mut ring = vec![start];
    let mut cur = start;
    loop {
        let nxt = next[cur];
        if nxt == usize::MAX {
            return None;
        }
        if nxt == start {
            break;
        }
        ring.push(nxt);
        cur = nxt;
        if ring.len() > pts.len() {
            return None;
        }
    }
    if ring.len() != boundary.len() || ring.len() < 3 {
        return None;
    }
    let mut out = group[0].clone();
    out.verts = ring.iter().map(|&i| pts[i]).collect();
    out.remove_colinears();
    if out.verts.len() < 3 {
        return None;
    }
    Some(out)
}

/// `bspMergeCoplanars` (§7.1) + the `bspBuildFPolys` surface reassembly (§6.2): group the CSG
/// world fragments by source surface and union each group's coplanar, edge-tiling fragments into
/// ONE boundary polygon (T-junction-aware, colinears removed).  A brush face that CSG clipped
/// into several fragments becomes one clean polygon here — so downstream it is ONE surf, and
/// `bspBuild` re-splits it into the minimal node set (matching the editor's per-surf vertex set).
/// Distinct surfaces never merge (`same_surface`); a group whose union is not a single simple
/// ring is left as its fragments.
pub fn bsp_merge_coplanars(polys: Vec<FPoly>) -> Vec<FPoly> {
    let mut groups: Vec<Vec<FPoly>> = Vec::new();
    for p in polys {
        match groups.iter_mut().find(|g| same_surface(&g[0], &p)) {
            Some(g) => g.push(p),
            None => groups.push(vec![p]),
        }
    }
    let mut out: Vec<FPoly> = Vec::new();
    for g in groups {
        if g.len() == 1 {
            out.extend(g);
        } else if let Some(u) = union_group(&g) {
            out.push(u);
        } else {
            out.extend(g);
        }
    }
    out
}

// --- bspRefresh (§7.3) ----------------------------------------------------

/// `bspRefresh` (§7.3): array compaction after a build — drop unreferenced surfs and renumber
/// the nodes' `iSurf`, then re-pack the vert pool so each node's verts are contiguous in build
/// order (renumbering `iVertPool`).  Pure array GC + reindex; no geometry decisions.  (Points/
/// Vectors are left as-is HERE — the Vectors canonical re-ORDER is a dedicated post-build pass in
/// `bspcsg.rs` (`reorder_surfs_canonical`/`rebuild_vector_pool` make the Surfs + Vectors pools
/// byte-exact in ORDER), and the Points pool is GC'd incrementally at the editor's real `bspRefresh`
/// call sites via `bsp_refresh_points_vectors[_stale_orphans]` below.  An unreferenced pool entry is
/// otherwise harmless.)
pub fn bsp_refresh(model: &mut Model) {
    // 1. Drop unreferenced surfs; renumber node.i_surf.
    let mut used = vec![false; model.surfs.len()];
    for n in &model.nodes {
        if n.i_surf >= 0 && (n.i_surf as usize) < used.len() {
            used[n.i_surf as usize] = true;
        }
    }
    let mut remap = vec![-1i32; model.surfs.len()];
    let mut new_surfs = Vec::new();
    for (i, &u) in used.iter().enumerate() {
        if u {
            remap[i] = new_surfs.len() as i32;
            new_surfs.push(model.surfs[i].clone());
        }
    }
    for n in &mut model.nodes {
        if n.i_surf >= 0 {
            n.i_surf = remap[n.i_surf as usize];
        }
    }
    model.surfs = new_surfs;

    // 2. Re-pack the vert pool contiguously in node order.
    let mut new_verts = Vec::with_capacity(model.verts.len());
    for n in &mut model.nodes {
        let start = new_verts.len() as i32;
        for k in 0..n.num_vertices {
            let idx = (n.i_vert_pool + k) as usize;
            new_verts.push(model.verts[idx]);
        }
        n.i_vert_pool = start;
    }
    model.verts = new_verts;
    model.num_shared_sides = 0;
}

/// `bspRefresh`'s Points/Vectors compaction — the part `bsp_refresh` above deliberately skips
/// (see its own doc comment). Fresh disassembly (2026-08-30, `Editor.dll` `0x10036fb0`-`0x10037166`,
/// the real `bspRefresh` continuing past the Nodes/Surfs/Verts work `bsp_refresh` already ports)
/// shows the real editor DOES drop unreferenced Points AND Vectors on every single `bspRefresh`
/// call (world-level AND every subtree repartition). Confirms and supersedes the
/// `native-materialize-findings.md` "`bspRefresh` does NOT correspondingly compact Verts/Points"
/// entry for POINTS specifically — that entry is correct for VERTS only (no verts remap exists in
/// the disassembled range) but wrong for Points/Vectors, which this ports.
///
/// Reachability, read directly off the disassembly: a Point is used iff some surf's `p_base`
/// (`+0x8`) OR some (already node-compacted) node's own vert-pool range names it via `vert.i_vertex`.
/// A Vector is used iff some surf's `v_normal`/`v_texture_u`/`v_texture_v`
/// (`+0xc`/`+0x10`/`+0x14`) names it — Vectors have no vert-side reference class.
///
/// Wired into the world-level rebuild checkpoint (`bspcsg.rs`), where it bounds the kept CSG-phase
/// Points pool the real `EmptyModel(0,0)` leaves untouched. See `wanchai-verts-points-residual-independently`.
pub fn bsp_refresh_points_vectors(model: &mut Model) {
    let mut pt_used = vec![false; model.points.len()];
    let mut vec_used = vec![false; model.vectors.len()];
    for s in &model.surfs {
        if s.p_base >= 0 {
            pt_used[s.p_base as usize] = true;
        }
        if s.v_normal >= 0 {
            vec_used[s.v_normal as usize] = true;
        }
        if s.v_texture_u >= 0 {
            vec_used[s.v_texture_u as usize] = true;
        }
        if s.v_texture_v >= 0 {
            vec_used[s.v_texture_v as usize] = true;
        }
    }
    for n in &model.nodes {
        for k in 0..n.num_vertices {
            let idx = (n.i_vert_pool + k) as usize;
            if let Some(v) = model.verts.get(idx) {
                if v.i_vertex >= 0 {
                    pt_used[v.i_vertex as usize] = true;
                }
            }
        }
    }

    let mut pt_remap = vec![-1i32; model.points.len()];
    let mut new_points = Vec::new();
    for (i, &used) in pt_used.iter().enumerate() {
        if used {
            pt_remap[i] = new_points.len() as i32;
            new_points.push(model.points[i]);
        }
    }
    let mut vec_remap = vec![-1i32; model.vectors.len()];
    let mut new_vectors = Vec::new();
    for (i, &used) in vec_used.iter().enumerate() {
        if used {
            vec_remap[i] = new_vectors.len() as i32;
            new_vectors.push(model.vectors[i]);
        }
    }

    for s in &mut model.surfs {
        if s.p_base >= 0 {
            s.p_base = pt_remap[s.p_base as usize];
        }
        if s.v_normal >= 0 {
            s.v_normal = vec_remap[s.v_normal as usize];
        }
        if s.v_texture_u >= 0 {
            s.v_texture_u = vec_remap[s.v_texture_u as usize];
        }
        if s.v_texture_v >= 0 {
            s.v_texture_v = vec_remap[s.v_texture_v as usize];
        }
    }
    for v in &mut model.verts {
        if v.i_vertex >= 0 {
            v.i_vertex = pt_remap[v.i_vertex as usize];
        }
    }

    model.points = new_points;
    model.vectors = new_vectors;
}

/// `bsp_refresh_points_vectors` with the real `bspRefresh`'s ORPHAN-VERT semantics
/// (`bspRefresh @0x36cd0`, read off the decompile 2026-09-02): the editor never compacts the verts
/// array and remaps `i_vertex` ONLY through live node vert pools (its final loop walks
/// `nodes[i].iVertPool..+NumVertices`) — an orphan vert (no node pool names it, e.g. a
/// `bspRepartition` subtree call's discarded reconstruction) keeps its now-STALE numeric `i_vertex`
/// and is serialized that way (goldens carry them). Point/vector marking is identical to
/// `bsp_refresh_points_vectors` (all surfs' refs + live pools) — orphan verts pin nothing.
pub fn bsp_refresh_points_vectors_stale_orphans(model: &mut Model) {
    let mut live_vert = vec![false; model.verts.len()];
    for n in &model.nodes {
        for k in 0..n.num_vertices {
            if let Some(slot) = live_vert.get_mut((n.i_vert_pool + k) as usize) {
                *slot = true;
            }
        }
    }
    let mut pt_used = vec![false; model.points.len()];
    let mut vec_used = vec![false; model.vectors.len()];
    for s in &model.surfs {
        if s.p_base >= 0 {
            pt_used[s.p_base as usize] = true;
        }
        for r in [s.v_normal, s.v_texture_u, s.v_texture_v] {
            if r >= 0 {
                vec_used[r as usize] = true;
            }
        }
    }
    for (vi, v) in model.verts.iter().enumerate() {
        if live_vert[vi] && v.i_vertex >= 0 {
            pt_used[v.i_vertex as usize] = true;
        }
    }

    let mut pt_remap = vec![-1i32; model.points.len()];
    let mut new_points = Vec::new();
    for (i, &used) in pt_used.iter().enumerate() {
        if used {
            pt_remap[i] = new_points.len() as i32;
            new_points.push(model.points[i]);
        }
    }
    let mut vec_remap = vec![-1i32; model.vectors.len()];
    let mut new_vectors = Vec::new();
    for (i, &used) in vec_used.iter().enumerate() {
        if used {
            vec_remap[i] = new_vectors.len() as i32;
            new_vectors.push(model.vectors[i]);
        }
    }

    for s in &mut model.surfs {
        if s.p_base >= 0 {
            s.p_base = pt_remap[s.p_base as usize];
        }
        if s.v_normal >= 0 {
            s.v_normal = vec_remap[s.v_normal as usize];
        }
        if s.v_texture_u >= 0 {
            s.v_texture_u = vec_remap[s.v_texture_u as usize];
        }
        if s.v_texture_v >= 0 {
            s.v_texture_v = vec_remap[s.v_texture_v as usize];
        }
    }
    for (vi, v) in model.verts.iter_mut().enumerate() {
        if live_vert[vi] && v.i_vertex >= 0 {
            v.i_vertex = pt_remap[v.i_vertex as usize];
        }
        // orphan vert: i_vertex left STALE on purpose (see doc comment).
    }

    model.points = new_points;
    model.vectors = new_vectors;
}

// --- bspBuildBounds (§7.4): render Bounds + collision LeafHulls -------------
//
// Faithful port of UnrealEd `UEditorEngine::bspBuildBounds` (Editor.dll 0xaace0) and its
// recursive `FilterBound` (0xa8a40), `SplitPartitioner` (0xaa000), `BuildInfiniteFPoly`
// (0xa7ae0), `UpdateBoundWithPolys` (0xaaa20) and `UpdateConvolutionWithPolys` (0xaaae0),
// all byte-decoded in `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/
// bounds-and-zonelayout.md` §1.  Now that native's node-emit ORDER is positionally
// plane-identical to the editor (§82 §10.17), this reproduces BOTH aux arrays in editor
// order:
//   * `Bounds` (UModel+0xc0) — one render FBox per INTERIOR node (>=1 child), indexed by
//     `iRenderBound` in POST-ORDER DFS (root gets the last index).  Each box is the AABB of
//     the hull-poly vertices of every AIR leaf in the node's subtree (child boxes fold in via
//     `FBox += FBox`).  A VALID (IsValid=1, real extents) box — the OccludeBsp render guard
//     (§50) dereferences `Bounds[iRenderBound]`, so an empty array with `iRenderBound>=0` NULL-
//     derefs; a valid box is safe.
//   * `LeafHulls` (UModel+0xcc) — one run per SOLID leaf: `[plane-node refs (|FLIP), …, -1,
//     6× raw-i32-bitcast f32 tight-cell bbox]`, `iCollisionBound` -> run start.  REQUIRED for a
//     walkable pawn (box sweep has no node-plane fallback — re-raw-zones/linecheck-oracle.md).

const NF_MASK_CSG: u8 = 0x21; // NF_NotCsg | NF_IsNew — IsCsg requires none set
const FLIP_BIT: i32 = 0x4000_0000; // LeafHulls plane-ref flag: negate the referenced node plane
const HALF_WORLD_MAX: f32 = 32768.0; // world-cube half-extent (Editor 0x47000000)
const WORLD_MAX: f32 = 65536.0; // BuildInfiniteFPoly quad half-extent (Editor 0x47800000)
const SMALL_NUMBER: f32 = 1.0e-8;
const MAX_FPOLY_SPLIT: usize = 14; // engine SplitInHalf guard (`>= 14` verts)

/// A node is a solid CSG splitter when it has area and no NotCsg/IsNew bit set (game
/// `FBspNode::IsCsg`; bounds run after `finalize` clears NF_IsNew).
fn is_csg(n: &BspNode) -> bool {
    n.num_vertices > 0 && (n.node_flags & NF_MASK_CSG) == 0
}

// --- FBox arithmetic (core.dll semantics, byte-decoded in §1.8) ------------

fn fbox_invalid() -> FBox {
    FBox {
        min: Vec3::new(0.0, 0.0, 0.0),
        max: Vec3::new(0.0, 0.0, 0.0),
        valid: 0,
    }
}

/// SSE `minss(a,b) = (a<b)?a:b` / `maxss(a,b) = (a>b)?a:b` — order-sensitive at ±0, matched to
/// the engine's expand so the serialized floats are bit-identical.
fn minss(a: f32, b: f32) -> f32 {
    if a < b {
        a
    } else {
        b
    }
}
fn maxss(a: f32, b: f32) -> f32 {
    if a > b {
        a
    } else {
        b
    }
}

/// `FBox::operator+=(FVector)` (core.dll 0x18650): valid -> per-component min/max expand;
/// invalid -> `Min=Max=v, IsValid=1`.
fn fbox_add_point(b: &mut FBox, v: &Vec3) {
    if b.valid != 0 {
        b.min = Vec3::new(minss(b.min.x, v.x), minss(b.min.y, v.y), minss(b.min.z, v.z));
        b.max = Vec3::new(maxss(b.max.x, v.x), maxss(b.max.y, v.y), maxss(b.max.z, v.z));
    } else {
        b.min = *v;
        b.max = *v;
        b.valid = 1;
    }
}

/// `FBox::operator+=(FBox&)` (core.dll 0x185b0): expand ONLY when BOTH boxes valid; otherwise
/// `*this = Other` (full copy incl. IsValid) — the quirk where a valid accumulator is REPLACED by
/// an invalid child box (a subtree with no air leaves).  Reproduced verbatim (§1.8).
fn fbox_add_box(dst: &mut FBox, o: &FBox) {
    if dst.valid != 0 && o.valid != 0 {
        dst.min = Vec3::new(
            minss(dst.min.x, o.min.x),
            minss(dst.min.y, o.min.y),
            minss(dst.min.z, o.min.z),
        );
        dst.max = Vec3::new(
            maxss(dst.max.x, o.max.x),
            maxss(dst.max.y, o.max.y),
            maxss(dst.max.z, o.max.z),
        );
    } else {
        *dst = *o;
    }
}

// --- FindBestAxisVectors + BuildInfiniteFPoly (§1.7) -----------------------

/// `FVector::SafeNormal`: `sq = X²+Y²+Z²`; `sq < SMALL_NUMBER` -> zero; else `v / sqrt(sq)`.
fn safe_normal(v: Vec3) -> Vec3 {
    let sq = v.x * v.x + v.y * v.y + v.z * v.z;
    if sq < SMALL_NUMBER {
        return Vec3::new(0.0, 0.0, 0.0);
    }
    let s = 1.0f32 / sq.sqrt();
    Vec3::new(v.x * s, v.y * s, v.z * s)
}

/// `FVector::FindBestAxisVectors(Axis1, Axis2)`: pick a seed axis least aligned with `n`,
/// Gram-Schmidt it against `n`, then `Axis2 = Axis1 × n`.
fn find_best_axis_vectors(n: Vec3) -> (Vec3, Vec3) {
    let (nx, ny, nz) = (n.x.abs(), n.y.abs(), n.z.abs());
    let axis1 = if nz > nx && nz > ny {
        Vec3::new(1.0, 0.0, 0.0)
    } else {
        Vec3::new(0.0, 0.0, 1.0)
    };
    let d = axis1.dot(&n);
    let a1 = safe_normal(Vec3::new(axis1.x - n.x * d, axis1.y - n.y * d, axis1.z - n.z * d));
    let a2 = a1.cross(&n);
    (a1, a2)
}

/// `BuildInfiniteFPoly(Model, iNode)` (0xa7ae0): a huge (±WORLD_MAX) quad ON the node's plane,
/// spanned by the node normal's best axis vectors and centred on the surf Base.  The caller then
/// stamps `iBrushPoly = iNode`.
fn build_infinite_fpoly(model: &Model, i_node: i32) -> FPoly {
    let n = &model.nodes[i_node as usize];
    let surf = &model.surfs[n.i_surf as usize];
    let base = model.points[surf.p_base as usize];
    let normal = model.vectors[surf.v_normal as usize];
    let (a, b) = find_best_axis_vectors(normal);
    let ax = Vec3::new(a.x * WORLD_MAX, a.y * WORLD_MAX, a.z * WORLD_MAX);
    let bx = Vec3::new(b.x * WORLD_MAX, b.y * WORLD_MAX, b.z * WORLD_MAX);
    let add = |p: &Vec3, q: &Vec3, r: &Vec3| Vec3::new(p.x + q.x + r.x, p.y + q.y + r.y, p.z + q.z + r.z);
    let sub_add = |p: &Vec3, q: &Vec3, r: &Vec3| Vec3::new(p.x - q.x + r.x, p.y - q.y + r.y, p.z - q.z + r.z);
    let sub_sub = |p: &Vec3, q: &Vec3, r: &Vec3| Vec3::new(p.x - q.x - r.x, p.y - q.y - r.y, p.z - q.z - r.z);
    let add_sub = |p: &Vec3, q: &Vec3, r: &Vec3| Vec3::new(p.x + q.x - r.x, p.y + q.y - r.y, p.z + q.z - r.z);
    let verts = vec![
        add(&base, &ax, &bx),     // Base + Ax + Bx
        sub_add(&base, &ax, &bx), // Base - Ax + Bx
        sub_sub(&base, &ax, &bx), // Base - Ax - Bx
        add_sub(&base, &ax, &bx), // Base + Ax - Bx
    ];
    let mut p = FPoly::new(verts);
    p.base = base;
    p.normal = normal;
    p.i_brush_poly = -1;
    p
}

/// Build the 6 outward-facing faces of the ±HALF_WORLD_MAX world cube — the initial hull
/// `FilterBound` pushes down the tree.  Windings/normals per §1.1 (winding is order-independent
/// for the FBox but the base/normal ARE used when a cube face acts as a clip plane).
fn world_cube_polys() -> Vec<FPoly> {
    let h = HALF_WORLD_MAX;
    let face = |v: [(f32, f32, f32); 4], n: Vec3| -> FPoly {
        let mut p = FPoly::new(v.iter().map(|&(x, y, z)| Vec3::new(x, y, z)).collect());
        p.normal = n;
        p.base = p.verts[0];
        p.i_brush_poly = -1;
        p
    };
    vec![
        face(
            [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)],
            Vec3::new(0.0, 0.0, 1.0),
        ),
        face(
            [(-h, h, -h), (h, h, -h), (h, -h, -h), (-h, -h, -h)],
            Vec3::new(0.0, 0.0, -1.0),
        ),
        face(
            [(-h, h, -h), (-h, h, h), (h, h, h), (h, h, -h)],
            Vec3::new(0.0, 1.0, 0.0),
        ),
        face(
            [(h, -h, -h), (h, -h, h), (-h, -h, h), (-h, -h, -h)],
            Vec3::new(0.0, -1.0, 0.0),
        ),
        face(
            [(h, h, -h), (h, h, h), (h, -h, h), (h, -h, -h)],
            Vec3::new(1.0, 0.0, 0.0),
        ),
        face(
            [(-h, -h, -h), (-h, -h, h), (-h, h, h), (-h, h, -h)],
            Vec3::new(-1.0, 0.0, 0.0),
        ),
    ]
}

/// Append a split fragment to a child list, halving it first if it exceeds the engine's
/// `MAX_FPOLY_SPLIT` vertex guard (the second half is pushed BEFORE the first, matching the
/// engine's `FrontList[nFront++]=Half; FrontList[nFront++]=Poly` order).
fn push_frag(list: &mut Vec<FPoly>, mut poly: FPoly) {
    if poly.verts.len() >= MAX_FPOLY_SPLIT {
        let half = poly.split_in_half();
        list.push(half);
    }
    list.push(poly);
}

/// `SplitPartitioner` (0xaa000): clip the node's infinite partition poly `part` down to the piece
/// that lies BEHIND every hull face in `poly_list` (the cross-section of the cell on the node
/// plane).  The surviving piece is added, REVERSED with the FLIP tag, to `front_list`, and as-is
/// (tag `iNode`) to `back_list` — so each child hull is closed by the node plane oriented outward.
fn split_partitioner(
    poly_list: &[FPoly],
    front_list: &mut Vec<FPoly>,
    back_list: &mut Vec<FPoly>,
    start: usize,
    mut part: FPoly,
) {
    let mut n = start;
    while n < poly_list.len() {
        if part.verts.len() >= MAX_FPOLY_SPLIT {
            let half = part.split_in_half();
            split_partitioner(poly_list, front_list, back_list, n, half);
        }
        match part.split_with_plane(&poly_list[n].base, &poly_list[n].normal, false) {
            Split::Coplanar => {} // "Got inficoplanar" — keep whole part
            Split::Front => return, // "Got infifront" — part entirely outside the cell
            Split::Back => {}       // keep whole part
            Split::Split(_f, b) => part = b, // keep the piece behind this face
        }
        n += 1;
    }
    let mut f = part.clone();
    f.reverse();
    f.i_brush_poly |= FLIP_BIT;
    front_list.push(f);
    back_list.push(part); // tag stays = iNode
}

/// Recursive `FilterBound` (0xa8a40) driver.  Holds the growing output arrays and the per-node
/// `iRenderBound`/`iCollisionBound` (written into `Model` after the descent, avoiding an alias on
/// `model.nodes` while it is read for geometry).
struct BoundBuilder<'a> {
    model: &'a Model,
    bounds: Vec<FBox>,
    leaf_hulls: Vec<i32>,
    i_render: Vec<i32>,
    i_coll: Vec<i32>,
}

impl<'a> BoundBuilder<'a> {
    /// `UpdateConvolutionWithPolys` (0xaaae0): emit one SOLID-leaf hull run — the deduped
    /// non-(-1) `iBrushPoly` tags of the hull polys (the bounding node-plane refs, with FLIP),
    /// a `-1` terminator, then the tight-cell AABB over ALL hull-poly vertices as 6 raw f32 bits.
    /// Sets the node's `iCollisionBound` to the run start (back call overwrites front — §1.5).
    fn update_convolution(&mut self, i_node: i32, list: &[FPoly]) {
        self.i_coll[i_node as usize] = self.leaf_hulls.len() as i32;
        let mut cell = fbox_invalid();
        for (i, p) in list.iter().enumerate() {
            let t = p.i_brush_poly;
            if t != -1 && !list[..i].iter().any(|q| q.i_brush_poly == t) {
                self.leaf_hulls.push(t);
            }
            for v in &p.verts {
                fbox_add_point(&mut cell, v);
            }
        }
        self.leaf_hulls.push(-1);
        for f in [cell.min.x, cell.min.y, cell.min.z, cell.max.x, cell.max.y, cell.max.z] {
            self.leaf_hulls.push(f.to_bits() as i32);
        }
    }

    /// One `FilterBound` node visit: split the incoming hull polys by the node plane, close each
    /// child hull with the node's partition poly, recurse/terminate per side, emit the render
    /// bound for this interior node, and return this node's accumulated FBox (folded into the
    /// parent by the caller — the engine's `*ParentBound += Bound`).
    fn filter_bound(&mut self, i_node: i32, polys: Vec<FPoly>, outside: bool) -> FBox {
        let node = self.model.nodes[i_node as usize].clone();
        let surf = &self.model.surfs[node.i_surf as usize];
        let base = self.model.points[surf.p_base as usize];
        let normal = self.model.vectors[surf.v_normal as usize];
        let csg = is_csg(&node);
        let mut bound = fbox_invalid();

        // Split incoming hull polys into front/back by the node plane.
        let mut front_list: Vec<FPoly> = Vec::new();
        let mut back_list: Vec<FPoly> = Vec::new();
        for p in &polys {
            match p.split_with_plane(&base, &normal, false) {
                Split::Coplanar => {
                    front_list.push(p.clone());
                    back_list.push(p.clone());
                }
                Split::Front => front_list.push(p.clone()),
                Split::Back => back_list.push(p.clone()),
                Split::Split(f, b) => {
                    push_frag(&mut front_list, f);
                    push_frag(&mut back_list, b);
                }
            }
        }

        // If the node plane actually splits the region, close both child hulls with its
        // infinite partition poly clipped to the cell.
        if !front_list.is_empty() && !back_list.is_empty() {
            let mut part = build_infinite_fpoly(self.model, i_node);
            part.i_brush_poly = i_node;
            split_partitioner(&polys, &mut front_list, &mut back_list, 0, part);
        }

        // FRONT side = iChild[1] = i_back (post-finalize convention).
        if !front_list.is_empty() {
            if node.i_back != -1 {
                let cb = self.filter_bound(node.i_back, front_list, outside || csg);
                fbox_add_box(&mut bound, &cb);
            } else if outside || csg {
                for p in &front_list {
                    for v in &p.verts {
                        fbox_add_point(&mut bound, v);
                    }
                }
            } else {
                self.update_convolution(i_node, &front_list);
            }
        }
        // BACK side = iChild[0] = i_front.
        if !back_list.is_empty() {
            if node.i_front != -1 {
                let cb = self.filter_bound(node.i_front, back_list, outside && !csg);
                fbox_add_box(&mut bound, &cb);
            } else if outside && !csg {
                for p in &back_list {
                    for v in &p.verts {
                        fbox_add_point(&mut bound, v);
                    }
                }
            } else {
                self.update_convolution(i_node, &back_list);
            }
        }

        // Render bound: one FBox per INTERIOR node, indexed in post-order (this runs after both
        // child recursions).  Leaf nodes (both children -1) keep iRenderBound = -1.
        if self.i_render[i_node as usize] == -1 && (node.i_front != -1 || node.i_back != -1) {
            self.i_render[i_node as usize] = self.bounds.len() as i32;
            self.bounds.push(bound);
        }
        bound
    }
}

/// `bspBuildBounds` — build the render `Bounds` (0xc0) and collision `LeafHulls` (0xcc) arrays and
/// the per-node `iRenderBound`/`iCollisionBound`, and re-runs Pass E over every node's `ZoneMask`.
/// Faithful port of the editor's `FilterBound` descent (see the module header).  Empty node array ->
/// nothing to build.
pub fn bsp_build_bounds(model: &mut Model) {
    // Step 1 of the editor's own sequence (spec §8): re-run Pass E.  Load-bearing since the zone
    // pass moved to its real place mid-`csgRebuild` — every node the detail-brush layer appends
    // afterwards is born with `ZoneMask` all-ones and is stamped only here.
    crate::zones::build_zone_masks(model);
    model.bounds.clear();
    model.leaf_hulls.clear();
    for n in model.nodes.iter_mut() {
        n.i_collision_bound = -1;
        n.i_render_bound = -1;
    }
    if model.nodes.is_empty() {
        return;
    }
    let mut b = BoundBuilder {
        model,
        bounds: Vec::new(),
        leaf_hulls: Vec::new(),
        i_render: vec![-1; model.nodes.len()],
        i_coll: vec![-1; model.nodes.len()],
    };
    b.filter_bound(0, world_cube_polys(), model.root_outside);
    let BoundBuilder {
        bounds,
        leaf_hulls,
        i_render,
        i_coll,
        ..
    } = b;
    model.bounds = bounds;
    model.leaf_hulls = leaf_hulls;
    for (i, n) in model.nodes.iter_mut().enumerate() {
        n.i_render_bound = i_render[i];
        n.i_collision_bound = i_coll[i];
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Vec3;

    fn quad(v: [(f32, f32, f32); 4], actor: i32, ibp: i32) -> FPoly {
        let mut p = FPoly::new(v.iter().map(|&(x, y, z)| Vec3::new(x, y, z)).collect());
        p.normal = Vec3::new(0.0, 0.0, 1.0);
        p.actor = actor;
        p.i_brush_poly = ibp;
        p
    }

    #[test]
    fn merges_two_adjacent_halves_of_same_face_into_one() {
        // Two unit-height rectangles sharing the edge x=0 (same actor+brush-poly) -> one rect.
        let left = quad(
            [
                (-10.0, -10.0, 0.0),
                (0.0, -10.0, 0.0),
                (0.0, 10.0, 0.0),
                (-10.0, 10.0, 0.0),
            ],
            1,
            0,
        );
        let right = quad(
            [
                (0.0, -10.0, 0.0),
                (10.0, -10.0, 0.0),
                (10.0, 10.0, 0.0),
                (0.0, 10.0, 0.0),
            ],
            1,
            0,
        );
        let out = bsp_merge_coplanars(vec![left, right]);
        assert_eq!(out.len(), 1, "same-surface halves merge");
        assert_eq!(
            out[0].verts.len(),
            4,
            "seam verts removed by RemoveColinears"
        );
    }

    #[test]
    fn does_not_merge_across_distinct_surfaces() {
        // Same geometry but different owning brush faces -> stays two (golden d behavior).
        let left = quad(
            [
                (-10.0, -10.0, 0.0),
                (0.0, -10.0, 0.0),
                (0.0, 10.0, 0.0),
                (-10.0, 10.0, 0.0),
            ],
            1,
            0,
        );
        let right = quad(
            [
                (0.0, -10.0, 0.0),
                (10.0, -10.0, 0.0),
                (10.0, 10.0, 0.0),
                (0.0, 10.0, 0.0),
            ],
            2,
            0,
        );
        let out = bsp_merge_coplanars(vec![left, right]);
        assert_eq!(out.len(), 2, "distinct surfaces never fuse");
    }
}
