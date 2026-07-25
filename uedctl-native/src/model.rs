//! The built `UModel` (BSP) as plain Rust structs — the compute core's output, mirroring
//! the Python `uedctl.native.umodel.Model`.  `model_write::serialize` turns it into the
//! UModel serial body, pinned byte-identical to the Python oracle (§6 gate 5).

/// A build failure carrying the offending value; `lib.rs` maps this to a Python exception.
#[derive(Debug, Clone)]
pub struct BuildError(pub String);

impl std::fmt::Display for BuildError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for BuildError {}

pub type BResult<T> = Result<T, BuildError>;

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Vec3 {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

impl Vec3 {
    pub fn new(x: f32, y: f32, z: f32) -> Self {
        Vec3 { x, y, z }
    }
    pub fn dot(&self, o: &Vec3) -> f32 {
        self.x * o.x + self.y * o.y + self.z * o.z
    }
    pub fn cross(&self, o: &Vec3) -> Vec3 {
        Vec3::new(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )
    }
    pub fn sub(&self, o: &Vec3) -> Vec3 {
        Vec3::new(self.x - o.x, self.y - o.y, self.z - o.z)
    }
    pub fn size(&self) -> f32 {
        self.dot(self).sqrt()
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Plane {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub w: f32,
}

#[derive(Debug, Clone)]
pub struct BspNode {
    pub plane: Plane,
    pub zone_mask: u64,
    pub node_flags: u8,
    pub i_vert_pool: i32,
    pub i_surf: i32,
    pub i_front: i32,
    pub i_back: i32,
    pub i_plane: i32,
    // On-disk FBspNode order (DX v68, decoded in spike 50-model-ondisk-layout-and-render.md):
    // ...iPlane, iCollisionBound(ci), iRenderBound(ci), iZone[2](ci), NumVertices(ci),
    //    iLeaf[2](fixed i32).  iCollisionBound/iRenderBound are Bounds-array indices (-1 =>
    //    renderer's OccludeBsp guard SKIPS the bound test; a >=0 index into an EMPTY Bounds
    //    array derefs a NULL FBox -> "Anomalous singularity in DrawWorld").  iLeaf[side] is the
    //    leaf index for a terminal (child == -1) side, else -1.
    pub i_collision_bound: i32,
    pub i_render_bound: i32,
    pub i_zone: [i32; 2],
    pub num_vertices: i32,
    pub i_leaf: [i32; 2],
}

impl BspNode {
    pub fn leaf(plane: Plane, i_surf: i32, i_vert_pool: i32, num_vertices: i32) -> Self {
        BspNode {
            plane,
            zone_mask: u64::MAX,
            node_flags: 0,
            i_vert_pool,
            i_surf,
            i_front: -1,
            i_back: -1,
            i_plane: -1,
            i_collision_bound: -1,
            i_render_bound: -1,
            i_zone: [0, 0],
            num_vertices,
            i_leaf: [-1, -1],
        }
    }
}

#[derive(Debug, Clone)]
pub struct BspSurf {
    pub texture_ref: i32,
    pub poly_flags: u32,
    pub p_base: i32,
    pub v_normal: i32,
    pub v_texture_u: i32,
    pub v_texture_v: i32,
    pub i_actor: i32,
    pub i_brush_poly: i32,
    pub i_zone: [u16; 2],
    pub i_light_map: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct BspVert {
    pub i_vertex: i32,
    pub i_side: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct BspLeaf {
    pub i_zone: i32,
    pub i_permeating: i32,
    pub i_volumetric: i32,
    pub i_exclusive: u64,
}

impl Default for BspLeaf {
    fn default() -> Self {
        BspLeaf {
            i_zone: 0,
            i_permeating: -1,
            i_volumetric: -1,
            i_exclusive: 0,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Zone {
    pub actor_ref: i32,
    pub connectivity: u64,
    pub visibility: u64,
}

/// `Bounds` element (UModel+0xc0; 25-byte serial = 6×f32 + 1 valid byte).  Render-bound culling
/// (`iRenderBound`); the native build POPULATES `Bounds` via the faithful `FilterBound` port
/// (`passes::bsp_build_bounds`) — one valid FBox per interior node, OccludeBsp-safe (section 50).
#[derive(Debug, Clone, Copy)]
pub struct FBox {
    pub min: Vec3,
    pub max: Vec3,
    pub valid: u8,
}

/// One `FLightMapIndex` (UModel+0xa8; 40-byte in-memory element) — the per-surface lumel-grid
/// descriptor produced by the native `LIGHT APPLY` bake (spike section 20-lighting-bake.md §4).
/// Serial order (written by `model_write`/`umodel.py`):
///   `raw_i32(data_offset) + f32(pan.x)+f32(pan.y)+f32(pan.z) + ci(u_size)+ci(v_size)
///    + f32(u_scale)+f32(v_scale) + raw_i32(i_light_actors)`.
#[derive(Debug, Clone, Copy)]
pub struct LightMapIndex {
    /// Byte offset of this surf's first bit-plane in `light_bits`.
    pub data_offset: i32,
    /// Index into `lights` (the start of this surf's NULL-terminated light run); `-1` = dark.
    pub i_light_actors: i32,
    /// Lumel-grid origin in texture space: `(Umin-0.125, Vmin-0.125, 0)`.
    pub pan: Vec3,
    /// World units per lumel along U/V.
    pub u_scale: f32,
    pub v_scale: f32,
    /// Lumel counts across U / down V.
    pub u_size: i32,
    pub v_size: i32,
}

#[derive(Debug, Clone)]
pub struct Model {
    pub vectors: Vec<Vec3>,
    pub points: Vec<Vec3>,
    pub nodes: Vec<BspNode>,
    pub surfs: Vec<BspSurf>,
    pub verts: Vec<BspVert>,
    pub num_shared_sides: i32,
    pub zones: Vec<Zone>,
    pub field_0x54: i32,
    /// Render-bound `FBox` array (UModel+0xc0), indexed by node `i_render_bound`.  Built by the
    /// faithful `FilterBound` port (`passes::bsp_build_bounds`): one FBox per INTERIOR node
    /// (post-order DFS), each IsValid=1 with well-formed extents so `URender::OccludeBsp`'s
    /// per-node bound test is safe (section 50).
    pub bounds: Vec<FBox>,
    /// `LeafHulls` (UModel+0xcc): the per-solid-leaf CONVEX HULL the game's box-sweep collision
    /// (`FBoxLineCheckInfo::BoxLineCheck` 0xf42f0) clips against, indexed by node
    /// `i_collision_bound`.  Each run: `[plane-node ref (|0x40000000 = FLIP), …, -1, 6×
    /// raw-i32-bitcast f32 bbox]`.  REQUIRED for a walkable pawn — a box sweep has NO node-plane
    /// fallback, so an `i_collision_bound=-1` node is non-solid to any `extent!=0` trace
    /// (re-raw-zones/linecheck-oracle.md).
    pub leaf_hulls: Vec<i32>,
    pub leaves: Vec<BspLeaf>,
    /// `LIGHT APPLY` bake output (spike section 20).  All empty for an unlit build; filled by
    /// `light::bake`.  `light_map` is the `FLightMapIndex` array (UModel+0xa8); `light_bits` the
    /// packed 1-bit-per-lumel shadow planes (UModel+0xb4); `lights` the flattened per-surf light
    /// runs (UModel+0xe4) — each entry a 0-based INDEX into the bake's input light list, with a
    /// `-1` NULL-terminator between runs.  Python assembly rewrites those indices to export
    /// object-refs (`_patch_light_refs`) after re-parsing the serialized body.
    pub light_map: Vec<LightMapIndex>,
    pub light_bits: Vec<u8>,
    pub lights: Vec<i32>,
    pub none_index: i32,
    pub bbox_min: Vec3,
    pub bbox_max: Vec3,
    /// The "outside" side of the empty root (engine `UModel::RootOutside`).  A fresh level is
    /// `true` — the void beyond all geometry is empty space, so an Add into the void keeps its
    /// outward faces and a Subtract into pure void keeps nothing (§4.2).  The CSG leaf-filter's
    /// empty-Bsp branch seeds `F_OUTSIDE` when true, `F_INSIDE` when false.
    pub root_outside: bool,
}

impl Default for Model {
    fn default() -> Self {
        Model {
            vectors: Vec::new(),
            points: Vec::new(),
            nodes: Vec::new(),
            surfs: Vec::new(),
            verts: Vec::new(),
            num_shared_sides: 0,
            zones: Vec::new(),
            field_0x54: 0,
            bounds: Vec::new(),
            leaf_hulls: Vec::new(),
            leaves: Vec::new(),
            light_map: Vec::new(),
            light_bits: Vec::new(),
            lights: Vec::new(),
            none_index: 0,
            bbox_min: Vec3::new(0.0, 0.0, 0.0),
            bbox_max: Vec3::new(0.0, 0.0, 0.0),
            root_outside: true,
        }
    }
}
