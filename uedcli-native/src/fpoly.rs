//! `FPoly` — the working polygon of CSG (§10.2-3).  The N-1 port: `CalcNormal`, `Fix`,
//! `RemoveColinears`, `Finalize`, `Reverse`, `Transform`, and `SplitWithPlane` (classify +
//! cut) with the exact engine thresholds.  Beyond geometry, an `FPoly` carries the
//! **surf-link metadata** (`actor`/`texture`/`i_link`/`i_brush_poly`/`pan`) that flows
//! through the CSG leaf-filter into `bspAddNode` (§6.4) — a fragment's surf identity.
//!
//! **FP fidelity (spike 41):** native `f32`, no `mul_add`/FMA; dot products reduce
//! left-to-right (see `model::Vec3::dot`).  Validated differentially against editor goldens
//! (§6 gate 3), not assumed bit-identical.

use crate::model::{BuildError, Vec3};

pub const THRESH_SPLIT_POLY_WITH_PLANE: f32 = 0.25;
pub const THRESH_SPLIT_POLY_PRECISELY: f32 = 0.01;
pub const SMALL_NUMBER: f32 = 1.0e-8;
pub const THRESH_COLINEAR: f32 = 9.999999e-05;
pub const THRESH_POINTS_ARE_SAME: f32 = 0.002;
pub const MAX_VERTICES: usize = 16;

/// The transient split marker the engine ORs into a cut fragment's PolyFlags (§3).
pub const PF_SPLIT_MARKER: u32 = 0x8000_0000;

/// `FVector::TransformVectorBy(FCoords)` (core.dll 0x2dd50): map a direction/covector by an FCoords
/// whose ROWS are its axes — `result[i] = V · axis[i]`, the dot reduced `(a·p + b·q) + c·r` (matches
/// the engine's SSE op-order and `Vec3::dot`).  Used for the scaled-brush face normal covariant map.
pub fn transform_vector_by(v: &Vec3, m: &[[f32; 3]; 3]) -> Vec3 {
    Vec3::new(
        (v.x * m[0][0] + v.y * m[0][1]) + v.z * m[0][2],
        (v.x * m[1][0] + v.y * m[1][1]) + v.z * m[1][2],
        (v.x * m[2][0] + v.y * m[2][1]) + v.z * m[2][2],
    )
}

/// `FVector::SafeNormalSlow` (core.dll 0x27180): normalize with the engine's f64-widened magnitude —
/// `SquareSize = (x*x+y*y)+z*z` (f32); below `SMALL_NUMBER` (1e-8) return None (zero vector); else
/// `inv = 1.f / (f32)sqrt((f64)SquareSize)` and scale.  Byte-faithful to the routine `FPoly::Transform`
/// applies to the face Normal (unlike `calc_normal`'s `NormalizeSlow`, which is the SAME arithmetic —
/// they differ only in that `CalcNormal` derives the vector from the winding).  §92 §43.
pub fn safe_normal_slow(v: &Vec3) -> Option<Vec3> {
    let sq = (v.x * v.x + v.y * v.y) + v.z * v.z;
    if sq < SMALL_NUMBER {
        return None;
    }
    let inv = 1.0f32 / ((sq as f64).sqrt() as f32);
    Some(Vec3::new(v.x * inv, v.y * inv, v.z * inv))
}

/// `FVector::SafeNormal` (`Core.dll 0x51090`) — the FAST sibling of [`safe_normal_slow`].  Same
/// `SquareSum = ((x*x)+(y*y))+(z*z)` and the same `SMALL_NUMBER` cutoff, but the reciprocal is built
/// differently: the `sqrt` result is rounded to f32 (`0x100510f5 fstp dword`), reloaded, and
/// `1.0 / root` is evaluated in x87 80-bit and only then rounded to f32 (`0x10051104 fstp dword`) —
/// modelled as an f64 divide, not `safe_normal_slow`'s single-precision one.  `None` is the
/// editor's zero vector.
pub fn safe_normal(v: &Vec3) -> Option<Vec3> {
    let square_sum = v.x * v.x + v.y * v.y + v.z * v.z;
    if square_sum < SMALL_NUMBER {
        return None;
    }
    let root = (square_sum as f64).sqrt() as f32;
    let scale = (1.0f64 / root as f64) as f32;
    Some(Vec3::new(v.x * scale, v.y * scale, v.z * scale))
}

/// `FLinePlaneIntersection(P1, P2, PlaneBase, PlaneNormal)` (`Engine.dll 0x1506f0`) — where the
/// segment `P1→P2` meets the plane.  The engine derives the parameter from two FRESH dot products,
/// `t = ((Base-P1)·N) / ((P2-P1)·N)` with one `divss` (`0x150780`), not from the two vertices'
/// already-computed signed distances.  The two forms are algebraically equal but cancel in
/// different places — this one dots fresh coordinate differences where the other subtracts two
/// rounded plane distances — so they part in the low bits at world scale, and the cut vertex is
/// stored.
fn line_plane_intersection(p1: &Vec3, p2: &Vec3, base: &Vec3, normal: &Vec3) -> Vec3 {
    let dir = p2.sub(p1);
    let t = base.sub(p1).dot(normal) / dir.dot(normal);
    Vec3::new(p1.x + dir.x * t, p1.y + dir.y * t, p1.z + dir.z * t)
}

#[derive(Debug, Clone, PartialEq)]
pub enum Split {
    Front,
    Back,
    Coplanar,
    Split(FPoly, FPoly),
}

#[derive(Debug, Clone, PartialEq)]
pub struct FPoly {
    pub base: Vec3,
    pub normal: Vec3,
    pub texture_u: Vec3,
    pub texture_v: Vec3,
    pub verts: Vec<Vec3>,
    pub poly_flags: u32,
    // surf-link metadata (→ Surf fields at bspAddNode; §6.4)
    pub actor: i32,
    pub texture: i32,
    pub i_link: i32,
    pub i_brush_poly: i32,
    /// Authored texture pan (T3D `Pan U=/V=`), copied verbatim into the surf's `PanU`/`PanV`.  The
    /// transform does not touch it and every split fragment inherits it (`empty_copy`).
    pub pan: [i32; 2],
    /// SOURCE-poly index for the mover build's saved-`iLink` tracking (`build_brush_model`): set on
    /// each input poly, and deliberately DROPPED (-1) by `empty_copy` so a split FRAGMENT is never
    /// mistaken for its whole original — the editor rewrites a `Polys` element's `iLink` only when
    /// the pointed-at original itself is consumed whole (splitter/coplanar), never via a fragment
    /// copy.  -1 (untracked) everywhere else.
    pub src: i32,
}

impl FPoly {
    pub fn new(verts: Vec<Vec3>) -> Self {
        FPoly {
            base: verts.first().copied().unwrap_or(Vec3::new(0.0, 0.0, 0.0)),
            normal: Vec3::new(0.0, 0.0, 0.0),
            texture_u: Vec3::new(0.0, 0.0, 0.0),
            texture_v: Vec3::new(0.0, 0.0, 0.0),
            verts,
            poly_flags: 0,
            actor: 0,
            texture: 0,
            i_link: -1,
            i_brush_poly: -1,
            pan: [0, 0],
            src: -1,
        }
    }

    /// Triangle-fan normal `Σ (V[i-1]-V[0]) × (V[i]-V[0])`, normalized; returns false if
    /// zero-area (|N|² < SMALL_NUMBER) — a degenerate poly the caller must reject.
    pub fn calc_normal(&mut self) -> bool {
        let mut n = Vec3::new(0.0, 0.0, 0.0);
        let n_verts = self.verts.len();
        for i in 2..n_verts {
            let a = self.verts[i - 1].sub(&self.verts[0]);
            let b = self.verts[i].sub(&self.verts[0]);
            let c = a.cross(&b);
            n = Vec3::new(n.x + c.x, n.y + c.y, n.z + c.z);
        }
        let mag2 = n.dot(&n);
        if mag2 < SMALL_NUMBER {
            return false;
        }
        // Byte-faithful to Engine.dll `FVector::NormalizeSlow` (core.dll 0x249d0), the routine
        // `FPoly::CalcNormal` (Engine.dll 0x150510) calls to normalize: it computes the magnitude
        // as `(f32)sqrt((f64)SquareSize)` — SquareSize is f32, widened to f64 for `sqrtsd`, then
        // narrowed back to f32 (`cvtps2pd`/`sqrtsd`/`cvtsd2ss`) — NOT a direct f32 `sqrtss`.  The two
        // differ by up to 1 ULP on the rare double-rounding input; matching it makes native's
        // recomputed normal reproduce the editor's for the same verts.  (§92 §16 decode; the
        // cross-product `operator^` and `operator+=` accumulation above already byte-match natively.)
        let inv = 1.0f32 / ((mag2 as f64).sqrt() as f32);
        self.normal = Vec3::new(n.x * inv, n.y * inv, n.z * inv);
        true
    }

    /// `FPoly::Fix` (Engine.dll `0x150da0`, IAT `0x100cee38`) — drop near-duplicate consecutive
    /// vertices, returning the surviving count.
    ///
    /// Two details are load-bearing and were both got wrong by the obvious implementation; they
    /// matter more now that this is the accept gate for every face `BRUSH FROM INTERSECTION`
    /// collects (`bspcsg::collect_leaf`), not just a tidy-up:
    ///
    /// * **The reference vertex is the LAST KEPT one, not the previous original.**  The binary
    ///   updates its `prev` slot only on a keep (`0x10150e49`: `mov ecx, esi` / `mov [ebp-0x1c],
    ///   ecx` inside the keep branch).  Comparing against the previous *original* instead lets a
    ///   chain of sub-threshold steps accumulate: three 0.0015 hops in a row are each "same" as
    ///   their predecessor, so all three are dropped, and a poly the editor keeps can fall under 3
    ///   verts and vanish.
    /// * **The same-test is a per-AXIS box test, not a Euclidean distance.**  `0x101508e9` compares
    ///   `|dx|`, then `|dy|`, then `|dz|` against `THRESH_POINTS_ARE_SAME` with `comiss` (strict),
    ///   treating the pair as identical only if ALL THREE are within it.  A Euclidean test
    ///   disagrees on the diagonal: a `(0.0015, 0.0015, 0.0015)` delta has length `0.0026 > 0.002`
    ///   so the distance form KEEPS it, while the editor's box form drops it.
    ///
    /// (The binary also sets `NumVertices = (j >= 3) ? j : 0` and calls
    /// `FPoly::DiscardVertexDeltas(1)`; neither has an analogue here — the caller reads the return
    /// value and there is no delta array.)
    pub fn fix(&mut self) -> usize {
        if self.verts.is_empty() {
            return 0;
        }
        let same = |a: &Vec3, b: &Vec3| {
            (a.x - b.x).abs() < THRESH_POINTS_ARE_SAME
                && (a.y - b.y).abs() < THRESH_POINTS_ARE_SAME
                && (a.z - b.z).abs() < THRESH_POINTS_ARE_SAME
        };
        let n = self.verts.len();
        let mut out: Vec<Vec3> = Vec::with_capacity(n);
        // Seed `prev` with the LAST vertex, so the ring closes the way the editor's does.
        let mut prev = self.verts[n - 1];
        for i in 0..n {
            let cur = self.verts[i];
            if !same(&cur, &prev) {
                out.push(cur);
                prev = cur; // advance only on a KEEP
            }
        }
        self.verts = out;
        self.verts.len()
    }

    /// `FPoly::RemoveColinears` (Engine.dll `0x151090`, cross-checked against the DLL's own PE
    /// export table and pinned by x86 emulation of the real bytes against a real editor-captured
    /// ring — board item `bspmergecoplanars-8-case-merge-gap-live-traced` follow-up, 2026-08-25).
    /// THREE stages, not two — an earlier reading of this function (and this port) missed the
    /// third:
    ///
    /// 1. **Coincident-vertex removal.** `Side = V[i] - V[i-1]`, `NormalizeSlow(Side × Normal)`
    ///    fails (squared length `< SMALL_NUMBER`) when `V[i]` sits within ~1e-4 uu of `V[i-1]` —
    ///    that vertex is redundant, drop it (no advance; the shifted-in vertex is re-tested at
    ///    the same index, matching the engine's in-place array shift). The normalized
    ///    `Side × Normal` — the edge's OUTWARD in-plane normal — is cached per surviving vertex
    ///    (`sides`, never recomputed, only ever shifted alongside a later removal) for stage 2.
    /// 2. **Per surviving vertex, in ring order:** if its cached side-normal and the NEXT
    ///    vertex's are component-wise near (`THRESH_COLINEAR`) — i.e. the two edges meeting at
    ///    this vertex are parallel, a straight run — the vertex is redundant, drop it (same
    ///    no-advance/re-test rule). Otherwise (a genuine corner) run a **convexity gate**:
    ///    classify the WHOLE ring against the tangent plane through this vertex
    ///    (`Base = V[i]`, `Normal = sides[i]`, `SplitWithPlane`). A properly convex vertex has
    ///    every other vertex on the BACK (interior) side, or exactly on the plane (Coplanar). If
    ///    the classification comes back `Front` or `Split` — some other vertex pokes past this
    ///    one's own tangent plane, i.e. this is a **reflex vertex** — the WHOLE merge is
    ///    rejected outright (`return 0`), not just this one vertex.
    /// 3. **`NumVertices < 3` at any point → reject** (`return 0`); the poly vanishes (a
    ///    "silent-absence hole" source).
    pub fn remove_colinears(&mut self) -> usize {
        if self.verts.len() < 3 {
            self.verts.clear();
            return 0;
        }
        let mut verts = std::mem::take(&mut self.verts);
        let mut sides: Vec<Vec3> = Vec::with_capacity(verts.len());

        // Stage 1 — coincident-vertex removal.
        let mut i = 0;
        while i < verts.len() {
            let prev = verts[(i + verts.len() - 1) % verts.len()];
            let side = verts[i].sub(&prev);
            let sxn = side.cross(&self.normal);
            match safe_normal_slow(&sxn) {
                None => {
                    verts.remove(i);
                }
                Some(s) => {
                    sides.push(s);
                    i += 1;
                }
            }
            if verts.len() < 3 {
                self.verts.clear();
                return 0;
            }
        }

        // Stage 2 — per-vertex colinear-redundancy removal, else the reflex-vertex convexity
        // gate.
        let vectors_near = |a: &Vec3, b: &Vec3| -> bool {
            (a.x - b.x).abs() < THRESH_COLINEAR
                && (a.y - b.y).abs() < THRESH_COLINEAR
                && (a.z - b.z).abs() < THRESH_COLINEAR
        };
        let mut i = 0;
        while i < verts.len() {
            let next_i = (i + 1) % verts.len();
            if vectors_near(&sides[i], &sides[next_i]) {
                verts.remove(i);
                sides.remove(i);
                if verts.len() < 3 {
                    self.verts.clear();
                    return 0;
                }
                continue;
            }
            // `false` (0.25 threshold) confirmed at this exact call site by disassembly: the
            // `VeryPrecise` arg at `Engine.dll` 0x10151343 is a literal `push 0`.
            let probe = FPoly::new(verts.clone());
            match probe.split_with_plane(&verts[i], &sides[i], false) {
                Split::Front | Split::Split(_, _) => {
                    self.verts.clear();
                    return 0;
                }
                Split::Back | Split::Coplanar => {}
            }
            i += 1;
        }

        self.verts = verts;
        self.verts.len()
    }

    /// `Finalize` (§2): Fix, ensure ≥3 verts, compute a normal if absent.  Returns Err on a
    /// degenerate poly (fewer than 3 real verts, or zero area) — the caller drops it.  (The
    /// engine's `NoError=0` variant `appErrorf`s; a native build must instead REJECT the poly,
    /// never abort — repo rule "no exception reaches the user".)
    pub fn finalize(&mut self) -> Result<(), BuildError> {
        if self.fix() < 3 {
            return Err(BuildError("degenerate poly: fewer than 3 vertices".into()));
        }
        if self.normal.dot(&self.normal) < SMALL_NUMBER && !self.calc_normal() {
            return Err(BuildError("degenerate poly: zero area (no normal)".into()));
        }
        Ok(())
    }

    /// Flip winding + normal (engine `FPoly::Reverse`): the vertex ring reverses and the
    /// normal negates; base/texture axes are unchanged.
    pub fn reverse(&mut self) {
        self.verts.reverse();
        self.normal = Vec3::new(-self.normal.x, -self.normal.y, -self.normal.z);
    }

    /// `FPoly::Transform` (§4.1): world = `Location + R·(v − PrePivot)`.  Scale/SheerRate are
    /// NOT yet ported — a non-identity scale is REJECTED (§3), never silently mis-built.
    /// `rot` is a 3×3 row-major rotation matrix (identity for the common case).
    pub fn transform(
        &mut self,
        rot: &[[f32; 3]; 3],
        prepivot: &Vec3,
        location: &Vec3,
    ) -> Result<(), BuildError> {
        let xf = |v: &Vec3| -> Vec3 {
            let p = v.sub(prepivot);
            let rx = rot[0][0] * p.x + rot[0][1] * p.y + rot[0][2] * p.z;
            let ry = rot[1][0] * p.x + rot[1][1] * p.y + rot[1][2] * p.z;
            let rz = rot[2][0] * p.x + rot[2][1] * p.y + rot[2][2] * p.z;
            Vec3::new(rx + location.x, ry + location.y, rz + location.z)
        };
        for v in self.verts.iter_mut() {
            *v = xf(v);
        }
        self.base = xf(&self.base);
        // Normal/texture axes rotate WITHOUT translation.
        let rot_only = |v: &Vec3| -> Vec3 {
            Vec3::new(
                rot[0][0] * v.x + rot[0][1] * v.y + rot[0][2] * v.z,
                rot[1][0] * v.x + rot[1][1] * v.y + rot[1][2] * v.z,
                rot[2][0] * v.x + rot[2][1] * v.y + rot[2][2] * v.z,
            )
        };
        self.normal = rot_only(&self.normal);
        self.texture_u = rot_only(&self.texture_u);
        self.texture_v = rot_only(&self.texture_v);
        Ok(())
    }

    /// Signed distance of a point from this poly's plane: `(P − Base) · Normal`.
    pub fn plane_dist(&self, p: &Vec3) -> f32 {
        p.sub(&self.base).dot(&self.normal)
    }

    /// `SplitWithPlane` (§10.3): classify against `(base, normal)` and, when straddling, cut
    /// into Front/Back fragments.  `very_precise` selects T (0.01) else 0.25.
    pub fn split_with_plane(&self, base: &Vec3, normal: &Vec3, very_precise: bool) -> Split {
        let t = if very_precise {
            THRESH_SPLIT_POLY_PRECISELY
        } else {
            THRESH_SPLIT_POLY_WITH_PLANE
        };
        let dists: Vec<f32> = self.verts.iter().map(|v| v.sub(base).dot(normal)).collect();
        let max_dist = dists.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
        let min_dist = dists.iter().cloned().fold(f32::INFINITY, f32::min);

        if max_dist < t && min_dist > -t {
            return Split::Coplanar;
        }
        if max_dist < t && min_dist <= -t {
            return Split::Back;
        }
        if max_dist >= t && min_dist > -t {
            return Split::Front;
        }

        // straddles -> cut (`Engine.dll 0x151b40`..`0x151ed8`)
        let n = self.verts.len();
        let mut front = self.empty_copy();
        let mut back = self.empty_copy();
        // A vertex inside the ±T band gets no side of its own: it INHERITS the running side
        // (`0x151e47 mov [ebp-0x1c], ecx` — `Status = PrevStatus`), so it joins one ring, never
        // both.  The classify pre-pass leaves the last vertex's side in `PrevStatus`
        // (`0x151b34`), which is what the wrap-around edge is compared against.
        const FRONT: u8 = 0;
        const BACK: u8 = 1;
        let side = |d: f32, prev: u8| -> u8 {
            if d > t {
                FRONT
            } else if d < -t {
                BACK
            } else {
                prev
            }
        };
        let mut prev_status = 2u8; // V_EITHER, the pre-pass seed (`0x1518f7 mov edi,2`)
        for d in &dists {
            prev_status = side(*d, prev_status);
        }
        let mut prev_i = n - 1;
        for i in 0..n {
            let status = side(dists[i], prev_status);
            if status != prev_status {
                // Crossing.  When the PREVIOUS vertex is itself in the band it IS the cut point
                // (`0x151c97`: `-T <= PrevDist < T`), and since it already sits in the ring it
                // inherited, it is added to the NEW side only — not to both.
                // The binary has a third arm first (`0x151be7`, "the CURRENT vertex is in the
                // band → it is the cut point"): dead code, because an in-band vertex inherits
                // `PrevStatus` and so can never reach a `status != prev_status` branch.
                if dists[prev_i] >= -t && dists[prev_i] < t {
                    let v = self.verts[prev_i];
                    if status == FRONT {
                        front.verts.push(v);
                    } else {
                        back.verts.push(v);
                    }
                } else {
                    let inter =
                        line_plane_intersection(&self.verts[prev_i], &self.verts[i], base, normal);
                    front.verts.push(inter);
                    back.verts.push(inter);
                }
            }
            if status == FRONT {
                front.verts.push(self.verts[i]);
            } else {
                back.verts.push(self.verts[i]);
            }
            prev_status = status;
            prev_i = i;
        }
        front.fix();
        back.fix();
        Split::Split(front, back)
    }

    /// Split a >MAX_VERTICES poly roughly in half, sharing the cut edge (engine
    /// `SplitInHalf`; §4.2 / §6.4).  Returns the second half; `self` keeps the first.  Both
    /// share two vertices (the seam) so the pieces re-close.
    pub fn split_in_half(&mut self) -> FPoly {
        let n = self.verts.len();
        let m = n / 2; // engine: NumVertices/2 on the first half's last index
        let mut half = self.empty_copy();
        half.poly_flags = self.poly_flags;
        // second half: verts[m .. n] plus wrap vert[0]
        for i in m..n {
            half.verts.push(self.verts[i]);
        }
        half.verts.push(self.verts[0]);
        // first half: verts[0 .. m] plus vert[m]
        let first: Vec<Vec3> = (0..=m).map(|i| self.verts[i]).collect();
        self.verts = first;
        half
    }

    /// A metadata-preserving empty copy (used by the split routines): geometry cleared, the
    /// surf-link identity + plane basis retained, the transient split marker ORed in.
    fn empty_copy(&self) -> FPoly {
        FPoly {
            base: self.base,
            normal: self.normal,
            texture_u: self.texture_u,
            texture_v: self.texture_v,
            verts: Vec::new(),
            poly_flags: self.poly_flags | PF_SPLIT_MARKER,
            actor: self.actor,
            texture: self.texture,
            i_link: self.i_link,
            i_brush_poly: self.i_brush_poly,
            pan: self.pan,
            src: -1, // a fragment is not its source poly (see the field doc)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn square_xy(z: f32) -> FPoly {
        FPoly::new(vec![
            Vec3::new(-10.0, -10.0, z),
            Vec3::new(10.0, -10.0, z),
            Vec3::new(10.0, 10.0, z),
            Vec3::new(-10.0, 10.0, z),
        ])
    }

    #[test]
    fn calc_normal_of_ccw_square_points_up() {
        let mut p = square_xy(0.0);
        assert!(p.calc_normal());
        assert!((p.normal.z - 1.0).abs() < 1e-5);
        assert!(p.normal.x.abs() < 1e-5 && p.normal.y.abs() < 1e-5);
    }

    #[test]
    fn calc_normal_axis_quad_is_exactly_unit() {
        // A clean axis-aligned quad must recompute to an EXACT unit normal (bit 0x3f800000),
        // not 0.99999994.  Engine.dll `FPoly::CalcNormal` (0x150510) → `NormalizeSlow` (0x249d0)
        // yields exact 1.0 here, and native's op-order (f64-widened sqrt, matching NormalizeSlow)
        // reproduces it byte-exact.  Pins the §92 §16 axis case.
        let mut p = square_xy(128.0);
        assert!(p.calc_normal());
        assert_eq!(p.normal.z.to_bits(), 0x3f80_0000, "N.z must be exactly 1.0");
        assert_eq!(p.normal.x.to_bits() & 0x7fff_ffff, 0);
        assert_eq!(p.normal.y.to_bits() & 0x7fff_ffff, 0);
    }

    #[test]
    fn calc_normal_dome_facet_matches_engine_dll_op_order() {
        // §92 §16: native `calc_normal` byte-reproduces Engine.dll `FPoly::CalcNormal` (0x150510:
        // `operator^` cross core 0x17cf0 + `operator+=` core 0x188f0 accumulation + `NormalizeSlow`
        // core 0x249d0 f64-widened-sqrt normalize) over BYTE-IDENTICAL verts.  These are UNATCO
        // Brush755's dome facet (i_brush_poly 44) verts, transformed by Location (540,1204,276),
        // proven byte-identical to the editor's gdb-dumped brush-model verts (`oracle-105.log`).
        //
        // Native (== Engine.dll over these verts) yields N.x bits 0xbf3b0791 (0.7305842).  The
        // editor STORES 0x3f3b07a5 (0.7305854, ~20 ULP higher) in golden105.dx — NOT reproducible
        // by ANY calc_normal op-order over these verts (brute-forced): the editor recomputes the
        // stored surf plane over its `bspAddPoint`-POOLED world verts, which differ from the exact
        // T3D verts by ~1e-4.  So this pins that the op-order is CORRECT and the residual is the
        // upstream vertex pool, not CalcNormal.
        let v = |x: u32, y: u32, z: u32| {
            Vec3::new(f32::from_bits(x), f32::from_bits(y), f32::from_bits(z))
        };
        let mut p = FPoly::new(vec![
            v(0x43ff_ad0d, 0x4497_c151, 0x4387_999a), // A
            v(0x4400_8289, 0x4497_a0a9, 0x4386_0000), // B
            v(0x4400_745d, 0x4497_8000, 0x4386_0000), // C
            v(0x43ff_745c, 0x4497_8000, 0x4387_999a), // D
        ]);
        assert!(p.calc_normal());
        assert_eq!(p.normal.x.to_bits(), 0xbf3b_0791, "dome N.x op-order pin");
        assert_eq!(p.normal.y.to_bits(), 0x3e22_534f, "dome N.y op-order pin");
        assert_eq!(p.normal.z.to_bits(), 0xbf2a_06d7, "dome N.z op-order pin");
    }

    #[test]
    fn scaled_face_covariant_normal_matches_editor_bits_not_calc_normal_twin() {
        // §92 §43 — the scaled-brush committed-tree twin (UNATCO Brush578 +y face, N=30 node 359).
        // Brush578 PostScale=(1.0625,0.625,1); PrePivot=(-7.529359,-12.799914,-6); Location=(144,1824,314).
        //
        // (A) NATIVE'S OLD PATH — `calc_normal` over the L-warped WORLD winding of the +y face (these are
        // the ACTUAL f32 world verts native's `FPoly::transform` produces, order-for-order) drifts to
        // `0x3f7fffff` (0.99999994, 1 ULP under unit) — the twin.  This assertion is the DISCRIMINATOR:
        // it FAILS the covariant claim only if `calc_normal` were used for the stored normal.
        let mut p = FPoly::new(vec![
            Vec3::new(f32::from_bits(0x417f_ff50), f32::from_bits(0x44f3_fffe), f32::from_bits(0x4370_0000)),
            Vec3::new(f32::from_bits(0x417f_ff50), f32::from_bits(0x44f3_fffe), f32::from_bits(0x43c8_0000)),
            Vec3::new(f32::from_bits(0x4390_0002), f32::from_bits(0x44f3_fffe), f32::from_bits(0x43c8_0000)),
            Vec3::new(f32::from_bits(0x4390_0002), f32::from_bits(0x44f3_fffe), f32::from_bits(0x4370_0000)),
        ]);
        assert!(p.calc_normal());
        assert_eq!(
            p.normal.y.to_bits(),
            0x3f7f_ffff,
            "calc_normal over the scaled world winding IS the twin (0.99999994)"
        );
        // (B) THE FIX — the editor's covariant path: the brush-LOCAL normal (0,1,0) through VectorXform
        // `(L⁻¹)ᵀ = diag(1/PS)` + `SafeNormalSlow` renormalizes to the EXACT `0x3f800000` the editor
        // STORES (gdb `Model->Nodes` over golden30, node 359 = `0xbf800000` = -this).
        let vec_xform = [
            [f32::from_bits(0x3f70_f0f1), 0.0, 0.0], // 1/1.0625
            [0.0, f32::from_bits(0x3fcc_cccd), 0.0], // 1/0.625
            [0.0, 0.0, 1.0f32],
        ];
        let cov = safe_normal_slow(&transform_vector_by(&Vec3::new(0.0, 1.0, 0.0), &vec_xform))
            .expect("covariant image is non-degenerate");
        assert_eq!(
            cov.y.to_bits(),
            0x3f80_0000,
            "covariant SafeNormalSlow must reproduce the editor's stored EXACT-unit bit"
        );
    }

    #[test]
    fn scaled_face_covariant_reproduces_editor_non_unit_normal() {
        // §92 §43 — the covariant path does NOT blindly snap to 1.0: for UNATCO Brush562 +x face
        // (PostScale=(1.625,1.416666,1)) the editor STORES `0x3f7fffff` (0.99999994) — its own
        // `SafeNormalSlow(diag(1/PS)·N_local)` renormalizes `1/1.625` to 0.99999994 (the f64-widened
        // magnitude double-rounds).  Native's covariant path reproduces that EXACT non-unit bit, so
        // Brush562 was never a twin (native == editor both 0.99999994 — N=30 diff, no node 349-356
        // divergence).  Pins that the fix matches the editor's bits WHATEVER they round to.
        let vec_xform = [
            [f32::from_bits(0x3f1d_89d9), 0.0, 0.0], // 1/1.625
            [0.0, f32::from_bits(0x3f34_b4ba), 0.0], // 1/1.416666
            [0.0, 0.0, 1.0f32],
        ];
        let cov = safe_normal_slow(&transform_vector_by(&Vec3::new(1.0, 0.0, 0.0), &vec_xform)).unwrap();
        assert_eq!(cov.x.to_bits(), 0x3f7f_ffff);
    }

    #[test]
    fn safe_normal_slow_pins_engine_bits_on_a_non_axis_vector() {
        // §92 §43: `SafeNormalSlow` (core.dll 0x27180) = `inv = 1.f/(f32)sqrt((f64)SquareSum)` with
        // the sum reduced `(x*x+y*y)+z*z`, returning None below SMALL_NUMBER (1e-8).  A NON-axis input
        // exercises all three (reduction order + f64-widened sqrt + reciprocal-then-multiply); the
        // expected output bits are HARDCODED (not self-derived) so any change to the arithmetic trips.
        let n = safe_normal_slow(&Vec3::new(
            f32::from_bits(0x3e99_999a), // 0.3
            f32::from_bits(0xbf33_3333), // -0.7
            f32::from_bits(0x3f25_e54b), // 0.64803
        ))
        .unwrap();
        assert_eq!(n.x.to_bits(), 0x3e99_9aba);
        assert_eq!(n.y.to_bits(), 0xbf33_3483);
        assert_eq!(n.z.to_bits(), 0x3f25_e682);
        assert!(safe_normal_slow(&Vec3::new(0.0, 0.0, 0.0)).is_none());
    }

    #[test]
    fn degenerate_poly_has_no_normal() {
        let mut p = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(1.0, 0.0, 0.0),
            Vec3::new(2.0, 0.0, 0.0),
        ]);
        assert!(!p.calc_normal());
    }

    #[test]
    fn classify_front_back_coplanar() {
        let p = square_xy(0.0);
        let base = Vec3::new(0.0, 0.0, 0.0);
        let up = Vec3::new(0.0, 0.0, 1.0);
        let hi = square_xy(100.0);
        assert_eq!(hi.split_with_plane(&base, &up, false), Split::Front);
        let lo = square_xy(-100.0);
        assert_eq!(lo.split_with_plane(&base, &up, false), Split::Back);
        assert_eq!(p.split_with_plane(&base, &up, false), Split::Coplanar);
    }

    #[test]
    fn split_produces_two_fragments() {
        let p = FPoly::new(vec![
            Vec3::new(-10.0, 0.0, -10.0),
            Vec3::new(10.0, 0.0, -10.0),
            Vec3::new(10.0, 0.0, 10.0),
            Vec3::new(-10.0, 0.0, 10.0),
        ]);
        let base = Vec3::new(0.0, 0.0, 0.0);
        let up = Vec3::new(0.0, 0.0, 1.0);
        match p.split_with_plane(&base, &up, false) {
            Split::Split(front, back) => {
                assert!(front.verts.len() >= 3, "front {:?}", front.verts);
                assert!(back.verts.len() >= 3, "back {:?}", back.verts);
            }
            other => panic!("expected Split, got {:?}", other),
        }
    }

    #[test]
    fn on_plane_vertex_joins_one_fragment_not_both() {
        // A vertex inside the ±0.25 band takes the running side (`Engine.dll 0x151e47`), so it
        // lands in ONE fragment.  Here the on-plane vertex (0,0,0) sits between two front
        // vertices, so both it and its two neighbours go front and the back fragment is the bare
        // triangle below the plane.  Copying the vertex into BOTH rings instead leaves a colinear
        // extra vertex in the back ring that `Fix` cannot drop (it is not a duplicate).
        let p = FPoly::new(vec![
            Vec3::new(-10.0, 0.0, 10.0),
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(10.0, 0.0, 10.0),
            Vec3::new(0.0, 0.0, -10.0),
        ]);
        match p.split_with_plane(&Vec3::new(0.0, 0.0, 0.0), &Vec3::new(0.0, 0.0, 1.0), false) {
            Split::Split(front, back) => {
                assert_eq!(front.verts.len(), 5, "front {:?}", front.verts);
                assert_eq!(back.verts.len(), 3, "back {:?}", back.verts);
                // The two cut points, from `line_plane_intersection` — halfway along each of the
                // two crossing edges.
                assert_eq!(
                    (back.verts[0].x, back.verts[0].z, back.verts[1].x, back.verts[1].z),
                    (-5.0, 0.0, 5.0, 0.0),
                    "cut points {:?}",
                    back.verts
                );
            }
            other => panic!("expected Split, got {:?}", other),
        }
    }

    #[test]
    fn fix_drops_duplicate_vertices() {
        let mut p = FPoly::new(vec![
            Vec3::new(0.0, 0.0, 0.0),
            Vec3::new(0.0, 0.0, 0.0001),
            Vec3::new(10.0, 0.0, 0.0),
            Vec3::new(10.0, 10.0, 0.0),
        ]);
        assert_eq!(p.fix(), 3);
    }

    #[test]
    fn reverse_flips_winding_and_normal() {
        let mut p = square_xy(0.0);
        p.calc_normal();
        let n0 = p.normal;
        let v0 = p.verts.clone();
        p.reverse();
        assert!((p.normal.z + n0.z).abs() < 1e-6);
        assert_eq!(p.verts, v0.iter().rev().cloned().collect::<Vec<_>>());
    }

    #[test]
    fn transform_translates() {
        let id = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
        let mut p = square_xy(0.0);
        p.transform(&id, &Vec3::new(0.0, 0.0, 0.0), &Vec3::new(100.0, 0.0, 0.0))
            .unwrap();
        assert!((p.verts[0].x - -10.0 - 100.0).abs() < 1e-4);
    }

    #[test]
    fn remove_colinears_rejects_a_reflex_merge_ring() {
        // `bspmergecoplanars-8-case-merge-gap-live-traced` follow-up (2026-08-25): the real
        // editor's `RemoveColinears` (Engine.dll 0x151090) has a third stage neither this port
        // nor the earlier board item caught — a convexity gate (§ port doc above `remove_colinears`).
        // This is the EXACT UNATCO `iLink=1144` merge ring `TryToMerge` builds for the first of 3
        // adjacent CSG fragment pairs there: verts byte-confirmed live (gdb, `RC_ENTRY`/`RC_V0..5`,
        // `logs/removecolinears-entry-unatco.log`) against the real running editor, and Normal
        // hex-confirmed EXACT `(-0.0,-0.0,1.0)` (`NHEX=0x80000000,0x80000000,0x3f800000`, no hidden
        // epsilon). Ring index 0 is reflex (2D cross-product sign flips only there: -372.9 against
        // neighbours 3355..14695). x86 emulation of the real `RemoveColinears` bytes (unicorn, IAT
        // hooks for `operator^`/`NormalizeSlow`, this exact ring) returns `eax=0` (reject),
        // `NumVertices` UNCHANGED at 6 — matching the live `TTM AFTERRC rc_eax=0 ringcount=6`
        // observed twice fresh this session (`logs/trytomerge-live-unatco.log`) and the prior
        // session's independent capture. Before this fix, native's `remove_colinears` (a single
        // colinearity pass, no convexity check) wrongly ACCEPTED this ring, over-merging 4 real
        // editor fragments into 1 (`iLink=1144`: native `nv=10`×1 vs editor `nv=4`×4).
        let mut p = FPoly {
            normal: Vec3::new(-0.0, -0.0, 1.0),
            verts: vec![
                Vec3::new(-2425.910156, 1921.385254, 560.0),
                Vec3::new(-2431.999756, 1952.000000, 560.0),
                Vec3::new(-2591.999756, 1952.000000, 560.0),
                Vec3::new(-2573.731201, 1860.155884, 560.0),
                Vec3::new(-2521.705566, 1782.294312, 560.0),
                Vec3::new(-2408.568604, 1895.431396, 560.0),
            ],
            ..FPoly::new(vec![])
        };
        assert_eq!(
            p.remove_colinears(),
            0,
            "a ring with a reflex vertex must be rejected outright, matching the real editor"
        );
        assert!(p.verts.is_empty());
    }

    #[test]
    fn remove_colinears_still_merges_a_plain_convex_ring() {
        // The convexity gate must not become a blanket reject: a convex hexagon with two
        // colinear midpoints (as `TryToMerge` would build from two coplanar squares sharing an
        // edge) must still thin to the plain rectangle. CCW winding for `Normal=(0,0,1)` (right
        // along the bottom first, matching `square_xy`'s convention — an earlier CW draft of this
        // ring wrongly tripped the new gate on every vertex, since a CW ring makes the cached
        // `Side × Normal` point inward instead of outward).
        let mut p = FPoly {
            normal: Vec3::new(0.0, 0.0, 1.0),
            verts: vec![
                Vec3::new(0.0, 0.0, 0.0),
                Vec3::new(10.0, 0.0, 0.0),
                Vec3::new(20.0, 0.0, 0.0),
                Vec3::new(20.0, 10.0, 0.0),
                Vec3::new(10.0, 10.0, 0.0),
                Vec3::new(0.0, 10.0, 0.0),
            ],
            ..FPoly::new(vec![])
        };
        // The two colinear midpoints (10,0,0) and (10,10,0) must thin away, leaving the plain
        // 4-vert rectangle — a convex ring must survive the gate intact.
        assert_eq!(p.remove_colinears(), 4);
        assert_eq!(p.verts.len(), 4);
    }
}
