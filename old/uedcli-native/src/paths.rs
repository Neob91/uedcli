//! The AI path build — `PATHS DEFINE`'s `definePaths`: reachspec edges (`addReachSpecs`), per-node
//! list bookkeeping (`insertReachSpec`), `Prune`, and `addVisNoReach` with the runtime route search
//! it runs.  Every geometric probe is behind `ReachWorld` (the collision layer), so the algorithmic
//! part is testable on its own: the goldens below replay retail and UED22 maps bit-exact.
//!
//! Spec: `PATHING-BUILD.md` §3; readings `findings/10-ued-pathbuilder.md` §4.4–4.10,
//! `findings/11-ued-reachability.md` §3, `findings/20-dx-pathbuilder.md` §3.28–3.33,
//! `findings/21-dx-reachability-and-ai.md`.  RVAs: `ued` = UED22 `Engine.dll` (base
//! `0x10000000`), `dx` = Deus Ex 1112fm `Engine.dll` (base `0x10300000`).  The two engines differ
//! only by the constants in `Preset`.

use crate::model::Vec3;

pub const R_WALK: i32 = 1;
pub const R_FLY: i32 = 2;
pub const R_SWIM: i32 = 4;
pub const R_JUMP: i32 = 8;
/// Lift / teleporter / warp-zone edges (`ued 0x10176f76`, `dx 0xb2308`).
pub const R_SPECIAL: i32 = 32;

/// A path-build failure carrying the offending value; `lib.rs` maps it to `uedcli_native.PathError`.
#[derive(Debug, Clone)]
pub struct PathError(pub String);

impl std::fmt::Display for PathError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for PathError {}

// ---------------------------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------------------------

/// The class question the builder asks of a NavigationPoint, answered by Python from the game's
/// class hierarchy (`IsA` chains in `addReachSpecs`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavKind {
    NavigationPoint,
    LiftCenter,
    LiftExit,
    Teleporter,
    WarpZoneMarker,
    PlayerStart,
}

impl NavKind {
    pub fn parse(s: &str) -> Result<NavKind, PathError> {
        Ok(match s {
            "navigationpoint" => NavKind::NavigationPoint,
            "liftcenter" => NavKind::LiftCenter,
            "liftexit" => NavKind::LiftExit,
            "teleporter" => NavKind::Teleporter,
            "warpzonemarker" => NavKind::WarpZoneMarker,
            "playerstart" => NavKind::PlayerStart,
            _ => {
                return Err(PathError(format!(
                    "unknown nav class_kind {s:?} (expect navigationpoint|liftcenter|liftexit|teleporter|warpzonemarker|playerstart)"
                )))
            }
        })
    }
}

/// One NavigationPoint of the roster (`None` holes already removed; `index` = roster position).
/// `lift_tag`/`url`/`tag` arrive casefolded (every engine compare is case-insensitive).
#[derive(Debug, Clone)]
pub struct NavIn {
    pub index: usize,
    pub kind: NavKind,
    pub location: Vec3,
    /// `Rotation` as (Pitch, Yaw, Roll) in 65536-unit angles; read only with `b_one_way_path`.
    pub rotation: [i32; 3],
    pub collision_radius: f32,
    pub collision_height: f32,
    pub b_one_way_path: bool,
    pub lift_tag: String,
    /// `Teleporter.URL`; for a WarpZoneMarker the zone's `OtherSideURL`.
    pub url: String,
    /// `Actor.Tag`; for a WarpZoneMarker the zone's `ThisTag`.
    pub tag: String,
}

/// How the stored size / `Distance` is made an integer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SizeRounding {
    /// `appRound` = `cvtss2si`, round-half-even (`ued 0x10194174`).
    AppRound,
    /// `(INT)` truncation (`dx 0xd9b04`).
    Truncate,
}

/// The `Prune` 1.2 compare, exactly as each engine computes it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PruneCompare {
    /// `ued 0x101768f4`: `comiss`, prune iff `σ ≤ 1.2f·γ` in f32 (`1.2f` at `0x10212d5c`).
    F32NonStrict,
    /// `dx 0xb1a97`: x87 at 64-bit precision, `σ ≤ γ·0x3FF3333333333333` — the constant is the
    /// double below 1.2, so for integer distances the effective rule is strict `σ < 1.2·γ`.
    F64Strict,
}

/// One rule set (`uedcli/native/pathrules.py` owns the two presets; this is their shape).  Every
/// constant cites the instruction that holds it.
#[derive(Debug, Clone, PartialEq)]
pub struct Preset {
    /// `defineFor`: `ued 0x10193d18` 320 / `dx 0xd95e8` 120.
    pub scout_jump_z: f32,
    /// `ued 0x10193d54` 320 / `dx 0xd9604` 120.
    pub scout_ground_speed: f32,
    /// `ued 0x10193d5e` 25 / `dx 0xd960a` 25.
    pub scout_max_step_height: f32,
    /// `dx 0xd9614` sets 0; `ued` leaves the Scout class default (`None`).
    pub scout_base_eye_height: Option<f32>,
    /// `findBestReachable` radius phase: `SetCollisionSize(start, height)` — `ued 0x10193e0c`
    /// (18, 39) / `dx 0xd9709` (12, 10).  The first step is `radius_cap - radius_start`
    /// (`ued 0x10193e29` 70 / `dx 0xd971d` 115).
    pub radius_start: f32,
    pub radius_phase_height: f32,
    /// The height the scout takes after a radius-phase success: `ued 0x10193f16` 40 / `dx` 10.
    pub radius_phase_height_after_success: f32,
    pub radius_cap: f32,
    /// Stop when the halved step drops below this: `ued 0x10193f3d` 2 / `dx 0xd9950` 1.
    pub radius_stop: f32,
    /// Height phase start = scout height + bump: `ued 0x10193fca` 4 / `dx` 0.
    pub height_bump: f32,
    /// Radius held during the height phase: `dx 0xd99c3` 12; `ued` keeps the best radius (`None`).
    pub height_phase_radius: Option<f32>,
    /// `ued 0x10193ff4` 70 / `dx 0xd9770` 79.
    pub height_cap: f32,
    /// `ued 0x1019414a` 40 / `dx 0xd9a8b` 10.
    pub height_floor: f32,
    /// `ued 0x101940d5` 1 / `dx` 1.
    pub height_stop: f32,
    /// `dx 0xd9870`: `SingleLineCheck(TRACE_World)` A→B before sizing (movers included).
    pub los_precheck: bool,
    /// `dx 0xd97ca`: the scout stands on the traced floor under A (79-uu probe, else
    /// `A.Z − A.CollisionHeight`) plus its own height; `ued 0x10193e9b` places it at `A.Location`.
    pub scout_on_traced_floor: bool,
    /// `pointReachable(B, bKnowVisible)`: `dx 0xd9905` 1 / `ued 0x10193ec5` 0.
    pub know_visible: bool,
    pub size_rounding: SizeRounding,
    /// `FindBestJump` fall limit: `dx 0xc30ce` 350; `ued` none.
    pub jump_fall_limit: Option<f32>,
    /// `walkReachable` on a wall: `ued 0x10184b83` runs `FindJumpUp`; `dx` does nothing.
    pub find_jump_up: bool,
    pub prune_compare: PruneCompare,
    /// `BotOnlyPath`: `ued 0x10193bc4` R < 24 / `dx 0xd9470` R < 12.
    pub bot_only_radius: i32,
    /// `MonsterPath`: `ued 0x10193c52` R ≥ 52 && H ≥ 40 / `dx 0xd9440` R ≥ 22 && H ≥ 51 (both `!R_FLY`).
    pub monster_radius: i32,
    pub monster_height: i32,
    /// `addVisNoReach` scout: `ued 0x10177548` 18×39 / `dx 0xb1eaa` 22×51.
    pub vis_scout_radius: f32,
    pub vis_scout_height: f32,
    /// Report the route-search residue fields (`dx` only; UED22's search is undecoded, spec §3.4).
    pub residue: bool,
}

impl Preset {
    pub fn ued22_469() -> Preset {
        Preset {
            scout_jump_z: 320.0,
            scout_ground_speed: 320.0,
            scout_max_step_height: 25.0,
            scout_base_eye_height: None,
            radius_start: 18.0,
            radius_phase_height: 39.0,
            radius_phase_height_after_success: 40.0,
            radius_cap: 70.0,
            radius_stop: 2.0,
            height_bump: 4.0,
            height_phase_radius: None,
            height_cap: 70.0,
            height_floor: 40.0,
            height_stop: 1.0,
            los_precheck: false,
            scout_on_traced_floor: false,
            know_visible: false,
            size_rounding: SizeRounding::AppRound,
            jump_fall_limit: None,
            find_jump_up: true,
            prune_compare: PruneCompare::F32NonStrict,
            bot_only_radius: 24,
            monster_radius: 52,
            monster_height: 40,
            vis_scout_radius: 18.0,
            vis_scout_height: 39.0,
            residue: false,
        }
    }

    pub fn deusex_1112fm() -> Preset {
        Preset {
            scout_jump_z: 120.0,
            scout_ground_speed: 120.0,
            scout_max_step_height: 25.0,
            scout_base_eye_height: Some(0.0),
            radius_start: 12.0,
            radius_phase_height: 10.0,
            radius_phase_height_after_success: 10.0,
            radius_cap: 115.0,
            radius_stop: 1.0,
            height_bump: 0.0,
            height_phase_radius: Some(12.0),
            height_cap: 79.0,
            height_floor: 10.0,
            height_stop: 1.0,
            los_precheck: true,
            scout_on_traced_floor: true,
            know_visible: true,
            size_rounding: SizeRounding::Truncate,
            jump_fall_limit: Some(350.0),
            find_jump_up: false,
            prune_compare: PruneCompare::F64Strict,
            bot_only_radius: 12,
            monster_radius: 22,
            monster_height: 51,
            vis_scout_radius: 22.0,
            vis_scout_height: 51.0,
            residue: true,
        }
    }

    fn round_size(&self, v: f32) -> i32 {
        match self.size_rounding {
            SizeRounding::AppRound => app_round(v),
            SizeRounding::Truncate => v as i32,
        }
    }

    /// The `Prune` distance gate: prune only when the detour `sigma` is within 1.2× of `gamma`.
    fn prune_distance_ok(&self, sigma: i32, gamma: i32) -> bool {
        match self.prune_compare {
            // `(float)gamma * 1.2f < (float)sigma → skip` (`ued 0x101768f4`–`0x10176912`).
            PruneCompare::F32NonStrict => !((gamma as f32) * 1.2f32 < sigma as f32),
            // `fild gamma; fmul 0x3FF3333333333333; fild sigma; fcompp` at 64-bit x87 precision
            // (`dx 0xb1a97`–`0xb1ab6`): the product is always just below 1.2·gamma, so an integer
            // sigma equal to 1.2·gamma is NOT ≤ it.  f64 `<` against the same constant reproduces
            // that: for distances ≤ 2000 the f64 product rounds to exactly 1.2·gamma when that is
            // an integer and never crosses an integer otherwise (pinned by `prune_dx_bar_165_198`).
            PruneCompare::F64Strict => (sigma as f64) < (gamma as f64) * 1.2_f64,
        }
    }

    fn bot_only_path(&self, s: &FReachSpec) -> bool {
        s.collision_radius < self.bot_only_radius
    }

    fn monster_path(&self, s: &FReachSpec) -> bool {
        s.collision_radius >= self.monster_radius
            && s.collision_height >= self.monster_height
            && s.reach_flags & R_FLY == 0
    }
}

/// `appRound` = SSE `cvtss2si` in the default rounding mode: nearest, ties to even.
pub fn app_round(x: f32) -> i32 {
    let f = x.floor();
    let diff = x - f;
    let fi = f as i32;
    if diff < 0.5 {
        fi
    } else if diff > 0.5 {
        fi + 1
    } else if fi % 2 == 0 {
        fi
    } else {
        fi + 1
    }
}

/// `FRotator::Vector()` = `(GMath.UnitCoords / Rotation).XAxis`: the forward vector
/// `(cos P cos Y, cos P sin Y, sin P)`.  UE1 reads its trig from a 16384-entry table indexed by
/// `angle >> 2`, so angles are quantised to 4 units first.
pub fn rotator_x_axis(rot: [i32; 3]) -> Vec3 {
    let ang = |a: i32| ((a >> 2) & 0x3FFF) as f32 * (std::f32::consts::PI * 2.0 / 16384.0);
    let (p, y) = (ang(rot[0]), ang(rot[1]));
    Vec3::new(p.cos() * y.cos(), p.cos() * y.sin(), p.sin())
}

// ---------------------------------------------------------------------------------------------
// FReachSpec and the graph state
// ---------------------------------------------------------------------------------------------

/// One directed edge (28 bytes in memory, `ued 0x10112b32` / `dx 0x44c80`).  `start`/`end` are nav
/// roster indices.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FReachSpec {
    pub distance: i32,
    pub start: i32,
    pub end: i32,
    pub collision_radius: i32,
    pub collision_height: i32,
    pub reach_flags: i32,
    pub b_pruned: bool,
}

impl FReachSpec {
    /// `operator+` (`ued 0x10193a20`, `dx 0xd9490`): sum, min, min, OR.
    fn plus(&self, o: &FReachSpec) -> FReachSpec {
        FReachSpec {
            distance: self.distance + o.distance,
            start: self.start,
            end: self.end,
            collision_radius: self.collision_radius.min(o.collision_radius),
            collision_height: self.collision_height.min(o.collision_height),
            reach_flags: self.reach_flags | o.reach_flags,
            b_pruned: self.b_pruned,
        }
    }

    /// `operator<=` (`ued 0x10193ad0`, `dx 0xd9510`): at least as roomy, no extra ability.
    fn le(&self, o: &FReachSpec) -> bool {
        self.collision_radius >= o.collision_radius
            && self.collision_height >= o.collision_height
            && (self.reach_flags | o.reach_flags) == o.reach_flags
    }

    /// `supports` (`ued 0x1011aa40`, `dx 0x44c30`): the pawn's flags must cover the spec's.
    pub fn supports(&self, radius: i32, height: i32, flags: i32) -> bool {
        self.collision_radius >= radius
            && self.collision_height >= height
            && (self.reach_flags & flags) == self.reach_flags
    }
}

/// The route-search scratch the `dx` build leaves in the saved map (`PATHING-BUILD.md` §1.3).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Residue {
    pub visited_weight: i32,
    pub best_path_weight: i32,
    pub cost: i32,
    pub b_end_point: bool,
    pub previous_path: i32,
    pub next_ordered: i32,
    pub prev_ordered: i32,
}

impl Default for Residue {
    fn default() -> Self {
        Residue {
            visited_weight: 0,
            best_path_weight: 0,
            cost: 0,
            b_end_point: false,
            previous_path: -1,
            next_ordered: -1,
            prev_ordered: -1,
        }
    }
}

/// One NavigationPoint's build output: the four 16-slot arrays (`-1` empty), the list link, and
/// the residue.  `paths`/`upstream`/`pruned_paths` hold spec indices, `vis_no_reach` nav indices.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NavState {
    pub paths: [i32; 16],
    pub upstream: [i32; 16],
    pub pruned_paths: [i32; 16],
    pub vis_no_reach: [i32; 16],
    pub next_nav: i32,
    pub residue: Residue,
}

impl Default for NavState {
    fn default() -> Self {
        NavState {
            paths: [-1; 16],
            upstream: [-1; 16],
            pruned_paths: [-1; 16],
            vis_no_reach: [-1; 16],
            next_nav: -1,
            residue: Residue::default(),
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct PathGraph {
    /// `ULevel.ReachSpecs` in creation order.
    pub specs: Vec<FReachSpec>,
    pub navs: Vec<NavState>,
    /// `LevelInfo.NavigationPointList` (nav index, -1 = none).
    pub nav_list_head: i32,
}

impl PathGraph {
    pub fn new(num_navs: usize) -> PathGraph {
        PathGraph {
            specs: Vec::new(),
            navs: vec![NavState::default(); num_navs],
            nav_list_head: -1,
        }
    }

    /// Nav indices in `NavigationPointList` order (head first).
    pub fn nav_list(&self) -> Vec<usize> {
        let mut out = Vec::with_capacity(self.navs.len());
        let mut n = self.nav_list_head;
        while n != -1 {
            out.push(n as usize);
            n = self.navs[n as usize].next_nav;
        }
        out
    }
}

// ---------------------------------------------------------------------------------------------
// Bookkeeping: insertReachSpec / link / specFor / Prune
// ---------------------------------------------------------------------------------------------

/// `insertReachSpec` (`ued 0x10179820`, `dx 0xb1d70`): the slot for a spec of `distance` in a
/// descending-Distance list, or -1 when the list is full and the spec would be its longest.
/// Ties go before existing equal entries (newer first); a full list evicts slot 0 (the longest).
pub fn insert_reach_spec(specs: &[FReachSpec], list: &mut [i32; 16], distance: i32) -> i32 {
    let mut n = 0usize;
    while n < 16 && list[n] != -1 && specs[list[n] as usize].distance > distance {
        n += 1;
    }
    if list[15] == -1 {
        let mut free = n;
        while list[free] != -1 {
            free += 1;
        }
        for k in (n..free).rev() {
            list[k + 1] = list[k];
        }
        return n as i32;
    }
    if n == 0 {
        return -1;
    }
    for k in 0..n - 1 {
        list[k] = list[k + 1];
    }
    (n - 1) as i32
}

/// The caller side of `insertReachSpec` in `addReachSpecs` (`ued 0x10177419`–`0x1017746f`,
/// `dx` `addSpec`): a refused `Paths` insert drops the spec entirely; a refused `upstreamPaths`
/// insert keeps it one-sided.
pub fn link(g: &mut PathGraph, spec: FReachSpec) {
    let (a, b) = (spec.start as usize, spec.end as usize);
    let n = insert_reach_spec(&g.specs, &mut g.navs[a].paths, spec.distance);
    if n == -1 {
        return;
    }
    g.specs.push(spec);
    let idx = (g.specs.len() - 1) as i32;
    g.navs[a].paths[n as usize] = idx;
    let m = insert_reach_spec(&g.specs, &mut g.navs[b].upstream, spec.distance);
    if m != -1 {
        g.navs[b].upstream[m as usize] = idx;
    }
}

/// `specFor(Start, End)` (`ued 0x10179cb0`, `dx 0xb1cd0`): scan `Start.Paths` for `End`.
pub fn spec_for(g: &PathGraph, start: usize, end: usize) -> Option<usize> {
    for &idx in &g.navs[start].paths {
        if idx == -1 {
            return None;
        }
        if g.specs[idx as usize].end as usize == end {
            return Some(idx as usize);
        }
    }
    None
}

/// Shift-compact `idx` out of a list; a list that does not hold it is left untouched (the replay
/// of every retail map and UED22 golden is bit-exact only with this form, `simulate_bookkeeping.py`).
fn remove_from_list(list: &mut [i32; 16], idx: i32) {
    let Some(i) = list.iter().position(|&v| v == idx) else {
        return;
    };
    for k in i..15 {
        list[k] = list[k + 1];
    }
    list[15] = -1;
}

/// `PrunedPaths` append: the first free slot, or slot 15 overwritten when full
/// (`ued 0x101769ad`–`0x101769c4`, `dx 0xb1b40`–`0xb1b53`).
fn append_pruned(list: &mut [i32; 16], idx: i32) {
    let slot = list.iter().position(|&v| v == -1).unwrap_or(15);
    list[slot] = idx;
}

/// `Prune(node)` (`ued 0x10176790`, `dx 0xb1990`): for every detour A→node→B, prune the direct
/// A→B when it is within 1.2× and no more capable.  Returns the number pruned.
pub fn prune(g: &mut PathGraph, p: &Preset, node: usize) -> u32 {
    let mut count = 0;
    for i in 0..16 {
        let ui = g.navs[node].upstream[i];
        if ui == -1 {
            break;
        }
        let alpha = g.specs[ui as usize];
        for j in 0..16 {
            let di = g.navs[node].paths[j];
            if di == -1 {
                break;
            }
            let beta = g.specs[di as usize];
            let (a, b) = (alpha.start as usize, beta.end as usize);
            let Some(k) = spec_for(g, a, b) else {
                continue;
            };
            let gamma = g.specs[k];
            let sigma = alpha.plus(&beta);
            if !p.prune_distance_ok(sigma.distance, gamma.distance) {
                continue;
            }
            if !(sigma.le(&gamma) || p.bot_only_path(&gamma) || p.monster_path(&sigma)) {
                continue;
            }
            count += 1;
            remove_from_list(&mut g.navs[a].paths, k as i32);
            append_pruned(&mut g.navs[a].pruned_paths, k as i32);
            g.specs[k].b_pruned = true;
            remove_from_list(&mut g.navs[b].upstream, k as i32);
        }
    }
    count
}

// ---------------------------------------------------------------------------------------------
// findBestReachable and the collision-world boundary
// ---------------------------------------------------------------------------------------------

/// The scout as the route search sees it (`APawn` fields read by `findPathToward` and friends).
#[derive(Debug, Clone, PartialEq)]
pub struct Pawn {
    pub location: Vec3,
    pub collision_radius: f32,
    pub collision_height: f32,
    pub base_eye_height: f32,
    /// `calcMoveFlags()` (`ued 0x10116cb0`, `dx 0x26d10`).
    pub move_flags: i32,
    pub b_is_player: bool,
    pub b_can_open_doors: bool,
    /// `MoveTarget` (nav index, -1 none).
    pub move_target: i32,
}

/// A Mover hit by a line check, as `expandAnchor`/`CanMoveTo` inspect it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MoverHit {
    pub b_player_only: bool,
}

/// The geometric probes the build needs.  Phase 2's `collision.rs` implements them over the level
/// Model + mover models; tests inject scripted answers.
pub trait ReachWorld {
    /// `SingleLineCheck(TRACE_World, Extent 0)` from `from` to `to`: true when nothing was hit
    /// (BSP and movers).  `findBestReachable`'s `dx` pre-check and `addVisNoReach`'s visibility.
    fn line_visible(&mut self, from: Vec3, to: Vec3) -> bool;
    /// One `findBestReachable` probe: the scout sized (`radius`, `height`) placed per the preset at
    /// `a` (`FarMoveActor(bTest=0)`, which may fail → 0) then `pointReachable(b.Location,
    /// know_visible)`.  Returns the reach-flag mask, 0 when unreachable.
    fn probe(&mut self, a: &NavIn, b: &NavIn, radius: f32, height: f32) -> i32;
    /// `addVisNoReach`'s scout: `SetCollisionSize(radius, height)`, `FarMoveActor(node.Location,
    /// bTest=1, bNoCheck=0)`, `MoveTarget = node`, `bCanDoSpecial = 1`.  Returns the pawn state
    /// the route search starts from (its `location` is where the scout actually stands).
    fn vis_scout(&mut self, node: &NavIn, radius: f32, height: f32) -> Pawn;
    /// `UModel::FastLineCheck(end, start)`: BSP-only, true when clear.
    fn fast_line_check(&mut self, end: Vec3, start: Vec3) -> bool;
    /// `APawn::pointReachable(dest, bKnowVisible)` from `pawn.location`; the pawn is restored.
    fn point_reachable(&mut self, pawn: &Pawn, dest: Vec3, know_visible: bool) -> i32;
    /// `FarMoveActor(pawn, dest, bTest=1, bNoCheck=0)`: the fit test.  The implementation decides
    /// whether the pawn's `location` changes (the `bTest` question, `PATHING-BUILD.md` §9).
    fn far_move_test(&mut self, pawn: &mut Pawn, dest: Vec3) -> bool;
    /// `SingleLineCheck(TRACE_World)` from `start` to `end`, reporting a Mover if that is what was
    /// hit (the door test of `expandAnchor`/`CanMoveTo`).
    fn line_hits_mover(&mut self, end: Vec3, start: Vec3) -> Option<MoverHit>;
}

/// The two halving searches of `findBestReachable` (`ued 0x10193dd0`, `dx 0xd96e0`) over a probe
/// `(radius, height) -> reachFlags`.  Returns `(best radius, best height, flags of the last
/// successful probe)` in the scout's float sizes, or `None` when no size passes.
pub fn find_best_reachable(p: &Preset, probe: &mut dyn FnMut(f32, f32) -> i32) -> Option<(f32, f32, i32)> {
    let mut r = p.radius_start;
    let mut h = p.radius_phase_height;
    let mut step = p.radius_cap - r;
    let mut success = false;
    let (mut best_r, mut best_h, mut flags) = (r, h, 0);
    loop {
        let res = probe(r, h);
        let old = step;
        step *= 0.5;
        if res != 0 {
            flags = res;
            success = true;
            best_r = r;
            best_h = h;
            r += old;
            h = p.radius_phase_height_after_success;
            if step < p.radius_stop || r > p.radius_cap {
                break;
            }
        } else {
            r -= old;
            if step < p.radius_stop || r < p.radius_start {
                break;
            }
        }
    }
    if !success {
        return None;
    }
    let hr = p.height_phase_radius.unwrap_or(best_r);
    h += p.height_bump;
    step = p.height_cap - h;
    loop {
        let res = probe(hr, h);
        if res != 0 {
            flags = res;
            best_h = h;
            h += step;
            step *= 0.5;
            if step < p.height_stop || h > p.height_cap {
                break;
            }
        } else {
            h -= step;
            step *= 0.5;
            if step < p.height_stop || h < p.height_floor {
                break;
            }
        }
    }
    Some((best_r, best_h, flags))
}

/// `FReachSpec::defineFor(A, B, Scout)` (`ued 0x10193cd0`, `dx 0xd95b0`): size the edge, or `None`.
pub fn define_for<W: ReachWorld>(w: &mut W, p: &Preset, a: &NavIn, b: &NavIn) -> Option<FReachSpec> {
    if p.los_precheck && !w.line_visible(a.location, b.location) {
        return None;
    }
    let (r, h, flags) = find_best_reachable(p, &mut |r, h| w.probe(a, b, r, h))?;
    // `Distance = (End.Location − Start.Location).Size()`, ×2 for a swim edge
    // (`ued 0x1019418f`–`0x101941c6`, `dx 0xd9b5d`–`0xd9b69`).
    let mut distance = p.round_size(b.location.sub(&a.location).size());
    if flags & R_SWIM != 0 {
        distance *= 2;
    }
    Some(FReachSpec {
        distance,
        start: a.index as i32,
        end: b.index as i32,
        collision_radius: p.round_size(r),
        collision_height: p.round_size(h),
        reach_flags: flags,
        b_pruned: false,
    })
}

fn special_spec(start: usize, end: usize, distance: i32, size: i32) -> FReachSpec {
    FReachSpec {
        distance,
        start: start as i32,
        end: end as i32,
        collision_radius: size,
        collision_height: size,
        reach_flags: R_SPECIAL,
        b_pruned: false,
    }
}

fn dist2(a: Vec3, b: Vec3) -> f32 {
    let d = a.sub(&b);
    d.dot(&d)
}

/// `addReachSpecs(node)` (`ued 0x10176eb0`, `dx 0xb2240`): the special edges, then every other
/// NavigationPoint within 1000 uu (in front, for a one-way node) sized by `defineFor`.
pub fn add_reach_specs<W: ReachWorld>(g: &mut PathGraph, w: &mut W, p: &Preset, navs: &[NavIn], node: usize) {
    let me = &navs[node];
    if me.kind == NavKind::LiftCenter {
        // `LiftCenter ↔ LiftExit` with the same `LiftTag`: 500 / 60×60 / SPECIAL both ways
        // (`ued 0x10176f58`–`0x10177065`, `dx 0xb2308`); a LiftCenter gets nothing else.
        for e in navs {
            if e.kind == NavKind::LiftExit && e.lift_tag == me.lift_tag {
                link(g, special_spec(node, e.index, 500, 60));
                link(g, special_spec(e.index, node, 500, 60));
            }
        }
        return;
    }
    if matches!(me.kind, NavKind::Teleporter | NavKind::WarpZoneMarker) {
        // `Teleporter → Teleporter` whose `Tag` == this `URL` (a WarpZoneMarker: the zone's
        // `ThisTag` == this zone's `OtherSideURL`): 100 / 150×150 / SPECIAL, one way, first match
        // (`ued 0x10177104`–`0x101771b9`, `dx 0xb25d7`–`0xb2665`).
        if let Some(o) = navs.iter().find(|o| o.kind == me.kind && o.index != node && me.url == o.tag) {
            link(g, special_spec(node, o.index, 100, 150));
        }
    }
    let x_axis = me.b_one_way_path.then(|| rotator_x_axis(me.rotation));
    for o in navs {
        if o.kind == NavKind::LiftCenter || o.index == node {
            continue;
        }
        // `|A−B|² < 1000²` (`ued 0x101772f0` `comiss 1000000.0`, `dx 0xb2729`).
        if dist2(me.location, o.location) >= 1_000_000.0 {
            continue;
        }
        // `bOneWayPath`: B must be in front of A's rotation (`ued 0x10177301`, `dx 0xb2743`).
        if let Some(x) = x_axis {
            if o.location.sub(&me.location).dot(&x) <= 0.0 {
                continue;
            }
        }
        if let Some(spec) = define_for(w, p, me, o) {
            link(g, spec);
        }
    }
}

// ---------------------------------------------------------------------------------------------
// The route search `addVisNoReach` runs: dx `findPathToward` (`0xdb3f0`) with a NavigationPoint
// goal — `findings/21` Part 2.  UED22's own search is undecoded; both presets run this one.
// ---------------------------------------------------------------------------------------------

/// `FSortedPathList` (`dx` stack object, 0x104 bytes): 32 `(node, dist)` pairs ascending by dist.
struct SortedPathList {
    path: Vec<i32>,
    dist: Vec<i32>,
}

impl SortedPathList {
    const MAX: usize = 32;

    fn new() -> Self {
        SortedPathList { path: Vec::new(), dist: Vec::new() }
    }

    /// `addPath` (`dx 0xdd170`): sorted insert, new before equal, the 33rd-longest dropped.
    fn add_path(&mut self, node: i32, dist: i32) {
        let n = self.dist.iter().position(|&d| dist <= d).unwrap_or(self.path.len());
        if n >= Self::MAX {
            return;
        }
        self.path.insert(n, node);
        self.dist.insert(n, dist);
        self.path.truncate(Self::MAX);
        self.dist.truncate(Self::MAX);
    }

    /// `removePath(i)` (`dx 0xdd2a0`).
    fn remove_path(&mut self, i: usize) {
        self.path.remove(i);
        self.dist.remove(i);
    }
}

/// `clearPath(N)` (`dx 0xd9f90`): the per-search scratch reset.  `cost = ExtraCost`, which the
/// roster does not carry (the interface contract has no `ExtraCost`), so 0.
fn clear_path(g: &mut PathGraph, n: usize) {
    let r = &mut g.navs[n].residue;
    r.visited_weight = 10_000_000;
    r.next_ordered = -1;
    r.prev_ordered = -1;
    r.b_end_point = false;
    r.cost = 0;
}

fn sqrt_int(d2: i32) -> i32 {
    (d2 as f32).sqrt() as i32
}

/// `FSortedPathList::FindVisiblePaths` (`dx 0xda210`) for a NavigationPoint goal (`bEndFound`
/// preset, so only the start side is collected).  Returns `bAnchor`.
fn find_visible_paths(g: &mut PathGraph, navs: &[NavIn], pawn: &Pawn, start_pts: &mut SortedPathList) -> bool {
    let mut anchor = false;
    if pawn.move_target != -1 {
        let mt = &navs[pawn.move_target as usize];
        let dz = (mt.location.z - pawn.location.z).abs();
        let dx = mt.location.x - pawn.location.x;
        let dy = mt.location.y - pawn.location.y;
        if dz < mt.collision_height + pawn.collision_height
            && dx * dx + dy * dy < pawn.collision_radius * pawn.collision_radius
        {
            anchor = true;
            start_pts.add_path(pawn.move_target, 0);
        }
    }
    for n in g.nav_list() {
        clear_path(g, n);
        if !anchor {
            let d2 = dist2(pawn.location, navs[n].location) as i32;
            if d2 < 640_000 {
                start_pts.add_path(n as i32, d2);
            }
        }
    }
    anchor
}

/// `findEndPoint` (`dx 0xda610`): pop until a visible, reachable start node; it is the anchor
/// when the pawn stands on it, else an end point weighted by its distance.  Returns `(found,
/// anchor)`.
fn find_end_point<W: ReachWorld>(
    g: &mut PathGraph, w: &mut W, navs: &[NavIn], pawn: &Pawn, pts: &mut SortedPathList,
) -> (bool, bool) {
    while !pts.path.is_empty() {
        let n = pts.path[0] as usize;
        let eye = Vec3::new(pawn.location.x, pawn.location.y, pawn.location.z + pawn.base_eye_height);
        if w.fast_line_check(navs[n].location, eye) && w.point_reachable(pawn, navs[n].location, true) != 0 {
            pts.dist[0] = sqrt_int(pts.dist[0]);
            let anchor = pts.dist[0] < (pawn.collision_radius as i32).max(48)
                && (navs[n].location.z - pawn.location.z).abs() < pawn.collision_height;
            if !anchor {
                g.navs[n].residue.b_end_point = true;
                g.navs[n].residue.best_path_weight = pts.dist[0];
            }
            return (true, anchor);
        }
        pts.remove_path(0);
    }
    (false, false)
}

/// `checkAnchorPath` (`dx 0xda880`): can the pawn go straight from its anchor to `dest`?
fn check_anchor_path<W: ReachWorld>(
    w: &mut W, navs: &[NavIn], pawn: &mut Pawn, pts: &mut SortedPathList, dest: Vec3,
) -> bool {
    let anchor = navs[pts.path[0] as usize].location;
    if dist2(dest, anchor) < 640_000.0
        && w.fast_line_check(dest, anchor)
        && w.far_move_test(pawn, anchor)
        && w.point_reachable(pawn, dest, false) != 0
    {
        return true;
    }
    pts.path.truncate(1);
    pts.dist.truncate(1);
    false
}

/// The door gate of `expandAnchor`/`CanMoveTo`: a Mover across the edge passes only for a pawn
/// that opens doors (and, for a non-player, a Mover that is not `bPlayerOnly`).
fn door_ok(pawn: &Pawn, hit: Option<MoverHit>) -> bool {
    match hit {
        None => true,
        Some(m) => pawn.b_can_open_doors && (pawn.b_is_player || !m.b_player_only),
    }
}

/// `expandAnchor` (`dx 0xdaaa0`): the anchor's out-neighbours become end points.
fn expand_anchor<W: ReachWorld>(g: &mut PathGraph, w: &mut W, navs: &[NavIn], pawn: &Pawn, anchor: usize) {
    g.navs[anchor].residue.cost = 1_000_000;
    let (radius, height) = (pawn.collision_radius as i32, pawn.collision_height as i32);
    let lists = [g.navs[anchor].paths, g.navs[anchor].pruned_paths];
    for list in lists {
        for idx in list {
            if idx == -1 {
                break;
            }
            let spec = g.specs[idx as usize];
            if !spec.supports(radius, height, pawn.move_flags) {
                continue;
            }
            let (s, e) = (navs[spec.start as usize].location, navs[spec.end as usize].location);
            if !door_ok(pawn, w.line_hits_mover(e, s)) {
                continue;
            }
            let r = &mut g.navs[spec.end as usize].residue;
            r.b_end_point = true;
            r.best_path_weight = spec.distance;
        }
    }
}

/// `CanMoveTo(From, To)` (`dx 0xdad20`): a supported, door-clear spec `From → To`.
fn can_move_to<W: ReachWorld>(g: &PathGraph, w: &mut W, navs: &[NavIn], pawn: &Pawn, from: usize, to: usize) -> bool {
    let (radius, height) = (pawn.collision_radius as i32, pawn.collision_height as i32);
    for list in [g.navs[from].paths, g.navs[from].pruned_paths] {
        for idx in list {
            if idx == -1 {
                break;
            }
            let spec = g.specs[idx as usize];
            if spec.end as usize != to || !spec.supports(radius, height, pawn.move_flags) {
                continue;
            }
            if door_ok(pawn, w.line_hits_mover(navs[to].location, navs[from].location)) {
                return true;
            }
        }
    }
    false
}

/// `breadthPathFrom` (`dx 0xdcd60`): Dijkstra backwards from `start` along `upstreamPaths` with a
/// sorted intrusive list (`nextOrdered`/`prevOrdered`), until it pops a `bEndPoint` node.
fn breadth_path_from(g: &mut PathGraph, pawn: &Pawn, start: usize, single_path: bool) -> Option<usize> {
    let (radius, height) = (pawn.collision_radius as i32, pawn.collision_height as i32);
    let mut cur = start as i32;
    let mut last_add = start as i32;
    let mut num_nodes = 1;
    let mut move_count = 0;
    let mut popped = 0;
    while cur != -1 {
        let c = cur as usize;
        if g.navs[c].residue.b_end_point {
            g.navs[start].residue.previous_path = -1;
            return Some(c);
        }
        // `bPlayerOnly` is not in the roster: every node is open to the (non-player) scout.
        for i in 0..16 {
            let ui = g.navs[c].upstream[i];
            if ui == -1 {
                break;
            }
            let spec = g.specs[ui as usize];
            if !spec.supports(radius, height, pawn.move_flags) {
                continue;
            }
            let next = spec.start as usize;
            let nr = g.navs[next].residue;
            let new_w = g.navs[c].residue.visited_weight
                + spec.distance
                + nr.cost
                + if nr.b_end_point { nr.best_path_weight } else { 0 };
            if nr.visited_weight <= new_w {
                continue;
            }
            if nr.prev_ordered != -1 {
                // unlink from its old position
                let (pv, nx) = (nr.prev_ordered, nr.next_ordered);
                g.navs[pv as usize].residue.next_ordered = nx;
                if nx != -1 {
                    g.navs[nx as usize].residue.prev_ordered = pv;
                }
                if last_add == next as i32 || g.navs[last_add as usize].residue.visited_weight > nr.visited_weight {
                    last_add = pv;
                }
            }
            g.navs[next].residue.previous_path = cur;
            g.navs[next].residue.visited_weight = new_w;
            let mut ins = if g.navs[last_add as usize].residue.visited_weight < new_w { last_add } else { cur };
            let mut steps = 0;
            loop {
                let nx = g.navs[ins as usize].residue.next_ordered;
                if nx == -1 || g.navs[nx as usize].residue.visited_weight >= new_w {
                    break;
                }
                ins = nx;
                steps += 1;
                if steps > 500 {
                    return None; // "Breadth path list overflow"
                }
            }
            let nx = g.navs[ins as usize].residue.next_ordered;
            g.navs[next].residue.next_ordered = nx;
            g.navs[next].residue.prev_ordered = ins;
            if nx != -1 {
                g.navs[nx as usize].residue.prev_ordered = next as i32;
            }
            g.navs[ins as usize].residue.next_ordered = next as i32;
        }
        num_nodes += 1;
        while move_count < num_nodes / 2 && g.navs[last_add as usize].residue.next_ordered != -1 {
            move_count += 1;
            last_add = g.navs[last_add as usize].residue.next_ordered;
        }
        cur = g.navs[c].residue.next_ordered;
        popped += 1;
        if single_path && popped > 4 {
            return None;
        }
        if popped > 1000 {
            return None;
        }
    }
    None
}

/// `findAltEndPoint` (`dx 0xdb0e0`): a cheaper start node than the one the search chose.
fn find_alt_end_point<W: ReachWorld>(
    g: &PathGraph, w: &mut W, navs: &[NavIn], pawn: &Pawn, pts: &SortedPathList, goal: Vec3, best: &mut usize,
) {
    let base = g.navs[pts.path[0] as usize].residue.visited_weight + pts.dist[0];
    for i in 1..pts.path.len() {
        let n = pts.path[i] as usize;
        let wgt = g.navs[n].residue.visited_weight + sqrt_int(pts.dist[i]);
        if wgt >= base || (navs[n].location.z - pawn.location.z).abs() >= 120.0 {
            continue;
        }
        let toward_goal = goal.sub(&pawn.location).dot(&navs[n].location.sub(&pawn.location)) < 0.0;
        if !(toward_goal || wgt < ((0.85 * base as f32) as i32).max(base - 150)) {
            continue;
        }
        let eye = Vec3::new(pawn.location.x, pawn.location.y, pawn.location.z + pawn.base_eye_height);
        if w.fast_line_check(navs[n].location, eye) && w.point_reachable(pawn, navs[n].location, true) != 0 {
            *best = n;
            return;
        }
    }
}

/// `APawn::findPathToward(goal, bSinglePath=0, bestPath, bClearPaths=1)` (`dx 0xdb3f0`) with a
/// NavigationPoint goal: the next node the pawn should go to, or `None`.
pub fn find_path_toward<W: ReachWorld>(
    g: &mut PathGraph, w: &mut W, navs: &[NavIn], pawn: &mut Pawn, goal: usize,
) -> Option<usize> {
    if g.nav_list_head == -1 || g.specs.is_empty() {
        return None;
    }
    let orig = pawn.location;
    let mut start_pts = SortedPathList::new();
    let mut anchor = find_visible_paths(g, navs, pawn, &mut start_pts);
    if start_pts.path.is_empty() {
        return None;
    }
    if !anchor {
        let (found, is_anchor) = find_end_point(g, w, navs, pawn, &mut start_pts);
        if !found {
            pawn.location = orig;
            return None;
        }
        anchor = is_anchor;
    }
    if anchor {
        let a = start_pts.path[0] as usize;
        if can_move_to(g, w, navs, pawn, a, goal) || check_anchor_path(w, navs, pawn, &mut start_pts, navs[goal].location) {
            pawn.location = orig;
            return Some(goal);
        }
        expand_anchor(g, w, navs, pawn, a);
    }
    // `EndPts = {goal, 0}`: the goal seeds the search with weight 0.
    g.navs[goal].residue.visited_weight = 0;
    let best = breadth_path_from(g, pawn, goal, false);
    pawn.location = orig;
    let mut best = best?;
    if !anchor {
        find_alt_end_point(g, w, navs, pawn, &start_pts, navs[goal].location, &mut best);
    }
    Some(best)
}

/// `addVisNoReach(node)` (`ued 0x101774e0`, `dx 0xb1e50`): up to 16 visible nodes within 2000 uu
/// whose route from the scout is missing or more than twice the straight line.
pub fn add_vis_no_reach<W: ReachWorld>(g: &mut PathGraph, w: &mut W, p: &Preset, navs: &[NavIn], node: usize) {
    if navs[node].kind == NavKind::LiftCenter {
        return;
    }
    let mut pawn = w.vis_scout(&navs[node], p.vis_scout_radius, p.vis_scout_height);
    let mut n = 0usize;
    for o in g.nav_list() {
        let d2 = dist2(navs[node].location, navs[o].location);
        if navs[o].kind == NavKind::LiftCenter || o == node || d2 >= 4_000_000.0 || n >= 16 {
            continue;
        }
        if !w.line_visible(navs[node].location, navs[o].location) {
            continue;
        }
        let weight = match find_path_toward(g, w, navs, &mut pawn, o) {
            Some(best) => {
                let wgt = g.navs[best].residue.visited_weight as f32;
                if wgt == 10_000_000.0 {
                    continue;
                }
                wgt
            }
            None => 200_000_000.0,
        };
        if weight * weight > 4.0 * d2 {
            g.navs[node].vis_no_reach[n] = o as i32;
            n += 1;
        }
    }
}

// ---------------------------------------------------------------------------------------------
// definePaths
// ---------------------------------------------------------------------------------------------

/// `definePaths` after the marker pass (`ued 0x10179070`–`0x101791a6`, `dx 0xb1597`–`0xb1680`):
/// prepend each nav to `NavigationPointList` and add its specs, then `Prune` and `addVisNoReach`
/// in list order.  Returns the graph and the number of specs pruned.
pub fn define_paths<W: ReachWorld>(w: &mut W, p: &Preset, navs: &[NavIn]) -> Result<(PathGraph, u32), PathError> {
    for (i, n) in navs.iter().enumerate() {
        if n.index != i {
            return Err(PathError(format!("nav {} has index {} but sits at roster position {i}", n.tag, n.index)));
        }
        for v in [n.location.x, n.location.y, n.location.z, n.collision_radius, n.collision_height] {
            if !v.is_finite() {
                return Err(PathError(format!("nav {i} ({}): non-finite Location/collision value {v}", n.tag)));
            }
        }
    }
    let mut g = PathGraph::new(navs.len());
    for i in 0..navs.len() {
        g.navs[i].next_nav = g.nav_list_head;
        g.nav_list_head = i as i32;
        add_reach_specs(&mut g, w, p, navs, i);
    }
    let list = g.nav_list();
    let pruned = list.iter().map(|&n| prune(&mut g, p, n)).sum();
    for &n in &list {
        add_vis_no_reach(&mut g, w, p, navs, n);
    }
    Ok((g, pruned))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One committed fixture (`fixtures/paths/extract_fixture.py` output).
    struct Fixture {
        specs: Vec<FReachSpec>,
        /// per nav in roster order: (name, Paths, upstreamPaths, PrunedPaths)
        navs: Vec<(String, [i32; 16], [i32; 16], [i32; 16])>,
    }

    fn arr16(it: &mut dyn Iterator<Item = &str>) -> [i32; 16] {
        let mut a = [-1; 16];
        for v in a.iter_mut() {
            *v = it.next().unwrap().parse().unwrap();
        }
        a
    }

    fn load_fixture(text: &str) -> Fixture {
        let mut f = Fixture { specs: Vec::new(), navs: Vec::new() };
        for line in text.lines() {
            let mut it = line.split_whitespace();
            match it.next() {
                Some("nav") => {
                    let _idx = it.next().unwrap();
                    let name = it.next().unwrap().to_string();
                    let _cls = it.next().unwrap();
                    assert_eq!(it.next(), Some("loc"));
                    it.nth(2);
                    assert_eq!(it.next(), Some("P"));
                    let paths = arr16(&mut it);
                    assert_eq!(it.next(), Some("U"));
                    let up = arr16(&mut it);
                    assert_eq!(it.next(), Some("PR"));
                    let pr = arr16(&mut it);
                    f.navs.push((name, paths, up, pr));
                }
                Some("spec") => {
                    let v: Vec<i32> = it.map(|s| s.parse().unwrap()).collect();
                    f.specs.push(FReachSpec {
                        distance: v[0],
                        start: v[1],
                        end: v[2],
                        collision_radius: v[3],
                        collision_height: v[4],
                        reach_flags: v[5],
                        b_pruned: v[6] != 0,
                    });
                }
                _ => {}
            }
        }
        f
    }

    /// Replay `insertReachSpec` over the saved specs in creation order, then `Prune` over the
    /// reverse roster, and compare with what the engine saved (`simulate_bookkeeping.py`).
    fn replay_bookkeeping(fx: &Fixture, p: &Preset) -> PathGraph {
        let mut g = PathGraph::new(fx.navs.len());
        for i in 0..fx.navs.len() {
            g.navs[i].next_nav = g.nav_list_head;
            g.nav_list_head = i as i32;
        }
        for s in &fx.specs {
            let mut s = *s;
            s.b_pruned = false;
            let k = g.specs.len() as i32;
            g.specs.push(s);
            if s.start < 0 || s.end < 0 {
                continue;
            }
            let n = insert_reach_spec(&g.specs, &mut g.navs[s.start as usize].paths, s.distance);
            assert_ne!(n, -1, "spec {k} refused by Paths although the engine kept it");
            g.navs[s.start as usize].paths[n as usize] = k;
            let m = insert_reach_spec(&g.specs, &mut g.navs[s.end as usize].upstream, s.distance);
            if m != -1 {
                g.navs[s.end as usize].upstream[m as usize] = k;
            }
        }
        for n in g.nav_list() {
            prune(&mut g, p, n);
        }
        g
    }

    fn assert_golden(fx: &Fixture, g: &PathGraph) {
        for (k, (sim, disk)) in g.specs.iter().zip(&fx.specs).enumerate() {
            assert_eq!(sim.b_pruned, disk.b_pruned, "spec {k} bPruned");
        }
        for (i, (name, paths, up, pr)) in fx.navs.iter().enumerate() {
            assert_eq!(&g.navs[i].paths, paths, "{name}.Paths");
            assert_eq!(&g.navs[i].upstream, up, "{name}.upstreamPaths");
            assert_eq!(&g.navs[i].pruned_paths, pr, "{name}.PrunedPaths");
        }
    }

    /// UED22 golden `evidence/pathlab-define.dx` (281 specs, 40 nodes): every `bPruned` bit and
    /// every `Paths`/`upstreamPaths`/`PrunedPaths` array, with the `ued22-469` prune compare.
    #[test]
    fn golden_pathlab_define_ued22() {
        let fx = load_fixture(include_str!("../fixtures/paths/pathlab-define.txt"));
        assert_eq!(fx.specs.len(), 281);
        assert_eq!(fx.navs.len(), 40);
        let g = replay_bookkeeping(&fx, &Preset::ued22_469());
        assert_golden(&fx, &g);
    }

    /// Retail `02_NYC_Bar.dx` (889 specs, 80 nodes), built by Deus Ex 1112fm: the same with the
    /// `deusex-1112fm` compare.  Spec 73 (direct 165, detour 50+148 = 198 = 1.2×165 exactly) is
    /// unpruned on disk — the strict rule.
    #[test]
    fn golden_nyc_bar_retail_dx() {
        let fx = load_fixture(include_str!("../fixtures/paths/nyc-bar-retail.txt"));
        assert_eq!(fx.specs.len(), 889);
        assert_eq!(fx.navs.len(), 80);
        assert_eq!((fx.specs[73].distance, fx.specs[73].b_pruned), (165, false));
        let g = replay_bookkeeping(&fx, &Preset::deusex_1112fm());
        assert_golden(&fx, &g);
        // The non-strict compare would prune spec 73: the two presets are distinguishable here.
        let g_ued = replay_bookkeeping(&fx, &Preset { prune_compare: PruneCompare::F32NonStrict, ..Preset::deusex_1112fm() });
        assert!(g_ued.specs[73].b_pruned, "1.2f non-strict compare must prune the exact-1.2x Bar edge");
    }

    #[test]
    fn prune_dx_bar_165_198() {
        let dx = Preset::deusex_1112fm();
        assert!(!dx.prune_distance_ok(198, 165), "198 == 1.2*165: not pruned on dx");
        assert!(dx.prune_distance_ok(197, 165));
        let ued = Preset::ued22_469();
        assert!(ued.prune_distance_ok(198, 165), "ued 1.2f non-strict prunes the exact ratio");
        assert!(!ued.prune_distance_ok(199, 165));
        // exhaustive: the dx compare is exactly `5σ < 6γ` over the distance range
        for gamma in 1..2100 {
            for sigma in gamma..=(gamma * 6 / 5 + 2) {
                assert_eq!(dx.prune_distance_ok(sigma, gamma), 5 * sigma < 6 * gamma, "σ {sigma} γ {gamma}");
            }
        }
    }

    #[test]
    fn app_round_is_half_even() {
        assert_eq!(app_round(24.5), 24);
        assert_eq!(app_round(37.5), 38);
        assert_eq!(app_round(50.5), 50);
        assert_eq!(app_round(63.5), 64);
        assert_eq!(app_round(53.75), 54);
        assert_eq!(app_round(2.4999), 2);
        assert_eq!(app_round(-0.5), 0);
        assert_eq!(app_round(-1.5), -2);
    }

    #[test]
    fn insert_reach_spec_orders_descending_and_evicts_longest() {
        let specs: Vec<FReachSpec> = (0..20)
            .map(|d| FReachSpec { distance: 100 - d * 3, start: 0, end: 1, collision_radius: 0, collision_height: 0, reach_flags: 1, b_pruned: false })
            .collect();
        let mut list = [-1; 16];
        for k in 0..16 {
            let n = insert_reach_spec(&specs, &mut list, specs[k].distance);
            assert_eq!(n, k as i32);
            list[n as usize] = k as i32;
        }
        // a 17th that is the longest of all is refused
        let longest = FReachSpec { distance: 999, ..specs[0] };
        let mut specs2 = specs.clone();
        specs2.push(longest);
        assert_eq!(insert_reach_spec(&specs2, &mut list, 999), -1);
        // a shorter one evicts slot 0 (distance 100) and lands sorted
        let n = insert_reach_spec(&specs2, &mut list, specs[16].distance);
        list[n as usize] = 16;
        assert_eq!(n, 15);
        assert_eq!(list[0], 1);
        let dists: Vec<i32> = list.iter().map(|&i| specs2[i as usize].distance).collect();
        assert!(dists.windows(2).all(|w| w[0] >= w[1]));
        // equal distance: the newer goes first
        let mut l2 = [-1; 16];
        let eq = vec![FReachSpec { distance: 50, ..specs[0] }, FReachSpec { distance: 50, ..specs[0] }];
        l2[insert_reach_spec(&eq, &mut l2, 50) as usize] = 0;
        assert_eq!(insert_reach_spec(&eq, &mut l2, 50), 0);
    }

    /// The recorded sizes of a monotone probe (`pass iff size ≤ limit`) over every limit fall on
    /// the engine's grids — the complete value sets seen in retail / live builds.
    fn grid(p: &Preset, limits: impl Iterator<Item = f32>, phase: usize) -> Vec<i32> {
        let mut seen = std::collections::BTreeSet::new();
        for limit in limits {
            let mut probe = |r: f32, h: f32| -> i32 {
                let v = if phase == 0 { r } else { h };
                (v <= limit) as i32
            };
            if let Some((r, h, _)) = find_best_reachable(p, &mut probe) {
                seen.insert(p.round_size(if phase == 0 { r } else { h }));
            }
        }
        seen.into_iter().collect()
    }

    #[test]
    fn dx_size_grids() {
        let p = Preset::deusex_1112fm();
        let radii = grid(&p, (0..1300).map(|i| i as f32 * 0.1), 0);
        assert_eq!(
            radii,
            vec![12, 15, 18, 21, 24, 28, 31, 34, 37, 40, 44, 47, 50, 53, 57, 60, 63, 66, 69, 73, 76, 79, 82, 86, 89, 92, 95, 98, 102, 105, 108, 111, 115]
        );
        let heights = grid(&p, (0..900).map(|i| i as f32 * 0.1), 1);
        let expect: Vec<i32> = (0..33).map(|k| (10.0 + 69.0 * k as f32 / 32.0) as i32).collect();
        assert_eq!(heights, expect);
        assert_eq!(heights.len(), 33);
        assert_eq!((heights[0], heights[1], heights[32]), (10, 12, 79));
    }

    #[test]
    fn ued_size_grids() {
        let p = Preset::ued22_469();
        assert_eq!(grid(&p, (0..800).map(|i| i as f32 * 0.1), 0), vec![18, 24, 31, 38, 44, 50, 57, 64, 70]);
        // height phase: radius always passes, height passes iff ≤ limit; limits below 44 leave
        // bestH at the radius phase's height (40 after the first success's SetCollisionSize).
        let mut seen = std::collections::BTreeSet::new();
        for limit in (440..800).map(|i| i as f32 * 0.1) {
            let mut probe = |_r: f32, h: f32| (h <= limit) as i32;
            let (_, h, _) = find_best_reachable(&p, &mut probe).unwrap();
            seen.insert(app_round(h));
        }
        assert_eq!(seen.into_iter().collect::<Vec<_>>(), vec![44, 47, 50, 54, 57, 60, 64, 67, 70]);
        let mut probe = |_r: f32, h: f32| (h <= 41.0) as i32;
        assert_eq!(find_best_reachable(&p, &mut probe).map(|t| app_round(t.1)), Some(40));
    }

    #[test]
    fn find_best_reachable_records_last_successful_flags() {
        let p = Preset::ued22_469();
        // radius ≤ 30 walks; ≤ 20 needs a jump; the last success decides the flags
        let mut probe = |r: f32, _h: f32| if r <= 20.0 { 9 } else if r <= 30.0 { 1 } else { 0 };
        let (r, _, flags) = find_best_reachable(&p, &mut probe).unwrap();
        assert_eq!((app_round(r), flags), (24, 1));
        let mut none = |_r: f32, _h: f32| 0;
        assert_eq!(find_best_reachable(&p, &mut none), None);
    }

    /// A scripted world: every probe passes below a per-pair size limit; LOS scripted per pair.
    struct ScriptWorld {
        limit: std::collections::HashMap<(usize, usize), (f32, f32, i32)>,
        blocked: std::collections::HashSet<(usize, usize)>,
    }

    impl ReachWorld for ScriptWorld {
        fn line_visible(&mut self, _from: Vec3, _to: Vec3) -> bool {
            true
        }
        fn probe(&mut self, a: &NavIn, b: &NavIn, radius: f32, height: f32) -> i32 {
            if self.blocked.contains(&(a.index, b.index)) {
                return 0;
            }
            match self.limit.get(&(a.index, b.index)) {
                Some(&(rl, hl, flags)) if radius <= rl && height <= hl => flags,
                _ => 0,
            }
        }
        fn vis_scout(&mut self, node: &NavIn, radius: f32, height: f32) -> Pawn {
            Pawn { location: node.location, collision_radius: radius, collision_height: height, base_eye_height: 0.0, move_flags: R_WALK | R_JUMP | R_SWIM | R_SPECIAL, b_is_player: false, b_can_open_doors: false, move_target: node.index as i32 }
        }
        fn fast_line_check(&mut self, _end: Vec3, _start: Vec3) -> bool {
            true
        }
        fn point_reachable(&mut self, _pawn: &Pawn, _dest: Vec3, _kv: bool) -> i32 {
            0
        }
        fn far_move_test(&mut self, _pawn: &mut Pawn, _dest: Vec3) -> bool {
            true
        }
        fn line_hits_mover(&mut self, _end: Vec3, _start: Vec3) -> Option<MoverHit> {
            None
        }
    }

    fn nav(index: usize, kind: NavKind, x: f32, y: f32) -> NavIn {
        NavIn { index, kind, location: Vec3::new(x, y, 0.0), rotation: [0, 0, 0], collision_radius: 20.0, collision_height: 40.0, b_one_way_path: false, lift_tag: String::new(), url: String::new(), tag: format!("n{index}") }
    }

    #[test]
    fn define_paths_corridor_and_special_edges() {
        let mut navs = vec![nav(0, NavKind::NavigationPoint, 0.0, 0.0), nav(1, NavKind::NavigationPoint, 300.0, 0.0), nav(2, NavKind::NavigationPoint, 600.0, 0.0), nav(3, NavKind::NavigationPoint, 2000.0, 0.0)];
        navs.push(NavIn { lift_tag: "lift".into(), ..nav(4, NavKind::LiftCenter, 0.0, 500.0) });
        navs.push(NavIn { lift_tag: "lift".into(), ..nav(5, NavKind::LiftExit, 0.0, 600.0) });
        navs.push(NavIn { url: "far".into(), ..nav(6, NavKind::Teleporter, 5000.0, 0.0) });
        navs.push(NavIn { tag: "far".into(), ..nav(7, NavKind::Teleporter, 9000.0, 0.0) });
        let mut w = ScriptWorld { limit: Default::default(), blocked: Default::default() };
        for a in 0..3 {
            for b in 0..3 {
                w.limit.insert((a, b), (70.0, 70.0, R_WALK));
            }
        }
        let p = Preset::ued22_469();
        let (g, pruned) = define_paths(&mut w, &p, &navs).unwrap();
        // the lift pair both ways, the teleporter one way, the corridor's 6 edges; node 3 is out of range
        let special: Vec<_> = g.specs.iter().filter(|s| s.reach_flags == R_SPECIAL).map(|s| (s.start, s.end, s.distance, s.collision_radius)).collect();
        assert_eq!(special, vec![(4, 5, 500, 60), (5, 4, 500, 60), (6, 7, 100, 150)]);
        let walk: Vec<_> = g.specs.iter().filter(|s| s.reach_flags == R_WALK).map(|s| (s.start, s.end, s.distance, s.b_pruned)).collect();
        assert_eq!(walk.len(), 6);
        // 0→2 (600) is pruned by 0→1→2 (300+300 ≤ 1.2·600) in both directions
        assert!(walk.contains(&(0, 2, 600, true)) && walk.contains(&(2, 0, 600, true)));
        assert!(walk.contains(&(0, 1, 300, false)));
        assert_eq!(pruned, 2);
        assert_eq!(g.nav_list(), vec![7, 6, 5, 4, 3, 2, 1, 0]);
        assert_eq!(g.navs[0].pruned_paths[0], g.specs.iter().position(|s| s.start == 0 && s.end == 2).unwrap() as i32);
        // sizes: the scripted limit 70 lets the full UED22 sweep pass → 70 × 70
        let s01 = g.specs.iter().find(|s| s.start == 0 && s.end == 1).unwrap();
        assert_eq!((s01.collision_radius, s01.collision_height), (70, 70));
    }

    #[test]
    fn one_way_path_uses_the_rotation() {
        let x = rotator_x_axis([0, 0, 0]);
        assert!((x.x - 1.0).abs() < 1e-6 && x.y.abs() < 1e-6);
        let y = rotator_x_axis([0, 16384, 0]);
        assert!(y.x.abs() < 1e-6 && (y.y - 1.0).abs() < 1e-6);
        let mut navs = vec![nav(0, NavKind::NavigationPoint, 0.0, 0.0), nav(1, NavKind::NavigationPoint, 300.0, 0.0), nav(2, NavKind::NavigationPoint, -300.0, 0.0)];
        navs[0].b_one_way_path = true;
        let mut w = ScriptWorld { limit: Default::default(), blocked: Default::default() };
        for a in 0..3 {
            for b in 0..3 {
                w.limit.insert((a, b), (70.0, 70.0, R_WALK));
            }
        }
        let (g, _) = define_paths(&mut w, &Preset::deusex_1112fm(), &navs).unwrap();
        let from0: Vec<i32> = g.specs.iter().filter(|s| s.start == 0).map(|s| s.end).collect();
        assert_eq!(from0, vec![1], "only the node in front of the yaw-0 one-way node");
    }

    #[test]
    fn distance_rounding_per_preset() {
        let navs = vec![nav(0, NavKind::NavigationPoint, 0.0, 0.0), nav(1, NavKind::NavigationPoint, 100.0, 50.0)];
        let mut w = ScriptWorld { limit: Default::default(), blocked: Default::default() };
        w.limit.insert((0, 1), (12.0, 10.0, R_WALK | R_SWIM));
        w.limit.insert((1, 0), (12.0, 10.0, R_WALK));
        let (g, _) = define_paths(&mut w, &Preset::deusex_1112fm(), &navs).unwrap();
        // |(100,50)| = 111.80: dx truncates (111) and doubles a swim edge
        assert_eq!(g.specs[0].distance, 222);
        assert_eq!(g.specs[1].distance, 111);
        assert_eq!((g.specs[0].collision_radius, g.specs[0].collision_height), (12, 10));
        let (g, _) = define_paths(&mut w, &Preset::ued22_469(), &navs).unwrap();
        assert!(g.specs.is_empty(), "the 18-radius UED22 sweep cannot fit a 12-uu limit");
    }

    #[test]
    fn bad_roster_index_is_an_error() {
        let navs = vec![nav(1, NavKind::NavigationPoint, 0.0, 0.0)];
        let mut w = ScriptWorld { limit: Default::default(), blocked: Default::default() };
        let err = define_paths(&mut w, &Preset::ued22_469(), &navs).unwrap_err();
        assert!(err.0.contains("index 1"), "{err}");
    }

    #[test]
    fn sorted_path_list_keeps_32_ascending_new_before_equal() {
        let mut l = SortedPathList::new();
        for i in 0..40 {
            l.add_path(i, (40 - i) * 10);
        }
        assert_eq!(l.path.len(), 32);
        assert!(l.dist.windows(2).all(|w| w[0] <= w[1]));
        assert_eq!(l.dist[0], 10);
        let mut l2 = SortedPathList::new();
        l2.add_path(1, 5);
        l2.add_path(2, 5);
        assert_eq!(l2.path, vec![2, 1]);
    }

    /// `breadthPathFrom` on a 4-node chain: the search from the goal runs along upstream edges to
    /// the marked end point, leaving the Dijkstra residue.
    #[test]
    fn breadth_path_from_chain() {
        let navs: Vec<NavIn> = (0..4).map(|i| nav(i, NavKind::NavigationPoint, i as f32 * 100.0, 0.0)).collect();
        let mut g = PathGraph::new(4);
        for i in 0..3 {
            link(&mut g, FReachSpec { distance: 100, start: i, end: i + 1, collision_radius: 30, collision_height: 60, reach_flags: R_WALK, b_pruned: false });
        }
        for n in 0..4 {
            clear_path(&mut g, n);
        }
        g.navs[1].residue.b_end_point = true;
        g.navs[1].residue.best_path_weight = 7;
        g.navs[3].residue.visited_weight = 0;
        let pawn = Pawn { location: navs[0].location, collision_radius: 22.0, collision_height: 51.0, base_eye_height: 0.0, move_flags: R_WALK, b_is_player: false, b_can_open_doors: false, move_target: -1 };
        assert_eq!(breadth_path_from(&mut g, &pawn, 3, false), Some(1));
        assert_eq!(g.navs[2].residue.visited_weight, 100);
        assert_eq!(g.navs[1].residue.visited_weight, 207);
        assert_eq!(g.navs[1].residue.previous_path, 2);
        assert_eq!(g.navs[2].residue.previous_path, 3);
        assert_eq!(g.navs[3].residue.previous_path, -1);
        assert_eq!(g.navs[0].residue.visited_weight, 10_000_000, "never expanded: the end point popped first");
        // a spec the pawn does not support is skipped
        let big = Pawn { collision_radius: 40.0, ..pawn };
        for n in 0..4 {
            clear_path(&mut g, n);
        }
        g.navs[3].residue.visited_weight = 0;
        assert_eq!(breadth_path_from(&mut g, &big, 3, false), None);
    }
}
