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
    use rstest::rstest;

    use super::*;

    fn v(x: i64, y: i64, z: i64) -> Vector3D {
        Vector3D::new(Decimal::from(x), Decimal::from(y), Decimal::from(z))
    }

    #[rstest]
    #[case::positive_components(v(1, 2, 3), v(4, 5, 6), Decimal::from(32))]
    #[case::orthogonal_is_zero(v(1, 0, 0), v(0, 1, 0), Decimal::ZERO)]
    #[case::negative_components(v(-1, 2, -3), v(4, -5, 6), Decimal::from(-4 - 10 - 18))]
    #[case::zero_vector_is_zero(v(0, 0, 0), v(9, -9, 9), Decimal::ZERO)]
    fn dot_cases(#[case] a: Vector3D, #[case] b: Vector3D, #[case] expected: Decimal) {
        assert_eq!(dot(a, b), expected);
    }

    #[rstest]
    #[case::x_cross_y_is_z(v(1, 0, 0), v(0, 1, 0), v(0, 0, 1))]
    #[case::parallel_vectors_are_zero(v(2, 4, 6), v(1, 2, 3), v(0, 0, 0))]
    fn cross_cases(#[case] a: Vector3D, #[case] b: Vector3D, #[case] expected: Vector3D) {
        assert_eq!(cross(a, b), expected);
    }

    #[test]
    fn cross_is_anticommutative() {
        let a = v(1, 2, 3);
        let b = v(4, -1, 2);
        let ab = cross(a, b);
        let ba = cross(b, a);
        assert_eq!(ab, multiply(ba, Decimal::from(-1)));
    }

    #[rstest]
    #[case::component_wise(v(5, 3, 1), v(2, 1, 1), v(3, 2, 0))]
    #[case::can_go_negative(v(1, 1, 1), v(5, 5, 5), v(-4, -4, -4))]
    fn subtract_cases(#[case] a: Vector3D, #[case] b: Vector3D, #[case] expected: Vector3D) {
        assert_eq!(subtract(a, b), expected);
    }

    #[rstest]
    #[case::positive(v(7, -3, 2))]
    #[case::zero(v(0, 0, 0))]
    fn subtract_from_self_is_zero(#[case] a: Vector3D) {
        assert_eq!(subtract(a, a), v(0, 0, 0));
    }

    #[rstest]
    #[case::positive_scalar(v(1, 2, 3), Decimal::from(2), v(2, 4, 6))]
    #[case::negative_scalar_flips_sign(v(1, 2, 3), Decimal::from(-2), v(-2, -4, -6))]
    #[case::zero_scalar_is_zero(v(1, 2, 3), Decimal::ZERO, v(0, 0, 0))]
    fn multiply_cases(#[case] a: Vector3D, #[case] scalar: Decimal, #[case] expected: Vector3D) {
        assert_eq!(multiply(a, scalar), expected);
    }

    #[rstest]
    #[case::three_four_five_triangle(v(3, 4, 0), Decimal::from(5))]
    #[case::unit_vector(v(0, 1, 0), Decimal::ONE)]
    #[case::ignores_sign(v(-3, -4, 0), Decimal::from(5))]
    #[case::zero_vector(v(0, 0, 0), Decimal::ZERO)]
    fn length_cases(#[case] a: Vector3D, #[case] expected: Decimal) {
        assert_eq!(length(a), expected);
    }

    #[rstest]
    #[case::three_four_zero(
        v(3, 4, 0),
        Vector3D::new(Decimal::from(3) / Decimal::from(5), Decimal::from(4) / Decimal::from(5), Decimal::ZERO)
    )]
    #[case::same_direction_scaled_up(
        v(6, 8, 0),
        Vector3D::new(Decimal::from(3) / Decimal::from(5), Decimal::from(4) / Decimal::from(5), Decimal::ZERO)
    )]
    #[case::already_unit(v(0, 0, 1), v(0, 0, 1))]
    fn normalize_vector_cases(#[case] a: Vector3D, #[case] expected: Vector3D) {
        assert_eq!(normalize_vector(a), expected);
    }

    #[rstest]
    #[case::square(vec![v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)], v(1, 1, 0))]
    #[case::single_point_is_itself(vec![v(5, -3, 2)], v(5, -3, 2))]
    // x sum = 2, y sum = 3 -- neither divides evenly by 3 in decimal; the expected value is
    // computed the same way (Decimal division) so this pins the function's actual behavior,
    // not a hand-rounded guess.
    #[case::triangle_divides_by_3_exactly_as_decimal_allows(
        vec![v(0, 0, 0), v(1, 0, 0), v(1, 3, 0)],
        Vector3D::new(Decimal::from(2) / Decimal::from(3), Decimal::ONE, Decimal::ZERO)
    )]
    fn compute_centroid_cases(#[case] ring: Vec<Vector3D>, #[case] expected: Vector3D) {
        assert_eq!(compute_centroid(&ring), expected);
    }

    #[rstest]
    // A square in the XY plane, wound CCW as seen from +Z -- Newell's method gives a normal
    // along +Z scaled by twice the ring's area (2 * 4 = 8), not a unit vector.
    #[case::square_in_xy_plane(vec![v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)], v(0, 0, 8))]
    // Same square, in the XZ plane instead -- confirms the method isn't accidentally hardcoded
    // to Z-axis-only math.
    #[case::square_in_xz_plane(vec![v(0, 0, 0), v(2, 0, 0), v(2, 0, 2), v(0, 0, 2)], v(0, -8, 0))]
    fn compute_newell_normal_cases(#[case] ring: Vec<Vector3D>, #[case] expected: Vector3D) {
        assert_eq!(compute_newell_normal(&ring), expected);
    }

    #[test]
    fn compute_newell_normal_flips_sign_when_winding_reverses() {
        let ring = [v(0, 0, 0), v(2, 0, 0), v(2, 2, 0), v(0, 2, 0)];
        let mut reversed = ring.to_vec();
        reversed.reverse();
        assert_eq!(compute_newell_normal(&reversed), v(0, 0, -8));
    }

    // Every axis-aligned normal (both directions): abs components always have at least a two-way
    // tie at 0 between the other two axes, and the lowest index always wins the seed.
    #[rstest]
    #[case::plus_x(v(1, 0, 0), v(0, 1, 0), v(0, 0, 1))]
    #[case::minus_x(v(-1, 0, 0), v(0, 1, 0), v(0, 0, -1))]
    #[case::plus_y(v(0, 1, 0), v(1, 0, 0), v(0, 0, -1))]
    #[case::minus_y(v(0, -1, 0), v(1, 0, 0), v(0, 0, 1))]
    #[case::plus_z(v(0, 0, 1), v(1, 0, 0), v(0, 1, 0))]
    #[case::minus_z(v(0, 0, -1), v(1, 0, 0), v(0, -1, 0))]
    fn compute_texture_basis_cases(
        #[case] normal: Vector3D,
        #[case] expected_u: Vector3D,
        #[case] expected_v: Vector3D,
    ) {
        let (u, v_basis) = compute_texture_basis(normal);
        assert_eq!(u, expected_u);
        assert_eq!(v_basis, expected_v);
    }
}
