//! The T3D data model -- shared across uedcli's Rust verbs, not brush-specific.

use rust_decimal::Decimal;

/// A 3D vector or point, matching UnrealEngine's X,Y,Z convention.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vector3D {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Vector3D {
    pub fn new(x: f64, y: f64, z: f64) -> Self {
        Vector3D { x, y, z }
    }
}

/// One face of a brush, in raw geometry floats -- the ring may carry sub-grid float noise;
/// nothing here is Decimal-exact yet.
pub struct Polygon {
    pub vertices: Vec<Vector3D>,
    pub origin: Vector3D,
    /// Face normal -- advisory; the editor recomputes it from vertex winding on import.
    pub normal: Vector3D,
    /// In-plane texture-U basis vector (not a texture reference -- no per-face texture yet).
    pub texture_u: Vector3D,
    /// In-plane texture-V basis vector, perpendicular to `texture_u` within the face's plane.
    pub texture_v: Vector3D,
}

/// A `Polygon` with its vertices pre-cleaned to Decimal exactly once. See
/// `core::emit::format_vertex`'s doc for why the exact number of `clean()` applications (once
/// here, again at emit time) matters.
pub struct FinalizedPolygon {
    pub vertices: Vec<(Decimal, Decimal, Decimal)>,
    pub origin: Vector3D,
    pub normal: Vector3D,
    pub texture_u: Vector3D,
    pub texture_v: Vector3D,
}
