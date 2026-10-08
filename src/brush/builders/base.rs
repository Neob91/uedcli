//! Shared across every `brush build <shape>`: the generic polygon builder, and the CSG/solidity
//! choices every brush actor takes.

use rust_decimal::Decimal;

use crate::core::emit::clean;
use crate::core::math::vectors;
use crate::core::model::{Polygon, Vector3D};

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum CsgOperation {
    Add,
    Subtract,
}

impl CsgOperation {
    pub fn as_t3d(self) -> &'static str {
        match self {
            CsgOperation::Add => "CSG_Add",
            CsgOperation::Subtract => "CSG_Subtract",
        }
    }
}

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum Solidity {
    Solid,
    Semisolid,
    Nonsolid,
}

impl Solidity {
    pub fn poly_flags(self) -> u32 {
        match self {
            Solidity::Solid => 0,
            Solidity::Semisolid => 0x0000_0020,
            Solidity::Nonsolid => 0x0000_0008,
        }
    }
}

/// Pre-cleans a `Polygon`'s vertices exactly once -- not its Origin/Normal/TextureU/TextureV,
/// which get their one and only clean() at emit time. See `core::emit::format_vertex`'s doc for
/// why that distinction matters.
pub fn clean_polygon(polygon: &Polygon) -> Result<Polygon, String> {
    let mut vertices = Vec::with_capacity(polygon.vertices.len());
    for vertex in &polygon.vertices {
        vertices.push(Vector3D::new(clean(vertex.x)?, clean(vertex.y)?, clean(vertex.z)?));
    }
    Ok(Polygon {
        vertices,
        origin: polygon.origin,
        normal: polygon.normal,
        texture_u: polygon.texture_u,
        texture_v: polygon.texture_v,
    })
}

/// Builds a `Polygon` from a boundary vertex ring and a rough outward direction.
pub fn build_polygon(ring: Vec<Vector3D>, outward: Vector3D) -> Polygon {
    let newell_normal = vectors::compute_newell_normal(&ring);
    let outward_normalized = vectors::normalize_vector(outward);
    // cube's 6 hand-authored rings already wind to match their declared `outward`, so this branch
    // never triggers for cube -- untested by this shape. The next shape with only an approximate
    // outward vector (a cylinder/cone side quad) is this code's first real exercise.
    let ring = if vectors::dot(newell_normal, outward_normalized) < Decimal::ZERO {
        let mut reversed = ring;
        reversed.reverse();
        reversed
    } else {
        ring
    };
    let (texture_u, texture_v) = vectors::compute_texture_basis(outward_normalized);
    Polygon {
        origin: vectors::compute_centroid(&ring),
        normal: outward_normalized,
        texture_u,
        texture_v,
        vertices: ring,
    }
}
