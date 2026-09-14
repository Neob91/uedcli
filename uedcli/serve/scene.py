"""Trunk → scene payload for `uedcli serve` (plan Task 2). Polygons/lightmaps reuse
`preview_native.build_scene` (the LIT path — `level photo --native`'s own backend) +
`preview_cache`; the actor metadata (bbox/pose/folder/labels/`order_value`) is assembled fresh from
`trunk.read_level_with_bodies`, since neither `preview_cache` tier holds it."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .. import config, trunk
from ..preview_native import build_scene
from ..rotation import actor_rotation_uu
from ..writes import actor_bounds

_ZERO3 = (Decimal(0), Decimal(0), Decimal(0))


@dataclass(frozen=True, kw_only=True)
class ScenePoly:
    """One render-ready polygon, mirroring `build_scene`'s own per-poly tuple field-for-field (see
    its module docstring): world verts (flat x,y,z triples), the base-UV frame, the texture-table
    index, the alpha-test gate, the raw merged `PolyFlags`, and the baked lightmap patch (carried,
    unused by Slice 1's unlit draw — Slice 2 turns it into the lit shading mode). Its RGB buffer
    (`build_scene`'s `bake_radiance` binding) is a plain `list[float]`, not `bytes` — already
    JSON-safe as-is, verified against the real HTTP route with a real light-bearing fixture
    (`test_scene_route_returns_200_with_a_json_safe_payload`)."""
    verts: list[float]
    base: list[float]
    tu: list[float]
    tv: list[float]
    pan: list[float]
    tex_index: int
    masked: bool
    flags: int
    lightmap: tuple | None


@dataclass(frozen=True, kw_only=True)
class SceneActor:
    """One actor's metadata for the inspector/organization panel — NOT its geometry (a brush
    actor's polys already ride in `ScenePayload.polys`, joined by CSG, not by actor). `props` is
    the actor's raw stored T3D property list (`Actor.props`, `list[(key, raw-text-value)]`) — the
    read-only inspector's "full raw T3D property set" (spec, "Selection & inspector")."""
    name: str
    cls: str
    bbox_lo: tuple[float, float, float]
    bbox_hi: tuple[float, float, float]
    location: tuple[float, float, float]
    rotation: tuple[int, int, int]
    folder: str | None
    labels: list[str]
    order_value: str
    props: list[tuple[str, str]]


@dataclass(frozen=True, kw_only=True)
class ScenePayload:
    polys: list[ScenePoly]
    actors: list[SceneActor]


def build_scene_payload(project, level_name: str, index, defaults, search_files) -> ScenePayload:
    """Load the trunk once (a lock-free read, read-only-safe) and build its scene: the solved,
    lit-but-undrawn polygons from `build_scene` (a `preview_cache` hit reuses the ~24s CSG solve
    and/or the fully-lit scene, keyed on `project`/`level_name`), plus every actor's inspector
    metadata joined fresh from the same load. `index`/`defaults`/`search_files` are the caller's
    already-assembled `build_scene` inputs (the same trio `level photo --native`'s `render_shots`
    call site assembles, `cli/commands/level.py` ~732-745) — this function does no resolution of
    its own, so a test can hand it a `StubClassIndex` and an offline `ClassDefaults` directly."""
    maps_dir = Path(config.project_maps_dir(project))
    level, ranks, _bodies, _folders = trunk.read_level_with_bodies(maps_dir / level_name)
    polys, _texture_table = build_scene(level, search_files, index, defaults=defaults,
                                        project=project, level_name=level_name)
    scene_polys = [
        ScenePoly(verts=verts, base=list(base), tu=list(tu), tv=list(tv), pan=list(pan),
                 tex_index=tex_index, masked=masked, flags=flags, lightmap=lightmap)
        for verts, base, tu, tv, pan, tex_index, masked, flags, lightmap in polys
    ]
    actors = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None:
            continue
        lo, hi = actor_bounds(actor)
        loc = actor.location or _ZERO3
        actors.append(SceneActor(
            name=name, cls=actor.cls or "",
            bbox_lo=tuple(float(c) for c in lo), bbox_hi=tuple(float(c) for c in hi),
            location=tuple(float(c) for c in loc), rotation=actor_rotation_uu(actor),
            folder=actor.folder, labels=sorted(actor.labels), order_value=ranks.get(name, ""),
            props=list(actor.props)))
    return ScenePayload(polys=scene_polys, actors=actors)
