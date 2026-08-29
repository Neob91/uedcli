//! Zones — the native port of the editor's `TestVisibility` portalization
//! (`dev/docs/spikes/2026-07-15-native-materialize/sections/70-zones-portalization.md`).
//!
//! Runs on the finalized (engine-order topology) tree and produces:
//!   - real `FBspLeaf`s (one per empty convex terminal cell) + per-node `iLeaf` (Pass A),
//!   - a leaf-adjacency PORTAL graph (Pass B, simplified: infinite node-plane quad clipped to the
//!     node's cell, then point-region sampled either side to find the two leaves it joins),
//!   - the zone-BARRIER set (Pass B', `collect_zone_barriers`: the faithful `BlockPortal` — the
//!     leaf-PAIRS a `PF_Portal` node's REAL polygon separates; these pairs do NOT merge),
//!   - the zone flood (Pass C union-find over non-barrier portals) → `leaf.iZone` in `1..=63`,
//!     `NumZones`,
//!   - per-node `iZone[2]` bytes + the per-zone fragment SPLIT (Pass D: a face spanning two zones
//!     is split into one node per zone, matching UnrealEd's `AssignAllZones` fan-out) + `ZoneMask`
//!     (Pass E),
//!   - the `Zones` array with `Connectivity` (Pass F); `Visibility = ~0`; `ZoneActor` = 0 here
//!     (wired at assembly time from the ZoneInfo actors — mirrors `_patch_light_refs`).
//!
//! Zone 0 is the solid/outside zone (no leaves, ZoneActor 0, Connectivity `1<<0`).

use crate::model::{BspLeaf, Model, Zone};
use std::collections::HashSet;

/// Unordered leaf-pair key (min, max) — the identity a portal and a zone barrier are matched on.
#[inline]
fn pair(a: i32, b: i32) -> (i32, i32) {
    (a.min(b), a.max(b))
}

const NF_MASK_LEAF: u8 = 0x25; // IsCsg mask for leaf/zone descent: NF_NotCsg|NF_IsNew|portal(0x04)
const NF_SOLID_BOUND: u8 = 0x40; // synthetic solid-bound marker (build::NF_SOLID_BOUND)
const PF_PORTAL: u32 = 0x0400_0000;
const WORLD: f32 = 32768.0;

fn is_csg_leaf(n: &crate::model::BspNode) -> bool {
    n.num_vertices > 0 && (n.node_flags & NF_MASK_LEAF) == 0
}

// --- Pass A: real leaves ---------------------------------------------------

/// DFS the front/back tree (engine order: FRONT = iChild[1] = `i_back`, BACK = iChild[0] =
/// `i_front`); at every empty terminal child append a leaf and record `node.iLeaf[side]`.
/// `outside` propagates as `front = outside||IsCsg`, `back = outside && !IsCsg`, seeded
/// `root_outside`.  Coplanar-chain (`i_plane`) nodes are not traversed (they keep iLeaf -1).
fn assign_leaves(model: &mut Model, ni: i32, outside: bool) {
    if ni < 0 {
        return;
    }
    let (i_front, i_back, csg, solid_bound) = {
        let n = &model.nodes[ni as usize];
        (
            n.i_front,
            n.i_back,
            is_csg_leaf(n),
            (n.node_flags & NF_SOLID_BOUND) != 0,
        )
    };
    // side 1 = FRONT (i_back), side 0 = BACK (i_front)
    for (side, child) in [(1usize, i_back), (0usize, i_front)] {
        let child_out = if csg { side == 1 } else { outside };
        if child == -1 {
            // A synthetic solid-bound node's EMPTY (front) side is a zero-volume sliver coincident
            // with its parent plane — suppress its leaf (treat as solid) so it never becomes a
            // spurious isolated zone; the SOLID (back) side proceeds as normal.
            if child_out && solid_bound {
                model.nodes[ni as usize].i_leaf[side] = -1;
            } else if child_out {
                let idx = model.leaves.len() as i32;
                model.leaves.push(BspLeaf {
                    i_zone: idx, // seed: own index (union-find label)
                    i_permeating: -1,
                    i_volumetric: -1,
                    i_exclusive: u64::MAX,
                });
                model.nodes[ni as usize].i_leaf[side] = idx;
            } else {
                model.nodes[ni as usize].i_leaf[side] = -1;
            }
        } else {
            assign_leaves(model, child, child_out);
        }
    }
}

// --- Pass B: portal graph --------------------------------------------------

/// A polygon = ordered vertices; clip helpers keep the side with `n·v - w <= 0` (inside).
fn clip_poly(verts: &[[f32; 3]], n: [f32; 3], w: f32) -> Vec<[f32; 3]> {
    let mut out: Vec<[f32; 3]> = Vec::new();
    let d = |v: &[f32; 3]| n[0] * v[0] + n[1] * v[1] + n[2] * v[2] - w;
    let m = verts.len();
    for i in 0..m {
        let a = verts[i];
        let b = verts[(i + 1) % m];
        let (da, db) = (d(&a), d(&b));
        if da <= 1e-4 {
            out.push(a);
        }
        if (da < -1e-4 && db > 1e-4) || (da > 1e-4 && db < -1e-4) {
            let t = da / (da - db);
            out.push([
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
            ]);
        }
    }
    out
}

/// Two in-plane orthonormal axes for a plane normal.
fn plane_axes(n: [f32; 3]) -> ([f32; 3], [f32; 3]) {
    let (ax, ay, az) = (n[0].abs(), n[1].abs(), n[2].abs());
    let helper = if ax <= ay && ax <= az {
        [1.0, 0.0, 0.0]
    } else if ay <= az {
        [0.0, 1.0, 0.0]
    } else {
        [0.0, 0.0, 1.0]
    };
    let cross = |a: [f32; 3], b: [f32; 3]| {
        [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]
    };
    let norm = |v: [f32; 3]| {
        let l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
        if l < 1e-8 {
            [1.0, 0.0, 0.0]
        } else {
            [v[0] / l, v[1] / l, v[2] / l]
        }
    };
    let u = norm(cross(helper, n));
    let v = norm(cross(n, u));
    (u, v)
}

/// One portal record: the two empty leaves a node face joins.  Whether the pair is a ZONE barrier
/// is NOT a per-portal-face property — it is decided separately by `collect_zone_barriers` (the
/// faithful `BlockPortal`, §3), which stamps the leaf-PAIRS a `PF_Portal` node's REAL polygon
/// covers.  (The old per-generating-node `zone_portal` flag over-marked: a small portal surface in
/// a large BSP cell had its whole cell-sized infinite-quad face flagged, wrongly separating leaves
/// that share open space — the native zone over-fragmentation root cause, §70 §13.)
pub(crate) struct Portal {
    pub(crate) a: i32,
    pub(crate) b: i32,
    /// The shared polygon (`sub`/`frag` from `collect_portals`), plus the generating node's plane
    /// (`normal`/`w`, oriented toward `a` — see `collect_portals`). Consumed by
    /// `permeating_lights::collect_leaf_portals` for the beam-flood; unused by the zone union-find.
    pub(crate) poly: Vec<[f32; 3]>,
    pub(crate) normal: [f32; 3],
    pub(crate) w: f32,
}

/// Area² proxy (sum of triangle cross-products) — reject slivers below `MIN_AREA`.
const MIN_AREA: f32 = 1.0;
fn poly_area(verts: &[[f32; 3]]) -> f32 {
    if verts.len() < 3 {
        return 0.0;
    }
    let mut n = [0.0f32; 3];
    for i in 1..verts.len() - 1 {
        let a = [
            verts[i][0] - verts[0][0],
            verts[i][1] - verts[0][1],
            verts[i][2] - verts[0][2],
        ];
        let b = [
            verts[i + 1][0] - verts[0][0],
            verts[i + 1][1] - verts[0][1],
            verts[i + 1][2] - verts[0][2],
        ];
        n[0] += a[1] * b[2] - a[2] * b[1];
        n[1] += a[2] * b[0] - a[0] * b[2];
        n[2] += a[0] * b[1] - a[1] * b[0];
    }
    0.5 * (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt()
}

/// Filter `poly` down the subtree rooted at child slot `child` (`-1` => terminal leaf
/// `leaf`), collecting `(leaf_index, fragment)` for every empty leaf the poly reaches.
fn filter_child(
    model: &Model,
    child: i32,
    leaf: i32,
    poly: Vec<[f32; 3]>,
    out: &mut Vec<(i32, Vec<[f32; 3]>)>,
) {
    if poly.len() < 3 {
        return;
    }
    if child == -1 {
        out.push((leaf, poly));
    } else {
        filter_subtree(model, child, poly, out);
    }
}

/// Split `poly` at node `ni`'s plane and recurse each part into the matching child.
fn filter_subtree(
    model: &Model,
    ni: i32,
    poly: Vec<[f32; 3]>,
    out: &mut Vec<(i32, Vec<[f32; 3]>)>,
) {
    let n = &model.nodes[ni as usize];
    let pl = [n.plane.x, n.plane.y, n.plane.z];
    let w = n.plane.w;
    // FRONT (PlaneDot >= 0) => keep n·v - w >= 0 => clip by (-n, -w); child = i_back, leaf = iLeaf[1].
    let front = clip_poly(&poly, [-pl[0], -pl[1], -pl[2]], -w);
    filter_child(model, n.i_back, n.i_leaf[1], front, out);
    // BACK (<= 0) => clip by (n, w); child = i_front, leaf = iLeaf[0].
    let back = clip_poly(&poly, pl, w);
    filter_child(model, n.i_front, n.i_leaf[0], back, out);
}

/// For each node, build its face polygon (infinite plane-quad clipped to the node's cell), then
/// find EVERY (frontLeaf, backLeaf) pair the face joins by nested filtering (Pass B): filter the
/// face down the BACK subtree, then re-filter each back-fragment down the FRONT subtree.  Both
/// leaves empty => a portal (a leaf ADJACENCY).  Whether the pair is a ZONE barrier is decided
/// separately by `collect_zone_barriers` (Pass B', the faithful `BlockPortal`) — NOT from this
/// node's surf flag, which over-marks (see the `Portal` struct doc / §70 §13).
fn collect_portals(
    model: &Model,
    ni: i32,
    planes: &mut Vec<([f32; 3], f32)>,
    out: &mut Vec<Portal>,
) {
    if ni < 0 {
        return;
    }
    let n = &model.nodes[ni as usize];
    let (i_front, i_back) = (n.i_front, n.i_back);
    let pl = [n.plane.x, n.plane.y, n.plane.z];
    let (u, v) = plane_axes(pl);
    let base = [
        n.plane.x * n.plane.w,
        n.plane.y * n.plane.w,
        n.plane.z * n.plane.w,
    ];
    let mut face: Vec<[f32; 3]> = vec![
        [
            base[0] - (u[0] + v[0]) * WORLD,
            base[1] - (u[1] + v[1]) * WORLD,
            base[2] - (u[2] + v[2]) * WORLD,
        ],
        [
            base[0] + (u[0] - v[0]) * WORLD,
            base[1] + (u[1] - v[1]) * WORLD,
            base[2] + (u[2] - v[2]) * WORLD,
        ],
        [
            base[0] + (u[0] + v[0]) * WORLD,
            base[1] + (u[1] + v[1]) * WORLD,
            base[2] + (u[2] + v[2]) * WORLD,
        ],
        [
            base[0] - (u[0] - v[0]) * WORLD,
            base[1] - (u[1] - v[1]) * WORLD,
            base[2] - (u[2] - v[2]) * WORLD,
        ],
    ];
    for &(cn, cw) in planes.iter() {
        if face.len() < 3 {
            break;
        }
        face = clip_poly(&face, cn, cw);
    }
    if face.len() >= 3 && poly_area(&face) >= MIN_AREA {
        // BACK side leaves (child = i_front, terminal leaf = iLeaf[0]).
        let mut back_frags: Vec<(i32, Vec<[f32; 3]>)> = Vec::new();
        filter_child(model, i_front, n.i_leaf[0], face.clone(), &mut back_frags);
        for (back_leaf, frag) in back_frags {
            if back_leaf < 0 {
                continue;
            }
            // FRONT side leaves for this back-fragment (child = i_back, leaf = iLeaf[1]).
            let mut front_frags: Vec<(i32, Vec<[f32; 3]>)> = Vec::new();
            filter_child(model, i_back, n.i_leaf[1], frag, &mut front_frags);
            for (front_leaf, sub) in front_frags {
                if front_leaf >= 0 && front_leaf != back_leaf && poly_area(&sub) >= MIN_AREA {
                    out.push(Portal {
                        a: front_leaf,
                        b: back_leaf,
                        poly: sub.clone(),
                        normal: pl,
                        w: n.plane.w,
                    });
                }
            }
        }
    }
    // recurse children, each adding THIS node's plane oriented so the child cell is negative-side.
    if i_back != -1 {
        planes.push(([-pl[0], -pl[1], -pl[2]], -n.plane.w));
        collect_portals(model, i_back, planes, out);
        planes.pop();
    }
    if i_front != -1 {
        planes.push((pl, n.plane.w));
        collect_portals(model, i_front, planes, out);
        planes.pop();
    }
}

/// Fresh re-collection of every empty-leaf-to-empty-leaf portal (with geometry), for
/// `permeating_lights` to consume at BAKE time — the geometry-build-time `portals` local in
/// `assign_leaves_and_zones` doesn't survive past that call, but the node tree is unchanged by the
/// time lighting runs, so recomputing here is cheap and exact.
pub(crate) fn collect_leaf_portals(model: &Model) -> Vec<Portal> {
    let mut planes: Vec<([f32; 3], f32)> = Vec::new();
    let mut out = Vec::new();
    collect_portals(model, 0, &mut planes, &mut out);
    out
}

// --- Pass C: zone flood (union-find) ---------------------------------------

fn find(parent: &mut [i32], x: i32) -> i32 {
    let mut r = x;
    while parent[r as usize] != r {
        r = parent[r as usize];
    }
    // path-compress
    let mut c = x;
    while parent[c as usize] != r {
        let nx = parent[c as usize];
        parent[c as usize] = r;
        c = nx;
    }
    r
}

// --- Pass D helpers: node-polygon re-filter + fragment split -----------------
//
// The faithful port of UnrealEd's `FEditorVisibility::AssignAllZones` (`Editor.dll` RVA `0xa7400`,
// decoded in `re-raw-zones/passD-assignzones-7400.md`).  For every node in each coplanar chain we
// rebuild the node's own polygon and re-filter it through the chain HEAD's back- then front-subtree
// (the same two-pass filter Pass B uses), collecting every `(backLeaf, frontLeaf)` landing.  If the
// landings agree per side, the node keeps a single `iZone` pair; if they DISAGREE (a face spanning
// two zones — the moat/water outer walls the water portal at `z=−12` cuts), the editor kills the
// original node and emits one `NF_IsNew` fragment node per surviving (nonzero-zone) landing.  We
// reproduce the resulting node fan-out (surf 354→10 nodes, 355→10, 349/350→8, … — the 29 extra
// nodes over the never-split simplification §70 §9) by KEEPING the original as the first surviving
// fragment and APPENDING the rest onto its coplanar (`i_plane`) chain.  All fragments share the
// original node's plane, so the plane multiset gains exactly the editor's extra nodes.
//
// The VERT-POOL re-emit (§82 §10.16): the editor calls `bspAddNode` for EVERY landing of EVERY
// processed node — `bspAddNode` appends that landing's ring verts (`Verts.Add(NumVertices)`) — then
// the keep/split decision KILLS most of those fragment nodes (`NumVertices = 0`) WITHOUT reclaiming
// their verts, leaving them ORPHANED in the pool (never compacted).  So Pass D re-emits ~every
// node's ring as fresh `FVert`s (referencing existing points), taking the pool 4405→10518.  Native
// reproduces this by recording every landing as an `Emit` (in walk+landing order) and appending its
// verts: a surviving zone-split landing becomes a real `Frag` node, every other landing is an
// `Orphan` (verts appended, no node).

/// One emission from Pass D's per-node re-filter, in walk+landing order.  UnrealEd's
/// `AssignAllZones` calls `bspAddNode` for EVERY (backLeaf, frontLeaf) landing of EVERY processed
/// node, and `bspAddNode` does `iVertPool = Verts.Add(NumVertices)` — appending that landing's ring
/// verts to the pool (via `bspAddPoint`, referencing existing points).  A landing whose resulting
/// node SURVIVES the keep/split decision is a real `Frag` node; every other landing's node is killed
/// (`NumVertices = 0`) but its appended verts are NEVER reclaimed — they stay in the pool as
/// `Orphan`s (uncompacted by `bspCleanup`/`bspRefresh`, which only compact POINTS by reference).
/// This orphan re-emit is the editor's 4405→10518 vert-pool jump between `bspBuild` and `bspOptGeom`
/// (§82 §10.16); native must reproduce it to reach the editor's Verts section.
enum Emit {
    /// A landing whose node was killed (consistent-node re-emit, zoneless fragment, or the retained
    /// original's first split copy) — verts appended to the pool, referenced by no node.
    /// (The leading `usize` is the owner node index, for the UEDCLI_PASSD_DUMP diagnostic only.)
    Orphan(usize, Vec<[f32; 3]>),
    /// A surviving zone-split fragment — a real coplanar node carrying the owner's plane/surf and
    /// this landing's clipped ring, spliced onto the owner's `i_plane` chain.
    Frag {
        owner: usize,
        i_zone: [i32; 2],
        verts: Vec<[f32; 3]>,
    },
    /// The FIRST surviving fragment of a split, retargeted onto the RETAINED original node: repoint
    /// `owner`'s ring to this clipped landing (a live ring) so native's live-ring layout matches the
    /// editor's per-zone fragments (editor kills the original and keeps S clipped fragments; native
    /// keeps the original in place but gives it the first fragment's CLIPPED ring rather than its
    /// full base ring — the old base ring is thereby orphaned, exactly as the editor orphans it).
    /// This aligns `ring-sum`/`NumSharedSides` with the editor.
    OriginalRing {
        owner: usize,
        verts: Vec<[f32; 3]>,
    },
}

/// Append one landing's ring verts to `model.verts`, resolving each world point through the Points
/// pool by the editor's `bspAddPoint` dedup (EUCLIDEAN `dist < 0.002`, `THRESH_POINTS_ARE_SAME` —
/// `fp-classification-sites.md §7`; first-vs-nearest is count-invariant, only the reused index
/// differs).  Returns the base vert-pool index of the appended ring.
///
/// `create_points` controls what happens for a vertex with NO existing point within threshold:
///   * `true` (a LIVE `Frag` ring — read by render/collision/bounds): append a NEW point, so the
///     fragment's geometry is faithful (matches `bspAddPoint`'s tail-append).
///   * `false` (an ORPHAN re-emit): snap to the NEAREST existing point instead of adding one.  The
///     editor's orphan verts carry STALE point indices anyway — Pass D's killed-fragment verts are
///     never remapped by the post-D `bspRefresh` point-compaction (which only remaps LIVE node-ring
///     `vert.iVertex` and drops unreferenced points), and they are never read (no live node ring
///     references them).  So the editor's final Points pool is bounded by ring/`pBase` references,
///     NOT by orphan verts; native must likewise NOT let the orphan re-emit inflate the pool (a raw
///     append added +447 spurious points, §82 §10.16 follow-up).  The snapped index is not
///     byte-faithful to the editor's stale index, but that residual is inherent to skipping the
///     compaction dance; the point COUNT and the Verts section SIZE are what this closes.
fn append_ring_verts(model: &mut Model, verts: &[[f32; 3]], create_points: bool) -> i32 {
    let vp = model.verts.len() as i32;
    for v in verts {
        let pt = crate::model::Vec3::new(v[0], v[1], v[2]);
        // First existing point within the bspAddPoint threshold (count-invariant vs nearest).
        let mut pi = -1i32;
        for (idx, p) in model.points.iter().enumerate() {
            if pt.sub(p).size() < crate::fpoly::THRESH_POINTS_ARE_SAME {
                pi = idx as i32;
                break;
            }
        }
        if pi < 0 {
            if create_points {
                pi = model.points.len() as i32;
                model.points.push(pt);
            } else {
                // Orphan with no near point: snap to the nearest existing point (never grow the
                // pool).  Index is inert — no live ring reads this vert.
                let mut best = f32::MAX;
                for (idx, p) in model.points.iter().enumerate() {
                    let d = pt.sub(p).size();
                    if d < best {
                        best = d;
                        pi = idx as i32;
                    }
                }
                if pi < 0 {
                    pi = 0; // empty pool guard (unreachable once any point exists)
                }
            }
        }
        model.verts.push(crate::model::BspVert {
            i_vertex: pi,
            i_side: -1,
        });
    }
    vp
}

/// Collapse consecutive near-duplicate vertices (`< THRESH_POINTS_ARE_SAME`, cyclic).
///
/// This reproduces the NET geometric effect of UnrealEd's `bspAddNode` vertex-fill degenerate-drop.
/// The editor's collapse is NOT a `FPoly::Fix` pre-pass — the decode
/// (`re-raw-zones/passD-assignzones-7400.md §4/§5`) shows `AssignAllZones`'s `FilterFunc` calls
/// `bspAddNode` UNCONDITIONALLY, and the drop happens INSIDE `bspAddNode`'s vertex-fill loop
/// (`Editor.dll 0x100352c8`): it runs `bspAddPoint` per poly vertex with **consecutive-duplicate
/// dropping** (by resolved point INDEX) + a first==last dedupe, then `if final NumVertices < 3 →
/// NumVertices = 0` (the fragment is emitted with no ring — 0 pool slots).
///
/// Native's Pass-D ORPHAN path does not resolve verts the editor's way — the editor's `bspAddPoint`
/// ADDS a point when none is near, but native SNAPS an orphan vert to the nearest existing point
/// (`append_ring_verts(create_points=false)`, to avoid inflating the Points pool — §82 §10.16).  So
/// the editor's index-equality collapse cannot be replayed on native's snap-indices; the faithful
/// signal is instead the COORDINATE degeneracy the editor's fill loop is really detecting — two ring
/// corners within `THRESH_POINTS_ARE_SAME` (they would resolve to one point either way).  `clip_poly`
/// (Sutherland–Hodgman with a `1e-4` on-plane band) can push a vertex coincident with its predecessor
/// at a plane-grazing corner; on `Test_Castle.dx` exactly 3 orphan triangles are `[A, B, B]` with the
/// `B,B` edge `0.000183` uu (< `0.002`) — this collapses each to 2 verts, dropped by the caller's
/// `< 3` guard, closing the +9 vert-pool overshoot at `bspOptGeom` entry (native 10527 → 10518;
/// §70 §12).  The kept fp-noise slivers (`0.0417` uu wide) and the small triangle (`0.017` uu edges)
/// are ABOVE the threshold, so this leaves every editor-emitted ring untouched.  Applied to orphans
/// only — the live `OriginalRing`/`Frag` path resolves ADD-style like the editor and carries no
/// within-threshold corner on this map; making the collapse universal + index-based is flagged in
/// `board/inbox/` for a map that puts a grazing-corner dup on a live fragment.
fn fix_ring(verts: &[[f32; 3]]) -> Vec<[f32; 3]> {
    let n = verts.len();
    if n == 0 {
        return Vec::new();
    }
    let mut out: Vec<[f32; 3]> = Vec::with_capacity(n);
    for i in 0..n {
        let cur = verts[i];
        let prev = verts[(i + n - 1) % n];
        let d = crate::model::Vec3::new(cur[0], cur[1], cur[2])
            .sub(&crate::model::Vec3::new(prev[0], prev[1], prev[2]))
            .size();
        if d >= crate::fpoly::THRESH_POINTS_ARE_SAME {
            out.push(cur);
        }
    }
    out
}

/// Rebuild a node's stored polygon (world points) from its vertex pool.
fn node_poly(model: &Model, ni: usize) -> Vec<[f32; 3]> {
    let n = &model.nodes[ni];
    let base = n.i_vert_pool;
    let nv = n.num_vertices;
    (0..nv)
        .map(|k| {
            let vi = model.verts[(base + k) as usize].i_vertex as usize;
            let p = &model.points[vi];
            [p.x, p.y, p.z]
        })
        .collect()
}

/// Filter `poly` through chain head `head`'s BACK subtree, then re-filter each back-landing through
/// its FRONT subtree — the editor's `FilterThroughSubtree` two-pass (pass 0 = `iChild[0]`/`iLeaf[0]`,
/// pass 1 = `iChild[1]`/`iLeaf[1]`).  Returns `(backLeaf, frontLeaf, fragment)` per landing.
fn node_landings(
    model: &Model,
    head: usize,
    poly: Vec<[f32; 3]>,
) -> Vec<(i32, i32, Vec<[f32; 3]>)> {
    let (hf, hb, hl0, hl1) = {
        let n = &model.nodes[head];
        (n.i_front, n.i_back, n.i_leaf[0], n.i_leaf[1])
    };
    // pass 0: BACK subtree (engine order: BACK child = i_front, BACK leaf = iLeaf[0]).
    let mut back: Vec<(i32, Vec<[f32; 3]>)> = Vec::new();
    filter_child(model, hf, hl0, poly, &mut back);
    let mut out = Vec::new();
    for (back_leaf, frag) in back {
        // pass 1: FRONT subtree (FRONT child = i_back, FRONT leaf = iLeaf[1]).
        let mut front: Vec<(i32, Vec<[f32; 3]>)> = Vec::new();
        filter_child(model, hb, hl1, frag, &mut front);
        for (front_leaf, sub) in front {
            out.push((back_leaf, front_leaf, sub));
        }
    }
    out
}

/// One node's Pass D: re-filter its polygon, decide keep-single vs per-zone split, record the
/// node's own `iZone` in `assigns`, and push one `Emit` per landing (in landing order) so the
/// caller re-emits every landing's ring verts and creates the surviving fragment nodes.  Mirrors the
/// `AllSame` / split branches of `0xa7400` (§1 of the decode) AND its per-landing `bspAddNode` vert
/// append (§82 §10.16).
fn passd_process(
    model: &Model,
    head: usize,
    m: usize,
    assigns: &mut Vec<(usize, [i32; 2])>,
    emissions: &mut Vec<Emit>,
) {
    let (nv, base) = {
        let n = &model.nodes[m];
        (n.num_vertices, n.i_vert_pool)
    };
    if nv < 3 || base < 0 {
        return; // degenerate / no real face — leave iZone (0,0), like the editor's OldNum==Num skip
    }
    let poly = node_poly(model, m);
    let landings = node_landings(model, head, poly);
    if landings.is_empty() {
        return;
    }
    // Orientation `k = (dot(Head.Plane.N, Node.Plane.N) < 0)`: maps back/front leaf zones onto
    // iZone[0]/iZone[1].  For a chain HEAD dot>0 ⇒ k=0 (iZone[0]=back, iZone[1]=front); a flipped
    // coplanar chain MEMBER gets k=1.
    let hn = {
        let p = &model.nodes[head].plane;
        [p.x, p.y, p.z]
    };
    let mn = {
        let p = &model.nodes[m].plane;
        [p.x, p.y, p.z]
    };
    let dot = hn[0] * mn[0] + hn[1] * mn[1] + hn[2] * mn[2];
    let k = if dot < 0.0 { 1usize } else { 0usize };
    let zof = |leaf: i32| -> i32 {
        if leaf < 0 {
            0
        } else {
            model.leaves[leaf as usize].i_zone
        }
    };
    // NOTE on the editor's `SplitWithNode(VeryPrecise=1)` `r==0` coplanar-DROP (decode §3/§7): a
    // fragment coplanar with a deeper filter node is dropped with no landing.  Native's `clip_poly`
    // has no exact analogue, but the case is effectively unreachable here — a face coplanar with
    // another node lives on that node's `i_plane` CHAIN, not down the head's front/back SUBTREE that
    // we filter through — so on the calibration map it never fires (node count + plane multiset are
    // byte-exact without any drop).  A `MIN_AREA` landing guard was tried and REJECTED: the coplanar
    // double-count is a FULL-area duplicate (not a thin sliver), so an area threshold doesn't catch
    // it, and it instead dropped one legitimate small face — regressing the otherwise-exact per-node
    // iZone distribution (introducing a spurious `(0,0)` node the editor lacks).  If a future map
    // shows fragment-count drift from coplanar faces, port the real `r==0` classification here.
    let mut fr: Vec<([i32; 2], Vec<[f32; 3]>)> = Vec::new();
    for (bl, fl, sub) in landings {
        let (bz, fz) = (zof(bl), zof(fl));
        let mut iz = [0i32; 2];
        iz[k] = bz;
        iz[k ^ 1] = fz;
        fr.push((iz, sub));
    }
    // Zone[side] = last nonzero iZone[side]; AllSame iff no fragment disagrees on a nonzero side.
    let mut zone = [0i32; 2];
    for (iz, _) in &fr {
        for s in 0..2 {
            if iz[s] != 0 {
                zone[s] = iz[s];
            }
        }
    }
    let mut all_same = true;
    for (iz, _) in &fr {
        for s in 0..2 {
            if iz[s] != 0 && iz[s] != zone[s] {
                all_same = false;
            }
        }
    }
    if all_same {
        // Consistent both sides — original node keeps the agreed pair, no split.  The editor appends
        // per-landing fragments here, then zeroes ALL of them and re-tags the original with the
        // agreed pair; `bspCleanup` culls the killed fragments' NODES but NOT their appended VERTS —
        // so every landing is re-emitted as ORPHAN verts (the dominant part of the 4405→10518 pool
        // growth, §82 §10.16).
        assigns.push((m, zone));
        for (_iz, sub) in fr {
            emissions.push(Emit::Orphan(m, sub));
        }
    } else {
        // Disagreement (face spans two zones) — the editor kills the original and keeps one fragment
        // per surviving (nonzero-zone) landing; `bspCleanup` then culls the killed original.  NET:
        // the surf fans out to `surviving.len()` coplanar nodes.  Native reproduces that COUNT and
        // PLANE set by KEEPING the original as the first fragment (re-tagged to its zone) and
        // appending the other `surviving.len()-1` onto its `i_plane` chain — verified node-for-node
        // against the real final map (`node_diff.py`: 1156 nodes / plane multiset 0 residual).
        // NOTE: the retained original keeps its FULL polygon (not the clipped first piece), so its
        // face is single-zoned where the editor's would be partitioned — a render-fidelity nuance
        // that is out of scope here (the byte gate is node count + plane multiset, NOT in-game
        // render; and the resulting per-node iZone distribution already matches the editor exactly,
        // with zero (0,0) solid-solid nodes — §70 §9).
        //
        // VERTS: every landing is re-emitted (§82 §10.16).  The original is KEPT in place with its
        // full base ring, so the first surviving landing's clipped copy becomes an ORPHAN (the
        // editor's referenced surviving[0] fragment ↔ native's orphaned copy — same vert COUNT,
        // different reference); the remaining surviving landings become real `Frag` nodes; every
        // zoneless landing is an ORPHAN.  Emitting IN LANDING ORDER matches the editor's per-landing
        // `bspAddNode` append order.
        let iz0 = match fr.iter().find(|(iz, _)| iz[0] != 0 || iz[1] != 0) {
            Some((iz, _)) => *iz,
            None => {
                // No surviving zone (unreachable when all_same is false, but stay faithful): the
                // editor still appended every landing's verts before killing all of them.
                for (_iz, sub) in fr {
                    emissions.push(Emit::Orphan(m, sub));
                }
                return;
            }
        };
        assigns.push((m, iz0));
        let mut first_surv = false;
        for (iz, sub) in fr {
            let surviving = iz[0] != 0 || iz[1] != 0;
            if surviving && !first_surv {
                first_surv = true;
                // Retarget the retained original onto this clipped fragment ring (editor parity:
                // the original's full base ring is orphaned, the node carries the first zone piece).
                emissions.push(Emit::OriginalRing {
                    owner: m,
                    verts: sub,
                });
            } else if surviving {
                emissions.push(Emit::Frag {
                    owner: m,
                    i_zone: iz,
                    verts: sub,
                });
            } else {
                emissions.push(Emit::Orphan(m, sub));
            }
        }
    }
}

/// Recurse the front/back tree (editor order: FRONT = `i_back`, then BACK = `i_front`); at every
/// node reached (a coplanar-chain HEAD, since chain members are never `iChild` targets) walk its
/// `i_plane` chain and Pass-D each member, filtered through the HEAD's subtrees.
fn passd_walk(
    model: &Model,
    h: i32,
    assigns: &mut Vec<(usize, [i32; 2])>,
    emissions: &mut Vec<Emit>,
) {
    if h < 0 {
        return;
    }
    let (front_child, back_child) = {
        let n = &model.nodes[h as usize];
        (n.i_back, n.i_front)
    };
    passd_walk(model, front_child, assigns, emissions);
    passd_walk(model, back_child, assigns, emissions);
    let mut m = h;
    while m >= 0 {
        passd_process(model, h as usize, m as usize, assigns, emissions);
        m = model.nodes[m as usize].i_plane;
    }
}

// --- Pass B': zone barriers (the faithful BlockPortal, §3 / §70 §13) --------
//
// A ZONE boundary is NOT "any portal generated by a node whose surf is PF_Portal" — that flags the
// node's whole cell-sized infinite-quad face, which for a small portal surface (a water pane) in a
// large BSP cell wrongly separates leaves that share open space (native's zone over-fragmentation
// root cause: on `10_Paris_Catacombs`'s OWN editor tree the old rule marked 1084 within-zone faces
// as barriers, shattering 17 editor zones into 56).  The editor's `MakePortals` instead runs
// `BlockPortal` (§3): for each `PF_Portal`-surf node it takes the node's REAL stored polygon (NOT an
// infinite quad), re-filters it through the tree, and stamps as a zone boundary every leaf-PAIR the
// real polygon actually lands between.  Pass C then keeps those pairs apart and merges every other
// adjacency.
//
// This reproduces that exactly, as a mechanical copy of the validated oracle
// (`harness/zone_flood_oracle.py::blockportal_interior_zones`): enumerate EVERY node flat, and for
// each whose surf is `PF_Portal`, re-filter its real polygon (`node_poly`) through its coplanar-chain
// HEAD's back-then-front subtrees (`node_landings`, the same two-pass filter Pass B/D use), recording
// every `(backLeaf, frontLeaf)` landing as an unordered barrier pair.  Filtering through the HEAD
// (not the node itself) is load-bearing: a `PF_Portal` surf on a coplanar-chain MEMBER has
// `i_front/i_back = -1` and would yield no landing on its own — its front/back space is partitioned
// by the chain head's subtrees.
//
// A FLAT enumeration (not a `passd_walk`-style front/back recursion) is deliberate: a recursion from
// the root reaches only nodes on the main `i_front/i_back/i_plane` graph, but coplanar-chain roots
// can sit OFF that graph — Pass E (`build_zone_mask`'s follow-up loop below) exists precisely because
// such nodes "may be unreached".  A `PF_Portal` surf on an unreached node would then be silently
// skipped, dropping its barrier and MERGING two zones the editor keeps apart (under-fragmentation).
// The flat enumeration + `head_of` (walk `i_plane` predecessors up to the first tree node) removes
// that reachability assumption and is provably identical to the oracle.  `head_of` is cycle-guarded
// (`seen < n`) like the oracle.  Validated leaf-pair-exact against all four editor goldens
// (`zone_flood_oracle.py` [D7]): interior-zone counts 3/6/4/16 = editor for
// Castle/UNATCO/HKMarket/Catacombs; and the shipped Rust reproduces the oracle on the real native
// trees (NativeUnatco 45 = oracle 44+1, NativeCatacombs 43 = oracle 42+1).  Runs on the pre-Pass-D
// tree (before `passd_walk` appends fragment nodes), so every node still carries its full CSG polygon.
fn collect_zone_barriers(model: &Model) -> HashSet<(i32, i32)> {
    let mut barriers: HashSet<(i32, i32)> = HashSet::new();
    let n = model.nodes.len();
    if n == 0 {
        return barriers;
    }
    // `is_tree`: root + every i_front/i_back target (a coplanar-chain member is an i_plane target
    // only, never a front/back child of a valid BSP).
    let mut is_tree = vec![false; n];
    is_tree[0] = true;
    for nd in &model.nodes {
        for &c in &[nd.i_front, nd.i_back] {
            if c >= 0 {
                is_tree[c as usize] = true;
            }
        }
    }
    // `iplane_pred`: inverse of the i_plane chain link (chain member -> the node that links to it).
    let mut iplane_pred = vec![-1i32; n];
    for (i, nd) in model.nodes.iter().enumerate() {
        if nd.i_plane >= 0 {
            iplane_pred[nd.i_plane as usize] = i as i32;
        }
    }
    // `head_of`: from any node, walk i_plane predecessors up to the first tree node = its chain head.
    let head_of = |mut ni: i32| -> i32 {
        let mut seen = 0usize;
        while !is_tree[ni as usize] && iplane_pred[ni as usize] >= 0 && seen < n {
            ni = iplane_pred[ni as usize];
            seen += 1;
        }
        ni
    };
    for ni in 0..n {
        let nd = &model.nodes[ni];
        if nd.i_surf < 0 || (nd.i_surf as usize) >= model.surfs.len() {
            continue;
        }
        if (model.surfs[nd.i_surf as usize].poly_flags & PF_PORTAL) == 0 {
            continue;
        }
        if nd.num_vertices < 3 || nd.i_vert_pool < 0 {
            continue;
        }
        let head = head_of(ni as i32) as usize;
        let poly = node_poly(model, ni);
        for (bl, fl, _sub) in node_landings(model, head, poly) {
            if bl >= 0 && fl >= 0 && bl != fl {
                barriers.insert(pair(bl, fl));
            }
        }
    }
    barriers
}

// --- top-level -------------------------------------------------------------

/// Full leaf + zone assignment (replaces the single-zone stub).  Call ONCE per build: the reset
/// below clears leaves/`iZone`/`ZoneMask` but does NOT remove the Pass D fragment nodes/points/verts
/// this appends (nor undo their `i_plane` splices), so a second call would re-walk them as real
/// chain members and append more — not idempotent.  (Called once from `build.rs`'s
/// `finalize_leaves_and_bbox` and once from `bspcsg.rs`'s `zone_pass`.)
///
/// Returns the Pass-D split-group node indices in the editor's array-emission order (`[original,
/// frag1, …]` per split, in `passd_walk` order).  The `bspcsg` pipeline relabels the node array to
/// move exactly these to the tail (a pure, tree-preserving permutation) so the on-disk node ORDER
/// matches `Test_Castle.dx` positionally; the legacy `build.rs` path ignores it.
pub fn assign_leaves_and_zones(model: &mut Model) -> Vec<usize> {
    // reset
    model.leaves.clear();
    for n in model.nodes.iter_mut() {
        n.i_leaf = [-1, -1];
        n.i_zone = [0, 0];
        n.zone_mask = 0;
    }
    if model.nodes.is_empty() {
        model.zones = vec![Zone {
            actor_ref: 0,
            connectivity: 0x1,
            visibility: u64::MAX,
        }];
        return Vec::new();
    }

    // Pass A: real leaves.
    let root_outside = model.root_outside;
    assign_leaves(model, 0, root_outside);
    if model.leaves.is_empty() {
        // no empty space (fully solid) — emit the two-zone stub so the engine doesn't index empty.
        model.zones = vec![
            Zone {
                actor_ref: 0,
                connectivity: 0x1,
                visibility: u64::MAX,
            },
            Zone {
                actor_ref: 0,
                connectivity: 0x2,
                visibility: u64::MAX,
            },
        ];
        return Vec::new();
    }
    let n_leaves = model.leaves.len();

    // Pass B: portal graph.
    let mut portals: Vec<Portal> = Vec::new();
    {
        let mut planes: Vec<([f32; 3], f32)> = Vec::new();
        collect_portals(model, 0, &mut planes, &mut portals);
    }

    // Pass B': zone barriers (faithful BlockPortal) — the leaf-PAIRS a PF_Portal node's REAL
    // polygon separates.  Runs on the pre-Pass-D tree (nodes still carry full CSG polygons).
    let barriers = collect_zone_barriers(model);

    // Pass C: union-find over NON-barrier portals (merge connected leaves); a portal whose leaf-pair
    // is a zone barrier keeps its two leaves apart.
    let mut parent: Vec<i32> = (0..n_leaves as i32).collect();
    for p in &portals {
        if !barriers.contains(&pair(p.a, p.b)) {
            let (ra, rb) = (find(&mut parent, p.a), find(&mut parent, p.b));
            if ra != rb {
                parent[ra as usize] = rb;
            }
        }
    }
    // compact component roots to dense zone ids in first-seen leaf order.
    let mut dense: Vec<i32> = vec![-1; n_leaves];
    let mut n_zones_found = 0i32;
    for i in 0..n_leaves as i32 {
        let r = find(&mut parent, i);
        if dense[r as usize] < 0 {
            dense[r as usize] = n_zones_found;
            n_zones_found += 1;
        }
    }
    // leaf.iZone = (dense % 63) + 1  (zones 1..=63; zone 0 reserved for solid).
    for i in 0..n_leaves {
        let r = find(&mut parent, i as i32);
        let z = (dense[r as usize] % 63) + 1;
        model.leaves[i].i_zone = z;
        // -1 = "no participating light reaches this leaf" (the correct sentinel; region 1 of
        // `Model.Lights` isn't ported yet -- see `port-the-per-leaf-permeating-light-lists-model`
        // -- but a bogus `0` here would misleadingly alias whatever ends up at `Lights[0]`).
        model.leaves[i].i_permeating = -1;
    }
    let num_zones = (n_zones_found + 1).min(64); // + zone 0

    // Pass D: per-node iZone[side] + the per-zone fragment SPLIT (faithful `AssignAllZones`,
    // `re-raw-zones/passD-assignzones-7400.md`).  Walk the tree; for each coplanar-chain member,
    // re-filter its polygon through the chain head's subtrees to find every (backLeaf, frontLeaf)
    // landing.  Consistent landings ⇒ the node keeps one iZone pair; landings disagreeing on a
    // side ⇒ the face spans two zones (the moat/water outer walls the `z=−12` water portal cuts),
    // and the editor kills the node and emits one fragment per surviving zone.  We keep the
    // original as the first fragment and append the rest onto its `i_plane` chain (same plane), so
    // the node count and plane multiset gain exactly the editor's fan-out (e.g. surf 354→10 nodes).
    let mut assigns: Vec<(usize, [i32; 2])> = Vec::new();
    let mut emissions: Vec<Emit> = Vec::new();
    passd_walk(model, 0, &mut assigns, &mut emissions);
    for (idx, iz) in assigns {
        model.nodes[idx].i_zone = iz;
    }
    // Consume the ordered emissions (walk+landing order, the editor's per-landing `bspAddNode`
    // order).  Every landing appends its ring verts to the pool (`append_ring_verts`, bspAddPoint
    // dedup); an `Orphan` adds only verts (no node — the editor's killed fragments, whose verts stay
    // uncompacted → the +6113-vert re-emit that takes the pool 4405→10518, §82 §10.16), a `Frag`
    // additionally creates a real coplanar node spliced onto the owner's `i_plane` chain.
    //
    // `tail_order` records the editor's NODE-ARRAY EMISSION ORDER for the split groups so the caller
    // (`bspcsg::finalize`) can relabel the node array to match `Test_Castle.dx` byte-for-byte (node
    // planes positional, not just multiset).  UnrealEd's `AssignAllZones` KILLS each split original
    // and appends ALL its zone fragments at the TAIL of `Model->Nodes` (then `bspCleanup` removes the
    // dead original) — so every split node, original included, lands in the tail cluster in walk
    // order.  Native instead KEEPS the original in place (early index) and appends only the extra
    // fragments, which scatters the group and makes the on-disk node ORDER diverge from the editor
    // even though the TREE is node-for-node isomorphic (§82 §10.17).  We therefore emit, per split
    // (in walk order — the editor's order), `[original, frag1, frag2, …]`; the caller moves exactly
    // these nodes to the array tail in this order (a pure, tree-preserving relabel).  A node's `Frag`
    // emissions are contiguous (each node is Pass-D'd once), so tracking the last frag owner delimits
    // one split group even with interleaved orphans.
    let mut tail_order: Vec<usize> = Vec::new();
    let mut last_frag_owner: i32 = -1;
    let dump_emit = std::env::var("UEDCLI_PASSD_DUMP").is_ok();
    for e in emissions {
        match e {
            Emit::Orphan(owner, verts) => {
                // Reproduce the editor's `bspAddNode` degenerate-drop (the collapse lives INSIDE
                // `bspAddNode`, not a pre-pass — see `fix_ring` doc + `passD-assignzones-7400.md §5`).
                // A ring left with < 3 real verts is a fragment whose vertex-fill collapsed below
                // `NumVertices==3`, so the editor emits it with 0 pool slots — closing the +9 orphan
                // overshoot (§70 §12).
                let verts = fix_ring(&verts);
                if verts.len() < 3 {
                    continue; // degenerate landing — editor's NumVertices<3 fragment (still no node)
                }
                let vp = model.verts.len();
                if dump_emit {
                    eprintln!("EMIT type=Orphan owner={} isurf={} vp={} len={}", owner, model.nodes[owner].i_surf, vp, verts.len());
                }
                append_ring_verts(model, &verts, false); // never grow the point pool for orphans
            }
            Emit::OriginalRing { owner, verts } => {
                if verts.len() < 3 {
                    continue; // degenerate first fragment — leave the original's base ring in place
                }
                // `create_points=true` is EDITOR-FAITHFUL: the editor's surviving zone fragments are
                // live rings filled by `bspAddPoint`, which appends a genuinely-new corner when none
                // is near (the editor's own Pass D adds ~+3 such points).  On the calibration castle
                // this is measured ZERO-delta — the first fragment's clip corners are all shared with
                // an adjacent surviving `Frag` piece (a false `all_same` means ≥2 surviving zone
                // pieces), so `model.points.len()` stays 2061 (ground_truth_bytediff, §70 §11).  A new
                // point here on some other map would MATCH the editor (its live fragment adds it too).
                let vp = append_ring_verts(model, &verts, true); // live ring — faithful geometry
                if dump_emit {
                    eprintln!("EMIT type=OrigRing owner={} isurf={} vp={} len={}", owner, model.nodes[owner].i_surf, vp, verts.len());
                }
                let n = &mut model.nodes[owner];
                n.i_vert_pool = vp;
                n.num_vertices = verts.len() as i32;
            }
            Emit::Frag {
                owner,
                i_zone,
                verts,
            } => {
                if verts.len() < 3 {
                    continue;
                }
                let vp = append_ring_verts(model, &verts, true); // live ring — faithful geometry
                if dump_emit {
                    eprintln!("EMIT type=Frag owner={} isurf={} vp={} len={}", owner, model.nodes[owner].i_surf, vp, verts.len());
                }
                let (plane, i_surf, node_flags) = {
                    let n = &model.nodes[owner];
                    (n.plane, n.i_surf, n.node_flags) // owner flags NF_IsNew-cleared by the caller
                };
                let new_idx = model.nodes.len() as i32;
                model.nodes.push(crate::model::BspNode {
                    plane,
                    zone_mask: 0,
                    node_flags,
                    i_vert_pool: vp,
                    i_surf,
                    i_front: -1,
                    i_back: -1,
                    i_plane: -1,
                    i_collision_bound: -1,
                    i_render_bound: -1,
                    i_zone,
                    num_vertices: verts.len() as i32,
                    i_leaf: [-1, -1],
                });
                // Splice onto the tail of the owner's coplanar (i_plane) chain.
                let mut t = owner as i32;
                while model.nodes[t as usize].i_plane >= 0 {
                    t = model.nodes[t as usize].i_plane;
                }
                model.nodes[t as usize].i_plane = new_idx;
                // tail_order: push the owner once per split group (first frag seen), then this frag.
                if last_frag_owner != owner as i32 {
                    tail_order.push(owner);
                    last_frag_owner = owner as i32;
                }
                tail_order.push(new_idx as usize);
            }
        }
    }

    // TEMP diagnostic (UEDCLI_PASSD_DUMP): full vert-pool layout right after Pass-D re-emit —
    // per-node iVertPool/NumVertices + total verts — so the orphan-run structure can be diffed vs
    // the editor's `editor-preopt-nodes.log` (§70 §11 +9 orphan localization).  Node order/links
    // change in `reorder_nodes_to_tail` after this, but ivp/nv per node do not, so this equals the
    // PREOPT vert layout.  Default path byte-unchanged.
    if std::env::var("UEDCLI_PASSD_DUMP").is_ok() {
        eprintln!("PASSD verts={} nodes={}", model.verts.len(), model.nodes.len());
        for (i, n) in model.nodes.iter().enumerate() {
            eprintln!("PD node={} ivp={} nv={} isurf={}", i, n.i_vert_pool, n.num_vertices, n.i_surf);
        }
    }

    build_zone_masks(model);

    // The zone pass writes NOTHING into any FBspSurf: the editor's `TestVisibility` doesn't
    // (re-raw-zones/passD-assignzones-7400.md §3), and the two u16 slots it used to stamp a zone pair
    // into are really `PanU`/`PanV`, the authored texture pan (evidence on `model::BspSurf::pan`).
    // Zeroing them erased the pan from every surface, so that loop is gone.  `Test_Castle.dx` ships
    // all-zero there, which is what put the old reading in — but that map is not in-repo to re-check,
    // and an all-zero pan is exactly what a map with no `Pan U=/V=` on any poly would store.

    // Pass F: Zones array + Connectivity (self-bit; OR across zone portals).
    let mut zones: Vec<Zone> = (0..num_zones)
        .map(|z| Zone {
            actor_ref: 0,
            connectivity: 1u64 << (z as u64 & 63),
            visibility: u64::MAX,
        })
        .collect();
    for p in &portals {
        if barriers.contains(&pair(p.a, p.b)) {
            let za = model.leaves[p.a as usize].i_zone;
            let zb = model.leaves[p.b as usize].i_zone;
            if za > 0 && zb > 0 && (za as usize) < zones.len() && (zb as usize) < zones.len() {
                zones[za as usize].connectivity |= 1u64 << (zb as u64 & 63);
                zones[zb as usize].connectivity |= 1u64 << (za as u64 & 63);
            }
        }
    }
    model.zones = zones;
    tail_order
}

/// Pass E, `BuildZoneMasks`: node `ZoneMask` = OR of `1<<iZone` over self + children + coplanar
/// chain (zone 0 sets no bit).  `bspBuildBounds` runs it a SECOND time (spec §8 step 1), which is
/// what stamps the nodes the detail-brush layer appended after `TestVisibility` — they are born with
/// `ZoneMask` all-ones and would otherwise ship that sentinel.
pub fn build_zone_masks(model: &mut Model) {
    if model.nodes.is_empty() {
        return;
    }
    // Zero first: the fallback below reads `zone_mask == 0` as "the recursion never reached this
    // node", which is only true from a cleared start.  A node born after an earlier run of this pass
    // carries `u64::MAX`, and would otherwise be skipped by both the recursion and the fallback.
    for n in model.nodes.iter_mut() {
        n.zone_mask = 0;
    }
    build_zone_mask(model, 0);
    // Coplanar-chain roots off the main tree may be unreached; OR their own bits directly.
    for ni in 0..model.nodes.len() {
        if model.nodes[ni].zone_mask == 0 {
            let mut m = 0u64;
            for z in model.nodes[ni].i_zone {
                if z > 0 {
                    m |= 1u64 << (z as u64 & 63);
                }
            }
            model.nodes[ni].zone_mask = m;
        }
    }
}

/// Recursive `ZoneMask` (Pass E): OR of `1<<iZone[k]` over self + children + coplanar chain.
fn build_zone_mask(model: &mut Model, ni: i32) -> u64 {
    if ni < 0 {
        return 0;
    }
    let (i_front, i_back, i_plane, z0, z1) = {
        let n = &model.nodes[ni as usize];
        (n.i_front, n.i_back, n.i_plane, n.i_zone[0], n.i_zone[1])
    };
    let mut m = 0u64;
    if z0 > 0 {
        m |= 1u64 << (z0 as u64 & 63);
    }
    if z1 > 0 {
        m |= 1u64 << (z1 as u64 & 63);
    }
    m |= build_zone_mask(model, i_back);
    m |= build_zone_mask(model, i_front);
    m |= build_zone_mask(model, i_plane);
    model.nodes[ni as usize].zone_mask = m;
    m
}

#[cfg(test)]
mod tests {
    use super::fix_ring;

    /// Engine-fact regression for the Pass-D orphan `bspAddNode` degenerate-drop (§70 §12).
    /// UnrealEd's `bspAddNode` vertex-fill collapses corners within `THRESH_POINTS_ARE_SAME` and
    /// emits no ring when < 3 survive; `fix_ring` reproduces that on native's Pass-D orphan rings.
    /// The three constants are the real values measured on `Test_Castle.dx`: the three dropped
    /// orphan triangles have a `0.000183`-uu duplicate edge; the kept fp-noise sliver quads are
    /// `0.0417`-uu wide and the kept small triangle has `0.017`-uu edges.
    #[test]
    fn fix_ring_drops_degenerate_but_keeps_thin_slivers() {
        // [A, B, B] with the B,B corner 0.000183 uu apart (< 0.002) -> collapses to 2 verts.
        let degenerate = [
            [-878.53, 832.53, 250.0],
            [-892.39, 818.67, 250.0],
            [-892.39 + 0.000183, 818.67, 250.0],
        ];
        assert!(
            fix_ring(&degenerate).len() < 3,
            "an [A,B,B] triangle with a sub-0.002 duplicate edge must collapse below 3 verts (dropped)"
        );

        // fp-noise sliver QUAD: two 0.0417-uu-wide edges (> 0.002) — the editor KEEPS it as nv=4.
        let sliver_quad = [
            [-112.0, -160.0, 160.0],
            [-111.958, -160.0, 160.0],
            [-111.958, -128.0, 160.0],
            [-112.0, -128.0, 160.0],
        ];
        assert_eq!(
            fix_ring(&sliver_quad).len(),
            4,
            "a 0.0417-uu-wide sliver quad is above THRESH_POINTS_ARE_SAME and must survive intact"
        );

        // Genuine small triangle, ~0.017-0.024-uu edges (> 0.002) — the editor KEEPS it as nv=3.
        let small_tri = [
            [44.0, -208.04, 0.0],
            [44.0, -208.06, 0.0],
            [44.02, -208.04, 0.0],
        ];
        assert_eq!(
            fix_ring(&small_tri).len(),
            3,
            "a genuine small triangle with all edges above the merge radius must survive"
        );

        // A clean quad with no near-duplicate is returned unchanged.
        let clean = [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0, 10.0, 0.0],
            [0.0, 10.0, 0.0],
        ];
        assert_eq!(fix_ring(&clean).len(), 4);
    }
}
