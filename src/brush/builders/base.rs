//! Shared across every `brush build <shape>`: the generic polygon builder, and the CSG/solidity
//! choices every brush actor takes.

use crate::core::emit::{clean, decimal_from_f64};
use crate::core::math::vectors;
use crate::core::model::{FinalizedPolygon, Polygon, Vector3D};

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

pub fn finalize_polygon(polygon: &Polygon) -> Result<FinalizedPolygon, String> {
    let mut vertices = Vec::with_capacity(polygon.vertices.len());
    for vertex in &polygon.vertices {
        vertices.push((
            clean(decimal_from_f64(vertex.x)?)?,
            clean(decimal_from_f64(vertex.y)?)?,
            clean(decimal_from_f64(vertex.z)?)?,
        ));
    }
    Ok(FinalizedPolygon {
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
    let ring = if vectors::dot(newell_normal, outward_normalized) < 0.0 {
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
