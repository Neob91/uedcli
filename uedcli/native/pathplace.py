"""`level paths define` (spec §5): UED22's `createPaths` auto-placement run natively over the
TRUNK, writing the new PathNodes back into the `Level`. The world BSP comes from the native CSG
build, each Mover's private model from `build_mover_shape_model`; the placement itself is Rust
(`uedcli_native.place_path_nodes`, `placer` below is the injectable seam).

Every run mints one `auto-path-<token>` label (minted like `actor duplicate`'s `dup-<token>`) and
strips the previous runs' `auto-path-*` nodes first, as `PATHS BUILD` strips `bAutoBuilt` ones. A
node the algorithm moves is moved, hand-placed or not (owner ruling 2026-09-05).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .. import labellib, rotation, t3dtree, typedprops
from ..model import Actor
from . import umodel as UM
from .materialize import _model_point_region, build_world_model
from .paths import MoverIn, NavIn, ZoneIn, _KINDS
from .unbuilt import _fpolys, build_mover_shape_model

AUTO_LABEL_PATTERN = "auto-path-*"
REUSE_DISTANCE = 1.0                  # uu: a new node this close to a stripped one keeps its name


class PathPlaceError(ValueError):
    """Placement cannot proceed -- names the offending actor/value (a clean exit 2)."""


@dataclass(frozen=True, kw_only=True)
class Placement:
    """The Rust `PlacementOut`: new node positions, moves of existing navs (by nav index), merge
    victims among the existing navs, and the log lines the editor would print."""
    created: tuple                    # xyz
    moved: tuple                      # (nav_index, xyz)
    removed: tuple                    # nav_index
    log: tuple


def placement_from_native(out) -> Placement:
    if isinstance(out, Placement):
        return out
    return Placement(created=tuple(tuple(float(c) for c in p) for p in out.created),
                     moved=tuple((int(i), tuple(float(c) for c in p)) for i, p in out.moved),
                     removed=tuple(int(i) for i in out.removed), log=tuple(out.log))


def _native_place_path_nodes(model_body, movers, navs, zones, level_zone, starts):
    import uedcli_native
    place = getattr(uedcli_native, "place_path_nodes", None)
    if place is None:
        raise PathPlaceError("the installed uedcli_native extension has no `place_path_nodes` -- "
                             "rebuild it (bin/test once, or `maturin develop`)")
    try:
        return place(model_body, movers, navs, zones, level_zone, starts)
    except Exception as e:
        raise PathPlaceError(f"native path placement failed: {e}") from e


placer = _native_place_path_nodes    # injectable: tests supply a fake


@dataclass(frozen=True, kw_only=True)
class DefineResult:
    token: str
    stripped: tuple                   # previous auto nodes removed before placement (names)
    created: tuple                    # names, placement order
    moved: tuple                      # names
    removed: tuple                    # existing nodes destroyed by the merge pass (names)
    starts: int
    log: tuple


# --- trunk actor values ---------------------------------------------------------------------------

def _fqcn(actor: Actor, index) -> str:
    cls = actor.cls or ""
    if "." in cls:
        return cls
    cands = index.bare_to_fqcn().get(cls.casefold(), set())
    if len(cands) != 1:
        raise PathPlaceError(f"actor {actor.name!r}: class {cls!r} resolves to "
                             f"{sorted(cands) or 'no class'} on the package path")
    return next(iter(cands))


def _effective(actor: Actor, info, key: str):
    """The stated value decoded through the class schema, else the class default; None for a
    property the class does not declare or a NAME/OBJECT `None`."""
    stated = next((v for k, v in actor.props if k.casefold() == key), None)
    v = info.typed_default((key, 0)) if stated is None else \
        typedprops.typed_value(stated, info.field(key))
    if v is typedprops.ABSENT or (isinstance(v, str) and v.casefold() == "none"):
        return None
    if isinstance(v, dict):
        return tuple(v[k] for k in ("x", "y", "z")) if "x" in v else \
            tuple(v[k] for k in ("pitch", "yaw", "roll"))
    return v


def _location(actor: Actor, info) -> tuple:
    if actor.location is not None:
        return tuple(float(c) for c in actor.location)
    return tuple(float(c) for c in (_effective(actor, info, "location") or (0.0, 0.0, 0.0)))


def _text(v) -> str:
    return "" if v is None else str(v).casefold()


def _vec(v) -> tuple:
    return (0.0, 0.0, 0.0) if v is None else tuple(float(c) for c in v)


def _zone_in(actor: Actor, info, zone_number: int) -> ZoneIn:
    return ZoneIn(zone_number=zone_number,
                  b_water=bool(_effective(actor, info, "bwaterzone")),
                  b_pain=bool(_effective(actor, info, "bpainzone")),
                  damage_type=_text(_effective(actor, info, "damagetype")),
                  gravity=_vec(_effective(actor, info, "zonegravity")),
                  fluid_friction=float(_effective(actor, info, "zonefluidfriction") or 0.0),
                  velocity=_vec(_effective(actor, info, "zonevelocity")))


def _nav_in(actor: Actor, info, fqcn: str, index, position: int) -> NavIn:
    kind = next((k for base, k in _KINDS if index.descends_from(fqcn, base)), "navigationpoint")
    return NavIn(index=position, class_kind=kind, location=_location(actor, info),
                 rotation=rotation.actor_rotation_uu(actor),
                 collision_radius=float(_effective(actor, info, "collisionradius")),
                 collision_height=float(_effective(actor, info, "collisionheight")),
                 b_one_way_path=bool(_effective(actor, info, "bonewaypath")),
                 lift_tag=_text(_effective(actor, info, "lifttag")),
                 url=_text(_effective(actor, info, "url")), tag=_text(_effective(actor, info, "tag")))


def _mover_in(actor: Actor, info) -> MoverIn:
    if actor.brush is None or not actor.brush.polys:
        raise PathPlaceError(f"Mover {actor.name!r} has no brush polygons -- its model cannot be built")
    model, _links = build_mover_shape_model(_fpolys(actor.brush, None, actor=actor.name))
    if not model.nodes:
        raise PathPlaceError(f"Mover {actor.name!r}: its brush model built no BSP nodes")
    return MoverIn(name=actor.name, model_body=UM.write_model_body(model),
                   location=_location(actor, info), rotation=rotation.actor_rotation_uu(actor),
                   pre_pivot=_vec(_effective(actor, info, "prepivot")),
                   b_block_actors=bool(_effective(actor, info, "bblockactors")))


def _is_auto(actor: Actor) -> bool:
    return any(labellib.match_label(AUTO_LABEL_PATTERN, lbl) for lbl in actor.labels)


def _mint_token(level) -> str:
    taken = {lbl for a in level.actors.values() for lbl in a.labels}
    while (token := f"auto-path-{t3dtree._rand_suffix()}") in taken:
        pass
    return token


def _pathnode_class(index) -> str:
    cands = index.bare_to_fqcn().get("pathnode", set())
    if len(cands) != 1:
        raise PathPlaceError(f"PathNode resolves to {sorted(cands) or 'no class'} on the package "
                             f"path; exactly one Engine.PathNode is needed")
    return next(iter(cands))


def define_paths(level, *, index, defaults) -> DefineResult:
    """Run the placement over `level` and MUTATE it: strip the previous auto nodes, apply the
    moves and merges, add the created `PathNode`s (name/rank reused from a stripped node within
    `REUSE_DISTANCE`, else a fresh `alloc_name`). Raises `PathPlaceError`/`NativeBuildError`
    naming the offending value; the level is untouched on an error."""
    from ..movers import is_mover
    pathnode_class = _pathnode_class(index)
    fqcns = {n: _fqcn(a, index) for n, a in level.actors.items()}
    infos = {n: defaults.for_class(f) for n, f in fqcns.items()}
    stripped = [n for n in level.order
                if index.descends_from(fqcns[n], "Engine.NavigationPoint") and _is_auto(level.actors[n])]
    for n in level.order:
        if index.descends_from(fqcns[n], "Engine.WarpZoneInfo"):
            raise PathPlaceError(f"actor {n!r} is a WarpZoneInfo: warp-zone marker edges are not "
                                 f"built (spec §4)")
    live = [n for n in level.order if n not in set(stripped)]
    level_info = next((n for n in live if index.descends_from(fqcns[n], "Engine.LevelInfo")), None)
    if level_info is None:
        raise PathPlaceError("the level has no LevelInfo")
    # Geometry first (a CSG failure must leave the trunk untouched): the world BSP, then movers.
    world_model, _brushes = build_world_model(level, index=index)
    if not world_model.nodes:
        raise PathPlaceError("the world builds no BSP nodes -- nothing to place paths in")
    movers, zones, navs, nav_in = [], [], [], []
    for n in live:
        a, f, info = level.actors[n], fqcns[n], infos[n]
        if index.descends_from(f, "Engine.NavigationPoint"):
            nav_in.append(_nav_in(a, info, f, index, len(navs)))
            navs.append(n)
        elif n != level_info and index.descends_from(f, "Engine.ZoneInfo"):
            zones.append(_zone_in(a, info, _model_point_region(world_model, _location(a, info))[1]))
        elif a.brush is not None and is_mover(a, index):
            movers.append(_mover_in(a, info))
    starts = [i for i, n in enumerate(navs) if index.descends_from(fqcns[n], "Engine.PlayerStart")]
    world_model.none_index = 0
    out = placement_from_native(placer(
        UM.write_model_body(world_model), [m.as_tuple() for m in movers],
        [v.as_tuple() for v in nav_in], [z.as_tuple() for z in zones],
        _zone_in(level.actors[level_info], infos[level_info], 0).as_tuple(), starts))
    for i, _p in out.moved:
        if not (0 <= i < len(navs)):
            raise PathPlaceError(f"placement moves nav index {i}, the level has {len(navs)}")
    for i in out.removed:
        if not (0 <= i < len(navs)):
            raise PathPlaceError(f"placement removes nav index {i}, the level has {len(navs)}")
    # --- mutate the level ---
    token = _mint_token(level)
    pool = {n: _location(level.actors[n], infos[n]) for n in stripped}
    for n in stripped + [navs[i] for i in out.removed]:
        del level.actors[n]
    level.order = [n for n in level.order if n in level.actors]
    moved = []
    for i, p in out.moved:
        level.actors[navs[i]].location = tuple(Decimal(str(c)) for c in p)
        moved.append(navs[i])
    existing = set(level.actors)
    created = []
    for p in out.created:
        near = next((n for n, q in pool.items()
                     if sum((a - b) ** 2 for a, b in zip(p, q)) <= REUSE_DISTANCE ** 2), None)
        if near is not None:
            del pool[near]
            name = near
        else:
            name = t3dtree.alloc_name("PathNode", existing, _rand=t3dtree._rand_suffix)
        existing.add(name)
        level.actors[name] = Actor(name=name, cls=pathnode_class,
                                   location=tuple(Decimal(str(c)) for c in p),
                                   labels=frozenset({token}))
        level.order.append(name)
        created.append(name)
    return DefineResult(token=token, stripped=tuple(stripped), created=tuple(created),
                        moved=tuple(moved), removed=tuple(navs[i] for i in out.removed),
                        starts=len(starts), log=out.log)
