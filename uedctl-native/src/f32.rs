//! Float32/SSE-faithful arithmetic helpers.  The parity win over CPython's f64 is using
//! native `f32` end-to-end (§10.2-3); Rust's `f32` is IEEE-754 single with no implicit
//! FMA contraction, which is what the CSG classify/split thresholds require.  x87-vs-SSE
//! extended-precision parity with the 1999 build is a separate, unresolved risk (spec §8.1)
//! that native `f32` does NOT by itself settle — characterize early at N-1.

/// Distance of a point to a plane defined by (base, unit normal), in native f32.
#[inline]
pub fn point_plane_dist(
    px: f32,
    py: f32,
    pz: f32,
    bx: f32,
    by: f32,
    bz: f32,
    nx: f32,
    ny: f32,
    nz: f32,
) -> f32 {
    (px - bx) * nx + (py - by) * ny + (pz - bz) * nz
}
