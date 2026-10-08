//! The T3D data model -- shared across uedcli's Rust verbs, not brush-specific.

use rust_decimal::Decimal;

/// A 3D vector or point, matching UnrealEngine's X,Y,Z convention.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vector3D {
    pub x: Decimal,
    pub y: Decimal,
    pub z: Decimal,
}

impl Vector3D {
    pub fn new(x: Decimal, y: Decimal, z: Decimal) -> Self {
        Vector3D { x, y, z }
    }
}

/// One face of a brush.
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
