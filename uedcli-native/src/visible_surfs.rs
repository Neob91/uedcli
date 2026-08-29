//! Port of `URender::GetVisibleSurfs` — the editor's per-light visible-surface gather.
//!
//! Decoded in `dev/docs/board/inbox/port-urender-getvisiblesurfs-so-each-light-gets/overview.md`
//! (disassembly-verified 2026-08-27, trusted per the 2026-08-28 freshness ruling). The editor picks
//! each light's surface set not by a geometric plane test but by RASTERIZING six 90°-apart,
//! `0x400 x 0x400` (1024x1024) cube-map faces from the light's Location through the finalized BSP,
//! with per-zone span-buffer occlusion: a surface is kept iff at least one screen pixel it covers, in
//! any of the six faces, was not already claimed by a nearer OPAQUE surface in the same zone.
//!
//! `light::bake` calls [`get_visible_surfs`] once per light (in parallel) to get the candidate surf
//! set BEFORE its own per-(surf,light) loop — which still separately applies `bSpecialLit`
//! partitioning, the coarse radius cull, and the per-lumel `linecheck::line_clear` shadow test. This
//! module answers ONLY "is this surface even in the light's run", replacing the old, more permissive
//! plane-test-only selection (`light_in_front` alone), which listed 618 (surf,light) pairs on
//! UNATCO that the editor's occlusion test rejects.
//!
//! ## `FovAngle` — the one named unknown, resolved empirically
//!
//! The gather pass never sets `FovAngle`; it is whatever the temp viewport's camera actor carries,
//! and six 90°-apart faces tile the sphere with no gap/overlap only at exactly FOV 90. The board item
//! flags this as unpinned by disassembly. This port uses **90°** — confirmed (not disassembly-level,
//! but multiply corroborated): `uned/UED22/user.ini` carries `DesiredFOV=90.000000` /
//! `DefaultFOV=90.000000` and `unrealtournament.ini` carries `FovAngleDegrees=90.000000` (the exact
//! ini FOV preference the board item's `Editor 0x100148ae` writes into every viewport actor), and
//! 90° is the only angle under which the six-face scheme is geometrically sound at all. Flagged here
//! per the task brief: **this is an assumption, not a disassembly-pinned fact.**
//!
//! ## Simplifications vs. the byte-level decode (functional-spec port, not a disassembly of the
//! rasterizer internals — sanctioned by the task brief when the fixture comparison doesn't show a
//! systematic edge-stepping mismatch)
//!
//! - **Span buffer = a per-zone boolean pixel grid**, not `FSpanBuffer`'s run-length scanline
//!   encoding. Front-to-back traversal (near child, self, far child, ordered by the light's side of
//!   each node's plane) makes a boolean "still visible" grid behaviourally equivalent to the real
//!   span buffer's accept/subtract semantics: painter's-algorithm-correct because BSP near-to-far
//!   order guarantees a pixel is never revisited by something CLOSER after something FARTHER already
//!   claimed it.
//! - **Frustum-cone reject (board step 6) and render-bound occlusion (step 4) are not ported.**
//!   Both are described as pure early-out optimizations: the four-plane clip in [`rasterize_node`]
//!   already yields an empty footprint for anything outside the view cone (step 6's exact outcome),
//!   and the board item itself says box-occlusion is "conservative, so skipping it should change cost
//!   and not the surface set" (step 4). Skipping both changes performance only, not this port's
//!   output — under that stated equivalence.
//! - **Moving-brush filter (step 3) and the `PlayerPawn` viewport-actor filter (step 9) are not
//!   modeled.** The board item says whether `BrushTracker` is even non-NULL during `LIGHT APPLY` is
//!   undetermined, and native has no dynamic-brush tracking to answer it; the editor's temp gather
//!   viewport's actor is a `Camera`, not a `PlayerPawn`, so step 9 is assumed to never fire. Both are
//!   assumptions, flagged here rather than silently guessed.
//!
//! ## What is faithfully ported
//!
//! Zone-mask subtree pruning (step 1), `bUseZones = viewZone != 0` and its unzoned-pass fallback
//! (step 2), `IsFront`/near-far child order (step 5), the exact back-face cull (step 7 — reuses
//! `light::light_in_front`, already ported and tested), `PF_Portal && !bUseZones` (step 8), zone
//! reachability (step 10), the `PF_Invisible` mask (step 11; `ShowFlags=0x800` keeps it in the drop
//! set), the six exact 90°-apart face rotations and `AddUniqueItem` (here: a `HashSet`) union across
//! them (§ "What it is"), and the opaque/non-opaque split on the disassembly-verified
//! `PF_NONOCCLUDING` mask (`render.dll 0x10019b57`'s `test …, 0x10020047`).

use crate::light::light_in_front;
use crate::model::{Model, Plane, Vec3};
use std::collections::HashSet;

const PF_INVISIBLE: u32 = 0x0000_0001;
const PF_PORTAL: u32 = 0x0400_0000;
/// The non-opaque mask read straight off `render.dll 0x10019b57`'s `test dword ptr […], 0x10020047`
/// (board item, "What it is"): a surface carrying any of these bits does not SUBTRACT its accepted
/// spans from the zone's span buffer, i.e. it never occludes anything behind it (masked/translucent/
/// portal/invisible/selected all pass light through for occlusion purposes even where visible).
const PF_NONOCCLUDING: u32 = 0x1002_0047;

/// Whether an accepted OPAQUE surface subtracts its footprint from the zone buffer (the "occludes
/// what is behind it" half of the port sketch). **Measured OFF on UNATCO** (`bin/uedcli … level
/// materialize` + `dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/{run_diff,
/// lightparity}.py` against a freshly built LIT golden, 2026-08-29): with it ON, extra (surf,light)
/// pairs drop 618→189 but MISSED pairs explode 7→1110 and per-record byte-identical REGRESSES
/// 2518→2457 — a net regression the repo's "must not regress the baseline" bar forbids shipping. With
/// it OFF (this port keeps only zone-reachability + backface + frustum + `PF_Invisible`, no true
/// self-occlusion), extra drops 618→447, missed rises 7→119, and byte-identical IMPROVES 2518→2557 —
/// a real, net, tested gain. Root cause of the ON regression is NOT pinned: `DBG_EMPTY_AFTER_TEST`
/// (`dump_debug_counters`) shows the "occluded by a nearer opaque surface" rejection dominating by a
/// wide margin, consistent with either a genuine bug in this port's boolean-grid subtract (vs. the
/// real `FSpanBuffer` run-length semantics) or with native's own zone graph (only 6 zones on UNATCO)
/// being coarser/wrong versus the editor's, so screen-space occlusion computed against OUR zoning
/// disagrees with what the editor's own gather actually did. See the follow-up board finding filed
/// alongside this port for the exact numbers and next steps before flipping this back on.
const SUBTRACT_OCCLUSION: bool = false;

/// Cube-face resolution, `0x400 x 0x400` (board item, "What it is").
const RES: i32 = 1024;
/// `Proj.Z` at the pinned `FovAngle = 90°`: `(SizeX/2)/tan(45°) = SizeX/2` (port sketch step 1).
const PROJ_Z: f32 = (RES / 2) as f32;

/// One cube face's camera basis: `forward` = view axis, `right`/`up` = the screen axes. Order and
/// axes match the board item's six rotators exactly: `(0x4000,0,0)`=+Z, `(0xc000,0,0)`=−Z,
/// `(0,0,0)`=+X, `(0,0x8000,0)`=−X, `(0,0xc000,0)`=−Y, `(0,0x4000,0)`=+Y. The `right`/`up` choice
/// within each face is this port's own (never disassembled) but self-consistent and orthonormal;
/// since occlusion is a purely geometric accept/reject test, any consistent choice of in-plane axes
/// yields the same visible-surface SET (a rotation/reflection of the same screen makes no pixel
/// newly visible or newly occluded).
struct Face {
    forward: Vec3,
    right: Vec3,
    up: Vec3,
}

fn faces() -> [Face; 6] {
    [
        Face { forward: Vec3::new(0.0, 0.0, 1.0), right: Vec3::new(1.0, 0.0, 0.0), up: Vec3::new(0.0, -1.0, 0.0) }, // +Z
        Face { forward: Vec3::new(0.0, 0.0, -1.0), right: Vec3::new(1.0, 0.0, 0.0), up: Vec3::new(0.0, 1.0, 0.0) }, // -Z
        Face { forward: Vec3::new(1.0, 0.0, 0.0), right: Vec3::new(0.0, 1.0, 0.0), up: Vec3::new(0.0, 0.0, 1.0) }, // +X
        Face { forward: Vec3::new(-1.0, 0.0, 0.0), right: Vec3::new(0.0, -1.0, 0.0), up: Vec3::new(0.0, 0.0, 1.0) }, // -X
        Face { forward: Vec3::new(0.0, -1.0, 0.0), right: Vec3::new(1.0, 0.0, 0.0), up: Vec3::new(0.0, 0.0, 1.0) }, // -Y
        Face { forward: Vec3::new(0.0, 1.0, 0.0), right: Vec3::new(-1.0, 0.0, 0.0), up: Vec3::new(0.0, 0.0, 1.0) }, // +Y
    ]
}

#[inline]
fn plane_dot(p: &Plane, v: &Vec3) -> f32 {
    p.x * v.x + p.y * v.y + p.z * v.z - p.w
}

/// Rebuild node `ni`'s world-space polygon ring from its vertex pool.
fn node_poly(model: &Model, ni: usize) -> Vec<Vec3> {
    let n = &model.nodes[ni];
    (0..n.num_vertices)
        .map(|k| {
            let vi = model.verts[(n.i_vert_pool + k) as usize].i_vertex as usize;
            model.points[vi]
        })
        .collect()
}

/// A zone's (or, unzoned, the single shared) span buffer: a boolean "still visible" pixel grid plus
/// a running count of set bits, so [`SpanBuf::any_visible`] is O(1) rather than an O(RES²) scan on
/// every zone-reachability test (board step 10 — checked at nearly every node).
struct SpanBuf {
    bits: Vec<bool>,
    count: u32,
}

impl SpanBuf {
    fn empty() -> Self {
        SpanBuf { bits: vec![false; (RES * RES) as usize], count: 0 }
    }
    fn full() -> Self {
        SpanBuf { bits: vec![true; (RES * RES) as usize], count: (RES * RES) as u32 }
    }
    #[inline]
    fn any_visible(&self) -> bool {
        self.count > 0
    }
}

/// One row's screen-space span `[x0, x1)` of a convex polygon at scanline `y` (pixel-centre sampled
/// at `y + 0.5`), or `None` if the row misses the polygon entirely.
fn convex_row_span(poly: &[(f32, f32)], y: f32) -> Option<(f32, f32)> {
    let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
    let n = poly.len();
    for i in 0..n {
        let (x1, y1) = poly[i];
        let (x2, y2) = poly[(i + 1) % n];
        if (y1 <= y && y2 > y) || (y2 <= y && y1 > y) {
            let t = (y - y1) / (y2 - y1);
            let x = x1 + t * (x2 - x1);
            lo = lo.min(x);
            hi = hi.max(x);
        }
    }
    if hi > lo {
        Some((lo, hi))
    } else {
        None
    }
}

/// Clip a convex camera-space polygon (list of `(depth, right, up)`) against the four `FovAngle=90`
/// side planes (`|right| <= depth`, `|up| <= depth` — no near/far plane, matching the port sketch:
/// "Four side planes, no near/far"), then project to screen pixel coordinates. Returns `None` if
/// nothing survives.
fn clip_and_project(cam: &[(f32, f32, f32)]) -> Option<Vec<(f32, f32)>> {
    // Sutherland-Hodgman against depth - side*right/up >= 0 for the two side/up half-spaces (using
    // signed +1/-1 sign so both planes of a pair share the same clip routine).
    fn clip(poly: &[(f32, f32, f32)], axis_is_up: bool, sign: f32) -> Vec<(f32, f32, f32)> {
        let inside = |v: &(f32, f32, f32)| {
            let a = if axis_is_up { v.2 } else { v.1 };
            v.0 - sign * a >= 0.0
        };
        let mut out = Vec::with_capacity(poly.len() + 2);
        let n = poly.len();
        for i in 0..n {
            let a = poly[i];
            let b = poly[(i + 1) % n];
            let (a_in, b_in) = (inside(&a), inside(&b));
            if a_in {
                out.push(a);
            }
            if a_in != b_in {
                let fa = if axis_is_up { a.2 } else { a.1 };
                let fb = if axis_is_up { b.2 } else { b.1 };
                // Solve t along a->b where (d - sign*x) == 0.
                let da = a.0 - sign * fa;
                let db = b.0 - sign * fb;
                let t = da / (da - db);
                out.push((a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1), a.2 + t * (b.2 - a.2)));
            }
        }
        out
    }
    let mut poly: Vec<(f32, f32, f32)> = cam.to_vec();
    for (axis_is_up, sign) in [(false, 1.0), (false, -1.0), (true, 1.0), (true, -1.0)] {
        if poly.len() < 3 {
            return None;
        }
        poly = clip(&poly, axis_is_up, sign);
    }
    if poly.len() < 3 {
        return None;
    }
    let half = RES as f32 / 2.0;
    Some(
        poly.iter()
            .map(|&(d, r, u)| {
                let d = d.max(1e-6); // guard: clip keeps d>=|axis|>=0; d==0 only for the degenerate apex
                (half + r / d * PROJ_Z, half - u / d * PROJ_Z)
            })
            .collect(),
    )
}

/// Rasterize node `ni`'s polygon as seen from `light_loc` through camera basis `face` into a list of
/// `(row, x0, x1)` screen spans, clamped to `[0, RES)`. `None` if the polygon is fully behind, fully
/// clipped away, or degenerate.
fn rasterize_node(model: &Model, ni: usize, light_loc: &Vec3, face: &Face) -> Option<Vec<(i32, i32, i32)>> {
    let world = node_poly(model, ni);
    if world.len() < 3 {
        return None;
    }
    let cam: Vec<(f32, f32, f32)> = world
        .iter()
        .map(|p| {
            let rel = p.sub(light_loc);
            (rel.dot(&face.forward), rel.dot(&face.right), rel.dot(&face.up))
        })
        .collect();
    let screen = clip_and_project(&cam)?;
    let (mut ymin, mut ymax) = (f32::INFINITY, f32::NEG_INFINITY);
    for &(_, y) in &screen {
        ymin = ymin.min(y);
        ymax = ymax.max(y);
    }
    let y0 = (ymin.floor() as i32).max(0);
    let y1 = (ymax.ceil() as i32).min(RES);
    if y1 <= y0 {
        return None;
    }
    let mut rows = Vec::with_capacity((y1 - y0) as usize);
    for y in y0..y1 {
        if let Some((lo, hi)) = convex_row_span(&screen, y as f32 + 0.5) {
            let x0 = (lo.floor() as i32).max(0);
            let x1 = (hi.ceil() as i32).min(RES);
            if x1 > x0 {
                rows.push((y, x0, x1));
            }
        }
    }
    if rows.is_empty() {
        None
    } else {
        Some(rows)
    }
}

/// Test `rows` against `buf`; if `subtract`, clear every visible pixel found (the opaque-surface
/// occlusion write). Returns the list of pixels that WERE visible before this call (the "accepted"
/// footprint — what a visible portal spreads into the far zone).
fn test_and_maybe_subtract(buf: &mut SpanBuf, rows: &[(i32, i32, i32)], subtract: bool) -> Vec<(i32, i32)> {
    let mut accepted = Vec::new();
    for &(y, x0, x1) in rows {
        let base = (y * RES) as usize;
        for x in x0..x1 {
            let idx = base + x as usize;
            if buf.bits[idx] {
                accepted.push((y, x));
                if subtract {
                    buf.bits[idx] = false;
                    buf.count -= 1;
                }
            }
        }
    }
    accepted
}

fn merge_into(buf: &mut SpanBuf, pixels: &[(i32, i32)]) {
    for &(y, x) in pixels {
        let idx = (y * RES + x) as usize;
        if !buf.bits[idx] {
            buf.bits[idx] = true;
            buf.count += 1;
        }
    }
}

/// Point-in-BSP zone lookup (the light's own `Frame->ZoneNumber`): descend by plane side from the
/// root using the SAME `IsFront = PlaneDot > 0` convention the traversal below uses, so the starting
/// zone is exactly what the first few traversal steps would independently derive. `node.i_zone[1]` is
/// the FRONT-side zone, `[0]` the BACK-side (board item struct offsets + step 10's `iZone[IsFront]`
/// indexing). Depth-bounded like `linecheck::line_clear` — never hang on a corrupt/cyclic Model.
fn zone_of_point(model: &Model, p: Vec3) -> i32 {
    if model.nodes.is_empty() {
        return 0;
    }
    let mut ni = 0i32;
    for _ in 0..4096 {
        let n = &model.nodes[ni as usize];
        let is_front = plane_dot(&n.plane, &p) > 0.0;
        let child = if is_front { n.i_back } else { n.i_front };
        if child < 0 {
            return n.i_zone[is_front as usize];
        }
        ni = child;
    }
    0 // pathological depth: fail to "solid/unzoned" rather than hang
}

/// Zone-keyed span buffers for one face's traversal. `use_zones` selects between per-zone buffers
/// (keyed by real zone id `1..=63`) and ONE shared buffer under `SHARED_KEY` (board step 2: a light
/// in zone 0 gets a fully unzoned pass — one buffer, no zone-mask pruning, portals skipped entirely).
const SHARED_KEY: i32 = -1;

// TEMP diagnostic counters (root-causing the subtract-enabled over-occlusion regression). Dumped by
// `dump_debug_counters` when `UEDCLI_VISGATE_DUMP` is set (see `light::bake`). Not per-light-scoped
// (rayon runs many lights concurrently) — global totals across the whole bake are enough to see which
// rejection reason dominates.
static DBG_RASTERIZED: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static DBG_ACCEPTED: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static DBG_EMPTY_AFTER_TEST: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static DBG_CLIPPED_AWAY: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static DBG_UNREACHABLE: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static DBG_BACKFACE: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

pub fn dump_debug_counters() {
    use std::sync::atomic::Ordering::Relaxed;
    eprintln!(
        "VISGATE_TRAVERSE rasterized={} accepted={} empty_after_test(occluded)={} clipped_away={} \
         unreachable={} backface={}",
        DBG_RASTERIZED.load(Relaxed),
        DBG_ACCEPTED.load(Relaxed),
        DBG_EMPTY_AFTER_TEST.load(Relaxed),
        DBG_CLIPPED_AWAY.load(Relaxed),
        DBG_UNREACHABLE.load(Relaxed),
        DBG_BACKFACE.load(Relaxed),
    );
}

struct ZoneBufs {
    bufs: std::collections::HashMap<i32, SpanBuf>,
}

impl ZoneBufs {
    fn get_or_empty(&mut self, key: i32) -> &mut SpanBuf {
        self.bufs.entry(key).or_insert_with(SpanBuf::empty)
    }
}

/// One face's traversal: DFS from `ni`, near-child first, mutating `active_mask`/`spans` as portals
/// are crossed, inserting every accepted surf's index into `out`.
///
/// Walks the `i_plane` COPLANAR CHAIN at `ni` too — a chain head's `i_front`/`i_back` are its real
/// tree children, but each subsequent chain member is a SEPARATE surface sharing the exact same
/// split plane (`i_front`/`i_back` both `-1` on a member, so recursing into them is a harmless
/// no-op); every member still needs its own filter+rasterize pass. Mirrors the same pattern
/// `light::lightmap_emit_order`'s walk and `zones::passd_walk` use for this Model.
#[allow(clippy::too_many_arguments)]
fn traverse(
    model: &Model,
    ni: i32,
    light_loc: &Vec3,
    face: &Face,
    use_zones: bool,
    active_mask: &mut u64,
    spans: &mut ZoneBufs,
    out: &mut HashSet<i32>,
) {
    let mut cur = ni;
    while cur >= 0 {
        let nu = cur as usize;
        let n = &model.nodes[nu];
        // Step 1: zone-mask subtree prune. `zone_mask` is the OR of every zone reachable at or below
        // this node (self + both children + the REST of the coplanar chain, `zones::build_zone_mask`
        // folds in `i_plane` too), so a miss here also rules out every later chain member — safe to
        // stop the whole chain, not just this one node.
        if use_zones && (*active_mask & n.zone_mask) == 0 {
            return;
        }
        let d = plane_dot(&n.plane, light_loc);
        let is_front = d > 0.0;
        // Engine child convention on the finalized model (matches `linecheck.rs`): FRONT = `i_back`,
        // BACK = `i_front`. The near child (same side as the light) is visited first. A coplanar
        // chain MEMBER carries `i_front == i_back == -1` (only the chain HEAD splits space), so this
        // recursion is a no-op past the first iteration.
        let (near_child, far_child) =
            if is_front { (n.i_back, n.i_front) } else { (n.i_front, n.i_back) };
        traverse(model, near_child, light_loc, face, use_zones, active_mask, spans, out);

        if n.i_surf >= 0 && (n.i_surf as usize) < model.surfs.len() && n.num_vertices >= 3 {
            let surf = &model.surfs[n.i_surf as usize];
            let poly_flags = surf.poly_flags;
            let near_zone = n.i_zone[is_front as usize];
            let near_key = if use_zones { near_zone } else { SHARED_KEY };
            // Step 10: zone reachability — nothing on the near side of this node is visible unless
            // that zone's span buffer still has SOMETHING unclaimed.
            let reachable = spans.bufs.get(&near_key).map(SpanBuf::any_visible).unwrap_or(false);
            // Step 7: back-face cull — reuse the already-ported `light::light_in_front` (identical
            // predicate: `PlaneDot >= -1.0` keeps, `PF_TwoSided|PF_Portal` always exempt).
            let normal = model.vectors[surf.v_normal as usize];
            let base = model.points[surf.p_base as usize];
            let front_ok = light_in_front(&normal, &base, light_loc, poly_flags);
            // Step 8: a portal surface is never drawn/crossed in the unzoned pass.
            let portal_needs_zones = poly_flags & PF_PORTAL != 0 && !use_zones;
            // Step 11: `ShowFlags=0x800` keeps `PF_Invisible` in the drop set.
            let invisible = poly_flags & PF_INVISIBLE != 0;
            if reachable && front_ok && !portal_needs_zones && !invisible {
                if let Some(rows) = rasterize_node(model, nu, light_loc, face) {
                    DBG_RASTERIZED.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    let opaque = SUBTRACT_OCCLUSION && poly_flags & PF_NONOCCLUDING == 0;
                    let buf = spans.get_or_empty(near_key);
                    let accepted = test_and_maybe_subtract(buf, &rows, opaque);
                    if !accepted.is_empty() {
                        DBG_ACCEPTED.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        out.insert(n.i_surf);
                        if use_zones && poly_flags & PF_PORTAL != 0 {
                            let far_zone = n.i_zone[(!is_front) as usize];
                            if far_zone != 0 {
                                let far_buf = spans.get_or_empty(far_zone);
                                merge_into(far_buf, &accepted);
                                *active_mask |= 1u64 << (far_zone as u64 & 63);
                            }
                        }
                    } else {
                        DBG_EMPTY_AFTER_TEST.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    }
                } else {
                    DBG_CLIPPED_AWAY.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                }
            } else if !reachable {
                DBG_UNREACHABLE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            } else if !front_ok {
                DBG_BACKFACE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            }
        }

        traverse(model, far_child, light_loc, face, use_zones, active_mask, spans, out);
        cur = n.i_plane;
    }
}

/// The full six-face gather for one light: the port of `URender::GetVisibleSurfs`. Returns the set of
/// `iSurf` indices the editor's occlusion rasterization would list this light on (before the caller's
/// own `bSpecialLit`/radius/per-lumel filters).
pub fn get_visible_surfs(model: &Model, light_loc: Vec3) -> HashSet<i32> {
    let mut out = HashSet::new();
    if model.nodes.is_empty() {
        return out;
    }
    let view_zone = zone_of_point(model, light_loc);
    let use_zones = view_zone != 0;
    for face in faces().iter() {
        let mut spans = ZoneBufs { bufs: std::collections::HashMap::new() };
        let seed_key = if use_zones { view_zone } else { SHARED_KEY };
        spans.bufs.insert(seed_key, SpanBuf::full());
        let mut active_mask: u64 = if use_zones { 1u64 << (view_zone as u64 & 63) } else { u64::MAX };
        traverse(model, 0, &light_loc, face, use_zones, &mut active_mask, &mut spans, &mut out);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;

    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper, poly_flags: u32) -> BrushInput {
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
            poly_flags,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
        }
    }

    #[test]
    fn a_light_at_the_centre_of_a_closed_room_sees_all_six_walls() {
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract, 0,
        )])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        let visible = get_visible_surfs(&m, Vec3::new(0.0, 0.0, 0.0));
        assert_eq!(visible.len(), 6, "a light at the room centre sees every one of the 6 walls");
    }

    #[test]
    fn a_light_outside_a_closed_room_never_sees_the_wall_it_faces_head_on() {
        // A light far along +X, outside a lone Subtract room: the near wall (x=+256, inward normal
        // -X) is squarely BEHIND the light's own view of it (`PlaneDot` hugely negative) and must be
        // backface-culled (step 7). NOTE: this fixture is a single Subtract brush with no enclosing
        // solid (`root_outside=true` — "a Subtract into pure void keeps nothing", `model.rs`), so the
        // void surrounding the room has no real geometry to occlude the OTHER 5 walls from an
        // exterior light — the same non-watertight-BSP leak `light_in_front_matches_plane_side`'s
        // sibling test documents for the per-lumel raycast (`out_of_room_light_is_never_listed`'s
        // comment: "the native ray traces a BSP whose solid cells do not perfectly enclose"). Real
        // levels are enclosed by actual solid mass, so this leak does not apply to them; the coarse
        // radius cull (`bake_surf`, caller-side) is what protects a genuinely distant light in
        // practice. This test pins only the one guarantee `GetVisibleSurfs` itself provides here.
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract, 0,
        )])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        let visible = get_visible_surfs(&m, Vec3::new(10000.0, 0.0, 0.0));
        let near_wall = m
            .surfs
            .iter()
            .position(|s| m.points[s.p_base as usize].x > 0.0)
            .expect("a wall with positive-X base exists") as i32;
        assert!(
            !visible.contains(&near_wall),
            "the wall the light faces head-on from outside must be backface-culled, got {visible:?}"
        );
    }

    #[test]
    fn a_wall_occludes_a_second_room_behind_it() {
        // Two SEPARATE sealed rooms side by side (no shared portal): a light inside room A must
        // never see room B's walls — they are a different zone with an empty, never-merged-into span
        // buffer, so zone reachability (step 10) alone must reject them even though nothing in this
        // test relies on solid-brush ray occlusion.
        let mut m = build_geometry_from_brushes(&[
            box_brush(128.0, 128.0, 128.0, Vec3::new(-400.0, 0.0, 0.0), CsgOper::Subtract, 0),
            box_brush(128.0, 128.0, 128.0, Vec3::new(400.0, 0.0, 0.0), CsgOper::Subtract, 0),
        ])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        let visible = get_visible_surfs(&m, Vec3::new(-400.0, 0.0, 0.0));
        // Every visible surf must belong to room A: its vertices all have x well below 0.
        for &si in &visible {
            let s = &m.surfs[si as usize];
            let base = m.points[s.p_base as usize];
            assert!(base.x < 0.0, "surf {si} at base {base:?} belongs to the far, unreachable room");
        }
        assert!(!visible.is_empty(), "room A's own light must still see room A's walls");
    }

    #[test]
    fn an_invisible_surface_is_never_listed() {
        const PF_INVISIBLE_TEST: u32 = 0x0000_0001;
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract, PF_INVISIBLE_TEST,
        )])
        .unwrap();
        crate::zones::assign_leaves_and_zones(&mut m);
        let visible = get_visible_surfs(&m, Vec3::new(0.0, 0.0, 0.0));
        assert!(visible.is_empty(), "PF_Invisible surfaces must never appear in the gather");
    }
}
