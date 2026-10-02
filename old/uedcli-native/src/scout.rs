//! The scout's traversal tests — `APawn::pointReachable → Reachable → walk/fly/swimReachable`
//! with `walkMove`/`flyMove`/`swimMove`, `jumpLanding`, `SuggestJumpVelocity`, `FindBestJump`,
//! `FindJumpUp`, `TwoWallAdjust` — and the real `ReachWorld` over `collision::World`.
//!
//! Readings: `findings/11-ued-reachability.md` §4 (`ued`, base `0x10000000`) and
//! `findings/21-dx-reachability-and-ai.md` Part 1 (`dx`, base `0x10300000`); the two differ only
//! by the `Preset` switches (`jump_fall_limit`, `find_jump_up`) and the scout parameters.

use crate::collision::{add, neg, safe_normal, scale, size_squared, CheckResult, Scout, World};
use crate::model::Vec3;
use crate::paths::{MoverHit, NavIn, Pawn, Preset, ReachWorld, R_FLY, R_JUMP, R_SPECIAL, R_SWIM, R_WALK};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Physics {
    Walking,
    Swimming,
    Flying,
}

/// The `AScout` with the `APawn` fields the tests read.
#[derive(Debug, Clone, PartialEq)]
pub struct ScoutPawn {
    pub scout: Scout,
    pub physics: Physics,
    pub jump_z: f32,
    pub ground_speed: f32,
    pub max_step_height: f32,
    pub base_eye_height: f32,
    pub can_walk: bool,
    pub can_jump: bool,
    pub can_swim: bool,
    pub can_fly: bool,
}

fn vz(z: f32) -> Vec3 {
    Vec3::new(0.0, 0.0, z)
}

impl ScoutPawn {
    /// `FReachSpec::defineFor`'s scout setup (`ued 0x10193d14`–`0x10193d5e`, `dx 0xd95dc`–`0xd9614`):
    /// walking, walk|jump|swim, no fly, the preset's `JumpZ`/`GroundSpeed`/`MaxStepHeight`.
    pub fn for_define(p: &Preset) -> ScoutPawn {
        ScoutPawn {
            scout: Scout::new(),
            physics: Physics::Walking,
            jump_z: p.scout_jump_z,
            ground_speed: p.scout_ground_speed,
            max_step_height: p.scout_max_step_height,
            // `dx` sets 0; the UED22 `Engine.u` Scout default is 0 too (`resolve_class_defaults`).
            base_eye_height: p.scout_base_eye_height.unwrap_or(0.0),
            can_walk: true,
            can_jump: true,
            can_swim: true,
            can_fly: false,
        }
    }

    fn loc(&self) -> Vec3 {
        self.scout.location
    }

    fn restore(&mut self, w: &World, loc: Vec3) {
        self.scout.far_move_actor(w, loc, true);
    }

    fn region_water(&self, w: &World) -> bool {
        w.zone(self.scout.region_zone).b_water
    }

    fn region_hostile(&self, w: &World) -> bool {
        w.zone(self.scout.region_zone).is_hostile()
    }

    fn foot_hostile(&self, w: &World) -> bool {
        w.zone(self.scout.foot_zone).is_hostile()
    }

    /// `walkMove(Delta, Hit, GoalActor = NULL, threshold, bAdjust)` (`ued 0x101841b0`, `dx 0xc3290`):
    /// 1 advanced ≥ threshold, 0 blocked or too short, −1 ledge/steep floor.
    pub fn walk_move(&mut self, w: &World, delta: Vec3, hit: &mut CheckResult, threshold: f32, b_adjust: bool) -> i32 {
        let start = self.loc();
        let mut delta = Vec3::new(delta.x, delta.y, 0.0);
        let grav_dir = if w.zone(self.scout.region_zone).gravity.z > 0.0 { 1.0 } else { -1.0 };
        let down = vz(grav_dir * self.max_step_height);
        let up = neg(down);
        self.scout.move_actor(w, delta, hit);
        if hit.time < 1.0 {
            delta = scale(delta, 1.0 - hit.time);
            self.scout.move_actor(w, up, hit);
            self.scout.move_actor(w, delta, hit);
            self.scout.move_actor(w, down, hit);
            if hit.time < 1.0 && hit.normal.z < 0.7 {
                if b_adjust {
                    self.restore(w, start);
                }
                return 0;
            }
        }
        let loc = self.loc();
        self.scout.move_actor(w, vz(grav_dir * (self.max_step_height + 2.0)), hit);
        if hit.time == 1.0 {
            self.restore(w, if b_adjust { start } else { loc });
            return -1;
        }
        if hit.normal.z < 0.7 {
            self.restore(w, start);
            return -1;
        }
        if threshold * threshold > size_squared(self.loc().sub(&start)) {
            if b_adjust {
                self.restore(w, start);
            }
            return 0;
        }
        1
    }

    /// `flyMove` (`ued 0x10181f90`): no gravity test, no drop probe, no slope test.
    fn fly_move(&mut self, w: &World, delta: Vec3, threshold: f32, b_adjust: bool) -> i32 {
        let start = self.loc();
        let mut hit = CheckResult::clear();
        self.scout.move_actor(w, delta, &mut hit);
        if hit.time < 1.0 {
            let rest = scale(delta, 1.0 - hit.time);
            self.scout.move_actor(w, vz(self.max_step_height), &mut hit);
            self.scout.move_actor(w, rest, &mut hit);
        }
        if threshold * threshold > size_squared(self.loc().sub(&start)) {
            if b_adjust {
                self.restore(w, start);
            }
            return 0;
        }
        1
    }

    /// `findWaterLine(InWater, OutOfWater)` (`dx 0xd3b10`): bisection to 1 uu; the last point still
    /// in water.  🔬 The exact endpoint choice was not decoded.
    fn find_water_line(&self, w: &World, in_water: Vec3, out_of_water: Vec3) -> Vec3 {
        let (mut a, mut b) = (in_water, out_of_water);
        while b.sub(&a).size() > 1.0 {
            let mid = scale(add(a, b), 0.5);
            if w.zone(w.point_region(mid)).b_water {
                a = mid;
            } else {
                b = mid;
            }
        }
        a
    }

    /// `swimMove` (`ued 0x10183870`): `flyMove` that steps back to the water line on leaving it.
    fn swim_move(&mut self, w: &World, delta: Vec3, threshold: f32, b_adjust: bool) -> i32 {
        let start = self.loc();
        let mut hit = CheckResult::clear();
        self.scout.move_actor(w, delta, &mut hit);
        if !self.region_water(w) {
            let wl = self.find_water_line(w, start, self.loc());
            if wl != self.loc() {
                let back = wl.sub(&self.loc());
                self.scout.move_actor(w, back, &mut hit);
            }
            return 0;
        }
        if hit.time < 1.0 {
            let rest = scale(delta, 1.0 - hit.time);
            self.scout.move_actor(w, vz(self.max_step_height), &mut hit);
            self.scout.move_actor(w, rest, &mut hit);
        }
        if threshold * threshold > size_squared(self.loc().sub(&start)) {
            if b_adjust {
                self.restore(w, start);
            }
            return 0;
        }
        1
    }

    /// `AActor::TwoWallAdjust` (UT `UnPhysic.cpp`, 📖 — called with these arguments by
    /// `jumpLanding`/`findScoutStart`, body not decoded).
    fn two_wall_adjust(desired_dir: Vec3, delta: &mut Vec3, hit_normal: Vec3, old_hit_normal: Vec3, hit_time: f32) {
        if old_hit_normal.dot(&hit_normal) <= 0.0 {
            let new_dir = safe_normal(hit_normal.cross(&old_hit_normal));
            *delta = scale(new_dir, delta.dot(&new_dir) * (1.0 - hit_time));
            if desired_dir.dot(delta) < 0.0 {
                *delta = neg(*delta);
            }
        } else {
            *delta = scale(delta.sub(&scale(hit_normal, delta.dot(&hit_normal))), 1.0 - hit_time);
            if delta.dot(&desired_dir) <= 0.0 {
                *delta = Vec3::new(0.0, 0.0, 0.0);
            }
        }
    }

    /// `jumpLanding(testVel, Landing, movePawn)` (`ued 0x101826b0`, `dx 0xc2530`): the ballistic
    /// simulation at `dt = 0.1`.  Returns the landing spot.
    pub fn jump_landing(&mut self, w: &World, mut test_vel: Vec3, move_pawn: bool) -> Vec3 {
        let orig = self.loc();
        let mut landed = false;
        let mut ticks = 0;
        while !landed {
            let z = w.zone(self.scout.region_zone).clone();
            test_vel = add(scale(test_vel, 1.0 - 0.1 * z.fluid_friction), scale(z.gravity, 0.1));
            let delta = scale(add(test_vel, z.velocity), 0.1);
            let mut hit = CheckResult::clear();
            self.scout.move_actor(w, delta, &mut hit);
            if self.region_water(w) {
                landed = true;
            } else if hit.time < 1.0 {
                if hit.normal.z > 0.7 {
                    landed = true;
                } else {
                    let old_normal = hit.normal;
                    let mut slide = scale(delta.sub(&scale(hit.normal, delta.dot(&hit.normal))), 1.0 - hit.time);
                    if slide.dot(&delta) >= 0.0 {
                        self.scout.move_actor(w, slide, &mut hit);
                        if hit.time < 1.0 {
                            landed |= hit.normal.z > 0.7;
                            Self::two_wall_adjust(safe_normal(delta), &mut slide, hit.normal, old_normal, hit.time);
                            self.scout.move_actor(w, slide, &mut hit);
                            landed |= hit.normal.z > 0.7;
                        }
                    }
                }
            }
            ticks += 1;
            if self.scout.region_zone == 0 || ticks > 35 || size_squared(test_vel) > 2_500_000.0 {
                self.restore(w, orig);
                landed = true;
            }
        }
        let landing = self.loc();
        if !move_pawn {
            self.restore(w, orig);
        }
        landing
    }

    /// `SuggestJumpVelocity(Dest, Vel)` (`ued 0x1017db40` 🔬, `dx 0xc2c80`): integrate the vertical
    /// throw at `dt = 0.05` to the time it passes `Dest.Z` on the way down, then size the horizontal
    /// speed to arrive then, capped at `GroundSpeed`.
    pub fn suggest_jump_velocity(&self, w: &World, dest: Vec3, vel: &mut Vec3) {
        let mut g = w.zone(self.scout.region_zone).gravity.z;
        if g >= 0.0 {
            g = -100.0;
        }
        let dz = dest.z - self.loc().z;
        let mut vz_ = vel.z;
        let mut z = 0.0f32;
        let mut t = 0.0f32;
        loop {
            vz_ += g * 0.05;
            z += vz_ * 0.05;
            t += 0.05;
            if z <= dz && vz_ <= 0.0 {
                break;
            }
        }
        if vz_.abs() > 1.0 {
            t -= (z - dz) / vz_;
        }
        let d = dest.sub(&self.loc());
        let flat = Vec3::new(d.x, d.y, 0.0);
        let dist = flat.size();
        let speed = if t > 0.0 { self.ground_speed.min(dist / t) } else { self.ground_speed };
        let dir = safe_normal(flat);
        vel.x = dir.x * speed;
        vel.y = dir.y * speed;
    }

    /// `FindBestJump(Dest, vel, Landing, movePawn = 1)` (`ued 0x1017b150`, `dx 0xc2f50`): 1 when the
    /// jump lands more than 8 uu closer (and, under the `dx` preset, drops less than 350 uu).
    pub fn find_best_jump(&mut self, w: &World, p: &Preset, dest: Vec3, mut vel: Vec3) -> i32 {
        let orig = self.loc();
        vel.z = self.jump_z;
        self.suggest_jump_velocity(w, dest, &mut vel);
        let landing = self.jump_landing(w, vel, true);
        if self.foot_hostile(w) {
            return 0;
        }
        if !self.can_swim && self.region_water(w) {
            return 0;
        }
        let closer = dest.sub(&orig).size() - dest.sub(&landing).size() > 8.0;
        let fall_ok = p.jump_fall_limit.map_or(true, |limit| orig.z - landing.z < limit);
        (closer && fall_ok) as i32
    }

    /// `FindJumpUp(Dest, vel, …)` (`ued 0x1017b320`): one `walkMove` of the old step length with a
    /// 48-uu step-up.
    pub fn find_jump_up(&mut self, w: &World, vel: Vec3) -> i32 {
        let saved = self.max_step_height;
        self.max_step_height = 48.0;
        let mut hit = CheckResult::clear();
        let r = self.walk_move(w, scale(safe_normal(vel), saved), &mut hit, 4.1, true);
        self.max_step_height = saved;
        if r == 5 {
            1
        } else {
            r
        }
    }

    /// `walkReachable(Dest, Threshold, reachFlags, GoalActor = NULL)` (`ued 0x101846e0`, `dx 0xc1b70`).
    pub fn walk_reachable(&mut self, w: &World, p: &Preset, dest: Vec3, threshold: f32, mut flags: i32) -> i32 {
        flags |= R_WALK;
        let mut success = false;
        let mut stillmoving = 1;
        let mut ticks = 100;
        let orig = self.loc();
        let orig_vel = self.scout.velocity;
        let threshold2 = threshold * threshold;
        let mut move_size = 16.0f32; // editor value (`ued 0x101847a6`, `dx 0xc1be7`)
        let move_size2 = move_size * move_size;
        let max_height = self.scout.collision_height;
        let mut hit = CheckResult::clear();
        while stillmoving == 1 {
            let d3 = dest.sub(&self.loc());
            let delta_z = d3.z;
            let delta = Vec3::new(d3.x, d3.y, 0.0);
            let dist2 = delta.x * delta.x + delta.y * delta.y;
            if delta_z > max_height {
                let d = (delta_z - max_height) as f64;
                if 0.8 * d * d > dist2 as f64 {
                    stillmoving = 0;
                    continue;
                }
            }
            if dist2 > threshold2 {
                let r = if move_size2 > dist2 {
                    self.walk_move(w, delta, &mut hit, 8.0, false)
                } else {
                    self.walk_move(w, scale(safe_normal(delta), move_size), &mut hit, 4.1, false)
                };
                stillmoving = r;
                if r != 1 {
                    if self.scout.region_zone == 0 {
                        stillmoving = 0;
                        success = false;
                    } else if self.can_fly {
                        stillmoving = 0;
                        flags = self.fly_reachable(w, p, dest, threshold, flags);
                        success = flags != 0;
                    } else if self.can_jump {
                        flags |= R_JUMP;
                        let vel = scale(safe_normal(delta), self.ground_speed);
                        if r == -1 {
                            stillmoving = self.find_best_jump(w, p, dest, vel);
                        } else if r == 0 && p.find_jump_up {
                            stillmoving = self.find_jump_up(w, vel);
                        }
                    } else if r == -1 && move_size > self.max_step_height {
                        stillmoving = 1;
                        move_size = self.max_step_height;
                    }
                }
                if self.foot_hostile(w) {
                    stillmoving = 0;
                    success = false;
                }
                if self.region_water(w) {
                    stillmoving = 0;
                    if self.can_swim && !self.region_hostile(w) {
                        flags = self.swim_reachable(w, p, dest, threshold, flags);
                        success = flags != 0;
                    }
                }
            } else {
                stillmoving = 0;
                if max_height > delta_z.abs() {
                    success = true;
                } else if 0.95 > hit.normal.z && hit.normal.z > 0.7 {
                    let nz = hit.normal.z;
                    let tan_a = (1.0 / (nz * nz) - 1.0).sqrt();
                    if delta_z < 0.0 && self.scout.collision_height + tan_a * self.scout.collision_radius > -delta_z {
                        success = true;
                    } else {
                        let goal_radius = 46.0f32;
                        if goal_radius > self.scout.collision_radius
                            && tan_a * (goal_radius + 15.0 - self.scout.collision_radius) + max_height > delta_z
                        {
                            success = true;
                        }
                    }
                }
            }
            ticks -= 1;
            if ticks < 0 {
                stillmoving = 0;
            }
        }
        self.restore(w, orig);
        self.scout.velocity = orig_vel;
        if success {
            flags
        } else {
            0
        }
    }

    /// `flyReachable` (`ued 0x101822c0`): 3-D arrival, step `max(200, CR)`.
    pub fn fly_reachable(&mut self, w: &World, p: &Preset, dest: Vec3, threshold: f32, mut flags: i32) -> i32 {
        flags |= R_FLY;
        let move_size = 200.0f32.max(self.scout.collision_radius);
        let mut ticks = 100;
        let orig = self.loc();
        let orig_vel = self.scout.velocity;
        let mut success = false;
        let mut stillmoving = 1;
        while stillmoving == 1 {
            let dir = dest.sub(&self.loc());
            let dist2 = size_squared(dir);
            if dist2 <= threshold * threshold && dir.z.abs() <= self.scout.collision_height {
                success = true;
                stillmoving = 0;
            } else {
                let r = if move_size * move_size > dist2 {
                    self.fly_move(w, dir, 8.0, false)
                } else {
                    self.fly_move(w, scale(safe_normal(dir), move_size), 4.1, false)
                };
                stillmoving = r;
                if r != 0 && self.region_water(w) {
                    stillmoving = 0;
                    if self.can_swim && !self.region_hostile(w) {
                        flags = self.swim_reachable(w, p, dest, threshold, flags);
                        success = flags != 0;
                    }
                }
            }
            ticks -= 1;
            if ticks < 0 {
                stillmoving = 0;
            }
        }
        self.restore(w, orig);
        self.scout.velocity = orig_vel;
        if success {
            flags
        } else {
            0
        }
    }

    /// `swimReachable` (`ued 0x10183c90`, `dx 0xc15a0`): like fly, plus the climb-out branch that
    /// reports exactly `R_WALK`.
    pub fn swim_reachable(&mut self, w: &World, p: &Preset, dest: Vec3, threshold: f32, mut flags: i32) -> i32 {
        flags |= R_SWIM;
        let move_size = 200.0f32.max(self.scout.collision_radius);
        let mut ticks = 100;
        let orig = self.loc();
        let orig_vel = self.scout.velocity;
        let mut success = false;
        let mut stillmoving = 1;
        while stillmoving == 1 {
            let dir = dest.sub(&self.loc());
            let dist2 = size_squared(dir);
            if dist2 <= threshold * threshold && dir.z.abs() <= self.scout.collision_height {
                success = true;
                stillmoving = 0;
            } else {
                let r = if move_size * move_size > dist2 {
                    self.swim_move(w, dir, 8.0, false)
                } else {
                    self.swim_move(w, scale(safe_normal(dir), move_size), 4.1, false)
                };
                stillmoving = r;
                if !self.region_water(w) {
                    stillmoving = 0;
                    if self.can_fly {
                        flags = self.fly_reachable(w, p, dest, threshold, flags);
                        success = flags != 0;
                    } else if self.can_walk && self.loc().z + 50.0 + self.max_step_height > dest.z {
                        let mut hit = CheckResult::clear();
                        let lift = (self.scout.collision_height + self.max_step_height).max(dest.z - self.loc().z);
                        self.scout.move_actor(w, vz(lift), &mut hit);
                        if hit.time == 1.0 {
                            success = self.fly_reachable(w, p, dest, threshold, flags) != 0;
                            flags = R_WALK;
                        }
                    }
                } else if self.region_hostile(w) {
                    stillmoving = 0;
                    success = false;
                }
            }
            ticks -= 1;
            if ticks < 0 {
                stillmoving = 0;
            }
        }
        self.restore(w, orig);
        self.scout.velocity = orig_vel;
        if success {
            flags
        } else {
            0
        }
    }

    /// `Reachable(Dest, Threshold, NULL)` (`ued 0x1017d8f0`, `dx 0xc1000`).
    pub fn reachable(&mut self, w: &World, p: &Preset, dest: Vec3, threshold: f32) -> i32 {
        if self.region_water(w) {
            return self.swim_reachable(w, p, dest, threshold, 0);
        }
        match self.physics {
            Physics::Walking | Physics::Swimming => self.walk_reachable(w, p, dest, threshold, 0),
            Physics::Flying => self.fly_reachable(w, p, dest, threshold, 0),
        }
    }

    /// `pointReachable(aPoint, bKnowVisible)` (`ued 0x10183340`, `dx 0xc0d30`) in the editor (no
    /// range cap).
    pub fn point_reachable(&mut self, w: &World, p: &Preset, dest: Vec3, know_visible: bool) -> i32 {
        let pr = w.zone(w.point_region(dest));
        if !self.region_water(w) && !self.can_swim && pr.b_water {
            return 0;
        }
        if !w.zone(self.scout.foot_zone).b_pain && pr.b_pain && pr.damage_type != "none" {
            return 0;
        }
        if !know_visible {
            let eye = add(self.loc(), vz(self.base_eye_height));
            if !w.level().fast_line_check(dest, eye) {
                return 0;
            }
        }
        let real = self.loc();
        let mut dest = dest;
        if self.scout.far_move_actor(w, dest, false) {
            dest = self.loc();
            self.restore(w, real);
        }
        self.reachable(w, p, dest, 15.0)
    }
}

/// The real `ReachWorld`: the collision world plus the scout the build drives.
pub struct CollisionWorld {
    pub world: World,
    pub pawn: ScoutPawn,
    pub preset: Preset,
}

impl CollisionWorld {
    pub fn new(world: World, preset: Preset) -> CollisionWorld {
        let pawn = ScoutPawn::for_define(&preset);
        CollisionWorld { world, pawn, preset }
    }

    fn sync(&mut self, pawn: &Pawn) {
        self.pawn.scout.location = pawn.location;
        self.pawn.scout.collision_radius = pawn.collision_radius;
        self.pawn.scout.collision_height = pawn.collision_height;
        self.pawn.scout.set_actor_zone(&self.world);
    }
}

impl ReachWorld for CollisionWorld {
    fn line_visible(&mut self, from: Vec3, to: Vec3) -> bool {
        self.world.single_line_check(to, from, Vec3::new(0.0, 0.0, 0.0)).is_none()
    }

    fn probe(&mut self, a: &NavIn, b: &NavIn, radius: f32, height: f32) -> i32 {
        let p = self.preset.clone();
        self.pawn = ScoutPawn { scout: self.pawn.scout.clone(), ..ScoutPawn::for_define(&p) };
        self.pawn.scout.collision_radius = radius;
        self.pawn.scout.collision_height = height;
        let placed = if p.scout_on_traced_floor {
            // `dx 0xd97ca`: the floor 79 uu under A, else `A.Z − A.CollisionHeight`.
            let floor = match self.world.single_line_check(add(a.location, vz(-79.0)), a.location, Vec3::new(0.0, 0.0, 0.0)) {
                Some(h) => h.location,
                None => add(a.location, vz(-a.collision_height)),
            };
            self.pawn.scout.far_move_actor(&self.world, add(floor, vz(height)), false)
        } else {
            self.pawn.scout.far_move_actor(&self.world, a.location, false)
        };
        if !placed {
            return 0;
        }
        self.pawn.point_reachable(&self.world, &p, b.location, p.know_visible)
    }

    fn vis_scout(&mut self, node: &NavIn, radius: f32, height: f32) -> Pawn {
        self.pawn.scout.collision_radius = radius;
        self.pawn.scout.collision_height = height;
        self.pawn.scout.far_move_actor(&self.world, node.location, false);
        Pawn {
            location: self.pawn.scout.location,
            collision_radius: radius,
            collision_height: height,
            base_eye_height: self.pawn.base_eye_height,
            // `calcMoveFlags`: walk|jump|swim from `defineFor`, `bCanDoSpecial` set by `addVisNoReach`.
            move_flags: R_WALK | R_JUMP | R_SWIM | R_SPECIAL,
            b_is_player: false,
            b_can_open_doors: false,
            move_target: node.index as i32,
        }
    }

    fn fast_line_check(&mut self, end: Vec3, start: Vec3) -> bool {
        self.world.level().fast_line_check(end, start)
    }

    fn point_reachable(&mut self, pawn: &Pawn, dest: Vec3, know_visible: bool) -> i32 {
        self.sync(pawn);
        let p = self.preset.clone();
        self.pawn.point_reachable(&self.world, &p, dest, know_visible)
    }

    fn far_move_test(&mut self, pawn: &mut Pawn, dest: Vec3) -> bool {
        self.sync(pawn);
        if self.pawn.scout.far_move_actor(&self.world, dest, false) {
            pawn.location = self.pawn.scout.location;
            return true;
        }
        false
    }

    /// No Mover is ever traced (`collision.rs` module doc), so the door gate never fires.
    fn line_hits_mover(&mut self, _end: Vec3, _start: Vec3) -> Option<MoverHit> {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::build::{build_geometry_from_brushes, BrushInput};
    use crate::collision::ZoneIn;
    use crate::csg::CsgOper;
    use crate::fpoly::FPoly;
    use crate::paths::{define_paths, NavKind};

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

    /// A 1024-long corridor (±128 Y, floor −128, ceiling +128) with a 16-uu step over x ∈ [0, 256]
    /// (top −112) and a 44-uu-high platform over x ∈ [384, 512] (top −84).
    fn corridor() -> World {
        let m = build_geometry_from_brushes(&[
            box_brush(512.0, 128.0, 128.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Subtract),
            box_brush(128.0, 128.0, 8.0, Vec3::new(128.0, 0.0, -120.0), CsgOper::Add),
            box_brush(64.0, 128.0, 22.0, Vec3::new(448.0, 0.0, -106.0), CsgOper::Add),
        ])
        .unwrap();
        World::new(&m, &[], vec![], zone0()).unwrap()
    }

    fn nav(index: usize, x: f32, z: f32) -> NavIn {
        NavIn { index, kind: NavKind::NavigationPoint, location: Vec3::new(x, 0.0, z), rotation: [0, 0, 0], collision_radius: 12.0, collision_height: 15.0, b_one_way_path: false, lift_tag: String::new(), url: String::new(), tag: format!("n{index}") }
    }

    #[test]
    fn walk_move_return_codes() {
        let w = corridor();
        let p = Preset::ued22_469();
        let mut s = ScoutPawn::for_define(&p);
        s.scout.collision_radius = 18.0;
        s.scout.collision_height = 39.0;
        assert!(s.scout.far_move_actor(&w, Vec3::new(-300.0, 0.0, -128.0 + 39.0), false));
        let mut hit = CheckResult::clear();
        assert_eq!(s.walk_move(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit, 4.1, false), 1, "open floor: moved");
        // onto the 16-uu step: still 1 (step-up within MaxStepHeight 25)
        s.scout.far_move_actor(&w, Vec3::new(-10.0, 0.0, -128.0 + 39.0), true);
        let z0 = s.scout.location.z;
        assert_eq!(s.walk_move(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit, 4.1, false), 1, "a 16-uu step is walked");
        assert!(s.scout.location.z > z0 + 10.0, "{:?}", s.scout.location);
        // into the 44-uu platform face from the corridor floor.  The first call returns 1: the
        // step-up/step-down pair leaves the scout ~4.7 uu higher (each box sweep pulls back a tenth
        // of its trace, then MoveActor 2 uu), and that rise alone exceeds the 4.1 threshold.  The
        // second call, from that hover, finds no floor within MaxStepHeight+2 on the step-down and
        // ends where it started: 0.  Pinned as the decoded behaviour (the pathlab golden agrees).
        s.scout.far_move_actor(&w, Vec3::new(360.0, 0.0, -128.0 + 39.0), true);
        let z0 = s.scout.location.z;
        assert_eq!(s.walk_move(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit, 4.1, false), 1, "first call: the hover counts as progress");
        assert!(s.scout.location.z - z0 > 4.1 && s.scout.location.z - z0 < 6.0, "{:?} vs {z0}", s.scout.location);
        assert!(s.scout.location.x < 364.0);
        assert_eq!(s.walk_move(&w, Vec3::new(16.0, 0.0, 0.0), &mut hit, 4.1, false), 0, "second call: a wall blocks");
        // off the platform's west edge (the box clears x = 384 after the step): a ledge (−1)
        s.scout.far_move_actor(&w, Vec3::new(378.0, 0.0, -84.0 + 39.0), true);
        assert_eq!(s.walk_move(&w, Vec3::new(-16.0, 0.0, 0.0), &mut hit, 4.1, false), -1, "no floor within MaxStepHeight+2");
        // too short a move: 0
        s.scout.far_move_actor(&w, Vec3::new(-300.0, 0.0, -128.0 + 39.0), true);
        assert_eq!(s.walk_move(&w, Vec3::new(2.0, 0.0, 0.0), &mut hit, 4.1, false), 0);
    }

    #[test]
    fn corridor_edges_walk_step_and_jump() {
        // nodes 15.1 uu above their floor (a PathNode's own half-height, as retail places them): the
        // dx preset's 10-uu-tall scout must arrive within |ΔZ| < CollisionHeight of the node
        let navs = vec![nav(0, -400.0, -128.0 + 15.1), nav(1, -100.0, -128.0 + 15.1), nav(2, 200.0, -112.0 + 15.1), nav(3, 448.0, -84.0 + 15.1)];
        for (p, name) in [(Preset::ued22_469(), "ued"), (Preset::deusex_1112fm(), "dx")] {
            let mut cw = CollisionWorld::new(corridor(), p.clone());
            let (g, _) = define_paths(&mut cw, &p, &navs).unwrap();
            let edge = |a: i32, b: i32| g.specs.iter().find(|s| s.start == a && s.end == b).copied();
            let e01 = edge(0, 1).unwrap_or_else(|| panic!("{name}: flat edge 0→1 missing"));
            assert_eq!(e01.reach_flags, R_WALK, "{name}: flat corridor is WALK");
            assert_eq!(e01.distance, 300);
            let e12 = edge(1, 2).unwrap_or_else(|| panic!("{name}: step edge 1→2 missing"));
            assert_eq!(e12.reach_flags, R_WALK, "{name}: a 16-uu step is WALK");
            let e21 = edge(2, 1).unwrap_or_else(|| panic!("{name}: step-down edge 2→1 missing"));
            assert_eq!(e21.reach_flags, R_WALK, "{name}: a 16-uu drop is WALK");
            // the 44-uu drop off the platform: WALK|JUMP (a ledge accepted by FindBestJump)
            let e32 = edge(3, 2).unwrap_or_else(|| panic!("{name}: drop edge 3→2 missing"));
            assert_eq!(e32.reach_flags, R_WALK | R_JUMP, "{name}: a non-stair drop is WALK|JUMP");
            // the 44-uu climb: UED22 takes it (FindJumpUp's 48-uu step-up); the pathlab golden pins
            // the real climb thresholds, the dx outcome is not asserted here
            if name == "ued" {
                let e23 = edge(2, 3).unwrap_or_else(|| panic!("{name}: climb edge 2→3 missing"));
                assert_eq!(e23.reach_flags & R_WALK, R_WALK, "{name}: climb {e23:?}");
            }
            // sizes: the UED22 sweep saturates at 70×70 in a 256-wide, 256-high corridor
            if name == "ued" {
                assert_eq!((e01.collision_radius, e01.collision_height), (70, 70));
            } else {
                assert_eq!((e01.collision_radius, e01.collision_height), (115, 79));
            }
        }
    }

    #[test]
    fn suggest_jump_velocity_caps_at_ground_speed() {
        let w = corridor();
        let p = Preset::ued22_469();
        let mut s = ScoutPawn::for_define(&p);
        s.scout.far_move_actor(&w, Vec3::new(0.0, 0.0, -128.0 + 39.0), false);
        let mut vel = Vec3::new(0.0, 0.0, s.jump_z);
        s.suggest_jump_velocity(&w, Vec3::new(900.0, 0.0, -128.0 + 39.0), &mut vel);
        assert!((vel.x - 320.0).abs() < 1e-3 && vel.y == 0.0 && vel.z == 320.0, "{vel:?}");
        let mut vel = Vec3::new(0.0, 0.0, s.jump_z);
        s.suggest_jump_velocity(&w, Vec3::new(100.0, 0.0, -128.0 + 39.0), &mut vel);
        assert!(vel.x > 100.0 && vel.x < 320.0, "{vel:?}");
    }
}
