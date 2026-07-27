"""Native, editor-less decode of a compiled UE1 map file (`.dx`/`.unr`) into `MAP EXPORT` T3D text.

This is the inverse of `level materialize`. Materialize turns the git-tracked T3D trunk into a
compiled map file by driving UnrealEd; this module turns a compiled map file back into the same T3D
text the editor's own `MAP EXPORT` would write — with **no editor and no UCC in the path**, just the
package bytes. `dispatch`'s `level import` verb then feeds that text to `model.parse_t3d` and writes
the resulting level into a new trunk or stash.

**What "a compiled map file" holds, for a reader who has not seen one.** A `.dx`/`.unr` is an
ordinary UE1 package (`upackage.py` parses the container): a name table, an import table, an export
table, and one serialized *body* per export. One export is the `Engine.Level` object; it owns an
`Actors` array naming every actor export, in the order that IS the level's actor order. Each actor
export's body is an optional `StateFrame` (the UnrealScript execution state) followed by a
`None`-terminated list of *tagged properties* — only those whose value differs from the actor's
class default. A brush actor additionally points at a private `UModel` object whose `Polys` object
is a `UPolys` array of `FPoly` records: the authored polygons.

**The three things this module does that nothing else in uedcli did before:**

1. **Skip the `StateFrame`** to find where an actor's property list starts (`_skip_state_frame`).
2. **Render each property exactly as `MAP EXPORT` would** (`render_prop`). Two rules make the text
   match the editor's: every float is written at six decimals, and a struct's members are compared
   member-by-member against the class default's members with the equal ones DROPPED — which is why
   the editor writes `Rotation=(Yaw=8192)` and not `(Pitch=0,Yaw=8192,Roll=0)`. The comparison is
   against the real class default, which is not always zero (`Scale=(X=1,Y=1,Z=1)`), so a member
   equal to a NON-zero default is dropped too.
3. **Decode a brush's `UPolys`** into the `Begin Brush / Begin PolyList / Begin Polygon` block
   (`decode_upolys`), including each polygon's `Item` label and `Texture` reference.

Everything else is reuse: `upackage` parses the container and the tagged-property list, `uprops`
decodes each property VALUE (including arbitrary schema-driven structs), `classindex` answers "is
this class an actor?", `emit` renders the geometry text, and `model.parse_t3d` ingests the result.

Every failure is a `upackage.SchemaError` naming what could not be decoded — never a bare
`struct.error`/`IndexError` traceback out of a binary parser (`CLAUDE.md`, "Never let a Python
exception reach the CLI user"). There is no partial result: a map that cannot be fully decoded
raises, because a trunk that looks complete but silently dropped an actor is the worst possible
outcome of this verb.

Spec: board item `level-import-native-editor-less-dx-unr-t3d`. Format evidence: the Actors-array layout is
`dev/docs/spikes/2026-07-24-level-import-order/findings.md`; the StateFrame and the `UPolys`/`FPoly`
bodies are `dev/docs/spikes/2026-06-27-decontainerize-uedcli/07-native-actor-bodies.md` (+ its
`harness/upolys_decode.py`), and both are mirrored by uedcli's own writers in `native/`.
"""
from __future__ import annotations

import functools
import struct
from decimal import Decimal

from . import emit, model, uprops
from .classindex import ENGINE_ACTOR
from .native.actor_write import FPoly
from .native.umodel import parse_model_body
from .upackage import (
    PT_ARRAY,
    PT_NAME,
    PT_OBJECT,
    PT_STR,
    PT_STR_LEGACY,
    PT_STRUCT,
    Package,
    PropertyTag,
    SchemaError,
    read_compact_index,
    read_property_tags,
)

# An export whose object flags carry this bit serializes a `StateFrame` before its property list.
# (`native/actor_write.py` sets the same constant on the write side.)
RF_HasStack = 0x02000000

# The class of the object that owns the authoritative actor ORDER.
ENGINE_LEVEL = "Engine.Level"

# A hard ceiling on any length read out of the file before it is trusted enough to loop on. A real
# retail level holds ~2200 actors and a brush ~500 polygons; a corrupt/hostile package can encode a
# 2-billion count in four bytes and would otherwise spin for minutes allocating. The bound is far
# above anything real and exists only so the failure is an immediate named error.
_MAX_ELEMENTS = 1 << 22


def _decode_guard(fn):
    """Turn ANY escape from the binary decoders into a named `SchemaError`.

    Everything below parses UNTRUSTED bytes: a truncated body, a garbage compact index, or a
    name/export index pointing off the end of its table surfaces from `struct`/list indexing as a
    `struct.error`/`IndexError`, which `CLAUDE.md` forbids reaching the user. This mirrors
    `uprops._schema_guard` (same contract, same reason); a real `SchemaError` passes through with
    its own, better message.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SchemaError:
            raise
        except RecursionError:
            raise SchemaError(f"{fn.__name__}: runaway recursion decoding a corrupt "
                              "map body") from None
        except (IndexError, ValueError, OverflowError, KeyError) as e:
            raise SchemaError(f"{fn.__name__}: corrupt map body "
                              f"({type(e).__name__}: {e})") from e
        except struct.error as e:
            raise SchemaError(f"{fn.__name__}: truncated map body ({e})") from e
    return wrapper


def _check_count(n: int, what: str) -> int:
    if not (0 <= n <= _MAX_ELEMENTS):
        raise SchemaError(f"implausible {what} count {n} — the map is corrupt or misparsed")
    return n


# ── the StateFrame ───────────────────────────────────────────────────────────────────────────

@_decode_guard
def _skip_state_frame(pkg: Package, export: dict) -> int:
    """The offset at which `export`'s tagged-property list starts.

    An `AActor` carries an UnrealScript execution state (`FStateFrame`) serialized ahead of its
    properties, and only when the export's flags carry `RF_HasStack`. Its layout — the exact
    inverse of `native.actor_write.state_frame`, and of the reader validated over all 3736 objects
    of `00_Intro.dx` in Spike 07 (`07-native-actor-bodies.md`) — is:

        Node:          compact object ref
        StateNode:     compact object ref
        ProbeMask:     u64
        LatentAction:  u32
        Offset:        compact int — PRESENT ONLY IF Node != 0

    A non-`RF_HasStack` export (a `Model`, a `Polys`, the `Level` itself) has no StateFrame, so its
    body starts at the property list directly.
    """
    soff, ssize = export["soff"], export["ssize"]
    if not (export["flags"] & RF_HasStack):
        return soff
    end = soff + ssize
    buf = pkg.buf
    node, p = read_compact_index(buf, soff)
    _state_node, p = read_compact_index(buf, p)
    p += 8 + 4                                        # ProbeMask (u64) + LatentAction (u32)
    if node != 0:
        _offset, p = read_compact_index(buf, p)
    if p > end:
        raise SchemaError(f"StateFrame of export at {soff} overruns its serial body "
                          f"({p} > {end}) — truncated or misparsed")
    return p


# ── brush geometry: UPolys / FPoly ───────────────────────────────────────────────────────────

@_decode_guard
def decode_fpoly(buf: bytes, pos: int) -> tuple[FPoly, int]:
    """One `FPoly` record → `(FPoly, cursor_after)`.

    The record layout is the exact inverse of `native.actor_write.write_fpoly`, itself taken from
    `operator<<(FArchive&, FPoly&)` and EOF-validated over 6566 of 6587 real `UPolys` exports
    (spike `2026-06-27-decontainerize-uedcli/harness/upolys_decode.py`):

        NumVertices: compact   Base/Normal/TextureU/TextureV: 3×f32 each   Vertices: NumVertices×3×f32
        PolyFlags: i32   Actor/Texture/ItemName/iLink/iBrushPoly: compact   PanU/PanV: u16 each
    """
    nv, pos = read_compact_index(buf, pos)
    _check_count(nv, "polygon vertex")

    def f3(p: int) -> tuple[tuple[float, float, float], int]:
        return struct.unpack_from("<3f", buf, p), p + 12

    base, pos = f3(pos)
    normal, pos = f3(pos)
    tu, pos = f3(pos)
    tv, pos = f3(pos)
    verts = []
    for _ in range(nv):
        v, pos = f3(pos)
        verts.append(v)
    flags = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    actor_ref, pos = read_compact_index(buf, pos)
    texture_ref, pos = read_compact_index(buf, pos)
    item_index, pos = read_compact_index(buf, pos)
    i_link, pos = read_compact_index(buf, pos)
    i_brush_poly, pos = read_compact_index(buf, pos)
    pan_u = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    pan_v = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    return FPoly(verts=verts, base=base, normal=normal, texture_u=tu, texture_v=tv,
                 poly_flags=flags, actor_ref=actor_ref, texture_ref=texture_ref,
                 item_index=item_index, i_link=i_link, i_brush_poly=i_brush_poly,
                 pan_u=pan_u, pan_v=pan_v), pos


@_decode_guard
def decode_upolys(pkg: Package, export_index0: int) -> list[FPoly]:
    """Every `FPoly` of the `UPolys` export at 0-based index `export_index0`.

    The body is `[property-list None terminator][i32 Num][i32 Max][Num × FPoly]` — the inverse of
    `native.actor_write.write_upolys_body`. Reaching exactly the body's end is the integrity check:
    a short or long cursor means the record layout was misread, and a half-decoded polygon list
    would be a silently wrong brush.

    The body is entered through `_skip_state_frame`, not at the raw `soff`: `RF_HasStack` is a
    per-EXPORT flag, and a small number of retail `Polys` exports carry it even though a polygon
    list is plain data and runs no UnrealScript (`unrealed/package-format.md` "`RF_HasStack` is a
    per-EXPORT flag"). Entering at `soff` on one of those desyncs by the StateFrame's length.
    """
    if not (0 <= export_index0 < len(pkg.exports)):
        raise SchemaError(f"Polys export index {export_index0} out of range in {pkg.name}")
    e = pkg.exports[export_index0]
    buf, end = pkg.buf, e["soff"] + e["ssize"]
    _none, pos = read_compact_index(buf, _skip_state_frame(pkg, e))
    num, _max = struct.unpack_from("<ii", buf, pos); pos += 8
    _check_count(num, "brush polygon")
    polys: list[FPoly] = []
    for _ in range(num):
        fp, pos = decode_fpoly(buf, pos)
        polys.append(fp)
    if pos != end:
        raise SchemaError(f"UPolys body of {pkg.names[e['nm']]} did not consume exactly "
                          f"(cursor {pos} != body end {end})")
    return polys


def _dec3(v) -> tuple[Decimal, Decimal, Decimal]:
    """A decoded f32 triple as the exact `Decimal`s the model stores geometry in. `repr(float)` is
    the shortest text that round-trips the float32-widened double, which is what `emit` then
    renders at six decimals."""
    return tuple(Decimal(repr(c)) for c in v)


@_decode_guard
def polygon_of(pkg: Package, fp: FPoly) -> model.Polygon:
    """One decoded `FPoly` → the `model.Polygon` the T3D emitter writes.

    Two of its fields are object/name references into the map's own tables:

    * `Texture` — the polygon's surface texture, an object reference rendered as the dotted path
      `Package.Group.Name` (the bare form `Begin Polygon Texture=…` takes — `unrealed/t3d.md`
      "Property line forms"). A 0 reference means the face is untextured and no `Texture=` is
      written.
    * `Item` — a per-face label (`Base`, `Step`, `OUTSIDE`, …) held as an `FName`, i.e. an index
      into the package's name table. "No label" is the index of the name `None`, wherever that
      happens to sit in this package's table — it is **not** index 0. Index 0 is an ordinary name,
      and in every Deus Ex map sampled it is the heavily-used `OUTSIDE`, so testing `idx == 0` for
      "unset" silently deletes every `Item=OUTSIDE` from the decoded map
      (`unrealed/package-format.md` "`FPoly.ItemName` — name index 0 is a REAL name").
    """
    if not (0 <= fp.item_index < len(pkg.names)):
        raise SchemaError(f"polygon Item name index {fp.item_index} out of range in {pkg.name}")
    name = pkg.names[fp.item_index]
    item = None if name == "None" else name
    texture = None
    if fp.texture_ref != 0:
        texture = pkg.object_path(fp.texture_ref)
        if texture is None:
            raise SchemaError(f"polygon Texture ref {fp.texture_ref} does not resolve "
                              f"in {pkg.name}")
    return model.Polygon(
        flags=fp.poly_flags, texture=texture, item=item,
        pan=(fp.pan_u, fp.pan_v),
        origin=_dec3(fp.base), normal=_dec3(fp.normal),
        texture_u=_dec3(fp.texture_u), texture_v=_dec3(fp.texture_v),
        vertices=[_dec3(v) for v in fp.verts])


@_decode_guard
def brush_of(pkg: Package, brush_ref: int) -> model.Brush:
    """The authored geometry behind an actor's `Brush=Model'…'` reference.

    The chain is `Brush` → a PRIVATE `UModel` object → that model's `Polys` reference → a `UPolys`
    array of `FPoly`. The model body is parsed by the same `native.umodel.parse_model_body` the
    world BSP uses (it reaches EOF on a private brush model too), and `Polys` is the field the
    writer calls `field_0x54`.

    A brush whose model holds NO polygons yields an empty `PolyList` rather than an error: that is
    a real, if unusual, state — maps built by uedcli's own native builder keep the shape in the
    world BSP and leave the private model empty (spec §8).
    """
    if brush_ref <= 0:
        raise SchemaError(f"brush Model ref {brush_ref} is not an object in this map "
                          f"({pkg.name}) — a brush's model is always a local export")
    if brush_ref > len(pkg.exports):
        raise SchemaError(f"brush Model ref {brush_ref} out of range in {pkg.name}")
    me = pkg.exports[brush_ref - 1]
    model_name = pkg.names[me["nm"]]
    if me["ssize"] <= 0:
        raise SchemaError(f"brush Model {model_name} has an empty serial body")
    # Enter the body past any StateFrame, for the same per-EXPORT-flag reason `decode_upolys`
    # does: 21 of the `Model` exports across the first twelve retail maps carry `RF_HasStack`,
    # and `parse_model_body` desyncs on every one of them if entered at the raw `soff`.
    mstart = _skip_state_frame(pkg, me)
    m = parse_model_body(pkg.buf, mstart, me["soff"] + me["ssize"] - mstart)
    polys: list[model.Polygon] = []
    if m.field_0x54 != 0:
        if not (0 < m.field_0x54 <= len(pkg.exports)):
            raise SchemaError(f"brush Model {model_name} Polys ref {m.field_0x54} out of range")
        polys = [polygon_of(pkg, fp) for fp in decode_upolys(pkg, m.field_0x54 - 1)]
    return model.Brush(model_name=model_name, polys=polys)


# ── the per-class schema + class defaults ────────────────────────────────────────────────────

class ImportSchema:
    """Per-class property schema and class DEFAULTS, resolved once per class and cached.

    Both halves come out of the game's own compiled `.u` packages (never a stub — `uprops` is the
    source of truth), reached through `resolver(package_name) -> path | None`, which is exactly the
    resolver a `classindex.ClassIndex` hands out.

    * `props(fqcn)` — `casefold(property name) -> uprops.Prop`, the class's full inherited property
      set. It supplies each property's declared TYPE, which the value decode needs (a struct's
      member layout, a byte's enum, a dynamic array's element kind).
    * `default_tag(fqcn, name, index)` — the RAW default value the class declares for a property,
      or None when it declares none (in which case the default is the type's zero). Raw, not
      rendered, because the struct member-strip has to compare member by member.
    """

    def __init__(self, *, resolver):
        self.resolver = resolver
        self.packages: dict = {}                 # shared package cache across every uprops call
        self._props: dict[str, dict[str, uprops.Prop]] = {}
        self._defaults: dict[str, dict[tuple[str, int], tuple[Package, PropertyTag]]] = {}

    def props(self, fqcn: str) -> dict[str, uprops.Prop]:
        key = fqcn.casefold()
        if key not in self._props:
            self._props[key] = {p.name.casefold(): p
                                for p in uprops.resolve_class_properties(
                                    fqcn, resolver=self.resolver)}
        return self._props[key]

    def _default_tags(self, fqcn: str) -> dict[tuple[str, int], tuple[Package, PropertyTag]]:
        key = fqcn.casefold()
        if key not in self._defaults:
            self._defaults[key] = uprops.resolve_class_default_tags(
                fqcn, resolver=self.resolver, _pkgs=self.packages)
        return self._defaults[key]

    def default_tag(self, fqcn: str, name: str,
                    array_index: int) -> tuple[Package, PropertyTag] | None:
        return self._default_tags(fqcn).get((name.casefold(), array_index))


# ── per-property rendering, UCC-exact ────────────────────────────────────────────────────────

@_decode_guard
def _default_struct_tree(pkg: Package, prop: uprops.Prop, fqcn: str, array_index: int, *,
                         schema: ImportSchema) -> dict:
    """The class default of struct property `prop`, as a nested member tree to compare against.

    When the class chain declares a default for the property, that default's own bytes are decoded
    (in the package they were serialized in — its object/name references index THAT package's
    tables). When it declares none, every member takes its type's zero
    (`uprops.zero_struct_tree`). Both are built in `T3D_STYLE`, the same style the value side uses,
    so the two compare directly.
    """
    entry = schema.default_tag(fqcn, prop.name, array_index)
    if entry is not None:
        dpkg, dtag = entry
        if dtag.ptype == PT_STRUCT:
            return uprops.struct_tag_member_tree(dpkg, dtag, prop, resolver=schema.resolver,
                                                 _pkgs=schema.packages,
                                                 style=uprops.T3D_STYLE)
    return uprops.zero_struct_tree(pkg, prop, resolver=schema.resolver,
                                   _pkgs=schema.packages, style=uprops.T3D_STYLE)


@_decode_guard
def render_prop(pkg: Package, tag: PropertyTag, fqcn: str, *,
                schema: ImportSchema) -> list[tuple[str, str]]:
    """One decoded property tag → the `(key, value)` T3D lines `MAP EXPORT` would write for it.

    Usually exactly one pair. A property is a list because a DYNAMIC array becomes one indexed line
    per element (`Foo(0)=…`, `Foo(1)=…`), and an empty array becomes no lines at all.

    `fqcn` is the actor's fully-qualified class name — the class whose schema types the property and
    whose defaults the struct member-strip compares against. Both compare sides (this decode and the
    UCC oracle it is checked against) use the same requalified FQCN, so they resolve the same
    defaults.

    The value forms follow `uprops.render_default_tag` (an actor-body tag and a class-defaults tag
    have the identical wire form), with the two `T3D_STYLE` differences that make the text the
    editor's: six-decimal floats, and enum-named byte struct members. On top of that, a STRUCT drops
    every member equal to the class default's corresponding member — the editor's own rule, and the
    reason it writes `Rotation=(Yaw=8192)` rather than all three components. That drop is
    **recursive**: a struct member that is itself a struct keeps only ITS differing members, so a
    mirrored brush comes out as `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)` — which is what
    the editor writes (real export: `uedcli/tests/fixtures/level_small.t3d`). Hence the member TREE
    rather than flat pairs: a pre-joined nested value could only be kept or dropped whole.
    """
    props = schema.props(fqcn)
    prop = props.get(tag.name.casefold())
    # A static array element is written with its index; a scalar never is. `array_dim` is the only
    # way to tell element 0 of a static array from a scalar, so an unknown property falls back to
    # "index it only if it is not element 0" — which is what the wire itself says.
    indexed = tag.array_index > 0 or (prop is not None and prop.array_dim > 1
                                      and prop.kind != "ArrayProperty")
    key = f"{tag.name}({tag.array_index})" if indexed else tag.name

    if tag.ptype == PT_ARRAY:
        if prop is None:
            raise SchemaError(f"dynamic array property {tag.name} is not declared by {fqcn} "
                              "(the map and the installed class package disagree)")
        return [(f"{tag.name}({i})", v)
                for i, v in enumerate(uprops.decode_array_tag(
                    pkg, tag, prop, resolver=schema.resolver, _pkgs=schema.packages,
                    style=uprops.T3D_STYLE))]

    if tag.ptype == PT_STRUCT:
        if prop is None:
            raise SchemaError(f"struct property {tag.name} is not declared by {fqcn} "
                              "(the map and the installed class package disagree) — its member "
                              "layout cannot be recovered")
        value = uprops.struct_tag_member_tree(pkg, tag, prop, resolver=schema.resolver,
                                              _pkgs=schema.packages, style=uprops.T3D_STYLE)
        default = _default_struct_tree(pkg, prop, fqcn, tag.array_index, schema=schema)
        return [(key, uprops.render_member_tree(uprops.strip_member_tree(value, default)))]

    text = uprops.render_default_tag(pkg, tag, prop, resolver=schema.resolver,
                                     _pkgs=schema.packages, style=uprops.T3D_STYLE)
    if tag.ptype in (PT_NAME, PT_STR, PT_STR_LEGACY):
        text = '"' + text + '"'                      # the editor quotes names and strings
    return [(key, text)]


# ── one actor ────────────────────────────────────────────────────────────────────────────────

@_decode_guard
def render_actor(pkg: Package, export_index0: int, *, schema: ImportSchema) -> str:
    """One actor export → its `Begin Actor … End Actor` T3D block.

    The block's shape mirrors what `MAP EXPORT` writes (`unrealed/t3d.md`): the class name BARE
    (the editor never qualifies it on export; `level import` re-qualifies on ingest), then the
    properties in the order the map serialized them — which is the same order the editor exports,
    because both walk the class's property list — then, for a brush, the inline geometry block
    followed by the `Brush=Model'…'` reference, then the trailing `Name="…"`.

    The `Brush=` reference is held back until AFTER the geometry block on purpose: an actor that
    binds its model before the model is defined imports with no usable bound and cannot be selected
    (`emit.emit_actor` keeps the same order and explains why).
    """
    if not (0 <= export_index0 < len(pkg.exports)):
        raise SchemaError(f"actor export index {export_index0} out of range in {pkg.name}")
    e = pkg.exports[export_index0]
    name = pkg.names[e["nm"]]
    bare = pkg.object_class_name(export_index0 + 1)
    fqcn = pkg.object_path(e["cls"])
    if bare is None or fqcn is None:
        raise SchemaError(f"actor {name}: its class reference does not resolve in {pkg.name}")
    if e["ssize"] <= 0:
        raise SchemaError(f"actor {name} ({fqcn}) has an empty serial body")

    lines = [f"Begin Actor Class={bare} Name={name}"]
    start = _skip_state_frame(pkg, e)
    tags, _pos = read_property_tags(pkg, start, e["soff"] + e["ssize"])
    brush_ref: int | None = None
    for tag in tags:
        if tag.name == "Brush" and tag.ptype == PT_OBJECT:
            brush_ref, _ = read_compact_index(tag.raw, 0)
            continue
        for key, value in render_prop(pkg, tag, fqcn, schema=schema):
            lines.append(f"    {key}={value}")
    if brush_ref is not None:
        brush = brush_of(pkg, brush_ref)
        lines.append(emit.emit_brush(brush))
        lines.append(f"    Brush=Model'{pkg.object_path(brush_ref)}'")
    lines.append(f'    Name="{name}"')
    lines.append("End Actor")
    return "\n".join(lines)


# ── the whole map ────────────────────────────────────────────────────────────────────────────

@_decode_guard
def level_export_index(pkg: Package) -> int:
    """The 0-based export index of the map's `Engine.Level` object — the one that owns the actor
    order. Exactly one is expected; none or several means this is not a map file."""
    found = [i for i, e in enumerate(pkg.exports)
             if pkg.object_path(e["cls"]) == ENGINE_LEVEL]
    if len(found) != 1:
        raise SchemaError(f"{pkg.name}: expected exactly one {ENGINE_LEVEL} object, found "
                          f"{len(found)} — this is not a map file")
    return found[0]


@_decode_guard
def actor_refs(pkg: Package) -> list[int]:
    """The map's actors, as signed object references, in the authoritative ORDER, nulls dropped.

    The order matters twice over: the brush subsequence IS the CSG precedence the level is built
    with, and `normalize.canonical_level_hash` folds the actor order in, so getting it wrong makes
    every acceptance compare fail. It is NOT the export-table order — that differs on every retail
    map tested — so it is read from the `Engine.Level` object's own `Actors` array.

    That array is the first thing in the Level's native tail, right after the object's
    `None`-terminated property list (a real map's Level carries no tagged properties at all), and
    is serialized as `[i32 Num][i32 Max]` — RAW 32-bit ints, not a compact count — followed by
    `Num` signed compact object references. A reference of 0 is a null/deleted slot and is dropped;
    retail maps carry 29-329 of them. `Actors[0]` is always the `LevelInfo`.

    Evidence: `dev/docs/spikes/2026-07-24-level-import-order/findings.md` (decoded on retail
    `00_Intro`, `00_Training`, `02_NYC_Street`); the same layout is what uedcli's own
    `native.level_write.write_level_body` writes.
    """
    e = pkg.exports[level_export_index(pkg)]
    buf, end = pkg.buf, e["soff"] + e["ssize"]
    # Entered through the StateFrame skip like every other body reader here: `RF_HasStack` is a
    # per-EXPORT flag and is set on objects nobody expects to carry one, so the decision is made on
    # the export's flags and never on the object's class (`unrealed/package-format.md` "`RF_HasStack`
    # is a per-EXPORT flag"). No sampled map flags its `Level`, but the rule is universal and the
    # cost of honouring it is one call.
    _tags, pos = read_property_tags(pkg, _skip_state_frame(pkg, e), end)
    num, _max = struct.unpack_from("<ii", buf, pos); pos += 8
    _check_count(num, "level actor")
    refs = []
    for _ in range(num):
        r, pos = read_compact_index(buf, pos)
        if pos > end:
            raise SchemaError(f"{pkg.name}: the Level Actors array overruns its body — "
                              "truncated or misparsed")
        if r != 0:
            refs.append(r)
    return refs


@_decode_guard
def import_map(pkg: Package, index, schema: ImportSchema) -> str:
    """A whole compiled map → the `Begin Map … End Map` T3D text `model.parse_t3d` ingests.

    `index` is a `classindex.ClassIndex` over the composed package search path; it answers whether
    a class descends from `Engine.Actor` and, later, requalifies the bare class names this emits.

    All actors are imported verbatim, in the `Actors`-array order. Two integrity gates make a
    silently partial trunk impossible:

    * every non-null `Actors` entry must be a local export whose class descends from `Engine.Actor`;
    * every actor-classed export in the package must appear in that array — otherwise the decode
      would drop content the map really holds, and the trunk would look complete while missing it.
    """
    refs = actor_refs(pkg)
    seen: set[int] = set()
    order: list[int] = []
    for ref in refs:
        if ref < 0:
            raise SchemaError(f"{pkg.name}: the Level Actors array names an IMPORTED object "
                              f"(ref {ref}); a map's actors are always its own exports")
        if ref > len(pkg.exports):
            raise SchemaError(f"{pkg.name}: the Level Actors array names export {ref}, "
                              f"which does not exist ({len(pkg.exports)} exports)")
        idx0 = ref - 1
        if idx0 in seen:
            raise SchemaError(f"{pkg.name}: actor {pkg.names[pkg.exports[idx0]['nm']]} appears "
                              "twice in the Level Actors array")
        seen.add(idx0)
        order.append(idx0)

    missing = [pkg.names[e["nm"]] for i, e in enumerate(pkg.exports)
               if i not in seen and _is_actor_export(pkg, index, i)]
    if missing:
        raise SchemaError(
            f"{pkg.name}: {len(missing)} actor(s) are not listed in the Level Actors array and "
            f"would be silently dropped: {', '.join(sorted(missing)[:10])}"
            + (" …" if len(missing) > 10 else ""))

    for idx0 in order:
        if not _is_actor_export(pkg, index, idx0):
            e = pkg.exports[idx0]
            raise SchemaError(f"{pkg.name}: the Level Actors array names "
                              f"{pkg.names[e['nm']]}, whose class "
                              f"{pkg.object_path(e['cls'])} does not descend from {ENGINE_ACTOR} "
                              "(is the right class package on the search path?)")

    blocks = [render_actor(pkg, idx0, schema=schema) for idx0 in order]
    return "Begin Map\n" + "\n".join(blocks) + "\nEnd Map\n"


# ── the editor's own scratch objects ─────────────────────────────────────────────────────────

# Classes an UnrealEd-saved map always carries that are EDITING APPARATUS, not level content.
# Matched on the BARE class name, so this must run BEFORE `ClassIndex.qualify_and_validate`
# rewrites `Camera` to `Engine.Camera` (see `drop_editor_scratch`).
#
# `Camera` is UnrealEd's viewport camera: it saves one per open editor viewport, so a map carries
# four or more of them (six in the committed `paste.dx`, four to eight in the other fixtures) with
# engine-allocated names like `Camera16`. It is NOT a level-content class and nothing in the game
# spawns from it — it has no subclasses at all in the composed Deus Ex class set, and although it
# derives FROM `Engine.PlayerPawn`, nothing derives from IT, so dropping the exact class cannot
# take a player start or any other real actor with it (checked against the composed `.u` set,
# 2026-07-27).
EDITOR_SCRATCH_CLASSES = frozenset({"Camera"})


def drop_editor_scratch(level: model.Level) -> list[str]:
    """Remove UnrealEd's own transient objects from a freshly imported level, in place.

    Returns the removed actor names, so the verb can report what it dropped rather than silently
    shrinking the import.

    **Why an import does not keep these.** A compiled map is the editor's saved workspace, not a
    clean inventory of level content: it also holds the apparatus the editor was using at the
    moment of the save. Two kinds of it:

    * the **builder brush** — the red scratch brush a level designer shapes geometry with before
      committing it to the world. Every saved map has exactly one, and it is a tool, not a room.
    * the **viewport cameras** — one `Camera` actor per open editor viewport.

    Keeping them would put editing apparatus into the durable T3D tree as though it were authored
    content, and a later `level materialize` of that tree would paste the imported builder brush
    in alongside the fresh one the editor creates for itself — two brushes competing for the name
    `Brush0`.

    **This must run BEFORE class names are qualified.** Both tests key on the SHORT class name
    (`Brush`, `Camera`), which is what the decode emits; `ClassIndex.qualify_and_validate` rewrites
    those to `Engine.Brush`/`Engine.Camera` on ingest, after which neither test can ever match
    again. The builder-brush test is `normalize.is_builder_brush`, reused rather than reimplemented
    so import and the acceptance compare agree on what a builder brush is (it keys on the reserved
    unnumbered inner model name `Brush` plus the absence of an explicit `CsgOper`, NOT on the actor
    name — a fresh editor does not number it `Brush0`).

    Owner ruling, 2026-07-27: drop the builder brush, and drop `Camera` actors too. This narrows
    the spec's "all actors imported verbatim" to "all CONTENT actors"; the rationale is
    `dev/docs/rationale/mapimport.md`.
    """
    from .normalize import is_builder_brush

    dropped = [name for name, a in level.actors.items()
               if is_builder_brush(a) or _bare_class(a) in EDITOR_SCRATCH_CLASSES]
    if not dropped:
        return []
    gone = set(dropped)
    level.actors = {n: a for n, a in level.actors.items() if n not in gone}
    level.order = [n for n in level.order if n not in gone]
    return dropped


def _bare_class(a: model.Actor) -> str:
    """An actor's class with any package/group qualification stripped (`Engine.Camera` → `Camera`),
    so the test works whether or not the name has been qualified yet."""
    return (a.cls or "").rsplit(".", 1)[-1]


def _is_actor_export(pkg: Package, index, export_index0: int) -> bool:
    """Does export `export_index0` hold an `Engine.Actor` descendant? Keyed on the CLASS reference's
    fully-qualified path (the actor's own path names the actor, not its class), so a class defined
    in any package on the search path resolves."""
    fqcn = pkg.object_path(pkg.exports[export_index0]["cls"])
    return fqcn is not None and index.descends_from(fqcn, ENGINE_ACTOR)
