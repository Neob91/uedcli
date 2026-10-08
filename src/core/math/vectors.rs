//! Pure vector math shared across every geometry-producing verb. Named `vectors` (not left at
//! `math`'s own top level) so a generic name like `subtract`/`multiply` stays unambiguous at the
//! call site (`vectors::subtract(...)`) and can't collide with a future non-vector `math::subtract`.

use rust_decimal::prelude::MathematicalOps;
use rust_decimal::Decimal;

use crate::core::model::Vector3D;

pub fn dot(a: Vector3D, b: Vector3D) -> Decimal {
    a.x * b.x + a.y * b.y + a.z * b.z
}

pub fn cross(a: Vector3D, b: Vector3D) -> Vector3D {
    Vector3D::new(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
}

pub fn subtract(a: Vector3D, b: Vector3D) -> Vector3D {
    Vector3D::new(a.x - b.x, a.y - b.y, a.z - b.z)
}

pub fn multiply(a: Vector3D, scalar: Decimal) -> Vector3D {
    Vector3D::new(a.x * scalar, a.y * scalar, a.z * scalar)
}

pub fn length(a: Vector3D) -> Decimal {
    // dot(a, a) is a sum of squares, always >= 0 -- sqrt() only returns None for a negative
    // input, which can't happen here.
    dot(a, a).sqrt().expect("dot(a, a) is never negative")
}

pub fn normalize_vector(a: Vector3D) -> Vector3D {
    // Zero-length input is unreachable from cube's fixed axis-aligned outward vectors (always
    // unit length already); not guarded here.
    let n = length(a);
    Vector3D::new(a.x / n, a.y / n, a.z / n)
}

pub fn compute_centroid(ring: &[Vector3D]) -> Vector3D {
    let n = Decimal::from(ring.len());
    let sx: Decimal = ring.iter().map(|p| p.x).sum();
    let sy: Decimal = ring.iter().map(|p| p.y).sum();
    let sz: Decimal = ring.iter().map(|p| p.z).sum();
    Vector3D::new(sx / n, sy / n, sz / n)
}

/// Newell's method: a robust face normal from the vertex winding (the same quantity UnrealEd
/// derives the face from). Points CCW-from-the-named-side.
pub fn compute_newell_normal(ring: &[Vector3D]) -> Vector3D {
    let mut n = Vector3D::new(Decimal::ZERO, Decimal::ZERO, Decimal::ZERO);
    let m = ring.len();
    for i in 0..m {
        let a = ring[i];
        let b = ring[(i + 1) % m];
        n.x += (a.y - b.y) * (a.z + b.z);
        n.y += (a.z - b.z) * (a.x + b.x);
        n.z += (a.x - b.x) * (a.y + b.y);
    }
    n
}

/// Unit in-plane (TextureU, TextureV) basis for a face, given its normal. Ties resolve to the
/// lowest axis index -- `min_by` returns the first minimal element on a tie, and every
/// axis-aligned face depends on that exact tiebreak.
pub fn compute_texture_basis(normal: Vector3D) -> (Vector3D, Vector3D) {
    let components = [normal.x, normal.y, normal.z];
    let axis = (0..3).min_by_key(|&i| components[i].abs()).unwrap();
    let mut seed = [Decimal::ZERO, Decimal::ZERO, Decimal::ZERO];
    seed[axis] = Decimal::ONE;
    let seed = Vector3D::new(seed[0], seed[1], seed[2]);
    let u = normalize_vector(subtract(seed, multiply(normal, dot(seed, normal))));
    let v = cross(normal, u);
    (u, v)
}
