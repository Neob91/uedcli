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

use crate::linecheck::line_clear;
use crate::model::{BuildError, LightMapIndex, Model, Vec3};
use rayon::prelude::*;

// PolyFlags (canonical UE1 EPolyFlags).
const PF_INVISIBLE: u32 = 0x0000_0001;
const PF_FAKE_BACKDROP: u32 = 0x0000_0080;
const PF_LOW_SHADOW_DETAIL: u32 = 0x0000_8000;
const PF_UNLIT: u32 = 0x0040_0000;
const PF_HIGH_SHADOW_DETAIL: u32 = 0x0080_0000;
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

/// Backface cull (editor parity): a light BEHIND a surface's plane never lights its front face.
/// `shadowIlluminateBsp`'s gather pass (`Editor 0xa4ba0`) asks the renderer which surfaces each
/// light "sees" (disasm shows it delegates to renderer-visibility vtable calls); **measured on the
/// editor oracle `Test_Castle.dx`, the result contains 0 of 3497 back-facing (surf, light) entries**
/// — so the editor keeps only front-side lights. Our old bake had **2586 of 5486 (47%)** back-facing,
/// and those spurious back-side lights flooded every surface with dim contributions, flattening the
/// render's contrast/falloff vs the editor (measured 2026-07-17; see section 20 §17).
///
/// A light is in front iff its signed offset along the surface normal is positive. Only the SIGN is
/// used, so this is robust to a non-unit `normal`, and any point on the plane works for `base`
/// (`pBase` lies on it by construction). Strict `> 0`: a coplanar light grazes at zero contribution
/// and the oracle shows no light closer than +1.96, so `> 0` vs `>= 0` is empirically indistinguishable.
///
/// Why native needs this when the editor's per-lumel LOS ray would also cull a back light: clear
/// line-of-sight to a surface's FRONT face is geometrically impossible from behind its plane, so for
/// *correct* geometry backface and LOS coincide and the cull looks redundant. But our native LOS
/// (`linecheck::line_clear`) leaks through the not-yet-fully-portalized BSP, so back-side lights slip
/// past the ray test. This cheap plane-side pre-filter is the robust guard the editor relies on.
///
/// ⚠️ Assumes single-sided surfaces (true for every lightmapped surf here). A `PF_TwoSided` sheet
/// renders its one lightmap from BOTH faces, so the editor could legitimately list a back-side light
/// on it; this strict cull would drop it. `Test_Castle` has no such case (0/3497), so it is a latent
/// generic-UE1 gap tracked in `board/inbox/`, not a regression on the castle.
#[inline]
fn light_in_front(normal: &Vec3, base: &Vec3, light: &Vec3) -> bool {
    light.sub(base).dot(normal) > 0.0
}

/// One participating light (the bake reads only Location + radius — §5).  `LightType != LT_None`
/// filtering happens caller-side; every light passed here participates.
#[derive(Debug, Clone, Copy)]
pub struct LightInput {
    pub location: Vec3,
    /// `LightRadius` BYTE (actor+0x1a1).  World radius = `(radius + 1) × 25` (§5.1).
    pub radius: u8,
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
/// The editor's lumel grid dimension is **`Clamp = ceil(extent / lumel_scale)`, clamped to
/// `[2, 256]`** — decoded byte-exact from the golden `Test_Castle.dx`: predicting each of the 484
/// records' stored `UClamp`/`VClamp` from that record's own surf extent reproduces all 484×2 grid
/// dims exactly (spike §20 §22, `harness/lightmap_grid_diff.py`).  An **exact multiple** of the
/// lumel scale (e.g. extent 64 at scale 32, or 1024 at 32) gives `extent/scale` with **no** extra
/// texel (`ceil(2.0)=2`, `ceil(32.0)=32`); a non-integer rounds **up** (`ceil(2.5)=3`).  The old
/// `trunc((extent-0.25)/scale - 0.5) + 1` under-counted every non-multiple by 1 (134 of 484 records
/// off by −1), which then shifted the whole downstream `LightBits` blob (each record's on-disk bit
/// length is `⌈UClamp/8⌉·VClamp`).
///
/// The texel **scale** is `(extent + 0.25) / (size - 1)`: the grid spans `[min-0.125, max+0.125]`
/// (a half-lumel pad each side, matching `Pan = min - 0.125`), so `(size-1)` steps cover
/// `extent + 0.25`.  Verified byte-exact on the golden's `TextureUScale`/`TextureVScale` floats.
fn axis_grid(vmin: f32, vmax: f32, scale: f32) -> (i32, f32, f32) {
    let extent = vmax - vmin;
    // Clamp on the INTEGER after the saturating f32->i32 cast (identical to the editor on every
    // finite in-range extent, but robust at the edges: an absurd extent saturates to i32::MAX then
    // clamps to 256, and a NaN coord casts to 0 then clamps to the min 2 — so `size - 1` below is
    // always in [1, 255] and can never be 0 or negative).
    let size = ((extent / scale).ceil() as i32).clamp(2, 256);
    let uscale = (extent + 0.25) / (size - 1) as f32;
    let pan = vmin - 0.125;
    (size, uscale, pan)
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

/// Solve for the world point on the surface plane at texture coords `(tex_u, tex_v)`: the 3×3
/// inverse of `[TextureU; TextureV; Normal]` applied to `(tex_u, tex_v, Base·Normal)` (§6).
/// Returns `None` for a degenerate basis (caller falls back to the surf base point).
///
/// `tex_u`/`tex_v` are the **world-space** projections `P·TextureU`/`P·TextureV` (the stored,
/// base-relative Pan is converted back to world by the caller adding `Base·TextureU/V` before
/// calling — see `bake_surf`).
fn lumel_world(
    tu: Vec3,
    tv: Vec3,
    normal: Vec3,
    base_dot_n: f32,
    tex_u: f32,
    tex_v: f32,
) -> Option<Vec3> {
    // Rows r0=tu, r1=tv, r2=normal.  A^-1 columns are (r1×r2, r2×r0, r0×r1)/det; det = r0·(r1×r2).
    let c0 = tv.cross(&normal);
    let det = tu.dot(&c0);
    if det.abs() < 1e-8 {
        return None;
    }
    let c1 = normal.cross(&tu);
    let c2 = tu.cross(&tv);
    let inv = 1.0 / det;
    // P = (tex_u * c0 + tex_v * c1 + base_dot_n * c2) / det.
    Some(Vec3::new(
        (tex_u * c0.x + tex_v * c1.x + base_dot_n * c2.x) * inv,
        (tex_u * c0.y + tex_v * c1.y + base_dot_n * c2.y) * inv,
        (tex_u * c0.z + tex_v * c1.z + base_dot_n * c2.z) * inv,
    ))
}

/// Validate that every geometry index the bake dereferences is in range, so the bake can index
/// with `as usize` without panicking (a panic would cross the FFI boundary as a `PanicException`,
/// not the contracted `BuildError` — repo rule: no bare traceback reaches the user).  A well-formed
/// `build_geometry` output always passes; this only fires on a corrupt/hand-built Model.
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
    let base_dot_n = base.dot(&normal);
    // The lightmap texture frame is BASE-RELATIVE: coordinates are `(vert - Base)·TextureU/V`, i.e.
    // world dots offset by the surf base's own projection.  The editor stores Pan in this frame
    // (`Pan = min(vert-Base)·Tex - 0.125`, verified field-for-field vs Test_Castle.dx 2026-07-16) —
    // NOT the raw world dot (spike §4's "raw dot" note was WRONG).  Using raw world dots put Pan at
    // world coords (e.g. -1150) while the renderer samples in the base-relative frame, so every
    // world point landed far outside the tiny lumel grid → out-of-bounds lightmap reads smeared all
    // the colored lights into a rainbow.  Subtract the base projection so Pan is small & local.
    let base_u = base.dot(&tu);
    let base_v = base.dot(&tv);

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

    // Surf centroid + radius for a coarse per-light cull (skip lights that can't reach any lumel).
    let mut centroid = Vec3::new(0.0, 0.0, 0.0);
    for v in verts {
        centroid = Vec3::new(centroid.x + v.x, centroid.y + v.y, centroid.z + v.z);
    }
    let inv_n = 1.0 / verts.len() as f32;
    centroid = Vec3::new(centroid.x * inv_n, centroid.y * inv_n, centroid.z * inv_n);
    let mut surf_reach = 0.0f32;
    for v in verts {
        surf_reach = surf_reach.max(v.sub(&centroid).size());
    }

    let row_bytes = (u_size as usize + 7) / 8;
    let mut light_indices: Vec<i32> = Vec::new();
    let mut bits: Vec<u8> = Vec::new();

    for (li, l) in lights.iter().enumerate() {
        // Backface cull: a light behind this surface's plane never lights its front face (editor
        // parity — see `light_in_front`). Cheapest possible test, so do it first.
        if !light_in_front(&normal, &base, &l.location) {
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
        for v in 0..v_size {
            // pan_y + v*v_scale is base-relative; add base_v to get the world-space P·TextureV.
            let tex_v = pan_y + v as f32 * v_scale + base_v;
            for u in 0..u_size {
                let tex_u = pan_x + u as f32 * u_scale + base_u;
                let p0 = lumel_world(tu, tv, normal, base_dot_n, tex_u, tex_v).unwrap_or(base);
                let p = Vec3::new(
                    p0.x + normal.x * SELF_SHADOW_BIAS,
                    p0.y + normal.y * SELF_SHADOW_BIAS,
                    p0.z + normal.z * SELF_SHADOW_BIAS,
                );
                let d2 = p.sub(&l.location).dot(&p.sub(&l.location));
                if wr2 <= d2 {
                    continue; // out of range -> dark lumel
                }
                if line_clear(model, p, l.location) {
                    let idx = (v as usize) * row_bytes + (u as usize >> 3);
                    plane[idx] |= 1u8 << (u & 7); // LSB-first within the row byte (§3)
                    any_lit = true;
                }
            }
        }
        if any_lit {
            light_indices.push(li as i32);
            bits.extend_from_slice(&plane);
        }
    }

    let rec = LightMapIndex {
        data_offset: 0,     // filled at concat
        i_light_actors: -1, // filled at concat
        pan: Vec3::new(pan_x, pan_y, 0.0),
        u_scale,
        v_scale,
        u_size,
        v_size,
    };
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
        // Pin the editor's lumel grid-sizing rule decoded byte-exact from the golden Test_Castle.dx
        // (spike §20 §22, harness/lightmap_grid_diff.py): size = clamp(ceil(extent/scale), 2, 256);
        // scale = (extent + 0.25)/(size-1); pan = min - 0.125.  A regression to the old
        // trunc((extent-0.25)/scale - 0.5)+1 form would trip here.
        let cases = [
            // (vmin, vmax, lumel_scale) => (size, scale, pan)
            (0.0f32, 64.0f32, 32.0f32, 2, 64.25f32),     // EXACT multiple: ceil(2.0)=2, NOT 3
            (0.0, 80.0, 32.0, 3, 80.25 / 2.0),           // 2.5 -> 3
            (0.0, 1024.0, 32.0, 32, 1024.25 / 31.0),     // EXACT multiple: ceil(32.0)=32, NOT 33
            (0.0, 16.0, 32.0, 2, 16.25),                 // 0.5 -> clamp up to min 2
            (-500.0, 500.0, 32.0, 32, 1000.25 / 31.0),   // 31.25 -> 32
        ];
        for (vmin, vmax, sc, want_size, want_scale) in cases {
            let (size, scale, pan) = axis_grid(vmin, vmax, sc);
            assert_eq!(size, want_size, "ceil grid size for extent {}", vmax - vmin);
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
    fn light_in_front_matches_plane_side() {
        // A wall at x=+256 whose front face looks back into the room (inward normal -X).
        let normal = Vec3::new(-1.0, 0.0, 0.0);
        let base = Vec3::new(256.0, 0.0, 0.0);
        // Light inside the room (x<256) is in FRONT of the inward-facing wall.
        assert!(light_in_front(
            &normal,
            &base,
            &Vec3::new(0.0, 0.0, 0.0)
        ));
        // Light outside the wall (x>256) is BEHIND it -> must be culled.
        assert!(!light_in_front(
            &normal,
            &base,
            &Vec3::new(400.0, 0.0, 0.0)
        ));
        // Light exactly on the plane (grazing, zero contribution) is NOT front (strict >0).
        assert!(!light_in_front(
            &normal,
            &base,
            &Vec3::new(256.0, 50.0, 50.0)
        ));
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
                radius: 255, // world radius (255+1)*25 = 6400, still < 100000 -> also out of range
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
