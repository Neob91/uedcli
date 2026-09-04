//! `bspOptGeom` — the editor's geometry-optimization pass, ported standalone.
//!
//! This is `UEditorEngine::bspOptGeom` (UED22 `Editor.dll @0x36870`), decoded to the
//! instruction level in `dev/docs/spikes/2026-07-15-native-materialize/42-bspoptgeom-decode.md`
//! and validated byte-exact against `Test_Castle.dx` (harness `optgeom_validate.py`).
//!
//! It runs after CSG + `SplitPolyList` repartition + `bspRefresh`, and does TWO things (in order):
//!
//!   1. **T-junction elimination (pass 1).**  A T-junction is a point that sits in the *interior*
//!      of another coplanar polygon's edge (not at a vertex).  Left alone it produces lighting
//!      seams / cracks.  Pass 1 walks the BSP for the endpoints of every not-yet-shared node edge,
//!      finds each coplanar node whose polygon that endpoint splits, and INSERTS the point as a new
//!      vertex into that node's ring (growing `Verts` and the node's `NumVertices`).  This is why
//!      the editor's FVert pool fattens to ~14 verts/node (castle 16163) vs a raw CSG build's ~4.
//!      The "not-yet-shared" dup-guard reads a **live** vertex-occurrence table that the inserter
//!      updates on every weld (§42.9) — so once a weld makes two endpoints co-resident in one node,
//!      a later edge over them is recognised as shared and skipped, matching the editor's exact weld
//!      count (castle 975).  A static pre-pass1 table over-welds (castle 977, +2 spurious).
//!      (The decode §1's original claim that bspOptGeom "never edits a node's vertex ring" was
//!      WRONG — the insertion happens inside the `AddPointLink`→inserter subroutine, not the
//!      bspOptGeom body; see the decode doc's corrected §1.)
//!
//!   2. **Shared-side linking + `NumSharedSides` tally (pass 2).**  For every pair of node edges
//!      that are geometrically the same edge (same two point indices, opposite winding), it assigns
//!      a shared side id (`FVert.iSide`) to the second endpoint of each edge, allocating a fresh id
//!      from `Model.NumSharedSides` (seeded at 4) the first time an edge pair is seen.  Pass 2 is
//!      purely combinatorial (point indices + ring positions only — no floating point) and is
//!      reproduced BYTE-EXACT against the golden (16163 iSide values + NumSharedSides = 2739).
//!
//! The pure function is [`bsp_opt_geom`]; [`build_side_links`] exposes pass 2 alone.

use crate::model::{BspVert, Model, Plane, Vec3};

// Debug-only detector-stage counters (UEDCLI_OPTGEOM_DEBUG): [scans, already_vert, band_reached,
// break_projge, capsule_fail, accepts, cap_refused].  Thread-local so the recursive descent can
// bump them.  The env check is cached in a OnceLock so the hot path (~200k/build) pays no getenv.
thread_local! {
    static DBG_STATS: std::cell::RefCell<[u64; 7]> = const { std::cell::RefCell::new([0; 7]) };
}
fn dbg_on() -> bool {
    use std::sync::OnceLock;
    static ON: OnceLock<bool> = OnceLock::new();
    *ON.get_or_init(|| std::env::var("UEDCLI_OPTGEOM_DEBUG").is_ok())
}
#[inline]
fn dbg_bump(i: usize) {
    if dbg_on() {
        DBG_STATS.with(|s| s.borrow_mut()[i] += 1);
    }
}

/// `THRESH_SPLIT_POLY_WITH_PLANE` — the editor's on-plane epsilon band (`Editor.dll` reads
/// `0x100dcb00`=+0.25 / `0x100dcb40`=-0.25).  Used both for the BSP descent in `AddPointLink` (a point
/// with `|PlaneDot| < 0.25` is treated as lying ON that node's plane) AND for the T-junction ring scan
/// (a point whose signed PERPENDICULAR distance from an edge line is within `±0.25` is treated as
/// lying ON that edge).
const THRESH: f32 = 0.25;

/// Degenerate-edge guard: the T-junction scan skips an edge whose cross vector `|E×N|²` is below this
/// (editor const `0x100dcb08` = `1e-6`, compared in f64).
const DEGEN_EDGE_LEN2: f32 = 1e-6;

/// Midpoint-capsule constant (editor const `0x100dcb28` = `0.251001`, f64): a point lying on an edge
/// line is welded only if `|edge|²·0.251001 ≥ |point - midpoint|²`, which bounds it to the segment
/// extent.  Slightly over `0.25` so a point at an endpoint (`|point-midpoint| = |edge|/2`) passes
/// (`0.25·|edge|² ≤ 0.251001·|edge|²`).
const CAPSULE: f64 = 0.251001;

/// `FPlane::PlaneDot` — signed distance of `v` from the plane (`N·v - W`).  Matches the editor's
/// `Core!FPlane::PlaneDot` used throughout the descent.
#[inline]
fn plane_dot(p: &Plane, v: &Vec3) -> f32 {
    p.x * v.x + p.y * v.y + p.z * v.z - p.w
}

/// Vertex-occurrence table: `table[point]` = every `(node, ringpos)` at which `point` appears as a
/// polygon vertex.  Built in the editor's `InitNode` order (`Editor.dll 0x316d0`→`0x31830`): nodes
/// `0..N`, each vertex `0..NumVertices` PREPENDED (head-insert).  The resulting head→tail order is
/// therefore descending node, and within a node descending ringpos — pass 2's first-match ordering
/// depends on this, so the prepend is load-bearing.  Pass 1 then MUTATES this table live (each weld
/// appends the new `(node, point)`; see `add_point_link`), so its dup-guard sees freshly-shared
/// vertices; pass 2 rebuilds a fresh copy.  (The live update appends rather than head-inserts because
/// pass 1's guard reads node membership only, never order — pass 2's order-sensitive first-match uses
/// the fresh rebuild.)
fn build_table(model: &Model) -> Vec<Vec<(i32, i32)>> {
    let mut table: Vec<Vec<(i32, i32)>> = vec![Vec::new(); model.points.len()];
    for (ni, n) in model.nodes.iter().enumerate() {
        let base = n.i_vert_pool;
        for j in 0..n.num_vertices {
            let p = model.verts[(base + j) as usize].i_vertex;
            table[p as usize].insert(0, (ni as i32, j)); // prepend (head insert)
        }
    }
    table
}

/// Full `bspOptGeom`: point-merge prep → pass 1 (T-junction elimination) → pass 2 (side links).
///
/// Operates in place on the built `Model`.  The caller is responsible for having run the CSG build,
/// `SplitPolyList` repartition and `bspRefresh` first (this mirrors `csgRebuild`'s call order); see
/// the module doc + `dev/docs/spikes/.../82-bspbrushcsg-port-decode.md` for the pipeline.
pub fn bsp_opt_geom(model: &mut Model) {
    merge_near_points(model);
    // The editor's LAST Points GC of the whole build sits HERE — inside `bspOptGeom`, right after
    // the ShrinkModel-style near-merge and BEFORE the T-junction weld (`Editor.dll 0x100368f4`,
    // live-confirmed to land exactly on the final golden Points count on UNATCO+Wanchai — board
    // item `wanchai-verts-points-residual-independently`, round 4). It is what drops the
    // near-merge's abandoned duplicate points.
    crate::passes::bsp_refresh_points_vectors_stale_orphans(model);
    eliminate_tjunctions(model);
    build_side_links(model);
}

/// `ShrinkModel`-style point de-dup prep (`Editor.dll 0x33dc0`, called with radius 0.25).  Merges
/// near-coincident world points so that side-links and T-junction tests compare by point INDEX.
///
/// Faithful to the disassembly: for each point `i`, `remap[i]` = the **lowest** earlier index `j < i`
/// whose **Euclidean** distance to `i` is `< 0.25` (`comiss radius², dist²; jbe` skips when
/// `radius² <= dist²`), else `i`; then every `FVert.iVertex` is replaced by `remap[iVertex]` (a single
/// indirection, `0x33ee5`, not a transitive closure).  We deliberately do NOT also remap `FBspSurf.pBase`
/// (`0x33eee`) — that would perturb the surf pool, which is kept byte-exact upstream.  On an already-
/// deduped model (the editor golden, closest pair 0.76 uu) this is a no-op.  The Points array is left
/// intact; only vertex references collapse — the observable effect pass 1/2 depend on.
fn merge_near_points(model: &mut Model) {
    let n = model.points.len();
    if n == 0 {
        return;
    }
    // remap[i] = lowest earlier index within 0.25 (Euclidean), else i.
    let mut remap: Vec<i32> = (0..n as i32).collect();
    // Spatial hash on a 0.25 grid to avoid the editor's O(n²) scan; still pick the LOWEST matching
    // index (the editor takes the first j in ascending order), so the result is identical.
    use std::collections::HashMap;
    let r2 = (THRESH as f64) * (THRESH as f64);
    let cell = THRESH as f64;
    let key = |p: &Vec3| -> (i64, i64, i64) {
        (
            (p.x as f64 / cell).floor() as i64,
            (p.y as f64 / cell).floor() as i64,
            (p.z as f64 / cell).floor() as i64,
        )
    };
    let mut grid: HashMap<(i64, i64, i64), Vec<usize>> = HashMap::new();
    for i in 0..n {
        let p = model.points[i];
        let (gx, gy, gz) = key(&p);
        let mut best: i32 = -1;
        for dx in -1..=1 {
            for dy in -1..=1 {
                for dz in -1..=1 {
                    if let Some(bucket) = grid.get(&(gx + dx, gy + dy, gz + dz)) {
                        for &j in bucket {
                            let q = model.points[j];
                            let (ex, ey, ez) =
                                ((p.x - q.x) as f64, (p.y - q.y) as f64, (p.z - q.z) as f64);
                            if ex * ex + ey * ey + ez * ez < r2 && (best < 0 || (j as i32) < best) {
                                best = j as i32;
                            }
                        }
                    }
                }
            }
        }
        // Always index the grid (unlike the editor's Points-array scan, a merged point can still be
        // the nearest earlier neighbour of a later one — matching the editor's raw-`j` remap).
        grid.entry((gx, gy, gz)).or_default().push(i);
        if best >= 0 {
            remap[i] = best;
        }
    }
    // Apply the remap to every vertex reference (single indirection; only if anything merged).
    // An ORPHAN vert (no node pool names it) can carry a STALE `i_vertex` from a prior
    // points GC — the real `bspRefresh` deliberately leaves orphans un-remapped
    // (`passes::bsp_refresh_points_vectors_stale_orphans`), so a stale ref may be out of range;
    // skip those instead of panicking (the editor's raw remap reads whatever memory sits there —
    // the value is garbage either way and nothing live reads it).
    let merged = remap.iter().enumerate().filter(|(i, &r)| r != *i as i32).count();
    if merged > 0 {
        for v in &mut model.verts {
            if let Some(&r) = remap.get(v.i_vertex as usize) {
                v.i_vertex = r;
            }
        }
    }
    // Ring fix-up — the function's final block [DISASM Editor.dll 0x10033f29-0x10033f9b, decoded
    // 2026-09-03, spike 2026-09-03-verts-points-residual]: for EVERY node (unconditional, not
    // gated on `merged > 0`), drop each ring vert whose post-remap `iVertex` equals its CYCLIC
    // predecessor's (`j == 0` compares against the last vert, so a wrap-closing duplicate dies
    // too), compacting the surviving `(iVertex, iSide)` pairs down within the ring's own slots
    // (`mov [esi+ebx*8]`, `mov [esi+ebx*8+4]`); then `NumVertices = survivors if survivors >= 3
    // else 0` (`cmp ebx, 3; cmovge`). Pool slots past the survivor count stay allocated — the
    // editor never shrinks the region, matching the golden's 3-slot/nv=0 and 4-slot/nv=3 nodes
    // (Underground nodes 1586/1744/1745, the level's whole ring-nv residual).
    for ni in 0..model.nodes.len() {
        let (ivp, nv) = {
            let nd = &model.nodes[ni];
            (nd.i_vert_pool as usize, nd.num_vertices as usize)
        };
        let mut kept = 0usize;
        for j in 0..nv {
            let prev = if j > 0 { j - 1 } else { nv - 1 };
            if model.verts[ivp + j].i_vertex == model.verts[ivp + prev].i_vertex {
                continue;
            }
            model.verts[ivp + kept] = model.verts[ivp + j];
            kept += 1;
        }
        model.nodes[ni].num_vertices = if kept >= 3 { kept as i32 } else { 0 };
    }
    if std::env::var("UEDCLI_OPTGEOM_DEBUG").is_ok() {
        eprintln!("OPTGEOM merge_near_points: {} of {} points remapped", merged, n);
    }
}

// --- pass 1: T-junction elimination -----------------------------------------

/// Pass 1 (`Editor.dll 0x36939`): for every node edge that is not already shared by another node,
/// walk the BSP for both endpoints and insert them as vertices wherever they split a coplanar
/// polygon's edge.  Grows `Model.verts` and the affected nodes' `NumVertices`.
///
/// Returns the number of vertices inserted (0 on an already-optimized model such as the golden).
pub fn eliminate_tjunctions(model: &mut Model) -> usize {
    for v in &mut model.verts {
        v.i_side = -1;
    }
    let mut table = build_table(model);
    let dbg = std::env::var("UEDCLI_OPTGEOM_DEBUG").is_ok();
    let mut inserted = 0usize;
    let mut edges_total = 0usize;
    let mut edges_calling = 0usize;
    let mut ni = 0usize;
    while ni < model.nodes.len() {
        let mut b = 0i32;
        // NumVertices of node `ni` can only change if `ni`'s own ring is split — which cannot
        // happen for `ni`'s own endpoints — but re-read each iteration to mirror the editor loop.
        while b < model.nodes[ni].num_vertices {
            let base = model.nodes[ni].i_vert_pool;
            let nv = model.nodes[ni].num_vertices;
            let a = if b > 0 { b - 1 } else { nv - 1 };
            let p_b = model.verts[(base + b) as usize].i_vertex;
            let p_a = model.verts[(base + a) as usize].i_vertex;
            edges_total += 1;
            // Dup-guard (0x36985): register this edge only if NO other node holds BOTH endpoints
            // as vertices (if another node already shares the exact edge, its side handles it).
            // The table is LIVE — insertions during pass 1 add the welded (node, point) so a later
            // edge sees the freshly-shared vertex (see `add_point_link`'s table update).
            if !edge_shared_elsewhere(&table, p_a, p_b, ni as i32) {
                edges_calling += 1;
                inserted += add_point_link(model, &mut table, 0, p_a);
                inserted += add_point_link(model, &mut table, 0, p_b);
            }
            b += 1;
        }
        ni += 1;
    }
    if dbg {
        let s = DBG_STATS.with(|s| *s.borrow());
        eprintln!(
            "OPTGEOM pass1: nodes={} edges={} edges_unshared(AddPointLink called)={} inserted={}",
            model.nodes.len(),
            edges_total,
            edges_calling,
            inserted
        );
        eprintln!(
            "OPTGEOM detector: ring_scans={} already_vertex={} band_reached={} break_projge={} capsule_fail={} accepts={} cap_refused={}",
            s[0], s[1], s[2], s[3], s[4], s[5], s[6]
        );
    }
    inserted
}

/// Dup-guard helper: is there a node other than `i_node` whose ring contains BOTH `p_a` and `p_b`?
/// Mirrors the listB×listA common-node scan at `0x36989`.
fn edge_shared_elsewhere(table: &[Vec<(i32, i32)>], p_a: i32, p_b: i32, i_node: i32) -> bool {
    let list_b = &table[p_b as usize];
    let list_a = &table[p_a as usize];
    for &(nb, _) in list_b {
        if nb == i_node {
            continue;
        }
        for &(na, _) in list_a {
            if na == nb {
                return true;
            }
        }
    }
    false
}

/// `AddPointLink` (`Editor.dll 0x325e0`, recursive): descend the BSP for `point`, and at every node
/// whose plane `point` lies on, walk the coplanar chain and insert `point` as a vertex wherever it
/// splits a polygon edge (T-junction).  Returns the number of insertions.
///
/// Descent bands (comiss-verified): recurse the FRONT child (`i_front`, mem +0x20) when `dot<0.25`;
/// recurse the BACK child (`i_back`, +0x24) when `dot>-0.25`; treat the point as on-plane and scan
/// this node's coplanar chain (`i_plane`, +0x28) when `-0.25<dot<0.25`.
fn add_point_link(
    model: &mut Model,
    table: &mut [Vec<(i32, i32)>],
    i_node: i32,
    point: i32,
) -> usize {
    if i_node < 0 || i_node as usize >= model.nodes.len() {
        return 0;
    }
    let dot = plane_dot(
        &model.nodes[i_node as usize].plane,
        &model.points[point as usize],
    );
    let mut inserted = 0usize;
    if dot < THRESH {
        let c = model.nodes[i_node as usize].i_front;
        if c != -1 {
            inserted += add_point_link(model, table, c, point);
        }
    }
    if dot <= -THRESH {
        return inserted;
    }
    // dot > -0.25
    let c = model.nodes[i_node as usize].i_back;
    if c != -1 {
        inserted += add_point_link(model, table, c, point);
    }
    if dot >= THRESH {
        return inserted;
    }
    // -0.25 < dot < 0.25: point lies on this node's plane -> walk the coplanar chain.
    let mut cur = i_node;
    let mut guard = 0;
    while cur != -1 {
        guard += 1;
        if guard > model.nodes.len() + 1 {
            break; // corrupt coplanar chain (cycle) — bail rather than spin
        }
        if let Some(edge) = tjunction_edge(model, cur, point) {
            // Ring-size cap (`0x31960`, disasm + live 2026-08-25): the inserter refuses when
            // `NumVertices+1 >= 16` — debugf "Node side limit reached", NO splice and NO live-table
            // update.  Live-confirmed on full UNATCO: 22 refusals, all on rings pinned at nv=15
            // (`editor-tree-oracle/logs/bspopt-insert-unatco.log`); uncapped, native grew those same
            // rings to 18/23.
            if model.nodes[cur as usize].num_vertices + 1 >= 16 {
                dbg_bump(6);
                if dbg_on() {
                    let n = &model.nodes[cur as usize];
                    let p = &model.points[point as usize];
                    eprintln!(
                        "NCAP node={} edge={} point={} plane={:.4},{:.4},{:.4},{:.4} P={:.4},{:.4},{:.4}",
                        cur, edge, point, n.plane.x, n.plane.y, n.plane.z, n.plane.w, p.x, p.y, p.z
                    );
                }
                cur = model.nodes[cur as usize].i_plane;
                continue;
            }
            if dbg_on() {
                let n = &model.nodes[cur as usize];
                let p = &model.points[point as usize];
                eprintln!(
                    "NINS node={} edge={} point={} plane={:.4},{:.4},{:.4},{:.4} P={:.4},{:.4},{:.4}",
                    cur, edge, point, n.plane.x, n.plane.y, n.plane.z, n.plane.w, p.x, p.y, p.z
                );
            }
            insert_ring_vertex(model, cur, edge, point);
            // LIVE table update (editor `0x31920` inserter updates the vertex-occurrence head list):
            // node `cur` now holds `point`, so a later edge whose endpoints BOTH now live in `cur`
            // is correctly treated as shared by the dup-guard — suppressing an over-weld the static
            // pre-pass1 table would have produced.  `edge_shared_elsewhere` reads only node
            // MEMBERSHIP (never ringpos, never order), so appending is enough and the stored ringpos
            // `edge` need not track later ring shifts.  (Pinned: harness
            // `editor-tree-oracle/weld_livetable_diff.py` — static→977 welds / +2 into node 1096,
            // live→975, matching the editor's 975 on both the native and editor pre-pass1 models.)
            table[point as usize].push((cur, edge));
            inserted += 1;
        }
        cur = model.nodes[cur as usize].i_plane;
    }
    inserted
}

/// The per-node T-junction ring scan (`Editor.dll 0x326fc`–`0x32977`, inside `AddPointLink`): decide
/// whether `point` should be spliced into node `ni`'s polygon ring, and at which edge.  Returns the
/// ring index of the edge's *second* endpoint (the insertion position `edge`), or `None`.
///
/// **Instruction-faithful transcription, re-decoded 2026-07-18** (constants read live from
/// `Editor.dll`: `0x100dcb00`=+0.25, `0x100dcb40`=-0.25, `0x100dcb08`=1e-6 f64, `0x100dcb28`=0.251001
/// f64, `0x100dcb10`=0.5).  **The projection vector is `E × N` (edge crossed with the node PLANE
/// NORMAL), NOT `E` itself** — the crucial correction over the earlier decode, which mis-read the
/// `??TFVector` call (`Core.dll FVector::operator^` = cross product) as a plain edge-length divide.
/// `proj` is therefore the signed **PERPENDICULAR distance of `point` from the (infinite) edge line**,
/// measured in the plane, not an along-edge distance:
///
///   * If `point` is already a ring vertex (index equality, post-merge) → `None`.
///   * Walk each edge `(prev→cur)` where `prev=(j?j-1:nv-1)`, `cur=j`:
///     - `E = P[cur] - P[prev]` (f32); `N =` node plane normal; `C = E × N` (f32 cross,
///       `FVector::operator^`).  `|C|² = C·C` (f32, widened to f64).  Skip the edge if `|C|² ≤ 1e-6`
///       (degenerate; note the editor tests the CROSS length, not `|E|`).
///     - `proj = (C·(P[point]-P[cur])) / |C|` — the signed perpendicular offset of `point` from the
///       edge line (`|C|` via f64 `appSqrt`; `C·D` f32 then widened; `proj` truncated back to f32).
///       Since `|N|=1` and `E⊥N` in-plane, `|C|=|E|`, so this is distance in world units.
///     - **`proj ≥ +0.25` → BREAK the whole ring scan, `None`** (`jae 0x32977`, then `esi != nv` so
///       no insert) — `point` sits on the OUTSIDE of this edge (past the convex boundary), so it is
///       not interior to this polygon; abort the node even if an earlier edge was accepted.
///     - `proj ≤ -0.25` → skip this edge (`point` is well INSIDE relative to this edge → not on it).
///     - else (`-0.25 < proj < 0.25`, i.e. `point` lies ON this edge's line): the midpoint **capsule**
///       test `|E|²·0.251001 ≥ |P[point] - midpoint(prev,cur)|²` (all f64, using the REAL edge length
///       `|E|²`, not `|C|²`) bounds the on-line point to the segment extent — on pass, record
///       `best = j` (**keep the LAST accepted edge**); on fail, skip.
///   * After a full scan (no break): insert at `best` if `best ≥ 0`.
///
/// This is a genuine point-on-edge-**INTERIOR** weld: a point in the middle of an edge (perpendicular
/// distance ~0, inside the segment) IS spliced in — that is exactly the CSG T-junction the pass
/// eliminates.  The earlier "near-endpoint / along-edge" reading was the byte-parity bug: it dotted
/// `D` with `E` (along-edge) instead of with `E × N` (perpendicular), so it skipped every deep-interior
/// T-crack.  Verified against the editor's inserter oracle (`bspopt_insert_oracle.py`, 975 welds):
/// node 1 welds points `(-48,-500,0)`/`(-48,-410,0)` at `edge=1` (proj=0, deep interior), which the
/// old reading rejected at `proj=-120/-90 ≤ -0.25`.  Stays a zero-insertion fixpoint on the golden
/// (every on-edge point there is already a ring vertex → the index-equality guard skips it).
fn tjunction_edge(model: &Model, ni: i32, point: i32) -> Option<i32> {
    let node = &model.nodes[ni as usize];
    let base = node.i_vert_pool;
    let nv = node.num_vertices;
    if nv < 1 {
        return None;
    }
    // Node plane normal N (the FVector at node+0x00, unit length) — the cross-product partner.
    let normal = Vec3::new(node.plane.x, node.plane.y, node.plane.z);
    dbg_bump(0); // scans
    // Skip if `point` is already a vertex of this ring (0x326e0 — exact iVertex index equality).
    for j in 0..nv {
        if model.verts[(base + j) as usize].i_vertex == point {
            dbg_bump(1); // already a ring vertex
            return None;
        }
    }
    let p = &model.points[point as usize];
    let mut best = -1i32;
    for j in 0..nv {
        let prev = if j > 0 { j - 1 } else { nv - 1 };
        let v_prev = &model.points[model.verts[(base + prev) as usize].i_vertex as usize];
        let v_cur = &model.points[model.verts[(base + j) as usize].i_vertex as usize];
        let e = v_cur.sub(v_prev);
        // C = E × N  (Editor `??TFVector` = FVector::operator^, f32 cross).  |C| == |E| for a unit
        // in-plane edge, but the editor projects onto C and tests C's length for degeneracy.
        let c = e.cross(&normal);
        let clen2 = c.dot(&c) as f64;
        if clen2 <= DEGEN_EDGE_LEN2 as f64 {
            continue; // |E×N|² <= 1e-6 (jbe 0x32965)
        }
        // proj = (E×N)·(point - v_cur) / |E×N|  = signed perpendicular distance from the edge line
        // (f32 dot; f64 |C| via appSqrt; result truncated to f32).
        let d = p.sub(v_cur);
        let dot = c.dot(&d) as f64;
        let proj = (dot / clen2.sqrt()) as f32;
        if proj >= THRESH {
            dbg_bump(3); // break on proj >= 0.25 (point outside this edge)
            return None; // BREAK whole scan (jae 0x32977 -> esi!=nv -> no insert)
        }
        if proj <= -THRESH {
            continue; // point well inside relative to this edge (jbe 0x32952)
        }
        dbg_bump(2); // reached the ±0.25 band: point is ON this edge line -> capsule test
        // Midpoint capsule (f64), using the REAL edge length |E|² (not |C|²):
        //   |E|²·0.251001 >= |point - midpoint|²   bounds the on-line point to the segment extent.
        let elen2 = e.dot(&e) as f64;
        let m = Vec3::new(
            0.5 * (v_prev.x + v_cur.x),
            0.5 * (v_prev.y + v_cur.y),
            0.5 * (v_prev.z + v_cur.z),
        );
        let r = p.sub(&m);
        let dist2 = r.dot(&r) as f64;
        if elen2 * CAPSULE < dist2 {
            dbg_bump(4); // capsule fail (point on the line but outside the segment)
            continue; // capsule fail (jb 0x3293f)
        }
        best = j; // accept, keep LAST ([ebp-0x34]=esi)
    }
    if best >= 0 {
        dbg_bump(5); // detector accept (a later ring-size cap can still refuse the splice)
        Some(best)
    } else {
        None
    }
}

/// Insert `point` as a new vertex at ring position `edge` of node `ni` (`Editor.dll 0x31920`).
///
/// Byte-faithful to the editor's inserter: allocate `NumVertices+1` fresh `FVert` slots at the
/// **end** of `Verts` (`0x31680`), copy the node's ring with the new vertex (`iVertex=point,
/// iSide=-1`) spliced in at ring position `edge`, repoint `node.iVertPool` to the new base, and
/// bump `NumVertices`.  The old ring slots are **orphaned** — left in place, never compacted (the
/// editor runs no `bspRefresh` after `bspOptGeom`, so those slots survive into the on-disk `Verts`
/// pool; this orphaning is *the* reason the editor's pool is ~16k while the live ring set is ~5.5k).
///
/// Because the new ring is appended (never inserted mid-array), NO other node's `iVertPool` shifts —
/// so, unlike an in-place splice, this needs no fix-up of following nodes.
fn insert_ring_vertex(model: &mut Model, ni: i32, edge: i32, point: i32) {
    let base = model.nodes[ni as usize].i_vert_pool;
    let nv = model.nodes[ni as usize].num_vertices;
    let new_base = model.verts.len() as i32;
    // Copy the ring, splicing the new vertex in at ring position `edge`.
    for j in 0..nv {
        if j == edge {
            model.verts.push(BspVert {
                i_vertex: point,
                i_side: -1,
            });
        }
        let src = model.verts[(base + j) as usize];
        model.verts.push(src);
    }
    if edge == nv {
        // `edge` never equals `nv` in practice (insertion is between two existing verts), but keep
        // the append total-correct if the tie-break ever picks the wrap position.
        model.verts.push(BspVert {
            i_vertex: point,
            i_side: -1,
        });
    }
    model.nodes[ni as usize].i_vert_pool = new_base;
    model.nodes[ni as usize].num_vertices = nv + 1;
}

// --- pass 2: shared-side linking + NumSharedSides ---------------------------

/// Pass 2 (`Editor.dll 0x36a45`): assign `FVert.iSide` shared-side ids and tally
/// `Model.NumSharedSides`.  Purely combinatorial (point indices + ring positions); reproduces the
/// golden byte-exact.
///
/// Rules (all decode-verified):
///   * seed `NumSharedSides = 4` (ids 0..3 reserved), reset every `iSide = -1`;
///   * iterate nodes `0..N`, ring `B` in `0..NumVertices`; skip an edge whose `iSide` is already
///     set; edge is `(A=B-1 wrap → B)`;
///   * find the FIRST partner (outer over `table[pB]`, inner over `table[pA]`) at a node `other ≠
///     this` where, in `other`'s ring, `(posA - posB) mod k == 1` (i.e. `other` has the same edge,
///     opposite winding);
///   * reuse `other`'s side id at `posA` if set, else allocate a fresh id (`NumSharedSides++`);
///   * write the id to BOTH `this` vertex `B` and `other` vertex `posA` (the edge's second
///     endpoints).
pub fn build_side_links(model: &mut Model) {
    for v in &mut model.verts {
        v.i_side = -1;
    }
    model.num_shared_sides = 4;
    let table = build_table(model);
    let node_pool: Vec<i32> = model.nodes.iter().map(|n| n.i_vert_pool).collect();
    let node_nv: Vec<i32> = model.nodes.iter().map(|n| n.num_vertices).collect();
    for ni in 0..model.nodes.len() {
        let base = node_pool[ni];
        let nv = node_nv[ni];
        for b in 0..nv {
            let gv_b = (base + b) as usize;
            if model.verts[gv_b].i_side != -1 {
                continue;
            }
            let a = if b > 0 { b - 1 } else { nv - 1 };
            let p_b = model.verts[gv_b].i_vertex;
            let p_a = model.verts[(base + a) as usize].i_vertex;
            let list_b = &table[p_b as usize];
            let list_a = &table[p_a as usize];
            let mut matched = false;
            'outer: for &(nb, pos_b) in list_b {
                for &(na, pos_a) in list_a {
                    if nb != na {
                        continue;
                    }
                    let other = nb;
                    if other == ni as i32 {
                        continue;
                    }
                    let k = node_nv[other as usize];
                    if k <= 0 {
                        continue;
                    }
                    if (pos_a - pos_b).rem_euclid(k) == 1 {
                        let obase = node_pool[other as usize];
                        let o_idx = (obase + pos_a) as usize;
                        let mut side = model.verts[o_idx].i_side;
                        if side == -1 {
                            side = model.num_shared_sides;
                            model.num_shared_sides += 1;
                        }
                        model.verts[o_idx].i_side = side;
                        model.verts[gv_b].i_side = side;
                        matched = true;
                        break 'outer;
                    }
                }
            }
            let _ = matched;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BspNode, Model, Plane, Vec3};

    fn leaf_node(plane: Plane, i_vert_pool: i32, num_vertices: i32) -> BspNode {
        let mut n = BspNode::leaf(plane, 0, i_vert_pool, num_vertices);
        n.i_front = -1;
        n.i_back = -1;
        n.i_plane = -1;
        n
    }

    /// Two coplanar-adjacent quads sharing one edge (opposite winding) → exactly one shared side,
    /// NumSharedSides = 5, with the id on the second endpoint of each shared edge.
    #[test]
    fn shared_edge_gets_one_side() {
        // points: square A (0,1,2,3) and square B sharing edge (1,2).
        //   0(0,0) 1(10,0) 2(10,10) 3(0,10)   4(20,0) 5(20,10)
        // Quad A ring: 0,1,2,3  (edge 1->2 is the shared edge)
        // Quad B ring: 1,4,5,2  (edge 5->2 ... shared edge 2->1 reversed = 1..2)
        let mut m = Model::default();
        m.points = vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
            Vec3::new(20.0, 0.0, 0.0),
            Vec3::new(20.0, 10.0, 0.0),
        ];
        let pl = Plane {
            x: 0.0,
            y: 0.0,
            z: 1.0,
            w: 0.0,
        };
        // Quad A verts at pool 0 (ring 0,1,2,3), Quad B verts at pool 4.
        // Quad B ring 1,4,5,2 (CCW): its edge (2->1) reverses A's edge (1->2) — opposite winding,
        // the correct adjacency, so pass 2 links them.
        m.verts = vec![
            BspVert {
                i_vertex: 0,
                i_side: -1,
            },
            BspVert {
                i_vertex: 1,
                i_side: -1,
            },
            BspVert {
                i_vertex: 2,
                i_side: -1,
            },
            BspVert {
                i_vertex: 3,
                i_side: -1,
            },
            BspVert {
                i_vertex: 1,
                i_side: -1,
            },
            BspVert {
                i_vertex: 4,
                i_side: -1,
            },
            BspVert {
                i_vertex: 5,
                i_side: -1,
            },
            BspVert {
                i_vertex: 2,
                i_side: -1,
            },
        ];
        m.nodes = vec![leaf_node(pl, 0, 4), leaf_node(pl, 4, 4)];

        build_side_links(&mut m);

        assert_eq!(m.num_shared_sides, 5, "one shared edge -> id 4 allocated");
        // A's edge 1->2 stores its side on vertex 2 (ring pos 2, global 2).
        // B's edge 1..2 reversed: ring is 2,5,4,1; the edge whose endpoints are {1,2} is (4->1)?
        // The pair is matched on point indices; exactly two verts carry side 4.
        let carriers: Vec<usize> = (0..m.verts.len())
            .filter(|&i| m.verts[i].i_side == 4)
            .collect();
        assert_eq!(carriers.len(), 2, "exactly two verts carry the shared side");
    }

    /// A vertex sitting on another polygon's edge LINE (within the ±0.25 perpendicular band + the
    /// midpoint capsule) is inserted (the real `Editor.dll 0x326fc` weld — a point-on-edge-interior
    /// test using `E × N`; see also `tjunction_welds_mid_edge_interior` for a deep-interior weld).
    #[test]
    fn tjunction_inserts_near_endpoint() {
        // Big quad P with a LONG bottom edge (0,0)->(1000,0), short 10-tall sides.  Point Q=(1000,1)
        // is a T-vertex from an adjacent face sitting 1 uu inside P's bottom-right corner.  It lies
        // exactly ON P's RIGHT edge line (x=1000), perpendicular distance 0, at y=1 inside the [0,10]
        // segment — so it is spliced into P's ring at the right edge.  Q is 1 uu from every P vertex,
        // so `merge_near_points` (0.25 radius) leaves it distinct.
        let mut m = Model::default();
        m.points = vec![
            Vec3::new(0.0, 0.0, 0.0),      // 0
            Vec3::new(1000.0, 0.0, 0.0),   // 1
            Vec3::new(1000.0, 10.0, 0.0),  // 2
            Vec3::new(0.0, 10.0, 0.0),     // 3
            Vec3::new(1000.0, 1.0, 0.0),   // 4  <- T-vertex near corner 1
            Vec3::new(1000.0, 50.0, 0.0),  // 5  } two more Q verts so Q's ring drives AddPointLink
            Vec3::new(900.0, 1.0, 0.0),    // 6  }   with point 4 as an endpoint
        ];
        let pl = Plane {
            x: 0.0,
            y: 0.0,
            z: 1.0,
            w: 0.0,
        };
        // P ring: 0,1,2,3.  Q ring: 4,5,6 (coplanar with P, chained via i_plane).
        m.verts = vec![
            BspVert { i_vertex: 0, i_side: -1 },
            BspVert { i_vertex: 1, i_side: -1 },
            BspVert { i_vertex: 2, i_side: -1 },
            BspVert { i_vertex: 3, i_side: -1 },
            BspVert { i_vertex: 4, i_side: -1 },
            BspVert { i_vertex: 5, i_side: -1 },
            BspVert { i_vertex: 6, i_side: -1 },
        ];
        // node 0 = P (root), node 1 = Q coplanar with P.  Root plane is P's plane, so any point on
        // z=0 has dot 0 -> the descent walks the coplanar chain 0 -> 1.
        let mut p_node = leaf_node(pl, 0, 4);
        p_node.i_plane = 1; // coplanar chain P -> Q
        let q_node = leaf_node(pl, 4, 3);
        m.nodes = vec![p_node, q_node];

        let before = m.verts.len();
        let inserted = eliminate_tjunctions(&mut m);
        assert!(
            inserted >= 1,
            "the near-endpoint T-vertex (1000,1) must be inserted into P's edge"
        );
        // Each insertion APPENDS a fresh (nv+1)-vertex ring at the end and orphans the old ring
        // (byte-faithful to the editor's 0x31920), so the pool grows by more than `inserted`.
        assert!(m.verts.len() > before);
        // P (node 0) now contains point 4 as a vertex (inserter appended P's grown ring at the end).
        let n0 = &m.nodes[0];
        let base = n0.i_vert_pool;
        let ring: Vec<i32> = (0..n0.num_vertices)
            .map(|j| m.verts[(base + j) as usize].i_vertex)
            .collect();
        assert!(
            ring.contains(&4),
            "P's ring gained the T-vertex: {ring:?}"
        );
    }

    /// A point in the deep INTERIOR of another polygon's edge IS welded — that is exactly the
    /// T-junction `bspOptGeom` eliminates.  Mirrors the editor inserter-oracle case (node 1): the
    /// point sits on the edge line (perpendicular distance 0) far from either endpoint, which the
    /// OLD along-edge reading wrongly rejected at `proj <= -0.25`.  Guards against regressing to it.
    #[test]
    fn tjunction_welds_mid_edge_interior() {
        let mut m = Model::default();
        m.points = vec![
            Vec3::new(0.0, 0.0, 0.0),    // 0
            Vec3::new(20.0, 0.0, 0.0),   // 1
            Vec3::new(20.0, 10.0, 0.0),  // 2
            Vec3::new(0.0, 10.0, 0.0),   // 3
            Vec3::new(10.0, 0.0, 0.0),   // 4  <- exact MID-EDGE of P's edge 0->1 (perp dist 0)
            Vec3::new(10.0, -10.0, 0.0), // 5
            Vec3::new(5.0, -10.0, 0.0),  // 6
        ];
        let pl = Plane { x: 0.0, y: 0.0, z: 1.0, w: 0.0 };
        m.verts = vec![
            BspVert { i_vertex: 0, i_side: -1 },
            BspVert { i_vertex: 1, i_side: -1 },
            BspVert { i_vertex: 2, i_side: -1 },
            BspVert { i_vertex: 3, i_side: -1 },
            BspVert { i_vertex: 4, i_side: -1 },
            BspVert { i_vertex: 5, i_side: -1 },
            BspVert { i_vertex: 6, i_side: -1 },
        ];
        let mut p_node = leaf_node(pl, 0, 4);
        p_node.i_plane = 1;
        let q_node = leaf_node(pl, 4, 3);
        m.nodes = vec![p_node, q_node];

        let before = m.verts.len();
        let inserted = eliminate_tjunctions(&mut m);
        assert_eq!(inserted, 1, "the mid-edge interior point is welded into P's edge");
        assert!(m.verts.len() > before);
        // P (node 0) now contains point 4 spliced into its bottom edge (ring pos 1).
        let n0 = &m.nodes[0];
        let base = n0.i_vert_pool;
        let ring: Vec<i32> = (0..n0.num_vertices)
            .map(|j| m.verts[(base + j) as usize].i_vertex)
            .collect();
        assert_eq!(ring, vec![0, 4, 1, 2, 3], "point 4 spliced between corners 0 and 1");
    }

    /// Build the mid-edge-weld fixture with P's ring padded to `nv` vertices (top/left edges
    /// subdivided with colinear points).  Point index of the weldable T-vertex is `nv`.
    fn capped_fixture(nv: i32) -> Model {
        let mut m = Model::default();
        let t = (nv - 5) as usize; // top-edge interior subdivisions
        let mut pts = vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(20.0, 0.0, 0.0),
            Vec3::new(20.0, 10.0, 0.0),
        ];
        for k in 0..t {
            pts.push(Vec3::new(19.0 - 18.0 * (k as f32) / (t as f32 - 1.0), 10.0, 0.0));
        }
        pts.push(Vec3::new(0.0, 10.0, 0.0));
        pts.push(Vec3::new(0.0, 5.0, 0.0));
        let weld = pts.len() as i32; // == nv
        pts.push(Vec3::new(10.0, 0.0, 0.0)); // T-vertex mid P's bottom edge
        pts.push(Vec3::new(10.0, -10.0, 0.0));
        pts.push(Vec3::new(5.0, -10.0, 0.0));
        m.points = pts;
        let pl = Plane { x: 0.0, y: 0.0, z: 1.0, w: 0.0 };
        m.verts = (0..nv + 3).map(|i| BspVert { i_vertex: i, i_side: -1 }).collect();
        let mut p_node = leaf_node(pl, 0, nv);
        p_node.i_plane = 1;
        let q_node = leaf_node(pl, nv, 3);
        m.nodes = vec![p_node, q_node];
        assert_eq!(weld, nv);
        m
    }

    /// The inserter's ring-size cap (`0x31960`): a weld that would push `NumVertices` past 15 is
    /// refused ("Node side limit reached") — no splice, no pool growth.  At nv=14 the same weld
    /// lands (boundary control).  Live-pinned on full UNATCO: the editor refuses 22 welds, all on
    /// rings at nv=15; uncapped native grew those rings to 18/23.
    #[test]
    fn tjunction_weld_refused_at_ring_cap() {
        let mut m = capped_fixture(14);
        let before = m.verts.len();
        assert_eq!(eliminate_tjunctions(&mut m), 1, "nv=14 -> weld lands (15 <= cap)");
        assert!(m.verts.len() > before);
        assert_eq!(m.nodes[0].num_vertices, 15);

        let mut m = capped_fixture(15);
        let before = m.verts.len();
        assert_eq!(eliminate_tjunctions(&mut m), 0, "nv=15 -> weld refused (would exceed 15)");
        assert_eq!(m.verts.len(), before, "refusal must not touch the pool");
        assert_eq!(m.nodes[0].num_vertices, 15);
    }

    /// merge_near_points is a no-op when all points are far apart.
    #[test]
    fn merge_is_noop_when_far() {
        let mut m = Model::default();
        m.points = vec![Vec3::new(0.0, 0.0, 0.0), Vec3::new(5.0, 0.0, 0.0)];
        m.verts = vec![
            BspVert {
                i_vertex: 0,
                i_side: -1,
            },
            BspVert {
                i_vertex: 1,
                i_side: -1,
            },
        ];
        merge_near_points(&mut m);
        assert_eq!(m.verts[0].i_vertex, 0);
        assert_eq!(m.verts[1].i_vertex, 1);
    }

    /// The ring fix-up at `merge_near_points`' tail (DISASM `Editor.dll 0x10033f29-0x10033f9b`;
    /// spike `2026-09-03-verts-points-residual`): cyclic index-equal ring verts are dropped
    /// count-only (slots stay allocated), survivors compact down within the ring's own slots,
    /// and a ring left under 3 is zeroed. Golden-pinned on `04_NYC_Underground` nodes
    /// 1586/1744 (3 slots, nv=0) and 1745 (4 slots, nv=3 with the survivors compacted).
    #[test]
    fn ring_fixup_compacts_index_equal_verts_and_zeroes_degenerate_rings() {
        let mut m = Model::default();
        // Points 0/1 are 0.1 apart (< 0.25) so the remap folds 1 -> 0, creating the wrap dup;
        // the second ring's adjacent dup (2,2) needs no merge to trigger the fix-up.
        m.points = vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(0.1, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
        ];
        let mk = |iv: i32, side: i32| BspVert { i_vertex: iv, i_side: side };
        // Ring A (pool 0..3): [0, 2, 1] -> after remap [0, 2, 0]: wrap dup -> 2 survivors -> nv=0.
        // Ring B (pool 3..7): [2, 3, 3, 4]: adjacent dup -> [2, 3, 4] compacted, nv=3, slot 4 kept.
        m.verts = vec![
            mk(0, -1), mk(2, -1), mk(1, -1),
            mk(2, 10), mk(3, 11), mk(3, 12), mk(4, 13),
        ];
        let pl = Plane { x: 0.0, y: 0.0, z: 1.0, w: 0.0 };
        m.nodes = vec![leaf_node(pl, 0, 3), leaf_node(pl, 3, 4)];

        merge_near_points(&mut m);

        assert_eq!(m.nodes[0].num_vertices, 0, "wrap-dup ring collapses under 3 -> zeroed");
        assert_eq!(m.nodes[1].num_vertices, 3, "adjacent dup dropped count-only");
        assert_eq!(m.verts.len(), 7, "pool slots are never shrunk");
        assert_eq!(
            (m.verts[3].i_vertex, m.verts[4].i_vertex, m.verts[5].i_vertex),
            (2, 3, 4),
            "survivors compact down within the ring's own slots"
        );
        assert_eq!(
            (m.verts[3].i_side, m.verts[4].i_side, m.verts[5].i_side),
            (10, 11, 13),
            "iSide travels with its surviving iVertex pair"
        );
    }
}
