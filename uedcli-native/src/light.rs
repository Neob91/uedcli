//! Native `LIGHT APPLY` — the surface-lightmap bake (spike section 20-lighting-bake.md).
//!
//! Reproduces UnrealEd's `shadowIlluminateBsp` **output**, not its light transport: the bake
//! stores, per lit surface per reaching light, a **1-bit-per-lumel visibility mask** (`1` = that
//! lumel has clear line-of-sight to the light AND is within its radius; `0` = shadowed / out of
//! range).  Brightness, hue and attenuation are applied by the GAME at render time from the light
//! actors (already in the T3D) — the bake is purely geometric: a **front-side plane cull** (a light
//! behind a surface's plane never lights its front face — `light_in_front`, §17), then per lumel a
//! radius cut-off + BSP line-of-sight (`linecheck::line_clear`).  See section 20 §0/§17.
//!
//! Produces the three Model arrays + the surf link (§2/§8):
//!   `model.light_map`  (FLightMapIndex per lightmapped surf),
//!   `model.light_bits` (packed shadow planes, §3), and
//!   `model.lights`     (flattened per-surf light runs, here 0-based light INDICES + `-1` NULL
//!                       terminators — Python assembly rewrites them to export object-refs).
//! Sets `surf.i_light_map` to the record index (or `-1` for an unlightmapped surf).

use crate::linecheck::{line_clear, VIS_BRIGHT_CORNERS, VIS_EXTRA_FLAGS};
use crate::model::{BuildError, LightMapIndex, Model, Vec3};
use rayon::prelude::*;

// PolyFlags (canonical UE1 EPolyFlags).
const PF_INVISIBLE: u32 = 0x0000_0001;
const PF_FAKE_BACKDROP: u32 = 0x0000_0080;
const PF_TWO_SIDED: u32 = 0x0000_0100;
const PF_LOW_SHADOW_DETAIL: u32 = 0x0000_8000;
const PF_BRIGHT_CORNERS: u32 = 0x0008_0000;
const PF_SPECIAL_LIT: u32 = 0x0010_0000;
const PF_UNLIT: u32 = 0x0040_0000;
const PF_HIGH_SHADOW_DETAIL: u32 = 0x0080_0000;
const PF_PORTAL: u32 = 0x0400_0000;
/// A surface with any of these flags is NOT lightmapped (gets `iLightMap = -1`, no record).
///
/// This is the editor's exact lightmap-skip mask **`0x400081`**, read straight out of the
/// allocate-meshes pass: `Editor 0x100a6031` does `test dword ptr [surf+0x1b0], 0x400081` and, when
/// nonzero, stores `iLightMap = -1` (`+0x1c8`) and skips the `push 0x28` (=40, the IN-MEMORY
/// `FLightMapIndex` size) allocation (disasm confirmed 2026-07-18; spike §20 §21).
///
/// ⚠️ `PF_Portal` (0x0400_0000) is **NOT** in this mask — an earlier §8 pseudo-code claim that it was
/// is REFUTED by the editor oracle `Test_Castle.dx`, which lightmaps all 4 of its two-sided water
/// portal sheets (pf `0x0400010c`) with real lit records, and by the disasm mask above. Including it
/// wrongly culled those 4 surfaces (native 480 records vs editor 484 — the 120-byte *serialized*
/// `LightMap` gap, 4 records × 30 on-disk bytes; the 40-byte `push 0x28` above is the RAM struct).
const PF_NO_LIGHTMAP: u32 = PF_UNLIT | PF_INVISIBLE | PF_FAKE_BACKDROP;

/// Self-shadow bias: push the lumel/ray origin off the surface by `Normal × 4` (§5.3, const 4.0).
const SELF_SHADOW_BIAS: f32 = 4.0;

/// Backface cull: a light far enough BEHIND a surface's plane never lights its front face.
///
/// This is the editor's own test, from the back-face branch of `URender::OccludeBsp`
/// (`render.dll 0x100198c7`–`0x100198dd`, disassembled 2026-08-27), which the gather pass reaches
/// through `URender::GetVisibleSurfs`:
///
/// ```text
/// if( !IsFront && PlaneDot < -1.0f && !(PolyFlags & 0x04000100) ) drop the surface
/// ```
///
/// with `IsFront = PlaneDot > 0`. So a surface is KEPT whenever `PlaneDot >= -1.0` — a one-unit
/// tolerance, not a strict sign test — and a `PF_TwoSided` or `PF_Portal` surface is never dropped at
/// all, however far behind it the light sits. That two-sided exemption is what the earlier strict
/// `> 0` form was flagged as latently missing: a two-sided sheet renders its single lightmap from
/// BOTH faces, so a light behind it is legitimate.
///
/// `normal` is the unit `Vectors[vNormal]` entry, so the dot is the true signed distance, and any
/// point on the plane works for `base` (`pBase` lies on it by construction).
///
/// Why native needs the cull at all when the per-lumel ray would also reject a back light: clear
/// line-of-sight to a surface's FRONT face is geometrically impossible from behind its plane, so for
/// *correct* geometry the two coincide — but the native ray traces a BSP whose solid cells do not
/// perfectly enclose, so back-side lights can slip past it. Measured on the editor oracle 2026-07-17,
/// dropping the cull put a back-side light on 2586 of 5486 (surf, light) entries, roughly doubling
/// the lights per surface and flattening the render's contrast.
#[inline]
fn light_in_front(normal: &Vec3, base: &Vec3, light: &Vec3, poly_flags: u32) -> bool {
    poly_flags & (PF_TWO_SIDED | PF_PORTAL) != 0
        || light.sub(base).dot(normal) >= -1.0
}

/// One participating light.  The actor-level filter (`LightType != LT_None && (bStatic ||
/// bNoDelete)`) happens caller-side; every light passed here participates.
#[derive(Debug, Clone, Copy)]
pub struct LightInput {
    pub location: Vec3,
    /// `LightRadius` BYTE (actor+0x1a1).  World radius = `(radius + 1) × 25` (§5.1).
    pub radius: u8,
    /// The light's `bSpecialLit`.  It PARTITIONS the surfaces, it does not merely add: a
    /// `bSpecialLit` light lights ONLY `PF_SpecialLit` surfaces, and a normal light lights ONLY
    /// surfaces without that flag (`Editor 0x100a4ea0`, disassembled 2026-08-27 — the branch tests
    /// the light's bit, then keeps or rejects on `surf.PolyFlags & 0x100000` accordingly).
    pub special_lit: bool,
}

impl LightInput {
    #[inline]
    fn world_radius(&self) -> f32 {
        (self.radius as f32 + 1.0) * 25.0
    }
}

/// The grid descriptor + planes computed for one surface (§3/§4), pre-concatenation.
struct SurfBake {
    surf_index: usize,
    rec: LightMapIndex, // data_offset / i_light_actors filled during serial concat
    light_indices: Vec<i32>,
    bits: Vec<u8>,
}

/// Grid-sizing (§4, editor rule pinned in spike §20 §22).  Returns `(size, scale, pan)` for one
/// axis given the texture-space extent.
///
/// The editor's lumel grid dimension is **`Clamp = ceil((extent − 0.25) / lumel_scale)`, clamped to
/// `[2, 256]`**.  The grid spans `[min − 0.125, max + 0.125]`, so the `0.25` is the half-lumel pad at
/// each end being taken back out before the division — the same `0.25` constant the allocator reads
/// from `.rdata` (`Editor 0x100de968`, spike §20 §4).
///
/// Fitted against the editor's own `LIGHT APPLY` output on UNATCO (`01_NYC_UNATCOHQ`, 3434 lit
/// records): predicting each record's stored `UClamp`/`VClamp` from that record's own surf extent
/// reproduces **6868/6868** axes.  Two rejected forms and what they cost on the same oracle
/// (`harness/grid_formula_fit.py` in `spikes/2026-08-27-native-light-apply-parity/`):
///
/// * `ceil(extent / scale)` — 6605/6868.  It over-counts by 1 on every axis whose extent sits within
///   0.25 **above** an exact multiple of the lumel scale (e.g. extent 160.0018 at scale 32 →
///   `ceil(5.00006) = 6`, editor 5).  Axis-aligned test geometry never produces such an extent, so
///   this form scored 484/484 on `Test_Castle.dx` and only broke on real level content.
/// * `trunc((extent − 0.25)/scale − 0.5) + 1` — 6116/6868; under-counts every non-multiple by 1.
///
/// All of that form's documented boundaries still hold here: an exact multiple takes no extra texel
/// (extent 64 at scale 32 → `ceil(1.992) = 2`; 1024 at 32 → 32) and a non-multiple rounds up
/// (extent 80 at 32 → `ceil(2.492) = 3`).
///
/// The texel **scale** is `(extent + 0.25) / (size - 1)`: the grid spans `[min-0.125, max+0.125]`
/// (a half-lumel pad each side, matching `Pan = min - 0.125`), so `(size-1)` steps cover
/// `extent + 0.25`.  Verified byte-exact on the golden's `TextureUScale`/`TextureVScale` floats.
///
/// Two details from the disassembly of `Editor 0x100a5bf0` (2026-08-27) that a plain `clamp(…, 2,
/// 256)` in f32 gets wrong:
///
/// * **256 is not a clamp.** The editor tests `size > 256` and, when it trips, DOUBLES the lumel
///   scale and recomputes the axis from scratch (`0x100a5dba`, `addss xmm3,xmm0`; the V axis has its
///   own retry at `0x100a5dac`, so U and V double independently). A surface needing ~300 lumels at
///   scale 32 gets scale 64 and ~150 lumels — a different `UScale` as well as a different size, not
///   a truncated grid. No UNATCO axis reaches 256 at its base scale, so this is unmeasured there;
///   it is here because clamping would silently ship a wrong grid on the first big high-detail
///   surface that does.
/// * **The extent subtraction is f32 but everything after it is f64**, down to a single narrowing
///   store (`cvtss2sd` / `subsd` / `divsd` / `cvtpd2ps`), and the three constants are f64 in
///   `.rdata`. Computing the scale or the pan in f32 instead differs by an ulp on some records.
fn axis_grid(vmin: f32, vmax: f32, scale: f32) -> (i32, f32, f32) {
    let extent = vmax - vmin; // f32 subtract, as the editor does
    let mut scale = scale;
    // Doubling the scale halves the size, so a finite extent settles in a handful of rounds; the
    // bound only stops an infinite/NaN extent from spinning here (a hang inside the FFI call).
    for _ in 0..64 {
        // `ceil` where the editor rounds-to-nearest after subtracting 0.5: the two agree except
        // when `(extent-0.25)/scale` is exactly integral, which a geometry-derived extent never is.
        // The cast is saturating, so an absurd or NaN extent lands on the `max(2)` rather than
        // producing a `size - 1` of 0.
        let size = (((extent as f64 - 0.25) / scale as f64).ceil() as i32).max(2);
        if size > 256 {
            scale *= 2.0;
            continue;
        }
        return (size, ((extent as f64 + 0.25) / (size - 1) as f64) as f32,
                (vmin as f64 - 0.125) as f32);
    }
    (256, ((extent as f64 + 0.25) / 255.0) as f32, (vmin as f64 - 0.125) as f32)
}

/// The bits a row's final byte carries ABOVE `u_size`: `1` for every one of them when the row's last
/// real lumel was lit, `0` otherwise (`0` also when the row is a whole number of bytes).
///
/// The game masks to `u_size` when it reads, so these bits cannot affect play — but they are on disk
/// and the bar here is byte identity. The editor's packer sets them from the LAST `LineCheck` result
/// it holds (`Editor 0x100a5a4c`–`0x100a5a5d`), which is why 40% of the bits above `USize` are set in
/// its own UNATCO output. Zero-filling them instead left 2026 of 3345 records byte-different.
///
/// It is NOT a re-trace of the extrapolated lumels: an earlier guess that it was scored worse, and
/// the instructions read the stored result rather than calling `LineCheck` again.
#[inline]
fn row_padding(u_size: i32, last_clear: bool) -> u8 {
    let used = u_size & 7;
    if used == 0 || !last_clear {
        0
    } else {
        !0u8 << used
    }
}

/// The stored grid descriptor.  `data_offset`/`i_light_actors` are filled during the serial concat.
fn descriptor(u_size: i32, v_size: i32, u_scale: f32, v_scale: f32, pan_x: f32, pan_y: f32)
              -> LightMapIndex {
    LightMapIndex {
        data_offset: 0,
        i_light_actors: -1,
        pan: Vec3::new(pan_x, pan_y, 0.0),
        u_scale,
        v_scale,
        u_size,
        v_size,
    }
}

/// The lumel STEP a `PF_BrightCorners` surface is walked with: `(f32)((f64)scale - 0.5/(size-1))`
/// (`Editor 0x100a570c`–`0x100a5731`, in f64 with the `0.5` from `.rdata 0x100de978`).
///
/// Paired with the `+0.25` the caller adds to the grid origin, it pulls the whole sample grid 0.25
/// off each edge of the surface — 0.5 of shrink spread over `size-1` steps. The SERIALIZED
/// `UScale`/`VScale` keep the un-shrunk values; only the walk uses this.
#[inline]
fn bright_corners_step(scale: f32, size: i32) -> f32 {
    ((scale as f64) - 0.5 / (size - 1) as f64) as f32
}

/// Lightmap resolution (world units per lumel) from PolyFlags (§4).
fn lumel_scale(pf: u32) -> f32 {
    if (pf & (PF_HIGH_SHADOW_DETAIL | PF_LOW_SHADOW_DETAIL))
        == (PF_HIGH_SHADOW_DETAIL | PF_LOW_SHADOW_DETAIL)
    {
        128.0
    } else if pf & PF_HIGH_SHADOW_DETAIL != 0 {
        16.0
    } else if pf & PF_LOW_SHADOW_DETAIL != 0 {
        64.0
    } else {
        32.0
    }
}

/// The two WORLD directions one lumel step moves along, for a surface whose texture frame is
/// `TextureU`/`TextureV` in the plane of `Normal`: `(u_dir, v_dir)`.  `None` for a degenerate basis.
///
/// The editor builds these as `FCoords(0, TextureU, TextureV, Normal).Inverse().Transpose()` and
/// then reads off `XAxis`/`YAxis` (`Editor 0x100a552a`–`0x100a556a`; `FCoords::Inverse` is
/// `core 0x509c0`, `Transpose` `core 0x2ddd0`).  Unwound, that is the classic adjugate inverse:
/// with `det = TextureU · (TextureV × Normal)`, `u_dir = (TextureV × Normal) / det` and
/// `v_dir = (Normal × TextureU) / det`,
/// so `u_dir · TextureU == 1`, `u_dir · TextureV == 0`, `u_dir · Normal == 0` — one world unit of
/// travel per unit of texture U. The vectors come from `Model.Vectors` and are used VERBATIM, with
/// no re-normalisation (`0x100a5107`–`0x100a5174`).
///
/// Why the caller then walks the grid by repeated addition of `u_dir * UScale` instead of solving
/// for each lumel: that is what the editor does (`FVector::operator+=` per lumel, `0x100a5a35`), and
/// the f32 rounding of an accumulation differs from that of a fresh multiply, so a per-lumel solve
/// cannot be bit-identical.
fn lumel_axes(tu: Vec3, tv: Vec3, normal: Vec3) -> Option<(Vec3, Vec3)> {
    let c0 = tv.cross(&normal);
    let det = tu.dot(&c0);
    if det.abs() < 1e-8 {
        return None;
    }
    let rdet = 1.0 / det;
    let c1 = normal.cross(&tu);
    Some((
        Vec3::new(c0.x * rdet, c0.y * rdet, c0.z * rdet),
        Vec3::new(c1.x * rdet, c1.y * rdet, c1.z * rdet),
    ))
}

#[inline]
fn add(a: &Vec3, b: &Vec3) -> Vec3 {
    Vec3::new(a.x + b.x, a.y + b.y, a.z + b.z)
}

#[inline]
fn scaled(v: &Vec3, s: f32) -> Vec3 {
    Vec3::new(v.x * s, v.y * s, v.z * s)
}

/// Validate that every geometry index the bake dereferences is in range, so the bake can index
/// with `as usize` without panicking (a panic would cross the FFI boundary as a `PanicException`,
/// not the contracted `BuildError` — repo rule: no bare traceback reaches the user).  A well-formed
/// `build_geometry` output always passes; this only fires on a corrupt/hand-built Model.
/// Refuse a Model carrying a non-finite point or vector, so no texture-space extent can be `inf` or
/// `NaN` by the time `axis_grid` divides by the lumel scale.  Without this an infinite extent walks
/// `axis_grid`'s scale-doubling loop to its bound and then falls through to a FABRICATED descriptor —
/// a substituted default for something it could not resolve, which the repo's no-fallback rule
/// forbids. A well-formed build never trips this; a corrupt or hand-built Model gets a named error.
fn validate_finite(model: &Model) -> Result<(), BuildError> {
    for (what, vs) in [("point", &model.points), ("vector", &model.vectors)] {
        for (i, v) in vs.iter().enumerate() {
            if !(v.x.is_finite() && v.y.is_finite() && v.z.is_finite()) {
                return Err(BuildError(format!(
                    "lightmap bake: {what} {i} is not finite ({}, {}, {})", v.x, v.y, v.z)));
            }
        }
    }
    Ok(())
}

fn validate_indices(model: &Model) -> Result<(), BuildError> {
    let (nvec, npts, nsurf, nvert, nnode) = (
        model.vectors.len() as i32,
        model.points.len() as i32,
        model.surfs.len() as i32,
        model.verts.len() as i32,
        model.nodes.len() as i32,
    );
    let ck = |v: i32, n: i32, what: &str| -> Result<(), BuildError> {
        if v < 0 || v >= n {
            Err(BuildError(format!(
                "lightmap bake: {what} index {v} out of range [0,{n})"
            )))
        } else {
            Ok(())
        }
    };
    for s in &model.surfs {
        ck(s.v_normal, nvec, "surf vNormal")?;
        ck(s.v_texture_u, nvec, "surf vTextureU")?;
        ck(s.v_texture_v, nvec, "surf vTextureV")?;
        ck(s.p_base, npts, "surf pBase")?;
    }
    for n in &model.nodes {
        if n.i_surf != -1 {
            ck(n.i_surf, nsurf, "node iSurf")?;
        }
        if n.i_front != -1 {
            ck(n.i_front, nnode, "node iChild[0]")?;
        }
        if n.i_back != -1 {
            ck(n.i_back, nnode, "node iChild[1]")?;
        }
        if n.i_plane != -1 {
            // `lightmap_emit_order` follows the `iPlane` coplanar chain — validate it here so the
            // walk can index `nodes[iPlane]` with `as usize` without panicking (no other pass reads
            // `iPlane`, but the no-panic FFI contract still covers it).
            ck(n.i_plane, nnode, "node iPlane")?;
        }
        if n.num_vertices < 0 || n.i_vert_pool < 0 || n.i_vert_pool + n.num_vertices > nvert {
            return Err(BuildError(format!(
                "lightmap bake: node vert pool [{}..{}) overruns Verts ({nvert})",
                n.i_vert_pool,
                n.i_vert_pool + n.num_vertices
            )));
        }
    }
    for v in &model.verts {
        ck(v.i_vertex, npts, "vert iVertex")?;
    }
    Ok(())
}

/// Bake the lightmaps into `model`, given the participating lights.  Idempotent: fully resets the
/// four lightmap outputs first.  Runs the per-surface work in parallel (rayon) and concatenates
/// deterministically in the editor's **BSP tree-walk order** (`lightmap_emit_order`), so offsets
/// are stable regardless of thread scheduling.  Returns `BuildError` (never panics) on an
/// out-of-range geometry index.
pub fn bake(model: &mut Model, lights: &[LightInput]) -> Result<(), BuildError> {
    // (1) Reset.
    model.light_map.clear();
    model.light_bits.clear();
    model.lights.clear();
    for s in model.surfs.iter_mut() {
        s.i_light_map = -1;
    }
    if model.nodes.is_empty() {
        return Ok(());
    }
    validate_indices(model)?;
    validate_finite(model)?;

    // Gather each surf's node vertices (a shared surf is referenced by several nodes) once.
    let mut surf_verts: Vec<Vec<Vec3>> = vec![Vec::new(); model.surfs.len()];
    for n in &model.nodes {
        if n.i_surf < 0 || n.i_surf as usize >= model.surfs.len() {
            continue;
        }
        let dst = &mut surf_verts[n.i_surf as usize];
        for k in 0..n.num_vertices {
            let vi = model.verts[(n.i_vert_pool + k) as usize].i_vertex as usize;
            dst.push(model.points[vi]);
        }
    }

    // (2-4) Per-surface bake, in parallel.
    let mut bakes: Vec<Option<SurfBake>> = (0..model.surfs.len())
        .into_par_iter()
        .map(|si| bake_surf(model, &surf_verts[si], si, lights))
        .collect();

    // (5) Serial concat: assign DataOffset/iLightActors, append planes + light runs, link surfs.
    // The `LightMap` array is emitted in the editor's **BSP-tree-walk order** (`lightmap_emit_order`),
    // NOT surf-index order — verified byte-exact against `Test_Castle.dx` (spike §20 §21). Emitting
    // in walk order aligns `LightMap`, `LightBits`, and the per-surf `Lights` region-2 runs
    // positionally with the editor. A defensive surf-order sweep afterward catches any lightmappable
    // surf the walk from root missed (a disconnected BSP — shouldn't happen), so the record count can
    // never silently drop below the surf's lit count.
    let order = lightmap_emit_order(model);
    for si in order {
        if let Some(b) = bakes[si].take() {
            emit_record(model, b);
        }
    }
    for si in 0..bakes.len() {
        if let Some(b) = bakes[si].take() {
            emit_record(model, b);
        }
    }
    Ok(())
}

/// Append one baked surf's record + its shadow bits + its light run to the Model, and link the surf.
/// Records are pushed in the caller's chosen order; `surf.i_light_map` is set to the pushed index.
fn emit_record(model: &mut Model, b: SurfBake) {
    let mut rec = b.rec;
    if b.light_indices.is_empty() {
        rec.data_offset = 0;
        rec.i_light_actors = -1; // dark record (§2)
    } else {
        rec.data_offset = model.light_bits.len() as i32;
        model.light_bits.extend_from_slice(&b.bits);
        rec.i_light_actors = model.lights.len() as i32;
        model.lights.extend_from_slice(&b.light_indices);
        model.lights.push(-1); // NULL terminator ends this surf's light run (§2/§8)
    }
    let idx = model.light_map.len() as i32;
    model.light_map.push(rec);
    model.surfs[b.surf_index].i_light_map = idx;
}

/// The editor's `LightMap`-array emission order: one `FLightMapIndex` per lightmapped surf in **BSP
/// tree-walk order**, NOT surf-index order. UnrealEd's shadow/mesh-allocate pass descends the node
/// tree — visit a node's surf, recurse its BACK subtree, then its FRONT subtree, then step to the
/// next coplanar node along the `iPlane` chain — allocating a record the first time each lightmappable
/// surf is seen. A surf is marked seen on first visit regardless of lightmappability (so an unlit surf
/// is never re-considered) but only appended if it passes `PF_NO_LIGHTMAP`. Verified byte-exact
/// against `Test_Castle.dx`: the resulting record→surf sequence reproduces the editor's `LightMap`
/// order exactly (spike §20 §21).
fn lightmap_emit_order(model: &Model) -> Vec<usize> {
    // `node_seen` (node-keyed) is a cycle/DAG guard: a well-formed BSP visits each node exactly once
    // (disjoint front/back subtrees, disjoint `iPlane` chains), but a corrupt Model with an
    // `iPlane`/child back-edge would otherwise loop forever or overflow the stack. Breaking on a
    // re-visit keeps the walk O(nodes) and honors the "never hang on a corrupt Model" contract.
    // `surf_seen` (surf-keyed) is the first-occurrence dedup that fixes the emission order.
    fn walk(model: &Model, mut ni: i32, node_seen: &mut [bool], surf_seen: &mut [bool], order: &mut Vec<usize>) {
        while ni >= 0 {
            let nu = ni as usize;
            if node_seen[nu] {
                break;
            }
            node_seen[nu] = true;
            let n = &model.nodes[nu];
            let s = n.i_surf;
            if s >= 0 {
                let su = s as usize;
                if !surf_seen[su] {
                    surf_seen[su] = true;
                    if model.surfs[su].poly_flags & PF_NO_LIGHTMAP == 0 {
                        order.push(su);
                    }
                }
            }
            walk(model, n.i_back, node_seen, surf_seen, order);
            walk(model, n.i_front, node_seen, surf_seen, order);
            ni = n.i_plane;
        }
    }
    let mut order = Vec::with_capacity(model.surfs.len());
    let mut surf_seen = vec![false; model.surfs.len()];
    let mut node_seen = vec![false; model.nodes.len()];
    if !model.nodes.is_empty() {
        walk(model, 0, &mut node_seen, &mut surf_seen, &mut order);
    }
    order
}

/// Compute one surface's grid + shadow planes (§3-§6).  Returns `None` for an unlightmapped surf.
fn bake_surf(model: &Model, verts: &[Vec3], si: usize, lights: &[LightInput]) -> Option<SurfBake> {
    let s = &model.surfs[si];
    if s.poly_flags & PF_NO_LIGHTMAP != 0 || verts.is_empty() {
        return None;
    }
    let normal = model.vectors[s.v_normal as usize];
    let tu = model.vectors[s.v_texture_u as usize];
    let tv = model.vectors[s.v_texture_v as usize];
    let base = model.points[s.p_base as usize];
    // A degenerate texture basis has no lumel grid to walk, so the surface gets a DARK record rather
    // than no record: the editor allocates records in a separate pass that looks only at the node's
    // vertex count and the `PF_NO_LIGHTMAP` mask, so skipping one here would shift every later
    // record's index.
    let axes = lumel_axes(tu, tv, normal);
    // The lightmap texture frame is BASE-RELATIVE: coordinates are `(vert - Base)·TextureU/V`, i.e.
    // world dots offset by the surf base's own projection.  The editor stores Pan in this frame
    // (`Pan = min(vert-Base)·Tex - 0.125`, verified field-for-field vs Test_Castle.dx 2026-07-16) —
    // NOT the raw world dot (spike §4's "raw dot" note was WRONG).  Using raw world dots put Pan at
    // world coords (e.g. -1150) while the renderer samples in the base-relative frame, so every
    // world point landed far outside the tiny lumel grid → out-of-bounds lightmap reads smeared all
    // the colored lights into a rainbow.  Subtract the base projection so Pan is small & local.

    // Texture-space extent = min/max of (vert - Base)·TextureU / (vert - Base)·TextureV (§4).
    // The base subtraction is done PER-VERTEX BEFORE the dot — `(v - Base)·Tex`, NOT the algebraically
    // equal `v·Tex - Base·Tex`. On an *angled* TextureU/V (a rotated surface) the two orderings round
    // differently in f32, and the editor's is subtract-first: computing extent as `(v-Base)·Tex`
    // reproduces the golden's stored `Pan`/`TextureVScale` on 484/484 records, vs 412/484 for the
    // dot-then-subtract form (spike §20 §22, `harness/lightmap_grid_diff.py`). Axis-aligned axes are
    // unaffected (both orderings collapse to `v.x - Base.x`), which is why only the angled-V surfaces
    // (75 records) diverged. `Vec3::dot` accumulates x+y+z left-to-right in f32, matching the engine.
    let (mut umin, mut umax) = (f32::INFINITY, f32::NEG_INFINITY);
    let (mut vmin, mut vmax) = (f32::INFINITY, f32::NEG_INFINITY);
    for v in verts {
        let d = v.sub(&base);
        let u = d.dot(&tu);
        let w = d.dot(&tv);
        umin = umin.min(u);
        umax = umax.max(u);
        vmin = vmin.min(w);
        vmax = vmax.max(w);
    }
    let scale = lumel_scale(s.poly_flags);
    let (u_size, u_scale, pan_x) = axis_grid(umin, umax, scale);
    let (v_size, v_scale, pan_y) = axis_grid(vmin, vmax, scale);

    // `PF_BrightCorners` (`0x00080000` — read off `unrealed.exe`'s own surface-flags dialog table at
    // `.data 0x4cd8f8`, where the mask sits beside control `0x42a`, captioned "Bright Corners")
    // changes the bake in two ways and the STORED descriptor in none: it insets the sample grid by
    // 0.25 and shrinks its step so the whole grid pulls 0.5 off the polygon's edges
    // (`Editor 0x100a56ff`–`0x100a5818`), and it raises the shadow ray's `ExtraNodeFlags` from `0x04`
    // to `0x14` (`0x100a597a`). `UScale`/`VScale` as SERIALIZED are the un-shrunk values; only the
    // walk uses these.
    let bright_corners = s.poly_flags & PF_BRIGHT_CORNERS != 0;
    let (step_u, step_v) = if bright_corners {
        (bright_corners_step(u_scale, u_size), bright_corners_step(v_scale, v_size))
    } else {
        (u_scale, v_scale)
    };
    let extra_flags = if bright_corners { VIS_BRIGHT_CORNERS } else { VIS_EXTRA_FLAGS };

    // Surf centroid + radius for a coarse per-light cull (skip lights that can't reach any lumel).
    let mut centroid = Vec3::new(0.0, 0.0, 0.0);
    for v in verts {
        centroid = Vec3::new(centroid.x + v.x, centroid.y + v.y, centroid.z + v.z);
    }
    let inv_n = 1.0 / verts.len() as f32;
    centroid = Vec3::new(centroid.x * inv_n, centroid.y * inv_n, centroid.z * inv_n);

    let row_bytes = (u_size as usize + 7) / 8;
    let mut light_indices: Vec<i32> = Vec::new();
    let mut bits: Vec<u8> = Vec::new();

    let surf_special = s.poly_flags & PF_SPECIAL_LIT != 0;
    let Some((u_dir, v_dir)) = axes else {
        // No basis, no grid to walk: the surface still gets its (dark) record.
        return Some(SurfBake { surf_index: si, rec: descriptor(u_size, v_size, u_scale, v_scale,
                                                              pan_x, pan_y),
                               light_indices, bits });
    };

    // Reach for the coarse per-light cull, measured from the GRID's four corners, not the surface's
    // vertices: the grid is the texture-space BOUNDING BOX, so on a triangle its corner sits well
    // outside the vertex hull (a right triangle 100x100 puts it 16 uu past the farthest vertex,
    // against only 4 uu of `SELF_SHADOW_BIAS` slack). Culling on the vertex hull would drop a light
    // that reaches a real in-grid lumel and silently change the stored bits.
    let grid_origin = add(&add(&base, &scaled(&u_dir, pan_x)), &scaled(&v_dir, pan_y));
    let span_u = scaled(&u_dir, u_scale * (u_size - 1) as f32);
    let span_v = scaled(&v_dir, v_scale * (v_size - 1) as f32);
    let mut surf_reach = 0.0f32;
    for corner in [grid_origin, add(&grid_origin, &span_u), add(&grid_origin, &span_v),
                   add(&add(&grid_origin, &span_u), &span_v)] {
        surf_reach = surf_reach.max(corner.sub(&centroid).size());
    }

    for (li, l) in lights.iter().enumerate() {
        // `bSpecialLit` partitions light and surface into two disjoint sets (see `LightInput`).
        if l.special_lit != surf_special {
            continue;
        }
        // Backface cull: a light behind this surface's plane never lights its front face (editor
        // parity — see `light_in_front`). Cheapest possible test, so do it first.
        if !light_in_front(&normal, &base, &l.location, s.poly_flags) {
            continue;
        }
        let wr = l.world_radius();
        // Coarse cull: if even the nearest possible lumel is out of range, this light can't reach.
        // Widen the surf's reach by the self-shadow bias so a light just past an edge lumel (whose
        // ray origin is pushed +Normal*bias) is never culled prematurely.
        if centroid.sub(&l.location).size() - (surf_reach + SELF_SHADOW_BIAS) > wr {
            continue;
        }
        let wr2 = wr * wr;
        let mut plane = vec![0u8; row_bytes * v_size as usize];
        let mut any_lit = false;
        // The grid origin is rebuilt per light exactly as the editor rebuilds it (`0x100a5610`), and
        // the self-shadow bias is applied ONCE here, to the origin, not per lumel (`0x100a54f0`).
        let mut row_origin = add(
            &add(&add(&base, &scaled(&normal, SELF_SHADOW_BIAS)), &scaled(&u_dir, pan_x)),
            &scaled(&v_dir, pan_y));
        if bright_corners {
            row_origin = add(&add(&row_origin, &scaled(&v_dir, 0.25)), &scaled(&u_dir, 0.25));
        }
        let u_step = scaled(&u_dir, step_u);
        let v_step = scaled(&v_dir, step_v);
        // The editor keeps the LAST `LineCheck` result across lumels and uses it to fill the row's
        // trailing padding bits (below). It is only refreshed when a ray actually runs, so a
        // radius-rejected lumel leaves it standing.
        let mut last_clear = false;
        for v in 0..v_size {
            let mut p = row_origin;
            for byte in 0..row_bytes {
                let mut acc = 0u8;
                let first = byte as i32 * 8;
                for bit in 0..8u32 {
                    if first + bit as i32 >= u_size {
                        acc |= row_padding(u_size, last_clear);   // see the fn
                        break;
                    }
                    let d = p.sub(&l.location);
                    if d.dot(&d) < wr2 {
                        last_clear = line_clear(model, p, l.location, extra_flags);
                        if last_clear {
                            acc |= 1u8 << bit; // LSB-first within the row byte (§3)
                            any_lit = true;
                        }
                    }
                    p = add(&p, &u_step); // advances even when the radius test rejected
                }
                plane[v as usize * row_bytes + byte] = acc;
            }
            row_origin = add(&row_origin, &v_step);
        }
        if any_lit {
            light_indices.push(li as i32);
            bits.extend_from_slice(&plane);
        }
    }

    let rec = descriptor(u_size, v_size, u_scale, v_scale, pan_x, pan_y);
    Some(SurfBake {
        surf_index: si,
        rec,
        light_indices,
        bits,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;

    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> BrushInput {
        let c = |sx: f32, sy: f32, sz: f32| Vec3::new(sx * hx, sy * hy, sz * hz);
        let faces = [
            (
                Vec3::new(1.0, 0.0, 0.0),
                [
                    c(1.0, -1.0, -1.0),
                    c(1.0, 1.0, -1.0),
                    c(1.0, 1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                ],
            ),
            (
                Vec3::new(-1.0, 0.0, 0.0),
                [
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, -1.0, -1.0),
                    c(-1.0, -1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 1.0, 0.0),
                [
                    c(1.0, 1.0, -1.0),
                    c(-1.0, 1.0, -1.0),
                    c(-1.0, 1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, -1.0, 0.0),
                [
                    c(-1.0, -1.0, -1.0),
                    c(1.0, -1.0, -1.0),
                    c(1.0, -1.0, 1.0),
                    c(-1.0, -1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 0.0, 1.0),
                [
                    c(-1.0, -1.0, 1.0),
                    c(1.0, -1.0, 1.0),
                    c(1.0, 1.0, 1.0),
                    c(-1.0, 1.0, 1.0),
                ],
            ),
            (
                Vec3::new(0.0, 0.0, -1.0),
                [
                    c(-1.0, 1.0, -1.0),
                    c(1.0, 1.0, -1.0),
                    c(1.0, -1.0, -1.0),
                    c(-1.0, -1.0, -1.0),
                ],
            ),
        ];
        let mut polys = Vec::new();
        for (n, verts) in faces {
            let mut p = FPoly::new(verts.to_vec());
            p.normal = n;
            polys.push(p);
        }
        BrushInput {
            polys,
            oper,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
        }
    }

    #[test]
    fn axis_grid_matches_editor_ceil_rule() {
        // Pin the editor's lumel grid-sizing rule as fitted against its own LIGHT APPLY output:
        // size = clamp(ceil((extent - 0.25)/scale), 2, 256); scale = (extent + 0.25)/(size-1);
        // pan = min - 0.125.  See `axis_grid`'s doc comment for the two rejected forms and their
        // measured cost on the UNATCO oracle.
        let cases = [
            // (vmin, vmax, lumel_scale) => (size, scale, pan)
            (0.0f32, 64.0f32, 32.0f32, 2, 64.25f32),     // EXACT multiple: no extra texel
            (0.0, 80.0, 32.0, 3, 80.25 / 2.0),           // non-multiple rounds up
            (0.0, 1024.0, 32.0, 32, 1024.25 / 31.0),     // EXACT multiple: 32, NOT 33
            (0.0, 16.0, 32.0, 2, 16.25),                 // below one lumel -> clamp to min 2
            (-500.0, 500.0, 32.0, 32, 1000.25 / 31.0),   // 31.24 -> 32
            // TEETH for the -0.25: an extent just ABOVE an exact multiple must NOT take the extra
            // texel. `ceil(extent/scale)` gives 6 here; the editor stores 5 (UNATCO surf 7).
            (0.0, 160.001831, 32.0, 5, (160.001831f32 + 0.25) / 4.0),
            // Same shape at HighShadowDetail's 16 uu (UNATCO surf 20): ceil(58.00001) would be 59.
            (0.0, 928.000122, 16.0, 58, (928.000122f32 + 0.25) / 57.0),
        ];
        for (vmin, vmax, sc, want_size, want_scale) in cases {
            let (size, scale, pan) = axis_grid(vmin, vmax, sc);
            assert_eq!(size, want_size, "grid size for extent {}", vmax - vmin);
            assert_eq!(scale, want_scale, "scale (extent+0.25)/(size-1)");
            assert_eq!(pan, vmin - 0.125, "pan = min - 0.125");
        }
    }

    #[test]
    fn single_room_light_fully_lights_all_walls() {
        // A room ±256 X/Y, ±128 Z with one bright light at the centre.  All 6 walls are within
        // radius and have clear LOS from every lumel -> every surf gets a lit record; the internal
        // linkage is consistent.
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        // radius 40 -> world radius (40+1)*25 = 1025 units, easily covers the room.
        bake(
            &mut m,
            &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 40,
                special_lit: false,
            }],
        )
        .unwrap();

        assert_eq!(m.light_map.len(), 6, "all 6 room walls lightmapped");
        for (i, s) in m.surfs.iter().enumerate() {
            assert_eq!(
                s.i_light_map, i as i32,
                "surf {i} links its record in order"
            );
        }
        // Every record is lit (1 light run) and its byte span matches N*ceil(U/8)*V (§3).
        let mut total_bits = 0usize;
        for rec in &m.light_map {
            assert!(rec.i_light_actors >= 0, "lit record has a light run");
            let run_start = rec.i_light_actors as usize;
            // run is [light_idx.., -1]; exactly one light (index 0) then terminator.
            assert_eq!(m.lights[run_start], 0, "the single light's index");
            assert_eq!(m.lights[run_start + 1], -1, "NULL terminator");
            let n = 1usize;
            let row_bytes = (rec.u_size as usize + 7) / 8;
            total_bits += n * row_bytes * rec.v_size as usize;
        }
        assert_eq!(
            total_bits,
            m.light_bits.len(),
            "light_bits length == sum of N*ceil(U/8)*V over records (§3)"
        );
        // At least one lumel is actually lit (non-black).
        assert!(m.light_bits.iter().any(|&b| b != 0), "some lumel is lit");
    }

    #[test]
    fn lightmap_skip_mask_matches_editor_disasm() {
        // The editor's allocate-meshes pass (`Editor 0x100a6031`) gates lightmap allocation with
        // `test [surf+0x1b0], 0x400081`. Pin that exact mask so a later "tidy-up" can't silently
        // re-add PF_Portal (which wrongly culls the two-sided water portals — spike §20 §21).
        assert_eq!(PF_NO_LIGHTMAP, 0x0040_0081, "editor lightmap-skip mask");
        // PF_Portal must NOT be in it (the oracle Test_Castle.dx lightmaps its 4 portal sheets).
        const PF_PORTAL: u32 = 0x0400_0000;
        assert_eq!(PF_NO_LIGHTMAP & PF_PORTAL, 0, "PF_Portal is lightmapped, not skipped");
    }

    #[test]
    fn bright_corners_changes_the_walk_but_not_the_stored_descriptor() {
        // `PF_BrightCorners` insets the SAMPLE grid (`bright_corners_step` + the origin's `+0.25`)
        // and raises the shadow ray's `ExtraNodeFlags` to 0x14, but the descriptor that goes on disk
        // keeps the un-shrunk `UScale`/`VScale`. Writing the shrunk value instead would move
        // `u_scale` on every one of these surfaces, which the oracle shows it must not.
        assert_eq!(bright_corners_step(32.0, 9), (32.0f64 - 0.5 / 8.0) as f32);
        assert_eq!(bright_corners_step(16.25, 2), (16.25f64 - 0.5) as f32);
        assert_eq!(VIS_BRIGHT_CORNERS, 0x14, "the editor pushes 0x14 for these surfaces");

        let stored = |flags: u32| {
            let mut b = box_brush(256.0, 256.0, 140.0, Vec3::new(0.0, 0.0, 0.0),
                                  CsgOper::Subtract);
            b.poly_flags = flags;
            let mut m = build_geometry_from_brushes(&[b]).unwrap();
            bake(&mut m, &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 40,
                special_lit: false,
            }]).unwrap();
            m.light_map.iter().map(|r| (r.u_size, r.v_size, r.u_scale, r.v_scale))
                .collect::<Vec<_>>()
        };
        assert_eq!(stored(PF_BRIGHT_CORNERS), stored(0),
                   "PF_BrightCorners must not change the stored grid descriptor");
    }

    #[test]
    fn special_lit_partitions_lights_and_surfaces() {
        // `bSpecialLit` is a PARTITION, not an extra permission (`Editor 0x100a4ea0`): a
        // `bSpecialLit` light lights ONLY `PF_SpecialLit` surfaces, and a plain light lights ONLY
        // surfaces without the flag. Getting this wrong is not subtle at real scale — before the
        // fix, one UNATCO light was listed on 130 surfaces it must never touch.
        //
        // Two rooms, both with a light at their centre: one carved by a brush whose faces carry
        // `PF_SpecialLit`, one plain. A plain light must light every plain wall and no special one;
        // a `bSpecialLit` light must do the reverse.
        let rooms = |special_flags: u32| {
            let mut b = box_brush(256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract);
            b.poly_flags = special_flags;
            build_geometry_from_brushes(&[b]).unwrap()
        };
        for (surf_flags, light_special, want_lit) in [
            (0u32, false, true),                  // plain light, plain surf   -> lit
            (0, true, false),                     // special light, plain surf -> never
            (PF_SPECIAL_LIT, false, false),       // plain light, special surf -> never
            (PF_SPECIAL_LIT, true, true),         // special light, special surf -> lit
        ] {
            let mut m = rooms(surf_flags);
            bake(&mut m, &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 40,
                special_lit: light_special,
            }]).unwrap();
            assert_eq!(m.light_map.len(), 6, "all 6 walls still get a record either way");
            let lit = m.light_map.iter().any(|r| r.i_light_actors >= 0);
            assert_eq!(lit, want_lit,
                       "surf_flags={surf_flags:#x} light.special_lit={light_special}");
        }
    }

    #[test]
    fn a_row_is_packed_to_its_last_whole_byte() {
        // The editor's packer fills the row's final byte, tracing the lumels ABOVE `USize` rather
        // than leaving them zero — measured on its own UNATCO output, 40% of those padding bits are
        // SET. The game masks to `USize` on read, so this is invisible in play and purely a
        // byte-identity concern; it moved 2026 of 3345 records from differing to identical.
        //
        // Two overlapping subtracts make one long open space whose floor and ceiling the BSP splits
        // into fragments. A fragment's lumel grid is the bounding box of that fragment in texture
        // space, so its padding columns extrapolate over the NEIGHBOURING fragment — open space with
        // clear line of sight to the light. Those bits come out 1 when the padding is traced and 0
        // when it is zero-filled, so a single set padding bit anywhere proves the rule. (A lone room
        // cannot show it: every padding column of a wall lies inside the surrounding solid.)
        for (u_size, last_clear, want) in [
            (9, true, 0b1111_1110u8),   // 1 bit used in the last byte -> 7 padding bits set
            (9, false, 0),
            (15, true, 0b1000_0000),    // 7 used -> 1 padding bit
            (16, true, 0),              // whole bytes -> no padding at all
            (2, true, 0b1111_1100),
        ] {
            assert_eq!(row_padding(u_size, last_clear), want,
                       "padding for USize {u_size}, last_clear {last_clear}");
        }
        // And that the bake USES it. A `PF_BrightCorners` room is the fixture that can show it: the
        // 0.25 inset pulls the grid's last column INSIDE the polygon, so the row's last real lumel is
        // lit and the padding bits follow. Without the inset (a plain room) that column sits 0.125
        // outside the surface, its biased ray starts in the surrounding solid, and every padding bit
        // is legitimately 0 — which is also why 60% of the editor's own padding bits are 0.
        let padding_bits = |flags: u32| {
            let mut b = box_brush(500.0, 500.0, 140.0, Vec3::new(0.0, 0.0, 0.0),
                                  CsgOper::Subtract);
            b.poly_flags = flags;
            let mut m = build_geometry_from_brushes(&[b]).unwrap();
            bake(&mut m, &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 80,
                special_lit: false,
            }]).unwrap();
            let mut set = 0usize;
            let mut positions = 0usize;
            let mut total = 0usize;
            for rec in &m.light_map {
                let row_bytes = (rec.u_size as usize + 7) / 8;
                if rec.i_light_actors >= 0 {
                    total += row_bytes * rec.v_size as usize;
                }
                if rec.u_size % 8 == 0 || rec.i_light_actors < 0 {
                    continue;
                }
                for v in 0..rec.v_size as usize {
                    let last = m.light_bits[rec.data_offset as usize + v * row_bytes + row_bytes - 1];
                    for u in rec.u_size as usize..row_bytes * 8 {
                        positions += 1;
                        set += (last >> (u & 7) & 1) as usize;
                    }
                }
            }
            assert!(positions > 0, "no record with a partial last byte");
            assert_eq!(total, m.light_bits.len(),
                       "LightBits is not the sum of ceil(U/8)*V over the lit records");
            set
        };
        assert_eq!(padding_bits(0), 0, "a plain room's padding columns are all in solid");
        assert!(padding_bits(PF_BRIGHT_CORNERS) > 0,
                "with the BrightCorners inset the last real lumel is lit, so its row's padding bits \
                 must be set — a zero-fill would leave them 0");
    }

    #[test]
    fn a_grid_over_256_lumels_doubles_the_lumel_scale() {
        // The editor does not clamp at 256: it doubles the lumel scale and recomputes the axis
        // (`0x100a5dba`), so an oversized surface gets a coarser grid AND a different texel scale.
        // Clamping instead would ship a 256-lumel grid whose scale does not span the surface.
        // 20000 uu at the default 32 uu scale wants 625 lumels -> 64 -> 313 -> 128 -> 157.
        let (size, scale, pan) = axis_grid(0.0, 20000.0, 32.0);
        assert_eq!(size, 157);
        assert_eq!(scale, ((20000.0f64 + 0.25) / 156.0) as f32);
        assert_eq!(pan, -0.125);
        assert!(size <= 256);
        // One doubling is enough here, and the scale it lands on is 64, not 32.
        assert_eq!(axis_grid(0.0, 10000.0, 32.0).0, 157);
    }

    #[test]
    fn light_in_front_matches_plane_side() {
        // A wall at x=+256 whose front face looks back into the room (inward normal -X), so a light
        // at x < 256 is in front of it and PlaneDot = 256 - x.
        let normal = Vec3::new(-1.0, 0.0, 0.0);
        let base = Vec3::new(256.0, 0.0, 0.0);
        let at = |x: f32, pf: u32| light_in_front(&normal, &base, &Vec3::new(x, 50.0, 50.0), pf);

        assert!(at(0.0, 0), "a light inside the room is in front");
        assert!(at(256.0, 0), "a light ON the plane is kept -- the test is >= -1, not > 0");
        // The tolerance is exactly one world unit behind the plane, from `render.dll 0x100198c7`'s
        // `PlaneDot < -1.0f`. A strict sign test here would drop the 256.5 case.
        assert!(at(256.5, 0), "half a unit behind the plane is still kept");
        assert!(at(257.0, 0), "exactly one unit behind is kept (the compare is strict <)");
        assert!(!at(257.5, 0), "past one unit behind, a single-sided surface drops the light");
        assert!(!at(400.0, 0));
        // A two-sided or portal surface renders its one lightmap from BOTH faces, so it is never
        // back-face culled however far behind the light sits.
        for pf in [PF_TWO_SIDED, PF_PORTAL, PF_TWO_SIDED | PF_PORTAL] {
            assert!(at(4000.0, pf), "PolyFlags {pf:#x} must exempt the surface from the cull");
        }
    }

    #[test]
    fn out_of_room_light_is_never_listed() {
        // Room ±256/±256/±128 with a light placed FAR outside the box. No surface may list it:
        // every record must be DARK (iLightActors == -1). NOTE: this is an out-of-range/occlusion
        // invariant, NOT an isolated backface-cull test — the coarse radius cull alone already
        // excludes a light this far away. The backface cull cannot be isolated at the bake() level
        // in watertight geometry (clear LOS to a front face from behind its plane is geometrically
        // impossible, so backface and LOS coincide there); the plane-side predicate itself is
        // guarded directly by `light_in_front_matches_plane_side`, and the real-world effect by the
        // in-game A/B in section 20 §17. The cull matters only against our leaky non-portalized LOS.
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        bake(
            &mut m,
            &[LightInput {
                location: Vec3::new(100000.0, 0.0, 0.0),
                radius: 255,
                special_lit: false, // world radius (255+1)*25 = 6400, still < 100000 -> also out of range
            }],
        )
        .unwrap();
        assert_eq!(m.light_map.len(), 6);
        for rec in &m.light_map {
            assert_eq!(
                rec.i_light_actors, -1,
                "an out-of-room light must not appear in any wall's list"
            );
        }
        assert!(m.light_bits.is_empty(), "no lit bits for an unreachable light");
    }

    #[test]
    fn corrupt_index_returns_builderror_not_panic() {
        // A hand-corrupted Model (surf vNormal out of range) must yield a clean BuildError, never
        // a panic (which would cross the FFI as a PanicException — repo rule forbids that).
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        m.surfs[0].v_normal = 9999; // out of range
        let err = bake(
            &mut m,
            &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 40,
                special_lit: false,
            }],
        );
        assert!(
            err.is_err(),
            "corrupt geometry index must be a BuildError, not a panic"
        );
    }

    #[test]
    fn no_lights_leaves_all_surfs_unlinked_but_records_dark() {
        let mut m = build_geometry_from_brushes(&[box_brush(
            256.0,
            256.0,
            128.0,
            Vec3::new(0.0, 0.0, 0.0),
            CsgOper::Subtract,
        )])
        .unwrap();
        bake(&mut m, &[]).unwrap();
        // Every lightmappable surf still gets a (dark) record, but no bits / no light runs.
        assert_eq!(m.light_map.len(), 6);
        assert!(m.light_bits.is_empty());
        assert!(m.lights.is_empty());
        for rec in &m.light_map {
            assert_eq!(rec.i_light_actors, -1, "dark record");
            assert_eq!(rec.data_offset, 0);
        }
    }

    /// Independent reference BSP walk (a hand-rolled duplicate of `lightmap_emit_order`'s rule),
    /// used to pin that `bake` emits `LightMap` in editor **tree-walk** order, not surf-index order.
    fn reference_walk(m: &Model) -> Vec<usize> {
        fn rec(m: &Model, mut ni: i32, seen: &mut [bool], out: &mut Vec<usize>) {
            while ni >= 0 {
                let n = &m.nodes[ni as usize];
                if n.i_surf >= 0 {
                    let s = n.i_surf as usize;
                    if !seen[s] {
                        seen[s] = true;
                        if m.surfs[s].poly_flags & PF_NO_LIGHTMAP == 0 {
                            out.push(s);
                        }
                    }
                }
                rec(m, n.i_back, seen, out);
                rec(m, n.i_front, seen, out);
                ni = n.i_plane;
            }
        }
        let mut out = Vec::new();
        let mut seen = vec![false; m.surfs.len()];
        if !m.nodes.is_empty() {
            rec(m, 0, &mut seen, &mut out);
        }
        out
    }

    #[test]
    fn lightmap_array_is_in_bsp_walk_order_not_surf_order() {
        // Two subtracts carving an L-shaped space give a non-trivial BSP tree whose lightmap
        // allocation order (editor tree-walk) differs from naive surf-index order. This pins the
        // §21 fix: the editor's `LightMap` array follows the BSP node walk (visit surf, recurse
        // back, recurse front, step the iPlane coplanar chain), NOT surf order — verified
        // byte-exact against `Test_Castle.dx`. Emitting in walk order is what aligns `LightMap`,
        // `LightBits`, and the per-surf `Lights` region-2 runs positionally with UnrealEd.
        let mut m = build_geometry_from_brushes(&[
            box_brush(256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(128.0, 128.0, 64.0, Vec3::new(200.0, 200.0, 0.0), CsgOper::Subtract),
        ])
        .unwrap();
        bake(
            &mut m,
            &[LightInput {
                location: Vec3::new(0.0, 0.0, 0.0),
                radius: 40,
                special_lit: false,
            }],
        )
        .unwrap();

        // Recover record -> surf from the surf links, then assert it equals the independent walk.
        let mut rec2surf = vec![usize::MAX; m.light_map.len()];
        for (si, s) in m.surfs.iter().enumerate() {
            if s.i_light_map >= 0 {
                rec2surf[s.i_light_map as usize] = si;
            }
        }
        assert!(
            rec2surf.iter().all(|&v| v != usize::MAX),
            "every record is linked by exactly one surf"
        );
        let want = reference_walk(&m);
        assert_eq!(
            rec2surf, want,
            "LightMap array must be emitted in BSP tree-walk order (§20 §21)"
        );
        // Teeth: this two-subtract geometry actually REORDERS — the walk is NOT surf-ascending — so
        // a regression to plain surf-index emission (`rec2surf == [0,1,2,…]`) would be caught here,
        // not silently pass. (The byte-exact teeth on the real map live in the spike: on
        // `Test_Castle.dx` the walk reproduces the editor's `[102, 324, 267, 191, 17, …]`, §20 §21.)
        let ascending: Vec<usize> = (0..rec2surf.len()).collect();
        assert_ne!(
            rec2surf, ascending,
            "test geometry must exercise walk!=surf order, else it cannot catch a regression"
        );
    }
}
