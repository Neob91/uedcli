"""Parse UnrealEd T3D text into a level model keyed by actor Name.

Line-oriented: `Begin/End` blocks nest (Map > Actor > Brush > PolyList >
Polygon). Property lines inside an Actor (outside its Brush) are kept verbatim
as ordered (key, value) pairs; Location is parsed out for geometry use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

# `labellib` is model-free (it imports only `folderlib`), so this top-level import cannot cycle;
# parse_t3d reads the `// uedctl-labels:` carrier via `labellib._LABELS_CARRIER`.
from . import labellib

# All coordinates (Vertex/Location AND poly Origin/Normal/TextureU/V) are stored as exact Decimal
# so authored values round-trip with no binary drift. Across a materialize round-trip the editor
# PRESERVES Origin/TextureU/V (stored FVectors, float32) but RECOMPUTES the poly Normal from vertex
# winding — so the COMPARE path (normalize.compare_view -> _geometry_text, never the
# identity hash) float32-quantizes coords and drops only Normal; see unrealed/t3d.md "Winding
# defines the face, not Normal".
Vec3 = tuple[Decimal, Decimal, Decimal]

_VEC_LINE = re.compile(
    r"^\s*(Origin|Normal|TextureU|TextureV|Vertex)\s+"
    r"([-+]?\d+\.\d+),([-+]?\d+\.\d+),([-+]?\d+\.\d+)\s*$"
)
# Each axis is matched independently: UnrealEd OMITS zero components on export
# (e.g. `Location=(X=2000.000000,Y=2000.000000)` when Z==0), so a fixed X,Y,Z
# regex would miss such lines entirely. Absent components default to 0.0.
_LOC_AXIS = re.compile(r"\b([XYZ])=([-+]?\d+\.?\d*)")
_POLY_HDR = re.compile(r"Begin Polygon(.*)$")
_KV = re.compile(r"(\w+)=(\S+)")
# Capture an optional `(N)` index after the key name so STATIC-ARRAY props (KeyPos(1)=...,
# MultiSkins(2)=...) parse instead of being silently dropped. Location/Name special-casing keys
# off the BARE name, so an indexed token never collides with them.
_PROP = re.compile(r"^\s*([A-Za-z_]\w*(?:\(\d+\))?)=(.*)$")
# The `actor show` folder interchange carrier: a bare `// uedctl-folder: <path>` line inside an
# actor block. `actor show` emits it from the folder sidecar; the T3D importer silently strips ALL
# bare `//` lines (spike 2026-07-18-t3d-comment-tolerance), so the same text pastes cleanly into
# UnrealEd. This parse reads it back into `actor.folder` (whence `actor add` writes the sidecar). A
# stored trunk body NEVER contains this line — the folder is the sidecar; only show output carries
# it. Non-carrier `//` lines are ignored as ordinary comments (they don't match this).
_FOLDER_CARRIER = re.compile(r"^\s*//\s*uedctl-folder:\s*(\S+)\s*$")


@dataclass
class Polygon:
    flags: int = 0
    texture: str | None = None
    item: str | None = None
    pan: tuple[int, int] | None = None
    origin: Vec3 | None = None
    normal: Vec3 | None = None
    texture_u: Vec3 | None = None
    texture_v: Vec3 | None = None
    vertices: list[Vec3] = field(default_factory=list)


@dataclass
class Brush:
    model_name: str
    polys: list[Polygon] = field(default_factory=list)


@dataclass
class Actor:
    name: str
    cls: str
    props: list[tuple[str, str]] = field(default_factory=list)
    location: Vec3 | None = None
    brush: Brush | None = None
    # Typed scale fields, parsed OUT of `props` (like `location`) so model-side geometry can USE
    # them and `emit_actor` re-emits SOLELY from here (a stale props copy would double-emit — spec
    # §10). Each is a `transform.FScale` (Scale FVector + SheerRate + SheerAxis) or None when the
    # actor has no such prop (a point actor). See dev/docs/architecture.md "Scale".
    main_scale: "object | None" = None                # transform.FScale | None (LOCAL, pre-rotation)
    post_scale: "object | None" = None                # transform.FScale | None (WORLD, post-rotation)
    # A uedctl-side hierarchical dotted organization path (e.g. "castle.tower.roof"), stored in a
    # per-actor `folder` SIDECAR in the trunk — NEVER in the T3D body, NEVER emitted to the built
    # map, INDEPENDENT of the T3D `Group=` prop. `None` = ungrouped. `emit`/`canonical_actor_t3d`
    # never serialize it (so it stays out of the body, the map, and the level hash); trunk read/write
    # own the sidecar. Its only on-the-wire form is the `// uedctl-folder:` carrier `actor show`
    # emits and `actor add` parses back (see `_FOLDER_CARRIER` below). See dev/docs/architecture.md
    # "Folders" + specs/2026-07-18-actor-folders-hierarchical.md.
    folder: str | None = None
    # A uedctl-side FLAT set of cross-cutting classification labels (e.g. "lighting", "flammable",
    # "dup-a1f"), stored in a per-actor `labels` SIDECAR in the trunk — NEVER in the T3D body, NEVER
    # emitted to the built map, ORTHOGONAL to `folder`, the T3D `Group=` prop, and the engine `Tag`
    # prop. The sorted-set analog of `folder`: `emit`/`canonical_actor_t3d` never serialize it (so it
    # stays out of the body, the map, and the level hash); trunk read/write own the sidecar. Its only
    # on-the-wire form is the `// uedctl-labels:` carrier `actor show` emits and `actor add` parses
    # back (labellib._LABELS_CARRIER). See dev/docs/architecture.md + specs/2026-07-22-actor-labels.md.
    labels: frozenset[str] = frozenset()
    # The `Location=` value EXACTLY as it was parsed, or None when the actor had no Location line.
    # A CONTAINED SIDE-CHANNEL for one fact `location` cannot carry: WHICH AXES THE SOURCE STATED.
    # UnrealEd omits an axis equal to the class default member, so `Location=(X=100,Y=200)` on an
    # `Engine.Camera` (default `(X=-500,Y=-300,Z=300)`) means Z=300, NOT Z=0 — but `location` is
    # consumed by all the geometry math (bounds, preview, transforms, CSG), which needs three real
    # numbers, so the axes stay 0-filled there and the omission is recorded here instead.
    #
    # It is SELF-INVALIDATING, and consumers MUST honour that: the text is only meaningful while
    # `rotation.parse_fvector(location_text) == location`. Any mutation (`actor move`, `rotate`,
    # `scale`, mover re-basing) writes `location` alone, the two stop agreeing, and the reader
    # falls back to "every axis is stated" — which is exactly right, because every uedctl write
    # path emits all three axes (`emit.emit_actor`). So no mutation site has to remember to clear
    # it. Read it through `normalize._stated_axes`, never directly. NEVER emitted (see
    # `emit_actor`), never hashed, never written to the trunk.
    location_text: str | None = None


@dataclass
class Level:
    actors: dict[str, Actor] = field(default_factory=dict)
    # Full actor export order; the brush subsequence is CSG precedence. Captured
    # pre-normalize (normalize_level re-sorts actors by Name), so set it from level_order.
    order: list[str] = field(default_factory=list)


def _vec(m: re.Match, base: int) -> tuple[float, float, float]:
    return (float(m.group(base)), float(m.group(base + 1)), float(m.group(base + 2)))


def _vec_decimal(m: re.Match, base: int) -> Vec3:
    # Build from the matched STRINGS so the float repr never enters the Decimal.
    return (Decimal(m.group(base)), Decimal(m.group(base + 1)), Decimal(m.group(base + 2)))


def parse_t3d_actors(text: str) -> list[Actor]:
    """Every actor in `text` as an ordered list, PRESERVING duplicate Names.

    `parse_t3d` keys actors by Name in a dict, so on a Name collision it silently keeps only the
    last — fine for a stored level (Names are unique there), WRONG for user-concatenated T3D where
    several `brush build`/`actor build` snippets may share a Name. Any caller ingesting raw user
    T3D MUST parse via this and uniquify before dict-keying, or all-but-the-last of each duplicate
    group is dropped without warning (see dev/docs/board/inbox.md dogfooding CRITICAL)."""
    actors: list[Actor] = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("Begin Actor"):
            actor, i = _parse_actor(lines, i)
            actors.append(actor)
        else:
            i += 1
    return actors


def parse_t3d(text: str) -> Level:
    """A `Level` keyed by actor Name (last-write-wins on a collision). For raw user T3D that may
    carry duplicate Names, use `parse_t3d_actors` and uniquify — see its docstring."""
    level = Level()
    for actor in parse_t3d_actors(text):
        level.actors[actor.name] = actor
    return level


def _parse_actor(lines: list[str], i: int) -> tuple[Actor, int]:
    hdr = lines[i]
    kv = dict(_KV.findall(hdr))
    actor = Actor(name=kv.get("Name", ""), cls=kv.get("Class", ""))
    i += 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "End Actor":
            i += 1
            break
        if s.startswith("Begin Brush"):
            actor.brush, i = _parse_brush(lines, i)
            continue
        fc = _FOLDER_CARRIER.match(lines[i])
        if fc:
            actor.folder = fc.group(1)     # interchange carrier → sidecar field (see _FOLDER_CARRIER)
            i += 1
            continue
        lc = labellib._LABELS_CARRIER.match(lines[i])
        if lc:
            actor.labels = frozenset(labellib.parse_labels_carrier(lc))  # carrier → labels sidecar
            i += 1
            continue
        m = _PROP.match(lines[i])
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "Location":
                # Location is owned by the typed `actor.location` field, NOT mirrored into
                # `props` — emit_actor re-emits it from the field. Keeping a props copy too
                # would let the two drift (the field is what move/rotate/bounds mutate).
                # An OMITTED axis means the CLASS DEFAULT member, not zero (the editor omits an
                # axis equal to it). Resolving that needs a schema, which this parser deliberately
                # does not have — it is also the trunk/stash/prefab/generator-snippet reader — so
                # the numeric triple stays 0-filled for the geometry consumers and the verbatim
                # text is kept in `location_text` for the schema-aware compare seam to expand
                # member-wise (see `Actor.location_text` and `normalize.compare_view`).
                axes = {ax: Decimal(v) for ax, v in _LOC_AXIS.findall(val)}
                if axes:
                    z = Decimal(0)
                    actor.location = (axes.get("X", z), axes.get("Y", z), axes.get("Z", z))
                    actor.location_text = val
            elif key == "Name":
                actor.name = val.strip('"')
            elif key in ("MainScale", "PostScale"):
                # MainScale/PostScale are owned by the typed `actor.main_scale`/`post_scale` fields
                # (like Location) — NOT mirrored into `props`, so emit_actor re-emits from the field
                # and a stale props copy can't double-emit (spec §10). The value is a nested
                # `(Scale=(X=,Y=,Z=),SheerRate=,SheerAxis=)` FScale struct.
                from .transform import parse_fscale
                fs = parse_fscale(val)
                if key == "MainScale":
                    actor.main_scale = fs
                else:
                    actor.post_scale = fs
            else:
                actor.props.append((key, val.strip('"')))
        i += 1
    return actor, i


def _parse_brush(lines: list[str], i: int) -> tuple[Brush, int]:
    kv = dict(_KV.findall(lines[i]))
    brush = Brush(model_name=kv.get("Name", ""))
    i += 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "End Brush":
            i += 1
            break
        if s.startswith("Begin Polygon"):
            poly, i = _parse_polygon(lines, i)
            brush.polys.append(poly)
            continue
        i += 1
    return brush, i


def _parse_polygon(lines: list[str], i: int) -> tuple[Polygon, int]:
    poly = Polygon()
    hdr = _POLY_HDR.search(lines[i]).group(1)
    attrs = dict(_KV.findall(hdr))
    if "Flags" in attrs:
        poly.flags = int(attrs["Flags"])
    poly.item = attrs.get("Item")
    poly.texture = attrs.get("Texture")
    i += 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "End Polygon":
            i += 1
            break
        if s.startswith("Pan"):
            pm = dict(_KV.findall(s))
            poly.pan = (int(pm.get("U", 0)), int(pm.get("V", 0)))
            i += 1
            continue
        m = _VEC_LINE.match(lines[i])
        if m:
            kind, v = m.group(1), _vec(m, 2)
            if kind == "Origin":
                poly.origin = v
            elif kind == "Normal":
                poly.normal = v
            elif kind == "TextureU":
                poly.texture_u = v
            elif kind == "TextureV":
                poly.texture_v = v
            elif kind == "Vertex":
                poly.vertices.append(_vec_decimal(m, 2))
        i += 1
    return poly, i
