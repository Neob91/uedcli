//! The `--native` preview software rasterizer (spec §5, 2026-07-16-native-preview-design).
//! Deliberately boring: perspective projection from a caller-supplied CAMERA BASIS
//! (Python computes forward/right/up via the GMath-verified `rotation.euler_to_matrix_uu`
//! and passes it across the FFI — Rust NEVER converts FRotator angles, so the camera
//! convention is single-sourced; plan refinement 3), near-plane polygon clip, z-buffer,
//! perspective-correct nearest-sampled UV (mip0, wrap), and a per-face brightness factor
//! so adjacent same-texture faces read as distinct 3-D shapes.
//!
//! Input is FLAT world-space textured polygons (plan refinement 2) — this module is fully
//! independent of the Model format and the CSG/build modules: Python does all joins and
//! computes each polygon's world UV frame (base/axes/pan, texel units); Rust only
//! rasterizes. `cargo test`-able with no Python.

use crate::light::light_in_front;
use crate::model::Vec3;

/// One world-space textured polygon: vertex ring + UV frame (texel units) + texture slot.
/// `tex_index < 0` (or out of range) renders in the flat default grey — the "no texture
/// set" face; unresolvable refs get a checkerboard TEXTURE Python-side, never a sentinel.
pub struct RenderPoly {
    pub verts: Vec<Vec3>,
    pub uv_base: Vec3,   // world point where (u,v) = (pan_u, pan_v)
    pub uv_axis_u: Vec3, // world axis: u texels per uu
    pub uv_axis_v: Vec3,
    pub pan: [f32; 2],
    pub tex_index: i32,
    pub masked: bool, // PF_Masked: skip texels whose mask byte is 0 (palette-index-0 transparent)
    /// The merged actor+poly `PolyFlags` (Python single-sources it from `BspSurf.poly_flags` for a
    /// CSG-solved surface, or `poly.flags | actor PolyFlags` for a mover). Consulted only by the
    /// backface cull (`light_in_front`'s `PF_TwoSided|PF_Portal` exemption) — no other bit here
    /// currently changes rendering.
    pub poly_flags: u32,
}

/// A decoded texture: mip0 RGB, row-major, `data.len() == w*h*3`. `mask` is the per-texel
/// alpha-test mask, `mask.len() == w*h`, `1 = opaque`, `0 = transparent` (only consulted for
/// PF_Masked faces). The placeholder checkerboard carries an all-opaque mask.
pub struct RenderTexture {
    pub w: u32,
    pub h: u32,
    pub data: Vec<u8>,
    pub mask: Vec<u8>,
}

/// Camera basis (world space). `forward`/`right`/`up` are the rotation matrix columns the
/// Python side derives from the SHOT pose (unit, orthogonal); `fov_deg` is the HORIZONTAL
/// field of view.
pub struct Camera {
    pub location: Vec3,
    pub forward: Vec3,
    pub right: Vec3,
    pub up: Vec3,
    pub fov_deg: f32,
}

/// Pixels no polygon covers: a flat dark grey, visibly distinct from black (black reads
/// as "render broke" — the historical black-viewport trap; spec §5).
pub const BACKGROUND: [u8; 3] = [56, 56, 60];
/// The flat default grey an untextured face renders in.
pub const DEFAULT_GREY: [u8; 3] = [128, 128, 128];
/// Near-plane distance (uu): geometry behind/straddling the camera is clipped, not wrapped.
pub const NEAR: f32 = 4.0;

/// Fixed world "key light" direction for the per-face brightness factor (v1 flat shading).
/// The factor is `0.55 + 0.45·|N·L|` — the `|·|` is NOT a winding-robustness hedge (a wrong-wound
/// single-sided face's shade is computed but never shown — the facing cull right below drops the
/// whole poly before rasterizing any of it): a genuinely `PF_TwoSided`/`PF_Portal` face IS actually
/// drawn from either side and must read identically lit from both, same reasoning as
/// `light::light_in_front`'s own two-sided exemption for the light-bake pass.
const KEY_LIGHT: Vec3 = Vec3 {
    x: -0.408,
    y: -0.577,
    z: 0.707,
};

/// One camera-space vertex ready for projection: position in the camera frame
/// (x = depth along forward, y = along right, z = along up) + UNPANNED-frame-applied
/// texel UV (pan already added).
#[derive(Clone, Copy)]
struct CamVert {
    d: f32, // depth (along forward)
    r: f32, // along right
    u: f32, // along up
    tu: f32,
    tv: f32,
}

fn newell_normal(verts: &[Vec3]) -> Vec3 {
    let mut n = Vec3::new(0.0, 0.0, 0.0);
    for i in 0..verts.len() {
        let a = &verts[i];
        let b = &verts[(i + 1) % verts.len()];
        n.x += (a.y - b.y) * (a.z + b.z);
        n.y += (a.z - b.z) * (a.x + b.x);
        n.z += (a.x - b.x) * (a.y + b.y);
    }
    n
}

/// Clip a camera-space polygon against the near plane `d >= NEAR` (Sutherland-Hodgman).
/// UVs interpolate linearly — exact, since UV is an affine function of world position.
fn clip_near(poly: &[CamVert]) -> Vec<CamVert> {
    let mut out: Vec<CamVert> = Vec::with_capacity(poly.len() + 2);
    for i in 0..poly.len() {
        let a = poly[i];
        let b = poly[(i + 1) % poly.len()];
        let a_in = a.d >= NEAR;
        let b_in = b.d >= NEAR;
        if a_in {
            out.push(a);
        }
        if a_in != b_in {
            let t = (NEAR - a.d) / (b.d - a.d);
            out.push(CamVert {
                d: NEAR,
                r: a.r + t * (b.r - a.r),
                u: a.u + t * (b.u - a.u),
                tu: a.tu + t * (b.tu - a.tu),
                tv: a.tv + t * (b.tv - a.tv),
            });
        }
    }
    out
}

#[inline]
fn wrap(i: i64, n: u32) -> u32 {
    (i.rem_euclid(n as i64)) as u32
}

/// Render `polys` into a `width × height` RGB framebuffer. Pure function of its inputs
/// (no threading in v1 — spec §5 determinism).
pub fn render(
    polys: &[RenderPoly],
    textures: &[RenderTexture],
    camera: &Camera,
    width: u32,
    height: u32,
) -> Vec<u8> {
    let (w, h) = (width as usize, height as usize);
    let mut img = vec![0u8; w * h * 3];
    for px in img.chunks_exact_mut(3) {
        px.copy_from_slice(&BACKGROUND);
    }
    let mut zbuf = vec![0.0f32; w * h]; // stores 1/depth; larger = closer; 0 = background

    let half_w = width as f32 / 2.0;
    let half_h = height as f32 / 2.0;
    // Horizontal FOV -> focal length in pixels (same focal for y: square pixels).
    let focal = half_w / (camera.fov_deg.to_radians() / 2.0).tan();

    for poly in polys {
        if poly.verts.len() < 3 {
            continue;
        }
        // Per-face brightness from the world-space face normal vs the fixed key light.
        let n = newell_normal(&poly.verts);
        let n_len = n.size();
        let shade = if n_len > 1e-12 {
            0.55 + 0.45 * (n.dot(&KEY_LIGHT).abs() / n_len)
        } else {
            continue; // degenerate (zero-area) polygon
        };

        // Single-sided by default (real UnrealEd: `dev/docs/unrealed/leveldesign/kb/textures.md`
        // "2-Sided renders both faces"). Reuses the editor's own disassembled facing test
        // (`light::light_in_front`, from `URender::OccludeBsp`) with the camera standing in for
        // the light: `PF_TwoSided`/`PF_Portal` faces are never culled, everything else needs
        // `PlaneDot >= -1.0`.
        let unit_n = Vec3::new(n.x / n_len, n.y / n_len, n.z / n_len);
        if !light_in_front(&unit_n, &poly.verts[0], &camera.location, poly.poly_flags) {
            continue;
        }

        // World -> camera frame + world-frame texel UV per vertex.
        let cam: Vec<CamVert> = poly
            .verts
            .iter()
            .map(|p| {
                let rel = p.sub(&camera.location);
                let dp = p.sub(&poly.uv_base);
                CamVert {
                    d: rel.dot(&camera.forward),
                    r: rel.dot(&camera.right),
                    u: rel.dot(&camera.up),
                    tu: dp.dot(&poly.uv_axis_u) + poly.pan[0],
                    tv: dp.dot(&poly.uv_axis_v) + poly.pan[1],
                }
            })
            .collect();
        let clipped = clip_near(&cam);
        if clipped.len() < 3 {
            continue;
        }

        // Project to screen: x right, y DOWN (row-major framebuffer).
        // Screen vertex carries (sx, sy, 1/d, u/d, v/d) for perspective-correct interp.
        let scr: Vec<[f32; 5]> = clipped
            .iter()
            .map(|v| {
                let inv = 1.0 / v.d;
                [
                    half_w + v.r * focal * inv,
                    half_h - v.u * focal * inv,
                    inv,
                    v.tu * inv,
                    v.tv * inv,
                ]
            })
            .collect();

        let tex = if poly.tex_index >= 0 {
            textures.get(poly.tex_index as usize)
        } else {
            None
        };

        for k in 1..scr.len() - 1 {
            raster_tri(
                &mut img,
                &mut zbuf,
                w,
                h,
                &scr[0],
                &scr[k],
                &scr[k + 1],
                tex,
                poly.masked,
                shade,
            );
        }
    }
    img
}

#[allow(clippy::too_many_arguments)]
fn raster_tri(
    img: &mut [u8],
    zbuf: &mut [f32],
    w: usize,
    h: usize,
    a: &[f32; 5],
    b: &[f32; 5],
    c: &[f32; 5],
    tex: Option<&RenderTexture>,
    masked: bool,
    shade: f32,
) {
    let min_x = a[0].min(b[0]).min(c[0]).floor().max(0.0) as usize;
    let max_x = (a[0].max(b[0]).max(c[0]).ceil() as i64).min(w as i64 - 1);
    let min_y = a[1].min(b[1]).min(c[1]).floor().max(0.0) as usize;
    let max_y = (a[1].max(b[1]).max(c[1]).ceil() as i64).min(h as i64 - 1);
    if max_x < min_x as i64 || max_y < min_y as i64 {
        return;
    }
    let (max_x, max_y) = (max_x as usize, max_y as usize);

    let den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
    if den.abs() < 1e-12 {
        return;
    }
    let inv_den = 1.0 / den;

    for y in min_y..=max_y {
        // Sample at the pixel centre.
        let py = y as f32 + 0.5;
        for x in min_x..=max_x {
            let px = x as f32 + 0.5;
            let w0 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) * inv_den;
            let w1 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) * inv_den;
            let w2 = 1.0 - w0 - w1;
            if w0 < 0.0 || w1 < 0.0 || w2 < 0.0 {
                continue;
            }
            let inv_d = w0 * a[2] + w1 * b[2] + w2 * c[2];
            let pi = y * w + x;
            if inv_d <= zbuf[pi] {
                continue; // an earlier polygon is closer (or equal) here
            }
            let (mut rr, mut gg, mut bb) = (
                DEFAULT_GREY[0] as f32,
                DEFAULT_GREY[1] as f32,
                DEFAULT_GREY[2] as f32,
            );
            if let Some(t) = tex {
                let u = (w0 * a[3] + w1 * b[3] + w2 * c[3]) / inv_d;
                let v = (w0 * a[4] + w1 * b[4] + w2 * c[4]) / inv_d;
                let tx = wrap(u.floor() as i64, t.w);
                let ty = wrap(v.floor() as i64, t.h);
                let texel = (ty * t.w + tx) as usize;
                // PF_Masked alpha test: a transparent texel (mask byte 0) is skipped WHOLE —
                // no colour, no z-write — so farther geometry / background shows through. The
                // mask index equals the colour texel, so the same UV/mip is sampled. `get`
                // bounds-checks defensively (mask.len() == w*h is enforced at the FFI edge).
                if masked && t.mask.get(texel).copied().unwrap_or(1) == 0 {
                    continue;
                }
                let ti = texel * 3;
                rr = t.data[ti] as f32;
                gg = t.data[ti + 1] as f32;
                bb = t.data[ti + 2] as f32;
            }
            zbuf[pi] = inv_d;
            let o = pi * 3;
            img[o] = (rr * shade).min(255.0) as u8;
            img[o + 1] = (gg * shade).min(255.0) as u8;
            img[o + 2] = (bb * shade).min(255.0) as u8;
        }
    }
}

// ---------------------------------------------------------------------------- tests

#[cfg(test)]
mod tests {
    use super::*;

    // PolyFlags used by these tests — not re-exported from `light`, so kept as plain hex
    // (canonical values: `light::light_in_front`'s doc comment, `dev/docs/unrealed/leveldesign/
    // kb/textures.md`).
    const PF_TWO_SIDED: u32 = 0x0000_0100;
    const PF_PORTAL: u32 = 0x0400_0000;

    fn cam_at_origin_looking_plus_x(fov: f32) -> Camera {
        Camera {
            location: Vec3::new(0.0, 0.0, 0.0),
            forward: Vec3::new(1.0, 0.0, 0.0),
            right: Vec3::new(0.0, 1.0, 0.0),
            up: Vec3::new(0.0, 0.0, 1.0),
            fov_deg: fov,
        }
    }

    /// A `size`-uu square wall at x=depth, centred on the view axis, UV = 1 texel/uu, wound to
    /// face BACK toward the origin (normal -X) — i.e. front-facing to `cam_at_origin_looking_plus_x`,
    /// which every caller here relies on now that a single-sided back face is culled.
    fn wall(depth: f32, size: f32, tex_index: i32) -> RenderPoly {
        let s = size / 2.0;
        RenderPoly {
            verts: vec![
                Vec3::new(depth, -s, s),
                Vec3::new(depth, s, s),
                Vec3::new(depth, s, -s),
                Vec3::new(depth, -s, -s),
            ],
            uv_base: Vec3::new(depth, -s, s), // top-left in screen terms
            uv_axis_u: Vec3::new(0.0, 1.0, 0.0),
            uv_axis_v: Vec3::new(0.0, 0.0, -1.0),
            pan: [0.0, 0.0],
            tex_index,
            masked: false,
            poly_flags: 0,
        }
    }

    #[test]
    fn projection_round_trip() {
        // 90° hfov, 200x100: focal = 100 px. A point 10 right / 5 up at depth 100
        // lands 10 px right of centre, 5 px above centre.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[wall(100.0, 400.0, -1)], &[], &cam, 200, 100);
        assert_eq!(img.len(), 200 * 100 * 3);
        // Wall covers the whole frame (±200 uu at depth 100 = ±63° > ±45° fov): no background.
        assert!(img.chunks_exact(3).all(|p| p != BACKGROUND));

        // Point projection math (the same formula render uses), checked exactly.
        let focal = 100.0_f32;
        let (d, r, u) = (100.0_f32, 10.0_f32, 5.0_f32);
        let sx = 100.0 + r * focal / d;
        let sy = 50.0 - u * focal / d;
        assert_eq!((sx, sy), (110.0, 45.0));
    }

    #[test]
    fn uv_texel_probe() {
        // 2x2 texture: TL red, TR green, BL blue, BR white; wall spans exactly 2x2 texels
        // (1 uu = 1 texel, 2 uu wall). At 90° fov / depth = focal the wall pixel-maps.
        let tex = RenderTexture {
            w: 2,
            h: 2,
            data: vec![255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255],
            mask: vec![1, 1, 1, 1],
        };
        // Wall 2uu at depth 32, focal 32 (90° fov, 64px wide) -> covers 2 px around centre.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[wall(32.0, 2.0, 0)], &[tex], &cam, 64, 64);
        let px = |x: usize, y: usize| {
            let o = (y * 64 + x) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        // shade for a +X-normal wall: 0.55 + 0.45*|(-0.408)| ≈ 0.7336 -> red 255*0.7336 ≈ 187
        let s = 0.55 + 0.45 * 0.408;
        let scale = |c: u8| (c as f32 * s) as u8;
        assert_eq!(px(31, 31), [scale(255), 0, 0]); // top-left texel = red
        assert_eq!(px(32, 31), [0, scale(255), 0]); // top-right = green
        assert_eq!(px(31, 32), [0, 0, scale(255)]); // bottom-left = blue
        let w = px(32, 32);
        assert_eq!(w, [scale(255), scale(255), scale(255)]); // bottom-right = white
    }

    #[test]
    fn near_plane_clips_geometry_behind_camera() {
        // A wall BEHIND the camera must not wrap into view. `wall()` at a NEGATIVE depth keeps
        // its own front (-X) facing further into -X, i.e. AWAY from a camera at the origin — so
        // it would already be dropped by the backface cull before ever reaching `clip_near`.
        // `PF_TwoSided` bypasses that cull, so this test still exercises the near-plane clip it's
        // named for, not the (separately, directly tested) facing cull.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut behind = wall(-100.0, 400.0, -1);
        behind.poly_flags = PF_TWO_SIDED;
        let img = render(&[behind], &[], &cam, 32, 32);
        assert!(img.chunks_exact(3).all(|p| p == BACKGROUND));
        // A wall straddling the camera plane clips cleanly (no panic, partial coverage).
        let mut straddle = wall(1.0, 400.0, -1);
        straddle.verts = vec![
            Vec3::new(-50.0, -200.0, -10.0),
            Vec3::new(50.0, -200.0, -10.0),
            Vec3::new(50.0, 200.0, -10.0),
            Vec3::new(-50.0, 200.0, -10.0),
        ];
        let img = render(&[straddle], &[], &cam, 32, 32);
        assert!(img.chunks_exact(3).any(|p| p != BACKGROUND));
    }

    #[test]
    fn zbuffer_near_face_wins() {
        let near = wall(50.0, 20.0, -1); // grey wall, small, near
        let far = {
            let mut f = wall(100.0, 400.0, 0); // red-textured wall, far, full-frame
            f.tex_index = 0;
            f
        };
        let tex = RenderTexture {
            w: 1,
            h: 1,
            data: vec![255, 0, 0],
            mask: vec![1],
        };
        let img = render(
            &[far, near],
            &[tex],
            &cam_at_origin_looking_plus_x(90.0),
            64,
            64,
        );
        let centre = {
            let o = (32 * 64 + 32) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        // Centre shows the NEAR grey wall (shaded default grey has r == g == b).
        assert_eq!(centre[0], centre[1]);
        assert_eq!(centre[1], centre[2]);
        // A corner outside the near wall's footprint shows the far red wall (g == b == 0).
        let corner = {
            let o = (2 * 64 + 2) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        assert!(corner[0] > 0 && corner[1] == 0 && corner[2] == 0);
    }

    #[test]
    fn pan_offsets_the_sample() {
        // 2x1 texture (left red, right green); a 2-uu wall = 2 texels. Unpanned, the left
        // pixel samples texel 0 (red); with pan U=1 the same pixel samples texel 1 (green)
        // and the right pixel wraps back to texel 0 (red).
        let tex = RenderTexture {
            w: 2,
            h: 1,
            data: vec![255, 0, 0, 0, 255, 0],
            mask: vec![1, 1],
        };
        let cam = cam_at_origin_looking_plus_x(90.0);
        let plain = render(
            &[wall(32.0, 2.0, 0)],
            &[RenderTexture {
                w: 2,
                h: 1,
                data: tex.data.clone(),
                mask: vec![1, 1],
            }],
            &cam,
            64,
            64,
        );
        let px = |img: &[u8], x: usize| {
            let o = (32 * 64 + x) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        assert!(px(&plain, 31)[0] > 0 && px(&plain, 31)[1] == 0); // unpanned left = red
        let mut p = wall(32.0, 2.0, 0);
        p.pan = [1.0, 0.0];
        let panned = render(&[p], &[tex], &cam, 64, 64);
        assert!(px(&panned, 31)[1] > 0 && px(&panned, 31)[0] == 0); // panned left = green
        assert!(px(&panned, 32)[0] > 0 && px(&panned, 32)[1] == 0); // wraps back to red
    }

    #[test]
    fn masked_face_skips_transparent_texels() {
        // 2x1 texture, both texels red; left texel opaque (mask 1), right transparent (mask 0).
        // A masked wall in FRONT of a full-frame grey wall: the left half shows red, the right
        // half shows the grey wall BEHIND (the transparent texel wrote neither colour nor z).
        let tex = RenderTexture {
            w: 2,
            h: 1,
            data: vec![255, 0, 0, 255, 0, 0],
            mask: vec![1, 0],
        };
        let back = wall(80.0, 400.0, -1); // grey, far, full-frame
        let mut front = wall(32.0, 2.0, 0); // 2-uu masked wall, near, 2 texels
        front.masked = true;
        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[back, front], &[tex], &cam, 64, 64);
        let px = |x: usize| {
            let o = (32 * 64 + x) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        // Left texel (opaque): red front wall. g == b == 0, r > 0.
        assert!(px(31)[0] > 0 && px(31)[1] == 0 && px(31)[2] == 0);
        // Right texel (transparent, skipped): grey back wall shows through (r == g == b > 0).
        let right = px(32);
        assert!(right[0] > 0 && right[0] == right[1] && right[1] == right[2]);

        // Same wall WITHOUT the flag: the transparent texel renders opaque red (fast path).
        let mut opaque = wall(32.0, 2.0, 0);
        opaque.masked = false;
        let tex2 = RenderTexture {
            w: 2,
            h: 1,
            data: vec![255, 0, 0, 255, 0, 0],
            mask: vec![1, 0],
        };
        let back2 = wall(80.0, 400.0, -1);
        let img = render(&[back2, opaque], &[tex2], &cam, 64, 64);
        let o = (32 * 64 + 32) * 3;
        assert!(img[o] > 0 && img[o + 1] == 0 && img[o + 2] == 0); // red, not grey
    }

    #[test]
    fn masked_transparent_texel_leaves_z_unwritten() {
        // Discriminates the z-write relocation: the masked wall is drawn FIRST and a FARTHER wall
        // second. At a transparent texel the masked face must write neither colour NOR z, so the
        // later farther wall passes the z-test and shows through. (With a z-write-before-skip bug
        // the masked face's depth would occlude the farther wall and the pixel would stay
        // BACKGROUND.) The reversed draw order is what makes this case sensitive to the relocation.
        let tex = RenderTexture {
            w: 2,
            h: 1,
            data: vec![255, 0, 0, 255, 0, 0],
            mask: vec![1, 0], // left opaque, right transparent
        };
        let mut front = wall(32.0, 2.0, 0); // near masked wall, 2 texels
        front.masked = true;
        let back = wall(80.0, 400.0, -1); // farther grey full-frame wall
        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[front, back], &[tex], &cam, 64, 64); // masked drawn FIRST
        let px = |x: usize| {
            let o = (32 * 64 + x) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        // Left texel (opaque): the near red wall.
        assert!(px(31)[0] > 0 && px(31)[1] == 0 && px(31)[2] == 0);
        // Right texel (transparent): the FARTHER wall shows (shaded grey, r == g == b), NOT the
        // background — the masked face left z unwritten so the later wall won the depth test.
        let right = px(32);
        assert_ne!(right, BACKGROUND);
        assert!(right[0] > 0 && right[0] == right[1] && right[1] == right[2]);
    }

    /// A wall wound to face AWAY from `cam_at_origin_looking_plus_x` (the reverse of `wall()`).
    fn wall_facing_away(depth: f32, size: f32, tex_index: i32) -> RenderPoly {
        let mut w = wall(depth, size, tex_index);
        w.verts.reverse();
        w
    }

    #[test]
    fn single_sided_back_face_is_culled() {
        // A wall facing away from the camera renders nothing: pure background, not even the
        // flat default grey (spec: real UnrealEd is single-sided by default).
        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[wall_facing_away(100.0, 400.0, -1)], &[], &cam, 64, 64);
        assert!(img.chunks_exact(3).all(|p| p == BACKGROUND));
        // The same wall facing the camera (unchanged from `wall()`) DOES render.
        let img = render(&[wall(100.0, 400.0, -1)], &[], &cam, 64, 64);
        assert!(img.chunks_exact(3).all(|p| p != BACKGROUND));
    }

    #[test]
    fn two_sided_flag_exempts_a_back_face_from_the_cull() {
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut w = wall_facing_away(100.0, 400.0, -1);
        w.poly_flags = PF_TWO_SIDED;
        let img = render(&[w], &[], &cam, 64, 64);
        assert!(img.chunks_exact(3).all(|p| p != BACKGROUND));
    }

    #[test]
    fn portal_flag_exempts_a_back_face_from_the_cull() {
        // Same exemption, the OTHER real mask bit (`light_in_front`'s test is `PF_TwoSided |
        // PF_Portal`, not `PF_TwoSided` alone — a visible two-sided portal sheet, `PF_Portal` set
        // and NOT `PF_TwoSided`, still renders).
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut w = wall_facing_away(100.0, 400.0, -1);
        w.poly_flags = PF_PORTAL;
        let img = render(&[w], &[], &cam, 64, 64);
        assert!(img.chunks_exact(3).all(|p| p != BACKGROUND));
    }
}
