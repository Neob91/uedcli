//! NEW, FEATURE-FLAGGED incremental CSG core — a faithful port of UnrealEd's `bspBrushCSG`
//! (`Editor.dll 0x355e0`) driving toward a byte-identical `UModel`.  This is OPT-IN and PARALLEL
//! to the default `build::build_geometry_from_brushes`; the default path is never touched.
//!
//! Reference decode: `dev/docs/spikes/2026-07-15-native-materialize/sections/82-bspbrushcsg-port-decode.md`
//! + `re-raw-zones/bspbrushcsg-filter-decode.md` + `bspbuild-splitpolylist-decode.md`.
//!
//! Unlike the default path (which carries the world as a flat surface list and defers solidity
//! to a point-in-solid oracle), this core GROWS the world BSP incrementally: each brush face is
//! filtered down the growing tree and the surviving OUTSIDE/INSIDE fragment is added as a node
//! with the brush's OWN face plane (`bspAddNode`) — the watertightness (NO bevel planes, §0),
//! then the world faces interior to the brush are cut (`FilterWorldThroughBrush`).  After all
//! structural brushes: `bspRepartition` (rebuild the tree from the fat fragment soup); then the
//! semisolid second layer; then finalize (leaves/zones/bounds).

use crate::fpoly::{
    safe_normal_slow, transform_vector_by, FPoly, Split, MAX_VERTICES, PF_SPLIT_MARKER,
};
use crate::model::{BspNode, BspSurf, BspVert, BuildError, Model, Plane, Vec3};
use crate::{build, csg, passes, zones};

const NF_IS_NEW: u8 = 0x20;
const THRESH_POINTS_ARE_SAME: f32 = 0.002;
/// Looser vertex-coincidence box bound for the `try_to_merge` step-3 edge-neighbour test.  The
/// same SAME-vs-NEAR dichotomy `build.rs` uses for point pooling.
const THRESH_POINTS_ARE_NEAR: f32 = 0.015;
const THRESH_NORMALS_ARE_SAME: f32 = 2.0e-5;
/// `bspAddVector` texture-axis dedup tolerance (DISASM `Editor.dll 0x35530`, spec §3.10). The editor
/// keeps near-parallel texture axes distinct below this; native previously used 0.001 and pooled
/// axes the editor keeps (OceanLab N3 Brush779 rotated-tessellated subtract).
const THRESH_VECTORS_ARE_NEAR: f32 = 4.0e-4;
/// `bspBuild` stamps every poly it partitions, and the bit reaches the saved `Model.Polys`.
const PF_ED_PROCESSED: u32 = 0x4000_0000;

// ENodePlace
const NODE_BACK: i32 = 0;
const NODE_FRONT: i32 = 1;
const NODE_PLANE: i32 = 2;
const NODE_ROOT: i32 = 3;

// EPolyNodeFilter
const F_OUTSIDE: i32 = 0;
const F_INSIDE: i32 = 1;
const F_COPLANAR_OUTSIDE: i32 = 2;
const F_COPLANAR_INSIDE: i32 = 3;
const F_COSPATIAL_FACING_OUT: i32 = 5;
const F_COSPATIAL_FACING_IN: i32 = 4;

// REPARTITION FindBestSplit params (byte-verified 2026-07-17,
// re-raw-zones/findbestsplit-params-decode.md): bspRepartition pushes BalancePacked=0xc, Opt=GOOD(1).
//   Balance    = 0xc & 0xff        = 12
//   PortalBias = (0xc >> 8) & 0xff = 0
//   Opt=GOOD   => candidate/counting stride Inc = max(NumPolys/20, 1)  (OPTIMAL would be stride 1).
const BALANCE: i32 = 12;
const PORTAL_BIAS: i32 = 0;

// The temp-brush convex partition (`build_brush_temp_bsp`) is a *different* bspBuild call — the convex
// tree `FilterWorldThroughBrush` filters each straddling world face through.  Byte-verified 2026-07-17
// (findbestsplit-params-decode.md Evidence 4: `bspBrushCSG @0x35b83` calls
// `bspBuild(TempModel, Opt=0/LAME, BalancePacked=0, RebuildSimplePolys=1)`):
//   Balance = 0, PortalBias = 0   => Score = 100*Splits (pure split-minimization, no balance term)
//   Opt = LAME                    => candidate stride Inc = max(NumPolys/4, 1)
// This replaced the historical OPTIMAL/50/70 guess.  For a convex brush the change is EMPIRICALLY
// SOUP-NEUTRAL (verified full-castle + N=30..33, §82 §10.5): kept because it is the value the binary
// uses, NOT because it moves any divergence.  The pinned N=33 roof under-merge is an incremental
// world-tree ORDER issue in LOOP-2 (`bsp_filter_fpoly`), not this temp brush — see §82 §10.5.
const TEMP_BALANCE: i32 = 0;
const TEMP_PORTAL_BIAS: i32 = 0;

/// `EBspOptimization` — selects the `FindBestSplit` candidate/counting stride (`FindBestSplit`
/// `0x335d0`; stride computed at `0x3369e`..`0x336c8`, live-verified 2026-07-18 vs `fbs_stride_oracle`
/// which read the running editor's root `bspRepartition` call: `Opt=1 (GOOD), Balance=12, stride=9`
/// for `NumPolys=199`): OPTIMAL (opt=2) scans every poly (stride 1), GOOD (opt=1) strides
/// **`NumPolys/20`**, LAME (opt=0) strides `NumPolys/4`.  The from-scratch world repartition uses
/// GOOD; the brush temp BSP uses LAME (oracle: opt=0 there).
///
/// The GOOD stride is the compiler idiom `imul 0x66666667; sar edx,3` = `(NumPolys * 0x66666667) >>
/// 35` = `NumPolys/20` — NOT `NumPolys/10` (that idiom shifts by 34).  The earlier `/10` reading
/// picked stride 19 for 199 polys, which never lands on the editor's root splitter (soup idx 90 =
/// 9×10); `/20` = stride 9 makes `FindBestSplit` pick soup idx 90 exactly (the editor's Nodes[0]).
#[derive(Clone, Copy)]
enum Opt {
    Lame,
    Good,
}

impl Opt {
    /// `Inc = max(base, 1)` where base is `NumPolys/4` (LAME) or `NumPolys/20` (GOOD, via the exact
    /// `(n * 0x66666667) >> 35` engine idiom).
    fn stride(self, num_polys: usize) -> usize {
        match self {
            Opt::Lame => (num_polys / 4).max(1),
            Opt::Good => (((num_polys as u64 * 0x6666_6667) >> 35) as usize).max(1),
        }
    }
}

// --- pooling (bspAddPoint / bspAddVector) — copied from build.rs to keep it untouched --------

// --- STAGE-1 POINT-DEDUP TRACE (UEDCLI_BSPCSG_POINT_TRACE) — env-gated, default path byte-unchanged.
// Faithful-dedup rewrite, Stage 1 (spike 2026-09-05-faithful-dedup-fix-attempt/stage1). Emits, per
// `bsp_add_point_tol` call: the query, native's SNAP-vs-ADD decision + target idx/value, the global
// nearest, and — the crux — whether that target point is REACHABLE in native's CURRENT incremental
// tree (DFS from root over iFront/iBack/iPlane, testing each reachable node's surf-base at +0x1c and
// its vert-pool, exactly what `UModel::FindNearestVertex` visits). This is the native-side half of
// the divergence pin: at the divergent surf-base add native SNAPS to a reachably-wired point; the
// editor's FNV MISS means its incremental tree does NOT reach that point at that moment.
//   UEDCLI_BSPCSG_POINT_TRACE=1|all         emit every point add
//   UEDCLI_BSPCSG_POINT_TRACE=x,y,z,r       emit only adds whose query is within r of (x,y,z)
enum PtTrace {
    Off,
    All,
    Near([f32; 3], f32),
}

fn pt_trace() -> &'static PtTrace {
    static SPEC: std::sync::OnceLock<PtTrace> = std::sync::OnceLock::new();
    SPEC.get_or_init(|| match std::env::var("UEDCLI_BSPCSG_POINT_TRACE") {
        Err(_) => PtTrace::Off,
        Ok(s) if s == "1" || s == "all" => PtTrace::All,
        Ok(s) => {
            let f: Vec<f32> = s.split(',').filter_map(|t| t.trim().parse().ok()).collect();
            if f.len() == 4 {
                PtTrace::Near([f[0], f[1], f[2]], f[3])
            } else {
                PtTrace::All
            }
        }
    })
}

/// Nodes reachable from root (0) over iFront/iBack/iPlane — the descent `FindNearestVertex` walks.
fn reachable_nodes(model: &Model) -> Vec<bool> {
    let mut seen = vec![false; model.nodes.len()];
    if model.nodes.is_empty() {
        return seen;
    }
    let mut stack = vec![0i32];
    while let Some(ni) = stack.pop() {
        if ni < 0 {
            continue;
        }
        let u = ni as usize;
        if u >= seen.len() || seen[u] {
            continue;
        }
        seen[u] = true;
        let n = &model.nodes[u];
        stack.push(n.i_front);
        stack.push(n.i_back);
        stack.push(n.i_plane);
    }
    seen
}

/// Among reachable nodes, which wire point `ti` as a surf-base (`Surf.pBase`) or a vert-pool entry
/// (`BspVert.iVertex`) — the two places FNV's helper tests a point.
fn point_wired(model: &Model, seen: &[bool], ti: i32) -> (Vec<i32>, Vec<i32>) {
    let mut sb = vec![];
    let mut vp = vec![];
    for (i, n) in model.nodes.iter().enumerate() {
        if !seen[i] {
            continue;
        }
        if n.i_surf >= 0 && model.surfs[n.i_surf as usize].p_base == ti {
            sb.push(i as i32);
        }
        if n.i_vert_pool >= 0 && n.num_vertices > 0 {
            let (s, c) = (n.i_vert_pool as usize, n.num_vertices as usize);
            if model.verts[s..(s + c).min(model.verts.len())]
                .iter()
                .any(|bv| bv.i_vertex == ti)
            {
                vp.push(i as i32);
            }
        }
    }
    (sb, vp)
}

fn trace_point_add(model: &Model, v: Vec3, tol: f32, hit: Option<i32>) {
    if let PtTrace::Near(c, r) = pt_trace() {
        let d = ((v.x - c[0]).powi(2) + (v.y - c[1]).powi(2) + (v.z - c[2]).powi(2)).sqrt();
        if d > *r {
            return;
        }
    }
    let glob = nearest(&model.points, &v);
    let (gi, gd) = glob.map(|(i, d)| (i as i32, d)).unwrap_or((-1, -1.0));
    let target = hit.unwrap_or(gi);
    let seen = reachable_nodes(model);
    let reach = seen.iter().filter(|b| **b).count();
    let (sb, vp) = if target >= 0 {
        point_wired(model, &seen, target)
    } else {
        (vec![], vec![])
    };
    let tv = if target >= 0 {
        model.points[target as usize]
    } else {
        Vec3::new(0.0, 0.0, 0.0)
    };
    eprintln!(
        "PT tol={:.3} q=({:.6},{:.6},{:.6}) {} target={} tval=({:.6},{:.6},{:.6}) gnear=(idx={},d={:.3e}) reach={}/{} sb={:?} vp={:?}",
        tol, v.x, v.y, v.z,
        if hit.is_some() { "SNAP" } else { "ADD " },
        target, tv.x, tv.y, tv.z, gi, gd, reach, model.nodes.len(), sb, vp
    );
    // Characterize the kept-reachable surf-base nodes: which face (normal / actor / brush-poly),
    // alive?, flags — this is WHAT native keeps reachable that the editor's FNV must not.
    for &ni in &sb {
        let n = &model.nodes[ni as usize];
        let (ia, ibp) = if n.i_surf >= 0 {
            let s = &model.surfs[n.i_surf as usize];
            (s.i_actor, s.i_brush_poly)
        } else {
            (-1, -1)
        };
        eprintln!(
            "   sbnode {} N=({:.5},{:.5},{:.5}) W={:.5} nv={} flags={:#x} iSurf={} iActor={} iBrushPoly={} iFront={} iBack={} iPlane={}",
            ni, n.plane.x, n.plane.y, n.plane.z, n.plane.w, n.num_vertices, n.node_flags,
            n.i_surf, ia, ibp, n.i_front, n.i_back, n.i_plane
        );
    }
    // Full reachable-from-root-0 tree dump (UEDCLI_BSPCSG_POINT_TRACE_TREE) — the structural target
    // for the Stage-3 tree-wiring diff vs the editor's winedbg tree-dump at the same add.
    if std::env::var("UEDCLI_BSPCSG_POINT_TRACE_TREE").is_ok() {
        for (i, r) in seen.iter().enumerate() {
            if !*r {
                continue;
            }
            let n = &model.nodes[i];
            let (pb, pt) = if n.i_surf >= 0 {
                let p = model.surfs[n.i_surf as usize].p_base;
                (p, model.points[p as usize])
            } else {
                (-1, Vec3::new(0.0, 0.0, 0.0))
            };
            let ia = if n.i_surf >= 0 { model.surfs[n.i_surf as usize].i_actor } else { -1 };
            eprintln!(
                "   RN {} N=({:.4},{:.4},{:.4}) W={:.4} iSurf={} pBase={} pt=({:.5},{:.5},{:.5}) iActor={} nv={} f={:#x} iF={} iB={} iP={}",
                i, n.plane.x, n.plane.y, n.plane.z, n.plane.w, n.i_surf, pb, pt.x, pt.y, pt.z,
                ia, n.num_vertices, n.node_flags, n.i_front, n.i_back, n.i_plane
            );
        }
    }
}

// --- FindNearestVertex — the editor's radius-pruned point dedup (Engine.dll 0x1adeb0 / helper -----
// 0x1adb60), used during INCREMENTAL brush CSG (see `fnv_dedup` flag). Faithful port decoded +
// live-validated in spike 2026-09-05-faithful-dedup-fix-attempt (stages 2/2b): a BSP descent over the
// LIVE `model.nodes` from root 0 that PRUNES a subtree when the query is beyond the current radius R
// of the splitting plane — so a within-tol point behind a far plane is MISSED, exactly where native's
// old linear scan wrongly SNAPPED (the x=448 / WanChai-step divergence class). `descent_sim.py` in the
// spike reproduces this over the committed editor + native tree dumps; `test_fnv_*` pin it in Rust.

/// True only for the duration of `bsp_brush_csg` (incremental CSG). Repartition (`bsp_build`) keeps the
/// linear scan over the retained points pool — the editor's `EmptyModel(0,0)` keeps Points across the
/// rebuild, and native's from-scratch re-add matches it by coordinate; a descent over the empty
/// rebuilding tree would append duplicates.
thread_local! {
    static FNV_DEDUP: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

/// RAII: enable the FindNearestVertex dedup for the current scope, restoring the previous value on drop.
struct FnvDedupGuard(bool);
impl FnvDedupGuard {
    fn enable() -> Self {
        FnvDedupGuard(FNV_DEDUP.with(|c| c.replace(true)))
    }
}
impl Drop for FnvDedupGuard {
    fn drop(&mut self) {
        FNV_DEDUP.with(|c| c.set(self.0));
    }
}

/// Child convention for the descent: false (default) = native's live CSG tree has iFront/iBack SWAPPED
/// vs the engine; true = engine convention (a static engine-convention tree, e.g. the editor dump in
/// tests). Thread-local so a test can pick per-tree.
thread_local! {
    static FNV_ENGINE_CHILDREN: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}
fn fnv_engine_children() -> bool {
    FNV_ENGINE_CHILDREN.with(|c| c.get())
}

/// RAII: run the descent in the ENGINE child convention for the current scope. The zone pass gets a
/// tree `swap_node_children` has already put in that convention, unlike live incremental CSG.
pub(crate) struct FnvEngineChildrenGuard(bool);
impl FnvEngineChildrenGuard {
    pub(crate) fn enable() -> Self {
        FnvEngineChildrenGuard(FNV_ENGINE_CHILDREN.with(|c| c.replace(true)))
    }
}
impl Drop for FnvEngineChildrenGuard {
    fn drop(&mut self) {
        FNV_ENGINE_CHILDREN.with(|c| c.set(self.0));
    }
}

/// Test the point `p_idx` against the query, shrinking `(best_i, best_d=R)` if it is the new nearest
/// within R. Editor summation order `(dy² + dx²) + dz²` (0x1adccb..0x1adccf); strict `d² < R²`.
fn fnv_consider(model: &Model, v: &Vec3, p_idx: i32, best_i: &mut i32, best_d: &mut f32) {
    if p_idx < 0 {
        return;
    }
    let p = &model.points[p_idx as usize];
    let (dx, dy, dz) = (v.x - p.x, v.y - p.y, v.z - p.z);
    let d2 = (dy * dy + dx * dx) + dz * dz;
    if d2 < *best_d * *best_d {
        *best_d = d2.sqrt();
        *best_i = p_idx;
    }
}

/// Points a caller is in the middle of pooling onto nodes it has already linked to `owner`'s coplanar
/// chain but that are not yet in `Model.Nodes` — Pass D's landing rings (see `find_nearest_vertex`).
/// Considered at the END of `owner`'s chain walk, which is where `bspAddNode(NODE_Plane)` links them.
pub(crate) struct PendingChainRing<'a> {
    pub owner: i32,
    pub points: &'a [i32],
}

/// The recursive descent (helper 0x1adb60): iBack recursed when `pd >= -R`; the node + its coplanar
/// (iPlane) chain's surf-base + vert-pool tested when `-R < pd <= R`; iFront tail-looped when `pd <= R`.
/// R (`best_d`) shrinks to the nearest hit so far, tightening the prune.
fn fnv_recurse(
    model: &Model,
    v: &Vec3,
    i_node_start: i32,
    best_i: &mut i32,
    best_d: &mut f32,
    pending: Option<&PendingChainRing>,
) {
    // Native's INCREMENTAL tree is in the CSG child convention (iFront/iBack swapped vs the engine's,
    // which `swap_node_children` converts at the end); the editor's FindNearestVertex walks the engine
    // convention. So during live CSG the descent's near/far children are swapped: recurse iFront when
    // pd >= -R, tail iBack when pd <= R. (Static tree-dump tests use `fnv_engine_children`.)
    let mut i_node = i_node_start;
    while i_node != -1 {
        let n = &model.nodes[i_node as usize];
        let pd = n.plane.x * v.x + n.plane.y * v.y + n.plane.z * v.z - n.plane.w;
        let (near_back, far_front) = if fnv_engine_children() {
            (n.i_back, n.i_front)
        } else {
            (n.i_front, n.i_back)
        };
        if pd >= -*best_d && near_back != -1 {
            fnv_recurse(model, v, near_back, best_i, best_d, pending);
        }
        if pd > -*best_d && pd <= *best_d {
            let mut c = i_node;
            let mut chain_has_pending_owner = false;
            while c != -1 {
                chain_has_pending_owner |= pending.is_some_and(|p| p.owner == c);
                let cn = &model.nodes[c as usize];
                // Same defensive bound as the vert pool below: never fires on a well-formed tree,
                // but a node whose iSurf outruns the surf array must not panic out of the CLI.
                if let Some(s) = usize::try_from(cn.i_surf).ok().and_then(|i| model.surfs.get(i)) {
                    fnv_consider(model, v, s.p_base, best_i, best_d);
                }
                // Vert-pool guarded by NumVertices only (disasm-faithful); the extra bounds guard
                // never fires on a well-formed tree but avoids a panic -> CLI traceback on bad input.
                if cn.i_vert_pool >= 0 {
                    for k in 0..cn.num_vertices {
                        let vi = (cn.i_vert_pool + k) as usize;
                        if vi >= model.verts.len() {
                            break;
                        }
                        fnv_consider(model, v, model.verts[vi].i_vertex, best_i, best_d);
                    }
                }
                c = cn.i_plane;
            }
            if chain_has_pending_owner {
                for &p_idx in pending.expect("owner matched").points {
                    fnv_consider(model, v, p_idx, best_i, best_d);
                }
            }
        }
        i_node = if pd <= *best_d { far_front } else { -1 };
    }
}

/// `UModel::FindNearestVertex` — nearest `Model.Points` index within `tol` reachable-and-unpruned from
/// root 0, or `None` (empty tree, or nothing within the pruned descent's reach). See the module note.
pub(crate) fn find_nearest_vertex(model: &Model, v: Vec3, tol: f32) -> Option<usize> {
    find_nearest_vertex_pending(model, v, tol, None)
}

/// `find_nearest_vertex` plus the caller's not-yet-materialised chain nodes (`PendingChainRing`).
/// `bspAddNode` adds its node to `Model.Nodes`, links it (`Editor.dll 0x100352c5`), zeroes
/// `NumVertices` (`0x100352d4`) and then increments it INSIDE the fill loop (`0x10035348`) right
/// after writing each slot — so a point pooled earlier in the same fill, and every ring an earlier
/// landing of the same chain node left behind, is already visible to the next `bspAddPoint`.
pub(crate) fn find_nearest_vertex_pending(
    model: &Model,
    v: Vec3,
    tol: f32,
    pending: Option<&PendingChainRing>,
) -> Option<usize> {
    let mut best_i: i32 = -1;
    let mut best_d: f32 = tol;
    if model.nodes.is_empty() {
        // 0x1adee3: Model->Nodes.Num == 0 -> immediate MISS. A pending ring is a node `bspAddNode`
        // has already added, so it still counts against that test and stays testable.
        for &p_idx in pending.map_or(&[][..], |p| p.points) {
            fnv_consider(model, &v, p_idx, &mut best_i, &mut best_d);
        }
        return (best_i >= 0).then_some(best_i as usize);
    }
    fnv_recurse(model, &v, 0, &mut best_i, &mut best_d, pending);
    if best_i >= 0 {
        Some(best_i as usize)
    } else {
        None
    }
}

fn bsp_add_point(model: &mut Model, v: Vec3) -> i32 {
    // FindNearestVertex threshold 0.002 (fp-classification-sites §7).
    bsp_add_point_tol(model, v, THRESH_POINTS_ARE_SAME)
}

/// `bspAddPoint` (`0x35430`) with an explicit `FindNearestVertex` threshold. The real editor selects
/// the threshold by `bspAddPoint`'s `arg_2` flag (`0x3545c`: `arg_2 ? 0.002 : 0.015`, both f32
/// constants read from `.rdata`, decoded 2026-09-02): the surf `pBase` add passes `1` → **0.002
/// (SAME)**, but the node vertex-RING add (`bspAddNode 0x352fd`, `push 0`) passes `0` → **0.015
/// (NEAR)** (see `ring_point_tol` below, used by the ring loop in `bsp_add_node`).
fn bsp_add_point_tol(model: &mut Model, v: Vec3, tol: f32) -> i32 {
    // Incremental CSG uses the editor's radius-pruned FindNearestVertex descent at BOTH thresholds —
    // `bspAddPoint` picks 0.002/0.015 from its `Exact` arg and then calls FNV unconditionally
    // (0x35465..0x35498). That branch is faithful.
    //
    // The repartition branch is NOT, and is a known STOPGAP (board
    // `repartition-point-dedup-still-uses-a-linear`). The editor has no second rule: on an FNV miss
    // `bspAddPoint` calls `AddThing(&Points, V, Thresh, !FastRebuild)` (`0x354d1`-`0x354ed`), and
    // `csgRebuild` sets `FastRebuild = 1` (`0x4a69f`-`0x4a6a8`), so during a rebuild the check
    // argument is 0 and `AddThing` (`0x31ae0`) appends WITHOUT scanning. Faithful = descent, else
    // append. Native instead scans the retained pool, because an earlier descent port over the
    // rebuilding tree over-created points (`native-materialize-findings.md`, garage-pool-snap rounds
    // 2-3) — with the pBase/chain candidates it was then missing.
    //
    // Within that stand-in, NEAREST beats FIRST: the retained pool holds the very point the editor's
    // descent finds, and taking the first point inside the threshold instead picks a neighbour's when
    // two are closer to each other than the threshold. Island's `Brush1359` and `Brush1355` oblique
    // faces have bases 0.001953125 apart, so `Brush1359`'s surf took `Brush1355`'s point as its
    // `pBase` and every Pass-D cut against that plane came out ~2 ULP off (board
    // `island-n5-n12-pre-existing-model2-orphan-vert-4`).
    let hit: Option<i32> = if FNV_DEDUP.with(|c| c.get()) {
        find_nearest_vertex(model, v, tol).map(|i| i as i32)
    } else {
        match nearest(&model.points, &v) {
            Some((i, dist)) if dist < tol => Some(i as i32),
            _ => None,
        }
    };
    if !matches!(pt_trace(), PtTrace::Off) {
        trace_point_add(model, v, tol, hit);
    }
    match hit {
        Some(i) => i,
        None => {
            model.points.push(v);
            (model.points.len() - 1) as i32
        }
    }
}

/// The node vertex-RING `bspAddPoint` threshold: 0.015 (NEAR), the real editor's value
/// (`bspAddNode 0x352fd push 0`). Corpus-measured 2026-09-02 (see the findings ledger, "full-corpus
/// RING_NEAR/MERGE_NEIGHBOR_SAME A/B measurement"): 0 currently-exact levels lose exactness, 5
/// improve, 3 regress on verts only, 1 (Vandenberg Gas) is a genuine cross-count tradeoff. Owner
/// approved shipping as default 2026-09-02.
fn ring_point_tol() -> f32 {
    THRESH_POINTS_ARE_NEAR
}

/// `bspAddVector` (`Editor.dll 0x35530`): unlike `bspAddPoint` it never consults the tree — it calls
/// `AddThing(&Model->Vectors, V, Thresh, Check=1)` (`0x31ae0`, `push 1`), whose scan takes the FIRST
/// entry inside the threshold, not the nearest.
fn bsp_add_vector(model: &mut Model, v: Vec3, exact: bool) -> i32 {
    let tol = if exact {
        THRESH_NORMALS_ARE_SAME
    } else {
        THRESH_VECTORS_ARE_NEAR
    };
    for (i, p) in model.vectors.iter().enumerate() {
        if v.sub(p).size() < tol {
            return i as i32;
        }
    }
    model.vectors.push(v);
    (model.vectors.len() - 1) as i32
}

/// `(index, distance)` of the entry in `pool` nearest `v` — the real `FindNearestVertex`'s
/// selection rule. It selects on SQUARED distance and `appSqrt`s only the winner (`Engine.dll`
/// `0x1adcd3` compares squared, `0x1adced` sqrts the winner), so the caller's accept test compares a
/// real distance against a real threshold (spec §3.10). Selecting on the sqrt of every candidate
/// would be the same choice at N times the cost.
fn nearest(pool: &[Vec3], v: &Vec3) -> Option<(usize, f32)> {
    let (i, d2) = pool
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let d = v.sub(p);
            (i, d.dot(&d))
        })
        .min_by(|a, b| a.1.partial_cmp(&b.1).expect("pool coordinate is NaN"))?;
    Some((i, d2.sqrt()))
}

/// Derive `NodeFlags` from a surf's PolyFlags (matches build.rs::derive_nf).
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

fn default_texture_axes(n: Vec3) -> (Vec3, Vec3) {
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

fn alloc_surf(model: &mut Model, edpoly: &FPoly) -> i32 {
    let pf = edpoly.poly_flags & 0x3cff_ffff;
    let p_base = bsp_add_point(model, edpoly.base);
    let v_normal = bsp_add_vector(model, edpoly.normal, true);
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
        pan: edpoly.pan,
        i_light_map: -1,
    });
    (model.surfs.len() - 1) as i32
}

/// `bspAddNode` (`0x34e80`): emit a node (+ on demand a shared surf + pooled verts) for `edpoly`,
/// linked under `i_parent` per `place`.  Coplanar-chain walk + >16-vert storage split + surf
/// sharing via `iLink==Surfs.Num`.  Returns the new node index.  Started as a copy of `build.rs`'s,
/// and the two have since diverged: only this one seeds `iZone`/`iLeaf` from the parent
/// (`inherit_parent_leaf_zone`).  `build.rs`'s path does not need it — its `finalize_leaves_and_bbox`
/// runs the zone pass LAST, so no node there escapes Pass A/D.
// ORACLE INSTRUMENTATION (UEDCLI_BSPCSG_TREE_DUMP) — env-gated, default path byte-unchanged.
// Logs each INCREMENTAL world-tree node add (LOOP-2 leaf_func + FWTB wtb_leaf) to diff native's
// incremental bspBrushCSG tree against the editor-tree oracle (sections/82 §10.6-§10.8).  `PP`/`pnv`
// (the parent node's plane + NumVertices) added §10.8 to expose the structural (parent-linkage)
// divergence `compare_trees.py` cannot see; consumed by `harness/editor-tree-oracle/oracle_pp.py`.
fn trace_node_add(model: &Model, phase: &str, i_parent: i32, place: i32, node_flags: u8, edpoly: &FPoly, i_node: i32) {
    if std::env::var("UEDCLI_BSPCSG_TREE_DUMP").is_ok() {
        let n = &edpoly.normal;
        let b = &edpoly.base;
        // parent plane (structural-divergence probe): the plane the fragment attaches under.
        let (pp, pnv) = if i_parent >= 0 && (i_parent as usize) < model.nodes.len() {
            let pn = &model.nodes[i_parent as usize];
            (pn.plane, pn.num_vertices)
        } else {
            (Plane { x: 0.0, y: 0.0, z: 0.0, w: 0.0 }, -1)
        };
        eprintln!(
            "NADD phase={} node={} parent={} place={} flags={:#x} ilink={} actor={} bpoly={} nv={} N={:.5},{:.5},{:.5} B={:.5},{:.5},{:.5} PP={:.5},{:.5},{:.5},{:.5} pnv={}",
            phase, i_node, i_parent, place, node_flags, edpoly.i_link, edpoly.actor, edpoly.i_brush_poly, edpoly.verts.len(),
            n.x, n.y, n.z, b.x, b.y, b.z, pp.x, pp.y, pp.z, pp.w, pnv
        );
    }
}

fn bsp_add_node(
    model: &mut Model,
    mut i_parent: i32,
    place: i32,
    node_flags: u8,
    edpoly: &FPoly,
) -> i32 {
    let mut place = place;
    if place == NODE_PLANE {
        let mut i = i_parent;
        while model.nodes[i as usize].i_plane != -1 {
            i = model.nodes[i as usize].i_plane;
        }
        i_parent = i;
    }

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

    let is_new_surf = edpoly.i_link < 0 || edpoly.i_link as usize >= model.surfs.len();
    let i_surf = if is_new_surf {
        alloc_surf(model, edpoly)
    } else {
        edpoly.i_link
    };

    let surf_pf = model.surfs[i_surf as usize].poly_flags;
    let nf = derive_nf(surf_pf, node_flags);

    let i_vert_pool = model.verts.len() as i32;
    // bspAddPoint each vertex, collapsing CONSECUTIVE duplicates (0x3532a) — a plain FORWARD walk,
    // same as the real `bspAddNode`.
    //
    // Round 15 note (kills round 13's flag-gated reversed walk that lived here): round 9's live
    // "Origin then REVERSED authored ring" `bspAddPoint` sequence is NOT a special insertion rule —
    // it is this same forward walk over a poly whose winding `SubtractBrushFromWorldFunc` had
    // already `Reverse()`d (inward-facing, `leaf_func`'s `e.reverse()`), so on the T3D-authored
    // axis it merely LOOKS reversed. Native reverses in the same place, so the forward walk already
    // reproduces the editor's exact point-insertion order; an extra explicit reversal here
    // double-reversed Subtract rings back to authored-forward order (measured: `DX.dx` base-block
    // trios came out exactly backwards vs golden with it, exact with it removed).
    // Node vertex RING pooling uses the NEAR (0.015) threshold in the real editor (`bspAddNode
    // 0x352fd push 0` → `bspAddPoint arg_2=0`), NOT the SAME (0.002) used for the surf pBase.
    let ring_tol = ring_point_tol();
    let ivs: Vec<i32> =
        edpoly.verts.iter().map(|v| bsp_add_point_tol(model, *v, ring_tol)).collect();
    let mut last_iv: i32 = -1;
    let mut nv = 0i32;
    for &iv in &ivs {
        if iv == last_iv {
            continue;
        }
        model.verts.push(BspVert {
            i_vertex: iv,
            i_side: -1,
        });
        last_iv = iv;
        nv += 1;
    }
    // bspAddNode's post-loop wrap trim [DISASM Editor.dll 0x100353a1-0x100353b8, decoded
    // 2026-09-02]: consecutive-only dedup above doesn't catch a ring whose LAST distinct vertex
    // equals its FIRST (a closed-loop duplicate). The real editor compares the first-pushed pool
    // entry's point index against the last-pushed one and drops the count by one if they match --
    // the vert-pool ARRAY itself is left as-is (not popped), so later nodes' `i_vert_pool` offsets
    // stay aligned with the real editor's own over-allocate-then-undercount behavior. Then
    // [DISASM 0x100353bb-0x100353eb]: any resulting count under 3 is treated as a degenerate
    // ("Infinitesimal polygon", `FOutputDevice::Logf`) node -- NumVertices forced to 0 rather than
    // left as a genuine 1/2-vertex sliver.
    if nv >= 2 && ivs[0] == *ivs.last().unwrap() {
        nv -= 1;
    }
    if nv < 3 {
        nv = 0;
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
        nv,
    );
    node.node_flags = nf;
    model.nodes.push(node);

    inherit_parent_leaf_zone(model, i_parent, i_node, place);

    match place {
        NODE_BACK => model.nodes[i_parent as usize].i_back = i_node,
        NODE_FRONT => model.nodes[i_parent as usize].i_front = i_node,
        NODE_PLANE => model.nodes[i_parent as usize].i_plane = i_node,
        _ => {}
    }
    i_node
}

/// `bspAddNode`'s zone/leaf seeding from the PARENT node — the last block of the real function
/// **[DISASM Editor.dll `0x3524a`–`0x352c7` (root + coplanar) and `0x3535b`–`0x3539c` (front/back,
/// decoded 2026-08-27); spec §5.1]**.  `FBspNode`: `iZone[2]` bytes at `+0x34/+0x35`, `iLeaf[2]` at
/// `+0x38/+0x3c`.
///
/// ```text
/// NODE_Root  (3): iLeaf[0] = iLeaf[1] = -1;  iZone[0] = iZone[1] = 0
/// NODE_Front (1) / NODE_Back (0):
///                 iLeaf[0] = iLeaf[1] = parent.iLeaf[NodePlace]
///                 iZone[0] = iZone[1] = parent.iZone[NodePlace]
/// NODE_Plane (2): k = (newPlane | parentPlane) < 0     // FPlane::operator|, Core.dll 0x17d60:
///                 iLeaf[0] = parent.iLeaf[k];  iLeaf[1] = parent.iLeaf[1-k]   // a FOUR-component
///                 iZone[0] = parent.iZone[k];  iZone[1] = parent.iZone[1-k]   // dot, W included
/// ```
///
/// **Why it is load-bearing.** `csgRebuild` runs `TestVisibility` (the leaf/zone pass) BETWEEN the
/// world repartition and the detail-brush loop, so the ~3300 nodes the detail loop appends are never
/// visited by Pass A/D.  Their zones and leaves come from here and nowhere else.  Without this, every
/// detail node reads `iLeaf = (-1, -1)` / `iZone = (0, 0)` — solid, zone 0 — and `UModel::PointRegion`,
/// which descends to the first childless side and reads that slot, resolves any actor below a detail
/// node into solid space: 1027 of UNATCO's 1437 actors, against the editor build's 126.
fn inherit_parent_leaf_zone(model: &mut Model, i_parent: i32, i_node: i32, place: i32) {
    if place == NODE_ROOT {
        return; // BspNode::leaf already seeds iLeaf = -1 / iZone = 0; it is the only parentless case.
    }
    let (p_plane, p_leaf, p_zone) = {
        let p = &model.nodes[i_parent as usize];
        (p.plane, p.i_leaf, p.i_zone)
    };
    let (leaf, zone) = if place == NODE_PLANE {
        let n = model.nodes[i_node as usize].plane;
        let dot = n.x * p_plane.x + n.y * p_plane.y + n.z * p_plane.z + n.w * p_plane.w;
        let k = usize::from(dot < 0.0);
        ([p_leaf[k], p_leaf[1 - k]], [p_zone[k], p_zone[1 - k]])
    } else {
        let s = place as usize; // NODE_Back = 0, NODE_Front = 1 — the same indices as iLeaf/iZone.
        ([p_leaf[s]; 2], [p_zone[s]; 2])
    };
    let n = &mut model.nodes[i_node as usize];
    n.i_leaf = leaf;
    n.i_zone = zone;
}

// --- bspCleanup: splice FWTB-DEAD nodes out of the incremental tree ---------------------------

/// `bspCleanup` (`Editor.dll` RVA `0x36160`) → the recursive worker `CleanupNodes` (`0x32100`),
/// decoded to the instruction level this session (`sections/82` §10.9).  Run at the TAIL of every
/// structural `bsp_brush_csg` call (per-brush), mirroring `bspBrushCSG` `0x35de1` — NOT once at the
/// end — so each brush filters through the previous brush's cleaned tree.
///
/// **Why it is load-bearing for byte-parity.** `FilterWorldThroughBrush` marks a world face DELETED
/// by setting its node's `NumVertices = 0` while keeping the node in the tree as a plane-only
/// splitter (`NodeCleanup` is a notify-only hook — it does NOT relink; verified from the `0x34020`
/// disasm).  So after the incremental CSG the tree is full of dead (`nv==0`) nodes.  `bspCleanup`
/// then walks the tree bottom-up and SPLICES each dead node out:
///   * **Case A — dead node with a coplanar (`iPlane`) successor `P`:** `P` is promoted into the
///     dead node's place.  `P` inherits the dead node's `iFront`/`iBack` children — SWAPPED when `P`
///     faces the opposite way (`Node.Normal · P.Normal < 0`, threshold `0.0`, via `FPlane::operator|`
///     `Core.dll ??|UFPlane`).  The parent is repointed from the dead node to `P`.  (Root special
///     case: copy `P`'s node into the root slot and mark `P` dead.)
///   * **Case B — dead node with NO coplanar successor:** if it has both children it is KEPT as a
///     pure splitter; otherwise the parent is repointed straight to its single child (or `-1`).
/// Dead nodes are NOT removed from the array (indices stay stable, matching the editor); they just
/// become unreachable and are never visited again.
///
/// This is what makes the editor route `node4.iFront -> ALIVE floor fragment (12)` where native used
/// to route `-> DEAD original (5)`, and — crucially — reorders the whole pre-repartition tree so
/// `MakeEdPolys` (`bsp_build_fpolys`) extracts the face soup in the editor's EXACT order, which
/// drives `bspMergeCoplanars` grouping + `bspBuild` splitter choice to node-for-node parity.  Before
/// this, the leaf-add multiset already matched through N=32 but the internal linkage diverged from
/// brush 0 (a flipped-orientation splitter → reversed front/back emit order), so the from-scratch
/// repartition saw a different `Polys` order (final `node_diff` prefix stuck at 0/1156).
fn bsp_cleanup(model: &mut Model) {
    if !model.nodes.is_empty() {
        cleanup_nodes(model, 0, -1);
    }
}

fn cleanup_nodes(model: &mut Model, i_node: i32, i_parent: i32) {
    // NodeFlags &= 0x1f — clear NF_IsNew (0x20) + high bits (0x32120).
    model.nodes[i_node as usize].node_flags &= 0x1f;

    // Recurse children first: front, back, plane (0x32124..0x3215d).
    let (i_f, i_b, i_p) = {
        let n = &model.nodes[i_node as usize];
        (n.i_front, n.i_back, n.i_plane)
    };
    if i_f != -1 {
        cleanup_nodes(model, i_f, i_node);
    }
    if i_b != -1 {
        cleanup_nodes(model, i_b, i_node);
    }
    if i_p != -1 {
        cleanup_nodes(model, i_p, i_node);
    }

    // Re-read: a child's own splice may have rewritten this node's links.
    let n = model.nodes[i_node as usize].clone();
    if n.num_vertices != 0 {
        return; // ALIVE — keep (0x32165).
    }

    // DEAD node (nv==0): splice it out.
    if n.i_plane != -1 {
        // Case A — promote the coplanar successor P (0x3216f..).
        let p = n.i_plane;
        // d = Node.Normal · P.Normal (FPlane::operator|, threshold 0.0 @0x100dcaec).
        let pn = model.nodes[p as usize].plane;
        let d = n.plane.x * pn.x + n.plane.y * pn.y + n.plane.z * pn.z;
        if d >= 0.0 {
            model.nodes[p as usize].i_front = n.i_front;
            model.nodes[p as usize].i_back = n.i_back;
        } else {
            model.nodes[p as usize].i_front = n.i_back;
            model.nodes[p as usize].i_back = n.i_front;
        }
        if i_parent == -1 {
            // ROOT: copy P into the root slot, mark P dead (0x32213..0x3223e).
            model.nodes[i_node as usize] = model.nodes[p as usize].clone();
            model.nodes[p as usize].num_vertices = 0;
            return;
        }
        // Repoint the parent at P (0x3223f..).
        let par = &mut model.nodes[i_parent as usize];
        if par.i_front == i_node {
            par.i_front = p;
        } else if par.i_back == i_node {
            par.i_back = p;
        } else if par.i_plane == i_node {
            par.i_plane = p;
        } else {
            // The engine `appErrorf`s here ("parent does not link the child").  We only assert in
            // debug (a release panic would surface as a CLI traceback); the invariant is verified to
            // hold — the post-fix soup is byte-exact, which requires a consistent tree.
            debug_assert!(false, "cleanup: parent {i_parent} does not link dead node {i_node}");
        }
        return;
    }

    // Case B — dead node with no coplanar successor (0x322a4..).
    let (f, b) = (n.i_front, n.i_back);
    if f != -1 && b != -1 {
        return; // both children, no plane successor -> keep as a splitter.
    }
    let child = if f != -1 { f } else { b }; // single child, or -1 (leaf).
    if i_parent == -1 {
        // ROOT dead leaf/one-child: the engine promotes the single child into the root slot (0x322dc)
        // or resets the model when childless (0x32ae0).  In this pipeline the root (brush-0's first
        // face) accrues an iPlane chain + both children, so it always takes Case A-root or the
        // both-children keep above and never reaches here — assert (debug-only) to catch it if a
        // future pipeline change ever lets the root die this way.
        debug_assert!(false, "cleanup: dead root with no iPlane successor (unhandled Case B root)");
        return;
    }
    let par = &mut model.nodes[i_parent as usize];
    if par.i_front == i_node {
        par.i_front = child;
    } else if par.i_back == i_node {
        par.i_back = child;
    } else if par.i_plane == i_node {
        par.i_plane = child;
    } else {
        debug_assert!(false, "cleanup: parent {i_parent} does not link dead node {i_node} (Case B)");
    }
}

// --- IsCsg (filter convention, mask 0x21 = NF_NotCsg|NF_IsNew) --------------------------------

/// `FBspNode::IsCsg` (`0x33b80`, extraMask=0): a node counts as CSG-solid iff it is neither NotCsg
/// (0x01) nor freshly-added-this-brush (NF_IsNew 0x20) — AND has `NumVertices > 0`.
///
/// **DEAD-NODE CSG (2026-08-28, live-editor PINNED).** We originally dropped the `NumVertices > 0`
/// clause (2026-07-17), validated against N=4..8 synthetic tests and the non-OG castle fixture: a
/// face that `FilterWorldThroughBrush` deleted by setting `NumVertices = 0` (the FACE gone, the node
/// left as a plane-only splitter, §8.1) had to keep dividing space as a CSG solid so the `Outside`
/// flag still flipped crossing it.  The 2026-08-27/28 Wanchai live capture REFUTES that for the
/// EDITOR's own predicate: it treats `NumVertices == 0` as non-CSG (`csg=0`), i.e. a dead node does
/// NOT flip `Outside`.  Restoring the clause matches the editor's true `IsCsg`.  The old N=4..8 /
/// castle validation was non-OG (owner ruling 2026-08-28: only original retail levels are valid
/// parity evidence), so those fixtures can no longer adjudicate this.  See
/// `wanchai-bsp-gap-localized-to-one-dropped`; re-measured on OG retail UNATCO / Wanchai.
fn is_csg_filter(n: &BspNode) -> bool {
    n.num_vertices > 0 && (n.node_flags & 0x21) == 0
}

// --- the filter recursion (FilterEdPoly / FilterLeaf) ----------------------------------------

/// `FCoplanarInfo` (Editor.dll `FilterEdPoly` frame `+0x18..+0x28`).  Field roles decoded from the
/// coplanar cascade (`0x32d91`) + `FilterLeaf` (`0x33130`) — see
/// `re-raw-zones/bspbrushcsg-filter-decode.md` §7b and `sections/82` §8.3:
///   * `i_back_node`   (+0x1c) — the NON-facing ("other") child, descended in the back pass.
///   * `back_seed`     (+0x20 `FrontLeafOutside`) — the `Outside` SEED for the OTHER-side descent.
///     NOT the facing-leaf's result: it's the coplanar-time CSG-adjusted outside for the other side.
///   * `front_outside` (+0x24 `BackNodeOutside`) — the classify's `frontOutside`.  Overwritten with
///     the facing-pass leaf result in the normal case; pre-seeded to `facing_out` when the facing
///     child is empty (`-1`).
#[derive(Clone, Copy)]
struct Coplanar {
    i_original_node: i32,
    i_back_node: i32,
    processing_back: bool,
    back_seed: bool,
    front_outside: bool,
}

impl Coplanar {
    fn none() -> Self {
        Coplanar {
            i_original_node: -1,
            i_back_node: -1,
            processing_back: false,
            back_seed: false,
            front_outside: false,
        }
    }
}

/// The four `BRUSH FROM INTERSECTION`/`DEINTERSECTION` leaf callbacks (RE:
/// `re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md` §2).  Unlike `Add`/`Subtract` — which
/// GROW the world tree via `bsp_add_node` — these are pure COLLECTORS: they append the surviving
/// fragment to an output polylist (the editor's `GModel->Polys`) and never touch the tree.  They
/// differ only in (a) which `EPolyNodeFilter` values they accept and (b) whether they `Reverse()`
/// the fragment before appending:
///
/// | leaf | addr | filtered through | accepts `F` | reverse? |
/// |---|---|---|---|---|
/// | `IntersectP1`   | `0x339e0` | builder face ↓ **world** tree   | `{INSIDE, COPLANAR_INSIDE}`               | no  |
/// | `DeintersectP1` | `0x32390` | builder face ↓ **world** tree   | `{OUTSIDE, COPLANAR_OUTSIDE}`             | no  |
/// | `IntersectP2`   | `0x33ab0` | world face ↓ **brush** temp BSP | `{INSIDE, COPLANAR_INSIDE, FACING_OUT}`   | no  |
/// | `DeintersectP2` | `0x32460` | world face ↓ **brush** temp BSP | `{INSIDE, COPLANAR_INSIDE, FACING_IN}`    | yes |
///
/// P1 keeps the builder's own faces where they lie inside solid (intersect) / in empty space
/// (deintersect); P2 keeps the world surfaces that pass through the builder volume — the "caps",
/// which is how the result inherits the surrounding brushes' texture AND PolyFlags.
#[derive(Clone, Copy, PartialEq)]
enum CollectKind {
    IntersectP1,
    DeintersectP1,
    IntersectP2,
    DeintersectP2,
}

impl CollectKind {
    /// The leaf's accept set + `Reverse` flag, read straight off the switch decode (§2).
    fn keeps(self, filter: i32) -> bool {
        match self {
            CollectKind::IntersectP1 => filter == F_INSIDE || filter == F_COPLANAR_INSIDE,
            CollectKind::DeintersectP1 => filter == F_OUTSIDE || filter == F_COPLANAR_OUTSIDE,
            CollectKind::IntersectP2 => {
                filter == F_INSIDE || filter == F_COPLANAR_INSIDE || filter == F_COSPATIAL_FACING_OUT
            }
            CollectKind::DeintersectP2 => {
                filter == F_INSIDE || filter == F_COPLANAR_INSIDE || filter == F_COSPATIAL_FACING_IN
            }
        }
    }

    fn reverses(self) -> bool {
        self == CollectKind::DeintersectP2
    }
}

/// The shared tail of all four collect leaves (`0x324a4`-`0x324e2` for `DeintersectP2`, the others
/// identical modulo the `Reverse` pair): `if (EdPoly->Fix() >= 3) GModel->Polys.Add(*EdPoly)`, with
/// `Reverse` wrapped around the append for `DeintersectP2` only.  `Fix` (`0x100cee38`) de-dups and
/// strips colinear vertices, returning the surviving vertex count; the editor's second `Reverse`
/// merely restores the caller's poly, so cloning here is equivalent.
fn collect_leaf(kind: CollectKind, edpoly: &FPoly, filter: i32, sink: &mut Vec<FPoly>) {
    if !kind.keeps(filter) {
        return;
    }
    let mut e = edpoly.clone();
    if e.fix() < 3 {
        return;
    }
    if kind.reverses() {
        e.reverse();
    }
    sink.push(e);
}

#[derive(Clone, Copy, PartialEq)]
enum LeafFunc {
    Add,
    Subtract,
    /// Append surviving fragments to the caller's `sink` instead of growing the tree
    /// (`BRUSH FROM INTERSECTION`/`DEINTERSECTION`).  The model is never mutated.
    Collect(CollectKind),
}

/// DESCENT/LEAF TRACE scope (`UEDCLI_BSPCSG_DESCENT=<ilink>` / `_ACTOR=<world-csg actor idx>` /
/// `_POLY=<i_brush_poly>`) — env-gated; shared by the `filter_ed_poly` descent-path trace and
/// `leaf_func`'s terminal-classification trace below.
///
/// `i_link` alone does NOT identify a brush: it is reassigned per brush-CSG-call to a
/// (speculative, not-yet-committed) surf slot number, `model.surfs.len()` at the time the poly's
/// coincident-group representative is first seen — a value that can repeat across UNRELATED
/// brushes whenever an earlier candidate surf never actually got committed by `bsp_add_node`
/// (dropped fragment), not a stable per-brush-poly identity
/// (`smuggler-4-surf-delta-traced-to-4-pf-semisolid`, 2026-08-30). `actor` (the world-CSG brush
/// index, stable and set once per `bsp_brush_csg` call, `FPoly::empty_copy`-preserved across every
/// split fragment) and `i_brush_poly` (the AUTHORED local poly index within that brush, likewise
/// preserved) together give an unambiguous per-brush-per-face identity; set `_ACTOR`/`_POLY` to
/// scope a trace to one specific brush's one specific face, or `UEDCLI_BSPCSG_DESCENT` alone for
/// the legacy i_link-keyed lookup (still valid where the caller has an independent iLink from an
/// editor-side dump, e.g. `wanchai-bsp-gap-localized-to-one-dropped`). At least one filter must be
/// set; every SET filter must match.
fn descent_scope_matches(edpoly: &FPoly) -> bool {
    let want_link = std::env::var("UEDCLI_BSPCSG_DESCENT").ok().and_then(|s| s.parse::<i32>().ok());
    let want_actor = std::env::var("UEDCLI_BSPCSG_DESCENT_ACTOR")
        .ok()
        .and_then(|s| s.parse::<i32>().ok());
    let want_poly = std::env::var("UEDCLI_BSPCSG_DESCENT_POLY")
        .ok()
        .and_then(|s| s.parse::<i32>().ok());
    (want_link.is_some() || want_actor.is_some() || want_poly.is_some())
        && want_link.is_none_or(|v| v == edpoly.i_link)
        && want_actor.is_none_or(|v| v == edpoly.actor)
        && want_poly.is_none_or(|v| v == edpoly.i_brush_poly)
}

/// The per-CsgOper leaf callback — where nodes are ADDED (`AddBrushToWorldFunc 0x31770` /
/// `SubtractBrushFromWorldFunc 0x348c0`).  §8.2: `Subtract` is NOT a mirror — it adds ONLY on
/// `{F_INSIDE, F_COPLANAR_INSIDE}` (no `F_COSPATIAL_FACING_IN`, no semisolid gate) and stores the
/// face `Reverse()`d (inward-facing) around `bspAddNode`; the descent keeps the outward normal.
fn leaf_func(
    model: &mut Model,
    func: LeafFunc,
    i_node: i32,
    edpoly: &FPoly,
    filter: i32,
    place: i32,
    sink: &mut Vec<FPoly>,
) {
    match func {
        LeafFunc::Collect(kind) => collect_leaf(kind, edpoly, filter, sink),
        LeafFunc::Add => {
            let add = filter == F_OUTSIDE
                || filter == F_COPLANAR_OUTSIDE
                || (filter == F_COSPATIAL_FACING_OUT
                    && (edpoly.poly_flags & csg::PF_SEMISOLID) == 0);
            // LEAF-CLASSIFY TRACE — same actor/poly scoping as the DESCENT trace above
            // (`smuggler-4-surf-delta-traced-to-4-pf-semisolid`): shows the terminal `filter`
            // value + the semisolid gate's own verdict, not just the descent path.
            if descent_scope_matches(edpoly) {
                eprintln!(
                    "LEAF actor={} i_brush_poly={} i_link={} filter={} semisolid={} add={}",
                    edpoly.actor, edpoly.i_brush_poly, edpoly.i_link,
                    filter, (edpoly.poly_flags & csg::PF_SEMISOLID) != 0, add
                );
            }
            if add {
                let r = bsp_add_node(model, i_node, place, NF_IS_NEW, edpoly);
                trace_node_add(model, "ADD", i_node, place, NF_IS_NEW, edpoly, r);
            }
        }
        LeafFunc::Subtract => {
            if filter == F_INSIDE || filter == F_COPLANAR_INSIDE {
                let mut e = edpoly.clone();
                e.reverse(); // store the carved wall inward-facing (Reverse wraps only the add)
                let r = bsp_add_node(model, i_node, place, NF_IS_NEW, &e);
                trace_node_add(model, "SUB", i_node, place, NF_IS_NEW, &e, r);
            }
        }
    }
}

/// `FilterLeaf` (`0x33130`): a fragment reached a leaf (or completes a coplanar cascade).
#[allow(clippy::too_many_arguments)]
fn filter_leaf(
    model: &mut Model,
    func: LeafFunc,
    i_node: i32,
    edpoly: &FPoly,
    mut coplanar: Coplanar,
    leaf_outside: bool,
    place: i32,
    sink: &mut Vec<FPoly>,
) {
    if coplanar.i_original_node == -1 {
        // Ordinary, non-coplanar leaf.
        let filter = if leaf_outside { F_OUTSIDE } else { F_INSIDE };
        leaf_func(model, func, i_node, edpoly, filter, place, sink);
    } else if coplanar.processing_back {
        // Finished filtering through the BACK (other-side) of the parent coplanar node -> classify
        // cospatial from (frontOutside, backOutside) = (coplanar.front_outside, leaf_outside).
        let fo = coplanar.front_outside;
        let filter = if !leaf_outside && !fo {
            F_COPLANAR_INSIDE
        } else if leaf_outside && fo {
            F_COPLANAR_OUTSIDE
        } else if !leaf_outside && fo {
            F_COSPATIAL_FACING_OUT
        } else {
            F_COSPATIAL_FACING_IN
        };
        leaf_func(
            model,
            func,
            coplanar.i_original_node,
            edpoly,
            filter,
            NODE_PLANE,
            sink,
        );
    } else {
        // Finished the FRONT (facing-side) pass (`FilterLeaf` `0x33184`): record the facing-leaf
        // result as the classify frontOutside, then descend the OTHER child seeded with `back_seed`
        // (the coplanar-time CSG-adjusted other-side outside), NOT this facing-leaf result.
        coplanar.front_outside = leaf_outside;
        coplanar.processing_back = true;
        let back_seed = coplanar.back_seed;
        if coplanar.i_back_node == -1 {
            // Other-side tree empty -> classify immediately: backOutside == back_seed.
            filter_leaf(model, func, i_node, edpoly, coplanar, back_seed, NODE_PLANE, sink);
        } else {
            let ibn = coplanar.i_back_node;
            filter_ed_poly(model, func, ibn, edpoly, coplanar, back_seed, sink);
        }
    }
}

/// `FilterEdPoly` (`0x32bf0`): push `edpoly` down the world tree, splitting at each node plane,
/// propagating `Outside`, and adding surviving fragments as nodes at leaves.
///
/// **Full `angr`-decompile cross-check (2026-09-01, `dev/docs/spikes/2026-09-01-filteredpoly-full-
/// decompile/`): every branch below (vertex-overflow pre-split order, Front/Back tail recursion,
/// `Split`'s front-before-back order, the out-of-place-coplanar path, the facing-test) matches the
/// decompiled pseudo-C with no divergence.** Confirmed this function (and `filter_leaf`) NEVER reads
/// a node's `i_plane` (coplanar-sibling chain) — only `bsp_add_node`'s insert-time tail-walk touches
/// it. A coplanar-node traversal-order bug, if real, cannot live in this function: it is blind to the
/// chain by construction, on both sides. See the findings ledger, search "coplanar `iPlane` node-chain
/// is NEVER read", for the full comparison.
#[allow(clippy::too_many_arguments)]
fn filter_ed_poly(
    model: &mut Model,
    func: LeafFunc,
    mut i_node: i32,
    edpoly: &FPoly,
    coplanar: Coplanar,
    mut outside: bool,
    sink: &mut Vec<FPoly>,
) {
    let mut edpoly = edpoly.clone();
    loop {
        // vertex-overflow guard (>=14 -> SplitInHalf, filter each half)
        if edpoly.verts.len() >= 14 {
            let mut first = edpoly.clone();
            let half = first.split_in_half();
            filter_ed_poly(model, func, i_node, &half, coplanar, outside, sink);
            edpoly = first;
        }

        let (i_front, i_back, csg, base, normal) = {
            let node = &model.nodes[i_node as usize];
            // A node with no surf cannot be classified against; treat it as a leaf rather than
            // indexing `surfs[-1]` and panicking out of a public entry point.
            if node.i_surf < 0 {
                return;
            }
            let surf = &model.surfs[node.i_surf as usize];
            let base = model.points[surf.p_base as usize];
            let normal = model.vectors[surf.v_normal as usize];
            (node.i_front, node.i_back, is_csg_filter(node), base, normal)
        };

        // DESCENT TRACE — env-gated (see `descent_scope_matches`); native counterpart of the
        // editor's `editor_descent.py` FilterEdPoly-loop-head trace (§10.8): the exact tree path a
        // poly + its split fragments descend, for pinning a per-poly emit-order divergence.
        if descent_scope_matches(&edpoly) {
            let node_surf = model.nodes[i_node as usize].i_surf;
            let dists: Vec<f32> =
                edpoly.verts.iter().map(|v| v.sub(&base).dot(&normal)).collect();
            let mn = dists.iter().cloned().fold(f32::INFINITY, f32::min);
            let mx = dists.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
            let cls = match edpoly.split_with_plane(&base, &normal, false) {
                Split::Front => "FRONT".to_string(),
                Split::Back => "BACK".to_string(),
                Split::Coplanar => {
                    let dot = edpoly.normal.dot(&normal);
                    format!("COPLANAR dot={:.5}", dot)
                }
                Split::Split(f, b) => format!("SPLIT f_nv={} b_nv={}", f.verts.len(), b.verts.len()),
            };
            // `plane_w` = Base·Normal = the UE1 `FPlane.W` convention the editor's own `nodeN`
            // dump (`area51_filteredpoly_descent.py`, offset +0xc of the packed plane) reads
            // directly -- printed here so a node can be paired cross-side by (Normal, W), not by
            // its (unrelated-numbering) index.
            let plane_w = base.dot(&normal);
            eprintln!(
                "DESC actor={} i_brush_poly={} i_link={} node={} nsurf={} iF={} iB={} csg={} nv={} N=({:.4},{:.4},{:.4},{:.4}) edN=({:.6},{:.6},{:.6}) min={:.5} max={:.5} -> {}",
                edpoly.actor, edpoly.i_brush_poly, edpoly.i_link,
                i_node, node_surf, i_front, i_back, csg as i32, edpoly.verts.len(),
                normal.x, normal.y, normal.z, plane_w,
                edpoly.normal.x, edpoly.normal.y, edpoly.normal.z, mn, mx, cls
            );
        }

        match edpoly.split_with_plane(&base, &normal, false) {
            Split::Front => {
                let no = outside || csg;
                if i_front == -1 {
                    filter_leaf(model, func, i_node, &edpoly, coplanar, no, NODE_FRONT, sink);
                    return;
                }
                i_node = i_front;
                outside = no;
                continue;
            }
            Split::Back => {
                let no = outside && !csg;
                if i_back == -1 {
                    filter_leaf(model, func, i_node, &edpoly, coplanar, no, NODE_BACK, sink);
                    return;
                }
                i_node = i_back;
                outside = no;
                continue;
            }
            Split::Split(front, back) => {
                let fo = outside || csg;
                let bo = outside && !csg;
                if i_front == -1 {
                    filter_leaf(model, func, i_node, &front, coplanar, fo, NODE_FRONT, sink);
                } else {
                    filter_ed_poly(model, func, i_front, &front, coplanar, fo, sink);
                }
                if i_back == -1 {
                    filter_leaf(model, func, i_node, &back, coplanar, bo, NODE_BACK, sink);
                } else {
                    filter_ed_poly(model, func, i_back, &back, coplanar, bo, sink);
                }
                return;
            }
            Split::Coplanar => {
                if coplanar.i_original_node != -1 {
                    // Out-of-place coplanar (rare): classify as Front.
                    let no = outside || csg;
                    if i_front == -1 {
                        filter_leaf(model, func, i_node, &edpoly, coplanar, no, NODE_FRONT, sink);
                        return;
                    }
                    i_node = i_front;
                    outside = no;
                    continue;
                }
                // Facing test (`0x32e32`): descend the poly's facing side first.  Each side's
                // descent is seeded with the CSG-adjusted outside for THAT side (front side ->
                // `outside||csg`, back side -> `outside&&!csg`) — the same adjustment the ordinary
                // SP_Front/SP_Back branches apply.  `Dot>=0` faces the node FRONT, `Dot<0` the BACK.
                let dot = edpoly.normal.dot(&normal);
                let (facing_child, other_child, facing_out, other_out) = if dot >= 0.0 {
                    (i_front, i_back, outside || csg, outside && !csg)
                } else {
                    (i_back, i_front, outside && !csg, outside || csg)
                };
                let mut cop = Coplanar {
                    i_original_node: i_node,
                    i_back_node: other_child,
                    processing_back: false,
                    back_seed: other_out,
                    front_outside: outside, // overwritten below / by the facing-pass leaf
                };
                if facing_child == -1 {
                    // Facing side is a leaf: its outside IS `facing_out`; go straight to the back pass
                    // (`0x32f15`/`0x32ec3`) — frontOutside is `facing_out`.
                    cop.front_outside = facing_out;
                    cop.processing_back = true;
                    if other_child == -1 {
                        filter_leaf(model, func, i_node, &edpoly, cop, other_out, NODE_PLANE, sink);
                    } else {
                        filter_ed_poly(model, func, other_child, &edpoly, cop, other_out, sink);
                    }
                } else {
                    // Descend the facing side first (`0x32f33`); `front_outside` gets set to this
                    // descent's leaf result in `filter_leaf`.
                    filter_ed_poly(model, func, facing_child, &edpoly, cop, facing_out, sink);
                }
                return;
            }
        }
    }
}

/// `bspFilterFPoly` (`0x31f50`): empty-tree shortcut, else descend from root.
fn bsp_filter_fpoly(model: &mut Model, func: LeafFunc, edpoly: &FPoly, sink: &mut Vec<FPoly>) {
    if model.nodes.is_empty() {
        // EMPTY-WORLD SEED. The DOMINANT case — a leading CSG_Add into the empty solid world — is
        // now handled UPSTREAM by the CONVEX SEED in `bsp_brush_csg`'s LOOP-2 (§92 §32): that path
        // builds ALL of a leading Add's polys as a NODE_ROOT + NODE_FRONT chain and never calls this
        // function, so the `LeafFunc::Add => F_OUTSIDE` arm below is UNREACHABLE for a real leading
        // Add on the DX solid world. This arm now serves only:
        //   * a leading CSG_Subtract at `root_outside==false` — needs F_INSIDE so the leaf stores the
        //     face Reverse()d at root (the castle's first brush `World_7e9y81`; byte-exact, unchanged);
        //   * a `root_outside==true` additive world (no DX level has one, §24: RootOutside=0 on every
        //     golden) — keeps the editor's op-INDEPENDENT empty rule (F_OUTSIDE);
        //   * direct unit-test calls (`first_poly_on_empty_world_is_seeded_as_root_node`), which still
        //     exercise the per-op seed for both ops.
        // Kept as the DEFENSIVE per-op form (rather than restoring the naive op-independent F_OUTSIDE)
        // so a stray direct Add call still seeds outward instead of silently dropping. RootOutside is
        // left UNCHANGED (false) — no void-polarity flip (§25, reverted).
        let filter = if !model.root_outside {
            match func {
                LeafFunc::Add => F_OUTSIDE,
                LeafFunc::Subtract => F_INSIDE,
                // A COLLECT leaf (intersect/deintersect Phase 1) has no node to seed, so the
                // defensive per-op form above does not apply: keep the editor's op-INDEPENDENT
                // empty-tree rule `RootOutside ? F_OUTSIDE : F_INSIDE`.  Unreachable in practice —
                // both verbs guarantee a non-empty world (intersect prepends the wrap-subtract;
                // deintersect requires >=1 subtract) — but it must not silently classify an
                // all-solid empty world as void.
                LeafFunc::Collect(_) => F_INSIDE,
            }
        } else {
            F_OUTSIDE
        };
        leaf_func(model, func, -1, edpoly, filter, NODE_ROOT, sink);
    } else {
        let outside = model.root_outside;
        filter_ed_poly(model, func, 0, edpoly, Coplanar::none(), outside, sink);
    }
}

// --- bspNodeToFPoly (reconstruct a node's face) ----------------------------------------------

/// `bspNodeToFPoly` (`0x365b0`): reconstruct node `ni`'s polygon — Base/Normal/Textures PRESERVED
/// from its surf, vertices from the FVert pool.  Returns `None` if degenerate.
fn bsp_node_to_fpoly(model: &Model, ni: usize) -> Option<FPoly> {
    let n = &model.nodes[ni];
    if n.num_vertices <= 0 || n.i_surf < 0 {
        return None;
    }
    let s = &model.surfs[n.i_surf as usize];
    let base = model.points[s.p_base as usize];
    let normal = model.vectors[s.v_normal as usize];
    let mut verts = Vec::with_capacity(n.num_vertices as usize);
    for k in 0..n.num_vertices {
        let vi = model.verts[(n.i_vert_pool + k) as usize].i_vertex as usize;
        verts.push(model.points[vi]);
    }
    let mut p = FPoly::new(verts);
    p.base = base;
    p.normal = normal;
    p.texture_u = if s.v_texture_u >= 0 {
        model.vectors[s.v_texture_u as usize]
    } else {
        Vec3::default()
    };
    p.texture_v = if s.v_texture_v >= 0 {
        model.vectors[s.v_texture_v as usize]
    } else {
        Vec3::default()
    };
    p.poly_flags = s.poly_flags;
    p.actor = s.i_actor;
    p.texture = s.texture_ref;
    p.i_brush_poly = s.i_brush_poly;
    // The pan is part of the surf's texture state, and bspRepartition re-allocs every surf from
    // these reconstructed polys — dropping it here erases the authored pan from the whole build.
    p.pan = s.pan;
    p.i_link = n.i_surf;
    p.remove_colinears();
    if p.verts.len() < 3 {
        return None;
    }
    Some(p)
}

// --- FilterWorldThroughBrush (cut the world with the brush) -----------------------------------

/// State for `FilterWorldThroughBrush` — the engine's `GNode`/`GLastCoplanar`/`GDiscarded` globals
/// (§8.1), threaded explicitly.  `world` is the growing world Model (mutated by the leaf); the DESCENT
/// reads the brush's convex temp BSP instead.
struct WtbCtx {
    g_node: i32,
    g_last_coplanar: i32,
    g_discarded: i32,
    subtract: bool,
    /// `Some(kind)` = the `BRUSH FROM INTERSECTION`/`DEINTERSECTION` **Phase 2** leaf (`0x33ab0` /
    /// `0x32460`), selected by `FilterWorldThroughBrush`'s `CsgOper` switch (`fwtb_switch.asm`
    /// `0x333d7`).  It only APPENDS to `sink`: it never re-adds nodes, never bumps `g_discarded`,
    /// and never marks the original node dead — so the enclosing save/commit/rollback in
    /// `filter_one_world_node` degenerates to a no-op and is skipped outright.
    collect: Option<CollectKind>,
}

/// `FilterWorldThroughBrush` (`0x33250`) — §8.1 SPLIT-AND-RE-ADD, driven by the editor's
/// **bound-pruned recursive tree-walk** (NOT a flat node loop).  Recurses the world tree from the
/// root; at each node it tests the node plane against the brush's bound **SPHERE**
/// (`&TempModel->Bound.Sphere`): with `d = PlaneDot(node.plane, sphereCenter)` and `R = sphere
/// radius`, `DoFront = d >= -R`, `DoBack = d <= R`.  A node's face is filtered through the brush temp
/// BSP **only when it STRADDLES the sphere** (`DoFront && DoBack`); each child subtree is descended
/// **only on its side's flag**, so a whole subtree entirely on one side of the brush is PRUNED.
///
/// **Bound type binary-verified 2026-07-18 (resolves the old §10.14 "not yet verified"):**
/// `FilterWorldThroughBrush` (arg5 = the bound ptr) computes `d = PlaneDot(node.plane, *arg5)`, reads
/// `R = *(arg5+0xc)`, and forms `DoFront = d >= -R`, `DoBack = d <= R` — so `arg5` is an **`FSphere`**
/// {`Center`@+0, `Radius`@+0xc}, NOT a box.  It is `&TempModel->Bound.Sphere`: `UModel::BuildBound`
/// (`Engine.dll 0x16fcf0`) sets `Bound` = {`FBox`@UModel+0x28 = AABB over the brush's `Polys` verts,
/// `FSphere`@+0x44}, and `FSphere(Pts,Count)` (`core.dll 0x50100`) = {center = AABB midpoint, radius =
/// √(max‖pt−center‖²) · 1.001 (a small pad, `fmul [0x100a5b40]`)}.  The earlier native code inferred a
/// per-node box push-out (`|Nx|hx+|Ny|hy+|Nz|hz`); the box and the sphere are DIFFERENT, INCOMPARABLE
/// prunes — neither straddle-set contains the other (for a diagonal node normal on a near-cubic brush
/// the box is looser; for a thin wall the sphere is looser), so this is not a strict widen/narrow.
/// Empirically, on the castle the sphere makes native's uncleared CSG pool (3447→3606 pts, verts
/// 15963→**17120 = EXACTLY the editor's** CSG-phase count, measured `repart_pool_oracle.py`) match the
/// editor — confirming the sphere is the faithful prune.
///
/// **Tree-safe / output-invariant regardless of the box↔sphere difference:** BOTH bounds are
/// CONSERVATIVE — the brush's true support along any node normal is `≤ radius` AND `≤ box-push` (every
/// brush vertex lies inside both the sphere and the AABB), so NEITHER can prune a node the brush
/// GENUINELY cuts (a real cut ⇒ `|d| ≤ support ≤ min(R, push)` ⇒ straddled under both).  The
/// symmetric difference of the two straddle-sets is therefore ALL grazes (`GDiscarded==0`), rolled
/// back — the committed node/surf tree is a function of the genuine-cut set only, identical either
/// way.  The graze re-adds DO leak `bspAddPoint`/`Verts.Add`, but the current path CLEARS + re-packs
/// the pool at `bspRepartition` (`EmptyModel(0,0)` + `bspRefresh` compaction), so graze transients
/// never reach the on-disk pool.  Verified final output byte-IDENTICAL: nodes 1156 / surfs 485 /
/// verts 10418 / points 1684 / vectors 26 / nss 2728 UNCHANGED after the switch.  (The prune sphere
/// affects the on-disk pool only on a future no-clear repartition; the editor's fatter pool is a
/// SEPARATE mechanism — kept Points/Vectors/Surfs + `TestVisibility`/Pass-D ring re-emit; see §10.16.)
///
/// The world-thru-brush leaf func RE-ADDs every bit31 fragment in an OUTSIDE-of-brush leaf as a
/// `NODE_Plane` node sharing the original surf and DISCARDs interior fragments; per straddling node:
/// `GDiscarded != 0` (face enters the brush) -> delete the original, keep the re-adds; `GDiscarded ==
/// 0` (graze) -> roll the re-adds back, keep the original whole.
fn filter_world_through_brush(
    world: &mut Model,
    brush_temp: &Model,
    subtract: bool,
    collect: Option<CollectKind>,
    sink: &mut Vec<FPoly>,
) {
    if brush_temp.nodes.is_empty() || world.nodes.is_empty() {
        return;
    }
    // Brush bound SPHERE = &TempModel->Bound.Sphere (UModel::BuildBound → FSphere(Pts,Count)):
    // center = AABB midpoint of the brush's vertices, radius = max distance from center to any vertex.
    let pts = &brush_temp.points;
    if pts.is_empty() {
        return;
    }
    let (mut mn, mut mx) = (pts[0], pts[0]);
    for p in pts {
        mn = Vec3::new(mn.x.min(p.x), mn.y.min(p.y), mn.z.min(p.z));
        mx = Vec3::new(mx.x.max(p.x), mx.y.max(p.y), mx.z.max(p.z));
    }
    let center = Vec3::new(
        (mn.x + mx.x) * 0.5,
        (mn.y + mx.y) * 0.5,
        (mn.z + mx.z) * 0.5,
    );
    let mut max_dist_sq = 0.0f32;
    for p in pts {
        let d = p.sub(&center);
        let ds = d.x * d.x + d.y * d.y + d.z * d.z;
        if ds > max_dist_sq {
            max_dist_sq = ds;
        }
    }
    // FSphere(Pts,Count) (`core.dll 0x50100`) tail: radius = appSqrt(maxDistSq) * 1.001 — the f64
    // `fmul [0x100a5b40]` (= the f32 literal 1.001) fudge that pads the bound slightly, then stored
    // back to f32.  Reproduced faithfully (f64 sqrt · f64 1.001 → f32).
    let radius = ((max_dist_sq as f64).sqrt() * (1.001f32 as f64)) as f32;
    filter_world_recurse(world, brush_temp, subtract, 0, center, radius, collect, sink);
}

/// One straddling world node: reconstruct its face, filter it through the brush temp BSP, and
/// commit (delete original, keep re-adds) or roll back (graze).  Extracted from the old flat loop.
#[allow(clippy::too_many_arguments)]
fn filter_one_world_node(
    world: &mut Model,
    brush_temp: &Model,
    subtract: bool,
    ni: usize,
    collect: Option<CollectKind>,
    sink: &mut Vec<FPoly>,
) {
    let face = match bsp_node_to_fpoly(world, ni) {
        Some(f) => f,
        None => return,
    };
    // COLLECT (intersect/deintersect Phase 2): the leaf only appends to `sink`, so there is nothing
    // to save, commit or roll back — filter the reconstructed world face down the brush hull and
    // leave the world tree completely untouched.
    if let Some(kind) = collect {
        let mut ctx = WtbCtx {
            g_node: ni as i32,
            g_last_coplanar: ni as i32,
            g_discarded: 0,
            subtract,
            collect: Some(kind),
        };
        wtb_filter_ed_poly(
            world,
            brush_temp,
            &mut ctx,
            0,
            &face,
            Coplanar::none(),
            brush_temp.root_outside,
            sink,
        );
        return;
    }
    let saved = world.nodes.len();
    // GLastCoplanar = tail of ni's iPlane chain; save its (−1) link for a clean rollback.
    let mut glc = ni as i32;
    while world.nodes[glc as usize].i_plane != -1 {
        glc = world.nodes[glc as usize].i_plane;
    }
    let saved_glc_plane = world.nodes[glc as usize].i_plane;
    let mut ctx = WtbCtx {
        g_node: ni as i32,
        g_last_coplanar: glc,
        g_discarded: 0,
        subtract,
        collect: None,
    };
    // filter the world face down the brush temp BSP (root outside = true).
    wtb_filter_ed_poly(
        world,
        brush_temp,
        &mut ctx,
        0,
        &face,
        Coplanar::none(),
        brush_temp.root_outside,
        sink,
    );
    if ctx.g_discarded == 0 {
        // Nothing interior -> the re-adds are spurious duplicates: roll them back.
        world.nodes.truncate(saved);
        world.nodes[glc as usize].i_plane = saved_glc_plane;
    } else {
        // Face genuinely enters the brush -> delete the whole original, keep the outside re-adds.
        world.nodes[ni].num_vertices = 0;
    }
}

/// The editor's `FilterWorldThroughBrush` recursion (`0x33250`): walk world node `i_node` and its
/// coplanar chain, pruning each child subtree by the brush bound SPHERE (`radius`, constant for the
/// whole descent).  Mirrors the decode's `if(NF_IsNew) return; d=PlaneDot(plane,center); DoFront =
/// d>=-R; DoBack = d<=R; if(both) filter; recurse gated children; iNode = iPlane`.
#[allow(clippy::too_many_arguments)]
fn filter_world_recurse(
    world: &mut Model,
    brush_temp: &Model,
    subtract: bool,
    mut i_node: i32,
    center: Vec3,
    radius: f32,
    collect: Option<CollectKind>,
    sink: &mut Vec<FPoly>,
) {
    while i_node != -1 {
        let (node_flags, nv, d) = {
            let n = &world.nodes[i_node as usize];
            let d = plane_dot_node(&n.plane, &center);
            (n.node_flags, n.num_vertices, d)
        };
        // Skip the brush's own freshly-added nodes (and stop the chain walk here, as the editor does).
        if node_flags & NF_IS_NEW != 0 {
            return;
        }
        let do_front = d >= -radius;
        let do_back = d <= radius;
        // The node plane STRADDLES the brush sphere -> filter its face (may add re-adds / mark dead).
        if do_front && do_back && nv > 0 {
            filter_one_world_node(world, brush_temp, subtract, i_node as usize, collect, sink);
        }
        // Re-read child/chain links AFTER the filter (matches the editor's post-filter recursion at
        // `0x33509`/`0x3351f`); the filter never edits this node's iFront/iBack, only the coplanar
        // chain tail, so this is equivalent but faithful.
        let (i_front, i_back, i_plane) = {
            let n = &world.nodes[i_node as usize];
            (n.i_front, n.i_back, n.i_plane)
        };
        if do_front && i_front != -1 {
            filter_world_recurse(
                world, brush_temp, subtract, i_front, center, radius, collect, sink,
            );
        }
        if do_back && i_back != -1 {
            filter_world_recurse(
                world, brush_temp, subtract, i_back, center, radius, collect, sink,
            );
        }
        i_node = i_plane;
    }
}

/// `FPlane::PlaneDot(FVector)` = `N·v - W` — signed distance of `v` from the node plane.
#[inline]
fn plane_dot_node(p: &Plane, v: &Vec3) -> f32 {
    p.x * v.x + p.y * v.y + p.z * v.z - p.w
}

/// World-thru-brush leaf funcs (`0x31b90` Add / `0x34980` Subtract, §8.1).  RE-ADD an outside cut
/// fragment (bit31 set) as a `NODE_Plane` node on `GLastCoplanar` sharing the original surf; DISCARD
/// an interior fragment (bump `GDiscarded`, mark the original dead).
fn wtb_leaf(world: &mut Model, ctx: &mut WtbCtx, edpoly: &FPoly, filter: i32, sink: &mut Vec<FPoly>) {
    // Phase-2 of intersect/deintersect: pure collector, no tree touch (see `WtbCtx::collect`).
    if let Some(kind) = ctx.collect {
        collect_leaf(kind, edpoly, filter, sink);
        return;
    }
    // RE-ADD set: Add {OUTSIDE, COPLANAR_OUTSIDE}; Subtract additionally {COSPATIAL_FACING_IN}.
    let re_add = filter == F_OUTSIDE
        || filter == F_COPLANAR_OUTSIDE
        || (ctx.subtract && filter == F_COSPATIAL_FACING_IN);
    if re_add {
        // bit31 gate: only a fragment a brush plane actually CUT off the face is re-added.
        if edpoly.poly_flags & PF_SPLIT_MARKER != 0 {
            let r = bsp_add_node(world, ctx.g_last_coplanar, NODE_PLANE, NF_IS_NEW, edpoly);
            trace_node_add(world, "FWTB", ctx.g_last_coplanar, NODE_PLANE, NF_IS_NEW, edpoly, r);
        }
    } else {
        // DISCARD: an interior fragment -> the face enters the brush.
        ctx.g_discarded += 1;
        if world.nodes[ctx.g_node as usize].num_vertices != 0 {
            world.nodes[ctx.g_node as usize].num_vertices = 0;
        }
    }
}

/// `wtb_filter_leaf` — the `FilterLeaf` dispatcher for the world-face-through-brush descent (mirrors
/// `filter_leaf`, but the leaf action is `wtb_leaf` writing the WORLD while descending the BRUSH).
#[allow(clippy::too_many_arguments)]
fn wtb_filter_leaf(
    world: &mut Model,
    brush: &Model,
    ctx: &mut WtbCtx,
    i_node: i32,
    edpoly: &FPoly,
    mut coplanar: Coplanar,
    leaf_outside: bool,
    sink: &mut Vec<FPoly>,
) {
    if coplanar.i_original_node == -1 {
        let filter = if leaf_outside { F_OUTSIDE } else { F_INSIDE };
        wtb_leaf(world, ctx, edpoly, filter, sink);
    } else if coplanar.processing_back {
        let fo = coplanar.front_outside;
        let filter = if !leaf_outside && !fo {
            F_COPLANAR_INSIDE
        } else if leaf_outside && fo {
            F_COPLANAR_OUTSIDE
        } else if !leaf_outside && fo {
            F_COSPATIAL_FACING_OUT
        } else {
            F_COSPATIAL_FACING_IN
        };
        wtb_leaf(world, ctx, edpoly, filter, sink);
    } else {
        coplanar.front_outside = leaf_outside;
        coplanar.processing_back = true;
        let back_seed = coplanar.back_seed;
        if coplanar.i_back_node == -1 {
            wtb_filter_leaf(world, brush, ctx, i_node, edpoly, coplanar, back_seed, sink);
        } else {
            let ibn = coplanar.i_back_node;
            wtb_filter_ed_poly(world, brush, ctx, ibn, edpoly, coplanar, back_seed, sink);
        }
    }
}

/// `wtb_filter_ed_poly` — `FilterEdPoly` descending the BRUSH temp BSP (`brush`), collecting outside
/// cut fragments back into the WORLD (`world`) via `wtb_leaf`.  Structurally identical to
/// `filter_ed_poly`; only the descent model and leaf action differ.
#[allow(clippy::too_many_arguments)]
fn wtb_filter_ed_poly(
    world: &mut Model,
    brush: &Model,
    ctx: &mut WtbCtx,
    mut i_node: i32,
    edpoly: &FPoly,
    coplanar: Coplanar,
    mut outside: bool,
    sink: &mut Vec<FPoly>,
) {
    let mut edpoly = edpoly.clone();
    loop {
        if edpoly.verts.len() >= 14 {
            let mut first = edpoly.clone();
            let half = first.split_in_half();
            wtb_filter_ed_poly(world, brush, ctx, i_node, &half, coplanar, outside, sink);
            edpoly = first;
        }

        let (i_front, i_back, csg, base, normal) = {
            let node = &brush.nodes[i_node as usize];
            let surf = &brush.surfs[node.i_surf as usize];
            let base = brush.points[surf.p_base as usize];
            let normal = brush.vectors[surf.v_normal as usize];
            (node.i_front, node.i_back, is_csg_filter(node), base, normal)
        };

        match edpoly.split_with_plane(&base, &normal, false) {
            Split::Front => {
                let no = outside || csg;
                if i_front == -1 {
                    wtb_filter_leaf(world, brush, ctx, i_node, &edpoly, coplanar, no, sink);
                    return;
                }
                i_node = i_front;
                outside = no;
            }
            Split::Back => {
                let no = outside && !csg;
                if i_back == -1 {
                    wtb_filter_leaf(world, brush, ctx, i_node, &edpoly, coplanar, no, sink);
                    return;
                }
                i_node = i_back;
                outside = no;
            }
            Split::Split(front, back) => {
                let fo = outside || csg;
                let bo = outside && !csg;
                if i_front == -1 {
                    wtb_filter_leaf(world, brush, ctx, i_node, &front, coplanar, fo, sink);
                } else {
                    wtb_filter_ed_poly(world, brush, ctx, i_front, &front, coplanar, fo, sink);
                }
                if i_back == -1 {
                    wtb_filter_leaf(world, brush, ctx, i_node, &back, coplanar, bo, sink);
                } else {
                    wtb_filter_ed_poly(world, brush, ctx, i_back, &back, coplanar, bo, sink);
                }
                return;
            }
            Split::Coplanar => {
                if coplanar.i_original_node != -1 {
                    let no = outside || csg;
                    if i_front == -1 {
                        wtb_filter_leaf(world, brush, ctx, i_node, &edpoly, coplanar, no, sink);
                        return;
                    }
                    i_node = i_front;
                    outside = no;
                    continue;
                }
                let dot = edpoly.normal.dot(&normal);
                let (facing_child, other_child, facing_out, other_out) = if dot >= 0.0 {
                    (i_front, i_back, outside || csg, outside && !csg)
                } else {
                    (i_back, i_front, outside && !csg, outside || csg)
                };
                let mut cop = Coplanar {
                    i_original_node: i_node,
                    i_back_node: other_child,
                    processing_back: false,
                    back_seed: other_out,
                    front_outside: outside,
                };
                if facing_child == -1 {
                    cop.front_outside = facing_out;
                    cop.processing_back = true;
                    if other_child == -1 {
                        wtb_filter_leaf(world, brush, ctx, i_node, &edpoly, cop, other_out, sink);
                    } else {
                        wtb_filter_ed_poly(
                            world, brush, ctx, other_child, &edpoly, cop, other_out, sink,
                        );
                    }
                } else {
                    wtb_filter_ed_poly(
                        world, brush, ctx, facing_child, &edpoly, cop, facing_out, sink,
                    );
                }
                return;
            }
        }
    }
}

/// Build the brush's plain convex temp BSP (`bspBuild(TempModel, …)`, §2): partition the LOOP-1
/// world-space brush faces with `SplitPolyList`.  The nodes are cleared of `NF_IsNew` so `IsCsg`
/// treats them as solid during the world-face descent (in front of a face = outside, behind all =
/// inside).  The CsgOper (for the leaf-func RE-ADD table's §8.1 F=4 case) is threaded separately via
/// `WtbCtx.subtract`, not here.  Built with `Opt=LAME, Balance=0, PortalBias=0` (byte-verified —
/// `bspBrushCSG @0x35b83`, findbestsplit-params-decode.md Evidence 4), replacing the historical
/// OPTIMAL/50/70 guess.  For a convex brush this is EMPIRICALLY SOUP-NEUTRAL (§82 §10.5) — kept as
/// the value the binary uses, not as a fix.  (The pinned N=33 roof under-merge is a LOOP-2 world-tree
/// ORDER divergence in `bsp_filter_fpoly`, not this temp brush — §82 §10.5.)
fn build_brush_temp_bsp(temp_polys: &[FPoly]) -> Result<Model, BuildError> {
    let mut tm = Model::default(); // root_outside = true
    let polys: Vec<FPoly> = temp_polys
        .iter()
        .cloned()
        .map(|mut p| {
            p.i_link = -1; // fresh surf per brush face (temp identity is irrelevant)
            p
        })
        .collect();
    // Temp-brush convex partition: LAME/0/0 (Score = 100*Splits, stride NumPolys/4) — the byte-verified
    // engine config; its splitter choice selects which brush face clips each straddling world face.
    split_poly_list(
        &mut tm,
        -1,
        NODE_ROOT,
        polys,
        0,
        TEMP_BALANCE,
        TEMP_PORTAL_BIAS,
        Opt::Lame,
        &mut 0,
        None,
    )?;
    for n in tm.nodes.iter_mut() {
        n.node_flags &= !NF_IS_NEW;
    }
    Ok(tm)
}

// --- FindBestSplit (EXACT engine scoring, no SPLIT_WEIGHT) + SplitPolyList --------------------

/// `FindBestSplit` (`0x335d0`) with the byte-verified repartition scoring.  This is the EXACT engine
/// score (no `SPLIT_WEIGHT` deviation) — required for byte-identity of the rebuilt tree.
///
/// `opt` selects the candidate-search stride (applied to BOTH the outer candidate loop AND the inner
/// front/back/split counting loop — decode `0x3369e imul 0x66666667; sar 3` = integer `NumPolys/20`,
/// `0x336bd cmovle 1`): `Opt::Good` = `Inc = max(NumPolys/20, 1)` (the repartition path);
/// `Opt::Lame` = `Inc = max(NumPolys/4, 1)` (the temp-brush convex partition — LAME per
/// findbestsplit-params-decode.md Evidence 4).  With `Inc>1` the returned `best` is the strided
/// winner index used directly as the splitter — the engine likewise splits on the strided winner
/// and then partitions ALL polys; only the SEARCH strides.
fn find_best_split_exact(polys: &[FPoly], balance: i32, portal_bias: i32, opt: Opt) -> usize {
    // Pre-pass (`0x336cb`..`0x336ef`): `all_structural` = every poly carries the `0x28`
    // (semisolid|notsolid) mask.  It tests the mask ALONE (`test byte [eax+0x1b0],0x28`) — being a
    // portal exempts a poly from the per-candidate skip below, NOT from this pre-pass.
    let is_structural = |pf: u32| (pf & 0x28) != 0;
    let all_structural = polys.iter().all(|p| is_structural(p.poly_flags));
    // Per-candidate skip (`0x3374b`..`0x33760`): a structural poly is skipped unless it is a portal
    // or the whole list is structural.
    let is_eligible = |pf: u32| !is_structural(pf) || (pf & csg::PF_PORTAL) != 0 || all_structural;
    if polys.len() == 1 {
        return 0;
    }
    let inc = opt.stride(polys.len());
    let bal = balance as f32;
    let inv_bal = (100 - balance) as f32;
    let pbias = portal_bias as f32 / 100.0;
    let mut best = usize::MAX;
    let mut best_score = f32::INFINITY;
    // The candidate loop walks SLOTS, not a plain `(0..n).step_by(inc)`.  Slot `k` spans
    // `[k*inc, (k+1)*inc)` and the candidate is the FIRST ELIGIBLE poly in that window: an
    // ineligible one advances WITHIN the window (`0x33760 je 0x33734`, back to `inc esi`), and the
    // slot only ends when `esi` reaches the running threshold `[ebp-0x24]` (`0x3373b`), which the
    // loop-back at `0x338c1` then uses as the next slot's start.
    let mut slot = 0;
    while slot < polys.len() {
        let window_end = (slot + inc).min(polys.len());
        let cand_i = (slot..window_end).find(|&k| is_eligible(polys[k].poly_flags));
        slot += inc;
        let Some(i) = cand_i else { continue };
        let cand = &polys[i];
        let cand_portal = (cand.poly_flags & csg::PF_PORTAL) != 0;
        let (mut front, mut back, mut splits) = (0i32, 0i32, 0f32);
        let mut j = 0;
        while j < polys.len() {
            if j != i {
                let p = &polys[j];
                match p.split_with_plane(&cand.base, &cand.normal, false) {
                    Split::Front => front += 1,
                    Split::Back => back += 1,
                    Split::Coplanar => {}
                    Split::Split(_, _) => {
                        splits += if (p.poly_flags & csg::PF_PORTAL) != 0 {
                            16.0
                        } else {
                            1.0
                        };
                    }
                }
            }
            j += inc;
        }
        // Score2 = (100-Balance)*Splits ; Score = |F-B|*Balance + Score2 (Score2 added last).
        let score2 = inv_bal * splits;
        let mut score = (front - back).abs() as f32 * bal + score2;
        if cand_portal {
            score -= score2 * pbias;
        }
        if best == usize::MAX || score < best_score {
            best_score = score;
            best = i;
        }
    }
    if best == usize::MAX {
        0
    } else {
        best
    }
}

/// Forensic twin of `find_best_split_exact` (UEDCLI_REPART_FBS_DUMP) — same candidate-slot walk,
/// but returns one row per candidate SLOT (eligible or skipped) instead of just the winner.  Kept
/// separate so the traced path never touches the hot loop above.  Row: (slot_start, cand_i,
/// eligible, plane, poly_flags, portal, front, back, splits, score).
struct FbsRow {
    slot: usize,
    cand_i: Option<usize>,
    plane: Option<(f32, f32, f32, f32)>,
    poly_flags: u32,
    portal: bool,
    front: i32,
    back: i32,
    splits: f32,
    score: f32,
}

fn find_best_split_trace(polys: &[FPoly], balance: i32, portal_bias: i32, opt: Opt) -> (usize, Vec<FbsRow>) {
    let is_structural = |pf: u32| (pf & 0x28) != 0;
    let all_structural = polys.iter().all(|p| is_structural(p.poly_flags));
    let is_eligible = |pf: u32| !is_structural(pf) || (pf & csg::PF_PORTAL) != 0 || all_structural;
    let mut rows = Vec::new();
    if polys.len() == 1 {
        return (0, rows);
    }
    let inc = opt.stride(polys.len());
    let bal = balance as f32;
    let inv_bal = (100 - balance) as f32;
    let pbias = portal_bias as f32 / 100.0;
    let mut best = usize::MAX;
    let mut best_score = f32::INFINITY;
    let mut slot = 0;
    while slot < polys.len() {
        let window_end = (slot + inc).min(polys.len());
        let cand_i = (slot..window_end).find(|&k| is_eligible(polys[k].poly_flags));
        let Some(i) = cand_i else {
            rows.push(FbsRow { slot, cand_i: None, plane: None, poly_flags: 0, portal: false,
                                front: 0, back: 0, splits: 0.0, score: f32::NAN });
            slot += inc;
            continue;
        };
        let cand = &polys[i];
        let cand_portal = (cand.poly_flags & csg::PF_PORTAL) != 0;
        let (mut front, mut back, mut splits) = (0i32, 0i32, 0f32);
        let mut j = 0;
        while j < polys.len() {
            if j != i {
                let p = &polys[j];
                match p.split_with_plane(&cand.base, &cand.normal, false) {
                    Split::Front => front += 1,
                    Split::Back => back += 1,
                    Split::Coplanar => {}
                    Split::Split(_, _) => {
                        splits += if (p.poly_flags & csg::PF_PORTAL) != 0 { 16.0 } else { 1.0 };
                    }
                }
            }
            j += inc;
        }
        let score2 = inv_bal * splits;
        let mut score = (front - back).abs() as f32 * bal + score2;
        if cand_portal {
            score -= score2 * pbias;
        }
        rows.push(FbsRow {
            slot, cand_i: Some(i),
            plane: Some((cand.base.x, cand.base.y, cand.base.z, 0.0))
                .map(|_| (cand.normal.x, cand.normal.y, cand.normal.z,
                          cand.normal.x * cand.base.x + cand.normal.y * cand.base.y + cand.normal.z * cand.base.z)),
            poly_flags: cand.poly_flags, portal: cand_portal, front, back, splits, score,
        });
        if best == usize::MAX || score < best_score {
            best_score = score;
            best = i;
        }
        slot += inc;
    }
    (if best == usize::MAX { 0 } else { best }, rows)
}

/// `SplitPolyList` (`0x34530`): make `FindBestSplit`'s plane a node, chain its coplanars, partition
/// the rest, recurse front/back.  Emits into `model`.  `rsp_links` engages the engine's
/// `RebuildSimplePolys` mode: seed `iLink=Surfs.Num` on the splitter (a fresh surf per call) and
/// `Surfs.Num()-1` on its coplanars (share the splitter's surf) — the bspBuild-from-brush-polys
/// path (`build_brush_model`).  The Vec records each SOURCE poly's assigned link (indexed by
/// `FPoly::src`), mirroring the editor's in-place `Polys` mutation: a poly consumed WHOLE gets its
/// saved `iLink` rewritten to the assigned surf; a split poly's entry is never touched (fragments
/// are copies, `src=-1`).  The repartition/temp-brush callers pass `None` (iLink pre-seeded).
#[allow(clippy::too_many_arguments)]
fn split_poly_list(
    model: &mut Model,
    i_parent: i32,
    place: i32,
    mut polys: Vec<FPoly>,
    depth: usize,
    balance: i32,
    portal_bias: i32,
    opt: Opt,
    call_id: &mut usize,
    mut rsp_links: Option<&mut Vec<i32>>,
) -> Result<(), BuildError> {
    if polys.is_empty() {
        return Ok(());
    }
    if depth > 8192 {
        return Err(BuildError(
            "bspcsg: SplitPolyList exceeded max depth".into(),
        ));
    }
    let my_id = *call_id;
    *call_id += 1;
    // FORENSIC CANDIDATE DUMP (UEDCLI_REPART_FBS_DUMP) — env-gated; one CALL header + one CAND row
    // per candidate slot `find_best_split_exact` walked, so a specific repartition SplitPolyList
    // call (identified by the resulting `i_node`, since `call_id` alone isn't stable across builds)
    // can be pulled out and its full scoring table inspected against the real editor's choice.
    let fbs_dump = std::env::var("UEDCLI_REPART_FBS_DUMP").is_ok();
    let (i_best, splitter) = if fbs_dump {
        let (i_best, rows) = find_best_split_trace(&polys, balance, portal_bias, opt);
        (i_best, Some(rows))
    } else {
        (find_best_split_exact(&polys, balance, portal_bias, opt), None)
    };
    let mut splitter_poly = polys[i_best].clone();
    if let Some(links) = rsp_links.as_deref_mut() {
        splitter_poly.i_link = model.surfs.len() as i32; // fresh surf for this call's splitter
        if splitter_poly.src >= 0 {
            links[splitter_poly.src as usize] = splitter_poly.i_link;
        }
    }
    let i_node = bsp_add_node(model, i_parent, place, NF_IS_NEW, &splitter_poly);
    if let Some(rows) = splitter {
        eprintln!(
            "REPART_CALL id={} i_node={} depth={} numpolys={} best_i={} best_plane=({:.6},{:.6},{:.6},{:.6})",
            my_id, i_node, depth, polys.len(), i_best,
            splitter_poly.normal.x, splitter_poly.normal.y, splitter_poly.normal.z,
            splitter_poly.normal.x * splitter_poly.base.x
                + splitter_poly.normal.y * splitter_poly.base.y
                + splitter_poly.normal.z * splitter_poly.base.z,
        );
        for r in &rows {
            match (r.cand_i, r.plane) {
                (Some(i), Some((nx, ny, nz, d))) => eprintln!(
                    "REPART_CAND id={} slot={} i={} plane=({:.6},{:.6},{:.6},{:.6}) flags={:#x} portal={} front={} back={} splits={} score={:.6}",
                    my_id, r.slot, i, nx, ny, nz, d, r.poly_flags, r.portal, r.front, r.back, r.splits, r.score
                ),
                _ => eprintln!("REPART_CAND id={} slot={} SKIPPED", my_id, r.slot),
            }
        }
    }
    let splitter = splitter_poly;

    let mut front: Vec<FPoly> = Vec::new();
    let mut back: Vec<FPoly> = Vec::new();
    for (j, p) in polys.drain(..).enumerate() {
        if j == i_best {
            continue;
        }
        // TEMPORARY DIAGNOSTIC (UEDCLI_REPART_TRACE_LINK=<i_link>) -- unatco-verts-points-residual-
        // after-the-zone, child=6108: find exactly which splitter plane cuts the poly with this
        // i_link, to locate the spurious split producing the 41st node.
        if let Ok(want) = std::env::var("UEDCLI_REPART_TRACE_LINK") {
            if want.parse::<i32>() == Ok(p.i_link) {
                let result_kind = match p.split_with_plane(&splitter.base, &splitter.normal, false) {
                    Split::Front => "Front".to_string(),
                    Split::Back => "Back".to_string(),
                    Split::Coplanar => "Coplanar".to_string(),
                    Split::Split(f, b) => format!("Split(front_nv={}, back_nv={})", f.verts.len(), b.verts.len()),
                };
                eprintln!(
                    "TRACE_LINK i_link={} depth={} splitter_i_link={} splitter_plane=({:.6},{:.6},{:.6},{:.6}) poly_nv={} result={}",
                    p.i_link, depth, splitter.i_link,
                    splitter.normal.x, splitter.normal.y, splitter.normal.z,
                    splitter.normal.x * splitter.base.x + splitter.normal.y * splitter.base.y + splitter.normal.z * splitter.base.z,
                    p.verts.len(), result_kind
                );
            }
        }
        match p.split_with_plane(&splitter.base, &splitter.normal, false) {
            Split::Front => front.push(p),
            Split::Back => back.push(p),
            Split::Coplanar => {
                let mut p = p;
                if let Some(links) = rsp_links.as_deref_mut() {
                    p.i_link = model.surfs.len() as i32 - 1; // share the splitter's fresh surf
                    if p.src >= 0 {
                        links[p.src as usize] = p.i_link;
                    }
                }
                bsp_add_node(model, i_node, NODE_PLANE, NF_IS_NEW, &p);
            }
            Split::Split(mut f, mut b) => {
                // Editor `SplitPolyList` case-3 (`Editor.dll 0x346f9`): append `Front` to `FrontList`
                // and `Back` to `BackList`; THEN, if a fragment has `NumVertices >= 0xe` (14), call
                // `FPoly::SplitInHalf` on it and append the returned second half to the SAME list
                // (`Front` half -> `FrontList`, `0x34716`..`0x3475b`; `Back` half -> `BackList`,
                // `0x3475f`..`0x347a1`).  The engine appends `Front` FIRST then splits it in place, so
                // the list holds `[first-half, second-half]` — reproduced here by pushing the
                // (now first-half) `f`/`b` then the second half.  It is a SINGLE split: the editor
                // re-checks neither half (no `<14` loop — matched exactly).  Native already omitted
                // this in repartition (present in the CSG-filter paths, `filter_ed_poly` / `csg`); the
                // castle never yields a >=14-vert repartition fragment, so this is a no-op there.
                if f.fix() >= 3 {
                    if f.verts.len() >= 14 {
                        let h = f.split_in_half();
                        front.push(f);
                        front.push(h);
                    } else {
                        front.push(f);
                    }
                }
                if b.fix() >= 3 {
                    if b.verts.len() >= 14 {
                        let h = b.split_in_half();
                        back.push(b);
                        back.push(h);
                    } else {
                        back.push(b);
                    }
                }
            }
        }
    }
    split_poly_list(
        model,
        i_node,
        NODE_FRONT,
        front,
        depth + 1,
        balance,
        portal_bias,
        opt,
        call_id,
        rsp_links.as_deref_mut(),
    )?;
    split_poly_list(
        model,
        i_node,
        NODE_BACK,
        back,
        depth + 1,
        balance,
        portal_bias,
        opt,
        call_id,
        rsp_links,
    )?;
    Ok(())
}

// --- bspRepartition (bspBuildFPolys -> bspMergeCoplanars -> bspBuild -> bspRefresh) -----------

/// `bspBuildFPolys` (`0x36090`): reconstruct every node into an FPoly (retaining every CSG
/// fragmentation vertex — the fat repartition input), `iLink` = source surf.
/// `MakeEdPolys` (`Editor.dll` RVA `0x33bb0`, reached via `bspBuildFPolys` `0x36090`): a recursive
/// pre-order tree walk **(self, front, back, plane)** from the root, emitting every node whose
/// reconstructed face has >=3 verts.  The face ORDER is therefore tree-STRUCTURAL, NOT node-index.
/// After `bsp_cleanup` splices the dead nodes out, this order matches the editor's soup order
/// exactly (verified node-for-node against `editor-struct-33.log`), which is what drives
/// `bspMergeCoplanars` + `bspBuild` to node-for-node parity.  (The old index-order iteration
/// produced the right face SET but the wrong ORDER — see `bsp_cleanup` and `sections/82` §10.8.)
fn bsp_build_fpolys(model: &Model) -> Vec<FPoly> {
    let mut out = Vec::new();
    if !model.nodes.is_empty() {
        make_ed_polys(model, 0, &mut out);
    }
    out
}

fn make_ed_polys(model: &Model, i_node: i32, out: &mut Vec<FPoly>) {
    if let Some(p) = bsp_node_to_fpoly(model, i_node as usize) {
        out.push(p); // emit self BEFORE recursing (0x33bef..0x33c5d).
    }
    let (i_f, i_b, i_p) = {
        let n = &model.nodes[i_node as usize];
        (n.i_front, n.i_back, n.i_plane)
    };
    if i_f != -1 {
        make_ed_polys(model, i_f, out);
    }
    if i_b != -1 {
        make_ed_polys(model, i_b, out);
    }
    if i_p != -1 {
        make_ed_polys(model, i_p, out);
    }
}

/// Garbage-collect `model.nodes`: drop everything unreachable from root 0 (walking
/// `i_front`/`i_back`/`i_plane`), compact, and remap every surviving node's links. `bsp_add_node`
/// always APPENDS (never reuses a freed slot), so grafting a new subtree onto an existing parent
/// (`repartition_frontier`) leaves the old subtree's nodes as permanent orphans unless something
/// collects them — `passes::bsp_refresh` does NOT (it only compacts surfs/verts, not nodes; see its
/// own doc comment). Needed for the repartition-frontier graft to be net-zero on node count, the
/// way the editor's own "`bspBuild` bumps the count and `bspRefresh` brings it back" is.
///
/// Returns the `old index -> new index` remap (`-1` for a removed node) so a caller holding OTHER
/// node-index references (e.g. `repartition_frontier`'s still-pending worklist) can fix them up —
/// see `UEDCLI_REPART_COMPACT_PER_CALL`, testing whether the editor's real per-subtree `bspRefresh`
/// compacts nodes immediately (not just once at the very end, as native currently does).
fn compact_unreachable_nodes(model: &mut Model) -> Vec<i32> {
    if model.nodes.is_empty() {
        return Vec::new();
    }
    let mut reachable = vec![false; model.nodes.len()];
    let mut stack = vec![0i32];
    while let Some(ni) = stack.pop() {
        if ni < 0 || reachable[ni as usize] {
            continue;
        }
        reachable[ni as usize] = true;
        let n = &model.nodes[ni as usize];
        stack.push(n.i_front);
        stack.push(n.i_back);
        stack.push(n.i_plane);
    }
    let mut remap = vec![-1i32; model.nodes.len()];
    let mut new_nodes = Vec::with_capacity(model.nodes.len());
    for (i, &r) in reachable.iter().enumerate() {
        if r {
            remap[i] = new_nodes.len() as i32;
            new_nodes.push(model.nodes[i].clone());
        }
    }
    let relink = |i: i32, remap: &[i32]| if i >= 0 { remap[i as usize] } else { -1 };
    for n in new_nodes.iter_mut() {
        n.i_front = relink(n.i_front, &remap);
        n.i_back = relink(n.i_back, &remap);
        n.i_plane = relink(n.i_plane, &remap);
    }
    model.nodes = new_nodes;
    remap
}

/// Port of `sub_49380` (`Editor.dll 0x10049380`) — see `unatco-verts-points-residual-after-the-zone`.
fn collect_repartition_frontier(model: &Model, ni: i32, list_a: &mut Vec<i32>, list_b: &mut Vec<i32>) {
    if ni < 0 {
        return;
    }
    let (i_back, i_front) = {
        let n = &model.nodes[ni as usize];
        (n.i_back, n.i_front)
    };
    if i_back == -1 {
        list_a.push(ni);
    } else {
        collect_repartition_frontier(model, i_back, list_a, list_b);
    }
    if i_front == -1 {
        list_b.push(ni);
    } else {
        collect_repartition_frontier(model, i_front, list_a, list_b);
    }
}

/// Re-partition every frontier slot that grew a subtree during the detail-brush loop
/// (`bspRepartition(Model, iChild, 2)`, `Editor.dll 0x1004aa3f`/`0x1004aa90`): reconstruct the
/// subtree's polygons (`make_ed_polys`) and rebuild via `split_poly_list` onto the same parent
/// slot. `list_a` grafts onto `NODE_BACK` (native's `i_back` = editor's iFront), `list_b` onto
/// `NODE_FRONT`. Leaves old subtree nodes as orphans — caller must run
/// `compact_unreachable_nodes` after, `bsp_refresh` does NOT collect them (surfs/verts only).
/// Port of `bspRepartition`'s per-subtree call (`Editor.dll 0x10049fc0`), called once per
/// `collect_repartition_frontier` entry. **The real editor's call is a NODE no-op that PERMANENTLY
/// leaks `Verts`/`Points`, and this reproduces that exactly rather than "fixing" it — the goal is
/// byte-identical output, and the editor's real output includes this waste.**
///
/// Live-verified exhaustively on UNATCO's full 209-call sequence
/// (`unatco-verts-points-residual-after-the-zone`, `repart-stage-unatco.log`, cross-checked against
/// 26 individually byte-diffed live captures): every call's real `bspBuildFPolys` →
/// `bspMergeCoplanars` → `bspBuild`/`SplitPolyList` reconstruction builds a whole NEW subtree via
/// real `bspAddNode` calls (growing `Nodes`/`Verts`/`Points`) — but the SAME call's own `bspRefresh`
/// (`Core.dll!FArray::Remove`, IAT-confirmed) discards the new NODE structure every single time,
/// landing `Nodes.Num` back at the exact pre-call baseline (209/209 calls, no exceptions). It does
/// NOT correspondingly compact `Verts`/`Points`: those pools keep every vertex the discarded
/// reconstruction allocated (0/209 calls net to zero vert growth — every call grows it, summing
/// exactly to the aggregate `44314→54776` figure). So the parent's pre-existing child is left
/// exactly as it was, and only the `Verts`/`Points` growth from computing the (correctly merged,
/// per `child=6108`'s live cross-check) reconstruction survives.
///
/// Implementation: run the real reconstruction into a throwaway `scratch` clone of `model` (so
/// `bsp_add_node`'s coplanar-chain walk and `MAX_VERTICES` splitting see the SAME pre-existing tree
/// state the real call would), then copy out only the `Verts`/`Points` it appended — never
/// `model.nodes`, never `model.surfs`. The scratch build DOES allocate surfs — the editor's own
/// `SplitPolyList` re-seeds each splitter (see the `rsp_links` block below) — but they live and die
/// in `scratch`; only the Verts/Points it appended are copied out.
fn repartition_frontier(model: &mut Model, list_a: &[i32], list_b: &[i32], surf_pool_len: usize)
    -> Result<(), BuildError> {
    let mut call_id = 0usize;
    let mut surf_pool = surf_pool_len;
    let worklist: Vec<(i32, i32)> = list_a.iter().map(|&n| (n, NODE_BACK))
        .chain(list_b.iter().map(|&n| (n, NODE_FRONT)))
        .collect();
    // Per-call Verts/Points before/after, to verify the fix directly against the editor's own
    // per-call growth (`repart-stage-unatco.log`/`wanchai-ed-repart-stage.log`). Zero effect on the
    // default path.
    let percall_verts_diag = std::env::var("UEDCLI_REPART_PERCALL_VERTS").is_ok();
    for (seq, &(parent, place)) in worklist.iter().enumerate() {
        let child = if place == NODE_BACK {
            model.nodes[parent as usize].i_back
        } else {
            model.nodes[parent as usize].i_front
        };
        if child == -1 {
            continue;
        }
        let mut polys = Vec::new();
        make_ed_polys(model, child, &mut polys);
        let merged = reduce_repartition_polys(polys);
        // `bspRepartition`'s own `bspBuildFPolys` EMPTIES `Model->Polys` and refills it from this
        // subtree (`Editor.dll 0x1004a007`), `bspMergeCoplanars` merges it in place (`0x1004a021`),
        // and each survivor comes out `PF_EdProcessed` — and nothing after this loop rebuilds it
        // (`csgRebuild` runs only `bspOptGeom`/`bspBuildBounds`). So the LAST frontier call's soup is
        // what the world Model saves, not the structural repartition's. It only shows once a level
        // has a detail brush (nothing grows the frontier otherwise): WanChai N35's first semisolid
        // Add leaves UED22 with that brush's 8 faces in `Model.Polys` where native kept the 320-face
        // structural soup.
        let mut soup = merged.clone();
        if merged.is_empty() {
            model.polys = soup;
            continue;
        }
        let before_verts = model.verts.len();
        let before_points = model.points.len();

        // `SplitPolyList` with a non-zero `RebuildSimplePolys` (the frontier calls pass 2) hands its
        // SPLITTER a fresh surf — `EdPoly->iLink = Model->Surfs.Num()` (`Editor.dll 0x100345cf`/
        // `0x100345d4`), which `bspAddNode` (`0x10034ee3`) then allocates — and gives each coplanar
        // `Surfs.Num()-1` to share it (`0x1003468c`/`0x1003469b`). A SPLIT poly is never rewritten
        // (`0x100346f9` puts fresh fragments in the lists and leaves the source alone), so it keeps
        // the iLink `bspBuildFPolys` gave it. `split_poly_list`'s `rsp_links` mode is that exact rule,
        // already golden-verified on the mover models — use it rather than inferring an order.
        let ready: Vec<FPoly> = merged
            .into_iter()
            .enumerate()
            .map(|(i, mut p)| {
                p.src = i as i32;
                p
            })
            .collect();
        let mut links: Vec<i32> = soup.iter().map(|p| p.i_link).collect();
        let mut scratch = model.clone();
        let scratch_surfs = scratch.surfs.len();
        split_poly_list(&mut scratch, parent, place, ready, 0, BALANCE, PORTAL_BIAS, Opt::Good,
                        &mut call_id, Some(&mut links))?;
        // Keep the Verts/Points growth (the real editor's permanent leak); discard everything else
        // in `scratch` — its new node tree and its own copy of the parent's rewritten child pointer
        // never touch `model`.
        model.points.extend_from_slice(&scratch.points[before_points..]);
        model.verts.extend_from_slice(&scratch.verts[before_verts..]);

        // Native's surf pool is the repartition-rebuilt (shorter) one, so shift each freshly assigned
        // index into the editor's pool. `surf_pool` tracks that pool across the loop: the call's own
        // `bspRefresh` runs `NoRemapSurfs=1` (`0x10036d68` memzeroes the poly-ref table, so nothing is
        // dropped) and only `bspOptGeom`'s `bspRefresh(Model,0)` (`0x100368ef`) collects them later,
        // so every call's allocations are still in the pool when the next call starts.
        let offset = surf_pool as i32 - scratch_surfs as i32;
        for (p, &l) in soup.iter_mut().zip(links.iter()) {
            if l >= scratch_surfs as i32 {
                p.i_link = l + offset;
            }
            p.poly_flags |= PF_ED_PROCESSED;
        }
        surf_pool += scratch.surfs.len() - scratch_surfs;
        model.polys = soup;

        if percall_verts_diag {
            eprintln!(
                "REPART_PERCALL seq={seq} parent={parent} place={place} child={child} verts_before={before_verts} verts_after={} points_before={before_points} points_after={}",
                model.verts.len(), model.points.len()
            );
        }
    }
    Ok(())
}

/// `bspMergeCoplanars` (`0x36200`) with `MergeDisparateTextures=0`: group polys sharing iLink +
/// coplanar-offset + same-facing normal + matching texture axes, then fuse each group>1 by
/// fixpoint pairwise edge-merge (`TryToMerge`).  Retains T-junction fragmentation the engine keeps.
///
/// ORDER (decoded 2026-07-18, `sections/82` §10.10): the engine's compaction pass (`0x36480`) walks
/// `Polys[0..Num)` in ORIGINAL index order and keeps every poly with `NumVertices != 0` — it does
/// NOT cluster a group at its head.  The grouping/merge phase only marks members and EMPTIES
/// (`NumVertices=0`) the faces fused away; the survivors stay in their tree-walk positions.  So the
/// merged soup preserves `MakeEdPolys`'s tree-walk order minus the fused-away faces — which is the
/// exact ORDER `bspBuild`/`SplitPolyList` then consumes (verified vs `editor_polys_oracle.py`).
/// (The prior port clustered each whole group at its head index; that produced the right face SET
/// but the wrong ORDER, leaving `node_diff` prefix stuck at 0.)
///
/// The candidate (`j`) scan does NOT skip a poly already claimed by an earlier group: the engine's
/// inner loop (`0x100362fc`-`0x1003641d`) tests `iLink`/coplanar/normal/UV against `Polys[j]`
/// unconditionally and re-sets its `0x40000000` bit even if already set — only the OUTER anchor
/// role is skip-gated on that flag (`0x100362b9`). So one poly can be pulled into more than one
/// group's candidate list; `merge_group`'s own `NumVertices<=0` skip makes a second pass over an
/// already-fused member a no-op, matching the engine's `MergeCoplanarPolys` per-member check.
fn bsp_merge_coplanars(polys: Vec<FPoly>) -> Vec<FPoly> {
    let mut polys = polys;
    let mut grouped = vec![false; polys.len()];
    let n = polys.len();
    let mut i = 0;
    while i < n {
        if grouped[i] {
            i += 1;
            continue;
        }
        grouped[i] = true;
        let mut group = vec![i];
        for j in (i + 1)..n {
            if merge_group_pred(&polys[i], &polys[j]) {
                grouped[j] = true;
                group.push(j);
            }
        }
        if group.len() > 1 {
            merge_group(&mut polys, &group);
        }
        i += 1;
    }
    // Compaction (`0x36480`): keep survivors in ORIGINAL index order (NOT clustered by group).
    let mut out = Vec::new();
    for p in polys {
        if !p.verts.is_empty() {
            out.push(p);
        }
    }
    out
}

/// TEMPORARY EXPERIMENT — `unatco-verts-points-residual-after-the-zone`, coordinator's sharper
/// hypothesis (2026-08-30): `bspBuildFPolys` (the step BEFORE `bspMergeCoplanars`) may walk
/// `Model->Surfs` (a flat array with ONE entry per surf, regardless of how many nodes/fragments
/// share it) rather than the node tree — which would emit exactly one poly per unique `i_link`,
/// with NO geometric weld involved, and `bspMergeCoplanars` would be a separate LATER step doing
/// genuine geometric merging of DISTINCT-surf adjacent fragments (not what closes the 40→29 gap).
/// This is the crude test of that: keep only the FIRST poly encountered per unique `i_link`, no
/// geometry, no `try_to_merge`. If this reproduces the same counts/shapes `bsp_merge_coplanars`
/// does, dedup and merge coincide on the tested calls (doesn't distinguish them); if not, or if
/// wiring this blanket-wide lands closer to 6314 than the merge's 5689, that's a real signal.
fn surf_dedup(polys: Vec<FPoly>) -> Vec<FPoly> {
    let mut seen = std::collections::HashSet::new();
    polys.into_iter().filter(|p| seen.insert(p.i_link)).collect()
}

/// Dispatcher for the two `repartition_frontier` reduction experiments, selected by
/// `UEDCLI_REPART_MERGE_MODE` (`dedup` -> `surf_dedup`; anything else, including unset -> the
/// already-tested `bsp_merge_coplanars`) so `UEDCLI_REPART_BLANKET_MERGE`/`UEDCLI_REPART_ISOLATED_TREE`
/// share one switch. TEMPORARY — `unatco-verts-points-residual-after-the-zone`.
fn reduce_repartition_polys(polys: Vec<FPoly>) -> Vec<FPoly> {
    match std::env::var("UEDCLI_REPART_MERGE_MODE").as_deref() {
        Ok("dedup") => surf_dedup(polys),
        _ => bsp_merge_coplanars(polys),
    }
}

fn merge_group_pred(a: &FPoly, b: &FPoly) -> bool {
    if a.i_link != b.i_link {
        return false;
    }
    let d = a.normal.dot(&b.base.sub(&a.base));
    if !(-0.001 < d && d < 0.001) {
        return false;
    }
    if !(a.normal.dot(&b.normal) > 0.9999) {
        return false;
    }
    // MergeDisparateTextures=0 -> require matching texture axes (4e-4).
    if a.texture_u.sub(&b.texture_u).size() > 4.0e-4 {
        return false;
    }
    if a.texture_v.sub(&b.texture_v).size() > 4.0e-4 {
        return false;
    }
    true
}

/// `FPointsAreSame` (Editor.dll `0x32b90`): per-component **box** test at `THRESH_POINTS_ARE_SAME`
/// (0.002) — each axis independently, NOT Euclidean distance.  A pair `0.002 < d < 0.0034` apart on
/// a diagonal passes a `.size()` (Euclidean) test's failure but fails this box test's success (and
/// vice-versa): the box test is what decides whether two fragment corners are "the same" vertex,
/// so it must match the engine exactly (verified live 2026-07-17, `sections/82 §7c`).
/// Per-component **box** coincidence test: each axis must differ by less than `tol` (NOT Euclidean
/// distance).  `points_are_same`/`points_are_near` are the SAME(0.002)/NEAR(0.015) pair — the same
/// dichotomy `build.rs::bsp_add_point` uses for point pooling.
#[inline]
fn points_are_same_with(p: &Vec3, q: &Vec3, tol: f32) -> bool {
    (p.x - q.x).abs() < tol && (p.y - q.y).abs() < tol && (p.z - q.z).abs() < tol
}

#[inline]
fn points_are_same(p: &Vec3, q: &Vec3) -> bool {
    points_are_same_with(p, q, THRESH_POINTS_ARE_SAME)
}

#[inline]
fn points_are_near(p: &Vec3, q: &Vec3) -> bool {
    points_are_same_with(p, q, THRESH_POINTS_ARE_NEAR)
}

/// `MergeCoplanarPolys` (Editor.dll `0x33cb0`): fixpoint pairwise `TryToMerge` over one group.
/// Instruction-exact iteration (`sections/82 §7c`): `while(Try){ Try=0; for i: Pi=group[i];
/// if NumVertices(Pi)<=0 skip; for j=i+1: Pj=group[j]; if NumVertices(Pj)<=0 skip; if
/// TryToMerge(Pi,Pj) Try=1 }`.  `Pi` **accumulates** — after Pi absorbs Pj (Pj emptied) the SAME
/// (now larger) Pi keeps trying against j+1, j+2, …; a successful pass re-runs the whole outer loop.
/// Only the upper triangle `j>i` is scanned (not all ordered pairs).
fn merge_group(polys: &mut [FPoly], group: &[usize]) {
    let g = group.len();
    let mut try_again = true;
    while try_again {
        try_again = false;
        for a in 0..g {
            let ia = group[a];
            if polys[ia].verts.is_empty() {
                continue;
            }
            for b in (a + 1)..g {
                let ib = group[b];
                if polys[ib].verts.is_empty() {
                    continue;
                }
                if let Some(m) = try_to_merge(&polys[ia], &polys[ib]) {
                    polys[ia] = m;
                    polys[ib].verts.clear(); // Other->NumVertices = 0
                    try_again = true;
                }
            }
        }
    }
}

/// `FPoly::TryToMerge` (Editor.dll `0x34b10`) — instruction-level transcription (`sections/82 §7c`).
/// Fuses `b` into `a` iff the two coplanar polys share exactly one **edge** (two adjacent verts in
/// opposite winding).  Returns the merged poly, or `None` if not mergeable.  Transcribed steps:
///   1. Gate: `NumVertices(a) + NumVertices(b) > 16` (`FPoly::VERTEX_THRESHOLD`) → `None`.
///   2. Scan `(i,j)` in row order for the FIRST `FPointsAreSame(a[i], b[j])` → `(Start1,Start2)`;
///      none → `None`.  (Only this first coincident point is considered — a later matching pair is
///      never tried, so the merge is order-sensitive exactly as the engine is.)
///   3. Forward test `a[(Start1+1)%NV1]` vs `b[(Start2-1)%NV2]`: match ⇒ `End1=Start1+1,
///      Start2=Start2-1`.  Else backward test `a[(Start1-1)%NV1]` vs `b[(Start2+1)%NV2]`: match ⇒
///      `Start1=Start1-1, End2=Start2+1`.  Neither ⇒ `None` (only one point overlaps).  The neighbour
///      tests use the NEAR (0.015) box coincidence, the step-2 anchor still SAME (0.002) — so two
///      coplanar source-face fragments fuse when their shared edge is off by a fractional-brush seam.
///   4. Build ring: ALL `NV1` verts of `a` starting at `End1` (wrapping), then `NV2-2` verts of
///      `b` starting at `(End2+1)%NV2` (pre-increment) — i.e. `b`'s verts minus its two shared ones.
///   5. `RemoveColinears`; reject if it collapses `<3` verts or the result exceeds 16 verts.
fn try_to_merge(a: &FPoly, b: &FPoly) -> Option<FPoly> {
    let nv1 = a.verts.len() as i32;
    let nv2 = b.verts.len() as i32;
    // 1. FPoly::VERTEX_THRESHOLD == 16.
    if nv1 + nv2 > 16 {
        return None;
    }
    // 2. First coincident point in (i,j) scan order.
    let (mut start1, mut start2) = (-1i32, -1i32);
    'find: for i in 0..nv1 {
        for j in 0..nv2 {
            if points_are_same(&a.verts[i as usize], &b.verts[j as usize]) {
                start1 = i;
                start2 = j;
                break 'find;
            }
        }
    }
    if start1 < 0 {
        return None;
    }
    let wrap = |x: i32, n: i32| {
        if x >= n {
            x - n
        } else if x < 0 {
            x + n
        } else {
            x
        }
    };
    // 3. Forward / backward neighbour test.  The neighbours need only be NEAR (0.015), not SAME
    //    (0.002): two fragments of one source face whose shared-edge corner sits a few units out
    //    of exact register (a fractional-brush seam) still fuse, matching the editor.
    let mut end1 = start1;
    let mut end2 = start2;
    // `UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME` — EXPERIMENT. Fresh raw disassembly of `TryToMerge`
    // (`Editor.dll 0x34b10`, 2026-09-02) shows all THREE coincidence tests — the step-2 anchor
    // (`0x34bdb`) AND both step-3 neighbour edge tests (`0x34c46`, `0x34ca9`) — `call 0x10032b90`,
    // which is `FPointsAreSame` with the ±0.002 box (constants `0x100dcb3c`/`0x100dcaf8`). There is
    // NO call to a looser `FPointsAreNear` anywhere in the function. So the binary uses 0.002 for the
    // neighbours too, contradicting the current default's NEAR (0.015) (introduced by the Wanchai
    // Brush754 seam-gap round `bspmergecoplanars-8-case-merge-gap-live-traced`, which very likely
    // patched a POOLING mismatch symptom in the merge threshold instead — see the findings ledger).
    // Gated to measure 0.002-for-neighbours across the corpus before touching the default.
    let neigh = |p: &Vec3, q: &Vec3| {
        if std::env::var("UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME").is_ok() {
            points_are_same(p, q)
        } else {
            points_are_near(p, q)
        }
    };
    let (tf1, tf2) = (wrap(start1 + 1, nv1), wrap(start2 - 1, nv2));
    if neigh(&a.verts[tf1 as usize], &b.verts[tf2 as usize]) {
        end1 = tf1;
        start2 = tf2;
    } else {
        let (tb1, tb2) = (wrap(start1 - 1, nv1), wrap(start2 + 1, nv2));
        if neigh(&a.verts[tb1 as usize], &b.verts[tb2 as usize]) {
            start1 = tb1;
            end2 = tb2;
        } else {
            return None;
        }
    }
    let _ = start1; // (only End1/End2/Start2 feed the build below; kept for parity with the decode)
    let _ = start2;
    // 4. Splice: all of `a` from End1, then `b`'s non-shared verts from End2+1.
    let mut ring: Vec<Vec3> = Vec::with_capacity((nv1 + nv2) as usize);
    let mut v = end1;
    for _ in 0..nv1 {
        ring.push(a.verts[v as usize]);
        v = wrap(v + 1, nv1);
    }
    let mut v = end2;
    for _ in 0..(nv2 - 2) {
        v = wrap(v + 1, nv2);
        ring.push(b.verts[v as usize]);
    }
    // 5. RemoveColinears + post-thresholds.
    let mut out = a.clone();
    out.verts = ring;
    if out.remove_colinears() >= 3 && out.verts.len() <= 16 {
        Some(out)
    } else {
        None
    }
}

/// `bspBuild` (`0x35ef0`) restricted to the from-scratch repartition path: build a node tree from
/// the (merged) FPoly list, sharing one surf per source surf identity.
fn bsp_build(model: &mut Model, polys: Vec<FPoly>) -> Result<(), BuildError> {
    // Re-seed iLink so each distinct source surf identity gets ONE surf (bspAddNode sharing).
    let mut ready: Vec<FPoly> = polys
        .into_iter()
        .filter_map(|mut p| p.finalize().ok().map(|_| p))
        .collect();
    // Map source surf id -> new surf idx (allocate lazily via alloc_surf during add).
    // We reproduce surf sharing by giving all fragments of one source surf the same iLink.
    let mut by_surf: Vec<(i32, i32)> = Vec::new();
    for p in ready.iter_mut() {
        let key = p.i_link;
        let existing = by_surf.iter().find(|(k, _)| *k == key).map(|(_, s)| *s);
        let i_surf = match existing {
            Some(s) => s,
            None => {
                let s = alloc_surf(model, p);
                by_surf.push((key, s));
                s
            }
        };
        p.i_link = i_surf;
    }
    // Retain the soup the editor keeps in `Model.Polys` (each poly's `i_link` now its surf index).
    // bspBuild marks every processed poly `PF_EdProcessed` (0x40000000) and that bit ends up in the
    // saved `Model.Polys`; OR it onto the SOUP CLONE only — the polys fed to the partitioner below
    // must keep their real flags (PF_Portal etc. drive `find_best_split`'s scoring).
    let mut soup = ready.clone();
    for p in soup.iter_mut() {
        p.poly_flags |= PF_ED_PROCESSED;
    }
    model.polys = soup;
    // Repartition: the byte-verified 12/0/GOOD engine params.
    split_poly_list(model, -1, NODE_ROOT, ready, 0, BALANCE, PORTAL_BIAS, Opt::Good, &mut 0, None)
}

// --- driver: bspBrushCSG ---------------------------------------------------------------------

/// `bspValidateBrush` link phase (`Editor.dll 0x37290`, decoded 2026-07-19 —
/// board item `92-stage-2-done`): assign each brush poly a surf-link `iLink` so that COPLANAR,
/// same-facing faces of ONE brush share a single `FBspSurf`.  UnrealEd runs this when a brush is
/// built/loaded; native's T3D re-ingest never did, so a brush with several coplanar same-plane faces
/// (e.g. the tessellated dome cap — 9 authored `(0,0,1)` facets) gave each facet its OWN surf, which
/// `bspMergeCoplanars` (grouped by `iLink`) can then never fuse.  The editor shares one surf across
/// them, so its cap is ONE surf (2 CSG fragments) where native kept 9 (`Brush755`, §92 §9 pin).
///
/// Decoded loop (instruction-exact): `for i: Polys[i].iLink=i; then for i where iLink==i, for j>i
/// where Polys[j].iLink==j: link j→i` iff ALL hold —
///   * same Texture object (`[+0x1b8]`),
///   * EXACT `TextureU`/`TextureV` equality (6 `ucomiss`, `[+0x18..0x2c]`),
///   * same `PolyFlags` (`[+0x1b0]`),
///   * `Normal_i · Normal_j > 0.9999` (const `0x100dcb30`),
///   * coplanar band `-0.001 < Normal_i · (Base_j − Base_i) < 0.001` (consts `0x100dcb48`/`0x100dcb20`).
/// Runs in brush-LOCAL space (the editor's `Brush->Polys`, pre-transform); coplanarity + same-normal
/// are rigid-transform invariant so the link set matches the editor's local-space link even though
/// LOOP-1 later transforms the polys.  Returns the per-poly link array (`links[i] <= i`), indexed in
/// `polys` space — the caller remaps into `temp` space after LOOP-1 compaction (see the call site).
/// Castle-SAFE: no castle brush has two coplanar same-normal faces, so every `links[i] == i` there
/// (byte-identity gate confirms).
///
/// The normal used is the FINALIZED (winding-derived) one, NOT the authored `FPoly::Normal`: some
/// T3D faces carry a STALE/projected authored normal (the sloped-roof case handled in LOOP 1), and
/// deciding coplanarity on it would link/unlink on a plane the rest of the build treats as wrong.
/// The BASE, by contrast, IS the authored `FPoly::Base` (T3D `Origin=`) — corrected 2026-09-01
/// (OceanLab Lab finding, see the call site) after a `verts[0]`-based base missed 3 real merges per
/// brush on 9 real T3D-authored brushes whose own vertices carry a few thousandths of a unit of
/// construction noise; the authored Origin sits exactly on the intended plane and reproduces the
/// editor's grouping exactly. The exact-axis gate is kept faithful to the decode: on `Brush755`'s
/// dome cap the 9 `(0,0,1)` facets carry IDENTICAL `TextureU`/`TextureV`, so it passes and they link.
fn bsp_validate_brush_links(polys: &[FPoly]) -> Vec<i32> {
    let n = polys.len();
    // Finalized normal + on-plane base per face, in brush-LOCAL space (the editor's link-time
    // geometry).  Fall back to the authored normal only for a degenerate winding.  The base is
    // the poly's own `FPoly::Base` (T3D `Origin=`), NOT `verts[0]` — live-verified 2026-09-01
    // (OceanLab Lab's 9 "2D Loft" PF_Semisolid detail brushes, `native-materialize-findings.md`
    // "OceanLab Lab +27 surf over-build"): a `verts[0]`-based coplanarity check missed 3 real
    // merges per brush (native 21 groups vs the live editor's isolated-golden 18) because these
    // T3D-authored faces carry a few thousandths of a unit of construction noise between their
    // OWN vertices, large enough (~0.0015-0.004) to push the `verts[0]` pair outside the ±0.001
    // coplanar band on some pairs but not others of the SAME flat cap/ring — while every poly's
    // own authored `Origin` sits exactly on its intended plane (0 delta), reproducing the
    // editor's grouping exactly on all 9 affected brushes with zero change on the other 101
    // same-poly-count brushes in the level.  `p.base` already carries the real authored Origin
    // when the brush has one (`brush_marshal.py`'s `origins_flat`, also what `bspAddNode` stores
    // as the surf `pBase`, §92 §45) and safely falls back to `verts[0]` otherwise (`FPoly::new`'s
    // default, `lib.rs`) — so this is a strict improvement, no new fallback gap.
    let mut nrm: Vec<Vec3> = Vec::with_capacity(n);
    let mut base: Vec<Vec3> = Vec::with_capacity(n);
    for p in polys {
        let mut w = p.clone();
        w.normal = Vec3::new(0.0, 0.0, 0.0);
        nrm.push(if w.calc_normal() { w.normal } else { p.normal });
        base.push(p.base);
    }
    let mut links: Vec<i32> = (0..n as i32).collect();
    for i in 0..n {
        if links[i] != i as i32 {
            continue;
        }
        for j in (i + 1)..n {
            if links[j] != j as i32 {
                continue;
            }
            if polys[i].texture != polys[j].texture {
                continue;
            }
            if polys[i].texture_u != polys[j].texture_u || polys[i].texture_v != polys[j].texture_v {
                continue;
            }
            if polys[i].poly_flags != polys[j].poly_flags {
                continue;
            }
            if nrm[i].dot(&nrm[j]) <= 0.9999 {
                continue;
            }
            let d = nrm[i].dot(&base[j].sub(&base[i]));
            if !(d > -0.001 && d < 0.001) {
                continue;
            }
            links[j] = i as i32;
        }
    }
    links
}

/// `bspBrushCSG` **LOOP 1** (`0x35791`) — transform the brush's polys into world space and adjust
/// their flags, producing the engine's `TempModel->Polys`.  Shared by every `CsgOper`: Add/Subtract
/// feed it to LOOP 2, Intersect/Deintersect feed it to the tail at `0x35ab3` (`intersect_brushset`).
///
/// The flag adjust is `Ed.PolyFlags = (Ed.PolyFlags | argPolyFlags) & ~NotPolyFlags` with
/// `NotPolyFlags = (CsgOper == Add) ? 0 : 0x28` — so for Intersect/Deintersect (as for Subtract) the
/// builder's OWN faces come out with `PF_NotSolid|PF_Semisolid` STRIPPED, and any semisolid/nonsolid
/// face in the result can only have arrived via Phase 2 (a world cap).  This is the §3 flag rule,
/// owned here by the merge and never re-derived downstream.
fn brush_loop1(brush: &build::BrushInput, actor_index: i32, poly_flags: u32) -> Vec<FPoly> {
    let oper = brush.oper;
    let not_poly_flags: u32 = if oper == csg::CsgOper::Add { 0 } else { 0x28 };

    // `bspValidateBrush` coplanar-link phase (Editor.dll 0x37290): pre-compute per-poly surf links so
    // coplanar same-facing faces of THIS brush share one surf (the dome-cap fix, §92 §9 / spec).
    // `links` are in `brush.polys` space; LOOP 1 can DROP a degenerate face, so we remap them into
    // `temp` space AFTER the loop (`brush_to_temp`) — else a dropped face desyncs the indices LOOP 2
    // chases through `temp[i_link]`, mis-sharing a surf or panicking out of bounds (cold-review
    // finding, 2026-07-19).
    let links = bsp_validate_brush_links(&brush.polys);

    // LINK-GROUP DUMP (UEDCLI_BSPCSG_LINK_DUMP=<actor_index>|ALL) — env-gated, read-only diagnostic,
    // zero effect on the default path. Prints the per-brush `bsp_validate_brush_links` group count and,
    // for each poly, its resolved root link index + base/normal, so a surf-count residual can be
    // attributed to a specific merge/non-merge pair without re-deriving the algorithm in Python (a
    // pure-Python reimplementation risks not matching `FPoly::calc_normal`'s exact behavior on a large
    // many-vertex poly set — this dumps the REAL Rust-computed groups instead).
    if let Ok(want) = std::env::var("UEDCLI_BSPCSG_LINK_DUMP") {
        let matches = want == "ALL" || want.parse::<i32>().ok() == Some(actor_index);
        if matches {
            let groups: std::collections::BTreeSet<i32> = links.iter().copied().collect();
            eprintln!("LINK_DUMP actor={} n_polys={} n_groups={}", actor_index, brush.polys.len(), groups.len());
            for (i, p) in brush.polys.iter().enumerate() {
                eprintln!(
                    "  poly[{i:3}] link={:3} base=({:.6},{:.6},{:.6}) v0=({:.6},{:.6},{:.6}) tex={:?} tu={:?} tv={:?} flags={}",
                    links[i], p.base.x, p.base.y, p.base.z,
                    p.verts.first().map(|v| v.x).unwrap_or(0.0),
                    p.verts.first().map(|v| v.y).unwrap_or(0.0),
                    p.verts.first().map(|v| v.z).unwrap_or(0.0),
                    p.texture, p.texture_u, p.texture_v, p.poly_flags,
                );
                let mut w = p.clone();
                w.normal = Vec3::new(0.0, 0.0, 0.0);
                let fin = if w.calc_normal() { w.normal } else { p.normal };
                eprintln!("           finalized_normal=({:.6},{:.6},{:.6})", fin.x, fin.y, fin.z);
            }
        }
    }

    let mut brush_to_temp = vec![-1i32; brush.polys.len()];

    // LOOP 1: transform brush polys into a temp poly list.
    let mut temp: Vec<FPoly> = Vec::new();
    for (i, p) in brush.polys.iter().enumerate() {
        let mut ed = p.clone();
        // THE EDITOR'S NORMAL PIPELINE, UNIFORM FOR EVERY BRUSH POLY (2026-09-03, Vandenberg
        // first-divergent-brush round; spike `2026-09-03-vandenberg-first-divergent-brush/`):
        //   1. The T3D importer STORES `CalcNormal(local winding)` over the authored normal —
        //      live golden bytes: Vandenberg Brush41's stored Polys normal is `bf75341a/3e931f43`
        //      (= CalcNormal) while the authored text parses to `bf753416/3e931f47`.
        //   2. `FPoly::Transform` (Engine.dll 0x152360) maps that stored normal by VectorXform and
        //      applies `SafeNormalSlow` UNCONDITIONALLY, on every poly (§92 §52).
        // So the world face normal is `SafeNormalSlow(X · CalcNormal(local))`, with X = the
        // `ABrush::BuildCoords` VectorXform (scaled/mirrored brushes — `brush.vec_xform`) or the
        // plain rotation (unscaled — `brush.rot`).  This replaces the former three-way split
        // (authored-kept Add / §48 Subtract-only recompute / dot<0.9999 disagree-guard): §48's
        // "Add keeps authored" castle evidence was coincidental — the castle's authored T3D
        // values ARE `SNS(CalcNormal(local))` for its faces (its T3D was itself an editor export
        // of import-recomputed normals), so the uniform rule reproduces them bit-for-bit.  Axis
        // faces are byte-stable too: `CalcNormal` of a large axis rect is `0.99999994·axis`, and
        // `SafeNormalSlow` lands that back on the exact `±1.0` the editor stores.  Validated
        // offline against the live per-brush Pass-1 gdb capture of the full Vandenberg build
        // (`vdb_model_check.py`: every explained plane-bit diff matches this rule).
        let local_normal: Vec3 = {
            let mut w = p.clone();
            w.normal = Vec3::new(0.0, 0.0, 0.0);
            if w.calc_normal() {
                w.normal
            } else {
                p.normal
            }
        };
        ed.poly_flags = (ed.poly_flags | poly_flags) & !not_poly_flags;
        ed.actor = actor_index;
        ed.i_brush_poly = i as i32;
        if ed
            .transform(&brush.rot, &brush.prepivot, &brush.location)
            .is_err()
        {
            continue;
        }
        if brush.orientation < 0 {
            // Mirrored brush: `FPoly::Transform`'s Orientation<0 post-map ring reversal (verts
            // only, no normal negation — spike 2026-06-25) — see `BrushInput::orientation`.
            ed.verts.reverse();
        }
        if ed.finalize().is_err() {
            continue;
        }
        // `SafeNormalSlow(X · CalcNormal(local))` — see the pipeline comment above.  For an axis
        // face this lands the EXACT unit axis; for a scaled brush it is the covariant editor value
        // `calc_normal(world)` misses (§92 §43).  A degenerate mapped image (|N|² < 1e-8) keeps the
        // `finalize`/transform normal.  For a MIRRORED brush `local_normal` was computed on the
        // UNREVERSED ring (above, before the Orientation reversal), exactly as the editor's
        // stored-poly normal is — and VectorXform (det < 0) maps it to the outward world normal.
        let x: &[[f32; 3]; 3] = brush.vec_xform.as_ref().unwrap_or(&brush.rot);
        if let Some(n) = safe_normal_slow(&transform_vector_by(&local_normal, x)) {
            ed.normal = n;
        }
        // Texture axes map by the SAME VectorXform as the normal: the editor's `FPoly::Transform`
        // maps Normal AND TextureU/V by the single `Uncoords.VectorXform = (L⁻¹)ᵀ` (no SafeNormalSlow
        // — the axis magnitude carries texel scale).  `ed.transform` above applied the forward `L`
        // (= `brush.rot`) to the LOCAL axes; overwrite with `x·local` from the un-transformed `p`.
        // For an unscaled brush `x == brush.rot` so this reproduces `transform`'s bits exactly.  The
        // former path pre-multiplied the axes by `(LᵀL)⁻¹` (Python f32) then let `transform` apply
        // forward `L` (f32) — two f32 steps that rounded 1 ULP below the editor's single division
        // (WanChai Vectors[8] = f32(-1/112) = bc124925, not bc124924).
        ed.texture_u = transform_vector_by(&p.texture_u, x);
        ed.texture_v = transform_vector_by(&p.texture_v, x);
        // §8.2: NO LOOP-1 reverse.  `ABrush::BuildCoords` returns Orientation +1 for identity scale
        // regardless of Add/Subtract, so the descent uses the OUTWARD brush normal; the single flip
        // for a subtract is applied at STORE time inside `SubtractBrushFromWorldFunc` (leaf_func).
        // base-snap onto plane: Base += Normal*(Normal·(Vertex[0]-Base)) if |d|>1e-4
        let d = ed.normal.dot(&ed.verts[0].sub(&ed.base));
        if d.abs() > 1.0e-4 {
            ed.base = Vec3::new(
                ed.base.x + ed.normal.x * d,
                ed.base.y + ed.normal.y * d,
                ed.base.z + ed.normal.z * d,
            );
        }
        brush_to_temp[i] = temp.len() as i32;
        temp.push(ed);
    }

    // Remap the `bspValidateBrush` surf-links into temp space (post-compaction, see above): each
    // surviving face points its `i_link` at its representative's TEMP slot (`links[i] <= i`, so the
    // representative — if it survived — sits at an EARLIER temp slot, which LOOP 2 has already seeded
    // to a real surf index by the time this face is reached).  A face whose representative was itself
    // dropped falls back to self-seeding.  Authored (non -1) links are left untouched.
    for (i, &t) in brush_to_temp.iter().enumerate() {
        if t < 0 || temp[t as usize].i_link != -1 {
            continue;
        }
        let rep_temp = brush_to_temp[links[i] as usize];
        temp[t as usize].i_link = if rep_temp >= 0 { rep_temp } else { t };
    }
    temp
}

fn bsp_brush_csg(model: &mut Model, brush: &build::BrushInput, actor_index: i32, poly_flags: u32) {
    // Incremental CSG dedups points via the editor's radius-pruned FindNearestVertex (over the live
    // world tree), not the linear pool scan. Restored on scope exit so repartition uses the scan.
    let _fnv = FnvDedupGuard::enable();
    let oper = brush.oper;
    if oper == csg::CsgOper::Intersect || oper == csg::CsgOper::Deintersect {
        // Intersect/Deintersect never reach MAP REBUILD — they are the `BRUSH FROM INTERSECTION`/
        // `DEINTERSECTION` exec commands, whose tail (`0x35ab3`) lives in `intersect_brushset`.
        // `csgRebuild`'s own dispatch (`0x100359d3`-`0x100359df`) branches away to that tail on a
        // LITERAL `CsgOper==3||4` test — `Active` (0) does not match, so it falls through into the
        // shared Add/Subtract body below, same as the real editor.
        return;
    }
    let mut temp = brush_loop1(brush, actor_index, poly_flags);
    let mut sink: Vec<FPoly> = Vec::new(); // unused by the Add/Subtract (node-growing) leaves

    // LOOP 2: filter each temp poly through the world, growing nodes.
    let func = if oper == csg::CsgOper::Add {
        LeafFunc::Add
    } else {
        LeafFunc::Subtract
    };
    // §92 §32 CONVEX SEED (leading CSG_Add into the empty world ONLY): the editor does NOT
    // filter-classify the first brush's faces — it SEEDS them into the empty world as world-tree
    // ROOT NODES, a `bspAddNode(NODE_ROOT)` then a `NODE_FRONT` chain in brush-poly order (editor
    // oracle §26/§30/§32 block 0: `places=311111`, parents 0,1,2,3,4). Native's per-poly filter kept
    // only 1 of a leading Add's 6 faces (§31/§32): face 0 seeds a 1-node NF_IsNew tree, is_csg treats
    // it non-CSG, so faces 1-5 never flip `outside` and reach an F_INSIDE leaf → the Add func drops
    // them. Seeding the whole convex brush as a front chain — keeping `root_outside=false` (NO §25
    // void-polarity flip) — retains all 6 faces as structural splitters while the exterior stays
    // solid, so later Subtracts still carve. Applied to a leading ADD only; a leading SUBTRACT keeps
    // the existing per-poly filter path (already byte-exact for the castle's `World_7e9y81`, §32 gate).
    //
    // CONVEXITY ASSUMPTION: the linear NODE_FRONT chain (each face on the FRONT of the previous) is a
    // valid seed BSP ONLY for a CONVEX first Add — it reproduces the editor's convex-brush world seed
    // exactly (verified node-for-node vs `oracle-105.log` block 0). Every real level's first world
    // brush IS a convex box; a NON-convex first Add would need a real recursive `bsp_build`/
    // SplitPolyList (front/back branching), not this chain, and is NOT handled here. Also UNTESTED:
    // a leading semisolid/nonsolid Add (`poly_flags & 0x28`) — no real level opens with one (a detail
    // brush is never first), so the interaction with the Pass-2 detail layer is unexercised. No guard
    // is added (all shipped first brushes are convex structural); this comment is the contract.
    //
    // ⚠️ CONVEXITY IS NOT THE ONLY PRECONDITION — the seed also assumes the first Add IS THE WORLD
    // SHELL. It stores every face `Reverse()`d (inward-facing), which declares the brush's INTERIOR
    // to be the region the level is carved out of and everything beyond it solid. That is right for
    // the enclosing box a real map opens with, and WRONG for a leading Add that is a small solid
    // sitting inside what a later Subtract turns into void: the seeded faces survive as structural
    // splitters, so the solid never gets carved away.
    //
    // MEASURED against the live editor 2026-07-25 (a CONVEX 64x64x256 pillar followed by a
    // 256x256x192 subtract): UnrealEd filter-classifies the leading Add normally, the later subtract
    // cuts its faces away, and the region reads as plain void (6 result polys). Native keeps the
    // pillar (22). Golden: `uedcli/tests/fixtures/intersect/h_leading_additive_deintersect.t3d`.
    //
    // `brush deintersect` no longer trips this — `brushcsg.build_scaffolding` prepends a distant
    // seed-subtract so the user's first brush never meets an empty tree — but `level materialize` and
    // any other caller still can. Tracked in `dev/docs/board/inbox/` (`first_add_seed`, p3). Fixing
    // it properly means classifying a leading Add the way the editor does WITHOUT regressing the
    // world-shell case the seed was introduced for (§92 §32/§33), not simply deleting the shortcut.
    let first_add_seed = model.nodes.is_empty() && oper == csg::CsgOper::Add;
    let n_temp = temp.len();
    let mut prev_seed_node: i32 = -1;
    for i in 0..n_temp {
        let mut ed2 = temp[i].clone();
        ed2.poly_flags &= 0x7fff_ffff;
        if ed2.i_link == i as i32 {
            let seed = model.surfs.len() as i32;
            temp[i].i_link = seed;
            ed2.i_link = seed;
        } else {
            ed2.i_link = temp[ed2.i_link as usize].i_link;
        }
        if first_add_seed {
            // ROOT for the first face, then a NODE_FRONT chain hung off the previous seed node —
            // the exact parent/place the editor's world-seed emits (block 0). Use the RETURNED node
            // index as the next parent (not `i-1`) so a >16-vert face that `bsp_add_node` storage-
            // splits still chains correctly.
            let (parent, place) = if prev_seed_node < 0 {
                (-1, NODE_ROOT)
            } else {
                (prev_seed_node, NODE_FRONT)
            };
            // The editor stores the leading-Add seed faces INWARD-facing (`Reverse`d): oracle §26
            // block 0 gives the bar's top face (z=416) normal (0,0,-1), i.e. into the solid — every
            // seed plane is the reverse of native's outward temp normal. Reverse each poly (winding +
            // normal, base preserved) so the stored plane orientation matches the editor node-for-node
            // (verified vs `oracle-105.log` block 0: bases/parents/places/ilinks already matched; this
            // aligns the normals). The descent's Outside-propagation then flips correctly at these
            // planes for the following brushes.
            let mut seed = ed2.clone();
            seed.reverse();
            let r = bsp_add_node(model, parent, place, NF_IS_NEW, &seed);
            trace_node_add(model, "SEED", parent, place, NF_IS_NEW, &seed, r);
            prev_seed_node = r;
        } else {
            bsp_filter_fpoly(model, func, &ed2, &mut sink);
        }
    }

    // Cut the world with the brush (skip for non-solid/semisolid brushes): build the brush's convex
    // temp BSP, then filter every existing world face down it (split-and-re-add, §8.1).
    //
    // ACTIVE never cuts the world (2026-09-03 re-disassembly): inside `FilterWorldThroughBrush`
    // (`0x33250`) the per-world-node filter body is gated on LITERAL `CsgOper==1||==2`
    // (`0x100333dd cmp ecx,1; je body; cmp ecx,2; je body`, `==3`/`==4` divert to the intersect
    // funcs, anything else — ordinal 0 included — falls to the recursion tail at `0x10033503`), so
    // for `Active` the editor walks the world tree doing NOTHING.  The 0x33472 cmove (Subtract func
    // unless `==1`) sits INSIDE that gated body and is unreachable for `Active` — round 2's
    // "Active takes the Subtract world-cut" reading decoded the cmove but missed the gate.
    // Skipping the call is outcome-equivalent to the editor's empty walk.
    if oper != csg::CsgOper::Active && !model.nodes.is_empty() && (poly_flags & 0x28) == 0 {
        if let Ok(brush_temp) = build_brush_temp_bsp(&temp) {
            filter_world_through_brush(
                model,
                &brush_temp,
                // World-thru-brush leaf func select (`Editor.dll 0x33472`-`0x1003347f`):
                // `eax=SubtractFunc(0x34980); cmp CsgOper,1; cmove eax,AddFunc(0x31b90)` — only
                // ever reached with `CsgOper==1||2` (gate above), so this is a plain Add/Subtract
                // choice.
                oper != csg::CsgOper::Add,
                None,
                &mut sink,
            );
        }
    }

    // bspBrushCSG TAIL (Editor.dll `0x35dcd`-`0x35dd5`): `bspCleanup` runs only for a LITERAL
    // `CsgOper==1||==2` (`cmp edx,1; je body; cmp edx,2; jne skip` — the `==2` compare round 2
    // misattributed to the NumZones reset at `0x356a2`, a separate site).  This does double duty —
    // it recursively clears NF_IsNew (so the NEXT brush sees these faces as CSG-solid) AND splices
    // the FWTB-DEAD (`nv==0`) nodes out of the tree, so the next brush filters through a CLEANED
    // tree that descends ALIVE coplanar anchors, not dead chain-heads.  Doing this per-brush (not
    // once at the end) is what makes native's incremental world tree match the editor's
    // node-for-node: a dead chain-head left in place flips a splitter's orientation and reverses
    // fragment emit order (§10.8 node-4 + the RoofNE #184 swap).  (csgRebuild passes
    // bBuildBounds=0, so bspBuildBounds is skipped; the per-brush bspMergeCoplanars it also runs
    // with bMergePolys=1 operates on Model->Polys, which native rebuilds from the nodes at
    // repartition — so it does not affect node-tree parity.)
    //
    // An ACTIVE brush therefore leaves ALL its new nodes flagged NF_IsNew until the next
    // Add/Subtract brush's cleanup clears them.  While flagged, they (a) do not flip `Outside` in
    // the next brush's descent (`FBspNode::IsCsg` masks NF_IsNew — `is_csg_filter`), so that
    // brush's polys classify against the PRE-Active world solidity, and (b) shield themselves and
    // their whole subtree from that brush's world cut (`FilterWorldThroughBrush` returns on
    // NF_IsNew, `0x100332d4`).  This is the live-confirmed 16/12/6-vs-14/11/2 Paris Underground
    // 2-brush outcome gap (spike `2026-09-03-built-parity-worst-tier`).
    if oper == csg::CsgOper::Add || oper == csg::CsgOper::Subtract {
        bsp_cleanup(model);
    }
    // The Add/Subtract leaves are node-GROWING, never collecting: nothing may have landed in the
    // sink. Pinned so a future `LeafFunc::Collect` use here cannot silently accumulate into a
    // vector no one reads.
    debug_assert!(sink.is_empty(), "Add/Subtract leaves must not collect faces");

    // Round 14 REMOVED round 13's per-brush `bsp_refresh_points_vectors` call that lived here: the
    // live interleaved trace (`combined_refresh_addpoint_trace.py`) proved `bspRefresh` fires ZERO
    // times during brush CSG — all its calls belong to the rebuild phase (`bspBuild` pre/post +
    // `bspRepartition` tails, see `build_geometry_bspcsg`). A GC here misclassifies ring-only points
    // (not yet node-linked) as unreachable — round 13's measured UNATCO crash + `DX.dx` regression.
}

/// The rebuild-phase PRE-repartition `bspRefresh` (`bspBuild @0x35ef0`, `arg_2==0` path): the editor
/// first zeroes EVERY node's `NumVertices` (the `[node+0x36]=0` loop right before the call), then
/// calls `bspRefresh(model, NoRemapSurfs=1)` — so its point-marking loop (`bspRefresh @0x36cd0`:
/// `p_base` of every surf + every node's ring verts) sees NO rings at all, and `NoRemapSurfs=1`
/// keeps every surf.  Net effect on Points: keep ONLY `p_base`-referenced points, order-preserving —
/// exactly round 9's live 44 -> 19 = bases-only observation (golden `Points[0..18]`), and why the
/// final layout is bases-first: rings are dropped here and freshly re-appended by the rebuild's own
/// `bspAddPoint` calls.  At native's matching seam everything except `model.points` is cleared right
/// after, so only the kept-points set/order matters.
fn compact_points_to_surf_bases(model: &mut Model) {
    let mut pt_used = vec![false; model.points.len()];
    for s in &model.surfs {
        if s.p_base >= 0 {
            pt_used[s.p_base as usize] = true;
        }
    }
    let mut kept = Vec::with_capacity(model.points.len());
    for (i, &u) in pt_used.iter().enumerate() {
        if u {
            kept.push(model.points[i]);
        }
    }
    model.points = kept;
}

// --- finalize (leaves/zones/bounds), mirroring build.rs::finalize_leaves_and_bbox ------------

/// Swap every node's `iFront`/`iBack` — native's CSG-side child convention vs the engine's.
fn swap_node_children(model: &mut Model) {
    for n in model.nodes.iter_mut() {
        std::mem::swap(&mut n.i_front, &mut n.i_back);
    }
}

/// `TestVisibility` (`Editor.dll 0xaa940`, engine vtable `+0x264`): leaves, portals, the zone flood
/// and Pass D's per-zone fragment split.  Reads/writes the ENGINE child convention — bracket it with
/// `swap_node_children` when the tree is in native's.
fn zone_pass(model: &mut Model) {
    let passd_tail = zones::assign_leaves_and_zones(model);
    for n in model.nodes.iter_mut() {
        n.node_flags &= !build::NF_SOLID_BOUND;
    }
    // Node-emit-ORDER parity: relabel the array so Pass-D split fragments cluster at the tail in the
    // editor's emission order (§82 §10.17).  Pure permutation — remaps child/chain links only, leaves
    // the tree isomorphic — so collision/zones/render are byte-unchanged; only the on-disk node ORDER
    // (and thus `Bounds`/`LeafHulls`, built after) moves to match `Test_Castle.dx` positionally.
    reorder_nodes_to_tail(model, &passd_tail);
}

fn finalize(model: &mut Model) {
    swap_node_children(model);
    for n in model.nodes.iter_mut() {
        n.node_flags &= !NF_IS_NEW;
        n.i_render_bound = -1;
    }
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

/// Relabel the node array so the given `tail` node indices move to the END, in the given order,
/// with all other nodes keeping their relative order.  A PURE, tree-preserving permutation: it
/// clones the nodes into the new order and remaps every `i_front`/`i_back`/`i_plane` link through
/// the old→new map, so the BSP tree is unchanged (isomorphic) — collision, zones, leaves, surfs and
/// render all read the identical tree, only the on-disk node ORDER changes.  This reproduces
/// UnrealEd's node-array layout, where `TestVisibility`/`AssignAllZones` appends every zone-split
/// fragment (originals included) at the tail of `Model->Nodes` (§82 §10.17).  Nothing outside the
/// node array references a node by index at this stage (leaves/surfs carry no node ref; `Bounds`/
/// `LeafHulls` are built AFTER this, against the relabelled tree), so the relabel is total and safe.
fn reorder_nodes_to_tail(model: &mut Model, tail: &[usize]) {
    let n = model.nodes.len();
    if tail.is_empty() || n == 0 {
        return;
    }
    // Dedup while preserving first-occurrence order; never move the root (node 0 must stay at 0).
    // Node 0 is a top-level FindBestSplit partition, never a Pass-D zone-split boundary face, so it
    // is not expected in `tail`; the `t != 0` guard below keeps it fail-safe (a stray 0 would only
    // cost byte-parity on that one group, never tree validity).
    debug_assert!(!tail.contains(&0), "root node 0 must not be a Pass-D split owner");
    let mut in_tail = vec![false; n];
    let mut tail_seq: Vec<usize> = Vec::with_capacity(tail.len());
    for &t in tail {
        if t != 0 && t < n && !in_tail[t] {
            in_tail[t] = true;
            tail_seq.push(t);
        }
    }
    if tail_seq.is_empty() {
        return;
    }
    // new_order[new_pos] = old_idx : base nodes (current order, not in tail) then the tail sequence.
    let mut new_order: Vec<usize> = Vec::with_capacity(n);
    for i in 0..n {
        if !in_tail[i] {
            new_order.push(i);
        }
    }
    new_order.extend_from_slice(&tail_seq);
    debug_assert_eq!(new_order.len(), n);
    // old -> new position.
    let mut old2new = vec![-1i32; n];
    for (new_pos, &old) in new_order.iter().enumerate() {
        old2new[old] = new_pos as i32;
    }
    let remap = |i: i32| -> i32 {
        if i < 0 {
            i
        } else {
            old2new[i as usize]
        }
    };
    let mut new_nodes: Vec<crate::model::BspNode> = Vec::with_capacity(n);
    for &old in &new_order {
        let mut nd = model.nodes[old].clone();
        nd.i_front = remap(nd.i_front);
        nd.i_back = remap(nd.i_back);
        nd.i_plane = remap(nd.i_plane);
        new_nodes.push(nd);
    }
    model.nodes = new_nodes;
}

// --- public entry point ----------------------------------------------------------------------

/// The NEW incremental pipeline (§7 port order): EmptyModel; structural brushes via `bspBrushCSG`;
/// `bspRepartition`; semisolid second layer; finalize; bounds.  Parallel to and independent of the
/// default `build::build_geometry_from_brushes`.
pub fn build_geometry_bspcsg(brushes: &[build::BrushInput]) -> Result<Model, BuildError> {
    let mut model = Model::default();
    model.root_outside = false; // DX level: solid world, Subtract carves.

    // A detail brush (2nd incremental layer, not repartitioned) is a SEMISOLID one: semisolid has a
    // real partial-carve effect (a distinct `leaf_func` classification table, spec.md line 445) that
    // stays deferred pending direct evidence either way.  A NotSolid-WITHOUT-Semisolid brush — portal
    // or not — carves nothing (`derive_nf` sets NF_NotCsg for NotSolid) and is a valid FindBestSplit
    // candidate the real editor processes in the FIRST incremental `bspBrushCSG` phase, BEFORE
    // `bspBuildFPolys`/repartition (`FindBestSplit` skips a `0x28` candidate only when it is
    // `!PF_Portal`, `bspcsg.rs:1178` / §82 §4 — the split-scoring exception already assumed a NotSolid
    // splitter can reach the soup at all).  §92 §54 first proved this for PORTAL brushes only
    // (Brush344/UNATCO: editor 1639 vs native 1637 committed nodes at N=106).  A live N=112 UNATCO
    // oracle capture generalizes it: `Brush416` (world-csg idx 111, `PF_NotSolid|PF_TwoSided|0x4` —
    // an ordinary glass/window pane, NOT Portal, NOT Semisolid) contributes exactly 2 pre-repartition
    // committed nodes in the real editor (1766 vs native's pre-fix 1764) — the same "+2 non-CSG
    // splitter" signature as a portal.  So the true rule is NotSolid (regardless of Portal), not
    // NotSolid&&Portal.  Castle-safe by construction: the castle has 0 detail brushes at all, so
    // `detail_pass` is a no-op there either way.
    let detail_pass = |_b: &build::BrushInput, pf: u32| pf & csg::PF_SEMISOLID != 0;

    // Resolve the per-brush effective poly_flags (Portal force: NotSolid, Semisolid cleared).
    let eff_flags = |b: &build::BrushInput| -> u32 {
        let mut pf = b.poly_flags;
        if pf & csg::PF_PORTAL != 0 {
            pf = (pf & !csg::PF_SEMISOLID) | csg::PF_NOTSOLID;
        }
        pf
    };

    // Reject scaled brushes (parity with default path).
    for (bi, b) in brushes.iter().enumerate() {
        if (b.scale.x - 1.0).abs() > 1e-6
            || (b.scale.y - 1.0).abs() > 1e-6
            || (b.scale.z - 1.0).abs() > 1e-6
        {
            return Err(BuildError(format!(
                "brush {} has non-identity Scale {:?} — scaled brushes are not yet supported",
                bi,
                (b.scale.x, b.scale.y, b.scale.z)
            )));
        }
    }

    // Pass 1: STRUCTURAL brushes (incremental) — now INCLUDING any NotSolid non-semisolid brush,
    // portal or not (see `detail_pass`).
    //
    // PER-BRUSH STATE DUMP (UEDCLI_BSPCSG_BRUSH_STATE) — env-gated, read-only diagnostic for the
    // live per-brush Pass-1 tree-shape trace (pairs with the editor-side `pass1_brush_trace_*.py`
    // gdb capture breaking at `bspBrushCSG` entry `0x100355e0`).  `COUNTS` emits one `BRUSHSTATE`
    // line after every Pass-1 CSG add (k = 0-based structural-call index, matching the editor's
    // k-th `bspBrushCSG` call; bi = world-CSG actor index); `FULL:<lo>-<hi>` additionally dumps
    // every node (plane float bits + linkage) after each brush with `lo <= k <= hi`.
    let brush_state = std::env::var("UEDCLI_BSPCSG_BRUSH_STATE").ok();
    let full_range: Option<(usize, usize)> = brush_state.as_deref().and_then(|v| {
        let r = v.strip_prefix("FULL:")?;
        let (lo, hi) = r.split_once('-')?;
        Some((lo.parse().ok()?, hi.parse().ok()?))
    });
    let mut k = 0usize;
    for (bi, b) in brushes.iter().enumerate() {
        let pf = eff_flags(b);
        if detail_pass(b, pf) {
            continue;
        }
        bsp_brush_csg(&mut model, b, bi as i32, pf);
        // bsp_brush_csg's tail already runs bsp_cleanup per Add/Subtract brush (mirrors bspBrushCSG
        // @0x35dcd), so the incremental tree here is already the editor's post-cleanup structure —
        // except right after an Active brush, whose nodes stay NF_IsNew (also editor-faithful).
        if brush_state.is_some() {
            eprintln!(
                "BRUSHSTATE k={} bi={} nodes={} surfs={} verts={} points={} vectors={}",
                k, bi, model.nodes.len(), model.surfs.len(), model.verts.len(),
                model.points.len(), model.vectors.len()
            );
            if let Some((lo, hi)) = full_range {
                if k >= lo && k <= hi {
                    for (i, n) in model.nodes.iter().enumerate() {
                        eprintln!(
                            "P1NODE k={} i={} pb={:08x},{:08x},{:08x},{:08x} iF={} iB={} iP={} isurf={} nv={} nf={:#x}",
                            k, i, n.plane.x.to_bits(), n.plane.y.to_bits(),
                            n.plane.z.to_bits(), n.plane.w.to_bits(),
                            n.i_front, n.i_back, n.i_plane, n.i_surf, n.num_vertices, n.node_flags
                        );
                    }
                }
            }
        }
        k += 1;
    }

    // TREE-STRUCT DUMP (UEDCLI_BSPCSG_TREE_STRUCT) — env-gated; native counterpart of the editor's
    // `editor_struct.py` Model->Nodes dump (§10.8).  Emits every node's plane + iFront/iBack/iPlane +
    // surf + nv (pre-repartition) so `tree_struct_diff.py` can pin the first STRUCTURAL divergence
    // (node 4, brush 0 — a coplanar-chain-head difference the leaf-add compare cannot see).
    if std::env::var("UEDCLI_BSPCSG_TREE_STRUCT").is_ok() {
        for (i, n) in model.nodes.iter().enumerate() {
            eprintln!(
                "STRUCT node={} plane=({:.5},{:.5},{:.5},{:.5}) iF={} iB={} iP={} isurf={} nf={:#x} nv={} pbits={:#010x},{:#010x},{:#010x},{:#010x}",
                i, n.plane.x, n.plane.y, n.plane.z, n.plane.w,
                n.i_front, n.i_back, n.i_plane, n.i_surf, n.node_flags, n.num_vertices,
                n.plane.x.to_bits(), n.plane.y.to_bits(), n.plane.z.to_bits(), n.plane.w.to_bits()
            );
        }
    }

    // bspRepartition: rebuild the tree from the fat fragment soup.
    // Snapshot of the incremental-CSG surf order (see §10.19); used post-build to canonicalize the
    // final Surfs/Vectors pools.  Empty when the repartition is skipped (NOREPART) — then no reorder.
    let mut canon_surf_keys: Vec<(i32, i32)> = Vec::new();
    if std::env::var("UEDCLI_BSPCSG_NOREPART").is_err() {
        if std::env::var("UEDCLI_BSPCSG_POOLDUMP").is_ok() {
            let live_pts: std::collections::HashSet<i32> =
                model.nodes.iter().flat_map(|n| {
                    (0..n.num_vertices).map(move |k| n.i_vert_pool + k)
                }).map(|vi| model.verts[vi as usize].i_vertex).collect();
            eprintln!(
                "POOLDUMP preclear nodes={} surfs={} verts={} points={} vectors={} live_pts={}",
                model.nodes.len(), model.surfs.len(), model.verts.len(),
                model.points.len(), model.vectors.len(), live_pts.len()
            );
        }
        let fpolys = bsp_build_fpolys(&model);
        // PRE-MERGE FRAGMENT DUMP (UEDCLI_BSPCSG_PREMERGE_DUMP=<ilink>[,<ilink>...]|ALL) — env-gated,
        // forensic-only: the exact `bsp_build_fpolys` output for named surfs (or every fragment, with
        // `ALL`), BEFORE `bsp_merge_coplanars` groups/fuses anything. Lets a specific iLink's raw
        // fragment set, or the WHOLE pre-merge order, be compared against the editor's live-captured
        // equivalent (`fpolys_stage_order.py`'s PREMERGE dump,
        // `2026-08-29-unatco-repart-live-diff/harness/`).
        if let Ok(want) = std::env::var("UEDCLI_BSPCSG_PREMERGE_DUMP") {
            let all = want.trim() == "ALL";
            let wanted: std::collections::HashSet<i32> =
                want.split(',').filter_map(|s| s.trim().parse().ok()).collect();
            for (i, p) in fpolys.iter().enumerate() {
                if !all && !wanted.contains(&p.i_link) {
                    continue;
                }
                eprintln!(
                    "PREMERGE idx={} ilink={} nv={} flags={:#x} N={:.6},{:.6},{:.6} B={:.6},{:.6},{:.6} TU={:.6},{:.6},{:.6} TV={:.6},{:.6},{:.6}",
                    i, p.i_link, p.verts.len(), p.poly_flags,
                    p.normal.x, p.normal.y, p.normal.z,
                    p.base.x, p.base.y, p.base.z,
                    p.texture_u.x, p.texture_u.y, p.texture_u.z,
                    p.texture_v.x, p.texture_v.y, p.texture_v.z,
                );
                for v in &p.verts {
                    eprintln!("PMVERT {:.6},{:.6},{:.6}", v.x, v.y, v.z);
                }
            }
        }
        let merged = bsp_merge_coplanars(fpolys);
        // SOUP-ORDER DUMP (UEDCLI_BSPCSG_SOUP_ORDER) — env-gated; the exact ORDER `bsp_build`/
        // `split_poly_list`/`find_best_split` consumes the post-merge soup, one line per face in
        // array order (the native counterpart of `editor_polys_oracle.py`'s bspBuild-entry dump).
        // Line format matches that oracle so `polys_order_diff.py` can diff the two sequences.
        if std::env::var("UEDCLI_BSPCSG_SOUP_ORDER").is_ok() {
            for (i, p) in merged.iter().enumerate() {
                eprintln!(
                    "POLY {} nv={} ilink={} N={:.5},{:.5},{:.5} B={:.5},{:.5},{:.5}",
                    i, p.verts.len(), p.i_link,
                    p.normal.x, p.normal.y, p.normal.z,
                    p.base.x, p.base.y, p.base.z
                );
                for v in &p.verts {
                    eprintln!("VERT {:.5},{:.5},{:.5}", v.x, v.y, v.z);
                }
            }
        }
        // DEBUG (harness soup differential): dump the post-merge soup — the exact input the editor
        // feeds its final SplitPolyList/FindBestSplit (== editor golden `Model.Polys`).  Packs each
        // merged FPoly as a leaf node so Python can reconstruct the face set; skips bsp_build.
        if std::env::var("UEDCLI_BSPCSG_SOUP_ONLY").is_ok() {
            model.nodes.clear();
            model.surfs.clear();
            model.verts.clear();
            model.points.clear();
            model.vectors.clear();
            for mut p in merged {
                p.i_link = -1;
                let _ = bsp_add_node(&mut model, -1, NODE_ROOT, 0, &p);
            }
            return Ok(model);
        }
        // CANONICAL SURF ORDER capture (§10.19).  The editor does NOT rebuild the Surfs pool at
        // repartition: it keeps the INCREMENTAL-CSG pool (each brush's surviving faces contiguous, in
        // brush-processing order, polys ascending) and only compacts it at `bspRefresh`.  Native's
        // repartition clears + re-allocates surfs in split-recursion order — a pure PERMUTATION of the
        // same 485-surf set that scrambles the on-disk Surfs/Vectors/Points-base order.  We snapshot
        // the incremental pool's `(iActor, iBrushPoly)` key order here (pre-clear) and, after the whole
        // build, re-sort the final surfs to it (`reorder_surfs_canonical`) + rebuild the Vectors pool
        // from the new surf order.  Key is unique per surf (proven vs the golden); walking surfs
        // `(vNormal, vTextureU, vTextureV)` reproduces the editor Vectors array byte-for-byte.
        canon_surf_keys = model.surfs.iter().map(|s| (s.i_actor, s.i_brush_poly)).collect();

        // Fresh node/surf/vert arrays: the reconstructed FPolys carry absolute coordinates
        // (bsp_node_to_fpoly copied them out), so a fresh Nodes/Surfs/Verts array lets `bsp_build`'s
        // own surf re-seeding (one fresh `alloc_surf` per distinct source surf id, see `bsp_build`)
        // and `bsp_add_node` rebuild them from `merged`. Vectors is UNCONDITIONALLY rebuilt later
        // anyway (`rebuild_vector_pool`, walking the final canonical Surfs' own refs), so clearing it
        // here has no effect on the final result either way — left as-is for symmetry with the
        // other CSG-phase pools, not because it matters.
        //
        // The editor's `EmptyModel(0,0)` (live gdb `emptymodel_worldlevel_trace.py`, UNATCO +
        // Wanchai, both node/surf/leaf-exact — called on the PERSISTENT world Model at this
        // checkpoint) clears Nodes/Verts but leaves Points BYTE-IDENTICAL across the call. Native
        // reproduces the editor's incremental point-pool: the Points pool is kept across the world-
        // level rebuild and GC'd only at the editor's real `bspRefresh` call sites — pre-repartition
        // bases-only (`compact_points_to_surf_bases` = `bspBuild@0x35ef0`'s NumVertices-zeroed
        // refresh before `EmptyModel(0,0)`), post-`bsp_build` (`bsp_refresh_points_vectors`), and
        // after the frontier repartitions — never during brush CSG, never after optgeom (native-
        // materialize-findings.md rounds 9-15; closes `DX.dx`'s `p_base` residual to 0/26).
        compact_points_to_surf_bases(&mut model);
        model.nodes.clear();
        model.surfs.clear();
        model.verts.clear();
        // Points are deliberately NOT cleared — kept across the rebuild, matching `EmptyModel(0,0)`.
        model.vectors.clear();
        bsp_build(&mut model, merged)?;
        passes::bsp_refresh(&mut model);
        // The editor's `bspRefresh` also drops unreferenced Points/Vectors on this call (not just
        // Nodes), bounding the kept CSG-phase pool back down.
        passes::bsp_refresh_points_vectors(&mut model);
        // CLEAR `NF_IsNew` ACROSS THE REBUILT TREE before anything filters through it.
        //
        // `NF_IsNew` is a per-brush TRANSIENT: `FBspNode::IsCsg()` (our `is_csg_filter`, mask 0x21)
        // reports a flagged node as NON-solid, so that the nodes a brush adds cannot influence how
        // that same brush's remaining faces classify.  The engine clears it in `bspCleanup` once an
        // Add/Subtract brush is done, which is why `bsp_brush_csg` ends with a gated `bsp_cleanup`
        // (an Active brush deliberately keeps its flags — see its tail comment).
        //
        // The repartition builds its whole tree through `split_poly_list` -> `bsp_add_node(…,
        // NF_IS_NEW, …)`, so EVERY node comes out flagged, and nothing cleared it before Pass 2 ran.
        // A detail brush therefore descended a world where no node was CSG-solid: `outside` never
        // flipped, every face reached an `F_INSIDE` leaf, and the Add leaf (which emits only on
        // `F_OUTSIDE`) dropped it — so semisolid/nonsolid brushes contributed NOTHING to the world,
        // silently.  Measured before this fix: `[wrap-subtract, semisolid-add]` built 6 nodes (the
        // wrap alone) where the same set with a SOLID add builds 12.
        //
        // The castle byte-identity golden never caught it: the castle has 0 detail brushes.
        bsp_cleanup(&mut model);
    }
    // STAGE COUNTS (UEDCLI_BSPCSG_STAGE_COUNTS) — env-gated.  Nothing in the serialized map says
    // which pipeline stage built a node, so a count gap against a golden cannot be attributed
    // without these.
    let stage_counts = std::env::var("UEDCLI_BSPCSG_STAGE_COUNTS").is_ok();
    if stage_counts {
        eprintln!(
            "STAGE post-repartition nodes={} surfs={} verts={} points={}",
            model.nodes.len(), model.surfs.len(), model.verts.len(), model.points.len()
        );
    }
    // POST-REPARTITION NODE DUMP (UEDCLI_BSPCSG_REPART_NODES) — env-gated.  Line format matches
    // `harness/editor-tree-oracle/repart_tree_unatco.py`, which reads the SAME state out of the live
    // editor (`Editor.dll 0x1004a05f`, right after `bspRefresh` inside `bspRepartition`), so the two
    // dumps diff node-for-node.
    if std::env::var("UEDCLI_BSPCSG_REPART_NODES").is_ok() {
        for (i, n) in model.nodes.iter().enumerate() {
            eprintln!(
                "RNODE {} isurf={} nv={} iB={} iF={} iP={} nf={} plane={:.5},{:.5},{:.5},{:.5}",
                i, n.i_surf, n.num_vertices, n.i_back, n.i_front, n.i_plane, n.node_flags,
                n.plane.x, n.plane.y, n.plane.z, n.plane.w
            );
        }
    }

    // TestVisibility runs HERE — between the repartition and the detail-brush loop, not after it.
    // `csgRebuild` (`Editor.dll 0x4a650`) calls `bspRepartition` (vtable `+0x1ec`) at `0x1004a89a`,
    // then `TestVisibility` (vtable `+0x264`) at `0x1004a8af`, and only then enters the second
    // (detail) `bspBrushCSG` loop at `0x1004a9e8` **[DISASM]**.  Live-confirmed on the 734-brush
    // UNATCO golden **[LIVE, `harness/editor-tree-oracle/brushcsg_calls_unatco.py`]**: the editor's
    // repartition returns 2953 nodes and the FIRST detail brush already sees 2984 — the +31 is the
    // zone pass's own fragment split, in the tree the detail brushes then filter through.
    //
    // Running it afterwards instead (native's old order) is wrong twice over: the detail brushes see
    // an unfragmented tree, and Pass D then re-fragments faces the detail layer has already cut, so a
    // face fans out far more than the editor's (measured +81 vs +31 on UNATCO).  Since the editor
    // never re-runs it, the leaves this pass writes go STALE against the finished tree — that is the
    // real editor's own bare-`MAP REBUILD` output (spec §14: 9.45 node `iLeaf` refs per leaf), not a
    // defect to paper over here.
    //
    // The pass reads the ENGINE child convention (`iFront`/`iBack` swapped relative to native's CSG
    // convention), so it is bracketed by the swap `finalize` used to own; the detail loop below needs
    // the native convention back.
    swap_node_children(&mut model);
    for n in model.nodes.iter_mut() {
        n.node_flags &= !NF_IS_NEW; // Pass D skips NF_IsNew fragments; clear even the unreachable.
    }
    zone_pass(&mut model);
    swap_node_children(&mut model);
    if stage_counts {
        eprintln!(
            "STAGE post-testvisibility nodes={} verts={} points={}",
            model.nodes.len(), model.verts.len(), model.points.len()
        );
    }

    // Snapshot the tree's frontier BEFORE the detail loop (`sub_49380` port — verified 2026-08-29 to
    // collect EXACTLY the 209 nodes that go on to grow on UNATCO, matching the editor's own count).
    let mut repart_frontier_a: Vec<i32> = Vec::new();
    let mut repart_frontier_b: Vec<i32> = Vec::new();
    if !model.nodes.is_empty() {
        collect_repartition_frontier(&model, 0, &mut repart_frontier_a, &mut repart_frontier_b);
    }

    // Pass 2: SEMISOLID detail brushes (incremental, NOT repartitioned) — NotSolid-only brushes
    // (portal or not) are NOT here; they were processed structurally in pass 1 (`detail_pass`).
    let pre_detail_surfs = model.surfs.len();
    for (bi, b) in brushes.iter().enumerate() {
        let pf = eff_flags(b);
        if !detail_pass(b, pf) {
            continue;
        }
        // Detail brushes still need NF_IsNew cleared per pass; bsp_brush_csg handles that.
        bsp_brush_csg(&mut model, b, bi as i32, pf);
        // BRUSHSTATE continues into Pass 2 (k keeps counting past the 728 structural calls), so the
        // per-brush count trace aligns against the editor's Pass-2 `bspBrushCSG` entries too.
        if brush_state.is_some() {
            eprintln!(
                "BRUSHSTATE k={} bi={} nodes={} surfs={} verts={} points={} vectors={}",
                k, bi, model.nodes.len(), model.surfs.len(), model.verts.len(),
                model.points.len(), model.vectors.len()
            );
            if let Some((lo, hi)) = full_range {
                if k >= lo && k <= hi {
                    for (i, n) in model.nodes.iter().enumerate() {
                        eprintln!(
                            "P1NODE k={} i={} pb={:08x},{:08x},{:08x},{:08x} iF={} iB={} iP={} isurf={} nv={} nf={:#x}",
                            k, i, n.plane.x.to_bits(), n.plane.y.to_bits(),
                            n.plane.z.to_bits(), n.plane.w.to_bits(),
                            n.i_front, n.i_back, n.i_plane, n.i_surf, n.num_vertices, n.node_flags
                        );
                    }
                }
            }
        }
        k += 1;
    }
    if stage_counts {
        eprintln!(
            "STAGE post-pass2 nodes={} verts={} points={}",
            model.nodes.len(), model.verts.len(), model.points.len()
        );
    }
    // PRE-REPARTITION-FRONTIER NODE DUMP (UEDCLI_BSPCSG_PREPART_NODES) — env-gated; the exact
    // tree state repartition_frontier's 209 calls are about to consume (matches editor's
    // checkpoint right as its first sub-repartition call begins, i.e. bspRepartition CALL idx=2
    // in `repart_child_trace.py`'s numbering).  Line format matches `RNODE` from
    // `UEDCLI_BSPCSG_REPART_NODES` / the editor's `repart_tree_unatco.py` oracle so the two can
    // be diffed structurally (which nodes are frontier leaves, not just aggregate counts) —
    // `unatco-verts-points-residual-after-the-zone`, testing whether the -625/-634 blanket-merge
    // deficit traces to a pre-repartition tree-SHAPE difference the matching aggregate count
    // (6314=6314) hides.  NOTE the swap convention: native's `i_back`/`i_front` here already
    // correspond to the editor's `iFront`/`iBack` respectively (see `collect_repartition_frontier`
    // — this mapping holds post the final `swap_node_children` above, not just during zone_pass).
    if std::env::var("UEDCLI_BSPCSG_PREPART_NODES").is_ok() {
        for (i, n) in model.nodes.iter().enumerate() {
            eprintln!(
                "PNODE {} isurf={} nv={} iB={} iF={} iP={} nf={} plane={:.5},{:.5},{:.5},{:.5}",
                i, n.i_surf, n.num_vertices, n.i_back, n.i_front, n.i_plane, n.node_flags,
                n.plane.x, n.plane.y, n.plane.z, n.plane.w
            );
        }
    }

    // Re-partition just the subtrees that grew on the pre-detail-loop frontier, then GC the
    // orphaned pre-repartition nodes `bsp_add_node`'s append-only growth leaves behind
    // (`bsp_refresh` does not collect nodes, only surfs/verts — see `compact_unreachable_nodes`).
    // The editor never rebuilds its Surfs pool at repartition (see `canon_surf_keys` above), so its
    // live pool through pass 2 is the incremental one plus whatever pass 2 appended — and that is the
    // length the frontier repartition's fresh-surf iLinks count up from. Native's own pool is the
    // repartition-rebuilt (shorter) one, so extend the canon snapshot with pass 2's appended surfs
    // and measure from there. Extending it does not move the final surf order: these keys sort after
    // every pass-1 rank, in the same pool order the `unwrap_or(base)` tie-break already gave them.
    canon_surf_keys.extend(
        model.surfs[pre_detail_surfs..].iter().map(|s| (s.i_actor, s.i_brush_poly)),
    );
    repartition_frontier(&mut model, &repart_frontier_a, &repart_frontier_b,
                         canon_surf_keys.len())?;
    compact_unreachable_nodes(&mut model);
    // Round 15: each frontier `bspRepartition(node, 2)` ends with a full `bspRefresh`
    // (`bspRepartition.decompiled.c` line 34 / round 14's rfidx=4/5 — the LAST Points GCs of the
    // whole build; nothing after optgeom ever GCs). The real `bspRefresh` at this site runs with
    // `NoRemapSurfs=1` (every surf kept), compacts nodes (here already done by
    // `compact_unreachable_nodes`) and GCs Points/Vectors — but NEVER compacts the verts array,
    // and remaps `i_vertex` only through live node pools (`bspRefresh.decompiled.c`'s final loop):
    // `repartition_frontier`'s orphan verts survive to disk with STALE `i_vertex` values (golden
    // keeps them — `DX.dx` verts 250 includes 104 such orphans; a repack here broke that count).
    // Hence the `_stale_orphans` variant, not `bsp_refresh_points_vectors` (whose all-verts remap
    // would set orphans to `-1` and panic `bsp_opt_geom`'s all-verts near-merge remap — the exact
    // UNATCO flag-on panic measured this round).
    passes::bsp_refresh_points_vectors_stale_orphans(&mut model);
    if stage_counts {
        eprintln!(
            "STAGE post-repartition-frontier nodes={} verts={} points={}",
            model.nodes.len(), model.verts.len(), model.points.len()
        );
    }

    // finalize (leaves/zones/bbox) + collision hulls.
    finalize(&mut model);
    if stage_counts {
        eprintln!(
            "STAGE post-finalize nodes={} verts={} points={}",
            model.nodes.len(), model.verts.len(), model.points.len()
        );
    }
    // PRE-OPTGEOM NODE DUMP (UEDCLI_BSPCSG_PREOPT_NODES) — env-gated; native counterpart of the
    // editor's `bspopt_pool_oracle`-family Model->Nodes dump at bspOptGeom ENTRY (§10.13).  Emits
    // each node's plane + iF/iB/iP + isurf + nv so the pre-optgeom TREE can be diffed node-for-node
    // vs the editor (both post-refresh/post-Pass-D, pre-weld, engine convention) — the fair
    // comparison that disambiguates a partitioner (SplitPolyList) ring-vertex gap from a bspOptGeom
    // weld gap.  Default path byte-unchanged (mirrors the SOUP_ORDER/TREE_STRUCT hooks).
    if std::env::var("UEDCLI_BSPCSG_PREOPT_NODES").is_ok() {
        eprintln!("PREOPT nodes={} verts={} points={}", model.nodes.len(), model.verts.len(), model.points.len());
        for (i, n) in model.nodes.iter().enumerate() {
            eprintln!(
                "PN node={} plane=({:.5},{:.5},{:.5},{:.5}) iF={} iB={} iP={} isurf={} nv={}",
                i, n.plane.x, n.plane.y, n.plane.z, n.plane.w,
                n.i_front, n.i_back, n.i_plane, n.i_surf, n.num_vertices
            );
        }
    }
    // bspOptGeom: T-junction elimination (grows Verts) + shared-side linking (sets every iSide
    // and NumSharedSides).  Mirrors csgRebuild's call ORDER (Editor 0x4a650, §80): it runs at
    // step 5 — AFTER the repartition+bspRefresh (step 2), AFTER TestVisibility's zone fragment-split
    // (step 3 = our zones Pass D, `zone_pass`), AND after the semisolid/detail second layer
    // (step 4 = our Pass 2 above) — right before bspBuildBounds.  Running it here (not at the
    // repartition tail) is load-bearing: the zone split creates the extra coplanar faces whose
    // near-endpoint T-cracks pass 1 welds, and `finalize`'s front/back swap has put the tree in
    // ENGINE convention (iFront=+0x20 / iBack=+0x24) — the exact convention AddPointLink's descent
    // reads.  Preconditions consumed: Points + node plane/iVertPool/NumVertices/iFront/iBack/iPlane
    // (Pass D appends split fragments onto the iPlane coplanar chain) + verts[].iVertex.
    crate::bspoptgeom::bsp_opt_geom(&mut model);
    passes::bsp_build_bounds(&mut model);
    if stage_counts {
        eprintln!(
            "STAGE post-optgeom nodes={} verts={} points={}",
            model.nodes.len(), model.verts.len(), model.points.len()
        );
    }

    // §10.19: canonicalize the Surfs pool to the editor's incremental-CSG order and rebuild the
    // Vectors pool from it.  A pure relabel of the Surfs/Vectors arrays + node.iSurf remap — it
    // touches no node plane/link, no vert, no bound/hull, so the node tree stays byte-identical.
    // Both fire together or not at all: an empty snapshot (repartition skipped via NOREPART) leaves
    // BOTH the Surfs order AND the Vectors pool untouched — never one without the other.
    if !canon_surf_keys.is_empty() {
        reorder_surfs_canonical(&mut model, &canon_surf_keys);
        rebuild_vector_pool(&mut model);
        // `model.points` is already in the editor's own incremental order, GC'd at the editor's
        // real call sites (pre-repartition, post-`bsp_build`, frontier tails). The editor never GCs
        // after the frontier repartitions — optgeom's additions survive untouched — so nothing runs
        // here for Points.
    }
    Ok(model)
}

// --- csgPrepMovingBrush: a mover's private shape-model build --------------------------------

// The mover-build `bspBuild` partition params, derived from the 28 built mover models in the
// UNATCO `MAP IMPORT` golden (2026-09-02): GOOD/15 reproduces every node tree byte-exactly, and
// both are DISCRIMINATED by the goldens (Balance=50: 10/28 diverge; Opt=LAME: 6/28).  PortalBias
// is NOT exercised (no mover brush carries a PF_Portal poly, so the discount never fires) — its
// value is unconfirmed by bytes.
const MOVER_BALANCE: i32 = 15;
const MOVER_PORTAL_BIAS: i32 = 70;

/// `csgPrepMovingBrush`: build a MOVER's private shape `UModel` over the brush's OWN local-space
/// polys — a plain `bspBuild` (no CSG), then bounds.  The editor runs this for every mover at
/// `MAP IMPORT`/rebuild, so a saved map carries a small BUILT model per mover where
/// `assemble_unbuilt` used to write an empty one.
///
/// Pipeline (golden-derived, all 28 UNATCO mover models byte-identical):
///   `SplitPolyList` with `RebuildSimplePolys` surf seeding (fresh surf per splitter, coplanars
///   share it — surfs allocate in NODE-EMIT order), clear `NF_IsNew`, exchange children into the
///   engine's on-disk convention, then the `FilterBound` bounds/hulls pass.  `RootOutside=true`
///   (the golden trailer is 1/1; `Linked` is serialized by the Python writer).
///
/// The caller passes the polys exactly as stored in the brush's `Polys` (base/normal/axes/pan/
/// texture ref verbatim); `num_shared_sides` comes out 4 (the engine's fresh-model constant) and
/// zones/leaves stay empty — no zone pass runs on a brush model.
///
/// Also returns the per-SOURCE-poly `iLink` the editor leaves in the mover's saved `Polys`: the
/// build mutates the brush's own `Polys` elements in place, so a poly consumed WHOLE (splitter or
/// coplanar) ends with its assigned surf index, while a SPLIT poly keeps its pre-build value —
/// the `bspValidateBrush` link (group-leader poly index).  Golden-verified over the 28 UNATCO
/// mover `Polys` bodies (12 of which differ from the plain validate result).
pub fn build_brush_model(polys: &[FPoly]) -> Result<(Model, Vec<i32>), BuildError> {
    let mut model = Model::default();
    model.root_outside = true;
    model.num_shared_sides = 4;
    // Pre-build links: what a poly's saved iLink stays at when the build splits it.
    let mut links = bsp_validate_brush_links(polys);
    let ready: Vec<FPoly> = polys
        .iter()
        .enumerate()
        .filter(|(_, p)| p.verts.len() >= 3)
        .map(|(i, p)| {
            let mut q = p.clone();
            q.src = i as i32;
            q
        })
        .collect();
    if ready.is_empty() {
        return Ok((model, links));
    }
    split_poly_list(
        &mut model,
        -1,
        NODE_ROOT,
        ready,
        0,
        MOVER_BALANCE,
        MOVER_PORTAL_BIAS,
        Opt::Good,
        &mut 0,
        Some(&mut links),
    )?;
    for n in model.nodes.iter_mut() {
        n.node_flags &= !NF_IS_NEW;
    }
    swap_node_children(&mut model);
    passes::bsp_build_bounds(&mut model);
    // Local-space bbox over the pooled points (the Python shape-model writer recomputes the
    // serialized prefix bbox/sphere from the brush polys, so this is informational).
    if !model.points.is_empty() {
        let mut mn = model.points[0];
        let mut mx = model.points[0];
        for p in &model.points {
            mn = Vec3::new(mn.x.min(p.x), mn.y.min(p.y), mn.z.min(p.z));
            mx = Vec3::new(mx.x.max(p.x), mx.y.max(p.y), mx.z.max(p.z));
        }
        model.bbox_min = mn;
        model.bbox_max = mx;
    }
    Ok((model, links))
}

/// The `bspBrushCSG` **Intersect/Deintersect tail** (`0x35ab3`) — the whole of the editor's
/// `BRUSH FROM INTERSECTION` / `BRUSH FROM DEINTERSECTION`, reframed onto a stateless in-tree brush
/// SET (spec in board item `bspcsg-core-apply-scaled-brushes`; RE
/// `re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`).
///
/// `brushes` is the world CSG set **in stdin order** — for `intersect` the caller prepends the
/// synthesized wrap-subtract cube that forces an EMPTY background; for `deintersect` it is the set
/// alone, against the default SOLID world.  `builder` is the synthesized padded-bbox cube carrying
/// `CsgOper = Intersect | Deintersect`, which selects the operation.  Both cubes are generated
/// Python-side at the editor's exact offsets so the scaffolding is byte-identical to the
/// editor-driven golden generator (`dispatch._stash_intersect_impl`).
///
/// Returns the result polylist (the editor writes it straight back into the builder brush's
/// `Polys`) — world-space faces, `i_link` renumbered to the surf-share representative.
///
/// **DELIBERATE DEVIATION from the editor's tail, after the renumber.**  `0x35d3b`-`0x35db9` runs a
/// per-result-poly loop the decode doc's §1 does not mention: `FPoly::Transform(&Coords,
/// [actor+0xd0], [actor+0x140], Orientation)` (IAT `0x100cee3c`) maps each poly back into
/// BUILDER-LOCAL space, then `Fix()`, then `Poly.Actor = NULL` (`+0x1b4`) and `Poly.iBrushPoly = i`
/// (`+0x1c8`).  We do NOT do that: we return WORLD-space polys and keep `actor`/`i_brush_poly` as
/// the SOURCE brush's ids.  Both are load-bearing for the caller — the CSG core never sees
/// textures, so `brushcsg.py` recovers each face's `Texture`/`PanU`/`PanV` from the source poly via
/// those ids, and it applies its own `--origin`/`--pivot` rebasing (spec §6b) in place of the
/// editor's fixed builder-local form.  The dropped trailing `Fix()` is a no-op over a pure
/// translation.  Do not "restore" this loop without giving the caller another route to texture
/// identity.
///
/// **Why the world is the FULL rebuild.** The editor's oracle runs the command after `MAP REBUILD`,
/// so Phase 1 descends and Phase 2 walks the fully repartitioned + optimized tree, not the raw
/// incremental CSG tree.  We therefore build the world with the whole `build_geometry_bspcsg`
/// pipeline and then UNDO `finalize`'s `iFront`/`iBack` exchange: that swap exists only to put the
/// tree in the engine's on-disk `iChild[0]=BACK` serialization convention (`build.rs:731`), while
/// every filter descent in this module reads the pre-`finalize` convention.  Swapping back yields
/// the rebuilt tree in the convention the descent expects.
pub fn intersect_brushset(
    brushes: &[build::BrushInput],
    builder: &build::BrushInput,
) -> Result<Vec<FPoly>, BuildError> {
    let deintersect = match builder.oper {
        csg::CsgOper::Intersect => false,
        csg::CsgOper::Deintersect => true,
        _ => {
            return Err(BuildError(
                "intersect_brushset: the builder brush must carry CsgOper Intersect (3) or \
                 Deintersect (4)"
                    .into(),
            ))
        }
    };

    // The builder never goes through `build_geometry_bspcsg`, so it would otherwise dodge that
    // function's scaled-brush reject and be built at UNIT size by `FPoly::transform` (which applies
    // `rot`/`prepivot`/`location` and ignores `scale` entirely) — a silently wrong-sized hull that
    // would carve the wrong result.  uedcli synthesizes an unscaled cube, but this is a public
    // `#[pyfunction]` entry point.
    if (builder.scale.x - 1.0).abs() > 1e-6
        || (builder.scale.y - 1.0).abs() > 1e-6
        || (builder.scale.z - 1.0).abs() > 1e-6
    {
        return Err(BuildError(format!(
            "intersect_brushset: the builder brush has non-identity Scale {:?} — scaled brushes are \
             not supported",
            (builder.scale.x, builder.scale.y, builder.scale.z)
        )));
    }

    let mut world = build_geometry_bspcsg(brushes)?;
    // An empty world means there is nothing to intersect AGAINST: Phase 2 is skipped by its
    // `Nodes.Num != 0` guard, and Phase 1's empty-tree rule classifies every builder face
    // `F_INSIDE`, so `intersect` would hand back the synthesized scaffolding cube dressed up as the
    // answer.  The verbs guarantee a non-empty world (intersect prepends the wrap-subtract,
    // deintersect the seed-subtract), so this only guards direct FFI callers.
    if world.nodes.is_empty() {
        return Err(BuildError(
            "intersect_brushset: the brush set produced no world geometry — there is nothing to \
             intersect against (an empty or fully-degenerate set)"
                .into(),
        ));
    }
    for n in world.nodes.iter_mut() {
        std::mem::swap(&mut n.i_front, &mut n.i_back);
    }

    // LOOP 1 (shared, `0x35791`): the builder's faces into world space, solidity bits stripped.
    // `actor_index = -1` marks these as BUILDER-sourced so the caller can tell them from the Phase-2
    // world caps (which carry the source brush's index and thus its texture).
    let temp = brush_loop1(builder, -1, 0);

    let mut result: Vec<FPoly> = Vec::new();

    // PHASE 1 (`0x35ac1`): clip each BUILDER face to the world's solid/empty field.
    let p1 = if deintersect {
        CollectKind::DeintersectP1
    } else {
        CollectKind::IntersectP1
    };
    for ed in &temp {
        bsp_filter_fpoly(&mut world, LeafFunc::Collect(p1), ed, &mut result);
    }
    let p1_count = result.len();

    // PHASE 2 (`0x35b3d`): clip each straddling WORLD face to the builder hull.  Guarded by
    // `World->Nodes.Num != 0` (`0x35b43`) — against an unbuilt world both ops degrade to Phase 1.
    // (`argPolyFlags & 0x28` is the other guard; `argPolyFlags` is 0 for the exec commands.)
    if !world.nodes.is_empty() {
        let brush_temp = build_brush_temp_bsp(&temp)?;
        let p2 = if deintersect {
            CollectKind::DeintersectP2
        } else {
            CollectKind::IntersectP2
        };
        // `subtract` is dead in collect mode — the leaf is chosen explicitly by `p2`, mirroring
        // FWTB's own `CsgOper` switch (`fwtb_switch.asm 0x333d7`).
        filter_world_through_brush(&mut world, &brush_temp, false, Some(p2), &mut result);
    }

    // FINALIZE (`0x35c14`): the iLink surf-share renumber, then `RootOutside = 1` (the latter is a
    // property of the builder UModel the editor writes back into; we return a bare polylist).
    renumber_result_ilinks(&mut result, p1_count);
    Ok(result)
}

/// The intersect/deintersect finalize renumber (`0x35c44` forward pass, `0x35cb1` backward pass).
///
/// Two INDEPENDENT grouping passes — one over the Phase-1 polys `[0, p1_count)`, one over the
/// Phase-2 polys `[p1_count, len)` — each rewriting every poly's `iLink` to the index of the FIRST
/// poly **in its own range** carrying the same original `iLink` (i.e. sharing a surf), or to itself
/// when it is the first.  The ranges never merge: a Phase-2 cap never links to a Phase-1 builder
/// face even if their source surfs happened to collide numerically.  Each pass walks `i` DOWNWARD,
/// so the `j < i` it compares against still hold their original values.
fn renumber_result_ilinks(result: &mut [FPoly], p1_count: usize) {
    let n = result.len();
    for (lo, hi) in [(0usize, p1_count), (p1_count, n)] {
        for i in (lo..hi).rev() {
            let orig = result[i].i_link;
            let rep = (lo..i).find(|&j| result[j].i_link == orig).unwrap_or(i);
            result[i].i_link = rep as i32;
        }
    }
}

/// Re-sort the final Surfs pool into the editor's canonical (incremental-CSG) order and remap every
/// `node.i_surf`.  `canon` is the pre-repartition-clear snapshot of `(iActor, iBrushPoly)` keys in
/// incremental order; surfs whose key is not in it (e.g. the semisolid/detail second layer, added
/// after the snapshot) keep their existing relative order AFTER all snapshot-ranked surfs.  No-op
/// when `canon` is empty (repartition skipped).  See §10.19.
fn reorder_surfs_canonical(model: &mut Model, canon: &[(i32, i32)]) {
    if canon.is_empty() || model.surfs.is_empty() {
        return;
    }
    let mut rank: std::collections::HashMap<(i32, i32), usize> = std::collections::HashMap::new();
    for (i, k) in canon.iter().enumerate() {
        rank.entry(*k).or_insert(i);
    }
    let base = canon.len();
    let n = model.surfs.len();
    // new_order[new_index] = old_index (stable sort by canonical rank; unknown keys sort last, in
    // their existing order via the tie-break on old index).
    let mut new_order: Vec<usize> = (0..n).collect();
    new_order.sort_by_key(|&i| {
        let k = (model.surfs[i].i_actor, model.surfs[i].i_brush_poly);
        let r = rank.get(&k).copied().unwrap_or(base);
        (r, i)
    });
    let mut old_to_new = vec![0i32; n];
    for (new_i, &old_i) in new_order.iter().enumerate() {
        old_to_new[old_i] = new_i as i32;
    }
    // The retained CSG soup (`model.polys`) froze each poly's `i_link = i_surf` at repartition
    // `bsp_build`, indexing this same pre-canonical Surfs pool. It must be remapped, but NOT to the
    // dense on-disk surf index the nodes use: UED22 numbers `Model.Polys` iLink in the FULL canon
    // (incremental-CSG) surf space — the `canon` snapshot the repartition rebuilt from, which can be
    // LARGER than the final pool when repartition merged a surf away. So the editor's iLink leaves a
    // GAP at the merged surf's canon rank and can exceed the final surf count (e.g. WanChai N=4:
    // 16 final surfs, a poly with iLink 16). Map each soup poly to its surf's canon RANK, not the
    // dense index. When `canon` has no gap (UNATCO/NYC_Bar N=4) the rank equals the dense index.
    let old_to_rank: Vec<i32> = (0..n).map(|i| {
        let k = (model.surfs[i].i_actor, model.surfs[i].i_brush_poly);
        rank.get(&k).copied().unwrap_or(base) as i32
    }).collect();
    let new_surfs: Vec<BspSurf> = new_order.iter().map(|&i| model.surfs[i].clone()).collect();
    model.surfs = new_surfs;
    for node in &mut model.nodes {
        if node.i_surf >= 0 && (node.i_surf as usize) < old_to_new.len() {
            node.i_surf = old_to_new[node.i_surf as usize];
        }
    }
    for p in &mut model.polys {
        if p.i_link >= 0 && (p.i_link as usize) < old_to_rank.len() {
            p.i_link = old_to_rank[p.i_link as usize];
        }
    }
}

/// Rebuild the Vectors pool from the (now canonical) Surfs order: walk surfs, `find-or-add` each
/// surf's `vNormal`, `vTextureU`, `vTextureV` (exact-equality dedup, pulled from the existing pool)
/// and rewrite the surf's refs.  This is the exact rule that reproduces the editor's Vectors array
/// (proven vs the golden: 26/26).  The pool value-set is unchanged — a pure permutation + reindex,
/// referenced by nothing but the surfs, so no node/vert/bound is affected.  See §10.19.
fn rebuild_vector_pool(model: &mut Model) {
    if model.surfs.is_empty() {
        return;
    }
    let old = model.vectors.clone();
    let mut new_vecs: Vec<Vec3> = Vec::with_capacity(old.len());
    // Remap a vector ref into the fresh pool.  A negative ref (`-1` = "no axis") is preserved as-is,
    // mirroring the guarded read in `bsp_node_to_fpoly` (surf axes are legitimately optional); today
    // every surf axis comes from `bsp_add_vector` (>= 0), but the guard keeps this no less defensive
    // than its neighbours.  `old` entries are already tolerance-deduped on insertion, so exact-equality
    // dedup here merges only true co-references and never collapses two distinct pool entries.
    let mut remap = |r: i32| -> i32 {
        if r < 0 {
            return r;
        }
        let v = old[r as usize];
        for (i, p) in new_vecs.iter().enumerate() {
            if *p == v {
                return i as i32;
            }
        }
        new_vecs.push(v);
        (new_vecs.len() - 1) as i32
    };
    for s in &mut model.surfs {
        s.v_normal = remap(s.v_normal);
        s.v_texture_u = remap(s.v_texture_u);
        s.v_texture_v = remap(s.v_texture_v);
    }
    model.vectors = new_vecs;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::csg::CsgOper;

    // The two live-captured N8 trees at the divergent add (actor-6 -X surf-base), normalized to one
    // node per line: `RN k N=(x,y,z) W=w pt=(px,py,pz) iF=.. iB=.. iP=..` where pt = the node's
    // surf-base point. Spike 2026-09-05-faithful-dedup-fix-attempt/stage2b (`descent_sim.py`).
    // (crate-local copies of the spike-dir dumps — the build container only mounts `uedcli-native/`.)
    const EDITOR_TREE_RN: &str = include_str!("../testdata/n8_editor_tree_rn.txt");
    const NATIVE_TREE_RN: &str = include_str!("../testdata/n8_native_tree_rn.txt");

    /// Build a Model from an RN fixture: one node per line, its surf-base point = `pt` (num_vertices=0
    /// so only surf-bases are tested — matching `descent_sim.py`).
    fn model_from_rn(txt: &str) -> Model {
        let mut m = Model::default();
        let mut recs: Vec<(usize, [f32; 4], Vec3, i32, i32, i32)> = Vec::new();
        for line in txt.lines() {
            if !line.starts_with("RN ") {
                continue;
            }
            let clean = line.replace(['=', '(', ')', ','], " ");
            let t: Vec<&str> = clean.split_whitespace().collect();
            // RN k N x y z W w pt px py pz iF a iB b iP c
            let g = |i: usize| t[i].parse::<f32>().unwrap();
            recs.push((
                t[1].parse().unwrap(),
                [g(3), g(4), g(5), g(7)],
                Vec3::new(g(9), g(10), g(11)),
                t[13].parse().unwrap(),
                t[15].parse().unwrap(),
                t[17].parse().unwrap(),
            ));
        }
        recs.sort_by_key(|r| r.0);
        for (k, pl, pt, _, _, _) in &recs {
            m.points.push(*pt);
            m.surfs.push(BspSurf {
                texture_ref: -1,
                poly_flags: 0,
                p_base: *k as i32,
                v_normal: 0,
                v_texture_u: 0,
                v_texture_v: 0,
                i_actor: -1,
                i_brush_poly: -1,
                pan: [0, 0],
                i_light_map: -1,
            });
            let mut n = BspNode::leaf(Plane { x: pl[0], y: pl[1], z: pl[2], w: pl[3] }, *k as i32, 0, 0);
            n.i_front = recs[*k].3;
            n.i_back = recs[*k].4;
            n.i_plane = recs[*k].5;
            m.nodes.push(n);
        }
        m
    }

    #[test]
    fn fnv_misses_the_far_corner_the_linear_scan_snaps() {
        // The x=448 divergence: at the actor-6 -X surf-base add the corner point (448.00006,64,~0) is
        // a live, reachable surf-base in BOTH trees, but the radius-pruned descent MISSES it (pruned
        // behind planes 416/4/1552uu from the query) -> keeps 447.99985 distinct, matching UED22. The
        // old linear scan finds it (d=2.16e-4 < 0.002) and wrongly snaps.
        let q = Vec3::new(447.999847, 64.000107, 0.0);
        let tol = THRESH_POINTS_ARE_SAME;
        // The editor dump is in the ENGINE child convention; the native dump was captured DURING
        // incremental CSG, in native's SWAPPED convention (pre-`swap_node_children`).
        for (name, txt, engine) in [("editor", EDITOR_TREE_RN, true), ("native", NATIVE_TREE_RN, false)] {
            FNV_ENGINE_CHILDREN.with(|c| c.set(engine));
            let m = model_from_rn(txt);
            assert_eq!(m.nodes.len(), 62, "{name}: expected the 62-node N8 tree");
            assert_eq!(
                find_nearest_vertex(&m, q, tol), None,
                "{name}: FindNearestVertex must MISS (radius-pruned) at the divergent add"
            );
            // The corner IS present within tol -> the old linear scan snapped (the bug).
            let linear = m.points.iter().position(|p| q.sub(p).size() < tol);
            assert!(linear.is_some(), "{name}: a within-tol point exists (the linear scan snapped it)");
        }
        FNV_ENGINE_CHILDREN.with(|c| c.set(false)); // restore the default (live CSG convention)
    }

    #[test]
    fn fnv_hits_an_exact_point_and_empty_tree_misses() {
        // Sanity: a query ON a reachable, unpruned node's surf-base HITS; an empty tree MISSES.
        let mut m = Model::default();
        assert_eq!(find_nearest_vertex(&m, Vec3::new(1.0, 2.0, 3.0), 0.002), None);
        m.points.push(Vec3::new(10.0, 0.0, 0.0));
        m.surfs.push(BspSurf {
            texture_ref: -1, poly_flags: 0, p_base: 0, v_normal: 0, v_texture_u: 0,
            v_texture_v: 0, i_actor: -1, i_brush_poly: -1, pan: [0, 0], i_light_map: -1,
        });
        // Root plane x=1 through the point; query on the point -> pd=0, within slab -> tested -> HIT.
        m.nodes.push(BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 10.0 }, 0, 0, 0));
        assert_eq!(find_nearest_vertex(&m, Vec3::new(10.0, 0.0, 0.0), 0.002), Some(0));
    }

    #[test]
    fn ring_tolerance_add_also_goes_through_the_descent() {
        // `bspAddPoint` (Editor.dll 0x35430) calls `FindNearestVertex` UNCONDITIONALLY, with the
        // threshold its `Exact` arg picks (0x3545c: `arg ? 0.002 : 0.015`) -- so the node vertex-RING
        // add (`bspAddNode 0x352fd push 0` -> 0.015) is deduped by the same radius-pruned descent as
        // the 0.002 surf-base add, NOT by a pool scan. Native scoped the descent to 0.002 only, so a
        // ring add snapped to a pool point the editor's descent cannot reach (WanChai N20: a
        // 1.22e-4 near-tie at x=1408 that stored the grid value instead of the tilted brush's).
        //
        // One node, plane x=0, whose surf base is point 0 AT the plane; point 1 sits 100uu away, in
        // the pool but wired to nothing. Both queries are 1e-3 from a pool point — inside 0.015,
        // outside 0.002 — so they separate the ring tolerance from the surf-base one.
        let mut model = Model::default();
        model.points.push(Vec3::new(0.0, 0.0, 0.0)); // the node's surf base: the descent reaches it
        model.points.push(Vec3::new(100.0, 0.0, 0.0)); // wired to no node, and 100uu off the plane
        model.surfs.push(BspSurf {
            texture_ref: -1, poly_flags: 0, p_base: 0, v_normal: 0, v_texture_u: 0,
            v_texture_v: 0, i_actor: -1, i_brush_poly: -1, pan: [0, 0], i_light_map: -1,
        });
        model.nodes.push(BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, 0, 0, 0));
        let unreachable_q = Vec3::new(100.001, 0.0, 0.0);
        let reachable_q = Vec3::new(0.001, 0.0, 0.0);

        let mut incremental = model.clone();
        let _fnv = FnvDedupGuard::enable();
        // Point 1 is 100uu beyond the root plane, so the descent prunes it and never tests it -> ADD.
        assert_eq!(
            bsp_add_point_tol(&mut incremental, unreachable_q, ring_point_tol()), 2,
            "the ring add must use the descent, which cannot reach the pruned point -> ADD"
        );
        // Point 0 is inside the radius band, so the SAME descent snaps it at the ring tolerance —
        // pinning that the descent runs with 0.015, not a hard-coded 0.002 (which would MISS here).
        assert_eq!(
            bsp_add_point_tol(&mut incremental, reachable_q, ring_point_tol()), 0,
            "the ring add's descent must carry the 0.015 tolerance, not the 0.002 one"
        );
        drop(_fnv);

        // Repartition (descent off) keeps the pool scan, which snaps the pruned point too.
        assert_eq!(bsp_add_point_tol(&mut model, unreachable_q, ring_point_tol()), 1);
    }

    #[test]
    fn repartition_point_add_snaps_to_the_nearest_pool_point_not_the_first() {
        // The repartition stand-in picks the nearest pool point, not the first inside the threshold
        // (see `bsp_add_point_tol`). Island's two coplanar oblique-face bases, 0.001953125 apart in y
        // and both inside the 0.002 SAME threshold, are the case that separates the two rules.
        let mut model = Model::default();
        model.points.push(Vec3::new(-3488.0, -6336.0, 0.0)); // Brush1355's base, pooled first
        model.points.push(Vec3::new(-3488.0, -6336.001953125, 0.0)); // Brush1359's own base
        let q = Vec3::new(-3488.0, -6336.001953125, 0.0);
        assert_eq!(
            bsp_add_point_tol(&mut model, q, THRESH_POINTS_ARE_SAME), 1,
            "must snap to the exact point, not the 0.00195-away one that comes first in the pool"
        );
        assert_eq!(model.points.len(), 2, "an exact match must not push a new point");
    }

    #[test]
    fn bsp_add_vector_keeps_axes_5e4_apart_merges_below_4e4() {
        // `bspAddVector` texture-axis dedup at `THRESH_VECTORS_ARE_NEAR` = 4e-4 (DISASM 0x35530).
        // Two axes 5e-4 apart stay distinct (OceanLab N3 pooled these at the old 0.001); two <4e-4
        // apart merge to the first. `exact=false` = texture axis.
        let mut model = Model::default();
        let base = Vec3::new(-0.863011, 0.505185, 0.0);
        let i0 = bsp_add_vector(&mut model, base, false);
        assert_eq!(i0, 0);

        // 5e-4 away (Euclidean) -> above 4e-4 -> kept distinct.
        let far = Vec3::new(base.x, base.y + 5.0e-4, 0.0);
        let i_far = bsp_add_vector(&mut model, far, false);
        assert_eq!(i_far, 1, "axes 5e-4 apart must stay distinct at the 4e-4 threshold");
        assert_eq!(model.vectors.len(), 2);

        // 3e-4 away -> below 4e-4 -> merges to the first-within-threshold entry (base, idx0).
        let near = Vec3::new(base.x, base.y + 3.0e-4, 0.0);
        let i_near = bsp_add_vector(&mut model, near, false);
        assert_eq!(i_near, 0, "axes <4e-4 apart must merge to the first within threshold");
        assert_eq!(model.vectors.len(), 2, "no new vector pushed for a sub-threshold axis");
    }

    /// Decode one mover-build fixture (`dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness/extract_mover_fixtures.py` format):
    /// `(none_index, field_0x54, polys, saved_links)` — `saved_links` is the golden `Polys`
    /// body's per-poly `iLink` after `csgPrepMovingBrush`.
    pub(super) fn decode_mover_fixture(blob: &[u8]) -> (i32, i32, Vec<FPoly>, Vec<i32>) {
        let i32_at = |o: usize| i32::from_le_bytes(blob[o..o + 4].try_into().unwrap());
        let f32_at = |o: usize| f32::from_le_bytes(blob[o..o + 4].try_into().unwrap());
        let v3_at = |o: usize| Vec3::new(f32_at(o), f32_at(o + 4), f32_at(o + 8));
        let (none_index, f54, n_polys) = (i32_at(0), i32_at(4), i32_at(8) as usize);
        let mut off = 12usize;
        let mut polys = Vec::with_capacity(n_polys);
        for _ in 0..n_polys {
            let nv = i32_at(off) as usize;
            let (base, normal, tu, tv) =
                (v3_at(off + 4), v3_at(off + 16), v3_at(off + 28), v3_at(off + 40));
            off += 52;
            let mut verts = Vec::with_capacity(nv);
            for _ in 0..nv {
                verts.push(v3_at(off));
                off += 12;
            }
            let mut p = FPoly::new(verts);
            p.base = base;
            p.normal = normal;
            p.texture_u = tu;
            p.texture_v = tv;
            p.poly_flags = i32_at(off) as u32;
            p.texture = i32_at(off + 4);
            p.pan = [i32_at(off + 8), i32_at(off + 12)];
            off += 16;
            polys.push(p);
        }
        let mut saved_links = Vec::with_capacity(n_polys);
        for _ in 0..n_polys {
            saved_links.push(i32_at(off));
            off += 4;
        }
        assert_eq!(off, blob.len(), "fixture blob not fully consumed");
        (none_index, f54, polys, saved_links)
    }

    /// `build_brush_model` over a fixture's polys, serialized with `field_0x54`/`none_index`
    /// aligned to the golden's; returns `(body, built_links, saved_links)`.  The 42-byte prefix
    /// (bbox/sphere — Python-owned) and the 8-byte trailer (`RootOutside`/`Linked` — golden 1/1,
    /// Rust serializer writes the level's 0/0) are the caller's to exclude.
    pub(super) fn mover_fixture_body(blob: &[u8]) -> (Vec<u8>, Vec<i32>, Vec<i32>) {
        let (none_index, f54, polys, saved_links) = decode_mover_fixture(blob);
        let (mut m, links) = build_brush_model(&polys).unwrap();
        m.none_index = none_index;
        m.field_0x54 = f54;
        (crate::model_write::serialize(&m).unwrap(), links, saved_links)
    }

    /// Pinned mover fixtures (committed bytes extracted from the UNATCO `MAP IMPORT` golden,
    /// 2026-09-02): the three smallest shape models (a plain box each) + `Mover0` (coplanar-chain
    /// surf sharing, 24 polys → 18 surfs).  Byte-exact model body — minus the 42-byte prefix and
    /// 8-byte trailer, which the Python shape-model writer owns — and the saved `Polys` iLink.
    #[test]
    fn mover_model_fixtures_byte_exact() {
        let cases: [(&str, &[u8], &[u8]); 4] = [
            (
                "Model_DeusExMover0",
                include_bytes!("../fixtures/mover/Model_DeusExMover0.polys"),
                include_bytes!("../fixtures/mover/Model_DeusExMover0.body"),
            ),
            (
                "Model_DeusExMover5",
                include_bytes!("../fixtures/mover/Model_DeusExMover5.polys"),
                include_bytes!("../fixtures/mover/Model_DeusExMover5.body"),
            ),
            (
                "Model_DeusExMover21",
                include_bytes!("../fixtures/mover/Model_DeusExMover21.polys"),
                include_bytes!("../fixtures/mover/Model_DeusExMover21.body"),
            ),
            (
                "Model_DeusExMover22",
                include_bytes!("../fixtures/mover/Model_DeusExMover22.polys"),
                include_bytes!("../fixtures/mover/Model_DeusExMover22.body"),
            ),
        ];
        for (name, blob, want) in cases {
            let (got, links, saved_links) = mover_fixture_body(blob);
            assert_eq!(got.len(), want.len(), "{name}: body length");
            let cut = got.iter().zip(want.iter()).position(|(a, b)| a != b);
            assert!(
                got[42..got.len() - 8] == want[42..want.len() - 8],
                "{name}: body bytes diverge (first at {cut:?})"
            );
            assert_eq!(links, saved_links, "{name}: saved Polys iLink");
        }
    }

    /// Corpus sweep vs the extracted UNATCO golden mover fixtures — dev-gated on
    /// `UEDCLI_MOVER_FIXDIR` (the goldens live in `_scratch`, not the repo); a no-op without it.
    #[test]
    fn mover_golden_sweep() {
        let Ok(dir) = std::env::var("UEDCLI_MOVER_FIXDIR") else {
            return;
        };
        let mut names: Vec<String> = std::fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| {
                let n = e.unwrap().file_name().into_string().unwrap();
                n.strip_suffix(".polys").map(str::to_string)
            })
            .collect();
        names.sort();
        let (mut pass, mut fail) = (0, 0);
        for name in &names {
            let blob = std::fs::read(format!("{dir}/{name}.polys")).unwrap();
            let want = std::fs::read(format!("{dir}/{name}.body")).unwrap();
            let (got, links, saved_links) = mover_fixture_body(&blob);
            let body_ok = got.len() == want.len()
                && got[42..got.len() - 8] == want[42..want.len() - 8];
            let links_ok = links == saved_links;
            if body_ok && links_ok {
                pass += 1;
            } else {
                fail += 1;
                let cut = got
                    .iter()
                    .zip(want.iter())
                    .position(|(a, b)| a != b)
                    .unwrap_or(got.len().min(want.len()));
                eprintln!(
                    "MOVER_DIFF {name}: body {} (got {} bytes want {}, first diff at {cut}); \
                     links {} (got {:?} want {:?})",
                    if body_ok { "ok" } else { "DIFF" },
                    got.len(),
                    want.len(),
                    if links_ok { "ok" } else { "DIFF" },
                    links,
                    saved_links
                );
            }
        }
        eprintln!("MOVER_SWEEP pass={pass} fail={fail}");
        assert_eq!(fail, 0, "{fail} mover models diverge from the golden");
    }

    /// A box brush centred at `loc`, half-extents `(hx,hy,hz)`, OUTWARD normals, CCW from outside.
    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> build::BrushInput {
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
        build::BrushInput {
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

    /// `bspAddNode` seeds a new node's `iZone`/`iLeaf` from its PARENT — the block at
    /// `Editor.dll 0x1003524a` (root/coplanar) and `0x1003535b` (front/back).  Without it every node
    /// the detail-brush layer appends AFTER `TestVisibility` reads solid/zone-0, and `PointRegion`
    /// resolves any actor under such a node into solid space (board
    /// `native-bsp-leaf-assignment-marks-2x-the-solid`).
    #[test]
    fn add_node_seeds_zone_and_leaf_from_its_parent() {
        let quad = |z: f32, up: bool| {
            let s = if up { 1.0 } else { -1.0 };
            let mut p = FPoly::new(vec![
                Vec3::new(-10.0, -10.0 * s, z),
                Vec3::new(10.0, -10.0 * s, z),
                Vec3::new(10.0, 10.0 * s, z),
                Vec3::new(-10.0, 10.0 * s, z),
            ]);
            p.normal = Vec3::new(0.0, 0.0, s);
            p.base = Vec3::new(0.0, 0.0, z);
            p
        };
        let mut m = Model::default();
        let root = bsp_add_node(&mut m, -1, NODE_ROOT, 0, &quad(0.0, true));
        assert_eq!(m.nodes[root as usize].i_leaf, [-1, -1], "NODE_Root: iLeaf = -1");
        assert_eq!(m.nodes[root as usize].i_zone, [0, 0], "NODE_Root: iZone = 0");

        // Stand in for what Pass A/D leave on the parent: distinct per-side leaf and zone.
        m.nodes[root as usize].i_leaf = [7, 9];
        m.nodes[root as usize].i_zone = [3, 5];

        // FRONT/BACK: BOTH of the child's sides take the parent's own side (index == ENodePlace).
        let front = bsp_add_node(&mut m, root, NODE_FRONT, 0, &quad(1.0, true));
        assert_eq!(m.nodes[front as usize].i_leaf, [9, 9]);
        assert_eq!(m.nodes[front as usize].i_zone, [5, 5]);
        let back = bsp_add_node(&mut m, root, NODE_BACK, 0, &quad(-1.0, true));
        assert_eq!(m.nodes[back as usize].i_leaf, [7, 7]);
        assert_eq!(m.nodes[back as usize].i_zone, [3, 3]);

        // COPLANAR, same facing: straight copy of both sides.
        let cop = bsp_add_node(&mut m, root, NODE_PLANE, 0, &quad(0.0, true));
        assert_eq!(m.nodes[cop as usize].i_leaf, [7, 9]);
        assert_eq!(m.nodes[cop as usize].i_zone, [3, 5]);
        // COPLANAR, opposite facing: sides SWAP (the 4-component FPlane dot goes negative).  It
        // chains off the previous coplanar member, which is the one it inherits from.
        let flip = bsp_add_node(&mut m, root, NODE_PLANE, 0, &quad(0.0, false));
        assert_eq!(m.nodes[flip as usize].i_leaf, [9, 7]);
        assert_eq!(m.nodes[flip as usize].i_zone, [5, 3]);
    }

    /// `bspAddNode`'s post-loop wrap trim [DISASM Editor.dll 0x100353a1-0x100353b8]: a ring whose
    /// authored LAST vertex duplicates its FIRST (consecutive-only dedup above doesn't catch this,
    /// since the dupes aren't adjacent in the loop) loses that redundant closing vertex from the
    /// reported count -- but the vert-pool array itself is left as-is (not popped), so a SECOND
    /// node added right after keeps the real editor's `i_vert_pool` offset (one past every pushed
    /// slot, trimmed one included).
    #[test]
    fn add_node_drops_a_wrap_duplicate_closing_vertex_from_the_count_not_the_pool() {
        let mut p = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
            Vec3::new(0.0, 0.0, 0.0), // closes the ring back onto the first vertex
        ]);
        p.normal = Vec3::new(0.0, 0.0, 1.0);
        let mut m = Model::default();
        let root = bsp_add_node(&mut m, -1, NODE_ROOT, 0, &p);
        assert_eq!(
            m.nodes[root as usize].num_vertices, 4,
            "the redundant closing vertex must not be counted"
        );
        assert_eq!(m.verts.len(), 5, "the pool itself keeps all 5 pushed slots, not popped");

        // A second node added right after must start its own pool region past ALL 5 slots (the
        // real editor's own over-allocate-then-undercount behavior), not past only the 4 counted.
        let mut q = FPoly::new(vec![
            Vec3::new(100.0, 0.0, 0.0),
            Vec3::new(110.0, 0.0, 0.0),
            Vec3::new(110.0, 10.0, 0.0),
        ]);
        q.normal = Vec3::new(0.0, 0.0, 1.0);
        bsp_add_node(&mut m, root, NODE_FRONT, 0, &q);
        assert_eq!(m.nodes[root as usize + 1].i_vert_pool, 5);
    }

    /// `bspAddNode`'s "Infinitesimal polygon" guard [DISASM 0x100353bb-0x100353eb]: if the wrap
    /// trim above leaves fewer than 3 vertices, the real editor reports `NumVertices=0` rather
    /// than a genuine 1/2-vertex sliver.
    #[test]
    fn add_node_reports_zero_vertices_for_a_degenerate_post_trim_result() {
        let mut p = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(0.0, 0.0, 0.0), // wrap trim leaves only 1 distinct vertex
        ]);
        p.normal = Vec3::new(0.0, 0.0, 1.0);
        let mut m = Model::default();
        let root = bsp_add_node(&mut m, -1, NODE_ROOT, 0, &p);
        assert_eq!(m.nodes[root as usize].num_vertices, 0);
    }

    /// Descent solidity on the FINAL (engine-convention) model: solid iff the region resolves to
    /// zone 0 (no empty leaf).
    fn model_solid(m: &Model, p: Vec3) -> bool {
        if m.nodes.is_empty() {
            return true;
        }
        let mut ni = 0i32;
        for _ in 0..4096 {
            let n = &m.nodes[ni as usize];
            let pd = n.plane.x * p.x + n.plane.y * p.y + n.plane.z * p.z - n.plane.w;
            let (child, side) = if pd >= 0.0 {
                (n.i_back, 1)
            } else {
                (n.i_front, 0)
            };
            if child == -1 {
                let lf = n.i_leaf[side];
                if lf >= 0 && (lf as usize) < m.leaves.len() {
                    return m.leaves[lf as usize].i_zone == 0;
                }
                return true;
            }
            ni = child;
        }
        true
    }

    #[test]
    fn candidate_scan_reaches_past_a_structural_poly_inside_its_slot() {
        // 40 parallel YZ quads, so no candidate ever splits another and the score is 12*|F-B|.
        // GOOD stride = 40/20 = 2, so the candidate slots are [0,2), [2,4), … and only the
        // even indices are slot boundaries.  Poly 21 sits at x=19 — the median of the 20
        // even-indexed polys the inner loop samples — so it alone scores 0; every even
        // candidate is excluded from its own sample and so scores at least 12.  Poly 20, its
        // slot's boundary, is NotSolid (`0x08`) and therefore skipped as a candidate: reaching
        // poly 21 requires scanning forward INSIDE slot 10 (`Editor.dll 0x33760 je 0x33734`).
        // Stepping to the next slot on a skip instead picks an even index.
        let quad = |x: f32| {
            let mut p = FPoly::new(vec![
                Vec3::new(x, -10.0, -10.0),
                Vec3::new(x, 10.0, -10.0),
                Vec3::new(x, 10.0, 10.0),
                Vec3::new(x, -10.0, 10.0),
            ]);
            p.normal = Vec3::new(1.0, 0.0, 0.0);
            p.base = Vec3::new(x, 0.0, 0.0);
            p
        };
        let mut polys: Vec<FPoly> = (0..40).map(|i| quad(i as f32)).collect();
        polys.swap(19, 21); // put the median plane x=19 at an ODD index, off every slot boundary
        polys[20].poly_flags = 0x08;
        assert_eq!(find_best_split_exact(&polys, 12, 0, Opt::Good), 21);

        // The pre-pass tests the `0x28` mask alone: with every poly structural, `all_structural`
        // holds even though one is a portal, so all 40 are eligible again and the winner returns
        // to the score-12 tie at the earliest slot boundary.  Conjoining "not a portal" into the
        // pre-pass would leave only the portal eligible.
        for p in polys.iter_mut() {
            p.poly_flags = 0x08;
        }
        polys[30].poly_flags = 0x08 | csg::PF_PORTAL;
        assert_eq!(find_best_split_exact(&polys, 12, 0, Opt::Good), 18);
    }

    /// §92 §30 SEED FIX regression — the unit changed is `bsp_filter_fpoly`'s empty-tree branch.
    /// The FIRST brush filtered into the EMPTY solid world (RootOutside=0) is SEEDED as a root node,
    /// NOT filter-classified. Before the fix a leading CSG_Add was classified F_INSIDE and
    /// `AddBrushToWorldFunc` (emits ONLY on F_OUTSIDE) DROPPED all its faces — `build([Brush74]) == 0
    /// nodes`, the UNATCO byte-cascade root (§92 §26/§30). A leading CSG_Subtract was already retained
    /// (Subtract emits on F_INSIDE, storing the face Reverse()d) and MUST stay byte-identical.
    #[test]
    fn first_poly_on_empty_world_is_seeded_as_root_node() {
        // A single upward face (outward normal +Z).
        let mk = || {
            let mut p = FPoly::new(vec![
                Vec3::new(-64.0, -64.0, 0.0),
                Vec3::new(64.0, -64.0, 0.0),
                Vec3::new(64.0, 64.0, 0.0),
                Vec3::new(-64.0, 64.0, 0.0),
            ]);
            p.normal = Vec3::new(0.0, 0.0, 1.0);
            p
        };

        // CRITICAL: mirror the real build's `root_outside = false` (set at bspcsg.rs:1853 before the
        // first `bsp_brush_csg`).  `Model::default()` sets `root_outside = TRUE`, at which the OLD
        // buggy code ALSO retained the Add (true → F_OUTSIDE) — so a Default-based test is a FALSE
        // GREEN (cold-review finding 1).  The bug (and this fix) only manifest at `root_outside=false`,
        // the DX solid world, where old code → F_INSIDE → Add DROPPED (0 nodes).

        // Leading CSG_Add: RETAINED as a root node (regression — was dropped -> 0 nodes at RO=false).
        let mut ma = Model::default();
        ma.root_outside = false; // DX solid world — the condition the real build + the bug use.
        bsp_filter_fpoly(&mut ma, LeafFunc::Add, &mk(), &mut Vec::new());
        assert_eq!(ma.nodes.len(), 1, "leading Add poly must SEED a root node (was 0 — dropped)");
        assert!(
            (ma.nodes[0].plane.z - 1.0).abs() < 1e-6,
            "Add seeds the OUTWARD normal (no Reverse): {:?}",
            ma.nodes[0].plane
        );
        assert!(ma.nodes[0].node_flags & NF_IS_NEW != 0, "seed carries NF_IsNew");

        // Leading CSG_Subtract at RO=false: UNCHANGED by the fix — one root node, stored INWARD (Rev)d.
        let mut ms = Model::default();
        ms.root_outside = false;
        bsp_filter_fpoly(&mut ms, LeafFunc::Subtract, &mk(), &mut Vec::new());
        assert_eq!(ms.nodes.len(), 1, "leading Subtract poly still seeds its root node");
        assert!(
            (ms.nodes[0].plane.z + 1.0).abs() < 1e-6,
            "Subtract seeds the Reverse()d (inward) normal: {:?}",
            ms.nodes[0].plane
        );
    }

    /// §92 §32 CONVEX SEED regression — the unit changed is `bsp_brush_csg`'s LOOP-2 for a leading
    /// CSG_Add into the EMPTY solid world (`root_outside=false`). The editor seeds the whole convex
    /// brush as world-tree ROOT nodes (a `NODE_ROOT` + `NODE_FRONT` chain, faces stored INWARD /
    /// `Reverse`d — oracle §26 block 0), keeping RootOutside=0. Before this fix the per-poly filter
    /// kept only ONE of a leading Add box's six faces (face 0 seeds a non-CSG 1-node tree, faces 1-5
    /// reach an F_INSIDE leaf → the Add func drops them). Now all six are retained; a leading Subtract
    /// is unaffected (it never takes the convex-seed branch — castle byte-exact gate).
    #[test]
    fn leading_add_box_seeds_convex_front_chain_inward() {
        // TRANSLATED box (centre far from origin) so the inwardness check genuinely tests the
        // Reverse() — a `plane.w < 0` proxy would pass spuriously only for an origin-centred box.
        let centre = Vec3::new(1000.0, 500.0, -300.0);
        let box_b = box_brush(128.0, 64.0, 32.0, centre, CsgOper::Add);
        let mut m = Model::default();
        m.root_outside = false; // DX solid world — the real build's seed condition.
        bsp_brush_csg(&mut m, &box_b, 0, box_b.poly_flags);

        // All six faces retained (was 1 before §32; 0 before §31) as a convex seed.
        assert_eq!(m.nodes.len(), 6, "leading Add box must seed all 6 faces (was 1)");
        assert_eq!(m.surfs.len(), 6, "six distinct surfs, one per face");
        // Root topology: node0 is a NODE_ROOT (no back child); node i is the FRONT child of node i-1.
        assert_eq!(m.nodes[0].i_back, -1, "seed root (NODE_ROOT) has no back child");
        for i in 0..5 {
            assert_eq!(
                m.nodes[i].i_front,
                (i + 1) as i32,
                "seed must be a NODE_FRONT chain (node {i}.iFront == {})",
                i + 1
            );
        }
        // Faces stored INWARD-facing (Reverse()d): each seed plane normal points TOWARD the brush
        // centroid — `normal · (centroid − base) > 0`.  This holds regardless of the box's location,
        // so (unlike `plane.w < 0`) it actually exercises the Reverse().
        for (i, n) in m.nodes.iter().enumerate() {
            let base = m.points[m.surfs[n.i_surf as usize].p_base as usize];
            let nrm = Vec3::new(n.plane.x, n.plane.y, n.plane.z);
            assert!(
                nrm.dot(&centre.sub(&base)) > 0.0,
                "seed face {i} normal must point INWARD toward the centroid: {:?}",
                n.plane
            );
            assert_eq!(n.node_flags & NF_IS_NEW, 0, "bsp_cleanup clears NF_IsNew on the seed");
        }

        // GATE NEGATIVE 1 — the CONVEX SEED, not per-poly filtering, is what retains all 6 faces.
        // Drive the SAME box's faces through `bsp_filter_fpoly` per poly (exactly what the pre-§32
        // code did, and what a leading Add would do WITHOUT the seed): face 0 seeds a 1-node NF_IsNew
        // tree, faces 1-5 reach an F_INSIDE leaf and the Add func drops them → only 1 survives.  So the
        // seed branch (gated to a leading Add) is load-bearing.  A leading SUBTRACT deliberately keeps
        // this per-poly filter path (`first_add_seed` is gated on `oper == Add`); its byte-exactness is
        // covered by the castle gate (castle's first brush `World_7e9y81` is a Subtract).
        let local = box_brush(64.0, 64.0, 64.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add);
        let mut mf = Model::default();
        mf.root_outside = false;
        for face in &local.polys {
            let mut p = face.clone();
            let _ = p.finalize();
            bsp_filter_fpoly(&mut mf, LeafFunc::Add, &p, &mut Vec::new());
        }
        assert_eq!(
            mf.nodes.len(),
            1,
            "per-poly filter of a leading Add keeps only 1 face — the convex SEED keeps all 6"
        );

        // GATE NEGATIVE 2 — a NON-EMPTY world does NOT re-seed: a second Add brush filters into the
        // existing tree instead of laying down a fresh 6-node NODE_FRONT chain (which would make the
        // total 12).  `first_add_seed` is gated on `model.nodes.is_empty()`.
        let box2 = box_brush(64.0, 64.0, 64.0, Vec3::new(1032.0, 500.0, -300.0), CsgOper::Add);
        let before = m.nodes.len();
        let root0 = m.nodes[0].plane;
        bsp_brush_csg(&mut m, &box2, 1, box2.poly_flags);
        assert_ne!(
            m.nodes.len(),
            before + 6,
            "second Add on a non-empty world must NOT lay a fresh 6-node convex seed"
        );
        let r = m.nodes[0].plane;
        assert!(
            (r.x - root0.x).abs() < 1e-6
                && (r.y - root0.y).abs() < 1e-6
                && (r.z - root0.z).abs() < 1e-6
                && (r.w - root0.w).abs() < 1e-6,
            "the first brush's root node stays the tree root"
        );
    }

    #[test]
    fn single_subtract_carves_a_void_room_with_inward_walls() {
        let brushes = [box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];
        let m = build_geometry_bspcsg(&brushes).unwrap();
        assert_eq!(m.surfs.len(), 6, "single subtract -> 6 walls");
        // interior is void, well outside is solid.
        assert!(
            !model_solid(&m, Vec3::new(0.0, 0.0, 0.0)),
            "room interior must be void"
        );
        assert!(
            model_solid(&m, Vec3::new(1000.0, 0.0, 0.0)),
            "far exterior must be solid"
        );
        // every wall normal points INWARD (toward the room centre at origin): base·normal < 0.
        for s in &m.surfs {
            let n = m.vectors[s.v_normal as usize];
            let b = m.points[s.p_base as usize];
            assert!(
                n.dot(&b) < 0.0,
                "wall normal must point inward (offset {})",
                n.dot(&b)
            );
        }
    }

    /// A LONE `CsgOper::Active` brush (T3D's absent-`CsgOper=` class default, ordinal 0) builds
    /// IDENTICALLY to a lone `CsgOper::Subtract`: pass 1 is Subtract-shaped (`0x10035688`/
    /// `0x10035a84`-`0x95`, Subtract unless a literal `CsgOper==1`), and the two ops' remaining
    /// differences — no world cut (`0x100333dd`), no tail `bspCleanup` (`0x10035dcd`) — are
    /// invisible with no prior world and no following brush.  Pins the ORIGINAL fix for
    /// `vandenberg-gas-csg-active-csgoper-brush-causes`: an early `bsp_brush_csg` guard used to
    /// silently no-op any oper that wasn't literally Add or Subtract, which would have shipped the
    /// ALREADY-REFUTED "skip the brush" hypothesis (live A/B/C build "A").  Where Active DOES
    /// diverge from Subtract — brush interactions — is pinned by
    /// `active_led_pair_keeps_buried_faces_uncut` below.
    #[test]
    fn csg_active_dispatches_exactly_like_subtract() {
        let geom = (256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0));
        let subtract = build_geometry_bspcsg(&[box_brush(
            geom.0, geom.1, geom.2, geom.3, CsgOper::Subtract,
        )])
        .unwrap();
        let active = build_geometry_bspcsg(&[box_brush(
            geom.0, geom.1, geom.2, geom.3, CsgOper::Active,
        )])
        .unwrap();

        // Not the "skip the brush" no-op (build A of the live test): a skipped brush leaves an
        // EMPTY world (no nodes/surfs at all), not a 6-wall carved room.
        assert_eq!(active.surfs.len(), 6, "Active must carve exactly like Subtract, not no-op");
        assert_eq!(active.nodes.len(), subtract.nodes.len());
        assert_eq!(active.surfs.len(), subtract.surfs.len());
        assert_eq!(active.verts.len(), subtract.verts.len());
        assert_eq!(active.points.len(), subtract.points.len());
        assert_eq!(active.vectors.len(), subtract.vectors.len());
        for (a, s) in active.surfs.iter().zip(subtract.surfs.iter()) {
            let an = active.vectors[a.v_normal as usize];
            let sn = subtract.vectors[s.v_normal as usize];
            assert!(
                (an.x - sn.x).abs() < 1e-6 && (an.y - sn.y).abs() < 1e-6 && (an.z - sn.z).abs() < 1e-6,
                "Active and Subtract must carve the identical surf normals"
            );
        }
    }

    /// The Paris Underground 2-brush minimal case (spike `2026-09-03-built-parity-worst-tier`;
    /// Active-led editor golden pinned in its committed `pu-prefix-search.log` n=2 line, the
    /// explicit-Subtract golden by `pu_two_subtract_golden.py`, recorded in `spike.md` and the
    /// board item): `Brush1246` — the
    /// level's `CsgOper`-ABSENT (= Active) first brush, a default 256-cube at the origin — followed
    /// by `Brush328`, a plain 6-poly `CSG_Subtract` box overlapping most of the cube.  Fixture
    /// geometry below is the two brushes' authored T3D (face order, windings, `Location`) verbatim.
    ///
    /// Editor, as authored (Active-led):        16 nodes / 12 surfs / 6 leaves
    /// Editor, `Brush1246` -> explicit Subtract: 14 nodes / 11 surfs / 2 leaves
    ///
    /// The Active brush skips its tail `bspCleanup` (`0x10035dcd`: literal `CsgOper==1||==2`), so
    /// its nodes stay `NF_IsNew` through `Brush328`'s op: `Brush328`'s descent classifies against
    /// the PRE-Active (all-solid) world (`IsCsg` masks NF_IsNew) — keeping its floor over the cube
    /// footprint — and its world cut skips the flagged subtree (`0x100332d4`) — keeping the cube's
    /// ceiling and full-height walls un-cut.  Before this fix native built BOTH variants 14/11/2.
    #[test]
    fn active_led_pair_keeps_buried_faces_uncut() {
        // Authored face order/windings: Brush1246 = +z, -z, +y, -y, +x, -x; Brush328 (local coords,
        // Location (368,-576,112)) = +z, -z, -y, +y, -x, +x.
        let quad = |n: (f32, f32, f32), v: [(f32, f32, f32); 4]| {
            let mut p = FPoly::new(v.iter().map(|&(x, y, z)| Vec3::new(x, y, z)).collect());
            p.normal = Vec3::new(n.0, n.1, n.2);
            p
        };
        let brush = |polys: Vec<FPoly>, oper: CsgOper, loc: Vec3| build::BrushInput {
            polys,
            oper,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        };
        let cube = |oper: CsgOper| {
            let s = 128.0;
            brush(
                vec![
                    quad((0., 0., 1.), [(-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)]),
                    quad((0., 0., -1.), [(-s, s, -s), (s, s, -s), (s, -s, -s), (-s, -s, -s)]),
                    quad((0., 1., 0.), [(-s, s, -s), (-s, s, s), (s, s, s), (s, s, -s)]),
                    quad((0., -1., 0.), [(s, -s, -s), (s, -s, s), (-s, -s, s), (-s, -s, -s)]),
                    quad((1., 0., 0.), [(s, s, -s), (s, s, s), (s, -s, s), (s, -s, -s)]),
                    quad((-1., 0., 0.), [(-s, -s, -s), (-s, -s, s), (-s, s, s), (-s, s, -s)]),
                ],
                oper,
                Vec3::new(0.0, 0.0, 0.0),
            )
        };
        let brush328 = || {
            let (x, y, z) = (672.0, 832.0, 176.0);
            brush(
                vec![
                    quad((0., 0., 1.), [(x, y, z), (-x, y, z), (-x, -y, z), (x, -y, z)]),
                    quad((0., 0., -1.), [(x, -y, -z), (-x, -y, -z), (-x, y, -z), (x, y, -z)]),
                    quad((0., -1., 0.), [(x, -y, -z), (x, -y, z), (-x, -y, z), (-x, -y, -z)]),
                    quad((0., 1., 0.), [(-x, y, -z), (-x, y, z), (x, y, z), (x, y, -z)]),
                    quad((-1., 0., 0.), [(-x, -y, -z), (-x, -y, z), (-x, y, z), (-x, y, -z)]),
                    quad((1., 0., 0.), [(x, y, -z), (x, y, z), (x, -y, z), (x, -y, -z)]),
                ],
                CsgOper::Subtract,
                Vec3::new(368.0, -576.0, 112.0),
            )
        };

        let active_led =
            build_geometry_bspcsg(&[cube(CsgOper::Active), brush328()]).unwrap();
        assert_eq!(
            (active_led.nodes.len(), active_led.surfs.len(), active_led.leaves.len()),
            (16, 12, 6),
            "Active-led pair must match the live editor golden 16/12/6"
        );

        let subtract_led =
            build_geometry_bspcsg(&[cube(CsgOper::Subtract), brush328()]).unwrap();
        assert_eq!(
            (subtract_led.nodes.len(), subtract_led.surfs.len(), subtract_led.leaves.len()),
            (14, 11, 2),
            "explicit-Subtract-led pair must match the live editor golden 14/11/2"
        );
    }

    /// `bspValidateBrush` coplanar-link (Editor.dll 0x37290; §92 stage-2, spec
    /// board item `92-stage-2-done`): coplanar, same-normal, same-texture,
    /// same-axes, same-flags faces of ONE brush link to a single surf (`links[j] = i`, `i < j`);
    /// a plain box (six DISTINCT normals) links nothing.  This is the dome-cap fix: N `(0,0,1)`
    /// facets at one z collapse to one surf (native kept 9, editor kept 1 — §92 §9 pin).
    #[test]
    fn validate_brush_links_fuses_coplanar_same_facing_faces() {
        // A plain box: 6 distinct normals, no coplanar same-normal pair -> every face its own surf.
        let box_b = box_brush(128.0, 128.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add);
        let box_links = bsp_validate_brush_links(&box_b.polys);
        for (i, &l) in box_links.iter().enumerate() {
            assert_eq!(l, i as i32, "box face {i} has no coplanar sibling -> its own surf");
        }

        // Dome-cap stand-in: 3 coplanar facets at z=+64, normal (0,0,1), identical texture/axes/flags.
        let mk_cap = |cx: f32, cy: f32| {
            let z = 64.0;
            let mut p = FPoly::new(vec![
                Vec3::new(cx - 8.0, cy - 8.0, z),
                Vec3::new(cx + 8.0, cy - 8.0, z),
                Vec3::new(cx + 8.0, cy + 8.0, z),
                Vec3::new(cx - 8.0, cy + 8.0, z),
            ]);
            p.normal = Vec3::new(0.0, 0.0, 1.0);
            p.texture_u = Vec3::new(1.0, 0.0, 0.0);
            p.texture_v = Vec3::new(0.0, 1.0, 0.0);
            p
        };
        let cap = vec![mk_cap(0.0, 0.0), mk_cap(24.0, 0.0), mk_cap(0.0, 24.0)];
        assert_eq!(
            bsp_validate_brush_links(&cap),
            vec![0, 0, 0],
            "3 coplanar same-facing cap facets must share one surf"
        );

        // Faithful exact-axis gate: differing TextureU breaks the link (facet 2 keeps its own surf).
        let mut cap2 = cap.clone();
        cap2[2].texture_u = Vec3::new(0.0, 0.0, 1.0);
        assert_eq!(
            bsp_validate_brush_links(&cap2),
            vec![0, 0, 2],
            "differing texture axes must NOT link (exact-axis gate)"
        );
    }

    /// OceanLab Lab finding (2026-09-01, `native-materialize-findings.md` "OceanLab Lab +27 surf
    /// over-build"): the coplanarity gate must use each poly's own AUTHORED `Base` (T3D `Origin=`),
    /// not `verts[0]`.  Real T3D-authored geometry (a "2D Loft" BrushBuilder shape, 9 instances in
    /// OceanLab Lab) carries a few thousandths of a unit of construction noise BETWEEN a face's own
    /// vertices — large enough to push a `verts[0]`-based coplanarity check outside the ±0.001 band
    /// on some pairs of an otherwise-flat cap while the SAME faces' authored `Origin` sits exactly
    /// on the intended plane (0 delta).  Live-verified: an isolated context golden (real editor,
    /// `dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/oceanlab_isolate_golden.py`) of
    /// `Brush784` groups its 26 authored polys into 18 surfs; a `verts[0]`-based gate gave 21
    /// (missed 3 real merges), the authored-`Base` gate gives 18 exactly.
    #[test]
    fn validate_brush_links_uses_authored_base_not_verts0() {
        // Two coplanar (0,0,1) quads whose OWN vertices carry ~0.002 uu of noise (so a `verts[0]`
        // coplanarity check reads a ~0.002 plane offset, outside the ±0.001 band), but whose
        // AUTHORED `Base` (T3D `Origin=`) is exactly on the shared z=64 plane on both.
        let mk_noisy = |cx: f32, z_noise: f32| {
            let z = 64.0 + z_noise;
            let mut p = FPoly::new(vec![
                Vec3::new(cx - 8.0, -8.0, z),
                Vec3::new(cx + 8.0, -8.0, z),
                Vec3::new(cx + 8.0, 8.0, z),
                Vec3::new(cx - 8.0, 8.0, z),
            ]);
            p.normal = Vec3::new(0.0, 0.0, 1.0);
            p.texture_u = Vec3::new(1.0, 0.0, 0.0);
            p.texture_v = Vec3::new(0.0, 1.0, 0.0);
            p.base = Vec3::new(cx, 0.0, 64.0); // authored Origin: exactly on the true plane
            p
        };
        let noisy = vec![mk_noisy(0.0, 0.002), mk_noisy(24.0, -0.0005)];
        assert_eq!(
            bsp_validate_brush_links(&noisy),
            vec![0, 0],
            "authored Base (on-plane) must link two faces whose own noisy verts[0] would not"
        );
    }

    #[test]
    fn repartition_splits_ge14_vert_fragment_in_half() {
        // Editor `SplitPolyList` (0x34716/0x3475f): a Split fragment with `NumVertices >= 14` is
        // `SplitInHalf`'d and BOTH halves stay in the SAME child list — so it becomes TWO coplanar
        // nodes, not one.  Native's repartition `split_poly_list` previously OMITTED this (present
        // only in the CSG-filter paths).  This pins the fact against a hand-built straddle.
        //
        // A = an x=0 quad (normal +x); B = a 16-gon in the z=0 plane centred front of x=0, so the
        // splitter A cuts B into a >=14-vert FRONT fragment and a small back fragment.  A wins the
        // root (tie-break lowest index).  WITH SplitInHalf the front fragment becomes two coplanar
        // half-nodes -> 3 nodes lie on B's z=0 plane (2 front halves + 1 back); WITHOUT it, 2.
        let mut a = FPoly::new(vec![
            Vec3::new(0.0, -200.0, -10.0),
            Vec3::new(0.0, 200.0, -10.0),
            Vec3::new(0.0, 200.0, 10.0),
            Vec3::new(0.0, -200.0, 10.0),
        ]);
        a.finalize().unwrap();

        let n = 16;
        let (cx, r) = (50.0_f32, 60.0_f32);
        let mut verts = Vec::new();
        for i in 0..n {
            let t = (i as f32) * std::f32::consts::TAU / (n as f32);
            verts.push(Vec3::new(cx + r * t.cos(), r * t.sin(), 0.0));
        }
        let mut b = FPoly::new(verts);
        b.finalize().unwrap();

        let mut model = Model::default();
        split_poly_list(
            &mut model,
            -1,
            NODE_ROOT,
            vec![a, b],
            0,
            BALANCE,
            PORTAL_BIAS,
            Opt::Good,
            &mut 0,
            None,
        )
        .unwrap();

        let on_b_plane = model
            .nodes
            .iter()
            .filter(|nd| nd.plane.z.abs() > 0.999)
            .count();
        assert_eq!(
            on_b_plane, 3,
            "a >=14-vert repartition front fragment must SplitInHalf into two coplanar nodes (got {on_b_plane})"
        );
    }

    #[test]
    fn merge_coplanars_rescans_a_poly_already_claimed_by_an_earlier_group() {
        // `bspMergeCoplanars` (`0x36200`): the candidate (`j`) scan tests iLink/coplanar/normal/UV
        // unconditionally and does NOT skip a poly already pulled into an earlier anchor's group —
        // only the OUTER anchor role is skip-gated on the "grouped" flag. So the SAME poly can be a
        // candidate for more than one anchor if the group predicate (in particular, the epsilon-ball
        // texture-UV-near test) is not transitive: A and D can each be "near enough" to B without
        // being near enough to EACH OTHER.
        //
        // A (far away, non-adjacent) and D (edge-adjacent to B) both share B's iLink/plane/normal.
        // textureU: A=0, D=7e-4, B=3.5e-4 -> |A-D|=7e-4 fails the 4e-4 gate (A and D never group
        // together) but |A-B|=3.5e-4 and |D-B|=3.5e-4 both pass, so B is a valid candidate for BOTH
        // A's group and D's group. B only actually shares an edge with D. A pre-fix build skips B
        // when D's turn comes (already flagged from A's group), so D never merges with B at all.
        let mut a = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
        ]);
        a.finalize().unwrap();
        a.i_link = 5;
        a.texture_u = Vec3::new(0.0, 0.0, 0.0);

        let mut d = FPoly::new(vec![
            Vec3::new(20.0, 0.0, 0.0),
            Vec3::new(30.0, 0.0, 0.0),
            Vec3::new(30.0, 10.0, 0.0),
            Vec3::new(20.0, 10.0, 0.0),
        ]);
        d.finalize().unwrap();
        d.i_link = 5;
        d.texture_u = Vec3::new(0.0007, 0.0, 0.0);

        let mut b = FPoly::new(vec![
            Vec3::new(30.0, 0.0, 0.0),
            Vec3::new(40.0, 0.0, 0.0),
            Vec3::new(40.0, 10.0, 0.0),
            Vec3::new(30.0, 10.0, 0.0),
        ]);
        b.finalize().unwrap();
        b.i_link = 5;
        b.texture_u = Vec3::new(0.00035, 0.0, 0.0);

        let out = bsp_merge_coplanars(vec![a, d, b]);

        assert_eq!(
            out.len(),
            2,
            "D and B share an edge and must fuse into one poly, leaving A separate (got {} polys)",
            out.len()
        );
        // D+B are two same-size axis-aligned quads sharing a full edge: the fused ring's two
        // seam midpoints are exactly colinear with their neighbours, so RemoveColinears thins the
        // 6-point splice back down to the resulting rectangle's 4 real corners.
        let fused = out.iter().find(|p| p.verts.len() == 4 && p.base.x > 15.0);
        assert!(
            fused.is_some(),
            "expected D+B fused into one 4-vertex rectangle (20,0)-(40,10); got {:?}",
            out.iter().map(|p| p.verts.len()).collect::<Vec<_>>()
        );
    }

    #[test]
    fn try_to_merge_step3_fuses_a_fractional_brush_seam_gap() {
        // Wanchai +2/+20: Brush754's PostScale Y=4.499965 puts a genuine fractional face plane at
        // world y=-768.00439, so two coplanar same-face fragments of one door face meet at a shared
        // edge whose corners differ by 0.00439 (SAME 0.002 box rejects, NEAR 0.015 accepts). The
        // editor fuses them into one polygon; native kept both while step 3 used the SAME threshold.
        // Step 3 now uses NEAR, so the seam-gap pair fuses and matches the editor.
        let mut a = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
        ]);
        a.finalize().unwrap();
        a.i_link = 3139;
        a.texture_u = Vec3::new(0.0, 0.0, 0.0);
        a.texture_v = Vec3::new(0.0, 0.0, 0.0);

        // Right quad, one shared-edge corner 0.00439 out of register (B[3]=y=10.00439 vs A[2]=y=10).
        let mut b = FPoly::new(vec![
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(20.0, 0.0, 0.0),
            Vec3::new(20.0, 10.0, 0.0),
            Vec3::new(10.0, 10.00439, 0.0),
        ]);
        b.finalize().unwrap();
        b.i_link = 3139;
        b.texture_u = Vec3::new(0.0, 0.0, 0.0);
        b.texture_v = Vec3::new(0.0, 0.0, 0.0);

        let fused = try_to_merge(&a, &b).expect("0.00439 seam gap must fuse under the NEAR step-3 test");

        // Fuses back to the 4-corner rectangle spanning (0,0)-(20,10) after RemoveColinears thins
        // the shared-edge seam vertices.
        assert!(
            fused.verts.len() == 4,
            "fused poly should be a 4-vertex rectangle; got {} verts: {:?}",
            fused.verts.len(),
            fused.verts
        );
        for v in [
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(20.0, 0.0, 0.0),
            Vec3::new(20.0, 10.0, 0.0),
            Vec3::new(0.0, 10.0, 0.0),
        ] {
            assert!(
                fused.verts.iter().any(|p| p.sub(&v).size() < 1e-3),
                "missing expected corner {:?}; got {:?}",
                v,
                fused.verts
            );
        }
    }

    #[test]
    fn abutting_subtracts_annihilate_the_shared_wall() {
        // Two cube subtracts sharing the x=0 plane -> the shared wall is cut away (no surf at x=0).
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
        let m = build_geometry_bspcsg(&brushes).unwrap();
        // a point on the shared plane, mid-room, must be VOID (the wall was annihilated).
        assert!(
            !model_solid(&m, Vec3::new(0.0, 0.0, 0.0)),
            "merged room interior at x=0 must be void"
        );
    }

    /// A right-triangular-prism (wedge) whose single slanted face carries an AUTHORED normal a few
    /// ULP off its winding `CalcNormal`.  `oper` picks Add vs Subtract; `slant_authored` is stamped
    /// on the slant face.
    fn wedge_brush(oper: CsgOper, slant_authored: Vec3) -> build::BrushInput {
        // Vertices (x,y,z): bottom rect A,B,C,D at z=-64; top edge E,F at x=-128,z=+64.
        let a = Vec3::new(-128.0, -64.0, -64.0);
        let b = Vec3::new(128.0, -64.0, -64.0);
        let c = Vec3::new(128.0, 64.0, -64.0);
        let d = Vec3::new(-128.0, 64.0, -64.0);
        let e = Vec3::new(-128.0, -64.0, 64.0);
        let f = Vec3::new(-128.0, 64.0, 64.0);
        // (outward normal, CCW-from-outside winding)
        let faces: [(Vec3, Vec<Vec3>); 5] = [
            (Vec3::new(0.0, 0.0, -1.0), vec![a, d, c, b]), // bottom  z=-64
            (Vec3::new(-1.0, 0.0, 0.0), vec![a, e, f, d]), // back    x=-128
            (slant_authored, vec![b, c, f, e]),            // SLANT   +x+z (non-axis)
            (Vec3::new(0.0, 1.0, 0.0), vec![d, f, c]),     // end     y=+64
            (Vec3::new(0.0, -1.0, 0.0), vec![a, b, e]),    // end     y=-64
        ];
        let mut polys = Vec::new();
        for (n, verts) in faces {
            let mut p = FPoly::new(verts);
            p.normal = n;
            polys.push(p);
        }
        build::BrushInput {
            polys,
            oper,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: Vec3::new(0.0, 0.0, 0.0),
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        }
    }

    #[test]
    fn every_face_normal_is_sns_of_local_calcnormal_authored_ignored() {
        // The uniform normal rule (2026-09-03 Vandenberg first-divergent-brush round, replacing §92
        // §48's Subtract-only split): the importer stores CalcNormal(local) over the authored
        // normal (live golden bytes: Vandenberg Brush41 Polys stores bf75341a/3e931f43 = CalcNormal
        // while the authored text parses to bf753416/3e931f47), and `FPoly::Transform` re-normalizes
        // with SafeNormalSlow on EVERY poly (§92 §52).  So Add and Subtract BOTH store
        // `safe_normal_slow(CalcNormal(local))`; a perturbed authored normal is ignored for both.
        let mut probe = FPoly::new(vec![
            Vec3::new(128.0, -64.0, -64.0),
            Vec3::new(128.0, 64.0, -64.0),
            Vec3::new(-128.0, 64.0, 64.0),
            Vec3::new(-128.0, -64.0, 64.0),
        ]);
        assert!(probe.calc_normal());
        let calc = probe.normal; // the winding CalcNormal (once-normalized by NormalizeSlow)
        // §92 §52: the editor's `FPoly::Transform` applies a SECOND `SafeNormalSlow` on top of
        // `CalcNormal`, so a SUBTRACT face stores `safe_normal_slow(calc)`, ~1-2 ULP off `calc`
        // (this is the dome twin: paste CalcNormal OUTPUT == native `calc_normal` byte-for-byte —
        // live gdb 78/78 — but the golden stores the re-normalized value; MAP REBUILD itself calls
        // CalcNormal ZERO times, so the twin is this transform re-normalization, not a vertex pool).
        let stored = safe_normal_slow(&calc).expect("renormalizable");
        // Perturb the authored normal by +16 ULP on x (kept unit-ish; dot stays > 0.9999).
        let nudged_x = f32::from_bits(calc.x.to_bits() + 16);
        let authored = Vec3::new(nudged_x, calc.y, calc.z);
        assert_ne!(authored.x.to_bits(), calc.x.to_bits(), "fixture must perturb");

        let is_slant = |v: &Vec3| v.x.abs() > 0.01 && v.z.abs() > 0.01;
        let slant_bits = |m: &Model| -> (u32, u32) {
            let v = m
                .vectors
                .iter()
                .find(|v| is_slant(v))
                .expect("a non-axis slant vector must exist");
            // Compare on ABSOLUTE mantissa (a subtract stores the face Reverse()d = negated normal).
            (v.x.abs().to_bits(), v.z.abs().to_bits())
        };

        let sub = build_geometry_bspcsg(&[wedge_brush(CsgOper::Subtract, authored)]).unwrap();
        let add = build_geometry_bspcsg(&[wedge_brush(CsgOper::Add, authored)]).unwrap();

        let (sx, sz) = slant_bits(&sub);
        assert_eq!(
            (sx, sz),
            (stored.x.abs().to_bits(), stored.z.abs().to_bits()),
            "SUBTRACT slant normal must be safe_normal_slow(CalcNormal(local)) — recomputed AND \
             re-normalized (§92 §52), not authored and not the once-normalized CalcNormal"
        );
        // Pin the §52 second-normalization: the stored value is 1-2 ULP off the once-normalized calc.
        assert_ne!(
            (sx, sz),
            (calc.x.abs().to_bits(), calc.z.abs().to_bits()),
            "the SECOND SafeNormalSlow must actually move the bits vs once-normalized CalcNormal"
        );
        let (ax, az) = slant_bits(&add);
        assert_eq!(
            (ax, az),
            (sx, sz),
            "ADD stores the same safe_normal_slow(CalcNormal(local)) — the authored normal is \
             ignored (uniform rule; the old Add-keeps-authored reading was coincidental castle \
             evidence, refuted by Vandenberg Brush41's live golden bytes)"
        );
        assert_ne!(
            (ax, az),
            (authored.x.abs().to_bits(), authored.z.abs().to_bits()),
            "the perturbed authored normal must NOT survive into the built model"
        );
    }

    #[test]
    fn subtract_slant_normal_rotates_then_renormalizes_with_correct_index_order() {
        // §92 §52: pin the PRODUCTION `R·calc_normal(local)` multiply itself.  The other §52 test uses
        // an identity `rot`, so a transpose/index bug in the hand-rolled `r[i][j]·nl` (bspcsg.rs LOOP-1
        // subtract branch) would pass it silently.  Here `rot` is a 90° yaw (R != Rᵀ), so a swapped
        // index lands the normal on the wrong axes and the exact-bit lookup below fails.
        let mut probe = FPoly::new(vec![
            Vec3::new(128.0, -64.0, -64.0),
            Vec3::new(128.0, 64.0, -64.0),
            Vec3::new(-128.0, 64.0, 64.0),
            Vec3::new(-128.0, -64.0, 64.0),
        ]);
        assert!(probe.calc_normal());
        let nl = probe.normal; // == the slant face's local CalcNormal (same winding as wedge b,c,f,e)
        // 90° yaw about z (orthonormal, non-symmetric): (x,y,z) -> (-y, x, z).
        let r = [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ];
        let rotated = Vec3::new(
            r[0][0] * nl.x + r[0][1] * nl.y + r[0][2] * nl.z,
            r[1][0] * nl.x + r[1][1] * nl.y + r[1][2] * nl.z,
            r[2][0] * nl.x + r[2][1] * nl.y + r[2][2] * nl.z,
        );
        let expected = safe_normal_slow(&rotated).expect("renormalizable");
        // A transpose bug would instead compute Rᵀ·nl -> (y, -x, z), moving the x/y magnitudes across
        // axes; assert the two are genuinely distinguishable on this fixture so the test has teeth.
        let transposed = Vec3::new(
            r[0][0] * nl.x + r[1][0] * nl.y + r[2][0] * nl.z,
            r[0][1] * nl.x + r[1][1] * nl.y + r[2][1] * nl.z,
            r[0][2] * nl.x + r[1][2] * nl.y + r[2][2] * nl.z,
        );
        let transposed = safe_normal_slow(&transposed).expect("renormalizable");
        assert_ne!(
            (expected.x.to_bits(), expected.y.to_bits()),
            (transposed.x.to_bits(), transposed.y.to_bits()),
            "fixture must distinguish R from Rᵀ or the test has no teeth"
        );

        let mut br = wedge_brush(CsgOper::Subtract, nl);
        br.rot = r;
        let m = build_geometry_bspcsg(&[br]).unwrap();
        // The stored slant normal must be exactly ±expected (a subtract Reverse()s the face → global
        // sign flip is allowed, but the per-axis bits must match R·nl, not Rᵀ·nl).
        let want = [expected, Vec3::new(-expected.x, -expected.y, -expected.z)];
        let found = m.vectors.iter().any(|v| {
            want.iter().any(|w| {
                v.x.to_bits() == w.x.to_bits()
                    && v.y.to_bits() == w.y.to_bits()
                    && v.z.to_bits() == w.z.to_bits()
            })
        });
        assert!(
            found,
            "stored slant normal must be safe_normal_slow(R·calc_normal(local)) with the correct \
             index order; a transpose/index bug in the R·nl multiply would fail this exact-bit lookup"
        );
    }

    /// A single-quad zone-portal SHEET brush, normal +Z, carrying `PF_Portal|PF_NotSolid|PF_TwoSided|
    /// PF_Invisible` on BOTH the brush-level `poly_flags` and the poly (mirrors the real DX portal
    /// brush, e.g. UNATCO `Brush344` `PolyFlags=0x4000109` — §92 §54).
    fn portal_sheet(hx: f32, hy: f32, loc: Vec3, oper: CsgOper) -> build::BrushInput {
        let pf = csg::PF_PORTAL | csg::PF_NOTSOLID | 0x100 | 0x01; // Portal|NotSolid|TwoSided|Invisible
        let mut p = FPoly::new(vec![
            Vec3::new(-hx, -hy, 0.0),
            Vec3::new(hx, -hy, 0.0),
            Vec3::new(hx, hy, 0.0),
            Vec3::new(-hx, hy, 0.0),
        ]);
        p.normal = Vec3::new(0.0, 0.0, 1.0);
        p.poly_flags = pf;
        build::BrushInput {
            polys: vec![p],
            oper,
            poly_flags: pf, // brush-level Portal (mirrors DX Brush344 PolyFlags=0x4000109)
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        }
    }

    /// §92 §54 PORTAL PASS-STAGING regression — pins that a `PF_Portal` brush is processed in the
    /// FIRST (structural) incremental `bspBrushCSG` pass, BEFORE `bspBuildFPolys`/repartition, so its
    /// face enters the repartition SOUP and survives into the committed tree — exactly as UnrealEd
    /// does (a portal is a legal `FindBestSplit` candidate, §82 §4).  The bug this guards: routing
    /// every non-solid brush (portal included) into the deferred PASS-2 semisolid layer, which runs
    /// AFTER repartition — so the portal never reaches the soup and is DROPPED from the committed tree
    /// the editor keeps (§92 §54: Brush344, the first UNATCO detail brush, is the (105,213] structural
    /// divergence — editor 1639 vs native 1637 committed nodes at N=106, closed by this routing).
    ///
    /// Fixture: a `CSG_Subtract` room carved into the solid world, plus a portal sheet coincident with
    /// its floor wall (mirroring the real portal, which sits antiparallel to a solid wall face — §54,
    /// Brush344 vs Brush365 — NOT bisecting empty space, which would trip a debug-only Pass-D
    /// fail-safe on this tiny synthetic scene).  The portal carves NOTHING (stays `NF_NotCsg`).
    ///
    /// Reverting `detail_pass` to the old `is_detail` (`pf & 0x28 != 0`, portal NOT excluded) routes
    /// the portal to pass 2: it never reaches the soup, so it contributes ZERO surfs — asserts (1)/(2)
    /// go RED.  (Verified 2026-07-20: fix → 7 surfs incl. PF_Portal; bug → 6 surfs, no PF_Portal.)
    #[test]
    fn portal_brush_enters_pass1_repartition_soup() {
        let c = Vec3::new(0.0, 0.0, 0.0);
        let room_only =
            build_geometry_bspcsg(&[box_brush(256.0, 256.0, 256.0, c, CsgOper::Subtract)]).unwrap();
        let with_portal = build_geometry_bspcsg(&[
            box_brush(256.0, 256.0, 256.0, c, CsgOper::Subtract),
            portal_sheet(256.0, 256.0, Vec3::new(0.0, 0.0, -256.0), CsgOper::Add),
        ])
        .unwrap();

        // (1) The portal reached the repartitioned tree: a surf carries PF_Portal.  Under the bug
        // (portal deferred to pass 2) it is dropped, so NO surf carries PF_Portal.
        let portal_surf = with_portal
            .surfs
            .iter()
            .position(|s| s.poly_flags & csg::PF_PORTAL != 0);
        assert!(
            portal_surf.is_some(),
            "a PF_Portal brush must reach the repartitioned tree as a surf — it was DROPPED, so it \
             was routed to the deferred pass-2 layer instead of the pass-1 soup (§92 §54)"
        );

        // (2) It genuinely ADDED that surf (a pass-1 portal contributes; a pass-2-deferred one does
        // not): with the portal the surf pool grows past the bare room's.
        assert!(
            with_portal.surfs.len() > room_only.surfs.len(),
            "the portal must add a surf over the portal-free room ({} vs {}); equal counts mean the \
             portal never entered the pass-1 soup",
            with_portal.surfs.len(),
            room_only.surfs.len()
        );

        // (3) Carve-safety: the portal's node stays NF_NotCsg (0x01) — it partitions, but carves no
        // solid (`derive_nf` sets NF_NotCsg from a portal's PF_NotSolid).
        let ps = portal_surf.unwrap() as i32;
        let portal_node = with_portal.nodes.iter().find(|n| n.i_surf == ps);
        assert!(
            portal_node.map_or(false, |n| n.node_flags & 1 != 0),
            "the portal node must be NF_NotCsg (carves nothing)"
        );
    }

    /// A single-quad NotSolid sheet brush that is NOT a portal — an ordinary glass/window pane,
    /// `PF_NotSolid|PF_TwoSided|PF_Translucent` (mirrors UNATCO `Brush416`, `PolyFlags=0x10c`, world-csg
    /// idx 111 — §92 §54 generalization, live N=112 oracle capture 2026-08-25).
    fn glass_sheet(hx: f32, hy: f32, loc: Vec3, oper: CsgOper) -> build::BrushInput {
        let pf = csg::PF_NOTSOLID | 0x100 | 0x04; // NotSolid|TwoSided|Translucent, NOT Portal
        let mut p = FPoly::new(vec![
            Vec3::new(-hx, -hy, 0.0),
            Vec3::new(hx, -hy, 0.0),
            Vec3::new(hx, hy, 0.0),
            Vec3::new(-hx, hy, 0.0),
        ]);
        p.normal = Vec3::new(0.0, 0.0, 1.0);
        p.poly_flags = pf;
        build::BrushInput {
            polys: vec![p],
            oper,
            poly_flags: pf,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        }
    }

    /// §92 §54 generalization — a NotSolid brush that is NOT a portal (e.g. an ordinary glass pane)
    /// ALSO belongs in the FIRST (structural) incremental `bspBrushCSG` pass, not the deferred
    /// semisolid pass-2.  Proved live (not just for portals): a gdb capture of the real editor's
    /// pre-repartition committed tree for the first 112 UNATCO world-csg brushes has 1766 nodes vs
    /// native's pre-fix 1764 — the SAME "+2 non-CSG splitter" signature §54 found for a portal —
    /// attributable to `Brush416` (idx 111, `PF_NotSolid|PF_TwoSided|0x4`, NOT Portal, NOT Semisolid),
    /// the last brush the N=112 cutoff includes. Reverting `detail_pass` to `pf & 0x28 != 0 &&
    /// !is_portal` (NotSolid-but-not-portal deferred to pass 2) routes this brush's face out of the
    /// soup, so it never reaches the repartitioned tree — assertions (1)/(2) go RED.
    #[test]
    fn notsolid_non_portal_brush_enters_pass1_repartition_soup() {
        let c = Vec3::new(0.0, 0.0, 0.0);
        let room_only =
            build_geometry_bspcsg(&[box_brush(256.0, 256.0, 256.0, c, CsgOper::Subtract)]).unwrap();
        let with_glass = build_geometry_bspcsg(&[
            box_brush(256.0, 256.0, 256.0, c, CsgOper::Subtract),
            glass_sheet(256.0, 256.0, Vec3::new(0.0, 0.0, -256.0), CsgOper::Add),
        ])
        .unwrap();

        // (1) The glass pane reached the repartitioned tree: a surf carries its PF_Translucent bit.
        let glass_surf = with_glass.surfs.iter().position(|s| s.poly_flags & 0x04 != 0);
        assert!(
            glass_surf.is_some(),
            "a NotSolid-but-not-portal brush must reach the repartitioned tree as a surf — it was \
             DROPPED, so it was routed to the deferred pass-2 layer instead of the pass-1 soup"
        );

        // (2) It genuinely ADDED that surf (a pass-1 splitter contributes; a pass-2-deferred one
        // does not, since pass 2 never repartitions).
        assert!(
            with_glass.surfs.len() > room_only.surfs.len(),
            "the glass pane must add a surf over the pane-free room ({} vs {}); equal counts mean it \
             never entered the pass-1 soup",
            with_glass.surfs.len(),
            room_only.surfs.len()
        );

        // (3) Carve-safety: the pane's node stays NF_NotCsg (0x01) — it partitions, but carves no
        // solid (`derive_nf` sets NF_NotCsg from NotSolid).
        let gs = glass_surf.unwrap() as i32;
        let glass_node = with_glass.nodes.iter().find(|n| n.i_surf == gs);
        assert!(
            glass_node.map_or(false, |n| n.node_flags & 1 != 0),
            "the glass pane's node must be NF_NotCsg (carves nothing)"
        );
    }

    // --- BRUSH FROM INTERSECTION / DEINTERSECTION (the `0x35ab3` tail) -------------------------

    /// World AABB of a brush set, as the Python verb computes it (`writes.union_bounds`).
    fn set_bounds(set: &[build::BrushInput]) -> (Vec3, Vec3) {
        let mut mn = Vec3::new(f32::INFINITY, f32::INFINITY, f32::INFINITY);
        let mut mx = Vec3::new(f32::NEG_INFINITY, f32::NEG_INFINITY, f32::NEG_INFINITY);
        for b in set {
            for p in &b.polys {
                for v in &p.verts {
                    let w = Vec3::new(
                        v.x + b.location.x,
                        v.y + b.location.y,
                        v.z + b.location.z,
                    );
                    mn = Vec3::new(mn.x.min(w.x), mn.y.min(w.y), mn.z.min(w.z));
                    mx = Vec3::new(mx.x.max(w.x), mx.y.max(w.y), mx.z.max(w.z));
                }
            }
        }
        (mn, mx)
    }

    /// The verb's INTERNAL scaffolding (`brushcsg.build_scaffolding`): a `bbox+64` builder cube
    /// CENTRED on the set (span `[lo-32, hi+32]`) and, for `intersect` only, a wrap-SUBTRACT of the
    /// SAME box, which carves the builder's own volume empty so Phase 1 keeps no builder face.
    /// (The editor-driven generator's `(cx-32, …)` wrap is that same box pre-compensated for
    /// UnrealEd's `EDIT PASTE` +32uu drift — see `brushcsg.py`.)
    fn scaffolding(set: Vec<build::BrushInput>, deintersect: bool) -> (Vec<build::BrushInput>, build::BrushInput) {
        let (lo, hi) = set_bounds(&set);
        let c = Vec3::new((lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5, (lo.z + hi.z) * 0.5);
        let h = Vec3::new(
            (hi.x - lo.x) * 0.5 + 32.0,
            (hi.y - lo.y) * 0.5 + 32.0,
            (hi.z - lo.z) * 0.5 + 32.0,
        );
        let oper = if deintersect {
            CsgOper::Deintersect
        } else {
            CsgOper::Intersect
        };
        let builder = box_brush(h.x, h.y, h.z, c, oper);
        let mut world: Vec<build::BrushInput> = Vec::new();
        if !deintersect {
            world.push(box_brush(h.x, h.y, h.z, c, CsgOper::Subtract));
        }
        world.extend(set);
        (world, builder)
    }

    fn faces_bounds(faces: &[FPoly]) -> (Vec3, Vec3) {
        let mut mn = Vec3::new(f32::INFINITY, f32::INFINITY, f32::INFINITY);
        let mut mx = Vec3::new(f32::NEG_INFINITY, f32::NEG_INFINITY, f32::NEG_INFINITY);
        for p in faces {
            for v in &p.verts {
                mn = Vec3::new(mn.x.min(v.x), mn.y.min(v.y), mn.z.min(v.z));
                mx = Vec3::new(mx.x.max(v.x), mx.y.max(v.y), mx.z.max(v.z));
            }
        }
        (mn, mx)
    }

    /// The distinct unit-axis normals present in a face set, as `(x,y,z)` sign triples.
    fn axis_normals(faces: &[FPoly]) -> std::collections::BTreeSet<(i32, i32, i32)> {
        faces
            .iter()
            .map(|p| {
                (
                    p.normal.x.round() as i32,
                    p.normal.y.round() as i32,
                    p.normal.z.round() as i32,
                )
            })
            .collect()
    }

    fn approx(a: f32, b: f32) -> bool {
        (a - b).abs() < 0.01
    }

    /// GATE B1 — `intersect` of a single ADDITIVE box returns that box's own boundary: the six
    /// axis faces, at the source extents.  This is the whole operation end to end (world build,
    /// Phase 1 builder-face clip, Phase 2 world-cap collection, iLink renumber).
    #[test]
    fn intersect_of_one_additive_box_is_that_box() {
        let set = vec![box_brush(
            128.0,
            128.0,
            64.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Add,
        )];
        let (world, builder) = scaffolding(set, false);
        let faces = intersect_brushset(&world, &builder).expect("intersect must build");
        assert!(!faces.is_empty(), "intersect produced no faces");
        let (mn, mx) = faces_bounds(&faces);
        assert!(
            approx(mn.x, -128.0) && approx(mx.x, 128.0)
                && approx(mn.y, -128.0) && approx(mx.y, 128.0)
                && approx(mn.z, -64.0) && approx(mx.z, 64.0),
            "result bounds {:?}..{:?} != the source box",
            (mn.x, mn.y, mn.z),
            (mx.x, mx.y, mx.z)
        );
        assert_eq!(
            axis_normals(&faces).len(),
            6,
            "a box plug must present all six axis normals, got {:?}",
            axis_normals(&faces)
        );
    }

    /// GATE B1 — `deintersect` of a single SUBTRACTIVE box returns the VOID PLUG: a solid filling
    /// exactly what the set carves (the door-mover case).
    #[test]
    fn deintersect_of_one_subtractive_box_is_the_void_plug() {
        let set = vec![box_brush(
            96.0,
            32.0,
            112.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];
        let (world, builder) = scaffolding(set, true);
        let faces = intersect_brushset(&world, &builder).expect("deintersect must build");
        assert!(!faces.is_empty(), "deintersect produced no faces");
        let (mn, mx) = faces_bounds(&faces);
        assert!(
            approx(mn.x, -96.0) && approx(mx.x, 96.0)
                && approx(mn.y, -32.0) && approx(mx.y, 32.0)
                && approx(mn.z, -112.0) && approx(mx.z, 112.0),
            "plug bounds {:?}..{:?} != the carved void",
            (mn.x, mn.y, mn.z),
            (mx.x, mx.y, mx.z)
        );
        assert_eq!(
            axis_normals(&faces).len(),
            6,
            "the plug must present all six axis normals, got {:?}",
            axis_normals(&faces)
        );
    }

    /// GATE B1 — the §3 flag rule, builder half: LOOP-1's `NotPolyFlags = 0x28` STRIPS
    /// `PF_NotSolid|PF_Semisolid` off the builder's own faces for Intersect/Deintersect (only
    /// `CSG_Add` uses 0), so a semisolid/nonsolid face in the result can only have arrived via
    /// Phase 2 — a world cap inheriting a SOURCE brush's solidity.  Asserting it here pins the rule
    /// where it lives (inside the merge), independently of any world geometry.
    ///
    /// The other half — an additive source's solidity SURVIVING into the result — needs a semisolid
    /// brush to actually reach the world tree, which the shared core currently does NOT do (Pass-2
    /// detail brushes are dropped: the repartition leaves every node `NF_IsNew`, so the descent
    /// treats them all as non-CSG and the detail faces reach an `F_INSIDE` leaf).  That is a
    /// pre-existing core gap, tracked in `board/inbox/`; this half is covered at the golden level
    /// once it lands.
    #[test]
    fn loop1_strips_solidity_bits_for_intersect_and_deintersect() {
        for oper in [CsgOper::Intersect, CsgOper::Deintersect, CsgOper::Subtract] {
            let mut b = box_brush(64.0, 64.0, 64.0, Vec3::new(0.0, 0.0, 0.0), oper);
            for p in b.polys.iter_mut() {
                p.poly_flags = csg::PF_SEMISOLID | csg::PF_NOTSOLID;
            }
            let temp = brush_loop1(&b, 0, 0);
            assert!(!temp.is_empty());
            assert!(
                temp.iter().all(|p| p.poly_flags & 0x28 == 0),
                "LOOP-1 must strip PF_NotSolid|PF_Semisolid (NotPolyFlags=0x28) for this oper"
            );
        }
        // CSG_Add is the ONE oper with NotPolyFlags = 0 — an additive KEEPS its solidity, which is
        // exactly how a semisolid face can reach the result as a Phase-2 cap.
        let mut b = box_brush(64.0, 64.0, 64.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add);
        for p in b.polys.iter_mut() {
            p.poly_flags = csg::PF_SEMISOLID;
        }
        let temp = brush_loop1(&b, 0, 0);
        assert!(
            temp.iter().all(|p| p.poly_flags & csg::PF_SEMISOLID != 0),
            "a CSG_Add source must KEEP its semisolid flag through LOOP-1"
        );
    }

    /// REGRESSION — a SEMISOLID (Pass-2 "detail") brush must reach the world tree.
    ///
    /// The repartition builds its whole tree via `bsp_add_node(…, NF_IS_NEW, …)`, and `NF_IsNew`
    /// makes `is_csg_filter` report a node NON-solid (so that a brush cannot cut itself).  Nothing
    /// cleared it before Pass 2, so a detail brush descended a world where nothing was CSG-solid:
    /// `outside` never flipped, every face reached an `F_INSIDE` leaf, and the Add leaf — which
    /// emits only on `F_OUTSIDE` — dropped the lot.  Semisolid/nonsolid brushes silently vanished,
    /// from `level materialize` as much as from the CSG merge verbs.  Fixed by `bsp_cleanup` after
    /// the repartition; this pins it at the level the bug lives at.  (The castle byte-identity
    /// golden cannot catch this: the castle has 0 detail brushes.)
    #[test]
    fn a_semisolid_detail_brush_reaches_the_world() {
        let world_nodes = |pf: u32| {
            let mut b = box_brush(64.0, 64.0, 64.0, Vec3::new(200.0, 0.0, 0.0), CsgOper::Add);
            b.poly_flags = pf;
            let set = vec![
                box_brush(512.0, 512.0, 256.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract),
                b,
            ];
            build_geometry_bspcsg(&set).expect("build must succeed").nodes.len()
        };
        let plain = world_nodes(0);
        let semi = world_nodes(csg::PF_SEMISOLID);
        assert!(
            semi > 6,
            "the semisolid detail brush contributed NO nodes (world has {semi}; the carved wrap \
             alone accounts for 6) — the repartition's NF_IsNew is not being cleared"
        );
        assert_eq!(
            semi, plain,
            "a semisolid brush should contribute the same FACES as the solid one here — semisolid \
             changes solidity, not whether the geometry exists"
        );
    }

    /// GATE B1 — the finalize renumber (`0x35c44`/`0x35cb1`): every `iLink` points at the FIRST
    /// poly of its own phase range sharing that surf, and never crosses the Phase-1/Phase-2 border.
    #[test]
    fn ilink_renumber_groups_within_each_phase_range() {
        // 4 P1-range polys with source surfs [7, 9, 7, 9]; 3 P2-range polys with surfs [7, 4, 7].
        let mut polys: Vec<FPoly> = [7, 9, 7, 9, 7, 4, 7]
            .iter()
            .map(|&s| {
                let mut p = FPoly::new(vec![
                    Vec3::new(0.0, 0.0, 0.0),
                    Vec3::new(1.0, 0.0, 0.0),
                    Vec3::new(0.0, 1.0, 0.0),
                ]);
                p.i_link = s;
                p
            })
            .collect();
        renumber_result_ilinks(&mut polys, 4);
        let links: Vec<i32> = polys.iter().map(|p| p.i_link).collect();
        // P1 range: 0,1 seed themselves; 2 links to 0; 3 links to 1.
        // P2 range: 4 seeds itself (surf 7 does NOT reach back to index 0); 5 seeds; 6 links to 4.
        assert_eq!(links, vec![0, 1, 0, 1, 4, 5, 4]);
    }

    /// GATE — the corrected `is_csg_filter` matches the editor's `IsCsg =
    /// NumVertices>0 && !(nf&0x21)`.  Pinned by the 2026-08-27/28 Wanchai live capture: the editor
    /// treats a `NumVertices == 0` dead node as NON-CSG (its `outside` does not flip), which is what
    /// makes it drop Brush250's buried z=112 face where native previously kept it.  The `nv>0` clause
    /// was dropped in 2026-07-17 against N=4..8 / non-OG castle fixtures; those are no longer valid
    /// parity evidence (owner ruling 2026-08-28 — only OG retail levels count).
    #[test]
    fn is_csg_filter_matches_editor_predicate() {
        use crate::model::BspNode;
        let plane = crate::model::Plane { x: 0.0, y: 0.0, z: 1.0, w: 0.0 };
        let live = BspNode::leaf(plane, 0, 0, 4);
        assert!(
            is_csg_filter(&live),
            "a live node (num_vertices>0, flags clean) must be CSG-solid"
        );

        let mut dead = BspNode::leaf(plane, 0, 0, 0);
        assert!(
            !is_csg_filter(&dead),
            "a dead node (num_vertices==0) must be NON-CSG even with clean flags — the editor's IsCsg"
        );

        dead.num_vertices = 4;
        dead.node_flags = 0x01; // NF_NotCsg
        assert!(!is_csg_filter(&dead), "NF_NotCsg must make a live node non-CSG");
        dead.node_flags = 0x20; // NF_IsNew
        assert!(!is_csg_filter(&dead), "NF_IsNew must make a live node non-CSG");
    }

    /// GATE (TDD, written before the fix) — `unatco-verts-points-residual-after-the-zone`: the real
    /// editor's `bspRepartition` call is a proven no-op on NODE structure (`bspRefresh`'s
    /// `Core.dll!FArray::Remove` discards every freshly-built subtree, 209/209 UNATCO calls
    /// live-verified) but a real, PERMANENT grower of `Verts`/`Points` (0/209 calls net to zero
    /// vert growth; every call keeps what its own real, merged reconstruction allocated, even
    /// though nothing ends up referencing it). `repartition_frontier` must reproduce both halves:
    /// leave the parent's `i_front`/`i_back` and the node array untouched, while still growing
    /// `verts` (points may or may not grow, depending on whether the reconstructed poly's corners
    /// already exist in the pool — but a real reconstruction always pushes fresh `BspVert` pool
    /// entries per `bsp_add_node`, which never reuses an existing vert-pool slot).
    #[test]
    fn repartition_frontier_is_a_node_noop_but_grows_verts() {
        let c = Vec3::new(0.0, 0.0, 0.0);
        let mut model =
            build_geometry_bspcsg(&[box_brush(256.0, 256.0, 256.0, c, CsgOper::Add)]).unwrap();

        // Find any node with a real (non-leaf-empty) child, exactly like `collect_repartition_frontier`
        // would surface as a frontier entry — don't hardcode which index or which place, since the
        // exact tree shape is incidental to this single-box scenario.
        let (parent, place) = model
            .nodes
            .iter()
            .enumerate()
            .find_map(|(i, n)| {
                if n.i_back != -1 {
                    Some((i as i32, NODE_BACK))
                } else if n.i_front != -1 {
                    Some((i as i32, NODE_FRONT))
                } else {
                    None
                }
            })
            .expect("a freshly-built box model must have at least one node with a real child");

        let nodes_before = model.nodes.clone();
        let verts_before = model.verts.len();
        let points_before = model.points.len();
        let surfs_before = model.surfs.len();

        let (list_a, list_b) = if place == NODE_BACK {
            (vec![parent], vec![])
        } else {
            (vec![], vec![parent])
        };
        repartition_frontier(&mut model, &list_a, &list_b, surfs_before).unwrap();

        assert_eq!(
            model.nodes.len(),
            nodes_before.len(),
            "repartition_frontier must never append or remove nodes"
        );
        assert_eq!(
            model.nodes, nodes_before,
            "repartition_frontier must never modify ANY existing node's content, including the \
             parent's i_front/i_back — the real editor's bspRefresh discards its whole freshly-built \
             subtree, so the parent keeps pointing at the pre-existing child unchanged"
        );
        assert_eq!(
            model.surfs.len(),
            surfs_before,
            "split fragments always preserve i_link (FPoly::empty_copy), so this reconstruction \
             never allocates a new surf"
        );
        assert!(
            model.verts.len() > verts_before,
            "the real editor's per-call reconstruction permanently grows Verts even though nothing \
             ends up referencing the new entries — verts_before={verts_before} verts_after={}",
            model.verts.len()
        );
        assert!(
            model.points.len() >= points_before,
            "points must never shrink"
        );
        // `bspRepartition`'s `bspBuildFPolys` refills `Model->Polys` from THIS subtree and nothing in
        // `csgRebuild` rebuilds it afterwards, so the world model saves the last call's soup.
        assert!(
            !model.polys.is_empty(),
            "the frontier call must leave its own subtree's soup in Model.Polys"
        );
        assert!(
            model.polys.iter().all(|p| p.poly_flags & PF_ED_PROCESSED != 0),
            "every saved soup poly carries PF_EdProcessed"
        );
        // Every poly consumed whole took a freshly seeded surf index, counted off the pool length
        // passed in; a split poly would keep its (smaller) pre-build iLink.
        assert!(
            model.polys.iter().any(|p| p.i_link >= surfs_before as i32),
            "at least the splitter must carry a freshly seeded iLink at or above the pool length"
        );
    }

    /// Structural safety pin for the incremental point-pool path (now the only path): its GC runs at
    /// the editor's real `bspRefresh` call sites (pre-repartition bases-only, post-`bsp_build`,
    /// frontier tails — never per-brush, never after optgeom), which closed `DX.dx`'s surf `p_base`
    /// residual to 0/26 (`parity_report.py`, cached golden). This pins the invariants round 13's
    /// per-brush GC violated (UNATCO's live `vert iVertex index -1 out of range` crash): every
    /// `p_base`/ring-vertex point reference on the simplest unsplit case is valid.
    #[test]
    fn incremental_points_keeps_the_simplest_subtract_case_structurally_safe() {
        let brushes = [box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )];

        let incremental = build_geometry_bspcsg(&brushes).unwrap();

        // No dangling references: every surf p_base and every node ring vertex must name a real
        // point. This is the exact invariant UNATCO's live crash (`vert iVertex index -1 out of
        // range`) violates on more complex, cross-brush-split geometry.
        for s in &incremental.surfs {
            assert!(
                s.p_base >= 0 && (s.p_base as usize) < incremental.points.len(),
                "surf p_base must be a valid point index, got {}",
                s.p_base
            );
        }
        for n in &incremental.nodes {
            for k in 0..n.num_vertices {
                let v = incremental.verts[(n.i_vert_pool + k) as usize];
                assert!(
                    v.i_vertex >= 0 && (v.i_vertex as usize) < incremental.points.len(),
                    "every node ring vertex must be a valid point index, got {}",
                    v.i_vertex
                );
            }
        }
    }

    /// The world CSG soup is RETAINED (`Model.polys`, 2026-09-04): the editor keeps the post-`bspBuild`
    /// FPoly list in `Model.Polys` and Python assembly emits it. For a lone unsplit Add box every surf
    /// maps to exactly one soup poly, each carrying `PF_EdProcessed` (0x40000000) as its ONLY flag
    /// (the source polys carry 0) and `i_link` == its surf. The box's six faces are pinned: each soup
    /// poly's normal is an exact unit axis and its base sits on that face's plane at the box's own
    /// half-extent (256 in x/y, 128 in z), and all six ±axis faces appear exactly once.
    #[test]
    fn world_build_retains_the_csg_soup_with_ed_processed_set() {
        let brushes = [box_brush(256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add)];
        let m = build_geometry_bspcsg(&brushes).unwrap();
        assert_eq!(m.polys.len(), m.surfs.len(), "one soup poly per surf on an unsplit box");
        assert_eq!(m.polys.len(), 6, "an unsplit box has six faces");

        let mut seen_faces: Vec<(i32, i32, i32)> = Vec::new();
        for (i, p) in m.polys.iter().enumerate() {
            // PF_EdProcessed (0x40000000) is the SOLE flag added vs the source poly (which was 0).
            assert_eq!(p.poly_flags, 0x4000_0000,
                       "soup poly {i} must carry PF_EdProcessed and nothing else, got {:#x}",
                       p.poly_flags);
            assert!(p.i_link >= 0 && (p.i_link as usize) < m.surfs.len(),
                    "soup poly {i} i_link must be a valid surf index, got {}", p.i_link);

            // Normal is an exact unit axis (one component ±1.0, the other two exactly 0.0).
            let n = p.normal;
            let axis = [(n.x, 256.0f32), (n.y, 256.0), (n.z, 128.0)];
            let nonzero: Vec<usize> = (0..3).filter(|&k| axis[k].0 != 0.0).collect();
            assert_eq!(nonzero.len(), 1,
                       "soup poly {i} normal must be a single unit axis, got ({},{},{})", n.x, n.y, n.z);
            let k = nonzero[0];
            assert!(axis[k].0 == 1.0 || axis[k].0 == -1.0,
                    "soup poly {i} axis component must be exactly ±1.0, got {}", axis[k].0);

            // Base sits on the face plane: |base·normal| == the box half-extent for that axis
            // (the plane's distance from origin; the soup normal's sign is the CSG convention).
            let half_extent = axis[k].1;
            let base_dot = p.base.x * n.x + p.base.y * n.y + p.base.z * n.z;
            assert_eq!(base_dot.abs(), half_extent,
                       "soup poly {i} base must lie on the face plane at half-extent {half_extent}, \
                        got base·n = {base_dot}");

            seen_faces.push((n.x as i32, n.y as i32, n.z as i32));
        }
        seen_faces.sort();
        assert_eq!(
            seen_faces,
            vec![(-1, 0, 0), (0, -1, 0), (0, 0, -1), (0, 0, 1), (0, 1, 0), (1, 0, 0)],
            "all six ±axis box faces must appear exactly once"
        );
    }

    /// `reorder_surfs_canonical` must renumber the retained soup's `i_link` (2026-09-04 regression:
    /// the soup froze `i_link = i_surf` at repartition `bsp_build` and was never remapped). Two
    /// distinct maps: NODES take the dense on-disk surf index (`old_to_new`); the soup's `Model.Polys`
    /// iLink takes the surf's CANON RANK — the incremental-CSG surf space repartition rebuilt from,
    /// which is larger than the final pool when repartition merged a surf away, so the iLink leaves a
    /// GAP at the merged rank and can exceed the final surf count (WanChai N=4: iLink 16, 16 surfs).
    #[test]
    fn reorder_surfs_canonical_renumbers_the_retained_soup_i_link() {
        let surf = |actor: i32, bp: i32| BspSurf {
            texture_ref: 0, poly_flags: 0, p_base: 0, v_normal: 0, v_texture_u: 0, v_texture_v: 0,
            i_actor: actor, i_brush_poly: bp, pan: [0, 0], i_light_map: -1,
        };
        let plane = Plane { x: 0.0, y: 0.0, z: 1.0, w: 0.0 };

        // (a) No-gap permutation: canon keys == final surfs. Rank == dense index, so nodes and the
        // soup take the SAME 3-cycle map [1,2,0].
        let mut m = Model::default();
        m.surfs = vec![surf(2, 0), surf(2, 1), surf(2, 2)];
        m.nodes = (0..3).map(|s| BspNode::leaf(plane, s, 0, 0)).collect();
        m.polys = (0..3).map(|s| { let mut p = FPoly::new(vec![]); p.i_link = s; p }).collect();
        reorder_surfs_canonical(&mut m, &[(2, 2), (2, 0), (2, 1)]);
        assert_eq!(m.nodes.iter().map(|nd| nd.i_surf).collect::<Vec<_>>(), vec![1, 2, 0]);
        assert_eq!(m.polys.iter().map(|p| p.i_link).collect::<Vec<_>>(), vec![1, 2, 0]);

        // (b) Gap: canon carries a 4th key (9,9) at rank 1 that repartition merged away — no final
        // surf holds it. Nodes stay dense [0,1,2]; the soup skips rank 1 and reaches iLink 3, one
        // past the final 3-surf pool — reproducing UED22's out-of-range Polys iLink.
        let mut g = Model::default();
        g.surfs = vec![surf(2, 0), surf(2, 1), surf(2, 2)];
        g.nodes = (0..3).map(|s| BspNode::leaf(plane, s, 0, 0)).collect();
        g.polys = (0..3).map(|s| { let mut p = FPoly::new(vec![]); p.i_link = s; p }).collect();
        reorder_surfs_canonical(&mut g, &[(2, 0), (9, 9), (2, 1), (2, 2)]);
        assert_eq!(g.nodes.iter().map(|nd| nd.i_surf).collect::<Vec<_>>(), vec![0, 1, 2],
                   "nodes keep the dense on-disk surf index");
        assert_eq!(g.polys.iter().map(|p| p.i_link).collect::<Vec<_>>(), vec![0, 2, 3],
                   "soup iLink takes the canon rank, gapping the merged-away surf");
    }

    /// Round 15 golden pin (`dev/docs/spikes/2026-09-01-dx-pbase-points-trace/`): `DX.dx`'s
    /// `Brush3` — its exact authored T3D polys (Origin = V0 on every face) as a lone world
    /// Subtract — must reproduce the UED22 golden's
    /// own `p_base` assignment `[0,1,1,3,4,2]` and base-block point order `[A,E,H,G,F]`
    /// (cached `DX.dx` golden, surfs 0-5 / `Points[0..5]`; round 9's live gdb decoded the same
    /// values from the editor's `bspAddPoint` sequence). Pins the two round-15 mechanisms: the
    /// Subtract-leaf `Reverse()` making the plain forward ring walk equal the editor's insertion
    /// order, and the pre-repartition bases-only Points GC (`compact_points_to_surf_bases`).
    #[test]
    fn incremental_points_reproduces_dx_brush3_golden_p_base_order() {
        let f = |verts: [[f32; 3]; 4], n: [f32; 3]| {
            let mut p = FPoly::new(verts.iter().map(|v| Vec3::new(v[0], v[1], v[2])).collect());
            p.normal = Vec3::new(n[0], n[1], n[2]);
            p
        };
        let s = 512.0;
        // DX.dx Brush3, verbatim authored order (T3D trunk `maps/dx`).
        let polys = vec![
            f([[-s, -s, s], [s, -s, s], [s, s, s], [-s, s, s]], [0.0, 0.0, 1.0]),
            f([[-s, s, -s], [s, s, -s], [s, -s, -s], [-s, -s, -s]], [0.0, 0.0, -1.0]),
            f([[-s, s, -s], [-s, s, s], [s, s, s], [s, s, -s]], [0.0, 1.0, 0.0]),
            f([[s, -s, -s], [s, -s, s], [-s, -s, s], [-s, -s, -s]], [0.0, -1.0, 0.0]),
            f([[s, s, -s], [s, s, s], [s, -s, s], [s, -s, -s]], [1.0, 0.0, 0.0]),
            f([[-s, -s, -s], [-s, -s, s], [-s, s, s], [-s, s, -s]], [-1.0, 0.0, 0.0]),
        ];
        let brush = build::BrushInput {
            polys,
            oper: CsgOper::Subtract,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: Vec3::new(0.0, 0.0, 0.0),
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        };
        let m = build_geometry_bspcsg(&[brush]).unwrap();  // incremental is the default path now

        let p_base: Vec<i32> = m.surfs.iter().map(|s| s.p_base).collect();
        assert_eq!(p_base, vec![0, 1, 1, 3, 4, 2], "golden DX.dx surfs 0-5 p_base");
        let expected_bases = [
            [-s, -s, s],  // A: poly0 Origin
            [-s, s, -s],  // E: poly1/poly2 Origin
            [-s, -s, -s], // H: poly1's reversed ring, 1st push (poly5's Origin)
            [s, -s, -s],  // G: poly1's reversed ring, 2nd push (poly3's Origin)
            [s, s, -s],   // F: poly1's reversed ring, 3rd push (poly4's Origin)
        ];
        for (i, e) in expected_bases.iter().enumerate() {
            let p = &m.points[i];
            assert_eq!(
                (p.x, p.y, p.z),
                (e[0], e[1], e[2]),
                "golden DX.dx Points[{i}]"
            );
        }
    }

}
