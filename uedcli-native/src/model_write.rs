//! Serialize a built `Model` into the UModel serial body — the RUNTIME/shipped serializer.
//!
//! This is a fresh re-port; the Python proof does NOT transfer.  It is pinned byte-identical
//! to the proven Python `uedcli.native.umodel.write_model_body` by §6 gate 5 (agreement is
//! the proof, not inheritance).  Serial order matches `umodel.py` exactly.

use crate::model::{BspLeaf, BspNode, BspSurf, BspVert, BuildError, LightMapIndex, Model, Vec3};

const PREFIX: usize = 42;

/// Canonical-minimal FCompactIndex (matches the engine writer + Python `write_ci`).
pub fn write_ci(value: i32) -> Vec<u8> {
    let neg = value < 0;
    let mut v: u32 = if neg {
        (-(value as i64)) as u32
    } else {
        value as u32
    };
    let mut out = Vec::new();
    let mut b0: u8 = if neg { 0x80 } else { 0 } | ((v & 0x3F) as u8);
    v >>= 6;
    if v != 0 {
        b0 |= 0x40;
    }
    out.push(b0);
    while v != 0 {
        let mut b = (v & 0x7F) as u8;
        v >>= 7;
        if v != 0 {
            b |= 0x80;
        }
        out.push(b);
    }
    out
}

fn put_f32(out: &mut Vec<u8>, v: f32) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn put_i32(out: &mut Vec<u8>, v: i32) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn put_u32(out: &mut Vec<u8>, v: u32) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn put_u16(out: &mut Vec<u8>, v: u16) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn put_u64(out: &mut Vec<u8>, v: u64) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn put_ci(out: &mut Vec<u8>, v: i32) {
    out.extend_from_slice(&write_ci(v));
}

fn put_vec3(out: &mut Vec<u8>, v: &Vec3) {
    put_f32(out, v.x);
    put_f32(out, v.y);
    put_f32(out, v.z);
}

fn put_fvector_array(out: &mut Vec<u8>, vecs: &[Vec3]) {
    put_ci(out, vecs.len() as i32);
    for v in vecs {
        put_vec3(out, v);
    }
}

fn put_node(out: &mut Vec<u8>, n: &BspNode) {
    put_f32(out, n.plane.x);
    put_f32(out, n.plane.y);
    put_f32(out, n.plane.z);
    put_f32(out, n.plane.w);
    put_u64(out, n.zone_mask);
    out.push(n.node_flags);
    put_ci(out, n.i_vert_pool);
    put_ci(out, n.i_surf);
    put_ci(out, n.i_front);
    put_ci(out, n.i_back);
    put_ci(out, n.i_plane);
    put_ci(out, n.i_collision_bound);
    put_ci(out, n.i_render_bound);
    put_ci(out, n.i_zone[0]);
    put_ci(out, n.i_zone[1]);
    put_ci(out, n.num_vertices);
    put_i32(out, n.i_leaf[0]);
    put_i32(out, n.i_leaf[1]);
}

fn put_surf(out: &mut Vec<u8>, s: &BspSurf) {
    put_ci(out, s.texture_ref);
    put_u32(out, s.poly_flags);
    put_ci(out, s.p_base);
    put_ci(out, s.v_normal);
    put_ci(out, s.v_texture_u);
    put_ci(out, s.v_texture_v);
    // FBspSurf real on-disk order (verified vs DXOnly/DX/Entry, 2026-07-16): iLightMap is the
    // 7th field (right after vTextureV); the owning-brush iActor is LAST.  Swapping them made the
    // game read iLightMap from the (large) iActor value -> OOB Model.LightMap -> bad Model.Lights
    // pointer -> the AddLight AV (Render.dll 0x10b08b4a).  Keep byte-identical to umodel._enc_surf.
    put_ci(out, s.i_light_map);
    put_ci(out, s.i_brush_poly);
    put_u16(out, s.i_zone[0]);
    put_u16(out, s.i_zone[1]);
    put_ci(out, s.i_actor);
}

fn put_vert(out: &mut Vec<u8>, v: &BspVert) {
    put_ci(out, v.i_vertex);
    put_ci(out, v.i_side);
}

fn put_lightmap_index(out: &mut Vec<u8>, l: &LightMapIndex) {
    // Serial order (spike section 20 §4/§8, matches Engine 0x1016f9f0 + umodel.py):
    //   raw_i32(DataOffset), f32 Pan.x/y/z, ci(USize), ci(VSize), f32 UScale/VScale,
    //   raw_i32(iLightActors).
    put_i32(out, l.data_offset);
    put_f32(out, l.pan.x);
    put_f32(out, l.pan.y);
    put_f32(out, l.pan.z);
    put_ci(out, l.u_size);
    put_ci(out, l.v_size);
    put_f32(out, l.u_scale);
    put_f32(out, l.v_scale);
    put_i32(out, l.i_light_actors);
}

fn put_leaf(out: &mut Vec<u8>, l: &BspLeaf) {
    put_ci(out, l.i_zone);
    put_ci(out, l.i_permeating);
    put_ci(out, l.i_volumetric);
    put_u64(out, l.i_exclusive);
}

fn put_prefix(out: &mut Vec<u8>, m: &Model) -> Result<(), BuildError> {
    let none = write_ci(m.none_index);
    if none.len() != 1 {
        return Err(BuildError(format!(
            "Model 'None' name index must encode to a single byte (index {}); keep it < 64",
            m.none_index
        )));
    }
    out.extend_from_slice(&none);
    put_vec3(out, &m.bbox_min);
    put_vec3(out, &m.bbox_max);
    // FBox IsValid — the level UModel's UPrimitive bbox is left uncomputed at save time, so
    // UnrealEd serializes IsValid=0 (verified against DX/Maps/Test_Castle.dx prefix byte 25 == 0,
    // 2026-07-18).  We previously hardcoded 1, the one avoidable prefix byte-diff vs the editor.
    out.push(0);
    let cx = (m.bbox_min.x + m.bbox_max.x) / 2.0;
    let cy = (m.bbox_min.y + m.bbox_max.y) / 2.0;
    let cz = (m.bbox_min.z + m.bbox_max.z) / 2.0;
    put_vec3(out, &Vec3::new(cx, cy, cz));
    put_f32(out, 0.0); // FSphere radius
    debug_assert_eq!(out.len(), PREFIX);
    Ok(())
}

/// Serialize the whole UModel body.
pub fn serialize(m: &Model) -> Result<Vec<u8>, BuildError> {
    let mut out = Vec::new();
    put_prefix(&mut out, m)?;
    put_fvector_array(&mut out, &m.vectors);
    put_fvector_array(&mut out, &m.points);
    put_ci(&mut out, m.nodes.len() as i32);
    for n in &m.nodes {
        put_node(&mut out, n);
    }
    put_ci(&mut out, m.surfs.len() as i32);
    for s in &m.surfs {
        put_surf(&mut out, s);
    }
    put_ci(&mut out, m.verts.len() as i32);
    for v in &m.verts {
        put_vert(&mut out, v);
    }
    put_i32(&mut out, m.num_shared_sides);
    put_i32(&mut out, m.zones.len() as i32);
    for z in &m.zones {
        put_ci(&mut out, z.actor_ref);
        put_u64(&mut out, z.connectivity);
        put_u64(&mut out, z.visibility);
    }
    put_ci(&mut out, m.field_0x54);
    // a8 LightMap (FLightMapIndex array), b4 LightBits (BYTE array) — the lightmap bake output
    // (spike section 20).  Empty for an unlit build => ci(0), byte-identical to the old stub.
    put_ci(&mut out, m.light_map.len() as i32);
    for l in &m.light_map {
        put_lightmap_index(&mut out, l);
    }
    put_ci(&mut out, m.light_bits.len() as i32);
    out.extend_from_slice(&m.light_bits);
    // c0 Bounds (TArray<FBox>): 6×f32 + 1 valid byte (25 B serial).  Populated by the FilterBound
    // port (passes::bsp_build_bounds) — one valid render FBox per interior node.
    put_ci(&mut out, m.bounds.len() as i32);
    for b in &m.bounds {
        put_vec3(&mut out, &b.min);
        put_vec3(&mut out, &b.max);
        out.push(b.valid);
    }
    // cc LeafHulls (TArray<INT>): the box-sweep collision hulls (raw INT array incl. bitcast bbox).
    put_ci(&mut out, m.leaf_hulls.len() as i32);
    for &i in &m.leaf_hulls {
        put_i32(&mut out, i);
    }
    put_ci(&mut out, m.leaves.len() as i32);
    for l in &m.leaves {
        put_leaf(&mut out, l);
    }
    // e4 Lights (TArray<AActor*> object-refs; here 0-based light indices + -1 NULL terminators,
    // patched to export refs by Python assembly).  Empty => ci(0).
    put_ci(&mut out, m.lights.len() as i32);
    for &r in &m.lights {
        put_ci(&mut out, r);
    }
    put_i32(&mut out, 0); // trailing
    put_i32(&mut out, 0); // trailing
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ci_roundtrip_matches_engine() {
        // canonical-minimal forms verified against the Python encoder's known outputs
        assert_eq!(write_ci(0), vec![0x00]);
        assert_eq!(write_ci(2), vec![0x02]);
        assert_eq!(write_ci(-1), vec![0x81]);
        assert_eq!(write_ci(63), vec![0x3F]);
        assert_eq!(write_ci(64), vec![0x40, 0x01]);
        assert_eq!(write_ci(-64), vec![0xC0, 0x01]);
    }

    #[test]
    fn box_model_serializes() {
        let m = crate::build::carved_box(512.0, 256.0);
        let body = serialize(&m).unwrap();
        // prefix(42) + at least the two vector arrays
        assert!(body.len() > PREFIX);
        assert_eq!(m.nodes.len(), 6);
        assert_eq!(m.surfs.len(), 6);
    }
}
