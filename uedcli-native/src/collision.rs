//! The collision layer the path-build scout moves through: `UModel::LineCheck` (zero-extent walker
//! with a hit point, and the box sweep against the leaf hulls), `UModel::PointCheck`,
//! `ULevel::FindSpot`, `MultiLineCheck`/`SingleLineCheck`, `PointRegion`, and the scout's
//! `MoveActor`/`FarMoveActor`.
//!
//! Decoded in `findings/60-collision.md` (`ued` = UED22 `Engine.dll`, base `0x10000000`; the `dx`
//! constants checked identical, §8).  Node convention on a finalized Model (`linecheck.rs`):
//! `i_back` = the FRONT child (`iChild[1]`), `i_front` = BACK (`iChild[0]`).
//!
//! Only the level Model collides.  The decoded code traces Movers through the collision hash
//! (`MultiLineCheck`: `if (bCheckActors && Hash)`), but the editor builds paths with no hash: the
//! UED22 `pathlab2` golden links the pair across its closed `bBlockActors` door as plain WALK, and
//! the retail Bar carries 15 edges whose straight line crosses a closed door (the `dx` LOS
//! pre-check would drop them) — with Movers traced native loses exactly those 15 and 2; with them
//! ignored both goldens reproduce every pair.  The same `Hash == NULL` makes `CheckEncroachment` a
//! no-op (`0x1039a3f1`/`0x1015f3f4`: no hash → no hits).

use crate::linecheck::{child, combine_state, crossing_mid, is_csg, plane_dot, terminal, BACK, FRONT, MAX_DEPTH, WHOLE_SEGMENT_EPS};
use crate::model::{BspNode, Model, Plane, Vec3};
use crate::paths::PathError;

// --------------------------------------------------------------------------------------------
// Vector helpers (UE1 `FVector` semantics)
// --------------------------------------------------------------------------------------------

pub(crate) fn add(a: Vec3, b: Vec3) -> Vec3 {
    Vec3::new(a.x + b.x, a.y + b.y, a.z + b.z)
}

pub(crate) fn scale(a: Vec3, s: f32) -> Vec3 {
    Vec3::new(a.x * s, a.y * s, a.z * s)
}

pub(crate) fn neg(a: Vec3) -> Vec3 {
    Vec3::new(-a.x, -a.y, -a.z)
}

pub(crate) fn size_squared(a: Vec3) -> f32 {
    a.dot(&a)
}

/// `FVector::SafeNormal`: zero below `SMALL_NUMBER` (1e-8), else `V * (1/appSqrt(|V|²))`.
pub(crate) fn safe_normal(v: Vec3) -> Vec3 {
    let ss = size_squared(v);
    if ss < 1e-8 {
        return Vec3::new(0.0, 0.0, 0.0);
    }
    scale(v, 1.0 / ss.sqrt())
}

/// `FVector::UnsafeNormal`.
fn unsafe_normal(v: Vec3) -> Vec3 {
    scale(v, 1.0 / size_squared(v).sqrt())
}

/// `FVector::IsNearlyZero` (`KINDA_SMALL_NUMBER` = 1e-4).
fn is_nearly_zero(v: Vec3) -> bool {
    v.x.abs() < 1e-4 && v.y.abs() < 1e-4 && v.z.abs() < 1e-4
}

fn plane_normal(p: &Plane) -> Vec3 {
    Vec3::new(p.x, p.y, p.z)
}

fn plane_from(base: Vec3, normal: Vec3) -> Plane {
    Plane { x: normal.x, y: normal.y, z: normal.z, w: base.dot(&normal) }
}

fn flip(p: &Plane) -> Plane {
    Plane { x: -p.x, y: -p.y, z: -p.z, w: -p.w }
}

// --------------------------------------------------------------------------------------------
// One collidable model (the level, or a Mover's model with its planes already in world space)
// --------------------------------------------------------------------------------------------

/// `FCheckResult` as the movement code reads it.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CheckResult {
    pub time: f32,
    pub location: Vec3,
    pub normal: Vec3,
}

impl CheckResult {
    /// `FCheckResult(1.0)`: `Time = 1`, everything else zero.
    pub fn clear() -> CheckResult {
        CheckResult { time: 1.0, location: Vec3::new(0.0, 0.0, 0.0), normal: Vec3::new(0.0, 0.0, 0.0) }
    }
}

/// The level Model prepared for collision queries: the nodes, the leaf hulls, `RootOutside`.
#[derive(Debug, Clone)]
pub struct CollisionModel {
    nodes: Vec<BspNode>,
    leaf_hulls: Vec<i32>,
    root_outside: bool,
    num_zones: usize,
}

impl CollisionModel {
    pub fn level(m: &Model) -> CollisionModel {
        CollisionModel { nodes: m.nodes.clone(), leaf_hulls: m.leaf_hulls.clone(), root_outside: m.root_outside, num_zones: m.zones.len() }
    }

    /// `FBspNode::ChildOutside` with plain `NF_NotCsg|NF_IsNew` (`0x101abd60`).
    fn child_outside(node: &BspNode, side: i32, outside: bool) -> bool {
        combine_state(side, outside, is_csg(node, 0, false))
    }

    /// `UModel::PointRegion` (`0x1aee60`): the zone number of the leaf holding `loc` (`>= 0` →
    /// FRONT); 0 on a solid side or when the model has no zones.
    pub fn point_region(&self, loc: Vec3) -> i32 {
        if self.nodes.is_empty() {
            return 0;
        }
        let mut i_node = 0i32;
        let mut prev = 0usize;
        let mut front = FRONT;
        while i_node != -1 {
            let node = &self.nodes[i_node as usize];
            front = if plane_dot(&node.plane, &loc) >= 0.0 { FRONT } else { BACK };
            prev = i_node as usize;
            i_node = child(node, front);
        }
        if self.num_zones == 0 {
            0
        } else {
            self.nodes[prev].i_zone[front as usize]
        }
    }

    /// `UModel::FastLineCheck(End, Start)`: the zero-extent walker, `ExtraNodeFlags = 0`, clear or not.
    pub fn fast_line_check(&self, end: Vec3, start: Vec3) -> bool {
        self.zero_extent_hit(end, start, 0).is_none()
    }

    /// The zero-extent walker (`0x1ae190`, `linecheck.rs`'s port) with the hit point (`0x101ae464`):
    /// `Location` = the start-side endpoint of the sub-segment that reached a solid terminal,
    /// `Normal` = the plane of the crossing that produced it (the `iParent` argument, threaded down
    /// through the recursion and updated only at a crossing — `0x101ae414`); a start inside solid
    /// reports `Start` and the root's plane (`iParent` = 0 at the top call, `0x101ae5b4`).
    fn zero_extent_hit(&self, end: Vec3, start: Vec3, extra_flags: u8) -> Option<(Vec3, Vec3)> {
        if self.nodes.is_empty() {
            return (!self.root_outside).then_some((start, Vec3::new(0.0, 0.0, 0.0)));
        }
        // `LineCheck` calls the walker with `Outside = 0` (`0x101ae5b4`/`0x101ae60e`), as `linecheck.rs`.
        let mut seen_empty = false;
        let mut hit = None;
        let entry = (start, plane_normal(&self.nodes[0].plane));
        let clear = self.seg_hit(0, end, start, false, 0, extra_flags, &mut seen_empty, entry, &mut hit);
        if clear {
            None
        } else {
            hit
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn seg_hit(
        &self, mut inode: i32, mut p1: Vec3, mut p2: Vec3, mut state: bool, mut depth: u32, extra_flags: u8,
        seen_empty: &mut bool, mut entry: (Vec3, Vec3), hit: &mut Option<(Vec3, Vec3)>,
    ) -> bool {
        loop {
            if depth > MAX_DEPTH {
                return true;
            }
            if inode == -1 {
                let clear = terminal(state, extra_flags, seen_empty);
                if !clear {
                    *hit = Some(entry);
                }
                return clear;
            }
            let node = &self.nodes[inode as usize];
            let d1 = plane_dot(&node.plane, &p1);
            let d2 = plane_dot(&node.plane, &p2);
            if d1 > -WHOLE_SEGMENT_EPS && d2 > -WHOLE_SEGMENT_EPS {
                state = combine_state(FRONT, state, is_csg(node, extra_flags, true));
                inode = child(node, FRONT);
                depth += 1;
                continue;
            }
            if d1 < WHOLE_SEGMENT_EPS && d2 < WHOLE_SEGMENT_EPS {
                state = combine_state(BACK, state, is_csg(node, extra_flags, true));
                inode = child(node, BACK);
                depth += 1;
                continue;
            }
            let t = d2 / (d1 - d2);
            let mid = crossing_mid(p1, p2, t);
            let near_side = if d2 > 0.0 { FRONT } else { BACK };
            let far_side = if near_side == FRONT { BACK } else { FRONT };
            let csg = is_csg(node, extra_flags, false);
            let near_state = combine_state(near_side, state, csg);
            if !self.seg_hit(child(node, near_side), mid, p2, near_state, depth + 1, extra_flags, seen_empty, entry, hit) {
                return false;
            }
            state = combine_state(far_side, state, csg);
            inode = child(node, far_side);
            p2 = mid;
            entry = (mid, plane_normal(&node.plane));
            depth += 1;
        }
    }

    /// `UModel::LineCheck(Hit, Owner, End, Start, Extent, ExtraNodeFlags)` (`0x1ae4c0`): `None` when
    /// clear, else the hit with the engine's pull-back applied.
    pub fn line_check(&self, end: Vec3, start: Vec3, extent: Vec3, extra_flags: u8) -> Option<CheckResult> {
        if self.nodes.is_empty() {
            return (!self.root_outside).then(|| CheckResult { time: 0.0, location: start, normal: Vec3::new(0.0, 0.0, 0.0) });
        }
        if extent.x == 0.0 && extent.y == 0.0 && extent.z == 0.0 {
            let (loc, mut normal) = self.zero_extent_hit(end, start, extra_flags)?;
            let dir = end.sub(&start);
            let mut time = loc.sub(&start).dot(&dir) / size_squared(dir);
            time = (time - 0.5 / dir.size()).clamp(0.0, 1.0);
            if normal.dot(&dir) > 0.0 {
                normal = neg(normal);
            }
            return Some(CheckResult { time, location: add(start, scale(dir, time)), normal });
        }
        let mut info = BoxCheck::new(self, start, end, extent);
        info.box_line_check(0, 0, self.root_outside);
        if !info.did_hit {
            return None;
        }
        let dist = end.sub(&start).size();
        let time = (info.hit_time - (0.1f32).max(0.1 / dist)).clamp(0.0, 1.0);
        if time == 1.0 {
            return None;
        }
        Some(CheckResult { time, location: add(start, scale(end.sub(&start), time)), normal: info.hit_normal })
    }

    /// `UModel::PointCheck` with an extent (`0x1aeba0`): true when the box is in free space.
    pub fn point_check(&self, loc: Vec3, extent: Vec3) -> bool {
        if self.nodes.is_empty() {
            return self.root_outside;
        }
        let mut info = BoxCheck::new(self, loc, loc, extent);
        info.box_point_check(0, 0, self.root_outside)
    }
}

/// `FBoxLineCheckInfo` / `FBoxPointCheckInfo` (§1.1): the sweep state plus the current leaf's hulls.
struct BoxCheck<'a> {
    m: &'a CollisionModel,
    start: Vec3,
    end: Vec3,
    extent: Vec3,
    hit_time: f32,
    hit_normal: Vec3,
    did_hit: bool,
    hulls: Vec<Plane>,
    flags: Vec<u32>,
    box_min: Vec3,
    box_max: Vec3,
    t0: f32,
    t1: f32,
    normal: Vec3,
}

impl<'a> BoxCheck<'a> {
    fn new(m: &'a CollisionModel, start: Vec3, end: Vec3, extent: Vec3) -> BoxCheck<'a> {
        BoxCheck {
            m,
            start,
            end,
            extent,
            hit_time: 2.0, // sentinel (`0x101ae888`): the first leaf's `T1` upper bound
            hit_normal: Vec3::new(0.0, 0.0, 0.0),
            did_hit: false,
            hulls: Vec::with_capacity(64),
            flags: Vec::with_capacity(64),
            box_min: Vec3::new(0.0, 0.0, 0.0),
            box_max: Vec3::new(0.0, 0.0, 0.0),
            t0: -1.0,
            t1: 2.0,
            normal: Vec3::new(0.0, 0.0, 0.0),
        }
    }

    /// Node-plane push-out with the 1.1 factor (`0x101abca2`).
    fn push_out_11(&self, p: &Plane) -> f32 {
        (p.x * self.extent.x * 1.1).abs() + (p.y * self.extent.y * 1.1).abs() + (p.z * self.extent.z * 1.1).abs()
    }

    /// Hull-plane push-out, no factor (`ClipTo 0x101ad557`).
    fn push_out(&self, p: &Plane) -> f32 {
        (p.x * self.extent.x).abs() + (p.y * self.extent.y).abs() + (p.z * self.extent.z).abs()
    }

    /// `SetupHull(Node)` (`0x101af0d0`): the leaf's hull planes (bit 30 = flipped), sign flags, box.
    fn setup_hull(&mut self, node: &BspNode) {
        let data = &self.m.leaf_hulls[node.i_collision_bound as usize..];
        self.hulls.clear();
        self.flags.clear();
        let mut i = 0;
        while data[i] != -1 && i < 64 {
            let mut p = self.m.nodes[(data[i] & 0x3fff_ffff) as usize].plane;
            if data[i] & 0x4000_0000 != 0 {
                p = flip(&p);
            }
            let sign = |v: f32, lo: u32, hi: u32| if v < 0.0 { lo } else if v > 0.0 { hi } else { 0 };
            self.flags.push(sign(p.x, 1, 2) | sign(p.y, 4, 8) | sign(p.z, 0x10, 0x20));
            self.hulls.push(p);
            i += 1;
        }
        let f = |k: usize| f32::from_bits(data[i + k] as u32);
        self.box_min = Vec3::new(f(1), f(2), f(3));
        self.box_max = Vec3::new(f(4), f(5), f(6));
    }

    /// `ClipTo(Hull, Item)` (`0x101ad540`): narrow `[T0, T1]` by one plane; false = missed the hull.
    fn clip_to(&mut self, h: &Plane) -> bool {
        let push_out = self.push_out(h);
        let d1 = plane_dot(h, &self.start);
        let d2 = plane_dot(h, &self.end);
        let mut num = d1 - push_out;
        if d1 > d2 && num >= -push_out {
            num = num.max(0.0);
        }
        let den = d1 - d2;
        let t = num / den;
        if den < -1e-5 {
            if self.t1 > t {
                self.t1 = t;
            }
        } else if den > 1e-5 {
            if t > self.t0 {
                self.t0 = t;
                self.normal = plane_normal(h);
            }
        } else if d1 > push_out && d2 > push_out {
            return false;
        }
        self.t1 > self.t0
    }

    /// `ClipToPoint` (`0x101ad660`) reduced to its verdict (the push-out `Hit` is never read by the
    /// build): false = the box is clear of this plane.
    fn clip_to_point(&self, h: &Plane) -> bool {
        self.push_out(h) > plane_dot(h, &self.start)
    }

    /// The six leaf-box planes (`Owner == NULL`, i.e. the level) in the engine's order with its
    /// asymmetric `±0.1` (`0x101abec0`–`0x101abffe`).
    fn box_planes(&self) -> [Plane; 6] {
        let (lo, hi) = (self.box_min, self.box_max);
        [
            Plane { x: 0.0, y: 0.0, z: -1.0, w: 0.1 - lo.z },
            Plane { x: 0.0, y: 0.0, z: 1.0, w: hi.z + 0.1 },
            Plane { x: -1.0, y: 0.0, z: 0.0, w: 0.1 - lo.x },
            Plane { x: 1.0, y: 0.0, z: 0.0, w: hi.x - 0.1 },
            Plane { x: 0.0, y: -1.0, z: 0.0, w: 0.1 - lo.y },
            Plane { x: 0.0, y: 1.0, z: 0.0, w: hi.y - 0.1 },
        ]
    }

    /// The pairwise edge bevel planes (`0x101ac00c`–`0x101ac81c`) in the engine's order; the
    /// caller clips them one by one and stops at the first miss.
    fn edge_planes(&self) -> Vec<Plane> {
        let axes = [(Vec3::new(1.0, 0.0, 0.0), 3u32), (Vec3::new(0.0, 1.0, 0.0), 0xc), (Vec3::new(0.0, 0.0, 1.0), 0x30)];
        let mut out = Vec::new();
        for i in 0..self.hulls.len() {
            for j in 0..i {
                let f = self.flags[i] | self.flags[j];
                let (hi, hj) = (self.hulls[i], self.hulls[j]);
                for (axis, mask) in axes {
                    if f & mask != mask {
                        continue;
                    }
                    if axis.cross(&plane_normal(&hi)).dot(&axis.cross(&plane_normal(&hj))) <= 0.001 {
                        continue;
                    }
                    let (i_pt, d) = intersect_planes2(&hi, &hj);
                    let mut nrm = unsafe_normal(axis.cross(&d));
                    if plane_normal(&hi).dot(&nrm) < 0.0 {
                        nrm = neg(nrm);
                    }
                    out.push(plane_from(i_pt, nrm));
                }
            }
        }
        out
    }

    /// `BoxLineCheck(iParent, iNode, IsFront, Outside)` (`0x101abc10`).
    fn box_line_check(&mut self, mut i_parent: i32, mut i_node: i32, mut outside: bool) {
        while i_node != -1 {
            let node = &self.m.nodes[i_node as usize];
            let d1 = plane_dot(&node.plane, &self.start);
            let d2 = plane_dot(&node.plane, &self.end);
            let max_dist = self.push_out_11(&node.plane);
            let is_back = d1 <= max_dist || d2 <= max_dist;
            let is_front = d1 >= -max_dist || d2 >= -max_dist;
            let near = if d1 >= d2 { FRONT } else { BACK };
            let far = if near == FRONT { BACK } else { FRONT };
            let side_flag = |s: i32| if s == FRONT { is_front } else { is_back };
            if side_flag(near) {
                let (c, o) = (child(node, near), CollisionModel::child_outside(node, near, outside));
                self.box_line_check(i_node, c, o);
            }
            if !side_flag(far) {
                return;
            }
            let node = &self.m.nodes[i_node as usize];
            i_parent = i_node;
            i_node = child(node, far);
            outside = CollisionModel::child_outside(node, far, outside);
        }
        if outside {
            return;
        }
        let node = self.m.nodes[i_parent as usize].clone();
        if node.i_collision_bound == -1 {
            return;
        }
        self.setup_hull(&node);
        self.t0 = -1.0;
        self.t1 = self.hit_time;
        self.normal = Vec3::new(0.0, 0.0, 0.0);
        for k in 0..self.hulls.len() {
            let h = self.hulls[k];
            if !self.clip_to(&h) {
                return;
            }
        }
        for p in self.box_planes() {
            if !self.clip_to(&p) {
                return;
            }
        }
        for p in self.edge_planes() {
            if !self.clip_to(&p) {
                return;
            }
        }
        if self.t0 > -1.0 && self.t1 > self.t0 && self.t1 > 0.0 {
            self.hit_time = self.t0;
            self.hit_normal = self.normal;
            self.did_hit = true;
        }
    }

    /// `BoxPointCheck(iParent, iNode, Outside)` (`0x101ac890`): true = free.
    fn box_point_check(&mut self, mut i_parent: i32, mut i_node: i32, mut outside: bool) -> bool {
        let mut result = true;
        while i_node != -1 {
            let node = &self.m.nodes[i_node as usize];
            let push_out = self.push_out_11(&node.plane);
            let dist = plane_dot(&node.plane, &self.start);
            if dist > -push_out {
                let (c, o) = (child(node, FRONT), CollisionModel::child_outside(node, FRONT, outside));
                result &= self.box_point_check(i_node, c, o);
            }
            let node = &self.m.nodes[i_node as usize];
            i_parent = i_node;
            i_node = child(node, BACK);
            outside = CollisionModel::child_outside(node, BACK, outside);
            if dist > push_out {
                return result;
            }
        }
        if outside {
            return result;
        }
        let node = self.m.nodes[i_parent as usize].clone();
        if node.i_collision_bound == -1 {
            return result;
        }
        self.setup_hull(&node);
        for k in 0..self.hulls.len() {
            let h = self.hulls[k];
            if !self.clip_to_point(&h) {
                return result;
            }
        }
        for p in self.box_planes() {
            if !self.clip_to_point(&p) {
                return result;
            }
        }
        for p in self.edge_planes() {
            if !self.clip_to_point(&p) {
                return result;
            }
        }
        false
    }
}

/// `FIntersectPlanes2(I, D, P1, P2)` (`0x101ad7a0`): the line where two planes meet.
fn intersect_planes2(p1: &Plane, p2: &Plane) -> (Vec3, Vec3) {
    let (n1, n2) = (plane_normal(p1), plane_normal(p2));
    let d = n1.cross(&n2);
    let dd = size_squared(d);
    if dd < 1e-6 {
        return (Vec3::new(0.0, 0.0, 0.0), Vec3::new(0.0, 0.0, 0.0));
    }
    let i = scale(add(scale(n2.cross(&d), p1.w), scale(d.cross(&n1), p2.w)), 1.0 / dd);
    (i, scale(d, 1.0 / dd.sqrt()))
}

// --------------------------------------------------------------------------------------------
// The level: zones, movers, the ULevel queries
// --------------------------------------------------------------------------------------------

/// A zone's traversal-relevant properties (`ZoneIn` of the interface contract).
#[derive(Debug, Clone, PartialEq)]
pub struct ZoneIn {
    pub zone_number: i32,
    pub b_water: bool,
    pub b_pain: bool,
    /// Casefolded `DamageType` name; `"none"` = the `None` name.
    pub damage_type: String,
    pub gravity: Vec3,
    pub fluid_friction: f32,
    pub velocity: Vec3,
}

impl ZoneIn {
    /// `bPainZone && DamageType != ReducedDamageType` with the scout's `ReducedDamageType` = `None`.
    pub fn is_hostile(&self) -> bool {
        self.b_pain && self.damage_type != "none"
    }
}

/// A Mover as the interface hands it over.  Validated (the model must parse and carry BSP nodes,
/// the transform must be finite) but not traced — see the module doc.
#[derive(Debug, Clone)]
pub struct MoverIn {
    pub name: String,
    pub model: Model,
    pub location: Vec3,
    pub rotation: [i32; 3],
    pub pre_pivot: Vec3,
    pub b_block_actors: bool,
}

/// The `ULevel` the scout moves through.
#[derive(Debug)]
pub struct World {
    level: CollisionModel,
    zones: Vec<ZoneIn>,
    level_zone: ZoneIn,
}

impl World {
    pub fn new(level: &Model, movers: &[MoverIn], zones: Vec<ZoneIn>, level_zone: ZoneIn) -> Result<World, PathError> {
        for m in movers {
            if m.model.nodes.is_empty() {
                return Err(PathError(format!("Mover {}: its model has no BSP nodes", m.name)));
            }
            for v in [m.location.x, m.location.y, m.location.z, m.pre_pivot.x, m.pre_pivot.y, m.pre_pivot.z] {
                if !v.is_finite() {
                    return Err(PathError(format!("Mover {}: non-finite Location/PrePivot value {v}", m.name)));
                }
            }
        }
        Ok(World { level: CollisionModel::level(level), zones, level_zone })
    }

    pub fn level(&self) -> &CollisionModel {
        &self.level
    }

    pub fn zone(&self, zone_number: i32) -> &ZoneIn {
        self.zones.iter().find(|z| z.zone_number == zone_number).unwrap_or(&self.level_zone)
    }

    pub fn point_region(&self, loc: Vec3) -> i32 {
        self.level.point_region(loc)
    }

    /// `ULevel::SingleLineCheck(Hit, Scout, End, Start, TraceFlags = 6, Extent)` (`0x162400`) →
    /// `MultiLineCheck` (`0x161500`) with no collision hash: the level's `LineCheck` alone.
    pub fn single_line_check(&self, end: Vec3, start: Vec3, extent: Vec3) -> Option<CheckResult> {
        self.level.line_check(end, start, extent, 0)
    }

    /// `SinglePointCheck(…, bActors = 0)` (`0x162620`): the level only.
    pub fn single_point_check(&self, loc: Vec3, extent: Vec3) -> bool {
        self.level.point_check(loc, extent)
    }

    /// `AdjustSpot(Adjusted, Adjusted + offset, TraceLen, Hit)` (`0x15f140`).
    fn adjust_spot(&self, adjusted: &mut Vec3, offset: Vec3, len: f32) {
        if let Some(h) = self.single_line_check(add(*adjusted, offset), *adjusted, Vec3::new(0.0, 0.0, 0.0)) {
            if h.time < 1.0 {
                *adjusted = add(*adjusted, scale(h.normal, (1.05 - h.time) * len));
            }
        }
    }

    /// `ULevel::FindSpot(Extent, Location, bCheckActors = 0, bAssumeFit = 0)` (`0x1602e0`): nudge
    /// `loc` into free space; false when no spot within reach.
    pub fn find_spot(&self, extent: Vec3, loc: &mut Vec3) -> bool {
        if extent.x == 0.0 && extent.y == 0.0 && extent.z == 0.0 {
            return self.single_point_check(*loc, extent);
        }
        let mut adjusted = *loc;
        let big = extent.size() + 2.0;
        for i in [-1.0f32, 1.0] {
            self.adjust_spot(&mut adjusted, Vec3::new(i * extent.x, 0.0, 0.0), extent.x);
            self.adjust_spot(&mut adjusted, Vec3::new(0.0, i * extent.y, 0.0), extent.y);
            self.adjust_spot(&mut adjusted, Vec3::new(0.0, 0.0, i * extent.z), extent.z);
        }
        if self.single_point_check(adjusted, extent) {
            *loc = adjusted;
            return true;
        }
        for x in [-1.0f32, 1.0] {
            for y in [-1.0f32, 1.0] {
                for z in [-1.0f32, 1.0] {
                    self.adjust_spot(&mut adjusted, Vec3::new(x * extent.x, y * extent.y, z * extent.z), big);
                }
            }
        }
        if size_squared(adjusted.sub(loc)) as f64 > 1.5 * size_squared(extent) as f64 {
            return false;
        }
        if self.single_point_check(adjusted, extent) {
            *loc = adjusted;
            return true;
        }
        false
    }
}

// --------------------------------------------------------------------------------------------
// The scout's ULevel moves
// --------------------------------------------------------------------------------------------

/// The `AScout` state the movement code reads and writes.
#[derive(Debug, Clone, PartialEq)]
pub struct Scout {
    pub location: Vec3,
    pub velocity: Vec3,
    pub collision_radius: f32,
    pub collision_height: f32,
    pub region_zone: i32,
    pub foot_zone: i32,
}

impl Scout {
    pub fn new() -> Scout {
        // Class defaults 52×50 (`Engine.u`), at the origin until the first placement.
        Scout { location: Vec3::new(0.0, 0.0, 0.0), velocity: Vec3::new(0.0, 0.0, 0.0), collision_radius: 52.0, collision_height: 50.0, region_zone: 0, foot_zone: 0 }
    }

    pub fn extent(&self) -> Vec3 {
        Vec3::new(self.collision_radius, self.collision_radius, self.collision_height)
    }

    /// `SetActorZone` (`0x161e10`) under `bTest`: `Region` from `Location`, `FootRegion` from
    /// `Location − CollisionHeight`.
    pub fn set_actor_zone(&mut self, w: &World) {
        self.region_zone = w.point_region(self.location);
        self.foot_zone = w.point_region(Vec3::new(self.location.x, self.location.y, self.location.z - self.collision_height));
    }

    /// `ULevel::MoveActor(Scout, Delta, Rotation, Hit, bTest = 1, bIgnorePawns = 1, 0, 0)`
    /// (`0x1608e0`): true iff the scout moved at all.  The level always blocks the scout
    /// (`IsBlockedBy(Level)` = `bCollideWorld`, `0x10113fda`).
    pub fn move_actor(&mut self, w: &World, delta: Vec3, hit: &mut CheckResult) -> bool {
        if is_nearly_zero(delta) {
            return true;
        }
        *hit = CheckResult::clear();
        let delta_size = delta.size();
        let delta_dir = if delta_size > 0.0 { scale(delta, 1.0 / delta_size) } else { Vec3::new(0.0, 0.0, 0.0) };
        let test_delta = add(delta, scale(delta_dir, 2.0));
        if let Some(h) = w.single_line_check(add(self.location, test_delta), self.location, self.extent()) {
            *hit = h;
        }
        let mut final_delta = delta;
        if hit.time < 1.0 {
            let moved = (2.0 + delta_size) * hit.time;
            if moved <= 2.0 {
                final_delta = Vec3::new(0.0, 0.0, 0.0);
                hit.time = 0.0;
            } else {
                final_delta = scale(test_delta, hit.time).sub(&scale(delta_dir, 2.0));
                hit.time = (moved - 2.0) / delta_size;
            }
        }
        self.location = add(self.location, final_delta);
        self.set_actor_zone(w);
        hit.time > 0.0
    }

    /// `ULevel::FarMoveActor(Scout, Dest, bTest, bNoCheck)` (`0x15ff80`): `FindSpot` unless
    /// `bNoCheck`; `CheckEncroachment` (unread, `findings/60` §12) is a no-op here — the scout is the
    /// only movable collider in a build level, so nothing can encroach it.  The location is written
    /// under `bTest` too.
    pub fn far_move_actor(&mut self, w: &World, dest: Vec3, b_no_check: bool) -> bool {
        let mut new_loc = dest;
        if !b_no_check && !w.find_spot(self.extent(), &mut new_loc) {
            return false;
        }
        self.location = new_loc;
        self.set_actor_zone(w);
        true
    }
}

impl Default for Scout {
    fn default() -> Self {
        Scout::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;

    /// An axis-aligned box brush (mirrors `linecheck.rs`'s fixture).
    fn box_brush(hx: f32, hy: f32, hz: f32, loc: Vec3, oper: CsgOper) -> BrushInput {
        let c = |sx: f32, sy: f32, sz: f32| Vec3::new(sx * hx, sy * hy, sz * hz);
        let faces = [
            (Vec3::new(1.0, 0.0, 0.0), [c(1.0, -1.0, -1.0), c(1.0, 1.0, -1.0), c(1.0, 1.0, 1.0), c(1.0, -1.0, 1.0)]),
            (Vec3::new(-1.0, 0.0, 0.0), [c(-1.0, 1.0, -1.0), c(-1.0, -1.0, -1.0), c(-1.0, -1.0, 1.0), c(-1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, 1.0, 0.0), [c(1.0, 1.0, -1.0), c(-1.0, 1.0, -1.0), c(-1.0, 1.0, 1.0), c(1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, -1.0, 0.0), [c(-1.0, -1.0, -1.0), c(1.0, -1.0, -1.0), c(1.0, -1.0, 1.0), c(-1.0, -1.0, 1.0)]),
            (Vec3::new(0.0, 0.0, 1.0), [c(-1.0, -1.0, 1.0), c(1.0, -1.0, 1.0), c(1.0, 1.0, 1.0), c(-1.0, 1.0, 1.0)]),
            (Vec3::new(0.0, 0.0, -1.0), [c(-1.0, 1.0, -1.0), c(1.0, 1.0, -1.0), c(1.0, -1.0, -1.0), c(-1.0, -1.0, -1.0)]),
        ];
        let polys = faces
            .iter()
            .map(|(n, verts)| {
                let mut p = FPoly::new(verts.to_vec());
                p.normal = *n;
                p
            })
            .collect();
        BrushInput {
            polys,
            oper,
            poly_flags: 0,
            rot: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            prepivot: Vec3::new(0.0, 0.0, 0.0),
            location: loc,
            scale: Vec3::new(1.0, 1.0, 1.0),
            vec_xform: None,
            orientation: 1,
        }
    }

    fn zone0() -> ZoneIn {
        ZoneIn { zone_number: 0, b_water: false, b_pain: false, damage_type: "none".into(), gravity: Vec3::new(0.0, 0.0, -950.0), fluid_friction: 1.2, velocity: Vec3::new(0.0, 0.0, 0.0) }
    }

    fn room() -> Model {
        // ±256 X/Y, ±128 Z, floor at z = -128
        build_geometry_from_brushes(&[box_brush(256.0, 256.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract)]).unwrap()
    }

    fn corridor_with_step() -> Model {
        // a room whose right half's floor is 16 uu higher (a step), plus a 160-uu-high ledge at the far end
        build_geometry_from_brushes(&[
            box_brush(512.0, 128.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(256.0, 128.0, 8.0, Vec3::new(256.0, 0.0, -120.0), CsgOper::Add),
        ])
        .unwrap()
    }

    #[test]
    fn zero_extent_line_check_reports_the_wall_hit() {
        let m = CollisionModel::level(&room());
        let start = Vec3::new(0.0, 0.0, 0.0);
        let h = m.line_check(Vec3::new(600.0, 0.0, 0.0), start, Vec3::new(0.0, 0.0, 0.0), 0).expect("the +X wall blocks");
        // hit at x = 256, pulled back half a unit, normal facing the ray
        assert!((h.location.x - 255.5).abs() < 0.01, "{:?}", h);
        assert!((h.time - 255.5 / 600.0).abs() < 1e-4);
        assert_eq!(h.normal, Vec3::new(-1.0, 0.0, 0.0));
        assert!(m.line_check(Vec3::new(200.0, 100.0, 50.0), start, Vec3::new(0.0, 0.0, 0.0), 0).is_none());
        assert!(m.fast_line_check(Vec3::new(200.0, 100.0, 50.0), start));
        assert!(!m.fast_line_check(Vec3::new(0.0, 0.0, 400.0), start));
    }

    #[test]
    fn box_sweep_stops_short_of_the_wall_by_the_extent() {
        let m = CollisionModel::level(&room());
        let extent = Vec3::new(18.0, 18.0, 39.0);
        let start = Vec3::new(0.0, 0.0, 0.0);
        let h = m.line_check(Vec3::new(300.0, 0.0, 0.0), start, extent, 0).expect("the wall blocks the box");
        // contact when the box face reaches x = 256: t = 238/300, then the 0.1 pull-back
        let t_contact = 238.0 / 300.0;
        assert!((h.time - (t_contact - 0.1)).abs() < 1e-3, "{:?}", h);
        assert_eq!(h.normal, Vec3::new(-1.0, 0.0, 0.0));
        // a sweep that stays clear of every wall
        assert!(m.line_check(Vec3::new(200.0, 0.0, 0.0), start, extent, 0).is_none());
        // the floor: dropping the box from the centre hits at z = -128 + 39
        let h = m.line_check(Vec3::new(0.0, 0.0, -200.0), start, extent, 0).expect("floor");
        assert!((h.time - ((89.0 / 200.0) - 0.1)).abs() < 1e-3, "{:?}", h);
        assert_eq!(h.normal, Vec3::new(0.0, 0.0, 1.0));
    }

    #[test]
    fn point_check_and_find_spot() {
        let w = World::new(&room(), &[], vec![], zone0()).unwrap();
        let extent = Vec3::new(18.0, 18.0, 39.0);
        assert!(w.single_point_check(Vec3::new(0.0, 0.0, 0.0), extent));
        assert!(!w.single_point_check(Vec3::new(250.0, 0.0, 0.0), extent), "box overlapping the +X wall");
        assert!(!w.single_point_check(Vec3::new(400.0, 0.0, 0.0), extent), "box inside solid");
        // FindSpot nudges a box overlapping the wall back inside
        let mut loc = Vec3::new(250.0, 0.0, 0.0);
        assert!(w.find_spot(extent, &mut loc));
        assert!(loc.x <= 238.0 + 1e-3 && loc.x > 200.0, "{loc:?}");
        assert!(w.single_point_check(loc, extent));
        // deep in solid: no spot within 1.5×|extent|²
        let mut loc = Vec3::new(600.0, 0.0, 0.0);
        assert!(!w.find_spot(extent, &mut loc));
    }

    #[test]
    fn point_region_zone_numbers() {
        let m = room();
        let w = World::new(&m, &[], vec![], zone0()).unwrap();
        let inside = w.point_region(Vec3::new(0.0, 0.0, 0.0));
        assert!(inside > 0, "an open leaf has a non-zero zone (got {inside})");
        assert_eq!(w.point_region(Vec3::new(600.0, 0.0, 0.0)), 0, "solid side → zone 0");
    }

    #[test]
    fn move_actor_pull_back_and_return_code() {
        let w = World::new(&room(), &[], vec![], zone0()).unwrap();
        let mut s = Scout { collision_radius: 18.0, collision_height: 39.0, ..Scout::new() };
        assert!(s.far_move_actor(&w, Vec3::new(200.0, 0.0, 0.0), false));
        let mut hit = CheckResult::clear();
        // 16 uu forward: the wall at x=256 is reachable for the box face at x=218+16=234 → clear
        assert!(s.move_actor(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit));
        assert_eq!(hit.time, 1.0);
        assert!((s.location.x - 216.0).abs() < 1e-4);
        // walk into the wall: contact at t = 22/102 (box face at x = 238), the box pull-back is a
        // tenth of the trace (`max(0.1, 0.1/Dist)`, `0x101ae922`), then MoveActor stops 2 uu short
        assert!(s.move_actor(&w, Vec3::new(100.0, 0.0, 0.0), &mut hit));
        let t = 22.0 / 102.0 - 0.1;
        assert!((hit.time - (102.0 * t - 2.0) / 100.0).abs() < 1e-3, "{:?}", hit);
        assert!((s.location.x - (216.0 + 102.0 * t - 2.0)).abs() < 0.05, "{:?}", s.location);
        // a 16-uu step from 2 uu short of the wall: contact at 2/18, minus the 0.1 pull-back → 0.011,
        // moved = 18 * 0.011 = 0.2 ≤ 2 → no move, Time 0
        s.location = Vec3::new(236.0, 0.0, 0.0);
        assert!(!s.move_actor(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit));
        assert_eq!(hit.time, 0.0);
        assert_eq!(s.location.x, 236.0);
        // the drop probe from the centre lands on the floor
        s.location = Vec3::new(0.0, 0.0, 0.0);
        assert!(s.move_actor(&w, Vec3::new(0.0, 0.0, -200.0), &mut hit));
        assert!(hit.time < 1.0);
        assert_eq!(hit.normal, Vec3::new(0.0, 0.0, 1.0));
        // contact at 89/202, pulled back 0.1 of the trace, then 2 uu
        let t = 89.0 / 202.0 - 0.1;
        assert!((s.location.z - (-(202.0 * t - 2.0))).abs() < 0.05, "{:?}", s.location);
    }

    #[test]
    fn step_geometry_is_a_floor_hit_not_a_wall() {
        let w = World::new(&corridor_with_step(), &[], vec![], zone0()).unwrap();
        let mut s = Scout { collision_radius: 18.0, collision_height: 39.0, ..Scout::new() };
        assert!(s.far_move_actor(&w, Vec3::new(-40.0, 0.0, -128.0 + 39.0), false));
        let z0 = s.location.z;
        let mut hit = CheckResult::clear();
        // walking east into the 16-uu step: blocked by its vertical face
        assert!(s.move_actor(&w, Vec3::new(60.0, 0.0, 0.0), &mut hit));
        assert!(hit.time < 1.0, "the step face blocks");
        assert!((hit.normal.x + 1.0).abs() < 1e-3, "{:?}", hit.normal);
        // step up, finish, step down: lands on the step
        assert!(s.move_actor(&w, Vec3::new(0.0, 0.0, 25.0), &mut hit));
        assert!(s.move_actor(&w, Vec3::new(40.0, 0.0, 0.0), &mut hit));
        s.move_actor(&w, Vec3::new(0.0, 0.0, -25.0), &mut hit);
        assert!(hit.time < 1.0 && hit.normal.z > 0.7);
        // the step-down stops 2 uu + a tenth of the 27-uu trace above the step's top
        assert!(s.location.z > z0 + 16.0 && s.location.z < z0 + 16.0 + 5.0, "{:?} vs {z0}", s.location);
    }

    /// Movers are validated but never traced (module doc): a door across the room neither occludes
    /// a line check nor blocks the scout.
    #[test]
    fn movers_do_not_collide() {
        let door = crate::bspcsg::build_brush_model(&box_brush(16.0, 128.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add).polys).unwrap().0;
        let mover = MoverIn { name: "Door".into(), model: door, location: Vec3::new(0.0, 0.0, 0.0), rotation: [0, 0, 0], pre_pivot: Vec3::new(0.0, 0.0, 0.0), b_block_actors: true };
        let w = World::new(&room(), std::slice::from_ref(&mover), vec![], zone0()).unwrap();
        let (a, b) = (Vec3::new(-200.0, 50.0, 0.0), Vec3::new(200.0, 50.0, 0.0));
        assert!(w.single_line_check(b, a, Vec3::new(0.0, 0.0, 0.0)).is_none());
        let mut s = Scout { collision_radius: 18.0, collision_height: 39.0, location: a, ..Scout::new() };
        let mut hit = CheckResult::clear();
        assert!(s.move_actor(&w, Vec3::new(400.0, 0.0, 0.0), &mut hit));
        assert_eq!(hit.time, 1.0);
        // a Mover without BSP nodes is refused by name
        let bad = MoverIn { model: Model::default(), ..mover };
        let err = World::new(&room(), &[bad], vec![], zone0()).unwrap_err();
        assert!(err.0.contains("Door"), "{err}");
    }
}
