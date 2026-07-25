//! `FPoly` — the working polygon of CSG (§10.2-3).  The N-1 port: `CalcNormal`, `Fix`,
//! `RemoveColinears`, `Finalize`, `Reverse`, `Transform`, and `SplitWithPlane` (classify +
//! cut) with the exact engine thresholds.  Beyond geometry, an `FPoly` carries the
//! **surf-link metadata** (`actor`/`texture`/`i_link`/`i_brush_poly`/`i_zone`) that flows
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
    pub i_zone: [u16; 2],
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
            i_zone: [0, 0],
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

    /// Drop colinear vertices (side-plane normals equal within THRESH_COLINEAR).  Thins to 0
    /// if it drops below 3 (the poly vanishes — a "silent-absence hole" source).
    pub fn remove_colinears(&mut self) -> usize {
        let n = self.verts.len();
        if n < 3 {
            self.verts.clear();
            return 0;
        }
        let mut keep = vec![true; n];
        for i in 0..n {
            let prev = self.verts[(i + n - 1) % n];
            let cur = self.verts[i];
            let next = self.verts[(i + 1) % n];
            let a = cur.sub(&prev);
            let b = next.sub(&cur);
            let cross = a.cross(&b);
            let denom = a.size() * b.size();
            if denom > SMALL_NUMBER && cross.size() / denom < THRESH_COLINEAR {
                keep[i] = false;
            }
        }
        let out: Vec<Vec3> = (0..n).filter(|&i| keep[i]).map(|i| self.verts[i]).collect();
        if out.len() < 3 {
            self.verts.clear();
            return 0;
        }
        self.verts = out;
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

        // straddles -> cut
        let n = self.verts.len();
        let mut front = self.empty_copy();
        let mut back = self.empty_copy();
        let side = |d: f32| -> i32 {
            if d > t {
                0
            } else if d < -t {
                1
            } else {
                2
            }
        };
        for i in 0..n {
            let prev = self.verts[(i + n - 1) % n];
            let cur = self.verts[i];
            let prev_d = dists[(i + n - 1) % n];
            let this_d = dists[i];
            let ps = side(prev_d);
            let cs = side(this_d);
            if (ps == 0 && cs == 1) || (ps == 1 && cs == 0) {
                let f = prev_d / (prev_d - this_d);
                let inter = Vec3::new(
                    prev.x + (cur.x - prev.x) * f,
                    prev.y + (cur.y - prev.y) * f,
                    prev.z + (cur.z - prev.z) * f,
                );
                front.verts.push(inter);
                back.verts.push(inter);
            }
            match cs {
                0 => front.verts.push(cur),
                1 => back.verts.push(cur),
                _ => {
                    front.verts.push(cur);
                    back.verts.push(cur);
                }
            }
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
            i_zone: self.i_zone,
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
}
