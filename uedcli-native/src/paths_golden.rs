//! Golden reproduction of committed builds: inputs from `fixtures/paths/<map>.world.txt` +
//! `.model.bin` (+ `.mover<k>.bin`) made by `extract_world.py`, the expected graph from
//! `fixtures/paths/<map>.txt` made by `extract_fixture.py`.  Test-only.

use crate::collision::{CollisionModel, MoverIn, World, ZoneIn};
use crate::model::{Model, Vec3};
use crate::paths::{define_paths, FReachSpec, NavIn, NavKind, PathGraph, Preset};
use crate::scout::CollisionWorld;

pub(crate) struct WorldFixture {
    pub navs: Vec<NavIn>,
    pub zones: Vec<(Vec3, ZoneIn)>,
    pub level_zone: ZoneIn,
    pub movers: Vec<MoverIn>,
}

fn f(it: &mut dyn Iterator<Item = &str>) -> f32 {
    it.next().unwrap().parse().unwrap()
}

fn i(it: &mut dyn Iterator<Item = &str>) -> i32 {
    it.next().unwrap().parse().unwrap()
}

fn zone_of(it: &mut dyn Iterator<Item = &str>) -> ZoneIn {
    let water = it.next().unwrap() == "1";
    let pain = it.next().unwrap() == "1";
    let damage = it.next().unwrap().to_string();
    let g = Vec3::new(f(it), f(it), f(it));
    let friction = f(it);
    let v = Vec3::new(f(it), f(it), f(it));
    ZoneIn { zone_number: 0, b_water: water, b_pain: pain, damage_type: damage, gravity: g, fluid_friction: friction, velocity: v }
}

pub(crate) fn load_world(text: &str, mover_bodies: &[&[u8]]) -> WorldFixture {
    let mut fx = WorldFixture {
        navs: Vec::new(),
        zones: Vec::new(),
        level_zone: ZoneIn { zone_number: 0, b_water: false, b_pain: false, damage_type: "none".into(), gravity: Vec3::new(0.0, 0.0, -950.0), fluid_friction: 1.2, velocity: Vec3::new(0.0, 0.0, 0.0) },
        movers: Vec::new(),
    };
    for line in text.lines() {
        let mut it = line.split_whitespace();
        match it.next() {
            Some("nav") => {
                let index = it.next().unwrap().parse().unwrap();
                let _name = it.next().unwrap();
                let kind = NavKind::parse(it.next().unwrap()).unwrap();
                let location = Vec3::new(f(&mut it), f(&mut it), f(&mut it));
                let rotation = [i(&mut it), i(&mut it), i(&mut it)];
                let collision_radius = f(&mut it);
                let collision_height = f(&mut it);
                let b_one_way_path = it.next().unwrap() == "1";
                let lift_tag = it.next().unwrap().to_string();
                let url = it.next().unwrap().to_string();
                let tag = it.next().unwrap().to_string();
                fx.navs.push(NavIn { index, kind, location, rotation, collision_radius, collision_height, b_one_way_path, lift_tag, url: if url == "none" { String::new() } else { url }, tag });
            }
            Some("zone") => {
                let loc = Vec3::new(f(&mut it), f(&mut it), f(&mut it));
                fx.zones.push((loc, zone_of(&mut it)));
            }
            Some("level_zone") => fx.level_zone = zone_of(&mut it),
            Some("mover") => {
                let k: usize = it.next().unwrap().parse().unwrap();
                let name = it.next().unwrap().to_string();
                let location = Vec3::new(f(&mut it), f(&mut it), f(&mut it));
                let rotation = [i(&mut it), i(&mut it), i(&mut it)];
                let pre_pivot = Vec3::new(f(&mut it), f(&mut it), f(&mut it));
                let b_block_actors = it.next().unwrap() == "1";
                let model = crate::model_read::parse(mover_bodies[k]).unwrap();
                fx.movers.push(MoverIn { name, model, location, rotation, pre_pivot, b_block_actors });
            }
            _ => {}
        }
    }
    fx
}

/// The ZoneInfos' zone numbers come from the level's own `PointRegion` at their Location.
pub(crate) fn make_world(fx: &WorldFixture, level: &Model) -> World {
    let lvl = CollisionModel::level(level);
    let zones: Vec<ZoneIn> = fx.zones.iter().map(|(loc, z)| ZoneIn { zone_number: lvl.point_region(*loc), ..z.clone() }).collect();
    World::new(level, &fx.movers, zones, fx.level_zone.clone()).unwrap()
}

pub(crate) fn load_expected(text: &str) -> (Vec<FReachSpec>, Vec<[[i32; 16]; 4]>) {
    let mut specs = Vec::new();
    let mut arrays = Vec::new();
    for line in text.lines() {
        let mut it = line.split_whitespace();
        match it.next() {
            Some("spec") => {
                let v: Vec<i32> = it.map(|s| s.parse().unwrap()).collect();
                specs.push(FReachSpec { distance: v[0], start: v[1], end: v[2], collision_radius: v[3], collision_height: v[4], reach_flags: v[5], b_pruned: v[6] != 0 });
            }
            Some("nav") => {
                let rest: Vec<&str> = it.collect();
                let mut arr = [[-1i32; 16]; 4];
                for (k, key) in ["P", "U", "PR", "VNR"].iter().enumerate() {
                    let at = rest.iter().position(|s| s == key).unwrap();
                    for (j, slot) in arr[k].iter_mut().enumerate() {
                        *slot = rest[at + 1 + j].parse().unwrap();
                    }
                }
                arrays.push(arr);
            }
            _ => {}
        }
    }
    (specs, arrays)
}

/// Every spec by (start, end) with its fields, the creation order, and the four per-node arrays;
/// panics with the full diff.
pub(crate) fn graph_diff(g: &PathGraph, expected: &[FReachSpec], arrays: &[[[i32; 16]; 4]]) -> Vec<String> {
    let key = |s: &FReachSpec| (s.start, s.end);
    let mut diffs = Vec::new();
    let exp: std::collections::BTreeMap<_, _> = expected.iter().map(|s| (key(s), *s)).collect();
    let got: std::collections::BTreeMap<_, _> = g.specs.iter().map(|s| (key(s), *s)).collect();
    for (k, e) in &exp {
        match got.get(k) {
            None => diffs.push(format!("missing {k:?}: golden {e:?}")),
            Some(s) if s != e => diffs.push(format!("differs {k:?}: golden {e:?} native {s:?}")),
            _ => {}
        }
    }
    for (k, s) in &got {
        if !exp.contains_key(k) {
            diffs.push(format!("extra {k:?}: native {s:?}"));
        }
    }
    if g.specs.len() != expected.len() || g.specs.iter().zip(expected).any(|(a, b)| a != b) {
        diffs.push(format!("spec order/count: native {} golden {}", g.specs.len(), expected.len()));
    }
    for (n, arr) in arrays.iter().enumerate() {
        let nav = &g.navs[n];
        for (name, sim, disk) in [("Paths", &nav.paths, &arr[0]), ("upstreamPaths", &nav.upstream, &arr[1]), ("PrunedPaths", &nav.pruned_paths, &arr[2]), ("VisNoReachPaths", &nav.vis_no_reach, &arr[3])] {
            if sim != disk {
                diffs.push(format!("nav {n} {name}: native {sim:?} golden {disk:?}"));
            }
        }
    }
    diffs
}

pub(crate) fn build(fx: &WorldFixture, level: &Model, p: &Preset) -> PathGraph {
    let mut cw = CollisionWorld::new(make_world(fx, level), p.clone());
    define_paths(&mut cw, p, &fx.navs).unwrap().0
}

/// The committed UED22 build of `evidence/pathlab-define.dx` (40 nodes, 281 specs), `ued22-469`.
#[test]
fn pathlab_define_ued22_graph_is_exact() {
    let fx = load_world(include_str!("../fixtures/paths/pathlab-define.world.txt"), &[]);
    let level = crate::model_read::parse(include_bytes!("../fixtures/paths/pathlab-define.model.bin")).unwrap();
    let g = build(&fx, &level, &Preset::ued22_469());
    let (specs, arrays) = load_expected(include_str!("../fixtures/paths/pathlab-define.txt"));
    let diffs = graph_diff(&g, &specs, &arrays);
    assert!(diffs.is_empty(), "{} differences:\n{}", diffs.len(), diffs.join("\n"));
}

/// The committed UED22 build of `evidence/pathlab2-define.dx` (water zone, a closed door Mover, a
/// lift, teleporters, pickups → 50 navs incl. the editor's InventorySpots at garbage locations):
/// every spec and every `Paths`/`upstreamPaths`/`PrunedPaths` array exact.  `VisNoReachPaths`
/// differs on exactly three water-room nodes (15, 19, 48): their entries come from the route search,
/// and UED22's `findPathToward` is undecoded (the build runs the decoded `dx` search for both
/// presets, spec §3.4) — pinned here as the known gap.
#[test]
fn pathlab2_define_ued22_graph_is_exact_except_the_water_room_vis_no_reach() {
    let fx = load_world(
        include_str!("../fixtures/paths/pathlab2-define.world.txt"),
        &[include_bytes!("../fixtures/paths/pathlab2-define.mover0.bin"), include_bytes!("../fixtures/paths/pathlab2-define.mover1.bin")],
    );
    let level = crate::model_read::parse(include_bytes!("../fixtures/paths/pathlab2-define.model.bin")).unwrap();
    let g = build(&fx, &level, &Preset::ued22_469());
    let (specs, arrays) = load_expected(include_str!("../fixtures/paths/pathlab2-define.txt"));
    let diffs = graph_diff(&g, &specs, &arrays);
    let known: Vec<String> = [15, 19, 48].iter().map(|n| format!("nav {n} VisNoReachPaths")).collect();
    let unexpected: Vec<&String> = diffs.iter().filter(|d| !known.iter().any(|k| d.starts_with(k))).collect();
    assert!(unexpected.is_empty(), "{} unexpected differences:\n{}", unexpected.len(), unexpected.iter().map(|s| s.as_str()).collect::<Vec<_>>().join("\n"));
    assert_eq!(diffs.len(), 3, "the known VisNoReachPaths gap: {diffs:?}");
}

/// Retail `02_NYC_Bar.dx` under `deusex-1112fm`: the fixture is extracted locally (the retail map is
/// not committed) — `extract_world.py <map> deusex <dir>/nyc-bar` and `extract_fixture.py <map> >
/// <dir>/nyc-bar-retail.txt`, then `UEDCLI_PATHS_FIXTURE_DIR=<dir> cargo test -- --ignored`.
#[test]
#[ignore]
fn nyc_bar_retail_dx_graph() {
    let dir = std::env::var("UEDCLI_PATHS_FIXTURE_DIR").expect("UEDCLI_PATHS_FIXTURE_DIR");
    let read = |name: &str| std::fs::read(format!("{dir}/{name}")).unwrap_or_else(|e| panic!("{dir}/{name}: {e}"));
    let world = String::from_utf8(read("nyc-bar.world.txt")).unwrap();
    let movers: Vec<Vec<u8>> = (0..5).map(|k| read(&format!("nyc-bar.mover{k}.bin"))).collect();
    let refs: Vec<&[u8]> = movers.iter().map(|m| m.as_slice()).collect();
    let fx = load_world(&world, &refs);
    let level = crate::model_read::parse(&read("nyc-bar.model.bin")).unwrap();
    let g = build(&fx, &level, &Preset::deusex_1112fm());
    let (specs, arrays) = load_expected(&String::from_utf8(read("nyc-bar-retail.txt")).unwrap());
    let diffs = graph_diff(&g, &specs, &arrays);
    let shared = specs.iter().filter(|e| g.specs.iter().any(|s| s.start == e.start && s.end == e.end)).count();
    eprintln!("Bar: native {} specs, retail {}, shared pairs {}, {} differences", g.specs.len(), specs.len(), shared, diffs.len());
    for d in &diffs {
        eprintln!("{d}");
    }
    // Measured state (2026-09-05): every one of the 889 retail pairs is built, in retail order,
    // with retail Distance/height/flags/bPruned; 81 specs record a LARGER radius than retail, all
    // starting or ending at four nodes (1, 7, 34, 36) that hug one wall (y = 128), where the retail
    // radius is exactly the largest grid value whose box fits at the node WITHOUT a `FindSpot`
    // nudge.  Native's nudge rescues the next sizes; why the 1112fm build did not is open (every
    // step of its placement path was checked against the binary: `FindSpot`, `AdjustSpot`,
    // `FarMoveActor`, the walker's hit fill, `CheckEncroachment` with no hash).
    assert_eq!((g.specs.len(), shared), (889, 889));
    assert!(diffs.iter().all(|d| d.starts_with("differs")), "only per-spec field differences expected");
    assert_eq!(diffs.len(), 81);
}

/// Diagnostic: trace `findBestReachable`'s probes for one Bar pair (`UEDCLI_PATHS_PAIR=a,b`).
#[test]
#[ignore]
fn nyc_bar_probe_trace() {
    use crate::paths::{find_best_reachable, ReachWorld};
    let dir = std::env::var("UEDCLI_PATHS_FIXTURE_DIR").expect("UEDCLI_PATHS_FIXTURE_DIR");
    let pair = std::env::var("UEDCLI_PATHS_PAIR").expect("UEDCLI_PATHS_PAIR");
    let mut it = pair.split(',');
    let (a, b): (usize, usize) = (it.next().unwrap().parse().unwrap(), it.next().unwrap().parse().unwrap());
    let read = |name: &str| std::fs::read(format!("{dir}/{name}")).unwrap();
    let world = String::from_utf8(read("nyc-bar.world.txt")).unwrap();
    let movers: Vec<Vec<u8>> = (0..5).map(|k| read(&format!("nyc-bar.mover{k}.bin"))).collect();
    let refs: Vec<&[u8]> = movers.iter().map(|m| m.as_slice()).collect();
    let fx = load_world(&world, &refs);
    let level = crate::model_read::parse(&read("nyc-bar.model.bin")).unwrap();
    let p = Preset::deusex_1112fm();
    let mut cw = CollisionWorld::new(make_world(&fx, &level), p.clone());
    let (na, nb) = (fx.navs[a].clone(), fx.navs[b].clone());
    eprintln!("A {:?} B {:?} visible {}", na.location, nb.location, cw.line_visible(na.location, nb.location));
    let res = find_best_reachable(&p, &mut |r, h| {
        let flags = cw.probe(&na, &nb, r, h);
        eprintln!("  probe r={r} h={h} -> flags {flags} scout at {:?}", cw.pawn.scout.location);
        flags
    });
    eprintln!("result {res:?}");
}


