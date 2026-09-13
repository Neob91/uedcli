//! Decode a `UMesh`/`ULodMesh` export body — the per-export bytes right after the tagged-property
//! prefix (`package_read::read_property_tags` already covers that prefix; untouched here). Faithful
//! port of `uedcli/umesh.py`'s `parse_mesh` and everything it drives (`lazy_array`, `tarray`, the
//! element decoders, `detect_vert_stride`, the `RemapAnimVerts` rebuild). Read path only — uedcli
//! never authors meshes. See `dev/docs/board/to-build/port-ue1-mesh-geometry-decode-to-rust/spec.md`.
//!
//! The oracle, same as the Python original: an export's body occupies exactly `[pos, end)`, so a
//! parse that lands anywhere else desynced somewhere upstream (a wrong field width or a missing/
//! extra array) — `parse_mesh_body` enforces that as its own final check, not a caller's job.

use crate::model::BuildError;
use crate::package_read::read_compact_index;

// ---------------------------------------------------------------- primitives (bounds-checked)

fn need(buf: &[u8], pos: usize, n: usize) -> Result<&[u8], BuildError> {
    buf.get(pos..pos + n).ok_or_else(|| {
        BuildError(format!(
            "mesh: buffer overrun at byte {pos} (need {n}, have {})",
            buf.len().saturating_sub(pos)
        ))
    })
}

fn read_u8(buf: &[u8], pos: usize) -> Result<(u8, usize), BuildError> {
    Ok((need(buf, pos, 1)?[0], pos + 1))
}
fn read_i16(buf: &[u8], pos: usize) -> Result<(i16, usize), BuildError> {
    Ok((i16::from_le_bytes(need(buf, pos, 2)?.try_into().unwrap()), pos + 2))
}
fn read_u16(buf: &[u8], pos: usize) -> Result<(u16, usize), BuildError> {
    Ok((u16::from_le_bytes(need(buf, pos, 2)?.try_into().unwrap()), pos + 2))
}
fn read_i32(buf: &[u8], pos: usize) -> Result<(i32, usize), BuildError> {
    Ok((i32::from_le_bytes(need(buf, pos, 4)?.try_into().unwrap()), pos + 4))
}
fn read_u32(buf: &[u8], pos: usize) -> Result<(u32, usize), BuildError> {
    Ok((u32::from_le_bytes(need(buf, pos, 4)?.try_into().unwrap()), pos + 4))
}
fn read_f32(buf: &[u8], pos: usize) -> Result<(f32, usize), BuildError> {
    Ok((f32::from_le_bytes(need(buf, pos, 4)?.try_into().unwrap()), pos + 4))
}

type FVec3 = (f32, f32, f32);
type Rotator = (i32, i32, i32);
type Box3 = (FVec3, FVec3, u8);
type Sphere = (FVec3, f32);
type Tri = ((u16, u16, u16), (u8, u8, u8, u8, u8, u8), u32, i32);
type AnimNotify = (f32, i64);
type AnimSeq = (i64, i64, i32, i32, f32, Vec<AnimNotify>);
type VertConnect = (i32, i32);
type Face = ((u16, u16, u16), u16);
type Wedge = (u16, u8, u8);
type Material = (u32, i32);

fn read_fvec(buf: &[u8], pos: usize) -> Result<(FVec3, usize), BuildError> {
    let (x, p) = read_f32(buf, pos)?;
    let (y, p) = read_f32(buf, p)?;
    let (z, p) = read_f32(buf, p)?;
    Ok(((x, y, z), p))
}

fn read_frotator(buf: &[u8], pos: usize) -> Result<(Rotator, usize), BuildError> {
    let (pi, p) = read_i32(buf, pos)?;
    let (ya, p) = read_i32(buf, p)?;
    let (ro, p) = read_i32(buf, p)?;
    Ok(((pi, ya, ro), p))
}

fn read_fbox(buf: &[u8], pos: usize) -> Result<(Box3, usize), BuildError> {
    let (mn, p) = read_fvec(buf, pos)?;
    let (mx, p) = read_fvec(buf, p)?;
    let (valid, p) = read_u8(buf, p)?;
    Ok(((mn, mx, valid), p))
}

fn read_fsphere(buf: &[u8], pos: usize) -> Result<(Sphere, usize), BuildError> {
    let (c, p) = read_fvec(buf, pos)?;
    let (r, p) = read_f32(buf, p)?;
    Ok(((c, r), p))
}

// ------------------------------------------------------------ mesh elements

/// Deus Ex `FMeshVert`: int16 X, Y, Z + int16 pad (8 bytes) — the licensee change.
fn mesh_vert_dx(buf: &[u8], pos: usize) -> Result<((i32, i32, i32), usize), BuildError> {
    let (x, p) = read_i16(buf, pos)?;
    let (y, p) = read_i16(buf, p)?;
    let (z, p) = read_i16(buf, p)?;
    let (_pad, p) = read_i16(buf, p)?;
    Ok(((x as i32, y as i32, z as i32), p))
}

/// Stock Unreal `FMeshVert`: one bit-packed dword, X:11 Y:11 Z:10 (signed).
fn mesh_vert_packed(buf: &[u8], pos: usize) -> Result<((i32, i32, i32), usize), BuildError> {
    let (d, p) = read_u32(buf, pos)?;
    let mut x = (d & 0x7FF) as i32;
    if x > 0x3FF {
        x -= 0x800;
    }
    let mut y = ((d >> 11) & 0x7FF) as i32;
    if y > 0x3FF {
        y -= 0x800;
    }
    let mut z = ((d >> 22) & 0x3FF) as i32;
    if z > 0x1FF {
        z -= 0x400;
    }
    Ok(((x, y, z), p))
}

/// `FMeshTri`: WORD iVertex[3]; FMeshUV Tex[3] (BYTE U,V); DWORD PolyFlags; INT TextureIndex.
fn mesh_tri(buf: &[u8], pos: usize) -> Result<(Tri, usize), BuildError> {
    let (iv0, p) = read_u16(buf, pos)?;
    let (iv1, p) = read_u16(buf, p)?;
    let (iv2, p) = read_u16(buf, p)?;
    let (u0, p) = read_u8(buf, p)?;
    let (v0, p) = read_u8(buf, p)?;
    let (u1, p) = read_u8(buf, p)?;
    let (v1, p) = read_u8(buf, p)?;
    let (u2, p) = read_u8(buf, p)?;
    let (v2, p) = read_u8(buf, p)?;
    let (flags, p) = read_u32(buf, p)?;
    let (tex, p) = read_i32(buf, p)?;
    Ok((((iv0, iv1, iv2), (u0, v0, u1, v1, u2, v2), flags, tex), p))
}

fn mesh_anim_notify(buf: &[u8], pos: usize) -> Result<(AnimNotify, usize), BuildError> {
    let (time, p) = read_f32(buf, pos)?;
    let (fname, p) = read_compact_index(buf, p)?; // FName index
    Ok(((time, fname), p))
}

/// `FMeshAnimSeq`: FName Name; FName Group; INT StartFrame; INT NumFrames;
/// TArray<FMeshAnimNotify> Notifys; FLOAT Rate.
///
/// TWO traps, both of which desync the entire body downstream:
/// 1. `Group` is a SINGLE FName, not UT's later `TArray<FName> Groups`.
/// 2. The SERIALIZED order is not the declaration order: `Notifys` comes BEFORE `Rate`.
///    Returned tuple order (name, group, start, nframes, rate, notifys) mirrors
///    `umesh.mesh_anim_seq`'s own return shape exactly — callers (e.g. `seq[1]` for `Group`) rely
///    on that position.
fn mesh_anim_seq(buf: &[u8], pos: usize) -> Result<(AnimSeq, usize), BuildError> {
    let (name, p) = read_compact_index(buf, pos)?;
    let (group, p) = read_compact_index(buf, p)?;
    let (start, p) = read_i32(buf, p)?;
    let (nframes, p) = read_i32(buf, p)?;
    let (notifys, p) = read_tarray(buf, p, mesh_anim_notify)?;
    let (rate, p) = read_f32(buf, p)?;
    Ok(((name, group, start, nframes, rate, notifys), p))
}

/// `FMeshVertConnect`: INT NumVertTriangles; INT TriangleListOffset.
fn mesh_vert_connect(buf: &[u8], pos: usize) -> Result<(VertConnect, usize), BuildError> {
    let (a, p) = read_i32(buf, pos)?;
    let (c, p) = read_i32(buf, p)?;
    Ok(((a, c), p))
}

/// `FMeshFace`: WORD iWedge[3]; WORD MaterialIndex.
fn mesh_face(buf: &[u8], pos: usize) -> Result<(Face, usize), BuildError> {
    let (w0, p) = read_u16(buf, pos)?;
    let (w1, p) = read_u16(buf, p)?;
    let (w2, p) = read_u16(buf, p)?;
    let (mat, p) = read_u16(buf, p)?;
    Ok((((w0, w1, w2), mat), p))
}

/// `FMeshWedge`: WORD iVertex; FMeshUV TexUV (BYTE U, BYTE V).
fn mesh_wedge(buf: &[u8], pos: usize) -> Result<(Wedge, usize), BuildError> {
    let (iv, p) = read_u16(buf, pos)?;
    let (u, p) = read_u8(buf, p)?;
    let (v, p) = read_u8(buf, p)?;
    Ok(((iv, u, v), p))
}

/// `FMeshMaterial`: DWORD PolyFlags; INT TextureIndex.
fn mesh_material(buf: &[u8], pos: usize) -> Result<(Material, usize), BuildError> {
    let (flags, p) = read_u32(buf, pos)?;
    let (tex, p) = read_i32(buf, p)?;
    Ok(((flags, tex), p))
}

// ------------------------------------------------------------------ generic array helpers

/// Plain `TArray<T>`: compact count, then `count` elements via `elem`.
fn read_tarray<T>(
    buf: &[u8],
    pos: usize,
    elem: impl Fn(&[u8], usize) -> Result<(T, usize), BuildError>,
) -> Result<(Vec<T>, usize), BuildError> {
    let (n, mut p) = read_compact_index(buf, pos)?;
    if !(0..=(1i64 << 24)).contains(&n) {
        return Err(BuildError(format!("implausible TArray count {n} at {p}")));
    }
    let mut out = Vec::with_capacity(n as usize);
    for _ in 0..n {
        let (v, next) = elem(buf, p)?;
        out.push(v);
        p = next;
    }
    Ok((out, p))
}

/// `TLazyArray<T>`: an `INT SkipOffset` (absolute file offset just past the element data;
/// serialized only for package version > 61), then a compact count, then the elements. The skip
/// offset is a free per-array checksum: after reading `count` elements the position MUST equal it.
fn read_lazy_array<T>(
    buf: &[u8],
    pos: usize,
    version: i32,
    elem: impl Fn(&[u8], usize) -> Result<(T, usize), BuildError>,
) -> Result<(Vec<T>, usize), BuildError> {
    let mut p = pos;
    let mut skip: Option<i32> = None;
    if version > 61 {
        let (s, next) = read_i32(buf, p)?;
        skip = Some(s);
        p = next;
    }
    let (n, next) = read_compact_index(buf, p)?;
    p = next;
    if !(0..=(1i64 << 24)).contains(&n) {
        return Err(BuildError(format!("implausible lazy-array count {n} at {p}")));
    }
    let mut out = Vec::with_capacity(n as usize);
    for _ in 0..n {
        let (v, next) = elem(buf, p)?;
        out.push(v);
        p = next;
    }
    if let Some(skip) = skip {
        if skip as i64 != p as i64 {
            return Err(BuildError(format!(
                "lazy-array skip mismatch: header says {skip}, parse ended at {p} (count={n}, delta={})",
                p as i64 - skip as i64
            )));
        }
    }
    Ok((out, p))
}

/// Vertex bytes-per-element, read off the `Verts` `TLazyArray` header without decoding anything:
/// `(skip_offset - first_element_offset) / count`. `None` for an empty array (nothing to measure)
/// or version<=61 (no skip offset serialized), so the caller falls back to `vert8_hint`. 8 = Deus
/// Ex int16 quad, 4 = stock Unreal packed dword.
fn detect_vert_stride(buf: &[u8], pos: usize, version: i32) -> Result<Option<i64>, BuildError> {
    if version <= 61 {
        return Ok(None);
    }
    let (skip, _) = read_i32(buf, pos)?;
    let (n, dp) = read_compact_index(buf, pos + 4)?;
    if n <= 0 {
        return Ok(None);
    }
    let span = skip as i64 - dp as i64;
    Ok(if span > 0 && span % n == 0 { Some(span / n) } else { None })
}

// ------------------------------------------------------------------- parser

/// One-for-one mirror of `umesh.Mesh`'s fields, minus `name`/`is_lod` (resolved Python-side before
/// this is called — `name` from the package's name table, `is_lod` from the export's class ref).
#[derive(Debug, Clone)]
pub struct RawMesh {
    pub bbox: Box3,
    pub sphere: Sphere,
    pub verts: Vec<(i32, i32, i32)>,
    pub tris: Vec<Tri>,
    pub anim_seqs: Vec<AnimSeq>,
    pub connects: Vec<VertConnect>,
    pub vert_links: Vec<i32>,
    pub textures: Vec<i64>, // signed object refs
    pub frame_verts: i32,
    pub anim_frames: i32,
    pub scale: FVec3,
    pub origin: FVec3,
    pub rot_origin: Rotator,
    pub texture_lod: Vec<f32>,
    // ULodMesh
    pub collapse_point_thus: Vec<u16>,
    pub face_level: Vec<u16>,
    pub faces: Vec<Face>,
    pub collapse_wedge_thus: Vec<u16>,
    pub wedges: Vec<Wedge>,
    pub materials: Vec<Material>,
    pub special_faces: Vec<Face>,
    pub model_verts: i32,
    pub special_verts: i32,
    pub mesh_scale_max: f32,
    pub lod_hysteresis: f32,
    pub lod_strength: f32,
    pub lod_min_verts: i32,
    pub lod_morph: f32,
    pub lod_z_displace: f32,
    pub remap_anim_verts: Vec<u16>,
    pub old_frame_verts: i32,
    pub vert_stride: i32, // 8 = Deus Ex int16 quad, 4 = stock Unreal packed dword
}

/// Decode a `Mesh`/`LodMesh` export body from `pos` (right after its tagged-property prefix) to
/// `end` (the export's declared end). Faithful port of `umesh.parse_mesh`'s body — see the module
/// doc. Returns an error naming the delta, never a panic, if the parse does not consume exactly to
/// `end`.
pub fn parse_mesh_body(
    buf: &[u8],
    pos: usize,
    end: usize,
    version: i32,
    is_lod: bool,
    vert8_hint: Option<bool>,
) -> Result<RawMesh, BuildError> {
    let mut p = pos;

    // --- UPrimitive
    let (bbox, next) = read_fbox(buf, p)?;
    p = next;
    let (sphere, next) = read_fsphere(buf, p)?;
    p = next;

    // --- UMesh
    // The vertex stride is SELF-DESCRIBING (see `detect_vert_stride`) — `vert8_hint` is only a
    // fallback for an empty `Verts` array, mirroring `parse_mesh`'s own `vert8=None` keyword.
    let stride = detect_vert_stride(buf, p, version)?;
    let vert8 = match stride {
        Some(s) => s == 8,
        None => vert8_hint
            .ok_or_else(|| BuildError("cannot determine vertex stride (empty Verts array)".to_string()))?,
    };
    let vert_stride: i32 = if vert8 { 8 } else { 4 };

    let (mut verts, next) = if vert8 {
        read_lazy_array(buf, p, version, mesh_vert_dx)?
    } else {
        read_lazy_array(buf, p, version, mesh_vert_packed)?
    };
    p = next;

    let (tris, next) = read_lazy_array(buf, p, version, mesh_tri)?;
    p = next;
    let (anim_seqs, next) = read_tarray(buf, p, mesh_anim_seq)?;
    p = next;
    let (connects, next) = read_lazy_array(buf, p, version, mesh_vert_connect)?;
    p = next;

    // UMesh re-serializes its OWN bounds INLINE here (duplicating UPrimitive's, read above) —
    // discarded, matching `umesh.parse_mesh`'s `_own_box`/`_own_sphere`.
    let (_own_box, next) = read_fbox(buf, p)?;
    p = next;
    let (_own_sphere, next) = read_fsphere(buf, p)?;
    p = next;

    let (vert_links, next) = read_lazy_array(buf, p, version, read_i32)?;
    p = next;
    let (textures, next) = read_tarray(buf, p, read_compact_index)?;
    p = next;
    let (_bboxes, next) = read_tarray(buf, p, read_fbox)?;
    p = next;
    let (_bspheres, next) = read_tarray(buf, p, read_fsphere)?;
    p = next;

    let (frame_verts, next) = read_i32(buf, p)?;
    p = next;
    let (anim_frames, next) = read_i32(buf, p)?;
    p = next;
    let (_and_flags, next) = read_u32(buf, p)?;
    p = next;
    let (_or_flags, next) = read_u32(buf, p)?;
    p = next;
    let (scale, next) = read_fvec(buf, p)?;
    p = next;
    let (origin, next) = read_fvec(buf, p)?;
    p = next;
    let (rot_origin, next) = read_frotator(buf, p)?;
    p = next;
    let (_cur_poly, next) = read_i32(buf, p)?;
    p = next;
    let (_cur_vertex, next) = read_i32(buf, p)?;
    p = next;

    let mut texture_lod: Vec<f32> = Vec::new();
    if version == 65 {
        let (_f, next) = read_f32(buf, p)?;
        p = next;
    } else if version >= 66 {
        let (tl, next) = read_tarray(buf, p, read_f32)?;
        texture_lod = tl;
        p = next;
    }

    // --- ULodMesh
    let mut collapse_point_thus: Vec<u16> = Vec::new();
    let mut face_level: Vec<u16> = Vec::new();
    let mut faces: Vec<Face> = Vec::new();
    let mut collapse_wedge_thus: Vec<u16> = Vec::new();
    let mut wedges: Vec<Wedge> = Vec::new();
    let mut materials: Vec<Material> = Vec::new();
    let mut special_faces: Vec<Face> = Vec::new();
    let mut model_verts: i32 = 0;
    let mut special_verts: i32 = 0;
    let mut mesh_scale_max: f32 = 0.0;
    let mut lod_hysteresis: f32 = 0.0;
    let mut lod_strength: f32 = 0.0;
    let mut lod_min_verts: i32 = 0;
    let mut lod_morph: f32 = 0.0;
    let mut lod_z_displace: f32 = 0.0;
    let mut remap_anim_verts: Vec<u16> = Vec::new();
    let mut old_frame_verts: i32 = 0;

    if is_lod {
        let (v, next) = read_tarray(buf, p, read_u16)?;
        collapse_point_thus = v;
        p = next;
        let (v, next) = read_tarray(buf, p, read_u16)?;
        face_level = v;
        p = next;
        let (v, next) = read_tarray(buf, p, mesh_face)?;
        faces = v;
        p = next;
        let (v, next) = read_tarray(buf, p, read_u16)?;
        collapse_wedge_thus = v;
        p = next;
        let (v, next) = read_tarray(buf, p, mesh_wedge)?;
        wedges = v;
        p = next;
        let (v, next) = read_tarray(buf, p, mesh_material)?;
        materials = v;
        p = next;
        let (v, next) = read_tarray(buf, p, mesh_face)?;
        special_faces = v;
        p = next;
        let (v, next) = read_i32(buf, p)?;
        model_verts = v;
        p = next;
        let (v, next) = read_i32(buf, p)?;
        special_verts = v;
        p = next;
        let (v, next) = read_f32(buf, p)?;
        mesh_scale_max = v;
        p = next;
        let (v, next) = read_f32(buf, p)?;
        lod_hysteresis = v;
        p = next;
        let (v, next) = read_f32(buf, p)?;
        lod_strength = v;
        p = next;
        let (v, next) = read_i32(buf, p)?;
        lod_min_verts = v;
        p = next;
        let (v, next) = read_f32(buf, p)?;
        lod_morph = v;
        p = next;
        let (v, next) = read_f32(buf, p)?;
        lod_z_displace = v;
        p = next;
        // `TArray<_WORD> RemapAnimVerts` + `INT OldFrameVerts` — present on LodMesh ONLY, empty in
        // every DX/UT retail sample, genuinely populated in original 1998 Unreal Gold content.
        let (v, next) = read_tarray(buf, p, read_u16)?;
        remap_anim_verts = v;
        p = next;
        let (v, next) = read_i32(buf, p)?;
        old_frame_verts = v;
        p = next;

        if !remap_anim_verts.is_empty() {
            // A non-empty RemapAnimVerts means Verts was serialized at the OLD per-frame stride
            // and each frame's logical vertex `k` now lives at `RemapAnimVerts[k]` within that
            // frame's OLD slice (`NewVerts[base+k] = Verts[oldBase + RemapAnimVerts[k]]`).
            if frame_verts < 0 || anim_frames < 0 || old_frame_verts < 0 {
                return Err(BuildError(format!(
                    "RemapAnimVerts rebuild: negative frame count (frame_verts={frame_verts}, \
                     anim_frames={anim_frames}, old_frame_verts={old_frame_verts})"
                )));
            }
            let new_len = anim_frames as usize * frame_verts as usize;
            if new_len > (1usize << 24) {
                return Err(BuildError(format!(
                    "RemapAnimVerts rebuild: implausible vertex count {new_len}"
                )));
            }
            let mut new_verts = vec![(0i32, 0i32, 0i32); new_len];
            for f in 0..anim_frames as usize {
                let base = frame_verts as usize * f;
                let old_base = old_frame_verts as usize * f;
                for k in 0..frame_verts as usize {
                    let remap = *remap_anim_verts.get(k).ok_or_else(|| {
                        BuildError(format!(
                            "RemapAnimVerts rebuild: index {k} exceeds RemapAnimVerts length {}",
                            remap_anim_verts.len()
                        ))
                    })? as usize;
                    let src = old_base + remap;
                    let vert = *verts.get(src).ok_or_else(|| {
                        BuildError(format!(
                            "RemapAnimVerts rebuild: source vertex {src} exceeds Verts length {}",
                            verts.len()
                        ))
                    })?;
                    new_verts[base + k] = vert;
                }
            }
            verts = new_verts;
        }
    }

    if p != end {
        return Err(BuildError(format!(
            "mesh: consumed to {p}, export ends at {end} (delta {})",
            p as i64 - end as i64
        )));
    }

    Ok(RawMesh {
        bbox,
        sphere,
        verts,
        tris,
        anim_seqs,
        connects,
        vert_links,
        textures,
        frame_verts,
        anim_frames,
        scale,
        origin,
        rot_origin,
        texture_lod,
        collapse_point_thus,
        face_level,
        faces,
        collapse_wedge_thus,
        wedges,
        materials,
        special_faces,
        model_verts,
        special_verts,
        mesh_scale_max,
        lod_hysteresis,
        lod_strength,
        lod_min_verts,
        lod_morph,
        lod_z_displace,
        remap_anim_verts,
        old_frame_verts,
        vert_stride,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---------------------------------------------------------- Step 1: element decoders

    #[test]
    fn vert_dx_reads_int16_quad_and_discards_pad() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&(-5i16).to_le_bytes());
        buf.extend_from_slice(&10i16.to_le_bytes());
        buf.extend_from_slice(&300i16.to_le_bytes());
        buf.extend_from_slice(&999i16.to_le_bytes()); // pad, discarded
        let ((x, y, z), p) = mesh_vert_dx(&buf, 0).unwrap();
        assert_eq!((x, y, z), (-5, 10, 300));
        assert_eq!(p, 8);
    }

    #[test]
    fn vert_packed_sign_extends_each_field() {
        // X=-1 (11 bits all set), Y=0, Z=-1 (10 bits all set): 0x7FF | (0x3FF << 22).
        let d: u32 = 0x7FF | (0x3FF << 22);
        let ((x, y, z), p) = mesh_vert_packed(&d.to_le_bytes(), 0).unwrap();
        assert_eq!((x, y, z), (-1, 0, -1));
        assert_eq!(p, 4);
    }

    #[test]
    fn vert_packed_positive_values_round_trip() {
        let d: u32 = 5 | (7 << 11) | (3 << 22);
        let ((x, y, z), _) = mesh_vert_packed(&d.to_le_bytes(), 0).unwrap();
        assert_eq!((x, y, z), (5, 7, 3));
    }

    #[test]
    fn tri_decodes_indices_uv_flags_and_texture() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&1u16.to_le_bytes());
        buf.extend_from_slice(&2u16.to_le_bytes());
        buf.extend_from_slice(&3u16.to_le_bytes());
        buf.extend_from_slice(&[10, 20, 30, 40, 50, 60]);
        buf.extend_from_slice(&0xABCDu32.to_le_bytes());
        buf.extend_from_slice(&(-1i32).to_le_bytes());
        let ((iv, uv, flags, tex), p) = mesh_tri(&buf, 0).unwrap();
        assert_eq!(iv, (1, 2, 3));
        assert_eq!(uv, (10, 20, 30, 40, 50, 60));
        assert_eq!(flags, 0xABCD);
        assert_eq!(tex, -1);
        assert_eq!(p, buf.len());
    }

    #[test]
    fn anim_seq_reads_notifys_before_rate_but_returns_rate_before_notifys() {
        // Name=12 (compact idx), Group=17 (single FName, NOT an array), Start=0, NumFrames=1,
        // Notifys=[] (compact count 0), Rate=30.0 — the exact Keypad3/Pigeon-style layout.
        let mut buf = Vec::new();
        buf.push(12u8); // Name
        buf.push(17u8); // Group: single FName, not TArray<FName>
        buf.extend_from_slice(&0i32.to_le_bytes()); // Start
        buf.extend_from_slice(&1i32.to_le_bytes()); // NumFrames
        buf.push(0u8); // Notifys: compact count 0
        buf.extend_from_slice(&30.0f32.to_le_bytes()); // Rate — AFTER Notifys on the wire
        let ((name, group, start, nframes, rate, notifys), p) = mesh_anim_seq(&buf, 0).unwrap();
        assert_eq!((name, group, start, nframes), (12, 17, 0, 1));
        assert_eq!(rate, 30.0);
        assert!(notifys.is_empty());
        assert_eq!(p, buf.len());
    }

    #[test]
    fn anim_seq_group_as_count_would_detonate_without_the_single_fname_fix() {
        // A grouped sequence (Group=17) must NOT be read as a 17-element TArray<FName> — proves
        // the decoder treats Group as one compact index, not an array header.
        let mut buf = Vec::new();
        buf.push(1u8); // Name
        buf.push(17u8); // Group=17
        buf.extend_from_slice(&0i32.to_le_bytes());
        buf.extend_from_slice(&2i32.to_le_bytes());
        buf.push(0u8); // Notifys: empty
        buf.extend_from_slice(&15.0f32.to_le_bytes());
        let ((_, group, _, _, rate, notifys), p) = mesh_anim_seq(&buf, 0).unwrap();
        assert_eq!(group, 17);
        assert_eq!(rate, 15.0);
        assert!(notifys.is_empty());
        assert_eq!(p, buf.len());
    }

    #[test]
    fn vert_connect_reads_two_ints() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&3i32.to_le_bytes());
        buf.extend_from_slice(&99i32.to_le_bytes());
        let ((a, c), p) = mesh_vert_connect(&buf, 0).unwrap();
        assert_eq!((a, c), (3, 99));
        assert_eq!(p, 8);
    }

    #[test]
    fn face_reads_three_wedges_and_material() {
        let mut buf = Vec::new();
        for w in [1u16, 2, 3, 7] {
            buf.extend_from_slice(&w.to_le_bytes());
        }
        let ((iw, mat), p) = mesh_face(&buf, 0).unwrap();
        assert_eq!(iw, (1, 2, 3));
        assert_eq!(mat, 7);
        assert_eq!(p, 8);
    }

    #[test]
    fn wedge_reads_vertex_and_uv_bytes() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&5u16.to_le_bytes());
        buf.extend_from_slice(&[128, 200]);
        let ((iv, u, v), p) = mesh_wedge(&buf, 0).unwrap();
        assert_eq!((iv, u, v), (5, 128, 200));
        assert_eq!(p, 4);
    }

    #[test]
    fn material_reads_flags_and_texture_index() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&0x12u32.to_le_bytes());
        buf.extend_from_slice(&4i32.to_le_bytes());
        let ((flags, tex), p) = mesh_material(&buf, 0).unwrap();
        assert_eq!((flags, tex), (0x12, 4));
        assert_eq!(p, 8);
    }

    // ---------------------------------------------------- Step 2: tarray/lazy_array + stride

    #[test]
    fn tarray_reads_compact_count_then_elements() {
        let mut buf = vec![3u8]; // count 3
        for v in [1i32, 2, 3] {
            buf.extend_from_slice(&v.to_le_bytes());
        }
        let (out, p) = read_tarray(&buf, 0, read_i32).unwrap();
        assert_eq!(out, vec![1, 2, 3]);
        assert_eq!(p, buf.len());
    }

    #[test]
    fn lazy_array_self_verifies_via_skip_offset() {
        // version > 61: 4-byte skip offset, compact count, elements.
        let mut buf = vec![0u8; 4]; // placeholder for skip offset
        buf.push(2u8); // count 2
        let data_start = buf.len();
        for v in [10i32, 20] {
            buf.extend_from_slice(&v.to_le_bytes());
        }
        let end = buf.len();
        buf[0..4].copy_from_slice(&(end as i32).to_le_bytes());
        let _ = data_start;
        let (out, p) = read_lazy_array(&buf, 0, 69, read_i32).unwrap();
        assert_eq!(out, vec![10, 20]);
        assert_eq!(p, end);
    }

    #[test]
    fn lazy_array_wrong_element_width_trips_the_skip_check() {
        // Header claims the elements end at byte 9 (as if 2-byte elements), but we decode with a
        // 4-byte element reader — the self-check must catch the desync, not silently succeed.
        let mut buf = vec![0u8; 4];
        buf.push(2u8); // count 2
        for v in [10i32, 20] {
            buf.extend_from_slice(&v.to_le_bytes());
        }
        buf[0..4].copy_from_slice(&9i32.to_le_bytes()); // WRONG skip offset (real end is 13)
        let err = read_lazy_array(&buf, 0, 69, read_i32).unwrap_err();
        assert!(err.0.contains("skip mismatch"), "message: {}", err.0);
    }

    #[test]
    fn lazy_array_omits_skip_offset_at_version_61_or_below() {
        let mut buf = vec![1u8]; // count 1, no skip offset prefix
        buf.extend_from_slice(&7i32.to_le_bytes());
        let (out, p) = read_lazy_array(&buf, 0, 61, read_i32).unwrap();
        assert_eq!(out, vec![7]);
        assert_eq!(p, buf.len());
    }

    #[test]
    fn detect_vert_stride_reads_dx_eight_byte_verts() {
        // 4-count array of 8-byte DX verts: skip = data_start + 4*8.
        let mut buf = vec![0u8; 4];
        buf.push(4u8); // count 4
        let data_start = buf.len();
        buf.resize(data_start + 4 * 8, 0);
        let skip = buf.len() as i32;
        buf[0..4].copy_from_slice(&skip.to_le_bytes());
        assert_eq!(detect_vert_stride(&buf, 0, 69).unwrap(), Some(8));
    }

    #[test]
    fn detect_vert_stride_reads_stock_four_byte_verts() {
        let mut buf = vec![0u8; 4];
        buf.push(6u8); // count 6
        let data_start = buf.len();
        buf.resize(data_start + 6 * 4, 0);
        let skip = buf.len() as i32;
        buf[0..4].copy_from_slice(&skip.to_le_bytes());
        assert_eq!(detect_vert_stride(&buf, 0, 69).unwrap(), Some(4));
    }

    #[test]
    fn detect_vert_stride_is_none_for_empty_array() {
        let mut buf = vec![0u8; 4];
        buf.push(0u8); // count 0
        let skip = buf.len() as i32;
        buf[0..4].copy_from_slice(&skip.to_le_bytes());
        assert_eq!(detect_vert_stride(&buf, 0, 69).unwrap(), None);
    }

    // ---------------------------------------------------------- Step 4: RemapAnimVerts rebuild

    /// Hand-built LodMesh body isolating just the `RemapAnimVerts` rebuild trap (a real Unreal
    /// Gold fixture — `uned/UnrealAssets/System/UnrealI.u` — is not present in every checkout;
    /// this proves the rebuild mechanics directly from bytes, mirroring
    /// `test_unrealgold_lodmesh_verts_are_rebuilt_through_the_remap`'s assertion).
    #[test]
    fn remap_anim_verts_rebuilds_verts_at_the_new_per_frame_stride() {
        // 2 frames, OldFrameVerts=3, FrameVerts=2: frame f's NEW verts[k] = OLD verts[oldBase +
        // remap[k]]. remap = [2, 0] (reverse the first two of each old 3-slot frame).
        let mut buf = Vec::new();
        // box (min vec3, max vec3, valid u8) + sphere (vec3 + radius) = UPrimitive prefix.
        buf.extend_from_slice(&[0u8; 12 * 2 + 1]); // fbox
        buf.extend_from_slice(&[0u8; 12 + 4]); // fsphere

        // verts: TLazyArray<DX 8-byte>, 6 elements (2 frames * OldFrameVerts=3).
        let dx_vert = |x: i16, y: i16, z: i16| -> [u8; 8] {
            let mut b = [0u8; 8];
            b[0..2].copy_from_slice(&x.to_le_bytes());
            b[2..4].copy_from_slice(&y.to_le_bytes());
            b[4..6].copy_from_slice(&z.to_le_bytes());
            b
        };
        let verts_data: Vec<[u8; 8]> = vec![
            dx_vert(0, 0, 0), dx_vert(1, 1, 1), dx_vert(2, 2, 2), // frame 0, old slots 0,1,2
            dx_vert(10, 10, 10), dx_vert(11, 11, 11), dx_vert(12, 12, 12), // frame 1
        ];
        let verts_start = buf.len() + 4 + 1; // skip-offset(4) + compact count(1 byte, count=6<64)
        let verts_end = verts_start + verts_data.len() * 8;
        buf.extend_from_slice(&(verts_end as i32).to_le_bytes());
        buf.push(6u8);
        for v in &verts_data {
            buf.extend_from_slice(v);
        }

        // tris: empty TLazyArray.
        let tris_pos = buf.len();
        buf.extend_from_slice(&((tris_pos + 4 + 1) as i32).to_le_bytes());
        buf.push(0u8);
        // anim_seqs: empty TArray.
        buf.push(0u8);
        // connects: empty TLazyArray.
        let connects_pos = buf.len();
        buf.extend_from_slice(&((connects_pos + 4 + 1) as i32).to_le_bytes());
        buf.push(0u8);
        // own box + own sphere (discarded).
        buf.extend_from_slice(&[0u8; 12 * 2 + 1]);
        buf.extend_from_slice(&[0u8; 12 + 4]);
        // vert_links: empty TLazyArray<i32>.
        let vl_pos = buf.len();
        buf.extend_from_slice(&((vl_pos + 4 + 1) as i32).to_le_bytes());
        buf.push(0u8);
        // textures: empty TArray.
        buf.push(0u8);
        // bboxes, bspheres: empty TArrays.
        buf.push(0u8);
        buf.push(0u8);
        // frame_verts, anim_frames.
        buf.extend_from_slice(&2i32.to_le_bytes()); // FrameVerts = 2 (NEW per-frame stride)
        buf.extend_from_slice(&2i32.to_le_bytes()); // AnimFrames = 2
        // and_flags, or_flags.
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(&0u32.to_le_bytes());
        // scale, origin, rot_origin.
        buf.extend_from_slice(&1.0f32.to_le_bytes());
        buf.extend_from_slice(&1.0f32.to_le_bytes());
        buf.extend_from_slice(&1.0f32.to_le_bytes());
        buf.extend_from_slice(&[0u8; 12]); // origin
        buf.extend_from_slice(&[0u8; 12]); // rot_origin
        // cur_poly, cur_vertex.
        buf.extend_from_slice(&0i32.to_le_bytes());
        buf.extend_from_slice(&0i32.to_le_bytes());
        // version 69 >= 66: texture_lod TArray<f32>, empty.
        buf.push(0u8);

        // --- ULodMesh tail
        buf.push(0u8); // collapse_point_thus: empty
        buf.push(0u8); // face_level: empty
        buf.push(0u8); // faces: empty
        buf.push(0u8); // collapse_wedge_thus: empty
        buf.push(0u8); // wedges: empty
        buf.push(0u8); // materials: empty
        buf.push(0u8); // special_faces: empty
        buf.extend_from_slice(&0i32.to_le_bytes()); // model_verts
        buf.extend_from_slice(&0i32.to_le_bytes()); // special_verts
        buf.extend_from_slice(&0.0f32.to_le_bytes()); // mesh_scale_max
        buf.extend_from_slice(&0.0f32.to_le_bytes()); // lod_hysteresis
        buf.extend_from_slice(&0.0f32.to_le_bytes()); // lod_strength
        buf.extend_from_slice(&0i32.to_le_bytes()); // lod_min_verts
        buf.extend_from_slice(&0.0f32.to_le_bytes()); // lod_morph
        buf.extend_from_slice(&0.0f32.to_le_bytes()); // lod_z_displace
        // remap_anim_verts: TArray<u16>, [2, 0].
        buf.push(2u8);
        buf.extend_from_slice(&2u16.to_le_bytes());
        buf.extend_from_slice(&0u16.to_le_bytes());
        // old_frame_verts = 3.
        buf.extend_from_slice(&3i32.to_le_bytes());

        let end = buf.len();
        let m = parse_mesh_body(&buf, 0, end, 69, true, None).unwrap();

        assert_eq!(m.vert_stride, 8);
        assert_eq!(m.remap_anim_verts, vec![2, 0]);
        assert_eq!(m.old_frame_verts, 3);
        assert_eq!(m.frame_verts, 2);
        assert_eq!(m.anim_frames, 2);
        // Frame 0: NewVerts[0] = OldVerts[0*3 + remap[0]=2] = (2,2,2); NewVerts[1] = OldVerts[0*3+0] = (0,0,0).
        // Frame 1: NewVerts[2] = OldVerts[1*3+2] = (12,12,12); NewVerts[3] = OldVerts[1*3+0] = (10,10,10).
        assert_eq!(
            m.verts,
            vec![(2, 2, 2), (0, 0, 0), (12, 12, 12), (10, 10, 10)]
        );
    }

    // ---------------------------------------------------- Step 3/4: real-package byte spans
    //
    // `cargo test` builds inside a container that mounts only `uedcli-native/` (see
    // `bin/_venv.sh`'s `_rust_build_run`), so a real `.u` under the repo's `uned/` corpus is
    // unreachable via `include_bytes!` from here. These two small fixtures are the exact
    // post-property-tag body bytes of one plain `Mesh` and one `LodMesh` export, extracted once
    // from the committed `uned/UED22/DeusExDeco.u` (v69) and checked in under `testdata/` —
    // `DXText` (356-byte body, the package's smallest `Mesh`) and `Keypad3` (552-byte body, the
    // package's smallest `LodMesh` — same mesh `test_v68_keypad3_matches_umodel_ground_truth`
    // cross-checks against umodel on the DX v68 side).

    /// `TLazyArray`'s `SkipOffset` is an ABSOLUTE position in the source package file (not
    /// relative to the export body), so a fixture extracted in isolation must be replayed at its
    /// ORIGINAL absolute offset or the self-check (`read_lazy_array`) reports a bogus mismatch.
    /// Zero-pads a buffer up to `orig_pos` (cheap: never read, just shifts where `body` lands) so
    /// `parse_mesh_body`'s internal position arithmetic reproduces the real file's.
    fn at_original_offset(body: &[u8], orig_pos: usize) -> (Vec<u8>, usize, usize) {
        let mut buf = vec![0u8; orig_pos];
        buf.extend_from_slice(body);
        let end = buf.len();
        (buf, orig_pos, end)
    }

    #[test]
    fn parses_a_real_v69_mesh_export_to_exact_end() {
        let body: &[u8] = include_bytes!("../testdata/deusexdeco_dxtext_mesh_v69.bin");
        let (buf, pos, end) = at_original_offset(body, 6_867_580); // DeusExDeco.u `DXText` export
        let m = parse_mesh_body(&buf, pos, end, 69, false, None).unwrap();
        assert_eq!(m.vert_stride, 4); // v69 stock-Unreal packed verts
        assert!(!m.tris.is_empty());
    }

    #[test]
    fn parses_a_real_v69_lodmesh_export_to_exact_end() {
        let body: &[u8] = include_bytes!("../testdata/deusexdeco_keypad3_lodmesh_v69.bin");
        let (buf, pos, end) = at_original_offset(body, 7_509_244); // DeusExDeco.u `Keypad3` export
        let m = parse_mesh_body(&buf, pos, end, 69, true, None).unwrap();
        assert_eq!(m.vert_stride, 4);
        assert!(!m.faces.is_empty());
        assert!(!m.wedges.is_empty());
        // This UED22-rebuilt v69 stub carries an empty ULodMesh tail (see
        // `test_lodmesh_tail_is_not_deusex_specific`'s note: retail v68 populates
        // `OldFrameVerts`, the v69 stubs UED22's own UCC writes leave it 0).
        assert_eq!(m.old_frame_verts, 0);
        assert!(m.remap_anim_verts.is_empty());
    }
}
