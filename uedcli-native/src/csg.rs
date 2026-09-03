//! CSG leaf-filter — carving solid/void (§4, gap #1).  A faithful port of `bspBrushCSG`'s
//! two-direction filter, `FilterEdPoly`/`FilterLeaf` (incl. the coplanar/cospatial routing —
//! the exact-0.0 facing test that annihilates buried interior faces, §6.5), and the FOUR
//! per-CsgOper keep/discard/reverse leaf funcs (§4.3).
//!
//! **Formulation.** The world is carried as a list of surface `FPoly`s.  `FilterEdPoly`
//! classifies a fragment against a *classify BSP* (built by `build::build_bsp`) and, at each
//! leaf, the per-oper leaf func decides keep/reverse/discard — "add a node" (pass 1) and
//! "collect a survivor" (pass 2) both reduce to *push the kept FPoly to an output list*.  The
//! final Nodes/Surfs/Verts are emitted from that list by `build` (bspBuild).  This ports the
//! CSG *algorithm* (which faces survive, with which winding); exact node-plane bit-identity is
//! gated separately on the editor differential (§10.10).

use crate::build;
use crate::fpoly::FPoly;
use crate::model::{Model, Vec3};

pub const PF_SEMISOLID: u32 = 0x20;
pub const PF_NOTSOLID: u32 = 0x08;
pub const PF_PORTAL: u32 = 0x0400_0000;
const CSG_SUBTRACT_MASK: u32 = 0x28; // PF_Semisolid | PF_NotSolid

/// `ECsgOper` (§4.1): Active=0, Add=1, Subtract=2, Intersect=3, Deintersect=4.
///
/// `Active` is `Engine.Brush.CsgOper`'s CLASS DEFAULT — a brush actor gets it only when it never
/// went through a real `BRUSH ADD`/`SUBTRACT`/etc (an absent `CsgOper=` in the T3D). Disassembly
/// (`Editor.dll bspBrushCSG 0x355e0`, 2026-09-01 + the 2026-09-03 re-read, against this tree's own
/// `uned/UED22/Editor.dll`): every CsgOper dispatch is a literal ordinal test, so ordinal 0 takes
/// the "not this value" arm everywhere.  Net semantics — Subtract-SHAPED going in, but NOT
/// outcome-equivalent to Subtract:
///   * pass 1 (brush polys -> world) is exactly Subtract's (`subtractMask` `0x10035688`, filter
///     func `0x10035a84`-`0x95`: Subtract unless `==1`);
///   * the world is NEVER cut: `FilterWorldThroughBrush`'s filter body is gated on literal
///     `CsgOper==1||==2` (`0x100333dd`), so for 0 the walk does nothing;
///   * NO `bspCleanup` after the op (`0x10035dcd`-`0x35dd5`, literal `==1||==2`), so an Active
///     brush's nodes keep `NF_IsNew` until the next Add/Subtract brush's cleanup: that next
///     brush's descent sees them non-CSG (`FBspNode::IsCsg` masks NF_IsNew — its polys classify
///     against the PRE-Active solidity) and its world cut skips their whole subtree
///     (`0x100332d4`).  Live-pinned by the Paris Underground 2-brush 16/12/6-vs-14/11/2 gap
///     (spike `2026-09-03-built-parity-worst-tier`).
/// A real placed brush actor is never AUTHORED with `CsgOper=CSG_Active` on purpose — this variant
/// exists to reproduce the editor's real (likely-unintended-by-the-level-author) behavior when one
/// is, not because `Active` is a meaningful world-CSG operation in its own right. See
/// `dev/docs/board/to-build/native-materialize/vandenberg-gas-csg-active-csgoper-brush-causes/`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CsgOper {
    Active,
    Add,
    Subtract,
    Intersect,
    Deintersect,
}

// --- point-in-solid classification (the reliable classifier) ----------------
//
// The old surface-based classifier rebuilt a "classify BSP" from the accumulated world SURFACE
// list at each brush step and trusted its propagated `outside`.  For complex (non-axis-aligned)
// geometry that intermediate surface set is not perfectly watertight, so the rebuilt tree
// MISCLASSIFIES some empty regions as solid and over-discards the next brush's faces (the
// "missing walls" bug).  We instead classify every face fragment by REPLAYING CSG against the
// accumulated brushes — a point-in-solid test that never depends on a possibly-non-watertight
// surface list.  The classify BSP is kept ONLY to SPLIT faces at boundaries so the surviving
// fragments align with existing geometry; WHICH fragments survive is decided here.

/// EPS for convex membership: a point within this distance BEHIND every outward face plane counts
/// as inside.  Smaller than `EPS_NUDGE` so a nudge cleanly resolves membership of a coincident
/// plane (nudge off the plane, then test).
const EPS_CONVEX: f32 = 0.1;
/// How far to nudge a fragment centroid along ±normal to sample the solidity just in front of /
/// just behind the face (the "solid behind, void in front" boundary test).
const EPS_NUDGE: f32 = 0.5;

/// One accumulated world brush in CSG order: its WORLD-SPACE convex faces (outward normals,
/// finalized), its CsgOper, and whether it affects solidity at all.  A `PF_NotSolid`/`PF_Portal`
/// brush (`non_solid`) never changes point-in-solid.
pub struct WorldBrush {
    pub polys: Vec<FPoly>,
    pub oper: CsgOper,
    pub non_solid: bool,
}

/// True iff `p` is inside the convex hull bounded by `polys` (each an outward-facing plane):
/// behind every face within `eps`.  DX brush builders emit convex brushes, so this is exact.
fn point_in_convex(p: &Vec3, polys: &[FPoly], eps: f32) -> bool {
    if polys.len() < 4 {
        return false;
    }
    for f in polys {
        if p.sub(&f.base).dot(&f.normal) > eps {
            return false;
        }
    }
    true
}

/// Replay CSG at a point: the world starts solid (`!root_outside` for a DX level), then each
/// brush in order flips solidity inside its hull — Add -> solid, anything else -> empty.  A
/// non-solid brush (Portal/NotSolid) is skipped.  O(brushes); brushes are convex.
fn point_in_solid(p: &Vec3, brushes: &[WorldBrush], root_outside: bool) -> bool {
    let mut solid = !root_outside;
    for b in brushes {
        if b.non_solid {
            continue;
        }
        if point_in_convex(p, &b.polys, EPS_CONVEX) {
            solid = b.oper == CsgOper::Add;
        }
    }
    solid
}

/// Public point-in-solid: replay CSG at `p` against the accumulated world brushes (the reliable
/// classifier).  Used by `build` to re-derive a terminal BSP leaf's true solidity where the
/// zone-flood's `outside` propagation mis-marked it (the same propagation bug, in the final tree).
pub fn point_in_solid_world(p: &Vec3, brushes: &[WorldBrush], root_outside: bool) -> bool {
    point_in_solid(p, brushes, root_outside)
}

/// Centroid (vertex average) of a poly fragment.
fn centroid(p: &FPoly) -> Vec3 {
    let n = p.verts.len().max(1) as f32;
    let mut s = Vec3::new(0.0, 0.0, 0.0);
    for v in &p.verts {
        s = Vec3::new(s.x + v.x, s.y + v.y, s.z + v.z);
    }
    Vec3::new(s.x / n, s.y / n, s.z / n)
}

/// The TRUE outward normal of a fragment, from its winding (triangle-fan sum) — used for the
/// front/back nudge.  The stored `FPoly::normal` can be the PRE-shear axis normal on a sheared
/// brush (a diagonal wall), which is not perpendicular to the actual face; nudging along it can
/// sample the wrong side.  Falls back to the stored normal if the winding is degenerate.
fn winding_normal(p: &FPoly) -> Vec3 {
    let mut n = Vec3::new(0.0, 0.0, 0.0);
    for i in 2..p.verts.len() {
        let a = p.verts[i - 1].sub(&p.verts[0]);
        let b = p.verts[i].sub(&p.verts[0]);
        let c = a.cross(&b);
        n = Vec3::new(n.x + c.x, n.y + c.y, n.z + c.z);
    }
    let mag = n.size();
    if mag < 1.0e-4 {
        return p.normal;
    }
    Vec3::new(n.x / mag, n.y / mag, n.z / mag)
}

/// Classify a terminal fragment by sampling FULL solidity just in front of (+normal) and just
/// behind (−normal) the face.  A valid world surface has SOLID behind and VOID in front; the
/// four `Filter` values feed the unchanged per-CsgOper leaf funcs (§4.3):
///   void-front, solid-back  -> Outside            (Add/Outside keep as-authored)
///   solid-front, void-back  -> Inside             (Subtract keeps reversed)
///   solid both (buried)     -> CospatialFacingIn  (Add keeps unless semisolid; else discard)
///   void both (shared wall) -> CospatialFacingOut (all funcs discard -> annihilate)
fn classify_fragment(edpoly: &FPoly, solid_at: &dyn Fn(&Vec3) -> bool) -> Filter {
    let c = centroid(edpoly);
    let n = winding_normal(edpoly);
    let front = Vec3::new(
        c.x + n.x * EPS_NUDGE,
        c.y + n.y * EPS_NUDGE,
        c.z + n.z * EPS_NUDGE,
    );
    let back = Vec3::new(
        c.x - n.x * EPS_NUDGE,
        c.y - n.y * EPS_NUDGE,
        c.z - n.z * EPS_NUDGE,
    );
    let void_front = !solid_at(&front);
    let void_back = !solid_at(&back);
    match (void_front, void_back) {
        (true, false) => Filter::Outside,
        (false, true) => Filter::Inside,
        (false, false) => Filter::CospatialFacingIn,
        (true, true) => Filter::CospatialFacingOut,
    }
}

/// `EPolyNodeFilter` (§4.2/§4.3).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Filter {
    Outside,
    Inside,
    CoplanarOutside,
    CoplanarInside,
    CospatialFacingOut,
    CospatialFacingIn,
}

/// The per-CsgOper leaf callback (§4.3).  Pass-1 funcs (Add/Subtract) "add a node"; pass-2
/// funcs (Outside/Intersect) "collect a survivor" — both push the kept FPoly to `out`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LeafFunc {
    Add,       // 0x31770 — keep OUTSIDE/COPLANAR_OUTSIDE as-authored; +cospatial-in unless semisolid
    Subtract,  // 0x348c0 — keep INSIDE/COPLANAR_INSIDE, REVERSED
    Outside,   // 0x32390 — collect OUTSIDE/COPLANAR_OUTSIDE (fix >= 3)
    Intersect, // 0x339e0 — collect INSIDE/COPLANAR_INSIDE (fix >= 3)
}

#[derive(Debug, Clone, Copy)]
struct Coplanar {
    i_original_node: i32,
    i_back_node: i32,
    processing_back: bool,
    front_leaf_outside: bool,
}

impl Coplanar {
    fn none() -> Self {
        Coplanar {
            i_original_node: -1,
            i_back_node: -1,
            processing_back: false,
            front_leaf_outside: false,
        }
    }
}

/// The leaf callback (§4.3): decide keep/reverse/discard for `edpoly` under `filter`.  A
/// fragment that reaches a leaf and is NOT kept increments `discarded` — the caller uses
/// "discarded == 0" to know the face was un-clipped (and may emit it whole).
fn leaf_apply(
    func: LeafFunc,
    filter: Filter,
    mut edpoly: FPoly,
    out: &mut Vec<FPoly>,
    discarded: &mut usize,
) {
    use Filter::*;
    match func {
        LeafFunc::Subtract => {
            if matches!(filter, Inside | CoplanarInside) {
                edpoly.reverse();
                out.push(edpoly);
            } else {
                *discarded += 1;
            }
        }
        LeafFunc::Add => {
            if matches!(filter, Outside | CoplanarOutside) {
                out.push(edpoly);
            } else if filter == CospatialFacingIn && (edpoly.poly_flags & PF_SEMISOLID) == 0 {
                out.push(edpoly);
            } else if filter == CospatialFacingOut && (edpoly.poly_flags & PF_NOTSOLID) != 0 {
                // Keep ONLY a non-solid (Portal/NotSolid) face classified CospatialFacingOut — void
                // on both sides — which the solid-face annihilation rule ("shared wall between two
                // voids -> discard") would otherwise drop.  Such a sheet legitimately floats in
                // empty space and must survive as a splitting node so zones.rs can cut a zone
                // boundary across it (e.g. the water-surface PF_Portal separating a water zone from
                // the dry interior).  Gated on CospatialFacingOut so buried non-solid fragments
                // (CospatialFacingIn, solid both sides) are NOT caught here; those are handled as
                // the engine's csgFunc does by the non-semisolid CospatialFacingIn arm above.
                out.push(edpoly);
            } else {
                *discarded += 1;
            }
        }
        LeafFunc::Outside => {
            if matches!(filter, Outside | CoplanarOutside) && edpoly.fix() >= 3 {
                out.push(edpoly);
            } else if filter == CospatialFacingOut
                && (edpoly.poly_flags & PF_NOTSOLID) != 0
                && edpoly.fix() >= 3
            {
                // Keep ONLY a non-solid (Portal/NotSolid) world face classified CospatialFacingOut —
                // void on both sides — as a LATER brush's pass-2 filter carries it through; the same
                // void/void annihilation is correct only for SOLID faces.  This keeps the non-solid
                // sheet in the final model as a portal/splitting surf (matches the editor keeping the
                // water-surface PF_Portal faces).  The Outside func has no CospatialFacingIn keep, so
                // a fragment buried by a later SOLID brush falls through to discard — a portal is
                // never entombed between two solid leaves.
                out.push(edpoly);
            } else {
                *discarded += 1;
            }
        }
        LeafFunc::Intersect => {
            if matches!(filter, Inside | CoplanarInside) && edpoly.fix() >= 3 {
                out.push(edpoly);
            } else {
                *discarded += 1;
            }
        }
    }
}

/// `FilterLeaf` (§4.2): a fragment reached a leaf of the classify BSP.  The classify BSP is used
/// ONLY to SPLIT the face into fragments that align with existing geometry (a coplanar poly is
/// still filtered down both subtrees so it is split by neighbouring planes); the keep/discard is
/// then decided by `classify_fragment` (point-in-solid), NOT by the BSP's propagated `outside`.
fn filter_leaf(
    func: LeafFunc,
    tree: &Model,
    edpoly: FPoly,
    mut coplanar: Coplanar,
    out: &mut Vec<FPoly>,
    discarded: &mut usize,
    solid_at: &dyn Fn(&Vec3) -> bool,
) {
    if coplanar.i_original_node == -1 || coplanar.processing_back {
        // A regular fragment, OR a coplanar fragment that has now filtered down both subtrees:
        // this is its terminal leaf — classify and emit exactly once.
        let filter = classify_fragment(&edpoly, solid_at);
        leaf_apply(func, filter, edpoly, out, discarded);
    } else {
        // Just finished the FRONT descent of a coplanar poly; filter it down the back subtree too
        // (to keep splitting it against neighbouring geometry) before it reaches its terminal leaf.
        coplanar.processing_back = true;
        if coplanar.i_back_node == -1 {
            filter_leaf(func, tree, edpoly, coplanar, out, discarded, solid_at);
        } else {
            filter_ed_poly(
                func,
                tree,
                coplanar.i_back_node,
                edpoly,
                coplanar,
                out,
                discarded,
                solid_at,
            );
        }
    }
}

/// `FilterEdPoly` (§4.2): push `edpoly` down the classify BSP, splitting at each node plane so the
/// surviving fragments align with existing geometry.  The BSP is used ONLY for splitting now — the
/// inside/outside decision is deferred to `filter_leaf`/`classify_fragment` (point-in-solid).  A
/// coplanar poly is still routed down both subtrees so it gets split by neighbouring planes.
fn filter_ed_poly(
    func: LeafFunc,
    tree: &Model,
    mut i_node: i32,
    mut edpoly: FPoly,
    coplanar: Coplanar,
    out: &mut Vec<FPoly>,
    discarded: &mut usize,
    solid_at: &dyn Fn(&Vec3) -> bool,
) {
    loop {
        // Headroom split: a >=14-vert poly might overflow when SplitWithPlane adds verts.
        if edpoly.verts.len() >= 14 {
            let half = edpoly.split_in_half();
            filter_ed_poly(func, tree, i_node, half, coplanar, out, discarded, solid_at);
        }

        let node = &tree.nodes[i_node as usize];
        let i_front = node.i_front;
        let i_back = node.i_back;
        let surf = &tree.surfs[node.i_surf as usize];
        let base = tree.points[surf.p_base as usize];
        let normal = tree.vectors[surf.v_normal as usize];

        match edpoly.split_with_plane(&base, &normal, false) {
            crate::fpoly::Split::Front => {
                if i_front == -1 {
                    filter_leaf(func, tree, edpoly, coplanar, out, discarded, solid_at);
                    return;
                }
                i_node = i_front;
                continue;
            }
            crate::fpoly::Split::Back => {
                if i_back == -1 {
                    filter_leaf(func, tree, edpoly, coplanar, out, discarded, solid_at);
                    return;
                }
                i_node = i_back;
                continue;
            }
            crate::fpoly::Split::Split(front, back) => {
                if i_front == -1 {
                    filter_leaf(func, tree, front, coplanar, out, discarded, solid_at);
                } else {
                    filter_ed_poly(
                        func, tree, i_front, front, coplanar, out, discarded, solid_at,
                    );
                }
                if i_back == -1 {
                    filter_leaf(func, tree, back, coplanar, out, discarded, solid_at);
                } else {
                    filter_ed_poly(func, tree, i_back, back, coplanar, out, discarded, solid_at);
                }
                return;
            }
            crate::fpoly::Split::Coplanar => {
                if coplanar.i_original_node != -1 {
                    // Rare: a fragment barely re-coplanar with another plane — ignore.
                    return;
                }
                let cop = Coplanar {
                    i_original_node: i_node,
                    i_back_node: i_back,
                    processing_back: false,
                    front_leaf_outside: false,
                };
                if i_front == -1 {
                    filter_leaf(func, tree, edpoly, cop, out, discarded, solid_at);
                } else {
                    filter_ed_poly(func, tree, i_front, edpoly, cop, out, discarded, solid_at);
                }
                return;
            }
        }
    }
}

/// `bspFilterFPoly` (§4.2): empty-Bsp shortcut (classify the whole face), else descend from root.
fn bsp_filter_fpoly(
    func: LeafFunc,
    tree: &Model,
    edpoly: FPoly,
    out: &mut Vec<FPoly>,
    discarded: &mut usize,
    solid_at: &dyn Fn(&Vec3) -> bool,
) {
    if tree.nodes.is_empty() {
        filter_leaf(
            func,
            tree,
            edpoly,
            Coplanar::none(),
            out,
            discarded,
            solid_at,
        );
    } else {
        filter_ed_poly(
            func,
            tree,
            0,
            edpoly,
            Coplanar::none(),
            out,
            discarded,
            solid_at,
        );
    }
}

/// Filter one face and return the kept geometry, emitting the face WHOLE when the filter
/// discarded nothing (an un-clipped face must not be left fragmented by the classifier's
/// interior planes — that is what keeps a room wall a single surf when an interior brush is
/// added, while a genuinely clipped face keeps only its surviving fragments).
fn filter_face(
    func: LeafFunc,
    tree: &Model,
    face: &FPoly,
    solid_at: &dyn Fn(&Vec3) -> bool,
) -> Vec<FPoly> {
    let mut kept: Vec<FPoly> = Vec::new();
    let mut discarded = 0usize;
    bsp_filter_fpoly(
        func,
        tree,
        face.clone(),
        &mut kept,
        &mut discarded,
        solid_at,
    );
    if discarded == 0 && !kept.is_empty() {
        // Wholly kept: emit the original face, processed as the func would (Subtract reverses).
        let mut whole = face.clone();
        if func == LeafFunc::Subtract {
            whole.reverse();
        }
        return vec![whole];
    }
    kept
}

/// `bspBrushCSG` (§4.1) — apply ONE brush to the world surface-poly list.  `brush_polys` are
/// ALREADY transformed to world space (caller applies `FPoly::transform`).  Returns the new
/// world poly list (surviving world faces + kept brush fragments).
///
/// `world_brushes` is the accumulated brush list in CSG order INCLUDING this one — the
/// point-in-solid oracle used to classify every fragment (§ classifier above).  The two classify
/// BSPs (world-poly tree, brush tree) are built ONLY to SPLIT faces so the surviving fragments
/// align with existing geometry.
pub fn bsp_brush_csg(
    world_polys: Vec<FPoly>,
    brush_polys: &[FPoly],
    oper: CsgOper,
    poly_flags: u32,
    world_root_outside: bool,
    world_brushes: &[WorldBrush],
) -> Vec<FPoly> {
    let subtract_mask = if oper == CsgOper::Add {
        0
    } else {
        CSG_SUBTRACT_MASK
    };

    // FULL-solidity oracle: replay CSG against every accumulated brush (this one included).
    let solid_at = |p: &Vec3| point_in_solid(p, world_brushes, world_root_outside);

    // Transformed brush polys with CSG-adjusted flags (§4.1: (pf | PolyFlags) & ~mask).
    let mut brush: Vec<FPoly> = Vec::new();
    for (i, p) in brush_polys.iter().enumerate() {
        let mut q = p.clone();
        q.poly_flags = (q.poly_flags | poly_flags) & !subtract_mask;
        q.i_link = -1;
        q.i_brush_poly = i as i32;
        if q.finalize().is_ok() {
            brush.push(q);
        }
    }

    // Splitting tree for PASS 1: the accumulated world surfaces.
    let world_tree = build::build_bsp(&world_polys);

    // PASS 1 (brush-through-world): kept brush fragments become new world faces.
    let f1 = match oper {
        CsgOper::Add => LeafFunc::Add,
        _ => LeafFunc::Subtract,
    };
    let mut kept_brush: Vec<FPoly> = Vec::new();
    for q in &brush {
        kept_brush.extend(filter_face(f1, &world_tree, q, &solid_at));
    }

    // Splitting tree for PASS 2: the brush's own faces.
    let brush_tree = build::build_bsp(&brush);
    let f2 = match oper {
        CsgOper::Intersect => LeafFunc::Intersect,
        _ => LeafFunc::Outside,
    };
    let mut kept_world: Vec<FPoly> = Vec::new();
    for w in &world_polys {
        kept_world.extend(filter_face(f2, &brush_tree, w, &solid_at));
    }

    kept_world.extend(kept_brush);
    kept_world
}
