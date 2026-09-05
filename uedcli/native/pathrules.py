"""The path-build rule presets `level materialize` runs (`PATHING-BUILD.md` §3, spec §2).

One frozen dataclass per engine; every constant is the one read out of that engine's `Engine.dll`
(RVA in the comment: `ued` = `uned/UED22/Engine.dll` image-relative, `dx` = the Deus Ex 1112fm
`Engine.dll`). `as_args()` is exactly the keyword set of the Rust `uedcli_native.PresetIn`
(`uedcli-native/src/paths_py.rs`); `name` and `skip_deleted` stay Python-side. The shared
constants below are the same in both engines and live in the Rust core; they are listed here so
the preset table is complete.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

# --- shared by both engines (PATHING-BUILD.md §3.1, §3.2, §3.4–3.7) ----------------------------
PAIR_CUTOFF = 1000.0            # candidate pair iff |A-B|^2 < 1000^2  (ued .rdata 0x1020296c, dx 0x130a64)
LIFT_SPEC = (500, 60, 60, 0x20)          # LiftCenter <-> LiftExit: Distance, R, H, reachFlags
TELEPORT_SPEC = (100, 150, 150, 0x20)    # Teleporter -> Teleporter / WarpZoneMarker
R_WALK, R_FLY, R_SWIM, R_JUMP, R_DOOR, R_SPECIAL = 1, 2, 4, 8, 16, 32
SWIM_DISTANCE_FACTOR = 2        # Distance x2 on an R_SWIM edge
WALK_MOVE_SIZE = 16.0           # editor walkReachable step
WALK_TICKS = 100
ARRIVE_DIST = 15.0              # Reachable(Dest, 15.0)
FLOOR_NORMAL_Z = 0.7            # a landing/floor with Normal.Z < 0.7 is a wall / ledge
NODE_ARRAY_SLOTS = 16           # Paths/upstreamPaths/PrunedPaths/VisNoReachPaths[16]
PRUNE_FACTOR = 1.2              # ued 0x10212d5c (f32, <=) / dx 0x130a48 (f64 just below 1.2, <)
SCOUT_DEFAULT_SIZE = (52.0, 50.0)        # class-default cylinder until the first SetCollisionSize
VIS_NO_REACH_RANGE = 2000.0     # addVisNoReach: other nodes within 2000 uu
VIS_NO_REACH_WEIGHT_FACTOR = 2  # ... whose route weight > 2 x straight distance
VISITED_WEIGHT_SENTINEL = 10000000
FIND_JUMP_UP_STEP = 48.0        # ued FindJumpUp: one walkMove with MaxStepHeight 48
FLOOR_PROBE_DEPTH = 79.0        # dx: the scout's floor probe under A
JUMP_LANDING_DT = 0.1
JUMP_LANDING_MAX_STEPS = 35
JUMP_LANDING_MAX_SPEED2 = 2.5e6
JUMP_LANDING_MIN_GAIN = 8.0     # landing must be > 8 uu closer to Dest


@dataclass(frozen=True, kw_only=True)
class PathPreset:
    name: str
    skip_deleted: bool                        # ued: definePaths' !bDeleteMe roster filter
    # scout (defineFor)                                        ued 0x10193cd0 / dx 0xd95b0
    scout_jump_z: float                       # ued 0x10193d18 / dx 0xd95e8
    scout_ground_speed: float                 # ued 0x10193d54 / dx 0xd9604
    scout_max_step_height: float              # ued 0x10193d5e / dx 0xd960a
    scout_base_eye_height: float | None       # dx 0xd9614 sets 0; ued keeps the class default
    # radius search (findBestReachable)                        ued 0x10193dd0 / dx 0xd96e0
    radius_start: float                       # ued 0x10193e0c 18 / dx 0xd9709 12; first step = cap - start
    radius_phase_height: float                # the height probed during the radius search: 39 / 10
    radius_phase_height_after_success: float  # ued 0x10193f16 40 / dx 10
    radius_cap: float                         # ued 0x10193e29 70 / dx 0xd971d 115
    radius_stop: float                        # stop when step < this: ued 0x10193f3d 2 / dx 0xd9950 1
    # height search: start = radius-phase height after success + bump (44 / 10)
    height_bump: float                        # ued 0x10193fca 4 / dx 0
    height_phase_radius: float | None         # dx 0xd99c3 12 (the stored pair is never tested together); ued: the best radius
    height_cap: float                         # ued 0x10193ff4 70 / dx 0xd9770 79
    height_floor: float                       # ued 0x1019414a 40 / dx 0xd9a8b 10
    height_stop: float                        # ued 0x101940d5 1 / dx 1
    # probe start
    los_precheck: bool                        # dx 0xd9870: SingleLineCheck(TRACE_World) A->B first
    scout_on_traced_floor: bool               # dx 0xd97ca: scout on the traced floor under A; ued 0x10193e9b: at A
    know_visible: bool                        # pointReachable(B, bKnowVisible): dx 0xd9905 1 / ued 0x10193ec5 0
    # stored size / Distance
    size_rounding: str                        # "round" (appRound, half-even) / "trunc" (int())
    # jumps
    jump_fall_limit: float | None             # dx 0xc30ce 350; ued none
    find_jump_up: bool                        # ued 0x10184b83 runs FindJumpUp on a wall; dx nothing
    # prune                                                    ued 0x10176790 / dx 0xb1990
    prune_compare: str                        # "f32-le" (ued, sigma <= 1.2f*gamma) / "f64-strict" (dx)
    bot_only_radius: int                      # BotOnlyPath(): ued 0x10193bc4 R < 24 / dx 0xd9470 R < 12
    monster_radius: int                       # MonsterPath(): ued 0x10193c52 52 & 40 / dx 0xd9440 22 & 51
    monster_height: int
    # addVisNoReach scout                                      ued 0x101774e0 / dx 0xb1e50
    vis_scout_radius: float
    vis_scout_height: float
    residue: bool                             # dx: the search residue fields are reproduced

    def as_args(self) -> dict:
        """The keyword arguments of `uedcli_native.PresetIn`."""
        return {k: v for k, v in dataclasses.asdict(self).items()
                if k not in ("name", "skip_deleted")}


DEUSEX_1112FM = PathPreset(
    name="deusex-1112fm", skip_deleted=False,
    scout_jump_z=120.0, scout_ground_speed=120.0, scout_max_step_height=25.0,
    scout_base_eye_height=0.0,
    radius_start=12.0, radius_phase_height=10.0, radius_phase_height_after_success=10.0,
    radius_cap=115.0, radius_stop=1.0,
    height_bump=0.0, height_phase_radius=12.0, height_cap=79.0, height_floor=10.0,
    height_stop=1.0,
    los_precheck=True, scout_on_traced_floor=True, know_visible=True,
    size_rounding="trunc",
    jump_fall_limit=350.0, find_jump_up=False,
    prune_compare="f64-strict", bot_only_radius=12, monster_radius=22, monster_height=51,
    vis_scout_radius=22.0, vis_scout_height=51.0,
    residue=True)

UED22_469 = PathPreset(
    name="ued22-469", skip_deleted=True,
    scout_jump_z=320.0, scout_ground_speed=320.0, scout_max_step_height=25.0,
    scout_base_eye_height=None,
    radius_start=18.0, radius_phase_height=39.0, radius_phase_height_after_success=40.0,
    radius_cap=70.0, radius_stop=2.0,
    height_bump=4.0, height_phase_radius=None, height_cap=70.0, height_floor=40.0,
    height_stop=1.0,
    los_precheck=False, scout_on_traced_floor=False, know_visible=False,
    size_rounding="round",
    jump_fall_limit=None, find_jump_up=True,
    prune_compare="f32-le", bot_only_radius=24, monster_radius=52, monster_height=40,
    vis_scout_radius=18.0, vis_scout_height=39.0,
    residue=False)

_PRESETS = {p.name: p for p in (DEUSEX_1112FM, UED22_469)}


def preset(name: str) -> PathPreset:
    """The preset for a `pathing` value other than `none`; a `ValueError` names an unknown one."""
    p = _PRESETS.get(name)
    if p is None:
        raise ValueError(f"unknown pathing preset {name!r} (known: {', '.join(_PRESETS)})")
    return p
