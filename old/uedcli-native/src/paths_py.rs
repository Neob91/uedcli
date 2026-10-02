//! The path-build PyO3 surface (`build_path_graph`, `place_path_nodes`; board item
//! `native-path-build-reachspecs-in-level`, plan "Interface contract").

use super::*;

fn map_path_err(e: paths::PathError) -> PyErr {
    PathError::new_err(e.to_string())
}

/// One rule preset (`uedcli/native/pathrules.py` owns the two instances).  Keyword-only; every
/// field is a `paths::Preset` field — see there for the RVA each constant comes from.
/// `size_rounding` ∈ {"round" (appRound), "trunc"}; `prune_compare` ∈ {"f32-le", "f64-strict"}.
#[pyclass(name = "PresetIn")]
#[derive(Clone)]
pub(crate) struct PresetIn {
    preset: paths::Preset,
}

#[pymethods]
impl PresetIn {
    #[new]
    #[pyo3(signature = (*, scout_jump_z, scout_ground_speed, scout_max_step_height,
        scout_base_eye_height, radius_start, radius_phase_height, radius_phase_height_after_success,
        radius_cap, radius_stop, height_bump, height_phase_radius, height_cap, height_floor,
        height_stop, los_precheck, scout_on_traced_floor, know_visible, size_rounding,
        jump_fall_limit, find_jump_up, prune_compare, bot_only_radius, monster_radius,
        monster_height, vis_scout_radius, vis_scout_height, residue))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        scout_jump_z: f32,
        scout_ground_speed: f32,
        scout_max_step_height: f32,
        scout_base_eye_height: Option<f32>,
        radius_start: f32,
        radius_phase_height: f32,
        radius_phase_height_after_success: f32,
        radius_cap: f32,
        radius_stop: f32,
        height_bump: f32,
        height_phase_radius: Option<f32>,
        height_cap: f32,
        height_floor: f32,
        height_stop: f32,
        los_precheck: bool,
        scout_on_traced_floor: bool,
        know_visible: bool,
        size_rounding: &str,
        jump_fall_limit: Option<f32>,
        find_jump_up: bool,
        prune_compare: &str,
        bot_only_radius: i32,
        monster_radius: i32,
        monster_height: i32,
        vis_scout_radius: f32,
        vis_scout_height: f32,
        residue: bool,
    ) -> PyResult<Self> {
        let size_rounding = match size_rounding {
            "round" => paths::SizeRounding::AppRound,
            "trunc" => paths::SizeRounding::Truncate,
            other => return Err(PathError::new_err(format!("size_rounding {other:?}: expect \"round\" or \"trunc\""))),
        };
        let prune_compare = match prune_compare {
            "f32-le" => paths::PruneCompare::F32NonStrict,
            "f64-strict" => paths::PruneCompare::F64Strict,
            other => return Err(PathError::new_err(format!("prune_compare {other:?}: expect \"f32-le\" or \"f64-strict\""))),
        };
        Ok(PresetIn {
            preset: paths::Preset {
                scout_jump_z,
                scout_ground_speed,
                scout_max_step_height,
                scout_base_eye_height,
                radius_start,
                radius_phase_height,
                radius_phase_height_after_success,
                radius_cap,
                radius_stop,
                height_bump,
                height_phase_radius,
                height_cap,
                height_floor,
                height_stop,
                los_precheck,
                scout_on_traced_floor,
                know_visible,
                size_rounding,
                jump_fall_limit,
                find_jump_up,
                prune_compare,
                bot_only_radius,
                monster_radius,
                monster_height,
                vis_scout_radius,
                vis_scout_height,
                residue,
            },
        })
    }
}

/// `MoverIn`: `(name, model_body_bytes, location xyz, rotation pyr, pre_pivot xyz, b_block_actors)`.
type MoverTuple = (String, Vec<u8>, [f32; 3], [i32; 3], [f32; 3], bool);
/// `NavIn`: `(index, class_kind, location xyz, rotation pyr, collision_radius, collision_height,
/// b_one_way_path, lift_tag, url, tag)`; strings casefolded by Python.
type NavTuple = (usize, String, [f32; 3], [i32; 3], f32, f32, bool, String, String, String);
/// `ZoneIn`: `(zone_number, b_water, b_pain, damage_type_casefold, gravity xyz, fluid_friction,
/// velocity xyz)`.
type ZoneTuple = (i32, bool, bool, String, [f32; 3], f32, [f32; 3]);

fn nav_from_tuple(t: &NavTuple) -> Result<paths::NavIn, paths::PathError> {
    let (index, kind, loc, rot, radius, height, one_way, lift_tag, url, tag) = t;
    Ok(paths::NavIn {
        index: *index,
        kind: paths::NavKind::parse(kind)?,
        location: model::Vec3::new(loc[0], loc[1], loc[2]),
        rotation: *rot,
        collision_radius: *radius,
        collision_height: *height,
        b_one_way_path: *one_way,
        lift_tag: lift_tag.clone(),
        url: url.clone(),
        tag: tag.clone(),
    })
}

/// The level Model: a `Built` handle or the serialized body bytes (`serialize_model` format).
fn model_from_any(model: &Bound<'_, PyAny>) -> PyResult<model::Model> {
    if let Ok(built) = model.extract::<PyRef<Built>>() {
        return Ok(built.model.clone());
    }
    if let Ok(bytes) = model.extract::<Vec<u8>>() {
        return model_read::parse(&bytes).map_err(|e| PathError::new_err(e.to_string()));
    }
    Err(PathError::new_err(format!("model must be a Built handle or bytes, got {}", model.get_type())))
}

/// `PathGraphOut`: the built graph.  `specs` = `ReachSpecs` in creation order as
/// `(distance, start_idx, end_idx, r, h, flags, pruned)`; per nav `paths`/`upstream`/
/// `pruned_paths` (spec indices), `vis_no_reach` (nav indices), `next_nav`, all -1 = empty;
/// `residue` = per nav `(visited_weight, best_path_weight, cost, b_end_point, previous_path,
/// next_ordered, prev_ordered)` or `None` when the preset does not report it.
#[pyclass(name = "PathGraphOut")]
pub(crate) struct PathGraphOut {
    #[pyo3(get)]
    specs: Vec<(i32, i32, i32, i32, i32, i32, bool)>,
    #[pyo3(get)]
    paths: Vec<[i32; 16]>,
    #[pyo3(get)]
    upstream: Vec<[i32; 16]>,
    #[pyo3(get)]
    pruned_paths: Vec<[i32; 16]>,
    #[pyo3(get)]
    vis_no_reach: Vec<[i32; 16]>,
    #[pyo3(get)]
    next_nav: Vec<i32>,
    #[pyo3(get)]
    residue: Option<Vec<(i32, i32, i32, bool, i32, i32, i32)>>,
    #[pyo3(get)]
    nav_list_head: i32,
    #[pyo3(get)]
    num_pruned: u32,
}

impl PathGraphOut {
    fn from_graph(g: &paths::PathGraph, pruned: u32, residue: bool) -> PathGraphOut {
        PathGraphOut {
            specs: g
                .specs
                .iter()
                .map(|s| (s.distance, s.start, s.end, s.collision_radius, s.collision_height, s.reach_flags, s.b_pruned))
                .collect(),
            paths: g.navs.iter().map(|n| n.paths).collect(),
            upstream: g.navs.iter().map(|n| n.upstream).collect(),
            pruned_paths: g.navs.iter().map(|n| n.pruned_paths).collect(),
            vis_no_reach: g.navs.iter().map(|n| n.vis_no_reach).collect(),
            next_nav: g.navs.iter().map(|n| n.next_nav).collect(),
            residue: residue.then(|| {
                g.navs
                    .iter()
                    .map(|n| {
                        let r = n.residue;
                        (r.visited_weight, r.best_path_weight, r.cost, r.b_end_point, r.previous_path, r.next_ordered, r.prev_ordered)
                    })
                    .collect()
            }),
            nav_list_head: g.nav_list_head,
            num_pruned: pruned,
        }
    }
}

/// `PlacementOut`: `createPaths`' result — `created` PathNode locations, `moved` existing nodes
/// `(nav_idx, xyz)`, `removed` nav indices, and the log lines the editor would print.
#[pyclass(name = "PlacementOut")]
pub(crate) struct PlacementOut {
    #[pyo3(get)]
    created: Vec<[f32; 3]>,
    #[pyo3(get)]
    moved: Vec<(usize, [f32; 3])>,
    #[pyo3(get)]
    removed: Vec<usize>,
    #[pyo3(get)]
    log: Vec<String>,
}

fn zone_from_tuple(t: &ZoneTuple) -> collision::ZoneIn {
    let (n, water, pain, damage, g, friction, v) = t;
    collision::ZoneIn {
        zone_number: *n,
        b_water: *water,
        b_pain: *pain,
        damage_type: damage.clone(),
        gravity: model::Vec3::new(g[0], g[1], g[2]),
        fluid_friction: *friction,
        velocity: model::Vec3::new(v[0], v[1], v[2]),
    }
}

fn mover_from_tuple(t: &MoverTuple) -> Result<collision::MoverIn, paths::PathError> {
    let (name, body, loc, rot, pp, block) = t;
    let model = model_read::parse(body).map_err(|e| paths::PathError(format!("Mover {name}: {e}")))?;
    Ok(collision::MoverIn {
        name: name.clone(),
        model,
        location: model::Vec3::new(loc[0], loc[1], loc[2]),
        rotation: *rot,
        pre_pivot: model::Vec3::new(pp[0], pp[1], pp[2]),
        b_block_actors: *block,
    })
}

/// `build_path_graph(model, movers, navs, zones, level_zone, preset) -> PathGraphOut` — the
/// reachspec build (`definePaths` minus marker spawning) over a built level.  Zero navs is a clean
/// empty graph.  Errors surface as `PathError` naming the offending value.
#[pyfunction]
pub(crate) fn build_path_graph(
    py: Python<'_>,
    model: &Bound<'_, PyAny>,
    movers: Vec<MoverTuple>,
    navs: Vec<NavTuple>,
    zones: Vec<ZoneTuple>,
    level_zone: ZoneTuple,
    preset: &PresetIn,
) -> PyResult<PathGraphOut> {
    let model = model_from_any(model)?;
    let navs: Vec<paths::NavIn> = navs.iter().map(nav_from_tuple).collect::<Result<_, _>>().map_err(map_path_err)?;
    let preset = preset.preset.clone();
    if navs.is_empty() {
        return Ok(PathGraphOut::from_graph(&paths::PathGraph::new(0), 0, preset.residue));
    }
    if model.nodes.is_empty() {
        return Err(PathError::new_err(format!("the level Model has no BSP nodes but {} nav actors need a world", navs.len())));
    }
    let movers: Vec<collision::MoverIn> = movers.iter().map(mover_from_tuple).collect::<Result<_, _>>().map_err(map_path_err)?;
    let zones: Vec<collision::ZoneIn> = zones.iter().map(zone_from_tuple).collect();
    let level_zone = zone_from_tuple(&level_zone);
    let residue = preset.residue;
    let (graph, pruned) = py
        .allow_threads(|| {
            let world = collision::World::new(&model, &movers, zones, level_zone)?;
            let mut cw = scout::CollisionWorld::new(world, preset.clone());
            paths::define_paths(&mut cw, &preset, &navs)
        })
        .map_err(map_path_err)?;
    Ok(PathGraphOut::from_graph(&graph, pruned, residue))
}

/// `place_path_nodes(model, movers, navs, zones, level_zone, starts) -> PlacementOut` — UED22's
/// `createPaths` auto-placement from the given start navs.  Not implemented yet (phase 2).
#[pyfunction]
pub(crate) fn place_path_nodes(
    model: &Bound<'_, PyAny>,
    movers: Vec<MoverTuple>,
    navs: Vec<NavTuple>,
    zones: Vec<ZoneTuple>,
    level_zone: ZoneTuple,
    starts: Vec<usize>,
) -> PyResult<PlacementOut> {
    let _model = model_from_any(model)?;
    let navs: Vec<paths::NavIn> = navs.iter().map(nav_from_tuple).collect::<Result<_, _>>().map_err(map_path_err)?;
    let _ = (&movers, &zones, &level_zone);
    for &s in &starts {
        if s >= navs.len() {
            return Err(PathError::new_err(format!("start nav index {s} out of range (roster has {} navs)", navs.len())));
        }
    }
    Err(PathError::new_err(
        "native path build: place_path_nodes (createPaths) is not implemented yet (phase 2)".to_string(),
    ))
}
