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
//!
//! `PF_Translucent`/`PF_Modulated` polys draw in a SECOND pass, back-to-front (painter's), after
//! every opaque poly: z-TESTED against the opaque buffer but never z-WRITTEN, so overlapping
//! blended layers all test against the same opaque depth and composite in draw order (nearest
//! last). Blend formulas (real UE1, 8-bit paletted textures with no per-texel alpha —
//! `dev/docs/unrealed/leveldesign/kb/textures.md` "Translucent"/"Modulated"): Translucent is
//! ADDITIVE (`dest + src`, clamped); Modulated is D3D modulate-2x (`dest * src / 128`, clamped).
//!
//! `PF_Mirrored` polys get a REAL planar reflection, not a blend formula: the camera is reflected
//! across the mirror poly's own plane and the WHOLE scene is re-rendered from that reflected
//! camera (same width/height/fov, so screen coordinates line up pixel-for-pixel — a reflected ray
//! through screen pixel (x,y) is the same ray on both sides of the mirror plane, a standard
//! property of planar reflection: reflecting camera position AND basis by the same isometry
//! preserves every dot product against the mirror point, so the two cameras agree on every
//! surface point's projected pixel). The secondary scene is world-space CLIPPED to the real
//! camera's side of the mirror plane first (an oblique near-clip at the mirror itself, not the
//! usual fixed `NEAR`), so nothing "behind" the mirror (e.g. a wall it's mounted on) leaks into
//! the reflection. A mirror poly draws OPAQUE (z-tested AND z-written) sampling the secondary
//! buffer at the SAME pixel it occupies in the primary frame, no per-poly shading (a mirror shows
//! already-lit imagery, not a diffuse surface). Capped at one reflection deep: inside a
//! reflection's own render, `PF_Mirrored` polys draw as ordinary opaque textured surfaces instead
//! of recursing — a hall-of-mirrors is a real UE1 case this draft renderer does not attempt.
//!
//! `PF_Mirrored` alone is a PURE mirror: the surface's own texture never shows. Combined with
//! `PF_Translucent` — real content carries both (`02_NYC_Bar.dx` Brush117, `Terraniux.unr`
//! `DecayedS.Floor.dmFlor2a`) — it draws the reflection AND its own texture, additively tinted on
//! top. UNVERIFIED HEURISTIC, not an RE fact like the rest of this file's mirror math: nothing here
//! confirms the real engine's PF_Mirrored+PF_Translucent combination actually composites this way,
//! only that real content sets both bits together. The additive formula is borrowed from
//! `PF_Translucent`'s own (confirmed) formula for lack of a better guess; a genuinely tinted/
//! one-way mirror plausibly ATTENUATES the reflection (multiplicative) rather than brightens it.
//! Needs disassembly/live-probe confirmation before this is trusted as real UE1 behavior.

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
    /// CSG-solved surface, or `poly.flags | actor PolyFlags` for a mover). Consulted by the
    /// backface cull (`light_in_front`'s `PF_TwoSided|PF_Portal` exemption) and by `blend_mode`
    /// (`PF_Translucent`/`PF_Modulated` — see the module doc).
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

const PF_TRANSLUCENT: u32 = 0x0000_0004;
const PF_MODULATED: u32 = 0x0000_0040;
const PF_MIRRORED: u32 = 0x0800_0000;

/// A poly's compositing mode, decided once from its `poly_flags`, for BUCKET ROUTING (which pass
/// draws it — opaque, mirror, or the z-tested-not-written blended pass). `PF_Mirrored` wins over
/// either blend flag: it routes to the mirror pass regardless of `PF_Translucent`/`PF_Modulated`
/// also being set. `PF_Translucent` alongside `PF_Mirrored` still has an effect, just not here —
/// `render_impl` gives that combination a second, additive tint pass of its own texture on top of
/// the reflection (module doc). Translucent takes precedence over Modulated if somehow both are
/// set with no Mirror bit — the two blend modes are mutually exclusive in the real renderer.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Blend {
    Opaque,
    Translucent,
    Modulated,
    Mirror,
}

fn blend_mode(poly_flags: u32) -> Blend {
    if poly_flags & PF_MIRRORED != 0 {
        Blend::Mirror
    } else if poly_flags & PF_TRANSLUCENT != 0 {
        Blend::Translucent
    } else if poly_flags & PF_MODULATED != 0 {
        Blend::Modulated
    } else {
        Blend::Opaque
    }
}

/// Reflect world point `p` across the plane through `plane_point` with unit normal `n`.
fn reflect_point(p: &Vec3, plane_point: &Vec3, n: &Vec3) -> Vec3 {
    let d = p.sub(plane_point).dot(n);
    Vec3::new(p.x - 2.0 * d * n.x, p.y - 2.0 * d * n.y, p.z - 2.0 * d * n.z)
}

/// Reflect a direction (no translation) across a plane with unit normal `n`. Sign of `n` does not
/// matter — both this and `reflect_point` are invariant under `n -> -n`.
fn reflect_dir(v: &Vec3, n: &Vec3) -> Vec3 {
    let d = v.dot(n);
    Vec3::new(v.x - 2.0 * d * n.x, v.y - 2.0 * d * n.y, v.z - 2.0 * d * n.z)
}

/// Sutherland-Hodgman clip of a world-space poly ring against the half-space
/// `(v - plane_point)·keep_dir >= 0`.
fn clip_world_by_plane(verts: &[Vec3], plane_point: &Vec3, keep_dir: &Vec3) -> Vec<Vec3> {
    let mut out = Vec::with_capacity(verts.len() + 2);
    let side = |v: &Vec3| v.sub(plane_point).dot(keep_dir);
    for i in 0..verts.len() {
        let a = verts[i];
        let b = verts[(i + 1) % verts.len()];
        let (sa, sb) = (side(&a), side(&b));
        if sa >= 0.0 {
            out.push(a);
        }
        if (sa >= 0.0) != (sb >= 0.0) {
            let t = sa / (sa - sb);
            out.push(Vec3::new(
                a.x + t * (b.x - a.x),
                a.y + t * (b.y - a.y),
                a.z + t * (b.z - a.z),
            ));
        }
    }
    out
}

/// A group of `RenderPoly` indices that share one mirror plane (a mirror surface fragmented by
/// CSG still reflects as ONE plane, one secondary render). `normal` is unit-length; its sign is
/// arbitrary (reflection is sign-invariant — see `reflect_point`/`reflect_dir`).
struct MirrorCluster {
    point: Vec3,
    normal: Vec3,
    indices: Vec<usize>,
}

/// Group every `Blend::Mirror` poly in `polys` by plane (point+normal within a loose tolerance —
/// CSG fragments of one authored mirror face land on the exact same plane in practice, and
/// several separate mirror brushes at the same height/orientation collapse into one reflection
/// too). Measured against real content: `Terraniux.unr`'s 8 `DecayedS.Floor.dmFlor2a` mirror
/// brushes (12 mirror-flagged polys total) span only 2 distinct Z levels, i.e. 2 clusters — not
/// bounded in general, so a level with many separately-oriented mirrors would cost one full
/// `render_impl` re-render per cluster (no cap, no warning).
fn group_mirror_clusters(polys: &[RenderPoly]) -> Vec<MirrorCluster> {
    let mut clusters: Vec<MirrorCluster> = Vec::new();
    for (i, poly) in polys.iter().enumerate() {
        if blend_mode(poly.poly_flags) != Blend::Mirror || poly.verts.len() < 3 {
            continue;
        }
        let n = newell_normal(&poly.verts);
        let len = n.size();
        if len < 1e-9 {
            continue; // degenerate mirror face, skip (matches render_poly's own degenerate guard)
        }
        let normal = Vec3::new(n.x / len, n.y / len, n.z / len);
        let point = poly.verts[0];
        // Same-orientation planes only (`dot`, not `abs(dot)`): two opposite-facing mirrors on the
        // same plane (a double-sided mirror wall) are two distinct physical mirrors, not one.
        let existing = clusters.iter_mut().find(|c| {
            c.normal.dot(&normal) > 0.999 && point.sub(&c.point).dot(&c.normal).abs() < 0.5
        });
        match existing {
            Some(c) => c.indices.push(i),
            None => clusters.push(MirrorCluster { point, normal, indices: vec![i] }),
        }
    }
    clusters
}

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

/// Render one polygon (facing cull, near clip, project, per-triangle raster) into `img`/`zbuf`.
#[allow(clippy::too_many_arguments)]
fn render_poly(
    poly: &RenderPoly,
    blend: Blend,
    textures: &[RenderTexture],
    camera: &Camera,
    half_w: f32,
    half_h: f32,
    focal: f32,
    img: &mut [u8],
    zbuf: &mut [f32],
    w: usize,
    h: usize,
    mirror_src: Option<&[u8]>,
    mirror_tint: bool,
) {
    if poly.verts.len() < 3 {
        return;
    }
    // Per-face brightness from the world-space face normal vs the fixed key light.
    let n = newell_normal(&poly.verts);
    let n_len = n.size();
    let shade = if n_len > 1e-12 {
        0.55 + 0.45 * (n.dot(&KEY_LIGHT).abs() / n_len)
    } else {
        return; // degenerate (zero-area) polygon
    };

    // Single-sided by default (real UnrealEd: `dev/docs/unrealed/leveldesign/kb/textures.md`
    // "2-Sided renders both faces"). Reuses the editor's own disassembled facing test
    // (`light::light_in_front`, from `URender::OccludeBsp`) with the camera standing in for
    // the light: `PF_TwoSided`/`PF_Portal` faces are never culled, everything else needs
    // `PlaneDot >= -1.0`.
    let unit_n = Vec3::new(n.x / n_len, n.y / n_len, n.z / n_len);
    if !light_in_front(&unit_n, &poly.verts[0], &camera.location, poly.poly_flags) {
        return;
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
        return;
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
            img,
            zbuf,
            w,
            h,
            &scr[0],
            &scr[k],
            &scr[k + 1],
            tex,
            poly.masked,
            shade,
            blend,
            mirror_src,
            mirror_tint,
        );
    }
}

/// World-space centroid depth along the camera's forward axis, for back-to-front sorting of
/// blended polys (painter's algorithm — larger depth = farther).
fn poly_depth(poly: &RenderPoly, camera: &Camera) -> f32 {
    let n = poly.verts.len().max(1) as f32;
    let mut c = Vec3::new(0.0, 0.0, 0.0);
    for v in &poly.verts {
        c.x += v.x;
        c.y += v.y;
        c.z += v.z;
    }
    c.x /= n;
    c.y /= n;
    c.z /= n;
    c.sub(&camera.location).dot(&camera.forward)
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
    render_impl(polys, textures, camera, width, height, 0)
}

/// The real `render()` body, plus `mirror_depth` (0 = the primary frame; 1 = inside one mirror's
/// reflected re-render — see the module doc for why recursion stops there). Opaque polys draw
/// first (z-tested + z-written); mirror polys draw next, also z-tested + z-written, each sampling
/// its own reflected re-render of the (mirror-plane-clipped) scene; `PF_Translucent`/
/// `PF_Modulated` polys draw last, sorted back-to-front, z-tested but not z-written (so they
/// composite correctly over a mirror pixel too).
fn render_impl(
    polys: &[RenderPoly],
    textures: &[RenderTexture],
    camera: &Camera,
    width: u32,
    height: u32,
    mirror_depth: u32,
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

    let mut blended: Vec<(&RenderPoly, Blend, f32)> = Vec::new();
    for poly in polys {
        let mut mode = blend_mode(poly.poly_flags);
        // Recursion cap (module doc): a mirror poly reached while ALREADY inside a reflected
        // re-render draws as plain opaque texture instead of recursing again.
        if mode == Blend::Mirror && mirror_depth > 0 {
            mode = Blend::Opaque;
        }
        match mode {
            Blend::Opaque => render_poly(
                poly, Blend::Opaque, textures, camera, half_w, half_h, focal, &mut img, &mut zbuf,
                w, h, None, false,
            ),
            Blend::Mirror => {} // drawn below, once per mirror plane, after every opaque poly
            _ => blended.push((poly, mode, poly_depth(poly, camera))),
        }
    }

    if mirror_depth == 0 {
        for cluster in group_mirror_clusters(polys) {
            // Orient the plane normal toward the REAL camera, so the clip below keeps the half
            // of the scene the mirror actually reflects (reflect_point/reflect_dir themselves
            // don't care about this sign — only the clip's notion of "which side is real" does).
            let mut keep_dir = cluster.normal;
            if camera.location.sub(&cluster.point).dot(&keep_dir) < 0.0 {
                keep_dir = Vec3::new(-keep_dir.x, -keep_dir.y, -keep_dir.z);
            }
            let refl_camera = Camera {
                location: reflect_point(&camera.location, &cluster.point, &cluster.normal),
                forward: reflect_dir(&camera.forward, &cluster.normal),
                right: reflect_dir(&camera.right, &cluster.normal),
                up: reflect_dir(&camera.up, &cluster.normal),
                fov_deg: camera.fov_deg,
            };
            // Reflected scene = every OTHER poly (this mirror's own faces excluded — a mirror
            // doesn't reflect itself), clipped to the real camera's side of the mirror plane so
            // whatever the mirror is mounted against doesn't leak into the reflection.
            let mut clipped_scene: Vec<RenderPoly> = Vec::new();
            for (j, poly) in polys.iter().enumerate() {
                if cluster.indices.contains(&j) {
                    continue;
                }
                let cv = clip_world_by_plane(&poly.verts, &cluster.point, &keep_dir);
                if cv.len() < 3 {
                    continue;
                }
                clipped_scene.push(RenderPoly {
                    verts: cv,
                    uv_base: poly.uv_base,
                    uv_axis_u: poly.uv_axis_u,
                    uv_axis_v: poly.uv_axis_v,
                    pan: poly.pan,
                    tex_index: poly.tex_index,
                    masked: poly.masked,
                    poly_flags: poly.poly_flags,
                });
            }
            let secondary =
                render_impl(&clipped_scene, textures, &refl_camera, width, height, mirror_depth + 1);
            for &idx in &cluster.indices {
                let tint = polys[idx].poly_flags & PF_TRANSLUCENT != 0;
                render_poly(
                    &polys[idx], Blend::Mirror, textures, camera, half_w, half_h, focal, &mut img,
                    &mut zbuf, w, h, Some(&secondary), tint,
                );
            }
        }
    }

    // Farthest first, so a nearer blended layer composites on top of a farther one.
    blended.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
    for (poly, mode, _depth) in blended {
        render_poly(
            poly, mode, textures, camera, half_w, half_h, focal, &mut img, &mut zbuf, w, h, None,
            false,
        );
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
    blend: Blend,
    mirror_src: Option<&[u8]>,
    mirror_tint: bool,
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
            let (sr, sg, sb) = (
                (rr * shade).min(255.0),
                (gg * shade).min(255.0),
                (bb * shade).min(255.0),
            );
            let o = pi * 3;
            match blend {
                Blend::Opaque => {
                    zbuf[pi] = inv_d; // z-tested AND z-written
                    img[o] = sr as u8;
                    img[o + 1] = sg as u8;
                    img[o + 2] = sb as u8;
                }
                Blend::Translucent => {
                    // Additive, no z-write: a black texel is near-invisible, a bright one glows.
                    img[o] = (img[o] as f32 + sr).min(255.0) as u8;
                    img[o + 1] = (img[o + 1] as f32 + sg).min(255.0) as u8;
                    img[o + 2] = (img[o + 2] as f32 + sb).min(255.0) as u8;
                }
                Blend::Modulated => {
                    // D3D modulate-2x, no z-write: 50%-grey src is neutral.
                    img[o] = ((img[o] as f32 * sr) / 128.0).min(255.0) as u8;
                    img[o + 1] = ((img[o + 1] as f32 * sg) / 128.0).min(255.0) as u8;
                    img[o + 2] = ((img[o + 2] as f32 * sb) / 128.0).min(255.0) as u8;
                }
                Blend::Mirror => {
                    // Opaque like a real mirror surface (z-tested AND z-written), but the colour
                    // comes from the reflected secondary render at this SAME pixel, not from a
                    // decoded texture — already-lit imagery, so no `shade` multiply on the
                    // reflection itself (see module doc for why the same pixel is the right
                    // sample). `mirror_src` is always `Some` at the one call site that passes
                    // `Blend::Mirror`; the texture-shaded colour is a defensive fallback, never
                    // hit in practice.
                    //
                    // `mirror_tint` (module doc, `PF_Mirrored | PF_Translucent`): the poly's own
                    // shaded texture (`sr`/`sg`/`sb`, already computed above) is additively
                    // composited ON TOP of the reflection, in this SAME pass — not a separate
                    // z-tested blended-list entry, which would tie (and lose) the z-test against
                    // the identical depth this same triangle just wrote.
                    zbuf[pi] = inv_d;
                    let (mut mr, mut mg, mut mb) = (sr, sg, sb); // Mirror-alone fallback (mirror_src=None)
                    if let Some(src) = mirror_src {
                        let so = pi * 3;
                        mr = src[so] as f32;
                        mg = src[so + 1] as f32;
                        mb = src[so + 2] as f32;
                    }
                    if mirror_tint {
                        mr = (mr + sr).min(255.0);
                        mg = (mg + sg).min(255.0);
                        mb = (mb + sb).min(255.0);
                    }
                    img[o] = mr as u8;
                    img[o + 1] = mg as u8;
                    img[o + 2] = mb as u8;
                }
            }
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

    // ── PF_Translucent/PF_Modulated blend compositing ──────────────────────────────────────

    #[test]
    fn raster_tri_blend_modes_are_z_tested_but_not_z_written() {
        // A 1x1 framebuffer, triangle fully covering the one pixel at depth 1/d = 1.0.
        let a = [0.0, 0.0, 1.0, 0.0, 0.0];
        let b = [2.0, 0.0, 1.0, 0.0, 0.0];
        let c = [0.0, 2.0, 1.0, 0.0, 0.0];

        // Opaque: z IS written (the existing, unchanged behaviour).
        let mut img = vec![0u8; 3];
        let mut zbuf = vec![0.0f32];
        raster_tri(&mut img, &mut zbuf, 1, 1, &a, &b, &c, None, false, 1.0, Blend::Opaque, None, false);
        assert_eq!(zbuf[0], 1.0);
        assert_eq!(img, vec![128, 128, 128]); // DEFAULT_GREY (no texture), shade 1.0

        // Translucent: the pixel composites (additive over the existing colour) but z stays
        // UNWRITTEN — mirrors `masked_transparent_texel_leaves_z_unwritten`'s precedent.
        let mut img = vec![10u8, 10, 10];
        let mut zbuf = vec![0.0f32];
        raster_tri(&mut img, &mut zbuf, 1, 1, &a, &b, &c, None, false, 1.0, Blend::Translucent, None, false);
        assert_eq!(zbuf[0], 0.0);
        assert_eq!(img, vec![138, 138, 138]); // 10 + 128

        // Modulated: same z-unwritten rule. src = DEFAULT_GREY (128) is the modulate-2x NEUTRAL
        // point, so a dest of 200 composites to exactly 200 — an exact, rounding-free check.
        let mut img = vec![200u8, 200, 200];
        let mut zbuf = vec![0.0f32];
        raster_tri(&mut img, &mut zbuf, 1, 1, &a, &b, &c, None, false, 1.0, Blend::Modulated, None, false);
        assert_eq!(zbuf[0], 0.0);
        assert_eq!(img, vec![200, 200, 200]);
    }

    #[test]
    fn translucent_wall_composites_additively_over_opaque_background() {
        // A full-frame opaque grey background, plus a small translucent wall in front carrying a
        // red/green tint (blue channel 0). Additive: red/green channels must brighten, blue must
        // stay exactly as the background left it (adding zero).
        let bg_tex = || RenderTexture { w: 1, h: 1, data: vec![128, 128, 128], mask: vec![1] };
        let front_tex = || RenderTexture { w: 1, h: 1, data: vec![100, 50, 0], mask: vec![1] };
        let cam = cam_at_origin_looking_plus_x(90.0);

        let bg_only = render(&[wall(100.0, 400.0, 0)], &[bg_tex()], &cam, 64, 64);

        let mut front = wall(40.0, 20.0, 1);
        front.poly_flags = PF_TRANSLUCENT;
        let composited = render(
            &[wall(100.0, 400.0, 0), front],
            &[bg_tex(), front_tex()],
            &cam,
            64,
            64,
        );

        let px = |img: &[u8]| {
            let o = (32 * 64 + 32) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        let (bg_px, comp_px) = (px(&bg_only), px(&composited));
        assert!(comp_px[0] > bg_px[0]); // red brightened
        assert!(comp_px[1] > bg_px[1]); // green brightened
        assert_eq!(comp_px[2], bg_px[2]); // blue unchanged (src blue = 0)
    }

    #[test]
    fn modulated_wall_darkens_or_brightens_the_backdrop() {
        let cam = cam_at_origin_looking_plus_x(90.0);
        let bg_tex = || RenderTexture { w: 1, h: 1, data: vec![128, 128, 128], mask: vec![1] };
        let bg_only = render(&[wall(100.0, 400.0, 0)], &[bg_tex()], &cam, 64, 64);
        let px = |img: &[u8]| {
            let o = (32 * 64 + 32) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        let bg_px = px(&bg_only);

        // A BLACK (src=0) modulated wall darkens the backdrop to EXACTLY zero (0 * anything = 0
        // regardless of shading/rounding) — an exact, rounding-free check.
        let mut dark = wall(40.0, 20.0, 1);
        dark.poly_flags = PF_MODULATED;
        let dark_tex = RenderTexture { w: 1, h: 1, data: vec![0, 0, 0], mask: vec![1] };
        let darkened = render(&[wall(100.0, 400.0, 0), dark], &[bg_tex(), dark_tex], &cam, 64, 64);
        assert_eq!(px(&darkened), [0, 0, 0]);

        // A WHITE (src=255, above the 128 neutral point) modulated wall brightens the backdrop.
        let mut bright = wall(40.0, 20.0, 1);
        bright.poly_flags = PF_MODULATED;
        let bright_tex = RenderTexture { w: 1, h: 1, data: vec![255, 255, 255], mask: vec![1] };
        let brightened =
            render(&[wall(100.0, 400.0, 0), bright], &[bg_tex(), bright_tex], &cam, 64, 64);
        assert!(px(&brightened)[0] > bg_px[0]);
    }

    #[test]
    fn translucent_face_behind_nearer_opaque_geometry_is_z_tested_out() {
        // A near OPAQUE wall in front of a farther TRANSLUCENT wall, same footprint: the
        // translucent face must fail the z-test and contribute nothing — the composite is
        // bit-for-bit the same as the near opaque wall rendered alone.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let near_tex = || RenderTexture { w: 1, h: 1, data: vec![10, 20, 30], mask: vec![1] };
        let far_tex = || RenderTexture { w: 1, h: 1, data: vec![200, 200, 200], mask: vec![1] };

        let alone = render(&[wall(40.0, 20.0, 0)], &[near_tex()], &cam, 64, 64);

        let mut far = wall(100.0, 20.0, 1);
        far.poly_flags = PF_TRANSLUCENT;
        let with_far = render(
            &[wall(40.0, 20.0, 0), far],
            &[near_tex(), far_tex()],
            &cam,
            64,
            64,
        );
        assert_eq!(alone, with_far);
    }

    #[test]
    fn blend_layer_compositing_does_not_depend_on_input_array_order() {
        // Two overlapping blended layers (one translucent, one modulated) over an opaque
        // background: `render()` must resolve draw order from DEPTH (back-to-front), not from
        // where each poly sits in the input slice.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let bg_tex = || RenderTexture { w: 1, h: 1, data: vec![128, 128, 128], mask: vec![1] };
        let near_tex = || RenderTexture { w: 1, h: 1, data: vec![90, 90, 90], mask: vec![1] };
        let far_tex = || RenderTexture { w: 1, h: 1, data: vec![40, 40, 40], mask: vec![1] };

        let make_near = || {
            let mut p = wall(40.0, 20.0, 1);
            p.poly_flags = PF_TRANSLUCENT;
            p
        };
        let make_far = || {
            let mut p = wall(70.0, 20.0, 2);
            p.poly_flags = PF_MODULATED;
            p
        };

        let forward = render(
            &[wall(100.0, 400.0, 0), make_near(), make_far()],
            &[bg_tex(), near_tex(), far_tex()],
            &cam,
            64,
            64,
        );
        let reversed = render(
            &[make_far(), make_near(), wall(100.0, 400.0, 0)],
            &[bg_tex(), near_tex(), far_tex()],
            &cam,
            64,
            64,
        );
        assert_eq!(forward, reversed);
    }

    // ── PF_Mirrored planar reflection ───────────────────────────────────────────────────────

    #[test]
    fn mirror_flag_takes_precedence_over_translucent() {
        // Real DX content carries both bits together (02_NYC_Bar.dx Brush117's glass pane,
        // 0x8880004 = Mirrored|HighShadowDetail|BrightCorners|Translucent) — Mirror must win.
        assert!(blend_mode(PF_MIRRORED | PF_TRANSLUCENT) == Blend::Mirror);
        assert!(blend_mode(PF_MIRRORED | PF_MODULATED) == Blend::Mirror);
        assert!(blend_mode(PF_MIRRORED) == Blend::Mirror);
    }

    #[test]
    fn mirror_reflects_geometry_behind_the_camera() {
        // Mirror wall at x=40 (wall()'s normal is -X: front-facing to a camera at the origin
        // looking +X). Reflecting the origin camera across x=40 gives a camera at x=80 looking
        // -X, which is exactly the ray a real mirror sends back down the room: past the real
        // camera (x=0) to whatever sits further behind it. A red "reflectee" wall at x=-100,
        // wound to face +X (`wall_facing_away`), sits on that reflected ray and nowhere the
        // PRIMARY camera can see it directly (it's behind the camera, so the ordinary facing
        // cull/near-clip already drops it from every non-mirror pass).
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut mirror = wall(40.0, 400.0, -1);
        mirror.poly_flags = PF_MIRRORED;
        let mut reflectee = wall_facing_away(-100.0, 400.0, 0);
        reflectee.poly_flags = 0;
        let red = RenderTexture { w: 1, h: 1, data: vec![255, 0, 0], mask: vec![1] };

        let img = render(&[mirror, reflectee], &[red], &cam, 64, 64);
        let o = (32 * 64 + 32) * 3;
        assert!(img[o] > 0 && img[o + 1] == 0 && img[o + 2] == 0); // red, not grey/background

        // Without the mirror flag the same wall is an ordinary opaque face: its OWN (untextured,
        // grey) surface shows, never the reflectee — proves the red pixel above really came from
        // the reflection, not from some other path painting the mirror face red.
        let mut opaque = wall(40.0, 400.0, -1);
        opaque.poly_flags = 0;
        let red2 = RenderTexture { w: 1, h: 1, data: vec![255, 0, 0], mask: vec![1] };
        let img2 = render(&[opaque, wall_facing_away(-100.0, 400.0, 0)], &[red2], &cam, 64, 64);
        let px2 = [img2[o], img2[o + 1], img2[o + 2]];
        assert_eq!(px2[0], px2[1]); // grey (default, untextured): r == g == b
        assert_eq!(px2[1], px2[2]);
    }

    #[test]
    fn mirror_plus_translucent_tints_the_reflection_with_its_own_texture() {
        // Real content combines the two bits (`02_NYC_Bar.dx` Brush117, `Terraniux.unr`
        // `DecayedS.Floor.dmFlor2a`): the mirror shows BOTH the reflection and its own texture,
        // additively tinted on top — distinct from Mirror alone, which never shows its texture.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let textures = || {
            vec![
                RenderTexture { w: 1, h: 1, data: vec![255, 0, 0], mask: vec![1] }, // 0: red
                RenderTexture { w: 1, h: 1, data: vec![0, 0, 255], mask: vec![1] }, // 1: blue
            ]
        };

        let mut mirror = wall(40.0, 400.0, 1); // tex 1 = blue tint
        mirror.poly_flags = PF_MIRRORED;
        let mut reflectee = wall_facing_away(-100.0, 400.0, 0); // tex 0 = red
        reflectee.poly_flags = 0;
        let pure = render(&[mirror, reflectee], &textures(), &cam, 64, 64);

        let mut tinted = wall(40.0, 400.0, 1);
        tinted.poly_flags = PF_MIRRORED | PF_TRANSLUCENT;
        let mut reflectee2 = wall_facing_away(-100.0, 400.0, 0);
        reflectee2.poly_flags = 0;
        let tint = render(&[tinted, reflectee2], &textures(), &cam, 64, 64);

        let o = (32 * 64 + 32) * 3;
        assert_eq!(pure[o + 2], 0); // pure mirror: no blue tint, its own texture never shows
        assert!(tint[o + 2] > 0); // tinted mirror: the blue texture IS additively visible
        assert!(tint[o] > 0 && tint[o + 1] == 0); // the red reflection is still there underneath
    }

    #[test]
    fn masked_mirror_lets_farther_geometry_show_through_the_transparent_texel() {
        // Combines two independently-tested mechanisms neither exercises together: PF_Masked's
        // alpha test (`masked_face_skips_transparent_texels`) and PF_Mirrored's reflection pass.
        // The mask check runs BEFORE the blend match in `raster_tri`, so it applies uniformly
        // regardless of blend mode: a transparent mirror texel writes nothing (no reflection, no
        // z), letting farther geometry show through, same as a masked opaque face would.
        let tex = RenderTexture {
            w: 2, h: 1,
            data: vec![0, 0, 0, 0, 0, 0], // colour is irrelevant: the opaque texel shows a REFLECTION
            mask: vec![1, 0],             // left opaque, right transparent
        };
        let back_tex = RenderTexture { w: 1, h: 1, data: vec![0, 255, 0], mask: vec![1] }; // green
        let reflect_tex = RenderTexture { w: 1, h: 1, data: vec![255, 0, 0], mask: vec![1] }; // red

        let mut mirror = wall(32.0, 2.0, 0); // 2-uu masked mirror, matching the masked-test geometry
        mirror.masked = true;
        mirror.poly_flags = PF_MIRRORED;
        let back = wall(80.0, 400.0, 1); // far green wall, full-frame fallback behind the mirror
        let reflectee = wall_facing_away(-100.0, 400.0, 2); // red, visible only via the reflection

        let cam = cam_at_origin_looking_plus_x(90.0);
        let img = render(&[mirror, back, reflectee], &[tex, back_tex, reflect_tex], &cam, 64, 64);
        let px = |x: usize| {
            let o = (32 * 64 + x) * 3;
            [img[o], img[o + 1], img[o + 2]]
        };
        // Left texel (opaque, mask=1): reflects -- red reflectee, not the mirror's own texture
        // colour (irrelevant here) and not the green backdrop.
        assert!(px(31)[0] > 0 && px(31)[1] == 0 && px(31)[2] == 0);
        // Right texel (transparent, mask=0): skipped whole, so the farther GREEN wall shows
        // through -- no reflection, no mirror colour. Shaded (opaque faces ARE shaded, unlike a
        // mirror's reflection): shade for a +X-normal wall is 0.55+0.45*0.408 (`uv_texel_probe`).
        let shade = 0.55 + 0.45 * 0.408_f32;
        assert_eq!(px(32), [0, (255.0 * shade) as u8, 0]);
    }

    #[test]
    fn mirror_poly_is_backface_culled_like_any_other_face() {
        // A mirror facing away from the camera is culled (real UnrealEd: single-sided by
        // default), same as `single_sided_back_face_is_culled` for an ordinary opaque face.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut away = wall_facing_away(100.0, 400.0, -1);
        away.poly_flags = PF_MIRRORED;
        let img = render(&[away], &[], &cam, 32, 32);
        assert!(img.chunks_exact(3).all(|p| p == BACKGROUND));
    }

    #[test]
    fn facing_mirrors_do_not_hang_and_cap_recursion() {
        // Two mirrors facing each other between the camera: without a recursion cap this would
        // either hang or blow the stack. Rendering must complete (this test finishing at all IS
        // the regression check) and show something other than the flat background — the module
        // doc's documented behaviour is that a mirror reached a second time (mirror_depth > 0)
        // draws as its own opaque texture instead of recursing again.
        let cam = cam_at_origin_looking_plus_x(90.0);
        let mut near_mirror = wall(20.0, 100.0, -1);
        near_mirror.poly_flags = PF_MIRRORED;
        let mut far_mirror = wall_facing_away(-20.0, 100.0, -1);
        far_mirror.poly_flags = PF_MIRRORED;
        let img = render(&[near_mirror, far_mirror], &[], &cam, 32, 32);
        assert_eq!(img.len(), 32 * 32 * 3);
        assert!(img.chunks_exact(3).any(|p| p != BACKGROUND));
    }
}
