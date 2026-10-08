//! Pure vector math shared across every geometry-producing verb -- mirrors the module-level
//! helpers in old/uedcli/builders.py. Named `vectors` (not just left at `math`'s own top level)
//! so a generic-sounding name like `subtract`/`multiply` is unambiguous at every call site
//! (`vectors::subtract(...)`) and can't collide with a future non-vector `math::subtract`.

use crate::core::model::Vector3D;

pub fn dot(a: Vector3D, b: Vector3D) -> f64 {
    a.x * b.x + a.y * b.y + a.z * b.z
}

pub fn cross(a: Vector3D, b: Vector3D) -> Vector3D {
    Vector3D::new(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
}

pub fn subtract(a: Vector3D, b: Vector3D) -> Vector3D {
    Vector3D::new(a.x - b.x, a.y - b.y, a.z - b.z)
}

pub fn multiply(a: Vector3D, scalar: f64) -> Vector3D {
    Vector3D::new(a.x * scalar, a.y * scalar, a.z * scalar)
}

pub fn length(a: Vector3D) -> f64 {
    dot(a, a).sqrt()
}

pub fn normalize_vector(a: Vector3D) -> Vector3D {
    // builders.py's _normalize raises GeometryError on a zero-length input -- never reachable for
    // cube's fixed axis-aligned outward vectors (always unit length already), so not replicated.
    let n = length(a);
    Vector3D::new(a.x / n, a.y / n, a.z / n)
}

pub fn compute_centroid(ring: &[Vector3D]) -> Vector3D {
    let n = ring.len() as f64;
    let sx: f64 = ring.iter().map(|p| p.x).sum();
    let sy: f64 = ring.iter().map(|p| p.y).sum();
    let sz: f64 = ring.iter().map(|p| p.z).sum();
    Vector3D::new(sx / n, sy / n, sz / n)
}

/// Newell's method: a robust face normal from the vertex winding (the same quantity UnrealEd
/// derives the face from). Points CCW-from-the-named-side.
pub fn compute_newell_normal(ring: &[Vector3D]) -> Vector3D {
    let mut n = Vector3D::new(0.0, 0.0, 0.0);
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
/// LOWEST axis index -- Rust's `min_by`, like Python's `min()`, returns the first minimal element
/// on a tie (builders.py's `_tex_basis` docstring: this is load-bearing -- every axis-aligned
/// face every builder emits depends on it).
pub fn compute_texture_basis(normal: Vector3D) -> (Vector3D, Vector3D) {
    let components = [normal.x, normal.y, normal.z];
    let axis = (0..3)
        .min_by(|&i, &j| components[i].abs().partial_cmp(&components[j].abs()).unwrap())
        .unwrap();
    let mut seed = [0.0, 0.0, 0.0];
    seed[axis] = 1.0;
    let seed = Vector3D::new(seed[0], seed[1], seed[2]);
    let u = normalize_vector(subtract(seed, multiply(normal, dot(seed, normal))));
    let v = cross(normal, u);
    (u, v)
}
