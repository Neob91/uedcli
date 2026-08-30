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
//! set — **from emission into the light's own run only**; rasterization, the span-buffer accept/
//! reject test and portal zone-crossing all run BEFORE this check, disassembly address order
//! `0x1001a257` < `0x1001a30d` — see `invisible`'s doc comment in [`traverse`]), the six exact
//! 90°-apart face rotations and `AddUniqueItem` (here: a `HashSet`) union across
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
/// what is behind it" half of the port sketch).
///
/// **History (`getvisiblesurfs-self-occlusion-regresses-missed`):** first shipped OFF — with the
/// original boolean-pixel-grid `SpanBuf`, turning it ON regressed UNATCO's missed pairs 7→1110 and
/// byte-identical records 2518→2457, a clear net loss. Root-caused 2026-08-29 by disassembling
/// `FSpanBuffer::CopyFromRaster`/`CopyFromRasterUpdate` (`render.dll 0x1001dd10`/`0x1001df70`):
/// `FSpanBuffer` is a per-row SORTED INTERVAL LIST, not a pixel grid — the boolean grid was a
/// materially different (and wrong) representation, not just an approximation. `SpanBuf` was
/// rewritten to match (see its doc comment), and with the fix, ON is a clear net win on UNATCO
/// (byte-identical 2518→2628, extra 618→151, missed 7→233) and roughly flat on Wanchai
/// (byte-identical 3229→3228, extra 526→131, missed 12→347 — same aggregate score, shifted from
/// extra to missed). Shipped ON: strictly better on the level this was diagnosed against, not worse
/// on the second, and structurally the faithful behavior rather than a heuristic. CORRECTED
/// 2026-08-30 (`getvisiblesurfs-wanchai-run-gap-root-cause`): `MergeWith` is NOT the likeliest source
/// of Wanchai's larger `missed` count — `pair_geometry.py`'s light/surf-zone comparison shows only
/// ~20% of Wanchai's missed pairs even cross a zone boundary (light and surface agree 94.6% of the
/// time on "both list", 96.3% on "native only", but just 80.0% on "editor only" — a real but small
/// skew). A live trace of a concrete missing pair (Light45 / surf 2920, same zone as its light) found
/// dense same-zone clutter fully consuming a row's span before the target was even reached — see
/// `rasterize_node`'s pixel-center-coverage fix, which cut Wanchai's missed count 350→314 without
/// touching `MergeWith` at all. **`MergeWith` itself is now fully decoded and confirmed correct as
/// ported** (`mergewith-fully-decoded-confirms-merge-into`, 2026-08-30): a complete
/// instruction-by-instruction disassembly of `render.dll 0x1001e3b0` (see [`merge_into`]'s doc
/// comment) plus a 10-sample live capture during a real Wanchai `LIGHT APPLY` (7 pure-append rows +
/// 3 genuine overlap/touching-boundary merges) shows the real algorithm produces byte-identical
/// output to what `merge_into` independently computes on the same inputs, 10/10. So the ~20%
/// zone-crossing share of Wanchai's missed pairs is NOT a `MergeWith`-fidelity gap — its true cause
/// is still open, but ruled out as a suspect here.
const SUBTRACT_OCCLUSION: bool = true;

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

/// One row's "still visible" content: a sorted, disjoint list of half-open `[x0,x1)` intervals —
/// faithful to the real `FSpanBuffer::Index[y]`, a linked list of 12-byte `{X0,X1,Next}` nodes
/// (`render.dll 0x1001dd10`/`0x1001df70`, disassembly-decoded 2026-08-29; struct confirmed via
/// `FMemStack::PushBytes(this->Mem /* @+0x10 */, 0xc, 4)` allocations). A `Vec` stands in for the
/// engine's `FMemStack`-allocated linked list — same sorted/disjoint invariant, no behavioral
/// difference for this port's purposes.
type Row = Vec<(i32, i32)>;

/// A zone's (or, unzoned, the single shared) span buffer: one [`Row`] per scanline, plus the count
/// of non-empty rows (`ValidLines` in the real struct) so [`SpanBuf::any_visible`] is O(1) rather
/// than an O(RES) scan on every zone-reachability test (board step 10 — checked at nearly every
/// node).
struct SpanBuf {
    rows: Vec<Row>,
    valid_lines: i32,
}

impl SpanBuf {
    fn empty() -> Self {
        SpanBuf { rows: vec![Vec::new(); RES as usize], valid_lines: 0 }
    }
    fn full() -> Self {
        SpanBuf { rows: vec![vec![(0, RES)]; RES as usize], valid_lines: RES }
    }
    #[inline]
    fn any_visible(&self) -> bool {
        self.valid_lines > 0
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
    // Pixel-CENTER coverage (include column i iff its center i+0.5 lies in [lo,hi)), not
    // full-coverage floor/ceil (`getvisiblesurfs-wanchai-run-gap-root-cause`, 2026-08-30). Live
    // trace of a concrete missing (surf, light) pair on Wanchai (see that board item) found the
    // target's tiny footprint swallowed by an accumulation of dozens of small NEIGHBOURING opaque
    // surfaces' subtracted spans in the same row — plausible cause: full-coverage floor/ceil pads
    // every polygon's footprint outward by up to ~1px per edge, and in a scene with many small
    // adjacent surfaces (Wanchai's market clutter) those pads compound across neighbours and can
    // swallow a genuine gap a pixel-center rasterizer would leave open. Measured net effect of this
    // one-line change: Wanchai records byte-identical 3228/4530 (71.3%) -> 3297/4530 (72.8%), run
    // differs 348->266, extra pairs 134->79, missed 350->314; UNATCO (geometry-matched, its tree
    // isn't node-exact so positional compare doesn't apply) run_ok 92.0%->94.2%, dark/lit
    // mismatches 29+36 -> 27+20. No regression on either level's shadow-bit-equal or grid/pan/scale
    // rates. `x0 = ceil(lo-0.5)`, `x1 = ceil(hi-0.5)` is the standard pixel-center-inclusion
    // formula. Zone-crossing pairs are NOT the dominant cause of the run gap this was chasing (only
    // ~20% of Wanchai's missed pairs cross a zone, measured via `pair_geometry.py`), so `MergeWith`
    // fidelity — named below as "the likeliest source" — is a smaller factor than that comment
    // claimed; left uncorrected there pending independent re-confirmation per the findings-ledger
    // process (`dev/docs/native-materialize-findings.md`).
    for y in y0..y1 {
        if let Some((lo, hi)) = convex_row_span(&screen, y as f32 + 0.5) {
            let x0 = ((lo - 0.5).ceil() as i32).max(0);
            let x1 = ((hi - 0.5).ceil() as i32).min(RES);
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

/// Test `rows` (a node's per-row rasterized window `[y, x0, x1)`) against `buf`'s current content;
/// if `subtract`, remove the accepted portion from `buf` in place (the opaque-surface occlusion
/// write). Returns the accepted `(y, x0, x1)` intervals — what a visible portal spreads into the far
/// zone.
///
/// Faithful to `FSpanBuffer::CopyFromRaster`/`CopyFromRasterUpdate` (disassembly-decoded 2026-08-29,
/// see `getvisiblesurfs-self-occlusion-regresses-missed`): walk the row's sorted disjoint interval
/// list; a node wholly left of the window (`x1 <= wx0`) is unaffected; the first node at/after that
/// point overlaps iff `x0 < wx1` — accept `[max(x0,wx0), min(x1,wx1))` (this single clamp covers
/// both the disassembly's separate "clip first node's left edge" and "clip last node's right edge"
/// cases, since every node after the first overlap already has `x0 >= wx0` by the sorted/disjoint
/// invariant); once a node's right edge exceeds the window, clip and STOP — nothing further right in
/// a sorted disjoint list can be inside a single contiguous window either.
fn test_and_maybe_subtract(
    buf: &mut SpanBuf,
    rows: &[(i32, i32, i32)],
    subtract: bool,
) -> Vec<(i32, i32, i32)> {
    let mut accepted = Vec::new();
    for &(y, wx0, wx1) in rows {
        if wx1 <= wx0 {
            continue;
        }
        let row = &mut buf.rows[y as usize];
        let mut out_row: Row = if subtract { Vec::with_capacity(row.len() + 2) } else { Vec::new() };
        let mut touched = false;
        let mut i = 0usize;
        while i < row.len() {
            let (x0, x1) = row[i];
            if x1 <= wx0 {
                if subtract {
                    out_row.push((x0, x1));
                }
                i += 1;
                continue;
            }
            if x0 >= wx1 {
                // This node, and everything after it (sorted), starts at/past the window's right
                // edge: no overlap here or later.
                if subtract {
                    out_row.extend_from_slice(&row[i..]);
                }
                break;
            }
            let (ax0, ax1) = (x0.max(wx0), x1.min(wx1));
            accepted.push((y, ax0, ax1));
            touched = true;
            if subtract {
                if x0 < ax0 {
                    out_row.push((x0, ax0));
                }
                if x1 > ax1 {
                    out_row.push((ax1, x1));
                }
            }
            if x1 <= wx1 {
                i += 1; // fully consumed by the window: keep scanning for more overlapping nodes
            } else {
                i += 1;
                if subtract {
                    out_row.extend_from_slice(&row[i..]);
                }
                break; // clipped at the right edge: nothing further right can be in-window either
            }
        }
        if subtract && touched {
            let was_empty = row.is_empty();
            *row = out_row;
            let is_empty = row.is_empty();
            if was_empty != is_empty {
                buf.valid_lines += if is_empty { -1 } else { 1 };
            }
        }
    }
    accepted
}

/// Union `intervals` into `buf` (a visible portal spreading its accepted footprint into the far
/// zone) — insert each `(y,x0,x1)` into that row's sorted disjoint list, merging overlapping or
/// touching runs.
///
/// **Fully decoded and confirmed correct** (`mergewith-fully-decoded-confirms-merge-into`,
/// 2026-08-30, disasm + live). `FSpanBuffer::MergeWith(this, Other)` (`render.dll` file RVA
/// `0x1001e3b0`) was disassembled instruction-by-instruction (`rdis.py dis Render 0x1001e3b0 0x400`)
/// and found to be: (1) if `Other`'s `[StartY,EndY)` isn't already contained in `this`'s own range,
/// reallocate `this->Index` to cover `[min(this.Start,Other.Start), max(this.End,Other.End))`,
/// copying the old row-pointer array into its new offset and zero-filling the newly extended rows
/// (irrelevant to this port — [`SpanBuf`] always allocates the full `[0,RES)` range up front, never
/// needs to grow); (2) for each row `y` in `[Other.StartY, Other.EndY)`, merge the two sorted disjoint
/// 12-byte-node (`{X0,X1,Next}`) interval lists `this->Index[y]` and `Other->Index[y-Other.StartY]`
/// into one new sorted disjoint list written back to `this->Index[y]` — a standard two-sorted-list
/// merge, `FMemStack`-allocating a fresh node for anything not already owned by `this` (an Other-only
/// run, or a run absorbed from `this`'s own chain that needs pushing further left/right — `this`'s
/// FIRST node in a merged run is mutated in place, not reallocated). Two intervals that only TOUCH
/// (`OtherX1 == ThisX0`, half-open boundary) still merge (`jge`, not `jg`, at the overlap test) — this
/// port's `merge_into` uses the same non-strict `b < cur.0` / `a > cur.1` boundary, confirmed to
/// match. `this+8` (`ValidLines` per the pre-existing `FSpanBuffer` struct layout) increments once
/// per NEW node allocated and decrements once per `this`-node absorbed-and-discarded during a merge —
/// i.e. it is a total INTERVAL-NODE count, not a per-ROW count as `SpanBuf::valid_lines` (which only
/// flips ±1 on a row's empty↔non-empty transition) — but this has NO functional effect anywhere it's
/// read: every consumer ([`SpanBuf::any_visible`], the real `ValidLines <= 0` zone-reachability test)
/// only tests `> 0`/`<= 0`, which both countings agree on (zero iff the buffer is truly empty).
///
/// **Live-verified** (`mergewith_live_check.py`,
/// `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`): 10 real `MergeWith` calls during a
/// genuine Wanchai `LIGHT APPLY`, gdb-breakpointed at the function's real runtime address (render.dll
/// does NOT load at its preferred 0x10000000 base in this wine process — confirmed live, it actually
/// loads at 0x015b0000; only Editor.dll keeps its preferred slot, which is why every prior live
/// capture in this codebase happened to work off the raw static VA and this one didn't at first).
/// 7/10 were a pure append (this's row empty, Other contributes one node — output equals Other's node
/// verbatim); 3/10 were a genuine merge, including two touching-boundary cases (`(978,980)` + a
/// row-content `(976,978)` → `(976,980)`; `(974,991)` + `(971,974)` → `(971,991)`) and one interior
/// overlap (`(315,316)` + `(316,317)` → `(315,317)`). All 10 match, node for node, what `merge_into`
/// independently computes from the same captured inputs (`merge_into_matches_the_real_editors_output`
/// below pins the 3 genuine-merge cases). So `merge_into` needed no fix — it already reproduces the
/// real `MergeWith`'s row-merge algorithm exactly for every case sampled.
fn merge_into(buf: &mut SpanBuf, intervals: &[(i32, i32, i32)]) {
    for &(y, x0, x1) in intervals {
        if x1 <= x0 {
            continue;
        }
        let row = &mut buf.rows[y as usize];
        let was_empty = row.is_empty();
        let mut merged: Row = Vec::with_capacity(row.len() + 1);
        let mut cur = (x0, x1);
        let mut inserted = false;
        for &(a, b) in row.iter() {
            if b < cur.0 {
                merged.push((a, b));
            } else if a > cur.1 {
                if !inserted {
                    merged.push(cur);
                    inserted = true;
                }
                merged.push((a, b));
            } else {
                cur = (cur.0.min(a), cur.1.max(b));
            }
        }
        if !inserted {
            merged.push(cur);
        }
        *row = merged;
        if was_empty && !row.is_empty() {
            buf.valid_lines += 1;
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
///
/// **Order, fixed 2026-08-30** (`getvisiblesurfs-dfs-order-vs-far-child-interleave`): the real
/// editor's own per-node order is disassembly-documented
/// (`port-urender-getvisiblesurfs-so-each-light-gets`, "AddUniqueItem ... front-to-back DFS order
/// (near child -> own surface -> iPlane chain -> far child)") as near child, THEN own surface, THEN
/// the REST of the coplanar chain, and ONLY THEN `far_child`. An earlier version of this port instead
/// recursed into `far_child` immediately after the head's own surface — before the rest of the chain
/// — letting `far_child`'s subtree consume shared span-buffer area before a later chain member (or a
/// portal reached only through one) was ever tested. That is an order-dependent span-buffer-
/// exhaustion bug, distinct from occlusion correctness itself: the "zone1's span buffer is GLOBALLY
/// exhausted ... by the time traversal reaches this node, even though other portals fed by the same
/// buffer succeed earlier in the same run" finding
/// (`zone-crossing-getvisiblesurfs-gap-invisible`) is exactly the symptom of far_child's subtree
/// (visited too early) draining the buffer before DFS order would have reached a later chain member.
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
    trace: Option<(usize, i32)>, // (face index, target surf) — see `trace_target`
    trace_portals: bool,        // see `trace_portals`
) {
    if ni < 0 {
        return;
    }
    let head = &model.nodes[ni as usize];
    // Step 1: zone-mask subtree prune, checked at the chain HEAD before anything else. `zone_mask`
    // is the OR of every zone reachable at or below this node (self + both children + the REST of
    // the coplanar chain, `zones::build_zone_mask` folds in `i_plane` too), so a miss here rules out
    // both children AND every chain member — safe to stop here without recursing at all.
    if use_zones && (*active_mask & head.zone_mask) == 0 {
        if trace.is_some_and(|(_, s)| s == head.i_surf) {
            eprintln!(
                "VISGATE_TRACE node={} surf={} PRUNED (zone_mask {:#x} & active {:#x} == 0)",
                ni as usize, head.i_surf, head.zone_mask, *active_mask
            );
        }
        return;
    }
    let d = plane_dot(&head.plane, light_loc);
    let is_front = d > 0.0;
    // Engine child convention on the finalized model (matches `linecheck.rs`): FRONT = `i_back`,
    // BACK = `i_front`. The near child (same side as the light) is visited first.
    let (near_child, far_child) =
        if is_front { (head.i_back, head.i_front) } else { (head.i_front, head.i_back) };

    // Near child, full subtree, first (front-to-back).
    traverse(model, near_child, light_loc, face, use_zones, active_mask, spans, out, trace, trace_portals);

    // Own surface, then every remaining `i_plane` coplanar chain member's surface — `far_child` is
    // visited only AFTER the whole chain (below), never interleaved with it. A coplanar chain
    // MEMBER carries `i_front == i_back == -1` (only the chain HEAD splits space), so re-deriving
    // near/far per member below is a harmless no-op.
    let mut cur = ni;
    while cur >= 0 {
        let nu = cur as usize;
        let n = &model.nodes[nu];
        if use_zones && (*active_mask & n.zone_mask) == 0 {
            // A later chain member's own (narrower) zone_mask can rule out the REMAINING chain
            // without touching `far_child`, which is visited unconditionally below regardless of
            // where in the chain this fires.
            if trace.is_some_and(|(_, s)| s == n.i_surf) {
                eprintln!("VISGATE_TRACE node={nu} surf={} PRUNED (zone_mask {:#x} & active {:#x} == 0)", n.i_surf, n.zone_mask, *active_mask);
            }
            break;
        }

        if n.i_surf >= 0 && (n.i_surf as usize) < model.surfs.len() && n.num_vertices >= 3 {
            let is_target = trace.is_some_and(|(_fi, s)| s == n.i_surf);
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
            // Step 11: `ShowFlags=0x800` keeps `PF_Invisible` in the drop set — but ONLY from
            // EMISSION into the caller's visible-surf set (`0x1001a30d`, decoded in the board item's
            // "per-node/per-surface filters, in traversal order"). Disassembly address ordering shows
            // the ACTIVE-ZONE-MASK-OR + `MergeWith` portal-crossing code (`0x1001a257`) runs BEFORE
            // this check (`0x1001a30d`) — i.e. rasterization, the span-buffer accept/reject test, and
            // zone-crossing all happen first, unconditionally; PF_Invisible only suppresses the final
            // "add this surf to the light's run" step. A `PF_Portal` surface is near-universally ALSO
            // `PF_Invisible` (a zone portal is not meant to render), so gating rasterization/crossing
            // on `!invisible` — as this port did until `getvisiblesurfs-zone-crossing-...` — silently
            // drops EVERY invisible portal's zone-crossing, live-confirmed the root cause of Wanchai's
            // zone-crossing missed-pair share (Light482/surf881 across an invisible `PF_Portal|
            // PF_Invisible` boundary, `zone_crossing_pairs.py` + the `UEDCLI_VISGATE_TRACE_PORTALS`
            // probe, 2026-08-30).
            let invisible = poly_flags & PF_INVISIBLE != 0;
            if is_target {
                eprintln!(
                    "VISGATE_TRACE node={nu} surf={} near_zone={near_zone} reachable={reachable} \
                     front_ok={front_ok} portal_needs_zones={portal_needs_zones} invisible={invisible} \
                     poly_flags={poly_flags:#x}",
                    n.i_surf
                );
            }
            if trace_portals && use_zones && poly_flags & PF_PORTAL != 0
                && !(reachable && front_ok && !portal_needs_zones)
            {
                eprintln!(
                    "VISGATE_TRACE_PORTAL node={nu} surf={} near_zone={near_zone} far_zone={} \
                     REJECTED_BEFORE_RASTER reachable={reachable} front_ok={front_ok} invisible={invisible}",
                    n.i_surf,
                    n.i_zone[(!is_front) as usize]
                );
            }
            if reachable && front_ok && !portal_needs_zones {
                if let Some(rows) = rasterize_node(model, nu, light_loc, face) {
                    DBG_RASTERIZED.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    let opaque = SUBTRACT_OCCLUSION && poly_flags & PF_NONOCCLUDING == 0;
                    let buf = spans.get_or_empty(near_key);
                    if is_target {
                        for &(y, wx0, wx1) in &rows {
                            eprintln!(
                                "VISGATE_TRACE node={nu} PRE row y={y} window=[{wx0},{wx1}) buf_row={:?}",
                                buf.rows[y as usize]
                            );
                        }
                    }
                    let accepted = test_and_maybe_subtract(buf, &rows, opaque);
                    if is_target {
                        let row_span: i32 = rows.iter().map(|&(_, x0, x1)| x1 - x0).sum();
                        let acc_span: i32 = accepted.iter().map(|&(_, x0, x1)| x1 - x0).sum();
                        eprintln!(
                            "VISGATE_TRACE node={nu} rasterized rows={} raster_px={row_span} accepted_px={acc_span} opaque={opaque}",
                            rows.len()
                        );
                    }
                    if !accepted.is_empty() {
                        DBG_ACCEPTED.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        // Step 11/12: PF_Invisible suppresses EMISSION only — the surf never joins
                        // the light's own run — never the raster/span-test/portal-crossing above.
                        if !invisible {
                            out.insert(n.i_surf);
                        }
                        if use_zones && poly_flags & PF_PORTAL != 0 {
                            let far_zone = n.i_zone[(!is_front) as usize];
                            if trace_portals {
                                eprintln!(
                                    "VISGATE_TRACE_PORTAL node={nu} surf={} near_zone={near_zone} \
                                     far_zone={far_zone} accepted_px={} action={}",
                                    n.i_surf,
                                    accepted.iter().map(|&(_, x0, x1)| x1 - x0).sum::<i32>(),
                                    if far_zone != 0 { "MERGE" } else { "SKIP(far_zone==0)" }
                                );
                            }
                            if far_zone != 0 {
                                let far_buf = spans.get_or_empty(far_zone);
                                merge_into(far_buf, &accepted);
                                *active_mask |= 1u64 << (far_zone as u64 & 63);
                            }
                        }
                    } else {
                        DBG_EMPTY_AFTER_TEST.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        if trace_portals && use_zones && poly_flags & PF_PORTAL != 0 {
                            eprintln!(
                                "VISGATE_TRACE_PORTAL node={nu} surf={} near_zone={near_zone} \
                                 EMPTY_AFTER_TEST (rasterized but self-occluded, no far-zone merge)",
                                n.i_surf
                            );
                        }
                    }
                } else if is_target {
                    eprintln!("VISGATE_TRACE node={nu} rasterize_node returned None (clipped away / degenerate)");
                    DBG_CLIPPED_AWAY.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                } else {
                    DBG_CLIPPED_AWAY.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                }
            } else if !reachable {
                DBG_UNREACHABLE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            } else if !front_ok {
                DBG_BACKFACE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            }
        }

        cur = n.i_plane;
    }

    // Far child, full subtree, last — only after the whole coplanar chain above.
    traverse(model, far_child, light_loc, face, use_zones, active_mask, spans, out, trace, trace_portals);
}

/// TEMP root-cause diagnostic (`getvisiblesurfs-wanchai-run-gap-root-cause`, 2026-08-30): when
/// `UEDCLI_VISGATE_TRACE_SURF=<surf>` and `UEDCLI_VISGATE_TRACE_LOC=<x>,<y>,<z>` are both set, print
/// a per-face, per-fragment-node trace of exactly why the named surf was accepted/rejected for the
/// light at that location — which of `reachable`/`front_ok`/`portal_needs_zones`/`invisible` failed,
/// or whether it rasterized but the span test came back empty (self-occlusion by something already
/// in the zone buffer). Not on any hot path (env lookups only fire when both vars are set); left in
/// place as a reusable probe rather than stripped after use, matching the existing `DBG_*` counters'
/// precedent.
fn trace_target() -> Option<(i32, Vec3)> {
    let surf: i32 = std::env::var("UEDCLI_VISGATE_TRACE_SURF").ok()?.parse().ok()?;
    let loc = std::env::var("UEDCLI_VISGATE_TRACE_LOC").ok()?;
    let parts: Vec<f32> = loc.split(',').filter_map(|s| s.trim().parse().ok()).collect();
    if parts.len() != 3 {
        return None;
    }
    Some((surf, Vec3::new(parts[0], parts[1], parts[2])))
}

/// TEMP diagnostic (zone-crossing root-cause round, 2026-08-30): when `UEDCLI_VISGATE_TRACE_PORTALS`
/// is set (any value) AND `UEDCLI_VISGATE_TRACE_LOC` matches the light being gathered (same 0.5uu
/// gate as [`trace_target`]), print every `PF_PORTAL` node the traversal visits for that light,
/// regardless of which surf it is — lets a live trace answer "does native even ATTEMPT the
/// zone-crossing merge for the right portal" independent of the specific target surf's own accept/
/// reject path. Env-gated, zero cost on the default path.
fn trace_portals_for(light_loc: &Vec3) -> bool {
    if std::env::var("UEDCLI_VISGATE_TRACE_PORTALS").is_err() {
        return false;
    }
    let Ok(loc) = std::env::var("UEDCLI_VISGATE_TRACE_LOC") else { return false };
    let parts: Vec<f32> = loc.split(',').filter_map(|s| s.trim().parse().ok()).collect();
    parts.len() == 3
        && Vec3::new(parts[0], parts[1], parts[2]).sub(light_loc).size() < 0.5
}

/// The full six-face gather for one light: the port of `URender::GetVisibleSurfs`. Returns the set of
/// `iSurf` indices the editor's occlusion rasterization would list this light on (before the caller's
/// own `bSpecialLit`/radius/per-lumel filters).
pub fn get_visible_surfs(model: &Model, light_loc: Vec3) -> HashSet<i32> {
    let mut out = HashSet::new();
    if model.nodes.is_empty() {
        return out;
    }
    let trace = trace_target().filter(|(_, loc)| loc.sub(&light_loc).size() < 0.5);
    let trace_portals = trace_portals_for(&light_loc);
    let view_zone = zone_of_point(model, light_loc);
    let use_zones = view_zone != 0;
    if let Some((surf, _)) = trace {
        eprintln!(
            "VISGATE_TRACE light={light_loc:?} view_zone={view_zone} use_zones={use_zones} target_surf={surf}"
        );
    }
    if trace_portals {
        eprintln!("VISGATE_TRACE_PORTAL light={light_loc:?} view_zone={view_zone} use_zones={use_zones}");
    }
    for (fi, face) in faces().iter().enumerate() {
        let mut spans = ZoneBufs { bufs: std::collections::HashMap::new() };
        let seed_key = if use_zones { view_zone } else { SHARED_KEY };
        spans.bufs.insert(seed_key, SpanBuf::full());
        let mut active_mask: u64 = if use_zones { 1u64 << (view_zone as u64 & 63) } else { u64::MAX };
        traverse(model, 0, &light_loc, face, use_zones, &mut active_mask, &mut spans, &mut out, trace.map(|(s, _)| (fi, s)), trace_portals);
    }
    if let Some((surf, _)) = trace {
        eprintln!("VISGATE_TRACE result: surf {surf} {}", if out.contains(&surf) { "ACCEPTED" } else { "REJECTED" });
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

    /// **Regression for `getvisiblesurfs-zone-crossing-...` (2026-08-30):** a `PF_Portal` surface
    /// that is ALSO `PF_Invisible` (the near-universal real case — a zone portal is not meant to
    /// render, e.g. real Wanchai `Brush344`-style portals carry `PolyFlags=0x4000109` = `PF_Portal|
    /// PF_NotSolid|PF_TwoSided|PF_Invisible`) must still propagate visibility into its far zone. Live
    /// disassembly address ordering (`port-urender-getvisiblesurfs-so-each-light-gets`, steps 10/11)
    /// shows the real editor's `ActiveZoneMask` OR + `MergeWith` portal-crossing code (`0x1001a257`)
    /// runs BEFORE the `PF_Invisible` emission-exclusion check (`0x1001a30d`) — i.e. `PF_Invisible`
    /// only suppresses the portal surf's OWN appearance in the light's run, never the zone-crossing
    /// it performs. Gating rasterization/crossing on `!invisible` (this port's bug until this fix)
    /// silently dropped every invisible portal's zone-crossing — live-traced to a concrete Wanchai
    /// miss (Light482/surf881 via portal surf998, `zone_crossing_pairs.py` +
    /// `UEDCLI_VISGATE_TRACE_PORTALS`) and measured as a real, positive fix: Wanchai byte-identical
    /// `LightMap` records 3297/4530 (72.8%) -> 3319/4530 (73.3%), run differs 266->240; UNATCO
    /// (geometry-matched) byte-identical 2692/3345 (80.5%) -> 2739/3345 (81.9%); neither level's
    /// geometry (node/surf/leaf counts) changed (`regression_gate.py`/`breadth_gate.py` unaffected —
    /// this is a lighting-only change).
    ///
    /// Hand-built two-zone fixture (no CSG — the portal doesn't need to carve anything, mirroring
    /// the real editor's "an ADD portal brush purely divides one open volume into two zones"
    /// pattern): a single portal node at the plane `x=0` whose FRONT side (`x>0`, zone 2) holds one
    /// opaque wall node further along `+X`, and whose BACK side (`x<0`, zone 1, `i_front=-1`) is
    /// empty — the light sits in zone 1, and the wall is visible ONLY by crossing the invisible
    /// portal into zone 2.
    #[test]
    fn an_invisible_portal_still_propagates_visibility_into_its_far_zone() {
        use crate::model::{BspNode, BspSurf, BspVert};

        const PF_PORTAL_TEST: u32 = 0x0400_0000;
        const PF_INVISIBLE_TEST: u32 = 0x0000_0001;
        const PF_NOTSOLID_TEST: u32 = 0x0000_0008;
        const PF_TWOSIDED_TEST: u32 = 0x0000_0100;

        let mut m = Model {
            // 0..4: portal quad at x=0, spanning y,z in [-50,50] — closer to the light, so it
            // subtends a LARGER screen angle than the wall behind it (nests the wall's footprint
            // inside the portal's accepted span).
            points: vec![
                Vec3::new(0.0, -50.0, -50.0),
                Vec3::new(0.0, 50.0, -50.0),
                Vec3::new(0.0, 50.0, 50.0),
                Vec3::new(0.0, -50.0, 50.0),
                // 4..8: wall quad at x=50, smaller half-extent, further from the light.
                Vec3::new(50.0, -20.0, -20.0),
                Vec3::new(50.0, 20.0, -20.0),
                Vec3::new(50.0, 20.0, 20.0),
                Vec3::new(50.0, -20.0, 20.0),
            ],
            vectors: vec![
                Vec3::new(1.0, 0.0, 0.0),  // portal normal (unused: PF_Portal exempts backface cull)
                Vec3::new(-1.0, 0.0, 0.0), // wall normal, faces back toward the light at -X
            ],
            verts: (0..8).map(|i| BspVert { i_vertex: i, i_side: 0 }).collect(),
            surfs: vec![
                BspSurf {
                    texture_ref: -1,
                    poly_flags: PF_PORTAL_TEST | PF_NOTSOLID_TEST | PF_TWOSIDED_TEST | PF_INVISIBLE_TEST,
                    p_base: 0,
                    v_normal: 0,
                    v_texture_u: 0,
                    v_texture_v: 0,
                    i_actor: -1,
                    i_brush_poly: -1,
                    pan: [0, 0],
                    i_light_map: -1,
                },
                BspSurf {
                    texture_ref: -1,
                    poly_flags: 0,
                    p_base: 4,
                    v_normal: 1,
                    v_texture_u: 0,
                    v_texture_v: 0,
                    i_actor: -1,
                    i_brush_poly: -1,
                    pan: [0, 0],
                    i_light_map: -1,
                },
            ],
            nodes: vec![
                {
                    let mut n = BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, 0, 0, 4);
                    n.i_front = -1; // near side (x<0, zone 1): empty
                    n.i_back = 1; // far side (x>0, zone 2): the wall node
                    n.i_zone = [1, 2]; // [back, front] = [zone1, zone2]
                    n
                },
                {
                    let mut n = BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, 1, 4, 4);
                    n.i_zone = [2, 2]; // same zone either side — orientation doesn't matter here
                    n
                },
            ],
            root_outside: true,
            ..Model::default()
        };
        // `zone_mask` is derived from `i_zone` via BFS over iFront/iBack/iPlane (`zones::
        // build_zone_masks`) — computing it here rather than hand-picking a value keeps this fixture
        // honest about what the real build pipeline would produce from the same wiring.
        crate::zones::build_zone_masks(&mut m);
        assert_eq!(m.nodes[0].zone_mask & 0x6, 0x6, "node0 must reach both zone 1 and zone 2");
        assert_eq!(m.nodes[1].zone_mask & 0x4, 0x4, "node1 must reach zone 2");

        let visible = get_visible_surfs(&m, Vec3::new(-100.0, 0.0, 0.0));
        assert!(
            visible.contains(&1),
            "the wall (surf 1) behind an INVISIBLE portal must still be reached by crossing it, \
             got {visible:?}"
        );
        assert!(
            !visible.contains(&0),
            "the portal surf itself (PF_Invisible) must never be emitted into the light's own run"
        );
    }

    /// **Regression for the DFS-order fix (2026-08-30):** the real editor's own per-node order is
    /// documented (`port-urender-getvisiblesurfs-so-each-light-gets`, "AddUniqueItem ... front-to-back
    /// DFS order (near child -> own surface -> iPlane chain -> far child)") as near child, THEN own
    /// surface, THEN the rest of the `i_plane` coplanar chain, and ONLY THEN `far_child`. An earlier
    /// version of this port instead recursed into `far_child` immediately after the head's own
    /// surface, before walking the rest of the chain — letting `far_child`'s subtree consume shared
    /// span-buffer area before a later chain member was ever tested.
    ///
    /// Fixture (no CSG, no zones — `use_zones=false` exercises the single shared span buffer
    /// directly): a head node with an empty near side and NO surface of its own, whose `i_plane`
    /// chain holds one member (a small opaque "target" quad, closer to the light) and whose
    /// `far_child` is a bigger opaque quad, farther away but angularly LARGER, so its screen
    /// footprint fully covers the target's. If `far_child` is rasterized before the chain member,
    /// it claims the shared buffer first and the member's later test comes back empty (rejected). If
    /// the chain is walked first (correct order), the member claims its footprint while the buffer is
    /// still full and is accepted regardless of what `far_child` does afterward.
    #[test]
    fn coplanar_chain_is_walked_before_far_child_not_interleaved_with_it() {
        use crate::model::{BspNode, BspSurf, BspVert};

        let m = Model {
            // 0..4: chain-member "target" quad at x=50, half-extent 50 — closer to the light.
            points: vec![
                Vec3::new(50.0, -50.0, -50.0),
                Vec3::new(50.0, 50.0, -50.0),
                Vec3::new(50.0, 50.0, 50.0),
                Vec3::new(50.0, -50.0, 50.0),
                // 4..8: far_child "occluder" quad at x=200, half-extent 200 — farther away but
                // angularly larger (200/300 vs the target's 50/150), so it fully covers the
                // target's screen footprint if rasterized first.
                Vec3::new(200.0, -200.0, -200.0),
                Vec3::new(200.0, 200.0, -200.0),
                Vec3::new(200.0, 200.0, 200.0),
                Vec3::new(200.0, -200.0, 200.0),
            ],
            vectors: vec![Vec3::new(-1.0, 0.0, 0.0)], // both quads face back toward the light at -X
            verts: (0..8).map(|i| BspVert { i_vertex: i, i_side: 0 }).collect(),
            surfs: vec![
                BspSurf {
                    // surf 0: the chain-member target.
                    texture_ref: -1,
                    poly_flags: 0,
                    p_base: 0,
                    v_normal: 0,
                    v_texture_u: 0,
                    v_texture_v: 0,
                    i_actor: -1,
                    i_brush_poly: -1,
                    pan: [0, 0],
                    i_light_map: -1,
                },
                BspSurf {
                    // surf 1: the far_child occluder.
                    texture_ref: -1,
                    poly_flags: 0,
                    p_base: 4,
                    v_normal: 0,
                    v_texture_u: 0,
                    v_texture_v: 0,
                    i_actor: -1,
                    i_brush_poly: -1,
                    pan: [0, 0],
                    i_light_map: -1,
                },
            ],
            nodes: vec![
                {
                    // node 0: the head. No surface of its own (i_surf=-1, num_vertices=0). Near side
                    // (x<0, same side as the light) empty; far side (x>0) is node 1 (the occluder);
                    // i_plane chains to node 2 (the target).
                    let mut n = BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, -1, 0, 0);
                    n.i_front = -1;
                    n.i_back = 1;
                    n.i_plane = 2;
                    n
                },
                {
                    // node 1: far_child leaf, the occluder (surf 1).
                    BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, 1, 4, 4)
                },
                {
                    // node 2: coplanar chain member, the target (surf 0). Leaf: no children of its
                    // own, end of chain (i_plane=-1, the `BspNode::leaf` default).
                    BspNode::leaf(Plane { x: 1.0, y: 0.0, z: 0.0, w: 0.0 }, 0, 0, 4)
                },
            ],
            root_outside: true,
            ..Model::default()
        };
        // zone_mask defaults to u64::MAX (`BspNode::leaf`) and use_zones is false here (the light
        // sits in zone 0, the default `i_zone`), so the zone-mask prune never engages — this fixture
        // isolates the chain/far_child ORDER question from zone-crossing entirely.

        let visible = get_visible_surfs(&m, Vec3::new(-100.0, 0.0, 0.0));
        assert!(
            visible.contains(&0),
            "the coplanar chain member (surf 0) must be tested before far_child's larger, opaque \
             subtree can claim its span-buffer footprint, got {visible:?}"
        );
    }

    #[test]
    fn merge_into_matches_the_real_editors_output() {
        // Pins `mergewith-fully-decoded-confirms-merge-into` (2026-08-30): the real editor's
        // `FSpanBuffer::MergeWith` (render.dll 0x1001e3b0), live-captured node-for-node during a real
        // Wanchai `LIGHT APPLY` (`mergewith_live_check.py`), against `merge_into` fed the exact same
        // pre-existing row content and incoming interval, for all 3 sampled cases that were a genuine
        // merge (not a plain append into an empty row) — including two touching-boundary merges.
        struct Case {
            row_before: &'static [(i32, i32)],
            incoming: (i32, i32),
            row_after: &'static [(i32, i32)],
        }
        // (this row content, other's incoming interval) -> this row content after MergeWith, as
        // captured live: n=3 (y=702), n=6 (y=627), n=8 (y=887).
        let cases = [
            Case { row_before: &[(315, 316)], incoming: (316, 317), row_after: &[(315, 317)] },
            Case { row_before: &[(978, 980)], incoming: (976, 978), row_after: &[(976, 980)] },
            Case { row_before: &[(974, 991)], incoming: (971, 974), row_after: &[(971, 991)] },
        ];
        for c in cases {
            let mut buf = SpanBuf::empty();
            buf.rows[0] = c.row_before.to_vec();
            merge_into(&mut buf, &[(0, c.incoming.0, c.incoming.1)]);
            assert_eq!(
                buf.rows[0], c.row_after,
                "row {:?} + incoming {:?} should merge to {:?}",
                c.row_before, c.incoming, c.row_after
            );
        }
    }
}
