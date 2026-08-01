"""Self-rendered orthographic preview — a low-noise COLOR image from the model alone (no
editor), so the LLM can SEE a brush's geometry and which poly INDEX is which face. `--faces wire`
(the default) draws outlines only; `--faces flat` fills each surviving face solid through a depth
buffer and keeps the wireframe over it (see `_scene_geometry` for the cull and the edge rule).
Rendering is stdlib only (no PIL/numpy), so every function here returns raw **PPM/P6
bytes IN MEMORY**. That is an internal format only: the CLI's disk-write boundary
(`rendering.render_actors_to_out`) encodes those bytes to **PNG** with Pillow before
writing, and PNG is the only form a preview ever takes on disk (no container/UnrealEd
involved either way).

**Two words, deliberately distinct — "annotation" vs "label".** An **ANNOTATION** is the
*selection* concept: WHICH extra marks a render draws (face indices, actor names), chosen by
the `--annotate` flag and carried by an `AnnotationSpec` (`parse_annotation_spec`,
`DEFAULT_ANNOTATIONS`). A **LABEL** is the *drawing* concept: one concrete piece of text laid
out on the canvas (`_LabelItem`, `_place_labels`, `poly_labels`) — the mechanism that renders
an annotation without colliding with the wireframe. So annotations are decided, labels are
placed. Neither has anything to do with the **actor `label` DIMENSION** (`labellib.py` — the
flat, cross-cutting `--label` classification stored per actor in the trunk); that is a third,
unrelated sense living outside this module, and it is why the selection concept here is no
longer called "label".

Rendering choices (all to make poly numbers readable):
  - dark-on-light-grey (display-ready, no negate): front edges darker, obscured/back edges
    lighter (face distinction by shade). Uncoloured brushes are black/grey; on the shared
    preview path each brush is coloured by its CSG classification (`_CSG_PALETTE`).
  - a highlighted poly (`--highlight`) is drawn in its brush's vivid front hue with a
    bolder line (the facing dim is ignored on it); `--zoom` only frames, never highlights.
  - point (non-brush) actors draw as a DT_Sprite billboard or a labelled marker, with
    optional faint collision/light/sound overlays (see PointRender). A highlighted point
    actor (`--highlight <name>`) gets corner brackets (a selection reticle) drawn UNDER its
    sprite/marker.
  - a NAME label (legacy path only — see below) sits in a knockout (white) box so the wireframe never
    runs through it, tied to its anchor dot by a leader line when nudged. Placement is density-aware
    (`DensityGrid` + `_place_labels`): names flee crowded regions and never cover a point-actor icon,
    the legend, or an on-face number.
  - HYBRID per-brush tint + legend (the CSG-coloured `color_by_csg` path, i.e. the real preview): the
    wireframe stays CSG-coloured, but each actor's LABELS carry a distinct categorical TINT
    (`assign_tints` → `_TINT_PALETTE`) — so two brushes with the SAME CSG op (one wireframe hue) are
    still told apart by their label colour. A brush's on-face poly-index decal and a point actor's
    marker use its tint. A top-left LEGEND (`_draw_legend`) maps each tint → actor NAME (brush = filled
    square, point = filled diamond), and actor names live there, OFF the geometry (declutter). The
    legacy black/grey path keeps black accents, on-geometry names, no legend.
  - `focus` (an actor name) recedes every OTHER brush — its wireframe to faint lines, and under a FILLED
    mode its fills to a faint tint of themselves — and paints face numbers only for the focused brush;
    `highlight` OVERRIDES focus (a highlighted poly/actor stays vivid+bold on top, at FULL fill
    strength, and keeps its number). All names still appear in the legend regardless of focus.
  - an `AnnotationSpec` (parsed from `--annotate`) selects WHICH annotations draw, per kind, by element
    category:
    e.g. `name:brush` = brush names only (⇒ their legend rows), `poly:hi` = highlighted faces only,
    `poly:vis,poly:hi,name` (the default) = face numbers + all names. On-face numbering is facing-blind,
    so `poly:vis` numbers every face (front/back shown by opacity); `poly:hi`/`none` stay exact.
  - poly face indices are the SOLE thing painted ON the geometry: each index is a CENTERED texture flat
    IN its face plane (`_plan_onface_texture`/`_draw_painted_decal`) — gravity-hung on walls/slopes,
    world-Y-aligned on floors/ceilings/caps, per-brush tinted, translucent with a 6/9 underline + halo,
    omitted when unreadable ON SCREEN (below a min projected texel size; no leader fallback). There is
    no leader-box poly-label mode.
  - poly-index opacity is GRADED by depth (`_decal_opacity` of `_occluder_count`): a face is dimmed by
    each front face in front of it under the self-or-solid rule (a solid brush's face, or another face
    of the SAME brush) — so a subtract/hollow room self-shades near→far without dimming brushes inside it.

Why a viewer at all: surface selection (PF_Selected) does NOT round-trip through the
brush T3D (verified — dev/docs/spikes/2026-06-17-capability-gaps.md), so a poly is identified MODEL-SIDE by
its PolyList index and this viewer maps index↔face.

Views: top (X/Y), front (X/Z), side (Y/Z) orthographic; iso isometric (separates
opposite faces). render_quad_pgm tiles Top/Front/Iso/Side like UnrealEd.
"""
from __future__ import annotations

import math
import re
from array import array
from dataclasses import dataclass, field
from decimal import Decimal

from .model import Actor
from .texframe import newell, poly_flags_int, world_uv_frame


class PreviewAbort(Exception):
    """A refusal the renderer can only reach mid-render, carried out to `dispatch`, which turns it into
    a clean exit 2. Everything a `--faces` render can validate is validated in `dispatch` BEFORE any
    pixel is drawn; this exists for the cases that cannot be — an out-of-memory buffer at an uncapped
    `--size`. So a `--faces` render is NOT fully validated before it starts."""


_ORTHO_AXES: dict[str, tuple[int, int]] = {"top": (0, 1), "front": (0, 2), "side": (1, 2)}
_DEPTH: dict[str, tuple[float, float, float]] = {
    "top": (0, 0, -1), "front": (0, 1, 0), "side": (1, 0, 0),
}

# Colours (RGB), tuned for a light-grey background (see BG).
WHITE = (255, 255, 255)
FRONT = (0, 0, 0)         # visible faces — black (uncoloured default)
BACK = (165, 165, 165)    # obscured faces — light grey (uncoloured default)
DIVIDER = (110, 110, 110)
CAPTION = (90, 90, 90)
MARKER = (90, 90, 90)     # point-actor marker + label — neutral grey (NOT a CSG hue)

# CSG-op wire palette — each brush's wireframe is coloured by its CSG classification when
# `color_by_csg=True` (the shared `actor`/`stash`/`prefab preview` path). Each entry is a
# (front, back) shade pair: front = viewer-facing / vivid (max-saturation), back = obscured /
# lighter — so the facing cue (front darker, back lighter) survives on the light-grey background, and
# `front` doubles as the vivid highlight hue. Adapted from UnrealEd's own brush-wire legend (hue
# preserved, luminance re-tuned for our light-grey bg — UED tunes for a near-black viewport); see
# dev/docs/unrealed/rendering.md. Red is deliberately NOT used (it's UED's builder brush, which we
# don't render). test_preview.py pins the classify→palette→render WIRING (a subtracted brush renders
# in the `subtract` pair; a point actor is never painted CSG-additive), not these literal RGB values.
# NOTE: `semisolid` deliberately DIVERGES from UED's rose (223,149,157) to a warm CORAL. UED's
# semisolid and mover are both red/purple and are told apart only by saturation against its black
# viewport — a cue that dies on our light bg (they conflated). Coral (warm) vs magenta (cool) stays
# distinct on any background; see spikes/2026-07-22-unrealed-brush-wire-colors.md.
PF_INVISIBLE = 0x00000001
PF_MASKED = 0x00000002
PF_SEMISOLID = 0x00000020
PF_NOTSOLID = 0x00000008
_CSG_PALETTE: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "add":       ((0, 0, 200),    (120, 120, 225)),   # additive solid — blue
    "subtract":  ((150, 110, 0),  (205, 180, 110)),   # subtracted — yellow / gold
    "semisolid": ((205, 95, 60),  (232, 165, 140)),   # semi-solid — warm coral (distinct from mover)
    "nonsolid":  ((0, 140, 0),    (120, 200, 120)),   # non-solid — green
    "mover":     ((150, 0, 190),  (205, 130, 225)),   # mover — magenta / purple
}

# Overlay colours (faint, solid — the renderer has no alpha blend buffer). Collision = red and
# sound = blue are UED-faithful; light is deviated to orange so it stays distinct from BOTH (UED
# draws light in the same red as collision, which are separate toggles here). All three stay
# distinguishable from the CSG palette above. Pinned in test_preview.py.
COL_COLLISION = (235, 150, 150)   # faint light-red — collision cylinder
COL_SOUND = (150, 165, 235)       # faint blue — sound reach
COL_LIGHT = (245, 175, 80)        # faint orange — light reach (deviated from UED's red)

# Categorical per-ACTOR label tints. The wireframe stays CSG-coloured (blue=add, gold=subtract, …); an
# actor's LABELS use its own tint instead — a brush's on-face poly-index decals + its legend swatch, and
# a point actor's on-geometry marker + its legend glyph. This is the fix for the CSG palette's
# cap: two brushes with the SAME CSG op share ONE wireframe hue, so their labels were indistinguishable;
# a distinct per-brush tint tells them apart while the CSG wireframe cue is preserved. Tints are assigned
# per actor in scene order (drawn or not — brushes AND point actors alike; an undrawn point actor with no
# render data still consumes an index), cycling when the scene has more actors than entries. Chosen for
# contrast on the light-grey bg (BG=224) and mutual separation, and kept clear of the two most common CSG
# wireframe hues (add=blue, subtract=gold) so a tint never reads as a CSG cue. The on-face number (digits
# AND its underline) is painted in the tint; a legacy NAME label keeps black digits with a tinted box.
# Used ONLY on the CSG-coloured preview path (`color_by_csg`); the legacy black/grey path keeps black
# accents + on-geometry names and draws no legend. test_preview.py pins the tint→label/legend WIRING (a
# brush's index labels carry its assigned tint; a point marker is tinted, not CSG-additive), not the
# literal RGB values.
_TINT_PALETTE: list[tuple[int, int, int]] = [
    (206, 34, 44),     # red      — CSG uses no red (builder brush, not rendered), so it anchors the set
    (0, 150, 150),     # teal
    (140, 55, 205),    # violet
    (222, 45, 135),    # rose / pink
    (30, 110, 200),    # azure    — cyan-shifted + lighter so it reads apart from CSG add-blue
    (60, 160, 65),     # green
    (150, 90, 40),     # brown
    (90, 95, 115),     # slate
    (0, 158, 120),     # emerald
    (120, 120, 30),    # olive
]


def assign_tints(actors: list[Actor]) -> dict[str, tuple[int, int, int]]:
    """Map each actor's Name to a categorical label tint (`_TINT_PALETTE`, cycled by scene position),
    one per actor in scene order (drawn or not — brushes AND point actors alike; an undrawn point actor
    still consumes an index), so a brush's poly-index labels and a point actor's marker each carry the
    actor's own tint and the legend can key tint→name. Deterministic given actor order, so the same actor
    gets the same tint in every quad pane and the legend."""
    return {a.name: _TINT_PALETTE[i % len(_TINT_PALETTE)] for i, a in enumerate(actors)}


@dataclass(frozen=True, kw_only=True)
class AnnotationSpec:
    """Which ANNOTATIONS to draw, as a set of element CATEGORIES per kind. A poly face has category
    `(is_front, is_highlighted)`; an actor name has `(is_brush, is_highlighted)`. The `--annotate`
    grammar (see `parse_annotation_spec`) is: a bare kind = ALL of it; each filter narrows; commas union.
    So membership is plain set algebra and the renderer just asks `draws_poly`/`draws_name`."""
    poly: frozenset[tuple[bool, bool]]   # selected (is_front, is_highlighted)
    name: frozenset[tuple[bool, bool]]   # selected (is_brush, is_highlighted)

    def draws_poly(self, *, is_front: bool, is_highlighted: bool) -> bool:
        return (is_front, is_highlighted) in self.poly

    def draws_name(self, *, is_brush: bool, is_highlighted: bool) -> bool:
        return (is_brush, is_highlighted) in self.name

    @classmethod
    def all(cls) -> "AnnotationSpec":
        return parse_annotation_spec("all")

    @classmethod
    def none(cls) -> "AnnotationSpec":
        return parse_annotation_spec("none")

    @classmethod
    def default(cls) -> "AnnotationSpec":
        return parse_annotation_spec(DEFAULT_ANNOTATIONS)


DEFAULT_ANNOTATIONS = "poly:vis,poly:hi,name"          # all face indices (vis is facing-blind) + all names
_ALL_POLY = frozenset((f, h) for f in (False, True) for h in (False, True))
_ALL_NAME = frozenset((b, h) for b in (False, True) for h in (False, True))
_POLY_FILTERS = {"vis", "hi", "highlighted"}       # `highlighted` is a synonym for `hi`
_NAME_FILTERS = {"brush", "point", "hi", "highlighted"}
_KEYWORDS = {"all", "none", "highlighted"}


def parse_annotation_spec(text: str) -> AnnotationSpec:
    """Parse a `--annotate` value into a `AnnotationSpec`. Grammar: a comma-set of selectors `KIND[:FILTER…]`,
    unioned. Bare kind = ALL of that kind; each colon filter narrows (intersecting within one
    selector); tokens are whitespace-stripped + lower-cased. Kinds `poly`/`name`; poly filters `vis`
    (an INERT alias of bare `poly` — on-face numbering is facing-blind, so it no longer means
    front-only; kept only so pre-facing-blind specs still parse) / `hi`; name filters `brush`/`point`/`hi`
    (`highlighted` = `hi`). Whole-value
    keywords `none` / `all` (=`poly,name`) / `highlighted` (=`poly:hi,name:hi`) must stand alone. Zero
    effective tokens ⇒ `none`. Raises `ValueError` naming the offending token on any invalid input."""
    tokens = [t for t in (raw.strip().lower() for raw in text.split(",")) if t]
    if not tokens:
        return AnnotationSpec(poly=frozenset(), name=frozenset())
    if keyword := next((t for t in tokens if t in _KEYWORDS), None):
        if len(tokens) != 1:
            raise ValueError(
                f"--annotate: {keyword!r} is a whole-value keyword and cannot be combined with "
                f"other tokens (got {text!r})")
        if keyword == "all":
            return AnnotationSpec(poly=_ALL_POLY, name=_ALL_NAME)
        if keyword == "none":
            return AnnotationSpec(poly=frozenset(), name=frozenset())
        return _union_selectors(["poly:hi", "name:hi"])       # highlighted
    return _union_selectors(tokens)


def _union_selectors(tokens: list[str]) -> AnnotationSpec:
    poly: set[tuple[bool, bool]] = set()
    name: set[tuple[bool, bool]] = set()
    for token in tokens:
        p, n = _selector_categories(token)
        poly |= p
        name |= n
    return AnnotationSpec(poly=frozenset(poly), name=frozenset(name))


def _selector_categories(token: str) -> tuple[set[tuple[bool, bool]], set[tuple[bool, bool]]]:
    kind, *filters = token.split(":")
    if kind == "poly":
        cats = set(_ALL_POLY)
        for f in filters:
            if f not in _POLY_FILTERS:
                raise ValueError(f"--annotate: unknown filter {f!r} for kind 'poly' (in {token!r})")
            cats = {c for c in cats if c[0]} if f == "vis" else {c for c in cats if c[1]}
        return cats, set()
    if kind == "name":
        cats = set(_ALL_NAME)
        subkind: str | None = None
        for f in filters:
            if f not in _NAME_FILTERS:
                raise ValueError(f"--annotate: unknown filter {f!r} for kind 'name' (in {token!r})")
            if f in ("brush", "point"):
                if subkind and subkind != f:
                    raise ValueError(
                        f"--annotate: {token!r} names both 'brush' and 'point' (empty intersection)")
                subkind = f
                cats = {c for c in cats if c[0] == (f == "brush")}
            else:
                cats = {c for c in cats if c[1]}
        return set(), cats
    raise ValueError(f"--annotate: unknown kind {kind!r} (in {token!r})")


@dataclass(frozen=True, kw_only=True)
class PointRender:
    """Resolved per-point-actor render data (computed in dispatch, drawn here — preview.py stays
    resolver-free). `sprite` is a decoded masked bitmap `(w, h, rgb, mask)` where `rgb` is
    w*h*3 packed bytes and `mask` is w*h bytes (1 = opaque, 0 = transparent). `sprite_world` is
    the billboard footprint `(world_w, world_h)` in world units. `collision`/`light_radius`/
    `sound_radius` are populated only when the matching `--show-*` overlay is requested AND the
    field resolves. A pure marker (DT_Mesh/DT_None, or a schema-degraded / sprite-miss actor) has
    them all None and draws a labelled marker at Location."""
    label: str = ""
    sprite: tuple[int, int, bytes, bytes] | None = None
    sprite_world: tuple[float, float] | None = None
    collision: tuple[float, float] | None = None      # (radius, half-height)
    light_radius: float | None = None                 # world units
    sound_radius: float | None = None                 # world units


@dataclass(frozen=True, kw_only=True)
class TextureData:
    """The decoded texture payload a `--faces textured` render draws from. `by_ref` maps a
    **casefolded** texture ref (FName semantics) to that texture's whole mip pyramid, each level as
    `(w, h, rgb, mask)`; every ref the scene uses is present, since an unreadable one refuses in
    `dispatch` before rendering. `masked` answers "does this face draw palette index 0 as a hole?" per
    `(actor_name, poly_idx)`."""
    by_ref: dict[str, list[tuple[int, int, bytes, bytes]]]
    masked: dict[tuple[str, int], bool]


@dataclass(frozen=True, kw_only=True)
class FaceData:
    """What a FILLED render needs about faces that `preview.py` cannot work out for itself, resolved in
    `dispatch` and passed across as data.

    `movers` is the set of actor Names that `movers.is_mover` said yes to — the schema-aware predicate,
    read off the game's class hierarchy. The fill needs it because a MOVER is never carved into the
    world whatever `CsgOper` it carries, so it escapes the subtract cull and fills in mover colour.

    **`movers` and `textures` are separate fields on purpose.** `flat` needs the mover set and no
    textures at all; a single texture-named payload would invite passing `None` for `flat`, which drops
    the mover set and makes the cull render a `CsgOper=CSG_Subtract` door inside-out."""
    movers: frozenset[str]
    textures: TextureData | None = None


@dataclass(frozen=True, kw_only=True)
class PreviewData:
    """Everything `dispatch` resolves for one preview and `preview.py` only draws — the resolver-free
    seam. `points` maps a point actor's Name to its `PointRender`; a point actor absent from it draws
    nothing. `faces` is `None` under `--faces wire` (which resolves nothing) and carries a `FaceData`
    under every filled mode."""
    points: dict[str, PointRender] = field(default_factory=dict)
    faces: FaceData | None = None


def world_light_radius(light_radius: int) -> float:
    """UE1 `AActor::WorldLightRadius`: byte `LightRadius` → world units, `25*(LightRadius+1)`. The
    `+1` is real (LightRadius=0 still reaches 25 UU). Spike 2026-07-21-unrealed-sprite-radii-rendering
    Q3 (✅ UE1 v200 `AActor.h`)."""
    return 25.0 * (light_radius + 1)


def world_sound_radius(sound_radius: int) -> float:
    """UE1 `AActor::WorldSoundRadius`: byte `SoundRadius` → world units, `25*(SoundRadius+1)`. Same
    spike Q3."""
    return 25.0 * (sound_radius + 1)


def sprite_footprint(draw_scale: float, usize: int, vsize: int) -> tuple[float, float]:
    """A DT_Sprite billboard's world footprint: `DrawScale*USize × DrawScale*VSize` (1 texel = 1 UU
    at DrawScale 1). Spike Q1 (✅ UE1 v200 `UnSprite.cpp` `FDynamicSprite::Setup`)."""
    return (draw_scale * usize, draw_scale * vsize)


def classify_brush(actor: Actor, *, is_mover: bool | None = None) -> str:
    """A brush actor's CSG palette key (`add`/`subtract`/`semisolid`/`nonsolid`/`mover`). A Mover →
    magenta, tested FIRST; else `CsgOper` (subtract → gold) is refined by the actor-level solidity
    `PolyFlags` on the additive side (PF_Semisolid → coral, PF_NotSolid → green). See the ergonomics
    spec §4 legend.

    **`is_mover` decides HOW mover-ness is answered, and the two answers are not interchangeable.**

    - `is_mover=None` (`--faces wire`, the default) → a NAME GUESS, `cls` basename ends in `Mover`.
      That is deliberate: the real predicate (`movers.is_mover`) needs a `classindex.ClassIndex`, and
      `wire` is the mode that must keep working with no game install at all. The cost is that a mover
      whose class name does not end in `Mover` (`CEDoor`, `BreakableGlass`, the lowercase `TNM.*mover`
      classes) falls through to its `CsgOper`/`PolyFlags` and reads as a static brush. Under `wire`
      that costs a wire shade and `is_solid`'s hidden-line grading — cosmetic.
    - `is_mover=True/False` (every FILLED mode) → the caller's authoritative answer, which
      `dispatch` obtains from `movers.is_mover` off the game's class hierarchy. A filled render MUST
      pass it: there the name guess does not cost a shade, it deletes faces. For a `CEDoor` carrying
      `CsgOper=CSG_Subtract` the guess says `subtract`, so the subtract cull would drop every
      camera-facing face and draw the door inside-out. One render never mixes the two answers — the
      key returned here feeds the fill colour, `is_solid` (hence `occluders`) and the cull alike."""
    mover = actor.cls.rpartition(".")[2].endswith("Mover") if is_mover is None else is_mover
    if mover:
        return "mover"
    oper = next((v for k, v in actor.props if k == "CsgOper"), "CSG_Add")
    if oper == "CSG_Subtract":
        return "subtract"
    pf = next((v for k, v in actor.props if k == "PolyFlags"), None)
    flags = 0
    if pf is not None:
        try:
            flags = int(pf)
        except ValueError:
            flags = 0
    if flags & PF_SEMISOLID:
        return "semisolid"
    if flags & PF_NOTSOLID:
        return "nonsolid"
    return "add"

_FONT: dict[str, list[str]] = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    ":": ["000", "010", "000", "010", "000"], "-": ["000", "000", "111", "000", "000"],
    "T": ["111", "010", "010", "010", "010"], "O": ["111", "101", "101", "101", "111"],
    "P": ["111", "101", "111", "100", "100"], "F": ["111", "100", "111", "100", "100"],
    "R": ["111", "101", "111", "110", "101"], "N": ["101", "111", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"], "S": ["111", "100", "111", "001", "111"],
    "D": ["110", "101", "101", "101", "110"], "E": ["111", "100", "111", "100", "111"],
    # Full uppercase alphabet + underscore so point-actor markers can be labelled with the actor Name.
    "A": ["111", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"],
    "C": ["111", "100", "100", "100", "111"], "G": ["111", "100", "101", "101", "111"],
    "H": ["101", "101", "111", "101", "101"], "J": ["001", "001", "001", "101", "111"],
    "K": ["101", "110", "100", "110", "101"], "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"], "Q": ["111", "101", "101", "111", "011"],
    "U": ["101", "101", "101", "101", "111"], "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"], "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"], "Z": ["111", "001", "010", "100", "111"],
    "_": ["000", "000", "000", "000", "111"], "+": ["000", "010", "111", "010", "000"],
}


def _project(v, view: str, iso_angle: float = 30.0) -> tuple[float, float]:
    if view == "iso":
        x, y, z = v
        r = math.radians(iso_angle)
        return ((x - y) * math.cos(r), (x + y) * math.sin(r) + z)
    ax, ay = _ORTHO_AXES[view]
    return (v[ax], v[ay])


def _iso_depth(iso_angle: float) -> tuple[float, float, float]:
    return (1.0, 1.0, -2.0 * math.sin(math.radians(iso_angle)))


def _view_depth(iso_angle: float, view: str) -> tuple[float, float, float]:
    """The into-screen direction for a view: `dot(point, this)` orders points front→back (smaller =
    nearer the camera). Used to decide whether a labelled face is occluded by nearer solid geometry."""
    return _iso_depth(iso_angle) if view == "iso" else _DEPTH[view]


def _poly_centroid_2d(vs) -> tuple[float, float]:
    """The area-weighted centroid of a 2-D projected face (shoelace) — the visual centre a poly-index
    label + arrow should point at. Falls back to the vertex average for a degenerate (~zero-area,
    edge-on) face, where the vertex average is the best available centre."""
    area = cx = cy = 0.0
    n = len(vs)
    for i in range(n):
        (x0, y0), (x1, y1) = vs[i], vs[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-9:
        return (sum(p[0] for p in vs) / n, sum(p[1] for p in vs) / n)
    return (cx / (3 * area), cy / (3 * area))


def _point_in_poly(pt, poly) -> bool:
    """Ray-cast point-in-polygon on a 2-D projected face (used to test label occlusion). Points on the
    boundary may read either way — fine here, occlusion is a soft visual cue."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i - 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _is_front(verts3d, view: str, iso_angle: float = 30.0) -> bool:
    """Does this face point at the camera, per its own WINDING (the Newell normal — not the stored
    `Normal`, which the engine recomputes from winding anyway)? Vertices are wound CCW-from-outside, so an
    outward normal pointing against the into-screen direction is camera-facing.

    **This answer is INVERTED on a mirrored brush** — see `_is_front_corrected`, which every filled
    render goes through instead."""
    d = _iso_depth(iso_angle) if view == "iso" else _DEPTH[view]
    n = newell(verts3d)
    return (n[0] * d[0] + n[1] * d[1] + n[2] * d[2]) < 0


def _is_front_corrected(verts3d, view: str, iso_angle: float = 30.0, *, mirrored: bool) -> bool:
    """`_is_front`, with a MIRRORED brush's answer put back the right way round.

    A negative-determinant linear part (`brush scale --by -1,1,1` — a negative axis mirrors) is a
    REFLECTION: it reverses every ring's handedness, so a transformed face's Newell normal comes out as
    the NEGATIVE of its true outward normal and `_is_front` answers the opposite of the truth for every
    face of that brush. One sign flip here fixes the subtract cull, the three colour roles, the `flat`
    edge rule and `occluders` together, because all four are expressed in terms of this boolean.

    **An EVEN number of negative axes is NOT a mirror** — `Scale=(X=-1,Y=-1)` is a 180° rotation,
    determinant +1, normals correct — so the discriminator is the determinant's SIGN, not "has a negative
    component"; a sheer leaves the determinant at the scale product. The caller computes `mirrored`: it is
    a per-BRUSH property and this is asked per face."""
    front = _is_front(verts3d, view, iso_angle)
    return not front if mirrored else front


# ----- raster primitives (RGB buffer, 3 bytes/pixel) -------------------------

BG = 224   # light-grey background: lifts the low-contrast subtract-gold vs a white bg while keeping
           # the black FRONT lines, light-grey BACK lines, and white label boxes all legible.


def _new_buf(size: int) -> bytearray:
    return bytearray(bytes((BG, BG, BG)) * (size * size))


def _alloc_buffers(size: int, *, depth: bool):
    """The RGB canvas, plus a depth buffer when the render fills faces. `--size` is UNCAPPED (owner
    ruling: no size guard, no cost ceiling), so an absurd value is a genuine `MemoryError` — caught
    here and re-raised as a `PreviewAbort` naming the size, never a traceback.

    The depth buffer is an `array("f")`, not a `list[float]`: at `--size 4096` a list of Python floats
    is ~0.5 GB against ~67 MB. `inf` = nothing drawn yet, and smaller = nearer.

    **BOTH exceptions are load-bearing.** `MemoryError` is the one an allocation that merely does not fit
    raises; past `3·size² > sys.maxsize` the same expression raises **`OverflowError`** instead ("repeated
    bytes are too long", or "cannot fit 'int' into an index-sized integer" further out). Catching only
    `MemoryError` left the largest sizes — the ones most likely to be typed by accident — tracebacking,
    on `wire` as well as the filled modes, since every canvas is allocated here."""
    try:
        buf = _new_buf(size)
        zbuf = array("f", [math.inf]) * (size * size) if depth else None
    except (MemoryError, OverflowError):
        raise PreviewAbort(f"--size {size} is too large: a {size}x{size} render buffer does not fit "
                           f"in memory (--size is uncapped, so pick a smaller one)") from None
    return buf, zbuf


def _alloc_dim_mask(size: int) -> bytearray:
    """The per-pixel `--focus` brightness mask (see `_fill_face`/`_fade_dimmed`).

    The guard is **defence in depth behind `_alloc_buffers`**, not a reachable path on `--size` alone: this
    mask is `size²` bytes and the canvas plus depth buffer are `7·size²`, allocated first, so any `--size`
    that fails here has already failed there. It stays because the two calls are not atomic — memory
    pressure or fragmentation between them is not a size question — and because a bare traceback out of a
    preview is the one outcome `--size` handling may never produce."""
    try:
        return bytearray(size * size)
    except (MemoryError, OverflowError):
        raise PreviewAbort(f"--size {size} is too large: a {size}x{size} render buffer does not fit "
                           f"in memory (--size is uncapped, so pick a smaller one)") from None


def _px(buf, size, x, y, rgb) -> bool:
    """Plot one pixel, clipped to the frame. Returns whether it LANDED, which `_line` sums so a caller can
    tell "I drew this" from "this was clipped away entirely"."""
    if 0 <= x < size and 0 <= y < size:
        i = (y * size + x) * 3
        buf[i], buf[i + 1], buf[i + 2] = rgb
        return True
    return False


def _line(buf, size, p0, p1, rgb, weight: int = 1, alpha: float = 1.0) -> int:
    """Bresenham line. `weight` > 1 thickens it (each plotted point becomes a weight×weight block,
    toward +x/+y) — used to make a highlighted poly's edges bolder without changing hue. `alpha` < 1
    COMPOSITES the line over whatever's behind it (via `_blend_px`) instead of painting opaquely — used
    to DIM a `--focus`/`--breakdown` non-focused brush so its faint wireframe shows crossed edges and
    numbers THROUGH it rather than covering them. Bresenham visits each pixel once, so no double-blend.

    **Returns the number of pixels that actually LANDED** inside the frame — 0 when the segment is clipped
    away entirely. `--highlight` needs that to tell "this face is not visible" from "this face is outside
    the frame", both of which draw nothing but only one of which is about depth."""
    plot = _px if alpha >= 1.0 else (lambda b, s, x, y, c: _blend_px(b, s, x, y, c, alpha))
    drawn = 0
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if weight <= 1:
            drawn += plot(buf, size, x0, y0, rgb)
        else:
            for wy in range(weight):
                for wx in range(weight):
                    drawn += plot(buf, size, x0 + wx, y0 + wy, rgb)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy
    return drawn


def _circle(buf, size, cx, cy, r_px, rgb) -> None:
    """A solid (continuous) wire circle of pixel radius `r_px` centred at (cx, cy)."""
    r_px = max(1, int(round(r_px)))
    steps = max(24, r_px * 4)
    prev = None
    for i in range(steps + 1):
        a = 2 * math.pi * i / steps
        p = (int(round(cx + r_px * math.cos(a))), int(round(cy + r_px * math.sin(a))))
        if prev is not None:
            _line(buf, size, prev, p, rgb)
        prev = p


def _filled_diamond(buf, size, cx, cy, r, rgb) -> None:
    """A solid diamond of pixel radius `r` centred at (cx, cy) — the point-actor marker glyph on the
    CSG-coloured preview (tinted per actor), and its matching legend glyph."""
    for dy in range(-r, r + 1):
        span = r - abs(dy)
        for dx in range(-span, span + 1):
            _px(buf, size, cx + dx, cy + dy, rgb)


def _draw_selection_brackets(buf, size, cx, cy, r_px) -> None:
    """Point-actor highlight = four black corner brackets (a selection reticle) framing the actor.
    Deliberately NOT a circle or rectangle: circles here already mean light/sound radius and the
    top-view collision cylinder, and a rectangle is the side-view cylinder — a selection mark must
    not reuse that vocabulary. Frames from `r_px*1.5` out so it never obscures the sprite/marker."""
    ri = int(round(r_px * 1.5))
    arm = max(3, ri // 2)
    for sx, sy, dx, dy in ((cx - ri, cy - ri, 1, 1), (cx + ri, cy - ri, -1, 1),
                           (cx - ri, cy + ri, 1, -1), (cx + ri, cy + ri, -1, -1)):
        for t in (0, 1):                          # 2px thick corners
            _line(buf, size, (sx, sy + t * dy), (sx + dx * arm, sy + t * dy), FRONT)
            _line(buf, size, (sx + t * dx, sy), (sx + t * dx, sy + dy * arm), FRONT)


def _blit(buf, size, cx, cy, pw, ph, tex, mask, tw, th) -> None:
    """Scaled nearest-neighbour bitmap blit of a `tw×th` RGB texture (`tex`, packed w*h*3) into a
    `pw×ph` screen rectangle centred at (cx, cy). `mask` (w*h bytes, 1 = opaque) makes palette-index-0
    pixels transparent so the sprite never occludes the wireframe behind it."""
    if pw <= 0 or ph <= 0 or tw <= 0 or th <= 0:
        return
    x0, y0 = cx - pw // 2, cy - ph // 2
    for dy in range(ph):
        sy = min(th - 1, dy * th // ph)
        for dx in range(pw):
            sx = min(tw - 1, dx * tw // pw)
            si = sy * tw + sx
            if mask[si]:
                _px(buf, size, x0 + dx, y0 + dy, (tex[si * 3], tex[si * 3 + 1], tex[si * 3 + 2]))


# ----- solid face fills (`--faces flat`) -------------------------------------
# A filled face is rasterized ONCE, into the RGB canvas plus a depth buffer, before any line art. The
# two rules that make it correct are both spelled out on the functions below: EVEN-ODD scanline
# coverage (a triangle fan bleeds outside the 0.1-0.6 % of real faces that are concave), and depth
# interpolated affinely off the face's OWN plane (exact under an orthographic projection).


def _face_depth_affine(v3, world_to_pxf, d_vec):
    """This face's depth as an affine function of the screen pixel: `(A, B, C)` with
    `depth = A*x + B*y + C`, or None for a face with no screen area to fill.

    `depth(P) = dot(P, d_vec)` orders points front-to-back (SMALLER = nearer). Both that and the
    projection are linear in world space, so on ONE plane depth is affine in screen space and
    interpolates EXACTLY — an orthographic camera needs no per-pixel divide. Solved from three points
    on the plane rather than from three vertices, because the plane is chosen and the vertices are not:
    it is anchored at `v3[0]` with the NEWELL normal (winding, not the stored `Normal`), which is
    observable on a face that is not planar — reachable from arbitrary editor T3D via `--from-t3d`.

    None means the solve is singular, i.e. the face projects to zero area (edge-on), or the face's own
    normal is degenerate. Either way it is skipped."""
    solved = _plane_screen_probes(v3, world_to_pxf)
    if solved is None:
        return None
    probes, (x0, y0), (ux, uy, vx, vy), det = solved
    d0, d1, d2 = (sum(p[i] * d_vec[i] for i in range(3)) for p in probes)
    return _affine_on_plane(d0, d1, d2, x0, y0, ux, uy, vx, vy, det)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _plane_screen_probes(v3, world_to_pxf):
    """Three world probes ON THE FACE'S OWN PLANE and their screen positions — the shared machinery
    that solves any quantity affine in world space (depth, U, V) exactly under an orthographic camera.
    Returns `(probes, (x0, y0), (ux, uy, vx, vy), det)`, or None when the face has no screen area to
    fill (edge-on) or its normal is degenerate.

    The plane is anchored at `v3[0]` with the NEWELL normal (winding, not the stored `Normal`), which is
    observable on a non-planar face reachable via `--from-t3d`. The in-plane probes step out by the
    face's OWN size (`span`), so the singular `det` test is a statement about the FACE rather than the
    probe length: a fixed 1-UU step would scale `det` with the framing's pixels-per-world-unit and read
    a perfectly good 4096-UU floor as edge-on in a zoomed-out pane. Measured to buy no float precision
    over a fixed step — only that meaning."""
    n = newell(v3)
    nl = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if nl < 1e-12:                             # guards the EXACT zero (collinear/coincident vertices):
        return None                            # normalising below would divide by zero. The threshold's
                                               # value is not separately observable — anything above it
                                               # and below ~1e-12 is caught by the `det` test instead.
    n = (n[0] / nl, n[1] / nl, n[2] / nl)
    seed = [0.0, 0.0, 0.0]
    seed[min(range(3), key=lambda i: abs(n[i]))] = 1.0     # the world axis least aligned with N
    t1 = _cross(n, seed)
    t1l = math.sqrt(sum(c * c for c in t1))
    if t1l < 1e-12:
        return None
    t1 = tuple(c / t1l for c in t1)
    t2 = _cross(n, t1)
    span = max((math.dist(p, v3[0]) for p in v3[1:]), default=0.0) or 1.0
    probes = [v3[0]] + [tuple(v3[0][i] + t[i] * span for i in range(3)) for t in (t1, t2)]
    (x0, y0), (x1, y1), (x2, y2) = (world_to_pxf(p) for p in probes)
    ux, uy, vx, vy = x1 - x0, y1 - y0, x2 - x0, y2 - y0
    det = ux * vy - vx * uy
    if abs(det) < 1e-9:
        return None
    return probes, (x0, y0), (ux, uy, vx, vy), det


def _affine_on_plane(f0, f1, f2, x0, y0, ux, uy, vx, vy, det):
    """Solve `f = a*x + b*y + c` from a quantity's three probe values (`f0..f2`, at the probes
    `_plane_screen_probes` returned) and that face's screen basis. `depth`, `u` and `v` all go through
    this, so their screen gradients (`a`, `b`) are consistent — which is why §4.4's mip term is free."""
    a = ((f1 - f0) * vy - (f2 - f0) * uy) / det
    b = ((f2 - f0) * ux - (f1 - f0) * vx) / det
    return (a, b, f0 - a * x0 - b * y0)


# ----- textured face fills (`--faces textured`) ------------------------------
# The texel path builds on the SAME cull, depth buffer and occlusion `flat` uses; only the fill differs:
# each pixel samples the face's own decoded texture through its authored UV frame instead of a flat hue.
# Shade, key light, mip pick and the DEFAULT_GREY no-texture colour all match `render.rs` (`level
# preview --native`) so the two tiers agree up to f32-vs-f64 (spec §4.9): the divergences are declared,
# never accidental.

_KEY_LIGHT = (-0.408, -0.577, 0.707)   # render.rs KEY_LIGHT — un-normalized (|L| = 0.99962), abs() below
DEFAULT_GREY = (128, 128, 128)         # a poly with no `Texture` — matches render.rs's `tex_index < 0`


def _face_shade(v3) -> float | None:
    """Per-face key-light brightness for `textured`, `0.55 + 0.45*|N·L|/|N|` with `N` the world Newell
    normal (§4.1), matching `render.rs`. None for a face `render.rs` also skips — fewer than 3 vertices
    or a degenerate (zero-length) normal — which the render loop drops with no fill."""
    if len(v3) < 3:
        return None
    n = newell(v3)
    nl = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if nl <= 1e-12:
        return None
    dot = n[0] * _KEY_LIGHT[0] + n[1] * _KEY_LIGHT[1] + n[2] * _KEY_LIGHT[2]
    return 0.55 + 0.45 * abs(dot) / nl


def _mip_level(du_dx, du_dy, dv_dx, dv_dy, n_mips: int) -> int:
    """The mip index for one face from its OWN screen-space UV gradients (§4.4): the larger axis'
    texels-per-pixel, `log2`'d and clamped to the pyramid. A per-FACE quantity — a view-global
    projection gain understates it on an oblique wall (~1.7x at the default iso angle, unbounded near
    edge-on), so it is derived from these gradients, which already account for the projection."""
    texels_per_px = max(math.hypot(du_dx, du_dy), math.hypot(dv_dx, dv_dy))
    return max(0, min(n_mips - 1, int(math.floor(math.log2(max(texels_per_px, 1.0))))))


def _poly_texture_ref(poly) -> str | None:
    """A brush poly's texture ref as a bare `Package[.Group].Name`, or None when it carries no
    `Texture`. Strips a `Texture'…'` object wrapper and drops the `None` sentinel. Pure string work —
    the resolve/decode stays in dispatch; this only names the key `TextureData.by_ref` is casefolded on,
    so dispatch (building the map) and `_scene_geometry` (reading it) agree by sharing this one helper."""
    t = getattr(poly, "texture", None)
    if not t:
        return None
    m = re.search(r"'([^']*)'", t)
    ref = (m.group(1) if m else t).strip()
    return ref if ref and ref != "None" else None


def _face_uv_affine(v3, frame, world_to_pxf):
    """This face's per-pixel UV as two affine maps `(au, bu, cu)`, `(av, bv, cv)` with
    `u = au*x + bu*y + cu` (and `v` likewise), exact under ortho — no per-pixel perspective divide.
    `frame` is `(base_w, tu_w, tv_w, pan)` from `texframe.world_uv_frame`; `u(P) = dot(P-base_w, tu_w) +
    pan[0]` is affine in world P, so it solves from the SAME plane probes the depth map uses, and the
    gradients `(au, bu)`/`(av, bv)` are exactly §4.4's mip term. None when the face is edge-on. The UV is
    in MIP-0 texel units; the render loop divides by `2**level` for the chosen mip."""
    solved = _plane_screen_probes(v3, world_to_pxf)
    if solved is None:
        return None
    probes, (x0, y0), (ux, uy, vx, vy), det = solved
    base_w, tu_w, tv_w, pan = frame

    def _u(p):
        return ((p[0] - base_w[0]) * tu_w[0] + (p[1] - base_w[1]) * tu_w[1]
                + (p[2] - base_w[2]) * tu_w[2] + pan[0])

    def _v(p):
        return ((p[0] - base_w[0]) * tv_w[0] + (p[1] - base_w[1]) * tv_w[1]
                + (p[2] - base_w[2]) * tv_w[2] + pan[1])

    us = [_u(p) for p in probes]
    vs = [_v(p) for p in probes]
    return (_affine_on_plane(us[0], us[1], us[2], x0, y0, ux, uy, vx, vy, det),
            _affine_on_plane(vs[0], vs[1], vs[2], x0, y0, ux, uy, vx, vy, det))


def _fill_face_textured(buf, zbuf, size, poly_px, depth, uv, mip, masked: bool, shade: float,
                        inv: float, dim=None, dimmed: int = 0) -> None:
    """Fill one face by sampling its texture per pixel (§4.3), depth-tested exactly like `_fill_face`
    (same even-odd scanline, same strict-`<` test, same `dim` mask). `uv` is `_face_uv_affine`'s two
    affine maps in MIP-0 texel units; `inv = 1/2**level` rescales them onto the chosen `mip`
    `(w, h, rgb, mask)`. Nearest-neighbour with Euclidean wrap (Python `%` on ints). A MASKED face's
    hole texels (`mask == 0`) write neither colour nor depth, so a face behind shows through; an
    unmasked face draws index 0 as an ordinary colour. Colour is `texel * shade`, truncated as
    `render.rs`'s `(c*shade).min(255) as u8`."""
    a, b, c = depth
    (au, bu, cu), (av, bv, cv) = uv
    mw, mh, mrgb, mmask = mip
    ys = [p[1] for p in poly_px]
    n = len(poly_px)
    for y in range(max(0, math.ceil(min(ys) - 0.5)), min(size - 1, math.floor(max(ys) - 0.5)) + 1):
        yc = y + 0.5
        xs: list[float] = []
        for i in range(n):
            (ax, ay), (bx, by) = poly_px[i], poly_px[(i + 1) % n]
            if (ay <= yc) != (by <= yc):       # half-open in y: a shared vertex is counted once
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        row, ru, rv, base = b * yc + c, bu * yc + cu, bv * yc + cv, y * size
        for k in range(0, len(xs) - 1, 2):     # even-odd: fill between crossing pairs
            for x in range(max(0, math.ceil(xs[k] - 0.5)),
                           min(size - 1, math.floor(xs[k + 1] - 0.5)) + 1):
                xc = x + 0.5
                d = a * xc + row
                if d < zbuf[base + x]:
                    tx = int(math.floor((au * xc + ru) * inv)) % mw
                    ty = int(math.floor((av * xc + rv) * inv)) % mh
                    mi = ty * mw + tx
                    if masked and mmask[mi] == 0:
                        continue               # a hole writes no colour AND no depth (§4.3)
                    zbuf[base + x] = d
                    if dim is not None:
                        dim[base + x] = dimmed
                    t3 = mi * 3
                    i3 = (base + x) * 3
                    buf[i3] = min(int(mrgb[t3] * shade), 255)
                    buf[i3 + 1] = min(int(mrgb[t3 + 1] * shade), 255)
                    buf[i3 + 2] = min(int(mrgb[t3 + 2] * shade), 255)


def _fill_face(buf, zbuf, size, poly_px, depth, rgb, dim=None, dimmed: int = 0) -> None:
    """Fill one projected face into `buf`, depth-testing every pixel against `zbuf`.

    **EVEN-ODD SCANLINE, not a triangle fan.** 0.1-0.6 % of faces in real exported maps are concave
    (measured, `spikes/concave-faces/`), and a fan fills OUTSIDE those; even-odd parity handles convex
    and concave in one path. Coverage is sampled at the PIXEL CENTRE (`x+0.5`, `y+0.5`).

    **The depth test is strictly `<`, so a coplanar tie goes to whichever face was drawn FIRST** —
    iteration is scene order, which is already stable. No epsilon bias: a flush add/subtract pair is
    common pre-CSG and a bias would only move the arbitrariness. **Every filled face therefore goes
    through ONE loop in scene order**, whatever `--focus` says, or the tie-break would depend on it.

    `dim`, when given, is a per-pixel byte set to `dimmed` on each write: it remembers whether the surface
    that WON this pixel belongs to a `--focus`-de-emphasised brush, so `_fade_dimmed` can fade exactly
    those pixels afterwards without a second pass over the geometry."""
    a, b, c = depth
    ys = [p[1] for p in poly_px]
    n = len(poly_px)
    for y in range(max(0, math.ceil(min(ys) - 0.5)), min(size - 1, math.floor(max(ys) - 0.5)) + 1):
        yc = y + 0.5
        xs: list[float] = []
        for i in range(n):
            (ax, ay), (bx, by) = poly_px[i], poly_px[(i + 1) % n]
            if (ay <= yc) != (by <= yc):       # half-open in y: a shared vertex is counted once
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        row, base = b * yc + c, y * size
        for k in range(0, len(xs) - 1, 2):     # even-odd: fill between crossing pairs
            for x in range(max(0, math.ceil(xs[k] - 0.5)),
                           min(size - 1, math.floor(xs[k + 1] - 0.5)) + 1):
                d = a * (x + 0.5) + row
                if d < zbuf[base + x]:
                    zbuf[base + x] = d
                    if dim is not None:
                        dim[base + x] = dimmed
                    i3 = (base + x) * 3
                    buf[i3], buf[i3 + 1], buf[i3 + 2] = rgb


_F32 = array("f", [0.0])          # scratch: quantise a float64 depth exactly as `zbuf` stores it


def _face_is_occluded(zbuf, size, poly_px, depth) -> bool:
    """Did DEPTH hide this face — is it covered by pixels of which NONE is its own frontmost surface?

    Called once every fill is down, so `zbuf` is final. The comparison is exact rather than epsilon'd:
    `zbuf` is an `array("f")`, so the value it stored is the float32 rounding of the same float64
    expression, and `_F32` reproduces that rounding. A coplanar sibling that rounds to the same depth
    counts as frontmost too, which is right — a tie means this face is at the front as well.

    **"Covers no pixel at all" is NOT occluded, and the distinction is the whole point of the name.**
    A face thinner than a pixel centre — 4-UU trim at `--size 128`, a 16-UU cube beside an 8192-UU one —
    fills nothing, but nothing is in front of it either. Reporting it as occluded makes the caller drop its
    edges as well. Coverage loss costs a FILL; only occlusion may cost the outline too.

    **This is one HALF of the rule; the caller holds the other** (an EDGE-ON face, `plane is None`, is also
    not occluded). Neither half alone reproduces the symptom that motivated it, so each needs its own test:
    on the 4096 × 4 × 4 trim in `top` every face is either a coverage-losing cap or an edge-on side, and
    those project to the SAME 2-D lines — so the outline survives if either half is right, and the brush
    vanished only because the original single condition got both wrong at once.

    **Per FACE, not per pixel** — a partly-covered face still counts as visible. Same granularity as the
    subtract cull, and deliberately not hidden-line removal, which is a much larger renderer.

    Coverage repeats `_fill_face`'s even-odd scanline: the two must agree about which pixels a face owns,
    so the shapes are kept identical on purpose."""
    a, b, c = depth
    ys = [q[1] for q in poly_px]
    n = len(poly_px)
    covered = False
    for y in range(max(0, math.ceil(min(ys) - 0.5)), min(size - 1, math.floor(max(ys) - 0.5)) + 1):
        yc = y + 0.5
        xs: list[float] = []
        for i in range(n):
            (ax, ay), (bx, by) = poly_px[i], poly_px[(i + 1) % n]
            if (ay <= yc) != (by <= yc):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        row, base = b * yc + c, y * size
        for k in range(0, len(xs) - 1, 2):
            for x in range(max(0, math.ceil(xs[k] - 0.5)),
                           min(size - 1, math.floor(xs[k + 1] - 0.5)) + 1):
                covered = True
                _F32[0] = a * (x + 0.5) + row
                if _F32[0] == zbuf[base + x]:
                    return False                   # frontmost somewhere ⇒ visible
    return covered                                 # covered, never frontmost ⇒ depth hid it


def _fade_dimmed(buf, dim, size, alpha: float) -> None:
    """Fade every pixel `dim` marks toward `BG` at `alpha` — the `--focus` de-emphasis, applied ONCE per
    pixel after the whole scene is rasterized.

    `dim[i]` says whether the surface that WON pixel `i` belongs to a de-emphasised brush, so this is one
    blend of one resolved colour: `alpha*colour + (1-alpha)*BG`. Blending as each face rasterizes instead
    would blend once per face that passes the depth test, fading a pixel N times where N context faces
    overlap and making the result depend on face iteration order.

    **Why a mask and not two passes.** Resolving the context separately and compositing it first also gets
    one blend per pixel, but it rasterizes the de-emphasised faces BEFORE the lit ones, so a coplanar tie
    went to whichever list a face was in — i.e. `--focus` decided which of two flush surfaces you saw.
    One scene-order loop plus this mask keeps the blend single AND leaves visibility completely
    independent of what is focused. Reasoning: `dev/docs/rationale/preview.md`."""
    beta = 1.0 - alpha
    faded = BG * beta
    for i in range(size * size):
        if dim[i]:
            j = i * 3
            buf[j] = round(alpha * buf[j] + faded)
            buf[j + 1] = round(alpha * buf[j + 1] + faded)
            buf[j + 2] = round(alpha * buf[j + 2] + faded)


def _fill(buf, size, x0, y0, x1, y1, rgb) -> None:
    for y in range(min(y0, y1), max(y0, y1) + 1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            _px(buf, size, x, y, rgb)


def _box(buf, size, x0, y0, x1, y1, rgb) -> None:
    _line(buf, size, (x0, y0), (x1, y0), rgb)
    _line(buf, size, (x1, y0), (x1, y1), rgb)
    _line(buf, size, (x1, y1), (x0, y1), rgb)
    _line(buf, size, (x0, y1), (x0, y0), rgb)


def _arrowhead(buf, size, tip, from_pt, rgb, length: int = 6) -> None:
    """A small filled `>` arrowhead whose point is AT `tip`, opening back toward `from_pt`. Even a
    short leader reads unambiguously as "this label points HERE" once it ends in an arrowhead — cold
    readers reliably traced arrow-tipped leaders but read plain short stubs as mere proximity."""
    tx, ty = tip
    base_ang = math.atan2(ty - from_pt[1], tx - from_pt[0])   # direction leader→tip
    for barb in (base_ang + math.pi - 0.5, base_ang + math.pi + 0.5):   # two barbs back from the tip
        bx, by = tx + math.cos(barb) * length, ty + math.sin(barb) * length
        _line(buf, size, tip, (int(round(bx)), int(round(by))), rgb, weight=2)


def _rect_edge_toward(center, halfw: int, halfh: int, target):
    """The point on the border of a `2·halfw × 2·halfh` box (centred at `center`) that lies on the ray
    toward `target` — so a leader line starts at the box EDGE, not its centre (never running under the
    label text)."""
    cx, cy = center
    dx, dy = target[0] - cx, target[1] - cy
    if dx == 0 and dy == 0:
        return center
    sx = halfw / abs(dx) if dx else float("inf")
    sy = halfh / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return int(cx + dx * s), int(cy + dy * s)


def _label_size(text: str, scale: int) -> tuple[int, int]:
    return len(text) * (4 * scale) - scale, 5 * scale


def _draw_text(buf, size, cx, cy, text, scale, rgb) -> None:
    """Draw `text` centred at (cx, cy) in the 3×5 bitmap font."""
    gw, gh = 3 * scale, 5 * scale
    total_w = len(text) * (gw + scale) - scale
    x0, y0 = cx - total_w // 2, cy - gh // 2
    for ch in text:
        rows = _FONT.get(ch)
        if rows:
            for ry, row in enumerate(rows):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                _px(buf, size, x0 + rx * scale + dx, y0 + ry * scale + dy, rgb)
        x0 += gw + scale


def _ppm(buf: bytearray, size: int) -> bytes:
    return f"P6\n{size} {size}\n255\n".encode() + bytes(buf)


# ----- label de-collision ----------------------------------------------------

def _rects_overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _clamp(v: int, lo: int, hi: int) -> int:
    if lo > hi:           # label wider/taller than the frame — degenerate, just center it
        lo, hi = hi, lo
    return max(lo, min(v, hi))


@dataclass(kw_only=True)
class DensityGrid:
    """A coarse pixel-occupancy grid of the drawn wireframe, so label placement can flee dense regions
    (a knot where many faces overlap = high cell counts). `cells` is row-major counts; `cell_px` is the
    cell side in pixels. A mutable accumulator: built empty, then `add_segment`d per wireframe edge
    before placement. NOT fed the labels or markers themselves (label-vs-label and label-vs-marker are
    the placer's `occupied`/overlap concern)."""
    cells: list[int]
    n_cols: int
    n_rows: int
    cell_px: int

    @classmethod
    def build(cls, size: int, cell_px: int = 8) -> "DensityGrid":
        n = (size + cell_px - 1) // cell_px
        return cls(cells=[0] * (n * n), n_cols=n, n_rows=n, cell_px=cell_px)

    def _col(self, x: int) -> int:
        return min(max(x // self.cell_px, 0), self.n_cols - 1)

    def _row(self, y: int) -> int:
        return min(max(y // self.cell_px, 0), self.n_rows - 1)

    def add_segment(self, p0, p1) -> None:
        (x0, y0), (x1, y1) = p0, p1
        steps = max(abs(x1 - x0), abs(y1 - y0)) // self.cell_px + 1
        for i in range(steps + 1):
            t = i / steps
            x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
            self.cells[self._row(y) * self.n_cols + self._col(x)] += 1

    def add_box(self, rect, weight: int = 1) -> None:
        """Add a filled footprint (a point-actor marker/sprite) so labels — including brush-name
        anchors chosen by `_least_dense_anchor` — flee actor icons, not just wireframe."""
        x0, y0, x1, y1 = rect
        for row in range(self._row(y0), self._row(y1) + 1):
            for col in range(self._col(x0), self._col(x1) + 1):
                self.cells[row * self.n_cols + col] += weight

    def avg_density_in_box(self, rect) -> float:
        x0, y0, x1, y1 = rect
        c0, c1 = self._col(x0), self._col(x1)
        r0, r1 = self._row(y0), self._row(y1)
        total = count = 0
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                total += self.cells[row * self.n_cols + col]
                count += 1
        return total / count if count else 0.0


@dataclass(frozen=True, kw_only=True)
class _LabelItem:
    """One label to place: its `anchor` (the true PIXEL point it belongs to), `text`, font `scale`,
    and draw `color`. Used ONLY for actor NAMES on the legacy (non-hybrid) on-geometry path — poly
    indices are painted on-face (`_plan_onface_texture`), never placed here."""
    anchor: tuple[int, int]
    text: str
    scale: int
    color: tuple[int, int, int]


@dataclass(frozen=True, kw_only=True)
class _PlacedLabel:
    """A `_LabelItem` after de-collision: `pos` is the nudged box centre where the text is drawn;
    `anchor` is the original (unclamped) point the leader/arrow points back at."""
    anchor: tuple[int, int]
    pos: tuple[int, int]
    text: str
    scale: int
    color: tuple[int, int, int]


# Cost weights (k1 geometry density, k2 label overlap, k3 leader length). k2 dominates so labels
# effectively never stack; k3 keeps them near their anchor (a moderate drift cap) so they cross into
# clear space only when the local geometry cost outweighs a short leader. Validated by eye on
# representative scenes (rooms, pillar halls, the showcase archetypes); not auto-tuned.
_LABEL_WEIGHTS = (1.0, 50.0, 3.0)


def _occluder_count(centroid2d, depth: float, occluders: list, *, own_brush: str) -> int:
    """How many front faces are IN FRONT of this face and count as occluders: a front face G (in
    `occluders` as `(poly2d, depth, brush_name, is_solid)`) occludes face F iff G is nearer the camera
    (smaller depth), its projection covers F's centroid, AND either G's brush is a SOLID CSG op OR G
    belongs to the SAME brush as F (`own_brush`). The same-brush arm gives a subtract/hollow room
    depth grading off its OWN near walls (self-occlusion) without a room dimming other brushes sitting
    inside it; solids still occlude across brushes. Drives the graded on-face decal opacity — each such
    layer attenuates the number like a stacked 50%-opaque pane. `1e-3` keeps a face from counting
    itself / a coplanar neighbour."""
    return sum(1 for opoly, odepth, obrush, osolid in occluders
               if odepth < depth - 1e-3 and (osolid or obrush == own_brush)
               and _point_in_poly(centroid2d, opoly))


def _decal_opacity(n_front: int) -> float:
    """On-face number opacity from the count of faces IN FRONT of it (`_occluder_count`): a
    decoupled "front stays clear" form `0.56 * 0.6 ** n_front`, so a VISIBLE face (0 in front) is 0.56,
    one layer behind 0.336, two behind 0.20 — the primary numbers stay legible but let the surface show
    through, while each occluding layer retains 60% of the one behind it for a front/back split. Floored
    at 0.12 so a deeply-buried number never fully vanishes."""
    return max(0.12, 0.56 * 0.6 ** n_front)


_DIM_ALPHA = 0.15   # `--focus`/`--breakdown` draw a non-focused brush's wireframe at this opacity
                    # (COMPOSITED, so crossed edges/numbers show through) — 0.15 over the light bg
                    # matches the old fade-toward-bg look but no longer hard-overwrites at crossings.

# A filled mode's non-focused FILLS composite at this opacity — separate from `_DIM_ALPHA`, which dims
# thin LINES, where a faint stroke still reads as a stroke. THE OWNER'S VALUE, picked from a ladder of
# real renders rather than arithmetic: do NOT retune it from a contrast formula, re-run the ladder
# (`dev/docs/spikes/2026-07-27-preview-focus-dim/`). Why, and why not 0.15: `rationale/preview.md`.
_DIM_FILL_ALPHA = 0.35


def _fade(rgb: tuple[int, int, int], amount: float = 0.6) -> tuple[int, int, int]:
    """Blend a colour `amount` of the way toward the background — a dimmed SHADE (still opaque). Used for
    the `brush_colors=legend` back-face tint; the `--focus` dimming is now a composite `_DIM_ALPHA`
    instead (see `_scene_geometry`), so a faint brush no longer covers the edges/numbers it crosses."""
    return tuple(round(c + (BG - c) * amount) for c in rgb)


def _least_dense_anchor(grid: "DensityGrid", cands_px: list, halfbox: int):
    """Of candidate PIXEL points (a brush's own projected wireframe VERTICES), the one sitting in the
    least-dense grid region. Anchoring a brush's name at a clear outer CORNER (rather than an edge
    midpoint or the centroid) reads as "this whole shape" and keeps it off the crowded centre — and,
    since every candidate is a real vertex, never in the hollow interior of a concave/subtract brush.
    Ties resolve to the first candidate (deterministic given candidate order)."""
    return min(cands_px, key=lambda q: grid.avg_density_in_box(
        (q[0] - halfbox, q[1] - halfbox, q[0] + halfbox, q[1] + halfbox)))


def _place_labels(items: list[_LabelItem], size: int, *, grid=None, occupied=(),
                  weights=_LABEL_WEIGHTS) -> list[_PlacedLabel]:
    """De-collide a mixed set of LABELS — drawn text boxes, the placement half of an annotation (see
    the module docstring). Each label's box centre is nudged off its anchor onto a ring
    position; the anchor stays the true (unclamped) spot so the leader points at it, and positions are
    clamped inside `[0, size)`. `occupied` seeds the placed-rect set with non-label footprints (point
    markers / sprites) so labels don't land on top of them.

    Placement minimises a cost per candidate. With no `grid` it is pure occupancy de-collision (first
    collision-free ring slot, else least-overlapping — the historical behaviour). With a `grid` (an
    occupancy grid of the wireframe only — markers are handled via `occupied`) the cost also flees
    dense geometry and penalises leader length: `k1·avg_density + k2·overlap + k3·(leader_px/cell)`."""
    k1, k2, k3 = weights
    placed: list = list(occupied)
    out: list[_PlacedLabel] = []
    # Deterministic order: with a grid, place the most-crowded anchors first (while clear space is
    # still plentiful); tie-break by text then anchor so the result is reproducible. Without a grid,
    # keep input order (the historical greedy behaviour).
    order = items
    if grid is not None:
        order = sorted(items, key=lambda it: (
            -grid.avg_density_in_box((it.anchor[0], it.anchor[1], it.anchor[0], it.anchor[1])),
            it.text, it.anchor))
    for item in order:
        (ax, ay) = item.anchor
        w, h = _label_size(item.text, item.scale)
        hw, hh = w // 2 + 3, h // 2 + 3
        step = max(10, 6 * item.scale)
        # No (0,0): every label is nudged at least one step off its anchor, so a dot-on-target + leader
        # line ALWAYS draw (cold readers could not attach an un-leadered label — it read as proximity
        # guesswork). The box floats above its anchor by default (first ring position), fanning out only
        # to de-collide / flee density.
        rings = [(0, -step)]
        for rad in (1, 2, 3, 4, 5):
            d = rad * step
            rings += [(0, -d), (d, -d), (-d, -d), (d, 0), (-d, 0), (d, d), (-d, d), (0, d)]
        best_cost = best_rect = best_pos = None
        for ox, oy in rings:
            lx = _clamp(ax + ox, hw, size - 1 - hw)
            ly = _clamp(ay + oy, hh, size - 1 - hh)
            rect = (lx - hw, ly - hh, lx + hw, ly + hh)
            overlaps = sum(1 for r in placed if _rects_overlap(rect, r))
            if grid is None:
                if overlaps == 0:                      # greedy fast path: first free slot wins
                    best_rect, best_pos = rect, (lx, ly)
                    break
                cost = float(overlaps)
            else:
                leader = ((lx - ax) ** 2 + (ly - ay) ** 2) ** 0.5 / grid.cell_px
                cost = k1 * grid.avg_density_in_box(rect) + k2 * overlaps + k3 * leader
            if best_cost is None or cost < best_cost:
                best_cost, best_rect, best_pos = cost, rect, (lx, ly)
        placed.append(best_rect)
        out.append(_PlacedLabel(anchor=(ax, ay), pos=best_pos, text=item.text, scale=item.scale,
                                color=item.color))
    return out


# ----- on-face PAINTED ("decal") poly-index rendering --------------------------
# This is the SOLE way `actor preview` labels poly faces: paint the face's INDEX flat IN the face's own
# 3-D plane, projected with the SAME `_project` as the wireframe, so it reads as painted ON the surface.
# The in-plane basis is anchored to WORLD-UP (not a face edge — an edge shears to an italic under
# projection): Vw (text-up) = world +Z projected into the face plane, so on a vertical wall the vertical
# strokes run straight up the wall while the width recedes along it; Uw (text-right) = N × Vw with N the
# CAMERA-FACING normal, so the glyph is never mirrored. Texels are SQUARE in world units and sized to the
# largest that fits the projected face; each texel's 3-D point (centroid + u·Uw + v·Vw) is projected and
# the glyph is inverse-mapped for gap-free fill. A number whose projected texels are too small to READ
# ON SCREEN is OMITTED (view-DEPENDENT) — there is NO leader-box fallback (the leader path is gone for polys).


_DECAL_SLOT_DIGITS = 2   # a number is sized/placed as if it were this many digits wide, then the actual
                         # (possibly shorter) number is centred in that slot — so a lone `5` renders at
                         # the same scale as `12`, for a neater, size-consistent look across a scene


def _text_bitmap(text: str, *, slot_digits: int = _DECAL_SLOT_DIGITS
                 ) -> tuple[tuple[tuple[bool, ...], ...], int, int]:
    """Render `text` into a dense boolean texel grid in the 3×5 `_FONT` (1-col gaps), plus a blank row and
    an UNDERLINE bar (under the digits) below the baseline. The grid is widened to a `slot_digits`-wide
    SLOT (min) and the actual text CENTRED in it, so single- and double-digit numbers get the same box
    aspect → the same size/placement (the extra slot columns stay blank; only the digits + their
    underline are painted). Returns `(grid, cols, rows)`; `rows` = 5 digit rows + 1 blank + 1 underline =
    7. The underline rides the face's own frame (along Uw) as a 6/9 cue."""
    glyphs = [_FONT.get(ch) or ["000", "000", "000", "000", "000"] for ch in text]
    text_cols = max(1, len(text) * 4 - 1)
    cols = max(text_cols, slot_digits * 4 - 1)          # reserve a `slot_digits`-wide slot
    x0 = (cols - text_cols) // 2                         # centre the actual number in the slot
    grid = [[False] * cols for _ in range(7)]
    x = x0
    for g in glyphs:
        for r in range(5):
            for c in range(3):
                if g[r][c] == "1":
                    grid[r][x + c] = True
        x += 4
    for c in range(x0, x0 + text_cols):                 # underline spans the DIGITS, not the blank slot
        grid[6][c] = True
    return tuple(tuple(row) for row in grid), cols, 7


def _face_decal_basis(v3, world_to_pxf):
    """The in-plane world frame `(Cw, Uw, Vw)` for painting text flat ON a face — Cw the 3-D centroid,
    Vw text-up, Uw text-right.

    NON-horizontal faces (walls, slopes): Vw = world +Z projected into the plane (exactly +Z on a
    vertical wall, so strokes stand straight up the wall — numbers hang by GRAVITY, consistent in any
    view); Vw is flipped to project upward and Uw = the in-plane ⟂ to Vw.

    HORIZONTAL faces (floor / ceiling / cap, normal ≈ ±Z — no in-plane gravity-up): the basis is fixed to
    the WORLD axes — Vw = world +Y (top), Uw = world +X (right) — so every cap number is consistently
    Y-aligned instead of an arbitrary roll.

    In BOTH cases Uw's sign is fixed from the SCREEN projection so the `(Uw, Vw)` frame is right-reading
    (screen cross < 0, pixel-y down) — never mirrored (e.g. a ceiling normal −Z). None if degenerate."""
    nx, ny, nz = newell(v3)
    nl = math.sqrt(nx * nx + ny * ny + nz * nz)
    if nl < 1e-9:
        return None
    n = (nx / nl, ny / nl, nz / nl)
    o = v3[0]
    s0 = world_to_pxf(o)

    def sdelta(w):
        p = world_to_pxf((o[0] + w[0], o[1] + w[1], o[2] + w[2]))
        return (p[0] - s0[0], p[1] - s0[1])

    d = n[2]                                        # up·N with up=(0,0,1)
    vw = (-d * n[0], -d * n[1], 1.0 - d * n[2])     # world-up projected into the plane
    vl = math.sqrt(sum(t * t for t in vw))
    if vl < 1e-3:                                   # HORIZONTAL face → world-axis basis: up +Y, right +X
        uw, vw = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    else:                                           # wall / slope → gravity (world-up) basis
        vw = (vw[0] / vl, vw[1] / vl, vw[2] / vl)
        if sdelta(vw)[1] > 0:                       # Vw projects DOWNWARD → flip so text isn't upside down
            vw = (-vw[0], -vw[1], -vw[2])
        uw = (n[1] * vw[2] - n[2] * vw[1], n[2] * vw[0] - n[0] * vw[2], n[0] * vw[1] - n[1] * vw[0])
        ul = math.sqrt(sum(t * t for t in uw))
        if ul < 1e-9:
            return None
        uw = (uw[0] / ul, uw[1] / ul, uw[2] / ul)
    a, b = sdelta(uw), sdelta(vw)                   # projected basis; enforce right-reading orientation
    if a[0] * b[1] - a[1] * b[0] >= 0:              # screen cross ≥ 0 (pixel-y down) ⇒ mirrored → flip Uw
        uw = (-uw[0], -uw[1], -uw[2])
    m = len(v3)
    cw = (sum(p[0] for p in v3) / m, sum(p[1] for p in v3) / m, sum(p[2] for p in v3) / m)
    return cw, uw, vw


@dataclass(frozen=True, kw_only=True)
class _DecalPlan:
    """A planned painted decal: the glyph→screen affine (top-left texel corner `tl`, per-column screen
    step `ex`, per-row downward step `ey`) plus the texel `bitmap`. Screen point of texel `(col, row)` =
    `tl + col·ex + row·ey`; drawing inverse-maps each covered pixel back to a texel (gap-free)."""
    tl: tuple[float, float]
    ex: tuple[float, float]
    ey: tuple[float, float]
    bitmap: tuple[tuple[bool, ...], ...]
    cols: int
    rows: int

    def _corners(self):
        cx, cy = self.cols, self.rows
        return [self.tl,
                (self.tl[0] + cx * self.ex[0], self.tl[1] + cx * self.ex[1]),
                (self.tl[0] + cy * self.ey[0], self.tl[1] + cy * self.ey[1]),
                (self.tl[0] + cx * self.ex[0] + cy * self.ey[0],
                 self.tl[1] + cx * self.ex[1] + cy * self.ey[1])]

    def bbox(self) -> tuple[int, int, int, int]:
        cs = self._corners()
        return (int(math.floor(min(p[0] for p in cs))), int(math.floor(min(p[1] for p in cs))),
                int(math.ceil(max(p[0] for p in cs))), int(math.ceil(max(p[1] for p in cs))))


# THE ONE RULE for on-face numbers. A face's index is a texture painted IN the face plane at the
# ROOMIEST spot (the largest glyph-box that fits INSIDE the face polygon — off-centre on an irregular
# face), sized to 0.75 of that maximum, foreshortening naturally under projection. It is OMITTED only
# when it would be UNREADABLE ON SCREEN — i.e. the projected glyph texels fall below a min pixel size —
# so numbering is VIEW-DEPENDENT: a face too small/edge-on/zoomed-out to read gets no number, and the
# SAME face gets one once it's big enough on screen (zoomed in, or in its own `--breakdown` pane).
_ONFACE_FILL = 0.75            # the decal is this fraction of the LARGEST glyph-box that fits the face
_ONFACE_MIN_TEXEL_PX = 2.0     # min PROJECTED px per glyph texel to be readable; below this → omit
# Reshuffle to dodge overlap is deliberately TINY: a number may shrink at most this LINEAR fraction and
# move at most this fraction of its own screen diagonal. Beyond that it stays put and overlaps — the
# overlap KEYLINE (below), not repositioning, is what keeps overlapping numbers legible.
_DECAL_MAX_SHRINK = 0.10
_DECAL_MAX_MOVE_FRAC = 0.10
_RESHUFFLE_SCALES = (0.975, 0.95, 0.925, 0.90)   # near-full sizes offered for the nudge (candidate 0 = 1.0)
_KEYLINE_RGB = (255, 255, 255)   # a CONSTANT 1-screen-px ring drawn just OUTSIDE overlapping numbers


def _poly_is_convex_2d(poly) -> bool:
    """True iff the 2-D polygon (list of `(u, v)`) is convex — the cross products of consecutive edges
    all share one sign (collinear runs ignored). UE1 brush faces are convex by convention but arbitrary
    vertex editing CAN make one concave (measured 0.1-0.6% of faces in real exported maps — see
    `spikes/concave-faces/`), so callers must handle both (see `_max_inscribed_box`)."""
    n = len(poly)
    if n < 4:
        return True
    sign = 0
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        cx, cy = poly[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cross) > 1e-9:
            s = 1 if cross > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
    return True


def _clip_ge(poly, n, b):
    """Sutherland-Hodgman clip of convex `poly` to the half-plane `{p : n·p >= b}` (n a 2-vector)."""
    out = []
    m = len(poly)
    for i in range(m):
        a = poly[i]
        c = poly[(i + 1) % m]
        da = n[0] * a[0] + n[1] * a[1] - b
        dc = n[0] * c[0] + n[1] * c[1] - b
        if da >= 0:
            out.append(a)
        if (da >= 0) != (dc >= 0):
            t = da / (da - dc)
            out.append((a[0] + t * (c[0] - a[0]), a[1] + t * (c[1] - a[1])))
    return out


def _seg_cross(a, b, c, d) -> bool:
    """Conservative crossing test for segments a-b and c-d (used to check a box edge against a face
    edge). True when they straddle each other by orientation sign; a T-junction (an endpoint lying ON
    the other segment) also reads True. That's the safe direction here — over-rejecting a tangent box
    is absorbed by drawing at 0.75× — so it is NOT a strict proper-intersection test."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _box_fits_2d(cu, cv, hw, hh, poly) -> bool:
    """True iff the UV-axis-aligned box centred at `(cu, cv)` with half-extents `(hw, hh)` lies fully
    inside the simple polygon `poly` — all four corners inside AND no face edge crosses a box edge (the
    edge test also rules out a face vertex poking into the box). Works for convex OR concave `poly`."""
    corners = [(cu - hw, cv - hh), (cu + hw, cv - hh), (cu + hw, cv + hh), (cu - hw, cv + hh)]
    if not all(_point_in_poly(p, poly) for p in corners):
        return False
    box_edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    m = len(poly)
    for i in range(m):
        pa, pb = poly[i], poly[(i + 1) % m]
        if any(_seg_cross(pa, pb, ba, bb) for ba, bb in box_edges):
            return False
    return True


def _erode_convex(poly, hw, hh):
    """The convex polygon `poly` eroded inward by an axis-aligned box of half-extents `(hw, hh)`: the set
    of box CENTRES at which the box fits fully inside `poly` (Minkowski erosion — shift each edge inward
    by its support `hw·|nx| + hh·|ny|` and intersect). Returns the eroded polygon, or None if it collapses
    (the box is too big to fit anywhere). Normals/offsets come from the ORIGINAL poly; only the clipped
    region accumulates — so the result is independent of edge order."""
    m = len(poly)
    cx = sum(p[0] for p in poly) / m
    cy = sum(p[1] for p in poly) / m
    region = poly
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        nx, ny = -(b[1] - a[1]), (b[0] - a[0])
        ln = math.hypot(nx, ny) or 1.0
        nx, ny = nx / ln, ny / ln
        if nx * (cx - a[0]) + ny * (cy - a[1]) < 0:          # point it INWARD (toward the centroid)
            nx, ny = -nx, -ny
        region = _clip_ge(region, (nx, ny), nx * a[0] + ny * a[1] + hw * abs(nx) + hh * abs(ny))
        if len(region) < 3:
            return None
    return region


def _concave_center_seeds(poly):
    """Candidate box-centre seeds for a CONCAVE face: a uniform grid over the UV bbox PLUS each vertex and
    edge-midpoint nudged 5% toward the centroid. A narrow lobe (a fat pocket on a thin neck) can sit
    entirely between grid nodes, so the grid alone would miss it; the vertex/edge seeds land inside such
    pockets. Caller filters these by `_box_fits_2d` for the box size it wants."""
    us = [p[0] for p in poly]
    vs = [p[1] for p in poly]
    umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
    cx, cy = sum(us) / len(poly), sum(vs) / len(poly)
    grid = 12
    seeds = [(umin + (umax - umin) * i / grid, vmin + (vmax - vmin) * j / grid)
             for i in range(grid + 1) for j in range(grid + 1)]
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        for p in (a, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)):
            seeds.append((p[0] + (cx - p[0]) * 0.05, p[1] + (cy - p[1]) * 0.05))
    return seeds


def _feasible_centers(poly, hw, hh):
    """A list of UV centres at which an axis-aligned box of half-extents `(hw, hh)` fits inside `poly` — a
    MODEST spread the decal resolver can slide a decal across without leaving its face. Convex: the eroded
    region's centroid FIRST, then each eroded-region vertex nudged 5% inward. Concave: the feasible subset
    of `_concave_center_seeds` (`_box_fits_2d`). Empty when nothing fits."""
    if _poly_is_convex_2d(poly):
        region = _erode_convex(poly, hw, hh)
        if region is None:
            return []
        rx = sum(p[0] for p in region) / len(region)
        ry = sum(p[1] for p in region) / len(region)
        return [(rx, ry)] + [(p[0] + (rx - p[0]) * 0.05, p[1] + (ry - p[1]) * 0.05) for p in region]
    return [(cu, cv) for cu, cv in _concave_center_seeds(poly) if _box_fits_2d(cu, cv, hw, hh, poly)]


def _max_inscribed_box(poly, cols, rows):
    """The LARGEST UV-axis-aligned box of the glyph's aspect (`cols`×`rows` texels) that fits fully
    inside face polygon `poly` (a list of `(u, v)` world coords), and WHERE its centre sits. Returns
    `(center=(u, v), cell)` where `cell` is world units per texel at that maximum (or `(None, 0.0)` if
    nothing fits). For a rectangular face this is the centred box limited by the tighter dimension; for
    a triangle/trapezoid/L it finds the roomiest OFF-centre spot. Convex faces solve exactly by eroding
    the polygon by the box (shift each edge inward by the box's support, intersect) under a binary search
    on `cell`; concave faces (rare) fall back to a bounded grid × binary search."""
    us = [p[0] for p in poly]
    vs = [p[1] for p in poly]
    cell_hi = max((max(us) - min(us)) / cols, (max(vs) - min(vs)) / rows)   # cell can't exceed this
    if cell_hi <= 0:
        return (None, 0.0)
    if _poly_is_convex_2d(poly):
        best = None
        lo, hi = 0.0, cell_hi
        for _ in range(24):                          # binary search the largest feasible cell
            mid = (lo + hi) / 2.0
            region = _erode_convex(poly, cols * mid / 2.0, rows * mid / 2.0)
            if region is not None:
                best = (sum(p[0] for p in region) / len(region),
                        sum(p[1] for p in region) / len(region))
                lo = mid
            else:
                hi = mid
        return (best, lo) if best is not None else (None, 0.0)
    # concave: each seed centre × binary search on cell (the grid+vertex seeds cover narrow lobes).
    best_c, best_cell = None, 0.0
    for cu, cv in _concave_center_seeds(poly):
        if not _point_in_poly((cu, cv), poly):
            continue
        lo, hi = 0.0, cell_hi
        for _ in range(18):
            mid = (lo + hi) / 2.0
            if _box_fits_2d(cu, cv, cols * mid / 2.0, rows * mid / 2.0, poly):
                lo = mid
            else:
                hi = mid
        if lo > best_cell:
            best_c, best_cell = (cu, cv), lo
    return (best_c, best_cell)


def _face_poly_uv(v3, basis):
    """Project face vertices `v3` (world 3-D) into the face's own in-plane UV coords, given its
    `basis = (Cw, Uw, Vw)` from `_face_decal_basis`."""
    cw, uw, vw = basis
    return [((p[0] - cw[0]) * uw[0] + (p[1] - cw[1]) * uw[1] + (p[2] - cw[2]) * uw[2],
             (p[0] - cw[0]) * vw[0] + (p[1] - cw[1]) * vw[1] + (p[2] - cw[2]) * vw[2]) for p in v3]


def _decal_plan_at(basis, center_uv, cell, bitmap, cols, rows, world_to_pxf, *,
                   min_texel_px: float = _ONFACE_MIN_TEXEL_PX) -> "_DecalPlan | None":
    """Build the glyph→screen affine for a decal of `cell` world-units/texel centred at `center_uv` (UV
    coords in the face's `basis`), or None if the projected texel is below `min_texel_px` (UNREADABLE ON
    SCREEN → omit)."""
    cw, uw, vw = basis
    cu, cv = center_uv
    wc = (cw[0] + cu * uw[0] + cv * vw[0], cw[1] + cu * uw[1] + cv * vw[1], cw[2] + cu * uw[2] + cv * vw[2])
    s0 = world_to_pxf(wc)

    def sdelta(w):
        p = world_to_pxf((wc[0] + w[0], wc[1] + w[1], wc[2] + w[2]))
        return (p[0] - s0[0], p[1] - s0[1])

    A, B = sdelta(uw), sdelta(vw)                   # screen delta per unit-world Uw / Vw (foreshortens)
    ex, ey = (cell * A[0], cell * A[1]), (-cell * B[0], -cell * B[1])   # projected px per glyph texel
    if min(math.hypot(*ex), math.hypot(*ey)) < min_texel_px:    # texel too small on screen → unreadable → omit
        return None
    hw, hh = cols * cell / 2.0, rows * cell / 2.0
    tl = world_to_pxf((wc[0] - hw * uw[0] + hh * vw[0], wc[1] - hw * uw[1] + hh * vw[1],
                       wc[2] - hw * uw[2] + hh * vw[2]))         # top-left texel corner: −Uw half, +Vw half
    return _DecalPlan(tl=tl, ex=ex, ey=ey, bitmap=bitmap, cols=cols, rows=rows)


def _plan_onface_texture(v3, world_to_pxf, text: str, *, fill: float = _ONFACE_FILL,
                         min_texel_px: float = _ONFACE_MIN_TEXEL_PX) -> "_DecalPlan | None":
    """Plan the painted number texture for a face at its ROOMIEST spot, or None if UNREADABLE ON SCREEN.
    Builds the in-plane frame (`_face_decal_basis`), projects the face to its UV plane, then
    `_max_inscribed_box` finds the LARGEST glyph-box that fits INSIDE the face polygon and WHERE it sits
    (off-centre on a non-rectangular face); the decal is drawn at `fill` (0.75) of that maximum. This is
    exactly candidate 0 of `_onface_candidates` — a single fixed placement, ignoring overlap."""
    basis = _face_decal_basis(v3, world_to_pxf)
    if basis is None:
        return None
    bitmap, cols, rows = _text_bitmap(text)
    center_uv, max_cell = _max_inscribed_box(_face_poly_uv(v3, basis), cols, rows)
    if center_uv is None or max_cell <= 0:                     # nothing fits inside the face
        return None
    return _decal_plan_at(basis, center_uv, fill * max_cell, bitmap, cols, rows, world_to_pxf,
                          min_texel_px=min_texel_px)


def _plan_key(plan: "_DecalPlan"):
    """A rounded identity for a `_DecalPlan` — its FULL screen affine (tl, both ex/ey components) plus
    aspect — so `_onface_candidates` dedups only truly-coincident placements, correct even under an
    oblique projection where `ex`/`ey` are not axis-aligned."""
    return (round(plan.tl[0], 3), round(plan.tl[1], 3), round(plan.ex[0], 3), round(plan.ex[1], 3),
            round(plan.ey[0], 3), round(plan.ey[1], 3), plan.cols)


def _onface_candidates(v3, world_to_pxf, text: str, *, fill: float = _ONFACE_FILL,
                       min_texel_px: float = _ONFACE_MIN_TEXEL_PX) -> "list[_DecalPlan]":
    """The placements the resolver may choose from for one face: candidate 0 FIRST (== `_plan_onface_texture`,
    the full-size roomiest spot), then only NEAR-FULL nudges — `_RESHUFFLE_SCALES` (down to ≤10% smaller),
    each with its feasible centres. Reshuffle is deliberately minimal, so there is NO deep size ladder and
    NO rotation; overlapping numbers stay big and the overlap keyline keeps them legible. Every placement
    keeps candidate 0's `fill` (0.75) edge padding (centres clear the max box the decal is 0.75 of, not the
    bare decal), so a nudged number never sits flush. Empty (face omitted) when candidate 0 is None."""
    basis = _face_decal_basis(v3, world_to_pxf)
    if basis is None:
        return []
    poly_uv = _face_poly_uv(v3, basis)
    bmp, cols, rows = _text_bitmap(text)
    center0, max0 = _max_inscribed_box(poly_uv, cols, rows)
    if center0 is None or max0 <= 0:
        return []
    c0 = _decal_plan_at(basis, center0, fill * max0, bmp, cols, rows, world_to_pxf, min_texel_px=min_texel_px)
    if c0 is None:                                              # unreadable → omitted (candidate 0 gates it)
        return []
    cands = [c0]
    seen = {_plan_key(c0)}
    for s in _RESHUFFLE_SCALES:                                 # near-full nudge sizes; centroid + slid
        cell = s * fill * max0
        for cu, cv in _feasible_centers(poly_uv, cols * (cell / fill) / 2.0, rows * (cell / fill) / 2.0):
            plan = _decal_plan_at(basis, (cu, cv), cell, bmp, cols, rows, world_to_pxf, min_texel_px=min_texel_px)
            if plan is None:
                continue
            key = _plan_key(plan)
            if key not in seen:
                seen.add(key)
                cands.append(plan)
    return cands


def _plan_px_area(plan: "_DecalPlan") -> float:
    """The decal's projected on-screen area in px² (the glyph parallelogram) — the resolver's size score:
    among near-full nudges it prefers the largest that reduces overlap."""
    ex, ey = plan.ex, plan.ey
    return plan.cols * plan.rows * abs(ex[0] * ey[1] - ey[0] * ex[1])


def _rect_overlap_area(box, others) -> int:
    """Total px² by which axis-aligned `box` overlaps the rects in `others`, SUMMED PER RECT — so a region
    covered by N others counts N times (3 decals stacked on the same 10%-of-area patch ⇒ 20% overlap, not
    10%): stacked collisions are worse and the resolver should treat them so. Disjoint pairs contribute 0."""
    x0, y0, x1, y1 = box
    total = 0
    for ox0, oy0, ox1, oy1 in others:
        ix = min(x1, ox1) - max(x0, ox0)
        iy = min(y1, oy1) - max(y0, oy0)
        if ix > 0 and iy > 0:
            total += ix * iy
    return total


def _overlap_fraction(box, others) -> float:
    """`_rect_overlap_area` as a fraction of `box`'s own area (summed per rect, so it can exceed 1.0 when
    layers stack). 0.0 for a degenerate (zero-area) box."""
    area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    return _rect_overlap_area(box, others) / area if area > 0 else 0.0


def _resolve_decals(entries, obstacles):
    """Greedy deterministic placement with a TRULY MINIMAL anti-overlap nudge. `entries` is a list of
    `(order_key, candidates)` where `candidates[0]` is the full-size roomiest placement; `obstacles` are
    fixed rects (point-actor markers, legend). Returns the chosen `_DecalPlan` per entry (aligned to input
    order; None when an entry has no candidates). Biggest-primary entries place first. A candidate 0 with
    NO overlap is kept VERBATIM (so clean scenes render exactly as the single-placement planner would).
    On overlap, the pick is restricted to candidates within the reshuffle budget — no more than
    `_DECAL_MAX_SHRINK` smaller AND whose centre moves no more than `_DECAL_MAX_MOVE_FRAC` of candidate 0's
    screen diagonal — and among those takes the LEAST overlap, then the largest, then the earliest. So a
    number barely moves/shrinks; the overlap KEYLINE (drawn separately) carries the residual overlap."""
    chosen: list = [None] * len(entries)
    occ = list(obstacles)
    for idx in sorted(range(len(entries)), key=lambda i: entries[i][0]):
        cands = entries[idx][1]
        if not cands:
            continue
        boxes = [c.bbox() for c in cands]
        if _overlap_fraction(boxes[0], occ) <= 0:
            pick, pbox = cands[0], boxes[0]
        else:
            area0 = _plan_px_area(cands[0])
            min_area = ((1.0 - _DECAL_MAX_SHRINK) ** 2) * area0                 # ≤10% linear shrink
            cx0 = (boxes[0][0] + boxes[0][2]) / 2.0
            cy0 = (boxes[0][1] + boxes[0][3]) / 2.0
            move_cap = _DECAL_MAX_MOVE_FRAC * math.hypot(boxes[0][2] - boxes[0][0],
                                                         boxes[0][3] - boxes[0][1])
            allowed = [k for k in range(len(cands))
                       if _plan_px_area(cands[k]) >= min_area
                       and math.hypot((boxes[k][0] + boxes[k][2]) / 2.0 - cx0,
                                      (boxes[k][1] + boxes[k][3]) / 2.0 - cy0) <= move_cap]
            j = min(allowed, key=lambda k: (_overlap_fraction(boxes[k], occ), -_plan_px_area(cands[k]), k))
            pick, pbox = cands[j], boxes[j]
        chosen[idx] = pick
        occ.append(pbox)
    return chosen


def _blend_px(buf, size, x, y, rgb, alpha: float = 0.5) -> bool:
    """Alpha-blend `rgb` OVER the pixel already in the buffer, i.e.
    `new = round(alpha*rgb + (1-alpha)*existing)`. Lets an on-face digit read as a TRANSLUCENT overlay —
    the surface/wireframe under it shows through, like a real decal — instead of an opaque knockout."""
    if 0 <= x < size and 0 <= y < size:
        i = (y * size + x) * 3
        beta = 1.0 - alpha
        buf[i] = round(alpha * rgb[0] + beta * buf[i])
        buf[i + 1] = round(alpha * rgb[1] + beta * buf[i + 1])
        buf[i + 2] = round(alpha * rgb[2] + beta * buf[i + 2])
        return True
    return False


def _draw_painted_decal(buf, size, plan: "_DecalPlan", tint, *,
                        alpha: float = 0.7, halo_alpha: float | None = None) -> "set[tuple[int, int]]":
    """Paint a planned decal flat on its face: inverse-map every pixel of the glyph's projected
    parallelogram back to a texel, collect the 'on' pixels, then blend a faint translucent halo around
    them (default `0.5·alpha`) and the `tint` texels on top, both at `alpha` — the graded opacity
    (`_decal_opacity`), so a deeper face's number is fainter and the surface shows through. Returns the
    set of 'on' (glyph) screen pixels so the caller can find where numbers OVERLAP (for the keyline)."""
    if halo_alpha is None:
        halo_alpha = 0.5 * alpha
    ex, ey = plan.ex, plan.ey
    det = ex[0] * ey[1] - ey[0] * ex[1]
    if abs(det) < 1e-9:
        return set()
    inv = (ey[1] / det, -ey[0] / det, -ex[1] / det, ex[0] / det)
    x0, y0, x1, y1 = plan.bbox()
    on: set[tuple[int, int]] = set()
    for y in range(max(0, y0), min(size, y1 + 1)):
        for x in range(max(0, x0), min(size, x1 + 1)):
            dx, dy = x + 0.5 - plan.tl[0], y + 0.5 - plan.tl[1]
            gi = int(math.floor(inv[0] * dx + inv[1] * dy))
            gj = int(math.floor(inv[2] * dx + inv[3] * dy))
            if 0 <= gj < plan.rows and 0 <= gi < plan.cols and plan.bitmap[gj][gi]:
                on.add((x, y))
    halo = {(x + dx, y + dy) for x, y in on for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - on
    for x, y in halo:
        _blend_px(buf, size, x, y, WHITE, halo_alpha)
    for x, y in on:
        _blend_px(buf, size, x, y, tint, alpha)
    return on


def _draw_overlap_keyline(buf, size, on_sets) -> None:
    """Where two on-face numbers OVERLAP on screen, outline the involved glyphs so the reader can still
    tell the shapes apart. The keyline is a CONSTANT 1-screen-pixel ring drawn just OUTSIDE each glyph's
    strokes (the 4-neighbour dilation of its 'on' set minus the set), restricted to pixels near an
    overlap. Constant width means it never fills a thin stroke and never thickens with zoom. `on_sets` is
    the per-number 'on' pixel sets from `_draw_painted_decal`, in draw order."""
    cover: dict = {}
    for on in on_sets:
        for px in on:
            cover[px] = cover.get(px, 0) + 1
    overlap = {p for p, n in cover.items() if n >= 2}
    if not overlap:
        return
    near = {(x + dx, y + dy) for (x, y) in overlap for dx in range(-2, 3) for dy in range(-2, 3)}
    for on in on_sets:
        ring = {(x + dx, y + dy) for (x, y) in on
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - on
        for x, y in (ring & near):
            if 0 <= x < size and 0 <= y < size:
                i = (y * size + x) * 3
                buf[i], buf[i + 1], buf[i + 2] = _KEYLINE_RGB


# ----- legend ----------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class _LegendRow:
    """One legend entry mapping a label tint → an actor NAME. `kind` picks the swatch glyph (a brush is
    a filled square, a point actor a filled diamond — matching its on-geometry marker); `color` is the
    actor's tint; `text` is the (upper-cased) name."""
    kind: str                       # "brush" | "point"
    color: tuple[int, int, int]
    text: str


def _legend_rows(actors, annotations: "AnnotationSpec", tints, *, highlight_polys, highlight_points,
                 drawn_points) -> list[_LegendRow]:
    """The legend rows for a scene: one per LABELLED brush (gated by the `name:brush[:hi]` selectors)
    and one per LABELLED, DRAWN point actor (gated by `name:point[:hi]`; a point with no render data is
    not drawn, so it is never listed). A brush counts as "highlighted" iff any of its polys is in
    `highlight_polys`; a point iff its name is in `highlight_points`. Focus does NOT filter the legend —
    every labelled name appears regardless of which brush is focused."""
    hp = set(highlight_polys or ())
    hpts = set(highlight_points or ())
    rows: list[_LegendRow] = []
    for a in actors:
        if a.brush is not None:
            hi = any((a.name, idx) in hp for idx in range(len(a.brush.polys)))
            if annotations.draws_name(is_brush=True, is_highlighted=hi):
                rows.append(_LegendRow(kind="brush", color=tints[a.name], text=a.name.upper()))
        elif a.name in drawn_points:
            hi = a.name in hpts
            if annotations.draws_name(is_brush=False, is_highlighted=hi):
                rows.append(_LegendRow(kind="point", color=tints[a.name], text=a.name.upper()))
    return rows


_LEGEND_PAD = 3
_LEGEND_BAND_DIV = 3       # the legend panel is capped to size/this so its RESERVED top band can't crush
                          # the geometry (overflow rows collapse into `+N MORE`); see `_legend_reserve`.


def _legend_metrics(scale: int) -> tuple[int, int, int, int]:
    """(swatch side, swatch↔text gap, glyph/text height, row pitch) in pixels — shared by the panel-rect
    calc and the draw so they never drift."""
    return 5 * scale, 2 * scale, 5 * scale, 5 * scale + 3 * scale


def _fit_legend_rows(rows: list[_LegendRow], scale: int, size: int) -> list[_LegendRow]:
    """Cap the legend to the rows that fit a BAND of `size / _LEGEND_BAND_DIV` px, replacing the
    overflow with a final `+N MORE` row. The band cap (not the full frame) is load-bearing: the panel's
    height is RESERVED as a top inset (`_legend_reserve`), so letting it grow to the full frame would
    crush — or, at some sizes, invert — the geometry. Shared by the panel-rect calc and the draw so both
    agree on how many rows show. `+N MORE`'s glyph slot is a plain `more` row (no swatch)."""
    if not rows:
        return rows
    _, _, gh, row_h = _legend_metrics(scale)
    band = size // _LEGEND_BAND_DIV
    avail = band - 1 - 2 - _LEGEND_PAD * 2 - gh          # panel top is at y=2; leave room for the border
    n_max = max(1, avail // row_h + 1)
    if len(rows) <= n_max:
        return rows
    kept = rows[:n_max - 1]                               # last slot goes to the "+N more" summary
    return kept + [_LegendRow(kind="more", color=DIVIDER, text=f"+{len(rows) - len(kept)} MORE")]


def _legend_panel_rect(rows: list[_LegendRow], scale: int, size: int):
    """The top-left legend panel's pixel box `(x0, y0, x1, y1)`, or None when there are no rows. Sized to
    the widest row and the rows that FIT the frame (`_fit_legend_rows`); clamped inside the frame. Seeded
    into label placement so poly-index labels flee it."""
    rows = _fit_legend_rows(rows, scale, size)
    if not rows:
        return None
    sw, gap, gh, row_h = _legend_metrics(scale)
    text_w = max(len(r.text) * (4 * scale) - scale for r in rows)
    w = _LEGEND_PAD * 2 + sw + gap + text_w
    h = _LEGEND_PAD * 2 + row_h * len(rows) - (row_h - gh)
    return (2, 2, min(2 + w, size - 1), min(2 + h, size - 1))


def _draw_legend(buf, size, rows: list[_LegendRow], scale: int) -> None:
    """Draw the top-left legend: a white panel (grey border) with one row per entry — a filled tint
    swatch (brush = square, point = diamond) + the NAME in black. A tall legend is capped to what fits
    the frame with a `+N MORE` tail (`_fit_legend_rows`). Sits in its RESERVED top band (the geometry is
    framed below it — see `_legend_reserve`), and is drawn LAST. No rows → nothing."""
    rect = _legend_panel_rect(rows, scale, size)
    if rect is None:
        return
    x0, y0, x1, y1 = rect
    _fill(buf, size, x0, y0, x1, y1, WHITE)
    _box(buf, size, x0, y0, x1, y1, DIVIDER)
    sw, gap, gh, row_h = _legend_metrics(scale)
    cy = y0 + _LEGEND_PAD + gh // 2
    for r in _fit_legend_rows(rows, scale, size):
        cx = x0 + _LEGEND_PAD + sw // 2
        if r.kind == "brush":
            _fill(buf, size, cx - sw // 2, cy - sw // 2, cx + sw // 2, cy + sw // 2, r.color)
        elif r.kind == "point":
            _filled_diamond(buf, size, cx, cy, sw // 2, r.color)
        tw = len(r.text) * (4 * scale) - scale
        _draw_text(buf, size, x0 + _LEGEND_PAD + sw + gap + tw // 2, cy, r.text, scale, FRONT)
        cy += row_h


# ----- renderers -------------------------------------------------------------


def point_extent(pr: PointRender) -> float:
    """The max world half-extent a point actor's decorations reach from its Location (for framing)."""
    e = 0.0
    if pr.sprite_world is not None:
        e = max(e, pr.sprite_world[0] / 2, pr.sprite_world[1] / 2)
    if pr.collision is not None:
        e = max(e, pr.collision[0], pr.collision[1])
    if pr.light_radius is not None:
        e = max(e, pr.light_radius)
    if pr.sound_radius is not None:
        e = max(e, pr.sound_radius)
    return e


@dataclass(frozen=True, kw_only=True)
class _SceneGeom:
    """The projected geometry of a preview scene, BEFORE framing/drawing — the shared output of the
    projection loop, so `render_brushes_pgm` computes the projection once and every `--breakdown` pane
    reuses the identical framing."""
    edges: list          # (front, (a2,b2), front_rgb, back_rgb, alpha, face_key) — alpha<1 dims
    fills: list          # (v3, poly2d, rgb, dimmed) in SCENE ORDER — ONE list, so the coplanar tie-break
                         # cannot depend on `--focus`; `dimmed`=1 marks a de-emphasised brush's face
    tex_faces: list      # (frame, mips|None, masked, shade|None) per `fills` entry, `textured` ONLY —
                         # index-aligned with `fills` so the texel loop pairs them; empty otherwise
    hi_edges: list       # ((a2,b2), vivid_rgb, face_key)
    vis_faces: list      # (face_key, v3, poly2d) per surviving face, FILLED MODES ONLY — the faces whose
                         # visibility `render_brushes_pgm` resolves against the finished depth buffer.
                         # Empty under `wire`, which is the structural reason `wire` cannot be affected
    hi_only_labels: set   # face_keys whose index is owed SOLELY to being highlighted
    poly_labels: list    # (centroid2d, idx_str, accent, depth, v3, brush_name) — participant faces
    brush_names: list    # (cands_2d, TEXT, color) — legacy on-geometry names
    occluders: list      # (poly2d, depth, brush_name, is_solid)
    points: list         # (actor, PointRender)
    pts: list            # every projected point (verts + point footprints) — the framing source


def _scene_geometry(actors, *, view, iso_angle, annotations, highlight_polys, focus_cf, hybrid, tints,
                    color_by_csg, render_data, brush_colors="csg", faces="wire") -> _SceneGeom:
    """Run the per-actor projection loop and return `_SceneGeom`. Pure (no drawing); reproduces
    exactly what `render_brushes_pgm`'s inline loop used to build, so the two callers share one
    projection. See `render_brushes_pgm` for the semantics of each accumulated list.

    `faces` is the `--faces` MODE. Under `wire` nothing below changes: every face contributes an edge
    pair regardless of facing, and `fills` stays empty. Under a FILLED mode three rules apply, in this
    order, and each of them removes a face ENTIRELY — no fill, no depth, no edge, no `--highlight`
    outline, no on-face index decal, and no entry in `occluders`:

    1. `PF_Invisible` (the poly's flags OR'd with the ACTOR's own `PolyFlags`, as the engine does).
    2. A SUBTRACT brush's camera-facing polys. Vertices are wound CCW-from-outside, so a subtract's
       near faces are exactly its `_is_front` set — and a subtract's polys looked at from outside the
       carved volume render neither in UnrealEd nor in game. What is left is the far/interior surfaces,
       which is what keeps geometry inside a subtracted room visible instead of hidden by a solid box.
       Mover-ness comes from `FaceData.movers`, never from a name guess: a mover is never carved into
       the world whatever `CsgOper` it carries, so it is not culled.
    3. Nothing else is back-face culled — a `nonsolid` sheet is a single face and must read from both
       sides — so a non-subtract brush fills every face and the depth buffer resolves what shows.

    **EVERY face emits an edge pair here; `render_brushes_pgm` then drops the ones DEPTH HID.** So the rule
    is "visible", never "front-facing" — two owner rulings, and mixing them up re-breaks one or the other.
    A facing condition (spec §4.6) left an away-facing single-sided sheet filled with no outline at all;
    making outlines unconditional then let a brush sealed inside a solid show its wireframe through it. A
    face with no cover is frontmost where it sits, so it keeps its outline under the visibility test but
    would lose it under a facing test — **do not reintroduce one.** Both directions are pinned, and
    `architecture.md` "Preview internals" carries the full history.

    Three more filled-mode rules are commented at their point of use below: which member of the brush's
    colour pair each of fill / edge / `--highlight` takes, the `--focus` split between `fills` and
    `dimmed` flag (the `--focus` brightness split `_fade_dimmed` applies), and the mirror correction
    (`_is_front_corrected`) that makes all of the above right on a reflected brush."""
    from .rotation import actor_linear, actor_prepivot, local_offset
    from .transform import det3
    filled = faces != "wire"
    textured = faces == "textured"
    face_data = render_data.faces
    if filled and face_data is None:
        raise PreviewAbort(f"--faces {faces} needs the resolved face data (the mover set) on the "
                           f"preview seam, and it arrived empty")
    mover_names = face_data.movers if face_data is not None else frozenset()
    tex_data = face_data.textures if face_data is not None else None
    if textured and tex_data is None:
        raise PreviewAbort("--faces textured needs the decoded texture payload on the preview seam, "
                           "and it arrived empty")
    edges: list = []
    fills: list = []
    tex_faces: list = []
    hi_edges: list = []
    vis_faces: list = []
    hi_only_labels: set = set()
    poly_labels: list = []
    brush_names: list = []
    occluders: list = []
    points: list = []
    pts: list = []
    d_vec = _view_depth(iso_angle, view)
    for actor in actors:
        loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
        if actor.brush is None:
            pr = render_data.points.get(actor.name)
            if pr is None:
                continue
            lp = (float(loc[0]), float(loc[1]), float(loc[2]))
            e = point_extent(pr)
            pts.append(_project(lp, view, iso_angle))
            if e:
                for ax in range(3):
                    for s in (-e, e):
                        d = list(lp); d[ax] += s
                        pts.append(_project(tuple(d), view, iso_angle))
            points.append((actor, pr))
            continue
        # ONE CSG key per actor, and it decides three things that must agree: the fill/wire colour,
        # `is_solid` (hence `occluders`, hence decal grading) and the subtract cull. A filled render
        # hands `classify_brush` the authoritative mover answer; `wire` leaves it on the name guess.
        csg_key = classify_brush(actor, is_mover=(actor.name in mover_names) if filled else None)
        if color_by_csg and brush_colors == "legend":
            # colour the wireframe by the actor's own legend TINT (not the CSG op) — drops the CSG
            # cue but tells same-op brushes apart at a glance without reading numbers.
            base = tints[actor.name]
            front_rgb, back_rgb, vivid = base, _fade(base), base
        else:
            csg_front, csg_back = _CSG_PALETTE[csg_key]
            vivid = csg_front
            front_rgb, back_rgb = (csg_front, csg_back) if color_by_csg else (FRONT, BACK)
        is_focus_brush = focus_cf is not None and actor.name.casefold() == focus_cf
        # A non-focused brush is DIMMED by compositing its wireframe at _DIM_ALPHA (not by fading its
        # colour + opaque paint), so its faint lines let crossed edges/numbers show through.
        edge_alpha = _DIM_ALPHA if (focus_cf is not None and not is_focus_brush) else 1.0
        label_accent = tints[actor.name] if hybrid else FRONT
        is_solid = csg_key not in ("subtract", "nonsolid")
        # A subtract's camera-facing polys are culled; every other brush keeps all of them. `csg_key`
        # is already mover-aware, so a mover carrying `CsgOper=CSG_Subtract` never reaches this.
        cull_front = filled and csg_key == "subtract"
        actor_flags = poly_flags_int(dict(actor.props)) if filled else 0
        R = actor_linear(actor)
        # `actor_linear` returns None as its IDENTITY sentinel (no rotation, no scale — the common
        # case), so the mirror test MUST guard it: `det3(actor_linear(a)) < 0` alone raises TypeError on
        # nearly every brush in existence.
        mirrored = filled and R is not None and det3(R) < 0
        prepivot = actor_prepivot(actor)
        brush_cands_2d: list = []
        brush_hi = False
        for idx, poly in enumerate(actor.brush.polys):
            v3 = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2]))
                  for w in (local_offset(R, prepivot, v) for v in poly.vertices)]
            vs = [_project(p, view, iso_angle) for p in v3]
            if not vs:
                continue
            front = _is_front_corrected(v3, view, iso_angle, mirrored=mirrored)
            if filled and (((poly.flags or 0) | actor_flags) & PF_INVISIBLE
                           or (cull_front and front)):
                continue          # removed entirely — fill, depth, edge, outline, decal, occluder
            is_hi = (actor.name, idx) in highlight_polys
            brush_hi = brush_hi or is_hi
            pts.extend(vs)
            brush_cands_2d.extend(vs)
            n = len(vs)
            depth = sum(c * dc for c, dc in zip(
                (sum(p[0] for p in v3) / n, sum(p[1] for p in v3) / n, sum(p[2] for p in v3) / n), d_vec))
            if front:
                occluders.append((vs, depth, actor.name, is_solid))
            # THE FILLED-MODE COLOUR ROLES, all three off ONE two-member pair. `own` is the member this
            # facing fills with, `partner` its opposite — SAME HUE, different luminance, so the CSG cue
            # ("this exact blue means additive") survives every assignment below.
            own, partner = (front_rgb, back_rgb) if front else (back_rgb, front_rgb)
            if filled:
                # FILL: `own`, with NO key-light shade (multiplying the hue would break the cue the
                # legend is read against). A subtract can therefore only ever show its BACK colour,
                # since its camera-facing polys are gone. A HIGHLIGHTED face INVERTS to `partner`, which
                # is what makes it stand out from its neighbours at all — see the edge note below.
                # `dimmed` is a BRIGHTNESS flag and nothing more. Every filled face goes into ONE list in
                # SCENE ORDER and through one rasterizing loop, so what is visible — including which of
                # two coplanar faces wins the strict-`<` tie — is identical whatever `--focus` says
                # (owner ruling: focus dims, it never changes visibility or occlusion). A HIGHLIGHTED face
                # is undimmed wherever its brush is, so `--highlight` still beats `--focus`'s dimming; it
                # does not beat depth, and a hidden highlighted face shows nothing — see the edge note.
                lit = focus_cf is None or is_focus_brush or is_hi
                fills.append((v3, vs, partner if is_hi else own, 0 if lit else 1))
                if textured:
                    # Index-aligned with `fills`: the resolver-free texel data this face draws from.
                    # The UV frame comes from `texframe` (pure); the mip pyramid + masked answer ride
                    # `TextureData`, resolved in dispatch. A highlighted face is NOT inverted here —
                    # `textured` keeps its texture and takes only a highlight OUTLINE (§4.6/§5).
                    frame = world_uv_frame(actor, poly)
                    if not all(math.isfinite(c) for pt in frame for c in pt):
                        raise PreviewAbort(
                            f"--faces textured: actor {actor.name!r} poly {idx} has a non-finite "
                            f"texture frame (Origin/TextureU/TextureV/Pan), so its UV cannot be "
                            f"sampled")
                    ref = _poly_texture_ref(poly)
                    mips = tex_data.by_ref[ref.casefold()] if ref is not None else None
                    masked = tex_data.masked.get((actor.name, idx), False)
                    tex_faces.append((frame, mips, masked, _face_shade(v3)))
            # EDGE: under a filled mode `partner`, NOT `own`. `own` is by definition the colour the fill
            # underneath it already is, so an edge drawn in it is INVISIBLE — which is how `flat` first
            # shipped, and it made decision 2.5's "keep the wireframe" promise vacuous (a room + two
            # adds rendered in exactly three colours, with no interior creases and no boundary between
            # two abutting adds). Owner ruling: draw it in the other member of the pair.
            # `wire` is untouched — it fills nothing, so `own` is the historical, visible choice.
            # It is drawn for EVERY surviving face, front-facing or not (second owner ruling — see the
            # docstring): the same colour-matching that makes an `own` edge invisible is what makes a
            # closed brush's back-face edges cost nothing, and a single-sided face has no front face to
            # borrow an outline from.
            edge_pair = (back_rgb, front_rgb) if filled else (front_rgb, back_rgb)
            # HIGHLIGHT: `own` under a filled mode. The highlighted face already inverted its fill to
            # `partner`, so `own` contrasts with it, AND it differs from every neighbour's `partner`
            # edge — a highlight that only doubled the stroke width in the ordinary edge colour would be
            # a second invisible cue of the same root cause.
            hi_rgb = own if filled else vivid
            # An edge is EMITTED for every surviving face; `render_brushes_pgm` then drops the ones depth
            # hid, which is what makes a solid brush opaque. The two owner rulings that shaped that, and
            # why the narrowing does not undo the one it narrows, are in this function's docstring — not
            # repeated here. A HIGHLIGHT rides the same test: it re-colours what is visible, never x-rays.
            face_key = (actor.name, idx)
            if filled:
                vis_faces.append((face_key, v3, vs))
            for i in range(n):
                a2, b2 = vs[i], vs[(i + 1) % n]
                edges.append((front, (a2, b2)) + edge_pair + (edge_alpha, face_key))
                if is_hi:
                    hi_edges.append(((a2, b2), hi_rgb, face_key))
            show_idx = (annotations.draws_poly(is_front=True, is_highlighted=is_hi)
                        or annotations.draws_poly(is_front=False, is_highlighted=is_hi))
            plain_idx = (annotations.draws_poly(is_front=True, is_highlighted=False)
                         or annotations.draws_poly(is_front=False, is_highlighted=False))
            if focus_cf is not None:
                show_idx = show_idx and (is_focus_brush or is_hi)
                plain_idx = plain_idx and is_focus_brush
            if filled and is_hi and show_idx and not plain_idx:
                # This face would carry NO index if it were not highlighted (`--annotate poly:hi`, or a
                # highlight outside the focused brush), so the index is part of the highlight and goes
                # with it when depth hides the face. An index the spec would have drawn anyway STAYS —
                # on-face numbering is facing-blind by design and grades hidden faces down rather than
                # dropping them, and a highlight must not start deleting numbers.
                hi_only_labels.add(face_key)
            if show_idx:
                poly_labels.append(
                    (_poly_centroid_2d(vs), str(idx), label_accent, depth, v3, actor.name))
        if not hybrid and brush_cands_2d and annotations.draws_name(is_brush=True, is_highlighted=brush_hi):
            brush_names.append((brush_cands_2d, actor.name.upper(), label_accent))
    return _SceneGeom(edges=edges, fills=fills, tex_faces=tex_faces, hi_edges=hi_edges,
                      vis_faces=vis_faces, hi_only_labels=hi_only_labels, poly_labels=poly_labels,
                      brush_names=brush_names, occluders=occluders, points=points, pts=pts)


_FRAME_PAD = 6         # px border kept clear of the geometry on every side (shared by framing + reserve)


def _framing(pts, region, size, view, iso_angle, inset_top: int = 0, pad: int = _FRAME_PAD):
    """World→pixel framing for a scene. Returns `(scale, to_px, to_pxf, world_to_pxf)`, computed from
    the projected `pts` (or an explicit `region` AABB). Shared so every filmstrip pane and the
    grouping pass frame IDENTICALLY (same `minx/span`), keeping geometry registered across panes.
    `pad` is the px border kept clear of the geometry on every side. `inset_top` reserves that many
    extra pixels at the TOP of the frame (for the legend panel) — the geometry is scaled down and pushed
    below the band so nothing draws under the legend. `inset_top=0` is byte-identical to the un-reserved
    framing (`draw == size - 2*pad`)."""
    if region is not None:
        x0, y0, z0, x1, y1, z1 = (float(c) for c in region)
        rp = [_project((x, y, z), view, iso_angle)
              for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        minx, maxx = min(p[0] for p in rp), max(p[0] for p in rp)
        miny, maxy = min(p[1] for p in rp), max(p[1] for p in rp)
    else:
        minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
        miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    span = max(maxx - minx, maxy - miny) or 1.0
    draw = max(1, size - 2 * pad - inset_top)     # uniform-scale budget after the reserved top band
    scale = draw / span

    def to_px(p):
        x = int((p[0] - minx) / span * draw) + pad
        y = size - 1 - (int((p[1] - miny) / span * draw) + pad)
        return x, y

    def to_pxf(p):
        x = (p[0] - minx) / span * draw + pad
        y = size - 1 - ((p[1] - miny) / span * draw + pad)
        return (x, y)

    def world_to_pxf(p3):
        return to_pxf(_project(p3, view, iso_angle))

    return scale, to_px, to_pxf, world_to_pxf


def _legend_reserve(rows: list, name_scale: int, size: int) -> int:
    """Pixels to reserve at the top of the frame for the legend panel (0 if no rows): the panel's
    bottom edge + a small margin, above the normal frame `pad`, so `_framing(inset_top=…)` pushes the
    geometry clear of the panel and it overlaps nothing. The panel is band-capped (`_fit_legend_rows`),
    so this stays a fraction of the frame and never crushes the geometry."""
    rect = _legend_panel_rect(rows, name_scale, size)
    if rect is None:
        return 0
    return max(0, rect[3] + 4 - _FRAME_PAD)      # rect[3] = panel bottom; +4 margin; −pad (already in _framing)


def render_brush_pgm(actor: Actor, *, view: str = "top", size: int = 256,
                     annotations: AnnotationSpec = AnnotationSpec.all(),
                     iso_angle: float = 30.0, region=None,
                     highlight_polys=None, highlight_points=None,
                     color_by_csg: bool = False, render_data=None,
                     focus: str | None = None, draw_legend: bool = True,
                     brush_colors: str = "csg", faces: str = "wire") -> bytes:
    return render_brushes_pgm([actor], view=view, size=size, annotations=annotations,
                              iso_angle=iso_angle, region=region, highlight_polys=highlight_polys,
                              highlight_points=highlight_points,
                              color_by_csg=color_by_csg, render_data=render_data,
                              focus=focus, draw_legend=draw_legend, brush_colors=brush_colors,
                              faces=faces)


def render_brushes_pgm(actors: list[Actor], *, view: str = "top", size: int = 256,
                       annotations: AnnotationSpec = AnnotationSpec.all(),
                       iso_angle: float = 30.0,
                       region=None, highlight_polys=None, highlight_points=None,
                       color_by_csg: bool = False, render_data=None,
                       focus: str | None = None, draw_legend: bool = True,
                       brush_colors: str = "csg", reserve_legend: bool = True,
                       frame_pad: int = _FRAME_PAD, faces: str = "wire",
                       shown_highlights: set | None = None) -> bytes:
    """Render a set of actors as a PPM (P6) on a light-grey background (BG).

    `faces` is the `--faces` MODE, and it is a parameter rather than something read off `render_data`
    because `render_data.faces is None` would be both `wire` and a filled mode. `wire` (the default)
    draws outlines only. `flat` additionally fills every surviving face solid in its brush's colour
    through a depth buffer — a diagram of what occludes what — and KEEPS the wireframe over the fills;
    it needs `render_data.faces` populated (see `_scene_geometry` for the cull and the edge rule).

    Brush actors draw as a wireframe: front faces darker, obscured/back faces lighter. When
    `color_by_csg` the shade pair is the brush's CSG hue (`classify_brush` → `_CSG_PALETTE`);
    otherwise black/grey. A `flat` fill uses that SAME pair, unshaded, picked by facing.
    `highlight_polys` is a set of `(actor_name, poly_idx)` — those polys draw
    in their brush's vivid front hue with a bolder line (facing dim ignored). `highlight_points` is a
    set of point-actor names — each gets corner brackets (a selection reticle) under its sprite/marker.

    On the CSG-coloured path (`color_by_csg`, the real preview) the labels use the HYBRID scheme: the
    wireframe keeps its CSG hue, but each actor's LABELS carry a distinct per-actor TINT
    (`assign_tints`) — a brush's on-face poly-index decals + its point marker — so two same-CSG
    brushes are told apart; a top-left LEGEND (drawn when `draw_legend`) maps each tint → actor NAME, and
    actor names move OFF the geometry into it. The legacy black/grey path (unit tests) keeps black
    accents, on-geometry names, and no legend.

    `focus` (an actor NAME, case-insensitive) recedes every OTHER brush — its wireframe to faint lines,
    and under a filled mode its fills to a single dimmed fade of whatever survived the depth test (the
    `dim` mask below) — and paints face numbers only for the focused brush;
    `highlight_polys`/`highlight_points` OVERRIDE focus — a highlighted poly/actor still draws vivid+bold
    on top, at full fill strength, and keeps its number. All names still appear in the legend regardless
    of focus.

    `annotations` is an `AnnotationSpec` (see `parse_annotation_spec`): per kind, the set of element categories that
    get a label — `draws_poly` decides WHETHER a face is numbered (on-face numbering is facing-blind, so
    `poly:vis` numbers every face; `poly:hi`/`none` stay exact), `draws_name(is_brush, is_highlighted)`
    decides each actor name (⇒ its legend row on the hybrid path).

    Poly face indices ALWAYS render ON-FACE: each face's index is a texture painted flat IN
    the face's own 3-D plane at its roomiest spot (`_plan_onface_texture` / `_draw_painted_decal`) —
    front AND back faces (facing-blind), graded translucent by depth (`_decal_opacity` of the
    self-or-solid `_occluder_count`), omitted when the number would be unreadable ON SCREEN
    (view-dependent; no leader fallback). Actor names
    go to the legend (hybrid path); `focus`/`highlight` still apply.

    `shown_highlights`, when a set is passed, collects the `(actor_name, poly_idx)` key of every
    highlighted face that actually DREW. It reports what landed rather than what did not, which is what
    makes it correct across panes: a face hidden in one pane and visible in another is still a highlight
    that landed, so a multi-pane caller passes ONE set through every pane and subtracts at the end.

    Point (non-brush) actors are drawn from `render_data.points` (name → `PointRender`): a DT_Sprite
    billboard, else a marker; plus faint collision/light/sound overlays when populated.
    Empty input → blank grey PPM."""
    highlight_polys = set(highlight_polys or ())
    highlight_points = set(highlight_points or ())
    render_data = render_data or PreviewData()
    hybrid = color_by_csg                     # the real preview: per-actor tints + legend + names-in-legend
    tints = assign_tints(actors) if hybrid else {}
    focus_cf = focus.casefold() if focus else None
    geom = _scene_geometry(actors, view=view, iso_angle=iso_angle, annotations=annotations,
                           highlight_polys=highlight_polys, focus_cf=focus_cf, hybrid=hybrid,
                           tints=tints, color_by_csg=color_by_csg, render_data=render_data,
                           brush_colors=brush_colors, faces=faces)
    edges, hi_edges, poly_labels = geom.edges, geom.hi_edges, geom.poly_labels
    brush_names, occluders, points = geom.brush_names, geom.occluders, geom.points

    if not geom.pts:
        return _ppm(_alloc_buffers(size, depth=False)[0], size)
    # Legend rows are computed BEFORE framing (they don't depend on it) so the legend's top band can be
    # RESERVED — geometry is inset below it so the panel overlaps nothing. `reserve_legend` (inset the
    # band) and `draw_legend` (paint the panel) are independent flags: a caller can reserve WITHOUT
    # drawing (e.g. to keep framing identical across panes that share a region) — see `render_quad_pgm`.
    name_scale = max(2, size // 256)
    legend_rows = _legend_rows(actors, annotations, tints, highlight_polys=highlight_polys,
                               highlight_points=highlight_points,
                               drawn_points={a.name for a, _ in points}) if hybrid else []
    # Drawing the legend ALWAYS reserves its band (never paint the panel over un-inset geometry).
    inset_top = _legend_reserve(legend_rows, name_scale, size) if (reserve_legend or draw_legend) else 0
    scale, to_px, to_pxf, world_to_pxf = _framing(geom.pts, region, size, view, iso_angle, inset_top,
                                                  pad=frame_pad)

    hidden: set = set()             # faces depth hid — their edges, outline and highlight index go
    buf, zbuf = _alloc_buffers(size, depth=bool(geom.fills))
    # Face fills sit here, immediately after the background and AHEAD of the point layer: they are
    # brush geometry, and drawing them later would paint over every sprite and every `--show` overlay.
    if zbuf is not None:
        d_vec = _view_depth(iso_angle, view)

        # ONE loop over every filled face in SCENE ORDER, dimmed or not. `--focus` is a brightness filter
        # and must not touch visibility, and the strict-`<` depth test hands a coplanar tie to whichever
        # face is rasterized FIRST — so splitting the de-emphasised faces into a pass of their own let
        # `--focus` decide which of two flush surfaces you saw, exactly what it may never do. `dim` records
        # whether a DE-EMPHASISED face won each pixel, and `_fade_dimmed` fades those pixels once at the
        # end: one blend per pixel with no second rasterizing pass and no scratch canvas.
        dim = _alloc_dim_mask(size) if any(f[3] for f in geom.fills) else None
        textured = faces == "textured"
        for i, (v3, vs, rgb, dimmed) in enumerate(geom.fills):
            plane = _face_depth_affine(v3, world_to_pxf, d_vec)
            if plane is None:                       # edge-on: no screen area to fill
                continue
            poly_px = [to_pxf(p) for p in vs]
            if not textured:
                _fill_face(buf, zbuf, size, poly_px, plane, rgb, dim, dimmed)
                continue
            frame, mips, masked, shade = geom.tex_faces[i]
            if shade is None:                       # <3 verts / degenerate normal — render.rs skips it
                continue
            if mips is None:                        # poly has no Texture → DEFAULT_GREY × shade (§4.3)
                grey = tuple(min(int(DEFAULT_GREY[c] * shade), 255) for c in range(3))
                _fill_face(buf, zbuf, size, poly_px, plane, grey, dim, dimmed)
                continue
            uv = _face_uv_affine(v3, frame, world_to_pxf)
            if uv is None:                          # edge-on in the UV solve too
                continue
            (au, bu, _cu), (av, bv, _cv) = uv
            level = _mip_level(au, bu, av, bv, len(mips))
            _fill_face_textured(buf, zbuf, size, poly_px, plane, uv, mips[level], masked, shade,
                                1.0 / (1 << level), dim, dimmed)
        if dim is not None:
            _fade_dimmed(buf, dim, size, _DIM_FILL_ALPHA)
        # Every fill is down, so `zbuf` is FINAL and each face can be asked whether DEPTH hid it. Those
        # draw no outline, no `--highlight` outline and no highlight-owed index below — a solid brush is
        # opaque and a highlight is not an x-ray. One extra scanline walk per filled face, so the fill
        # stage roughly doubles; accepted (no cost ceiling, decision 2.4).
        #
        # An EDGE-ON face (`plane is None`, the guard here) or one too thin to cover a pixel centre
        # (`_face_is_occluded`'s own `covered` result) is deliberately NOT in `hidden`: nothing is in front
        # of it, so it keeps its outline. The two are SEPARATE halves of one rule and are pinned separately
        # — on a sliver brush in `top` the coverage-losing caps and the edge-on sides project to the same
        # 2-D lines, so getting either half right still draws the outline, and the fully visible brush
        # vanished from a filled render only because the original single condition got both wrong.
        for face_key, v3, vs in geom.vis_faces:
            plane = _face_depth_affine(v3, world_to_pxf, d_vec)
            if plane is not None and _face_is_occluded(zbuf, size, [to_pxf(q) for q in vs], plane):
                hidden.add(face_key)
    grid = DensityGrid.build(size)                  # occupancy of the wireframe → labels flee dense knots
    for f, (a, b), fr, bk, al, fk in edges:
        if fk not in hidden:                        # a hidden edge paints nothing, so it must not pull
            grid.add_segment(to_px(a), to_px(b))    # labels away from a region that reads as empty
    for actor, pr in points:                        # under-layer: selection brackets + sprites + overlays
        _draw_point_underlay(buf, size, actor, pr, view, iso_angle, to_px, scale,
                             highlighted=actor.name in highlight_points)
    # `textured` draws NO wireframe (decision 2.5): only `--highlight` outlines below are line art.
    # `wire`/`flat` draw the back (lighter) then front (darker) edges of every non-depth-hidden face.
    draw_wire = faces != "textured"
    for f, (a, b), fr, bk, al, fk in edges:         # back (lighter) then front (darker)
        if draw_wire and not f and fk not in hidden:
            _line(buf, size, to_px(a), to_px(b), bk, alpha=al)
    for f, (a, b), fr, bk, al, fk in edges:
        if draw_wire and f and fk not in hidden:
            _line(buf, size, to_px(a), to_px(b), fr, alpha=al)
    for (a, b), vivid, face_key in hi_edges:         # highlighted poly: vivid hue + bold, on top
        if face_key not in hidden:                  # ...unless depth hid the face (filled modes only)
            landed = _line(buf, size, to_px(a), to_px(b), vivid, weight=2)
            # Record only a stroke that put PIXELS ON THE CANVAS. Counting the call instead made a
            # highlight clipped entirely outside the frame — ordinary with `--frame <other brush>` —
            # look drawn, so the note stayed silent on exactly the case it exists for.
            if landed and shown_highlights is not None:
                shown_highlights.add(face_key)
    for actor, pr in points:                        # over-layer: markers (names → legend/placement below)
        _draw_point_marker(buf, size, actor, pr, view, iso_angle, to_px,
                           color=tints.get(actor.name, MARKER) if hybrid else MARKER, hybrid=hybrid)

    # Point-actor footprints: seed `occupied` (so a label never covers an icon) AND the density grid
    # (so a brush-name anchor, chosen next, flees actor icons — not just wireframe). Must precede the
    # brush-name anchor choice below. (`name_scale`/`legend_rows` were computed above for the reserve.)
    occupied: list = []
    point_name_items: list = []          # LEGACY (non-hybrid) on-geometry point names
    for actor, pr in points:
        loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
        px = to_px(_project((float(loc[0]), float(loc[1]), float(loc[2])), view, iso_angle))
        # A marker-only point draws a radius-7 WHITE halo (see `_draw_point_marker`), so reserve >=7 or a
        # label could clip it; a sprite point reserves its half-footprint (min 6).
        r = max(6, int(max(pr.sprite_world) / 2 * scale)) if pr.sprite_world else 7
        rect = (px[0] - r, px[1] - r, px[0] + r, px[1] + r)
        occupied.append(rect)
        grid.add_box(rect, weight=4)
        if not hybrid and pr.label and annotations.draws_name(
                is_brush=False, is_highlighted=actor.name in highlight_points):
            point_name_items.append(_LabelItem(anchor=px, text=pr.label.upper(), scale=name_scale,
                                               color=MARKER))

    # HYBRID legend (rows computed above): reserve its footprint in `occupied` + the density grid so
    # any legacy name label flees it; it sits in the reserved top band and is drawn LAST.
    legend_rect = _legend_panel_rect(legend_rows, name_scale, size)
    if legend_rect is not None:
        occupied.append(legend_rect)
        grid.add_box(legend_rect, weight=8)

    # Poly indices: THE ONE RULE — a face's INDEX is a painted number texture (`_plan_onface_texture`)
    # lying in the face's own 3-D plane at its ROOMIEST spot (largest glyph-box inside the face, ×0.75;
    # front AND back faces, facing-blind — see `show_idx`), foreshortening naturally under
    # projection. OPACITY is GRADED by depth via `_decal_opacity(_occluder_count(...))` — a visible face
    # 0.56, one layer behind 0.336, floored at 0.12 (opacity IS the front/back cue) — with the 6/9 baseline
    # underline and a translucent halo. A face is OMITTED when its number would be UNREADABLE ON SCREEN
    # (projected texels below a min pixel size — VIEW-DEPENDENT, so a tiny/edge-on/zoomed-out face drops
    # out and reappears when big enough). Decals draw AFTER any name labels and seed `occupied` so name leaders avoid
    # them. The tint (`accent`) is the owning actor's per-brush tint on the hybrid path, so a face number
    # shared across brushes (every brush has a face `1`) is distinguishable by tint + the legend.
    # Overlap handling: resolve all faces' numbers JOINTLY so a decal MINIMALLY nudges (≤10% shrink,
    # ≤10%-diagonal move) WITHIN ITS OWN FACE off another decal or a point-actor marker (obstacles already
    # in `occupied`); a zero-overlap decal keeps its roomiest spot verbatim (opacity is placement-
    # independent, face-centroid based). `_draw_overlap_keyline` then rings any residual overlap in white.
    dropped_labels = hidden & geom.hi_only_labels    # hoisted: constant over the loop below
    painted_draws: list = []         # (_DecalPlan, tint, opacity)
    decal_entries: list = []         # (order_key, candidates)
    decal_meta: list = []            # (tint, opacity) aligned to decal_entries
    for c, t, accent, dep, v3face, brush_name in poly_labels:
        if (brush_name, int(t)) in dropped_labels:
            continue                                 # an index the highlight alone asked for, on a face
        cands = _onface_candidates(v3face, world_to_pxf, t)   # depth hid — it goes with the highlight
        primary_area = _plan_px_area(cands[0]) if cands else 0.0
        decal_entries.append(((-primary_area, brush_name, t), cands))       # biggest, hardest-to-move first
        decal_meta.append((accent, _decal_opacity(_occluder_count(c, dep, occluders, own_brush=brush_name))))
    for plan, (accent, opacity) in zip(_resolve_decals(decal_entries, occupied), decal_meta):
        if plan is not None:
            painted_draws.append((plan, accent, opacity))
            occupied.append(plan.bbox())             # so name leaders avoid the decal

    # One placement pass over the LEGACY (non-hybrid) on-geometry NAMES only — poly indices are painted
    # on-face above, never placed here; on the hybrid path names live in the legend so this is empty.
    items: list = []
    hb = name_scale * 4                              # density-sample box half-size for anchor choice
    for cands_2d, text, color in brush_names:
        anchor = _least_dense_anchor(grid, [to_px(p) for p in cands_2d], hb)
        items.append(_LabelItem(anchor=anchor, text=text, scale=name_scale, color=color))
    items += point_name_items
    for placed in _place_labels(items, size, grid=grid, occupied=occupied):
        (ax, ay), (lx, ly), accent = placed.anchor, placed.pos, placed.color
        # Tie the name to its target with a leader ending in an ARROWHEAD pointing at the exact spot (its
        # actor/wireframe corner); the leader/arrow/box border are the owning actor's accent (grey in
        # legacy) and the text stays black. The leader starts at the box edge (not its centre) so it
        # never runs under the text.
        box_fill = WHITE                              # this loop runs only for legacy (non-hybrid) names
        w, h = _label_size(placed.text, placed.scale)
        edge = _rect_edge_toward((lx, ly), w // 2 + 2, h // 2 + 2, (ax, ay))
        _line(buf, size, edge, (ax, ay), accent)
        _arrowhead(buf, size, (ax, ay), edge, accent)
        _fill(buf, size, lx - w // 2 - 2, ly - h // 2 - 2, lx + w // 2 + 2, ly + h // 2 + 2, box_fill)
        _box(buf, size, lx - w // 2 - 2, ly - h // 2 - 2, lx + w // 2 + 2, ly + h // 2 + 2, accent)
        _draw_text(buf, size, lx, ly, placed.text, placed.scale, FRONT)
    painted_on: list = []
    for plan, tint, opacity in painted_draws:
        # Painted index: the digit lying flat in the face's plane (world-up-anchored on walls, world-Y on
        # caps), tinted per brush, blended at the face's graded `opacity` over a proportional halo.
        painted_on.append(_draw_painted_decal(buf, size, plan, tint, alpha=opacity))
    _draw_overlap_keyline(buf, size, painted_on)     # 1px white ring wherever two numbers overlap
    if draw_legend and legend_rect is not None:      # rows/band are always reserved; only pane 0 draws
        _draw_legend(buf, size, legend_rows, name_scale)
    return _ppm(buf, size)


def _draw_point_underlay(buf, size, actor, pr: PointRender, view, iso_angle, to_px, scale,
                         *, highlighted: bool = False) -> None:
    """Corner brackets — a selection reticle — (when highlighted) + sprite billboard + faint
    collision/range overlays for one point actor (drawn UNDER the wireframe so the geometry stays
    readable). The brackets frame the sprite/marker from OUTSIDE, so they don't obscure it; they are
    drawn FIRST so the sprite (with its transparency mask) still composites on top."""
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    lp = (float(loc[0]), float(loc[1]), float(loc[2]))
    cx, cy = to_px(_project(lp, view, iso_angle))
    if highlighted:
        # frame the sprite/marker: half the larger sprite footprint (px) + 4, else a fixed radius
        # comfortably around the 3px diamond marker.
        r = (max(pr.sprite_world[0], pr.sprite_world[1]) * scale / 2 + 4
             if (pr.sprite is not None and pr.sprite_world is not None) else 10.0)
        _draw_selection_brackets(buf, size, cx, cy, r)
    if pr.sprite is not None and pr.sprite_world is not None:
        w, h, rgb, mask = pr.sprite
        pw = int(round(pr.sprite_world[0] * scale))
        ph = int(round(pr.sprite_world[1] * scale))
        _blit(buf, size, cx, cy, pw, ph, rgb, mask, w, h)
    if pr.collision is not None:
        _draw_cylinder(buf, size, lp, pr.collision[0], pr.collision[1], view, iso_angle,
                       to_px, scale, COL_COLLISION)
    if pr.light_radius is not None:
        _draw_sphere(buf, size, lp, pr.light_radius, view, iso_angle, to_px, scale, COL_LIGHT)
    if pr.sound_radius is not None:
        _draw_sphere(buf, size, lp, pr.sound_radius, view, iso_angle, to_px, scale, COL_SOUND)


def _draw_point_marker(buf, size, actor, pr: PointRender, view, iso_angle, to_px,
                       *, color=MARKER, hybrid: bool = False) -> None:
    """The point actor's marker (only when there is no sprite) at its Location, drawn OVER the wireframe.
    On the hybrid path it is a small FILLED DIAMOND in the actor's tint (matching its legend glyph, so a
    reader can key marker→name); on the legacy path a neutral-grey `+`. The actor's NAME is not drawn
    here — on the hybrid path it lives in the legend; on the legacy path it joins the unified label pass."""
    if pr.sprite is not None:                       # DT_Sprite draws its own billboard (underlay)
        return
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    cx, cy = to_px(_project((float(loc[0]), float(loc[1]), float(loc[2])), view, iso_angle))
    if hybrid:
        _filled_diamond(buf, size, cx, cy, 7, WHITE)    # halo lifts the marker off both bg and wireframe
        _filled_diamond(buf, size, cx, cy, 5, color)
        return
    for d in range(-3, 4):                           # DT_Mesh/DT_None/miss → a small neutral marker
        _px(buf, size, cx + d, cy, color)
        _px(buf, size, cx, cy + d, color)


# ISO collision-cylinder facet count. MUST be ODD (9), and that is LOAD-BEARING, not cosmetic: under
# the iso projection screen-x ∝ (cos θ − sin θ), and an EVEN count is mirror-symmetric so that value
# repeats — two vertical edges then land on the same screen column and "shadow" into one line (8@0°
# doubles the centerline; rotating an even count only relocates the doubling, never removes it). An
# odd count makes every edge's screen-x distinct. 9 = round enough without excess lines; bump to 11/13
# for rounder, but keep it ODD. Do NOT change to an even number.
_ISO_CYL_SEGMENTS = 9


def _draw_cylinder(buf, size, lp, radius, half_h, view, iso_angle, to_px, scale, rgb) -> None:
    """Collision cylinder — a TOP circle, a FRONT/SIDE `2r × 2h` rect, or an ISO wire cylinder
    (`_ISO_CYL_SEGMENTS` facets — ODD so no two vertical edges coincide on a screen column; see that
    constant). `half_h` is the HALF-height (the cylinder spans Location.Z ± half_h); upright,
    world-axis-aligned regardless of actor rotation (spike Q2, UnrealEd `SHOW_ActorRadii`)."""
    cx, cy = to_px(_project(lp, view, iso_angle))
    if view == "top":
        _circle(buf, size, cx, cy, radius * scale, rgb)
    elif view in ("front", "side"):
        rx, ry = int(round(radius * scale)), int(round(half_h * scale))
        _box(buf, size, cx - rx, cy - ry, cx + rx, cy + ry, rgb)
    else:                                            # iso: odd-facet wire cylinder, no column shadowing
        n = _ISO_CYL_SEGMENTS
        top = [(lp[0] + radius * math.cos(a), lp[1] + radius * math.sin(a), lp[2] + half_h)
               for a in (2 * math.pi * i / n for i in range(n))]
        bot = [(x, y, lp[2] - half_h) for x, y, _ in top]
        tp = [to_px(_project(p, view, iso_angle)) for p in top]
        bp = [to_px(_project(p, view, iso_angle)) for p in bot]
        for i in range(n):
            _line(buf, size, tp[i], tp[(i + 1) % n], rgb)
            _line(buf, size, bp[i], bp[(i + 1) % n], rgb)
            _line(buf, size, tp[i], bp[i], rgb)


def _draw_sphere(buf, size, lp, radius, view, iso_angle, to_px, scale, rgb) -> None:
    """Light/sound reach — a sphere silhouettes to a CIRCLE under ANY parallel projection (iso
    included), NOT the equator ring (which would project to a tilted ellipse). So it's a circle in
    every view. In ISO the projection uniformly scales lengths by `iso_scale` (√1.5 at the default
    30° — the `_project` rows are orthogonal + equal-length there), so the silhouette circle is
    `radius·iso_scale` in projected units; ortho views project 1:1 (`iso_scale`=1)."""
    cx, cy = to_px(_project(lp, view, iso_angle))
    if view == "iso":
        rr = math.radians(iso_angle)
        iso_scale = max(math.sqrt(2) * math.cos(rr), math.sqrt(2 * math.sin(rr) ** 2 + 1))
    else:
        iso_scale = 1.0
    _circle(buf, size, cx, cy, radius * iso_scale * scale, rgb)


def render_quad_pgm(actors, *, size: int = 512,
                    annotations: AnnotationSpec = AnnotationSpec.all(),
                    iso_angle: float = 30.0, region=None, highlight_polys=None,
                    highlight_points=None, color_by_csg: bool = False, render_data=None,
                    focus: str | None = None, brush_colors: str = "csg",
                    faces: str = "wire", shown_highlights: set | None = None) -> bytes:
    """UED-style 2×2: Top (TL), Front (TR), Iso (BL), Side (BR). On the hybrid (`color_by_csg`) path the
    per-actor tints are identical across panes (`assign_tints` is deterministic), so the legend is drawn
    ONCE — only the TOP-left pane renders it (`draw_legend=True`) and RESERVES a top band for it
    (`reserve_legend=True`, so its geometry is inset clear of the panel); the other three panes pass
    both False and use their full area. The TOP pane's "TOP" caption is dropped below the legend."""
    if isinstance(actors, Actor):
        actors = [actors]
    half = size // 2
    hdr = f"P6\n{half} {half}\n255\n".encode()
    buf, _ = _alloc_buffers(size, depth=False)
    # The legend lives in the TOP pane's corner (pane-local (2,2) == full-image (2,2) since TOP is at
    # offset (0,0)); recompute its rect at the pane's size/scale to place the caption clear of it.
    legend_rect = None
    if color_by_csg:
        rd = render_data or PreviewData()
        tints = assign_tints(actors)
        drawn_points = {a.name for a in actors if a.brush is None and a.name in rd.points}
        rows = _legend_rows(actors, annotations, tints, highlight_polys=highlight_polys,
                            highlight_points=highlight_points, drawn_points=drawn_points)
        legend_rect = _legend_panel_rect(rows, max(2, half // 256), half)
    panes = [("TOP", "top", 0, 0), ("FRONT", "front", half, 0),
             ("ISO", "iso", 0, half), ("SIDE", "side", half, half)]
    for name, view, ox, oy in panes:
        top_legend = color_by_csg and name == "TOP"
        sub = render_brushes_pgm(actors, view=view, size=half, annotations=annotations,
                                 iso_angle=iso_angle, region=region,
                                 highlight_polys=highlight_polys, highlight_points=highlight_points,
                                 color_by_csg=color_by_csg, render_data=render_data,
                                 focus=focus, draw_legend=top_legend, reserve_legend=top_legend,
                                 brush_colors=brush_colors, faces=faces,
                                 shown_highlights=shown_highlights)
        body = sub[len(hdr):]
        for j in range(half):
            dst = ((oy + j) * size + ox) * 3
            src = j * half * 3
            buf[dst:dst + half * 3] = body[src:src + half * 3]
        cap_y = oy + 12
        if name == "TOP" and legend_rect is not None:    # keep the caption below the legend, never under it
            cap_y = legend_rect[3] + 8
        _draw_text(buf, size, ox + 4 + len(name) * 8, cap_y, name, 2, CAPTION)
    for k in range(size):
        _px(buf, size, half, k, DIVIDER)
        _px(buf, size, k, half, DIVIDER)
    return _ppm(buf, size)
