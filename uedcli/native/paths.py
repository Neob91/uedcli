"""The path pass `level materialize` runs over a BUILT package (spec §3): read the roster, the
world Model, the nav actors, the zones and the movers; hand them to the Rust builder
(`uedcli_native.build_path_graph`); splice the graph back — the `ReachSpecs` run inside the ULevel
body, each nav actor's path tags, `LevelInfo.NavigationPointList` — and re-lay the package with the
resized bodies (`pkg_write.relayout_package`). Nothing else in the package changes.

Python owns the package read/write, class resolution (through the game's `ClassIndex`, never a name
suffix), the presets (`pathrules.py`) and the interface shapes below (plan.md "Interface contract");
Rust owns every geometric and algorithmic step. `graph_builder` is module-level so a test can supply
a fake; the real extension lacking the symbol is an error, not a fallback.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .. import typedprops, upackage
from ..mapimport import _skip_state_frame
from ..upackage import (PT_BOOL, PT_BYTE, PT_FLOAT, PT_INT, PT_NAME, PT_OBJECT, PT_STR, PT_STRUCT,
                        PropertyTag, read_compact_index, read_fstring, read_property_tags)
from . import actor_write as AW
from . import umodel as UM
from .actor_write import Prop
from .level_write import ReachSpec, write_reach_specs
from .materialize import _model_point_region
from .pathrules import NODE_ARRAY_SLOTS, preset as _preset
from .pkg_write import relayout_package


class PathPassError(ValueError):
    """The pass cannot fully satisfy the build (spec §3 exit conditions) -- names the offending
    actor/value. A `ValueError`, so `apply.run_materialize` turns it into a clean exit 2."""


# --- interface shapes (Rust <-> Python) ----------------------------------------------------------

_KINDS = (("Engine.LiftCenter", "liftcenter"), ("Engine.LiftExit", "liftexit"),
          ("Engine.Teleporter", "teleporter"), ("Engine.WarpZoneMarker", "warpzonemarker"),
          ("Engine.PlayerStart", "playerstart"))


@dataclass(frozen=True, kw_only=True)
class NavIn:
    index: int                       # position in the nav list (= what the graph's indices mean)
    class_kind: str
    location: tuple
    rotation: tuple
    collision_radius: float
    collision_height: float
    b_one_way_path: bool
    lift_tag: str                    # casefolded
    url: str
    tag: str

    def as_tuple(self) -> tuple:
        return (self.index, self.class_kind, self.location, self.rotation, self.collision_radius,
                self.collision_height, self.b_one_way_path, self.lift_tag, self.url, self.tag)


@dataclass(frozen=True, kw_only=True)
class MoverIn:
    name: str
    model_body: bytes                # the mover's BUILT private Model body (`serialize_model` format)
    location: tuple
    rotation: tuple
    pre_pivot: tuple
    b_block_actors: bool

    def as_tuple(self) -> tuple:
        return (self.name, self.model_body, self.location, self.rotation, self.pre_pivot,
                self.b_block_actors)


@dataclass(frozen=True, kw_only=True)
class ZoneIn:
    zone_number: int
    b_water: bool
    b_pain: bool
    damage_type: str                 # casefolded
    gravity: tuple
    fluid_friction: float
    velocity: tuple

    def as_tuple(self) -> tuple:
        return (self.zone_number, self.b_water, self.b_pain, self.damage_type, self.gravity,
                self.fluid_friction, self.velocity)


@dataclass(frozen=True, kw_only=True)
class SpecOut:
    distance: int
    start: int                       # nav index
    end: int
    radius: int
    height: int
    flags: int
    pruned: int


@dataclass(frozen=True, kw_only=True)
class NavResidue:
    """The `findPathToward` residue `deusex-1112fm` reproduces (spec §3.4); all zero = nothing."""
    visited_weight: int = 0
    best_path_weight: int = 0
    cost: int = 0
    b_end_point: bool = False
    previous_path: int = -1          # nav index or -1
    next_ordered: int = -1
    prev_ordered: int = -1


@dataclass(frozen=True, kw_only=True)
class NavOut:
    paths: tuple                     # spec indices, -1 empty (up to 16)
    upstream: tuple
    pruned_paths: tuple
    vis_no_reach: tuple              # nav indices, -1 empty
    next_nav: int                    # nav index or -1
    residue: NavResidue | None


@dataclass(frozen=True, kw_only=True)
class PathGraph:
    specs: tuple                     # SpecOut, creation order
    nodes: tuple                     # NavOut per nav, in nav order
    nav_list_head: int               # nav index or -1


_EMPTY_16 = (-1,) * NODE_ARRAY_SLOTS


def empty_graph(n_navs: int) -> PathGraph:
    """The graph of a path-less map: what `undefinePaths` leaves behind."""
    node = NavOut(paths=_EMPTY_16, upstream=_EMPTY_16, pruned_paths=_EMPTY_16,
                  vis_no_reach=_EMPTY_16, next_nav=-1, residue=None)
    return PathGraph(specs=(), nodes=(node,) * n_navs, nav_list_head=-1)


def graph_from_native(out) -> PathGraph:
    """Marshal the Rust `PathGraphOut` (`uedcli-native/src/paths_py.rs`: `specs`, the per-nav
    columns `paths`/`upstream`/`pruned_paths`/`vis_no_reach`/`next_nav`, `residue` per nav or
    None, `nav_list_head`) into `PathGraph`."""
    if isinstance(out, PathGraph):
        return out
    residue = out.residue
    nodes = tuple(
        NavOut(paths=tuple(p), upstream=tuple(u), pruned_paths=tuple(pp), vis_no_reach=tuple(v),
               next_nav=int(nn),
               residue=None if residue is None else NavResidue(
                   visited_weight=int(residue[i][0]), best_path_weight=int(residue[i][1]),
                   cost=int(residue[i][2]), b_end_point=bool(residue[i][3]),
                   previous_path=int(residue[i][4]), next_ordered=int(residue[i][5]),
                   prev_ordered=int(residue[i][6])))
        for i, (p, u, pp, v, nn) in enumerate(zip(out.paths, out.upstream, out.pruned_paths,
                                                   out.vis_no_reach, out.next_nav)))
    return PathGraph(specs=tuple(SpecOut(distance=int(d), start=int(s), end=int(e), radius=int(r),
                                         height=int(h), flags=int(f), pruned=int(p))
                                 for d, s, e, r, h, f, p in out.specs),
                     nodes=nodes, nav_list_head=int(out.nav_list_head))


def _native_build_path_graph(model_body, movers, navs, zones, level_zone, preset_args):
    import uedcli_native
    if not hasattr(uedcli_native, "build_path_graph") or not hasattr(uedcli_native, "PresetIn"):
        raise PathPassError("the installed uedcli_native extension has no `build_path_graph` -- "
                            "rebuild it (bin/test once, or `maturin develop`)")
    try:
        return uedcli_native.build_path_graph(model_body, movers, navs, zones, level_zone,
                                              uedcli_native.PresetIn(**preset_args))
    except Exception as e:                       # PathError / BuildError: named, never a traceback
        raise PathPassError(f"native path build failed: {e}") from e


graph_builder = _native_build_path_graph     # injectable: tests supply a fake


# --- reading the built package -------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class _Actor:
    export: int                      # 0-based export index
    name: str
    fqcn: str
    props_start: int                 # after the StateFrame
    tags: tuple
    none_start: int                  # where the `None` terminator (and any trailing bytes) begins


@dataclass(frozen=True, kw_only=True)
class _LevelBody:
    export: int
    roster: tuple                    # the Actors array, refs as stored (0 = None hole)
    model_ref: int
    specs: tuple                     # (distance, start_ref, end_ref, r, h, flags, pruned)
    specs_span: tuple                # [start, end) of the ReachSpecs run (count included), absolute


def _read_level(pkg: upackage.Package) -> _LevelBody:
    li = next((i for i in range(len(pkg.exports)) if pkg.object_class_name(i + 1) == "Level"), None)
    if li is None:
        raise PathPassError("package has no Level export")
    e = pkg.exports[li]
    buf, end = pkg.buf, e["soff"] + e["ssize"]
    _, pos = read_property_tags(pkg, e["soff"], end)
    num, = struct.unpack_from("<i", buf, pos); pos += 8               # Num, Max
    roster = []
    for _ in range(num):
        r, pos = read_compact_index(buf, pos); roster.append(r)
    for _ in range(4):                                                # FURL: protocol host map portal
        _, pos = read_fstring(buf, pos)
    n_ops, pos = read_compact_index(buf, pos)
    for _ in range(n_ops):
        _, pos = read_fstring(buf, pos)
    pos += 8                                                          # port, valid
    model_ref, pos = read_compact_index(buf, pos)
    specs_start = pos
    cnt, pos = read_compact_index(buf, pos)
    specs = []
    for _ in range(cnt):
        d, = struct.unpack_from("<i", buf, pos); pos += 4
        s, pos = read_compact_index(buf, pos)
        t, pos = read_compact_index(buf, pos)
        r, h, f = struct.unpack_from("<iii", buf, pos); pos += 12
        specs.append((d, s, t, r, h, f, buf[pos])); pos += 1
    if pos > end:
        raise PathPassError(f"Level body: ReachSpecs run overruns the body ({pos} > {end})")
    return _LevelBody(export=li, roster=tuple(roster), model_ref=model_ref, specs=tuple(specs),
                      specs_span=(specs_start, pos))


def _read_actor(pkg: upackage.Package, export: int) -> _Actor:
    e = pkg.exports[export]
    name = pkg.names[e["nm"]]
    fqcn = pkg.object_path(e["cls"])
    if fqcn is None:
        raise PathPassError(f"actor {name!r}: class ref {e['cls']} does not resolve")
    start = _skip_state_frame(pkg, e)
    tags, after = read_property_tags(pkg, start, e["soff"] + e["ssize"])
    return _Actor(export=export, name=name, fqcn=fqcn, props_start=start, tags=tuple(tags),
                  none_start=tags[-1].span[1] if tags else start)


def _decode(pkg: upackage.Package, t: PropertyTag):
    if t.ptype == PT_FLOAT:
        return struct.unpack("<f", t.raw)[0]
    if t.ptype == PT_INT:
        return struct.unpack("<i", t.raw)[0]
    if t.ptype == PT_BYTE:
        return t.raw[0]
    if t.ptype == PT_BOOL:
        return t.bool_value
    if t.ptype == PT_NAME:
        return pkg.names[read_compact_index(t.raw, 0)[0]]
    if t.ptype == PT_OBJECT:
        return read_compact_index(t.raw, 0)[0]
    if t.ptype == PT_STR:
        return read_fstring(t.raw, 0)[0]
    if t.ptype == PT_STRUCT and t.struct_name == "Vector":
        return struct.unpack("<fff", t.raw)
    if t.ptype == PT_STRUCT and t.struct_name == "Rotator":
        return struct.unpack("<iii", t.raw)
    return t.raw


def _default(info, key: str):
    """A class default in the pass's own shape: struct dicts as tuples, an undeclared property as
    None, a NAME/OBJECT `none` as None."""
    v = info.typed_default((key, 0))
    if v is typedprops.ABSENT:
        return None
    if isinstance(v, dict):
        return tuple(v[k] for k in ("x", "y", "z")) if "x" in v else \
            tuple(v[k] for k in ("pitch", "yaw", "roll"))
    if isinstance(v, str) and v.casefold() == "none":
        return None
    return v


def _value(pkg: upackage.Package, actor: _Actor, info, key: str):
    """The actor's effective value for `key` (casefolded): the stored tag, else the class default."""
    t = next((t for t in actor.tags if t.name.casefold() == key and t.array_index == 0), None)
    return _default(info, key) if t is None else _decode(pkg, t)


def _text(v) -> str:
    return "" if v is None else str(v).casefold()


def _vec(v) -> tuple:
    return (0.0, 0.0, 0.0) if v is None else tuple(float(c) for c in v)


def _rot(v) -> tuple:
    return (0, 0, 0) if v is None else tuple(int(c) for c in v)


@dataclass(frozen=True, kw_only=True)
class _Read:
    pkg: upackage.Package
    level: _LevelBody
    level_info: _Actor
    navs: tuple                      # _Actor per nav, roster order
    nav_in: tuple                    # NavIn per nav
    zones: tuple                     # ZoneIn
    level_zone: ZoneIn
    movers: tuple                    # MoverIn
    model: UM.Model | None


def _zone_in(pkg, actor: _Actor, info, zone_number: int) -> ZoneIn:
    return ZoneIn(zone_number=zone_number,
                  b_water=bool(_value(pkg, actor, info, "bwaterzone")),
                  b_pain=bool(_value(pkg, actor, info, "bpainzone")),
                  damage_type=_text(_value(pkg, actor, info, "damagetype")),
                  gravity=_vec(_value(pkg, actor, info, "zonegravity")),
                  fluid_friction=float(_value(pkg, actor, info, "zonefluidfriction") or 0.0),
                  velocity=_vec(_value(pkg, actor, info, "zonevelocity")))


def _mover_in(pkg, actor: _Actor, info) -> MoverIn:
    brush = _value(pkg, actor, info, "brush")
    e = pkg.exports[brush - 1] if isinstance(brush, int) and 0 < brush <= len(pkg.exports) else None
    if e is None or pkg.object_class_name(brush) != "Model":
        raise PathPassError(f"Mover {actor.name!r} has no brush Model to trace")
    body = pkg.buf[e["soff"]:e["soff"] + e["ssize"]]
    if not UM.parse_model_body(body, 0, len(body)).nodes:
        raise PathPassError(f"Mover {actor.name!r}: its brush Model {pkg.names[e['nm']]!r} is "
                            f"unbuilt (no BSP nodes) -- the path pass needs the built mover model")
    return MoverIn(name=actor.name, model_body=body,
                   location=_vec(_value(pkg, actor, info, "location")),
                   rotation=_rot(_value(pkg, actor, info, "rotation")),
                   pre_pivot=_vec(_value(pkg, actor, info, "prepivot")),
                   b_block_actors=bool(_value(pkg, actor, info, "bblockactors")))


def _nav_in(pkg, actor: _Actor, info, index: int, class_index) -> NavIn:
    kind = next((k for base, k in _KINDS if class_index.descends_from(actor.fqcn, base)),
                "navigationpoint")
    return NavIn(index=index, class_kind=kind,
                 location=_vec(_value(pkg, actor, info, "location")),
                 rotation=_rot(_value(pkg, actor, info, "rotation")),
                 collision_radius=float(_value(pkg, actor, info, "collisionradius")),
                 collision_height=float(_value(pkg, actor, info, "collisionheight")),
                 b_one_way_path=bool(_value(pkg, actor, info, "bonewaypath")),
                 lift_tag=_text(_value(pkg, actor, info, "lifttag")),
                 url=_text(_value(pkg, actor, info, "url")),
                 tag=_text(_value(pkg, actor, info, "tag")))


def _read_package(package_bytes: bytes, *, index, defaults, skip_deleted: bool) -> _Read:
    pkg = upackage.parse_package_bytes(package_bytes, where="built map", name="MyLevel")
    level = _read_level(pkg)
    actors = [_read_actor(pkg, r - 1) for r in level.roster if r > 0]     # None holes skipped
    level_info = next((a for a in actors if index.descends_from(a.fqcn, "Engine.LevelInfo")), None)
    if level_info is None:
        raise PathPassError("the Actors array carries no LevelInfo")
    model = None
    if 0 < level.model_ref <= len(pkg.exports):
        me = pkg.exports[level.model_ref - 1]
        model = UM.parse_model_body(pkg.buf, me["soff"], me["ssize"])
    def info_of(a: _Actor):
        try:
            return defaults.for_class(a.fqcn)
        except ValueError as e:                  # SchemaError: name the actor, not just the class
            raise PathPassError(f"actor {a.name!r}: {e}") from e

    navs, nav_in, zones, movers = [], [], [], []
    for a in actors:
        if index.descends_from(a.fqcn, "Engine.WarpZoneInfo"):
            raise PathPassError(f"actor {a.name!r} is a WarpZoneInfo: warp-zone marker edges are "
                                f"not built (spec §4), so its paths cannot be produced")
        if index.descends_from(a.fqcn, "Engine.NavigationPoint"):
            info = info_of(a)
            if skip_deleted and _value(pkg, a, info, "bdeleteme"):
                continue
            nav_in.append(_nav_in(pkg, a, info, len(navs), index))
            navs.append(a)
        elif a is not level_info and index.descends_from(a.fqcn, "Engine.ZoneInfo"):
            info = info_of(a)
            loc = _vec(_value(pkg, a, info, "location"))
            zone = _model_point_region(model, loc)[1] if model is not None else 0
            zones.append(_zone_in(pkg, a, info, zone))
        elif index.descends_from(a.fqcn, "Engine.Mover"):
            movers.append(_mover_in(pkg, a, info_of(a)))
    return _Read(pkg=pkg, level=level, level_info=level_info, navs=tuple(navs),
                 nav_in=tuple(nav_in), zones=tuple(zones),
                 level_zone=_zone_in(pkg, level_info, info_of(level_info), 0),
                 movers=tuple(movers), model=model)


# --- reading a graph back (the inverse of the write; the round-trip test and the replay) --------

def read_path_graph(package_bytes: bytes, *, index, defaults) -> PathGraph:
    """The path graph a package carries, in `PathGraph` shape (nav indices in roster order)."""
    r = _read_package(package_bytes, index=index, defaults=defaults, skip_deleted=False)
    pkg = r.pkg
    by_export = {a.export: i for i, a in enumerate(r.navs)}

    def nav_index(ref: int, where: str) -> int:
        if ref == 0:
            return -1
        i = by_export.get(ref - 1)
        if i is None:
            raise PathPassError(f"{where}: ref {ref} is not a NavigationPoint on the roster")
        return i

    def array(a: _Actor, name: str, refs: bool) -> tuple:
        out = [-1] * NODE_ARRAY_SLOTS
        for t in a.tags:
            if t.name.casefold() == name:
                v = _decode(pkg, t)
                out[t.array_index] = nav_index(v, f"{a.name}.{t.name}") if refs else v
        return tuple(out)

    def scalar(a: _Actor, name: str, default):
        t = next((t for t in a.tags if t.name.casefold() == name), None)
        return default if t is None else _decode(pkg, t)

    nodes = []
    for a in r.navs:
        nodes.append(NavOut(
            paths=array(a, "paths", False), upstream=array(a, "upstreampaths", False),
            pruned_paths=array(a, "prunedpaths", False),
            vis_no_reach=array(a, "visnoreachpaths", True),
            next_nav=nav_index(scalar(a, "nextnavigationpoint", 0), a.name),
            residue=NavResidue(
                visited_weight=scalar(a, "visitedweight", 0),
                best_path_weight=scalar(a, "bestpathweight", 0), cost=scalar(a, "cost", 0),
                b_end_point=bool(scalar(a, "bendpoint", False)),
                previous_path=nav_index(scalar(a, "previouspath", 0), a.name),
                next_ordered=nav_index(scalar(a, "nextordered", 0), a.name),
                prev_ordered=nav_index(scalar(a, "prevordered", 0), a.name))))
    specs = tuple(SpecOut(distance=d, start=nav_index(s, "ReachSpec.Start"),
                          end=nav_index(t, "ReachSpec.End"), radius=rr, height=h, flags=f,
                          pruned=p) for d, s, t, rr, h, f, p in r.level.specs)
    return PathGraph(specs=specs, nodes=tuple(nodes),
                     nav_list_head=nav_index(scalar(r.level_info, "navigationpointlist", 0),
                                             r.level_info.name))


# --- writing --------------------------------------------------------------------------------------

# Every tag the build writes (`PATHING-BUILD.md` §1.2–1.3) -- dropped from each rewritten body
# before the new ones go in. `NavigationPointList` is the LevelInfo's; a nav never carries it.
_PATH_TAGS = frozenset({"paths", "upstreampaths", "prunedpaths", "visnoreachpaths",
                        "nextnavigationpoint", "visitedweight", "bestpathweight", "cost",
                        "bendpoint", "previouspath", "nextordered", "prevordered",
                        "navigationpointlist"})


class _Names:
    """Name-table lookup by FName (case-insensitive) that appends what the table lacks."""

    def __init__(self, names: list[str]):
        self._by_cf = {n.casefold(): i for i, n in enumerate(names)}
        self._count = len(names)
        self.appended: list[str] = []

    def __call__(self, s: str) -> int:
        i = self._by_cf.get(s.casefold())
        if i is None:
            i = self._by_cf[s.casefold()] = self._count
            self._count += 1
            self.appended.append(s)
        return i


def _array_props(name: str, values, ptype: int, ref_of) -> list[Prop]:
    if len(values) > NODE_ARRAY_SLOTS:
        raise PathPassError(f"{name}: {len(values)} elements, the array has {NODE_ARRAY_SLOTS}")
    return [Prop(name, ptype, ref_of(v), array_index=i) for i, v in enumerate(values) if v != -1]


def _nav_props(node: NavOut, nav_refs: list[int]) -> list[Prop]:
    def ref(v: int) -> int:
        if not (0 <= v < len(nav_refs)):
            raise PathPassError(f"path graph names nav index {v}, the roster has {len(nav_refs)}")
        return nav_refs[v]
    props = (_array_props("upstreamPaths", node.upstream, AW.PT_INT, int)
             + _array_props("Paths", node.paths, AW.PT_INT, int)
             + _array_props("PrunedPaths", node.pruned_paths, AW.PT_INT, int)
             + _array_props("VisNoReachPaths", node.vis_no_reach, AW.PT_OBJECT, ref))
    if node.next_nav != -1:
        props.append(Prop("nextNavigationPoint", AW.PT_OBJECT, ref(node.next_nav)))
    res = node.residue
    if res is not None:
        for name, v in (("visitedWeight", res.visited_weight),
                        ("bestPathWeight", res.best_path_weight), ("cost", res.cost)):
            if v:
                props.append(Prop(name, AW.PT_INT, v))
        if res.b_end_point:
            props.append(Prop("bEndPoint", AW.PT_BOOL, True))
        for name, v in (("previousPath", res.previous_path), ("nextOrdered", res.next_ordered),
                        ("prevOrdered", res.prev_ordered)):
            if v != -1:
                props.append(Prop(name, AW.PT_OBJECT, ref(v)))
    return props


def _rewrite_actor(pkg: upackage.Package, actor: _Actor, props: list[Prop], rank: dict,
                   name_index) -> bytes:
    """The actor body with every path tag dropped and `props` written, the list re-sorted into
    the class's serialization order (static-array elements by index); the StateFrame, every
    untouched tag and the terminator are the original bytes."""
    buf, e = pkg.buf, pkg.exports[actor.export]
    items = [(rank.get(t.name.casefold(), len(rank)), t.array_index, buf[t.span[0]:t.span[1]])
             for t in actor.tags if t.name.casefold() not in _PATH_TAGS]
    items += [(rank.get(p.name.casefold(), len(rank)), p.array_index or 0,
               AW.write_prop(name_index, p)) for p in props]
    items.sort(key=lambda it: (it[0], it[1]))
    return (buf[e["soff"]:actor.props_start] + b"".join(b for _r, _i, b in items)
            + buf[actor.none_start:e["soff"] + e["ssize"]])


def _check_graph(graph: PathGraph, n_navs: int) -> None:
    if len(graph.nodes) != n_navs:
        raise PathPassError(f"path graph has {len(graph.nodes)} nodes for {n_navs} nav actors")
    for k, s in enumerate(graph.specs):
        if not (0 <= s.start < n_navs and 0 <= s.end < n_navs):
            raise PathPassError(f"ReachSpec {k}: Start/End nav index {s.start}/{s.end} out of range")


def apply_path_pass(package_bytes: bytes, *, pathing: str, index, defaults, rank_for) -> bytes:
    """Build the path graph into a built package (spec §3). `pathing` is the game's preset name
    (`none` returns the input unchanged); `index` a `classindex.ClassIndex` and `defaults` a
    `classdefaults.ClassDefaults` over the same packages; `rank_for` the serialization-order
    resolver (`unbuilt.serialization_rank_resolver`). Zero nav actors is a no-op. Raises
    `PathPassError` naming the offending actor/value; nothing is written on an error."""
    if pathing == "none":
        return package_bytes
    rules = _preset(pathing)
    r = _read_package(package_bytes, index=index, defaults=defaults,
                      skip_deleted=rules.skip_deleted)
    if not r.navs:
        return package_bytes
    if r.model is None or not r.model.nodes:
        raise PathPassError(f"the world Model has no BSP nodes but the level has {len(r.navs)} "
                            f"NavigationPoint actor(s) -- build the world before the path pass")
    me = r.pkg.exports[r.level.model_ref - 1]
    model_body = r.pkg.buf[me["soff"]:me["soff"] + me["ssize"]]
    graph = graph_from_native(graph_builder(
        model_body, [m.as_tuple() for m in r.movers], [n.as_tuple() for n in r.nav_in],
        [z.as_tuple() for z in r.zones], r.level_zone.as_tuple(), rules.as_args()))
    return splice_graph(r, graph, rank_for)


def splice_graph(r: _Read, graph: PathGraph, rank_for) -> bytes:
    """Write `graph` into the read package: the ReachSpecs run, every nav actor's path tags, the
    LevelInfo's `NavigationPointList`; re-laid with header, GUID, generations and tables kept."""
    _check_graph(graph, len(r.navs))
    pkg = r.pkg
    nav_refs = [a.export + 1 for a in r.navs]
    names = _Names(pkg.names)
    bodies: dict[int, bytes] = {}
    for a, node in zip(r.navs, graph.nodes):
        bodies[a.export] = _rewrite_actor(pkg, a, _nav_props(node, nav_refs), rank_for(a.fqcn),
                                          names)
    li = r.level_info
    head = [] if graph.nav_list_head == -1 else \
        [Prop("NavigationPointList", AW.PT_OBJECT, nav_refs[graph.nav_list_head])]
    bodies[li.export] = _rewrite_actor(pkg, li, head, rank_for(li.fqcn), names)
    specs = [ReachSpec(distance=s.distance, start=nav_refs[s.start], end=nav_refs[s.end],
                       radius=s.radius, height=s.height, reach_flags=s.flags, pruned=s.pruned)
             for s in graph.specs]
    le = pkg.exports[r.level.export]
    lb = pkg.buf[le["soff"]:le["soff"] + le["ssize"]]
    s0, s1 = (o - le["soff"] for o in r.level.specs_span)
    bodies[r.level.export] = lb[:s0] + write_reach_specs(specs) + lb[s1:]
    return relayout_package(pkg, bodies=bodies, new_names=names.appended)
