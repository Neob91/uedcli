
    // ===== §92 §47 DE-RISK: does the brush-model reconstruction/weld reproduce the AUTHORED normal
    // for a castle slanted face (so the castle stays byte-exact)?  Runs native's REAL
    // build_brush_temp_bsp + bsp_node_to_fpoly, then calc_normal over the reconstructed LOCAL winding.
    fn v(x: u32, y: u32, z: u32) -> Vec3 { Vec3::new(f32::from_bits(x), f32::from_bits(y), f32::from_bits(z)) }

    /// Reconstruct: build the brush's own temp BSP (welds points, tol 0.002), pull each node's face
    /// back via bsp_node_to_fpoly, recompute calc_normal over the reconstructed winding.  Returns
    /// (i_brush_poly, authored_normal_bits, recon_calcnormal_bits, recon_nverts).
    fn recon_normals(brush: Vec<FPoly>) -> Vec<(i32, [u32;3], [u32;3], usize)> {
        let authored: std::collections::HashMap<i32,[u32;3]> = brush.iter()
            .map(|p| (p.i_brush_poly, [p.normal.x.to_bits(), p.normal.y.to_bits(), p.normal.z.to_bits()])).collect();
        let mut fin: Vec<FPoly> = brush.into_iter().filter_map(|mut p| p.finalize().ok().map(|_| p)).collect();
        // preserve i_brush_poly through finalize (unchanged) — build the temp BSP
        for p in fin.iter_mut() { p.i_link = -1; }
        let tm = build_brush_temp_bsp(&fin).expect("brush temp bsp");
        let mut out = Vec::new();
        for ni in 0..tm.nodes.len() {
            if let Some(mut rp) = bsp_node_to_fpoly(&tm, ni) {
                let ib = tm.surfs[tm.nodes[ni].i_surf as usize].i_brush_poly;
                let nv = rp.verts.len();
                rp.normal = Vec3::new(0.0,0.0,0.0);
                let bits = if rp.calc_normal() { [rp.normal.x.to_bits(), rp.normal.y.to_bits(), rp.normal.z.to_bits()] } else { [0,0,0] };
                out.push((ib, *authored.get(&ib).unwrap_or(&[0,0,0]), bits, nv));
            }
        }
        out.sort_by_key(|t| t.0);
        out
    }

    #[test]
    fn derisk_castle_bastion_recon_vs_authored() {
        let mut brush: Vec<FPoly> = Vec::new();
        { let mut p = FPoly::new(vec![v(0x429d0f3d,0x42021cc4,0xc2fa0000), v(0x42021cc4,0x429d0f3d,0xc2fa0000), v(0x42021cc4,0x429d0f3d,0x42fa0000), v(0x429d0f3d,0x42021cc4,0x42fa0000)]);
        p.normal = v(0x3f3504f7,0x3f3504f7,0x0);
        p.base = v(0x425e1d9f,0x425e1d9f,0x0);
        p.i_brush_poly = 0; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42021cc4,0x429d0f3d,0xc2fa0000), v(0xc2021cc4,0x429d0f3d,0xc2fa0000), v(0xc2021cc4,0x429d0f3d,0x42fa0000), v(0x42021cc4,0x429d0f3d,0x42fa0000)]);
        p.normal = v(0x0,0x3f800000,0x0);
        p.base = v(0x0,0x429d0f3d,0x0);
        p.i_brush_poly = 1; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc2021cc4,0x429d0f3d,0xc2fa0000), v(0xc29d0f3d,0x42021cc4,0xc2fa0000), v(0xc29d0f3d,0x42021cc4,0x42fa0000), v(0xc2021cc4,0x429d0f3d,0x42fa0000)]);
        p.normal = v(0xbf3504f7,0x3f3504f7,0x0);
        p.base = v(0xc25e1d9f,0x425e1d9f,0x0);
        p.i_brush_poly = 2; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc29d0f3d,0x42021cc4,0xc2fa0000), v(0xc29d0f3d,0xc2021cc4,0xc2fa0000), v(0xc29d0f3d,0xc2021cc4,0x42fa0000), v(0xc29d0f3d,0x42021cc4,0x42fa0000)]);
        p.normal = v(0xbf800000,0x0,0x0);
        p.base = v(0xc29d0f3d,0x0,0x0);
        p.i_brush_poly = 3; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc29d0f3d,0xc2021cc4,0xc2fa0000), v(0xc2021cc4,0xc29d0f3d,0xc2fa0000), v(0xc2021cc4,0xc29d0f3d,0x42fa0000), v(0xc29d0f3d,0xc2021cc4,0x42fa0000)]);
        p.normal = v(0xbf3504f7,0xbf3504f7,0x0);
        p.base = v(0xc25e1d9f,0xc25e1d9f,0x0);
        p.i_brush_poly = 4; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc2021cc4,0xc29d0f3d,0xc2fa0000), v(0x42021cc4,0xc29d0f3d,0xc2fa0000), v(0x42021cc4,0xc29d0f3d,0x42fa0000), v(0xc2021cc4,0xc29d0f3d,0x42fa0000)]);
        p.normal = v(0x0,0xbf800000,0x0);
        p.base = v(0x0,0xc29d0f3d,0x0);
        p.i_brush_poly = 5; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42021cc4,0xc29d0f3d,0xc2fa0000), v(0x429d0f3d,0xc2021cc4,0xc2fa0000), v(0x429d0f3d,0xc2021cc4,0x42fa0000), v(0x42021cc4,0xc29d0f3d,0x42fa0000)]);
        p.normal = v(0x3f3504f7,0xbf3504f7,0x0);
        p.base = v(0x425e1d9f,0xc25e1d9f,0x0);
        p.i_brush_poly = 6; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x429d0f3d,0xc2021cc4,0xc2fa0000), v(0x429d0f3d,0x42021cc4,0xc2fa0000), v(0x429d0f3d,0x42021cc4,0x42fa0000), v(0x429d0f3d,0xc2021cc4,0x42fa0000)]);
        p.normal = v(0x3f800000,0x0,0x0);
        p.base = v(0x429d0f3d,0x0,0x0);
        p.i_brush_poly = 7; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x429d0f3d,0x42021cc4,0x42fa0000), v(0x42021cc4,0x429d0f3d,0x42fa0000), v(0xc2021cc4,0x429d0f3d,0x42fa0000), v(0xc29d0f3d,0x42021cc4,0x42fa0000), v(0xc29d0f3d,0xc2021cc4,0x42fa0000), v(0xc2021cc4,0xc29d0f3d,0x42fa0000), v(0x42021cc4,0xc29d0f3d,0x42fa0000), v(0x429d0f3d,0xc2021cc4,0x42fa0000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x0,0x0,0x42fa0000);
        p.i_brush_poly = 8; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x429d0f3d,0xc2021cc4,0xc2fa0000), v(0x42021cc4,0xc29d0f3d,0xc2fa0000), v(0xc2021cc4,0xc29d0f3d,0xc2fa0000), v(0xc29d0f3d,0xc2021cc4,0xc2fa0000), v(0xc29d0f3d,0x42021cc4,0xc2fa0000), v(0xc2021cc4,0x429d0f3d,0xc2fa0000), v(0x42021cc4,0x429d0f3d,0xc2fa0000), v(0x429d0f3d,0x42021cc4,0xc2fa0000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0x0,0x0,0xc2fa0000);
        p.i_brush_poly = 9; brush.push(p); }
        // raw-order calc_normal of the slanted face (i_brush_poly 0) for reference
        let mut raw = brush[0].clone(); raw.normal = Vec3::new(0.0,0.0,0.0); assert!(raw.calc_normal());
        eprintln!("CASTLE Bastion slanted poly0 raw calc_normal = {:#x},{:#x},{:#x}",
            raw.normal.x.to_bits(), raw.normal.y.to_bits(), raw.normal.z.to_bits());
        let r = recon_normals(brush);
        for (ib, auth, rec, nv) in &r {
            eprintln!("  ib={} nv={} authored={:#x},{:#x},{:#x}  recon_calc={:#x},{:#x},{:#x}  {}",
                ib, nv, auth[0],auth[1],auth[2], rec[0],rec[1],rec[2],
                if auth==rec {"== authored"} else {"!= AUTHORED"});
        }
        // DECISIVE: the slanted castle face (ib=0) authored = 0x3f3504f7 (sqrt2/2). Does reconstruction reproduce it?
        let slanted = r.iter().find(|t| t.0==0).unwrap();
        eprintln!("VERDICT castle-slanted reconstruction reproduces authored: {}", slanted.1==slanted.2);
    }

    #[test]
    fn derisk_dome_recon_vs_editor() {
        let mut brush: Vec<FPoly> = Vec::new();
        { let mut p = FPoly::new(vec![v(0x41eb8cfa,0xc15a8318,0x3fccccd5), v(0x41db182c,0xc13c5783,0xc099999c), v(0x41e52f24,0xc120a845,0xc099999c), v(0x41faaf75,0xc130fc50,0x3fccccd5)]);
        p.normal = v(0x3f3dd29e,0xbf0a5d3a,0xbecb8e4c);
        p.base = v(0xc4e994a4,0xc516d759,0xc38a0000);
        p.i_brush_poly = 0; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc12aaaf7,0xc1000000), v(0xc1ba2e81,0xc1000000,0xc1000000), v(0x41ba2e88,0xc1000000,0xc1000000), v(0x41ba2e8d,0xc12aab22,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 1; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc2000000,0xc1000000,0x41000000), v(0xc1faaf6e,0xc130fc25,0x41000000), v(0xc1eb8cf4,0xc15a82ed,0x41000000), v(0xc1d4e663,0xc1764240,0x41000000), v(0xc1ba2e81,0xc1800000,0x41000000), v(0xc1ba2e81,0xc1000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0xc1d4e663,0xc1764240,0x41000000);
        p.i_brush_poly = 2; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41e52f24,0xc120a845,0xc099999c), v(0x41cfaed9,0xc110544f,0xc1000000), v(0x41d17459,0xc1000000,0xc1000000), v(0x41e8ba2a,0xc1000000,0xc099999c)]);
        p.normal = v(0x3f3b077d,0xbe2255b0,0xbf2a06c8);
        p.base = v(0xc4612633,0xc54543f4,0xc38a0000);
        p.i_brush_poly = 3; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41db182c,0xc13c5783,0xc099999c), v(0x41caa35c,0xc11e2bee,0xc1000000), v(0x41cfaed9,0xc110544f,0xc1000000), v(0x41e52f24,0xc120a845,0xc099999c)]);
        p.normal = v(0x3f1c575c,0xbee3eab3,0xbf27a6bd);
        p.base = v(0xc4f57315,0xc5128413,0xc38a0000);
        p.i_brush_poly = 4; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41cbfe75,0xc14ed70f,0xc099999c), v(0x41c31680,0xc1276bb4,0xc1000000), v(0x41caa35c,0xc11e2bee,0xc1000000), v(0x41db182c,0xc13c5783,0xc099999c)]);
        p.normal = v(0x3eccf206,0xbf274d05,0xbf2474b8);
        p.base = v(0xc5048f69,0xc484a1dc,0xc38a0029);
        p.i_brush_poly = 5; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e8d,0xc15555e9,0xc099999c), v(0x41ba2e8d,0xc12aab22,0xc1000000), v(0x41c31680,0xc1276bb4,0xc1000000), v(0x41cbfe75,0xc14ed70f,0xc099999c)]);
        p.normal = v(0x3e0e0c17,0xbf42c333,0xbf224dc2);
        p.base = v(0xc4aebc9e,0xc239d580,0xc38a0000);
        p.i_brush_poly = 6; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41faaf75,0xc130fc50,0x3fccccd5), v(0x41e52f24,0xc120a845,0xc099999c), v(0x41e8ba2a,0xc1000000,0xc099999c), v(0x42000000,0xc1000000,0x3fccccd5)]);
        p.normal = v(0x3f64a2a9,0xbe4672b9,0xbecfd9ba);
        p.base = v(0xc443b785,0xc546dcb2,0xc38a0000);
        p.i_brush_poly = 7; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d4e66c,0xc176426b,0x3fccccd5), v(0x41cbfe75,0xc14ed70f,0xc099999c), v(0x41db182c,0xc13c5783,0xc099999c), v(0x41eb8cfa,0xc15a8318,0x3fccccd5)]);
        p.normal = v(0x3ef6a39c,0xbf4955e7,0xbec5e97d);
        p.base = v(0xc500d97e,0xc490bfc2,0xc38a0000);
        p.i_brush_poly = 8; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e8d,0xc1800000,0x3fccccd5), v(0x41ba2e8d,0xc15555e9,0xc099999c), v(0x41cbfe75,0xc14ed70f,0xc099999c), v(0x41d4e66c,0xc176426b,0x3fccccd5)]);
        p.normal = v(0x3e29f4d3,0xbf6907a7,0xbec23183);
        p.base = v(0xc4ac3e86,0xc31bd380,0xc38a0000);
        p.i_brush_poly = 9; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41faaf75,0xc130fc50,0x41000000), v(0x41faaf75,0xc130fc50,0x3fccccd5), v(0x42000000,0xc1000000,0x3fccccd5), v(0x42000000,0xc1000000,0x41000000)]);
        p.normal = v(0x3f7a2d95,0xbe5924f2,0x0);
        p.base = v(0x41faaf80,0xc130fc00,0xc38a0000);
        p.i_brush_poly = 10; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41eb8cfa,0xc15a8318,0x41000000), v(0x41eb8cfa,0xc15a8318,0x3fccccd5), v(0x41faaf75,0xc130fc50,0x3fccccd5), v(0x41faaf75,0xc130fc50,0x41000000)]);
        p.normal = v(0x3f4edfd7,0xbf16cb64,0x0);
        p.base = v(0x41eb8d00,0xc15a8300,0xc38a0000);
        p.i_brush_poly = 11; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d4e66c,0xc176426b,0x41000000), v(0x41d4e66c,0xc176426b,0x3fccccd5), v(0x41eb8cfa,0xc15a8318,0x3fccccd5), v(0x41eb8cfa,0xc15a8318,0x41000000)]);
        p.normal = v(0x3f05b691,0xbf5a4de4,0x0);
        p.base = v(0x41d4e660,0xc1764200,0xc38a0000);
        p.i_brush_poly = 12; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e8d,0xc1800000,0x41000000), v(0x41ba2e8d,0xc1800000,0x3fccccd5), v(0x41d4e66c,0xc176426b,0x3fccccd5), v(0x41d4e66c,0xc176426b,0x41000000)]);
        p.normal = v(0x3e37ae58,0xbf7bd912,0x0);
        p.base = v(0x41ba2e80,0xc1800000,0xc38a0000);
        p.i_brush_poly = 13; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc12aaaf7,0xc1000000), v(0x41ba2e8d,0xc12aab22,0xc1000000), v(0x41ba2e8d,0xc15555e9,0xc099999c), v(0xc1ba2e81,0xc15555bf,0xc099999c)]);
        p.normal = v(0x0,0xbf44a9ef,0xbf23e35c);
        p.base = v(0xc44effa9,0x4354ab40,0xc38a0000);
        p.i_brush_poly = 14; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc1800000,0x3fccccd5), v(0xc1ba2e81,0xc15555bf,0xc099999c), v(0x41ba2e8d,0xc15555e9,0xc099999c), v(0x41ba2e8d,0xc1800000,0x3fccccd5)]);
        p.normal = v(0x0,0xbf6c4eb5,0xbec4ecc8);
        p.base = v(0xc44f0000,0x42c75640,0xc38a0000);
        p.i_brush_poly = 15; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc1800000,0x41000000), v(0xc1ba2e81,0xc1800000,0x3fccccd5), v(0x41ba2e8d,0xc1800000,0x3fccccd5), v(0x41ba2e8d,0xc1800000,0x41000000)]);
        p.normal = v(0x0,0xbf800000,0x0);
        p.base = v(0xc1ba2e80,0xc1800000,0xc38a0000);
        p.i_brush_poly = 16; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41cbfe6c,0x414ed70f,0xc099999c), v(0x41c31675,0x41276bb4,0xc1000000), v(0x41ba2e7e,0x412aab22,0xc1000000), v(0x41ba2e7e,0x415555e9,0xc099999c)]);
        p.normal = v(0x3e0e0c17,0x3f42c333,0xbf224dc2);
        p.base = v(0xc38b319a,0xc31daa90,0xc38a0000);
        p.i_brush_poly = 17; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41db1822,0x413c5798,0xc099999c), v(0x41caa352,0x411e2c03,0xc1000000), v(0x41c31675,0x41276bb4,0xc1000000), v(0x41cbfe6c,0x414ed70f,0xc099999c)]);
        p.normal = v(0x3eccf11b,0x3f274d49,0xbf2474b8);
        p.base = v(0x44302ae4,0xc4276948,0xc38a0000);
        p.i_brush_poly = 18; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41e52f1c,0x4120a85a,0xc099999c), v(0x41cfaecf,0x41105464,0xc1000000), v(0x41caa352,0x411e2c03,0xc1000000), v(0x41db1822,0x413c5798,0xc099999c)]);
        p.normal = v(0x3f1c574b,0x3ee3eab3,0xbf27a6bd);
        p.base = v(0x4484057c,0xc4e0d397,0xc38a0000);
        p.i_brush_poly = 19; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41e8ba20,0x41000000,0xc099999c), v(0x41d1744f,0x41000000,0xc1000000), v(0x41cfaecf,0x41105464,0xc1000000), v(0x41e52f1c,0x4120a85a,0xc099999c)]);
        p.normal = v(0x3f3b077d,0x3e22556d,0xbf2a06c8);
        p.base = v(0x43cf0b9c,0xc53567a7,0xc38a0000);
        p.i_brush_poly = 20; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d4e662,0x4176426b,0x3fccccd5), v(0x41cbfe6c,0x414ed70f,0xc099999c), v(0x41ba2e7e,0x415555e9,0xc099999c), v(0x41ba2e7e,0x41800000,0x3fccccd5)]);
        p.normal = v(0x3e29f4d3,0x3f6907a7,0xbec23183);
        p.base = v(0xc381398c,0xc2413840,0xc38a0000);
        p.i_brush_poly = 21; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41eb8cf1,0x415a8318,0x3fccccd5), v(0x41db1822,0x413c5798,0xc099999c), v(0x41cbfe6c,0x414ed70f,0xc099999c), v(0x41d4e662,0x4176426b,0x3fccccd5)]);
        p.normal = v(0x3ef6a359,0x3f495608,0xbec5e95b);
        p.base = v(0x443f037c,0xc40f2f40,0xc38a0000);
        p.i_brush_poly = 22; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41faaf6b,0x4130fc50,0x3fccccd5), v(0x41e52f1c,0x4120a85a,0xc099999c), v(0x41db1822,0x413c5798,0xc099999c), v(0x41eb8cf1,0x415a8318,0x3fccccd5)]);
        p.normal = v(0x3f3dd29e,0x3f0a5d4a,0xbecb8e08);
        p.base = v(0x448fe429,0xc4d82c5c,0xc38a0000);
        p.i_brush_poly = 23; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42000000,0x41000000,0x3fccccd5), v(0x41e8ba20,0x41000000,0xc099999c), v(0x41e52f1c,0x4120a85a,0xc099999c), v(0x41faaf6b,0x4130fc50,0x3fccccd5)]);
        p.normal = v(0x3f64a2a9,0x3e4672b9,0xbecfd9ba);
        p.base = v(0x4404f4bc,0xc533cee0,0xc38a0000);
        p.i_brush_poly = 24; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d4e662,0x4176426b,0x41000000), v(0x41d4e662,0x4176426b,0x3fccccd5), v(0x41ba2e7e,0x41800000,0x3fccccd5), v(0x41ba2e7e,0x41800000,0x41000000)]);
        p.normal = v(0x3e37ae58,0x3f7bd912,0x0);
        p.base = v(0x41d4e660,0x41764200,0xc38a0000);
        p.i_brush_poly = 25; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41eb8cf1,0x415a8318,0x41000000), v(0x41eb8cf1,0x415a8318,0x3fccccd5), v(0x41d4e662,0x4176426b,0x3fccccd5), v(0x41d4e662,0x4176426b,0x41000000)]);
        p.normal = v(0x3f05b691,0x3f5a4de4,0x0);
        p.base = v(0x41eb8d00,0x415a8300,0xc38a0000);
        p.i_brush_poly = 26; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41faaf6b,0x4130fc50,0x41000000), v(0x41faaf6b,0x4130fc50,0x3fccccd5), v(0x41eb8cf1,0x415a8318,0x3fccccd5), v(0x41eb8cf1,0x415a8318,0x41000000)]);
        p.normal = v(0x3f4edfe7,0x3f16cb53,0x0);
        p.base = v(0x41faaf60,0x4130fc00,0xc38a0000);
        p.i_brush_poly = 27; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42000000,0x41000000,0x41000000), v(0x42000000,0x41000000,0x3fccccd5), v(0x41faaf6b,0x4130fc50,0x3fccccd5), v(0x41faaf6b,0x4130fc50,0x41000000)]);
        p.normal = v(0x3f7a2d84,0x3e592578,0x0);
        p.base = v(0x42000000,0x41000000,0xc38a0000);
        p.i_brush_poly = 28; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41e8ba2a,0xc1000000,0xc099999c), v(0x41d17459,0xc1000000,0xc1000000), v(0x41d1744f,0x41000000,0xc1000000), v(0x41e8ba20,0x41000000,0xc099999c)]);
        p.normal = v(0x3f3d6cb5,0x0,0xbf2c344c);
        p.base = v(0xc3597358,0xc5464000,0xc38a0000);
        p.i_brush_poly = 29; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42000000,0xc1000000,0x3fccccd5), v(0x41e8ba2a,0xc1000000,0xc099999c), v(0x41e8ba20,0x41000000,0xc099999c), v(0x42000000,0x41000000,0x3fccccd5)]);
        p.normal = v(0x3f690dd0,0x0,0xbed3ddfd);
        p.base = v(0xc2bc5b30,0xc5464000,0xc38a0000);
        p.i_brush_poly = 30; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42000000,0xc1000000,0x41000000), v(0x42000000,0xc1000000,0x3fccccd5), v(0x42000000,0x41000000,0x3fccccd5), v(0x42000000,0x41000000,0x41000000)]);
        p.normal = v(0x3f800000,0x0,0x0);
        p.base = v(0x42000000,0xc1000000,0xc38a0000);
        p.i_brush_poly = 31; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x412aab36,0xc1000000), v(0xc1ba2e9e,0x415555ff,0xc099999c), v(0x41ba2e7e,0x415555e9,0xc099999c), v(0x41ba2e7e,0x412aab22,0xc1000000)]);
        p.normal = v(0x0,0x3f44a9ef,0xbf23e35c);
        p.base = v(0xc44f0000,0xc354ab50,0xc38a0000);
        p.i_brush_poly = 32; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x415555ff,0xc099999c), v(0xc1ba2e9e,0x41800000,0x3fccccd5), v(0x41ba2e7e,0x41800000,0x3fccccd5), v(0x41ba2e7e,0x415555e9,0xc099999c)]);
        p.normal = v(0x0,0x3f6c4ea5,0xbec4ecc8);
        p.base = v(0xc44f0000,0xc2c755a0,0xc38a0000);
        p.i_brush_poly = 33; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x41800000,0x3fccccd5), v(0xc1ba2e9e,0x41800000,0x41000000), v(0x41ba2e7e,0x41800000,0x41000000), v(0x41ba2e7e,0x41800000,0x3fccccd5)]);
        p.normal = v(0x0,0x3f800000,0x0);
        p.base = v(0x41ba2e80,0x41800000,0xc38a0000);
        p.i_brush_poly = 34; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1cbfe6f,0xc14ed6e4,0xc099999c), v(0xc1c31675,0xc1276b89,0xc1000000), v(0xc1ba2e81,0xc12aaaf7,0xc1000000), v(0xc1ba2e81,0xc15555bf,0xc099999c)]);
        p.normal = v(0xbe0e0c17,0xbf42c333,0xbf224dc2);
        p.base = v(0xc34cd3d4,0x4375c5a0,0xc38a0000);
        p.i_brush_poly = 35; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1cbfe6f,0xc14ed6e4,0xc099999c), v(0xc1ba2e81,0xc15555bf,0xc099999c), v(0xc1ba2e81,0xc1800000,0x3fccccd5), v(0xc1d4e663,0xc1764240,0x3fccccd5)]);
        p.normal = v(0xbe29f4d3,0xbf6907a7,0xbec23183);
        p.base = v(0xc360c564,0x430867a0,0xc38a0000);
        p.i_brush_poly = 36; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1db1823,0xc13c576d,0xc099999c), v(0xc1cbfe6f,0xc14ed6e4,0xc099999c), v(0xc1d4e663,0xc1764240,0x3fccccd5), v(0xc1eb8cf4,0xc15a82ed,0x3fccccd5)]);
        p.normal = v(0xbef6a359,0xbf495608,0xbec5e95b);
        p.base = v(0x44565754,0xc3d232b0,0xc38a0000);
        p.i_brush_poly = 37; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e52f1d,0xc120a82f,0xc099999c), v(0xc1db1823,0xc13c576d,0xc099999c), v(0xc1eb8cf4,0xc15a82ed,0x3fccccd5), v(0xc1faaf6e,0xc130fc25,0x3fccccd5)]);
        p.normal = v(0xbf3dd29e,0xbf0a5d4a,0xbecb8e2a);
        p.base = v(0x44a1c23a,0xc4cb2644,0xc38a0000);
        p.i_brush_poly = 38; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e8ba23,0xc1000000,0xc099999c), v(0xc1e52f1d,0xc120a82f,0xc099999c), v(0xc1faaf6e,0xc130fc25,0x3fccccd5), v(0xc2000000,0xc1000000,0x3fccccd5)]);
        p.normal = v(0xbf64a2a9,0xbe4672b9,0xbecfd9ba);
        p.base = v(0x443119c2,0xc53169d1,0xc38a0000);
        p.i_brush_poly = 39; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1d4e663,0xc1764240,0x41000000), v(0xc1d4e663,0xc1764240,0x3fccccd5), v(0xc1ba2e81,0xc1800000,0x3fccccd5), v(0xc1ba2e81,0xc1800000,0x41000000)]);
        p.normal = v(0xbe37ae58,0xbf7bd912,0x0);
        p.base = v(0xc1d4e660,0xc1764200,0xc38a0000);
        p.i_brush_poly = 40; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1eb8cf4,0xc15a82ed,0x41000000), v(0xc1eb8cf4,0xc15a82ed,0x3fccccd5), v(0xc1d4e663,0xc1764240,0x3fccccd5), v(0xc1d4e663,0xc1764240,0x41000000)]);
        p.normal = v(0xbf05b680,0xbf5a4df4,0x0);
        p.base = v(0xc1eb8d00,0xc15a8300,0xc38a0000);
        p.i_brush_poly = 41; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1faaf6e,0xc130fc25,0x41000000), v(0xc1faaf6e,0xc130fc25,0x3fccccd5), v(0xc1eb8cf4,0xc15a82ed,0x3fccccd5), v(0xc1eb8cf4,0xc15a82ed,0x41000000)]);
        p.normal = v(0xbf4edfe7,0xbf16cb53,0x0);
        p.base = v(0xc1faaf60,0xc130fc00,0xc38a0000);
        p.i_brush_poly = 42; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc2000000,0xc1000000,0x41000000), v(0xc2000000,0xc1000000,0x3fccccd5), v(0xc1faaf6e,0xc130fc25,0x3fccccd5), v(0xc1faaf6e,0xc130fc25,0x41000000)]);
        p.normal = v(0xbf7a2d84,0xbe592535,0x0);
        p.base = v(0xc2000000,0xc1000000,0xc38a0000);
        p.i_brush_poly = 43; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e52f34,0x4120a85a,0xc099999c), v(0xc1cfaee9,0x41105464,0xc1000000), v(0xc1d17469,0x41000000,0xc1000000), v(0xc1e8ba3a,0x41000000,0xc099999c)]);
        p.normal = v(0xbf3b077d,0x3e2255b0,0xbf2a06c8);
        p.base = v(0xc3f447d2,0xc54ada7d,0xc38a0000);
        p.i_brush_poly = 44; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1db183b,0x413c5798,0xc099999c), v(0xc1caa369,0x411e2c03,0xc1000000), v(0xc1cfaee9,0x41105464,0xc1000000), v(0xc1e52f34,0x4120a85a,0xc099999c)]);
        p.normal = v(0xbf1c574b,0x3ee3ead5,0xbf27a6bd);
        p.base = v(0xc4cbd7d6,0xc521adf1,0xc38a0000);
        p.i_brush_poly = 45; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1cbfe87,0x414ed726,0xc099999c), v(0xc1c3168d,0x41276bc9,0xc1000000), v(0xc1caa369,0x411e2c03,0xc1000000), v(0xc1db183b,0x413c5798,0xc099999c)]);
        p.normal = v(0xbeccf228,0x3f274cf5,0xbf2474c9);
        p.base = v(0xc4ee9d2e,0xc4afe888,0xc38a0000);
        p.i_brush_poly = 46; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x415555ff,0xc099999c), v(0xc1ba2e9e,0x412aab36,0xc1000000), v(0xc1c3168d,0x41276bc9,0xc1000000), v(0xc1cbfe87,0x414ed726,0xc099999c)]);
        p.normal = v(0xbe0e0c17,0x3f42c333,0xbf224dc2);
        p.base = v(0xc4a58aac,0xc3e0f2e0,0xc38a0000);
        p.i_brush_poly = 47; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1faaf85,0x4130fc65,0x3fccccd5), v(0xc1e52f34,0x4120a85a,0xc099999c), v(0xc1e8ba3a,0x41000000,0xc099999c), v(0xc2000000,0x41000000,0x3fccccd5)]);
        p.normal = v(0xbf64a2a9,0x3e4672b9,0xbecfd9ba);
        p.base = v(0xc417929d,0xc54941be,0xc38a0000);
        p.i_brush_poly = 48; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1eb8d0c,0x415a832d,0x3fccccd5), v(0xc1db183b,0x413c5798,0xc099999c), v(0xc1e52f34,0x4120a85a,0xc099999c), v(0xc1faaf85,0x4130fc65,0x3fccccd5)]);
        p.normal = v(0xbf3dd29e,0x3f0a5d3a,0xbecb8e4c);
        p.base = v(0xc4d7b688,0xc51d5a6b,0xc38a0000);
        p.i_brush_poly = 49; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1d4e67b,0x41764280,0x3fccccd5), v(0xc1cbfe87,0x414ed726,0xc099999c), v(0xc1db183b,0x413c5798,0xc099999c), v(0xc1eb8d0c,0x415a832d,0x3fccccd5)]);
        p.normal = v(0xbef6a39c,0x3f4955e7,0xbec5e97d);
        p.base = v(0xc4f60905,0xc4a3cac1,0xc38a0000);
        p.i_brush_poly = 50; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x41800000,0x3fccccd5), v(0xc1ba2e9e,0x415555ff,0xc099999c), v(0xc1cbfe87,0x414ed726,0xc099999c), v(0xc1d4e67b,0x41764280,0x3fccccd5)]);
        p.normal = v(0xbe29f4d3,0x3f6907a7,0xbec23183);
        p.base = v(0xc4a808d3,0xc3aa43f0,0xc38a0000);
        p.i_brush_poly = 51; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1faaf85,0x4130fc65,0x41000000), v(0xc1faaf85,0x4130fc65,0x3fccccd5), v(0xc2000000,0x41000000,0x3fccccd5), v(0xc2000000,0x41000000,0x41000000)]);
        p.normal = v(0xbf7a2d95,0x3e592535,0x0);
        p.base = v(0xc1faaf80,0x4130fc00,0xc38a0000);
        p.i_brush_poly = 52; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1eb8d0c,0x415a832d,0x41000000), v(0xc1eb8d0c,0x415a832d,0x3fccccd5), v(0xc1faaf85,0x4130fc65,0x3fccccd5), v(0xc1faaf85,0x4130fc65,0x41000000)]);
        p.normal = v(0xbf4edfe7,0x3f16cb53,0x0);
        p.base = v(0xc1eb8d00,0x415a8300,0xc38a0000);
        p.i_brush_poly = 53; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1d4e67b,0x41764280,0x41000000), v(0xc1d4e67b,0x41764280,0x3fccccd5), v(0xc1eb8d0c,0x415a832d,0x3fccccd5), v(0xc1eb8d0c,0x415a832d,0x41000000)]);
        p.normal = v(0xbf05b680,0x3f5a4df4,0x0);
        p.base = v(0xc1d4e680,0x41764200,0xc38a0000);
        p.i_brush_poly = 54; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x41800000,0x41000000), v(0xc1ba2e9e,0x41800000,0x3fccccd5), v(0xc1d4e67b,0x41764280,0x3fccccd5), v(0xc1d4e67b,0x41764280,0x41000000)]);
        p.normal = v(0xbe37ae58,0x3f7bd912,0x0);
        p.base = v(0xc1ba2ea0,0x41800000,0xc38a0000);
        p.i_brush_poly = 55; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1d17452,0xc1000000,0xc1000000), v(0xc1e8ba23,0xc1000000,0xc099999c), v(0xc1e8ba3a,0x41000000,0xc099999c), v(0xc1d17469,0x41000000,0xc1000000)]);
        p.normal = v(0xbf3d6cb5,0x0,0xbf2c344c);
        p.base = v(0x435976a8,0xc5463ff3,0xc38a0000);
        p.i_brush_poly = 56; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e8ba23,0xc1000000,0xc099999c), v(0xc2000000,0xc1000000,0x3fccccd5), v(0xc2000000,0x41000000,0x3fccccd5), v(0xc1e8ba3a,0x41000000,0xc099999c)]);
        p.normal = v(0xbf690dd0,0x0,0xbed3ddfd);
        p.base = v(0x42bc6198,0xc5463ff7,0xc38a0000);
        p.i_brush_poly = 57; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc2000000,0x41000000,0x41000000), v(0xc2000000,0x41000000,0x3fccccd5), v(0xc2000000,0xc1000000,0x3fccccd5), v(0xc2000000,0xc1000000,0x41000000)]);
        p.normal = v(0xbf800000,0x0,0x0);
        p.base = v(0xc2000000,0x41000000,0xc38a0000);
        p.i_brush_poly = 58; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1db1823,0xc13c576d,0xc099999c), v(0xc1caa358,0xc11e2bd8,0xc1000000), v(0xc1c31675,0xc1276b89,0xc1000000), v(0xc1cbfe6f,0xc14ed6e4,0xc099999c)]);
        p.normal = v(0xbeccf11b,0xbf274d59,0xbf2474b8);
        p.base = v(0x44652dfc,0xc3a1b820,0xc38a002d);
        p.i_brush_poly = 59; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e52f1d,0xc120a82f,0xc099999c), v(0xc1cfaed2,0xc1105439,0xc1000000), v(0xc1caa358,0xc11e2bd8,0xc1000000), v(0xc1db1823,0xc13c576d,0xc099999c)]);
        p.normal = v(0xbf1c576d,0xbee3ea92,0xbf27a6ad);
        p.base = v(0x44ada0d4,0xc4c27fdf,0xc389ffda);
        p.i_brush_poly = 60; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1e8ba23,0xc1000000,0xc099999c), v(0xc1d17452,0xc1000000,0xc1000000), v(0xc1cfaed2,0xc1105439,0xc1000000), v(0xc1e52f1d,0xc120a82f,0xc099999c)]);
        p.normal = v(0xbf3b077d,0xbe2255b0,0xbf2a06c8);
        p.base = v(0x444e8856,0xc52fd113,0xc38a0000);
        p.i_brush_poly = 61; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e8d,0xc1800000,0x41000000), v(0x41d4e66c,0xc176426b,0x41000000), v(0x41eb8cfa,0xc15a8318,0x41000000), v(0x41faaf75,0xc130fc50,0x41000000), v(0x42000000,0xc1000000,0x41000000), v(0x41ba2e88,0xc1000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x41faaf75,0xc130fc50,0x41000000);
        p.i_brush_poly = 62; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x41800000,0x41000000), v(0xc1d4e67b,0x41764280,0x41000000), v(0xc1eb8d0c,0x415a832d,0x41000000), v(0xc1faaf85,0x4130fc65,0x41000000), v(0xc2000000,0x41000000,0x41000000), v(0xc1ba2e98,0x41000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0xc1faaf85,0x4130fc65,0x41000000);
        p.i_brush_poly = 63; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x42000000,0x41000000,0x41000000), v(0x41faaf6b,0x4130fc50,0x41000000), v(0x41eb8cf1,0x415a8318,0x41000000), v(0x41d4e662,0x4176426b,0x41000000), v(0x41ba2e7e,0x41800000,0x41000000), v(0x41ba2e7e,0x41000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x41d4e662,0x4176426b,0x41000000);
        p.i_brush_poly = 64; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc1000000,0x41000000), v(0xc1ba2e81,0xc1800000,0x41000000), v(0x41ba2e8d,0xc1800000,0x41000000), v(0x41ba2e88,0xc1000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0xc1ba2e81,0xc1000000,0x41000000);
        p.i_brush_poly = 65; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x41800000,0x41000000), v(0xc1ba2e98,0x41000000,0x41000000), v(0x41ba2e7e,0x41000000,0x41000000), v(0x41ba2e7e,0x41800000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x41ba2e7e,0x41000000,0x41000000);
        p.i_brush_poly = 66; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e98,0x41000000,0x41000000), v(0xc2000000,0x41000000,0x41000000), v(0xc2000000,0xc1000000,0x41000000), v(0xc1ba2e81,0xc1000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0xc1ba2e98,0x41000000,0x41000000);
        p.i_brush_poly = 67; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e88,0xc1000000,0x41000000), v(0x42000000,0xc1000000,0x41000000), v(0x42000000,0x41000000,0x41000000), v(0x41ba2e7e,0x41000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x41ba2e88,0xc1000000,0x41000000);
        p.i_brush_poly = 68; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e98,0x41000000,0x41000000), v(0xc1ba2e81,0xc1000000,0x41000000), v(0x41ba2e88,0xc1000000,0x41000000), v(0x41ba2e7e,0x41000000,0x41000000)]);
        p.normal = v(0x0,0x0,0x3f800000);
        p.base = v(0x41ba2e7e,0x41000000,0x41000000);
        p.i_brush_poly = 69; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41ba2e8d,0xc12aab22,0xc1000000), v(0x41ba2e88,0xc1000000,0xc1000000), v(0x41d17459,0xc1000000,0xc1000000), v(0x41cfaed9,0xc110544f,0xc1000000), v(0x41caa35c,0xc11e2bee,0xc1000000), v(0x41c31680,0xc1276bb4,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 70; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d1744f,0x41000000,0xc1000000), v(0x41ba2e7e,0x41000000,0xc1000000), v(0x41ba2e7e,0x412aab22,0xc1000000), v(0x41c31675,0x41276bb4,0xc1000000), v(0x41caa352,0x411e2c03,0xc1000000), v(0x41cfaecf,0x41105464,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 71; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0x41d17459,0xc1000000,0xc1000000), v(0x41ba2e88,0xc1000000,0xc1000000), v(0x41ba2e7e,0x41000000,0xc1000000), v(0x41d1744f,0x41000000,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 72; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e98,0x41000000,0xc1000000), v(0xc1ba2e9e,0x412aab36,0xc1000000), v(0x41ba2e7e,0x412aab22,0xc1000000), v(0x41ba2e7e,0x41000000,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 73; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc1000000,0xc1000000), v(0xc1ba2e98,0x41000000,0xc1000000), v(0x41ba2e7e,0x41000000,0xc1000000), v(0x41ba2e88,0xc1000000,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 74; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e81,0xc12aaaf7,0xc1000000), v(0xc1c31675,0xc1276b89,0xc1000000), v(0xc1caa358,0xc11e2bd8,0xc1000000), v(0xc1cfaed2,0xc1105439,0xc1000000), v(0xc1d17452,0xc1000000,0xc1000000), v(0xc1ba2e81,0xc1000000,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 75; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1ba2e9e,0x412aab36,0xc1000000), v(0xc1ba2e98,0x41000000,0xc1000000), v(0xc1d17469,0x41000000,0xc1000000), v(0xc1cfaee9,0x41105464,0xc1000000), v(0xc1caa369,0x411e2c03,0xc1000000), v(0xc1c3168d,0x41276bc9,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 76; brush.push(p); }
        { let mut p = FPoly::new(vec![v(0xc1d17452,0xc1000000,0xc1000000), v(0xc1d17469,0x41000000,0xc1000000), v(0xc1ba2e98,0x41000000,0xc1000000), v(0xc1ba2e81,0xc1000000,0xc1000000)]);
        p.normal = v(0x0,0x0,0xbf800000);
        p.base = v(0xc44f0000,0xc5464000,0xc1000000);
        p.i_brush_poly = 77; brush.push(p); }
        let mut raw = brush.iter().find(|p| p.i_brush_poly==44).unwrap().clone();
        raw.normal = Vec3::new(0.0,0.0,0.0); assert!(raw.calc_normal());
        eprintln!("DOME facet ib=44 raw-LOCAL calc_normal = {:#x},{:#x},{:#x} (editor stores 0x3f3b07a5 family)",
            raw.normal.x.to_bits(), raw.normal.y.to_bits(), raw.normal.z.to_bits());
        let r = recon_normals(brush);
        for (ib, auth, rec, nv) in r.iter().filter(|t| [3,20,44,61].contains(&t.0)) {
            eprintln!("  DOME ib={} nv={} authored={:#x},{:#x},{:#x}  recon_calc={:#x},{:#x},{:#x}",
                ib, nv, auth[0],auth[1],auth[2], rec[0],rec[1],rec[2]);
        }
    }
