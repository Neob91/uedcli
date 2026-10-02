//! Parse a UModel serial body back into a `Model` — the inverse of `model_write::serialize`, so the
//! path pass can take the `ULevel.Model` (or a Mover's `Brush`) body of a package read from disk.
//! Field order mirrors the writer exactly; `serialize(parse(body)) == body` for every body the
//! writer produces (pinned below on the committed mover fixtures).

use crate::model::{
    BspLeaf, BspNode, BspSurf, BspVert, BuildError, FBox, LightMapIndex, Model, Plane, Vec3, Zone,
};

struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize, what: &str) -> Result<&'a [u8], BuildError> {
        if self.pos + n > self.buf.len() {
            return Err(BuildError(format!(
                "Model body truncated reading {what} at byte {} (need {n}, have {})",
                self.pos,
                self.buf.len() - self.pos
            )));
        }
        let s = &self.buf[self.pos..self.pos + n];
        self.pos += n;
        Ok(s)
    }
    fn u8(&mut self, what: &str) -> Result<u8, BuildError> {
        Ok(self.take(1, what)?[0])
    }
    fn i32(&mut self, what: &str) -> Result<i32, BuildError> {
        Ok(i32::from_le_bytes(self.take(4, what)?.try_into().unwrap()))
    }
    fn u32(&mut self, what: &str) -> Result<u32, BuildError> {
        Ok(u32::from_le_bytes(self.take(4, what)?.try_into().unwrap()))
    }
    fn u16(&mut self, what: &str) -> Result<u16, BuildError> {
        Ok(u16::from_le_bytes(self.take(2, what)?.try_into().unwrap()))
    }
    fn u64(&mut self, what: &str) -> Result<u64, BuildError> {
        Ok(u64::from_le_bytes(self.take(8, what)?.try_into().unwrap()))
    }
    fn f32(&mut self, what: &str) -> Result<f32, BuildError> {
        Ok(f32::from_le_bytes(self.take(4, what)?.try_into().unwrap()))
    }
    fn vec3(&mut self, what: &str) -> Result<Vec3, BuildError> {
        Ok(Vec3::new(self.f32(what)?, self.f32(what)?, self.f32(what)?))
    }
    /// FCompactIndex (the engine's `operator<<(FCompactIndex&)`).
    fn ci(&mut self, what: &str) -> Result<i32, BuildError> {
        let b0 = self.u8(what)?;
        let neg = b0 & 0x80 != 0;
        let mut v: u32 = (b0 & 0x3F) as u32;
        if b0 & 0x40 != 0 {
            let mut shift = 6;
            loop {
                let b = self.u8(what)?;
                v |= ((b & 0x7F) as u32) << shift;
                shift += 7;
                if b & 0x80 == 0 || shift >= 32 {
                    break;
                }
            }
        }
        Ok(if neg { -(v as i64) as i32 } else { v as i32 })
    }
    fn count(&mut self, what: &str) -> Result<usize, BuildError> {
        let n = self.ci(what)?;
        if n < 0 {
            return Err(BuildError(format!("Model body: negative {what} count {n}")));
        }
        Ok(n as usize)
    }
}

fn read_node(r: &mut Reader) -> Result<BspNode, BuildError> {
    let plane = Plane {
        x: r.f32("node plane")?,
        y: r.f32("node plane")?,
        z: r.f32("node plane")?,
        w: r.f32("node plane")?,
    };
    Ok(BspNode {
        plane,
        zone_mask: r.u64("node zone_mask")?,
        node_flags: r.u8("node flags")?,
        i_vert_pool: r.ci("node iVertPool")?,
        i_surf: r.ci("node iSurf")?,
        i_front: r.ci("node iFront")?,
        i_back: r.ci("node iBack")?,
        i_plane: r.ci("node iPlane")?,
        i_collision_bound: r.ci("node iCollisionBound")?,
        i_render_bound: r.ci("node iRenderBound")?,
        i_zone: [r.ci("node iZone")?, r.ci("node iZone")?],
        num_vertices: r.ci("node NumVertices")?,
        i_leaf: [r.i32("node iLeaf")?, r.i32("node iLeaf")?],
    })
}

fn read_surf(r: &mut Reader) -> Result<BspSurf, BuildError> {
    Ok(BspSurf {
        texture_ref: r.ci("surf Texture")?,
        poly_flags: r.u32("surf PolyFlags")?,
        p_base: r.ci("surf pBase")?,
        v_normal: r.ci("surf vNormal")?,
        v_texture_u: r.ci("surf vTextureU")?,
        v_texture_v: r.ci("surf vTextureV")?,
        i_light_map: r.ci("surf iLightMap")?,
        i_brush_poly: r.ci("surf iBrushPoly")?,
        pan: [r.u16("surf PanU")? as i16 as i32, r.u16("surf PanV")? as i16 as i32],
        i_actor: r.ci("surf iActor")?,
    })
}

fn read_lightmap_index(r: &mut Reader) -> Result<LightMapIndex, BuildError> {
    Ok(LightMapIndex {
        data_offset: r.i32("lightmap DataOffset")?,
        pan: r.vec3("lightmap Pan")?,
        u_size: r.ci("lightmap USize")?,
        v_size: r.ci("lightmap VSize")?,
        u_scale: r.f32("lightmap UScale")?,
        v_scale: r.f32("lightmap VScale")?,
        i_light_actors: r.i32("lightmap iLightActors")?,
    })
}

/// Parse a UModel serial body (the `serialize` layout).  The prefix's bbox-valid byte and bounding
/// sphere are read and dropped (`Model` does not carry them; the writer re-derives them).
pub fn parse(body: &[u8]) -> Result<Model, BuildError> {
    let mut r = Reader { buf: body, pos: 0 };
    let mut m = Model {
        none_index: r.ci("None name index")?,
        bbox_min: r.vec3("bbox min")?,
        bbox_max: r.vec3("bbox max")?,
        ..Model::default()
    };
    r.u8("bbox IsValid")?;
    r.vec3("sphere center")?;
    r.f32("sphere radius")?;
    let n = r.count("Vectors")?;
    for _ in 0..n {
        m.vectors.push(r.vec3("vector")?);
    }
    let n = r.count("Points")?;
    for _ in 0..n {
        m.points.push(r.vec3("point")?);
    }
    let n = r.count("Nodes")?;
    for _ in 0..n {
        m.nodes.push(read_node(&mut r)?);
    }
    let n = r.count("Surfs")?;
    for _ in 0..n {
        m.surfs.push(read_surf(&mut r)?);
    }
    let n = r.count("Verts")?;
    for _ in 0..n {
        m.verts.push(BspVert {
            i_vertex: r.ci("vert pVertex")?,
            i_side: r.ci("vert iSide")?,
        });
    }
    m.num_shared_sides = r.i32("NumSharedSides")?;
    let n = r.i32("NumZones")?;
    if !(0..=64).contains(&n) {
        return Err(BuildError(format!("Model body: NumZones {n} out of range 0..=64")));
    }
    for _ in 0..n {
        m.zones.push(Zone {
            actor_ref: r.ci("zone ZoneActor")?,
            connectivity: r.u64("zone Connectivity")?,
            visibility: r.u64("zone Visibility")?,
        });
    }
    m.field_0x54 = r.ci("field 0x54")?;
    let n = r.count("LightMap")?;
    for _ in 0..n {
        m.light_map.push(read_lightmap_index(&mut r)?);
    }
    let n = r.count("LightBits")?;
    m.light_bits = r.take(n, "LightBits")?.to_vec();
    let n = r.count("Bounds")?;
    for _ in 0..n {
        m.bounds.push(FBox {
            min: r.vec3("bound min")?,
            max: r.vec3("bound max")?,
            valid: r.u8("bound IsValid")?,
        });
    }
    let n = r.count("LeafHulls")?;
    for _ in 0..n {
        m.leaf_hulls.push(r.i32("leaf hull")?);
    }
    let n = r.count("Leaves")?;
    for _ in 0..n {
        m.leaves.push(BspLeaf {
            i_zone: r.ci("leaf iZone")?,
            i_permeating: r.ci("leaf iPermeating")?,
            i_volumetric: r.ci("leaf iVolumetric")?,
            i_exclusive: r.u64("leaf VisibleZones")?,
        });
    }
    let n = r.count("Lights")?;
    for _ in 0..n {
        m.lights.push(r.ci("light ref")?);
    }
    // The trailing pair is `RootOutside`, `Linked`: 0/0 on a saved level model, 1/1 on a mover's.
    m.root_outside = r.i32("RootOutside")? != 0;
    r.i32("Linked")?;
    if r.pos != body.len() {
        return Err(BuildError(format!(
            "Model body: {} trailing bytes after the last field",
            body.len() - r.pos
        )));
    }
    Ok(m)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model_write::{serialize, write_ci};

    #[test]
    fn ci_reads_what_write_ci_writes() {
        for v in [0, 1, 2, 63, 64, 65, 127, 128, 8191, 8192, 1 << 20, -1, -63, -64, -65, -8192, -(1 << 20)] {
            let bytes = write_ci(v);
            let mut r = Reader { buf: &bytes, pos: 0 };
            assert_eq!(r.ci("v").unwrap(), v, "ci {v}");
            assert_eq!(r.pos, bytes.len());
        }
    }

    #[test]
    fn carved_box_round_trips() {
        let m = crate::build::carved_box(512.0, 256.0);
        let body = serialize(&m).unwrap();
        let back = parse(&body).unwrap();
        assert_eq!(back.nodes.len(), m.nodes.len());
        assert_eq!(back.surfs.len(), m.surfs.len());
        assert_eq!(serialize(&back).unwrap(), body);
    }

    /// The committed editor-built mover-model bodies: parse then re-serialize must reproduce every
    /// byte between the prefix and the trailing pair (the editor's prefix carries a valid bbox +
    /// bounding sphere and a `1, 1` tail that `Model` does not store; the writer emits the
    /// unbuilt-level form there).
    #[test]
    fn mover_fixture_bodies_round_trip() {
        for (name, body) in [
            ("Model_DeusExMover0", &include_bytes!("../fixtures/mover/Model_DeusExMover0.body")[..]),
            ("Model_DeusExMover5", &include_bytes!("../fixtures/mover/Model_DeusExMover5.body")[..]),
            ("Model_DeusExMover21", &include_bytes!("../fixtures/mover/Model_DeusExMover21.body")[..]),
            ("Model_DeusExMover22", &include_bytes!("../fixtures/mover/Model_DeusExMover22.body")[..]),
        ] {
            let m = parse(body).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert!(m.root_outside, "{name}: a mover model saves RootOutside = 1");
            assert!(!m.nodes.is_empty(), "{name}: no nodes");
            assert!(!m.leaf_hulls.is_empty(), "{name}: no leaf hulls");
            let out = serialize(&m).unwrap();
            assert_eq!(out.len(), body.len(), "{name}: length");
            assert_eq!(&out[42..out.len() - 8], &body[42..body.len() - 8], "{name}: round trip");
        }
    }

    #[test]
    fn truncated_body_names_the_field() {
        let m = crate::build::carved_box(512.0, 256.0);
        let body = serialize(&m).unwrap();
        let err = parse(&body[..body.len() / 2]).unwrap_err();
        assert!(err.0.contains("truncated"), "{err}");
    }
}
