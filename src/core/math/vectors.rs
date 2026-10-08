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

#[cfg(test)]
mod tests {
    use super::*;

    fn v(x: i64, y: i64, z: i64) -> Vector3D {
        Vector3D::new(Decimal::from(x), Decimal::from(y), Decimal::from(z))
    }

    #[test]
    fn dot_sums_component_products() {
        assert_eq!(dot(v(1, 2, 3), v(4, 5, 6)), Decimal::from(32));
    }

    #[test]
    fn dot_of_orthogonal_vectors_is_zero() {
        assert_eq!(dot(v(1, 0, 0), v(0, 1, 0)), Decimal::ZERO);
    }

    #[test]
    fn dot_with_negative_components() {
        assert_eq!(dot(v(-1, 2, -3), v(4, -5, 6)), Decimal::from(-4 - 10 - 18));
    }

    #[test]
    fn cross_of_x_and_y_axes_is_z() {
        assert_eq!(cross(v(1, 0, 0), v(0, 1, 0)), v(0, 0, 1));
    }

    #[test]
    fn cross_is_anticommutative() {
        let a = v(1, 2, 3);
        let b = v(4, -1, 2);
        let ab = cross(a, b);
        let ba = cross(b, a);
        assert_eq!(ab, multiply(ba, Decimal::from(-1)));
    }

    #[test]
    fn cross_of_parallel_vectors_is_zero() {
        assert_eq!(cross(v(2, 4, 6), v(1, 2, 3)), v(0, 0, 0));
    }

    #[test]
    fn subtract_is_component_wise() {
        assert_eq!(subtract(v(5, 3, 1), v(2, 1, 1)), v(3, 2, 0));
    }

    #[test]
    fn subtract_can_produce_negative_components() {
        assert_eq!(subtract(v(1, 1, 1), v(5, 5, 5)), v(-4, -4, -4));
    }

    #[test]
    fn subtract_from_self_is_zero() {
        let a = v(7, -3, 2);
        assert_eq!(subtract(a, a), v(0, 0, 0));
    }

    #[test]
    fn multiply_scales_every_component() {
        assert_eq!(multiply(v(1, 2, 3), Decimal::from(2)), v(2, 4, 6));
    }

    #[test]
    fn multiply_by_negative_scalar_flips_sign() {
        assert_eq!(multiply(v(1, 2, 3), Decimal::from(-2)), v(-2, -4, -6));
    }

    #[test]
    fn multiply_by_zero_is_zero() {
        assert_eq!(multiply(v(1, 2, 3), Decimal::ZERO), v(0, 0, 0));
    }

    #[test]
    fn length_of_a_3_4_0_triangle_is_5() {
        assert_eq!(length(v(3, 4, 0)), Decimal::from(5));
    }

    #[test]
    fn length_of_a_unit_vector_is_1() {
        assert_eq!(length(v(0, 1, 0)), Decimal::ONE);
    }

    #[test]
    fn length_ignores_sign_of_components() {
        assert_eq!(length(v(-3, -4, 0)), Decimal::from(5));
    }

    #[test]
    fn normalize_vector_scales_to_unit_length() {
        let expected = Vector3D::new(Decimal::from(3) / Decimal::from(5), Decimal::from(4) / Decimal::from(5), Decimal::ZERO);
        assert_eq!(normalize_vector(v(3, 4, 0)), expected);
    }

    #[test]
    fn normalize_vector_of_a_longer_vector_same_direction_matches() {
        let expected = Vector3D::new(Decimal::from(3) / Decimal::from(5), Decimal::from(4) / Decimal::from(5), Decimal::ZERO);
        assert_eq!(normalize_vector(v(6, 8, 0)), expected);
    }

    #[test]
    fn normalize_vector_of_an_already_unit_vector_is_unchanged() {
        assert_eq!(normalize_vector(v(0, 0, 1)), v(0, 0, 1));
    }

    #[test]
    fn compute_centroid_of_a_square() {
        let ring = [v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)];
        assert_eq!(compute_centroid(&ring), v(1, 1, 0));
    }

    #[test]
    fn compute_centroid_of_a_single_point_is_that_point() {
        let ring = [v(5, -3, 2)];
        assert_eq!(compute_centroid(&ring), v(5, -3, 2));
    }

    #[test]
    fn compute_centroid_of_a_triangle_divides_by_3_exactly_as_decimal_allows() {
        // x sum = 2, y sum = 3 -- neither divides evenly by 3 in decimal (2/3, 1 are the exact
        // answers for x and y respectively); the expected value is computed the same way
        // (Decimal division) so this pins the function's actual behavior, not a hand-rounded
        // guess.
        let ring = [v(0, 0, 0), v(1, 0, 0), v(1, 3, 0)];
        let expected = Vector3D::new(Decimal::from(2) / Decimal::from(3), Decimal::ONE, Decimal::ZERO);
        assert_eq!(compute_centroid(&ring), expected);
    }

    #[test]
    fn compute_newell_normal_of_a_square_points_along_its_axis() {
        // A square in the XY plane, wound CCW as seen from +Z -- Newell's method gives a normal
        // along +Z scaled by twice the ring's area (2 * 4 = 8), not a unit vector.
        let ring = [v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)];
        assert_eq!(compute_newell_normal(&ring), v(0, 0, 8));
    }

    #[test]
    fn compute_newell_normal_flips_sign_when_winding_reverses() {
        let ring = [v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)];
        let mut reversed = ring.to_vec();
        reversed.reverse();
        assert_eq!(compute_newell_normal(&reversed), v(0, 0, -8));
    }

    #[test]
    fn compute_newell_normal_generalizes_to_a_non_xy_plane() {
        // Same square, in the XZ plane instead -- confirms the method isn't accidentally
        // hardcoded to Z-axis-only math.
        let ring = [v(0, 0, 0), v(2, 0, 0), v(2, 0, 2), v(0, 0, 2)];
        assert_eq!(compute_newell_normal(&ring), v(0, -8, 0));
    }

    #[test]
    fn compute_texture_basis_for_x_normal_picks_lowest_tied_axis() {
        // normal=(1,0,0): components' absolute values are (1,0,0) -- Y and Z tie at 0, and the
        // lowest index (Y) wins the seed axis.
        let (u, v_basis) = compute_texture_basis(v(1, 0, 0));
        assert_eq!(u, v(0, 1, 0));
        assert_eq!(v_basis, v(0, 0, 1));
    }

    #[test]
    fn compute_texture_basis_for_y_normal_picks_lowest_tied_axis() {
        // normal=(0,1,0): abs values (0,1,0) -- X and Z tie at 0, and the lowest index (X) wins.
        let (u, v_basis) = compute_texture_basis(v(0, 1, 0));
        assert_eq!(u, v(1, 0, 0));
        assert_eq!(v_basis, v(0, 0, -1));
    }

    #[test]
    fn compute_texture_basis_for_z_normal_picks_lowest_tied_axis() {
        // normal=(0,0,1): abs values (0,0,1) -- X and Y tie at 0, and the lowest index (X) wins.
        let (u, v_basis) = compute_texture_basis(v(0, 0, 1));
        assert_eq!(u, v(1, 0, 0));
        assert_eq!(v_basis, v(0, 1, 0));
    }
}
